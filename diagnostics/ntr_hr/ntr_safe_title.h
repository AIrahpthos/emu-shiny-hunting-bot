/* GPL-2.0-only. PM-specific replacement for raw kernel title lookup.
 * Requires Luma3DS GetProcessInfo extension 0x10001. No unsafe fallback.
 */
#ifndef NTR_SAFE_TITLE_H
#define NTR_SAFE_TITLE_H
static u32 ntrGetProcessTitle(Handle process, u32 tid[2]) {
    s64 title = 0;
    tid[0] = tid[1] = 0;
    u32 result = svcGetProcessInfo(&title, process, 0x10001);
    if (result != 0) return result;
    tid[0] = (u32)(u64)title;
    tid[1] = (u32)((u64)title >> 32);
    return 0;
}
#endif
