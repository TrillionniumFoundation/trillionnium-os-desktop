// SPDX-License-Identifier: GPL-3.0-or-later
/* Mechanism tests only. No physical device is opened and no frame is captured. */
#include "../native_camera_capture.c"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/wait.h>

static void pair(int sockets[2], int type)
{
    assert(socketpair(AF_UNIX, type | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, sockets) == 0);
}
static void fresh(int stream[2], int control[2], struct camera_watch *watch, int self)
{
    pair(stream, SOCK_STREAM); pair(control, SOCK_SEQPACKET);
    *watch = (struct camera_watch){stream[0], control[0], self, self, self, -1};
}
static void finish_pair(int stream[2], int control[2])
{
    for (unsigned i = 0; i < 2; ++i) { close(stream[i]); close(control[i]); }
}
int main(void)
{
    unsigned checks = 0;
    unsigned char jpeg[] = {0xff, 0xd8, 0xff, 0xd9};
    struct camera_map map = {jpeg, sizeof(jpeg)};
    struct v4l2_buffer frame = {.index = 0, .bytesused = sizeof(jpeg),
        .flags = V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC, .timestamp = {.tv_sec = 10}};
    uint64_t stamp = 0, now = UINT64_C(10000000000);
    assert(camera_frame(&frame, &map, 1, now, &stamp) == 0 && stamp == now); ++checks;
    struct v4l2_buffer bad = frame;
    bad.flags = 0; assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == EBADMSG); ++checks;
    bad = frame; bad.flags |= V4L2_BUF_FLAG_ERROR;
    assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == EBADMSG); ++checks;
    bad = frame; bad.bytesused = 3;
    assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == EBADMSG); ++checks;
    bad = frame; bad.bytesused = sizeof(jpeg) + 1;
    assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == EBADMSG); ++checks;
    bad = frame; bad.index = 1;
    assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == EBADMSG); ++checks;
    bad = frame; bad.timestamp.tv_sec = 11;
    assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == ESTALE); ++checks;
    bad = frame; bad.timestamp.tv_sec = 8;
    assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == ESTALE); ++checks;
    bad = frame; bad.timestamp.tv_usec = 1000000;
    assert(camera_frame(&bad, &map, 1, now, &stamp) < 0 && errno == EBADMSG); ++checks;
    jpeg[3] = 0; assert(camera_frame(&frame, &map, 1, now, &stamp) < 0 && errno == EBADMSG); ++checks;
    jpeg[3] = 0xd9;
    int self = (int)syscall(SYS_pidfd_open, getpid(), 0);
    assert(self >= 0);
    int stream[2], control[2];
    struct camera_watch watch;
    fresh(stream, control, &watch, self);
    assert(camera_events(&watch, stream[0], POLLOUT, camera_now() + CAMERA_IO_WAIT) == 0); ++checks;
    assert(send(control[1], "DLCSTOP1", 8, MSG_NOSIGNAL) == 8);
    assert(camera_events(&watch, stream[0], POLLOUT, camera_now() + CAMERA_IO_WAIT) == 1 &&
           watch.outcome == CAMERA_OWNER_STOP); ++checks;
    finish_pair(stream, control);
    fresh(stream, control, &watch, self);
    assert(send(control[1], "DLCSTOP", 7, MSG_NOSIGNAL) == 7);
    assert(camera_events(&watch, stream[0], POLLOUT, camera_now() + CAMERA_IO_WAIT) < 0 &&
           errno == EPROTO); ++checks;
    finish_pair(stream, control);
    fresh(stream, control, &watch, self);
    assert(shutdown(stream[1], SHUT_RDWR) == 0);
    assert(camera_events(&watch, stream[0], POLLOUT, camera_now() + CAMERA_IO_WAIT) == 1 &&
           watch.outcome == CAMERA_SESSION_CLOSED); ++checks;
    finish_pair(stream, control);
    fresh(stream, control, &watch, self);
    assert(send(stream[1], "X", 1, MSG_NOSIGNAL) == 1);
    assert(camera_events(&watch, stream[0], POLLOUT, camera_now() + CAMERA_IO_WAIT) < 0 &&
           errno == EPROTO); ++checks;
    finish_pair(stream, control);
    int gate[2]; assert(pipe2(gate, O_CLOEXEC) == 0);
    pid_t child = fork(); assert(child >= 0);
    if (!child) {
        close(gate[1]); char byte;
        ssize_t n = read(gate[0], &byte, 1); close(gate[0]);
        _exit(n == 0 ? 0 : 1);
    }
    close(gate[0]);
    int ended = (int)syscall(SYS_pidfd_open, child, 0); assert(ended >= 0);
    close(gate[1]);
    struct pollfd dead = {.fd = ended, .events = POLLIN};
    assert(poll(&dead, 1, 2000) == 1 && (dead.revents & POLLIN));
    fresh(stream, control, &watch, self); watch.original_owner = ended;
    assert(camera_events(&watch, stream[0], POLLOUT, camera_now() + CAMERA_IO_WAIT) < 0 &&
           errno == EOWNERDEAD); ++checks;
    finish_pair(stream, control);
    int status; assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(ended); close(self);
    unsigned char header[20];
    camera_be32(header, 0x01020304); camera_be64(header + 4, UINT64_C(0x0102030405060708));
    camera_be64(header + 12, UINT64_C(0x1112131415161718));
    const unsigned char expected[20] = {1,2,3,4,1,2,3,4,5,6,7,8,0x11,0x12,0x13,0x14,0x15,0x16,0x17,0x18};
    assert(memcmp(header, expected, sizeof(header)) == 0); ++checks;
    printf("camera core mechanism checks: %u; physical device opens=0, captures=0\n", checks);
    printf("ioctl ABI: %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx\n",
        (unsigned long)VIDIOC_QUERYCAP, (unsigned long)VIDIOC_ENUM_FMT,
        (unsigned long)VIDIOC_ENUM_FRAMESIZES, (unsigned long)VIDIOC_ENUM_FRAMEINTERVALS,
        (unsigned long)VIDIOC_S_FMT, (unsigned long)VIDIOC_S_PARM,
        (unsigned long)VIDIOC_REQBUFS, (unsigned long)VIDIOC_QUERYBUF,
        (unsigned long)VIDIOC_QBUF, (unsigned long)VIDIOC_DQBUF,
        (unsigned long)VIDIOC_STREAMON, (unsigned long)VIDIOC_STREAMOFF);
    return 0;
}
