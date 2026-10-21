/* GPL-2.0-only. Included by ns.c after its packet-send helpers.
 * A bounded read of one USUM opponent slot, not a general debugger.
 */
#ifndef NTR_READ_ENCOUNTER_H
#define NTR_READ_ENCOUNTER_H
#define NTR_ENCOUNTER_COMMAND 902u
#define NTR_ENCOUNTER_MAGIC 0x53484e59u
#define NTR_ENCOUNTER_ADDRESS 0x3254f4acu
#define NTR_ENCOUNTER_SIZE 232u
#define NTR_ENCOUNTER_BAD_REQUEST 0xe1000001u
#define NTR_ENCOUNTER_NO_GAME 0xe1000002u
#define NTR_ENCOUNTER_BAD_REGION 0xe1000003u
static u8 ntrEncounterBuffer[4096] __attribute__((aligned(4096)));

static u32 ntrReadEncounter(u32 *pidOut, u32 tid[2]) {
    u32 pids[128];
    s32 count = 0;
    u32 result = svcGetProcessList(&count, pids, 128);
    if (result != 0) return result;
    if (count < 0 || count > 128) return NTR_ENCOUNTER_NO_GAME;
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
        MemInfo memory = {0};
        PageInfo page = {0};
        result = svcQueryProcessMemory(&memory, &page, process, NTR_ENCOUNTER_ADDRESS);
        if (result == 0 && (!(memory.perm & MEMPERM_READ) ||
            memory.base_addr > NTR_ENCOUNTER_ADDRESS ||
            (u64)memory.base_addr + memory.size < (u64)NTR_ENCOUNTER_ADDRESS + NTR_ENCOUNTER_SIZE))
            result = NTR_ENCOUNTER_BAD_REGION;
        if (result == 0)
            result = copyRemoteMemoryTimeout(CUR_PROCESS_HANDLE, ntrEncounterBuffer,
                process, (void *)NTR_ENCOUNTER_ADDRESS, NTR_ENCOUNTER_SIZE, 1000000000LL);
        svcCloseHandle(process);
        return result;
    }
    return NTR_ENCOUNTER_NO_GAME;
}

static void nsHandleEncounterPacket(void) {
    NS_PACKET *packet = &nsContext->packetBuf;
    u32 pid = 0, tid[2] = {0, 0};
    u32 result = NTR_ENCOUNTER_BAD_REQUEST;
    if (packet->type == 0 && packet->dataLen == 0 &&
        packet->args[0] == NTR_ENCOUNTER_MAGIC &&
        packet->args[1] == NTR_ENCOUNTER_ADDRESS)
        result = ntrReadEncounter(&pid, tid);
    memset(packet->args, 0, sizeof(packet->args));
    packet->args[0] = result;
    packet->args[1] = pid;
    packet->args[2] = tid[0];
    packet->args[3] = tid[1];
    packet->args[4] = NTR_ENCOUNTER_ADDRESS;
    packet->args[5] = NTR_ENCOUNTER_SIZE;
    packet->args[6] = NTR_ENCOUNTER_MAGIC;
    packet->dataLen = result == 0 ? NTR_ENCOUNTER_SIZE : 0;
    if (nsSendPacketHeader() == (int)sizeof(NS_PACKET) && packet->dataLen)
        nsSendPacketData(ntrEncounterBuffer, packet->dataLen);
}
#endif
