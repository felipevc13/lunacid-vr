#!/usr/bin/env python3
"""tools/extract/assetripper.py without running AssetRipper: how it starts the process."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "extract"))
import assetripper  # noqa: E402


class Started(Exception):
    pass


class TestAssetRipperProcess(unittest.TestCase):
    def test_output_never_goes_to_an_unread_pipe(self):
        """AssetRipper writes a line per exported asset. A pipe nobody reads fills at 64 KB and the export
        stops for good, near asset 900 of 7297 (2026-11-11, LESSONS 31)."""
        seen = {}

        def fake_popen(cmd, **kwargs):
            seen.update(kwargs)
            raise Started()

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assetripper.subprocess, "Popen", fake_popen):
            with self.assertRaises(Started):
                assetripper.export(os.path.join(tmp, "AssetRipper.GUI.Free"), tmp, os.path.join(tmp, "out"))
        self.assertIn("stdout", seen)
        self.assertNotEqual(seen["stdout"], subprocess.PIPE)
        self.assertNotEqual(seen.get("stderr"), subprocess.PIPE)


class TestAssetRipperSettings(unittest.TestCase):
    """AssetRipper 2.0.0 reads a setting like an HTML checkbox: the key present means on, whatever its value.
    Sending "false" switched PreferOriginalTextureExtension on, and 87 DLC textures came out .tga (LESSONS 31)."""

    def test_false_settings_are_left_out_of_the_form(self):
        fields = assetripper.form_fields(assetripper.SETTINGS)
        for key, value in assetripper.SETTINGS.items():
            if value == "false":
                self.assertNotIn(key, fields)

    def test_true_and_other_settings_are_sent(self):
        fields = assetripper.form_fields({"A": "true", "B": "false", "C": "Exr"})
        self.assertEqual(fields, {"A": "true", "C": "Exr"})

    def test_log_with_a_wrong_setting_is_a_failure(self):
        log = "General : PreferOriginalTextureExtension: True\nGeneral : LightmapTextureExportFormat: Exr\n"
        wrong = assetripper.wrong_settings(log, {"PreferOriginalTextureExtension": "false",
                                                 "LightmapTextureExportFormat": "Exr"})
        self.assertEqual(wrong, ["PreferOriginalTextureExtension"])

    def test_log_with_every_setting_right(self):
        log = "General : PreferOriginalTextureExtension: False\nGeneral : LightmapTextureExportFormat: Exr\n"
        self.assertEqual(assetripper.wrong_settings(log, {"PreferOriginalTextureExtension": "false",
                                                          "LightmapTextureExportFormat": "Exr"}), [])


if __name__ == "__main__":
    unittest.main()
