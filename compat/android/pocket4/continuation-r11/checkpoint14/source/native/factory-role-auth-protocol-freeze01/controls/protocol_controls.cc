// SPDX-License-Identifier: Apache-2.0
// Owned local protocol controls. No factory listener, application or namespace
// is started. Positive platform role authorization is a separate required gate.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_authorization.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <array>
#include <vector>

namespace role = droidloom::proc_maps_factory::role_v1;
namespace {
unsigned passed = 0;
void Check(bool condition, const char* label) {
  if (!condition) {
    fprintf(stderr, "FAIL %s errno=%d\n", label, errno);
    exit(1);
  }
  ++passed;
}
size_t Fds() {
  DIR* directory = opendir("/proc/self/fd");
  Check(directory != nullptr, "own fd directory");
  const int own = dirfd(directory);
  size_t total = 0;
  while (dirent* item = readdir(directory)) {
    char* end = nullptr;
    const long value = strtol(item->d_name, &end, 10);
    if (end != item->d_name && *end == '\0' && value != own) ++total;
  }
  Check(closedir(directory) == 0, "own fd count close");
  return total;
}
role::Request Valid(role::Operation operation) {
  role::Request request;
  request.operation = operation;
  for (size_t i = 0; i < role::kDigestBytes; ++i) {
    request.pair[i] = static_cast<unsigned char>(i + 1);
    if (operation != role::Operation::kBegin) request.token[i] = static_cast<unsigned char>(i + 33);
  }
  if (operation == role::Operation::kBegin || operation == role::Operation::kApprove) {
    request.uid_min = request.gid_min = 90000;
    request.uid_max = request.gid_max = 90099;
  }
  if (operation == role::Operation::kApprove) {
    request.child_pid_in_parent_namespace = 73;
    request.initial_uid = request.initial_gid = 61171;
  }
  if (operation == role::Operation::kCreate) {
    request.caller_tid = 73;
    request.payload_size = 4096;
    request.source_flags = O_RDONLY;
    request.original_fd_flags = FD_CLOEXEC;
  }
  if (operation == role::Operation::kAttach || operation == role::Operation::kSuspend) {
    request.caller_tid = 73;
  }
  return request;
}
std::array<unsigned char, role::kWireBytes> Encode(const role::Request& request) {
  std::array<unsigned char, role::kWireBytes> bytes{};
  Check(role::EncodeRequest(request, bytes.data()), "valid encode");
  return bytes;
}
void Reject(const unsigned char* bytes, size_t size, const char* label) {
  role::Request output = Valid(role::Operation::kApprove);
  unsigned char before[sizeof(output)];
  memcpy(before, &output, sizeof(output));
  Check(!role::DecodeRequest(bytes, size, &output), label);
  Check(!memcmp(before, &output, sizeof(output)), "failed decode untouched");
}
void BadEncode(const role::Request& request) {
  std::array<unsigned char, role::kWireBytes> bytes;
  bytes.fill(0xa5);
  const auto before = bytes;
  Check(!role::EncodeRequest(request, bytes.data()) && bytes == before, "failed encode untouched");
}
void WireControls() {
  for (auto operation : {role::Operation::kBegin, role::Operation::kApprove,
                         role::Operation::kCreate, role::Operation::kRelease,
                         role::Operation::kAttach, role::Operation::kSuspend}) {
    const auto request = Valid(operation);
    const auto bytes = Encode(request);
    role::Request decoded;
    Check(role::DecodeRequest(bytes.data(), bytes.size(), &decoded), "valid decode");
    Check(Encode(decoded) == bytes, "wire roundtrip exact");
    Reject(bytes.data(), bytes.size() - 1, "short frame");
    std::array<unsigned char, role::kWireBytes + 1> long_frame{};
    memcpy(long_frame.data(), bytes.data(), bytes.size());
    Reject(long_frame.data(), long_frame.size(), "long frame");
    for (size_t index : {size_t{0}, size_t{8}, size_t{128}, size_t{159}}) {
      auto altered = bytes;
      altered[index] ^= 0x40;
      Reject(altered.data(), altered.size(), "magic version or reserved");
    }
    auto altered = bytes;
    memset(altered.data() + 16, 0, role::kDigestBytes);
    Reject(altered.data(), altered.size(), "empty platform pair");
  }
  auto begin = Valid(role::Operation::kBegin);
  begin.token[0] = 1; BadEncode(begin);
  begin = Valid(role::Operation::kBegin); begin.uid_min = 0; BadEncode(begin);
  begin = Valid(role::Operation::kBegin); begin.gid_min = begin.gid_max + 1; BadEncode(begin);
  begin = Valid(role::Operation::kBegin); begin.uid_max = UINT32_MAX; BadEncode(begin);
  auto approve = Valid(role::Operation::kApprove);
  approve.child_pid_in_parent_namespace = 0; BadEncode(approve);
  approve = Valid(role::Operation::kApprove); approve.initial_uid = 0; BadEncode(approve);
  approve = Valid(role::Operation::kApprove); approve.initial_gid = UINT32_MAX; BadEncode(approve);
  auto create = Valid(role::Operation::kCreate);
  create.payload_size = 0; BadEncode(create);
  create = Valid(role::Operation::kCreate); create.payload_size = 8U * 1024U * 1024U + 1; BadEncode(create);
  create = Valid(role::Operation::kCreate); create.uid_min = 1; BadEncode(create);
  create = Valid(role::Operation::kCreate); create.original_fd_flags = 0x80000000U; BadEncode(create);
  create = Valid(role::Operation::kCreate); create.caller_tid = UINT32_MAX; BadEncode(create);
  auto release = Valid(role::Operation::kRelease);
  memset(release.token, 0, sizeof(release.token)); BadEncode(release);
  release = Valid(role::Operation::kRelease); release.source_flags = 1; BadEncode(release);
  auto pause = Valid(role::Operation::kSuspend);
  pause.caller_tid = 0; BadEncode(pause);
  pause = Valid(role::Operation::kAttach); pause.caller_tid = UINT32_MAX; BadEncode(pause);
  pause = Valid(role::Operation::kSuspend); pause.payload_size = 1; BadEncode(pause);
}
struct Pair {
  role::Descriptor sender, receiver;
  Pair(bool identity) {
    int fds[2];
    Check(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, fds) == 0,
          "owned seqpacket pair");
    sender.reset(fds[0]); receiver.reset(fds[1]);
    if (identity) Check(role::ConfigureIdentityReception(receiver.get(), false) == 0,
                        "kernel passcred passpidfd support");
  }
};
void Send(int socket, const unsigned char* data, size_t bytes, const std::vector<int>& rights) {
  std::vector<unsigned char> control(rights.empty() ? 0 : CMSG_SPACE(rights.size() * sizeof(int)));
  iovec iov{const_cast<unsigned char*>(data), bytes};
  msghdr message{};
  message.msg_iov = &iov; message.msg_iovlen = 1;
  if (!control.empty()) {
    message.msg_control = control.data(); message.msg_controllen = control.size();
    cmsghdr* header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(rights.size() * sizeof(int));
    memcpy(CMSG_DATA(header), rights.data(), rights.size() * sizeof(int));
  }
  Check(sendmsg(socket, &message, MSG_NOSIGNAL) == static_cast<ssize_t>(bytes), "owned frame send");
}
void ReceiveCase(role::Operation operation, size_t rights_count, int length_delta, bool corrupt,
                 bool expected_success) {
  const size_t process_before = Fds();
  {
    Pair pair(true);
    role::Descriptor original(open("/dev/null", O_RDONLY | O_CLOEXEC));
    Check(original.get() >= 0, "owned source descriptor");
    auto encoded = Encode(Valid(operation));
    std::vector<unsigned char> frame(encoded.begin(), encoded.end());
    if (length_delta < 0) frame.pop_back();
    if (length_delta > 0) frame.push_back(0);
    if (corrupt) frame[0] ^= 1;
    const size_t before = Fds();
    Send(pair.sender.get(), frame.data(), frame.size(), std::vector<int>(rights_count, original.get()));
    {
      role::Received received;
      errno = 0;
      const int rc = role::Receive(pair.receiver.get(), &received);
      const int error = errno;
      Check(expected_success ? rc == 0 : rc == -1 && error == EPROTO, "actual frame acceptance");
      Check(fcntl(original.get(), F_GETFD) >= 0, "sender original survives");
      if (expected_success) {
        Check(received.request().operation == operation, "actual operation");
        Check(Fds() == before + rights_count + 1, "owned rights plus kernel pidfd");
        if (operation == role::Operation::kCreate) {
          Check(received.source_fd() != original.get() && received.payload_fd() != original.get(),
                "received duplicates are distinct");
          Check((fcntl(received.source_fd(), F_GETFD) & FD_CLOEXEC) &&
                (fcntl(received.payload_fd(), F_GETFD) & FD_CLOEXEC), "rights cloexec");
        }
        Check(role::Receive(pair.receiver.get(), &received) == -1 && errno == EINVAL,
              "received object not overwritten");
      } else {
        Check(Fds() == before, "reject closes all delivered rights and pidfd");
        Check(received.source_fd() == -1 && received.payload_fd() == -1,
              "reject output untouched");
      }
    }
    Check(Fds() == before, "receive destruction closes owned descriptors");
  }
  Check(Fds() == process_before, "case closes every owned descriptor");
}
void TransportControls() {
  ReceiveCase(role::Operation::kBegin, 0, 0, false, true);
  ReceiveCase(role::Operation::kApprove, 0, 0, false, true);
  ReceiveCase(role::Operation::kRelease, 0, 0, false, true);
  ReceiveCase(role::Operation::kAttach, 0, 0, false, true);
  ReceiveCase(role::Operation::kSuspend, 0, 0, false, true);
  ReceiveCase(role::Operation::kCreate, 2, 0, false, true);
  ReceiveCase(role::Operation::kBegin, 2, 0, false, false);
  ReceiveCase(role::Operation::kCreate, 0, 0, false, false);
  ReceiveCase(role::Operation::kCreate, 1, 0, false, false);
  ReceiveCase(role::Operation::kCreate, 3, 0, false, false);
  ReceiveCase(role::Operation::kCreate, 253, 0, false, false);
  ReceiveCase(role::Operation::kCreate, 2, -1, false, false);
  ReceiveCase(role::Operation::kCreate, 2, 1, false, false);
  ReceiveCase(role::Operation::kCreate, 2, 0, true, false);
  const size_t before = Fds();
  {
    Pair pair(false);
    role::Received received;
    Check(role::Receive(pair.receiver.get(), &received) == -1 && errno == EPROTO,
          "missing kernel identity options rejected");
    Check(role::ConfigureIdentityReception(pair.receiver.get(), true) == -1 && errno == EPROTO,
          "connected endpoint is not listener");
    Check(role::ConfigureIdentityReception(pair.receiver.get(), false) == 0, "configure exact endpoint");
    Check(role::Receive(pair.receiver.get(), &received) == -1 && (errno == EAGAIN || errno == EWOULDBLOCK),
          "empty nonblocking receive preserves errno");
    pair.sender.reset();
    Check(role::Receive(pair.receiver.get(), &received) == -1 && errno == EPROTO, "EOF is not an operation");
  }
  Check(Fds() == before, "transport cleanup complete");
}
void UninitializedControls() {
  role::Registry registry;
  role::GrantHandle handle{1, 1};
  Check(registry.IsActive(handle) == -1 && errno == ESHUTDOWN, "not initialized active");
  Check(registry.Connection(handle) == -1 && errno == ESHUTDOWN, "not initialized connection");
  Check(registry.FinishCreate(handle) == -1 && errno == ESHUTDOWN, "not initialized finish");
  Check(registry.Sweep() == -1 && errno == ESHUTDOWN, "not initialized sweep");
  Check(registry.Detach(handle) == -1 && errno == ESHUTDOWN, "not initialized detach");
  role::Received received;
  Check(registry.Suspend(handle, received) == -1 && errno == ESHUTDOWN, "not initialized suspend");
  Check(registry.Release(handle, received) == -1 && errno == ESHUTDOWN, "not initialized release");
  role::Descriptor connection;
  role::Challenge challenge{};
  Check(registry.Begin(&connection, received, &challenge) == -1 && errno == ESHUTDOWN,
        "not initialized begin");
  Check(registry.Attach(&connection, received, &handle) == -1 && errno == ESHUTDOWN,
        "not initialized attach");
  Check(registry.Approve(-1, received) == -1 && errno == ESHUTDOWN, "not initialized approve");
  role::SnapshotAuthority authority;
  Check(registry.AuthorizeCreate(handle, received, &authority) == -1 && errno == ESHUTDOWN,
        "not initialized create");
}
struct ThreadTransfer { int to_parent, from_parent; int result = -1; };
struct CallerDirectory { int tid, descriptor; };
void* CallerThread(void* opaque) {
  auto* transfer = static_cast<ThreadTransfer*>(opaque);
  // This fixture must also work when the local executor mounts ancestor procfs.
  // Have the actual thread resolve the kernel thread-self link. The production
  // PinCaller path still requires its separately verified matching proc view.
  role::Descriptor directory(open("/proc/thread-self", O_PATH | O_DIRECTORY | O_CLOEXEC));
  if (directory.get() < 0) return nullptr;
  const CallerDirectory record{static_cast<int>(syscall(SYS_gettid)), directory.get()};
  if (write(transfer->to_parent, &record, sizeof(record)) != sizeof(record)) return nullptr;
  directory.release();  // The parent now owns this descriptor in our shared table.
  pollfd ready{transfer->from_parent, POLLIN, 0};
  if (poll(&ready, 1, 2000) != 1 || !(ready.revents & POLLIN)) return nullptr;
  unsigned char release;
  if (read(transfer->from_parent, &release, sizeof(release)) != sizeof(release) || release != 1) return nullptr;
  transfer->result = 0;
  return nullptr;
}
void HeldCallerExitControl() {
  const size_t before = Fds();
  {
    int first[2], second[2];
    Check(pipe2(first, O_CLOEXEC) == 0 && pipe2(second, O_CLOEXEC) == 0, "owned caller transfer");
    role::Descriptor to_parent_read(first[0]), to_parent_write(first[1]);
    role::Descriptor from_parent_read(second[0]), from_parent_write(second[1]);
    ThreadTransfer transfer{to_parent_write.get(), from_parent_read.get()};
    pthread_t thread;
    Check(pthread_create(&thread, nullptr, CallerThread, &transfer) == 0, "owned caller thread");
    pollfd ready{to_parent_read.get(), POLLIN, 0};
    Check(poll(&ready, 1, 2000) == 1 && (ready.revents & POLLIN), "bounded caller readiness");
    CallerDirectory record{-1, -1};
    Check(read(to_parent_read.get(), &record, sizeof(record)) == sizeof(record) &&
          record.tid > 0 && record.descriptor >= 0, "owned caller descriptor transfer");
    role::Descriptor task(record.descriptor);
    Check(task.get() >= 0, "pin actual caller directory");
    struct statfs filesystem{};
    Check(fstatfs(task.get(), &filesystem) == 0 && filesystem.f_type == 0x9fa0,
          "held caller directory is procfs");
    struct stat held_before{}, held_after{};
    Check(fstat(task.get(), &held_before) == 0, "pinned caller identity");
    {
      role::Descriptor status(openat(task.get(), "status", O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
      char text[4096];
      Check(status.get() >= 0 && read(status.get(), text, sizeof(text)) > 0, "held live caller status");
    }
    const unsigned char release = 1;
    Check(write(from_parent_write.get(), &release, sizeof(release)) == sizeof(release), "release only owned caller");
    Check(pthread_join(thread, nullptr) == 0 && transfer.result == 0, "owned caller joined normally");
    Check(fstat(task.get(), &held_after) == 0 && held_after.st_dev == held_before.st_dev &&
          held_after.st_ino == held_before.st_ino, "held directory remains same object");
    errno = 0;
    role::Descriptor dead_status(openat(task.get(), "status", O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    const int error = errno;
    Check(dead_status.get() == -1 && (error == ENOENT || error == ESRCH),
          "dead held caller cannot resolve a fresh task by numeric name");
    printf("{\"control\":\"held_caller_exit\",\"openat_errno\":%d,"
           "\"owned_thread_joined\":true,\"same_held_inode\":true,"
           "\"numeric_tid_reuse_forced\":false,\"directory_source\":\"owned_thread_thread-self\"}\n", error);
  }
  Check(Fds() == before, "caller control restores descriptors");
}
}  // namespace
int main() {
  const size_t before = Fds();
  WireControls();
  TransportControls();
  UninitializedControls();
  HeldCallerExitControl();
  Check(Fds() == before, "all process-owned descriptors restored");
  printf("{\"state\":\"PASS_PROTOCOL_SCOPE\",\"assertions\":%u,\"real_receive_cases\":14,"
         "\"SCM_PIDFD_source\":\"kernel\",\"registry_authorization_positive_executed\":false,"
         "\"platform_filter_executed\":false,\"Main_actions\":0,\"factory_service_started\":false}\n", passed);
}
