// Dumps the light-probe data the ORIGINAL PC game lights dynamic objects with, to compare with the
// port (Unity 6): the ambient settings, RenderSettings.ambientProbe, every baked probe
// (LightmapSettings.lightProbes.bakedProbes) and, for each renderer lit by probes, the SH Unity
// hands it (LightProbes.GetInterpolatedProbe). For each scene listed in BepInEx/probedump/request.txt
// the plugin loads it, samples at 6 s and 15 s (Lighting_Zone triggers change the ambient once the
// player stands in them), writes BepInEx/probedump/<scene>_<t>s.txt, then all_done.txt.
// SH lines are the 27 SphericalHarmonicsL2 coefficients, [rgb][9], as Unity stores them.
// Probe-usage test: for each renderer name listed in BepInEx/probedump/test.txt, renders a sphere with
// that renderer's material twice into a texture, light probes Off and BlendProbes, directional light
// off, and writes <scene>_<name>_<Off|BlendProbes>.png plus the mean colour in <scene>_probetest.txt.
// It shows what the original shader gets as ambient when a renderer does not use probes.
// Compile like tools/lightmap_dump (see its README).
using System.Collections;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

[BepInEx.BepInPlugin("lunacid.port.probedump", "LunaProbeDump", "0.1.0")]
public class LunaProbeDump : BepInEx.BaseUnityPlugin
{
    static string F(float v) { return v.ToString("R", CultureInfo.InvariantCulture); }

    static string Sh(SphericalHarmonicsL2 sh)
    {
        var sb = new StringBuilder();
        for (int c = 0; c < 3; c++)
            for (int k = 0; k < 9; k++)
                sb.Append(c + k == 0 ? "" : " ").Append(F(sh[c, k]));
        return sb.ToString();
    }

    static string Col(Color c) { return F(c.r) + " " + F(c.g) + " " + F(c.b) + " " + F(c.a); }

    IEnumerator Start()
    {
        string dir = Path.Combine(BepInEx.Paths.BepInExRootPath, "probedump");
        string request = Path.Combine(dir, "request.txt");
        if (!File.Exists(request)) yield break;
        var scenes = File.ReadAllLines(request).Select(l => l.Trim()).Where(l => l.Length > 0).ToArray();
        yield return new WaitForSecondsRealtime(20f);

        foreach (string scene in scenes)
        {
            SceneManager.LoadScene(scene);
            yield return null;
            foreach (int t in new[] { 6, 15 })
            {
                yield return new WaitForSecondsRealtime(t == 6 ? 6f : 9f);
                Dump(Path.Combine(dir, scene + "_" + t + "s.txt"), scene);
            }
            string test = Path.Combine(dir, "test.txt");
            if (File.Exists(test))
                yield return ProbeUsageTest(dir, scene, File.ReadAllLines(test).Select(l => l.Trim()).Where(l => l.Length > 0).ToArray());
        }
        File.WriteAllText(Path.Combine(dir, "all_done.txt"), string.Join("\n", scenes) + "\n");
    }

    void Dump(string file, string scene)
    {
        var sb = new StringBuilder();
        sb.AppendLine("scene " + scene);
        sb.AppendLine("unity " + Application.unityVersion + " colorspace " + QualitySettings.activeColorSpace);
        sb.AppendLine("ambientMode " + RenderSettings.ambientMode + " intensity " + F(RenderSettings.ambientIntensity));
        sb.AppendLine("ambientLight " + Col(RenderSettings.ambientLight));
        sb.AppendLine("ambientSky " + Col(RenderSettings.ambientSkyColor));
        sb.AppendLine("ambientEquator " + Col(RenderSettings.ambientEquatorColor));
        sb.AppendLine("ambientGround " + Col(RenderSettings.ambientGroundColor));
        sb.AppendLine("glstate_lightmodel_ambient " + Shader.GetGlobalVector("glstate_lightmodel_ambient").ToString("R"));
        sb.AppendLine("ambientProbe " + Sh(RenderSettings.ambientProbe));

        var lp = LightmapSettings.lightProbes;
        if (lp == null)
            sb.AppendLine("lightProbes none");
        else
        {
            var pos = lp.positions;
            var baked = lp.bakedProbes;
            sb.AppendLine("lightProbes " + lp.count);
            for (int i = 0; i < baked.Length; i++)
                sb.AppendLine("probe " + i + " " + F(pos[i].x) + " " + F(pos[i].y) + " " + F(pos[i].z) + " | " + Sh(baked[i]));
        }

        foreach (var r in FindObjectsOfType<Renderer>())
        {
            if (!r.enabled || !r.gameObject.activeInHierarchy) continue;
            if (r.lightProbeUsage == LightProbeUsage.Off || r.lightmapIndex >= 0 && r.lightmapIndex < 65534) continue;
            SphericalHarmonicsL2 sh;
            LightProbes.GetInterpolatedProbe(r.bounds.center, r, out sh);
            string mats = string.Join(",", r.sharedMaterials.Where(m => m != null)
                .Select(m => m.name + "@" + (m.shader != null ? m.shader.name : "?")).ToArray());
            sb.AppendLine("renderer " + HierPath(r.transform) + " | " + r.GetType().Name + " | " + mats
                + " | center " + F(r.bounds.center.x) + " " + F(r.bounds.center.y) + " " + F(r.bounds.center.z)
                + " | sh " + Sh(sh));
        }
        File.WriteAllText(file, sb.ToString());
        Logger.LogInfo("PROBEDUMP wrote " + file);
    }

    IEnumerator ProbeUsageTest(string dir, string scene, string[] names)
    {
        var log = new StringBuilder();
        var lights = FindObjectsOfType<Light>().Where(l => l.enabled).ToArray();
        foreach (var l in lights) l.enabled = false;
        var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        Destroy(go.GetComponent<Collider>());
        go.transform.position = new Vector3(0, 5000, 0);
        go.layer = 31;
        var mr = go.GetComponent<MeshRenderer>();
        var camGo = new GameObject("probetest_cam");
        var cam = camGo.AddComponent<Camera>();
        cam.transform.position = go.transform.position + new Vector3(0, 0, -2.2f);
        cam.cullingMask = 1 << 31;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Color.black;
        cam.fieldOfView = 30;
        cam.enabled = false;
        var rt = new RenderTexture(128, 128, 24, RenderTextureFormat.ARGB32);
        cam.targetTexture = rt;
        var read = new Texture2D(128, 128, TextureFormat.RGBA32, false);
        foreach (string name in names)
        {
            var src = FindObjectsOfType<Renderer>().FirstOrDefault(r => r.name == name);
            if (src == null) { log.AppendLine(name + " not found"); continue; }
            mr.sharedMaterials = new[] { src.sharedMaterial };
            foreach (var usage in new[] { LightProbeUsage.Off, LightProbeUsage.BlendProbes })
            {
                mr.lightProbeUsage = usage;
                yield return null;
                cam.Render();
                RenderTexture.active = rt;
                read.ReadPixels(new Rect(0, 0, 128, 128), 0, 0);
                read.Apply();
                RenderTexture.active = null;
                var px = read.GetPixels32();
                double r = 0, g = 0, b = 0; int n = 0;
                foreach (var c in px) if (c.r + c.g + c.b > 0) { r += c.r; g += c.g; b += c.b; n++; }
                string tag = name + "_" + usage;
                File.WriteAllBytes(Path.Combine(dir, scene + "_" + tag + ".png"), read.EncodeToPNG());
                log.AppendLine(tag + " material=" + src.sharedMaterial.name + "@" + src.sharedMaterial.shader.name
                    + " pixels=" + n + " mean=" + (n > 0 ? F((float)(r / n)) + " " + F((float)(g / n)) + " " + F((float)(b / n)) : "-")
                    + " ambientLight=" + Col(RenderSettings.ambientLight));
            }
        }
        foreach (var l in lights) l.enabled = true;
        Destroy(go); Destroy(camGo); rt.Release();
        File.WriteAllText(Path.Combine(dir, scene + "_probetest.txt"), log.ToString());
        Logger.LogInfo("PROBEDUMP probe usage test " + scene);
    }

    static string HierPath(Transform t)
    {
        string p = t.name;
        while (t.parent != null) { t = t.parent; p = t.name + "/" + p; }
        return p;
    }
}
