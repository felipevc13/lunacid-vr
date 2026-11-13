#!/usr/bin/env python3
"""
Lunacid VR: build the Quest port and put it on the headset, on macOS or Windows.

    python3 lunacid_vr.py doctor            # is this machine ready? (Unity, adb, disk, game version, signing key)
    python3 lunacid_vr.py build [--fast]    # build the APK (and OBB); see tools/build/build.py
    python3 lunacid_vr.py backup            # copy the Quest's saves and this machine's signing key
    python3 lunacid_vr.py install           # backup, then put the newest build on the Quest (never uninstalls)
    python3 lunacid_vr.py restore [folder]  # put a backup's saves back on the Quest

Paths come from core/config.py (LUNA_<KEY>, then local.json, then defaults).
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

PKG = "com.AkumaKira.LunacidVR"
SAVES_DIR = "/sdcard/Android/data/%s/files" % PKG
OBB_DIR = "/sdcard/Android/obb/%s" % PKG


class Problem(Exception):
    """Something the person must fix; printed without a traceback."""


def adb_path(cfg):
    """adb from the configured Android SDK, else from the PATH."""
    sdk = cfg.get("android_sdk")
    exe = "adb.exe" if os.name == "nt" else "adb"
    cand = os.path.join(sdk, "platform-tools", exe) if sdk else None
    if cand and os.path.exists(cand):
        return cand
    return shutil.which("adb")


def adb_runner(adb):
    """run(args) -> (exit code, output) for a real adb."""
    def run(args):
        try:
            res = subprocess.run([adb] + list(args), capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return 1, "adb timed out: %s" % " ".join(args)
        return res.returncode, (res.stdout + res.stderr).replace("\r", "")
    return run


def _q(path):
    return "'%s'" % path


def _is_network(serial):
    return ":" in serial or "._adb-tls" in serial


def pick_serial(run, env=None):
    """Which device adb should talk to: ANDROID_SERIAL when set (adb's own variable); the only device; or, when
    every device is the same headset (USB and Wi-Fi at once), the USB one. Different headsets: ask which.
    None when nothing is connected (Device.require says so)."""
    env = os.environ if env is None else env
    if env.get("ANDROID_SERIAL"):
        return env["ANDROID_SERIAL"]
    _, out = run(["devices"])
    serials = [line.split()[0] for line in out.splitlines()[1:] if len(line.split()) >= 2 and line.split()[1] == "device"]
    if len(serials) <= 1:
        return serials[0] if serials else None
    hardware = {s: run(["-s", s, "shell", "getprop ro.serialno"])[1].strip() for s in serials}
    if len(set(hardware.values())) > 1:
        raise Problem("more than one headset is connected (%s): choose one with ANDROID_SERIAL=<serial>"
                      % ", ".join(serials))
    usb = [s for s in serials if not _is_network(s)]
    return (usb or serials)[0]


class Device:
    """The headset, through adb. Every call goes through run(args) so the tests can stand in for adb."""

    def __init__(self, run, serial=None):
        self.serial = serial
        self.run = (lambda args: run(["-s", serial] + list(args))) if serial else run

    def require(self):
        rc, out = self.run(["get-state"])
        if rc != 0 or out.strip() != "device":
            detail = out.strip().splitlines()[-1] if out.strip() else "no output"
            raise Problem("no Quest answers adb (%s): plug it in by USB, allow USB debugging in the headset, "
                          "then try again" % detail)

    def shell(self, line):
        return self.run(["shell", line])

    def sizes(self, folder, suffix):
        """{remote path: size} of the files in folder whose name ends with suffix."""
        rc, out = self.shell("find %s -maxdepth 1 -type f -name '*%s' -exec stat -c '%%s|%%n' {} +" % (folder, suffix))
        found = {}
        for line in out.splitlines():
            size, sep, path = line.strip().partition("|")
            if sep and size.isdigit() and path.endswith(suffix):
                found[path] = int(size)
        if rc != 0 and not found and "No such file" not in out:
            raise Problem("could not list %s on the Quest: %s" % (folder, out.strip()))
        return found

    def size(self, path):
        rc, out = self.shell("stat -c %%s %s" % _q(path))
        return int(out.strip()) if rc == 0 and out.strip().isdigit() else None

    def cat(self, path):
        rc, out = self.shell("cat %s" % _q(path))
        return out.strip() if rc == 0 else None

    def pull(self, remote, local):
        rc, out = self.run(["pull", remote, local])
        if rc != 0:
            raise Problem("adb pull %s failed: %s" % (remote, out.strip()))

    def push(self, local, remote):
        rc, out = self.run(["push", local, remote])
        if rc != 0:
            raise Problem("adb push %s failed: %s" % (remote, out.strip()))


def backup(cfg, dev, stamp=None):
    """Copy every save (*.MIDNIGHT) from the Quest, one file at a time with its size checked against the headset
    (a whole-folder adb pull once copied nothing and said OK), and this machine's signing key, into
    <work>/backups/<date-time>/. Returns that folder."""
    dev.require()
    saves = dev.sizes(SAVES_DIR, ".MIDNIGHT")
    out = os.path.join(cfg["work"], "backups", stamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=True)
    copied = {}
    for remote, size in sorted(saves.items()):
        name = os.path.basename(remote)
        local = os.path.join(out, name)
        dev.pull(remote, local)
        got = os.path.getsize(local) if os.path.exists(local) else -1
        if got != size:
            raise Problem("backup of %s is %d bytes, the Quest has %d: the backup in %s is not good"
                          % (name, got, size, out))
        copied[name] = size
    key = os.path.join(cfg["work"], "keystore")
    if os.path.isdir(key):
        shutil.copytree(key, os.path.join(out, "keystore"), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("._*"))
    with open(os.path.join(out, "backup.json"), "w", encoding="utf-8") as fh:
        json.dump({"saves": copied, "keystore": os.path.isdir(key)}, fh, indent=2)
    return out


BACKUP_FOLDER = re.compile(r"^\d{8}_\d{6}$")


def newest_backup(cfg):
    """The newest <work>/backups/<date-time> folder that holds a game save (SAVE_*). A folder with only SETTINGS is
    skipped: after a fresh install the game's first launch writes default settings, and restore backs those up
    before pushing, so that folder is newer than the one with the progress."""
    root = os.path.join(cfg["work"], "backups")
    for name in sorted((n for n in (os.listdir(root) if os.path.isdir(root) else []) if BACKUP_FOLDER.match(n)),
                       reverse=True):
        manifest = os.path.join(root, name, "backup.json")
        if os.path.exists(manifest):
            with open(manifest, encoding="utf-8") as fh:
                if any(n.startswith("SAVE_") for n in json.load(fh).get("saves", {})):
                    return os.path.join(root, name)
    raise Problem("no backup with a game save (SAVE_*) in %s: run 'python3 lunacid_vr.py backup' first" % root)


def _md5(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def restore(cfg, dev, folder=None, stamp=None, say=print):
    """Put a backup's saves back on the Quest (the newest backup with saves, or folder). The game must be installed
    and opened once (it makes its files folder). Saves already on the Quest are backed up first; the game is
    stopped so it cannot write over them; each file is checked by size and md5 on the headset."""
    folder = folder or newest_backup(cfg)
    manifest = os.path.join(folder, "backup.json")
    if not os.path.exists(manifest):
        raise Problem("%s is not a backup made by this tool (no backup.json)" % folder)
    with open(manifest, encoding="utf-8") as fh:
        saves = json.load(fh)["saves"]
    if not saves:
        raise Problem("%s has no saves" % folder)
    dev.require()
    rc, out = dev.shell("pm path %s" % PKG)
    if rc != 0 or "package:" not in out:
        raise Problem("the game is not installed on the Quest: run 'python3 lunacid_vr.py install' first")
    rc, _ = dev.shell("ls -d %s" % _q(SAVES_DIR))
    if rc != 0:
        raise Problem("the game has no files folder yet: open the game once on the Quest, quit, then restore")
    dev.shell("am force-stop %s" % PKG)
    if dev.sizes(SAVES_DIR, ".MIDNIGHT"):
        say("saves on the Quest backed up first: %s" % backup(cfg, dev, stamp=stamp))
    for name, size in sorted(saves.items()):
        local = os.path.join(folder, name)
        if not os.path.exists(local) or os.path.getsize(local) != size:
            raise Problem("%s in %s is missing or not %d bytes as recorded: not restoring" % (name, folder, size))
        remote = "%s/%s" % (SAVES_DIR, name)
        dev.push(local, remote)
        # adb push leaves the file owned by shell with 644; the game runs as its own uid outside group ext_data_rw,
        # so it could read the save but never write it again. The folder (drwxrws---, owned by the game) still
        # keeps every other app out.
        dev.shell("chmod 666 %s" % _q(remote))
        rc, mode = dev.shell("stat -c %%a %s" % _q(remote))
        if rc != 0 or mode.strip() != "666":
            raise Problem("could not let the game write %s on the Quest (mode %s)" % (name, mode.strip()))
        rc, out = dev.shell("md5sum %s" % _q(remote))
        got = out.split()[0] if rc == 0 and out.split() else None
        if dev.size(remote) != size or got != _md5(local):
            raise Problem("%s on the Quest does not match the backup after the push: the backup is still in %s"
                          % (name, folder))
    say("restored %d saves from %s" % (len(saves), folder))
    return folder

APK_NAME = "Lunacid_Quest.apk"
OBB_NAME = "Lunacid_Quest.main.obb"
BUILD_FOLDER = re.compile(r"^\d{8}_\d{4}$")


def newest_build(cfg):
    """(APK, OBB) to install: the APK of the newest finished build in <work>/builds, and the OBB of the newest
    build at or before it that made one (a fast build reuses the last full build's OBB)."""
    root = os.path.join(cfg["work"], "builds")
    names = sorted(n for n in (os.listdir(root) if os.path.isdir(root) else []) if BUILD_FOLDER.match(n))
    with_apk = [n for n in names if os.path.exists(os.path.join(root, n, APK_NAME))]
    if not with_apk:
        raise Problem("no build in %s: run 'python3 lunacid_vr.py build' first" % root)
    apk_dir = with_apk[-1]
    obbs = [n for n in names if n <= apk_dir and os.path.exists(os.path.join(root, n, OBB_NAME))]
    obb = os.path.join(root, obbs[-1], OBB_NAME) if obbs else None
    return os.path.join(root, apk_dir, APK_NAME), obb


def obb_stamp(obb):
    """Size and modification time, as tools/tour/quest_tour.sh writes them (stat -L -f '%z %m')."""
    st = os.stat(obb)
    return "%d %d" % (st.st_size, int(st.st_mtime))


def check_signature(cfg):
    """apk -> '' when this machine's key signed it, else why it must not be installed (tools/build/keystore.py)."""
    sys.path.insert(0, os.path.join(REPO, "tools", "build"))
    import keystore
    key = keystore.load(cfg)

    def check(apk):
        if not key:
            return "no signing key in %s" % keystore.folder(cfg)
        return keystore.signature_problem(keystore.apk_sha256(apk, cfg), keystore.fingerprint(key, cfg))
    return check


def push_obb(dev, obb, say=print):
    """Push the OBB only when the stamp on the headset differs; check its size before stamping it."""
    stamp = obb_stamp(obb)
    if dev.cat(OBB_DIR + "/.luna_stamp") == stamp:
        say("OBB unchanged on the Quest")
        return False
    dest = "%s/main.1.%s.obb" % (OBB_DIR, PKG)
    say("pushing the OBB (%d MB)..." % (os.path.getsize(obb) // (1024 * 1024)))
    dev.shell("mkdir -p %s" % _q(OBB_DIR))
    dev.push(obb, dest)
    got, want = dev.size(dest), os.path.getsize(obb)
    if got != want:
        raise Problem("the OBB on the Quest is %s bytes, the build's is %d: push it again" % (got, want))
    dev.shell("echo %s > %s" % (_q(stamp), _q(OBB_DIR + "/.luna_stamp")))
    return True


def install(cfg, dev, apk=None, obb=None, stamp=None, signature_check=None, say=print):
    """Backup, then the OBB (when it changed), then adb install -r, then check every save is still there.
    Never uninstalls: that deletes the saves."""
    if not apk:
        apk, obb = newest_build(cfg)
    problem = (signature_check or check_signature(cfg))(apk)
    if problem:
        raise Problem("%s: not installing %s" % (problem, apk))
    dev.require()
    folder = backup(cfg, dev, stamp=stamp)
    with open(os.path.join(folder, "backup.json"), encoding="utf-8") as fh:
        saved = json.load(fh)["saves"]
    say("backup: %d saves in %s" % (len(saved), folder))
    if obb:
        push_obb(dev, obb, say)
    say("installing %s..." % apk)
    rc, out = dev.run(["install", "-r", apk])
    if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:
        raise Problem(
            "the game on the Quest was built on another computer (signed by another key), so Android will not "
            "update it. Your saves are backed up in %s. To switch to this computer's build:\n"
            "  adb uninstall com.AkumaKira.LunacidVR      (deletes the game and its saves on the Quest)\n"
            "  python3 lunacid_vr.py install\n"
            "  open the game once on the Quest, quit\n"
            "  python3 lunacid_vr.py restore\n"
            "See 'Moving to another computer, or reinstalling' in the README." % folder)
    if rc != 0 or "Success" not in out:
        raise Problem("adb install -r failed: %s (the saves are in %s)" % (out.strip()[-300:], folder))
    now = {os.path.basename(p): s for p, s in dev.sizes(SAVES_DIR, ".MIDNIGHT").items()}
    missing = sorted(n for n in saved if n not in now)
    if missing:
        raise Problem("after the install the Quest no longer has %s: the backup is in %s"
                      % (", ".join(missing), folder))
    say("installed; %d saves still on the Quest" % len(now))
    return folder


def build_command(fast=False, skip_passes=False):
    cmd = [sys.executable, os.path.join(REPO, "tools", "build", "build.py")]
    if fast:
        cmd.append("--fast")
    if skip_passes:
        cmd.append("--skip-passes")
    return cmd


def build(fast=False, skip_passes=False, run=None):
    """Run tools/build/build.py; returns its exit code."""
    run = run or (lambda cmd: subprocess.call(cmd))
    return run(build_command(fast, skip_passes))


NEED_GB = 40   # game, Unity with Android, SDK, project, Library, builds (docs/RELEASE_PLAN.md, decision 6)


def steamcmd_command(profile):
    """The SteamCMD line for the supported version. The person types it and their own login; SteamCMD asks for
    the password and Steam Guard itself. This script never reads, receives or keeps credentials."""
    v = profile["game_versions"][0]
    return ("steamcmd +@sSteamCmdForcePlatformType windows +login <your Steam user> "
            "+download_depot %s %s %s +quit" % (profile["appid"], profile["steam_depot"], v["manifest"]))


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_game(game_data, profile):
    """The game's files against the supported versions' fingerprints (games/lunacid.json)."""
    get = ("\nGet the supported version with SteamCMD (you type your own login; SteamCMD asks for the rest):\n  %s\n"
           "then set game_data in local.json to .../steamapps/content/app_%s/depot_%s/LUNACID_Data"
           % (steamcmd_command(profile), profile["appid"], profile["steam_depot"]))
    if not game_data or not os.path.isdir(game_data):
        return "FAIL", "game files not found (game_data = %s)%s" % (game_data, get)
    for v in profile["game_versions"]:
        hashes = {}
        for rel in v["sha256"]:
            path = os.path.join(game_data, *rel.split("/"))
            hashes[rel] = _sha256(path) if os.path.exists(path) else None
        if hashes == v["sha256"]:
            return "OK", "Steam build %s (manifest %s)" % (v["steam_build"], v["manifest"])
    return "FAIL", "unknown game version in %s (not one the port was made for)%s" % (game_data, get)


def check_space(path, usage=None):
    usage = usage or shutil.disk_usage
    while path and not os.path.exists(path):
        path = os.path.dirname(path)
    free_gb = usage(path)[2] / 1024 ** 3
    if free_gb < NEED_GB:
        return "FAIL", "%.0f GB free on %s, about %d GB needed" % (free_gb, path, NEED_GB)
    return "OK", "%.0f GB free on %s" % (free_gb, path)


def parse_diskutil(text):
    """(file system, external) from `diskutil info`."""
    fs = re.search(r"File System Personality:\s*(.+)", text)
    location = re.search(r"Device Location:\s*(\w+)", text)
    protocol = re.search(r"Protocol:\s*(.+)", text)
    external = bool((location and location.group(1) == "External")
                    or (protocol and protocol.group(1).strip() in ("USB", "Thunderbolt")))
    return (fs.group(1).strip() if fs else "unknown"), external


def disk_status(fs, external):
    if "fat" in fs.lower():
        return "WARN", "%s disk: Unity is slow on it and it leaves ._ files; use an internal APFS or NTFS disk" % fs
    if external:
        return "WARN", "external disk (%s): a bumped cable dropped it mid-build three times here; prefer an internal disk" % fs
    return "OK", "%s, internal" % fs


def disk_info(path):
    """(file system, external) of the disk holding path, or None when it cannot be told."""
    while path and not os.path.exists(path):
        path = os.path.dirname(path)
    try:
        if sys.platform == "darwin":
            mount = subprocess.run(["df", "-P", path], capture_output=True, text=True).stdout.splitlines()[-1].split()[-1]
            return parse_diskutil(subprocess.run(["diskutil", "info", mount], capture_output=True, text=True).stdout)
        if os.name == "nt":
            import ctypes
            root = ctypes.create_unicode_buffer(260)
            ctypes.windll.kernel32.GetVolumePathNameW(path, root, 260)
            name = ctypes.create_unicode_buffer(260)
            ctypes.windll.kernel32.GetVolumeInformationW(root.value, None, 0, None, None, None, name, 260)
            return name.value or "unknown", ctypes.windll.kernel32.GetDriveTypeW(root.value) == 2  # DRIVE_REMOVABLE
    except (OSError, IndexError, AttributeError):
        pass
    return None


def check_keystore(cfg):
    """The signing key (tools/build/keystore.py) and whether a backup holds the same key."""
    key = os.path.join(cfg["work"], "keystore", "lunacid-vr.keystore")
    if not os.path.exists(key):
        return "WARN", "no signing key yet: the first build makes one in %s" % os.path.dirname(key)
    with open(key, "rb") as fh:
        data = fh.read()
    root = os.path.join(cfg["work"], "backups")
    for name in sorted(os.listdir(root) if os.path.isdir(root) else [], reverse=True):
        copy = os.path.join(root, name, "keystore", "lunacid-vr.keystore")
        if os.path.exists(copy):
            with open(copy, "rb") as fh:
                if fh.read() == data:
                    return "OK", "%s, backed up in %s (copy that folder off this machine too)" % (key, os.path.dirname(copy))
    return "WARN", ("%s has no backup: run 'python3 lunacid_vr.py backup'. Without the key, another computer "
                    "cannot update the installed port without uninstalling it, which deletes the saves" % key)


def check_unity(unity, android_player):
    from core import config
    if not unity or not os.path.exists(unity):
        return "FAIL", "Unity %s not found (%s): install it with Unity Hub, with Android Build Support" % (config.UNITY_VERSION, unity)
    if not android_player or not os.path.isdir(android_player):
        return "FAIL", "Unity has no Android module (%s): add Android Build Support in Unity Hub" % android_player
    return "OK", unity


def check_adb(cfg):
    adb = adb_path(cfg)
    if not adb:
        return "FAIL", "adb not found: install Unity's Android module (it brings the SDK) or set android_sdk"
    run = adb_runner(adb)
    try:
        serial = pick_serial(run)
    except Problem as e:
        return "WARN", "%s (%s)" % (adb, e)
    rc, out = Device(run, serial).run(["get-state"])
    return "OK", "%s (%s)" % (adb, "Quest connected" if rc == 0 and out.strip() == "device" else "no Quest connected now")


def exit_code(results):
    return 1 if any(status == "FAIL" for _, status, _ in results) else 0


def doctor(cfg, profile):
    from core import config
    results = [("Unity",) + check_unity(cfg["unity"], config._unity_android_player(cfg["unity"])),
               ("adb",) + check_adb(cfg),
               ("game",) + check_game(cfg.get("game_data"), profile),
               ("space",) + check_space(cfg["work"]),
               ("signing key",) + check_keystore(cfg)]
    seen = set()
    for label, path in (("work disk", cfg["work"]), ("project disk", cfg["project"])):
        info = disk_info(path)
        if info and (info, label) not in seen:
            seen.add((info, label))
            results.append((label,) + disk_status(*info))
    return results


def main(argv=None):
    import argparse
    from core import config, runner
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check this machine")
    b = sub.add_parser("build", help="build the APK (and the OBB on a full build)")
    b.add_argument("--fast", action="store_true", help="code only; reuses the last full build's assets")
    b.add_argument("--skip-passes", action="store_true")
    sub.add_parser("backup", help="copy the Quest's saves and the signing key")
    i = sub.add_parser("install", help="backup, then install the newest build (never uninstalls)")
    i.add_argument("--apk", help="install this APK instead of the newest build's")
    i.add_argument("--obb", help="with --apk: the OBB to push when it changed")
    r = sub.add_parser("restore", help="put a backup's saves back on the Quest (the newest backup with saves)")
    r.add_argument("folder", nargs="?", help="a <work>/backups/<date-time> folder")
    args = ap.parse_args(argv)
    cfg = config.load()
    try:
        if args.command == "doctor":
            results = doctor(cfg, runner.load_profile())
            for label, status, detail in results:
                print("%-4s %-13s %s" % (status, label, detail))
            return exit_code(results)
        if args.command == "build":
            return build(args.fast, args.skip_passes)
        adb = adb_path(cfg)
        if not adb:
            raise Problem("adb not found: run 'python3 lunacid_vr.py doctor'")
        run = adb_runner(adb)
        dev = Device(run, serial=pick_serial(run))
        if args.command == "backup":
            print("backup in %s" % backup(cfg, dev))
        elif args.command == "restore":
            restore(cfg, dev, folder=args.folder and os.path.abspath(os.path.expanduser(args.folder)))
        elif args.command == "install":
            install(cfg, dev, apk=args.apk, obb=args.obb)
        return 0
    except Problem as e:
        print("FAIL: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
