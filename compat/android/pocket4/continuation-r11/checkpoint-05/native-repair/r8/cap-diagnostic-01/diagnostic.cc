// Owned diagnostic; no policy, credential, namespace or application mutation.
#include "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/engine/kernel_api/proc_maps_raw_metadata_owner.cc"
#include <cstdio>
#include <sys/statfs.h>
#include <sys/wait.h>
#include <sys/prctl.h>
namespace owner=berberis::proc_maps_provenance::raw_metadata_owner;
struct Detail {int context; long pidfd,nsfd,nsstat,nsfs,nstype,procfd,procstat,procfs,proctype; unsigned long long dev,ino,magic,pdev,pino,pmagic; owner::AppContext value;};
static Detail record;
__attribute__((no_stack_protector)) static int Diagnose(void*) {
  record.context=owner::ReadContext(&record.value);
  record.pidfd=owner::Raw(SYS_pidfd_open,owner::Raw(SYS_gettid),O_EXCL);
  record.nsfd=record.pidfd<0?record.pidfd:owner::Raw(SYS_ioctl,record.pidfd,_IO(0xff,9),0);
  record.nsstat=record.nsfs=record.nstype=-999;
  if(record.nsfd>=0) {
    struct stat info;struct statfs fs;
    record.nsstat=owner::Raw(SYS_fstat,record.nsfd,reinterpret_cast<long>(&info));
    record.nsfs=owner::Raw(SYS_fstatfs,record.nsfd,reinterpret_cast<long>(&fs));
    record.nstype=owner::Raw(SYS_ioctl,record.nsfd,NS_GET_NSTYPE,0);
    if(record.nsstat==0){record.dev=info.st_dev;record.ino=info.st_ino;}
    if(record.nsfs==0)record.magic=fs.f_type;
    owner::Raw(SYS_close,record.nsfd);
  }
  if(record.pidfd>=0)owner::Raw(SYS_close,record.pidfd);
  static constexpr char path[]="/proc/thread-self/ns/user";
  record.procfd=owner::Raw(SYS_openat,AT_FDCWD,reinterpret_cast<long>(path),O_RDONLY|O_CLOEXEC,0);
  record.procstat=record.procfs=record.proctype=-999;
  if(record.procfd>=0) {
    struct stat info;struct statfs fs;
    record.procstat=owner::Raw(SYS_fstat,record.procfd,reinterpret_cast<long>(&info));
    record.procfs=owner::Raw(SYS_fstatfs,record.procfd,reinterpret_cast<long>(&fs));
    record.proctype=owner::Raw(SYS_ioctl,record.procfd,NS_GET_NSTYPE,0);
    if(record.procstat==0){record.pdev=info.st_dev;record.pino=info.st_ino;}
    if(record.procfs==0)record.pmagic=fs.f_type;
    owner::Raw(SYS_close,record.procfd);
  }
  return 0;
}
static void Print(const char* role) {
  std::printf("{\"role\":\"%s\",\"context_rc\":%d,\"uid\":[%u,%u,%u],\"gid\":[%u,%u,%u],\"fsuid\":%u,\"fsgid\":%u,\"caps\":[%u,%u,%u,%u,%u,%u],\"group_count\":%u,\"self_pidfd\":%ld,\"pidfd_get_userns\":%ld,\"ns_stat\":%ld,\"ns_statfs\":%ld,\"ns_type\":%ld,\"ns_dev\":%llu,\"ns_ino\":%llu,\"ns_magic\":%llu,\"proc_ns_fd\":%ld,\"proc_stat\":%ld,\"proc_statfs\":%ld,\"proc_type\":%ld,\"proc_dev\":%llu,\"proc_ino\":%llu,\"proc_magic\":%llu}\n",
  role,record.context,record.value.uid[0],record.value.uid[1],record.value.uid[2],record.value.gid[0],record.value.gid[1],record.value.gid[2],record.value.fsuid,record.value.fsgid,record.value.capabilities[0],record.value.capabilities[1],record.value.capabilities[2],record.value.capabilities[3],record.value.capabilities[4],record.value.capabilities[5],record.value.group_count,record.pidfd,record.nsfd,record.nsstat,record.nsfs,record.nstype,record.dev,record.ino,record.magic,record.procfd,record.procstat,record.procfs,record.proctype,record.pdev,record.pino,record.pmagic);
}
int main() {
  setvbuf(stdout,nullptr,_IONBF,0);
  Diagnose(nullptr);Print("caller");
  const uint64_t full=~uint64_t{0};uint64_t old=0;
  if(owner::Raw(SYS_rt_sigprocmask,SIG_SETMASK,reinterpret_cast<long>(&full),reinterpret_cast<long>(&old),8)<0)return 2;
  void* memory=mmap(nullptr,128*1024,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  if(memory==MAP_FAILED)return 3;
  std::atomic<int> tid{0};
  const unsigned long flags=CLONE_VM|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM|CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID;
  const long clone_result=berberis_proc_metadata_raw_clone_x86_64(flags,static_cast<char*>(memory)+128*1024,&tid,Diagnose,nullptr);
  if(clone_result<0)return 4;
  for(;;){int observed=tid.load(std::memory_order_acquire);if(!observed)break;owner::Raw(SYS_futex,reinterpret_cast<long>(&tid),FUTEX_WAIT,observed);}
  owner::Raw(SYS_rt_sigprocmask,SIG_SETMASK,reinterpret_cast<long>(&old),0,8);
  Print("raw_private_fd_worker");munmap(memory,128*1024);return 0;
}
