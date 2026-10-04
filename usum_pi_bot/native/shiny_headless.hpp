// Direct RGB frame bridge for cc3dsfs 1.3.0.1, Loopy New 3DS only.
// Upstream capture/conversion code remains licensed under MIT.
#include <unistd.h>
#include <cerrno>
#include <cstdlib>
#include <cstdio>
#include <chrono>
#include <cstdint>
#include <cstring>

static bool shiny_write_all(int fd, const void* buffer, size_t count) {
    auto data = static_cast<const unsigned char*>(buffer);
    while (count) {
        ssize_t wrote = write(fd, data, count);
        if (wrote < 0 && errno == EINTR) continue;
        if (wrote <= 0) return false;
        data += wrote; count -= wrote;
    }
    return true;
}

static void shiny_little_endian(unsigned char* dst, uint64_t value, int bytes) {
    for (int i = 0; i < bytes; ++i) dst[i] = (value >> (i * 8)) & 255;
}

static int shiny_headless(CaptureData* capture_data) {
    const char* raw_fd = std::getenv("SHINY_FRAME_FD");
    int fd = raw_fd ? std::atoi(raw_fd) : -1;
    if (fd < 3) { capture_data->status.running = false; return 2; }
    bool force_disables[CC_POSSIBLE_DEVICES_END];
    for (int i = 0; i < CC_POSSIBLE_DEVICES_END; ++i) {
        force_disables[i] = i != CC_LOOPY_NEW_N3DSXL;
        capture_data->status.devices_allowed_scan[i] = !force_disables[i];
    }
    capture_data->status.capture_type = CAPTURE_SCREENS_BOTH;
    capture_data->status.capture_speed = CAPTURE_SPEEDS_FULL;
    capture_data->status.battery_percentage = 100;
    capture_data->status.ac_adapter_connected = true;
    capture_data->status.requested_3d = false;
    if (!connect(true, capture_data, nullptr, force_disables, true)) {
        std::fprintf(stderr, "Loopy connection failed: %s\n", capture_data->status.detailed_error_text.c_str());
        capture_data->status.running = false; return 3;
    }
    auto output = new VideoOutputData;
    uint64_t sequence = 0;
    const bool big_endian = is_big_endian();
    int result = 0;
    while (capture_data->status.running && capture_data->status.connected) {
        capture_data->status.video_wait.timed_lock();
        auto data = capture_data->data_buffers.GetReaderBuffer(CAPTURE_READER_VIDEO);
        if (!data) continue;
        bool valid = data->read >= get_video_in_size(capture_data, data->is_3d, data->should_be_3d, data->buffer_video_data_type)
            && !capture_data->status.cooldown_curr_in && capture_data->status.connected;
        bool converted = valid && convertVideoToOutput(output, big_endian, data, &capture_data->status, false);
        capture_data->data_buffers.ReleaseReaderBuffer(CAPTURE_READER_VIDEO);
        if (!converted) continue;
        // Loopy conversion places the bottom screen first, in 240×320 RGB order.
        unsigned char header[24] = {'S','B','F','1'};
        shiny_little_endian(header + 4, 240 * 320 * 3, 4);
        shiny_little_endian(header + 8, ++sequence, 8);
        auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
        shiny_little_endian(header + 16, static_cast<uint64_t>(now), 8);
        if (!shiny_write_all(fd, header, sizeof(header)) ||
            !shiny_write_all(fd, output->rgb_video_output_data.screen_data, 240 * 320 * 3)) {
            result = 4; break;
        }
    }
    delete output;
    if (!capture_data->status.connected) {
        std::fprintf(stderr, "Loopy disconnected: %s\n", capture_data->status.detailed_error_text.c_str());
        result = 5;
    }
    capture_data->status.running = false;
    return result;
}
