// SPDX-License-Identifier: MPL-2.0
// Compile once with -static -pthread and reuse the exact ELF on Linux and the guest.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/inotify.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/timerfd.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define LIMIT 32
#define REQUIRE(expression) do { \
    if (!(expression)) { \
        int saved_errno = errno; \
        dprintf(STDERR_FILENO, "NOFILE_ASSERT line=%d expression=%s errno=%d\n", \
                __LINE__, #expression, saved_errno); \
        return __LINE__; \
    } \
} while (0)
#define EXPECT_ERR(expression, expected_errno) do { \
    errno = 0; \
    long result = (expression); \
    REQUIRE(result == -1 && errno == (expected_errno)); \
} while (0)
#define CALL(expression) do { int failed_line = (expression); \
    if (failed_line != 0) return failed_line; \
} while (0)

static int set_soft(rlim_t value)
{
    struct rlimit limit;
    REQUIRE(getrlimit(RLIMIT_NOFILE, &limit) == 0);
    REQUIRE(value <= limit.rlim_max);
    limit.rlim_cur = value;
    REQUIRE(setrlimit(RLIMIT_NOFILE, &limit) == 0);
    REQUIRE(getrlimit(RLIMIT_NOFILE, &limit) == 0 && limit.rlim_cur == value);
    return 0;
}

static int fill_table(int limit)
{
    CALL(set_soft((rlim_t)limit));
    for (int count = 0; count <= limit; ++count) {
        errno = 0;
        int fd = open("/dev/null", O_RDONLY);
        if (fd < 0) {
            REQUIRE(errno == EMFILE);
            return 0;
        }
        REQUIRE(fd < limit);
    }
    REQUIRE(0 && "allocation did not stop at the soft limit");
}

static int open_exhaustion(void)
{
    CALL(fill_table(LIMIT));
    REQUIRE(fcntl(LIMIT - 1, F_GETFD) >= 0);
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    REQUIRE(close(7) == 0);
    REQUIRE(open("/dev/null", O_RDONLY) == 7);
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    return 0;
}

static int lowered_limit_fd_number(void)
{
    CALL(fill_table(64));
    REQUIRE(close(5) == 0);
    CALL(set_soft(16));
    REQUIRE(fcntl(63, F_GETFD) >= 0);
    REQUIRE(dup2(63, 63) == 63);
    REQUIRE(open("/dev/null", O_RDONLY) == 5);
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    EXPECT_ERR(dup2(3, 16), EBADF);
    return 0;
}

static int zero_limit(void)
{
    CALL(set_soft(0));
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    EXPECT_ERR(dup(STDIN_FILENO), EMFILE);
    EXPECT_ERR(socket(AF_UNIX, SOCK_STREAM, 0), EMFILE);
    EXPECT_ERR(fcntl(STDIN_FILENO, F_DUPFD, 0), EINVAL);
    REQUIRE(dup2(STDIN_FILENO, STDIN_FILENO) == STDIN_FILENO);
    CALL(set_soft(LIMIT));
    REQUIRE(open("/dev/null", O_RDONLY) == 3);
    return 0;
}

static int dup_and_fcntl(void)
{
    CALL(fill_table(LIMIT));
    EXPECT_ERR(dup(3), EMFILE);
    EXPECT_ERR(fcntl(3, F_DUPFD, 0), EMFILE);
    EXPECT_ERR(fcntl(3, F_DUPFD_CLOEXEC, 0), EMFILE);
    EXPECT_ERR(fcntl(3, F_DUPFD, LIMIT), EINVAL);
    EXPECT_ERR(fcntl(3, F_DUPFD_CLOEXEC, LIMIT), EINVAL);
    EXPECT_ERR(fcntl(3, F_DUPFD, -1), EINVAL);
    EXPECT_ERR(dup2(3, LIMIT), EBADF);
    EXPECT_ERR(dup3(3, LIMIT, O_CLOEXEC), EBADF);
    REQUIRE(close(9) == 0);
    REQUIRE(dup(3) == 9 && fcntl(9, F_GETFD) == 0);
    REQUIRE(close(9) == 0);
    REQUIRE(fcntl(3, F_DUPFD_CLOEXEC, 8) == 9);
    REQUIRE(fcntl(9, F_GETFD) == FD_CLOEXEC);
    REQUIRE(dup2(3, 9) == 9 && fcntl(9, F_GETFD) == 0);
    REQUIRE(dup3(3, 9, O_CLOEXEC) == 9 && fcntl(9, F_GETFD) == FD_CLOEXEC);
    REQUIRE(close(8) == 0);
    EXPECT_ERR(fcntl(3, F_DUPFD, 10), EMFILE);
    REQUIRE(fcntl(3, F_DUPFD, 8) == 8);
    return 0;
}

static int open_no_side_effects(void)
{
    const char original[] = "preserved";
    char actual[sizeof(original)] = {0};
    struct stat statbuf;
    int file = open("existing", O_CREAT | O_EXCL | O_RDWR, 0600);
    REQUIRE(file >= 0);
    REQUIRE(write(file, original, sizeof(original)) == (ssize_t)sizeof(original));
    CALL(fill_table(LIMIT));
    EXPECT_ERR(open("existing", O_WRONLY | O_TRUNC), EMFILE);
    REQUIRE(fstat(file, &statbuf) == 0 && statbuf.st_size == (off_t)sizeof(original));
    REQUIRE(pread(file, actual, sizeof(actual), 0) == (ssize_t)sizeof(actual));
    REQUIRE(memcmp(actual, original, sizeof(actual)) == 0);
    EXPECT_ERR(open("created", O_CREAT | O_EXCL | O_RDWR, 0600), EMFILE);
    EXPECT_ERR(stat("created", &statbuf), ENOENT);
    EXPECT_ERR(open(".", O_TMPFILE | O_RDONLY, 0600), EINVAL);
    return 0;
}

static int make_pair(int socket_pair, int fds[2])
{
    return socket_pair ? socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, fds)
                       : pipe2(fds, O_CLOEXEC);
}

static int pair_one_slot(int socket_pair)
{
    int fds[2] = {-71, -93};
    CALL(fill_table(LIMIT));
    REQUIRE(close(LIMIT - 1) == 0);
    EXPECT_ERR(make_pair(socket_pair, fds), EMFILE);
    REQUIRE(fds[0] == -71 && fds[1] == -93);
    REQUIRE(open("/dev/null", O_RDONLY) == LIMIT - 1);
    REQUIRE(close(LIMIT - 2) == 0 && close(LIMIT - 1) == 0);
    REQUIRE(make_pair(socket_pair, fds) == 0);
    REQUIRE(fds[0] == LIMIT - 2 && fds[1] == LIMIT - 1);
    REQUIRE(fcntl(fds[0], F_GETFD) == FD_CLOEXEC);
    REQUIRE(fcntl(fds[1], F_GETFD) == FD_CLOEXEC);
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    return 0;
}

static int pipe_one_slot(void) { return pair_one_slot(0); }
static int socketpair_one_slot(void) { return pair_one_slot(1); }

static int pair_copyout_fault(int socket_pair)
{
    CALL(fill_table(LIMIT));
    REQUIRE(close(LIMIT - 2) == 0 && close(LIMIT - 1) == 0);
    if (socket_pair)
        EXPECT_ERR(syscall(SYS_socketpair, AF_UNIX, SOCK_STREAM, 0, 1UL), EFAULT);
    else
        EXPECT_ERR(syscall(SYS_pipe2, 1UL, O_CLOEXEC), EFAULT);
    REQUIRE(open("/dev/null", O_RDONLY) == LIMIT - 2);
    REQUIRE(open("/dev/null", O_RDONLY) == LIMIT - 1);
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    return 0;
}

static int pipe_copyout_fault(void) { return pair_copyout_fault(0); }
static int socketpair_copyout_fault(void) { return pair_copyout_fault(1); }

static void listener_address(struct sockaddr_un *addr)
{
    memset(addr, 0, sizeof(*addr));
    addr->sun_family = AF_UNIX;
    memcpy(addr->sun_path, "listener", sizeof("listener"));
}

static int create_listener(int *result)
{
    struct sockaddr_un addr;
    listener_address(&addr);
    REQUIRE(unlink("listener") == 0 || errno == ENOENT);
    int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    REQUIRE(listener >= 0);
    REQUIRE(bind(listener, (struct sockaddr *)&addr, sizeof(addr)) == 0);
    REQUIRE(listen(listener, 4) == 0);
    *result = listener;
    return 0;
}

static int connect_listener(void)
{
    struct sockaddr_un addr;
    listener_address(&addr);
    int client = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    REQUIRE(client >= 0);
    REQUIRE(connect(client, (struct sockaddr *)&addr, sizeof(addr)) == 0);
    REQUIRE(write(client, "A", 1) == 1);
    return 0;
}

static int accept_preserves_queue(void)
{
    int listener;
    char data = 0;
    CALL(create_listener(&listener));
    CALL(connect_listener());
    CALL(fill_table(LIMIT));
    EXPECT_ERR(accept4(listener, NULL, NULL, SOCK_CLOEXEC), EMFILE);
    REQUIRE(close(LIMIT - 1) == 0);
    int accepted = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
    REQUIRE(accepted == LIMIT - 1);
    REQUIRE(fcntl(accepted, F_GETFD) == FD_CLOEXEC);
    REQUIRE(read(accepted, &data, 1) == 1 && data == 'A');
    return 0;
}

static int accept_copyout_fault(void)
{
    int listener;
    socklen_t size = sizeof(struct sockaddr_un);
    CALL(create_listener(&listener));
    CALL(connect_listener());
    CALL(fill_table(LIMIT));
    REQUIRE(close(LIMIT - 1) == 0);
    EXPECT_ERR(syscall(SYS_accept4, listener, 1UL, &size, SOCK_CLOEXEC), EFAULT);
    REQUIRE(open("/dev/null", O_RDONLY) == LIMIT - 1);
    return 0;
}

static int socket_limit(void)
{
    CALL(fill_table(LIMIT));
    EXPECT_ERR(socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0), EMFILE);
    REQUIRE(close(LIMIT - 1) == 0);
    REQUIRE(socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0) == LIMIT - 1);
    REQUIRE(fcntl(LIMIT - 1, F_GETFD) == FD_CLOEXEC);
    return 0;
}

#define SIMPLE_CREATOR_TEST(name, expression) \
static int name(void) { \
    CALL(fill_table(LIMIT)); \
    EXPECT_ERR((expression), EMFILE); \
    REQUIRE(close(LIMIT - 1) == 0); \
    REQUIRE((expression) == LIMIT - 1); \
    REQUIRE(fcntl(LIMIT - 1, F_GETFD) == FD_CLOEXEC); \
    return 0; \
}

SIMPLE_CREATOR_TEST(eventfd_limit, eventfd(0, EFD_CLOEXEC))
SIMPLE_CREATOR_TEST(timerfd_limit, timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC))
SIMPLE_CREATOR_TEST(epoll_limit, epoll_create1(EPOLL_CLOEXEC))
SIMPLE_CREATOR_TEST(inotify_limit, inotify_init1(IN_CLOEXEC))
SIMPLE_CREATOR_TEST(memfd_limit, memfd_create("nofile-probe", MFD_CLOEXEC))
SIMPLE_CREATOR_TEST(pidfd_open_limit, syscall(SYS_pidfd_open, getpid(), 0))

static int signalfd_limit_and_update(void)
{
    sigset_t mask;
    REQUIRE(sigemptyset(&mask) == 0 && sigaddset(&mask, SIGUSR1) == 0);
    int fd = signalfd(-1, &mask, SFD_CLOEXEC);
    REQUIRE(fd >= 0);
    CALL(fill_table(LIMIT));
    EXPECT_ERR(signalfd(-1, &mask, SFD_CLOEXEC), EMFILE);
    REQUIRE(sigaddset(&mask, SIGUSR2) == 0);
    REQUIRE(signalfd(fd, &mask, 0) == fd);
    REQUIRE(fcntl(fd, F_GETFD) == FD_CLOEXEC);
    REQUIRE(close(LIMIT - 1) == 0);
    REQUIRE(signalfd(-1, &mask, SFD_CLOEXEC) == LIMIT - 1);
    return 0;
}

static int pty_peer_limit(void)
{
    int unlocked = 0;
    int master = open("/dev/ptmx", O_RDWR | O_NOCTTY | O_CLOEXEC);
    REQUIRE(master >= 0);
    REQUIRE(ioctl(master, TIOCSPTLCK, &unlocked) == 0);
    CALL(fill_table(LIMIT));
    EXPECT_ERR(ioctl(master, TIOCGPTPEER, O_RDONLY | O_NOCTTY | O_CLOEXEC), EMFILE);
    REQUIRE(close(LIMIT - 1) == 0);
    REQUIRE(ioctl(master, TIOCGPTPEER, O_RDONLY | O_NOCTTY | O_CLOEXEC) == LIMIT - 1);
    REQUIRE(fcntl(LIMIT - 1, F_GETFD) == FD_CLOEXEC);
    return 0;
}

static double monotonic_time(void)
{
    struct timespec time;
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0)
        return -1.0;
    return (double)time.tv_sec + (double)time.tv_nsec / 1000000000.0;
}

struct competing_state {
    atomic_int start;
    atomic_int done;
    atomic_int release;
};

struct competing_worker {
    struct competing_state *state;
    int fd;
    int error;
};

static void *competing_open(void *argument)
{
    struct competing_worker *worker = argument;
    while (!atomic_load_explicit(&worker->state->start, memory_order_acquire))
        sched_yield();
    worker->fd = open("/dev/null", O_RDONLY);
    worker->error = errno;
    atomic_fetch_add_explicit(&worker->state->done, 1, memory_order_release);
    while (!atomic_load_explicit(&worker->state->release, memory_order_acquire))
        sched_yield();
    if (worker->fd >= 0)
        close(worker->fd);
    return NULL;
}

static int allocators_compete(void)
{
    enum { WORKERS = 6 };
    struct competing_state state = {0};
    struct competing_worker workers[WORKERS] = {0};
    pthread_t threads[WORKERS];
    for (int i = 0; i < WORKERS; ++i) {
        workers[i].state = &state;
        REQUIRE(pthread_create(&threads[i], NULL, competing_open, &workers[i]) == 0);
    }
    CALL(fill_table(LIMIT));
    REQUIRE(close(LIMIT - 2) == 0 && close(LIMIT - 1) == 0);
    double deadline = monotonic_time() + 5.0;
    atomic_store_explicit(&state.start, 1, memory_order_release);
    while (atomic_load_explicit(&state.done, memory_order_acquire) != WORKERS) {
        REQUIRE(monotonic_time() < deadline);
        sched_yield();
    }
    int successes = 0;
    unsigned occupied = 0;
    for (int i = 0; i < WORKERS; ++i) {
        if (workers[i].fd >= 0) {
            REQUIRE(workers[i].fd == LIMIT - 2 || workers[i].fd == LIMIT - 1);
            unsigned bit = 1U << (workers[i].fd - (LIMIT - 2));
            REQUIRE(!(occupied & bit));
            occupied |= bit;
            successes++;
        } else {
            REQUIRE(workers[i].error == EMFILE);
        }
    }
    REQUIRE(successes == 2 && occupied == 3);
    atomic_store_explicit(&state.release, 1, memory_order_release);
    for (int i = 0; i < WORKERS; ++i)
        REQUIRE(pthread_join(threads[i], NULL) == 0);
    return 0;
}

struct blocked_accept_state {
    atomic_int start;
    int listener;
    int accepted;
};

static void *blocked_accept(void *argument)
{
    struct blocked_accept_state *state = argument;
    while (!atomic_load_explicit(&state->start, memory_order_acquire))
        sched_yield();
    state->accepted = accept(state->listener, NULL, NULL);
    return NULL;
}

static int wait_for_reservation(int *reserved_fd)
{
    double deadline = monotonic_time() + 5.0;
    for (;;) {
        // Do not assume accept wins a race for a particular lowest FD. A successful
        // temporary dup2 may make it reserve the next slot instead. Only EBUSY proves
        // that the blocked syscall owns this unpublished slot; no sleep is a barrier.
        for (int fd = 3; fd < LIMIT; ++fd) {
            errno = 0;
            if (fcntl(fd, F_GETFD) >= 0)
                continue;
            REQUIRE(errno == EBADF);
            errno = 0;
            int copied = dup2(STDIN_FILENO, fd);
            if (copied == -1 && errno == EBUSY) {
                *reserved_fd = fd;
                return 0;
            }
            REQUIRE(copied == fd && close(copied) == 0);
        }
        REQUIRE(monotonic_time() < deadline);
        sched_yield();
    }
}

static int reserved_fd_case(int operation)
{
    struct blocked_accept_state state = {.accepted = -1};
    pthread_t thread;
    CALL(create_listener(&state.listener));
    REQUIRE(pthread_create(&thread, NULL, blocked_accept, &state) == 0);
    int target = -1;
    atomic_store_explicit(&state.start, 1, memory_order_release);
    CALL(wait_for_reservation(&target));
    // Keep every earlier number occupied so fork must expose the precise hole left
    // by the omitted parent reservation, independent of the allocation race above.
    for (int fd = 3; fd < target; ++fd)
        if (fcntl(fd, F_GETFD) < 0)
            REQUIRE(errno == EBADF && dup2(STDIN_FILENO, fd) == fd);

    if (operation == 0) {
        EXPECT_ERR(close(target), EBADF);
        EXPECT_ERR(fcntl(target, F_GETFD), EBADF);
        EXPECT_ERR(dup2(STDIN_FILENO, target), EBUSY);
        EXPECT_ERR(dup3(STDIN_FILENO, target, O_CLOEXEC), EBUSY);
    } else if (operation == 1) {
        pid_t child = fork();
        REQUIRE(child >= 0);
        if (child == 0) {
            int fd = open("/dev/null", O_RDONLY);
            _exit(fd == target ? 0 : 1);
        }
        int status;
        REQUIRE(waitpid(child, &status, 0) == child);
        REQUIRE(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    } else {
        REQUIRE(syscall(SYS_close_range, target, target, 4U) == 0);
    }
    CALL(connect_listener());
    REQUIRE(pthread_join(thread, NULL) == 0);
    REQUIRE(state.accepted == target);
    REQUIRE(fcntl(target, F_GETFD) == (operation == 2 ? FD_CLOEXEC : 0));
    return 0;
}

static int reserved_dup2_collision(void) { return reserved_fd_case(0); }
static int fork_ignores_reservation(void) { return reserved_fd_case(1); }
static int cloexec_marks_reservation(void) { return reserved_fd_case(2); }

struct shared_files_state {
    int reports[2];
    int commands[2];
};

static int shared_files_child_first(void)
{
    CALL(set_soft(16));
    REQUIRE(close(9) == 0 && open("/dev/null", O_RDONLY) == 9);
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    REQUIRE(close(63) == 0);
    return 0;
}

static int shared_files_child_second(void)
{
    struct rlimit limit;
    REQUIRE(getrlimit(RLIMIT_NOFILE, &limit) == 0 && limit.rlim_cur == 16);
    REQUIRE(fcntl(63, F_GETFD) >= 0);
    EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    return 0;
}

static int shared_files_child(void *argument)
{
    struct shared_files_state *state = argument;
    int line = shared_files_child_first();
    if (write(state->reports[1], &line, sizeof(line)) != (ssize_t)sizeof(line) || line)
        return 1;
    char command;
    if (read(state->commands[0], &command, 1) != 1)
        return 1;
    line = shared_files_child_second();
    if (write(state->reports[1], &line, sizeof(line)) != (ssize_t)sizeof(line))
        return 1;
    return line ? 1 : 0;
}

static int shared_table_distinct_limits(void)
{
    struct shared_files_state state;
    REQUIRE(pipe(state.reports) == 0 && pipe(state.commands) == 0);
    const size_t stack_size = 1024 * 1024;
    char *stack = mmap(NULL, stack_size, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    REQUIRE(stack != MAP_FAILED);
    CALL(fill_table(64));
    pid_t child = clone(shared_files_child, stack + stack_size, CLONE_FILES | SIGCHLD, &state);
    REQUIRE(child >= 0);
    int line = -1;
    REQUIRE(read(state.reports[0], &line, sizeof(line)) == (ssize_t)sizeof(line));
    REQUIRE(line == 0);
    struct rlimit limit;
    REQUIRE(getrlimit(RLIMIT_NOFILE, &limit) == 0 && limit.rlim_cur == 64);
    REQUIRE(open("/dev/null", O_RDONLY) == 63);
    REQUIRE(write(state.commands[1], "C", 1) == 1);
    REQUIRE(read(state.reports[0], &line, sizeof(line)) == (ssize_t)sizeof(line));
    REQUIRE(line == 0);
    int status;
    REQUIRE(waitpid(child, &status, 0) == child);
    REQUIRE(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    REQUIRE(munmap(stack, stack_size) == 0);
    return 0;
}

static int send_rights(int socket_fd, int source[3])
{
    _Alignas(struct cmsghdr) char control[CMSG_SPACE(3 * sizeof(int))] = {0};
    char payload = 'R';
    struct iovec iov = {.iov_base = &payload, .iov_len = 1};
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
                             .msg_control = control, .msg_controllen = sizeof(control)};
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET;
    header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(3 * sizeof(int));
    memcpy(CMSG_DATA(header), source, 3 * sizeof(int));
    REQUIRE(sendmsg(socket_fd, &message, 0) == 1);
    return 0;
}

static int receive_prefix(int socket_fd, void *control, size_t size, int flags,
                          int expected_fd, int expected_cloexec)
{
    char payload = 0;
    struct iovec iov = {.iov_base = &payload, .iov_len = 1};
    struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
                             .msg_control = control, .msg_controllen = size};
    REQUIRE(recvmsg(socket_fd, &message, flags) == 1 && payload == 'R');
    REQUIRE(message.msg_flags & MSG_CTRUNC);
    REQUIRE(!!(message.msg_flags & MSG_CMSG_CLOEXEC) == !!(flags & MSG_CMSG_CLOEXEC));
    if (expected_fd < 0) {
        REQUIRE(message.msg_controllen == 0 && CMSG_FIRSTHDR(&message) == NULL);
    } else {
        REQUIRE(message.msg_controllen == CMSG_SPACE(sizeof(int)));
        struct cmsghdr header;
        // The deliberate page-boundary case supplies a control buffer aligned to four,
        // not eight, bytes. Copy its header before inspecting it in the C abstract machine.
        memcpy(&header, message.msg_control, sizeof(header));
        REQUIRE(header.cmsg_level == SOL_SOCKET);
        REQUIRE(header.cmsg_type == SCM_RIGHTS && header.cmsg_len == CMSG_LEN(sizeof(int)));
        int fd = -1;
        memcpy(&fd, (char *)message.msg_control + CMSG_LEN(0), sizeof(fd));
        REQUIRE(fd == expected_fd && fcntl(fd, F_GETFD) == expected_cloexec);
        char identity = 0;
        REQUIRE(pread(fd, &identity, 1, 0) == 1 && identity == 'A');
    }
    return 0;
}

static int rights_case(int socket_type, int scenario)
{
    int sockets[2], source[3];
    REQUIRE(socketpair(AF_UNIX, socket_type | SOCK_CLOEXEC, 0, sockets) == 0);
    for (int i = 0; i < 3; ++i) {
        char name[] = "rights0";
        name[6] = (char)('0' + i);
        source[i] = open(name, O_CREAT | O_TRUNC | O_RDWR | O_CLOEXEC, 0600);
        REQUIRE(source[i] >= 0);
        char identity = (char)('A' + i);
        REQUIRE(write(source[i], &identity, 1) == 1);
    }
    CALL(send_rights(sockets[0], source));
    CALL(fill_table(LIMIT));
    _Alignas(struct cmsghdr) char control[CMSG_SPACE(3 * sizeof(int))] = {0};
    if (scenario == 0) {
        CALL(receive_prefix(sockets[1], control, sizeof(control), MSG_CMSG_CLOEXEC, -1, 0));
        EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    } else if (scenario == 1) {
        REQUIRE(close(LIMIT - 1) == 0);
        CALL(receive_prefix(sockets[1], control, sizeof(control), MSG_CMSG_CLOEXEC,
                            LIMIT - 1, FD_CLOEXEC));
        EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
    } else if (scenario == 2) {
        REQUIRE(close(LIMIT - 1) == 0);
        CALL(receive_prefix(sockets[1], control, sizeof(control), MSG_PEEK | MSG_CMSG_CLOEXEC,
                            LIMIT - 1, FD_CLOEXEC));
        REQUIRE(close(LIMIT - 1) == 0);
        memset(control, 0, sizeof(control));
        CALL(receive_prefix(sockets[1], control, sizeof(control), 0, LIMIT - 1, 0));
    } else {
        REQUIRE(close(LIMIT - 2) == 0 && close(LIMIT - 1) == 0);
        long page_size = sysconf(_SC_PAGESIZE);
        REQUIRE(page_size > 0);
        char *pages = mmap(NULL, (size_t)page_size * 2, PROT_READ | PROT_WRITE,
                           MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        REQUIRE(pages != MAP_FAILED);
        REQUIRE(mprotect(pages + page_size, (size_t)page_size, PROT_NONE) == 0);
        void *partial = pages + page_size - CMSG_LEN(sizeof(int));
        CALL(receive_prefix(sockets[1], partial, sizeof(control), MSG_CMSG_CLOEXEC,
                            LIMIT - 2, FD_CLOEXEC));
        REQUIRE(open("/dev/null", O_RDONLY) == LIMIT - 1);
        EXPECT_ERR(open("/dev/null", O_RDONLY), EMFILE);
        REQUIRE(munmap(pages, (size_t)page_size * 2) == 0);
    }
    for (int i = 0; i < 3; ++i)
        REQUIRE(fcntl(source[i], F_GETFD) == FD_CLOEXEC);
    return 0;
}

#define RIGHTS_TEST(name, type, scenario) \
    static int name(void) { return rights_case(type, scenario); }
RIGHTS_TEST(stream_rights_none, SOCK_STREAM, 0)
RIGHTS_TEST(stream_rights_partial, SOCK_STREAM, 1)
RIGHTS_TEST(stream_rights_peek, SOCK_STREAM, 2)
RIGHTS_TEST(stream_rights_copy_fault, SOCK_STREAM, 3)
RIGHTS_TEST(datagram_rights_none, SOCK_DGRAM, 0)
RIGHTS_TEST(datagram_rights_partial, SOCK_DGRAM, 1)
RIGHTS_TEST(datagram_rights_peek, SOCK_DGRAM, 2)
RIGHTS_TEST(datagram_rights_copy_fault, SOCK_DGRAM, 3)
RIGHTS_TEST(seqpacket_rights_none, SOCK_SEQPACKET, 0)
RIGHTS_TEST(seqpacket_rights_partial, SOCK_SEQPACKET, 1)
RIGHTS_TEST(seqpacket_rights_peek, SOCK_SEQPACKET, 2)
RIGHTS_TEST(seqpacket_rights_copy_fault, SOCK_SEQPACKET, 3)

struct test_case { const char *name; int (*run)(void); };
#define CASE(function) {#function, function}
static const struct test_case cases[] = {
    CASE(open_exhaustion), CASE(lowered_limit_fd_number), CASE(zero_limit),
    CASE(dup_and_fcntl), CASE(open_no_side_effects), CASE(pipe_one_slot),
    CASE(socketpair_one_slot), CASE(pipe_copyout_fault), CASE(socketpair_copyout_fault),
    CASE(accept_preserves_queue), CASE(accept_copyout_fault), CASE(socket_limit),
    CASE(eventfd_limit), CASE(timerfd_limit), CASE(epoll_limit), CASE(inotify_limit),
    CASE(memfd_limit), CASE(signalfd_limit_and_update), CASE(pidfd_open_limit),
    CASE(pty_peer_limit), CASE(allocators_compete), CASE(reserved_dup2_collision),
    CASE(fork_ignores_reservation), CASE(cloexec_marks_reservation),
    CASE(shared_table_distinct_limits),
    CASE(stream_rights_none), CASE(stream_rights_partial), CASE(stream_rights_peek),
    CASE(stream_rights_copy_fault), CASE(datagram_rights_none), CASE(datagram_rights_partial),
    CASE(datagram_rights_peek), CASE(datagram_rights_copy_fault), CASE(seqpacket_rights_none),
    CASE(seqpacket_rights_partial), CASE(seqpacket_rights_peek), CASE(seqpacket_rights_copy_fault),
};

int main(void)
{
    alarm(90);
    setvbuf(stdout, NULL, _IONBF, 0);
    // The probe owns only its own process FD table; each case forks a separate limit/table.
    if (syscall(SYS_close_range, 3U, ~0U, 0U) != 0) {
        perror("NOFILE_SETUP close_range");
        return 2;
    }
    char directory[] = "/tmp/a04-nofile-XXXXXX";
    if (mkdtemp(directory) == NULL || chdir(directory) != 0) {
        perror("NOFILE_SETUP directory");
        return 2;
    }
    size_t total = sizeof(cases) / sizeof(cases[0]), passed = 0;
    for (size_t i = 0; i < total; ++i) {
        pid_t child = fork();
        if (child == 0) {
            alarm(12);
            int line = cases[i].run();
            dprintf(STDOUT_FILENO, "NOFILE_CASE name=%s result=%s line=%d\n",
                    cases[i].name, line ? "FAIL" : "PASS", line);
            _exit(line ? 1 : 0);
        }
        int status;
        if (child < 0 || waitpid(child, &status, 0) != child) {
            perror("NOFILE_SETUP fork/wait");
            return 2;
        }
        if (WIFEXITED(status) && WEXITSTATUS(status) == 0)
            passed++;
        else if (!WIFEXITED(status))
            dprintf(STDOUT_FILENO, "NOFILE_CASE name=%s result=FAIL line=0 signal=%d\n",
                    cases[i].name, WTERMSIG(status));
    }
    const char *files[] = {"existing", "created", "listener", "rights0", "rights1", "rights2"};
    for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); ++i)
        if (unlink(files[i]) != 0 && errno != ENOENT) {
            perror("NOFILE_SETUP cleanup");
            return 2;
        }
    if (chdir("/") != 0 || rmdir(directory) != 0) {
        perror("NOFILE_SETUP cleanup directory");
        return 2;
    }
    printf("NOFILE_COMPLETE total=%zu passed=%zu failed=%zu\n", total, passed, total - passed);
    return passed == total ? 0 : 1;
}
