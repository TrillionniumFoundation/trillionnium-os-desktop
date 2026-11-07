// SPDX-License-Identifier: Apache-2.0
// Actual socketpair transport controls. No Registry authorization, root service,
// application, namespace, credential change or platform policy is performed.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_admission.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <array>
#include <stdexcept>
#include <utility>

namespace role = droidloom::proc_maps_factory::role_v1;
namespace {
unsigned checks = 0, cases = 0;
void Check(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
  ++checks;
}
size_t Fds() {
  DIR* directory = opendir("/proc/self/fd");
  Check(directory != nullptr, "open own fd count");
  const int own = dirfd(directory); size_t result = 0;
  while (dirent* entry = readdir(directory)) {
    char* end = nullptr; const long value = strtol(entry->d_name, &end, 10);
    if (end != entry->d_name && !*end && value != own) ++result;
  }
  Check(closedir(directory) == 0, "close own fd count"); return result;
}
role::Request Request(role::Operation operation = role::Operation::kBegin) {
  role::Request value{}; value.operation = operation;
  for (size_t i = 0; i < role::kDigestBytes; ++i) {
    value.pair[i] = static_cast<unsigned char>(i + 1);
    if (operation != role::Operation::kBegin) value.token[i] = static_cast<unsigned char>(i + 33);
  }
  if (operation == role::Operation::kBegin || operation == role::Operation::kApprove) {
    value.uid_min = value.gid_min = 90000; value.uid_max = value.gid_max = 90031;
  }
  if (operation == role::Operation::kApprove) {
    value.child_pid_in_parent_namespace = 123; value.initial_uid = value.initial_gid = 61179;
  } else if (operation == role::Operation::kAttach) value.caller_tid = static_cast<uint32_t>(syscall(SYS_gettid));
  return value;
}
role::AdmissionReply Reply(role::Operation operation) {
  role::AdmissionReply value{}; value.request = Request(operation);
  value.state = operation == role::Operation::kBegin ? role::AdmissionState::kPending :
                operation == role::Operation::kApprove ? role::AdmissionState::kApproved : role::AdmissionState::kAttached;
  if (operation == role::Operation::kBegin) {
    value.visible_pid = 123;
    for (size_t i = 0; i < role::kDigestBytes; ++i) value.token[i] = static_cast<unsigned char>(i + 33);
  }
  return value;
}
role::AdmissionReply Sentinel() {
  role::AdmissionReply value{}; value.request.operation = role::Operation::kCreate;
  value.state = role::AdmissionState::kAttached; value.visible_pid = UINT32_MAX; return value;
}
bool Unchanged(const role::AdmissionReply& value) {
  return value.request.operation == role::Operation::kCreate &&
      value.state == role::AdmissionState::kAttached && value.visible_pid == UINT32_MAX;
}
struct Pair {
  role::Descriptor send, receive;
  Pair() {
    int sockets[2];
    Check(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, sockets) == 0,
          "real owned seqpacket pair");
    send.reset(sockets[0]); receive.reset(sockets[1]);
  }
};
void Send(int fd, const unsigned char* bytes, size_t size, int file, unsigned rights) {
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(3 * sizeof(int))]; } ancillary{};
  iovec vector{const_cast<unsigned char*>(bytes), size}; msghdr message{};
  message.msg_iov = &vector; message.msg_iovlen = 1;
  if (rights) {
    Check(rights <= 3, "bounded ancillary source");
    message.msg_control = ancillary.bytes; message.msg_controllen = CMSG_SPACE(rights * sizeof(int));
    auto* header = CMSG_FIRSTHDR(&message); header->cmsg_level = SOL_SOCKET;
    header->cmsg_type = SCM_RIGHTS; header->cmsg_len = CMSG_LEN(rights * sizeof(int));
    for (unsigned i = 0; i < rights; ++i) memcpy(CMSG_DATA(header) + i * sizeof(int), &file, sizeof(int));
  }
  Check(sendmsg(fd, &message, MSG_DONTWAIT | MSG_NOSIGNAL) == static_cast<ssize_t>(size),
        "send actual response datagram");
}
void Codec() {
  for (auto op : {role::Operation::kBegin, role::Operation::kApprove, role::Operation::kAttach}) {
    const auto source = Reply(op);
    std::array<unsigned char, role::kAdmissionReplyBytes> bytes{};
    Check(role::EncodeAdmissionReply(source, bytes.data()), "encode legal admission reply");
    role::AdmissionReply decoded{};
    Check(role::DecodeAdmissionReply(bytes.data(), bytes.size(), &decoded), "decode full legal admission reply");
    std::array<unsigned char, role::kAdmissionReplyBytes> after{};
    Check(role::EncodeAdmissionReply(decoded, after.data()) && bytes == after, "complete admission bytes round trip");
    for (size_t index : {size_t{0}, size_t{8}, size_t{12}, size_t{16}, size_t{20}, size_t{28}}) {
      auto bad = bytes; bad[index] ^= 0x80; decoded = Sentinel();
      Check(!role::DecodeAdmissionReply(bad.data(), bad.size(), &decoded) && Unchanged(decoded),
            "bad fixed header rejected without output mutation");
    }
    decoded = Sentinel();
    Check(!role::DecodeAdmissionReply(bytes.data(), bytes.size() - 1, &decoded) && Unchanged(decoded),
          "short frame rejected without mutation");
    auto invalid = source;
    invalid.state = op == role::Operation::kBegin ? role::AdmissionState::kAttached : role::AdmissionState::kPending;
    auto unchanged = bytes;
    Check(!role::EncodeAdmissionReply(invalid, bytes.data()) && unchanged == bytes,
          "pending challenge cannot be relabeled as permission");
    ++cases;
  }
}
enum class Variant { kPending, kApproved, kAttached, kRight, kExcess, kWrongEcho,
                     kShort, kLong, kPidfd, kCredentials, kInvalidExpected };
const char* Name(Variant value) {
  switch (value) {
    case Variant::kPending: return "pending_challenge_no_authority";
    case Variant::kApproved: return "root_approval_ack_no_descriptor";
    case Variant::kAttached: return "attached_ack_no_descriptor";
    case Variant::kRight: return "unexpected_right_closed";
    case Variant::kExcess: return "extra_rights_closed";
    case Variant::kWrongEcho: return "different_request_rejected";
    case Variant::kShort: return "short_datagram_rejected";
    case Variant::kLong: return "long_datagram_rejected";
    case Variant::kPidfd: return "automatic_pidfd_closed";
    case Variant::kCredentials: return "credentials_not_descriptors";
    case Variant::kInvalidExpected: return "invalid_expected_does_not_consume";
  }
  return "invalid";
}
void Transport(Variant which) {
  const size_t baseline = Fds();
  {
    Pair pair; role::Descriptor input(open("/dev/null", O_RDONLY | O_CLOEXEC));
    Check(input.get() >= 0, "open own transport-only file");
    auto op = which == Variant::kApproved ? role::Operation::kApprove :
              which == Variant::kAttached ? role::Operation::kAttach : role::Operation::kBegin;
    auto expected = Request(op); auto outgoing = Reply(op);
    const unsigned rights = which == Variant::kRight ? 1U : which == Variant::kExcess ? 3U : 0U;
    if (which == Variant::kWrongEcho) ++outgoing.request.uid_max;
    if (which == Variant::kPidfd || which == Variant::kCredentials) {
      const int one = 1;
      Check(setsockopt(pair.receive.get(), SOL_SOCKET,
          which == Variant::kPidfd ? 76 : SO_PASSCRED, &one, sizeof(one)) == 0,
          "actual kernel ancillary option");
    }
    unsigned char bytes[role::kAdmissionReplyBytes + 1]{};
    Check(role::EncodeAdmissionReply(outgoing, bytes), "encode actual transport frame");
    size_t size = role::kAdmissionReplyBytes;
    if (which == Variant::kShort) --size;
    if (which == Variant::kLong) ++size;
    Send(pair.send.get(), bytes, size, input.get(), rights);
    auto observed = Sentinel(); const size_t before = Fds();
    if (which == Variant::kInvalidExpected) {
      auto invalid = expected; memset(invalid.pair, 0, sizeof(invalid.pair)); errno = 0;
      Check(role::ReceiveAdmissionReply(pair.receive.get(), invalid, &observed) == -1 && errno == EINVAL &&
          Unchanged(observed) && Fds() == before, "invalid expected is atomic and nonconsuming");
    }
    errno = 0;
    const int result = role::ReceiveAdmissionReply(pair.receive.get(), expected, &observed);
    const bool pass = which == Variant::kPending || which == Variant::kApproved ||
                      which == Variant::kAttached || which == Variant::kInvalidExpected;
    if (pass) {
      unsigned char actual[role::kAdmissionReplyBytes];
      Check(result == 0 && role::EncodeAdmissionReply(observed, actual) && !memcmp(actual, bytes, sizeof(actual)),
            "complete exact challenge or acknowledgement received");
    } else Check(result == -1 && errno == EPROTO && Unchanged(observed), "bad reply rejected atomically");
    Check(fcntl(input.get(), F_GETFD) == FD_CLOEXEC && Fds() == before,
          "all received rights/pidfds closed without interpreting credential bytes as FDs");
    observed = Sentinel(); errno = 0;
    Check(role::ReceiveAdmissionReply(pair.receive.get(), expected, &observed) == -1 &&
        (errno == EAGAIN || errno == EWOULDBLOCK) && Unchanged(observed),
        "one frame consumed and empty socket leaves output unchanged");
  }
  Check(Fds() == baseline, "entire transport case owns and closes all descriptors");
  ++cases; printf("{\"case\":\"%s\",\"state\":\"PASS\"}\n", Name(which));
}
}
int main() {
  try {
    Codec();
    for (auto which : {Variant::kPending, Variant::kApproved, Variant::kAttached, Variant::kRight,
        Variant::kExcess, Variant::kWrongEcho, Variant::kShort, Variant::kLong,
        Variant::kPidfd, Variant::kCredentials, Variant::kInvalidExpected}) Transport(which);
    printf("{\"state\":\"PASS_ADMISSION_TRANSPORT_ONLY\",\"cases\":%u,\"assertions\":%u,"
           "\"root_authorization_executed\":false,\"snapshot_created\":false,\"platform_qualified\":false}\n", cases, checks);
    return 0;
  } catch (const std::exception& error) {
    fprintf(stderr, "admission transport failed: %s; errno=%d\n", error.what(), errno);
    return 1;
  }
}
