#define _GNU_SOURCE
/* SPDX-License-Identifier: MPL-2.0 */
/*
 * Bounded, argument-free x86_64 Linux syscall tracer for disposable A04 probes.
 * Unlike strace, this records NO paths, argv, buffers, addresses or secrets.
 * It is an evidence fallback when strace is unavailable, not a full dependency
 * closure. PTRACE_O_EXITKILL prevents stray tracees if the host times out.
 */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define MAX_TRACED 4096
#define MAX_EVENTS 1000000UL

struct thread_state {
    pid_t tid;
    long syscall_nr;
    bool entry_seen;
};
static struct thread_state threads[MAX_TRACED];
static size_t thread_count;

static struct thread_state *thread_state(pid_t tid) {
    for (size_t i = 0; i < thread_count; ++i) {
        if (threads[i].tid == tid) return &threads[i];
    }
    if (thread_count >= MAX_TRACED) return NULL;
    struct thread_state *s = &threads[thread_count++];
    *s = (struct thread_state){.tid = tid, .syscall_nr = -1, .entry_seen = false};
    return s;
}

static void forget_thread(pid_t tid) {
    for (size_t i = 0; i < thread_count; ++i) {
        if (threads[i].tid == tid) {
            threads[i] = threads[--thread_count];
            return;
        }
    }
}

static int resume_thread(pid_t tid, int signal_to_deliver) {
    if (ptrace(PTRACE_SYSCALL, tid, 0, (void *)(long)signal_to_deliver) == -1) {
        if (errno == ESRCH) return 0;
        perror("PTRACE_SYSCALL");
        return -1;
    }
    return 0;
}

static int set_trace_options(pid_t tid) {
    long flags = PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEFORK |
                 PTRACE_O_TRACEVFORK | PTRACE_O_TRACECLONE |
                 PTRACE_O_TRACEEXEC | PTRACE_O_EXITKILL;
    if (ptrace(PTRACE_SETOPTIONS, tid, 0, (void *)flags) == -1) {
        perror("PTRACE_SETOPTIONS");
        return -1;
    }
    return 0;
}

int main(int argc, char **argv) {
#if !defined(__x86_64__) || !defined(__linux__)
    (void)argc; (void)argv;
    fprintf(stderr, "A04 ptrace evidence supported only for Linux x86_64\n");
    return 78;
#else
    if (argc < 4 || strcmp(argv[2], "--") != 0) {
        fprintf(stderr, "usage: a04-ptrace NEW-LOG.jsonl -- /absolute/pinned/ELF [args...]\n");
        return 64;
    }
    int fd = open(argv[1], O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) { perror("open exclusive trace log"); return 73; }
    FILE *log = fdopen(fd, "w");
    if (!log) { perror("fdopen"); close(fd); return 73; }
    setvbuf(log, NULL, _IOLBF, 0);
    pid_t initial = fork();
    if (initial == -1) { perror("fork"); fclose(log); return 1; }
    if (initial == 0) {
        if (ptrace(PTRACE_TRACEME, 0, 0, 0) == -1) _exit(125);
        raise(SIGSTOP);
        execvp(argv[3], &argv[3]);
        _exit(errno == ENOENT ? 127 : 126);
    }
    int status = 0;
    if (waitpid(initial, &status, 0) != initial || !WIFSTOPPED(status)) {
        fprintf(stderr, "tracee did not reach initial PTRACE stop\n");
        fclose(log); return 1;
    }
    if (set_trace_options(initial) != 0 || !thread_state(initial) || resume_thread(initial, 0) != 0) {
        fclose(log); return 1;
    }
    int primary_exit = -1;
    unsigned long event_count = 0;
    bool broken = false;
    for (;;) {
        pid_t tid = waitpid(-1, &status, __WALL);
        if (tid == -1) {
            if (errno == EINTR) continue;
            if (errno != ECHILD) { perror("waitpid"); broken = true; }
            break;
        }
        if (WIFEXITED(status) || WIFSIGNALED(status)) {
            int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : (128 + WTERMSIG(status));
            fprintf(log, "{\"kind\":\"exit\",\"tid\":%ld,\"code\":%d}\n", (long)tid, exit_code);
            if (tid == initial) primary_exit = exit_code;
            forget_thread(tid);
            continue;
        }
        if (!WIFSTOPPED(status)) { broken = true; break; }
        struct thread_state *thread = thread_state(tid);
        if (!thread) { fprintf(stderr, "A04 ptrace exceeded thread limit\n"); broken = true; break; }
        int sig = WSTOPSIG(status);
        unsigned int event = (unsigned int)status >> 16;
        if (sig == (SIGTRAP | 0x80)) {
            struct __ptrace_syscall_info info = {0};
            long result = ptrace(PTRACE_GET_SYSCALL_INFO, tid, sizeof(info), &info);
            if (result < 0) { perror("PTRACE_GET_SYSCALL_INFO"); broken = true; break; }
            if (info.op == PTRACE_SYSCALL_INFO_ENTRY || info.op == PTRACE_SYSCALL_INFO_SECCOMP) {
                thread->syscall_nr = (long)(info.op == PTRACE_SYSCALL_INFO_ENTRY ?
                                             info.entry.nr : info.seccomp.nr);
                thread->entry_seen = true;
            } else if (info.op == PTRACE_SYSCALL_INFO_EXIT && thread->entry_seen) {
                long rv = (long)info.exit.rval;
                int err = info.exit.is_error && rv >= -4095 && rv < 0 ? (int)-rv : 0;
                /* Linux internal -ERESTART* values are NOT userspace errno. */
                int internal_restart = err >= 512 && err <= 516 ? err : 0;
                if (internal_restart) err = 0;
                fprintf(log, "{\"kind\":\"syscall\",\"tid\":%ld,\"nr\":%ld,\"errno\":%d,\"internal_restart\":%d}\n",
                        (long)tid, thread->syscall_nr, err, internal_restart);
                thread->entry_seen = false;
                if (++event_count > MAX_EVENTS) {
                    fprintf(stderr, "A04 ptrace event budget exceeded\n");
                    broken = true; break;
                }
            }
            if (resume_thread(tid, 0) != 0) { broken = true; break; }
            continue;
        }
        if (sig == SIGTRAP && event) {
            if (event == PTRACE_EVENT_EXEC) thread->entry_seen = false;
            if (resume_thread(tid, 0) != 0) { broken = true; break; }
            continue;
        }
        /* A newly forked tracee gets a synthetic SIGSTOP. Never forward it. */
        if (resume_thread(tid, sig == SIGSTOP ? 0 : sig) != 0) {
            broken = true; break;
        }
    }
    if (fflush(log) != 0 || fclose(log) != 0) broken = true;
    if (broken || primary_exit < 0) {
        fprintf(stderr, "A04 syscall trace incomplete; no success claim\n");
        return 125;
    }
    return primary_exit;
#endif
}
