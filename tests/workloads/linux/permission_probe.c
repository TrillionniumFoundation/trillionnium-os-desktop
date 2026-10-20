// SPDX-License-Identifier: MPL-2.0
// Execute real Linux permission syscalls with independently observable credentials.
// The full reference must run in a private mount namespace; the guest has no disks.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/fsuid.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define OWNER 65534
#define OTHER 65533
#define MEMBER 65532
#define FOREIGN 65531
#define CAP_BIT(number) (UINT64_C(1) << (number))
#define REQUIRE(expr) do { \
    if (!(expr)) { \
        dprintf(STDERR_FILENO, "PERMISSION_ASSERT name=%s line=%d expression=%s errno=%d\n", \
                test->name, __LINE__, #expr, errno); \
        return __LINE__; \
    } \
} while (0)

enum operation {
    CHMOD_PATH, CHMOD_FD, CHMOD_AT, CHOWN_PATH, CHOWN_FD, CHOWN_AT,
    MOUNT_NEW, UMOUNT_EXISTING, MOUNT_MISSING, UMOUNT_MISSING, PIVOT_DENIED
};

struct test_case {
    const char *name;
    enum operation operation;
    uid_t actor;
    uint64_t caps;
    bool member;
    bool fsuid_owner;
    bool directory;
    gid_t original_gid;
    mode_t original_mode;
    mode_t requested_mode;
    uid_t requested_uid;
    gid_t requested_gid;
    int expected_errno;
    uid_t final_uid;
    gid_t final_gid;
    mode_t final_mode;
    bool ctime_advance;
};

#define MODE_CASE(name_, op_, actor_, cap_, member_, gid_, mode_, final_, error_) \
    {name_, op_, actor_, cap_, member_, false, false, gid_, 0644, mode_, \
     (uid_t)-1, (gid_t)-1, error_, OWNER, gid_, final_, false}
#define OWNER_CASE(name_, op_, actor_, cap_, member_, directory_, gid_, mode_, uid_, newgid_, error_, finaluid_, finalgid_, finalmode_) \
    {name_, op_, actor_, cap_, member_, false, directory_, gid_, mode_, 0, \
     uid_, newgid_, error_, finaluid_, finalgid_, finalmode_, false}
#define MOUNT_CASE(name_, op_, actor_, cap_, error_) \
    {name_, op_, actor_, cap_, false, false, false, 0, 0, 0, \
     (uid_t)-1, (gid_t)-1, error_, 0, 0, 0, false}

static const struct test_case cases[] = {
    MODE_CASE("chmod_nonowner_path", CHMOD_PATH, OTHER, 0, false, OWNER, 0600, 0644, EPERM),
    MODE_CASE("chmod_nonowner_fd", CHMOD_FD, OTHER, 0, false, OWNER, 0600, 0644, EPERM),
    MODE_CASE("chmod_nonowner_at", CHMOD_AT, OTHER, 0, false, OWNER, 0600, 0644, EPERM),
    MODE_CASE("chmod_owner", CHMOD_FD, OWNER, 0, false, OWNER, 0600, 0600, 0),
    MODE_CASE("chmod_fowner", CHMOD_PATH, OTHER, CAP_BIT(CAP_FOWNER), false, OWNER, 0600, 0600, 0),
    MODE_CASE("chmod_chown_cap_denied", CHMOD_FD, OTHER, CAP_BIT(CAP_CHOWN), false, OWNER, 0600, 0644, EPERM),
    MODE_CASE("chmod_owner_sgid_member", CHMOD_FD, OWNER, 0, true, MEMBER, 02755, 02755, 0),
    MODE_CASE("chmod_owner_sgid_nonmember", CHMOD_FD, OWNER, 0, false, MEMBER, 02755, 0755, 0),
    MODE_CASE("chmod_owner_sgid_fsetid", CHMOD_FD, OWNER, CAP_BIT(CAP_FSETID), false, MEMBER, 02755, 02755, 0),
    OWNER_CASE("chown_nonowner_path", CHOWN_PATH, OTHER, 0, false, false, OWNER, 0644, OTHER, (gid_t)-1, EPERM, OWNER, OWNER, 0644),
    OWNER_CASE("chown_nonowner_fd", CHOWN_FD, OTHER, 0, false, false, OWNER, 0644, OTHER, (gid_t)-1, EPERM, OWNER, OWNER, 0644),
    OWNER_CASE("chown_nonowner_at", CHOWN_AT, OTHER, 0, false, false, OWNER, 0644, OTHER, (gid_t)-1, EPERM, OWNER, OWNER, 0644),
    OWNER_CASE("chown_nonowner_same_uid", CHOWN_FD, OTHER, 0, false, false, OWNER, 0644, OWNER, (gid_t)-1, EPERM, OWNER, OWNER, 0644),
    {.name = "chown_nonowner_noop", .operation = CHOWN_FD, .actor = OTHER,
     .original_gid = OWNER, .original_mode = 0644, .requested_uid = (uid_t)-1,
     .requested_gid = (gid_t)-1, .final_uid = OWNER, .final_gid = OWNER,
     .final_mode = 0644, .ctime_advance = true},
    OWNER_CASE("chown_owner_uid_denied", CHOWN_FD, OWNER, 0, false, false, OWNER, 0644, OTHER, (gid_t)-1, EPERM, OWNER, OWNER, 0644),
    OWNER_CASE("chown_owner_group_primary", CHOWN_FD, OWNER, 0, false, false, MEMBER, 0644, (uid_t)-1, OWNER, 0, OWNER, OWNER, 0644),
    OWNER_CASE("chown_owner_group_member", CHOWN_FD, OWNER, 0, true, false, OWNER, 0644, (uid_t)-1, MEMBER, 0, OWNER, MEMBER, 0644),
    OWNER_CASE("chown_owner_group_denied", CHOWN_FD, OWNER, 0, false, false, OWNER, 0644, (uid_t)-1, MEMBER, EPERM, OWNER, OWNER, 0644),
    OWNER_CASE("chown_cap", CHOWN_FD, OTHER, CAP_BIT(CAP_CHOWN), false, false, OWNER, 0644, OTHER, FOREIGN, 0, OTHER, FOREIGN, 0644),
    OWNER_CASE("chown_fowner_denied", CHOWN_FD, OTHER, CAP_BIT(CAP_FOWNER), false, false, OWNER, 0644, OTHER, (gid_t)-1, EPERM, OWNER, OWNER, 0644),
    OWNER_CASE("chown_regular_clear_setid", CHOWN_FD, OWNER, 0, false, false, OWNER, 06755, (uid_t)-1, (gid_t)-1, 0, OWNER, OWNER, 0755),
    OWNER_CASE("chown_directory_keep_setid", CHOWN_FD, OWNER, 0, false, true, OWNER, 02775, (uid_t)-1, (gid_t)-1, 0, OWNER, OWNER, 02775),
    {"chmod_fsuid_owner", CHMOD_FD, OTHER, 0, false, true, false, OWNER, 0644, 0600,
     (uid_t)-1, (gid_t)-1, 0, OWNER, OWNER, 0600, false},
    MOUNT_CASE("mount_nonroot_denied", MOUNT_NEW, OTHER, 0, EPERM),
    MOUNT_CASE("mount_root_without_cap_denied", MOUNT_NEW, 0, 0, EPERM),
    MOUNT_CASE("mount_sysadmin", MOUNT_NEW, OTHER, CAP_BIT(CAP_SYS_ADMIN), 0),
    MOUNT_CASE("umount_nonroot_denied", UMOUNT_EXISTING, OTHER, 0, EPERM),
    MOUNT_CASE("umount_root_without_cap_denied", UMOUNT_EXISTING, 0, 0, EPERM),
    MOUNT_CASE("umount_sysadmin", UMOUNT_EXISTING, OTHER, CAP_BIT(CAP_SYS_ADMIN), 0),
    MOUNT_CASE("mount_missing_path", MOUNT_MISSING, OTHER, 0, ENOENT),
    MOUNT_CASE("umount_missing_path", UMOUNT_MISSING, OTHER, 0, ENOENT),
    MOUNT_CASE("pivot_without_cap", PIVOT_DENIED, OTHER, 0, EPERM),
};

static uint64_t combined(uint32_t low, uint32_t high)
{
    return low | ((uint64_t)high << 32);
}

static int cap_read(struct __user_cap_data_struct value[2])
{
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    return syscall(SYS_capget, &header, value);
}

static int cap_exact(uint64_t bits)
{
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct data[2] = {
        {.effective = (uint32_t)bits, .permitted = (uint32_t)bits},
        {.effective = (uint32_t)(bits >> 32), .permitted = (uint32_t)(bits >> 32)},
    };
    return syscall(SYS_capset, &header, data);
}

static bool same_metadata(const struct stat *a, const struct stat *b)
{
    return a->st_uid == b->st_uid && a->st_gid == b->st_gid && a->st_mode == b->st_mode
        && a->st_ino == b->st_ino && a->st_dev == b->st_dev
        && a->st_ctim.tv_sec == b->st_ctim.tv_sec && a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}

static int marker_present(void)
{
    struct stat info;
    if (stat("mountpoint/underlying-marker", &info) == 0)
        return 1;
    return errno == ENOENT ? 0 : -1;
}

static int child_case(const struct test_case *test)
{
    alarm(5);
    REQUIRE(chdir(test->name) == 0);
    int fd = -1;
    const bool mounts = test->operation >= MOUNT_NEW;
    if (mounts) {
        REQUIRE(mkdir("mountpoint", 0755) == 0);
        fd = open("mountpoint/underlying-marker", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0644);
        REQUIRE(fd >= 0);
        REQUIRE(close(fd) == 0);
        fd = -1;
        if (test->operation == UMOUNT_EXISTING)
            REQUIRE(mount("none", "mountpoint", "tmpfs", 0, "mode=0755") == 0);
    } else {
        if (test->directory) {
            REQUIRE(mkdir("subject", 0700) == 0);
            fd = open("subject", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        } else {
            fd = open("subject", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
        }
        REQUIRE(fd >= 0);
        REQUIRE(fchown(fd, OWNER, test->original_gid) == 0);
        REQUIRE(fchmod(fd, test->original_mode) == 0);
    }
    gid_t membership = MEMBER;
    REQUIRE(setgroups(test->member ? 1 : 0, test->member ? &membership : NULL) == 0);
    REQUIRE(setresgid(test->actor, test->actor, test->actor) == 0);
    REQUIRE(prctl(PR_SET_KEEPCAPS, 1, 0, 0, 0) == 0);
    if (test->fsuid_owner) {
        REQUIRE(setresuid(OWNER, OTHER, OWNER) == 0);
        (void)setfsuid(OWNER);
    } else {
        REQUIRE(setresuid(test->actor, test->actor, test->actor) == 0);
    }
    REQUIRE(cap_exact(test->caps) == 0);
    struct __user_cap_data_struct caps[2] = {{0}, {0}};
    REQUIRE(cap_read(caps) == 0);
    uint64_t effective = combined(caps[0].effective, caps[1].effective);
    uint64_t permitted = combined(caps[0].permitted, caps[1].permitted);
    uint64_t inheritable = combined(caps[0].inheritable, caps[1].inheritable);
    uid_t ruid, euid, suid;
    gid_t rgid, egid, sgid, actual_groups[2];
    REQUIRE(getresuid(&ruid, &euid, &suid) == 0);
    REQUIRE(getresgid(&rgid, &egid, &sgid) == 0);
    uid_t fsuid = setfsuid((uid_t)-1);
    gid_t fsgid = setfsgid((gid_t)-1);
    int group_count = getgroups(2, actual_groups);
    REQUIRE(group_count == (test->member ? 1 : 0));
    REQUIRE(!test->member || actual_groups[0] == MEMBER);
    REQUIRE(effective == test->caps && permitted == test->caps && inheritable == 0);
    REQUIRE(euid == test->actor && rgid == test->actor && egid == test->actor
            && sgid == test->actor && fsgid == test->actor);
    REQUIRE(ruid == (test->fsuid_owner ? OWNER : test->actor)
            && suid == (test->fsuid_owner ? OWNER : test->actor)
            && fsuid == (test->fsuid_owner ? OWNER : test->actor));

    struct stat before, after;
    REQUIRE((mounts ? stat("mountpoint", &before) : fstat(fd, &before)) == 0);
    int before_marker = mounts ? marker_present() : -1;
    REQUIRE(!mounts || before_marker >= 0);
    if (test->ctime_advance) {
        // Separate timestamps even on filesystems with one-second resolution.
        const struct timespec delay = {.tv_sec = 1, .tv_nsec = 100000000};
        REQUIRE(nanosleep(&delay, NULL) == 0);
    }
    errno = 0;
    long rc = -999;
    switch (test->operation) {
    case CHMOD_PATH: rc = syscall(SYS_chmod, "subject", test->requested_mode); break;
    case CHMOD_FD: rc = syscall(SYS_fchmod, fd, test->requested_mode); break;
    case CHMOD_AT: rc = syscall(SYS_fchmodat, AT_FDCWD, "subject", test->requested_mode); break;
    case CHOWN_PATH: rc = syscall(SYS_chown, "subject", test->requested_uid, test->requested_gid); break;
    case CHOWN_FD: rc = syscall(SYS_fchown, fd, test->requested_uid, test->requested_gid); break;
    case CHOWN_AT: rc = syscall(SYS_fchownat, AT_FDCWD, "subject", test->requested_uid, test->requested_gid, 0); break;
    case MOUNT_NEW: rc = mount("none", "mountpoint", "tmpfs", 0, "mode=0755"); break;
    case UMOUNT_EXISTING: rc = umount2("mountpoint", 0); break;
    case MOUNT_MISSING: rc = mount("none", "missing", "tmpfs", 0, "mode=0755"); break;
    case UMOUNT_MISSING: rc = umount2("missing", 0); break;
    case PIVOT_DENIED: rc = syscall(SYS_pivot_root, NULL, NULL); break;
    }
    const int operation_errno = errno;
    REQUIRE((mounts ? stat("mountpoint", &after) : fstat(fd, &after)) == 0);
    int after_marker = mounts ? marker_present() : -1;
    REQUIRE(!mounts || after_marker >= 0);
    char buffer[2048];
    int length = snprintf(buffer, sizeof(buffer),
        "PERMISSION_OBSERVATION name=%s ruid=%u euid=%u suid=%u fsuid=%u "
        "rgid=%u egid=%u sgid=%u fsgid=%u groups_count=%d group=%d "
        "effective=%llu permitted=%llu inheritable=%llu rc=%ld errno=%d "
        "before_uid=%u before_gid=%u before_mode=%u before_ino=%llu before_dev=%llu "
        "before_ctime_sec=%lld before_ctime_nsec=%ld "
        "after_uid=%u after_gid=%u after_mode=%u after_ino=%llu after_dev=%llu "
        "after_ctime_sec=%lld after_ctime_nsec=%ld marker_before=%d marker_after=%d\n",
        test->name, ruid, euid, suid, fsuid, rgid, egid, sgid, fsgid,
        group_count, group_count ? (int)actual_groups[0] : -1,
        (unsigned long long)effective, (unsigned long long)permitted, (unsigned long long)inheritable,
        rc, operation_errno, before.st_uid, before.st_gid, before.st_mode & 07777,
        (unsigned long long)before.st_ino, (unsigned long long)before.st_dev,
        (long long)before.st_ctim.tv_sec, before.st_ctim.tv_nsec,
        after.st_uid, after.st_gid, after.st_mode & 07777,
        (unsigned long long)after.st_ino, (unsigned long long)after.st_dev,
        (long long)after.st_ctim.tv_sec, after.st_ctim.tv_nsec, before_marker, after_marker);
    REQUIRE(length > 0 && (size_t)length < sizeof(buffer));
    REQUIRE(write(STDOUT_FILENO, buffer, (size_t)length) == length);
    REQUIRE(rc == (test->expected_errno ? -1 : 0) && operation_errno == test->expected_errno);
    if (test->expected_errno)
        REQUIRE(same_metadata(&before, &after));
    if (test->ctime_advance)
        REQUIRE(after.st_ctim.tv_sec > before.st_ctim.tv_sec ||
                (after.st_ctim.tv_sec == before.st_ctim.tv_sec &&
                 after.st_ctim.tv_nsec > before.st_ctim.tv_nsec));
    if (!mounts) {
        REQUIRE(before.st_ino == after.st_ino && before.st_dev == after.st_dev);
        REQUIRE(before.st_uid == OWNER && before.st_gid == test->original_gid
                && (before.st_mode & 07777) == test->original_mode);
        REQUIRE(after.st_uid == test->final_uid && after.st_gid == test->final_gid
                && (after.st_mode & 07777) == test->final_mode);
        REQUIRE(close(fd) == 0);
    } else {
        REQUIRE(before_marker == (test->operation == UMOUNT_EXISTING ? 0 : 1));
        int expected_marker = test->expected_errno ? before_marker :
            (test->operation == UMOUNT_EXISTING ? 1 : 0);
        REQUIRE(after_marker == expected_marker);
    }
    return 0;
}

static int cleanup_case(const struct test_case *test)
{
    char path[256];
    if (test->operation >= MOUNT_NEW) {
        snprintf(path, sizeof(path), "%s/mountpoint", test->name);
        // Only this test's new tmpfs can exist here; detach it before removing files.
        if (umount2(path, MNT_DETACH) != 0 && errno != EINVAL && errno != ENOENT)
            return -1;
        snprintf(path, sizeof(path), "%s/mountpoint/underlying-marker", test->name);
        if (unlink(path) != 0 && errno != ENOENT)
            return -1;
        snprintf(path, sizeof(path), "%s/mountpoint", test->name);
        if (rmdir(path) != 0 && errno != ENOENT)
            return -1;
    } else {
        snprintf(path, sizeof(path), "%s/subject", test->name);
        if ((test->directory ? rmdir(path) : unlink(path)) != 0 && errno != ENOENT)
            return -1;
    }
    return rmdir(test->name);
}

int main(int argc, char **argv)
{
    const char *work_dir = NULL, *selected = NULL;
    for (int i = 1; i < argc; ++i) {
        if (i + 1 < argc && strcmp(argv[i], "--work-dir") == 0)
            work_dir = argv[++i];
        else if (i + 1 < argc && strcmp(argv[i], "--case") == 0)
            selected = argv[++i];
        else {
            dprintf(STDERR_FILENO, "PERMISSION_SETUP invalid_arguments\n");
            return 2;
        }
    }
    if (!work_dir || geteuid() != 0 || mkdir(work_dir, 0755) != 0 || chdir(work_dir) != 0) {
        dprintf(STDERR_FILENO, "PERMISSION_SETUP need_root_and_fresh_work_directory errno=%d\n", errno);
        return 2;
    }
    umask(022);
    unsigned total = 0, passed = 0;
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        const struct test_case *test = &cases[i];
        if (selected && strcmp(selected, test->name) != 0)
            continue;
        ++total;
        if (mkdir(test->name, 0755) != 0) {
            dprintf(STDERR_FILENO, "PERMISSION_SETUP name=%s errno=%d\n", test->name, errno);
            return 2;
        }
        pid_t child = fork();
        if (child == 0) {
            int result = child_case(test);
            _exit(result == 0 ? 0 : 1 + result % 254);
        }
        if (child < 0) {
            dprintf(STDERR_FILENO, "PERMISSION_SETUP fork_failed errno=%d\n", errno);
            return 2;
        }
        int status;
        pid_t waited;
        do {
            waited = waitpid(child, &status, 0);
        } while (waited < 0 && errno == EINTR);
        if (waited != child) {
            dprintf(STDERR_FILENO, "PERMISSION_SETUP child_reap_failed errno=%d\n", errno);
            return 2;
        }
        int result = WIFEXITED(status) ? WEXITSTATUS(status) : 0;
        int signal_number = WIFSIGNALED(status) ? WTERMSIG(status) : 0;
        if (cleanup_case(test) != 0) {
            dprintf(STDERR_FILENO, "PERMISSION_SETUP name=%s cleanup_failed errno=%d\n", test->name, errno);
            result = 255;
        }
        const bool ok = WIFEXITED(status) && result == 0;
        passed += ok;
        if (signal_number)
            dprintf(STDOUT_FILENO, "PERMISSION_CASE name=%s result=FAIL line=0 signal=%d\n", test->name, signal_number);
        else
            dprintf(STDOUT_FILENO, "PERMISSION_CASE name=%s result=%s line=%d\n", test->name, ok ? "PASS" : "FAIL", result);
    }
    dprintf(STDOUT_FILENO, "PERMISSION_COMPLETE total=%u passed=%u failed=%u\n", total, passed, total - passed);
    return total != 0 && total == passed ? 0 : 1;
}
