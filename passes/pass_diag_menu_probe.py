#!/usr/bin/env python3
"""
Disposable Diagnostic Pass: Main Menu Camera Probe & Test Cube
--------------------------------------------------------------
Builds a non-invasive diagnostic probe to answer a single binary question:
"Does CAM deliver 3D geometry to the Quest display or not?"

Creates:
1. Assets/Shader/Diag_PureRedUnlit.shader: bulletproof solid red unlit shader (no light/fog/tex deps).
2. Assets/Resources/DiagRedCube.mat: material referencing Diag_PureRedUnlit.shader.
3. Assets/Scripts/Assembly-CSharp/RuntimeCameraProbe.cs:
   - Spawns a 0.5m red cube 2m in front of CAM on Layer 0.
   - Logs Camera.allCameras, activeColorSpace, screen resolution, and cube culling state at Start() and +2s.
   - Log prefix: LUNA_PROBE.

Usage:
  python3 passes/pass_diag_menu_probe.py apply [export_dir]
  python3 passes/pass_diag_menu_probe.py clean [export_dir]
"""

import os
import sys

SHADER_REL_PATH = "Assets/Shader/Diag_PureRedUnlit.shader"
SHADER_META_REL_PATH = "Assets/Shader/Diag_PureRedUnlit.shader.meta"
MAT_REL_PATH = "Assets/Resources/DiagRedCube.mat"
MAT_META_REL_PATH = "Assets/Resources/DiagRedCube.mat.meta"
PROBE_REL_PATH = "Assets/Scripts/Assembly-CSharp/RuntimeCameraProbe.cs"
PROBE_META_REL_PATH = "Assets/Scripts/Assembly-CSharp/RuntimeCameraProbe.cs.meta"

SHADER_CONTENT = """Shader "Diag/PureRedUnlit" {
    Properties {
        _Color ("Main Color", Color) = (1, 0, 0, 1)
    }
    SubShader {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 100
        Pass {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            struct appdata {
                float4 vertex : POSITION;
            };

            struct v2f {
                float4 pos : SV_POSITION;
            };

            v2f vert(appdata v) {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target {
                return fixed4(1, 0, 0, 1);
            }
            ENDCG
        }
    }
}
"""

SHADER_META_CONTENT = """fileFormatVersion: 2
guid: d1a90000000000000000000000000001
ShaderImporter:
  externalObjects: {}
  defaultTextures: []
  nonModifiableTextures: []
  userData: 
  assetBundleName: 
  assetBundleVariant: 
"""

MAT_CONTENT = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  serializedVersion: 6
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_Name: DiagRedCube
  m_Shader: {fileID: 4800000, guid: d1a90000000000000000000000000001, type: 3}
  m_ShaderKeywords: 
  m_LightmapFlags: 4
  m_EnableInstancingVariants: 0
  m_DoubleSidedGI: 0
  m_CustomRenderQueue: -1
  stringTagMap: {}
  disabledShaderPasses: []
  m_SavedProperties:
    serializedVersion: 3
    m_TexEnvs: {}
    m_Floats: {}
    m_Colors:
      _Color: {r: 1, g: 0, b: 0, a: 1}
  m_BuildTextureStacks: []
"""

MAT_META_CONTENT = """fileFormatVersion: 2
guid: d1a90000000000000000000000000002
NativeFormatImporter:
  externalObjects: {}
  mainObjectFileID: 2100000
  userData: 
  assetBundleName: 
  assetBundleVariant: 
"""

PROBE_CONTENT = """using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Scripting;

[Preserve]
public class RuntimeCameraProbe : MonoBehaviour
{
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void InitOnSceneLoad()
    {
        Scene currentScene = SceneManager.GetActiveScene();
        if (currentScene.name == "MainMenu")
        {
            if (GameObject.Find("[DIAG_CAMERA_PROBE]") == null)
            {
                var go = new GameObject("[DIAG_CAMERA_PROBE]");
                go.AddComponent<RuntimeCameraProbe>();
                DontDestroyOnLoad(go);
            }
        }
    }

    private void Start()
    {
        LogAllCameras("Start");
        SpawnDiagCube();
        StartCoroutine(LogAfterDelay(2.0f));
    }

    private void SpawnDiagCube()
    {
        Camera cam = null;
        var camGo = GameObject.Find("CAM");
        if (camGo != null)
        {
            cam = camGo.GetComponent<Camera>();
        }
        if (cam == null)
        {
            cam = Camera.main;
        }

        if (cam == null)
        {
            Debug.LogError("LUNA_PROBE: Could not find CAM or Camera.main to spawn cube!");
            return;
        }

        // Spawn cube and parent to CAM so it stays locked in center of view
        GameObject cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
        cube.name = "DIAG_TEST_CUBE";
        cube.transform.SetParent(cam.transform, false);
        cube.transform.localPosition = new Vector3(0f, 0f, 2.0f);
        cube.transform.localRotation = Quaternion.identity;
        cube.transform.localScale = Vector3.one * 0.5f;
        cube.layer = 0;

        // Clean collider so it doesn't interact with player or physics
        var col = cube.GetComponent<Collider>();
        if (col != null) Destroy(col);

        // Assign Pure Red Unlit Material
        Material redMat = Resources.Load<Material>("DiagRedCube");
        if (redMat == null)
        {
            Shader s = Shader.Find("Diag/PureRedUnlit") ?? Shader.Find("Unlit/Color");
            if (s != null)
            {
                redMat = new Material(s);
                redMat.color = Color.red;
            }
        }

        if (redMat != null)
        {
            cube.GetComponent<Renderer>().material = redMat;
        }
        else
        {
            Debug.LogError("LUNA_PROBE: Failed to load or create pure red unlit material!");
        }

        bool inMask = (cam.cullingMask & (1 << cube.layer)) != 0;
        Debug.Log($"LUNA_PROBE cube created: pos={cube.transform.position}, forward={cam.transform.forward}, scale={cube.transform.localScale}, layer={cube.layer}, camCullingMask={cam.cullingMask}, inCullingMask={inMask}");
    }

    private IEnumerator LogAfterDelay(float delay)
    {
        yield return new WaitForSeconds(delay);
        LogAllCameras("After2Sec");
    }

    private void LogAllCameras(string tag)
    {
        Debug.Log($"LUNA_PROBE [{tag}] QualitySettings.activeColorSpace={QualitySettings.activeColorSpace}, Screen={Screen.width}x{Screen.height}");
        Camera[] activeCams = Camera.allCameras;
        Camera[] allSceneCams = Object.FindObjectsOfType<Camera>(true);
        Debug.Log($"LUNA_PROBE [{tag}] Active cameras (Camera.allCameras): {activeCams.Length}, Total scene cameras: {allSceneCams.Length}");

        foreach (var c in allSceneCams)
        {
            if (c == null) continue;
            string rtInfo = (c.targetTexture != null) ? $"{c.targetTexture.width}x{c.targetTexture.height} ({c.targetTexture.format})" : "null (Backbuffer)";
            Debug.Log($"LUNA_PROBE [{tag}] Cam '{c.name}' (goActive={c.gameObject.activeInHierarchy}): enabled={c.enabled}, depth={c.depth}, clearFlags={c.clearFlags}, cullingMask={c.cullingMask}, targetTexture={rtInfo}, allowHDR={c.allowHDR}, allowMSAA={c.allowMSAA}, rect={c.rect}, pos={c.transform.position}, forward={c.transform.forward}");
        }
    }
}
"""

PROBE_META_CONTENT = """fileFormatVersion: 2
guid: d1a90000000000000000000000000003
MonoImporter:
  externalObjects: {}
  serializedVersion: 2
  defaultReferences: []
  executionOrder: 0
  icon: {fileID: 0}
  userData: 
  assetBundleName: 
  assetBundleVariant: 
"""

def detect(export_dir, profile=None):
    findings = []
    probe_path = os.path.join(export_dir, PROBE_REL_PATH)
    if not os.path.exists(probe_path):
        findings.append(f"Diagnostic probe not installed in {PROBE_REL_PATH}")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    files_to_write = [
        (SHADER_REL_PATH, SHADER_CONTENT),
        (SHADER_META_REL_PATH, SHADER_META_CONTENT),
        (MAT_REL_PATH, MAT_CONTENT),
        (MAT_META_REL_PATH, MAT_META_CONTENT),
        (PROBE_REL_PATH, PROBE_CONTENT),
        (PROBE_META_REL_PATH, PROBE_META_CONTENT)
    ]

    changes = 0
    details = []

    for rel_path, content in files_to_write:
        full_path = os.path.join(export_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if not os.path.exists(full_path):
            changes += 1
            details.append(f"Created {rel_path}")
            if not dry_run:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

    return {"changes_applied": changes, "details": details}

def clean(export_dir, profile=None, dry_run=False):
    files_to_remove = [
        SHADER_REL_PATH,
        SHADER_META_REL_PATH,
        MAT_REL_PATH,
        MAT_META_REL_PATH,
        PROBE_REL_PATH,
        PROBE_META_REL_PATH
    ]

    changes = 0
    details = []

    for rel_path in files_to_remove:
        full_path = os.path.join(export_dir, rel_path)
        if os.path.exists(full_path):
            changes += 1
            details.append(f"Removed {rel_path}")
            if not dry_run:
                os.remove(full_path)

    return {"changes_applied": changes, "details": details}

def verify(export_dir, profile=None):
    probe_path = os.path.join(export_dir, PROBE_REL_PATH)
    mat_path = os.path.join(export_dir, MAT_REL_PATH)
    shader_path = os.path.join(export_dir, SHADER_REL_PATH)
    ok = os.path.exists(probe_path) and os.path.exists(mat_path) and os.path.exists(shader_path)
    return {"passed": ok, "remaining_issues": 0 if ok else 1}


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

