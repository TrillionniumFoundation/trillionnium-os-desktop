#define _GNU_SOURCE
/* Three owned mount arms only. No controller activation, cgroup migration,
 * Android, network or installed-file change. The received cgroup descriptor
 * is the caller's already finite job; this program never writes its controls. */
#include <errno.h>
#include <fcntl.h>
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
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define FIXTURE_ROOT "/opt/p4-cgroup-mount-mechanism-20261105-02/mountpoint"
#define FIXTURE_NONCE "782a06e513cc0b63cd93d6022c6495b5"
#define MAGIC UINT64_C(0x503443474d4e5431)
#define CGROUP2_MAGIC 0x63677270
#define MOUNT_FLAGS (MS_NOSUID | MS_NODEV | MS_NOEXEC)

struct identity { uint64_t dev, ino; uint32_t mode, uid, gid; };
struct operation { int rc, error; };
struct clocks { uint64_t monotonic_ns, boottime_ns, realtime_ns; };
struct evidence {
    uint64_t magic;
    char nonce[33];
    int child_pid, stage, first_error, success;
    uint64_t child_birth_ticks;
    struct identity domain, first_target, fresh_target;
    struct identity parent_user, parent_mount, parent_cgroup;
    struct identity child_user, child_mount, child_cgroup;
    struct clocks begin, end;
    struct operation first_a, repeat_a_recursiveprot, repeat_a_plain, fresh_b;
    int all_private_mounts_unmounted, inherited_domain_closed;
};

static void close_fd(int *fd) { if (*fd >= 0) { close(*fd); *fd = -1; } }
static int fd_identity(int fd, struct identity *out) {
    struct stat st;
    if (fstat(fd, &st)) return -1;
    *out = (struct identity){st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid};
    return 0;
}
static int same_inode(const struct identity *a, const struct identity *b) {
    return a->dev == b->dev && a->ino == b->ino;
}
static int same_domain(const struct identity *a, const struct identity *b) {
    return same_inode(a,b) && a->mode == b->mode && a->uid == b->uid && a->gid == b->gid;
}
static int ns_identity(const char *name, struct identity *out) {
    char path[64];
    int count = snprintf(path, sizeof(path), "/proc/self/ns/%s", name);
    if (count <= 0 || (size_t)count >= sizeof(path)) { errno = EOVERFLOW; return -1; }
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    int rc = fd_identity(fd, out), saved = errno;
    close(fd); errno = saved; return rc;
}
static uint64_t clock_ns(clockid_t kind) {
    struct timespec ts;
    if (clock_gettime(kind, &ts)) return 0;
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}
static int clocks(struct clocks *out) {
    out->monotonic_ns = clock_ns(CLOCK_MONOTONIC);
    out->boottime_ns = clock_ns(CLOCK_BOOTTIME);
    out->realtime_ns = clock_ns(CLOCK_REALTIME);
    if (!out->monotonic_ns || !out->boottime_ns || !out->realtime_ns) { errno = EIO; return -1; }
    return 0;
}
static int domain_identity(int fd, struct identity *out) {
    struct statfs fs;
    if (fd_identity(fd, out) || fstatfs(fd, &fs)) return -1;
    /* The current user-manager job can be user-owned. The only authority is
     * the caller's held resource-gated descriptor, not an assumed UID. Every
     * projected view must retain this exact inode/owner/group/mode. */
    if (fs.f_type != CGROUP2_MAGIC || !S_ISDIR(out->mode)) { errno = EPERM; return -1; }
    return 0;
}
static int target_identity(const char *path, struct identity *out) {
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    int rc = domain_identity(fd, out), saved = errno;
    close(fd); errno = saved; return rc;
}
static struct operation mount_cgroup(const char *path, const char *options) {
    errno = 0;
    int rc = mount("none", path, "cgroup2", MOUNT_FLAGS, options);
    return (struct operation){rc, rc ? errno : 0};
}
static int decimal(const char *text, int *out) {
    if (!text || !*text || *text == '0') return -1;
    unsigned long value = 0;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p < '0' || *p > '9' || value > (2147483647UL - (*p - '0')) / 10UL) return -1;
        value = value * 10UL + (*p - '0');
    }
    *out = (int)value; return 0;
}
static int self_birth(uint64_t *out) {
    int fd = open("/proc/self/stat", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    char text[4096]; ssize_t n = read(fd, text, sizeof(text) - 1); int saved = errno;
    close(fd); errno = saved;
    if (n <= 0 || n >= (ssize_t)sizeof(text) - 1) { errno = EPROTO; return -1; }
    text[n] = 0;
    char *at = strrchr(text, ')');
    if (!at || at[1] != ' ') { errno = EPROTO; return -1; }
    at += 2;
    for (int field = 3; field < 22; ++field) {
        at = strchr(at, ' ');
        if (!at || !at[1] || at[1] == ' ') { errno = EPROTO; return -1; }
        ++at;
    }
    uint64_t value = 0;
    if (*at < '0' || *at > '9') { errno = EPROTO; return -1; }
    while (*at >= '0' && *at <= '9') {
        if (value > (UINT64_MAX - (unsigned)(*at - '0')) / 10) { errno = EOVERFLOW; return -1; }
        value = value * 10 + (unsigned)(*at++ - '0');
    }
    if (!value || *at != ' ') { errno = EPROTO; return -1; }
    *out = value; return 0;
}

static void child_run(int channel, int domain_fd, pid_t parent, struct evidence e) {
    int root_mounted = 0, a_mounts = 0, b_mounts = 0;
    int root = -1, a = -1, b = -1;
    e.child_pid = getpid(); e.stage = 1;
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent ||
        getuid() || geteuid() || getgid() || getegid() || clocks(&e.begin) ||
        self_birth(&e.child_birth_ticks)) goto fail;
    struct identity inherited;
    if (fcntl(domain_fd, F_SETFD, FD_CLOEXEC) || domain_identity(domain_fd, &inherited)) goto fail;
    if (!same_domain(&inherited,&e.domain)) { errno=EPROTO; goto fail; }
    e.stage = 2;
    if (unshare(CLONE_NEWNS | CLONE_NEWCGROUP) ||
        mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL)) goto fail;
    if (ns_identity("user", &e.child_user) || ns_identity("mnt", &e.child_mount) ||
        ns_identity("cgroup", &e.child_cgroup)) goto fail;
    if (!same_inode(&e.parent_user, &e.child_user) ||
        same_inode(&e.parent_mount, &e.child_mount) ||
        same_inode(&e.parent_cgroup, &e.child_cgroup)) { errno = EPROTO; goto fail; }
    e.stage = 3;
    if (mount("tmpfs", FIXTURE_ROOT, "tmpfs", MOUNT_FLAGS, "size=65536,mode=0700")) goto fail;
    root_mounted = 1;
    root = open(FIXTURE_ROOT, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (root < 0 || mkdirat(root, "a", 0700) || mkdirat(root, "b", 0700)) goto fail;
    a = openat(root, "a", O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    b = openat(root, "b", O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat sa, sb;
    if (a < 0 || b < 0 || fstat(a, &sa) || fstat(b, &sb) ||
        sa.st_uid || sa.st_gid || sb.st_uid || sb.st_gid ||
        !S_ISDIR(sa.st_mode) || !S_ISDIR(sb.st_mode) ||
        (sa.st_mode & 0022) || (sb.st_mode & 0022)) goto fail;
    /* Pathnames are wholly owned beneath this newly private tmpfs. Re-open
     * the projected roots for identity; the original O_PATH descriptors
     * refer to the uncovered directories and must not be used for repeat. */
    e.stage = 4;
    e.first_a = mount_cgroup(FIXTURE_ROOT "/a", NULL);
    if (e.first_a.rc) { errno = e.first_a.error; goto fail; }
    ++a_mounts;
    if (target_identity(FIXTURE_ROOT "/a", &e.first_target) ||
        !same_domain(&e.domain, &e.first_target)) { errno = EPROTO; goto fail; }
    e.stage = 5;
    e.repeat_a_recursiveprot = mount_cgroup(FIXTURE_ROOT "/a", "memory_recursiveprot");
    if (!e.repeat_a_recursiveprot.rc) ++a_mounts;
    e.repeat_a_plain = mount_cgroup(FIXTURE_ROOT "/a", NULL);
    if (!e.repeat_a_plain.rc) ++a_mounts;
    e.stage = 6;
    e.fresh_b = mount_cgroup(FIXTURE_ROOT "/b", NULL);
    if (!e.fresh_b.rc) ++b_mounts;
    if (e.fresh_b.rc) { errno = e.fresh_b.error; goto fail; }
    if (target_identity(FIXTURE_ROOT "/b", &e.fresh_target) ||
        !same_domain(&e.domain, &e.fresh_target)) { errno = EPROTO; goto fail; }
    if (e.repeat_a_recursiveprot.rc != -1 || e.repeat_a_recursiveprot.error != EBUSY ||
        e.repeat_a_plain.rc != -1 || e.repeat_a_plain.error != EBUSY) { errno = EPROTO; goto fail; }
    e.success = 1;
    goto done;
fail:
    e.first_error = errno ? errno : EPROTO;
done:
    close_fd(&a); close_fd(&b); close_fd(&root);
    int clean = 1;
    while (b_mounts-- > 0) if (umount2(FIXTURE_ROOT "/b", 0)) clean = 0;
    while (a_mounts-- > 0) if (umount2(FIXTURE_ROOT "/a", 0)) clean = 0;
    if (root_mounted && umount2(FIXTURE_ROOT, 0)) clean = 0;
    e.all_private_mounts_unmounted = clean;
    close_fd(&domain_fd); e.inherited_domain_closed = 1;
    if (clocks(&e.end) || !clean) {
        if (!e.first_error) e.first_error = errno ? errno : EIO;
        e.success = 0;
    }
    ssize_t sent = send(channel, &e, sizeof(e), MSG_NOSIGNAL);
    close_fd(&channel);
    _exit(sent == (ssize_t)sizeof(e) && e.success ? 0 : 1);
}

static void print_identity(const struct identity *value) {
    printf("{\"device\":%llu,\"inode\":%llu,\"mode\":%u,\"uid\":%u,\"gid\":%u}",
           (unsigned long long)value->dev, (unsigned long long)value->ino,
           value->mode, value->uid, value->gid);
}
static void print_ns(const struct identity *value) {
    printf("[%llu,%llu]", (unsigned long long)value->dev, (unsigned long long)value->ino);
}
static void print_op(const struct operation *value) { printf("{\"rc\":%d,\"errno\":%d}", value->rc, value->error); }
static void print_clock(const struct clocks *value) {
    printf("{\"monotonic_ns\":%llu,\"boottime_ns\":%llu,\"realtime_ns\":%llu}",
           (unsigned long long)value->monotonic_ns, (unsigned long long)value->boottime_ns,
           (unsigned long long)value->realtime_ns);
}
struct collection {
    int got, peer_eof, reaped, forced, status, error;
};

/* A seqpacket stream has exactly one evidence frame followed by EOF. EOF
 * after that frame is completion, not a second frame. Keep draining until
 * EOF even if the exact child has exited, so queued extra data is rejected. */
static struct collection collect_child(int channel, pid_t child,
                                      struct evidence *e, uint64_t timeout_ns) {
    struct collection out = {0};
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0);
    uint64_t deadline = clock_ns(CLOCK_MONOTONIC) + timeout_ns;
    if (pidfd < 0) out.error = errno;
    while (!out.error && (!out.reaped || !out.peer_eof)) {
        uint64_t now = clock_ns(CLOCK_MONOTONIC);
        if (!now || now >= deadline) { out.error = ETIMEDOUT; break; }
        struct pollfd polls[2] = {
            {out.peer_eof ? -1 : channel, POLLIN | POLLRDHUP, 0},
            {out.reaped ? -1 : pidfd, POLLIN, 0}
        };
        int rc = poll(polls, 2, 100);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0) { out.error = errno; break; }
        if (polls[0].revents & (POLLIN | POLLHUP | POLLRDHUP)) {
            struct evidence candidate;
            ssize_t n = recv(channel, &candidate, sizeof(candidate), MSG_DONTWAIT | MSG_TRUNC);
            if (n < 0) {
                if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) out.error = errno;
            } else if (n == 0) {
                if (!out.got || !(polls[0].revents & (POLLHUP | POLLRDHUP))) out.error = EPROTO;
                else out.peer_eof = 1;
            } else if (out.got || n != (ssize_t)sizeof(candidate) || candidate.magic != MAGIC ||
                       memcmp(candidate.nonce, FIXTURE_NONCE, sizeof(candidate.nonce)) ||
                       candidate.child_pid != child) {
                out.error = EPROTO;
            } else {
                *e = candidate; out.got = 1;
            }
        }
        if (polls[1].revents & (POLLIN | POLLHUP)) {
            pid_t waited = waitpid(child, &out.status, WNOHANG);
            if (waited == child) out.reaped = 1;
            else if (waited < 0 && errno != EINTR && !out.error) out.error = errno;
        }
        if (((polls[0].revents | polls[1].revents) & (POLLERR | POLLNVAL)) && !out.error) out.error = EIO;
    }
    if (!out.reaped) {
        /* Recheck the exact child before a cleanup signal. An exited child
         * must not be classified as forced merely because pidfd poll lagged. */
        pid_t waited = waitpid(child, &out.status, WNOHANG);
        if (waited == child) out.reaped = 1;
        else if (waited < 0 && errno != EINTR && !out.error) out.error = errno;
    }
    if (!out.reaped) {
        if (pidfd >= 0) syscall(SYS_pidfd_send_signal, pidfd, SIGKILL, NULL, 0);
        else kill(child, SIGKILL);
        out.forced = 1;
        uint64_t reap_deadline = clock_ns(CLOCK_MONOTONIC) + UINT64_C(3000000000);
        while (clock_ns(CLOCK_MONOTONIC) < reap_deadline) {
            pid_t waited = waitpid(child, &out.status, WNOHANG);
            if (waited == child) { out.reaped = 1; break; }
            if (waited < 0 && errno != EINTR) { if (!out.error) out.error = errno; break; }
            struct timespec delay = {0, 5000000}; nanosleep(&delay, NULL);
        }
        if (!out.reaped && !out.error) out.error = ETIMEDOUT;
    }
    if ((!out.got || !out.peer_eof) && !out.error) out.error = EPROTO;
    close_fd(&pidfd);
    return out;
}
int main(int argc, char **argv) {
    int expected_parent = 0, domain_fd = -1;
    if (argc != 3 || decimal(argv[1], &expected_parent) || decimal(argv[2], &domain_fd) ||
        domain_fd < 3 || getppid() != expected_parent || getuid() || geteuid() || getgid() || getegid() ||
        prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != expected_parent) return 2;
    struct evidence e; memset(&e, 0, sizeof(e));
    e.magic = MAGIC; memcpy(e.nonce, FIXTURE_NONCE, sizeof(e.nonce));
    if (domain_identity(domain_fd, &e.domain) || ns_identity("user", &e.parent_user) ||
        ns_identity("mnt", &e.parent_mount) || ns_identity("cgroup", &e.parent_cgroup)) return 2;
    int pair[2] = {-1, -1};
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, pair)) return 2;
    pid_t self = getpid(), child = fork();
    if (child < 0) { close_fd(&pair[0]); close_fd(&pair[1]); return 2; }
    if (!child) { close_fd(&pair[0]); child_run(pair[1], domain_fd, self, e); }
    close_fd(&pair[1]); close_fd(&domain_fd);
    struct collection out = collect_child(pair[0], child, &e, UINT64_C(15000000000));
    close_fd(&pair[0]);
    int success = out.got && out.peer_eof && !out.error && out.reaped && !out.forced &&
        WIFEXITED(out.status) && WEXITSTATUS(out.status) == 0 &&
        e.success && e.all_private_mounts_unmounted && e.inherited_domain_closed;
    printf("{\"schema\":1,\"nonce\":\"%s\",\"success\":%s,\"Android_executed\":false,"
           "\"cgroup_controls_written\":false,\"child_pid\":%d,\"child_birth_ticks\":%llu,\"child_stage\":%d,\"child_errno\":%d,"
           "\"parent_errno\":%d,\"peer_eof\":%s,\"child_reaped\":%s,\"forced_kill\":%s,\"child_wait_status\":%d,",
           FIXTURE_NONCE, success ? "true" : "false", child, (unsigned long long)e.child_birth_ticks, e.stage, e.first_error,
           out.error, out.peer_eof ? "true" : "false", out.reaped ? "true" : "false", out.forced ? "true" : "false", out.status);
    printf("\"domain\":"); print_identity(&e.domain);
    printf(",\"first_target\":"); print_identity(&e.first_target);
    printf(",\"fresh_target\":"); print_identity(&e.fresh_target);
    printf(",\"parent_user_namespace\":"); print_ns(&e.parent_user);
    printf(",\"child_user_namespace\":"); print_ns(&e.child_user);
    printf(",\"parent_mount_namespace\":"); print_ns(&e.parent_mount);
    printf(",\"child_mount_namespace\":"); print_ns(&e.child_mount);
    printf(",\"parent_cgroup_namespace\":"); print_ns(&e.parent_cgroup);
    printf(",\"child_cgroup_namespace\":"); print_ns(&e.child_cgroup);
    printf(",\"first_a\":"); print_op(&e.first_a);
    printf(",\"repeat_a_recursiveprot\":"); print_op(&e.repeat_a_recursiveprot);
    printf(",\"repeat_a_plain\":"); print_op(&e.repeat_a_plain);
    printf(",\"fresh_b\":"); print_op(&e.fresh_b);
    printf(",\"child_begin\":"); print_clock(&e.begin);
    printf(",\"child_end\":"); print_clock(&e.end);
    printf(",\"all_private_mounts_unmounted\":%s,\"inherited_domain_closed\":%s}\n",
           e.all_private_mounts_unmounted ? "true" : "false", e.inherited_domain_closed ? "true" : "false");
    return success ? 0 : 1;
}
