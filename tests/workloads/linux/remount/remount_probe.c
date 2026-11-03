// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static int cases, failures;
static void setup(int ok, const char *name) {
    if (!ok) { perror(name); printf("RM_SETUP_FAILED %s\n", name); exit(2); }
}
static void check(const char *name, int ok, long actual, int err) {
    ++cases; if (!ok) ++failures;
    printf("RM_CASE name=%s pass=%d actual=%ld errno=%d\n", name, !!ok, actual, err);
}
static char *mountinfo(void) {
    char *text = calloc(1, 65536);
    setup(text != NULL, "allocate mountinfo");
    int fd = open("/proc/self/mountinfo", O_RDONLY);
    setup(fd >= 0, "mountinfo open");
    size_t len = 0;
    for (;;) {
        ssize_t n = read(fd, text + len, 65535 - len);
        setup(n >= 0, "mountinfo read");
        if (!n) break;
        len += n;
        setup(len < 65535, "mountinfo bounded");
    }
    close(fd); return text;
}
static uint64_t disk_hash(int fd) {
    uint64_t hash = UINT64_C(14695981039346656037);
    unsigned char data[65536];
    for (off_t off = 0; off < 32 * 1024 * 1024; off += sizeof(data)) {
        setup(pread(fd, data, sizeof(data), off) == sizeof(data), "raw guest disk read");
        for (unsigned i = 0; i < sizeof(data); ++i) hash = (hash ^ data[i]) * UINT64_C(1099511628211);
    }
    return hash;
}
static void attempt(const char *prefix, const char *path, unsigned long flags,
                    int fd, int disk, char *writable, char *may_write) {
    char name[100];
    char *before = mountinfo();
    uint64_t before_disk = disk >= 0 ? disk_hash(disk) : 0;
    char bytes[2] = {writable[0], writable[1]};
    errno = 0;
    int result = mount(NULL, path, NULL, flags, NULL);
    int err = errno;
    snprintf(name, sizeof(name), "%s_rejected", prefix);
    check(name, result == -1 && err == EOPNOTSUPP, result, err);
    char *after = mountinfo();
    snprintf(name, sizeof(name), "%s_all_flags_unchanged", prefix);
    check(name, strcmp(before, after) == 0, strcmp(before, after), 0);
    free(before); free(after);
    if (disk >= 0) {
        uint64_t after_disk = disk_hash(disk);
        snprintf(name, sizeof(name), "%s_dirty_disk_unchanged", prefix);
        check(name, before_disk == after_disk, before_disk == after_disk, 0);
    }
    snprintf(name, sizeof(name), "%s_mapped_bytes_unchanged", prefix);
    check(name, writable[0] == bytes[0] && writable[1] == bytes[1], writable[0], 0);
    snprintf(name, sizeof(name), "%s_original_write_policy", prefix);
    errno = 0; ssize_t n = pwrite(fd, "F", 1, 2); err = errno;
    check(name, n == 1, n, err);
    snprintf(name, sizeof(name), "%s_original_maywrite_policy", prefix);
    errno = 0; result = mprotect(may_write, 4096, PROT_READ | PROT_WRITE); err = errno;
    if (!result) may_write[1] = 'M';
    check(name, result == 0 && writable[1] == 'M', result, err);
    if (!result) setup(mprotect(may_write, 4096, PROT_READ) == 0, "restore read mapping");
}
static void suite(const char *root, const char *alias, const char *type, const char *device) {
    setup(mkdir(root, 0755) == 0 && mkdir(alias, 0755) == 0, "directories");
    setup(mount(device, root, type, 0, NULL) == 0, "mount rw");
    char path[100]; snprintf(path, sizeof(path), "%s/retained", root);
    int fd = open(path, O_CREAT | O_EXCL | O_RDWR, 0666);
    setup(fd >= 0 && ftruncate(fd, 4096) == 0, "file creation");
    setup(mount(root, alias, NULL, MS_BIND, NULL) == 0, "bind alias");
    char *rw = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    char *may = mmap(NULL, 4096, PROT_READ, MAP_SHARED_VALIDATE, fd, 0);
    setup(rw != MAP_FAILED && may != MAP_FAILED, "retained mappings");
    int disk = strcmp(type, "ext2") == 0 ? open("/dev/vda", O_RDONLY) : -1;
    setup(strcmp(type, "ext2") != 0 || disk >= 0, "raw guest disk descriptor");
    sync();
    rw[0] = 'D'; /* Dirty shared page intentionally retained across each rejected call. */
    char name[100];
    snprintf(name, sizeof(name), "%s_bind", type);
    attempt(name, root, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOEXEC, fd, disk, rw, may);
    snprintf(name, sizeof(name), "%s_superblock", type);
    attempt(name, root, MS_REMOUNT | MS_RDONLY | MS_NOSUID, fd, disk, rw, may);
    snprintf(name, sizeof(name), "%s_alias", type);
    attempt(name, alias, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NODEV, fd, disk, rw, may);
    snprintf(name, sizeof(name), "%s_same_readonly_state_remount", type);
    errno = 0;
    int same = mount(NULL, root, NULL, MS_REMOUNT | MS_BIND | MS_NOEXEC, NULL);
    int same_errno = errno;
    check(name, same == 0, same, same_errno);
    pid_t child = fork(); setup(child >= 0, "fork namespace");
    if (!child) {
        if (unshare(CLONE_NEWNS) != 0) _exit(2);
        char *before = mountinfo();
        errno = 0;
        int r = mount(NULL, alias, NULL, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOEXEC, NULL);
        if (r != -1 || errno != EOPNOTSUPP) _exit(3);
        char *after = mountinfo();
        if (strcmp(before, after)) _exit(4);
        if (mprotect(may, 4096, PROT_READ | PROT_WRITE) != 0) _exit(5);
        may[3] = 'N';
        _exit(rw[3] == 'N' ? 0 : 6);
    }
    int status; setup(waitpid(child, &status, 0) == child, "wait namespace");
    snprintf(name, sizeof(name), "%s_fork_namespace_retained_mapping", type);
    check(name, WIFEXITED(status) && WEXITSTATUS(status) == 0, status, 0);
    munmap(rw, 4096); munmap(may, 4096); close(fd);
    if (disk >= 0) close(disk);
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 2 || strcmp(argv[1], "--disposable-guest") || access("/.hepta-disposable-guest", F_OK)) return 64;
    suite("/rm-ram", "/rm-ram-alias", "tmpfs", "tmpfs");
    suite("/rm-ext", "/rm-ext-alias", "ext2", "/dev/vda");
    printf("RM_COMPLETE cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
