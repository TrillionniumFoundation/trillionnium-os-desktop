// SPDX-License-Identifier: MPL-2.0
// Real Linux ABI regression for the protected host's exact process identity.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned cases, failures;
static void result(const char *name, int ok)
{
    cases++;
    failures += !ok;
    printf("PRIV_STATUS_CASE name=%s pass=%d\n", name, !!ok);
}

static int field(pid_t pid, long tid, const char *key, char value[256])
{
    char path[128], buffer[16384];
    if (tid) snprintf(path, sizeof path, "/proc/%ld/task/%ld/status", (long)pid, tid);
    else snprintf(path, sizeof path, "/proc/%ld/status", (long)pid);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    size_t used = 0;
    while (used < sizeof buffer - 1) {
        ssize_t count = read(fd, buffer + used, sizeof buffer - 1 - used);
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) { close(fd); return -1; }
        if (!count) break;
        used += (size_t)count;
    }
    close(fd);
    if (used == sizeof buffer - 1) return -1;
    buffer[used] = 0;
    size_t keylen = strlen(key);
    char *line = buffer;
    while (*line) {
        char *end = strchr(line, '\n');
        if (!end) return -1;
        if ((size_t)(end - line) >= keylen && !memcmp(line, key, keylen)) {
            size_t length = (size_t)(end - line) - keylen;
            if (length >= 256) return -1;
            memcpy(value, line + keylen, length);
            value[length] = 0;
            return 0;
        }
        line = end + 1;
    }
    return -1;
}

static int nnp(pid_t pid, long tid)
{
    char value[256];
    if (field(pid, tid, "NoNewPrivs:\t", value)) return -1;
    return !strcmp(value, "0") ? 0 : !strcmp(value, "1") ? 1 : -1;
}

static int exact_ids(pid_t pid, const char *key, unsigned expected)
{
    char value[256], trailing;
    unsigned a, b, c, d;
    return !field(pid, 0, key, value) && sscanf(value, "%u %u %u %u %c", &a, &b, &c, &d, &trailing) == 4
        && a == expected && b == expected && c == expected && d == expected;
}

static int empty_groups(pid_t pid)
{
    char value[256];
    if (field(pid, 0, "Groups:", value)) return 0;
    return strspn(value, " \t") == strlen(value);
}

static int no_caps(pid_t pid)
{
    static const char *keys[] = {"CapInh:\t", "CapPrm:\t", "CapEff:\t", "CapBnd:\t", "CapAmb:\t"};
    char value[256];
    for (unsigned i = 0; i < sizeof keys / sizeof keys[0]; i++)
        if (field(pid, 0, keys[i], value) || strcmp(value, "0000000000000000")) return 0;
    return 1;
}

struct thread_check { int initial; int ok; };
static void *thread_nnp(void *argument)
{
    struct thread_check *check = argument;
    long tid = syscall(SYS_gettid);
    check->ok = prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0
        && prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1
        && nnp(getpid(), tid) == 1 && nnp(getpid(), 0) == check->initial;
    return NULL;
}

static int child_identity(void)
{
    return nnp(getpid(), 0) == 1 && prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1
        && exact_ids(getpid(), "Uid:", 60001) && exact_ids(getpid(), "Gid:", 60001)
        && empty_groups(getpid()) && no_caps(getpid());
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--after-exec")) {
        int ok = child_identity();
        printf("PRIV_STATUS_EXEC_CHECK pass=%d\n", ok);
        return ok ? 0 : 1;
    }
    if (argc != 1 || geteuid() != 0) return 2;
    int initial = prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0);
    if (nnp(getpid(), 0) < 0) { puts("PRIV_STATUS_UNAVAILABLE field=NoNewPrivs"); return 1; }
    // A pre-enabled parent would not exercise per-thread isolation at all.
    result("initial_nnp_agrees", initial == 0 && nnp(getpid(), 0) == 0);
    struct thread_check check = {.initial = initial, .ok = 0};
    pthread_t thread;
    if (pthread_create(&thread, NULL, thread_nnp, &check)) return 3;
    if (pthread_join(thread, NULL)) return 3;
    result("per_thread_nnp", check.ok);
    result("main_thread_nnp_unchanged", nnp(getpid(), 0) == initial && prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == initial);

    int ready[2], release[2];
    if (pipe2(ready, O_CLOEXEC) || pipe2(release, O_CLOEXEC)) return 3;
    fflush(NULL);
    pid_t child = fork();
    if (child < 0) return 3;
    if (!child) {
        close(ready[0]); close(release[1]);
        gid_t groups[2] = {100, 200};
        char group_text[256];
        unsigned first, second;
        char trailing;
        int ok = setgroups(2, groups) == 0 && !field(getpid(), 0, "Groups:", group_text)
            && sscanf(group_text, "%u %u %c", &first, &second, &trailing) == 2 && first == 100 && second == 200;
        printf("PRIV_STATUS_SETUP_CHECK pass=%d\n", ok);
        fflush(stdout);
        ok = ok && setgroups(0, NULL) == 0 && prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) == 0;
        for (int cap = 0; cap <= CAP_LAST_CAP && ok; cap++) ok = prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) == 0;
        ok = ok && setresgid(60001, 60001, 60001) == 0 && setresuid(60001, 60001, 60001) == 0;
        struct __user_cap_header_struct header = {.version = _LINUX_CAPABILITY_VERSION_3, .pid = 0};
        struct __user_cap_data_struct data[2] = {{0}, {0}};
        ok = ok && syscall(SYS_capset, &header, data) == 0 && prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0;
        errno = 0;
        int cannot_clear = prctl(PR_SET_NO_NEW_PRIVS, 0, 0, 0, 0) == -1 && errno == EINVAL;
        char report = ok && cannot_clear && child_identity() ? '1' : '0';
        if (write(ready[1], &report, 1) != 1) _exit(4);
        close(ready[1]);
        char byte;
        if (read(release[0], &byte, 1) != 0) _exit(4);
        close(release[0]);
        execl(argv[0], argv[0], "--after-exec", (char *)NULL);
        _exit(5);
    }
    close(ready[1]); close(release[0]);
    char report = 0;
    ssize_t received = read(ready[0], &report, 1);
    close(ready[0]);
    result("child_sets_and_cannot_clear_nnp", received == 1 && report == '1');
    result("parent_attests_child_nnp", nnp(child, 0) == 1);
    result("four_child_uids", exact_ids(child, "Uid:", 60001));
    result("four_child_gids", exact_ids(child, "Gid:", 60001));
    result("child_groups_empty", empty_groups(child));
    result("five_child_capsets_zero", no_caps(child));
    result("parent_uid_unchanged", exact_ids(getpid(), "Uid:", 0));
    result("parent_nnp_unchanged", nnp(getpid(), 0) == initial);
    close(release[1]);
    int status = 0;
    result("exec_preserves_identity", waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    printf("PRIV_STATUS_COMPLETE cases=%u failures=%u\n", cases, failures);
    return failures ? 1 : 0;
}
