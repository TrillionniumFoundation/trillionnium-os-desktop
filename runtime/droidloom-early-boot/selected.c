// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "custody.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/types.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <unistd.h>

#define RELEASE_VERIFIER "/usr/lib/droidloom/production/current/droidloomd"
struct dl_pidinfo {
    uint64_t mask, cgroup;
    uint32_t pid,tgid,ppid,ruid,rgid,euid,egid,suid,sgid,fsuid,fsgid;
    int32_t exit_code;
};
_Static_assert(sizeof(struct dl_pidinfo)==64, "pidfs v0 ABI");
extern int droidloom_publish_early_child(pid_t,int,const char *);

static int dl_selection(char out[66]) {
    int channel[2], status=0;
    if (pipe2(channel,O_CLOEXEC)!=0) return -1;
    pid_t validator = fork();
    if (validator==0) {
        if (dup2(channel[1],STDOUT_FILENO)<0) _exit(125);
        close(channel[0]); close(channel[1]);
        char *const argv[] = {RELEASE_VERIFIER,"--initramfs-selected-generation",NULL};
        char *const env[] = {"PATH=/usr/bin:/bin","LC_ALL=C",NULL};
        execve(RELEASE_VERIFIER,argv,env);
        _exit(126);
    }
    int error=validator<0 ? errno : 0;
    close(channel[1]);
    size_t n=0;
    if (!error) {
        while (n<66) {
            ssize_t got=read(channel[0],out+n,66-n);
            if (got<0 && errno==EINTR) continue;
            if (got<0) error=errno;
            if (got<=0) break;
            n+=(size_t)got;
        }
    }
    close(channel[0]);
    if (validator>0) {
        pid_t done;
        do {done=waitpid(validator,&status,0);} while (done<0 && errno==EINTR);
        if (done!=validator || !WIFEXITED(status) || WEXITSTATUS(status)!=0)
            error=error ? error : EACCES;
    }
    if (!error && !n) error=ENODATA;
    if (!error && (n!=65 || out[64]!='\n')) error=EBADMSG;
    if (!error) {
        out[64]=0;
        if (strspn(out,"0123456789abcdef")!=64) error=EBADMSG;
    }
    if (error) {errno=error; return -1;}
    return 0;
}

int droidloom_publish_selected_child(pid_t child,int clone_pidfd) {
    struct dl_pidinfo info={.mask=1};
    if (child<=1 || geteuid()!=0) {errno=EINVAL;return -1;}
    if (ioctl(clone_pidfd,_IOWR(0xff,11,struct dl_pidinfo),&info)<0) return -1;
    if (!(info.mask&1) || info.tgid!=(uint32_t)child || info.pid!=(uint32_t)child ||
        info.ppid!=(uint32_t)getpid()) {errno=ECHILD;return -1;}
    char sha[66];
    if (dl_selection(sha)<0) return -1;
    return droidloom_publish_early_child(child,clone_pidfd,sha);
}
