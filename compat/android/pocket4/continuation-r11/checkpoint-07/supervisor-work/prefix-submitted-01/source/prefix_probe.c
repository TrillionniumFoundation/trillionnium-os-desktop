#define _GNU_SOURCE
/* Owned host-prefix probe. This is not Android init or the init constructor. */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum { CONTROL = 198, DOMAIN = 199, OWNER = 200, ENTRY = 201, WIRE = 128, RIGHTS = 12 };
static const char *const ns[] = {
    "pid", "pid_for_children", "mnt", "cgroup", "user", "net", "ipc", "uts", "time", "time_for_children"
};
static volatile sig_atomic_t term;
static void got_term(int signal_number) { (void)signal_number; term = 1; }
static int reject(const char *message) { dprintf(STDERR_FILENO, "prefix-probe: %s\n", message); return 97; }
static int64_t now_ms(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) return -1;
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
static void put64(unsigned char *out, uint64_t value) {
    for (unsigned i = 0; i < 8; ++i) { out[i] = (unsigned char)value; value >>= 8; }
}
static int nonce(unsigned char out[32]) {
    const char *text = getenv("DROIDLOOM_RELAY_ENTRY_NONCE");
    if (!text || strlen(text) != 64) return -1;
    unsigned any = 0;
    for (unsigned i = 0; i < 32; ++i) {
        unsigned value = 0;
        for (unsigned j = 0; j < 2; ++j) {
            unsigned char c = (unsigned char)text[i * 2 + j];
            unsigned n;
            if (c >= '0' && c <= '9') n = c - '0';
            else if (c >= 'a' && c <= 'f') n = c - 'a' + 10;
            else return -1;
            value = (value << 4) | n;
        }
        out[i] = (unsigned char)value; any |= value;
    }
    return any ? 0 : -1;
}
static int owner_alive(void) {
    struct pollfd p = { .fd = OWNER, .events = POLLIN };
    return poll(&p, 1, 0) == 0 && p.revents == 0;
}
static int owner_is_outside_pidfd(void) {
    char path[64], data[4096];
    snprintf(path, sizeof(path), "/proc/self/fdinfo/%d", OWNER);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    ssize_t count = read(fd, data, sizeof(data) - 1); close(fd);
    if (count <= 0 || count == (ssize_t)sizeof(data) - 1) return 0;
    data[count] = 0;
    unsigned matches = 0;
    for (char *line = data; line && *line;) {
        char *next = strchr(line, '\n'); if (next) *next++ = 0;
        if (!strncmp(line, "Pid:\t", 5)) {
            if (strcmp(line + 5, "0")) return 0;
            ++matches;
        }
        line = next;
    }
    return matches == 1;
}
static int send_frame(const unsigned char wire[WIRE], const int *fds, unsigned count) {
    unsigned char ancillary[CMSG_SPACE(RIGHTS * sizeof(int))];
    memset(ancillary, 0, sizeof(ancillary));
    struct iovec io = { .iov_base = (void *)wire, .iov_len = WIRE };
    struct msghdr message = { .msg_iov = &io, .msg_iovlen = 1 };
    if (count) {
        message.msg_control = ancillary; message.msg_controllen = CMSG_SPACE(count * sizeof(int));
        struct cmsghdr *header = CMSG_FIRSTHDR(&message);
        header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
        header->cmsg_len = CMSG_LEN(count * sizeof(int));
        memcpy(CMSG_DATA(header), fds, count * sizeof(int));
    }
    return sendmsg(CONTROL, &message, MSG_NOSIGNAL) == WIRE ? 0 : -1;
}
static int exec_no_capabilities(void) {
    for (int fd = CONTROL; fd <= ENTRY; ++fd) {
        errno = 0;
        if (fcntl(fd, F_GETFD) != -1 || errno != EBADF) return 93;
    }
    return 0;
}
static int check_next_exec(void) {
    pid_t parent = getpid(), child = fork();
    if (child < 0) return -1;
    if (!child) {
        if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) _exit(92);
        char *const args[] = { (char *)"owned-prefix-probe", (char *)"--fd-check", NULL };
        char *const environment[] = { NULL };
        fexecve(ENTRY, args, environment); _exit(91);
    }
    int status = 0, killed = 0;
    int64_t begin = now_ms();
    if (begin < 0) { kill(child, SIGKILL); return -1; }
    for (;;) {
        pid_t done = waitpid(child, &status, WNOHANG);
        if (done == child) return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
        if (done < 0 && errno != EINTR) return -1;
        int64_t now = now_ms();
        if (now < begin || now - begin > 2000) {
            /* This is our exact unreaped child, so its PID cannot be reused. */
            if (!killed) { kill(child, SIGKILL); killed = 1; }
            if (now < begin || now - begin > 3000) return -1;
        }
        struct timespec sleep_for = { .tv_nsec = 1000000 }; nanosleep(&sleep_for, NULL);
    }
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--fd-check")) return exec_no_capabilities();
    if (argc != 4 || strcmp(argv[1], "development-enter") || strcmp(argv[2], "--spec"))
        return reject("unexpected exact production-prefix argument shape");
    if (getuid() || geteuid() || getgid() || getegid() || getpid() != 1 || getppid() != 0)
        return reject("not owned private root PID 1");
    for (int fd = CONTROL; fd <= ENTRY; ++fd) {
        int flags = fcntl(fd, F_GETFD);
        if (flags < 0 || fcntl(fd, F_SETFD, flags | FD_CLOEXEC)) return reject("missing capability FD");
    }
    const char *abi = getenv("DROIDLOOM_RELAY_ENTRY_ABI");
    if (!abi || strcmp(abi, "droidloom-relay-entry-v1")) return reject("entry ABI differs");
    unsigned char frame[WIRE] = {0}; memcpy(frame, "P4PX01!!", 8); put64(frame + 8, 1);
    if (nonce(frame + 16)) return reject("nonce missing or malformed");
    struct sigaction action = { .sa_handler = got_term };
    if (sigemptyset(&action.sa_mask) || sigaction(SIGTERM, &action, NULL)) return reject("TERM handler");
    if (prctl(PR_SET_PDEATHSIG, SIGKILL)) return reject("parent-death arm");
    int death_signal = 0;
    if (prctl(PR_GET_PDEATHSIG, &death_signal) || death_signal != SIGKILL || !owner_alive()
        || !owner_is_outside_pidfd()) return reject("exact outer pidfd/death contract");
    int type = 0; socklen_t size = sizeof(type);
    if (getsockopt(CONTROL, SOL_SOCKET, SO_TYPE, &type, &size) || type != SOCK_SEQPACKET)
        return reject("control channel type");
    struct ucred peer; size = sizeof(peer);
    int flags = fcntl(CONTROL, F_GETFL);
    if (flags < 0 || !(flags & O_NONBLOCK)
        || getsockopt(CONTROL, SOL_SOCKET, SO_PEERCRED, &peer, &size)
        || size != sizeof(peer) || peer.uid || peer.gid || peer.pid < 0)
        return reject("control peer/flags");
    struct stat directory, executable, actual;
    int self_exe = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    if (self_exe < 0 || fstat(DOMAIN, &directory) || fstat(ENTRY, &executable) || fstat(self_exe, &actual))
        return reject("held fixture object metadata");
    close(self_exe);
    if (!S_ISDIR(directory.st_mode) || !S_ISREG(executable.st_mode) || executable.st_dev != actual.st_dev
        || executable.st_ino != actual.st_ino) return reject("entry identity or domain test-directory type");
    put64(frame + 48, (uint64_t)directory.st_dev); put64(frame + 56, directory.st_ino);
    put64(frame + 64, (uint64_t)executable.st_dev); put64(frame + 72, executable.st_ino);
    put64(frame + 80, (uint64_t)death_signal); put64(frame + 88, 1); put64(frame + 96, 0);
    int received[RIGHTS]; for (unsigned i = 0; i < RIGHTS; ++i) received[i] = -1;
    received[0] = (int)syscall(SYS_pidfd_open, getpid(), 0);
    for (unsigned i = 0; i < sizeof(ns) / sizeof(ns[0]); ++i) {
        char path[80]; snprintf(path, sizeof(path), "/proc/self/ns/%s", ns[i]);
        received[i + 1] = open(path, O_RDONLY | O_CLOEXEC);
    }
    /* Return the actual inherited owner capability for independent host
     * comparison. An arbitrary live outside-namespace pidfd is insufficient. */
    received[RIGHTS - 1] = fcntl(OWNER, F_DUPFD_CLOEXEC, 0);
    for (unsigned i = 0; i < RIGHTS; ++i) if (received[i] < 0) return reject("namespace/pidfd acquisition");
    int64_t start = now_ms(); if (start < 0) return reject("monotonic clock");
    put64(frame + 104, (uint64_t)start); put64(frame + 112, 15000);
    if (send_frame(frame, received, RIGHTS)) return reject("HELLO send");
    for (unsigned i = 0; i < RIGHTS; ++i) close(received[i]);
    int executed = 0;
    while (!term) {
        int64_t now = now_ms(); if (now < start || now - start > 15000) return reject("finite command deadline");
        /* After HELLO this probe deliberately has no software owner-death
         * fallback. The outer observer retains the other control endpoint,
         * so only the actual parent-death chain can satisfy its short gate. */
        struct pollfd control = {.fd=CONTROL,.events=POLLIN};
        int ready = poll(&control, 1, 100);
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0 || (control.revents & (POLLHUP|POLLERR|POLLNVAL)))
            return reject("parent/control loss");
        if (!(control.revents & POLLIN)) continue;
        unsigned char command[2];
        ssize_t length = recv(CONTROL, command, sizeof(command), 0);
        if (length != 1) return reject("command framing");
        if (command[0] == 'Q') return 0;
        if (command[0] != 'E' || executed) return reject("command replay/unknown");
        executed = 1;
        if (check_next_exec()) return reject("capability leaked into next exec");
        memset(frame + 48, 0, WIRE - 48); put64(frame + 8, 2);
        if (send_frame(frame, NULL, 0)) return reject("exec check reply");
    }
    return 0;
}
