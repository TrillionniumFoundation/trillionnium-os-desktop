// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/fsuid.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned failures;
static const char *filesystem;
static void check(const char *name, int okay) {
    printf("{\"filesystem\":\"%s\",\"case\":\"%s\",\"passed\":%s,\"errno\":%d}\n",
           filesystem, name, okay ? "true" : "false", errno);
    if (!okay) ++failures;
}
static int metadata(const char *path, uid_t uid, gid_t gid, mode_t mode, mode_t type) {
    struct stat st;
    return lstat(path, &st) == 0 && st.st_uid == uid && st.st_gid == gid
        && (st.st_mode & 07777) == mode && (st.st_mode & S_IFMT) == type;
}
static int make_file(const char *name, mode_t mode) {
    int fd = open(name, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, mode);
    if (fd < 0) return 0;
    return close(fd) == 0;
}
static int wait_child(pid_t child) {
    int status; pid_t got;
    do { got = waitpid(child, &status, 0); } while (got < 0 && errno == EINTR);
    return got == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
static int drop_to(uid_t uid, int supplementary) {
    gid_t group = 60002;
    return setgroups(supplementary ? 1 : 0, supplementary ? &group : NULL) == 0
        && setresgid(uid, uid, uid) == 0 && setresuid(uid, uid, uid) == 0;
}
static void connect_child(const struct sockaddr_un *address, uid_t uid, int allowed) {
    pid_t child = fork();
    if (!child) {
        int okay = drop_to(uid, 0);
        int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
        errno = 0;
        int rc = fd < 0 ? -1 : connect(fd, (const struct sockaddr *)address, sizeof *address);
        int saved = errno;
        if (fd >= 0) close(fd);
        _exit(okay && (allowed ? rc == 0 : rc < 0 && saved == EACCES) ? 0 : 1);
    }
    check(allowed ? "original_agent_uid_can_connect" : "unregistered_uid_denied", child > 0 && wait_child(child));
}
static void unprivileged_creation(int kind) {
    pid_t child = fork();
    if (!child) {
        failures = 0;
        uid_t uid = kind == 1 ? 60002 : 60003;
        check("drop_creation_privileges", drop_to(uid, kind == 2));
        if (failures) _exit(1);
        if (!kind) {
            check("nonmember_exec_sgid_stripped", make_file("parent/nonmember-exec", 02755)
                  && metadata("parent/nonmember-exec", uid, 60002, 0755, S_IFREG));
            check("nonmember_nonexec_sgid_preserved", make_file("parent/nonmember-noexec", 02644)
                  && metadata("parent/nonmember-noexec", uid, 60002, 02644, S_IFREG));
            check("nonmember_cannot_add_group_exec_via_chmod", chmod("parent/nonmember-noexec", 02755) == 0
                  && metadata("parent/nonmember-noexec", uid, 60002, 0755, S_IFREG));
            check("nonmember_directory_inherits_sgid", mkdir("parent/nonmember-dir", 0755) == 0
                  && metadata("parent/nonmember-dir", uid, 60002, 02755, S_IFDIR));
            check("nonmember_nested_file_gid", make_file("parent/nonmember-dir/file", 0600)
                  && metadata("parent/nonmember-dir/file", uid, 60002, 0600, S_IFREG));
        } else {
            const char *path = kind == 1 ? "parent/member-exec" : "parent/supplementary-exec";
            check(kind == 1 ? "primary_member_keeps_requested_sgid" : "supplementary_member_keeps_requested_sgid",
                  make_file(path, 02755) && metadata(path, uid, 60002, 02755, S_IFREG));
        }
        _exit(failures != 0);
    }
    check(kind == 0 ? "nonmember_child_completed" : kind == 1 ? "primary_member_child_completed" : "supplementary_child_completed",
          child > 0 && wait_child(child));
}
static void suite(const char *directory, const char *name, int tmpfile) {
    filesystem = name;
    int ready = mkdir(directory, 0755) == 0 && chdir(directory) == 0;
    check("fixture_directory", ready);
    if (!ready) return;
    check("creator_is_original_root_gid_zero", getuid() == 0 && geteuid() == 0 && getgid() == 0 && getegid() == 0);
    check("original_root_parent_created", mkdir("parent", 0700) == 0
          && chown("parent", 0, 60002) == 0 && chmod("parent", 02710) == 0);
    check("original_root_parent_metadata", metadata("parent", 0, 60002, 02710, S_IFDIR));
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, "parent/observation.sock");
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    check("actual_bind_and_mode0660", fd >= 0 && bind(fd, (struct sockaddr *)&address, sizeof address) == 0
          && chmod(address.sun_path, 0660) == 0 && listen(fd, 4) == 0);
    struct stat st = {0};
    int got = lstat(address.sun_path, &st) == 0;
    printf("{\"filesystem\":\"%s\",\"socket_uid\":%u,\"socket_gid\":%u,\"socket_mode\":%u}\n", name, st.st_uid, st.st_gid, st.st_mode & 07777);
    check("original_root_strict_socket_ownership", got && metadata(address.sun_path, 0, 60002, 0660, S_IFSOCK));
    connect_child(&address, 60002, 1);
    connect_child(&address, 60003, 0);
    if (fd >= 0) close(fd);
    check("regular_inherits_gid_without_sgid_bit", make_file("parent/file", 0640)
          && metadata("parent/file", 0, 60002, 0640, S_IFREG));
    check("directory_inherits_gid_and_sgid", mkdir("parent/directory", 0755) == 0
          && metadata("parent/directory", 0, 60002, 02755, S_IFDIR));
    check("nested_file_inherits_gid", make_file("parent/directory/file", 0600)
          && metadata("parent/directory/file", 0, 60002, 0600, S_IFREG));
    check("symlink_inherits_gid", symlink("file", "parent/link") == 0
          && metadata("parent/link", 0, 60002, 0777, S_IFLNK));
    check("fifo_inherits_gid", mkfifo("parent/fifo", 0600) == 0
          && metadata("parent/fifo", 0, 60002, 0600, S_IFIFO));
    check("device_inode_inherits_gid", mknod("parent/device", S_IFCHR | 0600, makedev(1, 3)) == 0
          && metadata("parent/device", 0, 60002, 0600, S_IFCHR));
    if (tmpfile) {
        fd = open("parent", O_TMPFILE | O_RDWR | O_CLOEXEC, 0660);
        check("unnamed_tmpfile_inherits_gid", fd >= 0 && fstat(fd, &st) == 0
              && st.st_uid == 0 && st.st_gid == 60002 && (st.st_mode & 07777) == 0660);
        if (fd >= 0) close(fd);
    }
    check("root_fsetid_keeps_requested_exec_sgid", make_file("parent/root-exec", 02755)
          && metadata("parent/root-exec", 0, 60002, 02755, S_IFREG));
    check("existing_object_created", make_file("outside", 0644) && metadata("outside", 0, 0, 0644, S_IFREG));
    check("hardlink_does_not_reassign_group", link("outside", "parent/hardlink") == 0
          && metadata("parent/hardlink", 0, 0, 0644, S_IFREG));
    check("rename_does_not_reassign_group", rename("outside", "parent/renamed") == 0
          && metadata("parent/renamed", 0, 0, 0644, S_IFREG));
    check("remove_parent_sgid", chmod("parent", 0710) == 0);
    check("ordinary_parent_uses_current_fsgid", make_file("parent/no-sgid", 0640)
          && metadata("parent/no-sgid", 0, 0, 0640, S_IFREG));
    check("restore_parent_sgid", chmod("parent", 02710) == 0);
    check("set_different_fsgid", setfsgid(60004) == 0 && setfsgid((gid_t)-1) == 60004);
    check("sgid_parent_overrides_current_fsgid", make_file("parent/different-fsgid", 0640)
          && metadata("parent/different-fsgid", 0, 60002, 0640, S_IFREG));
    check("ordinary_directory_retains_current_fsgid", make_file("fsgid-file", 0640)
          && metadata("fsgid-file", 0, 60004, 0640, S_IFREG));
    check("restore_fsgid_zero", setfsgid(0) == 60004 && setfsgid((gid_t)-1) == 0);
    check("prepare_unprivileged_creation", chmod("parent", 02777) == 0);
    for (int kind = 0; kind < 3; ++kind) unprivileged_creation(kind);
    check("fixture_leave_directory", chdir("/") == 0);
}
int main(void) {
    alarm(60); setvbuf(stdout, NULL, _IOLBF, 0); umask(0);
    filesystem = "setup";
    check("tmp_directory", mkdir("/tmp", 0755) == 0 || errno == EEXIST);
    suite("/tmp/sgid-ramfs", "ramfs", 1);
    filesystem = "setup";
    check("tmpfs_mount", mkdir("/tmp/sgid-tmpfs", 0755) == 0
          && mount("none", "/tmp/sgid-tmpfs", "tmpfs", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) == 0);
    suite("/tmp/sgid-tmpfs/fixture", "tmpfs", 1);
    filesystem = "setup";
    check("ext2_mount", mkdir("/tmp/sgid-ext2", 0755) == 0
          && mount("/dev/vda", "/tmp/sgid-ext2", "ext2", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) == 0);
    suite("/tmp/sgid-ext2/fixture", "ext2", 0);
    filesystem = "ext2";
    sync();
    check("ext2_unmount", umount("/tmp/sgid-ext2") == 0);
    check("ext2_reopen_readonly", mount("/dev/vda", "/tmp/sgid-ext2", "ext2", MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) == 0);
    check("ext2_gid_and_mode_persist", metadata("/tmp/sgid-ext2/fixture/parent/file", 0, 60002, 0640, S_IFREG)
          && metadata("/tmp/sgid-ext2/fixture/parent/directory", 0, 60002, 02755, S_IFDIR)
          && metadata("/tmp/sgid-ext2/fixture/parent/nonmember-exec", 60003, 60002, 0755, S_IFREG));
    check("ext2_final_unmount", umount("/tmp/sgid-ext2") == 0);
    filesystem = "setup";
    check("tmpfs_unmount", umount("/tmp/sgid-tmpfs") == 0);
    printf("{\"suite\":\"inode-sgid-inheritance-v1\",\"passed\":%s}\n", failures ? "false" : "true");
    return failures != 0;
}
