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
#include <unistd.h>

static unsigned checks, failed;
static int partial = 1;
static const char *self;
static char private_root[] = "/tmp/hepta-seccomp-XXXXXX";
static char effect_path[128];
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
        errno = 0; check(install(allow, 1, SECCOMP_FILTER_FLAG_TSYNC, 0) == -1 && errno == EINVAL, "unsupported_tsync_not_success");
        unsigned action = SECCOMP_RET_TRAP;
        errno = 0; check(syscall(SYS_seccomp, SECCOMP_GET_ACTION_AVAIL, 0, &action) == -1 && errno == EOPNOTSUPP, "unsupported_trap_not_advertised");
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
    if (child == 0) { failed = 0; test(); done(); }
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
    // Container reference hosts can prohibit strict mode with their own filter.
    // This does not weaken the ordinary guest's required strict assertions.
    if (partial) {
        run("strict_write_and_exit_child", strict_ok, 0);
        run("strict_disallowed_call_sigsys", strict_killed, SIGSYS);
    }
    printf("{\"scope\":\"seccomp_x86_64_stage_one\",\"parent_checks\":%u,\"failed\":%u,\"tsync_supported\":false,\"android_qualified\":false}\n", checks, failed);
    unlink(effect_path);
    rmdir(private_root);
    return failed ? 1 : 0;
}
