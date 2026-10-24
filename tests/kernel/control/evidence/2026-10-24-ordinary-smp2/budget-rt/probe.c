// SPDX-License-Identifier: MPL-2.0
/* Isolated Asterinas guest CPU-cap diagnostic, not a host configurator.
 * It requires a private initramfs marker and the Rust-built guest version.
 * Linux-compatible uname/version names alone are not kernel identity.
 * Threshold only detects gross non-enforcement; low usage is inconclusive.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <sched.h>
#include <pthread.h>
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
    int e = errno;
    printf("ORGAN_PROBE_BLOCKED where=%s errno=%d\n", where, e);
    exit(2);
}
static void read_text(const char *path, char *out, size_t size) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) fail(path);
    ssize_t n = read(fd, out, size - 1);
    if (n < 0) { int e = errno; close(fd); errno = e; fail(path); }
    out[n] = 0;
    if (close(fd) != 0) fail("close-read");
}
static void put(const char *path, const char *text) {
    int fd = open(path, O_WRONLY);
    if (fd < 0) fail(path);
    size_t n = strlen(text);
    ssize_t written = write(fd, text, n);
    if (written < 0 || (size_t)written != n) {
        int e = written < 0 ? errno : EIO;
        close(fd); errno = e; fail(path);
    }
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
struct measure { uint64_t wall_ns, cpu_ns, iterations; };
static void *parallel_worker(void *arg) {
    (void)arg;
    volatile uint64_t acc=1;
    uint64_t start=wall(), end=start;
    while (end - start < UINT64_C(5000000000)) {
        for (unsigned n=0; n<100000; ++n) acc = acc*UINT64_C(6364136223846793005)+1;
        end=wall();
    }
    return NULL;
}
static struct measure burn_parallel(const char *label) {
    uint64_t start=wall(), begin_cpu=cpu();
    pthread_t th;
    if (pthread_create(&th,NULL,parallel_worker,NULL)!=0) fail("pthread_create");
    parallel_worker(NULL);
    if (pthread_join(th,NULL)!=0) fail("pthread_join");
    uint64_t elapsed=wall()-start, total=cpu()-begin_cpu;
    struct measure m={elapsed,total,0};
    printf("ORGAN_CPU_SAMPLE label=%s wall_ns=%" PRIu64 " cpu_ns=%" PRIu64 " iterations=0 checksum=0\n",label,m.wall_ns,m.cpu_ns);
    return m;
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 2 || strcmp(argv[1], "--asterinas-disposable-guest") != 0) {
        fprintf(stderr,"requires --asterinas-disposable-guest; no host cgroup changes\n");return 2;
    }
    char buf[4096], path[256], group[192], pid[32];
    read_text("/proc/version",buf,sizeof buf);
    if (strstr(buf,"rustc 1.99.0-nightly") == NULL) {
        fprintf(stderr,"refusing non-matching guest kernel\n");return 2;
    }
    printf("ORGAN_KERNEL %s\n",buf);
    read_text("/.hepta-disposable-guest",buf,sizeof buf);
    if (strcmp(buf,"c90cb30bd5e6d081193ea26d71bbaf585719dc9eefa9eab081a2ba06b1056965\n") != 0) {
        fprintf(stderr,"refusing missing disposable-guest marker\n");return 2;
    }
    struct measure baseline = burn_parallel("unlimited");
    read_text("/sys/fs/cgroup/cgroup.controllers",buf,sizeof buf);
    printf("ORGAN_CONTROLLERS %s\n",buf);
    put("/sys/fs/cgroup/cgroup.subtree_control","+cpu\n");
    snprintf(group,sizeof group,"/sys/fs/cgroup/organ-audit-%ld",(long)getpid());
    if (mkdir(group,0755) != 0) fail("mkdir-cgroup");
    snprintf(path,sizeof path,"%s/cpu.max",group);put(path,"10000 100000\n");
    read_text(path,buf,sizeof buf);
    unsigned long long quota = 0, period = 0;
    if (sscanf(buf,"%llu %llu",&quota,&period)!=2 || quota!=10000 || period!=100000) {errno=EINVAL;fail("cpu-max-readback");}
    printf("ORGAN_CPU_CONFIG quota_us=%llu period_us=%llu\n",quota,period);
    snprintf(path,sizeof path,"%s/cgroup.procs",group);snprintf(pid,sizeof pid,"%ld\n",(long)getpid());put(path,pid);
    read_text("/proc/self/cgroup",buf,sizeof buf);
    printf("ORGAN_MEMBERSHIP %s\n",buf);
    if (strstr(buf,group+strlen("/sys/fs/cgroup"))==NULL) {errno=EINVAL;fail("membership-mismatch");}
    struct sched_param sp = {.sched_priority=1};
    if (sched_setscheduler(0,SCHED_FIFO,&sp) != 0) fail("sched_setscheduler");
    printf("ORGAN_POLICY=RT_FIFO\n");
    snprintf(path,sizeof path,"%s/cpu.stat",group);read_text(path,buf,sizeof buf);printf("ORGAN_CPU_STAT_BEFORE\n%s\n",buf);
    struct measure capped=burn_parallel("one-percent-configured");
    read_text(path,buf,sizeof buf);printf("ORGAN_CPU_STAT_AFTER\n%s\n",buf);
    if (baseline.cpu_ns > baseline.wall_ns/5 && capped.cpu_ns > capped.wall_ns/5)
        printf("ORGAN_CPU_VERDICT=NOT_ENFORCED\n");
    else printf("ORGAN_CPU_VERDICT=INCONCLUSIVE_REQUIRES_TIMING_VALIDATION\n");
    printf("ORGAN_PROBE_COMPLETE\n");
    return 0;
}