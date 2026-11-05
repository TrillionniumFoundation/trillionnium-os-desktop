// SPDX-License-Identifier: Apache-2.0
#include "berberis/kernel_api/proc_maps_generation.h"
#include "berberis/kernel_api/proc_maps_raw_metadata_owner.h"
#include <atomic>
#include <errno.h>
#include <sched.h>
#include <linux/seccomp.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>
namespace berberis::proc_maps_provenance::generation {
namespace {
using namespace droidloom::native_generation;
enum Phase {kCold,kPrepared,kReady,kClosed,kRetired,kFaulted,kExecPending};
std::atomic<int> process{0},previous_process{0},phase{kCold};
[[maybe_unused]] int Error(int value) {errno=value;return -1;}
int CurrentProcess() {return static_cast<int>(syscall(SYS_getpid));}
int CloseGeneration() {
  if(process.load(std::memory_order_acquire)!=CurrentProcess())return Error(EOPNOTSUPP);
  phase.store(kClosed,std::memory_order_release);
  return raw_metadata_owner::QuiesceBeforeTransition();
}
bool Ready() {
  return process.load(std::memory_order_acquire)==CurrentProcess() &&
         phase.load(std::memory_order_acquire)==kReady && raw_metadata_owner::Enabled();
}
int DispatchEnabled(const Request& request) {
  const int current=CurrentProcess();
  if(request.caller_tgid!=current)return -ESTALE;
  const int owner=process.load(std::memory_order_acquire);
  const int current_phase=phase.load(std::memory_order_acquire);
  const bool private_child=(request.flags&kPrivateForkChild)!=0;
  switch(request.operation) {
    case kPrepareMemory:
      if(request.flags!=0 || request.previous_tgid!=0 || owner!=0 || current_phase!=kCold)
        return -EPROTO;
      if(raw_metadata_owner::PrepareInheritedStack()<0)return -errno;
      process.store(current,std::memory_order_release);
      phase.store(kPrepared,std::memory_order_release);
      return 0;
    case kBeforeZygoteFork:
      if(request.flags!=0 || owner!=current || request.previous_tgid!=owner ||
         (current_phase!=kPrepared && current_phase!=kReady && current_phase!=kClosed))
        return -EPROTO;
      return CloseGeneration()==0?0:-errno;
    case kAfterSpecialize: {
      if(owner==0 || request.previous_tgid!=owner)return -EPROTO;
      if(current!=owner) {
        // This grant is issued only from ART's known private-memory zygote
        // fork path, after SpecializeCommon. TGID inequality alone is not
        // treated as proof that arbitrary CLONE_VM memory is private.
        if(!private_child || current_phase!=kClosed)return -EPROTO;
        raw_metadata_owner::ResetAfterPrivateFork();
        previous_process.store(owner,std::memory_order_relaxed);
        process.store(current,std::memory_order_release);
        phase.store(kPrepared,std::memory_order_release);
      } else if(private_child || (current_phase!=kPrepared && current_phase!=kReady)) {
        return -EPROTO;
      }
      if(raw_metadata_owner::Start()<0) {
        const int error=errno;
        phase.store(kFaulted,std::memory_order_release);
        return -error;
      }
      phase.store(kReady,std::memory_order_release);
      return 0;
    }
    case kCheckReady:
      if(request.flags!=0 || request.previous_tgid!=owner)return -EPROTO;
      return Ready()?0:-EPROTONOSUPPORT;
    case kBeforeUnload:
      if(owner==0)return -EPROTO;
      if(current!=owner) {
        if(!private_child || request.previous_tgid!=owner || current_phase!=kClosed)
          return -EPROTO;
        raw_metadata_owner::ResetAfterPrivateFork();
        previous_process.store(owner,std::memory_order_relaxed);
        process.store(current,std::memory_order_release);
      } else {
        const int expected=private_child?previous_process.load(std::memory_order_acquire):owner;
        if(request.previous_tgid!=expected)return -EPROTO;
      }
      if(CloseGeneration()<0)return -errno;
      phase.store(kRetired,std::memory_order_release);
      return 0;
  }
  return -EINVAL;
}
}
int Dispatch(const droidloom::native_generation::Request* request) {
  using namespace droidloom::native_generation;
  if(request==nullptr)return -EINVAL;
  if(request->version!=kVersion || request->size!=sizeof(Request) ||
     request->protocol0!=kProtocol0 || request->protocol1!=kProtocol1)
    return -EPROTONOSUPPORT;
  if((request->flags&~(kPrivateForkChild|kChildZygote))!=0)return -EINVAL;
  if(request->operation!=kAfterSpecialize && (request->flags&kChildZygote)!=0)return -EINVAL;
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  return DispatchEnabled(*request);
#else
  (void)&DispatchEnabled;
  return -EOPNOTSUPP;
#endif
}
int RequireReadyForNativeBridge() {
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  return Ready()?0:Error(EPROTONOSUPPORT);
#else
  (void)&Ready;
  return 0;
#endif
}
int BeforeGuestClone(unsigned long flags) {
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  const unsigned long namespaces=CLONE_NEWCGROUP|CLONE_NEWIPC|CLONE_NEWNET|
      CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWUSER|CLONE_NEWUTS;
  if((flags&namespaces)!=0 || ((flags&CLONE_VM)!=0 && (flags&CLONE_THREAD)==0))
    return Error(EOPNOTSUPP);
  if(!Ready())return Error(ESHUTDOWN);
#else
  (void)flags;
#endif
  return 0;
}
void AfterPrivateGuestFork() {
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  // Called only in CloneGuestThread's !(flags & CLONE_VM), pid == 0 branch.
  const int parent=process.load(std::memory_order_relaxed);
  if(parent==CurrentProcess())return;
  raw_metadata_owner::ResetAfterPrivateFork();
  previous_process.store(parent,std::memory_order_relaxed);
  process.store(CurrentProcess(),std::memory_order_release);
  phase.store(kPrepared,std::memory_order_release);
  if(raw_metadata_owner::Start()<0)phase.store(kFaulted,std::memory_order_release);
  else phase.store(kReady,std::memory_order_release);
  // The kernel fork result remains 0 in this child even if the owner's
  // preparation fails. Subsequent metadata fails closed; no fabricated fork
  // failure and no new host thread is started by a later metadata request.
#endif
}
int BeforeGuestSyscall(long number,unsigned long first,unsigned long second) {
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  // ARM64 generic Linux numbers, not host x86_64 syscall numbers.
  switch(number) {
    case 91: // capset
    case 143: case 144: case 145: case 146: // setregid/setgid/setreuid/setuid
    case 147: case 149: case 159: // setresuid/setresgid/setgroups
    case 40: case 41: case 51: case 39: // mount/pivot_root/chroot/umount2
    case 268: case 429: case 442: // setns/move_mount/mount_setattr
      return Error(EOPNOTSUPP);
    case 151: case 152: // setfsuid/setfsgid: -1 is the kernel's read-only query.
      if(static_cast<uint32_t>(first)!=UINT32_MAX)return Error(EOPNOTSUPP);
      break;
    case 97: // unshare: independent files/fs are supported by per-caller pinning.
      if((first&~static_cast<unsigned long>(CLONE_FILES|CLONE_FS))!=0)
        return Error(EOPNOTSUPP);
      break;
    case 167: // prctl credential/security changes; query operations still run.
      if(first==PR_SET_KEEPCAPS || first==PR_SET_SECUREBITS ||
         (first==PR_CAP_AMBIENT && second!=PR_CAP_AMBIENT_IS_SET) ||
         first==PR_SET_NO_NEW_PRIVS || first==PR_SET_SECCOMP ||
         first==PR_SET_DUMPABLE || first==PR_CAPBSET_DROP)
        return Error(EOPNOTSUPP);
      break;
    case 277: // seccomp installations cannot cross an unregistered worker generation.
      if(first==SECCOMP_SET_MODE_FILTER || first==SECCOMP_SET_MODE_STRICT)
        return Error(EOPNOTSUPP);
      break;
    case 94:
      return BeforeGuestExitGroup();
  }
#else
  (void)number;(void)first;(void)second;
#endif
  return 0;
}
int BeforeGuestExec() {
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  if(!Ready())return Error(ESHUTDOWN);
  int expected=kReady;
  if(!phase.compare_exchange_strong(expected,kExecPending,std::memory_order_acq_rel))
    return Error(ESHUTDOWN);
  if(raw_metadata_owner::Stop()<0) {
    const int error=errno;phase.store(kFaulted,std::memory_order_release);return Error(error);
  }
#endif
  return 0;
}
void AfterGuestExecFailure() {
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  const int saved=errno;
  if(process.load(std::memory_order_acquire)==CurrentProcess() &&
     phase.load(std::memory_order_acquire)==kExecPending) {
    if(raw_metadata_owner::Start()<0)phase.store(kFaulted,std::memory_order_release);
    else phase.store(kReady,std::memory_order_release);
  }
  errno=saved;
#endif
}
int BeforeGuestExitGroup() {
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  return CloseGeneration();
#else
  return 0;
#endif
}
}
extern "C" __attribute__((visibility("default"))) int DroidloomBerberisGenerationV1(
    const droidloom::native_generation::Request* request) {
  return berberis::proc_maps_provenance::generation::Dispatch(request);
}
extern "C" __attribute__((visibility("default"),used,retain)) const char DroidloomBerberisGenerationMarker[]=
#if BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  "DROIDLOOM_NATIVE_GENERATION=1;ROLE=ENGINE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;";
#else
  "DROIDLOOM_NATIVE_GENERATION=0;ROLE=ENGINE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;";
#endif
