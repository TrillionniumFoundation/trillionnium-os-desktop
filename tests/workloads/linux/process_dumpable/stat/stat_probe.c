#define _GNU_SOURCE
#include <errno.h>
#include <grp.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

/* Exactly one owned child. Only /proc/stat numerical fields are observed. */
static unsigned failures;
static void check(const char *name, int okay) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, okay ? "true" : "false");
    if (!okay) failures++;
}
static void exact(int fd, void *p, size_t length, int writing) {
    char *data = p;
    while (length) {
        ssize_t n = writing ? write(fd, data, length) : read(fd, data, length);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) _exit(90);
        data += n; length -= (size_t)n;
    }
}
static void drop_own_privileges(void) {
    if (geteuid() == 0) {
        for (int c = 0; c <= 40; c++)
            if (prctl(PR_CAPBSET_DROP, c, 0, 0, 0) && errno != EINVAL) _exit(91);
        if (setgroups(0, NULL) || setresgid(60001, 60001, 60001) ||
            setresuid(60001, 60001, 60001)) _exit(92);
    }
    struct __user_cap_header_struct h = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct c[2] = {{0}, {0}};
    if (syscall(SYS_capset, &h, c) || syscall(SYS_capget, &h, c) ||
        c[0].permitted || c[1].permitted || c[0].effective || c[1].effective ||
        prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L)) _exit(93);
}
static int read_stat(pid_t child, unsigned long long fields[53]) {
    char path[80], data[4096];
    snprintf(path, sizeof(path), "/proc/%d/stat", child);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    ssize_t n = read(fd, data, sizeof(data) - 1);
    close(fd);
    if (n <= 0 || n == (ssize_t)sizeof(data) - 1) return 0;
    data[n] = 0;
    if (strtoul(data, NULL, 10) != (unsigned long)child) return 0;
    char *last = strrchr(data, ')');
    if (!last || last[1] != ' ') return 0;
    char *save = NULL, *value = strtok_r(last + 2, " \n", &save);
    for (unsigned field = 3; field <= 52; field++) {
        if (!value) return 0;
        if (field != 3) {
            char *end = NULL;
            errno = 0;
            fields[field] = strtoull(value, &end, 10);
            if (errno || !end || *end) return 0;
        }
        value = strtok_r(NULL, " \n", &save);
    }
    return value == NULL;
}
static void observe(pid_t child, int dumpable, unsigned long long *starttime) {
    unsigned long long f[53] = {0};
    if (!read_stat(child, f)) { check("stat_exact_52_fields_parsed", 0); return; }
    check("stat_exact_52_fields_parsed", 1);
    if (!*starttime) *starttime = f[22];
    check("ordinary_starttime_stable_nonzero", f[22] > 0 && f[22] == *starttime);
    check("ordinary_vsize_readable_nonzero", f[23] > 0);
    /* RSS is asynchronously accounted by Linux and can legitimately be zero. */
    check("ordinary_rss_readable_bounded", f[24] <= (1ULL << 32));
    const unsigned address_fields[] = {26, 27, 28, 45, 46, 47, 48, 49, 50, 51};
    for (unsigned i = 0; i < sizeof(address_fields) / sizeof(address_fields[0]); i++) {
        unsigned field = address_fields[i];
        unsigned long long expected = field == 26 || field == 27 ? 1 : 0;
        int okay = dumpable ? f[field] > 1 : f[field] == expected;
        printf("{\"stage_dumpable\":%d,\"field\":%u,\"masked_value\":%llu,\"expected_mask\":%llu,\"passed\":%s}\n",
               dumpable, field, dumpable ? 0 : f[field], expected, okay ? "true" : "false");
        if (!okay) failures++;
    }
    check("live_child_exit_code_zero", f[52] == 0);
    printf("{\"stage_dumpable\":%d,\"ordinary_fields_remain_readable\":true,\"only_owned_child\":true}\n", dumpable);
}
int main(void) {
    alarm(20);
    setvbuf(stdout, NULL, _IOLBF, 0);
    drop_own_privileges();
    printf("{\"suite\":\"dumpable-stat-v3\",\"observer_uid\":%u,\"cap_eff\":0,\"cap_prm\":0,\"nnp\":1}\n", getuid());
    int command[2], reply[2];
    if (pipe(command) || pipe(reply)) return 94;
    pid_t child = fork();
    if (child < 0) return 95;
    if (child == 0) {
        close(command[1]); close(reply[0]);
        for (;;) {
            char c;
            exact(command[0], &c, 1, 0);
            if (c == 'Q') _exit(0);
            int target = c == '1' ? 1 : 0;
            int r = prctl(PR_SET_DUMPABLE, (long)target);
            int actual = prctl(PR_GET_DUMPABLE);
            int result[2] = {r, actual};
            exact(reply[1], result, sizeof(result), 1);
        }
    }
    close(command[0]); close(reply[1]);
    unsigned long long starttime = 0;
    for (unsigned phase = 0; phase < 3; phase++) {
        char c = phase == 1 ? '1' : '0';
        int result[2];
        exact(command[1], &c, 1, 1); exact(reply[0], result, sizeof(result), 0);
        check("child_set_get_agree", result[0] == 0 && result[1] == (c == '1'));
        observe(child, c == '1', &starttime);
    }
    char quit = 'Q'; exact(command[1], &quit, 1, 1);
    int status = -1;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    int reaped = waited == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
    check("owned_child_reaped", reaped);
    close(command[1]); close(reply[0]);
    printf("{\"summary\":true,\"violations\":%u,\"all_children_reaped\":%s}\n", failures, reaped ? "true" : "false");
    return failures ? 42 : 0;
}
