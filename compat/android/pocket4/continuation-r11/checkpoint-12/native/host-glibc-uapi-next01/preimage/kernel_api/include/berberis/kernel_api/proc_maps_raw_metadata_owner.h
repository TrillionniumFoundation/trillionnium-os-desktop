// SPDX-License-Identifier: Apache-2.0
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_RAW_METADATA_OWNER_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_RAW_METADATA_OWNER_H_
#include "proc_maps_provenance.h"
#include <stdint.h>

// Deployment is deliberately opt-in. The native bridge/ART generation
// protocol and all transition gates must be qualified before enabling this
// for Main. Owned controls compile the same code with this set to 1.
#ifndef BERBERIS_PROCMAPS_RAW_METADATA_OWNER
#define BERBERIS_PROCMAPS_RAW_METADATA_OWNER 0
#endif

namespace berberis::proc_maps_provenance::raw_metadata_owner {
// Exact caller/worker observations for one qualified app generation. These
// fields are never supplied by the guest. Kernel syscalls fill both sides.
struct AppContext {
  static constexpr unsigned kMaxGroups=128;
  uint32_t uid[3]{};
  uint32_t gid[3]{};
  uint32_t fsuid=0,fsgid=0;
  uint32_t capabilities[6]{};
  uint32_t groups[kMaxGroups]{};
  unsigned group_count=0;
  struct stat root{},user_namespace{},mount_namespace{};
};
struct Snapshot {
  struct stat identity{},final_identity{};
  // One pinned observation has two explicitly different ABI views.
  KernelStatfs kernel_filesystem{};
  struct statfs filesystem{};
  AppContext worker_before{},worker_after{};
  // 0 ordinary, 1 root-owned sealed tag ready for strict caller-side decoding.
  int tagged=0;
  size_t tag_size=0;
  unsigned char tag[kMaxTagBytes]{};
};

// Explicit initialization after application specialization, never from a
// generic thread-attach or signal callback. Reject root/saved-root/capabilities,
// mismatched fs IDs or user namespaces before any metadata operation. A worker
// must not cross a credential/root/mount/namespace/zygote/exec generation.
// Memory preparation reserves the persistent and inherited-table worker
// stacks before specialization. It creates no worker, stores no credentials
// and opens no request admission. Both stacks survive a private fork.
int PrepareInheritedStack();
int Start();
int Read(int fd,Snapshot* snapshot);
int Stop();
bool Enabled();
// Stop and close admission BEFORE a known transition. This is also required
// for zygote prepare and exec/last-host-thread retirement. No request lazily
// reopens a closed generation. This revision permanently closes the current
// process generation: Start also rejects until a private child reset. General
// same-process transition/resume support is not claimed.
int QuiesceBeforeTransition();
// Private-memory children only. Drop copied synchronization state; preserve
// stack, require explicit Start and a fresh caller/worker context qualification.
// A new TGID sharing CLONE_VM must never call this reset.
void ResetAfterPrivateFork();
bool HasInheritedStack();
}
#endif
