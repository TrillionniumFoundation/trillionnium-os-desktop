// SPDX-License-Identifier: GPL-3.0-or-later
// Run only under sudo unshare --mount --pid --fork. It creates an independent
// tmpfs over /dev in that private namespace, never mutates the host devtmpfs,
// never reads/writes kmsg contents, and never loads or changes a policy.
#include "../linux_run_label.c"
#include <stdlib.h>
#include <sys/wait.h>

static void check(bool passed, const char *name)
{
    if (!passed) {
        fprintf(stderr, "FAIL %s errno=%d\n", name, errno);
        exit(1);
    }
    printf("PASS %s\n", name);
}

static void fresh_node(unsigned int minor_number, mode_t mode)
{
    check(mknod("/dev/kmsg", S_IFCHR | mode, makedev(1, minor_number)) == 0,
          "private node created");
}

int main(void)
{
    check(getpid() == 1 && geteuid() == 0, "isolated PID 1");
    (void)umask(0);
    check(mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) == 0, "private mount namespace");
    check(mount("native-kmsg-test", "/dev", "tmpfs", MS_NOSUID | MS_NOEXEC,
                "mode=0755,size=1M") == 0, "independent test tmpfs");
    fresh_node(11, 0644);
    struct droidloom_linux_kmsg held;
    check(droidloom_hold_native_kmsg(&held) == 0 &&
          verify_native_kmsg(&held) == 0, "held exact original inode");
    check(droidloom_label_native_kmsg(&held) < 0,
          "unlabelled test filesystem cannot acquire production label");
    check(chmod("/dev/kmsg", 0600) == 0, "private mode changed");
    check(verify_native_kmsg(&held) < 0 && errno == ESTALE, "changed mode rejected");
    check(chmod("/dev/kmsg", 0644) == 0, "private mode restored");
    check(link("/dev/kmsg", "/dev/alias") == 0, "private alias created");
    check(verify_native_kmsg(&held) < 0 && errno == ESTALE, "hard-link alias rejected");
    check(unlink("/dev/alias") == 0, "private alias removed");
    check(mount("/dev/kmsg", "/dev/kmsg", NULL, MS_BIND, NULL) == 0,
          "same-inode private bind created");
    check(verify_native_kmsg(&held) < 0 && errno == ESTALE, "new binding mount rejected");
    check(umount2("/dev/kmsg", MNT_DETACH) == 0, "private bind removed");
    check(verify_native_kmsg(&held) == 0, "original binding restored");
    check(rename("/dev/kmsg", "/dev/old") == 0, "private old node moved");
    fresh_node(11, 0600);
    check(verify_native_kmsg(&held) < 0 && errno == ESTALE, "replaced pathname rejected");
    droidloom_close_native_kmsg(&held);
    check(held.dev.fd == -1 && held.node.fd == -1, "owned descriptors closed");
    check(unlink("/dev/kmsg") == 0, "private replacement removed");
    check(symlink("old", "/dev/kmsg") == 0, "private symlink created");
    check(droidloom_hold_native_kmsg(&held) < 0, "symlink rejected");
    check(unlink("/dev/kmsg") == 0, "private symlink removed");
    fresh_node(3, 0600);
    check(droidloom_hold_native_kmsg(&held) < 0 && errno == ESTALE, "wrong device rejected");
    pid_t child = fork();
    check(child >= 0, "namespace child created");
    if (child == 0) {
        int result = droidloom_hold_native_kmsg(&held);
        _exit(result == -1 && errno == EPERM ? 0 : 1);
    }
    int status;
    check(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "non-PID1 caller rejected");
    puts("RESULT {\"passed\":true,\"production_label_tested\":false,\"read_or_wrote_kmsg\":false}");
    return 0;
}
