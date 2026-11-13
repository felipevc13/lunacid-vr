# Lunacid VR on a Mac

One line does everything: it gets the programs it needs, your copy of the game, builds the game for the Quest and
installs it. It asks only what only you can answer. You do not need to know anything about programming.

## Before you start (10 minutes)

You need:

- A **Mac** with about **40 GB free** on its internal disk, plugged in.
- **Lunacid** on your Steam account (it is a Windows game, but the tools only read its files, so a Mac works), and
  your Steam password and phone (for the Steam Guard code).
- A **Meta Quest 3 or 3S** and its USB-C cable.
- About **2 to 3 hours**, most of it waiting. You can stop and carry on later.

Turn on the Quest's **developer mode** (needed to install games from a computer):

1. On your phone, open the **Meta Horizon** app, tap **Menu**, then **Devices**, and choose your headset.
2. Tap **Headset settings**, then **Developer mode**, and turn it on.
3. If it asks you to create a developer organization, follow its link
   (<https://developer.oculus.com/manage/organizations/create/>), give it any name, accept, and come back.
4. Restart the Quest.

## The one step

1. Press **Cmd+Space**, type `Terminal`, and press **Return**. A white or black window opens.
2. Copy this line, click in that window, paste it with **Cmd+V**, and press **Return**:

   ```
   curl -fsSL https://raw.githubusercontent.com/felipevc13/lunacid-vr/main/setup.sh | bash
   ```

3. Leave the window open and answer what it asks. That is all.

## What it will ask you

In this order. Each one is shown in the window when it is needed:

1. **macOS offers to install the command line developer tools** (Apple's, they bring Git and Python): choose
   **Install** and wait. Your Mac password may be asked for installs: that is macOS asking, not this project.
2. **Unity Hub opens** (Unity is the program that builds the game). Sign in, or make a free account, and choose the
   free **Personal** licence if asked. Then go back to Terminal and press **Return**.
3. **Your Steam user name** (the one you log in with, not your e-mail). Then **SteamCMD**, Valve's own program,
   asks for your **password** and your **Steam Guard code**. Nothing appears while you type the password: that is
   normal. This project never sees your password.
4. **The build:** about **1 to 2 hours** the first time. Keep the Mac plugged in.
5. **Connect the Quest** with the cable and put it on. A window asks to **Allow USB debugging**: tick **Always
   allow from this computer** and choose **Allow**. Then press **Return** on the Mac.
6. If you had saves from an earlier install on this Mac, it offers to put them back.

When it says **Done**, the game is in the headset: **Library**, the filter at the top, **Unknown sources**,
**Lunacid VR**.

## If something goes wrong

- **Run the same line again.** Finished steps are skipped, and it carries on from where it stopped.
- **Anything else:** copy the whole message from Terminal and send it with your question.

Prefer to see every piece, or the automatic way fails? [Doing it by hand](BY_HAND_MAC.md).
