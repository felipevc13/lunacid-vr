#!/usr/bin/env python3
"""
Pass: Puddle Stain Reflection
-----------------------------
Stain_mat (the WATER puddle in the MainMenu street) uses Shader Forge/Object with
_MainTex = Stain_D (light grey stain, soft alpha) and _Emission = RT_256, the render
texture of TOWN_Scene_Props/RT/RT_CAM: the moon reflected in the puddle.

On PC only the reflection is visible. Drawn as a lit opaque quad the stain shows as a
black polygon (_Clip 0) or a bright lavender patch (_Clip 1). This pass switches the
material to the Object shader's port-only emission mode: emission * stain alpha,
blended additively after the opaque geometry, no depth write.
"""

import os
import re

DEFAULT_TARGET_MATERIALS = ["Stain_mat.mat"]

def _get_target_materials(profile):
    if profile and "material_overrides" in profile:
        mats = []
        for item in profile["material_overrides"]:
            if isinstance(item, str):
                mats.append(item)
            elif isinstance(item, dict) and "file" in item:
                mats.append(item["file"])
        if mats:
            return mats
    return DEFAULT_TARGET_MATERIALS

# Float properties of the puddle mode (see shaders/Shader Forge_Object.shader).
PUDDLE_FLOATS = {
    "_Clip": "0",
    "_EmissionOnly": "1",
    "_LunaSrcBlend": "1",
    "_LunaDstBlend": "1",
    "_LunaZWrite": "0",
}
PUDDLE_QUEUE = "2501"

def _set_float(txt, name, value):
    pat = re.compile(r"^(\s*-?\s*)" + re.escape(name) + r":[^\n]*$", re.M)
    if pat.search(txt):
        return pat.sub(lambda m: f"{m.group(1)}{name}: {value}", txt, count=1)
    m = re.search(r"^(\s*)m_Floats:\n", txt, re.M)
    if m:
        indent = m.group(1) + "  "
        return txt[:m.end()] + f"{indent}{name}: {value}\n" + txt[m.end():]
    return txt.rstrip() + f"\n    {name}: {value}\n"

def _configure(txt):
    for name, value in PUDDLE_FLOATS.items():
        txt = _set_float(txt, name, value)
    if re.search(r"m_CustomRenderQueue:[^\n]*", txt):
        txt = re.sub(r"m_CustomRenderQueue:[^\n]*", f"m_CustomRenderQueue: {PUDDLE_QUEUE}", txt)
    else:
        txt = f"m_CustomRenderQueue: {PUDDLE_QUEUE}\n" + txt
    return txt

def detect(export_dir, profile=None):
    findings = []
    assets_dir = os.path.join(export_dir, "Assets")
    if not os.path.exists(assets_dir):
        return findings

    targets = _get_target_materials(profile)
    for root, _, files in os.walk(assets_dir):
        for f in files:
            if f in targets:
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()
                if _configure(txt) != txt:
                    findings.append(f"Material {f} is not set up as an additive puddle reflection")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    assets_dir = os.path.join(export_dir, "Assets")
    changes = 0
    details = []

    if not os.path.exists(assets_dir):
        return {"changes_applied": 0, "details": details}

    targets = _get_target_materials(profile)
    for root, _, files in os.walk(assets_dir):
        for f in files:
            if f in targets:
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()

                orig = txt
                txt = _configure(txt)

                if txt != orig:
                    changes += 1
                    details.append(f"Configured additive puddle reflection on {os.path.relpath(p, export_dir)}")
                    if not dry_run:
                        with open(p, "w", encoding="utf-8") as fh:
                            fh.write(txt)

    return {"changes_applied": changes, "details": details}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
