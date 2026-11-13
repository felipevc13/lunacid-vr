#!/usr/bin/env python3
"""tools/build/keystore.py: the key that signs the APK (RELEASE_PLAN item 6, LESSONS 36).

An APK signed by another key cannot replace the installed one: Android asks to uninstall, and uninstalling deletes
the saves. So each machine keeps one key in <work>/keystore, never in the repository, never overwritten."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "build"))
sys.path.insert(0, REPO)
import keystore  # noqa: E402


def find_keytool():
    try:
        from core import config
        jdk = config.load().get("jdk")
    except Exception:
        jdk = None
    for cand in ([os.path.join(jdk, "bin", "keytool")] if jdk else []) + [shutil.which("keytool")]:
        # macOS ships /usr/bin/keytool as a stub that fails when no Java is installed: it must actually run.
        if cand and os.path.exists(cand) and subprocess.run([cand, "-help"], capture_output=True).returncode == 0:
            return cand
    return None


APKSIGNER_OUT = """Signer #1 certificate DN: C=US, O=Android, CN=Android Debug
Signer #1 certificate SHA-256 digest: 3a3c0399cc766d1392669b3894033187e22e2c577a9f1f15c9e561dc42986d6e
Signer #1 certificate SHA-1 digest: 0000000000000000000000000000000000000000
"""


class TestKeystore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = {"work": os.path.join(self.tmp, "work")}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_adopt_copies_the_existing_key(self):
        src = os.path.join(self.tmp, "debug.keystore")
        with open(src, "wb") as fh:
            fh.write(b"key bytes")
        info = keystore.adopt(self.cfg, src, password="android", alias="androiddebugkey")
        with open(info["path"], "rb") as fh:
            self.assertEqual(fh.read(), b"key bytes")
        self.assertTrue(info["path"].startswith(self.cfg["work"]))
        self.assertEqual(keystore.load(self.cfg)["alias"], "androiddebugkey")

    def test_never_overwritten(self):
        src = os.path.join(self.tmp, "a.keystore")
        with open(src, "wb") as fh:
            fh.write(b"first")
        keystore.adopt(self.cfg, src, password="android", alias="androiddebugkey")
        other = os.path.join(self.tmp, "b.keystore")
        with open(other, "wb") as fh:
            fh.write(b"second")
        with self.assertRaises(RuntimeError):
            keystore.adopt(self.cfg, other, password="android", alias="androiddebugkey")
        with open(keystore.load(self.cfg)["path"], "rb") as fh:
            self.assertEqual(fh.read(), b"first")

    def test_no_key_yet(self):
        self.assertIsNone(keystore.load(self.cfg))

    def test_new_key_generated_once(self):
        keytool = find_keytool()
        if not keytool:
            self.skipTest("no keytool (configure 'jdk')")
        info = keystore.ensure(self.cfg, keytool=keytool)
        self.assertTrue(os.path.exists(info["path"]))
        self.assertGreaterEqual(len(info["password"]), 20)
        fp = keystore.fingerprint(info, keytool=keytool)
        self.assertRegex(fp, r"^[0-9a-f]{64}$")
        again = keystore.ensure(self.cfg, keytool=keytool)
        self.assertEqual(keystore.fingerprint(again, keytool=keytool), fp)  # the same key, not a new one

    def test_apk_signer_parsed(self):
        self.assertEqual(keystore.parse_apk_sha256(APKSIGNER_OUT),
                         "3a3c0399cc766d1392669b3894033187e22e2c577a9f1f15c9e561dc42986d6e")

    def test_signature_mismatch_is_a_failure(self):
        good = "3a3c0399cc766d1392669b3894033187e22e2c577a9f1f15c9e561dc42986d6e"
        self.assertEqual(keystore.signature_problem(good, good), "")
        self.assertIn("uninstall", keystore.signature_problem("0" * 64, good))
        self.assertIn("not signed", keystore.signature_problem(None, good))

    def test_build_hands_the_key_to_unity(self):
        import build
        from core import runner
        cfg = {"unity": "/opt/Unity", "project": "/p/ExportedProject", "builds": "/p/Builds", "work": "/w"}
        info = {"path": "/w/keystore/lunacid-vr.keystore", "password": "pw", "alias": "lunacidvr", "alias_password": "pw2"}
        _, env, _ = build.plan(cfg, runner.load_profile(), keystore=info)
        self.assertEqual(env["LUNA_KEYSTORE"], info["path"])
        self.assertEqual(env["LUNA_KEYSTORE_PASS"], "pw")
        self.assertEqual(env["LUNA_KEYALIAS"], "lunacidvr")
        self.assertEqual(env["LUNA_KEYALIAS_PASS"], "pw2")

    def test_keys_never_in_the_repository(self):
        with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as fh:
            ignore = fh.read()
        self.assertIn("*.keystore", ignore)
        self.assertIn("*.jks", ignore)
        with open(os.path.join(REPO, "editor", "ConfigureAndroidAndBuild.cs"), encoding="utf-8") as fh:
            cs = fh.read()
        for name in ("LUNA_KEYSTORE", "LUNA_KEYSTORE_PASS", "LUNA_KEYALIAS", "LUNA_KEYALIAS_PASS", "useCustomKeystore"):
            self.assertIn(name, cs)


class TestWindowsInPortuguese(unittest.TestCase):
    """2026-11-13 on the notebook: keytool answered in Portuguese in the Windows code page ('Proprietário'),
    reading it as UTF-8 failed on byte 0xe7, and the build died: 'expected string or bytes-like object, got
    NoneType'. Output from other programs is read whatever its encoding."""

    def test_fingerprint_from_a_portuguese_keytool(self):
        import stat
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        fake = os.path.join(tmp, "keytool")
        text = ("Propriet\xe1rio: CN=Lunacid VR port\nV\xe1lido de: ter\xe7a\n"
                "SHA256: 3A:3C:03:99:CC:76:6D:13:92:66:9B:38:94:03:31:87:E2:2E:2C:57:7A:9F:1F:15:C9:E5:61:DC:42:98:6D:6E\n")
        with open(fake, "wb") as fh:
            fh.write(b"#!/bin/sh\ncat <<'EOF'\n" + text.encode("cp1252") + b"EOF\n")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        info = {"path": "k", "password": "p", "alias": "a"}
        self.assertEqual(keystore.fingerprint(info, {}, keytool=fake),
                         "3a3c0399cc766d1392669b3894033187e22e2c577a9f1f15c9e561dc42986d6e")


if __name__ == "__main__":
    unittest.main()
