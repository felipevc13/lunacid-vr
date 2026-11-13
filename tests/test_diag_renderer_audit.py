#!/usr/bin/env python3
"""
Tests for the disposable renderer-audit diagnostic pass.
Checks apply / idempotency / clean / verify and basic consistency of the generated Unity files.
"""

import os
import re
import shutil
import tempfile
import unittest

from passes import pass_diag_renderer_audit as audit


class TestDiagRendererAudit(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_apply_is_idempotent_and_clean_removes_everything(self):
        self.assertTrue(audit.detect(self.dir))
        dry = audit.apply(self.dir, dry_run=True)
        self.assertEqual(dry["changes_applied"], len(audit.FILES))
        self.assertFalse(os.path.exists(os.path.join(self.dir, audit.AUDIT_REL_PATH)))

        first = audit.apply(self.dir)
        self.assertEqual(first["changes_applied"], len(audit.FILES))
        self.assertTrue(audit.verify(self.dir)["passed"])
        self.assertEqual(audit.detect(self.dir), [])
        self.assertEqual(audit.apply(self.dir)["changes_applied"], 0)

        removed = audit.clean(self.dir)
        self.assertEqual(removed["changes_applied"], len(audit.FILES))
        self.assertFalse(audit.verify(self.dir)["passed"])

    def test_guids_are_unique_and_do_not_collide_with_probe(self):
        guids = {audit.SHADER_GUID, audit.MAT_GUID, audit.AUDIT_GUID}
        self.assertEqual(len(guids), 3)
        for g in guids:
            self.assertEqual(len(g), 32)
            self.assertNotIn(g, {"d1a90000000000000000000000000001",
                                 "d1a90000000000000000000000000002",
                                 "d1a90000000000000000000000000003"})
        self.assertIn(audit.SHADER_GUID, audit.SHADER_META_CONTENT)
        self.assertIn(audit.MAT_GUID, audit.MAT_META_CONTENT)
        self.assertIn(audit.AUDIT_GUID, audit.AUDIT_META_CONTENT)
        self.assertIn(audit.SHADER_GUID, audit.MAT_CONTENT)

    def test_csharp_is_structurally_sound(self):
        src = audit.AUDIT_CONTENT
        stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        stripped = re.sub(r"//[^\n]*", "", stripped)
        self.assertEqual(stripped.count("{"), stripped.count("}"))
        self.assertEqual(stripped.count("("), stripped.count(")"))
        for stage in ("baseline", "pp_off", "legacy_flat", "all_flat", "final"):
            self.assertIn("STAGE_DONE " + stage, src)
        # Must not depend on Debug.Log alone: JNI logcat + file sinks are the reliable channels.
        self.assertIn('AndroidJavaClass("android.util.Log")', src)
        self.assertIn("persistentDataPath", src)
        # Resources.Load name must match the generated material name.
        self.assertIn('Resources.Load<Material>("DiagFlatTex")', src)
        self.assertIn("m_Name: DiagFlatTex", audit.MAT_CONTENT)
        self.assertIn('Shader "Diag/FlatTex"', audit.SHADER_CONTENT)


if __name__ == "__main__":
    unittest.main()
