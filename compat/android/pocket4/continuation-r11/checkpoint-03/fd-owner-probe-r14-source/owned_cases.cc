// Frozen r2 sources plus r3 syscall-word and r4 statfs field-portability corrections.
// There is NO process_vm test seam in this APK.
// Scheduling/count hooks always invoke the actual libc operation.
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cinttypes>
#include <initializer_list>
#include <fcntl.h>
#include <limits.h>
#include <linux/memfd.h>
#include <linux/magic.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>
extern "C" int __wrap_pthread_create(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);
extern "C" int __wrap_fstat(int,struct stat*);
extern "C" int __real_pthread_create(pthread_t* t,const pthread_attr_t* a,void*(*f)(void*),void* p){return pthread_create(t,a,f,p);}
extern "C" int __real_fstat(int fd,struct stat* out){return fstat(fd,out);}
#define pthread_create __wrap_pthread_create
#include "actual/kernel_api/proc_maps_fd_owner.cc"
#undef pthread_create
#define fstat __wrap_fstat
#include "actual/kernel_api/proc_maps_path.cc"
#include "actual/kernel_api/proc_maps_provenance.cc"
#undef fstat
// Only private helper identifiers collide in an amalgamated translation unit;
// the actual source files remain byte-for-byte pinned to the r4 portability source copy.
#define Fd OpenFixturePrivateFd
#define Error OpenFixturePrivateError
#define SameInode OpenFixtureSameInode
#include "actual/kernel_api/proc_maps_open.cc"
#undef SameInode
#undef Error
#undef Fd
struct ActualReceipt {
  volatile unsigned count;
  volatile uint64_t pass_mask;
  char first_failure[96];
  volatile unsigned children_started, children_reaped;
  volatile int last_child_signal, last_child_exit;
};
static ActualReceipt* actual_receipt;
static bool active_open_suite;
static void CountOpenOwner();
#if defined(__ANDROID__)
#define P4_OWNED_PATH_TEMPLATE "/data/user/0/local.pocket4.fdownerprobe.r11/files/p4-path-owner-XXXXXX"
#else
#define P4_OWNED_PATH_TEMPLATE "/tmp/p4-path-owner-XXXXXX"
#endif
static void RecordOwnedCase(const char* name,bool pass) {
  const unsigned position=actual_receipt->count;
  if(position>=63)_exit(121);
  if(pass)actual_receipt->pass_mask=actual_receipt->pass_mask|(UINT64_C(1)<<position);
  else if(actual_receipt->first_failure[0]==0)
    snprintf(actual_receipt->first_failure,sizeof(actual_receipt->first_failure),"%s",name);
  actual_receipt->count=position+1;
}
static int OwnedRawClose(int fd){return static_cast<int>(syscall(SYS_close,fd));}
static int OwnedRawDup3(int oldfd,int newfd,int flags){return static_cast<int>(syscall(SYS_dup3,oldfd,newfd,flags));}
static void OwnedChildSetup(pid_t expected_parent) {
  if(getpid()==expected_parent || getppid()!=expected_parent)_exit(122);
  if(prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=expected_parent)_exit(123);
  // This is a normal-fork child's independent table; the controller retains
  // its references. No Java/framework code runs in this disposable child.
  if(syscall(SYS_close_range,0u,UINT_MAX,0u)<0)_exit(124);
  for(int n=0;n<3;++n)if(open("/dev/null",O_RDWR|O_CLOEXEC)!=n)_exit(125);
}

#define close OwnedRawClose
#define dup3 OwnedRawDup3

namespace path_cases {
namespace p=berberis::proc_maps_provenance;
static std::atomic<unsigned> created{};
static std::atomic<int> race_stage{};
static pid_t race_caller_tid;
static int race_number=-1,race_replacement=-1,race_error;
static struct stat race_identity{};
extern "C" int __real_fstat(int,struct stat*);
extern "C" int __wrap_fstat(int fd,struct stat* value) {
  int result=__real_fstat(fd,value);int saved=errno;
  if(result==0 && race_stage.load()==1 && syscall(SYS_gettid)!=race_caller_tid &&
     value->st_dev==race_identity.st_dev && value->st_ino==race_identity.st_ino) {
    race_number=fd;race_stage.store(2,std::memory_order_release);
    while(race_stage.load(std::memory_order_acquire)==2)sched_yield();
  }
  errno=saved;return result;
}
extern "C" int __real_pthread_create(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);
extern "C" int __wrap_pthread_create(pthread_t* t,const pthread_attr_t* a,void*(*f)(void*),void* v) {
  created.fetch_add(1);::CountOpenOwner();return __real_pthread_create(t,a,f,v);
}
static int failures;
static void Record(const char* name,bool pass) {
  ::RecordOwnedCase(name,pass);
  if(!pass)++failures;
}
static ssize_t Candidate(int dir,const char* path,char* out,size_t length) {
  ssize_t result=-2;
  if(!p::Readlinkat(dir,path,out,length,p::kCandidateConfiguration,&result))
    result=readlinkat(dir,path,out,length);
  return result;
}
static void Compare(const char* name,int dir,const char* path,size_t length=128) {
  char expected[256],actual[256];memset(expected,0x6a,sizeof(expected));memset(actual,0x6a,sizeof(actual));
  errno=EDOM;ssize_t a=syscall(SYS_readlinkat,static_cast<long>(dir),path,expected,static_cast<unsigned long>(length));int ae=errno;
  errno=EDOM;ssize_t b=Candidate(dir,path,actual,length);int be=errno;
  bool pass=a==b && (a<0?ae==be:memcmp(expected,actual,sizeof(actual))==0 && be==EDOM);
  if(!pass)(void)0;
  Record(name,pass);
}
static int FakeSnapshotName() {
  int fd=syscall(SYS_memfd_create,"droidloom-proc-maps-v1",MFD_CLOEXEC);
  if(fd<0 || write(fd,"owned",5)!=5 || fchmod(fd,0444)<0) _exit(80);
  return fd;
}
static void Basic() {
  Compare("ordinary_proc_self",AT_FDCWD,"/proc/self");
  Compare("ordinary_proc_self_truncate",AT_FDCWD,"/proc/self",1);
  Compare("zero_size",AT_FDCWD,"/proc/self",0);
  Compare("negative_kernel_size",AT_FDCWD,"/proc/self",static_cast<size_t>(-1));
  int ordinary=open("/dev/null",O_RDONLY|O_CLOEXEC);if(ordinary<0)_exit(81);
  char ordinary_path[96];snprintf(ordinary_path,sizeof(ordinary_path),"/proc/thread-self/fd/%d",ordinary);
  Compare("ordinary_procfd",AT_FDCWD,ordinary_path);
  char alias[256];snprintf(alias,sizeof(alias),"/proc/self");
  ssize_t copied=Candidate(AT_FDCWD,alias,alias,sizeof(alias));
  char original[256];ssize_t native=readlink("/proc/self",original,sizeof(original));
  Record("input_output_alias",copied==native && native>0 && memcmp(alias,original,native)==0);
  int fake=FakeSnapshotName();char target[96];snprintf(target,sizeof(target),"/proc/thread-self/fd/%d",fake);
  Compare("name_is_not_provenance",AT_FDCWD,target);
  Compare("name_is_not_provenance_truncate",AT_FDCWD,target,1);
  int link=open(target,O_PATH|O_NOFOLLOW|O_CLOEXEC);if(link<0)_exit(82);
  Compare("empty_path_procfd",link,"");
  int directory=open("/proc/thread-self/fd",O_PATH|O_DIRECTORY|O_CLOEXEC);if(directory<0)_exit(83);
  char number[32];snprintf(number,sizeof(number),"%d",fake);
  Compare("relative_caller_dirfd",directory,number);
  Compare("empty_path_not_symlink",fake,"");
  void* mapped=mmap(nullptr,4096,PROT_READ,MAP_PRIVATE,fake,0);
  if(mapped==MAP_FAILED)_exit(100);
  char mapped_path[160];snprintf(mapped_path,sizeof(mapped_path),"/proc/self/map_files/%lx-%lx",
      reinterpret_cast<unsigned long>(mapped),reinterpret_cast<unsigned long>(mapped)+4096);
  Compare("ordinary_map_files_same_display_name",AT_FDCWD,mapped_path);
  munmap(mapped,4096);
  char temporary[]=P4_OWNED_PATH_TEMPLATE;if(!mkdtemp(temporary))_exit(84);
  char first[256],second[256],via[320];
  snprintf(first,sizeof(first),"%s/thread",temporary);snprintf(second,sizeof(second),"%s/alias",temporary);
  if(symlink("/proc/thread-self/fd",first)<0 || symlink("thread",second)<0)_exit(85);
  snprintf(via,sizeof(via),"%s/%d",second,fake);
  Compare("relative_symlink_alias_thread_self",AT_FDCWD,via);
  unlink(second);unlink(first);rmdir(temporary);
  close(directory);close(link);close(fake);close(ordinary);
}
static void Exhaust() {
  int source=open("/dev/null",O_RDONLY|O_CLOEXEC);if(source<0)_exit(86);
  rlimit limit{64,64};if(setrlimit(RLIMIT_NOFILE,&limit)<0)_exit(87);
  int last=-1,next;while((next=fcntl(source,F_DUPFD_CLOEXEC,0))>=0)last=next;
  unsigned before=created.load();
  Compare("ordinary_full_fd_table",AT_FDCWD,"/proc/self");
  Record("ordinary_full_table_no_owner",created.load()==before);
  if(last<0)_exit(88);
  close(last);
  before=created.load();Compare("ordinary_one_free_fd_slot",AT_FDCWD,"/proc/self");
  Record("ordinary_one_slot_no_owner",created.load()==before);
}
struct PublicationState {int prepared_number=-1;int replacement=-1;int result=-1;bool prepared_content=false;bool closed_number=false;};
static int Prepare(int,void* context) {
  auto* s=static_cast<PublicationState*>(context);
  int fd=syscall(SYS_memfd_create,"owned-publication",MFD_CLOEXEC);
  if(fd<0 || write(fd,"private-owner",13)!=13 || lseek(fd,0,SEEK_SET)!=0)return -1;
  s->prepared_number=fd;return fd;
}
static int Publish(const char* path,void* context) {
  auto* s=static_cast<PublicationState*>(context);
  // Reuse the same NUMBER in the caller's table before opening the prepared
  // file. The private owner's later cleanup must not touch this replacement.
  if(syscall(SYS_close_range,static_cast<unsigned>(s->prepared_number),
             static_cast<unsigned>(s->prepared_number),0)<0)return -1;
  if(dup3(s->replacement,s->prepared_number,O_CLOEXEC)<0)return -1;
  s->closed_number=true;
  return open(path,O_RDONLY|O_CLOEXEC);
}
static void Publication() {
  PublicationState state;
  state.replacement=fcntl(STDOUT_FILENO,F_DUPFD_CLOEXEC,32);
  if(state.replacement<0)_exit(89);
  struct stat replacement{};if(fstat(state.replacement,&replacement)<0)_exit(90);
  int result=p::fd_owner::WithPreparedFile(Prepare,Publish,&state);
  char data[32]{};ssize_t bytes=result>=0?read(result,data,sizeof(data)):-1;
  struct stat after{};
  bool survives=fstat(state.prepared_number,&after)==0 && after.st_dev==replacement.st_dev && after.st_ino==replacement.st_ino;
  Record("publication_private_slot_reuse",result>=0 && bytes==13 && memcmp(data,"private-owner",13)==0 && state.closed_number && survives);
  Record("publication_cloexec",result>=0 && fcntl(result,F_GETFD)==FD_CLOEXEC);
  if(result>=0)close(result);
}
struct Unshared {int target;bool pass;};
static void* UnsharedCaller(void* context) {
  auto* s=static_cast<Unshared*>(context);
  if(syscall(SYS_unshare,CLONE_FILES)<0)return nullptr;
  int fake=FakeSnapshotName();if(dup3(fake,s->target,O_CLOEXEC)<0)return nullptr;
  char path[96],actual[128],native[128];snprintf(path,sizeof(path),"/proc/thread-self/fd/%d",s->target);
  ssize_t a=readlink(path,native,sizeof(native)),b=Candidate(AT_FDCWD,path,actual,sizeof(actual));
  s->pass=a>0 && b==a && memcmp(actual,native,a)==0;
  return nullptr;
}
static void ThreadTable() {
  int fd=open("/dev/null",O_RDONLY|O_CLOEXEC);if(fd<0)_exit(91);
  Unshared state{fd,false};pthread_t thread;
  if(pthread_create(&thread,nullptr,UnsharedCaller,&state)!=0 || pthread_join(thread,nullptr)!=0)_exit(92);
  struct stat remains{};Record("unshared_caller_thread_self",state.pass && fstat(fd,&remains)==0 && S_ISCHR(remains.st_mode));
}
static void* ReusePrivateNumber(void*) {
  while(race_stage.load(std::memory_order_acquire)==1)sched_yield();
  if(race_stage.load()!=2)return nullptr;
  if(syscall(SYS_close_range,static_cast<unsigned>(race_number),static_cast<unsigned>(race_number),0)<0 ||
     dup3(race_replacement,race_number,O_CLOEXEC)<0)race_error=errno;
  race_stage.store(3,std::memory_order_release);
  return nullptr;
}
static void ReadlinkRace() {
  int initial=FakeSnapshotName();int target=fcntl(initial,F_DUPFD_CLOEXEC,100);close(initial);
  race_replacement=fcntl(STDOUT_FILENO,F_DUPFD_CLOEXEC,64);
  struct stat replacement{};
  if(target<0 || race_replacement<0 || __real_fstat(target,&race_identity)<0 ||
     __real_fstat(race_replacement,&replacement)<0)_exit(97);
  char path[96],expected[128],actual[128];snprintf(path,sizeof(path),"/proc/thread-self/fd/%d",target);
  ssize_t native=readlink(path,expected,sizeof(expected));
  race_caller_tid=syscall(SYS_gettid);race_stage.store(1);
  pthread_t worker;if(pthread_create(&worker,nullptr,ReusePrivateNumber,nullptr)!=0)_exit(98);
  ssize_t result=Candidate(AT_FDCWD,path,actual,sizeof(actual));
  int pending=1;race_stage.compare_exchange_strong(pending,4);
  if(pthread_join(worker,nullptr)!=0)_exit(99);
  struct stat after{},original{};
  bool survived=race_number>=0 && __real_fstat(race_number,&after)==0 &&
    after.st_dev==replacement.st_dev && after.st_ino==replacement.st_ino;
  bool target_survived=__real_fstat(target,&original)==0 && original.st_dev==race_identity.st_dev && original.st_ino==race_identity.st_ino;
  Record("readlink_private_fd_close_reuse",race_stage.load()==3 && race_error==0 && native>0 && result==native &&
    memcmp(expected,actual,native)==0 && survived && target_survived);
}
int RunSuite() {
  void(*cases[])()={Basic,Exhaust,Publication,ThreadTable,ReadlinkRace};
  for(auto run:cases) {
    pid_t expected_parent=getpid();pid_t child=fork();if(child<0)return 93;
    if(child==0){::OwnedChildSetup(expected_parent);run();_exit(failures?1:0);}
    ++actual_receipt->children_started;
    int status=0;bool reaped=false;
    for(unsigned n=0;n<500;++n){pid_t rc=waitpid(child,&status,WNOHANG);if(rc==child){reaped=true;++actual_receipt->children_reaped;break;}if(rc<0 && errno!=EINTR)return 94;usleep(10000);}
    if(!reaped){kill(child,SIGKILL);pid_t reaped_pid;do{reaped_pid=waitpid(child,&status,0);}while(reaped_pid<0 && errno==EINTR);if(reaped_pid==child)++actual_receipt->children_reaped;return 95;}
    actual_receipt->last_child_signal=WIFSIGNALED(status)?WTERMSIG(status):0;
    actual_receipt->last_child_exit=WIFEXITED(status)?WEXITSTATUS(status):-1;
    if(!WIFEXITED(status)||WEXITSTATUS(status)>1)return 96;
    if(WEXITSTATUS(status))++failures;
  }
  return failures?1:0;
}

}

namespace open_cases {
namespace p=berberis::proc_maps_provenance;
static int failures;
static std::atomic<unsigned> owners{};
extern "C" int __real_pthread_create(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);
extern "C" int OpenSuitePthreadCreate(pthread_t* t,const pthread_attr_t* a,void*(*f)(void*),void* v){owners.fetch_add(1);return __real_pthread_create(t,a,f,v);}
static void Record(const char* name,bool pass) {
  ::RecordOwnedCase(name,pass);
  if(!pass)++failures;
}
struct Context {int calls=0;int failure=0;int flags=0;bool source_is_proc=false;};
static int Snapshot(int source,int flags,void* opaque) {
  auto* c=static_cast<Context*>(opaque);++c->calls;c->flags=flags;
  struct statfs fs{};c->source_is_proc=fstatfs(source,&fs)==0 && static_cast<unsigned long>(fs.f_type)==PROC_SUPER_MAGIC;
  if(c->failure){errno=c->failure;return -1;}
  int fd=syscall(SYS_memfd_create,"owned-maps-formatter",MFD_CLOEXEC);
  if(fd<0 || write(fd,"translated-owned",16)!=16 || lseek(fd,0,SEEK_SET)!=0)return -1;
  return fd;
}
static bool Content(int fd){char text[32];return fd>=0 && read(fd,text,sizeof(text))==16 && memcmp(text,"translated-owned",16)==0;}
static void Basic(){
  for(int closexec: {0,O_CLOEXEC}) {
    Context c;int fd=-1;errno=EDOM;
    bool handled=p::TryOpenSelfMaps(AT_FDCWD,"/proc/self/maps",O_RDONLY|closexec,0,Snapshot,&c,&fd);
    Record(closexec?"maps_cloexec":"maps_inheritable",handled && fd>=0 && errno==EDOM && c.calls==1 && c.source_is_proc && Content(fd) && fcntl(fd,F_GETFD)==(closexec?FD_CLOEXEC:0));
    if(fd>=0)close(fd);
  }
  Context c;int fd=-1;
  bool handled=p::TryOpenSelfMaps(AT_FDCWD,"/proc/self/maps",O_PATH|O_CLOEXEC,0,Snapshot,&c,&fd);
  struct statfs fs{};
  Record("maps_opath",handled && fd>=0 && c.calls==0 && fstatfs(fd,&fs)==0 && static_cast<unsigned long>(fs.f_type)==PROC_SUPER_MAGIC && (fcntl(fd,F_GETFL)&O_PATH));
  if(fd>=0)close(fd);
  for(int flags:{O_RDONLY|O_DIRECTORY,O_RDONLY|O_CREAT|O_EXCL}) {
    errno=0;int native=open("/proc/self/maps",flags,0600);int expected=errno;if(native>=0)close(native);
    c={};fd=-1;errno=0;handled=p::TryOpenSelfMaps(AT_FDCWD,"/proc/self/maps",flags,0600,Snapshot,&c,&fd);
    Record((flags&O_EXCL)?"maps_exclusive_native_error":"maps_directory_native_error",native<0 && handled && fd<0 && errno==expected && c.calls==0);
  }
  c={};unsigned before=owners.load();fd=-1;
  Record("ordinary_open_admission_no_helper",!p::TryOpenSelfMaps(AT_FDCWD,"/dev/null",O_RDONLY,0,Snapshot,&c,&fd) && c.calls==0 && owners.load()==before);
}
static void Exhaust(){
  int source=open("/dev/null",O_RDONLY|O_CLOEXEC);if(source<0)_exit(80);
  rlimit limit{64,64};if(setrlimit(RLIMIT_NOFILE,&limit)<0)_exit(81);
  int last=-1,next;while((next=fcntl(source,F_DUPFD_CLOEXEC,0))>=0)last=next;
  if(last<0)_exit(82);
  Context c;int result=-1;errno=0;
  bool handled=p::TryOpenSelfMaps(AT_FDCWD,"/proc/self/maps",O_RDONLY|O_CLOEXEC,0,Snapshot,&c,&result);
  Record("maps_full_table_emfile_no_host_fallback",handled && result==-1 && errno==EMFILE && c.calls==1 && c.source_is_proc);
  close(last);c={};result=-1;
  handled=p::TryOpenSelfMaps(AT_FDCWD,"/proc/self/maps",O_RDONLY|O_CLOEXEC,0,Snapshot,&c,&result);
  Record("maps_one_slot_private_helpers",handled && result==last && Content(result) && c.calls==1 && c.source_is_proc);
  if(result>=0)close(result);
  c={};c.failure=EMFILE;result=-1;errno=0;
  handled=p::TryOpenSelfMaps(AT_FDCWD,"/proc/self/maps",O_RDONLY,0,Snapshot,&c,&result);
  bool failed=handled && result==-1 && errno==EMFILE && c.calls==1;
  int untouched=open("/dev/null",O_RDONLY|O_CLOEXEC);
  Record("factory_emfile_never_falls_back",failed && untouched==last);
  if(untouched>=0)close(untouched);
}
int RunSuite(){
  void(*cases[])()={Basic,Exhaust};
  for(auto f:cases){pid_t expected_parent=getpid();pid_t pid=fork();if(pid<0)return 90;if(pid==0){::OwnedChildSetup(expected_parent);f();_exit(failures?1:0);}++actual_receipt->children_started;int status=0;bool done=false;for(unsigned n=0;n<500;++n){pid_t r=waitpid(pid,&status,WNOHANG);if(r==pid){done=true;++actual_receipt->children_reaped;break;}if(r<0 && errno!=EINTR)return 91;usleep(10000);}if(!done){kill(pid,SIGKILL);pid_t reaped_pid;do{reaped_pid=waitpid(pid,&status,0);}while(reaped_pid<0 && errno==EINTR);if(reaped_pid==pid)++actual_receipt->children_reaped;return 92;}actual_receipt->last_child_signal=WIFSIGNALED(status)?WTERMSIG(status):0;actual_receipt->last_child_exit=WIFEXITED(status)?WEXITSTATUS(status):-1;if(!WIFEXITED(status)||WEXITSTATUS(status)>1)return 93;if(WEXITSTATUS(status))++failures;}
  return failures?1:0;
}

}

#undef dup3
#undef close
static void CountOpenOwner(){if(active_open_suite)open_cases::owners.fetch_add(1); }

static bool actual_children_reaped;
static int RunActualSourceCases(char* json,size_t capacity) {
  actual_receipt=static_cast<ActualReceipt*>(mmap(nullptr,sizeof(ActualReceipt),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(actual_receipt==MAP_FAILED){snprintf(json,capacity,"{\"pass\":false,\"setup_errno\":%d}",errno);return 70;}
#if defined(P4_HOST_COPY_SEAM)
  const char* actual_copy="false";
#else
  const char* actual_copy="true";
#endif
  const int path_rc=path_cases::RunSuite();
  const int path_signal=actual_receipt->last_child_signal;
  const int path_exit=actual_receipt->last_child_exit;
  active_open_suite=true;
  const int open_rc=open_cases::RunSuite();
  active_open_suite=false;
  actual_children_reaped=actual_receipt->children_started>0 && actual_receipt->children_started==actual_receipt->children_reaped;
  constexpr unsigned expected=30;
  const uint64_t mask=(UINT64_C(1)<<expected)-1;
  const bool pass=path_rc==0 && open_rc==0 && actual_children_reaped && actual_receipt->children_started==7 && actual_receipt->count==expected && actual_receipt->pass_mask==mask;
  snprintf(json,capacity,"{\"pass\":%s,\"expected_cases\":%u,\"observed_cases\":%u,\"pass_mask\":\"0x%016" PRIx64 "\",\"first_failure\":\"%s\",\"path_suite_rc\":%d,\"open_suite_rc\":%d,\"path_last_child_signal\":%d,\"path_last_child_exit\":%d,\"normal_owned_children_reaped\":%s,\"actual_copy_api\":%s,\"broker_positive_identity_tested\":false,\"maps_formatter\":\"owned_fixture\",\"candidate_production_ready\":false}",pass?"true":"false",expected,actual_receipt->count,static_cast<uint64_t>(actual_receipt->pass_mask),actual_receipt->first_failure,path_rc,open_rc,path_signal,path_exit,actual_children_reaped?"true":"false",actual_copy);
  munmap(actual_receipt,sizeof(ActualReceipt));actual_receipt=nullptr;
  return pass?0:1;
}
