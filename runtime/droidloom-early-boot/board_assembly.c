// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/mount.h>
#include <linux/openat2.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/xattr.h>
#include <unistd.h>
#include "board_cgroup.h"

static int fail(int value) {errno=value; return -1;}
static int beneath(int fd,const char *name) {
    struct open_how how={.flags=O_RDONLY|O_DIRECTORY|O_CLOEXEC,
        .resolve=RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS|RESOLVE_NO_MAGICLINKS};
    return syscall(SYS_openat2,fd,name,&how,sizeof(how));
}
static int mount_id(int fd,uint64_t *id){
    struct statx s={0};
    if(statx(fd,"",AT_EMPTY_PATH,STATX_MNT_ID_UNIQUE,&s) || !(s.stx_mask&STATX_MNT_ID_UNIQUE))return fail(ESTALE);
    *id=s.stx_mnt_id;return 0;
}
static int fs_is(int fd,long magic) {
    struct statfs s;if(fstatfs(fd,&s))return -1;return s.f_type==magic?0:fail(ESTALE);
}
static int attr(int fd,uint64_t flags) {
    struct mount_attr select={.attr_set=flags};
    return syscall(SYS_mount_setattr,fd,"",AT_EMPTY_PATH,&select,sizeof(select));
}
/* On return, even when move_mount succeeded before a later check failed, all
 * mounts are retained by the detached root and its existing typed owners. */
static int attach_held(int parent,const char *path,int target,int source) {
    uint64_t before=0,old=0,selected=0;struct stat sa,sb;
    int error=0;
    if(mount_id(parent,&before)||mount_id(target,&old)||mount_id(source,&selected)||fstat(source,&sa))error=errno;
    else if(old!=before||selected==old)error=EBUSY;
    else if(syscall(SYS_move_mount,source,"",target,"",MOVE_MOUNT_F_EMPTY_PATH|MOVE_MOUNT_T_EMPTY_PATH))error=errno;
    if(!error) {
        target=beneath(parent,path);
        if(target<0)error=errno;
        else {
            uint64_t now=0;
            if(mount_id(target,&now)||fstat(target,&sb))error=errno;
            else if(now!=selected || sa.st_dev!=sb.st_dev || sa.st_ino!=sb.st_ino)error=ESTALE;
            close(target);
        }
    }
    return error?fail(error):0;
}
static int attach(int parent,const char *path,int source) {
    int target=beneath(parent,path);if(target<0)return -1;
    int rc=attach_held(parent,path,target,source),error=errno;
    close(target);
    return rc?fail(error):0;
}
static int directory_label(int fd, const char *expected) {
    char value[128] = {0};
    int readable = beneath(fd, ".");
    if (readable < 0)
        return -1;
    uint64_t original, opened;
    if (mount_id(fd, &original) || mount_id(readable, &opened) || original != opened) {
        close(readable);
        return fail(ESTALE);
    }
    ssize_t got = fgetxattr(readable, "security.selinux", value, sizeof(value));
    int cause = errno;
    close(readable);
    errno = cause;
    if (got < 0)
        return -1;
    size_t n = strlen(expected);
    if ((got != (ssize_t)n && got != (ssize_t)(n + 1)) ||
        memcmp(value, expected, n + 1) != 0)
        return fail(ESTALE);
    return 0;
}

static int subtree(int directory,uint64_t flags){
    int f=syscall(SYS_open_tree,directory,"",OPEN_TREE_CLONE|OPEN_TREE_CLOEXEC|AT_EMPTY_PATH);
    if(f<0)return -1;
    if(attr(f,flags)){int e=errno;close(f);return fail(e);}
    return f;
}
static int fresh_tmpfs(unsigned uid,unsigned gid,const char *size,const char *nodes,uint64_t flags) {
    int ctx=syscall(SYS_fsopen,"tmpfs",FSOPEN_CLOEXEC);if(ctx<0)return -1;
    char u[16],g[16];snprintf(u,sizeof(u),"%u",uid);snprintf(g,sizeof(g),"%u",gid);
    const char *keys[]={"uid","gid","mode","size","nr_inodes"};
    const char *vals[]={u,g,"0755",size,nodes};
    int error=0,descriptor=-1;
    for(unsigned i=0;i<sizeof(keys)/sizeof(keys[0]);++i)
        if(syscall(SYS_fsconfig,ctx,FSCONFIG_SET_STRING,keys[i],vals[i],0)){error=errno;break;}
    if(!error && syscall(SYS_fsconfig,ctx,FSCONFIG_CMD_CREATE,NULL,NULL,0)) error=errno;
    if(!error && (descriptor=syscall(SYS_fsmount,ctx,FSMOUNT_CLOEXEC,flags))<0)error=errno;
    close(ctx);return error?fail(error):descriptor;
}
static int mkdir_held(int parent,const char *name,mode_t mode){
    if(mkdirat(parent,name,mode))return -1;
    int fd=beneath(parent,name);if(fd<0)return -1;
    if(fchmod(fd,mode)){int e=errno;close(fd);return fail(e);}
    return fd;
}
/* The original init mounts cgroup2 itself after the host has bound its PID
 * to a private, payload-rooted cgroup namespace. Only the empty sysfs
 * mountpoint is exported. A cgroup2 bind here would make that mount EBUSY. */
static int attach_guest_cgroup(int root, int payload) {
    const uint64_t restricted = MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV | MOUNT_ATTR_NOEXEC;
    struct stat owner;
    if (fs_is(payload, CGROUP2_SUPER_MAGIC) || fstat(payload, &owner))
        return -1;
    if (!S_ISDIR(owner.st_mode) || owner.st_ino == 1)
        return fail(ESTALE);

    int sys = fresh_tmpfs(0, 0, "64k", "8", restricted);
    if (sys < 0)
        return -1;
    int fs = -1, destination = -1, point = -1, error = 0;
    if ((fs = mkdir_held(sys, "fs", 0555)) < 0 ||
        (destination = mkdir_held(fs, "cgroup", 0555)) < 0 ||
        (point = droidloom_original_cgroup_leaf()) < 0 ||
        attach_held(sys, "fs/cgroup", destination, point) ||
        attr(sys, MOUNT_ATTR_RDONLY) || attach(root, "sys", sys))
        error = errno;
    if (point >= 0)
        close(point);
    if (destination >= 0)
        close(destination);
    if (fs >= 0)
        close(fs);
    close(sys);
    return error ? fail(error) : 0;
}
static int ready_projection(int dev,int generation,uint32_t group,uint32_t uid,uint32_t gid) {
    if(fs_is(dev,TMPFS_MAGIC) || fs_is(generation,TMPFS_MAGIC))return -1;
    int ready=beneath(generation,"readiness");
    if(ready<0)return -1;
    struct stat info;uint64_t a=0,b=0;int error=0;
    char context[128]={0};
    const char expected[]="u:object_r:p4_linux_readiness_dir_t:s0";
    ssize_t ctx=fgetxattr(ready,"security.selinux",context,sizeof(context));
    if(fstat(ready,&info)||mount_id(generation,&a)||mount_id(ready,&b))error=errno;
    else if(a!=b||info.st_uid!=0||info.st_gid!=group||(info.st_mode&07777)!=02710||
            ctx<0 || ((size_t)ctx!=sizeof(expected) && (size_t)ctx!=sizeof(expected)-1) ||
            memcmp(context,expected,sizeof(expected))) error=ESTALE;
    int sock=-1,sub=-1,visible=-1;
    struct stat dev_st,sock_st,sub_st;
    uint64_t dev_id=0,sock_id=0,sub_id=0;
    if(!error && ((sock=beneath(dev,"socket"))<0 || (sub=beneath(sock,"droidloom"))<0 ||
       fstat(dev,&dev_st) || fstat(sock,&sock_st) || fstat(sub,&sub_st) ||
       mount_id(dev,&dev_id) || mount_id(sock,&sock_id) || mount_id(sub,&sub_id)))error=errno;
    if(!error && (dev_id!=sock_id || dev_id!=sub_id || dev_st.st_dev!=sock_st.st_dev ||
        dev_st.st_dev!=sub_st.st_dev || sock_st.st_uid!=uid || sock_st.st_gid!=gid ||
        sub_st.st_uid!=uid || sub_st.st_gid!=gid || (sock_st.st_mode&07777)!=0755 ||
        (sub_st.st_mode&07777)!=0755))error=ESTALE;
    if (!error && (directory_label(dev, "u:object_r:p4_linux_private_dev_root_t:s0") ||
                   directory_label(sock, "u:object_r:p4_linux_private_socket_parent_t:s0") ||
                   directory_label(sub, "u:object_r:p4_linux_readiness_mount_t:s0")))
        error = errno;
    if(!error && ((visible=subtree(ready,MOUNT_ATTR_RDONLY|MOUNT_ATTR_NOSUID|MOUNT_ATTR_NODEV|MOUNT_ATTR_NOEXEC))<0 ||
           attach_held(dev,"socket/droidloom",sub,visible)))error=errno;
    if(visible>=0)close(visible);
    if(sub>=0)close(sub);
    if(sock>=0)close(sock);
    close(ready);
    return error?fail(error):0;
}
int droidloom_board_assemble(int root,int dev,int data,int metadata,int payload,int generation,
                             uint32_t uid,uint32_t gid,uint32_t observer_gid) {
    if(geteuid()!=0)return fail(EPERM);
    if(fs_is(root,EXT4_SUPER_MAGIC)||fs_is(data,EXT4_SUPER_MAGIC)||fs_is(metadata,EXT4_SUPER_MAGIC)||
       ready_projection(dev,generation,observer_gid,uid,gid)||attach(root,"dev",dev)||
       attach(root,"data",data)||attach(root,"metadata",metadata)||attach_guest_cgroup(root,payload))return -1;
    /* These writable early-boot directories precede the stock second-stage
     * actions, which create their own additional layers. */
    const char *paths[]={"apex","linkerconfig","mnt","debug_ramdisk","second_stage_resources"};
    const unsigned flags[]={6,6,14,14,14};
    for(size_t i=0;i<sizeof(paths)/sizeof(paths[0]);++i) {
        if(i==2 && gid>UINT32_MAX-1000)return fail(EINVAL);
        int layer=fresh_tmpfs(uid,i==2?gid+1000:gid,"16m","4096",flags[i]);if(layer<0)return -1;
        int error=attach(root,paths[i],layer)?errno:0;
        close(layer);if(error)return fail(error);
    }
    return 0;
}
