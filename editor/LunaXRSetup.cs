using UnityEditor;
using UnityEditor.XR.Management;
using UnityEditor.XR.Management.Metadata;
using UnityEngine;
using UnityEngine.XR.Management;
using UnityEngine.XR.OpenXR;
using UnityEngine.XR.OpenXR.Features;

// Turns the Quest build into an immersive OpenXR app (it was a flat 2D panel): OpenXR loader on
// Android, Meta Quest support and the Touch controller profile, and single-pass instanced
// (multiview) rendering, which draws both eyes in one pass to hold 72 fps.
public static class LunaXRSetup
{
    const string SettingsPath = "Assets/XR/XRGeneralSettingsPerBuildTarget.asset";

    public static void Configure()
    {
        EditorBuildSettings.TryGetConfigObject(XRGeneralSettings.k_SettingsKey, out XRGeneralSettingsPerBuildTarget perTarget);
        if (perTarget == null)
        {
            System.IO.Directory.CreateDirectory("Assets/XR");
            perTarget = ScriptableObject.CreateInstance<XRGeneralSettingsPerBuildTarget>();
            AssetDatabase.CreateAsset(perTarget, SettingsPath);
            EditorBuildSettings.AddConfigObject(XRGeneralSettings.k_SettingsKey, perTarget, true);
        }

        var settings = perTarget.SettingsForBuildTarget(BuildTargetGroup.Android);
        if (settings == null)
        {
            settings = ScriptableObject.CreateInstance<XRGeneralSettings>();
            settings.name = "Android Settings";
            var manager = ScriptableObject.CreateInstance<XRManagerSettings>();
            manager.name = "Android Providers";
            settings.Manager = manager;
            perTarget.SetSettingsForBuildTarget(BuildTargetGroup.Android, settings);
            AssetDatabase.AddObjectToAsset(settings, perTarget);
            AssetDatabase.AddObjectToAsset(manager, perTarget);
        }
        settings.InitManagerOnStart = true;
        XRPackageMetadataStore.AssignLoader(settings.Manager, "UnityEngine.XR.OpenXR.OpenXRLoader", BuildTargetGroup.Android);

        var openXR = OpenXRSettings.GetSettingsForBuildTargetGroup(BuildTargetGroup.Android);
        foreach (var feature in openXR.GetFeatures())
        {
            string type = feature.GetType().Name;
            if (type == "MetaQuestFeature" || type == "OculusTouchControllerProfile" || type == "FoveatedRenderingFeature")
            {
                feature.enabled = true;
                // Name entry (character creation) needs the Quest's system keyboard.
                var keyboard = feature.GetType().GetField("enableSystemKeyboard");
                if (keyboard != null) keyboard.SetValue(feature, true);
                EditorUtility.SetDirty(feature);
            }
        }
        openXR.renderMode = OpenXRSettings.RenderMode.SinglePassInstanced;
        // Built-in render pipeline: only the legacy foveation path works (FoveatedRenderingFeature validation).
        openXR.foveatedRenderingApi = OpenXRSettings.BackendFovationApi.Legacy;
        EditorUtility.SetDirty(openXR);
        EditorUtility.SetDirty(settings);
        EditorUtility.SetDirty(perTarget);
        AssetDatabase.SaveAssets();

        Debug.Log("[LunaXR] OpenXR on Android: loaders=" + settings.Manager.activeLoaders.Count
                  + " renderMode=" + openXR.renderMode + " initOnStart=" + settings.InitManagerOnStart);
    }
}
