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

int droidloom_board_activate_policy(gid_t observer_gid, const char *cohort)
{
    struct input policy = {DROIDLOOM_BOARD_SELINUX_SIZE, DROIDLOOM_BOARD_SELINUX_SHA256, POLICY_DIR "/joint.policy", NULL};
    struct input aa = {DROIDLOOM_BOARD_APPARMOR_SIZE, DROIDLOOM_BOARD_APPARMOR_SHA256, POLICY_DIR "/ubuntu-apparmor.profiles", NULL};
    struct droidloom_apparmor_measurement observation = {0};
    struct droidloom_raw_profile selected_profiles[4] = {0};
    int status = -1, epoch_directory = -1;
    struct droidloom_linux_init_scope scope = { .root.fd = -1, .scope.fd = -1, .procs.fd = -1, .controllers.fd = -1, .system_slice.fd = -1, .root_membership.fd = -1, .root_subtree_control.fd = -1 };
    struct droidloom_linux_run run = {.fd = -1}, shm = {.fd = -1}, mount_monitor = {.fd = -1};
    struct droidloom_linux_journal_store log_store = { .log.fd = -1, .journal.fd = -1 };
    struct droidloom_linux_credentials credentials = { .root.fd = -1, .systemd.fd = -1, .staging.fd = -1 };
    struct droidloom_linux_run udev = {.fd = -1}, udev_data = {.fd = -1};
    struct droidloom_readiness_paths paths = { .handoff.fd = -1, .readiness.fd = -1 };
    const char *stage = "read admitted SELinux input";
    int rc = read_admitted(&policy);
    if (rc == 0) { stage = "read admitted AppArmor input"; rc = read_admitted(&aa); }
    if (rc == 0) { stage = "validate AppArmor framing"; rc = apparmor_profiles(&aa, 0, selected_profiles); }
    if (rc == 0) { stage = "check initial Ubuntu policy state"; rc = initial_ubuntu_kernel(); }
    if (rc == 0) { stage = "prepare the original Ubuntu unified cgroup hierarchy"; rc = prepare_ubuntu_cgroup2(); }
    if (rc == 0) { stage = "hold the original Ubuntu cgroup root and move global PID 1 to its init.scope"; rc = droidloom_hold_linux_init_scope(&scope); }
    if (rc == 0) { stage = "prepare the original Ubuntu shared memory mount"; rc = droidloom_hold_linux_shm(&shm); }
    if (rc == 0) { stage = "hold original Ubuntu /run"; rc = droidloom_hold_linux_run(&run); }
    if (rc == 0) { stage = "hold the exact Ubuntu mount-monitor directory"; rc = droidloom_hold_linux_mount_monitor(&run, &mount_monitor); }
    if (rc == 0) { stage = "hold the Ubuntu runtime log directory"; rc = droidloom_hold_ubuntu_log(&run, &log_store); }
    if (rc == 0) { stage = "hold the distro credentials root"; rc = droidloom_hold_ubuntu_credentials(&run, &credentials); }
    if (rc == 0) { stage = "hold the root-owned Ubuntu udev directory on the original /run"; rc = droidloom_hold_linux_udev(&run, &udev); }
    if (rc == 0) { stage = "hold the original Ubuntu udev database directory"; rc = droidloom_hold_linux_udev_data(&udev, &udev_data); }
    if (rc == 0) { stage = "hold the selected early readiness directory"; rc = droidloom_hold_readiness_paths(&run, observer_gid, &paths); }
    /* Per-generation device sources are prepared only by the dedicated
     * launcher after this boot-wide policy epoch has been sealed. */
    (void)cohort;
    if (rc == 0) { stage = "project the exact Ubuntu console, null, full and kernel-log device nodes"; rc = droidloom_project_linux_standard_devices(); }
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
    if (rc == 0) { stage = "label the held Ubuntu runtime log directory"; rc = droidloom_label_ubuntu_log(&log_store); }
    if (rc == 0) { stage = "label the held distro credentials root"; rc = droidloom_label_ubuntu_credentials(&credentials); }
    if (rc == 0) { stage = "label the held Ubuntu udev directory"; rc = droidloom_label_linux_udev(&udev); }
    if (rc == 0) { stage = "label the original Ubuntu udev database directory"; rc = droidloom_label_linux_udev_data(&udev_data); }
    if (rc == 0) { stage = "label the held private readiness directory"; rc = droidloom_label_readiness_paths(&paths); }
    if (rc == 0) { stage = "seal the original kernel policy load epoch"; rc = droidloom_publish_apparmor_epoch(epoch_directory, status, policy.digest, &observation); }
    int error = errno;
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
