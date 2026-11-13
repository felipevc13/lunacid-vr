# Lunacid VR on Windows, step by step

This guide assumes you have never used a terminal or installed developer tools. Follow the steps in order. Each
step ends with a way to check that it worked. Do not go to the next step until the check passes.

It takes an afternoon. Most of it is waiting for downloads and for Unity. You need:

- A Windows 10 or 11 computer with about **40 GB free** on the C: drive.
- **Lunacid** on your Steam account.
- A **Meta Quest 3 or 3S** and a USB-C cable that carries data (the one that came with the Quest works).
- A free **Unity** account and a free **Meta developer** account (you make both below).

## 0. The terminal, and one rule

Some steps are commands you type in a **terminal**: a window where you type a line and press **Enter**.

- **To open it:** press the Windows key, type `Terminal` (or `PowerShell`), press Enter.
- **To run a command from this guide:** copy it, click in the terminal, paste with a right click (or Ctrl+V),
  press Enter.
- **The rule:** after you install any program, **close every terminal window and open a new one** (in VS Code:
  close VS Code itself and open it again). A terminal only sees programs that existed when it opened. If a command
  says `is not recognized` (`não é reconhecido`), this is almost always why.
- **VS Code works too:** its terminal (**Terminal → New Terminal**) is the same thing. The rule above applies to
  VS Code as a whole: quit it (**File → Exit**) after each install.
- **Administrator terminal:** one tool, SteamCMD, needs it. Press the Windows key, type `Terminal`, **right click**
  it, **Run as administrator**, and say **Yes** to Windows' question. The window's title starts with
  `Administrador` / `Administrator`. Use it only where this guide says so.

## 1. Install the programs

### Git (downloads this project)

1. Go to <https://git-scm.com/downloads/win> and download **Git for Windows/x64 Setup**.
2. Run it and click **Next** on every screen, keeping the choices it offers, then **Install** and **Finish**.
3. Close and reopen the terminal. **Check:** `git --version` prints `git version 2.…`.

### Python (runs this project's tools)

1. Go to <https://www.python.org/downloads/> and click the yellow **Download Python 3.…** button.
2. Run it. **On the first screen, tick "Add python.exe to PATH"** at the bottom, then click **Install Now**.
3. Close and reopen the terminal. **Check:** `py --version` prints `Python 3.…`.

### Unity 6000.0.85f1 with Android (builds the game for the Quest)

This is the biggest download (about 9 GB). Start it, then install the rest while it downloads.

1. Go to <https://unity.com/download>, download **Unity Hub** and install it.
2. Open Unity Hub and sign in. Make a free account if you have none. If it asks about a licence, choose the free
   **Personal** licence.
3. Open this page in your browser: <https://unity.com/releases/editor/archive>. Find **6000.0.85f1** (Unity 6)
   and click **Install** next to it. It opens Unity Hub.
4. Unity Hub shows a list of modules. Tick **Android Build Support**, and inside it tick **OpenJDK** and
   **Android SDK & NDK Tools**. Click **Install** and accept the licence it shows.
5. **Check:** in Unity Hub, **Installs** lists **6000.0.85f1** with an Android icon.

### .NET 8 SDK (rebuilds the game's shaders)

1. Go to <https://dotnet.microsoft.com/download/dotnet/8.0>.
2. Under **SDK**, in the **Windows** row, click **x64** in the Installers column. Run it and click **Install**.
3. Close and reopen the terminal. **Check:** `dotnet --version` prints `8.…`.

### AssetRipper 2.0.0 (reads your copy of the game)

1. Go to <https://github.com/AssetRipper/AssetRipper/releases/tag/2.0.0>. Under **Assets**, download the file
   whose name ends in **`win_x64.zip`**.
2. In File Explorer, make a folder `C:\AssetRipper` (open the C: drive, right click, **New → Folder**).
3. Right click the downloaded zip, **Extract All…**, choose `C:\AssetRipper`, **Extract**.
4. **Check:** `Test-Path C:\AssetRipper\AssetRipper.GUI.Free.exe` prints `True`. If it prints `False`, the
   files went into a folder inside `C:\AssetRipper`: move them up so `AssetRipper.GUI.Free.exe` sits directly in
   `C:\AssetRipper`.

### SteamCMD (downloads the right version of the game)

SteamCMD is Valve's own download tool. It is not installed like the others: it is a zip you unpack.

1. Download <https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip>.
2. Make a folder `C:\steamcmd` and extract the zip into it (right click, **Extract All…**).
3. **Check:** `Test-Path C:\steamcmd\steamcmd.exe` prints `True`.
4. **Open an administrator terminal** (step 0 says how). On the Windows 11 computer this guide was tested on,
   SteamCMD's first update failed in a normal terminal (`Failed to apply update`, then
   `Fatal Error: Failed to load steam.dll`) and worked in an administrator one.
5. **In the administrator terminal, let SteamCMD update itself, alone, before using it.** The first run downloads
   its own update (30 to 45 MB) and applies it:

   ```
   C:\steamcmd\steamcmd.exe +quit
   ```

   Wait until the prompt (`PS C:\...>`) comes back. **Check:** near the end it says `Update complete` and
   `Loading Steam API...OK`, with no `Fatal Error`. A last line about `CWorkThreadPool … items discarded` is
   normal. If you see `Fatal Error`, see "When something goes wrong" below.
6. **Keep this administrator terminal open** for step 3 (the game download). Use normal terminals for everything
   else.

## 2. Download this project

In a new terminal:

```
cd $HOME\Documents
git clone https://github.com/felipevc13/lunacid-vr.git
cd lunacid-vr
```

**Check:** the last line of the terminal ends with `lunacid-vr>`. From now on, run every command in this folder.
When you open a new terminal, go back to it first with `cd $HOME\Documents\lunacid-vr` (if you cloned it
somewhere else, `cd` to that folder instead; in VS Code, **File → Open Folder…** and choose `lunacid-vr`, and its
terminal opens there).

## 3. Download the game files

The port was made for one version of Lunacid (Steam build 24780950). SteamCMD downloads exactly that version with
your Steam account, even after the game updates. Your normal Steam install is not touched.

Run this **in the administrator terminal** (step 1, SteamCMD) from any folder, with **your Steam user name** in place of `<your Steam user>` (without the `< >`). **The command starts
with `C:\steamcmd\steamcmd.exe`, the full path, not just `steamcmd`**: Windows does not know where SteamCMD is,
so plain `steamcmd` says `is not recognized`.

```
C:\steamcmd\steamcmd.exe +@sSteamCmdForcePlatformType windows +login <your Steam user> +download_depot 1745510 1745511 9110162109347716163 +quit
```

- SteamCMD checks for updates again and prints a few lines. Wait.
- It asks for your **password**. Type it and press Enter. **Nothing appears while you type: that is normal.**
- It asks for your **Steam Guard code** (from the Steam app on your phone, or your email). Type it, press Enter.
- **These tools never see your password.** You type it into SteamCMD, Valve's program.
- It downloads about 740 MB (359 files); the game takes about 1.5 GB on disk.

**Check:** the last lines say `Depot download complete` and show a folder, normally
`C:\steamcmd\steamapps\content\app_1745510\depot_1745511`, with `(manifest 9110162109347716163)`.

**Now close the administrator terminal.** Go back to a normal terminal in the `lunacid-vr` folder.

## 4. Tell the tools where everything is

1. In the `lunacid-vr` folder, run `notepad local.json`. Notepad asks whether to create the file: click **Yes**.
   This is a new file. Do not edit `local.example.json`: it is only an example, and its text is not a real path.
2. Paste this whole text, unchanged if you used the folders of this guide:

   ```
   {
     "work": "C:\\lunacid-work",
     "project": "C:\\lunacid-work\\project\\ExportedProject",
     "game_data": "C:\\steamcmd\\steamapps\\content\\app_1745510\\depot_1745511\\LUNACID_Data",
     "assetripper": "C:\\AssetRipper\\AssetRipper.GUI.Free.exe"
   }
   ```

   In this file every `\` is written twice (`\\`). If SteamCMD showed another folder in step 3, change
   `game_data` to that folder followed by `\\LUNACID_Data`.
3. Save (Ctrl+S) and close Notepad.

**Check:** `py core\config.py` lists the folders, and `game_data` is the one from step 3.

## 5. Check everything

```
py lunacid_vr.py doctor
```

Every line should start with `OK`. `WARN` lines are advice. If a line starts with `FAIL`, read what it says,
fix that, and run `doctor` again. The Unity line needs Unity's download to have finished.

## 6. Make the Unity project (once)

Before this, set the computer **not to sleep while plugged in** (Settings → System → Power), and keep it plugged in.

```
py tools\extract\assetripper.py --out C:\lunacid-work\project
```

About 7 minutes. **Check:** it ends without `error`, and `C:\lunacid-work\project\ExportedProject` exists.

```
py tools\shader_gen\make_shaders.py --work C:\lunacid-work --data C:\steamcmd\steamapps\content\app_1745510\depot_1745511\LUNACID_Data
```

A few minutes. **Check:** the last line says `45 of 45 port shaders made`.

## 7. Build the game for the Quest

```
py lunacid_vr.py build
```

The first build takes **one to two hours**. Leave it alone. **Check:** the last line starts with `RESULT: built`.

## 8. Get the Quest ready (once)

1. **Developer mode:** on your phone, open the **Meta Horizon** app, go to the menu, **Devices**, choose your
   headset, **Headset settings**, **Developer mode**, and turn it on. If it asks you to make a developer
   organization, follow its link (<https://developer.oculus.com/manage/organizations/create/>), make one with any
   name, and come back.
2. Restart the Quest.
3. Connect the Quest to the computer with the USB-C cable and put the headset on. A window asks to **Allow USB
   debugging**: tick **Always allow from this computer** and click **Allow**.

## 9. Install on the Quest

```
py lunacid_vr.py install
```

It backs up your saves, copies the game data (about 600 MB, a few minutes), installs the game and checks the saves.

**In the headset**, the game is in your **Library** under **Unknown sources** (open the list's filter at the top
to find it). The first time, open it once and quit before restoring any saves (next section).

## 10. Already had the port from another computer?

If `install` stops with "the game on the Quest was built on another computer", or you want to bring saves from
another computer, follow "Moving to another computer, or reinstalling" in the README. To uninstall the game
without a terminal: in the headset, **Library**, find Lunacid VR, the **three dots** next to it, **Uninstall**.

## When something goes wrong

- **`is not recognized` / `não é reconhecido`:** close the terminal (or VS Code) and open it again. If it still
  fails, the program in that step did not finish installing: run its installer again.
- **SteamCMD says `Failed to apply update` or `Fatal Error: Failed to load steam.dll`:** its own update did not
  finish. Make sure you are in an **administrator terminal** (its title starts with `Administrador` /
  `Administrator`). Empty SteamCMD's folder except the program, then let it update again:

  ```
  Get-ChildItem C:\steamcmd -Exclude steamcmd.exe | Remove-Item -Recurse -Force
  C:\steamcmd\steamcmd.exe +quit
  ```

  If it still fails, look for a Windows Security notice ("blocked") and send it, with the last lines of
  `Get-Content C:\steamcmd\logs\bootstrap_log.txt -Tail 25`.
- **Anything else:** copy the whole message from the terminal (select it, right click) and send it with your
  question. The `doctor` output helps too.
