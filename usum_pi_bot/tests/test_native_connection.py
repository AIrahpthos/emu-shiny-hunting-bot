"""Exercise the bridge's connection lifecycle without physical USB hardware."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('g++'), 'C++ compiler unavailable')
class NativeConnectionTests(unittest.TestCase):
    def test_success_starts_frame_loop_and_failure_exits_cleanly(self):
        header = pathlib.Path(__file__).resolve().parents[1] / 'native/shiny_headless.hpp'
        stub = r'''
#include <string>
#include <fcntl.h>
#include <unistd.h>
constexpr int CC_POSSIBLE_DEVICES_END=2, CC_LOOPY_NEW_N3DSXL=1;
constexpr int CAPTURE_SCREENS_BOTH=0, CAPTURE_SPEEDS_FULL=0, CAPTURE_READER_VIDEO=0;
struct Wait { void timed_lock() {} };
struct Status {
 bool running=true, connected=false, devices_allowed_scan[2], ac_adapter_connected=false, requested_3d=true;
 int capture_type=0, capture_speed=0, battery_percentage=0, cooldown_curr_in=0;
 std::string detailed_error_text;
 Wait video_wait;
};
struct Buffer { int read=240*320*3, buffer_video_data_type=0; bool is_3d=false, should_be_3d=false; };
struct Buffers {
 Buffer frame;
 Buffer* GetReaderBuffer(int) { return &frame; }
 void ReleaseReaderBuffer(int) {}
};
struct CaptureData { Status status; Buffers data_buffers; };
struct VideoOutputData { struct { unsigned char screen_data[240*320*3]{}; } rgb_video_output_data; };
bool connect_success=true;
int converted_frames=0;
bool connect(bool, CaptureData*, void*, bool*, bool) { return connect_success; }
bool is_big_endian() { return false; }
int get_video_in_size(CaptureData*,bool,bool,int) { return 240*320*3; }
bool convertVideoToOutput(VideoOutputData*,bool,Buffer*,Status* status,bool) {
 ++converted_frames;
 status->running=false; // Finish after one frame rather than an endless USB stream.
 return true;
}
#include "HEADER_PATH"
int main() {
 int fd=open("/dev/null",O_WRONLY);
 if(fd<3) return 10;
 std::string value=std::to_string(fd);
 setenv("SHINY_FRAME_FD",value.c_str(),1);
 CaptureData success;
 if(shiny_headless(&success)!=0 || converted_frames!=1 || !success.status.connected) return 11;
 connect_success=false;
 CaptureData failure;
 if(shiny_headless(&failure)!=3 || failure.status.running || converted_frames!=1) return 12;
 close(fd);
 return 0;
}
'''.replace('HEADER_PATH', str(header))
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / 'bridge_test.cpp'
            executable = pathlib.Path(tmp) / 'bridge_test'
            source.write_text(stub)
            subprocess.run(['g++', '-std=c++17', str(source), '-o', str(executable)], check=True, capture_output=True)
            result = subprocess.run([str(executable)], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
