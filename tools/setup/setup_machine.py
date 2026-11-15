#!/usr/bin/env python3
"""
Get everything a build needs, for people who have never used these tools: `python3 lunacid_vr.py setup`.

What it fetches, each only when it is missing, into <work>/tools unless one is already there:
- Unity 6000.0.85f1 with Android Build Support and its children (OpenJDK, Android SDK & NDK), through the standalone
  Unity CLI 1.0.0 (pinned by Unity's SHA-256; Unity Hub 4 no longer runs `-- --headless install`). The exact version
  and changeset are pinned here, so nobody searches Unity's archive. Unity downloads in the background while the
  rest goes on. Unity Hub (winget on Windows) is still where the person signs in for the licence.
- SteamCMD from Valve, its first self-update (emptied and retried when it fails, as it did on Windows 11), then the
  supported game version. Only the Steam user name is asked here, and it only goes on SteamCMD's command line;
  the password and Steam Guard code are typed into SteamCMD itself.
- AssetRipper 2.0.0 from its GitHub release, checked against the SHA-256 GitHub publishes.
- The .NET 8 SDK with Microsoft's dotnet-install script, inside <work>/tools/dotnet (no administrator).
Then it writes local.json (dropping example text copied from local.example.json) and the caller runs doctor.
"""

import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

UNITY_VERSION = "6000.0.85f1"
UNITY_CHANGESET = "ee7790f1426a"

ASSETRIPPER_BASE = "https://github.com/AssetRipper/AssetRipper/releases/download/2.0.0/"
ASSETRIPPER_PINS = {   # SHA-256 published by GitHub for release 2.0.0 (read 2026-11-13)
    ("Windows", "x64"): ("AssetRipper_win_x64.zip", "9a7ef0e7c5c3ea5b90b4e6d855e2d98d5f7ec8c3f9e26fccbc194c6a7b01baf7"),
    ("Windows", "arm64"): ("AssetRipper_win_arm64.zip", "c2c3a335948aa0ecaf26baf22ac77e36993d1a1695b5db291cb63f66872627f1"),
    ("Darwin", "arm64"): ("AssetRipper_mac_arm64.tar.xz", "237a6da404bf089c5e5c71a5a9a698c2ea580872292dfa5ce21e25fd1dbe9045"),
    ("Darwin", "x64"): ("AssetRipper_mac_x64.tar.xz", "1b3836f135d16845cb57595fadff5739cbb86d28caaf621005b4301dba9b5a56"),
}
STEAMCMD_URL = {
    "Windows": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip",
    "Darwin": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz",
}
STEAMCMD_EXE = {"Windows": "steamcmd.exe", "Darwin": "steamcmd.sh"}
DOTNET_SCRIPT = {"Windows": "https://dot.net/v1/dotnet-install.ps1", "Darwin": "https://dot.net/v1/dotnet-install.sh"}
HUB = {"Windows": r"C:\Program Files\Unity Hub\Unity Hub.exe",
       "Darwin": "/Applications/Unity Hub.app/Contents/MacOS/Unity Hub"}
PLACEHOLDER = re.compile(r"^(leave out|path to)\b", re.I)


class Problem(Exception):
    """Something the person must do; printed without a traceback."""


def arch():
    return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"


# ---------- small helpers

MB = 1024 * 1024
LANG = "en"     # setup() sets it from the computer's language; the progress lines follow it
UNITY_TOTAL = 9 * 1024 * MB    # Unity 6000.0.85f1 with Android, OpenJDK and the SDK/NDK, roughly, installed


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.progress import time_left  # noqa: E402  (one estimate for every tool)


def progress_line(label, done, total, seconds=None, lang="en"):
    # Under 1 MB in KB: small files read "0 of 0 MB" (the notebook, 2026-11-13).
    unit, size = ("MB", MB) if max(done, total) >= MB else ("KB", 1024)
    if total:
        line = "%s: %d%% (%d of %d %s)" % (label, done * 100 // total, done // size, total // size, unit)
        left = time_left(float(done) / total, seconds, lang)
        return line + (", " + left if left else "")
    return "%s: %d %s" % (label, done // size, unit)


def _live(line, end=False):
    """One line that updates in place (core/progress.py)."""
    from core import progress
    progress.live(line, end)


def download(url, dest, label=None, say=None, lang=None):
    """Fetch url to dest (a temporary name first, so a cut download never looks finished), showing how far it is."""
    label = label or os.path.basename(dest)
    lang = lang or LANG
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "lunacid-vr-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(part, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done, shown, began = 0, -1, time.time()
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            step = done * 20 // total if total else done // (10 * MB)
            if step != shown:
                shown = step
                (say or _live)(progress_line(label, done, total, time.time() - began, lang))
    if say:
        say(progress_line(label, done, total or done, lang=lang))
    else:
        _live(progress_line(label, done, total or done, lang=lang), end=True)
    os.replace(part, dest)


def run(cmd, interactive=False):
    """(exit code, output). interactive: the program talks to the person in this terminal (SteamCMD's password)."""
    try:
        if interactive:
            return subprocess.call(cmd), ""
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        return res.returncode, res.stdout + res.stderr
    except OSError as e:     # a program that cannot start (missing, or Windows wants elevation) is an answer
        return 1, str(e)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack(archive, dest):
    os.makedirs(dest, exist_ok=True)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            if sys.version_info >= (3, 12):
                t.extractall(dest, filter="data")
            else:
                t.extractall(dest)


def find_file(folder, name):
    """The first file called name under folder, or None."""
    if not os.path.isdir(folder):
        return None
    for top, _, files in os.walk(folder):
        if name in files:
            return os.path.join(top, name)
    return None


def make_executable(path):
    if os.name != "nt":
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------- AssetRipper

def assetripper_asset(system, cpu, pins=None):
    pins = pins or ASSETRIPPER_PINS
    if (system, cpu) not in pins:
        raise Problem("no AssetRipper 2.0.0 download for %s %s" % (system, cpu))
    return pins[(system, cpu)]


def install_assetripper(tools, system, cpu, fetch=download, pins=None, say=print):
    exe_name = "AssetRipper.GUI.Free.exe" if system == "Windows" else "AssetRipper.GUI.Free"
    folder = os.path.join(tools, "AssetRipper")
    found = find_file(folder, exe_name)
    if found:
        return found
    name, digest = assetripper_asset(system, cpu, pins)
    archive = os.path.join(tools, "downloads", name)
    say("downloading AssetRipper 2.0.0 (%s)..." % name)
    fetch(ASSETRIPPER_BASE + name, archive)
    got = sha256(archive)
    if got != digest:
        os.remove(archive)
        raise Problem("the AssetRipper download is not the published file (SHA-256 %s, expected %s): try again "
                      "later" % (got[:16], digest[:16]))
    unpack(archive, folder)
    exe = find_file(folder, exe_name)
    if not exe:
        raise Problem("AssetRipper unpacked without %s in %s" % (exe_name, folder))
    make_executable(exe)
    if system == "Darwin":   # let macOS run a program downloaded by a script
        run(["xattr", "-dr", "com.apple.quarantine", folder])
    return exe


# ---------- SteamCMD

def _update_failed(out):
    return "Fatal Error" in out or "Failed to apply update" in out and "Update complete" not in out


def install_steamcmd(tools, system, fetch=download, runner=run, known=None, say=print):
    """SteamCMD's program, unpacked and updated. known: places it may already be (the guides used C:\\steamcmd)."""
    name = STEAMCMD_EXE[system]
    if known is None:
        known = [os.path.join("C:\\", "steamcmd", name)] if system == "Windows" else \
            [os.path.expanduser(os.path.join("~", "steamcmd", name))]
    exe = next((k for k in known if os.path.exists(k)), None)
    if not exe:
        folder = os.path.join(tools, "steamcmd")
        exe = os.path.join(folder, name)
        if not os.path.exists(exe):
            archive = os.path.join(tools, "downloads", os.path.basename(STEAMCMD_URL[system]))
            say("downloading SteamCMD (Valve's download tool)...")
            fetch(STEAMCMD_URL[system], archive)
            unpack(archive, folder)
            make_executable(exe)
    folder = os.path.dirname(exe)
    say("letting SteamCMD update itself (the first time it downloads about 40 MB)...")
    for attempt in (1, 2):
        rc, out = runner([exe, "+quit"])
        if not _update_failed(out):
            return exe
        if attempt == 1:
            say("SteamCMD's update failed; emptying its folder and trying again...")
            for entry in os.listdir(folder):
                if entry != name:
                    path = os.path.join(folder, entry)
                    shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
    hint = ("Close this window, open PowerShell as administrator (Windows key, type PowerShell, right click, Run as "
            "administrator) and run setup again from there." if system == "Windows" else
            "Run setup again; if it keeps failing, send the last lines of %s" % os.path.join(folder, "logs",
                                                                                              "bootstrap_log.txt"))
    raise Problem("SteamCMD could not update itself (\"Failed to load steam.dll\"). " + hint)


# ---------- the game

def fingerprint_ok(game_data, profile):
    for v in profile["game_versions"]:
        ok = True
        for rel, digest in v["sha256"].items():
            path = os.path.join(game_data, *rel.split("/"))
            if not os.path.exists(path) or sha256(path) != digest:
                ok = False
                break
        if ok:
            return v
    return None


def depot_candidates(steamcmd, profile):
    """Where SteamCMD leaves the depot: beside it on Windows; on a Mac also in Steam's Application Support."""
    tail = os.path.join("steamapps", "content", "app_%s" % profile["appid"], "depot_%s" % profile["steam_depot"],
                        "LUNACID_Data")
    places = [os.path.join(os.path.dirname(steamcmd), tail)] if steamcmd else []
    places.append(os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Steam", tail))
    return places


def get_game(profile, steamcmd, runner=run, ask=input, candidates=None, say=print, download=True):
    """The game's LUNACID_Data folder at the supported version: one already there, or downloaded with SteamCMD."""
    seen = []
    for data in (candidates or []) + depot_candidates(steamcmd, profile):
        if data and os.path.isdir(data):
            v = fingerprint_ok(data, profile)
            if v:
                say("game files found: %s (Steam build %s)" % (data, v["steam_build"]))
                return data
            seen.append(data)
    if not download:
        raise Problem("the game files in %s are not the version the port was made for" % ", ".join(seen))
    v = profile["game_versions"][0]
    say("\nNow the game files, with your own Steam account (Lunacid must be on it).")
    say("This program never sees your password: SteamCMD, Valve's program, asks for it below.")
    user = ""
    while not user:
        user = ask("Your Steam user name (not your e-mail): ").strip()
    say("SteamCMD will ask for your password (nothing shows while you type) and your Steam Guard code.")
    rc, _ = runner([steamcmd, "+@sSteamCmdForcePlatformType", "windows", "+login", user, "+download_depot",
                    str(profile["appid"]), str(profile["steam_depot"]), v["manifest"], "+quit"], interactive=True)
    for data in depot_candidates(steamcmd, profile):
        if os.path.isdir(data) and fingerprint_ok(data, profile):
            return data
    raise Problem("SteamCMD did not leave the game files where expected (exit code %s). If the password or code "
                  "was wrong, run setup again." % rc)


# ---------- .NET 8

def install_dotnet(tools, system, fetch=download, runner=run, which=shutil.which, say=print):
    target = os.path.join(tools, "dotnet")
    local = os.path.join(target, "dotnet.exe" if system == "Windows" else "dotnet")
    if os.path.exists(local):
        return local
    on_path = which("dotnet")
    if on_path:
        rc, out = runner([on_path, "--list-sdks"])
        if rc == 0 and any(line.strip().startswith("8.") for line in out.splitlines()):
            return on_path
    say("installing the .NET 8 SDK into %s (Microsoft's script, no administrator)..." % target)
    script = os.path.join(tools, "downloads", os.path.basename(DOTNET_SCRIPT[system]))
    fetch(DOTNET_SCRIPT[system], script)
    if system == "Windows":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
               "-Channel", "8.0", "-InstallDir", target]
    else:
        cmd = ["bash", script, "--channel", "8.0", "--install-dir", target]
    rc, out = runner(cmd)
    if not os.path.exists(local):
        raise Problem("the .NET 8 SDK did not install (exit code %s): %s" % (rc, out.strip()[-300:]))
    return local


# ---------- Unity

def folder_size(path):
    total = 0
    for top, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(top, f))
            except OSError:
                pass
    return total


def unity_progress(log, editor, minutes, total=UNITY_TOTAL, lang="en"):
    """How far Unity's install is: Unity Hub's own percentage when its output has one, else what is installed so far
    against the usual size (never 100% before it is done)."""
    if log and os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as fh:
            found = re.findall(r"(\d{1,3})(?:\.\d+)?\s*%", fh.read()[-4000:])
        if found:
            pct = min(99, int(found[-1]))
            left = time_left(pct / 100.0, minutes * 60, lang)
            return "Unity: %d%%%s" % (pct, ", " + left if left else "")
    size = folder_size(editor) if editor and os.path.isdir(editor) else 0
    # Past the usual size (Windows with Android passes 12 GB against the Mac's 9) an estimate is wrong: say what is
    # there and how long it has been (the notebook, 2026-11-13: "12.1 GB of about 9 GB (99%)").
    if total and size > total:
        return "Unity: %.1f GB installed so far, still going (%d min)" % (size / 1024.0 / MB, minutes)
    pct = min(99, size * 100 // total) if total else 0
    left = time_left(pct / 100.0, minutes * 60, lang)
    gb = "%.1f GB of about %.0f GB" % (size / 1024.0 / MB, total / 1024.0 / MB)
    return "Unity: %s (%d%%), %s" % (gb, pct, left or ("%d min" % minutes))


def editor_folder(unity, system):
    """...\\6000.0.85f1\\Editor\\Unity.exe or .../6000.0.85f1/Unity.app/Contents/MacOS/Unity -> the 6000.0.85f1 folder."""
    if not unity:
        return None
    up = 2 if system == "Windows" else 4
    for _ in range(up):
        unity = os.path.dirname(unity)
    return unity


def unity_command(cli, editor, android, system=None, cpu=None):
    """The Unity CLI command that gets 6000.0.85f1 with Android and its children, or None when present.
    Unity Hub 4.0.0 (2026-11-13) no longer runs `-- --headless install`; the standalone Unity CLI does. On a Mac
    the architecture is named: without it Hub 3.22.5 asked "Please select preferred architecture" in a log nobody
    read and waited for ever (Verho port, 2026-11-14)."""
    if editor and android:
        return None
    system = system or platform.system()
    cpu = cpu or arch()
    if editor:
        return [cli, "install-modules", "-e", UNITY_VERSION, "-m", "android", "--cm", "--accept-eula"]
    cmd = [cli, "install", UNITY_VERSION, "-c", UNITY_CHANGESET, "-m", "android", "--cm", "--accept-eula"]
    if system == "Darwin":
        cmd += ["-a", "arm64" if cpu == "arm64" else "x86_64"]
    return cmd


# Android's tools (SDK, NDK, CMake) come with Google's licence; the Unity CLI wants it accepted (--accept-eula) and
# stopped with exit code 6 without it (GitHub's clean machines, 2026-11-15). The old Hub accepted it silently; now
# the person is told first, here and in the README (Felipe, 2026-11-15).
LICENCE_NOTICE = ("Unity's Android module installs Google's Android SDK, NDK and CMake. By going on you accept their "
                  "licence terms: https://developer.android.com/studio/terms")


def cli_error(log):
    """The Unity CLI's own error line (it writes 'Error: ...'), or ''."""
    if not (log and os.path.exists(log)):
        return ""
    with open(log, encoding="utf-8", errors="replace") as fh:
        lines = [line.strip() for line in fh if line.strip()]
    errors = [line for line in lines if line.lower().startswith("error")]
    return errors[-1] if errors else (lines[-1] if lines else "")


def start_unity(cmd, log, popen=subprocess.Popen):
    """Run the install in the background, its output in log. No keyboard: a question fails at once instead of
    waiting where nobody sees it."""
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "w") as fh:
        return popen(cmd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT)


# The standalone Unity CLI, pinned to Unity's manifest for 1.0.0
# (https://public-cdn.cloud.unity3d.com/hub/prod/cli/1.0.0/latest.json, read 2026-11-14).
UNITY_CLI_VERSION = "1.0.0"
UNITY_CLI_BASE = "https://public-cdn.cloud.unity3d.com/hub/prod/cli/%s/" % UNITY_CLI_VERSION
UNITY_CLI_PINS = {
    ("Darwin", "arm64"): ("unity-darwin-arm64", "de6cb46c1ac1871d524965ed2ed5f14e1eb13b4fc25210a209a55c0b1154014f"),
    ("Darwin", "x64"): ("unity-darwin-x64", "2ce9f3cbdc537e4468f178382749508eca7c611cf4b304cc23395c63321a7d96"),
    ("Windows", "x64"): ("unity-windows-x64.exe", "1bca103f1daa94534e0232474b6b7e18f1c132d8a5868e20c71a649e92507c73"),
    ("Windows", "arm64"): ("unity-windows-arm64.exe", "3d9afe83c78d1de0a81e7c856f29a5663e89a1a426418cd3af97571e483263f1"),
}


def unity_cli_asset(system, cpu, pins=None):
    pins = pins or UNITY_CLI_PINS
    if (system, cpu) not in pins:
        raise Problem("no Unity CLI %s download for %s %s" % (UNITY_CLI_VERSION, system, cpu))
    return pins[(system, cpu)]


def install_unity_cli(tools, system, cpu, fetch=download, pins=None, say=print, runner=None):
    """<tools>/unity-cli/unity(.exe): Unity's own command line program, checked against Unity's SHA-256."""
    folder = os.path.join(tools, "unity-cli")
    exe = os.path.join(folder, "unity.exe" if system == "Windows" else "unity")
    if os.path.exists(exe):
        return exe
    name, digest = unity_cli_asset(system, cpu, pins)
    part = os.path.join(tools, "downloads", name)
    say("downloading the Unity CLI %s (%s)..." % (UNITY_CLI_VERSION, name))
    fetch(UNITY_CLI_BASE + name, part)
    got = sha256(part)
    if got != digest:
        os.remove(part)
        raise Problem("the Unity CLI download is not Unity's published file (SHA-256 %s, expected %s): try again "
                      "later" % (got[:16], digest[:16]))
    os.makedirs(folder, exist_ok=True)
    shutil.move(part, exe)
    make_executable(exe)
    if system == "Darwin":   # let macOS run a program downloaded by a script
        (runner or run)(["xattr", "-d", "com.apple.quarantine", exe])
    return exe


def find_installed_editor(cli, system, runner=run):
    """Where the CLI put 6000.0.85f1, when not at the Hub's usual place: `unity install-path` names the folder."""
    rc, out = runner([cli, "install-path"])
    if rc != 0:
        return None
    for line in out.splitlines():
        folder = line.strip().strip('"')
        if not folder or not os.path.isdir(folder):
            continue
        if system == "Windows":
            exe = os.path.join(folder, UNITY_VERSION, "Editor", "Unity.exe")
        else:
            exe = os.path.join(folder, UNITY_VERSION, "Unity.app", "Contents", "MacOS", "Unity")
        if os.path.exists(exe):
            return exe
    return None


HUB_INSTALLER = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup-%s.%s"   # x64 / arm64; exe / dmg


def hub_candidates(system):
    """Where Unity Hub may be: its default place, and on Windows a per-user install."""
    places = [HUB[system]]
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            places.append(os.path.join(local, "Programs", "Unity Hub", "Unity Hub.exe"))
    return places


def ensure_hub(system, runner=run, exists=os.path.exists, which=shutil.which, say=print, fetch=download,
               cpu=None, tools=None, candidates=None):
    """Unity Hub's program, installed when missing: winget on Windows (else Unity's own installer, silent, with the
    permission prompt), Unity's disk image on a Mac (copied to Applications)."""
    candidates = candidates or hub_candidates(system)
    hub = next((c for c in candidates if exists(c)), None)
    if hub:
        return hub
    hub = HUB[system]
    cpu = cpu or arch()
    tools = tools or os.path.join(os.path.expanduser("~"), "lunacid-work", "tools")
    out = ""
    if system == "Windows":
        if which("winget"):
            say("installing Unity Hub (winget; Windows may ask for permission)...")
            rc, out = runner(["winget", "install", "--id", "Unity.UnityHub", "-e", "--accept-source-agreements",
                              "--accept-package-agreements"])
            # winget may install it for this user only (AppData\Local\Programs): every place counts.
            found = next((c for c in candidates if exists(c)), None)
            if found:
                return found
            say("winget did not install it: %s" % (out.strip().splitlines() or ["no output"])[-1])
        if not exists(hub):
            installer = os.path.join(tools, "downloads", "UnityHubSetup-%s.exe" % cpu)
            say("installing Unity Hub (Unity's installer): Windows asks for permission, choose Yes...")
            fetch(HUB_INSTALLER % (cpu, "exe"), installer)
            # It installs for every user, so it needs elevation ([WinError 740] when started directly).
            rc, out = runner(["powershell", "-NoProfile", "-Command",
                              "Start-Process -FilePath '%s' -ArgumentList '/S' -Verb RunAs -Wait" % installer])
    else:
        dmg = os.path.join(tools, "downloads", "UnityHubSetup-%s.dmg" % cpu)
        say("installing Unity Hub (Unity's disk image)...")
        fetch(HUB_INSTALLER % (cpu, "dmg"), dmg)
        rc, out = runner(["hdiutil", "attach", "-nobrowse", dmg])
        volume = next((line.split("\t")[-1].strip() for line in out.splitlines() if "/Volumes/" in line), None)
        if volume:
            runner(["cp", "-R", volume + "/Unity Hub.app", "/Applications/"])   # a Mac path, whatever runs this
            runner(["hdiutil", "detach", volume])
    if exists(hub):
        return hub
    raise Problem("Unity Hub did not install (%s). Install it from https://unity.com/download, then run setup "
                  "again." % (out.strip()[-200:] or "no output"))


def sign_in(home, system, hub, ask=input, launch=None, say=print, check=None, sleep=None, clock=None, limit=1200):
    """Unity builds only with a licence, which Unity Hub writes when the person signs in. Ask for it now, at the
    start, instead of letting the build fail an hour later. Setup watches for the licence and goes on by itself: a
    "press Enter" here sat unseen under the Hub's log on the notebook (2026-11-13). `ask` is kept for callers."""
    import time
    check = check or check_licence
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    if check(home, system)[0] == "OK":
        return True
    # The Hub writes its own log lines; they stay out of the person's window.
    launch = launch or (lambda path: subprocess.Popen([path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                      stderr=subprocess.DEVNULL))
    say("\nUnity Hub is opening (it may open behind this window). Sign in there, or make a free Unity account,")
    say("and if it asks, choose the free Personal licence. Nothing to press here: this goes on by itself.")
    launch(hub)
    start = clock()
    reminded = start
    while clock() - start < limit:
        sleep(3)
        if check(home, system)[0] == "OK":
            say("Signed in to Unity: going on.")
            return True
        if clock() - reminded >= 120:
            reminded = clock()
            say("Still waiting for the Unity Hub sign-in (look for its window in the taskbar)...")
    say("No Unity licence after %d minutes; setup goes on, and doctor will remind you before the build." % (limit // 60))
    return False


def check_licence(home, system):
    """Unity needs a licence to build; Hub writes one when the person signs in."""
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        path = os.path.join(base, "Unity", "licenses", "UnityEntitlementLicense.xml")
    else:
        path = os.path.join(home, "Library", "Unity", "licenses", "UnityEntitlementLicense.xml")
    if os.path.exists(path):
        return "OK", path
    return "WARN", ("no Unity licence yet: open Unity Hub, sign in (a free account is enough) and choose the "
                    "Personal licence; the build needs it")


# ---------- local.json

def update_local(path, found):
    """Write the found paths into local.json; drop example text copied from local.example.json; keep the rest."""
    current = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            try:
                current = json.load(fh)
            except ValueError:
                raise Problem("%s is not valid JSON: fix it or delete it, then run setup again" % path)
    current = {k: v for k, v in current.items() if not (isinstance(v, str) and PLACEHOLDER.match(v))}
    def same(a, b):
        return os.path.abspath(os.path.expanduser(a)) == os.path.abspath(os.path.expanduser(b))
    for k, v in found.items():
        if v and not (isinstance(current.get(k), str) and same(current[k], v)):
            current[k] = v
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(current, fh, indent=2)
        fh.write("\n")
    return current


# ---------- all of it

def setup(cfg, profile, local_path, system=None, cpu=None, say=print, ask=input, lang="en"):
    global LANG
    LANG = lang
    system = system or platform.system()
    cpu = cpu or arch()
    if system not in ("Windows", "Darwin"):
        raise Problem("setup knows Windows and macOS; on %s install the tools by hand (README)" % system)
    tools = os.path.join(cfg["work"], "tools")
    os.makedirs(tools, exist_ok=True)
    say("Lunacid VR setup: everything goes into %s\n" % cfg["work"])

    # Unity first, in the background: it is the longest download.
    unity_proc = None
    unity_ok = cfg.get("unity") and os.path.exists(cfg["unity"])
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core import config
    player = config._unity_android_player(cfg.get("unity"))
    cmd = None
    cli = None
    if not (unity_ok and player and os.path.isdir(player)):
        cli = install_unity_cli(tools, system, cpu, say=say)
        cmd = unity_command(cli, editor=bool(unity_ok), android=False, system=system, cpu=cpu)
    # The Hub is still where a person signs in to Unity (the licence the build needs).
    if check_licence(os.path.expanduser("~"), system)[0] != "OK":
        hub = ensure_hub(system, say=say, cpu=cpu, tools=tools)
        sign_in(os.path.expanduser("~"), system, hub, ask=ask, say=say)
    if cmd:
        log = os.path.join(cfg["work"], "logs", "unity_install.log")
        say(LICENCE_NOTICE)
        say("Unity %s with Android is downloading in the background (about 9 GB; log: %s)" % (UNITY_VERSION, log))
        unity_proc = start_unity(cmd, log)
    else:
        say("Unity %s with Android: already installed" % UNITY_VERSION)

    found = {}
    if cfg.get("assetripper") and os.path.exists(cfg["assetripper"]):
        found["assetripper"] = cfg["assetripper"]
    else:
        found["assetripper"] = install_assetripper(tools, system, cpu, say=say)
    say("AssetRipper: %s" % found["assetripper"])
    if cfg.get("dotnet") and os.path.exists(cfg["dotnet"]):
        dotnet = cfg["dotnet"]
    else:
        dotnet = install_dotnet(tools, system, say=say)
    found["dotnet"] = None if os.path.dirname(dotnet) == "" else dotnet
    say(".NET 8 SDK: %s" % dotnet)
    game = cfg.get("game_data")
    if not (game and os.path.isdir(game) and fingerprint_ok(game, profile)):
        steamcmd = install_steamcmd(tools, system, say=say)
        game = get_game(profile, steamcmd, ask=ask, candidates=[game] if game else [], say=say)
    found["game_data"] = game
    update_local(local_path, found)
    say("local.json written: %s" % local_path)

    if unity_proc:
        say("\nwaiting for Unity to finish downloading and installing...")
        unity = wait_for_unity(unity_proc, cli, cfg.get("unity"), log, system, lang=lang)
        if unity != cfg.get("unity"):
            found["unity"] = unity
            update_local(local_path, found)
            say("Unity: %s" % unity)
    return found


def wait_for_unity(proc, cli, unity, log, system, lang="en", sleep=None, clock=None, finder=None):
    """Wait for the install, with a live line; the editor's path (where setup looks, or where the CLI put it)."""
    sleep = sleep or time.sleep
    clock = clock or time.time
    finder = finder or find_installed_editor
    began = clock()
    editor = editor_folder(unity, system)
    while proc.poll() is None:
        sleep(15)
        _live(unity_progress(log, editor, int((clock() - began) / 60), lang=lang))
    _live("Unity: done", end=True)
    if proc.returncode != 0:
        said = cli_error(log)
        raise Problem("the Unity CLI could not install Unity %s (exit code %s)%s. Its log: %s. Run setup again; if it "
                      "says the same, open an issue with that log." % (UNITY_VERSION, proc.returncode,
                                                                       ": " + said if said else "", log))
    if unity and os.path.exists(unity):
        return unity
    elsewhere = finder(cli, system)
    if not elsewhere:
        raise Problem("the Unity CLI finished but Unity %s is not where setup looks (%s): see %s"
                      % (UNITY_VERSION, unity, log))
    return elsewhere


def install_unity_only(work, system=None, cpu=None, say=print, popen=subprocess.Popen, fetch=download,
                       sleep=None, finder=None):
    """Only Unity with Android, as setup does it, then checked: the clean-Mac check on GitHub runs this
    (.github/workflows/unity-install.yml), so a change by Unity (Hub 4, 2026-11-13) is seen before a person meets it.
    No sign-in, no game: those need a person."""
    system = system or platform.system()
    cpu = cpu or arch()
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core import config
    tools = os.path.join(work, "tools")
    cli = install_unity_cli(tools, system, cpu, fetch=fetch, say=say)
    unity = config._unity_default()
    cmd = unity_command(cli, editor=os.path.exists(unity), android=False, system=system, cpu=cpu)
    say(LICENCE_NOTICE)
    say("running: %s" % " ".join(cmd))
    log = os.path.join(work, "logs", "unity_install.log")
    proc = start_unity(cmd, log, popen=popen)
    try:
        unity = wait_for_unity(proc, cli, unity, log, system, sleep=sleep, finder=finder)
    finally:
        if os.path.exists(log):
            with open(log, encoding="utf-8", errors="replace") as fh:
                say("--- the Unity CLI said (last lines):\n" + "".join(fh.readlines()[-40:]))
    player = config._unity_android_player(unity)
    if not (player and os.path.isdir(player)):
        raise Problem("Unity %s is installed (%s) but without the Android module" % (UNITY_VERSION, unity))
    say("OK: Unity %s at %s, Android at %s" % (UNITY_VERSION, unity, player))
    return unity


if __name__ == "__main__":
    # python3 tools/setup/setup_machine.py --unity-only <work folder>
    if len(sys.argv) == 3 and sys.argv[1] == "--unity-only":
        try:
            install_unity_only(os.path.abspath(sys.argv[2]))
        except Problem as e:
            sys.exit("FAIL: %s" % e)
    else:
        sys.exit("usage: setup_machine.py --unity-only <work folder>")
