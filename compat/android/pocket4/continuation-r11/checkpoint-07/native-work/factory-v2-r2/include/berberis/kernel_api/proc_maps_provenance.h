/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_PROVENANCE_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_PROVENANCE_H_

// V2 metadata projection. Factory wire definitions are shared explicitly.

#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/types.h>

#include "proc_maps_factory_protocol.h"

#if defined(__GNUC__)
#pragma GCC visibility push(hidden)
#endif

namespace berberis::proc_maps_provenance {

// Configuration is explicit and immutable. Absence of a verified broker or a
// required kernel API is an error for a virtual object, never a fabricated
// successful proc identity. socket_name excludes the initial abstract NUL.
struct Configuration {
  const char* socket_name;
  uint64_t initial_userns_device;
  uint64_t initial_userns_inode;
};
inline constexpr Configuration kCandidateConfiguration{
    kSocketName, kTrustedUserNamespaceDevice, kTrustedUserNamespaceInode};

// Checks actual calling-thread userns using PIDFD_THREAD + namespace ioctl,
// all real/effective/saved/fs uids nonzero, and effective/permitted/inheritable
// capability sets empty. No path-based /proc/self/ns/user inference is used.
// The deployment must independently qualify these calls in its Android policy.
int RequireUnprivilegedInitialNamespace(const Configuration& config);

// Inspect the real inode. Ordinary inode shapes use one native fstat. A
// possible virtual inode is pinned by pidfd_getfd in an independent fd table.
// With BERBERIS_PROCMAPS_RAW_METADATA_OWNER enabled, the explicitly prepared
// raw metadata worker only returns a fixed
// kernel snapshot; strict tag decoding runs on the normal caller thread.
// Guest close/reuse cannot close that private pin.
// There is no fd-number registry, cache or retained anchor. Kernel descriptor
// lifetime handles duplicated/transferred descriptors. The owner's startup,
// fork, credential/namespace transition and retirement hooks remain separate
// deployment gates. A malformed trusted tag fails closed; names are never
// consulted. Unprepared or quiesced generations cannot create a lazy worker.
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
// Raw LP64 kernel ABI, for ARM64 guest syscalls on the qualified x86_64 host.
// Only explicit V2 raw-statfs origin tags are projected. A host-libc result
// must never be guessed back into a kernel representation.
int FstatfsKernel(int fd, KernelStatfs* result, const Configuration& config);
int FstatfsForGuest(int fd, void* guest_result, const Configuration& config);
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
