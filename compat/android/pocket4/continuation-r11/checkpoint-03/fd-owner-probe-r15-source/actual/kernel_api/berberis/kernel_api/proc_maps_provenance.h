/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_PROVENANCE_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_PROVENANCE_H_

// Candidate protocol, version 1. This is an inode-origin tag for the runtime's
// proc/maps snapshot. It conveys no application authentication/integrity verdict.
// All wire integers are unsigned little-endian; signed stat fields use their
// two's-complement 64-bit representation. Never serialize a native C struct.

#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/types.h>

#if defined(__GNUC__)
#pragma GCC visibility push(hidden)
#endif

namespace berberis::proc_maps_provenance {

inline constexpr char kTagName[] = "user.droidloom.proc_maps.v1";
// Immutable factory protocol shape, usable only as a negative exclusion. A
// matching display string never authenticates an inode; every positive path
// must still validate its root-owned sealed inode and complete origin tag.
inline constexpr char kSnapshotKernelPath[] = "/memfd:droidloom-proc-maps-v1 (deleted)";
inline constexpr char kTagMagic[8] = {'D', 'P', '4', 'M', 'A', 'P', 'S', '1'};
inline constexpr char kRequestMagic[8] = {'D', 'P', '4', 'R', 'E', 'Q', '0', '1'};
inline constexpr char kReplyMagic[8] = {'D', 'P', '4', 'R', 'E', 'P', '0', '1'};
inline constexpr uint32_t kVersion = 1;
inline constexpr uint32_t kCreateSnapshot = 1;
inline constexpr size_t kRequestBytes = 64;
inline constexpr size_t kReplyBytes = 32;
inline constexpr size_t kMaxPathBytes = 4096;
inline constexpr uint64_t kMaxSnapshotBytes = 8u * 1024u * 1024u;
inline constexpr uint32_t kRequiredSeals = 15;  // SEAL|SHRINK|GROW|WRITE
inline constexpr uint64_t kTrustedUserNamespaceDevice = 5;
inline constexpr uint64_t kTrustedUserNamespaceInode = 4026531837ULL;

// Request: magic[0:8], version u32@8, operation u32@12,
// payload_size u64@16, calling_tid u32@24, source_F_GETFL u32@28,
// original_F_GETFD u32@32, zero bytes[36:64]. Exactly two SCM_RIGHTS:
// (1) actual open /proc/<authenticated-peer-tgid>/maps, (2) sealed input
// snapshot. The factory opens/verifies the actual peer's maps independently;
// path/metadata claims never come from this request. One request per connection.
// Reply: magic[0:8], version u32@8, positive errno u32@12 (zero on success),
// zero bytes[16:32]. Success has exactly one SCM_RIGHTS; failure has none.
// Both directions use SOCK_SEQPACKET; MSG_TRUNC/MSG_CTRUNC are errors.

// Tag header: magic[0:8], version u32@8, total_length u32@12,
// path_length u32@16, zero u32@20. Then kWordCount u64 values, followed
// immediately by path_length bytes of the kernel origin readlink target.
// The target is nonempty, has no NUL, and is not terminated on the wire.
// statfs fsid words preserve the native 32-bit bit pattern, zero-extended.
enum TagWord : size_t {
  kFactoryUsernsDevice,
  kFactoryUsernsInode,
  kBackingDevice,
  kBackingInode,
  kBackingSize,
  kOriginTgid,
  kOriginStartTicks,
  kStatDevice,
  kStatInode,
  kStatMode,
  kStatNlink,
  kStatUid,
  kStatGid,
  kStatRdev,
  kStatSize,
  kStatBlockSize,
  kStatBlocks,
  kStatAtimeSeconds,
  kStatAtimeNanoseconds,
  kStatMtimeSeconds,
  kStatMtimeNanoseconds,
  kStatCtimeSeconds,
  kStatCtimeNanoseconds,
  kFsType,
  kFsBlockSize,
  kFsBlocks,
  kFsBlocksFree,
  kFsBlocksAvailable,
  kFsFiles,
  kFsFilesFree,
  kFsId0,
  kFsId1,
  kFsNameLength,
  kFsFragmentSize,
  kFsFlags,
  kFsSpare0,
  kFsSpare1,
  kFsSpare2,
  kFsSpare3,
  kWordCount
};
inline constexpr size_t kTagHeaderBytes = 24 + 8 * kWordCount;
inline constexpr size_t kMaxTagBytes = kTagHeaderBytes + kMaxPathBytes;

struct Origin {
  uint64_t words[kWordCount]{};
  char path[kMaxPathBytes]{};
  size_t path_size = 0;
};

enum class Lookup { kOrdinary, kVirtual, kError };

// Configuration is explicit and immutable. Absence of a verified broker or a
// required kernel API is an error for a virtual object, never a fabricated
// successful proc identity. socket_name excludes the initial abstract NUL.
struct Configuration {
  const char* socket_name;
  uint64_t initial_userns_device;
  uint64_t initial_userns_inode;
};
inline constexpr Configuration kCandidateConfiguration{
    "droidloom.proc_maps.v1", kTrustedUserNamespaceDevice, kTrustedUserNamespaceInode};

uint32_t GetU32(const unsigned char* bytes);
uint64_t GetU64(const unsigned char* bytes);
void PutU32(unsigned char* bytes, uint32_t value);
void PutU64(unsigned char* bytes, uint64_t value);
bool DecodeOrigin(const unsigned char* bytes, size_t size, Origin* origin);
bool DecodeStat(const Origin& origin, struct stat* result);
bool DecodeStatfs(const Origin& origin, struct statfs* result);

// Checks actual calling-thread userns using PIDFD_THREAD + namespace ioctl,
// all real/effective/saved/fs uids nonzero, and effective/permitted/inheritable
// capability sets empty. No path-based /proc/self/ns/user inference is used.
// The deployment must independently qualify these calls in its Android policy.
int RequireUnprivilegedInitialNamespace(const Configuration& config);

// Inspect the real inode. Ordinary inode shapes use one native fstat. A
// possible virtual inode is pinned by pidfd_getfd in a temporary owner's
// independent fd table; guest close/reuse cannot close that private pin.
// There is no fd-number registry, cache or retained anchor. Kernel descriptor
// lifetime handles dup/fork/exec/SCM_RIGHTS. The owner's creation/fork/platform
// qualification is a separate deployment gate. A malformed trusted tag fails
// closed; names are never consulted.
Lookup QueryOrigin(int fd, const Configuration& config, Origin* origin);

// Source is the actual already-open proc/maps FD and bytes are its translated
// snapshot. The broker creates a NEW root-owned sealed inode; it never changes
// ownership of the app's input inode. This is an owner-private operation; its
// returned FD stays CLOEXEC until single-open publication in the caller table.
int CreateSnapshot(int source_fd, const void* bytes, size_t size,
                   const Configuration& config, int original_fd_flags);

// Metadata results are trusted host-local structures, copied to guest memory
// by the syscall adapter. Unambiguously ordinary results are a single native
// observation. Other queries use a pin in an independent owner fd table; no
// temporary descriptor is installed in or closed from the caller's table.
int Fstat(int fd, struct stat* result, const Configuration& config);
int Fstatfs(int fd, struct statfs* result, const Configuration& config);
int CopyToCaller(const void* source, void* destination, size_t size);

// Returns a final result for both ordinary and virtual links (including -1).
// The bool return keeps the existing adapter signature. Ordinary native bytes
// come from one captured readlinkat observation, never a second path lookup.
// There is no direct user-buffer dereference: kernel-mediated copy preserves
// truncation/no-NUL and reports incomplete copies as EFAULT.
bool Readlinkat(int dirfd, const char* path, char* buffer, size_t size,
                const Configuration& config, ssize_t* result);

}  // namespace berberis::proc_maps_provenance
#if defined(__GNUC__)
#pragma GCC visibility pop
#endif
#endif
