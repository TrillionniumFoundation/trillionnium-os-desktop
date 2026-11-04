/* Copyright 2026 Droidloom contributors. SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#if !defined(__aarch64__)
#error Compile this owned payload only for arm64-v8a.
#endif

#include <jni.h>
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

#include "probe_abi.h"

enum { CASE_SVC = 1, CASE_SMC_HANDLER = 2, CASE_SMC_DEFAULT = 3, CASE_SMC_MASK_EDIT = 4 };
enum { ST_PASS = 0, ST_FAIL = 1, ST_SETUP = 2, ST_TIMEOUT = 3 };
enum {
    WHY_NONE, WHY_BAD_CASE, WHY_BUSY, WHY_CLOCK, WHY_MASK_QUERY,
    WHY_ACTION_QUERY, WHY_ACTION_INSTALL, WHY_MASK_SET, WHY_ACTION_RESTORE,
    WHY_MASK_RESTORE, WHY_CHECKS, WHY_CHILD_POLICY, WHY_MMAP, WHY_FORK,
    WHY_WAIT, WHY_CHILD_SETUP, WHY_CHILD_RETURNED, WHY_CHILD_SIGNAL,
    WHY_CHILD_TIMEOUT, WHY_CHILD_CLEANUP
};
enum {
    PHASE_INITIAL = 0, PHASE_CHILD_STARTED = 1, PHASE_CHILD_READY = 2,
    PHASE_CHILD_RETURNED = 3, PHASE_CHILD_SETUP_ERROR = 4
};
enum {
    C_NO_SIGNAL = UINT64_C(1) << 0,
    C_ONE_SIGNAL = UINT64_C(1) << 1,
    C_SIGNO = UINT64_C(1) << 2,
    C_CODE = UINT64_C(1) << 3,
    C_ADDRESS = UINT64_C(1) << 4,
    C_PC = UINT64_C(1) << 5,
    C_REGS_BEFORE = UINT64_C(1) << 6,
    C_NZCV_BEFORE = UINT64_C(1) << 7,
    C_CONTEXT_MASK = UINT64_C(1) << 8,
    C_HANDLER_MASK = UINT64_C(1) << 9,
    C_REGS_RESTORED = UINT64_C(1) << 10,
    C_SP_RESTORED = UINT64_C(1) << 11,
    C_NZCV_RESTORED = UINT64_C(1) << 12,
    C_RESUME_PC = UINT64_C(1) << 13,
    C_COOKIE = UINT64_C(1) << 14,
    C_RETURN_VALUE = UINT64_C(1) << 15,
    C_MASK_RESTORED = UINT64_C(1) << 16,
    C_ACTION_RESTORED = UINT64_C(1) << 17,
    C_OPCODE_STABLE = UINT64_C(1) << 18,
    C_CHILD_READY = UINT64_C(1) << 19,
    C_CHILD_REAPED = UINT64_C(1) << 20,
    C_CHILD_SIGILL = UINT64_C(1) << 21,
    C_CHILD_NO_RETURN = UINT64_C(1) << 22,
    C_WITHIN_DEADLINE = UINT64_C(1) << 23,
    C_CONTEXT_MASK_FULL = UINT64_C(1) << 24,
    C_MASK_EDIT_APPLIED = UINT64_C(1) << 25,
    C_MASK_EDIT_STAGED = UINT64_C(1) << 26
};

struct capture {
    volatile sig_atomic_t count, unexpected;
    volatile int signo, info_signo, code, error;
    volatile uintptr_t address, pc, sp;
    volatile uint64_t pstate, regs[31], handler_mask;
    volatile long mask_rc;
    volatile int context_sigill_blocked, context_sigusr1_blocked;
    volatile uint64_t context_kernel_mask, context_requested_mask, live_mask_after_edit;
    volatile long mask_after_edit_rc;
};
struct child_shared {
    volatile sig_atomic_t phase, setup_reason, setup_errno;
    volatile pid_t pid, ppid, tid;
    volatile int pdeathsig;
    struct p4_after after;
};
struct result {
    int case_id, status, reason, error;
    pid_t pid, tid;
    uintptr_t expected_fault, expected_resume;
    uint32_t opcode_before, opcode_after;
    uint64_t started_ns, elapsed_ns, asm_return;
    uint64_t original_mask, mask_after;
    uint64_t entered_mask, post_handler_mask, expected_resume_mask;
    long post_handler_mask_rc;
    unsigned long old_action_flags;
    uintptr_t old_action_pointer;
    uint64_t old_action_mask, restored_action_mask;
    unsigned long restored_action_flags;
    uintptr_t restored_action_pointer;
    int action_readback_rc, action_equal;
    int action_restore_rc, mask_restore_rc;
    uint64_t checks, required;
    struct capture capture;
    struct p4_after after;
    pid_t child_pid, child_recorded_pid, child_recorded_ppid, child_recorded_tid;
    int child_phase, child_setup_reason, child_setup_errno, child_pdeathsig;
    int wait_status, wait_observed, child_reaped, timed_out, kill_rc, kill_errno;
    uint64_t child_elapsed_ns;
    unsigned long sigchld_flags;
    uintptr_t sigchld_pointer;
};

/* Only this preallocated storage is written by the signal handler. Formatting
 * and JNI allocation happen after the old action and mask have been restored.
 */
static struct result g_result;
static char g_json[16384];
static atomic_flag g_running = ATOMIC_FLAG_INIT;
static volatile uintptr_t g_fault, g_resume;
static volatile sig_atomic_t g_active;
static volatile sig_atomic_t g_edit_context_mask;
static volatile uint64_t g_requested_resume_mask;

static uint64_t bit_for_signal(int sig) { return UINT64_C(1) << (sig - 1); }
static const char* case_name(int c) {
    switch (c) {
        case CASE_SVC: return "svc";
        case CASE_SMC_HANDLER: return "smc-handler";
        case CASE_SMC_DEFAULT: return "smc-default";
        case CASE_SMC_MASK_EDIT: return "smc-mask-edit";
        default: return "invalid";
    }
}
static const char* status_name(int s) {
    switch (s) {
        case ST_PASS: return "PASS";
        case ST_FAIL: return "FAIL";
        case ST_SETUP: return "SETUP_ERROR";
        case ST_TIMEOUT: return "TIMEOUT";
        default: return "INVALID";
    }
}
static void problem(int status, int reason, int error) {
    if (g_result.reason == WHY_NONE) {
        g_result.status = status; g_result.reason = reason; g_result.error = error;
    }
}
static uint64_t now_ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0 || t.tv_sec < 0 ||
        t.tv_nsec < 0 || t.tv_nsec >= 1000000000L) return 0;
    if ((uint64_t)t.tv_sec > (UINT64_MAX - (uint64_t)t.tv_nsec) / UINT64_C(1000000000)) return 0;
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static long raw_mask(int how, const uint64_t* set, uint64_t* old) {
    /* AArch64 Linux rt_sigprocmask uses the 64-bit kernel signal set. The
     * public NDK sigset_t/ucontext_t are still used for public signal APIs.
     */
    return syscall(SYS_rt_sigprocmask, how, set, old, sizeof(uint64_t));
}
static uint32_t instruction_word(uintptr_t pc) {
    uint32_t word;
    memcpy(&word, (const void*)pc, sizeof(word));
    return word;
}
static uint64_t action_mask_bits(const sigset_t* mask) {
    uint64_t bits = 0;
    for (int sig = 1; sig <= 64; ++sig)
        if (sigismember(mask, sig) == 1) bits |= bit_for_signal(sig);
    return bits;
}

static void capture_sigill(int sig, siginfo_t* info, void* opaque) {
    struct capture* c = &g_result.capture;
    ucontext_t* context = (ucontext_t*)opaque;
    ++c->count;
    /* Never resume an unrelated instruction. This exit is an explicit owned
     * probe failure; the Java started record remains incomplete, never PASS.
     */
    if (!g_active || !info || !context || sig != SIGILL || c->count != 1 ||
        (uintptr_t)context->uc_mcontext.pc != g_fault) {
        c->unexpected = 1;
        _exit(124);
    }
    c->signo = sig; c->info_signo = info->si_signo;
    c->code = info->si_code; c->error = info->si_errno;
    c->address = (uintptr_t)info->si_addr;
    c->pc = (uintptr_t)context->uc_mcontext.pc;
    c->sp = (uintptr_t)context->uc_mcontext.sp;
    c->pstate = context->uc_mcontext.pstate;
    for (size_t i = 0; i < 31; ++i) c->regs[i] = context->uc_mcontext.regs[i];
    c->context_sigill_blocked = sigismember(&context->uc_sigmask, SIGILL);
    c->context_sigusr1_blocked = sigismember(&context->uc_sigmask, SIGUSR1);
    _Static_assert(sizeof(context->uc_sigmask) >= sizeof(uint64_t), "ARM64 kernel mask must fit");
    uint64_t context_mask = 0;
    memcpy(&context_mask, &context->uc_sigmask, sizeof(context_mask));
    c->context_kernel_mask = context_mask;
    uint64_t live_mask = 0;
    c->mask_rc = raw_mask(SIG_SETMASK, NULL, &live_mask);
    c->handler_mask = live_mask;
    if (g_edit_context_mask) {
        const uint64_t requested = g_requested_resume_mask;
        memcpy(&context->uc_sigmask, &requested, sizeof(requested));
        c->context_requested_mask = requested;
        uint64_t still_live = 0;
        c->mask_after_edit_rc = raw_mask(SIG_SETMASK, NULL, &still_live);
        c->live_mask_after_edit = still_live;
    }

    /* This recovery is solely the owned harness's registered signal action.
     * No SMC is executed as a system call, and no unrelated fault is skipped.
     */
    context->uc_mcontext.regs[0] = P4_RESTORED_X0;
    context->uc_mcontext.regs[1] = P4_RESTORED_X1;
    context->uc_mcontext.regs[8] = P4_RESTORED_X8;
    context->uc_mcontext.regs[9] = P4_RESTORED_X9;
    context->uc_mcontext.regs[10] = P4_RESTORED_X10;
    context->uc_mcontext.pstate =
        (context->uc_mcontext.pstate & ~UINT64_C(0xf0000000)) | P4_RESTORED_NZCV;
    context->uc_mcontext.pc = g_resume;
}

static void run_handler_case(int case_id) {
    struct sigaction original = {0}, action;
    bool installed = false, mask_changed = false;
    if (raw_mask(SIG_SETMASK, NULL, &g_result.original_mask) != 0) {
        problem(ST_SETUP, WHY_MASK_QUERY, errno); return;
    }
    if (sigaction(SIGILL, NULL, &original) != 0) {
        problem(ST_SETUP, WHY_ACTION_QUERY, errno); return;
    }
    g_result.old_action_flags = (unsigned long)original.sa_flags;
    g_result.old_action_pointer = (uintptr_t)original.sa_sigaction;
    g_result.old_action_mask = action_mask_bits(&original.sa_mask);
    memset(&action, 0, sizeof(action));
    action.sa_sigaction = capture_sigill;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    sigaddset(&action.sa_mask, SIGUSR1);
    g_fault = g_result.expected_fault; g_resume = g_result.expected_resume;
    g_edit_context_mask = case_id == CASE_SMC_MASK_EDIT;
    g_active = 1;
    if (sigaction(SIGILL, &action, NULL) != 0) {
        problem(ST_SETUP, WHY_ACTION_INSTALL, errno); goto cleanup;
    }
    installed = true;
    uint64_t enabled = g_result.original_mask & ~bit_for_signal(SIGILL);
    if (g_edit_context_mask) {
        enabled |= bit_for_signal(SIGUSR1);
        enabled &= ~bit_for_signal(SIGUSR2);
    }
    g_result.entered_mask = enabled;
    g_result.expected_resume_mask = g_edit_context_mask ?
        (enabled & ~bit_for_signal(SIGUSR1)) | bit_for_signal(SIGUSR2) : enabled;
    g_requested_resume_mask = g_result.expected_resume_mask |
        bit_for_signal(SIGKILL) | bit_for_signal(SIGSTOP);
    if (raw_mask(SIG_SETMASK, &enabled, NULL) != 0) {
        problem(ST_SETUP, WHY_MASK_SET, errno); goto cleanup;
    }
    mask_changed = true;
    g_result.opcode_before = instruction_word(g_result.expected_fault);
    g_result.asm_return = case_id == CASE_SVC ? p4_probe_svc(&g_result.after) :
                                              p4_probe_smc(&g_result.after);
    /* This is before any harness restoration. The explicit original-mask
     * cleanup below cannot make an ignored ucontext edit pass this check.
     */
    g_result.post_handler_mask_rc = raw_mask(SIG_SETMASK, NULL, &g_result.post_handler_mask);
    if (g_result.post_handler_mask_rc != 0) problem(ST_FAIL, WHY_MASK_QUERY, errno);
    g_result.opcode_after = instruction_word(g_result.expected_fault);

cleanup:
    if (installed) {
        g_result.action_restore_rc = sigaction(SIGILL, &original, NULL);
        if (g_result.action_restore_rc != 0) problem(ST_FAIL, WHY_ACTION_RESTORE, errno);
        else {
            struct sigaction restored = {0};
            g_result.action_readback_rc = sigaction(SIGILL, NULL, &restored);
            if (g_result.action_readback_rc != 0) problem(ST_FAIL, WHY_ACTION_RESTORE, errno);
            else {
                g_result.restored_action_flags = (unsigned long)restored.sa_flags;
                g_result.restored_action_pointer = (uintptr_t)restored.sa_sigaction;
                g_result.restored_action_mask = action_mask_bits(&restored.sa_mask);
                g_result.action_equal = restored.sa_flags == original.sa_flags &&
                    restored.sa_sigaction == original.sa_sigaction &&
                    g_result.restored_action_mask == g_result.old_action_mask;
                if (g_result.action_equal) g_result.checks |= C_ACTION_RESTORED;
                else problem(ST_FAIL, WHY_ACTION_RESTORE, 0);
            }
        }
    }
    if (mask_changed) {
        g_result.mask_restore_rc = (int)raw_mask(SIG_SETMASK, &g_result.original_mask, NULL);
        if (g_result.mask_restore_rc != 0) problem(ST_FAIL, WHY_MASK_RESTORE, errno);
    }
    g_active = 0;
    g_edit_context_mask = 0;
    if (raw_mask(SIG_SETMASK, NULL, &g_result.mask_after) != 0) problem(ST_FAIL, WHY_MASK_QUERY, errno);
    else if (g_result.mask_after == g_result.original_mask) g_result.checks |= C_MASK_RESTORED;
    if (g_result.reason != WHY_NONE) return;

    const struct capture* c = &g_result.capture;
    const struct p4_after* a = &g_result.after;
    if (c->count == 0) g_result.checks |= C_NO_SIGNAL;
    if (c->count == 1 && !c->unexpected) g_result.checks |= C_ONE_SIGNAL;
    if (c->signo == SIGILL && c->info_signo == SIGILL) g_result.checks |= C_SIGNO;
    if (c->code == ILL_ILLOPC && c->error == 0) g_result.checks |= C_CODE;
    if (c->address == g_result.expected_fault) g_result.checks |= C_ADDRESS;
    if (c->pc == g_result.expected_fault) g_result.checks |= C_PC;
    if (c->regs[0] == P4_BEFORE_X0 && c->regs[1] == P4_BEFORE_X1 &&
        c->regs[8] == SYS_getpid && c->regs[9] == P4_BEFORE_X9 && c->regs[10] == P4_BEFORE_X10)
        g_result.checks |= C_REGS_BEFORE;
    if ((c->pstate & P4_NZCV_MASK) == P4_BEFORE_NZCV) g_result.checks |= C_NZCV_BEFORE;
    if (c->context_sigill_blocked == 0 && c->context_sigusr1_blocked ==
        ((g_result.entered_mask & bit_for_signal(SIGUSR1)) ? 1 : 0)) g_result.checks |= C_CONTEXT_MASK;
    if (c->mask_rc == 0 && (c->handler_mask & bit_for_signal(SIGILL)) &&
        (c->handler_mask & bit_for_signal(SIGUSR1))) g_result.checks |= C_HANDLER_MASK;
    if (a->x0 == P4_RESTORED_X0 && a->x1 == P4_RESTORED_X1 && a->x8 == P4_RESTORED_X8 &&
        a->x9 == P4_RESTORED_X9 && a->x10 == P4_RESTORED_X10) g_result.checks |= C_REGS_RESTORED;
    if (a->sp != 0 && a->sp == c->sp) g_result.checks |= C_SP_RESTORED;
    if ((a->nzcv & P4_NZCV_MASK) == P4_RESTORED_NZCV) g_result.checks |= C_NZCV_RESTORED;
    if (a->resume_pc == g_result.expected_resume) g_result.checks |= C_RESUME_PC;
    if (a->cookie == P4_COOKIE) g_result.checks |= C_COOKIE;
    if (g_result.asm_return == (case_id == CASE_SVC ? (uint64_t)g_result.pid : P4_RESTORED_X0) &&
        a->x0 == g_result.asm_return) g_result.checks |= C_RETURN_VALUE;
    uint32_t expected = case_id == CASE_SVC ? UINT32_C(0xd4000001) : UINT32_C(0xd4000003);
    if (g_result.opcode_before == expected && g_result.opcode_after == expected) g_result.checks |= C_OPCODE_STABLE;
    g_result.required = C_RESUME_PC | C_COOKIE | C_RETURN_VALUE | C_MASK_RESTORED |
                        C_ACTION_RESTORED | C_OPCODE_STABLE;
    g_result.required |= case_id == CASE_SVC ? C_NO_SIGNAL :
        C_ONE_SIGNAL | C_SIGNO | C_CODE | C_ADDRESS | C_PC | C_REGS_BEFORE | C_NZCV_BEFORE |
        C_CONTEXT_MASK | C_HANDLER_MASK | C_REGS_RESTORED | C_SP_RESTORED | C_NZCV_RESTORED;
    if (case_id == CASE_SMC_MASK_EDIT) {
        if (c->context_kernel_mask == g_result.entered_mask) g_result.checks |= C_CONTEXT_MASK_FULL;
        if (g_result.post_handler_mask_rc == 0 &&
            g_result.post_handler_mask == g_result.expected_resume_mask)
            g_result.checks |= C_MASK_EDIT_APPLIED;
        if (c->context_requested_mask == (g_result.expected_resume_mask |
                bit_for_signal(SIGKILL) | bit_for_signal(SIGSTOP)) &&
            c->mask_after_edit_rc == 0 && c->live_mask_after_edit == c->handler_mask)
            g_result.checks |= C_MASK_EDIT_STAGED;
        g_result.required |= C_CONTEXT_MASK_FULL | C_MASK_EDIT_APPLIED | C_MASK_EDIT_STAGED;
    }
    if ((g_result.checks & g_result.required) != g_result.required) problem(ST_FAIL, WHY_CHECKS, 0);
}

static _Noreturn void child_error(struct child_shared* shared, int reason) {
    shared->setup_reason = reason; shared->setup_errno = errno;
    shared->phase = PHASE_CHILD_SETUP_ERROR;
    _exit(120);
}
static _Noreturn void default_child(struct child_shared* shared, pid_t parent) {
    shared->phase = PHASE_CHILD_STARTED;
    shared->pid = getpid(); shared->ppid = getppid();
    shared->tid = (pid_t)syscall(SYS_gettid);
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0) child_error(shared, 1);
    shared->pdeathsig = SIGKILL;
    if (getppid() != parent) { errno = ESRCH; child_error(shared, 2); }
    struct rlimit core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &core) != 0) child_error(shared, 3);
    struct sigaction dfl = {0};
    dfl.sa_handler = SIG_DFL;
    sigemptyset(&dfl.sa_mask);
    if (sigaction(SIGILL, &dfl, NULL) != 0) child_error(shared, 4);
    uint64_t mask = 0;
    if (raw_mask(SIG_SETMASK, NULL, &mask) != 0) child_error(shared, 5);
    mask &= ~bit_for_signal(SIGILL);
    if (raw_mask(SIG_SETMASK, &mask, NULL) != 0) child_error(shared, 6);
    shared->phase = PHASE_CHILD_READY;
    (void)p4_probe_smc(&shared->after);
    shared->phase = PHASE_CHILD_RETURNED;
    _exit(123);
}

static void copy_child_result(const struct child_shared* s) {
    g_result.child_phase = s->phase;
    g_result.child_setup_reason = s->setup_reason; g_result.child_setup_errno = s->setup_errno;
    g_result.child_recorded_pid = s->pid; g_result.child_recorded_ppid = s->ppid;
    g_result.child_recorded_tid = s->tid; g_result.child_pdeathsig = s->pdeathsig;
    g_result.after = s->after;
}
static bool reap_until(pid_t child, uint64_t deadline, int* status) {
    for (;;) {
        pid_t got = waitpid(child, status, WNOHANG);
        if (got == child) return true;
        if (got < 0 && errno != EINTR) { problem(ST_FAIL, WHY_WAIT, errno); return false; }
        uint64_t now = now_ns();
        if (!now || now >= deadline) return false;
        struct timespec pause = {0, 5000000L};
        (void)nanosleep(&pause, NULL);
    }
}
static void run_default_case(void) {
    struct sigaction child_action;
    if (sigaction(SIGCHLD, NULL, &child_action) != 0) { problem(ST_SETUP, WHY_ACTION_QUERY, errno); return; }
    g_result.sigchld_flags = (unsigned long)child_action.sa_flags;
    g_result.sigchld_pointer = (uintptr_t)child_action.sa_handler;
    /* A default, waitable child is required. Do not change a process-wide
     * reaper policy or signal a PID after an ECHILD result.
     */
    if (child_action.sa_handler != SIG_DFL || (child_action.sa_flags & SA_NOCLDWAIT)) {
        problem(ST_SETUP, WHY_CHILD_POLICY, 0); return;
    }
    struct child_shared* shared = mmap(NULL, sizeof(*shared), PROT_READ | PROT_WRITE,
                                     MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (shared == MAP_FAILED) { problem(ST_SETUP, WHY_MMAP, errno); return; }
    memset(shared, 0, sizeof(*shared));
    g_result.opcode_before = instruction_word(g_result.expected_fault);
    uint64_t started = now_ns();
    if (!started || started > UINT64_MAX - UINT64_C(3000000000)) {
        problem(ST_SETUP, WHY_CLOCK, errno); munmap(shared, sizeof(*shared)); return;
    }
    pid_t parent = getpid();
    pid_t child = fork();
    if (child < 0) { problem(ST_SETUP, WHY_FORK, errno); munmap(shared, sizeof(*shared)); return; }
    if (child == 0) default_child(shared, parent);
    g_result.child_pid = child;
    int status = 0;
    bool reaped = reap_until(child, started + UINT64_C(2000000000), &status);
    if (!reaped && g_result.reason == WHY_NONE) {
        g_result.timed_out = 1;
        problem(ST_TIMEOUT, WHY_CHILD_TIMEOUT, 0);
        /* This is the still-unreaped PID returned by our own fork, never a
         * name lookup. ECHILD above prevents sending a signal after lost ownership.
         */
        errno = 0; g_result.kill_rc = kill(child, SIGKILL); g_result.kill_errno = errno;
        uint64_t cleanup_start = now_ns();
        if (cleanup_start && cleanup_start <= UINT64_MAX - UINT64_C(1000000000))
            reaped = reap_until(child, cleanup_start + UINT64_C(1000000000), &status);
        if (!reaped) { g_result.reason = WHY_CHILD_CLEANUP; g_result.error = errno; }
    }
    g_result.child_reaped = reaped ? 1 : 0;
    g_result.wait_observed = reaped ? 1 : 0;
    if (reaped) g_result.wait_status = status;
    copy_child_result(shared);
    uint64_t ended = now_ns();
    if (ended >= started) g_result.child_elapsed_ns = ended - started;
    g_result.opcode_after = instruction_word(g_result.expected_fault);
    if (munmap(shared, sizeof(*shared)) != 0) problem(ST_FAIL, WHY_MMAP, errno);
    if (g_result.reason != WHY_NONE) return;
    if (g_result.child_phase == PHASE_CHILD_SETUP_ERROR) {
        problem(ST_SETUP, WHY_CHILD_SETUP, g_result.child_setup_errno); return;
    }
    if (g_result.child_phase == PHASE_CHILD_RETURNED) { problem(ST_FAIL, WHY_CHILD_RETURNED, 0); return; }
    if (g_result.child_phase == PHASE_CHILD_READY && g_result.child_recorded_pid == child &&
        g_result.child_recorded_ppid == parent && g_result.child_pdeathsig == SIGKILL) g_result.checks |= C_CHILD_READY;
    if (reaped) g_result.checks |= C_CHILD_REAPED;
    if (reaped && WIFSIGNALED(status) && WTERMSIG(status) == SIGILL) g_result.checks |= C_CHILD_SIGILL;
    const struct p4_after not_executed = {0};
    if (g_result.child_phase == PHASE_CHILD_READY &&
        memcmp(&g_result.after, &not_executed, sizeof(not_executed)) == 0) g_result.checks |= C_CHILD_NO_RETURN;
    if (!g_result.timed_out && ended && ended >= started && ended - started < UINT64_C(2000000000))
        g_result.checks |= C_WITHIN_DEADLINE;
    if (g_result.opcode_before == UINT32_C(0xd4000003) && g_result.opcode_after == UINT32_C(0xd4000003))
        g_result.checks |= C_OPCODE_STABLE;
    g_result.required = C_CHILD_READY | C_CHILD_REAPED | C_CHILD_SIGILL |
                        C_CHILD_NO_RETURN | C_WITHIN_DEADLINE | C_OPCODE_STABLE;
    if ((g_result.checks & g_result.required) != g_result.required) problem(ST_FAIL, WHY_CHILD_SIGNAL, 0);
}

struct json_writer { size_t used; bool failed; };
static void append(struct json_writer* w, const char* format, ...) {
    if (w->failed) return;
    va_list args; va_start(args, format);
    int n = vsnprintf(g_json + w->used, sizeof(g_json) - w->used, format, args);
    va_end(args);
    if (n < 0 || (size_t)n >= sizeof(g_json) - w->used) { w->failed = true; return; }
    w->used += (size_t)n;
}
static const char* format_result(void) {
    const struct result* r = &g_result;
    const struct capture* c = &r->capture;
    const struct p4_after* a = &r->after;
    struct json_writer w = {0, false};
    append(&w, "{\"schema\":1,\"case\":\"%s\",\"status\":\"%s\",\"reason\":%d,\"errno\":%d,"
           "\"pid\":%ld,\"tid\":%ld,\"elapsed_ns\":%" PRIu64 ",\"guest_isa\":\"aarch64\","
           "\"checks\":\"0x%016" PRIx64 "\",\"required_checks\":\"0x%016" PRIx64 "\",",
           case_name(r->case_id), status_name(r->status), r->reason, r->error,
           (long)r->pid, (long)r->tid, r->elapsed_ns, r->checks, r->required);
    append(&w, "\"instruction\":{\"fault_pc\":\"0x%016" PRIxPTR "\",\"resume_pc\":\"0x%016" PRIxPTR
           "\",\"word_before\":\"0x%08" PRIx32 "\",\"word_after\":\"0x%08" PRIx32 "\"},",
           r->expected_fault, r->expected_resume, r->opcode_before, r->opcode_after);
    append(&w, "\"signal\":{\"precise_siginfo_observed\":%s,\"count\":%d,\"unexpected\":%d,"
           "\"signo\":%d,\"info_signo\":%d,\"si_code\":%d,\"si_errno\":%d,"
           "\"si_addr\":\"0x%016" PRIxPTR "\",\"guest_pc\":\"0x%016" PRIxPTR
           "\",\"guest_sp\":\"0x%016" PRIxPTR "\",\"pstate\":\"0x%016" PRIx64 "\","
           "\"context_sigill_blocked\":%d,\"context_sigusr1_blocked\":%d,"
           "\"handler_mask_query_rc\":%ld,\"handler_kernel_mask\":\"0x%016" PRIx64 "\",\"x\":[",
           c->count ? "true" : "false", (int)c->count, (int)c->unexpected, c->signo, c->info_signo,
           c->code, c->error, c->address, c->pc, c->sp, c->pstate,
           c->context_sigill_blocked, c->context_sigusr1_blocked, c->mask_rc, c->handler_mask);
    for (size_t i = 0; i < 31; ++i) append(&w, "%s\"0x%016" PRIx64 "\"", i ? "," : "", c->regs[i]);
    append(&w, "]},\"after\":{\"x0\":\"0x%016" PRIx64 "\",\"x1\":\"0x%016" PRIx64
           "\",\"x8\":\"0x%016" PRIx64 "\",\"x9\":\"0x%016" PRIx64
           "\",\"x10\":\"0x%016" PRIx64 "\",\"sp\":\"0x%016" PRIx64
           "\",\"resume_pc\":\"0x%016" PRIx64 "\",\"cookie\":\"0x%016" PRIx64
           "\",\"nzcv\":\"0x%016" PRIx64 "\",\"return_value\":\"0x%016" PRIx64 "\"},",
           a->x0, a->x1, a->x8, a->x9, a->x10, a->sp, a->resume_pc, a->cookie, a->nzcv, r->asm_return);
    append(&w, "\"restore\":{\"mask_before\":\"0x%016" PRIx64 "\",\"mask_after\":\"0x%016" PRIx64
           "\",\"action_rc\":%d,\"mask_rc\":%d,\"action_readback_rc\":%d,\"action_equal\":%s,"
           "\"original_action_flags\":\"0x%lx\",\"original_action_pointer\":\"0x%016" PRIxPTR
           "\",\"original_action_mask\":\"0x%016" PRIx64 "\",\"restored_action_flags\":\"0x%lx\","
           "\"restored_action_pointer\":\"0x%016" PRIxPTR "\",\"restored_action_mask\":\"0x%016" PRIx64 "\"},",
           r->original_mask, r->mask_after, r->action_restore_rc, r->mask_restore_rc,
           r->action_readback_rc, r->action_equal ? "true" : "false",
           r->old_action_flags, r->old_action_pointer, r->old_action_mask,
           r->restored_action_flags, r->restored_action_pointer, r->restored_action_mask);
    append(&w, "\"mask_edit\":{\"requested\":%s,\"entered_kernel_mask\":\"0x%016" PRIx64
           "\",\"context_kernel_mask\":\"0x%016" PRIx64 "\",\"requested_context_mask\":\"0x%016" PRIx64
           "\",\"expected_resume_mask\":\"0x%016" PRIx64 "\",\"live_after_edit\":\"0x%016" PRIx64
           "\",\"live_after_edit_rc\":%ld,\"post_handler_kernel_mask\":\"0x%016" PRIx64
           "\",\"post_handler_query_rc\":%ld,\"sampled_before_harness_restore\":%s},",
           r->case_id == CASE_SMC_MASK_EDIT ? "true" : "false", r->entered_mask,
           c->context_kernel_mask, c->context_requested_mask, r->expected_resume_mask,
           c->live_mask_after_edit, c->mask_after_edit_rc, r->post_handler_mask, r->post_handler_mask_rc,
           r->post_handler_mask_rc == 0 ? "true" : "false");
    int signaled = r->wait_observed && WIFSIGNALED(r->wait_status);
    int exited = r->wait_observed && WIFEXITED(r->wait_status);
    append(&w, "\"child\":{\"pid\":%ld,\"recorded_pid\":%ld,\"recorded_ppid\":%ld,\"recorded_tid\":%ld,"
           "\"phase\":%d,\"setup_reason\":%d,\"setup_errno\":%d,\"pdeathsig\":%d,"
           "\"wait_observed\":%s,\"wait_status\":%d,\"wifsignaled\":%s,\"termination_signal\":%d,"
           "\"wifexited\":%s,\"exit_status\":%d,\"timed_out\":%s,\"kill_rc\":%d,\"kill_errno\":%d,"
           "\"reaped\":%s,\"elapsed_ns\":%" PRIu64 ",\"deadline_ms\":2000,\"cleanup_bound_ms\":1000,"
           "\"original_sigchld_flags\":\"0x%lx\",\"original_sigchld_pointer\":\"0x%016" PRIxPTR "\"}}",
           (long)r->child_pid, (long)r->child_recorded_pid, (long)r->child_recorded_ppid, (long)r->child_recorded_tid,
           r->child_phase, r->child_setup_reason, r->child_setup_errno, r->child_pdeathsig,
           r->wait_observed ? "true" : "false", r->wait_status, signaled ? "true" : "false",
           signaled ? WTERMSIG(r->wait_status) : 0, exited ? "true" : "false",
           exited ? WEXITSTATUS(r->wait_status) : 0, r->timed_out ? "true" : "false", r->kill_rc, r->kill_errno,
           r->child_reaped ? "true" : "false", r->child_elapsed_ns, r->sigchld_flags, r->sigchld_pointer);
    if (w.failed) return "{\"schema\":1,\"status\":\"SERIALIZATION_ERROR\"}";
    return g_json;
}

JNIEXPORT jstring JNICALL
Java_org_droidloom_signalprobe_r3_SignalProbeInstrumentation_nativeRun(JNIEnv* env, jclass klass, jint case_id) {
    (void)klass;
    if (atomic_flag_test_and_set_explicit(&g_running, memory_order_acquire))
        return (*env)->NewStringUTF(env, "{\"schema\":1,\"status\":\"BUSY\",\"reason\":2}");
    memset(&g_result, 0, sizeof(g_result));
    g_result.case_id = case_id; g_result.status = ST_PASS;
    g_result.pid = getpid(); g_result.tid = (pid_t)syscall(SYS_gettid);
    g_result.started_ns = now_ns();
    g_result.action_restore_rc = g_result.mask_restore_rc = -1;
    g_result.action_readback_rc = -1;
    g_result.post_handler_mask_rc = -1;
    g_result.capture.mask_after_edit_rc = -1;
    g_result.kill_rc = -1;
    if (!g_result.started_ns) problem(ST_SETUP, WHY_CLOCK, errno);
    else if (case_id < CASE_SVC || case_id > CASE_SMC_MASK_EDIT) problem(ST_SETUP, WHY_BAD_CASE, 0);
    else {
        g_result.expected_fault = (uintptr_t)(case_id == CASE_SVC ? p4_svc_fault : p4_smc_fault);
        g_result.expected_resume = (uintptr_t)(case_id == CASE_SVC ? p4_svc_resume : p4_smc_resume);
        if (case_id == CASE_SMC_DEFAULT) run_default_case();
        else run_handler_case(case_id);
    }
    uint64_t ended = now_ns();
    if (!ended || ended < g_result.started_ns) problem(ST_FAIL, WHY_CLOCK, errno);
    else g_result.elapsed_ns = ended - g_result.started_ns;
    jstring output = (*env)->NewStringUTF(env, format_result());
    atomic_flag_clear_explicit(&g_running, memory_order_release);
    return output;
}
