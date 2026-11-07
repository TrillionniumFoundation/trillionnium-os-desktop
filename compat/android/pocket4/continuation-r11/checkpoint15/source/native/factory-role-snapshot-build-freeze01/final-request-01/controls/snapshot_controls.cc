// SPDX-License-Identifier: Apache-2.0
// New owned snapshot fixture. The included, pinned registry fixture supplies
// its exact child cleanup, role drop, kernel message and parent-approval helpers.
// Its ten-case entry is renamed and is never called by this four-case control.
#define main ReferenceRegistryControlMain
#include "../references/registry_controls.cc"
#undef main

#include "role_snapshot.h"
#include "berberis/kernel_api/proc_maps_factory_protocol.h"
#include "berberis/kernel_api/proc_maps_linux_compat.h"
#include <linux/magic.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/xattr.h>

namespace {
namespace provenance = berberis::proc_maps_provenance;
constexpr char kPayload[] = "owned role snapshot payload\nnot an application maps capture\n";
enum class SnapshotCase : int32_t { kValid = 1, kWrongSource = 2, kUnsealed = 3, kWrongSize = 4 };

const char* SnapshotName(SnapshotCase value) {
  switch (value) {
    case SnapshotCase::kValid: return "authorized_root_sealed_v2_snapshot";
    case SnapshotCase::kWrongSource: return "wrong_source_rejected_then_same_grant_recovers";
    case SnapshotCase::kUnsealed: return "unsealed_input_rejected_then_same_grant_recovers";
    case SnapshotCase::kWrongSize: return "size_mismatch_rejected_then_same_grant_recovers";
  }
  return "invalid";
}

// Initial positive coverage is the ordinary O_RDONLY source path. The separate
// local-nofollow-reopen01 evidence retains the inherited O_NOFOLLOW status-flag
// incompatibility; this fixture does not claim to fix or qualify that case.
void SendSnapshot(int connection, const unsigned char* token, SnapshotCase which) {
  role::Descriptor maps(open(which == SnapshotCase::kWrongSource ? "/dev/null" : "/proc/self/maps",
                             O_RDONLY | O_CLOEXEC));
  role::Descriptor payload(static_cast<int>(syscall(SYS_memfd_create, "owned-role-snapshot-input",
      static_cast<unsigned long>(MFD_CLOEXEC | MFD_ALLOW_SEALING))));
  Require(maps.get() >= 0 && payload.get() >= 0, "owned source and payload opened");
  Require(write(payload.get(), kPayload, sizeof(kPayload) - 1) == sizeof(kPayload) - 1,
          "owned fixed payload written");
  if (which != SnapshotCase::kUnsealed) {
    Require(fcntl(payload.get(), F_ADD_SEALS, provenance::kRequiredSeals) == 0,
            "owned input completely sealed");
  }
  auto request = Request(role::Operation::kCreate, token);
  const int flags = fcntl(maps.get(), F_GETFL);
  Require(flags >= 0, "actual source status flags");
  request.source_flags = static_cast<uint32_t>(flags);
  request.payload_size = sizeof(kPayload) - 1 + (which == SnapshotCase::kWrongSize ? 1 : 0);
  unsigned char bytes[role::kWireBytes];
  Require(role::EncodeRequest(request, bytes), "encode actual role create");
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } ancillary{};
  iovec vector{bytes, sizeof(bytes)};
  msghdr message{}; message.msg_iov = &vector; message.msg_iovlen = 1;
  message.msg_control = ancillary.bytes; message.msg_controllen = sizeof(ancillary.bytes);
  auto* header = CMSG_FIRSTHDR(&message);
  header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
  header->cmsg_len = CMSG_LEN(2 * sizeof(int));
  const int rights[2] = {maps.get(), payload.get()};
  memcpy(CMSG_DATA(header), rights, sizeof(rights));
  Wait(connection, POLLOUT);
  Require(sendmsg(connection, &message, MSG_NOSIGNAL) == sizeof(bytes), "send real source and sealed payload");
}

provenance::Origin VerifySnapshot(int descriptor, uint32_t expected_pid) {
  struct stat metadata{};
  provenance::KernelStatfs fs{};
  Require(fstat(descriptor, &metadata) == 0 &&
          syscall(SYS_fstatfs, static_cast<long>(descriptor), &fs) == 0,
          "actual snapshot inode and raw filesystem");
  Require(metadata.st_mode == (S_IFREG | 0444) && metadata.st_uid == 0 && metadata.st_gid == 0 &&
          metadata.st_nlink == 0 && metadata.st_size == sizeof(kPayload) - 1 &&
          fs.f_type == TMPFS_MAGIC, "snapshot is a real root-owned anonymous readonly inode");
  const int seals = fcntl(descriptor, F_GET_SEALS), flags = fcntl(descriptor, F_GETFD);
  Require(seals >= 0 && (static_cast<uint32_t>(seals) & provenance::kRequiredSeals) == provenance::kRequiredSeals &&
          flags == FD_CLOEXEC && lseek(descriptor, 0, SEEK_CUR) == 0,
          "snapshot sealed CLOEXEC and initial offset");
  char content[sizeof(kPayload)]{};
  Require(pread(descriptor, content, sizeof(content), 0) == sizeof(kPayload) - 1 &&
          memcmp(content, kPayload, sizeof(kPayload) - 1) == 0,
          "snapshot fixed payload bytes and EOF");
  unsigned char tag[provenance::kMaxTagBytes];
  const ssize_t count = fgetxattr(descriptor, provenance::kTagName, tag, sizeof(tag));
  provenance::Origin origin{};
  Require(count > 0 && provenance::DecodeOrigin(tag, static_cast<size_t>(count), &origin),
          "complete ordinary V2 origin tag decodes");
  Require(origin.words[provenance::kFactoryUsernsDevice] == provenance::kTrustedUserNamespaceDevice &&
          origin.words[provenance::kFactoryUsernsInode] == provenance::kTrustedUserNamespaceInode &&
          origin.words[provenance::kBackingDevice] == metadata.st_dev &&
          origin.words[provenance::kBackingInode] == metadata.st_ino &&
          origin.words[provenance::kBackingSize] == sizeof(kPayload) - 1 &&
          origin.words[provenance::kOriginTgid] == expected_pid &&
          origin.words[provenance::kOriginStartTicks] > 0,
          "tag binds actual backing inode and approved subject");
  char path[80]; const int length = snprintf(path, sizeof(path), "/proc/%u/maps", expected_pid);
  Require(length > 0 && static_cast<size_t>(length) < sizeof(path) &&
          origin.path_size == static_cast<size_t>(length) && !memcmp(path, origin.path, origin.path_size),
          "tag canonical tgid maps path");
  return origin;
}

bool SameStat(const struct stat& a, const struct stat& b) {
  return a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_mode == b.st_mode &&
      a.st_nlink == b.st_nlink && a.st_uid == b.st_uid && a.st_gid == b.st_gid &&
      a.st_rdev == b.st_rdev && a.st_size == b.st_size && a.st_blksize == b.st_blksize &&
      a.st_blocks == b.st_blocks && a.st_atim.tv_sec == b.st_atim.tv_sec &&
      a.st_atim.tv_nsec == b.st_atim.tv_nsec && a.st_mtim.tv_sec == b.st_mtim.tv_sec &&
      a.st_mtim.tv_nsec == b.st_mtim.tv_nsec && a.st_ctim.tv_sec == b.st_ctim.tv_sec &&
      a.st_ctim.tv_nsec == b.st_ctim.tv_nsec;
}

[[noreturn]] void RunSnapshotChild(int control, int parent_pidfd, role::Registry* inherited) {
  try {
    child_stage = 1;
    ExpectError(inherited->Sweep(), ESHUTDOWN, "COW child cannot operate root registry");
    CloseOtherInherited(control, parent_pidfd);
    child_stage = 2; ParentDeath(parent_pidfd); SetupRole(parent_pidfd);
    child_stage = 3; CommandOnly(control, Command::kReady);
    role::Descriptor client;
    std::array<unsigned char, role::kDigestBytes> token{};
    for (;;) {
      Wait(control, POLLIN, 5000);
      Control peek{};
      Require(recv(control, &peek, sizeof(peek), MSG_PEEK | MSG_DONTWAIT) == sizeof(peek),
              "owned snapshot command peek");
      const bool expects_descriptor = peek.command == Command::kEndpoint;
      auto input = ReadControl(control, peek.command, expects_descriptor);
      child_stage = 200 + static_cast<int>(input.value.command);
      switch (input.value.command) {
        case Command::kBegin:
          NewEndpoint(control, &client, Request(role::Operation::kBegin)); break;
        case Command::kSetToken:
          memcpy(token.data(), input.value.token, token.size()); Ack(control); break;
        case Command::kCreate:
          Require(input.value.status >= 1 && input.value.status <= 4, "fixed owned snapshot variant");
          SendSnapshot(client.get(), token.data(), static_cast<SnapshotCase>(input.value.status));
          CommandOnly(control, Command::kFrame); break;
        case Command::kEndpoint:
          VerifySnapshot(input.descriptor.get(), static_cast<uint32_t>(getpid())); Ack(control); break;
        case Command::kExit:
          client.reset(); Ack(control); _exit(0);
        default: throw std::runtime_error("unexpected owned snapshot command");
      }
    }
  } catch (...) {
    const int observed = errno;
    try { Control output; output.command = Command::kError; output.status = observed;
          output.pid = child_stage; SendControl(control, output); } catch (...) {}
    _exit(90);
  }
}

void SnapshotFrame(int control, role::Registry& registry, role::GrantHandle handle,
                   SnapshotCase which, role::Received* frame) {
  Control command; command.command = Command::kCreate; command.status = static_cast<int32_t>(which);
  SendControl(control, command); Frame(control, registry, handle, frame);
}

void RunSnapshotCase(SnapshotCase which, role::Registry& registry) {
  const size_t before = DescriptorCount();
  {
    Sockets control;
    role::Descriptor parent_pidfd(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(getpid()), 0UL)));
    Require(parent_pidfd.get() >= 0, "owned snapshot controller pidfd");
    const pid_t pid = fork(); Require(pid >= 0, "owned snapshot role fork");
    if (!pid) RunSnapshotChild(control.second.get(), parent_pidfd.get(), &registry);
    OwnedChild child(pid); control.second.reset();
    ReadControl(control.first.get(), Command::kReady);
    CommandOnly(control.first.get(), Command::kBegin);
    role::Challenge challenge;
    {
      EndpointInput endpoint; Endpoint(control.first.get(), &endpoint);
      Require(registry.Begin(&endpoint.connection, endpoint.message, &challenge) == 0 &&
              endpoint.connection.get() == -1 && challenge.visible_pid == static_cast<uint32_t>(pid),
              "real kernel role begin matches exact fork child");
    }
    Control token; token.command = Command::kSetToken; memcpy(token.token, challenge.token, sizeof(token.token));
    SendControl(control.first.get(), token); ReadControl(control.first.get(), Command::kAck);
    Approve(registry, challenge, pid);
    const auto handle = challenge.handle;
    Require(registry.IsActive(handle) == 0, "role grant actually approved");
    if (which != SnapshotCase::kValid) {
      const size_t negative_before = DescriptorCount();
      {
        role::Received frame; SnapshotFrame(control.first.get(), registry, handle, which, &frame);
        ExpectError(role::CreateAuthorizedSnapshot(registry, handle, frame), EINVAL,
                    "invalid file input rejected by actual maker");
        Require(registry.IsActive(handle) == 0, "failed creation finishes without leaving busy state");
      }
      Require(DescriptorCount() == negative_before, "negative creation restores all owned descriptors");
    }
    {
      role::Received frame; SnapshotFrame(control.first.get(), registry, handle, SnapshotCase::kValid, &frame);
      struct stat source{}, decoded{}; provenance::KernelStatfs fs{}, decoded_fs{};
      Require(fstat(frame.source_fd(), &source) == 0 &&
              syscall(SYS_fstatfs, static_cast<long>(frame.source_fd()), &fs) == 0,
              "independent actual source metadata oracle");
      role::Descriptor snapshot(role::CreateAuthorizedSnapshot(registry, handle, frame));
      Require(snapshot.get() >= 0, "real authorized root sealed snapshot created");
      const auto origin = VerifySnapshot(snapshot.get(), static_cast<uint32_t>(pid));
      Require(provenance::DecodeStat(origin, &decoded) && provenance::DecodeKernelStatfs(origin, &decoded_fs) &&
              SameStat(source, decoded) && !memcmp(&fs, &decoded_fs, sizeof(fs)),
              "all source stat fields and raw statfs bytes preserved");
      Require(fcntl(snapshot.get(), F_GETFL) == static_cast<int>(frame.request().source_flags),
              "actual snapshot status flags match original maps");
      Control transfer; transfer.command = Command::kEndpoint;
      SendControl(control.first.get(), transfer, snapshot.get()); ReadControl(control.first.get(), Command::kAck);
      Require(registry.IsActive(handle) == 0, "successful creation finishes same grant");
    }
    CommandOnly(control.first.get(), Command::kExit); ReadControl(control.first.get(), Command::kAck);
    child.Join(); ++direct_reaped;
    Require(registry.Sweep() == 0, "dead subject grant retired through actual PIDFD");
  }
  Require(DescriptorCount() == before, "owned snapshot case restored descriptor count");
  printf("{\"case\":\"%s\",\"state\":\"PASS\",\"actual_kernel_identity\":true,"
         "\"snapshot_created\":true,\"maps_formatter\":\"owned_fixture\",\"production_platform_policy\":false}\n",
         SnapshotName(which)); fflush(stdout);
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 2 || strcmp(argv[1], "--execute-once")) {
    puts("{\"state\":\"PLAN_ONLY\",\"owned_cases\":4,\"factory_service_started\":false,\"Main_actions\":0}");
    return argc == 1 ? 0 : 2;
  }
  try {
    Require(getuid() == 0 && geteuid() == 0 && syscall(SYS_gettid) == getpid(),
            "initial root owner main thread required");
    struct sigaction disposition{};
    Require(sigaction(SIGCHLD, nullptr, &disposition) == 0 && disposition.sa_handler == SIG_DFL &&
            !(disposition.sa_flags & SA_NOCLDWAIT), "exclusive owned child wait policy");
    deadline = Now() + 30000000000ULL;
    const size_t before = DescriptorCount();
    {
      role::Registry registry; const auto pair = PairDigest();
      Require(registry.Initialize(pair.data()) == 0, "actual initial-user-namespace registry");
      for (auto which : {SnapshotCase::kValid, SnapshotCase::kWrongSource,
                         SnapshotCase::kUnsealed, SnapshotCase::kWrongSize}) RunSnapshotCase(which, registry);
    }
    Require(DescriptorCount() == before && direct_reaped == 4 && !nested_reaped &&
            !forced_cleanup && !cleanup_unreaped, "all owned children and descriptors retired normally");
    printf("{\"state\":\"PASS_OWNED_ROLE_SNAPSHOT\",\"cases\":4,\"assertions\":%u,"
           "\"direct_children_reaped\":%u,\"nested_children_reaped\":%u,\"forced_cleanup\":%u,"
           "\"cleanup_unreaped\":%u,\"snapshot_created\":true,\"maps_formatter\":\"owned_fixture\","
           "\"platform_policy_qualified\":false,\"factory_service_started\":false,\"Main_actions\":0}\n",
           assertions, direct_reaped, nested_reaped, forced_cleanup, cleanup_unreaped);
    return 0;
  } catch (const std::exception& error) {
    const int observed = errno;
    printf("{\"state\":\"FAIL\",\"error_hex\":\"%s\",\"errno\":%d,\"direct_children_reaped\":%u,"
           "\"forced_cleanup\":%u,\"cleanup_unreaped\":%u,\"Main_actions\":0}\n",
           Hex(error.what()).c_str(), observed, direct_reaped, forced_cleanup, cleanup_unreaped);
    return 1;
  }
}
