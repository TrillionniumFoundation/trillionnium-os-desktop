// SPDX-License-Identifier: MPL-2.0
// Narrow owned-process regression derived from PR 257 commoncap probe.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static volatile unsigned public_sentinel = 0x5a17c0deU;
static unsigned failures;
struct report {
    pid_t pid;
    uid_t uid, euid;
    gid_t gid, egid;
    int target_fd, dumpable, nnp, setup_error;
    uint64_t effective, permitted;
    uintptr_t address;
};
static int exact(int fd, void *buffer, size_t length, int writing) {
    char *p = buffer;
    while (length) {
        ssize_t n = writing ? write(fd, p, length) : read(fd, p, length);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n; length -= (size_t)n;
    }
    return 0;
}
static int set_caps(uint32_t permitted) {
    struct __user_cap_header_struct h = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct c[2] = {{0}, {0}};
    c[0].permitted = permitted;
    return (int)syscall(SYS_capset, &h, c);
}
static void report_self(struct report *r) {
    struct __user_cap_header_struct h = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct c[2] = {{0}, {0}};
    if (syscall(SYS_capget, &h, c)) { r->setup_error = errno; return; }
    r->pid = getpid(); r->uid = getuid(); r->euid = geteuid();
    r->gid = getgid(); r->egid = getegid();
    r->effective = ((uint64_t)c[1].effective << 32) | c[0].effective;
    r->permitted = ((uint64_t)c[1].permitted << 32) | c[0].permitted;
    r->dumpable = prctl(PR_GET_DUMPABLE);
    r->nnp = prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L);
}
static int set_identity(uint32_t permitted) {
    if (prctl(PR_SET_KEEPCAPS, 1L) || setgroups(0, NULL) ||
        setresgid(60001, 60001, 60001) || setresuid(60001, 60001, 60001) ||
        set_caps(permitted) || prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) ||
        prctl(PR_SET_DUMPABLE, 1L)) return errno ? errno : EINVAL;
    return 0;
}
static int actor(int command, int reply) {
    alarm(20);
    struct report r = {0};
    r.setup_error = set_identity(1U << CAP_CHOWN);
    r.target_fd = open("/dev/null", O_RDONLY);
    r.address = (uintptr_t)&public_sentinel;
    if (r.target_fd < 0) r.setup_error = errno;
    for (;;) {
        report_self(&r);
        if (exact(reply, &r, sizeof(r), 1)) return 91;
        char c;
        if (exact(command, &c, 1, 0)) return 92;
        if (c == 'Q') { if (r.target_fd >= 0) close(r.target_fd); return 0; }
        if (c != 'D') return 93;
        if (set_caps(0) || prctl(PR_SET_DUMPABLE, 1L)) r.setup_error = errno;
    }
}
static void check(const char *name, int okay) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, okay ? "true" : "false");
    if (!okay) failures++;
}
static void operation(const char *stage, const char *name, long rc, int error, int denied) {
    int okay = denied ? rc < 0 && (error == EPERM || error == EACCES) : rc > 0;
    printf("{\"stage\":\"%s\",\"operation\":\"%s\",\"rc\":%ld,\"errno\":%d,\"denied_expected\":%s,\"passed\":%s}\n",
        stage, name, rc, error, denied ? "true" : "false", okay ? "true" : "false");
    if (!okay) failures++;
}
static void read_path(const char *stage, const char *name, const struct report *r, int denied) {
    char path[128]; snprintf(path, sizeof(path), "/proc/%d/%s", r->pid, name);
    errno = 0; int fd = open(path, O_RDONLY | O_CLOEXEC), error = errno;
    if (fd < 0) { operation(stage, name, -1, error, denied); return; }
    unsigned data = 0; errno = 0;
    ssize_t n = !strcmp(name, "mem") ? pread(fd, &data, sizeof(data), (off_t)r->address) : read(fd, &data, 1);
    error = errno; close(fd); operation(stage, name, n, error, denied);
    if (!strcmp(name, "mem") && n == (ssize_t)sizeof(data)) check("only_public_sentinel_read", data == public_sentinel);
}
static void paths(const char *stage, const struct report *r, int denied) {
    printf("{\"target_stage\":\"%s\",\"uid\":%u,\"effective\":%llu,\"permitted\":%llu,\"dumpable\":%d}\n",
        stage, r->uid, (unsigned long long)r->effective, (unsigned long long)r->permitted, r->dumpable);
    check("target_actual_identity_and_caps", !r->setup_error && r->uid == 60001 && r->euid == 60001 &&
        r->gid == 60001 && r->egid == 60001 && !r->effective && r->permitted == (uint64_t)denied && r->dumpable == 1 && r->nnp == 1);
    read_path(stage, "maps", r, denied);
}

int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(30);
    if (geteuid() != 0) { fprintf(stderr, "Root only for owned credential setup\n"); return 77; }
    printf("{\"suite\":\"owned-commoncap-v1\",\"maximum_live_children\":1,\"production_qualified\":false}\n");
    int command[2], reply[2]; if (pipe(command) || pipe(reply)) return 90;
    pid_t child = fork(); if (child < 0) return 90;
    if (!child) { close(command[1]); close(reply[0]); _exit(actor(command[0], reply[1])); }
    close(command[0]); close(reply[1]);
    struct report observer = {0}; observer.setup_error = set_identity(0); report_self(&observer);
    printf("{\"observer_uid\":%u,\"observer_euid\":%u,\"effective\":%llu,\"permitted\":%llu,\"nnp\":%d,\"setup_error\":%d}\n",
        observer.uid, observer.euid, (unsigned long long)observer.effective,
        (unsigned long long)observer.permitted, observer.nnp, observer.setup_error);
    check("observer_actual_caps0_nnp1", !observer.setup_error && observer.uid == 60001 && observer.euid == 60001 &&
        !observer.effective && !observer.permitted && observer.nnp == 1);
    int setup_failed = 0;
    for (int stage = 0; stage < 2; stage++) {
        struct report r;
        if (exact(reply[0], &r, sizeof(r), 0) || r.pid != child || r.setup_error) { setup_failed = 1; break; }
        paths(stage ? "same_permitted" : "target_extra_permitted", &r, !stage);
        char c = stage ? 'Q' : 'D';
        if (exact(command[1], &c, 1, 1)) { setup_failed = 1; break; }
    }
    if (setup_failed) { printf("{\"setup_unavailable\":true}\n"); kill(child, SIGKILL); }
    int status = -1; pid_t reaped; do { reaped = waitpid(child, &status, 0); } while (reaped < 0 && errno == EINTR);
    check("owned_child_reaped", reaped == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(command[1]); close(reply[0]);
    printf("{\"summary\":true,\"failures\":%u,\"setup_unavailable\":%s,\"all_children_reaped\":%s}\n",
        failures, setup_failed ? "true" : "false", reaped == child ? "true" : "false");
    return setup_failed ? 77 : failures ? 42 : 0;
}
