// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "board.h"
#include "board_policy.h"
#include "linux_run_label.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/lsm.h>
#include <linux/sched.h>
#include <poll.h>
#include <signal.h>
#include <sys/wait.h>
#include <linux/openat2.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/xattr.h>
#include <unistd.h>

#define BOARD_INIT "/usr/lib/droidloom/production/current/droidloom-board-init"
#define SYSTEMD "/usr/lib/systemd/systemd"
#define FINISH "--exec-selected-ubuntu-init"
#define FACTORY "/usr/lib/droidloom/production/current/droidloomd"
extern char **environ;

static int fail(int error)
{
    errno = error;
    return -1;
}

static int trusted_elf(const char *path)
{
    struct open_how how = {
        .flags = O_RDONLY | O_NOFOLLOW | O_CLOEXEC,
        .resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS
    };
    int fd = (int)syscall(SYS_openat2, AT_FDCWD, path, &how, sizeof(how));
    if (fd < 0)
        return -1;
    struct stat st;
    int error = 0;
    if (fstat(fd, &st) < 0)
        error = errno;
    else if (!S_ISREG(st.st_mode) || st.st_uid != 0 || st.st_gid != 0 ||
             (st.st_mode & 07777) != 0755 || st.st_nlink == 0)
        error = EACCES;
    if (error) {
        close(fd);
        return fail(error);
    }
    return fd;
}

static int has_label(int fd, const char *expected)
{
    char actual[128] = {0};
    ssize_t size = fgetxattr(fd, "security.selinux", actual, sizeof(actual));
    if (size < 0)
        return -1;
    size_t length = strlen(expected);
    if ((size != (ssize_t)length && size != (ssize_t)length + 1) ||
        memcmp(actual, expected, length + 1) != 0)
        return fail(EACCES);
    return 0;
}

static const char *operation;

static int current_linux_role(void)
{
    const char expected[] = "u:system_r:p4_linux_early_t:s0";
    _Alignas(struct lsm_ctx) unsigned char buffer[512] = {0};
    struct lsm_ctx *context = (struct lsm_ctx *)buffer;
    context->id = LSM_ID_SELINUX;
    uint32_t size = sizeof(buffer);
    long count = syscall(SYS_lsm_get_self_attr, LSM_ATTR_CURRENT, context, &size, LSM_FLAG_SINGLE);
    if (count < 0)
        return -1;
    if (count != 1 || context->id != LSM_ID_SELINUX || size > sizeof(buffer) ||
        size < sizeof(*context) || context->len > size || context->len < sizeof(*context) ||
        context->ctx_len > context->len - sizeof(*context) ||
        (context->ctx_len != sizeof(expected) && context->ctx_len != sizeof(expected)-1) ||
        memcmp(context->ctx, expected, (size_t)context->ctx_len) != 0)
        return fail(EACCES);
    return 0;
}

static int verified_systemd(int fd)
{
    static const unsigned char selected[32] = {
        0xa3, 0x7f, 0x48, 0x1d, 0xa2, 0x0c, 0x11, 0xba, 0x2b, 0x5d, 0x06, 0xfc, 0xf5, 0x49, 0xf3, 0xa0,
        0xaf, 0xdb, 0xfd, 0x90, 0x3c, 0x76, 0x94, 0x41, 0x12, 0x95, 0xe3, 0x9f, 0x11, 0xf3, 0x42, 0x34
    };
    return droidloom_verified_elf(fd, 141776, selected);
}

static int finish(int argc, char **argv)
{
    operation = "check the Linux early process role";
    if (current_linux_role() < 0)
        return -1;
    operation = "reopen the Ubuntu console in the Linux early process role";
    if (droidloom_linux_console_descriptors() < 0)
        return -1;
    operation = "verify the selected Ubuntu systemd executable and label";
    int fd = trusted_elf(SYSTEMD);
    if (fd < 0 || has_label(fd, "u:object_r:init_exec_t:s0") < 0 || verified_systemd(fd) < 0)
        return -1;
    argv[1] = "/sbin/init";
    (void)argc;
    operation = "exec the original Ubuntu systemd";
    execveat(fd, "", &argv[1], environ, AT_EMPTY_PATH);
    return -1;
}

/* Execute the selected manager before the initial policy is loaded, then
 * keep it blocked on an inherited pipe. Stock kernel.te forbids *all* later
 * execute_no_trans; no policy exception is introduced for this executable. */
struct boot_factory { int pidfd, receive, release; };
static int factory_phase(struct boot_factory *factory,char expected)
{
    struct pollfd waiters[2]={{.fd=factory->receive,.events=POLLIN},{.fd=factory->pidfd,.events=POLLIN}};
    int count;
    do{count=poll(waiters,2,30000);}while(count<0&&errno==EINTR);
    if(count<0)return -1;
    if(!count)return fail(ETIMEDOUT);
    if(waiters[1].revents||!(waiters[0].revents&POLLIN))return fail(ECHILD);
    char ready=0;ssize_t n;
    do{n=read(factory->receive,&ready,1);}while(n<0&&errno==EINTR);
    if(n!=1||ready!=expected)return fail(n<0?errno:EPROTO);
    waiters[1].revents=0;
    return poll(&waiters[1],1,0)==0?0:fail(ECHILD);
}
static int prepare_instance_factory(struct boot_factory *factory)
{
    int executable=trusted_elf(FACTORY);
    if(executable<0)return -1;
    int channel[2],gate[2];
    if(pipe2(channel,O_CLOEXEC)<0){int error=errno;close(executable);return fail(error);}
    if(pipe2(gate,O_CLOEXEC)<0){
        int error=errno;close(executable);close(channel[0]);close(channel[1]);return fail(error);
    }
    int pidfd=-1;
    struct clone_args spawn={.flags=CLONE_PIDFD,.pidfd=(uint64_t)(uintptr_t)&pidfd,.exit_signal=SIGCHLD};
    pid_t child=(pid_t)syscall(SYS_clone3,&spawn,sizeof(spawn));
    if(child==0){
        close(channel[0]);close(gate[1]);
        if(dup2(channel[1],STDOUT_FILENO)<0||dup2(gate[0],STDIN_FILENO)<0||
           syscall(SYS_close_range,3U,~0U,CLOSE_RANGE_CLOEXEC)<0)_exit(125);
        char *const args[]={FACTORY,"--serve-early-instances",NULL};
        char *const environment[]={"PATH=/usr/bin:/bin","LC_ALL=C",NULL};
        execveat(executable,"",args,environment,AT_EMPTY_PATH);
        _exit(126);
    }
    int error=child<0?errno:0;
    close(executable);close(channel[1]);close(gate[0]);
    if(error){close(channel[0]);close(gate[1]);return fail(error);}
    *factory=(struct boot_factory){.pidfd=pidfd,.receive=channel[0],.release=gate[1]};
    return factory_phase(factory,'P');
}
static int release_instance_factory(struct boot_factory *factory)
{
    ssize_t n;
    do{n=write(factory->release,"G",1);}while(n<0&&errno==EINTR);
    if(n!=1)return fail(n<0?errno:EPROTO);
    if(factory_phase(factory,'F')<0)return -1;
    close(factory->receive);close(factory->release);close(factory->pidfd);
    return 0;
}

static int activate(int argc, char **argv)
{
    operation = "verify the real-root board PID 1 executable";
    int own = trusted_elf(BOARD_INIT);
    struct stat file, current;
    if (own < 0 || fstat(own, &file) < 0 || stat("/proc/1/exe", &current) < 0)
        return -1;
    if (file.st_dev != current.st_dev || file.st_ino != current.st_ino)
        return fail(ESTALE);
    operation = "verify the original Ubuntu executable";
    int dist = trusted_elf(SYSTEMD);
    if (dist < 0 || verified_systemd(dist) < 0)
        return -1;
    close(dist);

    struct droidloom_early_plan plan;
    operation = "verify the selected real-root release and empty Android slot";
    int selected = droidloom_post_switch_read_plan(&plan);
    if (selected <= 0)
        return selected < 0 ? -1 : fail(ENODEV);
    char **next = calloc((size_t)argc + 2, sizeof(*next));
    if (!next)
        return -1;
    next[0] = BOARD_INIT;
    next[1] = FINISH;
    for (int n = 1; n < argc; n++)
        next[n + 1] = argv[n];
    /* run-init can leave the global init sharing fs_struct with earlier tasks.
     * Give it private filesystem state and a private descriptor table before
     * changing its security domain. Pinned kernel objects keep their owners. */
    operation = "detach the Linux PID 1 filesystem and descriptor state";
    if (unshare(CLONE_FS | CLONE_FILES) < 0)
        return -1;
    struct boot_factory factory={.pidfd=-1,.receive=-1,.release=-1};
    operation = "prepare the original kernel-lineage instance factory";
    if(prepare_instance_factory(&factory)<0)return -1;
    operation = "activate the selected board security policy";
    if (droidloom_board_activate_policy((gid_t)(plan.gid_start + 9999), plan.base_cohort_sha256) < 0)
        return -1;
    operation = "verify the activated board executable label";
    if (has_label(own, "u:object_r:p4_linux_early_exec_t:s0") < 0)
        return -1;
    operation = "release the original kernel-lineage factory into its enforced AppArmor profile";
    if(release_instance_factory(&factory)<0)return -1;
    operation = "enter the Linux early process role";
    execveat(own, "", next, environ, AT_EMPTY_PATH);
    return -1;
}

int main(int argc, char **argv)
{
    if (getpid() != 1 || geteuid() != 0 || argc < 1) {
        fprintf(stderr, "Droidloom board init requires original Linux PID 1\n");
        return 1;
    }
    if (argc > 1 && strcmp(argv[1], FINISH) == 0)
        finish(argc, argv);
    else
        activate(argc, argv);
    int error = errno;
    fprintf(stderr, "Droidloom real-root Linux PID 1 failed to %s: %s\n", operation, strerror(error));
    return 1;
}
