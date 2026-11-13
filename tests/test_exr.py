#!/usr/bin/env python3
"""core/exr.py: the lightmap pass reads and writes EXR in Python, with nothing to install.

2026-11-13 on the Windows notebook: the build stopped at pass_lightmap_import with "[WinError 2] O sistema não
pode encontrar o arquivo especificado": it ran ffprobe/ffmpeg, which this Mac had from Homebrew and a fresh
Windows does not. Where ffmpeg is present the tests check our reader and writer against it, value for value."""

import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from core import exr  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


def ffmpeg_planes(path):
    """(w, h, [g, b, r, a]) as ffmpeg decodes the file."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            path], capture_output=True, text=True, check=True)
    w, h = (int(v) for v in probe.stdout.strip().split(","))
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt",
                          "gbrapf32le", "-"], capture_output=True, check=True).stdout
    n = w * h
    vals = struct.unpack("<%df" % (4 * n), raw)
    return w, h, [list(vals[i * n:(i + 1) * n]) for i in range(4)]


def sample(w, h, seed=1):
    rnd = random.Random(seed)
    return [[rnd.uniform(0, 4) for _ in range(w * h)] for _ in range(3)] + [[rnd.uniform(0.1, 1) for _ in range(w * h)]]


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_float_zip_round_trip_is_exact(self):
        planes = sample(37, 21)                          # not a multiple of the 16-line ZIP block
        path = os.path.join(self.tmp, "a.exr")
        exr.write_gbra(path, 37, 21, planes)
        w, h, back = exr.read_gbra(path)
        self.assertEqual((w, h), (37, 21))
        for p, q in zip(planes, back):
            self.assertEqual([struct.unpack("<f", struct.pack("<f", v))[0] for v in p], q)

    def test_every_compression_and_type_we_read(self):
        planes = sample(9, 5, seed=2)
        for compression in (exr.NONE, exr.RLE, exr.ZIPS, exr.ZIP):
            for pixel in (exr.HALF, exr.FLOAT):
                path = os.path.join(self.tmp, "c%d_%d.exr" % (compression, pixel))
                exr.write_gbra(path, 9, 5, planes, compression=compression, pixel=pixel)
                _, _, back = exr.read_gbra(path)
                tol = 2e-3 * 4 if pixel == exr.HALF else 1e-6
                for p, q in zip(planes, back):
                    self.assertTrue(all(abs(a - b) <= tol for a, b in zip(p, q)), (compression, pixel))

    def test_a_compression_we_do_not_read_says_so(self):
        path = os.path.join(self.tmp, "piz.exr")
        exr.write_gbra(path, 4, 4, sample(4, 4), compression=exr.ZIP)
        data = bytearray(open(path, "rb").read())
        i = data.index(b"compression\x00compression\x00") + len(b"compression\x00compression\x00") + 4
        data[i] = 4                                       # PIZ
        open(path, "wb").write(bytes(data))
        with self.assertRaises(ValueError) as ctx:
            exr.read_gbra(path)
        self.assertIn("PIZ", str(ctx.exception))


@unittest.skipUnless(FFMPEG, "ffmpeg is not installed here")
class TestAgainstFfmpeg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_ffmpeg_reads_what_we_write(self):
        planes = sample(40, 33, seed=3)
        path = os.path.join(self.tmp, "ours.exr")
        exr.write_gbra(path, 40, 33, planes)
        w, h, back = ffmpeg_planes(path)
        self.assertEqual((w, h), (40, 33))
        for p, q in zip(planes, back):
            self.assertEqual([struct.unpack("<f", struct.pack("<f", v))[0] for v in p], q)

    def test_we_read_what_ffmpeg_writes(self):
        planes = sample(40, 33, seed=4)
        raw = os.path.join(self.tmp, "in.raw")
        with open(raw, "wb") as fh:
            fh.write(struct.pack("<%df" % (4 * 40 * 33), *[v for p in planes for v in p]))
        path = os.path.join(self.tmp, "ffmpeg.exr")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gbrapf32le",
                        "-s", "40x33", "-i", raw, "-c:v", "exr", "-format", "2", "-compression", "3",
                        "-frames:v", "1", path], check=True)
        self.assertEqual(exr.read_gbra(path), ffmpeg_planes(path))

    def test_the_games_real_lightmaps_read_the_same(self):
        try:
            from core import config
            project = config.load()["project"]
        except Exception:
            project = ""
        found = [os.path.join(project, "Assets", "Scenes", s, f) for s in ("HUB_01", "DETHLAND")
                 for f in ("Lightmap-0_comp_light.exr", "Lightmap-0_comp_shadowmask.exr")]
        found = [f for f in found if os.path.exists(f)]
        if not found:
            self.skipTest("no lightmaps in this machine's project")
        for path in found[:2]:
            # These are HALF, and ffmpeg's half decode is not exact: it clips at 1.0 (the file's 1.12109375 reads
            # as 1.0; lightmaps are HDR, so that lost the brightest light) and drifts below it (0.066650390625 reads
            # 0.06619...). Ours is the stored value. Compared where ffmpeg does not clip, the gap stays below one
            # 8-bit step (1/255 = 0.0039); above 1, ours must keep the light.
            ours, theirs = exr.read_gbra(path), ffmpeg_planes(path)
            self.assertEqual(ours[:2], theirs[:2])
            above = 0
            for p, q in zip(ours[2][:3], theirs[2][:3]):
                gaps = [abs(a - b) for a, b in zip(p, q) if b < 0.999]
                self.assertLess(max(gaps), 2e-3, path)
                above += sum(1 for a in p if a > 1.0)
            if "_light" in path:
                self.assertGreater(above, 0, "HDR values above 1 must survive")


if __name__ == "__main__":
    unittest.main()
