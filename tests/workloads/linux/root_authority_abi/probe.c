// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <inttypes.h>
#include <limits.h>
#include <linux/capability.h>
#include <linux/memfd.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* This is an ABI preflight, never a Hepta writer, issuer or G2 verdict. */
static const unsigned char content[] = "original-root-sealed-bootstrap-abi-v1";
static const int seals = F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL;
static volatile sig_atomic_t owned_child;
static unsigned passed;
static int child_mode;

enum child_proof {
    EXEC_CLOEXEC = 1u << 0,
    RESTRICTED_CREDS = 1u << 1,
    ROOT_PEER = 1u << 2,
    RIGHTS_CLOEXEC = 1u << 3,
    SEALED_MEMFD = 1u << 4,
    ROOT_PIDFD = 1u << 5,
    ROOT_ALIVE = 1u << 6,
    ALL_PROOFS = (1u << 7) - 1,
};

static void cleanup_child(void) {
    pid_t pid = (pid_t)owned_child;
    if (pid > 0) {
        /* This is still our unreaped child, never an adopted numeric PID. */
        (void)kill(pid, SIGKILL);
        while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
        owned_child = 0;
    }
}

static void timeout_handler(int signal_number) {
    (void)signal_number;
    static const char line[] = "ROOT_ABI_TIMEOUT\n";
    ssize_t emitted = write(STDERR_FILENO, line, sizeof(line) - 1);
    (void)emitted;
    if (owned_child > 0) (void)kill((pid_t)owned_child, SIGKILL);
    _exit(124);
}

static void fail(const char *name, int line) {
    int saved = errno;
    dprintf(STDERR_FILENO, "ROOT_ABI_FAIL name=%s line=%d errno=%d child=%d\n", name, line, saved, child_mode);
    if (!child_mode) cleanup_child();
    exit(1);
}

#define MUST(value, name) do { if (!(value)) fail(name, __LINE__); } while (0)

static void record(const char *name) {
    ++passed;
    printf("ROOT_ABI_CASE name=%s passed=1\n", name);
    fflush(stdout);
}

static void write_all(int fd, const void *data, size_t bytes) {
    const unsigned char *cursor = data;
    while (bytes) {
        ssize_t result = write(fd, cursor, bytes);
        if (result < 0 && errno == EINTR) continue;
        MUST(result > 0, "write_all");
        cursor += result;
        bytes -= (size_t)result;
    }
}

static void read_all(int fd, void *data, size_t bytes) {
    unsigned char *cursor = data;
    while (bytes) {
        ssize_t result = read(fd, cursor, bytes);
        if (result < 0 && errno == EINTR) continue;
        MUST(result > 0, "read_all");
        cursor += result;
        bytes -= (size_t)result;
    }
}

static size_t read_text(const char *path, char *text, size_t capacity) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    MUST(fd >= 0, "open_metadata");
    size_t used = 0;
    while (used < capacity - 1) {
        ssize_t result = read(fd, text + used, capacity - 1 - used);
        if (result < 0 && errno == EINTR) continue;
        MUST(result >= 0, "read_metadata");
        if (!result) break;
        used += (size_t)result;
    }
    unsigned char excess;
    MUST(read(fd, &excess, 1) == 0, "bounded_metadata");
    MUST(close(fd) == 0, "close_metadata");
    text[used] = '\0';
    return used;
}

static const char *field(const char *text, const char *name) {
    size_t length = strlen(name);
    for (const char *line = text; line && *line; ) {
        if (strncmp(line, name, length) == 0) return line + length;
        line = strchr(line, '\n');
        if (line) ++line;
    }
    return NULL;
}

static void boot_identity(void) {
    char first[64], second[64];
    MUST(read_text("/proc/sys/kernel/random/boot_id", first, sizeof(first)) == 37, "boot_id_length");
    MUST(read_text("/proc/sys/kernel/random/boot_id", second, sizeof(second)) == 37, "boot_id_second_length");
    MUST(memcmp(first, second, 38) == 0 && first[36] == '\n', "boot_id_stable");
    bool nonzero = false;
    for (unsigned i = 0; i < 36; ++i) {
        if (i == 8 || i == 13 || i == 18 || i == 23) MUST(first[i] == '-', "boot_id_hyphens");
        else {
            MUST((first[i] >= '0' && first[i] <= '9') || (first[i] >= 'a' && first[i] <= 'f'), "boot_id_hex");
            nonzero |= first[i] != '0';
        }
    }
    MUST(nonzero, "boot_id_nonzero");
}

static unsigned long long start_ticks(pid_t pid) {
    char path[64], text[8192];
    MUST(snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid) > 0, "stat_path");
    read_text(path, text, sizeof(text));
    char *end = strrchr(text, ')');
    MUST(end && end[1] == ' ' && end[2] != 'Z' && end[2] != 'X', "live_stat_state");
    char *save = NULL;
    char *word = strtok_r(end + 2, " \n", &save);
    for (unsigned index = 0; index < 19; ++index) {
        MUST(word != NULL, "stat_field_count");
        word = strtok_r(NULL, " \n", &save);
    }
    MUST(word != NULL, "stat_start_field");
    char *tail;
    unsigned long long value = strtoull(word, &tail, 10);
    MUST(*tail == '\0' && value > 0, "stat_start_nonzero");
    return value;
}

static void pidfd_identity(int fd, pid_t expected) {
    char path[64], link[128], text[4096];
    MUST(snprintf(path, sizeof(path), "/proc/self/fd/%d", fd) > 0, "pidfd_link_path");
    ssize_t size = readlink(path, link, sizeof(link) - 1);
    MUST(size > 0 && size < (ssize_t)sizeof(link), "pidfd_readlink");
    link[size] = '\0';
    MUST(strcmp(link, "anon_inode:[pidfd]") == 0, "pidfd_link_identity");
    MUST(snprintf(path, sizeof(path), "/proc/self/fdinfo/%d", fd) > 0, "pidfd_info_path");
    read_text(path, text, sizeof(text));
    const char *value = field(text, "Pid:");
    MUST(value != NULL && strtol(value, NULL, 10) == expected, "pidfd_actual_pid");
}

static void sealed_metadata(int fd) {
    struct stat metadata;
    MUST(fstat(fd, &metadata) == 0, "memfd_fstat");
    MUST(S_ISREG(metadata.st_mode) && metadata.st_uid == 0 && metadata.st_nlink == 0 &&
         (metadata.st_mode & 07777) == 0400 && metadata.st_size == (off_t)sizeof(content), "memfd_sealed_identity");
    int actual = fcntl(fd, F_GET_SEALS);
    MUST(actual >= 0 && (actual & seals) == seals, "memfd_four_seals");
    unsigned char copy[sizeof(content)], extra;
    MUST(lseek(fd, 0, SEEK_SET) == 0, "memfd_rewind");
    read_all(fd, copy, sizeof(copy));
    MUST(memcmp(content, copy, sizeof(copy)) == 0 && read(fd, &extra, 1) == 0, "memfd_exact_readback");
}

static void restricted_credentials(void) {
    uid_t ru, eu, su;
    gid_t rg, eg, sg;
    MUST(getresuid(&ru, &eu, &su) == 0 && ru == 60001 && eu == 60001 && su == 60001, "child_uids");
    MUST(getresgid(&rg, &eg, &sg) == 0 && rg == 60001 && eg == 60001 && sg == 60001, "child_gids");
    MUST(getgroups(0, NULL) == 0 && prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1, "child_groups_nnp");
    char text[16384];
    read_text("/proc/self/status", text, sizeof(text));
    for (unsigned index = 0; index < 2; ++index) {
        const char *values = field(text, index ? "Gid:" : "Uid:");
        unsigned a, b, c, d;
        MUST(values && sscanf(values, "%u %u %u %u", &a, &b, &c, &d) == 4 &&
             a == 60001 && b == 60001 && c == 60001 && d == 60001, "proc_four_ids");
    }
    const char *caps[] = {"CapInh:", "CapPrm:", "CapEff:", "CapBnd:", "CapAmb:"};
    for (unsigned index = 0; index < 5; ++index) {
        const char *value = field(text, caps[index]);
        MUST(value, "proc_cap_field");
        while (*value == ' ' || *value == '\t') ++value;
        MUST(strncmp(value, "0000000000000000\n", 17) == 0, "proc_empty_capability");
    }
    const char *groups = field(text, "Groups:");
    MUST(groups != NULL, "proc_groups_field");
    while (*groups == ' ' || *groups == '\t') ++groups;
    MUST(*groups == '\n', "proc_empty_groups");
    MUST(strstr(text, "\nNoNewPrivs:\t1\n") != NULL, "proc_nnp_exact");
}

static void drop_credentials(void) {
    MUST(setgroups(0, NULL) == 0, "drop_groups");
    MUST(prctl(PR_SET_KEEPCAPS, 0, 0, 0, 0) == 0, "drop_keepcaps");
    MUST(prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) == 0, "drop_ambient");
    unsigned count = 0;
    for (; count < 64; ++count) {
        errno = 0;
        int present = prctl(PR_CAPBSET_READ, count, 0, 0, 0);
        if (present < 0 && errno == EINVAL) break;
        MUST(present >= 0 && prctl(PR_CAPBSET_DROP, count, 0, 0, 0) == 0, "drop_bounding");
    }
    MUST(count > 0 && count < 64, "capability_width");
    MUST(setresgid(60001, 60001, 60001) == 0 && setresuid(60001, 60001, 60001) == 0, "drop_ids");
    struct __user_cap_header_struct header = { .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0 };
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    MUST(syscall(SYS_capset, &header, data) == 0, "drop_capset");
    MUST(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0, "drop_nnp");
}

static int child_entry(int argc, char **argv) {
    MUST(argc == 6, "child_arguments");
    int executable = atoi(argv[3]);
    int stdout_copy = atoi(argv[4]);
    pid_t parent = (pid_t)strtol(argv[5], NULL, 10);
    uint32_t proof = 0;
    errno = 0;
    MUST(fcntl(executable, F_GETFD) < 0 && errno == EBADF, "exec_fd_closed");
    errno = 0;
    MUST(fcntl(stdout_copy, F_GETFD) < 0 && errno == EBADF, "inherited_stdout_copy_closed");
    errno = 0;
    MUST(fcntl(99, F_GETFD) < 0 && errno == EBADF, "close_range_high_fd_closed");
    MUST((fcntl(STDOUT_FILENO, F_GETFD) & FD_CLOEXEC) == 0, "explicit_stdout_preserved");
    proof |= EXEC_CLOEXEC;
    restricted_credentials();
    proof |= RESTRICTED_CREDS;
    int connection = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    MUST(connection >= 0, "child_socket");
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    MUST(strlen(argv[2]) < sizeof(address.sun_path), "child_socket_path");
    strcpy(address.sun_path, argv[2]);
    MUST(connect(connection, (struct sockaddr *)&address, sizeof(address)) == 0, "child_connect");
    struct ucred peer;
    socklen_t length = sizeof(peer);
    MUST(getsockopt(connection, SOL_SOCKET, SO_PEERCRED, &peer, &length) == 0 &&
         length == sizeof(peer) && peer.pid == parent && peer.uid == 0 && peer.gid == 0, "child_root_peer");
    proof |= ROOT_PEER;
    struct pollfd wait = {.fd = connection, .events = POLLIN};
    MUST(poll(&wait, 1, 3000) == 1 && (wait.revents & POLLIN), "child_rights_ready");
    unsigned char byte = 0;
    struct iovec vector = {.iov_base = &byte, .iov_len = 1};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } ancillary = {0};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1,
        .msg_control = ancillary.bytes, .msg_controllen = sizeof(ancillary.bytes)};
    MUST(recvmsg(connection, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC) == 1 && byte == 0x71 &&
         !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)), "child_receive_rights");
    struct cmsghdr *control = CMSG_FIRSTHDR(&message);
    MUST(control && control->cmsg_level == SOL_SOCKET && control->cmsg_type == SCM_RIGHTS &&
         control->cmsg_len == CMSG_LEN(2 * sizeof(int)) && CMSG_NXTHDR(&message, control) == NULL, "child_exact_two_rights");
    int descriptors[2];
    memcpy(descriptors, CMSG_DATA(control), sizeof(descriptors));
    MUST(descriptors[0] != descriptors[1] && (fcntl(descriptors[0], F_GETFD) & FD_CLOEXEC) &&
         (fcntl(descriptors[1], F_GETFD) & FD_CLOEXEC), "child_rights_cloexec");
    proof |= RIGHTS_CLOEXEC;
    sealed_metadata(descriptors[0]);
    proof |= SEALED_MEMFD;
    pidfd_identity(descriptors[1], parent);
    proof |= ROOT_PIDFD;
    struct pollfd root = {.fd = descriptors[1], .events = POLLIN};
    MUST(poll(&root, 1, 0) == 0 && root.revents == 0, "child_root_alive");
    proof |= ROOT_ALIVE;
    write_all(connection, &proof, sizeof(proof));
    /* Parent must kill this live child through the real pidfd. */
    read_all(connection, &byte, 1);
    fail("unexpected_child_release", __LINE__);
    return 1;
}

int main(int argc, char **argv) {
    child_mode = argc > 1 && strcmp(argv[1], "--child") == 0;
    struct sigaction action = {.sa_handler = timeout_handler};
    sigemptyset(&action.sa_mask);
    MUST(sigaction(SIGALRM, &action, NULL) == 0, "alarm_handler");
    alarm(child_mode ? 10 : 20);
    if (child_mode) return child_entry(argc, argv);
    MUST(argc == 1, "arguments");
    MUST(getuid() == 0 && geteuid() == 0 && getgid() == 0 && getegid() == 0, "actual_root_required");
    record("root_actual_ids");
    boot_identity();
    record("boot_identity");
    unsigned long long start = start_ticks(getpid());
    MUST(start_ticks(getpid()) == start, "self_start_stable");
    record("proc_start_identity");
    int executable = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    struct stat held, observed;
    MUST(executable >= 0 && fstat(executable, &held) == 0 && stat("/proc/self/exe", &observed) == 0 &&
         held.st_dev == observed.st_dev && held.st_ino == observed.st_ino && S_ISREG(held.st_mode), "self_exe_identity");
    record("proc_exe_inode");
    char *mounts = malloc(256 * 1024);
    MUST(mounts != NULL, "mountinfo_buffer");
    read_text("/proc/self/mountinfo", mounts, 256 * 1024);
    bool root_mount = false;
    char *line_context = NULL;
    for (char *line = strtok_r(mounts, "\n", &line_context); line; line = strtok_r(NULL, "\n", &line_context)) {
        unsigned id, parent_id;
        char device[64], mounted_root[PATH_MAX], mountpoint[PATH_MAX];
        if (sscanf(line, "%u %u %63s %4095s %4095s", &id, &parent_id, device, mounted_root, mountpoint) == 5 &&
            strcmp(mountpoint, "/") == 0 && strstr(line, " - ") != NULL) root_mount = true;
    }
    free(mounts);
    MUST(root_mount, "mountinfo_root_field");
    record("proc_mountinfo");
    int memory = (int)syscall(SYS_memfd_create, "root-authority-abi", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    struct stat metadata;
    MUST(memory >= 0 && fstat(memory, &metadata) == 0 && S_ISREG(metadata.st_mode) && metadata.st_uid == 0 &&
         metadata.st_nlink == 0 && (fcntl(memory, F_GETFD) & FD_CLOEXEC), "memfd_initial_metadata");
    record("memfd_create_metadata");
    write_all(memory, content, sizeof(content));
    MUST(fchmod(memory, 0400) == 0 && fcntl(memory, F_ADD_SEALS, seals) == 0, "memfd_seal");
    sealed_metadata(memory);
    record("memfd_seal_metadata");
    record("memfd_readback");
    errno = 0;
    MUST(pwrite(memory, content, 1, 0) < 0 && errno == EPERM, "sealed_write_denied");
    record("memfd_write_denied");
    errno = 0;
    MUST(ftruncate(memory, 0) < 0 && errno == EPERM, "sealed_shrink_denied");
    errno = 0;
    MUST(ftruncate(memory, sizeof(content) + 1) < 0 && errno == EPERM, "sealed_grow_denied");
    record("memfd_resize_denied");
    errno = 0;
    MUST(mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, memory, 0) == MAP_FAILED && errno == EPERM,
         "sealed_shared_mapping_denied");
    record("memfd_shared_write_denied");

    char directory[] = "/tmp/root-authority-abi.XXXXXX";
    MUST(mkdtemp(directory) != NULL && chown(directory, 0, 60001) == 0 && chmod(directory, 02710) == 0,
         "private_root_directory");
    char socket_path[sizeof(((struct sockaddr_un *)0)->sun_path)];
    int bytes = snprintf(socket_path, sizeof(socket_path), "%s/launch.sock", directory);
    MUST(bytes > 0 && bytes < (int)sizeof(socket_path), "socket_path");
    int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, socket_path);
    MUST(listener >= 0 && bind(listener, (struct sockaddr *)&address, sizeof(address)) == 0 &&
         chmod(socket_path, 0660) == 0 && listen(listener, 1) == 0, "root_listener");
    MUST(stat(directory, &metadata) == 0 && metadata.st_uid == 0 && metadata.st_gid == 60001 &&
         (metadata.st_mode & 07777) == 02710, "root_directory_identity");
    MUST(lstat(socket_path, &metadata) == 0 && S_ISSOCK(metadata.st_mode) && metadata.st_uid == 0 &&
         metadata.st_gid == 60001 && (metadata.st_mode & 07777) == 0660, "socket_inherits_root_group");
    record("private_socket_directory");
    int root_pidfd = (int)syscall(SYS_pidfd_open, getpid(), 0);
    MUST(root_pidfd >= 0, "root_pidfd_open");
    int stdout_copy = fcntl(STDOUT_FILENO, F_DUPFD_CLOEXEC, 10);
    int stderr_copy = fcntl(STDERR_FILENO, F_DUPFD_CLOEXEC, 10);
    MUST(stdout_copy >= 10 && stderr_copy >= 10 && dup2(memory, 99) == 99, "fixed_child_descriptors");
    char executable_text[32], stdout_text[32], parent_text[32];
    snprintf(executable_text, sizeof(executable_text), "%d", executable);
    snprintf(stdout_text, sizeof(stdout_text), "%d", stdout_copy);
    snprintf(parent_text, sizeof(parent_text), "%ld", (long)getpid());
    char *child_arguments[] = {"root-authority-abi", "--child", socket_path, executable_text, stdout_text, parent_text, NULL};
    char *child_environment[] = {NULL};
    pid_t child = fork();
    MUST(child >= 0, "fork_real_child");
    if (!child) {
        child_mode = 1;
        MUST(syscall(SYS_close_range, 0u, UINT_MAX, 4u) == 0, "child_close_range_cloexec");
        MUST(dup2(stdout_copy, STDOUT_FILENO) == STDOUT_FILENO && dup2(stderr_copy, STDERR_FILENO) == STDERR_FILENO,
             "child_explicit_stdio");
        drop_credentials();
        syscall(SYS_execveat, executable, "", child_arguments, child_environment, AT_EMPTY_PATH);
        fail("execveat_returned", __LINE__);
    }
    owned_child = child;
    MUST(close(stdout_copy) == 0 && close(stderr_copy) == 0 && close(99) == 0, "parent_duplicate_cleanup");
    struct pollfd incoming = {.fd = listener, .events = POLLIN};
    MUST(poll(&incoming, 1, 5000) == 1 && (incoming.revents & POLLIN), "root_child_connect_ready");
    int connection = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
    struct ucred peer;
    socklen_t peer_bytes = sizeof(peer);
    MUST(connection >= 0 && getsockopt(connection, SOL_SOCKET, SO_PEERCRED, &peer, &peer_bytes) == 0 &&
         peer_bytes == sizeof(peer) && peer.pid == child && peer.uid == 60001 && peer.gid == 60001,
         "accepted_original_child_credentials");
    record("child_peer_credentials");
    unsigned char byte = 0x71;
    struct iovec vector = {.iov_base = &byte, .iov_len = 1};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } ancillary = {0};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1,
        .msg_control = ancillary.bytes, .msg_controllen = sizeof(ancillary.bytes)};
    struct cmsghdr *control = CMSG_FIRSTHDR(&message);
    control->cmsg_level = SOL_SOCKET;
    control->cmsg_type = SCM_RIGHTS;
    control->cmsg_len = CMSG_LEN(2 * sizeof(int));
    int descriptors[] = {memory, root_pidfd};
    memcpy(CMSG_DATA(control), descriptors, sizeof(descriptors));
    MUST(sendmsg(connection, &message, MSG_DONTWAIT | MSG_NOSIGNAL) == 1, "send_original_root_rights");
    uint32_t proof;
    read_all(connection, &proof, sizeof(proof));
    MUST(proof == ALL_PROOFS, "complete_original_child_proof");
    record("child_exec_close_range");
    record("child_restricted_credentials");
    record("child_root_peer_credentials");
    record("child_rights_cloexec");
    record("child_sealed_memfd");
    record("child_root_pidfd");
    record("child_root_pidfd_alive");
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0);
    MUST(pidfd >= 0 && (fcntl(pidfd, F_GETFD) & FD_CLOEXEC), "child_pidfd_open");
    pidfd_identity(pidfd, child);
    (void)start_ticks(child);
    record("child_pidfd_identity");
    struct pollfd status = {.fd = pidfd, .events = POLLIN};
    MUST(poll(&status, 1, 0) == 0 && status.revents == 0, "live_pidfd_not_readable");
    const struct timespec immediate = {0};
    MUST(ppoll(&status, 1, &immediate, NULL) == 0 && status.revents == 0, "live_pidfd_ppoll_not_readable");
    record("child_pidfd_alive");
    MUST(syscall(SYS_pidfd_send_signal, pidfd, 0, NULL, 0) == 0, "pidfd_signal_zero");
    record("child_pidfd_zero_signal");
    MUST(syscall(SYS_pidfd_send_signal, pidfd, SIGKILL, NULL, 0) == 0, "pidfd_kill_actual_child");
    const struct timespec exit_timeout = {.tv_sec = 3, .tv_nsec = 0};
    MUST(ppoll(&status, 1, &exit_timeout, NULL) == 1 && (status.revents & POLLIN) &&
         !(status.revents & (POLLERR | POLLNVAL)), "pidfd_exit_wakes_poll");
    record("child_pidfd_exit_ready");
    int exited;
    MUST(waitpid(child, &exited, 0) == child && WIFSIGNALED(exited) && WTERMSIG(exited) == SIGKILL,
         "reap_pidfd_killed_child");
    owned_child = 0;
    record("child_reap_sigkill");
    errno = 0;
    MUST(syscall(SYS_pidfd_send_signal, pidfd, 0, NULL, 0) < 0 && errno == ESRCH, "reaped_pidfd_stays_absent");
    record("child_pidfd_reaped_esrch");
    MUST(close(pidfd) == 0 && close(connection) == 0 && close(root_pidfd) == 0 && close(listener) == 0 &&
         close(memory) == 0 && close(executable) == 0 && unlink(socket_path) == 0 && rmdir(directory) == 0,
         "original_resource_cleanup");
    record("all_resources_released");
    alarm(0);
    printf("ROOT_ABI_SUMMARY passed=%u failed=0 g2_complete=false\n", passed);
    return 0;
}
