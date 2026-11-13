#!/usr/bin/env python3
"""Score one tour round and plan the next: game-wide material coverage.

A round is a folder with <key>/pc_NN.png, quest_NN.png and their .mats.txt lists (from LunaTour).
Each pc/quest pair gets an SSIM score (ffmpeg). Materials in a shot scoring >= GOOD count as checked
for the whole game (same material, same shader); materials only ever seen in low shots are suspects.
State lives in state.json next to the rounds; each run writes, per scene key, want_<key>.txt (the
materials still unchecked there, from the PC inventory materials_<key>.txt) for the next round, and
report.md.

Usage: python3 tools/tour/coverage.py <tour dir> <round dir> [GOOD]
"""
import json
import os
import re
import subprocess
import sys

GOOD = 0.90


def ssim(a, b):
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", a, "-i", b, "-lavfi", "ssim", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"All:([0-9.]+)", out)
    return float(m.group(1)) if m else None


def mats_of(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="ignore") as f:
        # material \t shader \t renderer path  ->  material \t shader
        return sorted({"\t".join(l.rstrip("\n").split("\t")[:2]) for l in f if l.count("\t") >= 2})


def main(tour, rnd, good=GOOD):
    state_path = os.path.join(tour, "state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {"checked": {}, "suspect": {}, "shots": []}
    for key in sorted(os.listdir(rnd)):
        kdir = os.path.join(rnd, key)
        if not os.path.isdir(kdir):
            continue
        for fn in sorted(os.listdir(kdir)):
            m = re.match(r"pc_(\d+)\.png$", fn)
            if not m:
                continue
            n = m.group(1)
            pc, q = os.path.join(kdir, fn), os.path.join(kdir, f"quest_{n}.png")
            if not os.path.exists(q) or os.path.getsize(pc) == 0 or os.path.getsize(q) == 0:
                continue
            score = ssim(pc, q)
            mats = mats_of(os.path.join(kdir, f"pc_{n}.mats.txt"))
            state["shots"].append({"round": os.path.basename(rnd), "key": key, "shot": n, "ssim": score, "materials": mats})
            for mk in mats:
                if score is not None and score >= good:
                    state["checked"].setdefault(mk, f"{os.path.basename(rnd)}/{key}/{n}")
                    state["suspect"].pop(mk, None)
                elif mk not in state["checked"]:
                    state["suspect"].setdefault(mk, []).append(f"{os.path.basename(rnd)}/{key}/{n} {score}")
    json.dump(state, open(state_path, "w"), indent=1, sort_keys=True)

    # Next round: unchecked materials of each scene inventory (suspects included: a closer look).
    wanted = {}
    for fn in os.listdir(tour):
        m = re.match(r"materials_(.+)\.txt$", fn)
        if not m:
            continue
        key = m.group(1)
        inv = mats_of(os.path.join(tour, fn))
        want = [k for k in inv if k not in state["checked"]]
        wanted[key] = len(want)
        with open(os.path.join(tour, f"want_{key}.txt"), "w") as f:
            f.write("\n".join(want) + ("\n" if want else ""))

    lines = ["# Tour coverage", "", f"Checked materials: {len(state['checked'])}; suspects: {len(state['suspect'])}", "",
             "| key | still unchecked |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(wanted.items())]
    lines += ["", "## Suspects (only seen in shots under the threshold)", ""]
    for mk, where in sorted(state["suspect"].items()):
        lines.append(f"- `{mk.replace(chr(9), ' / ')}`: {', '.join(where[:3])}")
    lines += ["", "## Lowest shots", ""]
    for s in sorted((s for s in state["shots"] if s["ssim"] is not None), key=lambda s: s["ssim"])[:40]:
        lines.append(f"- {s['round']}/{s['key']}/{s['shot']}: {s['ssim']:.3f}")
    with open(os.path.join(tour, "report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"checked {len(state['checked'])}, suspects {len(state['suspect'])}, unchecked per key {wanted}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else GOOD)
