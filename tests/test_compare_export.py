#!/usr/bin/env python3
"""tools/extract/compare_export.py: a fresh AssetRipper export against the port's project, on made-up folders."""

import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "extract"))
import compare_export as ce  # noqa: E402


def write(root, rel, data):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode())


def meta(guid):
    return "fileFormatVersion: 2\nguid: %s\nTextureImporter:\n  serializedVersion: 12\n" % guid


class TestCompareExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.export = os.path.join(self.tmp.name, "export")
        self.project = os.path.join(self.tmp.name, "project")
        for root in (self.export, self.project):
            write(root, "Assets/Texture2D/a.png", b"png-a")
            write(root, "Assets/Texture2D/a.png.meta", meta("a" * 32))
            write(root, "Assets/Mesh/m.asset", "mesh")
            write(root, "Assets/Mesh/m.asset.meta", meta("b" * 32))
            write(root, "Assets/AudioClip/s.ogg", b"ogg")
            write(root, "Assets/AudioClip/s.ogg.meta", meta("c" * 32))
            write(root, "Assets/Material/x.mat", "mat")

    def tearDown(self):
        self.tmp.cleanup()

    def test_identical_projects_have_no_difference(self):
        report = ce.compare(self.export, self.project)
        self.assertEqual(ce.unexplained(report), [])
        self.assertEqual(report["content"]["Texture2D"]["same"], 1)

    def test_counts_ignore_meta_files(self):
        counts = ce.folder_counts(os.path.join(self.project, "Assets"))
        self.assertEqual(counts["Texture2D"], 1)
        self.assertEqual(counts["Material"], 1)

    def test_changed_texture_is_reported(self):
        write(self.project, "Assets/Texture2D/a.png", b"png-changed")
        problems = ce.unexplained(ce.compare(self.export, self.project))
        self.assertTrue(any("Texture2D/a.png" in p for p in problems), problems)

    def test_missing_mesh_is_reported(self):
        os.remove(os.path.join(self.export, "Assets/Mesh/m.asset"))
        problems = ce.unexplained(ce.compare(self.export, self.project))
        self.assertTrue(any("Mesh" in p for p in problems), problems)

    def test_changed_guid_is_counted_but_not_a_failure(self):
        """AssetRipper 2.0.0 gives new GUIDs on every export (2026-11-11: all 3362 differed, each export
        consistent with itself), so only the bytes have to match."""
        write(self.project, "Assets/AudioClip/s.ogg.meta", meta("d" * 32))
        report = ce.compare(self.export, self.project)
        self.assertEqual(report["content"]["AudioClip"]["guid"], ["s.ogg"])
        self.assertEqual(ce.unexplained(report), [])

    def test_texture_with_another_extension_is_reported(self):
        """PreferOriginalTextureExtension on made 87 DLC textures .tga instead of .png (LESSONS 31)."""
        os.rename(os.path.join(self.export, "Assets/Texture2D/a.png"), os.path.join(self.export, "Assets/Texture2D/a.tga"))
        problems = ce.unexplained(ce.compare(self.export, self.project))
        self.assertTrue(any("a.tga" in p for p in problems), problems)

    def test_meta_rewritten_by_unity_with_same_guid_is_fine(self):
        write(self.project, "Assets/Texture2D/a.png.meta", meta("a" * 32) + "  mipmaps: 1\n")
        self.assertEqual(ce.unexplained(ce.compare(self.export, self.project)), [])

    def test_folder_the_passes_write_may_differ(self):
        write(self.project, "Assets/Editor/ConfigureAndroidAndBuild.cs", "port")
        report = ce.compare(self.export, self.project)
        self.assertEqual(ce.unexplained(report), [])
        self.assertIn("Editor", report["counts_explained"])

    def test_other_folder_count_difference_is_reported(self):
        write(self.project, "Assets/Material/y.mat", "mat")
        problems = ce.unexplained(ce.compare(self.export, self.project))
        self.assertTrue(any("Material" in p for p in problems), problems)


class TestDeepCompare(unittest.TestCase):
    """Every text asset, with the export's GUIDs translated to the project's through the .meta at the same path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.export = os.path.join(self.tmp.name, "export")
        self.project = os.path.join(self.tmp.name, "project")
        write(self.export, "Assets/Texture2D/a.png.meta", meta("a" * 32))
        write(self.project, "Assets/Texture2D/a.png.meta", meta("1" * 32))
        write(self.export, "Assets/Material/x.mat", "  _MainTex: {fileID: 2800000, guid: %s, type: 3}\n  _Clip: 0\n" % ("a" * 32))
        write(self.project, "Assets/Material/x.mat", "  _MainTex: {fileID: 2800000, guid: %s, type: 3}\n  _Clip: 0\n" % ("1" * 32))

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_asset_with_other_guids_is_equal(self):
        res = ce.compare_text(self.export, self.project)
        self.assertEqual(res["different"], {})
        self.assertEqual(res["same"], 1)

    def test_changed_value_is_reported(self):
        write(self.project, "Assets/Material/x.mat", "  _MainTex: {fileID: 2800000, guid: %s, type: 3}\n  _Clip: 1\n" % ("1" * 32))
        res = ce.compare_text(self.export, self.project)
        self.assertEqual(res["different"], {"Material": ["Assets/Material/x.mat"]})

    def test_reference_to_another_texture_is_reported(self):
        write(self.export, "Assets/Texture2D/b.png.meta", meta("b" * 32))
        write(self.project, "Assets/Texture2D/b.png.meta", meta("2" * 32))
        write(self.project, "Assets/Material/x.mat", "  _MainTex: {fileID: 2800000, guid: %s, type: 3}\n  _Clip: 0\n" % ("2" * 32))
        self.assertIn("Material", ce.compare_text(self.export, self.project)["different"])


if __name__ == "__main__":
    unittest.main()
