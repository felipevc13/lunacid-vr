using UnityEditor;
using UnityEngine;

// Temporary: reports compile errors of the port's shader overrides.
public static class LunaShaderCheck
{
    public static void Run()
    {
        AssetDatabase.Refresh();
        foreach (var path in System.IO.Directory.GetFiles("Assets/Shader", "*.shader"))
        {
            var s = AssetDatabase.LoadAssetAtPath<Shader>(path);
            if (s == null) continue;
            ShaderUtil.CompilePass(new Material(s), 0, true);
            foreach (var m in ShaderUtil.GetShaderMessages(s))
                if (m.severity == UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error)
                    Debug.Log("SHADERCHECK " + path + ": " + m.message + " line " + m.line + " " + m.platform);
        }
        Debug.Log("SHADERCHECK done");
    }
}
