# Lunacid VR on Windows

One line does everything: it gets the programs it needs, your copy of the game, builds the game for the Quest and
installs it. It asks only what only you can answer. You do not need to know anything about programming.

## Before you start (10 minutes)

You need:

- A **Windows 10 or 11** computer with about **40 GB free**, plugged in.
- **Lunacid** on your Steam account, and your Steam password and phone (for the Steam Guard code).
- A **Meta Quest 3 or 3S** and its USB-C cable.
- About **2 to 3 hours**, most of it waiting. You can stop and carry on later.

Turn on the Quest's **developer mode** (needed to install games from a computer):

1. On your phone, open the **Meta Horizon** app, tap **Menu**, then **Devices**, and choose your headset.
2. Tap **Headset settings**, then **Developer mode**, and turn it on.
3. If it asks you to create a developer organization, follow its link
   (<https://developer.oculus.com/manage/organizations/create/>), give it any name, accept, and come back.
4. Restart the Quest.

## The one step

1. Press the **Windows key**, type `PowerShell`, and press **Enter**. A dark blue or black window opens.
2. Copy this line, click in that window, paste it with a **right click**, and press **Enter**:

   ```
   irm https://raw.githubusercontent.com/felipevc13/lunacid-vr/main/setup.ps1 | iex
   ```

3. Leave the window open and answer what it asks. That is all.

## What it will ask you

In this order. Each one is shown in the window when it is needed:

1. **Windows asks for permission** a few times, while programs install: choose **Yes**. **Windows Security** may
   also ask whether `adb` (the program that talks to the Quest) may use the network: choose **Allow**.
2. **Unity Hub opens** (Unity is the program that builds the game). Sign in, or make a free account, and choose the
   free **Personal** licence if asked. Then go back to the PowerShell window and press **Enter**.
3. **Your Steam user name** (the one you log in with, not your e-mail). Then **SteamCMD**, Valve's own program,
   asks for your **password** and your **Steam Guard code**. Nothing appears while you type the password: that is
   normal. This project never sees your password.
4. **The build:** about **1 to 2 hours** the first time. Keep the computer plugged in and do not let it sleep.
5. **The Quest:** put the headset on and wait for its home screen. Then, **still wearing it**, connect the cable
   to the computer. A window asks to **Allow USB debugging**: tick **Always allow from this computer** and choose
   **Allow** (look around if you do not see it in front of you). Then press **Enter** on the computer. The order
   matters: the Quest opens that window where the headset is facing the moment the cable goes in, so with the
   headset on a table nobody sees it.
6. If you had saves from an earlier install on this computer, it offers to put them back.

When it says **Done**, the game is in the headset: **Library**, the filter at the top, **Unknown sources**,
**Lunacid VR**.

## Updating

When a new version is out (a fix, a new feature), **paste the same line again**. It gets the new version, builds the
game again only when the change needs it (choosing the quick build, about 25 to 45 minutes, or the full one), and
installs it over the one on your Quest. **Your saves stay.** You decide nothing: just answer what it asks, as the
first time.

## If something goes wrong

- **Run the same line again.** Finished steps are skipped, and it carries on from where it stopped.
- **It says the Quest is waiting for you to allow this computer, but no window shows:** unplug the cable, put the
  headset on, wait for the home screen, and plug the cable back in while wearing it. If it still does not show,
  restart the Quest (hold its power button, Restart) and do the same.
- **It says SteamCMD could not update itself:** close the window. Press the Windows key, type `PowerShell`,
  **right click** it, choose **Run as administrator**, then **Yes**. Paste the same line there.
- **It says to install App Installer:** the Microsoft Store opens on it. Choose **Get** or **Update**, then paste
  the same line again.
- **Anything else:** copy the whole message (select it in the window, then right click) and send it with your
  question.

Prefer to see every piece, or the automatic way fails? [Doing it by hand](BY_HAND_WINDOWS.md).
