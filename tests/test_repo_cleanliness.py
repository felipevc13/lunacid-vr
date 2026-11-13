#!/usr/bin/env python3
"""
Test Repo Cleanliness
---------------------
Enforces that no game assets, decompiled binaries, scene files, prefabs,
textures, or proprietary game data exist inside the repository.
"""

import os
import unittest

FORBIDDEN_EXTENSIONS = {
    ".unity", ".prefab", ".asset", ".mat", ".dll", ".exe",
    ".png", ".jpg", ".jpeg",
    ".so", ".a", ".resS", ".resource", ".bundle",
    ".mp4", ".wav", ".ogg", ".mp3", ".exr"
}

ALLOWED_EXCEPTIONS = set()

class TestOurCodeIsTracked(unittest.TestCase):
    """Every source file of ours must reach a clone. "[Bb]uild/" in .gitignore hid tools/build/build.py from Git
    while the commit said it was added (LESSONS 32)."""

    def test_no_source_file_is_ignored(self):
        import subprocess
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sources = []
        for top in ("core", "passes", "tools", "tests", "editor", "runtime", "games"):
            for root, dirs, files in os.walk(os.path.join(repo_root, top)):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git") and not d.startswith(".")]
                sources += [os.path.relpath(os.path.join(root, f), repo_root) for f in files
                            if f.endswith((".py", ".sh", ".cs", ".json", ".md", ".patch")) and not f.startswith("._")]
        if not os.path.isdir(os.path.join(repo_root, ".git")):
            self.skipTest("not a Git checkout")
        res = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], cwd=repo_root, input="\n".join(sources),
                             capture_output=True, text=True)
        ignored = [line for line in res.stdout.splitlines() if line]
        self.assertEqual(ignored, [], "source files hidden by .gitignore")


class TestRepoCleanliness(unittest.TestCase):
    def test_no_game_files_in_repository(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        found_forbidden = []

        for root, dirs, files in os.walk(repo_root):
            # Ignore git internals
            if "/.git" in root or root.endswith("/.git"):
                continue

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                rel_path = os.path.relpath(os.path.join(root, f), repo_root)

                if ext in FORBIDDEN_EXTENSIONS and rel_path not in ALLOWED_EXCEPTIONS:
                    found_forbidden.append(rel_path)

        self.assertEqual(
            len(found_forbidden), 0,
            f"Found proprietary/game asset files inside repository:\n" + "\n".join(found_forbidden)
        )

    def test_no_machine_paths_in_code(self):
        # Every path of one machine lives in the local config (local.json, not committed; core/config.py), so the
        # repository builds on any Mac or Windows PC (docs/RELEASE_PLAN.md, item 4).
        import re
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pattern = re.compile(r"/Volumes/|/Users/[A-Za-z]|[A-Z]:\\\\Users\\\\|/home/[a-z]")
        code = {".py", ".cs", ".sh", ".json", ".ps1", ".md"}   # READMEs too: they reach the public repository
        found = []
        import subprocess
        # The files Git tracks (other sessions' worktrees under .claude/ and local.json are not the repository).
        tracked = subprocess.run(["git", "ls-files"], cwd=repo_root, capture_output=True, text=True).stdout.split("\n")
        for rel in tracked:
            f = os.path.basename(rel)
            if not rel or rel.startswith("docs/") or os.path.splitext(f)[1] not in code or f in ("local.json", "test_repo_cleanliness.py", "make_public.py", "test_make_public.py"):
                continue
            path = os.path.join(repo_root, rel)
            if not os.path.exists(path):
                continue
            if True:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    for n, line in enumerate(fh, 1):
                        if pattern.search(line):
                            found.append("%s:%d: %s" % (os.path.relpath(path, repo_root), n, line.strip()[:100]))
        self.assertEqual(found, [], "machine-specific paths in code:\n" + "\n".join(found))


if __name__ == "__main__":
    unittest.main()
