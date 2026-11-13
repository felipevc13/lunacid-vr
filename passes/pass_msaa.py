#!/usr/bin/env python3
"""
Pass: 4x MSAA on the Android Quality Level
------------------------------------------
The Android default level ("Medium") has antiAliasing 0, so polygon edges shimmer and stair-step
in the headset. 4x MSAA is the usual VR setting and nearly free on the Quest's tiled GPU: it smooths
edges only, so the game's point-filtered pixel textures stay as they are.
"""

import re

from passes.pass_soft_particles import TARGET, _state

SAMPLES = 4

def detect(export_dir, profile=None):
    path, text, block = _state(export_dir)
    if block is None:
        return []
    m = re.search(r"^    antiAliasing: (\d+)$", text[block[0]:block[1]], re.M)
    if m and int(m.group(1)) != SAMPLES:
        return [f"{TARGET}: the Android quality level has antiAliasing {m.group(1)}"]
    return []

def apply(export_dir, profile=None, dry_run=False):
    if not detect(export_dir, profile):
        return {"changes_applied": 0, "details": []}
    path, text, (start, end) = _state(export_dir)
    if not dry_run:
        block = re.sub(r"^    antiAliasing: \d+$", f"    antiAliasing: {SAMPLES}", text[start:end], count=1, flags=re.M)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text[:start] + block + text[end:])
    return {"changes_applied": 1, "details": [f"Set antiAliasing {SAMPLES} on the Android quality level"]}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
