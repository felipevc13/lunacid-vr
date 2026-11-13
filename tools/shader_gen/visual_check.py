#!/usr/bin/env python3
"""
Render each hand-written shader of shaders/ next to its generated version, in the throwaway Unity 6
project, and report how much the pixels differ.

  python3 tools/shader_gen/visual_check.py --work ~/lunacid-work --unity /Applications/Unity/Hub/Editor/6000.0.85f1 \
        --project ~/lunacid-shader-compile-test --shaders shaders [--only 'Shader Forge/Fairy' ...]

Same sphere, same synthetic textures (checker with an alpha ramp), directional + point light, flat
ambient, linear fog; once as a dynamic object and once with a synthetic directional lightmap.
Each pair gives a PNG under <work>/shader_gen/visual/ (hand-written | generated | difference x4)
and a line in visual_check.jsonl. Look at the PNGs: a small mean difference can still be a
visible error in a small area.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from compile_check import unity_exe  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--unity", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--shaders", required=True, help="folder with the hand-written shaders (the repo's shaders/)")
    ap.add_argument("--only", action="append")
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--no-point-light", action="store_true", help="directional light only (isolates the ForwardAdd pass)")
    a = ap.parse_args()

    root = os.path.join(os.path.abspath(os.path.expanduser(a.work)), "shader_gen")
    project = os.path.abspath(os.path.expanduser(a.project))
    if not os.path.isdir(os.path.join(project, "Assets")):
        sys.exit("No Unity project at %s: run compile_check.py first (it creates it)." % project)
    unity = unity_exe(a.unity)

    hand_src = os.path.abspath(os.path.expanduser(a.shaders))
    gen_src = os.path.join(root, "generated")
    hand_dir = os.path.join(project, "Assets", "Handwritten")
    gen_dir = os.path.join(project, "Assets", "Generated")
    for d in (hand_dir, gen_dir):
        os.makedirs(d, exist_ok=True)
    pairs = []
    for f in sorted(os.listdir(hand_src)):
        if not f.endswith(".shader") or not os.path.isfile(os.path.join(gen_src, f)):
            continue
        m = re.search(r'^Shader "([^"]+)"', open(os.path.join(hand_src, f), encoding="utf-8").read(), re.M)
        name = m.group(1) if m else f
        if a.only and name not in a.only:
            continue
        shutil.copy(os.path.join(hand_src, f), os.path.join(hand_dir, f))
        shutil.copy(os.path.join(gen_src, f), os.path.join(gen_dir, f))
        pairs.append({"name": name, "hand": "Assets/Handwritten/" + f, "gen": "Assets/Generated/" + f})
    os.makedirs(os.path.join(project, "Assets", "Editor"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "unity_check", "ShaderVisualCheck.cs"),
                os.path.join(project, "Assets", "Editor", "ShaderVisualCheck.cs"))

    out_dir = os.path.join(root, "visual")
    results = os.path.join(root, "visual_check.jsonl")
    job = os.path.join(root, "visual_check_job.json")
    json.dump({"pairs": pairs, "outDir": out_dir, "size": a.size, "output": results, "noPointLight": a.no_point_light}, open(job, "w", encoding="utf-8"), indent=1)
    if os.path.exists(results):
        os.remove(results)
    log = os.path.join(root, "visual_check_unity.log")
    r = subprocess.run([unity, "-batchmode", "-projectPath", project, "-executeMethod", "ShaderVisualCheck.Run",
                        "-job", job, "-logFile", log])
    if not os.path.exists(results):
        sys.exit("Unity wrote no results (exit %d); see %s" % (r.returncode, log))

    recs = [json.loads(l) for l in open(results, encoding="utf-8") if l.strip()]
    print("%-52s %-8s %9s %8s %8s %8s" % ("shader", "mode", "mean diff", ">8/255 %", "hand px", "gen px"))
    for x in sorted(recs, key=lambda x: -x.get("mean_diff", 999)):
        if "error" in x:
            print("%-52s %s" % (x["name"], x["error"]))
            continue
        print("%-52s %-8s %9.2f %8.2f %8d %8d" % (x["name"], x["mode"], x["mean_diff"], x["pct_over_8"],
                                                  x["hand_drawn"], x["gen_drawn"]))
    print("\nimages:", out_dir)


if __name__ == "__main__":
    main()
