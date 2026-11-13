#!/bin/bash
# Runs the editor regression and fails if anything is wrong. Usage: run_probe.sh [final|full|Case1,Case2] [log]
# Exit 0 only with a summary line, no failed check and no compile error.
set -u
MODE="${1:-final}"
LOG="${2:-$HOME/lunacid-work/diagnostics/probe_${MODE//,/_}.log}"
PROJECT="$(python3 "$(dirname "$0")/../../core/config.py" project)"
UNITY="$(python3 "$(dirname "$0")/../../core/config.py" unity)"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LIMIT="${LUNA_PROBE_LIMIT:-10800}"
TARGET="$PROJECT/Assets/Scripts/LunaPort/LunaProbe.cs"

# The Python tests first (passes, shader generator, repo cleanliness): two of them had been failing unseen
# since Build 88 because only the editor cases were run (LESSONS 29).
if ! (cd "$REPO" && python3 -m unittest discover -s tests -q >/tmp/luna_py_tests.log 2>&1); then
    tail -20 /tmp/luna_py_tests.log; echo "RESULT: FAIL (Python tests)"; exit 1
fi
echo "Python tests: $(grep -E '^Ran' /tmp/luna_py_tests.log)"
if pgrep -f "MacOS/Unity .*-projectPath $PROJECT" >/dev/null; then echo "FAIL: Unity already has this project open"; exit 2; fi
[ -f "$PROJECT/Temp/UnityLockfile" ] && mv "$PROJECT/Temp/UnityLockfile" "$PROJECT/Temp/UnityLockfile.before_probe"

python3 -c "
import sys; sys.path.insert(0, '$REPO/passes')
import pass_vr_runtime as v
v.apply('$PROJECT'); sys.exit(0 if v.verify('$PROJECT')['passed'] else 1)" || { echo "FAIL: pass_vr_runtime"; exit 2; }
cp "$REPO/tools/editor_checks/LunaProbe.cs" "$TARGET"

LUNA_PROBE="$MODE" perl -e "alarm $LIMIT; exec @ARGV" "$UNITY" -batchmode -accept-apiupdate -projectPath "$PROJECT" \
    -executeMethod LunaProbeRun.Run -logFile "$LOG"

rm -f "$TARGET" "$TARGET.meta"
[ -f "$PROJECT/Temp/UnityLockfile" ] && mv "$PROJECT/Temp/UnityLockfile" "$PROJECT/Temp/UnityLockfile.after_probe"

grep -E "PROBE (CHECK FAIL|EXCEPTION|SUMMARY)" "$LOG" | grep -v "m_Sprite" | sed -E 's/^PROBE //' | cut -c1-240
if grep -q "error CS" "$LOG"; then grep "error CS" "$LOG" | sort -u | cut -c1-200; echo "RESULT: FAIL (compile error)"; exit 1; fi
SUMMARY="$(grep -E "^PROBE SUMMARY" "$LOG" | tail -1)"
if [ -z "$SUMMARY" ]; then echo "RESULT: FAIL (no summary: crashed or cut by the time limit)"; exit 1; fi
if ! echo "$SUMMARY" | grep -q "failed=0$"; then echo "RESULT: FAIL ($SUMMARY)"; exit 1; fi
echo "RESULT: PASS ($SUMMARY)"
