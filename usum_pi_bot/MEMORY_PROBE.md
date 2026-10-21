# Read an encounter from USUM memory

This experiment reports an opponent's species number, PID and shiny status. It
does not send buttons, reset the game or change Pokemon data. It is separate from
the hunt loop; valid snapshots are not automatically treated as new encounters.

## First test

1. Finish or stop the current hunt, then close the bot and other NTR viewers.
   The probe uses the same TCP port (8000), so test it as the only NTR client.
2. Install `BootNTRSelector-NTR-Encounter-Reader-v3.cia` through FBI. It replaces
   the diagnostic launcher. Keep the working v2 installer to return to it.
3. Reboot, launch NTR and apply the NFC patch as usual. No extra debugger or
   game-plugin setting is needed. Version 3 retains v2's validated PM title query.
4. Launch USUM and enter an encounter manually. Leave the opponent on screen.
5. Put `encounter_probe.py` alongside the bot's `settings.json`, then run over SSH:

   ```bash
   python3 encounter_probe.py
   ```

   The script uses the saved 3DS IP. Alternatively:

   ```bash
   python3 encounter_probe.py --host YOUR_3DS_IP
   ```

It runs for 15 seconds. A successful result looks like
`Ultra Moon: species #717, PID 12345678, normal, XOR 1234` (illustrative values).
The reported species must match the opponent. A known shiny can provide a direct
positive test. There is no requirement to reset or lose a shiny for this test.

Results and raw snapshots are saved under `out/memory-probe-.../`. Send that
folder's `observations.jsonl` and `.bin` snapshots if the read is invalid or the
species does not match. If the console crashes, also preserve its Luma dump and
SD-root `ntr-plugin-trace.log`. Do not replace the game's patch/version merely
because this historical address did not validate.

## Address and protocol

PKMN-NTR reads the first wild opponent directly at virtual address `0x3254F4AC`
for both US and UM. Its read path does not resolve a pointer chain. This is an
initial address candidate, not a guarantee across every game revision or battle
mode. A game process ID can change on soft reset even when its virtual layout
stays the same. Version 3 discovers the currently running USUM process on each
request with validated Luma title queries; it holds no cached game handle.

NTR-HR v0.3.8.2 removed the old NTR debugger commands, so this reader adds a
bounded endpoint instead of using PKMN-NTR's old debugger client. NTR command 902
accepts guard `0x53484E59` and this single address. It opens only Ultra Sun/Moon,
checks the region is readable and copies 232 bytes to its own buffer. It does not
add a memory-write command or change streaming parameters. Query/copy failures
return an error and no Pokemon bytes. The client validates the reply and checks
the record checksum, sanity, text terminators, species and egg bit before
calculating Gen 7 shiny XOR (<16). It supports encrypted or decoded stored data.

The endpoint uses NTR's existing interprocess-copy helper and Luma's process-query
APIs. Hardware behaviour and the historical address still require confirmation.
The existing screen transition will be the trigger when this reader is integrated
into the hunt loop; this standalone test establishes the address/format first.

### Sources

- [PKMN-NTR wild offsets](https://github.com/drgoku282/PKMN-NTR/blob/master/PKMN-NTR/Helpers/LookupTable.cs)
- [PKHeX PK7 format](https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/PK7.cs)
- [PKHeX encryption format](https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/Util/PokeCrypto.cs)
- [Luma validated title queries](https://github.com/LumaTeam/Luma3DS/blob/master/k11_extension/source/svc/GetProcessInfo.c)
