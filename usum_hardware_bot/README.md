# Windows user guide

Run basic USUM soft-reset hunts on a real 3DS using Rosalina InputRedirection and the Loopy capture viewer.

This version does not include continuous encounter A tapping, optional screen-transition skipping, automatic capture recovery, or saved viewer incident reports. Use the [Pi version](../usum_pi_bot/README.md) if you need those features.

## Requirements and installation

- Windows with Python 3.12 or 3.13, including the **Python launcher**.
- A 3DS running Luma3DS and Ultra Sun or Ultra Moon.
- A Loopy capture board and its Windows capture viewer.
- Computer and 3DS on the same local network.

Download and extract this repository, open `usum_hardware_bot`, and double-click **Launch.bat**. The first launch creates a Python environment and installs dependencies. Keep any error text if installation fails.

## Set up a hunt

1. From the 3DS HOME Menu, enable Rosalina **InputRedirection**, then launch the game.
2. Open separate screens in the Loopy viewer. Keep the bottom window fully visible and unobstructed; its title must begin `3DS Capture - Bottom`. Close duplicate bottom viewers and disable desktop blanking.
3. Enter the console's IP in the bot and use **Test controls**. Check the D-pad movement on the console yourself; the test cannot confirm the connection automatically.
4. Save at the intended encounter, facing the required direction. Manually reset and load the save.
5. In **Screen setup**, capture the patterned bottom-screen gradient visible **after the save loads, before Rotom appears**. The whole screen is captured; no region selection is needed.
6. Preview the bottom screen. Click the preview if you need to move the timing detection point from its default centre position.
7. Set **Forward hold seconds** for the movement needed to reach the encounter, or `0` if none is needed. Leave automatic repeating off and click **Start**.
8. Once the actual battle menu appears, visually check the Pokémon. Click **Confirm first encounter is normal** only if it is normal. Otherwise press **STOP**.

With repeating off, the test ends without another reset. Once the configuration works, enable automatic repeating and start a new run. Confirm its first normal encounter again; every run establishes a new baseline.

## Detection and stopping

The bot soft-resets with L + R + START, taps A until it recognises the loaded-save gradient, presses A and optionally walks forward, then measures the bottom screen's dark → change → change sequence.

**Shiny extra seconds** defaults to `1.1` seconds above the normal baseline. Normal results can reset automatically; suspected shinies and uncertain results stop for inspection. This measures the interval between two screen changes, not the entire encounter animation.

Timing is an indication, not proof of shininess. Test every new encounter configuration. This version does not keep tapping A during the encounter. The Pi version also has an optional transition-skipping workaround named Ultra Beast mode, but it is not normally needed for Ultra Beast hunts.

Press **STOP** to cancel and release controls. If a network or computer fault leaves a control held, disable InputRedirection on the 3DS. The bot does not catch Pokémon automatically.

## Saved data and updates

Settings are stored in `settings.json`, the loaded-save reference in `references/`, and logs and screenshots in `out/`, all inside `usum_hardware_bot`.

Before updating, stop the bot and back up those files. For a new repository download, copy them into the replacement `usum_hardware_bot` folder, then open **Launch.bat**. Avoid running two copies of the bot.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Launch fails | Install Python 3.12 or 3.13 with the Python launcher. Keep the terminal error text for diagnosis. |
| Bottom window is missing | Check its title prefix, use separate viewer windows, close duplicates, and refresh the window list. |
| Controls do nothing | Check the console IP and local network; enable InputRedirection on HOME before opening the game. |
| Bot does not recognise the loaded save | Recapture the gradient after the save loads, with the bottom viewer unobstructed. |
| Encounter timing is wrong | Check the detection point and test a single encounter. Also check that the capture feed is working correctly. |
| Viewer or 3DS crashes | Stop the hunt and restore the viewer or console manually. This version has no automatic recovery. |

When reporting an issue, include your game/update version, viewer version, encounter settings and relevant `out/` log.

## Development checks

From this directory after the first launch:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```
