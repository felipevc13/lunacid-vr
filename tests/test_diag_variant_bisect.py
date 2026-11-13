#!/usr/bin/env python3
"""
Tests for the disposable variant-bisect diagnostic pass.
"""

import os
import re
import shutil
import tempfile
import unittest

from passes import pass_diag_variant_bisect as bisect
from passes import pass_diag_lit_probe as lit
from passes import pass_diag_renderer_audit as audit


class TestDiagVariantBisect(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_apply_is_idempotent_and_clean_removes_everything(self):
        total = len(bisect.all_files())
        self.assertEqual(total, 8 * 4 + 2)
        self.assertTrue(bisect.detect(self.dir))
        self.assertEqual(bisect.apply(self.dir, dry_run=True)["changes_applied"], total)
        self.assertFalse(os.path.exists(os.path.join(self.dir, bisect.PROBE_REL_PATH)))
        self.assertEqual(bisect.apply(self.dir)["changes_applied"], total)
        self.assertTrue(bisect.verify(self.dir)["passed"])
        self.assertEqual(bisect.apply(self.dir)["changes_applied"], 0)
        self.assertEqual(bisect.clean(self.dir)["changes_applied"], total)
        self.assertFalse(bisect.verify(self.dir)["passed"])

    def test_guids_unique_and_32_hex(self):
        guids = [bisect.PROBE_GUID]
        for i in range(1, 9):
            guids += [bisect.shader_guid(i), bisect.mat_guid(i)]
        self.assertEqual(len(guids), len(set(guids)))
        other = {lit.SHADER_GUID, lit.MAT_GUID, lit.PROBE_GUID,
                 audit.SHADER_GUID, audit.MAT_GUID, audit.AUDIT_GUID,
                 "d1a90000000000000000000000000001", "d1a90000000000000000000000000002",
                 "d1a90000000000000000000000000003"}
        for g in guids:
            self.assertRegex(g, r"^[0-9a-f]{32}$")
            self.assertNotIn(g, other)
        for i in range(1, 9):
            self.assertIn(bisect.shader_guid(i), bisect.build_mat(i))

    def test_each_variant_has_exactly_its_factors(self):
        for v in bisect.VARIANTS:
            i, _slug, _label, tag, fog, fwdbase, lightmap = v
            src = bisect.build_shader(v)
            self.assertEqual('"LightMode"="ForwardBase"' in src, tag, i)
            self.assertEqual("multi_compile_fog" in src, fog, i)
            self.assertEqual("multi_compile_fwdbase_fullshadows" in src, fwdbase, i)
            self.assertEqual("LIGHTMAP_ON" in src, lightmap, i)
            self.assertIn('Shader "Diag/V%d_' % i, src)
            self.assertIn("* 0.8 + 0.2", src)  # never pure black
        # stage 1 is the control: no factor at all; stage 8 is the full real-Object structure
        self.assertEqual(bisect.VARIANTS[0][3:], (False, False, False, False))
        self.assertEqual(bisect.VARIANTS[7][3:], (True, True, True, True))

    def test_csharp_consistent(self):
        src = bisect.PROBE_CONTENT
        stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        stripped = re.sub(r"//[^\n]*", "", stripped)
        self.assertEqual(stripped.count("{"), stripped.count("}"))
        self.assertEqual(stripped.count("("), stripped.count(")"))
        labels = re.findall(r'new Stage\("([A-B0]\d?) ', src)
        self.assertEqual(labels, ["0", "A1", "A2", "A3", "A4", "B2", "B3", "B4", "B5", "B6", "B7", "B8"])
        self.assertIn('Resources.Load<Material>("DiagV" + i)', src)
        self.assertIn("void OnGUI()", src)
        self.assertIn('AndroidJavaClass("android.util.Log")', src)
        # every shader index used by a stage exists
        for sh in re.findall(r'new Stage\("[^"]+", (\d), ', src):
            self.assertIn(int(sh), range(0, 9))

if __name__ == "__main__":
    unittest.main()
