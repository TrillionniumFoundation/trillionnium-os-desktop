// Fixed syscall-only worker. Independently inspect the final machine code.
#include "owned_snapshot.h"
#include <climits>
#include <linux/futex.h>
#include <sched.h>
#include <sys/syscall.h>

#if !defined(__x86_64__)
#error This mechanism control supports only the x86_64 host syscall ABI.
#endif
static_assert(SYS_clone == 56 && SYS_exit == 60);
static_assert(std::atomic<int>::is_always_lock_free);

// Instruction sequence copied from the frozen R21 trampoline; only the symbol
// is renamed. In particular parent_tid and child_tid refer to the same atomic.
extern "C" __attribute__((visibility("hidden"))) long OwnedFdSnapshotClone(
    unsigned long flags, void* stack, std::atomic<int>* clear_tid,
    int (*entry)(void*), void* argument);
__asm__(
    ".text\n"
    ".p2align 4\n"
    ".hidden OwnedFdSnapshotClone\n"
    ".global OwnedFdSnapshotClone\n"
    ".type OwnedFdSnapshotClone,@function\n"
    "OwnedFdSnapshotClone:\n"
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
    ".size OwnedFdSnapshotClone,.-OwnedFdSnapshotClone\n");

#define RAW_ONLY __attribute__((no_stack_protector))
RAW_ONLY __attribute__((always_inline)) inline long Raw(
    long number, long a=0, long b=0, long c=0, long d=0, long e=0, long f=0) {
  register long r10 __asm__("r10")=d;
  register long r8 __asm__("r8")=e;
  register long r9 __asm__("r9")=f;
  long result;
  __asm__ volatile("syscall":"=a"(result):"a"(number),"D"(a),"S"(b),"d"(c),
                   "r"(r10),"r"(r8),"r"(r9):"rcx","r11","memory");
  return result;
}
template<class T> RAW_ONLY __attribute__((always_inline)) inline long Address(T* p) {
  return reinterpret_cast<long>(p);
}
long OwnedRaw(long number,long a,long b,long c,long d,long e,long f) {
  return Raw(number,a,b,c,d,e,f);
}

extern "C" RAW_ONLY __attribute__((noinline, visibility("hidden")))
int OwnedFdSnapshotWorker(void* opaque) {
  auto* request=static_cast<OwnedSnapshotRequest*>(opaque);
  request->ready.store(1,std::memory_order_release);
  Raw(SYS_futex,Address(&request->ready),FUTEX_WAKE_PRIVATE,INT_MAX);
  while(request->go.load(std::memory_order_acquire)==0)
    Raw(SYS_futex,Address(&request->go),FUTEX_WAIT_PRIVATE,0);
  // The kernel copied this calling thread's file table at clone. No CLONE_FILES
  // and no later helper FD means close/dup in the caller cannot replace this
  // inherited open-file description. All inherited references die on exit.
  long result=Raw(SYS_fstat,request->fd,Address(&request->internal.identity));
  if(result>=0)
    result=Raw(SYS_fstatfs,request->fd,Address(&request->internal.filesystem));
  request->result=static_cast<int>(result);
  request->complete.store(1,std::memory_order_release);
  // The trampoline performs raw SYS_exit; no libc/TLS/callback follows.
  return 0;
}

__attribute__((noinline)) long SpawnOwnedFdSnapshot(
    void* stack_top,std::atomic<int>* tid,OwnedSnapshotRequest* request) {
  constexpr unsigned long flags=CLONE_VM|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM|
                                CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID;
  return OwnedFdSnapshotClone(flags,stack_top,tid,OwnedFdSnapshotWorker,request);
}
