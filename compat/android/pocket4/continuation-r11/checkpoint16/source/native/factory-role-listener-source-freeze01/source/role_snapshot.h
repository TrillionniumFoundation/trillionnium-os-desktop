// SPDX-License-Identifier: Apache-2.0
#ifndef DROIDLOOM_PROC_MAPS_ROLE_SNAPSHOT_H_
#define DROIDLOOM_PROC_MAPS_ROLE_SNAPSHOT_H_

#include "role_authorization.h"

namespace droidloom::proc_maps_factory::role_v1 {

// Produces an ordinary V2 provenance inode only within an already approved
// role grant. The two input descriptors remain owned by message. The returned
// descriptor is newly owned by the caller and is always CLOEXEC. No response is
// sent, no listener is created and no permission/policy is installed here.
//
// Both successful and failed creation finish the same registry transaction.
// Publication is allowed only after FinishCreate rechecks the bound process and
// held caller task. A finish failure closes a newly created output. The owner
// must still send it on this grant's authenticated session with a bounded
// response and revoke the session on transport failure.
//
// This entry does not establish the immutable pre-guest base/range policy.
// The trusted root-parent approval must already attest that platform boundary.
int CreateAuthorizedSnapshot(Registry& registry, GrantHandle handle,
                             const Received& message);

// The authenticated session dispatcher supplies its existing CLOCK_MONOTONIC
// deadline so receive, creation and response do not each get a new time budget.
// This entry requires a nonzero deadline at most two seconds from admission.
// Authorization failure revokes the supplied session without publishing a reply.
// An expired deadline still completes any authorized registry transaction;
// a descriptor is never returned after a post-creation deadline failure.
int CreateAuthorizedSnapshotBefore(Registry& registry, GrantHandle handle,
                                   const Received& message, uint64_t deadline);

}  // namespace droidloom::proc_maps_factory::role_v1
#endif
