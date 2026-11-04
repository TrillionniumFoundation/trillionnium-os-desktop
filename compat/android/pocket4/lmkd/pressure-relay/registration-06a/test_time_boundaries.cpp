// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
#include "pressure_relay.h"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <poll.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
using namespace droidloom::lmkd::relay;

enum class Scenario { HealthDelay, ArrivalDuringCall, ActualFuture, Quiet };
static Scenario scenario;
static uint64_t now_ns;
static bool record_received, clock_after_record, delay_applied, injected;
static int sender;
static Wire arriving;
extern "C" int __real_poll(pollfd*, nfds_t, int);
extern "C" ssize_t __real_recvmsg(int, msghdr*, int);
extern "C" int __wrap_clock_gettime(clockid_t clock, timespec* out) {
    if (clock != CLOCK_MONOTONIC) std::abort();
    out->tv_sec = static_cast<time_t>(now_ns / 1000000000);
    out->tv_nsec = static_cast<long>(now_ns % 1000000000);
    if (record_received) clock_after_record = true;
    return 0;
}
extern "C" int __wrap_poll(pollfd* fds, nfds_t count, int timeout) {
    int rc = __real_poll(fds, count, timeout);
    // A real health poll completes after time has advanced past the original
    // event window. There is no assumption about a particular poll count.
    if (scenario == Scenario::HealthDelay && record_received && clock_after_record && !delay_applied) {
        now_ns = 2500000000;
        delay_applied = true;
    }
    return rc;
}
extern "C" ssize_t __wrap_recvmsg(int fd, msghdr* message, int flags) {
    if ((scenario == Scenario::ArrivalDuringCall || scenario == Scenario::ActualFuture) && !injected) {
        // The genuine packet is sent only after Consume has entered recvmsg.
        // Its observation is before the eventual receipt, but after entry.
        now_ns = 1700000000;
        if (send(sender, arriving.data(), arriving.size(), MSG_NOSIGNAL) != ssize_t(arriving.size())) std::abort();
        injected = true;
    }
    ssize_t rc = __real_recvmsg(fd, message, flags);
    if (rc == ssize_t(kWireSize)) record_received = true;
    return rc;
}
static void Need(bool value) { if (!value) { std::perror("time boundary setup"); std::exit(3); } }
static bool Run(Scenario which, Status expected, const char* name) {
    scenario = which; now_ns = 1500000000;
    record_received = clock_after_record = delay_applied = injected = false;
    Scope scope; scope.generation.fill(0x61); scope.cgroup_device = 30; scope.cgroup_inode = 987655;
    scope.budget = BindBudget(536870912, 402653184, 0, false, false);
    Config config{Level::Critical, 1000000, 700000};
    int pair[2]; Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, pair) == 0);
    Need(shutdown(pair[0], SHUT_RD) == 0 && shutdown(pair[1], SHUT_WR) == 0);
    sender = pair[0]; Credentials credentials; Need(ReadCredentials(pair[1], &credentials));
    Monitor monitor; Need(monitor.Adopt(pair[1], scope, config, credentials));
    arriving = Encode({scope, config, 1, which == Scenario::ActualFuture ? 1800000000U : 1600000000U});
    if (which == Scenario::HealthDelay) {
        Wire wire = Encode({scope, config, 1, 1000000000});
        Need(send(sender, wire.data(), wire.size(), MSG_NOSIGNAL) == ssize_t(wire.size()));
    }
    Result result = monitor.Consume(scope);
    close(sender);
    bool ok = result.status == expected;
    if (which == Scenario::ActualFuture) ok = ok && result.error == Error::Timestamp;
    std::printf("%s %s\n", ok ? "PASS" : "FAIL", name);
    return ok;
}
int main() {
    bool ok = true;
    ok &= Run(Scenario::HealthDelay, Status::Stale, "health I/O after data cannot return an expired event as fresh");
    ok &= Run(Scenario::ArrivalDuringCall, Status::Event, "genuine in-call arrival is valid against receipt time");
    ok &= Run(Scenario::ActualFuture, Status::Revoked, "timestamp beyond actual receipt is still rejected");
    ok &= Run(Scenario::Quiet, Status::Empty, "quiet real channel never synthesizes a notification");
    std::printf("RESULT time-boundaries %s\n", ok ? "PASS" : "FAIL");
    return ok ? 0 : 2;
}
