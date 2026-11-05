// SPDX-License-Identifier: Apache-2.0
// Owned root mechanism only. The existing registry fixture supplies exact
// PIDFD child cleanup and its explicit non-platform role-policy fixture.
// Its original ten-case main is compiled but is not called here.
#define main ReferenceRegistryControlMain
#include "../references/registry_controls.cc"
#undef main
#include "role_session.h"
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
#include "../references/snapshot_verification.h"

enum class SessionCase : int32_t {
  kCreateRelease = 1, kMakerError, kWrongToken, kUnsupported, kPeerClose,
  kOwnerClose, kTimeout, kSuspendAttach, kOwnerData
};
const char* SessionName(SessionCase which) {
  switch (which) {
    case SessionCase::kCreateRelease: return "authorized_snapshot_dispatched_and_released";
    case SessionCase::kMakerError: return "maker_error_reply_then_same_grant_recovers";
    case SessionCase::kWrongToken: return "wrong_token_revokes_without_response";
    case SessionCase::kUnsupported: return "unsupported_active_operation_revokes";
    case SessionCase::kPeerClose: return "peer_hup_revokes_queued_input_rights";
    case SessionCase::kOwnerClose: return "service_owner_hup_revokes";
    case SessionCase::kTimeout: return "single_request_deadline_revokes";
    case SessionCase::kSuspendAttach: return "suspend_ack_detach_same_lease_reattach";
    case SessionCase::kOwnerData: return "unexpected_owner_control_data_revokes";
  }
  return "invalid";
}

role::Request SendSessionCreate(int connection, const unsigned char* token, bool wrong_source,
                                bool wrong_token) {
  role::Descriptor maps(open(wrong_source ? "/dev/null" : "/proc/self/maps", O_RDONLY | O_CLOEXEC));
  role::Descriptor payload(static_cast<int>(syscall(SYS_memfd_create, "owned-role-session-input",
      static_cast<unsigned long>(MFD_CLOEXEC | MFD_ALLOW_SEALING))));
  Require(maps.get() >= 0 && payload.get() >= 0, "owned session source and payload");
  Require(write(payload.get(), kPayload, sizeof(kPayload) - 1) == sizeof(kPayload) - 1 &&
      fcntl(payload.get(), F_ADD_SEALS, provenance::kRequiredSeals) == 0, "actual sealed fixed payload");
  auto request = Request(role::Operation::kCreate, token);
  const int flags = fcntl(maps.get(), F_GETFL), fd_flags = fcntl(maps.get(), F_GETFD);
  Require(flags >= 0 && fd_flags == FD_CLOEXEC, "actual source descriptor flags");
  request.source_flags = static_cast<uint32_t>(flags); request.original_fd_flags = fd_flags;
  request.payload_size = sizeof(kPayload) - 1;
  if (wrong_token) request.token[0] ^= 0x80;
  unsigned char bytes[role::kWireBytes];
  Require(role::EncodeRequest(request, bytes), "encode actual create request");
  union { cmsghdr align; unsigned char bytes[CMSG_SPACE(2 * sizeof(int))]; } ancillary{};
  iovec vector{bytes, sizeof(bytes)}; msghdr message{};
  message.msg_iov = &vector; message.msg_iovlen = 1;
  message.msg_control = ancillary.bytes; message.msg_controllen = sizeof(ancillary.bytes);
  auto* header = CMSG_FIRSTHDR(&message); header->cmsg_level = SOL_SOCKET;
  header->cmsg_type = SCM_RIGHTS; header->cmsg_len = CMSG_LEN(2 * sizeof(int));
  const int rights[2] = {maps.get(), payload.get()}; memcpy(CMSG_DATA(header), rights, sizeof(rights));
  Wait(connection, POLLOUT);
  Require(sendmsg(connection, &message, MSG_DONTWAIT | MSG_NOSIGNAL) == sizeof(bytes), "send actual source and payload rights");
  return request;
}

[[noreturn]] void RunSessionChild(int control, int parent_pidfd, role::Registry* inherited) {
  try {
    child_stage = 1; ExpectError(inherited->Sweep(), ESHUTDOWN, "fork child cannot operate parent registry");
    CloseOtherInherited(control, parent_pidfd); ParentDeath(parent_pidfd); SetupRole(parent_pidfd);
    CommandOnly(control, Command::kReady);
    role::Descriptor client; role::Request last_request{};
    std::array<unsigned char, role::kDigestBytes> token{};
    for (;;) {
      Wait(control, POLLIN, 5000); Control peek{};
      Require(recv(control, &peek, sizeof(peek), MSG_PEEK | MSG_DONTWAIT) == sizeof(peek), "session command peek");
      auto input = ReadControl(control, peek.command); child_stage = 300 + static_cast<int>(peek.command);
      switch (input.value.command) {
        case Command::kBegin: NewEndpoint(control, &client, Request(role::Operation::kBegin)); break;
        case Command::kSetToken:
          memcpy(token.data(), input.value.token, token.size()); Ack(control); break;
        case Command::kCreate:
          last_request = SendSessionCreate(client.get(), token.data(), input.value.status == 1, input.value.status == 2);
          if (input.value.status == 3) client.reset();
          CommandOnly(control, Command::kFrame); break;
        case Command::kSuspend:
          last_request = Request(role::Operation::kSuspend, token.data());
          SendRole(client.get(), last_request); CommandOnly(control, Command::kFrame); break;
        case Command::kAttach:
          if (input.value.status == 1) {
            last_request = Request(role::Operation::kAttach, token.data());
            SendRole(client.get(), last_request); CommandOnly(control, Command::kFrame);
          } else NewEndpoint(control, &client, Request(role::Operation::kAttach, token.data()));
          break;
        case Command::kRelease:
          last_request = Request(role::Operation::kRelease, token.data());
          SendRole(client.get(), last_request); CommandOnly(control, Command::kFrame); break;
        case Command::kEndpoint: {
          Wait(client.get(), static_cast<short>(POLLIN | POLLHUP));
          const size_t before = DescriptorCount(); role::Response response{}; role::Descriptor output;
          Require(role::ReceiveResponse(client.get(), last_request, &response, &output) == 0 &&
              response.error == static_cast<uint32_t>(input.value.status), "real fixed response binds outstanding request");
          const bool positive = last_request.operation == role::Operation::kCreate && !input.value.status;
          Require(response.has_snapshot == positive && (output.get() >= 0) == positive,
                  "exactly successful create publishes a real descriptor");
          if (positive) VerifySnapshot(output.get(), static_cast<uint32_t>(getpid()), last_request.source_flags);
          output.reset(); Require(DescriptorCount() == before, "child response has no leaked rights");
          if (last_request.operation == role::Operation::kRelease || last_request.operation == role::Operation::kSuspend) {
            Wait(client.get(), POLLHUP); unsigned char extra{};
            Require(recv(client.get(), &extra, 1, MSG_DONTWAIT) == 0, "acknowledgement followed by exact peer close");
            client.reset();
          }
          Ack(control); break;
        }
        case Command::kObserveDetach:
          if (client.get() >= 0) {
            Wait(client.get(), POLLHUP); unsigned char byte{};
            Require(recv(client.get(), &byte, 1, MSG_DONTWAIT) == 0, "revoked session has no response or published fd");
            client.reset();
          }
          Ack(control); break;
        case Command::kExit: client.reset(); Ack(control); _exit(0);
        default: throw std::runtime_error("unknown owned session command");
      }
    }
  } catch (...) {
    const int observed = errno;
    try { Control output; output.command = Command::kError; output.status = observed;
          output.pid = child_stage; SendControl(control, output); } catch (...) {}
    _exit(90);
  }
}

// Separate live root service owner. It creates the lease socket itself, so the
// kernel peer credentials/PIDFD refer to this actual child, not the inherited
// controller socketpair's creator. It never approves or replaces a role parent.
[[noreturn]] void RunLeaseChild(int control, int parent_pidfd) {
  try {
    CloseOtherInherited(control, parent_pidfd); ParentDeath(parent_pidfd);
    Sockets lease; Control endpoint; endpoint.command = Command::kEndpoint;
    SendControl(control, endpoint, lease.second.get()); lease.second.reset();
    for (;;) {
      Wait(control, POLLIN, 5000); Control peek{};
      Require(recv(control, &peek, sizeof(peek), MSG_PEEK | MSG_DONTWAIT) == sizeof(peek), "lease command peek");
      ReadControl(control, peek.command);
      if (peek.command == Command::kClose) { lease.first.reset(); Ack(control); }
      else if (peek.command == Command::kCreate) {
        const unsigned char byte = 1;
        Require(send(lease.first.get(), &byte, 1, MSG_DONTWAIT | MSG_NOSIGNAL) == 1, "actual unexpected owner data"); Ack(control);
      } else if (peek.command == Command::kExit) { lease.first.reset(); Ack(control); _exit(0); }
      else throw std::runtime_error("unexpected owned lease command");
    }
  } catch (...) { _exit(91); }
}

role::DispatchResult Dispatch(role::Registry& registry, role::GrantHandle handle,
                              const role::OwnerLease& lease, int expected_error = 0) {
  role::DispatchResult output{}; output.operation = role::Operation::kBegin;
  output.operation_error = UINT32_MAX; output.snapshot_published = true;
  errno = 0; const int result = role::DispatchOne(registry, handle, lease, &output);
  if (expected_error) {
    ExpectError(result, expected_error, "dispatch rejects exact failure");
    Require(output.operation == role::Operation::kBegin && output.operation_error == UINT32_MAX &&
        output.snapshot_published, "failed dispatcher leaves result untouched");
    ExpectError(registry.IsActive(handle), ESHUTDOWN, "failure leaves a live process tombstone");
  } else Require(result == 0, "actual dispatcher completed one transition");
  return output;
}
void Instruct(int control, Command command, int status = 0) {
  Control input; input.command = command; input.status = status; SendControl(control, input);
}
void ReadReply(int control, int expected_error = 0) {
  Instruct(control, Command::kEndpoint, expected_error); ReadControl(control, Command::kAck);
}
void SuccessfulCreate(int control, role::Registry& registry, role::GrantHandle handle,
                      const role::OwnerLease& lease) {
  Instruct(control, Command::kCreate); ReadControl(control, Command::kFrame);
  const auto result = Dispatch(registry, handle, lease);
  Require(result.operation == role::Operation::kCreate && !result.operation_error && result.snapshot_published &&
      result.state == role::DispatchState::kReplySent && registry.IsActive(handle) == 0,
      "successful dispatch finished and published within the same grant");
  ReadReply(control);
}
void Release(int control, role::Registry& registry, role::GrantHandle handle, const role::OwnerLease& lease) {
  Instruct(control, Command::kRelease); ReadControl(control, Command::kFrame);
  const auto result = Dispatch(registry, handle, lease);
  Require(result.operation == role::Operation::kRelease && !result.operation_error && !result.snapshot_published &&
      result.state == role::DispatchState::kReleased, "release acknowledgement follows actual revocation");
  ExpectError(registry.IsActive(handle), ESHUTDOWN, "released grant remains revoked while child alive");
  ReadReply(control);
}

void RunSessionCase(SessionCase which, role::Registry& registry) {
  const size_t before = DescriptorCount();
  {
    Sockets owner_control;
    role::Descriptor self_pidfd(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(getpid()), 0UL)));
    Require(self_pidfd.get() >= 0, "fixture controller pidfd");
    const pid_t owner_pid = fork(); Require(owner_pid >= 0, "owned root lease process");
    if (!owner_pid) RunLeaseChild(owner_control.second.get(), self_pidfd.get());
    OwnedChild owner(owner_pid); owner_control.second.reset();
    auto endpoint = ReadControl(owner_control.first.get(), Command::kEndpoint, true);
    role::OwnerLease lease;
    Require(lease.Initialize(&endpoint.descriptor) == 0 && endpoint.descriptor.get() < 0 && lease.Verify() == 0,
            "live actual root service-owner lease initialized");
    Sockets control; const pid_t pid = fork(); Require(pid >= 0, "owned role child");
    if (!pid) RunSessionChild(control.second.get(), self_pidfd.get(), &registry);
    OwnedChild child(pid); control.second.reset(); ReadControl(control.first.get(), Command::kReady);
    CommandOnly(control.first.get(), Command::kBegin); role::Challenge challenge;
    {
      EndpointInput input; Endpoint(control.first.get(), &input);
      Require(registry.Begin(&input.connection, input.message, &challenge) == 0 && input.connection.get() < 0 &&
          challenge.visible_pid == static_cast<uint32_t>(pid), "actual role begin bound to exact fork child");
    }
    Control token; token.command = Command::kSetToken; memcpy(token.token, challenge.token, sizeof(token.token));
    SendControl(control.first.get(), token); ReadControl(control.first.get(), Command::kAck);
    Approve(registry, challenge, pid); const auto handle = challenge.handle;
    Require(registry.IsActive(handle) == 0, "actual independent parent approval");
    if (which == SessionCase::kCreateRelease || which == SessionCase::kMakerError || which == SessionCase::kSuspendAttach) {
      if (which == SessionCase::kMakerError) {
        const size_t negative_before = DescriptorCount();
        Instruct(control.first.get(), Command::kCreate, 1); ReadControl(control.first.get(), Command::kFrame);
        const auto output = Dispatch(registry, handle, lease);
        Require(output.operation == role::Operation::kCreate && output.operation_error == EINVAL &&
            !output.snapshot_published && registry.IsActive(handle) == 0, "maker rejection finishes without revoking valid grant");
        ReadReply(control.first.get(), EINVAL);
        Require(DescriptorCount() == negative_before, "negative dispatch releases both input rights");
      }
      if (which == SessionCase::kSuspendAttach) {
        Instruct(control.first.get(), Command::kSuspend); ReadControl(control.first.get(), Command::kFrame);
        const auto output = Dispatch(registry, handle, lease);
        Require(output.operation == role::Operation::kSuspend && !output.operation_error && !output.snapshot_published &&
            output.state == role::DispatchState::kDetached, "suspend acknowledged then explicitly detached");
        ReadReply(control.first.get()); Attach(control.first.get(), registry, handle);
      }
      SuccessfulCreate(control.first.get(), registry, handle, lease);
      Release(control.first.get(), registry, handle, lease);
      RebeginDenied(control.first.get(), registry);
    } else {
      int expected = 0;
      if (which == SessionCase::kWrongToken || which == SessionCase::kPeerClose) {
        Instruct(control.first.get(), Command::kCreate, which == SessionCase::kWrongToken ? 2 : 3);
        ReadControl(control.first.get(), Command::kFrame); expected = which == SessionCase::kWrongToken ? EPERM : EPIPE;
      } else if (which == SessionCase::kUnsupported) {
        Instruct(control.first.get(), Command::kAttach, 1); ReadControl(control.first.get(), Command::kFrame); expected = EPROTO;
      } else if (which == SessionCase::kOwnerClose || which == SessionCase::kOwnerData) {
        CommandOnly(owner_control.first.get(), which == SessionCase::kOwnerClose ? Command::kClose : Command::kCreate);
        ReadControl(owner_control.first.get(), Command::kAck);
        Instruct(control.first.get(), Command::kCreate); ReadControl(control.first.get(), Command::kFrame); expected = ECANCELED;
      } else expected = ETIMEDOUT;
      Dispatch(registry, handle, lease, expected);
      CommandOnly(control.first.get(), Command::kObserveDetach); ReadControl(control.first.get(), Command::kAck);
      RebeginDenied(control.first.get(), registry);
    }
    CommandOnly(control.first.get(), Command::kExit); ReadControl(control.first.get(), Command::kAck);
    child.Join(); ++direct_reaped;
    Require(registry.Sweep() == 0, "dead role tombstone removed only after actual PIDFD exit");
    CommandOnly(owner_control.first.get(), Command::kExit); ReadControl(owner_control.first.get(), Command::kAck);
    owner.Join(); ++direct_reaped;
  }
  Require(DescriptorCount() == before, "entire owned dispatch case restores descriptor count");
  printf("{\"case\":\"%s\",\"state\":\"PASS\",\"actual_dispatch\":true,"
         "\"platform_policy_qualified\":false}\n", SessionName(which)); fflush(stdout);
}
}

int main(int argc, char** argv) {
  if (argc != 2 || strcmp(argv[1], "--execute-once")) {
    puts("{\"state\":\"PLAN_ONLY\",\"owned_cases\":9,\"root_children\":9,\"role_children\":9,"
         "\"factory_service_started\":false,\"Main_actions\":0}");
    return argc == 1 ? 0 : 2;
  }
  try {
    Require(getuid() == 0 && geteuid() == 0 && syscall(SYS_gettid) == getpid(), "root owner main thread required");
    struct sigaction disposition{};
    Require(sigaction(SIGCHLD, nullptr, &disposition) == 0 && disposition.sa_handler == SIG_DFL &&
        !(disposition.sa_flags & SA_NOCLDWAIT), "exclusive owned child wait policy");
    deadline = Now() + 30000000000ULL;
    const size_t before = DescriptorCount();
    {
      role::Registry registry; const auto pair = PairDigest();
      Require(registry.Initialize(pair.data()) == 0, "actual initial-user-namespace registry");
      for (auto which : {SessionCase::kCreateRelease, SessionCase::kMakerError, SessionCase::kWrongToken,
          SessionCase::kUnsupported, SessionCase::kPeerClose, SessionCase::kOwnerClose, SessionCase::kTimeout,
          SessionCase::kSuspendAttach, SessionCase::kOwnerData}) RunSessionCase(which, registry);
    }
    Require(DescriptorCount() == before && direct_reaped == 18 && !nested_reaped &&
        !forced_cleanup && !cleanup_unreaped, "all exact owned role/owner children and descriptors retired normally");
    printf("{\"state\":\"PASS_OWNED_AUTHENTICATED_SESSION_DISPATCH\",\"cases\":9,\"assertions\":%u,"
           "\"direct_children_reaped\":%u,\"forced_cleanup\":%u,\"cleanup_unreaped\":%u,"
           "\"platform_policy_qualified\":false,\"engine_connected\":false,\"Main_actions\":0}\n",
           assertions, direct_reaped, forced_cleanup, cleanup_unreaped);
    return 0;
  } catch (const std::exception& error) {
    const int observed = errno;
    printf("{\"state\":\"FAIL\",\"error_hex\":\"%s\",\"errno\":%d,\"direct_children_reaped\":%u,"
           "\"forced_cleanup\":%u,\"cleanup_unreaped\":%u,\"Main_actions\":0}\n",
           Hex(error.what()).c_str(), observed, direct_reaped, forced_cleanup, cleanup_unreaped);
    return 1;
  }
}
