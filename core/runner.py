#!/usr/bin/env python3
"""
Lunacid VR Porting Pipeline - Pass Runner & Orchestrator
-------------------------------------------------------
Executes modular, idempotent porting passes against an exported Unity project.
Supports detect(), apply(), and verify() cycles with optional --dry-run.
"""

import os
import sys
import json
import argparse
import importlib

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

PASS_NAMES = [
    "pass_duplicate_scene_guids",
    "pass_strip_scene_refs",
    "pass_legacy_dlls",
    "pass_rebinding_ui",
    "pass_tmp_essentials",
    "pass_steam_guard",
    "pass_filesystem_redirect",
    "pass_material_stains",
    "pass_material_floats",
    "pass_shader_stubs",
    "pass_pixel_nostalgia_guard",
    "pass_effect_blit_guard",
    "pass_editor_scripts",
    "pass_gradle_no_parallel",
    "pass_tour_runtime",
    "pass_lightmap_import",
    "pass_soft_particles",
    "pass_xr_packages",
    "pass_vr_runtime",
    "pass_xr_bindings",
    "pass_msaa",
    "pass_skin_weights",
    "pass_vr_intro_skip",
    "pass_bindings_file"
]

# Machine paths the passes read from the profile; they live in the machine configuration (core/config.py).
CONFIG_KEYS = ("work", "lightmap_dump_dir", "unity")


def load_profile(profile_path=None):
    """The game profile (games/<game>.json) with this machine's paths from core/config.py added."""
    from core import config
    profile = {}
    if not profile_path:
        default_profile = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "games", "lunacid.json")
        if os.path.exists(default_profile):
            profile_path = default_profile
    if profile_path and os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as fh:
            profile = json.load(fh)
    cfg = config.load()
    for key in CONFIG_KEYS:
        if cfg.get(key) and key not in profile:
            profile[key] = cfg[key]
    return profile

def get_passes():
    passes = []
    for name in PASS_NAMES:
        try:
            mod = importlib.import_module(f"passes.{name}")
            passes.append(mod)
        except Exception as ex:
            print(f"[Runner] Warning: Failed to import pass {name}: {ex}", file=sys.stderr)
    return passes

def run_detect(export_dir, profile):
    results = {}
    print(f"\n=== [Pipeline: Detect Phase] Target: {export_dir} ===")
    for p in get_passes():
        pname = p.__name__.split(".")[-1]
        doc = (p.__doc__ or "").strip().split("\n")[0]
        findings = p.detect(export_dir, profile)
        results[pname] = {
            "description": doc,
            "findings_count": len(findings),
            "findings": findings
        }
        status = f"FOUND {len(findings)} issues" if findings else "CLEAN"
        print(f"  [{pname:30}] : {status}")
    return results

def run_apply(export_dir, profile, dry_run=False):
    results = {}
    mode_str = "[DRY-RUN]" if dry_run else "[APPLYING]"
    print(f"\n=== [Pipeline: Apply Phase {mode_str}] Target: {export_dir} ===")
    for p in get_passes():
        pname = p.__name__.split(".")[-1]
        log = p.apply(export_dir, profile, dry_run=dry_run)
        results[pname] = log
        changes = log.get("changes_applied", 0)
        print(f"  [{pname:30}] : {changes} changes recorded.")
    return results

def run_verify(export_dir, profile):
    results = {}
    all_passed = True
    print(f"\n=== [Pipeline: Verify Phase] Target: {export_dir} ===")
    for p in get_passes():
        pname = p.__name__.split(".")[-1]
        v = p.verify(export_dir, profile)
        results[pname] = v
        passed = v.get("passed", False)
        if not passed:
            all_passed = False
        status = "PASSED" if passed else f"FAILED ({v.get('remaining_issues', 1)} remaining)"
        print(f"  [{pname:30}] : {status}")
    results["all_passed"] = all_passed
    return results

def main():
    parser = argparse.ArgumentParser(description="Modular Unity VR porting pass runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_p = subparsers.add_parser("detect", help="Run detection across all passes.")
    detect_p.add_argument("export_dir", help="Path to exported Unity project.")
    detect_p.add_argument("--profile", help="Path to game profile JSON.")
    detect_p.add_argument("--json", dest="json_out", help="Write JSON report.")

    apply_p = subparsers.add_parser("apply", help="Apply fixes across all passes.")
    apply_p.add_argument("export_dir", help="Path to exported Unity project.")
    apply_p.add_argument("--profile", help="Path to game profile JSON.")
    apply_p.add_argument("--dry-run", action="store_true", help="Simulate changes without writing to disk.")
    apply_p.add_argument("--json", dest="json_out", help="Write JSON report.")

    verify_p = subparsers.add_parser("verify", help="Verify that all passes have succeeded.")
    verify_p.add_argument("export_dir", help="Path to exported Unity project.")
    verify_p.add_argument("--profile", help="Path to game profile JSON.")
    verify_p.add_argument("--json", dest="json_out", help="Write JSON report.")

    all_p = subparsers.add_parser("all", help="Run full cycle: detect -> apply -> verify.")
    all_p.add_argument("export_dir", help="Path to exported Unity project.")
    all_p.add_argument("--profile", help="Path to game profile JSON.")
    all_p.add_argument("--dry-run", action="store_true", help="Simulate changes.")
    all_p.add_argument("--json", dest="json_out", help="Write JSON report.")

    args = parser.parse_args()
    profile = load_profile(args.profile)
    export_dir = os.path.abspath(args.export_dir)

    report = {"command": args.command, "export_dir": export_dir}

    if args.command == "detect":
        report["detect"] = run_detect(export_dir, profile)
    elif args.command == "apply":
        report["apply"] = run_apply(export_dir, profile, dry_run=args.dry_run)
    elif args.command == "verify":
        report["verify"] = run_verify(export_dir, profile)
    elif args.command == "all":
        report["detect"] = run_detect(export_dir, profile)
        report["apply"] = run_apply(export_dir, profile, dry_run=args.dry_run)
        report["verify"] = run_verify(export_dir, profile)

    if getattr(args, "json_out", None):
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"\n[Runner] Wrote JSON report to {args.json_out}")

if __name__ == "__main__":
    main()

