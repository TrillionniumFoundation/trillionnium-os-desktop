// SPDX-License-Identifier: MPL-2.0
// Observe synthesized ExFAT modes and credentials across real execve.
// This program mounts only the disposable block device supplied by its runner.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <inttypes.h>
#include <linux/capability.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/fsuid.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define ACTOR 65534
#define EXFAT_LINUX_MAGIC 0x2011bab0UL
#define EXFAT_ASTERINAS_MAGIC 0xaa55UL
#define SETUP(expr) do { \
    if (!(expr)) { \
        dprintf(STDERR_FILENO, "EXFAT_SETUP line=%d expression=%s errno=%d\n", \
                __LINE__, #expr, errno); \
        return 2; \
    } \
} while (0)

struct credentials {
    uid_t ruid, euid, suid, fsuid;
    gid_t rgid, egid, sgid, fsgid;
    int groups, nnp, securebits;
    uint64_t effective, permitted, inheritable, ambient, bounding;
};

static uint64_t combined(uint32_t low, uint32_t high)
{
    return low | ((uint64_t)high << 32);
}

static int credentials_read(struct credentials *value)
{
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct caps[2] = {{0}, {0}};
    memset(value, 0, sizeof(*value));
    if (getresuid(&value->ruid, &value->euid, &value->suid) != 0
        || getresgid(&value->rgid, &value->egid, &value->sgid) != 0
        || syscall(SYS_capget, &header, caps) != 0)
        return -1;
    value->fsuid = (uid_t)setfsuid((uid_t)-1);
    value->fsgid = (gid_t)setfsgid((gid_t)-1);
    value->groups = getgroups(0, NULL);
    value->nnp = prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0);
    value->securebits = prctl(PR_GET_SECUREBITS, 0, 0, 0, 0);
    if (value->groups < 0 || value->nnp < 0 || value->securebits < 0)
        return -1;
    value->effective = combined(caps[0].effective, caps[1].effective);
    value->permitted = combined(caps[0].permitted, caps[1].permitted);
    value->inheritable = combined(caps[0].inheritable, caps[1].inheritable);
    for (unsigned cap = 0; cap <= CAP_LAST_CAP; ++cap) {
        int ambient = prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, cap, 0, 0);
        int bounding = prctl(PR_CAPBSET_READ, cap, 0, 0, 0);
        if (ambient < 0 || bounding < 0)
            return -1;
        value->ambient |= (uint64_t)ambient << cap;
        value->bounding |= (uint64_t)bounding << cap;
    }
    return 0;
}

static bool unprivileged(const struct credentials *value, int nnp)
{
    return value->ruid == ACTOR && value->euid == ACTOR && value->suid == ACTOR
        && value->fsuid == ACTOR && value->rgid == ACTOR && value->egid == ACTOR
        && value->sgid == ACTOR && value->fsgid == ACTOR && value->groups == 0
        && value->effective == 0 && value->permitted == 0 && value->inheritable == 0
        && value->ambient == 0 && value->bounding == 0 && value->nnp == nnp && value->securebits == 0;
}

static void print_credentials(const char *phase, const char *name,
                              const struct credentials *value, unsigned long secure)
{
    printf("EXFAT_CREDENTIALS phase=%s name=%s ruid=%u euid=%u suid=%u fsuid=%u"
           " rgid=%u egid=%u sgid=%u fsgid=%u groups=%d nnp=%d securebits=%d"
           " effective=%" PRIu64 " permitted=%" PRIu64 " inheritable=%" PRIu64
           " ambient=%" PRIu64 " bounding=%" PRIu64 " at_secure=%lu\n",
           phase, name, (unsigned)value->ruid, (unsigned)value->euid,
           (unsigned)value->suid, (unsigned)value->fsuid, (unsigned)value->rgid,
           (unsigned)value->egid, (unsigned)value->sgid, (unsigned)value->fsgid,
           value->groups, value->nnp, value->securebits, value->effective,
           value->permitted, value->inheritable, value->ambient, value->bounding, secure);
}

static int exec_entry(const char *name, int nnp)
{
    struct credentials value;
    alarm(10);
    SETUP(credentials_read(&value) == 0);
    unsigned long secure = getauxval(AT_SECURE);
    print_credentials("after", name, &value, secure);
    // A failed identity assertion still leaves the measured values in the log.
    return unprivileged(&value, nnp) && secure == 0 ? 0 : 1;
}

static int drop_and_exec(const char *path, const char *name, int nnp)
{
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct zero[2] = {{0}, {0}};
    struct credentials before;
    alarm(10);
    SETUP(prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 0);
    SETUP(prctl(PR_SET_KEEPCAPS, 0, 0, 0, 0) == 0);
    SETUP(prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) == 0);
    for (unsigned cap = 0; cap <= CAP_LAST_CAP; ++cap)
        SETUP(prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) == 0);
    SETUP(setgroups(0, NULL) == 0);
    SETUP(setresgid(ACTOR, ACTOR, ACTOR) == 0);
    SETUP(setresuid(ACTOR, ACTOR, ACTOR) == 0);
    SETUP(syscall(SYS_capset, &header, zero) == 0);
    if (nnp)
        SETUP(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0);
    SETUP(credentials_read(&before) == 0);
    SETUP(unprivileged(&before, nnp));
    print_credentials("before", name, &before, getauxval(AT_SECURE));
    char *arguments[] = {(char *)path, "--exec-child", (char *)name, nnp ? "1" : "0", NULL};
    char *environment[] = {"PATH=/bin:/sbin", "LC_ALL=C", NULL};
    execve(path, arguments, environment);
    SETUP(false);
}

static int copy_probe(const char *source, const char *destination, uint64_t *copied)
{
    char bytes[16384], observed[16384];
    int source_fd = open(source, O_RDONLY | O_CLOEXEC);
    SETUP(source_fd >= 0);
    int destination_fd = open(destination, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0777);
    SETUP(destination_fd >= 0);
    *copied = 0;
    for (;;) {
        ssize_t size = read(source_fd, bytes, sizeof(bytes));
        if (size < 0 && errno == EINTR)
            continue;
        SETUP(size >= 0);
        if (size == 0)
            break;
        ssize_t done = 0;
        while (done < size) {
            ssize_t written = write(destination_fd, bytes + done, (size_t)(size - done));
            if (written < 0 && errno == EINTR)
                continue;
            SETUP(written > 0);
            done += written;
        }
        *copied += (uint64_t)size;
    }
    SETUP(fsync(destination_fd) == 0);
    SETUP(close(destination_fd) == 0);
    SETUP(lseek(source_fd, 0, SEEK_SET) == 0);
    destination_fd = open(destination, O_RDONLY | O_CLOEXEC);
    SETUP(destination_fd >= 0);
    // Read back every copied byte before executing the ExFAT file.
    for (;;) {
        ssize_t size = read(source_fd, bytes, sizeof(bytes));
        if (size < 0 && errno == EINTR)
            continue;
        SETUP(size >= 0);
        ssize_t done = 0;
        while (done < size) {
            ssize_t got = read(destination_fd, observed + done, (size_t)(size - done));
            if (got < 0 && errno == EINTR)
                continue;
            SETUP(got > 0);
            done += got;
        }
        if (size == 0) {
            SETUP(read(destination_fd, observed, 1) == 0);
            break;
        }
        SETUP(memcmp(bytes, observed, (size_t)size) == 0);
    }
    SETUP(close(source_fd) == 0);
    SETUP(close(destination_fd) == 0);
    return 0;
}

static bool observe_stat(const char *name, const char *path, mode_t type, dev_t device,
                         uint64_t expected_size)
{
    struct stat value;
    memset(&value, 0, sizeof(value));
    errno = 0;
    int result = stat(path, &value);
    int error = result == 0 ? 0 : errno;
    printf("EXFAT_STAT name=%s rc=%d errno=%d mode=%u type=%u uid=%u gid=%u"
           " ino=%" PRIu64 " dev=%" PRIu64 " size=%" PRIu64 "\n",
           name, result, error, (unsigned)(value.st_mode & 07777),
           (unsigned)(value.st_mode & S_IFMT), (unsigned)value.st_uid,
           (unsigned)value.st_gid, (uint64_t)value.st_ino,
           (uint64_t)value.st_dev, (uint64_t)value.st_size);
    return result == 0 && (value.st_mode & 07777) == 0777
        && (value.st_mode & S_IFMT) == type && value.st_uid == 0 && value.st_gid == 0
        && value.st_dev == device && value.st_ino != 0
        && (type != S_IFREG || (uint64_t)value.st_size == expected_size);
}

static void case_result(const char *name, int code, int signal_number, unsigned *passed)
{
    bool ok = code == 0 && signal_number == 0;
    printf("EXFAT_CASE name=%s result=%s exit=%d signal=%d\n",
           name, ok ? "PASS" : "FAIL", code, signal_number);
    *passed += ok;
}

int main(int argc, char **argv)
{
    setbuf(stdout, NULL);
    if (argc == 4 && strcmp(argv[1], "--exec-child") == 0) {
        SETUP((strcmp(argv[2], "exec_normal") == 0 && strcmp(argv[3], "0") == 0)
              || (strcmp(argv[2], "exec_nnp") == 0 && strcmp(argv[3], "1") == 0));
        return exec_entry(argv[2], argv[3][0] == '1');
    }
    SETUP(argc == 5 && strcmp(argv[1], "--device") == 0 && strcmp(argv[3], "--mountpoint") == 0);
    SETUP(geteuid() == 0 && prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 0);
    SETUP(prctl(PR_GET_SECUREBITS, 0, 0, 0, 0) == 0);
    const char *device = argv[2], *mountpoint = argv[4];
    struct stat device_stat, root_stat;
    struct statfs filesystem;
    SETUP(stat(device, &device_stat) == 0 && S_ISBLK(device_stat.st_mode));
    SETUP(mkdir(mountpoint, 0755) == 0);
    SETUP(mount(device, mountpoint, "exfat", 0, "uid=0,gid=0,fmask=0000,dmask=0000") == 0);
    SETUP(statfs(mountpoint, &filesystem) == 0 && stat(mountpoint, &root_stat) == 0);
    printf("EXFAT_FS type=%lu flags=%lu\n", (unsigned long)filesystem.f_type,
           (unsigned long)filesystem.f_flags);
    SETUP((unsigned long)filesystem.f_type == EXFAT_LINUX_MAGIC
          || (unsigned long)filesystem.f_type == EXFAT_ASTERINAS_MAGIC);
    SETUP((filesystem.f_flags & (MS_NOSUID | MS_NOEXEC)) == 0);
    char executable[4096], directory[4096];
    int length = snprintf(executable, sizeof(executable), "%s/observed-exec", mountpoint);
    SETUP(length > 0 && (size_t)length < sizeof(executable));
    length = snprintf(directory, sizeof(directory), "%s/observed-dir", mountpoint);
    SETUP(length > 0 && (size_t)length < sizeof(directory));
    uint64_t copied = 0;
    SETUP(copy_probe(argv[0], executable, &copied) == 0 && copied > 0);
    SETUP(mkdir(directory, 0777) == 0);
    printf("EXFAT_COPY bytes=%" PRIu64 " reread_equal=1\n", copied);
    unsigned passed = 0;
    case_result("root_mode", observe_stat("root_mode", mountpoint, S_IFDIR, root_stat.st_dev, 0) ? 0 : 1, 0, &passed);
    case_result("file_mode", observe_stat("file_mode", executable, S_IFREG, root_stat.st_dev, copied) ? 0 : 1, 0, &passed);
    case_result("directory_mode", observe_stat("directory_mode", directory, S_IFDIR, root_stat.st_dev, 0) ? 0 : 1, 0, &passed);
    for (int nnp = 0; nnp <= 1; ++nnp) {
        const char *name = nnp ? "exec_nnp" : "exec_normal";
        pid_t child = fork();
        SETUP(child >= 0);
        if (child == 0) {
            // Private evidence parents stay 0700. Resolve only within the already
            // mounted ExFAT directory after dropping identity and all capsets.
            SETUP(chdir(mountpoint) == 0);
            _exit(drop_and_exec("./observed-exec", name, nnp));
        }
        int status = 0;
        pid_t waited;
        do {
            waited = waitpid(child, &status, 0);
        } while (waited < 0 && errno == EINTR);
        SETUP(waited == child);
        case_result(name, WIFEXITED(status) ? WEXITSTATUS(status) : -1,
                    WIFSIGNALED(status) ? WTERMSIG(status) : 0, &passed);
    }
    SETUP(unlink(executable) == 0);
    SETUP(rmdir(directory) == 0);
    SETUP(umount2(mountpoint, 0) == 0);
    SETUP(rmdir(mountpoint) == 0);
    printf("EXFAT_COMPLETE total=5 passed=%u failed=%u\n", passed, 5 - passed);
    return passed == 5 ? 0 : 1;
}
