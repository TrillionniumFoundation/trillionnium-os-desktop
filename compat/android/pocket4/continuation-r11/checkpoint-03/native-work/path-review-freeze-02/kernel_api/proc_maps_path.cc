/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#include "berberis/kernel_api/proc_maps_path.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <stdint.h>
#include <string.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>

#include <algorithm>

namespace berberis::proc_maps_provenance::path {
namespace {

int Error(int error) { errno = error; return -1; }

class Fd {
 public:
  explicit Fd(int fd = -1) : fd_(fd) {}
  ~Fd() { reset(); }
  Fd(const Fd&) = delete;
  Fd& operator=(const Fd&) = delete;
  int get() const { return fd_; }
  int release() { const int result = fd_; fd_ = -1; return result; }
  void reset(int fd = -1) {
    const int saved = errno;
    if (fd_ >= 0) syscall(SYS_close, fd_);
    fd_ = fd;
    errno = saved;
  }
 private:
  int fd_;
};

int StartDirectory(int caller_pidfd, int caller_dirfd, bool absolute) {
  if (absolute) return open("/", O_PATH | O_DIRECTORY | O_CLOEXEC);
  if (caller_dirfd == AT_FDCWD) return open(".", O_PATH | O_DIRECTORY | O_CLOEXEC);
#ifdef SYS_pidfd_getfd
  return static_cast<int>(syscall(SYS_pidfd_getfd, caller_pidfd, caller_dirfd, 0));
#else
  (void)caller_pidfd;
  return Error(ENOSYS);
#endif
}

bool SameInode(const struct stat& left, const struct stat& right) {
  return left.st_dev == right.st_dev && left.st_ino == right.st_ino;
}

}  // namespace

int CopyFromCaller(const char* source, char (&destination)[kPathBytes]) {
#ifdef SYS_process_vm_readv
  // Do not read across an inaccessible following page after a valid NUL. A
  // short read can still contain the complete pathname and is accepted.
  const long page_size = sysconf(_SC_PAGESIZE);
  if (page_size <= 0) return Error(EIO);
  size_t offset = 0;
  while (offset < sizeof(destination)) {
    const uintptr_t base = reinterpret_cast<uintptr_t>(source);
    if (base > UINTPTR_MAX - offset) return Error(EFAULT);
    const uintptr_t address = base + offset;
    const size_t page_left = static_cast<size_t>(page_size) - address % page_size;
    const size_t count = std::min(page_left, sizeof(destination) - offset);
    struct iovec local{destination + offset, count};
    struct iovec remote{reinterpret_cast<void*>(address), count};
    const ssize_t copied = syscall(SYS_process_vm_readv, syscall(SYS_gettid),
                                   &local, 1, &remote, 1, 0);
    if (copied < 0) return -1;
    if (copied == 0) return Error(EFAULT);
    if (memchr(destination + offset, '\0', static_cast<size_t>(copied))) return 0;
    if (static_cast<size_t>(copied) != count) return Error(EFAULT);
    offset += count;
  }
  return Error(ENAMETOOLONG);
#else
  (void)source;
  (void)destination;
  return Error(ENOSYS);
#endif
}

int CaptureCallerView(CallerView* view) {
  if (fstatat(AT_FDCWD, "/proc/thread-self", &view->thread_self, AT_SYMLINK_NOFOLLOW) < 0) {
    return -1;
  }
  const ssize_t length = readlink("/proc/thread-self", view->thread_label,
                                 sizeof(view->thread_label) - 1);
  if (length < 0) return -1;
  if (length == 0 || static_cast<size_t>(length) >= sizeof(view->thread_label) - 1) {
    return Error(EXDEV);
  }
  view->thread_label[length] = '\0';
  return 0;
}

int Resolve(int caller_pidfd, int caller_dirfd, const char* copied_path,
            const CallerView& view, bool follow_final) {
  const size_t path_size = strnlen(copied_path, kPathBytes);
  if (path_size == 0) return Error(ENOENT);
  if (path_size == kPathBytes) return Error(ENAMETOOLONG);
  char pending[kPathBytes];
  memcpy(pending, copied_path, path_size + 1);
  Fd directory(StartDirectory(caller_pidfd, caller_dirfd, pending[0] == '/'));
  if (directory.get() < 0) return -1;
  unsigned symlinks = 0;
  for (;;) {
    const char* begin = pending;
    while (*begin == '/') ++begin;
    if (*begin == '\0') return directory.release();
    const char* end = begin;
    while (*end != '\0' && *end != '/') ++end;
    const bool trailing_slash = *end == '/' && strspn(end, "/") == strlen(end);
    const char* next = end;
    while (*next == '/') ++next;
    const bool final = *next == '\0';
    char component[kPathBytes];
    const size_t component_size = static_cast<size_t>(end - begin);
    memcpy(component, begin, component_size);
    component[component_size] = '\0';
    char rest[kPathBytes];
    memcpy(rest, next, strlen(next) + 1);

    Fd entry(openat(directory.get(), component, O_PATH | O_NOFOLLOW | O_CLOEXEC));
    if (entry.get() < 0) return -1;
    struct stat info{};
    if (fstat(entry.get(), &info) < 0) return -1;
    if (S_ISLNK(info.st_mode) && (!final || trailing_slash || follow_final)) {
      if (++symlinks > 40) return Error(ELOOP);
      struct statfs fs{};
      if (fstatfs(entry.get(), &fs) < 0) return -1;
      char target[kPathBytes];
      ssize_t target_size;
      if (static_cast<unsigned long>(fs.f_type) == PROC_SUPER_MAGIC &&
          SameInode(info, view.thread_self)) {
        target_size = static_cast<ssize_t>(strlen(view.thread_label));
        memcpy(target, view.thread_label, static_cast<size_t>(target_size));
      } else if (static_cast<unsigned long>(fs.f_type) == PROC_SUPER_MAGIC) {
        // Kernel proc magic links can name deleted files, namespaces, sockets,
        // etc.; their displayed text is not a pathname to resolve ourselves.
        // The proc node itself is immutable. The kernel selects its current
        // target atomically; the result stays pinned only in this table.
        entry.reset(openat(directory.get(), component, O_PATH | O_CLOEXEC));
        if (entry.get() < 0 || fstat(entry.get(), &info) < 0) return -1;
        if ((!final || trailing_slash) && !S_ISDIR(info.st_mode)) return Error(ENOTDIR);
        if (final) return entry.release();
        directory.reset(entry.release());
        memcpy(pending, rest, strlen(rest) + 1);
        continue;
      } else {
        target_size = readlinkat(entry.get(), "", target, sizeof(target) - 1);
        if (target_size < 0) return -1;
      }
      if (target_size == 0) return Error(ENOENT);
      const size_t target_length = static_cast<size_t>(target_size);
      const size_t rest_length = strlen(rest);
      const bool separator = rest_length != 0 || trailing_slash;
      if (target_length + (separator ? 1 : 0) + rest_length >= sizeof(pending)) {
        return Error(ENAMETOOLONG);
      }
      memcpy(pending, target, target_length);
      size_t position = target_length;
      if (separator) pending[position++] = '/';
      memcpy(pending + position, rest, rest_length + 1);
      if (target[0] == '/') {
        directory.reset(StartDirectory(caller_pidfd, caller_dirfd, true));
        if (directory.get() < 0) return -1;
      }
      continue;
    }
    if ((!final || trailing_slash) && !S_ISDIR(info.st_mode)) return Error(ENOTDIR);
    if (final) return entry.release();
    directory.reset(entry.release());
    memcpy(pending, rest, strlen(rest) + 1);
  }
}

}  // namespace berberis::proc_maps_provenance::path
