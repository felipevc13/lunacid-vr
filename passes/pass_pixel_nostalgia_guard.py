#!/usr/bin/env python3
"""
Pass: PixelNostalgia Dynamic Injection Guard
--------------------------------------------
Aestheticcc_scr.cs dynamically executes gameObject.AddComponent<PixelNostalgia>()
at runtime. Because the decompiled pixelnostalgia.shader only contains 1 pass,
PixelNostalgia.cs attempts to execute context.command.Blit(..., 4), causing
a flood of 'Invalid pass number (4) for Graphics.Blit' errors on mobile Vulkan
and introducing severe frametime overhead.

This pass adds an Android platform guard (#if !UNITY_ANDROID || UNITY_EDITOR)
to SpawnPIX() so the unviable screen-space retro effect is bypassed on Quest.
"""

import os
import re

TARGET_SCRIPT = os.path.join("Assets", "Scripts", "Assembly-CSharp", "Aestheticcc_scr.cs")

UNGUARDED_PATTERN = re.compile(
    r'(private\s+IEnumerator\s+SpawnPIX\s*\(\s*\)\s*\{)(?!\s*#if\s*!UNITY_ANDROID)([^}]*AddComponent<PixelNostalgia>[^}]*\})',
    re.MULTILINE
)

def detect(export_dir, profile=None):
    findings = []
    target_path = os.path.join(export_dir, TARGET_SCRIPT)
    if not os.path.exists(target_path):
        return findings

    with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "AddComponent<PixelNostalgia>()" in content and "#if !UNITY_ANDROID" not in content:
        findings.append(f"Unguarded PixelNostalgia runtime injection in {TARGET_SCRIPT}")

    return findings

def apply(export_dir, profile=None, dry_run=False):
    target_path = os.path.join(export_dir, TARGET_SCRIPT)
    changes = 0
    details = []

    if not os.path.exists(target_path):
        return {"changes_applied": 0, "details": details}

    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "AddComponent<PixelNostalgia>()" in content and "#if !UNITY_ANDROID" not in content:
        # Replace SpawnPIX method body with platform guard
        old_spawn = re.search(r'private\s+IEnumerator\s+SpawnPIX\s*\(\s*\)\s*\{[^}]+\}', content)
        if old_spawn:
            guarded_spawn = """private IEnumerator SpawnPIX()
	{
#if !UNITY_ANDROID || UNITY_EDITOR
		yield return new WaitForSeconds(0.1f);
		PX = base.gameObject.AddComponent<PixelNostalgia>();
#else
		yield break;
#endif
	}"""
            new_content = content[:old_spawn.start()] + guarded_spawn + content[old_spawn.end():]
            changes += 1
            details.append(f"Guarded PixelNostalgia injection in {TARGET_SCRIPT}")
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
