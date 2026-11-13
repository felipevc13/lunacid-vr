# PC reference screenshots (original game under CrossOver on the Mac)

Original Windows build: `$GAME`, the PC game's folder (Unity 2020.3.4f1, Mono).
CrossOver 26.3 (`$CROSSOVER`, its `.app`), bottle `Lunacid` in `$BOTTLES`. BepInEx 5.4.23.6
is unpacked into the game folder; the bottle needs `winhttp=native,builtin`.

Build the plugin (Unity's own Roslyn, no extra SDK):

```bash
GAME=<the PC game folder, with BepInEx in it>   # development only
U=/Applications/Unity/Hub/Editor/6000.0.85f1/Unity.app/Contents; M=$GAME/LUNACID_Data/Managed; B=$GAME/BepInEx/core
"$U/NetCoreRuntime/dotnet" "$U/DotNetSdkRoslyn/csc.dll" -nologo -nostdlib -target:library -out:$GAME/BepInEx/plugins/LunaShot.dll -r:$M/mscorlib.dll -r:$M/System.dll -r:$M/System.Core.dll -r:$M/netstandard.dll -r:$M/UnityEngine.dll -r:$M/UnityEngine.CoreModule.dll -r:$M/UnityEngine.ScreenCaptureModule.dll -r:$M/UnityEngine.InputLegacyModule.dll -r:$B/BepInEx.dll tools/pc_reference/LunaShot.cs
```

Run (windowed 1280x720; shots land in `$GAME/BepInEx/shots`):

```bash
cd $GAME && CX_BOTTLE_PATH=$BOTTLES $CROSSOVER/Contents/SharedSupport/CrossOver/bin/wine --bottle Lunacid --cx-app '<the game folder as a Windows path>\LUNACID.exe' -screen-fullscreen 0 -screen-width 1280 -screen-height 720
```

Gotchas: plain Wine 11.0 (Gcenx) crashes in wineboot on macOS 26; x86 binaries on an external
volume stall ~10 min in Rosetta for unsigned Wine (CrossOver on the HD was fine); exFAT
(an exFAT disk) has no symlinks, so bottles/prefixes go on the APFS sparsebundle.
