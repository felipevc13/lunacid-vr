// Temporary play-mode probe (editor only, env LUNA_PROBE=1): reproduces on the desktop what the headset
// showed, at the headset's 72 fps against 50 Hz physics, so a fix can be checked without a build.
#if UNITY_EDITOR
using System.Collections;
using System.Linq;
using System.Reflection;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class LunaProbe : MonoBehaviour
{
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Boot()
    {
        if (string.IsNullOrEmpty(System.Environment.GetEnvironmentVariable("LUNA_PROBE"))) return;
        var go = new GameObject("LunaProbe");
        DontDestroyOnLoad(go);
        go.AddComponent<LunaProbe>();
    }

    static readonly Vector3 SavePos = new Vector3(0.1f, 1f, 0f);
    static readonly Vector3 ScenePos = new Vector3(62.3f, 12.93f, -67.08f);
    static void Log(string s) => Debug.Log("PROBE " + s);

    IEnumerator WaitFrames(int n) { for (int i = 0; i < n; i++) yield return null; }

    static PlayerData Data(Vector3 pos)
    {
        var d = Save.ResetData();
        d.PLAYER_NAME = "Probe";
        d.PLAYER_SPD = 7;
        d.POS_X = pos.x; d.POS_Y = pos.y; d.POS_Z = pos.z;
        return d;
    }

    // Every case reports PASS or FAIL. tools/editor_checks/run_probe.sh fails when a check fails or when the
    // summary line is missing (a crash, a compile error, a run cut by the time limit).
    static int passed, failed;
    // Every text a player can see must draw: an active, non-empty TextMeshPro text needs a font, a material with a
    // supported shader, the font's atlas texture, and visible characters in its mesh; a UI Text needs a font.
    // Build 93 (a project made from scratch) lost the settings values (TURN, L/R HAND) while every behaviour check
    // passed (LESSONS 33). Returns the number of texts checked.
    static int CheckTexts(string label, Transform root)
    {
        int count = 0;
        var bad = new System.Collections.Generic.List<string>();
        if (System.Environment.GetEnvironmentVariable("LUNA_PROBE_TEXT_DUMP") == "1")
            foreach (var d in root.GetComponentsInChildren<TMP_Text>(true))
                Log("TEXTDUMP " + label + " " + d.transform.parent.name + "/" + d.name + " active=" + d.gameObject.activeInHierarchy + " enabled=" + d.enabled
                    + " a=" + d.color.a.ToString("F2") + " font=" + (d.font != null ? d.font.name : "-") + " text='" + (d.text ?? "<null>").Replace("\n", " ") + "'");
        foreach (var t in root.GetComponentsInChildren<TMP_Text>(false))
        {
            if (!t.isActiveAndEnabled || string.IsNullOrWhiteSpace(t.text) || t.color.a <= 0.01f) continue;
            count++;
            string why = null;
            var mat = t.fontSharedMaterial;
            if (t.font == null) why = "no font";
            else if (mat == null) why = "no material";
            else if (mat.shader == null || !mat.shader.isSupported) why = "shader " + (mat.shader == null ? "null" : mat.shader.name + " unsupported");
            else if (t.font.atlasTexture == null) why = "font " + t.font.name + " has no atlas";
            else if (!mat.HasProperty("_MainTex") || mat.GetTexture("_MainTex") == null) why = "material " + mat.name + " has no atlas texture";
            else
            {
                t.ForceMeshUpdate();
                int visible = 0;
                for (int i = 0; i < t.textInfo.characterCount; i++) if (t.textInfo.characterInfo[i].isVisible) visible++;
                if (visible == 0) why = "no visible character";
                else if (t.mesh == null || t.mesh.vertexCount == 0) why = "empty mesh";
            }
            if (why != null) bad.Add(t.name + " '" + t.text.Replace("\n", " ").Substring(0, Mathf.Min(20, t.text.Length)) + "': " + why
                                     + " (font=" + (t.font != null ? t.font.name : "-") + " mat=" + (mat != null ? mat.name + "/" + mat.shader.name : "-") + ")");
        }
        foreach (var u in root.GetComponentsInChildren<Text>(false))
        {
            if (!u.isActiveAndEnabled || string.IsNullOrWhiteSpace(u.text) || u.color.a <= 0.01f) continue;
            count++;
            if (u.font == null) bad.Add(u.name + " '" + u.text + "': UI Text without font");
        }
        Check("texts." + label, bad.Count == 0, count + " texts, bad=[" + string.Join("; ", bad.Take(12)) + "]");
        return count;
    }

    static void Check(string name, bool ok, string detail = "")
    {
        if (ok) passed++; else failed++;
        Log("CHECK " + (ok ? "PASS " : "FAIL ") + name + " " + detail);
    }

    static readonly int[] FrameRates = { 72, 45, 90, 60 };
    static readonly string[] Core = { "Menu", "Spawns", "Walk", "Run", "JumpAndFall", "FallSpawns", "SelectCursor", "Buttons", "AllMenus", "Options", "TouchMapping", "SpellAim", "TheaterLaser", "HandsAtHead",
                                      "Teleports", "TowerTeleport", "Ladder", "Elevator", "BoatRide", "PickupIcon", "PopLayout", "WarpLoading", "QuitToTitle", "FirstLaunch", "CursorGlideCut", "OpeningFacing", "MenuFieldOfView", "SaveLoad", "Death", "HeadRelativeMove" };

    IEnumerator Start()
    {
        Time.captureFramerate = 72;
        Application.logMessageReceived += (c, st, t) => { if (t == LogType.Exception && !c.Contains("steam") && !c.Contains("m_Sprite") && !st.Contains("Dialog.OnDisable")) { Log("EXCEPTION " + c + " | " + st.Split('\n').FirstOrDefault(l => l.Contains("Assets/"))); if (!sweepingSpells) failed++; } }; // Dialog.OnDisable: the game's own, when a scene unloads
        yield return WaitFrames(5);
        var mode = System.Environment.GetEnvironmentVariable("LUNA_PROBE");
        var names = mode == "final" ? Core : mode == "full" ? Core.Concat(new[] { "Scenes" }).ToArray() : mode.Split(',');
        foreach (var name in names)
        {
            var m = GetType().GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (m == null) { Check("case." + name, false, "no such case"); continue; }
            Log("CASE " + name);
            yield return (IEnumerator)m.Invoke(this, null);
            Time.captureFramerate = 72;
        }
        Log("SUMMARY passed=" + passed + " failed=" + failed);
        Log("done");
        // EditorApplication.Exit from play mode in batchmode hung until the time limit: leave at once.
        System.Diagnostics.Process.GetCurrentProcess().Kill();
    }

    float RegionBrightness(Rect uv)
    {
        var rt = FindObjectOfType<LunaTheater>().Texture;
        var was = RenderTexture.active;
        RenderTexture.active = rt;
        var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
        RenderTexture.active = was;
        float sum = 0f; int n = 0;
        for (int x = (int)(uv.xMin * rt.width); x < uv.xMax * rt.width; x += 3)
            for (int y = (int)(uv.yMin * rt.height); y < uv.yMax * rt.height; y += 3) { sum += tex.GetPixel(x, y).grayscale; n++; }
        Destroy(tex);
        return sum / n;
    }

    IEnumerator Spawns()
    {
        int atSave = 0, atScene = 0, between = 0;
        for (int i = 0; i < 16; i++)
        {
            Time.captureFramerate = FrameRates[i % FrameRates.Length];
            Hold_Data.HD = Data(SavePos);
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(1 + i % 5);
            var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().FirstOrDefault(p => p.gameObject.scene.IsValid());
            yield return WaitFrames(1);
            string trace = pl != null ? pl.transform.position.ToString("F1") : "none";
            float end = Time.time + 0.25f;
            while (Time.time < end) yield return null;
            var p2 = pl != null ? pl.transform.position : Vector3.zero;
            if ((p2 - SavePos).magnitude < 4f) atSave++;
            else if ((p2 - ScenePos).magnitude < 4f) atScene++;
            else between++;
            Log("spawn " + i + " early=" + trace + " after=" + p2.ToString("F1"));
            yield return WaitFrames(3 + i % 7);
        }
        Check("spawn.at_save", atSave == 16, "save=" + atSave + " scene=" + atScene + " between=" + between);
    }

    // Drops the player at points of the line between the save and the scene default, where Build 83 spawned
    // it: does a body starting there end up under the level?
    IEnumerator FallLine()
    {
        // Started at the scene default with the opening's trigger off: otherwise the opening freezes the player
        // near the save and the first points prove nothing.
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(30);
        var zone = Resources.FindObjectsOfTypeAll<Transform>().FirstOrDefault(t => t.name == "Scene_Zone" && t.gameObject.scene.IsValid());
        if (zone != null) zone.gameObject.SetActive(false);
        var pl = FindObjectOfType<Player_Control_scr>();
        var body = pl.GetComponent<Rigidbody>();
        foreach (var fix in Resources.FindObjectsOfTypeAll<FallFix>().Where(x => x.gameObject.scene.IsValid()))
        {
            var c = fix.GetComponent<Collider>();
            Log("FallFix " + fix.name + " at=" + fix.transform.position.ToString("F1") + " bounds=" + (c != null ? c.bounds.ToString("F1") : "none") + " active=" + fix.gameObject.activeInHierarchy);
        }
        int fell = 0;
        for (int i = 0; i <= 21; i++)
        {
            var start = i == 21 ? new Vector3(6.8f, 2.3f, -7.3f) : Vector3.Lerp(SavePos, ScenePos, i / 20f); // 21: where the Quest logged a new game
            // Back on known floor first, so one fall does not carry into the next point.
            pl.transform.position = ScenePos; body.position = ScenePos; body.linearVelocity = Vector3.zero;
            for (int w = 0; w < 25; w++) yield return new WaitForFixedUpdate();
            body.linearVelocity = Vector3.zero;
            bool floor = Physics.Raycast(start + Vector3.up * 0.1f, Vector3.down, out var down, 300f, ~0, QueryTriggerInteraction.Ignore);
            bool roof = Physics.Raycast(start, Vector3.up, out var up, 300f, ~0, QueryTriggerInteraction.Ignore);
            pl.transform.position = start; body.position = start; body.linearVelocity = Vector3.zero;
            float end = Time.time + 2f, minY = start.y, fastest = 0f;
            bool jumped = false; var last = start;
            yield return new WaitForFixedUpdate();
            while (Time.time < end)
            {
                minY = Mathf.Min(minY, body.position.y);
                fastest = Mathf.Min(fastest, body.linearVelocity.y);
                if ((body.position - last).magnitude > 5f) jumped = true;
                last = body.position;
                yield return null;
            }
            bool out_ = minY < start.y - 6f || fastest < -25f;
            if (out_) fell++;
            Log("LINE " + (i == 21 ? "QUEST" : (i * 5) + "%") + " start=" + start.ToString("F1") + " floor=" + (floor ? down.collider.name + "@" + down.distance.ToString("F1") : "none") + " roof=" + (roof ? up.collider.name + "@" + up.distance.ToString("F1") : "none")
                + " end=" + body.position.ToString("F1") + " minY=" + minY.ToString("F1") + " fastestFall=" + fastest.ToString("F1") + " teleported=" + jumped + (out_ ? " FELL" : ""));
        }
        Log("LINE RESULT fell=" + fell + " of 22");
    }

    // The real new-game start, followed through the opening: Kill_Other switches the player off, and it
    // comes back 8.35 s later at wherever it stood. FALL_FIX (y -128) sends a falling player to the crystal.
    IEnumerator FallSpawns()
    {
        int fell = 0, opened = 0, atFix = 0;
        for (int i = 0; i < 12; i++)
        {
            Time.captureFramerate = FrameRates[i % FrameRates.Length];
            Hold_Data.HD = Data(SavePos);
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(1 + i % 5);
            var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().FirstOrDefault(p => p.gameObject.scene.IsValid());
            var body = pl.GetComponent<Rigidbody>();
            float end = Time.time + 16f, minY = 999f, fastest = 0f, backAt = 0f;
            bool off = false, back = false, jumped = false;
            Vector3 offPos = Vector3.zero, backPos = Vector3.zero, last = body.position;
            while (Time.time < end)
            {
                bool active = pl.gameObject.activeInHierarchy;
                if (!active && !off) { off = true; offPos = pl.transform.position; }
                if (active && off && !back) { back = true; backPos = pl.transform.position; backAt = Time.time; last = backPos; }
                if (back)
                {
                    minY = Mathf.Min(minY, body.position.y);
                    fastest = Mathf.Min(fastest, body.linearVelocity.y);
                    if ((body.position - last).magnitude > 5f) jumped = true;
                    last = body.position;
                }
                yield return null;
            }
            if (off) opened++;
            bool down = back && (minY < backPos.y - 6f || fastest < -25f || jumped);
            if (down) fell++;
            if (back && (body.position - ScenePos).magnitude < 5f) atFix++;
            Log("OPENING " + i + " switchedOff=" + off + " offAt=" + offPos.ToString("F1") + " backAt=" + backPos.ToString("F1") + " t=" + backAt.ToString("F1") + " end=" + body.position.ToString("F1")
                + " minY=" + minY.ToString("F1") + " fastestFall=" + fastest.ToString("F1") + " teleported=" + jumped + (down ? " FELL" : ""));
            yield return WaitFrames(3 + i % 7);
        }
        Check("opening.runs", opened == 12, "opened=" + opened + " of 12");
        Check("opening.no_fall", fell == 0 && atFix == 0, "fell=" + fell + " crystal=" + atFix);
    }

    // The violet rectangle in Felipe's photos: page by page through the game's own LoadMenu, as Top_bar does,
    // every active graphic of that colour, and what the EventSystem has selected.
    IEnumerator SelectCursor()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var menu = FindObjectOfType<Menus>();
        var hud = menu.SEL.transform.root;
        var main = menu.MENUS[0].transform.parent;
        for (var x = main; x != null; x = x.parent) x.gameObject.SetActive(true);
        var es = UnityEngine.EventSystems.EventSystem.current;
        var plr = FindObjectOfType<Player_Control_scr>();
        plr.Freeze = true; // the laser and the cursor check run with a menu open
        int stray = 0;
        int[] pages = { 0, 1, 2, 3, 4, 1, 3, 1 };
        foreach (var page in pages)
        {
            menu.current_menu = page;
            menu.LoadMenu();
            yield return WaitFrames(30);
            var sel = es != null ? es.currentSelectedGameObject : null;
            bool shown = menu.SEL.gameObject.activeInHierarchy && menu.SEL.enabled;
            if (shown && (sel == null || !sel.activeInHierarchy)) { stray++; Log("SELECT   STRAY on page " + page); }
            Log("SELECT page=" + page + " SEL active=" + menu.SEL.gameObject.activeInHierarchy + " enabled=" + menu.SEL.enabled + " alpha=" + menu.SEL.color.a.ToString("F2")
                + " selected=" + (sel != null ? sel.name + " active=" + sel.activeInHierarchy + " dist=" + Vector3.Distance(menu.SEL.transform.position, sel.transform.position).ToString("F3") : "null"));
            foreach (var g in hud.GetComponentsInChildren<UnityEngine.UI.Graphic>())
                if (g.isActiveAndEnabled && g.color.b > 0.8f && g.color.r < 0.4f && g.color.g < 0.2f)
                {
                    var path = g.name;
                    for (var t = g.transform.parent; t != null && t != hud; t = t.parent) path = t.name + "/" + path;
                    Log("SELECT   violet " + path + " colour=" + g.color + " size=" + g.rectTransform.rect.size + " raycast=" + g.raycastTarget);
                }
        }
        Check("menu.cursor_not_stray", stray == 0, "stray=" + stray + " of " + pages.Length);
        plr.Freeze = false;
        menu.current_menu = -1;
        menu.LoadMenu();
    }

    // A real elevator (ARCHIVES), as shipped and then with the body interpolation forced back on, as before the fix.
    IEnumerator Elevator()
    {
        for (int round = 0; round < 2; round++)
        {
            Hold_Data.HD = Data(Vector3.zero);
            SceneManager.LoadScene("ARCHIVES");
            yield return WaitFrames(30);
            var pl = FindObjectOfType<Player_Control_scr>();
            var body = pl.GetComponent<Rigidbody>();
            var elevator = FindObjectOfType<Elevator_Control>();
            if (elevator == null) { Log("ELEVATOR none found"); yield break; }
            var platform = elevator.transform.parent;
            float settle = Time.time + 1.5f;
            while (Time.time < settle) yield return null;
            yield return new WaitForFixedUpdate();
            var on = platform.position + Vector3.up * 1.5f;
            pl.transform.position = on; body.position = on; body.linearVelocity = Vector3.zero;
            float y0 = platform.position.y, end = Time.time + 14f, gapMin = 999f, gapMax = -999f, fastest = 0f;
            bool busySeen = false;
            while (Time.time < end)
            {
                if (round == 1) body.interpolation = RigidbodyInterpolation.Interpolate;
                busySeen |= elevator.busy;
                float gap = body.position.y - platform.position.y;
                if (busySeen) { gapMin = Mathf.Min(gapMin, gap); gapMax = Mathf.Max(gapMax, gap); }
                fastest = Mathf.Min(fastest, body.linearVelocity.y);
                yield return null;
            }
            float final = body.position.y - platform.position.y;
            bool bad = !busySeen || Mathf.Abs(final) > 4f || fastest < -25f;
            if (round == 0) Check("elevator.real", !bad, "final=" + final.ToString("F2") + " fastestFall=" + fastest.ToString("F1"));
            Log("ELEVATOR " + (round == 0 ? "fixed " : "before ") + elevator.name + " moved=" + busySeen + " platformY " + y0.ToString("F1") + "->" + platform.position.y.ToString("F1")
                + " playerAbovePlatform min=" + gapMin.ToString("F2") + " max=" + gapMax.ToString("F2") + " final=" + final.ToString("F2") + " fastestFall=" + fastest.ToString("F1") + (bad ? " LOST" : ""));
        }
    }

    // The laser's own pick (HudElementAt) over a grid on each button that the pop-up line covered, with an icon
    // in the line so TMP makes its submesh; then the same with the line no longer skipped, as before the fix.
    IEnumerator Buttons()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var gp = FindObjectOfType<LunaVRGameplay>();
        const BindingFlags Any = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var pick = typeof(LunaVRGameplay).GetMethod("HudElementAt", Any);
        var hud = ((System.Collections.Generic.List<RectTransform>)typeof(LunaVRGameplay).GetField("huds", Any).GetValue(gp)).First(h => h != null);
        var popField = typeof(LunaVRGameplay).GetField("popCentred", Any);
        var pop = popField != null ? popField.GetValue(gp) as Component : null;
        Log("BUTTONS hud=" + hud.name + " pop=" + (pop != null ? pop.name : "null"));
        if (pop == null) yield break;
        pop.gameObject.SetActive(true);
        var tm = pop.GetComponent<TMPro.TextMeshProUGUI>();
        tm.color = Color.white;
        tm.text = "Picked up <sprite=0> item";
        string[] paths = { "HUD/QUERY/YES_BUTTON", "HUD/QUERY/NO_BUTTON", "HUD/CRYSTAL/STONE/LVL_BUTTON", "HUD/MAIN/menu1/ITEM2", "HUD/MAIN/menu1/WEP2", "HUD/MAIN/menu1/MAG2", "HUD/MAIN/menu2/SELECTION_1", "HUD/MAIN/menu3/INVERT_BUTTON", "HUD/MAIN/menu4/hud_button", "HUD/MAIN/menu1/ITEM1" };
        for (int round = 0; round < 2; round++)
        {
            if (round == 1) popField.SetValue(gp, null);
            foreach (var path in paths)
            {
                var t = hud.Find(path) as RectTransform;
                if (t == null) { Log("BUTTON " + path + " not found"); continue; }
                var turned = new System.Collections.Generic.List<GameObject>();
                if (path.EndsWith("LVL_BUTTON"))
                {
                    var cursor = hud.Find("HUD/CRYSTAL/SELECT");
                    if (cursor != null) { cursor.gameObject.SetActive(true); turned.Add(cursor.gameObject); cursor.position = t.position; }
                    var levelPage = hud.Find("HUD/CRYSTAL/LEVEL"); // the game shows STONE or LEVEL, never both
                    if (levelPage != null && levelPage.gameObject.activeSelf) { levelPage.gameObject.SetActive(false); yield return WaitFrames(2); }
                }
                for (var x = (Transform)t; x != null && x != hud; x = x.parent) if (!x.gameObject.activeSelf) { x.gameObject.SetActive(true); turned.Add(x.gameObject); }
                yield return WaitFrames(3);
                int ok = 0, total = 0; var thieves = new System.Collections.Generic.Dictionary<string, int>();
                var r = t.rect;
                for (int ix = 0; ix < 15; ix++) for (int iy = 0; iy < 7; iy++)
                {
                    var point = t.TransformPoint(new Vector3(r.xMin + r.width * (ix + 0.5f) / 15f, r.yMin + r.height * (iy + 0.5f) / 7f, 0f));
                    var got = (GameObject)pick.Invoke(gp, new object[] { point });
                    total++;
                    if (got != null && UnityEngine.EventSystems.ExecuteEvents.GetEventHandler<UnityEngine.EventSystems.IPointerClickHandler>(got) == t.gameObject) ok++;
                    else { var n = got != null ? got.name : "nothing"; thieves[n] = (thieves.TryGetValue(n, out var c) ? c : 0) + 1; }
                }
                if (round == 0) Check("laser." + path, ok == total, "clickable=" + ok + "/" + total + " lost to: " + string.Join(", ", thieves.Select(k => k.Key + "=" + k.Value)));
                else Log("BUTTON before " + path + " clickable=" + ok + "/" + total);
                foreach (var g in turned) g.SetActive(false);
                yield return WaitFrames(2);
            }
        }
    }

    // The way Teleport_scr, FallFix, ShadowTower_CON and Act_Button_scr move the player, at both phases of the
    // frame they run in (from Update, or from a physics callback). Two floor points the walk test crossed.
    IEnumerator Teleports()
    {
        for (int round = 0; round < 2; round++)
        {
            Hold_Data.HD = Data(Vector3.zero);
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(3);
            var pl = FindObjectOfType<Player_Control_scr>();
            var body = pl.GetComponent<Rigidbody>();
            float settle = Time.time + 1.5f;
            while (Time.time < settle) yield return null;
            var gameplay = FindObjectOfType<LunaVRGameplay>();
            Log("TELEPORT round " + (round == 0 ? "as shipped" : "port off (the game alone)") + " interpolation=" + body.interpolation + " interpolator=" + (pl.GetComponent<InterpolationObjectController>() != null ? pl.GetComponent<InterpolationObjectController>().enabled.ToString() : "none"));
            if (round == 1) gameplay.enabled = false;
            var a = new Vector3(62.3f, 12.5f, -65.7f); var b = new Vector3(62.3f, 12.5f, -61.3f);
            int lost = 0;
            for (int i = 0; i < 16; i++)
            {
                yield return WaitFrames(i % 5);
                if (i % 2 == 1) yield return new WaitForFixedUpdate();
                var target = (i / 2) % 2 == 0 ? b : a;
                pl.transform.position = target;
                var c = pl.GetComponent<InterpolationObjectController>();
                if (c != null) c.ResetTransforms();
                yield return new WaitForFixedUpdate();
                float end = Time.time + 0.4f, worst = 0f;
                while (Time.time < end)
                {
                    worst = Mathf.Max(worst, Vector2.Distance(new Vector2(pl.transform.position.x, pl.transform.position.z), new Vector2(target.x, target.z)));
                    yield return null;
                }
                float off = Vector2.Distance(new Vector2(body.position.x, body.position.z), new Vector2(target.x, target.z));
                if (off > 1.5f || worst > 1.5f) lost++;
            }
            if (round == 0) Check("teleport.from_update", lost == 0, "lost=" + lost + " of 16");
            else Log("TELEPORT game alone lost=" + lost + " of 16");
        }
    }

    // Ladder_scr (physics phase) and Elevator_Control (each frame) move the transform in small steps.
    IEnumerator Ladder()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        var pl = FindObjectOfType<Player_Control_scr>();
        var body = pl.GetComponent<Rigidbody>();
        float settle = Time.time + 1.5f;
        while (Time.time < settle) yield return null;
        float keep = pl.gravity;
        for (int mode = 0; mode < 1; mode++)
        {
            pl.gravity = 0f; pl.grounded = true; body.linearVelocity = Vector3.zero;
            float y0 = body.position.y, expected = 0f, end = Time.time + 1.5f;
            while (Time.time < end)
            {
                if (mode == 0) yield return new WaitForFixedUpdate(); else yield return null;
                float step = mode == 0 ? 3f * Time.smoothDeltaTime : 0.05f;
                pl.transform.Translate(0f, step, 0f);
                expected += step;
            }
            yield return new WaitForFixedUpdate();
            float gained = body.position.y - y0;
            Check("ladder.climb", gained / expected >= 0.95f, "expected=" + expected.ToString("F2") + " gained=" + gained.ToString("F2"));
            pl.gravity = keep;
            float land = Time.time + 2f;
            while (Time.time < land) yield return null;
        }
    }

    // The TOWER coffin boat: the player is a child of the animated MOVE, arriving from CAVE's GOTO_LEVEL. As
    // shipped, then with the port's gameplay off (no RideMovingParent), where the player used to fall off.
    IEnumerator BoatRide()
    {
        for (int round = 0; round < 2; round++)
        {
            Hold_Data.HD = Data(new Vector3(88f, -31f, 104f));
            SceneManager.LoadScene("TOWER");
            yield return WaitFrames(30);
            var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().FirstOrDefault(p => p.gameObject.scene.IsValid());
            var body = pl.GetComponent<Rigidbody>();
            var ride = FindObjectsOfType<Boat_Ride>().FirstOrDefault(b => !b.SKIP);
            if (ride == null) { Log("BOAT no Boat_Ride"); yield break; }
            var anim = ride.BOAT.GetComponent<Animation>();
            if (round == 1) FindObjectOfType<LunaVRGameplay>().enabled = false;
            float settle = Time.time + 3f;
            while (Time.time < settle && !anim.isPlaying) yield return null;
            bool autoStarted = anim.isPlaying;
            if (!anim.isPlaying) anim.Play();
            yield return null;
            var parentName = pl.transform.parent != null ? pl.transform.parent.name : "none";
            float limit = Time.time + 100f, worstH = 0f, minY = 999f, maxY = -999f, fastest = 0f;
            var startPos = ride.BOAT.position;
            bool kinematicSeen = false;
            while (Time.time < limit && anim.isPlaying && pl != null)
            {
                var d = body.position - ride.BOAT.position;
                worstH = Mathf.Max(worstH, new Vector2(d.x, d.z).magnitude);
                minY = Mathf.Min(minY, d.y); maxY = Mathf.Max(maxY, d.y);
                fastest = Mathf.Min(fastest, body.linearVelocity.y);
                kinematicSeen |= body.isKinematic;
                yield return null;
            }
            bool bad = worstH > 4f || minY < -3f || maxY > 6f || fastest < -25f;
            if (round == 0) Check("boat.stays_on", !bad, "horizontal=" + worstH.ToString("F2") + " vertical=" + minY.ToString("F2") + ".." + maxY.ToString("F2"));
            Log("BOAT " + (round == 0 ? "as shipped" : "port off") + " autoStarted=" + autoStarted + " parent=" + parentName + " boat " + startPos.ToString("F1") + "->" + ride.BOAT.position.ToString("F1")
                + " player from boat: horizontal max=" + worstH.ToString("F2") + " vertical " + minY.ToString("F2") + ".." + maxY.ToString("F2") + " fastestFall=" + fastest.ToString("F1") + " kinematic=" + kinematicSeen + (bad ? " LOST" : ""));
        }
    }

    static string DescribeIcon(POP_text_scr pop, TMPro.TextMeshProUGUI tm)
    {
        var text = "text='" + tm.text + "' sprites=" + tm.textInfo.spriteCount + " alpha=" + tm.color.a.ToString("F2") + " asset=" + (tm.spriteAsset != null ? tm.spriteAsset.name : "null");
        var dflt = TMPro.TMP_Settings.defaultSpriteAsset;
        text += " default=" + (dflt != null ? dflt.name + "/" + dflt.spriteCharacterTable.Count + " mat=" + (dflt.material != null ? dflt.material.name + ":" + dflt.material.shader.name + ":tex=" + (dflt.material.mainTexture != null ? dflt.material.mainTexture.name : "NULL") : "NULL") + " sheet=" + (dflt.spriteSheet != null ? dflt.spriteSheet.name : "NULL") : "null");
        foreach (var sub in pop.GetComponentsInChildren<TMPro.TMP_SubMeshUI>(true))
        {
            var m = sub.materialForRendering;
            text += " | sub go=" + sub.gameObject.activeInHierarchy + " on=" + sub.enabled + " verts=" + (sub.mesh != null ? sub.mesh.vertexCount : -1) + " cull=" + sub.canvasRenderer.cull + " crAlpha=" + sub.canvasRenderer.GetAlpha().ToString("F2")
                    + " mat=" + (m != null ? m.name + ":" + m.shader.name + ":supported=" + m.shader.isSupported + ":tex=" + (m.mainTexture != null ? m.mainTexture.name : "NULL") : "NULL") + " subAsset=" + (sub.spriteAsset != null ? sub.spriteAsset.name : "null") + " mainTexture=" + (sub.mainTexture != null ? sub.mainTexture.name : "NULL");
        }
        return text;
    }

    // Two pickups in a row: the second line arrives while the first is showing, and POP_text_scr.Reset switches
    // off the children of the line, the icon among them. As shipped, then with the port off.
    IEnumerator PickupIcon()
    {
        for (int round = 0; round < 2; round++)
        {
            Hold_Data.HD = Data(Vector3.zero);
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(3);
            float settle = Time.time + 3f;
            while (Time.time < settle) yield return null;
            var pop = FindObjectOfType<POP_text_scr>();
            var tm = pop.GetComponent<TMPro.TextMeshProUGUI>();
            if (round == 1) FindObjectOfType<LunaVRGameplay>().enabled = false;
            int good = 0;
            const int Tries = 10;
            for (int i = 0; i < Tries; i++)
            {
                pop.POP("Item <sprite=" + (i % 5) + "> one", 1f, 0);
                yield return WaitFrames(i % 2 == 0 ? 3 : 10);
                // In a build TMP leaves this object's default name, which is what POP's own re-enable misses.
                foreach (var sub in pop.GetComponentsInChildren<TMPro.TMP_SubMeshUI>(true)) sub.gameObject.name = "New Game Object";
                pop.POP("Item <sprite=" + ((i + 1) % 5) + "> two", 1f, 0);
                yield return WaitFrames(4);
                bool shown = pop.GetComponentsInChildren<TMPro.TMP_SubMeshUI>(true).Any(sub => sub.gameObject.activeInHierarchy && sub.enabled && sub.mesh != null && sub.mesh.vertexCount > 0 && sub.materialForRendering != null && sub.materialForRendering.mainTexture != null);
                if (shown) good++; // textInfo.spriteCount stays 0 here, the submesh is the proof
                if (i < 3) Log("PICKUP detail try " + i + " round " + round + " " + DescribeIcon(pop, tm));
                yield return WaitFrames(30);
            }
            // The case in Felipe's video: a single pickup, later, on its own (gold, sprite 0).
            yield return WaitFrames(300);
            pop.POP("2 <sprite=0> ACQUIRED", 1f, 0);
            yield return WaitFrames(10);
            bool alone = pop.GetComponentsInChildren<TMPro.TMP_SubMeshUI>(true).Any(sub => sub.gameObject.activeInHierarchy && sub.enabled && sub.mesh != null && sub.mesh.vertexCount > 0 && sub.materialForRendering != null && sub.materialForRendering.mainTexture != null);
            Log("PICKUP detail alone round " + round + " " + DescribeIcon(pop, tm));
            if (round == 0)
            {
                Check("pickup.icon_second_in_a_row", good == Tries, "shown=" + good + " of " + Tries);
                Check("pickup.icon_later_alone", alone, "gold icon shown=" + alone);
            }
            else Log("PICKUP game alone: in a row shown=" + good + " of " + Tries + "; later alone shown=" + alone);
        }
    }

    // POP_TEXT is the parent of the reading text, the warp and death effects: it has to stay where the game put
    // it, and the normal line still reads at the centre of the panel.
    IEnumerator PopLayout()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var pop = FindObjectOfType<POP_text_scr>();
        var rt = (RectTransform)pop.transform;
        var tm = pop.GetComponent<TMPro.TextMeshProUGUI>();
        Check("pop.stays_where_the_game_put_it", Vector2.Distance(rt.anchoredPosition, new Vector2(-420f, -220f)) < 1f && rt.anchorMin == Vector2.zero && rt.sizeDelta == new Vector2(200f, 50f),
              "pos=" + rt.anchoredPosition + " anchors=" + rt.anchorMin + " size=" + rt.sizeDelta);
        pop.POP("A short line", 1f, 0);
        yield return WaitFrames(5);
        tm.ForceMeshUpdate();
        var root = rt.GetComponentInParent<Canvas>().rootCanvas.transform;
        var centre = root.InverseTransformPoint(rt.TransformPoint(tm.textBounds.center));
        Check("pop.line_is_centred", Mathf.Abs(centre.x) < 40f && Mathf.Abs(centre.y) < 80f, "centre=" + centre.ToString("F0"));
        yield return WaitFrames(90);
        pop.POP("A note to read\n\nSecond line of it", 1f, 9);
        yield return WaitFrames(30);
        var extra = pop.EX.transform;
        var at = root.InverseTransformPoint(extra.position);
        var expected = root.InverseTransformPoint(rt.position);
        Check("pop.reading_text_follows_the_game", Vector2.Distance(at, expected) < 2f, "extra=" + at.ToString("F0") + " line origin=" + expected.ToString("F0"));
        var pivotAt = root.InverseTransformPoint(rt.TransformPoint(Vector3.zero));
        Check("pop.reading_text_not_moved_up_right", pivotAt.x < -200f, "pop origin=" + pivotAt.ToString("F0"));
    }

    // The main menu's cameras keep the field of view their scene gives them, even when something (VR, in
    // the headset) changed it before the theater routes them: once as loaded, once with every camera forced
    // to 100 degrees right after the load, as XR does.
    // The main menu after quitting a save (Felipe, Builds 85 and 87): on the Quest the menu's cameras already read
    // the headset's 100 degrees when the port first looks at them, so a value remembered at load is the wrong one.
    // Here: unroute each theater camera, force 100, let the port remember that, and check it is routed back with
    // the scene file's value; then that a later rewrite is held off.
    IEnumerator MenuFieldOfView()
    {
        Hold_Data.HD = null;
        SceneManager.LoadScene("MainMenu");
        yield return WaitFrames(20);
        var theater = FindObjectOfType<LunaTheater>();
        var cams = Camera.allCameras.Where(c => c.targetTexture == theater.Texture && c.name != "TheaterOverlay").ToList();
        Check("menu.fov.cameras_found", cams.Count > 0, "routed=" + string.Join(",", cams.Select(c => c.name)));
        var want = new System.Collections.Generic.Dictionary<Camera, float>();
        foreach (var c in cams)
        {
            bool listed = LunaTheater.SceneFileFov(c, out var fov);
            Check("menu.fov.listed." + c.name, listed, "path=" + c.gameObject.scene.name + "/" + LunaTheater.IndexedPath(c.transform) + " file=" + fov);
            want[c] = fov;
            c.targetTexture = null;
            c.fieldOfView = 100f;
        }
        theater.RememberFieldsOfView(); // what the Quest saw: the headset's value at load
        yield return WaitFrames(5);
        foreach (var c in cams)
            Check("menu.fov.restored." + c.name, c.targetTexture == theater.Texture && Mathf.Abs(c.fieldOfView - want[c]) < 0.5f, "after a remembered 100: " + c.fieldOfView.ToString("F1") + " (file " + want[c] + ")");
        foreach (var c in cams) c.fieldOfView = 100f;
        yield return WaitFrames(3);
        foreach (var c in cams)
            Check("menu.fov.held." + c.name, Mathf.Abs(c.fieldOfView - want[c]) < 0.5f, "after a later 100: " + c.fieldOfView.ToString("F1"));
        // The game's own zoom (the new-game intro animates SCENE_CAM 65 -> 35 -> 25, Felipe's Build 91 log) is the game's:
        // it stays, and only the headset's 100 is undone, back to that zoom.
        foreach (var c in cams) c.fieldOfView = 35f;
        yield return WaitFrames(3);
        foreach (var c in cams)
            Check("menu.fov.game_zoom_kept." + c.name, Mathf.Abs(c.fieldOfView - 35f) < 0.5f, "after the game set 35: " + c.fieldOfView.ToString("F1"));
        foreach (var c in cams) c.fieldOfView = 100f;
        yield return WaitFrames(3);
        foreach (var c in cams)
            Check("menu.fov.headset_undone_to_zoom." + c.name, Mathf.Abs(c.fieldOfView - 35f) < 0.5f, "after the headset's 100 over the zoom: " + c.fieldOfView.ToString("F1"));
    }

    // Felipe (Build 91 video): during the new-game intro the menu laser kept showing and vanishing; the intro has
    // nothing to click. The theater's laser is wanted only while something on the screen can be clicked.
    IEnumerator TheaterLaser()
    {
        Hold_Data.HD = null;
        SceneManager.LoadScene("MainMenu");
        yield return WaitFrames(30);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var theater = FindObjectOfType<LunaTheater>();
        var pointer = typeof(LunaTheater).GetField("pointer", AnyField).GetValue(theater) as Behaviour;
        var clickable = FindObjectsOfType<Selectable>().Where(x => x.IsInteractable()).ToList();
        Log("LASER clickable on the title: " + string.Join(",", clickable.Select(x => x.name)));
        yield return WaitFrames(20);
        Check("laser.title_shows", pointer != null && pointer.enabled, "pointer enabled=" + (pointer != null && pointer.enabled) + " with " + clickable.Count + " clickable");
        // A cut scene: nothing to click on screen.
        var turned = clickable.Select(x => x.gameObject).Where(g => g.activeSelf).ToList();
        foreach (var g in turned) g.SetActive(false);
        yield return WaitFrames(30);
        Check("laser.cutscene_hides", pointer != null && !pointer.enabled, "pointer enabled=" + (pointer != null && pointer.enabled) + " with nothing clickable");
        foreach (var g in turned) g.SetActive(true);
        yield return WaitFrames(30);
        Check("laser.menu_back_shows", pointer != null && pointer.enabled, "pointer enabled=" + (pointer != null && pointer.enabled));
        // Every theater page with something to click keeps the laser: settings and save slots on the title, the
        // character creation (name field) and the game over screen.
        var tm = Resources.FindObjectsOfTypeAll<Menus>().FirstOrDefault(m => m.gameObject.scene.IsValid());
        if (tm != null)
        {
            foreach (var (click, page) in new[] { (3, "settings"), (1, "main") })
            {
                tm.Click(click);
                yield return WaitFrames(30);
                Check("laser.title_" + page, pointer.enabled, "pointer enabled=" + pointer.enabled + " clickable=" + FindObjectsOfType<Selectable>().Count(x => x.IsInteractable()));
            }
        }
        foreach (var scene in new[] { "CHAR_CREATE", "Gameover" })
        {
            Hold_Data.HD = scene == "Gameover" ? Data(Vector3.zero) : null;
            SceneManager.LoadScene(scene);
            yield return WaitFrames(30);
            float wait = Time.time + 4f;
            while (Time.time < wait) yield return null;
            theater = FindObjectOfType<LunaTheater>();
            pointer = typeof(LunaTheater).GetField("pointer", AnyField).GetValue(theater) as Behaviour;
            var names = FindObjectsOfType<Selectable>().Where(x => x.IsInteractable()).Select(x => x.name).Take(8);
            Check("laser." + scene, pointer != null && pointer.enabled, "pointer enabled=" + (pointer != null && pointer.enabled) + " clickable: " + string.Join(",", names));
        }
    }

    // Felipe (Build 91 video): after a new game the sword floated above the HUD. The port puts HANDS at the head plus
    // the game's HAND_offset; the game sets that offset in Start from where HANDS and HEAD stand (the opening moves
    // them), and Head_Bob used to pull it back to zero every physics step. With Head_Bob off it stayed.
    // The new game's opening (the hand out of the ground, PITT_A1/Opening). Felipe (2026-11-13): in the headset the hand is
    // always somewhat to the side, and differently on the first launch and after a restart. The opening's camera turns
    // from the headset's forward, which is wherever the headset faced when the game started. With the head turned 0, 40
    // and -90 degrees from that forward: from the first frame that is not black the hand must be ahead (under 6 degrees),
    // the view must not turn by itself (the head holds still), and no frame may stall (LESSONS 42).
    IEnumerator OpeningFacing()
    {
        var frames = System.Environment.GetEnvironmentVariable("LUNA_PROBE_FRAMES");
        foreach (float headYaw in new[] { 0f, 40f, -90f })
        {
            // The headset position counts from where it was when the game started (Device origin): about zero.
            var pose = (Quaternion.Euler(0f, headYaw, 0f), Vector3.zero);
            LunaHeadTracker.TestPose = () => pose;
            Hold_Data.HD = Data(SavePos);
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(3);
            var opening = Resources.FindObjectsOfTypeAll<Transform>().FirstOrDefault(t => t.name == "Opening" && t.gameObject.scene.IsValid());
            if (opening == null) { Check("opening.found", false); yield break; }
            string dir = string.IsNullOrEmpty(frames) ? null : System.IO.Path.Combine(frames, "head" + headYaw.ToString("F0"));
            if (dir != null) System.IO.Directory.CreateDirectory(dir);
            float worstYaw = 0f, worstTurn = 0f, firstShown = -1f, lastViewYaw = float.NaN;
            var frameMs = new System.Collections.Generic.List<float>();
            int frame = 0, shown = 0;
            float end = Time.time + 8f, last = Time.realtimeSinceStartup;
            while (Time.time < end && opening != null && opening.gameObject.activeInHierarchy)
            {
                yield return null;
                frame++;
                float now = Time.realtimeSinceStartup; frameMs.Add((now - last) * 1000f); last = now;
                if (opening == null || !opening.gameObject.activeInHierarchy) break;
                if (dir != null && frame % 3 == 0) ShotHud(System.IO.Path.Combine(dir, (frame / 3).ToString("D4") + ".png"), true);
                var view = opening.GetComponentsInChildren<Camera>().FirstOrDefault(c => c.isActiveAndEnabled);
                // The hand alone; every frame from the one the opening's camera draws first (stricter than from the fade).
                var hand = opening.GetComponentsInChildren<Renderer>().FirstOrDefault(r => r.name == "HAND");
                if (view == null || hand == null) continue;
                Vector3 to = hand.bounds.center - view.transform.position, fwd = view.transform.forward;
                shown++;
                if (firstShown < 0f) firstShown = Time.timeSinceLevelLoad;
                float yaw = Vector3.SignedAngle(Vector3.ProjectOnPlane(fwd, Vector3.up), Vector3.ProjectOnPlane(to, Vector3.up), Vector3.up);
                if (Mathf.Abs(yaw) > Mathf.Abs(worstYaw)) worstYaw = yaw;
                float viewYaw = view.transform.eulerAngles.y;
                if (!float.IsNaN(lastViewYaw)) worstTurn = Mathf.Max(worstTurn, Mathf.Abs(Mathf.DeltaAngle(lastViewYaw, viewYaw)));
                lastViewYaw = viewYaw;
                if (frame % 72 == 0) Log("OPENING head=" + headYaw + " t=" + Time.timeSinceLevelLoad.ToString("F1") + " hand yaw from view=" + yaw.ToString("F1") + " view yaw=" + viewYaw.ToString("F1"));
            }
            frameMs.Sort();
            float median = frameMs.Count > 0 ? frameMs[frameMs.Count / 2] : 0f, worstMs = frameMs.Count > 0 ? frameMs[frameMs.Count - 1] : 0f;
            string tag = "head" + headYaw.ToString("F0");
            Check("opening.hand_ahead." + tag, shown > 0 && Mathf.Abs(worstYaw) < 6f, "worst yaw from the view to the hand=" + worstYaw.ToString("F1") + " deg over " + shown + " frames, first shown at " + firstShown.ToString("F2") + " s");
            Check("opening.no_jump." + tag, shown > 0 && worstTurn < 0.5f, "largest turn of the view between two frames with the head still=" + worstTurn.ToString("F2") + " deg");
            // Writing a frame for a video costs the next frame: the stall is judged only on runs that record none.
            if (dir == null) Check("opening.no_stall." + tag, worstMs < Mathf.Max(100f, median * 6f), "frame ms median=" + median.ToString("F1") + " worst=" + worstMs.ToString("F1"));
            float wait = Time.time + 2f;
            while (Time.time < wait) yield return null;
        }
        // Back to a straight headset for the cases after this one.
        LunaHeadTracker.TestPose = () => (Quaternion.identity, Vector3.zero);
        LunaHeadTracker.Recentre();
        yield return WaitFrames(3);
        LunaHeadTracker.TestPose = null;
    }

    IEnumerator HandsAtHead()
    {
        var offField = typeof(Player_Control_scr).GetField("HAND_offset", AnyField);
        // A new game: the opening (the hand out of the ground) runs, as in FallSpawns.
        Hold_Data.HD = Data(SavePos);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float end = Time.time + 14f;
        while (Time.time < end) yield return null;
        var pl = FindObjectOfType<Player_Control_scr>();
        var cam = FindObjectOfType<LunaHeadTracker>().transform;
        yield return WaitFrames(5);
        var off = (Vector3)offField.GetValue(pl);
        float gap = Vector3.Distance(pl.HANDS.transform.position, cam.position);
        Check("hands.after_opening", off.magnitude < 0.05f && gap < 0.1f, "HAND_offset=" + off.ToString("F3") + " hands from the head " + gap.ToString("F3") + " m");
        // Whatever the game left in it: the weapon is at the head a few frames later.
        offField.SetValue(pl, new Vector3(0f, 0.6f, 0f));
        yield return WaitFrames(5);
        off = (Vector3)offField.GetValue(pl);
        gap = Vector3.Distance(pl.HANDS.transform.position, cam.position);
        Check("hands.offset_left_over", off.magnitude < 0.05f && gap < 0.1f, "HAND_offset=" + off.ToString("F3") + " hands from the head " + gap.ToString("F3") + " m");
    }

    // A level loading from the warp map: the menus must stop drawing. As shipped, then with the port off.
    IEnumerator WarpLoading()
    {
        for (int round = 0; round < 2; round++)
        {
            Hold_Data.HD = Data(Vector3.zero);
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(3);
            float settle = Time.time + 3f;
            while (Time.time < settle) yield return null;
            var gp = FindObjectOfType<LunaVRGameplay>();
            const BindingFlags Any = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            var hud = ((System.Collections.Generic.List<RectTransform>)typeof(LunaVRGameplay).GetField("huds", Any).GetValue(gp)).First(h => h != null);
            var crystal = hud.Find("HUD/CRYSTAL");
            for (var x = crystal; x != null && x != hud.parent; x = x.parent) x.gameObject.SetActive(true);
            var warp = crystal.Find("WARP");
            foreach (var other in new[] { "STONE", "WARP", "LEVEL" }) { var t = crystal.Find(other); if (t != null) t.gameObject.SetActive(other == "WARP"); }
            var button = warp.GetComponentsInChildren<UnityEngine.UI.Button>().First();
            var image = button.GetComponent<UnityEngine.UI.Graphic>();
            // A selected button, as after a click: the violet cursor (HUD/.../SELECT) sits on it.
            UnityEngine.EventSystems.EventSystem.current.SetSelectedGameObject(button.gameObject);
            yield return WaitFrames(5);
            float before = image.canvasRenderer.GetInheritedAlpha();
            if (round == 1) gp.enabled = false;
            var load = Resources.FindObjectsOfTypeAll<Level_Load_Effect>().First(l => l.gameObject.scene.IsValid());
            load.LEVEL = "PITT_A1";
            load.Build_Override = -1;
            for (var x = load.transform; x != null && x != hud.parent; x = x.parent) x.gameObject.SetActive(true);
            float wait = Time.realtimeSinceStartup + 0f; int frames = 0;
            while (frames++ < 40) yield return null; // the scene load starts 1 s after the effect
            float during = image != null ? image.canvasRenderer.GetInheritedAlpha() : -1f;
            if (round == 0) Check("warp.menus_hidden_while_loading", before > 0.9f && during < 0.05f, "alpha before=" + before.ToString("F2") + " during=" + during.ToString("F2"));
            // The menus stop drawing by alpha, so the selected button stays active: the violet cursor stayed alone on
            // the loading screen (Felipe, the notebook build, 2026-11-13; LESSONS 40).
            var cursorsShown = hud.GetComponentsInChildren<UnityEngine.UI.Image>(true)
                .Where(i => i.name == "SELECT" && i.enabled && i.gameObject.activeInHierarchy && i.canvasRenderer.GetInheritedAlpha() > 0.05f)
                .Select(i => i.transform.parent != null ? i.transform.parent.name + "/SELECT" : "SELECT").ToArray();
            if (round == 0) Check("warp.cursor_hidden_while_loading", cursorsShown.Length == 0, "cursors shown=[" + string.Join(",", cursorsShown) + "]");
            else Log("WARP game alone alpha before=" + before.ToString("F2") + " during=" + during.ToString("F2"));
            float end = Time.time + 8f;
            while (Time.time < end) yield return null;
        }
    }

    // Violet graphics on screen that do not frame the selected button: the game's SELECT cursor (any violet box)
    // shown with nothing selected, on a hidden button, or with a size or place that is not the selected button's.
    static System.Collections.Generic.List<string> StrayViolet(string where)
    {
        var es = UnityEngine.EventSystems.EventSystem.current;
        var sel = es != null ? es.currentSelectedGameObject : null;
        var selRt = sel != null && sel.activeInHierarchy ? sel.GetComponent<RectTransform>() : null;
        var stray = new System.Collections.Generic.List<string>();
        // A disabled root canvas draws nothing (the port switches off MAUS_CANVAS, the game's mouse cursor).
        foreach (var canvas in FindObjectsOfType<Canvas>().Where(c => c.isRootCanvas && c.isActiveAndEnabled))
            foreach (var g in canvas.GetComponentsInChildren<Graphic>())
            {
                if (!g.isActiveAndEnabled || g.color.a < 0.05f || g.canvasRenderer.GetInheritedAlpha() < 0.05f || g.canvasRenderer.cull) continue;
                bool violet = g.name == "SELECT" || (g.color.b > 0.8f && g.color.r < 0.4f && g.color.g < 0.2f);
                if (!violet || g is TMP_Text) continue;
                var path = g.name;
                for (var t = g.transform.parent; t != null; t = t.parent) path = t.name + "/" + path;
                var r = g.rectTransform;
                var parent = r.parent;
                Vector2 Local(Vector3 world) => parent != null ? (Vector2)parent.InverseTransformPoint(world) : (Vector2)world;
                Vector2 size = r.rect.size, centre = Local(r.TransformPoint(r.rect.center));
                string detail = where + " " + path + " size=" + size.ToString("F0");
                if (selRt == null) { stray.Add(detail + " selected=" + (sel != null ? sel.name + "(hidden)" : "none")); continue; }
                var c = new Vector3[4];
                selRt.GetWorldCorners(c);
                Vector2 a = Local(c[0]), b = Local(c[2]);
                Vector2 want = new Vector2(Mathf.Abs(b.x - a.x), Mathf.Abs(b.y - a.y)) + new Vector2(12f, 12f), wantCentre = (a + b) / 2f;
                bool fits = Mathf.Abs(size.x - want.x) < 10f && Mathf.Abs(size.y - want.y) < 10f && Vector2.Distance(centre, wantCentre) < 10f;
                if (!fits) stray.Add(detail + " on " + sel.name + " want=" + want.ToString("F0") + " off by " + Vector2.Distance(centre, wantCentre).ToString("F0"));
            }
        return stray;
    }

    // Quitting to the title from the pause menu (Felipe, notebook build, 2026-11-13): the violet cursor stayed alone on
    // the loading screen, every time. The game closes its menus (current_menu = -1) before the load, unlike the warp map.
    IEnumerator QuitToTitle()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var menu = FindObjectOfType<Menus>();
        var mainT = menu.GetComponentsInChildren<Transform>(true).First(t => t.name == "MAIN");
        for (var x = mainT; x != null; x = x.parent) x.gameObject.SetActive(true);
        FindObjectOfType<Player_Control_scr>().Freeze = true; // the pause menu is open
        menu.current_menu = 0;
        menu.LoadMenu();
        yield return WaitFrames(10);
        menu.Click(49); // EXIT: "Exit to Menu?", YES selected
        yield return WaitFrames(30);
        var before = StrayViolet("query");
        Log("QUIT on the query: stray=[" + string.Join(" | ", before) + "]");
        menu.Click(28); // YES
        // The laser must go at once: a check a few times a second left it on for a moment (Felipe's Quest, 2026-11-13).
        yield return WaitFrames(2);
        var gpNow = FindObjectOfType<LunaVRGameplay>();
        var pointerNow = typeof(LunaVRGameplay).GetField("pointer", AnyField).GetValue(gpNow) as Behaviour;
        Check("quit.laser_off_at_once", pointerNow == null || !pointerNow.enabled, "pointer enabled 2 frames after YES=" + (pointerNow != null && pointerNow.enabled));
        yield return WaitFrames(8);
        var soon = StrayViolet("loading+10");
        yield return WaitFrames(30);
        var later = StrayViolet("loading+40");
        Check("quit.cursor_hidden_while_loading", soon.Count == 0 && later.Count == 0, "stray=[" + string.Join(" | ", soon.Concat(later)) + "]");
        // The port's own lilac laser (line, dot and grip) is drawn only with a headset, so the shots never show it:
        // check the pointer itself is off while the level loads.
        var gp = FindObjectOfType<LunaVRGameplay>();
        var pointer = typeof(LunaVRGameplay).GetField("pointer", AnyField).GetValue(gp) as Behaviour;
        Log("QUIT player frozen=" + FindObjectOfType<Player_Control_scr>().Freeze + " load active=" + (FindObjectOfType<Level_Load_Effect>() != null));
        Check("quit.laser_off_while_loading", pointer == null || !pointer.enabled, "pointer enabled=" + (pointer != null && pointer.enabled));
        float end = Time.time + 6f;
        while (Time.time < end) yield return null;
    }

    // The game's cursor glides to a new selection in a coroutine (Menus.SEL_BOUNCE) guarded by SEL_BB. When the HUD goes
    // inactive mid-glide the coroutine dies with SEL_BB still true, and the cursor never moves again in that scene: on the
    // first launch it stayed under SETTINGS while YES was selected (Felipe's Quest photos, 2026-11-13; LESSONS 41).
    IEnumerator CursorGlideCut()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var menu = FindObjectOfType<Menus>();
        var mainT = menu.GetComponentsInChildren<Transform>(true).First(t => t.name == "MAIN");
        for (var x = mainT; x != null; x = x.parent) x.gameObject.SetActive(true);
        var plr = FindObjectOfType<Player_Control_scr>();
        plr.Freeze = true;
        menu.current_menu = 0;
        menu.LoadMenu();
        yield return WaitFrames(30);
        menu.Click(3); // SETTINGS: the selection moves, the glide starts
        yield return null;
        menu.gameObject.SetActive(false); // the HUD goes away mid-glide
        yield return WaitFrames(3);
        menu.gameObject.SetActive(true);
        yield return WaitFrames(5);
        menu.Click(49); // EXIT: "Exit to Menu?", YES selected
        yield return WaitFrames(60);
        var es = UnityEngine.EventSystems.EventSystem.current;
        var sel = es.currentSelectedGameObject;
        float gap = sel != null ? Vector3.Distance(menu.SEL.transform.position, sel.transform.position) : -1f;
        var stray = StrayViolet("after a cut glide");
        Check("cursor.follows_after_cut_glide", sel != null && gap < 0.05f && stray.Count == 0, "selected=" + (sel != null ? sel.name : "none") + " gap=" + gap.ToString("F3") + " stray=[" + string.Join(" | ", stray) + "]");
        menu.current_menu = -1;
        menu.LoadMenu();
        plr.Freeze = false;
    }

    // The first launch after an install (Felipe, notebook build, 2026-11-13): in the game's own menu, the violet cursor
    // stretched over several buttons and a violet box under SETTINGS on the settings page; gone after a restart. A fresh
    // install has no SETTINGS.MIDNIGHT and no PlayerPrefs. Round 0 starts without them, round 1 with what round 0 wrote.
    static readonly string[] FirstLaunchPrefs = { "LunaVR_WalkByDefault", "LunaVR_SnapAngle30", "I2 Language", "Volume", "GAMMA", "AEST" };

    IEnumerator FirstLaunch()
    {
        string settings = Lunacid.VR.LunacidFileSystemHelper.GetSavePath("SETTINGS.MIDNIGHT"), kept = settings + ".probe_kept";
        bool had = System.IO.File.Exists(settings);
        if (had) System.IO.File.Copy(settings, kept, true);
        var prefs = FirstLaunchPrefs.Where(PlayerPrefs.HasKey).ToDictionary(k => k, k => (PlayerPrefs.GetString(k, null), PlayerPrefs.GetInt(k, int.MinValue), PlayerPrefs.GetFloat(k, float.NaN)));
        try
        {
            if (had) System.IO.File.Delete(settings);
            foreach (var k in FirstLaunchPrefs) PlayerPrefs.DeleteKey(k);
            for (int round = 0; round < 2; round++)
            {
                string tag = round == 0 ? "first" : "second";
                bool fresh = !System.IO.File.Exists(settings);
                Hold_Data.HD = Data(Vector3.zero);
                SceneManager.LoadScene("PITT_A1");
                yield return WaitFrames(3);
                float settle = Time.time + 3f;
                while (Time.time < settle) yield return null;
                var menu = FindObjectOfType<Menus>();
                var plr = FindObjectOfType<Player_Control_scr>();
                // As the game opens its pause menu (Menu button): frozen, page 0, its first button selected.
                plr.Freeze = true;
                menu.current_menu = 0;
                menu.LoadMenu();
                yield return WaitFrames(30);
                var stray = StrayViolet(tag + ".pause");
                ShotHud(tag + "_pause");
                menu.Click(3); // SETTINGS
                yield return WaitFrames(30);
                stray.AddRange(StrayViolet(tag + ".settings"));
                ShotHud(tag + "_settings");
                menu.current_menu = -1;
                menu.LoadMenu();
                plr.Freeze = false;
                yield return WaitFrames(10);
                Check("first_launch.cursor_fits." + tag, stray.Count == 0, "settings file at start=" + !fresh + " stray=[" + string.Join(" | ", stray) + "]");
            }
        }
        finally
        {
            if (had) System.IO.File.Copy(kept, settings, true);
            if (had) System.IO.File.Delete(kept);
            foreach (var k in FirstLaunchPrefs) PlayerPrefs.DeleteKey(k);
            foreach (var kv in prefs)
            {
                if (kv.Value.Item1 != null) PlayerPrefs.SetString(kv.Key, kv.Value.Item1);
                else if (kv.Value.Item2 != int.MinValue) PlayerPrefs.SetInt(kv.Key, kv.Value.Item2);
                else PlayerPrefs.SetFloat(kv.Key, kv.Value.Item3);
            }
            PlayerPrefs.Save();
        }
    }

    // Jump, and a drop from 8 m at several frame rates: the body lands on the floor, not through it.
    IEnumerator JumpAndFall()
    {
        for (int i = 0; i < 4; i++)
        {
            Time.captureFramerate = FrameRates[i];
            Hold_Data.HD = Data(Vector3.zero);
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(3);
            var pl = FindObjectOfType<Player_Control_scr>();
            var body = pl.GetComponent<Rigidbody>();
            float settle = Time.time + 1.5f;
            while (Time.time < settle) yield return null;
            float floorY = body.position.y, peak = floorY, end = Time.time + 2.5f;
            pl.SendMessage("OnJump");
            while (Time.time < end) { peak = Mathf.Max(peak, body.position.y); yield return null; }
            Check("jump.up_and_back@" + FrameRates[i], peak > floorY + 0.5f && Mathf.Abs(body.position.y - floorY) < 0.3f && pl.grounded, "peak=" + (peak - floorY).ToString("F2") + " end=" + (body.position.y - floorY).ToString("F2") + " grounded=" + pl.grounded);
            var above = body.position + Vector3.up * 8f;
            yield return new WaitForFixedUpdate();
            pl.transform.position = above; body.position = above; body.linearVelocity = Vector3.zero;
            float minY = above.y; end = Time.time + 4f;
            while (Time.time < end) { minY = Mathf.Min(minY, body.position.y); yield return null; }
            Check("fall.lands_on_floor@" + FrameRates[i], minY > floorY - 1f && Mathf.Abs(body.position.y - floorY) < 0.3f, "minY=" + (minY - floorY).ToString("F2") + " end=" + (body.position.y - floorY).ToString("F2"));
        }
    }

    // Save at a known floor point through the game's own Save, then load it as a save, not through Hold_Data.
    IEnumerator SaveLoad()
    {
        const int Slot = 7; // never a real slot on this machine
        int keep = PlayerPrefs.GetInt("CURRENT_SAVE", 0), good = 0;
        var target = new Vector3(62.3f, 12.5f, -61.3f);
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 1.5f;
        while (Time.time < settle) yield return null;
        PlayerPrefs.SetInt("CURRENT_SAVE", Slot);
        Save.SAVE_FILE(Slot, target, FindObjectOfType<CONTROL>());
        for (int i = 0; i < 8; i++)
        {
            Time.captureFramerate = FrameRates[i % FrameRates.Length];
            Hold_Data.HD = null;
            SceneManager.LoadScene("PITT_A1");
            yield return WaitFrames(1 + i % 5);
            var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().FirstOrDefault(p => p.gameObject.scene.IsValid());
            float end = Time.time + 2f;
            while (Time.time < end) yield return null;
            var at = pl.GetComponent<Rigidbody>().position;
            bool ok = Vector2.Distance(new Vector2(at.x, at.z), new Vector2(target.x, target.z)) < 3f && at.y > target.y - 4f;
            if (ok) good++;
            Log("SAVELOAD " + i + " at=" + at.ToString("F1"));
        }
        Check("save.load_returns_there", good == 8, "good=" + good + " of 8");
        PlayerPrefs.SetInt("CURRENT_SAVE", keep);
        Hold_Data.HD = null;
    }

    // The game's own death path, up to the Gameover scene.
    IEnumerator Death()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        var pl = FindObjectOfType<Player_Control_scr>();
        float settle = Time.time + 1.5f;
        while (Time.time < settle) yield return null;
        pl.Die();
        float end = Time.time + 25f;
        while (Time.time < end && SceneManager.GetActiveScene().name == "PITT_A1") yield return null;
        var name = SceneManager.GetActiveScene().name;
        Check("death.reaches_gameover", name == "Gameover", "scene=" + name);
    }

    // The laser on every visible control of every page: the middle of each one has to reach it.
    IEnumerator AllMenus()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var gp = FindObjectOfType<LunaVRGameplay>();
        const BindingFlags Any = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var pick = typeof(LunaVRGameplay).GetMethod("HudElementAt", Any);
        var hud = ((System.Collections.Generic.List<RectTransform>)typeof(LunaVRGameplay).GetField("huds", Any).GetValue(gp)).First(h => h != null);
        var menu = FindObjectOfType<Menus>();
        var plr = FindObjectOfType<Player_Control_scr>();
        plr.Freeze = true;
        var crystal = hud.Find("HUD/CRYSTAL");
        if (crystal != null)
        {
            for (var x = crystal; x != null && x != hud.parent; x = x.parent) x.gameObject.SetActive(true);
            var pages = new[] { "STONE", "WARP", "LEVEL" };
            foreach (var pageName in pages)
            {
                foreach (var other in pages) { var t = crystal.Find(other); if (t != null) t.gameObject.SetActive(other == pageName); }
                yield return WaitFrames(5);
                var shown = crystal.Find(pageName);
                if (shown != null) yield return CheckControls("crystal." + pageName, shown, pick, gp, true);
                if (shown != null) CheckTexts("crystal." + pageName, shown);
            }
            crystal.gameObject.SetActive(false);
        }
        var main = menu.MENUS[0].transform.parent;
        for (var x = main; x != null && x != hud.parent; x = x.parent) x.gameObject.SetActive(true);
        foreach (var page in new[] { 0, 1, 2, 3, 4 })
        {
            menu.current_menu = page;
            menu.LoadMenu();
            yield return WaitFrames(30);
            yield return CheckControls("page" + page, main, pick, gp, false);
            CheckTexts("page" + page, main);
        }
        menu.current_menu = -1;
        menu.LoadMenu();
        plr.Freeze = false;
    }

    IEnumerator CheckControls(string label, Transform root, MethodInfo pick, LunaVRGameplay gp, bool mustHaveControls)
    {
        yield return null;
        int checkedCount = 0, bad = 0;
        var names = new System.Collections.Generic.List<string>();
        foreach (var sel in root.GetComponentsInChildren<UnityEngine.UI.Selectable>())
        {
            if (!sel.IsInteractable()) continue;
            var t = (RectTransform)sel.transform;
            var centre = t.TransformPoint(t.rect.center);
            bool hidden = false;
            foreach (var m in t.GetComponentsInParent<UnityEngine.UI.RectMask2D>())
                if (!m.rectTransform.rect.Contains((Vector2)m.rectTransform.InverseTransformPoint(centre))) hidden = true;
            if (hidden) continue;
            int hit = 0; string lostTo = "";
            for (int ix = -1; ix <= 1; ix++) for (int iy = -1; iy <= 1; iy++)
            {
                var p = t.TransformPoint(t.rect.center + new Vector2(ix * t.rect.width * 0.3f, iy * t.rect.height * 0.3f));
                var got = (GameObject)pick.Invoke(gp, new object[] { p });
                if (got != null && got.transform.IsChildOf(sel.transform)) hit++;
                else lostTo = got != null ? got.name : "nothing";
            }
            checkedCount++;
            if (hit < 5) { bad++; names.Add(sel.name + "=" + hit + "/9 to " + lostTo); }
        }
        Check("laser.all." + label, bad == 0 && (checkedCount > 0 || !mustHaveControls), "controls=" + checkedCount + " bad=" + string.Join(", ", names));
    }

    // Every gameplay scene: starts on its floor; its real Teleport_scr objects work; and every level
    // entrance the game defines (GOTO_LEVEL) puts the player there, at varied frame rates.
    static readonly string[] GameScenes = { "PITT_A1", "HUB_01", "FOREST_A1", "SEWER_A1", "LAKE", "HAUNT", "ARCHIVES", "CAS_1", "PITT_B1", "FOREST_B1", "CAS_2", "CAVE", "WALL_01", "CAS_3", "TOWER", "PRISON", "ARENA", "ARENA2", "CAS_PITT", "VOID", "DETHLAND" };

    IEnumerator Scenes()
    {
        var entries = new System.Collections.Generic.Dictionary<string, Vector3>();
        var perScene = new System.Collections.Generic.Dictionary<string, int>();
        int rate = 0;
        foreach (var scene in GameScenes)
        {
            Time.captureFramerate = FrameRates[rate++ % FrameRates.Length];
            Hold_Data.HD = Data(Vector3.zero);
            SceneManager.LoadScene(scene);
            yield return WaitFrames(3);
            var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().FirstOrDefault(p => p.gameObject.scene.IsValid());
            if (pl == null) { Check("scene.default." + scene, false, "no player"); continue; }
            var body = pl.GetComponent<Rigidbody>();
            var start = body.position;
            float end = Time.time + 3f, minY = start.y, fastest = 0f;
            while (Time.time < end) { minY = Mathf.Min(minY, body.position.y); fastest = Mathf.Min(fastest, body.linearVelocity.y); yield return null; }
            Check("scene.default." + scene, !pl.gameObject.activeInHierarchy || (minY > start.y - 6f && fastest > -25f), "start=" + start.ToString("F1") + " minY=" + minY.ToString("F1") + " fastest=" + fastest.ToString("F1"));
            foreach (var g in Resources.FindObjectsOfTypeAll<GOTO_LEVEL>().Where(x => x.gameObject.scene.IsValid() && !string.IsNullOrEmpty(x.LVL)))
            {
                if (g.POS.x == 0f) continue; // the game reads x 0 as "no position"
                if (!Application.CanStreamedLevelBeLoaded(g.LVL)) { Log("SCENES entry to a scene not in the project: " + g.LVL); continue; }
                string key = g.LVL + "|" + g.POS.ToString("F0");
                if (entries.ContainsKey(key)) continue;
                perScene.TryGetValue(g.LVL, out var had);
                if (had >= 3) continue;
                perScene[g.LVL] = had + 1;
                entries[key] = g.POS;
            }
            int teleports = 0;
            foreach (var tp in Resources.FindObjectsOfTypeAll<Teleport_scr>().Where(x => x.gameObject.scene.IsValid() && !x.auto && !x.Veil && x.TAR != null && x.PL != null))
            {
                if (teleports++ >= 2) break;
                if (!pl.gameObject.activeInHierarchy) break;
                // On foot, as the interact button requires (TOWER starts on the moving boat).
                if (pl.transform.parent != null) { pl.transform.parent = null; yield return WaitFrames(5); }
                // ACT itself: these objects stay inactive until the game needs them, and SendMessage skips inactive objects.
                typeof(Teleport_scr).GetMethod("ACT", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(tp, null);
                var target = tp.TAR.transform.position;
                float wait = Time.time + 0.5f;
                while (Time.time < wait) yield return null;
                float off = Vector2.Distance(new Vector2(body.position.x, body.position.z), new Vector2(target.x, target.z));
                Check("scene.teleport." + scene + "." + tp.name, off < 2f, "off=" + off.ToString("F2"));
            }
        }
        foreach (var e in entries)
        {
            var parts = e.Key.Split('|');
            Time.captureFramerate = FrameRates[rate++ % FrameRates.Length];
            Hold_Data.HD = Data(e.Value);
            SceneManager.LoadScene(parts[0]);
            yield return WaitFrames(1 + rate % 5);
            var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().FirstOrDefault(p => p.gameObject.scene.IsValid());
            if (pl == null) { Check("scene.entry." + e.Key, false, "no player"); continue; }
            var body = pl.GetComponent<Rigidbody>();
            float end = Time.time + 5f;
            while (Time.time < end) yield return null;
            // Some entrances drop the player from above on purpose: what matters is arriving there and being at rest on something.
            var at = body.position;
            float off = Vector2.Distance(new Vector2(at.x, at.z), new Vector2(e.Value.x, e.Value.z));
            Check("scene.entry." + e.Key, !pl.gameObject.activeInHierarchy || body.isKinematic || (off < 4f && Mathf.Abs(body.linearVelocity.y) < 3f), "at=" + at.ToString("F1") + " off=" + off.ToString("F2") + " vy=" + body.linearVelocity.y.ToString("F1"));
        }
    }

    // TOWER's real Teleport_scr, repeated at each frame rate with the player's state, for a result that changed between runs.
    IEnumerator TowerTeleport()
    {
        for (int i = 0; i < 8; i++)
        {
            Time.captureFramerate = FrameRates[i % FrameRates.Length];
            Hold_Data.HD = Data(Vector3.zero);
            SceneManager.LoadScene("TOWER");
            yield return WaitFrames(3);
            var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().First(p => p.gameObject.scene.IsValid());
            var body = pl.GetComponent<Rigidbody>();
            float settle = Time.time + 3f;
            while (Time.time < settle) yield return null;
            var tp = Resources.FindObjectsOfTypeAll<Teleport_scr>().First(x => x.gameObject.scene.IsValid() && !x.auto && !x.Veil && x.TAR != null && x.PL != null);
            var target = tp.TAR.transform.position;
            var parent = pl.transform.parent;
            var anim = parent != null ? parent.GetComponent<Animation>() : null;
            string state = "parent=" + (parent != null ? parent.name : "none") + " animPlaying=" + (anim != null && anim.isPlaying) + " kinematic=" + body.isKinematic + " from=" + body.position.ToString("F1") + " target=" + target.ToString("F1");
            // The game fires it from the interact button, on foot: never while the boat carries the player.
            pl.transform.parent = null;
            yield return WaitFrames(5);
            typeof(Teleport_scr).GetMethod("ACT", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(tp, null);
            float wait = Time.time + 0.5f;
            while (Time.time < wait) yield return null;
            float off = Vector2.Distance(new Vector2(body.position.x, body.position.z), new Vector2(target.x, target.z));
            Check("tower.teleport@" + FrameRates[i % FrameRates.Length] + "#" + i, off < 2f, state + " end=" + body.position.ToString("F1") + " transform=" + pl.transform.position.ToString("F1") + " off=" + off.ToString("F2") + " kinematicNow=" + body.isKinematic);
        }
    }

    // The other scene that switches the player off and back on (Abyss_Scene, 15.25 s), through its real objects.
    IEnumerator Cave()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("CAVE");
        yield return WaitFrames(30);
        var pl = Resources.FindObjectsOfTypeAll<Player_Control_scr>().FirstOrDefault(p => p.gameObject.scene.IsValid());
        var body = pl.GetComponent<Rigidbody>();
        float settle = Time.time + 1.5f;
        while (Time.time < settle) yield return null;
        var obj = Resources.FindObjectsOfTypeAll<Transform>().FirstOrDefault(t => t.name == "Abyss_Scene" && t.gameObject.scene.IsValid());
        if (obj == null) { Log("CAVE Abyss_Scene not found"); yield break; }
        var goAnchor = obj.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == "GO");
        if (goAnchor != null) foreach (var c in goAnchor.GetComponents<MonoBehaviour>()) Log("CAVE GO has " + c.GetType().Name);
        var before = body.position;
        for (var t = obj; t != null; t = t.parent) t.gameObject.SetActive(true);
        float end = Time.time + 21f, minY = 999f, fastest = 0f;
        bool off = false, back = false, jumped = false; Vector3 offPos = Vector3.zero, backPos = Vector3.zero, last = before;
        while (Time.time < end)
        {
            bool active = pl.gameObject.activeInHierarchy;
            if (!active && !off) { off = true; offPos = pl.transform.position; }
            if (active && off && !back) { back = true; backPos = pl.transform.position; last = backPos; }
            if (back)
            {
                minY = Mathf.Min(minY, body.position.y);
                fastest = Mathf.Min(fastest, body.linearVelocity.y);
                if ((body.position - last).magnitude > 5f) jumped = true;
                last = body.position;
            }
            yield return null;
        }
        bool down = back && (minY < backPos.y - 6f || fastest < -25f || jumped);
        bool caveFloor = Physics.Raycast(backPos + Vector3.up * 0.1f, Vector3.down, out var caveHit, 300f, ~0, QueryTriggerInteraction.Ignore);
        Log("CAVE floorUnderReturn=" + (caveFloor ? caveHit.collider.name + "@" + caveHit.distance.ToString("F1") : "none"));
        Log("CAVE before=" + before.ToString("F1") + " switchedOff=" + off + " offAt=" + offPos.ToString("F1") + " backAt=" + backPos.ToString("F1") + " end=" + body.position.ToString("F1") + " minY=" + minY.ToString("F1") + " fastestFall=" + fastest.ToString("F1") + " teleported=" + jumped + (down ? " FELL" : ""));
    }

    // What takes the motion away: the same walk as shipped, then with one suspect removed at a time.
    IEnumerator Walk()
    {
        yield return WalkCase("as shipped", null);
        yield return WalkCase("rigidbody interpolation off", (pl, body) => body.interpolation = RigidbodyInterpolation.None);
        yield return WalkCase("game interpolation off", (pl, body) => { foreach (var c in pl.GetComponents<InterpolationObjectController>()) Destroy(c); });
        yield return WalkCase("port gameplay off", (pl, body) => FindObjectOfType<LunaVRGameplay>().enabled = false);
    }


    // Felipe (Build 95): turned around with the body, the stick's forward walked backwards. The stick must move the
    // player where the head looks, whatever the head's yaw against the game's body (LESSONS 35). The stick goes
    // through the real path: the port's virtual pad, the game's OnMove and its body-relative PLMOVE.
    IEnumerator HeadRelativeMove()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var pl = FindObjectOfType<Player_Control_scr>();
        var body = pl.GetComponent<Rigidbody>();
        var cam = pl.GetComponentInChildren<LunaHeadTracker>(true);
        var start = body.position;
        var hField = typeof(Player_Control_scr).GetField("horizontal", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        var vField0 = typeof(Player_Control_scr).GetField("vertical", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        foreach (var (bodyYaw, headYaw, stick) in new[] { (0f, 0f, new Vector2(0, 1)), (0f, 180f, new Vector2(0, 1)), (40f, 90f, new Vector2(0, 1)),
                                                          (0f, -90f, new Vector2(0, 1)), (0f, 180f, new Vector2(1, 0)) })
        {
            pl.transform.position = start; body.position = start; body.linearVelocity = Vector3.zero;
            pl.ROT.y = bodyYaw; pl.transform.rotation = Quaternion.Euler(0f, bodyYaw, 0f);
            var rot = Quaternion.Euler(0f, headYaw, 0f);
            LunaHeadTracker.TestPose = () => (rot, Vector3.zero);
            var s = stick;
            LunaVRGameplay.TestLeftStick = () => s;
            float until = Time.time + 0.6f;
            while (Time.time < until) yield return null;
            // The game's own command (its horizontal and vertical, which PLMOVE turns by the body), not the body's
            // speed: a wall behind the start would stop a correct walk.
            float h = (float)hField.GetValue(pl), vIn = (float)vField0.GetValue(pl);
            var cmd = pl.transform.TransformDirection(new Vector3(h, 0f, vIn)); cmd.y = 0f;
            var view = cam != null ? cam.transform.rotation : pl.transform.rotation * rot;
            var want = view * new Vector3(s.x, 0f, s.y); want.y = 0f;
            float angle = cmd.magnitude > 0.5f ? Vector3.Angle(cmd, want) : 999f;
            Check("move.head_" + headYaw.ToString("0") + (s.x != 0 ? "_right" : "_forward") + "_body" + bodyYaw.ToString("0"),
                  angle < 10f, "command=(" + h.ToString("F2") + ", " + vIn.ToString("F2") + ") off the view by " + angle.ToString("F0") + " deg");
        }
        // On a ladder (gravity 0, not swimming) the game climbs on vertical > 0.5: the stick stays the body's,
        // so looking aside does not stop the climb.
        var vField = typeof(Player_Control_scr).GetField("vertical", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        pl.ROT.y = 0f; pl.transform.rotation = Quaternion.identity;
        var side = Quaternion.Euler(0f, 90f, 0f);
        LunaHeadTracker.TestPose = () => (side, Vector3.zero);
        LunaVRGameplay.TestLeftStick = () => new Vector2(0, 1);
        float ladderUntil = Time.time + 0.5f;
        float vertical = 0f;
        while (Time.time < ladderUntil) { pl.gravity = 0f; yield return null; vertical = (float)vField.GetValue(pl); }
        Check("move.ladder_keeps_body_forward", vertical > 0.5f, "vertical=" + vertical.ToString("F2") + " with the head 90 deg aside");
        pl.gravity = 10f;
        LunaVRGameplay.TestLeftStick = null;
        LunaHeadTracker.TestPose = null;
    }

    IEnumerator Run() { yield return WalkCase("run", null, true); }

    IEnumerator WalkCase(string label, System.Action<Player_Control_scr, Rigidbody> change, bool sprint = false)
    {
        var sprintField = typeof(Player_Control_scr).GetField("sprinting", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        var f = typeof(Player_Control_scr).GetField("vertical", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        var pl = FindObjectOfType<Player_Control_scr>();
        var body = pl.GetComponent<Rigidbody>();
        float settle = Time.time + 1f;
        while (Time.time < settle) yield return null;
        change?.Invoke(pl, body);
        float accel = Time.time + 0.5f;
        while (Time.time < accel) { f.SetValue(pl, 1f); sprintField.SetValue(pl, sprint); yield return null; }
        // Steady state only, past the start of the walk.
        Vector3 a = body.position; float start = Time.time, sum = 0f; int n = 0;
        while (Time.time < start + 1.5f)
        {
            f.SetValue(pl, 1f);
            sprintField.SetValue(pl, sprint);
            sum += new Vector2(body.linearVelocity.x, body.linearVelocity.z).magnitude; n++;
            yield return null;
        }
        Vector3 b = body.position;
        f.SetValue(pl, 0f);
        sprintField.SetValue(pl, false);
        float dy = b.y - a.y; a.y = b.y;
        float realMeasured = Vector3.Distance(a, b) / (Time.time - start), meanVelocity = sum / n;
        if (label == "as shipped" || sprint) Check("move." + label.Replace(" ", "_"), meanVelocity > 2f && realMeasured >= meanVelocity * 0.93f, "real=" + realMeasured.ToString("F2") + " velocity=" + meanVelocity.ToString("F2"));
        Log("WALK [" + label + "] meanVelocity=" + (sum / n).ToString("F2") + " realSpeed=" + (Vector3.Distance(a, b) / (Time.time - start)).ToString("F2")
            + " dy=" + dy.ToString("F2") + " from=" + a.ToString("F1") + " to=" + b.ToString("F1") + " interpolation=" + body.interpolation);
    }

    IEnumerator Menu()
    {
        Hold_Data.HD = null;
        SceneManager.LoadScene("MainMenu");
        yield return WaitFrames(30);
        var skip = Resources.FindObjectsOfTypeAll<Canvas>().FirstOrDefault(c => c.name == "SKIP_CAN" && c.gameObject.scene.IsValid());
        if (skip == null) { Log("SKIP_CAN not found"); yield break; }
        Log("SKIP_CAN active=" + skip.gameObject.activeInHierarchy + " mode=" + skip.renderMode + " camera=" + (skip.worldCamera != null ? skip.worldCamera.name : "null") + " order=" + skip.sortingOrder);
        var con = skip.GetComponentInChildren<skip_con>(true) ?? FindObjectOfType<skip_con>();
        if (con != null)
        {
            con.enabled = false;
            // The indicator is inactive until the new-game intro starts it: without this the shot cannot show it.
            for (var t = con.TXT.transform; t != null && t != skip.transform.parent; t = t.parent) t.gameObject.SetActive(true);
            con.TXT.color = Color.white;
            con.IMG.color = Color.grey;
            con.IMG.rectTransform.sizeDelta = new Vector2(400f, con.IMG.rectTransform.sizeDelta.y);
        }
        yield return WaitFrames(5);
        Shot("menu");
        // The intro's own camera, as Start does.
        foreach (var c in Camera.allCameras) if (c.name == "CAM" || c.name == "CAM2") c.gameObject.SetActive(false);
        var scene = Resources.FindObjectsOfTypeAll<Camera>().FirstOrDefault(c => c.name == "SCENE_CAM" && c.gameObject.scene.IsValid());
        for (var t = scene.transform; t != null; t = t.parent) t.gameObject.SetActive(true);
        scene.enabled = true;
        yield return WaitFrames(10);
        Log("SKIP_CAN on intro camera: mode=" + skip.renderMode + " camera=" + (skip.worldCamera != null ? skip.worldCamera.name : "null") + " order=" + skip.sortingOrder);
        Shot("intro");
        Log("skip_con found=" + (con != null) + (con != null ? " TXT active=" + con.TXT.gameObject.activeInHierarchy + " colour=" + con.TXT.color + " size=" + con.TXT.rectTransform.rect.size + " text=" + con.TXT.text : ""));
        foreach (var c in Resources.FindObjectsOfTypeAll<Canvas>().Where(c => c.gameObject.scene.IsValid() && c.isRootCanvas))
            Log("canvas " + c.name + " active=" + c.gameObject.activeInHierarchy + " enabled=" + c.enabled + " mode=" + c.renderMode + " order=" + c.sortingOrder + " layer=" + c.gameObject.layer
                + " camera=" + (c.worldCamera != null ? c.worldCamera.name : "null") + " plane=" + c.planeDistance + " scale=" + c.transform.lossyScale.ToString("F4"));
        Log("SCENE_CAM mask=" + scene.cullingMask + " near=" + scene.nearClipPlane + " far=" + scene.farClipPlane + " target=" + (scene.targetTexture != null ? scene.targetTexture.name : "null"));
        Check("skip_text.has_camera", skip.renderMode == RenderMode.ScreenSpaceCamera && skip.worldCamera != null && skip.worldCamera.name == "TheaterOverlay", "mode=" + skip.renderMode);
        if (con != null)
        {
            var textArea = new Rect(0.33f, 0.21f, 0.34f, 0.10f);
            con.TXT.gameObject.SetActive(false);
            yield return WaitFrames(5);
            float withoutText = RegionBrightness(textArea);
            con.TXT.gameObject.SetActive(true);
            yield return WaitFrames(5);
            float withText = RegionBrightness(textArea);
            Check("skip_text.drawn", Mathf.Abs(withText - withoutText) > 0.01f, "brightness " + withoutText.ToString("F3") + " -> " + withText.ToString("F3"));
        }
        // The scene has 17 cameras named SCENE_CAM: check the one the canvas is really on.
        var drawn = skip.worldCamera;
        if (drawn != null && con != null)
        {
            var theaterTex = FindObjectOfType<LunaTheater>().Texture;
            var tp = drawn.WorldToViewportPoint(con.TXT.transform.position);
            var ip = drawn.WorldToViewportPoint(con.IMG.transform.position);
            con.TXT.ForceMeshUpdate();
            float groups = 1f;
            foreach (var g in con.TXT.GetComponentsInParent<CanvasGroup>(true)) groups *= g.alpha;
            Log("drawn camera same as probe's=" + (drawn == scene) + " active=" + drawn.isActiveAndEnabled + " onTheater=" + (drawn.targetTexture == theaterTex) + " depth=" + drawn.depth + " mask=" + drawn.cullingMask + " near=" + drawn.nearClipPlane);
            Log("TXT viewport=" + tp.ToString("F3") + " IMG viewport=" + ip.ToString("F3") + " IMG active=" + con.IMG.gameObject.activeInHierarchy + " IMG colour=" + con.IMG.color + " size=" + con.IMG.rectTransform.rect.size
                + " chars=" + con.TXT.textInfo.characterCount + " verts=" + con.TXT.mesh.vertexCount + " cull=" + con.TXT.canvasRenderer.cull + " alpha=" + con.TXT.canvasRenderer.GetAlpha() + " groups=" + groups
                + " shader=" + con.TXT.materialForRendering.shader.name + " supported=" + con.TXT.materialForRendering.shader.isSupported);
            var keep = drawn.targetTexture;
            drawn.targetTexture = theaterTex;
            drawn.Render();
            drawn.targetTexture = keep;
            Shot("intro_forced");
        }
        skip.sortingOrder = 1000;
        yield return WaitFrames(5);
        Shot("intro_lift");
    }

    // Every option of both settings pages, opened through the game's own Click as the buttons do: what makes no
    // sense in the headset is hidden, and every option still shown changes something in the game.
    const BindingFlags AnyField = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    static object Get(object o, string f) => o.GetType().GetField(f, AnyField).GetValue(o);

    // Shown on the game's pages (MAIN/menu3, MAIN/menu4); everything else with a Click there must be hidden.
    static readonly string[] GameOptionsShown = { "VOL_SLIDER", "INVERT_BUTTON", "FOV_SLIDER", "HAND_BUTTON", "QUALITY_BUTTON", "reset", "quit", "more",
                                                  "compass_button", "run_button", "npc_button", "hud_button", "feet_button", "DIFF_SLIDER", "MUSE_SLIDER", "speed_button" };
    static readonly string[] GameOptionsHidden = { "FILTER_BUTTON", "BOB_SLIDER", "GAMMA_SLIDER", "FULLSCREEN_BUTTON", "REZ_BUTTON", "REZ_BUTTON2", "APPLY_RES",
                                                   "SHAKE_SLIDER", "fps_button", "leg_button", "rebind" };
    // The values the game writes beside the rows that stay (TURN, L/R HAND, QUALITY). The row rule that hid AESTHETIC
    // also hid menu3/Settings, the parent of the TURN and L/R HAND values (Builds 88-93, LESSONS 33).
    static readonly string[] GameValuesShown = { "menu3/Settings/B", "menu3/Settings/C", "menu3/Settings2/A" };
    static readonly string[] GameTextsHidden = { "menu3/Settings/A", "menu3/Settings2/B", "menu3/Settings2/C", "menu3/LABELS1/LAB_A", "menu3/LABELS1/LAB_D", "menu3/LABELS1/LAB_E",
                                                 "menu3/LABELS2/B", "menu3/LABELS2/C", "menu4/LABELS1/G", "menu4/LABELS2/C", "menu4/LABELS2/D", "menu4/LABELS2/E" };
    // Shown on the main menu's page (ROOT/SETTINGS): volume, quality, language, reset, back.
    static readonly string[] TitleOptionsShown = { "VOL_SLIDER", "QUALITY_BUTTON", "reset", "quit", "Dropdown" };

    IEnumerator Options()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        var menu = FindObjectOfType<Menus>();
        var con = FindObjectOfType<CONTROL>();
        var pl = FindObjectOfType<Player_Control_scr>();
        var gp = FindObjectOfType<LunaVRGameplay>();
        var sys = con.CURRENT_SYS_DATA;
        var mainT = menu.GetComponentsInChildren<Transform>(true).First(t => t.name == "MAIN");
        for (var x = mainT; x != null; x = x.parent) x.gameObject.SetActive(true);
        menu.current_menu = 0;
        menu.LoadMenu();
        yield return WaitFrames(5);

        // What is shown and what is hidden, page by page.
        var shown = new System.Collections.Generic.List<string>();
        foreach (var click in new[] { 3, 58 })
        {
            menu.Click(click);
            yield return WaitFrames(10);
            var page = menu.SUBMENUS[menu.sub_menu].transform;
            foreach (var s in page.GetComponentsInChildren<Selectable>()) shown.Add(s.name);
            CheckTexts("settings" + click, page);
            if (click == 3)
            {
                var valuesGone = GameValuesShown.Where(p => { var t = mainT.Find(p); var tmp = t != null ? t.GetComponent<TMP_Text>() : null;
                                                            return tmp == null || !tmp.gameObject.activeInHierarchy || string.IsNullOrWhiteSpace(tmp.text); }).ToArray();
                Check("options.values_shown", valuesGone.Length == 0, "values not shown=[" + string.Join(",", valuesGone) + "]");
                // Nothing may stay visible on a hidden row: on the notebook (2026-11-13, every build since 94) the
                // AESTHETIC value box stayed as an empty violet rectangle, because the LESSONS 33 rule spared every
                // graphic with children, not only menu3/Settings whose children sit on other rows (LESSONS 40).
                var leftOnHiddenRows = new System.Collections.Generic.List<string>();
                foreach (var path in GameTextsHidden.Where(p => p.StartsWith("menu3/LABELS")))
                {
                    var label = mainT.Find(path) as RectTransform;
                    if (label == null) continue;
                    Vector3 lp = page.InverseTransformPoint(label.TransformPoint(label.rect.center));
                    foreach (var g in page.GetComponentsInChildren<Graphic>())
                    {
                        if (!g.enabled || g.color.a < 0.05f || g.canvasRenderer.GetAlpha() < 0.05f || g.rectTransform.rect.height > 90f) continue;
                        if (g is TMP_Text tx && string.IsNullOrWhiteSpace(tx.text)) continue;
                        Vector3 gpos = page.InverseTransformPoint(g.rectTransform.TransformPoint(g.rectTransform.rect.center));
                        if (Mathf.Abs(gpos.y - lp.y) > 18f || Mathf.Sign(gpos.x) != Mathf.Sign(lp.x) || gpos.x < lp.x - 40f) continue;
                        leftOnHiddenRows.Add(path.Split('/').Last() + ":" + g.name);
                    }
                }
                Check("options.hidden_rows_empty", leftOnHiddenRows.Count == 0, "still visible=[" + string.Join(",", leftOnHiddenRows.Distinct()) + "]");
            }
        }
        var notExpected = shown.Where(n => !GameOptionsShown.Contains(n)).ToArray();
        var missing = GameOptionsShown.Where(n => !shown.Contains(n)).ToArray();
        Check("options.game_shown", notExpected.Length == 0 && missing.Length == 0, "unexpected=[" + string.Join(",", notExpected) + "] missing=[" + string.Join(",", missing) + "]");
        var textsLeft = GameTextsHidden.Where(p => { var t = mainT.Find(p); return t != null && t.gameObject.activeInHierarchy; }).ToArray();
        var hiddenMissing = GameOptionsHidden.Where(n => mainT.GetComponentsInChildren<Selectable>(true).All(s => s.name != n)).ToArray();
        Check("options.game_hidden", textsLeft.Length == 0 && hiddenMissing.Length == 0, "texts still shown=[" + string.Join(",", textsLeft) + "] hidden controls not found=[" + string.Join(",", hiddenMissing) + "]");

        Selectable Ctrl(string name) => mainT.GetComponentsInChildren<Selectable>(true).First(s => s.name == name);
        void Press(string name) { var b = (Button)Ctrl(name); b.onClick.Invoke(); }
        var turn = typeof(LunaVRGameplay).GetMethod("TurnSettings", AnyField);
        (bool smooth, float sens, float snap) Turn() { var a = new object[] { false, 0f, 0f }; turn.Invoke(gp, a); return ((bool)a[0], (float)a[1], (float)a[2]); }

        menu.Click(3);
        yield return WaitFrames(5);
        // GAME VOLUME
        var vol = (Slider)Ctrl("VOL_SLIDER"); float volWas = vol.value;
        vol.value = 0.3f; yield return null;
        Check("options.volume", Mathf.Abs(AudioListener.volume - 0.3f) < 0.01f, "listener=" + AudioListener.volume.ToString("F2"));
        vol.value = volWas;
        // TURN: snap <-> smooth; TURN SPEED in smooth; SNAP ANGLE in snap
        var t0 = Turn();
        Press("INVERT_BUTTON"); yield return WaitFrames(3);
        var t1 = Turn();
        var speedSlider = (Slider)Ctrl("SENS_SLIDER");
        bool speedShown = speedSlider.gameObject.activeInHierarchy;
        speedSlider.value = 5f; yield return null;
        var t2 = Turn();
        Check("options.turn_smooth", t0.smooth != t1.smooth && t1.smooth && speedShown && Mathf.Abs(t2.sens - 5f) < 0.01f, "smooth " + t0.smooth + "->" + t1.smooth + " speed row shown=" + speedShown + " sens=" + t2.sens);
        speedSlider.value = 10f;
        Press("INVERT_BUTTON"); yield return WaitFrames(3);
        var fov = (Slider)Ctrl("FOV_SLIDER"); float fovWas = fov.value;
        fov.value = 100f; yield return WaitFrames(2);
        var t3 = Turn();
        Check("options.snap_angle", !t3.smooth && fov.gameObject.activeInHierarchy && Mathf.Abs(t3.snap - 90f) < 0.01f, "smooth=" + t3.smooth + " snap=" + t3.snap);
        fov.value = fovWas; yield return WaitFrames(2);
        // L/R HAND
        float handWas = pl.HANDS.transform.localScale.x;
        Press("HAND_BUTTON"); yield return null;
        float handNow = pl.HANDS.transform.localScale.x;
        Check("options.left_hand", Mathf.Sign(handWas) != Mathf.Sign(handNow) && sys.SETT_LEFT_HAND == 1, "scale.x " + handWas + "->" + handNow);
        Press("HAND_BUTTON"); yield return null;
        // QUALITY
        int q0 = QualitySettings.GetQualityLevel();
        Press("QUALITY_BUTTON"); yield return null;
        int q1 = QualitySettings.GetQualityLevel();
        Check("options.quality", q1 != q0, QualitySettings.names[q0] + "->" + QualitySettings.names[q1]);
        for (int i = 0; i < 3 && QualitySettings.GetQualityLevel() != q0; i++) Press("QUALITY_BUTTON");

        menu.Click(58);
        yield return WaitFrames(5);
        // COMPASS STYLE: the compass appears on the HUD
        int compassWas = sys.SETTING_COMPASS;
        while (sys.SETTING_COMPASS != 1) Press("compass_button");
        menu.current_menu = 1; menu.LoadMenu(); yield return WaitFrames(10);
        var comp = FindObjectOfType<Compass_control>();
        Check("options.compass", comp != null && comp.Needles.Any(n => n.activeInHierarchy), "compass=" + (comp != null));
        menu.current_menu = 0; menu.LoadMenu(); menu.Click(58); yield return WaitFrames(5);
        while (sys.SETTING_COMPASS != compassWas) Press("compass_button");
        // NPC HEALTH and SHOW HUD: what the HUD page shows
        var hudWas = menu.MENUS[1].activeSelf;
        Press("hud_button"); Press("npc_button");
        menu.current_menu = 1; menu.LoadMenu(); yield return WaitFrames(5);
        bool hudOff = !menu.MENUS[1].activeSelf, npcOff = !menu.ITEMS[22].activeSelf;
        menu.current_menu = 0; menu.LoadMenu(); menu.Click(58); yield return WaitFrames(5);
        Press("hud_button"); Press("npc_button");
        menu.current_menu = 1; menu.LoadMenu(); yield return WaitFrames(5);
        bool hudOn = menu.MENUS[1].activeSelf, npcOn = menu.ITEMS[22].activeSelf;
        Check("options.show_hud", hudOff && hudOn, "off=" + hudOff + " back=" + hudOn);
        Check("options.npc_health", npcOff && npcOn, "off=" + npcOff + " back=" + npcOn);
        menu.current_menu = 0; menu.LoadMenu(); menu.Click(58); yield return WaitFrames(5);
        // FOOTSTEPS: Shinobi steps are quiet and low
        var feet = pl.GetComponent<Player_Feet>();
        int feetWas = sys.SETTING_EX0;
        while (sys.SETTING_EX0 != 8) Press("feet_button");
        var fas = (AudioSource)Get(feet, "FAS");
        Check("options.footsteps", Mathf.Abs(fas.volume - 0.25f) < 0.01f && Mathf.Abs(fas.pitch - 0.7f) < 0.01f, "volume=" + fas.volume + " pitch=" + fas.pitch);
        while (sys.SETTING_EX0 != feetWas) Press("feet_button");
        // MUSIC VOLUME
        var muse = (Slider)Ctrl("MUSE_SLIDER"); float museWas = muse.value;
        muse.value = -0.4f; yield return null;
        var museScr = FindObjectsOfType<MUSE_scr>().FirstOrDefault();
        float maxVol = museScr != null ? (float)Get(museScr, "MAX_VOL") : -1f;
        Check("options.music_volume", Mathf.Abs(maxVol - 0.6f) < 0.01f, "slider=" + muse.value + " max volume=" + maxVol);
        muse.value = museWas;
        // PLAYER SPEED CAP
        int spdWas = con.CURRENT_PL_DATA.PLAYER_SPD, capWas = sys.SETTING_EX6;
        con.CURRENT_PL_DATA.PLAYER_SPD = 90;
        while (sys.SETTING_EX6 != 0) Press("speed_button");
        con.SetSpd();
        float free = pl.speed;
        while (sys.SETTING_EX6 != 3) Press("speed_button");
        float capped = pl.speed;
        Check("options.speed_cap", capped < free * 0.8f, "speed " + free.ToString("F2") + " capped " + capped.ToString("F2"));
        con.CURRENT_PL_DATA.PLAYER_SPD = spdWas;
        while (sys.SETTING_EX6 != capWas) Press("speed_button");
        // DIFFICULTY: damage taken
        var diff = (Slider)Ctrl("DIFF_SLIDER"); float diffWas = diff.value;
        float hp0 = con.CURRENT_PL_DATA.PLAYER_H; // the game caps health at the character's maximum
        float Loss() { con.CURRENT_PL_DATA.PLAYER_H = hp0; pl.Hurt(new Vector2(5f, 0f), true); return hp0 - con.CURRENT_PL_DATA.PLAYER_H; }
        diff.value = 0f; yield return null;
        float normal = Loss();
        yield return WaitFrames(30);
        diff.value = diff.maxValue; yield return null;
        float hard = Loss();
        Check("options.difficulty", hard > normal * 1.3f, "loss normal=" + normal.ToString("F1") + " hardest=" + hard.ToString("F1") + " (slider max " + diff.maxValue + ")");
        diff.value = diffWas;
        con.CURRENT_PL_DATA.PLAYER_H = hp0;
        // ALWAYS RUN: the walk speed with the stick alone
        int runWas = sys.SETTING_RUN;
        menu.current_menu = -1; menu.LoadMenu();
        var vField = typeof(Player_Control_scr).GetField("vertical", AnyField);
        var body = pl.GetComponent<Rigidbody>();
        float[] speeds = new float[2];
        for (int k = 0; k < 2; k++)
        {
            sys.SETTING_RUN = k;
            float end = Time.time + 1.2f, sum = 0f; int n = 0;
            while (Time.time < end) { vField.SetValue(pl, 1f); if (Time.time > end - 0.6f) { sum += new Vector2(body.linearVelocity.x, body.linearVelocity.z).magnitude; n++; } yield return null; }
            vField.SetValue(pl, 0f);
            speeds[k] = sum / Mathf.Max(1, n);
            yield return WaitFrames(30);
        }
        Check("options.always_run", Mathf.Abs(speeds[0] - speeds[1]) > 0.5f, "run on=" + speeds[0].ToString("F2") + " off=" + speeds[1].ToString("F2"));
        sys.SETTING_RUN = runWas;
        // RESET SETTINGS: the PC defaults, then the port's VR ones (walk, snap 30)
        menu.current_menu = 0; menu.LoadMenu(); menu.Click(3); yield return WaitFrames(5);
        sys.SETTING_RUN = 0; sys.FOV = 100f;
        Press("reset"); yield return WaitFrames(3);
        sys = con.CURRENT_SYS_DATA; // Save.ResetSYS hands back a new settings object
        Check("options.reset_vr_defaults", sys.SETTING_RUN == 1 && Mathf.Abs(Turn().snap - 30f) < 0.01f, "run=" + sys.SETTING_RUN + " snap=" + Turn().snap);
        menu.current_menu = -1; menu.LoadMenu();

        // The main menu's own settings page.
        Hold_Data.HD = null;
        SceneManager.LoadScene("MainMenu");
        yield return WaitFrames(30);
        float s2 = Time.time + 4f;
        while (Time.time < s2) yield return null;
        var tm = Resources.FindObjectsOfTypeAll<Menus>().First(m => m.gameObject.scene.IsValid());
        tm.Click(3);
        yield return WaitFrames(20);
        var title = tm.SUBMENUS[3].transform;
        var titleShown = title.GetComponentsInChildren<Selectable>().Select(s => s.name).ToArray();
        var titleExtra = titleShown.Where(n => !TitleOptionsShown.Contains(n)).ToArray();
        var titleMissing = TitleOptionsShown.Where(n => !titleShown.Contains(n)).ToArray();
        var texts = title.GetComponentsInChildren<TMPro.TMP_Text>().Select(t => t.text.Replace("\n", "|")).ToArray();
        bool flatTextLeft = texts.Any(t => t.Contains("(") && t.Contains(",") && t.Contains(")")) || texts.Any(t => { var l = t.ToLowerInvariant(); return l.Contains("aesthetic") || l.Contains("gamma") || l.Contains("fullscreen") || l.Contains("resolution"); });
        Check("options.title_page", titleExtra.Length == 0 && titleMissing.Length == 0 && !flatTextLeft, "unexpected=[" + string.Join(",", titleExtra) + "] missing=[" + string.Join(",", titleMissing) + "] texts=" + string.Join(" / ", texts));
        Shot("options_title");
        var tsys = FindObjectOfType<CONTROL>()?.CURRENT_SYS_DATA;
        if (tsys != null)
        {
            tsys.SETTING_RUN = 0; tsys.FOV = 100f;
            title.GetComponentsInChildren<Button>().First(b => b.name == "reset").onClick.Invoke();
            yield return WaitFrames(3);
            tsys = FindObjectOfType<CONTROL>().CURRENT_SYS_DATA;
            Check("options.title_reset_vr_defaults", tsys.SETTING_RUN == 1 && tsys.FOV < 60f, "run=" + tsys.SETTING_RUN + " fov=" + tsys.FOV);
        }
        else Check("options.title_reset_vr_defaults", false, "no CONTROL in the main menu");
    }

    // The Touch controllers through the port's virtual gamepad into the game's own actions: right stick click
    // uses the item, left stick click is the next item, Y swaps the weapon, and the item and weapon actions
    // fire from nothing else (Felipe: the right stick used items and swapped weapons while turning).
    IEnumerator TouchMapping()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 2f;
        while (Time.time < settle) yield return null;
        var gp = FindObjectOfType<LunaVRGameplay>();
        var pad = typeof(LunaVRGameplay).GetField("pad", AnyField).GetValue(gp) as UnityEngine.InputSystem.Gamepad;
        if (pad == null) { Check("touch.pad", false, "no virtual gamepad"); yield break; }
        // FeedPad queues the (absent) controllers every Update; the test's event is queued after it in the same
        // frame, so the press holds for one input update, enough for a performed. (Disabling the gameplay removes the pad.)
        var input = FindObjectsOfType<UnityEngine.InputSystem.PlayerInput>().FirstOrDefault();
        var fired = new System.Collections.Generic.HashSet<string>();
        System.Action<UnityEngine.InputSystem.InputAction.CallbackContext> rec = c => { if (c.performed) fired.Add(c.action.name); };
        foreach (var pi in FindObjectsOfType<UnityEngine.InputSystem.PlayerInput>()) foreach (var a in pi.actions) a.performed += rec;
        string[] watched = { "UseITEM", "NextITEM", "LastITEM", "Swap" };
        var cases = new (string name, LunaVRGameplay.TouchButtons b, string want)[]
        {
            ("right stick click", new LunaVRGameplay.TouchButtons { RightStickClick = true }, "UseITEM"),
            ("left stick click", new LunaVRGameplay.TouchButtons { LeftStickClick = true }, "NextITEM"),
            ("Y", new LunaVRGameplay.TouchButtons { Y = true }, "Swap"),
            ("A", new LunaVRGameplay.TouchButtons { A = true }, null), ("B", new LunaVRGameplay.TouchButtons { B = true }, null),
            ("X", new LunaVRGameplay.TouchButtons { X = true }, null), ("left grip", new LunaVRGameplay.TouchButtons { LeftGrip = true }, null),
            ("right grip", new LunaVRGameplay.TouchButtons { RightGrip = true }, null),
        };
        foreach (var (name, b, want) in cases)
        {
            fired.Clear();
            UnityEngine.InputSystem.InputSystem.QueueStateEvent(pad, LunaVRGameplay.PadState(Vector2.zero, 0f, 0f, b));
            yield return WaitFrames(6);
            var items = watched.Where(fired.Contains).ToArray();
            bool ok = want == null ? items.Length == 0 : items.Length == 1 && items[0] == want;
            Check("touch." + name.Replace(" ", "_"), ok, "item/weapon actions=[" + string.Join(",", items) + "] all=[" + string.Join(",", fired) + "]");
        }
        // The right stick is not an input of the mapping at all: the only stick it takes is the left one.
        var ps = typeof(LunaVRGameplay).GetMethod("PadState").GetParameters();
        Check("touch.right_stick_only_turns", ps.Count(p => p.ParameterType == typeof(Vector2)) == 1 && ps[0].Name == "leftStick", "parameters=" + string.Join(",", ps.Select(p => p.Name)));
        foreach (var pi in FindObjectsOfType<UnityEngine.InputSystem.PlayerInput>()) foreach (var a in pi.actions) a.performed -= rec;
        Log("TOUCH player input " + (input != null ? input.name + " scheme=" + input.currentControlScheme : "none"));
    }

    // Felipe (Build 88 video): the spell lands to the right of the aim mark, always. Magic_scr casts in Update at
    // Camera.main's pose (CAM2 under CAM). On the Quest that pose, mid-frame, is not the head's: Head_Bob (on CAM)
    // pulls CAM back towards the body and rolls it in FixedUpdate, and LunaHeadTracker writes the head pose only
    // in its Update and before rendering. The test keeps that order: a head pose written every frame after
    // Update (as the tracker's onBeforeRender), the spell cast from an Update, the aim mark where the port puts it.
    // Order -1: a game script that runs before one at the default order (the tracker before the fix).
    [DefaultExecutionOrder(-1)]
    class SpellCaster : MonoBehaviour
    {
        public Object Prefab; public GameObject Cast; public Vector3 HeadPosAtCast; public Quaternion MainRotAtCast, ParentRotAtCast, CamRotAtCast;
        public Transform Cam;
        void Update()
        {
            if (Prefab == null || Cast != null) return;
            var main = Camera.main.transform;
            MainRotAtCast = main.rotation; HeadPosAtCast = main.position;
            ParentRotAtCast = Cam.parent.rotation; CamRotAtCast = Cam.rotation;
            Cast = (GameObject)Instantiate(Prefab, main.position, main.rotation, main);
        }
    }

    static string PathOf(Transform t) { var p = t.name; for (var q = t.parent; q != null; q = q.parent) p = q.name + "/" + p; return p; }

    // While a sweep of spells runs, exceptions from the spells' own scripts are logged, not counted: some casts need
    // an enemy or a scene object to run their Start. The aim checks still decide.
    static bool sweepingSpells;

    // The aim, as Felipe asks (Builds 88-89): a spell or an arrow leaves along the centre of the view, the aim mark's
    // ray, whatever the body does. One physics step every frame (50 fps): the spell is pushed in its Start, right
    // after FixedUpdate, and a frame with no step (72 fps against 50 Hz) hid the pull of Head_Bob.
    IEnumerator SpellAim()
    {
        Hold_Data.HD = Data(Vector3.zero);
        SceneManager.LoadScene("PITT_A1");
        yield return WaitFrames(3);
        float settle = Time.time + 3f;
        while (Time.time < settle) yield return null;
        Time.captureFramerate = 50;
        var pl = FindObjectOfType<Player_Control_scr>();
        var head = FindObjectOfType<LunaHeadTracker>();
        var cam = head.transform;
        var body = pl.GetComponent<Rigidbody>();
        var bob = cam.GetComponent<Head_Bob>();
        Log("SPELL Camera.main=" + PathOf(Camera.main.transform) + " head=" + PathOf(head.transform) + " Head_Bob enabled=" + (bob != null && bob.enabled));
        Check("spell.head_bob_off", bob == null || !bob.enabled, "Head_Bob enabled=" + (bob != null && bob.enabled));
        var caster = new GameObject("SpellCaster").AddComponent<SpellCaster>();
        caster.Cam = cam;
        var vField = typeof(Player_Control_scr).GetField("vertical", AnyField);
        var bodyStart = pl.transform.position;

        // One cast: body yaw, head yaw/pitch (relative to the body), head offset in the room, walking or not.
        // Returns the spell's direction against the head's view in degrees (right, up), and the camera's at the cast.
        IEnumerator Cast(string spell, float bodyYaw, float headYaw, float headPitch, Vector3 headOffset, bool walking, System.Action<float, float, float, float, float> done)
        {
            var prefab = Resources.Load("MAGIC/CAST/" + spell);
            if (prefab == null) { done(float.NaN, 0, 0, 0, 0); yield break; }
            pl.transform.position = bodyStart; body.position = bodyStart; body.linearVelocity = Vector3.zero;
            pl.ROT.y = bodyYaw; pl.transform.rotation = Quaternion.Euler(0f, bodyYaw, 0f);
            var rot = Quaternion.Euler(headPitch, headYaw, 0f);
            LunaHeadTracker.TestPose = () => (rot, headOffset);
            float hold = Time.time + 0.5f;
            while (Time.time < hold) { vField.SetValue(pl, walking ? 1f : 0f); yield return null; }
            caster.Cast = null; caster.Prefab = prefab;
            vField.SetValue(pl, walking ? 1f : 0f);
            yield return null;                         // caster.Update casts, mid-frame, as Magic_scr does
            caster.Prefab = null;
            var mag = caster.Cast;
            var headFwd = caster.ParentRotAtCast * rot * Vector3.forward;   // the aim mark's ray at the cast
            var frame = Quaternion.LookRotation(headFwd, caster.ParentRotAtCast * Vector3.up);
            var start = caster.HeadPosAtCast;
            Vector3 early = Vector3.zero; float far = 0f;
            float end = Time.time + 0.5f;
            while (Time.time < end && mag != null)
            {
                vField.SetValue(pl, walking ? 1f : 0f);
                // The spell's path: the part of it furthest ahead along the view (an arrow has parts behind its start
                // on the first frames, which read as 180 degrees). Gravity and bounces change only the vertical.
                Vector3 best = Vector3.zero; float bestAhead = 0f;
                foreach (var t in mag.GetComponentsInChildren<Transform>()) { var d = t.position - start; float ahead = Vector3.Dot(d, headFwd); if (ahead > bestAhead) { bestAhead = ahead; best = d; } }
                if (best.magnitude > far) { far = best.magnitude; early = best; }
                yield return null;
            }
            if (far < 0.5f) early = Vector3.zero;
            vField.SetValue(pl, 0f);
            if (mag != null) Destroy(mag);
            float right = float.NaN, up = float.NaN;
            if (early != Vector3.zero)
            {
                // Walking adds the body's speed to nothing here (spells do not inherit it), but the start moved with the body:
                // measure from the camera's position at the cast, which is where the game spawned it.
                var l = Quaternion.Inverse(frame) * early.normalized;
                right = Mathf.Atan2(l.x, l.z) * Mathf.Rad2Deg; up = Mathf.Atan2(l.y, l.z) * Mathf.Rad2Deg;
            }
            var c = Quaternion.Inverse(frame) * (caster.MainRotAtCast * Vector3.forward);
            done(right, up, Mathf.Atan2(c.x, c.z) * Mathf.Rad2Deg, Mathf.Atan2(c.y, c.z) * Mathf.Rad2Deg, far);
        }

        // 1. Fire and arrow over a grid: head left/right and up/down against a body facing three ways, the head moved
        //    in the room, and walking.
        float[] yaws = { -45f, -20f, 0f, 20f, 45f }, pitches = { -20f, 0f, 20f }, bodies = { 0f, 90f, 200f };
        foreach (var spell in new[] { "FLAME_FLARE_CAST", "ARROW_CAST" })
        {
            int n = 0, bad = 0; float worst = 0f; string worstCase = "";
            var cases = new System.Collections.Generic.List<(float b, float y, float p, Vector3 o, bool w)>();
            foreach (var bY in bodies) foreach (var y in yaws) foreach (var p in pitches) cases.Add((bY, y, p, Vector3.zero, false));
            cases.Add((0f, -30f, 0f, new Vector3(0.2f, 0f, 0.15f), false));
            cases.Add((90f, 30f, -10f, new Vector3(-0.2f, -0.1f, 0f), false));
            cases.Add((0f, -30f, 0f, Vector3.zero, true));
            cases.Add((200f, 20f, 10f, new Vector3(0.1f, 0f, -0.1f), true));
            foreach (var cs in cases)
            {
                float r = 0, u = 0, cr = 0, cu = 0, far = 0;
                yield return Cast(spell, cs.b, cs.y, cs.p, cs.o, cs.w, (a1, a2, a3, a4, a5) => { r = a1; u = a2; cr = a3; cu = a4; far = a5; });
                n++;
                // Horizontal: the complaint. Vertical: an arrow or a fire ball may arc down a little, so only the camera.
                float off = Mathf.Max(float.IsNaN(r) ? 99f : Mathf.Abs(r), Mathf.Abs(cr), Mathf.Abs(cu));
                if (off > worst) { worst = off; worstCase = "body " + cs.b + " head yaw " + cs.y + " pitch " + cs.p + " offset " + cs.o + (cs.w ? " walking" : "") + ": spell right " + r.ToString("F2") + " up " + u.ToString("F2") + ", camera right " + cr.ToString("F2") + " up " + cu.ToString("F2") + ", travelled " + far.ToString("F1"); }
                if (off > 1f) bad++;
            }
            Check("spell.grid." + spell, bad == 0, bad + " of " + n + " casts off the aim mark by more than 1 deg; worst: " + worstCase);
        }

        // 2. Every spell Item_Emit pushes: the PC's way of looking 30 degrees left against VR's (Felipe's case).
        var names = new[] { "ACID_RED_SPIT_CAST", "ACID_SPIT_CAST", "ARROW_CAST", "BARRIER_CAST", "BLEED_CAST", "BLOOD_DRAIN_CAST", "BLOOD_KISS_CAST", "BLOOD_STRIKE_CAST", "BLOOD_STRIKE_CAST2", "BLUE_FLAME_CAST", "BLUE_FLAME_SPEAR_CAST", "BOLT_CAST", "BOLT_CAST2", "BOLT_CAST_NPC", "BOMB_CAST", "BRIDGE_CAST", "BUBBLE_SPIT_CAST", "BULLET_CAST", "CANDLE_CAST", "CICADA_CAST", "COFFIN_CAST", "COMM_CAST", "DAGGER_CAST", "DARK_CAST", "DARK_LIGHT_CAST", "DARK_SPHERE_CAST", "DARK_SPOUT_CAST", "DARK_SWORD_CAST", "DARK_SWORD_CAST_PL", "DARK_WAVE_CAST", "DISP_NPC_CAST", "FANG_CAST", "FIRE_THROW_CAST", "FLAME_FLARE_CAST", "FLAME_SPEAR_CAST", "FLAME_SPOUT_CAST", "FLAME_WORM_CAST2", "GHOST_FLARE_CAST", "GHOST_LIGHT_CAST", "GOB_SPEAR_CAST", "HOOK_CAST", "ICE_SLAM_CAST", "ICE_SPEAR_CAST", "ICE_SPEAR_CAST_PL", "IGNIS_CAST", "JAILOR_CANDLE_CAST", "KODAMA_SUMMON_CAST", "LASER_BEAM_CAST", "LASER_BEAM_CAST2", "LASER_BEAM_CAST3", "LASER_BEAM_CONT_CAST", "LAVA_CAST", "LAVA_FLOOR_CAST", "LIGHTBLADE_CAST", "LIGHTNING2_CAST", "LIGHTNING3_CAST", "LIGHTNING_CAST", "LIGHT_BEAM_CAST", "LIGHT_ORB_CAST", "LIGHT_RAY_CAST", "LIGHT_REVEAL_CAST", "LIGHT_SPARK_CAST", "LIGHT_SPARK_CAST2", "LUCID_CAST", "LUNA_NPC_CAST", "LightOrbPathCast", "MOONLIGHT_CAST", "MOON_BEAM_CAST", "NAVI_SUMMON_CAST", "NPC_DARK_BLAST", "NPC_GHOST_FLARE_CAST", "OBJECTMANCY_CAST", "POISON_WAVE_CAST", "PUMP_CAST", "P_DAGGER_CAST", "P_DAGGER_CAST2", "RIFLE_CAST", "ROCK_CAST", "R_DAGGER_CAST", "SANTA_CAST", "SILK_SPIT_CAST", "SKELETON_SUMMON_CAST", "SKULL_CAST", "SKULL_CAST2", "SLIME_CAST", "SNAIL_SUMMON_CAST", "SNOWROCK_CAST", "SUS_DAGGER_CAST", "SWORD_SUMMON_CAST", "THORN_CAST", "TORNADO_CAST", "TORNADO_NPC_CAST", "TRAP_ARROW_CAST", "TRI_PEST_CAST", "TRI_PEST_CAST2", "TWISTED_STAFF_CAST", "URN1_CAST", "URN2_CAST", "URN3_CAST", "UX_CAST", "UX_CAST_PL", "VOID_CAST", "VOID_NPC_CAST", "WAND_CAST", "WIND_CUT_CAST", "WIND_NPC_CAST", "WISP_BEAM_CAST", "WISP_SUMMON_CAST", "WindPush" };
        int swept = 0, moved = 0, off1 = 0; var offNames = new System.Collections.Generic.List<string>();
        sweepingSpells = true;
        foreach (var spell in names)
        {
            // Enemy and trap casts are not the player's to aim.
            if (spell.Contains("NPC") || spell.StartsWith("TRAP")) continue;
            // Summons walk off on their own (SKELETON_SUMMON, SWORD_SUMMON came out 4 and 8 degrees apart): not aimed.
            if (spell.Contains("SUMMON")) continue;
            // Some casts kill or remove the player (the test is not meant to survive every spell): start the scene again.
            if (pl == null || head == null || caster == null)
            {
                Log("SPELL player gone after the previous cast; reloading PITT_A1");
                Hold_Data.HD = Data(Vector3.zero);
                SceneManager.LoadScene("PITT_A1");
                yield return WaitFrames(3);
                float again = Time.time + 2f;
                while (Time.time < again) yield return null;
                Time.captureFramerate = 50;
                pl = FindObjectOfType<Player_Control_scr>(); head = FindObjectOfType<LunaHeadTracker>();
                cam = head.transform; body = pl.GetComponent<Rigidbody>(); bodyStart = pl.transform.position;
                caster = new GameObject("SpellCaster").AddComponent<SpellCaster>(); caster.Cam = cam;
            }
            // The same view two ways: as on the PC (body turned 30 degrees left, head straight) and as in VR (body
            // straight, head 30 left). A spell aimed by the view takes the same path both times, whatever its own shape
            // (walls, floors, wiggles); one that differs follows the body instead of the view.
            float r0 = 0, r = 0, cr = 0, far = 0;
            yield return Cast(spell, -30f, 0f, 0f, Vector3.zero, false, (a1, a2, a3, a4, a5) => { r0 = a1; });
            if (pl == null || caster == null) { swept++; continue; }
            yield return Cast(spell, 0f, -30f, 0f, Vector3.zero, false, (a1, a2, a3, a4, a5) => { r = a1; cr = a3; far = a5; });
            swept++;
            if (float.IsNaN(r) || float.IsNaN(r0)) continue;   // did not move 0.5 m in half a second (summons, beams)
            moved++;
            if (Mathf.Abs(r - r0) > 1f || Mathf.Abs(cr) > 0.5f) { off1++; offNames.Add(spell + " (as on the PC " + r0.ToString("F1") + ", in VR " + r.ToString("F1") + ")"); }
        }
        sweepingSpells = false;
        if (caster != null) Destroy(caster.gameObject);
        Check("spell.every_item_emit", off1 == 0 && moved > 20, moved + " of " + swept + " spells flew; off the aim mark: " + string.Join(", ", offNames));
        LunaHeadTracker.TestPose = null;
    }

    // What the headset shows in a level: every camera drawing to it, in depth order, into one picture.
    void ShotHud(string name, bool fullPath = false)
    {
        var rt = new RenderTexture(fullPath ? 960 : 1600, fullPath ? 540 : 900, 24);
        // LUNA_PROBE_FOV=<degrees>: the headset's field of view instead of the game camera's (the Quest 3S shows about 96).
        float.TryParse(System.Environment.GetEnvironmentVariable("LUNA_PROBE_FOV") ?? "", System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float fov);
        foreach (var c in Camera.allCameras.Where(c => c.targetTexture == null && c.stereoTargetEye != StereoTargetEyeMask.None).OrderBy(c => c.depth))
        {
            float fovWas = c.fieldOfView;
            if (fov > 1f) c.fieldOfView = fov;
            c.targetTexture = rt;
            c.Render();
            c.targetTexture = null;
            c.fieldOfView = fovWas;
        }
        var was = RenderTexture.active;
        RenderTexture.active = rt;
        var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
        RenderTexture.active = was;
        System.IO.File.WriteAllBytes(fullPath ? name : "/tmp/luna_probe_hud_" + name + ".png", tex.EncodeToPNG());
        Destroy(tex);
        rt.Release();
    }

    void Shot(string name)
    {
        var theater = FindObjectOfType<LunaTheater>();
        var rt = theater.Texture;
        var was = RenderTexture.active;
        RenderTexture.active = rt;
        var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
        RenderTexture.active = was;
        System.IO.File.WriteAllBytes("/tmp/luna_probe_" + name + ".png", tex.EncodeToPNG());
        Log("shot " + name + " " + rt.width + "x" + rt.height);
    }
}

public static class LunaProbeRun
{
    public static void Run()
    {
        UnityEditor.SceneManagement.EditorSceneManager.OpenScene("Assets/Scenes/MainMenu.unity");
        UnityEditor.EditorApplication.isPlaying = true;
    }
}
#endif
