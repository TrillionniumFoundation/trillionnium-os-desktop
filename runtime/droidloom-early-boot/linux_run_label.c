// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "linux_run_label.h"
#include <dirent.h>
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

static int verify_label(const struct droidloom_linux_run *run, const char *expected)
{
    char context[128];
    struct stat st;
    ssize_t size = fgetxattr(run->fd, "security.selinux", context, sizeof(context));
    if (size < 0 || fstat(run->fd, &st) < 0)
        return -1;
    if (!droidloom_context_matches(context, size, expected)) {
        errno = EACCES;
        return -1;
    }
    if (st.st_dev != run->device || st.st_ino != run->inode) {
        errno = ESTALE;
        return -1;
    }
    return 0;
}

static int apply_label(const struct droidloom_linux_run *run, const char *expected)
{
    char context[128];
    ssize_t size = fgetxattr(run->fd, "security.selinux", context, sizeof(context));
    if (size < 0)
        return -1;
    if (!droidloom_context_matches(context, size, expected)) {
        if (!droidloom_context_matches(context, size, "u:object_r:tmpfs:s0")) {
            errno = EACCES;
            return -1;
        }
        if (fsetxattr(run->fd, "security.selinux", expected,
                      strlen(expected) + 1, 0) < 0)
            return -1;
    }
    return verify_label(run, expected);
}

int droidloom_verify_linux_run(const struct droidloom_linux_run *run)
{
    return verify_label(run, private_run_context);
}

int droidloom_label_linux_run(const struct droidloom_linux_run *run)
{
    return apply_label(run, private_run_context);
}

static int hold_child(const struct droidloom_linux_run *parent, const char *name,
                      gid_t group, mode_t mode, struct droidloom_linux_run *child)
{
    int fd = openat(parent->fd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0)
        return -1;
    struct stat info;
    struct statx from, to;
    int error = 0;
    if (fstat(fd, &info) < 0 ||
        statx(parent->fd, "", AT_EMPTY_PATH, STATX_MNT_ID, &from) < 0 ||
        statx(fd, "", AT_EMPTY_PATH, STATX_MNT_ID, &to) < 0)
        error = errno;
    else if (!(from.stx_mask & STATX_MNT_ID) || !(to.stx_mask & STATX_MNT_ID) ||
             from.stx_mnt_id != to.stx_mnt_id || parent->device != info.st_dev ||
             !S_ISDIR(info.st_mode) || info.st_uid || info.st_gid != group ||
             (info.st_mode & 07777) != mode)
        error = EACCES;
    if (error) {
        close(fd);
        errno = error;
        return -1;
    }
    *child = (struct droidloom_linux_run){ .fd = fd, .device = info.st_dev, .inode = info.st_ino };
    return 0;
}

static int validate_empty_endpoint(int fd)
{
    int copy = fcntl(fd, F_DUPFD_CLOEXEC, 3);
    if (copy < 0)
        return -1;
    DIR *dir = fdopendir(copy);
    if (!dir) {
        int error = errno;
        close(copy);
        errno = error;
        return -1;
    }
    const struct dirent *entry;
    int error = 0;
    errno = 0;
    while ((entry = readdir(dir)) != NULL) {
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) {
            error = ENOTEMPTY;
            break;
        }
    }
    if (!error)
        error = errno;
    closedir(dir);
    if (error) {
        errno = error;
        return -1;
    }
    return 0;
}

int droidloom_hold_readiness_paths(const struct droidloom_linux_run *run,
                                  gid_t observer_gid, struct droidloom_readiness_paths *paths)
{
    if (hold_child(run, "droidloom-early", 0, 0700, &paths->handoff) < 0 ||
        hold_child(&paths->handoff, "readiness", observer_gid, 02710, &paths->readiness) < 0)
        return -1;
    return validate_empty_endpoint(paths->readiness.fd);
}

int droidloom_label_readiness_paths(const struct droidloom_readiness_paths *paths)
{
    if (apply_label(&paths->handoff, "u:object_r:p4_linux_early_handoff_dir_t:s0") < 0)
        return -1;
    return apply_label(&paths->readiness, "u:object_r:p4_linux_readiness_dir_t:s0");
}
