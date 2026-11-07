/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#include "berberis/kernel_api/proc_maps_provenance.h"
#include "berberis/kernel_api/proc_maps_fd_owner.h"
#include "berberis/kernel_api/proc_maps_path.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/capability.h>
#include <linux/magic.h>
#include <linux/memfd.h>
#include <linux/nsfs.h>
#include <poll.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/un.h>
#include <sys/xattr.h>
#include <unistd.h>

#include <algorithm>
#include <limits>
#include <type_traits>

namespace berberis::proc_maps_provenance {
namespace {

// Linux UAPI include/uapi/linux/pidfd.h. These are intentionally independent
// of whether an older Android libc header has acquired the new symbolic names.
constexpr int kPidfdThread = O_EXCL;
constexpr unsigned long kPidfdUserNamespace = _IO(0xff, 9);
constexpr int kPeerPidfd = 77;  // SO_PEERPIDFD, Linux asm-generic/socket.h

class Fd {
 public:
  explicit Fd(int value = -1) : value_(value) {}
  ~Fd() {
    const int saved = errno;
    if (value_ >= 0) syscall(SYS_close, value_);
    errno = saved;
  }
  Fd(const Fd&) = delete;
  Fd& operator=(const Fd&) = delete;
  int get() const { return value_; }
  int release() { const int result = value_; value_ = -1; return result; }
 private:
  int value_;
};

int Error(int error) { errno = error; return -1; }

int PidfdOpen(pid_t tid) {
#ifdef SYS_pidfd_open
  return static_cast<int>(syscall(SYS_pidfd_open, tid, kPidfdThread));
#else
  (void)tid;
  return Error(ENOSYS);
#endif
}

int PidfdGetfd(int pidfd, int fd) {
#ifdef SYS_pidfd_getfd
  return static_cast<int>(syscall(SYS_pidfd_getfd, pidfd, fd, 0));
#else
  (void)pidfd; (void)fd;
  return Error(ENOSYS);
#endif
}

int CheckUserNamespace(int pidfd, const Configuration& config) {
  Fd ns(static_cast<int>(ioctl(pidfd, kPidfdUserNamespace, 0)));
  if (ns.get() < 0) return -1;
  struct stat info{};
  struct statfs fs{};
  if (::fstat(ns.get(), &info) < 0 || ::fstatfs(ns.get(), &fs) < 0) return -1;
  const int kind = ioctl(ns.get(), NS_GET_NSTYPE, 0);
  if (kind < 0) return -1;
  if (kind != CLONE_NEWUSER || static_cast<uint64_t>(fs.f_type) != NSFS_MAGIC ||
      static_cast<uint64_t>(info.st_dev) != config.initial_userns_device ||
      static_cast<uint64_t>(info.st_ino) != config.initial_userns_inode) {
    return Error(EXDEV);
  }
  return 0;
}

bool EqualInode(const struct stat& left, const struct stat& right) {
  return left.st_dev == right.st_dev && left.st_ino == right.st_ino;
}

// This is only a negative filter. Passing it never establishes provenance.
// Every valid factory snapshot must have this immutable inode shape.
bool MayBeVirtual(const struct stat& actual) {
  return S_ISREG(actual.st_mode) && actual.st_uid == 0 && actual.st_gid == 0 &&
         (actual.st_mode & 07777) == 0444 && actual.st_nlink == 0 &&
         actual.st_size > 0 && static_cast<uint64_t>(actual.st_size) <= kMaxSnapshotBytes;
}

bool AllZero(const unsigned char* data, size_t size) {
  for (size_t i = 0; i != size; ++i) if (data[i] != 0) return false;
  return true;
}

template <typename T>
bool UnsignedField(uint64_t value, T* output) {
  static_assert(std::is_integral_v<T>);
  if (value > static_cast<uint64_t>(std::numeric_limits<T>::max())) return false;
  *output = static_cast<T>(value);
  return true;
}

template <typename T>
bool SignedField(uint64_t value, T* output) {
  static_assert(std::is_integral_v<T> && std::is_signed_v<T>);
  // memcpy preserves the specified two's-complement wire representation
  // without an out-of-range unsigned-to-signed arithmetic conversion.
  int64_t number;
  memcpy(&number, &value, sizeof(number));
  if (number < std::numeric_limits<T>::min() || number > std::numeric_limits<T>::max()) {
    return false;
  }
  *output = static_cast<T>(number);
  return true;
}

// Uses a verified procfs directory for THIS THREAD's fdtable, including a
// thread which has unshared CLONE_FILES. /proc/self/fd would use the leader's
// table and is deliberately not used for our private descriptors.
int OpenOwnProcFdDirectory() {
  Fd directory(::open("/proc/thread-self/fd", O_PATH | O_DIRECTORY | O_CLOEXEC));
  if (directory.get() < 0) return -1;
  struct statfs fs{};
  if (::fstatfs(directory.get(), &fs) < 0) return -1;
  if (static_cast<uint64_t>(fs.f_type) != PROC_SUPER_MAGIC) return Error(EXDEV);
  return directory.release();
}

ssize_t ReadFdKernelPath(int directory, int fd, char* path, size_t size) {
  char number[32];
  const int length = snprintf(number, sizeof(number), "%d", fd);
  if (length <= 0 || static_cast<size_t>(length) >= sizeof(number)) return Error(EOVERFLOW);
  return ::readlinkat(directory, number, path, size);
}

// O_PATH cannot be passed to fgetxattr/F_GET_SEALS. Reopen only after pinning
// and identifying an ordinary regular tmpfs inode; never open a device/FIFO.
// The final inode comparison binds the reopen to the held path object.
int ReadablePin(int pinned, const struct stat& identity) {
  const int flags = fcntl(pinned, F_GETFL);
  if (flags < 0) return -1;
  if ((flags & O_PATH) == 0) return fcntl(pinned, F_DUPFD_CLOEXEC, 0);
  Fd directory(::open("/proc/thread-self/fd", O_PATH | O_DIRECTORY | O_CLOEXEC));
  if (directory.get() < 0) return -1;
  struct statfs directory_fs{};
  if (::fstatfs(directory.get(), &directory_fs) < 0) return -1;
  if (static_cast<uint64_t>(directory_fs.f_type) != PROC_SUPER_MAGIC) return Error(EXDEV);
  // A procfs mount can expose a different PID namespace's numeric names.
  // Reopening does not need to infer that namespace: the held owner pin and
  // the final inode equality below bind the actual object. This is separate
  // from readlink path-to-task resolution, which still needs that protocol.
  char number[32];
  const int length = snprintf(number, sizeof(number), "%d", pinned);
  if (length <= 0 || static_cast<size_t>(length) >= sizeof(number)) return Error(EOVERFLOW);
  Fd readable(::openat(directory.get(), number, O_RDONLY | O_CLOEXEC));
  if (readable.get() < 0) return -1;
  struct stat after{};
  if (::fstat(readable.get(), &after) < 0) return -1;
  if (!EqualInode(identity, after)) return Error(ESTALE);
  return readable.release();
}

Lookup QueryPinned(int pinned, const Configuration& config, Origin* origin) {
  struct stat actual{};
  struct statfs fs{};
  if (::fstat(pinned, &actual) < 0) return Lookup::kError;
  // These are only an inexpensive candidate filter, not an identity decision.
  // Reject ordinary objects before reopening O_PATH or checking userns/xattrs.
  if (!MayBeVirtual(actual)) return Lookup::kOrdinary;
  if (::fstatfs(pinned, &fs) < 0) return Lookup::kError;
  if (static_cast<uint64_t>(fs.f_type) != TMPFS_MAGIC) return Lookup::kOrdinary;
  Fd readable(ReadablePin(pinned, actual));
  if (readable.get() < 0) return Lookup::kError;
  unsigned char bytes[kMaxTagBytes];
  const ssize_t size = fgetxattr(readable.get(), kTagName, bytes, sizeof(bytes));
  if (size < 0) {
    if (errno == ENODATA || errno == ENOTSUP) return Lookup::kOrdinary;
    return Lookup::kError;
  }
  // Test current userns before giving UID 0 any meaning. A copied user.* tag
  // on an App-owned inode is not a virtual file, regardless of its name.
  if (RequireUnprivilegedInitialNamespace(config) < 0) return Lookup::kError;
  if (actual.st_uid != 0 || actual.st_gid != 0 ||
      (actual.st_mode & 07777) != 0444 || actual.st_nlink != 0) return Lookup::kOrdinary;
  const int seals = fcntl(readable.get(), F_GET_SEALS);
  if (seals < 0) return Lookup::kError;
  if ((seals & kRequiredSeals) != kRequiredSeals) return Lookup::kOrdinary;
  if (!DecodeOrigin(bytes, static_cast<size_t>(size), origin)) {
    Error(EBADMSG);
    return Lookup::kError;
  }
  if (origin->words[kFactoryUsernsDevice] != config.initial_userns_device ||
      origin->words[kFactoryUsernsInode] != config.initial_userns_inode ||
      origin->words[kBackingDevice] != static_cast<uint64_t>(actual.st_dev) ||
      origin->words[kBackingInode] != static_cast<uint64_t>(actual.st_ino) ||
      origin->words[kBackingSize] != static_cast<uint64_t>(actual.st_size)) {
    Error(ESTALE);
    return Lookup::kError;
  }
  struct stat final_info{};
  if (::fstat(readable.get(), &final_info) < 0) return Lookup::kError;
  if (!EqualInode(actual, final_info) || actual.st_mode != final_info.st_mode ||
      actual.st_uid != final_info.st_uid || actual.st_gid != final_info.st_gid ||
      actual.st_size != final_info.st_size || final_info.st_nlink != 0) {
    Error(ESTALE);
    return Lookup::kError;
  }
  if (RequireUnprivilegedInitialNamespace(config) < 0) return Lookup::kError;
  return Lookup::kVirtual;
}

enum class MetadataOperation { kOrigin, kStat, kStatfs };

struct MetadataRequest {
  const Configuration* config;
  MetadataOperation operation;
  Lookup lookup = Lookup::kError;
  Origin origin{};
  struct stat info{};
  struct statfs filesystem{};
};

int ReadOwnedMetadata(int fd, void* context) {
  auto* request = static_cast<MetadataRequest*>(context);
  request->lookup = QueryPinned(fd, *request->config, &request->origin);
  if (request->lookup == Lookup::kError) return -1;
  switch (request->operation) {
    case MetadataOperation::kOrigin:
      return 0;
    case MetadataOperation::kStat:
      if (request->lookup == Lookup::kOrdinary) return ::fstat(fd, &request->info);
      if (!DecodeStat(request->origin, &request->info)) return Error(EBADMSG);
      return 0;
    case MetadataOperation::kStatfs:
      if (request->lookup == Lookup::kOrdinary) return ::fstatfs(fd, &request->filesystem);
      if (!DecodeStatfs(request->origin, &request->filesystem)) return Error(EBADMSG);
      return 0;
  }
  return Error(EIO);
}

int CopyKernel(int process, const void* source, void* destination, size_t size) {
  struct iovec local{const_cast<void*>(source), size};
  struct iovec remote{destination, size};
#ifdef SYS_process_vm_writev
  const ssize_t copied = syscall(SYS_process_vm_writev, process, &local, 1, &remote, 1, 0);
  if (copied < 0) return -1;
  if (static_cast<size_t>(copied) != size) return Error(EFAULT);
  return 0;
#else
  (void)process; (void)local; (void)remote;
  return Error(ENOSYS);
#endif
}

bool Number(const char*& cursor, const char* end, int* value) {
  if (cursor == end || *cursor < '0' || *cursor > '9') return false;
  if (*cursor == '0' && cursor + 1 != end && cursor[1] >= '0' && cursor[1] <= '9') return false;
  unsigned result = 0;
  while (cursor != end && *cursor >= '0' && *cursor <= '9') {
    const unsigned digit = static_cast<unsigned>(*cursor++ - '0');
    if (result > (static_cast<unsigned>(INT_MAX) - digit) / 10) return false;
    result = result * 10 + digit;
  }
  *value = static_cast<int>(result);
  return true;
}

bool Consume(const char*& cursor, const char* end, const char* literal) {
  const size_t size = strlen(literal);
  if (size > static_cast<size_t>(end - cursor) || memcmp(cursor, literal, size) != 0) return false;
  cursor += size;
  return true;
}

bool ParseProcFd(const char* path, size_t size, int* tid, int* descriptor) {
  const char* cursor = path;
  const char* end = path + size;
  int tgid;
  if (!Consume(cursor, end, "/proc/") || !Number(cursor, end, &tgid) || tgid <= 0) return false;
  *tid = tgid;
  if (end - cursor >= 6 && memcmp(cursor, "/task/", 6) == 0) {
    cursor += 6;
    if (!Number(cursor, end, tid) || *tid <= 0) return false;
  }
  return Consume(cursor, end, "/fd/") && Number(cursor, end, descriptor) && cursor == end;
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
      GetU32(bytes + 8) != kVersion || GetU32(bytes + 12) != size || GetU32(bytes + 20) != 0) return false;
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

bool DecodeStatfs(const Origin& origin, struct statfs* result) {
  const auto* w = origin.words;
  struct statfs value{};
  if (!UnsignedField(w[kFsType], &value.f_type) ||
      !SignedField(w[kFsBlockSize], &value.f_bsize) ||
      !UnsignedField(w[kFsBlocks], &value.f_blocks) ||
      !UnsignedField(w[kFsBlocksFree], &value.f_bfree) ||
      !UnsignedField(w[kFsBlocksAvailable], &value.f_bavail) ||
      !UnsignedField(w[kFsFiles], &value.f_files) ||
      !UnsignedField(w[kFsFilesFree], &value.f_ffree) ||
      !SignedField(w[kFsNameLength], &value.f_namelen) ||
      !SignedField(w[kFsFragmentSize], &value.f_frsize) ||
      !UnsignedField(w[kFsFlags], &value.f_flags) ||
      w[kFsId0] > UINT32_MAX || w[kFsId1] > UINT32_MAX) return false;
  const uint32_t fsid[2] = {static_cast<uint32_t>(w[kFsId0]), static_cast<uint32_t>(w[kFsId1])};
  static_assert(sizeof(value.f_fsid) == sizeof(fsid));
  memcpy(&value.f_fsid, fsid, sizeof(fsid));
  for (unsigned i = 0; i != 4; ++i) {
    if (!UnsignedField(w[kFsSpare0 + i], &value.f_spare[i])) return false;
  }
  *result = value;
  return true;
}

int RequireUnprivilegedInitialNamespace(const Configuration& config) {
  if (config.initial_userns_device != kTrustedUserNamespaceDevice ||
      config.initial_userns_inode != kTrustedUserNamespaceInode) return Error(EINVAL);
  uid_t real, effective, saved;
  if (getresuid(&real, &effective, &saved) < 0) return -1;
  const long fsuid = syscall(SYS_setfsuid, static_cast<uid_t>(-1));
  if (real == 0 || effective == 0 || saved == 0 || fsuid <= 0) return Error(EPERM);
  struct __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3, 0};
  struct __user_cap_data_struct caps[2]{};
  if (syscall(SYS_capget, &header, caps) < 0) return -1;
  for (const auto& cap : caps) {
    if (cap.effective != 0 || cap.permitted != 0 || cap.inheritable != 0) return Error(EPERM);
  }
  // Linux maintains ambient as a subset of permitted & inheritable, both zero.
  Fd self(PidfdOpen(static_cast<pid_t>(syscall(SYS_gettid))));
  if (self.get() < 0) return -1;
  return CheckUserNamespace(self.get(), config);
}

Lookup QueryOrigin(int fd, const Configuration& config, Origin* origin) {
  const int incoming_errno = errno;
  struct stat actual{};
  if (::fstat(fd, &actual) < 0) return Lookup::kError;
  if (!MayBeVirtual(actual)) return Lookup::kOrdinary;
  MetadataRequest request{&config, MetadataOperation::kOrigin};
  if (fd_owner::WithPinnedFd(fd, ReadOwnedMetadata, &request) < 0) return Lookup::kError;
  if (request.lookup == Lookup::kVirtual) *origin = request.origin;
  errno = incoming_errno;
  return request.lookup;
}

int Fstat(int fd, struct stat* result, const Configuration& config) {
  const int incoming_errno = errno;
  struct stat actual{};
  if (::fstat(fd, &actual) < 0) return -1;
  if (!MayBeVirtual(actual)) {
    // Return this single kernel observation; do not re-read a possibly reused
    // fd or allocate a helper merely to answer an ordinary metadata query.
    *result = actual;
    return 0;
  }
  MetadataRequest request{&config, MetadataOperation::kStat};
  if (fd_owner::WithPinnedFd(fd, ReadOwnedMetadata, &request) < 0) return -1;
  *result = request.info;
  errno = incoming_errno;
  return 0;
}

int Fstatfs(int fd, struct statfs* result, const Configuration& config) {
  const int incoming_errno = errno;
  struct statfs actual{};
  if (::fstatfs(fd, &actual) < 0) return -1;
  if (static_cast<uint64_t>(actual.f_type) != TMPFS_MAGIC) {
    // This one syscall is a complete ordinary result. For tmpfs, separate
    // fstat/fstatfs observations cannot exclude A->virtual->A fd-table races.
    *result = actual;
    return 0;
  }
  MetadataRequest request{&config, MetadataOperation::kStatfs};
  if (fd_owner::WithPinnedFd(fd, ReadOwnedMetadata, &request) < 0) return -1;
  *result = request.filesystem;
  errno = incoming_errno;
  return 0;
}

int CopyToCaller(const void* source, void* destination, size_t size) {
  return CopyKernel(static_cast<int>(syscall(SYS_gettid)), source, destination, size);
}

int CreateSnapshot(int source_fd, const void* bytes, size_t size, const Configuration& config,
                   int original_fd_flags) {
  if (size == 0 || size > kMaxSnapshotBytes || config.socket_name == nullptr ||
      (original_fd_flags & ~FD_CLOEXEC) != 0) return Error(EINVAL);
  if (RequireUnprivilegedInitialNamespace(config) < 0) return -1;
  Fd source(fcntl(source_fd, F_DUPFD_CLOEXEC, 0));
  if (source.get() < 0) return -1;
  struct stat source_info{};
  struct statfs source_fs{};
  if (::fstat(source.get(), &source_info) < 0 || ::fstatfs(source.get(), &source_fs) < 0) return -1;
  const int status_flags = fcntl(source.get(), F_GETFL);
  if (status_flags < 0) return -1;
  if (!S_ISREG(source_info.st_mode) || static_cast<uint64_t>(source_fs.f_type) != PROC_SUPER_MAGIC ||
      (status_flags & (O_PATH | O_ACCMODE)) != O_RDONLY) return Error(EINVAL);
  Fd input(static_cast<int>(syscall(SYS_memfd_create, "droidloom-proc-maps-input",
                                  MFD_CLOEXEC | MFD_ALLOW_SEALING)));
  if (input.get() < 0) return -1;
  size_t written = 0;
  while (written != size) {
    const ssize_t count = write(input.get(), static_cast<const char*>(bytes) + written, size - written);
    if (count < 0) { if (errno == EINTR) continue; return -1; }
    if (count == 0) return Error(EIO);
    written += static_cast<size_t>(count);
  }
  if (fcntl(input.get(), F_ADD_SEALS, kRequiredSeals) < 0) return -1;
  Fd connection(socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0));
  if (connection.get() < 0) return -1;
  const struct timeval timeout{2, 0};
  if (setsockopt(connection.get(), SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) < 0 ||
      setsockopt(connection.get(), SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) return -1;
  struct sockaddr_un address{};
  address.sun_family = AF_UNIX;
  const size_t name_size = strnlen(config.socket_name, sizeof(address.sun_path));
  if (name_size == 0 || name_size > sizeof(address.sun_path) - 1) return Error(ENAMETOOLONG);
  memcpy(address.sun_path + 1, config.socket_name, name_size);
  if (connect(connection.get(), reinterpret_cast<struct sockaddr*>(&address),
              offsetof(struct sockaddr_un, sun_path) + 1 + name_size) < 0) return -1;
  struct ucred peer{};
  socklen_t peer_size = sizeof(peer);
  if (getsockopt(connection.get(), SOL_SOCKET, SO_PEERCRED, &peer, &peer_size) < 0) return -1;
  // An ancestor-pidns broker can legitimately be invisible as numeric PID 0
  // in the client's child pidns. The kernel PIDFD, not this number, binds it.
  if (peer_size != sizeof(peer) || peer.uid != 0 || peer.pid < 0) return Error(EPERM);
  int peer_pidfd = -1;
  socklen_t pidfd_size = sizeof(peer_pidfd);
  if (getsockopt(connection.get(), SOL_SOCKET, kPeerPidfd, &peer_pidfd, &pidfd_size) < 0) return -1;
  Fd peer_process(peer_pidfd);
  if (pidfd_size != sizeof(peer_pidfd) || peer_pidfd < 0) return Error(EPROTO);
  if (fcntl(peer_pidfd, F_SETFD, FD_CLOEXEC) < 0) return -1;
  // A nonprivileged App cannot read a root peer's namespaces: Linux requires
  // PTRACE_MODE_READ_FSCREDS for that ioctl. Instead, self's actual initial
  // userns was proved above; SO_PEERCRED uid 0 in that namespace is kernel
  // host-kuid-0 provenance. SO_PEERPIDFD pins the exact live service object.
  // The independently pinned root factory checks its own userns per request.
  // No ptrace/SELinux policy is relaxed to make this handshake succeed.
  struct pollfd peer_poll{peer_pidfd, POLLIN, 0};
  if (poll(&peer_poll, 1, 0) < 0) return -1;
  if (peer_poll.revents != 0) return Error(EPIPE);
  unsigned char request[kRequestBytes]{};
  memcpy(request, kRequestMagic, 8);
  PutU32(request + 8, kVersion);
  PutU32(request + 12, kCreateSnapshot);
  PutU64(request + 16, size);
  PutU32(request + 24, static_cast<uint32_t>(syscall(SYS_gettid)));
  PutU32(request + 28, static_cast<uint32_t>(status_flags));
  PutU32(request + 32, static_cast<uint32_t>(original_fd_flags));
  const int descriptors[2] = {source.get(), input.get()};
  alignas(struct cmsghdr) unsigned char send_control[CMSG_SPACE(sizeof(descriptors))]{};
  struct iovec request_iov{request, sizeof(request)};
  struct msghdr message{};
  message.msg_iov = &request_iov;
  message.msg_iovlen = 1;
  message.msg_control = send_control;
  message.msg_controllen = sizeof(send_control);
  struct cmsghdr* ancillary = CMSG_FIRSTHDR(&message);
  ancillary->cmsg_level = SOL_SOCKET;
  ancillary->cmsg_type = SCM_RIGHTS;
  ancillary->cmsg_len = CMSG_LEN(sizeof(descriptors));
  memcpy(CMSG_DATA(ancillary), descriptors, sizeof(descriptors));
  const ssize_t sent = sendmsg(connection.get(), &message, MSG_NOSIGNAL);
  if (sent < 0) return -1;
  if (sent != sizeof(request)) return Error(EPROTO);
  unsigned char reply[kReplyBytes];
  alignas(struct cmsghdr) unsigned char receive_control[CMSG_SPACE(sizeof(int) * 16)]{};
  struct iovec reply_iov{reply, sizeof(reply)};
  message = {};
  message.msg_iov = &reply_iov;
  message.msg_iovlen = 1;
  message.msg_control = receive_control;
  message.msg_controllen = sizeof(receive_control);
  const ssize_t received = recvmsg(connection.get(), &message, MSG_CMSG_CLOEXEC);
  if (received < 0) return -1;
  int received_fd = -1;
  size_t fd_count = 0;
  bool invalid_control = false;
  for (ancillary = CMSG_FIRSTHDR(&message); ancillary; ancillary = CMSG_NXTHDR(&message, ancillary)) {
    if (ancillary->cmsg_level != SOL_SOCKET || ancillary->cmsg_type != SCM_RIGHTS ||
        ancillary->cmsg_len < CMSG_LEN(0)) { invalid_control = true; continue; }
    const size_t count_bytes = ancillary->cmsg_len - CMSG_LEN(0);
    if (count_bytes % sizeof(int) != 0) invalid_control = true;
    for (size_t i = 0; i + sizeof(int) <= count_bytes; i += sizeof(int)) {
      int descriptor;
      memcpy(&descriptor, CMSG_DATA(ancillary) + i, sizeof(descriptor));
      if (fd_count++ == 0) received_fd = descriptor;
      else { Fd extra(descriptor); }
    }
  }
  Fd output(received_fd);
  if (invalid_control || (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0 ||
      received != sizeof(reply) || memcmp(reply, kReplyMagic, 8) != 0 ||
      GetU32(reply + 8) != kVersion || !AllZero(reply + 16, 16)) return Error(EPROTO);
  const uint32_t error = GetU32(reply + 12);
  if (error != 0) {
    if (fd_count != 0 || error > 4095) return Error(EPROTO);
    return Error(static_cast<int>(error));
  }
  if (fd_count != 1 || output.get() < 0) return Error(EPROTO);
  Origin origin;
  const Lookup lookup = QueryPinned(output.get(), config, &origin);
  if (lookup == Lookup::kError) return -1;
  if (lookup != Lookup::kVirtual || origin.words[kBackingSize] != size ||
      origin.words[kStatDevice] != static_cast<uint64_t>(source_info.st_dev) ||
      origin.words[kStatInode] != static_cast<uint64_t>(source_info.st_ino) ||
      origin.words[kOriginTgid] != static_cast<uint64_t>(getpid())) return Error(EPROTO);
  Fd output_directory(OpenOwnProcFdDirectory());
  if (output_directory.get() < 0) return -1;
  char output_path[sizeof(kSnapshotKernelPath)];
  const ssize_t output_path_size = ReadFdKernelPath(
      output_directory.get(), output.get(), output_path, sizeof(output_path));
  if (output_path_size < 0) return -1;
  if (output_path_size != sizeof(kSnapshotKernelPath) - 1 ||
      memcmp(output_path, kSnapshotKernelPath, sizeof(kSnapshotKernelPath) - 1) != 0) {
    return Error(EPROTO);
  }
  const int output_flags = fcntl(output.get(), F_GETFL);
  if (output_flags < 0) return -1;
  if (output_flags != status_flags) return Error(EPROTO);
  if (lseek(output.get(), 0, SEEK_CUR) != 0) return Error(EPROTO);
  if (fcntl(output.get(), F_GETFD) != FD_CLOEXEC) return Error(EPROTO);
  // Once the authenticated reply and immutable inode have been validated,
  // a normal factory exit does not invalidate the object. The PIDFD stayed
  // held throughout reception; no lifetime now depends on the service.
  return output.release();
}

namespace {

struct ReadlinkRequest {
  int dirfd;
  const char* copied_path;
  const Configuration* config;
  const path::CallerView* caller_view;
  char output[kMaxPathBytes]{};
  ssize_t output_size = -1;
};

int ReadOwnedLink(int caller_pidfd, void* context) {
  auto* request = static_cast<ReadlinkRequest*>(context);
  // Empty-path readlinkat selects the caller's O_PATH symlink itself. openat
  // with an empty path does not have that meaning and must not be substituted.
  Fd link(request->copied_path[0] == '\0'
              ? PidfdGetfd(caller_pidfd, request->dirfd)
              : path::Resolve(caller_pidfd, request->dirfd, request->copied_path,
                              *request->caller_view, false));
  if (link.get() < 0) return -1;
  struct stat link_info{};
  struct statfs link_fs{};
  if (::fstat(link.get(), &link_info) < 0 || ::fstatfs(link.get(), &link_fs) < 0) return -1;
  if (!S_ISLNK(link_info.st_mode)) return Error(EINVAL);
  if (static_cast<uint64_t>(link_fs.f_type) != PROC_SUPER_MAGIC) {
    request->output_size = ::readlinkat(link.get(), "", request->output, sizeof(request->output));
    return request->output_size < 0 ? -1 : 0;
  }
  Fd directory(OpenOwnProcFdDirectory());
  if (directory.get() < 0) return -1;
  struct stat directory_info{};
  if (::fstat(directory.get(), &directory_info) < 0) return -1;
  if (directory_info.st_dev != link_info.st_dev) return Error(EXDEV);
  char canonical[kMaxPathBytes];
  const ssize_t canonical_size = ReadFdKernelPath(directory.get(), link.get(), canonical, sizeof(canonical));
  if (canonical_size < 0) return -1;
  if (static_cast<size_t>(canonical_size) >= sizeof(canonical)) return Error(ENAMETOOLONG);
  int holder_tid, target_fd;
  if (!ParseProcFd(canonical, canonical_size, &holder_tid, &target_fd)) {
    // This projector handles proc fd links. Other proc links (for example an
    // ordinary memfd executable or map_files entry with the same display
    // string) retain the actual held-link result and need no target-open or
    // namespace permission merely because their text matched the filter.
    request->output_size = ::readlinkat(link.get(), "", request->output, sizeof(request->output));
    return request->output_size < 0 ? -1 : 0;
  }
  canonical[canonical_size] = '\0';
  // Follow the actual procfs pathname in its OWN numeric PID view, not a
  // pidfd_open number from a potentially different PID namespace. O_PATH
  // selects a kernel-held target without device/FIFO open side effects. Its
  // inode and Path remain pinned in this independent table throughout query.
  Fd target(::open(canonical, O_PATH | O_CLOEXEC));
  if (target.get() < 0) return -1;
  char live_link[kMaxPathBytes];
  if (::readlinkat(link.get(), "", live_link, sizeof(live_link)) < 0) return -1;
  // The held original proc inode must still resolve after selecting target;
  // this rules out death/reuse of the numeric task name. FD-number reuse is
  // allowed: the open above has already selected one actual target atomically.
  Origin origin;
  const Lookup lookup = QueryPinned(target.get(), *request->config, &origin);
  if (lookup == Lookup::kError) return -1;
  if (lookup == Lookup::kOrdinary) {
    request->output_size = ReadFdKernelPath(directory.get(), target.get(),
                                           request->output, sizeof(request->output));
    return request->output_size < 0 ? -1 : 0;
  }
  if (origin.words[kStatDevice] != static_cast<uint64_t>(link_info.st_dev)) return Error(EXDEV);
  memcpy(request->output, origin.path, origin.path_size);
  request->output_size = static_cast<ssize_t>(origin.path_size);
  return 0;
}

}  // namespace

bool Readlinkat(int dirfd, const char* caller_path, char* buffer, size_t size,
                const Configuration& config, ssize_t* result) {
  const int incoming_errno = errno;
  // Linux narrows bufsiz to a signed int, and rejects zero/negative values.
  const int32_t kernel_size = static_cast<int32_t>(static_cast<uint32_t>(size));
  if (kernel_size <= 0) { *result = Error(EINVAL); return true; }
  char copied_path[path::kPathBytes];
  if (path::CopyFromCaller(caller_path, copied_path) < 0) { *result = -1; return true; }
  char observed[kMaxPathBytes];
  const ssize_t observed_size = ::readlinkat(dirfd, copied_path, observed, sizeof(observed));
  if (observed_size < 0) { *result = -1; return true; }
  // Every factory-v1 memfd has this immutable kernel display string. This
  // single native observation can exclude a virtual snapshot and preserves
  // ordinary symlinks at full RLIMIT_NOFILE, without ANY helper descriptor or
  // owner creation. Matching bytes provide NO positive provenance evidence.
  // Do not repeat the ordinary syscall after classification: the path could
  // have been replaced by a virtual link between the two observations.
  const bool possible_snapshot = observed_size == sizeof(kSnapshotKernelPath) - 1 &&
      memcmp(observed, kSnapshotKernelPath, sizeof(kSnapshotKernelPath) - 1) == 0;
  const char* selected = observed;
  size_t selected_size = static_cast<size_t>(observed_size);
  path::CallerView caller_view;
  ReadlinkRequest request{dirfd, copied_path, &config, &caller_view};
  if (possible_snapshot) {
    if (path::CaptureCallerView(&caller_view) < 0 ||
        fd_owner::WithPrivateTable(ReadOwnedLink, &request) < 0) {
      *result = -1;
      return true;
    }
    selected = request.output;
    selected_size = static_cast<size_t>(request.output_size);
  }
  const size_t count = std::min(selected_size, static_cast<size_t>(kernel_size));
  if (CopyToCaller(selected, buffer, count) < 0) { *result = -1; return true; }
  *result = static_cast<ssize_t>(count);
  errno = incoming_errno;
  return true;
}

}  // namespace berberis::proc_maps_provenance
