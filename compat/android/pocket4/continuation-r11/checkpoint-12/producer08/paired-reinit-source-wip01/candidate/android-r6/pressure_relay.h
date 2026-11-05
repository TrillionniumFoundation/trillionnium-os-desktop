// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <sys/types.h>

// Native LMKD-side protocol candidate only. No listener, process discovery,
// pressure registration, memory decision, signal, cgroup write or deployment.
// An authenticated host lease grant must supply the expected scope and socket.
namespace droidloom::lmkd::relay {

constexpr size_t kWireSize = 128;
constexpr size_t kMaxDrainRecords = 64;
using Bytes32 = std::array<uint8_t, 32>;
using Wire = std::array<uint8_t, kWireSize>;

enum class Level : uint32_t { Medium = 1, Critical = 2 };

struct Scope {
    Bytes32 generation{};
    uint64_t cgroup_device = 0;
    uint64_t cgroup_inode = 0;
    Bytes32 budget{};
    bool operator==(const Scope& other) const;
};

struct Config {
    Level level = Level::Medium;
    uint64_t window_us = 0;
    uint64_t stall_us = 0;
    bool operator==(const Config& other) const;
};

struct Credentials {
    pid_t pid = -1;
    uid_t uid = static_cast<uid_t>(-1);
    gid_t gid = static_cast<gid_t>(-1);
    bool operator==(const Credentials& other) const;
};

struct Event {
    Scope scope;
    Config config;
    uint64_t sequence = 0;
    uint64_t observed_monotonic_ns = 0;
};

bool ValidScope(const Scope& scope);
bool ValidConfig(const Config& config);
// Canonical lossless binding to the Reader's existing budget fields. This is
// not a hash and adds no cryptographic library dependency. Read/Validate must
// still establish a coherent snapshot before these values are used.
Bytes32 BindBudget(uint64_t maximum, uint64_t high, uint64_t swap_maximum,
                   bool high_unlimited, bool swap_unlimited);
Wire Encode(const Event& event);
bool Decode(const Wire& wire, Event* event);
bool ReadCredentials(int fd, Credentials* credentials);

enum class Status { Empty, Event, Stale, Revoked };
enum class Error {
    None, InvalidGrant, ScopeChanged, ClockInvalid, Transport, PeerChanged,
    AncillaryData, RecordSize, RecordEncoding, EventScope, EventConfig,
    Sequence, Timestamp, DrainLimit,
};

struct Result {
    Status status = Status::Empty;
    Error error = Error::None;
    uint64_t last_sequence = 0;
    uint64_t observed_monotonic_ns = 0;
    size_t stale_records = 0;
};

class Monitor {
public:
    // Thread-confined to LMKD's event loop. A separately reviewed atomic lease
    // gate is required before any watchdog-thread integration.
    Monitor() = default;
    Monitor(const Monitor&) = delete;
    Monitor& operator=(const Monitor&) = delete;
    ~Monitor();

    // Takes ownership even on rejection. Requires a connected AF_UNIX
    // SOCK_SEQPACKET descriptor received with MSG_CMSG_CLOEXEC. The grant
    // provider must have permanently shut down the recipient's write half.
    // expected_peer comes from the authenticated host grant, never a frame.
    bool Adopt(int fd, const Scope& scope, const Config& config,
               const Credentials& expected_peer);
    int fd() const { return fd_; }
    bool active() const { return fd_ >= 0; }
    void Revoke();

    // verified_current_scope must come from the existing fixed-root Reader
    // and the live lease owner. observed time uses shared CLOCK_MONOTONIC;
    // the host must verify matching time namespaces before granting a lease.
    // No allocation, logging, blocking wait or process operation occurs here.
    Result Consume(const Scope& verified_current_scope);

    // Deterministic tests exercise the identical parser and transport. This
    // clock injection entry point is absent from a normal compilation.
#ifdef DROIDLOOM_RELAY_TEST
    Result ConsumeAtForTest(const Scope& verified_current_scope, uint64_t now_ns);
#endif

private:
    Result ConsumeAt(const Scope& scope, uint64_t now_ns, bool live_clock);
    Result Fail(Error error);
    bool TransportHealthy(short* readiness);
    int fd_ = -1;
    Scope scope_{};
    Config config_{};
    Credentials peer_{};
    uint64_t last_sequence_ = 0;
    uint64_t last_event_ns_ = 0;
    uint64_t last_local_ns_ = 0;
    bool adopted_once_ = false;
};

}  // namespace droidloom::lmkd::relay
