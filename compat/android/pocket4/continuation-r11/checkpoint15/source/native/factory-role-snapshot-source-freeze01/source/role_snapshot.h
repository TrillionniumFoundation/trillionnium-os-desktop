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

}  // namespace droidloom::proc_maps_factory::role_v1
#endif
