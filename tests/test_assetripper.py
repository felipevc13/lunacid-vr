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


class TestWindowsNotebook(unittest.TestCase):
    """2026-11-13 on Windows: our console log was inside the export folder; AssetRipper deletes that folder before
    exporting, Windows cannot delete an open file ('The process cannot access the file assetripper_console.log
    because it is being used by another process'), the export failed, and the script waited for nothing."""

    def test_console_log_is_outside_the_folder_assetripper_deletes(self):
        seen = {}

        def fake_popen(cmd, **kwargs):
            seen["log"] = kwargs["stdout"].name
            raise Started()

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assetripper.subprocess, "Popen", fake_popen):
            out = os.path.join(tmp, "work", "project")
            with self.assertRaises(Started):
                assetripper.export(os.path.join(tmp, "AssetRipper.GUI.Free"), tmp, out)
        self.assertFalse(os.path.abspath(seen["log"]).startswith(os.path.abspath(out) + os.sep), seen["log"])

    def test_an_error_in_assetrippers_log_stops_the_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "AssetRipper_x.log")
            with open(log, "w") as fh:
                fh.write("Processing : Finished processing assets\n[Error] : System.IO.IOException: The process "
                         "cannot access the file 'assetripper_console.log' because it is being used\n")
            proc = mock.Mock()
            proc.poll.return_value = None
            with self.assertRaises(RuntimeError) as ctx:
                assetripper.wait_line(log, "Finished post-export", proc, limit_s=60)
            self.assertIn("IOException", str(ctx.exception))

    def test_a_finished_export_is_marked_and_a_half_one_is_put_aside(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "project")
            half = os.path.join(out, "ExportedProject", "Assets")
            os.makedirs(half)
            self.assertFalse(assetripper.is_complete(os.path.join(out, "ExportedProject")))
            aside = assetripper.put_aside_incomplete(out)
            self.assertTrue(os.path.isdir(os.path.join(aside, "Assets")))           # kept, not deleted
            self.assertFalse(os.path.exists(os.path.join(out, "ExportedProject")))
            os.makedirs(os.path.join(out, "ExportedProject", "Assets"))
            assetripper.mark_complete(os.path.join(out, "ExportedProject"))
            self.assertTrue(assetripper.is_complete(os.path.join(out, "ExportedProject")))
            self.assertIsNone(assetripper.put_aside_incomplete(out))                 # a complete one stays

    def test_a_project_unity_already_opened_counts_as_complete(self):
        # The projects made before the mark existed have been opened by Unity: they have a Library folder.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "Assets"))
            os.makedirs(os.path.join(tmp, "Library"))
            self.assertTrue(assetripper.is_complete(tmp))


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
