// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <linux/lsm.h>
#include <linux/sched.h>
#include <linux/seccomp.h>
#include <sched.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "instance_query.h"

extern int droidloom_factory_context(void);
static int fail(int e) { errno=e; return -1; }
static int attribute(uint64_t id,uint64_t attr,const char *expected) {
    _Alignas(struct lsm_ctx) unsigned char bytes[512]={0};
    struct lsm_ctx *c=(struct lsm_ctx *)bytes;
    c->id=id;
    uint32_t size=sizeof(bytes);
    long count=syscall(SYS_lsm_get_self_attr,attr,c,&size,LSM_FLAG_SINGLE);
    if(count<0)return -1;
    size_t n=strlen(expected);
    if(count!=1||c->id!=id||size>sizeof(bytes)||size<sizeof(*c)||
       c->len<sizeof(*c)||c->len>size||c->ctx_len>c->len-sizeof(*c)||
       (c->ctx_len!=n&&c->ctx_len!=n+1)||memcmp(c->ctx,expected,(size_t)c->ctx_len))
        return fail(EACCES);
    return 0;
}
static int label(uint64_t id,const char *expected) {
    return attribute(id,LSM_ATTR_CURRENT,expected);
}
static int set_attribute(uint64_t id,uint64_t attr,const char *value) {
    _Alignas(struct lsm_ctx) unsigned char bytes[256]={0};
    struct lsm_ctx *c=(struct lsm_ctx *)bytes;
    size_t n=strlen(value)+1;
    if(n>sizeof(bytes)-sizeof(*c))return fail(E2BIG);
    c->id=id;c->len=sizeof(*c)+n;c->ctx_len=n;
    memcpy(c->ctx,value,n);
    return syscall(SYS_lsm_set_self_attr,attr,c,c->len,0)<0?-1:0;
}
static int current(uint64_t id,const char *value) {
    return set_attribute(id,LSM_ATTR_CURRENT,value);
}
static const char *exec_context(uint32_t domain) {
    switch(domain) {
    case 0:return "u:r:droidloom_query:s0";
    case 1:return "u:r:droidloom_browser:s0";
    case 2:return "u:r:droidloom_contacts_read:s0";
    case 3:return "u:r:droidloom_launch_read:s0";
    case 4:return "u:r:droidloom_launch_start:s0";
    case 5:return "u:r:droidloom_install:s0";
    case 6:return "u:r:droidloom_catalog_read:s0";
    case 7:return "u:r:droidloom_display_control:s0";
    case 8:return "u:r:droidloom_appops_read:s0";
    default:return NULL;
    }
}
static uint64_t now_ns(void) {
    struct timespec value;
    if(clock_gettime(CLOCK_MONOTONIC,&value)||value.tv_sec<0||
       value.tv_nsec<0||value.tv_nsec>=1000000000)_exit(125);
    return (uint64_t)value.tv_sec*1000000000+(uint64_t)value.tv_nsec;
}
static void live_owners(void) {
    struct pollfd f[3]={
        {.fd=4,.events=POLLIN},
        {.fd=5,.events=POLLIN},
        {.fd=6,.events=POLLIN}
    };
    if(poll(f,3,0)!=0)_exit(125);
}
static void park(uint64_t deadline) {
    unsigned char ready='R';
    if(send(3,&ready,1,MSG_NOSIGNAL)!=1)_exit(125);
    for(;;) {
        uint64_t now=now_ns();
        if(now>=deadline)_exit(125);
        live_owners();
        struct pollfd p={.fd=3,.events=POLLIN};
        int millis=(int)((deadline-now)/1000000);
        if(millis>20)millis=20;
        if(millis<1)millis=1;
        int n=poll(&p,1,millis);
        if(n<0&&errno==EINTR)continue;
        if(n<0||p.revents&(POLLERR|POLLNVAL|POLLHUP))_exit(125);
        if(p.revents&POLLIN) {
            unsigned char value[2]={0};
            if(recv(3,value,sizeof(value),MSG_DONTWAIT)!=1||value[0]!='G')_exit(125);
            return;
        }
    }
}
/* No allocator, user-input dispatcher, pathname open, Binder handle or second
   process creation occurs in this fixed post-clone path. The factory profile
   remains active through the gate and namespace/credential transition. */
static _Noreturn void child(const struct droidloom_factory_query *q) {
    int copies[15];
    for(int i=0;i<15;i++){
        copies[i]=fcntl(q->files[i],F_DUPFD_CLOEXEC,64);
        if(copies[i]<0)_exit(125);
    }
    for(int i=0;i<15;i++)
        if((i<3?dup2(copies[i],i):dup3(copies[i],i,O_CLOEXEC))!=i)_exit(125);
    if(syscall(SYS_close_range,15U,~0U,0)<0)_exit(125);
    struct sigaction reset;
    memset(&reset,0,sizeof(reset));
    reset.sa_handler=SIG_DFL;
    if(sigemptyset(&reset.sa_mask))_exit(125);
    for(int s=1;s<NSIG;s++){
        if(s==SIGKILL||s==SIGSTOP)continue;
        if(sigaction(s,&reset,NULL)&&errno!=EINVAL)_exit(125);
    }
    sigset_t empty;
    if(sigemptyset(&empty)||sigprocmask(SIG_SETMASK,&empty,NULL))_exit(125);
    if(prctl(PR_SET_PDEATHSIG,SIGKILL)||getpid()<=1||getppid()!=0||getuid()!=0||geteuid()!=0||
       getgid()!=0||getegid()!=0||prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=0||
       prctl(PR_GET_SECCOMP,0,0,0,0)!=0||
       label(LSM_ID_SELINUX,"u:r:kernel:s0")||
       label(LSM_ID_APPARMOR,"droidloom-instance-factory (enforce)"))_exit(125);
    /* Clear supplementary groups while still in the original host userns.
       The target may deliberately have setgroups=deny. */
    if(syscall(SYS_setgroups,0,NULL)||prctl(PR_SET_DUMPABLE,1,0,0,0)||
       current(LSM_ID_SELINUX,"u:r:droidloom_query_birth:s0")||
       label(LSM_ID_SELINUX,"u:r:droidloom_query_birth:s0")||
       label(LSM_ID_APPARMOR,"droidloom-instance-factory (enforce)")||
       prctl(PR_SET_DUMPABLE,1,0,0,0))_exit(125);
    park(q->deadline_ns);
    /* The real parent now owns PTRACE_SEIZE on the non-kernel birth SID.
       USERNS is entered only after attach, with the original capabilities. */
    if(setns(8,CLONE_NEWUSER)||setns(10,CLONE_NEWIPC)||
       setns(11,CLONE_NEWUTS)||setns(12,CLONE_NEWNET)||
       setns(13,CLONE_NEWCGROUP)||setns(9,CLONE_NEWNS)||
       fchdir(7)||chroot(".")||chdir("/")||
       syscall(SYS_getgroups,0,NULL)!=0||
       syscall(SYS_setresgid,2000U,2000U,2000U)||
       syscall(SYS_setresuid,2000U,2000U,2000U))_exit(125);
    struct __user_cap_header_struct header={.version=_LINUX_CAPABILITY_VERSION_3,.pid=0};
    struct __user_cap_data_struct caps[2]={{0},{0}};
    if(syscall(SYS_capset,&header,caps)||prctl(PR_CAP_AMBIENT,PR_CAP_AMBIENT_CLEAR_ALL,0,0,0)||
       prctl(PR_SET_DUMPABLE,0,0,0,0)||
       prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=0)_exit(125);
    /* The validated closed operation selects one literal pending SELinux role.
       Setting the pending role changes no current authority; the real exec
       transition and its full label are independently checked at TRACEEXEC. */
    const char *domain=exec_context(q->domain);
    if(!domain||set_attribute(LSM_ID_SELINUX,LSM_ATTR_EXEC,domain)||
       attribute(LSM_ID_SELINUX,LSM_ATTR_EXEC,domain))_exit(125);
    /* Do the reviewed CURRENT AppArmor transition while NNP is still zero.
       The subsequent ELF exec stays in this exact profile; no profile is
       widened after NNP and no stacked factory restriction is misreported. */
    if(current(LSM_ID_APPARMOR,"changeprofile droidloom-production-android")||
       label(LSM_ID_APPARMOR,"droidloom-production-android (enforce)")||
       label(LSM_ID_SELINUX,"u:r:droidloom_query_birth:s0")||
       prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)||
       prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,q->filter))_exit(125);
    if(now_ns()>=q->deadline_ns)_exit(125);
    live_owners();
    for(int fd=3;fd<14;fd++)if(close(fd))_exit(125);
    /* The immutable file has its original system bytes, no setid bits and
       no file capabilities. The selected birth->operation transition is policy-owned.
       AT_EMPTY_PATH uses the kernel-origin reopened read-only body. */
    syscall(SYS_execveat,14,"",q->argv,q->envp,AT_EMPTY_PATH);
    _exit(125);
}
int droidloom_factory_spawn_query(const struct droidloom_factory_query *q,int *pid,int *pidfd) {
    *pid=-1;*pidfd=-1;
    if(!q||!q->argv||!q->envp||!q->filter||!q->filter->len||
       q->pid_namespace<0||q->cgroup<0||!exec_context(q->domain))return fail(EINVAL);
    if(droidloom_factory_context())return -1;
    if(syscall(SYS_gettid)!=getpid())return fail(EPERM);
    int original=open("/proc/self/ns/pid",O_RDONLY|O_CLOEXEC);
    if(original<0)return -1;
    sigset_t all,prior;
    if(sigfillset(&all)||sigprocmask(SIG_SETMASK,&all,&prior)){
        int error=errno;close(original);return fail(error);
    }
    int error=0;
    if(setns(q->pid_namespace,CLONE_NEWPID))error=errno;
    if(!error){
        struct clone_args args={.flags=CLONE_PIDFD|CLONE_INTO_CGROUP,
            .pidfd=(uint64_t)(uintptr_t)pidfd,.exit_signal=SIGCHLD,
            .cgroup=(uint64_t)q->cgroup};
        long value=syscall(SYS_clone3,&args,sizeof(args));
        if(value<0)error=errno;
        else if(value==0)child(q);
        else *pid=(int)value;
        /* Restore only next-child placement; the factory never left its own
           active host PID namespace, and remains the real wait owner. */
        if(setns(original,CLONE_NEWPID))error=errno;
    }
    if(close(original)&&!error)error=errno;
    if(sigprocmask(SIG_SETMASK,&prior,NULL)&&!error)error=errno;
    return error?fail(error):0;
}
