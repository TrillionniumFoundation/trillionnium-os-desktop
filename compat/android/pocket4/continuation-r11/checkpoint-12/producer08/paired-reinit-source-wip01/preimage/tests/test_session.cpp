// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
// Owned local packet/session controls. The accounting probe and selected clock
// boundaries are test inputs, not Android cgroup or real PSI qualifications.
#include "relay_session.h"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <poll.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <thread>
#include <time.h>
#include <unistd.h>

using namespace droidloom::lmkd::relay;
static unsigned passed = 0;
static std::atomic<uint64_t> test_clock{0};
extern "C" int __real_clock_gettime(clockid_t, timespec*);
extern "C" int __wrap_clock_gettime(clockid_t id, timespec* result) {
    const uint64_t value = test_clock.load();
    if (id == CLOCK_MONOTONIC && value) {
        result->tv_sec = static_cast<time_t>(value / 1000000000);
        result->tv_nsec = static_cast<long>(value % 1000000000);
        return 0;
    }
    return __real_clock_gettime(id, result);
}
static uint64_t Now() {
    timespec now{};
    if (clock_gettime(CLOCK_MONOTONIC, &now)) std::exit(3);
    return static_cast<uint64_t>(now.tv_sec) * 1000000000 + static_cast<uint64_t>(now.tv_nsec);
}
static void Need(bool value, const char* label) {
    if (!value) { std::fprintf(stderr, "SETUP %s errno=%d\n", label, errno); std::exit(3); }
}
static void Check(bool value, const char* label) {
    if (!value) { std::fprintf(stderr, "FAIL %s errno=%d\n", label, errno); std::exit(2); }
    ++passed;
    std::printf("PASS %s\n", label);
}
static size_t Fds() {
    DIR* directory = opendir("/proc/self/fd");
    Need(directory != nullptr, "fd inventory");
    size_t result = 0;
    while (dirent* entry = readdir(directory)) if (entry->d_name[0] != '.') ++result;
    closedir(directory);
    return result;
}
static EnrollmentRequest Request() {
    EnrollmentRequest request{};
    request.nonce.fill(0x31);
    request.cgroup_device = 13;
    request.cgroup_inode = 17;
    request.budget = BindBudget(64 * 1024 * 1024, 24 * 1024 * 1024, 0, false, false);
    request.count = 2;
    request.configs[0] = {Level::Medium, 1000000, 70000};
    request.configs[1] = {Level::Critical, 1000000, 70000};
    return request;
}
struct Probe {
    AccountingScope scope{13, 17, Request().budget};
    bool valid = true;
    unsigned reads = 0, advance_at = 0;
    uint64_t advance_to = 0;
    std::atomic<bool> block{false}, entered{false}, release{false};
    static bool Read(void* context, AccountingScope* result) {
        auto* self = static_cast<Probe*>(context);
        ++self->reads;
        if (self->advance_at == self->reads) test_clock = self->advance_to;
        if (self->block.exchange(false)) {
            self->entered = true;
            for (unsigned i = 0; i < 1000 && !self->release; ++i)
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            Need(self->release, "bounded probe release");
        }
        *result = self->scope;
        return self->valid;
    }
};
struct Fixture {
    int control[2]{-1, -1};
    int sender[2]{-1, -1};
    int recipient[2]{-1, -1};
    Probe probe;
    Session session;
    EnrollmentRequest request = Request();
    EnrollmentGrant grant{request, {}};
    Credentials peer{};
    Fixture() {
        test_clock = 0;
        Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, control) == 0, "control pair");
        Need(ReadCredentials(control[1], &peer), "actual server credential");
        grant.generation.fill(0x51);
        for (size_t i = 0; i < 2; ++i) {
            int pair[2];
            Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, pair) == 0, "recipient pair");
            sender[i] = pair[0]; recipient[i] = pair[1];
            Need(shutdown(sender[i], SHUT_RD) == 0 && shutdown(recipient[i], SHUT_WR) == 0, "one way endpoint");
        }
        std::thread server([&]() {
            pollfd pending{control[0], POLLIN, 0};
            Need(poll(&pending, 1, 1000) == 1, "bounded request wait");
            RequestWire bytes{};
            Need(recv(control[0], bytes.data(), bytes.size(), MSG_DONTWAIT | MSG_TRUNC) == ssize_t(bytes.size()), "request packet");
            EnrollmentRequest decoded{};
            Need(DecodeRequest(bytes, &decoded) && decoded == request, "exact request");
            GrantWire wire = EncodeGrant(grant);
            iovec payload{wire.data(), wire.size()};
            alignas(cmsghdr) unsigned char ancillary[CMSG_SPACE(2 * sizeof(int))]{};
            msghdr message{};
            message.msg_iov = &payload; message.msg_iovlen = 1;
            message.msg_control = ancillary; message.msg_controllen = sizeof(ancillary);
            cmsghdr* c = CMSG_FIRSTHDR(&message);
            c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS;
            c->cmsg_len = CMSG_LEN(sizeof(recipient));
            std::memcpy(CMSG_DATA(c), recipient, sizeof(recipient));
            Need(sendmsg(control[0], &message, MSG_NOSIGNAL) == ssize_t(wire.size()), "exact grant with rights");
        });
        const int owned = control[1]; control[1] = -1;
        const bool started = session.Start(owned, peer, request, {&probe, Probe::Read});
        server.join();
        for (int& fd : recipient) { close(fd); fd = -1; }
        Need(started, "session enrolled over actual SCM_RIGHTS");
    }
    ~Fixture() {
        session.Stop();
        for (int fd : control) if (fd >= 0) close(fd);
        for (int fd : sender) if (fd >= 0) close(fd);
        for (int fd : recipient) if (fd >= 0) close(fd);
        test_clock = 0;
    }
    void Packet(size_t index, uint64_t sequence, uint64_t observed, bool wrong_scope = false) {
        Scope scope{grant.generation, request.cgroup_device, request.cgroup_inode, request.budget};
        if (wrong_scope) scope.generation[0] ^= 1;
        Event event{scope, request.configs[index], sequence, observed};
        Wire wire = Encode(event);
        Need(send(sender[index], wire.data(), wire.size(), MSG_DONTWAIT | MSG_NOSIGNAL) == ssize_t(wire.size()), "owned notification packet");
    }
    uint64_t Fresh() {
        const uint64_t observed = Now();
        Packet(1, 1, observed);
        Need(session.Handle(Level::Critical, EPOLLIN) == Ready::Event, "fresh event accepted");
        return observed;
    }
    void FreezeClock() { test_clock = Now() + 1000000; }
};

int main() {
    const size_t before = Fds();
    {
        Fixture f;
        unsigned effects = 0;
        Check(f.session.active() && f.session.fd(Level::Critical) >= 0, "grant creates active packet monitoring");
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Denied && !effects,
              "healthy lease without real notification cannot authorize effect");
        Check(f.session.Handle(Level::Critical, 0) == Ready::Stale, "startup polling cannot fabricate pressure");
        f.Fresh();
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Sent && effects == 1,
              "fresh packet and current scope allow guarded operation");
        Check(f.session.Perform([]() { return false; }) == Dispatch::Failed && f.session.active(),
              "effect failure is distinct from invalid authority");
        Check(f.session.Handle(Level::Critical, 0) == Ready::Polling, "existing fresh window permits original periodic polling");
    }
    {
        Fixture f;
        f.FreezeClock();
        const uint64_t observed = f.Fresh();
        unsigned effects = 0;
        test_clock = observed + 1000000000 - 1;
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Sent, "effect allowed one nanosecond before original window boundary");
        test_clock = observed + 1000000000;
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Denied && effects == 1,
              "effect rejected exactly at original window boundary");
        Check(f.session.active() && f.session.Handle(Level::Critical, 0) == Ready::Stale,
              "expired pressure retires evidence without inventing transport failure");
        f.Packet(1, 2, test_clock.load());
        Check(f.session.Handle(Level::Critical, EPOLLIN) == Ready::Event,
              "later contiguous authentic observation starts a new window");
    }
    {
        Fixture f;
        f.FreezeClock();
        const uint64_t observed = f.Fresh();
        f.probe.advance_at = f.probe.reads + 1;
        f.probe.advance_to = observed + 1000000000;
        unsigned effects = 0;
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Denied && effects == 0,
              "scope I/O cannot extend pressure freshness at final effect boundary");
    }
    {
        Fixture f;
        f.FreezeClock();
        const uint64_t observed = Now();
        f.Packet(1, 1, observed);
        f.probe.advance_at = f.probe.reads + 2;
        f.probe.advance_to = observed + 1000000000;
        Check(f.session.Handle(Level::Critical, EPOLLIN) == Ready::Stale,
              "post-receive scope I/O cannot promote an expired event");
    }
    for (unsigned change = 0; change < 4; ++change) {
        Fixture f;
        f.Fresh();
        if (change == 0) ++f.probe.scope.device;
        if (change == 1) ++f.probe.scope.inode;
        if (change == 2) f.probe.scope.budget = BindBudget(64 * 1024 * 1024, 23 * 1024 * 1024, 0, false, false);
        if (change == 3) f.probe.valid = false;
        unsigned effects = 0;
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Denied && !effects && !f.session.active(),
              "scope identity budget drift or accounting failure revokes before effect");
        f.probe.scope = {13, 17, f.request.budget}; f.probe.valid = true;
        Check(f.session.Handle(Level::Critical, 0) == Ready::Revoked,
              "restored values cannot revive revoked generation");
    }
    {
        Fixture f;
        f.Fresh();
        close(f.sender[0]); f.sender[0] = -1;
        f.Packet(1, 2, Now());
        Check(f.session.Handle(Level::Critical, EPOLLIN) == Ready::Revoked,
              "other-monitor HUP rejects fresh packet from same epoll batch");
        unsigned effects = 0;
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Denied && !effects,
              "notification HUP cannot retain watchdog authority");
    }
    {
        Fixture f;
        f.Fresh();
        char extra = 'x';
        Need(send(f.control[0], &extra, 1, MSG_NOSIGNAL) == 1, "unexpected control packet");
        f.Packet(1, 2, Now());
        Check(f.session.Handle(Level::Critical, EPOLLIN) == Ready::Revoked,
              "unexpected control message preempts queued pressure packet");
    }
    {
        Fixture f;
        f.Fresh();
        close(f.control[0]); f.control[0] = -1;
        Check(f.session.Handle(Level::Critical, 0) == Ready::Revoked,
              "control HUP cancels original periodic polling");
    }
    {
        Fixture f;
        f.FreezeClock();
        f.Packet(1, 1, Now() - 1000000000);
        Check(f.session.Handle(Level::Critical, EPOLLIN) == Ready::Stale && f.session.active(),
              "stale authentic packet is drained without pressure promotion");
        unsigned effects = 0;
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Denied && !effects,
              "stale-only stream grants no effects");
    }
    {
        Fixture f;
        f.FreezeClock();
        f.Packet(1, 1, Now() + 1);
        Check(f.session.Handle(Level::Critical, EPOLLIN) == Ready::Revoked,
              "future event timestamp revokes generation");
    }
    {
        Fixture f;
        f.Packet(1, 1, Now(), true);
        Check(f.session.Handle(Level::Critical, EPOLLIN) == Ready::Revoked,
              "old or foreign generation packet cannot rebind active lease");
    }
    {
        Fixture f;
        f.FreezeClock();
        const uint64_t observed = f.Fresh();
        test_clock = observed - 1;
        Check(f.session.Perform([]() { return true; }) == Dispatch::Denied && !f.session.active(),
              "monotonic clock rollback revokes effect authority");
    }
    {
        Fixture f;
        f.FreezeClock();
        f.Fresh();
        f.probe.block = true;
        Ready result = Ready::Revoked;
        std::thread event_loop([&]() { result = f.session.Handle(Level::Critical, 0); });
        for (unsigned i = 0; i < 1000 && !f.probe.entered; ++i)
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        Need(f.probe.entered, "event loop holds lease gate");
        unsigned effects = 0;
        Check(f.session.Perform([&]() { ++effects; return true; }) == Dispatch::Denied && !effects,
              "contended watchdog uses try-lock and cannot act on partial validation");
        f.probe.release = true;
        event_loop.join();
        Check(result == Ready::Polling, "event-loop validation resumes with same bounded evidence");
    }
    {
        Fixture f;
        f.Fresh();
        Check(!f.session.Start(-1, f.peer, f.request, {&f.probe, Probe::Read}) && !f.session.active(),
              "same process cannot enroll a replacement generation");
        Check(f.session.fd(Level::Critical) < 0 && f.session.control_fd() < 0,
              "re-enrollment rejection closes previously claimed recipients");
    }
    Check(Fds() == before, "all session paths close every owned control pidfd and recipient");
    std::printf("RESULT %u assertions passed; local packet/session controls, no Android or real PSI\n", passed);
    return 0;
}
