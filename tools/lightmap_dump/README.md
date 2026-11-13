# Lightmap dump (original PC game)

AssetRipper's lightmap EXRs are darkened (sRGB→linear applied to HDR data and to the direction
maps). `LunaLightmapDump.cs` takes them from the running original game instead, decoded by the
GPU, so the port gets exactly what the PC shaders sample.

Build the plugin (same references as `tools/tour`, plus nothing else):

```bash
GAME=<the PC game folder, with BepInEx in it>   # development only
U=/Applications/Unity/Hub/Editor/6000.0.85f1/Unity.app/Contents; M=$GAME/LUNACID_Data/Managed; B=$GAME/BepInEx/core
"$U/NetCoreRuntime/dotnet" "$U/DotNetSdkRoslyn/csc.dll" -nologo -nostdlib -target:library -out:$GAME/BepInEx/plugins/LunaLightmapDump.dll -r:$M/mscorlib.dll -r:$M/System.dll -r:$M/System.Core.dll -r:$M/netstandard.dll -r:$M/UnityEngine.dll -r:$M/UnityEngine.CoreModule.dll -r:$M/UnityEngine.ImageConversionModule.dll -r:$B/BepInEx.dll tools/lightmap_dump/LunaLightmapDump.cs
```

List scenes (one per line) in `BepInEx/lmdump/request.txt` and start the game; it writes
`BepInEx/lmdump/<scene>/Lightmap-N_comp_*.exr` and `all_done.txt`. Delete `request.txt` to play
normally. Run it outside October: in October `HALLO.cs` swaps HUB_01's lightmap for the
Halloween one. `passes/pass_lightmap_import.py` copies the dumps over AssetRipper's files when
the game profile sets `lightmap_dump_dir`.

## Light probes (`LunaProbeDump.cs`)

Writes what the original game lights dynamic objects with: the ambient settings,
`RenderSettings.ambientProbe`, every baked probe, and the SH each probe-lit renderer gets. With
renderer names in `BepInEx/probedump/test.txt`, it also renders a sphere with each one's material,
probes Off and BlendProbes, into PNGs and mean colours, to compare with the same render in Unity 6.

```bash
U=/Applications/Unity/Hub/Editor/6000.0.85f1/Unity.app/Contents; M=$GAME/LUNACID_Data/Managed; B=$GAME/BepInEx/core
"$U/NetCoreRuntime/dotnet" "$U/DotNetSdkRoslyn/csc.dll" -nologo -nostdlib -target:library -out:$GAME/BepInEx/plugins/LunaProbeDump.dll -r:$M/mscorlib.dll -r:$M/System.dll -r:$M/System.Core.dll -r:$M/netstandard.dll -r:$M/UnityEngine.dll -r:$M/UnityEngine.CoreModule.dll -r:$M/UnityEngine.ImageConversionModule.dll -r:$M/UnityEngine.PhysicsModule.dll -r:$B/BepInEx.dll tools/lightmap_dump/LunaProbeDump.cs
```

List scenes in `BepInEx/probedump/request.txt` and start the game. Move `BepInEx/tour/request.txt` aside
first, or the tour runs too. It writes `<scene>_6s.txt`, `<scene>_15s.txt` (the ambient changes once a
`Lighting_Zone` trigger fires) and `all_done.txt`. Used on 2026-11-10 to show the port's probes equal
the PC's (LESSONS 26).
