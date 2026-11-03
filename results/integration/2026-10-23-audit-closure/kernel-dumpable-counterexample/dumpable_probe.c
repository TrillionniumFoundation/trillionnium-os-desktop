#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>
#include <linux/capability.h>

/* Only one child created by this program is ever inspected. No injection,
 * memory writes, unrelated PID, private data, global policy or limit changes. */
static volatile unsigned int public_sentinel = 0x5a17c0deU;
struct report { int pid, set_rc, set_errno, get, target_fd; uintptr_t addr; };
static pid_t owned_child;
static unsigned violations, positive_maps;
static void die(const char *what) { perror(what); exit(90); }
static void exact(int fd, void *buffer, size_t len, int writing) {
    char *p = buffer;
    while (len) {
        ssize_t n = writing ? write(fd,p,len) : read(fd,p,len);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) die("own child protocol");
        p += n; len -= (size_t)n;
    }
}
static void child_loop(int input, int output, int exec_stage) {
    alarm(20);
    int target = open("/dev/null", O_RDONLY);
    if (target < 0) _exit(91);
    struct report r = { .pid=getpid(), .set_rc=0, .set_errno=0,
                        .get=prctl(PR_GET_DUMPABLE), .target_fd=target,
                        .addr=(uintptr_t)&public_sentinel };
    if (!exec_stage) {
        errno=0; r.set_rc=prctl(PR_SET_DUMPABLE,0L);r.set_errno=errno;
        r.get=prctl(PR_GET_DUMPABLE);
    }
    exact(output,&r,sizeof(r),1);
    for (;;) {
        char command; exact(input,&command,1,0);
        if (command=='Q') _exit(0);
        if (command=='E') {
            char a[24],b[24]; snprintf(a,sizeof(a),"%d",input);snprintf(b,sizeof(b),"%d",output);
            char path[4096];ssize_t n=readlink("/proc/self/exe",path,sizeof(path)-1);
            if(n<=0) _exit(92);
            path[n]=0;
            char *args[]={path,"--child-exec",a,b,NULL};
            char *environment[]={"PATH=/usr/bin:/bin","LANG=C",NULL};
            execve(path,args,environment);_exit(93);
        }
        errno=0;r.set_rc=prctl(PR_SET_DUMPABLE,command=='1'?1L:0L);r.set_errno=errno;
        r.get=prctl(PR_GET_DUMPABLE);exact(output,&r,sizeof(r),1);
    }
}
static void observe(const char *stage,const char *operation,long rc,int err,int forbidden) {
    printf("{\"stage\":\"%s\",\"operation\":\"%s\",\"rc\":%ld,\"errno\":%d,\"own_child\":true}\n",stage,operation,rc,err);
    if(forbidden && rc>=0)violations++;
}
static void proc_read(const char *stage,const char *name,const struct report *r,int forbidden) {
    char path[128];snprintf(path,sizeof(path),"/proc/%d/%s",r->pid,name);
    errno=0;int fd=open(path,O_RDONLY|O_CLOEXEC);int err=errno;
    if(fd<0){observe(stage,name,-1,err,forbidden);return;}
    unsigned int value=0;errno=0;
    ssize_t n = !strcmp(name,"mem") ? pread(fd,&value,sizeof(value),(off_t)r->addr) : read(fd,&value,1);
    err=errno;close(fd);observe(stage,name,n,err,forbidden);
    if(!forbidden && !strcmp(name,"maps") && n>0)positive_maps++;
    if(!strcmp(name,"mem") && n==(ssize_t)sizeof(value) && value!=public_sentinel)die("public sentinel mismatch");
}
static void stage(const char *name,const struct report *r,int expected,int pidfd) {
    if(r->pid!=owned_child)die("not our retained child");
    printf("{\"stage\":\"%s\",\"operation\":\"prctl_set_get\",\"set_rc\":%d,\"set_errno\":%d,\"get\":%d,\"expected\":%d,\"own_child\":true}\n",name,r->set_rc,r->set_errno,r->get,expected);
    if(r->set_rc || r->get!=expected)violations++;
    int forbidden=expected==0;
    proc_read(name,"maps",r,forbidden);proc_read(name,"mem",r,forbidden);
    proc_read(name,"environ",r,forbidden);proc_read(name,"auxv",r,forbidden);
    char path[128],link[256];snprintf(path,sizeof(path),"/proc/%d/fd/%d",r->pid,r->target_fd);
    errno=0;ssize_t n=readlink(path,link,sizeof(link));observe(name,"proc_fd_readlink",n,errno,forbidden);
    if(pidfd>=0) {
        errno=0;long fd=syscall(SYS_pidfd_getfd,pidfd,r->target_fd,0);int err=errno;
        if(fd>=0) close((int)fd);
        observe(name,"pidfd_getfd_dev_null",fd,err,forbidden);
    }
    unsigned int value=0;struct iovec local={&value,sizeof(value)},remote={(void*)r->addr,sizeof(value)};
    errno=0;n=process_vm_readv(r->pid,&local,1,&remote,1,0);int err=errno;
    observe(name,"process_vm_readv_public_sentinel",n,err,forbidden);
    if(n==(ssize_t)sizeof(value) && value!=public_sentinel)die("readv public sentinel mismatch");
    errno=0;long rc=ptrace(PTRACE_ATTACH,r->pid,0,0);err=errno;
    observe(name,"ptrace_attach_only",rc,err,forbidden);
    if(rc==0) {
        int status=0;if(waitpid(r->pid,&status,WUNTRACED)!=r->pid || !WIFSTOPPED(status))die("own child stop");
        if(ptrace(PTRACE_DETACH,r->pid,0,0)!=0)die("own child detach");
    }
    fflush(stdout);
}
static void drop_own_privileges(void) {
    if(geteuid()==0) {
        for(int cap=0;cap<=40;cap++)if(prctl(PR_CAPBSET_DROP,cap,0,0,0)<0 && errno!=EINVAL)die("own bounding cap drop");
        if(setgroups(0,NULL) || setresgid(60001,60001,60001) || setresuid(60001,60001,60001))die("own credential drop");
    }
    struct __user_cap_header_struct h={_LINUX_CAPABILITY_VERSION_3,0};
    struct __user_cap_data_struct caps[2]={{0},{0}};
    if(syscall(SYS_capset,&h,caps)<0 || prctl(PR_SET_NO_NEW_PRIVS,1L,0L,0L,0L)<0)die("own NNP/cap clear");
}
int main(int argc,char **argv) {
    if(argc==4 && !strcmp(argv[1],"--child-exec")) {child_loop(atoi(argv[2]),atoi(argv[3]),1);return 94;}
    alarm(25);setvbuf(stdout,NULL,_IOLBF,0);drop_own_privileges();
    struct utsname u;if(uname(&u))die("uname");
    struct __user_cap_header_struct h={_LINUX_CAPABILITY_VERSION_3,0};struct __user_cap_data_struct caps[2]={{0},{0}};
    if(syscall(SYS_capget,&h,caps)<0)die("capget");
    if(caps[0].effective || caps[1].effective || caps[0].permitted || caps[1].permitted)die("capabilities not clear");
    printf("{\"kernel\":\"%s\",\"release\":\"%s\",\"uid\":%u,\"gid\":%u,\"cap_eff\":0,\"cap_prm\":0,\"nnp\":%d,\"scope\":\"single self-created child; no injection\"}\n",u.sysname,u.release,getuid(),getgid(),prctl(PR_GET_NO_NEW_PRIVS,0L,0L,0L,0L));
    int command[2],reply[2];if(pipe(command)||pipe(reply))die("pipe");
    owned_child=fork();if(owned_child<0)die("fork");
    if(!owned_child){close(command[1]);close(reply[0]);child_loop(command[0],reply[1],0);_exit(95);}
    close(command[0]);close(reply[1]);int pidfd=(int)syscall(SYS_pidfd_open,owned_child,0);
    struct report r;exact(reply[0],&r,sizeof(r),0);stage("set0",&r,0,pidfd);
    char c='1';exact(command[1],&c,1,1);exact(reply[0],&r,sizeof(r),0);stage("set1",&r,1,pidfd);
    c='0';exact(command[1],&c,1,1);exact(reply[0],&r,sizeof(r),0);stage("set0_again",&r,0,pidfd);
    c='E';exact(command[1],&c,1,1);exact(reply[0],&r,sizeof(r),0);stage("ordinary_exec",&r,1,pidfd);
    c='Q';exact(command[1],&c,1,1);int status;if(waitpid(owned_child,&status,0)!=owned_child || status!=0)die("own child exit");
    if(pidfd>=0) close(pidfd);
    close(command[1]);close(reply[0]);
    printf("{\"summary\":true,\"violations\":%u,\"dumpable_positive_maps_reads\":%u,\"all_children_reaped\":true}\n",violations,positive_maps);
    return violations?42:(positive_maps==2?0:43);
}
