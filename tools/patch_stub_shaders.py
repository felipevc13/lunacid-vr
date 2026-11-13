#!/usr/bin/env python3
"""
Lunacid Stub Shader Patcher
---------------------------
Replaces AssetRipper DummyShaderTextExporter stubs with proper mobile/VR SubShaders
based on shader semantics and material requirements.
Preserves shader names and .meta GUIDs so existing material references remain intact.
"""

import os
import re
import sys

from passes.pass_shader_stubs import _build_shader_body, apply

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 patch_stub_shaders.py <path_to_assets_or_shader_dir>")
        sys.exit(1)

    target_path = os.path.abspath(sys.argv[1])
    # If passed Assets/Shader, project_root is parent of Assets
    if os.path.basename(target_path) == "Shader":
        project_root = os.path.dirname(os.path.dirname(target_path))
    elif os.path.basename(target_path) == "Assets":
        project_root = os.path.dirname(target_path)
    else:
        project_root = target_path

    res = apply(project_root, dry_run=False)
    print(f"[Stub-Patcher] Applied {res['changes_applied']} shader changes.")
    for d in res['details'][:20]:
        print(f"  -> {d}")
    if len(res['details']) > 20:
        print(f"  ... and {len(res['details']) - 20} more.")

if __name__ == "__main__":
    main()
