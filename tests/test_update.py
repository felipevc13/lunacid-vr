#!/usr/bin/env python3
"""Updating is pasting the same line again (Felipe, 2026-11-13: everything chewed for a complete layperson).

setup.ps1 / setup.sh already pull the new version. Every build records the commit it came from; `start` compares
it with the code now and builds again when the code is newer, choosing the fast build (port code only, 25-45 min)
or the full one (shaders, assets, scene passes, 1-2 h) from the files that changed. The person decides nothing."""

import json
import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "build"))
import lunacid_vr  # noqa: E402
import build  # noqa: E402


class TestWhatChanged(unittest.TestCase):
    def test_nothing_that_goes_into_the_game(self):
        self.assertIsNone(lunacid_vr.rebuild_kind(["README.md", "docs/SETUP_WINDOWS.md", "tests/test_start.py",
                                                    "lunacid_vr.py", "setup.ps1", "tools/setup/setup_machine.py"]))

    def test_licence_texts_need_no_build(self):
        self.assertIsNone(lunacid_vr.rebuild_kind(["tools/shader_gen/uscs/patches/LICENSE", "LICENSE"]))

    def test_port_code_only_is_a_fast_build(self):
        self.assertEqual(lunacid_vr.rebuild_kind(["tools/vr/LunaVRRuntime.cs", "README.md"]), "fast")
        self.assertEqual(lunacid_vr.rebuild_kind(["passes/pass_vr_runtime.py"]), "fast")

    def test_shaders_assets_or_scene_passes_are_a_full_build(self):
        for f in ("shaders/Lunacid_VR_Fallback.shader", "tools/shader_gen/rules/Shader Forge_Object.json",
                  "passes/pass_material_floats.py", "games/lunacid.json"):
            self.assertEqual(lunacid_vr.rebuild_kind([f]), "full", f)

    def test_full_wins_over_fast(self):
        self.assertEqual(lunacid_vr.rebuild_kind(["tools/vr/LunaVRRuntime.cs", "passes/pass_msaa.py"]), "full")

    def test_a_file_it_does_not_know_is_a_full_build(self):
        # Safer to spend an hour than to install a game built from old assets.
        self.assertEqual(lunacid_vr.rebuild_kind(["something/new.bin"]), "full")


class TestIsABuildNeeded(unittest.TestCase):
    def test_same_code_as_the_last_build(self):
        self.assertIsNone(lunacid_vr.build_needed("abc", "abc", diff=lambda a, b: self.fail("no diff needed")))

    def test_newer_code(self):
        self.assertEqual(lunacid_vr.build_needed("old", "new", diff=lambda a, b: ["tools/vr/LunaVRRuntime.cs"]),
                         "fast")

    def test_no_build_yet(self):
        self.assertEqual(lunacid_vr.build_needed(None, "new", diff=lambda a, b: []), "full")

    def test_a_build_without_a_record_is_built_again_in_full(self):
        self.assertEqual(lunacid_vr.build_needed("unknown", "new", diff=lambda a, b: None), "full")

    def test_not_a_git_copy_keeps_the_build_it_has(self):
        self.assertIsNone(lunacid_vr.build_needed("old", None, diff=lambda a, b: ["x"]))


class TestEveryBuildRecordsItsCode(unittest.TestCase):
    def test_build_json_beside_the_apk(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        build.write_build_info(tmp, "0123abc", fast=True)
        with open(os.path.join(tmp, "build.json"), encoding="utf-8") as fh:
            info = json.load(fh)
        self.assertEqual(info["commit"], "0123abc")
        self.assertEqual(info["kind"], "fast")

    def test_last_build_commit(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        folder = os.path.join(tmp, "builds", "20261113_1500")
        os.makedirs(folder)
        open(os.path.join(folder, "Lunacid_Quest.apk"), "w").close()
        self.assertEqual(lunacid_vr.last_build_commit({"work": tmp}), "unknown")   # built before records existed
        build.write_build_info(folder, "0123abc", fast=False)
        self.assertEqual(lunacid_vr.last_build_commit({"work": tmp}), "0123abc")
        self.assertIsNone(lunacid_vr.last_build_commit({"work": os.path.join(tmp, "none")}))


if __name__ == "__main__":
    unittest.main()
