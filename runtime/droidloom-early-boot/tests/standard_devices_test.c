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
    printf("{\"real_inode_admission_checks\":%u,\"device_bodies_opened\":false,"
           "\"private_mount_namespace\":true,\"runtime_qualified\":false}\n", checks);
    return 0;
}
