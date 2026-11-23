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

static int apply_label_from(const struct droidloom_linux_run *run, const char *original, const char *expected)
{
    char context[128];
    ssize_t size = fgetxattr(run->fd, "security.selinux", context, sizeof(context));
    if (size < 0)
        return -1;
    if (!droidloom_context_matches(context, size, expected)) {
        if (!droidloom_context_matches(context, size, original)) {
            errno = EACCES;
            return -1;
        }
        if (fsetxattr(run->fd, "security.selinux", expected,
                      strlen(expected) + 1, 0) < 0)
            return -1;
    }
    return verify_label(run, expected);
}

static int apply_label(const struct droidloom_linux_run *run, const char *expected)
{
    return apply_label_from(run, "u:object_r:tmpfs:s0", expected);
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
    if (apply_label(&paths->readiness, "u:object_r:p4_linux_readiness_dir_t:s0") < 0)
        return -1;
    /* Mint this boot's request exactly once, before the ordinary system manager starts. */
    int fd = openat(paths->readiness.fd, "shutdown-request",
                    O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0640);
    if (fd < 0)
        return -1;
    struct stat file, parent;
    char label[100];
    const char expected[] = "u:object_r:p4_android_shutdown_request_t:s0";
    int e = 0;
    if (fchmod(fd, 0640) || fstat(fd, &file) || fstat(paths->readiness.fd, &parent))
        e = errno;
    else if (!S_ISREG(file.st_mode) || file.st_dev != parent.st_dev || file.st_uid != 0 ||
             file.st_gid != parent.st_gid || file.st_nlink != 1 || file.st_size ||
             (file.st_mode & 07777) != 0640 ||
             !droidloom_context_matches(label, fgetxattr(fd, "security.selinux", label, sizeof(label)), expected))
        e = ESTALE;
    else if (write(fd, "0", 1) != 1)
        e = errno ? errno : EIO;
    close(fd);
    if (e) { errno = e; return -1; }
    return 0;
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

static int hold_cgroup_inode(int fd, mode_t kind, struct droidloom_linux_run *out)
{
    if (fd < 0)
        return -1;
    struct stat st;
    struct statfs fs;
    int error = 0;
    if (fstat(fd, &st) < 0 || fstatfs(fd, &fs) < 0)
        error = errno;
    else if ((st.st_mode & S_IFMT) != kind || st.st_uid || st.st_gid ||
             (st.st_mode & 0022) || fs.f_type != CGROUP2_SUPER_MAGIC)
        error = EACCES;
    if (error) {
        close(fd);
        errno = error;
        return -1;
    }
    *out = (struct droidloom_linux_run){ .fd = fd, .device = st.st_dev, .inode = st.st_ino };
    return 0;
}

static int initial_cgroup_membership(void)
{
    char data[64];
    int fd = open("/proc/1/cgroup", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    ssize_t n;
    do { n = read(fd, data, sizeof(data) - 1); } while (n < 0 && errno == EINTR);
    int error = errno;
    close(fd);
    if (n < 0) {
        errno = error;
        return -1;
    }
    data[n] = 0;
    if (!strcmp(data, "0::/\n"))
        return 0;
    if (!strcmp(data, "0::/init.scope\n"))
        return 1;
    errno = EINVAL;
    return -1;
}

int droidloom_hold_linux_init_scope(struct droidloom_linux_init_scope *held)
{
    const int dir = O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC;
    int membership = initial_cgroup_membership();
    if (membership < 0 || getpid() != 1)
        return -1;
    if (hold_cgroup_inode(open("/sys/fs/cgroup", dir), S_IFDIR, &held->root) < 0)
        return -1;
    if (held->root.inode != 1) {
        errno = ESTALE;
        return -1;
    }
    if (hold_cgroup_inode(openat(held->root.fd, "cgroup.procs", O_RDONLY | O_NOFOLLOW | O_CLOEXEC),
                          S_IFREG, &held->root_membership) < 0)
        return -1;
    if (held->root_membership.device != held->root.device || held->root_membership.inode == held->root.inode) {
        errno = ESTALE;
        return -1;
    }
    if (mkdirat(held->root.fd, "system.slice", 0755) < 0 && errno != EEXIST)
        return -1;
    if (hold_cgroup_inode(openat(held->root.fd, "system.slice", dir), S_IFDIR, &held->system_slice) < 0)
        return -1;
    if (held->system_slice.device != held->root.device || held->system_slice.inode == held->root.inode) {
        errno = EXDEV;
        return -1;
    }
    if (mkdirat(held->root.fd, "init.scope", 0755) < 0 && errno != EEXIST)
        return -1;
    if (hold_cgroup_inode(openat(held->root.fd, "init.scope", dir),
                          S_IFDIR, &held->scope) < 0 ||
        hold_cgroup_inode(openat(held->root.fd, "cgroup.controllers", O_RDONLY | O_NOFOLLOW | O_CLOEXEC),
                          S_IFREG, &held->controllers) < 0 ||
        hold_cgroup_inode(openat(held->scope.fd, "cgroup.procs", O_RDONLY | O_NOFOLLOW | O_CLOEXEC),
                          S_IFREG, &held->procs) < 0)
        return -1;
    if (held->root.device != held->scope.device || held->root.device != held->procs.device ||
        held->root.device != held->controllers.device ||
        held->root.inode == held->scope.inode || held->scope.inode == held->procs.inode) {
        errno = EXDEV;
        return -1;
    }
    if (!membership) {
        /* Moving only this verified global Linux PID 1 avoids giving future
         * managers arbitrary task migration through the root cgroup.procs. */
        int fd = openat(held->scope.fd, "cgroup.procs", O_WRONLY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0)
            return -1;
        struct stat original;
        int error = 0;
        if (fstat(fd, &original) < 0)
            error = errno;
        else if (original.st_dev != held->procs.device || original.st_ino != held->procs.inode)
            error = ESTALE;
        else if (write(fd, "0\n", 2) != 2)
            error = errno ? errno : EIO;
        close(fd);
        if (error) {
            errno = error;
            return -1;
        }
    }
    if (initial_cgroup_membership() != 1) {
        errno = ESTALE;
        return -1;
    }
    return 0;
}

int droidloom_label_linux_init_scope(const struct droidloom_linux_init_scope *held)
{
    const char *original = "u:object_r:cgroup_v2:s0";
    if (apply_label_from(&held->root, original, "u:object_r:p4_linux_cgroup_root_t:s0") < 0 ||
        apply_label_from(&held->root_membership, original, "u:object_r:p4_linux_cgroup_root_membership_t:s0") < 0 ||
        apply_label_from(&held->scope, original, "u:object_r:p4_linux_cgroup_init_scope_t:s0") < 0 ||
        verify_label(&held->system_slice, "u:object_r:p4_linux_system_slice_t:s0") < 0 ||
        apply_label_from(&held->controllers, original, "u:object_r:p4_linux_cgroup_controller_list_t:s0") < 0 ||
        apply_label_from(&held->procs, original, "u:object_r:p4_linux_cgroup_init_tasks_t:s0") < 0)
        return -1;
    return 0;
}

void droidloom_close_linux_init_scope(struct droidloom_linux_init_scope *held)
{
    if (held->root_membership.fd >= 0)
        close(held->root_membership.fd);
    if (held->system_slice.fd >= 0)
        close(held->system_slice.fd);
    if (held->controllers.fd >= 0)
        close(held->controllers.fd);
    if (held->procs.fd >= 0)
        close(held->procs.fd);
    if (held->scope.fd >= 0)
        close(held->scope.fd);
    if (held->root.fd >= 0)
        close(held->root.fd);
}
