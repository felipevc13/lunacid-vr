#!/bin/bash
# Records the headset log to a folder on the Mac for a whole test session.
# Unity's Android build restarts the adb server, which ends a plain `adb logcat`; this loop waits for
# the device and resumes from the newest line each time, appending to the same files.
#   full.log     everything (adb logcat -v time)
#   session.log  port and compositor lines (LUNA, VrApi, Unity, crashes): tools/telemetry/scene_telemetry.py
# Usage: tools/telemetry/record_session.sh <output folder>
set -u
OUT=${1:?output folder}
mkdir -p "$OUT"
while true; do
  adb wait-for-device
  adb logcat -v time -T 1 | tee -a "$OUT/full.log" | grep --line-buffered -E "LUNA|VrApi|Unity|AndroidRuntime|FATAL" >> "$OUT/session.log"
  sleep 2
done
