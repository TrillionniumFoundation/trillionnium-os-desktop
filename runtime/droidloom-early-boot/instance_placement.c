// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/capability.h>
#include <linux/filter.h>
#include <linux/nsfs.h>
#include <linux/sched.h>
#include <linux/seccomp.h>
#include <sched.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

extern int droidloom_factory_context(void);

struct droidloom_init_placement {
    int pid;
    int pidfd;
    int restored;
};
static int fail(int value) { errno=value; return -1; }
/* cpuset may call security_task_setscheduler() when effective CPU/memory
 * masks differ. commoncap accepts a target whose permitted set is a subset
 * of the writer's; prove the complete current-kernel set before cloning.
 * The child changes no USERNS or credentials and drops no permitted bits. */
static int full_permitted(void) {
    if(CAP_LAST_CAP>=63)return fail(ENOTSUP);
    if(prctl(PR_CAPBSET_READ,CAP_LAST_CAP,0,0,0)<0)return -1;
    errno=0;
    if(prctl(PR_CAPBSET_READ,CAP_LAST_CAP+1,0,0,0)!=-1||errno!=EINVAL)
        return fail(ENOTSUP);
    struct __user_cap_header_struct header={.version=_LINUX_CAPABILITY_VERSION_3,.pid=0};
    struct __user_cap_data_struct data[_LINUX_CAPABILITY_U32S_3]={{0}};
    if(syscall(SYS_capget,&header,data)<0)return -1;
    uint64_t actual=(uint64_t)data[0].permitted|((uint64_t)data[1].permitted<<32);
    uint64_t required=(UINT64_C(1)<<(CAP_LAST_CAP+1))-1;
    return actual==required?0:fail(EPERM);
}
static int same_children_namespace(const struct stat *original) {
    struct stat current;
    if(stat("/proc/self/ns/pid_for_children",&current))return -1;
    if(current.st_dev!=original->st_dev||current.st_ino!=original->st_ino)
        return fail(EXDEV);
    return 0;
}
/* No Rust state, allocation, destructor, user argv, PID or path is accepted.
 * The original PID namespace's 1 cannot be recycled. All descriptors except
 * the exact factory-opened cgroup.procs are closed before the one write. */
static _Noreturn void move_pid_one(int target) {
    if(getpid()<=1)_exit(101);
    if(target!=3&&dup3(target,3,O_CLOEXEC)<0)_exit(102);
    if(syscall(SYS_close_range,4,UINT32_MAX,0)<0)_exit(103);
    close(0);close(1);close(2);
    struct sock_filter code[]={
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,AUDIT_ARCH_X86_64,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,nr)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,SYS_exit,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,SYS_exit_group,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,SYS_write,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[0])+4),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[0])),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,3,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
    };
    struct sock_fprog filter={.len=sizeof(code)/sizeof(code[0]),.filter=code};
    if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)<0||
       syscall(SYS_seccomp,SECCOMP_SET_MODE_FILTER,0,&filter)<0)_exit(104);
    ssize_t n;
    do{n=write(3,"1",1);}while(n<0&&errno==EINTR);
    _exit(n==1?0:105);
}
int droidloom_factory_place_init(int pid_namespace,int target,
                                struct droidloom_init_placement *out) {
    if(!out)return fail(EINVAL);
    out->pid=-1;out->pidfd=-1;out->restored=0;
    if(pid_namespace<0||target<0)return fail(EINVAL);
    if(droidloom_factory_context())return -1;
    if(syscall(SYS_gettid)!=getpid())return fail(EPERM);
    int original=open("/proc/self/ns/pid",O_RDONLY|O_CLOEXEC);
    if(original<0)return -1;
    struct stat original_node;
    int error=0;
    if(fstat(original,&original_node)||same_children_namespace(&original_node))
        error=errno;
    if(error){close(original);return fail(error);}
    out->restored=1;
    if(full_permitted()){int saved=errno;close(original);return fail(saved);}
    int kind=ioctl(pid_namespace,NS_GET_NSTYPE);
    if(kind!=CLONE_NEWPID){
        int saved=kind<0?errno:EINVAL;close(original);return fail(saved);
    }
    sigset_t all,prior;
    if(sigfillset(&all)||sigprocmask(SIG_SETMASK,&all,&prior)){
        int saved=errno;close(original);return fail(saved);
    }
    if(setns(pid_namespace,CLONE_NEWPID))error=errno;
    else{
        out->restored=0;
        struct clone_args args={.flags=CLONE_PIDFD,
            .pidfd=(uint64_t)(uintptr_t)&out->pidfd,.exit_signal=SIGCHLD};
        long value=syscall(SYS_clone3,&args,sizeof(args));
        if(value<0)error=errno;
        else if(value==0)move_pid_one(target);
        else out->pid=(int)value;
        if(setns(original,CLONE_NEWPID)||same_children_namespace(&original_node))
            error=errno;
        else out->restored=1;
    }
    if(close(original)&&!error)error=errno;
    if(sigprocmask(SIG_SETMASK,&prior,NULL)){
        error=errno;out->restored=0;
    }
    if(droidloom_factory_context()){error=errno;out->restored=0;}
    return error?fail(error):0;
}
