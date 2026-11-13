#!/usr/bin/env python3
"""
Pass: Soft Particles on the Android Quality Level
-------------------------------------------------
The PC game runs at a quality level with soft particles (additive light beams, steam and smoke
fade out where they meet walls and floors). The Android default level ("Medium") has them off,
so in PITT_A1 the stacked LIGHT_BEAM/steam particles near the pit edge added up to a white screen
and HUB_01's smoke showed hard quads. This turns softParticles on for the level Android uses;
Unity then renders the camera depth texture the particle shaders read.
"""

import os
import re

TARGET = "ProjectSettings/QualitySettings.asset"

def _android_level(text):
    m = re.search(r"m_PerPlatformDefaultQuality:.*?^\s+Android: (\d+)$", text, re.S | re.M)
    return int(m.group(1)) if m else None

def _levels(text):
    """(start, end) offsets of each quality level block, in order."""
    starts = [m.start() for m in re.finditer(r"^  - serializedVersion: \d+\n    name: ", text, re.M)]
    end = text.find("m_PerPlatformDefaultQuality")
    return list(zip(starts, starts[1:] + [end if end > 0 else len(text)]))

def _state(export_dir):
    path = os.path.join(export_dir, TARGET)
    if not os.path.exists(path):
        return None, None, None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    level = _android_level(text)
    blocks = _levels(text)
    if level is None or level >= len(blocks):
        return path, text, None
    return path, text, blocks[level]

def detect(export_dir, profile=None):
    path, text, block = _state(export_dir)
    if block is None:
        return []
    if re.search(r"^    softParticles: 0$", text[block[0]:block[1]], re.M):
        return [f"{TARGET}: the Android quality level has softParticles off"]
    return []

def apply(export_dir, profile=None, dry_run=False):
    if not detect(export_dir, profile):
        return {"changes_applied": 0, "details": []}
    path, text, (start, end) = _state(export_dir)
    if not dry_run:
        block = re.sub(r"^    softParticles: 0$", "    softParticles: 1", text[start:end], count=1, flags=re.M)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text[:start] + block + text[end:])
    return {"changes_applied": 1, "details": ["Enable softParticles on the Android quality level"]}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
