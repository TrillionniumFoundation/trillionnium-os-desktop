// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

typedef long (*vdso_getcpu_fn)(unsigned *, unsigned *, void *);
static vdso_getcpu_fn vdso_getcpu;
static cpu_set_t original_mask;
static int cpus[4], cpu_count;
static _Atomic unsigned failures;
static __thread uint64_t tls_cookie;
static const uint64_t main_cookie = UINT64_C(0xa5c0010012345678);
static const uint64_t thread_cookie = UINT64_C(0xa5c0020087654321);

static void check(const char *name, int passed) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, passed ? "true" : "false");
    if (!passed) atomic_fetch_add_explicit(&failures, 1, memory_order_relaxed);
}

static int read_text(const char *path, char *data, size_t size) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    ssize_t n = read(fd, data, size - 1);
    int saved = errno;
    if (close(fd) != 0 || n < 0) { errno = saved; return -1; }
    data[n] = 0;
    return (int)n;
}

static int guest_guard(int argc, char **argv) {
    char version[1024], marker[64];
    if (argc != 4 || strcmp(argv[1], "--asterinas-disposable-guest") ||
        strcmp(argv[2], "--expected-cpus")) return 0;
    char *end = NULL;
    long n = strtol(argv[3], &end, 10);
    if (!end || *end || (n != 1 && n != 2 && n != 4)) return 0;
    cpu_count = (int)n;
    if (read_text("/proc/version", version, sizeof version) < 0 ||
        !strstr(version, "rustc 1.99.0-nightly") ||
        read_text("/.hepta-vdso-cpu-qa", marker, sizeof marker) != 33 || marker[32] != '\n') return 0;
    for (int i = 0; i < 32; ++i)
        if (!((marker[i] >= '0' && marker[i] <= '9') || (marker[i] >= 'a' && marker[i] <= 'f'))) return 0;
    return 1;
}

/* The mapped vDSO contains its ELF header, PT_DYNAMIC and dynamic tables in
 * its first page. Resolve only the exact exported function inside that page. */
static vdso_getcpu_fn find_vdso_getcpu(void) {
    uintptr_t base = getauxval(AT_SYSINFO_EHDR);
    if (!base) return NULL;
    const Elf64_Ehdr *eh = (const Elf64_Ehdr *)base;
    if (memcmp(eh->e_ident, ELFMAG, SELFMAG) || eh->e_ident[EI_CLASS] != ELFCLASS64 ||
        eh->e_phentsize != sizeof(Elf64_Phdr) || eh->e_phnum > 16 ||
        eh->e_phoff + (uint64_t)eh->e_phnum * sizeof(Elf64_Phdr) > 4096) return NULL;
    const Elf64_Phdr *ph = (const Elf64_Phdr *)(base + eh->e_phoff);
    const Elf64_Dyn *dynamic = NULL;
    size_t dynamic_count = 0;
    for (unsigned i = 0; i < eh->e_phnum; ++i) {
        if (ph[i].p_type != PT_DYNAMIC) continue;
        if (ph[i].p_vaddr >= 4096 || ph[i].p_memsz > 4096 - ph[i].p_vaddr) return NULL;
        dynamic = (const Elf64_Dyn *)(base + ph[i].p_vaddr);
        dynamic_count = ph[i].p_memsz / sizeof(Elf64_Dyn);
    }
    uintptr_t symbols = 0, strings = 0, hash = 0;
    size_t strings_size = 0;
    if (!dynamic) return NULL;
    for (size_t i = 0; i < dynamic_count && dynamic[i].d_tag != DT_NULL; ++i) {
        switch (dynamic[i].d_tag) {
            case DT_SYMTAB: symbols = dynamic[i].d_un.d_ptr; break;
            case DT_STRTAB: strings = dynamic[i].d_un.d_ptr; break;
            case DT_HASH: hash = dynamic[i].d_un.d_ptr; break;
            case DT_STRSZ: strings_size = dynamic[i].d_un.d_val; break;
            default: break;
        }
    }
    if (!symbols || !strings || !hash || hash > 4096 - 8 ||
        strings >= 4096 || strings_size > 4096 - strings) return NULL;
    const uint32_t *table = (const uint32_t *)(base + hash);
    unsigned count = table[1];
    if (count > 128 || symbols >= 4096 || (uint64_t)count * sizeof(Elf64_Sym) > 4096 - symbols) return NULL;
    const Elf64_Sym *sym = (const Elf64_Sym *)(base + symbols);
    for (unsigned i = 0; i < count; ++i) {
        if (sym[i].st_name >= strings_size) return NULL;
        const char *name = (const char *)(base + strings + sym[i].st_name);
        if (!memchr(name, 0, strings_size - sym[i].st_name)) return NULL;
        if (strcmp(name, "__vdso_getcpu")) continue;
        if (ELF64_ST_TYPE(sym[i].st_info) != STT_FUNC || sym[i].st_value >= 4096 ||
            sym[i].st_size > 4096 - sym[i].st_value) return NULL;
        return (vdso_getcpu_fn)(base + sym[i].st_value);
    }
    return NULL;
}

static int mask_is_single_cpu(int cpu) {
    cpu_set_t mask;
    return sched_getaffinity(0, sizeof mask, &mask) == 0 && CPU_COUNT(&mask) == 1 && CPU_ISSET(cpu, &mask);
}

static void sample(const char *phase, int round, int target, pid_t expected_tid, uint64_t cookie) {
    char name[128];
    unsigned sys_cpu = UINT32_MAX, sys_node = UINT32_MAX;
    unsigned vdso_cpu = UINT32_MAX, vdso_node = UINT32_MAX;
    unsigned short cs, ss;
    errno = 0;
    long sys_rc = syscall(SYS_getcpu, &sys_cpu, &sys_node, NULL);
    int sys_errno = errno;
    errno = 0;
    int libc_cpu = sched_getcpu();
    int libc_errno = errno;
    errno = 0;
    long vdso_rc = vdso_getcpu(&vdso_cpu, &vdso_node, NULL);
    int vdso_errno = errno;
    uint32_t cpunode = 0x7b;
    unsigned char lsl_valid;
    __asm__ volatile("lsl %w0,%0; setz %1" : "+r"(cpunode), "=qm"(lsl_valid) : : "cc");
    __asm__ volatile("mov %%cs,%0; mov %%ss,%1" : "=r"(cs), "=r"(ss));
    pid_t tid = (pid_t)syscall(SYS_gettid);
    printf("{\"sample\":\"%s.r%d.cpu%d\",\"tid\":%ld,\"target\":%d,\"sys_rc\":%ld,\"sys_errno\":%d,\"sys_cpu\":%u,\"sys_node\":%u,\"libc_cpu\":%d,\"libc_errno\":%d,\"vdso_rc\":%ld,\"vdso_errno\":%d,\"vdso_cpu\":%u,\"vdso_node\":%u,\"lsl_valid\":%u,\"lsl_limit\":%u,\"cs\":%u,\"ss\":%u}\n",
           phase, round, target, (long)tid, target, sys_rc, sys_errno, sys_cpu, sys_node,
           libc_cpu, libc_errno, vdso_rc, vdso_errno, vdso_cpu, vdso_node, lsl_valid, cpunode, cs, ss);
    const char *keys[] = {"mask", "sys", "libc", "vdso", "lsl", "tls_selectors_tid"};
    int passed[] = {
        mask_is_single_cpu(target),
        sys_rc == 0 && sys_cpu == (unsigned)target && sys_node == 0,
        libc_cpu == target,
        vdso_rc == 0 && vdso_cpu == (unsigned)target && vdso_node == 0,
        lsl_valid && (cpunode & 0xfff) == (unsigned)target && (cpunode >> 12) == 0,
        tls_cookie == cookie && tid == expected_tid && cs == 0x33 && ss == 0x2b,
    };
    for (size_t i = 0; i < sizeof keys / sizeof keys[0]; ++i) {
        snprintf(name, sizeof name, "%s.r%d.cpu%d.%s", phase, round, target, keys[i]);
        check(name, passed[i]);
    }
}

static void exercise(const char *phase, uint64_t cookie) {
    pid_t tid = (pid_t)syscall(SYS_gettid);
    tls_cookie = cookie;
    for (int round = 0; round < 2; ++round) {
        for (int i = 0; i < cpu_count; ++i) {
            int cpu = cpus[round ? cpu_count - i - 1 : i];
            cpu_set_t mask;
            CPU_ZERO(&mask); CPU_SET(cpu, &mask);
            int pin_rc = sched_setaffinity(0, sizeof mask, &mask);
            if (pin_rc || !mask_is_single_cpu(cpu)) {
                char name[128];
                snprintf(name, sizeof name, "%s.r%d.cpu%d.mask", phase, round, cpu);
                check(name, 0);
                continue;
            }
            sample(phase, round, cpu, tid, cookie);
        }
    }
    int rc = sched_setaffinity(0, sizeof original_mask, &original_mask);
    cpu_set_t restored;
    char name[128];
    snprintf(name, sizeof name, "%s.mask_restored", phase);
    check(name, rc == 0 && sched_getaffinity(0, sizeof restored, &restored) == 0 && CPU_EQUAL(&restored, &original_mask));
}

static void *worker(void *unused) {
    (void)unused;
    check("thread.initial_tls", tls_cookie == 0);
    exercise("thread", thread_cookie);
    return NULL;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int guarded = guest_guard(argc, argv);
    check("setup.guest_guard", guarded);
    if (!guarded) return 2;
    int mask_ok = sched_getaffinity(0, sizeof original_mask, &original_mask) == 0 && CPU_COUNT(&original_mask) == cpu_count;
    for (int i = 0; i < cpu_count; ++i) { cpus[i] = i; mask_ok = mask_ok && CPU_ISSET(i, &original_mask); }
    check("setup.cpu_mask", mask_ok);
    vdso_getcpu = find_vdso_getcpu();
    check("setup.vdso_entry", vdso_getcpu != NULL);
    if (!mask_ok || !vdso_getcpu) return 2;
    pid_t tid = (pid_t)syscall(SYS_gettid);
    struct timespec before, after;
    int time_ok = clock_gettime(CLOCK_MONOTONIC, &before) == 0;
    exercise("main", main_cookie);
    pthread_t thread;
    int created = pthread_create(&thread, NULL, worker, NULL) == 0;
    check("setup.thread_create", created);
    int joined = created && pthread_join(thread, NULL) == 0;
    check("setup.thread_join", joined);
    cpu_set_t mask;
    check("cleanup.main_state", tls_cookie == main_cookie && tid == (pid_t)syscall(SYS_gettid) &&
          sched_getaffinity(0, sizeof mask, &mask) == 0 && CPU_EQUAL(&mask, &original_mask));
    time_ok = time_ok && clock_gettime(CLOCK_MONOTONIC, &after) == 0 &&
              (after.tv_sec > before.tv_sec || (after.tv_sec == before.tv_sec && after.tv_nsec >= before.tv_nsec));
    check("cleanup.monotonic", time_ok);
    return atomic_load_explicit(&failures, memory_order_relaxed) ? 1 : 0;
}
