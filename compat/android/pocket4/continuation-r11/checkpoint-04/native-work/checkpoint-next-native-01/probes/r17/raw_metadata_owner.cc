// SPDX-License-Identifier: Apache-2.0
#include "raw_metadata_owner.h"

#include <atomic>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <fcntl.h>
#include <linux/futex.h>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

#if !defined(__x86_64__)
#error This owned experiment is qualified only for the Pocket4 x86_64 host ABI.
#endif
static_assert(SYS_clone==56 && SYS_exit==60);
// Own the complete clone child trampoline as well as the worker. The child
// never passes through a libc clone wrapper that could touch inherited TLS.
// The syscall returns in the parent on its original stack. In the child the
// aligned private stack holds only the fixed entry and argument.
extern "C" __attribute__((visibility("hidden"))) long pocket4_raw_clone_x86_64(
    unsigned long flags,void* stack,std::atomic<int>* clear_tid,
    int(*entry)(void*),void* argument);
__asm__(
    ".text\n"
    ".p2align 4\n"
    ".hidden pocket4_raw_clone_x86_64\n"
    ".global pocket4_raw_clone_x86_64\n"
    ".type pocket4_raw_clone_x86_64,@function\n"
    "pocket4_raw_clone_x86_64:\n"
    "andq $-16,%rsi\n"
    "subq $16,%rsi\n"
    "movq %rcx,0(%rsi)\n"
    "movq %r8,8(%rsi)\n"
    "movq %rdx,%r10\n"
    "xorl %r8d,%r8d\n"
    "movl $56,%eax\n"
    "syscall\n"
    "testq %rax,%rax\n"
    "jnz 1f\n"
    "xorl %ebp,%ebp\n"
    "movq 8(%rsp),%rdi\n"
    "call *0(%rsp)\n"
    "movl %eax,%edi\n"
    "movl $60,%eax\n"
    "syscall\n"
    "ud2\n"
    "1: ret\n"
    ".size pocket4_raw_clone_x86_64,.-pocket4_raw_clone_x86_64\n");
namespace pocket4::raw_metadata_owner {
namespace {
// All functions reachable from Worker must stay free of libc and TLS. Inspect
// the final target disassembly as a separate qualification gate.
#define RAW_ONLY __attribute__((no_stack_protector))
static_assert(std::atomic<int>::is_always_lock_free);
static_assert(std::atomic<void*>::is_always_lock_free);
RAW_ONLY __attribute__((always_inline)) inline long Raw(
    long number,long a=0,long b=0,long c=0,long d=0,long e=0,long f=0) {
  register long r10 __asm__("r10")=d;
  register long r8 __asm__("r8")=e;
  register long r9 __asm__("r9")=f;
  long result;
  __asm__ volatile("syscall":"=a"(result):"a"(number),"D"(a),"S"(b),"d"(c),
                   "r"(r10),"r"(r8),"r"(r9):"rcx","r11","memory");
  return result;
}
template<class T> RAW_ONLY __attribute__((always_inline)) inline long Address(T* pointer) {
  return reinterpret_cast<long>(pointer);
}
struct Request {
  int caller_tid;
  int fd;
  Snapshot* snapshot;
  int result=-999;
  std::atomic<int> complete{0};
};
struct State {
  std::atomic<int> process{0};
  // 0 closed, 1 accepting, 2 stopping.
  std::atomic<int> admission{0};
  std::atomic<int> gate{0},event{0},command{0},ready{0},tid{0};
  std::atomic<Request*> request{nullptr};
  int startup_error=0;
  void* stack_mapping=nullptr;
  void* stack_top=nullptr;
  bool started=false;
};
State state;
int Error(int value) {errno=value;return -1;}
int Process() {return static_cast<int>(Raw(SYS_getpid));}
RAW_ONLY void Notify() {
  state.event.fetch_add(1,std::memory_order_release);
  Raw(SYS_futex,Address(&state.event),FUTEX_WAKE_PRIVATE,INT_MAX);
}
void WaitEvent(int value) {
  Raw(SYS_futex,Address(&state.event),FUTEX_WAIT_PRIVATE,value);
}
class Mask {
 public:
  int Enter() {
    const uint64_t full=~uint64_t{0};
    const long result=Raw(SYS_rt_sigprocmask,SIG_SETMASK,Address(&full),Address(&old_),8);
    saved_=result==0;
    return result<0?Error(static_cast<int>(-result)):0;
  }
  ~Mask() {if(saved_)Raw(SYS_rt_sigprocmask,SIG_SETMASK,Address(&old_),0,8);}
 private:
  uint64_t old_=0;
  bool saved_=false;
};
class Gate {
 public:
  void Enter() {
    for(;;) {
      int expected=0;
      if(state.gate.compare_exchange_weak(expected,1,std::memory_order_acquire)) {
        held_=true;return;
      }
      Raw(SYS_futex,Address(&state.gate),FUTEX_WAIT_PRIVATE,1);
    }
  }
  ~Gate() {
    if(!held_)return;
    state.gate.store(0,std::memory_order_release);
    Raw(SYS_futex,Address(&state.gate),FUTEX_WAKE_PRIVATE,INT_MAX);
  }
 private:
  bool held_=false;
};
// CLONE_CHILD_CLEARTID wakes a shared FUTEX_WAIT, not FUTEX_WAIT_PRIVATE. Do not
// reuse the stack until the kernel has performed that final exit transition.
void JoinRaw() {
  for(;;) {
    const int tid=state.tid.load(std::memory_order_acquire);
    if(tid==0)return;
    Raw(SYS_futex,Address(&state.tid),FUTEX_WAIT,tid);
  }
}
RAW_ONLY int ReadPinned(Request* request) {
  const long caller=Raw(SYS_pidfd_open,request->caller_tid,O_EXCL);
  if(caller<0)return static_cast<int>(caller);
  const long pinned=Raw(SYS_pidfd_getfd,caller,request->fd,0);
  if(pinned<0) {
    Raw(SYS_close,caller);return static_cast<int>(pinned);
  }
  Snapshot* value=request->snapshot;
  value->worker_tid=static_cast<int>(Raw(SYS_gettid));
  value->worker_tgid=static_cast<int>(Raw(SYS_getpid));
  Raw(SYS_rt_sigprocmask,SIG_SETMASK,0,Address(&value->worker_mask),8);
  value->stat_result=Raw(SYS_fstat,pinned,Address(&value->identity));
  value->statfs_result=Raw(SYS_fstatfs,pinned,Address(&value->filesystem));
  value->seals_result=Raw(SYS_fcntl,pinned,F_GET_SEALS);
  // Fixed owned-control tag; not the factory authentication/projection path.
  static constexpr char tag_name[]="user.pocket4.raw-owner-control";
  value->tag_result=Raw(SYS_fgetxattr,pinned,Address(tag_name),Address(value->tag),sizeof(value->tag));
  Raw(SYS_close,pinned);
  Raw(SYS_close,caller);
  if(value->stat_result<0)return static_cast<int>(value->stat_result);
  if(value->statfs_result<0)return static_cast<int>(value->statfs_result);
  return 0;
}
RAW_ONLY int Worker(void*) {
  // clone omitted CLONE_FILES. These closes can only affect this worker's own
  // copied table, even when the caller has no descriptor slots available.
  const long closed=Raw(SYS_close_range,0,UINT_MAX,0);
  state.startup_error=closed<0?static_cast<int>(-closed):0;
  state.ready.store(1,std::memory_order_release);
  Notify();
  if(closed>=0) {
    for(;;) {
      const int observed=state.event.load(std::memory_order_acquire);
      const int command=state.command.load(std::memory_order_acquire);
      if(command==2)break;
      if(command!=1) {
        Raw(SYS_futex,Address(&state.event),FUTEX_WAIT_PRIVATE,observed);
        continue;
      }
      Request* request=state.request.load(std::memory_order_acquire);
      request->result=ReadPinned(request);
      state.request.store(nullptr,std::memory_order_release);
      state.command.store(0,std::memory_order_release);
      request->complete.store(1,std::memory_order_release);
      // After this store only process-lifetime state is accessed.
      Notify();
    }
  }
  Raw(SYS_exit,0);
  __builtin_unreachable();
}
} // namespace

int Start() {
  const int before=errno;
  const int process=Process();
  int zero=0;
  state.process.compare_exchange_strong(zero,process,std::memory_order_acq_rel);
  if(state.process.load(std::memory_order_acquire)!=process)return Error(EOPNOTSUPP);
  if(state.admission.load(std::memory_order_acquire)==1)return 0;
  Mask mask;if(mask.Enter()<0)return -1;
  Gate gate;gate.Enter();
  if(state.admission.load(std::memory_order_acquire)==2)return Error(EBUSY);
  if(state.started) {
    int closed=0;
    if(!state.admission.compare_exchange_strong(closed,1,std::memory_order_acq_rel) && closed!=1)
      return Error(EBUSY);
    errno=before;return 0;
  }
  if(state.stack_mapping==nullptr) {
    const long page=sysconf(_SC_PAGESIZE);
    if(page<=0 || page>65536)return Error(EINVAL);
    const size_t stack_size=128u*1024u;
    const size_t length=stack_size+static_cast<size_t>(page);
    void* mapping=mmap(nullptr,length,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(mapping==MAP_FAILED)return -1;
    void* bottom=static_cast<char*>(mapping)+page;
    if(mprotect(bottom,stack_size,PROT_READ|PROT_WRITE)<0) {
      const int saved=errno;munmap(mapping,length);return Error(saved);
    }
    state.stack_mapping=mapping;
    state.stack_top=static_cast<char*>(bottom)+stack_size;
  }
  state.ready.store(0,std::memory_order_relaxed);
  state.command.store(0,std::memory_order_relaxed);
  state.startup_error=0;
  // Deliberately no CLONE_FILES, no CLONE_FS and no CLONE_SETTLS. Worker may
  // never enter libc, use pthread APIs, errno, C++ TLS or arbitrary callbacks.
  const int flags=CLONE_VM|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM|
                  CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID;
  const long tid=pocket4_raw_clone_x86_64(static_cast<unsigned long>(flags),state.stack_top,
                                         &state.tid,Worker,nullptr);
  if(tid<0)return Error(static_cast<int>(-tid));
  state.started=true;
  for(;;) {
    const int event=state.event.load(std::memory_order_acquire);
    if(state.ready.load(std::memory_order_acquire))break;
    WaitEvent(event);
  }
  if(state.startup_error) {
    JoinRaw();state.started=false;return Error(state.startup_error);
  }
  int closed=0;
  if(!state.admission.compare_exchange_strong(closed,1,std::memory_order_acq_rel) && closed!=1)
    return Error(EBUSY);
  errno=before;return 0;
}
int Read(int fd,Snapshot* snapshot) {
  const int before=errno;
  if(fd<0)return Error(EBADF);
  if(snapshot==nullptr)return Error(EINVAL);
  if(state.process.load(std::memory_order_acquire)!=Process())return Error(EOPNOTSUPP);
  Mask mask;if(mask.Enter()<0)return -1;
  if(state.admission.load(std::memory_order_acquire)!=1)return Error(ESHUTDOWN);
  Gate gate;gate.Enter();
  if(state.admission.load(std::memory_order_acquire)!=1)return Error(ESHUTDOWN);
  Request request{static_cast<int>(Raw(SYS_gettid)),fd,snapshot};
  state.request.store(&request,std::memory_order_release);
  state.command.store(1,std::memory_order_release);Notify();
  for(;;) {
    const int event=state.event.load(std::memory_order_acquire);
    if(request.complete.load(std::memory_order_acquire))break;
    WaitEvent(event);
  }
  if(request.result<0)return Error(-request.result);
  errno=before;return request.result;
}
int Stop() {
  const int before=errno;
  const int process=state.process.load(std::memory_order_acquire);
  if(process==0)return 0;
  if(process!=Process())return Error(EOPNOTSUPP);
  Mask mask;if(mask.Enter()<0)return -1;
  if(state.admission.exchange(2,std::memory_order_acq_rel)==2)return Error(EBUSY);
  {
    Gate gate;gate.Enter();
    if(state.started) {
      state.command.store(2,std::memory_order_release);Notify();JoinRaw();
      state.started=false;
    }
  }
  state.admission.store(0,std::memory_order_release);Notify();errno=before;return 0;
}
void ResetAfterPrivateFork() {
  state.admission.store(0,std::memory_order_relaxed);
  state.gate.store(0,std::memory_order_relaxed);
  state.event.store(0,std::memory_order_relaxed);
  state.command.store(0,std::memory_order_relaxed);
  state.ready.store(0,std::memory_order_relaxed);
  state.tid.store(0,std::memory_order_relaxed);
  state.request.store(nullptr,std::memory_order_relaxed);
  state.startup_error=0;state.started=false;
  state.process.store(Process(),std::memory_order_release);
}
bool HasInheritedStack() {return state.stack_mapping!=nullptr;}
} // namespace pocket4::raw_metadata_owner
