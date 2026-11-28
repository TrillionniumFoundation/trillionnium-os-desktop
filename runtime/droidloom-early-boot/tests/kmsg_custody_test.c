// SPDX-License-Identifier: GPL-3.0-or-later
// Build statically. Tests use a new private tmpfs, never a devtmpfs mount or
// any host device inode. All character-device operations are metadata-only.
#define _GNU_SOURCE
#include "../linux_run_label.c"
#include <assert.h>
#include <sched.h>
#include <sys/wait.h>

static unsigned checks;
static const struct {
    uint32_t version;
    struct { uint16_t tag, perm; uint32_t id; } entries[5];
} kmsg_acl = {2, {{1, 6, UINT32_MAX}, {2, 4, 1000}, {4, 4, UINT32_MAX},
                  {16, 4, UINT32_MAX}, {32, 4, UINT32_MAX}}};
static const unsigned char witness[] = {0, 7, 0, 255, 9, 1};

static void original_context(const char *context)
{
    assert(setxattr("/dev/kmsg", "security.selinux", context,
                    strlen(context) + 1, 0) == 0);
}

static void close_checked(struct linux_kmsg *held)
{
    int fds[] = {held->node, held->dev, held->proc_fds};
    for (size_t n = 0; n < 3; n++)
        assert(fds[n] >= 0 && (fcntl(fds[n], F_GETFD) & FD_CLOEXEC));
    kmsg_close(held);
    assert(held->node == -1 && held->dev == -1 && held->proc_fds == -1);
    for (size_t n = 0; n < 3; n++)
        assert(fcntl(fds[n], F_GETFD) == -1 && errno == EBADF);
    ++checks;
}

static void expect_hold_failure(void)
{
    struct linux_kmsg held = {.node = -1, .dev = -1, .proc_fds = -1};
    assert(kmsg_hold_original(&held) == -1);
    assert(errno == EACCES || errno == ELOOP);
    assert(held.node == -1 && held.dev == -1 && held.proc_fds == -1);
    ++checks;
}

static void expect_context(const char *wanted)
{
    char context[128];
    ssize_t size = getxattr("/dev/kmsg", "security.selinux", context, sizeof(context));
    assert(droidloom_context_matches(context, size, wanted));
    ++checks;
}

static int after_exec(void)
{
    assert(geteuid() == 0);
    for (int fd = 3; fd < 128; fd++)
        assert(fcntl(fd, F_GETFD) == -1 && errno == EBADF);
    struct stat original, after;
    assert(lstat("/dev/kmsg", &original) == 0);
    struct linux_kmsg held = {.node = -1, .dev = -1, .proc_fds = -1};
    assert(kmsg_hold_original(&held) == 0);
    assert(kmsg_relabel_held(&held) == 0);
    close_checked(&held);
    assert(lstat("/dev/kmsg", &after) == 0 && vt_same_inode(&original, &after, false));
    expect_context(linux_kmsg_context);
    unsigned char value[128];
    assert(getxattr("/dev/kmsg", "system.posix_acl_access", value, sizeof(value)) == sizeof(kmsg_acl));
    assert(memcmp(value, &kmsg_acl, sizeof(kmsg_acl)) == 0);
    assert(getxattr("/dev/kmsg", "trusted.droidloom_kmsg_test", value, sizeof(value)) == sizeof(witness));
    assert(memcmp(value, witness, sizeof(witness)) == 0);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--entry-guard") == 0) {
        assert(getpid() != 1);
        assert(droidloom_initialize_linux_kmsg() == -1 && errno == EPERM);
        puts("{\"non_pid1_entry_guard\":true,\"runtime_qualified\":false}");
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--after-exec") == 0)
        return after_exec();
    assert(argc == 2 && geteuid() == 0 && getpid() != 1);
    assert(droidloom_initialize_linux_kmsg() == -1 && errno == EPERM);
    ++checks;
    struct stat host_dev, host_kmsg;
    assert(lstat("/dev", &host_dev) == 0 && S_ISDIR(host_dev.st_mode));
    int host_kmsg_present = lstat("/dev/kmsg", &host_kmsg) == 0;
    assert(host_kmsg_present || errno == ENOENT);
    int executable = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    assert(executable >= 0 && executable < 128);
    struct stat root;
    struct statfs fs;
    assert(lstat(argv[1], &root) == 0 && S_ISDIR(root.st_mode));
    assert(root.st_uid == 0 && root.st_gid == 0 && (root.st_mode & 07777) == 0700);
    assert(statfs(argv[1], &fs) == 0 && fs.f_type == EXT4_SUPER_MAGIC);
    assert(unshare(CLONE_NEWNS) == 0);
    assert(mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) == 0);
    assert(chdir(argv[1]) == 0 && chroot(".") == 0 && chdir("/") == 0);
    umask(0);
    assert(mkdir("/dev", 0755) == 0 && mkdir("/proc", 0555) == 0);
    assert(mount("tmpfs", "/dev", "tmpfs", MS_NOSUID | MS_NOEXEC, "mode=0755,size=1m") == 0);
    assert(mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) == 0);
    assert(mknod("/dev/kmsg", S_IFCHR | 0644, makedev(1, 11)) == 0);
    assert(mknod("/kmsg-projection", S_IFCHR | 0600, makedev(1, 11)) == 0);
    struct stat private_dev, private_node, private_projection;
    assert(lstat("/dev", &private_dev) == 0 && private_dev.st_dev != host_dev.st_dev);
    assert(lstat("/dev/kmsg", &private_node) == 0 && private_node.st_dev == private_dev.st_dev);
    assert(lstat("/kmsg-projection", &private_projection) == 0);
    if (host_kmsg_present) {
        assert(private_node.st_dev != host_kmsg.st_dev || private_node.st_ino != host_kmsg.st_ino);
        assert(private_projection.st_dev != host_kmsg.st_dev || private_projection.st_ino != host_kmsg.st_ino);
    }
    checks += 3;

    assert(chmod("/dev/kmsg", 0600) == 0);
    expect_hold_failure();
    assert(chmod("/dev/kmsg", 0644) == 0);
    assert(chown("/dev/kmsg", 1, 0) == 0);
    expect_hold_failure();
    assert(chown("/dev/kmsg", 0, 1) == 0);
    expect_hold_failure();
    assert(chown("/dev/kmsg", 0, 0) == 0);
    assert(link("/dev/kmsg", "/dev/kmsg-extra") == 0);
    expect_hold_failure();
    assert(unlink("/dev/kmsg-extra") == 0);
    assert(unlink("/dev/kmsg") == 0);
    assert(mknod("/dev/kmsg", S_IFCHR | 0644, makedev(1, 3)) == 0);
    expect_hold_failure();
    assert(unlink("/dev/kmsg") == 0);
    int regular = open("/dev/kmsg", O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0644);
    assert(regular >= 0 && close(regular) == 0);
    expect_hold_failure();
    assert(unlink("/dev/kmsg") == 0);
    assert(symlink("/kmsg-projection", "/dev/kmsg") == 0);
    expect_hold_failure();
    assert(unlink("/dev/kmsg") == 0);
    assert(mknod("/dev/kmsg", S_IFCHR | 0644, makedev(1, 11)) == 0);

    struct linux_kmsg held = {.node = -1, .dev = -1, .proc_fds = -1};
    assert(kmsg_hold_original(&held) == 0);
    assert(kmsg_relabel_held(&held) == -1 && errno == ENODATA);
    close_checked(&held);
    original_context("u:object_r:kmsg_device:s0:c1");
    assert(kmsg_hold_original(&held) == 0);
    assert(kmsg_relabel_held(&held) == -1 && errno == EACCES);
    close_checked(&held);
    expect_context("u:object_r:kmsg_device:s0:c1");
    original_context(original_vt_context);

    assert(kmsg_hold_original(&held) == 0);
    assert(rename("/dev/kmsg", "/dev/kmsg-retained") == 0);
    assert(mknod("/dev/kmsg", S_IFCHR | 0644, makedev(1, 11)) == 0);
    assert(kmsg_relabel_held(&held) == -1 && errno == ESTALE);
    close_checked(&held);
    assert(unlink("/dev/kmsg") == 0);
    assert(rename("/dev/kmsg-retained", "/dev/kmsg") == 0);
    expect_context(original_vt_context);

    assert(kmsg_hold_original(&held) == 0);
    assert(mount("/kmsg-projection", "/dev/kmsg", NULL, MS_BIND, NULL) == 0);
    assert(kmsg_relabel_held(&held) == -1 && errno == EACCES);
    close_checked(&held);
    expect_hold_failure();
    assert(umount2("/dev/kmsg", 0) == 0);
    expect_context(original_vt_context);

    assert(setxattr("/dev/kmsg", "system.posix_acl_access", &kmsg_acl, sizeof(kmsg_acl), 0) == 0);
    assert(setxattr("/dev/kmsg", "trusted.droidloom_kmsg_test", witness, sizeof(witness), 0) == 0);
    assert(kmsg_hold_original(&held) == 0);
    assert(setxattr("/dev/kmsg", "trusted.droidloom_kmsg_test", "changed", 7, 0) == 0);
    assert(kmsg_relabel_held(&held) == -1 && errno == ESTALE);
    close_checked(&held);
    assert(setxattr("/dev/kmsg", "trusted.droidloom_kmsg_test", witness, sizeof(witness), 0) == 0);

    /* No device handle is inherited: the child executes first, then acquires
     * the original pathname afresh, as FINISH does after its SID transition. */
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        char *const args[] = {"kmsg-custody-test", "--after-exec", NULL};
        char *const environment[] = {"LC_ALL=C", NULL};
        execveat(executable, "", args, environment, AT_EMPTY_PATH);
        _exit(127);
    }
    int status;
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(executable);
    ++checks;
    struct stat before, after;
    assert(lstat("/dev/kmsg", &before) == 0);
    assert(kmsg_hold_original(&held) == 0 && kmsg_relabel_held(&held) == 0);
    close_checked(&held);
    assert(lstat("/dev/kmsg", &after) == 0 && vt_same_inode(&before, &after, true));
    expect_context(linux_kmsg_context);
    printf("{\"checks\":%u,\"fresh_acquisition_after_self_exec\":true,\"inherited_device_fds\":0,"
           "\"inode_and_acl_preserved\":true,\"device_bodies_opened\":false,"
           "\"private_mount_namespace\":true,\"private_tmpfs_distinct_from_host_dev\":true,"
           "\"runtime_qualified\":false}\n", checks);
    return 0;
}
