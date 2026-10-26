// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define BASE "/sys/fs/cgroup/w3b-force-affinity"
#define LEAF BASE "/limited"
#define OBSERVE_NS 250000000ULL
struct worker { _Atomic int ready, after_sleep, stop, cpu; _Atomic uint64_t count; };
static int failures, source_cpu, target_cpu;
static uint64_t stamp(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) _exit(90);
    return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
}
static void sleep_ns(uint64_t ns) {
    struct timespec t = {(time_t)(ns / 1000000000ULL), (long)(ns % 1000000000ULL)};
    while (nanosleep(&t, &t) && errno == EINTR) {}
}
static int getcpu_direct(void) {
    unsigned cpu = UINT32_MAX;
    return syscall(SYS_getcpu, &cpu, NULL, NULL) ? -1 : (int)cpu;
}
static void check(const char *name, int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, ok ? "true" : "false");
    failures += !ok;
}
static int pin(pid_t pid, int cpu) {
    cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set);
    return sched_setaffinity(pid, sizeof(set), &set);
}
static int mask_is(pid_t pid, int cpu) {
    cpu_set_t set;
    return !sched_getaffinity(pid, sizeof(set), &set) &&
           CPU_COUNT(&set) == 1 && CPU_ISSET(cpu, &set);
}
static int write_file(const char *path, const char *text) {
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    ssize_t n = write(fd, text, strlen(text)); int saved = errno;
    close(fd); errno = saved;
    return n == (ssize_t)strlen(text) ? 0 : -1;
}
static int proc_info(pid_t pid, char *state, int *cpu) {
    char path[64], data[2048];
    snprintf(path, sizeof(path), "/proc/%d/stat", pid);
    int fd = open(path, O_RDONLY);
    ssize_t n = fd < 0 ? -1 : read(fd, data, sizeof(data) - 1);
    if (fd >= 0) close(fd);
    if (n <= 0) return -1;
    data[n] = 0;
    char *tail = strrchr(data, ')'), *save = NULL;
    if (!tail || tail[1] != ' ') return -1;
    char *word = strtok_r(tail + 2, " ", &save);
    for (int field = 3; word; field++, word = strtok_r(NULL, " ", &save)) {
        if (field == 3) *state = word[0];
        if (field == 39) { *cpu = atoi(word); return 0; }
    }
    return -1;
}
static uint64_t throttles(void) {
    char data[2048] = {0}; int fd = open(LEAF "/cpu.stat", O_RDONLY);
    ssize_t n = fd < 0 ? -1 : read(fd, data, sizeof(data) - 1);
    if (fd >= 0) close(fd);
    char *p = n > 0 ? strstr(data, "nr_throttled ") : NULL;
    return p ? strtoull(p + strlen("nr_throttled "), NULL, 10) : UINT64_MAX;
}
static struct worker *shared(void) {
    struct worker *w = mmap(NULL, sizeof(*w), PROT_READ | PROT_WRITE,
                           MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (w == MAP_FAILED) return NULL;
    memset(w, 0, sizeof(*w)); atomic_store(&w->cpu, -1); return w;
}
static void busy(struct worker *w) {
    while (!atomic_load_explicit(&w->stop, memory_order_acquire)) {
        atomic_store_explicit(&w->cpu, getcpu_direct(), memory_order_release);
        atomic_fetch_add_explicit(&w->count, 1, memory_order_relaxed);
    }
}
/* Every child establishes its own mask; fork affinity inheritance is not assumed. */
static pid_t start_worker(struct worker *w, uint64_t sleep_before, int limited, int rt) {
    pid_t child = fork();
    if (child) return child;
    alarm(15);
    if (limited) {
        char pid[32]; snprintf(pid, sizeof(pid), "%d", getpid());
        if (write_file(LEAF "/cgroup.procs", pid)) _exit(91);
    }
    if (pin(0, source_cpu)) _exit(92);
    sleep_ns(10000000);
    if (getcpu_direct() != source_cpu) _exit(93);
    if (rt) {
        struct sched_param p = {.sched_priority = 80};
        if (sched_setscheduler(0, SCHED_FIFO, &p)) _exit(94);
    }
    atomic_store_explicit(&w->cpu, getcpu_direct(), memory_order_release);
    atomic_store_explicit(&w->ready, 1, memory_order_release);
    if (sleep_before) sleep_ns(sleep_before);
    atomic_store_explicit(&w->after_sleep, 1, memory_order_release);
    busy(w); _exit(0);
}
static int wait_ready(struct worker *w, uint64_t timeout) {
    uint64_t end = stamp() + timeout;
    while (stamp() < end) {
        if (atomic_load_explicit(&w->ready, memory_order_acquire)) return 1;
        sleep_ns(2000000);
    }
    return 0;
}
static int wait_cpu(struct worker *w, int cpu, uint64_t timeout) {
    uint64_t end = stamp() + timeout;
    while (stamp() < end) {
        if (atomic_load_explicit(&w->cpu, memory_order_acquire) == cpu &&
            atomic_load_explicit(&w->count, memory_order_acquire) > 0) return 1;
        sleep_ns(2000000);
    }
    return 0;
}
static int stop_join(pid_t pid, struct worker *w) {
    if (pid <= 0) return 0;
    atomic_store_explicit(&w->stop, 1, memory_order_release);
    int status;
    return waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
static void current_case(void) {
    struct worker *w = shared(); if (!w) { check("setup_current_shared", 0); return; }
    pid_t pid = start_worker(w, 0, 0, 0);
    int setup = pid > 0 && wait_ready(w, 500000000) && wait_cpu(w, source_cpu, 100000000);
    check("setup_current_busy_on_measured_source", setup);
    uint64_t before = atomic_load(&w->count); sleep_ns(20000000);
    check("control_current_busy_progress", setup && atomic_load(&w->count) > before);
    int changed = pid > 0 && !pin(pid, target_cpu) && mask_is(pid, target_cpu);
    check("control_current_new_mask_accepted", changed);
    int moved = changed && wait_cpu(w, target_cpu, OBSERVE_NS);
    printf("{\"mode\":\"current\",\"source\":%d,\"destination\":%d,\"observed_cpu\":%d,\"count\":%llu}\n",
           source_cpu, target_cpu, atomic_load(&w->cpu), (unsigned long long)atomic_load(&w->count));
    check("force_current_migrates", moved);
    check("control_current_join", stop_join(pid, w)); munmap(w, sizeof(*w));
}
static void queued_case(void) {
    struct worker *w = shared(), *hog = shared();
    if (!w || !hog) { check("setup_queued_shared", 0); return; }
    pid_t pid = start_worker(w, 150000000, 0, 0);
    int ready = pid > 0 && wait_ready(w, 500000000);
    char state = '?'; int cpu = -1;
    int sleeping = ready && !proc_info(pid, &state, &cpu) && state == 'S';
    check("setup_queued_candidate_timer_sleep", sleeping);
    /* Parent must physically leave source before the non-sleeping RT hog starts. */
    int parent_safe = !pin(0, target_cpu); sleep_ns(10000000);
    parent_safe = parent_safe && getcpu_direct() == target_cpu;
    check("setup_queued_parent_on_idle_destination", parent_safe);
    pid_t hp = parent_safe && sleeping ? start_worker(hog, 0, 0, 1) : -1;
    int hr = hp > 0 && wait_ready(hog, 500000000);
    sleep_ns(180000000);
    uint64_t progress = atomic_load(&hog->count); sleep_ns(20000000);
    int blocked = hr && sched_getscheduler(hp) == SCHED_FIFO &&
                  atomic_load(&hog->cpu) == source_cpu && atomic_load(&hog->count) > progress &&
                  !proc_info(pid, &state, &cpu) && state == 'R' && !atomic_load(&w->after_sleep);
    check("setup_queued_fair_runnable_behind_live_rt_hog", blocked);
    int changed = blocked && !pin(pid, target_cpu) && mask_is(pid, target_cpu);
    check("control_queued_new_mask_accepted", changed);
    int moved = changed && wait_cpu(w, target_cpu, OBSERVE_NS) && atomic_load(&w->after_sleep);
    printf("{\"mode\":\"queued\",\"source\":%d,\"destination\":%d,\"candidate_state\":\"%c\",\"after_sleep\":%d,\"observed_cpu\":%d,\"hog_progress\":%llu}\n",
           source_cpu, target_cpu, state, atomic_load(&w->after_sleep), atomic_load(&w->cpu),
           (unsigned long long)atomic_load(&hog->count));
    check("force_queued_migrates", moved);
    atomic_store(&w->stop, 1);
    check("control_queued_rt_hog_join", stop_join(hp, hog));
    check("control_queued_candidate_join", stop_join(pid, w));
    munmap(w, sizeof(*w)); munmap(hog, sizeof(*hog));
}
static void throttled_case(void) {
    int fixture = !write_file("/sys/fs/cgroup/cgroup.subtree_control", "+cpu") &&
                  !mkdir(BASE, 0755) && !write_file(BASE "/cgroup.subtree_control", "+cpu") &&
                  !mkdir(LEAF, 0755) && !write_file(LEAF "/cpu.max", "max 1000000");
    check("setup_throttled_original_cpu_max_owner", fixture);
    if (!fixture) return;
    struct worker *w = shared(); if (!w) { check("setup_throttled_shared", 0); return; }
    pid_t pid = start_worker(w, 0, 1, 0);
    int ready = pid > 0 && wait_ready(w, 500000000) && wait_cpu(w, source_cpu, 100000000);
    check("setup_throttled_busy_on_source", ready);
    /* Start close to a real one-second quota boundary, leaving >750ms for observations. */
    uint64_t phase = stamp() % 1000000000ULL;
    if (phase > 50000000ULL) sleep_ns(1000000000ULL - phase + 20000000ULL);
    int limited = ready && !write_file(LEAF "/cpu.max", "1000 1000000");
    uint64_t end = stamp() + 150000000ULL, stable = 0;
    while (limited && stamp() < end) {
        stable = atomic_load(&w->count); sleep_ns(20000000);
        if (stable == atomic_load(&w->count) && throttles() > 0 && throttles() != UINT64_MAX) break;
    }
    char state = '?'; int tagged = -1;
    int parked = limited && stable > 0 && stable == atomic_load(&w->count) &&
                 throttles() > 0 && throttles() != UINT64_MAX &&
                 !proc_info(pid, &state, &tagged) && state == 'R' && tagged == source_cpu;
    check("setup_throttled_runnable_counter_stable", parked);
    int changed = parked && !pin(pid, target_cpu) && mask_is(pid, target_cpu);
    check("control_throttled_new_mask_accepted", changed);
    sleep_ns(50000000);
    int tag_read = !proc_info(pid, &state, &tagged);
    check("control_throttled_migration_grants_no_budget", changed && atomic_load(&w->count) == stable);
    int unlimit = !write_file(LEAF "/cpu.max", "max 1000000");
    int progress = unlimit && wait_cpu(w, atomic_load(&w->cpu), OBSERVE_NS) &&
                   atomic_load(&w->count) > stable;
    /* Require fresh progress before accepting the last CPU observation. */
    uint64_t recovery_end = stamp() + OBSERVE_NS;
    while (!progress && stamp() < recovery_end) {
        sleep_ns(2000000); progress = unlimit && atomic_load(&w->count) > stable;
    }
    check("control_throttled_original_owner_unlimit_recovers", progress);
    int moved = tag_read && tagged == target_cpu && progress && atomic_load(&w->cpu) == target_cpu;
    printf("{\"mode\":\"throttled\",\"source\":%d,\"destination\":%d,\"owner_cpu_tag\":%d,\"recovery_getcpu\":%d,\"stable_count\":%llu,\"recovery_count\":%llu}\n",
           source_cpu, target_cpu, tagged, atomic_load(&w->cpu),
           (unsigned long long)stable, (unsigned long long)atomic_load(&w->count));
    check("force_throttled_owner_migrates", moved);
    check("control_throttled_child_join", stop_join(pid, w)); munmap(w, sizeof(*w));
    int leaf = -1;
    for (int i = 0; i < 100; i++) { leaf = rmdir(LEAF); if (!leaf || errno != EBUSY) break; sleep_ns(10000000); }
    check("control_throttled_leaf_cleanup", !leaf);
    check("control_throttled_parent_cleanup", !rmdir(BASE));
}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(40);
    cpu_set_t allowed; int first = -1, second = -1;
    if (!sched_getaffinity(0, sizeof(allowed), &allowed)) {
        for (int i = 0; i < CPU_SETSIZE; i++) if (CPU_ISSET(i, &allowed)) {
            if (first < 0) first = i; else { second = i; break; }
        }
    }
    source_cpu = first; target_cpu = second;
    check("setup_two_allowed_cpus_and_root", first >= 0 && second >= 0 && !geteuid());
    if (first < 0 || second < 0 || geteuid()) return 77;
    int pinned = !pin(0, target_cpu); sleep_ns(10000000);
    check("setup_parent_physically_on_destination", pinned && getcpu_direct() == target_cpu);
    if (!pinned || getcpu_direct() != target_cpu) return 77;
    current_case(); queued_case(); throttled_case();
    return failures ? 42 : 0;
}
