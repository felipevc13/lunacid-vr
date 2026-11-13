# Lunacid VR on a Mac, step by step

This guide assumes you have never used a terminal or installed developer tools. Follow the steps in order. Each
step ends with a way to check that it worked. Do not go to the next step until the check passes.

It takes an afternoon. Most of it is waiting for downloads and for Unity. You need:

- A Mac with about **40 GB free** on its internal disk.
- **Lunacid** on your Steam account. It is a Windows game, but the tools only read its files, so a Mac works.
- A **Meta Quest 3 or 3S** and a USB-C cable that carries data (the one that came with the Quest works).
- A free **Unity** account and a free **Meta developer** account (you make both below).

## 0. The terminal, and one rule

Some steps are commands you type in **Terminal**: a window where you type a line and press **Return**.

- **To open it:** press Cmd+Space, type `Terminal`, press Return.
- **To run a command from this guide:** copy it, click in Terminal, paste with Cmd+V, press Return.
- **The rule:** after you install any program, **quit Terminal (Cmd+Q) and open it again**. A terminal only sees
  programs that existed when it opened. If a command says `command not found`, this is almost always why.

**Which Mac do you have?** Apple menu → **About This Mac**. "Chip: Apple M…" means **Apple Silicon** (arm64);
"Processor: Intel…" means **Intel** (x64). Two downloads below depend on it.

## 1. Install the programs

### Git (downloads this project)

1. In Terminal, run `git --version`.
2. If macOS offers to install the **command line developer tools**, click **Install** and wait for it to finish.
3. **Check:** `git --version` prints `git version …`.

### Python (runs this project's tools)

1. Go to <https://www.python.org/downloads/> and click the yellow **Download Python 3.…** button.
2. Open the downloaded file and click **Continue** / **Install** until it finishes.
3. Quit and reopen Terminal. **Check:** `python3 --version` prints `Python 3.…`.

### Unity 6000.0.85f1 with Android (builds the game for the Quest)

This is the biggest download (about 9 GB). Start it, then install the rest while it downloads.

1. Go to <https://unity.com/download>, download **Unity Hub** and install it (drag it to Applications).
2. Open Unity Hub and sign in. Make a free account if you have none. If it asks about a licence, choose the free
   **Personal** licence.
3. Open this page in your browser: <https://unity.com/releases/editor/archive>. Find **6000.0.85f1** (Unity 6)
   and click **Install** next to it. It opens Unity Hub.
4. Unity Hub shows a list of modules. Tick **Android Build Support**, and inside it tick **OpenJDK** and
   **Android SDK & NDK Tools**. Click **Install** and accept the licence it shows.
5. **Check:** in Unity Hub, **Installs** lists **6000.0.85f1** with an Android icon.

### .NET 8 SDK (rebuilds the game's shaders)

1. Go to <https://dotnet.microsoft.com/download/dotnet/8.0>.
2. Under **SDK**, in the **macOS** row, click **Arm64** (Apple Silicon) or **x64** (Intel). Open the file and
   install it.
3. Quit and reopen Terminal. **Check:** `dotnet --version` prints `8.…`.

### AssetRipper 2.0.0 (reads your copy of the game)

1. Go to <https://github.com/AssetRipper/AssetRipper/releases/tag/2.0.0>. Under **Assets**, download the file
   whose name ends in **`mac_arm64.zip`** (Apple Silicon) or **`mac_x64.zip`** (Intel).
2. Make a folder called `AssetRipper` in your home folder (Finder → Go → Home, then File → New Folder) and unzip
   the download into it (double click the zip, then move the files in).
3. macOS blocks programs downloaded from the internet that it does not know. Let this one run:
   `xattr -dr com.apple.quarantine ~/AssetRipper`
4. **Check:** `ls ~/AssetRipper/AssetRipper.GUI.Free` prints the path back (not "No such file").

### SteamCMD (downloads the right version of the game)

SteamCMD is Valve's own download tool. It is not installed like the others: you unpack it. In Terminal:

```
mkdir -p ~/steamcmd && cd ~/steamcmd && curl -sqL https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz | tar zxvf -
```

**Check:** `ls ~/steamcmd/steamcmd.sh` prints the path back.

## 2. Download this project

```
cd ~
git clone https://github.com/felipevc13/lunacid-vr.git
cd lunacid-vr
```

**Check:** the prompt ends with `lunacid-vr %`. From now on, run every command in this folder. When you open a new
Terminal, go back to it first with `cd ~/lunacid-vr`.

## 3. Download the game files

The port was made for one version of Lunacid (Steam build 24780950). SteamCMD downloads exactly that version with
your Steam account, even after the game updates.

Run this, with **your Steam user name** in place of `<your Steam user>` (without the `< >`):

```
~/steamcmd/steamcmd.sh +@sSteamCmdForcePlatformType windows +login <your Steam user> +download_depot 1745510 1745511 9110162109347716163 +quit
```

- The first time, SteamCMD updates itself and prints many lines. Wait.
- It asks for your **password**. Type it and press Return. **Nothing appears while you type: that is normal.**
- It asks for your **Steam Guard code** (from the Steam app on your phone, or your email). Type it, press Return.
- **These tools never see your password.** You type it into SteamCMD, Valve's program.
- It downloads about 1.5 GB.

**Check:** the last lines say `Depot download complete` and show a folder. **Copy that folder's path**: you need
it in the next step.

## 4. Tell the tools where everything is

1. Run `nano local.json`. A text editor opens inside Terminal. (Do not use TextEdit: it changes the quotes and
   breaks the file.)
2. Paste this text with Cmd+V, and replace `<the folder from step 3>` with the folder SteamCMD showed:

   ```
   {
     "work": "~/lunacid-work",
     "project": "~/lunacid-work/project/ExportedProject",
     "game_data": "<the folder from step 3>/LUNACID_Data",
     "assetripper": "~/AssetRipper/AssetRipper.GUI.Free"
   }
   ```

3. Save and leave: press **Ctrl+O**, **Return**, then **Ctrl+X**.

**Check:** `python3 core/config.py` lists the folders, and `game_data` ends in `LUNACID_Data`.

## 5. Check everything

```
python3 lunacid_vr.py doctor
```

Every line should start with `OK`. `WARN` lines are advice. If a line starts with `FAIL`, read what it says,
fix that, and run `doctor` again. The Unity line needs Unity's download to have finished.

## 6. Make the Unity project (once)

Keep the Mac plugged in. `caffeinate -i` in front of a command keeps the Mac awake while it runs.

```
caffeinate -i python3 tools/extract/assetripper.py --out ~/lunacid-work/project
```

About 7 minutes. **Check:** it ends without `error`, and `ls ~/lunacid-work/project/ExportedProject` lists files.

```
caffeinate -i python3 tools/shader_gen/make_shaders.py --work ~/lunacid-work --data "<the folder from step 3>/LUNACID_Data"
```

A few minutes. **Check:** the last line says `45 of 45 port shaders made`.

## 7. Build the game for the Quest

```
caffeinate -i python3 lunacid_vr.py build
```

The first build takes **one to two hours**. Leave it alone. **Check:** the last line starts with `RESULT: built`.

## 8. Get the Quest ready (once)

1. **Developer mode:** on your phone, open the **Meta Horizon** app, go to the menu, **Devices**, choose your
   headset, **Headset settings**, **Developer mode**, and turn it on. If it asks you to make a developer
   organization, follow its link (<https://developer.oculus.com/manage/organizations/create/>), make one with any
   name, and come back.
2. Restart the Quest.
3. Connect the Quest to the Mac with the USB-C cable and put the headset on. A window asks to **Allow USB
   debugging**: tick **Always allow from this computer** and click **Allow**.

## 9. Install on the Quest

```
python3 lunacid_vr.py install
```

It backs up your saves, copies the game data (about 600 MB, a few minutes), installs the game and checks the saves.

**In the headset**, the game is in your **Library** under **Unknown sources** (open the list's filter at the top
to find it). The first time, open it once and quit before restoring any saves (next section).

## 10. Already had the port from another computer?

If `install` stops with "the game on the Quest was built on another computer", or you want to bring saves from
another computer, follow "Moving to another computer, or reinstalling" in the README. To uninstall the game
without a terminal: in the headset, **Library**, find Lunacid VR, the **three dots** next to it, **Uninstall**.

## When something goes wrong

- **`command not found`:** quit Terminal and open it again. If it still fails, the program in that step did not
  finish installing: run its installer again.
- **Anything else:** copy the whole message from Terminal and send it with your question. The `doctor` output
  helps too.
