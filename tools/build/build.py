#!/usr/bin/env python3
"""
Build the Quest APK (and OBB) on macOS or Windows.

    python3 tools/build/build.py            # full build: passes, then Unity, new APK and OBB (~75-90 min)
    python3 tools/build/build.py --fast     # code only: reuses the last full build's scenes and assets (~25-45 min)

Paths come from the machine configuration (core/config.py). Steps:
1. Apply every pass (core/runner.py) and stop if any fails to verify.
2. Run Unity in batch mode (ConfigureAndroidAndBuild.BuildMainMenuOnly) with every scene of the game profile,
   a watch on the log size (a runaway log once filled the disk), and a time limit.
3. Check the result: a fresh APK, no "error CS" in the log (Unity can report success with compile errors),
   every scene in the build. The APK and OBB are copied to <work>/builds/<date-time>/.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import config, runner  # noqa: E402

LOG_LIMIT = 500 * 1024 * 1024
APK = "Lunacid_Quest.apk"
OBB = "Lunacid_Quest.main.obb"


def scene_names(profile):
    return [os.path.splitext(os.path.basename(s))[0] for s in profile.get("scenes", [])]


def plan(cfg, profile, fast=False, log=None, keystore=None):
    """(command, environment additions, scenes): what the Unity run will be. No side effects."""
    scenes = scene_names(profile)
    extra = [s for s in scenes if s != "MainMenu"]
    log = log or os.path.join(cfg["builds"], "build_apk.log")
    # -accept-apiupdate: let Unity update old APIs in the decompiled scripts (velocity -> linearVelocity), as the
    # editor did when the project was first opened (LESSONS 31).
    cmd = [cfg["unity"], "-batchmode", "-accept-apiupdate", "-projectPath", cfg["project"],
           "-executeMethod", "ConfigureAndroidAndBuild.BuildMainMenuOnly", "-logFile", log]
    env = dict(config.unity_env(cfg))
    env["LUNA_SPLIT_OBB"] = "1"
    env["LUNA_EXTRA_SCENES"] = ",".join(extra)
    if fast:
        env["LUNA_SCRIPTS_ONLY"] = "1"
    if keystore:
        env.update({"LUNA_KEYSTORE": keystore["path"], "LUNA_KEYSTORE_PASS": keystore["password"],
                    "LUNA_KEYALIAS": keystore["alias"], "LUNA_KEYALIAS_PASS": keystore["alias_password"]})
    return cmd, env, scenes


def write_build_info(out, commit, fast):
    """build.json beside the APK: the code it was built from, so `lunacid_vr.py start` knows when to build again."""
    import json
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "build.json"), "w", encoding="utf-8") as fh:
        json.dump({"commit": commit, "kind": "fast" if fast else "full",
                   "date": datetime.datetime.now().isoformat(timespec="seconds")}, fh, indent=2)


def git_commit():
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, errors="replace")
        return res.stdout.strip() if res.returncode == 0 else None
    except OSError:
        return None


def keep_log(log, out):
    """Copy Unity's log into the build's own folder: the next build overwrites the one in Builds/ (LESSONS 33)."""
    if log and os.path.exists(log):
        os.makedirs(out, exist_ok=True)
        shutil.copy2(log, os.path.join(out, os.path.basename(log)))


def variant_warning(log, profile):
    """A warning when the build compiled more shader variants than the profile's budget, else ''."""
    import build_report
    budget = (profile or {}).get("shader_variant_budget")
    if not budget or not os.path.exists(log):
        return ""
    with open(log, encoding="utf-8", errors="replace") as fh:
        over = build_report.over_budget(build_report.shader_costs(fh.read().splitlines()), budget)
    return "WARNING: " + over[0] + " (python3 tools/build/build_report.py <log>)" if over else ""


def check_log(log, scenes):
    """Problems found in the Unity log: compile errors, scenes missing from the build."""
    problems = []
    with open(log, encoding="utf-8", errors="ignore") as fh:
        text = fh.read()
    errors = sorted({line.strip() for line in text.splitlines() if "error CS" in line})
    if errors:
        problems.append("%d compile errors, first: %s" % (len(errors), errors[0][:160]))
    built = text.count("[Scene ")
    want = len(scenes)
    if want and ("[Scene %d/%d]" % (want, want)) not in text:
        problems.append("the build did not list all %d scenes (%d [Scene lines)" % (want, built))
    return problems


def run_unity(cmd, env, log, limit_s, watcher=None):
    """Run Unity; with a watcher (core.progress.BuildWatcher) one line says which phase it is in and how far."""
    from core import progress
    full_env = dict(os.environ, **env)
    start = time.time()
    offset = 0
    proc = subprocess.Popen(cmd, env=full_env)
    while proc.poll() is None:
        time.sleep(10)
        if watcher:
            offset = progress.feed_new(log, offset, watcher)
            progress.live(watcher.line(int((time.time() - start) / 60)))
        if os.path.exists(log) and os.path.getsize(log) > LOG_LIMIT:
            proc.kill()
            return "the Unity log passed %d MB; build stopped" % (LOG_LIMIT // (1024 * 1024))
        if time.time() - start > limit_s:
            proc.kill()
            return "time limit (%d min)" % (limit_s // 60)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fast", action="store_true", help="code only; reuses the last full build's scenes and assets")
    ap.add_argument("--skip-passes", action="store_true", help="do not apply the passes first")
    ap.add_argument("--limit-min", type=int, default=240)
    args = ap.parse_args()

    cfg = config.load()
    profile = runner.load_profile()
    for key in ("project", "unity"):
        if not os.path.exists(cfg[key]):
            sys.exit("not found: %s = %s (set it in local.json, see local.example.json)" % (key, cfg[key]))
    lock = os.path.join(cfg["project"], "Temp", "UnityLockfile")
    if os.path.exists(lock):
        sys.exit("Unity has the project open (or left %s behind): close it, or move the file aside" % lock)

    if not args.skip_passes:
        print("== passes")
        runner.run_apply(cfg["project"], profile)
        report = runner.run_verify(cfg["project"], profile)
        failed = [name for name, r in report.items() if isinstance(r, dict) and not r.get("passed", True)]
        if failed:
            sys.exit("passes did not verify: %s" % ", ".join(failed))

    import keystore
    key = keystore.ensure(cfg)
    key_sha = keystore.fingerprint(key, cfg)
    print("== signing key %s (SHA-256 %s...)" % (key["path"], key_sha[:16]))

    commit = git_commit()   # the code as the build starts: a later pull does not change what this APK is
    os.makedirs(cfg["builds"], exist_ok=True)
    log = os.path.join(cfg["builds"], "build_apk.log")
    cmd, env, scenes = plan(cfg, profile, fast=args.fast, log=log, keystore=key)
    apk = os.path.join(cfg["builds"], APK)
    for f in (log, apk):
        if os.path.exists(f):
            os.remove(f)
    print("== Unity build (%s, %d scenes), log: %s" % ("fast" if args.fast else "full", len(scenes), log))
    start = time.time()
    from core import progress
    watcher = progress.BuildWatcher(len(scenes), progress.count_assets(cfg["project"]), progress.language())
    stopped = run_unity(cmd, env, log, args.limit_min * 60, watcher)
    print()
    minutes = (time.time() - start) / 60
    out = os.path.join(cfg["work"], "builds", datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    failure = stopped or (None if os.path.exists(apk) else "no APK at %s" % apk)
    if not failure:
        failure = keystore.signature_problem(keystore.apk_sha256(apk, cfg), key_sha) or None
    problems = [] if failure else check_log(log, scenes)
    if failure or problems:
        keep_log(log, out + "_failed")
        sys.exit("FAIL: %s (log kept in %s_failed)" % (failure or "; ".join(problems), out))

    os.makedirs(out, exist_ok=True)
    keep_log(log, out)
    shutil.copy2(apk, out)
    write_build_info(out, commit, args.fast)
    obb = os.path.join(cfg["builds"], OBB)
    if os.path.exists(obb) and not args.fast:
        shutil.copy2(obb, out)
    warning = variant_warning(log, profile)
    if warning:
        print(warning)
    print("RESULT: built in %.0f min, %d scenes, no compile errors -> %s" % (minutes, len(scenes), out))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core import progress
    progress.friendly(main, step="the build")
