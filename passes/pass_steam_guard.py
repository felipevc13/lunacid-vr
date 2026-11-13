#!/usr/bin/env python3
"""
Pass: Steam Achievement Guard
-----------------------------
Unlock_Achievement.Start calls Steamworks, which is not on the Quest: the call throws (no steam_api library). The
2026-10-27 project wrapped the body in try/catch by hand (LESSONS 31); this pass does the same to the decompiled
script. A version of the script it does not know is reported instead of edited.
"""

import os

TARGET = "Assets/Plugins/Assembly-CSharp-firstpass/Unlock_Achievement.cs"

BODY = """\t\tbool pbAchieved = false;
\t\tSteamUserStats.GetAchievement(DEF_NAME, out pbAchieved);
\t\tif (!pbAchieved)
\t\t{
\t\t\tSteamUserStats.SetAchievement(DEF_NAME);
\t\t\tSteamUserStats.StoreStats();
\t\t\tDebug.Log("Unlocked " + DEF_NAME);
\t\t}
"""

GUARDED = ("\t\ttry\n\t\t{\n" + "".join("\t" + line + "\n" for line in BODY.splitlines()) +
           "\t\t}\n\t\tcatch (System.Exception)\n\t\t{\n"
           "\t\t\t// Safe fallback for platforms without Steam (e.g. Android/Quest standalone)\n\t\t}\n")


def _state(export_dir):
    path = os.path.join(export_dir, TARGET)
    if not os.path.exists(path):
        return path, None, "absent"
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if GUARDED in text:
        return path, text, "guarded"
    if BODY in text:
        return path, text, "raw"
    return path, text, "unknown"


def detect(export_dir, profile=None):
    _, _, state = _state(export_dir)
    if state == "raw":
        return [f"{TARGET}: Steam call without try/catch"]
    if state == "unknown":
        return [f"{TARGET}: unknown version of the script; check the Steam call by hand"]
    return []


def apply(export_dir, profile=None, dry_run=False):
    path, text, state = _state(export_dir)
    if state != "raw":
        return {"changes_applied": 0, "details": detect(export_dir, profile)}
    if not dry_run:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(BODY, GUARDED, 1))
    return {"changes_applied": 1, "details": [f"Wrap the Steam achievement call in try/catch in {TARGET}"]}


def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {"passed": not findings, "remaining_issues": len(findings), "details": findings}
