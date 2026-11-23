// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "board_resources.h"
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/mount.h>
#include <linux/nsfs.h>
#include <linux/openat2.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static int reject(int reason) {
    errno = reason;
    return -1;
}

static int under(int parent, const char *name, int flags) {
    struct open_how how = {
        .flags = (uint64_t)(flags | O_CLOEXEC),
        .resolve = RESOLVE_BENEATH | RESOLVE_NO_MAGICLINKS | RESOLVE_NO_SYMLINKS,
    };
    return (int)syscall(SYS_openat2, parent, name, &how, sizeof(how));
}

static bool same_inode(int left, int right) {
    struct stat a, b;
    return fstat(left, &a) == 0 && fstat(right, &b) == 0 &&
           a.st_dev == b.st_dev && a.st_ino == b.st_ino;
}

static bool distinct_inode(int left, int right) {
    struct stat a, b;
    return fstat(left, &a) == 0 && fstat(right, &b) == 0 &&
           (a.st_dev != b.st_dev || a.st_ino != b.st_ino);
}

static bool same_mount_root(int left, int right) {
    struct statx a, b;
    return same_inode(left, right) &&
           statx(left, "", AT_EMPTY_PATH, STATX_MNT_ID, &a) == 0 &&
           statx(right, "", AT_EMPTY_PATH, STATX_MNT_ID, &b) == 0 &&
           (a.stx_mask & STATX_MNT_ID) && (b.stx_mask & STATX_MNT_ID) &&
           a.stx_mnt_id == b.stx_mnt_id;
}

static int namespace_type(int fd, int expected) {
    struct statfs fs;
    if (fstatfs(fd, &fs) < 0) return -1;
    if (fs.f_type != NSFS_MAGIC || ioctl(fd, NS_GET_NSTYPE) != expected)
        return reject(ESTALE);
    return 0;
}

static int original_init(int root) {
    int fd = under(root, "system/bin/init", O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return -1;
    struct stat info;
    Elf64_Ehdr elf;
    bool valid = fstat(fd, &info) == 0 && S_ISREG(info.st_mode) &&
                 (info.st_mode & 0111) && !(info.st_mode & 0022) &&
                 pread(fd, &elf, sizeof(elf), 0) == sizeof(elf) &&
                 !memcmp(elf.e_ident, ELFMAG, SELFMAG) &&
                 elf.e_ident[EI_CLASS] == ELFCLASS64 && elf.e_ident[EI_DATA] == ELFDATA2LSB &&
                 elf.e_machine == EM_X86_64 && (elf.e_type == ET_DYN || elf.e_type == ET_EXEC);
    close(fd);
    return valid ? 0 : reject(ENOEXEC);
}

static int filesystem(int root, const char *name, long magic, unsigned long on,
                      unsigned long off, dev_t *device) {
    int fd = *name ? under(root, name, O_PATH | O_DIRECTORY) : fcntl(root, F_DUPFD_CLOEXEC, 3);
    if (fd < 0) return -1;
    struct statfs fs;
    struct statvfs mount;
    struct stat node;
    bool valid = fstatfs(fd, &fs) == 0 && fstatvfs(fd, &mount) == 0 &&
                 fstat(fd, &node) == 0 && S_ISDIR(node.st_mode) &&
                 fs.f_type == magic && (mount.f_flag & on) == on && !(mount.f_flag & off);
    if (valid && device) *device = node.st_dev;
    close(fd);
    return valid ? 0 : reject(ESTALE);
}

#include "board_binder.h"

/* The caller owns the manifest, protected storage lease and actual cgroup
 * delegation. Check the receiving layout again at the mount handoff. */
static int prepared_layout(int root) {
    static const char *const ro[] = {"", "vendor", "system/system_ext/lib64",
                                     "system/system_ext/bin", "system/system_ext/etc/init"};
    dev_t media[7];
    for (size_t i = 0; i < sizeof(ro)/sizeof(ro[0]); ++i)
        if (filesystem(root, ro[i], EXT4_SUPER_MAGIC, ST_RDONLY, 0, &media[i])) return -1;
    if (media[3] != media[4]) return reject(EXDEV);
    if (filesystem(root, "data", EXT4_SUPER_MAGIC, ST_NOSUID | ST_NODEV, ST_RDONLY, &media[5]) ||
        filesystem(root, "metadata", EXT4_SUPER_MAGIC, ST_NOSUID | ST_NODEV, ST_RDONLY, &media[6]))
        return -1;
    for (int i = 0; i < 7; ++i)
        for (int j = i + 1; j < 7; ++j)
            if (!(i == 3 && j == 4) && media[i] == media[j]) return reject(EXDEV);
    if (board_dev_state(root, false) ||
        filesystem(root, "sys/fs/cgroup", CGROUP2_SUPER_MAGIC, 0, ST_RDONLY, NULL))
        return -1;
    return original_init(root);
}

static int still_live(int pidfd) {
    struct pollfd check = {.fd = pidfd, .events = POLLIN};
    int n;
    do { n = poll(&check, 1, 0); } while (n < 0 && errno == EINTR);
    if (n < 0) return -1;
    return n == 0 ? 0 : reject(ESRCH);
}

static int slot_mount(int root, int child_root) {
    int parent = under(child_root, "run/droidloom-early-slot", O_PATH | O_DIRECTORY);
    if (parent < 0) return -1;
    int slot = under(parent, "rootfs", O_PATH | O_DIRECTORY);
    if (slot < 0) { int e=errno; close(parent); return reject(e); }
    int error = 0;
    if (!same_mount_root(root, slot)) {
        struct statfs fs;
        struct stat a, b;
        struct statx mx, my;
        if (fstatfs(parent,&fs) < 0 || fstat(parent,&a) < 0 || fstat(slot,&b) < 0 ||
            statx(parent,"",AT_EMPTY_PATH,STATX_MNT_ID,&mx) < 0 ||
            statx(slot,"",AT_EMPTY_PATH,STATX_MNT_ID,&my) < 0) error = errno;
        else if (fs.f_type != TMPFS_MAGIC || a.st_dev != b.st_dev ||
                 !(mx.stx_mask & STATX_MNT_ID) || !(my.stx_mask & STATX_MNT_ID) ||
                 mx.stx_mnt_id != my.stx_mnt_id || (a.st_mode & 0022) || (b.st_mode & 0022))
            error = EBUSY;
        else if (syscall(SYS_move_mount,root,"",slot,"",MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH) < 0)
            error = errno;
    }
    close(slot);
    if (!error) {
        slot = under(parent,"rootfs",O_PATH | O_DIRECTORY);
        if (slot < 0) error = errno;
        else {
            if (!same_mount_root(root,slot) || prepared_layout(slot)) error = ESTALE;
            close(slot);
        }
    }
    close(parent);
    return error ? reject(error) : 0;
}

/* Only the normal resource owner calls this with its live kernel-generation
 * descriptors. No namespace switch is made in the multithreaded manager.
 * No file descriptor is sent into the Android process. */
int droidloom_board_deliver_root(int pidfd, int userns, int mountns,
                                 int child_root, int detached_root) {
    if (geteuid() != 0) return reject(EPERM);
    if (still_live(pidfd) || namespace_type(userns,CLONE_NEWUSER) ||
        namespace_type(mountns,CLONE_NEWNS) || prepared_layout(detached_root)) return -1;
    int host_user = open("/proc/self/ns/user",O_RDONLY | O_CLOEXEC);
    int host_mount = open("/proc/self/ns/mnt",O_RDONLY | O_CLOEXEC);
    bool separate = host_user >= 0 && host_mount >= 0 && distinct_inode(userns,host_user) && distinct_inode(mountns,host_mount);
    if (host_user >= 0) close(host_user);
    if (host_mount >= 0) close(host_mount);
    if (!separate) return reject(EPERM);
    int status_pipe[2];
    if (pipe2(status_pipe,O_CLOEXEC)) return -1;
    pid_t worker = fork();
    if (worker == 0) {
        close(status_pipe[0]);
        int failure = 0;
        if (setns(mountns,CLONE_NEWNS) || still_live(pidfd) || slot_mount(detached_root,child_root))
            failure = errno;
        ssize_t sent;
        do {sent=write(status_pipe[1],&failure,sizeof(failure));} while (sent < 0 && errno == EINTR);
        _exit(sent == sizeof(failure) ? 0 : 1);
    }
    int error = worker < 0 ? errno : 0;
    close(status_pipe[1]);
    if (worker > 0) {
        int result=0, status=0;
        ssize_t n;
        do {n=read(status_pipe[0],&result,sizeof(result));} while (n < 0 && errno == EINTR);
        pid_t out;
        do {out=waitpid(worker,&status,0);} while (out < 0 && errno == EINTR);
        if (out != worker || !WIFEXITED(status) || WEXITSTATUS(status) || n != sizeof(result))
            error=EIO;
        else error=result;
    }
    close(status_pipe[0]);
    if (error) return reject(error);
    return still_live(pidfd);
}

/* Called by the original, still-private PID 1 after it has received the
 * generation-specific release notification and opened the newly visible root. */
int droidloom_board_enter(int held_root) {
    if (getpid()!=1 || geteuid()!=0) return reject(EPERM);
    if (prepared_layout(held_root)) return -1;
    int ns=open("/proc/self/ns/pid",O_RDONLY|O_CLOEXEC);
    if (ns<0 || namespace_type(ns,CLONE_NEWPID)) {
        int e=errno; if(ns>=0)close(ns);return reject(e);
    }
    if (fchdir(held_root) || mount(".","/",NULL,MS_MOVE,NULL) || chroot(".") || chdir("/")) {
        int e=errno;close(ns);return reject(e);
    }
    struct statfs fs;
    if(statfs("/proc",&fs)) {int e=errno;close(ns);return reject(e);}
    if(fs.f_type!=PROC_SUPER_MAGIC &&
       mount("proc","/proc","proc",MS_NOSUID|MS_NOEXEC|MS_NODEV,"hidepid=2,gid=3009")) {
        int e=errno;close(ns);return reject(e);
    }
    int inner=open("/proc/1/ns/pid",O_RDONLY|O_CLOEXEC);
    char self[32]={0};
    ssize_t n=readlink("/proc/self",self,sizeof(self)-1);
    bool own=inner>=0 && same_inode(ns,inner) && n==1 && self[0]=='1';
    if(inner>=0)close(inner);
    close(ns);
    return own ? board_build_binder(held_root) : reject(ESTALE);
}
