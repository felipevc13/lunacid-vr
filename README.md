# Lunacid VR (Quest 3 / 3S)

A port of [Lunacid](https://store.steampowered.com/app/1745510/) to the Meta Quest, built on your own computer
from **your own copy of the game**. This repository holds only tools and the port's own code: no game files.
Everything game-derived is made locally, from your copy, and stays on your machine.

Works on **macOS** and **Windows**. You need about **40 GB free** and a few hours the first time (most of it
waiting on Unity).

## Install: one line

Before you start: **Lunacid** on your Steam account, a **Quest 3 or 3S** in **developer mode** with its USB-C
cable, about **40 GB free**, and 2 to 3 hours (most of it waiting). The guide for your computer says how to turn on
developer mode and what the line will ask you:
**[Windows](docs/SETUP_WINDOWS.md)** · **[Mac](docs/SETUP_MAC.md)**

**Windows:** press the Windows key, type `PowerShell`, Enter, and paste:

```
irm https://raw.githubusercontent.com/felipevc13/lunacid-vr/main/setup.ps1 | iex
```

**Mac:** press Cmd+Space, type `Terminal`, Return, and paste:

```
curl -fsSL https://raw.githubusercontent.com/felipevc13/lunacid-vr/main/setup.sh | bash
```

It installs what is missing (Git, Python, Unity Hub and Unity 6000.0.85f1 with Android, SteamCMD and the supported
game version, AssetRipper, .NET 8), builds the game and installs it on the Quest. It asks only for your Unity Hub
sign-in, your Steam user name (SteamCMD itself asks for the password: **these tools never see it**), and to plug in
the Quest. Run the same line again at any time: finished steps are skipped.

To do it by hand instead: [Windows](docs/BY_HAND_WINDOWS.md) · [Mac](docs/BY_HAND_MAC.md).

## Updating

When a new version is out (a fix, a new feature), **paste the same line again**. It gets the new version, builds the
game again only when the change needs it (choosing the quick build, about 25 to 45 minutes, or the full one), and
installs it over the one on your Quest. **Your saves stay.** You decide nothing: just answer what it asks, as the
first time.

## For people used to these tools

Inside a clone, `python3 lunacid_vr.py start` is what the line runs (on Windows, `py` for `python3`). The pieces:
`setup` (machine), `build` (makes the Unity project the first time, then the APK and OBB, into
`<work>/builds/<date-time>/`; `--fast` after code-only changes), `install` (backup, OBB only when it changed,
`adb install -r`, saves checked; never uninstalls), `doctor` (checks everything). Machine paths live in
`local.json` (see `local.example.json`); `setup` writes it. Put the work folder on an internal disk: external and
exFAT disks are slow, and a bumped cable mid-build costs the build.

## Controls

![Meta Quest Touch controls for Lunacid VR](docs/controls.svg)

Look around with your head. The left stick moves you where you look.

| Control | Left controller | Right controller |
|---|---|---|
| Stick | Move where you look | Turn |
| Stick click | Next item | Use item |
| Top button | Y: swap weapon | B: sprint, back |
| Bottom button | X: use, talk, open | A: jump, confirm |
| Menu button | Inventory, pause | |
| Trigger (index finger) | Block | Attack, menu click |
| Grip (middle finger) | Spell 1 | Spell 2 |

In menus, point with the right controller and pull its trigger. The settings page has TURN (snap or smooth),
SNAP ANGLE and TURN SPEED. L/R HAND swaps attack and block.

## Keep your signing key

The first build makes a signing key in `<work>/keystore`. Android only updates an installed app with an APK
signed by the same key. Every `backup` and `install` copies the key into the backup, but **also copy
`<work>/keystore` somewhere off this machine.**

Put that folder in `<work>/keystore` on a new computer before its first build, and its builds update the installed
game as usual. Without it, the new computer makes its own key. Then you move your saves by hand once, as the next
section shows.

## Moving to another computer, or reinstalling

`install` stops and shows these steps when the game on the Quest was built on another computer:
**"the game on the Quest was built on another computer (signed by another key)"**. They also work for a clean
reinstall.

1. **Back up the saves:** `python3 lunacid_vr.py backup` (`install` has just made one too). Check the folder it
   names holds your `SAVE_*.MIDNIGHT` files.
2. **Uninstall the game yourself:** in the headset, **Library**, the **three dots** next to Lunacid VR,
   **Uninstall** (or `adb uninstall com.AkumaKira.LunacidVR` if adb is on your PATH). This deletes the game, its
   saves and its game data (OBB) from the Quest. `lunacid_vr.py` never does it for you.
3. **Install:** `python3 lunacid_vr.py install`. The game data is copied again, so this takes a few minutes.
4. **Open the game once on the Quest, then quit.** The game makes its saves folder on the first launch, and
   `restore` needs it.
5. **Restore:** `python3 lunacid_vr.py restore`. It puts back the newest backup holding a game save, makes the files
   writable by the game, and checks each one. To use an older backup, name its folder:
   `python3 lunacid_vr.py restore <work>/backups/<date-time>`.
6. **Check:** load your save in the game and save once.

To bring saves from another computer, copy its backup folder (`<work>/backups/<date-time>/`, the whole folder) into
`<work>/backups/` on this one, then restore. `restore` only copies saves, so any computer can restore onto any
install.

## Commands

| Command | What it does |
|---|---|
| `python3 lunacid_vr.py start` | Everything, from nothing to the game on the Quest; run it again to carry on |
| `python3 lunacid_vr.py setup` | Downloads and installs what a build needs, writes `local.json` |
| `python3 lunacid_vr.py doctor` | Checks Unity and its Android module and licence, adb, the game version, disk space and type, and the signing key |
| `python3 lunacid_vr.py build [--fast]` | Makes the Unity project if there is none, then builds the APK (and the OBB on a full build) |
| `python3 lunacid_vr.py backup` | Copies the Quest's saves and the signing key |
| `python3 lunacid_vr.py install` | Backs up, then installs the newest build. Never uninstalls |
| `python3 lunacid_vr.py restore [folder]` | Puts a backup's saves back on the Quest (the newest backup with saves). Open the game once after installing first |

With two headsets connected, pick one with `ANDROID_SERIAL=<serial>` (from `adb devices`).

## License

MIT (see `LICENSE`), except the patches in `tools/shader_gen/uscs/patches/`, which change USCSandbox and are
GPL-3.0 like it. This repository contains no files from Lunacid: the game belongs to its developer, and these tools
only read the copy you own.
