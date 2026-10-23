// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <sys/eventfd.h>
#include <fcntl.h>
#include <stdint.h>
#include <poll.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static unsigned cases;
#define REQUIRE(expr) do { if (!(expr)) { fprintf(stderr, "UNIX_OWNER_FAIL line=%d errno=%d expr=%s\n", __LINE__, errno, #expr); exit(1); } } while (0)
static void pass(const char *name) { ++cases; printf("UNIX_OWNER_CASE %s PASS\n", name); }
static void pair(int type, int fd[2]) { REQUIRE(socketpair(AF_UNIX, type | SOCK_NONBLOCK, 0, fd) == 0); }
static struct sockaddr_un address(const char *name) {
    struct sockaddr_un addr = { .sun_family = AF_UNIX };
    REQUIRE(strlen(name) + 1 < sizeof(addr.sun_path));
    memcpy(addr.sun_path + 1, name, strlen(name));
    return addr;
}
static socklen_t alen(const char *name) { return (socklen_t)(offsetof(struct sockaddr_un, sun_path) + 1 + strlen(name)); }
static int bound(int type, const char *name) {
    int fd = socket(AF_UNIX, type | SOCK_NONBLOCK, 0);
    REQUIRE(fd >= 0);
    struct sockaddr_un addr = address(name);
    REQUIRE(bind(fd, (struct sockaddr *)&addr, alen(name)) == 0);
    return fd;
}
static ssize_t send_files(int socket, const char *destination, const int *files, size_t count) {
    char control[CMSG_SPACE(2 * sizeof(int))] = {0};
    char byte = 'H';
    struct iovec io = { &byte, 1 };
    struct msghdr message = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = control,
                             .msg_controllen = CMSG_SPACE(count * sizeof(int)) };
    REQUIRE(count > 0 && count <= 2);
    struct sockaddr_un addr;
    if (destination) { addr = address(destination); message.msg_name = &addr; message.msg_namelen = alen(destination); }
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(count * sizeof(int));
    memcpy(CMSG_DATA(header), files, count * sizeof(int));
    return sendmsg(socket, &message, MSG_DONTWAIT | MSG_NOSIGNAL);
}
static void receive_files(int socket, int *files, size_t count) {
    char control[CMSG_SPACE(2 * sizeof(int))] = {0};
    char byte = 0;
    struct iovec io = { &byte, 1 };
    struct msghdr message = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = control, .msg_controllen = sizeof(control) };
    REQUIRE(recvmsg(socket, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC) == 1);
    REQUIRE(byte == 'H' && !(message.msg_flags & MSG_CTRUNC));
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    REQUIRE(header && header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_RIGHTS);
    REQUIRE(header->cmsg_len == CMSG_LEN(count * sizeof(int)));
    memcpy(files, CMSG_DATA(header), count * sizeof(int));
    REQUIRE(CMSG_NXTHDR(&message, header) == NULL);
}
static void notes(int type, const char *name) {
    int bootstrap[2], effect[2], recovery[2], received[2];
    pair(type, bootstrap); pair(SOCK_STREAM, effect); pair(SOCK_DGRAM, recovery);
    int transfer[] = {effect[0], recovery[0]};
    REQUIRE(send_files(bootstrap[0], NULL, transfer, 2) == 1);
    close(effect[0]); close(recovery[0]);
    receive_files(bootstrap[1], received, 2);
    for (int index = 0; index < 2; ++index) {
        int actual = 0; socklen_t size = sizeof(actual);
        REQUIRE(getsockopt(received[index], SOL_SOCKET, SO_TYPE, &actual, &size) == 0);
        REQUIRE(actual == (index == 0 ? SOCK_STREAM : SOCK_DGRAM));
        REQUIRE(send(received[index], "N", 1, MSG_NOSIGNAL) == 1);
        char byte = 0;
        REQUIRE(recv(index == 0 ? effect[1] : recovery[1], &byte, 1, 0) == 1 && byte == 'N');
        close(received[index]);
    }
    close(effect[1]); close(recovery[1]); close(bootstrap[0]); close(bootstrap[1]); pass(name);
}
static void listener(int type, const char *name) {
    int server = bound(type, name), client = socket(AF_UNIX, type | SOCK_NONBLOCK, 0);
    REQUIRE(client >= 0 && listen(server, 2) == 0);
    struct sockaddr_un addr = address(name);
    REQUIRE(connect(client, (struct sockaddr *)&addr, alen(name)) == 0);
    REQUIRE(send_files(client, NULL, &server, 1) == -1 && errno == ELOOP);
    int accepted = accept4(server, NULL, NULL, SOCK_NONBLOCK);
    REQUIRE(accepted >= 0);
    char byte;
    REQUIRE(recv(accepted, &byte, 1, MSG_DONTWAIT) == -1 && errno == EAGAIN);
    REQUIRE(send_files(client, NULL, &server, 1) == 1);
    int passed;
    receive_files(accepted, &passed, 1);
    int listening = 0; socklen_t size = sizeof(listening);
    REQUIRE(getsockopt(passed, SOL_SOCKET, SO_ACCEPTCONN, &listening, &size) == 0 && listening == 1);
    close(passed); close(accepted); close(client); close(server); pass(name);
}
static void future_connect(void) {
    const char *name = "unix-owner-future-a";
    int a = bound(SOCK_DGRAM, name), b = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK, 0);
    REQUIRE(b >= 0 && send_files(a, name, &b, 1) == 1);
    struct sockaddr_un addr = address(name);
    REQUIRE(connect(b, (struct sockaddr *)&addr, alen(name)) == -1 && errno == ELOOP);
    int received; receive_files(a, &received, 1); close(received);
    REQUIRE(connect(b, (struct sockaddr *)&addr, alen(name)) == 0);
    close(a); close(b); pass("datagram_future_connect");
}
static void self_cycle(int type, const char *name) {
    int fd[2]; pair(type, fd);
    for (int side = 0; side < 2; ++side) {
        REQUIRE(send_files(fd[0], NULL, &fd[side], 1) == -1 && errno == ELOOP);
        char byte;
        REQUIRE(recv(fd[1], &byte, 1, MSG_DONTWAIT) == -1 && errno == EAGAIN);
    }
    close(fd[0]); close(fd[1]); pass(name);
}
static void slots(void) {
    int fd[2]; pair(SOCK_SEQPACKET, fd);
    for (int i = 0; i < 128; ++i) REQUIRE(send(fd[0], "", 0, MSG_NOSIGNAL) == 0);
    REQUIRE(send(fd[0], "", 0, MSG_NOSIGNAL) == -1 && errno == EAGAIN);
    struct pollfd ready[] = {{fd[0], POLLOUT, 0}, {fd[1], POLLIN, 0}};
    REQUIRE(poll(ready, 2, 0) == 1 && !(ready[0].revents & POLLOUT) && (ready[1].revents & POLLIN));
    char byte;
    REQUIRE(recv(fd[1], &byte, 1, MSG_PEEK | MSG_DONTWAIT) == 0);
    REQUIRE(send(fd[0], "", 0, MSG_NOSIGNAL) == -1 && errno == EAGAIN);
    REQUIRE(recv(fd[1], &byte, 1, MSG_DONTWAIT) == 0);
    ready[0].revents = ready[1].revents = 0;
    REQUIRE(poll(ready, 2, 0) == 2 && (ready[0].revents & POLLOUT));
    REQUIRE(send(fd[0], "", 0, MSG_NOSIGNAL) == 0);
    close(fd[0]); close(fd[1]); pass("seqpacket_empty_slots");
}
static void concurrent(void) {
    const char *names[] = {"unix-owner-concurrent-a", "unix-owner-concurrent-b"};
    int fd[] = {bound(SOCK_DGRAM, names[0]), bound(SOCK_DGRAM, names[1])};
    int start[2], result[2]; REQUIRE(pipe(start) == 0 && pipe(result) == 0);
    pid_t children[2];
    for (int i = 0; i < 2; ++i) {
        children[i] = fork(); REQUIRE(children[i] >= 0);
        if (!children[i]) {
            close(start[1]); close(result[0]); char go;
            REQUIRE(read(start[0], &go, 1) == 1);
            ssize_t sent = send_files(fd[i], names[i], &fd[1-i], 1);
            char outcome = sent == 1 ? 'A' : sent == -1 && errno == ELOOP ? 'R' : 'X';
            REQUIRE(write(result[1], &outcome, 1) == 1);
            _exit(outcome == 'X' ? 1 : 0);
        }
    }
    close(start[0]); close(result[1]); REQUIRE(write(start[1], "GG", 2) == 2); close(start[1]);
    char outcome[2]; REQUIRE(read(result[0], outcome, 1) == 1 && read(result[0], outcome + 1, 1) == 1); close(result[0]);
    for (int i = 0; i < 2; ++i) { int status; REQUIRE(waitpid(children[i], &status, 0) == children[i] && WIFEXITED(status) && WEXITSTATUS(status) == 0); }
    REQUIRE((outcome[0] == 'A' && outcome[1] == 'R') || (outcome[1] == 'A' && outcome[0] == 'R'));
    close(fd[0]); close(fd[1]); pass("concurrent_cross_edges");
}
static ssize_t send_split_rights(int socket, int file, size_t first, size_t second) {
    char control[2 * CMSG_SPACE(254 * sizeof(int))] = {0};
    char byte = 'M';
    struct iovec io = { &byte, 1 };
    struct msghdr message = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = control,
        .msg_controllen = CMSG_SPACE(first * sizeof(int)) + (second ? CMSG_SPACE(second * sizeof(int)) : 0) };
    REQUIRE(first <= 254 && second <= 254);
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    size_t lengths[] = {first, second};
    for (unsigned part = 0; part < (second ? 2u : 1u); ++part) {
        REQUIRE(header != NULL);
        header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
        header->cmsg_len = CMSG_LEN(lengths[part] * sizeof(int));
        for (size_t i = 0; i < lengths[part]; ++i)
            memcpy(CMSG_DATA(header) + i * sizeof(int), &file, sizeof(file));
        header = CMSG_NXTHDR(&message, header);
    }
    return sendmsg(socket, &message, 0);
}
static void ancillary_253(void) {
    const int types[] = {SOCK_STREAM, SOCK_SEQPACKET, SOCK_DGRAM};
    for (unsigned type = 0; type < 3; ++type) {
        int fd[2]; pair(types[type], fd);
        int event = eventfd(17, EFD_NONBLOCK | EFD_CLOEXEC); REQUIRE(event >= 0);
        REQUIRE(send_split_rights(fd[0], event, 126, 127) == 1);
        close(event);
        char control[CMSG_SPACE(253 * sizeof(int))] = {0}, byte = 0;
        struct iovec io = {&byte, 1};
        struct msghdr msg = {.msg_iov = &io, .msg_iovlen = 1, .msg_control = control, .msg_controllen = sizeof(control)};
        REQUIRE(recvmsg(fd[1], &msg, MSG_CMSG_CLOEXEC) == 1 && byte == 'M' && !(msg.msg_flags & MSG_CTRUNC));
        struct cmsghdr *header = CMSG_FIRSTHDR(&msg);
        REQUIRE(header && header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_RIGHTS);
        REQUIRE(header->cmsg_len == CMSG_LEN(253 * sizeof(int)) && !CMSG_NXTHDR(&msg, header));
        int received[253]; memcpy(received, CMSG_DATA(header), sizeof(received));
        for (unsigned i = 0; i < 253; ++i) REQUIRE(fcntl(received[i], F_GETFD) == FD_CLOEXEC);
        uint64_t count = 0;
        REQUIRE(read(received[0], &count, sizeof(count)) == sizeof(count) && count == 17);
        count = 7; REQUIRE(write(received[252], &count, sizeof(count)) == sizeof(count));
        count = 0; REQUIRE(read(received[0], &count, sizeof(count)) == sizeof(count) && count == 7);
        for (unsigned i = 0; i < 253; ++i) REQUIRE(close(received[i]) == 0);
        REQUIRE(recv(fd[1], &byte, 1, 0) == -1 && errno == EAGAIN);
        close(fd[0]); close(fd[1]);
    }
    pass("ancillary_multisegment_253");
}
static void ancillary_reject(void) {
    const int types[] = {SOCK_STREAM, SOCK_SEQPACKET, SOCK_DGRAM};
    for (unsigned type = 0; type < 3; ++type) {
        int fd[2]; pair(types[type], fd);
        int event = eventfd(0, EFD_NONBLOCK); REQUIRE(event >= 0);
        REQUIRE(send_split_rights(fd[0], event, 254, 0) == -1 && errno == EINVAL);
        REQUIRE(send_split_rights(fd[0], event, 127, 127) == -1 && errno == EINVAL);
        REQUIRE(send_split_rights(fd[0], -1, 1, 0) == -1 && errno == EBADF);
        char byte = 0;
        REQUIRE(recv(fd[1], &byte, 1, 0) == -1 && errno == EAGAIN);
        close(event); close(fd[0]); close(fd[1]);
    }
    pass("ancillary_rejected_inputs_publish_nothing");
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0); alarm(20);
    int reference = argc == 2 && strcmp(argv[1], "--linux-notes-reference") == 0;
    int ancillary_reference = argc == 2 && strcmp(argv[1], "--linux-ancillary-reference") == 0;
    if (ancillary_reference) { ancillary_253(); ancillary_reject(); REQUIRE(cases == 2); return 0; }
    REQUIRE(reference || (argc == 2 && strcmp(argv[1], "--disposable-guest") == 0 && access("/.hepta-disposable-guest", R_OK) == 0));
    notes(SOCK_STREAM, "notes_stream"); notes(SOCK_SEQPACKET, "notes_seqpacket");
    if (!reference) {
        listener(SOCK_STREAM, "listener_pending_stream"); listener(SOCK_SEQPACKET, "listener_pending_seqpacket");
        future_connect(); self_cycle(SOCK_STREAM, "self_stream"); self_cycle(SOCK_SEQPACKET, "self_seqpacket"); self_cycle(SOCK_DGRAM, "self_datagram");
        slots(); concurrent(); ancillary_253(); ancillary_reject();
    }
    REQUIRE(cases == (reference ? 2u : 12u));
    printf("UNIX_OWNER_COMPLETE cases=%u failures=0\n", cases); return 0;
}
