# Raspberry Pi user guide

This version runs USUM soft-reset hunts on a real 3DS using Rosalina InputRedirection and a USB capture viewer. Raspberry Pi 4 is the primary supported setup. The capture installer supports ARM64 and ARM32; Pi 3 performance has not been established.

## Requirements

- Raspberry Pi OS or a compatible Debian-based system with an **X11 desktop**. The tested setup uses Debian 13 and a Pi 4.
- Loopy New 3DS capture board connected with a USB data cable.
- A 3DS running Luma3DS, with Rosalina InputRedirection available.
- Ultra Sun or Ultra Moon and a save at the encounter you want to hunt.
- Pi and 3DS on the same local network.

For a Pi without a monitor, set up the [headless VNC desktop](HEADLESS.md). You can install dependencies over SSH, but launch the viewer and bot from a terminal **inside the desktop or VNC session**.

## Install

Download and extract the repository, or clone it:

```bash
git clone https://github.com/AIrahpthos/emu-shiny-hunting-bot.git
cd emu-shiny-hunting-bot/usum_pi_bot
bash Setup.sh
```

Setup installs the required dependencies and USB permissions, creates a Python environment, and downloads a checksum-verified cc3dsfs release.

When setup finishes, unplug and reconnect the capture USB cable.

## Open the viewer and bot

From the `usum_pi_bot` directory in your desktop terminal:

```bash
bash Capture_supervisor.sh
```

The supervisor opens separate top and bottom capture windows and restarts the viewer if it exits. Leave this terminal running. In a second desktop terminal, run:

```bash
bash Launch.sh
```

For a viewer without automatic restart, use `bash Launch_capture.sh` instead of the supervisor. Do not run both at once.

Keep the bottom-screen window fully visible and unobstructed. Its title should begin with `cc3dsfs_bot`. Close viewer menus and duplicate bottom-screen windows, and disable desktop blanking. The supervisor uses a layout suited to a 1280×800 desktop.

## Set up your first hunt

### 1. Connect the controls

On the 3DS HOME Menu, open Rosalina and start **InputRedirection**, then launch USUM. Enter the console's IPv4 address in **3DS IP**.

Click **Test controls (D-pad right)** and check that the console responds. This test sends a button press; it cannot confirm a network connection automatically. Return to your intended position afterward.

### 2. Capture the loaded-save reference

Save at the encounter position, facing the correct direction. Manually soft-reset and load the save. In the bot's **Screen setup** tab, click the capture button while the patterned bottom-screen gradient is visible **after the save has loaded, before Rotom appears**.

The whole bottom screen is captured automatically. You do not need to select a small region. Capture this again if you change the viewer layout or it no longer recognises the loaded save reliably.

### 3. Check the detector and movement

On **Hunt**, select the bottom-screen viewer and click **Preview bottom screen**. The timing detector starts at the centre; clicking the preview selects a different detection point. Choose a point that follows the encounter's dark → change → change sequence without triggering on unrelated animation.

Set **Forward hold seconds** to the movement needed to trigger the encounter, or `0` if no forward movement is needed. The bot presses A, moves forward for this duration, then continues tapping A while measuring the encounter.

Leave **Repeat normal encounters automatically**, **Resume after capture crash**, and **Retry failed attempts** off for the first test. Leave **Ultra Beast mode** off as well; it is not needed for ordinary use, including Ultra Beast hunts.

### 4. Run a single-encounter test

Click **Start**. The bot soft-resets, taps A until it recognises the loaded-save gradient, and triggers the encounter.

At the first encounter, wait until the actual battle menu appears. If the Pokémon is visibly normal, click **Confirm first encounter is normal**. If it is shiny or you are unsure, press **STOP** instead. Never confirm a shiny as the normal baseline.

With repeating off, the bot finishes this test without another reset. Check that the measured interval corresponds to the encounter introduction, rather than an earlier cutscene.

### 5. Start repeating

Enable **Repeat normal encounters automatically** and start a new run. Confirm its first normal encounter again; each run establishes a fresh baseline.

Later normal encounters are reset automatically. A suspected shiny or uncertain result stops the hunt for inspection. Use **STOP** at any time to cancel and release controls.

## Hunt settings

| Setting | Purpose |
| --- | --- |
| **Shiny extra seconds** | Additional introduction time above the normal baseline that triggers a suspected-shiny stop. Default: `1.1` seconds. |
| **Forward hold seconds** | How long to walk forward after loading the save. Range: `0`–`5` seconds. |
| **Repeat normal encounters automatically** | Continue resetting after normal results. Leave off when testing a new hunt. |
| **Ultra Beast mode** / **Screen changes to skip** | Optional transition-skipping workaround; leave disabled for ordinary use. |
| **Resume after capture crash** | Wait for a replacement viewer, then retry an interrupted active hunt with its existing baseline. |
| **Retry failed attempts** | Use learned reset timing when the gradient is missed, and retry detection failures. |

The baseline follows the fastest accepted normal interval. The measured interval is **between two bottom-screen changes**, not the entire time from black screen to gaining control. Timing alone does not prove shininess; inspect stopped encounters yourself.

## Ultra Beast mode

**Leave this disabled, including when hunting Ultra Beasts.** It was added to work around apparent extra bottom-screen changes during encounters, which appear to have been caused by a capture issue rather than the encounters themselves.

The option remains available in case it proves useful. When enabled, **Screen changes to skip** ignores the specified number of bottom-screen changes after the initial dark screen, before starting the normal timing check. The initial dark screen does not count. Valid values are `0`–`20`; disabling the mode ignores the saved count.

## Recovery and saved reports

### Capture viewer recovery

The capture supervisor restarts an exited viewer after three seconds. This works independently of whether a hunt is running. To let an active hunt resume after losing the viewer, also enable **Resume after capture crash** in the bot.

The bot releases controls and waits up to two minutes for the bottom-screen window to return. It then retries the attempt. **An interrupted encounter may be reset without knowing whether it was shiny.** A viewer restart does not restart a stopped hunt or bypass its first-normal confirmation.

The supervisor detects process exits, not every frozen feed. It cannot reboot a crashed 3DS or enable InputRedirection after a console reboot.

### Failed-attempt retries

With **Retry failed attempts** enabled, the bot can try an encounter when it appears to have missed the loaded-save gradient. It needs at least ten successfully observed resets before using learned time and A-tap limits.

Three consecutive attempt failures stop the hunt; a confirmed normal encounter clears that streak. This option can also reset an unclassified encounter, so leave it off unless you accept that tradeoff.

### Review and export incidents

The **Recovery reports** tab keeps viewer-interruption counts across bot restarts. Select incidents and click **Save selected reports as ZIP**. With nothing selected, the latest 100 incidents are exported. The ZIP contains viewer output, exit details, and recent bot-log output when available.

Exports go into `out/`. **Mark all reviewed** clears the unreviewed indicator without deleting the logs. A report can represent a disconnect or manual viewer close; it does not always mean a software crash. Intentional supervisor shutdowns are excluded.

## Files and logs

All paths below are relative to `usum_pi_bot`, except those beginning with `~/`.

| Location | Contents |
| --- | --- |
| `settings.json` | Saved connection and hunt settings |
| `references/` | Loaded-save reference image |
| `out/` | Bot logs, encounter screenshots, reset history and exported reports |
| `out/capture-incidents/` | Individual viewer-run logs and incident records |
| `~/capture-viewer.log` | Link to the current supervised viewer log |
| `~/capture-supervisor.log` | Supervisor output when configured through Openbox autostart |

“Observed reset #…” counts successful gradient observations for the current console/reference profile. It is not a count of confirmed normal encounters. Learned limits use only the latest 100 observations, while the observation counter continues increasing.

## Start automatically at boot

Follow [HEADLESS.md](HEADLESS.md) to start the desktop, capture supervisor and bot automatically. The bot window opens at startup; starting a hunt and confirming the first normal encounter remain manual steps.

## Update an existing installation

Stop the hunt and close the bot and capture supervisor before updating. Back up `settings.json`, `references/`, and `out/`.

For a Git clone, run `git pull --ff-only` from the repository directory. For a downloaded ZIP, extract the new repository and copy those saved files into its `usum_pi_bot` directory. Run `bash Setup.sh` in the updated installation before launching it again.

If the installation path changed, update desktop startup entries to point to the new directory and remove old entries. Keep only one bot and one capture supervisor running.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Bot says it needs X11 or a desktop | Launch from a desktop/VNC terminal. On Raspberry Pi OS, switch to X11 using the option shown by `Launch.sh`, then reboot. |
| Capture viewer cannot find the device | Check the USB data cable, reconnect after setup, and run `lsusb`. The tested Loopy FT600 board reports `0403:601e`. For a permission error, rerun setup and reconnect. |
| No bottom-screen window found | Use separate screens in cc3dsfs (`S`), check for a `cc3dsfs_bot` window, then click **Refresh windows**. |
| Capture stops because the window is covered | Move other windows away, close viewer menus, and keep the entire bottom window on-screen. |
| Controls do nothing | Check the 3DS IP and local network, and enable InputRedirection from HOME before launching the game. Verify the test press visually. |
| Bot keeps tapping A after loading | Recapture the correct gradient after the save loads. Check that the viewer is displaying live, unobstructed video. |
| Detector starts too early | Check the live capture feed and detection point, then test one encounter. Ultra Beast mode is an optional workaround, not a required hunt setting. |
| Viewer returns but the hunt stays stopped | Viewer restart and hunt resumption are separate. Check **Resume after capture crash** and the bot log. |
| 3DS shows an exception or returns to HOME | Stop the bot and inspect the console. Capture recovery cannot repair a console crash. Save the 3DS crash dump if available. |

When asking for help, include the relevant log and your OS, game/update version, viewer version and encounter configuration. Use **Recovery reports** for capture-viewer interruptions.

## Development checks

From this directory after setup:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Automated tests do not replace testing USB capture, controls and encounter timing on your hardware.
