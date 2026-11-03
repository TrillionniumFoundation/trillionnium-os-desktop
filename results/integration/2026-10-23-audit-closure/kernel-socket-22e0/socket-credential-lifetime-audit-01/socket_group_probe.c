#define main lifetime_probe_main
#include "socket_credential_probe.c"
#undef main
#ifndef SO_PEERGROUPS
#define SO_PEERGROUPS 59
#endif
struct group_report { struct identity identity; int count; gid_t groups[3]; };
static int group_report_send(int ctl) {
    struct group_report r={.identity=identity()};r.count=getgroups(3,r.groups);return exact(ctl,&r,sizeof(r),1);
}
static int group_report_read(int ctl,const char *name,const char *stage,int changed) {
    struct group_report r;
    if(exact(ctl,&r,sizeof(r),0))return -1;
    struct identity i=r.identity;
    int passed=!i.error&&i.uid==60001&&i.euid==60001&&i.suid==60001&&i.gid==60001&&i.egid==60001&&i.sgid==60001&&i.permitted==(1U<<CAP_SETGID)&&i.effective==(1U<<CAP_SETGID)&&i.nnp==1&&r.count==(changed?1:2)&&r.groups[0]==(gid_t)(changed?60005:60003)&&(changed||r.groups[1]==60004);
    printf("{\"transport\":\"%s\",\"stage\":\"%s\",\"uid\":%u,\"euid\":%u,\"gid\":%u,\"egid\":%u,\"permitted\":%llu,\"effective\":%llu,\"nnp\":%d,\"group_count\":%d,\"group0\":%u,\"group1\":%u,\"passed\":%s}\n",name,stage,i.uid,i.euid,i.gid,i.egid,(unsigned long long)i.permitted,(unsigned long long)i.effective,i.nnp,r.count,r.groups[0],r.groups[1],passed?"true":"false");
    failures+=!passed;return 0;
}
static void observe_groups(int fd,const char *name,const char *stage) {
    gid_t groups[3]={0};socklen_t size=sizeof(groups);errno=0;int rc=getsockopt(fd,SOL_SOCKET,SO_PEERGROUPS,groups,&size),error=errno;
    int passed=rc==0&&!error&&size==2*sizeof(gid_t)&&groups[0]==60003&&groups[1]==60004;
    printf("{\"transport\":\"%s\",\"peer_group_stage\":\"%s\",\"rc\":%d,\"errno\":%d,\"bytes\":%u,\"group0\":%u,\"group1\":%u,\"passed\":%s}\n",name,stage,rc,error,size,groups[0],groups[1],passed?"true":"false");failures+=!passed;
}
static int group_actor(int ctl,int type) {
    alarm(20);gid_t groups[2]={60003,60004};
    struct __user_cap_header_struct h={_LINUX_CAPABILITY_VERSION_3,0};struct __user_cap_data_struct caps[2]={{0},{0}};
    caps[0].effective=caps[0].permitted=1U<<CAP_SETGID;
    if(setgroups(2,groups)||prctl(PR_SET_KEEPCAPS,1L)||setresgid(60001,60001,60001)||setresuid(60001,60001,60001)||syscall(SYS_capset,&h,caps)||prctl(PR_SET_NO_NEW_PRIVS,1L,0L,0L,0L))return 90;
    int pair[2];if(socketpair(AF_UNIX,type,0,pair)||send_fd(ctl,pair[1]))return 91;close(pair[1]);
    if(group_report_send(ctl)||command(ctl,'G'))return 92;
    gid_t replacement=60005;
    if(setgroups(1,&replacement)||group_report_send(ctl)||command(ctl,'Q'))return 93;
    close(pair[0]);close(ctl);return 0;
}
static int group_fixture(const char *name,int type) {
    int ctl[2];if(socketpair(AF_UNIX,SOCK_STREAM,0,ctl))return -1;
    pid_t child=fork();if(child<0)return -1;
    if(!child){close(ctl[0]);_exit(group_actor(ctl[1],type));}
    close(ctl[1]);int fd=receive_fd(ctl[0]);check(name,"actual_rights_handoff_cloexec",fd>=0&&(fcntl(fd,F_GETFD)&FD_CLOEXEC));
    int bad=fd<0||group_report_read(ctl[0],name,"initial",0);
    if(!bad){observe_groups(fd,name,"created");bad=send_command(ctl[0],'G')||group_report_read(ctl[0],name,"changed",1);}
    if(!bad){observe_groups(fd,name,"after_group_change");bad=send_command(ctl[0],'Q');}
    if(bad){check(name,"fixture_completed",0);kill(child,SIGKILL);}
    int status=-1;pid_t got;do{got=waitpid(child,&status,0);}while(got<0&&errno==EINTR);
    check(name,"owned_child_reaped",got==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    if(!bad)observe_groups(fd,name,"after_sender_exit");
    if(fd>=0)close(fd);
    close(ctl[0]);return bad?-1:0;
}
int main(void) {
    setvbuf(stdout,NULL,_IOLBF,0);alarm(60);if(geteuid()!=0)return 77;
    puts("{\"suite\":\"socket-group-lifetime-v1\",\"maximum_live_children\":1,\"production_qualified\":false}");
    int incomplete=group_fixture("stream",SOCK_STREAM)!=0;
    incomplete+=group_fixture("seqpacket",SOCK_SEQPACKET)!=0;
    printf("{\"summary\":true,\"failures\":%u,\"incomplete_fixtures\":%d,\"reaped_fixtures\":%d}\n",failures,incomplete,2-incomplete);
    return failures||incomplete?42:0;
}
