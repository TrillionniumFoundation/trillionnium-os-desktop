// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <pthread.h>
#include <signal.h>
#include <stddef.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

static unsigned checks, failed;
static int partial = 1;
static const char *self;
static char private_root[] = "/tmp/hepta-seccomp-XXXXXX";
static char effect_path[128];
static char suid_path[128];
static void check(int ok, const char *name) {
    ++checks;
    if (!ok) ++failed;
    printf("{\"check\":\"%s\",\"passed\":%s,\"errno\":%d}\n", name, ok ? "true" : "false", errno);
    fflush(stdout);
}
static void done(void) { syscall(SYS_exit, failed ? 101 : 0); __builtin_unreachable(); }
static int install(struct sock_filter *code, unsigned short length, unsigned flags, int via_prctl) {
    struct sock_fprog program = { .len = length, .filter = code };
    return via_prctl ? prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program, 0L, 0L)
                     : (int)syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, flags, &program);
}
static void nnp(void) {
    check(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0, "set_no_new_privs");
}
static void deny(struct sock_filter *code, int number, unsigned action) {
    code[0] = (struct sock_filter) BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch));
    code[1] = (struct sock_filter) BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0);
    code[2] = (struct sock_filter) BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS);
    code[3] = (struct sock_filter) BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr));
    code[4] = (struct sock_filter) BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, number, 0, 1);
    code[5] = (struct sock_filter) BPF_STMT(BPF_RET | BPF_K, action);
    code[6] = (struct sock_filter) BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW);
}
static void *inherited_thread(void *unused) {
    (void)unused;
    errno = 0;
    return (void *)(size_t)(syscall(SYS_getpid) == -1 && errno == EPERM);
}
static void errno_filter(int via_prctl) {
    struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_ERRNO | EPERM);
    nnp();
    check(install(code, 7, 0, via_prctl) == 0, "install_native_filter");
    check(prctl(PR_GET_SECCOMP, 0L, 0L, 0L, 0L) == 2, "get_filter_mode");
    errno = 0; check(syscall(SYS_getpid) == -1 && errno == EPERM, "getpid_denied");
    check(syscall(SYS_getppid) > 0, "getppid_allowed");
    code[5].k = SECCOMP_RET_ALLOW;
    errno = 0; check(syscall(SYS_getpid) == -1 && errno == EPERM, "user_program_mutation_cannot_relax_filter");
    struct sock_filter allow[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    check(install(allow, 1, 0, 0) == 0, "stack_allow");
    errno = 0; check(syscall(SYS_getpid) == -1 && errno == EPERM, "stacking_cannot_relax_filter");
    pid_t child = fork();
    if (child == 0) {
        failed = 0; errno = 0;
        check(syscall(SYS_getpid) == -1 && errno == EPERM, "fork_inherits_filter");
        done();
    }
    int status = 0; check(child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "filtered_fork_child_exits");
    pthread_t thread;
    int created = pthread_create(&thread, NULL, inherited_thread, NULL);
    void *thread_result = NULL;
    check(created == 0 && pthread_join(thread, &thread_result) == 0 && thread_result == (void *)1,
          "clone_thread_inherits_filter");
    char *const argv[] = { (char *)self, "--inherited-exec", NULL };
    execv(self, argv);
    check(0, "exec_inherited_filter_launch");
}
static void no_effect(void) {
    struct sock_filter code[7]; deny(code, SYS_openat, SECCOMP_RET_ERRNO | EACCES);
    nnp(); check(install(code, 7, 0, 0) == 0, "install_openat_deny");
    errno = 0;
    long fd = syscall(SYS_openat, AT_FDCWD, effect_path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    check(fd == -1 && errno == EACCES, "denied_syscall_has_no_file_effect");
}
static void malformed(void) {
    nnp();
    struct sock_filter invalid[][2] = {
        { BPF_STMT(BPF_JMP | BPF_JA, 99), BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) },
        { BPF_STMT(BPF_LD | BPF_W | BPF_ABS, 64), BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) },
        { BPF_STMT(BPF_LD | BPF_W | BPF_MEM, 0), BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) },
        { BPF_STMT(BPF_ALU | BPF_DIV | BPF_K, 0), BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) },
    };
    for (unsigned i = 0; i < sizeof invalid / sizeof invalid[0]; ++i) {
        errno = 0; check(install(invalid[i], 2, 0, 0) == -1 && errno == EINVAL, "invalid_filter_rejected");
    }
    struct sock_filter allow[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    errno = 0; check(install(allow, 0, 0, 0) == -1 && errno == EINVAL, "zero_length_rejected");
    errno = 0; check(syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, 0, NULL) == -1 && errno == EFAULT, "bad_program_pointer_rejected");
    if (partial) {
        errno = 0; check(install(allow, 1, SECCOMP_FILTER_FLAG_LOG, 0) == -1 && errno == EINVAL, "unsupported_log_flag_not_success");
        unsigned action = SECCOMP_RET_TRACE;
        errno = 0; check(syscall(SYS_seccomp, SECCOMP_GET_ACTION_AVAIL, 0, &action) == -1 && errno == EOPNOTSUPP, "unsupported_trace_not_advertised");
    }
    check(install(allow, 1, 0, 0) == 0, "valid_filter_after_failures");
}
static void unprivileged(void) {
    check(setresuid(60001, 60001, 60001) == 0, "drop_privileges");
    struct sock_filter allow[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    errno = 0; check(install(allow, 1, 0, 0) == -1 && errno == EACCES, "unprivileged_requires_no_new_privs");
    nnp(); check(install(allow, 1, 0, 0) == 0, "unprivileged_nnp_can_restrict");
}
static void killed(void) {
    signal(SIGSYS, SIG_IGN);
    struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_KILL_PROCESS);
    nnp(); check(install(code, 7, 0, 0) == 0, "install_kill_process");
    (void)syscall(SYS_getpid);
    check(0, "kill_action_cannot_be_ignored");
}
static atomic_int sibling_ready;
static void *waiting_sibling(void *unused) {
    (void)unused;
    atomic_store_explicit(&sibling_ready, 1, memory_order_release);
    for (;;) {
        const struct timespec delay = { .tv_nsec = 10000000 };
        nanosleep(&delay, NULL);
    }
    return NULL;
}
static void killed_with_sibling(void) {
    // If only the triggering thread dies, SIGALRM makes this a bounded failure
    // rather than leaving the test process waiting forever on its sibling.
    alarm(3);
    struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_KILL_PROCESS);
    nnp(); check(install(code, 7, 0, 0) == 0, "install_multithread_kill_process");
    pthread_t thread;
    check(pthread_create(&thread, NULL, waiting_sibling, NULL) == 0, "create_kill_sibling");
    while (!atomic_load_explicit(&sibling_ready, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    (void)syscall(SYS_getpid);
    check(0, "kill_process_cannot_leave_sibling_running");
}
static volatile sig_atomic_t trap_received, trap_fields_ok;
static void trap_handler(int signo, siginfo_t *info, void *context) {
    ucontext_t *uc = context;
    trap_fields_ok = signo == SIGSYS && info->si_signo == SIGSYS && info->si_code == 1
        && info->si_errno == 0x1234 && info->si_syscall == SYS_openat
        && info->si_arch == AUDIT_ARCH_X86_64
        && info->si_call_addr == (void *)(size_t)uc->uc_mcontext.gregs[REG_RIP];
    ++trap_received;
    uc->uc_mcontext.gregs[REG_RAX] = -ERANGE;
}
static void trapped(void) {
    struct sigaction action = { .sa_sigaction = trap_handler, .sa_flags = SA_SIGINFO };
    sigemptyset(&action.sa_mask);
    check(sigaction(SIGSYS, &action, NULL) == 0, "install_sigsys_handler");
    struct sock_filter code[7];
    nnp();
    deny(code, SYS_openat, SECCOMP_RET_ERRNO | EACCES);
    check(install(code, 7, 0, 0) == 0, "install_older_errno");
    deny(code, SYS_openat, SECCOMP_RET_TRAP | 0x1234);
    unsigned available = SECCOMP_RET_TRAP;
    check(syscall(SYS_seccomp, SECCOMP_GET_ACTION_AVAIL, 0, &available) == 0, "trap_advertised");
    check(install(code, 7, 0, 0) == 0, "install_trap");
    errno = 0;
    long fd = syscall(SYS_openat, AT_FDCWD, effect_path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    check(fd == -1 && errno == ERANGE, "trap_handler_controls_return_without_dispatch");
    check(trap_received == 1 && trap_fields_ok, "trap_siginfo_uapi_and_return_ip");
    check(syscall(SYS_getpid) > 0, "trap_resumes_at_next_instruction");
}
static void trap_forced(int ignored) {
    if (ignored) signal(SIGSYS, SIG_IGN);
    else {
        struct sigaction action = { .sa_sigaction = trap_handler, .sa_flags = SA_SIGINFO };
        sigemptyset(&action.sa_mask);
        check(sigaction(SIGSYS, &action, NULL) == 0, "install_blocked_trap_handler");
        sigset_t blocked; sigemptyset(&blocked); sigaddset(&blocked, SIGSYS);
        check(sigprocmask(SIG_BLOCK, &blocked, NULL) == 0, "block_sigsys_before_trap");
    }
    struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_TRAP);
    nnp(); check(install(code, 7, 0, 0) == 0, "install_forced_trap");
    (void)syscall(SYS_getpid);
    check(0, "forced_trap_cannot_be_suppressed");
}
static void trap_ignored(void) { trap_forced(1); }
static void trap_blocked(void) { trap_forced(0); }
static atomic_int sync_ready, sync_phase;
static int sync_inherited;
static void *sync_worker(void *unused) {
    (void)unused;
    int before = prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == sync_inherited;
    atomic_fetch_add_explicit(&sync_ready, 1, memory_order_release);
    while (!atomic_load_explicit(&sync_phase, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    errno = 0;
    int denied = syscall(SYS_getpid) == -1 && errno == EPERM;
    int nnp_set = prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == 1;
    return (void *)(size_t)(before && denied && nnp_set);
}
static void sync_roundtrip(int inherited) {
    sync_inherited = inherited;
    struct sock_filter allow[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    if (inherited) { nnp(); check(install(allow, 1, 0, 0) == 0, "install_inherited_root_filter"); }
    pthread_t threads[3];
    for (unsigned i = 0; i < 3; ++i) check(pthread_create(&threads[i], NULL, sync_worker, NULL) == 0, "create_tsync_peer");
    while (atomic_load_explicit(&sync_ready, memory_order_acquire) != 3) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    if (!inherited) nnp();
    struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_ERRNO | EPERM);
    if (inherited) {
        check(install(code, 7, 0, 0) == 0, "caller_extends_inherited_policy");
        check(install(allow, 1, SECCOMP_FILTER_FLAG_TSYNC, 0) == 0, "tsync_inherited_ancestor");
    } else check(install(code, 7, SECCOMP_FILTER_FLAG_TSYNC, 0) == 0, "tsync_disabled_peers");
    errno = 0; check(syscall(SYS_getpid) == -1 && errno == EPERM, "tsync_restricts_caller");
    atomic_store_explicit(&sync_phase, 1, memory_order_release);
    for (unsigned i = 0; i < 3; ++i) {
        void *result = NULL;
        check(pthread_join(threads[i], &result) == 0 && result == (void *)1, "tsync_restricts_peer_and_propagates_nnp");
    }
    pthread_t future; void *result = NULL;
    check(pthread_create(&future, NULL, inherited_thread, NULL) == 0
          && pthread_join(future, &result) == 0 && result == (void *)1, "post_tsync_clone_inherits_policy");
}
static void sync_disabled(void) { sync_roundtrip(0); }
static void sync_ancestor(void) { sync_roundtrip(1); }
static atomic_int divergent_tid;
static void *divergent_worker(void *unused) {
    (void)unused;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return NULL;
    struct sock_filter allow[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    if (install(allow, 1, 0, 0)) return NULL;
    atomic_store_explicit(&divergent_tid, (int)syscall(SYS_gettid), memory_order_release);
    while (!atomic_load_explicit(&sync_phase, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    return (void *)(size_t)(syscall(SYS_getpid) > 0);
}
static void sync_divergent(void) {
    pthread_t thread;
    check(pthread_create(&thread, NULL, divergent_worker, NULL) == 0, "create_divergent_tsync_peer");
    while (!atomic_load_explicit(&divergent_tid, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    nnp(); struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_ERRNO | EPERM);
    int rc = install(code, 7, SECCOMP_FILTER_FLAG_TSYNC, 0);
    check(rc == atomic_load_explicit(&divergent_tid, memory_order_acquire), "tsync_returns_incompatible_tid");
    check(syscall(SYS_getpid) > 0 && prctl(PR_GET_SECCOMP, 0L, 0L, 0L, 0L) == 0, "failed_tsync_preserves_caller");
    atomic_store_explicit(&sync_phase, 1, memory_order_release);
    void *result = NULL;
    check(pthread_join(thread, &result) == 0 && result == (void *)1, "failed_tsync_preserves_peer");
}
static void *racing_creator(void *unused) {
    (void)unused;
    pthread_t threads[16];
    atomic_store_explicit(&sync_ready, 1, memory_order_release);
    unsigned count = 0;
    for (; count < 16; ++count) if (pthread_create(&threads[count], NULL, sync_worker, NULL)) break;
    int ok = count == 16;
    for (unsigned i = 0; i < count; ++i) {
        void *result = NULL;
        if (pthread_join(threads[i], &result) || result != (void *)1) ok = 0;
    }
    return (void *)(size_t)ok;
}
static void sync_clone_race(void) {
    // All children check after the successful TSYNC return. Creating any of
    // them before or during publication must not leave an old-policy sibling.
    sync_inherited = 1;
    nnp();
    pthread_t creator;
    check(pthread_create(&creator, NULL, racing_creator, NULL) == 0, "start_concurrent_clone_creator");
    while (!atomic_load_explicit(&sync_ready, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_ERRNO | EPERM);
    check(install(code, 7, SECCOMP_FILTER_FLAG_TSYNC, 0) == 0, "tsync_during_concurrent_clones");
    atomic_store_explicit(&sync_phase, 1, memory_order_release);
    void *result = NULL;
    check(pthread_join(creator, &result) == 0 && result == (void *)1, "all_concurrent_clones_keep_synced_policy");
}
static void *exec_installer(void *unused) {
    (void)unused;
    atomic_store_explicit(&sync_ready, 1, memory_order_release);
    struct sock_filter allow[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    for (unsigned i = 0; i < 128; ++i) {
        if (install(allow, 1, 0, 0) && errno != EINTR) return NULL;
    }
    for (;;) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    return NULL;
}
static void exec_with_installer(void) {
    nnp(); struct sock_filter code[7]; deny(code, SYS_getpid, SECCOMP_RET_ERRNO | EPERM);
    check(install(code, 7, 0, 0) == 0, "install_policy_before_racing_exec");
    pthread_t thread;
    check(pthread_create(&thread, NULL, exec_installer, NULL) == 0, "start_filter_installer_before_exec");
    while (!atomic_load_explicit(&sync_ready, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 1000000 };
        nanosleep(&delay, NULL);
    }
    char *const argv[] = { (char *)self, "--inherited-exec", NULL };
    execv(self, argv);
    check(0, "racing_exec_launch");
}
static void *sync_before_privileged_exec(void *unused) {
    (void)unused;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return NULL;
    atomic_store_explicit(&sync_ready, 1, memory_order_release);
    while (!atomic_load_explicit(&sync_phase, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 100000 };
        nanosleep(&delay, NULL);
    }
    struct sock_filter allow[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    (void)install(allow, 1, SECCOMP_FILTER_FLAG_TSYNC, 0);
    return NULL;
}
static void privileged_exec_race(void) {
    check(setresuid(60001, 60001, 60001) == 0, "drop_before_setuid_exec_race");
    pthread_t thread;
    check(pthread_create(&thread, NULL, sync_before_privileged_exec, NULL) == 0, "create_nnp_sync_exec_peer");
    while (!atomic_load_explicit(&sync_ready, memory_order_acquire)) {
        const struct timespec delay = { .tv_nsec = 100000 };
        nanosleep(&delay, NULL);
    }
    atomic_store_explicit(&sync_phase, 1, memory_order_release);
    char *const argv[] = { suid_path, "--setuid-exec-check", NULL };
    execv(suid_path, argv);
    check(0, "setuid_exec_race_launch");
}
static int prepare_suid_fixture(void) {
    // Only the disposable Asterinas guest calls this; the Linux reference must
    // never publish a setuid executable on the user's host filesystem.
    if (snprintf(suid_path, sizeof suid_path, "%s/suid-probe", private_root) >= (int)sizeof suid_path) return 0;
    int source = open(self, O_RDONLY | O_CLOEXEC);
    if (source < 0) return 0;
    int target = open(suid_path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0700);
    if (target < 0) { close(source); return 0; }
    char bytes[8192]; ssize_t count; int ok = 1;
    while ((count = read(source, bytes, sizeof bytes)) > 0) {
        ssize_t offset = 0;
        while (offset < count) {
            ssize_t written = write(target, bytes + offset, (size_t)(count - offset));
            if (written <= 0) { ok = 0; break; }
            offset += written;
        }
        if (!ok) break;
    }
    if (count < 0) ok = 0;
    close(source); close(target);
    struct stat st;
    return ok && chmod(suid_path, 04755) == 0 && stat(suid_path, &st) == 0
        && st.st_uid == 0 && (st.st_mode & 04755) == 04755 && chmod(private_root, 0755) == 0;
}
static void strict_ok(void) {
    check(syscall(SYS_seccomp, SECCOMP_SET_MODE_STRICT, 0, 0) == 0, "strict_install");
    const char text[] = "strict_write_allowed\n";
    syscall(SYS_write, STDOUT_FILENO, text, sizeof text - 1);
    done();
}
static void strict_killed(void) {
    check(prctl(PR_SET_SECCOMP, SECCOMP_MODE_STRICT, 0L, 0L, 0L) == 0, "strict_prctl_install");
    (void)syscall(SYS_getpid);
    syscall(SYS_exit, 101);
}
static void run(const char *name, void (*test)(void), int signum) {
    pid_t child = fork();
    if (child == 0) { failed = 0; alarm(10); test(); done(); }
    int status = 0;
    int waited = child > 0 && waitpid(child, &status, 0) == child;
    check(waited && (signum ? (WIFSIGNALED(status) && WTERMSIG(status) == signum)
                            : (WIFEXITED(status) && WEXITSTATUS(status) == 0)), name);
}
static void syscall_filter(void) { errno_filter(0); }
static void prctl_filter(void) { errno_filter(1); }
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0); self = argv[0];
    struct rlimit no_core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &no_core)) return 103;
    if (argc == 2 && !strcmp(argv[1], "--inherited-exec")) {
        errno = 0; check(syscall(SYS_getpid) == -1 && errno == EPERM, "exec_inherits_filter");
        check(prctl(PR_GET_SECCOMP, 0L, 0L, 0L, 0L) == 2, "exec_retains_mode"); done();
    }
    if (argc == 2 && !strcmp(argv[1], "--setuid-exec-check")) {
        int nnp_value = prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L);
        check(getuid() == 60001 && (nnp_value == 0 || nnp_value == 1), "setuid_exec_retains_real_identity");
        check((nnp_value == 1 && geteuid() == 60001) || (nnp_value == 0 && geteuid() == 0),
              "synced_nnp_never_publishes_stale_privileged_exec");
        printf("{\"setuid_exec_observed_nnp\":%d,\"euid\":%u}\n", nnp_value, (unsigned)geteuid());
        done();
    }
    if (argc == 2 && !strcmp(argv[1], "--linux-reference")) partial = 0;
    if (!mkdtemp(private_root)) return 104;
    if (snprintf(effect_path, sizeof effect_path, "%s/must-not-exist", private_root) >= (int)sizeof effect_path) return 105;
    run("syscall_filter_roundtrip", syscall_filter, 0);
    run("prctl_filter_roundtrip", prctl_filter, 0);
    run("denied_effect_child", no_effect, 0);
    check(access(effect_path, F_OK) == -1 && errno == ENOENT, "parent_confirms_no_file_effect");
    run("malformed_program_child", malformed, 0);
    if (partial || geteuid() == 0) run("unprivileged_admission_child", unprivileged, 0);
    else puts("Linux_reference_privilege_drop\tNOT_RUN\trequires_root");
    run("kill_process_reports_sigsys", killed, SIGSYS);
    run("kill_process_terminates_sibling", killed_with_sibling, SIGSYS);
    run("trap_siginfo_handler_roundtrip", trapped, 0);
    check(access(effect_path, F_OK) == -1 && errno == ENOENT, "parent_confirms_trap_has_no_file_effect");
    run("ignored_trap_forces_sigsys", trap_ignored, SIGSYS);
    run("blocked_trap_forces_sigsys", trap_blocked, SIGSYS);
    run("tsync_disabled_peer_roundtrip", sync_disabled, 0);
    run("tsync_ancestor_roundtrip", sync_ancestor, 0);
    run("tsync_divergent_chain_rejected_atomically", sync_divergent, 0);
    run("tsync_concurrent_clone_inheritance", sync_clone_race, 0);
    run("exec_with_filter_installer_does_not_deadlock", exec_with_installer, 0);
    // Container reference hosts can prohibit strict mode with their own filter.
    // This does not weaken the ordinary guest's required strict assertions.
    if (partial) {
        run("strict_write_and_exit_child", strict_ok, 0);
        run("strict_disallowed_call_sigsys", strict_killed, SIGSYS);
        int fixture = prepare_suid_fixture();
        check(fixture, "guest_only_setuid_fixture_is_root_owned");
        if (fixture) for (unsigned i = 0; i < 16; ++i)
            run("tsync_setuid_exec_race_preserves_nnp", privileged_exec_race, 0);
        unlink(suid_path);
        check(chmod(private_root, 0700) == 0, "remove_guest_setuid_fixture");
    }
    printf("{\"scope\":\"seccomp_x86_64_tsync\",\"parent_checks\":%u,\"failed\":%u,\"tsync_supported\":true,\"android_qualified\":false}\n", checks, failed);
    unlink(effect_path);
    rmdir(private_root);
    return failed ? 1 : 0;
}
