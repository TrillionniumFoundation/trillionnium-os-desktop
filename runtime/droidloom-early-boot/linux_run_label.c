// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "linux_run_label.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/mount.h>
#include <linux/magic.h>
#include <linux/mount.h>
#include <linux/openat2.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <stdbool.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
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

int droidloom_label_private_device(const struct droidloom_linux_run *held)
{
    return apply_label(held, "u:object_r:p4_linux_private_dev_root_t:s0");
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

struct console_node {
    const char *path;
    const char *source;
    unsigned int major;
    unsigned int minor;
    mode_t mode;
};

static const struct console_node board_nodes[] = {
    { "/dev/console", "/usr/lib/droidloom/production/current/board-devices/console", 5, 1, 0600 },
    { "/dev/null", "/usr/lib/droidloom/production/current/board-devices/null", 1, 3, 0666 },
    { "/dev/full", "/usr/lib/droidloom/production/current/board-devices/full", 1, 7, 0666 },
};

static int open_standard_node(const struct console_node *spec, bool backing, struct stat *st)
{
    struct open_how how = {
        .flags = O_PATH | O_CLOEXEC | O_NOFOLLOW,
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS,
    };
    int fd = (int)syscall(SYS_openat2, AT_FDCWD, backing ? spec->source : spec->path, &how, sizeof(how));
    if (fd < 0)
        return -1;
    struct stat root;
    struct statfs fs;
    int error = 0;
    if (stat("/", &root) < 0 || fstatfs(fd, &fs) < 0 || fstat(fd, st) < 0)
        error = errno;
    else if (st->st_uid != 0 || st->st_gid != 0 || !S_ISCHR(st->st_mode) ||
             (st->st_mode & 07777) != spec->mode || major(st->st_rdev) != spec->major ||
             minor(st->st_rdev) != spec->minor || (backing && root.st_dev != st->st_dev) ||
             (unsigned long)fs.f_type != (backing ? EXT4_SUPER_MAGIC : TMPFS_MAGIC))
        error = EACCES;
    if (error) {
        close(fd);
        errno = error;
        return -1;
    }
    return fd;
}

int droidloom_linux_console_descriptors(void)
{
    int fd = open("/dev/console", O_RDWR | O_NOCTTY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    struct stat state;
    int error = 0;
    if (fstat(fd, &state) < 0)
        error = errno;
    else if (!S_ISCHR(state.st_mode) || state.st_rdev != makedev(5, 1))
        error = ESTALE;
    for (int n = 0; n < 3 && !error; ++n) {
        if (dup2(fd, n) < 0 || fcntl(n, F_SETFD, 0) < 0)
            error = errno;
    }
    if (fd > 2)
        close(fd);
    if (error)
        errno = error;
    return error ? -1 : 0;
}

int droidloom_project_linux_standard_devices(void)
{
    enum { count = sizeof(board_nodes) / sizeof(board_nodes[0]) };
    int target[count], mount_fd[count];
    struct stat source[count];
    for (size_t i = 0; i < count; ++i)
        target[i] = mount_fd[i] = -1;
    size_t attached = 0;
    int error = 0;
    for (size_t i = 0; i < count && !error; ++i) {
        struct stat original;
        const struct console_node *n = &board_nodes[i];
        int fd = open_standard_node(n, true, &source[i]);
        if (fd < 0) {
            error = errno;
            break;
        }
        target[i] = open_standard_node(n, false, &original);
        if (target[i] < 0)
            error = errno;
        if (!error) {
            mount_fd[i] = (int)syscall(SYS_open_tree, fd, "", OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC | AT_EMPTY_PATH);
            if (mount_fd[i] < 0)
                error = errno;
        }
        if (!error) {
            struct mount_attr flags = { .attr_set = MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NOEXEC };
            if (syscall(SYS_mount_setattr, mount_fd[i], "", AT_EMPTY_PATH, &flags, sizeof(flags)) < 0)
                error = errno;
        }
        close(fd);
    }
    for (size_t i = 0; i < count && !error; ++i) {
        if (syscall(SYS_move_mount, mount_fd[i], "", target[i], "",
                    MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH) < 0) {
            error = errno;
            break;
        }
        ++attached;
        struct stat now;
        if (lstat(board_nodes[i].path, &now) < 0)
            error = errno;
        else if (now.st_dev != source[i].st_dev || now.st_ino != source[i].st_ino ||
                 now.st_rdev != source[i].st_rdev)
            error = ESTALE;
    }
    if (!error && droidloom_linux_console_descriptors() < 0)
        error = errno;
    if (error) {
        while (attached > 0) {
            size_t i = --attached;
            struct stat now;
            if (lstat(board_nodes[i].path, &now) == 0 &&
                now.st_dev == source[i].st_dev && now.st_ino == source[i].st_ino)
                (void)umount2(board_nodes[i].path, MNT_DETACH);
        }
    }
    for (size_t i = 0; i < count; ++i) {
        if (mount_fd[i] >= 0) close(mount_fd[i]);
        if (target[i] >= 0) close(target[i]);
    }
    if (error)
        errno = error;
    return error ? -1 : 0;
}

static int native_ubuntu_shm(int dev, int target)
{
    int context = (int)syscall(SYS_fsopen, "tmpfs", FSOPEN_CLOEXEC);
    if (context < 0)
        return -1;
    int tree = -1, error = 0;
    if (syscall(SYS_fsconfig, context, FSCONFIG_SET_STRING, "mode", "01777", 0) < 0 ||
        syscall(SYS_fsconfig, context, FSCONFIG_CMD_CREATE, NULL, NULL, 0) < 0)
        error = errno;
    if (!error) {
        tree = (int)syscall(SYS_fsmount, context, FSMOUNT_CLOEXEC,
                           MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV | MOUNT_ATTR_STRICTATIME);
        if (tree < 0)
            error = errno;
    }
    if (!error && syscall(SYS_move_mount, tree, "", target, "",
                          MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH) < 0)
        error = errno;
    if (tree >= 0)
        close(tree);
    close(context);
    if (error) {
        errno = error;
        return -1;
    }
    return openat(dev, "shm", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
}

int droidloom_hold_linux_shm(struct droidloom_linux_run *out)
{
    /* Ubuntu systemd normally establishes this before starting any units.
     * The board performs that mount while still owning early host mounts. */
    int dev = open("/dev", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dev < 0)
        return -1;
    int root = -1, error = 0;
    struct stat parent, child;
    struct statfs fs;
    if (fstat(dev, &parent) < 0 || fstatfs(dev, &fs) < 0)
        error = errno;
    else if (parent.st_uid || parent.st_gid || (parent.st_mode & 0022) || fs.f_type != TMPFS_MAGIC)
        error = EACCES;
    if (!error && mkdirat(dev, "shm", 0755) < 0 && errno != EEXIST)
        error = errno;
    if (!error) {
        root = openat(dev, "shm", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (root < 0 || fstat(root, &child) < 0)
            error = errno;
    }
    if (!error && child.st_dev == parent.st_dev) {
        mode_t mode = child.st_mode & 07777;
        if (child.st_uid || child.st_gid || (mode != 0755 && mode != 01777))
            error = EACCES;
        else if (validate_empty_endpoint(root) < 0)
            error = errno;
        else {
            int mounted = native_ubuntu_shm(dev, root);
            if (mounted < 0)
                error = errno;
            close(root);
            root = mounted;
        }
    }
    if (!error && (fstat(root, &child) < 0 || fstatfs(root, &fs) < 0))
        error = errno;
    if (!error && (child.st_dev == parent.st_dev || child.st_ino != 1 || child.st_uid ||
        child.st_gid || (child.st_mode & 07777) != 01777 || fs.f_type != TMPFS_MAGIC ||
        (fs.f_flags & (ST_NODEV | ST_NOSUID)) != (ST_NODEV | ST_NOSUID) || (fs.f_flags & ST_RDONLY)))
        error = EACCES;
    if (!error && validate_empty_endpoint(root) < 0)
        error = errno;
    close(dev);
    if (error) {
        if (root >= 0)
            close(root);
        errno = error;
        return -1;
    }
    *out = (struct droidloom_linux_run){ .fd = root, .device = child.st_dev, .inode = child.st_ino };
    return 0;
}

int droidloom_label_linux_shm(const struct droidloom_linux_run *held)
{
    return apply_label(held, "u:object_r:p4_linux_shm_root_t:s0");
}
