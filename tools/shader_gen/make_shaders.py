#!/usr/bin/env python3
"""
Make the port's shaders from the user's own copy of the game, in one command:
build USCSandbox (once), decompile every shader in the game's .assets, generate the port versions,
and check that every shader the port needs (port_shaders.json) came out.

  python3 tools/shader_gen/make_shaders.py --work ~/lunacid-work --data /path/to/LUNACID_Data [--dotnet PATH] [--rebuild]

Then point the pipeline at the result (pass_shader_stubs reads it):
  LUNA_SHADER_SOURCE=<work>/shader_gen/generated  python3 core/runner.py apply <ExportedProject>
Runs on macOS and Windows (Python 3, git, .NET 8 SDK).
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def step(args, label=None):
    """Run one stage; the screen gets a plain sentence, not the command line."""
    print("\n" + (label or " ".join(os.path.basename(a) if i == 0 else a for i, a in enumerate(args))), flush=True)
    res = subprocess.run([sys.executable] + args)
    if res.returncode:
        sys.exit(res.returncode)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--data", required=True, help="the game's _Data folder")
    ap.add_argument("--dotnet")
    ap.add_argument("--rebuild", action="store_true", help="build USCSandbox again even if it is built")
    a = ap.parse_args()

    root = os.path.join(os.path.abspath(os.path.expanduser(a.work)), "shader_gen")
    build_json = os.path.join(root, "uscs_bin", "build.json")
    pin = json.load(open(os.path.join(HERE, "uscs", "UPSTREAM.json"), encoding="utf-8"))
    patches = sorted(f for f in os.listdir(os.path.join(HERE, "uscs", "patches")) if f.endswith(".patch"))
    built = None
    if os.path.isfile(build_json):
        built = json.load(open(build_json, encoding="utf-8"))
    if a.rebuild or not built or built.get("commit") != pin["commit"] or built.get("patches") != patches:
        cmd = [os.path.join(HERE, "uscs.py"), "build", "--work", a.work]
        if a.dotnet:
            cmd += ["--dotnet", a.dotnet]
        step(cmd, "Building the shader decompiler (once, about a minute)...")
    else:
        print("USCSandbox already built with the pinned commit and patches")

    step([os.path.join(HERE, "uscs.py"), "decompile", "--work", a.work, "--data", a.data],
         "Reading the game's shaders from your copy...")
    step([os.path.join(HERE, "generate.py"), "--work", a.work], "Making the Quest versions of the shaders...")

    gen = os.path.join(root, "generated")
    wanted = json.load(open(os.path.join(HERE, "port_shaders.json"), encoding="utf-8"))["shaders"]
    missing = [f for f in wanted if not os.path.isfile(os.path.join(gen, f))]
    if missing:
        sys.exit("Missing for the port: " + ", ".join(missing))
    print("\n%d of %d port shaders made in %s" % (len(wanted), len(wanted), gen))



if __name__ == "__main__":
    main()
