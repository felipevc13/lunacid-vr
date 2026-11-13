#!/usr/bin/env python3
"""
Pass: Intro Skip on the Right Trigger
-------------------------------------
skip_con.cs skips the intro once Input.anyKey has been held for 2.5 s. On the Quest the legacy
input reports JoystickButton16 held from boot (an Android joystick the headset exposes), so the
intro skipped itself. The hold now reads LunaVRRuntime.SkipHeld(): the right controller's trigger,
or any keyboard or mouse key.
"""

import os

TARGET = "Assets/Scripts/Assembly-CSharp/skip_con.cs"
OLD = "if (Input.anyKey)"
NEW = "if (LunaVRRuntime.SkipHeld())"

def detect(export_dir, profile=None):
    path = os.path.join(export_dir, TARGET)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return [f"{TARGET}: intro skip reads Input.anyKey"] if OLD in text else []

def apply(export_dir, profile=None, dry_run=False):
    if not detect(export_dir, profile):
        return {"changes_applied": 0, "details": []}
    path = os.path.join(export_dir, TARGET)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(OLD, NEW))
    return {"changes_applied": 1, "details": [f"{TARGET}: skip on LunaVRRuntime.SkipHeld()"]}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {"passed": not findings, "remaining_issues": len(findings), "details": findings}


def _config_project():
    """The project from the machine configuration (core/config.py), for running this pass by hand."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core import config
    return config.load()["project"]

if __name__ == "__main__":
    import sys
    print(apply(sys.argv[1] if len(sys.argv) > 1 else _config_project()))
