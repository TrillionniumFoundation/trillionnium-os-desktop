/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#include "berberis/kernel_api/proc_maps_fd_owner.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/futex.h>
#include <linux/magic.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <atomic>

namespace berberis::proc_maps_provenance::fd_owner {
namespace {

int Error(int error) { errno = error; return -1; }

class OwnedFd {
 public:
  explicit OwnedFd(int fd) : fd_(fd) {}
  ~OwnedFd() {
    const int saved = errno;
    if (fd_ >= 0) syscall(SYS_close, fd_);
    errno = saved;
  }
  OwnedFd(const OwnedFd&) = delete;
  OwnedFd& operator=(const OwnedFd&) = delete;
  int get() const { return fd_; }
 private:
  int fd_;
};

// A guest signal handler or pthread cancellation must not abandon the stack
// request while its owner still uses it. libc retains its private cancellation
// and setxid signals; no application handler is installed or replaced here.
class CallerScope {
 public:
  int Enter() {
    int error;
#if !defined(__BIONIC__)
    // Bionic has no pthread cancellation API. Keep this protection for host
    // libc implementations that do support it, without adding missing Android
    // symbols to the native bridge.
    error = pthread_setcancelstate(PTHREAD_CANCEL_DISABLE, &old_cancel_);
    if (error != 0) return Error(error);
    cancel_saved_ = true;
#endif
    sigset_t blocked;
    if (sigfillset(&blocked) < 0) return -1;
    error = pthread_sigmask(SIG_BLOCK, &blocked, &old_mask_);
    if (error != 0) return Error(error);
    mask_saved_ = true;
    return 0;
  }
  // Re-enabling pending host cancellation can unwind from this destructor.
  // The owner is already joined; allow that unwind instead of terminating the
  // process at an implicit noexcept boundary.
  ~CallerScope() noexcept(false) {
    const int saved = errno;
    if (mask_saved_) pthread_sigmask(SIG_SETMASK, &old_mask_, nullptr);
#if !defined(__BIONIC__)
    if (cancel_saved_) pthread_setcancelstate(old_cancel_, nullptr);
#endif
    errno = saved;
  }
 private:
  sigset_t old_mask_{};
  bool mask_saved_ = false;
#if !defined(__BIONIC__)
  int old_cancel_ = PTHREAD_CANCEL_ENABLE;
  bool cancel_saved_ = false;
#endif
};

struct Request {
  pid_t caller_tid;
  int caller_fd;
  Operation operation;
  void* context;
  bool pin_caller_fd = true;
  Publication publication = nullptr;
  char publication_path[160]{};
  // 0 preparing; 1 caller publication requested; 2 publication acknowledged;
  // 3 completed. The owner never accesses request/context after completion.
  std::atomic<int> phase{0};
  int result = -1;
  int error = EIO;
  std::atomic<bool> complete{false};
};

void ChangePhase(Request* request, int phase) {
  request->phase.store(phase, std::memory_order_release);
  syscall(SYS_futex, &request->phase, FUTEX_WAKE_PRIVATE, INT_MAX, nullptr, nullptr, 0);
}

void WaitWhile(Request* request, int phase) {
  while (request->phase.load(std::memory_order_acquire) == phase) {
    syscall(SYS_futex, &request->phase, FUTEX_WAIT_PRIVATE, phase, nullptr, nullptr, 0);
  }
}

int PublishPreparedFile(Request* request, int caller_pidfd) {
  OwnedFd prepared(request->operation(caller_pidfd, request->context));
  if (prepared.get() < 0) return -1;
  // Use the procfs mount's actual numeric view. getpid/gettid can name a
  // different PID namespace than this mount (including the host test runner).
  OwnedFd directory(open("/proc/thread-self/fd", O_PATH | O_DIRECTORY | O_CLOEXEC));
  if (directory.get() < 0) return -1;
  struct statfs fs{};
  if (fstatfs(directory.get(), &fs) < 0) return -1;
  if (static_cast<unsigned long>(fs.f_type) != PROC_SUPER_MAGIC) return Error(EXDEV);
  char label[96];
  const ssize_t length = readlink("/proc/thread-self", label, sizeof(label) - 1);
  if (length < 0) return -1;
  if (length == 0 || static_cast<size_t>(length) >= sizeof(label) - 1) return Error(EXDEV);
  label[length] = '\0';
  const int written = snprintf(request->publication_path, sizeof(request->publication_path),
                               "/proc/%s/fd/%d", label, prepared.get());
  if (written <= 0 || static_cast<size_t>(written) >= sizeof(request->publication_path)) {
    return Error(EOVERFLOW);
  }
  ChangePhase(request, 1);
  WaitWhile(request, 1);
  if (request->phase.load(std::memory_order_acquire) != 2) return Error(EIO);
  // The caller has completed the sole public open. All subsequent closes are
  // in this independent table, even if its numeric slots are reused by guests.
  return 0;
}

int InitializePrivateTable() {
  // Until unshare succeeds this is still the caller's fd table. In particular,
  // do not close any descriptor on the failure path before this boundary.
  if (syscall(SYS_unshare, CLONE_FILES) < 0) return -1;
#ifdef SYS_close_range
  // Drop this owner's inherited references. This both avoids prolonging their
  // lifetimes and leaves room for the pin even if the caller is at RLIMIT_NOFILE.
  if (syscall(SYS_close_range, 0u, UINT_MAX, 0u) < 0) return -1;
#else
  return Error(ENOSYS);
#endif
  return 0;
}

int PerformInPrivateTable(Request& request) {
#ifdef SYS_pidfd_open
  OwnedFd caller(static_cast<int>(syscall(SYS_pidfd_open, request.caller_tid, O_EXCL)));
  if (caller.get() < 0) return -1;
#else
  return Error(ENOSYS);
#endif
#if defined(SYS_pidfd_open) && defined(SYS_pidfd_getfd)
  if (request.publication != nullptr) return PublishPreparedFile(&request, caller.get());
  if (!request.pin_caller_fd) return request.operation(caller.get(), request.context);
  // This syscall is the descriptor selection/linearization point. Passing the
  // caller's fd number to fstat in the owner would select a different table.
  OwnedFd pinned(static_cast<int>(syscall(SYS_pidfd_getfd, caller.get(), request.caller_fd, 0)));
  if (pinned.get() < 0) return -1;
  return request.operation(pinned.get(), request.context);
#else
  return Error(ENOSYS);
#endif
}

int Perform(Request& request) {
  if (InitializePrivateTable() < 0) return -1;
  return PerformInPrivateTable(request);
}

void* Run(void* context) {
  auto* request = static_cast<Request*>(context);
  errno = 0;
  request->result = Perform(*request);
  request->error = errno;
  // Perform has destroyed every private descriptor before this final access
  // to the caller's request. No callback/context access follows this store.
  ChangePhase(request, 3);
  request->complete.store(true, std::memory_order_release);
  return nullptr;
}

// This owner is opt-in. Before runtime lifecycle hooks are installed, the
// existing temporary owner remains the default. No TLS is used here: raw
// CLONE_VM guest processes can share the caller's host TLS while having a
// distinct TGID. Such a process must not reset or join this process's owner.
struct ReusableOwner {
  std::atomic<int> process{0};
  std::atomic<bool> enabled{false};
  // 0 closed; 1 accepting; 2 stopping. A single atomic prevents Start from
  // reopening admission while Stop is waiting for an in-flight request.
  std::atomic<int> admission{0};
  std::atomic<int> gate{0};
  std::atomic<int> event{0};
  // 0 idle; 1 request; 2 stop. Access to the slot is serialized by gate.
  std::atomic<int> command{0};
  std::atomic<Request*> slot{nullptr};
  std::atomic<bool> startup_done{false};
  std::atomic<bool> exited{false};
  int startup_error = 0;
  int poison = 0;  // guarded by gate; a failed join must never revive an exited worker
  pthread_t thread{};
  bool joinable = false;
  bool atfork_registered = false;
};

ReusableOwner g_reusable;

void NotifyReusable() {
  g_reusable.event.fetch_add(1, std::memory_order_release);
  syscall(SYS_futex, &g_reusable.event, FUTEX_WAKE_PRIVATE, INT_MAX,
          nullptr, nullptr, 0UL);
}

void WaitReusableEvent(int observed) {
  syscall(SYS_futex, &g_reusable.event, FUTEX_WAIT_PRIVATE, observed,
          nullptr, nullptr, 0UL);
}

int CurrentProcess() { return static_cast<int>(syscall(SYS_getpid)); }

bool OwnsReusableState() {
  return g_reusable.process.load(std::memory_order_acquire) == CurrentProcess();
}

class ReusableGate {
 public:
  int Enter() {
    if (!OwnsReusableState()) return Error(EOPNOTSUPP);
    for (;;) {
      int expected = 0;
      if (g_reusable.gate.compare_exchange_weak(expected, 1, std::memory_order_acquire)) {
        held_ = true;
        return 0;
      }
      syscall(SYS_futex, &g_reusable.gate, FUTEX_WAIT_PRIVATE, 1,
              nullptr, nullptr, 0UL);
    }
  }
  ~ReusableGate() {
    if (!held_) return;
    const int saved = errno;
    g_reusable.gate.store(0, std::memory_order_release);
    syscall(SYS_futex, &g_reusable.gate, FUTEX_WAKE_PRIVATE, INT_MAX,
            nullptr, nullptr, 0UL);
    errno = saved;
  }
 private:
  bool held_ = false;
};

void* RunReusable(void*) {
  errno = 0;
  const int initialized = InitializePrivateTable();
  g_reusable.startup_error = initialized < 0 ? errno : 0;
  if (initialized < 0) g_reusable.exited.store(true, std::memory_order_release);
  g_reusable.startup_done.store(true, std::memory_order_release);
  NotifyReusable();
  if (initialized < 0) return nullptr;
  for (;;) {
    const int observed = g_reusable.event.load(std::memory_order_acquire);
    const int command = g_reusable.command.load(std::memory_order_acquire);
    if (command == 2) break;
    if (command != 1) {
      WaitReusableEvent(observed);
      continue;
    }
    Request* request = g_reusable.slot.load(std::memory_order_acquire);
    // Only the admitted caller owns gate and publishes a non-null slot.
    // The caller cannot return until the completion store below.
    errno = 0;
    request->result = PerformInPrivateTable(*request);
    request->error = errno;
    g_reusable.slot.store(nullptr, std::memory_order_release);
    g_reusable.command.store(0, std::memory_order_release);
    request->complete.store(true, std::memory_order_release);
    // Do not access request again, including for futex wake. The caller may
    // already have returned and destroyed its stack request. Wake via the
    // process-lifetime event word instead.
    NotifyReusable();
  }
  g_reusable.exited.store(true, std::memory_order_release);
  NotifyReusable();
  return nullptr;
}

int RunReusableRequest(int fd, Operation operation, void* context) {
  if (fd < 0) return Error(EBADF);
  if (operation == nullptr) return Error(EINVAL);
  if (!OwnsReusableState()) return Error(EOPNOTSUPP);
  CallerScope scope;
  if (scope.Enter() < 0) return -1;
  if (g_reusable.admission.load(std::memory_order_acquire) != 1) return Error(ESHUTDOWN);
  ReusableGate gate;
  if (gate.Enter() < 0) return -1;
  if (g_reusable.admission.load(std::memory_order_acquire) != 1) return Error(ESHUTDOWN);
  Request request{static_cast<pid_t>(syscall(SYS_gettid)), fd, operation, context};
  g_reusable.slot.store(&request, std::memory_order_release);
  g_reusable.command.store(1, std::memory_order_release);
  NotifyReusable();
  for (;;) {
    const int observed = g_reusable.event.load(std::memory_order_acquire);
    if (request.complete.load(std::memory_order_acquire)) break;
    WaitReusableEvent(observed);
  }
  errno = request.error;
  return request.result;
}

}  // namespace

void ResetReusableMetadataOwnerAfterPrivateFork() {
  // This function is called only in a private-memory child, including libc
  // fork's child hook. The copied gate may have been held by a vanished thread.
  // No lock, old pthread handle or copied stack request is touched.
  g_reusable.admission.store(0, std::memory_order_relaxed);
  g_reusable.gate.store(0, std::memory_order_relaxed);
  g_reusable.event.store(0, std::memory_order_relaxed);
  g_reusable.command.store(0, std::memory_order_relaxed);
  g_reusable.slot.store(nullptr, std::memory_order_relaxed);
  g_reusable.startup_done.store(false, std::memory_order_relaxed);
  g_reusable.exited.store(false, std::memory_order_relaxed);
  g_reusable.startup_error = 0;
  g_reusable.poison = 0;
  g_reusable.thread = pthread_t{};
  g_reusable.joinable = false;
  g_reusable.process.store(CurrentProcess(), std::memory_order_release);
}

int StartReusableMetadataOwner() {
  const int incoming_errno = errno;
  const int process = CurrentProcess();
  const int registered = g_reusable.process.load(std::memory_order_acquire);
  if (registered != 0 && registered != process) return Error(EOPNOTSUPP);
  // An already-open owner needs no TLS, mask operation or gate acquisition.
  // A concurrent Stop can linearize immediately after this observation.
  if (g_reusable.admission.load(std::memory_order_acquire) == 1) return 0;
  CallerScope scope;
  if (scope.Enter() < 0) return -1;
  int unassigned = 0;
  g_reusable.process.compare_exchange_strong(unassigned, process, std::memory_order_acq_rel);
  if (!OwnsReusableState()) return Error(EOPNOTSUPP);
  if (g_reusable.admission.load(std::memory_order_acquire) == 2) return Error(EBUSY);
  ReusableGate gate;
  if (gate.Enter() < 0) return -1;
  if (g_reusable.admission.load(std::memory_order_acquire) == 2) return Error(EBUSY);
  if (g_reusable.poison != 0) return Error(g_reusable.poison);
  g_reusable.enabled.store(true, std::memory_order_release);
  if (g_reusable.joinable) {
    int closed = 0;
    if (!g_reusable.admission.compare_exchange_strong(closed, 1, std::memory_order_acq_rel) &&
        closed != 1) return Error(EBUSY);
    errno = incoming_errno;
    return 0;
  }
  if (!g_reusable.atfork_registered) {
    const int error = pthread_atfork(nullptr, nullptr, ResetReusableMetadataOwnerAfterPrivateFork);
    if (error != 0) return Error(error);
    g_reusable.atfork_registered = true;
  }
  pthread_attr_t attributes;
  int error = pthread_attr_init(&attributes);
  if (error != 0) return Error(error);
  error = pthread_attr_setstacksize(&attributes, 128u * 1024u);
  if (error != 0) {
    pthread_attr_destroy(&attributes);
    return Error(error);
  }
  g_reusable.startup_done.store(false, std::memory_order_relaxed);
  g_reusable.exited.store(false, std::memory_order_relaxed);
  g_reusable.command.store(0, std::memory_order_relaxed);
  error = pthread_create(&g_reusable.thread, &attributes, RunReusable, nullptr);
  pthread_attr_destroy(&attributes);
  if (error != 0) return Error(error);
  g_reusable.joinable = true;
  for (;;) {
    const int observed = g_reusable.event.load(std::memory_order_acquire);
    if (g_reusable.startup_done.load(std::memory_order_acquire)) break;
    WaitReusableEvent(observed);
  }
  if (g_reusable.startup_error != 0) {
    const int startup_error = g_reusable.startup_error;
    const int joined = pthread_join(g_reusable.thread, nullptr);
    if (joined == 0) {
      g_reusable.joinable = false;
      g_reusable.thread = pthread_t{};
    } else {
      g_reusable.poison = joined;
    }
    return Error(joined != 0 ? joined : startup_error);
  }
  int closed = 0;
  if (!g_reusable.admission.compare_exchange_strong(closed, 1, std::memory_order_acq_rel) &&
      closed != 1) return Error(EBUSY);
  errno = incoming_errno;
  return 0;
}

int StopReusableMetadataOwner() {
  const int incoming_errno = errno;
  if (!g_reusable.enabled.load(std::memory_order_acquire)) return 0;
  if (!OwnsReusableState()) return Error(EOPNOTSUPP);
  CallerScope scope;
  if (scope.Enter() < 0) return -1;
  // Close admission before waiting for a caller already holding the gate.
  if (g_reusable.admission.exchange(2, std::memory_order_acq_rel) == 2) return Error(EBUSY);
  int result = 0;
  int error = 0;
  {
    ReusableGate gate;
    if (gate.Enter() < 0) {
      result = -1;
      error = errno;
    } else if (g_reusable.poison != 0) {
      result = -1;
      error = g_reusable.poison;
    } else if (g_reusable.joinable) {
      g_reusable.command.store(2, std::memory_order_release);
      NotifyReusable();
      for (;;) {
        const int observed = g_reusable.event.load(std::memory_order_acquire);
        if (g_reusable.exited.load(std::memory_order_acquire)) break;
        WaitReusableEvent(observed);
      }
      error = pthread_join(g_reusable.thread, nullptr);
      if (error == 0) {
        g_reusable.joinable = false;
        g_reusable.thread = pthread_t{};
      } else {
        g_reusable.poison = error;
        result = -1;
      }
    }
  }
  g_reusable.admission.store(0, std::memory_order_release);
  NotifyReusable();
  errno = result < 0 ? error : incoming_errno;
  return result;
}

int RunRequest(int fd, bool pin_caller_fd, Operation operation, Publication publication,
               void* context) {
  if (pin_caller_fd && fd < 0) return Error(EBADF);
  if (operation == nullptr) return Error(EINVAL);
  CallerScope scope;
  if (scope.Enter() < 0) return -1;
  Request request{static_cast<pid_t>(syscall(SYS_gettid)), fd, operation, context};
  request.pin_caller_fd = pin_caller_fd;
  request.publication = publication;
  pthread_attr_t attributes;
  int error = pthread_attr_init(&attributes);
  if (error != 0) return Error(error);
  // Bounds each in-flight query's stack; no heap queue or process-global
  // synchronization state survives a guest fork/exec.
  constexpr size_t kOwnerStackBytes = 128u * 1024u;
  error = pthread_attr_setstacksize(&attributes, kOwnerStackBytes);
  if (error != 0) {
    pthread_attr_destroy(&attributes);
    return Error(error);
  }
  pthread_t owner;
  error = pthread_create(&owner, &attributes, Run, &request);
  pthread_attr_destroy(&attributes);
  if (error != 0) return Error(error);
  int publication_result = -1;
  int publication_error = 0;
  if (publication != nullptr) {
    WaitWhile(&request, 0);
    if (request.phase.load(std::memory_order_acquire) == 1) {
      publication_result = publication(request.publication_path, context);
      publication_error = errno;
      ChangePhase(&request, 2);
    }
  }
  error = pthread_join(owner, nullptr);
  if (error != 0) {
    // This private, joinable thread is never detached or exposed to another
    // joiner, and caller cancellation is disabled. Still do not allow an
    // unexpected libc error to leave a live callback using a dead stack.
    while (!request.complete.load(std::memory_order_acquire)) sched_yield();
    return Error(error);
  }
  if (!request.complete.load(std::memory_order_acquire)) return Error(EIO);
  if (publication != nullptr && request.result == 0) {
    errno = publication_error;
    return publication_result;
  }
  errno = request.error;
  return request.result;
}

int WithPinnedFd(int fd, Operation operation, void* context) {
  if (g_reusable.enabled.load(std::memory_order_acquire)) {
    return RunReusableRequest(fd, operation, context);
  }
  return RunRequest(fd, true, operation, nullptr, context);
}

int WithPrivateTable(Operation operation, void* context) {
  return RunRequest(-1, false, operation, nullptr, context);
}

int WithPreparedFile(Operation prepare, Publication publish, void* context) {
  if (publish == nullptr) return Error(EINVAL);
  return RunRequest(-1, false, prepare, publish, context);
}

}  // namespace berberis::proc_maps_provenance::fd_owner
