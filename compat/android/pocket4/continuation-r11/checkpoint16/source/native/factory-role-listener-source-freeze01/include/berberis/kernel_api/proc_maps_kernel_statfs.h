// SPDX-License-Identifier: Apache-2.0
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_KERNEL_STATFS_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_KERNEL_STATFS_H_

#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/statfs.h>
#include <type_traits>

namespace berberis::proc_maps_provenance {

// Linux asm-generic/statfs.h LP64 raw-syscall representation, shared by
// x86_64 and arm64. These members retain kernel bits, not libc semantics.
// Never construct it by adding flags to an already-normalized libc result.
struct KernelStatfs {
  uint64_t f_type{}, f_bsize{}, f_blocks{}, f_bfree{}, f_bavail{};
  uint64_t f_files{}, f_ffree{};
  uint32_t f_fsid[2]{};
  uint64_t f_namelen{}, f_frsize{}, f_flags{}, f_spare[4]{};
};
static_assert(sizeof(long) == 8);
static_assert(std::is_standard_layout_v<KernelStatfs>);
static_assert(std::is_trivially_copyable_v<KernelStatfs>);
static_assert(sizeof(KernelStatfs) == 120 && alignof(KernelStatfs) == 8);
static_assert(sizeof(struct statfs) == sizeof(KernelStatfs));
#define BERBERIS_CHECK_KERNEL_STATFS_FIELD(field, offset, bytes) \
  static_assert(offsetof(KernelStatfs, field) == offset); \
  static_assert(sizeof(KernelStatfs::field) == bytes); \
  static_assert(offsetof(struct statfs, field) == offset); \
  static_assert(sizeof(((struct statfs*)nullptr)->field) == bytes)
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_type, 0, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_bsize, 8, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_blocks, 16, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_bfree, 24, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_bavail, 32, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_files, 40, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_ffree, 48, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_fsid, 56, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_namelen, 64, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_frsize, 72, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_flags, 80, 8);
BERBERIS_CHECK_KERNEL_STATFS_FIELD(f_spare, 88, 32);
#undef BERBERIS_CHECK_KERNEL_STATFS_FIELD

// Caller-side conversion only. The fixed worker writes KernelStatfs directly.
// The host libc ABI has the asserted layout above, but Bionic's successful
// fstatfs wrapper clears ST_VALID. Preserve every other bit and raw snapshot.
inline void KernelStatfsToLibc(const KernelStatfs& kernel, struct statfs* result) {
  memcpy(result, &kernel, sizeof(kernel));
#if defined(__BIONIC__)
  result->f_flags &= ~0x0020;
#endif
}
}  // namespace berberis::proc_maps_provenance
#endif
