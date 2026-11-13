#!/usr/bin/env python3
"""
Unit tests for core/detect.py
"""

import os
import sys
import unittest
import tempfile
import shutil
from core.detect import detect_game

class TestDetectTool(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_detect_non_unity_folder(self):
        report = detect_game(self.test_dir)
        self.assertFalse(report["is_unity"])
        self.assertEqual(report["engine"], "Unknown")
        self.assertEqual(report["unity_version"], "desconhecida")

    def test_detect_synthetic_unity_game(self):
        # Create minimal synthetic Unity structure
        with open(os.path.join(self.test_dir, "UnityPlayer.dll"), "w") as f:
            f.write("mock")
        data_dir = os.path.join(self.test_dir, "Game_Data")
        os.makedirs(data_dir)

        # Mock globalgamemanagers with embedded version 2021.3.16f1
        with open(os.path.join(data_dir, "globalgamemanagers"), "wb") as f:
            f.write(b"\x00\x00\x00\x002021.3.16f1\x00\x00\x00")

        # Mock Managed dir with Assembly-CSharp and TextMeshPro
        managed_dir = os.path.join(data_dir, "Managed")
        os.makedirs(managed_dir)
        with open(os.path.join(managed_dir, "Assembly-CSharp.dll"), "wb") as f:
            f.write(b"mock assembly with I2.Loc and RetroLookPro strings")
        with open(os.path.join(managed_dir, "Unity.TextMeshPro.dll"), "w") as f:
            f.write("mock")

        # Mock level files
        with open(os.path.join(data_dir, "level0"), "w") as f:
            f.write("mock level")

        report = detect_game(self.test_dir)
        self.assertTrue(report["is_unity"])
        self.assertEqual(report["unity_version"], "2021.3.16f1")
        self.assertEqual(report["scripting_backend"], "Mono")
        self.assertEqual(report["render_pipeline"], "Built-in Render Pipeline")
        self.assertIn("TextMeshPro", report["packages"])
        self.assertIn("I2 Localization", report["third_party_assets"])
        self.assertIn("RetroLookPro", report["third_party_assets"])
        self.assertEqual(report["structure"]["levels_count"], 1)

    def test_ground_truth_lunacid_if_available(self):
        # The game folder is the parent of game_data in the machine configuration (core/config.py).
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from core import config
        data = config.load().get("game_data")
        lunacid_path = os.path.dirname(data) if data else ""
        if lunacid_path and os.path.exists(lunacid_path):
            report = detect_game(lunacid_path)
            self.assertTrue(report["is_unity"])
            self.assertEqual(report["unity_version"], "2020.3.4f1")
            self.assertEqual(report["scripting_backend"], "Mono")
            self.assertEqual(report["render_pipeline"], "Built-in Render Pipeline")
            self.assertIn("TextMeshPro", report["packages"])
            self.assertIn("Input System (New)", report["packages"])
            self.assertIn("I2 Localization", report["third_party_assets"])
            self.assertIn("Shader Forge", report["third_party_assets"])
            self.assertIn("Steamworks / Steam DRM", report["drm_and_protections"]["detected"])

if __name__ == "__main__":
    unittest.main()

