import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


class PatchTests(unittest.TestCase):
    def test_rejects_changed_and_already_instrumented_source(self):
        patcher = module('apply_patch')
        original = (ROOT / 'upstream/main_pm.c').read_text()
        changed = patcher.instrument(original)
        with self.assertRaises(ValueError): patcher.instrument(changed)
        with self.assertRaises(ValueError): patcher.instrument(original.replace('static FS_Archive sdmcArchive;', ''))

    def test_command_patches_only_pinned_source(self):
        with tempfile.TemporaryDirectory() as folder:
            tree = Path(folder)
            (tree / 'source/pm').mkdir(parents=True)
            (tree / 'include').mkdir()
            shutil.copy(ROOT / 'upstream/main_pm.c', tree / 'source/pm/main_pm.c')
            result = subprocess.run(['python3', str(ROOT / 'apply_patch.py'), str(tree)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((tree / 'include/ntr_plugin_trace.h').exists())
            repeated = subprocess.run(['python3', str(ROOT / 'apply_patch.py'), str(tree)], capture_output=True)
            self.assertNotEqual(repeated.returncode, 0)


class ReportTests(unittest.TestCase):
    def record(self, sequence, stage, launch=1, result=0, a=0, b=0, detail='-'):
        return f'NTRPLG/1 launch={launch:08x} seq={sequence:08x} stage={stage} result={result:08x} a={a:08x} b={b:08x} detail={detail}\n'

    def test_records_names_results_and_unfinished_stage_without_claiming_root_cause(self):
        text = self.record(1,'begin') + self.record(2,'plugin-file',detail='network fix.plg')
        text += self.record(3,'game-allocate-enter') + 'NTRPLG/1 launch=0000'
        report = module('report').summarise(text)
        self.assertIn('network fix.plg', report)
        self.assertIn('last checkpoint: game-allocate-enter', report)
        self.assertIn('unreadable/partial lines: 1', report)
        self.assertIn('not proof of a crash', report)

    def test_separates_reboots_with_reused_launch_numbers(self):
        text = self.record(1,'begin') + self.record(2,'run-exit') + self.record(1,'begin')
        launches, malformed = module('report').analyse(text)
        self.assertEqual(len(launches),2)
        self.assertEqual(malformed,0)


@unittest.skipUnless(shutil.which('gcc'), 'Host C compiler unavailable')
class NativeTraceTests(unittest.TestCase):
    def test_safe_title_success_failure_and_no_raw_lookup(self):
        source = r'''
#include <stdint.h>
#include <assert.h>
typedef uint32_t u32, Handle;
typedef uint64_t u64;
typedef int64_t s64;
static u32 reply;
static u32 svcGetProcessInfo(s64 *out, Handle process, u32 type) {
 assert(process == 0x03e00043); assert(type == 0x10001);
 *out = (s64)UINT64_C(0x00040000001b5100);
 return reply;
}
#include "HEADER"
int main(void) {
 u32 tid[2] = {0xdeadbeef,0xdeadbeef};
 assert(ntrGetProcessTitle(0x03e00043,tid)==0);
 assert(tid[0]==0x001b5100 && tid[1]==0x00040000);
 reply=0xd8e007f7;
 assert(ntrGetProcessTitle(0x03e00043,tid)==reply);
 assert(tid[0]==0 && tid[1]==0);
 return 0;
}
'''.replace('HEADER',str(ROOT / 'ntr_safe_title.h'))
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / 'title.c'
            exe = Path(folder) / 'title'
            src.write_text(source)
            subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,timeout=5)
        patched = module('apply_patch').instrument((ROOT / 'upstream/main_pm.c').read_text())
        self.assertNotIn('getProcessTIDByHandle(hGameProcess, tid)',patched)
        self.assertIn('if (traceTitleResult != 0) return traceTitleResult;',patched)
        self.assertIn('((svcRunTypeDef)svcRunHook.callCode)(hProcess, startInfo)',patched)

    def test_durable_records_rotation_and_write_failure(self):
        source = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <inttypes.h>
#include <string.h>
#include <assert.h>
typedef uint32_t u32, Handle;
typedef uint16_t u16;
typedef uint8_t u8;
typedef uint64_t u64;
typedef int Result;
enum { PATH_ASCII=1, FS_OPEN_CREATE=1, FS_OPEN_WRITE=2, FS_WRITE_FLUSH=1 };
static int sdmcArchive, opened, closed, flushes, partial, fail_open, truncated;
static char output[4096];
static size_t used;
static u64 disk_size;
static const char *fsMakePath(int type,const char *path) { (void)type; return path; }
static Result FSUSER_OpenFile(Handle *out,int archive,const char *path,int flags,int attributes) {
 (void)archive;(void)attributes;
 assert(strcmp(path,"/ntr-plugin-trace.log")==0); assert(flags==(FS_OPEN_CREATE|FS_OPEN_WRITE));
 if(fail_open) return -1;
 *out=7; ++opened; return 0;
}
static Result FSFILE_Close(Handle file) { assert(file==7); ++closed; return 0; }
static Result FSFILE_GetSize(Handle file,u64 *size) { assert(file==7); *size=disk_size; return 0; }
static Result FSFILE_SetSize(Handle file,u64 size) { assert(file==7); assert(size==0); disk_size=size; ++truncated; return 0; }
static Result FSFILE_Write(Handle file,u32 *written,u64 offset,const void *buf,u32 size,int flags) {
 assert(file==7); assert(flags==FS_WRITE_FLUSH); assert(offset==disk_size);
 ++flushes; *written=partial?size-1:size; disk_size+=*written;
 assert(used+*written<sizeof(output)); memcpy(output+used,buf,*written); used+=*written; output[used]=0;
 return 0;
}
static size_t xsnprintf(char *buf,size_t size,const char *fmt,...) {
 va_list args;va_start(args,fmt);int length=vsnprintf(buf,size,fmt,args);va_end(args);return length;
}
#include "HEADER"
int main(void) {
 ntrTraceBegin(42);
 u16 name[]={'x','\n',0x4444,'.','p','l','g',0};
 ntrTraceName(name);
 ntrTrace("game-copy-enter",0,42,4096,"-");
 assert(flushes==3); assert(strstr(output,"detail=x??.plg\n"));
 assert(ntrTraceHash("hello",5)==0x4f9f2cab);
 ntrTraceClose(); assert(opened==closed);
 disk_size=NTR_TRACE_MAX_BYTES;
 ntrTraceBegin(43); assert(truncated==1); ntrTraceClose();
 partial=1; int before=flushes;
 ntrTraceBegin(44); ntrTrace("must-not-write",0,0,0,"-");
 assert(flushes==before+1); assert(ntrTraceFailed); ntrTraceClose();
 fail_open=1; before=flushes;
 ntrTraceBegin(45); ntrTrace("must-not-write",0,0,0,"-");
 assert(flushes==before); assert(ntrTraceFile==0);
 return 0;
}
'''.replace('HEADER', str(ROOT / 'ntr_plugin_trace.h'))
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / 'trace_test.c'
            exe = Path(folder) / 'trace_test'
            src.write_text(source)
            subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],check=True,capture_output=True)
            result = subprocess.run([str(exe)],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
