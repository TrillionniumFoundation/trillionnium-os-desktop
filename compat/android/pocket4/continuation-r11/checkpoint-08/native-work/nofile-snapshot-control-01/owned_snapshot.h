// Mechanism experiment only: no provenance, generation or production API claim.
#ifndef OWNED_NOFILE_SNAPSHOT_H_
#define OWNED_NOFILE_SNAPSHOT_H_
#include <atomic>
#include <sys/stat.h>
#include "proc_maps_kernel_statfs.h"

struct OwnedMetadata {
  struct stat identity{};
  berberis::proc_maps_provenance::KernelStatfs filesystem{};
};
struct OwnedSnapshotRequest {
  int fd = -1;
  int result = -999;
  std::atomic<int> ready{0}, go{0}, complete{0};
  OwnedMetadata internal{};
};
// Caller owns and preallocates the stack, blocks signals, and retains both
// request and stack until the kernel clears tid. This deliberately does not
// implement or bypass the production app-generation or provenance gates.
long SpawnOwnedFdSnapshot(void* stack_top, std::atomic<int>* tid,
                         OwnedSnapshotRequest* request);
long OwnedRaw(long number, long a=0, long b=0, long c=0,
              long d=0, long e=0, long f=0);
#endif
