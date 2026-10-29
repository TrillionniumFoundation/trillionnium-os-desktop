// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <linux/capability.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

struct linux_attr {
    uint32_t size, policy;
    uint64_t flags;
    int32_t nice;
    uint32_t priority;
    uint64_t runtime, deadline, period;
    uint32_t util_min, util_max;
};
_Static_assert(sizeof(struct linux_attr) == 56, "Linux scheduling attribute ABI");
static int failures;
static void check(const char *actor, const char *name, int ok) {
    printf("{\"case\":\"policy_%s_%s\",\"passed\":%s}\n", actor, name, ok ? "true" : "false");
    failures += !ok;
}
static int join(pid_t pid) {
    int status;
    return waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
static int get_attr(pid_t target, struct linux_attr *attr) {
    memset(attr, 0, sizeof(*attr));
    return syscall(SYS_sched_getattr, target, attr, sizeof(*attr), 0);
}
static int change(pid_t target, int op) {
    struct sched_param param = { .sched_priority = 0 };
    struct linux_attr attr = { .size = sizeof(attr), .policy = SCHED_OTHER, .nice = 8 };
    if (op == 0) return sched_setscheduler(target, SCHED_OTHER, &param);
    if (op == 1) return syscall(SYS_sched_setattr, target, &attr, 0);
    return sched_setparam(target, &param);
}
static const char *names[] = { "setscheduler", "setattr", "setparam" };
static void exercise(pid_t target, const char *actor, int expected_errno) {
    struct sched_param param;
    struct linux_attr before, after;
    int readable = sched_getscheduler(target) >= 0 && !sched_getparam(target, &param) && !get_attr(target, &before);
    check(actor, "foreign_getters_readable", readable);
    if (!readable) return;
    for (int op = 0; op < 3; ++op) {
        if (get_attr(target, &before)) _exit(80);
        errno = 0;
        int rc = change(target, op), saved = errno;
        int ok = expected_errno ? rc == -1 && saved == expected_errno : rc == 0;
        check(actor, names[op], ok);
        if (expected_errno) {
            if (get_attr(target, &after)) _exit(81);
            char label[80]; snprintf(label, sizeof(label), "%s_denied_state_unchanged", names[op]);
            check(actor, label, before.policy == after.policy && before.nice == after.nice && before.priority == after.priority);
        }
    }
}
static int actor(pid_t target, uid_t uid, int drop_caps, const char *label, int expected) {
    fflush(NULL);
    pid_t child = fork();
    if (child < 0) exit(77);
    if (!child) {
        if (uid && setresuid(uid, uid, uid)) _exit(82);
        if (drop_caps) {
            struct __user_cap_header_struct h = { .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0 };
            struct __user_cap_data_struct data[2] = {{0}, {0}};
            if (syscall(SYS_capset, &h, data)) _exit(83);
        }
        exercise(target, label, expected);
        _exit(failures ? 42 : 0);
    }
    return join(child);
}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(40);
    if (geteuid()) return 77;
    int ready[2], stop[2]; if (pipe(ready) || pipe(stop)) return 77;
    pid_t target = fork(); if (target < 0) return 77;
    if (!target) {
        close(ready[0]); close(stop[1]);
        if (setresuid(2001, 2001, 2001)) _exit(84);
        char byte;
        if (write(ready[1], "r", 1) != 1 || read(stop[0], &byte, 1) != 1) _exit(85);
        _exit(0);
    }
    close(ready[1]); close(stop[0]); char byte;
    if (read(ready[0], &byte, 1) != 1) return 77;
    close(ready[0]);
    exercise(target, "privileged", 0);
    int stranger = actor(target, 2002, 0, "different_uid", EPERM);
    int zero_caps = actor(target, 0, 1, "uid_zero_without_capability", EPERM);
    int same_owner = actor(target, 2001, 0, "same_owner", 0);
    if (write(stop[1], "s", 1) != 1) return 77;
    close(stop[1]);
    check("control", "owned_children_reaped", join(target) && stranger && zero_caps && same_owner);
    for (int op = 0; op < 3; ++op) {
        char label[80]; snprintf(label, sizeof(label), "%s_reaped_esrch", names[op]);
        errno = 0; int rc = change(target, op); check("control", label, rc == -1 && errno == ESRCH);
        snprintf(label, sizeof(label), "%s_negative_einval", names[op]);
        errno = 0; rc = change(-1, op); check("control", label, rc == -1 && errno == EINVAL);
    }
    return failures ? 42 : 0;
}
