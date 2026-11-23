// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "board_policy.h"
#include "apparmor_epoch.h"
#include "linux_run_label.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
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
    if (getpid() != 1 || geteuid() != 0 || strcmp(kernel.release, "6.18.64-p4ctx6181-fusectl-r1") ||
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

/* The pinned distribution archive contains 165 Ubuntu entries and three board roles. */
#define APPARMOR_PROFILE_ENTRIES 168U

static int apparmor_profiles(const struct input *pack, int activate)
{
    if (pack->size < 12 || memcmp(pack->data, "DLAA0001", 8) || le32(pack->data + 8) != APPARMOR_PROFILE_ENTRIES)
        return reject(EBADMSG);
    size_t pos = 12;
    for (unsigned int i = 0; i != APPARMOR_PROFILE_ENTRIES; ++i) {
        if (pack->size - pos < 4)
            return reject(EBADMSG);
        size_t length = le32(pack->data + pos);
        pos += 4;
        if (!length || length > pack->size - pos)
            return reject(EBADMSG);
        if (activate && submit(AA_DIR "/.load", pack->data + pos, length) < 0)
            return -1;
        pos += length;
    }
    return pos == pack->size ? 0 : reject(EBADMSG);
}

int droidloom_board_activate_policy(gid_t observer_gid)
{
    struct input policy = {885180, "72fa254db667e02b38bdbad11f4b50d89a5c96bafe24d48c7eac771186623b6e", POLICY_DIR "/joint.policy", NULL};
    struct input aa = {5757064, "d8696c387207aeaac791c47dc8740ad0ff1434758b3ca05b5b16ac6c61e19954", POLICY_DIR "/ubuntu-apparmor.profiles", NULL};
    struct droidloom_apparmor_measurement observation = {0};
    int status = -1, epoch_directory = -1;
    struct droidloom_linux_run run = {.fd = -1};
    struct droidloom_readiness_paths paths = { .handoff.fd = -1, .readiness.fd = -1 };
    const char *stage = "read admitted SELinux input";
    int rc = read_admitted(&policy);
    if (rc == 0) { stage = "read admitted AppArmor input"; rc = read_admitted(&aa); }
    if (rc == 0) { stage = "validate AppArmor framing"; rc = apparmor_profiles(&aa, 0); }
    if (rc == 0) { stage = "check initial Ubuntu policy state"; rc = initial_ubuntu_kernel(); }
    if (rc == 0) { stage = "prepare the original Ubuntu unified cgroup hierarchy"; rc = prepare_ubuntu_cgroup2(); }
    if (rc == 0) { stage = "hold original Ubuntu /run"; rc = droidloom_hold_linux_run(&run); }
    if (rc == 0) { stage = "hold the selected early readiness directory"; rc = droidloom_hold_readiness_paths(&run, observer_gid, &paths); }
    if (rc == 0) { stage = "project the exact Ubuntu console, null and full device nodes"; rc = droidloom_project_linux_standard_devices(); }
    if (rc == 0) {
        stage = "prepare the protected read-only kernel measurement directory";
        epoch_directory = droidloom_prepare_epoch_directory(paths.handoff.fd);
        if (epoch_directory < 0) rc = -1;
    }
    if (rc == 0) { stage = "load the selected Ubuntu AppArmor profiles"; rc = apparmor_profiles(&aa, 1); }
    if (rc == 0) {
        stage = "capture original AppArmor namespace and loaded profile identities";
        rc = droidloom_capture_apparmor_epoch(&observation);
    }
    if (rc == 0) {
        stage = "hold the real SELinux status page before its first policy load";
        status = droidloom_open_initial_selinux_status();
        if (status < 0) rc = -1;
    }
    if (rc == 0) { stage = "load initial selected joint SELinux policy"; rc = submit(SELINUX_DIR "/load", policy.data, policy.size); }
    if (rc == 0) { stage = "label the held Ubuntu /run inode"; rc = droidloom_label_linux_run(&run); }
    if (rc == 0) { stage = "label the held private readiness directory"; rc = droidloom_label_readiness_paths(&paths); }
    if (rc == 0) { stage = "seal the original kernel policy load epoch"; rc = droidloom_publish_apparmor_epoch(epoch_directory, status, policy.digest, &observation); }
    int error = errno;
    if (status >= 0) close(status);
    if (epoch_directory >= 0) close(epoch_directory);
    if (rc < 0)
        fprintf(stderr, "Droidloom early policy failed to %s: %s\n", stage, strerror(error));
    if (paths.readiness.fd >= 0)
        close(paths.readiness.fd);
    if (paths.handoff.fd >= 0)
        close(paths.handoff.fd);
    if (run.fd >= 0)
        close(run.fd);
    free(aa.data);
    free(policy.data);
    return rc == 0 ? 0 : reject(error);
}
