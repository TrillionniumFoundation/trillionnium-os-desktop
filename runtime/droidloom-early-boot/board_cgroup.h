// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_BOARD_CGROUP_H
#define DROIDLOOM_BOARD_CGROUP_H

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/mount.h>
#include <linux/openat2.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>
#include <unistd.h>

static inline int droidloom_cgroup_error(int error)
{
    errno = error;
    return -1;
}

static inline int droidloom_empty_sysfs_leaf(int fd)
{
    struct statfs fs;
    struct statvfs mount;
    const unsigned long required = ST_RDONLY | ST_NOSUID | ST_NODEV | ST_NOEXEC;
    if (fstatfs(fd, &fs) || fstatvfs(fd, &mount)) return -1;
    if (fs.f_type != SYSFS_MAGIC || (mount.f_flag & required) != required)
        return droidloom_cgroup_error(ESTALE);
    int copy = openat(fd, ".", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (copy < 0) return -1;
    DIR *stream = fdopendir(copy);
    if (!stream) {
        int error = errno; close(copy); return droidloom_cgroup_error(error);
    }
    errno = 0;
    struct dirent *entry;
    while ((entry = readdir(stream))) {
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) {
            errno = ENOTEMPTY;
            break;
        }
    }
    int error = errno;
    closedir(stream);
    return error ? droidloom_cgroup_error(error) : 0;
}

/* The initial-namespace resource owner reads the kernel's original directory
 * from a nonrecursive private sysfs clone. No part of that clone except the
 * verified leaf is ever attached to Android. */
static inline int droidloom_original_cgroup_leaf(void)
{
    int sys = open("/sys", O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (sys < 0) return -1;
    int base = -1, leaf = -1, owned = -1, error = 0;
    struct statfs fs;
    if (fstatfs(sys, &fs)) error = errno;
    else if (fs.f_type != SYSFS_MAGIC) error = ESTALE;
    else if ((base = (int)syscall(SYS_open_tree, sys, "",
                AT_EMPTY_PATH | OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC)) < 0) error = errno;
    close(sys);
    const struct mount_attr flags = {
        .attr_set = MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV | MOUNT_ATTR_NOEXEC
    };
    const struct open_how how = { .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
        .resolve = RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_XDEV };
    if (!error && syscall(SYS_mount_setattr, base, "", AT_EMPTY_PATH, &flags, sizeof(flags))) error = errno;
    if (!error && (leaf = (int)syscall(SYS_openat2, base, "fs/cgroup", &how, sizeof(how))) < 0) error = errno;
    if (!error && droidloom_empty_sysfs_leaf(leaf)) error = errno;
    /* The mount FD owns its anonymous namespace. Clone the selected leaf
     * while that FD is still live, before releasing the private /sys view. */
    if (!error && (owned = (int)syscall(SYS_open_tree, leaf, "",
                AT_EMPTY_PATH | OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC)) < 0) error = errno;
    if (leaf >= 0) close(leaf);
    if (base >= 0) close(base);
    return error ? droidloom_cgroup_error(error) : owned;
}

/* Once the complete root has been moved, the guest checks the kernel's
 * recorded bind root by mount ID in its own mount namespace. It needs no
 * access to the source host sysfs or its overmounted hierarchy. */
static inline int droidloom_check_visible_cgroup_origin(int leaf)
{
    struct statx st;
    if (statx(leaf, "", AT_EMPTY_PATH, STATX_MNT_ID_UNIQUE, &st)) return -1;
    if (!(st.stx_mask & STATX_MNT_ID_UNIQUE)) return droidloom_cgroup_error(ENOTSUP);
    const struct mnt_id_req req = {
        .size = MNT_ID_REQ_SIZE_VER0, .mnt_id = st.stx_mnt_id,
        .param = STATMOUNT_MNT_BASIC | STATMOUNT_MNT_ROOT
    };
    union { struct statmount align; unsigned char data[8192]; } buf = {0};
    if (syscall(SYS_statmount, &req, &buf, sizeof(buf), 0)) return -1;
    const struct statmount *m = &buf.align;
    size_t head = offsetof(struct statmount, str);
    if ((m->mask & req.param) != req.param || m->mnt_id != st.stx_mnt_id ||
        m->size < head || m->size > sizeof(buf) || m->mnt_root >= m->size - head)
        return droidloom_cgroup_error(ESTALE);
    const char *name = m->str + m->mnt_root;
    size_t limit = m->size - head - m->mnt_root;
    return limit >= sizeof("/fs/cgroup") && !memcmp(name, "/fs/cgroup", sizeof("/fs/cgroup"))
        ? 0 : droidloom_cgroup_error(ESTALE);
}

static inline int droidloom_admit_cgroup_mountpoint(int root, bool attached)
{
    const struct open_how how = { .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
        .resolve = RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS };
    int leaf = (int)syscall(SYS_openat2, root, "sys/fs/cgroup", &how, sizeof(how));
    if (leaf < 0) return -1;
    int error = 0;
    if (droidloom_empty_sysfs_leaf(leaf)) error = errno;
    if (!error && attached) {
        if (droidloom_check_visible_cgroup_origin(leaf)) error = errno;
    } else if (!error) {
        int original = droidloom_original_cgroup_leaf();
        if (original < 0) error = errno;
        else {
            struct stat a, b;
            if (fstat(leaf, &a) || fstat(original, &b)) error = errno;
            else if (a.st_dev != b.st_dev || a.st_ino != b.st_ino) error = ESTALE;
            close(original);
        }
    }
    close(leaf);
    return error ? droidloom_cgroup_error(error) : 0;
}
#endif
