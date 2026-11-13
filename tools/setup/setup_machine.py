#!/usr/bin/env python3
"""
Get everything a build needs, for people who have never used these tools: `python3 lunacid_vr.py setup`.

What it fetches, each only when it is missing, into <work>/tools unless one is already there:
- Unity 6000.0.85f1 with Android Build Support and its children (OpenJDK, Android SDK & NDK), through Unity Hub's
  command line (Hub itself through winget on Windows). The exact version and changeset are pinned here, so nobody
  searches Unity's archive. Unity downloads in the background while the rest goes on.
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

def download(url, dest):
    """Fetch url to dest (a temporary name first, so a cut download never looks finished)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "lunacid-vr-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(part, "wb") as fh:
        shutil.copyfileobj(resp, fh, 1 << 20)
    os.replace(part, dest)


def run(cmd, interactive=False):
    """(exit code, output). interactive: the program talks to the person in this terminal (SteamCMD's password)."""
    if interactive:
        return subprocess.call(cmd), ""
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return res.returncode, res.stdout + res.stderr


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

def unity_command(hub, editor, android):
    """The Unity Hub command line that gets 6000.0.85f1 with Android and its children, or None when present."""
    if editor and android:
        return None
    base = [hub, "--", "--headless"]
    if not editor:
        return base + ["install", "--version", UNITY_VERSION, "--changeset", UNITY_CHANGESET,
                       "--module", "android", "--childModules"]
    return base + ["install-modules", "--version", UNITY_VERSION, "--module", "android", "--childModules"]


HUB_INSTALLER = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup-%s.%s"   # x64 / arm64; exe / dmg


def ensure_hub(system, runner=run, exists=os.path.exists, which=shutil.which, say=print, fetch=download,
               cpu=None, tools=None):
    """Unity Hub's program, installed when missing: winget on Windows (else Unity's own installer, silent), Unity's
    disk image on a Mac (copied to Applications)."""
    hub = HUB[system]
    if exists(hub):
        return hub
    cpu = cpu or arch()
    tools = tools or os.path.join(os.path.expanduser("~"), "lunacid-work", "tools")
    out = ""
    if system == "Windows":
        if which("winget"):
            say("installing Unity Hub (winget; Windows may ask for permission)...")
            rc, out = runner(["winget", "install", "--id", "Unity.UnityHub", "-e", "--accept-source-agreements",
                              "--accept-package-agreements"])
        if not exists(hub):
            installer = os.path.join(tools, "downloads", "UnityHubSetup-%s.exe" % cpu)
            say("installing Unity Hub (Unity's installer; Windows may ask for permission)...")
            fetch(HUB_INSTALLER % (cpu, "exe"), installer)
            rc, out = runner([installer, "/S"])
    else:
        dmg = os.path.join(tools, "downloads", "UnityHubSetup-%s.dmg" % cpu)
        say("installing Unity Hub (Unity's disk image)...")
        fetch(HUB_INSTALLER % (cpu, "dmg"), dmg)
        rc, out = runner(["hdiutil", "attach", "-nobrowse", dmg])
        volume = next((line.split("\t")[-1].strip() for line in out.splitlines() if "/Volumes/" in line), None)
        if volume:
            runner(["cp", "-R", os.path.join(volume, "Unity Hub.app"), "/Applications/"])
            runner(["hdiutil", "detach", volume])
    if exists(hub):
        return hub
    raise Problem("Unity Hub did not install (%s). Install it from https://unity.com/download, then run setup "
                  "again." % (out.strip()[-200:] or "no output"))


def sign_in(home, system, hub, ask=input, launch=None, say=print, check=None):
    """Unity builds only with a licence, which Unity Hub writes when the person signs in. Ask for it now, at the
    start, instead of letting the build fail an hour later."""
    check = check or check_licence
    if check(home, system)[0] == "OK":
        return True
    launch = launch or (lambda path: subprocess.Popen([path]))
    say("\nUnity Hub is opening. Sign in there (make a free Unity account if you have none) and, if it asks,")
    say("choose the free Personal licence.")
    launch(hub)
    ask("When you have signed in to Unity Hub, press Enter here to continue...")
    if check(home, system)[0] == "OK":
        return True
    say("No Unity licence found yet; setup goes on, and doctor will remind you before the build.")
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

def setup(cfg, profile, local_path, system=None, cpu=None, say=print, ask=input):
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
    hub = None
    if not (unity_ok and player and os.path.isdir(player)):
        hub = ensure_hub(system, say=say, cpu=cpu, tools=tools)
        cmd = unity_command(hub, editor=bool(unity_ok), android=False)
    if check_licence(os.path.expanduser("~"), system)[0] != "OK":
        hub = hub or ensure_hub(system, say=say, cpu=cpu, tools=tools)
        sign_in(os.path.expanduser("~"), system, hub, ask=ask, say=say)
    if cmd:
        log = os.path.join(cfg["work"], "logs", "unity_install.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        say("Unity %s with Android is downloading in the background (about 9 GB; log: %s)" % (UNITY_VERSION, log))
        with open(log, "w") as fh:
            unity_proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
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
        while unity_proc.poll() is None:
            time.sleep(30)
            say("  still installing Unity...")
        if unity_proc.returncode != 0:
            raise Problem("Unity Hub could not install Unity %s (exit code %s): see %s. Open Unity Hub, sign in, and "
                          "run setup again." % (UNITY_VERSION, unity_proc.returncode, log))
    return found
