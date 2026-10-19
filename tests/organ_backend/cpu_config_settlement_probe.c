/* SPDX-License-Identifier: MPL-2.0
 * Ordinary cpu.max timing regression in a disposable Asterinas guest.
 * The runner pins the ELF and records the inputs before starting QEMU.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static void fail(const char *where) {
    printf("CPU_CONFIG_BLOCKED where=%s errno=%d\n", where, errno);
    exit(2);
}

static void read_text(const char *path, char *out, size_t size) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) fail(path);
    ssize_t n = read(fd, out, size - 1);
    if (n < 0) fail("read");
    out[n] = 0;
    if (close(fd) != 0) fail("close-read");
}

static void put(const char *path, const char *text) {
    int fd = open(path, O_WRONLY);
    if (fd < 0) fail(path);
    size_t n = strlen(text);
    ssize_t written = write(fd, text, n);
    if (written < 0 || (size_t)written != n) fail("write");
    if (close(fd) != 0) fail("close-write");
}

static uint64_t wall(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) fail("clock_gettime");
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static uint64_t cpu(void) {
    struct rusage r;
    if (getrusage(RUSAGE_SELF, &r) != 0) fail("getrusage");
    return ((uint64_t)r.ru_utime.tv_sec + (uint64_t)r.ru_stime.tv_sec) * UINT64_C(1000000000)
        + ((uint64_t)r.ru_utime.tv_usec + (uint64_t)r.ru_stime.tv_usec) * 1000;
}

static void sample(const char *label, uint64_t duration, const char *path,
                   const char *config, int rewrite) {
    char buf[128];
    uint64_t start = wall(), first_cpu = cpu(), now = start, operations = 0;
    volatile uint64_t checksum = 1;
    while (now - start < duration) {
        for (unsigned i = 0; i < 128; ++i)
            checksum = checksum * UINT64_C(6364136223846793005) + 1;
        if (path != NULL) {
            if (rewrite) put(path, config);
            else read_text(path, buf, sizeof buf);
        }
        operations++;
        now = wall();
        if (now < start) { errno = ERANGE; fail("wall-backwards"); }
    }
    uint64_t last_cpu = cpu();
    if (last_cpu < first_cpu) { errno = ERANGE; fail("cpu-backwards"); }
    printf("CPU_CONFIG_SAMPLE label=%s wall_ns=%" PRIu64 " cpu_ns=%" PRIu64
           " operations=%" PRIu64 " checksum=%" PRIu64 "\n",
           label, now - start, last_cpu - first_cpu, operations, checksum);
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 5 || strcmp(argv[1], "--asterinas-disposable-guest") != 0) return 2;
    char buf[4096], path[256], group[192], config[64], pid[32];
    read_text("/proc/version", buf, sizeof buf);
    if (strstr(buf, "rustc 1.99.0-nightly") == NULL) return 2;
    read_text("/.hepta-disposable-guest", buf, sizeof buf);
    if (strcmp(buf, "__KERNEL_SHA__\n") != 0) return 2;
    unsigned long period_us = strtoul(argv[2], NULL, 10);
    int rewrite = strcmp(argv[3], "same-value") == 0;
    unsigned long seconds = strtoul(argv[4], NULL, 10);
    if ((period_us != 2000 && period_us != 100000) || seconds < 1 || seconds > 10)
        return 2;
    if (!rewrite && strcmp(argv[3], "read-only") != 0) return 2;

    sample("unlimited", UINT64_C(250000000), NULL, NULL, 0);
    put("/sys/fs/cgroup/cgroup.subtree_control", "+cpu\n");
    snprintf(group, sizeof group, "/sys/fs/cgroup/cpu-config-%ld", (long)getpid());
    if (mkdir(group, 0755) != 0) fail("mkdir-cgroup");
    snprintf(config, sizeof config, "1000 %lu\n", period_us);
    snprintf(path, sizeof path, "%s/cpu.max", group);
    put(path, config);
    read_text(path, buf, sizeof buf);
    if (strcmp(buf, config) != 0) { errno = EINVAL; fail("config-readback"); }
    snprintf(path, sizeof path, "%s/cgroup.procs", group);
    snprintf(pid, sizeof pid, "%ld\n", (long)getpid());
    put(path, pid);
    read_text("/proc/self/cgroup", buf, sizeof buf);
    if (strstr(buf, group + strlen("/sys/fs/cgroup")) == NULL) fail("membership");
    snprintf(path, sizeof path, "%s/cpu.max", group);
    printf("CPU_CONFIG_PARAMETERS quota_us=1000 period_us=%lu mode=%s seconds=%lu\n",
           period_us, argv[3], seconds);
    sample(argv[3], (uint64_t)seconds * UINT64_C(1000000000), path, config, rewrite);
    read_text(path, buf, sizeof buf);
    if (strcmp(buf, config) != 0) { errno = EINVAL; fail("final-config-readback"); }
    snprintf(path, sizeof path, "%s/cpu.stat", group);
    read_text(path, buf, sizeof buf);
    printf("CPU_CONFIG_STAT\n%sCPU_CONFIG_COMPLETE\n", buf);
    return 0;
}
