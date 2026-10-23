// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/xattr.h>
#include <unistd.h>

static int failures, cases;
static void check(const char *name, int ok, long actual, int err)
{
    ++cases;
    if (!ok) ++failures;
    printf("RO_CASE name=%s pass=%d actual=%ld errno=%d\n", name, !!ok, actual, err);
    fflush(stdout);
}
#define OK(name, expr) do { \
    errno = 0; \
    long r = (expr); \
    int e = errno; \
    check(name, r >= 0, r, e); \
} while (0)
#define ERR(name, expr, expected) do { \
    errno = 0; \
    long r = (expr); \
    int e = errno; \
    check(name, r == -1 && e == (expected), r, e); \
} while (0)
#define OPEN_ERR(name, expr, expected) do { \
    errno = 0; \
    int r = (expr); \
    int e = errno; \
    check(name, r == -1 && e == (expected), r, e); \
    if (r >= 0) close(r); \
} while (0)
static void setup(int ok, const char *name)
{
    if (!ok) { perror(name); printf("RO_SETUP_FAILED %s\n", name); exit(2); }
}
static void content_unchanged(int fd, const char *name)
{
    char data[8] = {0};
    struct stat st;
    int ok = pread(fd, data, sizeof(data), 0) == sizeof(data) &&
             memcmp(data, "RO-SEED!", sizeof(data)) == 0 &&
             fstat(fd, &st) == 0 && st.st_size == 4096;
    check(name, ok, ok, errno);
}
static void mappings(int fd, const char *prefix)
{
    char name[96];
    const int modes[] = {MAP_SHARED, MAP_SHARED_VALIDATE};
    for (unsigned i = 0; i < sizeof(modes) / sizeof(modes[0]); ++i) {
        errno = 0;
        void *p = mmap(NULL, 4096, PROT_READ | PROT_WRITE, modes[i], fd, 0);
        int e = errno;
        snprintf(name, sizeof(name), "%s_shared_%u_write", prefix, i);
        check(name, p == MAP_FAILED && e == EACCES, (long)p, e);
        if (p != MAP_FAILED) munmap(p, 4096);
        errno = 0;
        p = mmap(NULL, 4096, PROT_READ, modes[i], fd, 0);
        e = errno;
        snprintf(name, sizeof(name), "%s_shared_%u_read", prefix, i);
        check(name, p != MAP_FAILED, (long)p, e);
        if (p != MAP_FAILED) {
            snprintf(name, sizeof(name), "%s_shared_%u_mprotect", prefix, i);
            ERR(name, mprotect(p, 4096, PROT_READ | PROT_WRITE), EACCES);
            munmap(p, 4096);
        }
    }
    errno = 0;
    char *p = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE, fd, 0);
    int e = errno;
    snprintf(name, sizeof(name), "%s_private_write", prefix);
    check(name, p != MAP_FAILED, (long)p, e);
    if (p != MAP_FAILED) {
        struct stat st;
        int sized = fstat(fd, &st) == 0 && st.st_size >= 4096;
        if (sized) p[0] = 'C';
        snprintf(name, sizeof(name), "%s_private_cow", prefix);
        check(name, sized, sized, errno);
        munmap(p, 4096);
    }
}
/* A separate negative reproducer keeps the unsupported live-remount boundary
   visible. It is never counted as a passing readonly qualification. */
static int retained_mapping_reproducer(void)
{
    setup(mkdir("/rw", 0755) == 0, "mkdir lifetime rw");
    setup(mount("tmpfs", "/rw", "tmpfs", 0, NULL) == 0, "mount lifetime rw");
    int fd = open("/rw/seed", O_CREAT | O_RDWR, 0600);
    setup(fd >= 0 && ftruncate(fd, 4096) == 0, "prepare lifetime seed");
    char *p = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    setup(p != MAP_FAILED, "map lifetime seed");
    errno = 0;
    int r = mount(NULL, "/rw", NULL, MS_REMOUNT | MS_BIND | MS_RDONLY, NULL);
    int e = errno;
    if (r == -1) {
        check("remount_retained_mapping_safe", e == EBUSY, r, e);
    } else {
        p[0] = 'X';
        char actual = 0;
        setup(pread(fd, &actual, 1, 0) == 1, "read retained mapping store");
        check("remount_retained_mapping_safe", actual == 0, actual, 0);
    }
    munmap(p, 4096);
    close(fd);
    printf("RO_COMPLETE cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    /* Never run destructive setup on the host: only our runner's marked guest. */
    if (argc != 2 || access("/.hepta-disposable-guest", F_OK) != 0) return 64;
    if (strcmp(argv[1], "--disposable-guest-retained-map") == 0)
        return retained_mapping_reproducer();
    if (strcmp(argv[1], "--disposable-guest") != 0) return 64;
    setup(mkdir("/ro", 0755) == 0, "mkdir ro");
    setup(mkdir("/rw", 0755) == 0, "mkdir rw");
    setup(mkdir("/alias", 0755) == 0, "mkdir alias");
    setup(mount("/dev/vda", "/ro", "ext2", MS_RDONLY, NULL) == 0, "mount ext2 ro");
    int rd = open("/ro/seed", O_RDONLY);
    setup(rd >= 0, "open ro seed");
    OPEN_ERR("open_ro_wronly", open("/ro/seed", O_WRONLY), EROFS);
    OPEN_ERR("open_ro_rdwr", open("/ro/seed", O_RDWR), EROFS);
    OPEN_ERR("open_ro_trunc_write", open("/ro/seed", O_WRONLY | O_TRUNC), EROFS);
    OPEN_ERR("open_ro_trunc_read", open("/ro/seed", O_RDONLY | O_TRUNC), EROFS);
    OPEN_ERR("open_ro_create", open("/ro/new", O_CREAT | O_WRONLY, 0600), EROFS);
    ERR("ro_utimensat", utimensat(AT_FDCWD, "/ro/seed", NULL, 0), EROFS);
    ERR("ro_futimens", futimens(rd, NULL), EROFS);
    const struct timespec omit[2] = {{0, UTIME_OMIT}, {0, UTIME_OMIT}};
    OK("ro_utimens_omit", utimensat(AT_FDCWD, "/ro/seed", omit, 0));
    ERR("ro_path_truncate", truncate("/ro/seed", 0), EROFS);
    ERR("ro_setxattr", setxattr("/ro/seed", "user.probe", "x", 1, 0), EROFS);
    ERR("ro_removexattr", removexattr("/ro/seed", "user.absent"), EROFS);
    ERR("readonly_fd_write", write(rd, "x", 1), EBADF);
    ERR("readonly_fd_pwrite", pwrite(rd, "x", 1, 0), EBADF);
    ERR("readonly_fd_ftruncate", ftruncate(rd, 0), EINVAL);
    int path = open("/ro/seed", O_PATH | O_RDWR | O_TRUNC);
    check("open_ro_opath", path >= 0, path, errno);
    if (path >= 0) close(path);
    mappings(rd, "initial_ro");
    content_unchanged(rd, "initial_ro_content_unchanged");
    close(rd);
    setup(mount("/ro", "/alias", NULL, MS_BIND, NULL) == 0, "bind readonly superblock");
    setup(mount(NULL, "/alias", NULL, MS_REMOUNT | MS_BIND, NULL) == 0,
          "clear alias readonly mount flag");
    OPEN_ERR("open_readonly_superblock_alias", open("/alias/seed", O_RDWR), EROFS);
    ERR("readonly_superblock_alias_truncate", truncate("/alias/seed", 0), EROFS);
    setup(umount("/alias") == 0, "unmount readonly alias");

    setup(mount("tmpfs", "/rw", "tmpfs", 0, NULL) == 0, "mount tmpfs rw");
    int fd = open("/rw/seed", O_CREAT | O_RDWR, 0666);
    setup(fd >= 0, "open rw seed");
    OK("rw_write", write(fd, "RO-SEED!", 8));
    OK("rw_pwrite", pwrite(fd, "!", 1, 7));
    OK("rw_ftruncate", ftruncate(fd, 4096));
    OK("rw_futimens", futimens(fd, NULL));
    OK("rw_truncate", truncate("/rw/seed", 4096));
    setup(fchown(fd, 1000, 1000) == 0 && fchmod(fd, 0444) == 0, "prepare chmod fd");
    pid_t child = fork();
    setup(child >= 0, "fork chmod test");
    if (child == 0) {
        if (setuid(1000) != 0) _exit(3);
        if (pwrite(fd, "!", 1, 7) != 1 || ftruncate(fd, 4096) != 0) _exit(4);
        errno = 0;
        if (truncate("/rw/seed", 0) != -1 || errno != EACCES) _exit(5);
        _exit(0);
    }
    int status;
    setup(waitpid(child, &status, 0) == child, "wait chmod test");
    check("fd_survives_chmod_nonroot", WIFEXITED(status) && WEXITSTATUS(status) == 0, status, 0);
    close(fd);
    rd = open("/rw/seed", O_RDONLY);
    setup(rd >= 0, "open readonly fd on writable mount");
    mappings(rd, "rw_readonly_fd");
    content_unchanged(rd, "rw_readonly_fd_content_unchanged");
    close(rd);
    setup(chmod("/rw/seed", 0666) == 0, "restore mode");
    int wr = open("/rw/seed", O_WRONLY);
    setup(wr >= 0, "open writeonly fd");
    const int writeonly_modes[] = {MAP_PRIVATE, MAP_SHARED, MAP_SHARED_VALIDATE};
    for (unsigned i = 0; i < sizeof(writeonly_modes) / sizeof(writeonly_modes[0]); ++i) {
        char name[80];
        errno = 0;
        void *p = mmap(NULL, 4096, PROT_NONE, writeonly_modes[i], wr, 0);
        int e = errno;
        snprintf(name, sizeof(name), "writeonly_fd_none_%u", i);
        check(name, p == MAP_FAILED && e == EACCES, (long)p, e);
        if (p != MAP_FAILED) munmap(p, 4096);
    }
    close(wr);
    setup(mknod("/rw/null", S_IFCHR | 0666, makedev(1, 3)) == 0, "mknod null");
    setup(mkfifo("/rw/fifo", 0666) == 0, "mkfifo");
    setup(mount("/rw", "/alias", NULL, MS_BIND, NULL) == 0, "bind alias");
    fd = open("/alias/seed", O_RDWR);
    setup(fd >= 0, "open alias before ro");
    /* Existing implementation allows this transition. This verifies subsequent
       syscall gates; it does not certify concurrent remount or retained mappings. */
    setup(mount(NULL, "/alias", NULL, MS_REMOUNT | MS_BIND | MS_RDONLY, NULL) == 0,
          "bind remount ro");
    ERR("remount_fd_futimens", futimens(fd, NULL), EROFS);
    ERR("remount_fd_write", write(fd, "x", 1), EROFS);
    ERR("remount_fd_pwrite", pwrite(fd, "x", 1, 0), EROFS);
    ERR("remount_fd_ftruncate", ftruncate(fd, 0), EROFS);
    ERR("remount_fd_fallocate", fallocate(fd, 0, 0, 8192), EROFS);
    OPEN_ERR("open_alias_wronly", open("/alias/seed", O_WRONLY), EROFS);
    ERR("remount_path_truncate", truncate("/alias/seed", 0), EROFS);
    ERR("remount_setxattr", fsetxattr(fd, "user.probe", "x", 1, 0), EROFS);
    ERR("remount_removexattr", fremovexattr(fd, "user.absent"), EROFS);
    mappings(fd, "remount_ro");
    content_unchanged(fd, "remount_ro_content_unchanged");
    close(fd);
    int special = open("/alias/null", O_WRONLY);
    check("ro_device_open", special >= 0, special, errno);
    if (special >= 0) { OK("ro_device_write", write(special, "x", 1)); close(special); }
    special = open("/alias/fifo", O_RDWR | O_NONBLOCK);
    check("ro_fifo_open", special >= 0, special, errno);
    if (special >= 0) { OK("ro_fifo_write", write(special, "x", 1)); close(special); }
    fd = open("/rw/seed", O_RDWR);
    check("rw_alias_open", fd >= 0, fd, errno);
    if (fd >= 0) { OK("rw_alias_write", pwrite(fd, "!", 1, 7)); close(fd); }
    printf("RO_COMPLETE cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
