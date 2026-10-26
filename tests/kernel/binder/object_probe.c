// SPDX-License-Identifier: MPL-2.0
// Real Binder v8 object/handle IPC in an ordinary, isolated guest.
// Compile on the host, but never execute this probe there.
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
#include <sys/wait.h>
#include <unistd.h>

#define MAP_BYTES (16u * 4096u)
#define OBJECT_COUNT 4u
#define PRIMARY_PTR UINT64_C(0x10001000)
#define PRIMARY_COOKIE UINT64_C(0x1234abcdeffedcba)
#define EPHEMERAL_PTR UINT64_C(0x10002000)
#define EPHEMERAL_COOKIE UINT64_C(0x2345bcdef00fedcb)
#define WEAK_PTR UINT64_C(0x10003000)
#define WEAK_COOKIE UINT64_C(0x3456cdef0120fedc)

static unsigned checks;
static const char *role = "manager";
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "Binder objects FAIL role=%s line=%d: %s errno=%d\n", role, __LINE__, #x, errno); exit(1); } ++checks; } while (0)
struct reference_state {
    binder_uintptr_t pointer, cookie;
    unsigned increfs, acquires, releases, decrefs;
    int weak, strong;
};
struct endpoint {
    int fd;
    void *mapping;
    struct reference_state references[3];
};
struct message {
    uint32_t kind;
    struct binder_transaction_data transaction;
};
struct handles {
    uint32_t primary, ephemeral, weak;
};
static void no_messages(struct endpoint *e);
static void alarmed(int sig) { (void)sig; _exit(124); }
static void byte(int fd, char value) { CHECK(write(fd, &value, 1) == 1); }
static void await_byte(int fd, char expected) {
    char value = 0;
    CHECK(read(fd, &value, 1) == 1 && value == expected);
}
static void wait_child(pid_t pid) {
    int status = 0;
    CHECK(waitpid(pid, &status, 0) == pid);
    CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
}
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
    unsigned threads = 1;
    CHECK(ioctl(e.fd, BINDER_SET_MAX_THREADS, &threads) == 0);
    e.mapping = mmap(NULL, MAP_BYTES, PROT_READ, MAP_PRIVATE, e.fd, 0);
    CHECK(e.mapping != MAP_FAILED);
    e.references[0] = (struct reference_state){.pointer = PRIMARY_PTR, .cookie = PRIMARY_COOKIE};
    e.references[1] = (struct reference_state){.pointer = EPHEMERAL_PTR, .cookie = EPHEMERAL_COOKIE};
    e.references[2] = (struct reference_state){.pointer = WEAK_PTR, .cookie = WEAK_COOKIE};
    return e;
}
static void close_endpoint(struct endpoint *e) {
    CHECK(munmap(e->mapping, MAP_BYTES) == 0);
    CHECK(close(e->fd) == 0);
    e->fd = -1;
}
static void enter(int fd) {
    uint32_t command = BC_ENTER_LOOPER;
    CHECK(commands(fd, &command, sizeof command, NULL) == 0);
}
static int ref_command(int fd, uint32_t kind, uint32_t handle) {
    unsigned char stream[8];
    memcpy(stream, &kind, 4);
    memcpy(stream + 4, &handle, 4);
    return commands(fd, stream, sizeof stream, NULL);
}
static int ref_done(int fd, uint32_t kind, const struct binder_ptr_cookie *object) {
    unsigned char stream[20];
    memcpy(stream, &kind, 4);
    memcpy(stream + 4, object, sizeof *object);
    return commands(fd, stream, sizeof stream, NULL);
}
static int reference_event(struct endpoint *e, uint32_t kind,
                           const unsigned char *bytes, uint64_t size) {
    if (kind != BR_INCREFS && kind != BR_ACQUIRE && kind != BR_RELEASE && kind != BR_DECREFS)
        return 0;
    CHECK(size == 20);
    struct binder_ptr_cookie object;
    memcpy(&object, bytes + 4, sizeof object);
    struct reference_state *state = NULL;
    for (unsigned i = 0; i < 3; ++i)
        if (e->references[i].pointer == object.ptr && e->references[i].cookie == object.cookie)
            state = &e->references[i];
    CHECK(state != NULL);
    if (kind == BR_INCREFS) {
        CHECK(!state->weak && !state->strong);
        state->weak = 1;
        ++state->increfs;
        CHECK(ref_done(e->fd, BC_INCREFS_DONE, &object) == 0);
    } else if (kind == BR_ACQUIRE) {
        CHECK(state->weak && !state->strong);
        state->strong = 1;
        ++state->acquires;
        CHECK(ref_done(e->fd, BC_ACQUIRE_DONE, &object) == 0);
    } else if (kind == BR_RELEASE) {
        CHECK(state->weak && state->strong);
        state->strong = 0;
        ++state->releases;
    } else {
        CHECK(state->weak && !state->strong);
        state->weak = 0;
        ++state->decrefs;
    }
    return 1;
}
static struct message receive(struct endpoint *e) {
    for (;;) {
        unsigned char bytes[128] = {0};
        uint64_t consumed = 0;
        CHECK(read_bytes(e->fd, bytes, sizeof bytes, &consumed) == 0 && consumed >= 4);
        struct message result = {0};
        memcpy(&result.kind, bytes, 4);
        if (reference_event(e, result.kind, bytes, consumed)) continue;
        if (result.kind == BR_TRANSACTION || result.kind == BR_REPLY) {
            CHECK(consumed == 68);
            memcpy(&result.transaction, bytes + 4, sizeof result.transaction);
        } else CHECK(consumed == 4);
        return result;
    }
}
static void completion(struct endpoint *e) {
    CHECK(receive(e).kind == BR_TRANSACTION_COMPLETE);
}
static int send_raw(int fd, uint32_t kind, const struct binder_transaction_data *transaction,
                    uint64_t *consumed) {
    unsigned char stream[68];
    memcpy(stream, &kind, 4);
    memcpy(stream + 4, transaction, sizeof *transaction);
    return commands(fd, stream, sizeof stream, consumed);
}
static void send_data(int fd, uint32_t kind, uint32_t target, uint32_t code,
                      const void *data, size_t size) {
    struct binder_transaction_data tr = {
        .target.handle = target, .code = code, .data_size = size,
        .data.ptr.buffer = (uintptr_t)data,
    };
    uint64_t consumed = 0;
    CHECK(send_raw(fd, kind, &tr, &consumed) == 0 && consumed == 68);
}
static int send_objects_raw(int fd, uint32_t kind, uint32_t target, uint32_t code,
                            const struct flat_binder_object *objects, size_t count,
                            const binder_size_t *offsets, size_t offset_bytes,
                            uint64_t *consumed) {
    struct binder_transaction_data tr = {
        .target.handle = target, .code = code,
        .data_size = count * sizeof *objects, .offsets_size = offset_bytes,
        .data.ptr.buffer = (uintptr_t)objects, .data.ptr.offsets = (uintptr_t)offsets,
    };
    return send_raw(fd, kind, &tr, consumed);
}
static void send_objects(int fd, uint32_t kind, uint32_t target, uint32_t code,
                         const struct flat_binder_object *objects, size_t count) {
    binder_size_t offsets[OBJECT_COUNT];
    CHECK(count <= OBJECT_COUNT);
    for (size_t i = 0; i < count; ++i) offsets[i] = i * sizeof *objects;
    uint64_t consumed = 0;
    CHECK(send_objects_raw(fd, kind, target, code, objects, count, offsets,
                           count * sizeof *offsets, &consumed) == 0 && consumed == 68);
}
static void free_buffer(struct endpoint *e, binder_uintptr_t address) {
    unsigned char stream[12];
    uint32_t kind = BC_FREE_BUFFER;
    memcpy(stream, &kind, 4);
    memcpy(stream + 4, &address, sizeof address);
    CHECK(commands(e->fd, stream, sizeof stream, NULL) == 0);
    CHECK(commands(e->fd, stream, sizeof stream, NULL) == -1 && errno == EINVAL);
}
static const struct flat_binder_object *objects(const struct message *message,
                                               size_t count) {
    const struct binder_transaction_data *tr = &message->transaction;
    CHECK(tr->data_size == count * sizeof(struct flat_binder_object));
    CHECK(tr->offsets_size == count * sizeof(binder_size_t));
    CHECK(tr->data.ptr.offsets == tr->data.ptr.buffer + ((tr->data_size + 7) & ~7u));
    const binder_size_t *offsets = (const void *)(uintptr_t)tr->data.ptr.offsets;
    for (size_t i = 0; i < count; ++i) CHECK(offsets[i] == i * sizeof(struct flat_binder_object));
    return (const void *)(uintptr_t)tr->data.ptr.buffer;
}
static struct handles foreign_objects(const struct message *message) {
    const struct flat_binder_object *value = objects(message, OBJECT_COUNT);
    CHECK(value[0].hdr.type == BINDER_TYPE_HANDLE && value[0].handle != 0);
    CHECK(value[1].hdr.type == BINDER_TYPE_WEAK_HANDLE && value[1].handle == value[0].handle);
    CHECK(value[2].hdr.type == BINDER_TYPE_HANDLE && value[2].handle != value[0].handle);
    CHECK(value[3].hdr.type == BINDER_TYPE_WEAK_HANDLE && value[3].handle != value[0].handle);
    CHECK(value[3].handle != value[2].handle);
    for (unsigned i = 0; i < OBJECT_COUNT; ++i)
        CHECK(value[i].flags == 0 && value[i].cookie == 0 && (value[i].binder >> 32) == 0);
    return (struct handles){value[0].handle, value[2].handle, value[3].handle};
}
static void handle_objects(struct flat_binder_object *value, struct handles handles) {
    value[0] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_HANDLE, .handle = handles.primary};
    value[1] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_WEAK_HANDLE, .handle = handles.primary};
    value[2] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_HANDLE, .handle = handles.ephemeral};
    value[3] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_WEAK_HANDLE, .handle = handles.weak};
}
static void local_objects(struct flat_binder_object *value) {
    value[0] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_BINDER, .binder = PRIMARY_PTR, .cookie = PRIMARY_COOKIE};
    value[1] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_WEAK_BINDER, .binder = PRIMARY_PTR, .cookie = PRIMARY_COOKIE};
    value[2] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_BINDER, .binder = EPHEMERAL_PTR, .cookie = EPHEMERAL_COOKIE};
    value[3] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_WEAK_BINDER, .binder = WEAK_PTR, .cookie = WEAK_COOKIE};
}
static void reject_transaction(int fd, const struct binder_transaction_data *tr, int expected) {
    uint64_t consumed = 99;
    CHECK(send_raw(fd, BC_TRANSACTION, tr, &consumed) == -1 && errno == expected && consumed == 0);
}
static void invalid_objects(struct endpoint *e) {
    struct flat_binder_object value = {.hdr.type = BINDER_TYPE_HANDLE, .handle = 0x7ffffffe};
    binder_size_t offsets[2] = {0, 0};
    struct binder_transaction_data tr = {
        .data_size = sizeof value, .offsets_size = sizeof(binder_size_t),
        .data.ptr.buffer = (uintptr_t)&value, .data.ptr.offsets = (uintptr_t)offsets,
    };
    reject_transaction(e->fd, &tr, EINVAL); // Unknown source handle, no publication.
    tr.offsets_size = 1;
    reject_transaction(e->fd, &tr, EINVAL);
    tr.offsets_size = sizeof(binder_size_t);
    offsets[0] = 1;
    reject_transaction(e->fd, &tr, EINVAL);
    offsets[0] = 0;
    tr.data_size = sizeof value - 1;
    reject_transaction(e->fd, &tr, EINVAL);
    tr.data_size = sizeof value;
    tr.offsets_size = sizeof offsets;
    reject_transaction(e->fd, &tr, EINVAL); // Overlapping object descriptors.
    tr = (struct binder_transaction_data){.target.handle = 0x7ffffffe};
    reject_transaction(e->fd, &tr, EINVAL);
    CHECK(ref_command(e->fd, BC_ACQUIRE, 0x7ffffffe) == -1 && errno == EINVAL);
    CHECK(ref_command(e->fd, BC_INCREFS, 0x7ffffffe) == -1 && errno == EINVAL);
    CHECK(ref_command(e->fd, BC_RELEASE, 0x7ffffffe) == -1 && errno == EINVAL);
    CHECK(ref_command(e->fd, BC_DECREFS, 0x7ffffffe) == -1 && errno == EINVAL);
    struct binder_ptr_cookie wrong = {.ptr = PRIMARY_PTR, .cookie = PRIMARY_COOKIE};
    CHECK(ref_done(e->fd, BC_INCREFS_DONE, &wrong) == -1 && errno == EINVAL);
    CHECK(ref_done(e->fd, BC_ACQUIRE_DONE, &wrong) == -1 && errno == EINVAL);
    // A valid first object cannot consume a node slot if a later descriptor
    // fails. Distinct pointers exceed the 16-node owner cap if publication leaks.
    struct flat_binder_object batch[2] = {
        {.hdr.type = BINDER_TYPE_BINDER, .cookie = UINT64_C(0xfeed1000)},
        {.hdr.type = BINDER_TYPE_HANDLE, .handle = 0x7ffffffe},
    };
    binder_size_t batch_offsets[2] = {0, sizeof(struct flat_binder_object)};
    for (unsigned i = 0; i < 40; ++i) {
        batch[0].binder = UINT64_C(0x20000000) + 4096 * i;
        uint64_t consumed = 99;
        CHECK(send_objects_raw(e->fd, BC_TRANSACTION, 0, 99, batch, 2,
                               batch_offsets, sizeof batch_offsets, &consumed) == -1
              && errno == EINVAL && consumed == 0);
        no_messages(e);
    }
}
static void verify_local(const struct flat_binder_object *value, size_t count) {
    CHECK(count >= 1);
    CHECK(value[0].hdr.type == BINDER_TYPE_BINDER && value[0].binder == PRIMARY_PTR && value[0].cookie == PRIMARY_COOKIE);
    CHECK(value[0].flags == 0);
    if (count >= 2)
        CHECK(value[1].hdr.type == BINDER_TYPE_WEAK_BINDER && value[1].binder == PRIMARY_PTR && value[1].cookie == PRIMARY_COOKIE);
}
static void owner_process(int inherited, int notify, int control) {
    role = "owner";
    alarm(25);
    CHECK(close(inherited) == 0);
    struct endpoint own = endpoint();
    enter(own.fd);
    struct flat_binder_object value[OBJECT_COUNT];
    local_objects(value);
    send_objects(own.fd, BC_TRANSACTION, 0, 10, value, OBJECT_COUNT);
    completion(&own);
    struct message reply = receive(&own);
    CHECK(reply.kind == BR_REPLY && reply.transaction.code == 11);
    free_buffer(&own, reply.transaction.data.ptr.buffer);
    // Existing node identity cannot be relabelled by an owner cookie change.
    value[0].cookie ^= 1;
    binder_size_t offset = 0;
    uint64_t consumed = 99;
    CHECK(send_objects_raw(own.fd, BC_TRANSACTION, 0, 12, value, 1, &offset,
                           sizeof offset, &consumed) == -1 && errno == EINVAL && consumed == 0);
    byte(notify, 'r');
    pid_t client = 0;
    CHECK(read(control, &client, sizeof client) == sizeof client && client > 0);
    for (unsigned call = 0; call < 2; ++call) {
        struct message request = receive(&own);
        CHECK(request.kind == BR_TRANSACTION && request.transaction.code == 30 + call);
        CHECK(request.transaction.target.ptr == PRIMARY_PTR && request.transaction.cookie == PRIMARY_COOKIE);
        CHECK(request.transaction.sender_pid == client && request.transaction.sender_euid == 0);
        verify_local(objects(&request, 1), 1);
        free_buffer(&own, request.transaction.data.ptr.buffer);
        char result[] = "object-call-0";
        result[12] = (char)('0' + call);
        send_data(own.fd, BC_REPLY, 0, 40 + call, result, sizeof result);
        completion(&own);
    }
    send_data(own.fd, BC_TRANSACTION, 0, 50, NULL, 0);
    completion(&own);
    reply = receive(&own);
    CHECK(reply.kind == BR_REPLY && reply.transaction.code == 51);
    verify_local(objects(&reply, 2), 2);
    free_buffer(&own, reply.transaction.data.ptr.buffer);
    CHECK(own.references[0].increfs == 1 && own.references[0].acquires == 1);
    CHECK(own.references[1].increfs == 1 && own.references[1].acquires == 1);
    CHECK(own.references[2].increfs == 1 && own.references[2].acquires == 0);
    byte(notify, 's');
    await_byte(control, 'r');
    // Manager and client have now dropped the last references to the other
    // two nodes. Consume actual owner work, without manufacturing acknowledgments.
    while (!own.references[1].decrefs || !own.references[2].decrefs) {
        unsigned char bytes[128] = {0};
        uint64_t size = 0;
        CHECK(read_bytes(own.fd, bytes, sizeof bytes, &size) == 0 && size >= 4);
        uint32_t kind = 0;
        memcpy(&kind, bytes, 4);
        CHECK(reference_event(&own, kind, bytes, size));
    }
    CHECK(own.references[1].releases == 1 && !own.references[1].strong && !own.references[1].weak);
    CHECK(own.references[2].releases == 0 && !own.references[2].weak);
    struct binder_ptr_cookie done = {.ptr = PRIMARY_PTR, .cookie = PRIMARY_COOKIE};
    CHECK(ref_done(own.fd, BC_INCREFS_DONE, &done) == -1 && errno == EINVAL);
    CHECK(ref_done(own.fd, BC_ACQUIRE_DONE, &done) == -1 && errno == EINVAL);
    byte(notify, 'd');
    await_byte(control, 'x');
    close_endpoint(&own);
    printf("binder_objects_owner_identity_reference_work_cleanup\tPASS checks=%u\n", checks);
    _exit(0);
}
static void client_call(struct endpoint *own, uint32_t handle, unsigned call) {
    struct flat_binder_object object = {.hdr.type = BINDER_TYPE_HANDLE, .handle = handle};
    send_objects(own->fd, BC_TRANSACTION, handle, 30 + call, &object, 1);
    completion(own);
    struct message reply = receive(own);
    CHECK(reply.kind == BR_REPLY && reply.transaction.code == 40 + call);
    CHECK(reply.transaction.sender_pid == 0 && reply.transaction.sender_euid == 0);
    char expected[] = "object-call-0";
    expected[12] = (char)('0' + call);
    CHECK(reply.transaction.data_size == sizeof expected);
    CHECK(memcmp((const void *)(uintptr_t)reply.transaction.data.ptr.buffer, expected, sizeof expected) == 0);
    free_buffer(own, reply.transaction.data.ptr.buffer);
}
static void client_process(int inherited, int notify, int control) {
    role = "client";
    alarm(25);
    CHECK(close(inherited) == 0);
    struct endpoint own = endpoint();
    invalid_objects(&own);
    send_data(own.fd, BC_TRANSACTION, 0, 20, NULL, 0);
    completion(&own);
    uint64_t consumed = 99;
    CHECK(read_bytes(own.fd, (void *)1, 128, &consumed) == -1 && errno == EFAULT && consumed == 0);
    CHECK(ref_command(own.fd, BC_ACQUIRE, 0x7ffffffe) == -1 && errno == EBUSY);
    struct message reply = receive(&own);
    CHECK(reply.kind == BR_REPLY && reply.transaction.code == 21);
    struct handles handles = foreign_objects(&reply);
    struct binder_transaction_data bad = {.target.handle = handles.weak};
    reject_transaction(own.fd, &bad, EINVAL); // A weak buffer reference is not callable.
    CHECK(ref_command(own.fd, BC_ACQUIRE, handles.weak) == -1 && errno == EINVAL);
    CHECK(ref_command(own.fd, BC_RELEASE, handles.primary) == -1 && errno == EINVAL);
    CHECK(ref_command(own.fd, BC_DECREFS, handles.primary) == -1 && errno == EINVAL);
    client_call(&own, handles.primary, 0); // The live received buffer owns this reference.
    CHECK(ref_command(own.fd, BC_ACQUIRE, handles.primary) == 0);
    CHECK(ref_command(own.fd, BC_INCREFS, handles.primary) == 0);
    CHECK(ref_command(own.fd, BC_INCREFS, handles.weak) == 0);
    free_buffer(&own, reply.transaction.data.ptr.buffer);
    bad.target.handle = handles.ephemeral;
    reject_transaction(own.fd, &bad, EINVAL); // No retained reference survives FREE_BUFFER.
    bad.target.handle = handles.weak;
    reject_transaction(own.fd, &bad, EINVAL);
    CHECK(ref_command(own.fd, BC_DECREFS, handles.weak) == 0);
    CHECK(ref_command(own.fd, BC_DECREFS, handles.weak) == -1 && errno == EINVAL);
    client_call(&own, handles.primary, 1); // Explicit user reference survives FREE_BUFFER.
    byte(notify, 'd');
    await_byte(control, 'x');
    // The same numeric handle still names the dead original owner. It must
    // never route to a later context manager or another endpoint incarnation.
    send_data(own.fd, BC_TRANSACTION, handles.primary, 70, NULL, 0);
    completion(&own);
    CHECK(receive(&own).kind == BR_DEAD_REPLY);
    CHECK(ref_command(own.fd, BC_RELEASE, handles.primary) == 0);
    CHECK(ref_command(own.fd, BC_DECREFS, handles.primary) == 0);
    CHECK(ref_command(own.fd, BC_RELEASE, handles.primary) == -1 && errno == EINVAL);
    close_endpoint(&own);
    printf("binder_objects_third_process_buffer_user_refs_weak_denial_dead_owner\tPASS checks=%u\n", checks);
    _exit(0);
}
static void no_messages(struct endpoint *e) {
    int flags = fcntl(e->fd, F_GETFL);
    CHECK(flags >= 0 && fcntl(e->fd, F_SETFL, flags | O_NONBLOCK) == 0);
    unsigned char bytes[128];
    CHECK(read_bytes(e->fd, bytes, sizeof bytes, NULL) == -1 && errno == EAGAIN);
    CHECK(fcntl(e->fd, F_SETFL, flags) == 0);
}
static void object_roundtrip(void) {
    struct endpoint manager = endpoint();
    CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR, 0) == 0);
    enter(manager.fd);
    struct endpoint malformed = endpoint();
    invalid_objects(&malformed);
    close_endpoint(&malformed);
    int owner_notify[2], owner_control[2], client_notify[2], client_control[2];
    CHECK(pipe(owner_notify) == 0 && pipe(owner_control) == 0);
    CHECK(pipe(client_notify) == 0 && pipe(client_control) == 0);
    pid_t owner = fork();
    CHECK(owner >= 0);
    if (!owner) owner_process(manager.fd, owner_notify[1], owner_control[0]);
    struct message registration = receive(&manager);
    CHECK(registration.kind == BR_TRANSACTION && registration.transaction.code == 10);
    CHECK(registration.transaction.sender_pid == owner && registration.transaction.sender_euid == 0);
    struct handles handles = foreign_objects(&registration);
    CHECK(ref_command(manager.fd, BC_ACQUIRE, handles.primary) == 0);
    CHECK(ref_command(manager.fd, BC_INCREFS, handles.primary) == 0);
    CHECK(ref_command(manager.fd, BC_ACQUIRE, handles.ephemeral) == 0);
    CHECK(ref_command(manager.fd, BC_INCREFS, handles.weak) == 0);
    free_buffer(&manager, registration.transaction.data.ptr.buffer);
    send_data(manager.fd, BC_REPLY, 0, 11, NULL, 0);
    completion(&manager);
    await_byte(owner_notify[0], 'r');
    no_messages(&manager); // Rejected cookie change has no queued side effect.
    pid_t client = fork();
    CHECK(client >= 0);
    if (!client) client_process(manager.fd, client_notify[1], client_control[0]);
    struct message request = receive(&manager);
    CHECK(request.kind == BR_TRANSACTION && request.transaction.code == 20);
    CHECK(request.transaction.sender_pid == client);
    free_buffer(&manager, request.transaction.data.ptr.buffer);
    CHECK(write(owner_control[1], &client, sizeof client) == sizeof client);
    struct flat_binder_object value[OBJECT_COUNT];
    handle_objects(value, handles);
    send_objects(manager.fd, BC_REPLY, 0, 21, value, OBJECT_COUNT);
    completion(&manager);
    request = receive(&manager);
    CHECK(request.kind == BR_TRANSACTION && request.transaction.code == 50);
    CHECK(request.transaction.sender_pid == owner);
    free_buffer(&manager, request.transaction.data.ptr.buffer);
    send_objects(manager.fd, BC_REPLY, 0, 51, value, 2);
    completion(&manager);
    await_byte(owner_notify[0], 's');
    await_byte(client_notify[0], 'd');
    CHECK(ref_command(manager.fd, BC_RELEASE, handles.ephemeral) == 0);
    CHECK(ref_command(manager.fd, BC_DECREFS, handles.weak) == 0);
    byte(owner_control[1], 'r');
    await_byte(owner_notify[0], 'd');
    byte(owner_control[1], 'x');
    wait_child(owner);
    // Allocate another real endpoint after the owner has died. Its allocation
    // cannot change the old node's identity or make the client's handle callable.
    struct endpoint replacement = endpoint();
    enter(replacement.fd);
    byte(client_control[1], 'x');
    wait_child(client);
    no_messages(&replacement);
    CHECK(ref_command(manager.fd, BC_RELEASE, handles.primary) == 0);
    CHECK(ref_command(manager.fd, BC_DECREFS, handles.primary) == 0);
    close_endpoint(&replacement);
    no_messages(&manager);
    close_endpoint(&manager);
    CHECK(close(owner_notify[0]) == 0 && close(owner_notify[1]) == 0);
    CHECK(close(owner_control[0]) == 0 && close(owner_control[1]) == 0);
    CHECK(close(client_notify[0]) == 0 && close(client_notify[1]) == 0);
    CHECK(close(client_control[0]) == 0 && close(client_control[1]) == 0);
    puts("binder_objects_three_process_forward_return_and_no_identity_reuse\tPASS");
}
static uint32_t one_handle(const struct message *message) {
    const struct flat_binder_object *value = objects(message, 1);
    CHECK(value[0].hdr.type == BINDER_TYPE_HANDLE && value[0].handle != 0);
    CHECK(value[0].cookie == 0 && value[0].flags == 0 && (value[0].binder >> 32) == 0);
    return value[0].handle;
}
static void export_primary(struct endpoint *e, uint32_t code) {
    struct flat_binder_object object = {
        .hdr.type = BINDER_TYPE_BINDER, .binder = PRIMARY_PTR, .cookie = PRIMARY_COOKIE,
    };
    send_objects(e->fd, BC_TRANSACTION, 0, code, &object, 1);
    completion(e);
}
static void expect_dead_call(struct endpoint *e, uint32_t handle) {
    send_data(e->fd, BC_TRANSACTION, handle, 1070, NULL, 0);
    completion(e);
    CHECK(receive(e).kind == BR_DEAD_REPLY);
}
static int exec_owner(int fd, int notify, int control) {
    role = "exec-owner";
    struct binder_version version = {0};
    CHECK(ioctl(fd, BINDER_VERSION, &version) == -1 && errno == EPERM);
    CHECK(close(fd) == 0);
    struct endpoint replacement = endpoint();
    enter(replacement.fd);
    no_messages(&replacement);
    byte(notify, 'e');
    await_byte(control, 'x');
    no_messages(&replacement);
    close_endpoint(&replacement);
    printf("binder_objects_exec_old_fd_denial_new_endpoint_no_inheritance\tPASS checks=%u\n", checks);
    return 0;
}
static void exec_lifecycle(void) {
    struct endpoint manager = endpoint();
    CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR, 0) == 0);
    enter(manager.fd);
    int notify[2], control[2];
    CHECK(pipe(notify) == 0 && pipe(control) == 0);
    pid_t child = fork();
    CHECK(child >= 0);
    if (!child) {
        role = "before-exec-owner";
        alarm(25);
        CHECK(close(manager.fd) == 0);
        struct endpoint own = endpoint();
        enter(own.fd);
        CHECK(fcntl(own.fd, F_SETFD, 0) == 0);
        export_primary(&own, 1000);
        struct message reply = receive(&own);
        CHECK(reply.kind == BR_REPLY && reply.transaction.code == 1001);
        free_buffer(&own, reply.transaction.data.ptr.buffer);
        char fd[24], signal_fd[24], control_fd[24];
        snprintf(fd, sizeof fd, "%d", own.fd);
        snprintf(signal_fd, sizeof signal_fd, "%d", notify[1]);
        snprintf(control_fd, sizeof control_fd, "%d", control[0]);
        execl("/bin/safety-binder_objects", "safety-binder_objects", "--exec-owner",
              fd, signal_fd, control_fd, (char *)NULL);
        _exit(98);
    }
    struct message registration = receive(&manager);
    CHECK(registration.kind == BR_TRANSACTION && registration.transaction.code == 1000);
    CHECK(registration.transaction.sender_pid == child);
    uint32_t handle = one_handle(&registration);
    CHECK(ref_command(manager.fd, BC_ACQUIRE, handle) == 0);
    free_buffer(&manager, registration.transaction.data.ptr.buffer);
    send_data(manager.fd, BC_REPLY, 0, 1001, NULL, 0);
    completion(&manager);
    await_byte(notify[0], 'e');
    expect_dead_call(&manager, handle);
    byte(control[1], 'x');
    wait_child(child);
    CHECK(ref_command(manager.fd, BC_RELEASE, handle) == 0);
    no_messages(&manager);
    close_endpoint(&manager);
    CHECK(close(notify[0]) == 0 && close(notify[1]) == 0);
    CHECK(close(control[0]) == 0 && close(control[1]) == 0);
    puts("binder_objects_successful_exec_retires_old_exported_owner\tPASS");
}
static void prepared_owner_killed(void) {
    struct endpoint manager = endpoint();
    CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR, 0) == 0);
    enter(manager.fd);
    int notify[2];
    CHECK(pipe(notify) == 0);
    pid_t child = fork();
    CHECK(child >= 0);
    if (!child) {
        role = "prepared-object-owner";
        alarm(25);
        CHECK(close(manager.fd) == 0);
        struct endpoint own = endpoint();
        enter(own.fd);
        export_primary(&own, 1100);
        byte(notify[1], 'r');
        for (;;) pause();
    }
    await_byte(notify[0], 'r');
    uint64_t consumed = 99;
    CHECK(read_bytes(manager.fd, (void *)1, 128, &consumed) == -1 && errno == EFAULT && consumed == 0);
    CHECK(kill(child, SIGKILL) == 0);
    int status = 0;
    CHECK(waitpid(child, &status, 0) == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL);
    struct message request = receive(&manager);
    CHECK(request.kind == BR_TRANSACTION && request.transaction.code == 1100);
    CHECK(request.transaction.sender_pid == child);
    uint32_t handle = one_handle(&request);
    struct binder_transaction_data reply = {0};
    consumed = 99;
    CHECK(send_raw(manager.fd, BC_REPLY, &reply, &consumed) == -1 && errno == EINVAL && consumed == 0);
    // Prepared copyout retains the same actual object contribution even after
    // the sender/owner dies. Its live buffer still resolves the original node.
    expect_dead_call(&manager, handle);
    free_buffer(&manager, request.transaction.data.ptr.buffer);
    struct binder_transaction_data bad = {.target.handle = handle};
    reject_transaction(manager.fd, &bad, EINVAL);
    no_messages(&manager);
    close_endpoint(&manager);
    CHECK(close(notify[0]) == 0 && close(notify[1]) == 0);
    puts("binder_objects_prepared_EFAULT_SIGKILL_keeps_actual_node_until_FREE\tPASS");
}
int main(int argc, char **argv) {
    _Static_assert(sizeof(struct flat_binder_object) == 24, "64-bit Binder object layout");
    _Static_assert(sizeof(struct binder_transaction_data) == 64, "64-bit Binder transaction layout");
    _Static_assert(sizeof(struct binder_ptr_cookie) == 16, "64-bit Binder owner acknowledgment layout");
    signal(SIGALRM, alarmed);
    alarm(30);
    setbuf(stdout, NULL);
    if (argc == 5 && !strcmp(argv[1], "--exec-owner"))
        return exec_owner(atoi(argv[2]), atoi(argv[3]), atoi(argv[4]));
    CHECK(argc == 1);
    object_roundtrip();
    exec_lifecycle();
    prepared_owner_killed();
    printf("{\"passed\":true,\"checks\":%u,\"scope\":\"synchronous_binder_objects_handles\",\"fd_transfer\":false,\"thread_pool\":false,\"android_boot\":false}\n", checks);
    return 0;
}
