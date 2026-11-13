#!/usr/bin/env python3
"""
Tests for the disposable lit-shader probe diagnostic pass.
"""

import os
import re
import shutil
import tempfile
import unittest

from passes import pass_diag_lit_probe as probe
from passes import pass_diag_renderer_audit as audit


class TestDiagLitProbe(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_apply_is_idempotent_and_clean_removes_everything(self):
        self.assertTrue(probe.detect(self.dir))
        self.assertEqual(probe.apply(self.dir, dry_run=True)["changes_applied"], len(probe.FILES))
        self.assertFalse(os.path.exists(os.path.join(self.dir, probe.PROBE_REL_PATH)))
        self.assertEqual(probe.apply(self.dir)["changes_applied"], len(probe.FILES))
        self.assertTrue(probe.verify(self.dir)["passed"])
        self.assertEqual(probe.apply(self.dir)["changes_applied"], 0)
        self.assertEqual(probe.clean(self.dir)["changes_applied"], len(probe.FILES))
        self.assertFalse(probe.verify(self.dir)["passed"])

    def test_guids_do_not_collide_with_other_diag_passes(self):
        mine = {probe.SHADER_GUID, probe.MAT_GUID, probe.PROBE_GUID}
        theirs = {audit.SHADER_GUID, audit.MAT_GUID, audit.AUDIT_GUID,
                  "d1a90000000000000000000000000001",
                  "d1a90000000000000000000000000002",
                  "d1a90000000000000000000000000003"}
        self.assertEqual(len(mine), 3)
        self.assertFalse(mine & theirs)
        self.assertIn(probe.SHADER_GUID, probe.MAT_CONTENT)

    def test_csharp_stages_match_shader_modes(self):
        src = probe.PROBE_CONTENT
        stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        stripped = re.sub(r"//[^\n]*", "", stripped)
        self.assertEqual(stripped.count("{"), stripped.count("}"))
        self.assertEqual(stripped.count("("), stripped.count(")"))
        self.assertIn('Resources.Load<Material>("DiagLitViz")', src)
        self.assertIn("m_Name: DiagLitViz", probe.MAT_CONTENT)
        self.assertIn('Shader "Diag/LitViz"', probe.SHADER_CONTENT)
        self.assertIn("STAGE_DONE final", src)
        # Every mode the C# can set must have a branch in the shader.
        modes = {int(m) for m in re.findall(r'new Stage\("viz_[a-z_]+", (\d+)\)', src)}
        self.assertEqual(len(modes), 10)
        for m in modes:
            self.assertRegex(probe.SHADER_CONTENT, r"m == %d\b" % m)
        # Stage names must satisfy the capture script's `[a-z_]+` marker regex.
        for name in re.findall(r'new Stage\("(viz_[^"]+)"', src):
            self.assertRegex(name, r"^[a-z_]+$")
        # ForwardBase tag is required for _LightColor0 / SH to be populated like the real Object shader.
        self.assertIn('"LightMode"="ForwardBase"', probe.SHADER_CONTENT)
        self.assertIn("multi_compile_fwdbase_fullshadows", probe.SHADER_CONTENT)


if __name__ == "__main__":
    unittest.main()
