// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned count, failures;
static const char *label;
static void result(const char *name, int ok)
{
    count++; failures += !ok;
    printf("SGID_CASE fs=%s name=%s pass=%d\n", label, name, !!ok);
}
static void path(char out[512], const char *base, const char *name)
{
    int size = snprintf(out, 512, "%s/%s", base, name);
    if (size < 0 || size >= 512) exit(2);
}
static int attributes(const char *name, uid_t uid, gid_t gid, unsigned mode)
{
    struct stat value;
    return lstat(name, &value) == 0 && value.st_uid == uid && value.st_gid == gid && (value.st_mode & 07777) == mode;
}
static int file(const char *name, unsigned mode)
{
    int fd = open(name, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, mode);
    return fd >= 0 && close(fd) == 0;
}
static int drop_to(unsigned uid, int member)
{
    gid_t group = 60001;
    if (setgroups(member ? 1 : 0, member ? &group : NULL) || prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0)) return 0;
    for (int cap = 0; cap <= CAP_LAST_CAP; cap++) if (prctl(PR_CAPBSET_DROP, cap, 0, 0, 0)) return 0;
    if (setresgid(uid, uid, uid) || setresuid(uid, uid, uid)) return 0;
    struct __user_cap_header_struct header = {.version = _LINUX_CAPABILITY_VERSION_3, .pid = 0};
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    return syscall(SYS_capset, &header, data) == 0 && prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0;
}
static int socket_at(const char *name, int type)
{
    int fd = socket(AF_UNIX, type | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(name) >= sizeof address.sun_path || fd < 0) return -1;
    strcpy(address.sun_path, name);
    if (bind(fd, (struct sockaddr *)&address, sizeof address) || chmod(name, 0660)) { close(fd); return -1; }
    return fd;
}
static int send_to(const char *name, int type)
{
    int fd = socket(AF_UNIX, type | SOCK_CLOEXEC, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(name) >= sizeof address.sun_path || fd < 0) return 0;
    strcpy(address.sun_path, name);
    int ok = connect(fd, (struct sockaddr *)&address, sizeof address) == 0 && write(fd, "G", 1) == 1;
    close(fd); return ok;
}
static int wait_ok(pid_t child)
{
    int status; pid_t result;
    do { result = waitpid(child, &status, 0); } while (result < 0 && errno == EINTR);
    return result == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

int main(int argc, char **argv)
{
    if (argc != 3 || geteuid() != 0) return 2;
    label = argv[2]; umask(0);
    if (mkdir(argv[1], 0755)) return 2;
    char parent[512], name[512], nested[512], stream_path[512], datagram_path[512];
    path(parent, argv[1], "group");
    if (mkdir(parent, 0777) || chown(parent, 0, 60001) || chmod(parent, 02777)) return 2;
    path(name, parent, "file");
    result("file_owner_group_mode", file(name, 0640) && attributes(name, 0, 60001, 0640));
    path(name, parent, "directory");
    result("directory_group_and_setgid", mkdir(name, 0750) == 0 && attributes(name, 0, 60001, 02750));
    path(nested, name, "nested");
    result("nested_file_group", file(nested, 0600) && attributes(nested, 0, 60001, 0600));
    path(name, parent, "fifo");
    result("fifo_group", mkfifo(name, 0640) == 0 && attributes(name, 0, 60001, 0640));
    path(name, parent, "symlink");
    result("symlink_group", symlink("file", name) == 0 && attributes(name, 0, 60001, 0777));
    path(name, parent, "root-setgid");
    result("capable_root_retains_requested_setgid", file(name, 02750) && attributes(name, 0, 60001, 02750));
    path(stream_path, parent, "stream"); path(datagram_path, parent, "datagram");
    int stream = socket_at(stream_path, SOCK_STREAM), datagram = socket_at(datagram_path, SOCK_DGRAM);
    result("stream_socket_group", stream >= 0 && listen(stream, 1) == 0 && attributes(stream_path, 0, 60001, 0660));
    result("datagram_socket_group", datagram >= 0 && attributes(datagram_path, 0, 60001, 0660));

    int channel[2]; if (pipe2(channel, O_CLOEXEC)) return 2;
    fflush(NULL); pid_t child = fork(); if (child < 0) return 2;
    if (!child) {
        close(channel[0]); close(stream); close(datagram);
        unsigned char report[4] = {0};
        if (drop_to(60002, 0)) {
            path(name, parent, "nonmember-setgid");
            report[0] = file(name, 02750) && attributes(name, 60002, 60001, 0750);
            path(name, parent, "nonmember-nonexec");
            report[1] = file(name, 02640) && attributes(name, 60002, 60001, 02640);
            path(name, parent, "nonmember-directory");
            report[2] = mkdir(name, 0750) == 0 && attributes(name, 60002, 60001, 02750);
            report[3] = 1;
        }
        int ok = write(channel[1], report, sizeof report) == sizeof report; close(channel[1]); _exit(ok ? 0 : 3);
    }
    close(channel[1]); unsigned char report[4] = {0};
    ssize_t size = read(channel[0], report, sizeof report); close(channel[0]); int child_ok = wait_ok(child) && size == sizeof report && report[3];
    result("nonmember_exec_setgid_cleared", child_ok && report[0]);
    result("nonmember_nonexec_setgid_retained", child_ok && report[1]);
    result("nonmember_directory_still_inherits", child_ok && report[2]);
    if (pipe2(channel, O_CLOEXEC)) return 2;
    fflush(NULL); child = fork(); if (child < 0) return 2;
    if (!child) {
        close(channel[0]); close(stream); close(datagram);
        unsigned char allowed = 0;
        if (drop_to(60002, 1)) {
            path(name, parent, "member-setgid");
            allowed = file(name, 02750) && attributes(name, 60002, 60001, 02750);
        }
        int ok = write(channel[1], &allowed, 1) == 1; close(channel[1]); _exit(ok ? 0 : 3);
    }
    close(channel[1]); unsigned char allowed = 0;
    size = read(channel[0], &allowed, 1); close(channel[0]);
    result("supplementary_member_retains_setgid", wait_ok(child) && size == 1 && allowed);
    if (pipe2(channel, O_CLOEXEC)) return 2;
    fflush(NULL); child = fork(); if (child < 0) return 2;
    if (!child) {
        close(channel[0]); close(stream); close(datagram); unsigned char sent[2] = {0};
        if (drop_to(60001, 0)) { sent[0] = send_to(stream_path, SOCK_STREAM); sent[1] = send_to(datagram_path, SOCK_DGRAM); }
        int ok = write(channel[1], sent, sizeof sent) == sizeof sent; close(channel[1]); _exit(ok ? 0 : 3);
    }
    close(channel[1]); unsigned char sent[2] = {0}; size = read(channel[0], sent, sizeof sent); close(channel[0]);
    child_ok = wait_ok(child) && size == sizeof sent;
    int accepted = stream >= 0 ? accept4(stream, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK) : -1; char byte = 0;
    result("dedicated_group_stream_dac", child_ok && sent[0] && accepted >= 0 && read(accepted, &byte, 1) == 1 && byte == 'G');
    if (accepted >= 0) close(accepted);
    byte = 0;
    result("dedicated_group_datagram_dac", child_ok && sent[1] && datagram >= 0 && read(datagram, &byte, 1) == 1 && byte == 'G');
    if (stream >= 0) close(stream);
    if (datagram >= 0) close(datagram);
    if (chmod(parent, 0777)) return 2;
    path(name, parent, "plain-parent");
    result("non_setgid_parent_uses_caller_group", file(name, 0640) && attributes(name, 0, getegid(), 0640));
    printf("SGID_COMPLETE fs=%s cases=%u failures=%u\n", label, count, failures);
    return failures ? 1 : 0;
}
