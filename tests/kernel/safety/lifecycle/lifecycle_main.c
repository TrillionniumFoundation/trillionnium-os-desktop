// SPDX-License-Identifier: MPL-2.0
#include "lifecycle_probe.h"
#include <sys/utsname.h>

unsigned failures;
int reset_policy;
void check(const char *name, long actual, long expected) {
    int okay = actual == expected;
    printf("{\"case\":\"%s\",\"actual\":%ld,\"expected\":%ld,\"passed\":%s}\n",
           name, actual, expected, okay ? "true" : "false");
    if (!okay) failures++;
}
void require(int okay, const char *name) { check(name, !!okay, 1); }
void exact(int fd, void *buffer, size_t length, int writing) {
    char *p = buffer;
    while (length) {
        ssize_t n = writing ? write(fd, p, length) : read(fd, p, length);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { perror("owned child protocol"); _exit(91); }
        p += n; length -= (size_t)n;
    }
}
void no_caps(void) {
    struct __user_cap_header_struct h = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct c[2] = {{0}, {0}};
    if (syscall(SYS_capset, &h, c) || syscall(SYS_capget, &h, c) ||
        c[0].effective || c[1].effective || c[0].permitted || c[1].permitted ||
        prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L)) _exit(92);
}
void bound_caps(void) {
    for (int cap = 0; cap <= 40; cap++) {
        if (prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) && errno != EINVAL) _exit(93);
    }
}
void unprivileged(uid_t r, uid_t e, uid_t s, gid_t gr, gid_t ge, gid_t gs) {
    bound_caps();
    if (setgroups(0, NULL) || setresgid(gr, ge, gs) || setresuid(r, e, s)) _exit(94);
    no_caps();
}
void reap(pid_t child, const char *name) {
    int status = -1;
    pid_t r;
    do { r = waitpid(child, &status, 0); } while (r < 0 && errno == EINTR);
    require(r == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, name);
}
static void run_owned(unsigned number) {
    pid_t child = fork();
    if (child < 0) { perror("bounded fork"); exit(95); }
    if (child == 0) {
        alarm(15);
        failures = 0;
        if (number < 14) credential_case(number);
        else {
            unprivileged(60001, 60001, 60001, 60001, 60001, 60001);
            printf("{\"observer_uid\":%u,\"observer_gid\":%u,\"cap_eff\":0,\"cap_prm\":0,\"nnp\":%d}\n",
                   getuid(), getgid(), prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L));
            local_lifecycle();
            sensitive_paths();
        }
        _exit(failures ? 42 : 0);
    }
    reap(child, number < 14 ? "credential_fixture_reaped" : "unprivileged_fixture_reaped");
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (argc == 4 && !strcmp(argv[1], "--owned-exec"))
        return actor(atoi(argv[2]), atoi(argv[3]), 1);
    if (argc == 3 && !strcmp(argv[1], "--owned-credential-exec")) {
        check("exec_unequal_effective_real_uid_retains_identity", geteuid(), 60002);
        check("exec_unequal_real_uid", getuid(), 60001);
        check("exec_unequal_ids_resets_to_policy", prctl(PR_GET_DUMPABLE), atoi(argv[2]));
        return failures ? 42 : 0;
    }
    alarm(90);
    if (argc != 3 || strcmp(argv[1], "--reset-policy") ||
        strlen(argv[2]) != 1 || argv[2][0] < '0' || argv[2][0] > '2') {
        fprintf(stderr, "Usage: lifecycle-probe --reset-policy 0|1|2\n"); return 96;
    }
    reset_policy = argv[2][0] - '0';
    if (geteuid() != 0) { fprintf(stderr, "Root only for isolated credential fixture setup\n"); return 96; }
    struct utsname u;
    if (uname(&u)) return 97;
    printf("{\"suite\":\"dumpable-lifecycle-v2\",\"kernel\":\"%s\",\"release\":\"%s\",\"max_live_owned_children\":2}\n", u.sysname, u.release);
    int policy_fd = open("/proc/sys/fs/suid_dumpable", O_RDONLY);
    if (policy_fd >= 0) {
        char actual = 0;
        require(read(policy_fd, &actual, 1) == 1 && actual - '0' == reset_policy,
                "explicit_reset_policy_equals_readonly_actual_sysctl");
        close(policy_fd);
    }
    printf("{\"reset_policy\":%d,\"policy_sysctl_present\":%s,\"no_sysctl_changed\":true}\n", reset_policy, policy_fd >= 0 ? "true" : "false");
    for (unsigned n = 0; n < 15; n++) run_owned(n);
    printf("{\"summary\":true,\"failed_fixtures\":%u,\"all_children_reaped\":true,\"production_isolation_qualified\":false}\n", failures);
    return failures ? 42 : 0;
}
