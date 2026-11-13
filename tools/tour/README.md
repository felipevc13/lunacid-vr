# Comparison tour (PC original vs Quest port)

`LunaTour.cs` takes the same camera shots in both games so they can be compared side by side
without playing. Shots are 1280x720, rendered from the world camera into an sRGB render texture.

## 1. PC: plan and shoot (original game under CrossOver, see `tools/pc_reference/README.md`)

Build the plugin:

```bash
GAME=<the PC game folder, with BepInEx in it>   # development only
U=/Applications/Unity/Hub/Editor/6000.0.85f1/Unity.app/Contents; M=$GAME/LUNACID_Data/Managed; B=$GAME/BepInEx/core
"$U/NetCoreRuntime/dotnet" "$U/DotNetSdkRoslyn/csc.dll" -nologo -nostdlib -define:BEPINEX -target:library -out:$GAME/BepInEx/plugins/LunaTour.dll -r:$M/mscorlib.dll -r:$M/System.dll -r:$M/System.Core.dll -r:$M/netstandard.dll -r:$M/UnityEngine.dll -r:$M/UnityEngine.CoreModule.dll -r:$M/UnityEngine.PhysicsModule.dll -r:$M/UnityEngine.ParticleSystemModule.dll -r:$M/UnityEngine.ImageConversionModule.dll -r:$M/UnityEngine.JSONSerializeModule.dll -r:$M/UnityEngine.AnimationModule.dll -r:$M/UnityEngine.ScreenCaptureModule.dll -r:$B/BepInEx.dll tools/tour/LunaTour.cs
```

Write the scene names to `BepInEx/tour/request.txt`, one per line (e.g. `MainMenu`, `HUB_01`),
and start the game. About 20 s after boot the plugin tours them in order: it loads each scene,
writes `BepInEx/tour/plan_<scene>.txt` unless it exists (lights and renderers with
alpha/transparent materials, at least 6 m apart, max 24, camera placed with a clear line of
sight; MainMenu gets one shot from the game's own camera) and saves
`BepInEx/tour/<scene>/pc_NN.png`; then `all_done.txt`, and quits. Delete `request.txt` to play normally.

The game changes with the date: in October `HALLO.cs` adds the Halloween decoration and
lightmap, and `Moon_scr.cs` sets the moon phase. Take the PC shots close to the Quest run.

## 2. Quest: same shots

`passes/pass_tour_runtime.py` copies `LunaTour.cs` into the project. Build with the scene:
`LUNA_EXTRA_SCENES=HUB_01 bash ~/lunacid-work/scripts/build_menu_apk.sh`. Then:

```bash
F=/sdcard/Android/data/com.AkumaKira.LunacidVR/files/tour; adb shell mkdir -p $F; adb push $GAME/BepInEx/tour/plan_HUB_01.txt $F/
```

Launch the app (the headset must be awake: a Guardian or lock-screen dialog holds it in the
background): it tours every `plan_<scene>.txt` in name order, writes `quest_NN.png` into
`$F/<scene>/`, then `all_done.txt`, and quits. Remove the plan files to get the normal game back.

Unattended: `tools/tour/quest_tour.sh <plans_dir> <out_dir> [apk]` pauses the Guardian, makes the
headset act as worn (`vrpowermanager.prox_close`, re-sent every minute) so it does not sleep, pushes
the plans, runs the tour, pulls the results, and restores both settings on exit.

Faster builds for runtime-only changes: build once with `LUNA_SPLIT_OBB=1` (scenes and assets go to
`Lunacid_Quest.main.obb` beside a small APK), then rebuild code with `LUNA_SPLIT_OBB=1 LUNA_SCRIPTS_ONLY=1`
and the same `LUNA_EXTRA_SCENES`. `quest_tour.sh` installs the APK and pushes the OBB only when it changed.
