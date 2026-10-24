// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* A finite socket timeout makes the old per-call blocking bug observable as
 * a measured EAGAIN, never as an accepted outer timeout or killed process. */
#define SOCKET_TIMEOUT_US 750000
#define IMMEDIATE_MAX_US 250000
#define WAKE_DELAY_US 50000
#define QUEUE_MAX_BYTES (8U * 1024U * 1024U)

static unsigned int checks, failures;
static const char *kind;

static uint64_t now_us(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
        exit(2);
    return (uint64_t)ts.tv_sec * 1000000 + (uint64_t)ts.tv_nsec / 1000;
}

static void record(const char *name, int passed, long result, int error,
                   uint64_t elapsed)
{
    checks++;
    failures += !passed;
    printf("{\"suite\":\"unix_dontwait\",\"socket\":\"%s\",\"case\":\"%s\","
           "\"passed\":%s,\"return\":%ld,\"errno\":%d,\"elapsed_us\":%llu}\n",
           kind, name, passed ? "true" : "false", result, error,
           (unsigned long long)elapsed);
}

static void require_setup(int ok, const char *what)
{
    if (ok)
        return;
    fprintf(stderr, "unix_dontwait setup: %s errno=%d\n", what, errno);
    exit(2);
}

static int would_block(int error)
{
    return error == EAGAIN || error == EWOULDBLOCK;
}

static void set_timeout(int fd)
{
    struct timeval value = { .tv_sec = 0, .tv_usec = SOCKET_TIMEOUT_US };
    require_setup(setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &value, sizeof(value)) == 0,
                  "receive timeout");
    require_setup(setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &value, sizeof(value)) == 0,
                  "send timeout");
}

static void verify_flags(const char *name, int original, int duplicate, int before)
{
    int first = fcntl(original, F_GETFL), second = fcntl(duplicate, F_GETFL);
    record(name, first == before && second == before && !(first & O_NONBLOCK),
           first, second, 0);
}

static void join_child(pid_t child, const char *name)
{
    int status = 0;
    pid_t result;
    do {
        result = waitpid(child, &status, 0);
    } while (result < 0 && errno == EINTR);
    record(name, result == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
           result, status, 0);
}

static size_t fill_queue(int sender, int original_flags)
{
    char payload[1024];
    memset(payload, 'q', sizeof(payload));
    require_setup(fcntl(sender, F_SETFL, original_flags | O_NONBLOCK) == 0,
                  "set nonblock for bounded fill");
    size_t total = 0;
    for (;;) {
        errno = 0;
        ssize_t result = send(sender, payload, sizeof(payload), MSG_NOSIGNAL);
        if (result < 0 && would_block(errno))
            break;
        require_setup(result > 0 && (size_t)result <= sizeof(payload), "fill send");
        total += (size_t)result;
        require_setup(total < QUEUE_MAX_BYTES, "finite queue bound");
    }
    require_setup(total != 0, "nonempty full queue");
    require_setup(fcntl(sender, F_SETFL, original_flags) == 0, "restore blocking mode");
    return total;
}

static void one_socket(int type, const char *name)
{
    int pair[2];
    kind = name;
    require_setup(socketpair(AF_UNIX, type, 0, pair) == 0, "socketpair");
    set_timeout(pair[0]);
    set_timeout(pair[1]);
    int duplicate = dup(pair[0]);
    require_setup(duplicate >= 0, "dup");
    int flags = fcntl(pair[0], F_GETFL);
    require_setup(flags >= 0 && !(flags & O_NONBLOCK), "initial blocking flags");
    char value = 0;
    errno = 0;
    uint64_t start = now_us();
    ssize_t result = recv(duplicate, &value, 1, MSG_DONTWAIT);
    int error = errno;
    uint64_t elapsed = now_us() - start;
    record("empty_recv_dontwait", result == -1 && would_block(error) &&
           elapsed < IMMEDIATE_MAX_US, result, error, elapsed);
    verify_flags("recv_preserves_shared_flags", pair[0], duplicate, flags);

    /* A per-call flag must not poison the following ordinary timeout. */
    errno = 0;
    start = now_us();
    result = recv(pair[0], &value, 1, 0);
    error = errno;
    elapsed = now_us() - start;
    record("ordinary_recv_timeout", result == -1 && would_block(error) &&
           elapsed >= SOCKET_TIMEOUT_US / 2 && elapsed < 2000000,
           result, error, elapsed);

    pid_t child = fork();
    require_setup(child >= 0, "receive wake fork");
    if (child == 0) {
        close(pair[0]);
        close(duplicate);
        usleep(WAKE_DELAY_US);
        _exit(send(pair[1], "r", 1, MSG_NOSIGNAL) == 1 ? 0 : 3);
    }
    errno = 0;
    start = now_us();
    result = recv(pair[0], &value, 1, 0);
    error = errno;
    elapsed = now_us() - start;
    record("ordinary_recv_wakeup", result == 1 && value == 'r' &&
           elapsed >= WAKE_DELAY_US / 5 && elapsed < SOCKET_TIMEOUT_US,
           result, error, elapsed);
    join_child(child, "recv_child_reaped");

    size_t queued = fill_queue(pair[0], flags);
    char next_payload[1024];
    memset(next_payload, 'w', sizeof(next_payload));
    errno = 0;
    start = now_us();
    result = send(duplicate, next_payload, sizeof(next_payload), MSG_DONTWAIT | MSG_NOSIGNAL);
    error = errno;
    elapsed = now_us() - start;
    record("full_send_dontwait", result == -1 && would_block(error) &&
           elapsed < IMMEDIATE_MAX_US, result, error, elapsed);
    verify_flags("send_preserves_shared_flags", pair[0], duplicate, flags);

    /* The same full queue must still support an ordinary blocked sender.
     * The child drains exactly the original bytes and validates their content;
     * it cannot accidentally consume the newly sent message. The send size
     * equals the fill size: a smaller Linux datagram may fit unused accounting
     * space even when the fill message no longer fits. */
    child = fork();
    require_setup(child >= 0, "send wake fork");
    if (child == 0) {
        close(pair[0]);
        close(duplicate);
        usleep(WAKE_DELAY_US);
        char payload[1024];
        size_t left = queued;
        while (left != 0) {
            size_t want = left < sizeof(payload) ? left : sizeof(payload);
            ssize_t count = recv(pair[1], payload, want, 0);
            if (count <= 0 || (size_t)count > want)
                _exit(4);
            for (ssize_t i = 0; i < count; i++)
                if (payload[i] != 'q')
                    _exit(5);
            left -= (size_t)count;
        }
        _exit(0);
    }
    errno = 0;
    start = now_us();
    result = send(pair[0], next_payload, sizeof(next_payload), MSG_NOSIGNAL);
    error = errno;
    elapsed = now_us() - start;
    record("ordinary_send_wakeup", result == (ssize_t)sizeof(next_payload) && elapsed >= WAKE_DELAY_US / 5 &&
           elapsed < SOCKET_TIMEOUT_US, result, error, elapsed);
    join_child(child, "send_child_reaped_payload_preserved");
    errno = 0;
    char received[1024];
    result = recv(pair[1], received, sizeof(received), 0);
    error = errno;
    record("wakeup_payload_readback", result == (ssize_t)sizeof(received) &&
           memcmp(received, next_payload, sizeof(received)) == 0, result, error, 0);
    verify_flags("final_shared_flags", pair[0], duplicate, flags);
    close(duplicate);
    close(pair[0]);
    close(pair[1]);
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    /* An alarm is only a failed/incomplete probe, never the defect oracle. */
    alarm(20);
    one_socket(SOCK_STREAM, "stream");
    one_socket(SOCK_SEQPACKET, "seqpacket");
    one_socket(SOCK_DGRAM, "dgram");
    alarm(0);
    printf("{\"suite\":\"unix_dontwait\",\"summary\":true,\"checks\":%u,"
           "\"failures\":%u}\n", checks, failures);
    return failures ? 1 : 0;
}
