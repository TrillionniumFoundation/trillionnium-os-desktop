// SPDX-License-Identifier: MPL-2.0
// Guest-only cleanup saturation and actual TCP SO_LINGER regression.
#define main binder_transfer_fixture_main
#include "fd_probe.c"
#undef main
#include <netinet/in.h>
#include <sys/socket.h>
#include <time.h>

static uint64_t millis(void) {
    struct timespec ts;
    CHECK(clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
}
static void remote_objects(struct flat_binder_object value[2], struct handles h) {
    value[0] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_HANDLE,
        .flags = FLAT_BINDER_FLAG_ACCEPTS_FDS, .handle = h.accept};
    value[1] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_HANDLE, .handle = h.deny};
}
static struct handles local_owner(struct endpoint *manager, struct endpoint *owner) {
    struct flat_binder_object value[2] = {
        {.hdr.type = BINDER_TYPE_BINDER, .flags = FLAT_BINDER_FLAG_ACCEPTS_FDS,
         .binder = ACCEPT_PTR, .cookie = ACCEPT_COOKIE},
        {.hdr.type = BINDER_TYPE_BINDER, .binder = DENY_PTR, .cookie = DENY_COOKIE},
    };
    send_ok(owner, BC_TRANSACTION, 0, 100, 0, value, 2);
    completion(owner);
    struct message registration = receive(manager);
    CHECK(registration.kind == BR_TRANSACTION && registration.tr.code == 100);
    struct handles h = get_handles(&registration);
    CHECK(ref_command(manager, BC_ACQUIRE, h.accept) == 0);
    CHECK(ref_command(manager, BC_ACQUIRE, h.deny) == 0);
    free_buffer(manager, registration.tr.data.ptr.buffer);
    remote_objects(value, h);
    send_ok(manager, BC_REPLY, 0, 101, 0, value, 2);
    completion(manager);
    struct message reply = receive(owner);
    CHECK(reply.kind == BR_REPLY && reply.tr.code == 101);
    const struct flat_binder_object *returned = payload(&reply, 2);
    CHECK(returned[0].hdr.type == BINDER_TYPE_BINDER && returned[0].binder == ACCEPT_PTR);
    free_buffer(owner, reply.tr.data.ptr.buffer);
    return h;
}
static struct handles client_handles(struct endpoint *manager, struct endpoint *client,
                                      struct handles h) {
    send_ok(client, BC_TRANSACTION, 0, 110, 0, NULL, 0);
    completion(client);
    struct message request = receive(manager);
    CHECK(request.kind == BR_TRANSACTION && request.tr.code == 110);
    free_buffer(manager, request.tr.data.ptr.buffer);
    struct flat_binder_object value[2]; remote_objects(value, h);
    send_ok(manager, BC_REPLY, 0, 111, 0, value, 2);
    completion(manager);
    struct message reply = receive(client);
    CHECK(reply.kind == BR_REPLY && reply.tr.code == 111);
    struct handles result = get_handles(&reply);
    CHECK(ref_command(client, BC_ACQUIRE, result.accept) == 0);
    CHECK(ref_command(client, BC_ACQUIRE, result.deny) == 0);
    free_buffer(client, reply.tr.data.ptr.buffer);
    return result;
}
static void release_handles(struct endpoint *e, struct handles h) {
    CHECK(ref_command(e, BC_RELEASE, h.accept) == 0);
    CHECK(ref_command(e, BC_RELEASE, h.deny) == 0);
}
static void saturation(void) {
    struct endpoint manager = endpoint(); enter(&manager);
    CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR, 0) == 0);
    struct endpoint owner = endpoint(); enter(&owner);
    struct handles registered = local_owner(&manager, &owner);
    struct endpoint clients[9]; struct handles refs[9];
    for (unsigned i = 0; i < 9; ++i) {
        clients[i] = endpoint(); refs[i] = client_handles(&manager, &clients[i], registered);
    }
    int source = open("/tmp/binder-cleanup-saturation", O_RDWR | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    CHECK(source >= 0 && write(source, "original", 8) == 8 && lseek(source, 0, SEEK_SET) == 0);
    struct binder_fd_object values[32];
    for (unsigned i = 0; i < 32; ++i)
        values[i] = (struct binder_fd_object){.hdr.type = BINDER_TYPE_FD, .fd = (uint32_t)source};
    // Eight queued messages retain exactly 256 original file snapshots and
    // their already prepared cleanup stacks. No receiver descriptor is installed.
    for (unsigned i = 0; i < 8; ++i) {
        send_ok(&clients[i], BC_TRANSACTION, refs[i].accept, 700 + i, 0, values, 32);
        completion(&clients[i]);
    }
    unsigned before = fd_count();
    send_rejected(&clients[8], BC_TRANSACTION, refs[8].accept, 0, values, 1, ENOSPC);
    CHECK(fd_count() == before); no_messages(&clients[8]);
    close_endpoint(&owner); // Retire all 256 snapshots without reading their FD buffers.
    for (unsigned i = 0; i < 8; ++i) CHECK(receive(&clients[i]).kind == BR_DEAD_REPLY);
    // Once cleanup completes, an actual FD reply must succeed again. Rejected
    // attempts consume no reply and leave the same incoming request available.
    send_ok(&clients[8], BC_TRANSACTION, 0, 900, TF_ACCEPT_FDS, NULL, 0);
    completion(&clients[8]); struct message request = receive(&manager);
    CHECK(request.kind == BR_TRANSACTION && request.tr.code == 900);
    free_buffer(&manager, request.tr.data.ptr.buffer);
    uint64_t deadline = millis() + 5000, consumed = 0;
    for (;;) {
        if (send_payload(&manager, BC_REPLY, 0, 901, 0, values, 1, &consumed) == 0) break;
        CHECK(errno == ENOSPC && consumed == 0 && millis() < deadline); usleep(1000);
    }
    CHECK(consumed == 68); completion(&manager);
    struct message reply = receive(&clients[8]); CHECK(reply.kind == BR_REPLY && reply.tr.code == 901);
    int installed = received_fd(payload(&reply, 1)); char data[8];
    CHECK(read(installed, data, sizeof data) == sizeof data && !memcmp(data, "original", 8));
    free_buffer(&clients[8], reply.tr.data.ptr.buffer); CHECK(close(installed) == 0);
    for (unsigned i = 0; i < 9; ++i) { release_handles(&clients[i], refs[i]); close_endpoint(&clients[i]); }
    release_handles(&manager, registered); close_endpoint(&manager); CHECK(close(source) == 0);
    puts("binder_fd_256_prepared_cleanup_permits_saturate_reject_and_recover\tPASS");
}
static int slow_tcp(int *peer) {
    int listener = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0); CHECK(listener >= 0);
    int small = 4096;
    CHECK(setsockopt(listener, SOL_SOCKET, SO_RCVBUF, &small, sizeof small) == 0);
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    CHECK(bind(listener, (void *)&address, sizeof address) == 0 && listen(listener, 1) == 0);
    socklen_t size = sizeof address; CHECK(getsockname(listener, (void *)&address, &size) == 0);
    int source = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0); CHECK(source >= 0);
    CHECK(setsockopt(source, SOL_SOCKET, SO_SNDBUF, &small, sizeof small) == 0);
    int rc = connect(source, (void *)&address, sizeof address);
    CHECK(rc == 0 || (rc == -1 && errno == EINPROGRESS));
    *peer = accept4(listener, NULL, NULL, SOCK_CLOEXEC); CHECK(*peer >= 0);
    CHECK(close(listener) == 0);
    struct linger linger = {.l_onoff = 1, .l_linger = 3};
    CHECK(setsockopt(source, SOL_SOCKET, SO_LINGER, &linger, sizeof linger) == 0);
    char bytes[4096]; memset(bytes, 'L', sizeof bytes); size_t sent = 0;
    for (unsigned i = 0; i < 8192; ++i) {
        ssize_t count = send(source, bytes, sizeof bytes, 0);
        if (count < 0) { CHECK(errno == EAGAIN || errno == EWOULDBLOCK); break; }
        CHECK(count > 0); sent += (size_t)count;
    }
    CHECK(sent >= sizeof bytes);
    CHECK(send(source, bytes, sizeof bytes, 0) == -1 && errno == EAGAIN);
    return source;
}
static void slow_cleanup(void) {
    // Establish that this guest's real TCP destructor actually waits. A source
    // fixture that merely sets SO_LINGER without a slow close does not qualify.
    int baseline_peer; int baseline = slow_tcp(&baseline_peer);
    uint64_t started = millis(); CHECK(close(baseline) == 0); uint64_t baseline_ms = millis() - started;
    CHECK(baseline_ms >= 1500 && baseline_ms < 8000); CHECK(close(baseline_peer) == 0);
    struct endpoint manager = endpoint(); enter(&manager);
    CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR, 0) == 0);
    struct endpoint owner = endpoint(); enter(&owner);
    struct handles registered = local_owner(&manager, &owner);
    struct endpoint client = endpoint(); struct handles refs = client_handles(&manager, &client, registered);
    int peer, source = slow_tcp(&peer), pipe_fds[2]; CHECK(pipe(pipe_fds) == 0);
    struct binder_fd_object values[2]; fd_objects(values, source); values[1].fd = (uint32_t)pipe_fds[0];
    send_ok(&client, BC_TRANSACTION, refs.accept, 950, 0, values, 2);
    started = millis(); CHECK(close(source) == 0 && close(pipe_fds[0]) == 0);
    CHECK(millis() - started < 1000); // The queued snapshot still owns the actual socket.
    completion(&client);
    unsigned before = fd_count(); expect_read_error(&owner, (void *)1, EFAULT);
    const struct binder_fd_object *prepared = owner.mapping;
    uint32_t reserved[2] = {prepared[0].fd, prepared[1].fd};
    CHECK(fd_count() == before && reserved[0] != reserved[1]);
    CHECK(fcntl((int)reserved[0], F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl((int)reserved[1], F_GETFD) == -1 && errno == EBADF);
    started = millis(); close_endpoint(&owner);
    struct endpoint replacement = endpoint(); enter(&replacement);
    CHECK(millis() - started < 1000 && fd_count() == before);
    CHECK(fcntl((int)reserved[0], F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl((int)reserved[1], F_GETFD) == -1 && errno == EBADF);
    CHECK(receive(&client).kind == BR_DEAD_REPLY);
    // The separate pipe's last reader must disappear while the TCP cleanup
    // task is still inside its independently established multi-second linger.
    for (;;) {
        ssize_t rc = write(pipe_fds[1], "P", 1);
        if (rc == -1 && errno == EPIPE) break;
        CHECK(rc == 1 && millis() - started < 1000); usleep(1000);
    }
    CHECK(millis() - started < 1000); no_messages(&replacement);
    uint64_t cleanup_ms = millis() - started;
    release_handles(&client, refs); close_endpoint(&client); close_endpoint(&replacement);
    release_handles(&manager, registered); close_endpoint(&manager); CHECK(close(pipe_fds[1]) == 0);
    // Let the actual slow destructor finish before releasing its unread peer.
    if (cleanup_ms < 3500) usleep((useconds_t)((3500 - cleanup_ms) * 1000));
    CHECK(close(peer) == 0);
    printf("binder_fd_actual_TCP_linger_%llums_unrelated_refund_%llums\tPASS\n",
        (unsigned long long)baseline_ms, (unsigned long long)cleanup_ms);
}
int main(void) {
    role = "cleanup"; setbuf(stdout, NULL); signal(SIGALRM, alarmed); alarm(90); signal(SIGPIPE, SIG_IGN);
    usleep(100000); saturation(); slow_cleanup();
    printf("{\"passed\":true,\"checks\":%u,\"scope\":\"real_FD_cleanup_saturation_slow_TCP\",\"android_boot\":false}\n", checks);
    return 0;
}
