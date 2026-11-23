#include <cstdio>
// SPDX-License-Identifier: GPL-3.0-or-later
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/system_properties.h>
#include <sys/vfs.h>
#include <sys/xattr.h>
#include <unistd.h>

namespace {
constexpr char kRequestPath[] = "/dev/socket/droidloom/shutdown-request";
constexpr char kRequestType[] = "u:object_r:p4_android_shutdown_request_t:s0";
bool selected_request(int fd) {
    struct stat st {};
    struct statfs fs {};
    struct statvfs flags {};
    char type[sizeof(kRequestType)] {};
    const ssize_t n = fgetxattr(fd, "security.selinux", type, sizeof(type));
    return fstat(fd, &st) == 0 && fstatfs(fd, &fs) == 0 && fstatvfs(fd, &flags) == 0 &&
           fs.f_type == 0x01021994 && (flags.f_flag & ST_RDONLY) != 0 && S_ISREG(st.st_mode) &&
           st.st_nlink == 1 && (st.st_mode & 07777) == 0640 && st.st_gid == getegid() && st.st_size == 1 &&
           (n == sizeof(type) || n == sizeof(type) - 1) && !memcmp(type, kRequestType, sizeof(type));
}
}

// The Android helper opens only the original read-only projection. Watch the
// held inode before sampling it so writes made during service startup are seen.
int request_orderly_shutdown() {
    const int fd = open(kRequestPath, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0 || !selected_request(fd)) return 1;
    const int events = inotify_init1(IN_CLOEXEC);
    if (events < 0) return 1;
    char held[64];
    snprintf(held, sizeof(held), "/proc/self/fd/%d", fd);
    const int watch = inotify_add_watch(events, held, IN_MODIFY | IN_DELETE_SELF | IN_MOVE_SELF);
    if (watch < 0) return 1;
    for (;;) {
        char state = 0;
        if (TEMP_FAILURE_RETRY(pread(fd, &state, 1, 0)) != 1 || !selected_request(fd)) return 1;
        if (state == '1') return __system_property_set("sys.droidloom.shutdown_request", "shutdown") == 0 ? 0 : 1;
        if (state != '0') return 1;
        struct inotify_event event {};
        if (TEMP_FAILURE_RETRY(read(events, &event, sizeof(event))) != sizeof(event) ||
            event.wd != watch || event.len || event.mask != IN_MODIFY) return 1;
    }
}
