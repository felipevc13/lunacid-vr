#!/usr/bin/env python3
"""
Compile the generated shaders in a throwaway Unity 6 project, for Vulkan / Android, with and without
single-pass stereo (multiview, as on the Quest), and report the errors grouped by message.

  python3 tools/shader_gen/compile_check.py --work ~/lunacid-work --unity /Applications/Unity/Hub/Editor/6000.0.85f1
        [--project DIR] [--shader 'Shader Forge/Fairy' ...] [--max-sets 6] [--all-sets 'Shader Forge/Object' ...]

The project (default <work>/shader_gen/compile_test) is created empty on first run, never the port's
project. Generated shaders are copied into its Assets/Generated; results go to
<work>/shader_gen/compile_check.jsonl and a summary is printed.
"""

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEREO = "STEREO_MULTIVIEW_ON"
# Keyword sets of a forward base pass on the Quest: dynamic object, lightmapped object.
COMPARE_SETS = ["DIRECTIONAL FOG_LINEAR LIGHTPROBE_SH", "DIRECTIONAL FOG_LINEAR LIGHTMAP_ON DIRLIGHTMAP_COMBINED"]
COND_RE = re.compile(r"^\s*#(?:if|elif)\s+(defined\(.*)$")
ELSE_RE = re.compile(r"^\s*#else\s*//\s*(.*)$")


def unity_exe(folder):
    """Unity editor binary inside an install folder (the Hub's Editor/<version> folder)."""
    folder = os.path.abspath(os.path.expanduser(folder))
    if sys.platform.startswith("win"):
        return os.path.join(folder, "Editor", "Unity.exe")
    if sys.platform == "darwin":
        return os.path.join(folder, "Unity.app", "Contents", "MacOS", "Unity")
    return os.path.join(folder, "Editor", "Unity")


def passes_of(text):
    """Generated shader text -> [{subshader, pass, name, sets}] for every pass with CGPROGRAM."""
    out, sub, pas, cur, in_cg, name = [], -1, -1, None, False, ""
    for line in text.split("\n"):
        s = line.strip()
        if not in_cg:
            if s.startswith("SubShader"):
                sub += 1
                pas = -1
            elif s.startswith("Pass {") or s == "Pass" or s.startswith("UsePass"):
                pas += 1
                name = ""
            elif s.startswith("Name ") and pas >= 0:
                name = s[5:].strip('"')
            elif s == "CGPROGRAM":
                in_cg = True
                cur = {"subshader": sub, "pass": pas, "name": name or str(pas), "sets": []}
            continue
        if s == "ENDCG":
            in_cg = False
            if not cur["sets"]:
                cur["sets"] = [""]
            out.append(cur)
            continue
        m = COND_RE.match(line)
        if m:
            cur["sets"].append(" ".join(re.findall(r"defined\((\w+)\)", m.group(1))))
            continue
        m = ELSE_RE.match(line)
        if m:
            kw = m.group(1).strip()
            cur["sets"].append("" if kw == "no keywords" else kw)
    return out


def sample(sets, n):
    """Up to n keyword sets spread over the chain: always the largest and the smallest."""
    if n <= 0 or len(sets) <= n:
        return sets
    idx = sorted({round(i * (len(sets) - 1) / (n - 1)) for i in range(n)})
    return [sets[i] for i in idx]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--unity", required=True, help="Unity 6 install folder (the one holding Unity.app)")
    ap.add_argument("--project")
    ap.add_argument("--shader", action="append")
    ap.add_argument("--max-sets", type=int, default=6, help="keyword sets per pass (0 = all)")
    ap.add_argument("--all-sets", action="append", default=[], help="shaders to compile with every keyword set")
    ap.add_argument("--summary-only", action="store_true", help="just summarise the last results")
    ap.add_argument("--compare", metavar="DIR", help="also compile the hand-written shaders of these names "
                    "found in DIR (the repo's shaders/), first pass only, with the same keywords, and compare sizes")
    a = ap.parse_args()

    root = os.path.join(os.path.abspath(os.path.expanduser(a.work)), "shader_gen")
    project = os.path.abspath(os.path.expanduser(a.project or os.path.join(root, "compile_test")))
    results = os.path.join(root, "compile_check.jsonl")
    unity = unity_exe(a.unity)

    if not a.summary_only:
        index = json.load(open(os.path.join(root, "decompiled", "index.json"), encoding="utf-8"))["shaders"]
        names = a.shader or sorted(n for n, e in index.items() if e.get("decompiled"))
        log = os.path.join(root, "compile_check_unity.log")
        if not os.path.isdir(os.path.join(project, "Assets")):
            subprocess.run([unity, "-batchmode", "-quit", "-createProject", project, "-logFile", log], check=True)
        gen_dir = os.path.join(project, "Assets", "Generated")
        shutil.rmtree(gen_dir, ignore_errors=True)
        os.makedirs(gen_dir)
        os.makedirs(os.path.join(project, "Assets", "Editor"), exist_ok=True)
        shutil.copy(os.path.join(HERE, "unity_check", "ShaderCompileCheck.cs"),
                    os.path.join(project, "Assets", "Editor", "ShaderCompileCheck.cs"))
        jobs = []
        for name in names:
            fname = index[name]["decompiled"]
            src = os.path.join(root, "generated", fname)
            if not os.path.isfile(src):
                print("not generated:", name)
                continue
            shutil.copy(src, os.path.join(gen_dir, fname))
            text = open(src, encoding="utf-8").read()
            passes = passes_of(text)
            n = 0 if name in a.all_sets else a.max_sets
            for p in passes:
                p["sets"] = sample(p["sets"], n)
            jobs.append({"path": "Assets/Generated/" + fname, "name": name, "passes": passes})
        if a.compare:
            hand_dir = os.path.join(project, "Assets", "Handwritten")
            shutil.rmtree(hand_dir, ignore_errors=True)
            os.makedirs(hand_dir)
            for name in names:
                fname = index[name]["decompiled"]
                hand = os.path.join(os.path.abspath(os.path.expanduser(a.compare)), fname)
                if not os.path.isfile(hand):
                    continue
                shutil.copy(hand, os.path.join(hand_dir, fname))
                for kind, path in (("handwritten", "Assets/Handwritten/"), ("generated", "Assets/Generated/")):
                    jobs.append({"path": path + fname, "name": "%s:%s" % (kind, name),
                                 "passes": [{"subshader": 0, "pass": 0, "name": "first", "sets": COMPARE_SETS}]})
        manifest = os.path.join(root, "compile_check_manifest.json")
        json.dump({"shaders": jobs, "extra": ["", STEREO], "output": results}, open(manifest, "w", encoding="utf-8"), indent=1)
        if os.path.exists(results):
            os.remove(results)
        r = subprocess.run([unity, "-batchmode", "-projectPath", project, "-buildTarget", "Android",
                            "-executeMethod", "ShaderCompileCheck.Run", "-manifest", manifest, "-logFile", log])
        if not os.path.exists(results):
            sys.exit("Unity wrote no results (exit %d); see %s" % (r.returncode, log))

    summarise(results)
    compare(results)


def compare(results):
    recs = [json.loads(l) for l in open(results, encoding="utf-8") if l.strip()]
    rows = collections.defaultdict(dict)
    for r in recs:
        if ":" not in r["shader"] or r["stage"] not in ("Vertex", "Fragment"):
            continue
        kind, name = r["shader"].split(":", 1)
        key = (name, r["keywords"], r["stage"])
        rows[key][kind] = r["bytes"] if r["ok"] else "error"
    if not rows:
        return
    print("\nCompiled size (SPIR-V bytes), hand-written shaders/ vs generated, first pass:")
    for (name, kw, stage), v in sorted(rows.items()):
        print("  %-26s %-6s %-70s %8s %8s" % (name, stage[:4], kw, v.get("handwritten", "-"), v.get("generated", "-")))


def summarise(results):
    recs = [json.loads(l) for l in open(results, encoding="utf-8") if l.strip()]
    recs = [r for r in recs if ":" not in r["shader"]]
    shaders = sorted({r["shader"] for r in recs})
    bad = collections.defaultdict(set)
    groups = collections.defaultdict(lambda: {"count": 0, "shaders": set(), "example": None})
    compiles = sum(1 for r in recs if r["stage"] in ("Vertex", "Fragment") and r["severity"] in ("Ok", "Error", "Warning"))
    for r in recs:
        if r["severity"] != "Error":
            continue
        bad[r["shader"]].add(r["stage"])
        key = re.sub(r"'[^']*'", "'…'", r["message"].split(" | ")[0])
        key = re.sub(r"\d+", "N", key)[:140]
        g = groups[key]
        g["count"] += 1
        g["shaders"].add(r["shader"])
        if g["example"] is None:
            g["example"] = r
    print("%d shaders checked, %d with no errors, %d with errors (compile records: %d)" %
          (len(shaders), len(shaders) - len(bad), len(bad), compiles))
    for key, g in sorted(groups.items(), key=lambda kv: -len(kv[1]["shaders"])):
        ex = g["example"]
        print("\n[%d shaders, %d messages] %s" % (len(g["shaders"]), g["count"], key))
        print("   e.g. %s / %s / %s / '%s': %s (line %s)" % (ex["shader"], ex["pass"], ex["stage"], ex["keywords"],
                                                           ex["message"][:300], ex["line"]))
        print("   shaders: " + ", ".join(sorted(g["shaders"])[:12]) + (" …" if len(g["shaders"]) > 12 else ""))


if __name__ == "__main__":
    main()
