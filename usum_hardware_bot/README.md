# Windows real-hardware bot

This is the earlier Windows v0.5 hardware adaptation. For the latest recovery, persistent reports and Ultra Beast transition skipping, use the Pi version. These later features have not been ported to Windows yet.

Install Python 3.12 or 3.13 with the Windows Python launcher and open `Launch.bat`. Its first launch creates the environment and installs dependencies.

Start Rosalina InputRedirection from the 3DS HOME Menu before launching USUM. Enter the 3DS IP and verify the Test controls movement. Keep the Loopy separate bottom-screen window visible and unobstructed; its title must begin `3DS Capture - Bottom`. Close duplicate bottom viewers.

On Screen setup, capture the whole bottom-screen patterned gradient just after the save loads, before Rotom appears. Save at the encounter position. Run with Repeat off first; manually confirm only a normal Pokémon with the actual battle menu visible. Each fresh run establishes a new timing baseline. Suspected shinies and uncertain results stop the bot for inspection.

The bot soft-resets, taps A until the gradient, presses A and optionally moves forward, then times the bottom screen’s dark → change → change sequence. The default shiny margin is 1.1 seconds. This version does not continue encounter A tapping or skip Ultra Beast cutscene transitions.

Logs and screenshots go to `out/`. Settings and references are local and ignored by Git. STOP releases controls; if a network/computer fault leaves a button held, disable InputRedirection on the console.

```powershell
python -m unittest discover -s tests -v
```

Timing alone is not proof of shininess. No automatic catching, save writing or RAM editing is implemented.
