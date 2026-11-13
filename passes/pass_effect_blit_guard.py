#!/usr/bin/env python3
"""
Pass: Effect_scr Camera Blit Guard
----------------------------------
In Lunacid, Effect_scr.cs implements OnRenderImage with an opaque Graphics.Blit.
In MainMenu.unity, Effect_scr is attached to CAM2 (a secondary UI-only camera
with m_ClearFlags = 3 / Don't Clear and m_Depth = 5).

On Vulkan Android mobile, OnRenderImage on a secondary camera forces an offscreen
intermediate RenderTexture that contains only UI on a black background. Blitting
this with an opaque shader completely overwrites the 3D scene rendered by CAM.

This pass guards OnRenderImage in Effect_scr.cs with #if !UNITY_ANDROID || UNITY_EDITOR,
allowing CAM2 to render UI directly over CAM's 3D framebuffer on Quest standalone.
"""

import os
import re

TARGET_SCRIPT = "Assets/Scripts/Assembly-CSharp/Effect_scr.cs"

def detect(export_dir, profile=None):
    findings = []
    target_path = os.path.join(export_dir, TARGET_SCRIPT)
    if not os.path.exists(target_path):
        return findings

    with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Check if OnRenderImage is unguarded
    pattern = r'(?<!#if !UNITY_ANDROID \|\| UNITY_EDITOR\s)\bvoid OnRenderImage\b'
    if re.search(pattern, content) and "#if !UNITY_ANDROID || UNITY_EDITOR" not in content:
        findings.append(f"Unguarded OnRenderImage in {TARGET_SCRIPT} (overwrites multi-camera framebuffer on Android Vulkan)")

    return findings

def apply(export_dir, profile=None, dry_run=False):
    target_path = os.path.join(export_dir, TARGET_SCRIPT)
    changes = 0
    details = []

    if not os.path.exists(target_path):
        return {"changes_applied": 0, "details": details}

    with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Search for OnRenderImage method
    m = re.search(r'(\t*private void OnRenderImage\s*\([^)]*\)\s*\{[^}]*\})', content)
    if m and "#if !UNITY_ANDROID || UNITY_EDITOR" not in content:
        old_method = m.group(1)
        guarded_method = f"""#if !UNITY_ANDROID || UNITY_EDITOR
{old_method}
#endif"""
        new_content = content[:m.start(1)] + guarded_method + content[m.end(1):]
        changes += 1
        details.append(f"Guarded OnRenderImage in {TARGET_SCRIPT}")

        if not dry_run:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)

    return {"changes_applied": changes, "details": details}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }


def _config_project():
    """The project from the machine configuration (core/config.py), for running this pass by hand."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core import config
    return config.load()["project"]

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else _config_project()
    res = apply(target)
    print(res)
