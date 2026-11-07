// SPDX-License-Identifier: Apache-2.0
// Actual owned process/FD controls for the service OwnerLease. A separate
// owned root peer supplies kernel socket credentials; no capability or policy
// change, ambient service, application, namespace or allocator hook is used.
#define main ReferenceOwnerLeaseControlMain
#include "../references/registry_controls.cc"
#undef main
#include "role_session.h"
#include <new>
#include <iterator>
#include <sched.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>

namespace {
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

std::vector<int> FdNumbers() {
  DIR* directory = opendir("/proc/self/fd"); Require(directory != nullptr, "own fd enumeration");
  const int own = dirfd(directory); std::vector<int> result;
  while (dirent* entry = readdir(directory)) {
    char* end = nullptr; const long value = strtol(entry->d_name, &end, 10);
    if (end != entry->d_name && !*end && value >= 0 && value <= INT32_MAX && value != own)
      result.push_back(static_cast<int>(value));
  }
  Require(closedir(directory) == 0, "own enumeration closed");
  std::sort(result.begin(), result.end()); return result;
}
class Mapping {
 public:
  Mapping(size_t size, bool shared) : size_(size) {
    memory_ = mmap(nullptr, size, PROT_READ | PROT_WRITE,
                   (shared ? MAP_SHARED : MAP_PRIVATE) | MAP_ANONYMOUS, -1, 0);
    Require(memory_ != MAP_FAILED, "new owned anonymous mapping");
  }
  ~Mapping() { const int before = errno; if (memory_ != MAP_FAILED) munmap(memory_, size_); errno = before; }
  void* get() const { return memory_; }
  Mapping(const Mapping&) = delete;
  Mapping& operator=(const Mapping&) = delete;
 private:
  size_t size_; void* memory_ = MAP_FAILED;
};
class LeaseStorage {
 public:
  LeaseStorage() : memory_(4096, false), object_(::new(memory_.get()) role::OwnerLease) {
    static_assert(sizeof(role::OwnerLease) <= 4096);
  }
  ~LeaseStorage() { if (destroy_) object_->~OwnerLease(); }
  role::OwnerLease* get() const { return object_; }
  void DestroyOwner() { Require(destroy_, "single owner destruction"); object_->~OwnerLease(); destroy_ = false; }
  // Only used by the preimage negative after the foreign destructor entered.
  // The parent then never reads, invokes, or deletes the already-freed Impl.
  void AbandonDestroyedPreimage() { destroy_ = false; }
 private:
  Mapping memory_; role::OwnerLease* object_; bool destroy_ = true;
};
struct ChildArguments {
  role::OwnerLease* registry;
  int parent_pidfd;
  volatile uint32_t entered{}, completed{}, caller_pid{}, caller_tid{};
  volatile int before_errno{}, after_errno{}, failed_errno{};
};
int DestroyInherited(void* opaque) {
  auto* input = static_cast<ChildArguments*>(opaque);
  try {
    ParentDeath(input->parent_pidfd);
    input->caller_pid = static_cast<uint32_t>(getpid());
    input->caller_tid = static_cast<uint32_t>(syscall(SYS_gettid));
    errno = EUCLEAN; input->before_errno = errno; input->entered = 1;
    input->registry->~OwnerLease();
    input->after_errno = errno; input->completed = 1; return 0;
  } catch (...) { input->failed_errno = errno; return 90; }
}
enum class Kind { kSharedFiles, kPrivateFiles, kPrivateVm };
const char* KindName(Kind value) {
  switch (value) {
    case Kind::kSharedFiles: return "foreign_CLONE_VM_CLONE_FILES";
    case Kind::kPrivateFiles: return "foreign_CLONE_VM_private_fdtable";
    case Kind::kPrivateVm: return "foreign_fork_COW";
  }
  return "invalid";
}
void DestructionCase(Kind kind, bool preimage) {
  const auto case_before = FdNumbers();
  size_t owned_descriptors = 0, closed_in_foreign = 0;
  {
    role::Descriptor parent_pidfd(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(getpid()), 0UL)));
    Require(parent_pidfd.get() >= 0, "exact controller pidfd");
    Sockets owner_control;
    const pid_t owner_pid = fork(); Require(owner_pid >= 0, "separate owned root lease peer");
    if (!owner_pid) RunLeaseChild(owner_control.second.get(), parent_pidfd.get());
    OwnedChild owner(owner_pid); owner_control.second.reset();
    LeaseStorage storage;
    const auto before_init = FdNumbers();
    auto endpoint = ReadControl(owner_control.first.get(), Command::kEndpoint, true);
    Require(storage.get()->Initialize(&endpoint.descriptor) == 0 && endpoint.descriptor.get() < 0 &&
            storage.get()->Verify() == 0, "actual service-owner lease initialized from kernel root peer");
    const auto after_init = FdNumbers(); std::vector<int> owned;
    std::set_difference(after_init.begin(), after_init.end(), before_init.begin(), before_init.end(),
                        std::back_inserter(owned));
    Require(!owned.empty(), "actual OwnerLease holds independently observable descriptors");
    owned_descriptors = owned.size();
    // Allocate before spawning: observation must not throw before the exact
    // child reaches its existing reap guard, or open an FD that hides the bug.
    std::vector<bool> still_open(owned.size());
    std::vector<struct stat> identities;
    for (int fd : owned) { struct stat value{}; Require(fstat(fd, &value) == 0, "held owner descriptor identity"); identities.push_back(value); }
    Mapping shared(sizeof(ChildArguments), true);
    auto* input = ::new(shared.get()) ChildArguments{storage.get(), parent_pidfd.get()};
    {
      Mapping stack(131072, false);
      int kernel_pidfd = -1; pid_t child_pid;
      if (kind == Kind::kPrivateVm) {
        child_pid = fork();
        if (!child_pid) _exit(DestroyInherited(input));
        if (child_pid > 0) kernel_pidfd = static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(child_pid), 0UL));
      } else {
        const int flags = CLONE_VM | CLONE_VFORK | CLONE_PIDFD | SIGCHLD |
                          (kind == Kind::kSharedFiles ? CLONE_FILES : 0);
        // Separate owned stack and no concurrent allocator activity: the sole
        // parent is suspended by VFORK until this destructor callback exits.
        child_pid = clone(DestroyInherited, static_cast<unsigned char*>(stack.get()) + 131072,
                          flags, input, &kernel_pidfd, nullptr, nullptr);
      }
      if (preimage && input->entered) storage.AbandonDestroyedPreimage();
      Require(child_pid > 0, "actual owned foreign process created");
      role::Descriptor held_child(kernel_pidfd);
      // Sample before opening another FD: the preimage must not be hidden by
      // immediate descriptor-number reuse. No freed Impl is read by the parent.
      for (size_t i = 0; i < owned.size(); ++i) { errno = 0; const int flags = fcntl(owned[i], F_GETFD);
        still_open[i] = flags >= 0; if (flags < 0 && errno == EBADF) ++closed_in_foreign; }
      OwnedChild child(child_pid);
      Require(held_child.get() >= 0 && fcntl(held_child.get(), F_GETFD) == FD_CLOEXEC,
              "kernel child pidfd retained across observation");
      child.Join(); ++direct_reaped;
      Require(input->entered && input->completed && input->caller_pid == static_cast<uint32_t>(child_pid) &&
          input->caller_pid != static_cast<uint32_t>(getpid()) && input->caller_tid == input->caller_pid,
          "destructor actually executed in the exact foreign process");
      if (preimage) {
        Require(kind == Kind::kSharedFiles && closed_in_foreign == owned.size(),
                "preimage foreign destructor actually closed every parent OwnerLease descriptor");
      } else {
        Require(closed_in_foreign == 0 && input->before_errno == EUCLEAN && input->after_errno == EUCLEAN,
                "candidate foreign destructor preserves owner descriptors and caller errno");
        for (size_t i = 0; i < owned.size(); ++i) {
          struct stat current{};
          Require(still_open[i] && fstat(owned[i], &current) == 0 && current.st_dev == identities[i].st_dev &&
              current.st_ino == identities[i].st_ino && current.st_mode == identities[i].st_mode,
              "each held owner descriptor retained its actual object");
        }
        Require(storage.get()->Verify() == 0, "original owner OwnerLease remains operational after foreign destruction");
      }
    }
    if (!preimage) {
      Require(FdNumbers() == after_init, "candidate foreign child left the exact owner fd set");
      errno = EUCLEAN; storage.DestroyOwner(); const int after = errno;
      Require(after == EUCLEAN, "actual owner destructor preserves errno");
    }
    Require(FdNumbers() == before_init, "actual OwnerLease resources fully released without reuse or double destruction");
    CommandOnly(owner_control.first.get(), Command::kExit);
    ReadControl(owner_control.first.get(), Command::kAck); owner.Join(); ++direct_reaped;
  }
  Require(FdNumbers() == case_before, "all owned case descriptors returned to entry set");
  printf("{\"case\":\"%s\",\"state\":\"%s\",\"owned_descriptors\":%zu,"
         "\"foreign_closed_owner_descriptors\":%zu,\"allocator_hook\":false}\n",
         KindName(kind), preimage ? "OBSERVED_PREIMAGE_LEASE_DESTRUCTION_BUG" : "PASS", owned_descriptors, closed_in_foreign);
  fflush(stdout);
}
class LimitRestore {
 public:
  LimitRestore() { Require(getrlimit(RLIMIT_NOFILE, &value_) == 0, "read own original file limit"); }
  ~LimitRestore() { if (active_ && setrlimit(RLIMIT_NOFILE, &value_) != 0) ++restore_failures; }
  void Set(rlim_t soft) { rlimit next = value_; next.rlim_cur = soft;
    Require(soft <= value_.rlim_cur && setrlimit(RLIMIT_NOFILE, &next) == 0, "lower only owned soft limit"); active_ = true; }
  void Restore() { Require(setrlimit(RLIMIT_NOFILE, &value_) == 0, "restore exact owned file limit"); active_ = false; }
  static unsigned restore_failures;
 private: rlimit value_{}; bool active_ = false;
};
unsigned LimitRestore::restore_failures = 0;
void FailedConstruction() {
  const auto before = FdNumbers(); Require(!before.empty(), "original owned fd table nonempty");
  {
    role::Descriptor parent_pidfd(static_cast<int>(syscall(SYS_pidfd_open, static_cast<long>(getpid()), 0UL)));
    Require(parent_pidfd.get() >= 0, "exact controller pidfd");
    Sockets owner_control;
    const pid_t owner_pid = fork(); Require(owner_pid >= 0, "separate owned root peer for init failure");
    if (!owner_pid) RunLeaseChild(owner_control.second.get(), parent_pidfd.get());
    OwnedChild owner(owner_pid); owner_control.second.reset();
    auto endpoint = ReadControl(owner_control.first.get(), Command::kEndpoint, true);
    const int original_endpoint = endpoint.descriptor.get();
    {
      LimitRestore limit; const auto initial = FdNumbers(); limit.Set(static_cast<rlim_t>(initial.back()) + 10);
      std::vector<role::Descriptor> fillers;
      for (;;) {
        int fd = open("/dev/null", O_RDONLY | O_CLOEXEC);
        if (fd < 0) { Require(errno == EMFILE, "exact owned full-table boundary"); break; }
        fillers.emplace_back(fd);
      }
      Require(!fillers.empty(), "owned filler slots available");
      fillers.back().reset(); fillers.pop_back();
      // Exactly one free slot: SO_PEERPIDFD allocates a real peer descriptor,
      // then self pidfd_open fails. Neither owner proc proof nor public Impl
      // was published; all partial FDs must close and input ownership remain.
      const auto one_slot = FdNumbers();
      {
        role::OwnerLease lease; errno = 0;
        ExpectError(lease.Initialize(&endpoint.descriptor), EMFILE, "partial actual lease initialization hits real file limit");
        Require(endpoint.descriptor.get() == original_endpoint && FdNumbers() == one_slot,
                "failed init retains input and closes only its new peer pidfd");
      }
      Require(FdNumbers() == one_slot, "uninitialized public destructor changes no descriptors");
      limit.Restore();
    }
    endpoint.descriptor.reset();
    CommandOnly(owner_control.first.get(), Command::kExit);
    ReadControl(owner_control.first.get(), Command::kAck); owner.Join(); ++direct_reaped;
  }
  Require(!LimitRestore::restore_failures && FdNumbers() == before, "owned limit and all fixture descriptors restored");
  puts("{\"case\":\"partial_lease_initialization_EMFILE_cleanup\",\"state\":\"PASS\",\"limit_increased\":false}");
}
}

int main(int argc, char** argv) {
  const bool preimage = argc == 3 && !strcmp(argv[1], "--execute-once") && !strcmp(argv[2], "--expect-preimage");
  const bool candidate = argc == 3 && !strcmp(argv[1], "--execute-once") && !strcmp(argv[2], "--expect-candidate");
  if (!preimage && !candidate) {
    puts("{\"state\":\"PLAN_ONLY\",\"candidate_cases\":4,\"preimage_cases\":2,\"Main_actions\":0}");
    return argc == 1 ? 0 : 2;
  }
  try {
    Require(getuid() == 0 && geteuid() == 0 && syscall(SYS_gettid) == getpid(), "actual root owner main thread");
    struct sigaction disposition{};
    Require(sigaction(SIGCHLD, nullptr, &disposition) == 0 && disposition.sa_handler == SIG_DFL &&
        !(disposition.sa_flags & SA_NOCLDWAIT), "exclusive owned child wait policy");
    deadline = Now() + 20000000000ULL;
    const auto before = FdNumbers();
    DestructionCase(Kind::kSharedFiles, preimage);
    if (candidate) { DestructionCase(Kind::kPrivateFiles, false); DestructionCase(Kind::kPrivateVm, false); }
    FailedConstruction();
    Require(FdNumbers() == before && direct_reaped == (candidate ? 7U : 3U) && !forced_cleanup &&
        !cleanup_unreaped && !LimitRestore::restore_failures, "all owned processes and resources restored normally");
    printf("{\"state\":\"%s\",\"cases\":%u,\"assertions\":%u,\"direct_children_reaped\":%u,"
           "\"forced_cleanup\":%u,\"cleanup_unreaped\":%u,\"platform_qualified\":false,\"Main_actions\":0}\n",
           candidate ? "PASS_LEASE_DESTRUCTION_CONTROLS" : "OBSERVED_PREIMAGE_LEASE_BUG_AND_CLEANUP_CONTROL",
           candidate ? 4U : 2U, assertions, direct_reaped, forced_cleanup, cleanup_unreaped);
    return 0;
  } catch (const std::exception& error) {
    printf("{\"state\":\"FAIL\",\"error_hex\":\"%s\",\"errno\":%d,\"direct_children_reaped\":%u,"
           "\"forced_cleanup\":%u,\"cleanup_unreaped\":%u,\"limit_restore_failures\":%u}\n",
           Hex(error.what()).c_str(), errno, direct_reaped, forced_cleanup, cleanup_unreaped, LimitRestore::restore_failures);
    return 1;
  }
}
