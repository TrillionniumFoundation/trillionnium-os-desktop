// SPDX-License-Identifier: Apache-2.0
#ifndef DROIDLOOM_PROC_MAPS_ROLE_AUTHORIZATION_H_
#define DROIDLOOM_PROC_MAPS_ROLE_AUTHORIZATION_H_

#include <stddef.h>
#include <stdint.h>
#include <sys/socket.h>

namespace droidloom::proc_maps_factory::role_v1 {

// Separate protocol. No old V2 frame, role label or caller-supplied credential
// record is accepted as authorization. The ordinary V2 factory is unchanged.
inline constexpr size_t kWireBytes = 160;
inline constexpr size_t kDigestBytes = 32;
inline constexpr size_t kMaximumGrants = 16;
inline constexpr uint64_t kPendingNanos = 2000000000ULL;
enum class Operation : uint32_t {
  kBegin = 1, kApprove = 2, kCreate = 3, kRelease = 4, kAttach = 5, kSuspend = 6
};

struct Request {
  Operation operation{};
  unsigned char pair[kDigestBytes]{};
  unsigned char token[kDigestBytes]{};
  uint32_t uid_min{}, uid_max{}, gid_min{}, gid_max{};
  uint32_t child_pid_in_parent_namespace{}, initial_uid{}, initial_gid{};
  uint32_t caller_tid{};
  uint64_t payload_size{};
  uint32_t source_flags{}, original_fd_flags{};
};

bool DecodeRequest(const unsigned char* bytes, size_t size, Request* result);
bool EncodeRequest(const Request& request, unsigned char output[kWireBytes]);

class Descriptor {
 public:
  Descriptor() = default;
  explicit Descriptor(int value) : value_(value) {}
  ~Descriptor();
  Descriptor(const Descriptor&) = delete;
  Descriptor& operator=(const Descriptor&) = delete;
  Descriptor(Descriptor&& other) noexcept;
  Descriptor& operator=(Descriptor&& other) noexcept;
  int get() const { return value_; }
  int release();
  void reset(int value = -1);
 private:
  int value_ = -1;
};

// Only Receive can fill the kernel sender evidence. No public constructor
// accepts a PID, a credential struct, or a user-supplied "verified" flag.
class Received {
 public:
  Received() = default;
  Received(const Received&) = delete;
  Received& operator=(const Received&) = delete;
  const Request& request() const { return request_; }
  int source_fd() const { return rights_[0].get(); }
  int payload_fd() const { return rights_[1].get(); }
 private:
  friend int Receive(int, Received*);
  friend class Registry;
  Request request_{};
  struct ucred credentials_{};
  Descriptor sender_pidfd_;
  Descriptor rights_[2];
  bool received_ = false;
};

// Use on the new inherited listener before any accept, then require the same
// options on accepted connections. This never binds/listens or changes V2.
int ConfigureIdentityReception(int socket, bool listener);
// One nonblocking recvmsg; EAGAIN is returned to the bounded owner event loop.
// All delivered known FD-bearing ancillary data is owned even on rejection.
int Receive(int connection, Received* result);

struct GrantHandle { uint32_t slot{}; uint64_t serial{}; };
struct Challenge {
  GrantHandle handle{};
  unsigned char token[kDigestBytes]{};
  uint32_t visible_pid{};
};
struct SnapshotAuthority {
  // Borrowed from a busy registry slot; valid only until FinishCreate/Close.
  int proc_fd = -1;
  int subject_pidfd = -1;
  int caller_proc_fd = -1;
  uint32_t visible_tgid{}, uid{}, gid{};
  uint32_t caller_tid{};
  uint64_t start_ticks{}, caller_start_ticks{};
};

class Registry {
 public:
  Registry() = default;
  ~Registry();
  Registry(const Registry&) = delete;
  Registry& operator=(const Registry&) = delete;

  // Root, initial user namespace, one thread, verified current proc view.
  // pair is a trusted immutable platform configuration, never the Begin claim.
  int Initialize(const unsigned char pair[kDigestBytes]);
  // Takes connection ownership only on success. Failure leaves it untouched.
  int Begin(Descriptor* connection, const Received& message, Challenge* output);
  // Root admin must be the subject's actual live parent in the same PID ns.
  // The trusted parent supplies the fork-return PID and original range/IDs.
  int Approve(int admin_connection, const Received& message);
  // An explicitly suspended grant can reattach only the same live PIDFD-bound
  // process in its unchanged context. A fork child or an unexpected lost
  // connection cannot use this as a new authorization.
  int Attach(Descriptor* connection, const Received& message, GrantHandle* output);
  // The owner event loop sends a grant acknowledgement only after this is true.
  int IsActive(GrantHandle handle);
  int Connection(GrantHandle handle) const;
  int AuthorizeCreate(GrantHandle handle, const Received& message, SnapshotAuthority* output);
  // MUST succeed before a role-created snapshot is sent. Clears busy state on
  // failure too; a changed/dead subject is closed and never silently renewed.
  int FinishCreate(GrantHandle handle);
  // Pin the supplied caller task inode/birth within this grant while paused.
  // The owner sends the acknowledgement, then calls Detach. Attach requires
  // this same live caller lease; no second root approval is accepted.
  int Suspend(GrantHandle handle, const Received& message);
  int Detach(GrantHandle handle);
  int Release(GrantHandle handle, const Received& message);
  int Sweep();
  // Revoke, including after a protocol/owner failure. A tombstone retains the
  // subject PIDFD until actual process death, so Begin cannot reauthorize it.
  void Close(GrantHandle handle);

 private:
  struct Impl;
  Impl* impl_ = nullptr;
};

}  // namespace droidloom::proc_maps_factory::role_v1
#endif
