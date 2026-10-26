// SPDX-License-Identifier: MPL-2.0
/* Guest-only regression for Desktop #267's selected-frame memory controller.
 * Adapted from #268's anonymous-budget probe; this uses the existing frame
 * owner and memory.* ABI, not a second hepta.anon.* ledger. The pressure observer
 * stays outside WORK, so its next COW fault can still drive sibling recovery. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define BASE "/sys/fs/cgroup/hepta-safety"
#define WORK BASE "/work"
#define RECOVERY BASE "/recovery"
#define CONCURRENT BASE "/concurrent"
#define PAGE 4096UL
static int failures;
static void check(const char *name, int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, ok ? "true" : "false");
    failures += !ok;
}
static int write_file(const char *path, const char *s) {
    int fd = open(path, O_WRONLY); if (fd < 0) return -1;
    size_t n = strlen(s); ssize_t rc = write(fd, s, n); int saved = errno;
    close(fd); errno = saved; return rc == (ssize_t)n ? 0 : -1;
}
static unsigned long read_number(const char *path) {
    char b[64] = {0}; int fd = open(path, O_RDONLY); if (fd < 0) return ~0UL;
    ssize_t n = read(fd, b, sizeof(b)-1); close(fd); if (n <= 0) return ~0UL;
    return strtoul(b, NULL, 10);
}
static int join(const char *path) {
    char pid[32]; snprintf(pid, sizeof(pid), "%d", getpid()); return write_file(path, pid);
}
static volatile unsigned char *pages(size_t n) {
    void *p = mmap(NULL, n * PAGE, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    return p == MAP_FAILED ? NULL : p;
}
static void touch(volatile unsigned char *p, size_t n) {
    for (size_t i = 0; i < n; i++) p[i * PAGE] = (unsigned char)(i + 1);
}
static unsigned long read_events(const char *path) {
    char b[128] = {0}; int fd = open(path, O_RDONLY);
    ssize_t n = fd < 0 ? -1 : read(fd, b, sizeof(b)-1); if (fd >= 0) close(fd);
    return n > 0 && !strncmp(b, "max ", 4) ? strtoul(b + 4, NULL, 10) : ~0UL;
}
/* Warm this process's private stack/C library paths before measuring a small
 * mapping delta. Fork initially shares those pages; the first test call can
 * legitimately COW them and is not a leaked mapped page. */
__attribute__((noinline)) static void warm_measurement_paths(void) {
    volatile unsigned char stack[65536];
    for (size_t i = 0; i < sizeof(stack); i += PAGE) stack[i] = (unsigned char)i;
    struct timespec delay = {0, 1000000}; nanosleep(&delay, NULL);
    printf("{\"measurement_stack_warmed\":%zu}\n", sizeof(stack));
    (void)read_number(WORK "/memory.current");
}
static unsigned long wait_at_most(const char *path, unsigned long ceiling) {
    unsigned long value = read_number(path);
    unsigned observations = 0;
    while (value > ceiling && observations < 1000) {
        struct timespec delay = {0, 1000000}; nanosleep(&delay, NULL);
        value = read_number(path); observations++;
    }
    printf("{\"refund_path\":\"%s\",\"observations\":%u,\"current\":%lu,\"ceiling\":%lu}\n", path, observations, value, ceiling);
    return value;
}
static void private_file_paths(void) {
    char original[2 * PAGE]; memset(original, 0x3a, sizeof(original));
    int fd = open("/tmp/hepta-private-cow", O_CREAT | O_EXCL | O_RDWR, 0600);
    if (fd < 0 || write(fd, original, sizeof(original)) != sizeof(original)) {
        check("private_file_fixture", 0); if (fd >= 0) close(fd); return;
    }
    volatile unsigned char *p = mmap(NULL, 65 * PAGE, PROT_READ | PROT_WRITE, MAP_PRIVATE, fd, 0);
    if (p == MAP_FAILED) { check("private_file_mapping", 0); close(fd); return; }
    unsigned long before = read_number(WORK "/memory.current");
    unsigned char read_before_write = p[0];
    p[0] = 0x51;       /* COW from a previously read private file page. */
    p[PAGE] = 0x52;    /* Direct write fault on a private file page. */
    unsigned char tail_zero = p[64 * PAGE]; /* Existing private VMO tail semantics. */
    p[64 * PAGE] = 0x53;
    unsigned long held = read_number(WORK "/memory.current");
    unsigned char file_bytes[2];
    int unchanged = pread(fd, &file_bytes[0], 1, 0) == 1 && pread(fd, &file_bytes[1], 1, PAGE) == 1;
    printf("{\"file_cow_before\":%lu,\"file_cow_held\":%lu}\n", before, held);
    check("private_file_cow_and_vmo_tail_charge", read_before_write == 0x3a && tail_zero == 0 && held >= before + 3 * PAGE);
    check("private_file_cow_preserves_backing_file", unchanged && file_bytes[0] == 0x3a && file_bytes[1] == 0x3a);
    int rc = munmap((void *)p, 65 * PAGE);
    unsigned long released = wait_at_most(WORK "/memory.current", held - 3 * PAGE);
    check("private_file_cow_and_tail_refund", !rc && released + 3 * PAGE <= held);
    close(fd); unlink("/tmp/hepta-private-cow");
}
static atomic_int concurrent_done, concurrent_failed;
static pthread_barrier_t concurrent_start;
static void *concurrent_allocator(void *unused) {
    (void)unused;
    pthread_barrier_wait(&concurrent_start);
    for (unsigned round = 0; round < 32; round++) {
        volatile unsigned char *p = pages(8);
        if (!p) { atomic_store(&concurrent_failed, 1); break; }
        touch(p, 8);
        if (munmap((void *)p, 8 * PAGE)) atomic_store(&concurrent_failed, 1);
        struct timespec delay = {0, 100000}; nanosleep(&delay, NULL);
    }
    atomic_fetch_add(&concurrent_done, 1);
    return NULL;
}
static int concurrent_worker(void) {
    failures = 0; alarm(25);
    if (join(CONCURRENT "/cgroup.procs")) return 77;
    volatile unsigned char *pinned = pages(1); if (!pinned) return 90;
    touch(pinned, 1);
    pthread_t threads[4];
    if (pthread_barrier_init(&concurrent_start, NULL, 5)) return 90;
    for (unsigned i = 0; i < 4; i++) if (pthread_create(&threads[i], NULL, concurrent_allocator, NULL)) return 90;
    pthread_barrier_wait(&concurrent_start);
    unsigned updates = 0, rejected = 0;
    while (atomic_load(&concurrent_done) != 4) {
        errno = 0;
        if (write_file(CONCURRENT "/memory.max", "0") < 0 && errno == EBUSY) rejected++;
        else atomic_store(&concurrent_failed, 1);
        if (write_file(CONCURRENT "/memory.max", updates % 2 ? "8388608" : "16777216")) atomic_store(&concurrent_failed, 1);
        unsigned long current = read_number(CONCURRENT "/memory.current");
        unsigned long max = read_number(CONCURRENT "/memory.max");
        if (current > max) atomic_store(&concurrent_failed, 1);
        updates++;
        struct timespec delay = {0, 100000}; nanosleep(&delay, NULL);
    }
    for (unsigned i = 0; i < 4; i++) if (pthread_join(threads[i], NULL)) return 90;
    printf("{\"concurrent_allocators\":4,\"rounds_each\":32,\"limit_updates\":%u,\"rejected_under_current\":%u}\n", updates, rejected);
    check("concurrent_fault_refund_limit_updates", updates > 0 && rejected == updates && !atomic_load(&concurrent_failed));
    munmap((void *)pinned, PAGE); pthread_barrier_destroy(&concurrent_start);
    return failures ? 42 : 0;
}
static int worker(void) {
    failures = 0; alarm(25);
    if (join(WORK "/cgroup.procs")) return 77;
    warm_measurement_paths();
    private_file_paths();
    unsigned long before = read_number(WORK "/memory.current");
    volatile unsigned char *p = pages(128); if (!p) return 90;
    touch(p, 128);
    unsigned long held = read_number(WORK "/memory.current");
    printf("{\"anon_before\":%lu,\"anon_held\":%lu}\n", before, held);
    check("private_faults_charge_real_pages", before != ~0UL && held >= before + 128 * PAGE);
    int command[2], report[2]; if (pipe(command) || pipe(report)) return 90;
    pid_t child = fork(); if (child < 0) return 90;
    if (!child) {
        close(command[1]); close(report[0]);
        touch(p, 64); char c = 'R';
        if (write(report[1], &c, 1) != 1 || read(command[0], &c, 1) != 1) _exit(90);
        munmap((void *)p, 128 * PAGE); _exit(0);
    }
    close(command[0]); close(report[1]); char c;
    int ready = read(report[0], &c, 1) == 1 && c == 'R';
    unsigned long copied = read_number(WORK "/memory.current");
    printf("{\"anon_fork_cow\":%lu}\n", copied);
    check("descendant_cow_inherits_and_charges_budget", ready && copied >= held + 64 * PAGE);
    c = 'Q'; if (write(command[1], &c, 1) != 1) return 90;
    int status; if (waitpid(child, &status, 0) != child) return 90;
    check("cow_child_exits", WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(command[1]); close(report[0]);
    unsigned long refunded = wait_at_most(WORK "/memory.current", copied - 48 * PAGE);
    check("cow_exit_refunds_real_pages", refunded + 48 * PAGE <= copied);
    errno = 0; int unmap_result = munmap((void *)p, 128 * PAGE), unmap_error = errno;
    unsigned long released = read_number(WORK "/memory.current");
    printf("{\"anon_after_child_exit\":%lu,\"anon_after_munmap\":%lu,\"munmap_result\":%d,\"munmap_errno\":%d}\n", refunded, released, unmap_result, unmap_error);
    unsigned grace_observations = 0;
    while (released + 112 * PAGE > refunded && grace_observations < 100) {
        struct timespec delay = {0, 1000000}; nanosleep(&delay, NULL);
        released = read_number(WORK "/memory.current");
        grace_observations++;
    }
    printf("{\"anon_after_rcu\":%lu,\"grace_observations\":%u}\n", released, grace_observations);
    check("munmap_refunds_after_rcu_quiescence", !unmap_result && released + 112 * PAGE <= refunded);
    return failures ? 42 : 0;
}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(45);
    if (geteuid()) return 77;
    if (write_file("/sys/fs/cgroup/cgroup.subtree_control", "+cpu +memory") ||
        mkdir(BASE, 0755) || write_file(BASE "/cgroup.subtree_control", "+cpu +memory") ||
        mkdir(WORK, 0755) || mkdir(RECOVERY, 0755) || mkdir(CONCURRENT, 0755) ||
        write_file(BASE "/memory.max", "67108864") ||
        write_file(WORK "/memory.max", "2097152") ||
        write_file(RECOVERY "/memory.max", "2097152") ||
        write_file(CONCURRENT "/memory.max", "16777216")) { perror("budget setup"); return 77; }
    const char *weights[] = {"1", "100", "10000"};
    for (unsigned i = 0; i < sizeof(weights) / sizeof(weights[0]); i++) {
        errno = 0;
        int rc = write_file(WORK "/cpu.weight", weights[i]);
        check("cpu_weight_cannot_falsely_succeed", rc < 0 && errno == EOPNOTSUPP &&
              read_number(WORK "/cpu.weight") == 100);
    }
    check("selected_frame_limit_reads_back", read_number(WORK "/memory.max") == 2097152);
    pid_t child = fork(); if (child < 0) return 90;
    if (!child) _exit(worker());
    int status; if (waitpid(child, &status, 0) != child) return 90;
    check("workload_process_tree_test", WIFEXITED(status) && WEXITSTATUS(status) == 0);
    /* The observer is outside the exhausted subtree. Its own post-fork COW
     * faults must not compete with the workload while deferred frame frees
     * still occupy the workload ceiling. This is also the recovery topology. */
    check("completed_workload_refunds_before_pressure", wait_at_most(WORK "/memory.current", 0) == 0);
    unsigned long denied_before = read_events(WORK "/memory.events");
    child = fork(); if (child < 0) return 90;
    if (!child) {
        if (join(WORK "/cgroup.procs")) _exit(77);
        volatile unsigned char *large = pages(1024);
        if (!large) _exit(91);
        touch(large, 1024); _exit(92);
    }
    if (waitpid(child, &status, 0) != child) return 90;
    check("anonymous_limit_stops_faulting_descendant", WIFSIGNALED(status) && WTERMSIG(status) == SIGSEGV);
    unsigned long denied_after = read_events(WORK "/memory.events");
    printf("{\"denied_before\":%lu,\"denied_after\":%lu}\n", denied_before, denied_after);
    check("limit_denial_recorded_as_new_event", denied_before != ~0UL && denied_after != ~0UL && denied_after > denied_before);
    child = fork(); if (child < 0) return 90;
    if (!child) {
        if (join(RECOVERY "/cgroup.procs")) _exit(77);
        volatile unsigned char *p = pages(256); if (!p) _exit(90);
        touch(p, 256); munmap((void *)p, 256 * PAGE); _exit(0);
    }
    if (waitpid(child, &status, 0) != child) return 90;
    check("recovery_sibling_allocates_after_workload_denial", WIFEXITED(status) && WEXITSTATUS(status) == 0);
    check("reaped_workload_refunds_budget", wait_at_most(WORK "/memory.current", 0) == 0);
    check("reaped_recovery_refunds_budget", wait_at_most(RECOVERY "/memory.current", 0) == 0);
    child = fork(); if (child < 0) return 90;
    if (!child) _exit(concurrent_worker());
    if (waitpid(child, &status, 0) != child) return 90;
    check("concurrent_process_tree_test", WIFEXITED(status) && WEXITSTATUS(status) == 0);
    check("reaped_concurrent_refunds_budget", wait_at_most(CONCURRENT "/memory.current", 0) == 0);
    rmdir(WORK); rmdir(RECOVERY); rmdir(CONCURRENT); rmdir(BASE);
    return failures ? 42 : 0;
}
