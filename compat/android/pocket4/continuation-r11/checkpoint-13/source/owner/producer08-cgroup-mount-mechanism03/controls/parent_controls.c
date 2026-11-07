#define main mechanism_program_main
#include "probe.c"
#undef main

#include <dirent.h>

static int descriptor_count(void) {
    DIR *dir = opendir("/proc/thread-self/fd");
    if (!dir) return -1;
    int count = 0;
    struct dirent *entry;
    while ((entry = readdir(dir))) {
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) ++count;
    }
    closedir(dir);
    return count;
}
static void delay_ms(unsigned value) {
    struct timespec delay = {value / 1000, (long)(value % 1000) * 1000000};
    while (nanosleep(&delay, &delay) && errno == EINTR) {}
}
static int accepted(const struct collection *out, const struct evidence *e) {
    return out->got && out->peer_eof && !out->error && out->reaped && !out->forced &&
        WIFEXITED(out->status) && WEXITSTATUS(out->status) == 0 && e->success &&
        e->all_private_mounts_unmounted && e->inherited_domain_closed;
}
enum case_id {
    NORMAL, EOF_BEFORE_EXIT, DELAYED_CLOSE, ALREADY_EXITED, EMPTY_EOF,
    SECOND_FRAME, EXTRA_BYTE, BAD_NONCE, SHORT_FRAME, LONG_FRAME,
    OPEN_TIMEOUT, EXIT_TIMEOUT, NONZERO_EXIT, BAD_PID
};
static int run_case(enum case_id which, const char *name) {
    int before = descriptor_count(), pair[2];
    if (before < 0 || socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, pair)) return 1;
    pid_t parent = getpid(), child = fork();
    if (child < 0) { close(pair[0]); close(pair[1]); return 1; }
    if (!child) {
        close(pair[0]);
        if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) _exit(90);
        struct evidence e; memset(&e, 0, sizeof(e));
        e.magic = MAGIC; memcpy(e.nonce, FIXTURE_NONCE, sizeof(e.nonce));
        e.child_pid = getpid(); e.success = 1;
        e.all_private_mounts_unmounted = e.inherited_domain_closed = 1;
        if (which == EMPTY_EOF) { close(pair[1]); _exit(0); }
        if (which == BAD_NONCE) e.nonce[0] ^= 1;
        if (which == BAD_PID) e.child_pid = parent;
        if (which == LONG_FRAME) {
            unsigned char bytes[sizeof(e) + 1]; memcpy(bytes, &e, sizeof(e)); bytes[sizeof(e)] = 1;
            if (send(pair[1], bytes, sizeof(bytes), MSG_NOSIGNAL) != (ssize_t)sizeof(bytes)) _exit(91);
        } else {
            size_t size = which == SHORT_FRAME ? sizeof(e) - 1 : sizeof(e);
            if (send(pair[1], &e, size, MSG_NOSIGNAL) != (ssize_t)size) _exit(92);
        }
        if (which == SECOND_FRAME && send(pair[1], &e, sizeof(e), MSG_NOSIGNAL) != (ssize_t)sizeof(e)) _exit(93);
        if (which == EXTRA_BYTE && send(pair[1], "x", 1, MSG_NOSIGNAL) != 1) _exit(94);
        if (which == DELAYED_CLOSE) delay_ms(25);
        if (which == OPEN_TIMEOUT) for (;;) pause();
        close(pair[1]);
        if (which == EOF_BEFORE_EXIT) delay_ms(25);
        if (which == EXIT_TIMEOUT) for (;;) pause();
        _exit(which == NONZERO_EXIT ? 7 : 0);
    }
    close(pair[1]);
    int fixture_error = 0;
    if (which == ALREADY_EXITED || which == SECOND_FRAME || which == EXTRA_BYTE) {
        siginfo_t info; memset(&info, 0, sizeof(info));
        int rc;
        do { rc = waitid(P_PID, (id_t)child, &info, WEXITED | WNOWAIT); } while (rc && errno == EINTR);
        if (rc || info.si_pid != child) fixture_error = 1;
    }
    struct evidence e; memset(&e, 0, sizeof(e));
    uint64_t duration = which == OPEN_TIMEOUT || which == EXIT_TIMEOUT ? UINT64_C(50000000) : UINT64_C(1000000000);
    struct collection out = collect_child(pair[0], child, &e, duration);
    close(pair[0]);
    int expected_pass = which <= ALREADY_EXITED;
    int ok = !fixture_error && out.reaped && descriptor_count() == before && accepted(&out, &e) == expected_pass;
    if (expected_pass) ok = ok && !out.error && !out.forced && out.peer_eof;
    else if (which == OPEN_TIMEOUT || which == EXIT_TIMEOUT)
        ok = ok && out.error == ETIMEDOUT && out.forced && WIFSIGNALED(out.status) && WTERMSIG(out.status) == SIGKILL;
    else if (which == NONZERO_EXIT)
        ok = ok && !out.error && !out.forced && out.peer_eof && WIFEXITED(out.status) && WEXITSTATUS(out.status) == 7;
    else ok = ok && out.error == EPROTO;
    printf("{\"case\":\"%s\",\"passed\":%s,\"got\":%s,\"peer_eof\":%s,\"reaped\":%s,\"forced\":%s,\"error\":%d,\"wait_status\":%d}\n",
           name, ok ? "true" : "false", out.got ? "true" : "false", out.peer_eof ? "true" : "false",
           out.reaped ? "true" : "false", out.forced ? "true" : "false", out.error, out.status);
    return !ok;
}
static int legacy_eof_control(void) {
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, pair)) return 1;
    close(pair[1]);
    struct evidence candidate;
    int got = 1;
    ssize_t n = recv(pair[0], &candidate, sizeof(candidate), MSG_DONTWAIT | MSG_TRUNC);
    /* Exact first two disjuncts of frozen02's former receive predicate. */
    int old_rejects = got || n != (ssize_t)sizeof(candidate);
    close(pair[0]);
    int ok = n == 0 && old_rejects;
    printf("{\"case\":\"legacy_got_then_EOF_rejected\",\"passed\":%s,\"recv_bytes\":%zd}\n", ok ? "true" : "false", n);
    return !ok;
}
int main(void) {
    static const char *names[] = {
        "single_frame_EOF_normal_exit", "EOF_before_pidfd_ready", "delayed_close", "frame_pending_after_child_exit",
        "EOF_without_frame_rejected", "second_full_frame_rejected_after_exit", "extra_nonempty_frame_rejected_after_exit",
        "wrong_nonce_rejected", "short_frame_rejected", "oversized_frame_rejected", "missing_EOF_timeout_forced_failure",
        "EOF_without_exit_timeout_forced_failure", "nonzero_child_exit_rejected", "wrong_child_PID_rejected"
    };
    int failed = legacy_eof_control();
    for (unsigned i = 0; i < sizeof(names) / sizeof(names[0]); ++i) failed += run_case((enum case_id)i, names[i]);
    printf("{\"cases\":15,\"passed\":%d,\"namespace_or_mount_executed\":false}\n", 15 - failed);
    return failed ? 1 : 0;
}
