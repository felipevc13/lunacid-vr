#!/usr/bin/env python3
"""
Pass: Filesystem Path Redirection for Android
---------------------------------------------
Detects hardcoded Application.dataPath file access in decompiled C# scripts
that fail on Android due to read-only app package boundaries.
Redirects save files, settings, and read/write streams to persistentDataPath
and deploys LunacidFileSystemHelper.cs to Assembly-CSharp.
"""

import os
import re
import shutil

TARGET_SCRIPTS = [
    "Save.cs", "CONTROL.cs", "Menus.cs", "LocalTextHolder.cs",
    "KeyBindTest.cs", "Analyz_NPC.cs", "DemoMode.cs"
]

def detect(export_dir, profile=None):
    findings = []
    scripts_dir = os.path.join(export_dir, "Assets", "Scripts")
    if not os.path.exists(scripts_dir):
        return findings

    # Check for unredirected Application.dataPath file write/read patterns
    pattern = re.compile(r'Application\.dataPath\s*\+\s*"(?:/Resources/|/SAVE_|/SETTINGS\.MIDNIGHT|/SYS\.MIDNIGHT)')
    for root, _, files in os.walk(scripts_dir):
        for f in files:
            if f in TARGET_SCRIPTS:
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
                for line in lines:
                    if pattern.search(line) and 'LunacidFileSystemHelper' not in line and 'RuntimePlatform.Android' not in line:
                        findings.append(f"Unredirected Application.dataPath I/O in {os.path.relpath(p, export_dir)}: {line.strip()}")
                        break

    # Check if LunacidFileSystemHelper is installed
    helper_path = os.path.join(export_dir, "Assets", "Scripts", "Assembly-CSharp", "LunacidFileSystemHelper.cs")
    if not os.path.exists(helper_path):
        findings.append("Missing runtime helper: Assets/Scripts/Assembly-CSharp/LunacidFileSystemHelper.cs")

    return findings

def apply(export_dir, profile=None, dry_run=False):
    assets_dir = os.path.join(export_dir, "Assets")
    scripts_dir = os.path.join(assets_dir, "Scripts")
    changes = 0
    details = []

    if not os.path.exists(assets_dir):
        return {"changes_applied": 0, "details": details}

    # 1. Install runtime helper
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_helper = os.path.join(repo_root, "runtime", "LunacidFileSystemHelper.cs")
    target_dir = os.path.join(scripts_dir, "Assembly-CSharp")
    target_helper = os.path.join(target_dir, "LunacidFileSystemHelper.cs")

    if os.path.exists(source_helper):
        needs_copy = False
        if not os.path.exists(target_helper):
            needs_copy = True
        else:
            with open(source_helper, "r", encoding="utf-8") as f1, open(target_helper, "r", encoding="utf-8") as f2:
                if f1.read() != f2.read():
                    needs_copy = True
        if needs_copy:
            details.append("Deploy LunacidFileSystemHelper.cs to Assembly-CSharp")
            changes += 1
            if not dry_run:
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy2(source_helper, target_helper)

    # 2. Redirect script paths
    if os.path.exists(scripts_dir):
        for root, _, files in os.walk(scripts_dir):
            for f in files:
                if f in TARGET_SCRIPTS:
                    p = os.path.join(root, f)
                    with open(p, "r", encoding="utf-8") as fh:
                        code = fh.read()

                    orig = code
                    # StreamReader redirection
                    code = re.sub(
                        r"new\s+StreamReader\s*\(\s*(Application\.dataPath\s*\+\s*\"/Resources/[^)]+)\)",
                        r"Lunacid.VR.LunacidFileSystemHelper.OpenTextReader(\g<1>)", code
                    )
                    # StreamWriter redirection
                    code = re.sub(
                        r"new\s+StreamWriter\s*\(\s*(Application\.dataPath\s*\+\s*\"/Resources/[^)]+)\)",
                        r"Lunacid.VR.LunacidFileSystemHelper.CreateTextWriter(\g<1>)", code
                    )
                    # File.Exists redirection
                    code = re.sub(
                        r"File\.Exists\s*\(\s*(Application\.dataPath\s*\+\s*\"/Resources/[^)]+)\)",
                        r"Lunacid.VR.LunacidFileSystemHelper.FileExists(\g<1>)", code
                    )
                    # Save paths redirection
                    # Only the file name goes in: the path ends at the first ',' ')' or ';', so a FileMode argument
                    # stays with the FileStream (LESSONS 31).
                    code = re.sub(
                        r'Application\.dataPath\s*\+\s*"/SAVE_"\s*\+\s*([^,;)]+?)\s*(?=[,;)])',
                        r'Lunacid.VR.LunacidFileSystemHelper.GetSavePath("SAVE_" + \g<1>)', code
                    )
                    code = code.replace(
                        'Application.dataPath + "/SETTINGS.MIDNIGHT"',
                        'Lunacid.VR.LunacidFileSystemHelper.GetSavePath("SETTINGS.MIDNIGHT")'
                    )
                    code = code.replace(
                        'Application.dataPath + "/SYS.MIDNIGHT"',
                        'Lunacid.VR.LunacidFileSystemHelper.GetSavePath("SYS.MIDNIGHT")'
                    )
                    # OpenURL guard for desktop-only bindings viewing
                    code = re.sub(
                        r'(?<!RuntimePlatform\.Android\) )Application\.OpenURL\s*\(\s*Application\.dataPath\s*\+\s*"/Resources/BINDINGS\.txt"\s*\);',
                        r'if (Application.platform != RuntimePlatform.Android) Application.OpenURL(Application.dataPath + "/Resources/BINDINGS.txt");',
                        code
                    )

                    if code != orig:
                        changes += 1
                        details.append(f"Redirected Application.dataPath I/O calls in {os.path.relpath(p, export_dir)}")
                        if not dry_run:
                            with open(p, "w", encoding="utf-8") as fh:
                                fh.write(code)

    return {"changes_applied": changes, "details": details}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }

