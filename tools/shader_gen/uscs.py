#!/usr/bin/env python3
"""
Build USCSandbox (the DX11 shader decompiler) on this machine and run it on the user's own copy of
the game. Nothing it reads or writes goes into the repository: everything lands under --work.

  python3 tools/shader_gen/uscs.py build     --work ~/lunacid-work [--dotnet PATH]
  python3 tools/shader_gen/uscs.py decompile --work ~/lunacid-work --data /path/LUNACID_Data [--shader NAME ...]

build:     clones USCSandbox at the pinned commit (uscs/UPSTREAM.json), applies uscs/patches/*.patch,
           builds it with the .NET 8 SDK. No .NET? tools/shader_gen/README.md says how to get one
           without a password.
decompile: lists the shaders in every .assets file of --data, decompiles the ones asked for (all by
           default) into <work>/shader_gen/decompiled/<shader name>.shader and writes index.json.

USCSandbox is GPL-3.0 and runs as a separate program; this script and its output are not part of it.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
USCS_DIR = os.path.join(HERE, "uscs")
LIST_RE = re.compile(r"^\s+(.+) \(path id (-?\d+)\)\s*$")


def paths(work):
    root = os.path.join(os.path.abspath(os.path.expanduser(work)), "shader_gen")
    return {
        "root": root,
        "src": os.path.join(root, "uscs_src"),
        "bin": os.path.join(root, "uscs_bin"),
        "run": os.path.join(root, "uscs_run"),
        "out": os.path.join(root, "decompiled"),
    }


def find_dotnet(given, work):
    exe = "dotnet.exe" if os.name == "nt" else "dotnet"
    for cand in (given, shutil.which("dotnet"),
                 os.path.join(os.path.expanduser(work), "tools", "dotnet", exe)):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    sys.exit("No .NET 8 SDK found. Pass --dotnet, or see tools/shader_gen/README.md.")


def remove_appledouble(top):
    """exFAT and other non-Apple volumes get '._name' files from macOS; C# and the SDK choke on them."""
    n = 0
    for root, _dirs, files in os.walk(top):
        for f in files:
            if f.startswith("._"):
                os.remove(os.path.join(root, f))
                n += 1
    return n


def run(cmd, cwd=None, env=None, log=None):
    """Run a tool. With log, its output goes there (compiler warnings look like errors to people new to this) and
    only a failure shows the end of it."""
    if not log:
        print("+", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=cwd, env=env, check=True)
        return
    with open(log, "a", encoding="utf-8", errors="replace") as fh:
        fh.write("\n+ %s\n" % " ".join(cmd))
        fh.flush()
        rc = subprocess.call(cmd, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT)
    if rc != 0:
        with open(log, encoding="utf-8", errors="replace") as fh:
            tail = "".join(fh.readlines()[-25:])
        sys.exit("%s failed (exit code %d). The end of %s:\n%s" % (os.path.basename(cmd[0]), rc, log, tail))


def build(args):
    p = paths(args.work)
    up = json.load(open(os.path.join(USCS_DIR, "UPSTREAM.json"), encoding="utf-8"))
    dotnet = find_dotnet(args.dotnet, args.work)
    os.makedirs(p["root"], exist_ok=True)
    log = os.path.join(p["root"], "uscs_build.log")
    open(log, "w").close()
    print("Preparing the shader decompiler (USCSandbox, once)...", flush=True)
    if not os.path.isdir(os.path.join(p["src"], ".git")):
        # LF line endings whatever the user's git does (Windows' autocrlf), or the patches do not apply
        run(["git", "-c", "core.autocrlf=false", "clone", "--quiet", up["repo"], p["src"]], log=log)
    run(["git", "config", "core.autocrlf", "false"], cwd=p["src"], log=log)
    run(["git", "fetch", "--quiet", "origin"], cwd=p["src"], log=log)
    run(["git", "checkout", "--quiet", "--force", up["commit"]], cwd=p["src"], log=log)
    # On exFAT, macOS keeps ._ files beside the last build's outputs; git clean failed on them
    # ("could not lstat .../._USCSandbox.assets.cache") on the second build. Remove them first.
    remove_appledouble(p["src"])
    run(["git", "clean", "-fdxq"], cwd=p["src"], log=log)
    patches = sorted(f for f in os.listdir(os.path.join(USCS_DIR, "patches")) if f.endswith(".patch"))
    for f in patches:
        run(["git", "apply", os.path.join(USCS_DIR, "patches", f)], cwd=p["src"], log=log)
    remove_appledouble(p["src"])
    work = os.path.abspath(os.path.expanduser(args.work))
    if os.path.abspath(dotnet).startswith(work + os.sep):
        remove_appledouble(os.path.dirname(dotnet))  # our own SDK copy only, never a system install
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
               DOTNET_ROOT=os.path.dirname(dotnet))
    run([dotnet, "build", "-c", "Release", os.path.join(p["src"], "USCSandbox", "USCSandbox.csproj"),
         "-o", p["bin"]], env=env, log=log)
    shutil.copy(os.path.join(p["src"], "Files", "classdata.tpk"), p["bin"])
    json.dump({"commit": up["commit"], "patches": patches, "dotnet": dotnet},
              open(os.path.join(p["bin"], "build.json"), "w", encoding="utf-8"), indent=2)
    print("Shader decompiler ready (details: %s)" % log)


def uscs(p, dotnet, argv):
    """Run USCSandbox in its own folder: it writes dbg_entry*.bin and out/ into the current folder."""
    os.makedirs(p["run"], exist_ok=True)
    shutil.copy(os.path.join(p["bin"], "classdata.tpk"), p["run"])
    env = dict(os.environ, DOTNET_ROOT=os.path.dirname(dotnet))
    r = subprocess.run([dotnet, os.path.join(p["bin"], "USCSandbox.dll")] + argv, cwd=p["run"], env=env,
                       capture_output=True, text=True, errors="replace")
    for f in os.listdir(p["run"]):
        if f.startswith("dbg_entry"):
            os.remove(os.path.join(p["run"], f))
    return r


def parse_listing(text):
    """'  Shader Forge/Object (path id 13)' lines -> [(name, path id)]."""
    out = []
    for line in text.splitlines():
        m = LIST_RE.match(line)
        if m:
            out.append((m.group(1), int(m.group(2))))
    return out


def output_name(shader_name):
    """File name for a shader: 'Shader Forge/Object' -> 'Shader Forge_Object.shader' (as in shaders/)."""
    return shader_name.replace("/", "_") + ".shader"


def decompile(args):
    p = paths(args.work)
    build_info = json.load(open(os.path.join(p["bin"], "build.json"), encoding="utf-8"))
    dotnet = build_info["dotnet"]
    data = os.path.abspath(os.path.expanduser(args.data))
    files = sorted(f for f in os.listdir(data) if f.endswith(".assets") and not f.startswith("._"))
    index = {}
    for f in files:
        r = uscs(p, dotnet, ["null", os.path.join(data, f)])
        for name, pid in parse_listing(r.stdout):
            index.setdefault(name, {"file": f, "path_id": pid})
    wanted = args.shader or sorted(index)
    missing = [s for s in wanted if s not in index]
    if missing:
        sys.exit("Not found in %s: %s" % (data, ", ".join(missing)))
    os.makedirs(p["out"], exist_ok=True)
    failed = []
    sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
    from core import progress
    lang = progress.language()
    for i, name in enumerate(wanted, 1):
        progress.live("Shaders: %d of %d" % (i, len(wanted)))
        e = index[name]
        r = uscs(p, dotnet, ["null", os.path.join(data, e["file"]), str(e["path_id"])])
        made = os.path.join(p["run"], "out", name + ".shader")
        if r.returncode != 0 or not os.path.isfile(made):
            failed.append(name)
            print("FAILED", name, (r.stderr or r.stdout).strip()[-400:])
            continue
        shutil.move(made, os.path.join(p["out"], output_name(name)))
        e["decompiled"] = output_name(name)
    json.dump({"data": data, "uscs": build_info, "shaders": index},
              open(os.path.join(p["out"], "index.json"), "w", encoding="utf-8"), indent=2)
    print()
    print("%d decompiled, %d failed -> %s" % (len(wanted) - len(failed), len(failed), p["out"]))
    if failed:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--work", required=True)
    b.add_argument("--dotnet")
    d = sub.add_parser("decompile")
    d.add_argument("--work", required=True)
    d.add_argument("--data", required=True, help="the game's _Data folder")
    d.add_argument("--shader", action="append", help="shader name, e.g. 'Shader Forge/Fairy' (repeatable)")
    a = ap.parse_args()
    {"build": build, "decompile": decompile}[a.cmd](a)


if __name__ == "__main__":
    main()
