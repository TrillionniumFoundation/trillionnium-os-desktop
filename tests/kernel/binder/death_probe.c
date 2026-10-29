// SPDX-License-Identifier: MPL-2.0
// Actual multi-process Binder death subscriptions; guest-only.
#define main binder_transfer_fixture_main
#include "fd_probe.c"
#undef main
#include <poll.h>

static int death_command(struct endpoint *e, uint32_t command, uint32_t handle, uint64_t cookie) {
    unsigned char bytes[16]; memcpy(bytes, &command, 4); memcpy(bytes + 4, &handle, 4); memcpy(bytes + 8, &cookie, 8);
    return commands(e->fd, bytes, sizeof bytes, NULL);
}
static int death_done(struct endpoint *e, uint64_t cookie) {
    uint32_t command = BC_DEAD_BINDER_DONE; unsigned char bytes[12];
    memcpy(bytes, &command, 4); memcpy(bytes + 4, &cookie, 8);
    return commands(e->fd, bytes, sizeof bytes, NULL);
}
static void death_read(struct endpoint *e, uint32_t expected, uint64_t cookie) {
    unsigned char bytes[128] = {0}; uint64_t size = 0, actual = 0; uint32_t kind = 0;
    CHECK(read_bytes(e->fd, bytes, sizeof bytes, &size) == 0 && size == 12);
    memcpy(&kind, bytes, 4); memcpy(&actual, bytes + 4, 8);
    CHECK(kind == expected && actual == cookie);
}
static void remote_objects(struct flat_binder_object values[2], struct handles h) {
    values[0] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_HANDLE,
        .flags = FLAT_BINDER_FLAG_ACCEPTS_FDS, .handle = h.accept};
    values[1] = (struct flat_binder_object){.hdr.type = BINDER_TYPE_HANDLE, .handle = h.deny};
}
struct subscriber { struct endpoint e; uint32_t handle; binder_uintptr_t buffer; int retained; };
static struct subscriber subscribe_endpoint(struct endpoint *manager, struct handles h, int retain) {
    struct subscriber s = {.e = endpoint(), .retained = retain};
    send_ok(&s.e, BC_TRANSACTION, 0, 110, 0, NULL, 0); completion(&s.e);
    struct message request = receive(manager); CHECK(request.kind == BR_TRANSACTION && request.tr.code == 110);
    free_buffer(manager, request.tr.data.ptr.buffer);
    struct flat_binder_object values[2]; remote_objects(values, h);
    send_ok(manager, BC_REPLY, 0, 111, 0, values, 1); completion(manager);
    struct message reply = receive(&s.e); CHECK(reply.kind == BR_REPLY && reply.tr.code == 111);
    const struct flat_binder_object *value = payload(&reply, 1);
    CHECK(value->hdr.type == BINDER_TYPE_HANDLE && value->handle != 0);
    s.handle = value->handle; s.buffer = reply.tr.data.ptr.buffer;
    if (retain) { CHECK(ref_command(&s.e, BC_ACQUIRE, s.handle) == 0); free_buffer(&s.e, s.buffer); s.buffer = 0; }
    return s;
}
static void release_subscriber(struct subscriber *s) {
    if (s->retained) CHECK(ref_command(&s->e, BC_RELEASE, s->handle) == 0);
    else if (s->buffer) free_buffer(&s->e, s->buffer);
    close_endpoint(&s->e);
}
static struct handles owner_registration_reply(struct endpoint *manager) {
    struct message request = receive(manager); CHECK(request.kind == BR_TRANSACTION && request.tr.code == 100);
    struct handles h = get_handles(&request);
    CHECK(ref_command(manager, BC_ACQUIRE, h.accept) == 0 && ref_command(manager, BC_ACQUIRE, h.deny) == 0);
    free_buffer(manager, request.tr.data.ptr.buffer);
    struct flat_binder_object values[2]; remote_objects(values, h);
    send_ok(manager, BC_REPLY, 0, 101, 0, values, 2); completion(manager);
    return h;
}
static void child_owner(int inherited, int control, int notify, int exec_image) {
    role = "death-owner"; CHECK(close(inherited) == 0);
    struct endpoint own = endpoint(); enter(&own);
    if (exec_image) CHECK(fcntl(own.fd, F_SETFD, 0) == 0);
    owner_registration(&own); byte(notify, 'r');
    await_byte(control, exec_image ? 'e' : 'q');
    if (exec_image) {
        char fd[24], to_parent[24], from_parent[24];
        snprintf(fd, sizeof fd, "%d", own.fd); snprintf(to_parent, sizeof to_parent, "%d", notify);
        snprintf(from_parent, sizeof from_parent, "%d", control);
        execl("/bin/safety-binder_death", "safety-binder_death", "--exec-fd", fd, to_parent, from_parent, (char *)NULL);
        CHECK(0);
    }
    close_endpoint(&own); _exit(0);
}
static void killed(pid_t child) {
    int status = 0; CHECK(kill(child, SIGKILL) == 0); CHECK(waitpid(child, &status, 0) == child);
    CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL);
}
static void live_rejection_capacity(struct endpoint *manager, struct handles h) {
    CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, 0x7ffffffe, 1) == -1 && errno == EINVAL);
    CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, 0, 1) == -1 && errno == EINVAL);
    CHECK(death_done(manager, 1) == -1 && errno == EINVAL);
    CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, h.accept, 400) == 0);
    CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, h.deny, 400) == -1 && errno == EINVAL);
    CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, h.accept, 401) == -1 && errno == EINVAL);
    CHECK(death_command(manager, BC_CLEAR_DEATH_NOTIFICATION, h.accept, 401) == -1 && errno == EINVAL);
    CHECK(death_command(manager, BC_CLEAR_DEATH_NOTIFICATION, h.accept, 400) == 0);
    CHECK(death_command(manager, BC_CLEAR_DEATH_NOTIFICATION, h.accept, 400) == -1 && errno == EINVAL);
    death_read(manager, BR_CLEAR_DEATH_NOTIFICATION_DONE, 400); no_messages(manager);
    for (unsigned i = 0; i < 32; ++i) {
        CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, h.accept, 1000 + i) == 0);
        CHECK(death_command(manager, BC_CLEAR_DEATH_NOTIFICATION, h.accept, 1000 + i) == 0);
    }
    CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, h.accept, 2000) == -1 && errno == ENOSPC);
    for (unsigned i = 0; i < 32; ++i) death_read(manager, BR_CLEAR_DEATH_NOTIFICATION_DONE, 1000 + i);
    CHECK(death_command(manager, BC_REQUEST_DEATH_NOTIFICATION, h.accept, 2000) == 0);
    CHECK(death_command(manager, BC_CLEAR_DEATH_NOTIFICATION, h.accept, 2000) == 0);
    death_read(manager, BR_CLEAR_DEATH_NOTIFICATION_DONE, 2000); no_messages(manager);
    puts("binder_death_real_live_clear_wrong_cookie_duplicate_and_32_record_refund\tPASS");
}
static void subscriber_exit(struct endpoint *manager, struct handles h) {
    int ready[2]; CHECK(pipe(ready) == 0);
    pid_t child = fork(); CHECK(child >= 0);
    if (!child) {
        role = "death-subscriber"; CHECK(close(manager->fd) == 0);
        struct endpoint e = endpoint(); send_ok(&e, BC_TRANSACTION, 0, 120, 0, NULL, 0); completion(&e);
        struct message reply = receive(&e); CHECK(reply.kind == BR_REPLY && reply.tr.code == 121);
        const struct flat_binder_object *value = payload(&reply, 1);
        CHECK(death_command(&e, BC_REQUEST_DEATH_NOTIFICATION, value->handle, 600) == 0);
        byte(ready[1], 'r'); pause(); _exit(1);
    }
    struct message request = receive(manager); CHECK(request.kind == BR_TRANSACTION && request.tr.code == 120);
    free_buffer(manager, request.tr.data.ptr.buffer);
    struct flat_binder_object values[2]; remote_objects(values, h);
    send_ok(manager, BC_REPLY, 0, 121, 0, values, 1); completion(manager);
    await_byte(ready[0], 'r'); killed(child); CHECK(close(ready[0]) == 0 && close(ready[1]) == 0);
    puts("binder_death_subscriber_SIGKILL_releases_attached_subscription\tPASS");
}
static void main_matrix(void) {
    struct endpoint manager = endpoint(); enter(&manager); CHECK(ioctl(manager.fd, BINDER_SET_CONTEXT_MGR, 0) == 0);
    int control[2], notify[2]; CHECK(pipe(control) == 0 && pipe(notify) == 0);
    pid_t owner = fork(); CHECK(owner >= 0);
    if (!owner) child_owner(manager.fd, control[0], notify[1], 0);
    struct handles h = owner_registration_reply(&manager); await_byte(notify[0], 'r');
    live_rejection_capacity(&manager, h); subscriber_exit(&manager, h);
    int retained[8] = {1, 1, 0, 1, 0, 1, 0, 0}; struct subscriber s[8];
    for (unsigned i = 0; i < 8; ++i) {
        s[i] = subscribe_endpoint(&manager, h, retained[i]);
        CHECK(death_command(&s[i].e, BC_REQUEST_DEATH_NOTIFICATION, s[i].handle, 101 + i) == 0);
        no_messages(&s[i].e); // Registering an alive owner cannot fake a death.
    }
    struct subscriber weak = subscribe_endpoint(&manager, h, 0);
    CHECK(ref_command(&weak.e, BC_INCREFS, weak.handle) == 0);
    free_buffer(&weak.e, weak.buffer); weak.buffer = 0;
    CHECK(death_command(&weak.e, BC_REQUEST_DEATH_NOTIFICATION, weak.handle, 109) == 0);
    send_rejected(&weak.e, BC_TRANSACTION, weak.handle, 0, NULL, 0, EINVAL);
    CHECK(death_command(&s[5].e, BC_CLEAR_DEATH_NOTIFICATION, s[5].handle, 106) == 0);
    CHECK(death_command(&manager, BC_REQUEST_DEATH_NOTIFICATION, h.accept, 9000) == 0);
    // Fill the ordinary manager request admission queue. Death work owns a
    // separate bounded record and must still be delivered without losing it.
    struct endpoint callers[16];
    for (unsigned i = 0; i < 16; ++i) {
        callers[i] = endpoint();
        if (i < 15) { send_ok(&callers[i], BC_TRANSACTION, 0, 800 + i, 0, NULL, 0); completion(&callers[i]); }
        else send_rejected(&callers[i], BC_TRANSACTION, 0, 0, NULL, 0, EAGAIN);
    }
    killed(owner);
    struct pollfd polled = {.fd = s[1].e.fd, .events = POLLIN};
    CHECK(poll(&polled, 1, 1000) == 1 && (polled.revents & POLLIN));
    death_read(&manager, BR_DEAD_BINDER, 9000); CHECK(death_done(&manager, 9000) == 0);
    CHECK(death_command(&manager, BC_CLEAR_DEATH_NOTIFICATION, h.accept, 9000) == 0);
    death_read(&manager, BR_CLEAR_DEATH_NOTIFICATION_DONE, 9000);
    struct message preserved = receive(&manager);
    CHECK(preserved.kind == BR_TRANSACTION && preserved.tr.code == 800);
    free_buffer(&manager, preserved.tr.data.ptr.buffer);
    for (unsigned i = 0; i < 16; ++i) close_endpoint(&callers[i]);
    no_messages(&manager);
    // Queued death then CLEAR still owes death before clear-complete.
    CHECK(death_command(&s[0].e, BC_CLEAR_DEATH_NOTIFICATION, s[0].handle, 101) == 0);
    CHECK(death_done(&s[0].e, 101) == -1 && errno == EINVAL);
    death_read(&s[0].e, BR_DEAD_BINDER, 101);
    CHECK(death_done(&s[0].e, 101) == 0);
    death_read(&s[0].e, BR_CLEAR_DEATH_NOTIFICATION_DONE, 101);
    // Owner was already dead at the later registration: real immediate queue.
    CHECK(death_command(&s[0].e, BC_REQUEST_DEATH_NOTIFICATION, s[0].handle, 201) == 0);
    death_read(&s[0].e, BR_DEAD_BINDER, 201); CHECK(death_done(&s[0].e, 201) == 0);
    CHECK(death_done(&s[0].e, 201) == -1 && errno == EINVAL);
    CHECK(death_command(&s[0].e, BC_CLEAR_DEATH_NOTIFICATION, s[0].handle, 201) == 0);
    death_read(&s[0].e, BR_CLEAR_DEATH_NOTIFICATION_DONE, 201); release_subscriber(&s[0]);
    unsigned char small[11]; uint64_t consumed = 99;
    CHECK(read_bytes(s[1].e.fd, small, sizeof small, &consumed) == -1 && errno == ENOSPC && consumed == 0);
    CHECK(read_bytes(s[1].e.fd, (void *)1, 128, &consumed) == -1 && errno == EFAULT && consumed == 0);
    CHECK(death_done(&s[1].e, 102) == -1 && errno == EBUSY);
    death_read(&s[1].e, BR_DEAD_BINDER, 102);
    CHECK(death_command(&s[1].e, BC_CLEAR_DEATH_NOTIFICATION, s[1].handle, 102) == 0);
    CHECK(death_done(&s[1].e, 999) == -1 && errno == EINVAL);
    CHECK(death_done(&s[1].e, 102) == 0);
    CHECK(death_done(&s[1].e, 102) == -1 && errno == EINVAL);
    death_read(&s[1].e, BR_CLEAR_DEATH_NOTIFICATION_DONE, 102); release_subscriber(&s[1]);
    // Attached queued work dies with the last buffer reference.
    free_buffer(&s[2].e, s[2].buffer); s[2].buffer = 0;
    CHECK(death_done(&s[2].e, 103) == -1 && errno == EINVAL); no_messages(&s[2].e); release_subscriber(&s[2]);
    // Attached delivered work also dies with the last explicit reference.
    death_read(&s[3].e, BR_DEAD_BINDER, 104);
    CHECK(ref_command(&s[3].e, BC_RELEASE, s[3].handle) == 0); s[3].retained = 0;
    CHECK(death_done(&s[3].e, 104) == -1 && errno == EINVAL); no_messages(&s[3].e); release_subscriber(&s[3]);
    // CLEAR detached queued work survives last-buffer removal.
    CHECK(death_command(&s[4].e, BC_CLEAR_DEATH_NOTIFICATION, s[4].handle, 105) == 0);
    free_buffer(&s[4].e, s[4].buffer); s[4].buffer = 0;
    death_read(&s[4].e, BR_DEAD_BINDER, 105); CHECK(death_done(&s[4].e, 105) == 0);
    death_read(&s[4].e, BR_CLEAR_DEATH_NOTIFICATION_DONE, 105); release_subscriber(&s[4]);
    death_read(&s[5].e, BR_CLEAR_DEATH_NOTIFICATION_DONE, 106); no_messages(&s[5].e); release_subscriber(&s[5]);
    death_read(&s[6].e, BR_DEAD_BINDER, 107); free_buffer(&s[6].e, s[6].buffer); s[6].buffer = 0;
    CHECK(death_done(&s[6].e, 107) == -1 && errno == EINVAL); no_messages(&s[6].e); release_subscriber(&s[6]);
    death_read(&s[7].e, BR_DEAD_BINDER, 108);
    CHECK(death_command(&s[7].e, BC_CLEAR_DEATH_NOTIFICATION, s[7].handle, 108) == 0);
    free_buffer(&s[7].e, s[7].buffer); s[7].buffer = 0;
    CHECK(death_done(&s[7].e, 108) == 0); death_read(&s[7].e, BR_CLEAR_DEATH_NOTIFICATION_DONE, 108);
    release_subscriber(&s[7]);
    death_read(&weak.e, BR_DEAD_BINDER, 109);
    CHECK(ref_command(&weak.e, BC_DECREFS, weak.handle) == 0);
    CHECK(death_done(&weak.e, 109) == -1 && errno == EINVAL); no_messages(&weak.e);
    release_subscriber(&weak);
    puts("binder_death_SIGKILL_full_queue_exact_clear_ack_lastref_and_copyfault\tPASS");
    // A replacement owner exporting the same pointer/cookie is a new node.
    pid_t next = fork(); CHECK(next >= 0);
    if (!next) child_owner(manager.fd, control[0], notify[1], 1);
    struct handles newer = owner_registration_reply(&manager); await_byte(notify[0], 'r');
    CHECK(newer.accept != h.accept);
    CHECK(death_command(&manager, BC_REQUEST_DEATH_NOTIFICATION, newer.accept, 10000) == 0);
    byte(control[1], 'e'); await_byte(notify[0], 'x');
    death_read(&manager, BR_DEAD_BINDER, 10000); CHECK(death_done(&manager, 10000) == 0);
    CHECK(death_command(&manager, BC_CLEAR_DEATH_NOTIFICATION, newer.accept, 10000) == 0);
    death_read(&manager, BR_CLEAR_DEATH_NOTIFICATION_DONE, 10000);
    send_ok(&manager, BC_TRANSACTION, h.accept, 9999, 0, NULL, 0); completion(&manager);
    CHECK(receive(&manager).kind == BR_DEAD_REPLY);
    byte(control[1], 'q'); wait_child(next);
    CHECK(ref_command(&manager, BC_RELEASE, newer.accept) == 0 && ref_command(&manager, BC_RELEASE, newer.deny) == 0);
    unsigned clear_won = 0, death_won = 0;
    for (unsigned round = 0; round < 16; ++round) {
        pid_t racing = fork(); CHECK(racing >= 0);
        if (!racing) child_owner(manager.fd, control[0], notify[1], 0);
        struct handles raced = owner_registration_reply(&manager); await_byte(notify[0], 'r');
        uint64_t cookie = 20000 + round;
        CHECK(death_command(&manager, BC_REQUEST_DEATH_NOTIFICATION, raced.accept, cookie) == 0);
        byte(control[1], 'q'); // Another real process now closes its mapped endpoint.
        CHECK(death_command(&manager, BC_CLEAR_DEATH_NOTIFICATION, raced.accept, cookie) == 0);
        unsigned char bytes[128]; uint64_t size = 0, actual = 0; uint32_t kind = 0;
        CHECK(read_bytes(manager.fd, bytes, sizeof bytes, &size) == 0 && size == 12);
        memcpy(&kind, bytes, 4); memcpy(&actual, bytes + 4, 8); CHECK(actual == cookie);
        if (kind == BR_DEAD_BINDER) {
            ++death_won; CHECK(death_done(&manager, cookie) == 0);
            death_read(&manager, BR_CLEAR_DEATH_NOTIFICATION_DONE, cookie);
        } else { CHECK(kind == BR_CLEAR_DEATH_NOTIFICATION_DONE); ++clear_won; }
        wait_child(racing); no_messages(&manager);
        CHECK(death_done(&manager, cookie) == -1 && errno == EINVAL);
        CHECK(ref_command(&manager, BC_RELEASE, raced.accept) == 0 && ref_command(&manager, BC_RELEASE, raced.deny) == 0);
    }
    printf("binder_death_16_actual_owner_close_CLEAR_races clear_first=%u death_first=%u\tPASS\n", clear_won, death_won);
    CHECK(ref_command(&manager, BC_RELEASE, h.accept) == 0 && ref_command(&manager, BC_RELEASE, h.deny) == 0);
    close_endpoint(&manager); CHECK(close(control[0]) == 0 && close(control[1]) == 0 && close(notify[0]) == 0 && close(notify[1]) == 0);
    puts("binder_death_actual_exec_old_fd_rejected_new_node_no_retarget\tPASS");
}
int main(int argc, char **argv) {
    role = "death"; setbuf(stdout, NULL); signal(SIGALRM, alarmed); alarm(40);
    if (argc == 5 && !strcmp(argv[1], "--exec-fd")) {
        struct binder_version version; int old = atoi(argv[2]);
        CHECK(ioctl(old, BINDER_VERSION, &version) == -1 && errno == EPERM);
        struct endpoint replacement = endpoint(); enter(&replacement); no_messages(&replacement);
        byte(atoi(argv[3]), 'x'); await_byte(atoi(argv[4]), 'q'); no_messages(&replacement);
        close_endpoint(&replacement); CHECK(close(old) == 0); return 0;
    }
    CHECK(argc == 1); main_matrix();
    printf("{\"passed\":true,\"checks\":%u,\"scope\":\"bounded_real_binder_death_subscriptions\",\"thread_pool\":false,\"android_boot\":false}\n", checks);
    return 0;
}
