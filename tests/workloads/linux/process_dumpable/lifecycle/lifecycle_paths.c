#include "lifecycle_probe.h"

static volatile unsigned public_sentinel = 0x5a17c0deU;
struct report { pid_t pid; int dumpable, target_fd; uintptr_t address; };

int actor(int input, int output, int after_exec) {
    alarm(12);
    int target = open("/dev/null", O_RDONLY);
    if (target < 0) return 99;
    if (!after_exec && prctl(PR_SET_DUMPABLE, 0L)) return 99;
    for (;;) {
        struct report r = {getpid(), prctl(PR_GET_DUMPABLE), target, (uintptr_t)&public_sentinel};
        exact(output, &r, sizeof(r), 1);
        char command;
        exact(input, &command, 1, 0);
        if (command == 'Q') return 0;
        if (command == 'E') {
            char in[24], out[24];
            snprintf(in, sizeof(in), "%d", input);
            snprintf(out, sizeof(out), "%d", output);
            char *args[] = {"dumpable-lifecycle", "--owned-exec", in, out, NULL};
            char *env[] = {"DUMPABLE_PROBE=public_after_exec", "LANG=C", NULL};
            execve("/proc/self/exe", args, env);
            return 99;
        }
        if (prctl(PR_SET_DUMPABLE, command == '1' ? 1L : 0L)) return 99;
    }
}
static int path_open(pid_t child, const char *name) {
    char path[128];
    snprintf(path, sizeof(path), "/proc/%d/%s", child, name);
    return open(path, O_RDONLY | O_CLOEXEC);
}
static void operation(const char *stage, const char *name, long rc, int error, int denied) {
    int okay = denied ? rc < 0 && (error == EPERM || error == EACCES) : rc > 0;
    printf("{\"stage\":\"%s\",\"operation\":\"%s\",\"rc\":%ld,\"errno\":%d,\"denied_expected\":%s,\"passed\":%s,\"own_child\":true}\n",
           stage, name, rc, error, denied ? "true" : "false", okay ? "true" : "false");
    if (!okay) failures++;
}
static void read_path(const char *stage, const char *name, const struct report *r, int denied) {
    errno = 0;
    int fd = path_open(r->pid, name), error = errno;
    if (fd < 0) { operation(stage, name, -1, error, denied); return; }
    unsigned data = 0;
    errno = 0;
    ssize_t n = !strcmp(name, "mem") ? pread(fd, &data, sizeof(data), (off_t)r->address) : read(fd, &data, 1);
    error = errno;
    close(fd);
    operation(stage, name, n, error, denied);
    if (!strcmp(name, "mem") && n == (ssize_t)sizeof(data))
        check("public_mem_sentinel_only", data, public_sentinel);
}
static void link_path(const char *stage, const char *name, const struct report *r, int denied) {
    char path[128], data[512];
    snprintf(path, sizeof(path), "/proc/%d/%s", r->pid, name);
    errno = 0;
    ssize_t n = readlink(path, data, sizeof(data));
    int error = errno;
    operation(stage, name, n, error, denied);
}
static void paths(const char *stage, const struct report *r, int expected, int pidfd) {
    check(stage, r->dumpable, expected);
    int denied = expected == 0;
    read_path(stage, "maps", r, denied);
    read_path(stage, "mem", r, denied);
    read_path(stage, "environ", r, denied);
    read_path(stage, "auxv", r, denied);
    char fdname[48];
    snprintf(fdname, sizeof(fdname), "fd/%d", r->target_fd);
    link_path(stage, fdname, r, denied);
    link_path(stage, "exe", r, denied);
    link_path(stage, "ns/mnt", r, denied);
    errno = 0;
    int copied = (int)syscall(SYS_pidfd_getfd, pidfd, r->target_fd, 0);
    int error = errno;
    /* A copied descriptor may be zero; use 1 to report successful positive access. */
    operation(stage, "pidfd_getfd_dev_null", copied < 0 ? -1 : 1, error, denied);
    if (copied >= 0) {
        struct stat st;
        require(!fstat(copied, &st) && S_ISCHR(st.st_mode), "copied_own_dev_null_only");
        close(copied);
    }
}
static void old_image_paths(const int old[4], const unsigned char *before, ssize_t before_len,
                            const struct report *r) {
    const char *names[] = {"maps", "mem", "environ", "auxv"};
    unsigned char data[4096];
    for (unsigned i = 0; i < 4; i++) {
        require(lseek(old[i], 0, SEEK_SET) == 0, "old_proc_fd_rewind");
        ssize_t n = i == 1 ? pread(old[i], data, sizeof(unsigned), (off_t)r->address)
                           : read(old[i], data, sizeof(data));
        if (i == 3) {
            /* Linux pins old saved_auxv; Asterinas deliberately returns empty
             * for an obsolete image. Neither may expose the new image. */
            require(n == 0 || (n == before_len && !memcmp(data, before, (size_t)n)),
                    "old_auxv_is_empty_or_identical_old_snapshot");
        } else {
            check(i == 0 ? "old_maps_after_exec_empty" : i == 1 ? "old_mem_after_exec_empty" : "old_environ_after_exec_empty", n, 0);
        }
        printf("{\"operation\":\"old_%s_after_exec\",\"read_bytes\":%zd}\n", names[i], n);
        close(old[i]);
    }
}
void sensitive_paths(void) {
    int command[2], reply[2];
    if (pipe(command) || pipe(reply)) _exit(99);
    pid_t child = fork();
    if (child < 0) _exit(99);
    if (child == 0) {
        close(command[1]); close(reply[0]);
        _exit(actor(command[0], reply[1], 0));
    }
    close(command[0]); close(reply[1]);
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0);
    require(pidfd >= 0, "owned_child_pidfd_open");
    struct report r;
    exact(reply[0], &r, sizeof(r), 0);
    require(r.pid == child, "retained_child_identity");
    paths("cross_child_set0", &r, 0, pidfd);
    char c = '1';
    exact(command[1], &c, 1, 1); exact(reply[0], &r, sizeof(r), 0);
    paths("cross_child_set1", &r, 1, pidfd);
    c = '0';
    exact(command[1], &c, 1, 1); exact(reply[0], &r, sizeof(r), 0);
    paths("cross_child_set0_again", &r, 0, pidfd);
    c = '1';
    exact(command[1], &c, 1, 1); exact(reply[0], &r, sizeof(r), 0);
    const char *names[] = {"maps", "mem", "environ", "auxv"};
    int old[4];
    for (unsigned i = 0; i < 4; i++) {
        old[i] = path_open(child, names[i]);
        require(old[i] >= 0, "old_image_fd_open_at_dump1");
    }
    unsigned char auxv_before[4096];
    ssize_t auxv_length = read(old[3], auxv_before, sizeof(auxv_before));
    require(auxv_length > 0, "old_public_auxv_snapshot_exists");
    c = 'E';
    exact(command[1], &c, 1, 1); exact(reply[0], &r, sizeof(r), 0);
    require(r.pid == child, "exec_preserves_owned_pid");
    paths("ordinary_exec_resets_one", &r, 1, pidfd);
    old_image_paths(old, auxv_before, auxv_length, &r);
    c = 'Q';
    exact(command[1], &c, 1, 1);
    reap(child, "sensitive_child_reaped");
    close(command[1]); close(reply[0]);
    if (pidfd >= 0) close(pidfd);
}
