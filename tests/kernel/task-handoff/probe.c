// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define BASE "/sys/fs/cgroup/hepta-task-handoff"
#define LEAF BASE "/work"
static int failures, cpus[CPU_SETSIZE], ncpus;
static void check(const char *name, int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, ok ? "true" : "false");
    failures += !ok;
}
static int cpu_now(void) {
    unsigned cpu = 0;
    return syscall(SYS_getcpu, &cpu, NULL, NULL) ? -1 : (int)cpu;
}
static uint64_t stamp(clockid_t clock) {
    struct timespec value;
    if (clock_gettime(clock, &value)) _exit(90);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}
static int write_file(const char *path, const char *value) {
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    ssize_t result = write(fd, value, strlen(value));
    int saved = errno; close(fd); errno = saved;
    return result == (ssize_t)strlen(value) ? 0 : -1;
}
struct report { int cpu, pid, tid, round; uint64_t wall, cpu_time; };
struct measurement { uint64_t wall, cpu_time; };
static int exercise(unsigned rounds, uint64_t work_ns, int timed_sleep, struct measurement *result) {
    int go[2], replies[2];
    if (pipe(go) || pipe(replies)) return -1;
    pid_t child = fork();
    if (child < 0) return -1;
    if (!child) {
        close(go[1]); close(replies[0]);
        char pid[32]; snprintf(pid, sizeof(pid), "%d", getpid());
        if (write_file(LEAF "/cgroup.procs", pid)) _exit(91);
        uint64_t start_wall = stamp(CLOCK_MONOTONIC), start_cpu = stamp(CLOCK_PROCESS_CPUTIME_ID);
        for (unsigned round = 0; round <= rounds; round++) {
            struct report value = {cpu_now(), getpid(), (int)syscall(SYS_gettid), (int)round,
                                   stamp(CLOCK_MONOTONIC) - start_wall,
                                   stamp(CLOCK_PROCESS_CPUTIME_ID) - start_cpu};
            if (write(replies[1], &value, sizeof(value)) != sizeof(value)) _exit(92);
            if (round == rounds) break;
            char command;
            if (read(go[0], &command, 1) != 1) _exit(93);
            // Even if the pipe wake races before park, this explicit timer
            // wait occurs after the parent published the requested mask.
            if (timed_sleep) {
                struct timespec duration = {0, 10000000};
                while (nanosleep(&duration, &duration) && errno == EINTR) {}
            }
            uint64_t began = stamp(CLOCK_PROCESS_CPUTIME_ID);
            volatile uint64_t work = 1;
            do {
                for (unsigned i = 0; i < 8192; i++) work = work * 1664525 + 1013904223;
            } while (stamp(CLOCK_PROCESS_CPUTIME_ID) - began < work_ns);
        }
        close(go[0]); close(replies[1]); _exit(0);
    }
    close(go[0]); close(replies[1]);
    int accepted = 1, valid = 1, expected = -1;
    for (unsigned round = 0; round <= rounds; round++) {
        struct report value;
        if (read(replies[0], &value, sizeof(value)) != sizeof(value)) { valid = 0; break; }
        valid &= value.pid == child && value.tid == child && value.round == (int)round;
        int known = 0;
        for (int i = 0; i < ncpus; i++) known |= value.cpu == cpus[i];
        valid &= known;
        if (round && timed_sleep) valid &= value.cpu == expected;
        result->wall = value.wall; result->cpu_time = value.cpu_time;
        if (round == rounds) break;
        expected = cpus[round % (unsigned)ncpus];
        cpu_set_t desired; CPU_ZERO(&desired); CPU_SET(expected, &desired);
        accepted &= !sched_setaffinity(child, sizeof(desired), &desired);
        if (write(go[1], "g", 1) != 1) { valid = 0; break; }
    }
    close(go[1]); close(replies[0]);
    int status = 0;
    int reaped = waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
    printf("{\"rounds\":%u,\"timed_sleep\":%d,\"work_ns\":%llu,\"wall_ns\":%llu,\"cpu_ns\":%llu,\"accepted\":%d,\"identity_and_cpu\":%d,\"reaped\":%d}\n",
           rounds, timed_sleep, (unsigned long long)work_ns,
           (unsigned long long)result->wall, (unsigned long long)result->cpu_time, accepted, valid, reaped);
    return accepted && valid && reaped ? 0 : -1;
}
static int remove_after_release(const char *path) {
    for (unsigned i = 0; i < 100; i++) {
        if (!rmdir(path)) return 0;
        if (errno != EBUSY) return -1;
        struct timespec delay = {0, 10000000}; nanosleep(&delay, NULL);
    }
    return -1;
}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(50);
    cpu_set_t available;
    if (geteuid() || sched_getaffinity(0, sizeof(available), &available)) return 77;
    for (int cpu = 0; cpu < CPU_SETSIZE; cpu++) if (CPU_ISSET(cpu, &available)) cpus[ncpus++] = cpu;
    if (ncpus < 2 || write_file("/sys/fs/cgroup/cgroup.subtree_control", "+cpu") ||
        mkdir(BASE, 0755) || write_file(BASE "/cgroup.subtree_control", "+cpu") || mkdir(LEAF, 0755)) return 77;
    errno = 0;
    int unsupported = write_file(LEAF "/cpu.weight", "200");
    check("handoff_cpu_weight_still_einval", unsupported < 0 && errno == EINVAL);
    struct measurement route = {0}, race = {0}, unlimited = {0}, limited = {0};
    check("handoff_same_task_all_cpus_24_completed_waits", !exercise(24, 0, 1, &route));
    check("handoff_immediate_pipe_wakes_no_loss_or_duplicate_256", !exercise(256, 0, 0, &race));
    int unrestricted = write_file(LEAF "/cpu.max", "max 100000") || exercise(8, 100000000, 1, &unlimited);
    int restricted = write_file(LEAF "/cpu.max", "20000 100000") || exercise(8, 100000000, 1, &limited);
    check("handoff_migrating_cpu_max_children_complete", !unrestricted && !restricted);
    uint64_t unrate = unlimited.wall ? unlimited.cpu_time * 10000 / unlimited.wall : 0;
    uint64_t rate = limited.wall ? limited.cpu_time * 10000 / limited.wall : 0;
    check("handoff_unlimited_cpu_work_progresses", !unrestricted && unrate >= 4000);
    check("handoff_migration_preserves_original_cpu_max_debt", !restricted && rate >= 500 && rate <= 5500 && rate * 100 < unrate * 65);
    check("handoff_leaf_released", !remove_after_release(LEAF));
    check("handoff_parent_released", !remove_after_release(BASE));
    return failures ? 42 : 0;
}
