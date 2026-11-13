#!/usr/bin/env bash
# Runs a LunaTour round on the Quest, unattended:
#   quest_tour.sh <plans_dir> <out_dir> [apk]
# - optionally installs <apk>;
# - pauses the guardian and makes the headset act as worn (prox_close), so it neither sleeps nor
#   shows the lock screen while the tour runs off-face;
# - pushes every plan_*.txt from <plans_dir> (the previous tour folder is kept as tour_prev);
# - launches the app, logs Unity's logcat to <out_dir>/logcat.txt, re-sends prox_close every minute;
# - waits for all_done.txt, pulls the tour folder into <out_dir>;
# - always restores the guardian and the proximity sensor on exit, even on error or Ctrl-C.
# - on each "LUNA_HUD ready" log line (HUD effect shots) takes a headset screenshot with the system
#   capture service and saves it as <out_dir>/<key>/headset_NN.jpg (what the eyes see).
# If the lock screen still appears (SensorLockActivity), it says so: the user has to unlock it.
set -u
PLANS=${1:?plans dir}; OUT=${2:?out dir}; APK=${3:-}
PKG=com.AkumaKira.LunacidVR
D=/sdcard/Android/data/$PKG/files
mkdir -p "$OUT"

restore() {
    adb shell setprop debug.oculus.guardian_pause 0 >/dev/null 2>&1
    adb shell am broadcast -a com.oculus.vrpowermanager.automation_disable >/dev/null 2>&1
    [ -n "${LOGPID:-}" ] && kill "$LOGPID" 2>/dev/null
    # The screenshot watcher is a subshell running tail | grep | while: stop its children too, or
    # they outlive the tour.
    [ -n "${HUDPID:-}" ] && { pkill -P "$HUDPID" 2>/dev/null; kill "$HUDPID" 2>/dev/null; }
    echo "[quest_tour] guardian and proximity sensor restored"
}
trap restore EXIT

adb get-state >/dev/null 2>&1 || { echo "[quest_tour] no Quest on adb"; exit 1; }
if [ -n "$APK" ]; then
    adb install -r "$APK" | tail -1
    # Split build (LUNA_SPLIT_OBB=1): the scenes and assets live in <apk>.main.obb. Push it only
    # when it changed (its size and time are kept in a stamp beside it on the headset).
    OBB="${APK%.apk}.main.obb"
    if [ -f "$OBB" ]; then
        DEST=/sdcard/Android/obb/$PKG/main.1.$PKG.obb
        # -L: the OBB beside a staged APK is often a link to the build's OBB; stamp the file itself.
        stamp="$(stat -L -f '%z %m' "$OBB")"
        if [ "$(adb shell cat /sdcard/Android/obb/$PKG/.luna_stamp 2>/dev/null | tr -d '\r')" != "$stamp" ]; then
            adb shell mkdir -p /sdcard/Android/obb/$PKG
            adb push "$OBB" "$DEST" | tail -1
            adb shell "echo '$stamp' > /sdcard/Android/obb/$PKG/.luna_stamp"
        else
            echo "[quest_tour] OBB unchanged"
        fi
    fi
fi

awake() {
    adb shell setprop debug.oculus.guardian_pause 1 >/dev/null 2>&1
    adb shell am broadcast -a com.oculus.vrpowermanager.prox_close >/dev/null 2>&1
    adb shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
}
awake

adb shell "rm -rf $D/tour_prev; [ -d $D/tour ] && mv $D/tour $D/tour_prev; mkdir -p $D/tour"
adb push "$PLANS"/plan_*.txt "$D/tour/" | tail -1
adb shell "rm -f $D/tour/._*"

adb logcat -c
adb logcat -s Unity > "$OUT/logcat.txt" &
LOGPID=$!
adb shell am start -n $PKG/com.unity3d.player.UnityPlayerActivity | tail -1

# Headset screenshots for HUD shots: "LUNA_HUD ready <key> <index> <name>".
SHOTS=/sdcard/Oculus/Screenshots
(
    tail -n 0 -F "$OUT/logcat.txt" 2>/dev/null | grep --line-buffered "LUNA_HUD ready" | while read -r line; do
        set -- ${line##*LUNA_HUD ready }
        key=$1; idx=$(printf "%02d" "$2")
        before=$(adb shell ls -t $SHOTS 2>/dev/null | head -1)
        adb shell am startservice -n com.oculus.metacam/.capture.CaptureService -a TAKE_SCREENSHOT >/dev/null 2>&1
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            sleep 0.5
            newest=$(adb shell ls -t $SHOTS 2>/dev/null | head -1 | tr -d '\r')
            [ -n "$newest" ] && [ "$newest" != "$(echo "$before" | tr -d '\r')" ] && break
        done
        mkdir -p "$OUT/$key"
        [ -n "$newest" ] && adb pull "$SHOTS/$newest" "$OUT/$key/headset_$idx.jpg" >/dev/null 2>&1 && echo "[quest_tour] headset screenshot $key $idx"
    done
) &
HUDPID=$!

last=""; warned=0
while ! adb shell ls $D/tour/all_done.txt >/dev/null 2>&1; do
    sleep 60
    awake
    top=$(adb shell dumpsys activity activities 2>/dev/null | grep -m1 topResumed)
    if echo "$top" | grep -q SensorLock; then
        [ $warned = 0 ] && echo "[quest_tour] LOCK SCREEN: unlock the headset"
        warned=1
    else
        warned=0
    fi
    n=$(grep -c "LUNA_TOUR shot" "$OUT/logcat.txt")
    [ "$n" != "$last" ] && echo "[quest_tour] $n shots" && last=$n
done

adb pull $D/tour/. "$OUT/" | tail -1
echo "[quest_tour] done"
