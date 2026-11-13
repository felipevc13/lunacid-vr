#!/usr/bin/env python3
"""tools/setup/setup_machine.py: `lunacid_vr.py setup` gets everything a build needs, for people who never used
these tools (2026-11-13, the Windows notebook: Git, SteamCMD and the guide's manual steps went wrong one by one).

Downloads and programs are stand-ins: the tests check what would be fetched, checked, run and written."""

import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "setup"))
import setup_machine as sm  # noqa: E402
import lunacid_vr  # noqa: E402

PROFILE = {"appid": 1745510, "steam_depot": 1745511, "game_versions": [
    {"steam_build": 24780950, "manifest": "9110162109347716163",
     "sha256": {"Managed/Assembly-CSharp.dll": hashlib.sha256(b"code").hexdigest(),
                "globalgamemanagers": hashlib.sha256(b"ggm").hexdigest()}}]}


def write(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def make_game(folder, code=b"code"):
    write(os.path.join(folder, "LUNACID_Data", "Managed", "Assembly-CSharp.dll"), code)
    write(os.path.join(folder, "LUNACID_Data", "globalgamemanagers"), b"ggm")
    return os.path.join(folder, "LUNACID_Data")


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def tar_xz_bytes(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class Fake:
    """Downloads from a dict of url -> bytes; programs answer from a list of rules."""

    def __init__(self, files=None):
        self.files = dict(files or {})
        self.downloads = []
        self.runs = []
        self.rules = []          # (predicate(cmd), function(cmd) -> (rc, out))

    def download(self, url, dest):
        self.downloads.append(url)
        if url not in self.files:
            raise sm.Problem("no such download in the test: %s" % url)
        write(dest, self.files[url])

    def run(self, cmd, interactive=False):
        self.runs.append(list(cmd))
        for pred, fn in self.rules:
            if pred(cmd):
                return fn(cmd)
        return 1, "not found"

    def words(self):
        return " ".join(" ".join(c) for c in self.runs)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.tools = os.path.join(self.work, "tools")

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestAssetRipper(Base):
    def test_the_right_file_for_each_computer(self):
        self.assertEqual(sm.assetripper_asset("Windows", "x64")[0], "AssetRipper_win_x64.zip")
        self.assertEqual(sm.assetripper_asset("Windows", "arm64")[0], "AssetRipper_win_arm64.zip")
        self.assertEqual(sm.assetripper_asset("Darwin", "arm64")[0], "AssetRipper_mac_arm64.tar.xz")
        self.assertEqual(sm.assetripper_asset("Darwin", "x64")[0], "AssetRipper_mac_x64.tar.xz")
        # pinned to the SHA-256 GitHub publishes for release 2.0.0
        self.assertEqual(sm.assetripper_asset("Windows", "x64")[1],
                         "9a7ef0e7c5c3ea5b90b4e6d855e2d98d5f7ec8c3f9e26fccbc194c6a7b01baf7")

    def test_downloads_checks_and_unpacks(self):
        data = zip_bytes({"AssetRipper.GUI.Free.exe": b"exe", "other.dll": b"x"})
        url = sm.ASSETRIPPER_BASE + "AssetRipper_win_x64.zip"
        fake = Fake({url: data})
        pins = {("Windows", "x64"): ("AssetRipper_win_x64.zip", hashlib.sha256(data).hexdigest())}
        exe = sm.install_assetripper(self.tools, "Windows", "x64", fake.download, pins=pins)
        self.assertTrue(exe.endswith("AssetRipper.GUI.Free.exe"))
        self.assertTrue(os.path.exists(exe))

    def test_mac_tar_xz_in_a_folder(self):
        data = tar_xz_bytes({"AssetRipper_mac_arm64/AssetRipper.GUI.Free": b"bin"})
        url = sm.ASSETRIPPER_BASE + "AssetRipper_mac_arm64.tar.xz"
        pins = {("Darwin", "arm64"): ("AssetRipper_mac_arm64.tar.xz", hashlib.sha256(data).hexdigest())}
        exe = sm.install_assetripper(self.tools, "Darwin", "arm64", Fake({url: data}).download, pins=pins)
        self.assertTrue(exe.endswith("AssetRipper.GUI.Free"))
        self.assertTrue(os.access(exe, os.X_OK))

    def test_a_changed_download_is_refused(self):
        url = sm.ASSETRIPPER_BASE + "AssetRipper_win_x64.zip"
        fake = Fake({url: zip_bytes({"AssetRipper.GUI.Free.exe": b"tampered"})})
        with self.assertRaises(sm.Problem):
            sm.install_assetripper(self.tools, "Windows", "x64", fake.download)
        self.assertIsNone(sm.find_file(os.path.join(self.tools, "AssetRipper"), "AssetRipper.GUI.Free.exe"))

    def test_already_there_is_not_downloaded_again(self):
        write(os.path.join(self.tools, "AssetRipper", "AssetRipper.GUI.Free.exe"), b"exe")
        fake = Fake()
        sm.install_assetripper(self.tools, "Windows", "x64", fake.download)
        self.assertEqual(fake.downloads, [])


class TestSteamCMD(Base):
    def steamcmd_ok(self, fake):
        fake.rules.append((lambda c: c[-1] == "+quit" and len(c) == 2,
                           lambda c: (0, "Update complete, launching Steamcmd...\nLoading Steam API...OK")))

    def test_uses_one_already_unpacked(self):
        mine = os.path.join(self.tmp, "C_steamcmd", "steamcmd.exe")
        write(mine, b"exe")
        fake = Fake()
        self.steamcmd_ok(fake)
        exe = sm.install_steamcmd(self.tools, "Windows", fake.download, fake.run, known=[mine], say=lambda *a: None)
        self.assertEqual(exe, mine)
        self.assertEqual(fake.downloads, [])

    def test_downloads_unpacks_and_updates(self):
        fake = Fake({sm.STEAMCMD_URL["Windows"]: zip_bytes({"steamcmd.exe": b"exe"})})
        self.steamcmd_ok(fake)
        exe = sm.install_steamcmd(self.tools, "Windows", fake.download, fake.run, known=[], say=lambda *a: None)
        self.assertEqual(exe, os.path.join(self.tools, "steamcmd", "steamcmd.exe"))
        self.assertIn([exe, "+quit"], fake.runs)

    def test_failed_self_update_is_cleaned_and_retried(self):
        # The notebook: "Failed to apply update, reverting... Fatal Error: Failed to load steam.dll".
        fake = Fake({sm.STEAMCMD_URL["Windows"]: zip_bytes({"steamcmd.exe": b"exe"})})
        tries = []

        def update(cmd):
            tries.append(sorted(os.listdir(os.path.dirname(cmd[0]))))
            if len(tries) == 1:
                write(os.path.join(os.path.dirname(cmd[0]), "package", "broken.zip"), b"x")
                return 0, "Failed to apply update, reverting...\n!!! Fatal Error: Failed to load steam.dll"
            return 0, "Loading Steam API...OK"
        fake.rules.append((lambda c: c[-1] == "+quit", update))
        sm.install_steamcmd(self.tools, "Windows", fake.download, fake.run, known=[], say=lambda *a: None)
        self.assertEqual(len(tries), 2)
        self.assertEqual(tries[1], ["steamcmd.exe"])          # emptied except the program before the retry

    def test_still_failing_on_windows_asks_for_an_administrator_terminal(self):
        fake = Fake({sm.STEAMCMD_URL["Windows"]: zip_bytes({"steamcmd.exe": b"exe"})})
        fake.rules.append((lambda c: c[-1] == "+quit", lambda c: (0, "!!! Fatal Error: Failed to load steam.dll")))
        with self.assertRaises(sm.Problem) as ctx:
            sm.install_steamcmd(self.tools, "Windows", fake.download, fake.run, known=[], say=lambda *a: None)
        self.assertIn("administrator", str(ctx.exception))


class TestGame(Base):
    def test_a_folder_with_the_right_version_is_used_as_is(self):
        data = make_game(os.path.join(self.tmp, "depot"))
        fake = Fake()
        asked = []
        found = sm.get_game(PROFILE, "C:/steamcmd/steamcmd.exe", fake.run, ask=asked.append,
                            candidates=[data], say=lambda *a: None)
        self.assertEqual(found, data)
        self.assertEqual(asked, [])
        self.assertEqual(fake.runs, [])

    def test_downloads_with_the_user_name_typed_and_finds_the_depot(self):
        steamcmd = os.path.join(self.tmp, "steamcmd", "steamcmd.exe")
        write(steamcmd, b"exe")
        depot = os.path.join(self.tmp, "steamcmd", "steamapps", "content", "app_1745510", "depot_1745511")
        fake = Fake()
        fake.rules.append((lambda c: "+download_depot" in c, lambda c: (make_game(depot), (0, ""))[1]))
        found = sm.get_game(PROFILE, steamcmd, fake.run, ask=lambda q: "someone", candidates=[],
                            say=lambda *a: None)
        self.assertEqual(found, os.path.join(depot, "LUNACID_Data"))
        cmd = fake.runs[0]
        self.assertEqual(cmd[cmd.index("+login") + 1], "someone")
        self.assertEqual(cmd[cmd.index("+download_depot") + 1:cmd.index("+download_depot") + 4],
                         ["1745510", "1745511", "9110162109347716163"])

    def test_a_different_version_is_refused(self):
        data = make_game(os.path.join(self.tmp, "steam_install"), code=b"updated")
        with self.assertRaises(sm.Problem):
            sm.get_game(PROFILE, None, Fake().run, ask=lambda q: "", candidates=[data], say=lambda *a: None,
                        download=False)


class TestDotnet(Base):
    def test_dotnet_8_already_there(self):
        fake = Fake()
        fake.rules.append((lambda c: c[1:] == ["--list-sdks"], lambda c: (0, "8.0.404 [C:\\Program Files\\dotnet\\sdk]")))
        self.assertEqual(sm.install_dotnet(self.tools, "Windows", fake.download, fake.run, which=lambda n: "dotnet",
                                           say=lambda *a: None), "dotnet")
        self.assertEqual(fake.downloads, [])

    def test_installs_into_the_work_folder_without_admin(self):
        fake = Fake({sm.DOTNET_SCRIPT["Windows"]: b"script"})
        target = os.path.join(self.tools, "dotnet")
        fake.rules.append((lambda c: "-InstallDir" in c, lambda c: (write(os.path.join(target, "dotnet.exe")), (0, "ok"))[1]))
        got = sm.install_dotnet(self.tools, "Windows", fake.download, fake.run, which=lambda n: None,
                                say=lambda *a: None)
        self.assertEqual(got, os.path.join(target, "dotnet.exe"))
        cmd = [c for c in fake.runs if "-InstallDir" in c][0]
        self.assertIn("8.0", cmd)
        self.assertEqual(cmd[cmd.index("-InstallDir") + 1], target)


class TestUnity(Base):
    def test_editor_and_android_present(self):
        self.assertIsNone(sm.unity_command("hub", editor=True, android=True))

    def test_installs_the_exact_version_with_android_and_its_children(self):
        cmd = sm.unity_command("hub", editor=False, android=False)
        self.assertEqual(cmd[:3], ["hub", "--", "--headless"])
        for words in (["install"], ["--version", "6000.0.85f1"], ["--changeset", "ee7790f1426a"],
                      ["--module", "android"], ["--childModules"]):
            self.assertTrue(any(cmd[i:i + len(words)] == words for i in range(len(cmd))), (words, cmd))

    def test_adds_android_to_an_editor_without_it(self):
        cmd = sm.unity_command("hub", editor=True, android=False)
        self.assertIn("install-modules", cmd)
        self.assertIn("--childModules", cmd)

    def test_no_hub_on_windows_uses_winget(self):
        fake = Fake()
        installed = []
        fake.rules.append((lambda c: c[0] == "winget", lambda c: (installed.append(1), (0, "Successfully installed"))[1]))
        hub = sm.ensure_hub("Windows", fake.run, exists=lambda p: bool(installed), which=lambda n: "winget",
                            say=lambda *a: None)
        self.assertIn("Unity.UnityHub", fake.words())
        self.assertEqual(hub, sm.HUB["Windows"])

    def test_no_hub_on_a_mac_installs_it_from_unitys_disk_image(self):
        url = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup-arm64.dmg"
        fake = Fake({url: b"dmg"})
        copied = []
        fake.rules.append((lambda c: c[:2] == ["hdiutil", "attach"], lambda c: (0, "/dev/disk9\t\t/Volumes/Unity Hub 3.9.0")))
        fake.rules.append((lambda c: c[0] == "cp", lambda c: (copied.append(c), (0, ""))[1]))
        fake.rules.append((lambda c: c[:2] == ["hdiutil", "detach"], lambda c: (0, "")))
        hub = sm.ensure_hub("Darwin", fake.run, exists=lambda p: bool(copied), which=lambda n: None,
                            say=lambda *a: None, fetch=fake.download, cpu="arm64", tools=self.tools)
        self.assertEqual(fake.downloads, [url])
        self.assertEqual(copied[0][-2:], ["/Volumes/Unity Hub 3.9.0/Unity Hub.app", "/Applications/"])
        self.assertIn(["hdiutil", "detach", "/Volumes/Unity Hub 3.9.0"], fake.runs)
        self.assertEqual(hub, sm.HUB["Darwin"])

    def test_no_winget_on_windows_uses_unitys_installer(self):
        url = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup-x64.exe"
        fake = Fake({url: b"exe"})
        done = []
        fake.rules.append((lambda c: c[0] == "powershell", lambda c: (done.append(c), (0, ""))[1]))
        sm.ensure_hub("Windows", fake.run, exists=lambda p: bool(done), which=lambda n: None, say=lambda *a: None,
                      fetch=fake.download, cpu="x64", tools=self.tools)
        self.assertIn("UnityHubSetup-x64.exe' -ArgumentList '/S'", done[0][-1])   # silent install, elevated


class TestWindowsInstallerNeedsPermission(Base):
    """2026-11-13 on the notebook: Unity's installer refused to start without elevation ('[WinError 740] A operação
    solicitada requer elevação') and setup died with a traceback."""

    def test_a_program_that_cannot_start_is_an_answer_not_a_crash(self):
        rc, out = sm.run(["this-program-does-not-exist-anywhere"])
        self.assertNotEqual(rc, 0)
        self.assertTrue(out)

    def test_the_installer_is_run_again_asking_for_permission(self):
        url = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup-x64.exe"
        fake = Fake({url: b"exe"})
        done = []
        fake.rules.append((lambda c: c[0].endswith("UnityHubSetup-x64.exe"),
                           lambda c: (1, "[WinError 740] A operação solicitada requer elevação")))
        fake.rules.append((lambda c: c[0] == "powershell" and "RunAs" in " ".join(c),
                           lambda c: (done.append(c), (0, ""))[1]))
        hub = sm.ensure_hub("Windows", fake.run, exists=lambda p: bool(done) and p == sm.HUB["Windows"],
                            which=lambda n: None, say=lambda *a: None, fetch=fake.download, cpu="x64",
                            tools=self.tools)
        self.assertEqual(hub, sm.HUB["Windows"])
        line = " ".join(done[0])
        self.assertIn("Start-Process", line)
        self.assertIn("-Wait", line)
        self.assertIn("/S", line)

    def test_a_hub_installed_elsewhere_is_found(self):
        other = os.path.join(self.tmp, "Programs", "Unity Hub", "Unity Hub.exe")
        write(other, b"exe")
        hub = sm.ensure_hub("Windows", Fake().run, which=lambda n: None, say=lambda *a: None,
                            candidates=[sm.HUB["Windows"], other])
        self.assertEqual(hub, other)

    def test_winget_failing_says_what_it_answered(self):
        url = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup-x64.exe"
        fake = Fake({url: b"exe"})
        said = []
        fake.rules.append((lambda c: c[0] == "winget", lambda c: (1, "No package found matching input criteria.")))
        fake.rules.append((lambda c: True, lambda c: (0, "")))
        with self.assertRaises(sm.Problem):
            sm.ensure_hub("Windows", fake.run, exists=lambda p: False, which=lambda n: "winget", say=said.append,
                          fetch=fake.download, cpu="x64", tools=self.tools)
        self.assertTrue(any("No package found" in line for line in said), said)


class TestProgress(Base):
    """Felipe: a download with no number looks stuck, and people give up. Show how far each one is."""

    def test_a_download_says_its_percentage(self):
        src = os.path.join(self.tmp, "big.bin")
        write(src, b"x" * (3 * 1024 * 1024 + 7))
        said = []
        dest = os.path.join(self.tmp, "out", "big.bin")
        sm.download("file://" + src, dest, label="AssetRipper", say=said.append)
        with open(dest, "rb") as fh:
            self.assertEqual(len(fh.read()), 3 * 1024 * 1024 + 7)
        self.assertTrue(any("100%" in line and "AssetRipper" in line for line in said), said)
        self.assertTrue(any("MB" in line for line in said), said)

    def test_percentage_line(self):
        self.assertEqual(sm.progress_line("SteamCMD", 5 * 1024 * 1024, 20 * 1024 * 1024),
                         "SteamCMD: 25% (5 of 20 MB)")
        self.assertEqual(sm.progress_line("SteamCMD", 5 * 1024 * 1024, 0), "SteamCMD: 5 MB")

    def test_unity_uses_hubs_own_percentage_when_it_prints_one(self):
        log = os.path.join(self.tmp, "unity_install.log")
        write(log, b"Downloading Unity 6000.0.85f1...\nprogress: 12%\nprogress: 47.5%\n")
        line = sm.unity_progress(log, os.path.join(self.tmp, "Editor"), minutes=12)
        self.assertIn("47%", line)
        self.assertIn("about 14 min left", line)     # 47% in 12 min

    def test_unity_otherwise_measures_what_is_installed(self):
        log = os.path.join(self.tmp, "unity_install.log")
        write(log, b"Downloading Unity 6000.0.85f1...\n")
        editor = os.path.join(self.tmp, "Editor")
        write(os.path.join(editor, "a.bin"), b"x" * (2 * 1024 * 1024))
        line = sm.unity_progress(log, editor, minutes=3, total=8 * 1024 * 1024)
        self.assertIn("25%", line)
        self.assertIn("about 9 min left", line)      # 25% in 3 min

    def test_how_long_is_left(self):
        # 5 of 20 MB in 60 s: 15 MB more at that speed is 180 s.
        self.assertEqual(sm.progress_line("Unity", 5 * 1024 * 1024, 20 * 1024 * 1024, seconds=60),
                         "Unity: 25% (5 of 20 MB), about 3 min left")
        self.assertIn("less than a minute", sm.progress_line("x", 19 * 1024 * 1024, 20 * 1024 * 1024, seconds=60))
        self.assertNotIn("left", sm.progress_line("x", 1, 20 * 1024 * 1024, seconds=1))   # too early to guess

    def test_unity_says_how_long_is_left(self):
        log = os.path.join(self.tmp, "unity_install.log")
        write(log, b"progress: 40%\n")
        # 40% in 20 min: 60% more at that pace is 30 min.
        self.assertIn("about 30 min left", sm.unity_progress(log, None, minutes=20))

    def test_unity_never_says_100_before_it_is_done(self):
        editor = os.path.join(self.tmp, "Editor")
        write(os.path.join(editor, "a.bin"), b"x" * 100)
        self.assertIn("99%", sm.unity_progress(None, editor, minutes=1, total=50))


class TestSignIn(Base):
    """Unity needs a licence before it builds: ask for the Hub sign-in at the start, not hours later."""

    def test_opens_the_hub_and_waits_for_the_person(self):
        opened, asked = [], []
        state = {"ok": False}

        def ask(q):
            asked.append(q)
            state["ok"] = True
            return ""
        sm.sign_in(self.tmp, "Darwin", "hub", ask=ask, launch=opened.append, say=lambda *a: None,
                   check=lambda home, system: ("OK", "") if state["ok"] else ("WARN", "no licence"))
        self.assertEqual(opened, ["hub"])
        self.assertEqual(len(asked), 1)

    def test_already_signed_in(self):
        opened = []
        sm.sign_in(self.tmp, "Darwin", "hub", ask=lambda q: self.fail("asked"), launch=opened.append,
                   say=lambda *a: None, check=lambda home, system: ("OK", ""))
        self.assertEqual(opened, [])


class TestLocalJson(Base):
    def test_example_text_is_dropped_real_values_kept_found_paths_added(self):
        local = os.path.join(self.tmp, "local.json")
        with open(local, "w") as fh:
            json.dump({"work": "~/lunacid-work", "unity": "leave out to use Unity Hub's default install of 6000.0.85f1",
                       "game_data": "path to the game's LUNACID_Data folder", "android_sdk": "D:\\my\\sdk"}, fh)
        sm.update_local(local, {"game_data": "C:\\steamcmd\\steamapps\\LUNACID_Data", "assetripper": "C:\\A\\a.exe"})
        with open(local) as fh:
            got = json.load(fh)
        self.assertEqual(got, {"work": "~/lunacid-work", "android_sdk": "D:\\my\\sdk",
                               "game_data": "C:\\steamcmd\\steamapps\\LUNACID_Data", "assetripper": "C:\\A\\a.exe"})

    def test_the_same_path_written_differently_is_kept_as_the_person_wrote_it(self):
        local = os.path.join(self.tmp, "local.json")
        with open(local, "w") as fh:
            json.dump({"dotnet": "~/tools/dotnet"}, fh)
        sm.update_local(local, {"dotnet": os.path.expanduser("~/tools/dotnet")})
        with open(local) as fh:
            self.assertEqual(json.load(fh), {"dotnet": "~/tools/dotnet"})

    def test_no_file_yet(self):
        local = os.path.join(self.tmp, "local.json")
        sm.update_local(local, {"dotnet": "dotnet"})
        with open(local) as fh:
            self.assertEqual(json.load(fh), {"dotnet": "dotnet"})


class TestSetupNeverKeepsTheSteamLogin(Base):
    def test_user_name_is_not_written_anywhere(self):
        steamcmd = os.path.join(self.tmp, "steamcmd", "steamcmd.exe")
        write(steamcmd, b"exe")
        depot = os.path.join(self.tmp, "steamcmd", "steamapps", "content", "app_1745510", "depot_1745511")
        fake = Fake()
        fake.rules.append((lambda c: "+download_depot" in c, lambda c: (make_game(depot), (0, ""))[1]))
        data = sm.get_game(PROFILE, steamcmd, fake.run, ask=lambda q: "secretname", candidates=[],
                           say=lambda *a: None)
        local = os.path.join(self.tmp, "local.json")
        sm.update_local(local, {"game_data": data})
        for top, _, files in os.walk(self.tmp):
            for f in files:
                with open(os.path.join(top, f), "rb") as fh:
                    self.assertNotIn(b"secretname", fh.read(), f)


class TestBuildMakesTheProjectFirst(Base):
    def test_missing_project_is_extracted_and_shaders_made_before_building(self):
        cfg = {"work": self.work, "project": os.path.join(self.work, "project", "ExportedProject"),
               "game_data": os.path.join(self.tmp, "LUNACID_Data")}
        seen = []
        lunacid_vr.build(cfg=cfg, run=lambda cmd: seen.append(cmd) or 0)
        scripts = [os.path.basename(c[1]) for c in seen]
        self.assertEqual(scripts, ["assetripper.py", "make_shaders.py", "build.py"])
        self.assertEqual(seen[0][seen[0].index("--out") + 1], os.path.join(self.work, "project"))

    def test_a_half_export_is_extracted_again(self):
        project = os.path.join(self.work, "project", "ExportedProject")
        os.makedirs(os.path.join(project, "Assets"))             # no mark, never opened by Unity
        os.makedirs(os.path.join(self.work, "shader_gen", "generated"))
        seen = []
        lunacid_vr.build(cfg={"work": self.work, "project": project, "game_data": "x"},
                         run=lambda cmd: seen.append(cmd) or 0)
        self.assertEqual([os.path.basename(c[1]) for c in seen], ["assetripper.py", "build.py"])

    def test_existing_project_goes_straight_to_the_build(self):
        project = os.path.join(self.work, "project", "ExportedProject")
        os.makedirs(os.path.join(project, "Assets"))
        os.makedirs(os.path.join(project, "Library"))
        os.makedirs(os.path.join(self.work, "shader_gen", "generated"))
        seen = []
        lunacid_vr.build(cfg={"work": self.work, "project": project, "game_data": "x"},
                         run=lambda cmd: seen.append(cmd) or 0)
        self.assertEqual([os.path.basename(c[1]) for c in seen], ["build.py"])

    def test_a_failed_step_stops_the_rest(self):
        cfg = {"work": self.work, "project": os.path.join(self.work, "project", "ExportedProject"), "game_data": "x"}
        seen = []
        rc = lunacid_vr.build(cfg=cfg, run=lambda cmd: seen.append(cmd) or 2)
        self.assertEqual(rc, 2)
        self.assertEqual(len(seen), 1)


class TestDoctorLicence(Base):
    def test_no_unity_licence_warns(self):
        status, detail = sm.check_licence(self.tmp, "Darwin")
        self.assertEqual(status, "WARN")
        self.assertIn("Unity Hub", detail)
        write(os.path.join(self.tmp, "Library", "Unity", "licenses", "UnityEntitlementLicense.xml"), b"x")
        self.assertEqual(sm.check_licence(self.tmp, "Darwin")[0], "OK")


if __name__ == "__main__":
    unittest.main()
