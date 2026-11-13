#!/usr/bin/env python3
"""
Disposable Diagnostic Pass: Shader Variant Bisect (video-friendly)
------------------------------------------------------------------
Build 11 showed that a lit shader with `LightMode=ForwardBase` + multi_compile_fog +
multi_compile_fwdbase_fullshadows + multi_compile LIGHTMAP_ON draws NOTHING on Quest
(even when it only outputs a constant), while an unlit shader with no tag and no
multi_compile draws fine. This pass splits those two factors across 8 otherwise
identical shaders and cycles through them at runtime on all lit renderers.

Every shader outputs `tex.rgb * 0.8 + 0.2` (never pure black), so ANY drawn pixel is visible.
The current stage is printed on screen (OnGUI) so a screen recording is self-describing:

  0 REAL scene              untouched materials (expected black)
  1 plain                   no tag, no pragmas                      (control, expected OK)
  2 tag                     LightMode=ForwardBase only
  3 fog                     multi_compile_fog only
  4 fwdbase                 multi_compile_fwdbase_fullshadows only
  5 lightmap                multi_compile _ LIGHTMAP_ON only
  6 tag+fog
  7 tag+fwdbase
  8 tag+all                 tag + all three pragmas (= real Object structure)

Reading: the first stage that goes black while the previous simpler ones draw names the
culprit (e.g. 1,3,4,5 OK and 2 black => the ForwardBase tag: no forward pass is selected;
1,2 OK and 4 black => the fwdbase keyword set has no matching variant at runtime).
The sequence runs twice (about 2 x 60 s) so there is slack to start recording.
Logs also go to logcat (tag LUNA_AUDIT) and persistentDataPath/luna_audit.log.

Creates (disposable, fixed GUIDs, removed by `clean`):
  Assets/Shader/Diag_V1..V8.shader(+meta), Assets/Resources/DiagV1..V8.mat(+meta),
  Assets/Scripts/Assembly-CSharp/RuntimeVariantBisect.cs(+meta)

Build 13 update: Build 12 left even the plain control black (lit slots only, materials CLONED from the
original with the shader swapped) while Build 9 drew (ALL opaque slots, NEW material from a template).
Stages A1..A4 cross scope (lit/all) x method (template/clone); B2..B8 run the variants with all+template.

Conflicts with pass_diag_lit_probe / pass_diag_renderer_audit (they also swap materials).

Usage:
  python3 passes/pass_diag_variant_bisect.py apply [export_dir]
  python3 passes/pass_diag_variant_bisect.py clean [export_dir]
"""

import os
import sys

# (index, slug, human label, has_tag, fog, fwdbase, lightmap)
VARIANTS = [
    (1, "plain",         "1 plain (no tag, no pragmas) - control", False, False, False, False),
    (2, "tag",           "2 LightMode=ForwardBase tag only",       True,  False, False, False),
    (3, "fog",           "3 multi_compile_fog only",               False, True,  False, False),
    (4, "fwdbase",       "4 multi_compile_fwdbase_fullshadows only", False, False, True,  False),
    (5, "lightmap",      "5 multi_compile LIGHTMAP_ON only",      False, False, False, True),
    (6, "tag_fog",       "6 tag + fog",                            True,  True,  False, False),
    (7, "tag_fwdbase",   "7 tag + fwdbase",                        True,  False, True,  False),
    (8, "tag_all",       "8 tag + fog + fwdbase + lightmap (= real Object)", True, True, True, True),
]

PROBE_REL_PATH = "Assets/Scripts/Assembly-CSharp/RuntimeVariantBisect.cs"
PROBE_META_REL_PATH = PROBE_REL_PATH + ".meta"
PROBE_GUID = "d1a9%028x" % 0x60


def shader_rel(i):
    return "Assets/Shader/Diag_V%d.shader" % i


def mat_rel(i):
    return "Assets/Resources/DiagV%d.mat" % i


def shader_guid(i):
    return "d1a9%028x" % (0x20 + i)


def mat_guid(i):
    return "d1a9%028x" % (0x40 + i)


def build_shader(v):
    i, slug, _label, tag, fog, fwdbase, lightmap = v
    pragmas = []
    includes = ['#include "UnityCG.cginc"']
    if fog:
        pragmas.append("#pragma multi_compile_fog")
    if fwdbase:
        pragmas.append("#pragma multi_compile_fwdbase_fullshadows")
        includes += ['#include "Lighting.cginc"', '#include "AutoLight.cginc"']
    if lightmap:
        pragmas.append("#pragma multi_compile _ LIGHTMAP_ON")
    tag_line = 'Tags { "LightMode"="ForwardBase" }' if tag else ""
    return r"""Shader "Diag/V%d_%s" {
    Properties {
        _MainTex ("MainTex", 2D) = "white" {}
        _Color ("Main Color", Color) = (1,1,1,1)
    }
    SubShader {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 200
        Cull Off
        Pass {
            %s
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            %s
            %s

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;

            struct appdata {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            v2f vert(appdata v) {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target {
                fixed3 c = tex2D(_MainTex, i.uv).rgb * 0.8 + 0.2;
                return fixed4(c, 1);
            }
            ENDCG
        }
    }
}
""" % (i, slug, tag_line, "\n            ".join(pragmas), "\n            ".join(includes))


def shader_meta(i):
    return """fileFormatVersion: 2
guid: %s
ShaderImporter:
  externalObjects: {}
  defaultTextures: []
  nonModifiableTextures: []
  userData:
  assetBundleName:
  assetBundleVariant:
""" % shader_guid(i)


def build_mat(i):
    return """%%YAML 1.1
%%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  serializedVersion: 6
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_Name: DiagV%d
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
    m_Floats: []
    m_Colors:
    - _Color: {r: 1, g: 1, b: 1, a: 1}
  m_BuildTextureStacks: []
""" % (i, shader_guid(i))


def mat_meta(i):
    return """fileFormatVersion: 2
guid: %s
NativeFormatImporter:
  externalObjects: {}
  mainObjectFileID: 2100000
  userData:
  assetBundleName:
  assetBundleVariant:
""" % mat_guid(i)


PROBE_CONTENT = r"""using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Scripting;

// Disposable diagnostic (pass_diag_variant_bisect.py). Safe to delete: `clean`.
[Preserve]
public class RuntimeVariantBisect : MonoBehaviour
{
    const string TAG = "LUNA_AUDIT";
    const int LOOPS = 2;
    const float STAGE_SECONDS = 6f;
    const float LEAD_IN_SECONDS = 8f;

    static string s_FilePath;
#if UNITY_ANDROID && !UNITY_EDITOR
    static AndroidJavaClass s_AndroidLog;
#endif

    // Build 12 showed even stage "plain" black when lit materials were CLONED from the original and
    // only their shader swapped, while Build 9 (new Material from a template, ALL opaque slots) drew.
    // Stages A1..A4 separate (scope lit-only vs all) x (method template vs clone); B2..B8 then run
    // the variants with the method/scope that is known to draw (all + template).
    class Stage
    {
        public string label; public int shader; public bool all; public bool template;
        public Stage(string l, int s, bool a, bool t) { label = l; shader = s; all = a; template = t; }
    }

    static readonly Stage[] Stages = new Stage[]
    {
        new Stage("0 REAL scene (untouched)", 0, false, false),
        new Stage("A1 plain | lit only | NEW material from template", 1, false, true),
        new Stage("A2 plain | ALL opaque | NEW material from template (= Build 9)", 1, true, true),
        new Stage("A3 plain | lit only | CLONE of original (= Build 12)", 1, false, false),
        new Stage("A4 plain | ALL opaque | CLONE of original", 1, true, false),
        new Stage("B2 LightMode=ForwardBase tag only | ALL | template", 2, true, true),
        new Stage("B3 multi_compile_fog only | ALL | template", 3, true, true),
        new Stage("B4 multi_compile_fwdbase_fullshadows only | ALL | template", 4, true, true),
        new Stage("B5 multi_compile LIGHTMAP_ON only | ALL | template", 5, true, true),
        new Stage("B6 tag + fog | ALL | template", 6, true, true),
        new Stage("B7 tag + fwdbase | ALL | template", 7, true, true),
        new Stage("B8 tag + fog + fwdbase + lightmap | ALL | template", 8, true, true),
    };

    class Slot
    {
        public Renderer renderer;
        public Material[] original;
    }

    readonly List<Slot> m_Slots = new List<Slot>();
    readonly List<Material> m_Made = new List<Material>();
    readonly Material[] m_Templates = new Material[9];
    string m_Label = "";
    GUIStyle m_Style;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void InitOnSceneLoad()
    {
        if (SceneManager.GetActiveScene().name != "MainMenu") return;
        if (GameObject.Find("[DIAG_VARIANT_BISECT]") != null) return;
        var go = new GameObject("[DIAG_VARIANT_BISECT]");
        go.AddComponent<RuntimeVariantBisect>();
        DontDestroyOnLoad(go);
    }

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

    void OnGUI()
    {
        if (string.IsNullOrEmpty(m_Label)) return;
        if (m_Style == null)
        {
            m_Style = new GUIStyle(GUI.skin.label);
            m_Style.fontSize = Mathf.Max(22, Screen.height / 20);
            m_Style.fontStyle = FontStyle.Bold;
            m_Style.wordWrap = true;
        }
        var r = new Rect(24, 18, Screen.width - 48, Screen.height / 4f);
        m_Style.normal.textColor = Color.black;
        GUI.Label(new Rect(r.x + 2, r.y + 2, r.width, r.height), m_Label, m_Style);
        m_Style.normal.textColor = Color.yellow;
        GUI.Label(r, m_Label, m_Style);
    }

    IEnumerator Start()
    {
        try { File.WriteAllText(Path.Combine(Application.persistentDataPath, "luna_audit.log"), ""); } catch { }
        bool ok = true;
        for (int i = 1; i <= 8; i++)
        {
            var mat = Resources.Load<Material>("DiagV" + i);
            m_Templates[i] = mat;
            Log("shader V" + i + " loaded=" + (mat != null) + (mat != null ? " name=" + mat.shader.name + " supported=" + mat.shader.isSupported : ""));
            if (mat == null) ok = false;
        }
        m_Label = "VARIANT BISECT - starting in " + LEAD_IN_SECONDS + "s (start recording now)";
        yield return new WaitForSecondsRealtime(LEAD_IN_SECONDS);

        if (!ok) { m_Label = "ERROR: variant shaders missing"; yield break; }
        BuildSlots();
        Log("slots=" + m_Slots.Count);

        for (int loop = 1; loop <= LOOPS; loop++)
        {
            for (int s = 0; s < Stages.Length; s++)
            {
                Apply(s);
                m_Label = "[" + loop + "/" + LOOPS + "] " + Stages[s].label;
                Log("STAGE " + s + " " + Stages[s].label);
                yield return new WaitForSecondsRealtime(STAGE_SECONDS);
            }
        }
        Apply(0);
        m_Label = "DONE - sequence finished";
        Log("DONE");
    }

    static bool IsExcluded(string sn)
    {
        return sn.StartsWith("TextMeshPro") || sn.StartsWith("TMP") || sn.StartsWith("UI/") || sn.StartsWith("Diag/");
    }

    void BuildSlots()
    {
        foreach (var r in Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (!(r is MeshRenderer) && !(r is SkinnedMeshRenderer)) continue;
            var orig = r.sharedMaterials;
            bool any = false;
            foreach (var m in orig)
                if (m != null && m.shader != null && !IsExcluded(m.shader.name) && m.renderQueue < 3000) any = true;
            if (any) m_Slots.Add(new Slot { renderer = r, original = orig });
        }
    }

    Material Make(Material src, Stage st)
    {
        Material c;
        if (st.template)
        {
            c = new Material(m_Templates[st.shader]);
            if (src.HasProperty("_MainTex"))
            {
                c.SetTexture("_MainTex", src.GetTexture("_MainTex"));
                c.SetTextureScale("_MainTex", src.GetTextureScale("_MainTex"));
                c.SetTextureOffset("_MainTex", src.GetTextureOffset("_MainTex"));
            }
            c.SetColor("_Color", src.HasProperty("_Color") ? src.GetColor("_Color") : Color.white);
        }
        else
        {
            c = new Material(src);
            c.shader = m_Templates[st.shader].shader;
        }
        c.name = "BISECT_" + src.name;
        c.renderQueue = src.renderQueue;
        m_Made.Add(c);
        return c;
    }

    void Apply(int stage)
    {
        foreach (var s in m_Slots) if (s.renderer != null) s.renderer.sharedMaterials = s.original;
        foreach (var m in m_Made) if (m != null) Object.Destroy(m);
        m_Made.Clear();
        if (stage == 0) return;
        var st = Stages[stage];
        var cache = new Dictionary<Material, Material>();
        int n = 0;
        foreach (var s in m_Slots)
        {
            if (s.renderer == null) continue;
            var mats = new Material[s.original.Length];
            for (int i = 0; i < mats.Length; i++)
            {
                var m = s.original[i];
                bool eligible = m != null && m.shader != null && !IsExcluded(m.shader.name) && m.renderQueue < 3000
                    && (st.all || IsLitShader(m.shader.name));
                if (!eligible) { mats[i] = m; continue; }
                Material c;
                if (!cache.TryGetValue(m, out c)) { c = Make(m, st); cache[m] = c; }
                mats[i] = c;
                n++;
            }
            s.renderer.sharedMaterials = mats;
        }
        Log("applied stage " + stage + ": slots swapped=" + n + " distinct materials=" + cache.Count);
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


def all_files():
    files = []
    for v in VARIANTS:
        i = v[0]
        files += [
            (shader_rel(i), build_shader(v)),
            (shader_rel(i) + ".meta", shader_meta(i)),
            (mat_rel(i), build_mat(i)),
            (mat_rel(i) + ".meta", mat_meta(i)),
        ]
    files += [(PROBE_REL_PATH, PROBE_CONTENT), (PROBE_META_REL_PATH, PROBE_META_CONTENT)]
    return files


def detect(export_dir, profile=None):
    findings = []
    if not os.path.exists(os.path.join(export_dir, PROBE_REL_PATH)):
        findings.append(f"Variant bisect not installed in {PROBE_REL_PATH}")
    return findings


def apply(export_dir, profile=None, dry_run=False):
    changes = 0
    details = []
    for rel_path, content in all_files():
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
    for rel_path, _ in all_files():
        full_path = os.path.join(export_dir, rel_path)
        if os.path.exists(full_path):
            changes += 1
            details.append(f"Removed {rel_path}")
            if not dry_run:
                os.remove(full_path)
    return {"changes_applied": changes, "details": details}


def verify(export_dir, profile=None):
    missing = [p for p, _ in all_files() if not os.path.exists(os.path.join(export_dir, p))]
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
