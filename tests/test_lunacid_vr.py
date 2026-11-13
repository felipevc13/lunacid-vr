#!/usr/bin/env python3
"""lunacid_vr.py, the one command for people who build the port: backup, install, build, doctor.

The Quest is simulated at the level of adb's arguments (FakeQuest), so the tests check the real commands sent
to the headset without one plugged in."""

import json
import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import lunacid_vr  # noqa: E402

PKG = "com.AkumaKira.LunacidVR"
FILES = "/sdcard/Android/data/%s/files" % PKG
OBB_DIR = "/sdcard/Android/obb/%s" % PKG


class FakeQuest:
    """adb as seen by lunacid_vr.Device: a dict of remote files and the list of every call."""

    def __init__(self, files=None, connected=True):
        self.files = dict(files or {})
        self.connected = connected
        self.calls = []
        self.empty_pulls = False        # a pull that writes nothing and still says OK (seen 2026-11-09)
        self.install_wipes_saves = False
        self.short_push = False
        self.corrupt_push = False       # same size, different bytes
        self.installed = True
        self.files_dir = True           # the game made its files folder (it runs once after an install)
        self.modes = {}                 # adb push leaves 644 owned by shell; the game (another uid) cannot write

    def __call__(self, args):
        self.raw_calls = getattr(self, "raw_calls", []) + [list(args)]
        if args[:1] == ["-s"]:
            args = args[2:]
        self.calls.append(list(args))
        if not self.connected:
            return 1, "adb: no devices/emulators found"
        cmd = args[0]
        if cmd == "get-state":
            return 0, "device"
        if cmd == "pull":
            remote, local = args[1], args[2]
            if remote not in self.files:
                return 1, "remote object '%s' does not exist" % remote
            with open(local, "wb") as fh:
                fh.write(b"" if self.empty_pulls else self.files[remote])
            return 0, "1 file pulled"
        if cmd == "push":
            local, remote = args[1], args[2]
            with open(local, "rb") as fh:
                data = fh.read()
            if self.corrupt_push and data:
                data = bytes([data[0] ^ 1]) + data[1:]
            self.files[remote] = data[:-1] if self.short_push else data
            return 0, "1 file pushed"
        if cmd == "install":
            if self.install_wipes_saves:
                self.files = {k: v for k, v in self.files.items() if not k.endswith(".MIDNIGHT")}
            return 0, "Performing Streamed Install\nSuccess"
        if cmd == "shell":
            return self.shell(args[1])
        return 1, "unknown command %s" % cmd

    def shell(self, line):
        if line.startswith("find "):
            folder = line.split()[1]
            out = ["%d|%s" % (len(v), k) for k, v in sorted(self.files.items())
                   if os.path.dirname(k) == folder and k.endswith(".MIDNIGHT")]
            return 0, "\n".join(out)
        if line.startswith("stat -c %s "):
            path = line[len("stat -c %s "):].strip("'")
            return (0, str(len(self.files[path]))) if path in self.files else (1, "No such file")
        if line.startswith("cat "):
            path = line[4:].strip("'")
            return (0, self.files[path].decode()) if path in self.files else (1, "No such file")
        if line.startswith("pm path "):
            return (0, "package:/data/app/x/base.apk") if self.installed else (1, "")
        if line.startswith("am force-stop "):
            return 0, ""
        if line.startswith("ls -d "):
            return (0, line[6:].strip("'")) if self.files_dir else (1, "No such file or directory")
        if line.startswith("md5sum "):
            import hashlib
            path = line[7:].strip("'")
            if path not in self.files:
                return 1, "No such file"
            return 0, "%s  %s" % (hashlib.md5(self.files[path]).hexdigest(), path)
        if line.startswith("chmod "):
            mode, path = line[6:].split(" ", 1)
            self.modes[path.strip("'")] = mode
            return 0, ""
        if line.startswith("stat -c %a "):
            path = line[len("stat -c %a "):].strip("'")
            return (0, self.modes.get(path, "644")) if path in self.files else (1, "No such file")
        if line.startswith("mkdir -p "):
            return 0, ""
        if line.startswith("echo "):
            text, path = line[5:].split(" > ")
            self.files[path.strip("'")] = text.strip("'").encode()
            return 0, ""
        return 1, "unknown shell %s" % line

    def adb_words(self):
        return [w for call in self.calls for w in call]


SAVES = {FILES + "/SAVE_0.MIDNIGHT": b"slot one" * 100, FILES + "/SETTINGS.MIDNIGHT": b"settings",
         FILES + "/luna_test_inventory.txt.off": b""}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = {"work": os.path.join(self.tmp, "work")}
        os.makedirs(self.cfg["work"])

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestBackup(Base):
    def test_every_save_file_by_file_with_sizes(self):
        quest = FakeQuest(SAVES)
        out = lunacid_vr.backup(self.cfg, lunacid_vr.Device(quest), stamp="20261112_2300")
        self.assertEqual(out, os.path.join(self.cfg["work"], "backups", "20261112_2300"))
        self.assertEqual(sorted(f for f in os.listdir(out) if f.endswith(".MIDNIGHT")),
                         ["SAVE_0.MIDNIGHT", "SETTINGS.MIDNIGHT"])
        with open(os.path.join(out, "SAVE_0.MIDNIGHT"), "rb") as fh:
            self.assertEqual(fh.read(), SAVES[FILES + "/SAVE_0.MIDNIGHT"])
        with open(os.path.join(out, "backup.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["saves"], {"SAVE_0.MIDNIGHT": 800, "SETTINGS.MIDNIGHT": 8})

    def test_never_pulls_the_whole_folder(self):
        quest = FakeQuest(SAVES)
        lunacid_vr.backup(self.cfg, lunacid_vr.Device(quest), stamp="x")
        pulls = [c[1] for c in quest.calls if c[0] == "pull"]
        self.assertEqual(len(pulls), 2)
        self.assertTrue(all(p.endswith(".MIDNIGHT") for p in pulls), pulls)

    def test_a_pull_that_copies_nothing_fails(self):
        quest = FakeQuest(SAVES)
        quest.empty_pulls = True
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            lunacid_vr.backup(self.cfg, lunacid_vr.Device(quest), stamp="x")
        self.assertIn("SAVE_0.MIDNIGHT", str(ctx.exception))

    def test_copies_the_signing_key(self):
        key = os.path.join(self.cfg["work"], "keystore")
        os.makedirs(key)
        for name in ("lunacid-vr.keystore", "keystore.json"):
            with open(os.path.join(key, name), "w") as fh:
                fh.write(name)
        out = lunacid_vr.backup(self.cfg, lunacid_vr.Device(FakeQuest(SAVES)), stamp="x")
        self.assertEqual(sorted(os.listdir(os.path.join(out, "keystore"))), ["keystore.json", "lunacid-vr.keystore"])

    def test_no_headset_is_a_clear_error(self):
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            lunacid_vr.backup(self.cfg, lunacid_vr.Device(FakeQuest(SAVES, connected=False)), stamp="x")
        self.assertIn("Quest", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(self.cfg["work"], "backups", "x")))

    def test_no_saves_yet_is_fine(self):
        out = lunacid_vr.backup(self.cfg, lunacid_vr.Device(FakeQuest({})), stamp="x")
        with open(os.path.join(out, "backup.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["saves"], {})


class TestInstall(Base):
    """Backup first, OBB only when it changed, adb install -r (never uninstall), saves checked afterwards."""

    def make_build(self, name, obb=True, apk=b"apk bytes"):
        folder = os.path.join(self.cfg["work"], "builds", name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "Lunacid_Quest.apk"), "wb") as fh:
            fh.write(apk)
        if obb:
            with open(os.path.join(folder, "Lunacid_Quest.main.obb"), "wb") as fh:
                fh.write(b"obb of " + name.encode())
        return folder

    def install(self, quest, **kw):
        kw.setdefault("signature_check", lambda apk: "")
        return lunacid_vr.install(self.cfg, lunacid_vr.Device(quest), stamp="20261112_2300", **kw)

    def test_newest_build_and_its_obb(self):
        full = self.make_build("20261112_1437")
        fast = self.make_build("20261112_2038", obb=False)
        self.make_build("20261112_2100_failed")
        self.make_build("20261112_2200_later_failed", obb=False)
        os.makedirs(os.path.join(self.cfg["work"], "builds", "._20261112_2300"))
        apk, obb = lunacid_vr.newest_build(self.cfg)
        self.assertEqual(apk, os.path.join(fast, "Lunacid_Quest.apk"))
        self.assertEqual(obb, os.path.join(full, "Lunacid_Quest.main.obb"))

    def test_no_build_is_a_clear_error(self):
        with self.assertRaises(lunacid_vr.Problem):
            self.install(FakeQuest(SAVES))

    def test_backup_obb_install_in_that_order(self):
        self.make_build("20261112_1437")
        quest = FakeQuest(SAVES)
        self.install(quest)
        kinds = [c[0] for c in quest.calls]
        self.assertLess(kinds.index("pull"), kinds.index("push"))
        self.assertLess(kinds.index("push"), kinds.index("install"))
        self.assertTrue(os.path.exists(os.path.join(self.cfg["work"], "backups", "20261112_2300", "SAVE_0.MIDNIGHT")))
        dest = "%s/main.1.%s.obb" % (OBB_DIR, PKG)
        self.assertEqual(quest.files[dest], b"obb of 20261112_1437")
        install = [c for c in quest.calls if c[0] == "install"][0]
        self.assertEqual(install[:2], ["install", "-r"])

    def test_never_uninstalls(self):
        self.make_build("20261112_1437")
        quest = FakeQuest(SAVES)
        quest.install_wipes_saves = True
        with self.assertRaises(lunacid_vr.Problem):
            self.install(quest)
        self.assertFalse(any("uninstall" in w or "pm clear" in w for w in quest.adb_words()))

    def test_obb_stamp_matches_quest_tour(self):
        # tools/tour/quest_tour.sh writes "size mtime" (stat -L -f '%z %m'); the same stamp means the same OBB.
        folder = self.make_build("20261112_1437")
        obb = os.path.join(folder, "Lunacid_Quest.main.obb")
        st = os.stat(obb)
        self.assertEqual(lunacid_vr.obb_stamp(obb), "%d %d" % (st.st_size, int(st.st_mtime)))

    def test_unchanged_obb_is_not_pushed(self):
        folder = self.make_build("20261112_1437")
        quest = FakeQuest(SAVES)
        quest.files[OBB_DIR + "/.luna_stamp"] = lunacid_vr.obb_stamp(
            os.path.join(folder, "Lunacid_Quest.main.obb")).encode()
        self.install(quest)
        self.assertNotIn("push", [c[0] for c in quest.calls])
        self.assertIn("install", [c[0] for c in quest.calls])

    def test_changed_obb_is_pushed_and_stamped(self):
        folder = self.make_build("20261112_1437")
        quest = FakeQuest(SAVES)
        quest.files[OBB_DIR + "/.luna_stamp"] = b"1 2"
        self.install(quest)
        self.assertEqual(quest.files[OBB_DIR + "/.luna_stamp"].decode(),
                         lunacid_vr.obb_stamp(os.path.join(folder, "Lunacid_Quest.main.obb")))

    def test_short_obb_push_fails_and_is_not_stamped(self):
        self.make_build("20261112_1437")
        quest = FakeQuest(SAVES)
        quest.short_push = True
        with self.assertRaises(lunacid_vr.Problem):
            self.install(quest)
        self.assertNotIn(OBB_DIR + "/.luna_stamp", quest.files)
        self.assertNotIn("install", [c[0] for c in quest.calls])

    def test_saves_missing_after_install_names_the_backup(self):
        self.make_build("20261112_1437")
        quest = FakeQuest(SAVES)
        quest.install_wipes_saves = True
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            self.install(quest)
        self.assertIn(os.path.join("backups", "20261112_2300"), str(ctx.exception))

    def test_apk_signed_by_another_key_is_refused(self):
        self.make_build("20261112_1437")
        quest = FakeQuest(SAVES)
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            self.install(quest, signature_check=lambda apk: "signed by another key")
        self.assertIn("another key", str(ctx.exception))
        self.assertFalse({"push", "install"} & {c[0] for c in quest.calls})


class TestRestore(Base):
    """Put a backup's saves back on the Quest (2026-11-13: before uninstalling to test a new signing key)."""

    def saved(self, stamp="20261112_211011", saves=None):
        quest = FakeQuest(saves or SAVES)
        return lunacid_vr.backup(self.cfg, lunacid_vr.Device(quest), stamp=stamp)

    def test_newest_backup_goes_back_with_sizes_and_md5(self):
        self.saved("20261112_211011", {FILES + "/SAVE_0.MIDNIGHT": b"old"})
        self.saved("20261112_211055")
        quest = FakeQuest({})                               # a fresh install: no saves yet
        lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        self.assertEqual(quest.files[FILES + "/SAVE_0.MIDNIGHT"], SAVES[FILES + "/SAVE_0.MIDNIGHT"])
        self.assertEqual(quest.files[FILES + "/SETTINGS.MIDNIGHT"], b"settings")
        self.assertIn("md5sum", " ".join(quest.adb_words()))

    def test_the_game_is_stopped_before_the_push(self):
        self.saved()
        quest = FakeQuest({})
        lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        kinds = [c[0] if c[0] != "shell" else c[1] for c in quest.calls]
        stop = next(i for i, k in enumerate(kinds) if k.startswith("am force-stop"))
        self.assertLess(stop, kinds.index("push"))

    def test_saves_on_the_quest_are_backed_up_first(self):
        self.saved("20261112_211011")
        newer = {FILES + "/SAVE_0.MIDNIGHT": b"played after the backup"}
        quest = FakeQuest(newer)
        lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), stamp="20261113_100000", say=lambda *a: None)
        with open(os.path.join(self.cfg["work"], "backups", "20261113_100000", "SAVE_0.MIDNIGHT"), "rb") as fh:
            self.assertEqual(fh.read(), b"played after the backup")

    def test_a_backup_with_only_settings_is_not_chosen(self):
        # 2026-11-13: after a fresh install the game's first launch writes a default SETTINGS; restore backs it up
        # first, and that newer folder must not win over the one with the progress.
        self.saved("20261113_081352")
        self.saved("20261113_082118", {FILES + "/SETTINGS.MIDNIGHT": b"defaults"})
        quest = FakeQuest({})
        lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        self.assertEqual(quest.files[FILES + "/SAVE_0.MIDNIGHT"], SAVES[FILES + "/SAVE_0.MIDNIGHT"])

    def test_a_chosen_backup(self):
        first = self.saved("20261112_211011", {FILES + "/SAVE_0.MIDNIGHT": b"first"})
        self.saved("20261112_211055")
        quest = FakeQuest({})
        lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), folder=first, say=lambda *a: None)
        self.assertEqual(quest.files[FILES + "/SAVE_0.MIDNIGHT"], b"first")

    def test_the_game_can_write_its_restored_saves(self):
        # 2026-11-13 on the Quest: pushed files belong to shell (2000) with 644, and the game runs as its own uid
        # outside group ext_data_rw, so it could read the save but not write it again.
        self.saved()
        quest = FakeQuest({})
        lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        for name in ("SAVE_0.MIDNIGHT", "SETTINGS.MIDNIGHT"):
            self.assertEqual(quest.modes.get(FILES + "/" + name), "666")

    def test_not_installed_refuses(self):
        self.saved()
        quest = FakeQuest({})
        quest.installed = False
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        self.assertIn("install", str(ctx.exception))
        self.assertNotIn("push", [c[0] for c in quest.calls])

    def test_game_never_opened_refuses(self):
        self.saved()
        quest = FakeQuest({})
        quest.files_dir = False
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        self.assertIn("open the game once", str(ctx.exception))
        self.assertNotIn("push", [c[0] for c in quest.calls])

    def test_a_damaged_copy_fails(self):
        self.saved()
        quest = FakeQuest({})
        quest.corrupt_push = True
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        self.assertIn("SAVE_0.MIDNIGHT", str(ctx.exception))

    def test_no_backup_is_a_clear_error(self):
        with self.assertRaises(lunacid_vr.Problem):
            lunacid_vr.restore(self.cfg, lunacid_vr.Device(FakeQuest({})), say=lambda *a: None)

    def test_never_uninstalls_or_clears(self):
        self.saved()
        quest = FakeQuest({})
        lunacid_vr.restore(self.cfg, lunacid_vr.Device(quest), say=lambda *a: None)
        words = " ".join(quest.adb_words())
        self.assertNotIn("uninstall", words)
        self.assertNotIn("pm clear", words)


class TestBuild(unittest.TestCase):
    """build wraps tools/build/build.py with the same Python, so its checks (compile errors, scenes, signature) hold."""

    def test_full_and_fast(self):
        script = os.path.join(REPO, "tools", "build", "build.py")
        self.assertEqual(lunacid_vr.build_command(), [sys.executable, script])
        self.assertEqual(lunacid_vr.build_command(fast=True), [sys.executable, script, "--fast"])
        self.assertEqual(lunacid_vr.build_command(skip_passes=True), [sys.executable, script, "--skip-passes"])

    def test_exit_code_passes_through(self):
        seen = []
        rc = lunacid_vr.build(fast=True, run=lambda cmd: seen.append(cmd) or 3)
        self.assertEqual(rc, 3)
        self.assertEqual(seen[0][-1], "--fast")


def adb_with(devices, serials):
    """A run() for pick_serial: `adb devices` lists `devices`; getprop ro.serialno answers from `serials`."""
    def run(args):
        if args == ["devices"]:
            return 0, "List of devices attached\n" + "".join("%s\tdevice\n" % d for d in devices)
        if args[0] == "-s" and args[2:] == ["shell", "getprop ro.serialno"]:
            return 0, serials[args[1]] + "\n"
        return 1, "unexpected %s" % args
    return run


class TestWhichQuest(unittest.TestCase):
    """2026-11-12: the same Quest on USB and on Wi-Fi made adb answer "more than one device" and backup refused."""

    def test_one_device(self):
        self.assertEqual(lunacid_vr.pick_serial(adb_with(["ABC"], {"ABC": "ABC"}), env={}), "ABC")

    def test_same_quest_on_usb_and_wifi_uses_usb(self):
        run = adb_with(["192.0.2.20:5555", "2G0YC0QUEST001"],
                       {"192.0.2.20:5555": "2G0YC0QUEST001", "2G0YC0QUEST001": "2G0YC0QUEST001"})
        self.assertEqual(lunacid_vr.pick_serial(run, env={}), "2G0YC0QUEST001")

    def test_same_quest_on_wifi_twice_is_fine(self):
        run = adb_with(["192.0.2.20:5555", "adb-2G0YC-x._adb-tls-connect._tcp"],
                       {"192.0.2.20:5555": "Q1", "adb-2G0YC-x._adb-tls-connect._tcp": "Q1"})
        self.assertIn(lunacid_vr.pick_serial(run, env={}), ("192.0.2.20:5555", "adb-2G0YC-x._adb-tls-connect._tcp"))

    def test_two_headsets_asks_which(self):
        run = adb_with(["A", "B"], {"A": "A", "B": "B"})
        with self.assertRaises(lunacid_vr.Problem) as ctx:
            lunacid_vr.pick_serial(run, env={})
        self.assertIn("ANDROID_SERIAL", str(ctx.exception))

    def test_android_serial_wins(self):
        self.assertEqual(lunacid_vr.pick_serial(adb_with(["A", "B"], {"A": "A", "B": "B"}),
                                                env={"ANDROID_SERIAL": "B"}), "B")

    def test_no_device(self):
        self.assertIsNone(lunacid_vr.pick_serial(adb_with([], {}), env={}))

    def test_every_call_names_the_device(self):
        quest = FakeQuest(SAVES)
        lunacid_vr.backup({"work": tempfile.mkdtemp()}, lunacid_vr.Device(quest, serial="QUEST1"), stamp="x")
        self.assertTrue(all(c[:2] == ["-s", "QUEST1"] for c in quest.raw_calls), quest.raw_calls[:2])


PROFILE = {"appid": 1745510, "steam_depot": 1745511, "game_versions": [
    {"steam_build": 24780950, "manifest": "9110162109347716163",
     "sha256": {"Managed/Assembly-CSharp.dll": "", "globalgamemanagers": ""}}]}


class TestDoctor(Base):
    def game(self):
        data = os.path.join(self.tmp, "LUNACID_Data")
        os.makedirs(os.path.join(data, "Managed"))
        with open(os.path.join(data, "Managed", "Assembly-CSharp.dll"), "wb") as fh:
            fh.write(b"code")
        with open(os.path.join(data, "globalgamemanagers"), "wb") as fh:
            fh.write(b"ggm")
        return data

    def profile_for(self, data):
        import hashlib
        prof = json.loads(json.dumps(PROFILE))
        for rel in prof["game_versions"][0]["sha256"]:
            with open(os.path.join(data, rel), "rb") as fh:
                prof["game_versions"][0]["sha256"][rel] = hashlib.sha256(fh.read()).hexdigest()
        return prof

    def test_the_profile_has_the_supported_version(self):
        from core import runner
        prof = runner.load_profile()
        self.assertEqual(prof["steam_depot"], 1745511)
        v = prof["game_versions"][0]
        self.assertEqual((v["steam_build"], v["manifest"]), (24780950, "9110162109347716163"))
        self.assertTrue(v["sha256"]["Managed/Assembly-CSharp.dll"].startswith("4395dcc54e9a9825"))
        self.assertTrue(v["sha256"]["globalgamemanagers"].startswith("68136e3969e84fea"))

    def test_known_game_version(self):
        data = self.game()
        status, detail = lunacid_vr.check_game(data, self.profile_for(data))
        self.assertEqual(status, "OK")
        self.assertIn("24780950", detail)

    def test_unknown_game_version_fails(self):
        data = self.game()
        prof = self.profile_for(data)
        with open(os.path.join(data, "globalgamemanagers"), "wb") as fh:
            fh.write(b"updated by Steam")
        status, detail = lunacid_vr.check_game(data, prof)
        self.assertEqual(status, "FAIL")
        self.assertIn("download_depot 1745510 1745511 9110162109347716163", detail)

    def test_missing_game_prints_steamcmd_and_reads_no_credentials(self):
        status, detail = lunacid_vr.check_game(os.path.join(self.tmp, "nowhere"), PROFILE)
        self.assertEqual(status, "FAIL")
        self.assertIn("+@sSteamCmdForcePlatformType windows", detail)
        self.assertIn("+download_depot 1745510 1745511 9110162109347716163", detail)
        self.assertIn("+login <your Steam user>", detail)        # typed by the person, never by the script

    def test_disk_space(self):
        gb = 1024 ** 3
        self.assertEqual(lunacid_vr.check_space(self.tmp, usage=lambda p: (0, 0, 100 * gb))[0], "OK")
        self.assertEqual(lunacid_vr.check_space(self.tmp, usage=lambda p: (0, 0, 20 * gb))[0], "FAIL")

    def test_exfat_and_external_disks_warn(self):
        apfs = "   File System Personality:   APFS\n   Device Location:           Internal\n"
        exfat = ("   File System Personality:   ExFAT\n   Protocol:                  USB\n"
                 "   Device Location:           External\n")
        self.assertEqual(lunacid_vr.parse_diskutil(apfs), ("APFS", False))
        self.assertEqual(lunacid_vr.parse_diskutil(exfat), ("ExFAT", True))
        self.assertEqual(lunacid_vr.disk_status("ExFAT", True)[0], "WARN")
        self.assertEqual(lunacid_vr.disk_status("exfat", False)[0], "WARN")
        self.assertEqual(lunacid_vr.disk_status("APFS", True)[0], "WARN")
        self.assertEqual(lunacid_vr.disk_status("APFS", False)[0], "OK")
        self.assertEqual(lunacid_vr.disk_status("NTFS", False)[0], "OK")

    def test_keystore_and_its_backup(self):
        self.assertEqual(lunacid_vr.check_keystore(self.cfg)[0], "WARN")      # the first build makes it
        key = os.path.join(self.cfg["work"], "keystore")
        os.makedirs(key)
        with open(os.path.join(key, "lunacid-vr.keystore"), "wb") as fh:
            fh.write(b"key")
        with open(os.path.join(key, "keystore.json"), "w") as fh:
            fh.write("{}")
        status, detail = lunacid_vr.check_keystore(self.cfg)
        self.assertEqual(status, "WARN")
        self.assertIn("backup", detail)
        lunacid_vr.backup(self.cfg, lunacid_vr.Device(FakeQuest({})), stamp="x")
        self.assertEqual(lunacid_vr.check_keystore(self.cfg)[0], "OK")

    def test_unity_needs_the_android_module(self):
        unity = os.path.join(self.tmp, "Editor", "Unity.exe")
        os.makedirs(os.path.dirname(unity))
        open(unity, "w").close()
        player = os.path.join(self.tmp, "Editor", "Data", "PlaybackEngines", "AndroidPlayer")
        self.assertEqual(lunacid_vr.check_unity(unity, player)[0], "FAIL")
        os.makedirs(player)
        self.assertEqual(lunacid_vr.check_unity(unity, player)[0], "OK")
        self.assertEqual(lunacid_vr.check_unity(os.path.join(self.tmp, "none"), player)[0], "FAIL")

    def test_any_fail_makes_doctor_fail(self):
        self.assertEqual(lunacid_vr.exit_code([("a", "OK", ""), ("b", "WARN", "")]), 0)
        self.assertEqual(lunacid_vr.exit_code([("a", "OK", ""), ("b", "FAIL", "")]), 1)


if __name__ == "__main__":
    unittest.main()
