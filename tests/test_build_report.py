#!/usr/bin/env python3
"""tools/build/build_report.py: where a build's time goes, read from Unity's build log."""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "build"))
import build_report  # noqa: E402

LOG = '''Compiling shader "Shader Forge/Object" pass "FORWARD" (fp)
    Full variant space:         4096
    After settings filtering:   2048
    After built-in stripping:   900
    After scriptable stripping: 900
    Processed in 0.20 seconds
    starting compilation...
    finished in 300.00 seconds. Local cache hits 0 (0.00s CPU time), remote cache hits 0 (0.00s CPU time), compiled 900 variants (1200.50s CPU time), skipped 0 variants
Compiling shader "Shader Forge/Object" pass "FORWARD" (vp)
    Full variant space:         4096
    After settings filtering:   2048
    After built-in stripping:   900
    After scriptable stripping: 900
    finished in 100.00 seconds. Local cache hits 0 (0.00s CPU time), remote cache hits 0 (0.00s CPU time), compiled 900 variants (400.00s CPU time), skipped 0 variants
Compiling shader "Legacy Shaders/Particles/Alpha Blended" pass "" (vp)
    Full variant space:         4
    After settings filtering:   4
    After built-in stripping:   12
    After scriptable stripping: 12
    finished in 0.69 seconds. Local cache hits 12 (4.54s CPU time), remote cache hits 0 (0.00s CPU time), compiled 0 variants (0.00s CPU time), skipped 0 variants
'''


class TestBuildReport(unittest.TestCase):
    def test_variants_and_time_per_shader(self):
        shaders = build_report.shader_costs(LOG.splitlines())
        obj = shaders["Shader Forge/Object"]
        self.assertEqual(obj["variants"], 1800)
        self.assertEqual(obj["compiled"], 1800)
        self.assertAlmostEqual(obj["cpu_s"], 1600.5)
        self.assertAlmostEqual(obj["wall_s"], 400.0)
        part = shaders["Legacy Shaders/Particles/Alpha Blended"]
        self.assertEqual(part["variants"], 12)
        self.assertEqual(part["cache_hits"], 12)

    def test_ranking_puts_the_costliest_first(self):
        ranked = build_report.ranking(build_report.shader_costs(LOG.splitlines()))
        self.assertEqual(ranked[0][0], "Shader Forge/Object")

    def test_totals(self):
        t = build_report.totals(build_report.shader_costs(LOG.splitlines()))
        self.assertEqual(t["variants"], 1812)
        self.assertEqual(t["shaders"], 2)


    def test_budget(self):
        """A shader added to Always Included compiles every keyword combination: Particles/Standard Unlit alone
        was 61,920 variants and 84% of the shader time (LESSONS 34). The profile's budget catches that."""
        costs = build_report.shader_costs(LOG.splitlines())
        self.assertEqual(build_report.over_budget(costs, 2000), [])
        over = build_report.over_budget(costs, 1000)
        self.assertTrue(over and "1812" in over[0] and "Shader Forge/Object" in over[0], over)

    def test_profile_has_a_budget(self):
        sys.path.insert(0, REPO)
        from core import runner
        self.assertLess(runner.load_profile()["shader_variant_budget"], 141126)  # the 2026-11-12 measured build


if __name__ == "__main__":
    unittest.main()
