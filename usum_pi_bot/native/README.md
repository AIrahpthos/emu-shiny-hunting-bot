# Loopy direct-frame helper

`Build_loopy.sh` builds cc3dsfs 1.3.0.1 at commit `60c9f81259310a8738d20110f3c6104a047fd082`. Its SFML dependency is pinned to `2124d5fe87412ac1cf8e20de282502a75039efcf`; libusb-cmake is pinned to `bea6567b63796ab27c1c33257d230284fb2d8316`.

`prepare_cc3dsfs.py` validates the expected source anchors before making changes. With `SHINY_FRAME_FD` set, the helper bypasses the entire viewer loop. It restricts acquisition to Loopy New 3DS, converts USB frames with upstream routines and sends the bottom image over an inherited private pipe. It does not create or capture a viewer window, render top video, or run audio.

Each record has a 24-byte little-endian header (`<4sIQQ`): magic `SBF1`, payload length 230400, sequence, monotonic receipt nanoseconds. The payload is portrait 240×320 RGB; the Python receiver rotates it 90° counterclockwise to 320×240, matching upstream display rotation.

The bot drains this pipe independently of the UI and keeps only the latest fresh frame. Ordinary stdout/stderr go to an incident log. Closing the bot terminates the helper and releases USB ownership.

The helper is currently Linux-only and specifically supports the Loopy New 3DS board. The native build has been checked on x86-64 Linux; ARM64 compilation and physical capture require a Pi/console test. Source builds retain upstream licensing and do not include firmware or game files beyond the upstream capture dependencies.
