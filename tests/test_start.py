#!/usr/bin/env python3
"""`lunacid_vr.py start`: from nothing to the game on the Quest, with as few questions as possible, and resumable.

Felipe (2026-11-13): most people are not technical, and an install that is hard to get through is one they give up
on. So one command runs setup, build and install in order, skips what is already done, asks only what only the
person can answer, and speaks the computer's language (Portuguese or English)."""

import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import lunacid_vr  # noqa: E402


class Steps:
    """Stand-ins for setup, doctor, build, the Quest and install; records what ran."""

    def __init__(self, ready=False, built=False, quest_after=0, backups=False):
        self.ran = []
        self.ready = ready
        self.built = built
        self.quest_after = quest_after       # how many checks before the Quest answers
        self.backups = backups
        self.asked = []
        self.said = []

    def setup(self):
        self.ran.append("setup")
        self.ready = True
        return 0

    def is_ready(self):
        return self.ready

    def build_needed(self):
        return self.needed if hasattr(self, "needed") else (None if self.built else "full")

    def build(self, kind="full"):
        self.ran.append("build" if kind == "full" else "build " + kind)
        self.built = True
        self.needed = None
        return 0

    def quest(self):
        if self.quest_after > 0:
            self.quest_after -= 1
            return "none"
        return "device"

    def installed_before(self):
        return False

    def reask(self):
        self.ran.append("reask")

    def sleep(self, seconds):
        pass

    def install(self):
        self.ran.append("install")

    def restore(self):
        self.ran.append("restore")

    def has_saves_backup(self):
        return self.backups

    def ask(self, q):
        self.asked.append(q)
        return ""

    def say(self, *a):
        self.said.append(" ".join(str(x) for x in a))


def run_start(steps, lang="en"):
    return lunacid_vr.start(steps, lang=lang)


class TestStart(unittest.TestCase):
    def test_from_nothing_runs_every_step_in_order(self):
        s = Steps()
        self.assertEqual(run_start(s), 0)
        self.assertEqual(s.ran, ["setup", "build", "install"])

    def test_steps_already_done_are_skipped(self):
        s = Steps(ready=True, built=True)
        run_start(s)
        self.assertEqual(s.ran, ["install"])

    def test_numbered_steps_with_time_estimates(self):
        s = Steps()
        run_start(s)
        text = "\n".join(s.said)
        for words in ("Step 1 of 3", "Step 2 of 3", "Step 3 of 3", "1 to 2 hours"):
            self.assertIn(words, text)

    def test_newer_code_is_built_again_fast_when_only_port_code_changed(self):
        s = Steps(ready=True, built=True)
        s.needed = "fast"
        run_start(s)
        self.assertEqual(s.ran, ["build fast", "install"])
        self.assertIn("25 to 45 minutes", "\n".join(s.said))

    def test_up_to_date_says_so(self):
        s = Steps(ready=True, built=True)
        run_start(s)
        self.assertIn("up to date", "\n".join(s.said))

    def test_waits_for_the_quest_and_says_what_to_do(self):
        s = Steps(ready=True, built=True, quest_after=2)
        run_start(s)
        self.assertEqual(s.ran, ["install"])
        text = " ".join(s.said)
        self.assertIn("USB", text)
        self.assertIn("Allow", text)
        self.assertEqual(s.asked, [])          # it watches the cable by itself: no Enter to press

    def test_a_quest_waiting_for_permission_is_asked_again_by_itself(self):
        # 2026-11-13 on the Windows notebook: adb said "unauthorized" and nothing showed in the headset. The Quest
        # opens its "Allow USB debugging" panel the moment the cable goes in, where the headset is facing; with the
        # headset on a table nobody sees it, and it ignores new requests while that one is pending. start asks the
        # Quest again by itself (now the headset is on), instead of leaving the person to guess.
        s = Steps(ready=True, built=True)
        states = iter(["unauthorized"] * 20 + ["device"])
        s.quest = lambda: next(states)
        run_start(s)
        self.assertIn("reask", s.ran)
        self.assertEqual(s.ran[-1], "install")
        self.assertIn("Allow", " ".join(s.said))

    def test_when_asking_again_does_not_help_it_says_what_to_do_by_hand(self):
        s = Steps(ready=True, built=True)
        states = iter(["unauthorized"] * 200 + ["device"])
        s.quest = lambda: next(states)
        run_start(s)
        self.assertEqual(s.ran.count("reask"), 3)
        text = " ".join(s.said)
        self.assertIn("Unplug the cable", text)
        self.assertIn("plug the cable back in", text)
        self.assertIn("restart the Quest", text)
        self.assertEqual(s.ran[-1], "install")

    def test_headset_on_before_the_cable(self):
        s = Steps(ready=True, built=True)
        run_start(s)
        plug = next(line for line in s.said if "cable" in line)
        self.assertLess(plug.index("headset"), plug.index("cable"))

    def test_gives_up_with_a_sentence_when_no_quest_ever_shows(self):
        s = Steps(ready=True, built=True, quest_after=10 ** 6)
        self.assertNotEqual(run_start(s), 0)
        self.assertNotIn("install", s.ran)

    def test_offers_saves_from_a_backup_after_the_first_launch(self):
        s = Steps(ready=True, built=True, backups=True)
        answers = iter(["y", ""])   # yes to the saves, game opened once
        s.ask = lambda q: (s.asked.append(q), next(answers))[1]
        run_start(s)
        self.assertEqual(s.ran, ["install", "restore"])
        self.assertTrue(any("open" in q.lower() for q in s.asked))

    def test_saves_are_not_restored_when_the_person_says_no(self):
        s = Steps(ready=True, built=True, backups=True)
        s.ask = lambda q: (s.asked.append(q), "n")[1]
        run_start(s)
        self.assertEqual(s.ran, ["install"])

    def test_a_failed_setup_stops_before_the_build(self):
        s = Steps()
        s.setup = lambda: (s.ran.append("setup"), 1)[1]
        self.assertNotEqual(run_start(s), 0)
        self.assertEqual(s.ran, ["setup"])

    def test_ends_saying_where_the_game_is_in_the_headset(self):
        s = Steps(ready=True, built=True)
        run_start(s)
        self.assertIn("Unknown sources", s.said[-1] + " ".join(s.said[-3:]))

    def test_english_on_a_portuguese_computer(self):
        s = Steps()
        run_start(s, lang=lunacid_vr.language({"LANG": "pt_BR.UTF-8"}, "pt_BR"))
        self.assertIn("Step 1 of 3", "\n".join(s.said))


class TestNoTracebacks(unittest.TestCase):
    """A crash shows a sentence saying what to do; the details go to a log file."""

    def test_an_unexpected_error_in_a_step_is_a_sentence(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        s = Steps()

        def boom():
            raise OSError("[WinError 740] A operação solicitada requer elevação")
        s.setup = boom
        rc = lunacid_vr.start(s, lang="en", log_dir=tmp)
        self.assertNotEqual(rc, 0)
        text = "\n".join(s.said)
        self.assertIn("WinError 740", text)
        self.assertIn("Run the same command again", text)
        logs = os.listdir(tmp)
        self.assertEqual(len(logs), 1)
        with open(os.path.join(tmp, logs[0]), encoding="utf-8") as fh:
            self.assertIn("Traceback", fh.read())


class TestLanguage(unittest.TestCase):
    def test_always_english(self):
        # Felipe, 2026-11-13: everything in English, whatever the computer's language.
        self.assertEqual(lunacid_vr.language({"LANG": "pt_BR.UTF-8"}, None), "en")
        self.assertEqual(lunacid_vr.language({}, "Portuguese_Brazil"), "en")
        self.assertNotIn("pt", lunacid_vr.TEXT)


class TestStartIsACommand(unittest.TestCase):
    def test_listed(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            lunacid_vr.main(["start", "--help"])
        self.assertIn("start", out.getvalue())


if __name__ == "__main__":
    unittest.main()
