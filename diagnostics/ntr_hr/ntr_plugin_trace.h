/* NTR-HR plugin diagnostics, GPL-2.0-only. Included only by main_pm.c.
 * Flush checkpoints before risky operations; never do filesystem I/O while
 * mapRemoteMemoryInLoader has temporarily replaced kernel process state.
 */
#ifndef NTR_PLUGIN_TRACE_H
#define NTR_PLUGIN_TRACE_H

#define NTR_TRACE_MAX_BYTES (2u * 1024u * 1024u)
static Handle ntrTraceFile;
static u64 ntrTraceOffset;
static u32 ntrTraceLaunch;
static u32 ntrTraceSequence;
static int ntrTraceFailed;

static void ntrTraceClose(void) {
    if (ntrTraceFile) FSFILE_Close(ntrTraceFile);
    ntrTraceFile = 0;
}

static void ntrTrace(const char *stage, u32 result, u32 a, u32 b, const char *detail) {
    if (!ntrTraceFile || ntrTraceFailed) return;
    char line[256];
    int length = xsnprintf(line, sizeof(line),
        "NTRPLG/1 launch=%08"PRIx32" seq=%08"PRIx32" stage=%s result=%08"PRIx32
        " a=%08"PRIx32" b=%08"PRIx32" detail=%s\n",
        ntrTraceLaunch, ++ntrTraceSequence, stage, result, a, b, detail ? detail : "-");
    if (length <= 0 || (u32)length >= sizeof(line)) {
        ntrTraceFailed = 1;
        return;
    }
    u32 written = 0;
    Result res = FSFILE_Write(ntrTraceFile, &written, ntrTraceOffset, line, length, FS_WRITE_FLUSH);
    if (res != 0 || written != (u32)length) {
        ntrTraceFailed = 1;
        return;
    }
    ntrTraceOffset += written;
}

static void ntrTraceBegin(Handle process) {
    ntrTraceClose();
    ++ntrTraceLaunch;
    ntrTraceSequence = 0;
    ntrTraceFailed = 0;
    Result res = FSUSER_OpenFile(&ntrTraceFile, sdmcArchive,
        fsMakePath(PATH_ASCII, "/ntr-plugin-trace.log"), FS_OPEN_CREATE | FS_OPEN_WRITE, 0);
    if (res != 0) { ntrTraceFile = 0; return; }
    res = FSFILE_GetSize(ntrTraceFile, &ntrTraceOffset);
    if (res != 0) { ntrTraceClose(); return; }
    /* Rotate only between launches; a single launch's evidence stays together. */
    if (ntrTraceOffset >= NTR_TRACE_MAX_BYTES) {
        res = FSFILE_SetSize(ntrTraceFile, 0);
        if (res != 0) { ntrTraceClose(); return; }
        ntrTraceOffset = 0;
    }
    ntrTrace("begin", 0, process, 0, "ntr-hr-v0.3.8.2-safe-title-v2");
}

static void ntrTraceName(const u16 *name) {
    char detail[65];
    u32 i = 0;
    for (; i < sizeof(detail)-1 && name[i]; ++i)
        detail[i] = name[i] >= 32 && name[i] <= 126 ? (char)name[i] : '?';
    detail[i] = 0;
    ntrTrace("plugin-file", 0, 0, 0, detail);
}

static u32 ntrTraceHash(const void *buffer, u32 size) {
    const u8 *bytes = (const u8 *)buffer;
    u32 value = 2166136261u;
    for (u32 i = 0; i < size; ++i) value = (value ^ bytes[i]) * 16777619u;
    return value;
}
#endif
