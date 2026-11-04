// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
#include "pressure_relay.h"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
using namespace droidloom::lmkd::relay;
static unsigned clock_calls;
static uint64_t completion;
static bool completion_fails;
extern "C" int __wrap_clock_gettime(clockid_t clock, timespec* out) {
    if (clock != CLOCK_MONOTONIC) std::abort();
    uint64_t value = ++clock_calls == 1 ? 1500000000 : completion;
    if (clock_calls > 1 && completion_fails) { errno = EIO; return -1; }
    out->tv_sec = static_cast<time_t>(value / 1000000000);
    out->tv_nsec = static_cast<long>(value % 1000000000);
    return 0;
}
static void Need(bool value) { if (!value) { std::perror("clock test setup"); std::exit(3); } }
static bool Check(uint64_t end, bool fail, Status expected, const char* label) {
    clock_calls = 0; completion = end; completion_fails = fail;
    Scope scope; scope.generation.fill(0x51); scope.cgroup_device = 30; scope.cgroup_inode = 987654;
    scope.budget = BindBudget(536870912, 402653184, 0, false, false);
    Config config{Level::Critical, 1000000, 700000};
    int pair[2]; Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, pair) == 0);
    Need(shutdown(pair[0], SHUT_RD) == 0 && shutdown(pair[1], SHUT_WR) == 0);
    Credentials peer; Need(ReadCredentials(pair[1], &peer)); Monitor monitor;
    Need(monitor.Adopt(pair[1], scope, config, peer));
    Wire wire = Encode({scope, config, 1, 1000000000});
    Need(send(pair[0], wire.data(), wire.size(), MSG_NOSIGNAL) == ssize_t(wire.size()));
    Result result = monitor.Consume(scope); close(pair[0]);
    bool ok = result.status == expected;
    std::printf("%s %s\n", ok ? "PASS" : "FAIL", label);
    return ok;
}
int main() {
    bool ok = true;
    ok &= Check(2000000000, false, Status::Stale, "entry-fresh event expires exactly at I/O completion");
    ok &= Check(2500000000, false, Status::Stale, "kernel-side delay cannot reuse entry-time freshness");
    ok &= Check(1999999999, false, Status::Event, "completion before exact expiry remains valid");
    ok &= Check(1499999999, false, Status::Revoked, "completion clock rollback revokes");
    ok &= Check(1500000001, true, Status::Revoked, "completion clock read failure revokes");
    std::printf("RESULT completion-clock %s\n", ok ? "PASS" : "FAIL");
    return ok ? 0 : 2;
}
