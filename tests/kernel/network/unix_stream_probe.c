#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <sched.h>

/* Directed syscall probe. It never claims native execution from a host run. */
static const char *run_nonce;
static const char *case_name = "input";
static const char *suite_selection = "all";
static unsigned sequence;
static unsigned completed_cases;

static void emit(const char *event, const char *format, ...) {
    char line[768];
    int count = snprintf(line, sizeof line,
        "UNIX_STREAM_V1 nonce=%s event=%s case=%s seq=%u ",
        run_nonce, event, case_name, ++sequence);
    if (count < 0 || (size_t)count >= sizeof line) _exit(125);
    va_list args;
    va_start(args, format);
    int more = vsnprintf(line + count, sizeof line - (size_t)count, format, args);
    va_end(args);
    if (more < 0 || (size_t)more >= sizeof line - (size_t)count - 1) _exit(125);
    size_t size = (size_t)count + (size_t)more;
    line[size++] = '\n';
    size_t done = 0;
    while (done < size) {
        ssize_t result = write(STDOUT_FILENO, line + done, size - done);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) _exit(125);
        done += (size_t)result;
    }
}

static _Noreturn void finish_failure(void) {
    const char *failed_case = case_name;
    case_name = "suite";
    emit("suite_fail", "cases_passed=%u selection=%s failed_case=%s exit_code=1",
        completed_cases, suite_selection, failed_case);
    _exit(1);
}

static _Noreturn void fail(const char *operation, long expected, long observed, int error) {
    emit("case_fail", "op=%s expected=%ld observed=%ld errno=%d", operation, expected, observed, error);
    finish_failure();
}

#define EQUAL(expression, expected, operation) do { \
    errno = 0; long actual_value = (long)(expression); int actual_errno = errno; \
    if (actual_value != (long)(expected)) fail(operation, (long)(expected), actual_value, actual_errno); \
} while (0)
#define REQUIRE(condition, operation) do { if (!(condition)) fail(operation, 1, 0, 0); } while (0)

static void timeout_handler(int signal_number) {
    (void)signal_number;
    /* Missing completion / exit 124 is always failure, never a semantic negative. */
    _exit(124);
}

static void payload(unsigned char *bytes, size_t count, unsigned salt) {
    for (size_t index = 0; index < count; ++index)
        bytes[index] = (unsigned char)((unsigned char)run_nonce[index % 32] ^ (index * 17u + salt));
}

static void pair(int type, int sockets[2]) {
    EQUAL(socketpair(AF_UNIX, type | SOCK_CLOEXEC, 0, sockets), 0, "socketpair");
}

static void close_pair(int sockets[2]) {
    EQUAL(close(sockets[0]), 0, "close_sender");
    EQUAL(close(sockets[1]), 0, "close_receiver");
}

static void written(int fd, const void *bytes, size_t size) {
    EQUAL(send(fd, bytes, size, MSG_NOSIGNAL), size, "send_payload");
    emit("checkpoint", "name=write_done bytes=%zu", size);
}

static void shut(int fd) {
    EQUAL(shutdown(fd, SHUT_WR), 0, "shutdown_write");
    emit("checkpoint", "name=shutdown_done result=0");
}

static void eof(int fd) {
    unsigned char byte;
    EQUAL(recv(fd, &byte, 1, MSG_DONTWAIT), 0, "recv_eof");
}

static void receive_payload(int fd, const unsigned char *expected, size_t size, size_t chunk) {
    unsigned char observed[256];
    size_t done = 0;
    REQUIRE(chunk > 0 && chunk <= sizeof observed, "receive_chunk_bound");
    emit("checkpoint", "name=before_recv expected_bytes=%zu chunk=%zu", size, chunk);
    while (done < size) {
        size_t wanted = size - done < chunk ? size - done : chunk;
        errno = 0;
        ssize_t got = recv(fd, observed, wanted, MSG_DONTWAIT);
        int error = errno;
        if (got <= 0 || (size_t)got > wanted) fail("recv_payload", (long)wanted, got, error);
        REQUIRE(memcmp(observed, expected + done, (size_t)got) == 0, "payload_bytes");
        done += (size_t)got;
    }
}

union control_buffer {
    struct cmsghdr alignment;
    unsigned char bytes[256];
};

struct received {
    unsigned char bytes[256];
    union control_buffer controls;
    struct iovec iov;
    struct msghdr message;
    ssize_t length;
    int error;
};

static void receive_message(int fd, struct received *result, size_t capacity, int flags) {
    REQUIRE(capacity <= sizeof result->bytes, "receive_capacity");
    memset(result, 0, sizeof *result);
    result->iov.iov_base = result->bytes;
    result->iov.iov_len = capacity;
    result->message.msg_iov = &result->iov;
    result->message.msg_iovlen = 1;
    result->message.msg_control = result->controls.bytes;
    result->message.msg_controllen = sizeof result->controls.bytes;
    errno = 0;
    result->length = recvmsg(fd, &result->message, flags | MSG_DONTWAIT);
    result->error = errno;
}

static struct cmsghdr *single_control(struct received *result, int type, size_t size) {
    REQUIRE((result->message.msg_flags & MSG_CTRUNC) == 0, "control_not_truncated");
    REQUIRE(result->message.msg_controllen <= sizeof result->controls.bytes, "control_length_bound");
    struct cmsghdr *control = CMSG_FIRSTHDR(&result->message);
    REQUIRE(control != NULL, "control_present");
    REQUIRE(control->cmsg_len == CMSG_LEN(size), "control_exact_size");
    REQUIRE(control->cmsg_level == SOL_SOCKET && control->cmsg_type == type, "control_type");
    REQUIRE(CMSG_NXTHDR(&result->message, control) == NULL, "single_control");
    return control;
}

static void credentials(int fd, int value) {
    EQUAL(setsockopt(fd, SOL_SOCKET, SO_PASSCRED, &value, sizeof value), 0, "setsockopt_passcred");
    int observed = -1;
    socklen_t length = sizeof observed;
    EQUAL(getsockopt(fd, SOL_SOCKET, SO_PASSCRED, &observed, &length), 0, "getsockopt_passcred");
    REQUIRE(length == sizeof observed && observed == value, "passcred_readback");
}

static void send_credentials(int fd, const unsigned char *bytes, size_t size) {
    union control_buffer buffer = {0};
    struct iovec iov = {.iov_base = (void *)bytes, .iov_len = size};
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
        .msg_control = buffer.bytes, .msg_controllen = CMSG_SPACE(sizeof(struct ucred))};
    struct cmsghdr *control = CMSG_FIRSTHDR(&message);
    control->cmsg_level = SOL_SOCKET;
    control->cmsg_type = SCM_CREDENTIALS;
    control->cmsg_len = CMSG_LEN(sizeof(struct ucred));
    struct ucred cred = {.pid = getpid(), .uid = getuid(), .gid = getgid()};
    memcpy(CMSG_DATA(control), &cred, sizeof cred);
    EQUAL(sendmsg(fd, &message, MSG_NOSIGNAL), size, "send_credentials");
    emit("checkpoint", "name=write_done bytes=%zu credentials=1 rights=0", size);
}

static void open_empty(void) {
    int sockets[2];
    pair(SOCK_STREAM, sockets);
    unsigned char byte;
    emit("checkpoint", "name=before_recv expected_bytes=0 open=1");
    errno = 0;
    ssize_t observed = recv(sockets[1], &byte, 1, MSG_DONTWAIT);
    int error = errno;
    if (observed != -1 || error != EAGAIN) fail("open_empty_eagain", -1, observed, error);
    shut(sockets[0]);
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "open_errno=%d closed_bytes=0", EAGAIN);
}

static void queued_shutdown(void) {
    int sockets[2];
    unsigned char bytes[96];
    payload(bytes, sizeof bytes, 1);
    pair(SOCK_STREAM, sockets);
    written(sockets[0], bytes, sizeof bytes);
    shut(sockets[0]);
    receive_payload(sockets[1], bytes, sizeof bytes, sizeof bytes);
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "bytes=96 eof=1");
}

static void partial_peek(void) {
    int sockets[2];
    unsigned char bytes[96], prefix[7];
    payload(bytes, sizeof bytes, 2);
    pair(SOCK_STREAM, sockets);
    written(sockets[0], bytes, sizeof bytes);
    shut(sockets[0]);
    emit("checkpoint", "name=before_recv expected_bytes=7 peek=1");
    for (unsigned index = 0; index < 2; ++index) {
        EQUAL(recv(sockets[1], prefix, sizeof prefix, MSG_PEEK | MSG_DONTWAIT), sizeof prefix, "peek_prefix");
        REQUIRE(memcmp(prefix, bytes, sizeof prefix) == 0, "peek_bytes");
    }
    receive_payload(sockets[1], bytes, sizeof bytes, 11);
    EQUAL(recv(sockets[1], prefix, sizeof prefix, MSG_PEEK | MSG_DONTWAIT), 0, "peek_eof");
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "bytes=96 peek_calls=2 peek_bytes=7 chunk=11 eof=1");
}

static void credential_only(void) {
    int sockets[2];
    unsigned char bytes[13];
    payload(bytes, sizeof bytes, 3);
    pair(SOCK_STREAM, sockets);
    credentials(sockets[0], 1);
    credentials(sockets[1], 0);
    send_credentials(sockets[0], bytes, sizeof bytes);
    shut(sockets[0]);
    emit("checkpoint", "name=before_recv expected_bytes=13 sender_passcred=1 receiver_passcred=0");
    struct received result;
    receive_message(sockets[1], &result, sizeof result.bytes, 0);
    if (result.length != 13) fail("recv_credential_only", 13, result.length, result.error);
    REQUIRE(memcmp(result.bytes, bytes, sizeof bytes) == 0, "credential_only_bytes");
    REQUIRE(result.message.msg_controllen == 0 && (result.message.msg_flags & MSG_CTRUNC) == 0,
        "credential_only_no_control");
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "bytes=13 delivered_controls=0 eof=1");
}

static void credentials_preserved(void) {
    int sockets[2];
    unsigned char bytes[9];
    payload(bytes, sizeof bytes, 4);
    pair(SOCK_STREAM, sockets);
    credentials(sockets[1], 1);
    send_credentials(sockets[0], bytes, sizeof bytes);
    shut(sockets[0]);
    emit("checkpoint", "name=before_recv expected_bytes=9 receiver_passcred=1");
    struct received result;
    receive_message(sockets[1], &result, sizeof result.bytes, 0);
    if (result.length != 9) fail("recv_credentials", 9, result.length, result.error);
    REQUIRE(memcmp(result.bytes, bytes, sizeof bytes) == 0, "credential_bytes");
    struct cmsghdr *control = single_control(&result, SCM_CREDENTIALS, sizeof(struct ucred));
    struct ucred actual;
    memcpy(&actual, CMSG_DATA(control), sizeof actual);
    REQUIRE(actual.pid == getpid() && actual.uid == getuid() && actual.gid == getgid(), "credential_identity");
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "bytes=9 credentials=1 pid=%ld uid=%ld gid=%ld eof=1",
        (long)actual.pid, (long)actual.uid, (long)actual.gid);
}

static void rights_preserved(void) {
    int sockets[2], pipe_fds[2];
    unsigned char bytes[3], trailing[8];
    payload(bytes, sizeof bytes, 5);
    payload(trailing, sizeof trailing, 6);
    pair(SOCK_STREAM, sockets);
    credentials(sockets[1], 0);
    EQUAL(pipe2(pipe_fds, O_CLOEXEC), 0, "rights_pipe");
    EQUAL(write(pipe_fds[1], run_nonce, 1), 1, "rights_pipe_write");
    EQUAL(close(pipe_fds[1]), 0, "rights_pipe_close_writer");
    union control_buffer buffer = {0};
    struct iovec iov = {.iov_base = bytes, .iov_len = sizeof bytes};
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
        .msg_control = buffer.bytes, .msg_controllen = CMSG_SPACE(sizeof(int))};
    struct cmsghdr *control = CMSG_FIRSTHDR(&message);
    control->cmsg_level = SOL_SOCKET;
    control->cmsg_type = SCM_RIGHTS;
    control->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(control), &pipe_fds[0], sizeof(int));
    EQUAL(sendmsg(sockets[0], &message, MSG_NOSIGNAL), sizeof bytes, "send_rights");
    emit("checkpoint", "name=write_done bytes=3 credentials=0 rights=1");
    EQUAL(close(pipe_fds[0]), 0, "close_original_right");
    written(sockets[0], trailing, sizeof trailing);
    shut(sockets[0]);
    emit("checkpoint", "name=before_recv expected_bytes=3 rights=1 trailing_bytes=8");
    struct received result;
    for (unsigned peek = 1;; --peek) {
        receive_message(sockets[1], &result, sizeof result.bytes, MSG_CMSG_CLOEXEC | (peek ? MSG_PEEK : 0));
        if (result.length != 3) fail("recv_rights_boundary", 3, result.length, result.error);
        REQUIRE(memcmp(result.bytes, bytes, sizeof bytes) == 0, "rights_bytes");
        control = single_control(&result, SCM_RIGHTS, sizeof(int));
        int received_fd;
        memcpy(&received_fd, CMSG_DATA(control), sizeof received_fd);
        REQUIRE(received_fd >= 0, "received_fd_nonnegative");
        EQUAL(fcntl(received_fd, F_GETFD), FD_CLOEXEC, "rights_cloexec");
        if (!peek) {
            unsigned char actual;
            EQUAL(read(received_fd, &actual, 1), 1, "rights_pipe_read");
            REQUIRE(actual == (unsigned char)run_nonce[0], "rights_object_identity");
            EQUAL(read(received_fd, &actual, 1), 0, "rights_pipe_eof");
        }
        EQUAL(close(received_fd), 0, "close_received_right");
        if (!peek) break;
    }
    receive_payload(sockets[1], trailing, sizeof trailing, sizeof trailing);
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "bytes=3 rights=1 peek_rights=1 cloexec=1 trailing_bytes=8 object_read=1 eof=1");
}

static void seqpacket_boundaries(void) {
    int sockets[2];
    unsigned char first[7], second[11];
    payload(first, sizeof first, 7);
    payload(second, sizeof second, 8);
    pair(SOCK_SEQPACKET, sockets);
    written(sockets[0], first, 0);
    written(sockets[0], first, sizeof first);
    written(sockets[0], second, sizeof second);
    shut(sockets[0]);
    emit("checkpoint", "name=before_recv zero_packet=1 first_bytes=7 second_bytes=11");
    struct received result;
    receive_message(sockets[1], &result, sizeof result.bytes, MSG_PEEK);
    if (result.length != 0) fail("peek_zero_packet", 0, result.length, result.error);
    receive_message(sockets[1], &result, sizeof result.bytes, 0);
    if (result.length != 0) fail("recv_zero_packet", 0, result.length, result.error);
    receive_message(sockets[1], &result, sizeof result.bytes, MSG_PEEK);
    if (result.length != 7) fail("peek_packet", 7, result.length, result.error);
    REQUIRE(memcmp(result.bytes, first, sizeof first) == 0, "peek_packet_bytes");
    receive_message(sockets[1], &result, sizeof result.bytes, 0);
    if (result.length != 7) fail("recv_first_packet", 7, result.length, result.error);
    REQUIRE(memcmp(result.bytes, first, sizeof first) == 0, "first_packet_bytes");
    receive_message(sockets[1], &result, sizeof result.bytes, 0);
    if (result.length != 11) fail("recv_second_packet", 11, result.length, result.error);
    REQUIRE(memcmp(result.bytes, second, sizeof second) == 0, "second_packet_bytes");
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "zero_packet=1 peek_packets=2 first_bytes=7 second_bytes=11 eof=1");
}

static void seqpacket_truncation(void) {
    int sockets[2];
    unsigned char first[13], second[5];
    payload(first, sizeof first, 9);
    payload(second, sizeof second, 10);
    pair(SOCK_SEQPACKET, sockets);
    written(sockets[0], first, sizeof first);
    written(sockets[0], first, sizeof first);
    written(sockets[0], second, sizeof second);
    shut(sockets[0]);
    emit("checkpoint", "name=before_recv packet_bytes=13 buffer_bytes=4 packets=3");
    struct received result;
    receive_message(sockets[1], &result, 4, 0);
    if (result.length != 4) fail("packet_truncated_copy", 4, result.length, result.error);
    REQUIRE((result.message.msg_flags & MSG_TRUNC) != 0 && memcmp(result.bytes, first, 4) == 0,
        "packet_truncated_flag");
    receive_message(sockets[1], &result, 4, MSG_TRUNC);
    if (result.length != 13) fail("packet_trunc_returns_message_size", 13, result.length, result.error);
    REQUIRE((result.message.msg_flags & MSG_TRUNC) != 0 && memcmp(result.bytes, first, 4) == 0,
        "packet_trunc_input_flag");
    receive_message(sockets[1], &result, sizeof result.bytes, 0);
    if (result.length != 5) fail("packet_after_truncated", 5, result.length, result.error);
    REQUIRE(memcmp(result.bytes, second, sizeof second) == 0 && (result.message.msg_flags & MSG_TRUNC) == 0,
        "packet_after_truncated_bytes");
    eof(sockets[1]);
    close_pair(sockets);
    emit("case_pass", "packet_bytes=13 copied_bytes=4 trunc_return=13 next_packet_bytes=5 eof=1");
}

static void shutdown_race(void) {
    unsigned char bytes[96], actual[96];
    payload(bytes, sizeof bytes, 11);
    for (unsigned iteration = 0; iteration < 64; ++iteration) {
        int sockets[2], witness[2], start[2];
        pair(SOCK_STREAM, sockets);
        EQUAL(pipe2(witness, O_CLOEXEC), 0, "race_witness_pipe");
        EQUAL(pipe2(start, O_CLOEXEC), 0, "race_start_pipe");
        pid_t child = fork();
        if (child < 0) fail("race_fork", 1, child, errno);
        if (child == 0) {
            close(sockets[1]); close(witness[0]); close(start[1]);
            unsigned char token = 0;
            if (read(start[0], &token, 1) != 1 || token != 'S') _exit(126);
            close(start[0]);
            struct timespec delay = {.tv_sec = 0, .tv_nsec = 1000000};
            int result[6] = {-1, 0, -1, 0, -1, 0};
            errno = 0;
            result[4] = nanosleep(&delay, NULL);
            result[5] = errno;
            errno = 0;
            result[0] = (int)send(sockets[0], bytes, sizeof bytes, MSG_NOSIGNAL);
            result[1] = errno;
            errno = 0;
            result[2] = shutdown(sockets[0], SHUT_WR);
            result[3] = errno;
            if (write(witness[1], result, sizeof result) != (ssize_t)sizeof result) _exit(126);
            _exit(result[0] == 96 && result[2] == 0 && result[4] == 0 ? 0 : 127);
        }
        EQUAL(close(sockets[0]), 0, "race_close_sender");
        EQUAL(close(witness[1]), 0, "race_close_witness_sender");
        EQUAL(close(start[0]), 0, "race_close_start_receiver");
        emit("checkpoint", "name=before_recv iteration=%u expected_bytes=96 writer_delay_us=1000", iteration);
        EQUAL(write(start[1], "S", 1), 1, "race_start_writer");
        EQUAL(close(start[1]), 0, "race_close_start_sender");
        size_t done = 0;
        int premature = 0;
        long first_non_eagain = -2;
        long read_error_value = 0;
        int read_error = 0;
        unsigned attempts = 0;
        while (done < sizeof bytes && ++attempts <= 100000) {
            errno = 0;
            ssize_t got = recv(sockets[1], actual + done, sizeof actual - done, MSG_DONTWAIT);
            int error = errno;
            if (got < 0 && error == EAGAIN) { sched_yield(); continue; }
            if (first_non_eagain == -2) first_non_eagain = got;
            if (got == 0) { premature = 1; break; }
            if (got < 0 || (size_t)got > sizeof actual - done) {
                read_error_value = got;
                read_error = error;
                break;
            }
            done += (size_t)got;
        }
        int result[6] = {-1, 0, -1, 0, -1, 0}, status = -1;
        errno = 0;
        ssize_t witness_length = read(witness[0], result, sizeof result);
        int witness_error = errno;
        EQUAL(waitpid(child, &status, 0), child, "race_waitpid");
        if (witness_length != (ssize_t)sizeof result)
            fail("race_writer_witness", sizeof result, witness_length, witness_error);
        int child_exit = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
        emit("checkpoint", "name=writer_reaped iteration=%u writer_bytes=%d writer_errno=%d shutdown_result=%d shutdown_errno=%d delay_result=%d delay_errno=%d child_exit=%d observed_bytes=%zu first_non_eagain=%ld eof_read=%d",
            iteration, result[0], result[1], result[2], result[3], result[4], result[5], child_exit,
            done, first_non_eagain, premature ? 0 : -1);
        REQUIRE(child_exit == 0 && result[0] == 96 && result[1] == 0 && result[2] == 0 &&
            result[3] == 0 && result[4] == 0 && result[5] == 0,
            "race_write_shutdown_succeeded");
        REQUIRE(attempts <= 100000, "race_attempt_bound");
        if (read_error_value != 0 || read_error != 0)
            fail("race_recv", 1, read_error_value, read_error);
        if (premature) {
            int queued = -1;
            EQUAL(ioctl(sockets[1], FIONREAD, &queued), 0, "race_fionread");
            emit("case_fail", "op=race_eof expected=96 observed=%zu errno=0 queued_bytes=%d iteration=%u writer_bytes=96 shutdown_result=0 child_exit=0 first_non_eagain=%ld eof_read=0",
                done, queued, iteration, first_non_eagain);
            finish_failure();
        }
        REQUIRE(memcmp(actual, bytes, sizeof bytes) == 0, "race_payload_bytes");
        eof(sockets[1]);
        EQUAL(close(sockets[1]), 0, "race_close_receiver");
        EQUAL(close(witness[0]), 0, "race_close_witness");
    }
    emit("case_pass", "stress_iterations=64 bytes_per_iteration=96 eof=1 deterministic_race_reproduction=0");
}

struct test_case { const char *name; void (*run)(void); };
static const struct test_case cases[] = {
    {"open_empty", open_empty},
    {"queued_shutdown", queued_shutdown},
    {"partial_peek", partial_peek},
    {"credential_only", credential_only},
    {"credentials_preserved", credentials_preserved},
    {"rights_preserved", rights_preserved},
    {"seqpacket_boundaries", seqpacket_boundaries},
    {"seqpacket_truncation", seqpacket_truncation},
    {"shutdown_race", shutdown_race},
};

int main(int argc, char **argv) {
    if (argc < 2 || argc > 3 || strlen(argv[1]) != 32) return 64;
    for (unsigned index = 0; index < 32; ++index)
        if (!((argv[1][index] >= '0' && argv[1][index] <= '9') ||
              (argv[1][index] >= 'a' && argv[1][index] <= 'f'))) return 64;
    run_nonce = argv[1];
    if (argc == 3) {
        int found = 0;
        for (size_t index = 0; index < sizeof cases / sizeof cases[0]; ++index)
            if (strcmp(argv[2], cases[index].name) == 0) found = 1;
        if (!found) return 64;
        suite_selection = argv[2];
    }
    struct sigaction action = {.sa_handler = timeout_handler};
    EQUAL(sigemptyset(&action.sa_mask), 0, "sigemptyset");
    EQUAL(sigaction(SIGALRM, &action, NULL), 0, "sigaction");
    for (size_t index = 0; index < sizeof cases / sizeof cases[0]; ++index) {
        if (argc == 3 ? strcmp(argv[2], cases[index].name) != 0 : strcmp(cases[index].name, "shutdown_race") == 0)
            continue;
        case_name = cases[index].name;
        emit("case_begin", "pid=%ld", (long)getpid());
        alarm(20);
        cases[index].run();
        alarm(0);
        ++completed_cases;
    }
    case_name = "suite";
    emit("suite_pass", "cases=%u selection=%s", completed_cases, suite_selection);
    return 0;
}
