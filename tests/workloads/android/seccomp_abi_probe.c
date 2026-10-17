// SPDX-License-Identifier: MIT
// A08 minimal seccomp syscall ABI probe, safe on a disposable host: filter lives
// only in a short-lived forked child. A passing Linux host probe does NOT
// qualify Android on Asterinas or prove TSYNC across sibling threads.
#define _GNU_SOURCE
#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/audit.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static void result(const char *name, const char *status, int err) {
    printf("%s\t%s\terrno=%d\n", name, status, err);
}
int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
#ifndef SYS_seccomp
    result("seccomp_syscall_available", "UNSUPPORTED_BUILD", 0);
    return 77;
#else
    pid_t child = fork();
    if (child < 0) { result("fork", "FAIL", errno); return 1; }
    if (child == 0) {
        if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) {
            result("no_new_privs", "FAIL", errno); _exit(11);
        }
        if (prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1) {
            result("get_no_new_privs", "FAIL", errno); _exit(12);
        }
        result("no_new_privs", "PASS", 0);
        struct sock_filter filter[] = {
            BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                     (unsigned int)offsetof(struct seccomp_data, nr)),
            BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_getpid, 0, 1),
            BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
            BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        };
        struct sock_fprog prog = {
            .len = (unsigned short)(sizeof(filter) / sizeof(filter[0])),
            .filter = filter,
        };
        if (syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, 0, &prog) != 0) {
            result("seccomp_filter_install", "FAIL", errno); _exit(13);
        }
        result("seccomp_filter_install", "PASS", 0);
        errno = 0;
        long banned = syscall(SYS_getpid);
        int banned_errno = errno;
        if (banned != -1 || banned_errno != EPERM) {
            result("seccomp_deny_getpid", "FAIL", banned_errno); _exit(14);
        }
        result("seccomp_deny_getpid", "PASS", 0);
        errno = 0;
        long permitted = syscall(SYS_getppid);
        if (permitted <= 0) {
            result("seccomp_allow_getppid", "FAIL", errno); _exit(15);
        }
        result("seccomp_allow_getppid", "PASS", 0);
        _exit(0);
    }
    int status = 0;
    if (waitpid(child, &status, 0) < 0) {
        result("child_wait", "FAIL", errno); return 1;
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        printf("seccomp_child\tFAIL\texit=%d\n", WIFEXITED(status) ? WEXITSTATUS(status) : -1);
        return 1;
    }
    puts("seccomp_child\tPASS\texit=0");
    puts("seccomp_TSYNC_multithread\tNOT_TESTED\terrno=0");
    puts("Android_process_filters\tNOT_TESTED\terrno=0");
    return 0;
#endif
}
