// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "custody.h"
#include "board.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <openssl/evp.h>
#include <sys/stat.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <unistd.h>
#define VALIDATOR "/usr/lib/droidloom/production/current/droidloomd"
struct dl_pidinfo {uint64_t mask,cgroup;uint32_t pid,tgid,ppid,ruid,rgid,euid,egid,suid,sgid,fsuid,fsgid;int32_t exit_code;};
_Static_assert(sizeof(struct dl_pidinfo)==64,"pidfs v0 ABI");
extern int droidloom_publish_early_child(pid_t,int,const char*);

static int verifier(const char *action,int input,char *out,size_t capacity) {
    int channel[2], status=0;
    if (pipe2(channel,O_CLOEXEC)!=0) return -1;
    pid_t validator=fork();
    if (validator==0) {
        if (dup2(channel[1],STDOUT_FILENO)<0 || (input>=0 && dup2(input,STDIN_FILENO)<0)) _exit(125);
        close(channel[0]);close(channel[1]);
        char *const args[]={VALIDATOR,(char*)action,NULL};
        char *const env[]={"PATH=/usr/bin:/bin","LC_ALL=C",NULL};
        execve(VALIDATOR,args,env);_exit(126);
    }
    int error=validator<0?errno:0;
    close(channel[1]);
    size_t n=0;
    if (!error) while (n<capacity) {
        ssize_t got=read(channel[0],out+n,capacity-n);
        if (got<0 && errno==EINTR) continue;
        if (got<0) error=errno;
        if (got<=0) break;
        n+=(size_t)got;
    }
    close(channel[0]);
    if (validator>0) {
        pid_t done;
        do {done=waitpid(validator,&status,0);} while (done<0 && errno==EINTR);
        if (done!=validator || !WIFEXITED(status) || WEXITSTATUS(status)!=0)
            error=error?error:EACCES;
    }
    if(!error && n==capacity)error=EOVERFLOW;
    if(error){errno=error;return -1;}
    out[n]=0;
    return (int)n;
}

static int digest_text(const char *s) {return strlen(s)==64 && strspn(s,"0123456789abcdef")==64;}
int droidloom_early_read_plan(struct droidloom_early_plan *plan) {
    char out[256],tail;
    int n=verifier("--initramfs-board-plan",-1,out,sizeof out-1);
    if(n<0)return -1;
    if(!n)return 0;
    if(out[n-1]!='\n'){errno=EBADMSG;return -1;}
    out[n-1]=0;
    if(sscanf(out,"%64s %64s %u %u %u %u %u%c",plan->selection_sha256,plan->base_cohort_sha256,
            &plan->host_uid,&plan->uid_start,&plan->uid_count,&plan->gid_start,&plan->gid_count,&tail)!=7 ||
       !digest_text(plan->selection_sha256)||!digest_text(plan->base_cohort_sha256)||!plan->host_uid||
       !plan->uid_start||!plan->gid_start||plan->uid_count<=9999||plan->gid_count<=9999||
       (uint64_t)plan->uid_start+plan->uid_count>UINT32_MAX||
       (uint64_t)plan->gid_start+plan->gid_count>UINT32_MAX){errno=EBADMSG;return -1;}
    return 1;
}
int droidloom_early_original_elf(int fd) {
    static const unsigned char expected[32]={
        0x9f,0x69,0xcc,0x83,0xa8,0x8d,0xb5,0xf8,0x53,0x30,0x14,0xcf,0xea,0x5a,0xd9,0xea,
        0x8e,0x04,0x54,0x12,0x03,0x35,0x32,0x9a,0xec,0x27,0xf8,0xd6,0x5b,0x2a,0x95,0x37};
    struct stat before,after;
    if(fstat(fd,&before)||!S_ISREG(before.st_mode)||before.st_size!=2934488){errno=EINVAL;return -1;}
    EVP_MD_CTX *digest=EVP_MD_CTX_new();
    if(!digest){errno=ENOMEM;return -1;}
    unsigned char buffer[32768],actual[EVP_MAX_MD_SIZE];
    unsigned int count=0;off_t offset=0;
    int good=EVP_DigestInit_ex(digest,EVP_sha256(),NULL)==1;
    while(good&&offset<before.st_size) {
        ssize_t got=pread(fd,buffer,sizeof buffer,offset);
        if(got<0&&errno==EINTR)continue;
        if(got<=0){good=0;break;}
        good=EVP_DigestUpdate(digest,buffer,(size_t)got)==1;
        offset+=got;
    }
    if(good)good=EVP_DigestFinal_ex(digest,actual,&count)==1&&count==32&&memcmp(actual,expected,32)==0;
    EVP_MD_CTX_free(digest);
    if(!good||fstat(fd,&after)||after.st_dev!=before.st_dev||after.st_ino!=before.st_ino||
        after.st_size!=before.st_size||after.st_ctim.tv_sec!=before.st_ctim.tv_sec||
        after.st_ctim.tv_nsec!=before.st_ctim.tv_nsec){errno=ESTALE;return -1;}
    return 0;
}
int droidloom_publish_selected_child(pid_t child,int clone_pidfd,const char *prepared) {
    struct dl_pidinfo info={.mask=1};
    if(child<=1||geteuid()!=0||!prepared||!digest_text(prepared)){errno=EINVAL;return -1;}
    if(ioctl(clone_pidfd,_IOWR(0xff,11,struct dl_pidinfo),&info)<0)return -1;
    if(!(info.mask&1)||info.tgid!=(uint32_t)child||info.pid!=(uint32_t)child||info.ppid!=(uint32_t)getpid()){
        errno=ECHILD;return -1;
    }
    char sha[67];
    int n=verifier("--initramfs-selected-generation",-1,sha,sizeof sha-1);
    if(n<0)return -1;
    if(n!=65||sha[64]!='\n'){errno=EBADMSG;return -1;}
    sha[64]=0;
    if(strcmp(prepared,sha)){errno=ESTALE;return -1;}
    return droidloom_publish_early_child(child,clone_pidfd,sha);
}
