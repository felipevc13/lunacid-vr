#!/usr/bin/env python3
"""
Pass: Input System RebindingUI Sample
-------------------------------------
The game built the Input System's RebindingUI sample into Unity.InputSystem.RebindingUI.dll, and every scene holds
14 RebindActionUI components (the rebind page, hidden in VR). pass_legacy_dlls deletes that DLL and points the
components at RebindActionUI.cs with a fixed GUID; this pass puts the sample's two scripts there.

The scripts come from Unity's own com.unity.inputsystem package, never from this repository: the project's
Library/PackageCache when Unity has opened it, otherwise the package from Unity's registry (the address Unity uses),
checked against a pinned SHA-256 and kept in <work>/cache. Done by hand on 2026-10-27 (LESSONS 31).
"""

import glob
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request

VERSION = "1.20.0"
PACKAGE_URL = "https://download.packages.unity.com/com.unity.inputsystem/-/com.unity.inputsystem-%s.tgz" % VERSION
PACKAGE_SHA256 = "7f1050d80b8771ad2d3405972b1e222d4fa4fb409521521020d1eae341bd95e5"
SAMPLE = "Samples~/RebindingUI"
TARGET = "Assets/Scripts/RebindingUI"
REBIND_ACTION_UI_GUID = "82eb10d0a4c100000000000000000001"   # what pass_legacy_dlls points the components at
EXTENSIONS_GUID = "9a8373f6bb80d49e3a6dc9d7508327ad"          # the 2026-10-27 project's
FILES = {"RebindActionUI.cs": REBIND_ACTION_UI_GUID, "InputActionExtensions.cs": EXTENSIONS_GUID}

META = """fileFormatVersion: 2
guid: %s
MonoImporter:
  externalObjects: {}
  serializedVersion: 2
  defaultReferences: []
  executionOrder: 0
  icon: {instanceID: 0}
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def download(url, dest):
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as fh:
        shutil.copyfileobj(r, fh)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _from_package_cache(export_dir):
    """{name: bytes} from the project's Library/PackageCache, when Unity has resolved the same version."""
    for root in sorted(glob.glob(os.path.join(export_dir, "Library", "PackageCache", "com.unity.inputsystem@*"))):
        try:
            with open(os.path.join(root, "package.json"), encoding="utf-8") as fh:
                if json.load(fh).get("version") != VERSION:
                    continue
        except (OSError, ValueError):
            continue
        paths = {n: os.path.join(root, SAMPLE, n) for n in FILES}
        if all(os.path.exists(p) for p in paths.values()):
            out = {}
            for n, p in paths.items():
                with open(p, "rb") as fh:
                    out[n] = fh.read()
            return out
    return None


def _cached_package(profile):
    work = (profile or {}).get("work") or os.path.expanduser("~/lunacid-work")
    return os.path.join(work, "cache", "com.unity.inputsystem-%s.tgz" % VERSION)


def _from_registry(profile):
    """{name: bytes} from the package tarball, downloaded once and checked."""
    cached = _cached_package(profile)
    if not os.path.exists(cached) or _sha256(cached) != PACKAGE_SHA256:
        os.makedirs(os.path.dirname(cached), exist_ok=True)
        fd, part = tempfile.mkstemp(dir=os.path.dirname(cached), suffix=".part")
        os.close(fd)
        try:
            download(PACKAGE_URL, part)
            got = _sha256(part)
            if got != PACKAGE_SHA256:
                raise RuntimeError("com.unity.inputsystem %s from %s has SHA-256 %s, expected %s"
                                   % (VERSION, PACKAGE_URL, got, PACKAGE_SHA256))
            os.replace(part, cached)
        finally:
            if os.path.exists(part):
                os.remove(part)
    out = {}
    with tarfile.open(cached, "r:gz") as tar:
        for n in FILES:
            out[n] = tar.extractfile("package/%s/%s" % (SAMPLE, n)).read()
    return out


def _missing(export_dir):
    out = []
    for name, guid in FILES.items():
        path = os.path.join(export_dir, TARGET, name)
        if not os.path.exists(path):
            out.append("%s/%s missing" % (TARGET, name))
            continue
        try:
            with open(path + ".meta", encoding="utf-8") as fh:
                ok = ("guid: %s" % guid) in fh.read()
        except OSError:
            ok = False
        if not ok:
            out.append("%s/%s.meta must have guid %s" % (TARGET, name, guid))
    return out


def detect(export_dir, profile=None):
    if not os.path.isdir(os.path.join(export_dir, "Assets")):
        return []
    return _missing(export_dir)


def apply(export_dir, profile=None, dry_run=False):
    findings = detect(export_dir, profile)
    if not findings:
        return {"changes_applied": 0, "details": []}
    if dry_run:
        return {"changes_applied": len(findings), "details": ["Install the RebindingUI sample: " + f for f in findings]}
    files = _from_package_cache(export_dir) or _from_registry(profile)
    target = os.path.join(export_dir, TARGET)
    os.makedirs(target, exist_ok=True)
    for name, guid in FILES.items():
        with open(os.path.join(target, name), "wb") as fh:
            fh.write(files[name])
        with open(os.path.join(target, name + ".meta"), "w", encoding="utf-8") as fh:
            fh.write(META % guid)
    return {"changes_applied": len(findings), "details": ["Install %s/%s" % (TARGET, n) for n in FILES]}


def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {"passed": not findings, "remaining_issues": len(findings), "details": findings}
