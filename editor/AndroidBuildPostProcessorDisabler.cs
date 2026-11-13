using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using UnityEngine.SceneManagement;

public class AndroidBuildPostProcessorDisabler : IProcessSceneWithReport
{
    public int callbackOrder => 0;

    public void OnProcessScene(Scene scene, BuildReport report)
    {
        // Only run for Android standalone builds
        if (report != null && report.summary.platform != BuildTarget.Android)
            return;

        int disabledCount = 0;

        // 1. PostProcessing Stack v2 (PostProcessLayer, PostProcessVolume)
        var postProcessLayers = UnityEngine.Object.FindObjectsOfType<UnityEngine.Rendering.PostProcessing.PostProcessLayer>(true);
        foreach (var ppl in postProcessLayers)
        {
            if (ppl.enabled)
            {
                ppl.enabled = false;
                disabledCount++;
            }
        }

        var postProcessVolumes = UnityEngine.Object.FindObjectsOfType<UnityEngine.Rendering.PostProcessing.PostProcessVolume>(true);
        foreach (var ppv in postProcessVolumes)
        {
            if (ppv.enabled)
            {
                ppv.enabled = false;
                disabledCount++;
            }
        }

        // 2. RetroLookPro components if any MonoBehaviour inherits or references them
        var allBehaviours = UnityEngine.Object.FindObjectsOfType<MonoBehaviour>(true);
        foreach (var mb in allBehaviours)
        {
            if (mb == null) continue;
            string typeName = mb.GetType().Name;
            if (typeName.Contains("RetroLook") || typeName.Contains("RLPro") || typeName.Contains("AnalogTV") || typeName.Contains("PixelNostalgia"))
            {
                if (mb.enabled)
                {
                    mb.enabled = false;
                    disabledCount++;
                }
            }
        }

        if (disabledCount > 0)
        {
            UnityEngine.Debug.Log($"[PostProcessDisabler] Scene '{scene.name}': Disabled {disabledCount} post-processing / retro components for Android build.");
        }
    }
}

#if UNITY_ANDROID && !UNITY_EDITOR
public static class AndroidPostProcessingRuntimeGuard
{
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    static void Init()
    {
        SceneManager.sceneLoaded += (scene, mode) =>
        {
            foreach (var ppl in UnityEngine.Object.FindObjectsOfType<UnityEngine.Rendering.PostProcessing.PostProcessLayer>(true))
            {
                ppl.enabled = false;
            }
            foreach (var ppv in UnityEngine.Object.FindObjectsOfType<UnityEngine.Rendering.PostProcessing.PostProcessVolume>(true))
            {
                ppv.enabled = false;
            }
        };
    }
}
#endif

