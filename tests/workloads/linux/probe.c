#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/epoll.h>
#include <sys/file.h>
#include <sys/eventfd.h>
#include <sys/timerfd.h>
#include <sys/resource.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define CHECK(e) do { if (!(e)) { fprintf(stderr, "%s:%d: %s errno=%d (%s)\n", __FILE__, __LINE__, #e, errno, strerror(errno)); return 20; } } while (0)
#define PATHCAP 4096
static char path[PATHCAP];
static int make_path(const char *dir, const char *name) {
    int n = snprintf(path, sizeof path, "%s/%s", dir, name);
    return n > 0 && (size_t)n < sizeof path;
}
static int smoke(const char *dir) {
    CHECK(make_path(dir, "payload.bin"));
    int fd = open(path, O_RDWR | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    CHECK(fd >= 0);
    CHECK(write(fd, "SYNC", 4) == 4);
    CHECK(fsync(fd) == 0);
    char *p = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    CHECK(p != MAP_FAILED);
    p[0] = 'A';
    CHECK(msync(p, 4096, MS_SYNC) == 0);
    CHECK(munmap(p, 4096) == 0);
    CHECK(lseek(fd, 0, SEEK_SET) == 0);
    char buf[4] = {0};
    CHECK(read(fd, buf, 4) == 4 && memcmp(buf, "AYNC", 4) == 0);
    CHECK(close(fd) == 0);
    char oldpath[PATHCAP];
    memcpy(oldpath, path, strlen(path)+1);
    CHECK(make_path(dir, "renamed.bin"));
    CHECK(rename(oldpath, path) == 0);
    int dfd = open(dir, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    CHECK(dfd >= 0 && fsync(dfd) == 0 && close(dfd) == 0);
    CHECK(unlink(path) == 0);
    long page = (long)getauxval(AT_PAGESZ);
    CHECK(page >= 4096 && (page & (page - 1)) == 0);
    puts("{\"ok\":true,\"file_data\":\"AYNC\",\"msync\":true,\"rename_unlink\":true,\"auxv_page_power_of_two\":true}");
    return 0;
}
static _Atomic int gate, ready, finished;
static void *thread_fn(void *unused) {
    (void)unused;
    atomic_fetch_add(&ready, 1);
    while (atomic_load(&gate) == 0) {
        long ret = syscall(SYS_futex, (int*)&gate, FUTEX_WAIT_PRIVATE, 0, NULL, NULL, 0);
        if (ret == -1 && errno != EAGAIN && errno != EINTR) return (void*)(uintptr_t)1;
    }
    atomic_fetch_add(&finished, 1);
    return NULL;
}
static int futex_threads(void) {
    pthread_t threads[4];
    for (size_t i = 0; i < 4; i++) CHECK(pthread_create(&threads[i], NULL, thread_fn, NULL) == 0);
    for (int i = 0; i < 1000 && atomic_load(&ready) != 4; i++) usleep(1000);
    CHECK(atomic_load(&ready) == 4);
    usleep(10000);
    atomic_store(&gate, 1);
    CHECK(syscall(SYS_futex, (int*)&gate, FUTEX_WAKE_PRIVATE, 4, NULL, NULL, 0) >= 0);
    for (size_t i = 0; i < 4; i++) {
        void *ret = (void*)1;
        CHECK(pthread_join(threads[i], &ret) == 0 && ret == NULL);
    }
    CHECK(atomic_load(&finished) == 4);
    errno = 0;
    CHECK(syscall(SYS_futex, (int*)&gate, FUTEX_WAIT_PRIVATE, 0, NULL, NULL, 0) == -1 && errno == EAGAIN);
    puts("{\"ok\":true,\"threads_created\":4,\"threads_joined\":4,\"futex_mismatch_errno\":11}");
    return 0;
}
static int ipc_epoll(void) {
    int pair[2];
    CHECK(socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, pair) == 0);
    int epfd = epoll_create1(EPOLL_CLOEXEC);
    CHECK(epfd >= 0);
    struct epoll_event ev = {.events = EPOLLIN | EPOLLRDHUP, .data.fd = pair[1]};
    CHECK(epoll_ctl(epfd, EPOLL_CTL_ADD, pair[1], &ev) == 0);
    CHECK(write(pair[0], "ping", 4) == 4);
    struct epoll_event events[2];
    CHECK(epoll_wait(epfd, events, 2, 2000) == 1);
    CHECK((events[0].events & EPOLLIN) != 0 && events[0].data.fd == pair[1]);
    char data[4];
    CHECK(read(pair[1], data, 4) == 4 && memcmp(data, "ping", 4) == 0);
    CHECK(shutdown(pair[0], SHUT_WR) == 0);
    CHECK(read(pair[1], data, 4) == 0);
    CHECK(close(epfd) == 0 && close(pair[0]) == 0 && close(pair[1]) == 0);
    errno = 0;
    CHECK(fcntl(pair[0], F_GETFD) == -1 && errno == EBADF);
    puts("{\"ok\":true,\"af_unix\":\"socketpair\",\"epoll\":\"readable\",\"payload\":\"ping\",\"half_close_eof\":true,\"close_errno\":9}");
    return 0;
}
static int lock_test(const char *dir) {
    CHECK(make_path(dir, "locked.bin"));
    int fd = open(path, O_RDWR | O_CREAT | O_TRUNC, 0600);
    CHECK(fd >= 0 && flock(fd, LOCK_EX) == 0);
    struct flock fl = {.l_type=F_WRLCK, .l_whence=SEEK_SET, .l_start=0, .l_len=0};
    CHECK(fcntl(fd, F_SETLK, &fl) == 0);
    int observed[2], permit[2];
    CHECK(pipe(observed) == 0 && pipe(permit) == 0);
    pid_t child = fork();
    CHECK(child >= 0);
    if (child == 0) {
        close(observed[0]); close(permit[1]);
        int fd2 = open(path, O_RDWR);
        if (fd2 < 0) _exit(81);
        errno = 0;
        int b = flock(fd2, LOCK_EX | LOCK_NB);
        int flock_errno = errno;
        errno = 0;
        int f = fcntl(fd2, F_SETLK, &fl);
        int fcntl_errno = errno;
        char status = b == -1 && (flock_errno == EWOULDBLOCK || flock_errno == EAGAIN) && f == -1 && (fcntl_errno == EAGAIN || fcntl_errno == EACCES) ? '1' : '0';
        if (write(observed[1], &status, 1) != 1) _exit(82);
        char go;
        if (read(permit[0], &go, 1) != 1 || go != 'g') _exit(83);
        if (flock(fd2, LOCK_EX | LOCK_NB) != 0) _exit(84);
        if (fcntl(fd2, F_SETLK, &fl) != 0) _exit(85);
        close(fd2); _exit(status == '1' ? 0 : 86);
    }
    close(observed[1]); close(permit[0]);
    char status;
    CHECK(read(observed[0], &status, 1) == 1 && status == '1');
    CHECK(flock(fd, LOCK_UN) == 0);
    fl.l_type = F_UNLCK;
    CHECK(fcntl(fd, F_SETLK, &fl) == 0);
    CHECK(write(permit[1], "g", 1) == 1);
    int st = 0;
    CHECK(waitpid(child, &st, 0) == child && WIFEXITED(st) && WEXITSTATUS(st) == 0);
    CHECK(close(fd) == 0 && close(observed[0]) == 0 && close(permit[1]) == 0);
    CHECK(unlink(path) == 0);
    puts("{\"ok\":true,\"flock_contention\":\"EWOULDBLOCK\",\"fcntl_contention\":\"EACCES_or_EAGAIN\",\"post_release_acquire\":true,\"child_reaped\":true}");
    return 0;
}
static volatile sig_atomic_t received;
static void signal_fn(int n) { if (n == SIGUSR1) received++; }
static int process_test(const char *self) {
    struct sigaction sa = {.sa_handler=signal_fn};
    CHECK(sigemptyset(&sa.sa_mask) == 0 && sigaction(SIGUSR1, &sa, NULL) == 0);
    CHECK(kill(getpid(), SIGUSR1) == 0 && received == 1);
    int expected[2] = {17,23};
    for (int i = 0; i < 2; ++i) {
        pid_t c = fork();
        CHECK(c >= 0);
        if (c == 0) {
            char e[8];
            snprintf(e, sizeof e, "%d", expected[i]);
            execl(self, self, "child", e, (char*)NULL);
            _exit(127);
        }
        int st;
        CHECK(waitpid(c, &st, 0) == c && WIFEXITED(st) && WEXITSTATUS(st) == expected[i]);
    }
    puts("{\"ok\":true,\"signal_delivered\":true,\"fork_exec_wait\":true,\"restarts\":2,\"exit_codes\":[17,23]}");
    return 0;
}
static int errno_test(const char *dir) {
    CHECK(make_path(dir, "does-not-exist"));
    errno = 0;
    CHECK(open(path, O_RDONLY) == -1 && errno == ENOENT);
    CHECK(make_path(dir, "exists"));
    int fd = open(path, O_CREAT | O_EXCL | O_RDWR, 0600);
    CHECK(fd >= 0);
    errno = 0;
    CHECK(open(path, O_CREAT | O_EXCL | O_RDWR, 0600) == -1 && errno == EEXIST);
    CHECK(close(fd) == 0 && unlink(path) == 0);
    errno = 0;
    CHECK(close(-1) == -1 && errno == EBADF);
    puts("{\"ok\":true,\"ENOENT\":2,\"EEXIST\":17,\"EBADF\":9}");
    return 0;
}
static int fd_transfer(const char *dir) {
    CHECK(make_path(dir, "passable.txt"));
    int f = open(path, O_RDWR | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    CHECK(f >= 0 && write(f, "fdpass", 6) == 6 && lseek(f, 0, SEEK_SET) == 0);
    int sv[2];
    CHECK(socketpair(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0, sv) == 0);
    pid_t pid = fork();
    CHECK(pid >= 0);
    if (pid == 0) {
        close(sv[0]); close(f);
        char payload = 0;
        char ancillary[CMSG_SPACE(sizeof(int))] = {0};
        struct iovec io = {.iov_base=&payload, .iov_len=1};
        struct msghdr hdr = {.msg_iov=&io, .msg_iovlen=1,
                             .msg_control=ancillary, .msg_controllen=sizeof ancillary};
        if (recvmsg(sv[1], &hdr, MSG_CMSG_CLOEXEC) != 1 || payload != 'f'
            || (hdr.msg_flags & MSG_CTRUNC)) _exit(81);
        struct cmsghdr *cmsg = CMSG_FIRSTHDR(&hdr);
        if (!cmsg || cmsg->cmsg_level != SOL_SOCKET || cmsg->cmsg_type != SCM_RIGHTS
            || cmsg->cmsg_len != CMSG_LEN(sizeof(int))) _exit(82);
        int received;
        memcpy(&received, CMSG_DATA(cmsg), sizeof received);
        if (!(fcntl(received, F_GETFD) & FD_CLOEXEC)) _exit(83);
        char bytes[6];
        if (read(received, bytes, sizeof bytes) != 6 || memcmp(bytes,"fdpass",6)) _exit(84);
        if (close(received) != 0 || write(sv[1], "ok", 2) != 2) _exit(85);
        close(sv[1]);
        _exit(0);
    }
    close(sv[1]);
    char payload = 'f';
    char ancillary[CMSG_SPACE(sizeof(int))] = {0};
    struct iovec io = {.iov_base=&payload, .iov_len=1};
    struct msghdr hdr = {.msg_iov=&io, .msg_iovlen=1,
                         .msg_control=ancillary, .msg_controllen=sizeof ancillary};
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&hdr);
    CHECK(cmsg != NULL);
    cmsg->cmsg_level = SOL_SOCKET;
    cmsg->cmsg_type = SCM_RIGHTS;
    cmsg->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(cmsg), &f, sizeof f);
    CHECK(sendmsg(sv[0], &hdr, 0) == 1);
    char ack[2];
    CHECK(recv(sv[0], ack, sizeof ack, 0) == 2 && memcmp(ack,"ok",2) == 0);
    CHECK(lseek(f, 0, SEEK_CUR) == 6); /* shared open-file description */
    int status;
    CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(close(sv[0]) == 0 && close(f) == 0 && unlink(path) == 0);
    puts("{\"ok\":true,\"scm_rights\":true,\"recv_cloexec\":true,\"shared_offset\":true,\"child_reaped\":true}");
    return 0;
}
/* A readable level-triggered timerfd must lose readiness after settime/read.
 * This runs in both frozen full32 ELFs, including the ordinary product guest. */
static int timerfd_level_readiness(void) {
    int tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
    CHECK(tfd >= 0);
    int epfd = epoll_create1(EPOLL_CLOEXEC);
    CHECK(epfd >= 0);
    struct epoll_event ev = {.events=EPOLLIN, .data.fd=tfd}, ready;
    CHECK(epoll_ctl(epfd, EPOLL_CTL_ADD, tfd, &ev) == 0);
    const struct itimerspec short_timer = {.it_value={.tv_nsec=10000000}};
    const struct itimerspec long_timer = {.it_value={.tv_sec=60}};
    const struct itimerspec disarmed = {0};
    uint64_t ticks = 0;

    CHECK(timerfd_settime(tfd, 0, &short_timer, NULL) == 0);
    CHECK(epoll_wait(epfd, &ready, 1, 2000) == 1 && ready.data.fd == tfd);
    CHECK(timerfd_settime(tfd, 0, &disarmed, NULL) == 0);
    CHECK(epoll_wait(epfd, &ready, 1, 0) == 0);
    errno = 0;
    CHECK(read(tfd, &ticks, sizeof ticks) == -1 && errno == EAGAIN);

    CHECK(timerfd_settime(tfd, 0, &short_timer, NULL) == 0);
    CHECK(epoll_wait(epfd, &ready, 1, 2000) == 1 && ready.data.fd == tfd);
    CHECK(read(tfd, &ticks, sizeof ticks) == sizeof ticks && ticks == 1);
    CHECK(epoll_wait(epfd, &ready, 1, 0) == 0);

    CHECK(timerfd_settime(tfd, 0, &short_timer, NULL) == 0);
    CHECK(epoll_wait(epfd, &ready, 1, 2000) == 1 && ready.data.fd == tfd);
    /* Give the scheduler ample time before the new expiry when observing
     * cleared readiness; then require a fresh short timeout to become ready. */
    CHECK(timerfd_settime(tfd, 0, &long_timer, NULL) == 0);
    CHECK(epoll_wait(epfd, &ready, 1, 0) == 0);
    errno = 0;
    CHECK(read(tfd, &ticks, sizeof ticks) == -1 && errno == EAGAIN);
    CHECK(timerfd_settime(tfd, 0, &short_timer, NULL) == 0);
    CHECK(epoll_wait(epfd, &ready, 1, 2000) == 1 && ready.data.fd == tfd);
    CHECK(read(tfd, &ticks, sizeof ticks) == sizeof ticks && ticks == 1);
    CHECK(epoll_wait(epfd, &ready, 1, 0) == 0);
    CHECK(close(epfd) == 0 && close(tfd) == 0);
    return 0;
}
static int async_fd(void) {
    CHECK(timerfd_level_readiness() == 0);
    int evfd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
    CHECK(evfd >= 0);
    int tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
    CHECK(tfd >= 0);
    int epfd = epoll_create1(EPOLL_CLOEXEC);
    CHECK(epfd >= 0);
    struct epoll_event ev = {.events=EPOLLIN | EPOLLET, .data.u32=1};
    CHECK(epoll_ctl(epfd, EPOLL_CTL_ADD, evfd, &ev) == 0);
    ev.data.u32=2;
    CHECK(epoll_ctl(epfd, EPOLL_CTL_ADD, tfd, &ev) == 0);
    uint64_t one=1, value=0;
    CHECK(write(evfd, &one, sizeof one) == sizeof one);
    struct itimerspec timer = {.it_value={.tv_sec=0, .tv_nsec=10000000}};
    CHECK(timerfd_settime(tfd, 0, &timer, NULL) == 0);
    int seen_event=0, seen_timer=0;
    for (int attempt=0; attempt<4 && (!seen_event || !seen_timer); ++attempt) {
        struct epoll_event ready[2];
        int n=epoll_wait(epfd, ready, 2, 2000);
        CHECK(n >= 1);
        for (int i=0; i<n; i++) {
            if (ready[i].data.u32 == 1) {
                CHECK(read(evfd, &value, sizeof value) == sizeof value && value == 1);
                seen_event=1;
            } else if (ready[i].data.u32 == 2) {
                CHECK(read(tfd, &value, sizeof value) == sizeof value && value == 1);
                seen_timer=1;
            } else return 20;
        }
    }
    CHECK(seen_event && seen_timer);
    errno=0;
    CHECK(read(evfd, &value, sizeof value) == -1 && errno == EAGAIN);
    CHECK(close(epfd) == 0 && close(tfd) == 0 && close(evfd) == 0);
    puts("{\"ok\":true,\"eventfd\":true,\"timerfd\":true,\"epoll_edge\":true,\"empty_eventfd_errno\":11}");
    return 0;
}
static int mmap_cow(const char *dir) {
    CHECK(make_path(dir,"cow.bin"));
    int fd=open(path,O_RDWR | O_CREAT | O_TRUNC | O_CLOEXEC,0600);
    CHECK(fd >= 0);
    CHECK(ftruncate(fd,4096) == 0 && pwrite(fd,"BASE",4,0) == 4);
    char *priv=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE,fd,0);
    CHECK(priv != MAP_FAILED && memcmp(priv,"BASE",4) == 0);
    priv[0]='X';
    CHECK(msync(priv,4096,MS_SYNC) == 0);
    char value[4];
    CHECK(pread(fd,value,4,0) == 4 && memcmp(value,"BASE",4) == 0);
    char *shared=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    CHECK(shared != MAP_FAILED);
    shared[0]='S';
    CHECK(msync(shared,4096,MS_SYNC) == 0);
    CHECK(pread(fd,value,4,0) == 4 && memcmp(value,"SASE",4) == 0);
    CHECK(priv[0] == 'X');
    CHECK(munmap(shared,4096) == 0 && munmap(priv,4096) == 0);
    CHECK(fsync(fd) == 0 && close(fd) == 0 && unlink(path) == 0);
    puts("{\"ok\":true,\"private_cow\":true,\"shared_msync\":true,\"mapping_released\":true}");
    return 0;
}
static int cloexec_fork_exec(const char *dir, const char *self) {
    CHECK(make_path(dir,"exec-fds.txt"));
    int clo=open(path,O_RDWR|O_CREAT|O_TRUNC|O_CLOEXEC,0600);
    CHECK(clo >= 0);
    int inherited=open(path,O_RDONLY);
    CHECK(inherited >= 0);
    CHECK((fcntl(clo,F_GETFD)&FD_CLOEXEC) != 0);
    CHECK((fcntl(inherited,F_GETFD)&FD_CLOEXEC) == 0);
    pid_t pid=fork();
    CHECK(pid >= 0);
    if (pid == 0) {
        char e1[16],e2[16];
        snprintf(e1,sizeof e1,"%d",clo);
        snprintf(e2,sizeof e2,"%d",inherited);
        execl(self,self,"child_fds",e1,e2,(char*)NULL);
        _exit(127);
    }
    int status;
    CHECK(waitpid(pid,&status,0)==pid && WIFEXITED(status) && WEXITSTATUS(status)==0);
    CHECK(close(clo)==0 && close(inherited)==0 && unlink(path)==0);
    puts("{\"ok\":true,\"cloexec_closed_on_exec\":true,\"plain_fd_inherited\":true,\"wait_reaped\":true}");
    return 0;
}
static int fd_limit(const char *dir) {
    CHECK(make_path(dir,"limits.txt"));
    int initial = open(path, O_CREAT|O_RDWR|O_TRUNC, 0600);
    CHECK(initial >= 0 && close(initial) == 0);
    pid_t pid = fork();
    CHECK(pid >= 0);
    if (pid == 0) {
        struct rlimit lim;
        if (getrlimit(RLIMIT_NOFILE, &lim) != 0) _exit(81);
        if (lim.rlim_cur > 32) lim.rlim_cur=32;
        if (setrlimit(RLIMIT_NOFILE, &lim) != 0) _exit(82);
        int held[256], n=0, last_errno=0;
        while (n < 256) {
            int fd=open(path,O_RDONLY);
            if (fd < 0) { last_errno=errno; break; }
            held[n++]=fd;
        }
        for (int i=0; i<n; ++i) close(held[i]);
        _exit(last_errno==EMFILE ? 0 : 83);
    }
    int status;
    CHECK(waitpid(pid,&status,0)==pid && WIFEXITED(status) && WEXITSTATUS(status)==0);
    CHECK(unlink(path)==0);
    puts("{\"ok\":true,\"emfile_errno\":24,\"child_reaped\":true,\"parent_rlimit_unchanged\":true}");
    return 0;
}
/* Local IPC is a real filesystem/credentials ABI, not a socketpair alias. */
static int uds_path_peercred(const char *dir) {
    CHECK(make_path(dir, "a04-ipc.sock"));
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    CHECK(strlen(path) < sizeof(addr.sun_path));
    strcpy(addr.sun_path, path);
    int listen_fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    CHECK(listen_fd >= 0);
    CHECK(bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) == 0);
    CHECK(listen(listen_fd, 1) == 0);
    pid_t child = fork();
    CHECK(child >= 0);
    if (child == 0) {
        close(listen_fd);
        int sock = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
        if (sock < 0 || connect(sock, (struct sockaddr *)&addr, sizeof(addr)) != 0) _exit(81);
        if (write(sock, "PING", 4) != 4 || shutdown(sock, SHUT_WR) != 0) _exit(82);
        char answer[2];
        if (read(sock, answer, sizeof answer) != 2 || memcmp(answer, "OK", 2)) _exit(83);
        if (close(sock) != 0) _exit(84);
        _exit(0);
    }
    int peer = accept4(listen_fd, NULL, NULL, SOCK_CLOEXEC);
    CHECK(peer >= 0 && (fcntl(peer, F_GETFD) & FD_CLOEXEC));
    struct ucred credentials = {0};
    socklen_t credentials_len = sizeof(credentials);
    CHECK(getsockopt(peer, SOL_SOCKET, SO_PEERCRED, &credentials, &credentials_len) == 0);
    CHECK(credentials_len == sizeof(credentials) && credentials.pid == child &&
          credentials.uid == getuid() && credentials.gid == getgid());
    char message[4];
    CHECK(read(peer, message, sizeof message) == 4 && !memcmp(message, "PING", 4));
    CHECK(read(peer, message, sizeof message) == 0);
    CHECK(write(peer, "OK", 2) == 2);
    CHECK(close(peer) == 0 && close(listen_fd) == 0);
    CHECK(unlink(path) == 0);
    int status;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    errno = 0;
    CHECK(access(path, F_OK) == -1 && errno == ENOENT);
    puts("{\"ok\":true,\"unix_pathname\":true,\"so_peercred\":true,\"accept4_cloexec\":true,\"socket_unlinked\":true,\"child_reaped\":true}");
    return 0;
}

/* Cross-process robust futex owner death and recovery for Hepta mutex owners. */
static int robust_owner_death(void) {
    pthread_mutex_t *mutex = mmap(NULL, sizeof(*mutex), PROT_READ | PROT_WRITE,
                                  MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    CHECK(mutex != MAP_FAILED);
    pthread_mutexattr_t attributes;
    CHECK(pthread_mutexattr_init(&attributes) == 0);
    CHECK(pthread_mutexattr_setpshared(&attributes, PTHREAD_PROCESS_SHARED) == 0);
    CHECK(pthread_mutexattr_setrobust(&attributes, PTHREAD_MUTEX_ROBUST) == 0);
    CHECK(pthread_mutex_init(mutex, &attributes) == 0);
    CHECK(pthread_mutexattr_destroy(&attributes) == 0);
    pid_t child = fork();
    CHECK(child >= 0);
    if (child == 0) {
        if (pthread_mutex_lock(mutex) != 0) _exit(81);
        _exit(0); /* deliberate unclean owner exit: robust-futex contract */
    }
    int status;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    struct timespec deadline;
    CHECK(clock_gettime(CLOCK_REALTIME, &deadline) == 0);
    deadline.tv_sec += 3;
    int acquired = pthread_mutex_timedlock(mutex, &deadline);
    CHECK(acquired == EOWNERDEAD);
    CHECK(pthread_mutex_consistent(mutex) == 0);
    CHECK(pthread_mutex_unlock(mutex) == 0);
    CHECK(pthread_mutex_lock(mutex) == 0);
    CHECK(pthread_mutex_unlock(mutex) == 0);
    CHECK(pthread_mutex_destroy(mutex) == 0);
    CHECK(munmap(mutex, sizeof(*mutex)) == 0);
    puts("{\"ok\":true,\"robust_futex_owner_death\":true,\"recovered_with_consistent\":true,\"mutex_reused\":true,\"child_reaped\":true}");
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 4 && strcmp(argv[1], "child_fds") == 0) {
        int clo=atoi(argv[2]), plain=atoi(argv[3]);
        errno=0;
        if (fcntl(clo, F_GETFD) != -1 || errno != EBADF) return 70;
        if (fcntl(plain, F_GETFD) < 0) return 71;
        return 0;
    }
    if (argc == 3 && strcmp(argv[1], "child") == 0) {
        int e = atoi(argv[2]);
        return e > 0 && e < 126 ? e : 127;
    }
    if (argc != 3) {
        fprintf(stderr, "usage: %s CASE SCRATCH_DIR\n", argv[0]);
        return 64;
    }
    if (!strcmp(argv[1], "smoke")) return smoke(argv[2]);
    if (!strcmp(argv[1], "threads_futex")) return futex_threads();
    if (!strcmp(argv[1], "ipc_epoll")) return ipc_epoll();
    if (!strcmp(argv[1], "file_lock")) return lock_test(argv[2]);
    if (!strcmp(argv[1], "process")) return process_test(argv[0]);
    if (!strcmp(argv[1], "errno")) return errno_test(argv[2]);
    if (!strcmp(argv[1], "scm_rights")) return fd_transfer(argv[2]);
    if (!strcmp(argv[1], "async_fd")) return async_fd();
    if (!strcmp(argv[1], "mmap_cow")) return mmap_cow(argv[2]);
    if (!strcmp(argv[1], "cloexec")) return cloexec_fork_exec(argv[2], argv[0]);
    if (!strcmp(argv[1], "fd_limit")) return fd_limit(argv[2]);
    if (!strcmp(argv[1], "uds_peercred")) return uds_path_peercred(argv[2]);
    if (!strcmp(argv[1], "robust_owner_death")) return robust_owner_death();
    return 64;
}
