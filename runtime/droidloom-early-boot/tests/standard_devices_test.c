// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the production O_PATH admission against real ext4 and private tmpfs
// device inodes. No character device body is opened; no host mount is changed.
#define _GNU_SOURCE
#include "../linux_run_label.c"
#include <assert.h>
#include <sched.h>
#include <stdlib.h>

static unsigned checks;
static void expect_node(const struct console_node *node, bool backing, bool okay)
{
    struct stat st;
    errno = 0;
    int fd = open_standard_node(node, backing, &st);
    if (okay) {
        assert(fd >= 0);
        assert((fcntl(fd, F_GETFL) & O_PATH) == O_PATH);
        assert(fcntl(fd, F_GETFD) & FD_CLOEXEC);
        close(fd);
    } else {
        assert(fd == -1);
        assert(errno == EACCES || errno == ELOOP);
    }
    ++checks;
}


static void expect_vt(int dev, uint64_t mount, size_t index, bool okay)
{
    struct stat st;
    errno = 0;
    int fd = vt_admit_node(dev, mount, index, &st);
    if (okay) {
        assert(fd >= 0);
        assert((fcntl(fd, F_GETFL) & O_PATH) == O_PATH);
        assert(fcntl(fd, F_GETFD) & FD_CLOEXEC);
        close(fd);
    } else {
        assert(fd == -1);
        assert(errno == EACCES || errno == ELOOP || errno == EINVAL);
    }
    ++checks;
}

static void fixed_vt_cases(void)
{
    assert(DROIDLOOM_LINUX_VT_COUNT == 65);
    int dev = vt_open_path(AT_FDCWD, "/dev", true);
    uint64_t mount_id;
    assert(dev >= 0 && vt_mount(dev, &mount_id) == 0);
    for (size_t n = 0; n < 65; n++) {
        char name[16];
        dev_t number;
        mode_t mode;
        assert(vt_name(n, name, &number, &mode) == 0);
        assert(number == (n == 0 ? makedev(5, 0) : makedev(4, n - 1)));
        assert(mode == (n == 0 ? 0666 : 0600));
        assert(mknodat(dev, name, S_IFCHR | mode, number) == 0);
        if (n & 1)
            assert(fchownat(dev, name, 0, 5, AT_SYMLINK_NOFOLLOW) == 0);
        expect_vt(dev, mount_id, n, true);
    }
    expect_vt(dev, mount_id, 65, false);
    expect_vt(dev, mount_id + 1, 1, false);
    assert(chmod("/dev/tty0", 0666) == 0);
    expect_vt(dev, mount_id, 1, false);
    assert(chmod("/dev/tty0", 0600) == 0);
    assert(chown("/dev/tty0", 1, 5) == 0);
    expect_vt(dev, mount_id, 1, false);
    assert(chown("/dev/tty0", 0, 6) == 0);
    expect_vt(dev, mount_id, 1, false);
    assert(chown("/dev/tty0", 0, 5) == 0);
    assert(link("/dev/tty0", "/dev/extra") == 0);
    expect_vt(dev, mount_id, 1, false);
    assert(unlink("/dev/extra") == 0);
    assert(unlink("/dev/tty0") == 0);
    assert(mknod("/dev/tty0", S_IFCHR | 0600, makedev(4, 64)) == 0);
    expect_vt(dev, mount_id, 1, false);
    assert(unlink("/dev/tty0") == 0);
    int regular = open("/dev/tty0", O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    assert(regular >= 0);
    close(regular);
    expect_vt(dev, mount_id, 1, false);
    assert(unlink("/dev/tty0") == 0 && symlink("tty1", "/dev/tty0") == 0);
    expect_vt(dev, mount_id, 1, false);
    assert(unlink("/dev/tty0") == 0);
    assert(mknod("/dev/tty0", S_IFCHR | 0600, makedev(4, 0)) == 0);
    assert(chown("/dev/tty0", 0, 5) == 0);
    assert(mknod("/tty0", S_IFCHR | 0600, makedev(4, 0)) == 0);
    int ext4 = vt_open_path(AT_FDCWD, "/", true);
    uint64_t ext4_mount;
    assert(ext4 >= 0 && vt_mount(ext4, &ext4_mount) == 0);
    expect_vt(ext4, ext4_mount, 1, false);
    close(ext4);
    close(dev);
    /* A named ACL whose mask keeps the admitted normal 0600 mode. The
     * production label operation must preserve these exact existing bytes. */
    struct {
        uint32_t version;
        struct { uint16_t tag, perm; uint32_t id; } entries[5];
    } acl = {2, {{1, 6, UINT32_MAX}, {2, 4, 1000}, {4, 0, UINT32_MAX},
                 {16, 0, UINT32_MAX}, {32, 0, UINT32_MAX}}};
    assert(setxattr("/dev/tty0", "system.posix_acl_access", &acl, sizeof(acl), 0) == 0);
    unsigned char acl_before[128], acl_after[128];
    ssize_t acl_size = getxattr("/dev/tty0", "system.posix_acl_access", acl_before, sizeof(acl_before));
    assert(acl_size == sizeof(acl));
    assert(mkdir("/proc", 0555) == 0);
    assert(mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) == 0);
    struct droidloom_linux_vts held = {.dev = -1, .proc_fds = -1};
    held.dev = vt_open_path(AT_FDCWD, "/dev", true);
    char path[64];
    (void)snprintf(path, sizeof(path), "/proc/%ld/fd", (long)getpid());
    held.proc_fds = vt_open_path(AT_FDCWD, path, true);
    assert(held.dev >= 0 && held.proc_fds >= 0);
    assert(fstat(held.dev, &held.dev_identity) == 0);
    assert(fstat(held.proc_fds, &held.proc_identity) == 0);
    assert(vt_mount(held.dev, &held.dev_mount) == 0);
    assert(vt_mount(held.proc_fds, &held.proc_mount) == 0);
    for (size_t n = 0; n < 65; n++) {
        held.nodes[n].fd = vt_admit_node(held.dev, held.dev_mount, n, &held.nodes[n].identity);
        assert(held.nodes[n].fd >= 0);
        held.held_count++;
        int initial_kind = vt_label_kind(&held, n);
        if (initial_kind != 0) {
            fprintf(stderr, "VT first raw read index=%zu kind=%d errno=%d\n", n, initial_kind, errno);
            struct stat d, q, v;
            uint64_t dm, qm, vm;
            assert(fstat(held.dev, &d) == 0 && fstat(held.proc_fds, &q) == 0 &&
                   fstat(held.nodes[n].fd, &v) == 0);
            assert(vt_mount(held.dev, &dm) == 0 && vt_mount(held.proc_fds, &qm) == 0 &&
                   vt_mount(held.nodes[n].fd, &vm) == 0);
            fprintf(stderr, "matches dev=%d proc=%d node=%d mounts=%llu/%llu %llu/%llu %llu\n",
                vt_same_inode(&d, &held.dev_identity, true),
                vt_same_inode(&q, &held.proc_identity, true),
                vt_same_inode(&v, &held.nodes[n].identity, true),
                (unsigned long long)dm, (unsigned long long)held.dev_mount,
                (unsigned long long)qm, (unsigned long long)held.proc_mount,
                (unsigned long long)vm);
            fprintf(stderr, "proc before size=%lld links=%lu mode=%o uid=%u gid=%u ino=%lu c=%ld.%ld m=%ld.%ld; after size=%lld links=%lu mode=%o uid=%u gid=%u ino=%lu c=%ld.%ld m=%ld.%ld\n",
                (long long)held.proc_identity.st_size, (unsigned long)held.proc_identity.st_nlink,
                held.proc_identity.st_mode, held.proc_identity.st_uid, held.proc_identity.st_gid,
                (unsigned long)held.proc_identity.st_ino, held.proc_identity.st_ctim.tv_sec,
                held.proc_identity.st_ctim.tv_nsec, held.proc_identity.st_mtim.tv_sec,
                held.proc_identity.st_mtim.tv_nsec,
                (long long)q.st_size, (unsigned long)q.st_nlink, q.st_mode, q.st_uid, q.st_gid,
                (unsigned long)q.st_ino, q.st_ctim.tv_sec,q.st_ctim.tv_nsec,q.st_mtim.tv_sec,q.st_mtim.tv_nsec);
        }
        assert(initial_kind == 0);
    }
    for (size_t n = 0; n < 65; n++) {
        struct stat before = held.nodes[n].identity, after;
        assert(vt_raw_label(&held, n, true, NULL, 0) == 0);
        assert(vt_verify_held(&held, n, &before, false, &after) == 0);
        assert(vt_same_inode(&before, &after, false));
        held.nodes[n].identity = after;
        assert(vt_label_kind(&held, n) == 2);
        ++checks;
    }
    assert(getxattr("/dev/tty0", "system.posix_acl_access", acl_after, sizeof(acl_after)) == acl_size);
    assert(memcmp(acl_before, acl_after, (size_t)acl_size) == 0);
    ++checks;
    held.prepared = true;
    assert(droidloom_verify_linux_vts(&held) == 0);
    ++checks;
    int old = held.nodes[1].fd;
    held.nodes[1].fd = held.nodes[2].fd;
    assert(vt_label_kind(&held, 1) == -1 && errno == ESTALE);
    held.nodes[1].fd = old;
    ++checks;
    int proc = held.proc_fds;
    held.proc_fds = held.dev;
    assert(vt_label_kind(&held, 1) == -1 && errno == ESTALE);
    held.proc_fds = proc;
    ++checks;
    assert(rename("/dev/tty0", "/dev/tty0.retained") == 0);
    assert(mknod("/dev/tty0", S_IFCHR | 0600, makedev(4, 0)) == 0);
    assert(vt_label_kind(&held, 1) == -1 && errno == ESTALE);
    ++checks;
    int descriptors[67] = {held.dev, held.proc_fds};
    for (size_t n = 0; n < 65; n++)
        descriptors[n + 2] = held.nodes[n].fd;
    droidloom_close_linux_vts(&held);
    assert(!held.prepared && held.held_count == 0 && held.dev == -1 && held.proc_fds == -1);
    for (size_t n = 0; n < 67; n++)
        assert(fcntl(descriptors[n], F_GETFD) == -1 && errno == EBADF);
    ++checks;
}

int main(int argc, char **argv)
{
    assert(argc == 2 && geteuid() == 0);
    struct stat st;
    assert(lstat(argv[1], &st) == 0 && S_ISDIR(st.st_mode));
    assert(st.st_uid == 0 && st.st_gid == 0 && (st.st_mode & 07777) == 0700);
    struct statfs rootfs;
    assert(statfs(argv[1], &rootfs) == 0 &&
           (unsigned long)rootfs.f_type == EXT4_SUPER_MAGIC);
    assert(unshare(CLONE_NEWNS) == 0);
    assert(mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) == 0);
    assert(chdir(argv[1]) == 0 && chroot(".") == 0 && chdir("/") == 0);
    umask(0);
    const char *dirs[] = {"/dev", "/usr", "/usr/lib", "/usr/lib/droidloom",
        "/usr/lib/droidloom/production", "/usr/lib/droidloom/production/current",
        "/usr/lib/droidloom/production/current/board-devices"};
    for (size_t i = 0; i < sizeof(dirs)/sizeof(dirs[0]); ++i)
        assert(mkdir(dirs[i], 0755) == 0);
    assert(mount("tmpfs", "/dev", "tmpfs", MS_NOSUID | MS_NOEXEC,
                 "mode=0755,size=1m") == 0);
    assert(sizeof(board_nodes)/sizeof(board_nodes[0]) == 4);
    // These are the selected kernel/normal image's actual permissions,
    // independently specified from the projection's table.
    const mode_t source_modes[] = {0600, 0666, 0666, 0600};
    const mode_t target_modes[] = {0600, 0666, 0666, 0644};
    for (size_t i = 0; i < 4; ++i) {
        const struct console_node *n = &board_nodes[i];
        assert(mknod(n->source, S_IFCHR | source_modes[i],
                     makedev(n->major, n->minor)) == 0);
        assert(mknod(n->path, S_IFCHR | target_modes[i],
                     makedev(n->major, n->minor)) == 0);
        expect_node(n, true, true);
        expect_node(n, false, true);
    }
    const struct console_node *kmsg = &board_nodes[3];
    assert(chmod(kmsg->path, 0600) == 0);
    expect_node(kmsg, false, false);
    assert(chmod(kmsg->path, 0644) == 0);
    assert(chmod(kmsg->source, 0644) == 0);
    expect_node(kmsg, true, false);
    assert(chmod(kmsg->source, 0600) == 0);
    assert(chown(kmsg->path, 1, 0) == 0);
    expect_node(kmsg, false, false);
    assert(chown(kmsg->path, 0, 1) == 0);
    expect_node(kmsg, false, false);
    assert(chown(kmsg->path, 0, 0) == 0);
    struct console_node wrong_fs = *kmsg;
    wrong_fs.source = kmsg->path;
    expect_node(&wrong_fs, true, false);
    assert(unlink(kmsg->path) == 0);
    assert(mknod(kmsg->path, S_IFCHR | 0644, makedev(1, 3)) == 0);
    expect_node(kmsg, false, false);
    assert(unlink(kmsg->path) == 0);
    int fd = open(kmsg->path, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0644);
    assert(fd >= 0);
    close(fd);
    expect_node(kmsg, false, false);
    assert(unlink(kmsg->path) == 0);
    assert(symlink("/dev/null", kmsg->path) == 0);
    expect_node(kmsg, false, false);
    fixed_vt_cases();
    printf("{\"real_inode_admission_checks\":%u,\"device_bodies_opened\":false,"
           "\"private_mount_namespace\":true,\"fixed_linux_vt_nodes\":65,\"acl_bytes_preserved\":true,\"raw_label_readback_only\":true,\"runtime_qualified\":false}\n", checks);
    return 0;
}
