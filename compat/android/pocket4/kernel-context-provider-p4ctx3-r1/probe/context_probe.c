/* SPDX-License-Identifier: Apache-2.0
 * Finite, diskless VM controls. Never an Android shim or a host program.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <sys/xattr.h>
#include <netinet/in.h>
#include <time.h>
#include <termios.h>
#include <unistd.h>
#include <linux/android/binder.h>
#include <linux/android/binderfs.h>
#include "p4_lsm_context.h"

#ifndef SCM_SECURITY
#define SCM_SECURITY 3
#endif
#define SELINUX_ID 101U
#define TEST_UID 10001U
#define MARKER "p4-context-provider-8764-diskless-v1"
#define SEL_A "u:r:p4_context_a_t:s0"
#define SEL_B "u:r:p4_context_b_t:s0"
#define SEL_PARENT "u:r:p4_diag_parent_t:s0"
#define AA_A "p4-context-peer-a (enforce)"
#define AA_B "p4-context-peer-b (enforce)"
#ifndef EXPECTED_RELEASE
#define EXPECTED_RELEASE "7.0.14-p4ctx2"
#endif

static int change_pair(char suffix, int aa, int selinux);
static int drop_identity(void);
static int caps_zero(void);
#include "context_binder.h"

static unsigned cases, failures;
static int logger_error;
static int initial_net = -1, selected_net = -1, context_device = -1;
static int inactive_arm;

static void serial_drain(void)
{
    while (tcdrain(STDOUT_FILENO)) {
        if (errno == EINTR) continue;
        logger_error = errno; break;
    }
}

static void report(const char *name, int passed, int error, const char *format, ...)
{
    char detail[4096];
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(detail, sizeof(detail), format, arguments);
    va_end(arguments);
    cases++; failures += !passed;
    printf("P4CTX_CASE {\"name\":"); json_string(name);
    printf(",\"passed\":%s,\"error\":%d,\"detail\":", passed ? "true" : "false", error);
    json_string(detail); printf("}\n");
    serial_drain();
}

static int write_all(int fd, const void *buffer, size_t length)
{
    const unsigned char *p = buffer;
    while (length) {
        ssize_t count = write(fd, p, length);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { if (!count) errno = EIO; return -1; }
        p += count; length -= (size_t)count;
    }
    return 0;
}

static int read_exact(int fd, void *buffer, size_t length, int timeout_ms)
{
    unsigned char *p = buffer;
    long long end = milliseconds() + timeout_ms;
    while (length) {
        int remaining = (int)(end - milliseconds());
        if (remaining <= 0) { errno = ETIMEDOUT; return -1; }
        struct pollfd f = {fd, POLLIN, 0};
        int ready = poll(&f, 1, remaining);
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0) { if (!ready) errno = ETIMEDOUT; return -1; }
        ssize_t count = read(fd, p, length);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { if (!count) errno = EIO; return -1; }
        p += count; length -= (size_t)count;
    }
    return 0;
}

static int write_path(const char *path, const void *buffer, size_t length)
{
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    int result = write_all(fd, buffer, length), saved = errno;
    close(fd); errno = saved; return result;
}

static int change_pair(char suffix, int aa, int selinux)
{
    char command[128], observed[256];
    if (selinux) {
        const char *wanted = suffix == 'a' ? SEL_A : SEL_B;
        if (write_path("/proc-selected/self/attr/current", wanted, strlen(wanted))) return -1;
        read_text("/proc-selected/self/attr/current", observed, sizeof(observed));
        if (strcmp(observed, wanted)) { errno = EPROTO; return -1; }
    }
    if (aa) {
        int length = snprintf(command, sizeof(command), "changeprofile p4-context-peer-%c", suffix);
        if (length <= 0 || (size_t)length + 1 > sizeof(command)) { errno = EINVAL; return -1; }
        if (write_path("/proc/self/attr/apparmor/current", command, (size_t)length + 1)) return -1;
        read_text("/proc/self/attr/apparmor/current", observed, sizeof(observed));
        if (strcmp(observed, suffix == 'a' ? AA_A : AA_B)) { errno = EPROTO; return -1; }
    }
    return 0;
}

static int caps_zero(void)
{
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    if (syscall(SYS_capget, &header, data)) return 0;
    for (unsigned i = 0; i < 2; i++)
        if (data[i].effective || data[i].permitted || data[i].inheritable) return 0;
    for (unsigned i = 0; i <= CAP_LAST_CAP; i++)
        if (prctl(PR_CAPBSET_READ, i, 0, 0, 0) != 0 ||
            prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, i, 0, 0) != 0) return 0;
    return getuid() == TEST_UID && geteuid() == TEST_UID && getgid() == TEST_UID &&
           getegid() == TEST_UID && getgroups(0, NULL) == 0 && prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1;
}

static int drop_identity(void)
{
    for (unsigned i = 0; i <= CAP_LAST_CAP; i++)
        if (prctl(PR_CAPBSET_DROP, i, 0, 0, 0)) return -1;
    if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) ||
        setgroups(0, NULL) || setresgid(TEST_UID, TEST_UID, TEST_UID) ||
        setresuid(TEST_UID, TEST_UID, TEST_UID)) return -1;
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    if (syscall(SYS_capset, &header, data) || prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return -1;
    if (!caps_zero()) { errno = EPROTO; return -1; }
    return 0;
}

static int retire_child(pid_t pid, int pidfd, int kill_first)
{
    if (kill_first && kill(pid, SIGKILL) && errno != ESRCH) return -1;
    int status = 0;
    while (waitpid(pid, &status, 0) < 0) { if (errno != EINTR) return -1; }
    struct pollfd item = {pidfd, POLLIN, 0};
    int retired = poll(&item, 1, 0) > 0;
    close(pidfd);
    if (!retired || (!kill_first && (!WIFEXITED(status) || WEXITSTATUS(status)))) {
        errno = ECHILD; return -1;
    }
    return 0;
}

struct observation {
    int error, values[16], caps;
    char text[6][256];
};

static int worker(void (*function)(struct observation *, int), int argument,
                  struct observation *result)
{
    int channel[2];
    if (pipe2(channel, O_CLOEXEC)) return -1;
    pid_t child = fork();
    if (child < 0) { close(channel[0]); close(channel[1]); return -1; }
    if (!child) {
        close(channel[0]); alarm(9);
        struct observation value = {0};
        function(&value, argument);
        int error = write_all(channel[1], &value, sizeof(value));
        close(channel[1]); _exit(error ? 2 : 0);
    }
    close(channel[1]);
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0);
    if (pidfd < 0) { kill(child, SIGKILL); waitpid(child, NULL, 0); close(channel[0]); return -1; }
    int failed = read_exact(channel[0], result, sizeof(*result), 10000), saved = errno;
    close(channel[0]);
    if (retire_child(child, pidfd, failed != 0) && !failed) { failed = -1; saved = errno; }
    errno = saved; return failed;
}

static struct p4_lsm_netns request_for(int fd, unsigned id)
{
    struct stat info = {0};
    if (fstat(fd, &info)) return (struct p4_lsm_netns){0};
    return (struct p4_lsm_netns){.size = sizeof(struct p4_lsm_netns),
        .version = P4_LSM_CONTEXT_ABI, .netns_fd = fd, .lsm_id = id,
        .expected_ns_inum = info.st_ino};
}

static int context_ioctl(unsigned long command, struct p4_lsm_netns *request)
{
    return ioctl(context_device, command, request) ? errno : 0;
}

/* Child creates one unused netns owned by a new userns. The parent retains
 * its actual nsfs FD while the child is alive, then reaps that exact child. */
static int make_net(int use_socket, int *socket_errno)
{
    int ready[2], command[2];
    if (pipe2(ready, O_CLOEXEC)) return -1;
    if (pipe2(command, O_CLOEXEC)) { close(ready[0]); close(ready[1]); return -1; }
    pid_t child = fork();
    if (child < 0) goto fail_fork;
    if (!child) {
        close(ready[0]); close(command[1]); alarm(6);
        int result[3] = {0, -1, 0};
        if (unshare(CLONE_NEWUSER | CLONE_NEWNET)) result[0] = errno;
        if (!result[0] && use_socket) {
            int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, use_socket == 2 ? 123 : 0);
            result[2] = fd < 0 ? errno : 0;
            if (fd >= 0) close(fd);
            if ((use_socket == 1 && fd < 0) || (use_socket == 2 && fd >= 0)) result[0] = EPROTO;
        }
        if (!result[0]) {
            result[1] = open("/proc/self/ns/net", O_RDONLY | O_CLOEXEC);
            if (result[1] < 0) result[0] = errno;
        }
        if (write_all(ready[1], result, sizeof(result))) _exit(2);
        char done;
        if (read_exact(command[0], &done, 1, 5000)) _exit(3);
        if (result[1] >= 0) close(result[1]);
        _exit(0);
    }
    close(ready[1]); close(command[0]);
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0), fd = -1, result[3] = {0};
    int error = pidfd < 0 ? errno : 0;
    if (!error && read_exact(ready[0], result, sizeof(result), 6500)) error = errno;
    if (!error) error = result[0];
    if (!error) {
        char path[128]; snprintf(path, sizeof(path), "/proc/%ld/fd/%d", (long)child, result[1]);
        fd = open(path, O_RDONLY | O_CLOEXEC);
        if (fd < 0) error = errno;
    }
    if (socket_errno) *socket_errno = result[2];
    if (write_all(command[1], "x", 1) && !error) error = errno;
    close(ready[0]); close(command[1]);
    if (pidfd >= 0) {
        if (retire_child(child, pidfd, error != 0) && !error) error = errno;
    } else { kill(child, SIGKILL); waitpid(child, NULL, 0); }
    if (error) { if (fd >= 0) close(fd); errno = error; return -1; }
    return fd;
fail_fork:
    close(ready[0]); close(ready[1]); close(command[0]); close(command[1]); return -1;
}

static void wrong_userns(struct observation *o, int fd)
{
    if (unshare(CLONE_NEWUSER)) { o->error = errno; return; }
    struct p4_lsm_netns request = request_for(fd, SELINUX_ID);
    o->values[0] = context_ioctl(P4_LSM_NETNS_SET, &request);
}

static void provider_controls(void)
{
    int fd = make_net(0, NULL);
    if (fd < 0) { report("provider_pristine_namespace", 0, errno, "namespace creation failed"); return; }
    struct p4_lsm_netns request = request_for(fd, 0);
    int error = context_ioctl(P4_LSM_NETNS_GET, &request);
    report("provider_pristine_namespace", !error && !request.lsm_id && !request.flags, error,
           "id=%u flags=%u", request.lsm_id, request.flags);
    request = request_for(fd, SELINUX_ID); request.expected_ns_inum++;
    error = context_ioctl(P4_LSM_NETNS_SET, &request);
    report("provider_stale_inode", error == ESTALE, error, "expected ESTALE");
    request = request_for(fd, 104);
    error = context_ioctl(P4_LSM_NETNS_SET, &request);
    report("provider_unknown_id", error == EINVAL, error, "AppArmor ID is outside this original explicit ABI");
    request = request_for(fd, 0);
    error = context_ioctl(P4_LSM_NETNS_SET, &request);
    report("provider_explicit_zero_rejected", error == EINVAL, error, "zero is historical default, not a SET operation");
    request = request_for(fd, SELINUX_ID); request.flags = 1;
    error = context_ioctl(P4_LSM_NETNS_SET, &request);
    report("provider_nonzero_flags", error == EINVAL, error, "flags must be zero");
    request = request_for(initial_net, SELINUX_ID);
    error = context_ioctl(P4_LSM_NETNS_SET, &request);
    report("provider_initial_net_rejected", error == EPERM, error, "initial network namespace remains immutable default");
    struct observation o = {0};
    int failed = worker(wrong_userns, fd, &o);
    report("provider_child_userns_rejected", !failed && !o.error && o.values[0] == EPERM,
           failed ? errno : o.error, "SET errno=%d", o.values[0]);
    request = request_for(fd, SELINUX_ID);
    error = context_ioctl(P4_LSM_NETNS_SET, &request);
    if (inactive_arm) {
        report("provider_inactive_rejected", error == EOPNOTSUPP, error, "no active SELinux provider; no fallback");
        request = request_for(fd, 0);
        int got = context_ioctl(P4_LSM_NETNS_GET, &request);
        report("provider_inactive_state_unchanged", !got && !request.lsm_id && !request.flags, got,
               "id=%u flags=%u", request.lsm_id, request.flags);
        close(fd); return;
    }
    report("provider_initial_set", error == 0, error, "selected SELinux ID 101 on unused child-owned network namespace");
    if (error) { close(fd); return; }
    selected_net = fd;
    request = request_for(fd, 0); error = context_ioctl(P4_LSM_NETNS_GET, &request);
    report("provider_fixed_state", !error && request.lsm_id == SELINUX_ID && request.flags == P4_LSM_NETNS_FIXED,
           error, "id=%u flags=%u", request.lsm_id, request.flags);
    request = request_for(fd, SELINUX_ID); error = context_ioctl(P4_LSM_NETNS_SET, &request);
    report("provider_repeat_rejected", error == EBUSY, error, "first selection remains fixed");
    for (int use = 1; use <= 2; use++) {
        int socket_error = 0, used = make_net(use, &socket_error);
        request = request_for(used, SELINUX_ID);
        error = used < 0 ? errno : context_ioctl(P4_LSM_NETNS_SET, &request);
        struct p4_lsm_netns state = request_for(used, 0);
        int got = used < 0 ? errno : context_ioctl(P4_LSM_NETNS_GET, &state);
        report(use == 1 ? "provider_closed_socket_still_used" : "provider_failed_protocol_still_used",
               used >= 0 && error == EBUSY && !got && !state.lsm_id && state.flags == P4_LSM_NETNS_USED &&
               (use == 1 ? socket_error == 0 : socket_error == EPROTONOSUPPORT), error,
               "create_errno=%d id=%u flags=%u GET_errno=%d", socket_error, state.lsm_id, state.flags, got);
        if (used >= 0) close(used);
    }
    int fresh = make_net(0, NULL), child = -1;
    error = fresh < 0 ? errno : 0;
    if (!error && setns(fresh, CLONE_NEWNET)) error = errno;
    if (!error) { child = make_net(0, NULL); if (child < 0) error = errno; }
    if (setns(initial_net, CLONE_NEWNET) && !error) error = errno;
    request = request_for(fresh, SELINUX_ID);
    int blocked = error ? 0 : context_ioctl(P4_LSM_NETNS_SET, &request);
    report("provider_derivation_fixes_default", !error && blocked == EBUSY, error, "SET after derivation errno=%d", blocked);
    if (fresh >= 0) close(fresh); if (child >= 0) close(child);
    error = setns(selected_net, CLONE_NEWNET) ? errno : 0;
    child = error ? -1 : make_net(0, NULL);
    if (child < 0 && !error) error = errno;
    if (setns(initial_net, CLONE_NEWNET) && !error) error = errno;
    request = request_for(child, 0);
    int got = error ? error : context_ioctl(P4_LSM_NETNS_GET, &request);
    report("provider_child_inherits_fixed", !error && !got && request.lsm_id == SELINUX_ID && request.flags == P4_LSM_NETNS_FIXED,
           error ? error : got, "id=%u flags=%u", request.lsm_id, request.flags);
    if (child >= 0) close(child);
}

static int send_fd(int channel, int fd)
{
    char payload = 'F'; struct iovec vector = {&payload, 1};
    union { struct cmsghdr alignment; unsigned char bytes[CMSG_SPACE(sizeof(int))]; } control = {0};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1,
        .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes)};
    struct cmsghdr *c = CMSG_FIRSTHDR(&message);
    c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(c), &fd, sizeof(fd));
    ssize_t sent = sendmsg(channel, &message, MSG_NOSIGNAL);
    if (sent != 1) { if (sent >= 0) errno = EIO; return -1; }
    return 0;
}

static int receive_fd(int channel)
{
    char payload = 0; struct iovec vector = {&payload, 1};
    union { struct cmsghdr alignment; unsigned char bytes[256]; } control = {0};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1,
        .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes)};
    ssize_t got = recvmsg(channel, &message, MSG_CMSG_CLOEXEC);
    int result = -1, error = 0, count = 0;
    for (struct cmsghdr *c = CMSG_FIRSTHDR(&message); c; c = CMSG_NXTHDR(&message, c)) {
        if (c->cmsg_level != SOL_SOCKET || c->cmsg_type != SCM_RIGHTS || c->cmsg_len < CMSG_LEN(0)) {
            error = EPROTO; continue;
        }
        size_t bytes = c->cmsg_len - CMSG_LEN(0);
        if (bytes % sizeof(int)) error = EPROTO;
        for (size_t offset = 0; offset + sizeof(int) <= bytes; offset += sizeof(int)) {
            int fd; memcpy(&fd, CMSG_DATA(c) + offset, sizeof(fd));
            if (!count++) result = fd; else { close(fd); error = EPROTO; }
        }
    }
    if (got != 1 || payload != 'F' || count != 1 || (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)))
        error = got < 0 ? errno : EPROTO;
    if (error) { if (result >= 0) close(result); errno = error; return -1; }
    return result;
}

static struct {
    int selected, stream, listener, receiver, transport[2];
    ino_t socket_inode;
    char path[108];
} socket_work;

static void socket_receiver(struct observation *o, int unused)
{
    (void)unused;
    close(socket_work.transport[0]);
    if (socket_work.listener >= 0) close(socket_work.listener);
    if (setns(socket_work.selected ? initial_net : selected_net, CLONE_NEWNET) ||
        change_pair('b', 1, 1) || drop_identity()) { o->error = errno; return; }
    int fd = receive_fd(socket_work.transport[1]);
    if (fd < 0) { o->error = errno; return; }
    struct stat status;
    if (fstat(fd, &status) || status.st_ino != socket_work.socket_inode) {
        o->error = errno ? errno : EPROTO; close(fd); return;
    }
    o->caps = caps_zero();
    read_text("/proc/self/attr/apparmor/current", o->text[2], sizeof(o->text[2]));
    read_text("/proc-selected/self/attr/current", o->text[3], sizeof(o->text[3]));
    if (socket_work.stream) {
        char tiny = 0; socklen_t length = 1;
        o->values[2] = getsockopt(fd, SOL_SOCKET, SO_PEERSEC, &tiny, &length) ? errno : 0;
        o->values[3] = (int)length;
        length = sizeof(o->text[4]) - 1;
        if (getsockopt(fd, SOL_SOCKET, SO_PEERSEC, o->text[4], &length) || length >= sizeof(o->text[4])) {
            o->error = errno ? errno : EPROTO; close(fd); return;
        }
        o->text[4][length] = 0;
    }
    for (int index = 0; index < 2; index++) {
        char payload = 0; struct iovec vector = {&payload, 1};
        union { struct cmsghdr alignment; unsigned char bytes[1024]; } control = {0};
        struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1,
            .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes)};
        ssize_t got = recvmsg(fd, &message, MSG_CMSG_CLOEXEC);
        if (got != 1 || payload != 'A' + index || (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) {
            o->error = got < 0 ? errno : EPROTO; break;
        }
        for (struct cmsghdr *c = CMSG_FIRSTHDR(&message); c; c = CMSG_NXTHDR(&message, c)) {
            if (c->cmsg_level != SOL_SOCKET || c->cmsg_type != SCM_SECURITY ||
                c->cmsg_len <= CMSG_LEN(0) || c->cmsg_len > CMSG_LEN(sizeof(o->text[index]))) {
                o->error = EPROTO; break;
            }
            size_t count = c->cmsg_len - CMSG_LEN(0);
            if (o->values[index]++ || count >= sizeof(o->text[index]) ||
                strnlen((char *)CMSG_DATA(c), count) != count - 1) { o->error = EPROTO; break; }
            memcpy(o->text[index], CMSG_DATA(c), count);
        }
        if (o->error) break;
    }
    close(fd); close(socket_work.transport[1]);
}

static void socket_controls(int selected, int stream)
{
    const char *name = selected ? (stream ? "scm_selected_stream_queued_before_accept" : "scm_selected_dgram_queued_identity") :
                                  (stream ? "scm_default_stream_no_fallback" : "scm_default_dgram_no_fallback");
    memset(&socket_work, 0, sizeof(socket_work));
    socket_work.selected = selected; socket_work.stream = stream;
    socket_work.listener = socket_work.receiver = socket_work.transport[0] = socket_work.transport[1] = -1;
    snprintf(socket_work.path, sizeof(socket_work.path), "/p4-context-work/socket-%d-%d", selected, stream);
    int error = 0, ready[2] = {-1, -1}, done[2] = {-1, -1}, pidfd = -1;
    pid_t sender = -1;
    struct observation sent = {0}, received = {0};
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    memcpy(address.sun_path, socket_work.path, strlen(socket_work.path) + 1);
    if (setns(selected ? selected_net : initial_net, CLONE_NEWNET)) { error = errno; goto out; }
    int fd = socket(AF_UNIX, (stream ? SOCK_STREAM : SOCK_DGRAM) | SOCK_CLOEXEC, 0);
    if (fd < 0) { error = errno; goto out; }
    socket_work.receiver = fd;
    int enabled = 1;
    struct timeval timeout = {.tv_sec = 3};
    if (setsockopt(fd, SOL_SOCKET, SO_PASSSEC, &enabled, sizeof(enabled)) ||
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
        bind(fd, (struct sockaddr *)&address, sizeof(address)) || chmod(socket_work.path, 0777) ||
        (stream && listen(fd, 4))) { error = errno; goto out; }
    if (setns(initial_net, CLONE_NEWNET) ||
        socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, socket_work.transport) ||
        pipe2(ready, O_CLOEXEC) || pipe2(done, O_CLOEXEC)) { error = errno; goto out; }
    sender = fork();
    if (sender < 0) { error = errno; goto out; }
    if (!sender) {
        close(ready[0]); close(done[1]); close(socket_work.receiver);
        close(socket_work.transport[0]); close(socket_work.transport[1]);
        alarm(25);
        if (setns(selected ? initial_net : selected_net, CLONE_NEWNET) || change_pair('a', 1, 1)) sent.error = errno;
        int client = sent.error ? -1 : socket(AF_UNIX, (stream ? SOCK_STREAM : SOCK_DGRAM) | SOCK_CLOEXEC, 0);
        if (client < 0 && !sent.error) sent.error = errno;
        if (!sent.error && connect(client, (struct sockaddr *)&address, sizeof(address))) sent.error = errno;
        read_text("/proc-selected/self/attr/current", sent.text[0], sizeof(sent.text[0]));
        read_text("/proc/self/attr/apparmor/current", sent.text[2], sizeof(sent.text[2]));
        if (!sent.error && send(client, "A", 1, MSG_NOSIGNAL) != 1) sent.error = errno ? errno : EIO;
        if (!sent.error && (change_pair('b', 1, 1) || drop_identity())) sent.error = errno;
        read_text("/proc-selected/self/attr/current", sent.text[1], sizeof(sent.text[1]));
        read_text("/proc/self/attr/apparmor/current", sent.text[3], sizeof(sent.text[3]));
        sent.caps = caps_zero();
        if (!sent.error && !stream) {
            close(client); client = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
            if (client < 0 || connect(client, (struct sockaddr *)&address, sizeof(address))) sent.error = errno;
        }
        if (!sent.error && send(client, "B", 1, MSG_NOSIGNAL) != 1) sent.error = errno ? errno : EIO;
        if (write_all(ready[1], &sent, sizeof(sent))) _exit(2);
        char release;
        if (read_exact(done[0], &release, 1, 20000)) _exit(3);
        if (client >= 0) close(client);
        _exit(0);
    }
    close(ready[1]); ready[1] = -1; close(done[0]); done[0] = -1;
    pidfd = (int)syscall(SYS_pidfd_open, sender, 0);
    if (pidfd < 0 || read_exact(ready[0], &sent, sizeof(sent), 10000)) { error = errno; goto out; }
    if (sent.error) { error = sent.error; goto out; }
    /* No accept or receive occurred before the sender confirmed both sends. */
    if (stream) {
        socket_work.listener = socket_work.receiver;
        socket_work.receiver = accept4(socket_work.listener, NULL, NULL, SOCK_CLOEXEC);
        if (socket_work.receiver < 0) { error = errno; goto out; }
    }
    struct stat status;
    if (fstat(socket_work.receiver, &status)) { error = errno; goto out; }
    socket_work.socket_inode = status.st_ino;
    if (send_fd(socket_work.transport[0], socket_work.receiver)) { error = errno; goto out; }
    close(socket_work.receiver); socket_work.receiver = -1;
    if (worker(socket_receiver, 0, &received)) { error = errno; goto out; }
    if (received.error) error = received.error;
out:
    if (setns(initial_net, CLONE_NEWNET) && !error) error = errno;
    if (sender > 0) {
        if (done[1] >= 0 && write_all(done[1], "x", 1) && !error) error = errno;
        if (pidfd >= 0) {
            if (retire_child(sender, pidfd, error != 0) && !error) error = errno;
        } else { kill(sender, SIGKILL); waitpid(sender, NULL, 0); }
    }
    int fds[] = {socket_work.receiver, socket_work.listener, socket_work.transport[0], socket_work.transport[1],
                 ready[0], ready[1], done[0], done[1]};
    for (unsigned i = 0; i < sizeof(fds) / sizeof(fds[0]); i++) if (fds[i] >= 0) close(fds[i]);
    unlink(socket_work.path);
    const char *second = stream ? SEL_A : SEL_B;
    int passed = !error && sent.caps && received.caps && !strcmp(sent.text[0], SEL_A) &&
        !strcmp(sent.text[1], SEL_B) && !strcmp(sent.text[2], AA_A) && !strcmp(sent.text[3], AA_B) &&
        !strcmp(received.text[2], AA_B) && !strcmp(received.text[3], SEL_B);
    if (selected) passed = passed && received.values[0] == 1 && received.values[1] == 1 &&
        !strcmp(received.text[0], SEL_A) && !strcmp(received.text[1], second);
    else passed = passed && received.values[0] == 0 && received.values[1] == 0 &&
        !received.text[0][0] && !received.text[1][0];
    if (stream) passed = passed && received.values[2] == ERANGE && received.values[3] > 1 &&
        !strcmp(received.text[4], selected ? SEL_A : AA_A);
    report(name, passed, error,
           "queue_before_accept=%d; receive_after_SCM_RIGHTS_and_opposite_netns=1; sender=%s -> %s; "
           "SCM=[%s,%s] counts=[%d,%d]; peer=%s; small_peer_errno=%d length=%d; sender_caps_zero=%d receiver_caps_zero=%d",
           stream, sent.text[0], sent.text[1], received.text[0], received.text[1], received.values[0], received.values[1],
           received.text[4], received.values[2], received.values[3], sent.caps, received.caps);
}

static int open_errno(const char *path)
{
    int fd = open(path, O_RDONLY | O_CLOEXEC), error = fd < 0 ? errno : 0;
    if (fd >= 0) close(fd);
    return error;
}

static void enforcement_worker(struct observation *o, int choice)
{
    if (change_pair('a', choice & 1, choice & 2) || drop_identity()) { o->error = errno; return; }
    o->caps = caps_zero();
    o->values[0] = open_errno("/p4-context-work/aa-denied");
    o->values[1] = open_errno("/p4-context-work/selinux-denied");
    read_text("/proc/self/attr/apparmor/current", o->text[0], sizeof(o->text[0]));
    read_text("/proc-selected/self/attr/current", o->text[1], sizeof(o->text[1]));
}

static void enforcement_controls(void)
{
    int aa = open_errno("/p4-context-work/aa-denied"), selinux = open_errno("/p4-context-work/selinux-denied");
    report("combined_enforcement_parent_baseline", !aa && !selinux, aa ? aa : selinux,
           "both sentinel files readable by the setup domain; aa=%d selinux=%d", aa, selinux);
    for (int choice = 1; choice <= 3; choice++) {
        struct observation o = {0};
        int failed = worker(enforcement_worker, choice, &o);
        int passed = !failed && !o.error && o.caps &&
            o.values[0] == ((choice & 1) ? EACCES : 0) && o.values[1] == ((choice & 2) ? EACCES : 0) &&
            !strcmp(o.text[0], (choice & 1) ? AA_A : "unconfined") &&
            !strcmp(o.text[1], (choice & 2) ? SEL_A : SEL_PARENT);
        report(choice == 1 ? "apparmor_distinct_denial" : choice == 2 ? "selinux_distinct_denial" : "combined_enforcement_zero_caps",
               passed, failed ? errno : o.error, "aa=%s selinux=%s aa_open_errno=%d selinux_open_errno=%d caps_zero=%d",
               o.text[0], o.text[1], o.values[0], o.values[1], o.caps);
    }
}

static void proc_controls(void)
{
    char generic[256], selected[256], named[256], held[256] = {0};
    read_text("/proc/self/attr/current", generic, sizeof(generic));
    read_text("/proc-selected/self/attr/current", selected, sizeof(selected));
    read_text("/proc-selected/self/attr/apparmor/current", named, sizeof(named));
    report("proc_explicit_provider_discriminates", !strcmp(generic, "unconfined") &&
           !strcmp(selected, SEL_PARENT) && !strcmp(named, "unconfined"), 0,
           "default=%s selected=%s named_apparmor=%s", generic, selected, named);
    int fd = open("/proc-selected/self/attr/current", O_RDONLY | O_CLOEXEC);
    int error = fd < 0 ? errno : 0;
    int plain = mount(NULL, "/proc-selected", NULL, MS_REMOUNT, NULL) ? errno : 0;
    int same = mount(NULL, "/proc-selected", NULL, MS_REMOUNT, "lsm_context=selinux") ? errno : 0;
    int other = mount(NULL, "/proc-selected", NULL, MS_REMOUNT, "lsm_context=default") ? errno : 0;
    if (fd >= 0) {
        ssize_t count = read(fd, held, sizeof(held) - 1);
        if (count < 0 && !error) error = errno;
        close(fd);
    }
    read_text("/proc-selected/self/attr/current", selected, sizeof(selected));
    report("proc_remount_preserves_open_attr", !error && !plain && !same && other == EBUSY &&
           !strcmp(held, SEL_PARENT) && !strcmp(selected, SEL_PARENT), error,
           "no_option_errno=%d same_errno=%d different_errno=%d held=%s fresh=%s", plain, same, other, held, selected);
}

static void binder_controls_at(const char *root, int selected, int only_parent)
{
    for (int index = 0; index < (only_parent ? 1 : 5); index++) {
        int mode = only_parent ? 0 : (index > 1 ? index - 1 : 0);
        int wants_context = only_parent || index != 0;
        char name[80]; snprintf(name, sizeof(name), "context-%d-%d", selected, index);
        struct case_result value = binder_run_case(root, name, wants_context, mode, selected);
        const char *expected = selected ? (mode == 1 ? SEL_A : mode == 2 ? SEL_B : SEL_PARENT) :
                                         (mode == 1 ? "p4-context-peer-a" : mode == 2 ? "p4-context-peer-b" : "unconfined");
        int passed = !value.server_error && !value.timed_out && value.child_exited && !value.child_status &&
            !value.child.system_errno && !value.child.label_setup_error && value.child.completed &&
            !value.remount_plain_errno && !value.remount_same_errno && value.remount_other_errno == EBUSY;
        if (mode == 3) passed = passed && !value.transaction_received && !value.child.valid_reply &&
            value.child.failed_reply && value.child.extended_error == -EPERM && !value.context_received;
        else passed = passed && value.transaction_received == 1 && value.child.valid_reply && !value.child.failed_reply;
        if (mode != 3 && wants_context) passed = passed && value.context_received && !strcmp(value.context, expected);
        else passed = passed && !value.context_received && !value.context[0];
        if (mode) passed = passed && value.child.caps_zero && value.child.active_uid == TEST_UID &&
            (mode == 3 || value.sender_euid == TEST_UID) &&
            !strcmp(value.child.active_credential, mode == 3 ? AA_A : AA_B) &&
            !strcmp(value.child.active_selinux, mode == 3 ? SEL_A : SEL_B) && value.child.forbidden_open_errno == EACCES &&
            value.child.opened_uid == (mode == 2 ? TEST_UID : 0) &&
            !strcmp(value.child.opened_credential, mode == 1 ? AA_A : AA_B) &&
            !strcmp(value.child.opened_selinux, mode == 1 ? SEL_A : SEL_B);
        const char *kind = only_parent ? "duplicate_initial_option" : index == 0 ? "no_context" : index == 1 ? "parent" : index == 2 ? "saved_opener_a_active_b" : index == 3 ? "fresh_opener_b" : "impersonation_permission_denied";
        char label[128]; snprintf(label, sizeof(label), "binder_%s_%s", selected ? "selected" : "default", kind);
        report(label, passed, value.server_error ? value.server_error : value.child.system_errno,
               "received=%d ctx=%s expected=%s requested=%d; opened_aa=%s opened_selinux=%s opened_uid=%u; "
               "active_aa=%s active_selinux=%s active_uid=%u; caps_zero=%d deny_errno=%d; "
               "held_fd_remount_errno=[%d,%d,%d]; child_status=%d retired=%d timeout=%d reply=%d setup_error=%d failed_reply=%d extended_errno=%d",
               value.transaction_received, value.context, wants_context ? expected : "none", wants_context,
               value.child.opened_credential, value.child.opened_selinux, value.child.opened_uid,
               value.child.active_credential, value.child.active_selinux, value.child.active_uid,
               value.child.caps_zero, value.child.forbidden_open_errno, value.remount_plain_errno,
               value.remount_same_errno, value.remount_other_errno, value.child_status, value.child_exited,
               value.timed_out, value.child.valid_reply, value.child.label_setup_error,
               value.child.failed_reply, value.child.extended_error);
    }
}

#include "context_stream.h"
#include "context_ip.h"

static void ip_negative_controls(void)
{
    for (int selected = 0; selected < 2; selected++) {
        int error = setns(selected ? selected_net : initial_net, CLONE_NEWNET) ? errno : 0;
        int fd = error ? -1 : socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
        if (fd < 0 && !error) error = errno;
        int enabled = 1, observed = 0; socklen_t length = sizeof(observed);
        if (!error && (setsockopt(fd, SOL_IP, IP_PASSSEC, &enabled, sizeof(enabled)) ||
                       getsockopt(fd, SOL_IP, IP_PASSSEC, &observed, &length))) error = errno;
        char payload[16]; unsigned char ancillary[512] = {0};
        struct iovec vector = {payload, sizeof(payload)};
        struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1,
            .msg_control = ancillary, .msg_controllen = sizeof(ancillary)};
        ssize_t received = error ? 0 : recvmsg(fd, &message, MSG_DONTWAIT);
        int receive_error = received < 0 ? errno : 0;
        if (fd >= 0) close(fd);
        if (setns(initial_net, CLONE_NEWNET) && !error) error = errno;
        report(selected ? "ip_passsec_selected_no_network_negative" : "ip_passsec_default_no_network_negative",
               !error && observed == 1 && received == -1 && receive_error == EAGAIN, error,
               "IP_PASSSEC=%d empty_receive_errno=%d; no interfaces enabled, no packets sent; positive IP ancillary path remains outside this finite control",
               observed, receive_error);
    }
}

static int mount_required(const char *source, const char *target, const char *type, const char *options)
{
    if (mkdir(target, 0755) && errno != EEXIST) return -1;
    unsigned long flags = MS_NOSUID | MS_NOEXEC;
    if (strcmp(type, "binder")) flags |= MS_NODEV;
    return mount(source, target, type, flags, options);
}

static int load_policy(const char *source, const char *target, size_t *loaded)
{
    int fd = open(source, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    struct stat info;
    if (fstat(fd, &info) || !S_ISREG(info.st_mode) || info.st_uid || info.st_gid || info.st_nlink != 1 ||
        (info.st_mode & 0222) || info.st_size <= 0 || info.st_size > 512 * 1024) {
        close(fd); errno = EPROTO; return -1;
    }
    unsigned char *bytes = malloc((size_t)info.st_size);
    if (!bytes) { close(fd); return -1; }
    int error = read_exact(fd, bytes, (size_t)info.st_size, 1000) ? errno : 0;
    char extra;
    if (!error && read(fd, &extra, 1) != 0) error = EIO;
    close(fd);
    if (!error) {
        fd = open(target, O_WRONLY | O_CLOEXEC);
        if (fd < 0) error = errno;
        else {
            ssize_t sent = write(fd, bytes, (size_t)info.st_size);
            if (sent != info.st_size) error = sent < 0 ? errno : EIO;
            close(fd);
        }
    }
    free(bytes);
    if (error) { errno = error; return -1; }
    *loaded = (size_t)info.st_size; return 0;
}

static int setup_sentinels(void)
{
    if (mount_required("tmpfs", "/p4-context-work", "tmpfs", "mode=0777,size=4m")) return -1;
    const char *names[] = {"aa-denied", "selinux-denied"};
    const char *labels[] = {"u:object_r:p4_diag_scratch_t:s0", "u:object_r:p4_context_denied_t:s0"};
    for (unsigned i = 0; i < 2; i++) {
        char path[256]; snprintf(path, sizeof(path), "/p4-context-work/%s", names[i]);
        int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
        if (fd < 0) return -1;
        int error = write_all(fd, "finite enforcement sentinel\n", 28) ? errno : 0;
        if (!error && fchmod(fd, 0644)) error = errno;
        if (!error && fsetxattr(fd, "security.selinux", labels[i], strlen(labels[i]) + 1, 0)) error = errno;
        char actual[256] = {0};
        ssize_t length = error ? -1 : fgetxattr(fd, "security.selinux", actual, sizeof(actual));
        if (!error && (length != (ssize_t)strlen(labels[i]) + 1 || strcmp(actual, labels[i]))) error = EPROTO;
        close(fd);
        if (error) { errno = error; return -1; }
    }
    return 0;
}

static void mount_negative_controls(void)
{
    int unknown_proc = mount_required("proc", "/proc-unknown", "proc", "lsm_context=apparmor") ? errno : 0;
    int unknown_binder = mount_required("binder", "/binder-unknown", "binder", "lsm_context=apparmor") ? errno : 0;
    report("mount_unknown_provider_rejected", unknown_proc == EINVAL && unknown_binder == EINVAL, 0,
           "proc_errno=%d binder_errno=%d", unknown_proc, unknown_binder);
    if (!unknown_proc) umount2("/proc-unknown", 0);
    if (!unknown_binder) umount2("/binder-unknown", 0);
    if (inactive_arm) {
        int proc = mount_required("proc", "/proc-selected", "proc", "lsm_context=selinux") ? errno : 0;
        int binder = mount_required("binder", "/binder-selected", "binder", "lsm_context=selinux") ? errno : 0;
        report("mount_inactive_provider_rejected", proc == EOPNOTSUPP && binder == EOPNOTSUPP, 0,
               "proc_errno=%d binder_errno=%d; no default fallback mount", proc, binder);
        if (!proc) umount2("/proc-selected", 0);
        if (!binder) umount2("/binder-selected", 0);
    }
}

int main(void)
{
    static char output_buffer[8192];
    setvbuf(stdout, output_buffer, _IOLBF, sizeof(output_buffer));
    char marker[128];
    if (getpid() != 1 || getuid() != 0 || geteuid() != 0) return 64;
    read_text("/p4-context-marker", marker, sizeof(marker));
    if (strcmp(marker, MARKER)) return 64;
    int setup_error = 0; const char *step = "proc/sysfs";
    signal(SIGPIPE, SIG_IGN);
    if (mount_required("proc", "/proc", "proc", NULL) || mount_required("sysfs", "/sys", "sysfs", NULL)) {
        setup_error = errno; goto finish;
    }
    char vendor[128], product[128], serial[128], arm[64];
    read_text("/sys/class/dmi/id/sys_vendor", vendor, sizeof(vendor));
    read_text("/sys/class/dmi/id/product_name", product, sizeof(product));
    read_text("/sys/class/dmi/id/product_serial", serial, sizeof(serial));
    read_text("/p4-context-arm", arm, sizeof(arm));
    step = "disposable DMI identity";
    if (strcmp(vendor, "Pocket4KernelQualification") || strcmp(product, "P4Context8764Diskless") ||
        strcmp(serial, "p4-context-provider-8764-r1") || (strcmp(arm, "combined") && strcmp(arm, "inactive"))) {
        setup_error = EPERM; goto finish;
    }
    inactive_arm = !strcmp(arm, "inactive");
    step = "devtmpfs/securityfs";
    if (mkdir("/dev", 0755) && errno != EEXIST) { setup_error = errno; goto finish; }
    if (mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, NULL) ||
        mount_required("securityfs", "/sys/kernel/security", "securityfs", NULL)) { setup_error = errno; goto finish; }
    step = "Binder guest module";
    int module = open("/binder_linux.ko", O_RDONLY | O_CLOEXEC);
    if (module < 0) { setup_error = errno; goto finish; }
    if (syscall(SYS_finit_module, module, "", 0)) setup_error = errno;
    close(module); if (setup_error) goto finish;
    step = "AppArmor guest policy";
    size_t aa_bytes = 0, selinux_bytes = 0;
    if (load_policy("/context-apparmor.bin", "/sys/kernel/security/apparmor/.load", &aa_bytes)) { setup_error = errno; goto finish; }
    if (!inactive_arm) {
        step = "SELinux guest policy";
        if (mount_required("selinuxfs", "/sys/fs/selinux", "selinuxfs", NULL) ||
            load_policy("/context-selinux.bin", "/sys/fs/selinux/load", &selinux_bytes)) { setup_error = errno; goto finish; }
    }
    char lsm[512], enforcing[64] = "inactive"; struct utsname uts = {0};
    read_text("/sys/kernel/security/lsm", lsm, sizeof(lsm)); uname(&uts);
    if (!inactive_arm) read_text("/sys/fs/selinux/enforce", enforcing, sizeof(enforcing));
    step = "AppArmor-first enforcing boot";
    char *aa_position = strstr(lsm, "apparmor"), *selinux_position = strstr(lsm, "selinux");
    if (strcmp(uts.release, EXPECTED_RELEASE) || !aa_position ||
        (inactive_arm ? selinux_position != NULL : (!selinux_position || aa_position > selinux_position || strcmp(enforcing, "1")))) {
        setup_error = EPROTO; goto finish;
    }
    printf("P4CTX_BOOT {\"kernel\":"); json_string(uts.release);
    printf(",\"lsm\":"); json_string(lsm); printf(",\"arm\":"); json_string(arm);
    printf(",\"selinux_enforcing\":"); json_string(enforcing);
    printf(",\"apparmor_policy_bytes\":%zu,\"selinux_policy_bytes\":%zu,\"guest_disks\":0,\"guest_nics\":0}\n", aa_bytes, selinux_bytes);
    serial_drain();
    step = "provider device and initial namespace";
    context_device = open("/dev/p4_lsm_context", O_RDWR | O_CLOEXEC);
    initial_net = open("/proc/self/ns/net", O_RDONLY | O_CLOEXEC);
    if (context_device < 0 || initial_net < 0) { setup_error = errno; goto finish; }
    provider_controls();
    mount_negative_controls();
    if (!inactive_arm) {
        step = "explicit procfs/Binder mounts";
        if (mount_required("proc", "/proc-selected", "proc", "lsm_context=selinux") ||
            mount_required("binder", "/binder-selected", "binder", "lsm_context=selinux") ||
            mount_required("binder", "/binder-default", "binder", NULL)) { setup_error = errno; goto finish; }
        step = "sentinel labels";
        if (setup_sentinels()) { setup_error = errno; goto finish; }
        proc_controls();
        enforcement_controls();
        binder_controls_at("/binder-default", 0, 0);
        binder_controls_at("/binder-selected", 1, 0);
        if (selected_net >= 0) {
            socket_controls(1, 1); socket_controls(0, 1);
            socket_controls(1, 0); socket_controls(0, 0);
            ip_negative_controls();
            ip_positive_controls();
            stream_boundary_controls();
        } else report("socket_provider_setup", 0, EPROTO, "explicit network provider was not available");
        step = "duplicate initial mount options";
        int duplicate = mount_required("proc", "/proc-duplicate", "proc", "lsm_context=default,lsm_context=selinux") ? errno : 0;
        char final[256] = {0};
        if (!duplicate) read_text("/proc-duplicate/self/attr/current", final, sizeof(final));
        report("proc_duplicate_initial_last_value", !duplicate && !strcmp(final, SEL_PARENT), duplicate,
               "duplicate initial parameters select final value before publication: %s", final);
        duplicate = mount_required("binder", "/binder-duplicate", "binder", "lsm_context=default,lsm_context=selinux") ? errno : 0;
        if (duplicate) report("binder_selected_duplicate_initial_option", 0, duplicate, "mount failed");
        else binder_controls_at("/binder-duplicate", 1, 1);
    }
finish:
    if (selected_net >= 0) close(selected_net);
    if (initial_net >= 0) close(initial_net);
    if (context_device >= 0) close(context_device);
    char *kernel_log = calloc(1, 256U * 1024U);
    int count = kernel_log ? (int)syscall(SYS_syslog, 3, kernel_log, 256U * 1024U) : -1;
    int log_error = count < 0 ? errno : 0;
    char stdout_label[256] = {0};
    ssize_t label_length = fgetxattr(STDOUT_FILENO, "security.selinux", stdout_label, sizeof(stdout_label) - 1);
    if (label_length < 0) snprintf(stdout_label, sizeof(stdout_label), "ERROR:%d", errno);
    report("guest_kernel_log_capture", count > 0 && count < 256 * 1024, log_error,
           "kernel ring bytes=%d stdout_label=%s tcdrain_errno=%d", count, stdout_label, logger_error);
    if (count > 0) {
        printf("P4CTX_KMSG_BEGIN\n"); serial_drain();
        if (write_all(STDOUT_FILENO, kernel_log, (size_t)count)) logger_error = errno;
        serial_drain(); printf("\nP4CTX_KMSG_END\n"); serial_drain();
    }
    free(kernel_log);
    if (logger_error && !setup_error) { setup_error = logger_error; step = "serial log retirement"; }
    printf("P4CTX_SUMMARY {\"cases\":%u,\"passed\":%u,\"failed\":%u,\"setup_error\":%d,\"setup_step\":",
           cases, cases - failures, failures, setup_error);
    json_string(step); printf(",\"Android_started\":false,\"production_acceptance\":false}\n");
    serial_drain();
    sync(); reboot(RB_POWER_OFF);
    for (;;) pause();
}
