// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
#pragma once

#include "pressure_relay.h"
#include <array>
#include <cstddef>
#include <cstdint>

namespace droidloom::lmkd::relay {

constexpr size_t kRequestSize = 144;
constexpr size_t kGrantSize = 176;
constexpr size_t kMaxMonitors = 2;
using RequestWire = std::array<uint8_t, kRequestSize>;
using GrantWire = std::array<uint8_t, kGrantSize>;

struct EnrollmentRequest {
    Bytes32 nonce{};
    uint64_t cgroup_device = 0;
    uint64_t cgroup_inode = 0;
    Bytes32 budget{};
    uint32_t count = 0;
    std::array<Config, kMaxMonitors> configs{};
    bool operator==(const EnrollmentRequest& other) const;
};

struct EnrollmentGrant {
    EnrollmentRequest request;
    Bytes32 generation{};
};

bool ValidRequest(const EnrollmentRequest& request);
bool FreshRequestNonce(Bytes32* nonce);
RequestWire EncodeRequest(const EnrollmentRequest& request);
bool DecodeRequest(const RequestWire& wire, EnrollmentRequest* request);
GrantWire EncodeGrant(const EnrollmentGrant& grant);
bool DecodeGrant(const GrantWire& wire, EnrollmentGrant* grant);

// One grant has one owner. Destruction closes every unclaimed recipient.
// This object only owns packet recipients, never a real PSI/cgroup/namespace FD.
class GrantRecipients {
public:
    GrantRecipients() = default;
    GrantRecipients(const GrantRecipients&) = delete;
    GrantRecipients& operator=(const GrantRecipients&) = delete;
    ~GrantRecipients();
    const EnrollmentGrant& grant() const { return grant_; }
    bool complete() const { return complete_; }
    int Take(size_t index);
    void Reset();

private:
    friend class EnrollmentClient;
    std::array<int, kMaxMonitors> fds_{{-1, -1}};
    EnrollmentGrant grant_{};
    bool complete_ = false;
};

// Startup-only, allocation-free bounded request/grant transport. It is not an
// endpoint discovery mechanism and does not authorize a kill. The connected
// AF_UNIX endpoint and expected server credentials must come from the exact
// lifecycle-owned endpoint, not from a response or pressure notification.
// SO_PEERPIDFD pins server liveness even when the server's PID is projected as
// zero in Android's child PID namespace. No numeric PID fallback is used.
class EnrollmentClient {
public:
    EnrollmentClient() = default;
    EnrollmentClient(const EnrollmentClient&) = delete;
    EnrollmentClient& operator=(const EnrollmentClient&) = delete;
    ~EnrollmentClient();

    // Takes ownership of the connected fd on every path. One call only.
    // timeout_ms is a handshake bound (1..2000), not a pressure threshold.
    bool Exchange(int connected_fd, const Credentials& expected_server,
                  const EnrollmentRequest& request, uint32_t timeout_ms,
                  GrantRecipients* recipients);
    // Thread-confined with Exchange/Close. This is not the watchdog gate.
    bool Healthy() const;
    int control_fd() const { return control_fd_; }
    int server_pidfd() const { return server_pidfd_; }
    void Close();

private:
    int control_fd_ = -1;
    int server_pidfd_ = -1;
    Credentials server_{};
    bool attempted_ = false;
};

}  // namespace droidloom::lmkd::relay
