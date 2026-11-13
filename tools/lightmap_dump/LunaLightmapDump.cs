// Dumps the baked lightmaps of the ORIGINAL PC game, decoded by the GPU, as EXR files.
//
// AssetRipper decodes BC6H lightmaps badly (most of HUB_01's colour map came out black), so the
// port takes them from the running game instead: for each scene listed in
// BepInEx/lmdump/request.txt the plugin loads it, waits, blits every LightmapSettings.lightmaps
// texture (colour, direction, shadow mask) into a linear half-float render texture and writes
// BepInEx/lmdump/<scene>/Lightmap-N_comp_<light|dir|shadowmask>.exr, then all_done.txt.
// The values are exactly what the original shaders sample (no colour-space conversion).
// Compile like tools/tour (see tools/lightmap_dump/README.md).
using System.Collections;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.SceneManagement;

[BepInEx.BepInPlugin("lunacid.port.lightmapdump", "LunaLightmapDump", "0.1.0")]
public class LunaLightmapDump : BepInEx.BaseUnityPlugin
{
    IEnumerator Start()
    {
        string dir = Path.Combine(BepInEx.Paths.BepInExRootPath, "lmdump");
        string request = Path.Combine(dir, "request.txt");
        if (!File.Exists(request)) yield break;
        var scenes = File.ReadAllLines(request).Select(l => l.Trim()).Where(l => l.Length > 0).ToArray();
        yield return new WaitForSecondsRealtime(20f);

        foreach (string scene in scenes)
        {
            SceneManager.LoadScene(scene);
            yield return null;
            yield return new WaitForSecondsRealtime(6f);
            string outDir = Path.Combine(dir, scene);
            Directory.CreateDirectory(outDir);
            var maps = LightmapSettings.lightmaps;
            Logger.LogInfo("LMDUMP " + scene + " lightmaps=" + maps.Length + " mode=" + LightmapSettings.lightmapsMode);
            for (int i = 0; i < maps.Length; i++)
            {
                Save(maps[i].lightmapColor, Path.Combine(outDir, "Lightmap-" + i + "_comp_light.exr"));
                Save(maps[i].lightmapDir, Path.Combine(outDir, "Lightmap-" + i + "_comp_dir.exr"));
                Save(maps[i].shadowMask, Path.Combine(outDir, "Lightmap-" + i + "_comp_shadowmask.exr"));
            }
        }
        File.WriteAllText(Path.Combine(dir, "all_done.txt"), string.Join("\n", scenes) + "\n");
    }

    void Save(Texture2D src, string file)
    {
        if (src == null) return;
        var rt = RenderTexture.GetTemporary(src.width, src.height, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
        Graphics.Blit(src, rt);
        var prev = RenderTexture.active;
        RenderTexture.active = rt;
        var tex = new Texture2D(src.width, src.height, TextureFormat.RGBAHalf, false, true);
        tex.ReadPixels(new Rect(0, 0, src.width, src.height), 0, 0);
        tex.Apply();
        RenderTexture.active = prev;
        File.WriteAllBytes(file, tex.EncodeToEXR(Texture2D.EXRFlags.CompressZIP));
        Destroy(tex);
        RenderTexture.ReleaseTemporary(rt);
        Logger.LogInfo("LMDUMP wrote " + file + " " + src.format + " " + src.width + "x" + src.height);
    }
}
