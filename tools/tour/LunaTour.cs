// Scene tour: the same camera shots in the ORIGINAL PC game and in the Quest port, so the two
// can be compared picture by picture without playing.
//
// One file, two builds:
//   - PC (BepInEx 5, compiled with -define:BEPINEX): for each scene listed in BepInEx/tour/request.txt,
//     loads it, plans the shots (lights and transparent/alpha-tested renderers, with a camera spot
//     that has a clear line of sight) unless BepInEx/tour/plan_<scene>.txt already exists,
//     and saves every shot to BepInEx/tour/<scene>/pc_NN.png.
//   - Quest port (copied into the project by passes/pass_tour_runtime.py): for every
//     <persistentDataPath>/tour/plan_<scene>.txt, loads that scene and takes the same shots into
//     <persistentDataPath>/tour/<scene>/quest_NN.png; then writes all_done.txt and quits.
// Plans are plain text (one shot per line) because JsonUtility skips classes from a BepInEx DLL.
//
// Material coverage (rounds): on the PC each scene also writes materials_<key>.txt, every material on
// an active renderer. Every shot writes <prefix>_NN.mats.txt, the materials visible in it. When
// want_<key>.txt lists materials and no plan exists, the plan aims one shot at each of them.
// tools/tour/coverage.py scores the shots and writes the next round's want lists.
//
// Showcase: a plan whose shots have kind "prefab" spawns each named Resources prefab (weapons, items,
// broken enemy pieces, bodies, magic) far below the level with its scripts removed, frames it by its
// bounds under a fixed light and grey background, and shoots it. The plan's key (file name) can differ
// from its scene: plan_SHOWCASE.txt holds the host scene on its first line.
// A prefab shot's pos is (yaw, pitch, distance scale) of the camera around the model (all 0: the
// default three-quarter view); target.x is how many seconds its particles run (0: one).
//
// Enemies (key NPCS_<scene>, requested on the PC as NPCS_<scene>:<scene>): the plan is one set of
// "npc" shots per enemy kind in the scene. Every bone of an enemy carries its own OBJ_HEALTH (type 1
// hit zones, type 2 parts that break off); the enemy is the topmost animated object above them. Each
// is cloned into the showcase in its idle pose at frame 0, physics frozen, and shot in its states
// (euler.x): 0 whole, 1 broken (type-2 parts gone, their pieces spawned), 2 dead (every zone replaced
// by its DED piece), 3 fire, 4 ice, 5 poison. euler.y = 1 shoots on black (for additive and ghost
// materials), euler.z = 1 adds a warm point light (for the shaders' point-light passes). Game time is
// paused for showcase shots, so time-animated materials are at about the same moment on both games.
//
// Intro: shots of kind "intro" (in MainMenu) start the game's intro sequence the way the Start button
// does and shoot through the intro's own camera, untouched, at pos.x seconds after the start.
// Each scene logs its quality level and pixel light count (LUNA_TOUR quality ...).
// Shots render the world camera (or a plain one) into a fixed 1280x720 sRGB render texture, so
// screen size, window and stereo setup do not matter.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.SceneManagement;

public class LunaTourShot
{
    public string name;
    public string kind;
    public Vector3 target;
    public Vector3 pos;
    public Vector3 euler;
}

public class LunaTourPlan
{
    public string scene;
    public LunaTourShot[] shots;

    // Line 1: scene. Then: kind \t name \t target \t pos \t euler (vectors as "x y z").
    public string ToText()
    {
        var sb = new System.Text.StringBuilder(scene + "\n");
        foreach (var s in shots)
            sb.Append(s.kind).Append('\t').Append(s.name.Replace('\t', ' ')).Append('\t')
              .Append(V(s.target)).Append('\t').Append(V(s.pos)).Append('\t').Append(V(s.euler)).Append('\n');
        return sb.ToString();
    }

    public static LunaTourPlan FromText(string text)
    {
        var lines = text.Replace("\r", "").Split('\n').Where(l => l.Length > 0).ToArray();
        var shots = new List<LunaTourShot>();
        for (int i = 1; i < lines.Length; i++)
        {
            var f = lines[i].Split('\t');
            shots.Add(new LunaTourShot { kind = f[0], name = f[1], target = P(f[2]), pos = P(f[3]), euler = P(f[4]) });
        }
        return new LunaTourPlan { scene = lines[0].Trim(), shots = shots.ToArray() };
    }

    static string V(Vector3 v)
    {
        var c = System.Globalization.CultureInfo.InvariantCulture;
        return v.x.ToString("R", c) + " " + v.y.ToString("R", c) + " " + v.z.ToString("R", c);
    }

    static Vector3 P(string s)
    {
        var c = System.Globalization.CultureInfo.InvariantCulture;
        var p = s.Split(' ');
        return new Vector3(float.Parse(p[0], c), float.Parse(p[1], c), float.Parse(p[2], c));
    }
}

public class LunaTourRunner : MonoBehaviour
{
    const int Width = 1280, Height = 720, MaxShots = 24, MaxMaterialShots = 30;
    const float MinSpacing = 6f, SettleSeconds = 6f;
    const int MaxReloads = 6;
    // Fixed screens (the menu): one shot from where the game's own camera is, nothing else.
    static readonly string[] ViewOnlyScenes = { "MainMenu" };

    public string dir;        // folder holding plan.json / request and receiving the shots
    public string prefix;     // "pc" or "quest"
    public string scene;      // scene to plan (PC only, when no plan exists)
    public string key;        // plan / output name (the scene, or e.g. SHOWCASE)
    public bool quitWhenDone;
    public bool finished;
    public Action<string> log = Debug.Log;

    LunaTourPlan plan;

    public static LunaTourRunner Create(string dir, string prefix)
    {
        var go = new GameObject("LunaTour");
        DontDestroyOnLoad(go);
        var r = go.AddComponent<LunaTourRunner>();
        r.dir = dir;
        r.prefix = prefix;
        return r;
    }

    public void StartTour(LunaTourPlan existing)
    {
        plan = existing;
        StartCoroutine(Run());
    }

    IEnumerator Run()
    {
        string sceneName = plan != null ? plan.scene : scene;
        if (string.IsNullOrEmpty(key)) key = sceneName;
        log("LUNA_TOUR loading " + sceneName + " for " + key);
        SceneManager.LoadScene(sceneName);
        yield return null;
        yield return new WaitForSecondsRealtime(SettleSeconds);
        // HUD shots stand at the save's spot. On the Quest about one load in four put the player at the
        // new-game spawn instead (PITT_A1: by the coffins), where the opening scene takes the player
        // away (no Player_Control_scr): load again.
        for (int retry = 0; plan != null && plan.shots.Any(x => x.kind == "hud") && retry < 3
             && !FindObjectsOfType<MonoBehaviour>().Any(m => m.GetType().Name == "Player_Control_scr"); retry++)
        {
            log("LUNA_TOUR no player after loading " + sceneName + " for " + key + " (new-game spawn?), loading again");
            SceneManager.LoadScene(sceneName);
            yield return null;
            yield return new WaitForSecondsRealtime(SettleSeconds);
        }

        if (prefix == "pc" && key == sceneName) File.WriteAllText(Path.Combine(dir, "materials_" + key + ".txt"), MaterialInventory());
        if (plan == null)
        {
            string wantFile = Path.Combine(dir, "want_" + key + ".txt");
            var want = File.Exists(wantFile) ? new HashSet<string>(File.ReadAllLines(wantFile).Where(l => l.Length > 0)) : null;
            plan = new LunaTourPlan { scene = sceneName, shots = want != null ? PlanForMaterials(want)
                                                                 : key.StartsWith("NPCS_") ? PlanNpcs() : PlanShots() };
            File.WriteAllText(Path.Combine(dir, "plan_" + key + ".txt"), plan.ToText());
            log("LUNA_TOUR planned " + plan.shots.Length + " shots" + (want != null ? " for " + want.Count + " wanted materials" : ""));
        }

        // Diagnostic override: tour/pixel_lights.txt holding a number sets the pixel light count for this tour.
        string pixelLightsFile = Path.Combine(dir, "pixel_lights.txt");
        int pixelLights;
        if (File.Exists(pixelLightsFile) && int.TryParse(File.ReadAllText(pixelLightsFile).Trim(), out pixelLights))
            QualitySettings.pixelLightCount = pixelLights;
        log("LUNA_TOUR quality " + key + " level=" + QualitySettings.GetQualityLevel() + " (" + QualitySettings.names[QualitySettings.GetQualityLevel()]
            + ") pixelLights=" + QualitySettings.pixelLightCount + " shadows=" + QualitySettings.shadows + " lodBias=" + QualitySettings.lodBias);
        // The legacy ambient (UNITY_LIGHTMODEL_AMBIENT) the Shader Forge shaders light with, next to the scene's setting.
        log("LUNA_TOUR ambient " + key + " mode=" + RenderSettings.ambientMode + " light=" + RenderSettings.ambientLight
            + " intensity=" + RenderSettings.ambientIntensity + " glstate=" + Shader.GetGlobalVector("glstate_lightmodel_ambient"));
        log("LUNA_TOUR fog " + key + " on=" + RenderSettings.fog + " mode=" + RenderSettings.fogMode + " color=" + RenderSettings.fogColor
            + " start=" + RenderSettings.fogStartDistance + " end=" + RenderSettings.fogEndDistance + " density=" + RenderSettings.fogDensity);
        foreach (var l in FindObjectsOfType<Light>().Where(l => l.type == LightType.Directional))
            log("LUNA_TOUR sun " + key + " " + HierPath(l.transform) + " enabled=" + l.isActiveAndEnabled + " color=" + l.color
                + " intensity=" + l.intensity + " mode=" + l.renderMode + " mask=" + l.cullingMask + " euler=" + l.transform.eulerAngles);
        // The scene's ambient and fog come from Lighting_Zone triggers the player stands in: log where the
        // player is and which zone triggers hold it.
        var tagged = GameObject.FindGameObjectsWithTag("Player");
        log("LUNA_TOUR tagged " + key + " " + string.Join(", ", tagged.Select(g => HierPath(g.transform)).ToArray()));
        var control = FindObjectsOfType<MonoBehaviour>().FirstOrDefault(m => m.GetType().Name == "Player_Control_scr");
        var player = control != null ? control.gameObject : null;
        if (player != null)
        {
            var cols = player.GetComponentsInChildren<Collider>();
            log("LUNA_TOUR player " + key + " " + HierPath(player.transform) + " pos=" + player.transform.position
                + " colliders=" + string.Join(",", cols.Select(c => c.GetType().Name + (c.isTrigger ? "(trigger)" : "") + (c.enabled ? "" : "(off)")).ToArray())
                + " rigidbody=" + (player.GetComponentInParent<Rigidbody>() != null));
            foreach (var mb in FindObjectsOfType<MonoBehaviour>().Where(m => m.GetType().Name == "Lighting_Zone" || m.GetType().Name == "ShadowTower_CON"))
                foreach (var c in mb.GetComponents<Collider>())
                    if (c.bounds.Contains(player.transform.position))
                        log("LUNA_TOUR zone " + key + " " + mb.GetType().Name + " " + HierPath(mb.transform) + " holds the player");
        }
        frameLog = File.Exists(Path.Combine(dir, "frame_log.txt")) ? log : null;
        string outDir = Path.Combine(dir, key);
        Directory.CreateDirectory(outDir);
        float introStart = plan.shots.Any(x => x.kind == "intro") ? StartIntro() : -1f;
        // Showcase plans pause game time: time-animated materials then sit at the same moment on both games.
        float timeScale = Time.timeScale;
        if (plan.shots.All(x => x.kind == "npc" || x.kind == "prefab")) Time.timeScale = 0f;
        int reloads = 0;
        for (int i = 0; i < plan.shots.Length; i++)
        {
            // The player can die mid-tour (a fall into the TOWER abyss loads Gameover): reload the scene
            // and go on from this shot.
            if (plan.shots[i].kind != "intro" && SceneManager.GetActiveScene().name != sceneName && reloads < MaxReloads)
            {
                reloads++;
                log("LUNA_TOUR scene changed to " + SceneManager.GetActiveScene().name + " at shot " + i + ", reloading " + sceneName);
                SceneManager.LoadScene(sceneName);
                yield return null;
                yield return new WaitForSecondsRealtime(SettleSeconds);
            }
            if (plan.shots[i].kind == "intro")
                while (Time.realtimeSinceStartup - introStart < plan.shots[i].pos.x) yield return null;
            else if (plan.shots[i].kind == "hud")
            {
                // HUD screen effect: trigger it, wait target.x seconds, shoot; the Quest host script takes a
                // headset screenshot on the LUNA_HUD line (what the eyes see, view layer included).
                yield return new WaitForSecondsRealtime(1f);
                // A shot's action may throw (the DEATH weapon removes itself when equipped, so the
                // next fire:0 hits a destroyed object): log it and go on, or the whole tour stops.
                try { TriggerHud(plan.shots[i].name); }
                catch (System.Exception e) { log("LUNA_HUD failed " + key + " " + i + " " + plan.shots[i].name + ": " + (e.InnerException ?? e).Message); }
                yield return new WaitForSecondsRealtime(plan.shots[i].target.x);
                log("LUNA_HUD ready " + key + " " + i + " " + plan.shots[i].name);
                if (Camera.main != null) log("LUNA_HUD view " + key + " " + i + " euler=" + Camera.main.transform.eulerAngles.ToString("F1") + " pos=" + Camera.main.transform.position.ToString("F2"));
            }
            else
                yield return new WaitForSecondsRealtime(0.5f);
            // In batch mode (tools/tour/editor_tour.sh) end of frame never comes: there is no screen.
            if (Application.isBatchMode) yield return null; else yield return new WaitForEndOfFrame();
            string file = Path.Combine(outDir, string.Format("{0}_{1:00}.png", prefix, i));
            var seen = Shoot(plan.shots[i], file);
            File.WriteAllText(file.Substring(0, file.Length - 4) + ".mats.txt", string.Join("\n", seen.ToArray()) + "\n");
            log("LUNA_TOUR shot " + file + " " + plan.shots[i].name);
            if (plan.shots[i].kind == "hud") yield return new WaitForSecondsRealtime(plan.shots[i].target.y);
            // The intro beach sea (TOWN_OCEAN, Shader Forge/Water_alt) was missing on the Quest.
            if (plan.shots[i].kind == "intro")
                foreach (var r in FindObjectsOfType<Renderer>().Where(r => r.name == "TOWN_OCEAN"))
                    log("LUNA_TOUR sea " + key + " " + i + " enabled=" + r.enabled + " visible=" + r.isVisible + " shader=" + r.sharedMaterial.shader.name
                        + " supported=" + r.sharedMaterial.shader.isSupported + " queue=" + r.sharedMaterial.renderQueue + " bounds=" + r.bounds);
            // Where the player is at each shot (the TOWER boat ride drops him into a fall zone on the Quest).
            if (player != null)
                log("LUNA_TOUR playerpos " + key + " " + i + " t=" + Time.timeSinceLevelLoad.ToString("0.0") + " world=" + player.transform.position
                    + " local=" + player.transform.localPosition + " parent=" + (player.transform.parent != null ? player.transform.parent.name : "none")
                    + " vel=" + (player.GetComponent<Rigidbody>() != null ? player.GetComponent<Rigidbody>().velocity.ToString() : "-"));
        }
        Time.timeScale = timeScale;
        File.WriteAllText(Path.Combine(dir, "done.txt"), key + " " + plan.shots.Length + "\n");
        log("LUNA_TOUR done");
        finished = true;
        if (quitWhenDone) Application.Quit();
    }

    // ---- planning (PC) -------------------------------------------------------------------

    LunaTourShot[] PlanShots()
    {
        if (ViewOnlyScenes.Contains(SceneManager.GetActiveScene().name))
        {
            var cam = PickCamera().transform;
            return new[] { new LunaTourShot { name = HierPath(cam), kind = "view", target = cam.position + cam.forward,
                                              pos = cam.position, euler = cam.eulerAngles } };
        }
        var targets = new List<LunaTourShot>();
        foreach (var l in FindObjectsOfType<Light>())
        {
            if (!l.isActiveAndEnabled || l.type == LightType.Directional) continue;
            targets.Add(new LunaTourShot { name = HierPath(l.transform), kind = "light", target = l.transform.position });
        }
        foreach (var r in FindObjectsOfType<Renderer>())
        {
            if (!r.isVisible && !r.enabled) continue;
            if (!r.gameObject.activeInHierarchy) continue;
            var mats = r.sharedMaterials;
            if (mats == null || !mats.Any(m => m != null && m.renderQueue >= 2450)) continue;
            string kind = r is ParticleSystemRenderer ? "particles" : "alpha";
            targets.Add(new LunaTourShot { name = HierPath(r.transform), kind = kind, target = r.bounds.center });
        }
        // Deterministic order, then keep spots at least MinSpacing apart.
        targets = targets.OrderBy(t => t.kind).ThenBy(t => t.name, StringComparer.Ordinal)
                         .ThenBy(t => t.target.x).ThenBy(t => t.target.z).ToList();
        var chosen = new List<LunaTourShot>();
        foreach (var t in targets)
        {
            if (chosen.Count >= MaxShots) break;
            if (chosen.Any(c => (c.target - t.target).sqrMagnitude < MinSpacing * MinSpacing)) continue;
            PlaceCamera(t);
            chosen.Add(t);
        }
        return chosen.ToArray();
    }

    // Material identity across both games: material name (without " (Instance)") and shader name.
    public static string MaterialKey(Material m)
    {
        string n = m.name.Replace(" (Instance)", "");
        return n + "\t" + (m.shader != null ? m.shader.name : "?");
    }

    static IEnumerable<Renderer> ActiveRenderers()
    {
        return FindObjectsOfType<Renderer>().Where(r => r.enabled && r.gameObject.activeInHierarchy);
    }

    // Every material on an active renderer: key \t count \t one renderer's path.
    static string MaterialInventory()
    {
        var found = new Dictionary<string, KeyValuePair<int, string>>();
        foreach (var r in ActiveRenderers())
            foreach (var m in r.sharedMaterials)
            {
                if (m == null) continue;
                string k = MaterialKey(m);
                KeyValuePair<int, string> v;
                found[k] = found.TryGetValue(k, out v) ? new KeyValuePair<int, string>(v.Key + 1, v.Value) : new KeyValuePair<int, string>(1, HierPath(r.transform));
            }
        return string.Join("\n", found.OrderBy(f => f.Key, StringComparer.Ordinal).Select(f => f.Key + "\t" + f.Value.Key + "\t" + f.Value.Value).ToArray()) + "\n";
    }

    // One shot per wanted material, at its largest renderer; materials whose renderer sits next to an
    // already chosen spot are left for the next round (they are often in that shot anyway).
    LunaTourShot[] PlanForMaterials(HashSet<string> want)
    {
        var byKey = new Dictionary<string, Renderer>();
        foreach (var r in ActiveRenderers())
            foreach (var m in r.sharedMaterials)
            {
                if (m == null) continue;
                string k = MaterialKey(m);
                if (!want.Contains(k)) continue;
                Renderer cur;
                if (!byKey.TryGetValue(k, out cur) || r.bounds.size.sqrMagnitude > cur.bounds.size.sqrMagnitude) byKey[k] = r;
            }
        var chosen = new List<LunaTourShot>();
        foreach (var kv in byKey.OrderBy(k => k.Key, StringComparer.Ordinal))
        {
            if (chosen.Count >= MaxMaterialShots) break;
            var b = kv.Value.bounds;
            if (chosen.Any(c => (c.target - b.center).sqrMagnitude < 4f)) continue;
            var shot = new LunaTourShot { name = kv.Key.Split('\t')[0] + " @ " + HierPath(kv.Value.transform), kind = "material", target = b.center };
            PlaceCamera(shot, Mathf.Clamp(b.extents.magnitude * 2.5f, 2f, 12f));
            chosen.Add(shot);
        }
        return chosen.ToArray();
    }

    static void PlaceCamera(LunaTourShot s)
    {
        PlaceCamera(s, 5f);
    }

    static void PlaceCamera(LunaTourShot s, float want)
    {
        Vector3 best = s.target + new Vector3(0, 1.5f, -want);
        float bestDist = -1f;
        for (int a = 0; a < 8; a++)
        {
            float yaw = a * 45f * Mathf.Deg2Rad;
            var dir = new Vector3(Mathf.Sin(yaw), 0.35f, -Mathf.Cos(yaw)).normalized;
            RaycastHit hit;
            float free = Physics.Raycast(s.target, dir, out hit, want, ~0, QueryTriggerInteraction.Ignore) ? hit.distance * 0.8f : want;
            if (free > bestDist + 0.01f)
            {
                bestDist = free;
                best = s.target + dir * Mathf.Max(free, 1f);
            }
            if (free >= want) break;
        }
        s.pos = best;
        s.euler = Quaternion.LookRotation(s.target - best).eulerAngles;
    }

    static string HierPath(Transform t)
    {
        string p = t.name;
        while (t.parent != null) { t = t.parent; p = t.name + "/" + p; }
        return p;
    }

    // ---- shooting (both) -----------------------------------------------------------------

    // The world camera: perspective, draws the Default layer, renders to the screen (the HUD
    // camera on top of it draws only UI).
    static Camera PickCamera()
    {
        Camera best = null;
        foreach (var c in Camera.allCameras)
        {
            bool theater = c.targetTexture != null && c.targetTexture.name == "LunaTheaterScreen";   // VR port's menu screen
            if ((c.targetTexture != null && !theater) || c.orthographic || (c.cullingMask & 1) == 0) continue;
            if (best == null || c.depth > best.depth) best = c;
        }
        if (best == null)
        {
            var go = new GameObject("LunaTourCamera");
            DontDestroyOnLoad(go);
            best = go.AddComponent<Camera>();
            best.enabled = false;
        }
        return best;
    }

    // Materials of renderers in the frame, near enough and big enough on screen, not hidden behind a
    // collider (a line from the camera to the renderer's centre).
    static List<string> VisibleMaterials(Camera cam, GameObject only)
    {
        var planes = GeometryUtility.CalculateFrustumPlanes(cam);
        var camPos = cam.transform.position;
        var seen = new SortedSet<string>(StringComparer.Ordinal);
        IEnumerable<Renderer> rs = only != null ? only.GetComponentsInChildren<Renderer>() : ActiveRenderers();
        foreach (var r in rs)
        {
            var b = r.bounds;
            if (!GeometryUtility.TestPlanesAABB(planes, b)) continue;
            float dist = Vector3.Distance(camPos, b.center);
            if (only == null)
            {
                if (dist > 80f || b.extents.magnitude / Mathf.Max(dist, 0.01f) < 0.03f) continue;
                // Big walls and floors often have their centre out of view or behind something: the
                // renderer counts when its centre or any bounds corner is in frame with nothing closer.
                if (!AnyPointVisible(cam, planes, camPos, r, b)) continue;
            }
            foreach (var m in r.sharedMaterials)
                if (m != null) seen.Add(MaterialKey(m) + "\t" + HierPath(r.transform));
        }
        return seen.ToList();
    }

    static bool AnyPointVisible(Camera cam, Plane[] planes, Vector3 camPos, Renderer r, Bounds b)
    {
        var e = b.extents * 0.9f;   // just inside the box, so the point lies on or in the surface
        for (int i = 0; i < 9; i++)
        {
            var p = i == 8 ? b.center : b.center + Vector3.Scale(e, new Vector3((i & 1) == 0 ? -1 : 1, (i & 2) == 0 ? -1 : 1, (i & 4) == 0 ? -1 : 1));
            var vp = cam.WorldToViewportPoint(p);
            if (vp.z <= 0f || vp.x < 0f || vp.x > 1f || vp.y < 0f || vp.y > 1f) continue;
            float d = Vector3.Distance(camPos, p);
            RaycastHit hit;
            if (Physics.Linecast(camPos, p, out hit, ~0, QueryTriggerInteraction.Ignore) && hit.distance < d - 0.3f)
            {
                var t = hit.collider.transform;
                if (!t.IsChildOf(r.transform) && !r.transform.IsChildOf(t)) continue;
            }
            return true;
        }
        return false;
    }

    static Action<string> frameLog;
    static readonly Vector3 ShowcaseSpot = new Vector3(0f, -3000f, 0f);

    // A Resources prefab with its scripts removed (they expect a player), frozen (see Freeze).
    static GameObject SpawnShowcase(string path, float seconds)
    {
        var prefab = Resources.Load<GameObject>(path);
        if (prefab == null) return null;
        var holder = new GameObject("LunaTourShowcase");
        holder.SetActive(false);
        holder.transform.position = ShowcaseSpot;
        var go = Instantiate(prefab, ShowcaseSpot, Quaternion.identity, holder.transform);
        foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>(true).Reverse())
            try { DestroyImmediate(mb); } catch (Exception) { }
        // Weapon models sit inactive in the prefab until the game equips them: switch on every
        // renderer's chain up to the prefab root.
        foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            for (var t = r.transform; t != null && t != holder.transform; t = t.parent) t.gameObject.SetActive(true);
        holder.SetActive(true);
        Freeze(holder, seconds);
        return holder;
    }

    // Same result on both games: rigidbodies stop, particles restart from a fixed seed and run `seconds`.
    static void Freeze(GameObject root, float seconds)
    {
        foreach (var rb in root.GetComponentsInChildren<Rigidbody>(true)) rb.isKinematic = true;
        foreach (var ps in root.GetComponentsInChildren<ParticleSystem>(true))
        {
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            ps.useAutoRandomSeed = false;
            ps.randomSeed = 1234;
        }
        foreach (var ps in root.GetComponentsInChildren<ParticleSystem>(true))
            if (ps.transform.parent == null || ps.transform.parent.GetComponentInParent<ParticleSystem>() == null)
                ps.Simulate(seconds, true, true);
    }

    static readonly string[] Elements = { "EFFECTS/FIRE_SMALL", "EFFECTS/ICE", "EFFECTS/POISON" };

    static T Field<T>(MonoBehaviour m, string name)
    {
        var f = m.GetType().GetField(name);
        return f != null ? (T)f.GetValue(m) : default(T);
    }

    // Path without the " (3)" Unity adds to copies, so each enemy kind is shot once.
    static string KindOf(Transform t)
    {
        return System.Text.RegularExpressions.Regex.Replace(t.name, @" \(\d+\)$", "");
    }

    static bool Animated(Transform t)
    {
        return t.GetComponent<Animator>() != null || t.GetComponent<Animation>() != null;
    }

    // The topmost animated object above a hit zone (the zone itself when nothing above is animated).
    static Transform EnemyRoot(Transform zone)
    {
        Transform root = null;
        for (var t = zone; t != null; t = t.parent) if (Animated(t)) root = t;
        return root ?? zone;
    }

    static IEnumerable<MonoBehaviour> Zones(GameObject go, int type)
    {
        return go.GetComponentsInChildren<MonoBehaviour>(true).Where(m => m != null && m.GetType().Name == "OBJ_HEALTH" && Field<int>(m, "type") == type);
    }

    // One set of shots per enemy kind: whole all around, the other states from four sides.
    LunaTourShot[] PlanNpcs()
    {
        var shots = new List<LunaTourShot>();
        var kinds = new HashSet<string>();
        var roots = Resources.FindObjectsOfTypeAll<MonoBehaviour>()
            .Where(m => m != null && m.GetType().Name == "OBJ_HEALTH" && m.gameObject.scene.IsValid() && Field<int>(m, "type") == 1)
            .Select(m => EnemyRoot(m.transform)).Distinct()
            .OrderBy(t => HierPath(t), StringComparer.Ordinal);
        foreach (var root in roots)
        {
            if (!kinds.Add(KindOf(root))) continue;
            string path = HierPath(root);
            bool parts = Zones(root.gameObject, 2).Any();
            bool dead = Zones(root.gameObject, 1).Any(m => !string.IsNullOrEmpty(Field<string>(m, "DED")));
            bool glows = root.GetComponentsInChildren<Renderer>(true).Any(r => !(r is ParticleSystemRenderer)
                && r.sharedMaterials.Any(m => m != null && m.renderQueue >= 2450));
            for (int a = 0; a < 8; a++) shots.Add(NpcShot(path, 0, a * 45f, 10f, 1f));
            shots.Add(NpcShot(path, 0, 0f, 5f, 0.45f));
            if (glows) { shots.Add(NpcShot(path, 0, 0f, 10f, 1f, 1)); shots.Add(NpcShot(path, 0, 0f, 5f, 0.45f, 1)); }
            shots.Add(NpcShot(path, 0, 45f, 10f, 1f, 0, 1));
            foreach (int state in new[] { 1, 2, 3, 4, 5 })
            {
                if ((state == 1 && !parts) || (state == 2 && !dead)) continue;
                shots.Add(NpcShot(path, state, 0f, 10f, 1f, state >= 3 ? 1 : 0));
                shots.Add(NpcShot(path, state, 180f, 10f, 1f));
            }
        }
        log("LUNA_TOUR npcs " + key + " " + kinds.Count + " kinds");
        return shots.ToArray();
    }

    static LunaTourShot NpcShot(string path, int state, float yaw, float pitch, float dist, int black = 0, int pointLight = 0)
    {
        return new LunaTourShot { kind = "npc", name = path, pos = new Vector3(yaw, pitch, dist), euler = new Vector3(state, black, pointLight) };
    }

    static GameObject FindInScene(string path)
    {
        return Resources.FindObjectsOfTypeAll<Transform>()
            .Where(t => t.gameObject.scene.IsValid() && HierPath(t) == path).Select(t => t.gameObject).FirstOrDefault();
    }

    // Idle pose at frame 0 (the clip named idle, else the first), then the animators stop.
    static void Pose(GameObject go)
    {
        foreach (var an in go.GetComponentsInChildren<Animator>(true))
        {
            var clips = an.runtimeAnimatorController != null ? an.runtimeAnimatorController.animationClips : new AnimationClip[0];
            var clip = clips.FirstOrDefault(c => c != null && c.name.ToLowerInvariant().Contains("idle")) ?? clips.FirstOrDefault(c => c != null);
            if (clip != null) clip.SampleAnimation(an.gameObject, 0f);
            an.enabled = false;
        }
        foreach (var anim in go.GetComponentsInChildren<Animation>(true))
        {
            if (anim.clip != null) anim.clip.SampleAnimation(anim.gameObject, 0f);
            anim.enabled = false;
        }
    }

    static GameObject SpawnPart(string path, Vector3 pos, Quaternion rot, Transform parent)
    {
        var prefab = Resources.Load<GameObject>(path);
        if (prefab == null) return null;
        var go = Instantiate(prefab, pos, rot, parent);
        foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>(true).Reverse())
            try { DestroyImmediate(mb); } catch (Exception) { }
        return go;
    }

    // A frozen copy of a scene enemy in the showcase, in one of its states.
    static GameObject SpawnNpc(string path, int state, float seconds)
    {
        var src = FindInScene(path);
        if (src == null) return null;
        var holder = new GameObject("LunaTourShowcase");
        holder.SetActive(false);
        holder.transform.position = ShowcaseSpot;
        var go = Instantiate(src, ShowcaseSpot, Quaternion.identity, holder.transform);
        go.SetActive(true);
        // What the game's OBJ_HEALTH.Die would do to each zone, read before the scripts go.
        Func<int, List<KeyValuePair<Transform, string>>> zones = type => Zones(go, type)
            .Select(m => new KeyValuePair<Transform, string>(m.transform, Field<string>(m, "DED"))).ToList();
        var pieces = zones(2);
        var hits = zones(1);
        Pose(go);
        foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>(true).Reverse())
            try { DestroyImmediate(mb); } catch (Exception) { }
        holder.SetActive(true);
        if (state == 1)
            foreach (var p in pieces)
            {
                if (!string.IsNullOrEmpty(p.Value)) SpawnPart(p.Value, p.Key.position, p.Key.rotation, holder.transform);
                p.Key.localScale = Vector3.zero;
                p.Key.gameObject.SetActive(false);
            }
        if (state == 2)
        {
            foreach (var z in hits.Concat(pieces))
                if (!string.IsNullOrEmpty(z.Value)) SpawnPart(z.Value, z.Key.position, z.Key.rotation, holder.transform);
            go.SetActive(false);
        }
        if (state >= 3 && state <= 5) SpawnPart(Elements[state - 3], go.transform.position, go.transform.rotation, go.transform);
        Freeze(holder, seconds);
        return holder;
    }

    // What the Start button does in MainMenu (MainMenu.SUBMIT, menu 1, slot 1): the menu goes, the intro
    // object (main_objs[20]) comes on, the menu script stops.
    float StartIntro()
    {
        // Looked up in every loaded assembly (a BepInEx plugin does not resolve "MainMenu, Assembly-CSharp"),
        // inactive objects included.
        var type = AppDomain.CurrentDomain.GetAssemblies().Select(asm => asm.GetType("MainMenu")).FirstOrDefault(t => t != null);
        var menu = type == null ? null : Resources.FindObjectsOfTypeAll(type).OfType<MonoBehaviour>()
            .FirstOrDefault(m => m.gameObject.scene.IsValid());
        if (menu == null) { log("LUNA_TOUR intro: no MainMenu (type " + (type != null) + ")"); return Time.realtimeSinceStartup; }
        var objs = type.GetField("main_objs").GetValue(menu) as GameObject[];
        var menus = type.GetField("MENUS").GetValue(menu) as GameObject[];
        if (menus != null && menus.Length > 2 && menus[2] != null) menus[2].SetActive(false);
        if (objs != null && objs.Length > 20 && objs[20] != null) objs[20].SetActive(true);
        menu.enabled = false;
        log("LUNA_TOUR intro started");
        return Time.realtimeSinceStartup;
    }

    // The intro's own camera as it is (pose, field of view).
    // HUD effects (plan name): "harm:N" calls Player_Poison.Harm(N, 1.5 s) (negative N are the
    // hit flashes, 0 bleed, 1 poison, 2 curse, 3 water, 5 blind, 8 grab, 9 infection); "pop" is the item
    // pickup notice; "flash" is the magic cast flash, "flash_slow" the same fading over ~7 s (Flash_scr on FLASH_FADE, red at 0.5 alpha).
    static void TriggerHud(string what)
    {
        // "style:N" is the game's screen filter (Aestheticcc_scr.ChangeStyle: 0 MIDNIGHT, 1 VHS, 2 PSX,
        // 3 VAPORWAVE, 4 SILENT, 5 CLEAN), set on every camera that has it, as the settings menu does.
        if (what.StartsWith("style:"))
        {
            int style = int.Parse(what.Substring(6));
            var styleType = AppDomain.CurrentDomain.GetAssemblies().Select(asm => asm.GetType("Aestheticcc_scr")).FirstOrDefault(t => t != null);
            int n = 0;
            if (styleType != null)
                foreach (var c in Resources.FindObjectsOfTypeAll(styleType).OfType<MonoBehaviour>().Where(m => m.gameObject.scene.IsValid()))
                {
                    styleType.GetMethod("ChangeStyle").Invoke(c, new object[] { style });
                    n++;
                }
            Debug.Log("LUNA_HUD style " + style + " on " + n + " camera(s)");
            return;
        }
        // "wep:NAME" equips a weapon (the game's own swap, through slot 1 -> 0); "fire:N" sends the
        // equipped weapon OnFire(N): 0 press (wind-up), 1 release (swing), 2 block.
        // "mag:NAME" puts a spell in the first magic slot (the game's EQMagic); "cast:N" charges (1) or
        // casts (0) it, with the mana topped up so no spell fails for lack of it.
        if (what.StartsWith("mag:") || what.StartsWith("cast:"))
        {
            var conType = System.Type.GetType("CONTROL, Assembly-CSharp");
            var con = conType != null ? FindObjectOfType(conType) : null;
            if (con == null) return;
            const System.Reflection.BindingFlags F = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
            var data = conType.GetField("CURRENT_PL_DATA", F).GetValue(con);
            if (what.StartsWith("mag:"))
            {
                data.GetType().GetField("MAG1", F).SetValue(data, what.Substring(4));
                conType.GetMethod("EQMagic", F).Invoke(con, null);
            }
            else
            {
                data.GetType().GetField("PLAYER_M", F).SetValue(data, 999f);
                var mag = conType.GetField("EQ_MAG1", F).GetValue(con);
                mag?.GetType().GetMethod("Charging", F).Invoke(mag, new object[] { float.Parse(what.Substring(5), System.Globalization.CultureInfo.InvariantCulture) });
            }
            return;
        }
        if (what.StartsWith("wep:") || what.StartsWith("fire:"))
        {
            var conType = System.Type.GetType("CONTROL, Assembly-CSharp");
            var con = conType != null ? FindObjectOfType(conType) : null;
            if (con == null) return;
            const System.Reflection.BindingFlags F = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
            if (what.StartsWith("wep:"))
            {
                var data = conType.GetField("CURRENT_PL_DATA", F).GetValue(con);
                data.GetType().GetField("WEP1", F).SetValue(data, what.Substring(4));
                conType.GetField("EQ_SLOT", F).SetValue(con, 1);
                conType.GetMethod("OnSwap", F).Invoke(con, null);
            }
            else
            {
                var wep = conType.GetField("EQ_WEP", F).GetValue(con);
                wep?.GetType().GetMethod("OnFire", F).Invoke(wep, new object[] { int.Parse(what.Substring(5)) });
            }
            return;
        }
        // "face:YAW" turns the player so the view looks along YAW degrees, wherever the headset points
        // (on the Quest the camera yaw is the body's plus the headset's): PC and Quest shots then
        // face the same way and catch the same lights.
        if (what.StartsWith("face:"))
        {
            var plType = System.Type.GetType("Player_Control_scr, Assembly-CSharp");
            var pl = plType != null ? FindObjectOfType(plType) as Component : null;
            var cam = Camera.main;
            if (pl == null || cam == null) return;
            const System.Reflection.BindingFlags F = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
            float delta = Mathf.DeltaAngle(cam.transform.eulerAngles.y, float.Parse(what.Substring(5), System.Globalization.CultureInfo.InvariantCulture));
            foreach (var name in new[] { "ROT", "OLD_ROT" })
            {
                var f = plType.GetField(name, F);
                if (f == null || f.FieldType != typeof(Vector3)) continue;
                var r = (Vector3)f.GetValue(pl);
                r.y += delta;
                if (name == "ROT") r.x = 0f;
                f.SetValue(pl, r);
            }
            var rot = (Vector3)plType.GetField("ROT", F).GetValue(pl);
            pl.transform.rotation = Quaternion.Euler(0f, rot.y, 0f);
            return;
        }
        if (what.StartsWith("harm:"))
        {
            var type = System.Type.GetType("Player_Poison, Assembly-CSharp");
            var poison = type != null ? FindObjectOfType(type) : null;
            var harm = type != null ? type.GetMethod("Harm") : null;
            int n = int.Parse(what.Substring(5));
            if (poison != null && harm != null) harm.Invoke(poison, new object[] { n, 1.5f });
        }
        else if (what == "pop")
        {
            // The item pickup notice: text plus the OVERLAY_NEW glow (GlowBox, tinted by its animation).
            var type = System.Type.GetType("POP_text_scr, Assembly-CSharp");
            var pop = type != null ? FindObjectOfType(type) : null;
            if (pop != null) type.GetMethod("POP").Invoke(pop, new object[] { "TEST ITEM <sprite=3> AQUIRED", 1f, 0 });
        }
        else if (what.StartsWith("menu:") || what.StartsWith("sub:") || what == "close")
        {
            // Game menus: "menu:K" opens Menus.MENUS[K] (0 MAIN, 2 CRYSTAL, 3 ROOT, 4 DIALOG, 5 MERCHANT)
            // with the player frozen, "sub:N" shows SUBMENUS[N] (8 SAVE, 12 LEVEL, 13 WARP, 14 shop...),
            // "close" goes back to the playing HUD.
            var type = System.Type.GetType("Menus, Assembly-CSharp");
            var menus = type != null ? FindObjectOfType(type) : null;
            if (menus == null) return;
            var con = type.GetField("CON").GetValue(menus);
            var pl = con != null ? con.GetType().GetField("PL").GetValue(con) : null;
            var freeze = pl != null ? pl.GetType().GetField("Freeze") : null;
            try
            {
                if (what == "close")
                {
                    type.GetField("current_menu").SetValue(menus, 1);
                    type.GetMethod("LoadMenu").Invoke(menus, null);
                    if (freeze != null) freeze.SetValue(pl, false);
                }
                else if (what.StartsWith("menu:"))
                {
                    if (freeze != null) freeze.SetValue(pl, true);
                    type.GetField("current_menu").SetValue(menus, int.Parse(what.Substring(5)));
                    type.GetMethod("LoadMenu").Invoke(menus, null);
                }
                else
                {
                    type.GetField("sub_menu").SetValue(menus, int.Parse(what.Substring(4)));
                    type.GetMethod("LoadSub").Invoke(menus, null);
                }
            }
            catch (System.Exception e) { Debug.Log("LUNA_HUD menu " + what + " failed: " + (e.InnerException ?? e).Message); }
        }
        else if (what == "flash" || what == "flash_slow")
        {
            var go = GameObject.Find("FLASH_FADE");
            var type = System.Type.GetType("Flash_scr, Assembly-CSharp");
            var flash = go != null && type != null ? go.GetComponent(type) : null;
            if (flash != null) type.GetMethod("Flash").Invoke(flash, new object[] { new Color(1f, 0.2f, 0.2f, 0.5f), what == "flash" ? 1f : 0.15f });
        }
    }

    static List<string> ShootAsIs(string file)
    {
        var cam = PickCamera();
        var shot = new LunaTourShot { kind = "view", pos = cam.transform.position, euler = cam.transform.eulerAngles };
        float fov = cam.fieldOfView;
        var seen = Shoot(shot, file, fov);
        return seen;
    }

    static List<string> Shoot(LunaTourShot s, string file)
    {
        if (s.kind == "prefab") return ShootPrefab(s, file);
        if (s.kind == "npc") return ShootNpc(s, file);
#if BEPINEX
        // On PC the HUD is drawn by another camera: grab the whole composited frame (called after
        // WaitForEndOfFrame). The Quest's eye view comes from the headset screenshot instead.
        if (s.kind == "hud")
        {
            var shot = ScreenCapture.CaptureScreenshotAsTexture();
            File.WriteAllBytes(file, shot.EncodeToPNG());
            Destroy(shot);
            return new List<string>();
        }
#endif
        if (s.kind == "intro" || s.kind == "hud") return ShootAsIs(file);
        return Shoot(s, file, 60f);
    }

    static List<string> Shoot(LunaTourShot s, string file, float fieldOfView)
    {
        var cam = PickCamera();
        var rt = RenderTexture.GetTemporary(Width, Height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
        var oldTarget = cam.targetTexture;
        var oldPos = cam.transform.position;
        var oldRot = cam.transform.rotation;
        float oldFov = cam.fieldOfView, oldFar = cam.farClipPlane;
        var oldEye = cam.stereoTargetEye;   // with VR on, shoot in mono with the camera's own projection
        cam.stereoTargetEye = StereoTargetEyeMask.None;

        cam.transform.position = s.pos;
        cam.transform.rotation = Quaternion.Euler(s.euler);
        cam.fieldOfView = fieldOfView;
        cam.farClipPlane = Mathf.Max(oldFar, 300f);
        cam.targetTexture = rt;
        cam.aspect = (float)Width / Height;
        var seen = VisibleMaterials(cam, null);
        cam.Render();

        var prev = RenderTexture.active;
        RenderTexture.active = rt;
        var tex = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
        tex.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
        tex.Apply();
        RenderTexture.active = prev;
        File.WriteAllBytes(file, tex.EncodeToPNG());
        Destroy(tex);

        cam.targetTexture = oldTarget;
        cam.transform.position = oldPos;
        cam.transform.rotation = oldRot;
        cam.fieldOfView = oldFov;
        cam.farClipPlane = oldFar;
        cam.stereoTargetEye = oldEye;
        cam.ResetAspect();
        RenderTexture.ReleaseTemporary(rt);
        return seen;
    }

    static List<string> ShootPrefab(LunaTourShot s, string file)
    {
        var holder = SpawnShowcase(s.name, s.target.x > 0f ? s.target.x : 1f);
        if (holder == null) { File.WriteAllBytes(file, new byte[0]); return new List<string> { "missing prefab " + s.name }; }
        return ShootShowcase(holder, s, file);
    }

    static List<string> ShootNpc(LunaTourShot s, string file)
    {
        var holder = SpawnNpc(s.name, Mathf.RoundToInt(s.euler.x), 1f);
        if (holder == null) { File.WriteAllBytes(file, new byte[0]); return new List<string> { "missing npc " + s.name }; }
        return ShootShowcase(holder, s, file);
    }

    // Frames what the holder shows from s.pos = (yaw, pitch, distance scale); a close shot (scale under
    // 0.6) aims at the top of the model, where the faces and eyes are.
    static List<string> ShootShowcase(GameObject holder, LunaTourShot s, string file)
    {
        var rends = holder.GetComponentsInChildren<Renderer>();
        if (rends.Length == 0) { Destroy(holder); File.WriteAllBytes(file, new byte[0]); return new List<string> { "no renderer " + s.name }; }
        // Framed by its opaque models, else its models; particles only when there is nothing else (their
        // bounds are loose, and transparent bits such as the skeletons' blood rain hang far off).
        var models = rends.Where(r => r.enabled && !(r is ParticleSystemRenderer) && !(r is TrailRenderer) && !(r is LineRenderer)).ToArray();
        var opaque = models.Where(r => r.sharedMaterials.Any(m => m != null && m.renderQueue < 2450)).ToArray();
        if (opaque.Length > 0) rends = opaque;
        else if (models.Length > 0) rends = models;
        var b = Tight(rends[0]);
        foreach (var r in rends) b.Encapsulate(Tight(r));
        if (frameLog != null)
            foreach (var r in rends) frameLog("LUNA_TOUR frame " + HierPath(r.transform) + " " + r.GetType().Name + " " + Tight(r));
        float radius = Mathf.Max(b.extents.magnitude, 0.05f);
        var dir = s.pos == Vector3.zero ? new Vector3(0.35f, 0.25f, -1f).normalized
                                        : Quaternion.Euler(-s.pos.y, s.pos.x, 0f) * Vector3.forward;
        float scale = s.pos == Vector3.zero ? 1f : s.pos.z;
        var aim = scale < 0.6f ? b.center + Vector3.up * b.extents.y * 0.6f : b.center;
        var shot = new LunaTourShot { kind = "view", name = s.name, target = aim };
        if (s.pos == Vector3.zero) shot.pos = aim + dir * radius * 2.4f;
        else
        {
            // Close enough for the model, as seen from this side, to fill ~85% of the 60° frame.
            var look = Quaternion.LookRotation(-dir);
            Func<Vector3, float> span = axis => Mathf.Abs(axis.x) * b.extents.x + Mathf.Abs(axis.y) * b.extents.y + Mathf.Abs(axis.z) * b.extents.z;
            float t = Mathf.Tan(30f * Mathf.Deg2Rad);
            float fit = Mathf.Max(span(look * Vector3.up) / t, span(look * Vector3.right) / (t * Width / Height)) / 0.85f;
            shot.pos = aim + dir * (fit + 0.3f * span(dir)) * scale;
        }
        shot.euler = Quaternion.LookRotation(aim - shot.pos).eulerAngles;

        // Fixed light, background and ambient, the same on both games; restored after.
        var lightGo = new GameObject("LunaTourShowcaseLight");
        var light = lightGo.AddComponent<Light>();
        light.type = LightType.Directional;
        light.intensity = 1f;
        light.shadows = LightShadows.None;
        lightGo.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        bool fog = RenderSettings.fog;
        var ambientMode = RenderSettings.ambientMode;
        var ambient = RenderSettings.ambientLight;
        RenderSettings.fog = false;
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
        RenderSettings.ambientLight = new Color(0.4f, 0.4f, 0.4f);
        var cam = PickCamera();
        var clear = cam.clearFlags;
        var bg = cam.backgroundColor;
        float near = cam.nearClipPlane;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = s.euler.y > 0.5f ? Color.black : new Color(0.5f, 0.5f, 0.5f);
        GameObject pointGo = null;
        if (s.euler.z > 0.5f)
        {
            pointGo = new GameObject("LunaTourShowcasePoint");
            var point = pointGo.AddComponent<Light>();
            point.type = LightType.Point;
            point.color = new Color(1f, 0.6f, 0.3f);
            point.intensity = 2f;
            point.range = radius * 4f;
            point.shadows = LightShadows.None;
            point.renderMode = LightRenderMode.ForcePixel;
            pointGo.transform.position = b.center + new Vector3(radius, radius * 0.6f, -radius);
            light.intensity = 0.3f;
        }
        cam.nearClipPlane = Mathf.Min(near, radius * 0.1f);

        var seen = Shoot(shot, file);
        var mats = VisibleMaterialsOf(holder);

        cam.clearFlags = clear;
        cam.backgroundColor = bg;
        cam.nearClipPlane = near;
        RenderSettings.fog = fog;
        RenderSettings.ambientMode = ambientMode;
        RenderSettings.ambientLight = ambient;
        Destroy(lightGo);
        if (pointGo != null) Destroy(pointGo);
        Destroy(holder);
        return mats;
    }

    // A skinned mesh's bounds are loose (set for animation): its bones' positions, with some margin.
    static Bounds Tight(Renderer r)
    {
        var smr = r as SkinnedMeshRenderer;
        var bones = smr != null && smr.bones != null ? smr.bones.Where(t => t != null).ToArray() : new Transform[0];
        if (bones.Length < 2) return r.bounds;
        var b = new Bounds(bones[0].position, Vector3.zero);
        foreach (var t in bones) b.Encapsulate(t.position);
        b.Expand(Mathf.Max(b.size.magnitude * 0.15f, 0.05f));
        return b;
    }

    static List<string> VisibleMaterialsOf(GameObject holder)
    {
        var seen = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var r in holder.GetComponentsInChildren<Renderer>())
            foreach (var m in r.sharedMaterials)
                if (m != null) seen.Add(MaterialKey(m) + "\t" + HierPath(r.transform));
        return seen.ToList();
    }
}

#if BEPINEX
[BepInEx.BepInPlugin("lunacid.port.lunatour", "LunaTour", "0.1.0")]
public class LunaTourPlugin : BepInEx.BaseUnityPlugin
{
    IEnumerator Start()
    {
        string dir = System.IO.Path.Combine(BepInEx.Paths.BepInExRootPath, "tour");
        string request = System.IO.Path.Combine(dir, "request.txt");
        if (!File.Exists(request)) yield break;
        // One scene per line; they are toured one after the other.
        var scenes = File.ReadAllLines(request).Select(l => l.Trim()).Where(l => l.Length > 0).ToArray();
        File.Delete(System.IO.Path.Combine(dir, "done.txt"));
        // Let the game finish its own boot (logo, menu) before switching scenes.
        yield return new WaitForSecondsRealtime(20f);
        foreach (string scene in scenes)
        {
            // "KEY:SCENE" tours SCENE under another plan name (e.g. NPCS_CAVE:CAVE).
            var r = LunaTourRunner.Create(dir, "pc");
            r.scene = scene.Contains(":") ? scene.Split(':')[1] : scene;
            r.key = scene.Split(':')[0];
            r.log = s => Logger.LogInfo(s);
            string planFile = System.IO.Path.Combine(dir, "plan_" + r.key + ".txt");
            r.StartTour(File.Exists(planFile) ? LunaTourPlan.FromText(File.ReadAllText(planFile)) : null);
            while (!r.finished) yield return null;
            Destroy(r.gameObject);
        }
        File.WriteAllText(System.IO.Path.Combine(dir, "all_done.txt"), string.Join("\n", scenes) + "\n");
        // Close the game, or every unattended run leaves a window open.
        Application.Quit();
    }
}
#else
public static class LunaTourBoot
{
    // Every <persistentDataPath>/tour/plan_<scene>.txt is toured in name order, then the app quits.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Boot()
    {
        string dir = Path.Combine(Application.persistentDataPath, "tour");
        if (!Directory.Exists(dir)) return;
        var files = Directory.GetFiles(dir, "plan_*.txt").OrderBy(f => f, StringComparer.Ordinal).ToArray();
        var plans = files.Select(f => LunaTourPlan.FromText(File.ReadAllText(f))).ToArray();
        var keys = files.Select(f => Path.GetFileNameWithoutExtension(f).Substring(5)).ToArray();
        if (plans.Length == 0) return;
        File.Delete(Path.Combine(dir, "all_done.txt"));
        var host = new GameObject("LunaTourBoot");
        UnityEngine.Object.DontDestroyOnLoad(host);
        host.AddComponent<LunaTourHost>().StartCoroutine(RunAll(dir, plans, keys));
    }

    static IEnumerator RunAll(string dir, LunaTourPlan[] plans, string[] keys)
    {
        yield return new WaitForSecondsRealtime(8f);
        for (int i = 0; i < plans.Length; i++)
        {
            var plan = plans[i];
            var r = LunaTourRunner.Create(dir, "quest");
            r.key = keys[i];
            r.StartTour(plan);
            while (!r.finished) yield return null;
            UnityEngine.Object.Destroy(r.gameObject);
        }
        File.WriteAllText(Path.Combine(dir, "all_done.txt"), string.Join("\n", plans.Select(p => p.scene).ToArray()) + "\n");
        Application.Quit();
    }
}

public class LunaTourHost : MonoBehaviour { }
#endif
