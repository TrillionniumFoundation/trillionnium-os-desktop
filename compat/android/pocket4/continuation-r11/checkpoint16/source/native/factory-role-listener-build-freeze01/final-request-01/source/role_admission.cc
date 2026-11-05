// SPDX-License-Identifier: Apache-2.0
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_admission.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <string.h>
#include <time.h>

namespace droidloom::proc_maps_factory::role_v1 {
namespace {
constexpr unsigned char kMagic[8] = {'D','P','4','A','D','M','0','1'};
constexpr int kPassPidfd = 76, kScmPidfd = 4;
#ifdef SO_PASSPIDFD
static_assert(kPassPidfd == SO_PASSPIDFD);
#endif
#ifdef SCM_PIDFD
static_assert(kScmPidfd == SCM_PIDFD);
#endif
constexpr short kDead = POLLERR | POLLHUP | POLLNVAL | POLLRDHUP;
int Error(int value) { errno = value; return -1; }
uint32_t U32(const unsigned char* p) {
  return uint32_t{p[0]} | uint32_t{p[1]} << 8 | uint32_t{p[2]} << 16 | uint32_t{p[3]} << 24;
}
void Put32(unsigned char* p, uint32_t value) {
  for (unsigned i = 0; i < 4; ++i) p[i] = static_cast<unsigned char>(value >> (i * 8));
}
bool Nonzero(const unsigned char* p, size_t size) {
  unsigned value = 0; for (size_t i = 0; i < size; ++i) value |= p[i]; return value != 0;
}
bool Supported(Operation operation) {
  return operation == Operation::kBegin || operation == Operation::kApprove || operation == Operation::kAttach;
}
bool Valid(const AdmissionReply& value) {
  if (!Supported(value.request.operation)) return false;
  if (value.request.operation == Operation::kBegin) {
    return value.state == AdmissionState::kPending && value.visible_pid && value.visible_pid <= INT_MAX &&
           Nonzero(value.token, sizeof(value.token));
  }
  return !value.visible_pid && !Nonzero(value.token, sizeof(value.token)) &&
         value.state == (value.request.operation == Operation::kApprove ?
                         AdmissionState::kApproved : AdmissionState::kAttached);
}
uint64_t Now() {
  timespec t{};
  if (clock_gettime(CLOCK_MONOTONIC, &t) < 0 || t.tv_sec < 0 || t.tv_nsec < 0 || t.tv_nsec >= 1000000000 ||
      static_cast<uint64_t>(t.tv_sec) > (UINT64_MAX - 999999999) / 1000000000) return 0;
  return static_cast<uint64_t>(t.tv_sec) * 1000000000 + static_cast<uint64_t>(t.tv_nsec);
}
int Option(int fd, int name, int* value) {
  socklen_t size = sizeof(*value);
  if (getsockopt(fd, SOL_SOCKET, name, value, &size) < 0) return -1;
  return size == sizeof(*value) ? 0 : Error(EPROTO);
}
int Socket(int fd, bool listener, bool identity) {
  int domain, type, accepting, credentials, pidfd;
  if (Option(fd, SO_DOMAIN, &domain) < 0 || Option(fd, SO_TYPE, &type) < 0 ||
      Option(fd, SO_ACCEPTCONN, &accepting) < 0) return -1;
  const int status = fcntl(fd, F_GETFL), flags = fcntl(fd, F_GETFD);
  if (status < 0 || flags < 0) return -1;
  if (domain != AF_UNIX || type != SOCK_SEQPACKET || accepting != (listener ? 1 : 0) ||
      !(status & O_NONBLOCK) || !(flags & FD_CLOEXEC)) return Error(EPROTO);
  if (identity && (Option(fd, SO_PASSCRED, &credentials) < 0 || Option(fd, kPassPidfd, &pidfd) < 0)) return -1;
  return !identity || (credentials == 1 && pidfd == 1) ? 0 : Error(EPROTO);
}
int Check(Registry& registry, const OwnerLease& owner, uint64_t deadline, uint64_t* previous,
          const GrantHandle* handle, bool active, int role_connection) {
  const uint64_t now = Now();
  if (!now || now < *previous) return Error(EIO);
  *previous = now;
  if (now >= deadline) return Error(ETIMEDOUT);
  if (owner.Verify() < 0 || registry.Sweep() < 0) return -1;
  if (handle) {
    if (active && registry.IsActive(*handle) < 0) return -1;
    const int current = registry.Connection(*handle);
    if (current < 0) return -1;
    if (current != role_connection) return Error(ESTALE);
  }
  return 0;
}
int Wait(Registry& registry, const OwnerLease& owner, int connection, short events,
         uint64_t deadline, uint64_t* previous, const GrantHandle* handle = nullptr,
         bool active = false, int role_connection = -1) {
  for (;;) {
    if (Check(registry, owner, deadline, previous, handle, active, role_connection) < 0) return -1;
    const int control = owner.control_fd();
    if (control < 0) return -1;
    const int pidfd = owner.owner_pidfd();
    if (pidfd < 0) return -1;
    int timeout = static_cast<int>((deadline - *previous + 999999) / 1000000);
    if (timeout > 100) timeout = 100;
    pollfd items[3] = {{connection, static_cast<short>(events | POLLRDHUP), 0},
                      {control, static_cast<short>(POLLIN | POLLRDHUP), 0}, {pidfd, POLLIN, 0}};
    const int count = poll(items, 3, timeout);
    if (count < 0) { if (errno == EINTR) continue; return -1; }
    if (items[1].revents || items[2].revents) return Error(ECANCELED);
    if (items[0].revents & kDead) return Error(EPIPE);
    if (items[0].revents & events) return Check(registry, owner, deadline, previous, handle, active, role_connection);
  }
}
int CloseError(Registry& registry, const GrantHandle* handle, int error) {
  if (handle) registry.Close(*handle);
  return Error(error > 0 && error <= 4095 ? error : EIO);
}
}  // namespace

bool EncodeAdmissionReply(const AdmissionReply& value, unsigned char output[kAdmissionReplyBytes]) {
  if (!output || !Valid(value)) return false;
  unsigned char bytes[kAdmissionReplyBytes]{};
  if (!EncodeRequest(value.request, bytes + 64)) return false;
  memcpy(bytes, kMagic, sizeof(kMagic)); Put32(bytes + 8, 1); Put32(bytes + 12, sizeof(bytes));
  Put32(bytes + 16, static_cast<uint32_t>(value.state)); Put32(bytes + 24, value.visible_pid);
  memcpy(bytes + 32, value.token, sizeof(value.token)); memcpy(output, bytes, sizeof(bytes)); return true;
}
bool DecodeAdmissionReply(const unsigned char* bytes, size_t size, AdmissionReply* output) {
  if (!bytes || !output || size != kAdmissionReplyBytes || memcmp(bytes, kMagic, sizeof(kMagic)) ||
      U32(bytes + 8) != 1 || U32(bytes + 12) != size || U32(bytes + 20) || U32(bytes + 28)) return false;
  AdmissionReply value{};
  value.state = static_cast<AdmissionState>(U32(bytes + 16)); value.visible_pid = U32(bytes + 24);
  memcpy(value.token, bytes + 32, sizeof(value.token));
  if (!DecodeRequest(bytes + 64, kWireBytes, &value.request) || !Valid(value)) return false;
  *output = value; return true;
}
int ReceiveAdmissionReply(int connection, const Request& expected, AdmissionReply* output) {
  if (!output || !Supported(expected.operation)) return Error(EINVAL);
  unsigned char original[kWireBytes];
  if (!EncodeRequest(expected, original)) return Error(EINVAL);
  if (Socket(connection, false, false) < 0) return -1;
  unsigned char bytes[kAdmissionReplyBytes]{};
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(253 * sizeof(int)) +
      CMSG_SPACE(sizeof(ucred)) + CMSG_SPACE(sizeof(int))]; } ancillary{};
  iovec vector{bytes, sizeof(bytes)}; msghdr message{};
  message.msg_iov = &vector; message.msg_iovlen = 1;
  message.msg_control = ancillary.bytes; message.msg_controllen = sizeof(ancillary.bytes);
  const ssize_t count = recvmsg(connection, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC | MSG_TRUNC);
  if (count < 0) return -1;
  bool valid = count == sizeof(bytes) && !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC));
  for (cmsghdr* header = CMSG_FIRSTHDR(&message); header; header = CMSG_NXTHDR(&message, header)) {
    valid = false;  // This protocol never returns a descriptor or credentials.
    const size_t offset = reinterpret_cast<unsigned char*>(header) - ancillary.bytes;
    if (offset > message.msg_controllen || header->cmsg_len < CMSG_LEN(0) ||
        header->cmsg_len > message.msg_controllen - offset) break;
    const size_t size = header->cmsg_len - CMSG_LEN(0);
    if (header->cmsg_level == SOL_SOCKET && (header->cmsg_type == SCM_RIGHTS || header->cmsg_type == kScmPidfd)) {
      for (size_t i = 0; i < size / sizeof(int); ++i) {
        int fd; memcpy(&fd, CMSG_DATA(header) + i * sizeof(int), sizeof(fd)); Descriptor owned(fd);
      }
    }
  }
  AdmissionReply value{};
  if (!valid || !DecodeAdmissionReply(bytes, sizeof(bytes), &value) || memcmp(bytes + 64, original, sizeof(original))) return Error(EPROTO);
  *output = value; return 0;
}

int AdmitOne(Registry& registry, const OwnerLease& owner, int listener, Admission* result) {
  if (!result || listener < 3) return Error(EINVAL);
  const uint64_t now = Now();
  if (!now || now > UINT64_MAX - kSessionRequestNanos) return Error(EIO);
  const uint64_t deadline = now + kSessionRequestNanos; uint64_t previous = now;
  if (owner.Verify() < 0 || registry.Sweep() < 0 || Socket(listener, true, true) < 0) return -1;
  Descriptor connection;
  for (;;) {
    if (Wait(registry, owner, listener, POLLIN, deadline, &previous) < 0) return -1;
    const int accepted = accept4(listener, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (accepted >= 0) { connection.reset(accepted); break; }
    if (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK) return -1;
  }
  if (Socket(connection.get(), false, true) < 0) return -1;
  Received message;
  for (;;) {
    if (Wait(registry, owner, connection.get(), POLLIN, deadline, &previous) < 0) return -1;
    if (Receive(connection.get(), &message) == 0) break;
    if (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK) return -1;
  }
  const auto& request = message.request();
  Admission value{}; value.reply.request = request;
  bool active = false;
  if (request.operation == Operation::kBegin) {
    Challenge challenge;
    if (registry.Begin(&connection, message, &challenge) < 0) return -1;
    value.handle = challenge.handle; value.reply.state = AdmissionState::kPending;
    value.reply.visible_pid = challenge.visible_pid; memcpy(value.reply.token, challenge.token, sizeof(challenge.token));
  } else if (request.operation == Operation::kApprove) {
    if (registry.ApproveAndIdentify(connection.get(), message, &value.handle) < 0) return -1;
    value.reply.state = AdmissionState::kApproved; active = true;
  } else if (request.operation == Operation::kAttach) {
    if (registry.Attach(&connection, message, &value.handle) < 0) return -1;
    value.reply.state = AdmissionState::kAttached; active = true;
  } else return Error(EPROTO);
  const int role_connection = registry.Connection(value.handle);
  if (role_connection < 0) return CloseError(registry, &value.handle, errno);
  const int reply_connection = connection.get() >= 0 ? connection.get() : role_connection;
  unsigned char bytes[kAdmissionReplyBytes];
  if (!EncodeAdmissionReply(value.reply, bytes)) return CloseError(registry, &value.handle, EPROTO);
  for (;;) {
    if (Wait(registry, owner, reply_connection, POLLOUT, deadline, &previous,
             &value.handle, active, role_connection) < 0) return CloseError(registry, &value.handle, errno);
    const ssize_t count = send(reply_connection, bytes, sizeof(bytes), MSG_DONTWAIT | MSG_NOSIGNAL);
    if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
    if (count != sizeof(bytes)) return CloseError(registry, &value.handle, count < 0 ? errno : EPROTO);
    break;
  }
  *result = value; return 0;
}
}  // namespace droidloom::proc_maps_factory::role_v1
