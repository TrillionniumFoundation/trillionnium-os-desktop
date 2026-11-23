// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/magic.h>
#include <linux/nsfs.h>
#include <poll.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef PID_FS_MAGIC
#define PID_FS_MAGIC 0x50494446
#endif
#ifndef NS_GET_TGID_IN_PIDNS
#define NS_GET_TGID_IN_PIDNS _IOR(0xb7, 9, int)
#endif

#define DL_HANDOFF_ROOT "/run/droidloom-early"
#define DL_NS_PIN DL_HANDOFF_ROOT "/pidns"

static int dl_read(const char* path, char* buf, size_t capacity) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t n = read(fd, buf, capacity - 1);
    int saved = errno;
    close(fd);
    if (n <= 0 || (size_t)n == capacity - 1) {
        errno = n < 0 ? saved : EOVERFLOW;
        return -1;
    }
    buf[n] = '\0';
    return 0;
}

static int dl_fail(int code) { errno = code; return -1; }

static int dl_source(int fd, long type, struct stat* identity) {
    struct statfs fs;
    if (fstatfs(fd, &fs) || fstat(fd, identity)) return -1;
    return fs.f_type == type ? 0 : dl_fail(EINVAL);
}

static int dl_live(int fd) {
    struct pollfd wait_for_exit = { .fd = fd, .events = POLLIN };
    int result = poll(&wait_for_exit, 1, 0);
    return result == 0 ? 0 : (result == -1 ? -1 : dl_fail(ESRCH));
}

static int dl_pin(const char* path, int fd, const struct stat* expected) {
    int target = open(path,O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_CREAT | O_EXCL,0400);
    if (target < 0) return -1;
    close(target);
    char source[64];
    snprintf(source,sizeof(source),"/proc/self/fd/%d",fd);
    if (mount(source, path, NULL, MS_BIND, NULL) != 0) {
        int saved = errno;
        unlink(path);
        return dl_fail(saved);
    }
    struct stat got;
    if (mount(NULL,path,NULL,MS_BIND|MS_REMOUNT|MS_RDONLY|MS_NOSUID|MS_NODEV|MS_NOEXEC,NULL) == 0 &&
        stat(path,&got) == 0 && got.st_dev == expected->st_dev && got.st_ino == expected->st_ino)
        return 0;
    int saved = errno ? errno : ESTALE;
    umount2(path, MNT_DETACH);
    unlink(path);
    return dl_fail(saved);
}

/* Called only by the first-stage creator, before unblocking the new PID 1.
 * The caller supplies the digest it obtained from the verified release and the
 * pidfd returned by the same clone(CLONE_PIDFD | CLONE_NEWPID) operation.
 * The pinned PID namespace survives switch_root on the original /run tmpfs.
 * If its init dies, Linux never assigns PID 1 to a second task in that namespace. */
int droidloom_publish_early_child(pid_t child, int child_pidfd, const char* selection) {
    if (geteuid() != 0 || child <= 1 || !selection ||
        strlen(selection) != 64 || strspn(selection, "0123456789abcdef") != 64)
        return dl_fail(EINVAL);
    struct statfs ram;
    struct stat dir, process, space;
    if (lstat(DL_HANDOFF_ROOT,&dir) || statfs(DL_HANDOFF_ROOT,&ram)) return -1;
    if (ram.f_type != TMPFS_MAGIC || !S_ISDIR(dir.st_mode) || dir.st_uid ||
        dir.st_gid || (dir.st_mode & 07777) != 0700) return dl_fail(EACCES);
    if (dl_source(child_pidfd,PID_FS_MAGIC,&process) || dl_live(child_pidfd)) return -1;
    char path[100], info[512], process_line[60], boot[64];
    snprintf(path,sizeof(path),"/proc/self/fdinfo/%d",child_pidfd);
    snprintf(process_line,sizeof(process_line),"\nPid:\t%d\n",child);
    if (dl_read(path,info,sizeof(info)) || !strstr(info,process_line)) return dl_fail(ESTALE);
    if (dl_read("/proc/sys/kernel/random/boot_id",boot,sizeof(boot))) return -1;
    boot[strcspn(boot,"\n")]='\0';
    if (strlen(boot)!=36 || strspn(boot,"0123456789abcdef-")!=36) return dl_fail(EINVAL);
    snprintf(path,sizeof(path),"/proc/%d/ns/pid",child);
    int ns = open(path,O_RDONLY|O_CLOEXEC);
    if (ns < 0) return -1;
    bool ns_pinned=false,has_pending=false;
    int pending=-1, saved=0;
    if (dl_source(ns,NSFS_MAGIC,&space) || ioctl(ns,NS_GET_NSTYPE)!=CLONE_NEWPID ||
        ioctl(ns,NS_GET_TGID_IN_PIDNS,(unsigned long)child)!=1) {saved=ESTALE; goto done;}
    if (dl_pin(DL_NS_PIN,ns,&space)) {saved=errno; goto done;}
    ns_pinned=true;
    pending=open(DL_HANDOFF_ROOT "/generation.pending",O_WRONLY|O_CLOEXEC|O_CREAT|O_EXCL,0400);
    if(pending<0) {saved=errno; goto done;}
    has_pending=true;
    if(dprintf(pending,"{\"schema\":\"droidloom-early-child-v1\",\"selection_sha256\":\"%s\","
               "\"boot_id\":\"%s\",\"host_pid\":%d,\"pidfs_dev\":%" PRIuMAX ",\"pidfs_ino\":%" PRIuMAX
               ",\"pidns_dev\":%" PRIuMAX ",\"pidns_ino\":%" PRIuMAX "}\n",
               selection,boot,child,(uintmax_t)process.st_dev,(uintmax_t)process.st_ino,
               (uintmax_t)space.st_dev,(uintmax_t)space.st_ino)<0 || fsync(pending) || dl_live(child_pidfd)) {
        saved=errno; goto done;
    }
    if(syscall(SYS_renameat2,AT_FDCWD,DL_HANDOFF_ROOT "/generation.pending",
               AT_FDCWD,DL_HANDOFF_ROOT "/generation.json",RENAME_NOREPLACE)) {saved=errno; goto done;}
done:
    if(pending>=0)close(pending);
    close(ns);
    if(saved) {
        if(has_pending) unlink(DL_HANDOFF_ROOT "/generation.pending");
        if(ns_pinned) {umount(DL_NS_PIN);unlink(DL_NS_PIN);}
        return dl_fail(saved);
    }
    return 0;
}
/* The original creator publishes only named namespace objects and a FIFO
 * owned by this boot. The systemd resource worker opens all of them anew. */
struct droidloom_release_phase {char sha[65],nonce[65];};
static int dl_pin_child_namespace(pid_t child,const char* name,const char* target,int type,struct stat* meta) {
    char path[120];
    snprintf(path,sizeof path,"/proc/%d/ns/%s",child,name);
    int fd=open(path,O_RDONLY|O_CLOEXEC);
    if(fd<0)return -1;
    int result=dl_source(fd,NSFS_MAGIC,meta);
    if(!result&&ioctl(fd,NS_GET_NSTYPE)!=type) result=dl_fail(ESTALE);
    if(!result)result=dl_pin(target,fd,meta);
    int saved=errno;close(fd);errno=saved;return result;
}
void droidloom_cancel_unpublished_resource_handles(void) {
    unlink(DL_HANDOFF_ROOT "/resources.json");
    umount(DL_HANDOFF_ROOT "/mntns");unlink(DL_HANDOFF_ROOT "/mntns");
    umount(DL_HANDOFF_ROOT "/userns");unlink(DL_HANDOFF_ROOT "/userns");
    umount(DL_HANDOFF_ROOT "/cgroupns-creation");unlink(DL_HANDOFF_ROOT "/cgroupns-creation");
}
int droidloom_publish_resource_handles(pid_t child,const struct droidloom_release_phase* phase,int fifo) {
    struct stat mnt,user,initial_cgroup,gate,named;
    if(!phase||!phase->sha[0]||child<=1||fstat(fifo,&gate)||
       lstat(DL_HANDOFF_ROOT "/release",&named))return dl_fail(EINVAL);
    if(!S_ISFIFO(gate.st_mode)||(gate.st_mode&07777)!=0600||gate.st_uid||gate.st_gid||gate.st_nlink!=1||
       named.st_dev!=gate.st_dev||named.st_ino!=gate.st_ino)return dl_fail(EACCES);
    if(dl_pin_child_namespace(child,"mnt",DL_HANDOFF_ROOT "/mntns",CLONE_NEWNS,&mnt))return -1;
    if(dl_pin_child_namespace(child,"user",DL_HANDOFF_ROOT "/userns",CLONE_NEWUSER,&user)){
        int saved=errno;umount(DL_HANDOFF_ROOT "/mntns");unlink(DL_HANDOFF_ROOT "/mntns");return dl_fail(saved);
    }
    if(dl_pin_child_namespace(child,"cgroup",DL_HANDOFF_ROOT "/cgroupns-creation",CLONE_NEWCGROUP,&initial_cgroup)){
        int saved=errno;umount(DL_HANDOFF_ROOT "/mntns");unlink(DL_HANDOFF_ROOT "/mntns");
        umount(DL_HANDOFF_ROOT "/userns");unlink(DL_HANDOFF_ROOT "/userns");return dl_fail(saved);
    }
    const char *temp=DL_HANDOFF_ROOT "/resources.pending";
    int fd=open(temp,O_CREAT|O_EXCL|O_NOFOLLOW|O_WRONLY|O_CLOEXEC,0400);
    int saved=fd<0?errno:0;char boot[64];
    if(!saved&&dl_read("/proc/sys/kernel/random/boot_id",boot,sizeof boot))saved=errno;
    if(!saved){
        boot[strcspn(boot,"\n")]=0;
        if(dprintf(fd,"{\"schema\":\"droidloom-early-resources-v1\",\"boot_id\":\"%s\","
            "\"selection_sha256\":\"%s\",\"host_pid\":%d,\"nonce\":\"%s\","
            "\"mntns_dev\":%" PRIuMAX ",\"mntns_ino\":%" PRIuMAX ",\"userns_dev\":%" PRIuMAX ",\"userns_ino\":%" PRIuMAX
            ",\"cgroupns_dev\":%" PRIuMAX ",\"cgroupns_ino\":%" PRIuMAX ",\"fifo_dev\":%" PRIuMAX ",\"fifo_ino\":%" PRIuMAX "}\n",
            boot,phase->sha,child,phase->nonce,(uintmax_t)mnt.st_dev,(uintmax_t)mnt.st_ino,(uintmax_t)user.st_dev,
            (uintmax_t)user.st_ino,(uintmax_t)initial_cgroup.st_dev,(uintmax_t)initial_cgroup.st_ino,(uintmax_t)gate.st_dev,(uintmax_t)gate.st_ino)<0||fsync(fd))saved=errno;
    }
    if(!saved&&syscall(SYS_renameat2,AT_FDCWD,temp,AT_FDCWD,DL_HANDOFF_ROOT "/resources.json",RENAME_NOREPLACE))
        saved=errno;
    if(fd>=0){close(fd);if(saved)unlink(temp);}
    if(saved){umount(DL_HANDOFF_ROOT "/cgroupns-creation");unlink(DL_HANDOFF_ROOT "/cgroupns-creation");
        umount(DL_HANDOFF_ROOT "/mntns");unlink(DL_HANDOFF_ROOT "/mntns");
        umount(DL_HANDOFF_ROOT "/userns");unlink(DL_HANDOFF_ROOT "/userns");return dl_fail(saved);}
    return 0;
}
