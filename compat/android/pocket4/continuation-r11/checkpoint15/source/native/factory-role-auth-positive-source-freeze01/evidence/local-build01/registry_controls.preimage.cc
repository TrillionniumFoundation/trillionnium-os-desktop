// SPDX-License-Identifier: Apache-2.0
// Owned mechanism control only. No listener, snapshot creation, application,
// namespace mutation, platform filter, or persistent service is involved.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_authorization.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/audit.h>
#include <linux/capability.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace role = droidloom::proc_maps_factory::role_v1;
namespace {
constexpr uint32_t kFixtureUid = 61179, kFixtureGid = 61179;
constexpr uint32_t kRangeMin = 90200, kRangeMax = 90231;
constexpr uint32_t kCaps = (1U << CAP_SETUID) | (1U << CAP_SETGID) | (1U << CAP_SETPCAP);
constexpr uint32_t kControlMagic = 0x51415231;
constexpr int kScmPidfd = 4;
unsigned assertions = 0, direct_reaped = 0, nested_reaped = 0, forced_cleanup = 0;
unsigned cleanup_unreaped = 0;
uint64_t deadline = 0;
int child_stage = 0;

uint64_t Now() {
  timespec value{};
  if (clock_gettime(CLOCK_MONOTONIC, &value) < 0) throw std::runtime_error("clock_gettime");
  return uint64_t{static_cast<uint64_t>(value.tv_sec)} * 1000000000ULL + value.tv_nsec;
}
void Require(bool value, const char* text) {
  if (!value) throw std::runtime_error(text);
  ++assertions;
}
void ExpectError(int result, int error, const char* text) {
  const int observed = errno;
  Require(result == -1 && observed == error, text);
}
void Wait(int fd, short events, unsigned milliseconds = 2000) {
  const uint64_t end = std::min(deadline, Now() + uint64_t{milliseconds} * 1000000ULL);
  for (;;) {
    const uint64_t now = Now();
    Require(now < end, "bounded owned wait expired");
    const int remaining = static_cast<int>((end - now + 999999) / 1000000);
    pollfd entry{fd, events, 0};
    const int result = poll(&entry, 1, remaining);
    if (result < 0 && errno == EINTR) continue;
    Require(result == 1 && !(entry.revents & (POLLERR | POLLNVAL)) &&
            (entry.revents & events), "owned descriptor readiness");
    return;
  }
}
size_t DescriptorCount() {
  DIR* directory = opendir("/proc/self/fd");
  Require(directory != nullptr, "own fd directory");
  const int own = dirfd(directory);
  size_t count = 0;
  while (dirent* entry = readdir(directory)) {
    char* end = nullptr;
    const long value = strtol(entry->d_name, &end, 10);
    if (end != entry->d_name && *end == 0 && value != own) ++count;
  }
  Require(closedir(directory) == 0, "own fd count close");
  return count;
}
struct Sockets {
  role::Descriptor first, second;
  Sockets() {
    int value[2];
    Require(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, value) == 0,
            "anonymous owned socketpair");
    first.reset(value[0]); second.reset(value[1]);
  }
};
enum class Command : uint32_t {
  kReady = 1, kBegin = 2, kSetToken = 3, kCreate = 4, kSuspend = 5,
  kObserveDetach = 6, kAttach = 7, kClose = 8, kDropCaps = 9,
  kForkAttach = 10, kRelease = 11, kExit = 12, kAck = 13,
  kEndpoint = 14, kFrame = 15, kNestedReaped = 16, kError = 17
};
struct Control {
  uint32_t magic = kControlMagic;
  Command command{};
  int32_t status{};
  uint32_t pid{};
  unsigned char token[role::kDigestBytes]{};
};
static_assert(sizeof(Control) == 48);

void SendControl(int fd, const Control& input, int descriptor = -1) {
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(int))]; } control{};
  iovec vector{const_cast<Control*>(&input), sizeof(input)};
  msghdr message{}; message.msg_iov = &vector; message.msg_iovlen = 1;
  if (descriptor >= 0) {
    message.msg_control = control.bytes; message.msg_controllen = sizeof(control.bytes);
    auto* header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(header), &descriptor, sizeof(descriptor));
  }
  Wait(fd, POLLOUT);
  Require(sendmsg(fd, &message, MSG_NOSIGNAL) == sizeof(input), "owned control send");
}
struct ControlInput { Control value{}; role::Descriptor descriptor; };
ControlInput ReadControl(int fd, Command expected, bool descriptor = false) {
  Wait(fd, POLLIN);
  ControlInput output;
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(8 * sizeof(int)) + CMSG_SPACE(sizeof(ucred))]; } ancillary{};
  iovec vector{&output.value, sizeof(output.value)};
  msghdr message{}; message.msg_iov = &vector; message.msg_iovlen = 1;
  message.msg_control = ancillary.bytes; message.msg_controllen = sizeof(ancillary.bytes);
  const ssize_t count = recvmsg(fd, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC | MSG_TRUNC);
  bool valid = count == sizeof(Control) && !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC));
  unsigned descriptors = 0;
  for (auto* header = CMSG_FIRSTHDR(&message); header; header = CMSG_NXTHDR(&message, header)) {
    const size_t offset = reinterpret_cast<unsigned char*>(header) - ancillary.bytes;
    if (header->cmsg_len < CMSG_LEN(0) || header->cmsg_len > message.msg_controllen - offset) {
      valid = false; break;
    }
    const size_t bytes = header->cmsg_len - CMSG_LEN(0);
    if (header->cmsg_level == SOL_SOCKET &&
        (header->cmsg_type == SCM_RIGHTS || header->cmsg_type == kScmPidfd)) {
      for (size_t i = 0; i < bytes / sizeof(int); ++i) {
        int raw; memcpy(&raw, CMSG_DATA(header) + i * sizeof(raw), sizeof(raw));
        role::Descriptor owned(raw);
        if (header->cmsg_type == SCM_RIGHTS && descriptors++ == 0) output.descriptor = std::move(owned);
      }
      if (header->cmsg_type != SCM_RIGHTS || bytes % sizeof(int)) valid = false;
    } else valid = false;
  }
  if (output.value.magic == kControlMagic && output.value.command == Command::kError) {
    throw std::runtime_error("owned child stage=" + std::to_string(output.value.pid) +
                             " errno=" + std::to_string(output.value.status));
  }
  Require(valid && output.value.magic == kControlMagic && output.value.command == expected &&
          descriptors == (descriptor ? 1U : 0U), "exact owned control record");
  return output;
}
void CommandOnly(int fd, Command command) { Control value; value.command = command; SendControl(fd, value); }
void Ack(int fd) { CommandOnly(fd, Command::kAck); }

class OwnedChild {
 public:
  explicit OwnedChild(pid_t pid) : pid_(pid), pidfd_(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(pid), 0UL))) {
    // A just-forked, unreaped direct child cannot have had its PID reused.
    if (pidfd_.get() < 0) {
      const int error = errno;
      ++forced_cleanup;
      kill(pid_, SIGKILL);
      BoundedReap(); errno = error;
      throw std::runtime_error("own child pidfd_open");
    }
  }
  ~OwnedChild() {
    if (pid_ <= 0) return;
    ++forced_cleanup;
    syscall(SYS_pidfd_send_signal, static_cast<long>(pidfd_.get()), static_cast<long>(SIGKILL),
            nullptr, 0UL);
    BoundedReap();
  }
  void Join() {
    Wait(pidfd_.get(), POLLIN);
    int status = -1;
    const pid_t expected = pid_;
    const pid_t waited = waitpid(expected, &status, WNOHANG);
    if (waited == expected) pid_ = -1;
    Require(waited == expected && WIFEXITED(status) && WEXITSTATUS(status) == 0,
            "exact owned child exited normally and reaped");
  }
 private:
  static uint64_t MonotonicNoThrow() {
    timespec value{};
    if (clock_gettime(CLOCK_MONOTONIC, &value) < 0) return UINT64_MAX;
    return static_cast<uint64_t>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
  }
  void BoundedReap() noexcept {
    const uint64_t start = MonotonicNoThrow();
    if (start != UINT64_MAX) {
      const uint64_t end = start + 2000000000ULL;
      for (;;) {
        const pid_t value = waitpid(pid_, nullptr, WNOHANG);
        if (value == pid_) { pid_ = -1; return; }
        if (value < 0 && errno != EINTR) break;
        const uint64_t now = MonotonicNoThrow();
        if (now == UINT64_MAX || now >= end) break;
        pollfd entry{pidfd_.get(), POLLIN, 0}; poll(&entry, 1, 10);
      }
    }
    ++cleanup_unreaped;
  }
  pid_t pid_;
  role::Descriptor pidfd_;
};

void CloseOtherInherited(int keep_one, int keep_two) {
  Require(keep_one >= 3 && keep_two >= 3 && keep_one != keep_two, "owned inherited descriptors distinct");
  if (keep_one > keep_two) std::swap(keep_one, keep_two);
  const auto close = [](unsigned first, unsigned last) {
    if (first <= last) Require(syscall(SYS_close_range, static_cast<unsigned long>(first),
                                     static_cast<unsigned long>(last), 0UL) == 0,
                              "close only child inherited table");
  };
  close(3, static_cast<unsigned>(keep_one) - 1);
  close(static_cast<unsigned>(keep_one) + 1, static_cast<unsigned>(keep_two) - 1);
  close(static_cast<unsigned>(keep_two) + 1, UINT32_MAX);
}
void ParentDeath(int parent_pidfd) {
  Require(prctl(PR_SET_PDEATHSIG, static_cast<unsigned long>(SIGKILL), 0UL, 0UL, 0UL) == 0,
          "owned child parent-death signal");
  pollfd entry{parent_pidfd, POLLIN, 0};
  Require(poll(&entry, 1, 0) == 0, "owned parent still live");
}
void DropRoleCapabilities() {
  __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3, 0};
  __user_cap_data_struct data[2]{};
  Require(syscall(SYS_capset, &header, data) == 0, "drop own role capabilities");
}
void FixturePolicy() {
  // A fixture policy, not the Android base/range policy. All credential setters
  // and namespace/exec transitions are forbidden in this owned client. The
  // capability-drop negative uses capset, which cannot raise P above old P.
  std::vector<sock_filter> code;
  code.push_back(BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(seccomp_data, arch)));
  code.push_back(BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0));
  code.push_back(BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS));
  code.push_back(BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(seccomp_data, nr)));
  code.push_back(BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000U, 0, 1));
  code.push_back(BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | ENOSYS));
  for (uint32_t number : {SYS_setuid, SYS_setgid, SYS_setreuid, SYS_setregid,
                          SYS_setresuid, SYS_setresgid, SYS_setfsuid, SYS_setfsgid,
                          SYS_setgroups, SYS_setns, SYS_unshare, SYS_execve, SYS_execveat,
                          SYS_mount, SYS_umount2, SYS_pivot_root, SYS_chroot}) {
    code.push_back(BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, number, 0, 1));
    code.push_back(BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM));
  }
  code.push_back(BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
  sock_fprog program{static_cast<unsigned short>(code.size()), code.data()};
  Require(prctl(PR_SET_NO_NEW_PRIVS, 1UL, 0UL, 0UL, 0UL) == 0, "owned client NNP");
  Require(syscall(SYS_seccomp, static_cast<unsigned long>(SECCOMP_SET_MODE_FILTER), 0UL, &program) == 0,
          "owned fixture filter installed");
}
void SetupRole(int parent_pidfd) {
  Require(getuid() == 0 && geteuid() == 0, "fixture needs actual root parent");
  __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3, 0};
  __user_cap_data_struct data[2]{};
  Require(syscall(SYS_capget, &header, data) == 0 && (data[0].effective & kCaps) == kCaps,
          "fixture root has explicit role transition capabilities");
  // Populate I while the original permitted/bounding sets still allow it.
  data[0].inheritable = kCaps; data[1].inheritable = 0;
  Require(syscall(SYS_capset, &header, data) == 0, "prepare exact inheritable role caps");
  for (unsigned cap = 0; cap < 64; ++cap) {
    errno = 0;
    const int value = prctl(PR_CAPBSET_READ, static_cast<unsigned long>(cap), 0UL, 0UL, 0UL);
    if (value < 0 && errno == EINVAL) break;
    Require(value == 0 || value == 1, "capability bound read");
    if (value) Require(prctl(PR_CAPBSET_DROP, static_cast<unsigned long>(cap), 0UL, 0UL, 0UL) == 0,
                       "drop own capability bounding bit");
  }
  Require(prctl(PR_CAP_AMBIENT, static_cast<unsigned long>(PR_CAP_AMBIENT_CLEAR_ALL), 0UL, 0UL, 0UL) == 0,
          "clear owned ambient capabilities");
  Require(prctl(PR_SET_KEEPCAPS, 1UL, 0UL, 0UL, 0UL) == 0 && setgroups(0, nullptr) == 0,
          "owned keepcaps and empty supplementary groups");
  Require(setresgid(kFixtureGid, kFixtureGid, kFixtureGid) == 0 &&
          setresuid(kFixtureUid, kFixtureUid, kFixtureUid) == 0, "owned role identities");
  memset(data, 0, sizeof(data));
  data[0].inheritable = data[0].permitted = data[0].effective = kCaps;
  Require(syscall(SYS_capset, &header, data) == 0, "exact owned role EPI");
  Require(prctl(PR_SET_DUMPABLE, 0UL, 0UL, 0UL, 0UL) == 0, "owned role nondumpable");
  ParentDeath(parent_pidfd);
  FixturePolicy();
}
std::array<unsigned char, role::kDigestBytes> PairDigest() {
  std::array<unsigned char, role::kDigestBytes> value{};
  for (size_t i = 0; i < value.size(); ++i) value[i] = static_cast<unsigned char>(i + 1);
  return value;  // Fixture identity only, not a production paired-build digest.
}
role::Request Request(role::Operation operation, const unsigned char* token = nullptr) {
  role::Request value;
  value.operation = operation;
  const auto pair = PairDigest(); memcpy(value.pair, pair.data(), pair.size());
  if (token) memcpy(value.token, token, sizeof(value.token));
  if (operation == role::Operation::kBegin || operation == role::Operation::kApprove) {
    value.uid_min = value.gid_min = kRangeMin;
    value.uid_max = value.gid_max = kRangeMax;
  }
  if (operation == role::Operation::kCreate) {
    value.caller_tid = static_cast<uint32_t>(syscall(SYS_gettid));
    value.payload_size = 4096; value.source_flags = O_RDONLY; value.original_fd_flags = FD_CLOEXEC;
  }
  if (operation == role::Operation::kSuspend || operation == role::Operation::kAttach)
    value.caller_tid = static_cast<uint32_t>(syscall(SYS_gettid));
  return value;
}
void SendRole(int socket, const role::Request& request) {
  unsigned char bytes[role::kWireBytes];
  Require(role::EncodeRequest(request, bytes), "encode actual role frame");
  role::Descriptor payload;
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } ancillary{};
  iovec vector{bytes, sizeof(bytes)};
  msghdr message{}; message.msg_iov = &vector; message.msg_iovlen = 1;
  if (request.operation == role::Operation::kCreate) {
    // These own descriptors exercise authorization only. No factory snapshot
    // maker is called, so this is deliberately not a provenance positive.
    payload.reset(open("/dev/null", O_RDONLY | O_CLOEXEC));
    Require(payload.get() >= 0, "owned fixture payload descriptor");
    message.msg_control = ancillary.bytes; message.msg_controllen = sizeof(ancillary.bytes);
    auto* header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(2 * sizeof(int));
    const int rights[2] = {payload.get(), payload.get()}; memcpy(CMSG_DATA(header), rights, sizeof(rights));
  }
  Wait(socket, POLLOUT);
  Require(sendmsg(socket, &message, MSG_NOSIGNAL) == sizeof(bytes), "send actual role frame");
}
void NewEndpoint(int control, role::Descriptor* client, const role::Request& request) {
  Sockets pair;
  Require(role::ConfigureIdentityReception(pair.second.get(), false) == 0, "kernel role identity reception");
  SendRole(pair.first.get(), request);
  Control reply; reply.command = Command::kEndpoint; reply.pid = static_cast<uint32_t>(getpid());
  SendControl(control, reply, pair.second.get());
  *client = std::move(pair.first);
}

[[noreturn]] void RunChild(int control, int parent_pidfd, role::Registry* inherited) {
  try {
    child_stage = 1;
    errno = 0;
    Require(inherited->Sweep() == -1 && errno == ESHUTDOWN, "COW fork cannot operate parent's registry");
    CloseOtherInherited(control, parent_pidfd);
    child_stage = 2; ParentDeath(parent_pidfd); SetupRole(parent_pidfd);
    child_stage = 3; CommandOnly(control, Command::kReady);
    std::array<unsigned char, role::kDigestBytes> token{};
    role::Descriptor client;
    for (;;) {
      Wait(control, POLLIN);
      // ReadControl requires an expected kind; peek only this owned private
      // protocol to select it, then consume/validate the complete frame.
      Control peek{};
      Require(recv(control, &peek, sizeof(peek), MSG_PEEK | MSG_DONTWAIT) == sizeof(peek), "owned command peek");
      auto input = ReadControl(control, peek.command);
      child_stage = 100 + static_cast<int>(input.value.command);
      switch (input.value.command) {
        case Command::kBegin:
          NewEndpoint(control, &client, Request(role::Operation::kBegin)); break;
        case Command::kSetToken:
          memcpy(token.data(), input.value.token, token.size()); Ack(control); break;
        case Command::kCreate:
          SendRole(client.get(), Request(role::Operation::kCreate, token.data()));
          CommandOnly(control, Command::kFrame); break;
        case Command::kSuspend:
          SendRole(client.get(), Request(role::Operation::kSuspend, token.data()));
          CommandOnly(control, Command::kFrame); break;
        case Command::kObserveDetach:
          Wait(client.get(), POLLHUP); client.reset(); Ack(control); break;
        case Command::kAttach:
          NewEndpoint(control, &client, Request(role::Operation::kAttach, token.data())); break;
        case Command::kClose:
          client.reset(); Ack(control); break;
        case Command::kDropCaps:
          DropRoleCapabilities(); Ack(control); break;
        case Command::kRelease:
          SendRole(client.get(), Request(role::Operation::kRelease, token.data()));
          CommandOnly(control, Command::kFrame); break;
        case Command::kForkAttach: {
          Require(client.get() < 0, "fork control starts after detached connection closed");
          role::Descriptor self_pidfd(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(getpid()), 0UL)));
          Require(self_pidfd.get() >= 0, "nested owned parent pidfd");
          const pid_t nested = fork(); Require(nested >= 0, "owned nested fork");
          if (nested == 0) {
            try {
              ParentDeath(self_pidfd.get());
              role::Descriptor endpoint;
              NewEndpoint(control, &endpoint, Request(role::Operation::kAttach, token.data()));
              ReadControl(control, Command::kAck);
              _exit(0);
            } catch (...) { _exit(91); }
          }
          OwnedChild child(nested); child.Join();
          Control reply; reply.command = Command::kNestedReaped;
          reply.pid = static_cast<uint32_t>(nested); reply.status = 0; SendControl(control, reply);
          break;
        }
        case Command::kExit:
          client.reset(); Ack(control); _exit(0);
        default: throw std::runtime_error("unexpected owned child command");
      }
    }
  } catch (...) {
    const int error = errno;
    try {
      Control report; report.command = Command::kError; report.status = error; report.pid = child_stage;
      SendControl(control, report);
    } catch (...) {}
    _exit(90);
  }
}

struct EndpointInput { role::Descriptor connection; role::Received message; };
void Endpoint(int control, EndpointInput* result) {
  auto record = ReadControl(control, Command::kEndpoint, true);
  result->connection = std::move(record.descriptor);
  Wait(result->connection.get(), POLLIN);
  Require(role::Receive(result->connection.get(), &result->message) == 0, "actual endpoint frame and kernel pidfd");
}
void Frame(int control, role::Registry& registry, role::GrantHandle handle, role::Received* result) {
  ReadControl(control, Command::kFrame);
  const int connection = registry.Connection(handle);
  Require(connection >= 0, "active owned connection");
  Wait(connection, POLLIN);
  Require(role::Receive(connection, result) == 0, "actual frame and kernel pidfd");
}
void Approve(role::Registry& registry, const role::Challenge& challenge, pid_t pid, int expected = 0) {
  Sockets admin;
  Require(role::ConfigureIdentityReception(admin.second.get(), false) == 0, "owned root admin identity reception");
  auto request = Request(role::Operation::kApprove, challenge.token);
  request.child_pid_in_parent_namespace = static_cast<uint32_t>(pid);
  request.initial_uid = kFixtureUid; request.initial_gid = kFixtureGid;
  SendRole(admin.first.get(), request);
  role::Received received;
  Require(role::Receive(admin.second.get(), &received) == 0, "actual root approval receive");
  errno = 0;
  const int result = registry.Approve(admin.second.get(), received);
  if (expected) ExpectError(result, expected, "root approval exact rejection");
  else Require(result == 0, "actual root parent approves once");
}
void Create(int control, role::Registry& registry, role::GrantHandle handle) {
  CommandOnly(control, Command::kCreate);
  role::Received frame; Frame(control, registry, handle, &frame);
  role::SnapshotAuthority authority;
  Require(registry.AuthorizeCreate(handle, frame, &authority) == 0, "actual grant caller authority");
  Require(authority.proc_fd >= 0 && authority.subject_pidfd >= 0 && authority.caller_proc_fd >= 0 &&
          authority.uid == kFixtureUid && authority.gid == kFixtureGid && authority.start_ticks > 0 &&
          authority.caller_start_ticks == authority.start_ticks, "authority pins original leader caller");
  Require(registry.FinishCreate(handle) == 0, "actual grant caller commit recheck");
}
void Suspend(int control, role::Registry& registry, role::GrantHandle handle, bool detach) {
  CommandOnly(control, Command::kSuspend);
  role::Received frame; Frame(control, registry, handle, &frame);
  Require(registry.Suspend(handle, frame) == 0, "actual suspend pins caller lease");
  if (!detach) return;
  // This control channel is the fixture's acknowledgement. The role client
  // remains live and waits for the owner to close the role connection.
  CommandOnly(control, Command::kObserveDetach);
  Require(registry.Detach(handle) == 0, "explicit live transport detach");
  ReadControl(control, Command::kAck);
}
void Attach(int control, role::Registry& registry, role::GrantHandle old, int expected = 0) {
  CommandOnly(control, Command::kAttach);
  EndpointInput endpoint; Endpoint(control, &endpoint);
  role::GrantHandle output{UINT32_MAX, UINT64_MAX};
  errno = 0;
  const int result = registry.Attach(&endpoint.connection, endpoint.message, &output);
  if (expected) {
    ExpectError(result, expected, "actual reattach rejection");
    Require(output.slot == UINT32_MAX && output.serial == UINT64_MAX && endpoint.connection.get() >= 0,
            "failed reattach output and connection ownership unchanged");
  } else {
    Require(result == 0 && output.slot == old.slot && output.serial == old.serial && endpoint.connection.get() == -1,
            "same grant reattaches without new root approval");
    Require(registry.IsActive(output) == 0, "reattached grant active");
  }
}
void RebeginDenied(int control, role::Registry& registry) {
  CommandOnly(control, Command::kBegin);
  EndpointInput endpoint; Endpoint(control, &endpoint);
  role::Challenge output{}; output.visible_pid = UINT32_MAX;
  errno = 0;
  ExpectError(registry.Begin(&endpoint.connection, endpoint.message, &output), EALREADY,
              "live revoked process cannot obtain another grant");
  Require(output.visible_pid == UINT32_MAX && endpoint.connection.get() >= 0,
          "rejected begin leaves output and descriptor ownership untouched");
}

enum class Case { kCreateRelease, kSuspendAttach, kForkReject, kActiveHup, kPendingHup,
                  kSuspendingHup, kContextLoss, kWrongApproval, kDuplicateApproval, kExpired };
const char* Name(Case value) {
  switch (value) {
    case Case::kCreateRelease: return "one_grant_create_release_tombstone";
    case Case::kSuspendAttach: return "same_pidfd_caller_suspend_attach";
    case Case::kForkReject: return "fork_token_rejected_parent_reattaches";
    case Case::kActiveHup: return "unexpected_active_hup_tombstone";
    case Case::kPendingHup: return "pending_hup_tombstone";
    case Case::kSuspendingHup: return "pre_detach_hup_tombstone";
    case Case::kContextLoss: return "suspended_capability_loss_revokes";
    case Case::kWrongApproval: return "wrong_fork_return_pid_then_exact_parent";
    case Case::kDuplicateApproval: return "duplicate_root_approval_rejected";
    case Case::kExpired: return "pending_deadline_tombstone";
  }
  return "invalid";
}
void RunCase(Case which, role::Registry& registry) {
  const size_t before = DescriptorCount();
  role::GrantHandle handle{};
  {
    Sockets control;
    role::Descriptor parent_pidfd(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(getpid()), 0UL)));
    Require(parent_pidfd.get() >= 0, "owned controller pidfd");
    const pid_t pid = fork(); Require(pid >= 0, "owned role fork");
    if (pid == 0) RunChild(control.second.get(), parent_pidfd.get(), &registry);
    OwnedChild child(pid); control.second.reset();
    ReadControl(control.first.get(), Command::kReady);
    CommandOnly(control.first.get(), Command::kBegin);
    role::Challenge challenge;
    {
      EndpointInput endpoint; Endpoint(control.first.get(), &endpoint);
      Require(registry.Begin(&endpoint.connection, endpoint.message, &challenge) == 0 && endpoint.connection.get() == -1,
              "actual nonroot role begin bound to kernel PIDFD");
    }
    Require(challenge.visible_pid == static_cast<uint32_t>(pid), "parent fork-return PID matches live subject");
    handle = challenge.handle;
    Control token; token.command = Command::kSetToken; memcpy(token.token, challenge.token, sizeof(token.token));
    SendControl(control.first.get(), token); ReadControl(control.first.get(), Command::kAck);
    const bool pending = which == Case::kPendingHup || which == Case::kExpired;
    if (!pending) {
      if (which == Case::kWrongApproval) Approve(registry, challenge, pid + 1, EPERM);
      Approve(registry, challenge, pid);
      Require(registry.IsActive(handle) == 0, "approved grant active");
      if (which == Case::kDuplicateApproval) Approve(registry, challenge, pid, EALREADY);
    }
    switch (which) {
      case Case::kCreateRelease:
      case Case::kWrongApproval:
      case Case::kDuplicateApproval: {
        Create(control.first.get(), registry, handle);
        CommandOnly(control.first.get(), Command::kRelease);
        role::Received frame; Frame(control.first.get(), registry, handle, &frame);
        Require(registry.Release(handle, frame) == 0, "explicit revoke");
        ExpectError(registry.IsActive(handle), ESHUTDOWN, "released grant tombstone");
        RebeginDenied(control.first.get(), registry); break;
      }
      case Case::kSuspendAttach:
      case Case::kForkReject: {
        Suspend(control.first.get(), registry, handle, true);
        if (which == Case::kForkReject) {
          CommandOnly(control.first.get(), Command::kForkAttach);
          EndpointInput endpoint; Endpoint(control.first.get(), &endpoint);
          role::GrantHandle untouched{UINT32_MAX, UINT64_MAX};
          ExpectError(registry.Attach(&endpoint.connection, endpoint.message, &untouched), EPERM,
                      "actual fork child cannot use parent token");
          Require(untouched.slot == UINT32_MAX && untouched.serial == UINT64_MAX,
                  "fork refusal preserves output");
          Ack(control.first.get());
          auto joined = ReadControl(control.first.get(), Command::kNestedReaped);
          Require(joined.value.status == 0 && joined.value.pid != static_cast<uint32_t>(pid),
                  "only nested owned child reaped normally");
          ++nested_reaped;
        }
        Attach(control.first.get(), registry, handle);
        Create(control.first.get(), registry, handle); registry.Close(handle); break;
      }
      case Case::kActiveHup:
      case Case::kPendingHup:
      case Case::kSuspendingHup:
        if (which == Case::kSuspendingHup) Suspend(control.first.get(), registry, handle, false);
        CommandOnly(control.first.get(), Command::kClose); ReadControl(control.first.get(), Command::kAck);
        Require(registry.Sweep() == 0, "observe actual unexpected HUP");
        ExpectError(registry.IsActive(handle), ESHUTDOWN, "HUP permanently revokes same live process");
        RebeginDenied(control.first.get(), registry); break;
      case Case::kContextLoss:
        Suspend(control.first.get(), registry, handle, true);
        CommandOnly(control.first.get(), Command::kDropCaps); ReadControl(control.first.get(), Command::kAck);
        // Attach begins with Sweep, which observes the loss before token lookup.
        Attach(control.first.get(), registry, handle, ENOENT);
        ExpectError(registry.IsActive(handle), ESHUTDOWN, "capability change tombstones old generation"); break;
      case Case::kExpired: {
        const uint64_t until = Now() + role::kPendingNanos + 50000000ULL;
        while (Now() < until) {
          Require(Now() < deadline, "whole fixture deadline");
          poll(nullptr, 0, 10);
        }
        Require(registry.Sweep() == 0, "pending grant bounded expiry");
        ExpectError(registry.IsActive(handle), ESHUTDOWN, "expired grant revoked");
        RebeginDenied(control.first.get(), registry); break;
      }
    }
    CommandOnly(control.first.get(), Command::kExit); ReadControl(control.first.get(), Command::kAck);
    child.Join(); ++direct_reaped;
    Require(registry.Sweep() == 0, "confirmed child death retires only that slot");
    ExpectError(registry.IsActive(handle), ENOENT, "dead subject grant removed after pidfd death");
  }
  Require(DescriptorCount() == before, "case returns all owned factory descriptors");
  printf("{\"case\":\"%s\",\"state\":\"PASS\",\"actual_kernel_identity\":true,"
         "\"production_platform_policy\":false,\"snapshot_created\":false}\n", Name(which));
  fflush(stdout);
}
std::string Hex(const char* text) {
  constexpr char digits[] = "0123456789abcdef";
  std::string value;
  for (const unsigned char* p = reinterpret_cast<const unsigned char*>(text); *p; ++p) {
    value += digits[*p >> 4]; value += digits[*p & 15];
  }
  return value;
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 2 || strcmp(argv[1], "--execute-once")) {
    puts("{\"state\":\"PLAN_ONLY\",\"actual_role_registry\":false,\"owned_cases\":10,"
         "\"factory_service_started\":false,\"Main_actions\":0}");
    return argc == 1 ? 0 : 2;
  }
  try {
    Require(getuid() == 0 && geteuid() == 0 && syscall(SYS_gettid) == getpid(), "initial root owner main thread required");
    struct sigaction disposition{};
    Require(sigaction(SIGCHLD, nullptr, &disposition) == 0 && disposition.sa_handler == SIG_DFL &&
            !(disposition.sa_flags & SA_NOCLDWAIT), "fixture exclusively reaps its direct children");
    deadline = Now() + 30000000000ULL;
    const size_t before = DescriptorCount();
    {
      role::Registry registry;
      const auto pair = PairDigest();
      Require(registry.Initialize(pair.data()) == 0, "actual initial-user-namespace registry initialize");
      for (Case which : {Case::kCreateRelease, Case::kSuspendAttach, Case::kForkReject,
                          Case::kActiveHup, Case::kPendingHup, Case::kSuspendingHup,
                          Case::kContextLoss, Case::kWrongApproval, Case::kDuplicateApproval,
                          Case::kExpired}) RunCase(which, registry);
    }
    Require(DescriptorCount() == before && direct_reaped == 10 && nested_reaped == 1 &&
            !forced_cleanup && !cleanup_unreaped,
            "every exact owned descriptor and child retired without forced cleanup");
    printf("{\"state\":\"PASS_OWNED_REGISTRY_MECHANISM\",\"cases\":10,\"assertions\":%u,"
           "\"direct_children_reaped\":%u,\"nested_children_reaped\":%u,\"forced_cleanup\":%u,\"cleanup_unreaped\":%u,"
           "\"platform_policy_qualified\":false,\"snapshot_created\":false,\"Main_actions\":0,"
           "\"factory_service_started\":false}\n", assertions, direct_reaped, nested_reaped, forced_cleanup, cleanup_unreaped);
    return 0;
  } catch (const std::exception& error) {
    const int observed_errno = errno;
    printf("{\"state\":\"FAIL\",\"error_hex\":\"%s\",\"errno\":%d,"
           "\"direct_children_reaped\":%u,\"nested_children_reaped\":%u,"
           "\"forced_cleanup\":%u,\"cleanup_unreaped\":%u,\"Main_actions\":0,\"factory_service_started\":false}\n",
           Hex(error.what()).c_str(), observed_errno, direct_reaped, nested_reaped, forced_cleanup, cleanup_unreaped);
    return 1;
  }
}
