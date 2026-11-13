#!/usr/bin/env python3
"""
Pass: Material Floats
---------------------
Sets port-only float properties on specific materials, for shader overrides whose
behaviour must differ between materials of the same shader.

- Ghosty.mat (Shader Forge/ghost, the SPECTRE ghosts): its Ghost mesh carries vertex
  colours that fade the body, so it opts back into vertex colour (_LunaVertexColor 1).
  Every other ghost-shader user has no vertex colour and keeps the shader default (white).
"""

import os
import re

MATERIAL_FLOATS = {
    "Ghosty.mat": {"_LunaVertexColor": "1"},
}


def _set_float(txt, name, value):
    pat = re.compile(r"^(\s*-?\s*)" + re.escape(name) + r":[^\n]*$", re.M)
    if pat.search(txt):
        return pat.sub(lambda m: f"{m.group(1)}{name}: {value}", txt, count=1)
    m = re.search(r"^(\s*)m_Floats:\n", txt, re.M)
    if m:
        indent = m.group(1) + "  "
        return txt[:m.end()] + f"{indent}{name}: {value}\n" + txt[m.end():]
    return txt.rstrip() + f"\n    {name}: {value}\n"


def _configure(txt, floats):
    for name, value in floats.items():
        txt = _set_float(txt, name, value)
    return txt


def _targets(export_dir):
    assets_dir = os.path.join(export_dir, "Assets")
    if not os.path.exists(assets_dir):
        return
    for root, _, files in os.walk(assets_dir):
        for f in files:
            if f in MATERIAL_FLOATS:
                yield os.path.join(root, f), MATERIAL_FLOATS[f]


def detect(export_dir, profile=None):
    findings = []
    for p, floats in _targets(export_dir):
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            txt = fh.read()
        if _configure(txt, floats) != txt:
            findings.append(f"Material {os.path.basename(p)} lacks its port floats")
    return findings


def apply(export_dir, profile=None, dry_run=False):
    changes = 0
    details = []
    for p, floats in _targets(export_dir):
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            txt = fh.read()
        new = _configure(txt, floats)
        if new != txt:
            changes += 1
            details.append(f"Set {', '.join(floats)} on {os.path.relpath(p, export_dir)}")
            if not dry_run:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(new)
    return {"changes_applied": changes, "details": details}


def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {"passed": len(findings) == 0, "remaining_issues": len(findings), "details": findings}
