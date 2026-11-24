// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/lsm.h>
#include <linux/nsfs.h>
#include <sched.h>
#include <sys/ioctl.h>
#include <sys/statvfs.h>
#include <poll.h>
#include <sys/mount.h>
#include <sys/statfs.h>
#include <sys/sysmacros.h>
#include <linux/magic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <sys/xattr.h>
#include "device_source.h"
#include "device_template.h"

static int fail(int error) { errno=error; return -1; }
static int boot_mount_namespace=-1;
static int mount_namespace_matches_self(int fd) {
    if(fd<0)return fail(EBADF);
    struct stat actual,own;
    struct statfs fs;
    if(fstat(fd,&actual)||fstatfs(fd,&fs)||stat("/proc/self/ns/mnt",&own))return -1;
    int flags=fcntl(fd,F_GETFL);
    if(flags<0)return -1;
    if(!S_ISREG(actual.st_mode)||actual.st_uid||actual.st_gid||fs.f_type!=NSFS_MAGIC||
       (flags&O_ACCMODE)!=O_RDONLY||(flags&O_PATH)||
       actual.st_dev!=own.st_dev||actual.st_ino!=own.st_ino)return fail(EXDEV);
    int kind=ioctl(fd,NS_GET_NSTYPE);
    if(kind!=CLONE_NEWNS)return fail(kind<0?errno:EINVAL);
    return 0;
}
static int take_boot_mount_namespace(void) {
    if(boot_mount_namespace>=0)return fail(EBUSY);
    /* Original real-root PID 1 supplies exactly fd 3 before exec. A mount
     * namespace cannot be bind-mounted inside itself, so its real held FD
     * remains the authority for the entire original factory lifetime. */
    if(mount_namespace_matches_self(3))return -1;
    int held=fcntl(3,F_DUPFD_CLOEXEC,64);
    if(held<0)return -1;
    if(close(3)){int error=errno;close(held);return fail(error);}
    boot_mount_namespace=held;
    return 0;
}
static int context(uint64_t id, const char *expected) {
    _Alignas(struct lsm_ctx) unsigned char buffer[512]={0};
    struct lsm_ctx *value=(struct lsm_ctx*)buffer;
    value->id=id;
    uint32_t bytes=sizeof(buffer);
    long count=syscall(SYS_lsm_get_self_attr,LSM_ATTR_CURRENT,value,&bytes,LSM_FLAG_SINGLE);
    if(count<0)return -1;
    size_t length=strlen(expected);
    if(count!=1||value->id!=id||bytes>sizeof(buffer)||bytes<sizeof(*value)||
       value->len<sizeof(*value)||value->len>bytes||value->ctx_len>value->len-sizeof(*value)||
       (value->ctx_len!=length&&value->ctx_len!=length+1)||
       memcmp(value->ctx,expected,(size_t)value->ctx_len))return fail(EACCES);
    return 0;
}
/* The ordinary manager enters a dedicated domain. It cannot be emulated with
 * argv, environment variables, a receipt, or a numeric external process ID. */
static int actor_context(const char *selinux,const char *apparmor,int no_new_privileges) {
    if(geteuid()!=0||getpid()<=1||getppid()!=1||prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=no_new_privileges)
        return fail(EPERM);
    if(context(LSM_ID_SELINUX,selinux)||
       context(LSM_ID_APPARMOR,apparmor))return -1;
    int fd=open("/sys/fs/selinux/enforce",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)return -1;
    char value[2]={0};
    ssize_t n=read(fd,value,sizeof(value));int error=errno;close(fd);
    if(n<0)return fail(error);
    if(n!=1||value[0]!='1')return fail(EACCES);
    /* Original Linux PID 1 publishes these three immutable NSFS bind mounts
     * before policy activation and before the factory fork, in the real root.
     * MNT is instead the original retained descriptor: self-MNT bind mounting
     * would create a namespace reference cycle and is rejected by Linux. */
    const char *names[]={"pid","user","cgroup"};
    const char *pins[]={"host-pidns","host-userns","host-cgroupns"};
    const int kinds[]={CLONE_NEWPID,CLONE_NEWUSER,CLONE_NEWCGROUP};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);i++){
        char own_path[64],pin_path[128];
        int own_length=snprintf(own_path,sizeof(own_path),"/proc/self/ns/%s",names[i]);
        int pin_length=snprintf(pin_path,sizeof(pin_path),"/run/droidloom-early/%s",pins[i]);
        if(own_length<=0||(size_t)own_length>=sizeof(own_path)||
           pin_length<=0||(size_t)pin_length>=sizeof(pin_path))return fail(EINVAL);
        int held=open(pin_path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
        if(held<0)return -1;
        struct stat self,original,named;
        struct statfs fs;
        int error=0;
        if(fstat(held,&original)||fstatfs(held,&fs)||stat(own_path,&self)||
           lstat(pin_path,&named))error=errno;
        const unsigned long required=ST_RDONLY|ST_NOSUID|ST_NODEV|ST_NOEXEC;
        if(!error&&(!S_ISREG(original.st_mode)||original.st_uid||original.st_gid||
           fs.f_type!=NSFS_MAGIC||((unsigned long)fs.f_flags&required)!=required||
           original.st_dev!=named.st_dev||original.st_ino!=named.st_ino||
           original.st_dev!=self.st_dev||original.st_ino!=self.st_ino))error=EXDEV;
        if(!error){
            int kind=ioctl(held,NS_GET_NSTYPE);
            if(kind!=kinds[i])error=kind<0?errno:EINVAL;
        }
        if(close(held)&&!error)error=errno;
        if(error)return fail(error);
    }
    return 0;
}

int droidloom_instance_context(void) {
    /* This first gate precedes the authenticated DLHOST01 exchange. The
     * caller must then pass its actual original factory MNT descriptor to
     * droidloom_instance_host_mount before either START or ADOPT. */
    return actor_context("u:r:droidloom_instance_launcher:s0","droidloom-instance-launcher (enforce)",1);
}
int droidloom_instance_host_mount(int fd) {
    if(droidloom_instance_context())return -1;
    return mount_namespace_matches_self(fd);
}
int droidloom_factory_context(void) {
    if(prctl(PR_GET_SECCOMP,0,0,0,0)!=0)return fail(EPERM);
    if(actor_context("u:r:kernel:s0","droidloom-instance-factory (enforce)",0))return -1;
    return mount_namespace_matches_self(boot_mount_namespace);
}
int droidloom_factory_host_mount(void) {
    if(droidloom_factory_context())return -1;
    return fcntl(boot_mount_namespace,F_DUPFD_CLOEXEC,64);
}
/* Device banks, the empty private tmpfs and its labels belong to each new
 * Android generation. Their original node recipe and immutable image stay
 * unchanged; no boot-global mutable /dev is reused across generations. */
int droidloom_instance_devices(const char *cohort) {
    if(droidloom_factory_context())return -1;
    struct droidloom_device_identity original;
    int bank=droidloom_open_device_bank(cohort);
    if(bank<0)return -1;
    int root=droidloom_prepare_device_source(bank,cohort,&original);
    int error=root<0?errno:0;close(bank);
    const char expected[]="u:object_r:p4_linux_private_dev_root_t:s0";
    if(!error&&fsetxattr(root,"security.selinux",expected,sizeof(expected),0))error=errno;
    char value[128];
    if(!error){
        ssize_t n=fgetxattr(root,"security.selinux",value,sizeof(value));
        if(n<0)error=errno;
        else if((n!=(ssize_t)sizeof(expected)&&n!=(ssize_t)sizeof(expected)-1)||
                memcmp(value,expected,(size_t)n))error=EACCES;
    }
    if(root>=0)close(root);
    return error?fail(error):0;
}

/* The only pre-policy entry is a child of original Linux PID 1, with two
 * private anonymous pipes. It performs no namespace creation or service work
 * until PID 1 has activated the complete original policy and releases it. */
int droidloom_factory_prepare(void) {
    if(geteuid()!=0||getpid()<=1||getppid()!=1||prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=0||
       prctl(PR_GET_SECCOMP,0,0,0,0)!=0)
        return fail(EPERM);
    if(take_boot_mount_namespace())return -1;
    struct stat input,output;
    if(fstat(STDIN_FILENO,&input)||fstat(STDOUT_FILENO,&output))return -1;
    if(!S_ISFIFO(input.st_mode)||!S_ISFIFO(output.st_mode)||input.st_uid||output.st_uid||
       input.st_ino==output.st_ino)return fail(EACCES);
    ssize_t n;
    do{n=write(STDOUT_FILENO,"P",1);}while(n<0&&errno==EINTR);
    if(n!=1)return fail(n<0?errno:EPROTO);
    struct pollfd gate={.fd=STDIN_FILENO,.events=POLLIN};
    int ready;
    do{ready=poll(&gate,1,180000);}while(ready<0&&errno==EINTR);
    if(ready!=1||!(gate.revents&POLLIN))return fail(ready<0?errno:ETIMEDOUT);
    char phase=0;
    do{n=read(STDIN_FILENO,&phase,1);}while(n<0&&errno==EINTR);
    if(n!=1||phase!='G')return fail(n<0?errno:EPROTO);
    if(actor_context("u:r:kernel:s0","unconfined",0))return -1;
    if(mount_namespace_matches_self(boot_mount_namespace))return -1;
    const char change[]="changeprofile droidloom-instance-factory";
    _Alignas(struct lsm_ctx) unsigned char buffer[sizeof(struct lsm_ctx)+sizeof(change)]={0};
    struct lsm_ctx *value=(struct lsm_ctx*)buffer;
    value->id=LSM_ID_APPARMOR;value->len=sizeof(buffer);value->ctx_len=sizeof(change);
    memcpy(value->ctx,change,sizeof(change));
    if(syscall(SYS_lsm_set_self_attr,LSM_ATTR_CURRENT,value,sizeof(buffer),0)<0)return -1;
    return droidloom_factory_context();
}

/* The only boot-global device directory contains one exact loop-control node.
 * Per-generation loop nodes are private, correctly typed at creation and
 * unlinked as soon as their verified original descriptor is open. */
int droidloom_factory_device_directory(void) {
    if(droidloom_factory_context())return -1;
    const char *path="/run/droidloom-early/loop-dev";
    if(mkdir(path,0700)<0)return -1;
    if(mount("droidloom-factory-loop",path,"tmpfs",MS_NOSUID|MS_NOEXEC,
             "mode=0700,uid=0,gid=0,size=64k,nr_inodes=16,huge=never,noswap")<0)return -1;
    int root=open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(root<0)return -1;
    int error=0;
    struct stat st;struct statfs fs;
    if(fstat(root,&st)||fstatfs(root,&fs))error=errno;
    if(!error&&(!S_ISDIR(st.st_mode)||st.st_uid||st.st_gid||(st.st_mode&07777)!=0700||
       st.st_ino!=1||fs.f_type!=TMPFS_MAGIC))error=ESTALE;
    const char label[]="u:object_r:p4_linux_factory_devices_t:s0";
    if(!error&&fsetxattr(root,"security.selinux",label,sizeof(label),0)<0)error=errno;
    char actual[128];
    if(!error){
        ssize_t n=fgetxattr(root,"security.selinux",actual,sizeof(actual));
        if(n>0&&actual[n-1]==0)n--;
        if(n!=(ssize_t)strlen(label)||memcmp(actual,label,strlen(label)))error=EACCES;
    }
    if(!error&&mknodat(root,"loop-control",S_IFCHR|0600,makedev(10,237))<0)error=errno;
    if(!error&&(fstatat(root,"loop-control",&st,AT_SYMLINK_NOFOLLOW)<0||!S_ISCHR(st.st_mode)||
        st.st_uid||st.st_gid||st.st_nlink!=1||(st.st_mode&07777)!=0600||st.st_rdev!=makedev(10,237)))error=ESTALE;
    close(root);return error?fail(error):0;
}
