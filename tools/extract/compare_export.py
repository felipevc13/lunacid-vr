#!/usr/bin/env python3
"""
Compare a fresh AssetRipper export with the port's project, to prove the scripted export is the same as the one
the port was made on.

    python3 tools/extract/compare_export.py [--deep] <export>/ExportedProject [<project>]

<project> defaults to the configuration's project (core/config.py). --deep also compares every text asset (scenes,
prefabs, materials, scripts...) after translating the export's GUIDs to the project's, and lists the files that
differ by folder; use it on an export with the passes applied. Two things are always compared:
- the number of files (not .meta) in every top-level Assets folder. Folders the passes or Unity write to are
  listed in PASS_FOLDERS with the reason; their counts are printed but may differ;
- every file of CONTENT_FOLDERS (textures, meshes, sounds), which no pass touches: same names and same bytes
  (SHA-256). GUIDs are counted but are no failure: AssetRipper 2.0.0 gives new GUIDs on every export, each
  export consistent with itself (2026-11-11, LESSONS 31), and the repository pins no GUID of a game asset.

Exit code 0 when every difference is in PASS_FOLDERS.
"""

import hashlib
import os
import re
import sys

CONTENT_FOLDERS = ("Texture2D", "Mesh", "AudioClip")

# Top-level Assets folders whose file count may differ from a raw export, and why (LESSONS 31). Run the passes on the
# export first and the passes' own folders match too; what is left is written by Unity, the build or the editor.
PASS_FOLDERS = {
    "(root)": "SAVE_7.MIDNIGHT, a save the game writes to Assets when it runs in the editor (probe runs)",
    "Editor": "pass_editor_scripts copies the port's editor scripts; 7 old test scripts are leftovers",
    "Scripts": "pass_vr_runtime, pass_tour_runtime, pass_filesystem_redirect, pass_rebinding_ui add scripts",
    "Shader": "pass_shader_stubs adds the fallbacks; the build writes LunacidPreloadedVariants.shadervariants",
    "Plugins": "pass_legacy_dlls deletes 5 DLLs; pass_gradle_no_parallel adds the Gradle template",
    "Resources": "pass_tmp_essentials removes the game's 11 TMP shader stubs",
    "TextMesh Pro": "pass_tmp_essentials installs Unity's TMP Essential Resources (37 files)",
    "XR": "LunaXRSetup (editor) writes the OpenXR settings during the build",
}

GUID = re.compile(r"^guid:\s*([0-9a-f]{32})", re.M)


def _files(folder):
    """Relative paths of the non-.meta files under folder."""
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.endswith(".meta") or name.startswith("."):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, name), folder))
    return sorted(out)


def folder_counts(assets):
    """{top-level folder: number of non-.meta files}; files at the top count under '(root)'."""
    counts = {}
    for entry in sorted(os.listdir(assets)):
        if entry.startswith("."):
            continue
        path = os.path.join(assets, entry)
        if os.path.isdir(path):
            counts[entry] = len(_files(path))
        elif not entry.endswith(".meta"):
            counts["(root)"] = counts.get("(root)", 0) + 1
    return counts


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _guid(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            m = GUID.search(fh.read(4096))
    except OSError:
        return None
    return m.group(1) if m else None


def compare_content(a, b):
    """Byte and GUID comparison of two folders: counts and the paths that differ."""
    fa, fb = set(_files(a)) if os.path.isdir(a) else set(), set(_files(b)) if os.path.isdir(b) else set()
    res = {"same": 0, "different": [], "guid": [], "only_export": sorted(fa - fb), "only_project": sorted(fb - fa)}
    for rel in sorted(fa & fb):
        pa, pb = os.path.join(a, rel), os.path.join(b, rel)
        if os.path.getsize(pa) != os.path.getsize(pb) or _sha256(pa) != _sha256(pb):
            res["different"].append(rel)
        else:
            res["same"] += 1
        if _guid(pa + ".meta") != _guid(pb + ".meta"):
            res["guid"].append(rel)
    return res


TEXT_EXTS = (".unity", ".prefab", ".asset", ".mat", ".anim", ".controller", ".overrideController", ".shader", ".cs",
             ".txt", ".json", ".physicMaterial", ".renderTexture", ".cubemap", ".mask", ".playable", ".spriteatlas",
             ".hlsl", ".cginc", ".properties", ".shadervariants")
GUID_REF = re.compile(r"guid: ?([0-9a-f]{32})")


def _meta_guids(root):
    """{asset path without .meta: guid} of every .meta under root/Assets."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "Assets")):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.endswith(".meta") and not name.startswith("."):
                path = os.path.join(dirpath, name)
                guid = _guid(path)
                if guid:
                    out[os.path.relpath(path, root)[:-5]] = guid
    return out


def compare_text(export, project):
    """Every text asset in both, after translating the export's GUIDs to the project's (paired by .meta path).
    {"same": n, "different": {top-level folder: [paths]}}."""
    me, mp = _meta_guids(export), _meta_guids(project)
    gmap = {g: mp[k] for k, g in me.items() if k in mp}
    same, different = 0, {}
    for dirpath, dirnames, filenames in os.walk(os.path.join(export, "Assets")):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith(".") or not name.endswith(TEXT_EXTS):
                continue
            pe = os.path.join(dirpath, name)
            rel = os.path.relpath(pe, export)
            pp = os.path.join(project, rel)
            if not os.path.exists(pp):
                continue
            with open(pe, "rb") as fa, open(pp, "rb") as fb:
                a, b = fa.read().decode("utf-8", "replace"), fb.read().decode("utf-8", "replace")
            if a != b:
                a = GUID_REF.sub(lambda m: "guid: " + gmap.get(m.group(1), m.group(1)), a)
                b = GUID_REF.sub(lambda m: "guid: " + m.group(1), b)
            if a == b:
                same += 1
            else:
                different.setdefault(rel.replace(os.sep, "/").split("/")[1], []).append(rel.replace(os.sep, "/"))
    return {"same": same, "different": {k: sorted(v) for k, v in sorted(different.items())}}


def compare(export, project):
    ea, pa = os.path.join(export, "Assets"), os.path.join(project, "Assets")
    ce, cp = folder_counts(ea), folder_counts(pa)
    counts, explained = {}, {}
    for name in sorted(set(ce) | set(cp)):
        pair = (ce.get(name, 0), cp.get(name, 0))
        if pair[0] != pair[1]:
            (explained if name in PASS_FOLDERS else counts)[name] = pair
    content = {f: compare_content(os.path.join(ea, f), os.path.join(pa, f)) for f in CONTENT_FOLDERS}
    return {"export_counts": ce, "project_counts": cp, "counts": counts, "counts_explained": explained,
            "content": content}


def unexplained(report):
    """Every difference that no pass explains, one line each."""
    out = ["%s: %d files in the export, %d in the project" % (n, a, b) for n, (a, b) in report["counts"].items()]
    for folder, res in report["content"].items():
        out += ["%s/%s: different bytes" % (folder, r) for r in res["different"]]
        out += ["%s/%s: only in the export" % (folder, r) for r in res["only_export"]]
        out += ["%s/%s: only in the project" % (folder, r) for r in res["only_project"]]
    return out


def main(argv):
    deep = "--deep" in argv
    argv = [a for a in argv if a != "--deep"]
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    export = os.path.abspath(argv[1])
    if len(argv) > 2:
        project = os.path.abspath(argv[2])
    else:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from core import config
        project = config.load()["project"]
    report = compare(export, project)
    print("%-22s %8s %8s" % ("Assets folder", "export", "project"))
    for name in sorted(set(report["export_counts"]) | set(report["project_counts"])):
        a, b = report["export_counts"].get(name, 0), report["project_counts"].get(name, 0)
        note = "" if a == b else ("  passes: " + PASS_FOLDERS[name] if name in PASS_FOLDERS else "  DIFFERENT")
        print("%-22s %8d %8d%s" % (name, a, b, note))
    for folder, res in report["content"].items():
        print("%s: %d identical, %d different bytes, %d different guid, %d only export, %d only project"
              % (folder, res["same"], len(res["different"]), len(res["guid"]), len(res["only_export"]),
                 len(res["only_project"])))
    problems = unexplained(report)
    for p in problems[:50]:
        print("  " + p)
    if len(problems) > 50:
        print("  ... %d more" % (len(problems) - 50))
    if deep:
        res = compare_text(export, project)
        print("deep: %d text assets equal after translating GUIDs" % res["same"])
        for folder, paths in res["different"].items():
            print("  %-20s %5d different, e.g. %s" % (folder, len(paths), ", ".join(paths[:3])))
    print("RESULT: %s" % ("FAIL, %d unexplained differences" % len(problems) if problems else
                          "the export matches the project outside the folders the passes write"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
