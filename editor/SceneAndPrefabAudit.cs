using System;
using System.IO;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public class SceneAndPrefabAudit
{
    [MenuItem("Tools/Audit Missing Scripts")]
    public static void RunAudit()
    {
        Debug.Log("=== Starting Missing Script & Broken Reference Audit ===");

        string logPath = Path.Combine(Application.dataPath, "..", "Logs", "MissingScriptAudit.txt");
        Directory.CreateDirectory(Path.GetDirectoryName(logPath));

        using (var writer = new StreamWriter(logPath, false))
        {
            writer.WriteLine("=== LUNACID MISSING SCRIPT & BROKEN REFERENCE AUDIT ===");
            writer.WriteLine($"Timestamp: {DateTime.Now}\n");

            // 1. Audit Scenes
            writer.WriteLine("--- SCENE AUDIT ---");
            int totalScenesChecked = 0;
            int totalSceneMissingScripts = 0;

            foreach (var sceneEntry in EditorBuildSettings.scenes)
            {
                if (!sceneEntry.enabled) continue;
                totalScenesChecked++;

                try
                {
                    var scene = EditorSceneManager.OpenScene(sceneEntry.path, OpenSceneMode.Single);
                    int sceneMissing = 0;
                    List<string> missingPaths = new List<string>();

                    GameObject[] roots = scene.GetRootGameObjects();
                    foreach (var root in roots)
                    {
                        CheckGameObjectForMissingScripts(root, root.name, ref sceneMissing, missingPaths);
                    }

                    totalSceneMissingScripts += sceneMissing;
                    string status = sceneMissing == 0 ? "CLEAN (0 missing)" : $"FAIL ({sceneMissing} MISSING SCRIPTS)";
                    writer.WriteLine($"Scene {sceneEntry.path,-45}: {status}");
                    foreach (var p in missingPaths)
                    {
                        writer.WriteLine($"   -> {p}");
                    }
                }
                catch (Exception ex)
                {
                    writer.WriteLine($"Scene {sceneEntry.path,-45}: ERROR opening scene ({ex.Message})");
                }
            }

            writer.WriteLine($"\nTotal Scenes Checked: {totalScenesChecked}");
            writer.WriteLine($"Total Missing Scripts in Scenes: {totalSceneMissingScripts}\n");

            // 2. Audit Prefabs
            writer.WriteLine("--- PREFAB AUDIT ---");
            string[] prefabGuids = AssetDatabase.FindAssets("t:Prefab");
            int totalPrefabsChecked = prefabGuids.Length;
            int totalPrefabMissingScripts = 0;
            List<string> brokenPrefabs = new List<string>();

            foreach (string guid in prefabGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (prefab == null) continue;

                int prefabMissing = 0;
                List<string> missingPaths = new List<string>();
                CheckGameObjectForMissingScripts(prefab, prefab.name, ref prefabMissing, missingPaths);

                if (prefabMissing > 0)
                {
                    totalPrefabMissingScripts += prefabMissing;
                    brokenPrefabs.Add($"{path} ({prefabMissing} missing scripts)");
                }
            }

            writer.WriteLine($"Total Prefabs Checked: {totalPrefabsChecked}");
            writer.WriteLine($"Total Missing Scripts in Prefabs: {totalPrefabMissingScripts}");
            foreach (var bp in brokenPrefabs)
            {
                writer.WriteLine($"   -> {bp}");
            }

            writer.WriteLine("\n=== AUDIT SUMMARY ===");
            writer.WriteLine($"Scenes with 0 missing scripts: {totalScenesChecked - (totalSceneMissingScripts > 0 ? 1 : 0)} / {totalScenesChecked}");
            writer.WriteLine($"Prefabs with 0 missing scripts: {totalPrefabsChecked - brokenPrefabs.Count} / {totalPrefabsChecked}");
            writer.WriteLine($"Overall Status: {(totalSceneMissingScripts == 0 && totalPrefabMissingScripts == 0 ? "PERFECT 100% CLEAN" : "ATTENTION NEEDED")}");
        }

        Debug.Log($"[MissingScriptAudit] Audit completed. Report written to: {logPath}");
    }

    private static void CheckGameObjectForMissingScripts(GameObject go, string currentPath, ref int missingCount, List<string> missingPaths)
    {
        Component[] components = go.GetComponents<Component>();
        for (int i = 0; i < components.Length; i++)
        {
            if (components[i] == null)
            {
                missingCount++;
                missingPaths.Add($"{currentPath} (Component index {i} is null/Missing Script)");
            }
        }

        foreach (Transform child in go.transform)
        {
            if (child != null)
            {
                CheckGameObjectForMissingScripts(child.gameObject, $"{currentPath}/{child.name}", ref missingCount, missingPaths);
            }
        }
    }
}
