// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "device_source.h"
#include "device_template.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/nsfs.h>
#include <linux/openat2.h>
#include <sched.h>
#include <stdbool.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>
#include <unistd.h>

#define SOURCE_PARENT "/run/droidloom-early"
#define HANDOFF "/run/droidloom-early"

static int reject(int cause)
{
    errno = cause;
    return -1;
}

static int directory(const char *path)
{
    struct open_how how = {
        .flags = O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC,
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS
    };
    return (int) syscall(SYS_openat2, AT_FDCWD, path, &how, sizeof(how));
}

static int identity(int fd, struct droidloom_device_identity *out)
{
    struct stat st;
    struct statx mount;
    if (fstat(fd, &st) || statx(fd, "", AT_EMPTY_PATH, STATX_MNT_ID_UNIQUE, &mount))
        return -1;
    if (!(mount.stx_mask & STATX_MNT_ID_UNIQUE) || !mount.stx_mnt_id || !S_ISDIR(st.st_mode))
        return reject(ESTALE);
    *out = (struct droidloom_device_identity){st.st_dev, st.st_ino, mount.stx_mnt_id};
    return 0;
}

static int empty(int fd)
{
    int stream = openat(fd, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (stream < 0)
        return -1;
    DIR *dir = fdopendir(stream);
    if (!dir) {
        int error = errno;
        close(stream);
        return reject(error);
    }
    int error = 0;
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(dir))) {
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) {
            error = ENOTEMPTY;
            break;
        }
    }
    if (!error)
        error = errno;
    closedir(dir);
    return error ? reject(error) : 0;
}

static int source_in_namespace(bool create, struct droidloom_device_identity *out)
{
    int parent = directory(SOURCE_PARENT);
    if (parent < 0)
        return -1;
    int target = directory(DROIDLOOM_DEVICE_SLOT);
    struct droidloom_device_identity base, source;
    struct statfs parent_fs;
    int error = 0;
    if (target < 0 || identity(parent, &base) || identity(target, &source) ||
        fstatfs(parent, &parent_fs) || empty(target))
        error = errno;
    else if ((unsigned long)parent_fs.f_type != TMPFS_MAGIC)
        error = EXDEV;
    if (!error && create) {
        if (base.mount != source.mount || base.device != source.device)
            error = EBUSY;
        else if (mount("droidloom-private-dev", DROIDLOOM_DEVICE_SLOT, "tmpfs",
                       MS_NOSUID | MS_NOEXEC,
                       "mode=0755,uid=0,gid=0,size=64m,nr_inodes=16384,huge=never,noswap"))
            error = errno;
        if (!error) {
            close(target);
            target = directory(DROIDLOOM_DEVICE_SLOT);
            if (target < 0 || identity(target, &source))
                error = errno;
        }
    }
    struct stat st;
    struct statfs fs;
    struct statvfs limits;
    if (!error && (fstat(target, &st) || fstatfs(target, &fs) || fstatvfs(target, &limits)
                   || empty(target)))
        error = errno;
    if (!error && (base.mount == source.mount || base.device == source.device || st.st_ino != 1
                   || st.st_uid || st.st_gid || (st.st_mode & 07777) != 0755
                   || (unsigned long)fs.f_type != TMPFS_MAGIC
                   || (limits.f_flag & (ST_NOSUID | ST_NOEXEC | ST_RDONLY | ST_NODEV)) != (ST_NOSUID | ST_NOEXEC)
                   || !limits.f_frsize || (64ULL << 20) % limits.f_frsize
                   || limits.f_blocks != (64ULL << 20) / limits.f_frsize || limits.f_files != 16384))
        error = ESTALE;
    close(parent);
    if (error) {
        if (target >= 0) close(target);
        return reject(error);
    }
    *out = source;
    return target;
}

static int visit_device_source(int create, int bank, const char *cohort, struct droidloom_device_identity *out)
{
    if (!out || (create != 0 && create != 1) || geteuid() != 0)
        return reject(EINVAL);
    int host = open("/proc/self/ns/mnt", O_RDONLY | O_CLOEXEC);
    if (host < 0)
        return -1;
    int child = open(HANDOFF "/mntns", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    int user = open(HANDOFF "/userns", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    int owner = child >= 0 ? ioctl(child, NS_GET_USERNS) : -1;
    struct stat here, there, expected, actual;
    int error = 0, result = -1;
    if (child < 0 || user < 0 || owner < 0 || fstat(host, &here) || fstat(child, &there)
        || fstat(user, &expected) || fstat(owner, &actual))
        error = errno;
    else if (ioctl(child, NS_GET_NSTYPE) != CLONE_NEWNS || ioctl(user, NS_GET_NSTYPE) != CLONE_NEWUSER
             || (here.st_dev == there.st_dev && here.st_ino == there.st_ino)
             || expected.st_dev != actual.st_dev || expected.st_ino != actual.st_ino)
        error = ESTALE;
    else if (unshare(CLONE_FS) || setns(child, CLONE_NEWNS))
        error = errno;
    else {
        result = source_in_namespace(create != 0, out);
        if (result < 0)
            error = errno;
        else if (bank >= 0 && droidloom_populate_private_devices(result, bank, cohort) < 0) {
            error = errno;
            close(result);
            result = -1;
        }
        if (setns(host, CLONE_NEWNS)) {
            error = errno;
            if (result >= 0) close(result);
            result = -1;
        }
    }
    if (owner >= 0) close(owner);
    if (user >= 0) close(user);
    if (child >= 0) close(child);
    close(host);
    return error ? reject(error) : result;
}

int droidloom_hold_device_source(int create, struct droidloom_device_identity *out)
{
    return visit_device_source(create,-1,NULL,out);
}

int droidloom_prepare_device_source(int bank, const char *cohort, struct droidloom_device_identity *out)
{
    if (bank < 0)
        return reject(EBADF);
    return visit_device_source(0,bank,cohort,out);
}
