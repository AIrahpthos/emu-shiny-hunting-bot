# USUM Shiny Hunting Bot

Automate soft-reset shiny hunts in Pokémon Ultra Sun and Ultra Moon on a real 3DS. Controls use Rosalina InputRedirection; the Linux bot reads bottom-screen frames directly from a Loopy USB capture board or NTR wireless streaming.

Capture settings, preview and diagnostics are managed inside the bot. Covering or minimising the preview does not interrupt detection. Encounter timing suggests when a Pokémon may be shiny; the bot stops for inspection and does not catch Pokémon automatically.

## Installation guides

- [Linux / Raspberry Pi installation and user guide](usum_pi_bot/README.md)
- [Remote desktop and automatic startup](usum_pi_bot/HEADLESS.md)
- [Older Windows hardware implementation](usum_hardware_bot/README.md)
- [Original emulator instructions](README.emulator.md)

This branch contains the integrated-capture development version. Test a single encounter before enabling repeating. The Windows implementation does not include the integrated capture features.

Based on [Damon Murdoch’s emu-shiny-hunting-bot](https://github.com/damon-murdoch/emu-shiny-hunting-bot). Capture uses cc3dsfs USB acquisition code and the NTR JPEG Compat protocol. Licensed under [MIT](LICENSE).
