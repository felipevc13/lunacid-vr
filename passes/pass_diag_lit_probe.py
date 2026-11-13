#!/usr/bin/env python3
"""
Disposable Diagnostic Pass: Lit Shader Probe (measure, don't guess)
-------------------------------------------------------------------
The lit shaders (Shader Forge/Object, Object_DBL, Legacy/Mobile VertexLit) draw
black on Quest while an unlit textured shader draws the same geometry fine, and the
Object source is unchanged since Build 1 (which rendered the menu street). So the
failure is in an INPUT of the lit path, not in its code. This pass replaces every lit
renderer's material with a clone running Diag/LitViz, which outputs one raw input as
a colour, and cycles through them on a timer. Each stage prints `STAGE_DONE <name>`
so tools/diag_audit_capture.sh photographs it.

Stages (shader mode in brackets) and how to read the photo:
  baseline          untouched scene (expected black)
  viz_normal    [1] world normal as RGB.   mid-grey = normals are ZERO (missing mesh normals);
                                           black = NaN/negative; colourful = normals fine
  viz_lightcolor[3] _LightColor0.         black = no main light colour reaches ForwardBase
  viz_sh        [5] ShadeSH9(normal).     black = ambient SH is zero
  viz_fog       [6] white with fog applied. dark navy = fog saturates everywhere; white = fog fine
  viz_vcolor    [7] vertex colour.        black = no vertex colours; white = fine
  viz_uv        [8] frac(uv) as RG.       flat colour/streaks = collapsed or broken UVs
  viz_ndl       [9] N.L (normalised).     black = N or L is zero
  viz_formula  [10] exact Object formula, no fog, same material props
  viz_formula_fog [11] exact Object formula + fog
  viz_formula_up  [12] formula with normal forced to (0,1,0)

Decision: if viz_formula looks lit but the real Object is black, the bug is in the
variant/keywords/material state, not the maths. If viz_formula is black, the first
black viz_* stage names the broken input. viz_formula_up lit while viz_formula black
=> normals are the culprit.

Creates (all disposable, fixed GUIDs, removed by `clean`):
  Assets/Shader/Diag_LitViz.shader, Assets/Resources/DiagLitViz.mat,
  Assets/Scripts/Assembly-CSharp/RuntimeLitProbe.cs

Conflicts with pass_diag_renderer_audit (both swap materials): clean one before applying the other.

Usage:
  python3 passes/pass_diag_lit_probe.py apply [export_dir]
  python3 passes/pass_diag_lit_probe.py clean [export_dir]
"""

import os
import sys

SHADER_REL_PATH = "Assets/Shader/Diag_LitViz.shader"
SHADER_META_REL_PATH = SHADER_REL_PATH + ".meta"
MAT_REL_PATH = "Assets/Resources/DiagLitViz.mat"
MAT_META_REL_PATH = MAT_REL_PATH + ".meta"
PROBE_REL_PATH = "Assets/Scripts/Assembly-CSharp/RuntimeLitProbe.cs"
PROBE_META_REL_PATH = PROBE_REL_PATH + ".meta"

SHADER_GUID = "d1a90000000000000000000000000007"
MAT_GUID = "d1a90000000000000000000000000008"
PROBE_GUID = "d1a90000000000000000000000000009"

SHADER_CONTENT = r"""Shader "Diag/LitViz" {
    Properties {
        _MainTex ("MainTex", 2D) = "white" {}
        _Color ("Main Color", Color) = (1,1,1,1)
        _UNLIT_F ("UNLIT_F", Float) = 0
        _Clip ("Clip", Float) = 1
        _Cutoff ("Alpha cutoff", Range(0, 1)) = 0.5
        _Emission ("Emission", 2D) = "black" {}
        _EmissionColor ("Emission Color", Color) = (0,0,0,1)
        _Mode ("Mode", Float) = 0
    }
    SubShader {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 200
        Cull Off

        Pass {
            Name "ForwardBase"
            Tags { "LightMode"="ForwardBase" }

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_fwdbase_fullshadows
            #pragma multi_compile _ LIGHTMAP_ON

            #include "UnityCG.cginc"
            #include "Lighting.cginc"
            #include "AutoLight.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            sampler2D _Emission;
            float4 _Emission_ST;
            fixed4 _Color;
            fixed4 _EmissionColor;
            float _Clip;
            float _Cutoff;
            float _UNLIT_F;
            float _Mode;

            struct appdata {
                float4 vertex : POSITION;
                float3 normal : NORMAL;
                float2 uv : TEXCOORD0;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                fixed4 vcolor : COLOR;
                float3 normal : TEXCOORD1;
                UNITY_FOG_COORDS(2)
                UNITY_VERTEX_OUTPUT_STEREO
            };

            v2f vert(appdata v) {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                o.vcolor = v.color;
                o.normal = UnityObjectToWorldNormal(v.normal);
                UNITY_TRANSFER_FOG(o, o.pos);
                return o;
            }

            // Same maths as shaders/Shader Forge_Object.shader (vcolor forced to 1).
            fixed4 ObjectFormula(v2f i, float3 n, bool withFog) {
                fixed4 tex = tex2D(_MainTex, i.uv);
                if (_Clip > 0.5) {
                    clip(tex.a * _Color.a - _Cutoff);
                }
                fixed4 col = tex * _Color;
                if (_UNLIT_F < 0.5) {
                    float3 lightDir = normalize(_WorldSpaceLightPos0.xyz);
                    float NdotL = max(0.0, dot(normalize(n), lightDir));
                    fixed3 ambient = ShadeSH9(float4(n, 1.0));
                    fixed3 light = _LightColor0.rgb * NdotL + ambient;
                    col.rgb *= light;
                }
                fixed4 em = tex2D(_Emission, i.uv) * _EmissionColor;
                col.rgb += em.rgb;
                if (withFog) {
                    UNITY_APPLY_FOG(i.fogCoord, col);
                }
                return col;
            }

            fixed4 frag(v2f i) : SV_Target {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                int m = (int)(_Mode + 0.5);
                float3 n = i.normal;
                fixed4 col = fixed4(0, 0, 0, 1);

                if (m == 0) {
                    col = tex2D(_MainTex, i.uv) * _Color;
                } else if (m == 1) {
                    col.rgb = n * 0.5 + 0.5;
                } else if (m == 3) {
                    col.rgb = _LightColor0.rgb;
                } else if (m == 5) {
                    col.rgb = ShadeSH9(float4(n, 1.0));
                } else if (m == 6) {
                    col = fixed4(1, 1, 1, 1);
                    UNITY_APPLY_FOG(i.fogCoord, col);
                } else if (m == 7) {
                    col = fixed4(i.vcolor.rgb, 1);
                } else if (m == 8) {
                    col.rgb = fixed3(frac(i.uv), 0);
                } else if (m == 9) {
                    col.rgb = max(0.0, dot(normalize(n), normalize(_WorldSpaceLightPos0.xyz)));
                } else if (m == 10) {
                    col = ObjectFormula(i, n, false);
                } else if (m == 11) {
                    col = ObjectFormula(i, n, true);
                } else if (m == 12) {
                    col = ObjectFormula(i, float3(0, 1, 0), false);
                }
                col.a = 1;
                return col;
            }
            ENDCG
        }
    }
}
"""

SHADER_META_CONTENT = """fileFormatVersion: 2
guid: %s
ShaderImporter:
  externalObjects: {}
  defaultTextures: []
  nonModifiableTextures: []
  userData:
  assetBundleName:
  assetBundleVariant:
""" % SHADER_GUID

MAT_CONTENT = """%%YAML 1.1
%%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  serializedVersion: 6
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_Name: DiagLitViz
  m_Shader: {fileID: 4800000, guid: %s, type: 3}
  m_ShaderKeywords:
  m_LightmapFlags: 4
  m_EnableInstancingVariants: 0
  m_DoubleSidedGI: 0
  m_CustomRenderQueue: -1
  stringTagMap: {}
  disabledShaderPasses: []
  m_SavedProperties:
    serializedVersion: 3
    m_TexEnvs:
    - _MainTex:
        m_Texture: {fileID: 0}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}
    m_Floats:
    - _Mode: 0
    m_Colors:
    - _Color: {r: 1, g: 1, b: 1, a: 1}
  m_BuildTextureStacks: []
""" % SHADER_GUID

MAT_META_CONTENT = """fileFormatVersion: 2
guid: %s
NativeFormatImporter:
  externalObjects: {}
  mainObjectFileID: 2100000
  userData:
  assetBundleName:
  assetBundleVariant:
""" % MAT_GUID

PROBE_CONTENT = r"""using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Scripting;

// Disposable diagnostic (pass_diag_lit_probe.py). Safe to delete: `clean`.
[Preserve]
public class RuntimeLitProbe : MonoBehaviour
{
    const string TAG = "LUNA_AUDIT";
    static string s_FilePath;
#if UNITY_ANDROID && !UNITY_EDITOR
    static AndroidJavaClass s_AndroidLog;
#endif

    struct Stage
    {
        public string name;
        public int mode;
        public Stage(string n, int m) { name = n; mode = m; }
    }

    static readonly Stage[] Stages = new Stage[]
    {
        new Stage("viz_normal", 1),
        new Stage("viz_lightcolor", 3),
        new Stage("viz_sh", 5),
        new Stage("viz_fog", 6),
        new Stage("viz_vcolor", 7),
        new Stage("viz_uv", 8),
        new Stage("viz_ndl", 9),
        new Stage("viz_formula", 10),
        new Stage("viz_formula_fog", 11),
        new Stage("viz_formula_up", 12),
    };

    readonly Dictionary<Material, Material> m_Clones = new Dictionary<Material, Material>();

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void InitOnSceneLoad()
    {
        if (SceneManager.GetActiveScene().name != "MainMenu") return;
        if (GameObject.Find("[DIAG_LIT_PROBE]") != null) return;
        var go = new GameObject("[DIAG_LIT_PROBE]");
        go.AddComponent<RuntimeLitProbe>();
        DontDestroyOnLoad(go);
    }

    // JNI logcat (reliable) + file + Debug.Log (best effort).
    static void Log(string msg)
    {
        try
        {
            if (s_FilePath == null) s_FilePath = Path.Combine(Application.persistentDataPath, "luna_audit.log");
            File.AppendAllText(s_FilePath, msg + "\n");
        }
        catch { }
#if UNITY_ANDROID && !UNITY_EDITOR
        try
        {
            if (s_AndroidLog == null) s_AndroidLog = new AndroidJavaClass("android.util.Log");
            s_AndroidLog.CallStatic<int>("i", TAG, msg);
        }
        catch { }
#endif
        try { Debug.Log(TAG + " " + msg); } catch { }
    }

    static bool IsLitShader(string sn)
    {
        return sn == "Shader Forge/Object" || sn == "Shader Forge/Object_DBL"
            || sn == "Legacy Shaders/VertexLit" || sn == "Mobile/VertexLit";
    }

    IEnumerator Start()
    {
        try { File.WriteAllText(Path.Combine(Application.persistentDataPath, "luna_audit.log"), ""); } catch { }
        var template = Resources.Load<Material>("DiagLitViz");
        Log("BEGIN lit probe scene=" + SceneManager.GetActiveScene().name + " template=" + (template != null)
            + (template != null ? " shader=" + template.shader.name + " supported=" + template.shader.isSupported : ""));

        yield return new WaitForSecondsRealtime(3f);
        Log("STAGE_DONE baseline");
        if (template == null) yield break;

        int slots = Remap(template.shader);
        Log("remapped lit material slots=" + slots + " distinct source materials=" + m_Clones.Count);

        foreach (var s in Stages)
        {
            SetMode(s.mode);
            Log("mode=" + s.mode + " " + s.name);
            yield return new WaitForSecondsRealtime(1f);
            Log("STAGE_DONE " + s.name);
            yield return new WaitForSecondsRealtime(6f);
        }
        Log("STAGE_DONE final");
    }

    int Remap(Shader viz)
    {
        int slots = 0;
        foreach (var r in Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (!(r is MeshRenderer) && !(r is SkinnedMeshRenderer)) continue;
            var mats = r.sharedMaterials;
            bool changed = false;
            for (int i = 0; i < mats.Length; i++)
            {
                var m = mats[i];
                if (m == null || m.shader == null) continue;
                if (!IsLitShader(m.shader.name)) continue;
                if (m.renderQueue >= 3000) continue;
                Material clone;
                if (!m_Clones.TryGetValue(m, out clone))
                {
                    clone = new Material(m);
                    clone.shader = viz;          // keeps same-named properties (_MainTex, _Color, _UNLIT_F, _Clip, ...)
                    clone.renderQueue = m.renderQueue;
                    clone.name = "VIZ_" + m.name;
                    m_Clones[m] = clone;
                }
                mats[i] = clone;
                changed = true;
                slots++;
            }
            if (changed) r.sharedMaterials = mats;
        }
        return slots;
    }

    void SetMode(int mode)
    {
        foreach (var kv in m_Clones) kv.Value.SetFloat("_Mode", mode);
    }
}
"""

PROBE_META_CONTENT = """fileFormatVersion: 2
guid: %s
MonoImporter:
  externalObjects: {}
  serializedVersion: 2
  defaultReferences: []
  executionOrder: 0
  icon: {fileID: 0}
  userData:
  assetBundleName:
  assetBundleVariant:
""" % PROBE_GUID

FILES = [
    (SHADER_REL_PATH, SHADER_CONTENT),
    (SHADER_META_REL_PATH, SHADER_META_CONTENT),
    (MAT_REL_PATH, MAT_CONTENT),
    (MAT_META_REL_PATH, MAT_META_CONTENT),
    (PROBE_REL_PATH, PROBE_CONTENT),
    (PROBE_META_REL_PATH, PROBE_META_CONTENT),
]


def detect(export_dir, profile=None):
    findings = []
    if not os.path.exists(os.path.join(export_dir, PROBE_REL_PATH)):
        findings.append(f"Lit probe not installed in {PROBE_REL_PATH}")
    return findings


def apply(export_dir, profile=None, dry_run=False):
    changes = 0
    details = []
    for rel_path, content in FILES:
        full_path = os.path.join(export_dir, rel_path)
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                if f.read() == content:
                    continue
            action = "Updated"
        else:
            action = "Created"
        changes += 1
        details.append(f"{action} {rel_path}")
        if not dry_run:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
    return {"changes_applied": changes, "details": details}


def clean(export_dir, profile=None, dry_run=False):
    changes = 0
    details = []
    for rel_path, _ in FILES:
        full_path = os.path.join(export_dir, rel_path)
        if os.path.exists(full_path):
            changes += 1
            details.append(f"Removed {rel_path}")
            if not dry_run:
                os.remove(full_path)
    return {"changes_applied": changes, "details": details}


def verify(export_dir, profile=None):
    missing = [p for p, _ in FILES if not os.path.exists(os.path.join(export_dir, p))]
    return {"passed": not missing, "remaining_issues": len(missing)}



def _config_project():
    """The project from the machine configuration (core/config.py), for running this pass by hand."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core import config
    return config.load()["project"]

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    export = sys.argv[2] if len(sys.argv) > 2 else _config_project()
    if action == "clean":
        print(clean(export))
    else:
        print(apply(export))
