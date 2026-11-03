// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/fsuid.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>
#include <utime.h>

static int cases, failures;
static const struct timespec seed[2] = {{123456, 123000000}, {234567, 456000000}};
struct outcome { long actual; int error, unchanged, omit_preserved; };
enum time_kind { NOW_NULL, NOW_BOTH, EXPLICIT, NOW_OMIT, OMIT_NOW, OMIT_BOTH, EXPLICIT_OMIT };
enum call_kind { PATH, FD_READ, FD_WRITE, FD_RDWR, LEGACY_UTIME, LEGACY_UTIMES, LEGACY_FUTIMESAT, OPATH_EMPTY, OPATH_FD, SYMLINK };
struct scenario {
    const char *name;
    uid_t uid;
    gid_t gid;
    int supplementary;
    mode_t mode;
    enum time_kind times;
    enum call_kind call;
    int capability;
    int expected;
    int fsuid_owner;
};
#define USER(name, mode, times, call, expected) {name, 1001, 2001, 0, mode, times, call, -1, expected, 0}
#define OWNER(name, times, call) {name, 1000, 2001, 0, 0, times, call, -1, 0, 0}
static const struct scenario scenarios[] = {
    OWNER("owner_explicit_mode_zero", EXPLICIT, PATH),
    OWNER("owner_now_mode_zero", NOW_NULL, PATH),
    USER("other_now_no_write", 0444, NOW_NULL, PATH, EACCES),
    USER("other_both_now_no_write", 0444, NOW_BOTH, PATH, EACCES),
    USER("other_now_write", 0666, NOW_NULL, PATH, 0),
    USER("other_both_now_write", 0666, NOW_BOTH, PATH, 0),
    USER("other_explicit_write", 0666, EXPLICIT, PATH, EPERM),
    USER("other_now_omit_write", 0666, NOW_OMIT, PATH, EPERM),
    USER("other_omit_now_write", 0666, OMIT_NOW, PATH, EPERM),
    USER("other_both_omit_no_write", 0, OMIT_BOTH, PATH, 0),
    USER("other_explicit_no_write", 0444, EXPLICIT, PATH, EPERM),
    {"primary_group_now", 1001, 2000, 0, 0020, NOW_NULL, PATH, -1, 0, 0},
    {"supplementary_group_now", 1001, 2001, 1, 0020, NOW_BOTH, PATH, -1, 0, 0},
    {"group_precedes_other", 1001, 2001, 1, 0002, NOW_NULL, PATH, -1, EACCES, 0},
    USER("other_class_now", 0002, NOW_NULL, PATH, 0),
    USER("retained_wronly_not_authority", 0444, NOW_NULL, FD_WRITE, EACCES),
    USER("retained_rdwr_not_owner", 0666, EXPLICIT, FD_RDWR, EPERM),
    OWNER("owner_readonly_fd", EXPLICIT, FD_READ),
    USER("readonly_fd_write_dac", 0666, NOW_NULL, FD_READ, 0),
    {"fowner_explicit", 0, 0, 0, 0, EXPLICIT, PATH, CAP_FOWNER, 0, 0},
    {"fowner_now", 0, 0, 0, 0, NOW_NULL, PATH, CAP_FOWNER, 0, 0},
    {"dac_override_now", 0, 0, 0, 0, NOW_NULL, PATH, CAP_DAC_OVERRIDE, 0, 0},
    {"dac_override_not_explicit", 0, 0, 0, 0, EXPLICIT, PATH, CAP_DAC_OVERRIDE, EPERM, 0},
    {"root_without_caps_now", 0, 0, 0, 0, NOW_NULL, PATH, -1, EACCES, 0},
    {"root_without_caps_explicit", 0, 0, 0, 0, EXPLICIT, PATH, -1, EPERM, 0},
    {"fsuid_owner_explicit", 0, 0, 0, 0, EXPLICIT, PATH, -1, 0, 1},
    OWNER("owner_now_omit", NOW_OMIT, PATH),
    OWNER("owner_explicit_omit", EXPLICIT_OMIT, PATH),
    USER("utime_explicit_other", 0666, EXPLICIT, LEGACY_UTIME, EPERM),
    USER("utime_now_write", 0666, NOW_NULL, LEGACY_UTIME, 0),
    USER("utimes_explicit_other", 0666, EXPLICIT, LEGACY_UTIMES, EPERM),
    USER("utimes_now_write", 0666, NOW_NULL, LEGACY_UTIMES, 0),
    USER("futimesat_explicit_other", 0666, EXPLICIT, LEGACY_FUTIMESAT, EPERM),
    USER("futimesat_now_write", 0666, NOW_NULL, LEGACY_FUTIMESAT, 0),
    OWNER("opath_empty_owner", EXPLICIT, OPATH_EMPTY),
    {"opath_futimens_rejected", 1000, 2001, 0, 0, EXPLICIT, OPATH_FD, -1, EBADF, 0},
    OWNER("symlink_owner", EXPLICIT, SYMLINK),
    USER("symlink_other", 0777, EXPLICIT, SYMLINK, EPERM),
};
static void setup(int ok, const char *why) {
    if (!ok) { perror(why); printf("UT_SETUP_FAILED %s\n", why); exit(2); }
}
static int eqtime(struct timespec a, struct timespec b) {
    return a.tv_sec == b.tv_sec && a.tv_nsec == b.tv_nsec;
}
static long invoke(const struct scenario *s, const char *path, int fd) {
    struct timespec times[2] = {{345678, 321000000}, {456789, 654000000}};
    if (s->times == NOW_BOTH || s->times == NOW_OMIT) times[0].tv_nsec = UTIME_NOW;
    if (s->times == NOW_BOTH || s->times == OMIT_NOW) times[1].tv_nsec = UTIME_NOW;
    if (s->times == OMIT_NOW || s->times == OMIT_BOTH) times[0].tv_nsec = UTIME_OMIT;
    if (s->times == NOW_OMIT || s->times == OMIT_BOTH || s->times == EXPLICIT_OMIT) times[1].tv_nsec = UTIME_OMIT;
    const struct timespec *tp = s->times == NOW_NULL ? NULL : times;
    struct utimbuf old = {345678, 456789};
    struct timeval older[2] = {{345678, 321000}, {456789, 654000}};
    switch (s->call) {
    case LEGACY_UTIME: return syscall(SYS_utime, path, tp ? &old : NULL);
    case LEGACY_UTIMES: return syscall(SYS_utimes, path, tp ? older : NULL);
    case LEGACY_FUTIMESAT: return syscall(SYS_futimesat, AT_FDCWD, path, tp ? older : NULL);
    case FD_READ: case FD_WRITE: case FD_RDWR: case OPATH_FD: return futimens(fd, tp);
    case OPATH_EMPTY: return utimensat(fd, "", tp, AT_EMPTY_PATH);
    case SYMLINK: return utimensat(AT_FDCWD, path, tp, AT_SYMLINK_NOFOLLOW);
    default: return utimensat(AT_FDCWD, path, tp, 0);
    }
}
static void run_case(const char *root, const char *prefix, const struct scenario *s, unsigned index) {
    char path[256];
    snprintf(path, sizeof(path), "%s/case-%u", root, index);
    int fd = -1;
    if (s->call == SYMLINK) {
        setup(symlink("missing-target", path) == 0, "symlink");
        setup(lchown(path, 1000, 2000) == 0, "lchown");
    } else {
        fd = open(path, O_CREAT | O_EXCL | O_RDWR, 0600);
        setup(fd >= 0, "create");
        setup(fchown(fd, 1000, 2000) == 0 && fchmod(fd, s->mode) == 0, "owner/mode");
        close(fd);
        int flags = s->call == FD_WRITE ? O_WRONLY : s->call == FD_RDWR ? O_RDWR :
                    (s->call == OPATH_EMPTY || s->call == OPATH_FD) ? O_PATH : O_RDONLY;
        fd = open(path, flags);
        setup(fd >= 0, "retained fd");
    }
    setup(utimensat(AT_FDCWD, path, seed, s->call == SYMLINK ? AT_SYMLINK_NOFOLLOW : 0) == 0, "seed times");
    struct stat before, after;
    setup(lstat(path, &before) == 0, "before stat");
    int pipefd[2];
    setup(pipe(pipefd) == 0, "pipe");
    pid_t child = fork();
    setup(child >= 0, "fork");
    if (child == 0) {
        close(pipefd[0]);
        gid_t group = 2000;
        setup(setgroups(s->supplementary ? 1 : 0, &group) == 0, "setgroups");
        setup(setresgid(s->gid, s->gid, s->gid) == 0, "setresgid");
        setup(setresuid(s->uid, s->uid, s->uid) == 0, "setresuid");
        if (s->fsuid_owner) {
            setfsuid(1000);
            setup(setfsuid((uid_t)-1) == 1000, "setfsuid");
        }
        struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
        struct __user_cap_data_struct caps[2] = {{0}};
        if (s->capability >= 0) caps[s->capability / 32].effective = caps[s->capability / 32].permitted = 1U << (s->capability % 32);
        setup(syscall(SYS_capset, &header, caps) == 0, "capset");
        errno = 0;
        long actual = invoke(s, path, fd);
        struct outcome result = {.actual = actual, .error = errno};
        setup(write(pipefd[1], &result, sizeof(result)) == sizeof(result), "result");
        _exit(0);
    }
    close(pipefd[1]);
    struct outcome result;
    setup(read(pipefd[0], &result, sizeof(result)) == sizeof(result), "child result");
    int status;
    setup(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "child completion");
    close(pipefd[0]);
    if (fd >= 0) close(fd);
    setup(lstat(path, &after) == 0, "after stat");
    result.unchanged = eqtime(before.st_atim, after.st_atim) && eqtime(before.st_mtim, after.st_mtim) && eqtime(before.st_ctim, after.st_ctim);
    result.omit_preserved = ((s->times != OMIT_NOW && s->times != OMIT_BOTH) || eqtime(before.st_atim, after.st_atim)) &&
                           ((s->times != NOW_OMIT && s->times != OMIT_BOTH && s->times != EXPLICIT_OMIT) || eqtime(before.st_mtim, after.st_mtim));
    int good = s->expected ? result.actual == -1 && result.error == s->expected && result.unchanged :
                            result.actual == 0 && result.omit_preserved;
    if (s->times == OMIT_BOTH) good &= result.unchanged;
    if (!s->expected && (s->times == EXPLICIT || s->times == EXPLICIT_OMIT)) {
        good &= after.st_atim.tv_sec == 345678;
        if (s->times == EXPLICIT) good &= after.st_mtim.tv_sec == 456789;
    }
    if (!s->expected && (s->times == NOW_NULL || s->times == NOW_BOTH || s->times == NOW_OMIT))
        good &= after.st_atim.tv_sec != before.st_atim.tv_sec;
    if (!s->expected && (s->times == NOW_NULL || s->times == NOW_BOTH || s->times == OMIT_NOW))
        good &= after.st_mtim.tv_sec != before.st_mtim.tv_sec;
    ++cases; if (!good) ++failures;
    printf("UT_CASE name=%s_%s pass=%d actual=%ld errno=%d unchanged=%d omit=%d\n", prefix, s->name, good, result.actual, result.error, result.unchanged, result.omit_preserved);
    setup(unlink(path) == 0, "unlink test file");
}
static void suite(const char *root, const char *prefix) {
    for (unsigned i = 0; i < sizeof(scenarios) / sizeof(scenarios[0]); ++i) run_case(root, prefix, &scenarios[i], i);
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 3 && strcmp(argv[1], "--linux-reference") == 0) {
        /* Caller supplies a fresh isolated tmpfs directory, never arbitrary host paths. */
        setup(getuid() == 0 && access("/.dockerenv", F_OK) == 0, "isolated Linux container");
        suite(argv[2], "linux");
    } else if (argc == 2 && strcmp(argv[1], "--disposable-guest") == 0 && access("/.hepta-disposable-guest", F_OK) == 0) {
        setup(mkdir("/ut-ram", 0777) == 0 && mkdir("/ut-ext", 0777) == 0, "test directories");
        setup(mount("tmpfs", "/ut-ram", "tmpfs", 0, NULL) == 0, "tmpfs");
        setup(mount("/dev/vda", "/ut-ext", "ext2", 0, NULL) == 0, "ext2");
        setup(chmod("/ut-ram", 0777) == 0 && chmod("/ut-ext", 0777) == 0, "traversable directories");
        suite("/ut-ram", "tmpfs"); suite("/ut-ext", "ext2");
    } else return 64;
    printf("UT_COMPLETE cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
