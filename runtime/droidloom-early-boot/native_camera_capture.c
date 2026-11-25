// SPDX-License-Identifier: GPL-3.0-or-later
/* The only physical source is the caller's held, authenticated UVC descriptor.
 * No pathname, frame file, generated image, replay, or output file is accepted.
 * The original owner and Android peer PIDFDs remain live throughout capture.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define CAMERA_WIDTH 640U
#define CAMERA_HEIGHT 480U
#define CAMERA_FPS 30U
#define CAMERA_MAX_JPEG (4U * 1024U * 1024U)
#define CAMERA_MAX_AGE UINT64_C(1000000000)
#define CAMERA_IO_WAIT UINT64_C(2000000000)
#define CAMERA_MAX_BUFFERS 8U

enum { CAMERA_SESSION_CLOSED = 0, CAMERA_OWNER_STOP = 1, CAMERA_DEVICE_GONE = 2 };

struct droidloom_camera_statistics {
    uint64_t delivered, dequeued, dropped, last_capture_ns;
};
struct camera_watch {
    int stream, control, original_init, original_owner, producer;
    int outcome;
};
struct camera_map { void *address; size_t length; };

static int camera_fail(int error) { errno = error; return -1; }
static uint64_t camera_now(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) || value.tv_sec < 0 ||
        value.tv_nsec < 0 || value.tv_nsec >= 1000000000L) return 0;
    return (uint64_t)value.tv_sec * UINT64_C(1000000000) + (uint64_t)value.tv_nsec;
}
static int camera_ioctl(int fd, unsigned long request, void *value)
{
    int result;
    do { result = ioctl(fd, request, value); } while (result < 0 && errno == EINTR);
    return result;
}

/* A probe does not set a format, allocate buffers, start capture, or read frames.
 * It admits only the real UVC driver and the exact advertised MJPEG geometry.
 */
int droidloom_camera_probe(int fd)
{
    struct v4l2_capability cap = {0};
    if (camera_ioctl(fd, VIDIOC_QUERYCAP, &cap)) return -1;
    if (memcmp(cap.driver, "uvcvideo", 9)) return camera_fail(ENODEV);
    uint32_t flags = cap.capabilities & V4L2_CAP_DEVICE_CAPS ?
        cap.device_caps : cap.capabilities;
    if ((flags & (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING)) !=
        (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING)) return camera_fail(ENODEV);
    bool format = false, geometry = false, interval = false;
    for (uint32_t i = 0; i < 256; ++i) {
        struct v4l2_fmtdesc value = {.index = i, .type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
        if (camera_ioctl(fd, VIDIOC_ENUM_FMT, &value)) {
            if (errno == EINVAL) break;
            return -1;
        }
        if (value.pixelformat == V4L2_PIX_FMT_MJPEG) { format = true; break; }
    }
    if (!format) return camera_fail(ENODEV);
    for (uint32_t i = 0; i < 256; ++i) {
        struct v4l2_frmsizeenum value = {.index = i, .pixel_format = V4L2_PIX_FMT_MJPEG};
        if (camera_ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &value)) {
            if (errno == EINVAL) break;
            return -1;
        }
        if (value.type == V4L2_FRMSIZE_TYPE_DISCRETE &&
            value.discrete.width == CAMERA_WIDTH &&
            value.discrete.height == CAMERA_HEIGHT) { geometry = true; break; }
    }
    if (!geometry) return camera_fail(ENODEV);
    for (uint32_t i = 0; i < 256; ++i) {
        struct v4l2_frmivalenum value = {.index = i,
            .pixel_format = V4L2_PIX_FMT_MJPEG, .width = CAMERA_WIDTH, .height = CAMERA_HEIGHT};
        if (camera_ioctl(fd, VIDIOC_ENUM_FRAMEINTERVALS, &value)) {
            if (errno == EINVAL) break;
            return -1;
        }
        if (value.type == V4L2_FRMIVAL_TYPE_DISCRETE && value.discrete.numerator &&
            (uint64_t)value.discrete.numerator * CAMERA_FPS == value.discrete.denominator) {
            interval = true; break;
        }
    }
    return interval ? 0 : camera_fail(ENODEV);
}

static int camera_events(struct camera_watch *watch, int fd, short events, uint64_t deadline)
{
    for (;;) {
        uint64_t now = camera_now();
        if (!now || now >= deadline) return camera_fail(ETIMEDOUT);
        uint64_t remaining = (deadline - now + 999999) / 1000000;
        struct pollfd pollers[] = {
            {.fd = fd, .events = events},
            {.fd = watch->control, .events = POLLIN},
            {.fd = watch->original_init, .events = POLLIN},
            {.fd = watch->original_owner, .events = POLLIN},
            {.fd = watch->producer, .events = POLLIN},
            {.fd = watch->stream, .events = POLLIN | POLLRDHUP},
        };
        int count = poll(pollers, sizeof(pollers) / sizeof(pollers[0]),
                         (int)(remaining > 1000 ? 1000 : remaining));
        if (count < 0) { if (errno == EINTR) continue; return -1; }
        for (size_t i = 0; i < sizeof(pollers) / sizeof(pollers[0]); ++i)
            if (pollers[i].revents & POLLNVAL) return camera_fail(EBADF);
        if (pollers[1].revents & POLLIN) {
            unsigned char command[9];
            ssize_t n = recv(watch->control, command, sizeof(command), MSG_DONTWAIT);
            if (n < 0 && (errno == EAGAIN || errno == EINTR)) continue;
            if (n != 8 || memcmp(command, "DLCSTOP1", 8)) return camera_fail(EPROTO);
            watch->outcome = CAMERA_OWNER_STOP;
            return 1;
        }
        if (pollers[1].revents & (POLLHUP | POLLERR) ||
            pollers[2].revents || pollers[3].revents)
            return camera_fail(EOWNERDEAD);
        if (pollers[4].revents || (pollers[5].revents & (POLLHUP | POLLRDHUP))) {
            watch->outcome = CAMERA_SESSION_CLOSED;
            return 1;
        }
        if (pollers[5].revents & POLLIN) {
            unsigned char unexpected;
            ssize_t n = recv(watch->stream, &unexpected, 1, MSG_PEEK | MSG_DONTWAIT);
            if (n == 0) { watch->outcome = CAMERA_SESSION_CLOSED; return 1; }
            if (n > 0) return camera_fail(EPROTO);
            if (errno != EAGAIN && errno != EINTR) return -1;
        }
        if (pollers[0].revents & (POLLERR | POLLHUP)) return camera_fail(ENODEV);
        if (pollers[0].revents & events) return 0;
    }
}

static int camera_write(struct camera_watch *watch, const void *data, size_t size,
                        uint64_t deadline)
{
    const unsigned char *bytes = data;
    while (size) {
        int ready = camera_events(watch, watch->stream, POLLOUT, deadline);
        if (ready) return ready;
        ssize_t n = send(watch->stream, bytes, size, MSG_DONTWAIT | MSG_NOSIGNAL);
        if (n < 0) {
            if (errno == EAGAIN || errno == EINTR) continue;
            if (errno == EPIPE || errno == ECONNRESET) {
                watch->outcome = CAMERA_SESSION_CLOSED; return 1;
            }
            return -1;
        }
        if (!n) return camera_fail(EIO);
        bytes += n; size -= (size_t)n;
    }
    return 0;
}

static int camera_frame(const struct v4l2_buffer *buffer, const struct camera_map *maps,
                        unsigned count, uint64_t now, uint64_t *capture)
{
    if (buffer->index >= count || buffer->bytesused < 4 ||
        buffer->bytesused > CAMERA_MAX_JPEG || buffer->bytesused > maps[buffer->index].length ||
        (buffer->flags & V4L2_BUF_FLAG_ERROR) ||
        (buffer->flags & V4L2_BUF_FLAG_TIMESTAMP_MASK) != V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC ||
        buffer->timestamp.tv_sec < 0 || buffer->timestamp.tv_usec < 0 ||
        buffer->timestamp.tv_usec >= 1000000 || !now) return camera_fail(EBADMSG);
    const unsigned char *bytes = maps[buffer->index].address;
    if (!bytes || bytes[0] != 0xff || bytes[1] != 0xd8 ||
        bytes[buffer->bytesused-2] != 0xff || bytes[buffer->bytesused-1] != 0xd9)
        return camera_fail(EBADMSG);
    uint64_t seconds = (uint64_t)buffer->timestamp.tv_sec;
    if (seconds > UINT64_MAX / UINT64_C(1000000000)) return camera_fail(EOVERFLOW);
    *capture = seconds * UINT64_C(1000000000) + (uint64_t)buffer->timestamp.tv_usec * 1000;
    if (!*capture || *capture > now || now - *capture > CAMERA_MAX_AGE)
        return camera_fail(ESTALE);
    return 0;
}
static void camera_be32(unsigned char *bytes, uint32_t value)
{
    for (int i = 3; i >= 0; --i) { bytes[i] = (unsigned char)value; value >>= 8; }
}
static void camera_be64(unsigned char *bytes, uint64_t value)
{
    for (int i = 7; i >= 0; --i) { bytes[i] = (unsigned char)value; value >>= 8; }
}

int droidloom_camera_capture(int device, int stream, int control,
                             int original_init, int original_owner, int producer,
                             struct droidloom_camera_statistics *stats)
{
    if (!stats || device < 0 || stream < 0 || control < 0 || original_init < 0 ||
        original_owner < 0 || producer < 0) return camera_fail(EINVAL);
    memset(stats, 0, sizeof(*stats));
    struct camera_watch watch = {stream, control, original_init, original_owner, producer, -1};
    struct camera_map maps[CAMERA_MAX_BUFFERS] = {{0}};
    unsigned mapped = 0;
    bool allocated = false, streaming = false;
    int error = 0, result = -1;
    int ready = camera_events(&watch, stream, POLLOUT, camera_now() + CAMERA_IO_WAIT);
    if (ready) { if (ready > 0) result = watch.outcome; else error = errno; goto finish; }
    struct v4l2_format format = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
    format.fmt.pix.width = CAMERA_WIDTH;
    format.fmt.pix.height = CAMERA_HEIGHT;
    format.fmt.pix.pixelformat = V4L2_PIX_FMT_MJPEG;
    format.fmt.pix.field = V4L2_FIELD_ANY;
    if (camera_ioctl(device, VIDIOC_S_FMT, &format)) { error = errno; goto finish; }
    if (format.fmt.pix.width != CAMERA_WIDTH || format.fmt.pix.height != CAMERA_HEIGHT ||
        format.fmt.pix.pixelformat != V4L2_PIX_FMT_MJPEG) { error = ENODEV; goto finish; }
    struct v4l2_streamparm rate = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
    rate.parm.capture.timeperframe.numerator = 1;
    rate.parm.capture.timeperframe.denominator = CAMERA_FPS;
    if (camera_ioctl(device, VIDIOC_S_PARM, &rate)) { error = errno; goto finish; }
    if (!rate.parm.capture.timeperframe.numerator ||
        (uint64_t)rate.parm.capture.timeperframe.numerator * CAMERA_FPS !=
            rate.parm.capture.timeperframe.denominator) { error = ENODEV; goto finish; }
    struct v4l2_requestbuffers request = {.count = 4,
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
    if (camera_ioctl(device, VIDIOC_REQBUFS, &request)) { error = errno; goto finish; }
    allocated = true;
    if (request.count < 2 || request.count > CAMERA_MAX_BUFFERS) { error = EOVERFLOW; goto finish; }
    for (unsigned i = 0; i < request.count; ++i) {
        struct v4l2_buffer buffer = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
            .memory = V4L2_MEMORY_MMAP, .index = i};
        if (camera_ioctl(device, VIDIOC_QUERYBUF, &buffer)) { error = errno; goto finish; }
        if (!buffer.length || buffer.length > CAMERA_MAX_JPEG) { error = EOVERFLOW; goto finish; }
        void *address = mmap(NULL, buffer.length, PROT_READ | PROT_WRITE, MAP_SHARED, device, buffer.m.offset);
        if (address == MAP_FAILED) { error = errno; goto finish; }
        maps[i] = (struct camera_map){address, buffer.length}; ++mapped;
        if (camera_ioctl(device, VIDIOC_QBUF, &buffer)) { error = errno; goto finish; }
    }
    ready = camera_events(&watch, stream, POLLOUT, camera_now() + CAMERA_IO_WAIT);
    if (ready) { if (ready > 0) result = watch.outcome; else error = errno; goto finish; }
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (camera_ioctl(device, VIDIOC_STREAMON, &type)) { error = errno; goto finish; }
    streaming = true;
    for (;;) {
        uint64_t now = camera_now();
        if (!now || now > UINT64_MAX - CAMERA_IO_WAIT) { error = EOVERFLOW; break; }
        int ready = camera_events(&watch, device, POLLIN, now + CAMERA_IO_WAIT);
        if (ready) { if (ready > 0) result = watch.outcome; else error = errno; break; }
        struct v4l2_buffer buffer = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
        if (camera_ioctl(device, VIDIOC_DQBUF, &buffer)) { error = errno; break; }
        ++stats->dequeued;
        uint64_t captured = 0;
        if (camera_frame(&buffer, maps, request.count, camera_now(), &captured)) { error = errno; break; }
        /* Always discard already queued frames before sending; no backlog is replayed. */
        for (unsigned i = 1; i < request.count; ++i) {
            struct v4l2_buffer newer = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
            if (camera_ioctl(device, VIDIOC_DQBUF, &newer)) {
                if (errno == EAGAIN) break;
                error = errno; break;
            }
            ++stats->dequeued;
            uint64_t newer_capture = 0;
            if (camera_frame(&newer, maps, request.count, camera_now(), &newer_capture)) { error = errno; break; }
            if (newer_capture <= captured) { error = ESTALE; break; }
            if (camera_ioctl(device, VIDIOC_QBUF, &buffer)) { error = errno; break; }
            ++stats->dropped; buffer = newer; captured = newer_capture;
        }
        if (error) break;
        if (captured <= stats->last_capture_ns || stats->delivered == UINT64_MAX ||
            captured > UINT64_MAX - CAMERA_MAX_AGE) { error = ESTALE; break; }
        unsigned char header[20];
        camera_be32(header, buffer.bytesused);
        camera_be64(header + 4, stats->delivered + 1);
        camera_be64(header + 12, captured);
        ready = camera_write(&watch, header, sizeof(header), captured + CAMERA_MAX_AGE);
        if (!ready) ready = camera_write(&watch, maps[buffer.index].address,
                                         buffer.bytesused, captured + CAMERA_MAX_AGE);
        if (ready) { if (ready > 0) result = watch.outcome; else error = errno; break; }
        ++stats->delivered; stats->last_capture_ns = captured;
        if (camera_ioctl(device, VIDIOC_QBUF, &buffer)) { error = errno; break; }
    }
finish:
    /* Zero/stop is not reported until all actual driver/mapping retirement
     * succeeded. Device disappearance is distinct from an ordinary stream stop. */
    if (streaming) {
        enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (camera_ioctl(device, VIDIOC_STREAMOFF, &type) && !error)
            error = errno;
    }
    for (unsigned i = 0; i < mapped; ++i)
        if (munmap(maps[i].address, maps[i].length) && !error) error = errno;
    if (allocated) {
        struct v4l2_requestbuffers release = {.count = 0,
            .type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
        if (camera_ioctl(device, VIDIOC_REQBUFS, &release) && !error)
            error = errno;
    }
    if (error == ENODEV && result != CAMERA_OWNER_STOP) return CAMERA_DEVICE_GONE;
    return error ? camera_fail(error) : result;
}
