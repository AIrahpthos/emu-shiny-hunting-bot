#!/usr/bin/env python3
"""Instrument pinned NTR-HR source, rejecting unexpected or already-patched input."""
from pathlib import Path
import argparse
import hashlib

HERE = Path(__file__).resolve().parent


def instrument(source):
    source = source.replace('\r\n', '\n')
    def change(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError(f'Expected exactly one source anchor: {old[:80]!r}')
        source = source.replace(old, new, 1)

    change('static FS_Archive sdmcArchive;',
           'static FS_Archive sdmcArchive;\n#include "ntr_plugin_trace.h"')
    change('Handle file = rtOpenFile16(plgPath);',
           'ntrTraceName(name);\n\tHandle file = rtOpenFile16(plgPath);')
    change('if (file == 0) {\n\t\treturn;\n\t}',
           'if (file == 0) {\n\t\tntrTrace("file-open-failed", 0xffffffff, 0, 0, "-");\n\t\treturn;\n\t}')
    change('u32 fileSize = rtGetFileSize(file);',
           'u32 fileSize = rtGetFileSize(file);\n\tntrTrace("file-size", 0, fileSize, plgLoader->plgCount, "-");')
    change('s32 ret = plgEnsurePoolSize(plgLoaderEx->memSizeTotal + fileSize, 0);',
           'ntrTrace("reserve-enter", 0, plgLoaderEx->memSizeTotal, fileSize, "-");\n\t'
           's32 ret = plgEnsurePoolSize(plgLoaderEx->memSizeTotal + fileSize, 0);\n\t'
           'ntrTrace("reserve-exit", ret, plgLoaderEx->memSizeTotal, fileSize, "-");')
    change('u32 bytesRead = rtLoadFileToBuffer(file, (void *)addr, fileSize);',
           'ntrTrace("read-enter", 0, addr, fileSize, "-");\n\t'
           'u32 bytesRead = rtLoadFileToBuffer(file, (void *)addr, fileSize);\n\t'
           'ntrTrace("read-exit", bytesRead == fileSize ? 0 : 0xffffffff, bytesRead, fileSize, "-");')
    change('rtCloseFile(file);\n\n\tu32 alignedSize',
           'rtCloseFile(file);\n\tntrTrace("plugin-hash", 0, ntrTraceHash((void *)addr, fileSize), fileSize, "fnv1a32");\n\n\tu32 alignedSize')
    change('if (plgLoaderEx->noPlugins) {\n\t\tplgLoaderEx->memSizeTotal = 0;',
           'if (plgLoaderEx->noPlugins) {\n\t\tntrTrace("plugins-disabled", 0, 0, 0, "-");\n\t\tplgLoaderEx->memSizeTotal = 0;')
    change('plgAddPluginsFromDirectory("game");',
           'ntrTrace("scan-global", 0, 0, 0, "/plugin/game");\n\tplgAddPluginsFromDirectory("game");')
    change('plgAddPluginsFromDirectory(buf);',
           'ntrTrace("scan-title", 0, plgLoader->tid[1], plgLoader->tid[0], buf);\n\tplgAddPluginsFromDirectory(buf);\n\t'
           'ntrTrace("plugins-ready", 0, plgLoader->plgCount, plgLoaderEx->memSizeTotal, "-");')

    operations = [
        ('ret = copyRemoteMemory(CUR_PROCESS_HANDLE, addr, hMenuProcess, addr, size);', 'menu-read', '(u32)addr', 'size'),
        ('ret = copyRemoteMemory(hMenuProcess, addr, CUR_PROCESS_HANDLE, addr, size);', 'menu-write', '(u32)addr', 'size'),
        ('ret = pmAllocLoaderMemPool(hGameProcess, loaderMem);', 'game-allocate', 'hGameProcess', 'plgLoaderEx->memSizeTotal'),
        ('ret = protectRemoteMemory(hGameProcess, plgLoader, plgLoaderEx->memSizeTotal, MEMPERM_READWRITE | MEMPERM_EXECUTE);', 'game-protect', 'hGameProcess', 'plgLoaderEx->memSizeTotal'),
        ('ret = copyRemoteMemory(hGameProcess, plgLoader, CUR_PROCESS_HANDLE, plgLoader, plgLoaderEx->memSizeTotal);', 'game-copy', 'hGameProcess', 'plgLoaderEx->memSizeTotal'),
        ('ret = nsAttachProcess(hGameProcess, PROC_START_ADDR, &cfg, 0, 0);', 'game-attach', 'hGameProcess', 'PROC_START_ADDR'),
    ]
    for statement, stage, a, b in operations:
        change(statement,
               f'ntrTrace("{stage}-enter", 0, {a}, {b}, "-");\n\t{statement}\n\t'
               f'ntrTrace("{stage}-exit", ret, {a}, {b}, "-");')

    change('getProcessTIDByHandle(hGameProcess, tid);',
           'ntrTrace("title-enter", 0, hGameProcess, 0, "-");\n\t'
           'u32 traceTitleResult = getProcessTIDByHandle(hGameProcess, tid);\n\t'
           'ntrTrace("title-exit", traceTitleResult, tid[1], tid[0], "-");')
    change('rpSetGamePid(pid);',
           'ntrTrace("pid-update-enter", 0, pid, 0, "-");\n\t\trpSetGamePid(pid);\n\t\t'
           'ntrTrace("pid-update-exit", 0, pid, 0, "-");')
    change('int needInject =',
           'ntrTrace("options", 0, plgLoaderEx->noPlugins, plgLoaderEx->memSizeTotal, "a=noPlugins,b=pluginBytes");\n\t'
           'ntrTrace("overlays", 0, plgLoaderEx->remotePlayBoost, plgLoaderEx->overlayStats, "a=boost,b=stats");\n\t'
           'ntrTrace("debug-next", 0, cfg.ntrConfig.ex.nsUseDbg, plgLoaderEx->CTRPFCompat, "a=debug,b=CTRPF");\n\tint needInject =')
    change('pmInjectToGame(hProcess);\n\treturn ((svcRunTypeDef)svcRunHook.callCode)(hProcess, startInfo);',
           'ntrTraceBegin(hProcess);\n\t'
           'u32 traceResult = pmInjectToGame(hProcess);\n\t'
           'ntrTrace("inject-result", traceResult, hProcess, 0, "-");\n\t'
           'ntrTrace("run-enter", 0, hProcess, 0, "-");\n\t'
           'u32 runResult = ((svcRunTypeDef)svcRunHook.callCode)(hProcess, startInfo);\n\t'
           'ntrTrace("run-exit", runResult, hProcess, 0, "-");\n\t'
           'ntrTraceClose();\n\treturn runResult;')
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_tree', type=Path)
    args = parser.parse_args()
    target = args.source_tree / 'source/pm/main_pm.c'
    original = target.read_text()
    fixture = (HERE / 'upstream/main_pm.c').read_text()
    if original.replace('\r\n', '\n').rstrip() != fixture.rstrip():
        raise SystemExit('Source differs from pinned NTR-HR v0.3.8.2; refusing to patch.')
    changed = instrument(original)
    target.write_text(changed)
    (args.source_tree / 'include/ntr_plugin_trace.h').write_bytes((HERE / 'ntr_plugin_trace.h').read_bytes())
    print('Applied plugin trace v1; source SHA256:', hashlib.sha256(changed.encode()).hexdigest())


if __name__ == '__main__':
    main()
