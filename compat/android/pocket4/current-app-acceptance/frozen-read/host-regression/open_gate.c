#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Deterministic test rendezvous immediately before the target's real open.
 * No metadata, descriptor or return value is replaced by the interposer. */
static __thread int inside;
static int admitted;
static void rendezvous(const char *path, int flags) {
    if (inside || admitted) return;
    inside = 1;
    const char *expected = getenv("P4_FROZEN_RACE_PATH");
    const char *notify = getenv("P4_FROZEN_NOTIFY_FD");
    const char *release = getenv("P4_FROZEN_RELEASE_FD");
    if (expected && notify && release && !strcmp(path, expected)) {
        admitted = 1;
        char message[96];
        int length = snprintf(message, sizeof(message), "open_flags=%d\n", flags);
        if (write(atoi(notify), message, (size_t)length) != length) _exit(91);
        char byte;
        if (read(atoi(release), &byte, 1) != 1 || byte != 'G') _exit(92);
    }
    inside = 0;
}

int open(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, int); va_end(args); }
    int (*real_open)(const char *, int, ...) = dlsym(RTLD_NEXT, "open");
    if (!real_open) _exit(93);
    rendezvous(path, flags);
    return real_open(path, flags, mode);
}

int open64(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, int); va_end(args); }
    int (*real_open)(const char *, int, ...) = dlsym(RTLD_NEXT, "open64");
    if (!real_open) _exit(94);
    rendezvous(path, flags);
    return real_open(path, flags, mode);
}
