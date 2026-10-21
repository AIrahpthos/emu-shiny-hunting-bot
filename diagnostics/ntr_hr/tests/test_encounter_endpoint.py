import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class NetworkPatchTests(unittest.TestCase):
    def test_patch_is_guarded(self):
        spec=importlib.util.spec_from_file_location('patcher',ROOT/'apply_patch.py')
        patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
        source=(ROOT/'upstream/ns.c').read_text()
        patched=patcher.instrument_network(source)
        self.assertIn('nsHandleEncounterPacket();',patched)
        with self.assertRaises(ValueError): patcher.instrument_network(patched)


@unittest.skipUnless(shutil.which('gcc'),'Host C compiler unavailable')
class NativeEndpointTests(unittest.TestCase):
    def test_query_errors_handle_cleanup_request_guards_and_exact_read(self):
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
static int closed,copies,sent,mode;
static u32 svcGetProcessList(s32 *count,u32 *pids,s32 capacity) {
 assert(capacity==128);*count=2;pids[0]=1;pids[1]=50;return 0;
}
static u32 svcOpenProcess(Handle *out,u32 pid) {*out=pid;return 0;}
static u32 svcGetProcessInfo(s64 *out,Handle process,u32 type) {
 assert(type==0x10001);*out=process==50?0x00040000001b5100LL:0;
 return mode==1?0xd8e007f7:0;
}
static u32 svcCloseHandle(Handle process) {(void)process;++closed;return 0;}
static u32 svcQueryProcessMemory(MemInfo *memory,PageInfo *page,Handle process,u32 address) {
 (void)page;assert(process==50);assert(address==0x3254f4ac);
 memory->base_addr=0x3254f000;memory->size=mode==3?0x400:0x1000;memory->perm=mode==2?0:1;
 return mode==4?0xd8e007f7:0;
}
static u32 copyRemoteMemoryTimeout(Handle dst,void *buffer,Handle src,void *address,u32 size,s64 timeout) {
 assert(dst==99 && src==50);assert((uintptr_t)address==0x3254f4ac);
 assert(size==232 && timeout==1000000000LL);++copies;
 memset(buffer,0xab,size);return mode==5?1:0;
}
static int nsSendPacketHeader(void) {return sizeof(NS_PACKET);}
static int nsSendPacketData(u8 *buffer,u32 size) {assert(buffer[0]==0xab && size==232);++sent;return size;}
#include "HEADER"
static void request(void) {
 memset(&context,0,sizeof(context));context.packetBuf.args[0]=NTR_ENCOUNTER_MAGIC;
 context.packetBuf.args[1]=NTR_ENCOUNTER_ADDRESS;nsHandleEncounterPacket();
}
int main(void) {
 request();assert(context.packetBuf.args[0]==0 && sent==1 && copies==1 && closed==2);
 assert(context.packetBuf.args[1]==50 && context.packetBuf.dataLen==232);
 for(mode=1;mode<=5;++mode) {
  int before=closed;request();assert(context.packetBuf.args[0]!=0);
  assert(context.packetBuf.dataLen==0 && closed==before+2 && sent==1);
 }
 int before=copies;context.packetBuf.args[0]=0;nsHandleEncounterPacket();
 assert(context.packetBuf.args[0]==NTR_ENCOUNTER_BAD_REQUEST && copies==before);
 return 0;
}
'''.replace('HEADER',str(ROOT/'ntr_read_encounter.h'))
        with tempfile.TemporaryDirectory() as folder:
            c=Path(folder)/'test.c';exe=Path(folder)/'test';c.write_text(source)
            subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(c),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,timeout=5)
