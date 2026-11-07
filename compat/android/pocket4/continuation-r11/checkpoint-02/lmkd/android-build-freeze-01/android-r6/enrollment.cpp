// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
#include "enrollment.h"

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <poll.h>
#include <sys/random.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

namespace droidloom::lmkd::relay {
namespace {
constexpr std::array<uint8_t, 8> kRequestMagic{{'P','4','E','N','R','0','1','!'}};
constexpr std::array<uint8_t, 8> kGrantMagic{{'P','4','E','N','G','0','1','!'}};
constexpr int kPeerPidfd = 77;
constexpr short kBad = POLLERR | POLLHUP | POLLRDHUP | POLLNVAL;

template <size_t N>
void Put(std::array<uint8_t, N>& wire, size_t offset, uint64_t value, size_t bytes) {
    for (size_t i = 0; i < bytes; ++i) wire[offset + i] = static_cast<uint8_t>(value >> (8 * i));
}
template <size_t N>
uint64_t Get(const std::array<uint8_t, N>& wire, size_t offset, size_t bytes) {
    uint64_t value = 0;
    for (size_t i = 0; i < bytes; ++i) value |= uint64_t(wire[offset + i]) << (8 * i);
    return value;
}
template <size_t N>
void Configs(std::array<uint8_t, N>& wire, size_t offset, const EnrollmentRequest& request) {
    for (size_t i = 0; i < request.count && i < kMaxMonitors; ++i) {
        size_t at = offset + 24 * i;
        Put(wire, at, static_cast<uint32_t>(request.configs[i].level), 4);
        Put(wire, at + 8, request.configs[i].window_us, 8);
        Put(wire, at + 16, request.configs[i].stall_us, 8);
    }
}
template <size_t N>
bool DecodeConfigs(const std::array<uint8_t, N>& wire, size_t offset, EnrollmentRequest* request) {
    if (request->count < 1 || request->count > kMaxMonitors) return false;
    for (size_t i = 0; i < kMaxMonitors; ++i) {
        size_t at = offset + 24 * i;
        if (i >= request->count) {
            for (size_t j = at; j < at + 24; ++j) if (wire[j] != 0) return false;
            continue;
        }
        if (Get(wire, at + 4, 4) != 0) return false;
        request->configs[i] = {static_cast<Level>(Get(wire, at, 4)),
                              Get(wire, at + 8, 8), Get(wire, at + 16, 8)};
    }
    return true;
}
bool SocketInt(int fd, int option, int* value) {
    socklen_t length = sizeof(*value);
    return getsockopt(fd, SOL_SOCKET, option, value, &length) == 0 && length == sizeof(*value);
}
bool NonblockingPacket(int fd) {
    int flags = fcntl(fd, F_GETFL), descriptor = fcntl(fd, F_GETFD), type = 0, domain = 0;
    return flags >= 0 && descriptor >= 0 && (flags & O_NONBLOCK) && (descriptor & FD_CLOEXEC) &&
           SocketInt(fd, SO_TYPE, &type) && type == SOCK_SEQPACKET &&
           SocketInt(fd, SO_DOMAIN, &domain) && domain == AF_UNIX;
}
bool Now(uint64_t* value) {
    timespec t{};
    if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0 || t.tv_nsec < 0 ||
        t.tv_nsec >= 1000000000 || uint64_t(t.tv_sec) >
        (std::numeric_limits<uint64_t>::max() - uint64_t(t.tv_nsec)) / 1000000000) return false;
    *value = uint64_t(t.tv_sec) * 1000000000 + uint64_t(t.tv_nsec);
    return *value != 0;
}
bool BeforeDeadline(uint64_t start, uint64_t deadline, uint64_t* last) {
    uint64_t now = 0;
    if (!Now(&now) || now < start || now < *last || now >= deadline) return false;
    *last = now;
    return true;
}
bool Wait(int fd, int pidfd, short wanted, uint64_t start, uint64_t deadline, uint64_t* last) {
    while (BeforeDeadline(start, deadline, last)) {
        uint64_t remaining_ms = (deadline - *last + 999999) / 1000000;
        int timeout = static_cast<int>(std::min<uint64_t>(remaining_ms, 100));
        pollfd descriptors[2]{{fd, static_cast<short>(wanted | POLLRDHUP), 0}, {pidfd, POLLIN, 0}};
        int n = poll(descriptors, 2, timeout);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 || descriptors[0].revents & kBad || descriptors[1].revents != 0) return false;
        if (!BeforeDeadline(start, deadline, last)) return false;
        if (descriptors[0].revents & wanted) return true;
    }
    return false;
}
// All kernel-delivered FDs are closed on every malformed/truncated path.
bool ReceiveRights(msghdr* message, std::array<int, kMaxMonitors>* output, size_t* count) {
    *count = 0;
    bool valid = true;
    size_t headers = 0;
    for (cmsghdr* header = CMSG_FIRSTHDR(message); header; header = CMSG_NXTHDR(message, header)) {
        ++headers;
        if (header->cmsg_level != SOL_SOCKET || header->cmsg_type != SCM_RIGHTS ||
            header->cmsg_len < CMSG_LEN(0)) { valid = false; continue; }
        size_t bytes = header->cmsg_len - CMSG_LEN(0);
        if (bytes % sizeof(int)) valid = false;
        const unsigned char* data = CMSG_DATA(header);
        for (size_t i = 0; i < bytes / sizeof(int); ++i) {
            int fd = -1;
            std::memcpy(&fd, data + i * sizeof(int), sizeof(fd));
            if (*count < kMaxMonitors) (*output)[(*count)++] = fd;
            else { close(fd); valid = false; }
        }
    }
    return valid && headers == 1 && !(message->msg_flags & MSG_CTRUNC);
}
}  // namespace

bool EnrollmentRequest::operator==(const EnrollmentRequest& other) const {
    if (nonce != other.nonce || cgroup_device != other.cgroup_device ||
        cgroup_inode != other.cgroup_inode || budget != other.budget || count != other.count ||
        count > kMaxMonitors) return false;
    for (size_t i = 0; i < count; ++i) if (!(configs[i] == other.configs[i])) return false;
    return true;
}
bool ValidRequest(const EnrollmentRequest& request) {
    Scope scope{request.nonce, request.cgroup_device, request.cgroup_inode, request.budget};
    if (!ValidScope(scope) || request.count < 1 || request.count > kMaxMonitors) return false;
    for (size_t i = 0; i < request.count; ++i) if (!ValidConfig(request.configs[i])) return false;
    return request.count != 2 || request.configs[0].level != request.configs[1].level;
}
bool FreshRequestNonce(Bytes32* nonce) {
    if (!nonce) return false;
    nonce->fill(0);
    ssize_t count = getrandom(nonce->data(), nonce->size(), 0);
    if (count != static_cast<ssize_t>(nonce->size()) ||
        std::all_of(nonce->begin(), nonce->end(), [](uint8_t b) { return b == 0; })) {
        nonce->fill(0);
        return false;
    }
    return true;
}
RequestWire EncodeRequest(const EnrollmentRequest& request) {
    RequestWire wire{};
    std::copy(kRequestMagic.begin(), kRequestMagic.end(), wire.begin());
    Put(wire, 8, 1, 4); Put(wire, 12, request.count, 4);
    std::copy(request.nonce.begin(), request.nonce.end(), wire.begin() + 16);
    Put(wire, 48, request.cgroup_device, 8); Put(wire, 56, request.cgroup_inode, 8);
    std::copy(request.budget.begin(), request.budget.end(), wire.begin() + 64);
    Configs(wire, 96, request);
    return wire;
}
bool DecodeRequest(const RequestWire& wire, EnrollmentRequest* request) {
    if (!request || !std::equal(kRequestMagic.begin(), kRequestMagic.end(), wire.begin()) || Get(wire, 8, 4) != 1) return false;
    EnrollmentRequest decoded{};
    decoded.count = static_cast<uint32_t>(Get(wire, 12, 4));
    std::copy_n(wire.begin() + 16, 32, decoded.nonce.begin());
    decoded.cgroup_device = Get(wire, 48, 8); decoded.cgroup_inode = Get(wire, 56, 8);
    std::copy_n(wire.begin() + 64, 32, decoded.budget.begin());
    if (!DecodeConfigs(wire, 96, &decoded) || !ValidRequest(decoded)) return false;
    *request = decoded;
    return true;
}
GrantWire EncodeGrant(const EnrollmentGrant& grant) {
    GrantWire wire{};
    std::copy(kGrantMagic.begin(), kGrantMagic.end(), wire.begin());
    Put(wire, 8, 1, 4); Put(wire, 12, grant.request.count, 4);
    std::copy(grant.request.nonce.begin(), grant.request.nonce.end(), wire.begin() + 16);
    std::copy(grant.generation.begin(), grant.generation.end(), wire.begin() + 48);
    Put(wire, 80, grant.request.cgroup_device, 8); Put(wire, 88, grant.request.cgroup_inode, 8);
    std::copy(grant.request.budget.begin(), grant.request.budget.end(), wire.begin() + 96);
    Configs(wire, 128, grant.request);
    return wire;
}
bool DecodeGrant(const GrantWire& wire, EnrollmentGrant* grant) {
    if (!grant || !std::equal(kGrantMagic.begin(), kGrantMagic.end(), wire.begin()) || Get(wire, 8, 4) != 1) return false;
    EnrollmentGrant decoded{};
    decoded.request.count = static_cast<uint32_t>(Get(wire, 12, 4));
    std::copy_n(wire.begin() + 16, 32, decoded.request.nonce.begin());
    std::copy_n(wire.begin() + 48, 32, decoded.generation.begin());
    decoded.request.cgroup_device = Get(wire, 80, 8); decoded.request.cgroup_inode = Get(wire, 88, 8);
    std::copy_n(wire.begin() + 96, 32, decoded.request.budget.begin());
    Scope scope{decoded.generation, decoded.request.cgroup_device, decoded.request.cgroup_inode, decoded.request.budget};
    if (!DecodeConfigs(wire, 128, &decoded.request) || !ValidRequest(decoded.request) || !ValidScope(scope)) return false;
    *grant = decoded;
    return true;
}

GrantRecipients::~GrantRecipients() { Reset(); }
void GrantRecipients::Reset() {
    for (int& fd : fds_) { if (fd >= 0) close(fd); fd = -1; }
    grant_ = {}; complete_ = false;
}
int GrantRecipients::Take(size_t index) {
    if (!complete_ || index >= grant_.request.count) return -1;
    int fd = fds_[index]; fds_[index] = -1; return fd;
}
EnrollmentClient::~EnrollmentClient() { Close(); }
void EnrollmentClient::Close() {
    if (control_fd_ >= 0) close(control_fd_);
    if (server_pidfd_ >= 0) close(server_pidfd_);
    control_fd_ = server_pidfd_ = -1;
}
bool EnrollmentClient::Healthy() const {
    Credentials actual;
    if (control_fd_ < 0 || server_pidfd_ < 0 || !ReadCredentials(control_fd_, &actual) || !(actual == server_)) return false;
    pollfd descriptors[2]{{control_fd_, POLLIN | POLLRDHUP, 0}, {server_pidfd_, POLLIN, 0}};
    // After the single grant, any additional control data is a protocol error.
    return poll(descriptors, 2, 0) == 0 && descriptors[0].revents == 0 && descriptors[1].revents == 0;
}
bool EnrollmentClient::Exchange(int connected_fd, const Credentials& expected_server,
                                const EnrollmentRequest& request, uint32_t timeout_ms,
                                GrantRecipients* recipients) {
    // Every failed attempt clears the supplied output, including an unclaimed
    // successful grant passed back on a forbidden replay.
    if (recipients) recipients->Reset();
    if (attempted_) {
        if (connected_fd >= 0 && connected_fd != control_fd_) close(connected_fd);
        Close(); return false;
    }
    attempted_ = true; control_fd_ = connected_fd; server_ = expected_server;
    auto fail = [&]() { if (recipients) recipients->Reset(); Close(); return false; };
    uint64_t started = 0, last = 0;
    if (!recipients || !ValidRequest(request) || timeout_ms == 0 || timeout_ms > 2000 ||
        !NonblockingPacket(control_fd_) || !Now(&started) ||
        started > std::numeric_limits<uint64_t>::max() - uint64_t(timeout_ms) * 1000000) return fail();
    uint64_t deadline = started + uint64_t(timeout_ms) * 1000000; last = started;
    Credentials actual;
    if (!ReadCredentials(control_fd_, &actual) || !(actual == server_) ||
        !SocketInt(control_fd_, kPeerPidfd, &server_pidfd_) || server_pidfd_ < 0) return fail();
    int pid_flags = fcntl(server_pidfd_, F_GETFD);
    if (pid_flags < 0 || !(pid_flags & FD_CLOEXEC) || !Healthy()) return fail();
    RequestWire request_wire = EncodeRequest(request);
    for (;;) {
        if (!Wait(control_fd_, server_pidfd_, POLLOUT, started, deadline, &last)) return fail();
        ssize_t sent = send(control_fd_, request_wire.data(), request_wire.size(), MSG_DONTWAIT | MSG_NOSIGNAL);
        if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (sent != static_cast<ssize_t>(request_wire.size())) return fail();
        break;
    }
    GrantWire wire{};
    alignas(cmsghdr) unsigned char ancillary[CMSG_SPACE(4 * sizeof(int))]{};
    size_t fd_count = 0;
    for (;;) {
        if (!Wait(control_fd_, server_pidfd_, POLLIN, started, deadline, &last)) return fail();
        iovec payload{wire.data(), wire.size()};
        msghdr message{}; message.msg_iov = &payload; message.msg_iovlen = 1;
        message.msg_control = ancillary; message.msg_controllen = sizeof(ancillary);
        ssize_t count = recvmsg(control_fd_, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC | MSG_TRUNC);
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        bool rights_ok = count >= 0 && ReceiveRights(&message, &recipients->fds_, &fd_count);
        if (count != static_cast<ssize_t>(wire.size()) || (message.msg_flags & MSG_TRUNC) ||
            !rights_ok || fd_count != request.count || !DecodeGrant(wire, &recipients->grant_) ||
            !(recipients->grant_.request == request)) return fail();
        break;
    }
    for (size_t i = 0; i < fd_count; ++i) {
        if (!NonblockingPacket(recipients->fds_[i]) || !ReadCredentials(recipients->fds_[i], &actual) ||
            !(actual == server_)) return fail();
        pollfd descriptor{recipients->fds_[i], POLLIN | POLLRDHUP, 0};
        if (poll(&descriptor, 1, 0) < 0 || descriptor.revents & kBad) return fail();
    }
    if (!Healthy() || !BeforeDeadline(started, deadline, &last)) return fail();
    recipients->complete_ = true;
    return true;
}
}  // namespace droidloom::lmkd::relay
