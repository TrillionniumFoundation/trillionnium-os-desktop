/*
 * Copyright (C) 2024 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "gtest/gtest.h"

#include <fcntl.h>  // open
#include <linux/memfd.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <unistd.h>  // close, sysconf(_SC_PAGESIZE)

#include <array>
#include <cerrno>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <initializer_list>
#include <memory>
#include <string>

namespace {

const size_t kPageSize = sysconf(_SC_PAGESIZE);
constexpr bool kExactMapping = true;

template <bool kIsExactMapping = false>
bool IsExecutable(void* ptr, size_t size) {
  uintptr_t addr = reinterpret_cast<uintptr_t>(ptr);
  std::unique_ptr<FILE, decltype(&fclose)> fp(fopen("/proc/self/maps", "re"), fclose);
  if (fp == nullptr) {
    ADD_FAILURE() << "Cannot open /proc/self/maps";
    return false;
  }

  char line[BUFSIZ];
  while (fgets(line, sizeof(line), fp.get()) != nullptr) {
    uintptr_t start;
    uintptr_t end;
    char prot[5];  // sizeof("rwxp")
    if (sscanf(line, "%" SCNxPTR "-%" SCNxPTR " %4s", &start, &end, prot) == 3) {
      bool is_match;
      if constexpr (kIsExactMapping) {
        is_match = (addr == start);
        if (is_match) {
          EXPECT_EQ(start + size, end);
        }
      } else {
        is_match = (addr >= start) && (addr < end);
        if (is_match) {
          EXPECT_LE(addr + size, end);
        }
      }
      if (is_match) {
        return prot[2] == 'x';
      }
    }
  }
  ADD_FAILURE() << "Didn't find range " << ptr << "-" << reinterpret_cast<void*>(addr + size)
                << " in /proc/self/maps";
  return false;
}

template <typename FuncType>
class ScopeExit {
 public:
  explicit ScopeExit(FuncType f) : func_(f) {}
  ~ScopeExit() { func_(); }

 private:
  FuncType func_;
};

TEST(ProcSelfMaps, ExecutableFromMmap) {
  uint8_t* mapping = reinterpret_cast<uint8_t*>(
      mmap(0, 3 * kPageSize, PROT_READ, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
  ASSERT_NE(mapping, nullptr);
  auto mapping_cleanup = ScopeExit([mapping]() { EXPECT_EQ(0, munmap(mapping, 3 * kPageSize)); });

  ASSERT_FALSE(IsExecutable(mapping, 3 * kPageSize));

  void* exec_mapping = mmap(mapping + kPageSize,
                            kPageSize,
                            PROT_READ | PROT_EXEC,
                            MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS,
                            -1,
                            0);
  ASSERT_NE(exec_mapping, nullptr);

  ASSERT_FALSE(IsExecutable(mapping, kPageSize));
  // Surrounding mappings can be merged with adjacent mappings. But this one must match exactly.
  ASSERT_TRUE(IsExecutable<kExactMapping>(mapping + kPageSize, kPageSize));
  ASSERT_FALSE(IsExecutable(mapping + 2 * kPageSize, kPageSize));
}

TEST(ProcSelfMaps, ExecutableFromMprotect) {
  uint8_t* mapping = reinterpret_cast<uint8_t*>(
      mmap(0, 3 * kPageSize, PROT_READ, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
  ASSERT_NE(mapping, nullptr);
  auto mapping_cleanup = ScopeExit([mapping]() { EXPECT_EQ(0, munmap(mapping, 3 * kPageSize)); });

  ASSERT_FALSE(IsExecutable(mapping, 3 * kPageSize));

  ASSERT_EQ(mprotect(mapping + kPageSize, kPageSize, PROT_READ | PROT_EXEC), 0);

  ASSERT_FALSE(IsExecutable(mapping, kPageSize));
  // Surrounding mappings can be merged with adjacent mappings. But this one must match exactly.
  ASSERT_TRUE(IsExecutable<kExactMapping>(mapping + kPageSize, kPageSize));
  ASSERT_FALSE(IsExecutable(mapping + 2 * kPageSize, kPageSize));
}

TEST(ProcSelfMaps, ExecutableFromFileBackedMmap) {
  int fd = open("/dev/zero", O_RDONLY);
  auto fd_cleanup = ScopeExit([fd]() { close(fd); });
  uint8_t* mapping =
      reinterpret_cast<uint8_t*>(mmap(0, 3 * kPageSize, PROT_READ, MAP_PRIVATE, fd, 0));
  ASSERT_NE(mapping, nullptr);
  auto mapping_cleanup = ScopeExit([mapping]() { EXPECT_EQ(0, munmap(mapping, 3 * kPageSize)); });

  ASSERT_FALSE(IsExecutable(mapping, 3 * kPageSize));

  ASSERT_EQ(0, mprotect(mapping + kPageSize, kPageSize, PROT_READ | PROT_EXEC));

  // File-backed mappings shouldn't merge with the adjacent mappings and must match exactly.
  ASSERT_FALSE(IsExecutable<kExactMapping>(mapping, kPageSize));
  ASSERT_TRUE(IsExecutable<kExactMapping>(mapping + kPageSize, kPageSize));
  ASSERT_FALSE(IsExecutable<kExactMapping>(mapping + 2 * kPageSize, kPageSize));
}


class OwnedProcTestFd {
 public:
  explicit OwnedProcTestFd(int fd) : fd_(fd) {}
  ~OwnedProcTestFd() {
    if (fd_ >= 0) EXPECT_EQ(close(fd_), 0);
  }
  OwnedProcTestFd(const OwnedProcTestFd&) = delete;
  OwnedProcTestFd& operator=(const OwnedProcTestFd&) = delete;
  int get() const { return fd_; }
  int Release() {
    int fd = fd_;
    fd_ = -1;
    return fd;
  }
 private:
  int fd_;
};

std::string ProcFdPath(int fd) {
  return "/proc/self/fd/" + std::to_string(fd);
}

std::string CanonicalOwnMapsPath() {
  return "/proc/" + std::to_string(getpid()) + "/maps";
}

std::string ProcFdTarget(int fd) {
  const std::string path = ProcFdPath(fd);
  std::array<char, 4096> out{};
  ssize_t count = readlink(path.c_str(), out.data(), out.size());
  if (count < 0 || static_cast<size_t>(count) >= out.size()) {
    ADD_FAILURE() << "bounded own-FD readlink failed: " << count << ", errno=" << errno;
    return {};
  }
  return std::string(out.data(), static_cast<size_t>(count));
}

// These are ABI conformance tests, not provenance implementation seams.
// The same source must run natively and through the candidate translator.
// The old R16 path leaks its backing memfd name and is expected to fail the
// maps-target assertions. A fixture result does not qualify a commercial App.
TEST(ProcSelfMaps, ReadlinkHasCanonicalOwnerPath) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  EXPECT_EQ(ProcFdTarget(maps.get()), CanonicalOwnMapsPath());

  OwnedProcTestFd directory(open("/proc/self/fd", O_RDONLY | O_DIRECTORY | O_CLOEXEC));
  ASSERT_GE(directory.get(), 0);
  const std::string leaf = std::to_string(maps.get());
  std::array<char, 4096> out{};
  ssize_t count = readlinkat(directory.get(), leaf.c_str(), out.data(), out.size());
  ASSERT_GE(count, 0);
  ASSERT_LT(static_cast<size_t>(count), out.size());
  EXPECT_EQ(std::string(out.data(), static_cast<size_t>(count)), CanonicalOwnMapsPath());
}

TEST(ProcSelfMaps, DuplicatedAliasesKeepOriginAfterOriginalClose) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  OwnedProcTestFd duplicate(dup(maps.get()));
  ASSERT_GE(duplicate.get(), 0);
  OwnedProcTestFd cloexec(fcntl(maps.get(), F_DUPFD_CLOEXEC, 0));
  ASSERT_GE(cloexec.get(), 0);
  ASSERT_EQ(close(maps.Release()), 0);
  EXPECT_EQ(ProcFdTarget(duplicate.get()), CanonicalOwnMapsPath());
  EXPECT_EQ(ProcFdTarget(cloexec.get()), CanonicalOwnMapsPath());
  const int fd_flags = fcntl(cloexec.get(), F_GETFD);
  ASSERT_GE(fd_flags, 0);
  EXPECT_EQ(fd_flags & FD_CLOEXEC, FD_CLOEXEC);
}

TEST(ProcSelfMaps, Dup2ReplacementDoesNotKeepMapsAttribution) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  OwnedProcTestFd ordinary(open("/dev/null", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(ordinary.get(), 0);
  const std::string expected = ProcFdTarget(ordinary.get());
  ASSERT_FALSE(expected.empty());
  ASSERT_NE(expected, CanonicalOwnMapsPath());
  ASSERT_EQ(dup2(ordinary.get(), maps.get()), maps.get());
  EXPECT_EQ(ProcFdTarget(maps.get()), expected);
}

TEST(ProcSelfMaps, ReusedClosedNumberDoesNotKeepMapsAttribution) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  OwnedProcTestFd ordinary(open("/dev/null", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(ordinary.get(), 0);
  const std::string expected = ProcFdTarget(ordinary.get());
  ASSERT_FALSE(expected.empty());
  int old_number = maps.Release();
  ASSERT_EQ(close(old_number), 0);
  // Allocate the freed slot without replacing a descriptor acquired by another thread.
  OwnedProcTestFd reused(fcntl(ordinary.get(), F_DUPFD_CLOEXEC, old_number));
  ASSERT_EQ(reused.get(), old_number);
  EXPECT_EQ(ProcFdTarget(reused.get()), expected);
}

TEST(ProcSelfMaps, CloseRangeOfOnlyOwnedFdDoesNotKeepMapsAttribution) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  OwnedProcTestFd ordinary(open("/dev/null", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(ordinary.get(), 0);
  const std::string expected = ProcFdTarget(ordinary.get());
  ASSERT_FALSE(expected.empty());
  const int old_number = maps.get();
  // A one-FD interval cannot close an ambient harness descriptor.
  ASSERT_EQ(syscall(__NR_close_range, static_cast<unsigned int>(old_number),
                    static_cast<unsigned int>(old_number), 0U), 0);
  ASSERT_EQ(maps.Release(), old_number);
  // Allocate the freed slot without replacing a descriptor acquired by another thread.
  OwnedProcTestFd reused(fcntl(ordinary.get(), F_DUPFD_CLOEXEC, old_number));
  ASSERT_EQ(reused.get(), old_number);
  EXPECT_EQ(ProcFdTarget(reused.get()), expected);
}

TEST(ProcSelfMaps, SealedLookalikeMemfdIsNotTrustedMaps) {
  for (const char* name : {"[guest /proc/self/maps]", "droidloom-proc-maps-v2"}) {
    OwnedProcTestFd lookalike(static_cast<int>(
        syscall(__NR_memfd_create, name, MFD_CLOEXEC | MFD_ALLOW_SEALING)));
    ASSERT_GE(lookalike.get(), 0);
    ASSERT_EQ(fcntl(lookalike.get(), F_ADD_SEALS,
                    F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL), 0);
    const std::string target = ProcFdTarget(lookalike.get());
    ASSERT_FALSE(target.empty());
    EXPECT_NE(target, CanonicalOwnMapsPath());
  }
}

TEST(ProcSelfMaps, ReadlinkLengthAndNoTerminatorSemantics) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  const std::string path = ProcFdPath(maps.get());
  const std::string expected = CanonicalOwnMapsPath();
  std::array<char, 4096> out{};
  out.fill('Q');
  ASSERT_LT(expected.size() + 1, out.size());
  ASSERT_EQ(readlink(path.c_str(), out.data(), expected.size()), 
            static_cast<ssize_t>(expected.size()));
  EXPECT_EQ(std::string(out.data(), expected.size()), expected);
  EXPECT_EQ(out[expected.size()], 'Q');
  out.fill('Q');
  ASSERT_EQ(readlink(path.c_str(), out.data(), 1), 1);
  EXPECT_EQ(out[0], expected[0]);
  EXPECT_EQ(out[1], 'Q');
  errno = 0;
  EXPECT_EQ(readlink(path.c_str(), out.data(), 0), -1);
  EXPECT_EQ(errno, EINVAL);
}

TEST(ProcSelfMaps, ClosedFdAndBadDirfdKeepKernelErrors) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  const std::string path = ProcFdPath(maps.get());
  const std::string leaf = std::to_string(maps.get());
  ASSERT_EQ(close(maps.Release()), 0);
  std::array<char, 64> out{};
  errno = 0;
  EXPECT_EQ(readlink(path.c_str(), out.data(), out.size()), -1);
  EXPECT_EQ(errno, ENOENT);
  errno = 0;
  EXPECT_EQ(readlinkat(-1, leaf.c_str(), out.data(), out.size()), -1);
  EXPECT_EQ(errno, EBADF);
}

TEST(ProcSelfMaps, UnwritableBufferReturnsEfaultWithoutAProcessFault) {
  OwnedProcTestFd maps(open("/proc/self/maps", O_RDONLY | O_CLOEXEC));
  ASSERT_GE(maps.get(), 0);
  const std::string path = ProcFdPath(maps.get());
  void* guard = mmap(nullptr, kPageSize, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  ASSERT_NE(guard, MAP_FAILED);
  auto cleanup = ScopeExit([guard]() { EXPECT_EQ(munmap(guard, kPageSize), 0); });
  errno = 0;
  EXPECT_EQ(readlink(path.c_str(), static_cast<char*>(guard), 1), -1);
  EXPECT_EQ(errno, EFAULT);
}

}  // namespace
