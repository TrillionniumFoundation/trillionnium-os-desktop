// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/mount.h>
#include <linux/nsfs.h>
#include <poll.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static int fail(int value) { errno=value; return -1; }

/* Query a file's actual mount, including anonymous mounts which cannot be
 * looked up by path in the manager's mount namespace. */
static int held_mount(int fd, struct statmount *result) {
    struct mnt_id_req req = {.size=sizeof(req),.mnt_fd=(unsigned)fd,
                             .param=STATMOUNT_MNT_BASIC|STATMOUNT_MNT_NS_ID};
    if (syscall(SYS_statmount,&req,result,sizeof(*result),STATMOUNT_BY_FD)) return -1;
    if (!(result->mask & STATMOUNT_MNT_BASIC) || !result->mnt_id) return fail(EPROTO);
    return 0;
}
static int exited(int pidfd) {
    struct statfs fs;
    if(fstatfs(pidfd,&fs))return -1;
    if((unsigned long)fs.f_type != 0x50494446UL)return fail(ESTALE);
    struct pollfd check={.fd=pidfd,.events=POLLIN};
    int n;
    do {n=poll(&check,1,0);} while(n<0 && errno==EINTR);
    if(n<0)return -1;
    return n==1 && (check.revents&POLLIN) && !(check.revents&(POLLNVAL|POLLERR)) ? 0 : fail(EBUSY);
}

int droidloom_board_retire_root(int pidfd,int nsfd,int rootfd) {
    if(geteuid()!=0)return fail(EPERM);
    if(exited(pidfd))return -1;
    if(ioctl(nsfd,NS_GET_NSTYPE)!=CLONE_NEWNS)return fail(ESTALE);
    uint64_t nsid=0;
    if(ioctl(nsfd,NS_GET_MNTNS_ID,&nsid)||!nsid)return -1;
    struct statmount original={0};
    if(held_mount(rootfd,&original))return -1;
    if(!(original.mask&STATMOUNT_MNT_NS_ID) || !original.mnt_ns_id)return exited(pidfd);
    if(original.mnt_ns_id!=nsid ||
        original.mnt_propagation!=MS_PRIVATE)return fail(ESTALE);
    int result[2]; if(pipe2(result,O_CLOEXEC))return -1;
    char path[64];
    int len=snprintf(path,sizeof(path),"/proc/self/fd/%d",rootfd);
    if(len<=0 || (size_t)len>=sizeof(path)) {close(result[0]);close(result[1]);return fail(EOVERFLOW);}
    pid_t worker=fork();
    if(worker==0){
        close(result[0]);int e=0;
        if(setns(nsfd,CLONE_NEWNS) || exited(pidfd) || umount2(path,MNT_DETACH))e=errno;
        ssize_t n;do{n=write(result[1],&e,sizeof(e));}while(n<0&&errno==EINTR);
        _exit(n==sizeof(e)?0:1);
    }
    int e=worker<0?errno:0;
    close(result[1]);
    if(worker>0){
        int result_errno=0,status=0;ssize_t n;pid_t w;
        do{n=read(result[0],&result_errno,sizeof(result_errno));}while(n<0&&errno==EINTR);
        do{w=waitpid(worker,&status,0);}while(w<0&&errno==EINTR);
        e=w==worker&&WIFEXITED(status)&&WEXITSTATUS(status)==0&&n==sizeof(result_errno)?result_errno:EIO;
    }
    close(result[0]);if(e)return fail(e);
    struct statmount now={0}; if(held_mount(rootfd,&now))return -1;
    if(now.mnt_id!=original.mnt_id || ((now.mask&STATMOUNT_MNT_NS_ID) && now.mnt_ns_id))return fail(EBUSY);
    return exited(pidfd);
}

/* Query the original mount namespace by descriptor. Record IDs, not path file
 * descriptors, so the witness itself cannot make Android's normal umount busy. */
int droidloom_board_storage_state(int nsfd, uint64_t id, int expect_present) {
    if (!id || ioctl(nsfd, NS_GET_NSTYPE) != CLONE_NEWNS) return fail(EINVAL);
    uint64_t namespace_id = 0;
    if (ioctl(nsfd, NS_GET_MNTNS_ID, &namespace_id) || !namespace_id) return -1;
    struct mnt_id_req req = {.size=sizeof(req), .mnt_ns_fd=(unsigned)nsfd,
                             .mnt_id=id, .param=STATMOUNT_MNT_BASIC|STATMOUNT_MNT_NS_ID};
    struct statmount out = {0};
    if (syscall(SYS_statmount, &req, &out, sizeof(out), 0) < 0) {
        if (!expect_present && errno == ENOENT) return 0;
        return -1;
    }
    if ((out.mask & req.param) != req.param || out.mnt_ns_id != namespace_id || out.mnt_id != id)
        return fail(ESTALE);
    return expect_present ? 0 : fail(EBUSY);
}
static int unique_mount_id(int fd, uint64_t *id) {
    struct statx st = {0};
    if (statx(fd, "", AT_EMPTY_PATH, STATX_MNT_ID_UNIQUE, &st)) return -1;
    if (!(st.stx_mask & STATX_MNT_ID_UNIQUE) || !st.stx_mnt_id) return fail(ESTALE);
    *id = st.stx_mnt_id;
    return 0;
}
int droidloom_board_storage_id(int fd, uint64_t *id) {
    struct statfs fs;
    struct statvfs flags;
    if (fstatfs(fd, &fs) || fstatvfs(fd, &flags)) return -1;
    if (fs.f_type != EXT4_SUPER_MAGIC || flags.f_flag & ST_RDONLY) return fail(ESTALE);
    return unique_mount_id(fd, id);
}
