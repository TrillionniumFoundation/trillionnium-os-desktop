#include "lifecycle_probe.h"

static void *thread_change(void *unused) {
    (void)unused;
    check("thread_inherits_zero", prctl(PR_GET_DUMPABLE), 0);
    check("thread_sets_one", prctl(PR_SET_DUMPABLE, 1L), 0);
    return NULL;
}
static int vm_change(void *unused) {
    (void)unused;
    int okay = prctl(PR_GET_DUMPABLE) == 1 && prctl(PR_SET_DUMPABLE, 0L) == 0;
    return okay ? 0 : 42;
}
static void self_access(void) {
    int fd = open("/dev/null", O_RDONLY);
    require(fd >= 0, "self_dev_null_open");
    char path[96], data[512];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    require(readlink(path, data, sizeof(data)) > 0, "dump0_self_fd_readlink");
    snprintf(path, sizeof(path), "/proc/self/fdinfo/%d", fd);
    int info = open(path, O_RDONLY);
    require(info >= 0 && read(info, data, sizeof(data)) > 0, "dump0_self_fdinfo");
    if (info >= 0) close(info);
    int pidfd = (int)syscall(SYS_pidfd_open, getpid(), 0);
    require(pidfd >= 0, "self_pidfd_open");
    snprintf(path, sizeof(path), "/proc/self/fd/%d", pidfd);
    ssize_t n = readlink(path, data, sizeof(data) - 1);
    require(n > 0, "dump0_self_pidfd_readlink");
    if (n > 0) {
        data[n] = 0;
        require(!strcmp(data, "anon_inode:[pidfd]"), "self_pidfd_link_identity");
    }
    snprintf(path, sizeof(path), "/proc/self/fdinfo/%d", pidfd);
    info = open(path, O_RDONLY);
    n = info < 0 ? -1 : read(info, data, sizeof(data) - 1);
    require(n > 0, "dump0_self_pidfd_fdinfo");
    if (n > 0) {
        data[n] = 0;
        snprintf(path, sizeof(path), "Pid:\t%d", getpid());
        require(strstr(data, path) != NULL, "self_pidfd_metadata_identity");
    }
    if (info >= 0) close(info);
    if (pidfd >= 0) close(pidfd);
    if (fd >= 0) close(fd);
}
void local_lifecycle(void) {
    check("set_zero", prctl(PR_SET_DUMPABLE, 0L), 0);
    check("get_zero", prctl(PR_GET_DUMPABLE), 0);
    errno = 0;
    check("invalid_set_rejected", prctl(PR_SET_DUMPABLE, 2L), -1);
    check("invalid_set_errno", errno, EINVAL);
    check("invalid_set_preserves_zero", prctl(PR_GET_DUMPABLE), 0);
    char *args[] = {"controlled-missing-program", NULL};
    char *env[] = {"DUMPABLE_PROBE=controlled", NULL};
    errno = 0;
    check("failed_exec", execve("/controlled-dumpable-no-such-program", args, env), -1);
    check("failed_exec_errno", errno, ENOENT);
    check("failed_exec_preserves_zero", prctl(PR_GET_DUMPABLE), 0);
    self_access();
    pid_t child = fork();
    if (child < 0) _exit(98);
    if (child == 0) _exit(prctl(PR_GET_DUMPABLE) == 0 && prctl(PR_SET_DUMPABLE, 1L) == 0 ? 0 : 42);
    reap(child, "fork_copies_zero");
    check("fork_child_change_not_shared", prctl(PR_GET_DUMPABLE), 0);
    pthread_t thread;
    int e = pthread_create(&thread, NULL, thread_change, NULL);
    check("pthread_create", e, 0);
    if (!e) check("pthread_join", pthread_join(thread, NULL), 0);
    check("thread_change_shared", prctl(PR_GET_DUMPABLE), 1);
    errno = 0;
    int failed = execve("/controlled-dumpable-no-such-program", args, env);
    int failed_errno = errno;
    check("failed_exec_at_one", failed, -1);
    check("failed_exec_at_one_errno", failed_errno, ENOENT);
    check("failed_exec_preserves_one", prctl(PR_GET_DUMPABLE), 1);
    void *stack = malloc(128 * 1024);
    require(stack != NULL, "clone_vm_bounded_stack");
    if (stack) {
        child = clone(vm_change, (char *)stack + 128 * 1024, CLONE_VM | SIGCHLD, NULL);
        require(child > 0, "clone_vm_created");
        if (child > 0) reap(child, "clone_vm_child_reaped");
        check("clone_vm_change_shared", prctl(PR_GET_DUMPABLE), 0);
        free(stack);
    }
}
