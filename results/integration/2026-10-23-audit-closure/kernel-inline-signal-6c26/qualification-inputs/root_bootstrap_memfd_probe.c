#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <linux/memfd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static void require(int value, const char *name)
{
    if (!value) {
        printf("ROOT_BOOTSTRAP_MEMFD_FAIL %s errno=%d\n", name, errno);
        exit(1);
    }
}

static void drop_identity(void)
{
    require(setgroups(0, NULL) == 0, "clear_groups");
    require(prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) == 0, "clear_ambient");
    for (int cap = 0; cap <= CAP_LAST_CAP; cap++)
        require(prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) == 0, "clear_bounding");
    require(setresgid(60001, 60001, 60001) == 0 && setresuid(60001, 60001, 60001) == 0, "dedicated_identity");
    struct __user_cap_header_struct header = {.version = _LINUX_CAPABILITY_VERSION_3, .pid = 0};
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    require(syscall(SYS_capset, &header, data) == 0, "clear_capsets");
    require(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0, "no_new_privileges");
    require(getuid() == 60001 && geteuid() == 60001 && getgid() == 60001 && getegid() == 60001, "actual_identity");
    require(syscall(SYS_capget, &header, data) == 0, "actual_capget");
    for (int i = 0; i < 2; i++)
        require(data[i].effective == 0 && data[i].permitted == 0 && data[i].inheritable == 0, "actual_caps_zero");
    require(prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1, "actual_nnp");
}

int main(int argc, char **argv)
{
    require(argc == 2 && (!strcmp(argv[1], "--controlled-linux") || !strcmp(argv[1], "--disposable-guest")) && geteuid() == 0, "explicit_root_fixture");
    setvbuf(stdout, NULL, _IONBF, 0);
    alarm(30);
    puts("ROOT_BOOTSTRAP_MEMFD_BEGIN");
    int fd = syscall(SYS_memfd_create, "hepta-bootstrap-fixture", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    require(fd >= 0, "create_memfd");
    static const char bytes[] = "public fixture bytes; no authority or keys";
    require(write(fd, bytes, sizeof bytes) == sizeof bytes, "write_public_fixture");
    require(fchmod(fd, 0400) == 0, "root_read_mode");
    int seals = F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL;
    require(fcntl(fd, F_ADD_SEALS, seals) == 0, "seal_immutable");
    struct stat metadata;
    require(fstat(fd, &metadata) == 0, "stat_memfd");
    int observed_seals = fcntl(fd, F_GET_SEALS);
    printf("ROOT_BOOTSTRAP_MEMFD_OBSERVED uid=%lu links=%lu mode=%o seals=%d\n",
           (unsigned long)metadata.st_uid, (unsigned long)metadata.st_nlink,
           (unsigned)(metadata.st_mode & 07777), observed_seals);
    require(S_ISREG(metadata.st_mode) && metadata.st_uid == 0 && metadata.st_nlink == 0 &&
            (metadata.st_mode & 07777) == 0400 && observed_seals == seals, "root_unlinked_sealed_source");
    pid_t parent = getpid();
    pid_t child = fork();
    require(child >= 0, "fork_owned_consumer");
    if (child == 0) {
        drop_identity();
        require(prctl(PR_SET_PDEATHSIG, SIGKILL, 0, 0, 0) == 0 && getppid() == parent, "owned_parent_lifetime");
        require(lseek(fd, 0, SEEK_SET) == 0, "rewind_inherited");
        char observed[sizeof bytes];
        require(read(fd, observed, sizeof observed) == sizeof observed && !memcmp(observed, bytes, sizeof bytes), "read_exact_public_bytes");
        errno = 0;
        require(pwrite(fd, "x", 1, 0) == -1 && errno == EPERM, "sealed_write_refused");
        errno = 0;
        require(ftruncate(fd, 0) == -1 && errno == EPERM, "sealed_shrink_refused");
        errno = 0;
        require(fcntl(fd, F_ADD_SEALS, F_SEAL_GROW) == -1 && errno == EPERM, "seals_cannot_change");
        errno = 0;
        require(fchown(fd, 60001, (gid_t)-1) == -1 && errno == EPERM, "root_ownership_cannot_change");
        close(fd);
        puts("ROOT_BOOTSTRAP_MEMFD_CHILD uid=60001 caps=0 nnp=1 immutable=1");
        _exit(0);
    }
    int status;
    require(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "consumer_reaped_success");
    close(fd);
    alarm(0);
    puts("ROOT_BOOTSTRAP_MEMFD_COMPLETE pass=1 production_ready=0");
    return 0;
}
