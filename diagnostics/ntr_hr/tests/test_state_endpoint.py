import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('gcc'),'Host C compiler unavailable')
class StateEndpointTests(unittest.TestCase):
    def test_fixed_addresses_guards_and_process_cleanup(self):
        source=r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
typedef uint8_t u8; typedef uint32_t u32,Handle; typedef uint64_t u64;
typedef int32_t s32; typedef int64_t s64;
typedef struct {u32 base_addr,size,perm,state;} MemInfo;
typedef struct {u32 flags;} PageInfo;
typedef struct {u32 magic,seq,type,cmd,args[16],dataLen;} NS_PACKET;
static struct {NS_PACKET packetBuf;} context,*nsContext=&context;
enum {MEMPERM_READ=1,CUR_PROCESS_HANDLE=99};
static int closed,copies,sent,bad;
static u32 svcGetProcessList(s32 *count,u32 *pids,s32 capacity) {
 assert(capacity==128);*count=1;pids[0]=50;return 0;
}
static u32 svcOpenProcess(Handle *out,u32 pid) {*out=pid;return 0;}
static u32 svcGetProcessInfo(s64 *out,Handle process,u32 type) {
 assert(type==0x10001 && process==50);*out=0x00040000001b5100LL;return 0;
}
static u32 svcCloseHandle(Handle process) {assert(process==50);++closed;return 0;}
static u32 svcQueryProcessMemory(MemInfo *mem,PageInfo *page,Handle process,u32 address) {
 (void)page;assert(process==50);
 assert(address==0x67107c || address==0x6a668c || address==0x6a60e8);
 mem->base_addr=address;mem->size=8;mem->perm=bad && address==0x6a668c?0:MEMPERM_READ;return 0;
}
static u32 copyRemoteMemoryTimeout(Handle dst,void *buffer,Handle src,void *address,u32 size,s64 timeout) {
 assert(dst==99 && src==50 && timeout==1000000000LL);
 u32 base=(u32)(uintptr_t)address;
 assert(size==(base==0x6a60e8?8:4));
 memset(buffer,0,size);
 u32 value=base==0x6a60e8?0x6a60ea:base;
 memcpy((u8*)buffer+(base==0x6a60e8?2:0),&value,4);++copies;return 0;
}
static int nsSendPacketHeader(void) {return sizeof(NS_PACKET);}
static int nsSendPacketData(u8 *buffer,u32 size) {
 assert(size==24);
 u32 *words=(u32*)buffer;
 assert(words[0]==0 && words[1]==0x67107c);
 assert(words[2]==(bad?0xe1000003u:0));
 assert(words[3]==(bad?0:0x6a668c));
 assert(words[4]==0 && words[5]==0x6a60ea);
 ++sent;return size;
}
#include "HEADER"
int main(void) {
 memset(&context,0,sizeof(context));
 context.packetBuf.args[0]=NTR_STATE_GUARD^1;
 context.packetBuf.args[1]=NTR_STATE_SCHEMA;
 nsHandleStatePacket();
 assert(context.packetBuf.args[0]==NTR_STATE_BAD_REQUEST && copies==0 && closed==0);
 context.packetBuf.args[0]=NTR_STATE_GUARD;
 context.packetBuf.args[1]=NTR_STATE_SCHEMA;
 nsHandleStatePacket();
 assert(context.packetBuf.args[0]==0 && context.packetBuf.args[1]==50);
 assert(context.packetBuf.dataLen==24 && copies==3 && closed==1 && sent==1);
 bad=1;context.packetBuf.args[0]=NTR_STATE_GUARD;
 context.packetBuf.args[1]=NTR_STATE_SCHEMA;
 context.packetBuf.dataLen=0;
 nsHandleStatePacket();
 assert(context.packetBuf.args[0]==0 && copies==5 && closed==2 && sent==2);
 return 0;
}
'''.replace('HEADER',str(ROOT/'ntr_read_state.h'))
        with tempfile.TemporaryDirectory() as folder:
            source_file=Path(folder)/'state.c';exe=Path(folder)/'state'
            source_file.write_text(source)
            compiled=subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(source_file),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            subprocess.run([str(exe)],check=True,timeout=5)
