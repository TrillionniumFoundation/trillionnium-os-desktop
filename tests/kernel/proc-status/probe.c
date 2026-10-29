// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <limits.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned failed;
static pthread_barrier_t barrier;
static pid_t worker_tid;
static const char *self;
static const gid_t initial_groups[] = {23, 65539, 70003};
static const gid_t leader_groups[] = {31, 80001};
static void check(const char *name, int okay) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, okay ? "true" : "false");
    if (!okay) ++failed;
}
static void sync_thread(void) {
    int r = pthread_barrier_wait(&barrier);
    if (r && r != PTHREAD_BARRIER_SERIAL_THREAD) _exit(90);
}
static int status_bytes(const char *path, char buffer[16384]) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    size_t length = 0;
    for (;;) {
        /* Deliberately split lines across proc read_at offsets. */
        ssize_t n = read(fd, buffer + length, 97);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 || length + (size_t)n >= 16384 - 97) {
            close(fd); return -1;
        }
        if (!n) break;
        length += (size_t)n;
    }
    close(fd); buffer[length] = 0; return 0;
}
static int status_nnp(const char *path) {
    char buffer[16384];
    if (status_bytes(path, buffer)) return -1;
    unsigned found = 0; int value = -1;
    for (char *line = buffer; *line;) {
        char *end = strchr(line, '\n');
        if (!end) return -1;
        *end = 0;
        if (!strncmp(line, "NoNewPrivs:", 11)) {
            ++found;
            if (!strcmp(line, "NoNewPrivs:\t0")) value = 0;
            else if (!strcmp(line, "NoNewPrivs:\t1")) value = 1;
            else return -1;
        }
        line = end + 1;
    }
    return found == 1 ? value : -1;
}
static int status_groups(const char *path, const gid_t *expected, size_t count) {
    char buffer[16384];
    if (status_bytes(path, buffer)) return 0;
    unsigned found = 0;
    for (char *line = buffer; *line;) {
        char *end = strchr(line, '\n');
        if (!end) return 0;
        *end = 0;
        if (!strncmp(line, "Groups:", 7)) {
            ++found;
            size_t index = 0;
            for (char *value = line + 7;;) {
                while (*value == ' ' || *value == '\t') ++value;
                if (!*value) break;
                if (*value < '0' || *value > '9') return 0;
                errno = 0; char *next;
                unsigned long group = strtoul(value, &next, 10);
                if (errno || group > UINT_MAX || index >= count ||
                    group != expected[index++] || (*next && *next != ' ' && *next != '\t')) return 0;
                value = next;
            }
            if (index != count) return 0;
        }
        line = end + 1;
    }
    return found == 1;
}
static int current_groups(const gid_t *expected, size_t count) {
    gid_t actual[16];
    int n = (int)syscall(SYS_getgroups, 16, actual);
    return n >= 0 && (size_t)n == count && (!count || !memcmp(actual, expected, count * sizeof(gid_t)));
}
static void task_path(char path[128], pid_t pid, pid_t tid) {
    snprintf(path, 128, "/proc/%d/task/%d/status", pid, tid);
}
static void child_drop(void) {
    check("original_agent_clear_groups", setgroups(0, NULL) == 0);
    int dropped = 1;
    for (int cap = 0; cap <= 40; ++cap)
        dropped &= prctl(PR_CAPBSET_DROP, cap, 0L, 0L, 0L) == 0;
    check("original_agent_clear_bounding", dropped);
    check("original_agent_clear_ambient", prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0L, 0L, 0L) == 0);
    check("original_agent_lock_securebits", prctl(PR_SET_SECUREBITS, 15L, 0L, 0L, 0L) == 0);
    check("original_agent_drop_uid_gid", setresgid(60002,60002,60002) == 0 && setresuid(60002,60002,60002) == 0);
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    check("original_agent_capset_zero", syscall(SYS_capset, &header, data) == 0);
    check("original_agent_set_nnp", prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) == 0);
    char status[16384];
    int read_ok = status_bytes("/proc/self/status", status) == 0;
    check("original_agent_uid_readback", read_ok && strstr(status, "Uid:\t60002\t60002\t60002\t60002\n") != NULL);
    const char *caps[] = {"CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"};
    for (unsigned i = 0; i < sizeof caps / sizeof caps[0]; ++i) {
        char line[64]; snprintf(line, sizeof line, "%s:\t0000000000000000\n", caps[i]);
        check(caps[i], read_ok && strstr(status, line) != NULL);
    }
    check("original_agent_nnp_readback", status_nnp("/proc/self/status") == 1);
    check("original_agent_groups_empty_readback", current_groups(NULL, 0) && status_groups("/proc/self/status", NULL, 0));
}
static void *existing_thread(void *unused) {
    (void)unused;
    worker_tid = (pid_t)syscall(SYS_gettid);
    sync_thread(); sync_thread();
    char path[128]; task_path(path, getpid(), worker_tid);
    check("existing_thread_retains_nnp_zero", prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == 0 && status_nnp(path) == 0);
    check("self_status_reports_leader_not_reader", status_nnp("/proc/self/status") == 1);
    check("existing_thread_retains_original_groups", current_groups(initial_groups, 3) && status_groups(path, initial_groups, 3));
    check("thread_self_status_reports_leader_groups", status_groups("/proc/self/status", leader_groups, 2));
    /* Raw syscall deliberately changes this thread only, bypassing NPTL propagation. */
    check("thread_clears_own_groups", syscall(SYS_setgroups, 0, NULL) == 0);
    check("thread_reads_own_empty_groups", current_groups(NULL, 0) && status_groups(path, NULL, 0));
    check("thread_set_nnp", prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) == 0);
    sync_thread(); sync_thread(); return NULL;
}
static void *inherited_thread(void *unused) {
    (void)unused;
    char path[128]; task_path(path, getpid(), (pid_t)syscall(SYS_gettid));
    check("new_thread_inherits_nnp", prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == 1 && status_nnp(path) == 1);
    check("new_thread_inherits_groups", current_groups(leader_groups, 2) && status_groups(path, leader_groups, 2));
    return NULL;
}
static int wait_child(pid_t child) {
    int status = 0; pid_t got;
    do { got = waitpid(child, &status, 0); } while (got < 0 && errno == EINTR);
    return got == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
int main(int argc, char **argv) {
    alarm(30); setvbuf(stdout, NULL, _IOLBF, 0); self = argv[0];
    if (argc == 2 && !strcmp(argv[1], "--inherited-exec")) {
        check("exec_keeps_nnp", prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == 1 && status_nnp("/proc/self/status") == 1);
        check("exec_keeps_groups", current_groups(leader_groups, 2) && status_groups("/proc/self/status", leader_groups, 2));
        errno = 0;
        check("exec_cannot_unset_nnp", prctl(PR_SET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == -1 && errno == EINVAL && status_nnp("/proc/self/status") == 1);
        return failed != 0;
    }
    check("initial_nnp_zero", prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == 0 && status_nnp("/proc/self/status") == 0);
    const gid_t unordered_groups[] = {70003, 23, 65539};
    check("set_nonempty_groups", syscall(SYS_setgroups, 3, unordered_groups) == 0);
    check("actual_nonempty_groups_sorted", current_groups(initial_groups, 3) && status_groups("/proc/self/status", initial_groups, 3));
    check("nonempty_groups_cannot_pass_empty_policy", !status_groups("/proc/self/status", NULL, 0));
    int ready[2], release[2]; if (pipe(ready) || pipe(release)) return 91;
    pid_t child = fork();
    if (!child) {
        close(ready[0]); close(release[1]); failed = 0; child_drop();
        char byte = 'R'; if (write(ready[1], &byte, 1) != 1 || read(release[0], &byte, 1) != 1) _exit(92);
        close(ready[1]); close(release[0]); _exit(failed != 0);
    }
    if (child < 0) return 93;
    close(ready[1]); close(release[0]); char byte;
    if (read(ready[0], &byte, 1) != 1) return 94;
    char path[128]; snprintf(path, sizeof path, "/proc/%d/status", child);
    check("root_reads_dropped_child_nnp_one", status_nnp(path) == 1);
    check("root_reads_dropped_child_empty_groups", status_groups(path, NULL, 0));
    task_path(path, child, child); check("root_reads_dropped_child_task_nnp_one", status_nnp(path) == 1);
    check("root_reads_dropped_child_task_empty_groups", status_groups(path, NULL, 0));
    check("child_nnp_does_not_change_parent", status_nnp("/proc/self/status") == 0);
    check("child_groups_do_not_change_parent", current_groups(initial_groups, 3) && status_groups("/proc/self/status", initial_groups, 3));
    if (write(release[1], "R", 1) != 1) return 95;
    close(ready[0]); close(release[1]); check("original_agent_readback_child_exits", wait_child(child));
    pthread_t thread;
    if (pthread_barrier_init(&barrier, NULL, 2) || pthread_create(&thread, NULL, existing_thread, NULL)) return 96;
    sync_thread();
    check("leader_changes_only_own_groups", syscall(SYS_setgroups, 2, leader_groups) == 0);
    check("leader_reads_changed_groups", current_groups(leader_groups, 2) && status_groups("/proc/self/status", leader_groups, 2));
    check("leader_sets_nnp", prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) == 0);
    check("leader_reads_nnp_one", prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == 1 && status_nnp("/proc/self/status") == 1);
    task_path(path, getpid(), worker_tid); check("leader_reads_existing_thread_nnp_zero", status_nnp(path) == 0);
    check("leader_reads_existing_thread_original_groups", status_groups(path, initial_groups, 3));
    sync_thread(); sync_thread();
    check("leader_reads_changed_thread_nnp_one", status_nnp(path) == 1);
    check("leader_reads_changed_thread_empty_groups", status_groups(path, NULL, 0));
    check("thread_group_change_does_not_change_leader", current_groups(leader_groups, 2) && status_groups("/proc/self/status", leader_groups, 2));
    sync_thread(); check("existing_thread_joins", pthread_join(thread, NULL) == 0);
    check("barrier_destroy", pthread_barrier_destroy(&barrier) == 0);
    errno = 0;
    check("nnp_is_irreversible", prctl(PR_SET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == -1 && errno == EINVAL && status_nnp("/proc/self/status") == 1);
    if (pthread_create(&thread, NULL, inherited_thread, NULL)) return 97;
    check("inherited_thread_joins", pthread_join(thread, NULL) == 0);
    child = fork();
    if (!child) {
        failed = 0;
        check("fork_inherits_nnp", prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) == 1 && status_nnp("/proc/self/status") == 1);
        check("fork_inherits_groups", current_groups(leader_groups, 2) && status_groups("/proc/self/status", leader_groups, 2));
        if (failed) _exit(1);
        char *const arguments[] = {(char *)self, "--inherited-exec", NULL}; execv(self, arguments); _exit(98);
    }
    check("fork_exec_child_exits", child > 0 && wait_child(child));
    printf("{\"suite\":\"proc-credential-status-v2\",\"passed\":%s}\n", failed ? "false" : "true");
    return failed != 0;
}
