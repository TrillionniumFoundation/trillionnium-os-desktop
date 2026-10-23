// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
// Retain the original strict HOS2 codec, including its header/body checks.
#define main original_queryabi_probe_main
#include "hos2_queryabi_probe.c"
#undef main
#include <poll.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>

static unsigned cases, failures;

static void result(const char *name, int passed)
{
    cases++;
    failures += !passed;
    printf("BOOT_ID_CASE name=%s pass=%d\n", name, !!passed);
}

static int read_uuid(char value[38])
{
    int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t count = read(fd, value, 38);
    int saved = errno;
    close(fd);
    errno = saved;
    return count == 37 ? 0 : -1;
}

static int decode_uuid(const char value[38], uint8_t bytes[16])
{
    static const char hex[] = "0123456789abcdef";
    unsigned index = 0;
    for (unsigned i = 0; i < 36;) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (value[i++] != '-') return -1;
            continue;
        }
        const char *hi = strchr(hex, value[i++]);
        const char *lo = strchr(hex, value[i++]);
        if (!hi || !lo || hi == hex + 16 || lo == hex + 16 || index == 16) return -1;
        bytes[index++] = (uint8_t)(((hi - hex) << 4) | (lo - hex));
    }
    return index == 16 && value[36] == '\n' && bytes[6] >> 4 == 4 && bytes[8] >> 6 == 2 ? 0 : -1;
}

static int exact_read(int fd, void *buffer, size_t length)
{
    char *bytes = buffer;
    while (length) {
        ssize_t count = read(fd, bytes, length);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return -1;
        bytes += count;
        length -= (size_t)count;
    }
    return 0;
}

int main(int argc, char **argv)
{
    int native = argc == 3 && strcmp(argv[1], "--hos2-ioctl") == 0;
    if (!native && argc != 1) return 2;
    char uuid[38] = {0}, again[38] = {0};
    uint8_t identity[16] = {0};
    if (read_uuid(uuid) != 0) {
        printf("BOOT_ID_UNAVAILABLE errno=%d\n", errno);
        return 1;
    }
    result("uuid_format", decode_uuid(uuid, identity) == 0);
    result("stable_reopen", read_uuid(again) == 0 && memcmp(uuid, again, 37) == 0);
    int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 1;
    int partial = 1;
    for (off_t i = 0; i < 37; i++) {
        char byte = 0;
        if (pread(fd, &byte, 1, i) != 1 || byte != uuid[i]) partial = 0;
    }
    result("partial_reads", partial);
    char byte;
    result("eof", pread(fd, &byte, 1, 37) == 0);
    close(fd);
    fd = open("/proc/sys/kernel/random/boot_id", O_WRONLY | O_CLOEXEC);
    int denied = fd < 0 && (errno == EACCES || errno == EPERM || errno == EROFS);
    if (fd >= 0) {
        denied = write(fd, "changed", 7) == -1 && (errno == EPERM || errno == EACCES || errno == EROFS);
        close(fd);
    }
    result("write_denied", denied);
    result("unchanged_after_write", read_uuid(again) == 0 && memcmp(uuid, again, 37) == 0);

    int report[2], release[2];
    if (pipe2(report, O_CLOEXEC) || pipe2(release, O_CLOEXEC)) return 1;
    pid_t child = fork();
    if (child < 0) return 1;
    if (child == 0) {
        close(report[0]); close(release[1]);
        char own[38] = {0}, stop;
        int ok = read_uuid(own) == 0 && write(report[1], own, 37) == 37;
        close(report[1]);
        if (ok && read(release[0], &stop, 1) == 0) { close(release[0]); _exit(0); }
        _exit(1);
    }
    close(report[1]); close(release[0]);
    result("fork_same_uuid", exact_read(report[0], again, 37) == 0 && memcmp(uuid, again, 37) == 0);
    close(report[0]);
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0);
    int pinned = 0;
    if (pidfd >= 0) {
        char path[96], link[64] = {0}, info[512] = {0}, expected[64];
        snprintf(path, sizeof(path), "/proc/self/fd/%d", pidfd);
        ssize_t length = readlink(path, link, sizeof(link) - 1);
        snprintf(path, sizeof(path), "/proc/self/fdinfo/%d", pidfd);
        int details = open(path, O_RDONLY | O_CLOEXEC);
        ssize_t info_length = details >= 0 ? read(details, info, sizeof(info) - 1) : -1;
        if (details >= 0) close(details);
        snprintf(expected, sizeof(expected), "Pid:\t%ld\n", (long)child);
        pinned = length == 18 && memcmp(link, "anon_inode:[pidfd]", 18) == 0 && info_length > 0 && strstr(info, expected);
    }
    result("pidfd_identity", pinned);
    struct pollfd event = { .fd = pidfd, .events = POLLIN };
    result("pidfd_alive_not_readable", pidfd >= 0 && poll(&event, 1, 0) == 0);
    close(release[1]);
    int ready = pidfd >= 0 ? poll(&event, 1, 2000) : -1;
    int status = 0;
    pid_t reaped = waitpid(child, &status, 0);
    result("pidfd_exit_readable", ready == 1 && (event.revents & POLLIN) && reaped == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    if (pidfd >= 0) close(pidfd);
    struct timespec first, second;
    int clocks = clock_gettime(CLOCK_BOOTTIME, &first) == 0 && clock_gettime(CLOCK_BOOTTIME, &second) == 0;
    result("clock_boottime_nondecreasing", clocks && first.tv_sec >= 0 && (second.tv_sec > first.tv_sec || (second.tv_sec == first.tv_sec && second.tv_nsec >= first.tv_nsec)));

    if (native) {
        char *end = NULL;
        unsigned long request_number = strtoul(argv[2], &end, 0);
        if (!end || *end || !request_number) return 2;
        uint8_t request[HEADER], response[QUERY_RESPONSE] = {0}, transport[TRANSPORT] = {0};
        query(request);
        w64(transport, (uintptr_t)request); w64(transport + 8, (uintptr_t)response);
        w32(transport + 16, sizeof(request)); w32(transport + 20, sizeof(response));
        fd = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
        int ok = fd >= 0 && ioctl(fd, request_number, transport) == 0 && check_query(response, sizeof(response)) == 0;
        if (fd >= 0) close(fd);
        result("hos2_same_boot", ok && memcmp(response + HEADER, identity, 16) == 0);
    }
    uuid[36] = 0;
    printf("BOOT_ID_UUID=%s\nBOOT_ID_COMPLETE cases=%u failures=%u\n", uuid, cases, failures);
    return failures ? 1 : 0;
}
