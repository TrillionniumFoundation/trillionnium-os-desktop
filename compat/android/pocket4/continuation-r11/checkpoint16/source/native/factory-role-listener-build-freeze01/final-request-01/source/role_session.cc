// SPDX-License-Identifier: Apache-2.0
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_session.h"
#include "role_snapshot.h"
#include "factory_context.h"
#include "berberis/kernel_api/proc_maps_linux_compat.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/magic.h>
#include <memory>
#include <new>
#include <poll.h>
#include <sched.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include <utility>

namespace droidloom::proc_maps_factory::role_v1 {
namespace {
constexpr unsigned char kMagic[8] = {'D','P','4','R','P','L','Y','1'};
constexpr int kPeerPidfd = 77, kScmPidfd = 4;
#ifdef SO_PEERPIDFD
static_assert(kPeerPidfd == SO_PEERPIDFD);
#endif
#ifdef SCM_PIDFD
static_assert(kScmPidfd == SCM_PIDFD);
#endif
constexpr short kDead = POLLERR | POLLHUP | POLLNVAL | POLLRDHUP;
struct PidfdInfo {
  uint64_t mask{}, cgroup{};
  uint32_t pid{}, tgid{}, ppid{}, ruid{}, rgid{}, euid{}, egid{}, suid{}, sgid{}, fsuid{}, fsgid{}, spare{};
};
static_assert(sizeof(PidfdInfo) == 64 && offsetof(PidfdInfo, fsuid) == 52);
constexpr unsigned long kGetInfo = _IOWR(0xff, 11, PidfdInfo);
constexpr unsigned long kGetUserNs = _IO(0xff, 9), kGetPidNs = _IO(0xff, 5);
int Error(int value) { errno = value; return -1; }
uint32_t U32(const unsigned char* p) {
  return uint32_t{p[0]} | uint32_t{p[1]} << 8 | uint32_t{p[2]} << 16 | uint32_t{p[3]} << 24;
}
void Put32(unsigned char* p, uint32_t value) {
  for (unsigned i = 0; i < 4; ++i) p[i] = static_cast<unsigned char>(value >> (8 * i));
}
bool Supported(Operation operation) {
  return operation == Operation::kCreate || operation == Operation::kSuspend ||
         operation == Operation::kRelease;
}
bool ValidResponse(const Response& value) {
  if (!Supported(value.request.operation) || value.error > 4095) return false;
  return value.has_snapshot == (value.error == 0 && value.request.operation == Operation::kCreate);
}
uint64_t Now() {
  timespec t{};
  if (clock_gettime(CLOCK_MONOTONIC, &t) < 0 || t.tv_sec < 0 || t.tv_nsec < 0 ||
      t.tv_nsec >= 1000000000 ||
      static_cast<uint64_t>(t.tv_sec) > (UINT64_MAX - 999999999) / 1000000000) return 0;
  return static_cast<uint64_t>(t.tv_sec) * 1000000000 + static_cast<uint64_t>(t.tv_nsec);
}
int Option(int fd, int option, int* result) {
  socklen_t n = sizeof(*result);
  if (getsockopt(fd, SOL_SOCKET, option, result, &n) < 0) return -1;
  return n == sizeof(*result) ? 0 : Error(EPROTO);
}
int Socket(int fd) {
  int domain, type, accepting;
  if (Option(fd, SO_DOMAIN, &domain) < 0 || Option(fd, SO_TYPE, &type) < 0 ||
      Option(fd, SO_ACCEPTCONN, &accepting) < 0) return -1;
  const int status = fcntl(fd, F_GETFL);
  if (status < 0) return -1;
  const int flags = fcntl(fd, F_GETFD);
  if (flags < 0) return -1;
  return domain == AF_UNIX && type == SOCK_SEQPACKET && !accepting &&
                 (status & O_NONBLOCK) && (flags & FD_CLOEXEC) ? 0 : Error(EPROTO);
}
int Alive(int fd) {
  pollfd p{fd, POLLIN, 0};
  const int count = poll(&p, 1, 0);
  if (count < 0) return -1;
  return count == 0 && p.revents == 0 ? 0 : Error(EPIPE);
}
int RootInfo(int fd, uint32_t expected_pid) {
  const int flags = fcntl(fd, F_GETFD);
  if (flags < 0) return -1;
  if (!(flags & FD_CLOEXEC)) return Error(EPROTO);
  if (Alive(fd) < 0) return -1;
  PidfdInfo value{}; value.mask = 3;
  if (ioctl(fd, kGetInfo, &value) < 0) return -1;
  if ((value.mask & 3) != 3 || value.pid != expected_pid || !value.pid ||
      value.pid > INT_MAX || value.pid != value.tgid || value.ruid || value.rgid ||
      value.euid || value.egid || value.suid || value.sgid || value.fsuid || value.fsgid) return Error(EPERM);
  return Alive(fd);
}
int Namespace(int fd, int type, struct stat* identity) {
  struct statfs fs{};
  if (fstat(fd, identity) < 0 || fstatfs(fd, &fs) < 0) return -1;
  const int actual = ioctl(fd, NS_GET_NSTYPE, 0UL);
  if (actual < 0) return -1;
  return actual == type && static_cast<uint64_t>(fs.f_type) == NSFS_MAGIC ? 0 : Error(EXDEV);
}
int Namespaces(int pidfd, struct stat* pidns) {
  Descriptor user(ioctl(pidfd, kGetUserNs, 0UL));
  if (user.get() < 0) return -1;
  Descriptor pid(ioctl(pidfd, kGetPidNs, 0UL));
  struct stat identity{};
  if (pid.get() < 0 || Namespace(user.get(), CLONE_NEWUSER, &identity) < 0 ||
      Namespace(pid.get(), CLONE_NEWPID, pidns) < 0) return -1;
  return static_cast<uint64_t>(identity.st_dev) == 5 &&
                 static_cast<uint64_t>(identity.st_ino) == 4026531837ULL ? 0 : Error(EXDEV);
}
int CloseError(Registry& registry, GrantHandle handle, int error) {
  registry.Close(handle);
  return Error(error > 0 && error <= 4095 ? error : EIO);
}
int TimeRemaining(uint64_t deadline, uint64_t* previous) {
  const uint64_t now = Now();
  if (!now || now < *previous) return Error(EIO);
  *previous = now;
  if (now >= deadline) return Error(ETIMEDOUT);
  return 0;
}
int Wait(Registry& registry, GrantHandle handle, const OwnerLease& owner, int connection,
         short events, uint64_t deadline, uint64_t* previous, bool require_active) {
  for (;;) {
    if (TimeRemaining(deadline, previous) < 0 || owner.Verify() < 0 || registry.Sweep() < 0) return -1;
    if (require_active && registry.IsActive(handle) < 0) return -1;
    const uint64_t remaining = deadline - *previous;
    int timeout = static_cast<int>((remaining + 999999) / 1000000);
    if (timeout > 100) timeout = 100;
    const int control = owner.control_fd();
    if (control < 0) return -1;
    const int pidfd = owner.owner_pidfd();
    if (pidfd < 0) return -1;
    pollfd items[3] = {
        {connection, static_cast<short>(events | POLLRDHUP), 0},
        {control, static_cast<short>(POLLIN | POLLRDHUP), 0},
        {pidfd, POLLIN, 0}};
    const int count = poll(items, 3, timeout);
    if (count < 0) { if (errno == EINTR) continue; return -1; }
    if (items[1].revents || items[2].revents) return Error(ECANCELED);
    if (items[0].revents & kDead) return Error(EPIPE);
    if (items[0].revents & events) {
      if (TimeRemaining(deadline, previous) < 0 || owner.Verify() < 0 || registry.Sweep() < 0) return -1;
      return require_active ? registry.IsActive(handle) : 0;
    }
  }
}
int Send(Registry& registry, GrantHandle handle, const OwnerLease& owner, int connection,
         const Response& response, int snapshot, uint64_t deadline, uint64_t* previous,
         bool require_active) {
  unsigned char bytes[kResponseBytes];
  if (!EncodeResponse(response, bytes) || response.has_snapshot != (snapshot >= 0)) return Error(EINVAL);
  for (;;) {
    if (Wait(registry, handle, owner, connection, POLLOUT, deadline, previous, require_active) < 0) return -1;
    union { cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(int))]; } ancillary{};
    iovec vector{bytes, sizeof(bytes)}; msghdr message{};
    message.msg_iov = &vector; message.msg_iovlen = 1;
    if (snapshot >= 0) {
      message.msg_control = ancillary.bytes; message.msg_controllen = sizeof(ancillary.bytes);
      cmsghdr* header = CMSG_FIRSTHDR(&message);
      header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
      header->cmsg_len = CMSG_LEN(sizeof(snapshot)); memcpy(CMSG_DATA(header), &snapshot, sizeof(snapshot));
    }
    const ssize_t count = sendmsg(connection, &message, MSG_DONTWAIT | MSG_NOSIGNAL);
    if (count < 0) { if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) continue; return -1; }
    return count == sizeof(bytes) ? 0 : Error(EPROTO);
  }
}
}  // namespace

bool EncodeResponse(const Response& value, unsigned char output[kResponseBytes]) {
  if (!output || !ValidResponse(value)) return false;
  unsigned char bytes[kResponseBytes]{};
  if (!EncodeRequest(value.request, bytes + 32)) return false;
  memcpy(bytes, kMagic, sizeof(kMagic)); Put32(bytes + 8, 1); Put32(bytes + 12, sizeof(bytes));
  Put32(bytes + 16, value.error); Put32(bytes + 20, value.has_snapshot ? 1 : 0);
  memcpy(output, bytes, sizeof(bytes)); return true;
}
bool DecodeResponse(const unsigned char* bytes, size_t size, Response* result) {
  if (!bytes || !result || size != kResponseBytes || memcmp(bytes, kMagic, sizeof(kMagic)) ||
      U32(bytes + 8) != 1 || U32(bytes + 12) != size || U32(bytes + 20) > 1) return false;
  for (size_t i = 24; i < 32; ++i) if (bytes[i]) return false;
  Response value{};
  if (!DecodeRequest(bytes + 32, kWireBytes, &value.request)) return false;
  value.error = U32(bytes + 16); value.has_snapshot = U32(bytes + 20) == 1;
  if (!ValidResponse(value)) return false;
  *result = value; return true;
}
int ReceiveResponse(int connection, const Request& expected, Response* response, Descriptor* snapshot) {
  if (!response || !snapshot || snapshot->get() >= 0 || !Supported(expected.operation)) return Error(EINVAL);
  unsigned char request[kWireBytes];
  if (!EncodeRequest(expected, request)) return Error(EINVAL);
  if (Socket(connection) < 0) return -1;
  unsigned char bytes[kResponseBytes]{};
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(253 * sizeof(int)) +
      CMSG_SPACE(sizeof(ucred)) + CMSG_SPACE(sizeof(int))]; } ancillary{};
  iovec vector{bytes, sizeof(bytes)}; msghdr message{};
  message.msg_iov = &vector; message.msg_iovlen = 1;
  message.msg_control = ancillary.bytes; message.msg_controllen = sizeof(ancillary.bytes);
  const ssize_t count = recvmsg(connection, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC | MSG_TRUNC);
  if (count < 0) return -1;
  bool valid = count == sizeof(bytes) && !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC));
  size_t rights = 0, rights_headers = 0; Descriptor output;
  for (cmsghdr* header = CMSG_FIRSTHDR(&message); header; header = CMSG_NXTHDR(&message, header)) {
    const size_t offset = reinterpret_cast<unsigned char*>(header) - ancillary.bytes;
    if (offset > message.msg_controllen || header->cmsg_len < CMSG_LEN(0) ||
        header->cmsg_len > message.msg_controllen - offset) {
      valid = false; break;
    }
    const size_t size = header->cmsg_len - CMSG_LEN(0);
    if (header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_RIGHTS) {
      ++rights_headers; if (size % sizeof(int)) valid = false;
      for (size_t i = 0; i < size / sizeof(int); ++i) {
        int fd; memcpy(&fd, CMSG_DATA(header) + i * sizeof(int), sizeof(fd)); Descriptor owned(fd);
        if (!rights) output = std::move(owned);
        ++rights;
      }
    } else if (header->cmsg_level == SOL_SOCKET && header->cmsg_type == kScmPidfd) {
      // This is an actual received descriptor even though this reply protocol
      // does not accept the ancillary class. Never leak it on rejection.
      for (size_t i = 0; i < size / sizeof(int); ++i) {
        int fd; memcpy(&fd, CMSG_DATA(header) + i * sizeof(int), sizeof(fd)); Descriptor owned(fd);
      }
      valid = false;
    } else { valid = false; }  // Credentials/unknown non-FD bytes are not FDs.
  }
  Response value{};
  if (!valid || !DecodeResponse(bytes, sizeof(bytes), &value) ||
      memcmp(bytes + 32, request, sizeof(request)) ||
      rights != (value.has_snapshot ? 1U : 0U) || rights_headers != (value.has_snapshot ? 1U : 0U)) return Error(EPROTO);
  if (value.has_snapshot) {
    const int flags = fcntl(output.get(), F_GETFD);
    if (flags < 0) return -1;
    if (!(flags & FD_CLOEXEC)) return Error(EPROTO);
  }
  *response = value; *snapshot = std::move(output); return 0;
}

struct OwnerLease::Impl {
  Descriptor control, owner, self, proc;
  uint32_t service_pid{}, owner_pid{};
  uint64_t pidns_device{}, pidns_inode{};
  int OwnThread() const {
    if (!service_pid || getpid() != static_cast<pid_t>(service_pid) ||
        syscall(SYS_gettid) != service_pid) return Error(ESHUTDOWN);
    // The original PIDFD alone identifies its owner, not this caller. Resolve
    // the current thread in the owner's held, verified proc view so an equal
    // numeric PID/TID in a foreign PID namespace cannot delete shared state.
    if (Alive(self.get()) < 0) return -1;
    Descriptor status(openat(proc.get(), "thread-self/status", O_RDONLY | O_CLOEXEC));
    if (status.get() < 0) return -1;
    char text[16385]; size_t used = 0;
    while (used < sizeof(text)) {
      const ssize_t count = read(status.get(), text + used, sizeof(text) - used);
      if (count < 0) { if (errno == EINTR) continue; return -1; }
      if (!count) break;
      used += static_cast<size_t>(count);
    }
    ProcessStatus current;
    if (!ParseStatus(text, used, &current)) return Error(EBADMSG);
    if (current.tgid != service_pid || current.tgid_depth != 1 || current.pid_depth != 1 ||
        current.namespace_tgids[0] != service_pid || current.namespace_pids[0] != service_pid) {
      return Error(ESHUTDOWN);
    }
    return Alive(self.get());
  }
};

OwnerLease::~OwnerLease() {
  const int before = errno;
  if (impl_ && impl_->OwnThread() == 0) delete impl_;
  errno = before;
}
int OwnerLease::control_fd() const {
  if (!impl_) return Error(ESHUTDOWN);
  return impl_->OwnThread() == 0 ? impl_->control.get() : -1;
}
int OwnerLease::owner_pidfd() const {
  if (!impl_) return Error(ESHUTDOWN);
  return impl_->OwnThread() == 0 ? impl_->owner.get() : -1;
}
int OwnerLease::Initialize(Descriptor* control) {
  if (!control || impl_ || control->get() < 3 || syscall(SYS_gettid) != getpid()) return Error(EINVAL);
  if (Socket(control->get()) < 0) return -1;
  ucred peer{}; socklen_t n = sizeof(peer);
  if (getsockopt(control->get(), SOL_SOCKET, SO_PEERCRED, &peer, &n) < 0) return -1;
  if (n != sizeof(peer) || peer.uid || peer.gid || peer.pid <= 0 || peer.pid == getpid()) return Error(EPERM);
  std::unique_ptr<Impl> value(new(std::nothrow) Impl);
  if (!value) return Error(ENOMEM);
  value->service_pid = static_cast<uint32_t>(getpid());
  value->owner_pid = static_cast<uint32_t>(peer.pid);
  int owner = -1; if (Option(control->get(), kPeerPidfd, &owner) < 0) return -1;
  value->owner.reset(owner);
  value->self.reset(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(getpid()), 0UL)));
  struct stat self_ns{}, owner_ns{};
  if (value->self.get() < 0 || RootInfo(value->self.get(), value->service_pid) < 0 ||
      RootInfo(value->owner.get(), value->owner_pid) < 0 || Namespaces(value->self.get(), &self_ns) < 0 ||
      Namespaces(value->owner.get(), &owner_ns) < 0) return -1;
  if (self_ns.st_dev != owner_ns.st_dev || self_ns.st_ino != owner_ns.st_ino) return Error(EXDEV);
  value->pidns_device = self_ns.st_dev; value->pidns_inode = self_ns.st_ino;
  value->proc.reset(open("/proc", O_PATH | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
  struct statfs procfs{}; struct stat proc_identity{}, proc_pidns{};
  if (value->proc.get() < 0 || fstat(value->proc.get(), &proc_identity) < 0 ||
      fstatfs(value->proc.get(), &procfs) < 0) return -1;
  if (!S_ISDIR(proc_identity.st_mode) || static_cast<uint64_t>(procfs.f_type) != PROC_SUPER_MAGIC) return Error(EXDEV);
  Descriptor pidns(openat(value->proc.get(), "1/ns/pid", O_RDONLY | O_CLOEXEC));
  if (pidns.get() < 0 || Namespace(pidns.get(), CLONE_NEWPID, &proc_pidns) < 0) return -1;
  if (proc_pidns.st_dev != self_ns.st_dev || proc_pidns.st_ino != self_ns.st_ino) return Error(EXDEV);
  if (value->OwnThread() < 0) return -1;
  pollfd p{control->get(), static_cast<short>(POLLIN | POLLRDHUP), 0};
  const int polled = poll(&p, 1, 0);
  if (polled < 0) return -1;
  if (polled || p.revents) return Error(ECANCELED);
  value->control = std::move(*control); impl_ = value.release(); return 0;
}
int OwnerLease::Verify() const {
  if (!impl_) return Error(ESHUTDOWN);
  if (impl_->OwnThread() < 0) return -1;
  const Impl& value = *impl_;
  if (value.control.get() < 0) return Error(ESHUTDOWN);
  if (Socket(value.control.get()) < 0 || RootInfo(value.self.get(), value.service_pid) < 0 ||
      RootInfo(value.owner.get(), value.owner_pid) < 0) return -1;
  struct stat self_ns{}, owner_ns{};
  if (Namespaces(value.self.get(), &self_ns) < 0 || Namespaces(value.owner.get(), &owner_ns) < 0) return -1;
  if (self_ns.st_dev != value.pidns_device || self_ns.st_ino != value.pidns_inode ||
      owner_ns.st_dev != value.pidns_device || owner_ns.st_ino != value.pidns_inode) return Error(EXDEV);
  pollfd p{value.control.get(), static_cast<short>(POLLIN | POLLRDHUP), 0};
  const int count = poll(&p, 1, 0);
  if (count < 0) return -1;
  return count == 0 && p.revents == 0 ? 0 : Error(ECANCELED);
}

int DispatchOne(Registry& registry, GrantHandle handle, const OwnerLease& owner, DispatchResult* result) {
  if (!result) return Error(EINVAL);
  const uint64_t start = Now();
  if (!start || start > UINT64_MAX - kSessionRequestNanos) return CloseError(registry, handle, EIO);
  const uint64_t deadline = start + kSessionRequestNanos; uint64_t previous = start;
  if (registry.IsActive(handle) < 0 || owner.Verify() < 0) return CloseError(registry, handle, errno);
  const int connection = registry.Connection(handle);
  if (connection < 0) return CloseError(registry, handle, errno);
  const int control = owner.control_fd();
  if (control < 0) return CloseError(registry, handle, errno);
  const int pidfd = owner.owner_pidfd();
  if (pidfd < 0) return CloseError(registry, handle, errno);
  if (connection == control || connection == pidfd) return CloseError(registry, handle, EINVAL);
  Received received;
  for (;;) {
    if (Wait(registry, handle, owner, connection, POLLIN, deadline, &previous, true) < 0) return CloseError(registry, handle, errno);
    if (Receive(connection, &received) == 0) break;
    if (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK) return CloseError(registry, handle, errno);
  }
  const Request& request = received.request();
  if (!Supported(request.operation)) return CloseError(registry, handle, EPROTO);
  Response response{}; response.request = request;
  DispatchResult completed{}; completed.operation = request.operation;
  Descriptor output, release_transport;
  int send_connection = connection;
  bool active_during_send = true;
  if (request.operation == Operation::kCreate) {
    output.reset(CreateAuthorizedSnapshotBefore(registry, handle, received, deadline));
    const int creation_error = errno;
    if (output.get() < 0) response.error = creation_error > 0 && creation_error <= 4095 ? creation_error : EIO;
    // A maker error can finish normally; an authorization/finish failure can
    // instead revoke the slot. Never use a stale numeric connection afterward.
    if (registry.IsActive(handle) < 0) return CloseError(registry, handle, output.get() < 0 ? creation_error : errno);
    const int current_connection = registry.Connection(handle);
    if (current_connection < 0) return CloseError(registry, handle, output.get() < 0 ? creation_error : errno);
    if (current_connection != connection) return CloseError(registry, handle, ESTALE);
    response.has_snapshot = output.get() >= 0;
  } else if (request.operation == Operation::kSuspend) {
    if (registry.Suspend(handle, received) < 0) return CloseError(registry, handle, errno);
    active_during_send = false;
  } else {
    // Release revokes/closes the registry's connection. Hold only this OFD long
    // enough to report that completed transition; it never renews authority.
    release_transport.reset(fcntl(connection, F_DUPFD_CLOEXEC, 0));
    if (release_transport.get() < 0 || registry.Release(handle, received) < 0) return CloseError(registry, handle, errno);
    send_connection = release_transport.get(); active_during_send = false;
  }
  if (Send(registry, handle, owner, send_connection, response, output.get(), deadline, &previous, active_during_send) < 0) {
    return CloseError(registry, handle, errno);
  }
  completed.operation_error = response.error; completed.snapshot_published = response.has_snapshot;
  if (request.operation == Operation::kSuspend) {
    if (TimeRemaining(deadline, &previous) < 0 || owner.Verify() < 0 || registry.Detach(handle) < 0) {
      return CloseError(registry, handle, errno);
    }
    completed.state = DispatchState::kDetached;
  } else if (request.operation == Operation::kRelease) {
    completed.state = DispatchState::kReleased;
  }
  *result = completed; return 0;
}
}  // namespace droidloom::proc_maps_factory::role_v1
