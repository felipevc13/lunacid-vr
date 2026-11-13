using System;
using System.IO;
using System.Diagnostics;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using UnityEngine.Rendering;

public class ConfigureAndroidAndBuild
{
    // Paths come from the machine configuration (core/config.py sets LUNA_* for the Unity run). Defaults: the
    // Android module Unity Hub installs beside the editor, and Builds/.gradle beside the project folder.
    static string Env(string name, string fallback)
    {
        string v = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrEmpty(v) ? fallback : v;
    }
    static string AndroidPlayer => BuildPipeline.GetPlaybackEngineDirectory(BuildTarget.Android, BuildOptions.None);
    static string ProjectParent => Path.GetDirectoryName(Path.GetDirectoryName(Application.dataPath));
    static string SDK_PATH => Env("LUNA_ANDROID_SDK", Path.Combine(AndroidPlayer, "SDK"));
    static string NDK_PATH => Env("LUNA_ANDROID_NDK", Path.Combine(AndroidPlayer, "NDK"));
    static string JDK_PATH => Env("LUNA_JDK", Path.Combine(AndroidPlayer, "OpenJDK"));
    static string BUILDS => Env("LUNA_BUILDS", Path.Combine(ProjectParent, "Builds"));
    static string APK_OUTPUT => Path.Combine(BUILDS, "Lunacid_Quest.apk");
    static string GRADLE_HOME => Env("LUNA_GRADLE_HOME", Path.Combine(ProjectParent, ".gradle"));
    static string Sep => Path.PathSeparator.ToString();
    static string Exe(string name) => Application.platform == RuntimePlatform.WindowsEditor ? name + ".exe" : name;

    public static void ConfigureSettings()
    {
        UnityEngine.Debug.Log("=== Configuring Android External Tools & PlayerSettings ===");

        // Set stacktrace to ScriptOnly so Quest runtime crashes/exceptions have full C# stacktraces
        Application.SetStackTraceLogType(LogType.Warning, StackTraceLogType.ScriptOnly);
        Application.SetStackTraceLogType(LogType.Log, StackTraceLogType.ScriptOnly);
        Application.SetStackTraceLogType(LogType.Error, StackTraceLogType.ScriptOnly);
        Application.SetStackTraceLogType(LogType.Exception, StackTraceLogType.ScriptOnly);
        Application.SetStackTraceLogType(LogType.Assert, StackTraceLogType.ScriptOnly);

        PlayerSettings.SetStackTraceLogType(LogType.Warning, StackTraceLogType.ScriptOnly);
        PlayerSettings.SetStackTraceLogType(LogType.Log, StackTraceLogType.ScriptOnly);
        PlayerSettings.SetStackTraceLogType(LogType.Error, StackTraceLogType.ScriptOnly);
        PlayerSettings.SetStackTraceLogType(LogType.Exception, StackTraceLogType.ScriptOnly);
        PlayerSettings.SetStackTraceLogType(LogType.Assert, StackTraceLogType.ScriptOnly);

        // Configure External Tools paths
        EditorPrefs.SetString("AndroidSdkRoot", SDK_PATH);
        EditorPrefs.SetString("AndroidNdkRoot", NDK_PATH);
        EditorPrefs.SetString("AndroidNdkRootR27c", NDK_PATH);
        EditorPrefs.SetString("JdkPath", JDK_PATH);

        // Export environment variables for child processes (Gradle, IL2CPP, d8, aapt2)
        Environment.SetEnvironmentVariable("JAVA_HOME", JDK_PATH);
        Environment.SetEnvironmentVariable("ANDROID_HOME", SDK_PATH);
        Environment.SetEnvironmentVariable("ANDROID_SDK_ROOT", SDK_PATH);
        Environment.SetEnvironmentVariable("ANDROID_NDK_ROOT", NDK_PATH);
        Environment.SetEnvironmentVariable("GRADLE_USER_HOME", GRADLE_HOME);
        string currentPath = Environment.GetEnvironmentVariable("PATH") ?? "";
        Environment.SetEnvironmentVariable("PATH", $"{Path.Combine(JDK_PATH, "bin")}{Sep}{Path.Combine(SDK_PATH, "platform-tools")}{Sep}{Path.Combine(SDK_PATH, "build-tools", "36.0.0")}{Sep}{currentPath}");

#if UNITY_ANDROID
        try
        {
            UnityEditor.Android.AndroidExternalToolsSettings.sdkRootPath = SDK_PATH;
            UnityEditor.Android.AndroidExternalToolsSettings.ndkRootPath = NDK_PATH;
            UnityEditor.Android.AndroidExternalToolsSettings.jdkRootPath = JDK_PATH;
            UnityEngine.Debug.Log($"[AndroidSettings] Configured AndroidExternalToolsSettings: SDK={UnityEditor.Android.AndroidExternalToolsSettings.sdkRootPath}, NDK={UnityEditor.Android.AndroidExternalToolsSettings.ndkRootPath}, JDK={UnityEditor.Android.AndroidExternalToolsSettings.jdkRootPath}");
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogWarning($"[AndroidSettings] AndroidExternalToolsSettings reflection/access note: {ex.Message}");
        }
#endif

        // Verify tools exist on disk
        bool sdkOk = Directory.Exists(Path.Combine(SDK_PATH, "platform-tools")) && Directory.Exists(Path.Combine(SDK_PATH, "build-tools"));
        bool ndkOk = File.Exists(Path.Combine(NDK_PATH, "source.properties"));
        bool jdkOk = File.Exists(Path.Combine(JDK_PATH, "bin", Exe("java")));

        UnityEngine.Debug.Log($"[AndroidSettings] Toolchain verification: SDK: {sdkOk} ({SDK_PATH}), NDK: {ndkOk} ({NDK_PATH}), JDK: {jdkOk} ({JDK_PATH})");

        if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.Android)
        {
            UnityEngine.Debug.Log("[AndroidSettings] Switching active build target to Android...");
            EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Android, BuildTarget.Android);
        }

        // PlayerSettings for Quest / Android
        PlayerSettings.companyName = "AkumaKira";
        PlayerSettings.productName = "Lunacid";
        PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, "com.AkumaKira.LunacidVR");
        PlayerSettings.bundleVersion = "1.0.0";
        PlayerSettings.Android.bundleVersionCode = 1;
        // LUNA_SPLIT_OBB=1: scenes and assets go to Lunacid_Quest.main.obb beside a small APK, so a
        // scripts-only build repacks only the code (Gradle took 26 of 50 minutes packing the 716 MB APK).
        // tools/tour/quest_tour.sh pushes the OBB to /sdcard/Android/obb/<package>/ when it changed.
        PlayerSettings.Android.splitApplicationBinary = System.Environment.GetEnvironmentVariable("LUNA_SPLIT_OBB") == "1";

        // Signing: the machine's own key from tools/build/keystore.py (<work>/keystore, never in the repository).
        // An APK signed by another key cannot replace the installed app without an uninstall, which deletes the
        // saves; build.py checks the signature after the build (LESSONS 36). Without LUNA_KEYSTORE, Unity's debug key.
        string keystore = Environment.GetEnvironmentVariable("LUNA_KEYSTORE");
        PlayerSettings.Android.useCustomKeystore = !string.IsNullOrEmpty(keystore);
        if (PlayerSettings.Android.useCustomKeystore)
        {
            PlayerSettings.Android.keystoreName = keystore;
            PlayerSettings.Android.keystorePass = Environment.GetEnvironmentVariable("LUNA_KEYSTORE_PASS");
            PlayerSettings.Android.keyaliasName = Environment.GetEnvironmentVariable("LUNA_KEYALIAS");
            PlayerSettings.Android.keyaliasPass = Environment.GetEnvironmentVariable("LUNA_KEYALIAS_PASS");
            UnityEngine.Debug.Log("[AndroidSettings] signing with " + keystore + " (alias " + PlayerSettings.Android.keyaliasName + ")");
        }

        // Architecture & Scripting Backend
        PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        PlayerSettings.SetManagedStrippingLevel(NamedBuildTarget.Android, ManagedStrippingLevel.Minimal);

        // Color Space: Lunacid was authored for Gamma color space
        PlayerSettings.colorSpace = ColorSpace.Gamma;

        // SDK versions
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel29; // Android 10
        PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevel34; // Android 14

        // Graphics APIs: Vulkan first, OpenGLES3 fallback
        PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.Android, false);
        PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, new[] {
            GraphicsDeviceType.Vulkan,
            GraphicsDeviceType.OpenGLES3
        });

        // VR: OpenXR with Meta Quest support, single-pass instanced (multiview) rendering.
        PlayerSettings.stereoRenderingPath = StereoRenderingPath.Instancing;
        LunaXRSetup.Configure();

        UnityEngine.Debug.Log($"[AndroidSettings] PlayerSettings configured: Identifier={PlayerSettings.GetApplicationIdentifier(NamedBuildTarget.Android)}, Backend={PlayerSettings.GetScriptingBackend(NamedBuildTarget.Android)}, Arch={PlayerSettings.Android.targetArchitectures}, MinSDK={PlayerSettings.Android.minSdkVersion}, TargetSDK={PlayerSettings.Android.targetSdkVersion}");

        // Automatically update shader collection and AlwaysIncludedShaders.
        // LUNA_SKIP_SVC=1 skips it (Build 1-like GraphicsSettings, used to bisect the black MainMenu regression).
        if (Environment.GetEnvironmentVariable("LUNA_SKIP_SVC") == "1")
        {
            UnityEngine.Debug.Log("[AndroidSettings] LUNA_SKIP_SVC=1: skipping ShaderVariantCollection/AlwaysIncludedShaders registration.");
        }
        else
        {
            try
            {
                ShaderVariantCollectionBuilder.CollectAndRegisterAllShaders();
            }
            catch (Exception ex)
            {
                UnityEngine.Debug.LogWarning($"[AndroidSettings] ShaderVariantCollection note: {ex.Message}");
            }
        }
    }

    public static void CheckDiskSpace()
    {
        UnityEngine.Debug.Log("=== Checking Storage Space ===");
        DriveInfo[] allDrives = DriveInfo.GetDrives();
        foreach (DriveInfo d in allDrives)
        {
            if (d.IsReady)
            {
                double freeGb = d.AvailableFreeSpace / (1024.0 * 1024.0 * 1024.0);
                double totalGb = d.TotalSize / (1024.0 * 1024.0 * 1024.0);
                UnityEngine.Debug.Log($"Drive {d.Name} ({d.DriveType}): Free {freeGb:F2} GB / Total {totalGb:F2} GB");
            }
        }
    }

    public static void BuildMainMenuOnly()
    {
        // LUNA_EXTRA_SCENES="HUB_01,LAKE" adds scenes for the comparison tour (tools/tour).
        var scenes = new System.Collections.Generic.List<string> { "Assets/Scenes/MainMenu.unity" };
        string extra = System.Environment.GetEnvironmentVariable("LUNA_EXTRA_SCENES");
        if (!string.IsNullOrEmpty(extra))
            foreach (var name in extra.Split(','))
                if (name.Trim().Length > 0) scenes.Add("Assets/Scenes/" + name.Trim() + ".unity");
        BuildScenesInternal(scenes.ToArray());
    }

    public static void BuildQuestAPK()
    {
        // Get enabled scenes from EditorBuildSettings (all 30 scenes in order)
        var scenes = EditorBuildSettings.scenes;
        var scenePaths = new System.Collections.Generic.List<string>();
        for (int i = 0; i < scenes.Length; i++)
        {
            if (scenes[i].enabled)
            {
                scenePaths.Add(scenes[i].path);
            }
        }
        BuildScenesInternal(scenePaths.ToArray());
    }

    private static void BuildScenesInternal(string[] scenePaths)
    {
        ConfigureSettings();
        CheckDiskSpace();

        UnityEngine.Debug.Log($"=== Starting Lunacid Standalone Quest APK Build ({scenePaths.Length} scene(s)) ===");
        for (int i = 0; i < scenePaths.Length; i++)
        {
            UnityEngine.Debug.Log($"  [Scene {i + 1:D2}/{scenePaths.Length:D2}] {scenePaths[i]}");
        }

        string buildDir = Path.GetDirectoryName(APK_OUTPUT);
        if (!Directory.Exists(buildDir))
        {
            Directory.CreateDirectory(buildDir);
        }

        // LUNA_SCRIPTS_ONLY=1: rebuild only the code and reuse the scenes and assets of the last full
        // build (same scene list and settings), for runtime-only changes.
        var options = BuildOptions.None;
        if (System.Environment.GetEnvironmentVariable("LUNA_SCRIPTS_ONLY") == "1")
        {
            options |= BuildOptions.BuildScriptsOnly;
            UnityEngine.Debug.Log("[Build] Scripts-only build: reusing the last build's scenes and assets");
        }
        BuildPlayerOptions buildPlayerOptions = new BuildPlayerOptions
        {
            scenes = scenePaths,
            locationPathName = APK_OUTPUT,
            target = BuildTarget.Android,
            targetGroup = BuildTargetGroup.Android,
            options = options
        };

        Stopwatch sw = Stopwatch.StartNew();
        BuildReport report = null;
        try
        {
            report = BuildPipeline.BuildPlayer(buildPlayerOptions);
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogWarning($"[Build] BuildPipeline exception (checking Gradle fallback): {ex.Message}");
        }
        sw.Stop();

        if (report != null)
        {
            BuildSummary summary = report.summary;
            UnityEngine.Debug.Log($"=== Build Finished with Result: {summary.result} in {sw.Elapsed.TotalMinutes:F2} minutes ({sw.Elapsed.TotalSeconds:F0} seconds) ===");
            UnityEngine.Debug.Log($"Total Errors: {summary.totalErrors}, Warnings: {summary.totalWarnings}");
            UnityEngine.Debug.Log($"Total Output Size: {summary.totalSize / (1024.0 * 1024.0):F2} MB");

            if (summary.result != BuildResult.Succeeded)
            {
                UnityEngine.Debug.LogError($"[Build] FAILURE: Unity BuildPlayer did not succeed. Result: {summary.result}");
                CheckDiskSpace();
                EditorApplication.Exit(1);
                return;
            }
        }

        // Automatic Gradle fallback if APK was not generated directly due to AAPT2 daemon startup issues in batchmode
        if (!File.Exists(APK_OUTPUT))
        {
            string gradlePrjDir = Path.Combine(Directory.GetCurrentDirectory(), "Library", "Bee", "Android", "Prj", "IL2CPP", "Gradle");
            if (Directory.Exists(gradlePrjDir))
            {
                UnityEngine.Debug.LogWarning($"[Build] APK not generated directly. Triggering standalone Gradle assembly in {gradlePrjDir}...");
                bool gradleSuccess = RunStandaloneGradle(gradlePrjDir);
                if (gradleSuccess)
                {
                    string builtApk = Path.Combine(gradlePrjDir, "launcher", "build", "outputs", "apk", "release", "launcher-release.apk");
                    if (File.Exists(builtApk))
                    {
                        File.Copy(builtApk, APK_OUTPUT, true);
                        UnityEngine.Debug.Log($"[Build] Successfully assembled and copied APK from Gradle: {APK_OUTPUT}");
                    }
                }
            }
        }

        if (File.Exists(APK_OUTPUT))
        {
            FileInfo fi = new FileInfo(APK_OUTPUT);
            UnityEngine.Debug.Log($"[Build] SUCCESS! APK generated at: {APK_OUTPUT} ({fi.Length / (1024.0 * 1024.0):F2} MB)");
            CheckDiskSpace();
            EditorApplication.Exit(0);
        }
        else
        {
            UnityEngine.Debug.LogError($"[Build] FAILURE: APK was not found at {APK_OUTPUT}");
            CheckDiskSpace();
            EditorApplication.Exit(1);
        }
    }

    private static bool RunStandaloneGradle(string gradleDir)
    {
        UnityEngine.Debug.Log($"=== Running Standalone Gradle in {gradleDir} ===");
        try
        {
            string javaExe = Path.Combine(JDK_PATH, "bin", Exe("java"));
            string gradleLib = Path.Combine(AndroidPlayer, "Tools", "gradle", "lib");
            string[] jars = Directory.Exists(gradleLib) ? Directory.GetFiles(gradleLib, "gradle-launcher-*.jar") : new string[0];
            if (jars.Length == 0) { UnityEngine.Debug.LogError($"[Gradle] no gradle-launcher jar in {gradleLib}"); return false; }
            string gradleJar = jars[0];
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = javaExe,
                Arguments = $"-classpath \"{gradleJar}\" org.gradle.launcher.GradleMain \"-Dorg.gradle.jvmargs=-Xmx4096m\" assembleRelease --stacktrace",
                WorkingDirectory = gradleDir,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            psi.EnvironmentVariables["JAVA_HOME"] = JDK_PATH;
            psi.EnvironmentVariables["ANDROID_HOME"] = SDK_PATH;
            psi.EnvironmentVariables["ANDROID_SDK_ROOT"] = SDK_PATH;
            psi.EnvironmentVariables["ANDROID_NDK_ROOT"] = NDK_PATH;
            psi.EnvironmentVariables["GRADLE_USER_HOME"] = GRADLE_HOME;
            string currentPath = Environment.GetEnvironmentVariable("PATH") ?? "";
            psi.EnvironmentVariables["PATH"] = $"{Path.Combine(JDK_PATH, "bin")}{Sep}{Path.Combine(SDK_PATH, "platform-tools")}{Sep}{currentPath}";

            using (Process proc = Process.Start(psi))
            {
                proc.OutputDataReceived += (s, e) => {
                    if (!string.IsNullOrEmpty(e.Data)) UnityEngine.Debug.Log($"[Gradle] {e.Data}");
                };
                proc.ErrorDataReceived += (s, e) => {
                    if (!string.IsNullOrEmpty(e.Data)) UnityEngine.Debug.LogError($"[Gradle] {e.Data}");
                };
                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
                proc.WaitForExit();
                UnityEngine.Debug.Log($"[Gradle] Process exited with code {proc.ExitCode}");
                return proc.ExitCode == 0;
            }
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError($"[Gradle] Failed to start standalone gradle: {ex.Message}");
            return false;
        }
    }

    public static void BuildStandaloneMac()
    {
        string macOutput = Path.Combine(BUILDS, "Lunacid_Mac.app");
        string[] scenePaths = new string[] { "Assets/Scenes/MainMenu.unity" };
        UnityEngine.Debug.Log("=== Starting Lunacid Standalone macOS Build (MainMenu only) ===");

        BuildPlayerOptions buildPlayerOptions = new BuildPlayerOptions
        {
            scenes = scenePaths,
            locationPathName = macOutput,
            target = BuildTarget.StandaloneOSX,
            targetGroup = BuildTargetGroup.Standalone,
            options = BuildOptions.None
        };
        BuildReport report = BuildPipeline.BuildPlayer(buildPlayerOptions);
        UnityEngine.Debug.Log($"=== macOS Build Finished: {report.summary.result} ===");
        EditorApplication.Exit(report.summary.result == BuildResult.Succeeded ? 0 : 1);
    }
}
