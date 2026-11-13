# shader_gen: the game's shaders, made on each user's machine

The port needs the game's own shaders (Shader Forge and others), rewritten for Unity 6 and the Quest's
stereo rendering. Their formulas come from the game, so they cannot sit in a public repository.
This folder makes them on the user's machine, from their own copy of the game.

```
LUNACID_Data/*.assets ──uscs.py decompile──▶ <work>/shader_gen/decompiled/*.shader   (HLSL, every PC variant)
                                             │
                          generate.py ───────▶ <work>/shader_gen/generated/*.shader    (Unity 6, VR, Quest)
```

Nothing under `<work>` is ever committed. `tests/test_shader_gen.py` fails if a generated shader
shows up in the repository.

## What lives where

| Path | What | Licence |
|---|---|---|
| `uscs.py` | Builds USCSandbox and runs it on the game's `.assets` files | ours |
| `uscs/UPSTREAM.json` | USCSandbox repository and the pinned commit | — |
| `uscs/patches/*.patch` | Our fixes to USCSandbox, applied at build time | GPL-3.0, like USCSandbox |
| `generate.py` | Decompiled shader → port shader (variants, keywords, stereo, Unity 6 rules) | ours |
| `rules/*.json` | Per-shader changes the port needs (see "Port rules") | ours |
| `compile_check.py`, `visual_check.py`, `unity_check/*.cs` | Compile and render checks in a throwaway Unity 6 project | ours |
| `tests/test_shader_gen.py` | Tests on a hand-written shader, no game content | ours |

USCSandbox (<https://github.com/nesrak1/USCSandbox>, GPL-3.0) runs as a separate program. It is
downloaded and built on the user's machine, never copied into this repository. Only our patches
are stored here, with their own GPL-3.0 notice.

## Running it

Needs Python 3, `git` and the .NET 8 SDK, on macOS or Windows. To install the SDK without admin
rights, into the work folder:

```bash
# macOS / Linux
curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh
bash /tmp/dotnet-install.sh --channel 8.0 --install-dir ~/lunacid-work/tools/dotnet
```

```powershell
# Windows (PowerShell)
Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile $env:TEMP\dotnet-install.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\dotnet-install.ps1 -Channel 8.0 -InstallDir $HOME\lunacid-work\tools\dotnet
```

`uscs.py` finds `dotnet` on the PATH or in `<work>/tools/dotnet`; `--dotnet` overrides both.

Unity 6's own `NetCoreRuntime` cannot build it: that is .NET 6 with a C# 11 compiler, and
USCSandbox uses C# 12.

All in one (builds USCSandbox once, then decompiles and generates, and checks every shader in
`port_shaders.json` came out):

```bash
python3 tools/shader_gen/make_shaders.py --work ~/lunacid-work --data /path/to/LUNACID_Data
```

Or step by step:

```bash
python3 tools/shader_gen/uscs.py build --work ~/lunacid-work
python3 tools/shader_gen/uscs.py decompile --work ~/lunacid-work --data /path/to/LUNACID_Data
python3 tools/shader_gen/generate.py --work ~/lunacid-work [--shader 'Shader Forge/Fairy']
```

On an exFAT disk, macOS writes `._name` files next to everything, and they break both the C# build
and the .NET SDK. `uscs.py` deletes them in the folders it owns.

### Using them in the port

`passes/pass_shader_stubs.py` copies the protected shader overrides into `Assets/Shader/`. By
default they come from the repo's `shaders/`, exactly as before. To take them from the generator:

```bash
LUNA_SHADER_SOURCE=~/lunacid-work/shader_gen/generated python3 core/runner.py apply /path/to/ExportedProject
```

The profile key `"shader_source"` works too; the environment variable wins. Every file in
`port_shaders.json` then comes from that folder, and the run fails if one is missing. The repo's own
shaders (`Lunacid_VR_Fallback*`, which have no game counterpart) still come from `shaders/`. Remove the
variable and the next run puts `shaders/` back.

Tried on a copy of the port's `Assets/Shader` (2026-11-10): 43 files swapped. `Heatwave` and
`VolumetricCloud3` stayed the same (the generated one is ours). No other stub was touched, and
`verify` passes. The port's project itself was not touched.

`port_shaders.json` also lists `candidates`: game shaders the port still covers with generic stubs
(`Shader Forge/Goblin`, `MIRROR`, `Object_Clip`, `Object_glow`, `swim_shady`, the PIDI blur, two
ProBuilder ones). The generator makes them too; moving one to `shaders` changes what is on screen, so
each needs a look first. Post-processing and RetroLookPro also exist as stubs in the project: they go
through the port's own post-processing handling and are not candidates yet.

### Windows

- **What was tested**, under Wine 11 on the Mac, with the Windows builds of Python 3.12, Git 2.47
  (MinGit) and the .NET 8.0.427 SDK:
  - `uscs.py build` cloned USCSandbox at the pinned commit and applied the 3 patches.
  - `uscs.py decompile` with the Windows .NET runtime.
  - `generate.py`.
  - `tests/test_shader_gen.py`: 26 of 26 pass.
  - The decompiled and generated `Fairy`, `Water_Flow` and `Object` are identical to the Mac ones apart
    from line endings (CRLF on Windows, which Unity reads).
- **Not tested on Windows:**
  - `dotnet build`, the C# compile of USCSandbox. MSBuild crashes under Wine, a known Wine limit,
    which says nothing about Windows itself. The decompile above used the `USCSandbox.dll` built on the
    Mac; the .NET IL is the same on both.
  - `compile_check.py` and `visual_check.py`, which need Unity for Windows.
- **What the scripts do for Windows:**
  - Every file is opened as UTF-8, not cp1252.
  - The SDK is looked for as `dotnet.exe`.
  - USCSandbox is cloned with `core.autocrlf=false`, and `.gitattributes` keeps our `.patch` files
    byte for byte, so the patches apply whatever the user's git does with line endings.
  - The Unity binary is found in `Editor\Unity.exe`.
- **Paths:** shader names have no character Windows forbids in file names (checked on all 133). The
  longest is 67 characters. Keep `<work>` short on Windows: the Unity test project's `Library`
  nests deep.

## Our patches to USCSandbox

1. `0001`: when two textures share one sampler, the read was named after the sampler. The
   directional lightmap read `unity_Lightmap` twice instead of `unity_LightmapInd` then
   `unity_Lightmap` (checked against the DXBC of `Shader Forge/Object`).
2. `0002`: the last variant of each stage was a bare `#else`, losing its keywords. The generator
   needs them.
3. `0003`: a constant-buffer read that takes all four components lost its swizzle. The DXBC
   `mad(r1.xxxx, cb3[1].zzzz, cb3[1].wwww)` came out as `x * unity_FogParams + unity_FogParams`. It
   changed 30 of the 133 shaders (`ShineySurf`, `Hair`, `MLGS`, `Light_Spot`, post-processing `Uber`...).
   Found by the render comparison (PIDI World Based Fog) and confirmed with `dxbc_dump.py`.
4. `0004`: DXBC `log` is base 2; it was written as HLSL `log()` (natural). Every `pow()` and the
   ambient's gamma step went wrong: 22 of 133 shaders, among them `Object`, `Hair`, `Mix`.

## What generate.py does

- **Variants.** Shader Forge declares `LIGHTMAP_OFF LIGHTMAP_ON`, `DIRLIGHTMAP_OFF COMBINED SEPARATE` and
  `DYNAMICLIGHTMAP_OFF ON` on top of Unity's keywords. That gives variants no renderer uses, such as
  `LIGHTMAP_OFF` together with `LIGHTMAP_ON`. They are dropped, and the `*_OFF` keywords are removed.
  Each remaining variant becomes a `#if defined(...)` branch, most keywords first. A keyword outside
  Unity's set for the pass is dropped when no variant's code changes with it.
- **Keywords.** The pass uses Unity's own sets, as the game was built (`multi_compile_fwdbase`,
  `_fwdadd`, `_shadowcaster`, `_fog`), with `skip_variants` for keywords the game never compiled.
- **Stereo.** The single-pass instanced and multiview macros go into `appdata`, `v2f`, `vert` and `frag`.
  `unity_MatrixVP`, `_WorldSpaceCameraPos` and `unity_ObjectToWorld` already become per-eye values in
  Unity 6.
- **Unity 2020 PC → Unity 6 Quest.** `DecodeLightmap` is added after each lightmap read (the PC's
  lightmaps needed no decoding). `glstate_lightmodel_ambient`, which held half the ambient colour in
  Unity 2020, becomes `unity_AmbientSky * 0.5`. `rsqrt(x)` becomes `rsqrt(max(x, 1e-12))`: on Vulkan a
  zero vector normalised gives NaN (the port's old `LunaSafeNormalize`). The light probe proxy volume
  variables are declared when used, since mobile does not declare them.

## Port rules (`rules/<shader file>.json`)

The changes the port needs on top of the original, written with property names and Unity terms only,
never the game's formulas. Each file has a `why`.

| Key | Does |
|---|---|
| `properties`, `declare` | Port-only properties and their uniforms |
| `subshader_tags` | Set or add SubShader tags (`Queue`, `DisableBatching`) |
| `pass_state` | Replace or add `Blend`/`ZWrite`/… in the pass with that LightMode |
| `vertex_color` | `white`, or `property:_Name` (white unless the property is 1): Vulkan sends 0 for meshes without colours |
| `replace_when` | Regex replace in the branches of a pass that have the given keywords |
| `frag_wrapper` | Renames the game's `frag` to `frag_game` and adds ours around it |
| `use_repo_shader` | Our own shader instead of the game's (passes that draw nothing on the Quest) |

Today: `Object` (puddle mode), `ghost` (vertex colour switch), `Mix` (no realtime N.L on lightmapped
surfaces), `Water`/`Water_alt` (Queue Transparent-10), `flame_bill` (DisableBatching), `Heatwave` and
`VolumetricCloud3` (ours, draw nothing).

## Checking that they compile

```bash
python3 tools/shader_gen/compile_check.py --work ~/lunacid-work --unity /Applications/Unity/Hub/Editor/6000.0.85f1 \
    --project ~/lunacid-shader-compile-test [--shader NAME ...] [--max-sets 6] [--all-sets NAME ...] [--compare shaders]
```

This creates an empty Unity 6 project (never the port's own project) and copies the generated
shaders into it. `unity_check/ShaderCompileCheck.cs` compiles each pass for Vulkan/Android with
`ShaderData.Pass.CompileVariant`, with and without `STEREO_MULTIVIEW_ON` (the Quest's single-pass
stereo). Errors are printed grouped by message. `--compare DIR` also compiles the hand-written
shaders of the same names and prints the SPIR-V size of both.

**The project must be on an APFS disk.** On exFAT, Unity's asset database (LMDB) crashes while the
project is being created (`MDB_BAD_RSLOT`).

## Status (2026-11-10)

- All 133 shaders in the game's `.assets` decompile, and all 133 generate.
- **Compile, Unity 6000.0.85f1, Vulkan, Android:** 126 shaders have compilable passes. The other 7 are
  compute-based post-processing and `UI/Unlit/Transparent`. **121 of the 126 compile with no errors**,
  each keyword set with and without stereo. **All 45 game shaders in `shaders/` compile.** The 5 that
  fail are not in `shaders/`: four hit a USCSandbox for-loop bug (undeclared `i`), and
  `VR/SpatialMapping/Wireframe` is a geometry shader.
- **Render, generated vs `shaders/`** (`visual_check.py`, same sphere, textures and lights, dynamic and
  lightmapped): **37 of 45 identical** (mean difference ≤ 0.1/255), after patch 0004 and the VFACE rule
  (2026-11-10, see "The brighter characters" below). In the other 8 the generated shader is the game's
  original, and the version in `shaders/` departs from it. Each one, with the evidence:

| Shader | Why `shaders/` differs | Evidence | Check at integration |
|---|---|---|---|
| `Moon_shader` | Approximation tuned from a capture | Original: `Blend One One`, `ZWrite On`, 2 passes; additive, so the dark craters let the sky through, as the approximation tried to imitate | Sky moon over the clouds (MOON scenes) |
| `Moon_Reflection` | "Approximation of the original" (its header) | Original `Cull Back`; ours `Cull Off`. Nothing in the history asks for `Cull Off` | Reflection quad under MOON2 still visible |
| `Fade to Image` | "Approximation of the original" (its header) | Original is a fullscreen overlay (`Overlay+1`, `ZTest Always`, `Blend Off`) that fades by its own maths | Intro stills fade in and out |
| `Gamma` | Written after Build 3, where an opaque stub covered the menu | Original is the same kind of fullscreen pass (`Overlay+1`, `ZTest Always`, `ZWrite Off`), with contrast, posterise and fade, not `pow(1/_GAMMA)` | Menu brightness and fade, and whether it is drawn by `Graphics.Blit` in stereo |
| `Ignore_Fog` | Generic override from the vertex-colour fixes (Oct 29-31) | Original does not read vertex colour; Queue AlphaTest | — |
| `Object_DBL` | Same generic override | Original is transparent (`Blend SrcAlpha OneMinusSrcAlpha`), does not read vertex colour | Double-sided props draw in the right order |
| `Hair` (lightmapped only) | Transcription has no lightmap path | Original has the lightmap variants; ours lights lightmapped hair as dynamic. Dynamic hair is identical | Hair in lightmapped scenes |
| `Oil` | Transcription rotates 90° off | Original is Shader Forge's rotator `(x·cos + y·sin, −x·sin + y·cos)`; ours swaps sin and cos | — (it keeps turning; barely visible) |
| `ITEM_FLARE` | Transcription has no ForwardAdd pass | Identical with the point light off; the original adds point lights to the glow | Item glow near torches |

  Port changes in `shaders/` that the sphere render cannot show (vertex colour 0 on Vulkan, puddle
  mode, Queue, batching, Heatwave/VolumetricCloud3) are in `rules/`. Every shader whose original reads
  vertex colour also reads it in `shaders/`, apart from `ghost` (rule) and `Heatwave` (ours), so the
  switch brings no new vertex-colour risk. Render state (Queue, Blend, ZWrite, Cull, ZTest) differs
  only in the 6 approximations above; the other extra passes in the generated shaders are the
  original's ShadowCaster and ForwardAdd passes.

### The brighter characters (2026-11-10)

In the port's editor (main session, `tools/tour/editor_tour.sh`), the generated shaders made dynamic
characters brighter than on the PC: the FOREST_A1 dryad (Patchi), the HUB_01 witch. The old `shaders/`
matched the PC.

- **The probe data is the same everywhere.**
  - HUB_01's 905 baked probes: the running PC game (`tools/lightmap_dump/LunaProbeDump.cs`) and the
    port's `LightProbes.asset` from AssetRipper agree to 5e-9.
  - Flat ambient: from the colour a `Lighting_Zone` sets, FOREST_A1 (0.3608, 0.4, 0.2392), Unity
    2020 on the PC and Unity 6 both build `ambientProbe` = sRGB→linear of the colour (0.10702,
    0.13287, 0.04667), equal to the last digit.
  - So the data needs no conversion pass.
- **The shader was wrong: a fourth USCSandbox defect.**
  - The DXBC `log` instruction is base 2. USCSandbox wrote it as HLSL `log()`, the natural log.
  - The original's linear→gamma step of the ambient (`log`, `× 0.4166667`, `exp2`) became `x^0.289`
    instead of `x^(1/2.4)`.
  - Measured in Unity 6 with a white texture, it fits that formula exactly (ambient 0.1 → 0.224, 0.36
    → 0.498).
  - Fixed by patch 0004 (`log2`). It changed 22 of the 133 shaders, among them `Object`, `Hair` and
    `Mix`.
- **Result.** The dryad's own material (`Patchi_mat`), the same sphere and the PC's ambient give these
  mean pixels:

  | | R | G | B |
  |---|---|---|---|
  | PC game (original shader) | 30.96 | 48.76 | 24.93 |
  | Unity 6, generated after the fix | 30.28 | 48.01 | 24.55 |
  | Unity 6, `shaders/` | 30.27 | 48.00 | 24.54 |
  | Unity 6, generated before the fix | 41.77 | 64.13 | 39.08 |

- **Correction.** Our transcriptions never lacked the gamma step: in a gamma-space project Unity's
  `ShadeSH9` applies it itself (measured: `unity_SHAr.w` 0.106, `ShadeSH9` 0.361). The earlier "darker
  ambient" finding against `Object`, `Hair` and `Mix` was the `log` defect seen from the other side.
- **Front faces.** Also found: the decompiled code reads the face side as `uint facing: VFACE`
  (D3D11). In Unity, VFACE is a float, negative on back faces, so the normal never flipped. The
  generator now writes `float facing : VFACE` and `facing.x > 0.0`. This affects `Hair`, `Object_DBL`,
  `Clouds`, `GlowWave` and `Wind`; `Hair`'s inside was dark.
- **Size against `shaders/`:** median 1.01×. Size is not speed; the Quest has not been measured.
- **Not checked yet:** a real scene (game meshes, materials, lightmaps) and the Quest itself. Both need
  the generated shaders in the port's project: that is the next step, for the main session.
