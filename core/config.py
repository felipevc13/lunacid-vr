#!/usr/bin/env python3
"""
Machine configuration: every path that belongs to one computer, in one place.

Order: an environment variable LUNA_<KEY> (LUNA_PROJECT, LUNA_WORK...), then local.json at the repository
root (never committed; local.example.json shows the keys), then a default that fits a plain install on
macOS or Windows. Nothing here names a particular machine (tests/test_repo_cleanliness.py checks it).

    python3 core/config.py            # prints the resolved configuration
    python3 core/config.py project    # prints one value (for shell scripts)
"""

import glob
import json
import os
import platform
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_FILE = os.path.join(REPO_ROOT, "local.json")
UNITY_VERSION = "6000.0.85f1"

KEYS = {
    "work": "Work folder: extraction, generated shaders, diagnostics, saves backups.",
    "project": "The Unity project the passes change and the build uses.",
    "game_data": "The game's LUNACID_Data folder (from SteamCMD or a Steam install).",
    "unity": "The Unity 6 editor executable.",
    "android_sdk": "Android SDK; default: the one Unity Hub installs with the Android module.",
    "android_ndk": "Android NDK; default: Unity's.",
    "jdk": "Java JDK; default: Unity's OpenJDK.",
    "builds": "Where the APK and OBB go; default: Builds beside the project.",
    "gradle_home": "Gradle's cache; default: .gradle beside the project.",
    "lightmap_dump_dir": "Optional: lightmaps dumped from the running PC game (development only).",
    "dotnet": "Optional: the .NET 8 SDK for tools/shader_gen; default: on the PATH or in <work>/tools/dotnet.",
    "assetripper": "AssetRipper 2.0.0's AssetRipper.GUI.Free executable (tools/extract/assetripper.py).",
}


def _unity_default():
    if platform.system() == "Darwin":
        path = "/Applications/Unity/Hub/Editor/%s/Unity.app/Contents/MacOS/Unity" % UNITY_VERSION
    elif platform.system() == "Windows":
        path = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Unity", "Hub", "Editor", UNITY_VERSION, "Editor", "Unity.exe")
    else:
        path = os.path.expanduser("~/Unity/Hub/Editor/%s/Editor/Unity" % UNITY_VERSION)
    return path


def _unity_android_player(unity):
    """Unity Hub's Android module, beside the editor."""
    if not unity:
        return None
    if platform.system() == "Darwin":   # .../Unity.app/Contents/MacOS/Unity -> .../Unity.app/Contents/PlaybackEngines
        root = os.path.dirname(os.path.dirname(unity))
        candidates = [os.path.join(root, "PlaybackEngines", "AndroidPlayer"),
                      os.path.join(os.path.dirname(os.path.dirname(root)), "PlaybackEngines", "AndroidPlayer")]
    else:                                # ...\Editor\Unity.exe -> ...\Editor\Data\PlaybackEngines
        candidates = [os.path.join(os.path.dirname(unity), "Data", "PlaybackEngines", "AndroidPlayer")]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def _local():
    if os.path.exists(LOCAL_FILE):
        with open(LOCAL_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def load():
    """The resolved configuration: {key: absolute path or None}."""
    local = _local()
    cfg = {}
    for key in KEYS:
        value = os.environ.get("LUNA_" + key.upper()) or local.get(key)
        cfg[key] = os.path.abspath(os.path.expanduser(value)) if value else None
    cfg["work"] = cfg["work"] or os.path.abspath(os.path.expanduser("~/lunacid-work"))
    cfg["project"] = cfg["project"] or os.path.join(cfg["work"], "project", "ExportedProject")
    cfg["unity"] = cfg["unity"] or _unity_default()
    player = _unity_android_player(cfg["unity"])
    if player:
        cfg["android_sdk"] = cfg["android_sdk"] or os.path.join(player, "SDK")
        cfg["android_ndk"] = cfg["android_ndk"] or os.path.join(player, "NDK")
        cfg["jdk"] = cfg["jdk"] or os.path.join(player, "OpenJDK")
    parent = os.path.dirname(cfg["project"])
    cfg["builds"] = cfg["builds"] or os.path.join(parent, "Builds")
    cfg["gradle_home"] = cfg["gradle_home"] or os.path.join(parent, ".gradle")
    return cfg


def unity_env(cfg=None):
    """Environment for a Unity run: the build script (editor/ConfigureAndroidAndBuild.cs) reads these."""
    cfg = cfg or load()
    env = {}
    for key, name in (("android_sdk", "LUNA_ANDROID_SDK"), ("android_ndk", "LUNA_ANDROID_NDK"), ("jdk", "LUNA_JDK"),
                      ("builds", "LUNA_BUILDS"), ("gradle_home", "LUNA_GRADLE_HOME")):
        if cfg.get(key):
            env[name] = cfg[key]
    return env


if __name__ == "__main__":
    cfg = load()
    if len(sys.argv) > 1:
        value = cfg.get(sys.argv[1])
        if value is None:
            sys.exit("not set: %s" % sys.argv[1])
        print(value)
    else:
        for key in KEYS:
            print("%-18s %s" % (key, cfg.get(key)))
