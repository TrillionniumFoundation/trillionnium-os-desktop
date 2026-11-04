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

int Perform(Request& request) {
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

}  // namespace

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
