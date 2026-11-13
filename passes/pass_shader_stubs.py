#!/usr/bin/env python3
"""
Pass: Shader Stub Replacement and Library Sync
----------------------------------------------
Detects AssetRipper DummyShaderTextExporter stubs that lack executable SubShaders
(causing pink or completely black rendering in Unity builds).
Generates mobile/stereo-ready ForwardBase and ForwardAdd SubShaders tailored to material
blending rules (Additive, Transparent, Moon, Unlit, Opaque Lit), preserving .meta GUIDs.
Also synchronizes the protected shader overrides into Assets/Shader/. The game's shaders come from
tools/shader_gen, made from the user's own copy of the game, in <work>/shader_gen/generated (<work> is
LUNA_WORK, the profile's "work", or ~/lunacid-work): the default since Build 91, approved on the Quest.
LUNA_SHADER_SOURCE (or the profile's "shader_source") names another folder, or "repo" for the hand-made
transcriptions in shaders/ (development only: the public repository does not carry them). The repo's
own shaders (no game counterpart) always come from shaders/. A development checkout with no generated
shaders falls back to shaders/ with a warning; without them either, the pass stops and says how.
"""

import json
import os
import re
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT_SHADERS = os.path.join(REPO_ROOT, "tools", "shader_gen", "port_shaders.json")


def work_dir(profile=None):
    w = os.environ.get("LUNA_WORK") or (profile or {}).get("work") or "~/lunacid-work"
    return os.path.abspath(os.path.expanduser(w))


def shader_source(profile=None):
    """(folder of generated shaders or None for the repo's shaders/, chosen explicitly?)"""
    src = os.environ.get("LUNA_SHADER_SOURCE") or (profile or {}).get("shader_source")
    if src == "repo":
        return None, True
    if src:
        return os.path.abspath(os.path.expanduser(src)), True
    return os.path.join(work_dir(profile), "shader_gen", "generated"), False


MAKE_HINT = "run: python3 tools/shader_gen/make_shaders.py --work <work> --data <the game's LUNACID_Data>"


def override_sources(profile=None):
    """{shader file name: path to copy from} for every protected override."""
    repo_shaders = os.path.join(REPO_ROOT, "shaders")
    out = {}
    if os.path.isdir(repo_shaders):
        for f in os.listdir(repo_shaders):
            if f.endswith(".shader"):
                out[f] = os.path.join(repo_shaders, f)
    with open(PORT_SHADERS, encoding="utf-8") as fh:
        wanted = json.load(fh)["shaders"]
    gen, explicit = shader_source(profile)
    if gen is None:
        return out
    if not os.path.isdir(gen):
        if explicit:
            raise FileNotFoundError("shader source folder not found: %s (%s)" % (gen, MAKE_HINT))
        if all(f in out for f in wanted):
            print("[shader_stubs] WARNING: no generated shaders in %s; using the transcriptions in shaders/ (%s)" % (gen, MAKE_HINT))
            return out
        raise FileNotFoundError("the game's shaders are not generated yet (looked in %s): %s" % (gen, MAKE_HINT))
    missing = [f for f in wanted if not os.path.isfile(os.path.join(gen, f))]
    if missing:
        raise FileNotFoundError("not generated in %s: %s" % (gen, ", ".join(missing)))
    for f in wanted:
        out[f] = os.path.join(gen, f)
    return out

ADDITIVE_KEYWORDS = ["additive", "light_beam", "item_flare", "fairy", "torchlight", "sunbeam", "glowwave", "radiant", "flame_bill"]
TRANSPARENT_KEYWORDS = ["ghost", "cloud", "hair", "moon_reflection", "reflection", "fog_cube", "smoke", "alpha", "fade", "dust", "heatwave"]
WATER_KEYWORDS = ["water", "poison_water", "slime", "fake_caustics"]
DBL_KEYWORDS = ["dbl", "double"]
MOON_KEYWORDS = ["moon_shader", "casmoon"]
UNLIT_KEYWORDS = ["unlit", "postprocessing", "retrolookpro", "picker", "hidden/", "gamma", "sky", "menupainting", "mix"]

def _build_shader_body(shader_name, shader_type):
    sname_lower = shader_name.lower()
    ignore_fog = "ignore_fog" in sname_lower or "ignore fog" in sname_lower

    if shader_type == "moon":
        return f"""Shader "{shader_name}" {{
    Properties {{
        _MainTex ("MainTex", 2D) = "white" {{}}
        _Color ("Color", Color) = (1,1,1,1)
        _EmissionColor ("Emission Color", Color) = (1,1,1,1)
    }}
    SubShader {{
        Tags {{ "Queue"="Transparent" "IgnoreProjector"="True" "RenderType"="Transparent" }}
        LOD 150
        Blend SrcAlpha OneMinusSrcAlpha
        Cull Off
        Lighting Off
        ZWrite Off

        Pass {{
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            fixed4 _EmissionColor;

            struct appdata {{
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            }};

            struct v2f {{
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_OUTPUT_STEREO
            }};

            v2f vert(appdata v) {{
                v2f o;
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                fixed4 vcol = fixed4(1, 1, 1, 1); // FORCE white - Vulkan sends (0,0,0,0) for missing vertex colors
                o.color = vcol * _Color * _EmissionColor;
                return o;
            }}

            fixed4 frag(v2f i) : SV_Target {{
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                fixed4 tex = tex2D(_MainTex, i.uv);
                return tex * i.color;
            }}
            ENDCG
        }}
    }}
    Fallback "Legacy Shaders/Transparent/Diffuse"
}}
"""

    if shader_type == "unlit":
        return f"""Shader "{shader_name}" {{
    Properties {{
        _MainTex ("MainTex", 2D) = "white" {{}}
        _Color ("Color", Color) = (1,1,1,1)
        _Cutoff ("Alpha cutoff", Range(0,1)) = 0
    }}
    SubShader {{
        Tags {{ "RenderType"="Opaque" }}
        LOD 100
        Cull Off
        ZWrite On

        Pass {{
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            float _Cutoff;

            struct appdata {{
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            }};

            struct v2f {{
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_OUTPUT_STEREO
            }};

            v2f vert(appdata v) {{
                v2f o;
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                fixed4 vcol = fixed4(1, 1, 1, 1); // FORCE white - Vulkan sends (0,0,0,0) for missing vertex colors
                o.color = vcol * _Color;
                return o;
            }}

            fixed4 frag(v2f i) : SV_Target {{
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                fixed4 tex = tex2D(_MainTex, i.uv);
                // Cutout materials (e.g. MenuPaint2: alpha-masked wall over a see-through area) must clip,
                // otherwise the transparent area draws as an opaque black quad over the whole scene.
                if (_Cutoff > 0.01) {{
                    clip(tex.a * i.color.a - _Cutoff);
                }}
                return tex * i.color;
            }}
            ENDCG
        }}
    }}
    Fallback "Unlit/Texture"
}}
"""

    if shader_type == "additive":
        fog_decl = "" if ignore_fog else "#pragma multi_compile_fog"
        fog_coord = "" if ignore_fog else "UNITY_FOG_COORDS(1)"
        fog_vert = "" if ignore_fog else "UNITY_TRANSFER_FOG(o, o.pos);"
        fog_frag = "" if ignore_fog else "UNITY_APPLY_FOG_COLOR(i.fogCoord, col, fixed4(0,0,0,0));"

        return f"""Shader "{shader_name}" {{
    Properties {{
        _MainTex ("MainTex", 2D) = "white" {{}}
        _TintColor ("Color", Color) = (1,1,1,1)
        _Color ("Color", Color) = (1,1,1,1)
    }}
    SubShader {{
        Tags {{ "Queue"="Transparent" "IgnoreProjector"="True" "RenderType"="Transparent" }}
        LOD 150
        Blend SrcAlpha One
        ColorMask RGB
        Cull Off
        Lighting Off
        ZWrite Off

        Pass {{
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            {fog_decl}
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _TintColor;
            fixed4 _Color;

            struct appdata {{
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            }};

            struct v2f {{
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                {fog_coord}
                UNITY_VERTEX_OUTPUT_STEREO
            }};

            v2f vert(appdata v) {{
                v2f o;
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                // Particles carry their fade/colour-over-lifetime in vertex colour: keep it.
                o.color = v.color * _TintColor * _Color;
                {fog_vert}
                return o;
            }}

            fixed4 frag(v2f i) : SV_Target {{
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                fixed4 col = 2.0f * i.color * tex2D(_MainTex, i.uv);
                {fog_frag}
                return col;
            }}
            ENDCG
        }}
    }}
    Fallback "Mobile/Particles/Additive"
}}
"""

    if shader_type in ("transparent", "water"):
        fog_decl = "" if ignore_fog else "#pragma multi_compile_fog"
        fog_coord = "" if ignore_fog else "UNITY_FOG_COORDS(1)"
        fog_vert = "" if ignore_fog else "UNITY_TRANSFER_FOG(o, o.pos);"
        fog_frag = "" if ignore_fog else "UNITY_APPLY_FOG(i.fogCoord, col);"

        return f"""Shader "{shader_name}" {{
    Properties {{
        _MainTex ("MainTex", 2D) = "white" {{}}
        _Color ("Main Color", Color) = (1,1,1,1)
        _TintColor ("Tint Color", Color) = (1,1,1,1)
    }}
    SubShader {{
        Tags {{ "Queue"="Transparent" "IgnoreProjector"="True" "RenderType"="Transparent" }}
        LOD 150
        Blend SrcAlpha OneMinusSrcAlpha
        Cull Back
        ZWrite Off

        Pass {{
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            {fog_decl}
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            fixed4 _TintColor;

            struct appdata {{
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            }};

            struct v2f {{
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                {fog_coord}
                UNITY_VERTEX_OUTPUT_STEREO
            }};

            v2f vert(appdata v) {{
                v2f o;
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                // Particles carry their fade/colour-over-lifetime in vertex colour: keep it.
                o.color = v.color * _Color * _TintColor;
                {fog_vert}
                return o;
            }}

            fixed4 frag(v2f i) : SV_Target {{
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                fixed4 col = tex2D(_MainTex, i.uv) * i.color;
                {fog_frag}
                return col;
            }}
            ENDCG
        }}
    }}
    Fallback "Legacy Shaders/Transparent/Diffuse"
}}
"""

    # Opaque 3D Lit with ForwardBase and ForwardAdd
    cull_mode = "Off" if any(k in sname_lower for k in DBL_KEYWORDS) else "Back"
    fog_decl = "" if ignore_fog else "#pragma multi_compile_fog"
    fog_coord_base = "" if ignore_fog else "UNITY_FOG_COORDS(2)"
    fog_coord_add = "" if ignore_fog else "UNITY_FOG_COORDS(4)"
    fog_vert = "" if ignore_fog else "UNITY_TRANSFER_FOG(o, o.pos);"
    fog_frag_base = "" if ignore_fog else "UNITY_APPLY_FOG(i.fogCoord, col);"
    fog_frag_add = "" if ignore_fog else "UNITY_APPLY_FOG_COLOR(i.fogCoord, col, fixed4(0,0,0,0));"

    return f"""Shader "{shader_name}" {{
    Properties {{
        _MainTex ("MainTex", 2D) = "white" {{}}
        _Color ("Color", Color) = (1,1,1,1)
        _Cutoff ("Alpha cutoff", Range(0,1)) = 0
    }}
    SubShader {{
        Tags {{ "RenderType"="Opaque" }}
        LOD 200
        Cull {cull_mode}

        Pass {{
            Name "FORWARD"
            Tags {{ "LightMode"="ForwardBase" }}
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fwdbase
            {fog_decl}
            #include "UnityCG.cginc"
            #include "Lighting.cginc"
            #include "AutoLight.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            float _Cutoff;

            struct appdata {{
                float4 vertex : POSITION;
                float3 normal : NORMAL;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            }};

            struct v2f {{
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                float3 worldNormal : TEXCOORD1;
                {fog_coord_base}
                UNITY_VERTEX_OUTPUT_STEREO
            }};

            v2f vert(appdata v) {{
                v2f o;
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                o.worldNormal = UnityObjectToWorldNormal(v.normal);
                fixed4 vcol = fixed4(1, 1, 1, 1); // FORCE white - Vulkan sends (0,0,0,0) for missing vertex colors
                o.color = vcol * _Color;
                {fog_vert}
                return o;
            }}

            fixed4 frag(v2f i) : SV_Target {{
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                fixed4 tex = tex2D(_MainTex, i.uv);
                // Cutout materials (leaves, moths, crows, cloth): honour _Cutoff like the original shaders.
                if (_Cutoff > 0.01) {{
                    clip(tex.a * i.color.a - _Cutoff);
                }}
                fixed3 ambient = ShadeSH9(float4(i.worldNormal, 1.0));
                fixed3 lightDir = _WorldSpaceLightPos0.xyz;
                fixed ndotl = max(0.0, dot(i.worldNormal, lightDir));
                fixed3 diff = _LightColor0.rgb * ndotl + ambient;
                fixed4 col = fixed4(tex.rgb * i.color.rgb * diff, tex.a * i.color.a);
                {fog_frag_base}
                return col;
            }}
            ENDCG
        }}

        Pass {{
            Name "FORWARD_ADD"
            Tags {{ "LightMode"="ForwardAdd" }}
            Blend One One
            ZWrite Off
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fwdadd
            {fog_decl}
            #include "UnityCG.cginc"
            #include "Lighting.cginc"
            #include "AutoLight.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            float _Cutoff;

            struct appdata {{
                float4 vertex : POSITION;
                float3 normal : NORMAL;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            }};

            struct v2f {{
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                float3 worldNormal : TEXCOORD1;
                float3 worldPos : TEXCOORD2;
                UNITY_SHADOW_COORDS(3)
                {fog_coord_add}
                UNITY_VERTEX_OUTPUT_STEREO
            }};

            v2f vert(appdata v) {{
                v2f o;
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                o.worldNormal = UnityObjectToWorldNormal(v.normal);
                o.worldPos = mul(unity_ObjectToWorld, v.vertex).xyz;
                fixed4 vcol = fixed4(1, 1, 1, 1); // FORCE white - Vulkan sends (0,0,0,0) for missing vertex colors
                o.color = vcol * _Color;
                UNITY_TRANSFER_SHADOW(o, v.uv);
                {fog_vert}
                return o;
            }}

            fixed4 frag(v2f i) : SV_Target {{
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                fixed4 tex = tex2D(_MainTex, i.uv);
                // Cutout materials (leaves, moths, crows, cloth): honour _Cutoff like the original shaders.
                if (_Cutoff > 0.01) {{
                    clip(tex.a * i.color.a - _Cutoff);
                }}
                float3 lightDir = normalize(UnityWorldSpaceLightDir(i.worldPos));
                fixed ndotl = max(0.0, dot(i.worldNormal, lightDir));
                UNITY_LIGHT_ATTENUATION(atten, i, i.worldPos);
                fixed3 lightColor = _LightColor0.rgb * (ndotl * atten);
                fixed4 col = fixed4(tex.rgb * i.color.rgb * lightColor, 0.0);
                {fog_frag_add}
                return col;
            }}
            ENDCG
        }}
    }}
    Fallback "Mobile/VertexLit"
}}
"""

def _needs_regeneration(txt):
    """AssetRipper stubs, plus unlit/lit stubs generated before alpha-cutout support (no clip)."""
    if ("//DummyShaderTextExporter" in txt or
            "LIGHTING_COORDS(2,3)" in txt or
            "UNITY_FOG_COORDS(3)" in txt or
            'UNITY_FOG_COORDS(1)\n            #include "UnityCG.cginc"' in txt):
        return True
    # Additive stubs from before tint-alpha support (Blend One One ignored _TintColor.a -> overblown glows).
    if 'Particles/Additive"' in txt and "Blend One One" in txt and "LightMode" not in txt:
        return True
    if "clip(" in txt or '_Cutoff ("Alpha cutoff"' not in txt:
        return False
    unlit = 'Fallback "Unlit/Texture"' in txt and "LOD 100" in txt
    lit = 'Fallback "Mobile/VertexLit"' in txt and 'Name "FORWARD_ADD"' in txt
    return unlit or lit

def detect(export_dir, profile=None):
    findings = []
    shader_dir = os.path.join(export_dir, "Assets", "Shader")
    if not os.path.exists(shader_dir):
        return findings

    sources = override_sources(profile)
    overrides_set = set(sources)

    # 1. Detect missing or out-of-sync overrides (repo shaders/ or the generated folder)
    for f, src in sorted(sources.items()):
        dst = os.path.join(shader_dir, f)
        if not os.path.exists(dst):
            findings.append(f"Missing shader override: Assets/Shader/{f}")
        else:
            with open(src, "r", encoding="utf-8") as f1, open(dst, "r", encoding="utf-8") as f2:
                if f1.read() != f2.read():
                    findings.append(f"Out-of-sync shader override: Assets/Shader/{f}")

    # 2. Detect unpatched dummy stubs (excluding protected repo overrides)
    for root, _, files in os.walk(shader_dir):
        for f in files:
            if f.endswith(".shader") and f not in overrides_set:
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()
                if _needs_regeneration(txt):
                    findings.append(f"Broken or stub shader in {os.path.relpath(p, export_dir)}")

    return findings

def apply(export_dir, profile=None, dry_run=False):
    shader_dir = os.path.join(export_dir, "Assets", "Shader")
    changes = 0
    details = []

    if not os.path.exists(shader_dir):
        return {"changes_applied": 0, "details": details}

    sources = override_sources(profile)
    overrides_set = set(sources)
    origin = "generated" if shader_source(profile) else "repo"

    # 1. Synchronize protected shader overrides (repo shaders/ or the generated folder)
    for f, src in sorted(sources.items()):
        dst = os.path.join(shader_dir, f)
        needs_copy = False
        if not os.path.exists(dst):
            needs_copy = True
        else:
            with open(src, "r", encoding="utf-8") as f1, open(dst, "r", encoding="utf-8") as f2:
                if f1.read() != f2.read():
                    needs_copy = True
        if needs_copy:
            kind = "generated" if os.path.dirname(src) != os.path.join(REPO_ROOT, "shaders") else "repo"
            details.append(f"Synchronize protected shader override {f} ({kind}) to Assets/Shader/")
            changes += 1
            if not dry_run:
                os.makedirs(shader_dir, exist_ok=True)
                shutil.copy2(src, dst)
    if origin == "generated":
        details.append(f"Shader source: {shader_source(profile)[0] or 'shaders/ (repo)'}")

    # 2. Patch remaining DummyShaderTextExporter stubs (strictly excluding protected overrides)
    for root, _, files in os.walk(shader_dir):
        for f in files:
            if f.endswith(".shader") and f not in overrides_set:
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()

                if _needs_regeneration(txt):
                    m = re.search(r'Shader\s+"([^"]+)"', txt)
                    shader_name = m.group(1) if m else os.path.splitext(f)[0]
                    sname_lower = shader_name.lower()

                    if any(k in sname_lower for k in MOON_KEYWORDS):
                        stype = "moon"
                    elif any(k in sname_lower for k in UNLIT_KEYWORDS):
                        stype = "unlit"
                    elif any(k in sname_lower for k in ADDITIVE_KEYWORDS):
                        stype = "additive"
                    elif any(k in sname_lower for k in WATER_KEYWORDS):
                        stype = "transparent"
                    elif any(k in sname_lower for k in TRANSPARENT_KEYWORDS):
                        stype = "transparent"
                    else:
                        stype = "opaque"

                    new_body = _build_shader_body(shader_name, stype)
                    changes += 1
                    details.append(f"Replaced broken/stub shader {f} with {stype} SubShader ({shader_name})")
                    if not dry_run:
                        with open(p, "w", encoding="utf-8") as fh:
                            fh.write(new_body)

    return {"changes_applied": changes, "details": details}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
