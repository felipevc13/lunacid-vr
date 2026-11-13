#!/usr/bin/env python3
"""
Pass: Neutral BINDINGS.txt
--------------------------
KeyBindTest.cs reads Resources/BINDINGS.txt on every focus and applies each listed path as a
binding override by position (ApplyBindingOverride(index, path)). The file in the export is the
PC game's: once the port's input asset changes (template XR bindings removed, Touch bindings
added), the positions no longer line up. On the Quest it put the template "<XRController>/{Primary2DAxis}"
back on Move at another binding's place, and, through a parser slip in LOAD (the "Fire" header
keeps the previous action index), wrote Fire's paths over Look: the right trigger drove Look, and
a binding index past the end threw on every start.

The file is cut to its instruction header: LOAD finds no action headers and applies nothing, so
the input asset is used as is. The file still exists, so KeyBindTest does not regenerate it.
"""

import os

TARGET = "Assets/Resources/BINDINGS.txt"
HEADERS = ("Move", "Look", "Fire", "Maus_On", "Maus_Off")   # the actions LOAD applies overrides for

def _lines(text):
    return [l.strip() for l in text.replace("\r", "\n").split("\n")]

def detect(export_dir, profile=None):
    path = os.path.join(export_dir, TARGET)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = _lines(f.read())
    found = [h for h in HEADERS if h in lines]
    return [f"{TARGET}: binding overrides for {', '.join(found)}"] if found else []

def apply(export_dir, profile=None, dry_run=False):
    if not detect(export_dir, profile):
        return {"changes_applied": 0, "details": []}
    path = os.path.join(export_dir, TARGET)
    with open(path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    # Keep everything before the first action map name ("Player" on its own line).
    lines = text.split("\n")
    cut = next((i for i, l in enumerate(lines) if l.strip() == "Player"), len(lines))
    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines[:cut]).rstrip() + "\n")
    return {"changes_applied": 1, "details": [f"{TARGET}: cut to its header (no binding overrides)"]}

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
