#!/usr/bin/env python3
"""
Pass: TextMesh Pro Essential Resources with the Game's Shader GUIDs
------------------------------------------------------------------
AssetRipper exports the game's 11 TextMesh Pro shaders as stubs in Assets/Resources/shaders (tmp_sdf.shader...),
and the game's 26 font materials point at them. The working shaders are TMP's own, in the "TMP Essential
Resources" package that comes with every Unity install (com.unity.ugui). This pass:
- unpacks those Essential Resources into Assets/TextMesh Pro, as Unity's "Import TMP Essentials" does;
- gives each package shader the GUID of the game's stub of the same name (TMP_SDF <- tmp_sdf), so the game's
  materials draw with TMP's shader without touching them;
- deletes the stubs, so the shader names are not defined twice.
Nothing of TMP is in this repository: the package is read from the configured Unity (core/config.py "unity").
Done by hand on 2026-10-27 (LESSONS 31).
"""

import glob
import ntpath
import os
import posixpath
import re
import tarfile

ROOT = "Assets/TextMesh Pro"
STUBS = "Assets/Resources/shaders"
GUID = re.compile(r"^guid:\s*([0-9a-f]{32})", re.M)


def essentials_package(unity):
    """TMP Essential Resources.unitypackage inside a Unity install, from the Unity executable's path."""
    tail = ("Resources", "PackageManager", "BuiltInPackages", "com.unity.ugui", "Package Resources",
            "TMP Essential Resources.unitypackage")
    unity = unity or ""
    pathmod = ntpath if "\\" in unity else posixpath     # a Windows path can be checked on any machine
    if "/Contents/MacOS/" in unity:                         # macOS: .../Unity.app/Contents/MacOS/Unity
        return pathmod.join(pathmod.dirname(pathmod.dirname(unity)), *tail)
    return pathmod.join(pathmod.dirname(unity), "Data", *tail)  # Windows/Linux: .../Editor/Unity(.exe)


def _read_package(path):
    """[(pathname, asset bytes or None for a folder, meta text)] of a .unitypackage."""
    entries = {}
    with tarfile.open(path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            guid, _, kind = member.name.lstrip("./").partition("/")
            if kind in ("pathname", "asset", "asset.meta"):
                entries.setdefault(guid, {})[kind] = tar.extractfile(member).read()
    out = []
    for guid, e in entries.items():
        if "pathname" not in e or "asset.meta" not in e:
            continue
        pathname = e["pathname"].decode("utf-8").splitlines()[0].strip()
        if not pathname.startswith(ROOT):
            continue
        out.append((pathname, e.get("asset"), e["asset.meta"].decode("utf-8")))
    return sorted(out)


def _guid(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            m = GUID.search(fh.read(4096))
    except OSError:
        return None
    return m.group(1) if m else None


def _stubs(export_dir):
    """{lower-case shader file name: game GUID} of the game's TMP stubs still in the export."""
    out = {}
    for path in glob.glob(os.path.join(export_dir, STUBS, "tmp_*.shader")):
        guid = _guid(path + ".meta")
        if guid:
            out[os.path.basename(path).lower()] = guid
    return out


def _plan(export_dir, profile):
    """(package path, [(pathname, asset, meta text as it must be)]) or (package path, None) when unreadable."""
    pkg = essentials_package((profile or {}).get("unity"))
    if not os.path.exists(pkg):
        return pkg, None
    stubs = _stubs(export_dir)
    # Once the stubs are gone, the GUIDs they gave are the ones already in the installed metas.
    installed = {}
    for path in glob.glob(os.path.join(export_dir, ROOT, "Shaders", "*.shader.meta")):
        installed[os.path.basename(path)[:-5].lower()] = _guid(path)
    plan = []
    for pathname, asset, meta in _read_package(pkg):
        name = os.path.basename(pathname).lower()
        if pathname.endswith(".shader"):
            game = stubs.get(name)
            if game:
                meta = GUID.sub("guid: " + game, meta, count=1)
            elif installed.get(name) and installed[name] != _guid_text(meta):
                meta = GUID.sub("guid: " + installed[name], meta, count=1)
        plan.append((pathname, asset, meta))
    return pkg, plan


def _guid_text(text):
    m = GUID.search(text)
    return m.group(1) if m else None


def _differences(export_dir, plan):
    out = []
    for pathname, asset, meta in plan:
        path = os.path.join(export_dir, pathname)
        if asset is not None:
            try:
                with open(path, "rb") as fh:
                    if fh.read() != asset:
                        out.append(pathname)
                        continue
            except OSError:
                out.append(pathname)
                continue
        if _guid(path + ".meta") != _guid_text(meta):
            out.append(pathname + ".meta")
    return out


def detect(export_dir, profile=None):
    if not os.path.isdir(os.path.join(export_dir, "Assets")):
        return []
    if not _stubs(export_dir) and not os.path.isdir(os.path.join(export_dir, ROOT)):
        return []  # no TextMesh Pro in this project
    pkg, plan = _plan(export_dir, profile)
    if plan is None:
        return ["TMP Essential Resources not found at %s (set 'unity' in local.json to Unity 6000.0.85f1)" % pkg]
    findings = ["%s/%s: game TMP stub still in the project" % (STUBS, n) for n in sorted(_stubs(export_dir))]
    findings += ["%s missing or different from Unity's TMP Essential Resources" % p for p in _differences(export_dir, plan)]
    return findings


def apply(export_dir, profile=None, dry_run=False):
    findings = detect(export_dir, profile)
    if not findings:
        return {"changes_applied": 0, "details": []}
    if dry_run:
        return {"changes_applied": len(findings), "details": findings}
    pkg, plan = _plan(export_dir, profile)
    if plan is None:
        raise RuntimeError(findings[0])
    for pathname, asset, meta in plan:
        path = os.path.join(export_dir, pathname)
        if asset is None:
            os.makedirs(path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(asset)
        with open(path + ".meta", "w", encoding="utf-8") as fh:
            fh.write(meta)
    for path in glob.glob(os.path.join(export_dir, STUBS, "tmp_*.shader*")):
        os.remove(path)
    return {"changes_applied": len(findings), "details": findings}


def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {"passed": not findings, "remaining_issues": len(findings), "details": findings}
