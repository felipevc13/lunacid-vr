// Renders pairs of shaders (hand-written vs generated) on the same object, with the same synthetic
// textures, lights, fog and lightmap, and writes the pixel difference of each pair plus a PNG with
// both images and the difference. Run by tools/shader_gen/visual_check.py:
//   Unity -batchmode -projectPath P -executeMethod ShaderVisualCheck.Run -job job.json
// Nothing here comes from the game: textures, mesh and lights are made in code.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

public static class ShaderVisualCheck
{
    [Serializable] class Pair { public string name; public string hand; public string gen; }
    [Serializable] class Job { public Pair[] pairs; public string outDir; public int size; public string output; public bool noPointLight; }

    static string Arg(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        return null;
    }

    public static void Run()
    {
        int code = 0;
        try { RunInner(); }
        catch (Exception e) { Debug.LogError("ShaderVisualCheck failed: " + e); code = 1; }
        EditorApplication.Exit(code);
    }

    // ------------------------------------------------------------ synthetic inputs

    static Texture2D MakeTexture(int seed)
    {
        var t = new Texture2D(64, 64, TextureFormat.RGBA32, true);
        var rnd = new System.Random(seed);
        var a = new Color((float)rnd.NextDouble(), (float)rnd.NextDouble(), (float)rnd.NextDouble());
        var b = new Color((float)rnd.NextDouble(), (float)rnd.NextDouble(), (float)rnd.NextDouble());
        for (int y = 0; y < 64; y++)
            for (int x = 0; x < 64; x++)
            {
                bool check = ((x / 8) + (y / 8)) % 2 == 0;
                var c = check ? a : b;
                c = Color.Lerp(c, new Color(x / 63f, y / 63f, 0.5f), 0.35f);
                c.a = Mathf.Clamp01(0.3f + 0.7f * x / 63f);      // alpha ramp: exercises clip (< 0.5 on the left) and blending
                t.SetPixel(x, y, c);
            }
        t.wrapMode = TextureWrapMode.Repeat;
        t.Apply(true);
        return t;
    }

    static Cubemap MakeCube()
    {
        var c = new Cubemap(16, TextureFormat.RGBA32, false);
        var cols = new[] { new Color(0.9f, 0.4f, 0.3f), new Color(0.3f, 0.8f, 0.4f), new Color(0.9f, 0.9f, 0.9f),
                           new Color(0.1f, 0.1f, 0.2f), new Color(0.3f, 0.4f, 0.9f), new Color(0.8f, 0.7f, 0.2f) };
        for (int f = 0; f < 6; f++)
            for (int y = 0; y < 16; y++)
                for (int x = 0; x < 16; x++)
                    c.SetPixel((CubemapFace)f, x, y, Color.Lerp(cols[f], Color.white, y / 30f));
        c.Apply();
        return c;
    }

    static Texture3D MakeTex3D()
    {
        var t = new Texture3D(8, 8, 8, TextureFormat.RGBA32, false);
        var px = new Color[512];
        for (int i = 0; i < 512; i++) px[i] = new Color((i % 8) / 7f, (i / 8 % 8) / 7f, (i / 64) / 7f, 1);
        t.SetPixels(px);
        t.Apply();
        return t;
    }

    static Mesh MakeMesh()
    {
        var tmp = GameObject.CreatePrimitive(PrimitiveType.Sphere);     // radius 0.5
        var m = UnityEngine.Object.Instantiate(tmp.GetComponent<MeshFilter>().sharedMesh);
        UnityEngine.Object.DestroyImmediate(tmp);
        var v = m.vertices;
        var cols = new Color[v.Length];
        for (int i = 0; i < v.Length; i++)
            cols[i] = new Color(v[i].x + 0.5f, v[i].y + 0.5f, v[i].z + 0.5f, 0.5f + v[i].y);
        m.colors = cols;
        m.uv2 = m.uv;
        return m;
    }

    static void SetLightmaps()
    {
        var col = new Texture2D(32, 32, TextureFormat.RGBA32, false, true);
        var dir = new Texture2D(32, 32, TextureFormat.RGBA32, false, true);
        for (int y = 0; y < 32; y++)
            for (int x = 0; x < 32; x++)
            {
                col.SetPixel(x, y, new Color(0.3f + x / 64f, 0.3f + y / 80f, 0.35f, 1));
                dir.SetPixel(x, y, new Color(0.7f, 0.85f, 0.4f, 0.8f));
            }
        col.Apply(); dir.Apply();
        LightmapSettings.lightmapsMode = LightmapsMode.CombinedDirectional;
        LightmapSettings.lightmaps = new[] { new LightmapData { lightmapColor = col, lightmapDir = dir } };
    }

    // ------------------------------------------------------------ material set-up

    static void Fill(Material m, Shader reference, Dictionary<string, Texture> tex2d, Cubemap cube, Texture3D t3d)
    {
        int n = reference.GetPropertyCount();
        for (int i = 0; i < n; i++)
        {
            var name = reference.GetPropertyName(i);
            if (!m.HasProperty(name)) continue;
            switch (reference.GetPropertyType(i))
            {
                case ShaderPropertyType.Color:
                    m.SetColor(name, reference.GetPropertyDefaultVectorValue(i)); break;
                case ShaderPropertyType.Vector:
                    m.SetVector(name, reference.GetPropertyDefaultVectorValue(i)); break;
                case ShaderPropertyType.Float:
                case ShaderPropertyType.Range:
                    m.SetFloat(name, reference.GetPropertyDefaultFloatValue(i)); break;
                case ShaderPropertyType.Texture:
                    var dim = reference.GetPropertyTextureDimension(i);
                    if (dim == TextureDimension.Cube) m.SetTexture(name, cube);
                    else if (dim == TextureDimension.Tex3D) m.SetTexture(name, t3d);
                    else if (dim == TextureDimension.Tex2D) m.SetTexture(name, tex2d[name]);
                    break;
            }
        }
    }

    // ------------------------------------------------------------ main

    static void RunInner()
    {
        var job = JsonUtility.FromJson<Job>(File.ReadAllText(Arg("-job")));
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        Directory.CreateDirectory(job.outDir);
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        var ambient = new Color(0.25f, 0.22f, 0.3f);
        RenderSettings.ambientMode = AmbientMode.Flat;
        RenderSettings.ambientLight = ambient;
        var sh = new SphericalHarmonicsL2();
        sh.AddAmbientLight(ambient);
        RenderSettings.ambientProbe = sh;
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.Linear;
        RenderSettings.fogStartDistance = 2.5f;
        RenderSettings.fogEndDistance = 6f;
        RenderSettings.fogColor = new Color(0.35f, 0.3f, 0.45f);
        SetLightmaps();

        int size = job.size > 0 ? job.size : 256;
        var rt = new RenderTexture(size, size, 24, RenderTextureFormat.ARGB32);
        var camGo = new GameObject("cam");
        var cam = camGo.AddComponent<Camera>();
        cam.transform.position = new Vector3(0, 0, -3.2f);
        cam.fieldOfView = 30;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(0.12f, 0.12f, 0.12f, 1);
        cam.targetTexture = rt;
        cam.enabled = false;

        var sun = new GameObject("sun").AddComponent<Light>();
        sun.type = LightType.Directional;
        sun.transform.rotation = Quaternion.Euler(40, -35, 0);
        sun.color = new Color(1f, 0.93f, 0.8f);
        sun.intensity = 1f;
        sun.shadows = LightShadows.None;
        var lamp = new GameObject("lamp").AddComponent<Light>();
        lamp.type = LightType.Point;
        lamp.transform.position = new Vector3(1.0f, 0.8f, -1.2f);
        lamp.range = 4f;
        lamp.color = new Color(0.4f, 0.6f, 1f);
        lamp.intensity = 2f;
        lamp.renderMode = LightRenderMode.ForcePixel;
        lamp.shadows = LightShadows.None;
        lamp.enabled = !job.noPointLight;

        var go = new GameObject("probe");
        go.AddComponent<MeshFilter>().sharedMesh = MakeMesh();
        var mr = go.AddComponent<MeshRenderer>();
        mr.lightProbeUsage = LightProbeUsage.BlendProbes;
        go.transform.rotation = Quaternion.Euler(15, 30, 0);

        var cube = MakeCube();
        var t3d = MakeTex3D();
        var read = new Texture2D(size, size, TextureFormat.RGBA32, false);
        var lines = new List<string>();

        foreach (var pair in job.pairs)
        {
            var hand = AssetDatabase.LoadAssetAtPath<Shader>(pair.hand);
            var gen = AssetDatabase.LoadAssetAtPath<Shader>(pair.gen);
            if (hand == null || gen == null)
            {
                lines.Add(string.Format("{{\"name\":\"{0}\",\"error\":\"shader did not load\"}}", pair.name));
                continue;
            }
            var tex2d = new Dictionary<string, Texture>();
            for (int i = 0; i < gen.GetPropertyCount(); i++)
                if (gen.GetPropertyType(i) == ShaderPropertyType.Texture)
                    tex2d[gen.GetPropertyName(i)] = MakeTexture(gen.GetPropertyName(i).GetHashCode());
            for (int i = 0; i < hand.GetPropertyCount(); i++)
                if (hand.GetPropertyType(i) == ShaderPropertyType.Texture && !tex2d.ContainsKey(hand.GetPropertyName(i)))
                    tex2d[hand.GetPropertyName(i)] = MakeTexture(hand.GetPropertyName(i).GetHashCode());

            var mHand = new Material(hand);
            var mGen = new Material(gen);
            // Game values first (the generated shader carries the original defaults), then the hand-written
            // shader's own extra properties at its defaults.
            Fill(mHand, hand, tex2d, cube, t3d);
            Fill(mHand, gen, tex2d, cube, t3d);
            Fill(mGen, gen, tex2d, cube, t3d);

            foreach (var mode in new[] { "dynamic", "lightmap" })
            {
                mr.lightmapIndex = mode == "lightmap" ? 0 : -1;
                mr.lightmapScaleOffset = new Vector4(1, 1, 0, 0);
                var px = new Color32[2][];
                var mats = new[] { mHand, mGen };
                for (int k = 0; k < 2; k++)
                {
                    mr.sharedMaterial = mats[k];
                    cam.Render();
                    RenderTexture.active = rt;
                    read.ReadPixels(new Rect(0, 0, size, size), 0, 0);
                    read.Apply();
                    RenderTexture.active = null;
                    px[k] = read.GetPixels32();
                }
                double sum = 0; int over = 0, lit0 = 0, lit1 = 0;
                var bg = (Color32)cam.backgroundColor;
                var sheet = new Texture2D(size * 3, size, TextureFormat.RGBA32, false);
                for (int i = 0; i < px[0].Length; i++)
                {
                    var a = px[0][i]; var b = px[1][i];
                    int d = Math.Max(Math.Abs(a.r - b.r), Math.Max(Math.Abs(a.g - b.g), Math.Abs(a.b - b.b)));
                    sum += (Math.Abs(a.r - b.r) + Math.Abs(a.g - b.g) + Math.Abs(a.b - b.b)) / 3.0;
                    if (d > 8) over++;
                    if (a.r != bg.r || a.g != bg.g || a.b != bg.b) lit0++;
                    if (b.r != bg.r || b.g != bg.g || b.b != bg.b) lit1++;
                    int x = i % size, y = i / size;
                    sheet.SetPixel(x, y, a);
                    sheet.SetPixel(x + size, y, b);
                    byte e = (byte)Math.Min(255, d * 4);
                    sheet.SetPixel(x + 2 * size, y, new Color32(e, e, e, 255));
                }
                sheet.Apply();
                var file = pair.name.Replace("/", "_").Replace(" ", "_") + "_" + mode + ".png";
                File.WriteAllBytes(Path.Combine(job.outDir, file), sheet.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(sheet);
                lines.Add(string.Format(
                    "{{\"name\":\"{0}\",\"mode\":\"{1}\",\"mean_diff\":{2:F3},\"pct_over_8\":{3:F2},\"hand_drawn\":{4},\"gen_drawn\":{5},\"png\":\"{6}\"}}",
                    pair.name, mode, sum / px[0].Length, 100.0 * over / px[0].Length, lit0, lit1, file));
            }
        }
        File.WriteAllLines(job.output, lines.ToArray());
        Debug.Log("ShaderVisualCheck wrote " + lines.Count + " records");
    }
}
