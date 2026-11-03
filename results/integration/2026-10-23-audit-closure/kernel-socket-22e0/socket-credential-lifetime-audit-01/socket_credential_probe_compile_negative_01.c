#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned failures;
static int exact(int fd, void *buf, size_t size, int writing) {
    char *p = buf;
    while (size) {
        ssize_t n = writing ? write(fd, p, size) : read(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}
static void check(const char *transport, const char *name, int passed) {
    printf("{\"transport\":\"%s\",\"case\":\"%s\",\"passed\":%s}\n",transport,name,passed?"true":"false");
    failures += !passed;
}
struct identity { uid_t uid, euid, suid; gid_t gid, egid, sgid; uint64_t permitted,effective; int nnp,error; };
static struct identity identity(void) {
    struct identity r = {0};
    struct __user_cap_header_struct h = {_LINUX_CAPABILITY_VERSION_3,0};
    struct __user_cap_data_struct c[2] = {{0},{0}};
    if (getresuid(&r.uid,&r.euid,&r.suid) || getresgid(&r.gid,&r.egid,&r.sgid) || syscall(SYS_capget,&h,c)) r.error=errno;
    r.permitted=((uint64_t)c[1].permitted<<32)|c[0].permitted;
    r.effective=((uint64_t)c[1].effective<<32)|c[0].effective;
    r.nnp=prctl(PR_GET_NO_NEW_PRIVS,0L,0L,0L,0L);
    return r;
}
static int report(int ctl) { struct identity r=identity();return exact(ctl,&r,sizeof(r),1); }
static int observe_identity(int ctl,const char *name,const char *stage,uid_t id,uid_t saved) {
    struct identity r;
    if (exact(ctl,&r,sizeof(r),0)) return -1;
    printf("{\"transport\":\"%s\",\"stage\":\"%s\",\"uid\":%u,\"euid\":%u,\"suid\":%u,\"gid\":%u,\"egid\":%u,\"sgid\":%u,\"permitted\":%llu,\"effective\":%llu,\"nnp\":%d,\"error\":%d}\n",name,stage,r.uid,r.euid,r.suid,r.gid,r.egid,r.sgid,(unsigned long long)r.permitted,(unsigned long long)r.effective,r.nnp,r.error);
    check(name,"actual_sender_identity_caps0_nnp1",!r.error&&r.uid==id&&r.euid==id&&r.suid==saved&&r.gid==id&&r.egid==id&&r.sgid==saved&&!r.permitted&&!r.effective&&r.nnp==1);
    return 0;
}
static int command(int fd,char want) { char got;return exact(fd,&got,1,0)||got!=want; }
static int send_command(int fd,char c) { return exact(fd,&c,1,1); }
static int send_fd(int ctl,int fd) {
    char byte='F';struct iovec iov={&byte,1};
    union { struct cmsghdr align;char bytes[CMSG_SPACE(sizeof(int))]; } control={0};
    struct msghdr msg={.msg_iov=&iov,.msg_iovlen=1,.msg_control=control.bytes,.msg_controllen=sizeof(control.bytes)};
    struct cmsghdr *h=CMSG_FIRSTHDR(&msg);h->cmsg_level=SOL_SOCKET;h->cmsg_type=SCM_RIGHTS;h->cmsg_len=CMSG_LEN(sizeof(fd));memcpy(CMSG_DATA(h),&fd,sizeof(fd));
    return sendmsg(ctl,&msg,0)==1?0:-1;
}
static int receive_fd(int ctl) {
    char byte=0;struct iovec iov={&byte,1};
    union { struct cmsghdr align;char bytes[CMSG_SPACE(sizeof(int))]; } control={0};
    struct msghdr msg={.msg_iov=&iov,.msg_iovlen=1,.msg_control=control.bytes,.msg_controllen=sizeof(control.bytes)};
    if(recvmsg(ctl,&msg,MSG_CMSG_CLOEXEC)!=1||byte!='F'||msg.msg_flags&MSG_CTRUNC)return -1;
    struct cmsghdr *h=CMSG_FIRSTHDR(&msg);int fd=-1;
    if(!h||h->cmsg_level!=SOL_SOCKET||h->cmsg_type!=SCM_RIGHTS||h->cmsg_len!=CMSG_LEN(sizeof(fd))||CMSG_NXTHDR(&msg,h))return -1;
    memcpy(&fd,CMSG_DATA(h),sizeof(fd));return fd;
}
static ssize_t send_credential(int fd,char byte,pid_t pid,uid_t uid,gid_t gid) {
    struct ucred cred={pid,uid,gid};struct iovec iov={&byte,1};
    union { struct cmsghdr align;char bytes[CMSG_SPACE(sizeof(struct ucred))]; } control={0};
    struct msghdr msg={.msg_iov=&iov,.msg_iovlen=1,.msg_control=control.bytes,.msg_controllen=sizeof(control.bytes)};
    struct cmsghdr *h=CMSG_FIRSTHDR(&msg);h->cmsg_level=SOL_SOCKET;h->cmsg_type=SCM_CREDENTIALS;h->cmsg_len=CMSG_LEN(sizeof(cred));memcpy(CMSG_DATA(h),&cred,sizeof(cred));
    return sendmsg(fd,&msg,0);
}
static void observe_peer(int fd,pid_t pid,const char *name,const char *stage) {
    struct ucred c={0};socklen_t len=sizeof(c);errno=0;int rc=getsockopt(fd,SOL_SOCKET,SO_PEERCRED,&c,&len),error=errno;
    int passed=rc==0&&len==sizeof(c)&&c.pid==pid&&c.uid==60001&&c.gid==60001;
    printf("{\"transport\":\"%s\",\"peer_stage\":\"%s\",\"rc\":%d,\"errno\":%d,\"pid_matches\":%s,\"uid\":%u,\"gid\":%u,\"passed\":%s}\n",name,stage,rc,error,c.pid==pid?"true":"false",c.uid,c.gid,passed?"true":"false");failures+=!passed;
}
static void observe_message(int fd,pid_t pid,const char *name,const char *stage,char want,uid_t uid,int flags) {
    char byte=0;struct iovec iov={&byte,1};
    union { struct cmsghdr align;char bytes[256]; } control={0};
    struct msghdr msg={.msg_iov=&iov,.msg_iovlen=1,.msg_control=control.bytes,.msg_controllen=sizeof(control.bytes)};
    errno=0;ssize_t rc=recvmsg(fd,&msg,flags);int error=errno,count=0;struct ucred c={0};
    for(struct cmsghdr *h=CMSG_FIRSTHDR(&msg);h;h=CMSG_NXTHDR(&msg,h)) {
        if(h->cmsg_level==SOL_SOCKET&&h->cmsg_type==SCM_CREDENTIALS&&h->cmsg_len==CMSG_LEN(sizeof(c))){memcpy(&c,CMSG_DATA(h),sizeof(c));count++;}
        else count+=100;
    }
    int passed=rc==1&&!error&&byte==want&&!(msg.msg_flags&MSG_CTRUNC)&&count==1&&c.pid==pid&&c.uid==uid&&c.gid==uid;
    printf("{\"transport\":\"%s\",\"message_stage\":\"%s\",\"rc\":%zd,\"errno\":%d,\"byte\":%u,\"credential_count\":%d,\"pid_matches\":%s,\"uid\":%u,\"gid\":%u,\"passed\":%s}\n",name,stage,rc,error,(unsigned char)byte,count,c.pid==pid?"true":"false",c.uid,c.gid,passed?"true":"false");failures+=!passed;
}
struct forged { long root_rc,other_rc;int root_error,other_error; };
static int after_exec(int ctl,int sender) {
    alarm(20);
    if(report(ctl)||send_credential(sender,'B',getpid(),getuid(),getgid())!=1||command(ctl,'F'))return 95;
    struct forged f={0};errno=0;f.root_rc=send_credential(sender,'X',getpid(),0,0);f.root_error=errno;
    errno=0;f.other_rc=send_credential(sender,'Y',getppid(),getuid(),getgid());f.other_error=errno;
    if(exact(ctl,&f,sizeof(f),1)||command(ctl,'Q'))return 96;
    close(sender);close(ctl);return 0;
}
static int actor(int ctl,int type,const char *self) {
    alarm(20);
    struct __user_cap_header_struct h={_LINUX_CAPABILITY_VERSION_3,0};struct __user_cap_data_struct c[2]={{0},{0}};
    if(setgroups(0,NULL)||setresgid(60001,60001,60002)||setresuid(60001,60001,60002)||syscall(SYS_capset,&h,c)||prctl(PR_SET_NO_NEW_PRIVS,1L,0L,0L,0L))return 90;
    int pair[2],one=1;
    if(socketpair(AF_UNIX,type,0,pair)||setsockopt(pair[1],SOL_SOCKET,SO_PASSCRED,&one,sizeof(one))||send_fd(ctl,pair[1]))return 91;
    close(pair[1]);
    if(report(ctl)||command(ctl,'G')||send_credential(pair[0],'A',getpid(),getuid(),getgid())!=1)return 92;
    if(setresgid(60002,60002,60001)||setresuid(60002,60002,60001)||report(ctl)||command(ctl,'E'))return 93;
    char ctl_arg[24],sender_arg[24];snprintf(ctl_arg,sizeof(ctl_arg),"%d",ctl);snprintf(sender_arg,sizeof(sender_arg),"%d",pair[0]);
    execl(self,self,"--after-exec",ctl_arg,sender_arg,(char *)NULL);return 94;
}
static int fixture(const char *name,int type,const char *self) {
    int ctl[2];if(socketpair(AF_UNIX,SOCK_STREAM,0,ctl))return -1;
    pid_t child=fork();if(child<0)return -1;
    if(!child){close(ctl[0]);_exit(actor(ctl[1],type,self));}
    close(ctl[1]);int fd=receive_fd(ctl[0]);
    check(name,"actual_rights_handoff_cloexec",fd>=0&&(fcntl(fd,F_GETFD)&FD_CLOEXEC));
    int failed_setup=fd<0||observe_identity(ctl[0],name,"initial",60001,60002);
    if(!failed_setup){observe_peer(fd,child,name,"created");failed_setup=send_command(ctl[0],'G')||observe_identity(ctl[0],name,"changed",60002,60001);}
    if(!failed_setup){
        observe_peer(fd,child,name,"after_identity_change");
        observe_message(fd,child,name,"queued_peek",'A',60001,MSG_PEEK);
        observe_message(fd,child,name,"queued_consume",'A',60001,0);
        failed_setup=send_command(ctl[0],'E')||observe_identity(ctl[0],name,"exec",60002,60002);
    }
    if(!failed_setup){
        observe_peer(fd,child,name,"after_exec");observe_message(fd,child,name,"new_after_exec",'B',60002,0);
        struct forged f;
        failed_setup=send_command(ctl[0],'F')||exact(ctl[0],&f,sizeof(f),0);
        if(!failed_setup){
            printf("{\"transport\":\"%s\",\"forged_root_rc\":%ld,\"root_errno\":%d,\"forged_parent_rc\":%ld,\"parent_errno\":%d}\n",name,f.root_rc,f.root_error,f.other_rc,f.other_error);
            check(name,"root_and_other_pid_credentials_rejected",f.root_rc==-1&&f.root_error==EPERM&&f.other_rc==-1&&f.other_error==EPERM);
            char byte;errno=0;ssize_t n=recv(fd,&byte,1,MSG_DONTWAIT);int error=errno;
            check(name,"rejected_credentials_publish_no_payload",n==-1&&(error==EAGAIN||error==EWOULDBLOCK));
            failed_setup=send_command(ctl[0],'Q');
        }
    }
    if(failed_setup){check(name,"fixture_completed",0);kill(child,SIGKILL);}
    int status=-1;pid_t got;do{got=waitpid(child,&status,0);}while(got<0&&errno==EINTR);
    check(name,"owned_child_reaped",got==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    if(!failed_setup)observe_peer(fd,child,name,"after_sender_exit");
    if(fd>=0)close(fd);close(ctl[0]);return failed_setup?-1:0;
}
int main(int argc,char **argv) {
    if(argc==4&&!strcmp(argv[1],"--after-exec"))return after_exec(atoi(argv[2]),atoi(argv[3]));
    setvbuf(stdout,NULL,_IOLBF,0);alarm(60);
    if(geteuid()!=0){fputs("Root only for owned credential fixture construction\n",stderr);return 77;}
    puts("{\"suite\":\"socket-credential-lifetime-v1\",\"maximum_live_children\":1,\"production_qualified\":false}");
    int incomplete=0;incomplete+=fixture("stream",SOCK_STREAM,argv[0])!=0;
    incomplete+=fixture("datagram",SOCK_DGRAM,argv[0])!=0;
    incomplete+=fixture("seqpacket",SOCK_SEQPACKET,argv[0])!=0;
    printf("{\"summary\":true,\"failures\":%u,\"incomplete_fixtures\":%d,\"reaped_fixtures\":%d}\n",failures,incomplete,3-incomplete);
    return failures||incomplete?42:0;
}
