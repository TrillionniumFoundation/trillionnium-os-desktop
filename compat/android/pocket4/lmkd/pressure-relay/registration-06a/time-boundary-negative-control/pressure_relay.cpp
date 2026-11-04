// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
#include "pressure_relay.h"

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <poll.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

namespace droidloom::lmkd::relay {
namespace {
constexpr std::array<uint8_t, 8> kMagic = {'P', '4', 'P', 'S', 'I', '0', '1', '!'};

template <size_t N>
void Put(std::array<uint8_t, N>& wire, size_t offset, uint64_t value, size_t bytes) {
    for (size_t i = 0; i < bytes; ++i) wire[offset + i] = (value >> (8 * i)) & 255;
}
template <size_t N>
uint64_t Get(const std::array<uint8_t, N>& wire, size_t offset, size_t bytes) {
    uint64_t value = 0;
    for (size_t i = 0; i < bytes; ++i) value |= uint64_t(wire[offset + i]) << (8 * i);
    return value;
}
bool Nonzero(const Bytes32& value) {
    return std::any_of(value.begin(), value.end(), [](uint8_t x) { return x != 0; });
}
bool MonotonicNow(uint64_t* value) {
    timespec now{};
    if (clock_gettime(CLOCK_MONOTONIC, &now) || now.tv_sec < 0 || now.tv_nsec < 0 ||
        now.tv_nsec >= 1000000000 ||
        uint64_t(now.tv_sec) > (std::numeric_limits<uint64_t>::max() - uint64_t(now.tv_nsec)) / 1000000000)
        return false;
    *value = uint64_t(now.tv_sec) * 1000000000 + uint64_t(now.tv_nsec);
    return *value != 0;
}
bool SocketInt(int fd, int option, int* value) {
    socklen_t size = sizeof(*value);
    return getsockopt(fd, SOL_SOCKET, option, value, &size) == 0 && size == sizeof(*value);
}
bool CloseUnexpectedRights(msghdr* message) {
    bool any = false;
    for (cmsghdr* header = CMSG_FIRSTHDR(message); header;
         header = CMSG_NXTHDR(message, header)) {
        any = true;
        if (header->cmsg_level != SOL_SOCKET || header->cmsg_type != SCM_RIGHTS ||
            header->cmsg_len < CMSG_LEN(0)) continue;
        size_t count = (header->cmsg_len - CMSG_LEN(0)) / sizeof(int);
        const auto* data = reinterpret_cast<const unsigned char*>(CMSG_DATA(header));
        for (size_t i = 0; i < count; ++i) {
            int fd;
            std::memcpy(&fd, data + i * sizeof(fd), sizeof(fd));
            close(fd);
        }
    }
    return any;
}
}  // namespace

bool Scope::operator==(const Scope& o) const {
    return generation == o.generation && cgroup_device == o.cgroup_device &&
           cgroup_inode == o.cgroup_inode && budget == o.budget;
}
bool Config::operator==(const Config& o) const {
    return level == o.level && window_us == o.window_us && stall_us == o.stall_us;
}
bool Credentials::operator==(const Credentials& o) const {
    return pid == o.pid && uid == o.uid && gid == o.gid;
}
Bytes32 BindBudget(uint64_t maximum, uint64_t high, uint64_t swap_maximum,
                   bool high_unlimited, bool swap_unlimited) {
    Bytes32 bytes{};
    Put(bytes, 0, maximum, 8);
    Put(bytes, 8, high_unlimited ? 0 : high, 8);
    Put(bytes, 16, swap_unlimited ? 0 : swap_maximum, 8);
    Put(bytes, 24, (high_unlimited ? 1U : 0U) | (swap_unlimited ? 2U : 0U), 4);
    Put(bytes, 28, 1, 4);
    return bytes;
}
bool ValidScope(const Scope& s) {
    uint64_t maximum = Get(s.budget, 0, 8), high = Get(s.budget, 8, 8);
    uint64_t swap = Get(s.budget, 16, 8), flags = Get(s.budget, 24, 4);
    return Nonzero(s.generation) && s.cgroup_device && s.cgroup_inode &&
           Get(s.budget, 28, 4) == 1 && flags <= 3 && maximum > 0 &&
           maximum <= uint64_t(std::numeric_limits<int64_t>::max()) &&
           swap <= uint64_t(std::numeric_limits<int64_t>::max()) &&
           ((flags & 1) ? high == 0 : high > 0 && high <= maximum) &&
           (!(flags & 2) || swap == 0);
}
bool ValidConfig(const Config& c) {
    return (c.level == Level::Medium || c.level == Level::Critical) &&
           c.window_us >= 500000 && c.window_us <= 10000000 &&
           c.stall_us > 0 && c.stall_us <= c.window_us;
}
Wire Encode(const Event& e) {
    Wire w{};
    std::copy(kMagic.begin(), kMagic.end(), w.begin());
    Put(w, 8, 1, 4);
    Put(w, 12, static_cast<uint32_t>(e.config.level), 4);
    std::copy(e.scope.generation.begin(), e.scope.generation.end(), w.begin() + 16);
    Put(w, 48, e.scope.cgroup_device, 8);
    Put(w, 56, e.scope.cgroup_inode, 8);
    std::copy(e.scope.budget.begin(), e.scope.budget.end(), w.begin() + 64);
    Put(w, 96, e.config.window_us, 8);
    Put(w, 104, e.config.stall_us, 8);
    Put(w, 112, e.sequence, 8);
    Put(w, 120, e.observed_monotonic_ns, 8);
    return w;
}
bool Decode(const Wire& w, Event* e) {
    if (!e || !std::equal(kMagic.begin(), kMagic.end(), w.begin()) || Get(w, 8, 4) != 1)
        return false;
    e->config.level = static_cast<Level>(Get(w, 12, 4));
    std::copy_n(w.begin() + 16, 32, e->scope.generation.begin());
    e->scope.cgroup_device = Get(w, 48, 8);
    e->scope.cgroup_inode = Get(w, 56, 8);
    std::copy_n(w.begin() + 64, 32, e->scope.budget.begin());
    e->config.window_us = Get(w, 96, 8);
    e->config.stall_us = Get(w, 104, 8);
    e->sequence = Get(w, 112, 8);
    e->observed_monotonic_ns = Get(w, 120, 8);
    return ValidScope(e->scope) && ValidConfig(e->config) && e->sequence &&
           e->sequence != std::numeric_limits<uint64_t>::max() && e->observed_monotonic_ns;
}
bool ReadCredentials(int fd, Credentials* credentials) {
    ucred actual{};
    socklen_t size = sizeof(actual);
    if (!credentials || getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &actual, &size) ||
        size != sizeof(actual)) return false;
    *credentials = {actual.pid, actual.uid, actual.gid};
    return true;
}

Monitor::~Monitor() { Revoke(); }
void Monitor::Revoke() {
    if (fd_ >= 0) close(fd_);
    fd_ = -1;
    last_sequence_ = last_event_ns_ = last_local_ns_ = 0;
}
bool Monitor::Adopt(int fd, const Scope& s, const Config& c, const Credentials& peer) {
    if (adopted_once_) {
        if (fd >= 0 && fd != fd_) close(fd);
        Revoke();
        return false;
    }
    adopted_once_ = true;
    fd_ = fd;
    scope_ = s;
    config_ = c;
    peer_ = peer;
    int type = 0, domain = 0;
    int descriptor_flags = fd_ < 0 ? -1 : fcntl(fd_, F_GETFD);
    int status_flags = fd_ < 0 ? -1 : fcntl(fd_, F_GETFL);
    Credentials actual;
    if (fd_ < 0 || !ValidScope(s) || !ValidConfig(c) ||
        descriptor_flags < 0 || status_flags < 0 ||
        (descriptor_flags & FD_CLOEXEC) == 0 || (status_flags & O_NONBLOCK) == 0 ||
        !SocketInt(fd_, SO_TYPE, &type) || type != SOCK_SEQPACKET ||
        !SocketInt(fd_, SO_DOMAIN, &domain) || domain != AF_UNIX ||
        !ReadCredentials(fd_, &actual) || !(actual == peer_)) {
        Revoke();
        return false;
    }
    short readiness = 0;
    if (!TransportHealthy(&readiness)) {
        Revoke();
        return false;
    }
    return true;
}
bool Monitor::TransportHealthy(short* readiness) {
    Credentials actual;
    if (fd_ < 0 || !ReadCredentials(fd_, &actual) || !(actual == peer_)) return false;
    pollfd descriptor{fd_, POLLIN | POLLRDHUP, 0};
    int rc = poll(&descriptor, 1, 0);
    if (rc < 0 || descriptor.revents & (POLLHUP | POLLRDHUP | POLLERR | POLLNVAL))
        return false;
    *readiness = descriptor.revents;
    return true;
}
Result Monitor::Fail(Error error) {
    Revoke();
    return {Status::Revoked, error, 0, 0, 0};
}
Result Monitor::Consume(const Scope& scope) {
    uint64_t before = 0, after = 0;
    if (!MonotonicNow(&before)) return Fail(Error::ClockInvalid);
    Result result = ConsumeAt(scope, before);
    if (result.status == Status::Revoked) return result;
    // Nonblocking I/O can still fault or stall on a kernel memory charge. A
    // fresh entry timestamp cannot certify an event after such a delay.
    if (!MonotonicNow(&after) || after < before || after < last_local_ns_)
        return Fail(Error::ClockInvalid);
    last_local_ns_ = after;
    short readiness = 0;
    if (!TransportHealthy(&readiness)) return Fail(Error::Transport);
    if (result.status == Status::Event &&
        after - result.observed_monotonic_ns >= config_.window_us * 1000) {
        result.status = Status::Stale;
        ++result.stale_records;
    }
    return result;
}
#ifdef DROIDLOOM_RELAY_TEST
Result Monitor::ConsumeAtForTest(const Scope& scope, uint64_t now_ns) {
    return ConsumeAt(scope, now_ns);
}
#endif
Result Monitor::ConsumeAt(const Scope& scope, uint64_t now_ns) {
    if (!active()) return {Status::Revoked, Error::Transport, 0, 0, 0};
    if (!(scope == scope_)) return Fail(Error::ScopeChanged);
    if (!now_ns || now_ns < last_local_ns_) return Fail(Error::ClockInvalid);
    last_local_ns_ = now_ns;
    short readiness = 0;
    if (!TransportHealthy(&readiness)) return Fail(Error::Transport);
    Result result;
    for (size_t i = 0; i < kMaxDrainRecords; ++i) {
        Wire wire{};
        alignas(cmsghdr) unsigned char ancillary[CMSG_SPACE(16 * sizeof(int))]{};
        iovec payload{wire.data(), wire.size()};
        msghdr message{};
        message.msg_iov = &payload;
        message.msg_iovlen = 1;
        message.msg_control = ancillary;
        message.msg_controllen = sizeof(ancillary);
        ssize_t received = recvmsg(fd_, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC | MSG_TRUNC);
        if (received < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            if (errno == EINTR) {
                // No unbounded retry in the pressure path. A later poll retries.
                if (!TransportHealthy(&readiness)) return Fail(Error::Transport);
                return result;
            }
            return Fail(Error::Transport);
        }
        bool unexpected_control = CloseUnexpectedRights(&message);
        if (unexpected_control || (message.msg_flags & MSG_CTRUNC)) return Fail(Error::AncillaryData);
        if (received != static_cast<ssize_t>(wire.size()) || (message.msg_flags & MSG_TRUNC))
            return Fail(Error::RecordSize);
        Event event;
        if (!Decode(wire, &event)) return Fail(Error::RecordEncoding);
        if (!(event.scope == scope_)) return Fail(Error::EventScope);
        if (!(event.config == config_)) return Fail(Error::EventConfig);
        if (event.sequence != last_sequence_ + 1) return Fail(Error::Sequence);
        if (event.observed_monotonic_ns > now_ns || event.observed_monotonic_ns < last_event_ns_)
            return Fail(Error::Timestamp);
        last_sequence_ = event.sequence;
        last_event_ns_ = event.observed_monotonic_ns;
        result.last_sequence = event.sequence;
        if (now_ns - event.observed_monotonic_ns >= config_.window_us * 1000) {
            ++result.stale_records;
            if (result.status != Status::Event) result.status = Status::Stale;
        } else {
            result.status = Status::Event;
            result.observed_monotonic_ns = event.observed_monotonic_ns;
        }
        if (!TransportHealthy(&readiness)) return Fail(Error::Transport);
        if (!(readiness & POLLIN)) break;
        if (i + 1 == kMaxDrainRecords) return Fail(Error::DrainLimit);
    }
    if (!TransportHealthy(&readiness)) return Fail(Error::Transport);
    return result;
}
}  // namespace droidloom::lmkd::relay
