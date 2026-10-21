/* GPL-2.0-only. Read three fixed USUM state candidates for diagnostics.
 * This endpoint accepts no caller-supplied address or length and never writes game memory.
 */
#ifndef NTR_READ_STATE_H
#define NTR_READ_STATE_H
#define NTR_STATE_COMMAND 903u
#define NTR_STATE_GUARD 0x53544154u
#define NTR_STATE_SCHEMA 1u
#define NTR_STATE_BAD_REQUEST 0xe1000001u
#define NTR_STATE_NO_GAME 0xe1000002u
#define NTR_STATE_BAD_REGION 0xe1000003u
static const u32 ntrStateAddresses[3] = {0x67107cu, 0x6a668cu, 0x6a60eau};
/* Each field is (read result, raw 32-bit value); failed reads have value 0. */
static u32 ntrStateValues[6];
static u8 ntrStateScratch[4096] __attribute__((aligned(4096)));

static u32 ntrReadStates(u32 *pidOut, u32 tid[2]) {
    u32 pids[128];
    s32 count = 0;
    u32 result = svcGetProcessList(&count, pids, 128);
    if (result != 0) return result;
    if (count < 0 || count > 128) return NTR_STATE_NO_GAME;
    for (s32 i = 0; i < count; ++i) {
        Handle process = 0;
        if (svcOpenProcess(&process, pids[i]) != 0) continue;
        s64 title = 0;
        result = svcGetProcessInfo(&title, process, 0x10001);
        u64 id = (u64)title;
        if (result != 0 || (id != 0x00040000001b5000ULL && id != 0x00040000001b5100ULL)) {
            svcCloseHandle(process);
            continue;
        }
        *pidOut = pids[i];
        tid[0] = (u32)id;
        tid[1] = (u32)(id >> 32);
        for (u32 field = 0; field < 3; ++field) {
            u32 address = ntrStateAddresses[field];
            MemInfo memory = {0};
            PageInfo page = {0};
            result = svcQueryProcessMemory(&memory, &page, process, address);
            if (result == 0 && (!(memory.perm & MEMPERM_READ) ||
                memory.base_addr > address ||
                (u64)memory.base_addr + memory.size < (u64)address + 4u))
                result = NTR_STATE_BAD_REGION;
            if (result == 0)
                result = copyRemoteMemoryTimeout(CUR_PROCESS_HANDLE, ntrStateScratch,
                    process, (void *)(unsigned long)address, 4u, 1000000000LL);
            ntrStateValues[2u * field] = result;
            ntrStateValues[2u * field + 1u] = 0;
            if (result == 0) memcpy(&ntrStateValues[2u * field + 1u], ntrStateScratch, 4u);
        }
        svcCloseHandle(process);
        return 0;
    }
    return NTR_STATE_NO_GAME;
}

static void nsHandleStatePacket(void) {
    NS_PACKET *packet = &nsContext->packetBuf;
    u32 pid = 0, tid[2] = {0, 0};
    u32 result = NTR_STATE_BAD_REQUEST;
    if (packet->type == 0 && packet->dataLen == 0 &&
        packet->args[0] == NTR_STATE_GUARD && packet->args[1] == NTR_STATE_SCHEMA)
        result = ntrReadStates(&pid, tid);
    memset(packet->args, 0, sizeof(packet->args));
    packet->args[0] = result;
    packet->args[1] = pid;
    packet->args[2] = tid[0];
    packet->args[3] = tid[1];
    packet->args[4] = NTR_STATE_SCHEMA;
    packet->args[5] = sizeof(ntrStateValues);
    packet->args[6] = NTR_STATE_GUARD;
    packet->dataLen = result == 0 ? sizeof(ntrStateValues) : 0;
    if (nsSendPacketHeader() == (int)sizeof(NS_PACKET) && packet->dataLen)
        nsSendPacketData((u8 *)ntrStateValues, packet->dataLen);
}
#endif
