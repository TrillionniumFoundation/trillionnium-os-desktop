// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
#pragma once
#include "enrollment.h"
#include <mutex>
#include <utility>

namespace droidloom::lmkd::relay {

struct AccountingScope {
    uint64_t device = 0;
    uint64_t inode = 0;
    Bytes32 budget{};
};
struct ScopeProbe {
    void* context = nullptr;
    // Must read the real fixed-root Reader. Serialized by this session's lock;
    // the probe Reader is separate from the main handler's pending-evidence Reader.
    bool (*read)(void*, AccountingScope*) = nullptr;
};
enum class Ready { Polling, Event, Empty, Stale, Revoked };
enum class Dispatch { Denied, Failed, Sent };

// One LMKD process generation, one enrollment, at most two monitors.
// The event-loop owns receive sequencing; watchdog effect checks use a try-lock
// and independently re-read the same scope, never Monitor::Consume or a mutable
// main-thread Reader. Invalid/contended authority never permits a signal.
class Session {
public:
    Session() = default;
    Session(const Session&) = delete;
    Session& operator=(const Session&) = delete;
    bool Start(int connected_fd, const Credentials& server,
               const EnrollmentRequest& request, ScopeProbe probe);
    int fd(Level level) const;
    int control_fd() const;
    Ready Handle(Level level, uint32_t events);
    void Stop();
    bool active() const;
    template <class F> Dispatch Perform(F&& operation) {
        std::unique_lock<std::mutex> lock(mutex_, std::try_to_lock);
        if (!lock.owns_lock() || !FreshDecision() || !CheckScopeAndTransport() ||
            !FreshDecision()) return Dispatch::Denied;
        return std::forward<F>(operation)() ? Dispatch::Sent : Dispatch::Failed;
    }

private:
    bool CheckScopeAndTransport();
    bool CheckClock(uint64_t* now);
    bool FreshDecision();
    int Index(Level level) const;
    void StopLocked();
    mutable std::mutex mutex_;
    bool attempted_ = false;
    bool active_ = false;
    EnrollmentClient client_;
    std::array<Monitor, kMaxMonitors> monitors_;
    EnrollmentGrant grant_{};
    Scope scope_{};
    ScopeProbe probe_{};
    uint64_t last_clock_ns_ = 0;
    uint64_t decision_observed_ns_ = 0;
    uint64_t decision_window_ns_ = 0;
};

// Exact lifecycle endpoint only. This function retains each /dev/socket
// directory component with O_NOFOLLOW, validates ownership/modes and the
// selected socket inode before/after connect, and requires root server UID/GID.
// Host PID may be zero in a child PID namespace; Exchange pins SO_PEERPIDFD.
int ConnectLifecycleEndpoint(Credentials* expected_server);

}  // namespace droidloom::lmkd::relay
