// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
#include "relay_session.h"

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <poll.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

namespace droidloom::lmkd::relay {
namespace {
bool RootDirectory(int fd) {
    struct stat st{};
    return fd >= 0 && !fstat(fd, &st) && S_ISDIR(st.st_mode) &&
           st.st_uid == 0 && st.st_gid == 0 && (st.st_mode & 0022) == 0;
}
bool SameSocket(const struct stat& a, const struct stat& b) {
    return S_ISSOCK(a.st_mode) && S_ISSOCK(b.st_mode) && a.st_dev == b.st_dev &&
           a.st_ino == b.st_ino && a.st_uid == b.st_uid && a.st_gid == b.st_gid &&
           a.st_mode == b.st_mode;
}
}  // namespace

bool Session::CheckClock(uint64_t* result) {
    struct timespec now{};
    if (!result || clock_gettime(CLOCK_MONOTONIC, &now) || now.tv_sec < 0 ||
        now.tv_nsec < 0 || now.tv_nsec >= 1000000000 ||
        static_cast<uint64_t>(now.tv_sec) >
            (std::numeric_limits<uint64_t>::max() - static_cast<uint64_t>(now.tv_nsec)) /
                1000000000) return false;
    const uint64_t value = static_cast<uint64_t>(now.tv_sec) * 1000000000 +
                           static_cast<uint64_t>(now.tv_nsec);
    if (!value || value < last_clock_ns_) return false;
    last_clock_ns_ = value;
    *result = value;
    return true;
}

int Session::Index(Level level) const {
    for (uint32_t i = 0; i < grant_.request.count; ++i)
        if (grant_.request.configs[i].level == level) return static_cast<int>(i);
    return -1;
}

bool Session::FreshDecision() {
    uint64_t now = 0;
    if (!active_ || !decision_observed_ns_ || !decision_window_ns_) return false;
    if (!CheckClock(&now) || now < decision_observed_ns_) {
        active_ = false;
        decision_observed_ns_ = decision_window_ns_ = 0;
        return false;
    }
    if (now - decision_observed_ns_ >= decision_window_ns_) {
        decision_observed_ns_ = decision_window_ns_ = 0;
        return false;
    }
    return true;
}

bool Session::CheckScopeAndTransport() {
    AccountingScope current{};
    uint64_t now = 0;
    if (!active_ || !CheckClock(&now) || !client_.Healthy() || !probe_.read ||
        !probe_.read(probe_.context, &current) || current.device != scope_.cgroup_device ||
        current.inode != scope_.cgroup_inode || current.budget != scope_.budget) {
        active_ = false;
        return false;
    }
    for (uint32_t i = 0; i < grant_.request.count; ++i) {
        pollfd descriptor{monitors_[i].fd(), POLLIN | POLLRDHUP, 0};
        if (descriptor.fd < 0 || poll(&descriptor, 1, 0) < 0 ||
            (descriptor.revents & (POLLHUP | POLLRDHUP | POLLERR | POLLNVAL))) {
            active_ = false;
            return false;
        }
    }
    // Recheck after accounting/health I/O; no earlier timestamp certifies a
    // result that was delayed inside a syscall or a memory charge.
    if (!client_.Healthy() || !CheckClock(&now)) {
        active_ = false;
        return false;
    }
    return true;
}

bool Session::Start(int connected_fd, const Credentials& server,
                    const EnrollmentRequest& request, ScopeProbe probe) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (attempted_) {
        if (connected_fd >= 0 && connected_fd != client_.control_fd()) close(connected_fd);
        StopLocked();
        return false;
    }
    attempted_ = true;
    GrantRecipients recipients;
    if (!probe.read || !client_.Exchange(connected_fd, server, request, 1000, &recipients)) {
        if (!probe.read && connected_fd >= 0) close(connected_fd);
        StopLocked();
        return false;
    }
    grant_ = recipients.grant();
    scope_ = {grant_.generation, request.cgroup_device, request.cgroup_inode, request.budget};
    probe_ = probe;
    for (uint32_t i = 0; i < request.count; ++i) {
        if (!monitors_[i].Adopt(recipients.Take(i), scope_, request.configs[i], server)) {
            StopLocked();
            return false;
        }
    }
    active_ = true;
    if (!CheckScopeAndTransport()) {
        StopLocked();
        return false;
    }
    return true;
}

int Session::fd(Level level) const {
    std::lock_guard<std::mutex> lock(mutex_);
    const int i = Index(level);
    return active_ && i >= 0 ? monitors_[static_cast<size_t>(i)].fd() : -1;
}
int Session::control_fd() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return active_ ? client_.control_fd() : -1;
}
bool Session::active() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return active_;
}
void Session::StopLocked() {
    active_ = false;
    decision_observed_ns_ = decision_window_ns_ = 0;
    client_.Close();
    for (Monitor& monitor : monitors_) monitor.Revoke();
}
void Session::Stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    StopLocked();
}

Ready Session::Handle(Level level, uint32_t events) {
    std::lock_guard<std::mutex> lock(mutex_);
    const int index = Index(level);
    if (index < 0 || (events & ~static_cast<uint32_t>(EPOLLIN)) || !CheckScopeAndTransport()) {
        active_ = false;
        return Ready::Revoked;
    }
    if (!events) return FreshDecision() ? Ready::Polling : Ready::Stale;
    const size_t i = static_cast<size_t>(index);
    const Result result = monitors_[i].Consume(scope_);
    if (result.status == Status::Revoked || !CheckScopeAndTransport()) {
        active_ = false;
        return Ready::Revoked;
    }
    if (result.status == Status::Event) {
        uint64_t after = 0;
        if (!CheckClock(&after) || result.observed_monotonic_ns > after) {
            active_ = false;
            return Ready::Revoked;
        }
        if (after - result.observed_monotonic_ns >= grant_.request.configs[i].window_us * 1000) {
            decision_observed_ns_ = decision_window_ns_ = 0;
            return Ready::Stale;
        }
        decision_observed_ns_ = result.observed_monotonic_ns;
        decision_window_ns_ = grant_.request.configs[i].window_us * 1000;
        return Ready::Event;
    }
    if (result.status == Status::Stale) decision_observed_ns_ = decision_window_ns_ = 0;
    return result.status == Status::Stale ? Ready::Stale : Ready::Empty;
}

int ConnectLifecycleEndpoint(Credentials* expected_server) {
    if (!expected_server) { errno = EINVAL; return -1; }
    constexpr const char* name = "droidloom-lmkd-psi";
    int root = open("/", O_PATH | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    int dev = -1, sockets = -1, fd = -1;
    auto fail = [&]() {
        const int saved = errno;
        if (fd >= 0) close(fd);
        if (sockets >= 0) close(sockets);
        if (dev >= 0) close(dev);
        if (root >= 0) close(root);
        errno = saved;
        return -1;
    };
    if (!RootDirectory(root)) return fail();
    dev = openat(root, "dev", O_PATH | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (!RootDirectory(dev)) return fail();
    sockets = openat(dev, "socket", O_PATH | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (!RootDirectory(sockets)) return fail();
    struct stat before{}, after{};
    if (fstatat(sockets, name, &before, AT_SYMLINK_NOFOLLOW) || !S_ISSOCK(before.st_mode) ||
        before.st_uid != geteuid() || before.st_gid != getegid() ||
        (before.st_mode & 07777) != 0600) return fail();
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    const int written = std::snprintf(address.sun_path, sizeof(address.sun_path),
                                      "/proc/self/fd/%d/%s", sockets, name);
    if (written <= 0 || static_cast<size_t>(written) >= sizeof(address.sun_path)) return fail();
    fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) return fail();
    if (connect(fd, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0) {
        if (errno != EINPROGRESS) return fail();
        pollfd ready{fd, POLLOUT | POLLRDHUP, 0};
        int error = 0;
        socklen_t length = sizeof(error);
        if (poll(&ready, 1, 100) <= 0 || !(ready.revents & POLLOUT) ||
            (ready.revents & (POLLHUP | POLLRDHUP | POLLERR | POLLNVAL)) ||
            getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length) ||
            length != sizeof(error) || error) return fail();
    }
    Credentials peer{};
    if (fstatat(sockets, name, &after, AT_SYMLINK_NOFOLLOW) || !SameSocket(before, after) ||
        !ReadCredentials(fd, &peer) || peer.uid != 0 || peer.gid != 0 || peer.pid < 0)
        return fail();
    close(sockets);
    close(dev);
    close(root);
    *expected_server = peer;
    return fd;
}
}  // namespace droidloom::lmkd::relay
