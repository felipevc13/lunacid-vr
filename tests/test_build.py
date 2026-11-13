#!/usr/bin/env python3
"""tools/build/build.py without running Unity: the command and environment it builds, and how it reads the log."""

import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "build"))
sys.path.insert(0, REPO)
import build  # noqa: E402
from core import runner  # noqa: E402


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.cfg = {"unity": "/opt/Unity", "project": "/p/ExportedProject", "builds": "/p/Builds", "work": "/w",
                    "android_sdk": "/sdk", "android_ndk": "/ndk", "jdk": "/jdk", "gradle_home": "/p/.gradle"}
        self.profile = runner.load_profile()

    def test_every_profile_scene_goes_in(self):
        cmd, env, scenes = build.plan(self.cfg, self.profile)
        self.assertEqual(len(scenes), self.profile["build_scenes_count"])      # 30: MainMenu and the 29 others
        extra = env["LUNA_EXTRA_SCENES"].split(",")
        self.assertEqual(len(extra), len(scenes) - 1)
        self.assertNotIn("MainMenu", extra)
        self.assertIn("DETHLAND", extra)

    def test_unity_updates_old_apis(self):
        """The decompiled scripts use Rigidbody.velocity/drag; the 2026-10-27 project got linearVelocity/linearDamping
        from Unity's API Updater, which batchmode runs only with -accept-apiupdate (LESSONS 31)."""
        cmd, _, _ = build.plan(self.cfg, self.profile)
        self.assertIn("-accept-apiupdate", cmd)

    def test_probe_run_updates_old_apis_too(self):
        """On a new machine the probe run can be the first Unity open of the project (LESSONS 32)."""
        with open(os.path.join(REPO, "tools", "editor_checks", "run_probe.sh"), encoding="utf-8") as fh:
            self.assertIn("-accept-apiupdate", fh.read())

    def test_unity_log_is_kept_with_the_build(self):
        """The 133-min full build's log was overwritten by the next fast build, so its phases could not be
        measured (LESSONS 33). Each build's log goes into its own folder."""
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "build_apk.log")
            out = os.path.join(tmp, "out")
            os.makedirs(out)
            with open(log, "w") as fh:
                fh.write("Compiling shader ...")
            build.keep_log(log, out)
            self.assertTrue(os.path.exists(os.path.join(out, "build_apk.log")))

    def test_variant_budget_warning(self):
        """A full build reports its shader variants against the profile's budget (LESSONS 34)."""
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "build_apk.log")
            with open(log, "w") as fh:
                fh.write('Compiling shader "Particles/Standard Unlit" pass "" (vp)\n'
                         '    After scriptable stripping: 95000\n')
            self.assertIn("95000", build.variant_warning(log, {"shader_variant_budget": 90000}))
            self.assertEqual(build.variant_warning(log, {"shader_variant_budget": 100000}), "")
            self.assertEqual(build.variant_warning(log, {}), "")

    def test_full_and_fast(self):
        _, full, _ = build.plan(self.cfg, self.profile)
        _, fast, _ = build.plan(self.cfg, self.profile, fast=True)
        self.assertNotIn("LUNA_SCRIPTS_ONLY", full)
        self.assertEqual(fast["LUNA_SCRIPTS_ONLY"], "1")
        self.assertEqual(full["LUNA_SPLIT_OBB"], "1")

    def test_machine_paths_reach_unity(self):
        cmd, env, _ = build.plan(self.cfg, self.profile)
        self.assertEqual(cmd[0], "/opt/Unity")
        self.assertIn("ConfigureAndroidAndBuild.BuildMainMenuOnly", cmd)
        self.assertEqual(cmd[cmd.index("-projectPath") + 1], "/p/ExportedProject")
        for key, value in (("LUNA_ANDROID_SDK", "/sdk"), ("LUNA_ANDROID_NDK", "/ndk"), ("LUNA_JDK", "/jdk"),
                           ("LUNA_BUILDS", "/p/Builds"), ("LUNA_GRADLE_HOME", "/p/.gradle")):
            self.assertEqual(env[key], value)

    def test_log_checks(self):
        scenes = ["MainMenu", "A", "B"]
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
            fh.write("  [Scene 01/3] x\n  [Scene 02/3] y\n  [Scene 3/3] z\n")
            ok = fh.name
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
            fh.write("Assets/X.cs(1,2): error CS0103: nope\n  [Scene 01/3] x\n")
            bad = fh.name
        try:
            self.assertEqual(build.check_log(ok, scenes), [])
            problems = build.check_log(bad, scenes)
            self.assertTrue(any("compile errors" in p for p in problems))
            self.assertTrue(any("all 3 scenes" in p for p in problems))
        finally:
            os.remove(ok); os.remove(bad)


if __name__ == "__main__":
    unittest.main()
