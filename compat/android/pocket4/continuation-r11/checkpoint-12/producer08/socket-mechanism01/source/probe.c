#define _GNU_SOURCE
/* Owned kernel mechanism control only. No Android, pressure, network namespace,
 * production socket, or installed file is accessed. Every mount is made after
 * creating a private mount namespace. The original socket is an owned fixture. */
#include <errno.h>
#include <fcntl.h>
#include <linux/mount.h>
#include <linux/stat.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define FIXTURE_ROOT "/opt/p4-init-socket-projection-mechanism-20261105-01/mountpoint"
#define FIXTURE_NONCE "4fae685087dcfee61ceac314fcbd617f"
#define MAGIC UINT64_C(0x50344d4f554e5431)
#define FIXTURE_UID 1069
#define FIXTURE_GID 1069

struct file_identity { uint64_t device, inode; uint32_t uid, gid, mode; };
struct operation { int rc, error; };
struct evidence {
    uint64_t magic;
    char nonce[33];
    struct operation raw_foreign_bind, local_reopen_bind, detached_move;
    struct file_identity raw_source, local_source, detached_source;
    struct file_identity local_target, moved_target;
    struct file_identity parent_namespace, child_namespace;
    struct file_identity parent_user_namespace, child_user_namespace;
    uint64_t raw_mount_id, local_mount_id, detached_mount_id, moved_mount_id;
    int rights_count, inherited_source_fds_closed, all_received_fds_closed;
    int child_stage, child_error, child_success;
};

static void close_fd(int *fd) { if (*fd >= 0) { close(*fd); *fd = -1; } }
static int identity(int fd, struct file_identity *out) {
    struct stat st;
    if (fstat(fd, &st)) return -1;
    *out = (struct file_identity){st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode};
    return 0;
}
static int equal_identity(const struct file_identity *a, const struct file_identity *b) {
    return a->device == b->device && a->inode == b->inode && a->uid == b->uid &&
           a->gid == b->gid && a->mode == b->mode;
}
static int socket_identity(const struct file_identity *s) {
    return S_ISSOCK(s->mode) && s->uid == FIXTURE_UID && s->gid == FIXTURE_GID &&
           (s->mode & 07777) == 0600;
}
static int mount_id(int fd, uint64_t *out) {
    struct statx st;
    memset(&st, 0, sizeof(st));
    if (syscall(SYS_statx, fd, "", AT_EMPTY_PATH | AT_STATX_DONT_SYNC, STATX_MNT_ID, &st)) return -1;
    if (!(st.stx_mask & STATX_MNT_ID) || !st.stx_mnt_id) { errno = EPROTO; return -1; }
    *out = st.stx_mnt_id;
    return 0;
}
static int namespace_identity(struct file_identity *out) {
    int fd = open("/proc/self/ns/mnt", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    int rc = identity(fd, out), saved = errno;
    close(fd); errno = saved; return rc;
}
static int user_namespace_identity(struct file_identity *out) {
    int fd = open("/proc/self/ns/user", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    int rc = identity(fd, out), saved = errno;
    close(fd); errno = saved; return rc;
}
static int wait_readable(int fd, int milliseconds) {
    struct pollfd p = {fd, POLLIN, 0};
    int rc;
    do { rc = poll(&p, 1, milliseconds); } while (rc < 0 && errno == EINTR);
    if (rc != 1 || !(p.revents & POLLIN) || p.revents & (POLLERR | POLLNVAL)) {
        if (rc >= 0) errno = ETIMEDOUT;
        return -1;
    }
    return 0;
}
static int send_rights(int channel, const int fds[2]) {
    uint64_t magic = MAGIC;
    struct iovec iov = {&magic, sizeof(magic)};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } control;
    memset(&control, 0, sizeof(control));
    struct msghdr msg;
    memset(&msg, 0, sizeof(msg));
    msg.msg_iov = &iov; msg.msg_iovlen = 1;
    msg.msg_control = control.bytes; msg.msg_controllen = sizeof(control.bytes);
    struct cmsghdr *c = CMSG_FIRSTHDR(&msg);
    c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(2 * sizeof(int));
    memcpy(CMSG_DATA(c), fds, 2 * sizeof(int));
    return sendmsg(channel, &msg, MSG_NOSIGNAL) == (ssize_t)sizeof(magic) ? 0 : -1;
}
static int receive_rights(int channel, int fds[2], int *count) {
    uint64_t magic = 0;
    struct iovec iov = {&magic, sizeof(magic)};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(8 * sizeof(int))]; } control;
    memset(&control, 0, sizeof(control));
    struct msghdr msg;
    memset(&msg, 0, sizeof(msg));
    msg.msg_iov = &iov; msg.msg_iovlen = 1;
    msg.msg_control = control.bytes; msg.msg_controllen = sizeof(control.bytes);
    if (wait_readable(channel, 5000)) return -1;
    ssize_t n = recvmsg(channel, &msg, MSG_CMSG_CLOEXEC | MSG_DONTWAIT);
    int total = 0, bad = n != (ssize_t)sizeof(magic) || magic != MAGIC ||
                         (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC));
    for (struct cmsghdr *c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c)) {
        if (c->cmsg_level != SOL_SOCKET || c->cmsg_type != SCM_RIGHTS ||
            c->cmsg_len < CMSG_LEN(0) || (c->cmsg_len - CMSG_LEN(0)) % sizeof(int)) {
            bad = 1; continue;
        }
        size_t number = (c->cmsg_len - CMSG_LEN(0)) / sizeof(int);
        for (size_t i = 0; i < number; ++i) {
            int fd; memcpy(&fd, CMSG_DATA(c) + i * sizeof(int), sizeof(fd));
            if (total < 2) fds[total] = fd; else { close(fd); bad = 1; }
            ++total;
        }
    }
    *count = total;
    if (bad || total != 2) { close_fd(&fds[0]); close_fd(&fds[1]); errno = EPROTO; return -1; }
    for (size_t i = 0; i < 2; ++i) {
        int flags = fcntl(fds[i], F_GETFL), descriptor_flags = fcntl(fds[i], F_GETFD);
        if (flags < 0 || !(flags & O_PATH) || descriptor_flags < 0 || !(descriptor_flags & FD_CLOEXEC)) {
            close_fd(&fds[0]); close_fd(&fds[1]); errno = EPROTO; return -1;
        }
    }
    return 0;
}
static int new_target(int directory, const char *leaf) {
    return openat(directory, leaf, O_RDONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
}
static struct operation bind_to(int source, int target) {
    char from[64], to[64];
    int a = snprintf(from, sizeof(from), "/proc/self/fd/%d", source);
    int b = snprintf(to, sizeof(to), "/proc/self/fd/%d", target);
    if (a <= 0 || (size_t)a >= sizeof(from) || b <= 0 || (size_t)b >= sizeof(to))
        return (struct operation){-1, EOVERFLOW};
    errno = 0;
    int rc = mount(from, to, NULL, MS_BIND, NULL);
    return (struct operation){rc, rc ? errno : 0};
}
static int target_identity(int dir, const char *leaf, struct file_identity *out, uint64_t *mnt) {
    int fd = openat(dir, leaf, O_PATH | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    int rc = identity(fd, out);
    if (!rc && mnt) rc = mount_id(fd, mnt);
    int saved = errno; close(fd); errno = saved; return rc;
}
static void child(int channel, int inherited_raw, int inherited_clone, int inherited_listener,
                  pid_t parent, const struct file_identity *parent_ns,
                  const struct file_identity *parent_user_ns) {
    struct evidence e;
    memset(&e, 0, sizeof(e));
    e.magic = MAGIC; memcpy(e.nonce, FIXTURE_NONCE, sizeof(e.nonce));
    e.parent_namespace = *parent_ns;
    e.parent_user_namespace = *parent_user_ns;
    e.raw_foreign_bind = e.local_reopen_bind = e.detached_move = (struct operation){-99, 0};
    int fds[2] = {-1, -1}, directory = -1, local = -1, targets[3] = {-1, -1, -1};
    close(inherited_raw); close(inherited_clone); close(inherited_listener);
    e.inherited_source_fds_closed = 1;
    e.child_stage = 1;
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent || unshare(CLONE_NEWNS) ||
        mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) || namespace_identity(&e.child_namespace) ||
        user_namespace_identity(&e.child_user_namespace)) goto done;
    if (equal_identity(&e.child_namespace, parent_ns) ||
        !equal_identity(&e.child_user_namespace, parent_user_ns)) { errno = EPROTO; goto done; }
    e.child_stage = 2;
    if (send(channel, "R", 1, MSG_NOSIGNAL) != 1 || receive_rights(channel, fds, &e.rights_count)) goto done;
    if (identity(fds[0], &e.raw_source) || identity(fds[1], &e.detached_source) ||
        !socket_identity(&e.raw_source) || !equal_identity(&e.raw_source, &e.detached_source) ||
        mount_id(fds[0], &e.raw_mount_id) || mount_id(fds[1], &e.detached_mount_id)) goto done;
    e.child_stage = 3;
    directory = open(FIXTURE_ROOT, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory < 0) goto done;
    local = openat(directory, "source.sock", O_PATH | O_CLOEXEC | O_NOFOLLOW);
    if (local < 0 || identity(local, &e.local_source) || !equal_identity(&e.raw_source, &e.local_source) ||
        mount_id(local, &e.local_mount_id) || e.local_mount_id == e.raw_mount_id) goto done;
    targets[0] = new_target(directory, "raw-target");
    targets[1] = new_target(directory, "local-target");
    targets[2] = new_target(directory, "move-target");
    if (targets[0] < 0 || targets[1] < 0 || targets[2] < 0) goto done;
    e.child_stage = 4;
    e.raw_foreign_bind = bind_to(fds[0], targets[0]);
    e.local_reopen_bind = bind_to(local, targets[1]);
    errno = 0;
    e.detached_move.rc = (int)syscall(SYS_move_mount, fds[1], "", targets[2], "",
                                     MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH);
    e.detached_move.error = e.detached_move.rc ? errno : 0;
    if (e.local_reopen_bind.rc == 0 && target_identity(directory, "local-target", &e.local_target, NULL)) goto done;
    if (e.detached_move.rc == 0 && target_identity(directory, "move-target", &e.moved_target, &e.moved_mount_id)) goto done;
    e.child_stage = 5;
    e.child_success = e.raw_foreign_bind.rc == -1 && e.raw_foreign_bind.error == EINVAL &&
        e.local_reopen_bind.rc == 0 && e.detached_move.rc == 0 &&
        equal_identity(&e.raw_source, &e.local_target) && equal_identity(&e.raw_source, &e.moved_target) &&
        e.moved_mount_id == e.detached_mount_id;
done:
    e.child_error = e.child_success ? 0 : errno;
    for (size_t i = 0; i < 3; ++i) close_fd(&targets[i]);
    close_fd(&local); close_fd(&directory); close_fd(&fds[0]); close_fd(&fds[1]);
    e.all_received_fds_closed = fds[0] == -1 && fds[1] == -1;
    ssize_t sent = send(channel, &e, sizeof(e), MSG_NOSIGNAL);
    close(channel);
    _exit(sent == (ssize_t)sizeof(e) && e.child_success ? 0 : 1);
}
static int reap(pid_t pid, int pidfd, int *status, int *forced) {
    if (pidfd >= 0) {
        struct pollfd p = {pidfd, POLLIN, 0};
        int rc;
        do { rc = poll(&p, 1, 1000); } while (rc < 0 && errno == EINTR);
        if (rc != 1 || !(p.revents & POLLIN)) {
            *forced = 1;
            if (syscall(SYS_pidfd_send_signal, pidfd, SIGKILL, NULL, 0) && errno != ESRCH) return -1;
        }
    } else {
        *forced = 1;
        /* Exact unreaped child PID is owned here and cannot be recycled. */
        if (kill(pid, SIGKILL) && errno != ESRCH) return -1;
    }
    for (unsigned i = 0; i < 200; ++i) {
        pid_t rc = waitpid(pid, status, WNOHANG);
        if (rc == pid) return 0;
        if (rc < 0 && errno != EINTR) return -1;
        struct timespec pause = {0, 5000000}; nanosleep(&pause, NULL);
    }
    errno = ETIMEDOUT; return -1;
}
int main(int argc, char **argv) {
    int stage = 0, saved = 0, success = 0, mounted = 0, unmounted = 0;
    int listener = -1, raw = -1, clone = -1, channels[2] = {-1, -1}, pidfd = -1;
    int child_reaped = 0, child_status = -1, forced = 0, report_received = 0;
    pid_t child_pid = -1;
    struct file_identity parent_ns, parent_user_ns;
    memset(&parent_ns, 0, sizeof(parent_ns));
    memset(&parent_user_ns, 0, sizeof(parent_user_ns));
    struct evidence e;
    memset(&e, 0, sizeof(e));
    struct utsname os;
    memset(&os, 0, sizeof(os));
    if (argc != 2 || strlen(FIXTURE_NONCE) != 32) { errno = EINVAL; goto done; }
    char *end = NULL; long expected_parent = strtol(argv[1], &end, 10);
    if (!end || *end || expected_parent <= 1 || expected_parent != getppid() ||
        getuid() || geteuid() || getgid() || getegid() ||
        prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != expected_parent) { errno = EPERM; goto done; }
    stage = 1;
    if (unshare(CLONE_NEWNS) || mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) ||
        namespace_identity(&parent_ns) || user_namespace_identity(&parent_user_ns) || uname(&os)) goto done;
    struct stat st;
    if (lstat(FIXTURE_ROOT, &st) || !S_ISDIR(st.st_mode) || st.st_uid || st.st_gid ||
        (st.st_mode & 07777) != 0700) { errno = EPERM; goto done; }
    stage = 2;
    if (mount("p4-owned-projection", FIXTURE_ROOT, "tmpfs", MS_NOSUID | MS_NODEV | MS_NOEXEC,
              "mode=0700,size=1048576")) goto done;
    mounted = 1;
    listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (listener < 0) goto done;
    struct sockaddr_un address;
    memset(&address, 0, sizeof(address)); address.sun_family = AF_UNIX;
    int n = snprintf(address.sun_path, sizeof(address.sun_path), "%s/source.sock", FIXTURE_ROOT);
    if (n <= 0 || (size_t)n >= sizeof(address.sun_path)) { errno = EOVERFLOW; goto done; }
    if (bind(listener, (const struct sockaddr *)&address, sizeof(address)) ||
        chmod(address.sun_path, 0600) || chown(address.sun_path, FIXTURE_UID, FIXTURE_GID) ||
        listen(listener, 1)) goto done;
    raw = open(address.sun_path, O_PATH | O_CLOEXEC | O_NOFOLLOW);
    if (raw < 0) goto done;
    stage = 3;
    clone = (int)syscall(SYS_open_tree, raw, "", OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC | AT_EMPTY_PATH);
    if (clone < 0 || socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, channels)) goto done;
    stage = 4;
    pid_t self = getpid();
    child_pid = fork();
    if (child_pid < 0) goto done;
    if (!child_pid) {
        close(channels[0]);
        child(channels[1], raw, clone, listener, self, &parent_ns, &parent_user_ns);
    }
    close_fd(&channels[1]);
    pidfd = (int)syscall(SYS_pidfd_open, child_pid, 0);
    if (pidfd < 0) goto done;
    stage = 5;
    char ready[2];
    if (wait_readable(channels[0], 5000) || recv(channels[0], ready, sizeof(ready), MSG_TRUNC) != 1 || ready[0] != 'R') goto done;
    const int send[2] = {raw, clone};
    if (send_rights(channels[0], send) || wait_readable(channels[0], 5000)) goto done;
    if (recv(channels[0], &e, sizeof(e), MSG_TRUNC | MSG_DONTWAIT) != (ssize_t)sizeof(e) ||
        e.magic != MAGIC || memcmp(e.nonce, FIXTURE_NONCE, sizeof(e.nonce))) { errno = EPROTO; goto done; }
    report_received = 1;
    stage = 6;
done:
    saved = errno;
    if (child_pid > 0) child_reaped = reap(child_pid, pidfd, &child_status, &forced) == 0;
    close_fd(&pidfd); close_fd(&channels[0]); close_fd(&channels[1]);
    close_fd(&raw); close_fd(&clone); close_fd(&listener);
    if (mounted && (child_pid <= 0 || child_reaped)) unmounted = umount(FIXTURE_ROOT) == 0;
    success = stage == 6 && report_received && e.child_success && child_reaped &&
              WIFEXITED(child_status) && WEXITSTATUS(child_status) == 0 && !forced && unmounted;
    printf("{\"schema\":1,\"nonce\":\"%s\",\"success\":%s,\"stage\":%d,\"error\":%d,"
           "\"kernel_release\":\"%s\",\"parent_mount_namespace\":[%llu,%llu],"
           "\"child_mount_namespace\":[%llu,%llu],\"parent_user_namespace\":[%llu,%llu],"
           "\"child_user_namespace\":[%llu,%llu],\"child_stage\":%d,\"child_error\":%d,"
           "\"raw_foreign_bind\":{\"rc\":%d,\"errno\":%d},"
           "\"local_reopen_bind\":{\"rc\":%d,\"errno\":%d},"
           "\"detached_move\":{\"rc\":%d,\"errno\":%d},"
           "\"source_identity\":[%llu,%llu,%u,%u,%u],"
           "\"mount_ids\":[%llu,%llu,%llu,%llu],\"rights_count\":%d,"
           "\"inherited_source_fds_closed\":%s,\"received_fds_closed\":%s,"
           "\"same_inode_owner_mode_after_local_bind_and_move\":%s,"
           "\"child_pid\":%d,\"child_reaped\":%s,\"child_wait_status\":%d,"
           "\"forced_kill\":%s,\"private_tmpfs_unmounted\":%s,\"Android_executed\":false}\n",
           FIXTURE_NONCE, success ? "true" : "false", stage, success ? 0 : saved, os.release,
           (unsigned long long)parent_ns.device, (unsigned long long)parent_ns.inode,
           (unsigned long long)e.child_namespace.device, (unsigned long long)e.child_namespace.inode,
           (unsigned long long)parent_user_ns.device, (unsigned long long)parent_user_ns.inode,
           (unsigned long long)e.child_user_namespace.device, (unsigned long long)e.child_user_namespace.inode,
           e.child_stage, e.child_error, e.raw_foreign_bind.rc, e.raw_foreign_bind.error,
           e.local_reopen_bind.rc, e.local_reopen_bind.error, e.detached_move.rc, e.detached_move.error,
           (unsigned long long)e.raw_source.device, (unsigned long long)e.raw_source.inode,
           e.raw_source.uid, e.raw_source.gid, e.raw_source.mode,
           (unsigned long long)e.raw_mount_id, (unsigned long long)e.local_mount_id,
           (unsigned long long)e.detached_mount_id, (unsigned long long)e.moved_mount_id,
           e.rights_count, e.inherited_source_fds_closed ? "true" : "false",
           e.all_received_fds_closed ? "true" : "false",
           report_received && equal_identity(&e.raw_source, &e.local_target) &&
             equal_identity(&e.raw_source, &e.moved_target) ? "true" : "false",
           child_pid, child_reaped ? "true" : "false", child_status, forced ? "true" : "false",
           unmounted ? "true" : "false");
    return success ? 0 : 1;
}
