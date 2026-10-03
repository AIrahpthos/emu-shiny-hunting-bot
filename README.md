# USUM shiny hunting: emulator and real 3DS hardware

Fork of [Damon Murdoch’s emu-shiny-hunting-bot](https://github.com/damon-murdoch/emu-shiny-hunting-bot), extended to control a real Nintendo 3DS using Rosalina InputRedirection and a USB capture board. Damon’s original emulator source remains at the repository root; its original instructions are in [README.emulator.md](README.emulator.md). The MIT license and original attribution are retained.

## Choose a version

| Version | Folder | Capture source |
| --- | --- | --- |
| Raspberry Pi / Linux X11 | [usum_pi_bot](usum_pi_bot/README.md) | cc3dsfs separate bottom-screen window |
| Windows hardware version | [usum_hardware_bot](usum_hardware_bot/README.md) | Loopy viewer named `3DS Capture - Bottom…` |
| Original emulator bot | Root and `src/` | See original README |

The Pi version contains the latest development: gradient-based save loading, repeated encounter A taps, configurable Ultra Beast cutscene skipping, learned reset timing fallback, capture process restart, and persistent recovery reports. Windows retains the earlier working hardware adaptation; it does not yet have all Pi recovery and Ultra Beast features.

## What the bot does

1. Soft-reset the game using L + R + START.
2. Tap A until a reference image identifies the loaded-save gradient.
3. Trigger the encounter with A and optional forward movement. On Pi, continue tapping A while checking the encounter.
4. Time bottom-screen transitions and compare them with a manually confirmed normal baseline.
5. Stop for a suspected shiny or uncertain result; optionally repeat normal encounters.

It uses visible capture-window pixels rather than reading game memory. Timing is an indication, not proof of shininess: inspect every stopped encounter. The first encounter of each run must be manually confirmed normal. There is no automatic catching or save editing.

## Current status

Developed around Ultra Moon on a New 3DS with a Loopy New 3DS capture board and Raspberry Pi 4, including a headless TigerVNC/Openbox desktop accessed from an iPad. NTR is not required for normal operation; Rosalina InputRedirection supplies the controls.

In the current hardware testing, removing Ultra Moon’s update shortened reset loading and appeared to resolve repeated console crashes. This is one observed configuration, not a general diagnosis or recommendation to remove updates. The viewer supervisor recovers viewer process exits; it cannot reboot a crashed 3DS or detect every frozen capture feed.

Top-screen learned recognition is a future experiment. It is **not implemented** in these versions.

## Validation and credits

Pi: 51 automated tests cover packets, releases/cancellation, timing and skipped transitions, gradient matching, reset statistics, recovery, X11 geometry, archive validation and viewer reports. Windows tests are separate. New encounter configurations still need a single-encounter console test before unattended repeating.

Original source snapshot: `51ae94d15abdb8d873f25270f757cf575871ea4d`.

Capture viewer: [Lorenzooone/cc3dsfs](https://github.com/Lorenzooone/cc3dsfs), downloaded separately by the Pi installer with a pinned release and checksum. Input protocol reference: [TuxSH/InputRedirectionClient-Qt](https://github.com/TuxSH/InputRedirectionClient-Qt). No game files, saves, capture binaries or crash dumps are included.
