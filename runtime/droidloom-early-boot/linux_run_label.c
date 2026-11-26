// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "linux_run_label.h"
#include "boot_diagnostics.h"
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
#include <stdio.h>
#include <sys/socket.h>
#include <sys/un.h>
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

static int hold_runtime_directory(const struct droidloom_linux_run *parent, const char *name,
                                  mode_t mode, struct droidloom_linux_run *held)
{
    mode_t saved_umask = umask(0);
    int rc = mkdirat(parent->fd, name, mode);
    int error = errno;
    umask(saved_umask);
    if (rc < 0 && error != EEXIST) {
        errno = error;
        return -1;
    }
    return hold_child(parent, name, 0, mode, held);
}

int droidloom_hold_ubuntu_log(const struct droidloom_linux_run *run,
                            struct droidloom_linux_journal_store *store)
{
    if (hold_runtime_directory(run, "log", 0755, &store->log) < 0)
        return -1;
    struct stat st;
    if (fstatat(store->log.fd, "journal", &st, AT_SYMLINK_NOFOLLOW) < 0)
        return errno == ENOENT ? 0 : -1;
    /* Ubuntu tmpfiles may already have assigned its local systemd-journal gid
     * and setgid bit. Keep that group, its ACL and any earlier journal data. */
    mode_t mode = st.st_mode & 07777;
    if (!S_ISDIR(st.st_mode) || st.st_uid != 0 || (mode != 0755 && mode != 02755)) {
        errno = EACCES;
        return -1;
    }
    return hold_child(&store->log, "journal", st.st_gid, mode, &store->journal);
}

int droidloom_label_ubuntu_log(const struct droidloom_linux_journal_store *store)
{
    if (apply_label(&store->log, "u:object_r:p4_linux_volatile_log_root_t:s0") < 0)
        return -1;
    if (store->journal.fd >= 0)
        return apply_label(&store->journal, "u:object_r:p4_linux_volatile_journal_store_t:s0");
    return 0;
}

void droidloom_close_ubuntu_log(struct droidloom_linux_journal_store *store)
{
    if (store->journal.fd >= 0)
        close(store->journal.fd);
    if (store->log.fd >= 0)
        close(store->log.fd);
}

int droidloom_hold_ubuntu_credentials(const struct droidloom_linux_run *run,
                                     struct droidloom_linux_credentials *credentials)
{
    /* Keep the distro's root-owned directories across initial policy load.
     * Linux PID 1 and its executor retain their original credential contents. */
    if (hold_runtime_directory(run, "credentials", 0755, &credentials->root) < 0 ||
        hold_runtime_directory(run, "systemd", 0755, &credentials->systemd) < 0)
        return -1;
    return hold_runtime_directory(&credentials->systemd, "temporary-credentials", 0700,
                                  &credentials->staging);
}

int droidloom_label_ubuntu_credentials(const struct droidloom_linux_credentials *credentials)
{
    if (apply_label(&credentials->root, "u:object_r:p4_linux_credentials_root_t:s0") < 0 ||
        apply_label(&credentials->systemd, "u:object_r:p4_linux_systemd_run_t:s0") < 0)
        return -1;
    return apply_label(&credentials->staging, "u:object_r:p4_linux_credential_staging_t:s0");
}

void droidloom_close_ubuntu_credentials(struct droidloom_linux_credentials *credentials)
{
    if (credentials->staging.fd >= 0)
        close(credentials->staging.fd);
    if (credentials->systemd.fd >= 0)
        close(credentials->systemd.fd);
    if (credentials->root.fd >= 0)
        close(credentials->root.fd);
}

/* Ubuntu's init-bottom/udev settles the queue and exits its daemon. On a
 * switch_root the two old filesystem socket names may survive on the moved
 * tmpfs. Release only a refused endpoint from that exact protected directory.
 * A live or busy listener retains ownership of its name. */
static int retire_inactive_udev_socket(int dir, const char *name, int kind)
{
    const struct open_how how = {
        .flags = O_PATH | O_NOFOLLOW | O_CLOEXEC,
        .resolve = RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_XDEV,
    };
    int held = (int)syscall(SYS_openat2, dir, name, &how, sizeof(how));
    if (held < 0)
        return errno == ENOENT ? 0 : -1;
    int error = 0;
    struct stat original, current;
    if (fstat(held, &original) < 0)
        error = errno;
    else if (!S_ISSOCK(original.st_mode) || original.st_uid != 0 ||
             original.st_gid != 0 || original.st_nlink != 1 ||
             ((original.st_mode & 07777) != 0600 &&
              !(kind == SOCK_SEQPACKET && (original.st_mode & 07777) == 0755))) {
        /* Standalone Ubuntu udevd binds its control socket with umask 022.
         * The varlink server and the systemd socket units specify 0600. */
        fprintf(stderr, "Unexpected Ubuntu udev endpoint %s mode=%o uid=%u gid=%u links=%lu\n",
                name, (unsigned)original.st_mode, (unsigned)original.st_uid,
                (unsigned)original.st_gid, (unsigned long)original.st_nlink);
        error = EACCES;
    }
    struct sockaddr_un addr = { .sun_family = AF_UNIX };
    int length = snprintf(addr.sun_path, sizeof(addr.sun_path), "/proc/self/fd/%d/%s", dir, name);
    if (length < 0 || (size_t)length >= sizeof(addr.sun_path))
        error = ENAMETOOLONG;
    if (!error) {
        int fd = socket(AF_UNIX, kind | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
        if (fd < 0)
            error = errno;
        else {
            int rc = connect(fd, (struct sockaddr *)&addr, sizeof(addr));
            int result = rc < 0 ? errno : 0;
            close(fd);
            if (result == ECONNREFUSED) {
                if (fstatat(dir, name, &current, AT_SYMLINK_NOFOLLOW) < 0)
                    error = errno == ENOENT ? 0 : errno;
                else if (original.st_dev != current.st_dev || original.st_ino != current.st_ino)
                    error = ESTALE;
                else if (unlinkat(dir, name, 0) < 0 && errno != ENOENT)
                    error = errno;
            } else if (result != 0 && result != ENOENT && result != EAGAIN &&
                       result != EINPROGRESS) {
                error = result;
            }
        }
    }
    close(held);
    if (error)
        errno = error;
    return error ? -1 : 0;
}

int droidloom_hold_linux_udev(const struct droidloom_linux_run *run, struct droidloom_linux_run *udev)
{
    if (mkdirat(run->fd, "udev", 0755) < 0 && errno != EEXIST)
        return -1;
    if (hold_child(run, "udev", 0, 0755, udev) < 0)
        return -1;
    if (retire_inactive_udev_socket(udev->fd, "control", SOCK_SEQPACKET) < 0)
        return -1;
    return retire_inactive_udev_socket(udev->fd, "io.systemd.Udev", SOCK_STREAM);
}

int droidloom_label_linux_udev(const struct droidloom_linux_run *udev)
{
    return apply_label(udev, "u:object_r:p4_linux_udev_run_t:s0");
}

int droidloom_hold_linux_udev_data(const struct droidloom_linux_run *udev,
                                  struct droidloom_linux_run *data)
{
    /* The distribution may have processed no devices in the initramfs yet. */
    if (hold_child(udev, "data", 0, 0755, data) < 0)
        return errno == ENOENT ? 0 : -1;
    return 0;
}

int droidloom_label_linux_udev_data(const struct droidloom_linux_run *data)
{
    if (data->fd < 0)
        return 0;
    return apply_label(data, "u:object_r:p4_linux_udev_state_t:s0");
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

static int label_instance_boot_slot(const struct droidloom_readiness_paths *paths) {
    int lock=openat(paths->handoff.fd,"startup.lock",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(lock<0)return -1;
    struct stat st;
    int e=0;
    if(fstat(lock,&st))e=errno;
    else if(!S_ISREG(st.st_mode)||st.st_uid||st.st_gid||st.st_nlink!=1||(st.st_mode&07777)!=0400)e=ESTALE;
    const char label[]="u:object_r:p4_linux_instance_lock_t:s0";
    if(!e&&fsetxattr(lock,"security.selinux",label,sizeof(label),0))e=errno;
    close(lock);
    const char *names[]={"/run/droidloom-early-slot","/run/droidloom-early/private-dev"};
    mode_t modes[]={0711,0700};
    for(unsigned i=0;!e&&i<2;i++){
        int fd=open(names[i],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        if(fd<0){e=errno;break;}
        struct droidloom_linux_run held={.fd=fd};
        if(fstat(fd,&st))e=errno;
        else if(!S_ISDIR(st.st_mode)||st.st_uid||st.st_gid||(st.st_mode&07777)!=modes[i])e=ESTALE;
        else {
            held.device=st.st_dev;held.inode=st.st_ino;
            if(apply_label(&held,"u:object_r:p4_linux_instance_slot_t:s0"))e=errno;
        }
        close(fd);
    }
    if(e){errno=e;return -1;}return 0;
}

int droidloom_label_readiness_paths(const struct droidloom_readiness_paths *paths)
{
    if(label_instance_boot_slot(paths))return -1;
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
    mode_t source_mode;
    mode_t target_mode;
};

static const struct console_node board_nodes[] = {
    { "/dev/console", "/usr/lib/droidloom/production/current/board-devices/console", 5, 1, 0600, 0600 },
    { "/dev/null", "/usr/lib/droidloom/production/current/board-devices/null", 1, 3, 0666, 0666 },
    { "/dev/full", "/usr/lib/droidloom/production/current/board-devices/full", 1, 7, 0666, 0666 },
    /* The selected Linux drivers/char/mem.c creates devtmpfs kmsg as 0644.
     * Its protected ext4 replacement remains 0600. Admit those two exact
     * metadata contracts independently before attaching the held source. */
    { "/dev/kmsg", "/usr/lib/droidloom/production/current/board-devices/kmsg", 1, 11, 0600, 0644 },
};

static void standard_device_failure(const struct console_node *spec, bool backing,
                                    const char *operation, const struct stat *st,
                                    const struct statfs *fs, int error)
{
    char stage[192];
    const char *path = backing ? spec->source : spec->path;
    if (st && fs)
        (void)snprintf(stage, sizeof(stage),
                       "%s %s %s uid=%lu gid=%lu mode=%#o dev=%u:%u fs=%#lx",
                       operation, backing ? "source" : "target", path,
                       (unsigned long)st->st_uid, (unsigned long)st->st_gid,
                       (unsigned int)(st->st_mode & 07777),
                       major(st->st_rdev), minor(st->st_rdev),
                       (unsigned long)fs->f_type);
    else
        (void)snprintf(stage, sizeof(stage), "%s %s %s",
                       operation, backing ? "source" : "target", path);
    droidloom_boot_diagnostics_report(DROIDLOOM_DIAGNOSTIC_POLICY, stage, error);
}

static int open_standard_node(const struct console_node *spec, bool backing, struct stat *st)
{
    struct open_how how = {
        .flags = O_PATH | O_CLOEXEC | O_NOFOLLOW,
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS,
    };
    int fd = (int)syscall(SYS_openat2, AT_FDCWD, backing ? spec->source : spec->path, &how, sizeof(how));
    if (fd < 0) {
        standard_device_failure(spec, backing, "open O_PATH", NULL, NULL, errno);
        return -1;
    }
    struct stat root;
    struct statfs fs;
    int error = 0;
    if (stat("/", &root) < 0 || fstatfs(fd, &fs) < 0 || fstat(fd, st) < 0) {
        error = errno;
        standard_device_failure(spec, backing, "read held metadata", NULL, NULL, error);
    } else if (st->st_uid != 0 || st->st_gid != 0 || !S_ISCHR(st->st_mode) ||
               (st->st_mode & 07777) != (backing ? spec->source_mode : spec->target_mode) ||
               major(st->st_rdev) != spec->major || minor(st->st_rdev) != spec->minor ||
               (backing && root.st_dev != st->st_dev) ||
               (unsigned long)fs.f_type != (backing ? EXT4_SUPER_MAGIC : TMPFS_MAGIC)) {
        error = EACCES;
        standard_device_failure(spec, backing, "validate held metadata", st, &fs, error);
    }
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
            if (mount_fd[i] < 0) {
                error = errno;
                standard_device_failure(n, true, "clone held mount", NULL, NULL, error);
            }
        }
        if (!error) {
            struct mount_attr flags = { .attr_set = MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NOEXEC };
            if (syscall(SYS_mount_setattr, mount_fd[i], "", AT_EMPTY_PATH, &flags, sizeof(flags)) < 0) {
                error = errno;
                standard_device_failure(n, true, "protect held mount", NULL, NULL, error);
            }
        }
        close(fd);
    }
    for (size_t i = 0; i < count && !error; ++i) {
        if (syscall(SYS_move_mount, mount_fd[i], "", target[i], "",
                    MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH) < 0) {
            error = errno;
            standard_device_failure(&board_nodes[i], false, "attach held mount", NULL, NULL, error);
            break;
        }
        ++attached;
        struct stat now;
        if (lstat(board_nodes[i].path, &now) < 0)
            error = errno;
        else if (now.st_dev != source[i].st_dev || now.st_ino != source[i].st_ino ||
                 now.st_rdev != source[i].st_rdev)
            error = ESTALE;
        if (error)
            standard_device_failure(&board_nodes[i], false, "read attached identity", NULL, NULL, error);
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


/* Fixed Linux VT inventory. These are the original writable devtmpfs inodes:
 * unlike the four protected standard devices, normal udev and logind must
 * retain their DAC/ACL and owner-management semantics. Never open device body. */
#ifndef STATX_MNT_ID_UNIQUE
#define STATX_MNT_ID_UNIQUE 0x4000U
#endif
#ifndef SYS_setxattrat
#define SYS_setxattrat 463
#endif
#ifndef SYS_getxattrat
#define SYS_getxattrat 464
#endif
static const char linux_vt_context[] = "u:object_r:p4_linux_console_vt_t:s0";
static const char original_vt_context[] = "u:object_r:device:s0";

struct vt_xattr_args {
    uint64_t value;
    uint32_t size;
    uint32_t flags;
};

static int vt_fail(int error)
{
    errno = error;
    return -1;
}

static int vt_name(size_t index, char name[16], dev_t *number, mode_t *mode)
{
    if (index >= DROIDLOOM_LINUX_VT_COUNT)
        return vt_fail(EINVAL);
    if (index == 0) {
        strcpy(name, "tty");
        *number = makedev(5, 0);
        *mode = 0666;
    } else {
        (void)snprintf(name, 16, "tty%u", (unsigned int)(index - 1));
        *number = makedev(4, index - 1);
        *mode = 0600;
    }
    return 0;
}

static int vt_mount(int fd, uint64_t *identity)
{
    struct statx st;
    if (statx(fd, "", AT_EMPTY_PATH | AT_SYMLINK_NOFOLLOW,
              STATX_MNT_ID_UNIQUE, &st) < 0)
        return -1;
    if (!(st.stx_mask & STATX_MNT_ID_UNIQUE))
        return vt_fail(EOPNOTSUPP);
    *identity = st.stx_mnt_id;
    return 0;
}

static bool vt_same_inode(const struct stat *a, const struct stat *b, bool same_ctime)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
           a->st_rdev == b->st_rdev && a->st_mode == b->st_mode &&
           a->st_uid == b->st_uid && a->st_gid == b->st_gid &&
           a->st_nlink == b->st_nlink && a->st_size == b->st_size &&
           a->st_mtim.tv_sec == b->st_mtim.tv_sec &&
           a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
           (!same_ctime || (a->st_ctim.tv_sec == b->st_ctim.tv_sec &&
                           a->st_ctim.tv_nsec == b->st_ctim.tv_nsec));
}

static bool vt_same_proc_directory(const struct stat *current, const struct stat *held)
{
    /* Selected 6.18 fs/proc/fd.c: proc_fd_getattr reports the current open-FD
     * count as st_size. Our own held/verification FDs necessarily change it.
     * Only this procfs directory has a dynamic size; retain every other F9
     * field and never use this exception for a device inode or /dev. */
    struct stat compared = *current;
    compared.st_size = held->st_size;
    return vt_same_inode(&compared, held, true);
}

static int vt_open_path(int parent, const char *name, bool directory)
{
    struct open_how how = {
        .flags = O_PATH | O_CLOEXEC | O_NOFOLLOW | (directory ? O_DIRECTORY : 0),
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS,
    };
    return (int)syscall(SYS_openat2, parent, name, &how, sizeof(how));
}

static int vt_admit_node(int dev, uint64_t dev_mount, size_t index, struct stat *st)
{
    char name[16];
    dev_t number;
    mode_t mode;
    if (vt_name(index, name, &number, &mode) < 0)
        return -1;
    int fd = vt_open_path(dev, name, false);
    if (fd < 0)
        return -1;
    struct stat parent;
    struct statfs fs;
    uint64_t mount;
    int error = 0;
    if (fstat(fd, st) < 0 || fstat(dev, &parent) < 0 || fstatfs(fd, &fs) < 0 ||
        vt_mount(fd, &mount) < 0)
        error = errno;
    /* The selected kernel initially creates root:root. The admitted distro
     * rule changes only group to tty(5), retaining exactly these two modes. */
    else if (!S_ISCHR(st->st_mode) || st->st_rdev != number ||
             (st->st_mode & 07777) != mode || st->st_uid != 0 ||
             (st->st_gid != 0 && st->st_gid != 5) || st->st_nlink != 1 ||
             st->st_size != 0 || st->st_dev != parent.st_dev ||
             mount != dev_mount || fs.f_type != TMPFS_MAGIC ||
             (fs.f_flags & ST_RDONLY))
        error = EACCES;
    if (error) {
        close(fd);
        return vt_fail(error);
    }
    return fd;
}

static int vt_verify_held(const struct droidloom_linux_vts *held, size_t index,
                          const struct stat *expected, bool same_ctime,
                          struct stat *current)
{
    struct stat parent, proc;
    struct statfs fs;
    uint64_t mount, proc_mount;
    if (fstat(held->dev, &parent) < 0 || fstat(held->proc_fds, &proc) < 0 ||
        fstatfs(held->proc_fds, &fs) < 0 || vt_mount(held->dev, &mount) < 0 ||
        vt_mount(held->proc_fds, &proc_mount) < 0)
        return -1;
    if (!vt_same_inode(&parent, &held->dev_identity, true) ||
        !vt_same_proc_directory(&proc, &held->proc_identity) ||
        mount != held->dev_mount || proc_mount != held->proc_mount ||
        fs.f_type != PROC_SUPER_MAGIC)
        return vt_fail(ESTALE);
    const struct droidloom_linux_vt *node = &held->nodes[index];
    struct stat named;
    int fd = vt_admit_node(held->dev, held->dev_mount, index, &named);
    if (fd < 0)
        return -1;
    int error = 0;
    if (fstat(node->fd, current) < 0 || vt_mount(node->fd, &mount) < 0)
        error = errno;
    else if (mount != held->dev_mount ||
             !vt_same_inode(current, expected, same_ctime) ||
             !vt_same_inode(&named, current, true))
        error = ESTALE;
    close(fd);
    return error ? vt_fail(error) : 0;
}

/* O_PATH deliberately cannot use fsetxattr. Follow only our own numeric
 * /proc/PID/fd entry through a held, verified procfs directory; prove that
 * second O_PATH resolves to the same inode and unique mount before and after
 * each raw xattr operation. No caller path, descriptor, key or label is used. */
static ssize_t vt_raw_label(const struct droidloom_linux_vts *held, size_t index,
                            bool write_label, char *value, size_t size)
{
    const struct droidloom_linux_vt *node = &held->nodes[index];
    struct stat before, duplicate, after;
    uint64_t mount;
    if (vt_verify_held(held, index, &node->identity, true, &before) < 0)
        return -1;
    char name[32];
    (void)snprintf(name, sizeof(name), "%d", node->fd);
    int fd = openat(held->proc_fds, name, O_PATH | O_CLOEXEC);
    if (fd < 0)
        return -1;
    int error = 0;
    if (fstat(fd, &duplicate) < 0 || vt_mount(fd, &mount) < 0)
        error = errno;
    else if (!vt_same_inode(&before, &duplicate, true) || mount != held->dev_mount)
        error = ESTALE;
    ssize_t result = -1;
    if (!error) {
        struct vt_xattr_args args = {
            .value = (uint64_t)(uintptr_t)(write_label ? linux_vt_context : value),
            .size = write_label ? sizeof(linux_vt_context) : size,
            .flags = 0,
        };
        result = syscall(write_label ? SYS_setxattrat : SYS_getxattrat,
                         held->proc_fds, name, 0U, "security.selinux", &args, sizeof(args));
        if (result < 0)
            error = errno;
    }
    int verified = vt_verify_held(held, index, &before, !write_label, &after);
    if (verified < 0)
        error = errno;
    if (fstat(fd, &duplicate) < 0 || vt_mount(fd, &mount) < 0)
        error = errno;
    else if (verified == 0 &&
             (!vt_same_inode(&after, &duplicate, true) || mount != held->dev_mount))
        error = ESTALE;
    close(fd);
    if (error)
        return vt_fail(error);
    return result;
}

static int vt_label_kind(const struct droidloom_linux_vts *held, size_t index)
{
    char label[128];
    ssize_t size = vt_raw_label(held, index, false, label, sizeof(label));
    if (size < 0)
        return -1; /* An initialized devtmpfs inode always has a real SID. */
    if (droidloom_context_matches(label, size, original_vt_context))
        return 1;
    if (droidloom_context_matches(label, size, linux_vt_context))
        return 2;
    return vt_fail(EACCES);
}

void droidloom_close_linux_vts(struct droidloom_linux_vts *held)
{
    for (size_t n = 0; n < held->held_count; n++) {
        if (held->nodes[n].fd >= 0)
            close(held->nodes[n].fd);
        held->nodes[n].fd = -1;
    }
    held->held_count = 0;
    if (held->proc_fds >= 0)
        close(held->proc_fds);
    if (held->dev >= 0)
        close(held->dev);
    held->proc_fds = held->dev = -1;
    held->prepared = false;
}

int droidloom_prepare_linux_vts(struct droidloom_linux_vts *held)
{
    /* FINISH is already p4_linux_early_t and verifies the current first-load
     * enforcing status and original namespaces before and after this whole
     * transaction. FS_USE_TRANS devtmpfs requires a post-load relabel. */
    if (getpid() != 1 || geteuid() != 0 || held->held_count ||
        held->dev != -1 || held->proc_fds != -1 || held->prepared)
        return vt_fail(EPERM);
    int error = 0;
    held->dev = vt_open_path(AT_FDCWD, "/dev", true);
    char path[64];
    (void)snprintf(path, sizeof(path), "/proc/%ld/fd", (long)getpid());
    held->proc_fds = vt_open_path(AT_FDCWD, path, true);
    struct statfs devfs, procfs;
    if (held->dev < 0 || held->proc_fds < 0 ||
        fstat(held->dev, &held->dev_identity) < 0 ||
        fstat(held->proc_fds, &held->proc_identity) < 0 ||
        fstatfs(held->dev, &devfs) < 0 || fstatfs(held->proc_fds, &procfs) < 0 ||
        vt_mount(held->dev, &held->dev_mount) < 0 ||
        vt_mount(held->proc_fds, &held->proc_mount) < 0)
        error = errno;
    else if (!S_ISDIR(held->dev_identity.st_mode) ||
             held->dev_identity.st_uid || held->dev_identity.st_gid ||
             (held->dev_identity.st_mode & 0022) || devfs.f_type != TMPFS_MAGIC ||
             (devfs.f_flags & ST_RDONLY) ||
             !S_ISDIR(held->proc_identity.st_mode) ||
             held->proc_identity.st_uid || held->proc_identity.st_gid ||
             (held->proc_identity.st_mode & 07777) != 0500 ||
             procfs.f_type != PROC_SUPER_MAGIC)
        error = EACCES;
    /* All 65 metadata and prior labels are admitted before the first write. */
    for (size_t n = 0; n < DROIDLOOM_LINUX_VT_COUNT && !error; n++) {
        struct droidloom_linux_vt *node = &held->nodes[n];
        node->fd = vt_admit_node(held->dev, held->dev_mount, n, &node->identity);
        if (node->fd < 0) {
            error = errno;
            break;
        }
        held->held_count++;
        node->label_kind = vt_label_kind(held, n);
        if (node->label_kind < 0)
            error = errno;
    }
    for (size_t n = 0; n < held->held_count && !error; n++) {
        struct droidloom_linux_vt *node = &held->nodes[n];
        int kind = vt_label_kind(held, n);
        if (kind < 0)
            error = errno;
        else if (kind != node->label_kind)
            error = ESTALE;
        else if (kind != 2) {
            struct stat after;
            if (vt_raw_label(held, n, true, NULL, 0) < 0 ||
                vt_verify_held(held, n, &node->identity, false, &after) < 0)
                error = errno;
            else
                node->identity = after; /* Only this xattr's ctime may differ. */
        }
        if (!error) {
            int result = vt_label_kind(held, n);
            if (result != 2)
                error = result < 0 ? errno : EACCES;
        }
    }
    if (!error)
        held->prepared = true;
    else {
        /* Any partial post-load relabel is fatal; never start systemd or
         * services from this transaction. Close every held descriptor. */
        droidloom_close_linux_vts(held);
        return vt_fail(error);
    }
    return 0;
}

int droidloom_verify_linux_vts(const struct droidloom_linux_vts *held)
{
    if (!held->prepared || held->held_count != DROIDLOOM_LINUX_VT_COUNT ||
        held->dev < 0 || held->proc_fds < 0)
        return vt_fail(EINVAL);
    /* The same post-load transaction reads each actual SELinux SID.
     * Reject invalid/unmapped labels and changed F9 before any service. */
    for (size_t n = 0; n < held->held_count; n++) {
        int result = vt_label_kind(held, n);
        if (result != 2)
            return vt_fail(result < 0 ? errno : EACCES);
    }
    return 0;
}

int droidloom_initialize_linux_vts(void)
{
    struct droidloom_linux_vts held = { .dev = -1, .proc_fds = -1 };
    int result = droidloom_prepare_linux_vts(&held);
    if (result == 0)
        result = droidloom_verify_linux_vts(&held);
    int error = errno;
    droidloom_close_linux_vts(&held);
    return result == 0 ? 0 : vt_fail(error);
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
        hold_cgroup_inode(openat(held->root.fd, "cgroup.subtree_control", O_RDONLY | O_NOFOLLOW | O_CLOEXEC),
                          S_IFREG, &held->root_subtree_control) < 0 ||
        hold_cgroup_inode(openat(held->scope.fd, "cgroup.procs", O_RDONLY | O_NOFOLLOW | O_CLOEXEC),
                          S_IFREG, &held->procs) < 0)
        return -1;
    if (held->root.device != held->scope.device || held->root.device != held->procs.device ||
        held->root.device != held->controllers.device ||
        held->root.device != held->root_subtree_control.device ||
        held->root_subtree_control.inode == held->root_membership.inode ||
        held->root_subtree_control.inode == held->controllers.inode ||
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
        verify_label(&held->scope, "u:object_r:p4_linux_cgroup_init_scope_t:s0") < 0 ||
        verify_label(&held->system_slice, "u:object_r:p4_linux_system_slice_t:s0") < 0 ||
        apply_label_from(&held->controllers, original, "u:object_r:p4_linux_cgroup_controller_list_t:s0") < 0 ||
        apply_label_from(&held->root_subtree_control, original, "u:object_r:p4_linux_cgroup_subtree_control_t:s0") < 0 ||
        verify_label(&held->procs, "u:object_r:p4_linux_cgroup_init_tasks_t:s0") < 0)
        return -1;
    return 0;
}

void droidloom_close_linux_init_scope(struct droidloom_linux_init_scope *held)
{
    if (held->root_subtree_control.fd >= 0)
        close(held->root_subtree_control.fd);
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
