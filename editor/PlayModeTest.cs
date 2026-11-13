using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public class PlayModeTest
{
    public static void RunMainMenuTest()
    {
        RunTestForScene("Assets/Scenes/MainMenu.unity", "MainMenu");
    }

    public static void RunHubTest()
    {
        RunTestForScene("Assets/Scenes/HUB_01.unity", "HUB_01");
    }

    private static void RunTestForScene(string scenePath, string sceneName)
    {
        Debug.Log($"[PlayModeTest] Opening scene {scenePath}...");
        EditorSceneManager.OpenScene(scenePath);

        // Spawn a runtime capture runner in the scene
        GameObject runner = new GameObject("RuntimePlayModeCapturer");
        var capturer = runner.AddComponent<RuntimePlayModeCapturer>();
        capturer.SceneName = sceneName;

        Debug.Log($"[PlayModeTest] Entering PlayMode for {sceneName}...");
        EditorApplication.isPlaying = true;
    }
}

public class RuntimePlayModeCapturer : MonoBehaviour
{
    public string SceneName = "Scene";
    private int frameCount = 0;

    private void Awake()
    {
        DontDestroyOnLoad(gameObject);
    }

    private void Update()
    {
        frameCount++;
        if (frameCount == 100) // ~1.6 seconds in
        {
            CaptureRenderTextureScreenshot(SceneName);
        }
        else if (frameCount >= 140) // ~2.3 seconds
        {
            Debug.Log($"[PlayModeTest] Runtime test for {SceneName} completed successfully.");
#if UNITY_EDITOR
            EditorApplication.isPlaying = false;
            EditorApplication.Exit(0);
#else
            Application.Quit();
#endif
        }
    }

    private void CaptureRenderTextureScreenshot(string sceneName)
    {
        string logsDir = Path.Combine(Application.dataPath, "..", "Logs");
        Directory.CreateDirectory(logsDir);
        string screenshotPath = Path.Combine(logsDir, $"PlayMode_{sceneName}.png");

        // Find and sort all active cameras by depth
        Camera[] cams = UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsSortMode.None);
        List<Camera> activeCams = new List<Camera>();
        foreach (var c in cams)
        {
            if (c.isActiveAndEnabled)
            {
                activeCams.Add(c);
            }
        }
        activeCams.Sort((a, b) => a.depth.CompareTo(b.depth));

        if (activeCams.Count == 0)
        {
            Debug.LogWarning("[PlayModeTest] No camera found in scene to capture screenshot.");
            return;
        }

        int width = 1920;
        int height = 1080;
        RenderTexture rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
        RenderTexture prevActive = RenderTexture.active;

        RenderTexture.active = rt;
        GL.Clear(true, true, Color.black);

        foreach (var c in activeCams)
        {
            RenderTexture prevTarget = c.targetTexture;
            c.targetTexture = rt;
            c.Render();
            c.targetTexture = prevTarget;
        }

        Texture2D screenShot = new Texture2D(width, height, TextureFormat.RGB24, false);
        screenShot.ReadPixels(new Rect(0, 0, width, height), 0, 0);
        screenShot.Apply();

        RenderTexture.active = prevActive;
        UnityEngine.Object.DestroyImmediate(rt);

        byte[] bytes = screenShot.EncodeToPNG();
        UnityEngine.Object.DestroyImmediate(screenShot);

        File.WriteAllBytes(screenshotPath, bytes);
        Debug.Log($"[PlayModeTest] Successfully wrote off-screen RenderTexture screenshot ({bytes.Length} bytes) to: {screenshotPath}");
    }
}
