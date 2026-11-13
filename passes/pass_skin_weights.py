#!/usr/bin/env python3
"""
Pass: Four Skin Weights on the Android Quality Level
----------------------------------------------------
The Android default level ("Medium") skins with 2 bones per vertex; the original PC build runs
the Ultra level (unlimited). With 2 bones, vertices shared between a body bone and a destroyed
part's bone (scaled to zero by OBJ_HEALTH.Die) land elsewhere, so a broken enemy's stumps show
the wrong part of their texture (Big_Moth wings), and blended areas pose differently (the
Nom_ROOT book ribbon). 4 bones covers every mesh the game imports and costs little with GPU
skinning.
"""

import re

from passes.pass_soft_particles import TARGET, _state

WEIGHTS = 4

def detect(export_dir, profile=None):
    path, text, block = _state(export_dir)
    if block is None:
        return []
    m = re.search(r"^    skinWeights: (\d+)$", text[block[0]:block[1]], re.M)
    if m and int(m.group(1)) != WEIGHTS:
        return [f"{TARGET}: the Android quality level has skinWeights {m.group(1)}"]
    return []

def apply(export_dir, profile=None, dry_run=False):
    if not detect(export_dir, profile):
        return {"changes_applied": 0, "details": []}
    path, text, (start, end) = _state(export_dir)
    if not dry_run:
        block = re.sub(r"^    skinWeights: \d+$", f"    skinWeights: {WEIGHTS}", text[start:end], count=1, flags=re.M)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text[:start] + block + text[end:])
    return {"changes_applied": 1, "details": [f"Set skinWeights {WEIGHTS} on the Android quality level"]}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
