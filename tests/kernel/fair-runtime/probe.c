// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define BASE "/sys/fs/cgroup/hepta-fair-runtime"
#define LEAF BASE "/work"
static int failures;
static void check(const char *name, int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, ok ? "true" : "false");
    failures += !ok;
}
static int write_file(const char *path, const char *value) {
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    ssize_t result = write(fd, value, strlen(value));
    int saved = errno;
    close(fd); errno = saved;
    return result == (ssize_t)strlen(value) ? 0 : -1;
}
static uint64_t stamp(clockid_t clock) {
    struct timespec value;
    if (clock_gettime(clock, &value)) _exit(90);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}
static uint64_t stat_value(const char *key) {
    char content[1024] = {0};
    int fd = open(LEAF "/cpu.stat", O_RDONLY);
    ssize_t size = fd < 0 ? -1 : read(fd, content, sizeof(content) - 1);
    if (fd >= 0) close(fd);
    if (size <= 0) return UINT64_MAX;
    char *at = strstr(content, key);
    return at ? strtoull(at + strlen(key), NULL, 10) : UINT64_MAX;
}
struct measurement { uint64_t wall_ns, cpu_ns; };
static int measure(struct measurement *result) {
    int report[2];
    if (pipe(report)) return -1;
    pid_t child = fork();
    if (child < 0) { close(report[0]); close(report[1]); return -1; }
    if (!child) {
        close(report[0]);
        char pid[32]; snprintf(pid, sizeof(pid), "%d", getpid());
        if (write_file(LEAF "/cgroup.procs", pid)) _exit(91);
        uint64_t wall = stamp(CLOCK_MONOTONIC), cpu = stamp(CLOCK_PROCESS_CPUTIME_ID);
        volatile uint64_t work = 1;
        do {
            for (unsigned i = 0; i < 8192; i++) work = work * 1664525 + 1013904223;
        } while (stamp(CLOCK_MONOTONIC) - wall < 1000000000ULL);
        struct measurement value = {stamp(CLOCK_MONOTONIC) - wall,
                                    stamp(CLOCK_PROCESS_CPUTIME_ID) - cpu};
        int ok = write(report[1], &value, sizeof(value)) == sizeof(value);
        close(report[1]); _exit(ok ? 0 : 92);
    }
    close(report[1]);
    ssize_t bytes = read(report[0], result, sizeof(*result));
    close(report[0]);
    int status;
    return waitpid(child, &status, 0) == child && WIFEXITED(status) &&
           WEXITSTATUS(status) == 0 && bytes == sizeof(*result) ? 0 : -1;
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
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(30);
    if (geteuid() || write_file("/sys/fs/cgroup/cgroup.subtree_control", "+cpu") ||
        mkdir(BASE, 0755) || write_file(BASE "/cgroup.subtree_control", "+cpu") ||
        mkdir(LEAF, 0755)) { perror("fair runtime fixture"); return 77; }
    errno = 0;
    int weight = write_file(LEAF "/cpu.weight", "200");
    check("fair_w1_cpu_weight_remains_unsupported", weight < 0 && errno == EINVAL);
    struct measurement unlimited = {0}, limited = {0};
    int unrestricted = write_file(LEAF "/cpu.max", "max 100000") || measure(&unlimited);
    int restricted = write_file(LEAF "/cpu.max", "20000 100000") || measure(&limited);
    check("fair_w1_real_children_complete", !unrestricted && !restricted);
    uint64_t unlimited_rate = unlimited.wall_ns ? unlimited.cpu_ns * 10000 / unlimited.wall_ns : 0;
    uint64_t limited_rate = limited.wall_ns ? limited.cpu_ns * 10000 / limited.wall_ns : 0;
    uint64_t throttled = stat_value("nr_throttled ");
    printf("{\"unlimited_wall_ns\":%llu,\"unlimited_cpu_ns\":%llu,"
           "\"limited_wall_ns\":%llu,\"limited_cpu_ns\":%llu,\"nr_throttled\":%llu}\n",
           (unsigned long long)unlimited.wall_ns, (unsigned long long)unlimited.cpu_ns,
           (unsigned long long)limited.wall_ns, (unsigned long long)limited.cpu_ns,
           (unsigned long long)throttled);
    check("fair_w1_unlimited_work_is_not_starved", !unrestricted && unlimited_rate >= 4000);
    check("fair_w1_original_cpu_max_still_limits_actual_cpu_time",
          !restricted && limited_rate >= 500 && limited_rate <= 5500 &&
          limited_rate * 100 < unlimited_rate * 65);
    check("fair_w1_original_cpu_max_records_throttling", throttled != UINT64_MAX && throttled > 0);
    check("fair_w1_leaf_released", !remove_after_release(LEAF));
    check("fair_w1_parent_released", !remove_after_release(BASE));
    return failures ? 42 : 0;
}
