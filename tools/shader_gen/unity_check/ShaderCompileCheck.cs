// Compiles shaders variant by variant for Vulkan / Android, inside a throwaway Unity 6 project, and
// writes every compiler message to a JSON-lines file. Run by tools/shader_gen/compile_check.py:
//   Unity -batchmode -projectPath P -buildTarget Android -executeMethod ShaderCompileCheck.Run
//         -manifest manifest.json -quit
// The manifest lists, per shader, the passes and the keyword sets to compile (see compile_check.py).
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.Rendering;
using UnityEngine;
using UnityEngine.Rendering;

public static class ShaderCompileCheck
{
    [Serializable] class PassJob { public int subshader; public int pass; public string name; public string[] sets; }
    [Serializable] class ShaderJob { public string path; public string name; public PassJob[] passes; }
    [Serializable] class Manifest { public ShaderJob[] shaders; public string[] extra; public string output; }

    static string Arg(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        return null;
    }

    static string Esc(string s)
    {
        if (s == null) return "";
        var sb = new StringBuilder();
        foreach (var c in s)
        {
            if (c == '"' || c == '\\') sb.Append('\\').Append(c);
            else if (c == '\n') sb.Append("\\n");
            else if (c == '\r') { }
            else if (c == '\t') sb.Append("\\t");
            else if (c < 32) sb.Append(' ');
            else sb.Append(c);
        }
        return sb.ToString();
    }

    public static void Run()
    {
        int code = 0;
        try { RunInner(); }
        catch (Exception e) { Debug.LogError("ShaderCompileCheck failed: " + e); code = 1; }
        EditorApplication.Exit(code);
    }

    static void RunInner()
    {
        var m = JsonUtility.FromJson<Manifest>(File.ReadAllText(Arg("-manifest")));
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        var lines = new List<string>();
        int bytes = 0;  // size of the last compiled variant (SPIR-V), for comparisons
        Action<string, string, string, string, bool, string, string, int> rec =
            (shader, pass, stage, keywords, ok, severity, message, line) =>
                lines.Add(string.Format(
                    "{{\"shader\":\"{0}\",\"pass\":\"{1}\",\"stage\":\"{2}\",\"keywords\":\"{3}\",\"ok\":{4},\"severity\":\"{5}\",\"message\":\"{6}\",\"line\":{7},\"bytes\":{8}}}",
                    Esc(shader), Esc(pass), stage, Esc(keywords), ok ? "true" : "false", severity, Esc(message), line, bytes));

        foreach (var job in m.shaders)
        {
            bytes = 0;
            var sh = AssetDatabase.LoadAssetAtPath<Shader>(job.path);
            if (sh == null) { rec(job.name, "", "load", "", false, "Error", "asset did not load as a Shader", 0); continue; }
            foreach (var msg in ShaderUtil.GetShaderMessages(sh))
                rec(job.name, "", "import", "", msg.severity != ShaderCompilerMessageSeverity.Error, msg.severity.ToString(),
                    msg.message + (string.IsNullOrEmpty(msg.messageDetails) ? "" : " | " + msg.messageDetails), msg.line);
            var data = ShaderUtil.GetShaderData(sh);
            foreach (var pj in job.passes)
            {
                if (pj.subshader >= data.SubshaderCount || pj.pass >= data.GetSubshader(pj.subshader).PassCount)
                {
                    rec(job.name, pj.name, "pass", "", false, "Error", "pass not found in compiled shader data", 0);
                    continue;
                }
                var pass = data.GetSubshader(pj.subshader).GetPass(pj.pass);
                foreach (var set in pj.sets)
                {
                    foreach (var extra in m.extra)
                    {
                        var kw = new List<string>(set.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries));
                        kw.AddRange(extra.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries));
                        var kwText = string.Join(" ", kw);
                        foreach (var st in new[] { ShaderType.Vertex, ShaderType.Fragment })
                        {
                            var r = pass.CompileVariant(st, kw.ToArray(), ShaderCompilerPlatform.Vulkan, BuildTarget.Android);
                            bytes = r.ShaderData != null ? r.ShaderData.Length : 0;
                            bool any = false;
                            foreach (var msg in r.Messages)
                            {
                                any = true;
                                rec(job.name, pj.name, st.ToString(), kwText, r.Success, msg.severity.ToString(),
                                    msg.message + (string.IsNullOrEmpty(msg.messageDetails) ? "" : " | " + msg.messageDetails), msg.line);
                            }
                            if (!any) rec(job.name, pj.name, st.ToString(), kwText, r.Success, r.Success ? "Ok" : "Error", "", 0);
                        }
                    }
                }
            }
        }
        File.WriteAllLines(m.output, lines.ToArray());
        Debug.Log("ShaderCompileCheck wrote " + lines.Count + " records to " + m.output);
    }
}
