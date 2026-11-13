#!/usr/bin/env python3
"""
Pass: Legacy DLL Remapping and Removal
-------------------------------------
Detects legacy precompiled assemblies (TextMeshPro, InputSystem, UnityEngine.UI)
in Assets/Plugins/, reads their GUIDs dynamically from .meta files, remaps component
references across scene files, prefabs, animations, and assets to modern package GUIDs,
and deletes the obsolete DLLs to prevent CS0433 type collision errors.
"""

import os
import re
import json

from core import unity_ids
from passes import pass_rebinding_ui

def _read_guid_from_meta(meta_path):
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8", errors="ignore") as f:
        txt = f.read(500)
    m = re.search(r"guid:\s*([a-f0-9]{32})", txt)
    return m.group(1) if m else None

# The classes the legacy DLLs held and the package script that replaces each one: (namespace, class, GUID of its
# .cs.meta in Unity 6000.0.85's com.unity.ugui 2.0.0 / com.unity.inputsystem 1.20.0). The fileID each class has
# inside a DLL is computed from its name (core/unity_ids.py), as Unity does. A fixed table of fileIDs used to be here,
# wrong for 13 of the 14 TMP classes and HorizontalLayoutGroup (LESSONS 31).
PACKAGE_SCRIPTS = [
    ('UnityEngine.InputSystem.UI', 'InputSystemUIInputModule', '01614664b831546d2ae94a42149d80ac'),
    ('UnityEngine.InputSystem', 'PlayerInput', '62899f850307741f2a39c98a8b639597'),
    ('UnityEngine.InputSystem', 'InputActionReference', 'fc1515ab76e54f068e2f2207940fab32'),
    ('UnityEngine.InputSystem', 'InputActionAsset', '39fa3d8997a24136984ca6e2c99902bc'),
    ('UnityEngine.InputSystem', 'InputSettings', 'c46f07b5ed07e4e92aa78254188d3d10'),
    ('TMPro', 'TextMeshProUGUI', 'f4688fdb7df04437aeb418b961361dc5'),
    ('TMPro', 'TextMeshPro', '9541d86e2fd84c1d9990edf0852d74ab'),
    ('TMPro', 'TMP_FontAsset', '71c1514a6bd24e1e882cebbe1904ce04'),
    ('TMPro', 'TMP_Settings', '2705215ac5b84b70bacc50632be6e391'),
    ('TMPro', 'TMP_StyleSheet', 'ab2114bdc8544297b417dfefe9f1e410'),
    ('TMPro', 'TMP_SpriteAsset', '84a92b25f83d49b9bc132d206b370281'),
    ('TMPro', 'TMP_SubMeshUI', '058cba836c1846c3aa1c5fd2e28aea77'),
    ('TMPro', 'TMP_InputField', '2da0c512f12947e489f739169773d7ca'),
    ('TMPro', 'TMP_Dropdown', '7b743370ac3e4ec2a1668f5455a8ef8a'),
    ('TMPro', 'TMP_ColorGradient', '54d21f6ece3b46479f0c328f8c6007e0'),
    ('TMPro', 'TMP_SelectionCaret', 'ca819640f53b48919bf7774744f7f15e'),
    ('TMPro', 'TMP_SubMesh', '07994bfe8b0e4adb97d706de5dea48d5'),
    ('TMPro', 'TMP_ScrollbarEventHandler', '34e150112c1c42ac83170b52d898e322'),
    ('TMPro', 'TextContainer', '32d40088a6124c578ad6b428df586e2e'),
    ('UnityEngine.EventSystems', 'EventSystem', '76c392e42b5098c458856cdf6ecaaaa1'),
    ('UnityEngine.UI', 'Image', 'fe87c0e1cc204ed48ad3b37840f39efc'),
    ('UnityEngine.UI', 'RawImage', '1344c3c82d62a2a41a3576d8abb8e3ea'),
    ('UnityEngine.UI', 'Mask', '31a19414c41e5ae4aae2af33fee712f6'),
    ('UnityEngine.UI', 'RectMask2D', '3312d7739989d2b4e91e6319e9a96d76'),
    ('UnityEngine.UI', 'VerticalLayoutGroup', '59f8146938fff824cb5fd77236b75775'),
    ('UnityEngine.UI', 'HorizontalLayoutGroup', '30649d3a9faa99c48a7b1166b86bf2a0'),
    ('UnityEngine.UI', 'GridLayoutGroup', '8a8695521f0d02e499659fee002a26c2'),
    ('UnityEngine.UI', 'GraphicRaycaster', 'dc42784cf147c0c48a680349fa168899'),
    ('UnityEngine.UI', 'ScrollRect', '1aa08ab6e0800fa44ae55d278d1423e3'),
    ('UnityEngine.UI', 'LayoutElement', '306cc8c2b49d7114eaa3623786fc2126'),
    ('UnityEngine.UI', 'ContentSizeFitter', '3245ec927659c4140ac4f8d17403cc18'),
    ('UnityEngine.UI', 'CanvasScaler', '0cd44c1031e13a943bb63640046fad76'),
    ('UnityEngine.UI', 'Button', '4e29b1a8efbd4b44bb3f3716e73f07ff'),
    ('UnityEngine.UI', 'Toggle', '9085046f02f69544eb97fd06b6048fe2'),
    ('UnityEngine.UI', 'Slider', '67db9e8f0e2ae9c40bc1e2b64352a6b4'),
    ('UnityEngine.UI', 'Scrollbar', '2a4db7a114972834c8e4117be1d82ba3'),
    ('UnityEngine.UI', 'AspectRatioFitter', '86710e43de46f6f4bac7c8e50813a599'),
    ('UnityEngine.UI', 'Text', '5f7201a12d95ffc409449d95f23cf332'),
    ('UnityEngine.UI', 'InputField', 'd199490a83bb2b844b9695cbf13b01ef'),
]

OFFICIAL_MAPPINGS = {str(unity_ids.script_file_id(ns, cls)): (guid, "11500000") for ns, cls, guid in PACKAGE_SCRIPTS}

# The game's TMP shaders are handled by pass_tmp_essentials, which keeps the GUIDs the materials use. A fixed table of
# their GUIDs used to be here; AssetRipper gives new GUIDs on every export, so it never matched (LESSONS 31).

# Components of a single DLL: the RebindingUI sample's RebindActionUI, whose script pass_rebinding_ui installs.
DLL_SPECIFIC_MAPPINGS = {
    "Unity.InputSystem.RebindingUI.dll": {
        str(unity_ids.script_file_id("UnityEngine.InputSystem.Samples.RebindUI", "RebindActionUI")):
            (pass_rebinding_ui.REBIND_ACTION_UI_GUID, "11500000"),
    },
}

# The packages that replace the deleted DLLs (Unity 6 versions of the 2026-10-27 project).
REPLACEMENT_PACKAGES = {
    "com.unity.inputsystem": "1.20.0",
    "com.unity.ugui": "2.0.0",
}
MANIFEST = os.path.join("Packages", "manifest.json")

LEGACY_DLL_NAMES = [
    "Unity.TextMeshPro.dll",
    "Unity.InputSystem.dll",
    "Unity.InputSystem.RebindingUI.dll",
    "UnityEngine.UI.dll",
    "com.unity.multiplayer-hlapi.Runtime.dll",  # UNet, removed from Unity; nothing of the game uses it
]


def _manifest(export_dir):
    path = os.path.join(export_dir, MANIFEST)
    if not os.path.exists(path):
        return path, None
    with open(path, encoding="utf-8") as fh:
        return path, json.load(fh)


def _missing_packages(export_dir):
    _, manifest = _manifest(export_dir)
    if manifest is None:
        return {}
    deps = manifest.get("dependencies", {})
    return {n: v for n, v in REPLACEMENT_PACKAGES.items() if deps.get(n) != v}

def detect(export_dir, profile=None):
    findings = []
    assets_dir = os.path.join(export_dir, "Assets")
    if not os.path.exists(assets_dir):
        return findings

    plugins_dir = os.path.join(assets_dir, "Plugins")
    if os.path.exists(plugins_dir):
        for dll_name in LEGACY_DLL_NAMES:
            p = os.path.join(plugins_dir, dll_name)
            if os.path.exists(p):
                findings.append(f"Legacy precompiled DLL found: Assets/Plugins/{dll_name}")
    for name, version in _missing_packages(export_dir).items():
        findings.append(f"{MANIFEST}: {name} {version} missing (replaces the legacy DLLs)")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    assets_dir = os.path.join(export_dir, "Assets")
    changes = 0
    details = []

    if not os.path.exists(assets_dir):
        return {"changes_applied": 0, "details": details}

    plugins_dir = os.path.join(assets_dir, "Plugins")
    discovered_guids = {}

    if os.path.exists(plugins_dir):
        for dll_name in LEGACY_DLL_NAMES:
            meta_path = os.path.join(plugins_dir, f"{dll_name}.meta")
            guid = _read_guid_from_meta(meta_path)
            if guid:
                discovered_guids[dll_name] = guid

    # Map discovered GUIDs to official mappings
    replacements = {}
    for dll_name, guid in discovered_guids.items():
        for fid, (target_guid, target_fid) in OFFICIAL_MAPPINGS.items():
            replacements[(guid, fid)] = (target_guid, target_fid)
        for fid, (target_guid, target_fid) in DLL_SPECIFIC_MAPPINGS.get(dll_name, {}).items():
            replacements[(guid, fid)] = (target_guid, target_fid)

    # Remap asset references across project
    target_exts = (".unity", ".prefab", ".asset", ".mat", ".anim", ".controller")
    for root, _, files in os.walk(assets_dir):
        for f in files:
            if f.endswith(target_exts):
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()

                file_repls = 0
                for (oguid, ofid), (nguid, nfid) in replacements.items():
                    if oguid in content:
                        p1 = rf"fileID:\s*{re.escape(ofid)},\s*guid:\s*{oguid}"
                        r1 = f"fileID: {nfid}, guid: {nguid}"
                        content, c1 = re.subn(p1, r1, content)
                        file_repls += c1

                        p2 = rf"guid:\s*{oguid},\s*type:\s*3,\s*fileID:\s*{re.escape(ofid)}"
                        r2 = f"guid: {nguid}, type: 3, fileID: {nfid}"
                        content, c2 = re.subn(p2, r2, content)
                        file_repls += c2

                if file_repls > 0:
                    changes += file_repls
                    details.append(f"Remapped {file_repls} legacy references in {os.path.relpath(p, export_dir)}")
                    if not dry_run:
                        with open(p, "w", encoding="utf-8") as fh:
                            fh.write(content)

    # Delete legacy DLLs and their .meta files
    if os.path.exists(plugins_dir):
        for dll_name in LEGACY_DLL_NAMES:
            dll_p = os.path.join(plugins_dir, dll_name)
            meta_p = os.path.join(plugins_dir, f"{dll_name}.meta")
            if os.path.exists(dll_p):
                details.append(f"Remove obsolete legacy DLL: {dll_name}")
                changes += 1
                if not dry_run:
                    os.remove(dll_p)
            if os.path.exists(meta_p):
                details.append(f"Remove obsolete meta file: {dll_name}.meta")
                changes += 1
                if not dry_run:
                    os.remove(meta_p)

    missing = _missing_packages(export_dir)
    if missing:
        changes += len(missing)
        details += [f"Add {n} {v} to {MANIFEST}" for n, v in missing.items()]
        if not dry_run:
            path, manifest = _manifest(export_dir)
            manifest.setdefault("dependencies", {}).update(missing)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)
                fh.write("\n")

    return {"changes_applied": changes, "details": details}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }

