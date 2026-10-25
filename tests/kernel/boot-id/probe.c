// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned failures;
static const char path[] = "/proc/sys/kernel/random/boot_id";
static void check(int ok, const char *name) {
    if (!ok) ++failures;
    printf("{\"check\":\"%s\",\"passed\":%s,\"errno\":%d}\n", name, ok ? "true" : "false", errno);
}
static int read_id(char out[38]) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t n = read(fd, out, 38);
    int error = errno;
    close(fd); errno = error;
    if (n != 37) return -1;
    out[37] = 0; return 0;
}
static int nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
static int parse_id(const char text[38], unsigned char out[16]) {
    unsigned at = 0;
    for (unsigned i = 0; i < 36;) {
        if (i == 8 || i == 13 || i == 18 || i == 23) { if (text[i++] != '-') return 0; continue; }
        int hi = nibble(text[i++]), lo = nibble(text[i++]);
        if (hi < 0 || lo < 0 || at >= 16) return 0;
        out[at++] = (unsigned char)((hi << 4) | lo);
    }
    return at == 16 && text[36] == '\n' && text[37] == 0
        && (out[6] & 0xf0) == 0x40 && (out[8] & 0xc0) == 0x80;
}
static void put(unsigned char *out, uint64_t value, unsigned n) {
    for (unsigned i = 0; i < n; ++i) out[i] = (unsigned char)(value >> (i * 8));
}
static int query_matches(const unsigned char expected[16]) {
    int fd = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
    if (fd < 0) return 0;
    unsigned char request[64] = {0}, reply[112] = {0}, transport[32] = {0};
    memcpy(request, "HOS2", 4); put(request + 4, 2, 2); put(request + 8, 1, 2);
    put(request + 12, 64, 4); request[24] = 73;
    put(transport, (uintptr_t)request, 8); put(transport + 8, (uintptr_t)reply, 8);
    put(transport + 16, sizeof request, 4); put(transport + 20, sizeof reply, 4);
    int ok = ioctl(fd, 0xc0204802U, transport) == 0 && !memcmp(reply, "HOSR", 4)
        && reply[4] == 2 && reply[8] == 1 && reply[20] == 0
        && !memcmp(reply + 24, request + 24, 16) && !memcmp(reply + 40, expected, 16);
    close(fd); return ok;
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    char first[38], second[38];
    if (argc == 2 && !strcmp(argv[1], "--expect-unavailable")) {
        errno = 0; check(read_id(first) == -1 && errno == EOPNOTSUPP, "timestamp_seed_has_no_protected_boot_id");
        errno = 0; int fd = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
        check(fd == -1 && errno == EOPNOTSUPP, "timestamp_seed_cannot_open_hos2");
        if (fd >= 0) close(fd);
        printf("{\"boot_id_unavailable\":true}\n"); return failures ? 1 : 0;
    }
    if (argc == 3 && !strcmp(argv[1], "--verify-exec")) {
        check(read_id(first) == 0 && !strcmp(first, argv[2]), "boot_id_stable_across_exec");
        return failures ? 1 : 0;
    }
    int read_ok = read_id(first) == 0;
    check(read_ok, "read_kernel_boot_id"); if (!read_ok) return 1;
    unsigned char bytes[16] = {0};
    check(parse_id(first, bytes), "boot_id_is_canonical_v4_uuid");
    check(read_id(second) == 0 && !strcmp(first, second), "boot_id_stable_across_reopen");
    int fd = open(path, O_RDONLY | O_CLOEXEC); char part[7] = {0};
    check(fd >= 0 && pread(fd, part, 6, 17) == 6 && !memcmp(part, first + 17, 6), "boot_id_partial_offset_read");
    check(fd >= 0 && pread(fd, part, sizeof part, 37) == 0, "boot_id_eof_after_newline");
    if (fd >= 0) close(fd);
    struct stat st;
    check(stat(path, &st) == 0 && S_ISREG(st.st_mode) && !(st.st_mode & 0222), "boot_id_inode_is_read_only");
    fd = open(path, O_WRONLY | O_CLOEXEC);
    check(fd < 0 || write(fd, "forged", 6) < 0, "boot_id_rejects_write_even_as_root");
    if (fd >= 0) close(fd);
    check(read_id(second) == 0 && !strcmp(first, second), "failed_write_does_not_change_boot_id");
    check(chmod(path, 0666) == 0, "procfs_metadata_change_is_separate_from_boot_identity");
    fd = open(path, O_WRONLY | O_CLOEXEC);
    check(fd >= 0 && write(fd, "forged", 6) == -1 && errno == EPERM, "writable_mode_does_not_enable_boot_id_mutation");
    if (fd >= 0) close(fd);
    check(chmod(path, 0444) == 0 && read_id(second) == 0 && !strcmp(first, second), "boot_identity_survives_metadata_change");
    check(query_matches(bytes), "procfs_and_hos2_use_same_original_boot_bytes");
    pid_t child = fork();
    if (child == 0) _exit(read_id(second) == 0 && !strcmp(first, second) ? 0 : 71);
    int status;
    check(child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "boot_id_stable_across_fork");
    child = fork();
    if (child == 0) _exit(setuid(1001) == 0 && read_id(second) == 0 && !strcmp(first, second) ? 0 : 73);
    check(child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "boot_id_same_for_unprivileged_reader");
    child = fork();
    if (child == 0) { char *const next[] = {argv[0], "--verify-exec", first, NULL}; execv(argv[0], next); _exit(72); }
    check(child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "boot_id_exec_child_exits");
    first[36] = 0; printf("{\"boot_id\":\"%s\",\"wire_matches\":%s}\n", first, failures ? "false" : "true");
    return failures ? 1 : 0;
}
