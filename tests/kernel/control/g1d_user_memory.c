/* SPDX-License-Identifier: MPL-2.0 */
/* Reuse the actual sealed-role bootstrap, HOS2 ABI and exact history reader.
 * The legacy entry point is compiled but never used by this bounded probe. */
#define main legacy_g1d_main
#include "g1d_init.c"
#undef main

#define MEMORY_STATUS IPC_DIR "/memory-status"
#define MEMORY_FILE IPC_DIR "/memory-file"
#define MEMORY_LIMIT_PAGES 16384U
#define MEMORY_HOLDER_PAGES 4608U
#define MEMORY_TIMEOUT_NS UINT64_C(120000000000)
#define MEMORY_MAGIC UINT64_C(0x4731444D454D3031)

struct memory_report {
    uint64_t magic, state, pid, pages, address;
    int64_t direct_errno, shared_errno, cow_errno, file_errno, write_errno;
};
struct memory_status {
    uint64_t magic, state, fork_pid, exec_pid, saturator_pid, saturated_pages, address;
};
static int memory_commands[3][2], memory_replies[3][2];
static int memory_zero = -1, memory_file = -1, memory_status_fd = -1;
static unsigned char *memory_cow;

static void memory_io(int fd, void *data, size_t size, int writing) {
    unsigned char *bytes = data;
    while (size) {
        ssize_t count = writing ? write(fd, bytes, size) : read(fd, bytes, size);
        if (count < 0 && errno == EINTR) continue;
        CHECK(count > 0, "memory_pipe_io");
        bytes += count; size -= (size_t)count;
    }
}

__attribute__((noinline)) static void memory_warm_stack(void) {
    volatile unsigned char pages[64 * 1024];
    for (size_t i = 0; i < sizeof pages; i += PAGE_BYTES) pages[i] = 37;
    pages[sizeof pages - 1] = 19;
    __asm__ __volatile__("" : : "r"(pages) : "memory");
}

static unsigned char *memory_map(size_t pages, int shared, int fd) {
    int flags = shared ? MAP_SHARED : MAP_PRIVATE;
    if (fd < 0) flags |= MAP_ANONYMOUS;
    void *address = mmap(NULL, pages * PAGE_BYTES, PROT_READ | PROT_WRITE, flags, fd, 0);
    CHECK(address != MAP_FAILED, "memory_map");
    return address;
}

static int memory_touch(unsigned char *address) {
    errno = 0;
    ssize_t count = read(memory_zero, address, 1);
    if (count == 1) return 0;
    CHECK(count == -1, "memory_touch_result");
    return errno;
}

static void memory_publish(const struct memory_status *status) {
    CHECK(pwrite(memory_status_fd, status, sizeof *status, 0) == (ssize_t)sizeof *status,
          "memory_status_write");
}

static void memory_wait_release(void) {
    uint64_t deadline = now_ns() + MEMORY_TIMEOUT_NS;
    unsigned char release = 0;
    while (now_ns() < deadline) {
        CHECK(pread(memory_status_fd, &release, 1, 256) == 1, "memory_release_read");
        if (release == 1) return;
        CHECK(release == 0, "memory_release_value");
        sleep_ms(5);
    }
    failure("memory_release_timeout", __LINE__);
}

static _Noreturn void memory_worker(unsigned kind, int command, int reply) {
    memory_warm_stack();
    unsigned char action;
    memory_io(command, &action, 1, 0);
    CHECK(action == 'A', "memory_worker_start");
    memory_warm_stack();
    if (memory_zero < 0) memory_zero = open("/dev/zero", O_RDONLY);
    CHECK(memory_zero >= 0, "memory_zero_open");
    size_t pages = kind == 2 ? MEMORY_LIMIT_PAGES : MEMORY_HOLDER_PAGES;
    unsigned char *region = memory_map(pages, 0, -1);
    unsigned char *shared = NULL, *file_map = NULL;
    if (kind == 2) {
        shared = memory_map(1, 1, -1);
        file_map = memory_map(2, 1, memory_file);
    }
    struct memory_report result = {.magic = MEMORY_MAGIC, .pid = (uint64_t)getpid()};
    for (size_t page = 0; page < pages; ++page) {
        int error = memory_touch(region + page * PAGE_BYTES);
        if (error != 0) {
            CHECK(kind == 2 && error == EFAULT, "memory_holder_admission");
            result.direct_errno = error;
            result.address = (uintptr_t)(region + page * PAGE_BYTES);
            break;
        }
        result.pages++;
    }
    if (kind != 2) {
        CHECK(result.pages == MEMORY_HOLDER_PAGES, "memory_holder_pages");
        record("G1DM_HOLDER kind=%s pid=%ld parent=%ld pages=%u",
               kind == 0 ? "fork" : "exec", (long)getpid(), (long)getppid(), MEMORY_HOLDER_PAGES);
        result.state = 1;
    } else if (result.pages == MEMORY_LIMIT_PAGES) {
        /* A precise old/no-owner negative. Keep the pages resident until the
         * manager receives this report; no timeout or generic crash qualifies. */
        result.state = 3;
        record("G1DM_NO_LIMIT pid=%ld pages=%u held_pages=%u", (long)getpid(),
               MEMORY_LIMIT_PAGES, 2 * MEMORY_HOLDER_PAGES);
    } else {
        result.state = 1;
        result.shared_errno = memory_touch(shared);
        result.cow_errno = memory_touch(memory_cow);
        result.file_errno = memory_touch(file_map);
        unsigned char byte = 0;
        errno = 0;
        CHECK(pwrite(memory_file, &byte, 1, PAGE_BYTES) == -1, "memory_file_write_limit");
        result.write_errno = errno;
        CHECK(result.shared_errno == EFAULT && result.cow_errno == EFAULT &&
              result.file_errno == EFAULT && result.write_errno == ENOMEM,
              "memory_path_admission");
        CHECK(*memory_cow == 109, "memory_cow_denied_preserved");
        record("G1DM_DENIALS pid=%ld address=%" PRIu64 " pages=%" PRIu64
               " shared_address=%" PRIuPTR " cow_address=%" PRIuPTR " file_address=%" PRIuPTR
               " direct_errno=14 shared_errno=14 cow_errno=14 file_errno=14 write_errno=12",
               (long)getpid(), result.address, result.pages,
               (uintptr_t)shared, (uintptr_t)memory_cow, (uintptr_t)file_map);
    }
    memory_io(reply, &result, sizeof result, 1);
    memory_io(command, &action, 1, 0);
    if (kind == 2 && result.state == 1) {
        CHECK(action == 'T', "memory_retry_command");
        CHECK(memory_touch((unsigned char *)(uintptr_t)result.address) == 0 &&
              memory_touch(shared) == 0 && memory_touch(memory_cow) == 0 &&
              memory_touch(file_map) == 0, "memory_refund_retry_same_mappings");
        unsigned char byte = 83;
        CHECK(pwrite(memory_file, &byte, 1, PAGE_BYTES) == 1 && file_map[PAGE_BYTES] == 83,
              "memory_file_refund_retry");
        CHECK(*memory_cow == 0, "memory_cow_retry_changed_only_child");
        record("G1DM_RETRY pid=%ld address=%" PRIu64
               " same_mappings=1 anonymous=1 shared=1 cow=1 file_fault=1 file_write=1",
               (long)getpid(), result.address);
        result.state = 2;
        memory_io(reply, &result, sizeof result, 1);
        CHECK(munmap(shared, PAGE_BYTES) == 0 && munmap(file_map, 2 * PAGE_BYTES) == 0,
              "memory_extra_unmap");
    } else CHECK(action == 'R', "memory_release_command");
    CHECK(munmap(region, pages * PAGE_BYTES) == 0, "memory_holder_unmap");
    _exit(0);
}

static _Noreturn void memory_exec_worker(int argc, char **argv) {
    CHECK(argc == 4 && getauxval(AT_HEPTA_BOOT) == 0 && getuid() == WORKLOAD_ID &&
          geteuid() == WORKLOAD_ID && prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1,
          "memory_exec_identity");
    role = 2;
    char *end;
    long command = strtol(argv[2], &end, 10);
    CHECK(*end == 0 && command >= 3 && command <= INT_MAX, "memory_exec_command_fd");
    long reply = strtol(argv[3], &end, 10);
    CHECK(*end == 0 && reply >= 3 && reply <= INT_MAX && command != reply, "memory_exec_reply_fd");
    record("G1DM_EXEC_CHILD pid=%ld parent=%ld uid=60001 no_boot=1", (long)getpid(), (long)getppid());
    memory_worker(1, (int)command, (int)reply);
}

static void memory_reap(pid_t child) {
    int status;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "memory_child_exit");
}

static _Noreturn void memory_workload(void) {
    wait_ready();
    CHECK(getuid() == WORKLOAD_ID && geteuid() == WORKLOAD_ID, "memory_workload_uid");
    memory_status_fd = open(MEMORY_STATUS, O_RDWR);
    memory_file = open(MEMORY_FILE, O_RDWR);
    memory_zero = open("/dev/zero", O_RDONLY);
    CHECK(memory_status_fd >= 0 && memory_file >= 0 && memory_zero >= 0, "memory_workload_fds");
    memory_cow = memory_map(1, 0, -1);
    *memory_cow = 109;
    for (unsigned i = 0; i < 3; ++i)
        CHECK(pipe(memory_commands[i]) == 0 && pipe(memory_replies[i]) == 0, "memory_pipes");
    pid_t children[3];
    struct memory_report reports[3] = {{0}};
    memory_warm_stack();
    for (unsigned i = 0; i < 3; ++i) {
        children[i] = fork();
        CHECK(children[i] >= 0, "memory_fork");
        if (children[i] == 0) {
            if (i == 1) {
                char command[24], reply[24];
                CHECK(snprintf(command, sizeof command, "%d", memory_commands[i][0]) > 0 &&
                      snprintf(reply, sizeof reply, "%d", memory_replies[i][1]) > 0, "memory_exec_args");
                char *args[] = {"/test/g1d-init", "--memory-exec-holder", command, reply, NULL};
                execv(args[0], args);
                failure("memory_exec_returned", __LINE__);
            }
            memory_worker(i, memory_commands[i][0], memory_replies[i][1]);
        }
        /* All future parent stack writes must be private before the last
         * child consumes the account. There is no pressure-time heap use. */
        memory_warm_stack();
        /* The reply destination is in this caller frame, above the warm-up
         * frame. Force its COW before authorizing this child to allocate. */
        volatile unsigned char *reply_bytes = (volatile unsigned char *)&reports[i];
        for (size_t j = 0; j < sizeof reports[i]; ++j) reply_bytes[j] = 0;
        unsigned char action = 'A';
        memory_io(memory_commands[i][1], &action, 1, 1);
        memory_io(memory_replies[i][0], &reports[i], sizeof reports[i], 0);
        CHECK(reports[i].magic == MEMORY_MAGIC && reports[i].pid == (uint64_t)children[i] &&
              (reports[i].state == 1 || (i == 2 && reports[i].state == 3)), "memory_report_binding");
    }
    struct memory_status status = {.magic = MEMORY_MAGIC, .state = reports[2].state,
        .fork_pid = (uint64_t)children[0], .exec_pid = (uint64_t)children[1],
        .saturator_pid = (uint64_t)children[2], .saturated_pages = reports[2].pages,
        .address = reports[2].address};
    if (status.state == 1) {
        CHECK(status.saturated_pages >= 4096 &&
              status.saturated_pages + 2 * MEMORY_HOLDER_PAGES < MEMORY_LIMIT_PAGES,
              "memory_family_not_per_process");
        record("G1DM_SATURATED pid=%ld fork_pid=%ld exec_pid=%ld saturator_pid=%ld"
               " holder_pages=%u saturator_pages=%" PRIu64 " limit_pages=%u",
               (long)getpid(), (long)children[0], (long)children[1], (long)children[2],
               MEMORY_HOLDER_PAGES, status.saturated_pages, MEMORY_LIMIT_PAGES);
    }
    memory_publish(&status);
    memory_wait_release();
    unsigned char action = 'R';
    memory_io(memory_commands[0][1], &action, 1, 1);
    memory_reap(children[0]);
    action = status.state == 1 ? 'T' : 'R';
    memory_io(memory_commands[2][1], &action, 1, 1);
    if (status.state == 1) {
        struct memory_report retried;
        memory_io(memory_replies[2][0], &retried, sizeof retried, 0);
        CHECK(retried.magic == MEMORY_MAGIC && retried.pid == status.saturator_pid &&
              retried.state == 2 && retried.address == status.address, "memory_retry_binding");
    }
    memory_reap(children[2]);
    action = 'R';
    memory_io(memory_commands[1][1], &action, 1, 1);
    memory_reap(children[1]);
    CHECK(*memory_cow == 109, "memory_cow_parent_unchanged");
    CHECK(ftruncate(memory_file, 0) == 0, "memory_file_refund_cleanup");
    if (status.state == 1) record("G1DM_REFUND family_children_reaped=3 parent_cow_unchanged=1 file_truncated=1");
    status.state = 2;
    memory_publish(&status);
    _exit(0);
}

static _Noreturn void memory_recovery(void) {
    wait_ready();
    control_fd = open_control(1);
    query(control_fd, own_space);
    CHECK(memcmp(own_space, recovery_space, 16) == 0, "memory_recovery_space");
    struct message ready = {.magic = IPC_MAGIC};
    publish_message("recovery-ready", &ready);
    uint64_t last = 0;
    for (;;) {
        struct message command;
        uint64_t deadline = now_ns() + MEMORY_TIMEOUT_NS;
        for (;;) {
            if (read_message("command", &command) && command.id == last + 1) break;
            CHECK(now_ns() < deadline, "memory_recovery_timeout");
            sleep_ms(2);
        }
        last = command.id;
        if (command.action == REC_STOP) {
            publish_message("reply", &command);
            _exit(0);
        }
        CHECK(command.action == REC_INSTALL && last == 1, "memory_recovery_command");
        /* This is a finite observation of a separate role's allocation,
         * never a claim that physical recovery reserves exist. */
        memory_zero = open("/dev/zero", O_RDONLY);
        CHECK(memory_zero >= 0, "memory_recovery_zero");
        unsigned char *pages = memory_map(16, 0, -1);
        for (unsigned i = 0; i < 16; ++i)
            CHECK(memory_touch(pages + i * PAGE_BYTES) == 0, "memory_recovery_allocation");
        record("G1DM_RECOVERY_ALLOC role=3 pid=%ld pages=16 workload_at_limit=1 physical_reserve=false",
               (long)getpid());
        struct usage before = usage_read(control_fd, 0);
        CHECK(before.revision == command.a && command.b == 0, "memory_recovery_revision");
        struct usage after = install_ok(1, before, MAX_CAP_NS, command.response, 1);
        CHECK(after.revision == before.revision + 1, "memory_recovery_applied");
        CHECK(munmap(pages, 16 * PAGE_BYTES) == 0, "memory_recovery_unmap");
        publish_message("reply", &command);
    }
}

static _Noreturn void memory_manager(void) {
    CHECK(mount("none", "/dev", "devtmpfs", 0, NULL) == 0, "memory_mount_dev");
    CHECK(mount("none", "/proc", "proc", 0, NULL) == 0, "memory_mount_proc");
    CHECK(mount("none", "/sys", "sysfs", 0, NULL) == 0, "memory_mount_sys");
    CHECK(mount("none", "/sys/fs/cgroup", "cgroup2", 0, NULL) == 0, "memory_mount_cgroup");
    CHECK(mkdir(IPC_DIR, 0755) == 0, "memory_ipc_directory");
    unsigned char initialized[PAGE_BYTES] = {0};
    write_file(MEMORY_STATUS, initialized, sizeof initialized);
    write_file(MEMORY_FILE, "", 0);
    CHECK(chown(MEMORY_STATUS, WORKLOAD_ID, WORKLOAD_ID) == 0 &&
          chown(MEMORY_FILE, WORKLOAD_ID, WORKLOAD_ID) == 0, "memory_ipc_owner");
    memory_status_fd = open(MEMORY_STATUS, O_RDWR);
    memory_file = open(MEMORY_FILE, O_RDWR);
    CHECK(memory_status_fd >= 0 && memory_file >= 0 && ftruncate(memory_file, 2 * PAGE_BYTES) == 0,
          "memory_ipc_prepare");
    struct message ready = {.magic = IPC_MAGIC};
    publish_message("ready", &ready);
    (void)await_message("recovery-ready", 0);
    struct memory_status status = {0};
    uint64_t deadline = now_ns() + MEMORY_TIMEOUT_NS;
    while (status.state == 0 && now_ns() < deadline) {
        CHECK(pread(memory_status_fd, &status, sizeof status, 0) == (ssize_t)sizeof status,
              "memory_manager_status");
        if (status.state == 0) sleep_ms(5);
    }
    CHECK(status.magic == MEMORY_MAGIC && status.state != 0, "memory_workload_report_timeout");
    CHECK(status.state != 3, "memory_aggregate_limit");
    CHECK(status.state == 1, "memory_workload_saturated");
    control_fd = open_control(1);
    query(control_fd, own_space);
    CHECK(memcmp(own_space, manager_space, 16) == 0, "memory_manager_space");
    struct usage initial = usage_read(control_fd, MAX_CAP_NS);
    unsigned char applied[128], history_bytes[128];
    struct usage stopped = install_ok(1, initial, 0, applied, 1);
    sleep_ms(25);
    struct usage still_stopped = usage_read(control_fd, 0);
    CHECK(still_stopped.revision == stopped.revision &&
          still_stopped.cumulative == stopped.cumulative, "memory_stopped_cpu");
    history(control_fd, manager_history_slot, manager_history_gen, manager_space, 1, 0, OK, history_bytes);
    history_terminal(history_bytes, 1, OK, applied);
    struct message restored = recovery_command(REC_INSTALL, stopped.revision, 0, OK);
    struct usage after = usage_read(control_fd, MAX_CAP_NS);
    CHECK(after.revision == initial.revision + 2 && get64(restored.response + 56) == after.revision,
          "memory_actual_recovery_readback");
    record("G1DM_RECOVERY_READBACK initial=%" PRIu64 " stopped=%" PRIu64 " recovered=%" PRIu64
           " stopped_total=%" PRIu64 " paused_total=%" PRIu64
           " cap=50000000 manager_history_terminal=1", initial.revision, stopped.revision, after.revision,
           stopped.cumulative, still_stopped.cumulative);
    unsigned char release = 1;
    CHECK(pwrite(memory_status_fd, &release, 1, 256) == 1, "memory_manager_release");
    memory_reap(workload_pid);
    CHECK(pread(memory_status_fd, &status, sizeof status, 0) == (ssize_t)sizeof status && status.state == 2,
          "memory_workload_complete");
    (void)recovery_command(REC_STOP, 0, 0, OK);
    memory_reap(recovery_pid);
    record("G1DM_COMPLETE aggregate_user_frames=true fork_exec=true recovery=true memory_max=false physical_reserve=false hardware=false");
    sync();
    reboot(RB_POWER_OFF);
    failure("memory_poweroff_returned", __LINE__);
    _exit(121);
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc > 1 && strcmp(argv[1], "--memory-exec-holder") == 0) memory_exec_worker(argc, argv);
    CHECK(argc == 1, "memory_initial_argc");
    bootstrap();
    if (role == 1) memory_manager();
    if (role == 2) memory_workload();
    memory_recovery();
}
