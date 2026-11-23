// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "device_template.h"
#include "board.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/loop.h>
#include <linux/magic.h>
#include <linux/mount.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/statfs.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/xattr.h>
#include <unistd.h>

#define IMAGE_NAME "b5b7ee1522f87c6fafb668d671ff028685db9e8e346564b1edda1f7ef867d5f7.img"
#define IMAGE_SIZE (8 * 1024 * 1024)
static const unsigned char image_sha256[32] = {
    0xb5,0xb7,0xee,0x15,0x22,0xf8,0x7c,0x6f,0xaf,0xb6,0x68,0xd6,0x71,0xff,0x02,0x86,
    0x85,0xdb,0x9e,0x8e,0x34,0x65,0x64,0xb1,0xed,0xda,0x1f,0x7e,0xf8,0x67,0xd5,0xf7
};

static int reject(int error)
{
    errno = error;
    return -1;
}

static int selected_image(const char *cohort)
{
    if (!cohort || strnlen(cohort, 65) != 64 ||
        strspn(cohort, "0123456789abcdef") != 64)
        return reject(EINVAL);
    const char *components[] = {"var", "lib", "droidloom", "cohorts", cohort, "board"};
    int fd = open("/", O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0)
        return -1;
    struct stat st;
    for (size_t i = 0; ; ++i) {
        if (fstat(fd, &st) < 0 || !S_ISDIR(st.st_mode) || st.st_uid || st.st_gid ||
            (st.st_mode & 0022)) {
            int error = EACCES;
            close(fd);
            return reject(error);
        }
        if (i == sizeof(components) / sizeof(components[0]))
            break;
        int next = openat(fd, components[i], O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        int error = errno;
        close(fd);
        if (next < 0)
            return reject(error);
        fd = next;
    }
    int image = openat(fd, IMAGE_NAME, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    int error = errno;
    close(fd);
    if (image < 0)
        return reject(error);
    if (fstat(image, &st) < 0)
        error = errno;
    else if (!S_ISREG(st.st_mode) || (st.st_mode & 07777) != 0444 ||
             st.st_uid || st.st_gid || st.st_nlink != 1 || st.st_size != IMAGE_SIZE)
        error = EACCES;
    else
        return image;
    close(image);
    return reject(error);
}

int droidloom_private_device_template(const char *selected_base)
{
    int source = selected_image(selected_base);
    if (source < 0)
        return -1;
    int image = memfd_create("droidloom-selected-device-template", MFD_ALLOW_SEALING | MFD_CLOEXEC);
    int error = image < 0 ? errno : 0;
    unsigned char bytes[32768];
    off_t offset = 0;
    while (!error && offset < IMAGE_SIZE) {
        ssize_t count = pread(source, bytes, sizeof(bytes), offset);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0) {
            error = count < 0 ? errno : EBADMSG;
            break;
        }
        ssize_t written = 0;
        while (written < count) {
            ssize_t n = pwrite(image, bytes + written, (size_t)(count - written), offset + written);
            if (n < 0 && errno == EINTR)
                continue;
            if (n <= 0) {
                error = n < 0 ? errno : EIO;
                break;
            }
            written += n;
        }
        offset += count;
    }
    close(source);
    // Check the exact private bytes the loop device will consume. CP3A ueventd
    // applies its normal owners and modes to this per-generation copy.
    if (!error && (fcntl(image, F_ADD_SEALS, F_SEAL_SEAL | F_SEAL_SHRINK | F_SEAL_GROW) < 0 ||
        droidloom_verified_elf(image, IMAGE_SIZE, image_sha256) < 0))
        error = errno;
    if (error) {
        if (image >= 0)
            close(image);
        return reject(error);
    }
    return image;
}

// Bind only the private memfd to a fresh kernel loop. No system/vendor/data
// device is accepted as writable storage.
static int template_loop(int image)
{
    struct stat source, control_stat;
    if (fstat(image, &source) < 0)
        return -1;
    int control = open("/dev/loop-control", O_RDWR | O_NOFOLLOW | O_CLOEXEC);
    if (control < 0)
        return -1;
    int error = 0, device = -1;
    if (fstat(control, &control_stat) < 0)
        error = errno;
    else if (!S_ISCHR(control_stat.st_mode) || control_stat.st_rdev != makedev(10, 237))
        error = ENODEV;
    for (int retry = 0; !error && retry < 32; ++retry) {
        int number = ioctl(control, LOOP_CTL_GET_FREE);
        char path[64];
        if (number < 0) {
            error = errno;
            break;
        }
        int length = snprintf(path, sizeof(path), "/dev/loop%d", number);
        if (length < 0 || (size_t)length >= sizeof(path)) {
            error = ENAMETOOLONG;
            break;
        }
        device = open(path, O_RDWR | O_NOFOLLOW | O_CLOEXEC);
        if (device < 0) {
            error = errno;
            break;
        }
        struct stat st;
        struct loop_config config = {.fd = (uint32_t)image, .info.lo_flags = LO_FLAGS_AUTOCLEAR};
        if (fstat(device, &st) < 0)
            error = errno;
        else if (!S_ISBLK(st.st_mode) || major(st.st_rdev) != 7)
            error = ENODEV;
        else if (ioctl(device, LOOP_CONFIGURE, &config) < 0) {
            error = errno;
            if (error == EBUSY) {
                close(device);
                device = -1;
                error = 0;
                continue;
            }
        } else {
            struct loop_info64 info = {0};
            if (ioctl(device, LOOP_GET_STATUS64, &info) < 0)
                error = errno;
            else if (info.lo_number != (uint32_t)number || info.lo_inode != source.st_ino ||
                     info.lo_device != source.st_dev || info.lo_offset || info.lo_sizelimit ||
                     info.lo_flags != LO_FLAGS_AUTOCLEAR)
                error = ESTALE;
        }
        break;
    }
    close(control);
    if (error) {
        if (device >= 0)
            close(device);
        return reject(error);
    }
    return device < 0 ? reject(EBUSY) : device;
}

int droidloom_open_device_bank(const char *selected_base)
{
    int backing = droidloom_private_device_template(selected_base);
    if (backing < 0)
        return -1;
    int device = template_loop(backing);
    int error = device < 0 ? errno : 0;
    close(backing);
    if (error)
        return reject(error);
    char path[64];
    int length = snprintf(path, sizeof(path), "/proc/self/fd/%d", device);
    if (length < 0 || (size_t)length >= sizeof(path)) {
        close(device);
        return reject(ENAMETOOLONG);
    }
    int fs = (int)syscall(SYS_fsopen, "ext4", FSOPEN_CLOEXEC);
    int tree = -1;
    if (fs < 0 || syscall(SYS_fsconfig, fs, FSCONFIG_SET_STRING, "source", path, 0) < 0 ||
        syscall(SYS_fsconfig, fs, FSCONFIG_CMD_CREATE, NULL, NULL, 0) < 0)
        error = errno;
    else {
        tree = (int)syscall(SYS_fsmount, fs, FSMOUNT_CLOEXEC, MOUNT_ATTR_NOEXEC | MOUNT_ATTR_NOSUID);
        if (tree < 0)
            error = errno;
    }
    if (fs >= 0)
        close(fs);
    close(device);
    return error ? reject(error) : tree;
}

// Construction is limited to this generation's previously verified, empty
// tmpfs. The caller holds the namespace, generation and original root inode.
struct stock_node {
    const char *name;
    unsigned int major_number, minor_number;
    mode_t permissions;
    int from_image;
};

static const struct stock_node stock_nodes[] = {
    {"null",1,3,0666,0}, {"random",1,8,0666,0}, {"urandom",1,9,0666,0},
    {"zero",1,5,0666,1}, {"full",1,7,0666,1}, {"tty",5,0,0666,1}, {"fuse",10,229,0600,1}
};

static int verify_stock_node(const struct stat *st, const struct stock_node *node)
{
    if (!S_ISCHR(st->st_mode) || (st->st_mode & 07777) != node->permissions ||
        st->st_rdev != makedev(node->major_number,node->minor_number) ||
        st->st_uid || st->st_gid || st->st_nlink != 1)
        return reject(ESTALE);
    return 0;
}

static int add_stock_node(int root, int bank, const struct stock_node *node, int *created, int *attached)
{
    if (!node->from_image) {
        if (mknodat(root,node->name,S_IFCHR | node->permissions,
                    makedev(node->major_number,node->minor_number)) < 0)
            return -1;
        *created = 1;
        if (fchmodat(root,node->name,node->permissions,0) < 0)
            return -1;
        struct stat st;
        return fstatat(root,node->name,&st,AT_SYMLINK_NOFOLLOW) < 0 ? -1 : verify_stock_node(&st,node);
    }
    int source = openat(bank,node->name,O_PATH | O_NOFOLLOW | O_CLOEXEC);
    if (source < 0)
        return -1;
    struct stat st;
    int error = 0, mount = -1;
    if (fstat(source,&st) < 0 || verify_stock_node(&st,node) < 0)
        error = errno;
    else {
        mount = (int)syscall(SYS_open_tree,source,"",OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC | AT_EMPTY_PATH);
        if (mount < 0)
            error = errno;
    }
    close(source);
    if (!error) {
        int slot = openat(root,node->name,O_CREAT | O_EXCL | O_NOFOLLOW | O_WRONLY | O_CLOEXEC,0000);
        if (slot < 0)
            error = errno;
        else {
            close(slot);
            *created = 1;
        }
    }
    if (!error) {
        if (syscall(SYS_move_mount,mount,"",root,node->name,MOVE_MOUNT_F_EMPTY_PATH) < 0)
            error = errno;
        else
            *attached = 1;
    }
    if (mount >= 0)
        close(mount);
    struct stat target;
    if (!error && fstatat(root,node->name,&target,AT_SYMLINK_NOFOLLOW) < 0)
        error = errno;
    if (!error && (target.st_dev != st.st_dev || target.st_ino != st.st_ino))
        error = ESTALE;
    return error ? reject(error) : 0;
}


// This xattr belongs to the selected tmpfs root. The supervisor can read the
// board's completed measurement without opening a stock Android char device.
static int seal_nodes(int root, const char *cohort)
{
    if (!cohort || strnlen(cohort,65)!=64 || strspn(cohort,"0123456789abcdef")!=64)
        return reject(EINVAL);
    struct statx parent;
    if (statx(root,"",AT_EMPTY_PATH,STATX_INO | STATX_MNT_ID_UNIQUE,&parent) < 0)
        return -1;
    if ((parent.stx_mask & (STATX_INO | STATX_MNT_ID_UNIQUE)) != (STATX_INO | STATX_MNT_ID_UNIQUE))
        return reject(EOPNOTSUPP);
    char data[1536];
    int length=snprintf(data,sizeof(data),"DROIDLOOM_DEVICES_V1\n%s\n%s\n%u %u %llu %llu\n",cohort,IMAGE_NAME,
                        parent.stx_dev_major,parent.stx_dev_minor,(unsigned long long)parent.stx_ino,
                        (unsigned long long)parent.stx_mnt_id);
    if (length<0 || (size_t)length>=sizeof(data))
        return reject(EOVERFLOW);
    size_t used=(size_t)length;
    for(size_t i=0;i<sizeof(stock_nodes)/sizeof(stock_nodes[0]);++i) {
        const struct stock_node *n=&stock_nodes[i];
        struct statx st;
        if (statx(root,n->name,AT_SYMLINK_NOFOLLOW,STATX_BASIC_STATS | STATX_MNT_ID_UNIQUE,&st) < 0)
            return -1;
        if ((st.stx_mask & (STATX_BASIC_STATS | STATX_MNT_ID_UNIQUE)) != (STATX_BASIC_STATS | STATX_MNT_ID_UNIQUE) ||
            st.stx_mode != (S_IFCHR | n->permissions) || st.stx_rdev_major!=n->major_number ||
            st.stx_rdev_minor!=n->minor_number || st.stx_uid || st.stx_gid || st.stx_nlink!=1 ||
            ((st.stx_mnt_id==parent.stx_mnt_id) != !n->from_image))
            return reject(ESTALE);
        length=snprintf(data+used,sizeof(data)-used,"%s %u %u %llu %llu\n",n->name,st.stx_dev_major,st.stx_dev_minor,
                        (unsigned long long)st.stx_ino,(unsigned long long)st.stx_mnt_id);
        if(length<0 || (size_t)length>=sizeof(data)-used)
            return reject(EOVERFLOW);
        used+=(size_t)length;
    }
    return fsetxattr(root,"trusted.droidloom.device-source",data,used,XATTR_CREATE);
}

int droidloom_populate_private_devices(int root, int bank, const char *cohort)
{
    enum { COUNT = sizeof(stock_nodes)/sizeof(stock_nodes[0]) };
    int created[COUNT] = {0}, attached[COUNT] = {0}, property = 0;
    struct statfs devfs, sourcefs;
    struct stat root_stat, bank_stat;
    if (fstatfs(root,&devfs) < 0 || fstatfs(bank,&sourcefs) < 0 ||
        fstat(root,&root_stat) < 0 || fstat(bank,&bank_stat) < 0)
        return -1;
    if ((unsigned long)devfs.f_type != TMPFS_MAGIC || (unsigned long)sourcefs.f_type != EXT4_SUPER_MAGIC ||
        root_stat.st_dev == bank_stat.st_dev || root_stat.st_ino != 1 ||
        !S_ISDIR(root_stat.st_mode) || (root_stat.st_mode & 07777) != 0755 ||
        root_stat.st_uid || root_stat.st_gid || bank_stat.st_ino != 2 ||
        !S_ISDIR(bank_stat.st_mode) || bank_stat.st_uid || bank_stat.st_gid)
        return reject(ESTALE);
    int error = 0;
    for (size_t i = 0; i < COUNT; ++i) {
        if (add_stock_node(root,bank,&stock_nodes[i],&created[i],&attached[i]) < 0) {
            error = errno;
            break;
        }
    }
    // Stock init creates and labels the entire property area itself. The only
    // input to that subsystem is its original empty, execute-only directory.
    if (!error) {
        if (mkdirat(root,"__properties__",0711) < 0)
            error = errno;
        else {
            property = 1;
            if (fchmodat(root,"__properties__",0711,0) < 0)
                error = errno;
        }
    }
    if (!error && seal_nodes(root,cohort) < 0)
        error = errno;
    if (!error)
        return 0;
    if (property && unlinkat(root,"__properties__",AT_REMOVEDIR) < 0)
        error = EUCLEAN;
    for (size_t i = COUNT; i > 0; --i) {
        size_t n = i-1;
        if (attached[n]) {
            char path[96];
            int len = snprintf(path,sizeof(path),"/proc/self/fd/%d/%s",root,stock_nodes[n].name);
            if (len < 0 || (size_t)len >= sizeof(path) || umount2(path,MNT_DETACH) < 0) {
                error = EUCLEAN;
                continue;
            }
        }
        if (created[n] && unlinkat(root,stock_nodes[n].name,0) < 0)
            error = EUCLEAN;
    }
    return reject(error);
}
