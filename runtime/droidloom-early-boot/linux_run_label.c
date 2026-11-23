// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "linux_run_label.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <stdbool.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/xattr.h>
#include <unistd.h>

int droidloom_hold_linux_run(struct droidloom_linux_run *run)
{
    struct stat st;
    struct statfs fs;
    int fd = open("/run", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0)
        return -1;
    if (fstat(fd, &st) < 0 || fstatfs(fd, &fs) < 0) {
        int cause = errno;
        close(fd);
        errno = cause;
        return -1;
    }
    if (!S_ISDIR(st.st_mode) || st.st_uid != 0 || (st.st_mode & 0022) ||
        (unsigned long)fs.f_type != TMPFS_MAGIC) {
        close(fd);
        errno = EINVAL;
        return -1;
    }
    *run = (struct droidloom_linux_run){ .fd = fd, .device = st.st_dev, .inode = st.st_ino };
    return 0;
}

static bool droidloom_context_matches(const char *data, ssize_t size, const char *wanted)
{
    size_t length = strlen(wanted);
    if (size != (ssize_t)length &&
        (size != (ssize_t)(length + 1) || data[length] != '\0'))
        return false;
    return memcmp(data, wanted, length) == 0;
}

static const char private_run_context[] = "u:object_r:p4_linux_run_t:s0";

int droidloom_verify_linux_run(const struct droidloom_linux_run *run)
{
    char context[128];
    struct stat st;
    ssize_t size = fgetxattr(run->fd, "security.selinux", context, sizeof(context));
    if (size < 0 || fstat(run->fd, &st) < 0)
        return -1;
    if (!droidloom_context_matches(context, size, private_run_context)) {
        errno = EACCES;
        return -1;
    }
    if (st.st_dev != run->device || st.st_ino != run->inode) {
        errno = ESTALE;
        return -1;
    }
    return 0;
}

int droidloom_label_linux_run(const struct droidloom_linux_run *run)
{
    char context[128];
    ssize_t size = fgetxattr(run->fd, "security.selinux", context, sizeof(context));
    if (size < 0)
        return -1;
    if (!droidloom_context_matches(context, size, private_run_context)) {
        if (!droidloom_context_matches(context, size, "u:object_r:tmpfs:s0")) {
            errno = EACCES;
            return -1;
        }
        if (fsetxattr(run->fd, "security.selinux", private_run_context,
                      sizeof(private_run_context), 0) < 0)
            return -1;
    }
    return droidloom_verify_linux_run(run);
}
