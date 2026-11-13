#!/usr/bin/env python3
"""setup.ps1 (Windows) and setup.sh (Mac): the one line a person pastes, on a computer with nothing installed.

They get what Python needs to run (Git and Python itself), the repository, then hand over to
`lunacid_vr.py start`, which does the rest. This Mac has no PowerShell, so setup.ps1 is checked by content here
and for real on a Windows computer."""

import os
import re
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(REPO, name), encoding="utf-8") as fh:
        return fh.read()


class TestWindows(unittest.TestCase):
    def setUp(self):
        self.ps = read("setup.ps1")

    def test_installs_git_and_python_with_winget_when_missing(self):
        for words in ("winget install", "Git.Git", "Python.Python.3.12", "--accept-package-agreements"):
            self.assertIn(words, self.ps)

    def test_new_programs_work_without_reopening_the_window(self):
        # 2026-11-13 on the notebook: Git installed but "não é reconhecido" until the terminal was reopened.
        self.assertIn('GetEnvironmentVariable("Path", "Machine")', self.ps)

    def test_never_trusts_the_store_python_stub(self):
        # Windows has a 'python' that only opens the Microsoft Store: use the py launcher, checked by its output.
        self.assertIn("py", self.ps)
        self.assertRegex(self.ps, r"--version")

    def test_hands_over_to_start(self):
        self.assertIn("lunacid_vr.py", self.ps)
        self.assertRegex(self.ps, r"lunacid_vr\.py\"?\s+start")

    def test_clones_or_uses_the_copy_it_is_in(self):
        self.assertIn("git clone", self.ps)
        self.assertIn("PSScriptRoot", self.ps)

    def test_never_reads_a_password(self):
        self.assertNotIn("AsSecureString", self.ps)
        self.assertNotRegex(self.ps.lower(), r"read-host[^\n]*(password|senha)")

    def test_speaks_portuguese_too(self):
        self.assertIn("Get-Culture", self.ps)
        self.assertIn("Instalando", self.ps)


class TestMac(unittest.TestCase):
    def setUp(self):
        self.sh = read("setup.sh")

    def test_valid_bash(self):
        res = subprocess.run(["bash", "-n", os.path.join(REPO, "setup.sh")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_gets_apples_tools_for_git_and_python(self):
        self.assertIn("xcode-select --install", self.sh)

    def test_questions_reach_the_person_when_piped(self):
        # curl ... | bash: the script itself is standard input, so start reads the keyboard from /dev/tty.
        self.assertRegex(self.sh, r"lunacid_vr\.py start\s*<\s*/dev/tty")

    def test_clones_or_uses_the_copy_it_is_in(self):
        self.assertIn("git clone", self.sh)

    def test_speaks_portuguese_too(self):
        self.assertIn("AppleLocale", self.sh)
        self.assertIn("Instalando", self.sh)


class TestTheOneLines(unittest.TestCase):
    """The README and both guides show the same two lines the scripts say they are run with."""

    def lines(self):
        ps = re.search(r"irm \S+setup\.ps1 \| iex", read("setup.ps1")).group(0)
        sh = re.search(r"curl -fsSL \S+setup\.sh \| bash", read("setup.sh")).group(0)
        return ps, sh

    def test_readme_and_guides_show_them(self):
        ps, sh = self.lines()
        for doc in ("README.md", "docs/SETUP_WINDOWS.md"):
            self.assertIn(ps, read(doc), doc)
        for doc in ("README.md", "docs/SETUP_MAC.md"):
            self.assertIn(sh, read(doc), doc)


if __name__ == "__main__":
    unittest.main()
