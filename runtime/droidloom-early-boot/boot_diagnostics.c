// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "boot_diagnostics.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/openat2.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/xattr.h>
#include <unistd.h>

#define BOOT_KMSG "/usr/lib/droidloom/production/current/board-devices/kmsg"
#define BOOT_KMSG_CONTEXT "u:object_r:kmsg_device:s0"
#define STAGE_LIMIT 192U

static int boot_kmsg = -1;

static int reject(int error)
{
    errno = error;
    return -1;
}

int droidloom_boot_diagnostics_prepare(void)
{
    if (getpid() != 1 || geteuid() != 0 || boot_kmsg >= 0)
        return reject(EPERM);
    struct open_how how = {
        .flags = O_WRONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK | O_NOCTTY,
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS,
    };
    int fd = (int)syscall(SYS_openat2, AT_FDCWD, BOOT_KMSG, &how, sizeof(how));
    if (fd < 0)
        return -1;
    int error = 0;
    struct stat held, named, root;
    struct statfs filesystem;
    char context[sizeof(BOOT_KMSG_CONTEXT) + 1] = {0};
    ssize_t length;
    int descriptor_flags = fcntl(fd, F_GETFD);
    if (descriptor_flags < 0 || fstat(fd, &held) < 0 || lstat(BOOT_KMSG, &named) < 0 ||
        stat("/", &root) < 0 || fstatfs(fd, &filesystem) < 0)
        error = errno;
    else if (!S_ISCHR(held.st_mode) || held.st_rdev != makedev(1, 11) ||
             held.st_uid != 0 || held.st_gid != 0 || held.st_nlink != 1 ||
             (held.st_mode & 07777) != 0600 ||
             held.st_dev != root.st_dev ||
             held.st_dev != named.st_dev || held.st_ino != named.st_ino ||
             !S_ISCHR(named.st_mode) || named.st_rdev != held.st_rdev ||
             (unsigned long)filesystem.f_type != EXT4_SUPER_MAGIC ||
             (descriptor_flags & FD_CLOEXEC) == 0)
        error = EACCES;
    /* Before initial SELinux activation, the real kernel's getsecurity hook
     * falls back to this actual on-disk xattr. Do not relabel an arbitrary
     * devtmpfs node, or defer an unavailable getattr/open until after load. */
    if (!error) {
        length = fgetxattr(fd, "security.selinux", context, sizeof(context));
        if (length < 0)
            error = errno;
        else if ((length != (ssize_t)sizeof(BOOT_KMSG_CONTEXT) &&
                  length != (ssize_t)sizeof(BOOT_KMSG_CONTEXT) - 1) ||
                 memcmp(context, BOOT_KMSG_CONTEXT, sizeof(BOOT_KMSG_CONTEXT)) != 0)
            error = EACCES;
    }
    if (!error) {
        struct stat after;
        if (fstat(fd, &after) < 0)
            error = errno;
        else if (after.st_dev != held.st_dev || after.st_ino != held.st_ino ||
                 after.st_rdev != held.st_rdev || after.st_mode != held.st_mode ||
                 after.st_uid != held.st_uid || after.st_gid != held.st_gid ||
                 after.st_nlink != held.st_nlink ||
                 after.st_ctim.tv_sec != held.st_ctim.tv_sec ||
                 after.st_ctim.tv_nsec != held.st_ctim.tv_nsec)
            error = ESTALE;
    }
    if (error) {
        close(fd);
        return reject(error);
    }
    boot_kmsg = fd;
    return 0;
}

/* One bounded kernel-log record. A failed diagnostic must not replace the
 * original startup error or alter the startup decision. There is no dynamic
 * path, caller-supplied content, environment, or credential material here. */
void droidloom_boot_diagnostics_report(enum droidloom_boot_diagnostic_phase phase,
                                      const char *stage, int error)
{
    int saved = errno;
    const char *scope = phase == DROIDLOOM_DIAGNOSTIC_POLICY ? "early policy" :
                        phase == DROIDLOOM_DIAGNOSTIC_PID1 ? "real-root PID 1" : NULL;
    if (!scope || !stage)
        goto finished;
    char safe_stage[STAGE_LIMIT + 1];
    size_t size = strnlen(stage, STAGE_LIMIT);
    for (size_t n = 0; n < size; n++) {
        unsigned char byte = (unsigned char)stage[n];
        safe_stage[n] = byte >= ' ' && byte <= '~' ? (char)byte : '?';
    }
    safe_stage[size] = 0;
    char record[320];
    int length = snprintf(record, sizeof(record),
                          "<3>Droidloom %s failed at %s: errno=%d\n",
                          scope, safe_stage, error);
    if (length <= 0 || (size_t)length >= sizeof(record))
        goto finished;
    int fd = boot_kmsg >= 0 ? boot_kmsg : STDERR_FILENO;
    for (unsigned int attempts = 0; attempts < 4; attempts++) {
        ssize_t written = write(fd, record, (size_t)length);
        if (written >= 0 || errno != EINTR)
            break;
    }
finished:
    errno = saved;
}
