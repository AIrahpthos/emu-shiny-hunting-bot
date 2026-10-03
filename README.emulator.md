# Emulator Shiny Hunting Bot
## Automating Static Encounter Resets
### Created By Damon Murdoch ([@SirScrubbington](https://github.com/SirScrubbington))

## Description

This is a simple shiny hunting bot that uses a virtual controller in Python and an emulator to automate resetting static encounters in Pokémon games.
The bot detects shiny encounters by measuring the delay between the start of a battle and the availability of the menu. Shiny encounters make this delay longer!

While the bot is reliable, there are some cases where it may get stuck. However, the bot is designed to detect these situations and reset to continue shiny hunting. 
Planned future updates include support for hatching bots and additional games.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Future Changes](#future-changes)
- [Problems / Improvements](#problems--improvements)
- [Changelog](#changelog)
- [Sponsor this Project](#sponsor-this-project)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/damon-murdoch/emu-shiny-hunting-bot.git
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure you have the required emulator installed.
4. Run the script to start the bot:
   ```bash
   python main.py
   ```

## Usage

1. Start the bot by running the script. The bot will search for the emulator window on your desktop.
2. Select from the available bot options:
   - Static Encounter Bot
   - Egg Hatcher (XY, ORAS, SM/USUM) – *Coming Soon!*
3. The bot will take a screenshot of the game window for confirmation before proceeding with shiny hunting.
4. The bot will reset the game automatically upon non-shiny encounters and continue until a shiny is found.

## Future Changes

- Adding support for egg hatching in various Pokémon games.
- Improving shiny detection accuracy.
- Implementing support for more games beyond the Pokémon series.

### Change Table

| Change Description            | Priority |
| ----------------------------- | -------- |
| Add Egg Hatching Bot support   | High     |
| Improve failure recovery logic | Medium   |
| Expand to more games           | Medium   |

## Problems / Improvements

If you have any suggestions or encounter issues, feel free to open an issue [here](../../issues) or reach out to me on Twitter for help reproducing the problem.

## Changelog

### Ver. 0.1.0

- Confirmed static encounter bot works through testing, improved logging

### Ver. 0.0.2

- Added file logging (events.log)
- Random delay after each reset (to negate any potential seeding issues)

### Ver. 0.0.1

- Initial release with Static Encounter Bot functionality for emulators.
- Basic error handling to detect stuck situations and reset the game.

## Sponsor this Project

If you'd like to support this project and future updates, consider donating through PayPal:  
[https://www.paypal.com/paypalme/sirsc](https://www.paypal.com/paypalme/sirsc)

