#!/usr/bin/env python3
"""
The key that signs the Quest APK (RELEASE_PLAN item 6, LESSONS 36).

    python3 tools/build/keystore.py                      # show the key in use (creates one if there is none)
    python3 tools/build/keystore.py --adopt <file> [--password P --alias A]   # use a key that already signs an install

Android only lets an APK replace the installed app when both are signed by the same key; otherwise it must be
uninstalled first, and uninstalling deletes the saves. So each machine keeps one key in <work>/keystore, outside the
repository, and never overwrites it. The first build makes a new key with the JDK's keytool (its password is random
and kept in keystore.json beside it). Someone who already has the port installed adopts the key that signed it
(on a Mac with Unity's default signing: ~/.android/debug.keystore, password "android", alias "androiddebugkey").
Back up the folder: on another computer, without it, the next install would need an uninstall.
"""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys

KEY_FILE = "lunacid-vr.keystore"
INFO_FILE = "keystore.json"


def folder(cfg):
    return os.path.join(cfg.get("work") or os.path.expanduser("~/lunacid-work"), "keystore")


def load(cfg):
    """The key in use, {path, password, alias, alias_password}, or None."""
    info_path = os.path.join(folder(cfg), INFO_FILE)
    if not os.path.exists(info_path):
        return None
    with open(info_path, encoding="utf-8") as fh:
        info = json.load(fh)
    info["path"] = os.path.join(folder(cfg), KEY_FILE)
    return info if os.path.exists(info["path"]) else None


def _save(cfg, info):
    os.makedirs(folder(cfg), exist_ok=True)
    data = {k: info[k] for k in ("password", "alias", "alias_password")}
    path = os.path.join(folder(cfg), INFO_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def adopt(cfg, source, password, alias, alias_password=None):
    """Use an existing key (the one that signed what is installed). Refuses to replace a different key."""
    target = os.path.join(folder(cfg), KEY_FILE)
    if os.path.exists(target):
        with open(target, "rb") as a, open(source, "rb") as b:
            if a.read() != b.read():
                raise RuntimeError("a different key is already in %s: it is never replaced" % folder(cfg))
    else:
        os.makedirs(folder(cfg), exist_ok=True)
        shutil.copy2(source, target)
    info = {"path": target, "password": password, "alias": alias, "alias_password": alias_password or password}
    _save(cfg, info)
    return info


def _keytool(cfg, keytool=None):
    if keytool:
        return keytool
    jdk = cfg.get("jdk")
    exe = "keytool.exe" if os.name == "nt" else "keytool"
    cand = os.path.join(jdk, "bin", exe) if jdk else None
    if cand and os.path.exists(cand):
        return cand
    found = shutil.which("keytool")
    if not found:
        raise RuntimeError("keytool not found: set 'jdk' in local.json (the JDK of Unity's Android module)")
    return found


def java_env(extra=None):
    """Java tools answer in English whatever the computer's language: their output is parsed here (keytool in
    Portuguese broke the build on a Windows notebook, 2026-11-13)."""
    env = dict(os.environ, **(extra or {}))
    env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "") + " -Duser.language=en -Duser.country=US").strip()
    return env


def ensure(cfg, keytool=None):
    """The key in use; a new one when there is none."""
    info = load(cfg)
    if info:
        return info
    password = secrets.token_urlsafe(24)
    info = {"path": os.path.join(folder(cfg), KEY_FILE), "password": password, "alias": "lunacidvr", "alias_password": password}
    os.makedirs(folder(cfg), exist_ok=True)
    subprocess.run([_keytool(cfg, keytool), "-genkeypair", "-keystore", info["path"], "-storetype", "PKCS12",
                    "-storepass", password, "-keypass", password, "-alias", info["alias"], "-keyalg", "RSA",
                    "-keysize", "2048", "-validity", "10000", "-dname", "CN=Lunacid VR port, O=local build"],
                   check=True, capture_output=True, env=java_env())
    _save(cfg, info)
    return info


def fingerprint(info, cfg=None, keytool=None):
    """SHA-256 of the key's certificate, lowercase hex."""
    out = subprocess.run([_keytool(cfg or {}, keytool), "-list", "-v", "-keystore", info["path"], "-storepass",
                          info["password"], "-alias", info["alias"]], check=True, capture_output=True, text=True, errors="replace",
                         env=java_env()).stdout
    m = re.search(r"SHA256:\s*([0-9A-Fa-f:]+)", out)
    if not m:
        raise RuntimeError("no SHA-256 in keytool's output for %s" % info["path"])
    return m.group(1).replace(":", "").lower()


def parse_apk_sha256(apksigner_output):
    m = re.search(r"Signer #1 certificate SHA-256 digest:\s*([0-9a-f]{64})", apksigner_output)
    return m.group(1) if m else None


def apk_sha256(apk, cfg):
    """SHA-256 of the certificate that signed the APK, read with the SDK's apksigner."""
    sdk = cfg.get("android_sdk") or ""
    tools = sorted(os.listdir(os.path.join(sdk, "build-tools"))) if os.path.isdir(os.path.join(sdk, "build-tools")) else []
    if not tools:
        raise RuntimeError("no build-tools in the Android SDK (%s)" % sdk)
    signer = os.path.join(sdk, "build-tools", tools[-1], "apksigner.bat" if os.name == "nt" else "apksigner")
    env = java_env()
    if cfg.get("jdk"):
        env["JAVA_HOME"] = cfg["jdk"]
    out = subprocess.run([signer, "verify", "--print-certs", apk], capture_output=True, text=True, errors="replace", env=env)
    return parse_apk_sha256(out.stdout + out.stderr)


def signature_problem(apk_sha, key_sha):
    """'' when the APK is signed by the machine's key, else why it must not be installed."""
    if not apk_sha:
        return "the APK is not signed (or apksigner could not read it)"
    if apk_sha != key_sha:
        return ("the APK is signed by another key (%s, expected %s): installing it would need an uninstall, "
                "which deletes the saves" % (apk_sha[:16], key_sha[:16]))
    return ""


def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core import config
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adopt", help="an existing keystore that signed the installed app")
    ap.add_argument("--password", default="android")
    ap.add_argument("--alias", default="androiddebugkey")
    args = ap.parse_args()
    cfg = config.load()
    info = adopt(cfg, os.path.expanduser(args.adopt), args.password, args.alias) if args.adopt else ensure(cfg)
    print("key: %s (alias %s)" % (info["path"], info["alias"]))
    print("SHA-256: %s" % fingerprint(info, cfg))
    print("Back up %s: without it, another computer cannot update the installed app." % folder(cfg))


if __name__ == "__main__":
    main()
