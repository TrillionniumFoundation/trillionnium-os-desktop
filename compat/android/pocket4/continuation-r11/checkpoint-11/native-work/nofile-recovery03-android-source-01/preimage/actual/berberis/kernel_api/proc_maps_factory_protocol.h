// SPDX-License-Identifier: Apache-2.0
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_FACTORY_PROTOCOL_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_FACTORY_PROTOCOL_H_
// New V2 protocol. It records kernel inode origin, not application integrity.
// Statfs words explicitly retain the Linux LP64 raw ABI including ST_VALID.
// Every wire integer is little endian; no native C struct goes on the wire.
#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/types.h>
#include "proc_maps_kernel_statfs.h"
#if defined(__GNUC__)
#pragma GCC visibility push(hidden)
#endif
namespace berberis::proc_maps_provenance {
inline constexpr char kTagName[] = "user.droidloom.proc_maps.v2";
// Immutable factory protocol shape, usable only as a negative exclusion. A
// matching display string never authenticates an inode; every positive path
// must still validate its root-owned sealed inode and complete origin tag.
inline constexpr char kSnapshotKernelPath[] = "/memfd:droidloom-proc-maps-v2 (deleted)";
inline constexpr char kTagMagic[8] = {'D', 'P', '4', 'M', 'A', 'P', 'S', '2'};
inline constexpr char kRequestMagic[8] = {'D', 'P', '4', 'R', 'E', 'Q', '0', '2'};
inline constexpr char kReplyMagic[8] = {'D', 'P', '4', 'R', 'E', 'P', '0', '2'};
inline constexpr uint32_t kVersion = 2;
inline constexpr uint32_t kLinuxLp64RawStatfs = 1;
inline constexpr char kSocketName[] = "droidloom.proc_maps.v2";
inline constexpr char kSnapshotName[] = "droidloom-proc-maps-v2";
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
// original_F_GETFD u32@32, raw_statfs_encoding u32@36=1,
// ABI_bits u32@40=64, zero bytes[44:64]. Exactly two SCM_RIGHTS:
// (1) actual open maps in the authenticated peer's procfs view, (2) sealed input
// snapshot. The factory opens/verifies the actual peer's maps independently;
// path/metadata claims never come from this request. One request per connection.
// Reply: magic[0:8], version u32@8, positive errno u32@12 (zero on success),
// zero bytes[16:32]. Success has exactly one SCM_RIGHTS; failure has none.
// Both directions use SOCK_SEQPACKET; MSG_TRUNC/MSG_CTRUNC are errors.

// Tag header: magic[0:8], version u32@8, total_length u32@12,
// path_length u32@16, raw_statfs_encoding u32@20=1. Then kWordCount u64 values, followed
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


uint32_t GetU32(const unsigned char* bytes);
uint64_t GetU64(const unsigned char* bytes);
void PutU32(unsigned char* bytes, uint32_t value);
void PutU64(unsigned char* bytes, uint64_t value);
bool DecodeOrigin(const unsigned char* bytes, size_t size, Origin* origin);
bool DecodeStat(const Origin& origin, struct stat* result);
bool DecodeKernelStatfs(const Origin& origin, KernelStatfs* result);
bool DecodeStatfs(const Origin& origin, struct statfs* result);
size_t EncodeOrigin(const Origin& origin, unsigned char* output, size_t capacity);
struct CreateRequest {
  uint64_t payload_size{};
  uint32_t caller_tid{};
  uint32_t source_flags{};
  uint32_t original_fd_flags{};
};
bool DecodeCreateRequest(const unsigned char* bytes, size_t size, CreateRequest* request);
bool EncodeCreateRequest(const CreateRequest& request, unsigned char output[kRequestBytes]);
void EncodeReply(uint32_t error, unsigned char output[kReplyBytes]);

}  // namespace berberis::proc_maps_provenance
#if defined(__GNUC__)
#pragma GCC visibility pop
#endif
#endif
