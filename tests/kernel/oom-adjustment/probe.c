// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

/* Only the private, networkless guest runner supplies this marker. Never run
 * this program against host procfs. All non-self PIDs and FDs below are owned
 * children or explicit SCM_RIGHTS delegations within this one fixture. */
#define REQUIRE(expression) do { \
    if (!(expression)) { \
        dprintf(2, "OOM_QA line=%d errno=%d\n", __LINE__, errno); \
        return 1; \
    } \
} while (0)
#define STACK_BYTES (256 * 1024)
static const char *program;
static const char *guard_arg = "--asterinas-disposable-guest";
static const char *stage_name = "exec";

static int guest_guard(void) {
    char marker[34];
    int fd = open("/.hepta-oom-adjustment-qa", O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return 0;
    ssize_t count = read(fd, marker, sizeof(marker));
    close(fd);
    if (count != 33 || marker[32] != '\n') return 0;
    for (int i = 0; i < 32; ++i)
        if (!((marker[i] >= '0' && marker[i] <= '9') ||
              (marker[i] >= 'a' && marker[i] <= 'f'))) return 0;
    return getpid() > 1;
}

static int caps(struct __user_cap_data_struct data[2]) {
    struct __user_cap_header_struct header = {
        .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0
    };
    return syscall(SYS_capget, &header, data);
}

/* Preserve the real permitted set; only effective bits change. No test-only
 * authority override is provided to the kernel. This is per-writer state. */
static int effective(uint64_t bits) {
    struct __user_cap_header_struct header = {
        .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0
    };
    struct __user_cap_data_struct data[2];
    if (caps(data)) return -1;
    data[0].effective = (uint32_t)bits;
    data[1].effective = (uint32_t)(bits >> 32);
    return syscall(SYS_capset, &header, data);
}

static int have_effective(uint64_t bits) {
    struct __user_cap_data_struct data[2];
    if (caps(data)) return 0;
    uint64_t actual = data[0].effective | ((uint64_t)data[1].effective << 32);
    return actual == bits;
}

static int become_user(uid_t uid) {
    if (setresgid(uid, uid, uid) || setresuid(uid, uid, uid)) return -1;
    /* A real credential transition makes the image nondumpable. Explicitly
     * restore dumpability so owner-DAC tests exercise a normal owned image. */
    if (prctl(PR_SET_DUMPABLE, 1) || !have_effective(0)) return -1;
    return getuid() == uid && geteuid() == uid ? 0 : -1;
}

static int open_adj(pid_t pid) {
    char path[80];
    if (pid == 0) return open("/proc/self/oom_score_adj", O_RDWR);
    snprintf(path, sizeof(path), "/proc/%ld/oom_score_adj", (long)pid);
    return open(path, O_RDWR);
}

static int read_adj(int fd, int expected) {
    char text[32], *end;
    ssize_t count = pread(fd, text, sizeof(text) - 1, 0);
    if (count <= 0) return 0;
    text[count] = 0;
    long value = strtol(text, &end, 10);
    return value == expected && !strcmp(end, "\n");
}

static int write_adj(int fd, int value, int expected_errno) {
    char text[32];
    int length = snprintf(text, sizeof(text), "%d\n", value);
    errno = 0;
    ssize_t count = pwrite(fd, text, length, 0);
    int saved = errno;
    /* Record actual syscall facts even on a failing candidate. */
    dprintf(1, "{\"observation\":\"write\",\"stage\":\"%s\",\"pid\":%ld,\"value\":%d,"
            "\"rc\":%ld,\"errno\":%d,\"expected_errno\":%d}\n",
            stage_name, (long)getpid(), value, (long)count, saved, expected_errno);
    return expected_errno ? count == -1 && saved == expected_errno : count == length;
}

static int join(pid_t pid) {
    int status;
    return waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

static int byte(int fd, int writing) {
    char value = 'x';
    return (writing ? write(fd, &value, 1) : read(fd, &value, 1)) == 1;
}

static int uid_floor(void) {
    REQUIRE(become_user(60001) == 0);
    int fd = open_adj(0);
    REQUIRE(fd >= 0 && read_adj(fd, 0));
    REQUIRE(write_adj(fd, 500, 0) && write_adj(fd, 0, 0));
    REQUIRE(write_adj(fd, -1, EACCES) && read_adj(fd, 0));
    REQUIRE(write_adj(fd, -1001, EINVAL) && write_adj(fd, 1001, EINVAL));
    REQUIRE(read_adj(fd, 0));
    return close(fd) != 0;
}

static int privileged_floor(void) {
    int fd = open_adj(0);
    REQUIRE(fd >= 0);
    REQUIRE(effective(UINT64_C(1) << CAP_SYS_RESOURCE) == 0);
    REQUIRE(have_effective(UINT64_C(1) << CAP_SYS_RESOURCE));
    REQUIRE(write_adj(fd, 200, 0));
    REQUIRE(effective(0) == 0 && have_effective(0));
    REQUIRE(write_adj(fd, 500, 0) && write_adj(fd, 200, 0));
    REQUIRE(write_adj(fd, 199, EACCES) && read_adj(fd, 200));
    /* UID zero and SYS_PTRACE are not substitutes for SYS_RESOURCE. */
    REQUIRE(effective(UINT64_C(1) << CAP_SYS_PTRACE) == 0);
    REQUIRE(write_adj(fd, 199, EACCES));
    REQUIRE(effective(UINT64_C(1) << CAP_SYS_RESOURCE) == 0);
    REQUIRE(write_adj(fd, -100, 0));
    REQUIRE(effective(0) == 0 && have_effective(0));
    REQUIRE(write_adj(fd, 400, 0) && write_adj(fd, -100, 0));
    REQUIRE(write_adj(fd, -101, EACCES) && read_adj(fd, -100));
    return close(fd) != 0;
}

static int ordinary_fork(void) {
    int fd = open_adj(0), ready[2], go[2];
    REQUIRE(fd >= 0 && write_adj(fd, -100, 0));
    REQUIRE(effective(0) == 0 && write_adj(fd, 500, 0));
    REQUIRE(pipe(ready) == 0 && pipe(go) == 0);
    pid_t child = fork();
    REQUIRE(child >= 0);
    if (!child) {
        close(fd); close(ready[0]); close(go[1]);
        int own = open_adj(0);
        int ok = own >= 0 && read_adj(own, 500) && write_adj(own, -100, 0) &&
                 write_adj(own, -101, EACCES) && byte(ready[1], 1) && byte(go[0], 0) &&
                 read_adj(own, -100) && write_adj(own, 0, 0);
        if (own >= 0) close(own);
        _exit(ok ? 0 : 42);
    }
    close(ready[1]); close(go[0]);
    REQUIRE(byte(ready[0], 0));
    REQUIRE(effective(UINT64_C(1) << CAP_SYS_RESOURCE) == 0);
    REQUIRE(write_adj(fd, 200, 0) && byte(go[1], 1));
    REQUIRE(join(child) && read_adj(fd, 200));
    close(ready[0]); close(go[1]);
    return close(fd) != 0;
}

struct peer_args { int ready[2], go[2]; };
static int shared_peer(void *argument) {
    struct peer_args *args = argument;
    int fd = open_adj(0);
    if (fd < 0 || !byte(args->ready[1], 1) || !byte(args->go[0], 0)) return 42;
    if (!read_adj(fd, 200) || effective(0) || !write_adj(fd, 199, EACCES) ||
        !write_adj(fd, 500, 0) || !byte(args->ready[1], 1) || !byte(args->go[0], 0)) return 42;
    int ok = read_adj(fd, -100) && write_adj(fd, -100, 0) && write_adj(fd, -101, EACCES);
    close(fd);
    return ok ? 0 : 42;
}

static int separate_clone_vm(void) {
    int fd = open_adj(0);
    struct peer_args args;
    REQUIRE(fd >= 0 && pipe(args.ready) == 0 && pipe(args.go) == 0);
    void *stack = mmap(NULL, STACK_BYTES, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
    REQUIRE(stack != MAP_FAILED);
    pid_t child = clone(shared_peer, (char *)stack + STACK_BYTES, CLONE_VM | SIGCHLD, &args);
    REQUIRE(child >= 0 && byte(args.ready[0], 0));
    int retained_child_fd = open_adj(child);
    REQUIRE(retained_child_fd >= 0 && write_adj(fd, 200, 0) && byte(args.go[1], 1));
    REQUIRE(byte(args.ready[0], 0) && read_adj(fd, 500));
    REQUIRE(write_adj(fd, -100, 0) && byte(args.go[1], 1) && join(child));
    REQUIRE(read_adj(fd, -100));
    /* After real exit and reaping, an old delegated proc file cannot revive
     * the child. Native tests separately bind the earlier VM-unbind cut. */
    errno = 0;
    char value[16];
    REQUIRE(pread(retained_child_fd, value, sizeof(value), 0) == -1 && errno == ESRCH);
    REQUIRE(write_adj(retained_child_fd, 0, ESRCH));
    REQUIRE(write_adj(fd, 0, 0) && read_adj(fd, 0));
    close(retained_child_fd); close(fd);
    close(args.ready[0]); close(args.ready[1]); close(args.go[0]); close(args.go[1]);
    return munmap(stack, STACK_BYTES) != 0;
}

static int vfork_peer(void *unused) {
    (void)unused;
    int fd = open_adj(0);
    if (fd < 0 || !read_adj(fd, 200) || !write_adj(fd, 300, 0) || effective(0)) return 42;
    int ok = write_adj(fd, 500, 0) && write_adj(fd, 300, 0) && write_adj(fd, 299, EACCES);
    close(fd);
    return ok ? 0 : 42;
}

static int independent_vfork(void) {
    int fd = open_adj(0);
    REQUIRE(fd >= 0 && write_adj(fd, 200, 0));
    void *stack = mmap(NULL, STACK_BYTES, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
    REQUIRE(stack != MAP_FAILED);
    /* A separate child stack avoids C vfork's caller-stack restrictions while
     * exercising the actual Linux CLONE_VM|CLONE_VFORK kernel handshake. */
    pid_t child = clone(vfork_peer, (char *)stack + STACK_BYTES,
                        CLONE_VM | CLONE_VFORK | SIGCHLD, NULL);
    REQUIRE(child > 0 && join(child) && read_adj(fd, 200));
    close(fd);
    return munmap(stack, STACK_BYTES) != 0;
}

struct thread_args { int expected, denied, failed; };
static void *thread_writer(void *argument) {
    struct thread_args *args = argument;
    int fd = open_adj(0);
    args->failed = fd < 0 || effective(0) || !have_effective(0) ||
                   !read_adj(fd, args->expected) || !write_adj(fd, 500, 0) ||
                   !write_adj(fd, args->expected, 0) || !write_adj(fd, args->denied, EACCES);
    if (fd >= 0) close(fd);
    return NULL;
}

static int shared_process_threads(void) {
    int fd = open_adj(0);
    REQUIRE(fd >= 0 && write_adj(fd, -100, 0));
    struct thread_args args = {.expected = -100, .denied = -101};
    pthread_t thread;
    REQUIRE(pthread_create(&thread, NULL, thread_writer, &args) == 0);
    REQUIRE(pthread_join(thread, NULL) == 0 && !args.failed && read_adj(fd, -100));
    /* The first writer dropped only its own capability. The parent still has
     * SYS_RESOURCE and replaces the same Process floor for a second thread. */
    REQUIRE(write_adj(fd, 200, 0));
    args = (struct thread_args){.expected = 200, .denied = 199};
    REQUIRE(pthread_create(&thread, NULL, thread_writer, &args) == 0);
    REQUIRE(pthread_join(thread, NULL) == 0 && !args.failed && read_adj(fd, 200));
    return close(fd) != 0;
}

static int exec_check(int fd) {
    REQUIRE(getuid() == 60001 && have_effective(0));
    REQUIRE(read_adj(fd, 500));
    int own = open_adj(0);
    REQUIRE(own >= 0 && read_adj(own, 500));
    REQUIRE(write_adj(fd, -100, 0) && write_adj(own, -101, EACCES));
    REQUIRE(read_adj(fd, -100));
    close(own);
    return close(fd) != 0;
}

static int real_exec(void) {
    int fd = open_adj(0);
    REQUIRE(fd >= 0 && write_adj(fd, -100, 0));
    REQUIRE(effective(0) == 0 && write_adj(fd, 500, 0));
    /* Restore only the capabilities needed for a real UID/GID transition. */
    REQUIRE(effective((UINT64_C(1) << CAP_SETUID) | (UINT64_C(1) << CAP_SETGID)) == 0);
    REQUIRE(become_user(60001) == 0);
    char descriptor[24];
    snprintf(descriptor, sizeof(descriptor), "%d", fd);
    execl(program, program, guard_arg, "--exec-check", descriptor, (char *)NULL);
    return 1;
}

struct exec_args { int ready[2], go[2]; };
static int exec_vm_peer(void *argument) {
    struct exec_args *args = argument;
    int own = open_adj(0);
    if (own < 0 || become_user(60001)) return 41;
    char fd[24], ready[24], go[24];
    snprintf(fd, sizeof(fd), "%d", own);
    snprintf(ready, sizeof(ready), "%d", args->ready[1]);
    snprintf(go, sizeof(go), "%d", args->go[0]);
    execl(program, program, guard_arg, "--exec-peer", fd, ready, go, (char *)NULL);
    return 42;
}

static int clone_vm_exec_detaches(void) {
    int fd = open_adj(0);
    REQUIRE(fd >= 0 && write_adj(fd, -100, 0));
    REQUIRE(effective(0) == 0 && write_adj(fd, 500, 0));
    REQUIRE(effective((UINT64_C(1) << CAP_SYS_RESOURCE) |
                      (UINT64_C(1) << CAP_SETUID) | (UINT64_C(1) << CAP_SETGID)) == 0);
    struct exec_args args;
    REQUIRE(pipe(args.ready) == 0 && pipe(args.go) == 0);
    void *stack = mmap(NULL, STACK_BYTES, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
    REQUIRE(stack != MAP_FAILED);
    /* The child must open its own proc target before exec. A parent's self
     * FD names that parent permanently, even when inherited by a child. */
    pid_t child = clone(exec_vm_peer, (char *)stack + STACK_BYTES, CLONE_VM | SIGCHLD, &args);
    REQUIRE(child > 0 && byte(args.ready[0], 0));
    REQUIRE(write_adj(fd, 200, 0) && byte(args.go[1], 1));
    REQUIRE(join(child) && read_adj(fd, 200));
    close(fd);
    close(args.ready[0]); close(args.ready[1]); close(args.go[0]); close(args.go[1]);
    return munmap(stack, STACK_BYTES) != 0;
}

static int opened_fd_writer_changes(void) {
    int fd = open_adj(0);
    REQUIRE(fd >= 0 && write_adj(fd, 0, 0));
    REQUIRE(become_user(60001) == 0);
    REQUIRE(write_adj(fd, 500, 0) && write_adj(fd, 0, 0));
    REQUIRE(write_adj(fd, -1, EACCES) && read_adj(fd, 0));
    return close(fd) != 0;
}

static int send_fd(int socket, int fd) {
    char value = 'f', control[CMSG_SPACE(sizeof(int))];
    struct iovec iov = {.iov_base = &value, .iov_len = 1};
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
                            .msg_control = control, .msg_controllen = sizeof(control)};
    memset(control, 0, sizeof(control));
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&message);
    cmsg->cmsg_level = SOL_SOCKET; cmsg->cmsg_type = SCM_RIGHTS;
    cmsg->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(cmsg), &fd, sizeof(fd));
    return sendmsg(socket, &message, 0) == 1;
}

static int receive_fd(int socket) {
    char value, control[CMSG_SPACE(sizeof(int))];
    struct iovec iov = {.iov_base = &value, .iov_len = 1};
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
                            .msg_control = control, .msg_controllen = sizeof(control)};
    if (recvmsg(socket, &message, 0) != 1 || message.msg_flags & (MSG_CTRUNC | MSG_TRUNC)) return -1;
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&message);
    if (!cmsg || cmsg->cmsg_level != SOL_SOCKET || cmsg->cmsg_type != SCM_RIGHTS ||
        cmsg->cmsg_len != CMSG_LEN(sizeof(int)) || CMSG_NXTHDR(&message, cmsg)) return -1;
    int fd;
    memcpy(&fd, CMSG_DATA(cmsg), sizeof(fd));
    return fd;
}

static int transferred_fd_uses_receiver(void) {
    int fd = open_adj(0), sockets[2];
    REQUIRE(fd >= 0 && write_adj(fd, 0, 0));
    REQUIRE(socketpair(AF_UNIX, SOCK_STREAM, 0, sockets) == 0);
    pid_t target = getpid(), child = fork();
    REQUIRE(child >= 0);
    if (!child) {
        close(fd); close(sockets[0]);
        if (become_user(60001)) _exit(41);
        /* A fresh open of the root owner's file must fail DAC. The received
         * already-open FD is a legitimate delegation, not retained authority. */
        errno = 0;
        int fresh = open_adj(target);
        int ok = fresh == -1 && errno == EACCES;
        if (fresh >= 0) close(fresh);
        int received = receive_fd(sockets[1]);
        ok = ok && received >= 0 && write_adj(received, 500, 0) &&
             write_adj(received, 0, 0) && write_adj(received, -1, EACCES);
        if (received >= 0) close(received);
        close(sockets[1]);
        _exit(ok ? 0 : 42);
    }
    close(sockets[1]);
    REQUIRE(send_fd(sockets[0], fd) && join(child) && read_adj(fd, 0));
    close(sockets[0]);
    return close(fd) != 0;
}

static int dac_actor(pid_t target, uid_t uid, int same_owner) {
    pid_t child = fork();
    REQUIRE(child >= 0);
    if (!child) {
        if (become_user(uid)) _exit(41);
        errno = 0;
        int fd = open_adj(target), saved = errno;
        int ok = same_owner ? fd >= 0 && write_adj(fd, 500, 0) && write_adj(fd, 0, 0) &&
                              write_adj(fd, -1, EACCES) : fd == -1 && saved == EACCES;
        if (fd >= 0) close(fd);
        _exit(ok ? 0 : 42);
    }
    return join(child) ? 0 : 1;
}

static int owned_target_dac(void) {
    int ready[2], stop[2];
    REQUIRE(pipe(ready) == 0 && pipe(stop) == 0);
    pid_t target = fork();
    REQUIRE(target >= 0);
    if (!target) {
        close(ready[0]); close(stop[1]);
        int ok = become_user(60001) == 0 && byte(ready[1], 1) && byte(stop[0], 0);
        _exit(ok ? 0 : 42);
    }
    close(ready[1]); close(stop[0]);
    REQUIRE(byte(ready[0], 0));
    int same = dac_actor(target, 60001, 1), stranger = dac_actor(target, 60002, 0);
    REQUIRE(byte(stop[1], 1));
    int reaped = join(target);
    close(ready[0]); close(stop[1]);
    REQUIRE(same == 0 && stranger == 0 && reaped);
    return 0;
}

struct stage { const char *name; int (*run)(void); };
static const struct stage stages[] = {
    {"uid_floor", uid_floor}, {"privileged_floor", privileged_floor},
    {"fork", ordinary_fork}, {"clone_vm_exit", separate_clone_vm},
    {"vfork", independent_vfork}, {"threads", shared_process_threads},
    {"exec", real_exec}, {"clone_vm_exec", clone_vm_exec_detaches},
    {"fd_credential", opened_fd_writer_changes},
    {"fd_transfer", transferred_fd_uses_receiver}, {"owned_dac", owned_target_dac},
};

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    program = argv[0];
    if (argc < 2 || strcmp(argv[1], guard_arg) || !guest_guard()) return 125;
    alarm(35);
    if ((argc == 4 && !strcmp(argv[2], "--exec-check")) ||
        (argc == 6 && !strcmp(argv[2], "--exec-peer"))) {
        char *end;
        long fd = strtol(argv[3], &end, 10);
        if (*end || fd < 0 || fd > 1024) return 125;
        if (argc == 6) {
            stage_name = "clone_vm_exec";
            long ready = strtol(argv[4], &end, 10);
            if (*end || ready < 0 || ready > 1024) return 125;
            long go = strtol(argv[5], &end, 10);
            if (*end || go < 0 || go > 1024) return 125;
            if (!byte((int)ready, 1) || !byte((int)go, 0)) return 42;
            close((int)ready); close((int)go);
        }
        return exec_check((int)fd);
    }
    if (argc != 2) return 125;
    struct __user_cap_data_struct data[2];
    int setup = getuid() == 0 && geteuid() == 0 && !caps(data) &&
                (data[0].effective & (1U << CAP_SYS_RESOURCE)) &&
                prctl(PR_SET_CHILD_SUBREAPER, 1) == 0;
    printf("{\"case\":\"oom.setup\",\"passed\":%s}\n", setup ? "true" : "false");
    if (!setup) return 77;
    int failures = 0;
    for (size_t i = 0; i < sizeof(stages) / sizeof(stages[0]); ++i) {
        stage_name = stages[i].name;
        pid_t child = fork();
        if (child < 0) return 77;
        if (!child) {
            /* Separate process group bounds cleanup after any failed assertion
             * or timeout without addressing unrelated guest processes. */
            if (setpgid(0, 0)) _exit(43);
            alarm(3);
            _exit(stages[i].run() ? 42 : 0);
        }
        int status, waited = waitpid(child, &status, 0) == child;
        int ok = waited && WIFEXITED(status) && WEXITSTATUS(status) == 0;
        /* Reap any owned descendants left by a failed assertion. A nominally
         * successful stage leaving a descendant also fails qualification. */
        kill(-child, SIGKILL);
        int descendants = 0;
        while (waitpid(-child, &status, 0) > 0) ++descendants;
        ok = ok && errno == ECHILD && descendants == 0;
        printf("{\"case\":\"oom.%s\",\"passed\":%s}\n", stages[i].name, ok ? "true" : "false");
        failures += !ok;
    }
    return failures ? 42 : 0;
}
