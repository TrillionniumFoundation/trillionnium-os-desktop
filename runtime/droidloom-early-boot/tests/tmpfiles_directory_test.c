// SPDX-License-Identifier: GPL-3.0-or-later
// Real private tmpfs/chroot checks. The selected SELinux policy is never loaded:
// a real raw xattr supplies the initial-context fixture before post-load checks.
#define _GNU_SOURCE
#include "../linux_run_label.c"
#include <assert.h>
#include <sched.h>

static unsigned checks;
static void expect_verify(const struct droidloom_linux_run *run,
                          const struct droidloom_linux_tmpfiles *held, bool okay)
{
    errno = 0;
    int rc = tmpfiles_verify(run, held, true, NULL);
    assert(okay ? rc == 0 : rc < 0);
    ++checks;
}
static void fresh(const struct droidloom_linux_run *run,
                  struct droidloom_linux_tmpfiles *held)
{
    *held = (struct droidloom_linux_tmpfiles){ .directory.fd = -1 };
    assert(droidloom_hold_linux_tmpfiles(run, held) == 0);
    assert(held->prepared);
    assert((fcntl(held->directory.fd, F_GETFL) & O_ACCMODE) == O_RDONLY);
    assert(fcntl(held->directory.fd, F_GETFD) & FD_CLOEXEC);
    expect_verify(run, held, true);
}
static void discard(struct droidloom_linux_tmpfiles *held)
{
    int fd = held->directory.fd;
    droidloom_close_linux_tmpfiles(held);
    assert(held->directory.fd == -1 && !held->prepared);
    assert(fcntl(fd, F_GETFD) < 0 && errno == EBADF);
    assert(rmdir("/run/tmpfiles.d") == 0);
    ++checks;
}
static void context_fixture(struct droidloom_linux_tmpfiles *held, const char *context)
{
    assert(fsetxattr(held->directory.fd, "security.selinux", context,
                     strlen(context) + 1, 0) == 0);
    /* Loading an initial policy gives the tmpfs inode its original SID without
     * modifying inode clocks. This maintenance kernel has no selected policy;
     * pin the actual post-fixture stat before exercising the production writer. */
    assert(fstat(held->directory.fd, &held->identity) == 0);
}

int main(int argc, char **argv)
{
    assert(argc == 2 && geteuid() == 0);
    struct stat root;
    assert(lstat(argv[1], &root) == 0 && S_ISDIR(root.st_mode) &&
           root.st_uid == 0 && root.st_gid == 0 && (root.st_mode & 07777) == 0700);
    assert(unshare(CLONE_NEWNS) == 0);
    assert(mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) == 0);
    assert(chdir(argv[1]) == 0 && chroot(".") == 0 && chdir("/") == 0);
    umask(0);
    assert(mkdir("/run", 0755) == 0);
    assert(mount("tmpfs", "/run", "tmpfs", MS_NOSUID | MS_NODEV | MS_NOEXEC,
                 "mode=0755,size=1m") == 0);
    struct droidloom_linux_run run = { .fd = -1 };
    assert(droidloom_hold_linux_run(&run) == 0);
    struct droidloom_linux_tmpfiles held = { .directory.fd = -1 };

    fresh(&run, &held);
    assert(droidloom_label_linux_tmpfiles(&run, &held) < 0 && errno == ENODATA);
    ++checks;
    context_fixture(&held, "u:object_r:tmpfs:s0");
    struct stat before = held.identity;
    assert(droidloom_label_linux_tmpfiles(&run, &held) == 0);
    assert(vt_same_inode(&before, &held.identity, false));
    assert(tmpfiles_label_kind(&held) == 1);
    expect_verify(&run, &held, true);
    before = held.identity;
    assert(droidloom_label_linux_tmpfiles(&run, &held) == 0);
    assert(vt_same_inode(&before, &held.identity, true));
    ++checks;
    discard(&held);

    // A second invocation cannot adopt any existing path, even one with exactly
    // the desired owner/mode/label. No existing content or metadata is changed.
    assert(mkdir("/run/tmpfiles.d", 0755) == 0);
    struct stat pre, post;
    assert(lstat("/run/tmpfiles.d", &pre) == 0);
    assert(droidloom_hold_linux_tmpfiles(&run, &held) < 0 && errno == EEXIST);
    assert(lstat("/run/tmpfiles.d", &post) == 0 && vt_same_inode(&pre, &post, true));
    assert(rmdir("/run/tmpfiles.d") == 0); ++checks;
    assert(symlink("/run", "/run/tmpfiles.d") == 0);
    assert(droidloom_hold_linux_tmpfiles(&run, &held) < 0 && errno == EEXIST);
    assert(unlink("/run/tmpfiles.d") == 0); ++checks;
    int file = open("/run/tmpfiles.d", O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    assert(file >= 0); close(file);
    assert(droidloom_hold_linux_tmpfiles(&run, &held) < 0 && errno == EEXIST);
    assert(unlink("/run/tmpfiles.d") == 0); ++checks;

    fresh(&run, &held);
    assert(fchmod(held.directory.fd, 0700) == 0);
    expect_verify(&run, &held, false); discard(&held);
    fresh(&run, &held);
    assert(fchown(held.directory.fd, 1, 0) == 0);
    expect_verify(&run, &held, false); discard(&held);
    fresh(&run, &held);
    assert(fchown(held.directory.fd, 0, 1) == 0);
    expect_verify(&run, &held, false); discard(&held);
    fresh(&run, &held);
    assert(fsetxattr(held.directory.fd, "user.foreign", "x", 1, 0) == 0);
    expect_verify(&run, &held, false);
    assert(fremovexattr(held.directory.fd, "user.foreign") == 0);
    expect_verify(&run, &held, false); discard(&held);
    fresh(&run, &held);
    file = openat(held.directory.fd, "foreign", O_CREAT | O_EXCL | O_WRONLY, 0600);
    assert(file >= 0); close(file);
    expect_verify(&run, &held, false);
    assert(unlinkat(held.directory.fd, "foreign", 0) == 0);
    expect_verify(&run, &held, false); discard(&held);

    fresh(&run, &held);
    assert(rename("/run/tmpfiles.d", "/run/retained") == 0);
    assert(mkdir("/run/tmpfiles.d", 0755) == 0);
    expect_verify(&run, &held, false);
    discard(&held);
    assert(rmdir("/run/retained") == 0);
    fresh(&run, &held);
    assert(rename("/run/tmpfiles.d", "/run/retained") == 0);
    assert(symlink("retained", "/run/tmpfiles.d") == 0);
    expect_verify(&run, &held, false);
    droidloom_close_linux_tmpfiles(&held);
    assert(unlink("/run/tmpfiles.d") == 0 && rmdir("/run/retained") == 0);

    assert(mkdir("/foreign", 0755) == 0);
    assert(mount("tmpfs", "/foreign", "tmpfs", MS_NOSUID | MS_NODEV | MS_NOEXEC,
                 "mode=0755,size=1m") == 0);
    fresh(&run, &held);
    assert(mount("/foreign", "/run/tmpfiles.d", NULL, MS_BIND, NULL) == 0);
    expect_verify(&run, &held, false);
    assert(umount("/run/tmpfiles.d") == 0);
    expect_verify(&run, &held, true);
    assert(mount("/foreign", "/run", NULL, MS_BIND, NULL) == 0);
    expect_verify(&run, &held, false);
    assert(umount("/run") == 0);
    expect_verify(&run, &held, true); discard(&held);

    fresh(&run, &held);
    context_fixture(&held, "u:object_r:p4_linux_rootdir_t:s0");
    assert(droidloom_label_linux_tmpfiles(&run, &held) < 0 && errno == EACCES);
    ++checks; discard(&held);
    fresh(&run, &held);
    context_fixture(&held, "u:object_r:tmpfs:s0");
    assert(fchmod(held.directory.fd, 0755) == 0);
    assert(droidloom_label_linux_tmpfiles(&run, &held) < 0);
    assert(tmpfiles_label_kind(&held) == 0);
    ++checks; discard(&held);

    assert(fchmod(run.fd, 0777) == 0);
    assert(droidloom_hold_linux_tmpfiles(&run, &held) < 0);
    assert(faccessat(run.fd, "tmpfiles.d", F_OK, AT_SYMLINK_NOFOLLOW) < 0 && errno == ENOENT);
    ++checks;
    assert(fchmod(run.fd, 0755) == 0);
    close(run.fd);
    printf("{\"tmpfiles_real_inode_checks\":%u,\"create_only\":true,"
           "\"private_mount_namespace\":true,\"initial_context_raw_xattr_fixture\":true,"
           "\"selected_policy_loaded\":false,\"runtime_qualified\":false}\n", checks);
    return 0;
}
