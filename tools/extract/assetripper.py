#!/usr/bin/env python3
"""
Extract the game into a Unity project with AssetRipper 2.0.0, headless, with the settings the port needs.

    python3 tools/extract/assetripper.py --out <folder>          # exports <folder>/ExportedProject
    python3 tools/extract/assetripper.py --out <folder> --check  # only checks an existing export

The game folder is the machine configuration's game_data (core/config.py); AssetRipper's executable is the
configuration's "assetripper", or --assetripper. AssetRipper runs on 127.0.0.1 only and is driven over its
local web API: settings (POST /Settings/Update), the game (POST /LoadFolder), the export
(POST /Export/UnityProject). The end of an export is "Finished post-export" in AssetRipper's own log.

The settings are those of the export the port was made on (2026-10-27): lightmaps as EXR (PNG crashes on the
lightmaps) and decompiled scripts are required (docs/EXTRACTION_GUIDE.md); the rest keeps the export the
same as the one every pass was written against.
"""

import argparse
import glob
import re
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from core import config, runner  # noqa: E402

VERSION = "2.0.0"
SETTINGS = {
    "ScriptContentLevel": "Level2",
    "ScriptExportMode": "Hybrid",
    "ScriptLanguageVersion": "AutoSafe",
    "LightmapTextureExportFormat": "Exr",
    "ImageExportFormat": "Png",
    "ShaderExportMode": "Dummy",
    "SpriteExportMode": "Yaml",
    "TextExportMode": "Parse",
    "AudioExportFormat": "Default",
    "BundledAssetsExportMode": "DirectExport",
    "DefaultVersion": "0.0.0a0",
    "TargetVersion": "0.0.0a0",
    "EnablePrefabOutlining": "false",
    "EnableStaticMeshSeparation": "false",
    "EnableAssetDeduplication": "false",
    "ExportUnreadableAssets": "false",
    "PreferOriginalTextureExtension": "false",
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post(base, path, fields, timeout=600):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def form_fields(settings):
    """The form for /Settings/Update. AssetRipper reads a boolean like an HTML checkbox: the key present means on,
    whatever the value, so an off setting must be left out (LESSONS 31)."""
    return {k: v for k, v in settings.items() if v != "false"}


def wrong_settings(log_text, settings):
    """Settings whose value in AssetRipper's 'Configuration Settings' dump differs from the one asked for."""
    wrong = []
    for key, value in settings.items():
        m = re.search(r"^General : %s: (.*)$" % re.escape(key), log_text, re.M)
        if m and m.group(1).strip().lower() != value.lower():
            wrong.append(key)
    return wrong


def wait_line(log, text, proc, limit_s, start_size=0):
    end = time.time() + limit_s
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError("AssetRipper exited (code %s)" % proc.returncode)
        if os.path.exists(log):
            with open(log, encoding="utf-8", errors="ignore") as fh:
                fh.seek(start_size)
                if text in fh.read():
                    return
        time.sleep(3)
    raise TimeoutError("no %r in %s after %d min" % (text, log, limit_s // 60))


def check_export(project, profile):
    """Problems in an exported project: missing scenes, lightmaps, scripts."""
    problems = []
    assets = os.path.join(project, "Assets")
    if not os.path.isdir(assets):
        return ["no Assets folder in %s" % project]
    for scene in profile.get("scenes", []):
        if not os.path.exists(os.path.join(project, scene)):
            problems.append("scene missing: " + scene)
    # Only these scenes have baked lightmaps in the whole game (games/lunacid.json, lightmap_scenes).
    for scene in profile.get("lightmap_scenes", []):
        if not glob.glob(os.path.join(assets, "Scenes", scene, "Lightmap-*_comp_light.exr")):
            problems.append("no lightmap EXR for %s (LightmapTextureExportFormat must be Exr)" % scene)
    cs = glob.glob(os.path.join(assets, "Scripts", "Assembly-CSharp", "*.cs"))
    if len(cs) < 100:
        problems.append("only %d decompiled scripts in Assets/Scripts/Assembly-CSharp" % len(cs))
    return problems


def export(assetripper, game, out, limit_min=180):
    if os.path.exists(os.path.join(out, "ExportedProject")):
        sys.exit("%s already holds an ExportedProject: choose an empty folder" % out)
    os.makedirs(out, exist_ok=True)
    port = free_port()
    ar_dir = os.path.dirname(assetripper)
    before = set(glob.glob(os.path.join(ar_dir, "AssetRipper_*.log")))
    # Never a pipe: AssetRipper prints a line per asset, and a pipe nobody reads fills at 64 KB and stops the
    # export for good (LESSONS 31). Its own log file is read for progress instead.
    console = open(os.path.join(out, "assetripper_console.log"), "w")
    try:
        proc = subprocess.Popen([assetripper, "--headless", "--port", str(port)], cwd=ar_dir,
                                stdout=console, stderr=subprocess.STDOUT)
    except BaseException:
        console.close()
        raise
    base = "http://127.0.0.1:%d" % port
    try:
        end = time.time() + 120
        while time.time() < end:
            try:
                urllib.request.urlopen(base + "/", timeout=5)
                break
            except OSError:
                time.sleep(2)
        else:
            raise TimeoutError("AssetRipper did not answer on %s" % base)
        logs = sorted(set(glob.glob(os.path.join(ar_dir, "AssetRipper_*.log"))) - before)
        log = logs[-1] if logs else None
        print("AssetRipper %s on %s, log %s" % (VERSION, base, log))
        post(base, "/Settings/Update", form_fields(SETTINGS))
        print("== loading", game)
        post(base, "/LoadFolder", {"path": game}, timeout=7200)
        if log:
            # AssetRipper writes its settings to the log when it loads the game: stop before a wrong export.
            with open(log, encoding="utf-8", errors="ignore") as fh:
                wrong = wrong_settings(fh.read(), SETTINGS)
            if wrong:
                raise RuntimeError("AssetRipper did not take these settings: " + ", ".join(wrong))
        print("== exporting to", out)
        size = os.path.getsize(log) if log and os.path.exists(log) else 0
        post(base, "/Export/UnityProject", {"path": out}, timeout=limit_min * 60)
        if log:
            wait_line(log, "Finished post-export", proc, limit_min * 60, size)
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
        console.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="empty folder; the project lands in <out>/ExportedProject")
    ap.add_argument("--assetripper", help="AssetRipper.GUI.Free executable (default: configuration 'assetripper')")
    ap.add_argument("--check", action="store_true", help="only check an existing export")
    args = ap.parse_args()
    cfg = config.load()
    profile = runner.load_profile()
    out = os.path.abspath(os.path.expanduser(args.out))
    if not args.check:
        ar = args.assetripper or cfg.get("assetripper")
        if not ar or not os.path.exists(ar):
            sys.exit("AssetRipper %s not found: set 'assetripper' in local.json or pass --assetripper" % VERSION)
        if not cfg.get("game_data") or not os.path.isdir(cfg["game_data"]):
            sys.exit("the game's LUNACID_Data folder is not set or not found (game_data in local.json)")
        start = time.time()
        export(os.path.abspath(ar), os.path.dirname(cfg["game_data"]), out)
        print("exported in %.0f min" % ((time.time() - start) / 60))
    problems = check_export(os.path.join(out, "ExportedProject"), profile)
    if problems:
        sys.exit("FAIL: " + "; ".join(problems))
    print("RESULT: export looks complete (%d scenes, lightmaps as EXR, decompiled scripts)" % len(profile.get("scenes", [])))


if __name__ == "__main__":
    main()
