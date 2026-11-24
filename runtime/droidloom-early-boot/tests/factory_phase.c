// SPDX-License-Identifier: GPL-3.0-or-later
// Compile the actual board reader; dead-code elimination discards PID 1 startup.
// This checks only the original pipe/PIDFD mechanism, never a boot role.
#define main droidloom_board_init_unused_main
#include "../board_init.c"
#undef main
#include <assert.h>
#include <sys/time.h>

static unsigned int reports;
static int reported_errno;
static char reported_stage[320];
void droidloom_boot_diagnostics_report(enum droidloom_boot_diagnostic_phase phase,
                                      const char *stage, int error)
{
    assert(phase == DROIDLOOM_DIAGNOSTIC_PID1);
    reports++;
    reported_errno = error;
    snprintf(reported_stage, sizeof(reported_stage), "%s", stage);
}
struct sample { struct boot_factory factory; pid_t pid; };

static struct sample sample(const unsigned char *payload, size_t size,
                            int close_output, int hold)
{
    int pipefd[2], gate[2], pidfd = -1;
    assert(pipe2(pipefd, O_CLOEXEC) == 0);
    assert(pipe2(gate, O_CLOEXEC) == 0);
    struct clone_args spawn = {
        .flags = CLONE_PIDFD, .pidfd = (uint64_t)(uintptr_t)&pidfd,
        .exit_signal = SIGCHLD
    };
    pid_t child = (pid_t)syscall(SYS_clone3, &spawn, sizeof(spawn));
    assert(child >= 0);
    if (!child) {
        close(pipefd[0]); close(gate[1]);
        if (size && write(pipefd[1], payload, size) != (ssize_t)size)
            _exit(91);
        if (close_output)
            close(pipefd[1]);
        if (hold) {
            unsigned char go;
            if (read(gate[0], &go, 1) < 0)
                _exit(92);
        }
        _exit(0);
    }
    close(pipefd[1]); close(gate[0]);
    return (struct sample) {
        .factory = { .pidfd = pidfd, .receive = pipefd[0], .release = gate[1] },
        .pid = child
    };
}

static void reset_report(void)
{
    reports = 0; reported_errno = 0; reported_stage[0] = 0;
}

static void wait_exited(struct sample *s)
{
    struct pollfd ended = { .fd = s->factory.pidfd, .events = POLLIN };
    assert(poll(&ended, 1, 2000) == 1 && (ended.revents & POLLIN));
}

static void retire(struct sample *s)
{
    close(s->factory.release);
    siginfo_t info = {0};
    assert(waitid(P_PIDFD, s->factory.pidfd, &info, WEXITED) == 0);
    assert(info.si_pid == s->pid && info.si_code == CLD_EXITED && info.si_status == 0);
    close(s->factory.receive); close(s->factory.pidfd);
}

static void rejected(const unsigned char *frame, size_t size)
{
    struct sample s = sample(frame, size, 0, 1);
    reset_report();
    assert(factory_phase(&s.factory, 'F') == -1 && errno == EPROTO);
    retire(&s);
}

static volatile sig_atomic_t interruptions;
static void interrupted(int signal_number) { (void)signal_number; interruptions++; }

int main(void)
{
    unsigned int cases = 0;
    const unsigned char error[] = { 'E', 1, 3, 6, EACCES, 0, 0, 0, 'l','s','m','-','a','a' };
    struct sample s = sample(error, sizeof(error), 1, 0);
    wait_exited(&s);
    reset_report();
    assert(factory_phase(&s.factory, 'F') == -1 && errno == EACCES);
    assert(reports == 1 && reported_errno == EACCES &&
           strstr(reported_stage, "native prepare") && strstr(reported_stage, "lsm-aa"));
    retire(&s); cases++;

    const unsigned char ready[] = { 'F' };
    s = sample(ready, sizeof(ready), 1, 0);
    wait_exited(&s);
    reset_report();
    assert(factory_phase(&s.factory, 'F') == -1 && errno == ECHILD);
    assert(strstr(reported_stage, "queued ready from exited child"));
    retire(&s); cases++;

    s = sample(ready, sizeof(ready), 0, 1);
    assert(factory_phase(&s.factory, 'F') == 0);
    struct pollfd live = { .fd = s.factory.pidfd, .events = POLLIN };
    assert(poll(&live, 1, 0) == 0);
    retire(&s); cases++;

    /* Closing stdout after losing a buffered F is HUP, not process exit. */
    s = sample(NULL, 0, 1, 1);
    reset_report();
    assert(factory_phase(&s.factory, 'F') == -1 && errno == EPIPE);
    live = (struct pollfd) { .fd = s.factory.pidfd, .events = POLLIN };
    assert(poll(&live, 1, 0) == 0);
    assert(strstr(reported_stage, "channel EOF") && strstr(reported_stage, "pidfd=0x0"));
    retire(&s); cases++;

    const unsigned char short_frame[] = { 'E', 1, 3 };
    s = sample(short_frame, sizeof(short_frame), 1, 0);
    wait_exited(&s);
    assert(factory_phase(&s.factory, 'F') == -1 && errno == EPROTO);
    retire(&s); cases++;

    unsigned char bad[sizeof(error)];
    memcpy(bad, error, sizeof(error)); bad[1] = 2;
    rejected(bad, sizeof(bad)); cases++;
    memcpy(bad, error, sizeof(error)); bad[2] = 0;
    rejected(bad, sizeof(bad)); cases++;
    memcpy(bad, error, sizeof(error)); bad[3] = 241;
    rejected(bad, FACTORY_ERROR_HEADER); cases++;
    memcpy(bad, error, sizeof(error)); bad[8] = '\n';
    rejected(bad, sizeof(bad)); cases++;
    memcpy(bad, error, sizeof(error)); bad[7] = 1;
    rejected(bad, sizeof(bad)); cases++;

    /* Repeated EINTR and a partial frame cannot restart the absolute budget. */
    s = sample(short_frame, sizeof(short_frame), 0, 1);
    struct sigaction action = { .sa_handler = interrupted }, previous;
    sigemptyset(&action.sa_mask);
    assert(sigaction(SIGALRM, &action, &previous) == 0);
    struct itimerval timer = { .it_interval = { .tv_usec = 10000 },
                              .it_value = { .tv_usec = 10000 } };
    assert(setitimer(ITIMER_REAL, &timer, NULL) == 0);
    struct timespec begin, deadline, ended;
    assert(clock_gettime(CLOCK_MONOTONIC, &begin) == 0);
    deadline = begin;
    deadline.tv_nsec += 100000000L;
    if (deadline.tv_nsec >= 1000000000L) { deadline.tv_sec++; deadline.tv_nsec -= 1000000000L; }
    assert(factory_phase_until(&s.factory, 'F', &deadline) == -1 && errno == ETIMEDOUT);
    assert(clock_gettime(CLOCK_MONOTONIC, &ended) == 0);
    timer = (struct itimerval) {0};
    assert(setitimer(ITIMER_REAL, &timer, NULL) == 0);
    assert(sigaction(SIGALRM, &previous, NULL) == 0);
    int64_t elapsed = (int64_t)(ended.tv_sec - begin.tv_sec) * 1000000000LL +
                      ended.tv_nsec - begin.tv_nsec;
    assert(interruptions > 0 && elapsed >= 75000000LL && elapsed < 500000000LL);
    retire(&s); cases++;

    printf("actual factory pipe/PIDFD reader: %u cases passed; production_qualified=false\n", cases);
    return 0;
}
