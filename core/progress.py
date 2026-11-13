#!/usr/bin/env python3
"""
How far the long steps are, read from what each tool already writes, in the computer's language (English unless the
computer is in Portuguese; LUNA_LANG chooses). One updating line, so a step never looks stopped.

- AssetRipper's export: "ExportProgress : (2880/7297) ..." in its own log.
- Unity's first import: one "Start importing <path>" per file; the total is the project's files.
- Unity's build: "[Scene 11/30]", "Compiling shader ...", the build backend's "[3737/4839 ...]", then Gradle.
"""

import os
import re
import sys

MB = 1024 * 1024


def language(env=None, system_locale=None):
    """'pt' on a Portuguese computer, else 'en'. LUNA_LANG chooses."""
    env = os.environ if env is None else env
    if env.get("LUNA_LANG") in ("en", "pt"):
        return env["LUNA_LANG"]
    if system_locale is None:
        try:
            import locale
            system_locale = locale.getlocale()[0]
        except Exception:
            system_locale = None
    for value in (env.get("LC_ALL"), env.get("LANG"), system_locale):
        if value and (value.lower().startswith("pt") or value.lower().startswith("portuguese")):
            return "pt"
    return "en"


def time_left(fraction, seconds, lang="en"):
    """'about 3 min left' from how far it is (0..1) and how long it took; '' when it is too early to guess."""
    if not seconds or seconds < 5 or fraction <= 0.01 or fraction >= 1:
        return ""
    left = seconds * (1 - fraction) / fraction
    if left < 60:
        return "menos de um minuto" if lang == "pt" else "less than a minute left"
    minutes = int(round(left / 60.0))
    if minutes >= 120:
        hours = "%.1f" % (minutes / 60.0)
        return ("faltam umas %s h" % hours.replace(".", ",")) if lang == "pt" else "about %s h left" % hours
    return ("faltam uns %d min" % minutes) if lang == "pt" else "about %d min left" % minutes


def live(line, end=False):
    """One line that updates in place."""
    sys.stdout.write("\r" + line + " " * 8 + ("\n" if end else ""))
    sys.stdout.flush()


# ---------- AssetRipper

EXPORT = re.compile(r"ExportProgress\s*:\s*\((\d+)/(\d+)\)")


def export_progress(text):
    found = EXPORT.findall(text)
    return (int(found[-1][0]), int(found[-1][1])) if found else None


def export_line(done, total, seconds=None, lang="en"):
    pct = done * 100 // total if total else 0
    left = time_left(float(done) / total if total else 0, seconds, lang)
    if lang == "pt":
        line = "Extraindo o jogo: %d%% (%d de %d)" % (pct, done, total)
    else:
        line = "Extracting the game: %d%% (%d of %d)" % (pct, done, total)
    return line + (", " + left if left else "")


def export_status(log, start, seconds, lang="en"):
    """The export line from what AssetRipper wrote after start (its log keeps earlier exports), or None."""
    if not log or not os.path.exists(log):
        return None
    with open(log, encoding="utf-8", errors="ignore") as fh:
        fh.seek(start)
        found = export_progress(fh.read())
    return export_line(found[0], found[1], seconds, lang) if found else None


def count_assets(project):
    """Files Unity will import the first time: everything under Assets except .meta files."""
    total = 0
    for _, _, files in os.walk(os.path.join(project, "Assets")):
        total += sum(1 for f in files if not f.endswith(".meta"))
    return total


def feed_new(log, offset, watcher):
    """Give the watcher what the log gained since offset; return the new offset."""
    if not os.path.exists(log):
        return offset
    with open(log, encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        watcher.feed(fh.read())
        return fh.tell()


# ---------- Unity's build

SCENE = re.compile(r"\[Scene (\d+)/(\d+)\]")
BEE = re.compile(r"^\[\s*(\d+)/(\d+)\s", re.M)

WORDS = {
    "en": {"start": "Build: starting Unity... (%d min)",
           "import": "Build: importing the project, %d%% (%d of %d), %s",
           "scene": "Build: scene %d of %d (%d min)",
           "shaders": "Build: compiling shaders (%d so far), %d min",
           "scripts": "Build: compiling the scripts: %d%% (%d of %d), %s",
           "pack": "Build: packaging: %d%% (%d of %d), %s",
           "gradle": "Build: making the APK, almost done (%d min)"},
    "pt": {"start": "Build: abrindo o Unity... (%d min)",
           "import": "Build: importando o projeto, %d%% (%d de %d), %s",
           "scene": "Build: cena %d de %d (%d min)",
           "shaders": "Build: compilando shaders (%d até agora), %d min",
           "scripts": "Build: compilando os scripts: %d%% (%d de %d), %s",
           "pack": "Build: empacotando: %d%% (%d de %d), %s",
           "gradle": "Build: montando o APK, quase pronto (%d min)"},
}


class BuildWatcher:
    """Reads Unity's log as it grows and says which phase the build is in, and how far. The phase is the one of the
    last marker seen (a real log interleaves them)."""

    def __init__(self, scenes, assets, lang="en", clock=None):
        import time
        self.clock = clock or time.time
        self.phase_began = self.clock()
        self.scenes, self.assets, self.lang = scenes, assets, lang
        self.pending = ""
        self.imports = 0
        self.opened = 0
        self.shaders = 0
        self.bee = None
        self.phase = "start"

    def feed(self, text):
        text = self.pending + text
        lines = text.split("\n")
        self.pending = lines.pop()          # an unfinished line waits for the rest
        for line in lines:
            if self.phase == "gradle":
                break                          # the last phase: a few late imports do not take the line back
            if line.startswith("Start importing "):
                self.imports += 1
                if not self.opened:            # the project's import comes before the build opens any scene
                    self._set("import")
            elif line.startswith("Opening scene "):
                self.opened += 1
                self._set("scene")
            elif line.startswith("Compiling shader "):
                self.shaders += 1
                self._set("shaders")
            elif "Gradle" in line and ("7z" in line or "BUSY" in line):
                self._set("gradle")
            else:
                m = BEE.match(line)
                if m:
                    self.bee = (int(m.group(1)), int(m.group(2)))
                    # before any scene the build backend is compiling the scripts; after, packaging the player
                    self._set("pack" if self.opened else "scripts")

    def _set(self, phase):
        if phase != self.phase:
            self.phase = phase
            self.phase_began = self.clock()

    def line(self, minutes):
        w = WORDS[self.lang]
        secs = self.clock() - self.phase_began     # time left is read from this phase's own pace
        if self.phase == "import":
            done, total = self.imports, max(self.assets, 1)
            pct = min(99, done * 100 // total)
            return w["import"] % (pct, done, total, time_left(pct / 100.0, secs, self.lang) or "%d min" % minutes)
        if self.phase == "scene":
            return w["scene"] % (min(self.opened, self.scenes), self.scenes, minutes)
        if self.phase == "shaders":
            return w["shaders"] % (self.shaders, minutes)
        if self.phase in ("pack", "scripts"):
            done, total = self.bee
            pct = min(99, done * 100 // total) if total else 0
            return w[self.phase] % (pct, done, total, time_left(pct / 100.0, secs, self.lang) or "%d min" % minutes)
        if self.phase == "gradle":
            return w["gradle"] % minutes
        return w["start"] % minutes


# ---------- errors as sentences

def friendly(main, log_dir=None, lang=None, step=None):
    """Run a tool's main(): an unexpected error prints one sentence (what failed, where the details are, run the
    same command again) and writes the traceback to <log_dir>/error_<time>.log. Planned exits pass through."""
    import datetime
    import traceback
    try:
        return main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as e:  # noqa: BLE001: the person needs a sentence; the details go to a file
        lang = lang or language()
        if not log_dir:
            try:
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from core import config
                log_dir = os.path.join(config.load()["work"], "logs")
            except Exception:
                log_dir = os.path.join(os.path.expanduser("~"), "lunacid-work", "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "error_%s.log" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
        what = step or os.path.basename(sys.argv[0] or "the tool")
        if lang == "pt":
            msg = ("\nAlgo inesperado aconteceu em %s: %s\nDetalhes em: %s\nRode o mesmo comando de novo; se "
                   "acontecer de novo, envie esse arquivo junto com a sua pergunta." % (what, e, path))
        else:
            msg = ("\nSomething unexpected happened in %s: %s\nDetails in: %s\nRun the same command again; if it "
                   "happens again, send that file with your question." % (what, e, path))
        print(msg)
        sys.exit(1)
