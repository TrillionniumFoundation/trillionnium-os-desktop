// SPDX-License-Identifier: Apache-2.0
// Owned root listener and dispatch mechanism only. The existing registry
// fixture supplies exact PIDFD cleanup and its non-platform role-policy
// fixture. Its original ten-case main is compiled but is not called here.
#define main ReferenceRegistryControlMain
#include "../references/registry_controls.cc"
#undef main
#include "role_session.h"
#include "role_admission.h"
#include <limits.h>
#include <sys/un.h>
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

sockaddr_un owned_address{};
socklen_t owned_address_size = 0;
uint32_t owned_service_pid = 0;
unsigned owned_listener_serial = 0;
class OwnedListener {
 public:
  OwnedListener() {
    fd_.reset(socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0));
    Require(fd_.get() >= 0, "owned actual listener socket");
    owned_address = {}; owned_address.sun_family = AF_UNIX;
    const int size = snprintf(owned_address.sun_path + 1, sizeof(owned_address.sun_path) - 1,
                             "pocket4-role-owned-%ld-%u-%llu", static_cast<long>(getpid()),
                             ++owned_listener_serial, static_cast<unsigned long long>(Now()));
    Require(size > 0 && static_cast<size_t>(size) < sizeof(owned_address.sun_path) - 1, "owned abstract address bound");
    owned_address_size = offsetof(sockaddr_un, sun_path) + 1 + static_cast<socklen_t>(size);
    Require(bind(fd_.get(), reinterpret_cast<sockaddr*>(&owned_address), owned_address_size) == 0 &&
            listen(fd_.get(), 8) == 0, "new owned listener binds once, no fallback address");
    Require(role::ConfigureIdentityReception(fd_.get(), true) == 0,
            "identity reception configured before any client can connect");
    owned_service_pid = static_cast<uint32_t>(getpid());
  }
  int get() const { return fd_.get(); }
 private: role::Descriptor fd_;
};
role::Descriptor ConnectOwned() {
  role::Descriptor client(socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0));
  Require(client.get() >= 0 && connect(client.get(), reinterpret_cast<sockaddr*>(&owned_address), owned_address_size) == 0,
          "connect only the inherited owned test address");
  ucred peer{}; socklen_t size = sizeof(peer);
  Require(getsockopt(client.get(), SOL_SOCKET, SO_PEERCRED, &peer, &size) == 0 && size == sizeof(peer) &&
          !peer.uid && !peer.gid && peer.pid == static_cast<pid_t>(owned_service_pid),
          "owned fixture connects to its actual root controller");
  return client;
}
void SendAdmission(int control, role::Descriptor* client, role::Request* last, const role::Request& request) {
  *client = ConnectOwned(); *last = request; SendRole(client->get(), request); CommandOnly(control, Command::kFrame);
}
role::Admission AcceptAdmission(role::Registry& registry, const role::OwnerLease& lease, int listener) {
  role::Admission value{};
  Require(role::AdmitOne(registry, lease, listener, &value) == 0, "actual accepted admission and fixed acknowledgement");
  return value;
}
void ParentApprove(role::Registry& registry, const role::OwnerLease& lease, int listener,
                   const role::Challenge& challenge, pid_t pid, int expected = 0) {
  auto client = ConnectOwned(); auto request = Request(role::Operation::kApprove, challenge.token);
  request.child_pid_in_parent_namespace = static_cast<uint32_t>(pid);
  request.initial_uid = kFixtureUid; request.initial_gid = kFixtureGid;
  SendRole(client.get(), request);
  role::Admission result{}; result.handle = {UINT32_MAX, UINT64_MAX}; errno = 0;
  const int accepted = role::AdmitOne(registry, lease, listener, &result);
  if (expected) {
    ExpectError(accepted, expected, "actual parent admission rejects exact typed mismatch or duplicate");
    Require(result.handle.slot == UINT32_MAX && result.handle.serial == UINT64_MAX, "failed admission output untouched");
    Wait(client.get(), POLLHUP); unsigned char byte{};
    Require(recv(client.get(), &byte, 1, MSG_DONTWAIT) == 0, "failed parent admission closes without acknowledgement");
    return;
  }
  Require(accepted == 0 && result.reply.state == role::AdmissionState::kApproved &&
          result.handle.slot == challenge.handle.slot && result.handle.serial == challenge.handle.serial &&
          registry.IsActive(challenge.handle) == 0, "exact trusted-parent approval identifies its active grant");
  Wait(client.get(), POLLIN); role::AdmissionReply reply{};
  Require(role::ReceiveAdmissionReply(client.get(), request, &reply) == 0 &&
          reply.state == role::AdmissionState::kApproved, "parent receives the actual fixed approval acknowledgement");
}
void ListenerAttach(int control, role::Registry& registry, const role::OwnerLease& lease, int listener,
                    const role::Challenge& original) {
  CommandOnly(control, Command::kAttach); ReadControl(control, Command::kFrame);
  const auto result = AcceptAdmission(registry, lease, listener);
  Require(result.reply.state == role::AdmissionState::kAttached &&
          result.handle.slot == original.handle.slot && result.handle.serial == original.handle.serial &&
          registry.IsActive(original.handle) == 0, "same held caller lease reattaches through actual listener");
  CommandOnly(control, Command::kSetToken); auto reply = ReadControl(control, Command::kAck);
  Require(!memcmp(reply.value.token, original.token, sizeof(original.token)), "reattach keeps original one-time grant token");
}
void ListenerRebeginDenied(int control, role::Registry& registry, const role::OwnerLease& lease,
                           int listener, int expected) {
  CommandOnly(control, Command::kBegin); ReadControl(control, Command::kFrame);
  role::Admission output{}; output.handle = {UINT32_MAX, UINT64_MAX}; errno = 0;
  ExpectError(role::AdmitOne(registry, lease, listener, &output), expected,
              "live process cannot acquire a second grant through listener");
  Require(output.handle.slot == UINT32_MAX && output.handle.serial == UINT64_MAX, "rejected listener output unchanged");
}

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

// A revoked seqpacket connection with an unread request may report HUP|ERR
// and ECONNRESET. That is a closed transport, not an application response.
// Keep this check separate from the normal data/ack readiness helper.
int ObserveRevokedSession(int connection, uint64_t end) {
  if (connection < 0) { errno = EBADF; return -1; }
  const int before = errno;
  for (;;) {
    timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC, &time) < 0) return -1;
    const uint64_t now = static_cast<uint64_t>(time.tv_sec) * 1000000000ULL + time.tv_nsec;
    if (now >= end) { errno = ETIMEDOUT; return -1; }
    const int timeout = static_cast<int>(std::min<uint64_t>((end - now + 999999) / 1000000, 2000));
    pollfd entry{connection, static_cast<short>(POLLIN | POLLHUP), 0};
    const int polled = poll(&entry, 1, timeout);
    if (polled < 0 && errno == EINTR) continue;
    if (polled < 0) return -1;
    if (!polled) { errno = ETIMEDOUT; return -1; }
    if (entry.revents & POLLNVAL) { errno = EBADF; return -1; }
    if (polled != 1 || !(entry.revents & POLLHUP)) { errno = EPROTO; return -1; }
    unsigned char byte{};
    iovec vector{&byte, sizeof(byte)};
    msghdr message{}; message.msg_iov = &vector; message.msg_iovlen = 1;
    // No ancillary buffer: unexpected rights cannot be installed in this
    // process. MSG_CTRUNC still makes such a queued message a failure.
    const ssize_t count = recvmsg(connection, &message,
                                 MSG_DONTWAIT | MSG_TRUNC | MSG_CMSG_CLOEXEC);
    const int observed = errno;
    if (count < 0 && observed == EINTR) continue;
    if ((message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) || count > 0) {
      errno = EPROTO; return -1;
    }
    if (!count || (count < 0 && observed == ECONNRESET)) { errno = before; return 0; }
    errno = observed; return -1;
  }
}

[[noreturn]] void RunListenerChild(int control, int parent_pidfd, role::Registry* inherited) {
  try {
    child_stage = 1; ExpectError(inherited->Sweep(), ESHUTDOWN, "fork child cannot operate parent registry");
    CloseOtherInherited(control, parent_pidfd); ParentDeath(parent_pidfd); SetupRole(parent_pidfd);
    CommandOnly(control, Command::kReady);
    role::Descriptor client; role::Request last_request{}, last_admission{};
    std::array<unsigned char, role::kDigestBytes> token{};
    for (;;) {
      Wait(control, POLLIN, 5000); Control peek{};
      Require(recv(control, &peek, sizeof(peek), MSG_PEEK | MSG_DONTWAIT) == sizeof(peek), "session command peek");
      auto input = ReadControl(control, peek.command); child_stage = 300 + static_cast<int>(peek.command);
      switch (input.value.command) {
        case Command::kBegin: SendAdmission(control, &client, &last_admission, Request(role::Operation::kBegin)); break;
        case Command::kSetToken: {
          Wait(client.get(), POLLIN); role::AdmissionReply reply{};
          Require(role::ReceiveAdmissionReply(client.get(), last_admission, &reply) == 0,
                  "actual fixed admission reply binds the exact outstanding request");
          if (last_admission.operation == role::Operation::kBegin) {
            Require(reply.state == role::AdmissionState::kPending && reply.visible_pid == static_cast<uint32_t>(getpid()),
                    "Begin returns only its pending challenge and actual visible PID");
            memcpy(token.data(), reply.token, token.size());
          } else Require(reply.state == role::AdmissionState::kAttached &&
                         last_admission.operation == role::Operation::kAttach, "Attach receives the exact active acknowledgement");
          Control ack; ack.command = Command::kAck; memcpy(ack.token, token.data(), token.size()); SendControl(control, ack); break;
        }
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
          } else SendAdmission(control, &client, &last_admission, Request(role::Operation::kAttach, token.data()));
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
            Require(ObserveRevokedSession(client.get(),
                        std::min<uint64_t>(deadline, Now() + 2000000000ULL)) == 0,
                    "revoked session is closed without a response or delivered rights");
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

void RunListenerCase(SessionCase which, role::Registry& registry) {
  const size_t before = DescriptorCount();
  {
    OwnedListener listener;
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
    if (!pid) RunListenerChild(control.second.get(), self_pidfd.get(), &registry);
    OwnedChild child(pid); control.second.reset(); ReadControl(control.first.get(), Command::kReady);
    CommandOnly(control.first.get(), Command::kBegin); ReadControl(control.first.get(), Command::kFrame);
    const auto admitted = AcceptAdmission(registry, lease, listener.get());
    Require(admitted.reply.state == role::AdmissionState::kPending && admitted.reply.visible_pid == static_cast<uint32_t>(pid),
            "actual listener Begin yields only the precise pending child");
    role::Challenge challenge{}; challenge.handle = admitted.handle; challenge.visible_pid = admitted.reply.visible_pid;
    memcpy(challenge.token, admitted.reply.token, sizeof(challenge.token));
    ExpectError(registry.IsActive(challenge.handle), EAGAIN, "pending challenge is not snapshot authority");
    CommandOnly(control.first.get(), Command::kSetToken); auto token_reply = ReadControl(control.first.get(), Command::kAck);
    Require(!memcmp(token_reply.value.token, challenge.token, sizeof(challenge.token)), "child receives factory-generated challenge over real listener");
    if (which == SessionCase::kCreateRelease) {
      Require(pid < INT_MAX, "wrong typed PID remains representable");
      ParentApprove(registry, lease, listener.get(), challenge, pid + 1, EPERM);
      ExpectError(registry.IsActive(challenge.handle), EAGAIN, "wrong parent input did not authorize or renew pending grant");
    }
    ParentApprove(registry, lease, listener.get(), challenge, pid); const auto handle = challenge.handle;
    if (which == SessionCase::kCreateRelease) ParentApprove(registry, lease, listener.get(), challenge, pid, EALREADY);
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
        ReadReply(control.first.get()); ListenerAttach(control.first.get(), registry, lease, listener.get(), challenge);
      }
      SuccessfulCreate(control.first.get(), registry, handle, lease);
      Release(control.first.get(), registry, handle, lease);
      ListenerRebeginDenied(control.first.get(), registry, lease, listener.get(), EALREADY);
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
      ListenerRebeginDenied(control.first.get(), registry, lease, listener.get(),
          which == SessionCase::kOwnerClose || which == SessionCase::kOwnerData ? ECANCELED : EALREADY);
    }
    CommandOnly(control.first.get(), Command::kExit); ReadControl(control.first.get(), Command::kAck);
    child.Join(); ++direct_reaped;
    Require(registry.Sweep() == 0, "dead role tombstone removed only after actual PIDFD exit");
    CommandOnly(owner_control.first.get(), Command::kExit); ReadControl(owner_control.first.get(), Command::kAck);
    owner.Join(); ++direct_reaped;
  }
  Require(DescriptorCount() == before, "entire owned dispatch case restores descriptor count");
  printf("{\"case\":\"%s\",\"state\":\"PASS\",\"actual_dispatch\":true,\"actual_listener_admission\":true,"
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
          SessionCase::kSuspendAttach, SessionCase::kOwnerData}) RunListenerCase(which, registry);
    }
    Require(DescriptorCount() == before && direct_reaped == 18 && !nested_reaped &&
        !forced_cleanup && !cleanup_unreaped, "all exact owned role/owner children and descriptors retired normally");
    printf("{\"state\":\"PASS_OWNED_LISTENER_AND_SESSION\",\"cases\":9,\"assertions\":%u,"
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
