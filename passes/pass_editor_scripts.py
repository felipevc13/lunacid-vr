#!/usr/bin/env python3
"""
Pass: Editor Script Synchronization
-----------------------------------
Ensures that critical editor tooling scripts (ConfigureAndroidAndBuild.cs,
AndroidBuildPostProcessorDisabler.cs, ShaderVariantCollectionBuilder.cs)
are deployed from the repository editor/ directory into Assets/Editor/.
"""

import os
import shutil

REQUIRED_EDITOR_SCRIPTS = [
    "ConfigureAndroidAndBuild.cs",
    "AndroidBuildPostProcessorDisabler.cs",
    "ShaderVariantCollectionBuilder.cs",
    "LunaXRSetup.cs"
]

def detect(export_dir, profile=None):
    findings = []
    editor_dir = os.path.join(export_dir, "Assets", "Editor")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_editor = os.path.join(repo_root, "editor")

    for s in REQUIRED_EDITOR_SCRIPTS:
        target = os.path.join(editor_dir, s)
        source = os.path.join(repo_editor, s)
        if not os.path.exists(target):
            findings.append(f"Missing required editor script: Assets/Editor/{s}")
        elif os.path.exists(source):
            with open(source, "r", encoding="utf-8") as f1, open(target, "r", encoding="utf-8") as f2:
                if f1.read() != f2.read():
                    findings.append(f"Out-of-sync editor script: Assets/Editor/{s}")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    editor_dir = os.path.join(export_dir, "Assets", "Editor")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_editor = os.path.join(repo_root, "editor")
    changes = 0
    details = []

    for s in REQUIRED_EDITOR_SCRIPTS:
        target = os.path.join(editor_dir, s)
        source = os.path.join(repo_editor, s)
        if not os.path.exists(source):
            continue

        needs_copy = False
        if not os.path.exists(target):
            needs_copy = True
        else:
            with open(source, "r", encoding="utf-8") as f1, open(target, "r", encoding="utf-8") as f2:
                if f1.read() != f2.read():
                    needs_copy = True

        if needs_copy:
            details.append(f"Deploy editor script {s} to Assets/Editor/")
            changes += 1
            if not dry_run:
                os.makedirs(editor_dir, exist_ok=True)
                shutil.copy2(source, target)

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

