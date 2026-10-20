// SPDX-License-Identifier: MPL-2.0
// One observation ELF for Linux and both ordinary-kernel disk guests.
// Semantic verdicts belong to the independent Python oracle, not this program.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <inttypes.h>
#include <linux/capability.h>
#include <linux/loop.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/fsuid.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define IMAGE_SIZE (UINT64_C(512) * 1024 * 1024)
#define ACTOR 65534
#define LAST_CAP 40
#define REQUIRE(expr) do { if (!(expr)) fail(#expr, __LINE__); } while (0)

static pid_t supervisor;
static int loop_fd = -1, image_fd = -1, cwd_fd = -1;
static bool mounted, owns_loop;
static const char *mount_dir;
static struct stat image_stat;

static _Noreturn void fail(const char *expression, int line)
{
    dprintf(STDERR_FILENO, "EXFAT_ERROR line=%d errno=%d expression=%s\n", line, errno, expression);
    // A forked actor must never unmount or detach its parent's fixture.
    if (getpid() != supervisor)
        _exit(111);
    exit(1);
}

static bool same_loop(void)
{
    struct loop_info64 info = {0};
    return loop_fd >= 0 && ioctl(loop_fd, LOOP_GET_STATUS64, &info) == 0
        && info.lo_inode == (uint64_t)image_stat.st_ino
        && info.lo_device == (uint64_t)image_stat.st_dev;
}

static bool cleanup(void)
{
    bool ok = true;
    if (cwd_fd >= 0 && fchdir(cwd_fd) != 0)
        ok = false;
    if (mounted) {
        if (umount2(mount_dir, 0) != 0)
            ok = false;
        else
            mounted = false;
    }
    if (owns_loop) {
        // Never detach a reused or unrecognized global loop device.
        if (mounted || !same_loop() || ioctl(loop_fd, LOOP_CLR_FD, 0) != 0) {
            ok = false;
        } else {
            struct loop_info64 info = {0};
            errno = 0;
            if (ioctl(loop_fd, LOOP_GET_STATUS64, &info) != -1 || errno != ENXIO)
                ok = false;
            owns_loop = false;
        }
    }
    if (!mounted && !owns_loop) {
        if (loop_fd >= 0) close(loop_fd);
        if (image_fd >= 0) close(image_fd);
        if (cwd_fd >= 0) close(cwd_fd);
        loop_fd = image_fd = cwd_fd = -1;
    }
    return ok;
}

static void on_exit_cleanup(void)
{
    if (getpid() == supervisor && !cleanup())
        dprintf(STDERR_FILENO, "EXFAT_ERROR cleanup_incomplete=1 errno=%d\n", errno);
}

static void require_head(const char *head)
{
    REQUIRE(strlen(head) == 40);
    REQUIRE(strspn(head, "0123456789abcdef") == 40);
}

static void attach_image(const char *path, bool readonly, char *device, size_t size)
{
    image_fd = open(path, (readonly ? O_RDONLY : O_RDWR) | O_CLOEXEC | O_NOFOLLOW);
    REQUIRE(image_fd >= 0 && fstat(image_fd, &image_stat) == 0);
    REQUIRE(S_ISREG(image_stat.st_mode) && image_stat.st_nlink == 1);
    REQUIRE(image_stat.st_uid == geteuid() && (uint64_t)image_stat.st_size == IMAGE_SIZE);
    int control = open("/dev/loop-control", O_RDWR | O_CLOEXEC);
    REQUIRE(control >= 0);
    for (int retry = 0; retry < 8; ++retry) {
        int number = ioctl(control, LOOP_CTL_GET_FREE);
        REQUIRE(number >= 0);
        int length = snprintf(device, size, "/dev/loop%d", number);
        REQUIRE(length > 0 && (size_t)length < size);
        int candidate = open(device, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
        REQUIRE(candidate >= 0);
        struct loop_config config = {0};
        config.fd = (uint32_t)image_fd;
        config.info.lo_flags = LO_FLAGS_AUTOCLEAR | (readonly ? LO_FLAGS_READ_ONLY : 0);
        // Atomic attach: GET_FREE alone is not an ownership claim.
        if (ioctl(candidate, LOOP_CONFIGURE, &config) == 0) {
            loop_fd = candidate;
            owns_loop = true;
            REQUIRE(same_loop());
            struct loop_info64 info = {0};
            REQUIRE(ioctl(loop_fd, LOOP_GET_STATUS64, &info) == 0);
            REQUIRE(info.lo_flags == config.info.lo_flags);
            REQUIRE(close(control) == 0);
            printf("EXFAT_LOOP readonly=%d autoclear=1 inode=%ju device=%ju\n",
                   readonly, (uintmax_t)image_stat.st_ino, (uintmax_t)image_stat.st_dev);
            return;
        }
        int error = errno;
        REQUIRE(close(candidate) == 0);
        REQUIRE(error == EBUSY);
    }
    REQUIRE(close(control) == 0);
    REQUIRE(false);
}

static void begin_mount(const char *device, const char *directory, bool prepare, bool linux_host)
{
    mount_dir = directory;
    REQUIRE(directory[0] == '/');
    REQUIRE(mkdir(directory, 0700) == 0);
    cwd_fd = open(".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    REQUIRE(cwd_fd >= 0);
    unsigned long flags = MS_NODEV | (prepare ? MS_NOSUID | MS_NOEXEC : MS_RDONLY);
    // Asterinas currently ignores mount data and uses these zero defaults.
    const char *data = linux_host ? "uid=0,gid=0,fmask=0000,dmask=0000" : "";
    REQUIRE(mount(device, directory, "exfat", flags, data) == 0);
    mounted = true;
    REQUIRE(chdir(directory) == 0);
}

static uint64_t copy_or_compare(int source, int destination, bool copy)
{
    unsigned char left[16384], right[16384];
    uint64_t total = 0;
    for (;;) {
        ssize_t count = read(source, left, sizeof(left));
        REQUIRE(count >= 0);
        if (!count) break;
        total += (uint64_t)count;
        REQUIRE(total <= 16 * 1024 * 1024);
        size_t done = 0;
        while (done < (size_t)count) {
            ssize_t next = copy ? write(destination, left + done, (size_t)count - done)
                : read(destination, right + done, (size_t)count - done);
            REQUIRE(next > 0);
            done += (size_t)next;
        }
        if (!copy) REQUIRE(memcmp(left, right, (size_t)count) == 0);
    }
    if (!copy) REQUIRE(read(destination, right, 1) == 0);
    REQUIRE(total > 0);
    return total;
}

static void prepare_image(int self, const char *head)
{
    int fd = open("subject", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0777);
    REQUIRE(fd >= 0);
    uint64_t bytes = copy_or_compare(self, fd, true);
    REQUIRE(fsync(fd) == 0 && close(fd) == 0);
    REQUIRE(mkdir("directory", 0777) == 0);
    fd = open("source-head", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0666);
    REQUIRE(fd >= 0 && write(fd, head, 40) == 40 && fsync(fd) == 0 && close(fd) == 0);
    int directory = open(".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    REQUIRE(directory >= 0 && fsync(directory) == 0 && close(directory) == 0);
    printf("EXFAT_PREPARED source=%s bytes=%" PRIu64 "\n", head, bytes);
}

static uint64_t cap_mask(const struct __user_cap_data_struct *data, unsigned field)
{
    if (field == 0) return data[0].effective | ((uint64_t)data[1].effective << 32);
    if (field == 1) return data[0].permitted | ((uint64_t)data[1].permitted << 32);
    return data[0].inheritable | ((uint64_t)data[1].inheritable << 32);
}

static void credentials(const char *phase, const char *condition)
{
    uid_t ruid, euid, suid;
    gid_t rgid, egid, sgid;
    REQUIRE(getresuid(&ruid, &euid, &suid) == 0 && getresgid(&rgid, &egid, &sgid) == 0);
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct data[2] = {{0}};
    REQUIRE(syscall(SYS_capget, &header, data) == 0);
    uint64_t bounding = 0, ambient = 0;
    for (int cap = 0; cap <= LAST_CAP; ++cap) {
        int bound = prctl(PR_CAPBSET_READ, cap, 0, 0, 0);
        int amb = prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, cap, 0, 0);
        REQUIRE((bound == 0 || bound == 1) && (amb == 0 || amb == 1));
        bounding |= (uint64_t)bound << cap;
        ambient |= (uint64_t)amb << cap;
    }
    errno = 0;
    REQUIRE(prctl(PR_CAPBSET_READ, LAST_CAP + 1, 0, 0, 0) == -1 && errno == EINVAL);
    int groups = getgroups(0, NULL);
    int nnp = prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0);
    int secure = prctl(PR_GET_SECUREBITS, 0, 0, 0, 0);
    int keep = prctl(PR_GET_KEEPCAPS, 0, 0, 0, 0);
    REQUIRE(groups >= 0 && nnp >= 0 && secure >= 0 && keep >= 0);
    printf("EXFAT_CREDENTIALS phase=%s condition=%s ruid=%u euid=%u suid=%u fsuid=%u "
           "rgid=%u egid=%u sgid=%u fsgid=%u groups=%d effective=%" PRIu64
           " permitted=%" PRIu64 " inheritable=%" PRIu64 " bounding=%" PRIu64
           " ambient=%" PRIu64 " nnp=%d securebits=%d keepcaps=%d\n",
           phase, condition, ruid, euid, suid, (uid_t)setfsuid((uid_t)-1),
           rgid, egid, sgid, (gid_t)setfsgid((gid_t)-1), groups,
           cap_mask(data, 0), cap_mask(data, 1), cap_mask(data, 2),
           bounding, ambient, nnp, secure, keep);
}

static void execute_subject(const char *condition)
{
    pid_t child = fork();
    REQUIRE(child >= 0);
    if (!child) {
        REQUIRE(prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 0);
        REQUIRE(prctl(PR_GET_SECUREBITS, 0, 0, 0, 0) == 0);
        REQUIRE(prctl(PR_SET_KEEPCAPS, 0, 0, 0, 0) == 0);
        REQUIRE(prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) == 0);
        for (int cap = 0; cap <= LAST_CAP; ++cap)
            REQUIRE(prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) == 0);
        REQUIRE(setgroups(0, NULL) == 0);
        REQUIRE(setresgid(ACTOR, ACTOR, ACTOR) == 0 && setresuid(ACTOR, ACTOR, ACTOR) == 0);
        struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
        struct __user_cap_data_struct data[2] = {{0}};
        REQUIRE(syscall(SYS_capset, &header, data) == 0);
        if (!strcmp(condition, "nnp"))
            REQUIRE(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0);
        credentials("before", condition);
        // cwd already names the mounted root; no inaccessible 0700 host parent
        // directory can interfere with the actual unprivileged exec lookup.
        char *const argv[] = {"./subject", "--exec-observe", (char *)condition, NULL};
        char *const env[] = {"PATH=/bin:/sbin", NULL};
        execve("./subject", argv, env);
        REQUIRE(false);
    }
    int status;
    REQUIRE(waitpid(child, &status, 0) == child);
    int code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    int signal = WIFSIGNALED(status) ? WTERMSIG(status) : 0;
    printf("EXFAT_CHILD condition=%s exit=%d signal=%d\n", condition, code, signal);
    REQUIRE(code == 0 && signal == 0);
}

static void observe(int self, const char *head)
{
    struct statfs fs;
    REQUIRE(statfs(".", &fs) == 0);
    printf("EXFAT_MOUNT type=%lu flags=%lu\n", (unsigned long)fs.f_type, (unsigned long)fs.f_flags);
    const char *paths[] = {".", "subject", "directory"};
    const char *names[] = {"root", "subject", "directory"};
    for (size_t i = 0; i < 3; ++i) {
        struct stat st;
        REQUIRE(lstat(paths[i], &st) == 0);
        printf("EXFAT_METADATA object=%s uid=%u gid=%u mode=%u type=%u inode=%ju device=%ju\n",
               names[i], st.st_uid, st.st_gid, st.st_mode & 07777, st.st_mode & S_IFMT,
               (uintmax_t)st.st_ino, (uintmax_t)st.st_dev);
    }
    int fd = open("subject", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    REQUIRE(fd >= 0);
    uint64_t bytes = copy_or_compare(self, fd, false);
    REQUIRE(close(fd) == 0);
    char marker[41];
    fd = open("source-head", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    REQUIRE(fd >= 0 && read(fd, marker, sizeof(marker)) == 40 && close(fd) == 0);
    REQUIRE(memcmp(marker, head, 40) == 0);
    printf("EXFAT_ELF_MATCH source=%s bytes=%" PRIu64 "\n", head, bytes);
    execute_subject("plain");
    execute_subject("nnp");
    printf("EXFAT_COMPLETE metadata=3 executions=2\n");
}

int main(int argc, char **argv)
{
    supervisor = getpid();
    REQUIRE(setvbuf(stdout, NULL, _IONBF, 0) == 0);
    if (argc == 3 && !strcmp(argv[1], "--exec-observe")) {
        REQUIRE(!strcmp(argv[2], "plain") || !strcmp(argv[2], "nnp"));
        credentials("after", argv[2]);
        return 0;
    }
    REQUIRE(geteuid() == 0);
    REQUIRE(atexit(on_exit_cleanup) == 0);
    bool guest = argc == 3 && !strcmp(argv[1], "--guest");
    bool prepare = argc == 5 && !strcmp(argv[1], "--prepare-image");
    bool reference = argc == 5 && !strcmp(argv[1], "--reference-image");
    REQUIRE(guest || prepare || reference);
    const char *head = argv[guest ? 2 : 4];
    require_head(head);
    int self = open(argv[0], O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    REQUIRE(self >= 0);
    char device[64];
    if (guest) {
        REQUIRE(getenv("EXFAT_DISPOSABLE_GUEST") && !strcmp(getenv("EXFAT_DISPOSABLE_GUEST"), "1"));
        strcpy(device, "/dev/vda");
    } else {
        REQUIRE(getenv("GITHUB_ACTIONS") && !strcmp(getenv("GITHUB_ACTIONS"), "true"));
        REQUIRE(getenv("EXFAT_DISPOSABLE_CI") && !strcmp(getenv("EXFAT_DISPOSABLE_CI"), "1"));
        attach_image(argv[2], reference, device, sizeof(device));
    }
    begin_mount(device, guest ? "/exfat-work" : argv[3], prepare, !guest);
    if (prepare) prepare_image(self, head);
    else observe(self, head);
    REQUIRE(close(self) == 0);
    REQUIRE(cleanup());
    printf("EXFAT_CLEANUP unmounted=1 backing=%s detached=%d\n", guest ? "virtio" : "loop", !guest);
    return 0;
}
