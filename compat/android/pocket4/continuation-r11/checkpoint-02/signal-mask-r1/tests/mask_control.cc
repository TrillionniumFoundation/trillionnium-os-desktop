#define _GNU_SOURCE 1
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <ucontext.h>
#include <unistd.h>

#include "berberis/guest_os_primitives/guest_signal.h"
#include "berberis/guest_os_primitives/guest_signal_arch.h"
#include "guest_context_arch.h"
#if CANDIDATE
#include "scoped_guest_signal_mask.h"
#endif

namespace b = berberis;
static constexpr int kSignal = SIGUSR2;
static constexpr uint64_t Bit(int s) { return uint64_t{1} << (s-1); }
static uint64_t KernelMask() {
  uint64_t mask = 0;
  if (syscall(SYS_rt_sigprocmask,SIG_SETMASK,nullptr,&mask,8)) _exit(90);
  return mask;
}
static void SetMask(uint64_t mask) {
  if (syscall(SYS_rt_sigprocmask,SIG_SETMASK,&mask,nullptr,8)) _exit(91);
}
static void Trigger() {
  if (syscall(SYS_tgkill,syscall(SYS_getpid),syscall(SYS_gettid),kSignal)) _exit(92);
}
static uint64_t ReadAt(void* p, size_t offset) {
  uint64_t x; memcpy(&x,static_cast<unsigned char*>(p)+offset,8); return x;
}
static void WriteAt(void* p, size_t offset, uint64_t x) {
  memcpy(static_cast<unsigned char*>(p)+offset,&x,8);
}
struct Capture { uint64_t context_mask, live, live_after_edit, nested_live_after; };
static Capture captures[2];
static b::GuestThread thread;
static b::Guest_sigaction action;
static int count, mode, depth;
static uint64_t entered, expected_resume;

static void Invoke(siginfo_t* info, b::HostSigset* resume) {
#if CANDIDATE
  b::ProcessGuestSignal(&thread,&action,info,resume);
#else
  (void)resume;
  b::ProcessGuestSignal(&thread,&action,info);
#endif
}
static void HostHandler(int, siginfo_t* info, void* opaque) {
  auto* context = static_cast<ucontext_t*>(opaque);
  Invoke(info,&context->uc_sigmask);
}
namespace berberis {
void FixtureGuestHandler(GuestAddr, int, siginfo_t*, void* context) {
  const int slot = count++;
  if (slot > 1) _exit(93);
  Capture& capture = captures[slot];
  capture.context_mask=ReadAt(context,40);
  capture.live=KernelMask();
  if (mode == 2 && depth == 0) {
    ++depth;
    Trigger();
    --depth;
    capture.nested_live_after=KernelMask();
  }
  if (mode == 1 || mode == 2) {
    uint64_t edited = depth ? capture.live | Bit(SIGTERM) : expected_resume;
    // Both unblockable bits are deliberately requested through guest context.
    WriteAt(context,40,edited|Bit(SIGKILL)|Bit(SIGSTOP));
    capture.live_after_edit=KernelMask();
  }
  // Actual GuestContext::Restore must still restore edited CPU state.
  WriteAt(context,176+8,0x5a01);
}
}

static bool Run(const char* name, bool host_frame, bool nodefer, int selected_mode) {
  const uint64_t saved=KernelMask();
  entered=Bit(SIGUSR1)|Bit(64);
  expected_resume=Bit(SIGUSR2)|Bit(64);
  count=depth=0;mode=selected_mode;memset(captures,0,sizeof(captures));
  action={};action.guest_sa_sigaction=4;action.sa_flags=SA_SIGINFO|(nodefer?SA_NODEFER:0);
  action.sa_mask.bits[0]=Bit(SIGALRM)|Bit(SIGUSR1);
  struct sigaction sa{},old{};
  sa.sa_sigaction=HostHandler;sa.sa_flags=static_cast<int>(action.sa_flags);
  sigemptyset(&sa.sa_mask);sigaddset(&sa.sa_mask,SIGALRM);sigaddset(&sa.sa_mask,SIGUSR1);
  if (sigaction(kSignal,&sa,&old)) _exit(94);
  SetMask(entered);
  thread.state()->cpu.x[0]=0x1111;
  if(host_frame) Trigger();
  else {siginfo_t info{};info.si_signo=kSignal;Invoke(&info,nullptr);}
  const uint64_t after=KernelMask();
  SetMask(saved);
  if(sigaction(kSignal,&old,nullptr)) _exit(95);
  const uint64_t expected_live=entered|Bit(SIGALRM)|(nodefer?0:Bit(kSignal));
  bool pass=count==(mode==2?2:1) && captures[0].context_mask==entered &&
      captures[0].live==expected_live && after==(mode?expected_resume:entered) &&
      thread.state()->cpu.x[0]==0x5a01;
  if(mode) pass &= captures[0].live_after_edit==(mode==2?expected_live|Bit(SIGTERM):expected_live);
  if(mode==2) pass &= captures[1].context_mask==expected_live && captures[1].live==expected_live &&
      captures[0].nested_live_after==(expected_live|Bit(SIGTERM));
  printf("{\"case\":\"%s\",\"pass\":%s,\"signals\":%d,\"context\":\"0x%016llx\","
      "\"live\":\"0x%016llx\",\"after_real_return\":\"0x%016llx\","
      "\"nested_context\":\"0x%016llx\",\"nested_return_live\":\"0x%016llx\"}\n",
      name,pass?"true":"false",count,(unsigned long long)captures[0].context_mask,
      (unsigned long long)captures[0].live,(unsigned long long)after,
      (unsigned long long)captures[1].context_mask,(unsigned long long)captures[0].nested_live_after);
  return pass;
}
int main() {
  struct rlimit no_core{0,0};setrlimit(RLIMIT_CORE,&no_core);
  alarm(10);
  bool all=true;
  all &= Run("host_frame_original_mask",true,false,0);
  all &= Run("host_frame_nodefer",true,true,0);
  all &= Run("host_frame_edited_mask_real_sigreturn",true,false,1);
  all &= Run("deferred_original_mask",false,false,0);
  all &= Run("deferred_edited_mask",false,false,1);
  all &= Run("nested_nodefer_frame_masks",true,true,2);
#if CANDIDATE
  const uint64_t saved=KernelMask();
  b::HostSigset host_mask, action_mask{};
  memset(&host_mask,0xa5,sizeof(host_mask));memcpy(&host_mask,&saved,8);
  unsigned char tail[sizeof(host_mask)];memcpy(tail,&host_mask,sizeof(host_mask));
  {
    b::ScopedGuestSignalMask scope(&action_mask,&host_mask);
    scope.Commit(Bit(SIGUSR1)|Bit(SIGKILL)|Bit(SIGSTOP));
  }
  uint64_t committed=0;memcpy(&committed,&host_mask,8);
  const bool canary=committed==Bit(SIGUSR1)&&
      memcmp(reinterpret_cast<unsigned char*>(&host_mask)+8,tail+8,sizeof(host_mask)-8)==0;
  printf("{\"case\":\"only_kernel_low64_written_and_unblockable_filtered\",\"pass\":%s}\n",canary?"true":"false");
  all &= canary;
  SetMask(saved);
#endif
  return all?0:1;
}
