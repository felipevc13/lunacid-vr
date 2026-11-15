#!/usr/bin/env python3
"""
The VR runtime must never load a whole Resources tree at once
-------------------------------------------------------------
Resources.LoadAll("") loads every file of every Resources folder: in Lunacid that is 822 files, 126 MB, and the
Quest stood still 4 to 7 s on the "Hollow Basin" title after the new game's opening (2026-11-14). A search names
its folder, e.g. Resources.LoadAll("Sprite Assets", type).
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = [os.path.join(ROOT, "tools", "vr", f) for f in ("LunaVRRuntime.cs",)]


class TestNoWholeResourcesLoad(unittest.TestCase):
    def test_no_load_all_of_the_root(self):
        bad = []
        for path in RUNTIME:
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if line.lstrip().startswith("//"):
                        continue
                    if re.search(r'Resources\.LoadAll\s*(<[^>]*>)?\s*\(\s*(""|string\.Empty)', line):
                        bad.append("%s:%d: %s" % (os.path.basename(path), n, line.strip()))
        self.assertEqual(bad, [], "Resources.LoadAll of the root loads every resource file")


if __name__ == "__main__":
    unittest.main()
