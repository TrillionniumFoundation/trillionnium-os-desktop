// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/signalfd.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t children[8];
static int child_count;
static int info_fd = -1;
struct fault_info { int num, code; uintptr_t addr; };

static void cleanup(void)
{
    for (int i = 0; i < child_count; ++i)
        if (children[i] > 0) kill(children[i], SIGKILL);
}
static void deadline(int sig) { (void)sig; cleanup(); _exit(124); }
static void require(int okay, const char *why)
{
    if (okay) return;
    fprintf(stderr, "INLINE_SIGNAL_FAIL %s errno=%d\n", why, errno);
    cleanup();
    exit(1);
}
static pid_t child(void)
{
    require(child_count < 8, "child capacity");
    pid_t pid = fork();
    require(pid >= 0, "fork");
    if (pid == 0) {
        child_count = 0;
        alarm(20);
        require(prctl(PR_SET_PDEATHSIG, SIGKILL) == 0, "parent death cleanup");
    } else children[child_count++] = pid;
    return pid;
}
static int reap(pid_t pid)
{
    int status = 0;
    require(waitpid(pid, &status, 0) == pid, "wait/reap");
    for (int i = 0; i < child_count; ++i)
        if (children[i] == pid) children[i] = 0;
    while (child_count > 0 && children[child_count - 1] == 0) --child_count;
    return status;
}
static void killed(pid_t pid)
{
    int status = reap(pid);
    require(WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL, "SIGKILL status");
}
static void marker(const char *line)
{
    size_t len = strlen(line);
    require(write(STDOUT_FILENO, line, len) == (ssize_t)len, "marker write");
}
static void pass(const char *name)
{
    char line[128];
    int n = snprintf(line, sizeof(line), "INLINE_SIGNAL_PASS %s\n", name);
    require(n > 0 && n < (int)sizeof(line), "marker length"); marker(line);
}
static void fault_handler(int num, siginfo_t *info, void *context)
{
    (void)context;
    struct fault_info data = { num, info->si_code, (uintptr_t)info->si_addr };
    _exit(write(info_fd, &data, sizeof(data)) == (ssize_t)sizeof(data) ? 0 : 91);
}
static void fault_information(int permission_denied)
{
    int fds[2]; require(pipe(fds) == 0, "fault pipe");
    void *page = mmap(NULL, 4096, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    require(page != MAP_FAILED, "fault mapping");
    if (!permission_denied) require(munmap(page, 4096) == 0, "create unmapped address");
    pid_t pid = child();
    if (pid == 0) {
        close(fds[0]); info_fd = fds[1];
        struct sigaction action = { .sa_sigaction = fault_handler, .sa_flags = SA_SIGINFO };
        sigemptyset(&action.sa_mask);
        require(sigaction(SIGSEGV, &action, NULL) == 0, "SA_SIGINFO");
        *(volatile char *)page = 1;
        _exit(92);
    }
    close(fds[1]); struct fault_info info;
    require(read(fds[0], &info, sizeof(info)) == (ssize_t)sizeof(info), "fault information read");
    printf("INLINE_SIGNAL_OBSERVED num=%d code=%d addr=%#lx expected=%#lx\n", info.num, info.code, (unsigned long)info.addr, (unsigned long)(uintptr_t)page);
    require(info.num == SIGSEGV && info.code == (permission_denied ? SEGV_ACCERR : SEGV_MAPERR) && info.addr == (uintptr_t)page,
            "fault number/code/address");
    int status = reap(pid); require(WIFEXITED(status) && WEXITSTATUS(status) == 0, "fault handler exit");
    close(fds[0]);
    if (permission_denied) require(munmap(page, 4096) == 0, "unmap fault page");
    pass(permission_denied ? "fault_siginfo" : "unmapped_fault_siginfo");
}
static void fatal_send(int mode)
{
    int fds[2]; require(pipe(fds) == 0, "ready pipe");
    pid_t pid = child();
    if (pid == 0) {
        close(fds[0]);
        if (mode == 2) require(setpgid(0, 0) == 0, "child process group");
        require(write(fds[1], "R", 1) == 1, "ready"); close(fds[1]);
        for (;;) pause();
    }
    close(fds[1]); char ready;
    require(read(fds[0], &ready, 1) == 1 && ready == 'R', "ready read"); close(fds[0]);
    if (mode == 0) require(kill(pid, SIGKILL) == 0, "kill");
    else if (mode == 1) require(syscall(SYS_tgkill, pid, pid, SIGKILL) == 0, "tgkill");
    else if (mode == 2) require(kill(-pid, SIGKILL) == 0, "group kill");
    else {
        int fd = syscall(SYS_pidfd_open, pid, 0); require(fd >= 0, "pidfd open");
        require(syscall(SYS_pidfd_send_signal, fd, SIGKILL, NULL, 0) == 0, "pidfd send"); close(fd);
    }
    killed(pid);
    const char *names[] = { "kill_reap", "tgkill_reap", "group_kill_reap", "pidfd_dynamic_reap" };
    pass(names[mode]);
}
static void permission_denial(void)
{
    int fds[2]; require(pipe(fds) == 0, "permission ready pipe");
    pid_t target = child();
    if (target == 0) {
        close(fds[0]); require(setgid(60001) == 0 && setuid(60001) == 0, "target identity");
        require(write(fds[1], "R", 1) == 1, "target ready"); close(fds[1]);
        for (;;) pause();
    }
    close(fds[1]); char ready; require(read(fds[0], &ready, 1) == 1, "target ready read"); close(fds[0]);
    pid_t sender = child();
    if (sender == 0) {
        require(setgid(60002) == 0 && setuid(60002) == 0, "sender identity");
        errno = 0; require(kill(target, SIGKILL) == -1 && errno == EPERM, "kill permission");
        errno = 0; require(syscall(SYS_tgkill, target, target, SIGKILL) == -1 && errno == EPERM, "tgkill permission");
        _exit(0);
    }
    int status = reap(sender); require(WIFEXITED(status) && WEXITSTATUS(status) == 0, "sender exit");
    require(kill(target, 0) == 0 && kill(target, SIGKILL) == 0, "target survived denial"); killed(target);
    pass("original_permissions");
}
static void realtime_and_signalfd(void)
{
    sigset_t mask, original; sigemptyset(&mask); sigaddset(&mask, SIGRTMIN); sigaddset(&mask, SIGUSR1);
    require(sigprocmask(SIG_BLOCK, &mask, &original) == 0, "mask signals");
    for (int value = 11; value <= 12; ++value) {
        union sigval payload = { .sival_int = value };
        require(sigqueue(getpid(), SIGRTMIN, payload) == 0, "RT enqueue");
    }
    struct timespec limit = { .tv_sec = 1 }; siginfo_t info;
    for (int value = 11; value <= 12; ++value) {
        require(sigtimedwait(&mask, &info, &limit) == SIGRTMIN, "RT dequeue");
        require(info.si_code == SI_QUEUE && info.si_value.sival_int == value && info.si_pid == getpid(), "RT FIFO info");
    }
    pass("dynamic_realtime_fifo");
    sigemptyset(&mask); sigaddset(&mask, SIGUSR1);
    int fd = signalfd(-1, &mask, SFD_NONBLOCK | SFD_CLOEXEC); require(fd >= 0, "signalfd");
    require(kill(getpid(), SIGUSR1) == 0, "standard enqueue");
    struct signalfd_siginfo record;
    require(read(fd, &record, sizeof(record)) == sizeof(record), "signalfd read");
    require(record.ssi_signo == SIGUSR1 && record.ssi_code == SI_USER, "signalfd original fields");
    close(fd); require(sigprocmask(SIG_SETMASK, &original, NULL) == 0, "restore mask");
    pass("dynamic_signalfd");
}
static void ptrace_fault(void)
{
    void *page = mmap(NULL, 4096, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    require(page != MAP_FAILED, "ptrace mapping");
    pid_t pid = child();
    if (pid == 0) {
        require(ptrace(PTRACE_TRACEME, 0, NULL, NULL) == 0, "traceme");
        require(raise(SIGSTOP) == 0, "trace stop");
        *(volatile char *)page = 1; _exit(93);
    }
    int status;
    require(waitpid(pid, &status, 0) == pid && WIFSTOPPED(status) && WSTOPSIG(status) == SIGSTOP, "initial trace stop");
    require(ptrace(PTRACE_CONT, pid, NULL, NULL) == 0, "continue to fault");
    require(waitpid(pid, &status, 0) == pid && WIFSTOPPED(status) && WSTOPSIG(status) == SIGSEGV, "fault trace stop");
    siginfo_t info; require(ptrace(PTRACE_GETSIGINFO, pid, NULL, &info) == 0, "trace info");
    require(info.si_signo == SIGSEGV && info.si_code == SEGV_ACCERR && info.si_addr == page, "trace fault information");
    require(ptrace(PTRACE_CONT, pid, NULL, (void *)(uintptr_t)SIGSEGV) == 0, "deliver fault");
    status = reap(pid); require(WIFSIGNALED(status) && WTERMSIG(status) == SIGSEGV, "trace fault reap");
    require(munmap(page, 4096) == 0, "unmap trace page"); pass("ptrace_fault_owner");
}
int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    require(argc == 2 && getuid() == 0 &&
            (!strcmp(argv[1], "--linux-reference") ||
             (!strcmp(argv[1], "--disposable-guest") && access("/.hepta-disposable-guest", F_OK) == 0)), "explicit test environment");
    signal(SIGALRM, deadline); alarm(30);
    marker("INLINE_SIGNAL_BEGIN\n");
    fault_information(1); fault_information(0);
    for (int mode = 0; mode < 4; ++mode) fatal_send(mode);
    permission_denial(); realtime_and_signalfd(); ptrace_fault();
    alarm(0); marker("INLINE_SIGNAL_COMPLETE cases=10\n"); return 0;
}
