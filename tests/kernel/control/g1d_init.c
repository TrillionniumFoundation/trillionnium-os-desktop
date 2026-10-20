/* SPDX-License-Identifier: MPL-2.0 */
/* Three actual, independently prepared initial processes in a disposable guest.
 * Files below coordinate this fixed probe; they never confer HOS2 authority.
 * This qualification is deliberately not a Hepta disk-durability certificate. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
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
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define HOS2_IOCTL 0xC0204802U
#define AT_HEPTA_BOOT 240
#define PAGE_BYTES 4096U
#define PERIOD_NS UINT64_C(100000000)
#define MAX_CAP_NS UINT64_C(50000000)
#define WINDOW_CAPACITY 1024U
#define IPC_MAGIC UINT64_C(0x4731444348414e32)
#define IPC_DIR "/tmp/g1d"

enum { OK = 0, INVALID = 1, DENIED = 2, STALE = 3, REVOKED = 4,
       CONFLICT = 5, EXHAUSTED = 6, UNSUPPORTED = 7, UNKNOWN = 8,
       BUSY = 9, OUT_OF_ORDER = 10, RETIRED = 11 };
enum { RESERVED_STATE = 0, TERMINAL_STATE = 1, RETIRED_STATE = 2,
       NOT_SEEN_STATE = 3, HISTORY_LOST_STATE = 4 };
enum { REC_QUERY_MANAGER = 1, REC_RETIRE_MANAGER = 2, REC_INSTALL = 3,
       REC_QUERY_SELF = 4, REC_STOP = 5 };

static unsigned char boot_id[16], manager_space[16], recovery_space[16], own_space[16];
static unsigned char *boot_page;
static uint64_t role, observe_slot, observe_gen, manage_slot, manage_gen;
static uint64_t manager_history_slot, manager_history_gen, recovery_history_slot, recovery_history_gen;
static pid_t manager_pid, workload_pid, recovery_pid;
static uint64_t request_id, command_id;
static int control_fd = -1;

static void record(const char *format, ...) {
    char line[2048];
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
    record("G1D_FAIL at=%s line=%d errno=%d pid=%ld role=%" PRIu64,
           at, line, saved, (long)getpid(), role);
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
static int uniform(const unsigned char *p, size_t n, unsigned char value) {
    for (size_t i = 0; i < n; ++i) if (p[i] != value) return 0;
    return 1;
}
static uint64_t now_ns(void) {
    struct timespec t;
    CHECK(clock_gettime(CLOCK_BOOTTIME, &t) == 0, "boottime");
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static void sleep_ms(unsigned ms) {
    struct timespec t = {(time_t)(ms / 1000), (long)(ms % 1000) * 1000000};
    while (nanosleep(&t, &t) != 0) CHECK(errno == EINTR, "nanosleep");
}
static void hex16(const unsigned char *data, char text[33]) {
    static const char hex[] = "0123456789abcdef";
    for (unsigned i = 0; i < 16; ++i) {
        text[2 * i] = hex[data[i] >> 4]; text[2 * i + 1] = hex[data[i] & 15];
    }
    text[32] = 0;
}
static void unhex16(const char *text, unsigned char data[16]) {
    CHECK(strlen(text) == 32, "exec_identity_length");
    for (unsigned i = 0; i < 16; ++i) {
        unsigned value;
        CHECK(sscanf(text + 2 * i, "%2x", &value) == 1, "exec_identity_hex");
        data[i] = (unsigned char)value;
    }
}

static void request(unsigned char q[104], uint16_t opcode, uint64_t slot, uint64_t generation) {
    memset(q, 0, 104);
    memcpy(q, "HOS2", 4);
    put16(q + 4, 2); put16(q + 8, opcode); put32(q + 12, 64);
    put64(q + 24, ++request_id);
    put64(q + 32, UINT64_C(0x47314450524f4200) | role);
    put64(q + 40, slot); put64(q + 48, generation);
}
static void install_request(unsigned char q[104], uint64_t seq, uint64_t revision, uint64_t cap) {
    request(q, 3, manage_slot, manage_gen);
    put32(q + 16, 32);
    put64(q + 24, seq); put64(q + 32, 0);
    put64(q + 64, revision); put64(q + 72, PERIOD_NS); put64(q + 80, cap);
}
static int raw_transact(int fd, const unsigned char *q, unsigned qlen, void *r, unsigned rlen) {
    unsigned char transport[32] = {0};
    put64(transport, (uint64_t)(uintptr_t)q); put64(transport + 8, (uint64_t)(uintptr_t)r);
    put32(transport + 16, qlen); put32(transport + 20, rlen);
    return ioctl(fd, HOS2_IOCTL, transport);
}
static int transact(int fd, const unsigned char *q, unsigned qlen, unsigned char r[128]) {
    memset(r, 0xa5, 128);
    return raw_transact(fd, q, qlen, r, 128);
}
static void response_header(const unsigned char r[128], const unsigned char *q,
                            unsigned status, unsigned payload, uint64_t revision) {
    CHECK(memcmp(r, "HOSR", 4) == 0 && get16(r + 4) == 2 && get16(r + 6) == 0,
          "response_protocol");
    CHECK(get16(r + 8) == get16(q + 8) && get16(r + 10) == status, "response_opcode_status");
    CHECK(get32(r + 12) == 64 && get32(r + 16) == payload && get32(r + 20) == 0,
          "response_lengths_reserved");
    CHECK(memcmp(r + 24, q + 24, 16) == 0 && !uniform(r + 40, 16, 0),
          "response_request_boot_identity");
    CHECK(get64(r + 56) == revision, "response_revision");
    CHECK(uniform(r + 64 + payload, 64 - payload, 0xa5), "response_copyout_tail");
    if (!uniform(boot_id, 16, 0)) CHECK(memcmp(boot_id, r + 40, 16) == 0, "boot_identity_changed");
}
static int open_control(int cloexec) {
    int fd = open("/dev/hepta-control", O_RDWR | (cloexec ? O_CLOEXEC : 0));
    CHECK(fd >= 0, "open_control");
    return fd;
}
static void query(int fd, unsigned char space[16]) {
    unsigned char q[104], r[128];
    request(q, 1, 0, 0);
    CHECK(transact(fd, q, 64, r) == 0, "query_ioctl");
    response_header(r, q, OK, 48, 0);
    CHECK(!uniform(r + 64, 16, 0) && get32(r + 80) == PAGE_BYTES &&
          get32(r + 84) == 40 && get32(r + 88) == 64 && get32(r + 92) == 0 &&
          get64(r + 96) == 62 && get64(r + 104) == 0, "query_exact_capabilities");
    memcpy(boot_id, r + 40, 16); memcpy(space, r + 64, 16);
}
struct usage {
    uint64_t sample, cumulative, window_start, consumed, cap, period, events, dropped, revision;
};
static struct usage usage_read(int fd, uint64_t cap) {
    unsigned char q[104], r[128];
    request(q, 2, observe_slot, observe_gen);
    CHECK(transact(fd, q, 64, r) == 0, "usage_ioctl");
    CHECK(get64(r + 56) != 0, "usage_revision_nonzero");
    response_header(r, q, OK, 64, get64(r + 56));
    struct usage u = {get64(r+64),get64(r+72),get64(r+80),get64(r+88),
        get64(r+96),get64(r+104),get64(r+112),get64(r+120),get64(r+56)};
    CHECK(u.cap == cap && u.period == PERIOD_NS && u.sample > 0, "usage_exact_cap");
    CHECK(u.window_start == u.sample / PERIOD_NS * PERIOD_NS &&
          u.consumed <= u.cumulative && u.consumed <= u.sample % PERIOD_NS &&
          u.cumulative <= u.sample &&
          u.cumulative - u.consumed <= u.window_start && u.dropped <= u.events,
          "usage_invariants");
    return u;
}
static void empty_response(int fd, unsigned char *q, unsigned qlen, unsigned status) {
    unsigned char r[128];
    CHECK(transact(fd, q, qlen, r) == 0, "denial_transport");
    response_header(r, q, status, 0, 0);
}
static void bad_transport(int fd, unsigned char *q, unsigned qlen, int error) {
    unsigned char r[128];
    errno = 0;
    CHECK(transact(fd, q, qlen, r) == -1 && errno == error, "transport_errno");
    CHECK(uniform(r, 128, 0xa5), "transport_error_copyout");
}
static void history(int fd, uint64_t slot, uint64_t gen, const unsigned char space[16],
                    uint64_t seq, int retire, unsigned status, unsigned char r[128]) {
    unsigned char q[104];
    request(q, retire ? 5 : 4, slot, gen); put32(q + 16, 40);
    memcpy(q + 64, boot_id, 16); memcpy(q + 80, space, 16); put64(q + 96, seq);
    CHECK(transact(fd, q, 104, r) == 0, "history_ioctl");
    response_header(r, q, status, status ? 0 : (retire ? 16 : 64), 0);
    if (status == OK && !retire) {
        CHECK(get32(r + 68) == 0 && get64(r + 72) == seq, "history_reserved_sequence");
    }
}
static void history_empty(const unsigned char r[128], unsigned state, uint64_t seq) {
    CHECK(get16(r + 64) == state && get16(r + 66) == OK && get64(r + 72) == seq &&
          uniform(r + 80, 48, 0), "history_empty_state");
}
static void history_terminal(const unsigned char r[128], uint64_t seq, unsigned status,
                             const unsigned char *receipt) {
    CHECK(get16(r + 64) == TERMINAL_STATE && get16(r + 66) == status &&
          get64(r + 72) == seq, "history_terminal_state");
    if (status == OK) {
        CHECK(receipt != NULL && !uniform(r + 80, 16, 0), "history_stable_object");
        CHECK(get64(r + 96) == get64(receipt + 56) &&
              memcmp(r + 104, receipt + 64, 24) == 0, "history_exact_saved_receipt");
    } else {
        CHECK(uniform(r + 80, 48, 0), "history_error_has_no_success_fields");
    }
}
static struct usage install_ok(uint64_t seq, struct usage before, uint64_t cap,
                               unsigned char r[128], int emit) {
    unsigned char q[104];
    install_request(q, seq, before.revision, cap);
    CHECK(transact(control_fd, q, 96, r) == 0, "install_ioctl");
    response_header(r, q, OK, 24, before.revision + 1);
    CHECK(get64(r + 64) == before.revision, "install_previous_revision");
    struct usage after = usage_read(control_fd, cap);
    uint64_t effective = get64(r + 72), consumed = get64(r + 80);
    CHECK(after.revision == before.revision + 1 && after.cumulative >= before.cumulative &&
          effective >= before.sample && effective <= after.sample &&
          consumed <= effective % PERIOD_NS, "install_preserves_accounting");
    if (effective / PERIOD_NS * PERIOD_NS == before.window_start)
        CHECK(consumed >= before.consumed, "install_reset_window_consumption");
    if (effective / PERIOD_NS * PERIOD_NS == after.window_start)
        CHECK(after.consumed >= consumed, "post_install_reset_window_consumption");
    if (emit) record("G1D_APPLY role=%" PRIu64 " sequence=%" PRIu64 " cap=%" PRIu64
                     " previous=%" PRIu64 " revision=%" PRIu64 " effective=%" PRIu64
                     " consumed=%" PRIu64 " before_sample=%" PRIu64 " before_total=%" PRIu64
                     " before_start=%" PRIu64 " before_used=%" PRIu64
                     " after_sample=%" PRIu64 " after_total=%" PRIu64
                     " after_start=%" PRIu64 " after_used=%" PRIu64,
                     role, seq, cap, before.revision, after.revision, effective, consumed,
                     before.sample, before.cumulative, before.window_start, before.consumed,
                     after.sample, after.cumulative, after.window_start, after.consumed);
    return after;
}

struct message {
    uint64_t magic, id, action, a, b, expected_status;
    unsigned char response[128];
};
static void write_file(const char *path, const void *bytes, size_t length) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    CHECK(fd >= 0, "ipc_create");
    const unsigned char *p = bytes;
    while (length) {
        ssize_t n = write(fd, p, length);
        if (n < 0 && errno == EINTR) continue;
        CHECK(n > 0, "ipc_write");
        p += n; length -= (size_t)n;
    }
    CHECK(close(fd) == 0, "ipc_close");
}
static void publish_message(const char *name, const struct message *message) {
    char temporary[128], final[128];
    CHECK(snprintf(temporary, sizeof temporary, IPC_DIR "/%s.new", name) > 0, "ipc_temp_name");
    CHECK(snprintf(final, sizeof final, IPC_DIR "/%s", name) > 0, "ipc_final_name");
    write_file(temporary, message, sizeof *message);
    CHECK(rename(temporary, final) == 0, "ipc_publish");
}
static int read_message(const char *name, struct message *message) {
    char path[128];
    CHECK(snprintf(path, sizeof path, IPC_DIR "/%s", name) > 0, "ipc_read_name");
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) { CHECK(errno == ENOENT, "ipc_read_open"); return 0; }
    unsigned char *p = (unsigned char *)message;
    size_t remaining = sizeof *message;
    while (remaining) {
        ssize_t n = read(fd, p, remaining);
        if (n < 0 && errno == EINTR) continue;
        CHECK(n > 0, "ipc_read_complete");
        p += n; remaining -= (size_t)n;
    }
    unsigned char extra;
    CHECK(read(fd, &extra, 1) == 0 && close(fd) == 0, "ipc_exact_size");
    CHECK(message->magic == IPC_MAGIC, "ipc_magic");
    return 1;
}
static struct message await_message(const char *name, uint64_t id) {
    uint64_t deadline = now_ns() + UINT64_C(20000000000);
    struct message message;
    while (now_ns() < deadline) {
        if (read_message(name, &message)) {
            CHECK(message.id <= id, "ipc_future_id");
            if (message.id == id) return message;
        }
        sleep_ms(2);
    }
    failure("ipc_timeout", __LINE__);
    return (struct message){0};
}
static struct message recovery_command(uint64_t action, uint64_t a, uint64_t b, unsigned status) {
    struct message command = { .magic = IPC_MAGIC, .id = ++command_id,
        .action = action, .a = a, .b = b, .expected_status = status };
    publish_message("command", &command);
    struct message reply = await_message("reply", command.id);
    CHECK(reply.action == action && reply.a == a && reply.b == b &&
          reply.expected_status == status, "ipc_reply_binding");
    return reply;
}
static void bootstrap(void) {
    boot_page = (unsigned char *)(uintptr_t)getauxval(AT_HEPTA_BOOT);
    CHECK(boot_page != NULL && (uintptr_t)boot_page % PAGE_BYTES == 0, "bootstrap_address");
    CHECK(memcmp(boot_page, "HOS2BOOT", 8) == 0 && get64(boot_page + 8) == 2 &&
          get64(boot_page + 24) == 192 && uniform(boot_page + 192, PAGE_BYTES - 192, 0),
          "bootstrap_layout");
    role = get64(boot_page + 16);
    observe_slot = get64(boot_page + 32); observe_gen = get64(boot_page + 40);
    manage_slot = get64(boot_page + 48); manage_gen = get64(boot_page + 56);
    manager_history_slot = get64(boot_page + 64); manager_history_gen = get64(boot_page + 72);
    recovery_history_slot = get64(boot_page + 80); recovery_history_gen = get64(boot_page + 88);
    memcpy(boot_id, boot_page + 96, 16);
    memcpy(manager_space, boot_page + 112, 16); memcpy(recovery_space, boot_page + 128, 16);
    CHECK(get64(boot_page + 144) <= INT_MAX && get64(boot_page + 152) <= INT_MAX &&
          get64(boot_page + 160) <= INT_MAX, "bootstrap_pid_width");
    manager_pid = (pid_t)get64(boot_page + 144); workload_pid = (pid_t)get64(boot_page + 152);
    recovery_pid = (pid_t)get64(boot_page + 160);
    CHECK(manager_pid == 1 && workload_pid > 1 && recovery_pid > 1 && workload_pid != recovery_pid &&
          role >= 1 && role <= 3, "bootstrap_roles");
    CHECK(getpid() == (role == 1 ? manager_pid : role == 2 ? workload_pid : recovery_pid),
          "bootstrap_actual_process");
    CHECK(!uniform(boot_id, 16, 0) && !uniform(manager_space, 16, 0) &&
          !uniform(recovery_space, 16, 0) && memcmp(manager_space, recovery_space, 16) != 0,
          "bootstrap_namespaces");
    CHECK(get64(boot_page + 168) == MAX_CAP_NS && get64(boot_page + 176) == PERIOD_NS &&
          get64(boot_page + 184) == UINT64_C(300000000000), "bootstrap_envelope");
    if (role == 2) CHECK(uniform(boot_page + 32, 64, 0), "workload_has_no_grant_handles");
    else CHECK(observe_slot == 1 && observe_gen == 1 && manage_slot == 2 && manage_gen == 1 &&
               manager_history_slot == 3 && manager_history_gen == 1 &&
               recovery_history_slot == (role == 3 ? 4U : 0U) &&
               recovery_history_gen == (role == 3 ? 1U : 0U), "bootstrap_grant_handles");
    errno = 0;
    CHECK(mprotect(boot_page, PAGE_BYTES, PROT_READ | PROT_WRITE) == -1 && errno == EPERM,
          "bootstrap_page_sealed");
    record("G1D_BOOT role=%" PRIu64 " pid=%ld manager=%ld workload=%ld recovery=%ld version=2 bytes=192",
           role, (long)getpid(), (long)manager_pid, (long)workload_pid, (long)recovery_pid);
}
static void wait_ready(void) {
    (void)await_message("ready", 0);
}
static uint64_t heartbeat(void) {
    unsigned char bytes[8];
    int fd = open(IPC_DIR "/heartbeat", O_RDONLY | O_CLOEXEC);
    if (fd < 0) { CHECK(errno == ENOENT, "heartbeat_open"); return 0; }
    ssize_t n = pread(fd, bytes, sizeof bytes, 0);
    CHECK((n == 0 || n == 8) && close(fd) == 0, "heartbeat_read");
    return n == 8 ? get64(bytes) : 0;
}
static void workload(void) {
    wait_ready();
    control_fd = open_control(1); query(control_fd, own_space);
    CHECK(memcmp(own_space, manager_space, 16) != 0 &&
          memcmp(own_space, recovery_space, 16) != 0, "workload_private_capspace");
    unsigned char q[104];
    request(q, 2, 1, 1); empty_response(control_fd, q, 64, DENIED);
    install_request(q, 1, 1, MAX_CAP_NS); put64(q + 40, 2); put64(q + 48, 1);
    empty_response(control_fd, q, 96, DENIED);
    record("G1D_WORKLOAD_NO_AUTHORITY");
    int fd = open(IPC_DIR "/heartbeat", O_WRONLY | O_CREAT | O_CLOEXEC, 0600);
    CHECK(fd >= 0, "workload_heartbeat_open");
    uint64_t count = 0;
    for (;;) {
        for (unsigned i = 0; i < 32768; ++i) __asm__ volatile("" : "+r"(count));
        ++count;
        unsigned char bytes[8]; put64(bytes, count);
        CHECK(pwrite(fd, bytes, sizeof bytes, 0) == 8, "workload_heartbeat_write");
    }
}
static void recovery(void) {
    wait_ready();
    control_fd = open_control(1); query(control_fd, own_space);
    CHECK(memcmp(own_space, recovery_space, 16) == 0, "recovery_capspace");
    struct message ready = {.magic=IPC_MAGIC};
    publish_message("recovery-ready", &ready);
    record("G1D_RECOVERY_READY");
    uint64_t id = 0, sequence = 0;
    for (;;) {
        struct message message = await_message("command", ++id);
        switch (message.action) {
        case REC_QUERY_MANAGER:
            history(control_fd, manager_history_slot, manager_history_gen, manager_space,
                    message.a, 0, (unsigned)message.expected_status, message.response);
            break;
        case REC_RETIRE_MANAGER:
            history(control_fd, manager_history_slot, manager_history_gen, manager_space,
                    message.a, 1, (unsigned)message.expected_status, message.response);
            break;
        case REC_INSTALL: {
            struct usage before = usage_read(control_fd, message.b);
            CHECK(before.revision == message.a, "recovery_expected_revision");
            (void)install_ok(++sequence, before, MAX_CAP_NS, message.response, 1);
            break;
        }
        case REC_QUERY_SELF:
            history(control_fd, recovery_history_slot, recovery_history_gen, recovery_space,
                    message.a, 0, (unsigned)message.expected_status, message.response);
            break;
        case REC_STOP:
            publish_message("reply", &message);
            record("G1D_RECOVERY_STOPPED");
            _exit(0);
        default: failure("unknown_recovery_command", __LINE__);
        }
        publish_message("reply", &message);
    }
}

static void denied_foreign_fd(int fd, int expected_errno) {
    unsigned char q[104];
    request(q, 2, 1, 1);
    bad_transport(fd, q, 64, expected_errno);
}
static void send_fd(int socket_fd, int fd) {
    char byte = 'F', control[CMSG_SPACE(sizeof(int))] = {0};
    struct iovec iov = {.iov_base=&byte,.iov_len=1};
    struct msghdr message = {.msg_iov=&iov,.msg_iovlen=1,
        .msg_control=control,.msg_controllen=sizeof control};
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&message);
    cmsg->cmsg_level=SOL_SOCKET; cmsg->cmsg_type=SCM_RIGHTS; cmsg->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(cmsg), &fd, sizeof fd);
    CHECK(sendmsg(socket_fd, &message, 0) == 1, "scm_send");
}
static int receive_fd(int socket_fd) {
    char byte=0, control[CMSG_SPACE(sizeof(int))] = {0};
    struct iovec iov={.iov_base=&byte,.iov_len=1};
    struct msghdr message={.msg_iov=&iov,.msg_iovlen=1,
        .msg_control=control,.msg_controllen=sizeof control};
    CHECK(recvmsg(socket_fd, &message, 0) == 1 && byte == 'F' &&
          !(message.msg_flags & (MSG_CTRUNC | MSG_TRUNC)), "scm_receive");
    struct cmsghdr *cmsg=CMSG_FIRSTHDR(&message);
    CHECK(cmsg != NULL && cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS &&
          cmsg->cmsg_len == CMSG_LEN(sizeof(int)) && CMSG_NXTHDR(&message,cmsg) == NULL,
          "scm_exact_rights");
    int fd; memcpy(&fd,CMSG_DATA(cmsg),sizeof fd);
    CHECK(fd >= 0,"scm_valid_fd");
    return fd;
}
static void fork_and_transfer(void) {
    int pair[2];
    CHECK(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,pair) == 0,"scm_socketpair");
    pid_t child=fork();
    CHECK(child >= 0,"fork_probe");
    if (child == 0) {
        close(pair[0]);
        denied_foreign_fd(control_fd,EPERM);
        int received=receive_fd(pair[1]);
        denied_foreign_fd(received,EPERM);
        int fresh=open_control(1);
        unsigned char space[16],q[104],r[128];
        query(fresh,space);
        CHECK(memcmp(space,manager_space,16) != 0 &&
              memcmp(space,recovery_space,16) != 0,"fork_new_namespace");
        request(q,2,1,1); empty_response(fresh,q,64,DENIED);
        install_request(q,1,1,MAX_CAP_NS); empty_response(fresh,q,96,DENIED);
        history(fresh,3,1,manager_space,1,0,DENIED,r);
        close(received);close(fresh);close(pair[1]);
        record("G1D_FORK_CHILD_NO_AUTHORITY");
        _exit(0);
    }
    close(pair[1]);send_fd(pair[0],control_fd);close(pair[0]);
    int status;
    CHECK(waitpid(child,&status,0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "fork_child_result");
    record("G1D_FORK_SCM_NO_AUTHORITY");
}
static void static_admission(uint64_t next, uint64_t revision) {
    unsigned char q[104],r[128];
    install_request(q,next+1,revision,MAX_CAP_NS);
    empty_response(control_fd,q,96,OUT_OF_ORDER);
    install_request(q,next,0,MAX_CAP_NS);
    bad_transport(control_fd,q,96,EINVAL);
    install_request(q,next,revision,PERIOD_NS+1);
    bad_transport(control_fd,q,96,EINVAL);
    install_request(q,next,revision,MAX_CAP_NS);put64(q+88,1);
    bad_transport(control_fd,q,96,EINVAL);
    install_request(q,next,revision,MAX_CAP_NS);put64(q+32,1);
    bad_transport(control_fd,q,96,EINVAL);
    install_request(q,0,revision,MAX_CAP_NS);
    bad_transport(control_fd,q,96,EINVAL);
    install_request(q,UINT64_MAX,revision,MAX_CAP_NS);
    bad_transport(control_fd,q,96,EINVAL);
    install_request(q,next,revision,MAX_CAP_NS);put64(q+40,99);
    empty_response(control_fd,q,96,STALE);
    install_request(q,next,revision,MAX_CAP_NS);put64(q+48,2);
    empty_response(control_fd,q,96,STALE);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,next,0,OK,r);
    history_empty(r,NOT_SEEN_STATE,next);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,next+1,0,OK,r);
    history_empty(r,NOT_SEEN_STATE,next+1);
    record("G1D_STATIC_AND_GAP_DO_NOT_RESERVE next=%" PRIu64,next);
}
static void legacy_write_denied(const char *path,const char *text,const char *label) {
    int fd=open(path,O_WRONLY|O_CLOEXEC);
    CHECK(fd >= 0,"legacy_alias_open");
    errno=0;
    CHECK(write(fd,text,strlen(text)) == -1 && errno == EACCES,"legacy_alias_write_denied");
    CHECK(close(fd) == 0,"legacy_alias_close");
    record("G1D_LEGACY_ALIAS_DENIED kind=%s errno=%d",label,EACCES);
}
static void legacy_aliases(void) {
    char proc_path[128],line[256],leaf[384],path[448],pid_text[32];
    CHECK(snprintf(proc_path,sizeof proc_path,"/proc/%ld/cgroup",(long)workload_pid)>0,
          "workload_cgroup_path");
    int fd=open(proc_path,O_RDONLY|O_CLOEXEC);
    CHECK(fd >= 0,"workload_cgroup_open");
    ssize_t n=read(fd,line,sizeof line-1);
    CHECK(n > 4 && close(fd)==0,"workload_cgroup_read");
    line[n]=0;
    CHECK(strncmp(line,"0::/",4)==0 && strchr(line+4,'\n')!=NULL,"workload_cgroup_layout");
    *strchr(line+4,'\n')=0;
    CHECK(strncmp(line+3,"/hepta-g1d-",11)==0,"workload_real_controlled_leaf");
    CHECK(snprintf(leaf,sizeof leaf,"/sys/fs/cgroup%s",line+3)>0,"workload_leaf_path");
    CHECK(snprintf(path,sizeof path,"%s/cpu.max",leaf)>0,"legacy_cpu_max_path");
    legacy_write_denied(path,"max 100000","cpu_max");
    CHECK(snprintf(path,sizeof path,"%s/cgroup.procs",leaf)>0,"legacy_membership_path");
    legacy_write_denied(path,"1","migrate_into");
    CHECK(snprintf(pid_text,sizeof pid_text,"%ld",(long)workload_pid)>0,"legacy_workload_pid");
    legacy_write_denied("/sys/fs/cgroup/cgroup.procs",pid_text,"migrate_out");
    legacy_write_denied("/sys/fs/cgroup/cgroup.subtree_control","-cpu","disable_controller");
}
static void start_workload_and_recovery(void) {
    CHECK(mount("none","/dev","devtmpfs",0,NULL)==0,"mount_devtmpfs");
    CHECK(mount("none","/proc","proc",0,NULL)==0,"mount_proc");
    CHECK(mount("none","/sys","sysfs",0,NULL)==0,"mount_sysfs");
    CHECK(mount("none","/sys/fs/cgroup","cgroup2",0,NULL)==0,"mount_cgroup");
    CHECK(mkdir(IPC_DIR,0700)==0,"probe_coordination_directory");
    struct message ready={.magic=IPC_MAGIC};
    publish_message("ready",&ready);
    (void)await_message("recovery-ready",0);
    uint64_t deadline=now_ns()+UINT64_C(10000000000);
    while (heartbeat()==0 && now_ns()<deadline) sleep_ms(2);
    CHECK(heartbeat()>0,"workload_really_running");
}
static void read_exact_file(const char *path,void *data,size_t size) {
    int fd=open(path,O_RDONLY|O_CLOEXEC);
    CHECK(fd>=0,"saved_receipt_open");
    unsigned char *p=data;
    while(size) {
        ssize_t n=read(fd,p,size);
        if(n<0 && errno==EINTR)continue;
        CHECK(n>0,"saved_receipt_read");
        p+=n;size-=(size_t)n;
    }
    unsigned char extra;
    CHECK(read(fd,&extra,1)==0 && close(fd)==0,"saved_receipt_size");
}
struct saved_terminal { unsigned char receipt[128],stable_object[16]; };

static void post_exec(int argc,char **argv) {
    CHECK(argc==10 && getpid()==1,"post_exec_actual_manager");
    role=1;
    char *end;
    control_fd=(int)strtol(argv[2],&end,10);CHECK(*end==0 && control_fd>=0,"post_exec_fd_arg");
    unhex16(argv[3],boot_id);unhex16(argv[4],manager_space);unhex16(argv[5],recovery_space);
    uint64_t last=strtoull(argv[6],&end,10);CHECK(*end==0 && last==1025,"post_exec_last_arg");
    command_id=strtoull(argv[7],&end,10);CHECK(*end==0,"post_exec_command_arg");
    workload_pid=(pid_t)strtol(argv[8],&end,10);CHECK(*end==0 && workload_pid>1,"post_exec_workload_arg");
    recovery_pid=(pid_t)strtol(argv[9],&end,10);CHECK(*end==0 && recovery_pid>1,"post_exec_recovery_arg");
    denied_foreign_fd(control_fd,ESTALE);close(control_fd);
    int fresh=open_control(1);
    query(fresh,own_space);
    CHECK(memcmp(own_space,manager_space,16)!=0 && memcmp(own_space,recovery_space,16)!=0,
          "exec_capspace_rotated");
    errno=0;
    CHECK(getauxval(AT_HEPTA_BOOT)==0 && errno==ENOENT,"exec_bootstrap_absent");
    unsigned char q[104],r[128];
    request(q,2,1,1);empty_response(fresh,q,64,DENIED);
    manage_slot=2;manage_gen=1;
    install_request(q,last+1,1,MAX_CAP_NS);empty_response(fresh,q,96,DENIED);
    history(fresh,3,1,manager_space,last,0,DENIED,r);
    struct saved_terminal saved;
    read_exact_file(IPC_DIR "/last-terminal",&saved,sizeof saved);
    struct message query_result=recovery_command(REC_QUERY_MANAGER,last,0,OK);
    history_terminal(query_result.response,last,OK,saved.receipt);
    CHECK(memcmp(query_result.response+80,saved.stable_object,16)==0,"exec_history_stable_owner");
    record("G1D_EXEC_REVOKED old_fd_errno=%d no_auxv=true own_history=denied recovery_history=terminal sequence=%" PRIu64,
           ESTALE,last);
    struct message retired=recovery_command(REC_RETIRE_MANAGER,last,0,OK);
    CHECK(get64(retired.response+64)==last && get64(retired.response+72)==last+1,
          "post_exec_independent_retirement");
    query_result=recovery_command(REC_QUERY_MANAGER,last,0,OK);
    history_empty(query_result.response,RETIRED_STATE,last);
    record("G1D_RECOVERY_RETIRED_AFTER_MANAGER_EXEC through=%" PRIu64 " next=%" PRIu64,
           last,last+1);
    CHECK(kill(workload_pid,SIGTERM)==0,"stop_workload");
    int status;
    CHECK(waitpid(workload_pid,&status,0)==workload_pid && WIFSIGNALED(status) &&
          WTERMSIG(status)==SIGTERM,"reap_workload");
    (void)recovery_command(REC_STOP,0,0,OK);
    CHECK(waitpid(recovery_pid,&status,0)==recovery_pid && WIFEXITED(status) &&
          WEXITSTATUS(status)==0,"reap_recovery");
    CHECK(close(fresh)==0,"post_exec_close");
    record("G1D_CHILDREN_REAPED workload_signal=%d recovery_exit=0",SIGTERM);
    record("G1D_COMPLETE native_manage=true history=true hepta_durability=false hardware=false");
    reboot(RB_POWER_OFF);
    failure("poweroff_returned",__LINE__);
}
static void manager(void) {
    start_workload_and_recovery();
    control_fd=open_control(0);query(control_fd,own_space);
    CHECK(memcmp(own_space,manager_space,16)==0,"manager_capspace");
    record("G1D_QUERYABI_OK supported_ops=62 max_request=40 max_response=64 features=0");
    struct usage u=usage_read(control_fd,MAX_CAP_NS);
    CHECK(u.cumulative>0,"initial_workload_cpu_measured");
    uint64_t initial_revision=u.revision;
    unsigned char q[104],r[128],first[128],third[128],hist[128],stable_object[16];
    u=install_ok(1,u,UINT64_C(25000000),first,1);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,1,0,OK,hist);
    history_terminal(hist,1,OK,first);memcpy(stable_object,hist+80,16);
    u=install_ok(2,u,UINT64_C(25000000),r,1);
    record("G1D_SAME_VALUE_NEW_D_PRESERVES_USAGE");

    /* A real inaccessible copyout must not erase a committed effect or allow
     * the retry to execute it twice. Never memset this inaccessible address. */
    struct usage before_fault=u;
    install_request(q,3,u.revision,UINT64_C(20000000));
    void *inaccessible=mmap(NULL,PAGE_BYTES,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    CHECK(inaccessible!=MAP_FAILED,"copyout_fault_mapping");
    errno=0;
    CHECK(raw_transact(control_fd,q,96,inaccessible,128)==-1 && errno==EFAULT,"actual_copyout_fault");
    CHECK(munmap(inaccessible,PAGE_BYTES)==0,"copyout_fault_unmap");
    u=usage_read(control_fd,UINT64_C(20000000));
    CHECK(u.revision==before_fault.revision+1 && u.cumulative>=before_fault.cumulative,
          "copyout_fault_did_not_undo_effect");
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,3,0,OK,hist);
    CHECK(transact(control_fd,q,96,third)==0,"copyout_retry_transport");
    response_header(third,q,OK,24,before_fault.revision+1);
    history_terminal(hist,3,OK,third);
    CHECK(memcmp(hist+80,stable_object,16)==0,"copyout_history_same_owner");
    CHECK(transact(control_fd,q,96,r)==0 && memcmp(r,third,128)==0,"exact_retry_receipt_bytes");
    struct usage after_retry=usage_read(control_fd,UINT64_C(20000000));
    CHECK(after_retry.revision==u.revision && after_retry.cumulative>=u.cumulative,
          "same_D_executed_twice");
    put64(q+80,UINT64_C(20000001));empty_response(control_fd,q,96,CONFLICT);
    put64(q+80,UINT64_C(20000000));put64(q+64,before_fault.revision+1);
    empty_response(control_fd,q,96,CONFLICT);
    record("G1D_COPYOUT_REPLAY sequence=3 errno=%d revision=%" PRIu64 " exact_bytes=true conflicts=2",
           EFAULT,u.revision);

    install_request(q,4,initial_revision,MAX_CAP_NS);
    CHECK(transact(control_fd,q,96,r)==0,"stale_revision_transport");
    response_header(r,q,CONFLICT,0,0);
    unsigned char stale[128];memcpy(stale,r,128);
    CHECK(transact(control_fd,q,96,r)==0 && memcmp(r,stale,128)==0,"stale_terminal_retry");
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,4,0,OK,hist);
    history_terminal(hist,4,CONFLICT,NULL);
    install_request(q,4,u.revision,MAX_CAP_NS);empty_response(control_fd,q,96,CONFLICT);
    CHECK(usage_read(control_fd,UINT64_C(20000000)).revision==u.revision,"stale_changed_revision");
    record("G1D_STALE_REVISION_TERMINAL sequence=4 saved_status=5");
    static_admission(5,u.revision);
    u=usage_read(control_fd,UINT64_C(20000000));
    u=install_ok(5,u,MAX_CAP_NS,r,1);
    install_request(q,6,u.revision,UINT64_C(60000000));
    empty_response(control_fd,q,96,DENIED);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,6,0,OK,hist);
    history_terminal(hist,6,DENIED,NULL);
    CHECK(usage_read(control_fd,MAX_CAP_NS).revision==u.revision,"ceiling_refusal_changed_revision");
    record("G1D_CEILING_REFUSAL_TERMINAL sequence=6 saved_status=2");
    fork_and_transfer();
    legacy_aliases();
    u=usage_read(control_fd,MAX_CAP_NS);

    u=install_ok(7,u,0,r,1);
    sleep_ms(220);
    struct usage zero_a=usage_read(control_fd,0);uint64_t count_a=heartbeat();
    sleep_ms(220);
    struct usage zero_b=usage_read(control_fd,0);uint64_t count_b=heartbeat();
    CHECK(zero_a.cumulative==zero_b.cumulative && count_a==count_b && count_a>0,
          "zero_cap_workload_still_runs");
    CHECK(zero_b.sample-zero_a.sample>=PERIOD_NS*2 && zero_b.revision==u.revision,
          "zero_cap_observation_interval");
    record("G1D_ZERO_CAP_STOPPED sample_a=%" PRIu64 " sample_b=%" PRIu64
           " total_a=%" PRIu64 " total_b=%" PRIu64 " heartbeat_a=%" PRIu64
           " heartbeat_b=%" PRIu64 " revision=%" PRIu64,
           zero_a.sample,zero_b.sample,zero_a.cumulative,zero_b.cumulative,
           count_a,count_b,zero_b.revision);
    struct message restored=recovery_command(REC_INSTALL,u.revision,0,OK);
    CHECK(get64(restored.response+56)==u.revision+1,"independent_restore_revision");
    sleep_ms(220);u=usage_read(control_fd,MAX_CAP_NS);
    CHECK(u.revision==get64(restored.response+56) && u.cumulative>zero_b.cumulative &&
          heartbeat()>count_b,"recovery_did_not_resume_workload");
    struct message recovery_history=recovery_command(REC_QUERY_SELF,1,0,OK);
    history_terminal(recovery_history.response,1,OK,restored.response);
    CHECK(memcmp(recovery_history.response+80,stable_object,16)==0,"recovery_same_real_owner");
    record("G1D_INDEPENDENT_RECOVERY resumed_total=%" PRIu64 " revision=%" PRIu64 " own_sequence=1",
           u.cumulative,u.revision);
    const uint64_t caps[]={1,999,1001};
    for(unsigned i=0;i<3;++i)u=install_ok(8+i,u,caps[i],r,1);
    u=install_ok(11,u,MAX_CAP_NS,r,1);
    record("G1D_SUBMICROSECOND_CAPS_EXACT cases=3");

    /* Fill the original fixed window. No clock/window reset, LRU eviction,
     * host-only counter or replacement delivery table can satisfy these reads. */
    for(uint64_t seq=12;seq<=WINDOW_CAPACITY;++seq)u=install_ok(seq,u,MAX_CAP_NS,r,0);
    install_request(q,1025,u.revision,MAX_CAP_NS);empty_response(control_fd,q,96,EXHAUSTED);
    CHECK(usage_read(control_fd,MAX_CAP_NS).revision==u.revision,"full_window_changed_revision");
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,1,0,OK,hist);
    history_terminal(hist,1,OK,first);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,3,0,OK,hist);
    history_terminal(hist,3,OK,third);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,1025,0,OK,hist);
    history_empty(hist,NOT_SEEN_STATE,1025);
    record("G1D_FULL_WINDOW capacity=1024 refused_sequence=1025 old_results=retained revision=%" PRIu64,
           u.revision);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,512,1,DENIED,hist);
    (void)recovery_command(REC_RETIRE_MANAGER,1025,0,OUT_OF_ORDER);
    struct message retired=recovery_command(REC_RETIRE_MANAGER,512,0,OK);
    CHECK(get64(retired.response+64)==512 && get64(retired.response+72)==1025,
          "independent_prefix_retirement");
    struct message retired_again=recovery_command(REC_RETIRE_MANAGER,512,0,OK);
    CHECK(memcmp(retired_again.response+64,retired.response+64,16)==0,"idempotent_retirement");
    u=usage_read(control_fd,MAX_CAP_NS);u=install_ok(1025,u,MAX_CAP_NS,r,1);
    struct saved_terminal saved;memcpy(saved.receipt,r,128);memcpy(saved.stable_object,stable_object,16);
    install_request(q,1,initial_revision,UINT64_C(25000000));
    empty_response(control_fd,q,96,RETIRED);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,1,0,OK,hist);
    history_empty(hist,RETIRED_STATE,1);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,3,0,OK,hist);
    history_empty(hist,RETIRED_STATE,3);
    history(control_fd,manager_history_slot,manager_history_gen,manager_space,1024,0,OK,hist);
    CHECK(get16(hist+64)==TERMINAL_STATE && get16(hist+66)==OK,"unretired_suffix_retained");
    CHECK(usage_read(control_fd,MAX_CAP_NS).revision==u.revision,"retired_D_executed");
    record("G1D_PREFIX_RETIRED through=512 next=1026 old_D=retired manager_ack=denied");
    write_file(IPC_DIR "/last-terminal",&saved,sizeof saved);

    char fd_text[24],boot_text[33],manager_text[33],recovery_text[33],command_text[24],wpid[24],rpid[24];
    CHECK(snprintf(fd_text,sizeof fd_text,"%d",control_fd)>0,"exec_fd_format");
    CHECK(snprintf(command_text,sizeof command_text,"%" PRIu64,command_id)>0,"exec_command_format");
    CHECK(snprintf(wpid,sizeof wpid,"%ld",(long)workload_pid)>0,"exec_workload_format");
    CHECK(snprintf(rpid,sizeof rpid,"%ld",(long)recovery_pid)>0,"exec_recovery_format");
    hex16(boot_id,boot_text);hex16(manager_space,manager_text);hex16(recovery_space,recovery_text);
    char *args[]={"/test/g1d-init","--post-exec",fd_text,boot_text,manager_text,recovery_text,
                  "1025",command_text,wpid,rpid,NULL};
    record("G1D_MANAGER_EXEC_BEGIN sequence=1025");
    execv(args[0],args);
    failure("manager_exec_returned",__LINE__);
}

int main(int argc,char **argv) {
    setvbuf(stdout,NULL,_IONBF,0);
    if(argc>1 && strcmp(argv[1],"--post-exec")==0)post_exec(argc,argv);
    CHECK(argc==1,"initial_argc");
    bootstrap();
    if(role==1)manager();
    else if(role==2)workload();
    else recovery();
    failure("initial_role_returned",__LINE__);
    return 1;
}
