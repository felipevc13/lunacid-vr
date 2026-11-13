#!/usr/bin/env python3
"""
Where a build's shader time goes, read from Unity's build log.

    python3 tools/build/build_report.py <build_apk.log> [--top 25] [--budget N]   # exit 1 over N variants

For every shader: the variants left after stripping, how many were compiled (not from the cache), the CPU and
wall seconds of the compilation. A full build of a new project compiles every variant (61,440 on 2026-11-11, the
largest part of 133 min), so this ranking says which shaders to strip first.
"""

import re
import sys

SHADER = re.compile(r'^Compiling shader "([^"]+)" pass "([^"]*)"')
AFTER = re.compile(r"^\s+After scriptable stripping:\s+(\d+)")
FINISHED = re.compile(r"^\s+finished in ([\d.]+) seconds\. Local cache hits (\d+).*?compiled (\d+) variants \(([\d.]+)s CPU time\)")


def shader_costs(lines):
    """{shader: {variants, compiled, cache_hits, cpu_s, wall_s, passes}}."""
    out, current = {}, None
    for line in lines:
        m = SHADER.match(line)
        if m:
            current = out.setdefault(m.group(1), {"variants": 0, "compiled": 0, "cache_hits": 0, "cpu_s": 0.0,
                                                  "wall_s": 0.0, "passes": 0})
            current["passes"] += 1
            continue
        if current is None:
            continue
        m = AFTER.match(line)
        if m:
            current["variants"] += int(m.group(1))
            continue
        m = FINISHED.match(line)
        if m:
            current["wall_s"] += float(m.group(1))
            current["cache_hits"] += int(m.group(2))
            current["compiled"] += int(m.group(3))
            current["cpu_s"] += float(m.group(4))
    return out


def ranking(costs):
    """Shaders, costliest first (CPU seconds, then variants)."""
    return sorted(costs.items(), key=lambda kv: (-kv[1]["cpu_s"], -kv[1]["variants"]))


def totals(costs):
    return {"shaders": len(costs), "variants": sum(c["variants"] for c in costs.values()),
            "compiled": sum(c["compiled"] for c in costs.values()), "cpu_s": sum(c["cpu_s"] for c in costs.values()),
            "wall_s": sum(c["wall_s"] for c in costs.values())}


def over_budget(costs, budget):
    """[] when the build's variants fit the budget, else one line naming the total and the five largest shaders."""
    t = totals(costs)
    if not budget or t["variants"] <= budget:
        return []
    top = sorted(costs.items(), key=lambda kv: -kv[1]["variants"])[:5]
    return ["%d shader variants, budget %d; largest: %s" % (t["variants"], budget,
            ", ".join("%s %d" % (n, c["variants"]) for n, c in top))]


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 25
    budget = int(argv[argv.index("--budget") + 1]) if "--budget" in argv else 0
    with open(argv[1], encoding="utf-8", errors="replace") as fh:
        costs = shader_costs(fh.read().splitlines())
    t = totals(costs)
    print("%d shaders, %d variants, %d compiled, %.0f min CPU, %.0f min wall (summed per pass)"
          % (t["shaders"], t["variants"], t["compiled"], t["cpu_s"] / 60, t["wall_s"] / 60))
    print("%-55s %9s %9s %9s %6s" % ("shader", "variants", "compiled", "CPU min", "share"))
    for name, c in ranking(costs)[:top]:
        share = 100.0 * c["cpu_s"] / t["cpu_s"] if t["cpu_s"] else 0.0
        print("%-55s %9d %9d %9.1f %5.1f%%" % (name[:55], c["variants"], c["compiled"], c["cpu_s"] / 60, share))
    over = over_budget(costs, budget)
    if over:
        print("OVER BUDGET: " + over[0])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
