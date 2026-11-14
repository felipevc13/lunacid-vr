"""A stand-in for another program (keytool, adb) that runs on the Mac and on Windows: a Python script that writes the
given bytes and exits with the given code. On Windows a .cmd starts it; a shell script cannot run there (CI, 2026-11-14)."""
import os
import stat
import sys


def make(folder, name, output, code=0):
    script = os.path.join(folder, name + "_fake.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("import sys\nsys.stdout.buffer.write(%r)\nsys.stdout.flush()\nsys.exit(%d)\n" % (output, code))
    if os.name == "nt":
        program = os.path.join(folder, name + ".cmd")
        with open(program, "w", encoding="ascii") as fh:
            fh.write('@"%s" "%s" %%*\r\n' % (sys.executable, script))
        return program
    program = os.path.join(folder, name)
    with open(program, "w", encoding="utf-8") as fh:
        fh.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, script))
    os.chmod(program, os.stat(program).st_mode | stat.S_IXUSR)
    return program
