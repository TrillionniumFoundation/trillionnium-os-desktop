// SPDX-License-Identifier: GPL-3.0-or-later
/* Included after the board's descriptor-relative mount and namespace checks. */
#include <dirent.h>
#include <linux/android/binder.h>
#include <linux/android/binderfs.h>
#include <sys/sysmacros.h>

struct ordinary_device { const char *name; unsigned maj, min; };
static const struct ordinary_device private_devices[] = {
    {"null",1,3}, {"zero",1,5}, {"full",1,7}, {"random",1,8},
    {"urandom",1,9}, {"tty",5,0}, {"fuse",10,229},
};
static const char *const binder_names[] = {"binder", "hwbinder", "vndbinder"};

static int board_names(int fd, const char *const *names, size_t count, const char *optional) {
    if (count >= 31) return reject(E2BIG);
    int readable = openat(fd, ".", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (readable < 0) return -1;
    DIR *dir = fdopendir(readable);
    if (!dir) { int e=errno; close(readable); return reject(e); }
    unsigned seen=0;
    int error=0;
    for (;;) {
        errno=0;
        struct dirent *entry=readdir(dir);
        if (!entry) { error=errno; break; }
        if (!strcmp(entry->d_name,".") || !strcmp(entry->d_name,"..")) continue;
        if (optional && !strcmp(entry->d_name,optional)) continue;
        size_t i=0;
        while (i<count && strcmp(entry->d_name,names[i])) ++i;
        if (i==count || (seen&(1U<<i))) { error=ESTALE; break; }
        seen|=1U<<i;
    }
    closedir(dir);
    if (!error && seen!=((1U<<count)-1)) error=ESTALE;
    return error?reject(error):0;
}

static int board_dev_state(int root, bool binder_ready) {
    int dev=under(root,"dev",O_RDONLY|O_DIRECTORY);
    if (dev<0) return -1;
    struct stat dir;
    int error=0;
    const char *names[11];
    size_t count=0;
    if (filesystem(root,"dev",TMPFS_MAGIC,ST_NOSUID|ST_NOEXEC,ST_RDONLY|ST_NODEV,NULL) || fstat(dev,&dir)) error=errno;
    for(size_t i=0;!error && i<sizeof(private_devices)/sizeof(private_devices[0]);++i) {
        const struct ordinary_device *expected=&private_devices[i];
        struct stat node;
        if(fstatat(dev,expected->name,&node,AT_SYMLINK_NOFOLLOW)) { error=errno; break; }
        if(node.st_dev!=dir.st_dev || node.st_mode!=(S_IFCHR|0666) || node.st_nlink!=1 ||
           node.st_uid!=dir.st_uid || node.st_gid!=dir.st_gid ||
           node.st_rdev!=makedev(expected->maj,expected->min)) { error=ESTALE; break; }
        names[count++]=expected->name;
    }
    if(binder_ready) {
        names[count++]="binderfs";
        for(size_t i=0;i<3;++i) names[count++]=binder_names[i];
    }
    if(!error && board_names(dev,names,count,"socket")) error=errno;
    if(!error) {
        struct stat socket;
        if (!fstatat(dev,"socket",&socket,AT_SYMLINK_NOFOLLOW)) {
            if(!S_ISDIR(socket.st_mode) || socket.st_dev!=dir.st_dev || (socket.st_mode&0022)) error=ESTALE;
        } else if(errno!=ENOENT) error=errno;
    }
    close(dev);
    return error?reject(error):0;
}

static int board_binder_alias(int dev,int fs,const char *name) {
    char target[64],observed[64];
    int len=snprintf(target,sizeof(target),"binderfs/%s",name);
    if(len<0 || (size_t)len>=sizeof(target)) return reject(EINVAL);
    if(symlinkat(target,dev,name)) return -1;
    ssize_t n=readlinkat(dev,name,observed,sizeof(observed));
    if(n!=len || memcmp(observed,target,(size_t)len)) return reject(ESTALE);
    struct stat known,link,node;
    if(fstatat(fs,name,&known,AT_SYMLINK_NOFOLLOW) ||
       fstatat(dev,name,&link,AT_SYMLINK_NOFOLLOW) || fstatat(dev,name,&node,0)) return -1;
    if(!S_ISLNK(link.st_mode) || !S_ISCHR(known.st_mode) || node.st_ino!=known.st_ino ||
       node.st_dev!=known.st_dev || node.st_rdev!=known.st_rdev) return reject(ESTALE);
    return 0;
}

static int board_binder_create(int fs,int control,const struct stat *ctl,const char *name,dev_t *id) {
    struct binderfs_device request={0};
    if(strlen(name)>=sizeof(request.name)) return reject(EINVAL);
    memcpy(request.name,name,strlen(name)+1);
    if(ioctl(control,BINDER_CTL_ADD,&request)) return -1;
    int fd=under(fs,name,O_RDWR|O_NOFOLLOW|O_NONBLOCK);
    if(fd<0) return -1;
    struct stat node,after;
    struct binder_version version={.protocol_version=-1};
    int error=0;
    if(fstat(fd,&node)) error=errno;
    else if(node.st_dev!=ctl->st_dev || node.st_mode!=(S_IFCHR|0600) || node.st_nlink!=1 ||
        node.st_uid || node.st_gid || node.st_rdev!=makedev(request.major,request.minor) ||
        major(node.st_rdev)!=major(ctl->st_rdev) || node.st_rdev==ctl->st_rdev ||
        node.st_ino!=(ino_t)request.minor+3) error=ESTALE;
    else if(ioctl(fd,BINDER_VERSION,&version)) error=errno;
    else if(version.protocol_version!=8) error=EPROTONOSUPPORT;
    else if(fchmod(fd,0666) || fstat(fd,&after)) error=errno;
    else if(after.st_ino!=node.st_ino || after.st_dev!=node.st_dev || after.st_rdev!=node.st_rdev ||
            after.st_mode!=(S_IFCHR|0666) || after.st_uid || after.st_gid || after.st_nlink!=1) error=ESTALE;
    else *id=node.st_rdev;
    close(fd);
    return error?reject(error):0;
}

static int board_private_ipc_owner(void) {
    if(getpid()!=1 || geteuid()!=0 || getegid()!=0) return reject(EPERM);
    int user=open("/proc/self/ns/user",O_RDONLY|O_CLOEXEC);
    int ipc=open("/proc/self/ns/ipc",O_RDONLY|O_CLOEXEC);
    int owner=-1,error=0;
    if(user<0 || ipc<0 || namespace_type(user,CLONE_NEWUSER) || namespace_type(ipc,CLONE_NEWIPC)) error=errno;
    else if((owner=ioctl(ipc,NS_GET_USERNS))<0) error=errno;
    else if(!same_inode(user,owner)) error=EPERM;
    if(owner>=0)close(owner);
    if(ipc>=0)close(ipc);
    if(user>=0)close(user);
    return error?reject(error):0;
}

static int board_build_binder(int root) {
    if(board_private_ipc_owner() || board_dev_state(root,false)) return -1;
    int dev=-1,target=-1,context=-1,mnt=-1,fs=-1,control=-1;
    int error=0;
    struct stat before,dir,ctl;
    dev_t ids[3]={0};
    static const char *const initial[]={"binder-control","features"};
    static const char *const ready[]={"binder-control","features","binder","hwbinder","vndbinder"};
    dev=under(root,"dev",O_RDONLY|O_DIRECTORY);
    if(dev<0 || mkdirat(dev,"binderfs",0755)) { error=errno; goto done; }
    target=under(dev,"binderfs",O_RDONLY|O_DIRECTORY);
    if(target<0 || fchmod(target,0755) || fstat(target,&before) || fstat(dev,&dir) ||
       board_names(target,NULL,0,NULL)) { error=errno; goto done; }
    if(before.st_dev!=dir.st_dev || before.st_mode!=(S_IFDIR|0755) ||
       before.st_uid || before.st_gid) { error=ESTALE; goto done; }
    context=(int)syscall(SYS_fsopen,"binder",FSOPEN_CLOEXEC);
    if(context<0 || syscall(SYS_fsconfig,context,FSCONFIG_SET_STRING,"max","3",0) ||
       syscall(SYS_fsconfig,context,FSCONFIG_CMD_CREATE,NULL,NULL,0)) { error=errno; goto done; }
    mnt=(int)syscall(SYS_fsmount,context,FSMOUNT_CLOEXEC,MOUNT_ATTR_NOSUID|MOUNT_ATTR_NOEXEC);
    if(mnt<0 || syscall(SYS_move_mount,mnt,"",target,"",MOVE_MOUNT_F_EMPTY_PATH|MOVE_MOUNT_T_EMPTY_PATH)) {
        error=errno; goto done;
    }
    fs=under(dev,"binderfs",O_RDONLY|O_DIRECTORY);
    if(fs<0 || filesystem(dev,"binderfs",BINDERFS_SUPER_MAGIC,ST_NOSUID|ST_NOEXEC,ST_NODEV|ST_RDONLY,NULL) ||
       fstat(fs,&before) || board_names(fs,initial,2,NULL)) { error=errno; goto done; }
    if(before.st_dev==dir.st_dev || before.st_ino!=1 || before.st_mode!=(S_IFDIR|0755) ||
       before.st_uid || before.st_gid) { error=ESTALE; goto done; }
    control=under(fs,"binder-control",O_RDWR|O_NONBLOCK);
    if(control<0 || fstat(control,&ctl)) { error=errno; goto done; }
    if(ctl.st_dev!=before.st_dev || ctl.st_ino!=2 || ctl.st_mode!=(S_IFCHR|0600) ||
       ctl.st_uid || ctl.st_gid || ctl.st_nlink!=1) { error=ESTALE; goto done; }
    for(size_t i=0;i<3;++i) {
        if(board_binder_create(fs,control,&ctl,binder_names[i],&ids[i])) { error=errno; goto done; }
        for(size_t j=0;j<i;++j) if(ids[i]==ids[j]) { error=ESTALE; goto done; }
    }
    struct binderfs_device fourth={.name="rejected-fourth"};
    if(ioctl(control,BINDER_CTL_ADD,&fourth)!=-1 || errno!=ENOSPC) { error=EPROTO; goto done; }
    if(board_names(fs,ready,5,NULL)) { error=errno; goto done; }
    for(size_t i=0;i<3;++i) if(board_binder_alias(dev,fs,binder_names[i])) { error=errno; goto done; }
    if(board_dev_state(root,true)) error=errno;
done:
    if(control>=0)close(control);
    if(fs>=0)close(fs);
    if(mnt>=0)close(mnt);
    if(context>=0)close(context);
    if(target>=0)close(target);
    if(dev>=0)close(dev);
    return error?reject(error):0;
}
