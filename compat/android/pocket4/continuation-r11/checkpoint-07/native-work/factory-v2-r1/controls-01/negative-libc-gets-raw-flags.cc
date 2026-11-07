// SPDX-License-Identifier: Apache-2.0
#include "berberis/kernel_api/proc_maps_factory_protocol.h"
#include <fcntl.h>
#include <limits.h>
#include <linux/magic.h>
#include <stdio.h>
#include <string.h>
#include <limits>
#include <type_traits>
namespace berberis::proc_maps_provenance {
namespace {
template <typename T>
bool UnsignedField(uint64_t value, T* output) {
  static_assert(std::is_integral_v<T>);
  if (value > static_cast<uint64_t>(std::numeric_limits<T>::max())) return false;
  *output = static_cast<T>(value);
  return true;
}

template <typename T>
bool SignedField(uint64_t value, T* output) {
  static_assert(std::is_integral_v<T> && sizeof(T) <= sizeof(int64_t));
  // memcpy preserves the specified two's-complement wire representation
  // without an out-of-range unsigned-to-signed arithmetic conversion.
  int64_t number;
  memcpy(&number, &value, sizeof(number));
  // The wire field is signed, but libc ABI declarations differ: for example
  // statfs.f_bsize is signed on glibc and unsigned on Bionic x86_64. Reject
  // negative-to-unsigned and every narrowing overflow before the final cast.
  if constexpr (std::is_signed_v<T>) {
    if (number < static_cast<int64_t>(std::numeric_limits<T>::min()) ||
        number > static_cast<int64_t>(std::numeric_limits<T>::max())) return false;
  } else {
    if (number < 0 || static_cast<uint64_t>(number) >
                          static_cast<uint64_t>(std::numeric_limits<T>::max())) return false;
  }
  *output = static_cast<T>(number);
  return true;
}


}  // namespace
uint32_t GetU32(const unsigned char* bytes) {
  uint32_t value = 0;
  for (unsigned i = 0; i != 4; ++i) value |= uint32_t{bytes[i]} << (8 * i);
  return value;
}
uint64_t GetU64(const unsigned char* bytes) {
  uint64_t value = 0;
  for (unsigned i = 0; i != 8; ++i) value |= uint64_t{bytes[i]} << (8 * i);
  return value;
}
void PutU32(unsigned char* bytes, uint32_t value) {
  for (unsigned i = 0; i != 4; ++i) bytes[i] = static_cast<unsigned char>(value >> (8 * i));
}
void PutU64(unsigned char* bytes, uint64_t value) {
  for (unsigned i = 0; i != 8; ++i) bytes[i] = static_cast<unsigned char>(value >> (8 * i));
}

bool DecodeOrigin(const unsigned char* bytes, size_t size, Origin* origin) {
  if (size < kTagHeaderBytes || size > kMaxTagBytes || memcmp(bytes, kTagMagic, 8) != 0 ||
      GetU32(bytes + 8) != kVersion || GetU32(bytes + 12) != size || GetU32(bytes + 20) != kLinuxLp64RawStatfs) return false;
  const size_t path_size = GetU32(bytes + 16);
  if (path_size == 0 || path_size > kMaxPathBytes || kTagHeaderBytes + path_size != size ||
      memchr(bytes + kTagHeaderBytes, 0, path_size) != nullptr) return false;
  Origin decoded;
  for (size_t i = 0; i != kWordCount; ++i) decoded.words[i] = GetU64(bytes + 24 + i * 8);
  memcpy(decoded.path, bytes + kTagHeaderBytes, path_size);
  decoded.path_size = path_size;
  if (decoded.words[kBackingSize] == 0 || decoded.words[kBackingSize] > kMaxSnapshotBytes ||
      decoded.words[kBackingInode] == 0 || decoded.words[kOriginTgid] == 0 ||
      decoded.words[kOriginTgid] > INT_MAX || decoded.words[kOriginStartTicks] == 0 ||
      decoded.words[kStatInode] == 0 || decoded.words[kFsType] != PROC_SUPER_MAGIC ||
      decoded.words[kStatMode] != (S_IFREG | 0444) ||
      decoded.words[kStatAtimeNanoseconds] >= 1000000000ULL ||
      decoded.words[kStatMtimeNanoseconds] >= 1000000000ULL ||
      decoded.words[kStatCtimeNanoseconds] >= 1000000000ULL) return false;
  char expected[64];
  const int expected_size = snprintf(expected, sizeof(expected), "/proc/%llu/maps",
                                    static_cast<unsigned long long>(decoded.words[kOriginTgid]));
  if (expected_size < 0 || static_cast<size_t>(expected_size) != path_size ||
      memcmp(decoded.path, expected, path_size) != 0) return false;
  struct stat st{};
  struct statfs fs{};
  if (!DecodeStat(decoded, &st) || !DecodeStatfs(decoded, &fs)) return false;
  *origin = decoded;
  return true;
}

bool DecodeStat(const Origin& origin, struct stat* result) {
  const auto* w = origin.words;
  struct stat value{};
  if (!UnsignedField(w[kStatDevice], &value.st_dev) ||
      !UnsignedField(w[kStatInode], &value.st_ino) ||
      !UnsignedField(w[kStatMode], &value.st_mode) ||
      !UnsignedField(w[kStatNlink], &value.st_nlink) ||
      !UnsignedField(w[kStatUid], &value.st_uid) ||
      !UnsignedField(w[kStatGid], &value.st_gid) ||
      !UnsignedField(w[kStatRdev], &value.st_rdev) ||
      !SignedField(w[kStatSize], &value.st_size) ||
      !SignedField(w[kStatBlockSize], &value.st_blksize) ||
      !SignedField(w[kStatBlocks], &value.st_blocks) ||
      !SignedField(w[kStatAtimeSeconds], &value.st_atim.tv_sec) ||
      !UnsignedField(w[kStatAtimeNanoseconds], &value.st_atim.tv_nsec) ||
      !SignedField(w[kStatMtimeSeconds], &value.st_mtim.tv_sec) ||
      !UnsignedField(w[kStatMtimeNanoseconds], &value.st_mtim.tv_nsec) ||
      !SignedField(w[kStatCtimeSeconds], &value.st_ctim.tv_sec) ||
      !UnsignedField(w[kStatCtimeNanoseconds], &value.st_ctim.tv_nsec)) return false;
  *result = value;
  return true;
}

bool DecodeKernelStatfs(const Origin& origin, KernelStatfs* result) {
  const auto* w = origin.words;
  KernelStatfs value{};
  // Procfs block, name and fragment sizes are nonnegative signed wire values.
  // Reject negative/oversized values before any native ABI conversion.
  if (w[kFsType] != PROC_SUPER_MAGIC ||
      w[kFsBlockSize] > INT64_MAX || w[kFsNameLength] > INT64_MAX ||
      w[kFsFragmentSize] > INT64_MAX ||
      w[kFsId0] > UINT32_MAX || w[kFsId1] > UINT32_MAX) return false;
  value.f_type=w[kFsType];value.f_bsize=w[kFsBlockSize];
  value.f_blocks=w[kFsBlocks];value.f_bfree=w[kFsBlocksFree];
  value.f_bavail=w[kFsBlocksAvailable];value.f_files=w[kFsFiles];
  value.f_ffree=w[kFsFilesFree];value.f_fsid[0]=static_cast<uint32_t>(w[kFsId0]);
  value.f_fsid[1]=static_cast<uint32_t>(w[kFsId1]);
  value.f_namelen=w[kFsNameLength];value.f_frsize=w[kFsFragmentSize];
  value.f_flags=w[kFsFlags];
  for (unsigned i=0;i<4;++i)value.f_spare[i]=w[kFsSpare0+i];
  *result=value;
  return true;
}
bool DecodeStatfs(const Origin& origin, struct statfs* result) {
  KernelStatfs value{};
  if (!DecodeKernelStatfs(origin,&value))return false;
  memcpy(result,&value,sizeof(value));
  return true;
}
size_t EncodeOrigin(const Origin& origin,unsigned char* output,size_t capacity) {
  if(origin.path_size==0 || origin.path_size>kMaxPathBytes ||
     capacity<kTagHeaderBytes+origin.path_size)return 0;
  unsigned char bytes[kMaxTagBytes]{};
  const size_t size=kTagHeaderBytes+origin.path_size;
  memcpy(bytes,kTagMagic,8);PutU32(bytes+8,kVersion);
  PutU32(bytes+12,static_cast<uint32_t>(size));
  PutU32(bytes+16,static_cast<uint32_t>(origin.path_size));
  PutU32(bytes+20,kLinuxLp64RawStatfs);
  for(size_t i=0;i<kWordCount;++i)PutU64(bytes+24+i*8,origin.words[i]);
  memcpy(bytes+kTagHeaderBytes,origin.path,origin.path_size);
  Origin verified{};
  if(!DecodeOrigin(bytes,size,&verified))return 0;
  memcpy(output,bytes,size);
  return size;
}
bool DecodeCreateRequest(const unsigned char* bytes,size_t size,CreateRequest* request) {
  if(size!=kRequestBytes || memcmp(bytes,kRequestMagic,8) ||
     GetU32(bytes+8)!=kVersion || GetU32(bytes+12)!=kCreateSnapshot ||
     GetU32(bytes+36)!=kLinuxLp64RawStatfs || GetU32(bytes+40)!=64)return false;
  for(size_t i=44;i<kRequestBytes;++i)if(bytes[i])return false;
  CreateRequest value{GetU64(bytes+16),GetU32(bytes+24),GetU32(bytes+28),GetU32(bytes+32)};
  if(value.payload_size==0 || value.payload_size>kMaxSnapshotBytes ||
     value.caller_tid==0 || value.caller_tid>INT_MAX ||
     (value.source_flags&(O_PATH|O_ACCMODE))!=O_RDONLY ||
     (value.original_fd_flags&~static_cast<uint32_t>(FD_CLOEXEC)))return false;
  *request=value;
  return true;
}
bool EncodeCreateRequest(const CreateRequest& request,unsigned char output[kRequestBytes]) {
  unsigned char bytes[kRequestBytes]{};
  memcpy(bytes,kRequestMagic,8);PutU32(bytes+8,kVersion);PutU32(bytes+12,kCreateSnapshot);
  PutU64(bytes+16,request.payload_size);PutU32(bytes+24,request.caller_tid);
  PutU32(bytes+28,request.source_flags);PutU32(bytes+32,request.original_fd_flags);
  PutU32(bytes+36,kLinuxLp64RawStatfs);PutU32(bytes+40,64);
  CreateRequest verified{};
  if(!DecodeCreateRequest(bytes,sizeof(bytes),&verified))return false;
  memcpy(output,bytes,sizeof(bytes));return true;
}
void EncodeReply(uint32_t error,unsigned char output[kReplyBytes]) {
  memset(output,0,kReplyBytes);memcpy(output,kReplyMagic,8);
  PutU32(output+8,kVersion);PutU32(output+12,error);
}

}  // namespace berberis::proc_maps_provenance
