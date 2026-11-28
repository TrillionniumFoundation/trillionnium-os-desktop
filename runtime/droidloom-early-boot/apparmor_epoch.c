// SPDX-License-Identifier: GPL-3.0-or-later
#define _GNU_SOURCE
#include "apparmor_epoch.h"
#include "board_policy_inputs.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/magic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/xattr.h>
#include <unistd.h>

#define AA_DIR "/sys/kernel/security/apparmor"
#define EPOCH "apparmor-epoch"
#define EPOCH_DIR "kernel-policy"

static const char *const names[] = {
    "droidloom-policy-loader", "droidloom-production-android", "droidloom-production-broker",
    "droidloom-camera-capture"
};
struct role {
    char directory[128], digest[68];
    uint64_t inode[4], raw_inode[2], revision_inode, initial_revision;
    char birth[32], raw_digest[68];
};
struct epoch {
    char boot[40], revision[32];
    uint64_t mount, ns, profiles;
    struct role roles[4];
};

static int reject(int e) { errno = e; return -1; }

static int kernel_line(int parent, const char *name, unsigned long magic, char *text, size_t cap)
{
    int fd = openat(parent, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return -1;
    struct statfs fs;
    int error = 0;
    if (fstatfs(fd, &fs) < 0) error = errno;
    else if ((unsigned long)fs.f_type != magic) error = EXDEV;
    ssize_t n = -1;
    if (!error) {
        do { n = read(fd, text, cap - 1); } while (n < 0 && errno == EINTR);
        if (n < 0) error = errno;
        else if (n < 2 || (size_t)n >= cap - 1 || text[n-1] != '\n' ||
                 memchr(text, 0, n) || memchr(text, '\n', n-1)) error = EBADMSG;
        else text[n-1] = 0;
    }
    close(fd);
    return error ? reject(error) : 0;
}

static int identity(int fd, uint64_t *mnt, uint64_t *ino)
{
    struct statfs fs;
    struct statx st;
    if (fstatfs(fd, &fs) < 0 || statx(fd, "", AT_EMPTY_PATH, STATX_INO | STATX_MNT_ID, &st) < 0)
        return -1;
    if ((unsigned long)fs.f_type != AAFS_MAGIC ||
        (st.stx_mask & (STATX_INO | STATX_MNT_ID)) != (STATX_INO | STATX_MNT_ID) ||
        !st.stx_mnt_id || !st.stx_ino)
        return reject(EXDEV);
    *mnt = st.stx_mnt_id;
    *ino = st.stx_ino;
    return 0;
}

static int capture_raw_profile(int dir, struct role *role, uint64_t mount,
                               const struct droidloom_raw_profile *input)
{
    char link[160];
    ssize_t length = readlinkat(dir,"raw_data",link,sizeof(link)-1);
    if (length <= 0 || (size_t)length >= sizeof(link)-1) return reject(EBADMSG);
    link[length] = 0;
    const char prefix[] = "../../raw_data/";
    if (strncmp(link,prefix,sizeof(prefix)-1)) return reject(EBADMSG);
    char *generation = link + sizeof(prefix)-1;
    char *end = strchr(generation,'/');
    if (!end || strcmp(end,"/raw_data")) return reject(EBADMSG);
    *end = 0;
    if (!*generation || generation[strspn(generation,"0123456789")] ||
        strlen(generation) >= sizeof(role->birth)) return reject(EBADMSG);
    strcpy(role->birth,generation);
    const char *const fields[] = {"raw_data","raw_sha256"};
    for (size_t i = 0; i < 2; i++) {
        // Both symlinks are generated from the current kernel profile proxy.
        int fd = openat(dir,fields[i],O_RDONLY | O_CLOEXEC);
        if (fd < 0) return -1;
        uint64_t actual;
        int error = 0;
        if (identity(fd,&actual,&role->raw_inode[i]) < 0) error = errno;
        else if (actual != mount) error = EXDEV;
        if (!error && i == 0) {
            unsigned char page[4096];
            size_t offset = 0;
            for (;;) {
                ssize_t n = read(fd,page,sizeof(page));
                if (n < 0 && errno == EINTR) continue;
                if (n < 0) { error = errno; break; }
                if (n == 0) { if (offset != input->size) error = EBADMSG; break; }
                if ((size_t)n > input->size - offset ||
                    memcmp(page,input->data+offset,(size_t)n)) { error = EBADMSG; break; }
                offset += (size_t)n;
            }
        } else if (!error) {
            ssize_t n = read(fd,role->raw_digest,sizeof(role->raw_digest)-1);
            if (n < 0) error = errno;
            else if (n != 65 || role->raw_digest[64] != '\n' ||
                     strspn(role->raw_digest,"0123456789abcdef") != 64) error = EBADMSG;
            else role->raw_digest[64] = 0;
        }
        close(fd);
        if (error) return reject(error);
    }
    return 0;
}


static int capture_raw_revision(const struct epoch *epoch, size_t index, struct role *role)
{
    if (index >= 4) return reject(ESTALE);
    const uint64_t expected = index < 3 ? 164U + index : DROIDLOOM_BOARD_APPARMOR_CAMERA_RAW_BIRTH;
    char birth_name[32];
    if (snprintf(birth_name, sizeof(birth_name), "%" PRIu64, expected) < 1 ||
        strcmp(role->birth, birth_name)) return reject(ESTALE);
    int root = open(AA_DIR "/policy", O_PATH | O_DIRECTORY | O_CLOEXEC);
    if (root < 0) return -1;
    int store = -1, birth = -1, fd = -1, error = 0;
    uint64_t mount, ino;
    if (identity(root, &mount, &ino) < 0) error = errno;
    else if (mount != epoch->mount || ino != epoch->ns) error = ESTALE;
    if (!error && (store = openat(root, "raw_data", O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)) < 0)
        error = errno;
    if (!error && (birth = openat(store, birth_name, O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)) < 0)
        error = errno;
    if (!error && (fd = openat(birth, "revision", O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)) < 0)
        error = errno;
    struct stat st;
    if (!error && (identity(fd, &mount, &role->revision_inode) < 0 || fstat(fd, &st) < 0))
        error = errno;
    if (!error && (mount != epoch->mount || !S_ISREG(st.st_mode) || st.st_uid || st.st_gid ||
                   st.st_nlink != 1 || (st.st_mode & 07777) != 0444)) error = ESTALE;
    char value[32];
    ssize_t count = -1;
    if (!error) {
        do { count = read(fd, value, sizeof(value) - 1); } while (count < 0 && errno == EINTR);
        if (count < 0) error = errno;
        else if (count < 2 || (size_t)count >= sizeof(value) - 1 || value[count-1] != '\n' ||
                 value[0] == '0' || memchr(value, 0, count)) error = EBADMSG;
        else {
            value[count-1] = 0;
            if (strspn(value, "0123456789") != (size_t)count - 1) error = EBADMSG;
            else {
                char *end;
                errno = 0;
                role->initial_revision = strtoull(value, &end, 10);
                if (errno || *end || role->initial_revision != expected + 1U) error = ESTALE;
            }
        }
    }
    if (fd >= 0) close(fd);
    if (birth >= 0) close(birth);
    if (store >= 0) close(store);
    close(root);
    return error ? reject(error) : 0;
}

static int read_role(int parent, const char *base, size_t index, struct epoch *epoch,
                     const struct droidloom_raw_profile *input)
{
    struct role *role = &epoch->roles[index];
    size_t size = strlen(base);
    if (role->directory[0] || size >= sizeof(role->directory)) return reject(EBADMSG);
    strcpy(role->directory, base);
    int dir = openat(parent, base, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dir < 0) return -1;
    uint64_t mount;
    int error = 0;
    char name[96], mode[32];
    const char *const fields[] = {"name", "mode", "sha256"};
    if (identity(dir, &mount, &role->inode[0]) < 0) error = errno;
    else if (mount != epoch->mount) error = EXDEV;
    for (size_t i = 0; !error && i < 3; i++) {
        int fd = openat(dir, fields[i], O_PATH | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0) { error = errno; break; }
        if (identity(fd, &mount, &role->inode[i+1]) < 0) error = errno;
        else if (mount != epoch->mount) error = EXDEV;
        close(fd);
    }
    if (!error && (kernel_line(dir, fields[0], AAFS_MAGIC, name, sizeof(name)) < 0 ||
                   kernel_line(dir, fields[1], AAFS_MAGIC, mode, sizeof(mode)) < 0 ||
                   kernel_line(dir, fields[2], AAFS_MAGIC, role->digest, sizeof(role->digest)) < 0))
        error = errno;
    if (!error && (strcmp(name,names[index]) || strcmp(mode,"enforce") || strlen(role->digest) != 64 ||
                   strspn(role->digest, "0123456789abcdef") != 64)) error = EBADMSG;
    if (!error && capture_raw_profile(dir,role,epoch->mount,input) < 0) error = errno;
    if (!error && capture_raw_revision(epoch,index,role) < 0) error = errno;
    close(dir);
    return error ? reject(error) : 0;
}

/* Only the initial kernel-lineage loader calls this before the first SELinux
 * load. The persisted runtime custody contract remains its original three
 * profiles; no runtime reader is asked to inspect unrelated board roles. */
static int board_profile_fields(size_t index, const char *name,
                                const char *mode, const char *digest)
{
    if (index >= DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES)
        return reject(EBADMSG);
    const struct droidloom_board_apparmor_profile *role =
        &droidloom_board_apparmor_profiles[index];
    return strcmp(name, role->name) || strcmp(mode, "enforce") ||
        strcmp(digest, role->kernel_sha256) ? reject(EBADMSG) : 0;
}

static int read_board_profile(int parent, const char *base, size_t index,
                              uint64_t expected_mount)
{
    int fd = openat(parent, base, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    uint64_t mount, inode;
    int error = 0;
    char name[96], mode[32], digest[68];
    if (identity(fd, &mount, &inode) < 0) error = errno;
    else if (mount != expected_mount) error = EXDEV;
    if (!error && (kernel_line(fd, "name", AAFS_MAGIC, name, sizeof(name)) < 0 ||
                   kernel_line(fd, "mode", AAFS_MAGIC, mode, sizeof(mode)) < 0 ||
                   kernel_line(fd, "sha256", AAFS_MAGIC, digest, sizeof(digest)) < 0))
        error = errno;
    if (!error && board_profile_fields(index, name, mode, digest) < 0)
        error = errno;
    close(fd);
    return error ? reject(error) : 0;
}

static int capture(struct epoch *epoch, const struct droidloom_raw_profile inputs[4])
{
    if (kernel_line(AT_FDCWD, "/proc/sys/kernel/random/boot_id", PROC_SUPER_MAGIC,
                    epoch->boot, sizeof(epoch->boot)) < 0 ||
        kernel_line(AT_FDCWD, AA_DIR "/revision", SECURITYFS_MAGIC, epoch->revision, sizeof(epoch->revision)) < 0)
        return -1;
    if (strlen(epoch->boot) != 36 || strspn(epoch->boot, "0123456789abcdef-") != 36 ||
        strspn(epoch->revision, "0123456789") != strlen(epoch->revision) || epoch->revision[0] == '0')
        return reject(EBADMSG);
    char level[16], stacked[16];
    if (kernel_line(AT_FDCWD, AA_DIR "/.ns_level", SECURITYFS_MAGIC, level, sizeof(level)) < 0 ||
        kernel_line(AT_FDCWD, AA_DIR "/.ns_stacked", SECURITYFS_MAGIC, stacked, sizeof(stacked)) < 0)
        return -1;
    if (strcmp(level,"0") || strcmp(stacked,"no")) return reject(EXDEV);
    int root = open(AA_DIR "/policy", O_PATH | O_DIRECTORY | O_CLOEXEC);
    if (root < 0) return -1;
    int profiles = -1, error = 0;
    uint64_t mount;
    if (identity(root, &epoch->mount, &epoch->ns) < 0) error = errno;
    if (!error && (profiles = openat(root, "profiles", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)) < 0)
        error = errno;
    close(root);
    if (error) return reject(error);
    if (identity(profiles, &mount, &epoch->profiles) < 0) error = errno;
    else if (mount != epoch->mount) error = EXDEV;
    if (error) { close(profiles); return reject(error); }
    DIR *entries = fdopendir(profiles);
    if (!entries) { error = errno; close(profiles); return reject(error); }
    bool seen[DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES] = {false};
    do {
        errno = 0;
        struct dirent *entry = readdir(entries);
        if (!entry) { error = errno; break; }
        for (size_t i = 0; i < DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES; ++i) {
            const char *name = droidloom_board_apparmor_profiles[i].name;
            size_t n = strlen(name);
            if (strncmp(entry->d_name, name, n) || entry->d_name[n] != '.') continue;
            const char *suffix = entry->d_name + n + 1;
            if (seen[i] || !*suffix || suffix[strspn(suffix, "0123456789")]) {
                error = EBADMSG;
                break;
            }
            if (read_board_profile(profiles, entry->d_name, i, epoch->mount) < 0) {
                error = errno;
                break;
            }
            seen[i] = true;
        }
        if (error) break;
        for (size_t i = 0; i < 4; i++) {
            size_t n = strlen(names[i]);
            if (strncmp(entry->d_name, names[i], n) || entry->d_name[n] != '.') continue;
            const char *suffix = entry->d_name + n + 1;
            if (!*suffix || suffix[strspn(suffix, "0123456789")]) { error = EBADMSG; break; }
            if (read_role(profiles, entry->d_name, i, epoch, &inputs[i]) < 0) { error = errno; break; }
        }
    } while (!error);
    closedir(entries);
    if (error) return reject(error);
    for (size_t i = 0; i < DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES; ++i)
        if (!seen[i]) return reject(ENOENT);
    for (size_t i = 0; i < 4; i++) if (!epoch->roles[i].directory[0]) return reject(ENOENT);
    char last[32];
    if (kernel_line(AT_FDCWD, AA_DIR "/revision", SECURITYFS_MAGIC, last, sizeof(last)) < 0) return -1;
    return strcmp(last, epoch->revision) ? reject(ESTALE) : 0;
}

static int protect(int fd, int parent)
{
    int tree = open_tree(fd, "", OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC | AT_EMPTY_PATH);
    if (tree < 0) return -1;
    struct mount_attr attributes = {
        .attr_set = MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV | MOUNT_ATTR_NOEXEC,
        .propagation = MS_PRIVATE,
    };
    int error = 0;
    if (mount_setattr(tree, "", AT_EMPTY_PATH, &attributes, sizeof(attributes)) < 0 ||
        move_mount(tree, "", fd, "", MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH) < 0) error = errno;
    close(tree);
    if (error) return reject(error);
    int view = openat(parent, EPOCH_DIR, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (view < 0) return -1;
    struct stat a, b;
    struct statvfs fs;
    unsigned long flags = ST_RDONLY | ST_NOSUID | ST_NODEV | ST_NOEXEC;
    if (fstat(fd,&a) < 0 || fstat(view,&b) < 0 || fstatvfs(view,&fs) < 0) error = errno;
    else if (a.st_dev != b.st_dev || a.st_ino != b.st_ino || (fs.f_flag & flags) != flags ||
             b.st_uid || b.st_gid || !S_ISDIR(b.st_mode) ||
             (b.st_mode & 07777) != 0700) error = ESTALE;
    close(view);
    return error ? reject(error) : 0;
}

int droidloom_prepare_epoch_directory(int handoff)
{
    if (mkdirat(handoff, EPOCH_DIR, 0700) < 0) return -1;
    int fd = openat(handoff,EPOCH_DIR,O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    if (protect(fd,handoff) < 0) { int error = errno; close(fd); return reject(error); }
    return fd;
}

static int label_epoch_directory(int fd)
{
    static const char initial[] = "u:object_r:tmpfs:s0";
    static const char desired[] = "u:object_r:p4_linux_policy_epoch_dir_t:s0";
    char context[128];
    ssize_t n = fgetxattr(fd,"security.selinux",context,sizeof(context));
    if (n < 0) return -1;
    if (!((n == (ssize_t)sizeof(initial) || n == (ssize_t)sizeof(initial)-1) &&
          !memcmp(context,initial,n))) return reject(ESTALE);
    if (fsetxattr(fd,"security.selinux",desired,sizeof(desired),0) < 0) return -1;
    n = fgetxattr(fd,"security.selinux",context,sizeof(context));
    if (n < 0) return -1;
    return ((n == (ssize_t)sizeof(desired) || n == (ssize_t)sizeof(desired)-1) &&
            !memcmp(context,desired,n)) ? 0 : reject(ESTALE);
}

int droidloom_capture_apparmor_epoch(struct droidloom_apparmor_measurement *saved,
                                    const struct droidloom_raw_profile inputs[4])
{
    struct epoch epoch = {0};
    if (capture(&epoch,inputs) < 0) return -1;
    FILE *text = fmemopen(saved->bytes, sizeof(saved->bytes), "w");
    if (!text) return -1;
    int error = 0;
    if (fprintf(text, "DLAAREV3\n%s %s %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
                epoch.boot, epoch.revision, epoch.mount, epoch.ns, epoch.profiles) < 0)
        error = errno;
    for (size_t i = 0; !error && i < 3; i++) {
        struct role *r = &epoch.roles[i];
        if (fprintf(text, "%s %s %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64
                    " %s %s %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
                    r->directory,r->digest,r->inode[0],r->inode[1],r->inode[2],r->inode[3],
                    r->birth,r->raw_digest,r->raw_inode[0],r->raw_inode[1],
                    r->revision_inode,r->initial_revision) < 0)
            error = errno;
    }
    if (fflush(text) < 0 && !error) error = errno;
    long length = ftell(text);
    if (fclose(text) < 0 && !error) error = errno;
    if (error) return reject(error);
    if (length < 1 || (size_t)length >= sizeof(saved->bytes)) return reject(EOVERFLOW);
    saved->size = (size_t)length;
    text = fmemopen(saved->camera, sizeof(saved->camera), "w");
    if (!text) return -1;
    struct role *r = &epoch.roles[3];
    if (fprintf(text, "DLAACAM1\n%s %s %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
                epoch.boot, epoch.revision, epoch.mount, epoch.ns, epoch.profiles) < 0 ||
        fprintf(text, "%s %s %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64
                " %s %s %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
                r->directory,r->digest,r->inode[0],r->inode[1],r->inode[2],r->inode[3],
                r->birth,r->raw_digest,r->raw_inode[0],r->raw_inode[1],
                r->revision_inode,r->initial_revision) < 0)
        error = errno;
    if (fflush(text) < 0 && !error) error = errno;
    length = ftell(text);
    if (fclose(text) < 0 && !error) error = errno;
    if (error) return reject(error);
    if (length < 1 || (size_t)length >= sizeof(saved->camera)) return reject(EOVERFLOW);
    saved->camera_size = (size_t)length;
    return 0;
}

int droidloom_open_initial_selinux_status(void)
{
    int fd = open("/sys/fs/selinux/status", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    struct statfs fs;
    uint32_t before[5];
    int error = 0;
    if (fstatfs(fd, &fs) < 0) error = errno;
    else if ((unsigned long)fs.f_type != 0xf97cff8cUL) error = EXDEV;
    else if (pread(fd, before, sizeof(before), 0) != sizeof(before)) error = EIO;
    else if (before[0] != 1 || (before[1] & 1) || before[2] != 1 || before[3] != 0) error = ESTALE;
    if (error) { close(fd); return reject(error); }
    return fd;
}

static int record_selinux_load(int output, int fd, const char *input_sha256)
{
    if (strlen(input_sha256) != 64 || strspn(input_sha256, "0123456789abcdef") != 64)
        return reject(EBADMSG);
    struct statfs fs;
    uint32_t first[5], next[5];
    int error = 0;
    if (fstatfs(fd,&fs) < 0) error = errno;
    else if ((unsigned long)fs.f_type != 0xf97cff8cUL) error = EXDEV;
    else if (pread(fd,first,sizeof(first),0) != sizeof(first) ||
             pread(fd,next,sizeof(next),0) != sizeof(next)) error = EIO;
    else if (memcmp(first,next,sizeof(first)) || first[0] != 1 || (first[1] & 1) ||
             first[2] != 1 || first[3] != 1) error = ESTALE;
    if (error) return reject(error);
    if (dprintf(output,"SELINUX1 %s %" PRIu32 " %" PRIu32 " %" PRIu32 "\n",
                input_sha256,first[1],first[2],first[3]) < 0 || fsync(output) < 0) return -1;
    return 0;
}

static int publish_packet(int handoff, int status, const char *input_sha256,
                          const char *name, const char *bytes, size_t size)
{
    static const char label[] = "u:object_r:p4_linux_apparmor_epoch_t:s0";
    int fd = openat(handoff, name, O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0400);
    if (fd < 0) return -1;
    char value[128];
    int error = 0;
    ssize_t n = fgetxattr(fd, "security.selinux", value, sizeof(value));
    if (n < 0) error = errno;
    else if (!((n == (ssize_t)sizeof(label) || n == (ssize_t)sizeof(label)-1) &&
               !memcmp(value, label, n))) error = EACCES;
    if (!error && write(fd, bytes, size) != (ssize_t)size) error = EIO;
    if (!error && record_selinux_load(fd,status,input_sha256) < 0) error = errno;
    struct stat final;
    if (!error && (fsync(handoff) < 0 || fstat(fd,&final) < 0)) error = errno;
    if (!error && (!S_ISREG(final.st_mode) || (final.st_mode & 07777) != 0400 ||
                   final.st_uid || final.st_gid || final.st_nlink != 1)) error = EACCES;
    close(fd);
    return error ? reject(error) : 0;
}

int droidloom_publish_apparmor_epoch(int handoff, int status, const char *input_sha256,
                                      const struct droidloom_apparmor_measurement *saved)
{
    if (!saved->size || saved->size >= sizeof(saved->bytes) ||
        !saved->camera_size || saved->camera_size >= sizeof(saved->camera)) return reject(EINVAL);
    if (label_epoch_directory(handoff) < 0) return -1;
    if (publish_packet(handoff,status,input_sha256,EPOCH,saved->bytes,saved->size) < 0) return -1;
    return publish_packet(handoff,status,input_sha256,"camera-apparmor-epoch",
                          saved->camera,saved->camera_size);
}
