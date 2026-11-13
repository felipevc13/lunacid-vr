#!/bin/bash
# Runs LunaTour in the Unity editor (no build, no headset): the same camera shots as the PC tour.
# Usage: editor_tour.sh <plans_dir> <out_dir> [scene ...]
# Copies plan_<scene>.txt for each scene (all plans if none given) into the editor's
# persistentDataPath/tour, plays the project, waits for all_done.txt and moves the shots to <out_dir>.
# The editor renders on the desktop GPU, mono: good for comparing shader maths, not Quest performance.
set -u
PLANS="$1"; OUT="$2"; shift 2
PROJECT="$(python3 "$(dirname "$0")/../../core/config.py" project)"
UNITY="$(python3 "$(dirname "$0")/../../core/config.py" unity)"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="${LUNA_EDITOR_DATA:-$HOME/Library/Application Support/AkumaKira/Lunacid}"
LIMIT="${LUNA_TOUR_LIMIT:-3600}"
TOUR="$DATA/tour"
PROBE="$PROJECT/Assets/Scripts/LunaPort/LunaProbe.cs"

if pgrep -f "MacOS/Unity .*-projectPath $PROJECT" >/dev/null; then echo "FAIL: Unity already has this project open"; exit 2; fi
python3 -c "
import sys; sys.path.insert(0, '$REPO/passes')
import pass_tour_runtime as t
t.apply('$PROJECT'); sys.exit(0 if t.verify('$PROJECT')['passed'] else 1)" || { echo "FAIL: pass_tour_runtime"; exit 2; }
rm -rf "$TOUR"; mkdir -p "$TOUR" "$OUT"
if [ $# -eq 0 ]; then cp "$PLANS"/plan_*.txt "$TOUR/"; else for s in "$@"; do cp "$PLANS/plan_$s.txt" "$TOUR/" || exit 2; done; fi
# LunaProbe.cs holds LunaProbeRun.Run (enter play mode); without LUNA_PROBE it does nothing else.
cp "$REPO/tools/editor_checks/LunaProbe.cs" "$PROBE"
[ -f "$PROJECT/Temp/UnityLockfile" ] && mv "$PROJECT/Temp/UnityLockfile" "$PROJECT/Temp/UnityLockfile.before_tour"

"$UNITY" -batchmode -projectPath "$PROJECT" -executeMethod LunaProbeRun.Run -logFile "$OUT/editor_tour.log" &
PID=$!
START=$(date +%s)
while kill -0 $PID 2>/dev/null; do
    [ -f "$TOUR/all_done.txt" ] && break
    [ $(( $(date +%s) - START )) -gt "$LIMIT" ] && { echo "FAIL: time limit"; break; }
    sleep 10
done
kill $PID 2>/dev/null; sleep 5; kill -9 $PID 2>/dev/null
rm -f "$PROBE" "$PROBE.meta"
[ -f "$PROJECT/Temp/UnityLockfile" ] && mv "$PROJECT/Temp/UnityLockfile" "$PROJECT/Temp/UnityLockfile.after_tour"

# No trailing slash on the source: macOS cp would merge every scene's shots into one folder.
for d in "$TOUR"/*/; do [ -d "$d" ] && cp -R "${d%/}" "$OUT/"; done
DONE=0; [ -f "$TOUR/all_done.txt" ] && DONE=1
# Plans left here would make every later editor run (the probe too) start a tour.
rm -rf "$TOUR"
grep -E "error CS" "$OUT/editor_tour.log" | sort -u | head
N=$(find "$OUT" -name "quest_*.png" | wc -l | tr -d ' ')
[ $DONE -eq 1 ] && echo "RESULT: done, $N shots in $OUT" || { echo "RESULT: FAIL ($N shots in $OUT)"; exit 1; }
