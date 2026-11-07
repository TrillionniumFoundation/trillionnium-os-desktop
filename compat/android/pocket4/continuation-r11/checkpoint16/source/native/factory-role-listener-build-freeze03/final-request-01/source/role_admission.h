// SPDX-License-Identifier: Apache-2.0
#ifndef DROIDLOOM_PROC_MAPS_ROLE_ADMISSION_H_
#define DROIDLOOM_PROC_MAPS_ROLE_ADMISSION_H_

#include "role_session.h"

namespace droidloom::proc_maps_factory::role_v1 {
inline constexpr size_t kAdmissionReplyBytes = 64 + kWireBytes;
enum class AdmissionState : uint32_t { kPending = 1, kApproved = 2, kAttached = 3 };
struct AdmissionReply {
  Request request{};
  AdmissionState state{};
  // Populated only for Begin. This is a challenge, not permission to create.
  unsigned char token[kDigestBytes]{};
  uint32_t visible_pid{};
};
bool EncodeAdmissionReply(const AdmissionReply&, unsigned char output[kAdmissionReplyBytes]);
bool DecodeAdmissionReply(const unsigned char*, size_t, AdmissionReply*);
// Nonblocking receive on an independently authenticated root-factory socket.
// Requires the exact outstanding request and no descriptors. All known received
// FD-bearing ancillary records are closed on rejection. Output is atomic.
int ReceiveAdmissionReply(int connection, const Request& expected, AdmissionReply*);

struct Admission {
  AdmissionReply reply{};
  // Kernel-authenticated Registry transition identifies this local handle.
  // A request never supplies a slot or a serial number.
  GrantHandle handle{};
};

// One bounded actual accept4 -> Receive -> Begin/Approve/Attach -> reply path.
// The trusted caller holds the listener for this call and must configure its
// identity reception BEFORE accepting any peer. No listener is created, bound,
// published or enabled here. The existing V2 main and zero-cap gate are intact.
// The same two-second deadline covers accept, first frame and acknowledgement.
// Begin yields only a pending handle. It MUST NOT be dispatched until a real
// trusted-parent Approve succeeds; IsActive remains the authority gate.
// Approve attests the typed pre-guest policy transition through the original
// Registry kernel-parent checks. This function does not invent those inputs.
// Any error after a transition revokes exactly the returned Registry handle;
// other grants are not revoked based on a rejected token from an unknown peer.
// The accepted connection is retained only by successful Begin/Attach.
// Owner loss must also stop the enclosing service; no fallback is provided.
// No root service, Android early-fork caller or policy is activated by this API.
int AdmitOne(Registry&, const OwnerLease&, int inherited_listener, Admission*);
}  // namespace droidloom::proc_maps_factory::role_v1
#endif
