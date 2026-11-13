using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

public class MaterialShaderAudit
{
    [MenuItem("Tools/Audit Material Shaders")]
    public static void RunAudit()
    {
        string[] guids = AssetDatabase.FindAssets("t:Material");
        Debug.Log($"[MaterialShaderAudit] Found {guids.Length} materials via AssetDatabase.");

        var shaderUsage = new Dictionary<string, List<string>>();
        int missingCount = 0;
        int unsupportedCount = 0;

        foreach (string guid in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) continue;

            string shaderName = (mat.shader != null) ? mat.shader.name : "<Missing Shader>";
            if (mat.shader == null || shaderName.Contains("InternalErrorShader") || shaderName == "<Missing Shader>")
            {
                missingCount++;
            }
            else if (!mat.shader.isSupported)
            {
                unsupportedCount++;
            }

            if (!shaderUsage.ContainsKey(shaderName))
            {
                shaderUsage[shaderName] = new List<string>();
            }
            shaderUsage[shaderName].Add(path);
        }

        string reportPath = Path.Combine(Application.dataPath, "..", "Logs", "MaterialAudit.txt");
        Directory.CreateDirectory(Path.GetDirectoryName(reportPath));

        using (var writer = new StreamWriter(reportPath, false))
        {
            writer.WriteLine("=== LUNACID MATERIAL SHADER AUDIT (UNITY 6) ===");
            writer.WriteLine($"Total Materials in AssetDatabase: {guids.Length}");
            writer.WriteLine($"Missing/Error Shaders: {missingCount}");
            writer.WriteLine($"Unsupported Shaders: {unsupportedCount}");
            writer.WriteLine($"Distinct Shaders: {shaderUsage.Count}\n");

            var sorted = shaderUsage.OrderByDescending(kv => kv.Value.Count);
            foreach (var kv in sorted)
            {
                writer.WriteLine($"{kv.Key,-50} : {kv.Value.Count,4} materials");
            }
        }

        Debug.Log($"[MaterialShaderAudit] Audit complete. Report written to {reportPath}");
    }
}
