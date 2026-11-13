#!/usr/bin/env python3
"""Write plan_SHOWCASE.txt: one "prefab" shot per Resources prefab in the showcase folders.

Weapons, items, broken enemy pieces, enemy bodies and magic. The host scene only has to load in
both games; the shots happen far below it (see LunaTour.SpawnShowcase).
Usage: python3 tools/tour/showcase_plan.py <ExportedProject> <out plan file> [host scene]
"""
import os
import sys

FOLDERS = ["weps", "items", "broke", "ded", "magic"]


def main(project, out, host="PITT_A1"):
    res = os.path.join(project, "Assets", "Resources")
    lines = [host]
    for folder in FOLDERS:
        d = os.path.join(res, folder)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".prefab"):
                lines.append(f"prefab\t{folder}/{fn[:-7]}\t0 0 0\t0 0 0\t0 0 0")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(lines) - 1} showcase shots in {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
