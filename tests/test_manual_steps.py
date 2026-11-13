#!/usr/bin/env python3
"""The four steps done by hand on the 2026-10-27 project, now passes (LESSONS 31, RELEASE_PLAN item 3):
the TMP Essential Resources with the game's TMP shader GUIDs, the Input System RebindingUI sample, the hlapi DLL,
and the packages that replace the removed DLLs. Made-up projects; no Unity, no network."""

import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from passes import pass_filesystem_redirect, pass_legacy_dlls, pass_rebinding_ui, pass_steam_guard, pass_tmp_essentials  # noqa: E402


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode())


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def meta(guid):
    return "fileFormatVersion: 2\nguid: %s\nShaderImporter:\n  externalObjects: {}\n" % guid


def add(tar, name, data):
    data = data.encode() if isinstance(data, str) else data
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.export = os.path.join(self.tmp, "ExportedProject")
        self.assets = os.path.join(self.export, "Assets")
        write(os.path.join(self.export, "Packages", "manifest.json"), json.dumps({"dependencies": {"com.unity.timeline": "1.8.7"}}))
        os.makedirs(self.assets)

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestLegacyDllsManualSteps(Project):
    REBIND = "fbe28a4b1c7f2904442f19856180c2ef"

    def setUp(self):
        super().setUp()
        plugins = os.path.join(self.assets, "Plugins")
        write(os.path.join(plugins, "Unity.InputSystem.RebindingUI.dll"), b"dll")
        write(os.path.join(plugins, "Unity.InputSystem.RebindingUI.dll.meta"), meta(self.REBIND))
        write(os.path.join(plugins, "com.unity.multiplayer-hlapi.Runtime.dll"), b"dll")
        write(os.path.join(plugins, "com.unity.multiplayer-hlapi.Runtime.dll.meta"), meta("c" * 32))
        self.scene = os.path.join(self.assets, "Scenes", "HUB_01.unity")
        write(self.scene, "  m_Script: {fileID: 781412291, guid: %s, type: 3}\n" % self.REBIND)

    def test_hlapi_dll_is_removed(self):
        pass_legacy_dlls.apply(self.export)
        self.assertFalse(os.path.exists(os.path.join(self.assets, "Plugins", "com.unity.multiplayer-hlapi.Runtime.dll")))
        self.assertFalse(os.path.exists(os.path.join(self.assets, "Plugins", "com.unity.multiplayer-hlapi.Runtime.dll.meta")))

    def test_rebind_action_ui_points_at_the_sample_script(self):
        pass_legacy_dlls.apply(self.export)
        text = read(self.scene)
        self.assertIn("m_Script: {fileID: 11500000, guid: %s, type: 3}" % pass_rebinding_ui.REBIND_ACTION_UI_GUID, text)
        self.assertNotIn(self.REBIND, text)

    def test_packages_that_replace_the_dlls_are_added(self):
        self.assertTrue(any("com.unity.ugui" in f for f in pass_legacy_dlls.detect(self.export)))
        pass_legacy_dlls.apply(self.export)
        deps = json.loads(read(os.path.join(self.export, "Packages", "manifest.json")))["dependencies"]
        self.assertEqual(deps["com.unity.inputsystem"], "1.20.0")
        self.assertEqual(deps["com.unity.ugui"], "2.0.0")
        self.assertEqual(deps["com.unity.timeline"], "1.8.7")
        self.assertTrue(pass_legacy_dlls.verify(self.export)["passed"])
        self.assertEqual(pass_legacy_dlls.apply(self.export)["changes_applied"], 0)


class TestTmpEssentials(Project):
    GAME_SDF = "1" * 32

    def setUp(self):
        super().setUp()
        shaders = os.path.join(self.assets, "Resources", "shaders")
        write(os.path.join(shaders, "tmp_sdf.shader"), 'Shader "TextMeshPro/Distance Field" { stub }')
        write(os.path.join(shaders, "tmp_sdf.shader.meta"), meta(self.GAME_SDF))
        write(os.path.join(shaders, "other.shader"), "game")
        write(os.path.join(shaders, "other.shader.meta"), meta("2" * 32))
        # A made-up "TMP Essential Resources.unitypackage", laid out as Unity's: <guid>/{pathname,asset,asset.meta}.
        self.unity = os.path.join(self.tmp, "Unity.app", "Contents", "MacOS", "Unity")
        pkg = pass_tmp_essentials.essentials_package(self.unity)
        os.makedirs(os.path.dirname(pkg))
        with tarfile.open(pkg, "w:gz") as tar:
            for guid, path, data in (("a" * 32, "Assets/TextMesh Pro/Shaders/TMP_SDF.shader", "package sdf"),
                                     ("b" * 32, "Assets/TextMesh Pro/Shaders/TMPro.cginc", "cginc"),
                                     ("d" * 32, "Assets/TextMesh Pro/Resources/TMP Settings.asset", "settings")):
                add(tar, guid + "/pathname", path + "\n00")
                add(tar, guid + "/asset", data)
                add(tar, guid + "/asset.meta", meta(guid))
            add(tar, "e" * 32 + "/pathname", "Assets/TextMesh Pro")
            add(tar, "e" * 32 + "/asset.meta", "fileFormatVersion: 2\nguid: %s\nfolderAsset: yes\n" % ("e" * 32))
        self.profile = {"unity": self.unity}

    def test_package_path_on_mac_and_windows(self):
        mac = pass_tmp_essentials.essentials_package("/Applications/Unity/Hub/Editor/6000.0.85f1/Unity.app/Contents/MacOS/Unity")
        self.assertTrue(mac.endswith("Unity.app/Contents/Resources/PackageManager/BuiltInPackages/com.unity.ugui/"
                                     "Package Resources/TMP Essential Resources.unitypackage"), mac)
        win = pass_tmp_essentials.essentials_package(r"C:\Program Files\Unity\Hub\Editor\6000.0.85f1\Editor\Unity.exe")
        self.assertIn("Data", win.replace("\\", "/").split("/"))
        self.assertTrue(win.replace("\\", "/").endswith("Editor/Data/Resources/PackageManager/BuiltInPackages/"
                                                        "com.unity.ugui/Package Resources/TMP Essential Resources.unitypackage"), win)

    def test_detect_wants_the_essentials(self):
        self.assertTrue(pass_tmp_essentials.detect(self.export, self.profile))

    def test_essentials_installed_with_the_games_shader_guid(self):
        pass_tmp_essentials.apply(self.export, self.profile)
        tmp = os.path.join(self.assets, "TextMesh Pro")
        self.assertEqual(read(os.path.join(tmp, "Shaders", "TMP_SDF.shader")), "package sdf")
        self.assertIn("guid: " + self.GAME_SDF, read(os.path.join(tmp, "Shaders", "TMP_SDF.shader.meta")))
        self.assertIn("guid: " + "b" * 32, read(os.path.join(tmp, "Shaders", "TMPro.cginc.meta")))
        self.assertEqual(read(os.path.join(tmp, "Resources", "TMP Settings.asset")), "settings")
        self.assertIn("folderAsset: yes", read(os.path.join(self.assets, "TextMesh Pro.meta")))

    def test_game_stub_leaves_and_other_shaders_stay(self):
        pass_tmp_essentials.apply(self.export, self.profile)
        shaders = os.path.join(self.assets, "Resources", "shaders")
        self.assertFalse(os.path.exists(os.path.join(shaders, "tmp_sdf.shader")))
        self.assertFalse(os.path.exists(os.path.join(shaders, "tmp_sdf.shader.meta")))
        self.assertTrue(os.path.exists(os.path.join(shaders, "other.shader")))

    def test_idempotent_and_verified(self):
        pass_tmp_essentials.apply(self.export, self.profile)
        self.assertEqual(pass_tmp_essentials.apply(self.export, self.profile)["changes_applied"], 0)
        self.assertTrue(pass_tmp_essentials.verify(self.export, self.profile)["passed"])
        self.assertIn("guid: " + self.GAME_SDF,
                      read(os.path.join(self.assets, "TextMesh Pro", "Shaders", "TMP_SDF.shader.meta")))

    def test_dry_run_changes_nothing(self):
        pass_tmp_essentials.apply(self.export, self.profile, dry_run=True)
        self.assertFalse(os.path.exists(os.path.join(self.assets, "TextMesh Pro")))
        self.assertTrue(os.path.exists(os.path.join(self.assets, "Resources", "shaders", "tmp_sdf.shader")))

    def test_project_without_tmp_needs_nothing(self):
        for f in os.listdir(os.path.join(self.assets, "Resources", "shaders")):
            if f.startswith("tmp_"):
                os.remove(os.path.join(self.assets, "Resources", "shaders", f))
        nowhere = {"unity": os.path.join(self.tmp, "nowhere", "Unity")}
        self.assertEqual(pass_tmp_essentials.detect(self.export, nowhere), [])
        self.assertEqual(pass_tmp_essentials.apply(self.export, nowhere)["changes_applied"], 0)

    def test_no_unity_is_a_clear_failure(self):
        res = pass_tmp_essentials.verify(self.export, {"unity": os.path.join(self.tmp, "nowhere", "Unity")})
        self.assertFalse(res["passed"])
        self.assertTrue(any("TMP Essential Resources" in d for d in res["details"]), res["details"])


class TestRebindingUi(Project):
    def setUp(self):
        super().setUp()
        self.work = os.path.join(self.tmp, "work")
        self.tgz = os.path.join(self.tmp, "com.unity.inputsystem-1.20.0.tgz")
        with tarfile.open(self.tgz, "w:gz") as tar:
            add(tar, "package/Samples~/RebindingUI/RebindActionUI.cs", "class RebindActionUI {}")
            add(tar, "package/Samples~/RebindingUI/InputActionExtensions.cs", "static class InputActionExtensions {}")
            add(tar, "package/Samples~/RebindingUI/RebindSaveLoad.cs", "not wanted")
        with open(self.tgz, "rb") as fh:
            self.sha = hashlib.sha256(fh.read()).hexdigest()
        self.profile = {"work": self.work}

    def fake_download(self, url, dest):
        self.urls.append(url)
        shutil.copy(self.tgz, dest)

    def apply(self, sha=None):
        self.urls = []
        with mock.patch.object(pass_rebinding_ui, "PACKAGE_SHA256", sha or self.sha), \
                mock.patch.object(pass_rebinding_ui, "download", self.fake_download):
            return pass_rebinding_ui.apply(self.export, self.profile)

    def test_detect_wants_the_sample(self):
        self.assertTrue(pass_rebinding_ui.detect(self.export, self.profile))

    def test_sample_copied_with_fixed_guids(self):
        self.apply()
        folder = os.path.join(self.assets, "Scripts", "RebindingUI")
        self.assertEqual(sorted(f for f in os.listdir(folder) if f.endswith(".cs")),
                         ["InputActionExtensions.cs", "RebindActionUI.cs"])
        self.assertIn("guid: " + pass_rebinding_ui.REBIND_ACTION_UI_GUID, read(os.path.join(folder, "RebindActionUI.cs.meta")))
        self.assertIn("guid: " + pass_rebinding_ui.EXTENSIONS_GUID, read(os.path.join(folder, "InputActionExtensions.cs.meta")))
        self.assertEqual(self.urls, [pass_rebinding_ui.PACKAGE_URL])
        self.assertTrue(pass_rebinding_ui.verify(self.export, self.profile)["passed"])

    def test_package_downloaded_once(self):
        self.apply()
        shutil.rmtree(os.path.join(self.assets, "Scripts"))
        self.apply()
        self.assertEqual(self.urls, [])
        self.assertTrue(os.path.exists(os.path.join(self.assets, "Scripts", "RebindingUI", "RebindActionUI.cs")))

    def test_wrong_download_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.apply(sha="0" * 64)
        self.assertFalse(os.path.exists(os.path.join(self.assets, "Scripts", "RebindingUI", "RebindActionUI.cs")))
        self.assertFalse(os.listdir(os.path.join(self.work, "cache")) if os.path.isdir(os.path.join(self.work, "cache")) else [])

    def test_project_package_cache_needs_no_download(self):
        sample = os.path.join(self.export, "Library", "PackageCache", "com.unity.inputsystem@7a4e1a2a8194", "Samples~", "RebindingUI")
        write(os.path.join(sample, "RebindActionUI.cs"), "class RebindActionUI {}")
        write(os.path.join(sample, "InputActionExtensions.cs"), "static class InputActionExtensions {}")
        write(os.path.join(sample, "..", "..", "package.json"), json.dumps({"version": "1.20.0"}))
        self.apply()
        self.assertEqual(self.urls, [])
        self.assertTrue(pass_rebinding_ui.verify(self.export, self.profile)["passed"])



class TestFilesystemRedirectOnTheRealLines(Project):
    """The lines as AssetRipper decompiles them. The 2026-10-27 project's Save.cs had been edited by hand before the
    pass existed, so these were never run through it (LESSONS 31)."""

    def setUp(self):
        super().setUp()
        scripts = os.path.join(self.assets, "Scripts", "Assembly-CSharp")
        self.save = os.path.join(scripts, "Save.cs")
        write(self.save, '\t\tFileStream fileStream = new FileStream(Application.dataPath + "/SAVE_" + Save_Slot + '
                         '".MIDNIGHT", FileMode.Create);\n'
                         '\t\tstring path = Application.dataPath + "/SAVE_" + Save_Slot + ".MIDNIGHT";\n')
        self.menus = os.path.join(scripts, "Menus.cs")
        write(self.menus, '\t\t\tApplication.OpenURL(Application.dataPath + "/Resources/BINDINGS.txt");\n')

    def test_file_mode_stays_outside_the_save_path(self):
        pass_filesystem_redirect.apply(self.export)
        text = read(self.save)
        self.assertIn('new FileStream(Lunacid.VR.LunacidFileSystemHelper.GetSavePath("SAVE_" + Save_Slot + ".MIDNIGHT"), '
                      'FileMode.Create);', text)
        self.assertIn('string path = Lunacid.VR.LunacidFileSystemHelper.GetSavePath("SAVE_" + Save_Slot + ".MIDNIGHT");', text)

    def test_bindings_guard_added_once(self):
        pass_filesystem_redirect.apply(self.export)
        self.assertEqual(pass_filesystem_redirect.apply(self.export)["changes_applied"], 0)
        self.assertEqual(read(self.menus).count("RuntimePlatform.Android"), 1)


class TestScriptReferences(Project):
    """Unity names a script inside a DLL by fileID = the first 4 bytes of MD4("s\\0\\0\\0" + namespace + class).
    The fixed table had the wrong fileID and GUID for 13 of the 14 TMP classes (LESSONS 31); the numbers below are
    the ones AssetRipper wrote in the 2026-11-11 export and Unity 6's com.unity.ugui 2.0.0 .meta files."""

    def test_md4_and_file_ids(self):
        from core import unity_ids
        self.assertEqual(unity_ids.md4(b"abc").hex(), "a448017aaf21d8525fc10ae87aa6729d")
        self.assertEqual(unity_ids.script_file_id("TMPro", "TMP_FontAsset"), -667331979)
        self.assertEqual(unity_ids.script_file_id("TMPro", "TextMeshProUGUI"), 1453722849)
        self.assertEqual(unity_ids.script_file_id("UnityEngine.InputSystem.Samples.RebindUI", "RebindActionUI"), 781412291)

    def test_tmp_components_reach_the_ugui_package(self):
        tmp_dll = "67dfb1fdfb2b407222eda8e23ac8b724"
        write(os.path.join(self.assets, "Plugins", "Unity.TextMeshPro.dll"), b"dll")
        write(os.path.join(self.assets, "Plugins", "Unity.TextMeshPro.dll.meta"), meta(tmp_dll))
        expected = {-667331979: "71c1514a6bd24e1e882cebbe1904ce04",   # TMP_FontAsset
                    -806885394: "9541d86e2fd84c1d9990edf0852d74ab",   # TextMeshPro
                    -1620774994: "2da0c512f12947e489f739169773d7ca",  # TMP_InputField
                    1148083418: "7b743370ac3e4ec2a1668f5455a8ef8a",   # TMP_Dropdown
                    2108210716: "54d21f6ece3b46479f0c328f8c6007e0",   # TMP_ColorGradient
                    2019389346: "84a92b25f83d49b9bc132d206b370281",   # TMP_SpriteAsset
                    -1936749209: "ab2114bdc8544297b417dfefe9f1e410",  # TMP_StyleSheet
                    -395462249: "2705215ac5b84b70bacc50632be6e391",   # TMP_Settings
                    1453722849: "f4688fdb7df04437aeb418b961361dc5"}   # TextMeshProUGUI
        asset = os.path.join(self.assets, "MonoBehaviour", "fonts.asset")
        write(asset, "".join("  m_Script: {fileID: %d, guid: %s, type: 3}\n" % (f, tmp_dll) for f in expected))
        pass_legacy_dlls.apply(self.export)
        text = read(asset)
        for guid in expected.values():
            self.assertIn("m_Script: {fileID: 11500000, guid: %s, type: 3}" % guid, text)
        self.assertNotIn(tmp_dll, text)

    def test_table_matches_the_installed_packages(self):
        """Every target GUID is the .cs.meta of that class in the packages Unity resolved (skipped without them)."""
        import glob
        import re
        from core import config
        project = config.load().get("project") or ""
        caches = glob.glob(os.path.join(project, "Library", "PackageCache"))
        metas = {}
        for cache in caches:
            for m in glob.glob(os.path.join(cache, "com.unity.ugui@*", "**", "*.cs.meta"), recursive=True) + \
                    glob.glob(os.path.join(cache, "com.unity.inputsystem@*", "**", "*.cs.meta"), recursive=True):
                with open(m, encoding="utf-8") as fh:
                    metas.setdefault(os.path.basename(m)[:-8], set()).add(re.search(r"guid: (\w+)", fh.read()).group(1))
        if not metas:
            self.skipTest("no resolved com.unity.ugui / com.unity.inputsystem package on this machine")
        for ns, cls, guid in pass_legacy_dlls.PACKAGE_SCRIPTS:
            self.assertIn(guid, metas.get(cls, set()), cls)


RAW_UNLOCK = 'using Steamworks;\nusing UnityEngine;\n\npublic class Unlock_Achievement : MonoBehaviour\n{\n\tpublic string DEF_NAME;\n\n\tprivate void Start()\n\t{\n\t\tbool pbAchieved = false;\n\t\tSteamUserStats.GetAchievement(DEF_NAME, out pbAchieved);\n\t\tif (!pbAchieved)\n\t\t{\n\t\t\tSteamUserStats.SetAchievement(DEF_NAME);\n\t\t\tSteamUserStats.StoreStats();\n\t\t\tDebug.Log("Unlocked " + DEF_NAME);\n\t\t}\n\t}\n}\n'

GUARDED_UNLOCK = 'using Steamworks;\nusing UnityEngine;\n\npublic class Unlock_Achievement : MonoBehaviour\n{\n\tpublic string DEF_NAME;\n\n\tprivate void Start()\n\t{\n\t\ttry\n\t\t{\n\t\t\tbool pbAchieved = false;\n\t\t\tSteamUserStats.GetAchievement(DEF_NAME, out pbAchieved);\n\t\t\tif (!pbAchieved)\n\t\t\t{\n\t\t\t\tSteamUserStats.SetAchievement(DEF_NAME);\n\t\t\t\tSteamUserStats.StoreStats();\n\t\t\t\tDebug.Log("Unlocked " + DEF_NAME);\n\t\t\t}\n\t\t}\n\t\tcatch (System.Exception)\n\t\t{\n\t\t\t// Safe fallback for platforms without Steam (e.g. Android/Quest standalone)\n\t\t}\n\t}\n}\n'


class TestSteamGuard(Project):
    """Steam is not on the Quest: the achievement call throws. The 2026-10-27 project wrapped it by hand."""

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.assets, "Plugins", "Assembly-CSharp-firstpass", "Unlock_Achievement.cs")
        write(self.path, RAW_UNLOCK)

    def test_raw_script_becomes_the_projects(self):
        self.assertTrue(pass_steam_guard.detect(self.export))
        pass_steam_guard.apply(self.export)
        self.assertEqual(read(self.path), GUARDED_UNLOCK)
        self.assertTrue(pass_steam_guard.verify(self.export)["passed"])
        self.assertEqual(pass_steam_guard.apply(self.export)["changes_applied"], 0)

    def test_unknown_version_fails_clearly(self):
        write(self.path, RAW_UNLOCK.replace("StoreStats", "StoreStatsNow"))
        res = pass_steam_guard.verify(self.export)
        self.assertFalse(res["passed"])
        self.assertIn("unknown", res["details"][0])
        self.assertEqual(pass_steam_guard.apply(self.export)["changes_applied"], 0)


class TestRunnerHasThem(unittest.TestCase):
    def test_new_passes_run_after_the_dlls_go(self):
        from core import runner
        names = runner.PASS_NAMES
        self.assertIn("pass_tmp_essentials", names)
        self.assertIn("pass_rebinding_ui", names)
        self.assertIn("pass_steam_guard", names)
        self.assertLess(names.index("pass_legacy_dlls"), names.index("pass_rebinding_ui"))

    def test_passes_get_the_unity_path(self):
        from core import runner
        self.assertIn("unity", runner.CONFIG_KEYS)


if __name__ == "__main__":
    unittest.main()
