// SPDX-License-Identifier: Apache-2.0
#ifndef DROIDLOOM_PROC_MAPS_ROLE_SESSION_H_
#define DROIDLOOM_PROC_MAPS_ROLE_SESSION_H_

#include "role_authorization.h"

namespace droidloom::proc_maps_factory::role_v1 {

// A response echoes the complete fixed request, not a peer-supplied role name.
// It is framing, not a replacement for the client's authenticated root-factory
// connection or the parent's pre-guest policy/NNP/range authorization.
inline constexpr size_t kResponseBytes = 32 + kWireBytes;
inline constexpr uint64_t kSessionRequestNanos = 2000000000ULL;
struct Response {
  Request request{};
  uint32_t error{};
  bool has_snapshot{};
};
bool EncodeResponse(const Response&, unsigned char output[kResponseBytes]);
bool DecodeResponse(const unsigned char*, size_t, Response*);

// One nonblocking receive. Expected is the single outstanding request on this
// authenticated session. Known FD-bearing ancillary data is owned even on
// rejection. Outputs are untouched on framing/FD failure. A framed error is a
// successful transport receive with Response.error != 0 and no descriptor.
int ReceiveResponse(int connection, const Request& expected, Response* response,
                    Descriptor* snapshot);

// Independent service-owner control lease. A role peer cannot supply it in a
// request. Binding requires a live kernel root peer PIDFD, initial user namespace
// and the service's same PID namespace. It never creates a listener, changes a
// capability, installs a policy, or authorizes a role. Registry::Approve retains
// the separate exact actual-parent and pre-guest authorization requirement.
class OwnerLease {
 public:
  OwnerLease() = default;
  ~OwnerLease();
  OwnerLease(const OwnerLease&) = delete;
  OwnerLease& operator=(const OwnerLease&) = delete;
  OwnerLease(OwnerLease&&) = delete;
  OwnerLease& operator=(OwnerLease&&) = delete;
  // Takes control ownership only after all checks succeed.
  int Initialize(Descriptor* control);
  int Verify() const;
  int control_fd() const;
  int owner_pidfd() const;
 private:
  // The storage is owned by the initializing service thread. A foreign
  // CLONE_VM destructor must not run Descriptor destructors on shared state.
  // As with Registry, external storage/freeing remains the owner's contract.
  // If its held proc proof becomes unreadable, deletion fails closed and the
  // enclosing owner process lifetime is the resource-reclamation boundary.
  struct Impl;
  Impl* impl_ = nullptr;
};

enum class DispatchState { kReplySent, kDetached, kReleased };
struct DispatchResult {
  Operation operation{};
  uint32_t operation_error{};
  bool snapshot_published{};
  DispatchState state = DispatchState::kReplySent;
};

// The production caller of CreateAuthorizedSnapshotBefore. This entry accepts
// only an already approved/attached Registry handle. Begin/Approve/Attach and
// listener admission remain the owner's separate protocol; they are never
// inferred from a request label here. There is no standalone service entry.
//
// Receive, creation and response share one absolute two-second deadline. A
// valid Create error may leave the approved grant usable after FinishCreate.
// Unknown operations, authentication failure, owner loss, timeout or transport
// failure revoke this handle and close unpublished output. Suspend is staged:
// send acknowledgement, then Detach while the peer is live; clients must wait
// for close and still authenticate Attach. An acknowledgement alone is not a
// completed reattachment. Release uses a held duplicate solely to acknowledge
// after the Registry has revoked the grant.
//
// Return 0 means the described response/transition completed, not that a
// Create succeeded: operation_error must also be zero. Failure leaves result
// untouched. No ordinary V2 or zero-capability admission gate is changed.
int DispatchOne(Registry&, GrantHandle, const OwnerLease&, DispatchResult*);

}  // namespace droidloom::proc_maps_factory::role_v1
#endif
