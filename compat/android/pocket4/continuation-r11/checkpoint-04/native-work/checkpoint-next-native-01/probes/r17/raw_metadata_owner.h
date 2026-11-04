// SPDX-License-Identifier: Apache-2.0
// Experimental fixed-operation owner. No runtime hooks or provenance projection.
#ifndef POCKET4_RAW_METADATA_OWNER_H_
#define POCKET4_RAW_METADATA_OWNER_H_
#include <cstddef>
#include <cstdint>
#include <sys/stat.h>
#include <sys/statfs.h>

namespace pocket4::raw_metadata_owner {
struct Snapshot {
  struct stat identity{};
  struct statfs filesystem{};
  long stat_result=-999,statfs_result=-999,seals_result=-999,tag_result=-999;
  unsigned char tag[256]{};
  uint64_t worker_mask=0;
  int worker_tid=0,worker_tgid=0;
};
// First Start allocates a guarded stack. Later Stop/Start and explicit private
// child Reset reuse it. The worker has an independent descriptor table from
// clone and performs only fixed raw syscalls: no TLS, libc, callbacks or malloc.
// This is an owned qualification experiment, not a production API replacement.
int Start();
int Read(int fd,Snapshot* snapshot);
int Stop();
void ResetAfterPrivateFork();
bool HasInheritedStack();
}
#endif
