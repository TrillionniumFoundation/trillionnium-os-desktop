// SPDX-License-Identifier: Apache-2.0
// Actual socketpair transport controls. No Registry authorization, root service,
// application, namespace, credential change or platform policy is performed.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_session.h"
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
role::Request Request(role::Operation operation = role::Operation::kCreate) {
  role::Request value{}; value.operation = operation;
  for (size_t i = 0; i < role::kDigestBytes; ++i) {
    value.pair[i] = static_cast<unsigned char>(i + 1);
    value.token[i] = static_cast<unsigned char>(i + 33);
  }
  if (operation == role::Operation::kCreate) {
    value.caller_tid = static_cast<uint32_t>(syscall(SYS_gettid));
    value.payload_size = 5; value.original_fd_flags = FD_CLOEXEC;
  } else if (operation == role::Operation::kSuspend) {
    value.caller_tid = static_cast<uint32_t>(syscall(SYS_gettid));
  }
  return value;
}
role::Response Sentinel() {
  role::Response value{}; value.request.operation = role::Operation::kBegin;
  value.error = 123; value.has_snapshot = true; return value;
}
bool Unchanged(const role::Response& value) {
  return value.request.operation == role::Operation::kBegin &&
      value.error == 123 && value.has_snapshot;
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
  for (auto op : {role::Operation::kCreate, role::Operation::kSuspend, role::Operation::kRelease}) {
    for (uint32_t error : {0U, static_cast<uint32_t>(EPERM)}) {
      role::Response source{Request(op), error, op == role::Operation::kCreate && error == 0};
      std::array<unsigned char, role::kResponseBytes> bytes{};
      Check(role::EncodeResponse(source, bytes.data()), "encode legal response");
      role::Response decoded{};
      Check(role::DecodeResponse(bytes.data(), bytes.size(), &decoded), "decode full legal response");
      std::array<unsigned char, role::kResponseBytes> after{};
      Check(role::EncodeResponse(decoded, after.data()) && bytes == after, "complete response bytes round trip");
      for (size_t index : {size_t{0}, size_t{8}, size_t{12}, size_t{24}, size_t{31}}) {
        auto bad = bytes; bad[index] ^= 0x80; decoded = Sentinel();
        Check(!role::DecodeResponse(bad.data(), bad.size(), &decoded) && Unchanged(decoded),
              "bad fixed header rejected without output mutation");
      }
      decoded = Sentinel();
      Check(!role::DecodeResponse(bytes.data(), bytes.size() - 1, &decoded) && Unchanged(decoded),
            "short frame rejected without mutation");
      ++cases;
    }
  }
}
enum class Variant { kSuccess, kError, kMissing, kExcess, kErrorWithRight, kWrongEcho,
                     kShort, kLong, kPidfd, kCredentials, kInvalidExpected };
const char* Name(Variant value) {
  switch (value) {
    case Variant::kSuccess: return "real_one_right";
    case Variant::kError: return "framed_error_no_right";
    case Variant::kMissing: return "missing_right_rejected";
    case Variant::kExcess: return "extra_rights_closed";
    case Variant::kErrorWithRight: return "error_right_closed";
    case Variant::kWrongEcho: return "different_request_closed";
    case Variant::kShort: return "short_datagram_closed";
    case Variant::kLong: return "long_datagram_closed";
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
    auto expected = Request(); role::Response outgoing{expected, 0, true};
    unsigned rights = 1;
    if (which == Variant::kError || which == Variant::kErrorWithRight) {
      outgoing.error = EINVAL; outgoing.has_snapshot = false;
      if (which == Variant::kError) rights = 0;
    }
    if (which == Variant::kMissing) rights = 0;
    if (which == Variant::kExcess) rights = 3;
    if (which == Variant::kWrongEcho) ++outgoing.request.payload_size;
    if (which == Variant::kPidfd || which == Variant::kCredentials) {
      const int one = 1;
      Check(setsockopt(pair.receive.get(), SOL_SOCKET,
          which == Variant::kPidfd ? 76 : SO_PASSCRED, &one, sizeof(one)) == 0,
          "actual kernel ancillary option");
    }
    unsigned char bytes[role::kResponseBytes + 1]{};
    Check(role::EncodeResponse(outgoing, bytes), "encode actual transport frame");
    size_t size = role::kResponseBytes;
    if (which == Variant::kShort) --size;
    if (which == Variant::kLong) ++size;
    Send(pair.send.get(), bytes, size, input.get(), rights);
    role::Response observed = Sentinel(); role::Descriptor output;
    const size_t before = Fds();
    if (which == Variant::kInvalidExpected) {
      auto invalid = expected; memset(invalid.token, 0, sizeof(invalid.token));
      errno = 0;
      Check(role::ReceiveResponse(pair.receive.get(), invalid, &observed, &output) == -1 && errno == EINVAL &&
          Unchanged(observed) && output.get() < 0 && Fds() == before, "invalid expected is atomic and nonconsuming");
    }
    errno = 0;
    const int result = role::ReceiveResponse(pair.receive.get(), expected, &observed, &output);
    const bool pass = which == Variant::kSuccess || which == Variant::kError || which == Variant::kInvalidExpected;
    if (pass) {
      Check(result == 0 && observed.error == outgoing.error && observed.has_snapshot == outgoing.has_snapshot,
            "exact success or framed operation error received");
      if (outgoing.has_snapshot) {
        struct stat a{}, b{};
        Check(output.get() >= 0 && fstat(input.get(), &a) == 0 && fstat(output.get(), &b) == 0 &&
            a.st_dev == b.st_dev && a.st_ino == b.st_ino && fcntl(output.get(), F_GETFD) == FD_CLOEXEC,
            "actual right shares sent inode and has close-on-exec");
        output.reset();
      } else Check(output.get() < 0, "framed error has no output descriptor");
    } else Check(result == -1 && errno == EPROTO && output.get() < 0 && Unchanged(observed),
                 "bad response rejected atomically");
    Check(Fds() == before, "all received rights and pidfds returned to baseline");
    observed = Sentinel(); errno = 0;
    Check(role::ReceiveResponse(pair.receive.get(), expected, &observed, &output) == -1 &&
        (errno == EAGAIN || errno == EWOULDBLOCK) && Unchanged(observed) && output.get() < 0,
        "one frame consumed and empty socket leaves outputs unchanged");
  }
  Check(Fds() == baseline, "entire transport case owns and closes all descriptors");
  ++cases; printf("{\"case\":\"%s\",\"state\":\"PASS\"}\n", Name(which));
}
}
int main() {
  try {
    Codec();
    for (auto which : {Variant::kSuccess, Variant::kError, Variant::kMissing, Variant::kExcess,
        Variant::kErrorWithRight, Variant::kWrongEcho, Variant::kShort, Variant::kLong,
        Variant::kPidfd, Variant::kCredentials, Variant::kInvalidExpected}) Transport(which);
    printf("{\"state\":\"PASS_RESPONSE_TRANSPORT_ONLY\",\"cases\":%u,\"assertions\":%u,"
           "\"root_authorization_executed\":false,\"snapshot_created\":false,\"platform_qualified\":false}\n", cases, checks);
    return 0;
  } catch (const std::exception& error) {
    fprintf(stderr, "response control failed: %s; errno=%d\n", error.what(), errno);
    return 1;
  }
}
