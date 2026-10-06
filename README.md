# USUM Shiny Hunting Bot

Automate soft-reset shiny hunts in **Pokémon Ultra Sun and Ultra Moon** on a real Nintendo 3DS. The bot sends controls over Wi-Fi using **Luma3DS Rosalina InputRedirection** and watches the bottom screen through a USB capture board or NTR wireless streaming.

It resets after normal encounters and stops when encounter timing suggests a shiny, leaving you to inspect and catch the Pokémon. The Pi version supports both capture methods.

## Choose your setup

| Setup | Guide | Available features |
| --- | --- | --- |
| Raspberry Pi / Linux with X11 | [Pi installation and user guide](usum_pi_bot/README.md) | Colour-based save-load detection, USB or NTR capture, encounter A tapping, optional screen-transition skipping, retries, viewer recovery and saved incident reports |
| Windows | [Windows installation and user guide](usum_hardware_bot/README.md) | Older gradient-reference save-load detection and basic encounter timing; does not include the Pi recovery or transition-skipping features |
| Emulator | [Original emulator instructions](README.emulator.md) | Damon's original emulator bot |

**The Raspberry Pi version is the most complete hardware version.** Raspberry Pi 4 is the tested setup, using a Loopy New 3DS capture board or NTRViewer-HR. For operation without a monitor, follow the [headless desktop guide](usum_pi_bot/HEADLESS.md); you can control the desktop from a computer, tablet or phone using a VNC client.

## What you need

- A 3DS running Luma3DS with Rosalina InputRedirection.
- Pokémon Ultra Sun or Ultra Moon, saved at a repeatable encounter position.
- On Pi: a Loopy board with **cc3dsfs**, or NTR on the 3DS with **NTRViewer-HR** for wireless capture.
- On Windows: a Loopy board with the **3DS Capture** viewer.
- A computer or Pi on the same local network as the 3DS.

The bot captures an on-screen viewer window, so the bottom-screen window must remain visible, unobstructed and on the desktop.

## How a hunt works

1. Enable InputRedirection on the 3DS HOME Menu, then launch the game.
2. On Pi, select the capture source and keep its bottom-screen viewer visible. Save loading is detected from blue → black → red; no reference screenshot is needed. The older Windows version still requires a gradient reference.
3. Run a single encounter and visually confirm that it is normal once the battle menu appears. This establishes the timing baseline.
4. Enable automatic repeating after checking that the bot reaches and measures the intended encounter correctly.
5. Inspect the Pokémon whenever the bot stops for a suspected shiny or uncertain result.

**Detection is based on timing, not the Pokémon's colour or game memory.** Different encounter animations and cutscenes can affect the result. The first encounter of every run needs manual confirmation, and a new hunt should be tested before leaving it unattended. The bot does not catch Pokémon automatically.

## Help and troubleshooting

Start with the troubleshooting section in your platform's guide. On Pi, the **Recovery reports** tab can export capture-viewer incident logs for diagnosis. Reports are saved locally and are never uploaded automatically.

When [reporting an issue](https://github.com/AIrahpthos/emu-shiny-hunting-bot/issues), include your platform, game and update version, capture viewer, encounter type, and the relevant bot or viewer log. Do not include your save files or private settings unless needed and you intend to share them.

## Credits and licence

Based on [Damon Murdoch's emu-shiny-hunting-bot](https://github.com/damon-murdoch/emu-shiny-hunting-bot). The original emulator source remains at the repository root and in `src/`.

The Pi installer downloads [cc3dsfs](https://github.com/Lorenzooone/cc3dsfs) separately. Wireless capture uses [NTRViewer-HR](https://github.com/xzn/ntrviewer-hr). Controls use the [InputRedirection protocol](https://github.com/TuxSH/InputRedirectionClient-Qt).

Licensed under [MIT](LICENSE). No game files or saves are included.
