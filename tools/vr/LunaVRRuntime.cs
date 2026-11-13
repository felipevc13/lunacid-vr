// Port runtime for the Quest: holds the headset at 72 Hz and keeps the GPU cost down.
// Copied into Assets/Scripts/LunaPort/ by passes/pass_vr_runtime.py.
//   - frame-paces the game to the headset's 72 Hz (Quest apps start at 72 Hz; going to 90 Hz needs the
//     Meta OpenXR package's display utilities);
//   - turns on fixed foveated rendering (sharp centre, cheaper edges), the biggest GPU saving on Quest;
//   - logs frames that miss the 13.9 ms budget so stutters can be found per scene (LUNA_PERF);
//   - eye-level tracking origin;
//   - theater mode for the scenes that are not gameplay (menu, character creation, endings): the
//     game renders as usual into a texture shown on a fixed screen in a dark room, so the head moves
//     freely and the game's own camera animation cannot drag the view (LunaTheater);
//   - a controller laser pointer that drives the game's mouse-based UI on that screen and on the HUD panel
//     while a game menu is open (LunaVRPointer);
//   - in gameplay scenes: the Touch controllers as a virtual gamepad, snap turn on the right stick and
//     the HUD on a panel that lazily follows the head (LunaVRGameplay).
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.SceneManagement;
using UnityEngine.XR;
using CommonUsages = UnityEngine.XR.CommonUsages;
using InputDevice = UnityEngine.XR.InputDevice;

public class LunaVRRuntime : MonoBehaviour
{
    const float RefreshRate = 72f;
    const float FoveationLevel = 1f;   // 0 off .. 1 strongest

    // Scenes shown on the theater screen instead of around the player.
    static readonly string[] TheaterScenes = { "MainMenu", "CHAR_CREATE", "Gameover", "END_A", "END_B", "END_E",
                                               "END_EVID", "END_TOWN", "WhatWillBeAtTheEnd" };

    float slowSince, worst;
    int frames, slow;
    LunaTheater theater;
    LunaVRGameplay gameplay;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Boot()
    {
        var go = new GameObject("LunaVRRuntime");
        DontDestroyOnLoad(go);
        go.AddComponent<LunaVRRuntime>();
    }

    void Start()
    {
        QualitySettings.vSyncCount = 0;
        Application.targetFrameRate = (int)RefreshRate;
        var displays = new List<XRDisplaySubsystem>();
        SubsystemManager.GetSubsystems(displays);
        var inputs = new List<XRInputSubsystem>();
        SubsystemManager.GetSubsystems(inputs);
        foreach (var i in inputs)
        {
            bool ok = i.TrySetTrackingOriginMode(TrackingOriginModeFlags.Device);
            Debug.Log("LUNA_INPUT tracking origin Device " + (ok ? "set" : "refused") + ", now " + i.GetTrackingOriginMode() + " (supported " + i.GetSupportedTrackingOriginModes() + ")");
        }

        theater = LunaTheater.Create(transform);
        gameplay = gameObject.AddComponent<LunaVRGameplay>();
        SceneManager.activeSceneChanged += (a, b) => OnScene(b);
        OnScene(SceneManager.GetActiveScene());
    }

    // The display only accepts foveation once it is running.
    void ApplyFoveation()
    {
        var displays = new List<XRDisplaySubsystem>();
        SubsystemManager.GetSubsystems(displays);
        foreach (var d in displays)
        {
            if (!d.running) continue;
            d.foveatedRenderingFlags = XRDisplaySubsystem.FoveatedRenderingFlags.None;
            d.foveatedRenderingLevel = FoveationLevel;
            foveated = true;
            Debug.Log("LUNA_PERF foveation=" + d.foveatedRenderingLevel);
        }
    }

    void OnScene(Scene s)
    {
        bool on = TheaterScenes.Contains(s.name);
        theater.SetActive(on);
        gameplay.enabled = !on;
        Debug.Log("LUNA_PERF scene " + s.name + " theater=" + on);
        theater.RememberFieldsOfView();
        StartCoroutine(HoldSpawnInterpolation());
    }

    // The player's Rigidbody interpolates, and in Unity 6 an interpolated body writes its own pose to the
    // transform each frame. Player_Control_scr.OnEnable teleports through the transform (save position), so
    // the body wrote the scene's default position back and the game's own interpolation lerped between the
    // two: the probe got 4 of 16 loads at the save, 4 at the scene default (the crystal) and 8 on the line
    // between them, which can be outside the level (Felipe: new game at the crystal; falling off the map).
    // OnScene runs before CONTROL.Start, so interpolation is off when the teleport happens and comes back
    // once physics has taken the new position. RideMovingParent is the same Unity 6 behaviour.
    const int SpawnSettleSteps = 5;
    static readonly System.Type SpawnPlayerType = System.Type.GetType("Player_Control_scr, Assembly-CSharp");

    // Switched off, not destroyed: Elevator_Control calls its ResetTransforms without a null check. Called
    // again once a second, because the new-game opening's FIX_INTER (FixOPInter) adds a fresh one to the
    // player when the hand scene ends.
    public static void SwitchOffPlayerInterpolation(Component player)
    {
        if (player.GetComponent("InterpolationObjectController") is MonoBehaviour interpolator && interpolator.enabled)
        {
            interpolator.StopAllCoroutines();
            interpolator.enabled = false;
            Debug.Log("LUNA_VR player interpolation switched off");
        }
        // Head_Bob sits on CAM, the head-tracked camera, and in FixedUpdate pulls it back towards the body,
        // rolls it on turns and bobs it. A spell is pushed in its Start (Item_Emit), after FixedUpdate and before
        // any Update, from the camera's pose then: the pull, not the head, set its direction, and it landed to
        // the side of the aim mark (Felipe, Builds 88-89; LESSONS 27). The headset owns this camera; view bob
        // and screen shake are hidden in the settings already.
        if (HeadBobType == null) return;
        foreach (var bob in player.GetComponentsInChildren(HeadBobType, true))
            if (bob is MonoBehaviour b && b.enabled)
            {
                b.enabled = false;
                Debug.Log("LUNA_VR Head_Bob switched off on " + b.name);
            }
    }
    static readonly System.Type HeadBobType = System.Type.GetType("Head_Bob, Assembly-CSharp");

    IEnumerator HoldSpawnInterpolation()
    {
        var player = SpawnPlayerType != null ? FindObjectOfType(SpawnPlayerType, true) as Component : null;
        var body = player != null ? player.GetComponent<Rigidbody>() : null;
        if (body == null) yield break;
        // The game's own interpolation on the player's transform fights the physics step in Unity 6: the
        // body reports 2.90 m/s and moves 1.7, with the port's code off as well. Removing the component
        // gives 2.90 m/s; the body's own interpolation keeps the view smooth (Felipe: walk and run slow).
        SwitchOffPlayerInterpolation(player);
        var was = body.interpolation;
        body.interpolation = RigidbodyInterpolation.None;
        yield return null; // CONTROL.Start, then the teleport
        for (int i = 0; i < SpawnSettleSteps; i++) yield return new WaitForFixedUpdate();
        if (body != null) body.interpolation = was;
    }

    bool foveated;

    // Intro skip hold (skip_con, patched by pass_vr_intro_skip): the right trigger (with the trigger's
    // hysteresis), or a keyboard key. Legacy joystick buttons are left out: the Quest reports one held
    // from boot (JoystickButton16 or 5), which skipped the intro by itself. The grip is left out too:
    // holding the controller squeezes it, which started the skip unasked.
    static bool skipWas;
    static float skipSince;

    public static bool SkipHeld()
    {
        bool held = LunaTrigger.Held(InputDevices.GetDeviceAtXRNode(XRNode.RightHand))
                    || (Keyboard.current != null && Keyboard.current.anyKey.isPressed);
        if (held != skipWas)
        {
            skipWas = held;
            if (held) skipSince = Time.unscaledTime;
            else Debug.Log("LUNA_INPUT intro skip held for " + (Time.unscaledTime - skipSince).ToString("F2") + " s");
        }
        return held;
    }

    // The intro's skip (skip_con) fires after Input.anyKey has been held for 2.5 s and it skips with the
    // controllers untouched: log which legacy key reads as held, and for how long.
    bool anyKey;
    float anyKeySince;

    void LogAnyKey()
    {
        if (Input.anyKey == anyKey) return;
        anyKey = Input.anyKey;
        if (anyKey)
        {
            anyKeySince = Time.realtimeSinceStartup;
            var held = System.Enum.GetValues(typeof(KeyCode)).Cast<KeyCode>().Where(Input.GetKey).Distinct();
            Debug.Log("LUNA_INPUT anyKey down: " + string.Join(",", held) + " scene=" + SceneManager.GetActiveScene().name);
        }
        else
            Debug.Log("LUNA_INPUT anyKey up after " + (Time.realtimeSinceStartup - anyKeySince).ToString("F2") + " s");
    }

    // Solid magenta squares (Unity's error shader) showed on menus and in the view. Every 10 s, objects
    // not seen before are checked: UI images whose shader the headset cannot run go back to the default
    // UI material, other renderers (particles, meshes) are hidden; each one is logged with its path.
    const float SweepInterval = 10f;
    float nextSweep;
    readonly HashSet<int> swept = new HashSet<int>();

    static string PathOf(Transform t)
    {
        var path = t.name;
        for (var p = t.parent; p != null; p = p.parent) path = p.name + "/" + path;
        return path;
    }

    static bool Broken(Material m) => m != null && (m.shader == null || !m.shader.isSupported || m.shader.name == "Hidden/InternalErrorShader");

    void SweepBrokenShaders()
    {
        foreach (var g in FindObjectsByType<UnityEngine.UI.Graphic>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (!swept.Add(g.GetInstanceID())) continue;
            var m = g.material;
            if (m == g.defaultMaterial || !Broken(m)) continue;
            g.material = null;
            Debug.Log("LUNA_PERF broken shader on UI " + PathOf(g.transform) + " (" + m.name + ", " + (m.shader != null ? m.shader.name : "none") + "): default UI material");
        }
        foreach (var r in FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (!swept.Add(r.GetInstanceID())) continue;
            foreach (var m in r.sharedMaterials)
            {
                if (!Broken(m)) continue;
                r.enabled = false;
                Debug.Log("LUNA_PERF broken shader on " + r.GetType().Name + " " + PathOf(r.transform) + " (" + m.name + ", " + (m.shader != null ? m.shader.name : "none") + "): hidden");
                break;
            }
        }
    }

    void Update()
    {
        if (Time.unscaledTime >= nextSweep) { nextSweep = Time.unscaledTime + SweepInterval; SweepBrokenShaders(); }
        LogAnyKey();
        if (!foveated) ApplyFoveation();
        // A frame over 1.5x the budget is a visible hitch in the headset.
        float dt = Time.unscaledDeltaTime;
        frames++;
        if (dt > 1.5f / RefreshRate) slow++;
        if (dt > worst) worst = dt;
        if (Time.realtimeSinceStartup - slowSince > 10f)
        {
            Debug.Log("LUNA_PERF " + SceneManager.GetActiveScene().name + " fps=" + (frames / (Time.realtimeSinceStartup - slowSince)).ToString("F1")
                      + " hitches=" + slow + " worst_ms=" + (worst * 1000f).ToString("F1"));
            slowSince = Time.realtimeSinceStartup;
            frames = 0; slow = 0; worst = 0f;
        }
    }

    // The gameplay component is off in theater scenes, but the main menu has a settings page too.
    void LateUpdate()
    {
        if (gameplay != null && !gameplay.enabled) gameplay.SettingsPageWhileOff();
    }
}

// A dark room far below the level with a fixed screen. While active, every game camera renders into
// the screen's texture (mono, its own projection) and the headset sees only the room.
public class LunaTheater : MonoBehaviour
{
    public const int Layer = 31;                 // unused by the game
    const int Width = 1600, Height = 900;
    const float Distance = 3f, ScreenWidth = 3.2f;
    static readonly Vector3 RoomPosition = new Vector3(0f, -5000f, 0f);

    public RenderTexture Texture { get; private set; }
    public Camera Eye { get; private set; }
    Camera overlay;                              // draws the converted overlay canvases, after every game camera
    public Transform Screen { get; private set; }
    public Camera GameCamera { get; private set; }   // the camera whose pixels map to the screen (UI raycasts)
    bool active;
    LunaVRPointer pointer;

    public static LunaTheater Create(Transform parent)
    {
        var root = new GameObject("LunaTheater");
        root.transform.SetParent(parent, false);
        root.transform.position = RoomPosition;
        var t = root.AddComponent<LunaTheater>();
        t.Build();
        return t;
    }

    void Build()
    {
        Texture = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
        Texture.name = "LunaTheaterScreen";

        var eyeGo = new GameObject("TheaterEye");
        eyeGo.transform.SetParent(transform, false);
        Eye = eyeGo.AddComponent<Camera>();
        eyeGo.AddComponent<LunaHeadTracker>();
        Eye.cullingMask = 1 << Layer;
        Eye.clearFlags = CameraClearFlags.SolidColor;
        Eye.backgroundColor = new Color(0.02f, 0.02f, 0.025f);
        Eye.nearClipPlane = 0.05f;
        Eye.farClipPlane = 50f;
        Eye.depth = 100f;
        Eye.stereoTargetEye = StereoTargetEyeMask.Both;

        // A ScreenSpaceOverlay canvas draws over the finished picture, and XR never shows one. Converted to a
        // game camera it draws inside that camera's frame, where the intro never showed it (SKIP_CAN, with the
        // text active, on screen and with a valid mesh). This camera keeps the overlay's meaning: it runs
        // after every game camera and draws only the converted canvases, whichever camera the scene uses now.
        var overlayGo = new GameObject("TheaterOverlay");
        overlayGo.transform.SetParent(transform, false);
        overlay = overlayGo.AddComponent<Camera>();
        overlay.clearFlags = CameraClearFlags.Depth;
        overlay.cullingMask = ~(1 << Layer);
        overlay.nearClipPlane = 0.05f;
        overlay.farClipPlane = 10f;
        overlay.depth = Eye.depth - 1f;
        overlay.targetTexture = Texture;
        overlay.stereoTargetEye = StereoTargetEyeMask.None;
        overlay.aspect = (float)Width / Height;

        var quad = GameObject.CreatePrimitive(PrimitiveType.Quad);
        Destroy(quad.GetComponent<Collider>());
        quad.name = "TheaterScreen";
        quad.layer = Layer;
        quad.transform.SetParent(transform, false);
        quad.transform.localPosition = new Vector3(0f, 0f, Distance);
        quad.transform.localScale = new Vector3(ScreenWidth, ScreenWidth * Height / Width, 1f);
        var mat = new Material(Shader.Find("Unlit/Texture"));
        mat.mainTexture = Texture;
        quad.GetComponent<MeshRenderer>().sharedMaterial = mat;
        Screen = quad.transform;

        pointer = gameObject.AddComponent<LunaVRPointer>();
        pointer.Origin = transform;   // the theater room is the tracking origin
        pointer.Layer = Layer;
        pointer.RayToPixel = RayToPixel;
        SetActive(false);
    }

    public void SetActive(bool on)
    {
        active = on;
        Eye.enabled = on;
        overlay.enabled = on;
        Screen.gameObject.SetActive(on);
        pointer.enabled = on && SomethingToClick();
        nextClickCheck = 0f;
        if (!on) ReleaseGameCameras();
    }

    // The laser only while the screen has something to click: the new-game intro and the endings are cut scenes, and
    // the laser kept showing and vanishing over them (Felipe, Build 91 video; LESSONS 28). Selectable.allSelectablesArray
    // holds the active, enabled ones (buttons, sliders, toggles, dropdowns, the name field).
    float nextClickCheck;
    static bool SomethingToClick()
    {
        foreach (var sel in UnityEngine.UI.Selectable.allSelectablesArray)
            if (sel != null && sel.IsInteractable()) return true;
        return false;
    }

    void UpdateLaser()
    {
        if (Time.unscaledTime < nextClickCheck) return;
        nextClickCheck = Time.unscaledTime + 0.2f;
        bool want = SomethingToClick();
        if (pointer.enabled == want) return;
        pointer.enabled = want;
        Debug.Log("LUNA_PERF theater laser " + (want ? "shown" : "hidden: nothing to click"));
    }

    void LateUpdate()
    {
        if (!active) return;
        UpdateLaser();
        // Cameras and canvases appear as the scene runs: keep routing them into the screen texture.
        Camera top = null;
        foreach (var c in Camera.allCameras)
        {
            if (c == Eye || c == overlay || (c.targetTexture != null && c.targetTexture != Texture)) continue;
            if (c.targetTexture == null) RestoreFieldOfView(c);
            c.targetTexture = Texture;
            c.stereoTargetEye = StereoTargetEyeMask.None;
            c.aspect = (float)Width / Height;
            if (top == null || c.depth > top.depth) top = c;
        }
        HoldFieldsOfView();
        if (top == null) return;
        if (top != GameCamera)
            Debug.Log("LUNA_PERF theater draws through " + top.name + " depth=" + top.depth + " clear=" + top.clearFlags
                      + " mask=" + top.cullingMask + " cameras=" + string.Join(",", Camera.allCameras.Where(c => c != Eye && c != overlay).Select(c => c.name + "@" + c.depth)));
        GameCamera = top;
        foreach (var canvas in FindObjectsOfType<Canvas>())
        {
            if (!canvas.isRootCanvas || canvas.renderMode != RenderMode.ScreenSpaceOverlay) continue;
            canvas.renderMode = RenderMode.ScreenSpaceCamera;
            // Set together: a camera-mode canvas with no camera reads back as ScreenSpaceOverlay, so this
            // loop converted it again every frame (SKIP_CAN: 2105 conversions in 30 s on the Quest).
            canvas.worldCamera = overlay;
            canvas.planeDistance = overlay.nearClipPlane + 0.05f;
            Debug.Log("LUNA_PERF theater canvas " + canvas.name + " overlay -> theater overlay camera, order " + canvas.sortingOrder);
        }
    }

    // With VR on, a camera that renders to the headset takes the eye's field of view (about 100 degrees)
    // and refuses its own ("Cannot set field of view ... while VR is enabled"). The first time the menu
    // loads XR is still starting, so its cameras kept the scene's 65 degrees; back from a game they had
    // the headset's, and the menu showed the edges of its painting (Felipe, Builds 85 and 87).
    // Build 86 remembered each camera's value as the scene loaded: back from a game that read was already
    // the headset's, so nothing was restored. The value now comes from the scene file
    // (LunaTheaterFov, written by passes/pass_vr_runtime.py); the read at load is only a fallback
    // for cameras the file does not list.
    readonly Dictionary<Camera, float> authoredFov = new Dictionary<Camera, float>();
    readonly Dictionary<Camera, float> theaterFov = new Dictionary<Camera, float>();
    readonly HashSet<Camera> fovRewritten = new HashSet<Camera>();
    static readonly System.Text.RegularExpressions.Regex SiblingIndex = new System.Text.RegularExpressions.Regex("#-?\\d+");

    public void RememberFieldsOfView()
    {
        authoredFov.Clear();
        theaterFov.Clear();
        foreach (var c in Resources.FindObjectsOfTypeAll<Camera>())
            if (c != null && c.gameObject.scene.IsValid() && c != Eye && c != overlay) authoredFov[c] = c.fieldOfView;
    }

    public static string IndexedPath(Transform t)
    {
        var parts = new List<string>();
        for (; t != null; t = t.parent) parts.Add(t.name + "#" + t.GetSiblingIndex());
        parts.Reverse();
        return string.Join("/", parts);
    }

    // The scene file's value: the exact path first, then the path by names alone when that is unambiguous
    // (the game may add or remove objects before this one, which shifts sibling indices).
    public static bool SceneFileFov(Camera c, out float fov)
    {
        var key = c.gameObject.scene.name + "/" + IndexedPath(c.transform);
        if (LunaTheaterFov.Authored.TryGetValue(key, out fov)) return true;
        var bare = SiblingIndex.Replace(key, "");
        var matches = LunaTheaterFov.Authored.Where(kv => SiblingIndex.Replace(kv.Key, "") == bare).Select(kv => kv.Value).Distinct().ToList();
        fov = matches.Count == 1 ? matches[0] : 0f;
        return matches.Count == 1;
    }

    void RestoreFieldOfView(Camera c)
    {
        c.stereoTargetEye = StereoTargetEyeMask.None;
        float read = c.fieldOfView, fov;
        string source;
        if (SceneFileFov(c, out fov)) source = "scene file";
        else if (authoredFov.TryGetValue(c, out fov)) source = "as loaded";
        else return;
        theaterFov[c] = fov;
        if (Mathf.Abs(read - fov) > 0.1f) c.fieldOfView = fov;
        Debug.Log("LUNA_PERF theater camera " + c.name + " field of view read " + read.ToString("F1") + ", set " + fov.ToString("F1") + " (" + source + ")");
    }

    // Held every frame against the headset only: its value (about 100 degrees) is undone, back to the last one the
    // game set. The game's own changes stay: the new-game intro zooms SCENE_CAM 65 -> 35 -> 25, and Build 88-91
    // pulled it back to 65 every frame (Felipe's Build 91 log; LESSONS 28).
    const float HeadsetFov = 100f;
    readonly List<Camera> fovKeys = new List<Camera>();
    void HoldFieldsOfView()
    {
        fovKeys.Clear(); fovKeys.AddRange(theaterFov.Keys);
        foreach (var c in fovKeys)
        {
            if (c == null || c.targetTexture != Texture) continue;
            float now = c.fieldOfView, want = theaterFov[c];
            if (Mathf.Abs(now - want) <= 0.1f) continue;
            if (Mathf.Abs(now - HeadsetFov) < 1.5f && Mathf.Abs(want - HeadsetFov) >= 1.5f)
            {
                if (fovRewritten.Add(c)) Debug.Log("LUNA_PERF theater camera " + c.name + " took the headset's " + now.ToString("F1") + ", back to " + want.ToString("F1") + " (logged once)");
                c.fieldOfView = want;
            }
            else theaterFov[c] = now;   // the game's own zoom
        }
    }

    void ReleaseGameCameras()
    {
        foreach (var c in Camera.allCameras)
            if (c != Eye && c != overlay && c.targetTexture == Texture)
            {
                c.targetTexture = null;
                c.stereoTargetEye = StereoTargetEyeMask.Both;
                c.ResetAspect();
            }
    }

    // Screen pixel (in the texture) under a world-space ray, if it hits the screen.
    public bool RayToPixel(Ray ray, out Vector2 pixel, out Vector3 hit)
    {
        pixel = default; hit = default;
        var plane = new Plane(-Screen.forward, Screen.position);
        if (!plane.Raycast(ray, out float d)) return false;
        hit = ray.GetPoint(d);
        Vector3 local = Screen.InverseTransformPoint(hit);   // quad spans -0.5..0.5
        if (Mathf.Abs(local.x) > 0.5f || Mathf.Abs(local.y) > 0.5f) return false;
        pixel = new Vector2((local.x + 0.5f) * Width, (local.y + 0.5f) * Height);
        return true;
    }
}

// Right-controller laser for the game's UI; the trigger is the click. The owner says where controller
// poses live (Origin + OriginOffset, the tracking space) and how a ray maps to a pixel. On the theater
// it feeds a virtual mouse at the laser's pixel (the menus read the mouse). On the HUD panel the owner
// also gives PickAt, the UI element under the hit, and the laser sends it pointer events directly: the
// panel is a world canvas seen in stereo, where a mouse pixel lands off the element.
public class LunaVRPointer : MonoBehaviour
{
    public delegate bool PixelFinder(Ray ray, out Vector2 pixel, out Vector3 hit);
    public System.Func<Vector3, GameObject> PickAt;
    GameObject hovered, pressed;
    bool wasTrigger;
    static readonly InputFeatureUsage<Vector3> PointerPosition = new InputFeatureUsage<Vector3>("PointerPosition");
    static readonly InputFeatureUsage<Quaternion> PointerRotation = new InputFeatureUsage<Quaternion>("PointerRotation");
    public Transform Origin;
    public Vector3 OriginOffset;
    public PixelFinder RayToPixel;
    public int Layer
    {
        set { if (laser != null) { laser.gameObject.layer = value; dot.gameObject.layer = value; grip.gameObject.layer = value; } layer = value; }
    }
    int layer = LunaTheater.Layer;
    Mouse laserMouse;   // Input System mouse the game's InputSystemUIInputModule reads
    LineRenderer laser;
    Transform dot, grip;
    VirtualMouse mouse;

    void Awake()
    {
        var go = new GameObject("LunaLaser");
        go.layer = layer;
        go.transform.SetParent(transform, false);
        laser = go.AddComponent<LineRenderer>();
        laser.useWorldSpace = true;
        laser.positionCount = 2;
        laser.widthMultiplier = 0.004f;
        // Unlit/Texture is already in the build (the screen uses it); a 1x1 lilac texture gives the colour.
        var tint = new Texture2D(1, 1);
        tint.SetPixel(0, 0, new Color(0.75f, 0.55f, 1f));
        tint.Apply();
        laser.material = new Material(Shader.Find("Unlit/Texture")) { mainTexture = tint };

        dot = GameObject.CreatePrimitive(PrimitiveType.Sphere).transform;
        Destroy(dot.GetComponent<Collider>());
        dot.gameObject.layer = layer;
        dot.SetParent(transform, false);
        dot.localScale = Vector3.one * 0.03f;
        dot.GetComponent<MeshRenderer>().sharedMaterial = laser.material;
        // A small stick where the controller is, so the laser visibly leaves the hand.
        grip = GameObject.CreatePrimitive(PrimitiveType.Cube).transform;
        Destroy(grip.GetComponent<Collider>());
        grip.gameObject.layer = layer;
        grip.SetParent(transform, false);
        grip.localScale = new Vector3(0.025f, 0.025f, 0.1f);
        grip.GetComponent<MeshRenderer>().sharedMaterial = laser.material;
        mouse = gameObject.AddComponent<VirtualMouse>();
    }

    void OnDisable()
    {
        SetHovered(null, null);
        pressed = null;
        dragging = null;
        if (laserMouse != null) { InputSystem.RemoveDevice(laserMouse); laserMouse = null; }
        if (laser != null) laser.enabled = false;
        if (dot != null) dot.gameObject.SetActive(false);
        if (grip != null) grip.gameObject.SetActive(false);
    }

    void Update()
    {
        if (Origin == null || RayToPixel == null) { laser.enabled = false; dot.gameObject.SetActive(false); grip.gameObject.SetActive(false); return; }
        var hand = InputDevices.GetDeviceAtXRNode(XRNode.RightHand);
        if (!hand.isValid) hand = InputDevices.GetDeviceAtXRNode(XRNode.LeftHand);
        // The pointer pose aims along the controller; the grip pose (devicePosition) points ~40 degrees down.
        if (!(hand.TryGetFeatureValue(PointerPosition, out Vector3 p) && hand.TryGetFeatureValue(PointerRotation, out Quaternion r)) &&
            !(hand.TryGetFeatureValue(CommonUsages.devicePosition, out p) && hand.TryGetFeatureValue(CommonUsages.deviceRotation, out r)))
        {
            laser.enabled = false; dot.gameObject.SetActive(false); grip.gameObject.SetActive(false);
            return;
        }
        bool trigger = LunaTrigger.Held(hand);

        // Device poses are in tracking space.
        // Controller poses get the same software recentre as the head (LunaHeadTracker.Recentre).
        p = LunaHeadTracker.YawOffset * (p - LunaHeadTracker.PositionOffset);
        r = LunaHeadTracker.YawOffset * r;
        var ray = new Ray(Origin.TransformPoint(OriginOffset + p), Origin.rotation * r * Vector3.forward);
        bool onScreen = RayToPixel(ray, out Vector2 pixel, out Vector3 hit);
        laser.enabled = true;
        grip.gameObject.SetActive(true);
        grip.SetPositionAndRotation(ray.origin - ray.direction * 0.05f, Quaternion.LookRotation(ray.direction));
        laser.SetPosition(0, ray.origin);
        laser.SetPosition(1, onScreen ? hit : ray.GetPoint(5f));
        dot.gameObject.SetActive(onScreen);
        if (onScreen) dot.position = hit;

        if (PickAt != null)
        {
            SendDirect(onScreen ? PickAt(hit) : null, trigger, pixel, hit);
            return;
        }
        mouse.Position = pixel;
        mouse.Present = onScreen;
        mouse.Down = trigger && onScreen;
        if (laserMouse == null) laserMouse = InputSystem.AddDevice<Mouse>("LunaLaserMouse");
        if (onScreen || trigger)
            InputSystem.QueueStateEvent(laserMouse, new MouseState { position = pixel, buttons = (ushort)(mouse.Down ? 1 : 0) });
        var es = EventSystem.current;
        if (es != null && es.currentInputModule != null && es.currentInputModule.inputOverride != mouse)
            es.currentInputModule.inputOverride = mouse;
    }

    // The raycast carries the canvas's raycaster as its module: that is where press/enterEventCamera
    // come from. Without it a slider read the laser's pixel as a flat screen point, far outside its
    // track, and jumped to its minimum or maximum (Build 73).
    PointerEventData EventAt(Vector2 pixel, Vector3 hit, GameObject target)
    {
        BaseRaycaster module = null;
        var canvas = target != null ? target.GetComponentInParent<Canvas>() : null;
        if (canvas != null) module = canvas.rootCanvas.GetComponent<BaseRaycaster>();
        if (module == null && dragging != null) module = dragModule;
        var cast = new RaycastResult { gameObject = target, worldPosition = hit, module = module, screenPosition = pixel };
        return new PointerEventData(EventSystem.current)
        {
            position = pixel,
            pressPosition = pressPixel,
            button = PointerEventData.InputButton.Left,
            pointerCurrentRaycast = cast,
            pointerPressRaycast = dragging != null ? dragCast : cast,
            pointerDrag = dragging,
            dragging = dragging != null,
            useDragThreshold = false,
        };
    }

    // A press on something draggable (a slider, a scroll bar) drags it while the trigger stays down.
    GameObject dragging;
    BaseRaycaster dragModule;
    RaycastResult dragCast;
    Vector2 pressPixel;

    void SetHovered(GameObject target, PointerEventData data)
    {
        if (target == hovered) return;
        if (hovered != null && EventSystem.current != null)
            ExecuteEvents.ExecuteHierarchy(hovered, data ?? new PointerEventData(EventSystem.current), ExecuteEvents.pointerExitHandler);
        hovered = target;
        if (hovered != null && data != null) ExecuteEvents.ExecuteHierarchy(hovered, data, ExecuteEvents.pointerEnterHandler);
    }

    // Hover is enter/exit, the trigger press selects and presses, the release clicks what was pressed
    // if the laser is still on it, like a mouse button.
    void SendDirect(GameObject target, bool trigger, Vector2 pixel, Vector3 hit)
    {
        var es = EventSystem.current;
        if (es == null) return;
        var data = EventAt(pixel, hit, target);
        SetHovered(target, data);
        if (trigger && !wasTrigger && target != null)
        {
            pressed = ExecuteEvents.GetEventHandler<IPointerClickHandler>(target);
            var select = ExecuteEvents.GetEventHandler<ISelectHandler>(target);
            if (select != null) es.SetSelectedGameObject(select, data);
            ExecuteEvents.ExecuteHierarchy(target, data, ExecuteEvents.pointerDownHandler);
            pressPixel = pixel;
            var drag = ExecuteEvents.GetEventHandler<IDragHandler>(target);
            if (drag != null)
            {
                dragCast = data.pointerCurrentRaycast;
                dragModule = dragCast.module;
                data.pointerPressRaycast = dragCast;
                data.pointerDrag = drag;
                ExecuteEvents.Execute(drag, data, ExecuteEvents.initializePotentialDrag);
                ExecuteEvents.Execute(drag, data, ExecuteEvents.beginDragHandler);
                dragging = drag;
            }
        }
        else if (trigger && wasTrigger && dragging != null && target != null)
        {
            ExecuteEvents.Execute(dragging, data, ExecuteEvents.dragHandler);
        }
        else if (!trigger && wasTrigger)
        {
            if (dragging != null) { ExecuteEvents.Execute(dragging, data, ExecuteEvents.endDragHandler); dragging = null; }
            if (target != null) ExecuteEvents.ExecuteHierarchy(target, data, ExecuteEvents.pointerUpHandler);
            if (pressed != null && target != null && ExecuteEvents.GetEventHandler<IPointerClickHandler>(target) == pressed)
                ExecuteEvents.Execute(pressed, data, ExecuteEvents.pointerClickHandler);
            pressed = null;
        }
        wasTrigger = trigger;
    }
}

// BaseInput replacement the UI module reads instead of the real mouse.
public class VirtualMouse : BaseInput
{
    public Vector2 Position;
    public bool Present, Down;
    bool wasDown, down, up;

    void Update()
    {
        down = Down && !wasDown;
        up = !Down && wasDown;
        wasDown = Down;
    }

    public override bool mousePresent => Present;
    public override Vector2 mousePosition => Position;
    public override Vector2 mouseScrollDelta => Vector2.zero;
    public override bool GetMouseButton(int button) => button == 0 && Down;
    public override bool GetMouseButtonDown(int button) => button == 0 && down;
    public override bool GetMouseButtonUp(int button) => button == 0 && up;
    public override int touchCount => 0;
}

// Gameplay scenes: the head looks around freely (the right stick's Look stays unbound, so the game's
// pitch stays level), the right stick snap-turns the player's body, and screen-space HUD canvases
// become a world panel in front of the eyes that eases after the head.
//
// Controls: the Touch controllers drive a virtual gamepad (LunaTouchPad) and every PlayerInput is held
// on the game's own Gamepad scheme, so the game plays exactly as with an Xbox pad. Bindings on the XR
// controller devices did not reach the game (only the grip did; Builds 35-38), while the XR device API
// reads every control. Layout:
//   left stick  Move                     right stick  turning only
//   right trigger  Fire                  right stick click  use item (dpad up)
//   left trigger   Block                 left stick click   next item (dpad right)
//   A  Jump / menu submit                B  Sprint, Spin           X  Activate     Y  Swap weapon
//   left grip   Magic1 (LB)              right grip  Magic2 (RB)   left menu  Inventory (select)
// The right stick used to push items too (up = use, down = swap): turning set them off unasked
// (Felipe, 2026-11-10), so it only turns now. PadState is the whole mapping (LunaProbe TouchMapping).
// Places HANDS before the game's LateUpdates (DynamicBone on the ANGEL CASE handle simulates there).
// Only this runs early: in Build 82 the whole of LunaVRGameplay ran first, and Felipe found the walk
// slower and fell through the floor at the start; the gameplay script is back at the default order.
[DefaultExecutionOrder(-1000)]
public class LunaHandsEarly : MonoBehaviour
{
    public LunaVRGameplay Gameplay;
    void LateUpdate() { if (Gameplay != null && Gameplay.isActiveAndEnabled) Gameplay.PlaceHandsEarly(); }
}

public class LunaVRGameplay : MonoBehaviour
{
    const float SnapAngle = 30f, SnapThreshold = 0.7f, ReleaseThreshold = 0.3f;
    const float HudDistance = 1.6f, HudDrop = 0.1f, HudWidth = 2.4f, HudFollowRate = 5f;

    static readonly System.Type PlayerType = System.Type.GetType("Player_Control_scr, Assembly-CSharp");
    static readonly System.Reflection.FieldInfo RotField = PlayerType?.GetField("ROT");
    static readonly System.Reflection.FieldInfo OldRotField = PlayerType?.GetField("OLD_ROT",
        System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);
    static readonly System.Reflection.FieldInfo FreezeField = PlayerType?.GetField("Freeze");
    static readonly System.Reflection.FieldInfo HandsField = PlayerType?.GetField("HANDS");
    static readonly System.Reflection.FieldInfo HandOffsetField = PlayerType?.GetField("HAND_offset");

    Component player;
    int handJumps;
    float handJumpWorst, nextHandLog;
    Quaternion handAim;
    bool handAimSet, handOffsetLogged;
    LunaVRPointer pointer;
    Gamepad pad;
    bool snapped, inputLogged;
    float nextScan;
    Quaternion hudGaze = Quaternion.identity;
    bool hudGazeSet;
    readonly List<RectTransform> huds = new List<RectTransform>();

    void Update()
    {
        if (Time.unscaledTime >= nextScan)
        {
            nextScan = Time.unscaledTime + 1f;
            TrackHeadOnGameCameras();
            if (player == null && PlayerType != null) { player = (Component)FindObjectOfType(PlayerType); if (player != null) LogSpawn(); }
            if (player != null) { AnchorHud(); WalkByDefault(); CenterPopText(); LunaVRRuntime.SwitchOffPlayerInterpolation(player); }
            PatchControlTexts();
            HoldGamepadScheme();
        }
        SnapTurn();
        RideMovingParent();
        KeepPopIcons();
        LogPopIcon();
        PointAtMenus();
        FeedPad();
        if (huds.Count > 0 && Time.timeSinceLevelLoad > 8f && Time.unscaledTime >= nextHudDump) { nextHudDump = Time.unscaledTime + 1f; DumpHud(); }
        if (Time.unscaledTime >= nextHudMaterialCheck)
        {
            nextHudMaterialCheck = Time.unscaledTime + HudMaterialInterval;
            HideMenusWhileLoading();
            foreach (var rt in huds) if (rt != null) ReplaceBrokenUiMaterials(rt);
        }
    }

    // Felipe (Build 80): a new game sometimes starts at the save crystal instead of the hand opening, and
    // the tour saw save loads land at the new-game spawn. Log where the player is when found, the save
    // slot, the loaded data's position and whether Hold_Data carried data from the previous scene.
    void LogSpawn()
    {
        try
        {
            var con = ControlType != null ? FindObjectOfType(ControlType) : null;
            var data = con != null ? ControlType.GetField("CURRENT_PL_DATA")?.GetValue(con) : null;
            var hold = System.Type.GetType("Hold_Data, Assembly-CSharp")?.GetField("HD")?.GetValue(null);
            string Pos(object d) => d == null ? "null" : "(" + d.GetType().GetField("POS_X")?.GetValue(d) + ", "
                + d.GetType().GetField("POS_Y")?.GetValue(d) + ", " + d.GetType().GetField("POS_Z")?.GetValue(d) + ") name="
                + d.GetType().GetField("PLAYER_NAME")?.GetValue(d);
            Debug.Log("LUNA_SPAWN scene=" + SceneManager.GetActiveScene().name + " player=" + player.transform.position.ToString("F1")
                      + " enabled=" + ((Behaviour)player).enabled + " slot=" + PlayerPrefs.GetInt("CURRENT_SAVE", 0)
                      + " data=" + Pos(data) + " hold=" + (hold == null ? "null" : (ReferenceEquals(hold, data) ? "same " : "other ") + Pos(hold))
                      + " t=" + Time.timeSinceLevelLoad.ToString("F1"));
        }
        catch (System.Exception e) { Debug.Log("LUNA_SPAWN failed: " + e.Message); }
    }

    // The TOWER boat carries the player as a child of its animated MOVE object. In Unity 6 an interpolated
    // rigidbody writes its own world pose every frame, so the parent's motion no longer carries it: the
    // boat slides out from under the player, who drops into the fall zone. While the parent animation
    // plays, the body is made kinematic and not interpolated (the game's Unity 2020 behaviour), and put
    // back as it was when the ride ends.
    Rigidbody riding;
    bool ridingWasKinematic;
    RigidbodyInterpolation ridingInterpolation;

    void RideMovingParent()
    {
        var body = player != null ? player.GetComponent<Rigidbody>() : null;
        var parent = player != null ? player.transform.parent : null;
        var anim = parent != null ? parent.GetComponent<Animation>() : null;
        bool moving = body != null && anim != null && anim.isPlaying;
        if (moving && riding == null)
        {
            riding = body;
            ridingWasKinematic = body.isKinematic;
            ridingInterpolation = body.interpolation;
            body.isKinematic = true;
            body.interpolation = RigidbodyInterpolation.None;
            Debug.Log("LUNA_VR riding " + parent.name + ": player body kinematic while it moves");
        }
        else if (!moving && riding != null)
        {
            riding.isKinematic = ridingWasKinematic;
            riding.interpolation = ridingInterpolation;
            riding = null;
            Debug.Log("LUNA_VR ride over: player body restored");
        }
    }

    // The game runs by default (8 m/s) and its Sprint button (B) walks (3 m/s); its "always run" setting
    // (SETTING_RUN) flips that. In the headset walking is the comfortable default, so the first time the
    // port runs a game it turns the setting on and saves it through the game's own Save.SAVE_SYSTEM.
    // After that the game's menu option decides.
    const string WalkDefaultKey = "LunaVR_WalkByDefault";
    static readonly System.Type ControlType = System.Type.GetType("CONTROL, Assembly-CSharp");
    static readonly System.Type SaveType = System.Type.GetType("Save, Assembly-CSharp");

    void WalkByDefault()
    {
        if (PlayerPrefs.GetInt(WalkDefaultKey, 0) == 1 || ControlType == null || SaveType == null) return;
        var con = FindObjectOfType(ControlType);
        var data = con != null ? ControlType.GetField("CURRENT_SYS_DATA")?.GetValue(con) : null;
        var run = data?.GetType().GetField("SETTING_RUN");
        var save = SaveType.GetMethod("SAVE_SYSTEM", new[] { ControlType });
        if (run == null || save == null) return;
        run.SetValue(data, 1);
        save.Invoke(null, new object[] { con });
        PlayerPrefs.SetInt(WalkDefaultKey, 1);
        PlayerPrefs.Save();
        Debug.Log("LUNA_INPUT walk by default: SETTING_RUN=1 saved");
    }

    // The head-tracked camera. CAM and its child CAM2 are both tagged MainCamera, so Camera.main can be
    // CAM2: taking its parent as the tracking origin applied the head pose twice (the menu laser came
    // from the body and moved with the head).
    static LunaHeadTracker HeadTracker()
    {
        var cam = Camera.main;
        return cam != null ? cam.GetComponentInParent<LunaHeadTracker>() : null;
    }

    // Lines drawn in world space on the weapon (the fishing rod's line, Fishing.Update, and the other
    // corded weapon) were set where HANDS stood in the game's Update, then HANDS moved under the
    // headset: the cords flickered (Felipe, Build 80). Their points move with HANDS.
    readonly List<LineRenderer> lineBuf = new List<LineRenderer>();
    Vector3[] pointBuf = new Vector3[64];

    void CarryLines(GameObject hands, Vector3 oldPos, Quaternion oldRot)
    {
        var newPos = hands.transform.position;
        var newRot = hands.transform.rotation;
        if ((newPos - oldPos).sqrMagnitude < 1e-8f && Quaternion.Angle(oldRot, newRot) < 0.01f) return;
        var inv = Quaternion.Inverse(oldRot);
        hands.GetComponentsInChildren(false, lineBuf);
        foreach (var lr in lineBuf)
        {
            if (!lr.useWorldSpace || lr.positionCount == 0) continue;
            if (pointBuf.Length < lr.positionCount) pointBuf = new Vector3[lr.positionCount * 2];
            int n = lr.GetPositions(pointBuf);
            for (int i = 0; i < n; i++) lr.SetPosition(i, newPos + newRot * (inv * (pointBuf[i] - oldPos)));
        }
    }

    // The game's pop-up line (CON.PAPPY, POP_text_scr: weapon name on a swap, item picked up, "A door
    // opens"...) sits at the left of the PC screen; in the headset that is the edge of sight. Felipe asked
    // for the bottom centre: it is re-anchored there on the panel, text centred, under the aim mark.
    static readonly System.Type PopType = System.Type.GetType("POP_text_scr, Assembly-CSharp");
    Component popCentred;

    const float PopHalfWidth = 450f, PopCentreY = -5f;

    void CenterPopText()
    {
        if (PopType == null) return;
        var pop = (Component)FindObjectOfType(PopType);
        if (pop == null || pop == popCentred) return;
        popCentred = pop;
        var rt = pop.transform as RectTransform;
        var tm = pop.GetComponent<TMPro.TextMeshProUGUI>();
        if (rt == null || tm == null) return;
        // POP_TEXT is the parent of the reading text and of the death and warp effects, which the game places
        // from it: moving it carried them up and to the right (Felipe, reading a note, Build 83). It stays
        // where the game put it, and only the line's own text box is moved, through its margins.
        var root = rt.GetComponentInParent<Canvas>().rootCanvas.transform;
        var target = rt.InverseTransformPoint(root.TransformPoint(new Vector3(0f, PopCentreY, 0f)));
        var r = rt.rect;
        float dx = target.x - r.center.x, dy = target.y - r.center.y;
        tm.margin = new Vector4(dx - PopHalfWidth + r.width / 2f, -dy, r.width / 2f - dx - PopHalfWidth, dy);
        tm.alignment = TMPro.TextAlignmentOptions.Bottom;
        Debug.Log("LUNA_VR pop text box moved by margins, dx=" + dx.ToString("F0") + " dy=" + dy.ToString("F0"));
    }

    // The game teleports the player through its transform (Teleport_scr, ShadowTower_CON, Act_Button_scr...).
    // Outside a physics callback an interpolated body wrote its old pose back: 3 to 7 of 16 teleports were lost with
    // the port off, all from Update. The body gets the new position when the transform jumps. Only then: syncing
    // every frame pushed the interpolated pose into the body on frames with no physics step, and at 90 fps the
    // player stopped part of the way (TOWER). No physics step moves it this far, even falling.
    const float TeleportJump = 1f;
    Component teleportWatched;
    Vector3 teleportLast;

    void CommitTeleport()
    {
        if (player == null || !player.gameObject.activeInHierarchy) { teleportWatched = null; return; }
        var at = player.transform.position;
        if (player == teleportWatched && (at - teleportLast).sqrMagnitude > TeleportJump * TeleportJump) Physics.SyncTransforms();
        teleportWatched = player;
        teleportLast = at;
    }

    // POP_text_scr.Reset switches off every child of the pop-up line when a new line arrives while the last is
    // playing, and POP switches back on the ones named "TMP...". In the editor TMP names the icon's object
    // "TMP SubMeshUI [...]"; in a build it is "New Game Object", so the icon stayed off for good (Felipe).
    void KeepPopIcons()
    {
        if (popCentred == null) return;
        bool restored = false;
        foreach (var sub in popCentred.GetComponentsInChildren<TMPro.TMP_SubMeshUI>(true))
            if (!sub.gameObject.activeSelf) { sub.gameObject.SetActive(true); restored = true; }
        if (restored && popCentred.TryGetComponent<TMPro.TextMeshProUGUI>(out var tm))
        {
            tm.SetVerticesDirty();
            Debug.Log("LUNA_ICON restored the icon object after a reset"); // unproven in the editor: this line says if it ever acts
        }
    }

    // Felipe's video (Build 84): "2 [gap] ACQUIRED", the icon missing. The editor shows it healthy, so log its
    // state on the headset, a few frames after each line with an icon.
    string popLastText;
    int popLogIn;

    void LogPopIcon()
    {
        if (popCentred == null || !popCentred.TryGetComponent<TMPro.TextMeshProUGUI>(out var tm)) return;
        if (tm.text != popLastText)
        {
            popLastText = tm.text;
            popLogIn = popLastText != null && popLastText.Contains("<sprite") ? 3 : 0;
        }
        if (popLogIn == 0 || --popLogIn > 0) return;
        var line = "LUNA_ICON text='" + tm.text + "' alpha=" + tm.color.a.ToString("F2");
        foreach (var sub in popCentred.GetComponentsInChildren<TMPro.TMP_SubMeshUI>(true))
        {
            var m = sub.materialForRendering;
            line += " | go=" + sub.gameObject.activeInHierarchy + " on=" + sub.enabled + " verts=" + (sub.mesh != null ? sub.mesh.vertexCount : -1) + " cull=" + sub.canvasRenderer.cull
                    + " alpha=" + sub.canvasRenderer.GetInheritedAlpha().ToString("F2") + " mat=" + (m != null ? m.name + "/" + m.shader.name + "/" + m.shader.isSupported + "/" + (m.mainTexture != null ? m.mainTexture.name : "NOTEX") : "NULL");
        }
        Debug.Log(line);
    }

    // Felipe (Build 82): the walk feels slower than before. Every 5 s while moving: the body's speed,
    // the game's speed stat, ALWAYS RUN, sprint and whether the game thinks the player is grounded.
    float nextMoveLog;
    static readonly System.Reflection.FieldInfo SpeedField = PlayerType?.GetField("speed");
    static readonly System.Reflection.FieldInfo SprintField = PlayerType?.GetField("sprinting",
        System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);
    static readonly System.Reflection.FieldInfo GroundedField = PlayerType?.GetField("grounded",
        System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);

    void LogMovement()
    {
        if (player == null || Time.unscaledTime < nextMoveLog) return;
        var body = player.GetComponent<Rigidbody>();
        if (body == null) return;
        var v = body.linearVelocity; v.y = 0f;
        if (v.magnitude < 0.5f) return;
        nextMoveLog = Time.unscaledTime + 5f;
        var sys = SysData();
        var run = sys?.GetType().GetField("SETTING_RUN")?.GetValue(sys);
        Debug.Log("LUNA_MOVE v=" + v.magnitude.ToString("F2") + " speed=" + SpeedField?.GetValue(player) + " sprint=" + SprintField?.GetValue(player)
                  + " grounded=" + GroundedField?.GetValue(player) + " run=" + run + " kinematic=" + body.isKinematic
                  + " parent=" + (player.transform.parent != null ? player.transform.parent.name : "none") + " fixedDt=" + Time.fixedDeltaTime.ToString("F4") + " timeScale=" + Time.timeScale);
    }

    // The aim mark (HUD/GAME/REDICLE: always, bow, magic) sat on the HUD panel, 1.6 m away and HudDrop
    // below the gaze, lagging the head. Bolts, arrows and spells fly from the centre of the view
    // (Spawn_on_enable FromCam pulls them onto the camera line), so they landed up and to the right of
    // the mark (Felipe, Build 80; right from the dominant eye's parallax at 1.6 m). The mark is now drawn
    // at the centre of the view, at the distance of what it points at, with the PC's angular size; the
    // panel copy is hidden.
    RectTransform reticleSrc;
    Canvas reticleCanvas;
    readonly List<(UnityEngine.UI.Image src, UnityEngine.UI.Image dst)> reticleParts = new List<(UnityEngine.UI.Image, UnityEngine.UI.Image)>();
    const float ReticleMaxDistance = 30f, PcFov = 65f, PcHeight = 720f;

    // A physics query syncs every moved transform into its Rigidbody (m_AutoSyncTransforms is on). During
    // Update and LateUpdate the player holds the position the game's InterpolationObjectController lerped,
    // behind the real one, so a raycast there pulled the body back (real walk 1.41 m/s against 1.63 without
    // it; the larger loss is in HoldSpawnInterpolation's note). In FixedUpdate the transforms hold the real
    // pose; the mark uses the last distance found.
    float reticleDistance = ReticleMaxDistance;

    void FixedUpdate()
    {
        var head = HeadTracker();
        if (head == null) return;
        var cam = head.transform;
        reticleDistance = Physics.Raycast(cam.position, cam.forward, out var hit, ReticleMaxDistance, ~0, QueryTriggerInteraction.Ignore)
            ? Mathf.Max(0.5f, hit.distance * 0.95f) : ReticleMaxDistance;
    }

    void PlaceReticle()
    {
        try
        {
            if (reticleSrc == null)
            {
                reticleParts.Clear();
                if (reticleCanvas != null) Destroy(reticleCanvas.gameObject);
                foreach (var h in huds)
                {
                    if (h == null) continue;
                    var t = h.GetComponentsInChildren<RectTransform>(true).FirstOrDefault(r => r.name == "REDICLE");
                    if (t != null) { reticleSrc = t; break; }
                }
                if (reticleSrc == null) return;
                var go = new GameObject("LunaReticle", typeof(RectTransform));
                go.layer = reticleSrc.gameObject.layer;
                reticleCanvas = go.AddComponent<Canvas>();
                reticleCanvas.renderMode = RenderMode.WorldSpace;
                reticleCanvas.sortingOrder = 32000;
                foreach (var img in reticleSrc.GetComponentsInChildren<UnityEngine.UI.Image>(true))
                {
                    var d = new GameObject(img.name, typeof(RectTransform)).AddComponent<UnityEngine.UI.Image>();
                    d.transform.SetParent(go.transform, false);
                    d.gameObject.layer = go.layer;
                    d.raycastTarget = false;
                    reticleParts.Add((img, d));
                    img.material = HiddenUiMaterial();
                }
                Debug.Log("LUNA_VR reticle drawn at the view centre: " + string.Join(",", reticleParts.Select(p => p.src.name)));
            }
            var head = HeadTracker();
            if (head == null || reticleCanvas == null) return;
            var cam = head.transform;
            float dist = reticleDistance;
            // One canvas unit = one PC pixel at the PC's 65 degree, 720 px high view.
            float unit = 2f * dist * Mathf.Tan(PcFov * 0.5f * Mathf.Deg2Rad) / PcHeight;
            var rt = (RectTransform)reticleCanvas.transform;
            rt.SetPositionAndRotation(cam.position + cam.forward * dist, cam.rotation);
            rt.localScale = Vector3.one * unit;
            foreach (var (src, dst) in reticleParts)
            {
                if (src == null || dst == null) continue;
                bool on = src.isActiveAndEnabled;
                dst.enabled = on;
                if (!on) continue;
                dst.sprite = src.sprite;
                dst.color = src.color;
                dst.type = src.type;
                dst.rectTransform.sizeDelta = src.rectTransform.rect.size;
                dst.rectTransform.anchoredPosition = Vector2.zero;
                if (src.material != HiddenUiMaterial()) src.material = HiddenUiMaterial();
            }
        }
        catch (System.Exception e) { Debug.Log("LUNA_VR reticle failed: " + e.Message); reticleSrc = null; }
    }

    // Diagnostic (Felipe, Build 88: the spell lands right of the aim mark, with either eye). Magic_scr puts each
    // cast under Camera.main; a new child is followed for half a second and its place logged against the head's
    // view at the cast and against the aim mark: LUNA_AIM lines.
    Transform spellParent;
    readonly HashSet<Transform> spellSeen = new HashSet<Transform>();
    readonly List<Transform> spellCandidates = new List<Transform>();
    Transform spellTracked;
    Vector3 spellOrigin; Quaternion spellHead; Vector3 spellAim; float spellAimDist, spellStart; int spellStep;
    static readonly float[] SpellTimes = { 0.1f, 0.3f, 0.5f };

    static string Degrees(Quaternion frame, Vector3 v)
    {
        var l = Quaternion.Inverse(frame) * v;
        return "right " + (Mathf.Atan2(l.x, l.z) * Mathf.Rad2Deg).ToString("F1") + " up " + (Mathf.Atan2(l.y, l.z) * Mathf.Rad2Deg).ToString("F1");
    }

    void LogSpellFlight()
    {
        try
        {
            var main = Camera.main;
            var head = HeadTracker();
            if (main == null || head == null) return;
            if (spellParent != main.transform)
            {
                spellParent = main.transform; spellSeen.Clear();
                foreach (Transform c in spellParent) spellSeen.Add(c);
                foreach (var root in SceneManager.GetActiveScene().GetRootGameObjects()) spellSeen.Add(root.transform);
            }
            spellCandidates.Clear();
            foreach (Transform c in spellParent) spellCandidates.Add(c);
            // A cast may already have left the camera (Break_from_parent in its Start) when this runs.
            foreach (var root in SceneManager.GetActiveScene().GetRootGameObjects())
                if (root.name.IndexOf("_CAST", System.StringComparison.OrdinalIgnoreCase) >= 0) spellCandidates.Add(root.transform);
            foreach (var c in spellCandidates)
            {
                if (spellSeen.Contains(c)) continue;
                spellSeen.Add(c);
                if (c.name.IndexOf("CAST", System.StringComparison.OrdinalIgnoreCase) < 0) continue;
                spellTracked = c; spellOrigin = head.transform.position; spellHead = head.transform.rotation;
                spellStart = Time.time; spellStep = 0;
                spellAimDist = reticleDistance;
                spellAim = reticleCanvas != null ? (reticleCanvas.transform.position - spellOrigin).normalized : head.transform.forward;
                Debug.Log("LUNA_AIM cast " + c.name + " camera.main=" + main.name + " " + Degrees(spellHead, main.transform.forward) + " vs head; spell " + Degrees(spellHead, c.forward)
                          + "; aim mark " + Degrees(spellHead, spellAim) + " at " + spellAimDist.ToString("F1") + " m; spell from head " + (Quaternion.Inverse(spellHead) * (c.position - spellOrigin)).ToString("F2")
                          + "; head local " + head.transform.localEulerAngles.ToString("F1") + " HEAD " + head.transform.parent.eulerAngles.ToString("F1"));
            }
            if (spellTracked == null || spellStep >= SpellTimes.Length) return;
            if (Time.time - spellStart < SpellTimes[spellStep]) return;
            var pos = spellTracked.position;
            Debug.Log("LUNA_AIM spell at " + SpellTimes[spellStep].ToString("F1") + " s: " + Degrees(spellHead, pos - spellOrigin) + " deg from the head at the cast, "
                      + Vector3.Distance(pos, spellOrigin).ToString("F1") + " m; parent=" + (spellTracked.parent != null ? spellTracked.parent.name : "none") + "; head now " + Degrees(spellHead, head.transform.forward));
            spellStep++;
        }
        catch (System.Exception e) { Debug.Log("LUNA_AIM failed: " + e.Message); spellTracked = null; spellStep = SpellTimes.Length; }
    }

    // The ANGEL CASE flickered (Felipe, Build 80) as the sword did before Build 40: its handle swings on
    // a DynamicBone, which simulates in LateUpdate from where HANDS stands then; the weapon is put under
    // the headset only before rendering, so the bones were solved at the game's HANDS pose and drawn at
    // ours, alternating. HANDS is placed here too, before the game's LateUpdates.
    // (called from LateUpdate below)

    void OnEnable()
    {
        if (pad == null) pad = InputSystem.AddDevice<Gamepad>("LunaTouchPad");
        Application.onBeforeRender += PlaceHands;
        var inputs = new List<XRInputSubsystem>();
        SubsystemManager.GetSubsystems(inputs);
        foreach (var i in inputs) i.trackingOriginUpdated += OnRecentre;
    }

    // A recentre (holding the Meta button), the app coming back from a pause or regaining focus (the
    // headset was taken off and put back on): zero the headset's yaw against the body, as a system
    // recentre does, so forward is where you look again and the HUD panel comes back in front. The
    // game walks along the body; after the headset came back on facing elsewhere, forward was off to
    // the side ("como se eu tivesse andado de lado"). Turning the body instead (Build 75) did nothing,
    // since the camera turns with it, and fed a loop that shook the view.
    void OnRecentre(XRInputSubsystem _)
    {
        LunaHeadTracker.Recentre();
        hudGazeSet = false;
        handAimSet = false;
        Debug.Log("LUNA_INPUT recentred");
    }
    void OnApplicationPause(bool paused) { if (!paused) OnRecentre(null); }
    void OnApplicationFocus(bool focused) { if (focused) OnRecentre(null); }

    void OnDisable()
    {
        Application.onBeforeRender -= PlaceHands;
        var inputs = new List<XRInputSubsystem>();
        SubsystemManager.GetSubsystems(inputs);
        foreach (var i in inputs) i.trackingOriginUpdated -= OnRecentre;
        if (viewLayer != null) viewLayer.gameObject.SetActive(false);
        if (pointer != null) pointer.enabled = false;
        // Menu-like scenes go back to the laser mouse: let PlayerInput switch schemes again.
        foreach (var pi in PlayerInput.all) pi.neverAutoSwitchControlSchemes = false;
        if (pad != null) { InputSystem.RemoveDevice(pad); pad = null; }
    }

    void HoldGamepadScheme()
    {
        if (pad == null) return;
        foreach (var pi in PlayerInput.all)
        {
            if (pi.currentControlScheme == "Gamepad" && pi.devices.Contains(pad) && pi.devices.Count == 1) continue;
            // A PlayerInput without an input user yet (disabled, or mid scene load) throws "Invalid user"
            // on a scheme switch, which cut the rest of Update short every second.
            if (!pi.user.valid) continue;
            pi.neverAutoSwitchControlSchemes = true;
            pi.SwitchCurrentControlScheme("Gamepad", pad);
            Debug.Log("LUNA_INPUT " + pi.name + " on the Gamepad scheme with " + pad.name);
        }
    }

    static bool Pressed(InputDevice hand, InputFeatureUsage<bool> usage) => hand.TryGetFeatureValue(usage, out bool v) && v;

    // The game moves the body along its own facing (Player_Control_scr.PLMOVE: TransformDirection of the stick),
    // while the headset turns the view freely: turned around in the room, forward walked backwards (Felipe,
    // Build 95). The stick is turned by the head's yaw against the body, so forward is where the head looks.
    // Not on a ladder (gravity 0, not swimming: Ladder_scr climbs on vertical > 0.5) nor while frozen (menus,
    // scenes), where the stick keeps the game's meaning (LESSONS 35).
    static readonly System.Reflection.FieldInfo GravityField = PlayerType?.GetField("gravity");
    static readonly System.Reflection.FieldInfo SwimmingField = PlayerType?.GetField("Swimming");

    public static Vector2 HeadRelative(Vector2 stick, float yaw)
    {
        if (yaw == 0f || stick == Vector2.zero) return stick;
        float r = yaw * Mathf.Deg2Rad, c = Mathf.Cos(r), s = Mathf.Sin(r);
        return new Vector2(stick.x * c + stick.y * s, -stick.x * s + stick.y * c);
    }

    float MoveYaw()
    {
        if (player == null) return 0f;
        if (FreezeField != null && FreezeField.GetValue(player) is bool frozen && frozen) return 0f;
        bool swimming = SwimmingField != null && SwimmingField.GetValue(player) is bool sw && sw;
        if (!swimming && GravityField != null && GravityField.GetValue(player) is float g && g == 0f) return 0f;
        var tracker = HeadTracker();
        if (tracker == null) return 0f;
        var rot = tracker.transform.rotation;
        var look = rot * Vector3.forward;
        // Looking straight down or up, the top of the head points the way the face does (or away from it).
        if (new Vector2(look.x, look.z).sqrMagnitude < 0.01f) look = (look.y < 0f ? 1f : -1f) * (rot * Vector3.up);
        float headYaw = Mathf.Atan2(look.x, look.z) * Mathf.Rad2Deg;
        return Mathf.DeltaAngle(player.transform.eulerAngles.y, headYaw);
    }

    // Editor tests have no controllers: LunaProbe sets the left stick here (as LunaHeadTracker.TestPose sets the head).
    public static System.Func<Vector2?> TestLeftStick;

    void FeedPad()
    {
        if (pad == null) return;
        var left = InputDevices.GetDeviceAtXRNode(XRNode.LeftHand);
        var right = InputDevices.GetDeviceAtXRNode(XRNode.RightHand);
        left.TryGetFeatureValue(CommonUsages.primary2DAxis, out Vector2 leftStick);
        if (TestLeftStick?.Invoke() is Vector2 testStick) leftStick = testStick;
        leftStick = HeadRelative(leftStick, MoveYaw());
        // Triggers go over as on/off at the controller's own press point: the game's Fire is a Value
        // action and starts a swing on every change of an analog trigger.
        float leftTrigger = LunaTrigger.Held(left) ? 1f : 0f;
        float rightTrigger = LunaTrigger.Held(right) ? 1f : 0f;
        // The right trigger is the laser's click while a menu is open; on the pad it would also switch tabs.
        if (pointer != null && pointer.enabled) rightTrigger = 0f;
        // L/R HAND set to LEFT (SETT_LEFT_HAND = 1) mirrors the weapon to the left; the swing and the
        // guard follow it: fire on the left trigger, block on the right.
        if (LeftHanded()) { float t = leftTrigger; leftTrigger = rightTrigger; rightTrigger = t; }

        var buttons = new TouchButtons
        {
            A = Pressed(right, CommonUsages.primaryButton), B = Pressed(right, CommonUsages.secondaryButton),
            X = Pressed(left, CommonUsages.primaryButton), Y = Pressed(left, CommonUsages.secondaryButton),
            LeftGrip = Pressed(left, CommonUsages.gripButton), RightGrip = Pressed(right, CommonUsages.gripButton),
            Menu = Pressed(left, CommonUsages.menuButton),
            LeftStickClick = Pressed(left, CommonUsages.primary2DAxisClick), RightStickClick = Pressed(right, CommonUsages.primary2DAxisClick),
        };
        InputSystem.QueueStateEvent(pad, PadState(leftStick, leftTrigger, rightTrigger, buttons));

        if (!inputLogged && leftStick.magnitude > 0.3f) { inputLogged = true; LogInput(leftStick); }
        RumbleOnDamage(left, right);
        RumbleOnHit(LeftHanded() ? left : right);
    }

    // A melee swing that lands pulses the weapon hand: hard on something with health (an enemy, a
    // breakable), soft on a wall. The swing starts the weapon's cooldown (Weapon_scr.cooling, set in
    // OnFire); the hit is the game's own test, a SphereCast from the camera over WEP_REACH (Attack).
    static readonly System.Type HealthType = System.Type.GetType("OBJ_HEALTH, Assembly-CSharp");
    float lastCooling;

    void RumbleOnHit(InputDevice hand)
    {
        if (ControlType == null || control == null) return;
        var wep = ControlType.GetField("EQ_WEP")?.GetValue(control) as Component;
        if (wep == null) { lastCooling = 0f; return; }
        var t = wep.GetType();
        float cooling = t.GetField("cooling")?.GetValue(wep) is float c ? c : 0f;
        bool swung = lastCooling <= 0f && cooling > 0.15f;
        lastCooling = cooling;
        if (!swung || !(t.GetField("type")?.GetValue(wep) is int type) || type != 0) return;
        var cam = Camera.main;
        if (cam == null) return;
        float reach = t.GetField("WEP_REACH")?.GetValue(wep) is float r ? r : 2f;
        int mask = t.GetField("Mask")?.GetValue(wep) is LayerMask m ? m.value : ~0;
        if (!Physics.SphereCast(cam.transform.position, 0.1f, cam.transform.forward, out var hit, reach, mask)) return;
        bool alive = HealthType != null && hit.transform.GetComponentInParent(HealthType) != null;
        UnityEngine.XR.OpenXR.Input.OpenXRInput.SendHapticImpulse(hand, alive ? 0.8f : 0.3f, 0f, alive ? 0.12f : 0.06f);
    }

    // The game sends no rumble. A hit taken pulses both controllers, harder for a bigger share of the
    // health bar (CONTROL.CURRENT_PL_DATA.PLAYER_H against CONTROL.PLAYER_MAX_HP, read each frame).
    Component control;
    float lastHealth = -1f;
    bool rumbleLogged;

    void RumbleOnDamage(InputDevice left, InputDevice right)
    {
        if (ControlType == null) return;
        if (control == null) { control = (Component)FindObjectOfType(ControlType); lastHealth = -1f; if (control == null) return; }
        var data = ControlType.GetField("CURRENT_PL_DATA")?.GetValue(control);
        if (data == null) return;
        float hp = (float)data.GetType().GetField("PLAYER_H").GetValue(data);
        float max = ControlType.GetField("PLAYER_MAX_HP")?.GetValue(control) is float m && m > 0f ? m : 100f;
        if (lastHealth >= 0f && hp < lastHealth - 0.01f)
        {
            float share = Mathf.Clamp01((lastHealth - hp) / max);
            float amp = Mathf.Lerp(0.35f, 1f, share * 4f);
            float dur = Mathf.Lerp(0.08f, 0.3f, share * 4f);
            // InputDevice.SendHapticImpulse did nothing on the Quest under OpenXR (Build 73): go through
            // the OpenXR plugin's own call, which takes the same XR device.
            UnityEngine.XR.OpenXR.Input.OpenXRInput.SendHapticImpulse(left, amp, 0f, dur);
            UnityEngine.XR.OpenXR.Input.OpenXRInput.SendHapticImpulse(right, amp, 0f, dur);
            if (!rumbleLogged) { rumbleLogged = true; Debug.Log("LUNA_INPUT rumble on hit amp=" + amp.ToString("F2") + " left=" + left.isValid + " right=" + right.isValid); }
        }
        lastHealth = hp;
    }

    public struct TouchButtons { public bool A, B, X, Y, LeftGrip, RightGrip, Menu, LeftStickClick, RightStickClick; }

    // The Touch controllers as the game's gamepad. The right stick is not an input here: it only turns.
    // Game actions (MIDNIGHT_TEST): dpad up UseITEM, dpad right NextITEM, buttonNorth (Y) Swap.
    public static GamepadState PadState(Vector2 leftStick, float leftTrigger, float rightTrigger, TouchButtons b)
    {
        return new GamepadState { leftStick = leftStick, leftTrigger = leftTrigger, rightTrigger = rightTrigger }
            .WithButton(GamepadButton.South, b.A)
            .WithButton(GamepadButton.East, b.B)
            .WithButton(GamepadButton.West, b.X)
            .WithButton(GamepadButton.North, b.Y)
            .WithButton(GamepadButton.LeftShoulder, b.LeftGrip)
            .WithButton(GamepadButton.RightShoulder, b.RightGrip)
            .WithButton(GamepadButton.Select, b.Menu)
            .WithButton(GamepadButton.DpadRight, b.LeftStickClick)
            .WithButton(GamepadButton.DpadUp, b.RightStickClick);
    }

    // The game puts HANDS (weapon and hand) at the camera's position in its own Update. The head pose
    // reaches the camera at another point of the frame, so on some frames the weapon was placed from
    // the camera without the head offset and showed up beside itself, closer (a flickering second
    // sword). Right before rendering, with the head pose applied, the weapon is put back where the game
    // means it: camera position plus the game's HAND_offset.
    void PlaceHands() => PlaceHands(true);

    void PlaceHands(bool advance)
    {
        if (player == null || HandsField == null || HandOffsetField == null) return;
        if (!(HandsField.GetValue(player) is GameObject hands)) return;
        var tracker = HeadTracker();
        if (tracker == null) return;
        tracker.Apply();
        // The game sets HAND_offset in Start from where HANDS and HEAD stand, and Head_Bob pulled it to zero (plus
        // its bob) every physics step. Head_Bob is off in VR (the aim, LESSONS 27), and after a new game's opening the
        // offset was left at about (0.1, 1.0, 0): the sword floated a metre above the head (Felipe, Build 91; LESSONS 28).
        // Zero, as Head_Bob kept it with no bob; the game reads it too (Player_Control_scr.Hand).
        var offset = (Vector3)HandOffsetField.GetValue(player);
        if (offset.sqrMagnitude > 1e-6f)
        {
            if (!handOffsetLogged) { handOffsetLogged = true; Debug.Log("LUNA_PERF hand offset " + offset.ToString("F3") + " from the game, held at zero"); }
            HandOffsetField.SetValue(player, Vector3.zero);
            offset = Vector3.zero;
        }
        var target = tracker.transform.position + offset;
        float jump = Vector3.Distance(hands.transform.position, target);
        if (advance && jump > 0.03f) { handJumps++; handJumpWorst = Mathf.Max(handJumpWorst, jump); }
        var oldPos = hands.transform.position;
        var oldRot = hands.transform.rotation;
        hands.transform.position = target;
        // Classic mode: the game turns HANDS toward its own look (HEAD pitch, body yaw), which in VR
        // stays put while the headset turns, so the weapon pointed away from where the hit goes (the
        // camera's forward). Aim it with the headset instead, yaw and pitch, no roll, with the game's
        // own smoothing (Slerp at a speed proportional to the angle left, Player_Control_scr.Hand).
        var look = tracker.transform.rotation.eulerAngles;
        var want = Quaternion.Euler(look.x, look.y, 0f);
        if (!handAimSet) { handAim = want; handAimSet = true; }
        float magni = Quaternion.Angle(handAim, want) * 0.25f;
        if (advance) handAim = Quaternion.Slerp(handAim, want, Mathf.Clamp01(Time.smoothDeltaTime * magni));
        hands.transform.rotation = handAim;
        CarryLines(hands, oldPos, oldRot);
        if (Time.unscaledTime >= nextHandLog && handJumps > 0)
        {
            Debug.Log("LUNA_PERF hands re-placed " + handJumps + " times, worst " + handJumpWorst.ToString("F2") + " m");
            nextHandLog = Time.unscaledTime + 10f; handJumps = 0; handJumpWorst = 0f;
        }
    }

    // While a game menu has the player frozen (inventory, pause, dialogs), the laser points at the HUD.
    void PointAtMenus()
    {
        var head = HeadTracker();
        bool menu = player != null && head != null && FreezeField != null && (bool)FreezeField.GetValue(player)
                    && huds.Exists(h => h != null && h.gameObject.activeInHierarchy);
        if (!menu)
        {
            if (pointer != null && pointer.enabled) pointer.enabled = false;
            return;
        }
        if (pointer == null)
        {
            pointer = gameObject.AddComponent<LunaVRPointer>();
            pointer.RayToPixel = HudPixel;
            pointer.PickAt = HudElementAt;
        }
        // Controller poses share the head's tracking space: the tracked camera's parent plus its offset.
        pointer.Origin = head.transform.parent != null ? head.transform.parent : transform;
        pointer.OriginOffset = head.BasePosition;
        pointer.Layer = huds.Find(h => h != null).gameObject.layer;
        if (!pointer.enabled) pointer.enabled = true;
        HideStrayCursor();
    }

    // On the PC the level-load fade covers the whole screen, menus included. Here the fade is on the view layer
    // and the panel stays in front of it, so LOADING appeared over the warp map's buttons (Felipe). A loading
    // level always ends in a new scene, so the open menus simply stop drawing and catching the laser.
    static readonly System.Type LevelLoadType = System.Type.GetType("Level_Load_Effect, Assembly-CSharp");
    static readonly string[] MenuPanels = { "HUD/CRYSTAL", "HUD/MAIN", "HUD/MERCHANT", "HUD/QUERY" };

    void HideMenusWhileLoading()
    {
        if (LevelLoadType == null || FindObjectOfType(LevelLoadType) == null) return;
        foreach (var h in huds)
        {
            if (h == null) continue;
            foreach (var path in MenuPanels)
            {
                var panel = h.Find(path);
                if (panel == null) continue;
                var group = panel.GetComponent<CanvasGroup>();
                if (group == null) group = panel.gameObject.AddComponent<CanvasGroup>();
                group.alpha = 0f;
                group.blocksRaycasts = false;
            }
        }
    }

    // The game's selection cursor (the violet box, HUD/SELECT) goes to whatever the EventSystem has selected.
    // Pages with no button of their own leave a button of a hidden page selected, and the box stayed there,
    // floating with nothing under it (Felipe's photos; the probe saw it on an inactive InputField).
    readonly List<UnityEngine.UI.Image> selectCursors = new List<UnityEngine.UI.Image>();

    void HideStrayCursor()
    {
        if (selectCursors.Count == 0 || selectCursors.Exists(c => c == null))
        {
            selectCursors.Clear();
            foreach (var h in huds)
                if (h != null) selectCursors.AddRange(h.GetComponentsInChildren<UnityEngine.UI.Image>(true).Where(i => i.name == "SELECT"));
        }
        var selected = EventSystem.current != null ? EventSystem.current.currentSelectedGameObject : null;
        bool show = selected != null && selected.activeInHierarchy;
        foreach (var c in selectCursors) if (c.enabled != show) c.enabled = show;
    }

    // Topmost raycast-target element of the open panel under a world point: the rect test done in 3D,
    // skipping elements clipped by a scroll view or in a group that blocks no raycasts.
    GameObject HudElementAt(Vector3 point)
    {
        UnityEngine.UI.Graphic best = null;
        foreach (var rt in huds)
        {
            if (rt == null || !rt.gameObject.activeInHierarchy) continue;
            foreach (var g in rt.GetComponentsInChildren<UnityEngine.UI.Graphic>())
            {
                if (!g.raycastTarget || !g.enabled || g.depth < 0 || g.canvasRenderer.cull) continue;
                // The pop-up line, 900 wide across the panel since Build 82, is drawn over everything: it took
                // the middle of the buttons under it and left only their edges (YES/NO, ITEM2, WEP2, MAG2...).
                // It is skipped whole, because TMP adds a submesh child when the line has an icon.
                if (popCentred != null && g.transform.IsChildOf(popCentred.transform)) continue;
                // The selection cursor lies over the selected button, and CRYSTAL/SELECT is a raycast target.
                if (g.name == "SELECT") continue;
                if (best != null && g.depth <= best.depth) continue;
                if (!g.rectTransform.rect.Contains((Vector2)g.rectTransform.InverseTransformPoint(point))) continue;
                if (Clipped(g.transform, point) || Blocked(g.transform)) continue;
                best = g;
            }
        }
        return best != null ? best.gameObject : null;
    }

    static bool Clipped(Transform t, Vector3 point)
    {
        for (var p = t.parent; p != null; p = p.parent)
        {
            if (p.GetComponent<UnityEngine.UI.RectMask2D>() == null && p.GetComponent<UnityEngine.UI.Mask>() == null) continue;
            var r = (RectTransform)p;
            if (!r.rect.Contains((Vector2)r.InverseTransformPoint(point))) return true;
        }
        return false;
    }

    static bool Blocked(Transform t)
    {
        for (var p = t; p != null; p = p.parent)
        {
            var group = p.GetComponent<CanvasGroup>();
            if (group == null) continue;
            if (!group.blocksRaycasts) return true;
            if (group.ignoreParentGroups) return false;
        }
        return false;
    }

    // The laser's hit on the panel, plus its screen point for the pointer events.
    bool HudPixel(Ray ray, out Vector2 pixel, out Vector3 hit)
    {
        pixel = default; hit = default;
        var cam = Camera.main;
        if (cam == null) return false;
        foreach (var rt in huds)
        {
            if (rt == null || !rt.gameObject.activeInHierarchy) continue;
            var plane = new Plane(-rt.forward, rt.position);
            if (!plane.Raycast(ray, out float d)) continue;
            var p = ray.GetPoint(d);
            if (!rt.rect.Contains((Vector2)rt.InverseTransformPoint(p))) continue;
            hit = p;
            pixel = cam.WorldToScreenPoint(p);
            return true;
        }
        return false;
    }

    // Follow rather than parent: some game canvases survive scene loads and the body does not. The
    // panel keeps its distance from the eyes every frame (no lag while walking); only its direction
    // eases after the head (health and mana bars), so a glance moves it a little and a turn brings it
    // back in front.
    LunaHandsEarly handsEarly;
    public void PlaceHandsEarly() => PlaceHands(false);

    void LateUpdate()
    {
        if (handsEarly == null) { handsEarly = gameObject.AddComponent<LunaHandsEarly>(); handsEarly.Gameplay = this; }
        LogMovement();
        CommitTeleport();
        PlaceReticle();
        LogSpellFlight();
        // After the game's own Update: its settings page rewrites these texts and slider every frame
        // while one is dragged ("FOV [ 59 ]", "TURN [ NO ]" in Build 75).
        RelabelTurnSettings();
        var tracker = HeadTracker();
        if (player == null || tracker == null) return;
        huds.RemoveAll(h => h == null);
        if (huds.Count == 0) return;
        var head = tracker.transform;
        if (!hudGazeSet) { hudGaze = head.rotation; hudGazeSet = true; }
        // With a menu open the panel holds still so the laser can aim at it.
        bool menuOpen = pointer != null && pointer.enabled;
        if (!menuOpen) hudGaze = Quaternion.Slerp(hudGaze, head.rotation, 1f - Mathf.Exp(-HudFollowRate * Time.unscaledDeltaTime));
        var pos = head.position + hudGaze * new Vector3(0f, -HudDrop, HudDistance);
        var rot = Quaternion.LookRotation(pos - head.position, hudGaze * Vector3.up);
        foreach (var rt in huds)
        {
            rt.position = pos;
            rt.rotation = rot;
        }
        DrawViewOverlays(head, huds[0].gameObject.layer);
        PlaceHudParticles();
    }

    // One-time report of what the Input System sees: devices with their usages and each PlayerInput's
    // scheme and paired devices, plus the game's Move action value while the left stick is pushed
    // (it should follow the stick through LunaTouchPad).
    static void LogInput(Vector2 stick)
    {
        foreach (var d in InputSystem.devices)
            Debug.Log("LUNA_INPUT device " + d.layout + " '" + d.name + "' usages=" + string.Join(",", d.usages.Select(u => u.ToString())));
        foreach (var pi in PlayerInput.all)
        {
            var move = pi.actions != null ? pi.actions.FindAction("Move") : null;
            Debug.Log("LUNA_INPUT playerinput " + pi.name + " map=" + pi.currentActionMap?.name + " scheme=" + pi.currentControlScheme
                + " devices=" + string.Join(",", pi.devices.Select(d => d.name))
                + " move=" + (move != null ? move.ReadValue<Vector2>().ToString() : "none") + " xrstick=" + stick);
        }
    }

    // The player has more than one camera (CAM1, CAM2 with the screen effects). Every camera that
    // draws to the headset gets the head pose, except cameras under another camera (they inherit it).
    void TrackHeadOnGameCameras()
    {
        foreach (var c in Camera.allCameras)
        {
            if (c.targetTexture != null || c.stereoTargetEye == StereoTargetEyeMask.None) continue;
            if (c.GetComponent<LunaHeadTracker>() != null) continue;
            var parent = c.transform.parent;
            if (parent != null && parent.GetComponentInParent<Camera>(true) != null) continue;
            var tracker = c.gameObject.AddComponent<LunaHeadTracker>();
            Debug.Log("LUNA_PERF head tracking on " + c.name + (tracker.SceneCamera ? " (scene camera, the game's yaw kept)" : ""));
        }
    }

    // Turning with the right stick. Three of the game's settings steer the flat-screen camera, which
    // the headset replaces, so in VR they set the turn (saved with the game's settings):
    //   INVERT Y    -> TURN: "YES" (INVERT == -1) is smooth turn, otherwise snap;
    //   SENSITIVITY -> TURN SPEED (smooth only): SENS x 9 degrees a second (90 at the default 10);
    //   FOV         -> SNAP ANGLE (snap only): the slider (30..100) steps through SnapAngles.
    // The settings page shows only the row that applies to the chosen turn (RelabelTurnSettings).
    const float SmoothDeadzone = 0.2f, FovMin = 30f, FovMax = 100f;
    static readonly float[] SnapAngles = { 15f, 30f, 45f, 60f, 90f };
    const string SnapDefaultKey = "LunaVR_SnapAngle30";

    static int SnapIndex(float fov) => Mathf.Clamp(Mathf.RoundToInt((fov - FovMin) / (FovMax - FovMin) * (SnapAngles.Length - 1)), 0, SnapAngles.Length - 1);
    static float SnapFov(int index) => Mathf.Round(FovMin + (FovMax - FovMin) * index / (SnapAngles.Length - 1));

    object SysData()
    {
        if (ControlType == null) return null;
        if (control == null) control = (Component)FindObjectOfType(ControlType);
        return control != null ? ControlType.GetField("CURRENT_SYS_DATA")?.GetValue(control) : null;
    }

    void TurnSettings(out bool smooth, out float sens, out float snapAngle)
    {
        smooth = false; sens = 10f; snapAngle = 30f;
        var sys = SysData();
        if (sys == null) return;
        smooth = sys.GetType().GetField("INVERT")?.GetValue(sys) is int inv && inv == -1;
        if (sys.GetType().GetField("SENS")?.GetValue(sys) is float f && f > 0f) sens = f;
        if (sys.GetType().GetField("FOV")?.GetValue(sys) is float fov) snapAngle = SnapAngles[SnapIndex(fov)];
    }

    // The game's texts name keyboard and Xbox buttons: the tutorial line and the manual's controls
    // table (Gamepad column, one line per action of ManualData21). Every language gets the Touch
    // controller names, in English.
    static bool controlTextsPatched;
    static readonly (string term, string text)[] ControlTexts =
    {
        ("TutorialText1", "Press the Menu button (left controller) to open menus."),
        ("Manual/ManualData20", "Quest Touch\nHead / Right Stick\nLeft Stick\nRight Trigger\nLeft Trigger\nA\nB\nMenu (Left)\nLeft Grip\nRight Grip\nY\nX\nRight Stick Click\nLeft Stick Click"),
    };

    static void PatchControlTexts()
    {
        if (controlTextsPatched || I2.Loc.LocalizationManager.Sources.Count == 0) return;
        controlTextsPatched = true;
        int n = 0;
        foreach (var source in I2.Loc.LocalizationManager.Sources)
            foreach (var (term, text) in ControlTexts)
            {
                var data = source.GetTermData(term);
                if (data == null) continue;
                for (int i = 0; i < data.Languages.Length; i++) data.Languages[i] = text;
                n++;
            }
        I2.Loc.LocalizationManager.LocalizeAll(true);
        Debug.Log("LUNA_INPUT control texts patched: " + n);
    }

    bool LeftHanded() => SysData() is object sys && sys.GetType().GetField("SETT_LEFT_HAND")?.GetValue(sys) is int h && h == 1;

    // RESET SETTINGS (Menus case 16 -> Save.ResetSYS) restores the PC defaults: always run, FOV 65
    // (a 45 degree snap). Right after the game's own handler, put the VR defaults back: walk, snap 30.
    void ApplyVrDefaultsAfterReset()
    {
        var sys = SysData();
        var save = SaveType?.GetMethod("SAVE_SYSTEM", new[] { ControlType });
        if (sys == null || save == null) return;
        sys.GetType().GetField("SETTING_RUN")?.SetValue(sys, 1);
        sys.GetType().GetField("FOV")?.SetValue(sys, SnapFov(1));
        save.Invoke(null, new object[] { control });
        MenusType?.GetMethod("LoadText")?.Invoke(menus, new object[] { 1 });
        Debug.Log("LUNA_INPUT settings reset: VR defaults back (walk, snap 30)");
    }

    void HookResetButton()
    {
        foreach (var b in menus.GetComponentsInChildren<UnityEngine.UI.Button>(true))
            // menu3: the game's settings page; SETTINGS: the main menu's.
            if (b.name == "reset" && b.transform.parent != null && (b.transform.parent.name == "menu3" || b.transform.parent.name == "SETTINGS"))
            {
                b.onClick.AddListener(ApplyVrDefaultsAfterReset);
                Debug.Log("LUNA_INPUT reset button hooked");
            }
    }

    // First run of the port: the game's FOV default (65) would read as 45 degrees; start at 30.
    void SnapDefault()
    {
        if (PlayerPrefs.GetInt(SnapDefaultKey, 0) == 1 || SaveType == null) return;
        var sys = SysData();
        var fov = sys?.GetType().GetField("FOV");
        var save = SaveType.GetMethod("SAVE_SYSTEM", new[] { ControlType });
        if (fov == null || save == null) return;
        fov.SetValue(sys, SnapFov(1));
        save.Invoke(null, new object[] { control });
        PlayerPrefs.SetInt(SnapDefaultKey, 1);
        PlayerPrefs.Save();
        Debug.Log("LUNA_INPUT snap angle default 30 saved (FOV=" + SnapFov(1) + ")");
    }

    void Turn(float degrees)
    {
        var rot = (Vector3)RotField.GetValue(player);
        rot.y += degrees;
        RotField.SetValue(player, rot);
        if (OldRotField != null && OldRotField.FieldType == typeof(Vector3))
        {
            var old = (Vector3)OldRotField.GetValue(player);
            old.y += degrees;
            OldRotField.SetValue(player, old);
        }
        // The game eases the body toward ROT; land the turn this frame (one step for snap, no lag for smooth).
        player.transform.rotation = Quaternion.Euler(0f, rot.y, 0f);
    }

    void SnapTurn()
    {
        if (player == null || RotField == null) return;
        if (FreezeField != null && FreezeField.GetValue(player) is bool frozen && frozen) return;
        var hand = InputDevices.GetDeviceAtXRNode(XRNode.RightHand);
        if (!hand.TryGetFeatureValue(CommonUsages.primary2DAxis, out Vector2 stick)) return;
        TurnSettings(out bool smooth, out float sens, out float snapAngle);
        if (smooth)
        {
            snapped = false;
            float x = stick.x;
            if (Mathf.Abs(x) < SmoothDeadzone || Mathf.Abs(x) < Mathf.Abs(stick.y)) return;
            float push = (Mathf.Abs(x) - SmoothDeadzone) / (1f - SmoothDeadzone);
            Turn(Mathf.Sign(x) * push * Mathf.Clamp(sens * 9f, 30f, 360f) * Time.deltaTime);
            return;
        }
        if (snapped)
        {
            if (Mathf.Abs(stick.x) < ReleaseThreshold) snapped = false;
            return;
        }
        if (Mathf.Abs(stick.x) < SnapThreshold || Mathf.Abs(stick.x) < Mathf.Abs(stick.y)) return;
        snapped = true;
        Turn(Mathf.Sign(stick.x) * snapAngle);
    }

    // Settings rows with no meaning in the headset are hidden, label, value, arrows and slider: the
    // whole row is what sits at the label's height in its column. Settings (menu3): VIEW BOB (the
    // camera follows the head), GAMMA (a camera post effect that does not run in VR yet; back with the
    // screen filters), FULLSCREEN, SCREEN RESOLUTION and APPLY RESOLUTION. MORE (menu4): FPS CAP (the
    // headset runs at 72 Hz), LEGACY MODE and its note (tank controls turn the body with the stick),
    // REBIND CONTROLS (the port maps the Touch controllers), SCREEN SHAKE (Head_Bob shakes CAM, whose
    // pose the head tracker writes every frame: no effect in the headset). AESTHETIC (the screen
    // filters, post effects that do not run in VR yet): hidden until they do. The resolution's value
    // and arrows sit a row below their label, so the row rule missed them: they are named here.
    static readonly string[] HiddenRows = { "menu3/LABELS1/LAB_A", "menu3/LABELS1/LAB_D", "menu3/LABELS1/LAB_E", "menu3/LABELS2/B", "menu3/LABELS2/C",
                                            "menu4/LABELS1/G", "menu4/LABELS2/C", "menu4/LABELS2/D", "menu4/LABELS2/E" };
    static readonly string[] HiddenObjects = { "menu3/APPLY_RES", "menu3/FILTER_BUTTON", "menu3/REZ_BUTTON", "menu3/REZ_BUTTON2", "menu3/Settings2/C", "menu4/rebind" };
    // The main menu's settings page (ROOT/SETTINGS) is an older layout: one label text per column, a
    // line per row. Its value texts and controls are hidden by name; the label lines by index
    // (any language): LABELS1 "AESTHETIC / game volume / gamma", LABELS2 "quality / fullscreen".
    static readonly string[] HiddenTitleObjects = { "FILTER_BUTTON", "Settings", "GAMMA_SLIDER", "FULLSCREEN_BUTTON", "Settings2/Settings2B",
                                                    "LABELS3", "REZ_BUTTON", "REZ_BUTTON2", "Settings2/Settings2C", "APPLY_RES" };
    static readonly (string label, int[] lines)[] HiddenTitleLines = { ("LABELS1", new[] { 0, 2 }), ("LABELS2", new[] { 1 }) };
    readonly List<GameObject> hiddenSettings = new List<GameObject>();
    readonly List<(TMPro.TMP_Text text, int[] lines)> hiddenLines = new List<(TMPro.TMP_Text, int[])>();
    bool hiddenFound;

    void HideFlatScreenSettings()
    {
        if (!hiddenFound)
        {
            hiddenFound = true;
            hiddenSettings.Clear();
            hiddenLines.Clear();
            Transform main = null, title = null;
            foreach (var t in menus.GetComponentsInChildren<Transform>(true))
            {
                if (t.name == "MAIN" && main == null) main = t;
                else if (t.name == "SETTINGS" && t.parent != null && t.parent.name == "ROOT" && title == null) title = t;
            }
            if (title != null)
            {
                foreach (var path in HiddenTitleObjects) { var o = title.Find(path); if (o != null) hiddenSettings.Add(o.gameObject); }
                foreach (var (label, lines) in HiddenTitleLines)
                {
                    var o = title.Find(label);
                    var text = o != null ? o.GetComponent<TMPro.TMP_Text>() : null;
                    if (text != null) hiddenLines.Add((text, lines));
                }
            }
            if (main == null) return;
            foreach (var path in HiddenObjects) { var o = main.Find(path); if (o != null) hiddenSettings.Add(o.gameObject); }
            foreach (var path in HiddenRows)
            {
                var label = main.Find(path) as RectTransform;
                if (label == null) continue;
                var menu = main.Find(path.Split('/')[0]);
                hiddenSettings.Add(label.gameObject);
                Vector3 lp = menu.InverseTransformPoint(label.TransformPoint(label.rect.center));
                foreach (var g in menu.GetComponentsInChildren<UnityEngine.UI.Graphic>(true))
                {
                    var r = g.rectTransform;
                    if (r.rect.height > 90f || g.transform == label || g.transform.IsChildOf(label)) continue;
                    Vector3 gp = menu.InverseTransformPoint(r.TransformPoint(r.rect.center));
                    // Same row (height within a quarter row) and same column (label's side of the page).
                    if (Mathf.Abs(gp.y - lp.y) > 18f || Mathf.Sign(gp.x) != Mathf.Sign(lp.x) || gp.x < lp.x - 40f) continue;
                    var sel = g.GetComponentInParent<UnityEngine.UI.Selectable>(true);
                    // A text that only holds other rows' texts is never hidden whole: menu3/Settings sits at the
                    // AESTHETIC row and is the parent of the TURN and L/R HAND values (LESSONS 33). Its children
                    // are judged row by row like any other graphic.
                    if (sel == null && g.GetComponentsInChildren<UnityEngine.UI.Graphic>(true).Length > 1) continue;
                    var go = sel != null && sel.transform.IsChildOf(menu) && sel.transform != menu ? sel.gameObject : g.gameObject;
                    if (!hiddenSettings.Contains(go)) hiddenSettings.Add(go);
                }
            }
            Debug.Log("LUNA_INPUT settings hidden: " + string.Join(", ", hiddenSettings.Select(o => o.name)));
        }
        foreach (var go in hiddenSettings) if (go != null && go.activeSelf) go.SetActive(false);
        // Localisation can write the label back: blank the hidden lines whenever they show again.
        foreach (var (text, lines) in hiddenLines)
        {
            if (text == null || !text.gameObject.activeInHierarchy) continue;
            var parts = text.text.Split('\n');
            bool changed = false;
            foreach (int i in lines) if (i < parts.Length && parts[i].Length > 0) { parts[i] = ""; changed = true; }
            if (changed) text.text = string.Join("\n", parts);
        }
    }

    // The settings page's INVERT Y, SENSITIVITY and FOV rows, renamed to what they do in VR, with only
    // the row for the chosen turn shown.
    Component menus;
    TMPro.TMP_Text turnLabel, speedLabel;
    UnityEngine.UI.Slider speedSlider, fovSlider;

    public void SettingsPageWhileOff() => RelabelTurnSettings();

    void RelabelTurnSettings()
    {
        if (MenusType == null) return;
        if (menus == null) { menus = (Component)FindObjectOfType(MenusType); turnLabel = speedLabel = null; speedSlider = fovSlider = null; hiddenFound = false; if (menus == null) return; SnapDefault(); HookResetButton(); }
        if (turnLabel == null || speedLabel == null)
            foreach (var t in menus.GetComponentsInChildren<TMPro.TMP_Text>(true))
            {
                if (t.name == "LAB_F") turnLabel = t;
                else if (t.name == "LAB_C") speedLabel = t;
            }
        if (speedSlider == null || fovSlider == null)
            foreach (var sl in menus.GetComponentsInChildren<UnityEngine.UI.Slider>(true))
            {
                if (sl.name == "SENS_SLIDER") speedSlider = sl;
                else if (sl.name == "FOV_SLIDER") fovSlider = sl;
            }
        HideFlatScreenSettings();
        if (turnLabel == null || !turnLabel.gameObject.activeInHierarchy) return;
        TurnSettings(out bool smooth, out _, out float snapAngle);
        if (turnLabel.text != "TURN") turnLabel.text = "TURN";
        var txt = MenusType.GetField("TXT")?.GetValue(menus) as TMPro.TextMeshProUGUI[];
        if (txt != null && txt.Length > 6 && txt[6] != null && txt[6].transform.childCount >= 2)
        {
            var value = txt[6].transform.GetChild(1).GetComponent<TMPro.TMP_Text>();
            string want = smooth ? "[ SMOOTH ]" : "[ SNAP ]";
            if (value != null && value.text != want) value.text = want;
        }
        // Smooth: TURN SPEED. Snap: SNAP ANGLE, the FOV slider held on its steps.
        var fovText = txt != null && txt.Length > 8 ? txt[8] : null;
        if (speedLabel != null)
        {
            if (speedLabel.text != "TURN SPEED") speedLabel.text = "TURN SPEED";
            if (speedLabel.gameObject.activeSelf != smooth) speedLabel.gameObject.SetActive(smooth);
        }
        if (speedSlider != null && speedSlider.gameObject.activeSelf != smooth) speedSlider.gameObject.SetActive(smooth);
        if (fovSlider != null)
        {
            if (fovSlider.gameObject.activeSelf == smooth) fovSlider.gameObject.SetActive(!smooth);
            float step = SnapFov(SnapIndex(fovSlider.value));
            if (!smooth && !Mathf.Approximately(fovSlider.value, step)) fovSlider.value = step;
        }
        if (fovText != null)
        {
            if (fovText.gameObject.activeSelf == smooth) fovText.gameObject.SetActive(!smooth);
            // No degree sign: the game's menu font may not have the glyph.
            string want = "SNAP ANGLE [ " + snapAngle.ToString("0") + " ]";
            if (fovText.text != want) fovText.text = want;
        }
    }

    // Some HUD images carry their own material (additive glows beside menu entries, selection marks,
    // status glows). On the panel several drew as solid magenta, Unity's error colour: those whose
    // shader is unsupported, and the legacy particle shaders, go back to the default UI material with
    // the material's tint carried into the image colour.
    // Screen effects are full-screen HUD images: the status tint and the damage/pickup flash (FULL_COLOR,
    // FLASH_FADE: the GlowBox sprite, sliced, so only the screen edges glow), blindness (FULL_COLOR2, flat),
    // the scene fades (LEVEL_LOAD/FLASH). On the floating panel they would be a coloured
    // window. They stay culled there and are mirrored, sprite, slicing and all, on a view layer right in
    // front of the eyes that spans the field of view, so a vignette sits at the edges of sight.
    // FULL_COLOR starts 0 px high (an AspectRatioFitter sizes it on the first hit), so images with a
    // fitter count as screen effects whatever their size.
    const float ViewDistance = 0.3f, ViewMargin = 1.25f;
    readonly HashSet<UnityEngine.UI.Graphic> viewOverlays = new HashSet<UnityEngine.UI.Graphic>();
    readonly Dictionary<UnityEngine.UI.Graphic, UnityEngine.UI.Graphic> viewMirrors = new Dictionary<UnityEngine.UI.Graphic, UnityEngine.UI.Graphic>();
    readonly Dictionary<UnityEngine.UI.Graphic, Color> mirrorTint = new Dictionary<UnityEngine.UI.Graphic, Color>();
    RectTransform viewLayer;

    // Screen-sized art inside the game's menus (Menus.MENUS: MAIN, CRYSTAL with its warp map clouds
    // and MIST behind a mask, ROOT, DIALOG, MERCHANT; GAME is the playing HUD) belongs to the menu on
    // the panel, not to the view.
    static readonly System.Type MenusType = System.Type.GetType("Menus, Assembly-CSharp");
    static readonly System.Reflection.FieldInfo MenusField = MenusType?.GetField("MENUS");

    static bool InMenu(UnityEngine.UI.Graphic g)
    {
        if (MenusField == null) return false;
        var menus = g.GetComponentInParent(MenusType, true);
        if (menus == null) menus = g.canvas != null ? g.canvas.rootCanvas.GetComponentInChildren(MenusType, true) : null;
        if (menus == null) return false;
        foreach (var root in (GameObject[])MenusField.GetValue(menus))
            if (root != null && root.name != "GAME" && g.transform.IsChildOf(root.transform)) return true;
        return false;
    }

    static bool IsScreenEffect(UnityEngine.UI.Graphic g, Rect screen)
    {
        if (!(g is UnityEngine.UI.Image || g is UnityEngine.UI.RawImage)) return false;
        if (InMenu(g)) return false;
        if (g.GetComponent<UnityEngine.UI.AspectRatioFitter>() != null) return true;
        var r = g.rectTransform.rect;
        return r.width >= screen.width * 0.95f && r.height >= screen.height * 0.95f;
    }

    void DrawViewOverlays(Transform head, int layer)
    {
        foreach (var dead in viewMirrors.Keys.Where(g => g == null).ToList())
        {
            if (viewMirrors[dead] != null) Destroy(viewMirrors[dead].gameObject);
            viewMirrors.Remove(dead);
        }
        viewOverlays.RemoveWhere(g => g == null);
        if (viewOverlays.Count == 0) return;
        var cam = Camera.main;
        if (viewLayer == null)
        {
            var go = new GameObject("LunaViewLayer");
            DontDestroyOnLoad(go);
            var canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.sortingOrder = 32767;
            viewLayer = (RectTransform)go.transform;
        }
        viewLayer.gameObject.SetActive(true);
        // The layer has the source canvas's width in UI units and the eye's aspect, scaled so that width
        // covers the horizontal field of view at ViewDistance. The PC screen maps to the HUD panel's
        // angular size inside it (screenFrac of the layer width), so effects line up with the HUD.
        // The headset's eye frusta are asymmetric and wider than Camera.fieldOfView (the outer and
        // lower sides reach further): sized from fieldOfView, the layer's edge showed as a hard line
        // where a vignette is strongest. Take the widest tangent of both eyes' projections instead.
        float tanX = 0f, tanY = 0f;
        if (cam != null && cam.stereoEnabled)
        {
            foreach (var eye in new[] { Camera.StereoscopicEye.Left, Camera.StereoscopicEye.Right })
            {
                var p = cam.GetStereoProjectionMatrix(eye);
                if (p.m00 <= 0f || p.m11 <= 0f) continue;
                tanX = Mathf.Max(tanX, (1f + Mathf.Abs(p.m02)) / p.m00);
                tanY = Mathf.Max(tanY, (1f + Mathf.Abs(p.m12)) / p.m11);
            }
        }
        if (tanY <= 0f)
        {
            tanY = Mathf.Tan((cam != null ? cam.fieldOfView : 90f) * Mathf.Deg2Rad * 0.5f);
            tanX = tanY * (cam != null && cam.aspect > 0.1f ? cam.aspect : 1f);
        }
        float viewH = 2f * ViewDistance * tanY * ViewMargin;
        float viewW = 2f * ViewDistance * tanX * ViewMargin;
        float aspect = viewW / viewH;
        screenFrac = Mathf.Min(1f, HudWidth * ViewDistance / HudDistance / viewW);
        foreach (var g in viewOverlays)
        {
            // The panel's RectMask2D sets cull on every maskable child each frame, which brought the
            // originals back on the panel (a lopsided glow inside the vignette): keep it off them.
            if (g is UnityEngine.UI.MaskableGraphic mg && mg.maskable) mg.maskable = false;
            g.canvasRenderer.cull = true;
            var src = g.canvas != null ? g.canvas.rootCanvas : null;
            if (src == null) continue;
            var srcRect = ((RectTransform)src.transform).rect;
            float unitsW = srcRect.width, unitsH = srcRect.width / aspect;
            viewLayer.sizeDelta = new Vector2(unitsW, unitsH);
            viewLayer.localScale = Vector3.one * (viewW / unitsW);
            screenAspect = srcRect.height / Mathf.Max(1f, srcRect.width);
            if (!viewMirrors.TryGetValue(g, out var m) || m == null)
            {
                var mgo = new GameObject("Mirror_" + g.name, typeof(RectTransform));
                mgo.transform.SetParent(viewLayer, false);
                m = g is UnityEngine.UI.RawImage ? (UnityEngine.UI.Graphic)mgo.AddComponent<UnityEngine.UI.RawImage>() : mgo.AddComponent<UnityEngine.UI.Image>();
                m.raycastTarget = false;
                m.enabled = false;
                // Same rule as the panel: a supported material is kept; legacy particle ones (MIST's
                // additive EffCloud) fall back to the UI default with their tint folded into a colour.
                var sm = g.material;
                if (sm != null && sm != g.defaultMaterial && sm.shader != null)
                {
                    string sh = sm.shader.name;
                    if (sm.shader.isSupported && !sh.StartsWith("Legacy Shaders/Particles") && !sh.StartsWith("Mobile/Particles")) m.material = sm;
                    else if (sm.HasProperty("_TintColor"))
                    {
                        var tint = sm.GetColor("_TintColor");
                        mirrorTint[m] = new Color(Mathf.Min(1f, tint.r * 2f), Mathf.Min(1f, tint.g * 2f), Mathf.Min(1f, tint.b * 2f), Mathf.Min(1f, tint.a * 2f));
                    }
                }
                viewMirrors[g] = m;
                // Hide the original on the panel for good: culling alone did not hold for FLASH_FADE (a
                // hard-edged red frame over the vignette). A UI material that writes no colour does.
                if (HiddenUiMaterial() is Material hidden) g.material = hidden;
                Debug.Log("LUNA_PERF view layer mirror " + g.name + " sprite=" + ((g as UnityEngine.UI.Image)?.sprite?.name ?? "-") + " material=" + (sm != null ? sm.name + "/" + sm.shader?.name : "-"));
            }
            m.gameObject.layer = layer;
            bool on = g.isActiveAndEnabled;
            var c = g.color;
            c.a *= g.canvasRenderer.GetInheritedAlpha();
            bool was = m.enabled;
            m.enabled = on && c.a > 0.001f;
            if (m.enabled && !was)
                Debug.Log("LUNA_PERF view layer on " + g.name + " colour=" + c + " layer=" + layer + " at=" + viewLayer.position
                          + " head=" + head.position + " scale=" + viewLayer.localScale.x + " size=" + viewLayer.sizeDelta + " fov=" + (cam != null ? cam.fieldOfView : -1f) + " view=" + viewW + "x" + viewH + " screenFrac=" + screenFrac
                          + " camMask=" + (cam != null ? cam.cullingMask : 0) + " near=" + (cam != null ? cam.nearClipPlane : -1f));
            if (!m.enabled) { EdgeFill(m, false, 0f, layer); continue; }
            m.color = mirrorTint.TryGetValue(m, out var mt) ? c * mt : c;
            bool glow = false;
            if (g is UnityEngine.UI.Image si && m is UnityEngine.UI.Image mi)
            {
                mi.sprite = si.sprite;
                mi.type = si.type;
                mi.fillCenter = si.fillCenter;
                mi.pixelsPerUnitMultiplier = si.pixelsPerUnitMultiplier;
                // A sliced glow (GlowBox) is drawn over the PC screen's area only, border scaled with
                // it, exactly as on the monitor; the view outside that area takes the sprite's outer
                // edge colour (fully opaque) so the glow carries on past the edge of sight. Stretching
                // the border over the whole view instead bent it out of shape (the view is not 16:9).
                glow = si.type == UnityEngine.UI.Image.Type.Sliced && si.sprite != null && si.sprite.border.x > 0f;
                if (glow) mi.pixelsPerUnitMultiplier = si.pixelsPerUnitMultiplier / Mathf.Max(0.01f, screenFrac);
                mi.preserveAspect = si.preserveAspect;
            }
            else if (g is UnityEngine.UI.RawImage sr && m is UnityEngine.UI.RawImage mr)
            {
                mr.texture = sr.texture;
                mr.uvRect = sr.uvRect;
            }
            var mrt = m.rectTransform;
            var r = g.rectTransform.rect;
            if (glow)
            {
                mrt.anchorMin = mrt.anchorMax = new Vector2(0.5f, 0.5f);
                mrt.sizeDelta = new Vector2(unitsW, unitsW * screenAspect) * screenFrac;
                mrt.anchoredPosition = Vector2.zero;
            }
            else if (r.width >= srcRect.width * 0.95f || g.GetComponent<UnityEngine.UI.AspectRatioFitter>() != null)
            {
                // Screen-wide: fill the view, as it fills the monitor on PC.
                mrt.anchorMin = Vector2.zero; mrt.anchorMax = Vector2.one;
                mrt.sizeDelta = Vector2.zero; mrt.anchoredPosition = Vector2.zero;
            }
            else
            {
                mrt.anchorMin = mrt.anchorMax = new Vector2(0.5f, 0.5f);
                mrt.sizeDelta = r.size * screenFrac;
                mrt.anchoredPosition = (Vector2)src.transform.InverseTransformPoint(g.rectTransform.TransformPoint(r.center)) * screenFrac;
            }
            mrt.localRotation = Quaternion.identity;
            EdgeFill(m, glow, unitsW * 2f, layer);
        }
        viewLayer.gameObject.layer = layer;
        viewLayer.SetPositionAndRotation(head.position + head.forward * ViewDistance, head.rotation);
    }

    static Material hiddenUi;

    static Material HiddenUiMaterial()
    {
        if (hiddenUi == null)
        {
            var sh = Shader.Find("UI/Default");
            if (sh == null) return null;
            hiddenUi = new Material(sh) { name = "Luna hidden on panel" };
            hiddenUi.SetFloat("_ColorMask", 0f);
        }
        return hiddenUi;
    }

    // Four plain bands around a glow mirror, out to beyond the view: left and right span the full
    // height, top and bottom the mirror's width.
    readonly Dictionary<UnityEngine.UI.Graphic, UnityEngine.UI.Image[]> edgeFills = new Dictionary<UnityEngine.UI.Graphic, UnityEngine.UI.Image[]>();

    void EdgeFill(UnityEngine.UI.Graphic m, bool on, float extent, int layer)
    {
        if (!edgeFills.TryGetValue(m, out var bands))
        {
            if (!on) return;
            bands = new UnityEngine.UI.Image[4];
            for (int i = 0; i < 4; i++)
            {
                var b = new GameObject("Edge" + i, typeof(RectTransform)).AddComponent<UnityEngine.UI.Image>();
                b.transform.SetParent(m.transform, false);
                b.raycastTarget = false;
                var rt = b.rectTransform;
                switch (i)
                {
                    case 0: rt.anchorMin = new Vector2(0f, 0f); rt.anchorMax = new Vector2(0f, 1f); rt.pivot = new Vector2(1f, 0.5f); break;
                    case 1: rt.anchorMin = new Vector2(1f, 0f); rt.anchorMax = new Vector2(1f, 1f); rt.pivot = new Vector2(0f, 0.5f); break;
                    case 2: rt.anchorMin = new Vector2(0f, 1f); rt.anchorMax = new Vector2(1f, 1f); rt.pivot = new Vector2(0.5f, 0f); break;
                    default: rt.anchorMin = new Vector2(0f, 0f); rt.anchorMax = new Vector2(1f, 0f); rt.pivot = new Vector2(0.5f, 1f); break;
                }
                rt.anchoredPosition = Vector2.zero;
                bands[i] = b;
            }
            edgeFills[m] = bands;
        }
        foreach (var b in bands)
        {
            if (b == null) continue;
            b.enabled = on;
            if (!on) continue;
            b.gameObject.layer = layer;
            b.color = m.color;
            int i = System.Array.IndexOf(bands, b);
            b.rectTransform.sizeDelta = i < 2 ? new Vector2(extent, extent * 2f) : new Vector2(0f, extent);
        }
    }

    // Particle systems inside the HUD canvas: the hit blood (BLOODSS, BL_PART), the curse chains
    // (CHAIN), the water bubbles. On PC the canvas sits 50 m in front of CAM2 (65 degree field of view)
    // and these simulate locally with Local scaling, so a particle's size is startSize times the
    // system's own scale, unaffected by the canvas. On the floating panel the canvas scale shrank
    // their positions but not their sizes: the chains drew huge at the face, the blood far away. They
    // are placed on the view layer at their canvas position in the screen area, scaled by the screen
    // area's height over the PC screen height.
    struct HudParticle { public RectTransform canvas; public Vector3 pos; public Quaternion rot; public Vector3 scale; }
    readonly Dictionary<ParticleSystem, HudParticle> hudParticles = new Dictionary<ParticleSystem, HudParticle>();
    static readonly float PcScreenHeight = 2f * 50f * Mathf.Tan(65f * 0.5f * Mathf.Deg2Rad);
    float screenFrac = 1f, screenAspect = 0.5625f;

    void PlaceHudParticles()
    {
        if (viewLayer == null || hudParticles.Count == 0) return;
        foreach (var dead in hudParticles.Keys.Where(p => p == null).ToList()) hudParticles.Remove(dead);
        // The PC screen's height on the layer, in metres.
        float k = viewLayer.sizeDelta.x * screenFrac * screenAspect * viewLayer.lossyScale.x / PcScreenHeight;
        foreach (var kv in hudParticles)
        {
            var tr = kv.Key.transform;
            var h = kv.Value;
            if (h.canvas == null) continue;
            // Canvas units to view-layer units: both canvases share the source width.
            tr.SetPositionAndRotation(viewLayer.TransformPoint(new Vector3(h.pos.x, h.pos.y, 0f) * screenFrac), viewLayer.rotation * h.rot);
            var parentScale = tr.parent != null ? tr.parent.lossyScale : Vector3.one;
            // Local scaling uses only the system's own scale; Hierarchy/Shape modes would also take the
            // parents', so those keep the canvas-relative scale instead.
            float layerScale = viewLayer.lossyScale.x * screenFrac;
            tr.localScale = kv.Key.main.scalingMode == ParticleSystemScalingMode.Local ? h.scale * k
                : Vector3.Scale(h.scale, new Vector3(layerScale / Mathf.Max(1e-6f, parentScale.x), layerScale / Mathf.Max(1e-6f, parentScale.y), layerScale / Mathf.Max(1e-6f, parentScale.z)));
        }
    }

    // Diagnostics: every HUD graphic that shows, logged once (menus included, so a box that appears
    // in a menu is caught when it opens): path, rect, colour, texture, material.
    float nextHudDump;
    readonly HashSet<int> dumpedGraphics = new HashSet<int>();

    bool renderersDumped;

    void DumpHud()
    {
        // Once per scene: every renderer within 2 m of the head (the panel, the view layer and anything
        // else in front of the eyes), with its material, so a stray shape there can be named.
        var head = Camera.main != null ? Camera.main.transform : null;
        if (!renderersDumped && head != null)
        {
            renderersDumped = true;
            foreach (var r in FindObjectsOfType<Renderer>())
            {
                if (!r.enabled || !r.gameObject.activeInHierarchy || r is ParticleSystemRenderer) continue;
                if ((r.bounds.ClosestPoint(head.position) - head.position).magnitude > 2f) continue;
                string path = r.name;
                for (var t = r.transform.parent; t != null; t = t.parent) path = t.name + "/" + path;
                Debug.Log("LUNA_HUDDUMP renderer " + path + " type=" + r.GetType().Name + " bounds=" + r.bounds.center + "/" + r.bounds.size + " layer=" + r.gameObject.layer
                          + " material=" + (r.sharedMaterial != null ? r.sharedMaterial.name + "/" + r.sharedMaterial.shader?.name : "-"));
            }
            if (viewLayer != null)
                foreach (var g in viewLayer.GetComponentsInChildren<UnityEngine.UI.Graphic>())
                    if (g.isActiveAndEnabled) Debug.Log("LUNA_HUDDUMP view mirror " + g.name + " colour=" + g.color + " rect=" + g.rectTransform.rect + " at=" + g.rectTransform.anchoredPosition);
        }
        foreach (var rt in huds)
        {
            if (rt == null) continue;
            foreach (var g in rt.GetComponentsInChildren<UnityEngine.UI.Graphic>())
            {
                if (!g.isActiveAndEnabled || g.canvasRenderer.cull) continue;
                float a = g.color.a * g.canvasRenderer.GetInheritedAlpha();
                if (a <= 0.01f || !dumpedGraphics.Add(g.GetInstanceID())) continue;
                var r = g.rectTransform.rect;
                var c = rt.InverseTransformPoint(g.rectTransform.TransformPoint(r.center));
                string path = g.name;
                for (var t = g.transform.parent; t != null && t != rt; t = t.parent) path = t.name + "/" + path;
                var tex = g.mainTexture;
                Debug.Log("LUNA_HUDDUMP " + path + " at=" + (Vector2)c + " size=" + r.size + " colour=" + g.color + " alpha=" + a.ToString("0.00") + " type=" + g.GetType().Name
                          + " tex=" + (tex != null ? tex.name + "/" + tex.GetType().Name + "/" + tex.width + "x" + tex.height : "-")
                          + " material=" + (g.materialForRendering != null ? g.materialForRendering.name + "/" + g.materialForRendering.shader?.name + " supported=" + g.materialForRendering.shader?.isSupported : "-"));
            }
        }
    }

    // Images are also created while playing (the item pickup notice), so the panel is checked again
    // every HudMaterialInterval; only images not seen before are looked at.
    const float HudMaterialInterval = 0.25f;
    float nextHudMaterialCheck;
    readonly HashSet<int> seenGraphics = new HashSet<int>();
    readonly List<UnityEngine.UI.Graphic> graphics = new List<UnityEngine.UI.Graphic>();

    void ReplaceBrokenUiMaterials(Component canvas)
    {
        canvas.GetComponentsInChildren(true, graphics);
        var screen = ((RectTransform)canvas.transform).rect;
        foreach (var g in graphics)
        {
            if (!seenGraphics.Add(g.GetInstanceID())) continue;
            if (IsScreenEffect(g, screen))
            {
                viewOverlays.Add(g);
                Debug.Log("LUNA_PERF hud screen effect " + g.name + " drawn on the view layer");
                continue;
            }
            var m = g.material;
            // Inline text icons (<sprite=N> in the pickup notice) are TMP_SubMeshUI graphics made on the fly.
            if (g.GetType().Name == "TMP_SubMeshUI")
                Debug.Log("LUNA_PERF hud text icon " + g.transform.parent?.name + " material=" + (m != null ? m.name : "-") + " shader=" + (m?.shader != null ? m.shader.name + " supported=" + m.shader.isSupported : "-")
                          + " texture=" + (g.mainTexture != null ? g.mainTexture.name + " " + g.mainTexture.width + "x" + g.mainTexture.height : "-"));
            if (g.GetType().Name == "TMP_SubMeshUI" && m != null && (m.shader == null || !m.shader.isSupported || m.shader.name.StartsWith("Hidden/InternalErrorShader")))
            {
                // The icon material came up with Unity's error shader (a magenta square in the pickup
                // notice): give the sprite asset's material, and this instance, a working sprite shader.
                var ok = Shader.Find("TextMeshPro/Sprite");
                if (ok == null || !ok.isSupported) ok = Shader.Find("UI/Default");
                var asset = Member(g, "spriteAsset");
                var assetMat = Member(asset, "material") as Material;
                if (assetMat != null && ok != null) assetMat.shader = ok;
                if (ok != null) m.shader = ok;
                // TMP_SpriteAsset keeps the sheet and material in public fields, not properties.
                var sheet = Member(asset, "spriteSheet") as Texture;
                // The rip's sprite asset material came without its texture, and that is the material
                // TMP renders with: give the sheet to every material involved and to the renderer.
                if (sheet != null)
                {
                    m.mainTexture = sheet;
                    if (assetMat != null) assetMat.mainTexture = sheet;
                    if (g.materialForRendering != null) g.materialForRendering.mainTexture = sheet;
                    g.canvasRenderer.SetTexture(sheet);
                    g.SetMaterialDirty();
                }
                Debug.Log("LUNA_PERF hud text icon shader set to " + (ok != null ? ok.name : "none") + " sheet=" + (sheet != null ? sheet.name : "-"));
                continue;
            }
            if (m == null || m == g.defaultMaterial || m.shader == null) continue;
            string shader = m.shader.name;
            bool broken = !m.shader.isSupported || shader.StartsWith("Legacy Shaders/Particles") || shader.StartsWith("Mobile/Particles")
                          || shader.StartsWith("Hidden/InternalErrorShader");
            if (!broken) continue;
            // Additive glows (the level-up crystal art, selection marks, flares) are drawn on sprites
            // with an opaque black background: on the default, alpha-blended material that black showed
            // as a square. Keep them additive with the port's additive shader instead.
            if (shader.Contains("Additive") && AdditiveUiMaterial(m) is Material add)
            {
                g.material = add;
                Debug.Log("LUNA_PERF hud material made additive: " + g.name + " (" + m.name + ", " + shader + ")");
                continue;
            }
            if (m.HasProperty("_TintColor"))
            {
                var tint = m.GetColor("_TintColor");
                g.color *= new Color(Mathf.Min(1f, tint.r * 2f), Mathf.Min(1f, tint.g * 2f), Mathf.Min(1f, tint.b * 2f), Mathf.Min(1f, tint.a * 2f));
            }
            g.material = null;
            Debug.Log("LUNA_PERF hud material replaced: " + g.name + " (" + m.name + ", " + shader + ", supported=" + m.shader.isSupported + ")");
        }
    }

    // The port's stand-in for Shader Forge/Additive_Ignore_Fog (Blend SrcAlpha One, Cull Off, colour
    // 2 x vertex x _TintColor x _Color x texture) is the legacy Particles/Additive formula and is in the
    // build (FIX_SEL uses it). Two shaders carry that name; the stand-in is the one with _Color.
    Shader additiveUi;
    bool additiveUiLooked;
    readonly Dictionary<Material, Material> additiveCopies = new Dictionary<Material, Material>();

    Material AdditiveUiMaterial(Material src)
    {
        if (!additiveUiLooked)
        {
            additiveUiLooked = true;
            foreach (var sh in Resources.FindObjectsOfTypeAll<Shader>())
                if (sh.name == "Shader Forge/Additive_Ignore_Fog" && sh.isSupported && sh.FindPropertyIndex("_Color") >= 0) { additiveUi = sh; break; }
            Debug.Log("LUNA_PERF hud additive shader " + (additiveUi != null ? "found" : "missing"));
        }
        if (additiveUi == null) return null;
        if (additiveCopies.TryGetValue(src, out var copy) && copy != null) return copy;
        copy = new Material(additiveUi) { name = src.name + " (additive)" };
        copy.SetColor("_TintColor", src.HasProperty("_TintColor") ? src.GetColor("_TintColor") : new Color(0.5f, 0.5f, 0.5f, 1f));
        copy.SetColor("_Color", Color.white);
        if (src.mainTexture != null) copy.mainTexture = src.mainTexture;
        additiveCopies[src] = copy;
        return copy;
    }

    // Coffee SoftMask (the warp map's "flashlight" that lights the map around the cursor) only came
    // through the rip as placeholder shaders (Hidden/SoftMask, Hidden/UI/Default (SoftMaskable)): the
    // map drew as flat discs with noise at its edge. Turn the masks off so the lit map shows whole.
    void DisableSoftMasks(Component canvas)
    {
        foreach (var mb in canvas.GetComponentsInChildren<MonoBehaviour>(true))
        {
            if (mb == null) continue;
            var type = mb.GetType();
            if (type.Namespace == null || !type.Namespace.StartsWith("Coffee")) continue;
            string n = type.Name;
            if (n.StartsWith("SoftMask") && n != "SoftMaskable")
            {
                mb.enabled = false;
                var gr = mb.GetComponent<UnityEngine.UI.Graphic>();
                if (gr != null) gr.enabled = false;
                // What a soft mask holds shows only inside it: the warp map's flashlight (the lit map
                // around the selection), the mist streak at the map's foot. A soft-edged RectMask2D on
                // the mask's rect stands in (axis-aligned: the rotated mist streak gets its bounds).
                if (mb.GetComponent<UnityEngine.UI.RectMask2D>() == null)
                {
                    var clip = mb.gameObject.AddComponent<UnityEngine.UI.RectMask2D>();
                    var size = ((RectTransform)mb.transform).rect.size;
                    int soft = Mathf.RoundToInt(Mathf.Min(size.x, size.y) * 0.4f);
                    clip.softness = new Vector2Int(soft, soft);
                }
                Debug.Log("LUNA_PERF hud soft mask off: " + mb.name);
            }
            else if (n == "SoftMaskable") mb.enabled = false;
        }
    }

    // HUD images that show a render texture (the shop's turning item, RT_256): until a camera draws
    // into it, D3D11 gave a transparent texture and Vulkan an opaque black square. Start them clear.
    void ClearHudRenderTextures(Component canvas)
    {
        var done = new HashSet<RenderTexture>();
        foreach (var g in canvas.GetComponentsInChildren<UnityEngine.UI.Graphic>(true))
        {
            var tex = g is UnityEngine.UI.RawImage ri ? ri.texture : g.material != null && g.material != g.defaultMaterial ? g.material.mainTexture : null;
            if (!(tex is RenderTexture rtex) || !done.Add(rtex)) continue;
            if (!rtex.IsCreated()) rtex.Create();
            var prev = RenderTexture.active;
            RenderTexture.active = rtex;
            GL.Clear(true, true, new Color(0f, 0f, 0f, 0f));
            RenderTexture.active = prev;
            Debug.Log("LUNA_PERF hud render texture cleared: " + rtex.name + " (" + g.name + ")");
        }
    }

    static object Member(object o, string name)
    {
        if (o == null) return null;
        var t = o.GetType();
        const System.Reflection.BindingFlags F = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
        var p = t.GetProperty(name, F);
        if (p != null) return p.GetValue(o, null);
        return t.GetField(name, F)?.GetValue(o);
    }

    // Two "TMP Settings" assets sit in Resources folders: the game's (its own EmojiOne sprite asset,
    // 31 icons, the pickup notice's bag among them) and the TextMesh Pro package's (the stock 16
    // emoji). The player loaded the package's, so <sprite=3> drew a smiley. Point TMP's default
    // sprite asset at the game's: the one with the most sprites.
    static bool spriteAssetFixed;

    static void UseGameSpriteAsset()
    {
        if (spriteAssetFixed) return;
        spriteAssetFixed = true;
        var assetType = System.Type.GetType("TMPro.TMP_SpriteAsset, Unity.TextMeshPro");
        var settingsType = System.Type.GetType("TMPro.TMP_Settings, Unity.TextMeshPro");
        if (assetType == null || settingsType == null) { Debug.Log("LUNA_PERF tmp sprite asset: TMP types not found"); return; }
        Object best = null; int bestCount = -1;
        foreach (var a in Resources.LoadAll("", assetType))
        {
            var table = Member(a, "spriteCharacterTable") as System.Collections.ICollection ?? Member(a, "spriteInfoList") as System.Collections.ICollection;
            int n = table != null ? table.Count : 0;
            Debug.Log("LUNA_PERF tmp sprite asset " + a.name + " sprites=" + n);
            if (n > bestCount) { best = a; bestCount = n; }
        }
        var settings = settingsType.GetProperty("instance", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.Public)?.GetValue(null, null);
        var field = settingsType.GetField("m_defaultSpriteAsset", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public);
        if (settings != null && field != null && best != null)
        {
            field.SetValue(settings, best);
            Debug.Log("LUNA_PERF tmp default sprite asset set to " + best.name + " (" + bestCount + " sprites)");
        }
    }

    void AnchorHud()
    {
        UseGameSpriteAsset();
        var cam = Camera.main;
        foreach (var canvas in FindObjectsOfType<Canvas>())
        {
            if (!canvas.isRootCanvas || canvas.renderMode == RenderMode.WorldSpace) continue;
            // The game's software mouse cursor: a magenta square on the panel, and the laser replaces it.
            if (canvas.name == "MAUS_CANVAS") { canvas.enabled = false; continue; }
            var rt = (RectTransform)canvas.transform;
            Vector2 size = rt.sizeDelta.x > 1f ? rt.sizeDelta : new Vector2(1920f, 1080f);
            // The HUD's scaler (Scale With Screen Size, 1280x720, Expand) sized the canvas to the eye
            // buffer, nearly square (1280x1341): menus sat in the middle of a tall panel with marble
            // above and below. Lay it out as on a 16:9 monitor instead.
            var scaler = canvas.GetComponent<UnityEngine.UI.CanvasScaler>();
            if (scaler != null && scaler.uiScaleMode == UnityEngine.UI.CanvasScaler.ScaleMode.ScaleWithScreenSize)
            {
                var r = scaler.referenceResolution;
                size = new Vector2(Mathf.Max(r.x, r.y * 16f / 9f), Mathf.Max(r.y, r.x * 9f / 16f));
            }
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.worldCamera = cam;
            rt.sizeDelta = size;
            rt.localScale = Vector3.one * (HudWidth / size.x);
            ReplaceBrokenUiMaterials(canvas);
            DisableSoftMasks(canvas);
            ClearHudRenderTextures(canvas);
            // Tints and art wider than the screen (the inventory's lilac mask, 2600 px; menu borders,
            // 1500 px; the warp map clouds) fill the monitor edge to edge on PC. Clip the panel at
            // its edges, as the monitor does, instead of hiding them.
            if (canvas.GetComponent<UnityEngine.UI.RectMask2D>() == null) canvas.gameObject.AddComponent<UnityEngine.UI.RectMask2D>();
            huds.Add(rt);
            foreach (var ps in canvas.GetComponentsInChildren<ParticleSystem>(true))
            {
                if (hudParticles.ContainsKey(ps)) continue;
                var tr = ps.transform;
                hudParticles[ps] = new HudParticle { canvas = rt, pos = rt.InverseTransformPoint(tr.position),
                    rot = Quaternion.Inverse(rt.rotation) * tr.rotation, scale = tr.localScale };
            }
            Debug.Log("LUNA_PERF hud " + canvas.name + " follows the head");
        }
    }
}

// Trigger press with hysteresis on the analog value: pressed above 0.7, released below 0.35. The
// runtime's own press point flickered near the threshold, which read as several clicks.
public static class LunaTrigger
{
    const float Press = 0.7f, Release = 0.35f;
    static readonly Dictionary<ulong, bool> held = new Dictionary<ulong, bool>();

    public static bool Held(InputDevice hand)
    {
        if (!hand.isValid || !hand.TryGetFeatureValue(CommonUsages.trigger, out float v)) return false;
        ulong key = (ulong)hand.characteristics;
        held.TryGetValue(key, out bool was);
        bool now = was ? v > Release : v > Press;
        held[key] = now;
        return now;
    }
}

// Puts the headset pose on a camera, relative to its parent (OpenXR does not track cameras by
// itself). Applied in Update and again just before rendering for the freshest pose.
// Runs before every game script: Head_Bob (on the same CAM) pulls the camera back towards the body and
// rolls it in FixedUpdate, and the game reads Camera.main in its Update (Magic_scr casts a spell from
// it). Applied after the game's Update, the spell left from that pose, not the head's, and landed off
// the aim mark (Felipe, Build 88 video). LunaProbe SpellAim.
[DefaultExecutionOrder(-1000)]
public class LunaHeadTracker : MonoBehaviour
{
    Vector3 basePosition;   // the camera's own offset under its parent (e.g. the player's HEAD)
    bool hasBase;
    public Vector3 BasePosition => basePosition;

    // A scene camera (not the player's) is aimed by the game: PITT_A1's opening (Opening/FIRST_SCENE,
    // SCENE_C.anim) turns it 38.6 degrees right and 17.7 down, at the hand coming out of the ground.
    // The head pose replaced that aim and the view faced the coffin. The yaw the game gives such a
    // camera is kept as the base the head turns from; its pitch and roll are not (the horizon stays
    // level). The game writes the rotation again each frame it animates it: a rotation that is not the
    // one written here last is the game's new aim.
    static readonly System.Type PlayerType = System.Type.GetType("Player_Control_scr, Assembly-CSharp");
    bool sceneCamera, written;
    public bool SceneCamera => sceneCamera;
    Quaternion aimYaw = Quaternion.identity, lastWritten;

    void OnEnable()
    {
        if (!hasBase)
        {
            basePosition = transform.localPosition;
            hasBase = true;
            sceneCamera = PlayerType != null && GetComponentInParent(PlayerType) == null;
        }
        Application.onBeforeRender += Apply;
    }

    void TakeGameAim()
    {
        if (!sceneCamera) return;
        var current = transform.localRotation;
        if (written && Quaternion.Angle(current, lastWritten) < 0.01f) return;
        float yaw = current.eulerAngles.y;
        var aim = Quaternion.Euler(0f, yaw, 0f);
        if (Quaternion.Angle(aim, aimYaw) > 1f) Debug.Log("LUNA_VR " + name + " aimed by the game: yaw " + yaw.ToString("F1"));
        aimYaw = aim;
    }
    void OnDisable() { Application.onBeforeRender -= Apply; }
    void Update() { Apply(); }

    // Software recentre: the headset's yaw and position at the last Recentre are taken off, so the
    // view faces the body's forward from there (the same as a system recentre).
    static Quaternion yawOffset = Quaternion.identity;
    static Vector3 positionOffset;
    static bool recentrePending;

    public static void Recentre() { recentrePending = true; }
    public static Quaternion YawOffset => yawOffset;
    public static Vector3 PositionOffset => positionOffset;

    // Editor tests only: a head pose in place of the headset's (LunaProbe SpellAim).
    public static System.Func<(Quaternion rot, Vector3 pos)?> TestPose;

    static bool HeadPose(out Quaternion r, out Vector3 p, out bool hasRotation)
    {
        var test = TestPose?.Invoke();
        if (test.HasValue) { r = test.Value.rot; p = test.Value.pos; hasRotation = true; return true; }
        var head = InputDevices.GetDeviceAtXRNode(XRNode.CenterEye);
        if (!head.isValid) head = InputDevices.GetDeviceAtXRNode(XRNode.Head);
        p = Vector3.zero;
        bool hasR = head.TryGetFeatureValue(CommonUsages.centerEyeRotation, out r) || head.TryGetFeatureValue(CommonUsages.deviceRotation, out r);
        bool hasP = head.TryGetFeatureValue(CommonUsages.centerEyePosition, out p) || head.TryGetFeatureValue(CommonUsages.devicePosition, out p);
        hasRotation = hasR;
        return hasR && hasP;
    }

    public void Apply()
    {
        TakeGameAim();
        if (!HeadPose(out Quaternion r, out Vector3 p, out bool hasRotation))
        {
            // Without a headset (the editor) the read fails and r is all zeros, which Unity turned into
            // "look straight ahead" every frame: only a real rotation is written.
            if (hasRotation) Write(aimYaw * yawOffset * r);
            return;
        }
        if (recentrePending)
        {
            recentrePending = false;
            yawOffset = Quaternion.Euler(0f, -r.eulerAngles.y, 0f);
            positionOffset = new Vector3(p.x, 0f, p.z);
            Debug.Log("LUNA_INPUT view recentred by " + (-r.eulerAngles.y).ToString("F0") + " degrees");
        }
        Write(aimYaw * yawOffset * r);
        transform.localPosition = basePosition + aimYaw * yawOffset * (p - positionOffset);
    }

    void Write(Quaternion rotation)
    {
        transform.localRotation = rotation;
        lastWritten = transform.localRotation;
        written = true;
    }
}
