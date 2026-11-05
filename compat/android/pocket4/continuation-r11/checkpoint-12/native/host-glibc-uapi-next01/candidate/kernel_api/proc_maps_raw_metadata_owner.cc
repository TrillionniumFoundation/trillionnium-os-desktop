// SPDX-License-Identifier: Apache-2.0
#include "berberis/kernel_api/proc_maps_raw_metadata_owner.h"
#include "berberis/kernel_api/proc_maps_linux_compat.h"

#include <atomic>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <fcntl.h>
#include <linux/futex.h>
#include <linux/capability.h>
#include <linux/magic.h>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
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
extern "C" __attribute__((visibility("hidden"))) long berberis_proc_metadata_raw_clone_x86_64(
    unsigned long flags,void* stack,std::atomic<int>* clear_tid,
    int(*entry)(void*),void* argument);
__asm__(
    ".text\n"
    ".p2align 4\n"
    ".hidden berberis_proc_metadata_raw_clone_x86_64\n"
    ".global berberis_proc_metadata_raw_clone_x86_64\n"
    ".type berberis_proc_metadata_raw_clone_x86_64,@function\n"
    "berberis_proc_metadata_raw_clone_x86_64:\n"
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
    ".size berberis_proc_metadata_raw_clone_x86_64,.-berberis_proc_metadata_raw_clone_x86_64\n");
namespace berberis::proc_maps_provenance::raw_metadata_owner {
namespace {
// All functions reachable from Worker must stay free of libc and TLS. Inspect
// the final target disassembly as a separate qualification gate.
#define RAW_ONLY __attribute__((no_stack_protector))
static_assert(std::atomic<int>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);
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
RAW_ONLY bool SameInode(const struct stat& a,const struct stat& b) {
  return a.st_dev==b.st_dev && a.st_ino==b.st_ino;
}
RAW_ONLY bool SameContext(const AppContext& a,const AppContext& b) {
  for(unsigned i=0;i<3;++i)if(a.uid[i]!=b.uid[i] || a.gid[i]!=b.gid[i])return false;
  for(unsigned i=0;i<6;++i)if(a.capabilities[i]!=b.capabilities[i])return false;
  if(a.group_count!=b.group_count)return false;
  for(unsigned i=0;i<a.group_count;++i)if(a.groups[i]!=b.groups[i])return false;
  return a.fsuid==b.fsuid && a.fsgid==b.fsgid && SameInode(a.root,b.root) &&
         SameInode(a.user_namespace,b.user_namespace) &&
         SameInode(a.mount_namespace,b.mount_namespace);
}
// No descriptor allocation and no libc/TLS access. Called with all kernel
// signals blocked on the caller, and independently in the fixed worker.
RAW_ONLY int ReadContext(AppContext* context) {
  long result=Raw(SYS_getresuid,Address(&context->uid[0]),Address(&context->uid[1]),
                  Address(&context->uid[2]));
  if(result<0)return static_cast<int>(result);
  result=Raw(SYS_getresgid,Address(&context->gid[0]),Address(&context->gid[1]),
             Address(&context->gid[2]));
  if(result<0)return static_cast<int>(result);
  result=Raw(SYS_setfsuid,-1L);if(result<0)return static_cast<int>(result);
  context->fsuid=static_cast<uint32_t>(result);
  result=Raw(SYS_setfsgid,-1L);if(result<0)return static_cast<int>(result);
  context->fsgid=static_cast<uint32_t>(result);
  struct __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
  static_assert(sizeof(context->capabilities)==2*sizeof(struct __user_cap_data_struct));
  result=Raw(SYS_capget,Address(&header),Address(context->capabilities));
  if(result<0)return static_cast<int>(result);
  for(unsigned i=0;i<3;++i)if(context->uid[i]==0 || context->gid[i]==0)return -EPERM;
  if(context->fsuid==0 || context->fsgid==0)return -EPERM;
  for(unsigned i=0;i<6;++i)if(context->capabilities[i]!=0)return -EPERM;
  result=Raw(SYS_getgroups,AppContext::kMaxGroups,Address(context->groups));
  if(result<0)return static_cast<int>(result);
  context->group_count=static_cast<unsigned>(result);
  struct statfs filesystem;
  static constexpr char self[]="/proc/thread-self";
  result=Raw(SYS_statfs,Address(self),Address(&filesystem));
  if(result<0)return static_cast<int>(result);
  if(static_cast<uint64_t>(filesystem.f_type)!=PROC_SUPER_MAGIC)return -EXDEV;
  static constexpr char root[]="/";
  static constexpr char userns[]="/proc/thread-self/ns/user";
  static constexpr char mountns[]="/proc/thread-self/ns/mnt";
  result=Raw(SYS_newfstatat,AT_FDCWD,Address(root),Address(&context->root),0);
  if(result<0)return static_cast<int>(result);
  result=Raw(SYS_newfstatat,AT_FDCWD,Address(userns),Address(&context->user_namespace),0);
  if(result<0)return static_cast<int>(result);
  result=Raw(SYS_newfstatat,AT_FDCWD,Address(mountns),Address(&context->mount_namespace),0);
  if(result<0)return static_cast<int>(result);
  if(static_cast<uint64_t>(context->user_namespace.st_dev)!=kTrustedUserNamespaceDevice ||
     static_cast<uint64_t>(context->user_namespace.st_ino)!=kTrustedUserNamespaceInode)return -EXDEV;
  return 0;
}
// The startup namespace authority is a real PIDFD_THREAD namespace ioctl,
// not the textual /proc namespace path used for later context comparisons.
RAW_ONLY int VerifyInitialUserNamespace(const AppContext& context) {
  const long self=Raw(SYS_pidfd_open,Raw(SYS_gettid),O_EXCL);
  if(self<0)return static_cast<int>(self);
  const long ns=Raw(SYS_ioctl,self,_IO(0xff,9),0);
  Raw(SYS_close,self);
  if(ns<0)return static_cast<int>(ns);
  struct stat info;struct statfs filesystem;
  long result=Raw(SYS_fstat,ns,Address(&info));
  if(result>=0)result=Raw(SYS_fstatfs,ns,Address(&filesystem));
  const long kind=result<0?result:Raw(SYS_ioctl,ns,NS_GET_NSTYPE,0);
  Raw(SYS_close,ns);
  if(kind<0)return static_cast<int>(kind);
  if(kind!=CLONE_NEWUSER || static_cast<uint64_t>(filesystem.f_type)!=NSFS_MAGIC ||
     static_cast<uint64_t>(info.st_dev)!=kTrustedUserNamespaceDevice ||
     static_cast<uint64_t>(info.st_ino)!=kTrustedUserNamespaceInode ||
     !SameInode(info,context.user_namespace))return -EXDEV;
  return 0;
}
enum class PinFailure {kNone,kPidfdOpen,kPidfdGetfd};
struct Request {
  int caller_tid;
  int fd;
  Snapshot* snapshot;
  const AppContext* caller_context;
  int result=-999;
  bool context_invalid=false;
  PinFailure pin_failure=PinFailure::kNone;
  std::atomic<int> complete{0};
};
struct State {
  std::atomic<int> process{0};
  std::atomic<bool> enabled{false};
  // An explicit transition closes this process generation permanently. Only
  // a private-memory child reset may discard it. Ordinary Start/Read must
  // never reopen admission while the runtime is changing credentials.
  std::atomic<bool> transition_closed{false};
  // 0 closed, 1 accepting, 2 stopping.
  std::atomic<int> admission{0};
  std::atomic<int> gate{0},event{0},command{0},ready{0},tid{0};
  std::atomic<int> inherited_tid{0};
  std::atomic<Request*> request{nullptr};
  int startup_error=0;
  void* stack_mapping=nullptr;
  void* stack_top=nullptr;
  void* inherited_stack_mapping=nullptr;
  void* inherited_stack_top=nullptr;
  bool started=false;
  AppContext generation{},startup_context{};
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
void JoinRaw(std::atomic<int>* clear_tid=&state.tid) {
  for(;;) {
    const int tid=clear_tid->load(std::memory_order_acquire);
    if(tid==0)return;
    Raw(SYS_futex,Address(clear_tid),FUTEX_WAIT,tid);
  }
}
// Gate and complete caller signal mask must already be held.
void RetireLocked() {
  if(state.started) {
    state.command.store(2,std::memory_order_release);Notify();JoinRaw();
    state.started=false;
  }
}
int PrepareOneStackLocked(void** owned_mapping,void** owned_top) {
  if(*owned_mapping!=nullptr)return 0;
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
  *owned_mapping=mapping;
  *owned_top=static_cast<char*>(bottom)+stack_size;
  return 0;
}
int PrepareStackLocked() {
  if(PrepareOneStackLocked(&state.stack_mapping,&state.stack_top)<0)return -1;
  return PrepareOneStackLocked(&state.inherited_stack_mapping,&state.inherited_stack_top);
}
int OwnProcess() {
  const int process=Process();
  int zero=0;
  state.process.compare_exchange_strong(zero,process,std::memory_order_acq_rel);
  return state.process.load(std::memory_order_acquire)==process?0:Error(EOPNOTSUPP);
}
// inherited_table is true only in the fixed one-shot worker cloned by
// this request's calling thread without CLONE_FILES. The ordinary worker
// must continue acquiring a pidfd/getfd pin from the calling thread.
RAW_ONLY int ReadPinned(Request* request,bool inherited_table) {
  Snapshot* value=request->snapshot;
  int context_result=ReadContext(&value->worker_before);
  if(context_result<0) {request->context_invalid=true;return context_result;}
  if(!SameContext(value->worker_before,state.generation) ||
     !SameContext(value->worker_before,*request->caller_context)) {
    request->context_invalid=true;return -ESTALE;
  }
  long caller=-1;
  long pinned=request->fd;
  if(!inherited_table) {
    caller=Raw(SYS_pidfd_open,request->caller_tid,O_EXCL);
    if(caller<0) {
      request->pin_failure=PinFailure::kPidfdOpen;return static_cast<int>(caller);
    }
    pinned=Raw(SYS_pidfd_getfd,caller,request->fd,0);
    if(pinned<0) {
      request->pin_failure=PinFailure::kPidfdGetfd;
      Raw(SYS_close,caller);return static_cast<int>(pinned);
    }
  }
  long result=Raw(SYS_fstat,pinned,Address(&value->identity));
  if(result>=0)result=Raw(SYS_fstatfs,pinned,Address(&value->kernel_filesystem));
  long readable=-1;
  bool ordinary=true;
  if(result>=0 && S_ISREG(value->identity.st_mode) && value->identity.st_uid==0 &&
     value->identity.st_gid==0 && (value->identity.st_mode&07777)==0444 &&
     value->identity.st_nlink==0 && value->identity.st_size>0 &&
     static_cast<uint64_t>(value->identity.st_size)<=kMaxSnapshotBytes &&
     value->kernel_filesystem.f_type==TMPFS_MAGIC) {
    const long flags=Raw(SYS_fcntl,pinned,F_GETFL);
    if(flags<0)result=flags;
    else if((flags&O_PATH)==0)readable=pinned;
    else {
      static constexpr char directory_path[]="/proc/thread-self/fd";
      const long directory=Raw(SYS_openat,AT_FDCWD,Address(directory_path),
                               O_PATH|O_DIRECTORY|O_CLOEXEC,0);
      if(directory<0)result=directory;
      else {
        struct statfs directory_fs;
        result=Raw(SYS_fstatfs,directory,Address(&directory_fs));
        if(result>=0 && static_cast<uint64_t>(directory_fs.f_type)!=PROC_SUPER_MAGIC)result=-EXDEV;
        if(result>=0) {
          char number[12];char* end=number+sizeof(number);*--end=0;
          unsigned current=static_cast<unsigned>(pinned);
          do{*--end=static_cast<char>('0'+current%10);current/=10;}while(current!=0);
          readable=Raw(SYS_openat,directory,Address(end),O_RDONLY|O_CLOEXEC,0);
          if(readable<0)result=readable;
          else {
            result=Raw(SYS_fstat,readable,Address(&value->final_identity));
            if(result>=0 && !SameInode(value->identity,value->final_identity))result=-ESTALE;
          }
        }
        Raw(SYS_close,directory);
      }
    }
    if(result>=0) {
      const long count=Raw(SYS_fgetxattr,readable,Address(kTagName),Address(value->tag),sizeof(value->tag));
      if(count==-ENODATA || count==-ENOTSUP)ordinary=true;
      else if(count<0)result=count;
      else {
        const long seals=Raw(SYS_fcntl,readable,F_GET_SEALS);
        if(seals<0)result=seals;
        else if((static_cast<unsigned long>(seals)&kRequiredSeals)==kRequiredSeals) {
          ordinary=false;value->tag_size=static_cast<size_t>(count);
          result=Raw(SYS_fstat,readable,Address(&value->final_identity));
          if(result>=0 && (!SameInode(value->identity,value->final_identity) ||
             value->identity.st_mode!=value->final_identity.st_mode ||
             value->identity.st_uid!=value->final_identity.st_uid ||
             value->identity.st_gid!=value->final_identity.st_gid ||
             value->identity.st_size!=value->final_identity.st_size ||
             value->final_identity.st_nlink!=0))result=-ESTALE;
        }
      }
    }
  }
  if(readable>=0 && readable!=pinned)Raw(SYS_close,readable);
  if(!inherited_table) {Raw(SYS_close,pinned);Raw(SYS_close,caller);}
  if(result<0)return static_cast<int>(result);
  context_result=ReadContext(&value->worker_after);
  if(context_result<0) {request->context_invalid=true;return context_result;}
  if(!SameContext(value->worker_before,value->worker_after)) {
    request->context_invalid=true;return -ESTALE;
  }
  value->tagged=ordinary?0:1;
  return 0;
}
RAW_ONLY int InheritedWorker(void* opaque) {
  auto* request=static_cast<Request*>(opaque);
  request->result=ReadPinned(request,true);
  request->complete.store(1,std::memory_order_release);
  Raw(SYS_exit,0);
  __builtin_unreachable();
}
// Caller holds Gate and Mask throughout clone, metadata and kernel
// clear-tid. This is never used to establish initial namespace authority:
// only an already started, explicitly admitted generation reaches it.
void ReadInheritedAfterAllocationFailure(Request* original) {
  if(state.inherited_stack_top==nullptr ||
     state.inherited_tid.load(std::memory_order_acquire)!=0) {
    original->result=-ESHUTDOWN;return;
  }
  Request inherited{original->caller_tid,original->fd,original->snapshot,
                    original->caller_context};
  const int flags=CLONE_VM|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM|
                  CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID;
  const long tid=berberis_proc_metadata_raw_clone_x86_64(
      static_cast<unsigned long>(flags),state.inherited_stack_top,
      &state.inherited_tid,InheritedWorker,&inherited);
  if(tid<0) {original->result=static_cast<int>(tid);return;}
  JoinRaw(&state.inherited_tid);
  original->result=inherited.complete.load(std::memory_order_acquire)?inherited.result:-EIO;
  original->context_invalid=inherited.context_invalid;
}
RAW_ONLY int Worker(void*) {
  // clone omitted CLONE_FILES. These closes can only affect this worker's own
  // copied table, even when the caller has no descriptor slots available.
  long initialized=Raw(SYS_close_range,0,UINT_MAX,0);
  if(initialized>=0)initialized=ReadContext(&state.startup_context);
  if(initialized>=0 && !SameContext(state.startup_context,state.generation))initialized=-ESTALE;
  if(initialized>=0)initialized=VerifyInitialUserNamespace(state.startup_context);
  state.startup_error=initialized<0?static_cast<int>(-initialized):0;
  state.ready.store(1,std::memory_order_release);
  Notify();
  if(initialized>=0) {
    for(;;) {
      const int observed=state.event.load(std::memory_order_acquire);
      const int command=state.command.load(std::memory_order_acquire);
      if(command==2)break;
      if(command!=1) {
        Raw(SYS_futex,Address(&state.event),FUTEX_WAIT_PRIVATE,observed);
        continue;
      }
      Request* request=state.request.load(std::memory_order_acquire);
      request->result=ReadPinned(request,false);
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

int PrepareInheritedStack() {
  const int before=errno;
  if(OwnProcess()<0)return -1;
  Mask mask;if(mask.Enter()<0)return -1;
  Gate gate;gate.Enter();
  if(PrepareStackLocked()<0)return -1;
  errno=before;return 0;
}
int Start() {
  const int before=errno;
  if(OwnProcess()<0)return -1;
  Mask mask;if(mask.Enter()<0)return -1;
  Gate gate;gate.Enter();
  if(state.transition_closed.load(std::memory_order_acquire))return Error(ESHUTDOWN);
  if(state.admission.load(std::memory_order_acquire)==2)return Error(EBUSY);
  AppContext caller{};
  const int context_result=ReadContext(&caller);
  if(context_result<0 || (state.started && !SameContext(caller,state.generation))) {
    if(state.started) {
      state.transition_closed.store(true,std::memory_order_release);
      state.admission.store(0,std::memory_order_release);
      state.enabled.store(false,std::memory_order_release);RetireLocked();
    }
    return Error(context_result<0?-context_result:ESTALE);
  }
  if(state.started) {
    int closed=0;
    if(!state.admission.compare_exchange_strong(closed,1,std::memory_order_acq_rel) && closed!=1)
      return Error(EBUSY);
    errno=before;return 0;
  }
  if(PrepareStackLocked()<0)return -1;
  state.generation=caller;
  state.ready.store(0,std::memory_order_relaxed);
  state.command.store(0,std::memory_order_relaxed);
  state.startup_error=0;
  // Deliberately no CLONE_FILES, no CLONE_FS and no CLONE_SETTLS. Worker may
  // never enter libc, use pthread APIs, errno, C++ TLS or arbitrary callbacks.
  const int flags=CLONE_VM|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM|
                  CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID;
  const long tid=berberis_proc_metadata_raw_clone_x86_64(static_cast<unsigned long>(flags),state.stack_top,
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
  AppContext after{};
  const int after_result=ReadContext(&after);
  if(after_result<0 || !SameContext(caller,after) ||
     state.transition_closed.load(std::memory_order_acquire)) {
    state.transition_closed.store(true,std::memory_order_release);
    state.admission.store(0,std::memory_order_release);
    RetireLocked();return Error(after_result<0?-after_result:ESTALE);
  }
  int closed=0;
  if(!state.admission.compare_exchange_strong(closed,1,std::memory_order_acq_rel) && closed!=1)
    return Error(EBUSY);
  state.enabled.store(true,std::memory_order_release);
  errno=before;return 0;
}
int Read(int fd,Snapshot* snapshot) {
  const int before=errno;
  if(fd<0)return Error(EBADF);
  if(snapshot==nullptr)return Error(EINVAL);
  const int owner_process=state.process.load(std::memory_order_acquire);
  if(owner_process==0)return Error(ESHUTDOWN);
  if(owner_process!=Process())return Error(EOPNOTSUPP);
  Mask mask;if(mask.Enter()<0)return -1;
  if(state.admission.load(std::memory_order_acquire)!=1)return Error(ESHUTDOWN);
  Gate gate;gate.Enter();
  if(state.admission.load(std::memory_order_acquire)!=1)return Error(ESHUTDOWN);
  AppContext caller{};
  const int context_result=ReadContext(&caller);
  if(context_result<0 || !SameContext(caller,state.generation)) {
    state.transition_closed.store(true,std::memory_order_release);
    state.admission.store(0,std::memory_order_release);
    state.enabled.store(false,std::memory_order_release);RetireLocked();
    return Error(context_result<0?-context_result:ESTALE);
  }
  // Never publish partially written metadata to the caller on a failed read.
  // The request and its context are held until the worker's last stack access.
  Snapshot value{};
  Request request{static_cast<int>(Raw(SYS_gettid)),fd,&value,&caller};
  state.request.store(&request,std::memory_order_release);
  state.command.store(1,std::memory_order_release);Notify();
  for(;;) {
    const int event=state.event.load(std::memory_order_acquire);
    if(request.complete.load(std::memory_order_acquire))break;
    WaitEvent(event);
  }
  // Only these two exact allocation stages qualify. A later EMFILE from
  // a filesystem, tag read or O_PATH reopen is preserved as an error.
  if(request.result==-EMFILE &&
     (request.pin_failure==PinFailure::kPidfdOpen ||
      request.pin_failure==PinFailure::kPidfdGetfd))
    ReadInheritedAfterAllocationFailure(&request);
  AppContext after{};
  const int after_result=ReadContext(&after);
  if(after_result<0 || !SameContext(caller,after) || request.context_invalid) {
    state.transition_closed.store(true,std::memory_order_release);
    state.admission.store(0,std::memory_order_release);
    state.enabled.store(false,std::memory_order_release);RetireLocked();
    return Error(after_result<0?-after_result:
                 (request.context_invalid && request.result<0?-request.result:ESTALE));
  }
  if(request.result<0)return Error(-request.result);
  // Retain the exact raw result for the guest syscall adapter. Host libc
  // normalization belongs only to the separate public filesystem view.
  KernelStatfsToLibc(value.kernel_filesystem, &value.filesystem);
  *snapshot=value;
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
    RetireLocked();state.enabled.store(false,std::memory_order_release);
  }
  state.admission.store(0,std::memory_order_release);Notify();errno=before;return 0;
}
bool Enabled() {
  return state.process.load(std::memory_order_acquire)==Process() &&
         state.enabled.load(std::memory_order_acquire) &&
         state.admission.load(std::memory_order_acquire)==1 &&
         !state.transition_closed.load(std::memory_order_acquire);
}
int QuiesceBeforeTransition() {
  if(OwnProcess()<0)return -1;
  state.transition_closed.store(true,std::memory_order_release);
  return Stop();
}
void ResetAfterPrivateFork() {
  // Caller must prove private memory. Mutating this state from a CLONE_VM
  // child would discard a live parent's synchronization and is forbidden.
  state.enabled.store(false,std::memory_order_relaxed);
  state.transition_closed.store(false,std::memory_order_relaxed);
  state.admission.store(0,std::memory_order_relaxed);
  state.gate.store(0,std::memory_order_relaxed);
  state.event.store(0,std::memory_order_relaxed);
  state.command.store(0,std::memory_order_relaxed);
  state.ready.store(0,std::memory_order_relaxed);
  state.tid.store(0,std::memory_order_relaxed);
  state.inherited_tid.store(0,std::memory_order_relaxed);
  state.request.store(nullptr,std::memory_order_relaxed);
  state.startup_error=0;state.started=false;
  state.generation=AppContext{};state.startup_context=AppContext{};
  state.process.store(Process(),std::memory_order_release);
}
bool HasInheritedStack() {
  return state.stack_mapping!=nullptr && state.inherited_stack_mapping!=nullptr;
}
} // namespace berberis::proc_maps_provenance::raw_metadata_owner
