#!/bin/bash
# Host-side companion of passes/pass_diag_renderer_audit.py.
# Installs the APK, launches it, and screenshots the Quest after every
# `STAGE_DONE <name>` marker the runtime audit prints. Pulls luna_audit.log at the end.
#
# Usage: tools/diag_audit_capture.sh [apk] [out_dir]
# Put the headset on (or cover the proximity sensor) so the app keeps rendering.

set -u
APK="${1:-$(python3 "$(dirname "$0")/../core/config.py" builds)/Lunacid_Quest.apk}"
OUT="${2:-$HOME/lunacid-work/diagnostics/audit_$(date +%H%M%S)}"
PKG="com.AkumaKira.LunacidVR"
mkdir -p "$OUT"

DEVICE=$(adb devices | awk '$2=="device"{print $1; exit}')
[ -z "$DEVICE" ] && { echo "No Quest in 'device' state (accept USB debugging in the headset)"; exit 1; }

if [ -f "$APK" ]; then
    echo "Installing $APK"
    adb -s "$DEVICE" install -r -d -g "$APK" || exit 1
fi

adb -s "$DEVICE" shell am force-stop "$PKG"
adb -s "$DEVICE" logcat -c
adb -s "$DEVICE" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
echo "Launched. Waiting for audit stages (about 45s)... output: $OUT"

# Stop after the final stage or after 120s.
( sleep 120; pkill -P $$ -f "logcat -s LUNA_AUDIT" 2>/dev/null ) &
adb -s "$DEVICE" logcat -v time -s LUNA_AUDIT:I | while read -r line; do
    echo "$line" >> "$OUT/logcat_audit.log"
    case "$line" in
        *STAGE_DONE*)
            name=$(echo "$line" | sed -E 's/.*STAGE_DONE ([a-z_]+).*/\1/')
            sleep 1
            # `adb shell screencap` returns pure black on Quest (compositor layer is not captured);
            # the Meta capture service writes the real composited frame to /sdcard/Oculus/Screenshots.
            adb -s "$DEVICE" shell am startservice -n com.oculus.metacam/.capture.CaptureService -a TAKE_SCREENSHOT >/dev/null 2>&1
            sleep 2
            newest=$(adb -s "$DEVICE" shell 'ls -t /sdcard/Oculus/Screenshots | head -1' | tr -d '\r')
            adb -s "$DEVICE" pull "/sdcard/Oculus/Screenshots/$newest" "$OUT/stage_${name}.jpg" >/dev/null 2>&1
            echo "captured stage_${name}.jpg ($newest)"
            [ "$name" = "final" ] && break
            ;;
    esac
done

adb -s "$DEVICE" pull "/sdcard/Android/data/$PKG/files/luna_audit.log" "$OUT/luna_audit_full.log" 2>&1 | tail -1
echo "Done. Results in $OUT"
