// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "board_policy.h"
#include "board_policy_inputs.h"
#include "boot_diagnostics.h"
#include "apparmor_epoch.h"
#include "linux_run_label.h"
#include "device_source.h"
#include "device_template.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/openat2.h>
#include <linux/nsfs.h>
#include <sched.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/statvfs.h>
#include <sys/xattr.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/utsname.h>
#include <unistd.h>
#include <stdbool.h>
#include <limits.h>
#include <linux/capability.h>
#include <linux/lsm.h>
#include <linux/sched.h>
#include <poll.h>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/sysmacros.h>
#include <sys/wait.h>
#include <time.h>

#define POLICY_DIR "/usr/lib/droidloom/production/current/board-policy"
#define SELINUX_DIR "/sys/fs/selinux"
#define AA_DIR "/sys/kernel/security/apparmor"
#define SELINUXFS_MAGIC 0xf97cff8cU

static int reject(int error)
{
    errno = error;
    return -1;
}

struct input {
    size_t size;
    const char *digest;
    const char *path;
    unsigned char *data;
};

/* The global PID 1 captures its own real mount namespace before first load.
 * Only its fixed identity data crosses into the later native return helper;
 * there is no namespace bind mount, foreign proc lookup or caller authority. */
struct host_mount_identity {
    int fd;
    struct stat identity;
    char boot_id[37];
};
static int epoch_same(const struct stat *a, const struct stat *b);
static int publish_host_mount_identity(const struct host_mount_identity *held,
                                        int directory, const char *policy_digest);

static int hold_host_mount_identity(struct host_mount_identity *held)
{
    if (!held || held->fd >= 0 || getpid() != 1 || geteuid() != 0)
        return reject(EINVAL);
    int fd = open("/proc/self/ns/mnt", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    struct statfs fs;
    struct stat before, after;
    int error = 0;
    if (fstat(fd, &before) < 0 || fstatfs(fd, &fs) < 0)
        error = errno;
    else if ((unsigned long)fs.f_type != NSFS_MAGIC || !S_ISREG(before.st_mode) ||
             before.st_uid || before.st_gid || before.st_nlink != 1 ||
             ioctl(fd, NS_GET_NSTYPE) != CLONE_NEWNS)
        error = EACCES;
    int boot = -1;
    if (!error) {
        boot = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
        if (boot < 0) error = errno;
    }
    char value[38];
    size_t pos = 0;
    if (!error && fstatfs(boot, &fs) < 0) error = errno;
    if (!error && (unsigned long)fs.f_type != PROC_SUPER_MAGIC) error = EXDEV;
    while (!error && pos < sizeof(value)) {
        ssize_t n = read(boot, value + pos, sizeof(value) - pos);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { error = errno; break; }
        if (!n) break;
        pos += (size_t)n;
    }
    if (!error && (pos != 37 || value[36] != '\n')) error = EBADMSG;
    for (size_t i = 0; !error && i < 36; ++i) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (value[i] != '-') error = EBADMSG;
        } else if (!((value[i] >= '0' && value[i] <= '9') ||
                     (value[i] >= 'a' && value[i] <= 'f'))) error = EBADMSG;
    }
    if (!error && fstat(fd, &after) < 0) error = errno;
    if (!error && !epoch_same(&before, &after)) error = ESTALE;
    if (boot >= 0) close(boot);
    if (error) { close(fd); return reject(error); }
    memcpy(held->boot_id, value, 36);
    held->boot_id[36] = 0;
    held->identity = before;
    held->fd = fd;
    return 0;
}

static int read_admitted(struct input *input)
{
    struct stat st;
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_size = 0;
    int fd = open(input->path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0)
        return -1;
    int error = 0;
    if (fstat(fd, &st) < 0)
        error = errno;
    else if (!S_ISREG(st.st_mode) || st.st_uid != 0 || st.st_gid != 0 ||
             (st.st_mode & 0022) || st.st_size < 0 || (uint64_t)st.st_size != input->size)
        error = EACCES;
    if (!error && (input->data = malloc(input->size)) == NULL)
        error = ENOMEM;
    size_t pos = 0;
    while (!error && pos < input->size) {
        ssize_t n = read(fd, input->data + pos, input->size - pos);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            error = n < 0 ? errno : EIO;
        else
            pos += (size_t)n;
    }
    close(fd);
    if (error)
        return reject(error);
    if (EVP_Digest(input->data, input->size, hash, &hash_size, EVP_sha256(), NULL) != 1 || hash_size != 32)
        return reject(EIO);
    char hex[65];
    for (size_t i = 0; i < 32; ++i)
        snprintf(hex + 2 * i, 3, "%02x", hash[i]);
    if (strcmp(hex, input->digest) != 0)
        return reject(EBADMSG);
    return 0;
}

static int mount_kernel_fs(const char *type, const char *where, unsigned long magic)
{
    struct statfs fs;
    if (statfs(where, &fs) < 0)
        return -1;
    if ((unsigned long)fs.f_type == magic)
        return 0;
    if ((unsigned long)fs.f_type != SYSFS_MAGIC)
        return reject(EXDEV);
    if (mount(type, where, type, MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) < 0)
        return -1;
    if (statfs(where, &fs) < 0)
        return -1;
    return (unsigned long)fs.f_type == magic ? 0 : reject(EXDEV);
}

static int prepare_ubuntu_cgroup2(void)
{
    const char *where = "/sys/fs/cgroup";
    struct statfs fs;
    if (statfs(where, &fs) < 0)
        return -1;
    if ((unsigned long)fs.f_type != CGROUP2_SUPER_MAGIC) {
        if ((unsigned long)fs.f_type != SYSFS_MAGIC)
            return reject(EXDEV);
        if (mount("cgroup2", where, "cgroup2", MS_NOSUID | MS_NODEV | MS_NOEXEC,
                  "nsdelegate,memory_recursiveprot") < 0)
            return -1;
    }
    if (statfs(where, &fs) < 0)
        return -1;
    if ((unsigned long)fs.f_type != CGROUP2_SUPER_MAGIC)
        return reject(EXDEV);
    int fd = open("/sys/fs/cgroup/cgroup.controllers", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0)
        return -1;
    char data[1024];
    ssize_t n;
    do { n = read(fd, data, sizeof(data) - 1); } while (n < 0 && errno == EINTR);
    int error = errno;
    close(fd);
    if (n < 0)
        return reject(error);
    if (n == 0 || n >= (ssize_t)sizeof(data) - 1)
        return reject(EBADMSG);
    data[n] = 0;
    const char *const selected[] = {"cpu", "cpuset", "io", "memory", "pids"};
    unsigned found = 0;
    char *rest = NULL;
    for (char *token = strtok_r(data, " \t\r\n", &rest); token; token = strtok_r(NULL, " \t\r\n", &rest)) {
        for (size_t i = 0; i < sizeof(selected)/sizeof(selected[0]); ++i)
            if (strcmp(token, selected[i]) == 0)
                found |= 1U << i;
    }
    return found == 31 ? 0 : reject(ENODEV);
}

static int check_value(const char *path, const char *expected)
{
    char value[256];
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0)
        return -1;
    ssize_t n;
    do { n = read(fd, value, sizeof(value) - 1); } while (n < 0 && errno == EINTR);
    int error = errno;
    close(fd);
    if (n < 0)
        return reject(error);
    while (n && (value[n-1] == '\n' || value[n-1] == '\0'))
        --n;
    value[n] = 0;
    return strcmp(value, expected) == 0 ? 0 : reject(EACCES);
}

static int class_directory_is_empty(void)
{
    DIR *dir = opendir(SELINUX_DIR "/class");
    if (!dir)
        return -1;
    int error = 0;
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(dir))) {
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) {
            error = EALREADY;
            break;
        }
    }
    if (!error)
        error = errno;
    closedir(dir);
    return error ? reject(error) : 0;
}

static int initial_ubuntu_kernel(void)
{
    struct utsname kernel;
    struct statfs root;
    if (uname(&kernel) < 0 || statfs("/", &root) < 0)
        return -1;
    if (getpid() != 1 || geteuid() != 0 || strcmp(kernel.release, DROIDLOOM_BOARD_KERNEL_RELEASE) ||
        (unsigned long)root.f_type != EXT4_SUPER_MAGIC)
        return reject(EXDEV);
    const char *namespaces[] = {"user", "pid", "mnt"};
    for (size_t i = 0; i < sizeof(namespaces)/sizeof(namespaces[0]); ++i) {
        char path[64];
        struct stat self, first;
        snprintf(path, sizeof(path), "/proc/self/ns/%s", namespaces[i]);
        if (stat(path, &self) < 0)
            return -1;
        snprintf(path, sizeof(path), "/proc/1/ns/%s", namespaces[i]);
        if (stat(path, &first) < 0)
            return -1;
        if (self.st_ino != first.st_ino || self.st_dev != first.st_dev)
            return reject(EXDEV);
    }
    if (mount_kernel_fs("securityfs", "/sys/kernel/security", SECURITYFS_MAGIC) ||
        check_value("/sys/kernel/security/lsm", "lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm") ||
        mount_kernel_fs("selinuxfs", SELINUX_DIR, SELINUXFS_MAGIC) ||
        check_value(SELINUX_DIR "/enforce", "1") || class_directory_is_empty() ||
        check_value(AA_DIR "/profiles", ""))
        return -1;
    return 0;
}

static uint32_t le32(const unsigned char *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static int submit(const char *path, const unsigned char *data, size_t length)
{
    int fd = open(path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    ssize_t n;
    do { n = write(fd, data, length); } while (n < 0 && errno == EINTR);
    int error = n < 0 ? errno : (size_t)n == length ? 0 : EIO;
    close(fd);
    return error ? reject(error) : 0;
}

/* Counts, order, raw bytes and epoch indexes come from the same committed lock
 * as the normal AppArmor publisher. Appending a role never moves the original
 * loader/Android/broker custody slots. */
static int apparmor_profile_bytes(const unsigned char *data, size_t length,
                                 const struct droidloom_board_apparmor_profile *role)
{
    if (length != role->size)
        return reject(EBADMSG);
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int count = 0;
    if (EVP_Digest(data, length, digest, &count, EVP_sha256(), NULL) != 1 || count != 32)
        return reject(EIO);
    char actual[65];
    for (size_t i = 0; i < 32; ++i)
        snprintf(actual + 2 * i, 3, "%02x", digest[i]);
    return strcmp(actual, role->compiled_sha256) ? reject(EBADMSG) : 0;
}

static int apparmor_profiles(const struct input *pack, int activate,
                             struct droidloom_raw_profile selected[4])
{
    if (pack->size < 12 || memcmp(pack->data, "DLAA0001", 8) ||
        le32(pack->data + 8) != DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES)
        return reject(EBADMSG);
    static const unsigned int epoch_indexes[4] = {
        DROIDLOOM_BOARD_APPARMOR_EPOCH_LOADER_INDEX,
        DROIDLOOM_BOARD_APPARMOR_EPOCH_ANDROID_INDEX,
        DROIDLOOM_BOARD_APPARMOR_EPOCH_BROKER_INDEX,
        DROIDLOOM_BOARD_APPARMOR_EPOCH_CAMERA_INDEX,
    };
    size_t pos = 12;
    for (unsigned int i = 0; i != DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES; ++i) {
        if (pack->size - pos < 4)
            return reject(EBADMSG);
        size_t length = le32(pack->data + pos);
        pos += 4;
        if (!length || length > pack->size - pos)
            return reject(EBADMSG);
        if (i >= DROIDLOOM_BOARD_APPARMOR_UBUNTU_ENTRIES) {
            const size_t board = i - DROIDLOOM_BOARD_APPARMOR_UBUNTU_ENTRIES;
            if (board >= DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES)
                return reject(EBADMSG);
            if (apparmor_profile_bytes(pack->data + pos, length,
                                       &droidloom_board_apparmor_profiles[board]) < 0)
                return -1;
        }
        if (selected) {
            for (size_t role = 0; role < 4; ++role) {
                if (i == epoch_indexes[role])
                    selected[role] = (struct droidloom_raw_profile){pack->data + pos, length};
            }
        }
        if (activate && submit(AA_DIR "/.load", pack->data + pos, length) < 0)
            return -1;
        pos += length;
    }
    return pos == pack->size ? 0 : reject(EBADMSG);
}


/* The working boot's early recovery already armed one Software Watchdog.
 * The first-load factory proves that exact devtmpfs inode before loading policy.
 * A private, non-exec child assigns its new type after load. No later host role
 * receives relabel authority, and the parent never opens a watchdog body. */
#define WORKING_WATCHDOG_CONTEXT "u:object_r:p4_linux_working_watchdog_t:s0"
#define WORKING_WATCHDOG_LABELER "u:r:p4_linux_working_watchdog_label_t:s0"
#define WORKING_WATCHDOG_OLD_CONTEXT "u:object_r:device:s0"
#define WORKING_WATCHDOG_TOTAL_NS 6000000000ULL
#define WORKING_WATCHDOG_RETIRE_NS 2000000000ULL
#ifndef STATX_MNT_ID_UNIQUE
#define STATX_MNT_ID_UNIQUE 0x4000U
#endif
#ifndef SYS_setxattrat
#define SYS_setxattrat 463
#endif
#ifndef SYS_getxattrat
#define SYS_getxattrat 464
#endif

struct working_watchdog_birth {
    int selected, device, directory, proc_fds;
    struct stat inode;
    uint64_t mount_id;
    char name[16];
};

struct working_xattr_args {
    uint64_t value;
    uint32_t size, flags;
};
_Static_assert(sizeof(struct working_xattr_args) == 16, "selected xattrat ABI");

static int working_now(uint64_t *value)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) < 0) return -1;
    if (t.tv_sec < 0 || t.tv_nsec < 0 || t.tv_nsec >= 1000000000L ||
        (uint64_t)t.tv_sec > (UINT64_MAX - 999999999ULL) / 1000000000ULL)
        return reject(EOVERFLOW);
    *value = (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
    return 0;
}

static int working_before(uint64_t end)
{
    uint64_t now;
    if (working_now(&now) < 0) return -1;
    return now < end ? 0 : reject(ETIMEDOUT);
}

static int working_same_inode(const struct stat *a, const struct stat *b, int ctime)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
        a->st_mode == b->st_mode && a->st_uid == b->st_uid &&
        a->st_gid == b->st_gid && a->st_nlink == b->st_nlink &&
        a->st_size == b->st_size && a->st_rdev == b->st_rdev &&
        a->st_mtim.tv_sec == b->st_mtim.tv_sec &&
        a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
        (!ctime || (a->st_ctim.tv_sec == b->st_ctim.tv_sec &&
                    a->st_ctim.tv_nsec == b->st_ctim.tv_nsec));
}

static int working_mount_id(int fd, uint64_t *value)
{
    struct statx s;
    if (statx(fd, "", AT_EMPTY_PATH | AT_SYMLINK_NOFOLLOW,
              STATX_MNT_ID_UNIQUE, &s) < 0) return -1;
    if (!(s.stx_mask & STATX_MNT_ID_UNIQUE) || !s.stx_mnt_id)
        return reject(EOPNOTSUPP);
    *value = s.stx_mnt_id;
    return 0;
}

static int working_open(int parent, const char *name, int flags)
{
    struct open_how how = {
        .flags = (uint64_t)(flags | O_NOFOLLOW | O_CLOEXEC),
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS,
    };
    return (int)syscall(SYS_openat2, parent, name, &how, sizeof(how));
}

static int working_directory(int fd, unsigned long magic, struct stat *identity)
{
    struct statfs fs;
    if (fstat(fd, identity) < 0 || fstatfs(fd, &fs) < 0) return -1;
    return S_ISDIR(identity->st_mode) && !identity->st_uid &&
        !identity->st_gid && !(identity->st_mode & 0022) &&
        (unsigned long)fs.f_type == magic ? 0 : reject(EACCES);
}

static ssize_t working_read(int fd, char *out, size_t capacity)
{
    size_t used = 0;
    while (used < capacity) {
        ssize_t n = read(fd, out + used, capacity - used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) return -1;
        if (!n) return (ssize_t)used;
        used += (size_t)n;
    }
    return reject(EOVERFLOW);
}

static int working_hex(const char *s)
{
    return strlen(s) == 64 && strspn(s, "0123456789abcdef") == 64;
}

/* This is only a closed first-load selector, not a qualification authority.
 * The normal working owner still validates the complete pinned configuration,
 * boot grammar, original/copy lineage, runtime selection and actual Main. */
static int working_selector(char *line, char return_sha256[65])
{
    const char *keys[] = {"droidloom.working=", "droidloom.working.config=",
                          "droidloom.working.return="};
    unsigned seen = 0;
    int legacy = 0;
    char *rest = NULL;
    for (char *v = strtok_r(line, " \t\r\n", &rest); v;
         v = strtok_r(NULL, " \t\r\n", &rest)) {
        if (!strncmp(v, "droidloom.once", strlen("droidloom.once")))
            legacy = 1;
        if (strncmp(v, "droidloom.working", strlen("droidloom.working")))
            continue;
        int found = 0;
        for (unsigned i = 0; i < 3; ++i) {
            size_t n = strlen(keys[i]);
            if (!strncmp(v, keys[i], n)) {
                if ((seen & (1U << i)) || !working_hex(v + n))
                    return reject(EBADMSG);
                seen |= 1U << i;
                if (i == 2) memcpy(return_sha256, v + n, 65);
                found = 1;
                break;
            }
        }
        if (!found) return reject(EBADMSG);
    }
    if (!seen) return 0;
    return seen == 7 && !legacy ? 1 : reject(EBADMSG);
}

static int working_selected_boot(void)
{
    int fd = working_open(AT_FDCWD, "/proc/cmdline", O_RDONLY | O_NONBLOCK);
    if (fd < 0) return -1;
    struct statfs fs;
    char line[32770], expected[65] = {0};
    int error = 0;
    ssize_t size = -1;
    if (fstatfs(fd, &fs) < 0) error = errno;
    if (!error && (unsigned long)fs.f_type != PROC_SUPER_MAGIC) error = EXDEV;
    if (!error) {
        size = working_read(fd, line, sizeof(line) - 1);
        if (size < 0) error = errno;
        else if (!size || size > 32768 || memchr(line, 0, (size_t)size)) error = EBADMSG;
    }
    close(fd);
    if (error) return reject(error);
    line[size] = 0;
    int selected = working_selector(line, expected);
    if (selected <= 0) return selected;
    fd = working_open(AT_FDCWD, "/etc/droidloom/qualification/working-return.json",
                      O_RDONLY | O_NONBLOCK);
    if (fd < 0) return -1;
    struct stat before, after, named, root;
    if (fstat(fd, &before) < 0 || fstatfs(fd, &fs) < 0 || stat("/", &root) < 0)
        error = errno;
    else if (before.st_mode != (S_IFREG | 0400) || before.st_uid || before.st_gid ||
             before.st_nlink != 1 || before.st_size < 64 || before.st_size > 65536 ||
             (unsigned long)fs.f_type != EXT4_SUPER_MAGIC || before.st_dev != root.st_dev)
        error = EACCES;
    unsigned char *body = !error ? malloc((size_t)before.st_size + 1) : NULL;
    if (!error && !body) error = ENOMEM;
    if (!error) {
        size = working_read(fd, (char *)body, (size_t)before.st_size + 1);
        if (size < 0) error = errno;
        else if (size != before.st_size) error = ESTALE;
    }
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned count = 0;
    char actual[65];
    if (!error && (EVP_Digest(body, (size_t)size, digest, &count, EVP_sha256(), NULL) != 1 ||
                   count != 32)) error = EIO;
    if (!error) {
        for (size_t i = 0; i < 32; ++i)
            snprintf(actual + 2 * i, 3, "%02x", digest[i]);
        if (strcmp(actual, expected)) error = EBADMSG;
    }
    if (!error && (fstat(fd, &after) < 0 ||
        lstat("/etc/droidloom/qualification/working-return.json", &named) < 0)) error = errno;
    if (!error && (!working_same_inode(&before, &after, 1) ||
                   !working_same_inode(&after, &named, 1))) error = ESTALE;
    free(body);
    close(fd);
    return error ? reject(error) : 1;
}

static int working_number(const char *text, uint32_t *value)
{
    size_t n = strlen(text);
    if (!n || n > 10 || (n > 1 && text[0] == '0') ||
        strspn(text, "0123456789") != n) return reject(EBADMSG);
    uint64_t result = 0;
    for (size_t i = 0; i < n; ++i) result = result * 10 + (unsigned)(text[i] - '0');
    if (result > UINT32_MAX) return reject(EOVERFLOW);
    *value = (uint32_t)result;
    return 0;
}

static int working_watchdog_name(const char *name)
{
    uint32_t value;
    if (strncmp(name, "watchdog", 8) || strlen(name + 8) > 3 ||
        working_number(name + 8, &value) < 0 || value > 999)
        return reject(EBADMSG);
    return 0;
}

static int working_attribute(int directory, const char *name, char value[513])
{
    int fd = working_open(directory, name, O_RDONLY | O_NONBLOCK);
    if (fd < 0) return -1;
    struct stat before, after, named;
    struct statfs fs;
    int error = 0;
    ssize_t n = -1;
    if (fstat(fd, &before) < 0 || fstatfs(fd, &fs) < 0) error = errno;
    else if (!S_ISREG(before.st_mode) || (before.st_mode & 0022) ||
             before.st_uid || before.st_gid || before.st_nlink != 1 ||
             (unsigned long)fs.f_type != SYSFS_MAGIC) error = EACCES;
    if (!error) {
        n = working_read(fd, value, 513);
        if (n < 0) error = errno;
        else if (!n || n > 512 || value[n - 1] != '\n' ||
                 memchr(value, 0, (size_t)n) || memchr(value, '\r', (size_t)n) ||
                 memchr(value, '\n', (size_t)n - 1)) error = EBADMSG;
    }
    if (!error && (fstat(fd, &after) < 0 ||
        fstatat(directory, name, &named, AT_SYMLINK_NOFOLLOW) < 0)) error = errno;
    if (!error && (!working_same_inode(&before, &after, 1) ||
                   !working_same_inode(&after, &named, 1))) error = ESTALE;
    close(fd);
    if (error) return reject(error);
    value[n - 1] = 0;
    return 0;
}

static int working_devtmpfs(int directory, dev_t filesystem_device)
{
    /* mountinfo uses the ordinary mount ID; never compare it with the distinct
     * STATX_MNT_ID_UNIQUE value retained for the inode custody bookends. */
    struct statx observed;
    if (statx(directory, "", AT_EMPTY_PATH | AT_SYMLINK_NOFOLLOW,
              STATX_MNT_ID, &observed) < 0) return -1;
    if (!(observed.stx_mask & STATX_MNT_ID) || !observed.stx_mnt_id)
        return reject(EOPNOTSUPP);
    uint64_t mount_id = observed.stx_mnt_id;
    int fd = working_open(AT_FDCWD, "/proc/1/mountinfo", O_RDONLY | O_NONBLOCK);
    if (fd < 0) return -1;
    char *body = malloc(131073);
    if (!body) { close(fd); return reject(ENOMEM); }
    ssize_t n = working_read(fd, body, 131073);
    int error = n < 0 ? errno : 0;
    close(fd);
    if (!error && (!n || n > 131072 || memchr(body, 0, (size_t)n))) error = EBADMSG;
    unsigned found = 0;
    if (!error) {
        body[n] = 0;
        char *rest = NULL;
        for (char *line = strtok_r(body, "\n", &rest); line;
             line = strtok_r(NULL, "\n", &rest)) {
            unsigned long long id, parent;
            unsigned major_value, minor_value;
            char root[256], point[256], type[64];
            char *sep = strstr(line, " - ");
            if (!sep || sscanf(line, "%llu %llu %u:%u %255s %255s",
                               &id, &parent, &major_value, &minor_value, root, point) != 6 ||
                sscanf(sep + 3, "%63s", type) != 1) { error = EBADMSG; break; }
            if ((uint64_t)id == mount_id) {
                if (++found != 1 || strcmp(root, "/") || strcmp(point, "/dev") ||
                    strcmp(type, "devtmpfs") || major_value != major(filesystem_device) ||
                    minor_value != minor(filesystem_device)) { error = EACCES; break; }
            }
        }
    }
    free(body);
    return error ? reject(error) : found == 1 ? 0 : reject(EXDEV);
}

static void working_watchdog_close(struct working_watchdog_birth *held)
{
    if (held->device >= 0) close(held->device);
    if (held->directory >= 0) close(held->directory);
    if (held->proc_fds >= 0) close(held->proc_fds);
    *held = (struct working_watchdog_birth){ .device = -1, .directory = -1, .proc_fds = -1 };
}

static int working_watchdog_hold(struct working_watchdog_birth *held)
{
    if (!held || held->device != -1 || held->directory != -1 || held->proc_fds != -1 ||
        held->selected || getpid() != 1 || geteuid() != 0) return reject(EINVAL);
    int selected = working_selected_boot();
    if (selected <= 0) return selected;
    int base = -1, chosen = -1, stream = -1, device = -1, dev = -1, proc_fds = -1;
    DIR *inventory = NULL;
    struct stat base_before, base_after, directory_before, directory_after, dev_stat, inode, named;
    uint64_t mount_id, node_mount;
    int error = 0;
    char name[16] = {0}, text[513];
    base = working_open(AT_FDCWD, "/sys/devices/virtual/watchdog", O_PATH | O_DIRECTORY);
    if (base < 0 || working_directory(base, SYSFS_MAGIC, &base_before) < 0) { error = errno; goto out; }
    stream = working_open(base, ".", O_RDONLY | O_DIRECTORY);
    if (stream < 0) { error = errno; goto out; }
    inventory = fdopendir(stream);
    if (!inventory) { error = errno; goto out; }
    stream = -1;
    unsigned count = 0, matches = 0;
    for (;;) {
        errno = 0;
        struct dirent *row = readdir(inventory);
        if (!row) { if (errno) error = errno; break; }
        if (!strcmp(row->d_name, ".") || !strcmp(row->d_name, "..")) continue;
        if (++count > 16 || working_watchdog_name(row->d_name) < 0) { error = EBADMSG; break; }
        int candidate = working_open(base, row->d_name, O_PATH | O_DIRECTORY);
        struct stat candidate_stat;
        if (candidate < 0) { error = errno; break; }
        if (working_directory(candidate, SYSFS_MAGIC, &candidate_stat) < 0 ||
            working_attribute(candidate, "identity", text) < 0) error = errno;
        if (!error && !strcmp(text, "Software Watchdog")) {
            if (++matches != 1) error = EEXIST;
            else {
                memcpy(name, row->d_name, strlen(row->d_name) + 1);
                chosen = candidate;
                directory_before = candidate_stat;
                candidate = -1;
            }
        }
        if (candidate >= 0) close(candidate);
        if (error) break;
    }
    if (!error && matches != 1) error = ENODEV;
    if (error) goto out;
    const char *attributes[] = {"identity", "state", "nowayout", "timeout"};
    const char *values[] = {"Software Watchdog", "active", "1", "900"};
    for (size_t i = 0; i < 4; ++i)
        if (working_attribute(chosen, attributes[i], text) < 0) {
            error = errno; goto out;
        } else if (strcmp(text, values[i])) { error = EACCES; goto out; }
    if (working_attribute(chosen, "dev", text) < 0) { error = errno; goto out; }
    char *colon = strchr(text, ':');
    uint32_t major_value, minor_value;
    if (!colon || strchr(colon + 1, ':')) { error = EBADMSG; goto out; }
    *colon = 0;
    if (working_number(text, &major_value) < 0 || working_number(colon + 1, &minor_value) < 0 ||
        !major_value) { error = EBADMSG; goto out; }
    dev_t rdev = makedev(major_value, minor_value);
    if (major(rdev) != major_value || minor(rdev) != minor_value) { error = EOVERFLOW; goto out; }
    dev = working_open(AT_FDCWD, "/dev", O_PATH | O_DIRECTORY);
    if (dev < 0 || working_directory(dev, TMPFS_MAGIC, &dev_stat) < 0 ||
        working_mount_id(dev, &mount_id) < 0 || working_devtmpfs(dev, dev_stat.st_dev) < 0) {
        error = errno; goto out;
    }
    device = working_open(dev, name, O_PATH);
    if (device < 0 || fstat(device, &inode) < 0 || working_mount_id(device, &node_mount) < 0 ||
        fstatat(dev, name, &named, AT_SYMLINK_NOFOLLOW) < 0) { error = errno; goto out; }
    if (inode.st_mode != (S_IFCHR | 0600) || inode.st_uid || inode.st_gid ||
        inode.st_nlink != 1 || inode.st_rdev != rdev || inode.st_dev != dev_stat.st_dev ||
        node_mount != mount_id || !working_same_inode(&inode, &named, 1)) {
        error = EACCES; goto out;
    }
    if (fstat(base, &base_after) < 0 || fstat(chosen, &directory_after) < 0) { error = errno; goto out; }
    if (!working_same_inode(&base_before, &base_after, 1) ||
        !working_same_inode(&directory_before, &directory_after, 1)) { error = ESTALE; goto out; }
    /* Keep the armed values and named device bookend adjacent to custody. */
    for (size_t i = 0; i < 4; ++i)
        if (working_attribute(chosen, attributes[i], text) < 0) {
            error = errno; goto out;
        } else if (strcmp(text, values[i])) { error = EACCES; goto out; }
    proc_fds = working_open(AT_FDCWD, "/proc/1/fd", O_PATH | O_DIRECTORY);
    struct stat proc_stat;
    if (proc_fds < 0 || working_directory(proc_fds, PROC_SUPER_MAGIC, &proc_stat) < 0) {
        error = errno; goto out;
    }
    held->selected = 1;
    held->device = device; device = -1;
    held->directory = dev; dev = -1;
    held->proc_fds = proc_fds; proc_fds = -1;
    held->inode = inode;
    held->mount_id = mount_id;
    memcpy(held->name, name, sizeof(name));
out:
    if (inventory) closedir(inventory);
    if (stream >= 0) close(stream);
    if (base >= 0) close(base);
    if (chosen >= 0) close(chosen);
    if (device >= 0) close(device);
    if (dev >= 0) close(dev);
    if (proc_fds >= 0) close(proc_fds);
    return error ? reject(error) : 0;
}

static int working_context_bytes(const char *value, ssize_t size, const char *expected)
{
    size_t n = strlen(expected);
    return size >= 0 && ((size_t)size == n ||
        ((size_t)size == n + 1 && (value[n] == 0 || value[n] == '\n'))) &&
        !memcmp(value, expected, n);
}

static int working_xattr(int proc_fds, int device, long operation, void *body, uint32_t size)
{
    char name[32];
    int n = snprintf(name, sizeof(name), "%d", device);
    if (n < 1 || (size_t)n >= sizeof(name)) return reject(EOVERFLOW);
    struct stat held, followed;
    if (fstat(device, &held) < 0 || fstatat(proc_fds, name, &followed, 0) < 0) return -1;
    int flags = fcntl(device, F_GETFL);
    if (flags < 0) return -1;
    if (!working_same_inode(&held, &followed, 1) ||
        (flags & O_PATH) != O_PATH) return reject(ESTALE);
    struct working_xattr_args args = {(uint64_t)(uintptr_t)body, size, 0};
    long result = syscall(operation, proc_fds, name, 0, "security.selinux", &args, sizeof(args));
    if (result < 0) return -1;
    if (fstat(device, &held) < 0 || fstatat(proc_fds, name, &followed, 0) < 0) return -1;
    return working_same_inode(&held, &followed, 1) ? (int)result : reject(ESTALE);
}

/* Selected 6.18 has no /proc/<pid>/attr/selinux directory. The typed
 * interface selects SELinux explicitly and is SELF-only, even under AA-first
 * stacking. Compare one complete canonical record; unsupported is an error. */
static int working_self_record(const struct lsm_ctx *context, long count,
                               uint32_t size, size_t capacity, const char *expected)
{
    size_t n = strlen(expected) + 1;
    size_t aligned = (sizeof(*context) + n + 7) & ~(size_t)7;
    if (n > 128 || count != 1 || context->id != LSM_ID_SELINUX || context->flags ||
        context->ctx_len != n || context->len != aligned || size != aligned ||
        aligned > capacity || memcmp(context->ctx, expected, n))
        return reject(EACCES);
    for (size_t i = n; i < aligned - sizeof(*context); ++i)
        if (context->ctx[i]) return reject(EACCES);
    return 0;
}
static int working_process_context(const char *expected)
{
    _Alignas(struct lsm_ctx) unsigned char bytes[256] = {0};
    struct lsm_ctx *context = (struct lsm_ctx *)bytes;
    _Static_assert(sizeof(*context) == 32, "selected typed LSM context header");
    context->id = LSM_ID_SELINUX;
    uint32_t size = sizeof(bytes);
    long tid = syscall(SYS_gettid);
    if (tid <= 0) return reject(EACCES);
    long count = syscall(SYS_lsm_get_self_attr, LSM_ATTR_CURRENT,
                         context, &size, LSM_FLAG_SINGLE);
    if (count < 0) return -1;
    if (syscall(SYS_gettid) != tid) return reject(ESTALE);
    return working_self_record(context, count, size, sizeof(bytes), expected);
}
static int working_set_labeler_context(uint64_t end)
{
    _Alignas(struct lsm_ctx) unsigned char bytes[256] = {0};
    struct lsm_ctx *context = (struct lsm_ctx *)bytes;
    const size_t n = sizeof(WORKING_WATCHDOG_LABELER);
    _Static_assert(sizeof(WORKING_WATCHDOG_LABELER) <= 128, "fixed labeler context bound");
    if (working_before(end) < 0) return -1;
    long tid = syscall(SYS_gettid);
    if (tid <= 0) return reject(EACCES);
    context->id = LSM_ID_SELINUX;
    context->len = sizeof(*context) + n;
    context->ctx_len = n;
    memcpy(context->ctx, WORKING_WATCHDOG_LABELER, n);
    long result = syscall(SYS_lsm_set_self_attr, LSM_ATTR_CURRENT,
                          context, (uint32_t)context->len, 0);
    if (result < 0) return -1;
    if (result || syscall(SYS_gettid) != tid) return reject(ESTALE);
    return working_before(end);
}

static int working_caps_empty(void)
{
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct values[2] = {{0}, {0}};
    if (syscall(SYS_capget, &header, values) < 0) return -1;
    for (size_t i = 0; i < 2; ++i)
        if (values[i].effective || values[i].permitted || values[i].inheritable)
            return reject(EACCES);
    _Static_assert(CAP_LAST_CAP == 40, "selected capability upper bound");
    for (unsigned i = 0; i <= CAP_LAST_CAP; ++i)
        if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, i, 0, 0) != 0)
            return reject(EACCES);
    return 0;
}

static int working_zero_caps(void)
{
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct values[2] = {{0}, {0}};
    if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) < 0 ||
        syscall(SYS_capset, &header, values) < 0) return -1;
    return working_caps_empty();
}

static int working_child_label(const struct working_watchdog_birth *held, uint64_t end)
{
    if (getpid() <= 1 || getppid() != 1 || getuid() || geteuid() || getgid() || getegid() ||
        working_before(end) < 0 || working_process_context("u:r:kernel:s0") < 0)
        return reject(EACCES);
    /* These are the only inherited descriptors retained by the non-exec child:
     * its exact O_PATH device and its own proc FD directory. */
    int saved_device = fcntl(held->device, F_DUPFD_CLOEXEC, 6);
    char path[96];
    int n = snprintf(path, sizeof(path), "/proc/%d/fd", (int)getpid());
    if (saved_device < 0 || n < 1 || (size_t)n >= sizeof(path)) return -1;
    int proc_fds = working_open(AT_FDCWD, path, O_PATH | O_DIRECTORY);
    int saved_proc = proc_fds < 0 ? -1 : fcntl(proc_fds, F_DUPFD_CLOEXEC, 6);
    if (saved_proc < 0 || dup3(saved_device, 3, O_CLOEXEC) < 0 ||
        dup3(saved_proc, 4, O_CLOEXEC) < 0 ||
        syscall(SYS_close_range, 0, 2, 0) < 0 ||
        syscall(SYS_close_range, 5, UINT_MAX, 0) < 0) return -1;
    sigset_t empty;
    if (sigemptyset(&empty) < 0 || sigprocmask(SIG_SETMASK, &empty, NULL) < 0 ||
        working_zero_caps() < 0 || working_before(end) < 0) return -1;
    if (working_set_labeler_context(end) < 0) return -1;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) < 0 ||
        prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1 ||
        working_process_context(WORKING_WATCHDOG_LABELER) < 0 ||
        working_caps_empty() < 0 || getppid() != 1 || working_before(end) < 0) return reject(EACCES);
    struct stat before, after;
    uint64_t mount_id;
    if (fstat(3, &before) < 0 || working_mount_id(3, &mount_id) < 0) return -1;
    if (!working_same_inode(&before, &held->inode, 1) || mount_id != held->mount_id)
        return reject(ESTALE);
    char context[128];
    int size = working_xattr(4, 3, SYS_getxattrat, context, sizeof(context));
    if (size < 0 || !working_context_bytes(context, size, WORKING_WATCHDOG_OLD_CONTEXT))
        return reject(EACCES);
    if (working_before(end) < 0 ||
        working_xattr(4, 3, SYS_setxattrat, (void *)WORKING_WATCHDOG_CONTEXT,
                      sizeof(WORKING_WATCHDOG_CONTEXT) - 1) < 0) return -1;
    size = working_xattr(4, 3, SYS_getxattrat, context, sizeof(context));
    if (size < 0 || !working_context_bytes(context, size, WORKING_WATCHDOG_CONTEXT) ||
        fstat(3, &after) < 0 || !working_same_inode(&before, &after, 0) ||
        working_process_context(WORKING_WATCHDOG_LABELER) < 0 ||
        working_caps_empty() < 0 || working_before(end) < 0) return reject(ESTALE);
    return 0;
}

static int working_wait(int pidfd, uint64_t end)
{
    for (;;) {
        uint64_t now;
        if (working_now(&now) < 0) return -1;
        if (now >= end) return reject(ETIMEDOUT);
        uint64_t left = (end - now + 999999ULL) / 1000000ULL;
        struct pollfd p = {.fd = pidfd, .events = POLLIN};
        int n = poll(&p, 1, left > INT_MAX ? INT_MAX : (int)left);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) return -1;
        if (n > 0 && (p.revents & POLLIN)) return 0;
        if (n > 0) return reject(EIO);
    }
}

static int working_watchdog_label(const struct working_watchdog_birth *held)
{
    if (!held->selected) return 0;
    uint64_t now;
    if (getpid() != 1 || geteuid() || working_now(&now) < 0 ||
        now > UINT64_MAX - WORKING_WATCHDOG_TOTAL_NS) return reject(EACCES);
    const uint64_t end = now + WORKING_WATCHDOG_TOTAL_NS;
    const uint64_t work_end = end - WORKING_WATCHDOG_RETIRE_NS;
    int pidfd = -1;
    struct clone_args args = {
        .flags = CLONE_PIDFD | CLONE_CLEAR_SIGHAND,
        .pidfd = (uint64_t)(uintptr_t)&pidfd,
        .exit_signal = SIGCHLD,
    };
    pid_t child = (pid_t)syscall(SYS_clone3, &args, sizeof(args));
    if (child < 0) return -1;
    if (child == 0) {
        int rc = working_child_label(held, work_end);
        int error = errno;
        _exit(rc == 0 ? 0 : error > 0 && error < 255 ? error : 255);
    }
    if (pidfd < 0) return reject(EIO);
    int error = working_wait(pidfd, work_end) < 0 ? errno : 0;
    if (error) {
        /* No retry and no renewed work window. The remaining original two
         * seconds are solely for this owned child's forced retirement. */
        if (syscall(SYS_pidfd_send_signal, pidfd, SIGKILL, NULL, 0) < 0 && errno != ESRCH)
            error = errno;
        if (working_wait(pidfd, end) < 0) error = errno;
    }
    siginfo_t status;
    memset(&status, 0, sizeof(status));
    if (waitid((idtype_t)P_PIDFD, (id_t)pidfd, &status, WEXITED | WNOHANG) < 0)
        error = errno;
    else if (status.si_pid != child || status.si_code != CLD_EXITED || status.si_status != 0)
        error = status.si_code == CLD_EXITED && status.si_status > 0 ? status.si_status : ECHILD;
    close(pidfd);
    if (error) return reject(error);
    struct stat current, named;
    uint64_t mount_id;
    char context[128];
    int size = working_xattr(held->proc_fds, held->device, SYS_getxattrat, context, sizeof(context));
    if (size < 0 || !working_context_bytes(context, size, WORKING_WATCHDOG_CONTEXT) ||
        fstat(held->device, &current) < 0 ||
        fstatat(held->directory, held->name, &named, AT_SYMLINK_NOFOLLOW) < 0 ||
        working_mount_id(held->device, &mount_id) < 0 ||
        !working_same_inode(&current, &held->inode, 0) ||
        !working_same_inode(&current, &named, 1) || mount_id != held->mount_id ||
        working_before(end) < 0) return reject(ESTALE);
    return 0;
}

int droidloom_board_activate_policy(gid_t observer_gid, const char *cohort)
{
    struct input policy = {DROIDLOOM_BOARD_SELINUX_SIZE, DROIDLOOM_BOARD_SELINUX_SHA256, POLICY_DIR "/joint.policy", NULL};
    struct input aa = {DROIDLOOM_BOARD_APPARMOR_SIZE, DROIDLOOM_BOARD_APPARMOR_SHA256, POLICY_DIR "/ubuntu-apparmor.profiles", NULL};
    struct droidloom_apparmor_measurement observation = {0};
    struct droidloom_raw_profile selected_profiles[4] = {0};
    int status = -1, epoch_directory = -1;
    struct droidloom_linux_init_scope scope = { .root.fd = -1, .scope.fd = -1, .procs.fd = -1, .controllers.fd = -1, .system_slice.fd = -1, .root_membership.fd = -1, .root_subtree_control.fd = -1 };
    struct droidloom_linux_run run = {.fd = -1}, shm = {.fd = -1}, mount_monitor = {.fd = -1};
    struct droidloom_linux_tmpfiles tmpfiles = { .directory.fd = -1 };
    struct droidloom_linux_journal_store log_store = { .log.fd = -1, .journal.fd = -1 };
    struct droidloom_linux_credentials credentials = { .root.fd = -1, .systemd.fd = -1, .staging.fd = -1 };
    struct droidloom_linux_run udev = {.fd = -1}, udev_data = {.fd = -1};
    struct droidloom_readiness_paths paths = { .handoff.fd = -1, .readiness.fd = -1 };
    struct host_mount_identity mount_identity = { .fd = -1 };
    struct working_watchdog_birth watchdog = { .device = -1, .directory = -1, .proc_fds = -1 };
    const char *stage = "read admitted SELinux input";
    int rc = read_admitted(&policy);
    if (rc == 0) { stage = "read admitted AppArmor input"; rc = read_admitted(&aa); }
    if (rc == 0) { stage = "validate AppArmor framing"; rc = apparmor_profiles(&aa, 0, selected_profiles); }
    if (rc == 0) { stage = "check initial Ubuntu policy state"; rc = initial_ubuntu_kernel(); }
    if (rc == 0) { stage = "hold original PID 1 mount namespace and boot identity"; rc = hold_host_mount_identity(&mount_identity); }
    if (rc == 0) { stage = "hold the unique already-armed working Software Watchdog before first policy load"; rc = working_watchdog_hold(&watchdog); }
    if (rc == 0) { stage = "prepare the original Ubuntu unified cgroup hierarchy"; rc = prepare_ubuntu_cgroup2(); }
    if (rc == 0) { stage = "hold the original Ubuntu cgroup root and move global PID 1 to its init.scope"; rc = droidloom_hold_linux_init_scope(&scope); }
    if (rc == 0) { stage = "prepare the original Ubuntu shared memory mount"; rc = droidloom_hold_linux_shm(&shm); }
    if (rc == 0) { stage = "hold original Ubuntu /run"; rc = droidloom_hold_linux_run(&run); }
    if (rc == 0) { stage = "hold the exact Ubuntu mount-monitor directory"; rc = droidloom_hold_linux_mount_monitor(&run, &mount_monitor); }
    if (rc == 0) { stage = "create and hold the fixed Ubuntu tmpfiles directory"; rc = droidloom_hold_linux_tmpfiles(&run, &tmpfiles); }
    if (rc == 0) { stage = "hold the Ubuntu runtime log directory"; rc = droidloom_hold_ubuntu_log(&run, &log_store); }
    if (rc == 0) { stage = "hold the distro credentials root"; rc = droidloom_hold_ubuntu_credentials(&run, &credentials); }
    if (rc == 0) { stage = "hold the root-owned Ubuntu udev directory on the original /run"; rc = droidloom_hold_linux_udev(&run, &udev); }
    if (rc == 0) { stage = "hold the original Ubuntu udev database directory"; rc = droidloom_hold_linux_udev_data(&udev, &udev_data); }
    if (rc == 0) { stage = "hold the selected early readiness directory"; rc = droidloom_hold_readiness_paths(&run, observer_gid, &paths); }
    /* Per-generation device sources are prepared only by the dedicated
     * launcher after this boot-wide policy epoch has been sealed. */
    (void)cohort;
    if (rc == 0) { stage = "project the exact Ubuntu console, null and full device nodes"; rc = droidloom_project_linux_standard_devices(); }
    if (rc == 0) {
        stage = "prepare the protected read-only kernel measurement directory";
        epoch_directory = droidloom_prepare_epoch_directory(paths.handoff.fd);
        if (epoch_directory < 0) rc = -1;
    }
    if (rc == 0) { stage = "load the selected Ubuntu AppArmor profiles"; rc = apparmor_profiles(&aa, 1, NULL); }
    if (rc == 0) {
        stage = "capture original AppArmor namespace and loaded profile identities";
        rc = droidloom_capture_apparmor_epoch(&observation, selected_profiles);
    }
    if (rc == 0) {
        stage = "hold the real SELinux status page before its first policy load";
        status = droidloom_open_initial_selinux_status();
        if (status < 0) rc = -1;
    }
    if (rc == 0) { stage = "load initial selected joint SELinux policy"; rc = submit(SELINUX_DIR "/load", policy.data, policy.size); }
    if (rc == 0) { stage = "label the held Ubuntu cgroup root and its initial scope"; rc = droidloom_label_linux_init_scope(&scope); }
    if (rc == 0) { stage = "label the original Ubuntu shared memory root"; rc = droidloom_label_linux_shm(&shm); }
    if (rc == 0) { stage = "label the held Ubuntu /run inode"; rc = droidloom_label_linux_run(&run); }
    if (rc == 0) { stage = "label the held Ubuntu mount-monitor directory"; rc = droidloom_label_linux_mount_monitor(&mount_monitor); }
    if (rc == 0) { stage = "label the fixed held Ubuntu tmpfiles directory"; rc = droidloom_label_linux_tmpfiles(&run, &tmpfiles); }
    if (rc == 0) { stage = "label the held Ubuntu runtime log directory"; rc = droidloom_label_ubuntu_log(&log_store); }
    if (rc == 0) { stage = "label the held distro credentials root"; rc = droidloom_label_ubuntu_credentials(&credentials); }
    if (rc == 0) { stage = "label the held Ubuntu udev directory"; rc = droidloom_label_linux_udev(&udev); }
    if (rc == 0) { stage = "label the original Ubuntu udev database directory"; rc = droidloom_label_linux_udev_data(&udev_data); }
    if (rc == 0) { stage = "label the held private readiness directory"; rc = droidloom_label_readiness_paths(&paths); }
    if (rc == 0) { stage = "label the held Software Watchdog through the owned zero-capability first-load child"; rc = working_watchdog_label(&watchdog); }
    if (rc == 0) { stage = "publish the typed original host mount identity"; rc = publish_host_mount_identity(&mount_identity, paths.handoff.fd, policy.digest); }
    if (rc == 0) { stage = "seal the original kernel policy load epoch"; rc = droidloom_publish_apparmor_epoch(epoch_directory, status, policy.digest, &observation); }
    int error = errno;
    working_watchdog_close(&watchdog);
    if (mount_identity.fd >= 0) close(mount_identity.fd);
    if (status >= 0) close(status);
    if (epoch_directory >= 0) close(epoch_directory);
    if (rc < 0)
        droidloom_boot_diagnostics_report(DROIDLOOM_DIAGNOSTIC_POLICY, stage, error);
    if (paths.readiness.fd >= 0)
        close(paths.readiness.fd);
    if (paths.handoff.fd >= 0)
        close(paths.handoff.fd);
    droidloom_close_linux_init_scope(&scope);
    if (shm.fd >= 0)
        close(shm.fd);
    droidloom_close_ubuntu_log(&log_store);
    droidloom_close_ubuntu_credentials(&credentials);
    if (udev_data.fd >= 0)
        close(udev_data.fd);
    if (udev.fd >= 0)
        close(udev.fd);
    droidloom_close_linux_tmpfiles(&tmpfiles);
    if (mount_monitor.fd >= 0)
        close(mount_monitor.fd);
    if (run.fd >= 0)
        close(run.fd);
    free(aa.data);
    free(policy.data);
    return rc == 0 ? 0 : reject(error);
}

/* Reopen the typed, read-only first-load receipt after the board self-exec.
 * This is an observation of the current kernel status, never a caller flag.
 * No policy API transaction, boot-id proc read, or inherited FD is used. */
static int epoch_same(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
        a->st_mode == b->st_mode && a->st_uid == b->st_uid &&
        a->st_gid == b->st_gid && a->st_nlink == b->st_nlink &&
        a->st_size == b->st_size && a->st_rdev == b->st_rdev &&
        a->st_mtim.tv_sec == b->st_mtim.tv_sec &&
        a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec == b->st_ctim.tv_sec &&
        a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}

static int epoch_label(int fd, const char *expected)
{
    char value[128] = {0};
    ssize_t n = fgetxattr(fd, "security.selinux", value, sizeof(value));
    if (n < 0) return -1;
    size_t length = strlen(expected);
    return (n == (ssize_t)length || n == (ssize_t)length + 1) &&
        !memcmp(value, expected, length + 1) ? 0 : reject(EACCES);
}

static int epoch_open(int parent, const char *name, int directory)
{
    struct open_how how = {
        .flags = O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK |
            (directory ? O_DIRECTORY : 0),
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS,
    };
    return (int)syscall(SYS_openat2, parent, name, &how, sizeof(how));
}

static int epoch_directory(int fd, const char *context, int readonly, struct stat *st)
{
    struct statfs fs;
    struct statvfs flags;
    if (fstat(fd, st) < 0 || fstatfs(fd, &fs) < 0 ||
        fstatvfs(fd, &flags) < 0 || epoch_label(fd, context) < 0)
        return -1;
    const unsigned long required = ST_RDONLY | ST_NOSUID | ST_NODEV | ST_NOEXEC;
    if (!S_ISDIR(st->st_mode) || st->st_uid || st->st_gid ||
        (st->st_mode & 07777) != 0700 || (unsigned long)fs.f_type != TMPFS_MAGIC ||
        (readonly && (flags.f_flag & required) != required))
        return reject(EACCES);
    return 0;
}

static int publish_host_mount_identity(const struct host_mount_identity *held,
                                        int directory, const char *policy_digest)
{
    static const char name[] = "host-mount-identity.json";
    static const char context[] = "u:object_r:p4_linux_host_mount_identity_t:s0";
    struct stat actual, parent, named, written, after;
    struct statfs fs;
    if (!held || held->fd < 0 || directory < 0 || getpid() != 1 || geteuid() != 0)
        return reject(EINVAL);
    if (strlen(policy_digest) != 64 || strcmp(policy_digest, DROIDLOOM_BOARD_SELINUX_SHA256))
        return reject(EBADMSG);
    if (fstat(held->fd, &actual) < 0 || fstatfs(held->fd, &fs) < 0)
        return -1;
    if (!epoch_same(&held->identity, &actual) || (unsigned long)fs.f_type != NSFS_MAGIC)
        return reject(ESTALE);
    if (epoch_directory(directory, "u:object_r:p4_linux_early_handoff_dir_t:s0", 0, &parent) < 0 ||
        lstat("/run/droidloom-early", &named) < 0)
        return -1;
    if (!epoch_same(&parent, &named)) return reject(ESTALE);
    char body[512];
    int length = snprintf(body, sizeof(body),
        "{\"schema\":\"droidloom.host-mount-identity.v1\",\"boot_id\":\"%s\","
        "\"joint_policy_sha256\":\"%s\",\"device\":%llu,\"inode\":%llu}\n",
        held->boot_id, policy_digest, (unsigned long long)actual.st_dev,
        (unsigned long long)actual.st_ino);
    if (length <= 0 || (size_t)length >= sizeof(body)) return reject(EOVERFLOW);
    /* tmpfs uses fs_use_trans. This file must be created after first load;
     * the exact named transition supplies its actual SID. Never raw-set it. */
    int fd = openat(directory, name, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return -1;
    int error = 0;
    if (fstat(fd, &written) < 0 || fstatfs(fd, &fs) < 0 || epoch_label(fd, context) < 0)
        error = errno;
    else if (!S_ISREG(written.st_mode) || written.st_uid || written.st_gid ||
             written.st_nlink != 1 || written.st_size != 0 || written.st_dev != parent.st_dev ||
             (unsigned long)fs.f_type != TMPFS_MAGIC)
        error = EACCES;
    size_t pos = 0;
    while (!error && pos < (size_t)length) {
        ssize_t n = write(fd, body + pos, (size_t)length - pos);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) error = n < 0 ? errno : EIO;
        else pos += (size_t)n;
    }
    if (!error && (fchmod(fd, 0400) < 0 || fsync(fd) < 0 || fsync(directory) < 0)) error = errno;
    char readback[512];
    ssize_t received = -1;
    if (!error) {
        do { received = pread(fd, readback, sizeof(readback), 0); }
        while (received < 0 && errno == EINTR);
        if (received < 0) error = errno;
        else if (received != length || memcmp(readback, body, (size_t)length)) error = ESTALE;
    }
    if (!error && (fstat(fd, &after) < 0 ||
        fstatat(directory, name, &named, AT_SYMLINK_NOFOLLOW) < 0 || epoch_label(fd, context) < 0))
        error = errno;
    if (!error && (!epoch_same(&after, &named) || after.st_dev != written.st_dev ||
        after.st_ino != written.st_ino || after.st_mode != (S_IFREG | 0400) ||
        after.st_uid || after.st_gid || after.st_nlink != 1 || after.st_size != length)) error = ESTALE;
    if (!error && (fstat(directory, &after) < 0 || lstat("/run/droidloom-early", &named) < 0))
        error = errno;
    if (!error && (!epoch_same(&after, &named) || after.st_dev != parent.st_dev ||
        after.st_ino != parent.st_ino || after.st_mode != parent.st_mode ||
        after.st_uid != parent.st_uid || after.st_gid != parent.st_gid || after.st_nlink != parent.st_nlink))
        error = ESTALE;
    if (!error && fstat(held->fd, &after) < 0) error = errno;
    if (!error && !epoch_same(&held->identity, &after)) error = ESTALE;
    /* A failed, partially written observation is preserved for diagnosis;
     * the boot fails before native execution and no file is overwritten. */
    close(fd);
    return error ? reject(error) : 0;
}

static int epoch_status(int fd, uint32_t value[5])
{
    struct stat a, b;
    struct statfs fs;
    uint32_t next[5];
    if (fstat(fd, &a) < 0 || fstatfs(fd, &fs) < 0)
        return -1;
    /* Selected selinuxfs.c supplies this 0444 regular status page. Its
     * size is not a user file size; pread returns the kernel page bytes. */
    if (!S_ISREG(a.st_mode) || a.st_uid || a.st_gid ||
        (a.st_mode & 07777) != 0444 || (unsigned long)fs.f_type != SELINUXFS_MAGIC)
        return reject(EACCES);
    if (pread(fd, value, 5 * sizeof(uint32_t), 0) != 5 * sizeof(uint32_t) ||
        pread(fd, next, sizeof(next), 0) != sizeof(next))
        return reject(EIO);
    if (fstat(fd, &b) < 0)
        return -1;
    if (!epoch_same(&a, &b) || memcmp(value, next, sizeof(next)) ||
        value[0] != 1 || (value[1] & 1) || value[2] != 1 ||
        value[3] != 1 || value[4] != 1)
        return reject(ESTALE);
    return 0;
}

static int epoch_packet(const unsigned char *bytes, size_t length,
                        const uint32_t status[5])
{
    const char header[] = "DLAAREV3\n";
    if (status[0] != 1 || (status[1] & 1) || status[2] != 1 ||
        status[3] != 1 || status[4] != 1 ||
        length <= sizeof(header) || length >= 8192 ||
        memcmp(bytes, header, sizeof(header) - 1))
        return reject(EBADMSG);
    size_t start = 0, tail = 0, lines = 0;
    for (size_t n = 0; n < length; n++) {
        unsigned char c = bytes[n];
        if (c == '\n') {
            if (n == start) return reject(EBADMSG);
            tail = start;
            start = n + 1;
            lines++;
        } else if (c < 0x20 || c > 0x7e) {
            return reject(EBADMSG);
        }
    }
    if (start != length || lines != 6)
        return reject(EBADMSG);
    char expected[128];
    int n = snprintf(expected, sizeof(expected), "SELINUX1 %s %u 1 1\n",
        DROIDLOOM_BOARD_SELINUX_SHA256, status[1]);
    if (n < 0 || (size_t)n >= sizeof(expected) ||
        (size_t)n != length - tail || memcmp(bytes + tail, expected, (size_t)n))
        return reject(ESTALE);
    return 0;
}

int droidloom_board_verify_policy_epoch(void)
{
    int handoff = -1, directory = -1, receipt = -1, status = -1, error = 0;
    struct stat handoff_before, directory_before, file_before, current, named;
    uint32_t first[5], after[5];
    unsigned char bytes[8192];
    if (getpid() != 1 || geteuid() != 0)
        return reject(EPERM);
    handoff = epoch_open(AT_FDCWD, "/run/droidloom-early", 1);
    if (handoff < 0 || epoch_directory(handoff,
        "u:object_r:p4_linux_early_handoff_dir_t:s0", 0, &handoff_before) < 0)
        goto failed;
    directory = epoch_open(handoff, "kernel-policy", 1);
    if (directory < 0 || epoch_directory(directory,
        "u:object_r:p4_linux_policy_epoch_dir_t:s0", 1, &directory_before) < 0)
        goto failed;
    status = epoch_open(AT_FDCWD, SELINUX_DIR "/status", 0);
    if (status < 0 || epoch_status(status, first) < 0)
        goto failed;
    receipt = epoch_open(directory, "apparmor-epoch", 0);
    struct statfs fs;
    struct statvfs flags;
    if (receipt < 0 || fstat(receipt, &file_before) < 0 ||
        fstatfs(receipt, &fs) < 0 || fstatvfs(receipt, &flags) < 0 ||
        epoch_label(receipt, "u:object_r:p4_linux_apparmor_epoch_t:s0") < 0)
        goto failed;
    const unsigned long required = ST_RDONLY | ST_NOSUID | ST_NODEV | ST_NOEXEC;
    if (!S_ISREG(file_before.st_mode) || file_before.st_uid || file_before.st_gid ||
        (file_before.st_mode & 07777) != 0400 || file_before.st_nlink != 1 ||
        file_before.st_size < 128 || file_before.st_size >= (off_t)sizeof(bytes) ||
        (unsigned long)fs.f_type != TMPFS_MAGIC ||
        file_before.st_dev != directory_before.st_dev ||
        (flags.f_flag & required) != required) {
        errno = EACCES;
        goto failed;
    }
    size_t size = (size_t)file_before.st_size;
    ssize_t received;
    /* The sealed tmpfs packet is smaller than this fixed buffer. A short or
     * overlong read is rejected; no untrusted length reaches pread(2). */
    do { received = pread(receipt, bytes, sizeof(bytes), 0); }
    while (received < 0 && errno == EINTR);
    if (received < 0)
        goto failed;
    if ((size_t)received != size) { errno = EIO; goto failed; }
    unsigned char extra;
    if (pread(receipt, &extra, 1, (off_t)size) != 0) {
        errno = ESTALE;
        goto failed;
    }
    if (epoch_packet(bytes, size, first) < 0 || epoch_status(status, after) < 0)
        goto failed;
    if (memcmp(first, after, sizeof(first))) { errno = ESTALE; goto failed; }
    if (fstat(receipt, &current) < 0 ||
        fstatat(directory, "apparmor-epoch", &named, AT_SYMLINK_NOFOLLOW) < 0)
        goto failed;
    if (!epoch_same(&file_before, &current) || !epoch_same(&current, &named)) {
        errno = ESTALE; goto failed;
    }
    if (fstat(directory, &current) < 0 ||
        fstatat(handoff, "kernel-policy", &named, AT_SYMLINK_NOFOLLOW) < 0)
        goto failed;
    if (!epoch_same(&directory_before, &current) || !epoch_same(&current, &named)) {
        errno = ESTALE; goto failed;
    }
    if (fstat(handoff, &current) < 0 ||
        lstat("/run/droidloom-early", &named) < 0)
        goto failed;
    if (!epoch_same(&handoff_before, &current) || !epoch_same(&current, &named)) {
        errno = ESTALE; goto failed;
    }
    goto done;
failed:
    error = errno;
done:
    if (status >= 0) close(status);
    if (receipt >= 0) close(receipt);
    if (directory >= 0) close(directory);
    if (handoff >= 0) close(handoff);
    return error ? reject(error) : 0;
}
