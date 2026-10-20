/* SPDX-License-Identifier: MPL-2.0 */
/* Runs as the actual, manifest-bound initial ELF in a disposable N0 guest. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define HOS2_IOCTL 0xC0204802U
#define AT_HEPTA_BOOT 240
#define PAGE_BYTES 4096U
#define PERIOD_NS UINT64_C(100000000)
#define CAP_NS UINT64_C(50000000)

static uint64_t request_sequence;
static unsigned char boot_id[16], capspace[16];
static unsigned char *boot_page;

/* Each evidence record is one write, including its newline. */
static void record(const char *format, ...) {
    char line[1024];
    va_list ap;
    va_start(ap, format);
    int n = vsnprintf(line, sizeof line - 1, format, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= sizeof line - 1) _exit(123);
    line[n++] = '\n';
    if (write(STDOUT_FILENO, line, (size_t)n) != n) _exit(124);
}

static void failure(const char *at, int line) {
    int saved = errno;
    record("G1C_FAIL at=%s line=%d errno=%d pid=%ld", at, line, saved, (long)getpid());
    if (getpid() == 1) reboot(RB_POWER_OFF);
    _exit(121);
}
#define CHECK(condition, name) do { if (!(condition)) failure(name, __LINE__); } while (0)

static void put16(unsigned char *p, uint16_t n) {
    p[0] = (unsigned char)n; p[1] = (unsigned char)(n >> 8);
}
static void put32(unsigned char *p, uint32_t n) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (unsigned char)(n >> (8 * i));
}
static void put64(unsigned char *p, uint64_t n) {
    for (unsigned i = 0; i < 8; ++i) p[i] = (unsigned char)(n >> (8 * i));
}
static uint16_t get16(const unsigned char *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}
static uint32_t get32(const unsigned char *p) {
    uint32_t n = 0;
    for (int i = 3; i >= 0; --i) n = n * 256 + p[i];
    return n;
}
static uint64_t get64(const unsigned char *p) {
    uint64_t n = 0;
    for (int i = 7; i >= 0; --i) n = n * 256 + p[i];
    return n;
}
static int uniform(const unsigned char *p, size_t n, unsigned char byte) {
    for (size_t i = 0; i < n; ++i) if (p[i] != byte) return 0;
    return 1;
}

static void request(unsigned char *q, uint16_t opcode, uint64_t slot, uint64_t generation) {
    memset(q, 0, 64);
    memcpy(q, "HOS2", 4);
    put16(q + 4, 2); put16(q + 8, opcode); put32(q + 12, 64);
    put64(q + 24, ++request_sequence);
    put64(q + 32, UINT64_C(0x47314350524f4245));
    put64(q + 40, slot); put64(q + 48, generation);
}
static int transact(int fd, unsigned char *q, unsigned qlen, unsigned char *r, unsigned rlen) {
    unsigned char transport[32] = {0};
    put64(transport, (uint64_t)(uintptr_t)q);
    put64(transport + 8, (uint64_t)(uintptr_t)r);
    put32(transport + 16, qlen); put32(transport + 20, rlen);
    memset(r, 0xa5, rlen);
    return ioctl(fd, HOS2_IOCTL, transport);
}
static void response_header(const unsigned char *r, const unsigned char *q,
                            unsigned status, unsigned payload, uint64_t revision) {
    CHECK(memcmp(r, "HOSR", 4) == 0 && get16(r + 4) == 2 && get16(r + 6) == 0,
          "response_protocol");
    CHECK(get16(r + 8) == get16(q + 8) && get16(r + 10) == status,
          "response_opcode_status");
    CHECK(get32(r + 12) == 64 && get32(r + 16) == payload && get32(r + 20) == 0,
          "response_lengths_reserved");
    CHECK(memcmp(r + 24, q + 24, 16) == 0 && !uniform(r + 40, 16, 0),
          "response_request_boot_identity");
    CHECK(get64(r + 56) == revision, "response_revision");
    CHECK(uniform(r + 64 + payload, 128 - 64 - payload, 0xa5), "response_copyout_tail");
    if (!uniform(boot_id, sizeof boot_id, 0))
        CHECK(memcmp(boot_id, r + 40, 16) == 0, "boot_identity_changed");
}
static void query(int fd, unsigned char space[16]) {
    unsigned char q[64], r[128];
    request(q, 1, 0, 0);
    CHECK(transact(fd, q, sizeof q, r, sizeof r) == 0, "query_ioctl");
    response_header(r, q, 0, 48, 0);
    CHECK(!uniform(r + 64, 16, 0) && get32(r + 80) == PAGE_BYTES &&
          get32(r + 84) == 0 && get32(r + 88) == 64 && get32(r + 92) == 0 &&
          get64(r + 96) == 6 && get64(r + 104) == 0, "query_exact_build_capabilities");
    memcpy(boot_id, r + 40, 16);
    memcpy(space, r + 64, 16);
}

struct usage {
    uint64_t sample, cumulative, window_start, window_consumed;
    uint64_t cap, period, events, dropped, revision;
};
static struct usage read_usage_budget(int fd, const char *label, uint64_t expected_cap) {
    unsigned char q[64], r[128];
    request(q, 2, 1, 1);
    CHECK(transact(fd, q, sizeof q, r, sizeof r) == 0, "read_usage_ioctl");
    CHECK(get64(r + 56) != 0, "read_usage_nonzero_revision");
    response_header(r, q, 0, 64, get64(r + 56));
    struct usage u = {
        get64(r + 64), get64(r + 72), get64(r + 80), get64(r + 88),
        get64(r + 96), get64(r + 104), get64(r + 112), get64(r + 120), get64(r + 56)
    };
    CHECK(u.cap == expected_cap && u.period == PERIOD_NS && u.sample > 0,
          "read_usage_fixed_budget");
    CHECK(u.window_start == (u.sample / PERIOD_NS) * PERIOD_NS &&
          u.window_consumed <= u.cumulative && u.cumulative <= u.sample &&
          u.cumulative - u.window_consumed <= u.window_start && u.dropped <= u.events,
          "read_usage_accounting_invariants");
    record("G1C_USAGE label=%s sample=%" PRIu64 " cumulative=%" PRIu64
           " window_start=%" PRIu64 " window_consumed=%" PRIu64
           " cap=%" PRIu64 " period=%" PRIu64 " events=%" PRIu64
           " dropped=%" PRIu64 " revision=%" PRIu64,
           label, u.sample, u.cumulative, u.window_start, u.window_consumed,
           u.cap, u.period, u.events, u.dropped, u.revision);
    return u;
}
static struct usage read_usage(int fd, const char *label) {
    return read_usage_budget(fd, label, CAP_NS);
}
static void denied_usage(int fd, uint64_t slot, uint64_t generation, unsigned status) {
    unsigned char q[64], r[128];
    request(q, 2, slot, generation);
    CHECK(transact(fd, q, sizeof q, r, sizeof r) == 0, "denied_usage_transport");
    response_header(r, q, status, 0, 0);
}
static void denied_fd(int fd, int error) {
    unsigned char q[64], r[128];
    request(q, 2, 1, 1); errno = 0;
    CHECK(transact(fd, q, sizeof q, r, sizeof r) == -1 && errno == error,
          "foreign_or_old_fd_errno");
    CHECK(uniform(r, sizeof r, 0xa5), "denied_fd_wrote_response");
}

static void check_boot_page(void) {
    errno = 0;
    boot_page = (unsigned char *)(uintptr_t)getauxval(AT_HEPTA_BOOT);
    CHECK(boot_page != NULL && (uintptr_t)boot_page % PAGE_BYTES == 0, "boot_auxv_pointer");
    CHECK(memcmp(boot_page, "HOS2BOOT", 8) == 0 && get64(boot_page + 8) == 1 &&
          get64(boot_page + 16) == 1 && get64(boot_page + 24) == 1 &&
          uniform(boot_page + 32, PAGE_BYTES - 32, 0), "boot_page_layout");
    record("G1C_BOOT_PAGE_OK version=1 slot=1 generation=1");
}

static void check_disabled_and_malformed(int fd) {
    unsigned char q[104], r[128];
    const unsigned lengths[] = {32, 40, 40};
    for (unsigned i = 0; i < 3; ++i) {
        request(q, (uint16_t)(i + 3), 1, 1);
        memset(q + 64, 0, 40); put32(q + 16, lengths[i]);
        if (i == 0) {
            memset(q + 32, 0, 8);
            put64(q + 64, 1); put64(q + 72, PERIOD_NS); put64(q + 80, CAP_NS);
        } else {
            memcpy(q + 64, boot_id, 16); memcpy(q + 80, capspace, 16);
            put64(q + 96, 1);
        }
        errno = 0;
        CHECK(transact(fd, q, 64 + lengths[i], r, sizeof r) == -1 && errno == EOPNOTSUPP,
              "management_history_still_disabled");
        CHECK(uniform(r, sizeof r, 0xa5), "disabled_opcode_wrote_response");
    }
    record("G1C_DISABLED_OPERATIONS_OK count=3");
    request(q, 2, 1, 1); errno = 0;
    CHECK(transact(fd, q, 64, r, 127) == -1 && errno == EMSGSIZE, "short_read_usage_copyout");
    request(q, 2, 1, 1); q[0] = 'X'; errno = 0;
    CHECK(transact(fd, q, 64, r, sizeof r) == -1 && errno == EPROTONOSUPPORT, "bad_magic");
    errno = 0;
    CHECK(ioctl(fd, HOS2_IOCTL, NULL) == -1 && errno == EFAULT, "null_transport");
    record("G1C_INVALID_TRANSPORT_DENIED");
}

static void seal_case(const char *name, int result) {
    CHECK(result == -1 && errno == EPERM, name);
    record("G1C_SEAL_CASE name=%s result=PASS errno=%d", name, errno);
}
static int unexpected_clone(void *unused) { (void)unused; return 0; }
static void check_sealed_mappings(void) {
    void *code = (void *)((uintptr_t)&check_sealed_mappings & ~(uintptr_t)(PAGE_BYTES - 1));
    errno = 0; seal_case("boot_add_write", mprotect(boot_page, PAGE_BYTES, PROT_READ | PROT_WRITE));
    errno = 0; seal_case("code_add_write", mprotect(code, PAGE_BYTES, PROT_READ | PROT_WRITE | PROT_EXEC));
    errno = 0; seal_case("boot_add_exec", mprotect(boot_page, PAGE_BYTES, PROT_READ | PROT_EXEC));
    errno = 0;
    void *p = mmap(NULL, PAGE_BYTES, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    seal_case("new_exec_mapping", p == MAP_FAILED ? -1 : 0);
    errno = 0;
    p = mmap(boot_page, PAGE_BYTES, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    seal_case("boot_fixed_replace", p == MAP_FAILED ? -1 : 0);
    errno = 0; seal_case("boot_unmap", munmap(boot_page, PAGE_BYTES));
    errno = 0; seal_case("boot_discard", madvise(boot_page, PAGE_BYTES, MADV_DONTNEED));
    p = mmap(NULL, PAGE_BYTES, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    CHECK(p != MAP_FAILED, "ordinary_anon_mapping");
    errno = 0;
    void *remapped = mremap(p, PAGE_BYTES, PAGE_BYTES * 2, MREMAP_MAYMOVE);
    seal_case("remap_alias", remapped == MAP_FAILED ? -1 : 0);
    CHECK(munmap(p, PAGE_BYTES) == 0, "ordinary_anon_unmap");
    p = mmap(NULL, PAGE_BYTES * 16, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    CHECK(p != MAP_FAILED, "clone_stack");
    errno = 0;
    int cloned = clone(unexpected_clone, (char *)p + PAGE_BYTES * 16, CLONE_VM | SIGCHLD, NULL);
    if (cloned > 0) waitpid(cloned, NULL, 0);
    seal_case("cross_process_clone_vm", cloned);
    CHECK(munmap(p, PAGE_BYTES * 16) == 0, "clone_stack_unmap");
    record("G1C_MAPPINGS_SEALED cases=9");
}

static int open_control(int cloexec) {
    int fd = open("/dev/hepta-control", O_RDWR | (cloexec ? O_CLOEXEC : 0));
    CHECK(fd >= 0, "open_control");
    return fd;
}
static void *thread_observe(void *unused) {
    (void)unused;
    int fd = open_control(1);
    unsigned char space[16];
    query(fd, space);
    CHECK(memcmp(space, capspace, 16) == 0, "thread_capspace_changed");
    read_usage(fd, "thread");
    CHECK(close(fd) == 0, "thread_close");
    return NULL;
}

static void send_two_fds(int socket, int first, int second) {
    char byte = 'G';
    struct iovec iov = {.iov_base = &byte, .iov_len = 1};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } control;
    memset(&control, 0, sizeof control);
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
                            .msg_control = control.bytes, .msg_controllen = sizeof control};
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&message);
    cmsg->cmsg_level = SOL_SOCKET; cmsg->cmsg_type = SCM_RIGHTS;
    cmsg->cmsg_len = CMSG_LEN(2 * sizeof(int));
    int fds[2] = {first, second};
    memcpy(CMSG_DATA(cmsg), fds, sizeof fds);
    CHECK(sendmsg(socket, &message, 0) == 1, "send_scm_fds");
}
static void receive_two_fds(int socket, int fds[2]) {
    char byte = 0;
    struct iovec iov = {.iov_base = &byte, .iov_len = 1};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } control;
    memset(&control, 0, sizeof control);
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
                            .msg_control = control.bytes, .msg_controllen = sizeof control};
    CHECK(recvmsg(socket, &message, MSG_CMSG_CLOEXEC) == 1 && byte == 'G' &&
          message.msg_flags == MSG_CMSG_CLOEXEC, "receive_scm_fds");
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&message);
    CHECK(cmsg != NULL && cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS &&
          cmsg->cmsg_len == CMSG_LEN(2 * sizeof(int)) && CMSG_NXTHDR(&message, cmsg) == NULL,
          "exact_scm_fd_count");
    memcpy(fds, CMSG_DATA(cmsg), 2 * sizeof(int));
    CHECK(fds[0] >= 0 && fds[1] >= 0 && fds[0] != fds[1], "distinct_scm_fds");
    CHECK(fcntl(fds[0], F_GETFD) == FD_CLOEXEC && fcntl(fds[1], F_GETFD) == FD_CLOEXEC,
          "scm_descriptors_cloexec");
}

static void check_fork_and_transfer(int fd, int memfd) {
    int sockets[2];
    CHECK(socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sockets) == 0, "socketpair");
    pid_t child = fork();
    CHECK(child >= 0, "fork");
    if (child == 0) {
        close(sockets[0]);
        denied_fd(fd, EPERM);
        record("G1C_FORK_FD_DENIED");
        close(fd); close(memfd);
        int fresh = open_control(1);
        unsigned char space[16];
        query(fresh, space);
        CHECK(memcmp(space, capspace, 16) != 0, "fork_capspace_reused");
        record("G1C_FORK_CAPSPACE_DISTINCT");
        /* A copied bootstrap page is discovery data, never an authority token. */
        CHECK(mprotect(boot_page, PAGE_BYTES, PROT_READ | PROT_WRITE) == 0, "fork_private_page_write");
        put64(boot_page + 16, 1); put64(boot_page + 24, 1);
        boot_page[32] = 0x7f;
        denied_usage(fresh, 1, 1, 2);
        record("G1C_FORGED_BOOT_PAGE_DENIED");
        int received[2];
        receive_two_fds(sockets[1], received);
        denied_fd(received[0], EPERM);
        record("G1C_SCM_FD_DENIED");
        unsigned char changed = 'X'; errno = 0;
        CHECK(pwrite(received[1], &changed, 1, (off_t)(uintptr_t)boot_page) == -1 && errno == EIO,
              "transferred_parent_mem_write");
        record("G1C_TRANSFERRED_MEM_WRITE_DENIED");
        errno = 0;
        int alien = open("/proc/1/mem", O_RDWR | O_CLOEXEC);
        CHECK(alien == -1 && errno == EACCES, "alien_mem_open");
        record("G1C_ALIEN_MEM_OPEN_DENIED");
        close(received[0]); close(received[1]); close(fresh); close(sockets[1]);
        CHECK(setuid(65534) == 0, "child_setuid"); errno = 0;
        int unprivileged = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
        CHECK(unprivileged == -1 && errno == EACCES, "nonroot_control_open");
        record("G1C_NONROOT_OPEN_DENIED");
        _exit(0);
    }
    close(sockets[1]);
    send_two_fds(sockets[0], fd, memfd);
    close(sockets[0]);
    int status;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "fork_child_result");
    record("G1C_FORK_CHILD_OK");
    CHECK(memcmp(boot_page, "HOS2BOOT", 8) == 0 && boot_page[32] == 0, "fork_cow_changed_parent");
    read_usage(fd, "after_fork");
    record("G1C_FORK_PARENT_AUTHORITY_STABLE");
}

static void read_text(const char *path, char *text, size_t size) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "open_cpu_owner_file");
    size_t done = 0;
    while (done + 1 < size) {
        ssize_t n = read(fd, text + done, size - done - 1);
        CHECK(n >= 0, "read_cpu_owner_file");
        if (n == 0) break;
        done += (size_t)n;
    }
    char extra;
    CHECK(read(fd, &extra, 1) == 0, "cpu_owner_file_bound");
    CHECK(close(fd) == 0, "close_cpu_owner_file");
    text[done] = '\0';
}
static uint64_t monotonic_ns(void) {
    struct timespec now;
    CHECK(clock_gettime(CLOCK_MONOTONIC, &now) == 0, "clock_gettime");
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}
static void write_cpu_max(const char *path, const char *value) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    CHECK(fd >= 0, "open_cpu_max_writer");
    size_t length = strlen(value);
    CHECK(write(fd, value, length) == (ssize_t)length, "write_original_cpu_max");
    CHECK(close(fd) == 0, "close_cpu_max_writer");
}
static void check_real_cpu_owner(int fd) {
    char membership[256], path[512], max_path[512], text[2048], extra;
    read_text("/proc/self/cgroup", membership, sizeof membership);
    CHECK(strncmp(membership, "0::/hepta-g1c-", strlen("0::/hepta-g1c-")) == 0,
          "real_cgroup_membership");
    char *newline = strchr(membership, '\n');
    CHECK(newline != NULL && newline[1] == '\0', "single_cgroup_membership");
    *newline = '\0';
    const char *relative = membership + 3;
    CHECK(strstr(relative, "..") == NULL && strchr(relative + 1, '/') == NULL,
          "bounded_cgroup_path");
    int n = snprintf(max_path, sizeof max_path, "/sys/fs/cgroup%s/cpu.max", relative);
    CHECK(n > 0 && (size_t)n < sizeof max_path, "cpu_max_path");
    read_text(max_path, text, sizeof text);
    uint64_t quota, period;
    CHECK(sscanf(text, "%" SCNu64 " %" SCNu64 " %c", &quota, &period, &extra) == 2 &&
          quota == 50000 && period == 100000, "real_cpu_max");
    struct usage before = read_usage(fd, "before_work");
    uint64_t deadline = monotonic_ns() + UINT64_C(40000000);
    volatile uint64_t work = 1;
    do {
        for (unsigned i = 0; i < 20000; ++i) work = work * UINT64_C(6364136223846793005) + 1;
    } while (monotonic_ns() < deadline);
    (void)work;
    struct usage left = read_usage(fd, "before_stat");
    n = snprintf(path, sizeof path, "/sys/fs/cgroup%s/cpu.stat", relative);
    CHECK(n > 0 && (size_t)n < sizeof path, "cpu_stat_path");
    read_text(path, text, sizeof text);
    uint64_t usage_usec;
    CHECK(sscanf(text, "usage_usec %" SCNu64, &usage_usec) == 1 &&
          usage_usec <= UINT64_MAX / 1000, "parse_real_cpu_stat");
    struct usage right = read_usage(fd, "after_stat");
    CHECK(left.cumulative > before.cumulative && right.cumulative >= left.cumulative,
          "native_usage_accounts_real_work");
    CHECK(before.revision == left.revision && left.revision == right.revision,
          "read_only_changed_revision");
    /* cpu.stat uses jiffies; preserve it without asserting nanosecond equivalence. */
    record("G1C_CPU_STAT_OBSERVATION usage_usec=%" PRIu64 " before_ns=%" PRIu64
           " after_ns=%" PRIu64, usage_usec, left.cumulative, right.cumulative);
    /* Exercise the ORIGINAL Linux manager of this same disposable leaf. This
     * is not a HOS2 management grant or an effectful native request. The public
     * native observation must reflect that owner's real revision and config. */
    write_cpu_max(max_path, "50000 100000");
    struct usage same = read_usage(fd, "same_linux_budget");
    CHECK(same.revision == right.revision + 1 && same.cumulative >= right.cumulative,
          "same_linux_budget_owner_revision");
    CHECK(same.window_start != right.window_start || same.window_consumed >= right.window_consumed,
          "same_linux_budget_refilled_window");
    write_cpu_max(max_path, "25000 100000");
    struct usage changed = read_usage_budget(fd, "changed_linux_budget", UINT64_C(25000000));
    CHECK(changed.revision == same.revision + 1, "linux_budget_revision_not_observed");
    write_cpu_max(max_path, "50000 100000");
    struct usage restored = read_usage(fd, "restored_linux_budget");
    CHECK(restored.revision == changed.revision + 1, "linux_budget_restore_not_observed");
    record("G1C_REAL_CPU_OWNER_MATCH same_revision=%" PRIu64 " changed_revision=%" PRIu64
           " restored_revision=%" PRIu64, same.revision, changed.revision, restored.revision);
}

static void hex16(const unsigned char *value, char output[33]) {
    static const char digits[] = "0123456789abcdef";
    for (unsigned i = 0; i < 16; ++i) {
        output[2 * i] = digits[value[i] >> 4]; output[2 * i + 1] = digits[value[i] & 15];
    }
    output[32] = '\0';
}
static void post_exec(int argc, char **argv) {
    CHECK(getpid() == 1 && argc == 5, "post_exec_pid_arguments");
    char *end;
    errno = 0;
    long fd = strtol(argv[2], &end, 10);
    CHECK(errno == 0 && *end == '\0' && end != argv[2] && fd >= 0 && fd <= INT_MAX,
          "post_exec_descriptor");
    denied_fd((int)fd, ESTALE);
    record("G1C_EXEC_OLD_FD_DENIED");
    CHECK(close((int)fd) == 0, "post_exec_close_old");
    int fresh = open_control(1);
    unsigned char space[16]; char current[33];
    query(fresh, space);
    hex16(space, current);
    CHECK(strlen(argv[3]) == 32 && strcmp(current, argv[3]) != 0, "post_exec_new_capspace");
    hex16(boot_id, current);
    CHECK(strlen(argv[4]) == 32 && strcmp(current, argv[4]) == 0, "post_exec_same_boot");
    record("G1C_EXEC_CAPSPACE_ROTATED");
    errno = 0;
    CHECK(getauxval(AT_HEPTA_BOOT) == 0 && errno == ENOENT, "post_exec_no_boot_auxv");
    record("G1C_EXEC_AUXV_ABSENT");
    denied_usage(fresh, 1, 1, 2);
    record("G1C_EXEC_NO_GRANT_OK");
    CHECK(close(fresh) == 0, "post_exec_close_fresh");
    record("G1C_COMPLETE initial_manifest=exact observe=real_owner manage=disabled exec_grant=revoked");
    reboot(RB_POWER_OFF);
    failure("poweroff_returned", __LINE__);
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc > 1 && strcmp(argv[1], "--post-exec") == 0) post_exec(argc, argv);
    CHECK(getpid() == 1 && argc == 1, "actual_initial_process");
    record("G1C_INIT_STARTED pid=1");
    check_boot_page();
    CHECK(mount("none", "/proc", "proc", 0, NULL) == 0, "mount_proc");
    CHECK(mount("none", "/sys", "sysfs", 0, NULL) == 0, "mount_sysfs");
    CHECK(mount("none", "/sys/fs/cgroup", "cgroup2", 0, NULL) == 0, "mount_cgroup");
    /* This fd deliberately survives the final exec in this SAME, granted PID. */
    int fd = open_control(0);
    query(fd, capspace);
    record("G1C_QUERYABI_OK supported_ops=6 max_request=0 max_response=64 features=0");
    read_usage(fd, "initial");
    record("G1C_READ_USAGE_OK");
    denied_usage(fd, 2, 1, 3); record("G1C_WRONG_SLOT_DENIED");
    denied_usage(fd, 1, 2, 3); record("G1C_WRONG_GENERATION_DENIED");
    check_disabled_and_malformed(fd);
    check_sealed_mappings();
    /* Transfer a genuinely open proc-memory file to exercise the write-time guard. */
    int memfd = open("/proc/self/mem", O_RDWR | O_CLOEXEC);
    CHECK(memfd >= 0, "open_self_mem");
    unsigned char byte = 'X'; errno = 0;
    CHECK(pwrite(memfd, &byte, 1, (off_t)(uintptr_t)boot_page) == -1 && errno == EIO,
          "self_proc_mem_write");
    record("G1C_SELF_MEM_WRITE_DENIED");
    pthread_t worker;
    CHECK(pthread_create(&worker, NULL, thread_observe, NULL) == 0, "create_same_process_thread");
    CHECK(pthread_join(worker, NULL) == 0, "join_same_process_thread");
    read_usage(fd, "after_thread");
    record("G1C_THREAD_SHARE_OK");
    int duplicated = dup(fd);
    CHECK(duplicated >= 0, "dup_control");
    unsigned char space[16]; query(duplicated, space);
    CHECK(memcmp(space, capspace, 16) == 0, "dup_capspace_changed");
    read_usage(duplicated, "dup"); close(duplicated);
    record("G1C_DUP_SESSION_OK");
    check_fork_and_transfer(fd, memfd);
    CHECK(close(memfd) == 0, "close_self_mem");
    check_real_cpu_owner(fd);
    char *invalid_args[] = {"g1c-init", NULL};
    errno = 0;
    CHECK(execve("/missing-g1c-executable", invalid_args, environ) == -1 && errno == ENOENT,
          "failed_exec_errno");
    query(fd, space);
    CHECK(memcmp(space, capspace, 16) == 0, "failed_exec_changed_capspace");
    read_usage(fd, "after_failed_exec");
    record("G1C_FAILED_EXEC_GRANT_STABLE");
    read_usage(fd, "pre_exec");
    record("G1C_PRE_EXEC_USAGE_OK");
    char fd_text[32], old_space[33], old_boot[33];
    snprintf(fd_text, sizeof fd_text, "%d", fd);
    hex16(capspace, old_space); hex16(boot_id, old_boot);
    char *next[] = {"/test/g1c-init", "--post-exec", fd_text, old_space, old_boot, NULL};
    execve(next[0], next, environ);
    failure("final_same_process_exec_returned", __LINE__);
    return 1;
}
