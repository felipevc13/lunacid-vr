#!/usr/bin/env python3
"""
Pass: XR Packages
-----------------
The exported project has no XR packages, so the port ran as a flat 2D window (a Horizon OS
panel) on the Quest. This adds Unity's OpenXR plugin, which includes the Meta Quest feature,
and XR Plugin Management to Packages/manifest.json. The loader and the Quest feature are turned
on by editor/ConfigureAndroidAndBuild.cs at build time.
"""

import json
import os

TARGET = "Packages/manifest.json"

# OpenXR 1.18.0 (2026-08) is the newest release requiring Unity 6000.0 that has been out a while.
PACKAGES = {
    "com.unity.xr.openxr": "1.18.0",
    "com.unity.xr.management": "4.5.4",
}

def _load(export_dir):
    path = os.path.join(export_dir, TARGET)
    if not os.path.exists(path):
        return path, None
    with open(path, encoding="utf-8") as f:
        return path, json.load(f)

def detect(export_dir, profile=None):
    _, manifest = _load(export_dir)
    if manifest is None:
        return []
    deps = manifest.get("dependencies", {})
    return [f"{TARGET}: {name} {version} missing" for name, version in PACKAGES.items()
            if deps.get(name) != version]

def apply(export_dir, profile=None, dry_run=False):
    findings = detect(export_dir, profile)
    if not findings:
        return {"changes_applied": 0, "details": []}
    path, manifest = _load(export_dir)
    if not dry_run:
        manifest.setdefault("dependencies", {}).update(PACKAGES)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
    return {"changes_applied": len(findings), "details": [f"Add {n} {v}" for n, v in PACKAGES.items()]}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
