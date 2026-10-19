// SPDX-License-Identifier: MPL-2.0
// A04 guest regression for PR #8's observed MSG_CMSG_CLOEXEC failure.
// Compile once with -static; run the identical ELF on Linux and the candidate kernel.
// This is an independent capability probe, not the pinned Debian13 rootfs profile.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define MAX_FDS 16
#define REQUIRE(expr) do { \
    if (!(expr)) { \
        fprintf(stderr, "SCM_CLOEXEC_ASSERT line=%d expression=%s errno=%d\n", \
                __LINE__, #expr, errno); \
        result = __LINE__; \
        goto out; \
    } \
} while (0)

struct fixture {
    int sockets[2];
    int source;
    int received[MAX_FDS];
    size_t received_count;
};

struct observation {
    size_t first_fd;
    size_t fd_count;
    int flags;
    bool credentials;
};

static void cleanup(struct fixture *f)
{
    for (size_t i = 0; i < f->received_count; ++i)
        close(f->received[i]);
    if (f->source >= 0)
        close(f->source);
    for (size_t i = 0; i < 2; ++i)
        if (f->sockets[i] >= 0)
            close(f->sockets[i]);
}

static int setup(struct fixture *f, int type)
{
    *f = (struct fixture){.sockets = {-1, -1}, .source = -1};
    if (socketpair(AF_UNIX, type | SOCK_CLOEXEC, 0, f->sockets) != 0)
        return -1;
    f->source = open("/dev/null", O_RDONLY | O_CLOEXEC);
    return f->source < 0 ? -1 : 0;
}

static int send_rights(struct fixture *f, size_t count)
{
    if (count > 3) {
        errno = EINVAL;
        return -1;
    }
    char payload = 'F';
    struct iovec io = {.iov_base = &payload, .iov_len = 1};
    union {
        struct cmsghdr alignment;
        unsigned char data[CMSG_SPACE(3 * sizeof(int))];
    } control = {0};
    struct msghdr msg = {.msg_iov = &io, .msg_iovlen = 1};
    if (count > 0) {
        msg.msg_control = control.data;
        msg.msg_controllen = CMSG_SPACE(count * sizeof(int));
        struct cmsghdr *header = CMSG_FIRSTHDR(&msg);
        header->cmsg_level = SOL_SOCKET;
        header->cmsg_type = SCM_RIGHTS;
        header->cmsg_len = CMSG_LEN(count * sizeof(int));
        int fds[3] = {f->source, f->source, f->source};
        memcpy(CMSG_DATA(header), fds, count * sizeof(int));
    }
    return sendmsg(f->sockets[0], &msg, 0) == 1 ? 0 : -1;
}

static int receive_rights(struct fixture *f, int flags, size_t capacity,
                          struct observation *o)
{
    char payload = 0;
    struct iovec io = {.iov_base = &payload, .iov_len = 1};
    union {
        struct cmsghdr alignment;
        unsigned char data[256];
    } control = {0};
    if (capacity > sizeof(control.data)) {
        errno = EINVAL;
        return -1;
    }
    struct msghdr msg = {
        .msg_iov = &io,
        .msg_iovlen = 1,
        .msg_control = capacity ? control.data : NULL,
        .msg_controllen = capacity,
    };
    *o = (struct observation){.first_fd = f->received_count};
    if (recvmsg(f->sockets[1], &msg, flags) != 1 || payload != 'F')
        return -1;
    if (msg.msg_controllen > capacity) {
        errno = EPROTO;
        return -1;
    }
    o->flags = msg.msg_flags;
    for (struct cmsghdr *h = CMSG_FIRSTHDR(&msg); h; h = CMSG_NXTHDR(&msg, h)) {
        if (h->cmsg_len < CMSG_LEN(0) || h->cmsg_level != SOL_SOCKET) {
            errno = EPROTO;
            return -1;
        }
        if (h->cmsg_type == SCM_CREDENTIALS) {
            struct ucred cred;
            if (h->cmsg_len != CMSG_LEN(sizeof(cred))) {
                errno = EPROTO;
                return -1;
            }
            memcpy(&cred, CMSG_DATA(h), sizeof(cred));
            if (cred.pid != getpid() || cred.uid != getuid() || cred.gid != getgid()) {
                errno = EPROTO;
                return -1;
            }
            o->credentials = true;
            continue;
        }
        size_t bytes = h->cmsg_len - CMSG_LEN(0);
        if (h->cmsg_type != SCM_RIGHTS || bytes % sizeof(int) != 0 ||
            bytes / sizeof(int) > MAX_FDS - f->received_count) {
            errno = EPROTO;
            return -1;
        }
        size_t count = bytes / sizeof(int);
        memcpy(f->received + f->received_count, CMSG_DATA(h), bytes);
        f->received_count += count;
        o->fd_count += count;
    }
    return 0;
}

static bool descriptor_flags_match(const struct fixture *f,
                                   const struct observation *o, bool cloexec)
{
    for (size_t i = o->first_fd; i < o->first_fd + o->fd_count; ++i) {
        int flags = fcntl(f->received[i], F_GETFD);
        if (flags < 0 || !!(flags & FD_CLOEXEC) != cloexec)
            return false;
    }
    return !!(o->flags & MSG_CMSG_CLOEXEC) == cloexec;
}

static int plain_receive(int type, const char *self)
{
    (void)self;
    int result = 0;
    struct fixture f;
    struct observation o;
    REQUIRE(setup(&f, type) == 0);
    REQUIRE(send_rights(&f, 1) == 0);
    REQUIRE(receive_rights(&f, 0, 256, &o) == 0);
    REQUIRE(o.fd_count == 1 && !(o.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &o, false));
    REQUIRE(fcntl(f.source, F_GETFD) == FD_CLOEXEC);
out:
    cleanup(&f);
    return result;
}

static int cloexec_multifd(int type, const char *self)
{
    (void)self;
    int result = 0;
    struct fixture f;
    struct observation o;
    REQUIRE(setup(&f, type) == 0);
    REQUIRE(fcntl(f.source, F_SETFD, 0) == 0);
    REQUIRE(send_rights(&f, 3) == 0);
    REQUIRE(receive_rights(&f, MSG_CMSG_CLOEXEC, 256, &o) == 0);
    REQUIRE(o.fd_count == 3 && !(o.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &o, true));
    REQUIRE(f.received[0] != f.received[1] && f.received[0] != f.received[2] &&
            f.received[1] != f.received[2]);
    REQUIRE(fcntl(f.source, F_GETFD) == 0);
out:
    cleanup(&f);
    return result;
}

static int peek_then_receive(int type, bool peek_cloexec)
{
    int result = 0;
    struct fixture f;
    struct observation peek, consumed;
    REQUIRE(setup(&f, type) == 0);
    REQUIRE(send_rights(&f, 2) == 0);
    REQUIRE(receive_rights(&f, MSG_PEEK | (peek_cloexec ? MSG_CMSG_CLOEXEC : 0),
                           256, &peek) == 0);
    REQUIRE(peek.fd_count == 2 && !(peek.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &peek, peek_cloexec));
    REQUIRE(receive_rights(&f, peek_cloexec ? 0 : MSG_CMSG_CLOEXEC,
                           256, &consumed) == 0);
    REQUIRE(consumed.fd_count == 2 && !(consumed.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &consumed, !peek_cloexec));
    REQUIRE(descriptor_flags_match(&f, &peek, peek_cloexec));
    REQUIRE(f.received[0] != f.received[2] && f.received[1] != f.received[3]);
out:
    cleanup(&f);
    return result;
}

static int peek_cloexec(int type, const char *self)
{
    (void)self;
    return peek_then_receive(type, true);
}

static int peek_plain(int type, const char *self)
{
    (void)self;
    return peek_then_receive(type, false);
}

static int truncated_control(int type, const char *self)
{
    (void)self;
    int result = 0;
    struct fixture f;
    struct observation o;
    REQUIRE(setup(&f, type) == 0);
    REQUIRE(send_rights(&f, 3) == 0);
    REQUIRE(receive_rights(&f, MSG_CMSG_CLOEXEC, CMSG_LEN(sizeof(int)), &o) == 0);
    REQUIRE(o.fd_count == 1 && (o.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &o, true));
out:
    cleanup(&f);
    return result;
}

static int discarded_control(int type, const char *self)
{
    (void)self;
    int result = 0;
    struct fixture f;
    struct observation o;
    int after = -1;
    REQUIRE(setup(&f, type) == 0);
    int available = dup(f.source);
    REQUIRE(available >= 0);
    REQUIRE(close(available) == 0);
    REQUIRE(send_rights(&f, 3) == 0);
    REQUIRE(receive_rights(&f, MSG_CMSG_CLOEXEC, 0, &o) == 0);
    REQUIRE(o.fd_count == 0 && (o.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &o, true));
    after = dup(f.source);
    REQUIRE(after == available);
out:
    if (after >= 0)
        close(after);
    cleanup(&f);
    return result;
}

static int no_control_message(int type, const char *self)
{
    (void)self;
    int result = 0;
    struct fixture f;
    struct observation o;
    REQUIRE(setup(&f, type) == 0);
    REQUIRE(send_rights(&f, 0) == 0);
    REQUIRE(receive_rights(&f, MSG_CMSG_CLOEXEC, 256, &o) == 0);
    REQUIRE(o.fd_count == 0 && !(o.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &o, true));
out:
    cleanup(&f);
    return result;
}

static int credentials_with_rights(int type, const char *self)
{
    (void)self;
    int result = 0;
    struct fixture f;
    struct observation o;
    int enabled = 1;
    REQUIRE(setup(&f, type) == 0);
    REQUIRE(setsockopt(f.sockets[1], SOL_SOCKET, SO_PASSCRED,
                       &enabled, sizeof(enabled)) == 0);
    REQUIRE(send_rights(&f, 2) == 0);
    REQUIRE(receive_rights(&f, MSG_CMSG_CLOEXEC, 256, &o) == 0);
    REQUIRE(o.fd_count == 2 && o.credentials && !(o.flags & MSG_CTRUNC));
    REQUIRE(descriptor_flags_match(&f, &o, true));
out:
    cleanup(&f);
    return result;
}

static int exec_inheritance(int type, const char *self)
{
    int result = 0;
    struct fixture f;
    struct observation plain, cloexec;
    pid_t child = -1;
    REQUIRE(setup(&f, type) == 0);
    REQUIRE(send_rights(&f, 1) == 0);
    REQUIRE(receive_rights(&f, 0, 256, &plain) == 0 && plain.fd_count == 1);
    REQUIRE(send_rights(&f, 1) == 0);
    REQUIRE(receive_rights(&f, MSG_CMSG_CLOEXEC, 256, &cloexec) == 0 &&
            cloexec.fd_count == 1);
    REQUIRE(descriptor_flags_match(&f, &plain, false));
    REQUIRE(descriptor_flags_match(&f, &cloexec, true));
    child = fork();
    REQUIRE(child >= 0);
    if (child == 0) {
        char keep[24], drop[24];
        snprintf(keep, sizeof(keep), "%d", f.received[plain.first_fd]);
        snprintf(drop, sizeof(drop), "%d", f.received[cloexec.first_fd]);
        execl(self, self, "--exec-check", keep, drop, (char *)NULL);
        _exit(127);
    }
    int status = 0;
    pid_t waited;
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    if (waited == child)
        child = -1;
    REQUIRE(waited >= 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    REQUIRE(descriptor_flags_match(&f, &plain, false));
    REQUIRE(descriptor_flags_match(&f, &cloexec, true));
out:
    if (child > 0) {
        kill(child, SIGKILL);
        while (waitpid(child, NULL, 0) < 0 && errno == EINTR) {}
    }
    cleanup(&f);
    return result;
}

int main(int argc, char **argv)
{
    if (argc == 4 && strcmp(argv[1], "--exec-check") == 0) {
        int keep = atoi(argv[2]);
        int drop = atoi(argv[3]);
        if (keep == drop || fcntl(keep, F_GETFD) != 0)
            return 81;
        errno = 0;
        return fcntl(drop, F_GETFD) == -1 && errno == EBADF ? 0 : 82;
    }
    if (argc != 1 || argv[0][0] != '/') {
        fprintf(stderr, "invoke the probe by its absolute path (for fork/exec checks)\n");
        return 2;
    }
    // Every scenario uses only this process's sockets, FDs and reaped child.
    // An outer guest runner must also impose a QEMU deadline and retain raw serial.
    alarm(30);
    setvbuf(stdout, NULL, _IONBF, 0);
    const struct {
        const char *name;
        int type;
    } sockets[] = {{"stream", SOCK_STREAM}, {"datagram", SOCK_DGRAM},
                   {"seqpacket", SOCK_SEQPACKET}};
    const struct {
        const char *name;
        int (*run)(int, const char *);
    } cases[] = {
        {"plain_receive", plain_receive},
        {"cloexec_multifd", cloexec_multifd},
        {"peek_cloexec_then_plain", peek_cloexec},
        {"peek_plain_then_cloexec", peek_plain},
        {"truncated_control", truncated_control},
        {"discarded_control", discarded_control},
        {"no_control_message", no_control_message},
        {"credentials_with_rights", credentials_with_rights},
        {"exec_inheritance", exec_inheritance},
    };
    size_t total = 0, failed = 0;
    for (size_t s = 0; s < sizeof(sockets) / sizeof(sockets[0]); ++s) {
        for (size_t c = 0; c < sizeof(cases) / sizeof(cases[0]); ++c) {
            int result = cases[c].run(sockets[s].type, argv[0]);
            ++total;
            failed += result != 0;
            printf("SCM_CLOEXEC_CASE name=%s.%s result=%s line=%d\n",
                   sockets[s].name, cases[c].name, result ? "FAIL" : "PASS", result);
        }
    }
    alarm(0);
    printf("SCM_CLOEXEC_COMPLETE total=%zu passed=%zu failed=%zu\n",
           total, total - failed, failed);
    return failed ? 1 : 0;
}
