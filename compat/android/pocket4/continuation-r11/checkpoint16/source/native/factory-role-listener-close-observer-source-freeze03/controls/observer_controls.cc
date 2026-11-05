// Real local transport controls; no listener service, role, namespace or grant.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#include "actual_observer.inc"

namespace {
unsigned assertions = 0;
void Need(bool ok, const char* why) {
  if (!ok) throw std::runtime_error(why);
  ++assertions;
}
struct Fd {
  int value = -1;
  explicit Fd(int fd = -1) : value(fd) {}
  Fd(const Fd&) = delete;
  ~Fd() { if (value >= 0) close(value); }
  void Reset() { if (value >= 0) close(value); value = -1; }
};
size_t Count() {
  DIR* directory = opendir("/proc/self/fd");
  Need(directory != nullptr, "owned fd count opens");
  size_t count = 0;
  while (dirent* item = readdir(directory)) {
    if (item->d_name[0] != '.') ++count;
  }
  Need(closedir(directory) == 0, "owned fd count closes");
  return count;
}
uint64_t Now() {
  timespec time{};
  Need(clock_gettime(CLOCK_MONOTONIC, &time) == 0, "real monotonic time");
  return static_cast<uint64_t>(time.tv_sec) * 1000000000ULL + time.tv_nsec;
}
void Send(int socket, size_t payload, bool rights) {
  Fd one, two;
  if (rights) {
    one.value = static_cast<int>(syscall(SYS_memfd_create, "owned-observer-one", 1UL));
    two.value = static_cast<int>(syscall(SYS_memfd_create, "owned-observer-two", 1UL));
    Need(one.value >= 0 && two.value >= 0, "real owned input rights");
  }
  char byte = 'x'; iovec vector{&byte, payload};
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } control{};
  msghdr message{}; message.msg_iov = &vector; message.msg_iovlen = 1;
  if (rights) {
    message.msg_control = control.bytes; message.msg_controllen = sizeof(control.bytes);
    cmsghdr* header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(2 * sizeof(int));
    const int fds[2] = {one.value, two.value};
    memcpy(CMSG_DATA(header), fds, sizeof(fds));
  }
  Need(sendmsg(socket, &message, MSG_DONTWAIT | MSG_NOSIGNAL) == static_cast<ssize_t>(payload),
       "actual seqpacket and optional SCM_RIGHTS queued");
}
enum class Case { kEof, kReset, kReply, kReplyRights, kEmptyRights, kLive, kNegative, kInvalid };
const char* Name(Case c) {
  switch (c) {
    case Case::kEof: return "closed_empty_peer_EOF";
    case Case::kReset: return "closed_unread_request_rights_RESET";
    case Case::kReply: return "queued_reply_rejected";
    case Case::kReplyRights: return "queued_reply_rights_rejected_without_delivery";
    case Case::kEmptyRights: return "empty_packet_rights_rejected_without_delivery";
    case Case::kLive: return "live_peer_times_out";
    case Case::kNegative: return "negative_descriptor_rejected";
    case Case::kInvalid: return "closed_descriptor_pollnval_rejected";
  }
  return "invalid";
}
void Run(Case which) {
  const size_t before = Count();
  int result = -2, observed = 0, revents = 0;
  {
    int raw[2];
    Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, raw) == 0,
         "actual owned seqpacket pair");
    Fd client(raw[0]), server(raw[1]);
    int input = client.value;
    if (which == Case::kReset) Send(client.value, 1, true);
    if (which == Case::kReply) Send(server.value, 1, false);
    if (which == Case::kReplyRights) Send(server.value, 1, true);
    if (which == Case::kEmptyRights) Send(server.value, 0, true);
    if (which != Case::kLive) server.Reset();
    if (which == Case::kNegative) input = -1;
    if (which == Case::kInvalid) client.Reset();
    if (which != Case::kNegative) {
      pollfd entry{input, static_cast<short>(POLLIN | POLLHUP), 0};
      Need(poll(&entry, 1, 0) >= 0, "actual terminal readiness sample");
      revents = entry.revents;
    }
    if (which == Case::kEof) Need((revents & POLLHUP) && !(revents & POLLERR), "EOF arm is clean HUP");
    if (which == Case::kReset) Need((revents & (POLLHUP | POLLERR)) == (POLLHUP | POLLERR), "RESET arm reproduces old readiness rejection");
    const size_t before_read = Count();
    const uint64_t end = Now() + 20000000ULL;
    errno = EDOM;
    result = ObserveRevokedSession(input, end);
    observed = errno;
    if (which == Case::kEof || which == Case::kReset) Need(result == 0 && observed == EDOM, "closed transport accepted preserving prior errno");
    else {
      int expected = EPROTO;
      if (which == Case::kLive) expected = ETIMEDOUT;
      if (which == Case::kNegative || which == Case::kInvalid) expected = EBADF;
      Need(result == -1 && observed == expected, "exact rejection remains strict");
    }
    Need(Count() == before_read, "recvmsg never installed ancillary rights");
  }
  Need(Count() == before, "all owned descriptors reclaimed");
  printf("{\"case\":\"%s\",\"state\":\"PASS\",\"poll_revents\":%d,\"returncode\":%d,\"errno\":%d}\n",
         Name(which), revents, result, observed);
}
}
int main() {
  try {
    for (Case which : {Case::kEof, Case::kReset, Case::kReply, Case::kReplyRights,
                       Case::kEmptyRights, Case::kLive, Case::kNegative, Case::kInvalid}) Run(which);
    printf("{\"state\":\"PASS_EXTRACTED_TRANSPORT_OBSERVER\",\"cases\":8,\"assertions\":%u,"
           "\"real_poll_recvmsg_clock\":true,\"role_authorization_qualified\":false,\"Android_execution\":false}\n", assertions);
    return 0;
  } catch (const std::exception& e) {
    fprintf(stderr, "FAIL: %s errno=%d\n", e.what(), errno);
    return 1;
  }
}
