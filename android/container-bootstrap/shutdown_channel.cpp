// SPDX-License-Identifier: Apache-2.0
#include "shutdown_channel.h"

#include <fcntl.h>
#include <linux/magic.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/vfs.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <charconv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <set>
#include <string_view>

namespace droidloom::bootstrap {
namespace {
constexpr int kSocket = 3;
constexpr std::string_view kRequest = "DROIDLOOM_SHUTDOWN_V1";
constexpr std::string_view kComplete = "DROIDLOOM_DATA_UNMOUNTED_V1";
enum class State { Closed, Open, Requested, Acknowledged };
State state = State::Closed;
struct stat initial_namespace {};
std::set<unsigned long> persistent_mount_ids;

struct Mounts {
    bool data = false;
    bool metadata = false;
    bool children = false;
    std::set<unsigned long> all_ids;
    std::set<unsigned long> storage_ids;
};

bool ReadMounts(Mounts* mounts) {
    auto close_file = [](FILE* file) { fclose(file); };
    std::unique_ptr<FILE, decltype(close_file)> file(fopen("/proc/self/mountinfo", "re"), close_file);
    struct statfs fs {};
    if (!file || fstatfs(fileno(file.get()), &fs) < 0 || fs.f_type != PROC_SUPER_MAGIC) return false;
    char* line = nullptr;
    size_t size = 0;
    bool valid = true;
    bool have_root = false;
    while (getline(&line, &size, file.get()) >= 0) {
        std::string_view row(line);
        unsigned long id = 0;
        auto first = row.find(' ');
        if (first == row.npos) { valid = false; break; }
        auto parsed = std::from_chars(row.data(), row.data() + first, id);
        if (parsed.ec != std::errc() || parsed.ptr != row.data() + first || id == 0) {
            valid = false; break;
        }
        mounts->all_ids.insert(id);
        for (unsigned i = 0; i < 4; ++i) {
            auto sep = row.find(' ');
            if (sep == row.npos) { valid = false; break; }
            row.remove_prefix(sep + 1);
        }
        auto end = row.find(' ');
        if (!valid || end == row.npos || row.find(" - ", end) == row.npos) { valid = false; break; }
        auto path = row.substr(0, end);
        have_root |= path == "/";
        mounts->data |= path == "/data";
        mounts->metadata |= path == "/metadata";
        bool nested = path.substr(0, 6) == "/data/" || path.substr(0, 10) == "/metadata/";
        mounts->children |= nested;
        if (path == "/data" || path == "/metadata" || nested) mounts->storage_ids.insert(id);
    }
    free(line);
    return valid && have_root && feof(file.get()) && !ferror(file.get());
}
}  // namespace

bool OpenShutdownChannel() {
    if (state != State::Closed || getppid() != 1) return false;
    int flags = fcntl(kSocket, F_GETFD);
    if (flags < 0 || fcntl(kSocket, F_SETFD, flags | FD_CLOEXEC) < 0) return false;
    int type = 0;
    socklen_t size = sizeof(type);
    if (getsockopt(kSocket, SOL_SOCKET, SO_TYPE, &type, &size) < 0 ||
        size != sizeof(type) || type != SOCK_DGRAM) return false;
    sockaddr_un addr {};
    size = sizeof(addr);
    if (getpeername(kSocket, reinterpret_cast<sockaddr*>(&addr), &size) < 0 ||
        addr.sun_family != AF_UNIX) return false;
    ucred peer {};
    size = sizeof(peer);
    if (getsockopt(kSocket, SOL_SOCKET, SO_PEERCRED, &peer, &size) < 0 ||
        size != sizeof(peer) || peer.pid != 1 || peer.uid != 0 || peer.gid != 0) return false;
    int enabled = 1;
    Mounts mounts;
    if (setsockopt(kSocket, SOL_SOCKET, SO_PASSCRED, &enabled, sizeof(enabled)) < 0 ||
        stat("/proc/self/ns/mnt", &initial_namespace) < 0 ||
        !ReadMounts(&mounts) || !mounts.data || !mounts.metadata) return false;
    persistent_mount_ids.swap(mounts.storage_ids);
    state = State::Open;
    return true;
}

int ShutdownFd() {
    return state == State::Open ? kSocket : -1;
}

bool ReceiveShutdownRequest() {
    if (state != State::Open) return false;
    std::array<char, 64> bytes {};
    iovec part {bytes.data(), bytes.size()};
    alignas(cmsghdr) char control[CMSG_SPACE(sizeof(ucred))] {};
    msghdr msg {};
    msg.msg_iov = &part;
    msg.msg_iovlen = 1;
    msg.msg_control = control;
    msg.msg_controllen = sizeof(control);
    ssize_t n;
    do { n = recvmsg(kSocket, &msg, MSG_DONTWAIT | MSG_CMSG_CLOEXEC); }
    while (n < 0 && errno == EINTR);
    if (n < 0) return false;
    bool trusted = false;
    bool valid = !(msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC));
    for (auto* c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c)) {
        if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_CREDENTIALS &&
            c->cmsg_len == CMSG_LEN(sizeof(ucred)) && !trusted) {
            ucred cred {};
            memcpy(&cred, CMSG_DATA(c), sizeof(cred));
            trusted = cred.pid == 1 && cred.uid == 0 && cred.gid == 0;
            valid &= trusted;
        } else {
            valid = false;
            if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS) {
                size_t count = (c->cmsg_len - CMSG_LEN(0)) / sizeof(int);
                for (size_t i = 0; i < count; ++i) {
                    int fd;
                    memcpy(&fd, CMSG_DATA(c) + i * sizeof(fd), sizeof(fd));
                    close(fd);
                }
            }
        }
    }
    if (!valid || !trusted || std::string_view(bytes.data(), n) != kRequest) return false;
    state = State::Requested;
    return true;
}

bool AcknowledgeUnmount() {
    if (state != State::Requested) return false;
    Mounts mounts;
    struct stat current {};
    if (stat("/proc/self/ns/mnt", &current) < 0 || current.st_dev != initial_namespace.st_dev ||
        current.st_ino != initial_namespace.st_ino || !ReadMounts(&mounts) ||
        mounts.data || mounts.metadata || mounts.children) return false;
    for (auto id : persistent_mount_ids) if (mounts.all_ids.count(id)) return false;
    ssize_t sent;
    do { sent = send(kSocket, kComplete.data(), kComplete.size(), MSG_NOSIGNAL | MSG_DONTWAIT); }
    while (sent < 0 && errno == EINTR);
    if (sent != static_cast<ssize_t>(kComplete.size())) return false;
    state = State::Acknowledged;
    return true;
}
}  // namespace droidloom::bootstrap
