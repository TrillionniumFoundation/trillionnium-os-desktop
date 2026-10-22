/* SPDX-License-Identifier: MPL-2.0 */
/* Included by g1d_init.c. These are real guest syscalls, never host fixtures.
 * Only the original cgroup pids controller owns the task budget. Probe IPC
 * coordinates observations; it cannot grant CPU or cgroup authority. */
#define WORKLOAD_PIDS_MAX 16U
#define PIDS_STACK_BYTES (64U * 1024U)

static void pids_pipe(int pair[2]) {
    CHECK(pipe2(pair, O_CLOEXEC) == 0, "pids_pipe");
}
static void pids_send(int fd, char byte) {
    CHECK(write(fd, &byte, 1) == 1, "pids_pipe_write");
}
static char pids_receive(int fd) {
    char byte;
    ssize_t n;
    do { n = read(fd, &byte, 1); } while (n < 0 && errno == EINTR);
    CHECK(n == 1, "pids_pipe_read");
    return byte;
}
static void pids_wait(pid_t child) {
    int status;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "pids_child_exit");
}
static void pids_leaf(pid_t pid, char path[384]) {
    char proc[64], text[256];
    CHECK(snprintf(proc, sizeof proc, "/proc/%ld/cgroup", (long)pid) > 0, "pids_proc_path");
    int fd = open(proc, O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "pids_proc_open");
    ssize_t n = read(fd, text, sizeof text - 1);
    CHECK(n >= 5 && n < (ssize_t)sizeof text - 1 && close(fd) == 0, "pids_proc_read");
    text[n] = 0;
    CHECK(strncmp(text, "0::/", 4) == 0 && text[n - 1] == '\n' &&
          strchr(text, '\n') == text + n - 1, "pids_proc_exact");
    text[n - 1] = 0;
    CHECK(snprintf(path, 384, "/sys/fs/cgroup%s", text + 3) > 0, "pids_leaf_path");
}
static void pids_attr_path(const char *leaf, const char *attr, char path[448]) {
    int n = snprintf(path, 448, "%s/%s", leaf, attr);
    CHECK(n > 0 && n < 448, "pids_attr_path");
}
static unsigned pids_value(const char *leaf, const char *attr) {
    char path[448], text[32], *end;
    pids_attr_path(leaf, attr, path);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "pids_value_open");
    ssize_t n = read(fd, text, sizeof text - 1);
    CHECK(n > 0 && n < (ssize_t)sizeof text - 1 && close(fd) == 0, "pids_value_read");
    text[n] = 0;
    errno = 0;
    unsigned long value = strtoul(text, &end, 10);
    CHECK(errno == 0 && end != text && strcmp(end, "\n") == 0 && value <= UINT_MAX,
          "pids_value_exact");
    return (unsigned)value;
}
static void pids_write(const char *leaf, const char *attr, const char *value) {
    char path[448];
    pids_attr_path(leaf, attr, path);
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    CHECK(fd >= 0 && write(fd, value, strlen(value)) == (ssize_t)strlen(value) && close(fd) == 0,
          "pids_attr_write");
}
static void pids_move(const char *leaf, pid_t pid) {
    char text[32];
    CHECK(snprintf(text, sizeof text, "%ld", (long)pid) > 0, "pids_move_format");
    pids_write(leaf, "cgroup.procs", text);
}
static void pids_count(const char *leaf, unsigned expected) {
    CHECK(pids_value(leaf, "pids.current") == expected, "pids_current_exact");
}
static void pids_text(const char *leaf, const char *attr, const char *expected) {
    char path[448], text[128];
    pids_attr_path(leaf, attr, path);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "pids_text_open");
    ssize_t n = read(fd, text, sizeof text - 1);
    CHECK(n >= 0 && n < (ssize_t)sizeof text - 1 && close(fd) == 0, "pids_text_read");
    text[n] = 0;
    CHECK(strcmp(text, expected) == 0, "pids_text_exact");
}
static void pids_waitable(pid_t child) {
    siginfo_t info;
    memset(&info, 0, sizeof info);
    CHECK(waitid(P_PID, (id_t)child, &info, WEXITED | WNOWAIT) == 0 &&
          info.si_pid == child && info.si_code == CLD_EXITED && info.si_status == 0,
          "pids_zombie_retained_wnowait");
}
static int pids_create(pthread_t *thread, void *(*entry)(void *), void *arg) {
    pthread_attr_t attr;
    CHECK(pthread_attr_init(&attr) == 0 && pthread_attr_setstacksize(&attr, PIDS_STACK_BYTES) == 0,
          "pids_thread_attr");
    int result = pthread_create(thread, &attr, entry, arg);
    CHECK(pthread_attr_destroy(&attr) == 0, "pids_thread_attr_destroy");
    return result;
}
static void *pids_empty_thread(void *unused) {
    (void)unused;
    return NULL;
}
static void pids_fork_denied(void) {
    errno = 0;
    pid_t result = fork();
    if (result == 0) _exit(0);
    CHECK(result == -1 && errno == EAGAIN, "pids_fork_must_return_eagain");
}
static void pids_thread_denied(void) {
    pthread_t thread;
    int rc = pids_create(&thread, pids_empty_thread, NULL);
    if (rc != EAGAIN)
        record("G1D_PIDS_THREAD_LIMIT_UNSAFE rc=%d expected=11 pid=%ld parent=%ld",
               rc, (long)getpid(), (long)getppid());
    CHECK(rc == EAGAIN, "pids_thread_must_return_eagain");
}
static void pids_thread_reused(void) {
    pthread_t thread;
    CHECK(pids_create(&thread, pids_empty_thread, NULL) == 0 && pthread_join(thread, NULL) == 0,
          "pids_refunded_thread_reusable");
}
static void *pids_gate_thread(void *arg) {
    int fd = *(int *)arg;
    char byte;
    ssize_t n;
    do { n = read(fd, &byte, 1); } while (n < 0 && errno == EINTR);
    CHECK(n == 0, "pids_thread_gate_eof");
    return NULL;
}
static void pids_await_leader_exit(pid_t pid) {
    char path[64], text[1024];
    CHECK(snprintf(path, sizeof path, "/proc/%ld/stat", (long)pid) > 0, "pids_leader_stat_path");
    uint64_t deadline = now_ns() + UINT64_C(5000000000);
    while (now_ns() < deadline) {
        int fd = open(path, O_RDONLY | O_CLOEXEC);
        CHECK(fd >= 0, "pids_leader_stat_open");
        ssize_t n = read(fd, text, sizeof text - 1);
        CHECK(n > 0 && n < (ssize_t)sizeof text - 1 && close(fd) == 0, "pids_leader_stat_read");
        text[n] = 0;
        char *comm_end = strrchr(text, ')');
        CHECK(comm_end != NULL && strlen(comm_end) > 3, "pids_leader_stat_layout");
        if (comm_end[1] == ' ' && comm_end[2] == 'Z' && comm_end[3] == ' ') return;
        sleep_ms(1);
    }
    failure("pids_leader_exit_timeout", __LINE__);
}

/* The manager's separate, ordinary hierarchy tests activation, both hierarchical
 * rejection paths, rollback, full thread-group migration, and a dead leader.
 * It does not move a process into or out of the trusted workload leaf. */
static void pids_accounting(void) {
    const char *parent = "/sys/fs/cgroup/g1d-pids-accounting";
    const char *one = "/sys/fs/cgroup/g1d-pids-accounting/one";
    const char *two = "/sys/fs/cgroup/g1d-pids-accounting/two";
    CHECK(mkdir(parent, 0755) == 0 && mkdir(one, 0755) == 0 && mkdir(two, 0755) == 0,
          "pids_accounting_directories");
    pids_write(parent, "pids.max", "4");
    int commands[2], replies[2], gate[2];
    pids_pipe(commands); pids_pipe(replies); pids_pipe(gate);
    pid_t child = fork();
    CHECK(child >= 0, "pids_accounting_fork");
    if (child == 0) {
        close(commands[1]); close(replies[0]); close(gate[1]);
        pthread_t threads[2];
        CHECK(pids_create(&threads[0], pids_gate_thread, &gate[0]) == 0 &&
              pids_create(&threads[1], pids_gate_thread, &gate[0]) == 0, "pids_accounting_threads");
        pids_send(replies[1], 'R');
        for (;;) {
            char command = pids_receive(commands[0]);
            if (command == 'D') { pids_fork_denied(); pids_thread_denied(); }
            else if (command == 'A') pids_thread_reused();
            else if (command == 'X') {
                pids_send(replies[1], command);
                syscall(SYS_exit, 0); /* Only the leader exits; two threads remain. */
                _exit(126);
            } else failure("pids_accounting_command", __LINE__);
            pids_send(replies[1], command);
        }
    }
    close(commands[0]); close(replies[1]); close(gate[0]);
    CHECK(pids_receive(replies[0]) == 'R', "pids_accounting_ready");
    pids_move(one, child);
    pids_count(parent, 3);
    /* Activate after the threaded process joined an inactive descendant. */
    pids_write(parent, "cgroup.subtree_control", "+pids");
    pids_count(one, 3); pids_count(two, 0); pids_count(parent, 3);
    pids_write(one, "pids.max", "3");
    pids_send(commands[1], 'D'); CHECK(pids_receive(replies[0]) == 'D', "pids_leaf_rejected");
    pids_count(one, 3); pids_count(parent, 3);
    pids_write(one, "pids.max", "16"); pids_write(parent, "pids.max", "3");
    pids_send(commands[1], 'D'); CHECK(pids_receive(replies[0]) == 'D', "pids_ancestor_rejected");
    pids_count(one, 3); pids_count(parent, 3);
    pids_write(parent, "pids.max", "4");
    pids_send(commands[1], 'A'); CHECK(pids_receive(replies[0]) == 'A', "pids_ancestor_rollback_reused");
    pids_count(one, 3); pids_count(parent, 3);
    pids_write(two, "pids.max", "1");
    pids_move(two, child); /* Organizational migration may exceed pids.max. */
    pids_count(one, 0); pids_count(two, 3); pids_count(parent, 3);
    pids_send(commands[1], 'D'); CHECK(pids_receive(replies[0]) == 'D', "pids_migrated_rejected");
    pids_move("/sys/fs/cgroup", child);
    pids_count(one, 0); pids_count(two, 0); pids_count(parent, 0);
    pids_send(commands[1], 'A'); CHECK(pids_receive(replies[0]) == 'A', "pids_root_reused");
    pids_move(one, child); pids_count(one, 3); pids_count(parent, 3);
    pids_send(commands[1], 'X'); CHECK(pids_receive(replies[0]) == 'X', "pids_leader_exit_ack");
    pids_await_leader_exit(child); pids_count(one, 3);
    pids_move(two, child);
    pids_count(one, 0); pids_count(two, 3); pids_count(parent, 3);
    CHECK(close(gate[1]) == 0, "pids_accounting_release");
    pids_waitable(child);
    unsigned retained = pids_value(two, "pids.current"), ancestor = pids_value(parent, "pids.current");
    record("G1D_PIDS_ZOMBIE_RETAINED current=%u ancestor=%u wnowait=1", retained, ancestor);
    CHECK(retained == 1 && ancestor == 1, "pids_zombie_charge_retained");
    pids_text(two, "cgroup.procs", "");
    pids_text(two, "cgroup.events", "populated 0\nfrozen 0\n");
    pids_text(parent, "cgroup.events", "populated 0\nfrozen 0\n");
    pids_write(two, "cgroup.subtree_control", "+pids");
    pids_write(two, "cgroup.subtree_control", "-pids");
    pids_count(two, 1);
    pids_wait(child);
    pids_count(one, 0); pids_count(two, 0); pids_count(parent, 0);
    close(commands[1]); close(replies[0]);
    /* Kernel CPU leases may outlive waitpid for the last scheduler debit. */
    for (unsigned attempt = 0; rmdir(one) != 0; ++attempt) {
        CHECK(errno == EBUSY && attempt < 1000, "pids_remove_one"); sleep_ms(1);
    }
    for (unsigned attempt = 0; rmdir(two) != 0; ++attempt) {
        CHECK(errno == EBUSY && attempt < 1000, "pids_remove_two"); sleep_ms(1);
    }
    CHECK(rmdir(parent) == 0, "pids_remove_parent");
    record("G1D_PIDS_ACCOUNTING tasks=3 activated=3 leaf_errno=11 ancestor_errno=11 rollback_reused=1 migrated=3 moved_root=0 retained_leader=3 zombie=1 zombie_populated=0 final=0");
}

static unsigned pids_saturated(void) {
    unsigned char bytes[8];
    int fd = open(IPC_DIR "/pids-saturated", O_RDONLY | O_CLOEXEC);
    CHECK(fd >= 0, "pids_saturated_open");
    ssize_t n = pread(fd, bytes, sizeof bytes, 0);
    CHECK((n == 0 || n == 8) && close(fd) == 0, "pids_saturated_read");
    CHECK(n == 0 || get64(bytes) == WORKLOAD_PIDS_MAX, "pids_saturated_exact");
    return n == 8 ? WORKLOAD_PIDS_MAX : 0;
}
static void pids_role_reserve(void) {
    char own[384], leaf[384];
    CHECK((role == 1 && getpid() == manager_pid) || (role == 3 && getpid() == recovery_pid),
          "pids_reserve_actual_role");
    pids_leaf(getpid(), own); pids_leaf(workload_pid, leaf);
    CHECK(strcmp(own, "/sys/fs/cgroup/") == 0, "pids_reserve_outside_workload");
    pids_count(leaf, WORKLOAD_PIDS_MAX);
    pid_t child = fork();
    CHECK(child >= 0, "pids_reserved_role_fork");
    if (child == 0) {
        pids_leaf(getpid(), own);
        CHECK(strcmp(own, "/sys/fs/cgroup/") == 0 && getuid() == 0, "pids_reserved_child_root");
        _exit(0);
    }
    pids_wait(child); pids_count(leaf, WORKLOAD_PIDS_MAX);
    record("G1D_PIDS_ROLE_RESERVE role=%" PRIu64 " pid=%ld child=%ld workload_current=16 root_member=1 child_exit=0",
           role, (long)getpid(), (long)child);
}
static int pids_unexpected_clone(void *unused) {
    (void)unused;
    syscall(SYS_exit, 0);
    return 0;
}
static void pids_failed_clone_rollback(const char *leaf) {
    unsigned char *stack = mmap(NULL, PIDS_STACK_BYTES, PROT_READ | PROT_WRITE,
                               MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    CHECK(stack != MAP_FAILED, "pids_bad_clone_stack");
    for (unsigned i = 0; i < 4; ++i) {
        int flags = CLONE_PARENT_SETTID | (i < 2 ? SIGCHLD : CLONE_VM | CLONE_SIGHAND | CLONE_THREAD);
        errno = 0;
        int rc = clone(pids_unexpected_clone, stack + PIDS_STACK_BYTES, flags, NULL,
                       (pid_t *)(uintptr_t)1, NULL, NULL);
        CHECK(rc == -1 && errno == EFAULT, "pids_clone_copyout_efault");
        pids_count(leaf, 1);
    }
    CHECK(munmap(stack, PIDS_STACK_BYTES) == 0, "pids_bad_clone_stack_release");
    record("G1D_PIDS_CLONE_ROLLBACK fork_cases=2 thread_cases=2 errno=14 before=1 after=1");
}
static void pids_permission_denied(const char *leaf, const char *attr, const char *name) {
    char path[448];
    pids_attr_path(leaf, attr, path);
    errno = 0;
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    int saved = errno;
    if (fd >= 0) close(fd);
    record("G1D_PIDS_BOUNDARY name=%s rc=%d errno=%d", name, fd, saved);
    CHECK(fd == -1 && saved == EACCES, "pids_workload_write_denied");
}
static void pids_descendants(const char *leaf) {
    int ready[2], release[2];
    pids_pipe(ready); pids_pipe(release);
    pid_t branch = fork();
    CHECK(branch >= 0, "pids_branch_fork");
    if (branch == 0) {
        close(ready[0]); close(release[1]);
        int gate[2]; pids_pipe(gate);
        pid_t children[WORKLOAD_PIDS_MAX - 2];
        for (unsigned i = 0; i < WORKLOAD_PIDS_MAX - 2; ++i) {
            children[i] = fork();
            CHECK(children[i] >= 0, "pids_grandchild_fork");
            if (children[i] == 0) {
                close(gate[1]);
                char byte;
                CHECK(read(gate[0], &byte, 1) == 0, "pids_grandchild_release");
                _exit(0);
            }
        }
        close(gate[0]);
        pids_count(leaf, WORKLOAD_PIDS_MAX);
        pids_fork_denied(); pids_thread_denied();
        pids_send(ready[1], 'F');
        CHECK(pids_receive(release[0]) == 'R', "pids_branch_release");
        close(gate[1]);
        for (unsigned i = 0; i < WORKLOAD_PIDS_MAX - 2; ++i) pids_wait(children[i]);
        _exit(0);
    }
    close(ready[1]); close(release[0]);
    CHECK(pids_receive(ready[0]) == 'F', "pids_descendants_ready");
    pids_count(leaf, WORKLOAD_PIDS_MAX); pids_fork_denied(); pids_thread_denied();
    record("G1D_PIDS_DESCENDANTS current=16 branch=1 grandchildren=14 parent_fork_errno=11 child_fork_errno=11 thread_errno=11");
    unsigned char bytes[8]; put64(bytes, WORKLOAD_PIDS_MAX);
    int fd = open(IPC_DIR "/pids-saturated", O_WRONLY | O_CLOEXEC);
    CHECK(fd >= 0 && pwrite(fd, bytes, sizeof bytes, 0) == 8 && close(fd) == 0, "pids_publish_saturation");
    (void)await_message("pids-reserved", 0);
    pids_count(leaf, WORKLOAD_PIDS_MAX);
    pids_send(release[1], 'R'); pids_wait(branch);
    close(ready[0]); close(release[1]);
    pids_count(leaf, 1);
    pid_t reused = fork();
    CHECK(reused >= 0, "pids_fork_refund_reused");
    if (reused == 0) _exit(0);
    pids_wait(reused); pids_count(leaf, 1);
    record("G1D_PIDS_FORK_REFUND before=16 after=1 reused=1 final=1");
}
static void pids_threads(const char *leaf) {
    pthread_t threads[WORKLOAD_PIDS_MAX - 1];
    int gates[WORKLOAD_PIDS_MAX - 1][2];
    for (unsigned i = 0; i < WORKLOAD_PIDS_MAX - 1; ++i) {
        pids_pipe(gates[i]);
        CHECK(pids_create(&threads[i], pids_gate_thread, &gates[i][0]) == 0, "pids_workload_thread");
    }
    pids_count(leaf, WORKLOAD_PIDS_MAX); pids_thread_denied(); pids_fork_denied();
    close(gates[0][1]);
    CHECK(pthread_join(threads[0], NULL) == 0 && close(gates[0][0]) == 0, "pids_one_thread_refund");
    pids_count(leaf, WORKLOAD_PIDS_MAX - 1);
    pids_pipe(gates[0]);
    CHECK(pids_create(&threads[0], pids_gate_thread, &gates[0][0]) == 0, "pids_thread_slot_reused");
    pids_count(leaf, WORKLOAD_PIDS_MAX); pids_thread_denied();
    for (unsigned i = 0; i < WORKLOAD_PIDS_MAX - 1; ++i) {
        close(gates[i][1]);
        CHECK(pthread_join(threads[i], NULL) == 0 && close(gates[i][0]) == 0, "pids_thread_cleanup");
    }
    pids_count(leaf, 1);
    record("G1D_PIDS_THREADS threads=15 current=16 thread_errno=11 fork_errno=11 after_one_exit=15 reused=1 final=1");
}
static void pids_zombies(const char *leaf) {
    pid_t children[WORKLOAD_PIDS_MAX - 1];
    for (unsigned i = 0; i < WORKLOAD_PIDS_MAX - 1; ++i) {
        children[i] = fork();
        CHECK(children[i] >= 0, "pids_zombie_fork");
        if (children[i] == 0) _exit(0);
    }
    for (unsigned i = 0; i < WORKLOAD_PIDS_MAX - 1; ++i) pids_waitable(children[i]);
    pids_count(leaf, WORKLOAD_PIDS_MAX);
    char only_workload[32];
    CHECK(snprintf(only_workload, sizeof only_workload, "%ld\n", (long)getpid()) > 0, "pids_live_procs_format");
    pids_text(leaf, "cgroup.procs", only_workload);
    pids_fork_denied(); pids_thread_denied();
    pids_wait(children[0]); pids_count(leaf, WORKLOAD_PIDS_MAX - 1);
    children[0] = fork();
    CHECK(children[0] >= 0, "pids_reaped_zombie_reused");
    if (children[0] == 0) _exit(0);
    pids_waitable(children[0]); pids_count(leaf, WORKLOAD_PIDS_MAX); pids_fork_denied();
    for (unsigned i = 0; i < WORKLOAD_PIDS_MAX - 1; ++i) pids_wait(children[i]);
    pids_count(leaf, 1);
    record("G1D_PIDS_ZOMBIES retained=15 current=16 fork_errno=11 thread_errno=11 wnowait_refunded=0 after_one_reap=15 reused=1 live_procs=1 final=1");
}
static void *pids_exec_thread(void *unused) {
    (void)unused;
    char *args[] = {"/test/g1d-init", "--pids-after-exec", NULL};
    execv(args[0], args);
    failure("pids_nonleader_exec_returned", __LINE__);
    return NULL;
}
static void pids_exec_refund(const char *leaf) {
    pid_t child = fork();
    CHECK(child >= 0, "pids_exec_fork");
    if (child == 0) {
        pthread_t thread;
        CHECK(pids_create(&thread, pids_exec_thread, NULL) == 0, "pids_exec_thread");
        for (;;) pause(); /* The non-leader exec must terminate this old leader. */
    }
    pids_wait(child); pids_count(leaf, 1);
    record("G1D_PIDS_EXEC_REFUND final=1");
}
static void pids_after_exec(void) {
    char leaf[384];
    CHECK(getauxval(AT_HEPTA_BOOT) == 0 && getuid() == WORKLOAD_ID, "pids_exec_no_boot_authority");
    pids_leaf(getpid(), leaf);
    pids_count(leaf, 2);
    CHECK(pids_value(leaf, "pids.max") == WORKLOAD_PIDS_MAX, "pids_exec_preserved_limit");
    record("G1D_PIDS_NONLEADER_EXEC pid=%ld parent=%ld current=2 max=16 old_leader_refunded=1",
           (long)getpid(), (long)getppid());
}
static void pids_workload(void) {
    char leaf[384];
    pids_leaf(getpid(), leaf);
    CHECK(strncmp(leaf, "/sys/fs/cgroup/hepta-g1d-", 25) == 0, "pids_workload_bound_leaf");
    CHECK(pids_value(leaf, "pids.max") == WORKLOAD_PIDS_MAX, "pids_workload_boot_limit");
    pids_count(leaf, 1);
    record("G1D_PIDS_INITIAL pid=%ld max=16 current=1", (long)getpid());
    pids_permission_denied(leaf, "pids.max", "raise_limit");
    pids_permission_denied(leaf, "cgroup.procs", "membership");
    pids_permission_denied("/sys/fs/cgroup", "cgroup.procs", "escape_root");
    pids_permission_denied("/sys/fs/cgroup", "cgroup.subtree_control", "disable_controller");
    pids_failed_clone_rollback(leaf);
    pids_descendants(leaf);
    pids_zombies(leaf);
    pids_threads(leaf);
    pids_exec_refund(leaf);
    CHECK(pids_value(leaf, "pids.max") == WORKLOAD_PIDS_MAX &&
          pids_value(leaf, "pids.peak") == WORKLOAD_PIDS_MAX, "pids_workload_budget_unchanged");
    record("G1D_PIDS_COMPLETE max=16 current=1 peak=16 fork_threads_zombies=true memory_controller=false");
}
