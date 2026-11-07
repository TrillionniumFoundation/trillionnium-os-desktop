// SPDX-License-Identifier: Apache-2.0
// Owned mechanism probe only. This is not linked into the native bridge.
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <linux/futex.h>
#include <new>
#include <sched.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#if !defined(__x86_64__) || defined(__ILP32__)
#error Qualified implementation target is Linux x86_64 LP64 only.
#endif
static_assert(std::atomic<int>::is_always_lock_free);
static_assert(sizeof(long) == 8 && SYS_clone == 56 && SYS_exit == 60);

namespace {
constexpr unsigned kUid = 61171;
constexpr unsigned kCapabilityMask = (1u << CAP_SETUID) | (1u << CAP_SETGID) |
                                      (1u << CAP_SETPCAP);
constexpr size_t kStackSize = 128 * 1024;
#define RAW_ONLY __attribute__((no_stack_protector))
RAW_ONLY __attribute__((always_inline)) inline long Raw(
    long number, long a=0, long b=0, long c=0, long d=0, long e=0, long f=0) {
  register long r10 __asm__("r10") = d;
  register long r8 __asm__("r8") = e;
  register long r9 __asm__("r9") = f;
  long result;
  __asm__ volatile("syscall" : "=a"(result) : "a"(number), "D"(a), "S"(b), "d"(c),
                   "r"(r10), "r"(r8), "r"(r9) : "rcx", "r11", "memory");
  return result;
}
template<class T> RAW_ONLY __attribute__((always_inline)) inline long Ptr(T* p) {
  return reinterpret_cast<long>(p);
}

struct Arm {
  int caller_tid = 0;
  int source_fd = -1;
  bool separate_process = false;
  std::atomic<int> clear_tid{0};
  std::atomic<int> complete{0};
  int observed_pid = 0;
  int observed_tid = 0;
  long clear_caps = -999;
  long read_caps = -999;
  long parent_death = -999;
  long close_table = -999;
  long pidfd_open = -999;
  long pidfd_getfd = -999;
  long stat_result = -999;
  long statfs_result = -999;
  __user_cap_data_struct caller_caps[2]{};
  __user_cap_data_struct caps[2]{};
  struct stat info{};
  struct statfs filesystem{};
  int clone_errno = 0;
  int wait_status = -1;
  bool joined = false;
  bool stat_equal = false;
  bool statfs_equal = false;
  bool caller_caps_unchanged = false;
  bool source_survived = false;
  bool passed = false;
};
struct Report {
  int setup_errno = 0;
  int setup_step = 0;
  int caller_pid = 0;
  bool mask_restored = false;
  Arm same;
  Arm different;
  bool passed = false;
};

extern "C" __attribute__((visibility("hidden"))) long owned_zero_cap_clone(
    unsigned long flags, void* stack, std::atomic<int>* tid,
    int(*entry)(void*), void* argument);
__asm__(
    ".text\n.p2align 4\n.hidden owned_zero_cap_clone\n.global owned_zero_cap_clone\n"
    ".type owned_zero_cap_clone,@function\nowned_zero_cap_clone:\n"
    "andq $-16,%rsi\nsubq $16,%rsi\nmovq %rcx,0(%rsi)\nmovq %r8,8(%rsi)\n"
    "movq %rdx,%r10\nxorl %r8d,%r8d\nmovl $56,%eax\nsyscall\n"
    "testq %rax,%rax\njnz 1f\nxorl %ebp,%ebp\nmovq 8(%rsp),%rdi\n"
    "call *0(%rsp)\nmovl %eax,%edi\nmovl $60,%eax\nsyscall\nud2\n1: ret\n"
    ".size owned_zero_cap_clone,.-owned_zero_cap_clone\n");

// All reached helpers inline. Binary audit must prove no libc/TLS/callback
// edges before an actual execution. This raw child never modifies caller caps.
RAW_ONLY __attribute__((noinline,used)) int ZeroCapWorker(void* opaque) {
  auto* arm = static_cast<Arm*>(opaque);
  __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3, 0};
  __user_cap_data_struct zeros[2]{};
  // The first syscall in this worker removes its inherited privilege.
  arm->clear_caps = Raw(SYS_capset, Ptr(&header), Ptr(zeros));
  arm->read_caps = Raw(SYS_capget, Ptr(&header), Ptr(arm->caps));
  arm->observed_pid = static_cast<int>(Raw(SYS_getpid));
  arm->observed_tid = static_cast<int>(Raw(SYS_gettid));
  if (arm->separate_process) {
    arm->parent_death = Raw(SYS_prctl, PR_SET_PDEATHSIG, SIGKILL);
    if (arm->parent_death < 0 || Raw(SYS_getppid) != arm->caller_tid) goto done;
  }
  if (arm->clear_caps < 0 || arm->read_caps < 0) goto done;
  for (unsigned i=0; i<2; ++i) {
    if (arm->caps[i].effective || arm->caps[i].permitted || arm->caps[i].inheritable) goto done;
  }
  // CLONE_FILES was omitted. These closes only affect this raw worker table.
  arm->close_table = Raw(SYS_close_range, 0, UINT32_MAX, 0);
  if (arm->close_table < 0) goto done;
  arm->pidfd_open = Raw(SYS_pidfd_open, arm->caller_tid, O_EXCL);
  if (arm->pidfd_open < 0) goto done;
  arm->pidfd_getfd = Raw(SYS_pidfd_getfd, arm->pidfd_open, arm->source_fd, 0);
  if (arm->pidfd_getfd >= 0) {
    arm->stat_result = Raw(SYS_fstat, arm->pidfd_getfd, Ptr(&arm->info));
    arm->statfs_result = Raw(SYS_fstatfs, arm->pidfd_getfd, Ptr(&arm->filesystem));
    Raw(SYS_close, arm->pidfd_getfd);
  }
  Raw(SYS_close, arm->pidfd_open);
done:
  arm->complete.store(1, std::memory_order_release);
  Raw(SYS_exit, 0);
  __builtin_unreachable();
}

bool ReadCaps(__user_cap_data_struct (&caps)[2]) {
  __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
  return Raw(SYS_capget, Ptr(&header), Ptr(caps)) == 0;
}
bool ExpectedCaps(const __user_cap_data_struct (&caps)[2]) {
  return caps[0].effective == kCapabilityMask && caps[0].permitted == kCapabilityMask &&
         caps[0].inheritable == kCapabilityMask && caps[1].effective == 0 &&
         caps[1].permitted == 0 && caps[1].inheritable == 0;
}
bool InitialUserNamespace() {
  const long pidfd=Raw(SYS_pidfd_open,Raw(SYS_gettid),O_EXCL);
  if (pidfd<0) return false;
  const long ns=Raw(SYS_ioctl,pidfd,_IO(0xff,9),0);
  Raw(SYS_close,pidfd);
  if (ns<0) return false;
  struct stat info{};struct statfs filesystem{};
  const bool ok=Raw(SYS_fstat,ns,Ptr(&info))==0 && Raw(SYS_fstatfs,ns,Ptr(&filesystem))==0 &&
      Raw(SYS_ioctl,ns,0xb703,0)==CLONE_NEWUSER && info.st_dev==5 &&
      info.st_ino==4026531837ULL && filesystem.f_type==0x6e736673;
  Raw(SYS_close,ns);return ok;
}
long long NowNs() {
  timespec value{};
  if (clock_gettime(CLOCK_MONOTONIC, &value) < 0) return -1;
  return static_cast<long long>(value.tv_sec)*1000000000LL + value.tv_nsec;
}
bool WaitThread(Arm* arm) {
  const long long start = NowNs();
  if (start < 0) return false;
  const timespec short_wait{0, 10000000};
  while (arm->clear_tid.load(std::memory_order_acquire) != 0) {
    const long long now = NowNs();
    if (now < 0 || now-start >= 2000000000LL) return false;
    const int tid = arm->clear_tid.load(std::memory_order_acquire);
    if (tid) Raw(SYS_futex, Ptr(&arm->clear_tid), FUTEX_WAIT, tid, Ptr(&short_wait));
  }
  return arm->complete.load(std::memory_order_acquire) == 1;
}
bool RunArm(Arm* arm, int fd, void* stack_top, bool separate_process) {
  arm->caller_tid = static_cast<int>(Raw(SYS_gettid));
  arm->source_fd = fd;
  arm->separate_process = separate_process;
  __user_cap_data_struct before[2]{}, after[2]{};
  struct stat expected{};
  struct statfs expected_fs{};
  if (!ReadCaps(before) || !ExpectedCaps(before) ||
      Raw(SYS_fstat, fd, Ptr(&expected)) < 0 || Raw(SYS_fstatfs, fd, Ptr(&expected_fs)) < 0) return false;
  std::memcpy(arm->caller_caps, before, sizeof(before));
  const unsigned long flags = CLONE_VM | CLONE_SIGHAND | CLONE_SYSVSEM |
      CLONE_PARENT_SETTID | CLONE_CHILD_CLEARTID | (separate_process ? SIGCHLD : CLONE_THREAD);
  const long child = owned_zero_cap_clone(flags, stack_top, &arm->clear_tid, ZeroCapWorker, arm);
  if (child < 0) { arm->clone_errno = static_cast<int>(-child); return false; }
  arm->joined = WaitThread(arm);
  if (!arm->joined) _exit(124); // Own case exits; outer root controller must not report PASS.
  if (separate_process) {
    pid_t result;
    do { result = waitpid(static_cast<pid_t>(child), &arm->wait_status, 0); } while (result < 0 && errno == EINTR);
    if (result != child || !WIFEXITED(arm->wait_status) || WEXITSTATUS(arm->wait_status) != 0) return false;
  }
  arm->caller_caps_unchanged = ReadCaps(after) && ExpectedCaps(after) &&
                              std::memcmp(before, after, sizeof(before)) == 0;
  struct stat still_open{};
  arm->source_survived = Raw(SYS_fstat, fd, Ptr(&still_open)) == 0 &&
                         still_open.st_dev == expected.st_dev && still_open.st_ino == expected.st_ino;
  arm->stat_equal = std::memcmp(&arm->info, &expected, sizeof(expected)) == 0;
  arm->statfs_equal = std::memcmp(&arm->filesystem, &expected_fs, sizeof(expected_fs)) == 0;
  bool zero = true;
  for (const auto& cap : arm->caps) zero = zero && !cap.effective && !cap.permitted && !cap.inheritable;
  const bool common = arm->clear_caps == 0 && arm->read_caps == 0 && zero && arm->close_table == 0 &&
      arm->pidfd_open >= 0 && arm->joined && arm->caller_caps_unchanged && arm->source_survived;
  arm->passed = common && (separate_process ?
      (arm->observed_pid != arm->caller_tid && arm->parent_death == 0 && arm->pidfd_getfd == -EPERM) :
      (arm->observed_pid == arm->caller_tid && arm->observed_tid != arm->caller_tid &&
       arm->pidfd_getfd >= 0 && arm->stat_result == 0 && arm->statfs_result == 0 &&
       arm->stat_equal && arm->statfs_equal));
  return arm->passed;
}
void Child(Report* report) {
  report->caller_pid = getpid();
  auto setup = [&](int step, bool ok) {
    if (!ok) { report->setup_step=step; report->setup_errno=errno ? errno : EPROTO; _exit(1); }
  };
  const pid_t parent = getppid();
  setup(1, prctl(PR_SET_PDEATHSIG, SIGKILL) == 0 && getppid() == parent);
  setup(2, sysconf(_SC_PAGESIZE) == 4096);
  void* stack = mmap(nullptr,kStackSize+4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  setup(2, stack != MAP_FAILED && mprotect(static_cast<char*>(stack)+4096,kStackSize,PROT_READ|PROT_WRITE) == 0);
  setup(3, setgroups(0,nullptr) == 0 && setresgid(kUid,kUid,kUid) == 0 &&
           prctl(PR_SET_KEEPCAPS,1) == 0 && setresuid(kUid,kUid,kUid) == 0);
  __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
  __user_cap_data_struct caps[2]{{kCapabilityMask,kCapabilityMask,kCapabilityMask},{0,0,0}};
  setup(4, Raw(SYS_capset,Ptr(&header),Ptr(caps)) == 0 && ReadCaps(caps) && ExpectedCaps(caps));
  // setresuid clears PDEATHSIG. Re-establish it after the credential change.
  setup(5, prctl(PR_SET_PDEATHSIG,SIGKILL) == 0 && getppid() == parent &&
           getuid() == kUid && geteuid() == kUid && getgid() == kUid && getegid() == kUid);
  const long fd = Raw(SYS_memfd_create, Ptr("owned-zero-cap-pin"), 1);
  setup(6, fd >= 0);
  uint64_t old=0, blocked=~uint64_t{0}, after=0;
  setup(7, Raw(SYS_rt_sigprocmask,SIG_SETMASK,Ptr(&blocked),Ptr(&old),8) == 0);
  void* top = static_cast<char*>(stack)+4096+kStackSize;
  const bool a = RunArm(&report->same,static_cast<int>(fd),top,false);
  const bool b = RunArm(&report->different,static_cast<int>(fd),top,true);
  const bool restored = Raw(SYS_rt_sigprocmask,SIG_SETMASK,Ptr(&old),0,8) == 0 &&
                        Raw(SYS_rt_sigprocmask,SIG_SETMASK,0,Ptr(&after),8) == 0 && old == after;
  report->mask_restored=restored;
  Raw(SYS_close,fd); munmap(stack,kStackSize+4096);
  report->passed=a && b && restored;
  _exit(report->passed ? 0 : 1);
}
void PrintArm(const char* name, const Arm& a) {
  std::printf("{\"name\":\"%s\",\"passed\":%s,\"caller_tid\":%d,\"worker_pid\":%d,\"worker_tid\":%d,"
              "\"clear_caps\":%ld,\"capget\":%ld,\"close_table\":%ld,\"pidfd_open\":%ld,\"pidfd_getfd\":%ld,"
              "\"fstat\":%ld,\"fstatfs\":%ld,\"stat_equal\":%s,\"statfs_equal\":%s,\"joined\":%s,"
              "\"wait_status\":%d,\"caller_caps_unchanged\":%s,\"source_survived\":%s,\"clone_errno\":%d,"
              "\"caller_cap_words\":[[%u,%u,%u],[%u,%u,%u]],\"worker_cap_words\":[[%u,%u,%u],[%u,%u,%u]]}",
              name,a.passed?"true":"false",a.caller_tid,a.observed_pid,a.observed_tid,a.clear_caps,a.read_caps,
              a.close_table,a.pidfd_open,a.pidfd_getfd,a.stat_result,a.statfs_result,
              a.stat_equal?"true":"false",a.statfs_equal?"true":"false",a.joined?"true":"false",a.wait_status,
              a.caller_caps_unchanged?"true":"false",a.source_survived?"true":"false",a.clone_errno,
              a.caller_caps[0].effective,a.caller_caps[0].permitted,a.caller_caps[0].inheritable,
              a.caller_caps[1].effective,a.caller_caps[1].permitted,a.caller_caps[1].inheritable,
              a.caps[0].effective,a.caps[0].permitted,a.caps[0].inheritable,
              a.caps[1].effective,a.caps[1].permitted,a.caps[1].inheritable);
}
} // namespace

int main(int argc, char** argv) {
  if (argc == 1) {
    std::puts("{\"state\":\"PLAN_ONLY\",\"fixed_uid\":61171,\"cap_mask\":448,\"owned_arms\":2,\"Main_actions\":0}");
    return 0;
  }
  if (argc != 2 || std::strcmp(argv[1],"--execute-owned") || getuid()!=0 || geteuid()!=0 || getgid()!=0 || getegid()!=0) return 2;
  struct sigaction child_action{};
  if (sigaction(SIGCHLD,nullptr,&child_action)<0 || child_action.sa_handler!=SIG_DFL ||
      (child_action.sa_flags&SA_NOCLDWAIT)) return 2;
  __user_cap_data_struct root_before[2]{},root_after[2]{};
  if (!ReadCaps(root_before) || !InitialUserNamespace() || prctl(PR_SET_CHILD_SUBREAPER,1)<0) return 2;
  void* memory=mmap(nullptr,sizeof(Report),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
  if (memory==MAP_FAILED) return 2;
  auto* report = new(memory) Report;
  const pid_t child=fork();
  if (child<0) { munmap(memory,sizeof(Report)); return 2; }
  if (child==0) Child(report);
  const long long started=NowNs();
  int status=-1;bool timed_out=false;pid_t waited=0;
  for (;;) {
    waited=waitpid(child,&status,WNOHANG);
    if (waited==child) break;
    if (waited<0 && errno!=EINTR) break;
    const long long now=NowNs();
    if (started<0 || now<0 || now-started>=8000000000LL) {
      timed_out=true;
      // A live, unreaped direct child cannot have its numeric PID reused.
      if (kill(child,SIGKILL)<0 && errno!=ESRCH) break;
      do { waited=waitpid(child,&status,0); } while (waited<0 && errno==EINTR);
      break;
    }
    timespec pause{0,10000000};nanosleep(&pause,nullptr);
  }
  // This standalone process has one direct child and only the explicitly
  // created raw descendants above. Subreaper ownership is local to this probe.
  // Reap adopted failures, but never turn their existence into a PASS.
  unsigned adopted_reaped=0;bool descendants_absent=false;
  const long long cleanup_start=NowNs();
  for (;;) {
    int adopted_status=-1;
    const pid_t adopted=waitpid(-1,&adopted_status,WNOHANG);
    if (adopted>0) {++adopted_reaped;continue;}
    if (adopted<0 && errno==ECHILD) {descendants_absent=true;break;}
    if (adopted<0 && errno!=EINTR) break;
    const long long now=NowNs();
    if (cleanup_start<0 || now<0 || now-cleanup_start>=1000000000LL) break;
    timespec pause{0,10000000};nanosleep(&pause,nullptr);
  }
  const bool root_same=ReadCaps(root_after) && std::memcmp(root_before,root_after,sizeof(root_before))==0 &&
      getuid()==0 && geteuid()==0 && getgid()==0 && getegid()==0;
  const bool pass=waited==child && !timed_out && WIFEXITED(status) && WEXITSTATUS(status)==0 &&
      report->passed && root_same && descendants_absent && adopted_reaped==0;
  std::printf("{\"state\":\"%s\",\"setup_step\":%d,\"setup_errno\":%d,\"direct_child_reaped\":%s,"
              "\"direct_wait_status\":%d,\"timed_out\":%s,\"root_credentials_unchanged\":%s,\"mask_restored\":%s,\"arms\":[",
              pass?"MECHANISM_PASS":"MECHANISM_FAILED",report->setup_step,report->setup_errno,
              waited==child?"true":"false",status,timed_out?"true":"false",root_same?"true":"false",report->mask_restored?"true":"false");
  PrintArm("same_tgid_zero_cap_worker",report->same);std::putchar(',');
  PrintArm("different_tgid_must_reject",report->different);
  std::printf("],\"adopted_reaped\":%u,\"descendants_absent\":%s,\"production_ready\":false,\"Main_actions\":0}\n",
              adopted_reaped,descendants_absent?"true":"false");
  report->~Report();munmap(memory,sizeof(Report));
  return pass?0:1;
}
