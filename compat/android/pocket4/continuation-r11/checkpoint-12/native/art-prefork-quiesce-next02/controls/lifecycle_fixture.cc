// Fixture support around exact extracted ART/NativeBridge function bodies.
// This is not a complete ART translation unit or the production raw owner.
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <pthread.h>
#include <sstream>
#include <string>
#include <time.h>
#include <unistd.h>
#include <vector>

namespace fixture {
std::atomic<bool> started{false};
std::atomic<bool> stop{false};
pthread_t worker{};
bool live = false;
bool refuse_stop = false;
unsigned reads = 0;
unsigned callbacks = 0;
unsigned quiesces = 0;

void Event(const char* text) {
  std::cout << "EVENT " << text << '\n' << std::flush;
}

[[noreturn]] void Fatal(const char* reason, int code) {
  std::cout << "FATAL " << reason << " reads=" << reads
            << " callbacks=" << callbacks << " quiesces=" << quiesces << '\n'
            << std::flush;
  _Exit(code);
}

void* Work(void*) {
  started.store(true, std::memory_order_release);
  while (!stop.load(std::memory_order_acquire)) {
    timespec delay{0, 1000000};
    nanosleep(&delay, nullptr);
  }
  return nullptr;
}

void Start() {
  if (pthread_create(&worker, nullptr, Work, nullptr) != 0) Fatal("pthread-create", 73);
  while (!started.load(std::memory_order_acquire)) sched_yield();
  live = true;
  Event("worker-ready");
}

bool Stop() {
  ++quiesces;
  Event("quiesce-enter");
  if (refuse_stop) return false;
  if (live) {
    stop.store(true, std::memory_order_release);
    if (pthread_join(worker, nullptr) != 0) Fatal("pthread-join", 73);
    live = false;
  }
  Event("quiesce-complete");
  return true;
}

struct Log {
  const char* level;
  std::ostringstream stream;
  explicit Log(const char* value) : level(value) {}
  template<typename T> Log& operator<<(const T& value) { stream << value; return *this; }
  ~Log() {
    std::cerr << level << ' ' << stream.str() << '\n';
    if (std::strcmp(level, "FATAL") == 0) Fatal("kernel-single-thread-wait", 70);
  }
};
}  // namespace fixture

#define LOG(level) fixture::Log(#level)
#define CHECK(condition) do { if (!(condition)) fixture::Fatal("CHECK:" #condition, 72); } while (false)
#define CHECK_EQ(left, right) CHECK((left) == (right))
#define CHECK_NE(left, right) CHECK((left) != (right))
#define LOG_ALWAYS_FATAL_IF(condition, ...) do { if (condition) fixture::Fatal("bridge-quiesce-rejected", 71); } while (false)
#define ALOGE(...) do { fixture::Fatal("incompatible-bridge", 72); } while (false)

namespace android {
enum class NativeBridgeState { kInitialized, kClosed };
NativeBridgeState g_state = NativeBridgeState::kInitialized;
void* g_native_bridge_handle = reinterpret_cast<void*>(1);
constexpr int PRE_ZYGOTE_FORK_VERSION = 8;
bool NativeBridgeInitialized() { return true; }
bool isCompatibleWith(int version) { return version == PRE_ZYGOTE_FORK_VERSION; }
struct Callbacks { void (*preZygoteFork)(); };
void LegacyCallback() {
  ++fixture::callbacks;
  fixture::Event("legacy-guest-log-close");
}
Callbacks callbacks{LegacyCallback};
Callbacks* g_callbacks = &callbacks;
namespace droidloom_generation {
bool BeforeFork() {
#if defined(DROIDLOOM_NATIVE_GENERATION_RUNTIME) && DROIDLOOM_NATIVE_GENERATION_RUNTIME
  return fixture::Stop();
#else
  ++fixture::quiesces;
  fixture::Event("generation-disabled");
  return true;
#endif
}
[[maybe_unused]] int LastError() { return EBUSY; }
}  // namespace droidloom_generation
#include "native_bridge_prefork.inc"
}  // namespace android

namespace art {
constexpr bool kIsDebugBuild = true;
uint64_t MilliTime() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}
size_t GetOsThreadStat(pid_t pid, char* buffer, size_t maximum) {
  CHECK_EQ(pid, getpid());
  if (++fixture::reads == 1) fixture::Event("kernel-wait-first-read");
  int fd = open("/proc/self/stat", O_RDONLY | O_CLOEXEC);
  CHECK(fd >= 0);
  ssize_t size;
  do { size = read(fd, buffer, maximum); } while (size < 0 && errno == EINTR);
  CHECK_EQ(close(fd), 0);
  CHECK(size > 0);
  return static_cast<size_t>(size);
}
std::string GetOtherThreadOsStats() { return "owned fixture; no other-process reads"; }
class Thread {
 public:
  static Thread* Current() { static Thread thread; return &thread; }
  void GetThreadName(std::string& name) { name = "owned-main"; }
};
struct Locks { static int* thread_list_lock_; };
int thread_lock = 0;
int* Locks::thread_list_lock_ = &thread_lock;
class MutexLock { public: MutexLock(Thread*, int&) {} };
class ThreadList {
 public:
  void WaitForUnregisterToComplete(Thread*) { fixture::Event("art-threadlist-wait"); }
  std::vector<Thread*> GetList() { return {Thread::Current()}; }
  size_t Size() { return 1; }  // The fixture worker is deliberately not ART-registered.
};
namespace jit {
class Jit { public: void PreZygoteFork() { fixture::Event("jit-prefork"); } };
}
class Heap {
 public:
  bool HasZygoteSpace() { return true; }
  void PreZygoteFork() { fixture::Event("heap-prefork"); }
};
class ClassLinker {
 public:
  void MakeInitializedClassesVisiblyInitialized(Thread*, bool) {
    fixture::Fatal("unexpected-first-fork-fixture-branch", 72);
  }
  template<typename T> void VisitClasses(T*) {
    fixture::Fatal("unexpected-first-fork-fixture-branch", 72);
  }
};
class ScopedObjectAccess { public: explicit ScopedObjectAccess(Thread*) {} };
class UpdateMethodsPreFirstForkVisitor {
 public:
  explicit UpdateMethodsPreFirstForkVisitor(ClassLinker*) {}
};
class Runtime {
 public:
  jit::Jit* GetJit() { return &jit_; }
  ThreadList* GetThreadList() { return &threads_; }
  void PreZygoteFork();
 private:
  jit::Jit jit_;
  ThreadList threads_;
  Heap heap;
  ClassLinker linker;
  Heap* heap_ = &heap;
  ClassLinker* class_linker_ = &linker;
};
#include "art_bridge_wrapper.inc"
#include "art_wait.inc"
#include "art_prefork.inc"
}  // namespace art

int main(int argc, char** argv) {
  if (argc != 2) return 74;
  const bool with_worker = std::strcmp(argv[1], "worker") == 0 ||
                           std::strcmp(argv[1], "reject-stop") == 0;
  if (!with_worker && std::strcmp(argv[1], "no-worker") != 0) return 74;
  fixture::refuse_stop = std::strcmp(argv[1], "reject-stop") == 0;
  if (with_worker) fixture::Start();
  art::Runtime runtime;
  runtime.PreZygoteFork();
  CHECK(!fixture::live);
  CHECK_EQ(fixture::callbacks, 1u);
  CHECK_EQ(fixture::quiesces, 1u);
  CHECK(fixture::reads > 0);
  fixture::Event("returned");
  return 0;
}
