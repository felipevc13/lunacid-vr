#!/usr/bin/env python3
"""
Pass: Gradle Without Parallel Execution
---------------------------------------
Unity 6 exports the Android Gradle project with org.gradle.parallel=true. With the
bundled Gradle 9.3.1 the composite build (launcher + unityLibrary) deadlocks: the
"included builds" worker waits on DefaultResourceLockCoordinationService while the
Daemon worker waits in DefaultBuildControllers.awaitCompletion, at 0% CPU, forever
(Builds 14, 15 and 16, often right after "symbols will be stripped").

This pass enables Unity's custom gradle.properties template
(Assets/Plugins/Android/gradleTemplate.properties, useCustomGradlePropertiesTemplate: 1)
with org.gradle.parallel=false.
"""

import os
import re

TEMPLATE = "Assets/Plugins/Android/gradleTemplate.properties"
SETTINGS = "ProjectSettings/ProjectSettings.asset"

TEMPLATE_BODY = """org.gradle.jvmargs=-Xmx**JVM_HEAP_SIZE**M
org.gradle.parallel=false
unityStreamingAssets=**STREAMING_ASSETS**
**ADDITIONAL_PROPERTIES**
"""

def _template_ok(export_dir):
    path = os.path.join(export_dir, TEMPLATE)
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return "org.gradle.parallel=false" in f.read()

def _settings_ok(export_dir):
    path = os.path.join(export_dir, SETTINGS)
    if not os.path.exists(path):
        return True
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return "useCustomGradlePropertiesTemplate: 1" in f.read()

def detect(export_dir, profile=None):
    findings = []
    if not _template_ok(export_dir):
        findings.append(f"{TEMPLATE} missing or not forcing org.gradle.parallel=false (Gradle 9.3.1 deadlock)")
    if not _settings_ok(export_dir):
        findings.append(f"{SETTINGS} does not enable useCustomGradlePropertiesTemplate")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    changes = 0
    details = []

    if not _template_ok(export_dir):
        changes += 1
        details.append(f"Wrote {TEMPLATE} with org.gradle.parallel=false")
        if not dry_run:
            path = os.path.join(export_dir, TEMPLATE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(TEMPLATE_BODY)

    settings_path = os.path.join(export_dir, SETTINGS)
    if os.path.exists(settings_path) and not _settings_ok(export_dir):
        with open(settings_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        new_content, n = re.subn(r"useCustomGradlePropertiesTemplate: 0", "useCustomGradlePropertiesTemplate: 1", content)
        if n:
            changes += 1
            details.append(f"Enabled useCustomGradlePropertiesTemplate in {SETTINGS}")
            if not dry_run:
                with open(settings_path, "w", encoding="utf-8") as f:
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
