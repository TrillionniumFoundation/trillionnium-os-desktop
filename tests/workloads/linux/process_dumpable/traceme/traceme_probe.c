#define _GNU_SOURCE
#include <errno.h>
#include <grp.h>
#include <linux/capability.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

/* Exactly one cooperative, self-created child. Its only inspected datum is
 * this public constant. PEEKDATA is read-only; no POKEDATA or other process. */
static volatile unsigned long public_sentinel = 0x5341464544554d50UL;
static unsigned violations;
struct reply { int stage, traceme, traceme_errno, set_result, dumpable; };
static void check(const char *name, int okay) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, okay ? "true" : "false");
    if (!okay) violations++;
}
static void exact(int fd, void *buffer, size_t length, int writing) {
    char *p = buffer;
    while (length) {
        ssize_t n = writing ? write(fd, p, length) : read(fd, p, length);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) _exit(90);
        p += n; length -= (size_t)n;
    }
}
static void drop_own_privileges(void) {
    if (geteuid() == 0) {
        for (int c = 0; c <= 40; c++)
            if (prctl(PR_CAPBSET_DROP, c, 0, 0, 0) && errno != EINVAL) _exit(91);
        if (setgroups(0, NULL) || setresgid(60001, 60001, 60001) ||
            setresuid(60001, 60001, 60001)) _exit(92);
    }
    struct __user_cap_header_struct h = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct c[2] = {{0}, {0}};
    if (syscall(SYS_capset, &h, c) || syscall(SYS_capget, &h, c) ||
        c[0].permitted || c[1].permitted || c[0].effective || c[1].effective ||
        prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L)) _exit(93);
}
int main(void) {
    alarm(25);
    setvbuf(stdout, NULL, _IOLBF, 0);
    drop_own_privileges();
    printf("{\"suite\":\"dumpable-traceme-v1\",\"observer_uid\":%u,\"observer_gid\":%u,\"cap_eff\":0,\"cap_prm\":0,\"nnp\":1,\"own_child_only\":true}\n", getuid(), getgid());
    int reply[2];
    if (pipe(reply)) return 94;
    pid_t child = fork();
    if (child < 0) return 95;
    if (child == 0) {
        close(reply[0]);
        errno = 0;
        int result = (int)ptrace(PTRACE_TRACEME, 0, NULL, NULL);
        int error = errno;
        for (int stage = 0; stage < 3; stage++) {
            int r = prctl(PR_SET_DUMPABLE, stage == 1 ? 1L : 0L);
            struct reply value = {stage, result, error, r, prctl(PR_GET_DUMPABLE)};
            exact(reply[1], &value, sizeof(value), 1);
            if (raise(SIGSTOP)) _exit(96);
        }
        close(reply[1]);
        _exit(0);
    }
    close(reply[1]);
    for (int stage = 0; stage < 3; stage++) {
        struct reply r;
        exact(reply[0], &r, sizeof(r), 0);
        int status = -1;
        pid_t waited;
        do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
        int stopped = waited == child && WIFSTOPPED(status) && WSTOPSIG(status) == SIGSTOP;
        printf("{\"stage\":%d,\"traceme_rc\":%d,\"traceme_errno\":%d,\"set_rc\":%d,\"dumpable\":%d,\"expected\":%d,\"owned_child_stopped\":%s}\n",
               stage, r.traceme, r.traceme_errno, r.set_result, r.dumpable,
               stage == 1 ? 1 : 0, stopped ? "true" : "false");
        check("exact_owned_child_stage_and_stop", r.stage == stage && r.traceme == 0 &&
              r.traceme_errno == 0 && r.set_result == 0 && r.dumpable == (stage == 1) && stopped);
        if (!stopped) return 97;
        errno = 0;
        long value = ptrace(PTRACE_PEEKDATA, child, (void *)&public_sentinel, NULL);
        int error = errno;
        int okay = stage == 1 ? error == 0 && (unsigned long)value == public_sentinel
                              : value == -1 && error == EIO;
        printf("{\"stage\":%d,\"operation\":\"peek_public_sentinel_only\",\"rc\":%ld,\"errno\":%d,\"denied_expected\":%s,\"passed\":%s}\n",
               stage, value, error, stage == 1 ? "false" : "true", okay ? "true" : "false");
        if (!okay) violations++;
        errno = 0;
        long continued = ptrace(PTRACE_CONT, child, NULL, NULL);
        int continue_errno = errno;
        printf("{\"stage\":%d,\"operation\":\"continue_owned_child\",\"rc\":%ld,\"errno\":%d,\"passed\":%s}\n",
               stage, continued, continue_errno, continued == 0 && continue_errno == 0 ? "true" : "false");
        if (continued || continue_errno) return 98;
    }
    close(reply[0]);
    int status = -1;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    int reaped = waited == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
    check("owned_child_reaped", reaped);
    printf("{\"summary\":true,\"violations\":%u,\"all_children_reaped\":%s,\"production_isolation_qualified\":false}\n", violations, reaped ? "true" : "false");
    return violations ? 42 : 0;
}
