// BepInEx 5 plugin for the ORIGINAL PC game (run under CrossOver/Wine on the Mac).
// Saves reference screenshots from inside the game, so the Quest port can be compared
// frame by frame with the real thing (the Mac terminal cannot capture the screen).
//
// First version: timed captures during the menu/intro plus one capture shortly after
// every scene load. Output: <game>/BepInEx/shots/<seconds>_<scene>_<reason>.png
using System.Collections;
using System.IO;
using BepInEx;
using UnityEngine;
using UnityEngine.SceneManagement;

[BepInPlugin("lunacid.port.lunashot", "LunaShot", "0.1.0")]
public class LunaShot : BaseUnityPlugin
{
    static readonly float[] TimedCaptures = { 15f, 20f, 25f, 30f, 40f, 50f, 60f, 75f, 90f, 120f };

    string outDir;

    void Awake()
    {
        outDir = Path.Combine(Paths.BepInExRootPath, "shots");
        Directory.CreateDirectory(outDir);
        SceneManager.sceneLoaded += (scene, mode) => StartCoroutine(CaptureAfter(3f, "load"));
        StartCoroutine(Timed());
        Logger.LogInfo("LunaShot writing to " + outDir);
    }

    IEnumerator Timed()
    {
        foreach (float t in TimedCaptures)
        {
            while (Time.realtimeSinceStartup < t) yield return null;
            Capture("timed");
        }
    }

    IEnumerator CaptureAfter(float delay, string reason)
    {
        yield return new WaitForSecondsRealtime(delay);
        Capture(reason);
    }

    void Capture(string reason)
    {
        string scene = SceneManager.GetActiveScene().name;
        string file = Path.Combine(outDir, string.Format("{0:000.0}_{1}_{2}.png", Time.realtimeSinceStartup, scene, reason));
        ScreenCapture.CaptureScreenshot(file);
        Logger.LogInfo("shot " + file);
    }

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.F9)) Capture("key");
    }
}
