// SPDX-License-Identifier: MPL-2.0
// Real Binder FD transfer fixture. Build on host; execute only in an isolated guest.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/android/binder.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MAP_BYTES (16u * 4096u)
#define ACCEPT_PTR UINT64_C(0x10101000)
#define ACCEPT_COOKIE UINT64_C(0x1122334455667788)
#define DENY_PTR UINT64_C(0x10102000)
#define DENY_COOKIE UINT64_C(0x2233445566778899)
#define FD_COOKIE UINT64_C(0)
static unsigned checks;
static const char *role = "manager";
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "Binder FD FAIL role=%s line=%d: %s errno=%d\n", role, __LINE__, #x, errno); exit(1); } ++checks; } while (0)
struct ref_state { uint64_t pointer, cookie; int weak, strong; };
struct endpoint { int fd; void *mapping; struct ref_state nodes[2]; };
struct message { uint32_t kind; struct binder_transaction_data tr; };
struct handles { uint32_t accept, deny; };
static void alarmed(int sig) { (void)sig; _exit(124); }
static void byte(int fd, char value) { CHECK(write(fd, &value, 1) == 1); }
static void await_byte(int fd, char wanted) { char value = 0; CHECK(read(fd, &value, 1) == 1 && value == wanted); }
static void wait_child(pid_t child) { int status = 0; CHECK(waitpid(child, &status, 0) == child); CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0); }
static int commands(int fd, const void *bytes, size_t size, uint64_t *consumed) {
    struct binder_write_read wire = {.write_size = size, .write_buffer = (uintptr_t)bytes};
    int rc = ioctl(fd, BINDER_WRITE_READ, &wire);
    if (consumed) *consumed = wire.write_consumed;
    return rc;
}
static int read_bytes(int fd, void *bytes, size_t size, uint64_t *consumed) {
    struct binder_write_read wire = {.read_size = size, .read_buffer = (uintptr_t)bytes};
    int rc = ioctl(fd, BINDER_WRITE_READ, &wire);
    if (consumed) *consumed = wire.read_consumed;
    return rc;
}
static struct endpoint endpoint(void) {
    struct endpoint e = {.fd = open("/dev/binder", O_RDWR | O_CLOEXEC)};
    CHECK(e.fd >= 0);
    struct binder_version version = {0};
    CHECK(ioctl(e.fd, BINDER_VERSION, &version) == 0 && version.protocol_version == 8);
    e.mapping = mmap(NULL, MAP_BYTES, PROT_READ, MAP_PRIVATE, e.fd, 0);
    CHECK(e.mapping != MAP_FAILED);
    e.nodes[0] = (struct ref_state){.pointer = ACCEPT_PTR, .cookie = ACCEPT_COOKIE};
    e.nodes[1] = (struct ref_state){.pointer = DENY_PTR, .cookie = DENY_COOKIE};
    return e;
}
static void close_endpoint(struct endpoint *e) { CHECK(munmap(e->mapping, MAP_BYTES) == 0); CHECK(close(e->fd) == 0); e->fd = -1; }
static void enter(struct endpoint *e) { uint32_t command = BC_ENTER_LOOPER; CHECK(commands(e->fd, &command, 4, NULL) == 0); }
static int ref_command(struct endpoint *e, uint32_t kind, uint32_t handle) {
    unsigned char bytes[8]; memcpy(bytes, &kind, 4); memcpy(bytes + 4, &handle, 4);
    return commands(e->fd, bytes, sizeof bytes, NULL);
}
static void acknowledge(struct endpoint *e, uint32_t kind, const struct binder_ptr_cookie *object) {
    unsigned char bytes[20]; memcpy(bytes, &kind, 4); memcpy(bytes + 4, object, 16);
    CHECK(commands(e->fd, bytes, sizeof bytes, NULL) == 0);
}
static int reference_work(struct endpoint *e, uint32_t kind, const unsigned char *bytes, uint64_t size) {
    if (kind != BR_INCREFS && kind != BR_ACQUIRE && kind != BR_RELEASE && kind != BR_DECREFS) return 0;
    CHECK(size == 20);
    struct binder_ptr_cookie object; memcpy(&object, bytes + 4, 16);
    struct ref_state *node = NULL;
    for (unsigned i = 0; i < 2; ++i)
        if (object.ptr == e->nodes[i].pointer && object.cookie == e->nodes[i].cookie) node = &e->nodes[i];
    CHECK(node != NULL);
    if (kind == BR_INCREFS) { CHECK(!node->weak && !node->strong); node->weak = 1; acknowledge(e, BC_INCREFS_DONE, &object); }
    else if (kind == BR_ACQUIRE) { CHECK(node->weak && !node->strong); node->strong = 1; acknowledge(e, BC_ACQUIRE_DONE, &object); }
    else if (kind == BR_RELEASE) { CHECK(node->strong); node->strong = 0; }
    else { CHECK(node->weak && !node->strong); node->weak = 0; }
    return 1;
}
static struct message receive(struct endpoint *e) {
    for (;;) {
        unsigned char bytes[128] = {0}; uint64_t size = 0;
        CHECK(read_bytes(e->fd, bytes, sizeof bytes, &size) == 0 && size >= 4);
        struct message result = {0}; memcpy(&result.kind, bytes, 4);
        if (reference_work(e, result.kind, bytes, size)) continue;
        if (result.kind == BR_TRANSACTION || result.kind == BR_REPLY) { CHECK(size == 68); memcpy(&result.tr, bytes + 4, 64); }
        else CHECK(size == 4);
        return result;
    }
}
static void completion(struct endpoint *e) { CHECK(receive(e).kind == BR_TRANSACTION_COMPLETE); }
static int send_raw(struct endpoint *e, uint32_t kind, const struct binder_transaction_data *tr, uint64_t *consumed) {
    unsigned char stream[68]; memcpy(stream, &kind, 4); memcpy(stream + 4, tr, 64);
    return commands(e->fd, stream, sizeof stream, consumed);
}
static int send_payload(struct endpoint *e, uint32_t kind, uint32_t target, uint32_t code,
                        uint32_t flags, const void *objects, size_t count, uint64_t *consumed) {
    CHECK(count <= 32);
    binder_size_t offsets[32];
    for (size_t i = 0; i < count; ++i) offsets[i] = i * 24;
    struct binder_transaction_data tr = {
        .target.handle = target, .code = code, .flags = flags,
        .data_size = count * 24, .offsets_size = count * sizeof(binder_size_t),
        .data.ptr.buffer = (uintptr_t)objects, .data.ptr.offsets = (uintptr_t)offsets,
    };
    return send_raw(e, kind, &tr, consumed);
}
static void send_ok(struct endpoint *e, uint32_t kind, uint32_t target, uint32_t code,
                     uint32_t flags, const void *objects, size_t count) {
    uint64_t consumed = 0;
    CHECK(send_payload(e, kind, target, code, flags, objects, count, &consumed) == 0 && consumed == 68);
}
static void send_rejected(struct endpoint *e, uint32_t kind, uint32_t target, uint32_t flags,
                          const void *objects, size_t count, int expected) {
    uint64_t consumed = 99;
    CHECK(send_payload(e, kind, target, 999, flags, objects, count, &consumed) == -1 && errno == expected && consumed == 0);
}
static void free_buffer(struct endpoint *e, binder_uintptr_t address) {
    unsigned char bytes[12]; uint32_t kind = BC_FREE_BUFFER;
    memcpy(bytes, &kind, 4); memcpy(bytes + 4, &address, 8);
    CHECK(commands(e->fd, bytes, sizeof bytes, NULL) == 0);
}
static const void *payload(const struct message *message, size_t count) {
    CHECK(message->tr.data_size == count * 24 && message->tr.offsets_size == count * 8);
    CHECK(message->tr.data.ptr.offsets == message->tr.data.ptr.buffer + count * 24);
    const binder_size_t *offsets = (const void *)(uintptr_t)message->tr.data.ptr.offsets;
    for (size_t i = 0; i < count; ++i) CHECK(offsets[i] == i * 24);
    return (const void *)(uintptr_t)message->tr.data.ptr.buffer;
}
static struct handles get_handles(const struct message *message) {
    const struct flat_binder_object *values = payload(message, 2);
    CHECK(values[0].hdr.type == BINDER_TYPE_HANDLE && values[0].flags == FLAT_BINDER_FLAG_ACCEPTS_FDS);
    CHECK(values[1].hdr.type == BINDER_TYPE_HANDLE && values[1].flags == 0);
    CHECK(values[0].handle != 0 && values[1].handle != 0 && values[0].handle != values[1].handle);
    CHECK(values[0].cookie == 0 && values[1].cookie == 0);
    CHECK((values[0].binder >> 32) == 0 && (values[1].binder >> 32) == 0);
    return (struct handles){values[0].handle, values[1].handle};
}
static void fd_objects(struct binder_fd_object values[2], int fd) {
    values[0] = (struct binder_fd_object){.hdr.type = BINDER_TYPE_FD, .fd = (uint32_t)fd, .cookie = FD_COOKIE};
    values[1] = values[0];
}
static int received_fd(const struct binder_fd_object *object) {
    CHECK(object->hdr.type == BINDER_TYPE_FD && object->pad_flags == 0 && object->cookie == FD_COOKIE);
    CHECK((object->pad_binder >> 32) == 0 && object->fd <= INT32_MAX);
    int flags = fcntl((int)object->fd, F_GETFD);
    CHECK(flags >= 0 && (flags & FD_CLOEXEC));
    return (int)object->fd;
}
static unsigned fd_count(void) {
    unsigned count = 0;
    for (int fd = 0; fd < 256; ++fd) {
        errno = 0;
        int flags = fcntl(fd, F_GETFD);
        if (flags >= 0) ++count;
        else CHECK(errno == EBADF);
    }
    return count;
}
static void no_messages(struct endpoint *e) {
    int flags = fcntl(e->fd, F_GETFL);
    CHECK(flags >= 0 && fcntl(e->fd, F_SETFL, flags | O_NONBLOCK) == 0);
    unsigned char bytes[128];
    CHECK(read_bytes(e->fd, bytes, sizeof bytes, NULL) == -1 && errno == EAGAIN);
    CHECK(fcntl(e->fd, F_SETFL, flags) == 0);
}
static void owner_registration(struct endpoint *own) {
    struct flat_binder_object objects[2] = {
        {.hdr.type = BINDER_TYPE_BINDER, .flags = FLAT_BINDER_FLAG_ACCEPTS_FDS, .binder = ACCEPT_PTR, .cookie = ACCEPT_COOKIE},
        {.hdr.type = BINDER_TYPE_BINDER, .binder = DENY_PTR, .cookie = DENY_COOKIE},
    };
    send_ok(own, BC_TRANSACTION, 0, 100, 0, objects, 2);
    completion(own);
    struct message reply = receive(own);
    CHECK(reply.kind == BR_REPLY && reply.tr.code == 101);
    const struct flat_binder_object *returned = payload(&reply, 2);
    CHECK(returned[0].hdr.type == BINDER_TYPE_BINDER && returned[0].binder == ACCEPT_PTR && returned[0].cookie == ACCEPT_COOKIE);
    CHECK(returned[0].flags == FLAT_BINDER_FLAG_ACCEPTS_FDS);
    CHECK(returned[1].hdr.type == BINDER_TYPE_BINDER && returned[1].binder == DENY_PTR && returned[1].cookie == DENY_COOKIE && returned[1].flags == 0);
    free_buffer(own, reply.tr.data.ptr.buffer);
}
static void ordinary_fd_request(struct endpoint *own, unsigned call, pid_t client) {
    struct message request = receive(own);
    CHECK(request.kind == BR_TRANSACTION && request.tr.code == 200 + call);
    CHECK(request.tr.target.ptr == ACCEPT_PTR && request.tr.cookie == ACCEPT_COOKIE);
    CHECK(request.tr.sender_pid == client && request.tr.sender_euid == 0);
    CHECK(request.tr.flags == (call ? 0u : (uint32_t)TF_ACCEPT_FDS));
    const struct binder_fd_object *objects = payload(&request, 1);
    int fd = received_fd(&objects[0]);
    struct binder_fd_object reply[2]; fd_objects(reply, fd);
    if (!call) {
        char value[7]; CHECK(read(fd, value, sizeof value) == sizeof value && !memcmp(value, "source-", sizeof value));
        send_ok(own, BC_REPLY, 0, 210, 0, reply, 1);
    } else {
        send_rejected(own, BC_REPLY, 0, 0, reply, 1, EPERM);
        send_ok(own, BC_REPLY, 0, 211, 0, NULL, 0);
    }
    completion(own);
    free_buffer(own, request.tr.data.ptr.buffer);
    CHECK(fcntl(fd, F_GETFD) >= 0); // FREE_BUFFER is not a descriptor close.
    CHECK(close(fd) == 0);
}
static void racy_fd_requests(struct endpoint *own, pid_t client) {
    for (unsigned i = 0; i < 128; ++i) {
        // The client delays every enqueue, so this read repeatedly starts with
        // an empty transaction queue while another process later fills it.
        struct message request = receive(own);
        CHECK(request.kind == BR_TRANSACTION && request.tr.code == 300 + i);
        CHECK(request.tr.sender_pid == client && request.tr.flags == TF_ACCEPT_FDS);
        CHECK(request.tr.target.ptr == ACCEPT_PTR && request.tr.cookie == ACCEPT_COOKIE);
        const struct binder_fd_object *object = payload(&request, 1);
        int fd = received_fd(object);
        unsigned char value = 0;
        CHECK(read(fd, &value, 1) == 1 && value == (unsigned char)((2 * i) ^ 0xa5));
        struct binder_fd_object returned[2]; fd_objects(returned, fd);
        send_ok(own, BC_REPLY, 0, 500 + i, 0, returned, 1);
        completion(own);
        free_buffer(own, request.tr.data.ptr.buffer);
        CHECK(close(fd) == 0);
    }
    puts("binder_fd_128_empty_queue_to_real_FD_enqueue_races\tPASS");
}
static void expect_read_error(struct endpoint *e, void *address, int wanted) {
    unsigned char bytes[128]; uint64_t consumed = 99;
    CHECK(read_bytes(e->fd, address ? address : bytes, sizeof bytes, &consumed) == -1 && errno == wanted && consumed == 0);
}
static void emfile_and_copyfault(struct endpoint *own, pid_t client) {
    struct rlimit original;
    CHECK(getrlimit(RLIMIT_NOFILE, &original) == 0 && original.rlim_cur >= 64);
    struct rlimit limited = original; limited.rlim_cur = 64;
    CHECK(setrlimit(RLIMIT_NOFILE, &limited) == 0);
    int fillers[64]; unsigned nr = 0;
    for (;;) {
        int fd = open("/dev/null", O_RDONLY | O_CLOEXEC);
        if (fd < 0) { CHECK(errno == EMFILE); break; }
        CHECK(nr < 64); fillers[nr++] = fd;
    }
    CHECK(nr >= 2 && fd_count() == 64);
    expect_read_error(own, NULL, EMFILE);
    CHECK(fd_count() == 64);
    CHECK(close(fillers[--nr]) == 0);
    CHECK(fd_count() == 63);
    // One free slot is insufficient for a two-object transaction; the first
    // reservation must roll back instead of consuming that slot on failure.
    expect_read_error(own, NULL, EMFILE);
    CHECK(fd_count() == 63);
    int reusable = open("/dev/null", O_RDONLY | O_CLOEXEC);
    CHECK(reusable >= 0); CHECK(close(reusable) == 0);
    CHECK(close(fillers[--nr]) == 0 && fd_count() == 62);
    expect_read_error(own, (void *)1, EFAULT);
    CHECK(fd_count() == 62);
    const struct binder_fd_object *prepared = own->mapping;
    CHECK(prepared[0].hdr.type == BINDER_TYPE_FD && prepared[1].hdr.type == BINDER_TYPE_FD);
    uint32_t first = prepared[0].fd, second = prepared[1].fd;
    CHECK(first != second && first < 64 && second < 64);
    CHECK(fcntl((int)first, F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl((int)second, F_GETFD) == -1 && errno == EBADF);
    CHECK(open("/dev/null", O_RDONLY | O_CLOEXEC) == -1 && errno == EMFILE);
    expect_read_error(own, (void *)1, EFAULT);
    CHECK(fd_count() == 62 && prepared[0].fd == first && prepared[1].fd == second);
    struct message request = receive(own);
    CHECK(request.kind == BR_TRANSACTION && request.tr.code == 202 && request.tr.sender_pid == client);
    CHECK(request.tr.flags == TF_ACCEPT_FDS && request.tr.target.ptr == ACCEPT_PTR && request.tr.cookie == ACCEPT_COOKIE);
    const struct binder_fd_object *objects = payload(&request, 2);
    CHECK(objects[0].fd == first && objects[1].fd == second);
    int fds[2] = {received_fd(&objects[0]), received_fd(&objects[1])};
    CHECK(fd_count() == 64);
    CHECK(setrlimit(RLIMIT_NOFILE, &original) == 0);
    for (unsigned i = 0; i < nr; ++i) CHECK(close(fillers[i]) == 0);
    char value = 0;
    CHECK(read(fds[0], &value, 1) == 1 && value == 'A');
    CHECK(read(fds[1], &value, 1) == 1 && value == 'B');
    struct binder_fd_object returned[2]; fd_objects(returned, fds[0]); returned[1].fd = (uint32_t)fds[1];
    send_ok(own, BC_REPLY, 0, 212, 0, returned, 2);
    completion(own);
    free_buffer(own, request.tr.data.ptr.buffer);
    CHECK(fcntl(fds[0], F_GETFD) >= 0 && fcntl(fds[1], F_GETFD) >= 0);
    CHECK(close(fds[0]) == 0 && close(fds[1]) == 0);
    puts("binder_fd_EMFILE_atomic_reservation_and_EFAULT_stable_retry\tPASS");
}
static void prepared_close(struct endpoint *own, int rollback_ready, int control) {
    unsigned before = fd_count();
    expect_read_error(own, (void *)1, EFAULT);
    CHECK(fd_count() == before);
    const struct binder_fd_object *prepared = own->mapping;
    CHECK(prepared[0].hdr.type == BINDER_TYPE_FD);
    uint32_t reserved = prepared[0].fd;
    CHECK(fcntl((int)reserved, F_GETFD) == -1 && errno == EBADF);
    close_endpoint(own);
    // Open/ioctl of a fresh endpoint drains deferred cleanup outside DOMAIN.
    struct endpoint replacement = endpoint(); enter(&replacement);
    CHECK(fd_count() == before);
    CHECK(fcntl((int)reserved, F_GETFD) == -1 && errno == EBADF);
    no_messages(&replacement);
    byte(rollback_ready, 'r');
    await_byte(control, 'x');
    no_messages(&replacement);
    close_endpoint(&replacement);
    puts("binder_fd_close_prepared_releases_reservation_and_original_file\tPASS");
}
static void owner_process(int inherited, int ready, int control, int rollback_ready) {
    role = "owner"; alarm(30); CHECK(close(inherited) == 0);
    struct endpoint own = endpoint(); enter(&own); owner_registration(&own);
    byte(ready, 'r'); pid_t client = 0;
    CHECK(read(control, &client, sizeof client) == sizeof client && client > 0);
    ordinary_fd_request(&own, 0, client);
    ordinary_fd_request(&own, 1, client);
    racy_fd_requests(&own, client);
    emfile_and_copyfault(&own, client);
    prepared_close(&own, rollback_ready, control);
    printf("binder_fd_real_owner_acceptance_transfer_and_rollback\tPASS checks=%u\n", checks);
    _exit(0);
}
static void invalid_fd_metadata(struct endpoint *e, uint32_t handle, int fd) {
    struct binder_fd_object object[2]; fd_objects(object, fd);
    object[0].cookie = 1;
    uint64_t consumed = 99;
    CHECK(send_payload(e, BC_TRANSACTION, handle, 999, 0, object, 1, &consumed) == -1
          && (errno == EINVAL || errno == EOPNOTSUPP) && consumed == 0);
    object[0].cookie = 0; object[0].pad_binder |= UINT64_C(1) << 32;
    consumed = 99;
    CHECK(send_payload(e, BC_TRANSACTION, handle, 999, 0, object, 1, &consumed) == -1
          && (errno == EINVAL || errno == EOPNOTSUPP) && consumed == 0);
    fd_objects(object, fd); object[0].pad_flags = 1; consumed = 99;
    CHECK(send_payload(e, BC_TRANSACTION, handle, 999, 0, object, 1, &consumed) == -1
          && (errno == EINVAL || errno == EOPNOTSUPP) && consumed == 0);
}
static void client_process(int inherited, int rollback_ready) {
    role = "client"; alarm(30); signal(SIGPIPE, SIG_IGN); CHECK(close(inherited) == 0);
    struct endpoint own = endpoint();
    send_ok(&own, BC_TRANSACTION, 0, 110, 0, NULL, 0); completion(&own);
    struct message reply = receive(&own);
    CHECK(reply.kind == BR_REPLY && reply.tr.code == 111);
    struct handles handles = get_handles(&reply);
    CHECK(ref_command(&own, BC_ACQUIRE, handles.accept) == 0 && ref_command(&own, BC_ACQUIRE, handles.deny) == 0);
    free_buffer(&own, reply.tr.data.ptr.buffer);
    int source = open("/tmp/binder-fd-source", O_RDWR | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    CHECK(source >= 0 && write(source, "source-object-file", 18) == 18 && lseek(source, 0, SEEK_SET) == 0);
    struct binder_fd_object values[2]; fd_objects(values, source);
    send_rejected(&own, BC_TRANSACTION, 0, TF_ACCEPT_FDS, values, 1, EPERM);
    send_rejected(&own, BC_TRANSACTION, handles.deny, TF_ACCEPT_FDS, values, 1, EPERM);
    struct binder_fd_object bad[2]; fd_objects(bad, 0x7ffffffe);
    send_rejected(&own, BC_TRANSACTION, handles.accept, TF_ACCEPT_FDS, bad, 1, EBADF);
    invalid_fd_metadata(&own, handles.accept, source);
    send_ok(&own, BC_TRANSACTION, handles.accept, 200, TF_ACCEPT_FDS, values, 1);
    CHECK(close(source) == 0);
    int reused = open("/tmp/binder-fd-reused", O_RDWR | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    CHECK(reused == source && write(reused, "different-file", 14) == 14);
    completion(&own); reply = receive(&own);
    CHECK(reply.kind == BR_REPLY && reply.tr.code == 210);
    const struct binder_fd_object *returned = payload(&reply, 1);
    int retained = received_fd(&returned[0]);
    char tail[11]; CHECK(read(retained, tail, sizeof tail) == sizeof tail && !memcmp(tail, "object-file", sizeof tail));
    free_buffer(&own, reply.tr.data.ptr.buffer); CHECK(fcntl(retained, F_GETFD) >= 0);
    fd_objects(values, reused);
    send_ok(&own, BC_TRANSACTION, handles.accept, 201, 0, values, 1); completion(&own);
    reply = receive(&own); CHECK(reply.kind == BR_REPLY && reply.tr.code == 211 && reply.tr.data_size == 0);
    free_buffer(&own, reply.tr.data.ptr.buffer); CHECK(close(reused) == 0);
    int race = open("/tmp/binder-fd-race", O_RDWR | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    CHECK(race >= 0);
    unsigned char pattern[256];
    for (unsigned i = 0; i < sizeof pattern; ++i) pattern[i] = (unsigned char)(i ^ 0xa5);
    CHECK(write(race, pattern, sizeof pattern) == sizeof pattern && lseek(race, 0, SEEK_SET) == 0);
    for (unsigned i = 0; i < 128; ++i) {
        usleep(1000);
        fd_objects(values, race);
        send_ok(&own, BC_TRANSACTION, handles.accept, 300 + i, TF_ACCEPT_FDS, values, 1);
        completion(&own);
        reply = receive(&own);
        CHECK(reply.kind == BR_REPLY && reply.tr.code == 500 + i);
        returned = payload(&reply, 1);
        int received = received_fd(returned);
        unsigned char value = 0;
        CHECK(read(received, &value, 1) == 1 && value == (unsigned char)((2 * i + 1) ^ 0xa5));
        free_buffer(&own, reply.tr.data.ptr.buffer);
        CHECK(close(received) == 0);
    }
    CHECK(close(race) == 0);
    int pair[2]; CHECK(pipe(pair) == 0 && write(pair[1], "ABCD", 4) == 4);
    fd_objects(values, pair[0]);
    send_ok(&own, BC_TRANSACTION, handles.accept, 202, TF_ACCEPT_FDS, values, 2);
    CHECK(close(pair[0]) == 0); completion(&own);
    reply = receive(&own); CHECK(reply.kind == BR_REPLY && reply.tr.code == 212);
    returned = payload(&reply, 2);
    int first = received_fd(&returned[0]), second = received_fd(&returned[1]);
    CHECK(first != second);
    free_buffer(&own, reply.tr.data.ptr.buffer);
    char value = 0; CHECK(read(first, &value, 1) == 1 && value == 'C');
    CHECK(read(second, &value, 1) == 1 && value == 'D');
    CHECK(close(first) == 0 && close(second) == 0 && close(pair[1]) == 0);
    int pending[2]; CHECK(pipe(pending) == 0); fd_objects(values, pending[0]);
    send_ok(&own, BC_TRANSACTION, handles.accept, 203, 0, values, 1);
    CHECK(close(pending[0]) == 0); completion(&own);
    CHECK(receive(&own).kind == BR_DEAD_REPLY);
    await_byte(rollback_ready, 'r');
    // FD-slot refund was already checked before rollback_ready. Actual
    // FileLike destruction runs on its prebuilt task and may be scheduled
    // after that byte; require real EPIPE within a fixed bound, not in the
    // very first scheduling slice. Capture errno only for this actual write.
    struct timespec began, now; CHECK(clock_gettime(CLOCK_MONOTONIC, &began) == 0);
    ssize_t first_write = 0; int first_error = 0; unsigned attempts = 0;
    for (;;) {
        errno = 0;
        ssize_t written = write(pending[1], "Z", 1); int write_error = errno;
        if (attempts++ == 0) { first_write = written; first_error = write_error; }
        CHECK(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
        int64_t elapsed_ns = (int64_t)(now.tv_sec - began.tv_sec) * INT64_C(1000000000)
                           + now.tv_nsec - began.tv_nsec;
        if (written == -1 && write_error == EPIPE) {
            CHECK(elapsed_ns >= 0 && elapsed_ns < INT64_C(1000000000));
            printf("binder_fd_actual_cleanup_initial_rc=%zd_error=%d_EPIPE_elapsed_ns=%lld\tPASS\n",
                   first_write, first_error, (long long)elapsed_ns);
            break;
        }
        if (written != 1 || elapsed_ns >= INT64_C(1000000000))
            fprintf(stderr, "Binder actual pipe cleanup rc=%zd error=%d elapsed_ns=%lld\n",
                    written, write_error, (long long)elapsed_ns);
        CHECK(written == 1 && elapsed_ns < INT64_C(1000000000));
        usleep(1000);
    }
    CHECK(close(pending[1]) == 0);
    CHECK(ref_command(&own, BC_RELEASE, handles.accept) == 0 && ref_command(&own, BC_RELEASE, handles.deny) == 0);
    close_endpoint(&own);
    CHECK(lseek(retained, 0, SEEK_SET) == 0);
    char prefix[6]; CHECK(read(retained, prefix, sizeof prefix) == sizeof prefix && !memcmp(prefix, "source", sizeof prefix));
    CHECK(close(retained) == 0);
    printf("binder_fd_source_reuse_original_file_shared_offset_CLOEXEC_and_endpoint_independence\tPASS checks=%u\n", checks);
    _exit(0);
}
int main(void) {
    _Static_assert(sizeof(struct binder_fd_object) == 24, "Binder v8 FD object");
    _Static_assert(sizeof(struct flat_binder_object) == 24, "Binder v8 local object");
    signal(SIGALRM, alarmed); alarm(30); setbuf(stdout, NULL);
    struct endpoint manager = endpoint(); CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR, 0) == 0); enter(&manager);
    struct flat_binder_object ext = {.hdr.type = BINDER_TYPE_BINDER, .flags = FLAT_BINDER_FLAG_ACCEPTS_FDS};
    CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR_EXT, &ext) == -1 && errno == EOPNOTSUPP);
    int ready[2], control[2], rollback[2]; CHECK(pipe(ready) == 0 && pipe(control) == 0 && pipe(rollback) == 0);
    pid_t owner = fork(); CHECK(owner >= 0);
    if (!owner) owner_process(manager.fd, ready[1], control[0], rollback[1]);
    // The manager must not keep another reader of the later rollback pipe.
    struct message request = receive(&manager);
    CHECK(request.kind == BR_TRANSACTION && request.tr.code == 100 && request.tr.sender_pid == owner);
    struct handles handles = get_handles(&request);
    CHECK(ref_command(&manager, BC_ACQUIRE, handles.accept) == 0 && ref_command(&manager, BC_ACQUIRE, handles.deny) == 0);
    free_buffer(&manager, request.tr.data.ptr.buffer);
    struct flat_binder_object objects[2] = {
        {.hdr.type = BINDER_TYPE_HANDLE, .flags = FLAT_BINDER_FLAG_ACCEPTS_FDS, .handle = handles.accept},
        {.hdr.type = BINDER_TYPE_HANDLE, .handle = handles.deny},
    };
    send_ok(&manager, BC_REPLY, 0, 101, 0, objects, 2); completion(&manager); await_byte(ready[0], 'r');
    pid_t client = fork(); CHECK(client >= 0);
    if (!client) client_process(manager.fd, rollback[0]);
    request = receive(&manager);
    CHECK(request.kind == BR_TRANSACTION && request.tr.code == 110 && request.tr.sender_pid == client);
    free_buffer(&manager, request.tr.data.ptr.buffer);
    CHECK(write(control[1], &client, sizeof client) == sizeof client);
    send_ok(&manager, BC_REPLY, 0, 111, 0, objects, 2); completion(&manager);
    wait_child(client); byte(control[1], 'x'); wait_child(owner);
    no_messages(&manager);
    CHECK(ref_command(&manager, BC_RELEASE, handles.accept) == 0 && ref_command(&manager, BC_RELEASE, handles.deny) == 0);
    close_endpoint(&manager);
    CHECK(close(ready[0]) == 0 && close(ready[1]) == 0 && close(control[0]) == 0 && close(control[1]) == 0);
    CHECK(close(rollback[0]) == 0 && close(rollback[1]) == 0);
    printf("{\"passed\":true,\"checks\":%u,\"scope\":\"bounded_binder_FD_real_installation_rollback\",\"fd_array\":false,\"thread_pool\":false,\"android_boot\":false}\n", checks);
    return 0;
}
