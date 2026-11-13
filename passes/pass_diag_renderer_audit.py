#!/usr/bin/env python3
"""
Disposable Diagnostic Pass: Renderer Audit & Staged Shader Bisect
-----------------------------------------------------------------
Answers "why is the MainMenu 3D scene black on Quest?" in ONE build by running
a timed, self-bisecting experiment at runtime and reporting through a channel
that does not depend on UnityEngine.Debug.Log (which did not reach logcat in
the Build 8 APK):

  1. android.util.Log via JNI  -> `adb logcat -s LUNA_AUDIT:I`
  2. file in persistentDataPath -> luna_audit.log (adb pull)
  3. UnityEngine.Debug.Log      -> best effort

Timeline (each stage prints `STAGE_DONE <name>` so a host script can screenshot):
  t+3s   baseline      per-renderer / camera / light / RenderSettings audit
  t+10s  pp_off        disable every PostProcessLayer on every camera
  t+18s  legacy_flat   Legacy/Hidden/unsupported-shader opaque renderers -> Diag/FlatTex
  t+27s  all_flat      every opaque Mesh/SkinnedMesh renderer             -> Diag/FlatTex
  t+36s  final         audit again

How to read the screenshots (stages are cumulative):
  - pp_off fixes it          -> Post Processing stack on CAM2 is overwriting CAM output.
  - legacy_flat fixes it     -> built-in legacy shaders (fileID-referenced) are the problem.
  - only all_flat fixes it   -> Shader Forge stubs (Object/Clouds/...) are wrong too.
  - nothing fixes it         -> not materials: culling / camera composite / frustum.

Creates (all disposable, fixed GUIDs, removed by `clean`):
  Assets/Shader/Diag_FlatTex.shader            unlit textured, Cull Off, no fog/light deps
  Assets/Resources/DiagFlatTex.mat             forces shader inclusion in the player build
  Assets/Scripts/Assembly-CSharp/RuntimeRendererAudit.cs

Usage:
  python3 passes/pass_diag_renderer_audit.py apply [export_dir]
  python3 passes/pass_diag_renderer_audit.py clean [export_dir]
"""

import os
import sys

SHADER_REL_PATH = "Assets/Shader/Diag_FlatTex.shader"
SHADER_META_REL_PATH = SHADER_REL_PATH + ".meta"
MAT_REL_PATH = "Assets/Resources/DiagFlatTex.mat"
MAT_META_REL_PATH = MAT_REL_PATH + ".meta"
AUDIT_REL_PATH = "Assets/Scripts/Assembly-CSharp/RuntimeRendererAudit.cs"
AUDIT_META_REL_PATH = AUDIT_REL_PATH + ".meta"

SHADER_GUID = "d1a90000000000000000000000000004"
MAT_GUID = "d1a90000000000000000000000000005"
AUDIT_GUID = "d1a90000000000000000000000000006"

SHADER_CONTENT = r"""Shader "Diag/FlatTex" {
    Properties {
        _MainTex ("MainTex", 2D) = "white" {}
        _Color ("Color", Color) = (1, 1, 1, 1)
    }
    SubShader {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 100
        Cull Off
        Pass {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

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
                fixed4 c = tex2D(_MainTex, i.uv) * _Color;
                return fixed4(c.rgb, 1);
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
  m_Name: DiagFlatTex
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
    m_Floats: {}
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

AUDIT_CONTENT = r"""using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Scripting;

// Disposable diagnostic (pass_diag_renderer_audit.py). Safe to delete: `clean`.
[Preserve]
public class RuntimeRendererAudit : MonoBehaviour
{
    const string TAG = "LUNA_AUDIT";
    static string s_FilePath;
#if UNITY_ANDROID && !UNITY_EDITOR
    static AndroidJavaClass s_AndroidLog;
#endif

    readonly Dictionary<Material, Material> m_Remap = new Dictionary<Material, Material>();
    Material m_Template;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void InitOnSceneLoad()
    {
        if (SceneManager.GetActiveScene().name != "MainMenu") return;
        if (GameObject.Find("[DIAG_RENDERER_AUDIT]") != null) return;
        var go = new GameObject("[DIAG_RENDERER_AUDIT]");
        go.AddComponent<RuntimeRendererAudit>();
        DontDestroyOnLoad(go);
    }

    // Three independent sinks: JNI logcat (reliable), file, Debug.Log (best effort).
    static void Log(string msg, bool toFileOnly = false)
    {
        try
        {
            if (s_FilePath == null) s_FilePath = Path.Combine(Application.persistentDataPath, "luna_audit.log");
            File.AppendAllText(s_FilePath, msg + "\n");
        }
        catch { }
        if (toFileOnly) return;
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

    IEnumerator Start()
    {
        try { File.WriteAllText(Path.Combine(Application.persistentDataPath, "luna_audit.log"), ""); } catch { }
        m_Template = Resources.Load<Material>("DiagFlatTex");
        Log("BEGIN pkg=" + Application.identifier + " scene=" + SceneManager.GetActiveScene().name + " template=" + (m_Template != null) + " file=" + Application.persistentDataPath);

        yield return new WaitForSeconds(3f);
        Audit("baseline");
        Log("STAGE_DONE baseline");

        yield return new WaitForSeconds(7f);
        int pp = DisablePostProcessLayers();
        Log("pp_off: disabled PostProcessLayer components = " + pp);
        yield return new WaitForSeconds(1f);
        Log("STAGE_DONE pp_off");

        yield return new WaitForSeconds(7f);
        int a = Remap(true);
        Log("legacy_flat: remapped material slots = " + a);
        yield return new WaitForSeconds(1f);
        Log("STAGE_DONE legacy_flat");

        yield return new WaitForSeconds(8f);
        int b = Remap(false);
        Log("all_flat: remapped material slots = " + b);
        yield return new WaitForSeconds(1f);
        Log("STAGE_DONE all_flat");

        yield return new WaitForSeconds(8f);
        Audit("final");
        Log("STAGE_DONE final");
    }

    int DisablePostProcessLayers()
    {
        int n = 0;
        foreach (var c in Object.FindObjectsByType<Camera>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            foreach (var b in c.GetComponents<Behaviour>())
            {
                if (b != null && b.GetType().Name == "PostProcessLayer" && b.enabled)
                {
                    b.enabled = false;
                    n++;
                }
            }
        }
        return n;
    }

    static bool IsExcludedShader(string sn)
    {
        return sn.StartsWith("TextMeshPro") || sn.StartsWith("TMP") || sn.StartsWith("UI/") || sn.StartsWith("Diag/");
    }

    Material GetFlat(Material src)
    {
        Material flat;
        if (m_Remap.TryGetValue(src, out flat)) return flat;
        flat = new Material(m_Template);
        flat.name = "FLAT_" + src.name;
        if (src.HasProperty("_MainTex"))
        {
            flat.SetTexture("_MainTex", src.GetTexture("_MainTex"));
            flat.SetTextureScale("_MainTex", src.GetTextureScale("_MainTex"));
            flat.SetTextureOffset("_MainTex", src.GetTextureOffset("_MainTex"));
        }
        flat.SetColor("_Color", src.HasProperty("_Color") ? src.GetColor("_Color") : Color.white);
        flat.renderQueue = src.renderQueue;
        m_Remap[src] = flat;
        return flat;
    }

    int Remap(bool legacyOnly)
    {
        if (m_Template == null)
        {
            Log("ERROR Remap: DiagFlatTex template missing (Resources.Load returned null)");
            return -1;
        }
        int slots = 0;
        foreach (var r in Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (!(r is MeshRenderer) && !(r is SkinnedMeshRenderer)) continue;
            if (r.gameObject.name == "DIAG_TEST_CUBE") continue;
            var mats = r.sharedMaterials;
            bool changed = false;
            for (int i = 0; i < mats.Length; i++)
            {
                var m = mats[i];
                if (m == null || m.shader == null) continue;
                string sn = m.shader.name;
                if (IsExcludedShader(sn)) continue;
                if (m.renderQueue >= 3000) continue; // keep blended quads (fog walls, shadows) untouched
                if (legacyOnly)
                {
                    bool legacy = sn.StartsWith("Legacy Shaders/") || sn.StartsWith("Hidden/") || !m.shader.isSupported;
                    if (!legacy) continue;
                }
                mats[i] = GetFlat(m);
                changed = true;
                slots++;
            }
            if (changed) r.sharedMaterials = mats;
        }
        return slots;
    }

    static string HierPath(Transform t)
    {
        string s = t.name;
        for (int i = 0; i < 2 && t.parent != null; i++)
        {
            t = t.parent;
            s = t.name + "/" + s;
        }
        return s;
    }

    void Audit(string tag)
    {
        Log("[" + tag + "] gfx=" + SystemInfo.graphicsDeviceType + " ver=" + SystemInfo.graphicsDeviceVersion + " gpu=" + SystemInfo.graphicsDeviceName
            + " colorSpace=" + QualitySettings.activeColorSpace + " screen=" + Screen.width + "x" + Screen.height + " t=" + Time.realtimeSinceStartup.ToString("F1"));
        Log("[" + tag + "] quality pixelLights=" + QualitySettings.pixelLightCount + " lodBias=" + QualitySettings.lodBias + " maxLOD=" + QualitySettings.maximumLODLevel
            + " shadows=" + QualitySettings.shadows + " shadowDist=" + QualitySettings.shadowDistance + " globalShaderMaxLOD=" + Shader.globalMaximumLOD);
        Log("[" + tag + "] render fog=" + RenderSettings.fog + " mode=" + RenderSettings.fogMode + " start=" + RenderSettings.fogStartDistance + " end=" + RenderSettings.fogEndDistance
            + " color=" + RenderSettings.fogColor + " ambientMode=" + RenderSettings.ambientMode + " ambient=" + RenderSettings.ambientLight
            + " skyColor=" + RenderSettings.ambientSkyColor + " skybox=" + (RenderSettings.skybox != null ? RenderSettings.skybox.name : "null"));

        var lightCounts = new Dictionary<string, int>();
        foreach (var l in Object.FindObjectsByType<Light>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
        {
            string k = l.type + (l.enabled ? "" : "(disabled)") + "/" + l.shadows;
            int n; lightCounts.TryGetValue(k, out n); lightCounts[k] = n + 1;
        }
        var ls = new StringBuilder();
        foreach (var kv in lightCounts) ls.Append(kv.Key + "=" + kv.Value + " ");
        Log("[" + tag + "] lights " + ls);

        Camera main = null;
        foreach (var c in Object.FindObjectsByType<Camera>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (c.gameObject.name == "CAM") main = c;
            string rt = c.targetTexture != null ? (c.targetTexture.width + "x" + c.targetTexture.height) : "backbuffer";
            var comps = new StringBuilder();
            foreach (var b in c.GetComponents<Behaviour>())
                if (b != null) comps.Append(b.GetType().Name + (b.enabled ? "+" : "-") + " ");
            Log("[" + tag + "] cam '" + c.name + "' active=" + c.gameObject.activeInHierarchy + " enabled=" + c.enabled + " depth=" + c.depth + " clear=" + c.clearFlags
                + " mask=" + c.cullingMask + " near=" + c.nearClipPlane + " far=" + c.farClipPlane + " rt=" + rt + " pos=" + c.transform.position + " comps: " + comps);
        }

        // Per-shader aggregate: total / active+enabled / visible this frame.
        var agg = new Dictionary<string, int[]>();
        int nullMats = 0;
        foreach (var r in Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            bool live = r.gameObject.activeInHierarchy && r.enabled;
            var mats = r.sharedMaterials;
            if (mats.Length == 0) nullMats++;
            for (int i = 0; i < mats.Length; i++)
            {
                var m = mats[i];
                string key;
                if (m == null || m.shader == null) { key = "<null material/shader>"; nullMats++; }
                else key = m.shader.name + " | supported=" + m.shader.isSupported + " | passes=" + m.passCount + " | maxLOD=" + m.shader.maximumLOD;
                int[] a;
                if (!agg.TryGetValue(key, out a)) { a = new int[3]; agg[key] = a; }
                a[0]++;
                if (live) a[1]++;
                if (live && r.isVisible) a[2]++;
            }
        }
        var keys = new List<string>(agg.Keys);
        keys.Sort((x, y) => agg[y][0].CompareTo(agg[x][0]));
        foreach (var k in keys)
            Log("[" + tag + "] shader " + k + " -> total=" + agg[k][0] + " live=" + agg[k][1] + " visible=" + agg[k][2]);
        Log("[" + tag + "] nullMaterialSlots=" + nullMats);

        // Full per-renderer dump goes to the file only (hundreds of lines); live-but-invisible ones also go to logcat.
        int shown = 0;
        foreach (var r in Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            bool live = r.gameObject.activeInHierarchy && r.enabled;
            var mats = r.sharedMaterials;
            string sh = (mats.Length > 0 && mats[0] != null && mats[0].shader != null) ? mats[0].shader.name : "<none>";
            string mn = (mats.Length > 0 && mats[0] != null) ? mats[0].name : "<none>";
            float dist = main != null ? Vector3.Distance(main.transform.position, r.bounds.center) : -1f;
            string line = "[" + tag + "] R " + HierPath(r.transform) + " | " + r.GetType().Name + " live=" + live + " vis=" + r.isVisible + " layer=" + r.gameObject.layer
                + " dist=" + dist.ToString("F1") + " mat=" + mn + " shader=" + sh;
            Log(line, true);
            if (live && !r.isVisible && !(r is ParticleSystemRenderer) && shown < 40)
            {
                shown++;
                Log(line);
            }
        }
    }
}
"""

AUDIT_META_CONTENT = """fileFormatVersion: 2
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
""" % AUDIT_GUID

FILES = [
    (SHADER_REL_PATH, SHADER_CONTENT),
    (SHADER_META_REL_PATH, SHADER_META_CONTENT),
    (MAT_REL_PATH, MAT_CONTENT),
    (MAT_META_REL_PATH, MAT_META_CONTENT),
    (AUDIT_REL_PATH, AUDIT_CONTENT),
    (AUDIT_META_REL_PATH, AUDIT_META_CONTENT),
]


def detect(export_dir, profile=None):
    findings = []
    if not os.path.exists(os.path.join(export_dir, AUDIT_REL_PATH)):
        findings.append(f"Renderer audit not installed in {AUDIT_REL_PATH}")
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
