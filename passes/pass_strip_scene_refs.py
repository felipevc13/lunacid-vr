#!/usr/bin/env python3
"""
Pass: Strip Scene References from External Assets
-------------------------------------------------
Detects and removes invalid cross-boundary references from external assets
(.asset, .prefab, .mat) to scene objects (type: 2 or references matching scene GUIDs).
Such references cause fatal 'ReadObjectThreaded' crashes during Unity player build.
"""

import os
import re

def _discover_scene_guids(assets_dir):
    scene_guids = {}
    if not os.path.exists(assets_dir):
        return scene_guids
    for root, _, files in os.walk(assets_dir):
        for f in files:
            if f.endswith(".unity.meta"):
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    m = re.search(r"guid:\s*([a-f0-9]{32})", fh.read(500))
                    if m:
                        scene_guids[m.group(1)] = f[:-11]  # remove .unity.meta
    return scene_guids

def detect(export_dir, profile=None):
    findings = []
    assets_dir = os.path.join(export_dir, "Assets")
    if not os.path.exists(assets_dir):
        return findings

    scene_guids = _discover_scene_guids(assets_dir)
    target_dirs = [
        os.path.join(assets_dir, "MonoBehaviour"),
        os.path.join(assets_dir, "Resources"),
        os.path.join(assets_dir, "GameObject"),
        os.path.join(assets_dir, "ScriptableObject"),
        os.path.join(assets_dir, "Material")
    ]

    for d in target_dirs:
        if not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".asset", ".prefab", ".mat")):
                    p = os.path.join(root, f)
                    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    has_scene_guid = any(g in content for g in scene_guids)
                    if has_scene_guid:
                        findings.append(f"Invalid scene reference in {os.path.relpath(p, export_dir)}")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    assets_dir = os.path.join(export_dir, "Assets")
    changes = 0
    details = []

    if not os.path.exists(assets_dir):
        return {"changes_applied": 0, "details": details}

    scene_guids = _discover_scene_guids(assets_dir)
    target_dirs = [
        os.path.join(assets_dir, "MonoBehaviour"),
        os.path.join(assets_dir, "Resources"),
        os.path.join(assets_dir, "GameObject"),
        os.path.join(assets_dir, "ScriptableObject"),
        os.path.join(assets_dir, "Material")
    ]

    def repl_flow1(m):
        guid = m.group(1)
        if guid in scene_guids:
            return "{fileID: 0}"
        return m.group(0)

    def repl_flow2(m):
        guid = m.group(1)
        if guid in scene_guids:
            return "{fileID: 0}"
        return m.group(0)

    def repl_multiline(m):
        prefix = m.group(1)
        guid = m.group(2)
        if guid in scene_guids:
            return f"{prefix}{{fileID: 0}}"
        return m.group(0)

    for d in target_dirs:
        if not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".asset", ".prefab", ".mat")):
                    p = os.path.join(root, f)
                    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()

                    has_scene_guid = any(g in content for g in scene_guids)
                    if not has_scene_guid:
                        continue

                    orig = content
                    content, c1 = re.subn(r'\{fileID:\s*-?\d+,\s*guid:\s*([a-f0-9]{32}),\s*type:\s*\d+\}', repl_flow1, content)
                    content, c2 = re.subn(r'\{guid:\s*([a-f0-9]{32}),\s*type:\s*\d+,\s*fileID:\s*-?\d+\}', repl_flow2, content)
                    content, c3 = re.subn(r'([a-zA-Z0-9_]+:\s*)\n\s*fileID:\s*-?\d+\s*\n\s*guid:\s*([a-f0-9]{32})\s*\n\s*type:\s*\d+', repl_multiline, content)

                    file_repls = c1 + c2 + c3
                    if file_repls > 0 or content != orig:
                        changes += file_repls if file_repls > 0 else 1
                        details.append(f"Stripped {file_repls} scene refs in {os.path.relpath(p, export_dir)}")
                        if not dry_run:
                            with open(p, "w", encoding="utf-8") as fh:
                                fh.write(content)

    return {"changes_applied": changes, "details": details}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }

