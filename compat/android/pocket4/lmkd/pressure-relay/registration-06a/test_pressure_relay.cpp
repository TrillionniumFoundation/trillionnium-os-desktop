// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
// Native protocol and owned-FD controls. This executable never opens cgroups,
// registers PSI triggers, enters namespaces, or executes LMKD.
#include "pressure_relay.h"
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <functional>
#include <limits>
#include <poll.h>
#include <signal.h>
#include <string>
#include <sys/eventfd.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

using namespace droidloom::lmkd::relay;
static unsigned passed = 0;
static void Check(bool value, const char* label) {
    if (!value) { std::fprintf(stderr, "FAIL %s errno=%d\n", label, errno); std::exit(2); }
    ++passed;
    std::printf("PASS %s\n", label);
}
static void Need(bool value) { if (!value) { std::perror("test setup"); std::exit(3); } }
static Scope ScopeValue() {
    Scope s; s.generation.fill(0x51); s.budget = BindBudget(536870912, 402653184, 0, false, false);
    s.cgroup_device = 30; s.cgroup_inode = 987654;
    return s;
}
static Config ConfigValue() { return {Level::Critical, 1000000, 700000}; }
static Event E(uint64_t sequence = 1, uint64_t observed = 1000000000) {
    return {ScopeValue(), ConfigValue(), sequence, observed};
}
struct Pair {
    int host = -1, guest = -1;
    Credentials peer;
    Pair(bool bounded = true) {
        int fds[2]; Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, fds) == 0);
        host = fds[0]; guest = fds[1];
        int size = bounded ? 4096 : 262144;
        Need(setsockopt(host, SOL_SOCKET, SO_SNDBUF, &size, sizeof(size)) == 0);
        Need(setsockopt(guest, SOL_SOCKET, SO_RCVBUF, &size, sizeof(size)) == 0);
        Need(shutdown(host, SHUT_RD) == 0 && shutdown(guest, SHUT_WR) == 0);
        Need(ReadCredentials(guest, &peer));
    }
    ~Pair() { if (host >= 0) close(host); if (guest >= 0) close(guest); }
    int Take() { int value = guest; guest = -1; return value; }
    void Close() { if (host >= 0) close(host); host = -1; }
    bool Send(const Wire& w) { return send(host, w.data(), w.size(), MSG_DONTWAIT | MSG_NOSIGNAL) == ssize_t(w.size()); }
    void Put(const Event& e) { Need(Send(Encode(e))); }
    void Bind(Monitor& m) { Need(m.Adopt(Take(), ScopeValue(), ConfigValue(), peer)); }
};

static void GrantControls() {
    { Scope s = ScopeValue(); Check(ValidScope(s), "canonical finite memory budget accepted"); s.budget = BindBudget(536870912, 123, 456, true, true); Check(ValidScope(s) && s.budget == BindBudget(536870912, 0, 0, true, true), "unlimited modes have one canonical representation"); s.budget[25] = 1; Check(!ValidScope(s), "unknown budget flag bits rejected"); }
    { Scope s = ScopeValue(); s.budget[28] = 2; Check(!ValidScope(s), "unknown budget encoding rejected"); s.budget = BindBudget(536870912, 536870913, 0, false, false); Check(!ValidScope(s), "finite high cannot exceed bound maximum"); s.budget = BindBudget(0, 0, 0, true, true); Check(!ValidScope(s), "unbounded or zero cell maximum is not a valid lease budget"); }
    { Pair p; Monitor m; Check(m.Adopt(p.Take(), ScopeValue(), ConfigValue(), p.peer), "valid authenticated-shape grant accepted"); }
    { Pair p; Monitor m; auto c = p.peer; ++c.uid; Check(!m.Adopt(p.Take(), ScopeValue(), ConfigValue(), c), "different peer UID rejected"); }
    { Pair p; Monitor m; auto c = p.peer; ++c.pid; Check(!m.Adopt(p.Take(), ScopeValue(), ConfigValue(), c), "different peer PID rejected"); }
    { Pair p; Monitor m; auto c = p.peer; ++c.gid; Check(!m.Adopt(p.Take(), ScopeValue(), ConfigValue(), c), "different peer GID rejected"); }
    { Pair p; Monitor m; Need(fcntl(p.guest, F_SETFD, 0) == 0); Check(!m.Adopt(p.Take(), ScopeValue(), ConfigValue(), p.peer), "non-CLOEXEC grant rejected"); }
    { Pair p; Monitor m; Need(fcntl(p.guest, F_SETFL, 0) == 0); Check(!m.Adopt(p.Take(), ScopeValue(), ConfigValue(), p.peer), "blocking grant rejected"); }
    { Pair p; Monitor m; Scope s = ScopeValue(); s.generation.fill(0); Check(!m.Adopt(p.Take(), s, ConfigValue(), p.peer), "missing generation rejected"); }
    { Pair p; Monitor m; Scope s = ScopeValue(); s.budget.fill(0); Check(!m.Adopt(p.Take(), s, ConfigValue(), p.peer), "missing budget binding rejected"); }
    { Pair p; Monitor m; Config c = ConfigValue(); c.window_us = 499999; Check(!m.Adopt(p.Take(), ScopeValue(), c, p.peer), "window below existing monitor limit rejected"); }
    { Pair p; Monitor m; Config c = ConfigValue(); c.window_us = 10000001; Check(!m.Adopt(p.Take(), ScopeValue(), c, p.peer), "window above existing monitor limit rejected"); }
    { Pair p; Monitor m; Config c = ConfigValue(); c.stall_us = 0; Check(!m.Adopt(p.Take(), ScopeValue(), c, p.peer), "zero threshold rejected"); }
    { Pair p; Monitor m; Config c = ConfigValue(); c.stall_us = c.window_us + 1; Check(!m.Adopt(p.Take(), ScopeValue(), c, p.peer), "threshold above window rejected"); }
    { Pair p; Monitor m; Config c = ConfigValue(); c.level = static_cast<Level>(0); Check(!m.Adopt(p.Take(), ScopeValue(), c, p.peer), "unregistered level rejected"); }
    { int f[2]; Need(socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, f) == 0); Monitor m; Credentials c; Need(ReadCredentials(f[1], &c)); Check(!m.Adopt(f[1], ScopeValue(), ConfigValue(), c), "stream descriptor cannot replace packet contract"); close(f[0]); }
    { Pair p; Monitor m; int fd = p.Take(); p.Close(); Check(!m.Adopt(fd, ScopeValue(), ConfigValue(), p.peer), "already-revoked grant rejected"); }
    { Pair p, q; Monitor m; p.Bind(m); Check(!m.Adopt(q.Take(), ScopeValue(), ConfigValue(), q.peer) && !m.active(), "one consumer object cannot be rebound to another lease"); }
}

static void FrameControls() {
    { Pair p; Monitor m; p.Bind(m); timespec time{}; Need(clock_gettime(CLOCK_MONOTONIC, &time) == 0); uint64_t now = uint64_t(time.tv_sec) * 1000000000 + uint64_t(time.tv_nsec); p.Put(E(1, now)); Check(m.Consume(ScopeValue()).status == Status::Event, "normal consumer uses the real shared monotonic clock path"); }
    { Pair p; Monitor m; p.Bind(m); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).status == Status::Empty, "quiet channel is not a pressure notification"); p.Put(E()); auto r = m.ConsumeAtForTest(ScopeValue(), 1500000000); Check(r.status == Status::Event && r.last_sequence == 1, "fresh exact-scope event accepted"); Check(m.ConsumeAtForTest(ScopeValue(), 1500000001).status == Status::Empty, "consumed event cannot be replayed by another poll"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E()); Check(m.ConsumeAtForTest(ScopeValue(), 1999999999).status == Status::Event, "one nanosecond before existing-window expiry remains fresh"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E()); auto r = m.ConsumeAtForTest(ScopeValue(), 2000000000); Check(r.status == Status::Stale && r.stale_records == 1, "exact existing-window expiry cannot authorize a decision"); p.Put(E(2, 2100000000)); Check(m.ConsumeAtForTest(ScopeValue(), 2100000001).status == Status::Event, "new genuine event can follow a stale dropped event"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E()); p.Put(E(2, 1900000000)); auto r = m.ConsumeAtForTest(ScopeValue(), 2000000000); Check(r.status == Status::Event && r.stale_records == 1 && r.last_sequence == 2, "bounded drain keeps latest fresh event without reviving stale one"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E(1, 1500000001)); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::Timestamp, "future host timestamp revokes lease"); }
    { Pair p; Monitor m; p.Bind(m); m.ConsumeAtForTest(ScopeValue(), 1500000000); Check(m.ConsumeAtForTest(ScopeValue(), 1499999999).error == Error::ClockInvalid, "local monotonic rollback revokes lease"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E()); p.Put(E()); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::Sequence, "duplicate sequence invalidates entire decision batch"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E(2)); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::Sequence, "missing notification sequence is not silently accepted"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E(1, 1200000000)); p.Put(E(2, 1100000000)); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::Timestamp, "host event timestamp rollback rejected"); }
    const std::array<std::pair<const char*, std::function<void(Event&)>>, 7> changes = {{
        {"other cell generation rejected", [](Event& e) { ++e.scope.generation[0]; }},
        {"different cgroup device rejected", [](Event& e) { ++e.scope.cgroup_device; }},
        {"different cgroup inode rejected", [](Event& e) { ++e.scope.cgroup_inode; }},
        {"different budget binding rejected", [](Event& e) { ++e.scope.budget[0]; }},
        {"different pressure level rejected", [](Event& e) { e.config.level = Level::Medium; }},
        {"different existing window rejected", [](Event& e) { e.config.window_us += 1; }},
        {"different threshold rejected", [](Event& e) { e.config.stall_us += 1; }},
    }};
    for (const auto& item : changes) {
        Pair p; Monitor m; p.Bind(m); Event event = E(); item.second(event); p.Put(event);
        Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).status == Status::Revoked, item.first);
    }
    { Pair p; Monitor m; p.Bind(m); p.Put(E()); auto s = ScopeValue(); ++s.budget[0]; Check(m.ConsumeAtForTest(s, 1500000000).error == Error::ScopeChanged, "current Reader scope change rejects queued old event"); }
    { Pair p; Monitor m; p.Bind(m); Wire w = Encode(E()); w[0] ^= 1; Need(p.Send(w)); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::RecordEncoding, "invalid protocol magic rejected"); }
    { Pair p; Monitor m; p.Bind(m); Wire w = Encode(E()); w[8] = 2; Need(p.Send(w)); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::RecordEncoding, "unknown protocol version rejected"); }
    { Pair p; Monitor m; p.Bind(m); Wire w = Encode(E()); Need(send(p.host, w.data(), w.size() - 1, MSG_NOSIGNAL) == ssize_t(w.size() - 1)); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::RecordSize, "short packet rejected"); }
    { Pair p; Monitor m; p.Bind(m); std::array<unsigned char, kWireSize + 1> w{}; Need(send(p.host, w.data(), w.size(), MSG_NOSIGNAL) == ssize_t(w.size())); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::RecordSize, "oversized packet is detected with MSG_TRUNC"); }
    { Pair p(false); Monitor m; p.Bind(m); for (uint64_t i = 1; i <= kMaxDrainRecords + 1; ++i) p.Put(E(i)); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::DrainLimit, "unexpected oversized backlog cannot monopolize LMKD loop"); }
}

static void AncillaryControls() {
    Pair p; Monitor m; p.Bind(m);
    int f[2]; Need(pipe2(f, O_CLOEXEC | O_NONBLOCK) == 0);
    Wire w = Encode(E()); iovec io{w.data(), w.size()};
    alignas(cmsghdr) unsigned char data[CMSG_SPACE(sizeof(int))]{};
    msghdr msg{}; msg.msg_iov = &io; msg.msg_iovlen = 1; msg.msg_control = data; msg.msg_controllen = sizeof(data);
    cmsghdr* c = CMSG_FIRSTHDR(&msg); c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(sizeof(int));
    std::memcpy(CMSG_DATA(c), &f[1], sizeof(int));
    Need(sendmsg(p.host, &msg, MSG_NOSIGNAL) == ssize_t(w.size())); close(f[1]);
    Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).error == Error::AncillaryData, "unexpected transferred authority rejected");
    char byte; Check(read(f[0], &byte, 1) == 0, "unexpected transferred descriptor closed without a leak"); close(f[0]);
}

static void RevocationAndCapabilityControls() {
    { int f[2]; Need(pipe2(f, O_NONBLOCK | O_CLOEXEC) == 0); std::string name = "/proc/self/fd/" + std::to_string(f[0]); int reopened = open(name.c_str(), O_WRONLY | O_NONBLOCK | O_CLOEXEC); Need(reopened >= 0); char c = 'x'; Need(write(reopened, &c, 1) == 1); Check(read(f[0], &c, 1) == 1, "negative control: pipe read end can be reopened to forge input under creator credentials"); close(reopened); close(f[0]); close(f[1]); }
    { int owner = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC); Need(owner >= 0); int retained = fcntl(owner, F_DUPFD_CLOEXEC, 0); Need(retained >= 0); close(owner); uint64_t n = 1; Need(write(retained, &n, sizeof(n)) == sizeof(n)); Check(read(retained, &n, sizeof(n)) == sizeof(n) && n == 1, "negative control: closing one open-file-description copy does not revoke another"); close(retained); }
    { Pair p; Monitor m; p.Bind(m); errno = 0; Check(send(m.fd(), "forged", 6, MSG_NOSIGNAL) == -1 && errno == EPIPE, "shutdown write half prevents recipient packet injection"); int alias = fcntl(m.fd(), F_DUPFD_CLOEXEC, 0); Need(alias >= 0); errno = 0; Check(send(alias, "forged", 6, MSG_NOSIGNAL) == -1 && errno == EPIPE, "duplicating recipient endpoint cannot undo shutdown"); std::string name = "/proc/self/fd/" + std::to_string(alias); errno = 0; int reopened = open(name.c_str(), O_WRONLY | O_NONBLOCK | O_CLOEXEC); Check(reopened == -1 && errno == ENXIO, "socket endpoint cannot be reopened through procfd as a writer"); sockaddr address{}; address.sa_family = AF_UNSPEC; errno = 0; Check(connect(alias, &address, sizeof(address.sa_family)) == -1 && errno == EINVAL, "recipient cannot disconnect packet lease to reconnect a fake peer"); close(alias); }
    { Pair p; p.Put(E()); p.Close(); Wire w{}; ssize_t n = recv(p.guest, w.data(), w.size(), MSG_DONTWAIT); Check(n == ssize_t(w.size()), "negative control: read-only old consumer would accept queued record after sender death"); }
    { Pair p; Monitor m; p.Bind(m); p.Put(E()); p.Close(); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).status == Status::Revoked, "HUP takes precedence over queued authentic-looking event"); }
    { Pair p; Monitor m; p.Bind(m); int alias = fcntl(m.fd(), F_DUPFD_CLOEXEC, 0); Need(alias >= 0); p.Close(); pollfd d{alias, POLLIN | POLLRDHUP, 0}; Need(poll(&d, 1, 0) >= 0); Check(d.revents & (POLLHUP | POLLRDHUP), "host close revokes every retained recipient duplicate"); close(alias); }
    { Pair p; Monitor m; p.Bind(m); int size = 0; socklen_t n = sizeof(size); Need(getsockopt(p.host, SOL_SOCKET, SO_SNDBUF, &size, &n) == 0); Check(size > 0 && size <= 8192, "host socket notification buffer has a measured finite bound"); uint64_t seq = 0; while (++seq < 10000 && p.Send(Encode(E(seq)))) {} Check(seq < 10000 && (errno == EAGAIN || errno == EWOULDBLOCK), "owned unread queue eventually reaches EAGAIN without blocking"); p.Close(); Check(m.ConsumeAtForTest(ScopeValue(), 1500000000).status == Status::Revoked, "proposed overflow policy revokes instead of silently dropping events"); }
}

static void PeerPidfdControls() {
    char directory[] = "/tmp/p4-relay-peer-XXXXXX"; Need(mkdtemp(directory) != nullptr);
    std::string name = std::string(directory) + "/socket";
    int listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0); Need(listener >= 0);
    sockaddr_un address{}; address.sun_family = AF_UNIX; Need(name.size() < sizeof(address.sun_path)); std::memcpy(address.sun_path, name.c_str(), name.size() + 1);
    Need(bind(listener, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0 && listen(listener, 1) == 0);
    pid_t parent = getpid(), child = fork(); Need(child >= 0);
    if (child == 0) {
        prctl(PR_SET_PDEATHSIG, SIGKILL); if (getppid() != parent) _exit(91);
        close(listener); int client = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0); if (client < 0) _exit(92);
        timeval timeout{2, 0}; setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        if (connect(client, reinterpret_cast<sockaddr*>(&address), sizeof(address))) _exit(93);
        char command; if (recv(client, &command, 1, 0) != 1) _exit(94); close(client); _exit(0);
    }
    pollfd ready{listener, POLLIN, 0}; Need(poll(&ready, 1, 1000) == 1);
    int connection = accept4(listener, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK); Need(connection >= 0);
    Credentials credentials; Need(ReadCredentials(connection, &credentials));
    Check(credentials.pid == child && credentials.uid == getuid(), "accepted connection exposes exact owned peer credentials");
    int pidfd = -1; socklen_t size = sizeof(pidfd); Need(getsockopt(connection, SOL_SOCKET, 77, &pidfd, &size) == 0 && size == sizeof(pidfd));
    pollfd alive{pidfd, POLLIN, 0}; Check(poll(&alive, 1, 0) == 0 && (fcntl(pidfd, F_GETFD) & FD_CLOEXEC), "SO_PEERPIDFD returns live generation-pinned CLOEXEC handle");
    Need(send(connection, "x", 1, MSG_NOSIGNAL) == 1); Need(poll(&alive, 1, 1000) == 1);
    int status = 0; Need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    Check(alive.revents & POLLIN, "exact peer death becomes observable without numeric PID rescanning");
    int stale = -1; size = sizeof(stale); Need(getsockopt(connection, SOL_SOCKET, 77, &stale, &size) == 0);
    pollfd dead{stale, POLLIN, 0}; Check(poll(&dead, 1, 0) == 1 && (dead.revents & POLLIN), "SO_PEERPIDFD after reaping retains dead connection generation");
    close(stale); close(pidfd); close(connection); close(listener); unlink(name.c_str()); rmdir(directory);
}

// This independent test needs no addressable listener. It proves the exact
// peer generation retained by a child-created socketpair after SCM_RIGHTS.
// It does not substitute for the named endpoint's authentication test above.
static void OwnedPeerPidfdControls() {
    int transfer[2]; Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, transfer) == 0);
    pid_t parent = getpid(), child = fork(); Need(child >= 0);
    if (child == 0) {
        prctl(PR_SET_PDEATHSIG, SIGKILL); if (getppid() != parent) _exit(91);
        close(transfer[0]); int peer[2];
        if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, peer)) _exit(92);
        char byte = 'x'; iovec io{&byte, 1};
        alignas(cmsghdr) unsigned char control[CMSG_SPACE(sizeof(int))]{};
        msghdr msg{}; msg.msg_iov = &io; msg.msg_iovlen = 1; msg.msg_control = control; msg.msg_controllen = sizeof(control);
        cmsghdr* header = CMSG_FIRSTHDR(&msg); header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS; header->cmsg_len = CMSG_LEN(sizeof(int));
        std::memcpy(CMSG_DATA(header), &peer[1], sizeof(int));
        if (sendmsg(transfer[1], &msg, MSG_NOSIGNAL) != 1) _exit(93);
        close(peer[1]); close(transfer[1]);
        pollfd ready{peer[0], POLLIN, 0}; if (poll(&ready, 1, 2000) != 1 || recv(peer[0], &byte, 1, 0) != 1) _exit(94);
        close(peer[0]); _exit(0);
    }
    close(transfer[1]); pollfd ready{transfer[0], POLLIN, 0}; Need(poll(&ready, 1, 1000) == 1);
    char byte; iovec io{&byte, 1}; alignas(cmsghdr) unsigned char control[CMSG_SPACE(sizeof(int))]{};
    msghdr msg{}; msg.msg_iov = &io; msg.msg_iovlen = 1; msg.msg_control = control; msg.msg_controllen = sizeof(control);
    Need(recvmsg(transfer[0], &msg, MSG_CMSG_CLOEXEC) == 1);
    cmsghdr* header = CMSG_FIRSTHDR(&msg); Need(header && header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_RIGHTS && header->cmsg_len == CMSG_LEN(sizeof(int)));
    int connection; std::memcpy(&connection, CMSG_DATA(header), sizeof(int)); close(transfer[0]);
    Credentials credentials; Need(ReadCredentials(connection, &credentials));
    Check(credentials.pid == child && credentials.uid == getuid(), "SCM_RIGHTS retains exact child-created peer credentials");
    int pidfd = -1; socklen_t size = sizeof(pidfd); Need(getsockopt(connection, SOL_SOCKET, 77, &pidfd, &size) == 0 && size == sizeof(pidfd));
    pollfd alive{pidfd, POLLIN, 0}; Check(poll(&alive, 1, 0) == 0 && (fcntl(pidfd, F_GETFD) & FD_CLOEXEC), "SO_PEERPIDFD pins the live owned child generation");
    Need(send(connection, "x", 1, MSG_NOSIGNAL) == 1); Need(poll(&alive, 1, 1000) == 1);
    int status; Need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    Check(alive.revents & POLLIN, "owned child death signals the original peer pidfd");
    int stale = -1; size = sizeof(stale); Need(getsockopt(connection, SOL_SOCKET, 77, &stale, &size) == 0);
    pollfd dead{stale, POLLIN, 0}; Check(poll(&dead, 1, 0) == 1 && (dead.revents & POLLIN), "re-query after reaping retains the dead peer generation");
    close(stale); close(pidfd); close(connection);
}

int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IOLBF, 0);
    if (argc == 2 && std::string(argv[1]) == "--owned-peer-pidfd-only") {
        OwnedPeerPidfdControls();
    } else {
        Need(argc == 1 || (argc == 2 && std::string(argv[1]) == "--transport-only"));
        GrantControls(); FrameControls(); AncillaryControls(); RevocationAndCapabilityControls();
        if (argc == 1) PeerPidfdControls();
        else std::puts("SCOPE named-listener authentication not exercised");
    }
    std::printf("RESULT %u passed\n", passed);
    return 0;
}
