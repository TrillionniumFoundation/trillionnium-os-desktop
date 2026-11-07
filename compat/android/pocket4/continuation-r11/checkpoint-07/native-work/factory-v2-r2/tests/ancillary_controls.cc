// Actual recvmsg/SCM_RIGHTS/SO_PASSPIDFD/SO_PASSCRED controls. No service,
// namespace, credential transition, poll, socket, or recvmsg seam is used.
// Client coverage is the exact receive stage called by CreateSnapshot, not
// its separate authorization, root factory, or provenance qualification.
#ifndef FACTORY_SOURCE
#define FACTORY_SOURCE "../source/factory_main.cc"
#endif
#ifndef PROVENANCE_SOURCE
#define PROVENANCE_SOURCE "../engine-delta/proc_maps_provenance.cc"
#endif
#define main disabled_factory_entry
#include FACTORY_SOURCE
#undef main
#include PROVENANCE_SOURCE
#include <dirent.h>
#include <set>
#include <stdlib.h>
#include <sys/utsname.h>

namespace f = droidloom::proc_maps_factory;
namespace p = berberis::proc_maps_provenance;
namespace {
void Must(bool condition, const char* name) {
  if (!condition) { perror(name); exit(70); }
}
std::set<int> Fds() {
  DIR* directory = opendir("/proc/thread-self/fd");
  Must(directory != nullptr, "own fd directory");
  const int own = dirfd(directory);
  std::set<int> result;
  while (dirent* row = readdir(directory)) {
    char* end;
    const long value = strtol(row->d_name, &end, 10);
    if (end != row->d_name && *end == 0 && value >= 0 && value <= INT_MAX && value != own)
      result.insert(static_cast<int>(value));
  }
  closedir(directory);
  return result;
}
struct Case {
  const char* name;
  bool pidfd;
  bool credentials;
  unsigned rights;
  int byte_delta;
  uint32_t reply_error;
};
bool One(const Case& item, bool client, bool log) {
  f::Authority authority;
  int control[2];
  Must(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, control) == 0,
       "owned authority socketpair");
  authority.control.reset(control[0]); f::Fd keep_control(control[1]);
  authority.owner_pidfd.reset(static_cast<int>(syscall(SYS_pidfd_open, getpid(), 0)));
  Must(authority.owner_pidfd.get() >= 0, "own authority pidfd");
  int sockets[2];
  Must(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, sockets) == 0,
       "owned data socketpair");
  f::Fd receiver(sockets[0]), sender(sockets[1]);
  const int pass_pidfd = item.pidfd, pass_credentials = item.credentials;
  Must(setsockopt(receiver.get(), SOL_SOCKET, 76, &pass_pidfd, sizeof(pass_pidfd)) == 0,
       "SO_PASSPIDFD");
  Must(setsockopt(receiver.get(), SOL_SOCKET, SO_PASSCRED, &pass_credentials, sizeof(pass_credentials)) == 0,
       "SO_PASSCRED");
  Must(f::ValidateSocket(receiver.get(), false) == 0, "actual factory ValidateSocket");
  int enabled = -1; socklen_t option_size = sizeof(enabled);
  Must(getsockopt(receiver.get(), SOL_SOCKET, 76, &enabled, &option_size) == 0 &&
       option_size == sizeof(enabled) && enabled == pass_pidfd, "receiver option observed");
  f::Fd input(open("/dev/null", O_RDONLY | O_CLOEXEC));
  Must(input.get() >= 0, "owned sent input");
  struct stat identity{};
  Must(fstat(input.get(), &identity) == 0, "owned input identity");
  unsigned char bytes[p::kRequestBytes + 1]{};
  if (client) {
    p::EncodeReply(item.reply_error, bytes);
  } else {
    const p::CreateRequest request{1, static_cast<uint32_t>(syscall(SYS_gettid)), O_RDONLY, FD_CLOEXEC};
    Must(p::EncodeCreateRequest(request, bytes), "owned request encode");
  }
  const size_t size = (client ? p::kReplyBytes : p::kRequestBytes) + item.byte_delta;
  union { cmsghdr alignment; unsigned char bytes[CMSG_SPACE(32 * sizeof(int))]; } ancillary{};
  iovec vector{bytes, size}; msghdr message{};
  message.msg_iov = &vector; message.msg_iovlen = 1;
  if (item.rights) {
    Must(item.rights <= 32, "bounded rights count");
    message.msg_control = ancillary.bytes;
    message.msg_controllen = CMSG_SPACE(item.rights * sizeof(int));
    cmsghdr* header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(item.rights * sizeof(int));
    for (unsigned i = 0; i < item.rights; ++i) {
      const int descriptor = input.get();
      memcpy(CMSG_DATA(header) + i * sizeof(int), &descriptor, sizeof(descriptor));
    }
  }
  Must(sendmsg(sender.get(), &message, MSG_NOSIGNAL) == static_cast<ssize_t>(size), "actual sendmsg");
  const auto before = Fds();
  int result, error;
  bool positive_fd_valid = true;
  errno = 203;
  if (client) {
    result = p::ReceiveSnapshotReply(receiver.get()); error = errno;
    if (result >= 0) {
      f::Fd returned(result);
      struct stat received_identity{};
      const int flags = fcntl(returned.get(), F_GETFD);
      positive_fd_valid = fstat(returned.get(), &received_identity) == 0 &&
                          f::SameInode(identity, received_identity) && flags >= 0 && (flags & FD_CLOEXEC);
    }
  } else {
    f::Rights rights; p::CreateRequest decoded{};
    result = f::Receive(authority, receiver.get(), &decoded, &rights, f::Now() + f::kRequestNanos);
    error = errno;
    if (result == 0) positive_fd_valid = rights.count == 2 && decoded.payload_size == 1;
  }
  const auto after = Fds();
  size_t leaked = 0;
  for (int descriptor : after) if (!before.count(descriptor)) {
    ++leaked;
    close(descriptor); // Only newly installed, unowned receive-stage objects in this single-threaded test.
  }
  struct stat still_input{};
  const bool input_alive = fstat(input.get(), &still_input) == 0 && f::SameInode(identity, still_input);
  const bool no_fd_change = after == before;
  const bool restored = Fds() == before;
  const bool ordinary = !item.pidfd && !item.credentials && item.byte_delta == 0;
  const bool success = ordinary && item.reply_error == 0 && item.rights == (client ? 1u : 2u);
  const bool propagated_error = client && ordinary && item.rights == 0 &&
                                item.reply_error > 0 && item.reply_error <= 4095;
  const int wanted_error = propagated_error ? static_cast<int>(item.reply_error) : EPROTO;
  const bool semantics = success ? (client ? result >= 0 : result == 0) : result == -1 && error == wanted_error;
  const bool pass = semantics && no_fd_change && restored && input_alive && positive_fd_valid;
  if (log) printf("{\"stage\":\"%s\",\"case\":\"%s\",\"passpidfd\":%d,\"passcred\":%d,"
                 "\"rights_sent\":%u,\"receive_rc\":%d,\"receive_errno\":%d,\"leaked_received_fds\":%zu,"
                 "\"ordinary_fds_unchanged\":%s,\"input_alive\":%s,\"control_restored_table\":%s,\"pass\":%s}\n",
                 client ? "client_reply" : "factory_request", item.name, pass_pidfd, pass_credentials,
                 item.rights, result, error, leaked, no_fd_change ? "true" : "false",
                 input_alive ? "true" : "false", restored ? "true" : "false", pass ? "true" : "false");
  return pass;
}
}
int main() {
  const auto start = Fds();
  utsname kernel{}; Must(uname(&kernel) == 0, "uname");
  printf("{\"scope\":\"actual receive stages and real kernel ancillary; no service or namespace; client auth/provenance not exercised\","
         "\"kernel\":\"%s\",\"recvmsg_seam\":false,\"poll_seam\":false}\n", kernel.release);
  bool all = true; unsigned cases = 0;
  for (bool client : {false, true}) {
    const unsigned normal = client ? 1 : 2;
    const Case tests[] = {
      {"ordinary", false, false, normal, 0, 0},
      {"pidfd_with_rights", true, false, normal, 0, 0},
      {"credentials_with_rights", false, true, normal, 0, 0},
      {"pidfd_credentials_rights", true, true, normal, 0, 0},
      {"pidfd_only", true, false, 0, 0, 0},
      {"credentials_only", false, true, 0, 0, 0},
      {"no_rights", false, false, 0, 0, 0},
      {"too_many_rights", false, false, 3, 0, 0},
      {"ctrunc_rights", false, false, 32, 0, 0},
      {"ctrunc_with_pidfd", true, false, 32, 0, 0},
      {"short_with_pidfd", true, false, normal, -1, 0},
      {"long_with_pidfd", true, false, normal, 1, 0},
      {"short_ordinary", false, false, normal, -1, 0},
      {"long_ordinary", false, false, normal, 1, 0},
    };
    for (const auto& item : tests) { all = One(item, client, true) && all; ++cases; }
    bool repeat = true;
    for (unsigned i = 0; i < 32; ++i)
      repeat = One({"repeated_pidfd", true, false, normal, 0, 0}, client, false) && repeat;
    printf("{\"stage\":\"%s\",\"case\":\"32_pidfd_rejections\",\"pass\":%s}\n",
           client ? "client_reply" : "factory_request", repeat ? "true" : "false");
    all = repeat && all; ++cases;
  }
  for (const auto& item : {Case{"propagate_error_without_fd", false, false, 0, 0, EPERM},
                           Case{"error_with_pidfd_rejected", true, false, 0, 0, EPERM},
                           Case{"error_with_rights_rejected", false, false, 1, 0, EPERM},
                           Case{"invalid_error_rejected", false, false, 0, 0, 4096}}) {
    all = One(item, true, true) && all; ++cases;
  }
  const bool closed = Fds() == start;
  printf("{\"cases\":%u,\"all_owned_descriptors_closed\":%s,\"all_pass\":%s}\n",
         cases, closed ? "true" : "false", all && closed ? "true" : "false");
  return all && closed ? 0 : 1;
}
