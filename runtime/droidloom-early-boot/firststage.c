// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "board.h"
#include "custody.h"
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/magic.h>
#include <linux/sched.h>
#include <poll.h>
#include <signal.h>
#include <sched.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/xattr.h>
#include <unistd.h>

#define HANDOFF "/run/droidloom-early"
#define SLOT "/run/droidloom-early-slot"
#define FIFO HANDOFF "/release"
#define INIT "/system/bin/init"
struct droidloom_release_phase { char sha[65], nonce[65]; };
extern void droidloom_cancel_unpublished_resource_handles(void);
extern int droidloom_publish_resource_handles(pid_t,const struct droidloom_release_phase*,int);

static int failure(int e){errno=e;return -1;}
static int receive_one(int fd,char expected) {
    char byte=0;ssize_t n;
    do {n=read(fd,&byte,1);} while(n<0 && errno==EINTR);
    return n==1 && byte==expected ? 0:failure(EPROTO);
}
static int send_one(int fd,char value) {
    ssize_t n;
    do{n=write(fd,&value,1);}while(n<0&&errno==EINTR);
    return n==1?0:-1;
}
static int root_directory(const char* path,mode_t mode) {
    if(mkdir(path,mode)==0) {if(chmod(path,mode))return -1;}
    else if(errno!=EEXIST)return -1;
    struct stat st;struct statfs fs;
    if(lstat(path,&st)||statfs(path,&fs))return -1;
    return S_ISDIR(st.st_mode)&&st.st_uid==0&&st.st_gid==0&&(st.st_mode&07777)==mode&&fs.f_type==TMPFS_MAGIC
        ?0:failure(EACCES);
}
static int prepare_observer_directory(gid_t observed_group) {
    int parent=open(HANDOFF,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(parent<0)return -1;
    int created=mkdirat(parent,"readiness",0700)==0;
    if(!created&&errno!=EEXIST){int e=errno;close(parent);return failure(e);}
    int directory=openat(parent,"readiness",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    int e=directory<0?errno:0;
    if(!e&&created&&(fchown(directory,0,observed_group)||fchmod(directory,02710)))e=errno;
    struct stat a,b;struct statx x,y;
    if(!e&&(fstat(parent,&a)||fstat(directory,&b)||
        statx(parent,"",AT_EMPTY_PATH,STATX_MNT_ID,&x)||statx(directory,"",AT_EMPTY_PATH,STATX_MNT_ID,&y)))e=errno;
    if(!e&&(!(x.stx_mask&STATX_MNT_ID)||!(y.stx_mask&STATX_MNT_ID)||x.stx_mnt_id!=y.stx_mnt_id||
        a.st_dev!=b.st_dev||!S_ISDIR(b.st_mode)||b.st_uid||b.st_gid!=observed_group||(b.st_mode&07777)!=02710))e=EACCES;
    if(!e){
        DIR *entries=fdopendir(directory);
        if(!entries)e=errno;
        else{
            directory=-1;
            errno=0;struct dirent *row;
            while((row=readdir(entries))!=NULL){
                if(strcmp(row->d_name,".")&&strcmp(row->d_name,"..")){e=ENOTEMPTY;break;}
            }
            if(!e&&errno)e=errno;
            closedir(entries);
        }
    }
    if(directory>=0)close(directory);
    if(e&&created)unlinkat(parent,"readiness",AT_REMOVEDIR);
    close(parent);
    return e?failure(e):0;
}
static int maps(pid_t pid,const char *name,uint32_t start,uint32_t span) {
    char path[100],range[100];
    snprintf(path,sizeof path,"/proc/%d/%s",pid,name);
    int bytes=snprintf(range,sizeof range,"0 %u %u\n",start,span);
    int fd=open(path,O_WRONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)return -1;
    ssize_t w=write(fd,range,(size_t)bytes);int e=errno;close(fd);
    if(w!=bytes)return failure(w<0?e:EIO);
    fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)return -1;
    char actual[200],extra;
    ssize_t n=read(fd,actual,sizeof actual-1);e=errno;close(fd);
    if(n<0)return failure(e);
    actual[n]=0;
    unsigned a,b,c;
    return sscanf(actual," %u %u %u %c",&a,&b,&c,&extra)==3&&a==0&&b==start&&c==span?0:failure(ESTALE);
}
static int random_phase(struct droidloom_release_phase *p,const char *sha) {
    unsigned char random[32];
    size_t offset=0;
    while(offset<sizeof random) {
        ssize_t n=getrandom(random+offset,sizeof random-offset,0);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)return -1;
        offset+=(size_t)n;
    }
    memcpy(p->sha,sha,65);
    for(size_t i=0;i<sizeof random;i++)snprintf(p->nonce+i*2,3,"%02x",random[i]);
    return 0;
}
static int next_release_step(int fd,const struct droidloom_release_phase *p) {
    char expected[180],response[181];
    struct pollfd waiting={.fd=fd,.events=POLLIN};
    for(;;){
        int r=poll(&waiting,1,-1);
        if(r<0&&errno==EINTR)continue;
        if(r<0)return -1;
        if(waiting.revents&POLLIN)break;
        if(waiting.revents&POLLHUP){usleep(100000);continue;}
        return failure(EPIPE);
    }
    ssize_t got;
    do{got=read(fd,response,sizeof response);}while(got<0&&errno==EINTR);
    for(int step=1;step<=2;step++){
        const char *tag=step==1?"DROIDLOOM_EARLY_CGROUP_V1":"DROIDLOOM_EARLY_RELEASE_V1";
        int length=snprintf(expected,sizeof expected,"%s %s %s\n",tag,p->sha,p->nonce);
        if(got==length && memcmp(response,expected,(size_t)length)==0)return step;
    }
    return failure(EBADMSG);
}
static int confirmed_original(int root,int *out) {
    int sys=openat(root,"system",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(sys<0)return -1;
    int bin=openat(sys,"bin",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);close(sys);
    if(bin<0)return -1;
    int fd=openat(bin,"init",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);close(bin);
    if(fd<0)return -1;
    struct stat st; struct statfs fs; char label[128];
    static const char original[]="u:object_r:init_exec:s0";
    ssize_t n=fgetxattr(fd,"security.selinux",label,sizeof label);
    if(n==(ssize_t)sizeof original&&label[n-1]==0)n--;
    if(fstat(fd,&st)||fstatfs(fd,&fs)||!S_ISREG(st.st_mode)||(st.st_mode&07777)!=0755||
        st.st_uid!=0||st.st_gid!=2000||!(fs.f_flags&MS_RDONLY)||n!=(ssize_t)strlen(original)||
        memcmp(original,label,strlen(original))||droidloom_early_original_elf(fd)) {
        int e=errno?errno:ESTALE;close(fd);return failure(e);
    }
    *out=fd;return 0;
}
static void log_error(const char *name){dprintf(STDERR_FILENO,"droidloom early boot: %s: %s\n",name,strerror(errno));}
static int child_main(int maps_ready,int prepared,int fifo,const struct droidloom_release_phase *p) {
    if(getpid()!=1||receive_one(maps_ready,'M')||setresgid(0,0,0)||setresuid(0,0,0))return -1;
    /* Android init and Zygote assign supplementary AIDs when dropping credentials. */
    if(getgroups(0,NULL)!=0)return failure(EACCES);
    if(setgroups(0,NULL)<0 || getgroups(0,NULL)!=0)return failure(EPERM);
    close(maps_ready);
    if(mount(NULL,"/",NULL,MS_REC|MS_PRIVATE,NULL)||
       mount("tmpfs",SLOT,"tmpfs",MS_NODEV|MS_NOSUID|MS_NOEXEC,"mode=0700")||
       mkdir(SLOT "/rootfs",0700))return -1;
    if(send_one(prepared,'S'))return -1;
    close(prepared);
    if(next_release_step(fifo,p)!=1)return failure(EPROTO);
    if(unshare(CLONE_NEWCGROUP))return -1;
    int step;
    do{step=next_release_step(fifo,p);}while(step==1);
    if(step!=2 || prctl(PR_SET_DUMPABLE,0))return failure(EPROTO);
    close(fifo);
    int root=open(SLOT "/rootfs",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(root<0)return -1;
    int init=-1;
    if(confirmed_original(root,&init)||droidloom_board_enter(root))return -1;
    struct stat expected,effective;
    if(fstat(init,&expected)||stat(INIT,&effective)||expected.st_dev!=effective.st_dev||expected.st_ino!=effective.st_ino)return failure(ESTALE);
    close(root);
    if(syscall(SYS_close_range,3U,~0U,CLOSE_RANGE_CLOEXEC)<0)return -1;
    char *const args[]={INIT,"second_stage",NULL};
    char *const env[]={"PATH=/system/bin:/system/xbin","ANDROID_ROOT=/system","ANDROID_DATA=/data",NULL};
    signal(SIGPIPE,SIG_DFL);
    close(0);close(1);close(2);
    return (int)syscall(SYS_execveat,init,"",args,env,AT_EMPTY_PATH);
}
int main(int argc,char **argv) {
    (void)argv;
    if(argc!=1||geteuid()!=0){errno=EINVAL;log_error("requires the unparameterized root initramfs entry");return 1;}
    signal(SIGPIPE,SIG_IGN);
    struct droidloom_early_plan plan;
    int selected=droidloom_early_read_plan(&plan);
    if(selected<0){log_error("selected Ubuntu release");return 1;}
    if(!selected)return 0;
    if(root_directory(HANDOFF,0700)||root_directory(SLOT,0711)){log_error("private /run delivery");return 1;}
    int lock=open(HANDOFF "/startup.lock",O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_CREAT,0400);
    struct stat owner;
    if(lock<0||fstat(lock,&owner)||!S_ISREG(owner.st_mode)||owner.st_uid||owner.st_gid||
        owner.st_nlink!=1||(owner.st_mode&07777)!=0400||flock(lock,LOCK_EX|LOCK_NB)) {
        log_error("private early startup owner");return 1;
    }
    if(access(HANDOFF "/generation.json",F_OK)==0){errno=EALREADY;log_error("an early generation already owns this boot");return 1;}
    if(errno!=ENOENT){log_error("check existing root generation");return 1;}
    if(root_directory(HANDOFF "/private-dev",0700)){log_error("empty private device mountpoint");return 1;}
    if(prepare_observer_directory(plan.gid_start+9999)){log_error("rooted empty observer directory");return 1;}
    if(mkfifo(FIFO,0600)<0){log_error("new release FIFO");return 1;}
    int fifo=open(FIFO,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
    struct droidloom_release_phase phase;
    int channel[2], prepared[2];
    if(fifo<0||random_phase(&phase,plan.selection_sha256)||pipe2(channel,O_CLOEXEC)||pipe2(prepared,O_CLOEXEC)){
        log_error("prepare original child");unlink(FIFO);return 1;
    }
    /* A new user namespace inherits the caller's kernel group list unchanged. */
    if(setgroups(0,NULL)<0 || getgroups(0,NULL)!=0){
        log_error("clear Linux supplementary groups before creating Android PID 1");
        unlink(FIFO);
        return 1;
    }
    int pidfd=-1;
    struct clone_args args={.flags=CLONE_NEWPID|CLONE_NEWNS|CLONE_NEWNET|CLONE_NEWIPC|CLONE_NEWUTS|CLONE_NEWUSER|CLONE_NEWCGROUP|CLONE_PIDFD,
        .pidfd=(uint64_t)(uintptr_t)&pidfd,.exit_signal=SIGCHLD};
    pid_t pid=(pid_t)syscall(SYS_clone3,&args,sizeof args);
    if(!pid) {
        close(lock);close(channel[1]);close(prepared[0]);
        int status=child_main(channel[0],prepared[1],fifo,&phase);
        if(status<0)log_error("original shared-kernel Android child");
        _exit(121);
    }
    close(channel[0]);close(prepared[1]);
    if(pid<0){log_error("create original isolated PID 1");unlink(FIFO);return 1;}
    int pins=0;
    int status=maps(pid,"uid_map",plan.uid_start,plan.uid_count);
    if(!status)status=maps(pid,"gid_map",plan.gid_start,plan.gid_count);
    if(!status)status=send_one(channel[1],'M');
    if(!status)status=receive_one(prepared[0],'S');
    if(!status){
        status=droidloom_publish_resource_handles(pid,&phase,fifo);
        pins=(status==0);
    }
    if(!status)status=droidloom_publish_selected_child(pid,pidfd,plan.selection_sha256);
    if(status) {
        log_error("publish the original waiting cell");
        syscall(SYS_pidfd_send_signal,pidfd,SIGKILL,NULL,0);
        while(waitpid(pid,NULL,0)<0&&errno==EINTR){}
        if(pins)droidloom_cancel_unpublished_resource_handles();
        unlink(FIFO);return 1;
    }
    close(fifo);close(pidfd);close(channel[1]);close(prepared[0]);close(lock);
    /* Linux PID1 adopts the suspended process and continues the ordinary Ubuntu
     * boot. Only the later selected resource owner can release this FIFO. */
    return 0;
}
