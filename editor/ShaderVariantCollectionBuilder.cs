using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

public static class ShaderVariantCollectionBuilder
{
    private const string COLLECTION_PATH = "Assets/Shader/LunacidPreloadedVariants.shadervariants";

    // Shaders kept out of Always Included. A shader there is compiled with every keyword combination:
    // Particles/Standard Unlit was 61,920 variants and 84% of the build's shader time (2026-11-12) though its
    // 14 materials use 6 combinations. Its materials and the variant collection bring in what is used (LESSONS 34).
    public static readonly HashSet<string> NotAlwaysIncluded = new HashSet<string> { "Particles/Standard Unlit" };

    public static bool IsShaderExcluded(Shader s)
    {
        if (s == null) return true;
        string sName = s.name;
        if (string.IsNullOrEmpty(sName)) return true;

        // Skip internal error shader and default GUI text shader (marked DontSave in unity default resources)
        if (sName == "Hidden/InternalErrorShader" || sName == "GUI/Text Shader") return true;

        // Skip post-processing, RetroLookPro, ProBuilder
        if (sName.StartsWith("Hidden/PostProcessing/") ||
            sName.StartsWith("RetroLookPro/") ||
            sName.StartsWith("Hidden/ProBuilder/"))
        {
            return true;
        }

        // Check HideFlags.DontSave or internal asset paths
        if (s.hideFlags.HasFlag(HideFlags.DontSave)) return true;

        string assetPath = AssetDatabase.GetAssetPath(s);
        if (!string.IsNullOrEmpty(assetPath) && assetPath.StartsWith("Library/"))
        {
            return true;
        }

        return false;
    }

    [MenuItem("Lunacid/Collect Shaders And Build Variant Collection")]
    public static void CollectAndRegisterAllShaders()
    {
        UnityEngine.Debug.Log("=== [ShaderCollection] Scanning all materials in project ===");

        string[] matGuids = AssetDatabase.FindAssets("t:Material");
        UnityEngine.Debug.Log($"[ShaderCollection] Found {matGuids.Length} total material assets.");

        HashSet<Shader> uniqueShaders = new HashSet<Shader>();
        Dictionary<Shader, HashSet<string>> shaderKeywordsMap = new Dictionary<Shader, HashSet<string>>();

        int validMats = 0;
        foreach (string guid in matGuids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null || mat.shader == null) continue;

            Shader s = mat.shader;
            if (IsShaderExcluded(s)) continue;

            validMats++;
            uniqueShaders.Add(s);

            if (!shaderKeywordsMap.ContainsKey(s))
            {
                shaderKeywordsMap[s] = new HashSet<string>();
            }

            foreach (string kw in mat.shaderKeywords)
            {
                if (!string.IsNullOrEmpty(kw))
                {
                    shaderKeywordsMap[s].Add(kw);
                }
            }
        }

        UnityEngine.Debug.Log($"[ShaderCollection] Valid materials: {validMats}. Unique shaders referenced: {uniqueShaders.Count}.");

        // Build ShaderVariantCollection
        ShaderVariantCollection svc = new ShaderVariantCollection();
        int variantCount = 0;

        PassType[] passTypes = new PassType[]
        {
            PassType.ForwardBase,
            PassType.ForwardAdd,
            PassType.ShadowCaster,
            PassType.Normal
        };

        foreach (var kvp in shaderKeywordsMap)
        {
            Shader s = kvp.Key;
            string sName = s.name;
            if (sName.StartsWith("Hidden/PostProcessing/") ||
                sName.StartsWith("RetroLookPro/") ||
                sName.StartsWith("Hidden/ProBuilder/"))
            {
                continue;
            }
            List<string> kwList = new List<string>(kvp.Value);

            foreach (PassType pt in passTypes)
            {
                try
                {
                    // Add variant with no keywords
                    ShaderVariantCollection.ShaderVariant svBase = new ShaderVariantCollection.ShaderVariant
                    {
                        shader = s,
                        passType = pt,
                        keywords = new string[0]
                    };
                    svc.Add(svBase);
                    variantCount++;

                    // Add variant with material keywords if any
                    if (kwList.Count > 0)
                    {
                        ShaderVariantCollection.ShaderVariant svKw = new ShaderVariantCollection.ShaderVariant
                        {
                            shader = s,
                            passType = pt,
                            keywords = kwList.ToArray()
                        };
                        svc.Add(svKw);
                        variantCount++;
                    }
                }
                catch
                {
                    // Pass type might not exist on shader, ignore
                }
            }
        }

        // Save or update collection asset
        ShaderVariantCollection existing = AssetDatabase.LoadAssetAtPath<ShaderVariantCollection>(COLLECTION_PATH);
        if (existing != null)
        {
            AssetDatabase.DeleteAsset(COLLECTION_PATH);
        }
        AssetDatabase.CreateAsset(svc, COLLECTION_PATH);
        AssetDatabase.SaveAssets();
        UnityEngine.Debug.Log($"[ShaderCollection] Saved ShaderVariantCollection to {COLLECTION_PATH} with {variantCount} variants.");

        // Register in GraphicsSettings
        RegisterInGraphicsSettings(uniqueShaders, svc);
    }

    private static void RegisterInGraphicsSettings(HashSet<Shader> shaders, ShaderVariantCollection svc)
    {
        UnityEngine.Object graphicsSettingsAsset = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/GraphicsSettings.asset")[0];
        SerializedObject so = new SerializedObject(graphicsSettingsAsset);

        // 1. m_AlwaysIncludedShaders
        SerializedProperty alwaysIncluded = so.FindProperty("m_AlwaysIncludedShaders");

        // Clean any invalid or DontSave shaders already present in alwaysIncluded
        for (int i = alwaysIncluded.arraySize - 1; i >= 0; i--)
        {
            SerializedProperty elem = alwaysIncluded.GetArrayElementAtIndex(i);
            if (elem.objectReferenceValue == null)
            {
                alwaysIncluded.DeleteArrayElementAtIndex(i);
            }
            else if (elem.objectReferenceValue is Shader n && NotAlwaysIncluded.Contains(n.name))
            {
                UnityEngine.Debug.Log($"[ShaderCollection] Not always included (its materials bring the variants they use): {n.name}");
                alwaysIncluded.DeleteArrayElementAtIndex(i);
            }
            else if (elem.objectReferenceValue is Shader s && IsShaderExcluded(s))
            {
                UnityEngine.Debug.Log($"[ShaderCollection] Removing excluded/DontSave shader from AlwaysIncluded: {s.name}");
                alwaysIncluded.DeleteArrayElementAtIndex(i);
            }
        }

        HashSet<Shader> alreadyIncluded = new HashSet<Shader>();
        for (int i = 0; i < alwaysIncluded.arraySize; i++)
        {
            SerializedProperty elem = alwaysIncluded.GetArrayElementAtIndex(i);
            if (elem.objectReferenceValue is Shader s && s != null)
            {
                alreadyIncluded.Add(s);
            }
        }

        int addedShaders = 0;
        foreach (Shader s in shaders)
        {
            if (s != null && !alreadyIncluded.Contains(s))
            {
                if (IsShaderExcluded(s) || NotAlwaysIncluded.Contains(s.name))
                {
                    continue;
                }
                alwaysIncluded.InsertArrayElementAtIndex(alwaysIncluded.arraySize);
                alwaysIncluded.GetArrayElementAtIndex(alwaysIncluded.arraySize - 1).objectReferenceValue = s;
                alreadyIncluded.Add(s);
                addedShaders++;
            }
        }

        // 2. m_PreloadedShaders
        SerializedProperty preloaded = so.FindProperty("m_PreloadedShaders");
        bool svcFound = false;
        for (int i = 0; i < preloaded.arraySize; i++)
        {
            SerializedProperty elem = preloaded.GetArrayElementAtIndex(i);
            if (elem.objectReferenceValue == svc)
            {
                svcFound = true;
                break;
            }
        }

        if (!svcFound && svc != null)
        {
            preloaded.InsertArrayElementAtIndex(preloaded.arraySize);
            preloaded.GetArrayElementAtIndex(preloaded.arraySize - 1).objectReferenceValue = svc;
        }

        so.ApplyModifiedProperties();
        AssetDatabase.SaveAssets();
        UnityEngine.Debug.Log($"[ShaderCollection] GraphicsSettings updated: added {addedShaders} shaders to AlwaysIncluded (total: {alwaysIncluded.arraySize}), Preloaded collection linked.");
    }
}

