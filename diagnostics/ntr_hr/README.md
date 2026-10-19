# NTR-HR plugin-loading diagnostics

Development instrumentation and candidate title-lookup correction for NTR-HR
v0.3.8.2. This is **not a confirmed fix**
for USUM reset crashes. It records the console-side loading path so that another
failure can be investigated with stage information and matching build symbols.
It does not modify the bot, capture receiver, network settings or plugin contents.
Version 2 changes PM title lookup to Luma GetProcessInfo type 0x10001 and skips
NTR injection when that query fails; the original process-launch call still runs. Do not install it over an ongoing hunt.

## What is recorded

The SD card file `/ntr-plugin-trace.log` contains flushed checkpoints for:

- Plugin directory scans and filenames, file sizes, and FNV-1a checksums of the
  loaded bytes (checksums identify repeated files; they are not security hashes).
- Plugin pool reservation, game-memory allocation, permissions, and copying.
- Reading/writing shared HOME Menu metadata, title lookup, streaming game-PID
  notification, game-payload attachment, and the original game-launch call.
- Plugin counts, total bytes, loader/boost/overlay/debug flags and return codes.

Each checkpoint requests `FS_WRITE_FLUSH`. Logging errors disable tracing for
that launch; the launcher continues with its original result. The log is
truncated at the next launch once it reaches 2 MiB. This retains recent evidence
without unlimited log growth. Filenames are sanitised to ASCII and limited to
64 characters. Checkpoints run outside the function that temporarily replaces
kernel process state.

The last `*-enter` without its corresponding `*-exit` narrows the interval where
execution stopped. It does **not** prove the operation caused a crash: power
loss, logging failure and interrupted writes can produce an unfinished trace.
Flushing SD writes and hashing plugin bytes add overhead and may change a race's
timing. A stable diagnostic run alone cannot establish that the bug is fixed.

## Build

The isolated `ntr-plugin-diagnostics` branch has a GitHub Actions workflow that
uses upstream's build-container tag and pins both console source repositories:

- NTR-HR: `cbc8858c43ecda7903baeeb8efa7c433ae6e8ffa` (v0.3.8.2).
- BootNTR: `6ba51e7d1d8664639bc55d3bdc35e78dfa18fffd`.

`build.sh` checks out those commits and their pinned submodules, validates the
unmodified PM source against the included fixture, applies instrumentation, and
uses the upstream build procedure. It creates the regular New 3DS CIA, ELF files,
linker maps, patched source and checksums. The container is pinned by upstream's
version tag, not a content digest; BUILD.txt and toolchain logs preserve the
additional provenance available from this workflow.

The development build has upstream's application title ID, so installing it
replaces that NTR-HR launcher. Keep the stock v0.3.8.2 CIA for restoring it after
diagnostics. All binaries remain hardware-unverified until explicitly tested.
The workflow may need GitHub Actions enabled on the repository.

For a local build, use the upstream NTR-HR build environment and run:

```bash
bash diagnostics/ntr_hr/build.sh /path/to/new-build-directory
```

## Analyse a trace

```bash
python3 diagnostics/ntr_hr/report.py /path/to/ntr-plugin-trace.log
```

Keep the corresponding CIA, `BUILD.txt`, `SHA256SUMS.txt`, ELF/map files and crash
dump together. The ordinary Luma crash dump does not contain the full injected
payload or kernel instruction memory; symbols do not magically restore those
missing bytes. They do allow addresses inside this known build to be mapped.

## Investigation status

The reported failure occurs with standalone and integrated viewers and can be
reproduced on the Loopy-equipped console when NTR streaming is active. A run with
the built-in NFC patch and game plugins disabled stayed up for over four hours.
That supports investigating plugin loading but does not identify a faulty plugin
or prove the loader was the sole cause. Earlier advice incorrectly treated a
loader-enabled setting as proof that a plugin was loaded. The trace establishes
whether any `.plg` file is actually found and read.

Audit of the source found privileged raw handle-table access in title lookup,
temporary changes to kernel process identity during allocation, and several
silent file-loading failures. These are investigation targets, not demonstrated
root causes. Version 1 recorded those behaviours without changing them. Version 2 changes only
the PM title-lookup path, as described below.

The source fixture is from xzn/ntr-hr, derived from cell9's NTR, GPL version 2.
This directory's diagnostic changes are provided under GPL-2.0-only; see LICENSE.

## Version 2: validated PM title lookup

The supplied trace ended at `title-enter` for process handle `03e00043`, with no
`title-exit`. The 519 preceding completed launch callbacks comprised 173 game
launches and 346 system-process launches. No plugin files were recorded. The new
PM dump faults at `FFF8F044` in supervisor mode with prefetch permission fault
status `0xF`; its return address remains `FFF1DDF8`. This localises the observed
stop to the interval containing title lookup, without proving where any earlier
corruption originated.

The upstream helper reads a handle-table entry and two kernel structures through
raw privileged memory operations. Version 2 replaces that call **in the PM launch
hook only** with Luma's GetProcessInfo extension `0x10001`. Luma validates the
process handle and retains a reference while reading the title ID. Failure clears
the title output, records the error and skips NTR injection for that process; it
does not suppress the original process launch. There is no fallback to raw memory
lookup. Other NTR users of the upstream helper remain unchanged.

This requires Luma3DS support for that extension. If title queries fail, streaming
may not receive game-PID updates; repeated nonzero `title-exit` results should be
reported rather than treated as successful validation. This is a candidate repair,
not a demonstrated hardware fix. Logging overhead remains present.

Install `BootNTRSelector-NTR-Safe-Title-v2.cia` through FBI, replacing the diagnostic
v1 launcher, then reboot and launch NTR. Retain the same NFC patch, input
redirection and streaming configuration for comparison. Preserve the next crash
dump and `/ntr-plugin-trace.log` together. Existing log entries are appended; the
begin checkpoint identifies `ntr-hr-v0.3.8.2-safe-title-v2`.

API reference: https://github.com/LumaTeam/Luma3DS/blob/master/k11_extension/source/svc/GetProcessInfo.c
