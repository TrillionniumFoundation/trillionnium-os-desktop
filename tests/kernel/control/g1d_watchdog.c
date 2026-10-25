/* SPDX-License-Identifier: MPL-2.0 */
/* Original sealed bootstrap, ABI, owner and delivery namespace. The selected
 * case is test data; it never creates an image role or pause authority. */
#define main legacy_g1d_main
#include "g1d_init.c"
#undef main

#define WATCHDOG_SMALL_CAP UINT64_C(25000000)
#define WATCHDOG_TIMEOUT_NS UINT64_C(20000000000)
static char watchdog_stat_path[448];
static int zero_case(const char *kind) { return !strcmp(kind, "zero") || !strcmp(kind, "zerothread"); }

static void watchdog_leaf(void) {
    char path[128], line[256];
    CHECK(snprintf(path, sizeof path, "/proc/%ld/cgroup", (long)workload_pid) > 0, "watchdog_cgroup_path");
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "watchdog_cgroup_open");
    ssize_t n = read(fd, line, sizeof line - 1);
    CHECK(n > 4 && close(fd) == 0, "watchdog_cgroup_read");
    line[n] = 0;
    CHECK(strncmp(line, "0::/hepta-g1d-", 14) == 0 && strchr(line + 4, '\n'), "watchdog_real_leaf");
    *strchr(line + 4, '\n') = 0;
    CHECK(snprintf(watchdog_stat_path, sizeof watchdog_stat_path, "/sys/fs/cgroup%s/cpu.stat", line + 3) > 0,
          "watchdog_stat_path");
}
static void watchdog_assert_zero_cap(void) {
    char path[448], value[96];
    size_t prefix = strlen(watchdog_stat_path) - strlen("cpu.stat");
    CHECK(prefix < sizeof path && snprintf(path, sizeof path, "%.*scpu.max", (int)prefix,
          watchdog_stat_path) > 0, "watchdog_zero_cap_path");
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "watchdog_zero_cap_open");
    ssize_t n = read(fd, value, sizeof value - 1);
    CHECK(n > 0 && close(fd) == 0, "watchdog_zero_cap_read");
    value[n] = 0;
    uint64_t quota, period;
    CHECK(sscanf(value, "%" SCNu64 " %" SCNu64, &quota, &period) == 2 && quota == 0 && period == 100000,
          "watchdog_fatal_cleanup_preserves_zero_cap");
}
struct watchdog_stat {
    uint64_t armed, due, expires, status, evaluated, available, stopped, pause_available;
    uint64_t stable_low, stable_high, previous, revision, effective, consumed, ticks;
    unsigned mask;
};
static struct watchdog_stat watchdog_read(void) {
    int fd = open(watchdog_stat_path, O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "watchdog_stat_open");
    char buffer[2048];
    ssize_t n = read(fd, buffer, sizeof buffer - 1);
    CHECK(n > 0 && n < (ssize_t)sizeof buffer - 1 && close(fd) == 0, "watchdog_stat_read");
    buffer[n] = 0;
    struct watchdog_stat stat;
    memset(&stat, 0, sizeof stat);
    const char *keys[] = {"hepta_watchdog_armed", "hepta_watchdog_due_ns", "hepta_watchdog_expires_ns",
        "hepta_watchdog_status", "hepta_watchdog_evaluated_ns", "hepta_job_stop_available",
        "hepta_job_stopped", "hepta_user_pause_intent_available", "hepta_watchdog_stable_id_low",
        "hepta_watchdog_stable_id_high", "hepta_watchdog_previous_revision", "hepta_watchdog_revision",
        "hepta_watchdog_effective_ns", "hepta_watchdog_consumed_ns", "hepta_watchdog_ticks"};
    uint64_t *values[] = {&stat.armed, &stat.due, &stat.expires, &stat.status, &stat.evaluated,
        &stat.available, &stat.stopped, &stat.pause_available, &stat.stable_low, &stat.stable_high,
        &stat.previous, &stat.revision, &stat.effective, &stat.consumed, &stat.ticks};
    char *save, *line = strtok_r(buffer, "\n", &save);
    while (line) {
        char key[80], tail; uint64_t value;
        CHECK(sscanf(line, "%79s %" SCNu64 "%c", key, &value, &tail) == 2, "watchdog_stat_line");
        for (unsigned i = 0; i < sizeof keys / sizeof keys[0]; i++) if (!strcmp(key, keys[i])) {
            CHECK(!(stat.mask & (1U << i)), "watchdog_stat_duplicate");
            stat.mask |= 1U << i; *values[i] = value;
        }
        line = strtok_r(NULL, "\n", &save);
    }
    CHECK((stat.mask & 16639U) == 16639U && stat.armed == 1 && stat.ticks > 0 && stat.available == 1 && stat.pause_available == 0,
          "watchdog_required_fields");
    CHECK(stat.due > 0 && stat.expires == stat.due + UINT64_C(25000000000), "watchdog_fixed_deadline");
    CHECK(stat.mask == (stat.status == 1 ? 32767U : 16639U), "watchdog_receipt_presence");
    return stat;
}
static void watchdog_wait_until(uint64_t deadline) {
    CHECK(deadline <= now_ns() + WATCHDOG_TIMEOUT_NS, "watchdog_wait_bound");
    while (now_ns() < deadline) sleep_ms(10);
}
static _Noreturn void watchdog_workload(void) {
    wait_ready();
    int fd = open(IPC_DIR "/heartbeat", O_WRONLY | O_CLOEXEC);
    CHECK(fd >= 0 && getuid() == WORKLOAD_ID, "watchdog_workload_identity");
    uint64_t count = 0;
    for (;;) {
        for (unsigned i = 0; i < 32768; ++i) __asm__ volatile("" : "+r"(count));
        ++count;
        CHECK(pwrite(fd, &count, sizeof count, 0) == sizeof count, "watchdog_heartbeat_write");
    }
}
static void watchdog_finish(const char *kind, uint64_t cap, uint64_t revision, struct watchdog_stat stat) {
    record("G1DW_RESULT case=%s status=%" PRIu64 " cap=%" PRIu64 " revision=%" PRIu64
           " due=%" PRIu64 " expires=%" PRIu64 " evaluated=%" PRIu64
           " stopped=%" PRIu64 " user_pause_intent_available=0",
           kind, stat.status, cap, revision, stat.due, stat.expires, stat.evaluated, stat.stopped);
    record("G1DW_COMPLETE case=%s timer=true original_owner=true durable=false reserve=false", kind);
}
static void watchdog_recovery(const char *kind) {
    wait_ready();
    control_fd = open_control(1); query(control_fd, own_space);
    CHECK(memcmp(own_space, recovery_space, 16) == 0, "watchdog_recovery_identity");
    struct message ready = {.magic = IPC_MAGIC};
    publish_message("watchdog-ready", &ready);
    if (!strcmp(kind, "healthy")) { for (;;) sleep_ms(1000); }
    struct message closed = await_message("watchdog-closed", 0);
    uint64_t cap = closed.a, revision = closed.b;
    watchdog_leaf();
    struct watchdog_stat pending = watchdog_read();
    CHECK(pending.status == 0 && pending.due > now_ns() + UINT64_C(3000000000), "watchdog_not_early");
    struct usage before = usage_read(control_fd, cap);
    CHECK(before.revision == revision, "watchdog_original_revision");
    uint64_t beat = heartbeat();
    unsigned char history_saved[128];
    history(control_fd, manager_history_slot, manager_history_gen, manager_space, 1, 0, OK, history_saved);
    history_terminal(history_saved, 1, OK, closed.response);
    if (!strcmp(kind, "recovered")) {
        unsigned char receipt[128];
        before = install_ok(1, before, MAX_CAP_NS, receipt, 1);
        cap = MAX_CAP_NS; revision = before.revision;
    }
    watchdog_wait_until(pending.due - UINT64_C(500000000));
    struct usage early = usage_read(control_fd, cap);
    CHECK(early.revision == revision && watchdog_read().status == 0, "watchdog_before_deadline_unchanged");
    watchdog_wait_until(pending.due + UINT64_C(300000000));
    struct watchdog_stat final = watchdog_read();
    int restored = !strcmp(kind, "restore");
    unsigned expected_status = restored ? 1 : !strcmp(kind, "stopped") ? 3 : 2;
    CHECK(final.status == expected_status && final.evaluated >= final.due && final.evaluated < final.expires,
          "watchdog_bounded_terminal");
    if (restored) { cap = MAX_CAP_NS; revision++; }
    struct usage after = usage_read(control_fd, cap);
    CHECK(after.revision == revision && after.cumulative >= before.cumulative, "watchdog_effect_readback");
    if (restored) {
        CHECK(final.previous + 1 == final.revision && final.revision == revision &&
              final.previous == before.revision && final.effective == final.evaluated &&
              final.consumed <= final.effective % PERIOD_NS &&
              final.stable_low == get64(history_saved + 80) && final.stable_high == get64(history_saved + 88),
              "watchdog_original_receipt");
        record("G1DW_RECEIPT previous=%" PRIu64 " revision=%" PRIu64 " effective=%" PRIu64
               " consumed=%" PRIu64 " stable_low=%" PRIu64 " stable_high=%" PRIu64,
               final.previous, final.revision, final.effective, final.consumed, final.stable_low, final.stable_high);
        unsigned char response[128];
        history(control_fd, manager_history_slot, manager_history_gen, manager_space, 2, 0, OK, response);
        history_empty(response, NOT_SEEN_STATE, 2);
        unsigned char q[104], first[128], again[128];
        install_request(q, 1, revision, MAX_CAP_NS);
        CHECK(transact(control_fd, q, 96, first) == 0, "watchdog_late_recovery_transport");
        response_header(first, q, DENIED, 0, 0);
        CHECK(transact(control_fd, q, 96, again) == 0 && memcmp(first, again, sizeof first) == 0,
              "watchdog_late_recovery_exact_replay");
        record("G1DW_ONE_USE denied=2 exact_replay=1 manager_next_D=not_seen");
    }
    if (zero_case(kind) || !strcmp(kind, "stopped")) {
        CHECK(heartbeat() == beat && after.cumulative == before.cumulative, "watchdog_preserves_pause");
        CHECK(final.stopped == (uint64_t)!strcmp(kind, "stopped"), "watchdog_original_jobstop_observation");
    }
    sleep_ms(300);
    struct watchdog_stat repeated = watchdog_read();
    uint64_t later_ticks = repeated.ticks;
    repeated.ticks = final.ticks;
    CHECK(later_ticks > final.ticks && memcmp(&final, &repeated, sizeof final) == 0 &&
          usage_read(control_fd, cap).revision == revision,
          "watchdog_repeated_ticks_immutable");
    record("G1DW_REPEAT before_ticks=%" PRIu64 " after_ticks=%" PRIu64 " unchanged_receipt=1 unchanged_revision=1",
           final.ticks, later_ticks);
    if (!strcmp(kind, "stopped")) {
        CHECK(kill(workload_pid, SIGCONT) == 0, "watchdog_explicit_continue");
        sleep_ms(300);
        CHECK(heartbeat() > beat && watchdog_read().stopped == 0 && watchdog_read().status == 3 &&
              usage_read(control_fd, cap).revision == revision, "watchdog_no_retry_after_continue");
        record("G1DW_EXPLICIT_CONTINUE signal=18 original_jobstop_cleared=1 budget_unchanged=1");
    }
    watchdog_finish(kind, cap, revision, final);
    struct message done = {.magic = IPC_MAGIC}; publish_message("watchdog-done", &done);
    _exit(0);
}
static _Noreturn void watchdog_after_exec(int argc, char **argv) {
    CHECK(argc == 5 && getauxval(AT_HEPTA_BOOT) == 0, "watchdog_exec_no_authority");
    role = 1; workload_pid = (pid_t)strtol(argv[3], NULL, 10); recovery_pid = (pid_t)strtol(argv[4], NULL, 10);
    CHECK(getpid() == 1 && workload_pid > 1 && recovery_pid > 1, "watchdog_exec_identity");
    /* The ordinary post-exec image has no saved slots. The independent role
     * only observes while the timer acts; it sends no recovery request in the
     * restore case until after the native timer receipt has been checked. */
    struct message closed;
    CHECK(read_message("watchdog-before-close", &closed), "watchdog_saved_before_close");
    publish_message("watchdog-closed", &closed);
    (void)await_message("watchdog-done", 0);
    const char *kind = argv[2];
    uint64_t before_beat = heartbeat();
    if (zero_case(kind)) { watchdog_leaf(); watchdog_assert_zero_cap(); }
    if (!strcmp(kind, "zerothread")) {
        CHECK(syscall(SYS_tgkill, workload_pid, workload_pid, SIGKILL) == 0, "watchdog_cleanup_thread");
    } else {
        CHECK(kill(workload_pid, SIGKILL) == 0, "watchdog_cleanup_workload");
    }
    int status;
    CHECK(waitpid(workload_pid, &status, 0) == workload_pid && WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL,
          "watchdog_reap_workload");
    CHECK(waitpid(recovery_pid, &status, 0) == recovery_pid && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "watchdog_reap_recovery");
    if (zero_case(kind)) {
        uint64_t after_beat = heartbeat();
        CHECK(after_beat == before_beat, "watchdog_fatal_cleanup_no_user_progress");
        watchdog_assert_zero_cap();
        record("G1DW_FATAL_EXIT case=%s signal=9 reaped=1 heartbeat_before=%" PRIu64
               " heartbeat_after=%" PRIu64 " cap_before=0 cap_after=0 period_usec=100000",
               kind, before_beat, after_beat);
    }
    record("G1DW_REAP case=%s workload_signal=9 recovery_exit=0", kind);
    reboot(RB_POWER_OFF); _exit(120);
}
static _Noreturn void watchdog_manager(const char *kind) {
    CHECK(getpid() == 1 && kill(getpid(), SIGKILL) == 0, "watchdog_init_original_signal_immunity");
    record("G1DW_INIT_SIGKILL_IGNORED original_policy=1");
    CHECK(mount("none", "/dev", "devtmpfs", 0, NULL) == 0 && mount("none", "/proc", "proc", 0, NULL) == 0 &&
          mount("none", "/sys", "sysfs", 0, NULL) == 0 && mount("none", "/sys/fs/cgroup", "cgroup2", 0, NULL) == 0,
          "watchdog_mounts");
    CHECK(mkdir(IPC_DIR, 0755) == 0, "watchdog_ipc_directory");
    write_file(IPC_DIR "/heartbeat", "", 0);
    CHECK(chown(IPC_DIR "/heartbeat", WORKLOAD_ID, WORKLOAD_ID) == 0, "watchdog_heartbeat_owner");
    struct message ready = {.magic = IPC_MAGIC}; publish_message("ready", &ready);
    (void)await_message("watchdog-ready", 0);
    uint64_t deadline = now_ns() + WATCHDOG_TIMEOUT_NS;
    while (heartbeat() == 0 && now_ns() < deadline) sleep_ms(10);
    CHECK(heartbeat() > 0, "watchdog_workload_running");
    control_fd = open_control(1); query(control_fd, own_space);
    CHECK(memcmp(own_space, manager_space, 16) == 0, "watchdog_manager_identity");
    uint64_t cap = zero_case(kind) ? 0 : WATCHDOG_SMALL_CAP;
    struct usage before = usage_read(control_fd, MAX_CAP_NS);
    struct message closed = {.magic = IPC_MAGIC, .a = cap};
    struct usage after = install_ok(1, before, cap, closed.response, 1); closed.b = after.revision;
    watchdog_leaf();
    if (!strcmp(kind, "healthy")) {
        sleep_ms(5600);
        struct watchdog_stat stat = watchdog_read();
        CHECK(stat.status == 0 && stat.due > now_ns() && usage_read(control_fd, cap).revision == after.revision,
              "watchdog_healthy_manager_not_overridden");
        watchdog_finish(kind, cap, after.revision, stat);
        CHECK(kill(workload_pid, SIGKILL) == 0 && kill(recovery_pid, SIGKILL) == 0, "watchdog_healthy_cleanup");
        int status; CHECK(waitpid(workload_pid, &status, 0) == workload_pid && waitpid(recovery_pid, &status, 0) == recovery_pid,
                          "watchdog_healthy_reap");
        reboot(RB_POWER_OFF); _exit(120);
    }
    if (!strcmp(kind, "stopped")) {
        CHECK(kill(workload_pid, SIGSTOP) == 0, "watchdog_explicit_stop");
        int status; CHECK(waitpid(workload_pid, &status, WUNTRACED) == workload_pid && WIFSTOPPED(status) &&
                          WSTOPSIG(status) == SIGSTOP, "watchdog_confirm_jobstop");
        CHECK(watchdog_read().stopped == 1, "watchdog_jobstop_original_owner");
    }
    write_file(IPC_DIR "/watchdog-before-close", &closed, sizeof closed);
    char wp[24], rp[24];
    CHECK(snprintf(wp, sizeof wp, "%ld", (long)workload_pid) > 0 &&
          snprintf(rp, sizeof rp, "%ld", (long)recovery_pid) > 0, "watchdog_exec_pid_strings");
    char *args[] = {"/test/g1d-init", "--watchdog-after-exec", (char *)kind, wp, rp, NULL};
    record("G1DW_MANAGER_CLOSE case=%s original_revision=%" PRIu64 " failure=exec_revoke", kind, after.revision);
    execv(args[0], args); failure("watchdog_exec_returned", __LINE__);
    _exit(120);
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc > 1 && !strcmp(argv[1], "--watchdog-after-exec")) watchdog_after_exec(argc, argv);
    CHECK(argc == 2, "watchdog_initial_case");
    const char *kind = argv[1];
    CHECK(!strcmp(kind, "restore") || !strcmp(kind, "healthy") || zero_case(kind) ||
          !strcmp(kind, "stopped") || !strcmp(kind, "recovered"), "watchdog_known_case");
    bootstrap();
    if (role == 1) watchdog_manager(kind);
    else if (role == 2) watchdog_workload();
    else watchdog_recovery(kind);
    return 121;
}
