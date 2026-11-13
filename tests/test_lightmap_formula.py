#!/usr/bin/env python3
"""The lightmaps by formula, without running the PC game (docs/RELEASE_PLAN.md, "Viabilidade: lightmaps").

AssetRipper's EXRs are converted on the user's machine and must match what the original game decodes on
the GPU (tools/lightmap_dump). The test needs game data that is never in the repository: AssetRipper's
originals (LUNA_LIGHTMAP_ORIGINALS, default <work>/backup_lightmaps) and the game's dumps (the
configuration's lightmap_dump_dir, core/config.py). Without them it is skipped."""

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "passes"))
import pass_lightmap_import as lm  # noqa: E402

sys.path.insert(0, REPO)
from core import config  # noqa: E402
_CFG = config.load()
ORIGINALS = os.path.expanduser(os.environ.get("LUNA_LIGHTMAP_ORIGINALS", os.path.join(_CFG["work"], "backup_lightmaps")))
DUMPS = _CFG.get("lightmap_dump_dir") or ""
CASES = [("HUB_01", "light"), ("HUB_01", "dir"), ("HUB_01", "shadowmask"), ("DETHLAND", "dir")]


def planes(exr):
    w, h = (int(v) for v in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", exr],
                                           capture_output=True, text=True, check=True).stdout.strip().split(","))
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", exr, "-f", "rawvideo", "-pix_fmt", "gbrapf32le", "-"],
                         capture_output=True, check=True).stdout
    return w, h, struct.unpack("<%df" % (4 * w * h), raw)


class TestLightmapFormula(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_formula_matches_the_games_decode(self):
        found = [(s, k) for s, k in CASES
                 if os.path.exists(os.path.join(ORIGINALS, s, "Lightmap-0_comp_%s.exr" % k)) and os.path.exists(os.path.join(DUMPS, s, "Lightmap-0_comp_%s.exr" % k))]
        if not found:
            self.skipTest("no AssetRipper originals and game dumps on this machine")
        for scene, kind in found:
            work = os.path.join(self.tmp, scene + "_" + kind + ".exr")
            shutil.copyfile(os.path.join(ORIGINALS, scene, "Lightmap-0_comp_%s.exr" % kind), work)
            converted = lm.convert_by_formula(work, kind)
            if kind == "dir":       # the direction map goes to a PNG from these planes, never back to EXR
                w, h, pl = converted
                got = [v for plane in pl for v in plane]
            else:
                w, h, got = planes(work)
            w2, h2, want = planes(os.path.join(DUMPS, scene, "Lightmap-0_comp_%s.exr" % kind))
            self.assertEqual((w, h), (w2, h2))
            step = max(1, len(got) // 4 // 65536)          # about 65k pixels, every plane
            n, err = 0, 0.0
            for p in range(4):
                base = p * w * h
                for i in range(0, w * h, step):
                    err += abs(got[base + i] - want[base + i]); n += 1
            mean = err / n
            print("  %s %s: mean error %.5f" % (scene, kind, mean))
            self.assertLess(mean, 0.002, "%s %s: mean error %.5f against the game's decode" % (scene, kind, mean))

    def test_pass_end_to_end_without_dump(self):
        # The pass as it runs on a user's machine: AssetRipper's EXRs in Assets/Scenes/<scene>/, no dump in the
        # profile. The colour map stays an EXR converted by formula; the direction map ends as the 8-bit PNG.
        scene = "HUB_01"
        need = ["light", "dir"]
        if not all(os.path.exists(os.path.join(ORIGINALS, scene, "Lightmap-0_comp_%s.exr" % k)) for k in need) \
                or not os.path.exists(os.path.join(DUMPS, scene, "Lightmap-0_comp_dir.exr")):
            self.skipTest("no AssetRipper originals and game dumps on this machine")
        meta_text = open(os.path.join(ORIGINALS, scene, "Lightmap-0_comp_dir.exr.meta"), encoding="utf-8").read()
        folder = os.path.join(self.tmp, "export", "Assets", "Scenes", scene)
        os.makedirs(folder)
        for k in need:
            shutil.copyfile(os.path.join(ORIGINALS, scene, "Lightmap-0_comp_%s.exr" % k), os.path.join(folder, "Lightmap-0_comp_%s.exr" % k))
            with open(os.path.join(folder, "Lightmap-0_comp_%s.exr.meta" % k), "w", encoding="utf-8") as f:
                f.write(meta_text)
        export = os.path.join(self.tmp, "export")
        self.assertTrue(any("by formula" in d for d in lm.detect(export, {}) + lm.apply(export, {}, dry_run=True)["details"]))
        lm.apply(export, {})
        self.assertTrue(lm.verify(export, {})["passed"], lm.detect(export, {}))
        self.assertEqual(lm.apply(export, {})["changes_applied"], 0)          # once only
        # Colour map against the game's decode.
        w, h, got = planes(os.path.join(folder, "Lightmap-0_comp_light.exr"))
        _, _, want = planes(os.path.join(DUMPS, scene, "Lightmap-0_comp_light.exr"))
        n = w * h; step = max(1, n // 40000)
        mean = sum(abs(got[p * n + i] - want[p * n + i]) for p in range(3) for i in range(0, n, step)) / (3 * len(range(0, n, step)))
        self.assertLess(mean, 0.002, "light: %.5f" % mean)
        # Direction map: the PNG against the game's decode, within 8-bit steps.
        png = os.path.join(folder, "Lightmap-0_comp_dir.png")
        self.assertTrue(os.path.exists(png) and os.path.exists(png + ".meta"))
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", png, "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True, check=True).stdout
        _, _, dump = planes(os.path.join(DUMPS, scene, "Lightmap-0_comp_dir.exr"))
        err = 0.0; c = 0
        for i in range(0, n, step):
            r, g, b = raw[4 * i] / 255.0, raw[4 * i + 1] / 255.0, raw[4 * i + 2] / 255.0
            err += abs(r - min(1.0, dump[2 * n + i])) + abs(g - min(1.0, dump[i])) + abs(b - min(1.0, dump[n + i])); c += 3
        print("  end to end %s: light %.5f, dir PNG %.5f" % (scene, mean, err / c))
        self.assertLess(err / c, 0.004, "dir PNG: %.5f" % (err / c))


if __name__ == "__main__":
    unittest.main()
