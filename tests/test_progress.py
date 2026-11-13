#!/usr/bin/env python3
"""core/progress.py: how far the long steps are (Felipe, 2026-11-13: 'it is stopped, nothing for the person to
know whether it is going'). Each line is read from what the tool already writes:
- AssetRipper's export: "ExportProgress : (2880/7297) Exporting 'Tilla_Alert'" in its own log.
- Unity's first import: one "Start importing <path>" per file (8294 lines for 8273 files in the project, 2026-11-11).
- Unity's build: "[Scene 11/30]", "Compiling shader", the build backend's "[3737/4839  0s]", then Gradle."""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from core import progress  # noqa: E402


class TestExport(unittest.TestCase):
    LOG = ("System : AssetRipper\nExportProgress : (136/7297) Exporting 'NavMesh'\n"
           "ExportProgress : (2880/7297) Exporting 'Tilla_Alert'\nsomething else\n")

    def test_reads_the_last_count(self):
        self.assertEqual(progress.export_progress(self.LOG), (2880, 7297))
        self.assertIsNone(progress.export_progress("System : AssetRipper\n"))

    def test_line(self):
        self.assertEqual(progress.export_line(2880, 7297, seconds=120),
                         "Extracting the game: 39% (2880 of 7297), about 3 min left")
        self.assertEqual(progress.export_line(2880, 7297, seconds=120, lang="pt"),
                         "Extraindo o jogo: 39% (2880 de 7297), faltam uns 3 min")


class TestBuild(unittest.TestCase):
    def watch(self, text, assets=8000, lang="en"):
        w = progress.BuildWatcher(scenes=30, assets=assets, lang=lang)
        w.feed(text)
        return w.line(minutes=10)

    def test_first_import_counts_files(self):
        text = "".join("Start importing Assets/a%d.png using Guid(x)\n" % i for i in range(2000))
        line = self.watch(text)
        self.assertIn("importing the project", line)
        self.assertIn("25%", line)
        self.assertIn("2000 of 8000", line)

    def test_import_never_says_100_before_it_is_done(self):
        text = "".join("Start importing Assets/a%d.png using Guid(x)\n" % i for i in range(9000))
        self.assertIn("99%", self.watch(text))

    def test_scenes_are_counted_as_unity_opens_them(self):
        # "[Scene n/30]" is only the list, written all at once; "Opening scene" comes as each one is processed.
        text = "".join("  [Scene %d/30] Assets/Scenes/S%d.unity\n" % (i, i) for i in range(1, 31))
        text += "".join("Opening scene 'Assets/Scenes/S%d.unity'\n" % i for i in range(1, 12))
        self.assertIn("scene 11 of 30", self.watch(text))

    def test_the_first_counter_is_the_scripts(self):
        # The build backend counts the script compile first ([268/269]) and the player's packaging later.
        self.assertIn("compiling the scripts", self.watch("[268/269  0s] Csc x\n"))
        self.assertIn("packaging", self.watch("Opening scene 'a'\n[3737/4839  0s] CopyFiles x\n"))

    def test_shaders(self):
        text = "Opening scene 'a'\n" + 'Compiling shader "Shader Forge/Object" pass "FORWARD" (vp)\n' * 40
        self.assertIn("compiling shaders (40 so far)", self.watch(text))

    def test_packaging(self):
        text = "Opening scene 'a'\n" + 'Compiling shader "a" pass "b" (vp)\n[3737/4839  0s] CopyFiles x\n'
        self.assertIn("packaging: 77%", self.watch(text))

    def test_gradle(self):
        self.assertIn("making the APK", self.watch("[4800/4839  0s] x\n[BUSY     102s] 7z x/Gradle.main.obb\n"))

    def test_never_goes_back_after_the_build_moved_on(self):
        # The real log ends with a few "Start importing" after the APK: the line must not jump back to 0% import.
        w = progress.BuildWatcher(scenes=30, assets=8000)
        w.feed("Opening scene 'a'\n[4800/4839  0s] x\n[BUSY  9s] 7z x/Gradle.main.obb\nStart importing a\n")
        self.assertIn("making the APK", w.line(minutes=50))
        w = progress.BuildWatcher(scenes=30, assets=8000)
        w.feed("Opening scene 'a'\nStart importing b\n")
        self.assertIn("scene 1 of 30", w.line(minutes=5))

    def test_time_left_counts_from_the_start_of_the_phase(self):
        now = [0.0]
        w = progress.BuildWatcher(scenes=30, assets=8000, clock=lambda: now[0])
        w.feed("Opening scene 'a'\n")
        now[0] = 40 * 60.0                      # scenes and shaders took 40 minutes
        w.feed("[1000/4000  0s] x\n")          # packaging starts
        now[0] = 41 * 60.0                      # one minute into packaging, a quarter done
        w.feed("[1000/4000  0s] x\n")
        self.assertIn("about 3 min left", w.line(minutes=41))

    def test_fed_in_pieces(self):
        w = progress.BuildWatcher(scenes=30, assets=100)
        w.feed("Start importing a\nStart imp")
        w.feed("orting b\n")
        self.assertIn("2 of 100", w.line(minutes=1))

    def test_portuguese(self):
        text = "".join("Start importing Assets/a%d.png using Guid(x)\n" % i for i in range(2000))
        self.assertIn("importando o projeto", self.watch(text, lang="pt"))

    def test_nothing_yet(self):
        self.assertIn("starting Unity", self.watch(""))


class TestReadingLogsAsTheyGrow(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "x.log")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_export_status_reads_only_this_export(self):
        with open(self.log, "w") as fh:
            fh.write("ExportProgress : (7000/7297) an older export\n")
        start = os.path.getsize(self.log)
        self.assertIsNone(progress.export_status(self.log, start, seconds=10))
        with open(self.log, "a") as fh:
            fh.write("ExportProgress : (100/7297) Exporting 'x'\n")
        self.assertIn("(100 of 7297)", progress.export_status(self.log, start, seconds=10))

    def test_build_log_is_read_from_where_it_stopped(self):
        w = progress.BuildWatcher(scenes=30, assets=100)
        with open(self.log, "w") as fh:
            fh.write("Opening scene 'a'\n")
        offset = progress.feed_new(self.log, 0, w)
        with open(self.log, "a") as fh:
            fh.write("Opening scene 'b'\n")
        progress.feed_new(self.log, offset, w)
        self.assertIn("scene 2 of 30", w.line(minutes=1))
        self.assertEqual(progress.feed_new(os.path.join(self.tmp, "none.log"), 0, w), 0)

    def test_project_files_are_counted_without_metas(self):
        assets = os.path.join(self.tmp, "Assets", "a")
        os.makedirs(assets)
        for name in ("x.png", "x.png.meta", "y.prefab"):
            open(os.path.join(assets, name), "w").close()
        self.assertEqual(progress.count_assets(self.tmp), 2)


class TestRealBuildLog(unittest.TestCase):
    """A real 52-minute full build (Build 95), read in pieces as Unity writes it: the phases come in order."""
    LOG = os.path.expanduser("~/lunacid-work/builds/20261112_1437/build_apk.log")

    def test_phases_in_order(self):
        if not os.path.exists(self.LOG):
            self.skipTest("no stored build log on this machine")
        with open(self.LOG, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        w = progress.BuildWatcher(scenes=30, assets=8273)
        seen = []
        for i in range(0, len(text), 50000):
            w.feed(text[i:i + 50000])
            if not seen or seen[-1] != w.phase:
                seen.append(w.phase)
        self.assertEqual([p for p in ("scripts", "scene", "shaders", "pack", "gradle") if p in seen],
                         ["scripts", "scene", "shaders", "pack", "gradle"])
        self.assertLess(seen.index("scene"), seen.index("shaders"))
        self.assertLess(seen.index("pack"), seen.index("gradle"))


class TestTimeLeftLivesHere(unittest.TestCase):
    def test_shared(self):
        self.assertEqual(progress.time_left(0.25, 60), "about 3 min left")
        self.assertEqual(progress.time_left(0.25, 60, "pt"), "faltam uns 3 min")


class TestLanguageLivesHere(unittest.TestCase):
    def test_same_rule_for_every_tool(self):
        self.assertEqual(progress.language({"LANG": "pt_BR.UTF-8"}, None), "pt")
        self.assertEqual(progress.language({"LUNA_LANG": "en", "LANG": "pt_BR"}, "pt_BR"), "en")
        self.assertEqual(progress.language({}, None), "en")


if __name__ == "__main__":
    unittest.main()
