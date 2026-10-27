// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum api { SEND, SENDTO, SENDMSG, SENDMMSG, WRITE, WRITEV, API_COUNT };
enum mode { DEFAULT, HANDLER, NOSIGNAL, PER_CALL, SEQPACKET, HEALTHY, ZERO_DEFAULT, ZERO_NOSIGNAL };
static const char *api_names[] = {"send", "sendto", "sendmsg", "sendmmsg", "write", "writev"};
static const char *mode_names[] = {"default", "handler", "nosignal", "per_call", "seqpacket", "healthy", "zero_default", "zero_nosignal"};
_Static_assert(ATOMIC_INT_LOCK_FREE == 2, "signal observation must be lock-free");
static _Atomic unsigned caught;
static unsigned failures;
static size_t observed_capacity;

struct observation { long rc, error, signals, rc2, error2, signals2, setup; };
static void handler(int sig) { if (sig == SIGPIPE) atomic_fetch_add_explicit(&caught, 1, memory_order_relaxed); }
static void check(const char *name, int passed) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, passed ? "true" : "false");
    if (!passed) ++failures;
}
static int transfer(int fd, void *buffer, size_t length, int write_side) {
    size_t done = 0;
    while (done < length) {
        ssize_t n = write_side ? write(fd, (char *)buffer + done, length - done)
                               : read(fd, (char *)buffer + done, length - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        done += (size_t)n;
    }
    return 0;
}
static ssize_t transmit(enum api api, int fd, int flags, size_t length) {
    char payload[4] = {'U', 'N', 'I', 'X'};
    struct iovec vector = {.iov_base = payload, .iov_len = length};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1};
    struct mmsghdr multi = {.msg_hdr = message};
    switch (api) {
    case SEND: return send(fd, payload, length, flags);
    case SENDTO: return sendto(fd, payload, length, flags, NULL, 0);
    case SENDMSG: return sendmsg(fd, &message, flags);
    case SENDMMSG: {
        int n = sendmmsg(fd, &multi, 1, flags);
        return n == 1 ? (ssize_t)multi.msg_len : n;
    }
    case WRITE: return write(fd, payload, length);
    case WRITEV: return writev(fd, &vector, 1);
    default: return -2;
    }
}
static void observe_child(enum api api, enum mode mode, int witness) {
    struct observation o = {.rc = -2, .rc2 = -2};
    struct sigaction action = {.sa_handler = (mode == HANDLER || mode == PER_CALL) ? handler : SIG_DFL};
    sigemptyset(&action.sa_mask);
    int fds[2];
    if (sigaction(SIGPIPE, &action, NULL) ||
        socketpair(AF_UNIX, mode == SEQPACKET ? SOCK_SEQPACKET : SOCK_STREAM, 0, fds)) goto report;
    if (mode != HEALTHY && shutdown(fds[0], SHUT_WR)) goto report_close;
    o.setup = 1;
    int flags = (mode == NOSIGNAL || mode == PER_CALL || mode == ZERO_NOSIGNAL ||
                 (mode == HEALTHY && api <= SENDMMSG)) ? MSG_NOSIGNAL : 0;
    size_t length = mode == ZERO_DEFAULT || mode == ZERO_NOSIGNAL ? 0 : 4;
    errno = 0;
    o.rc = transmit(api, fds[0], flags, length); o.error = errno; o.signals = caught;
    if (mode == PER_CALL) {
        errno = 0;
        o.rc2 = transmit(api, fds[0], 0, length); o.error2 = errno; o.signals2 = caught;
    }
    if (mode == HEALTHY) {
        char payload[4] = {0};
        if (o.rc != 4 || transfer(fds[1], payload, 4, 0) || memcmp(payload, "UNIX", 4)) o.setup = 0;
    }
report_close:
    close(fds[0]); close(fds[1]);
report:
    if (transfer(witness, &o, sizeof o, 1)) _exit(126);
    _exit(o.setup ? 0 : 125);
}
static void run_case(enum api api, enum mode mode) {
    char name[80];
    snprintf(name, sizeof name, "%s.%s", mode_names[mode], api_names[api]);
    int witness[2], status = -1;
    if (pipe2(witness, O_CLOEXEC)) { check(name, 0); return; }
    pid_t child = fork();
    if (child == 0) { close(witness[0]); observe_child(api, mode, witness[1]); }
    close(witness[1]);
    struct observation o = {.rc = -2, .rc2 = -2};
    int received = transfer(witness[0], &o, sizeof o, 0) == 0;
    close(witness[0]);
    int waited = child > 0 && waitpid(child, &status, 0) == child;
    int signal = waited && WIFSIGNALED(status) ? WTERMSIG(status) : 0;
    int exit = waited && WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    int passed;
    if (mode == DEFAULT || mode == ZERO_DEFAULT) passed = signal == SIGPIPE && !received;
    else {
        passed = waited && exit == 0 && received && o.setup;
        if (mode == HEALTHY) passed = passed && o.rc == 4 && o.signals == 0;
        else passed = passed && o.rc == -1 && o.error == EPIPE && o.signals == (mode == HANDLER ? 1 : 0);
        if (mode == PER_CALL) passed = passed && o.rc2 == -1 && o.error2 == EPIPE && o.signals2 == 1;
    }
    printf("{\"observation\":\"%s\",\"received\":%d,\"child_signal\":%d,\"child_exit\":%d,"
           "\"rc\":%ld,\"errno\":%ld,\"signals\":%ld,\"rc2\":%ld,\"errno2\":%ld,\"signals2\":%ld,\"setup\":%ld}\n",
           name, received, signal, exit, o.rc, o.error, o.signals, o.rc2, o.error2, o.signals2, o.setup);
    check(name, passed);
}
static void nonblocking_partial(void) {
    int fds[2];
    int setup = socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK, 0, fds) == 0;
    struct sigaction action = {.sa_handler = handler}, old;
    sigemptyset(&action.sa_mask);
    setup = setup && sigaction(SIGPIPE, &action, &old) == 0;
    if (!setup) {
        check("nonblock.backpressure", 0); check("nonblock.partial", 0); check("nonblock.epipe", 0);
        return;
    }
    caught = 0;
    char bytes[8192]; memset(bytes, 'P', sizeof bytes);
    size_t filled = 0; ssize_t rc = 0; int error = 0;
    for (unsigned i = 0; i < 512; ++i) {
        errno = 0; rc = send(fds[0], bytes, sizeof bytes, MSG_NOSIGNAL); error = errno;
        if (rc < 0) break;
        if (!rc) break;
        filled += (size_t)rc;
    }
    printf("{\"observation\":\"nonblock.backpressure\",\"rc\":%ld,\"errno\":%d,\"filled\":%zu,\"signals\":%d}\n",
           (long)rc, error, filled, (int)caught);
    check("nonblock.backpressure", rc == -1 && error == EAGAIN && filled > 8192 && caught == 0);
    observed_capacity = filled;
    size_t drained = 0, target = filled / 2;
    while (drained < target) {
        size_t wanted = target - drained < sizeof bytes ? target - drained : sizeof bytes;
        ssize_t n = recv(fds[1], bytes, wanted, 0);
        if (n <= 0) break;
        drained += (size_t)n;
    }
    char *large = malloc(filled ? filled : 1);
    if (large) memset(large, 'Q', filled);
    errno = 0; rc = large ? send(fds[0], large, filled, MSG_NOSIGNAL) : -2; error = errno;
    printf("{\"observation\":\"nonblock.partial\",\"rc\":%ld,\"errno\":%d,\"drained\":%ld,\"signals\":%d}\n",
           (long)rc, error, (long)drained, (int)caught);
    check("nonblock.partial", drained == target && target > 0 && rc > 0 && (size_t)rc < filled && caught == 0);
    free(large);
    int shut = shutdown(fds[0], SHUT_WR);
    errno = 0; rc = send(fds[0], bytes, 1, 0); error = errno;
    printf("{\"observation\":\"nonblock.epipe\",\"rc\":%ld,\"errno\":%d,\"shutdown\":%d,\"signals\":%d}\n",
           (long)rc, error, shut, (int)caught);
    check("nonblock.epipe", shut == 0 && rc == -1 && error == EPIPE && caught == 1);
    close(fds[0]); close(fds[1]); sigaction(SIGPIPE, &old, NULL);
}

struct drain_state { int fd; size_t length, received; int shutdown_result; };
static void *drain_then_shutdown(void *argument) {
    struct drain_state *state = argument;
    struct timespec delay = {.tv_sec = 0, .tv_nsec = 20000000};
    while (nanosleep(&delay, &delay) && errno == EINTR) {}
    char bytes[4096];
    while (state->received < state->length) {
        size_t wanted = state->length - state->received;
        if (wanted > sizeof bytes) wanted = sizeof bytes;
        ssize_t n = read(state->fd, bytes, wanted);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        state->received += (size_t)n;
    }
    state->shutdown_result = shutdown(state->fd, SHUT_RD);
    return NULL;
}
static void writev_boundaries(void) {
    struct sigaction action = {.sa_handler = handler}, old;
    sigemptyset(&action.sa_mask);
    int setup = sigaction(SIGPIPE, &action, &old) == 0;
    unsigned partials = 0, completed = 0, positive_signals = 0;
    size_t capacity = observed_capacity;
    char *payload = capacity <= 4 * 1024 * 1024 ? malloc(capacity ? capacity : 1) : NULL;
    if (payload) memset(payload, 'V', capacity);
    for (unsigned attempt = 0; setup && payload && capacity > 0 && attempt < 8; ++attempt) {
        int fds[2]; pthread_t reader;
        if (socketpair(AF_UNIX, SOCK_STREAM, 0, fds)) break;
        struct timeval deadline = {.tv_sec = 2};
        if (setsockopt(fds[1], SOL_SOCKET, SO_RCVTIMEO, &deadline, sizeof deadline)) {
            close(fds[0]); close(fds[1]); break;
        }
        struct drain_state state = {.fd = fds[1], .length = capacity, .shutdown_result = -1};
        if (pthread_create(&reader, NULL, drain_then_shutdown, &state)) { close(fds[0]); close(fds[1]); break; }
        struct iovec vectors[2] = {{.iov_base = payload, .iov_len = capacity},
                                  {.iov_base = payload, .iov_len = capacity}};
        caught = 0;
        ssize_t rc = writev(fds[0], vectors, 2);
        int joined = pthread_join(reader, NULL) == 0;
        if (rc > 0 && caught) ++positive_signals;
        if (joined && state.received == capacity && state.shutdown_result == 0 && rc > 0 && (size_t)rc <= 2 * capacity) {
            ++completed;
            if ((size_t)rc < 2 * capacity) ++partials;
        }
        close(fds[0]); close(fds[1]);
    }
    free(payload);
    printf("{\"observation\":\"writev.partial_shutdown\",\"completed\":%u,\"partials\":%u,\"positive_signals\":%u}\n",
           completed, partials, positive_signals);
    check("writev.partial_shutdown", completed == 8 && partials > 0 && positive_signals == 0);

    int fds[2];
    int ready = socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK, 0, fds) == 0;
    char good[4] = {'I', 'O', 'V', 'S'}, received[8] = {0};
    struct iovec bad_later[2] = {{.iov_base = good, .iov_len = 4}, {.iov_base = NULL, .iov_len = 4}};
    caught = 0; errno = 0;
    ssize_t rc = ready ? writev(fds[0], bad_later, 2) : -2; int error = errno;
    ssize_t got = ready ? recv(fds[1], received, sizeof received, 0) : -2;
    printf("{\"observation\":\"writev.invalid_after_progress\",\"rc\":%ld,\"errno\":%d,\"received\":%ld,\"bytes_ok\":%d,\"signals\":%d}\n",
           (long)rc, error, (long)got, !memcmp(received, good, 4), (int)caught);
    check("writev.invalid_after_progress", ready && rc == 4 && got == 4 && !memcmp(received, good, 4) && caught == 0);
    int shut = ready ? shutdown(fds[0], SHUT_WR) : -1;
    caught = 0; errno = 0; rc = ready ? writev(fds[0], NULL, 0) : -2; error = errno;
    printf("{\"observation\":\"writev.empty_vector\",\"rc\":%ld,\"errno\":%d,\"shutdown\":%d,\"signals\":%d}\n",
           (long)rc, error, shut, (int)caught);
    check("writev.empty_vector", shut == 0 && rc == 0 && caught == 0);
    struct iovec one = {.iov_base = good, .iov_len = 4};
    errno = 0; rc = ready ? pwritev(fds[0], &one, 1, 0) : -2; error = errno;
    printf("{\"observation\":\"writev.offset_boundary\",\"rc\":%ld,\"errno\":%d,\"signals\":%d}\n",
           (long)rc, error, (int)caught);
    check("writev.offset_boundary", ready && rc == -1 && error == ESPIPE && caught == 0);
    if (ready) { close(fds[0]); close(fds[1]); }
    if (setup) sigaction(SIGPIPE, &old, NULL);
}
static int guest_guard(int argc, char **argv) {
    if (argc != 2 || strcmp(argv[1], "--asterinas-disposable-guest")) return 0;
    char marker[34]; int fd = open("/.hepta-unix-signal-qa", O_RDONLY);
    if (fd < 0) return 0;
    ssize_t n = read(fd, marker, sizeof marker); close(fd);
    if (n != 33 || marker[32] != '\n') return 0;
    for (int i = 0; i < 32; ++i)
        if (!((marker[i] >= '0' && marker[i] <= '9') || (marker[i] >= 'a' && marker[i] <= 'f'))) return 0;
    return 1;
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int guarded = guest_guard(argc, argv); check("setup.guest_guard", guarded);
    if (!guarded) return 125;
    for (enum api api = SEND; api < API_COUNT; ++api) {
        run_case(api, DEFAULT); run_case(api, HANDLER); run_case(api, SEQPACKET); run_case(api, HEALTHY);
        if (api <= SENDMMSG) { run_case(api, NOSIGNAL); run_case(api, PER_CALL); }
    }
    run_case(SEND, ZERO_DEFAULT); run_case(SEND, ZERO_NOSIGNAL);
    nonblocking_partial();
    writev_boundaries();
    return failures ? 1 : 0;
}
