// SPDX-License-Identifier: Apache-2.0
#include "droidloom_generation.h"
#include "nativebridge/droidloom_generation_protocol.h"
#include <cstdio>
#include <cerrno>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
namespace platform=android::droidloom_generation;
using namespace droidloom::native_generation;
struct Details {int error=0,steps=0,children=0,reaped=0,timeout=0,fd_survived=0,exec_errno=0;};
static Details* detail;
static int Pid(){return static_cast<int>(syscall(SYS_getpid));}
static long long Millis(){timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t)<0)return -1;return t.tv_sec*1000LL+t.tv_nsec/1000000;}
static bool Guard(int parent){return getppid()==parent && prctl(PR_SET_PDEATHSIG,SIGKILL)==0 && getppid()==parent;}
static bool Wait(pid_t child,int ms,int* status) {
 long long began=Millis();if(began<0)return false;
 const timespec delay{0,1000000};
 for(;;) {
  const pid_t done=waitpid(child,status,WNOHANG);
  if(done==child)return true;
  if(done<0&&errno!=EINTR)return false;
  const long long now=Millis();if(now<0||now-began>=ms)break;
  nanosleep(&delay,nullptr);
 }
 const pid_t final_check=waitpid(child,status,WNOHANG);
 if(final_check==child)return true;
 if(final_check!=0)return false;
 detail->timeout=1;
 if(kill(child,SIGKILL)<0&&errno!=ESRCH)return false;
 began=Millis();
 for(;;) {
  const pid_t done=waitpid(child,status,WNOHANG);
  if(done==child)return true;
  if(done<0&&errno!=EINTR)return false;
  if(Millis()-began>1000)return false;
  nanosleep(&delay,nullptr);
 }
}
static bool ForkCycle() {
 const int parent=Pid();
 const pid_t child=static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(SIGCHLD),0UL,0UL,0UL,0UL));
 if(child<0){detail->error=errno;return false;}
 if(child==0) {
  if(!Guard(parent))_exit(81);
  const bool ok=platform::AfterSpecialize()&&platform::RequireReady()&&platform::BeforeUnload();
  if(!ok)detail->error=platform::LastError();
  _exit(ok?0:1);
 }
 ++detail->children;int status=0;const bool done=Wait(child,2000,&status);if(done)++detail->reaped;
 return done&&!detail->timeout&&WIFEXITED(status)&&WEXITSTATUS(status)==0;
}
static bool Run(unsigned n,const char* root) {
 char path[1024];const char* library=n==0?"libold-engine.so":n==1?"libengine-disabled.so":"libengine-enabled.so";
 const int written=snprintf(path,sizeof(path),"%s/%s",root,library);
 if(written<0||static_cast<size_t>(written)>=sizeof(path))return false;
 void* handle=dlopen(path,RTLD_NOW|RTLD_LOCAL);
 if(handle==nullptr){detail->error=ELIBBAD;return false;}
 auto entry=reinterpret_cast<Entry>(dlsym(handle,kEngineSymbol));
 if(n==0 || n==1) {
  const bool ready=platform::Prepare(handle);detail->error=platform::LastError();
  return !ready && detail->error==(n==0?EPROTONOSUPPORT:EOPNOTSUPP);
 }
 if(entry==nullptr)return false;
 if(n==2) {
  const Request q=MakeRequest(kCheckReady,0,Pid(),0);
  detail->error=-entry(&q);return detail->error==EPROTONOSUPPORT;
 }
 if(n==3) {
  const Request good=MakeRequest(kPrepareMemory,0,Pid(),0);
  Request bad=good;++bad.version;if(entry(&bad)!=-EPROTONOSUPPORT)return false;++detail->steps;
  bad=good;--bad.size;if(entry(&bad)!=-EPROTONOSUPPORT)return false;++detail->steps;
  bad=good;bad.protocol1^=1;if(entry(&bad)!=-EPROTONOSUPPORT)return false;++detail->steps;
  bad=good;bad.flags=4;if(entry(&bad)!=-EINVAL)return false;++detail->steps;
  bad=good;bad.operation=kAfterSpecialize;if(entry(&bad)!=-EPROTO)return false;++detail->steps;
  return detail->steps==5;
 }
 const int fd=open("/dev/null",O_RDONLY|O_CLOEXEC);struct stat before{},after{};
 if(fd<0||fstat(fd,&before)<0)return false;
 if(!platform::Prepare(handle)){detail->error=platform::LastError();return false;}
 if(n==6) {
  if(!platform::BeforeFork() || !ForkCycle() || platform::RequireReady())return false;
 } else {
  if(!platform::AfterSpecialize() || !platform::RequireReady()) {
   detail->error=platform::LastError();return false;
  }
  if(n==5) {
   if(!platform::BeforeFork() || platform::RequireReady() || platform::AfterSpecialize())return false;
   detail->error=platform::LastError();if(detail->error!=EPROTO)return false;
  } else if(n==7 || n==8) {
   if(!platform::BeforeFork())return false;
   if(n==8) {const rlimit limit{1,1};if(setrlimit(RLIMIT_AS,&limit)<0)return false;}
   if(!ForkCycle())return false;
   if(n==7 && (!platform::BeforeFork() || !ForkCycle()))return false;
   if(platform::RequireReady())return false;
  } else if(n==9) {
   auto before_exec=reinterpret_cast<int(*)()>(dlsym(handle,"TestBeforeExec"));
   auto after_exec=reinterpret_cast<void(*)()>(dlsym(handle,"TestAfterExecFailure"));
   if(!before_exec||!after_exec || before_exec()!=0 || platform::RequireReady())return false;
   char absent[1024];const int count=snprintf(absent,sizeof(absent),"%s/owned-absent-executable",root);
   if(count<0||static_cast<size_t>(count)>=sizeof(absent))return false;
   char* args[]={absent,nullptr};char* env[]={nullptr};
   if(execve(absent,args,env)!=-1)return false;
   detail->exec_errno=errno;
   after_exec();
   if(errno!=detail->exec_errno || detail->exec_errno!=ENOENT || !platform::RequireReady())return false;
  } else if(n==10) {
   auto before_clone=reinterpret_cast<int(*)(unsigned long)>(dlsym(handle,"TestBeforeClone"));
   auto before_syscall=reinterpret_cast<int(*)(long,unsigned long,unsigned long)>(dlsym(handle,"TestBeforeSyscall"));
   if(!before_clone||!before_syscall)return false;
   errno=0;if(before_clone(CLONE_VM|SIGCHLD)!=-1||errno!=EOPNOTSUPP)return false;++detail->steps;
   errno=0;if(before_clone(CLONE_NEWUSER|SIGCHLD)!=-1||errno!=EOPNOTSUPP)return false;++detail->steps;
   errno=0;if(before_syscall(146,static_cast<unsigned long>(getuid()),0)!=-1||errno!=EOPNOTSUPP)return false;++detail->steps;
   errno=0;if(before_syscall(51,0,0)!=-1||errno!=EOPNOTSUPP)return false;++detail->steps;
   errno=0;if(before_syscall(97,CLONE_NEWUSER,0)!=-1||errno!=EOPNOTSUPP)return false;++detail->steps;
   if(before_syscall(97,CLONE_FILES,0)!=0 || before_syscall(151,UINT32_MAX,0)!=0)return false;
   detail->steps+=2;
  }
 }
 if(!platform::BeforeUnload()){detail->error=platform::LastError();return false;}
 detail->fd_survived=fstat(fd,&after)==0&&before.st_dev==after.st_dev&&before.st_ino==after.st_ino;
 return detail->fd_survived;
}
int main(int argc,char** argv) {
 if(argc!=2)return 80;
 setvbuf(stdout,nullptr,_IONBF,0);
 struct sigaction action{};if(sigaction(SIGCHLD,nullptr,&action)<0||action.sa_handler!=SIG_DFL||(action.sa_flags&SA_NOCLDWAIT))return 81;
 detail=static_cast<Details*>(mmap(nullptr,sizeof(Details),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0));
 if(detail==MAP_FAILED)return 82;
 const char* names[]={"old_engine_missing_private_ABI_refused","disabled_engine_refused","engine_without_post_specialize_grant_refused","ABI_and_order_negative_controls","ordinary_application_generation","prefork_stays_closed_in_parent","private_zygote_child_generation","app_zygote_two_private_children","post_specialize_rawfork_AS_1_inherited_stack","failed_exec_explicit_restart_preserves_errno","unsupported_guest_mutations_rejected_known_limit"};
 bool all=true;
 for(unsigned n=0;n<sizeof(names)/sizeof(names[0]);++n) {
  *detail=Details{};const int parent=Pid();const pid_t child=fork();if(child<0)return 83;
  if(child==0)_exit(Guard(parent)&&Run(n,argv[1])?0:1);
  int status=0;const bool reaped=Wait(child,4500,&status);
  const bool passed=reaped&&!detail->timeout&&WIFEXITED(status)&&WEXITSTATUS(status)==0;
  printf("{\"case\":\"%s\",\"passed\":%s,\"direct_child_reaped\":%s,\"timeout\":%d,\"status\":%d,\"errno\":%d,\"steps\":%d,\"nested_started\":%d,\"nested_reaped\":%d,\"fd_survived\":%d,\"exec_errno\":%d,\"known_compatibility_limit\":%s}\n",names[n],passed?"true":"false",reaped?"true":"false",detail->timeout,status,detail->error,detail->steps,detail->children,detail->reaped,detail->fd_survived,detail->exec_errno,n==10?"true":"false");
  all=all&&passed;if(!reaped||detail->timeout)break;
 }
 return all?0:1;
}
