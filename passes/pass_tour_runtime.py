#!/usr/bin/env python3
"""
Pass: Comparison Tour Runtime
-----------------------------
Copies tools/tour/LunaTour.cs into the project (Assets/Scripts/LunaPort/). The same file
runs as a BepInEx plugin in the original PC game. In the port it does nothing unless
<persistentDataPath>/tour/plan_<scene>.txt files exist: then it tours those scenes, takes the planned
shots and quits. See tools/tour/README.md.
"""

import os
import shutil

TARGET = "Assets/Scripts/LunaPort/LunaTour.cs"

def _source():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "tools", "tour", "LunaTour.cs")

def _same(a, b):
    if not os.path.exists(b):
        return False
    with open(a, "rb") as f1, open(b, "rb") as f2:
        return f1.read() == f2.read()

def detect(export_dir, profile=None):
    if not os.path.exists(os.path.join(export_dir, "Assets")):
        return []
    if _same(_source(), os.path.join(export_dir, TARGET)):
        return []
    return [f"{TARGET} missing or out of sync with tools/tour/LunaTour.cs"]

def apply(export_dir, profile=None, dry_run=False):
    if not detect(export_dir, profile):
        return {"changes_applied": 0, "details": []}
    if not dry_run:
        target = os.path.join(export_dir, TARGET)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(_source(), target)
    return {"changes_applied": 1, "details": [f"Deploy tour runtime to {TARGET}"]}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
