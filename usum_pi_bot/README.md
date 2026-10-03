# Raspberry Pi real-hardware bot

## Requirements and installation

Raspberry Pi 4 is the primary target. ARM64 and ARM32 capture downloads are supported; Pi 3 performance is not established. Use an X11 desktop, a Loopy capture board, a USB data cable and a modified 3DS with Rosalina InputRedirection. The Pi and 3DS must share a local network.

From this directory, as your normal user:

```bash
bash Setup.sh
bash Launch_capture.sh
bash Launch.sh
```

Setup installs Python/system dependencies, downloads pinned cc3dsfs 1.3.0.1, checks its SHA-256 and runs its USB rules installer from the correct directory. Reconnect the capture USB cable afterward. If the board still reports a permission error, check `lsusb`; the Loopy FT600 board used during development reports `0403:601e`.

For the headless iPad workflow, see [HEADLESS.md](HEADLESS.md). Desktop capture requires the windows to remain visible in the virtual desktop even when the VNC client disconnects.

## Screen and controls setup

Start InputRedirection from Rosalina on the 3DS HOME Menu before launching USUM. Enter the console’s IP and use Test controls; verify the D-pad movement yourself because UDP has no connection acknowledgement.

In cc3dsfs, use separate screen windows (S). The bot finds `cc3dsfs_bot…` automatically. Keep that window fully visible and unobstructed, close viewer menus and duplicate bottom viewers, and disable desktop blanking. On Screen setup, capture the whole patterned gradient visible **after loading the save**, before Rotom appears. No region selection is required.

Save at your intended encounter and facing direction. Run with Repeat off first. Confirm the first encounter only once the Pokémon is visibly normal and the actual battle menu has appeared. The baseline is established afresh each run. The default shiny margin is 1.1 seconds above the fastest accepted normal timing; a sufficiently short timing is uncertain.

## Ultra Beast mode

Enable **Ultra Beast mode** and set **Screen changes to skip** to the number of extra cutscene transitions at the selected bottom-screen detection point. The initial dark screen is an anchor and does not count. After skipping N stable changes, the next change starts timing and the following change finishes it. Each transition requires three matching samples. The log shows skipped changes and timing start.

Zero skips preserves ordinary detection. Disabling Ultra Beast mode ignores the saved count. A keeps tapping after forward movement throughout skipped changes and timing. STOP, timeout, capture loss and measurement completion cancel tapping and release controls. Check the count with Repeat off before unattended use.

## Capture recovery and reporting

```bash
bash Capture_supervisor.sh
```

The supervisor launches split capture windows at positions suitable for a 1280×800 desktop, disables audio, reconnects automatically, and restarts an exited viewer after three seconds. It keeps a separate stdout/stderr log and bot-log snapshot for each unexpected exit. An exit of zero is labelled a close/disconnect, not assumed to be a crash. Intentional supervisor shutdowns are excluded.

The Recovery reports tab shows persistent counts and lets you export selected reports to a ZIP in `out/`. Nothing is uploaded automatically. `~/capture-viewer.log` points to the current viewer log. Closing the viewer while the supervisor runs causes it to restart.

To resume an active hunt after viewer loss, enable **Resume after capture crash**. An interrupted encounter may be reset without knowing whether it was shiny. Frozen feeds and 3DS exception screens are not automatically repaired.

## Learned reset fallback

**Retry failed attempts** records confirmed gradient timings and A-tap counts. After at least ten successes it can use conservative learned limits to try an encounter when the gradient was missed. Inferred loads do not train those limits. Three consecutive attempt failures stop the hunt; a normal result clears the failure streak. Retrying an unclassified encounter can discard an unseen shiny, so this option defaults off.

## Existing installation and data

This repository contains the latest complete source, rather than a chain of update ZIPs. To move an existing installation, stop it, install dependencies in the new directory, and copy `settings.json`, `references/` and `out/` from the old directory. Rerun capture setup because executable paths are installation-specific. Reconfigure startup to launch only one installation.

Private settings, captures, logs, save-gradient references and downloaded binaries are ignored by Git. Program updates do not require replacing those files.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

51 tests pass in the development environment. Actual USB capture, console response and encounter timing must be checked on your hardware.
