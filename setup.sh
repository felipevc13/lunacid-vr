#!/bin/bash
# Lunacid VR for macOS: from nothing to the game on your Quest.
#
# Open Terminal (Cmd+Space, type Terminal, press Return) and paste this line:
#
#   curl -fsSL https://raw.githubusercontent.com/felipevc13/lunacid-vr/main/setup.sh | bash
#
# Inside a copy of this repository you can also run:  bash setup.sh
#
# It installs Apple's command line tools when missing (they bring Git and Python), gets this project, and hands
# over to "lunacid_vr.py start", which does the rest and asks only what only you can answer.
# Run it again at any time: finished steps are skipped.

set -e
REPO_URL="https://github.com/felipevc13/lunacid-vr.git"

say() { printf '\033[36m%s\033[0m\n' "$1"; }

say "Lunacid VR: getting this computer ready."

if ! xcode-select -p >/dev/null 2>&1 || ! /usr/bin/python3 --version >/dev/null 2>&1; then
    say "Installing Apple's command line tools (they bring Git and Python). A window opens: choose Install and wait."
    xcode-select --install >/dev/null 2>&1 || true
    until xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 --version >/dev/null 2>&1; do sleep 10; done
fi

# This project: the copy this script is in, or one in your home folder (cloned the first time, updated after).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && [ -f "$HERE/lunacid_vr.py" ]; then
    DIR="$HERE"
else
    DIR="$HOME/lunacid-vr"
    if [ -d "$DIR/.git" ]; then
        git -C "$DIR" pull --ff-only
    else
        say "Downloading Lunacid VR..."
        git clone "$REPO_URL" "$DIR"
    fi
fi

cd "$DIR"
exec /usr/bin/python3 lunacid_vr.py start < /dev/tty
