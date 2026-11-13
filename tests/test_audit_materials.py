#!/usr/bin/env python3
"""
Tests for the static material/shader audit.
"""

import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import audit_materials as am  # noqa: E402

from passes import pass_shader_stubs


def _png(path, rgba):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(rgba) * 2 for _ in range(2))
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _meta(path, guid):
    with open(path + ".meta", "w") as fh:
        fh.write("fileFormatVersion: 2\nguid: %s\n" % guid)


MAT = """%%YAML 1.1
--- !u!21 &2100000
Material:
  m_Name: %(name)s
  m_Shader: {fileID: 4800000, guid: %(shader)s, type: 3}
  m_ShaderKeywords:
  m_CustomRenderQueue: %(queue)d
  m_SavedProperties:
    serializedVersion: 3
    m_TexEnvs:
      _MainTex:
        m_Texture: {fileID: 2800000, guid: %(tex)s, type: 3}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}
    m_Floats:
      _Cutoff: %(cutoff)s
      _Mode: 0
    m_Colors:
      _Color: {r: 1, g: 1, b: 1, a: 1}
"""


class TestAuditMaterials(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.assets = os.path.join(self.dir, "Assets")
        for d in ("Shader", "Material", "Texture2D", "Scenes"):
            os.makedirs(os.path.join(self.assets, d))
        good = pass_shader_stubs._build_shader_body("Unlit/MenuPainting", "unlit")
        stale = good.replace("clip(", "(void)(")
        for name, body, guid in (("Good", good, "a" * 32), ("Stale", stale, "b" * 32)):
            p = os.path.join(self.assets, "Shader", name + ".shader")
            with open(p, "w") as fh:
                fh.write(body)
            _meta(p, guid)
        _png(os.path.join(self.assets, "Texture2D", "masked.png"), (10, 20, 30, 0))
        _meta(os.path.join(self.assets, "Texture2D", "masked.png"), "c" * 32)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _mat(self, name, shader, cutoff="0.5", queue=-1, guid=None):
        p = os.path.join(self.assets, "Material", name + ".mat")
        with open(p, "w") as fh:
            fh.write(MAT % {"name": name, "shader": shader, "tex": "c" * 32, "cutoff": cutoff, "queue": queue})
        _meta(p, guid or (name.encode().hex() + "0" * 32)[:32])

    def test_flags_menupaint_regression_only_on_stale_shader(self):
        self._mat("OnStale", "b" * 32, guid="1" * 32)
        self._mat("OnGood", "a" * 32, guid="2" * 32)
        with open(os.path.join(self.assets, "Scenes", "MainMenu.unity"), "w") as fh:
            fh.write("m_Materials:\n  - {fileID: 2100000, guid: %s, type: 2}\n" % ("1" * 32))
        found = am.audit(self.dir, ffmpeg=None)
        cut = [f for f in found if f["check"] == "CUTOUT_LOST"]
        self.assertEqual([f["material"] for f in cut], ["OnStale"])
        self.assertEqual(cut[0]["scenes"], ["MainMenu"])

    def test_transparent_queue_on_opaque_shader(self):
        self._mat("Glass", "b" * 32, cutoff="0", queue=3000)
        checks = {f["check"] for f in am.audit(self.dir, with_scenes=False)}
        self.assertIn("TRANSPARENT_LOST", checks)

    def test_builtin_and_missing(self):
        self._mat("Builtin", "0000000000000000f000000000000000")
        self._mat("Gone", "d" * 32)
        by = {f["material"]: f["check"] for f in am.audit(self.dir, with_scenes=False)}
        self.assertEqual(by["Builtin"], "BUILTIN_SHADER")
        self.assertEqual(by["Gone"], "MISSING_SHADER")

    def test_forward_add_blend_is_not_transparency(self):
        lit = pass_shader_stubs._build_shader_body("Shader Forge/Object_DBL", "opaque")
        self.assertFalse(am.shader_traits(lit)["blends"])
        self.assertTrue(am.shader_traits(lit)["clips"])
        self.assertFalse(pass_shader_stubs._needs_regeneration(lit))
        stale = lit.replace("clip(", "(void)(")
        self.assertTrue(pass_shader_stubs._needs_regeneration(stale))
        self.assertFalse(am.shader_traits(stale)["blends"])

    def test_png_alpha_channel(self):
        self.assertTrue(am.png_has_alpha_channel(os.path.join(self.assets, "Texture2D", "masked.png")))


if __name__ == "__main__":
    unittest.main()
