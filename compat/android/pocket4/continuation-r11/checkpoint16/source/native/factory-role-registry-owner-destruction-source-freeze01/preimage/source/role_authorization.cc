// SPDX-License-Identifier: Apache-2.0
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_authorization.h"
#include "factory_context.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/capability.h>
#include <linux/magic.h>
#include <linux/nsfs.h>
#include <new>
#include <poll.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include <utility>

namespace droidloom::proc_maps_factory::role_v1 {
namespace {
constexpr unsigned char kMagic[8] = {'D','P','4','R','O','L','E','1'};
constexpr uint64_t kMaximumPayload = 8U * 1024U * 1024U;
constexpr int kPassPidfd = 76, kPeerPidfd = 77, kScmPidfd = 4;
constexpr uint64_t kInitialUserDevice = 5, kInitialUserInode = 4026531837ULL;
constexpr uint64_t kRoleCaps = (1ULL << CAP_SETUID) | (1ULL << CAP_SETGID) | (1ULL << CAP_SETPCAP);
#ifdef SO_PASSPIDFD
static_assert(kPassPidfd == SO_PASSPIDFD);
#endif
#ifdef SO_PEERPIDFD
static_assert(kPeerPidfd == SO_PEERPIDFD);
#endif
#ifdef SCM_PIDFD
static_assert(kScmPidfd == SCM_PIDFD);
#endif
// First published 64-byte PIDFD_GET_INFO ABI. Request/require only fields in
// this prefix. Unsupported kernels fail; no path-text or numeric-PID fallback.
struct PidfdInfo {
  uint64_t mask{}, cgroup{};
  uint32_t pid{}, tgid{}, ppid{}, ruid{}, rgid{}, euid{}, egid{}, suid{}, sgid{}, fsuid{}, fsgid{}, spare{};
};
static_assert(sizeof(PidfdInfo) == 64 && offsetof(PidfdInfo, fsuid) == 52);
constexpr unsigned long kGetInfo = _IOWR(0xff, 11, PidfdInfo);
constexpr unsigned long kGetUserNs = _IO(0xff, 9), kGetPidNs = _IO(0xff, 5), kGetMountNs = _IO(0xff, 3);
int Error(int value) { errno = value; return -1; }
bool Nonzero(const unsigned char* p, size_t n) { unsigned v=0; for(size_t i=0;i<n;++i)v|=p[i]; return v!=0; }
bool Equal(const unsigned char* a,const unsigned char* b,size_t n) { unsigned v=0;for(size_t i=0;i<n;++i)v|=a[i]^b[i];return v==0; }
uint32_t U32(const unsigned char* p) { return uint32_t{p[0]} | uint32_t{p[1]}<<8 | uint32_t{p[2]}<<16 | uint32_t{p[3]}<<24; }
uint64_t U64(const unsigned char* p) { return U32(p) | uint64_t{U32(p+4)}<<32; }
void Put32(unsigned char* p,uint32_t v) {for(unsigned i=0;i<4;++i)p[i]=static_cast<unsigned char>(v>>(8*i));}
void Put64(unsigned char* p,uint64_t v) {Put32(p,static_cast<uint32_t>(v));Put32(p+4,static_cast<uint32_t>(v>>32));}
bool Range(uint32_t low,uint32_t high) {return low>0&&low<=high&&high<=INT_MAX;}
bool EmptyAuthorityFields(const Request& r) {return !r.uid_min&&!r.uid_max&&!r.gid_min&&!r.gid_max&&!r.child_pid_in_parent_namespace&&!r.initial_uid&&!r.initial_gid;}
bool EmptyCreateFields(const Request& r) {return !r.caller_tid&&!r.payload_size&&!r.source_flags&&!r.original_fd_flags;}
bool ValidRequest(const Request& r) {
  if(!Nonzero(r.pair,kDigestBytes))return false;
  switch(r.operation) {
    case Operation::kBegin:
      return !Nonzero(r.token,kDigestBytes)&&Range(r.uid_min,r.uid_max)&&Range(r.gid_min,r.gid_max)&&
             !r.child_pid_in_parent_namespace&&!r.initial_uid&&!r.initial_gid&&EmptyCreateFields(r);
    case Operation::kApprove:
      return Nonzero(r.token,kDigestBytes)&&Range(r.uid_min,r.uid_max)&&Range(r.gid_min,r.gid_max)&&
             r.child_pid_in_parent_namespace>0&&r.child_pid_in_parent_namespace<=INT_MAX&&
             r.initial_uid>0&&r.initial_uid<=INT_MAX&&r.initial_gid>0&&r.initial_gid<=INT_MAX&&EmptyCreateFields(r);
    case Operation::kCreate:
      return Nonzero(r.token,kDigestBytes)&&EmptyAuthorityFields(r)&&r.caller_tid>0&&r.caller_tid<=INT_MAX&&
             r.payload_size>0&&r.payload_size<=kMaximumPayload&&!(r.original_fd_flags&~uint32_t{FD_CLOEXEC});
    case Operation::kRelease:
      return Nonzero(r.token,kDigestBytes)&&EmptyAuthorityFields(r)&&EmptyCreateFields(r);
    case Operation::kAttach:
    case Operation::kSuspend:
      return Nonzero(r.token,kDigestBytes)&&EmptyAuthorityFields(r)&&
             r.caller_tid>0&&r.caller_tid<=INT_MAX&&!r.payload_size&&!r.source_flags&&!r.original_fd_flags;
  }
  return false;
}
int Option(int fd,int option,int* result) {
  socklen_t n=sizeof(*result);
  if(getsockopt(fd,SOL_SOCKET,option,result,&n)<0)return -1;
  return n==sizeof(*result)?0:Error(EPROTO);
}
int CheckSocket(int fd,bool listener,bool require_identity) {
  int domain,kind,accepting,cred,pidfd;
  if(Option(fd,SO_DOMAIN,&domain)<0||Option(fd,SO_TYPE,&kind)<0||Option(fd,SO_ACCEPTCONN,&accepting)<0)return -1;
  const int status=fcntl(fd,F_GETFL),flags=fcntl(fd,F_GETFD);
  if(domain!=AF_UNIX||kind!=SOCK_SEQPACKET||accepting!=(listener?1:0)||status<0||flags<0||
     !(status&O_NONBLOCK)||!(flags&FD_CLOEXEC))return Error(EPROTO);
  if(require_identity&&(Option(fd,SO_PASSCRED,&cred)<0||Option(fd,kPassPidfd,&pidfd)<0||cred!=1||pidfd!=1))return Error(EPROTO);
  return 0;
}
int PidfdLiveness(int fd) {
  pollfd p{fd,POLLIN,0};
  if(poll(&p,1,0)<0)return -1;
  if(p.revents&(POLLERR|POLLNVAL))return Error(EIO);
  if(p.revents&POLLIN)return 0;
  return p.revents==0?1:Error(EIO);
}
bool Alive(int fd) {
  const int live=PidfdLiveness(fd);
  if(live==0)Error(EPIPE);
  return live==1;
}
bool ConnectionAlive(int fd) {
  pollfd p{fd,static_cast<short>(POLLRDHUP|POLLIN),0};
  if(poll(&p,1,0)<0)return false;
  if(p.revents&(POLLRDHUP|POLLHUP|POLLERR|POLLNVAL)){Error(EPIPE);return false;}
  return true;
}
uint64_t Now() {
  timespec t{};
  if(clock_gettime(CLOCK_MONOTONIC,&t)<0||t.tv_sec<0||t.tv_nsec<0||t.tv_nsec>=1000000000||
     static_cast<uint64_t>(t.tv_sec)>(UINT64_MAX-999999999)/1000000000)return 0;
  return uint64_t{static_cast<uint64_t>(t.tv_sec)}*1000000000+static_cast<uint64_t>(t.tv_nsec);
}
bool SameInode(const struct stat& a,const struct stat& b){return a.st_dev==b.st_dev&&a.st_ino==b.st_ino;}
int Namespace(int fd,int type,struct stat* result) {
  struct statfs fs{};
  if(fstat(fd,result)<0||fstatfs(fd,&fs)<0)return -1;
  const int actual=ioctl(fd,NS_GET_NSTYPE,0UL);
  if(actual<0)return -1;
  return actual==type&&static_cast<uint64_t>(fs.f_type)==NSFS_MAGIC?0:Error(EXDEV);
}
int InitialUser(int fd) {
  struct stat s{};if(Namespace(fd,CLONE_NEWUSER,&s)<0)return -1;
  return static_cast<uint64_t>(s.st_dev)==kInitialUserDevice&&static_cast<uint64_t>(s.st_ino)==kInitialUserInode?0:Error(EXDEV);
}
int VerifyProc(int proc,const struct stat& pidns) {
  struct statfs fs{};if(fstatfs(proc,&fs)<0)return -1;
  if(static_cast<uint64_t>(fs.f_type)!=PROC_SUPER_MAGIC)return Error(EXDEV);
  Descriptor fd(openat(proc,"1/ns/pid",O_RDONLY|O_CLOEXEC));struct stat s{};
  if(fd.get()<0||Namespace(fd.get(),CLONE_NEWPID,&s)<0)return -1;
  return SameInode(s,pidns)?0:Error(EXDEV);
}
int GetInfo(int pidfd,PidfdInfo* result) {
  PidfdInfo info{};info.mask=3;
  const int flags=fcntl(pidfd,F_GETFD);
  if(flags<0||!(flags&FD_CLOEXEC)||!Alive(pidfd))return Error(EPIPE);
  if(ioctl(pidfd,kGetInfo,&info)<0)return -1;
  if((info.mask&3)!=3||!info.pid||info.pid>INT_MAX||info.pid!=info.tgid||info.ppid>INT_MAX)return Error(EPROTO);
  if(!Alive(pidfd))return -1;
  *result=info;return 0;
}
bool SameInfo(const PidfdInfo& a,const PidfdInfo& b) {
  return a.pid==b.pid&&a.tgid==b.tgid&&a.ppid==b.ppid&&a.ruid==b.ruid&&a.rgid==b.rgid&&
         a.euid==b.euid&&a.egid==b.egid&&a.suid==b.suid&&a.sgid==b.sgid&&a.fsuid==b.fsuid&&a.fsgid==b.fsgid;
}
int Path(char* p,size_t n,uint32_t pid,const char* leaf) {
  const int amount=snprintf(p,n,"%u/%s",pid,leaf);return amount>0&&static_cast<size_t>(amount)<n?0:Error(EOVERFLOW);
}
ssize_t ReadAt(int base,const char* path,char* output,size_t cap) {
  Descriptor fd(openat(base,path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW));if(fd.get()<0)return -1;
  size_t used=0;
  while(used<cap){const ssize_t n=read(fd.get(),output+used,cap-used);if(n<0){if(errno==EINTR)continue;return -1;}if(!n)return static_cast<ssize_t>(used);used+=static_cast<size_t>(n);}
  return Error(EOVERFLOW);
}
struct Status {ProcessStatus base{};uint64_t bounding{};uint32_t pid{},ppid{},threads{},nnp{},seccomp{};};
bool ParseExtended(const char* text,size_t n,Status* result) {
  Status s{};if(!ParseStatus(text,n,&s.base))return false;
  unsigned seen=0;size_t at=0;
  while(at<n){size_t end=at;while(end<n&&text[end]!='\n')++end;const char* line=text+at;const size_t size=end-at;at=end+1;
    const char* colon=static_cast<const char*>(memchr(line,':',size));if(!colon)continue;
    const size_t key=static_cast<size_t>(colon-line);const char* value=colon+1;size_t len=size-key-1;
    while(len&&(*value==' '||*value=='\t')){++value;--len;}while(len&&(value[len-1]==' '||value[len-1]=='\t'))--len;
    unsigned bit=0;uint32_t* field=nullptr;
#define ROLE_FIELD(name) (key==sizeof(name)-1&&!memcmp(line,name,sizeof(name)-1))
    if(ROLE_FIELD("Pid")){bit=1;field=&s.pid;}
    else if(ROLE_FIELD("PPid")){bit=2;field=&s.ppid;}
    else if(ROLE_FIELD("Threads")){bit=4;field=&s.threads;}
    else if(ROLE_FIELD("NoNewPrivs")){bit=8;field=&s.nnp;}
    else if(ROLE_FIELD("Seccomp")){bit=16;field=&s.seccomp;}
    else if(ROLE_FIELD("CapBnd")){bit=32;uint64_t v=0;if(!len||len>16)return false;for(size_t i=0;i<len;++i){unsigned d;if(value[i]>='0'&&value[i]<='9')d=value[i]-'0';else if(value[i]>='a'&&value[i]<='f')d=value[i]-'a'+10;else if(value[i]>='A'&&value[i]<='F')d=value[i]-'A'+10;else return false;v=v*16+d;}s.bounding=v;}
#undef ROLE_FIELD
    if(bit&&(seen&bit))return false;
    if(field){uint64_t v;if(!ParseDecimal(value,len,UINT32_MAX,&v))return false;*field=static_cast<uint32_t>(v);}seen|=bit;
  }
  if(seen!=63||s.pid!=s.base.namespace_pids[0]||s.pid>INT_MAX||s.ppid>INT_MAX||!s.threads||s.nnp>1||s.seccomp>2)return false;
  *result=s;return true;
}
int ReadStatusAt(int proc,const char* path,Status* result) {
  char bytes[16384];const ssize_t n=ReadAt(proc,path,bytes,sizeof(bytes));if(n<0)return -1;
  return ParseExtended(bytes,static_cast<size_t>(n),result)?0:Error(EBADMSG);
}
bool IdsMatch(const Status& s,const PidfdInfo& p) {
  const uint32_t uid[]={p.ruid,p.euid,p.suid,p.fsuid},gid[]={p.rgid,p.egid,p.sgid,p.fsgid};
  return s.pid==p.pid&&s.base.tgid==p.tgid&&s.ppid==p.ppid&&!memcmp(uid,s.base.uid,sizeof(uid))&&!memcmp(gid,s.base.gid,sizeof(gid));
}
bool SameCredentials(const Status& a,const Status& b) {
  return !memcmp(a.base.uid,b.base.uid,sizeof(a.base.uid))&&!memcmp(a.base.gid,b.base.gid,sizeof(a.base.gid))&&
         a.base.inheritable==b.base.inheritable&&a.base.permitted==b.base.permitted&&a.base.effective==b.base.effective&&
         a.base.ambient==b.base.ambient&&a.bounding==b.bounding&&a.nnp==b.nnp&&a.seccomp==b.seccomp;
}
bool RoleProfile(const Status& s) {
  if(!s.base.uid[0]||!s.base.gid[0]||s.base.inheritable!=kRoleCaps||s.base.permitted!=kRoleCaps||
     s.base.effective!=kRoleCaps||s.base.ambient||s.bounding||s.nnp!=1||s.seccomp!=2)return false;
  for(unsigned i=1;i<4;++i)if(s.base.uid[i]!=s.base.uid[0]||s.base.gid[i]!=s.base.gid[0])return false;
  return true;
}
bool RootProfile(const Status& s) {for(unsigned i=0;i<4;++i)if(s.base.uid[i]||s.base.gid[i])return false;return true;}
struct Snapshot {
  Descriptor userns,pidns,mountns,root,proc;
  struct stat pidns_identity{},mountns_identity{},root_identity{};
  PidfdInfo info{};Status status{};uint32_t visible_pid{};uint64_t start_ticks{};
};
int Capture(int host_proc,int pidfd,Snapshot* output) {
  Snapshot value;
  if(GetInfo(pidfd,&value.info)<0)return -1;
  value.userns.reset(ioctl(pidfd,kGetUserNs,0UL));value.pidns.reset(ioctl(pidfd,kGetPidNs,0UL));value.mountns.reset(ioctl(pidfd,kGetMountNs,0UL));
  if(value.userns.get()<0||value.pidns.get()<0||value.mountns.get()<0||InitialUser(value.userns.get())<0||
     Namespace(value.pidns.get(),CLONE_NEWPID,&value.pidns_identity)<0||Namespace(value.mountns.get(),CLONE_NEWNS,&value.mountns_identity)<0)return -1;
  char path[80];
  if(Path(path,sizeof(path),value.info.pid,"status")<0||ReadStatusAt(host_proc,path,&value.status)<0)return -1;
  if(!IdsMatch(value.status,value.info))return Error(ESTALE);
  const auto& status=value.status.base;
  for(size_t i=0;i<status.tgid_depth;++i)if(status.namespace_tgids[i]!=status.namespace_pids[i])return Error(EPROTO);
  value.visible_pid=status.namespace_tgids[status.tgid_depth-1];
  char text[16384];
  if(Path(path,sizeof(path),value.info.pid,"stat")<0)return -1;
  const ssize_t n=ReadAt(host_proc,path,text,sizeof(text));if(n<0)return -1;
  if(!ParseStartTicks(text,static_cast<size_t>(n),value.info.pid,&value.start_ticks))return Error(EBADMSG);
  if(Path(path,sizeof(path),value.info.pid,"root")<0)return -1;
  value.root.reset(openat(host_proc,path,O_PATH|O_DIRECTORY|O_CLOEXEC));
  if(value.root.get()<0||fstat(value.root.get(),&value.root_identity)<0)return -1;
  value.proc.reset(openat(value.root.get(),"proc",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));
  if(value.proc.get()<0||VerifyProc(value.proc.get(),value.pidns_identity)<0)return -1;
  Status visible{};
  if(Path(path,sizeof(path),value.visible_pid,"status")<0||ReadStatusAt(value.proc.get(),path,&visible)<0)return -1;
  if(visible.base.tgid_depth!=1||visible.pid!=value.visible_pid||visible.base.tgid!=value.visible_pid||
     !SameCredentials(visible,value.status))return Error(EXDEV);
  PidfdInfo after{};if(GetInfo(pidfd,&after)<0)return -1;
  if(!SameInfo(value.info,after))return Error(ESTALE);
  *output=std::move(value);return 0;
}
bool SameSnapshot(const Snapshot& a,const Snapshot& b) {
  return SameInfo(a.info,b.info)&&SameAuthority(a.status.base,b.status.base)&&SameCredentials(a.status,b.status)&&
         a.visible_pid==b.visible_pid&&a.start_ticks==b.start_ticks&&SameInode(a.pidns_identity,b.pidns_identity)&&
         SameInode(a.mountns_identity,b.mountns_identity)&&SameInode(a.root_identity,b.root_identity);
}
struct CallerObservation {
  Status status{};
  uint64_t start_ticks{};
};
struct CallerPin {
  Descriptor directory;
  struct stat identity{};
  uint32_t visible_tid{};
  CallerObservation observation{};
};
int ObserveCaller(int directory, uint32_t tid, const Snapshot& leader,
                  CallerObservation* result) {
  CallerObservation value;
  if (ReadStatusAt(directory, "status", &value.status) < 0) return -1;
  const auto& status = value.status;
  if (status.pid != tid || status.base.tgid != leader.visible_pid ||
      status.base.tgid_depth != 1 || status.base.pid_depth != 1 ||
      !SameCredentials(status, leader.status) || !RoleProfile(status)) {
    return Error(EPERM);
  }
  char text[16384];
  const ssize_t bytes = ReadAt(directory, "stat", text, sizeof(text));
  if (bytes < 0) return -1;
  if (!ParseStartTicks(text, static_cast<size_t>(bytes), tid, &value.start_ticks)) {
    return Error(EBADMSG);
  }
  *result = value;
  return 0;
}
int PinCaller(const Snapshot& leader, uint32_t tid, CallerPin* result) {
  char path[80];
  const int bytes = snprintf(path, sizeof(path), "%u/task/%u", leader.visible_pid, tid);
  if (bytes <= 0 || static_cast<size_t>(bytes) >= sizeof(path)) return Error(EOVERFLOW);
  CallerPin value;
  value.visible_tid = tid;
  value.directory.reset(openat(leader.proc.get(), path,
                              O_PATH | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
  struct statfs fs{};
  if (value.directory.get() < 0 || fstat(value.directory.get(), &value.identity) < 0 ||
      fstatfs(value.directory.get(), &fs) < 0) return -1;
  if (!S_ISDIR(value.identity.st_mode) || static_cast<uint64_t>(fs.f_type) != PROC_SUPER_MAGIC) {
    return Error(EXDEV);
  }
  if (ObserveCaller(value.directory.get(), tid, leader, &value.observation) < 0) return -1;
  *result = std::move(value);
  return 0;
}
int RecheckCaller(const CallerPin& caller, const Snapshot& leader) {
  // Keep the proc task-directory inode, not just its numeric name, while the
  // snapshot is made. Reopening /proc/<tgid>/task/<tid> here would accept a new
  // task after TID reuse. Child lookups through this held proc inode refer to
  // the original struct pid; a dead task fails instead of changing the lease.
  struct stat identity{};
  CallerObservation now;
  if (fstat(caller.directory.get(), &identity) < 0 ||
      ObserveCaller(caller.directory.get(), caller.visible_tid, leader, &now) < 0) return -1;
  if (!SameInode(identity, caller.identity) || now.start_ticks != caller.observation.start_ticks ||
      !SameAuthority(now.status.base, caller.observation.status.base) ||
      !SameCredentials(now.status, caller.observation.status)) return Error(ESTALE);
  return 0;
}
struct Peer {Descriptor pidfd;Snapshot snapshot;};
int CaptureSender(int host_proc,int connection,const struct ucred& sender,int sender_pidfd,Peer* output) {
  if(CheckSocket(connection,false,true)<0||!ConnectionAlive(connection))return -1;
  struct ucred creator{};socklen_t n=sizeof(creator);
  if(getsockopt(connection,SOL_SOCKET,SO_PEERCRED,&creator,&n)<0)return -1;
  if(n!=sizeof(creator)||creator.pid<=0||sender.pid!=creator.pid)return Error(EPERM);
  Peer value;int fd=-1;if(Option(connection,kPeerPidfd,&fd)<0)return -1;value.pidfd.reset(fd);
  if(Capture(host_proc,value.pidfd.get(),&value.snapshot)<0)return -1;
  PidfdInfo message{};if(GetInfo(sender_pidfd,&message)<0)return -1;
  if(value.snapshot.info.pid!=static_cast<uint32_t>(creator.pid)||message.pid!=value.snapshot.info.pid||
     message.tgid!=value.snapshot.info.tgid||creator.uid!=value.snapshot.info.euid||creator.gid!=value.snapshot.info.egid||
     !SameInfo(value.snapshot.info,message)||!Alive(value.pidfd.get()))return Error(EPERM);
  // sender.uid/gid are deliberately not authority: SETUID/GID can forge those
  // ucred fields. Kernel PIDFD_GET_INFO and pinned task status provide the IDs.
  *output=std::move(value);return 0;
}
}  // namespace

Descriptor::~Descriptor(){reset();}
Descriptor::Descriptor(Descriptor&& other) noexcept:value_(other.release()){}
Descriptor& Descriptor::operator=(Descriptor&& other) noexcept{if(this!=&other)reset(other.release());return *this;}
int Descriptor::release(){const int value=value_;value_=-1;return value;}
void Descriptor::reset(int value){if(value==value_)return;const int saved=errno;if(value_>=0)close(value_);value_=value;errno=saved;}

bool DecodeRequest(const unsigned char* bytes,size_t size,Request* result) {
  if(!bytes||!result||size!=kWireBytes||memcmp(bytes,kMagic,sizeof(kMagic))||U32(bytes+8)!=1)return false;
  for(size_t i=128;i<size;++i)if(bytes[i])return false;
  Request r{};r.operation=static_cast<Operation>(U32(bytes+12));memcpy(r.pair,bytes+16,kDigestBytes);memcpy(r.token,bytes+48,kDigestBytes);
  r.uid_min=U32(bytes+80);r.uid_max=U32(bytes+84);r.gid_min=U32(bytes+88);r.gid_max=U32(bytes+92);
  r.child_pid_in_parent_namespace=U32(bytes+96);r.initial_uid=U32(bytes+100);r.initial_gid=U32(bytes+104);
  r.caller_tid=U32(bytes+108);r.payload_size=U64(bytes+112);r.source_flags=U32(bytes+120);r.original_fd_flags=U32(bytes+124);
  if(!ValidRequest(r))return false;
  *result=r;
  return true;
}
bool EncodeRequest(const Request& r,unsigned char output[kWireBytes]) {
  if(!output||!ValidRequest(r))return false;
  unsigned char bytes[kWireBytes]{};
  memcpy(bytes,kMagic,sizeof(kMagic));Put32(bytes+8,1);Put32(bytes+12,static_cast<uint32_t>(r.operation));
  memcpy(bytes+16,r.pair,kDigestBytes);memcpy(bytes+48,r.token,kDigestBytes);
  Put32(bytes+80,r.uid_min);Put32(bytes+84,r.uid_max);Put32(bytes+88,r.gid_min);Put32(bytes+92,r.gid_max);
  Put32(bytes+96,r.child_pid_in_parent_namespace);Put32(bytes+100,r.initial_uid);Put32(bytes+104,r.initial_gid);
  Put32(bytes+108,r.caller_tid);Put64(bytes+112,r.payload_size);Put32(bytes+120,r.source_flags);Put32(bytes+124,r.original_fd_flags);
  memcpy(output,bytes,sizeof(bytes));return true;
}
int ConfigureIdentityReception(int socket,bool listener) {
  if(CheckSocket(socket,listener,false)<0)return -1;
  const int on=1;
  if(setsockopt(socket,SOL_SOCKET,SO_PASSCRED,&on,sizeof(on))<0||setsockopt(socket,SOL_SOCKET,kPassPidfd,&on,sizeof(on))<0)return -1;
  return CheckSocket(socket,listener,true);
}
int Receive(int connection,Received* result) {
  if(!result||result->received_)return Error(EINVAL);
  if(CheckSocket(connection,false,true)<0)return -1;
  Received value;unsigned char bytes[kWireBytes]{};
  union{cmsghdr alignment;unsigned char bytes[CMSG_SPACE(253*sizeof(int))+CMSG_SPACE(sizeof(ucred))+CMSG_SPACE(sizeof(int))];} control{};
  iovec iov{bytes,sizeof(bytes)};msghdr message{};message.msg_iov=&iov;message.msg_iovlen=1;message.msg_control=control.bytes;message.msg_controllen=sizeof(control.bytes);
  const ssize_t count=recvmsg(connection,&message,MSG_DONTWAIT|MSG_CMSG_CLOEXEC|MSG_TRUNC);
  if(count<0)return -1;
  bool valid=count==sizeof(bytes)&&!(message.msg_flags&(MSG_TRUNC|MSG_CTRUNC));size_t rights=0,creds=0,pidfds=0;
  for(cmsghdr* h=CMSG_FIRSTHDR(&message);h;h=CMSG_NXTHDR(&message,h)){
    const size_t offset=reinterpret_cast<unsigned char*>(h)-control.bytes;
    if(h->cmsg_len<CMSG_LEN(0)||h->cmsg_len>message.msg_controllen-offset){valid=false;break;}
    const size_t size=h->cmsg_len-CMSG_LEN(0);
    if(h->cmsg_level==SOL_SOCKET&&h->cmsg_type==SCM_RIGHTS){
      if(size%sizeof(int))valid=false;
      for(size_t i=0;i<size/sizeof(int);++i){int fd;memcpy(&fd,CMSG_DATA(h)+i*sizeof(int),sizeof(fd));Descriptor owned(fd);if(rights<2)value.rights_[rights]=std::move(owned);++rights;}
    }else if(h->cmsg_level==SOL_SOCKET&&h->cmsg_type==kScmPidfd){
      for(size_t i=0;i<size/sizeof(int);++i){
        int fd;memcpy(&fd,CMSG_DATA(h)+i*sizeof(int),sizeof(fd));Descriptor owned(fd);
        if(!pidfds&&i==0)value.sender_pidfd_=std::move(owned);
      }
      if(size!=sizeof(int))valid=false;
      ++pidfds;
    }else if(h->cmsg_level==SOL_SOCKET&&h->cmsg_type==SCM_CREDENTIALS){
      if(size==sizeof(ucred)&&!creds)memcpy(&value.credentials_,CMSG_DATA(h),sizeof(ucred));else valid=false;++creds;
    }else valid=false;  // Non-FD ancillary bytes are never interpreted as FDs.
  }
  if(!valid||creds!=1||pidfds!=1||value.sender_pidfd_.get()<0||!DecodeRequest(bytes,sizeof(bytes),&value.request_))return Error(EPROTO);
  if(rights!=(value.request_.operation==Operation::kCreate?2U:0U))return Error(EPROTO);
  for(size_t i=0;i<rights;++i){const int flags=fcntl(value.rights_[i].get(),F_GETFD);if(flags<0||!(flags&FD_CLOEXEC))return Error(EPROTO);}
  const int flags=fcntl(value.sender_pidfd_.get(),F_GETFD);if(flags<0||!(flags&FD_CLOEXEC)||value.credentials_.pid<=0)return Error(EPROTO);
  result->request_=value.request_;result->credentials_=value.credentials_;result->sender_pidfd_=std::move(value.sender_pidfd_);
  for(unsigned i=0;i<2;++i)result->rights_[i]=std::move(value.rights_[i]);
  result->received_=true;
  return 0;
}

struct Registry::Impl {
  enum class Phase {kEmpty,kPending,kActive,kSuspending,kSuspended,kRevoked};
  struct Slot {
    Phase phase=Phase::kEmpty;Descriptor connection;Peer subject;Request begin{};
    unsigned char token[kDigestBytes]{};uint64_t serial{},deadline{};bool busy=false;
    CallerPin caller;
    Descriptor revoked_pidfd;
    uint32_t subject_host_pid{};
  };
  Slot slots[kMaximumGrants];Descriptor self_pidfd,proc;Snapshot self;
  unsigned char pair[kDigestBytes]{};uint32_t owner{};uint64_t serial{};
  bool poisoned=false;
  int OwnThread() const {
    if(static_cast<uint32_t>(getpid())!=owner||syscall(SYS_gettid)!=owner)return Error(ESHUTDOWN);
    // A shared-VM process in a new PID namespace can have the same numeric PID
    // as this owner. Resolve current thread-self in the owner's held, verified
    // proc view before touching shared state; never use the owner's pidfd as
    // evidence that the *current caller* is that owner.
    Status current;
    if(ReadStatusAt(proc.get(),"thread-self/status",&current)<0)return -1;
    if(current.pid!=owner||current.base.tgid!=owner||current.base.pid_depth!=1||
       current.base.tgid_depth!=1)return Error(ESHUTDOWN);
    return 0;
  }
  int Owner() {
    if(OwnThread()<0)return -1;
    if(poisoned)return Error(ESHUTDOWN);
    Snapshot now;
    if(Capture(proc.get(),self_pidfd.get(),&now)<0){poisoned=true;return -1;}
    if(!SameSnapshot(now,self)||!RootProfile(now.status)||now.status.threads!=1){
      poisoned=true;return Error(ESTALE);
    }
    return 0;
  }
  Slot* Find(GrantHandle h) {if(h.slot>=kMaximumGrants)return nullptr;Slot& s=slots[h.slot];return s.phase!=Phase::kEmpty&&s.serial==h.serial?&s:nullptr;}
  void Reset(Slot& s){s=Slot{};}
  int SubjectPidfd(const Slot& s) const {
    return s.phase==Phase::kRevoked?s.revoked_pidfd.get():s.subject.pidfd.get();
  }
  void Revoke(Slot& s) {
    if(s.phase==Phase::kEmpty||s.phase==Phase::kRevoked)return;
    Descriptor pidfd=std::move(s.subject.pidfd);
    const uint32_t pid=s.subject_host_pid;
    const uint64_t generation=s.serial;
    Reset(s);
    s.phase=Phase::kRevoked;s.serial=generation;s.subject_host_pid=pid;
    s.revoked_pidfd=std::move(pidfd);
  }
  int Recheck(Slot& s, bool connection_required=true) {
    if(s.phase==Phase::kEmpty||s.phase==Phase::kRevoked)return Error(ESHUTDOWN);
    if((connection_required&&!ConnectionAlive(s.connection.get()))||!Alive(s.subject.pidfd.get()))return Error(EPIPE);
    Snapshot now;if(Capture(proc.get(),s.subject.pidfd.get(),&now)<0)return -1;
    return SameSnapshot(now,s.subject.snapshot)&&RoleProfile(now.status)?0:Error(ESTALE);
  }
};

Registry::~Registry(){delete impl_;}
int Registry::Initialize(const unsigned char pair[kDigestBytes]) {
  if(impl_||!pair||!Nonzero(pair,kDigestBytes)||syscall(SYS_gettid)!=getpid())return Error(EINVAL);
  Impl* value=new(std::nothrow) Impl;if(!value)return Error(ENOMEM);
  // Construct under a temporary owner so every failure closes only new FDs.
  Registry cleanup;cleanup.impl_=value;value->owner=static_cast<uint32_t>(getpid());
  value->self_pidfd.reset(static_cast<int>(syscall(SYS_pidfd_open,static_cast<long>(getpid()),0UL)));
  if(value->self_pidfd.get()<0)return -1;
  Descriptor user(ioctl(value->self_pidfd.get(),kGetUserNs,0UL)),pidns(ioctl(value->self_pidfd.get(),kGetPidNs,0UL));struct stat pidns_identity{};
  if(user.get()<0||pidns.get()<0||InitialUser(user.get())<0||Namespace(pidns.get(),CLONE_NEWPID,&pidns_identity)<0)return -1;
  value->proc.reset(open("/proc",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));
  if(value->proc.get()<0||VerifyProc(value->proc.get(),pidns_identity)<0||Capture(value->proc.get(),value->self_pidfd.get(),&value->self)<0)return -1;
  if(!RootProfile(value->self.status)||value->self.status.threads!=1)return Error(EPERM);
  memcpy(value->pair,pair,kDigestBytes);impl_=value;cleanup.impl_=nullptr;return 0;
}
int Registry::Begin(Descriptor* connection,const Received& message,Challenge* output) {
  if(!impl_)return Error(ESHUTDOWN);
  if(!connection||!output||!message.received_||message.request_.operation!=Operation::kBegin)return Error(EINVAL);
  if(impl_->Owner()<0||Sweep()<0)return -1;
  const auto& request=message.request_;if(!Equal(request.pair,impl_->pair,kDigestBytes))return Error(EPROTO);
  Peer peer;if(CaptureSender(impl_->proc.get(),connection->get(),message.credentials_,message.sender_pidfd_.get(),&peer)<0)return -1;
  if(!RoleProfile(peer.snapshot.status)||peer.snapshot.status.threads!=1||peer.snapshot.info.ppid==0)return Error(EPERM);
  size_t index=kMaximumGrants;
  for(size_t i=0;i<kMaximumGrants;++i){auto& s=impl_->slots[i];if(s.phase==Impl::Phase::kEmpty){if(index==kMaximumGrants)index=i;continue;}if(s.subject_host_pid==peer.snapshot.info.pid)return Error(EALREADY);}
  if(index==kMaximumGrants)return Error(ENOSPC);
  if(impl_->serial==UINT64_MAX)return Error(EOVERFLOW);
  const uint64_t now=Now();if(!now||now>UINT64_MAX-kPendingNanos)return Error(EIO);
  unsigned char token[kDigestBytes];const ssize_t amount=getrandom(token,sizeof(token),GRND_NONBLOCK);
  if(amount<0)return -1;
  if(amount!=sizeof(token)||!Nonzero(token,sizeof(token)))return Error(EIO);
  for(const auto& s:impl_->slots)if(s.phase!=Impl::Phase::kEmpty&&Equal(s.token,token,kDigestBytes))return Error(EAGAIN);
  Snapshot after;if(Capture(impl_->proc.get(),peer.pidfd.get(),&after)<0)return -1;
  if(!SameSnapshot(peer.snapshot,after)||after.status.threads!=1)return Error(ESTALE);
  auto& slot=impl_->slots[index];slot.connection=std::move(*connection);slot.subject=std::move(peer);slot.begin=request;
  slot.subject_host_pid=slot.subject.snapshot.info.pid;
  memcpy(slot.token,token,sizeof(token));slot.serial=++impl_->serial;slot.deadline=now+kPendingNanos;slot.phase=Impl::Phase::kPending;
  Challenge challenge{};challenge.handle={static_cast<uint32_t>(index),slot.serial};memcpy(challenge.token,token,sizeof(token));challenge.visible_pid=slot.subject.snapshot.visible_pid;
  *output=challenge;return 0;
}
int Registry::Approve(int admin_connection,const Received& message) {
  if(!impl_)return Error(ESHUTDOWN);
  if(!message.received_||message.request_.operation!=Operation::kApprove)return Error(EINVAL);
  if(impl_->Owner()<0||Sweep()<0)return -1;
  const auto& request=message.request_;if(!Equal(request.pair,impl_->pair,kDigestBytes))return Error(EPROTO);
  Peer parent;if(CaptureSender(impl_->proc.get(),admin_connection,message.credentials_,message.sender_pidfd_.get(),&parent)<0)return -1;
  if(!RootProfile(parent.snapshot.status))return Error(EPERM);
  Impl::Slot* slot=nullptr;for(auto& s:impl_->slots)if(s.phase!=Impl::Phase::kEmpty&&Equal(s.token,request.token,kDigestBytes)){slot=&s;break;}
  if(!slot)return Error(ENOENT);
  if(slot->phase!=Impl::Phase::kPending)return Error(EALREADY);
  const auto& child=slot->subject.snapshot;const auto& original=slot->begin;
  // The first supported role fork stays in its parent's PID namespace. The
  // parent's fork-return PID is therefore the child's last NStgid component.
  if(parent.snapshot.info.pid!=child.info.ppid||!SameInode(parent.snapshot.pidns_identity,child.pidns_identity)||
     request.child_pid_in_parent_namespace!=child.visible_pid||request.initial_uid!=child.status.base.uid[0]||
     request.initial_gid!=child.status.base.gid[0]||request.uid_min!=original.uid_min||request.uid_max!=original.uid_max||
     request.gid_min!=original.gid_min||request.gid_max!=original.gid_max)return Error(EPERM);
  if(impl_->Recheck(*slot)<0){impl_->Revoke(*slot);return -1;}
  Snapshot after;if(Capture(impl_->proc.get(),parent.pidfd.get(),&after)<0)return -1;
  if(!SameSnapshot(parent.snapshot,after)||!RootProfile(after.status))return Error(ESTALE);
  const uint64_t now=Now();if(!now||now>=slot->deadline){impl_->Revoke(*slot);return Error(ETIMEDOUT);}
  // Root approval attests the matched pre-guest platform transition. NNP,
  // seccomp mode and this bounded snapshot alone are not filter attestation.
  slot->phase=Impl::Phase::kActive;slot->deadline=0;return 0;
}
int Registry::Attach(Descriptor* connection,const Received& message,GrantHandle* output) {
  if(!impl_)return Error(ESHUTDOWN);
  if(!connection||!output||!message.received_||message.request_.operation!=Operation::kAttach)return Error(EINVAL);
  if(impl_->Owner()<0||Sweep()<0)return -1;
  const auto& request=message.request_;
  if(!Equal(request.pair,impl_->pair,kDigestBytes))return Error(EPROTO);
  size_t index=kMaximumGrants;
  for(size_t i=0;i<kMaximumGrants;++i){
    const auto& s=impl_->slots[i];
    if(s.phase!=Impl::Phase::kEmpty&&s.phase!=Impl::Phase::kRevoked&&Equal(s.token,request.token,kDigestBytes)){
      index=i;break;
    }
  }
  if(index==kMaximumGrants)return Error(ENOENT);
  auto& slot=impl_->slots[index];
  if(slot.phase!=Impl::Phase::kSuspended||slot.busy||slot.connection.get()>=0)return Error(EBUSY);
  Peer peer;
  if(CaptureSender(impl_->proc.get(),connection->get(),message.credentials_,message.sender_pidfd_.get(),&peer)<0)return -1;
  // A copied token/connection in a fork child cannot target its parent slot.
  // Do not revoke another task merely because that other task's token leaked.
  if(peer.snapshot.info.pid!=slot.subject_host_pid)return Error(EPERM);
  if(!SameSnapshot(peer.snapshot,slot.subject.snapshot)||!RoleProfile(peer.snapshot.status)){
    impl_->Revoke(slot);return Error(ESTALE);
  }
  if(request.caller_tid!=slot.caller.visible_tid)return Error(EPERM);
  if(impl_->Recheck(slot,false)<0||RecheckCaller(slot.caller,slot.subject.snapshot)<0){
    impl_->Revoke(slot);return -1;
  }
  slot.connection=std::move(*connection);slot.phase=Impl::Phase::kActive;
  slot.caller=CallerPin{};
  *output={static_cast<uint32_t>(index),slot.serial};return 0;
}
int Registry::IsActive(GrantHandle handle) {
  if(!impl_)return Error(ESHUTDOWN);
  if(impl_->Owner()<0)return -1;
  auto* slot=impl_->Find(handle);if(!slot)return Error(ENOENT);
  if(slot->phase==Impl::Phase::kRevoked)return Error(ESHUTDOWN);
  if(slot->phase!=Impl::Phase::kActive)return Error(EAGAIN);
  if(impl_->Recheck(*slot)<0){impl_->Revoke(*slot);return -1;}return 0;
}
int Registry::Connection(GrantHandle handle) const {
  if(!impl_)return Error(ESHUTDOWN);
  if(impl_->Owner()<0)return -1;
  auto* slot=impl_->Find(handle);
  if(!slot)return Error(ENOENT);
  if(slot->phase==Impl::Phase::kRevoked)return Error(ESHUTDOWN);
  return slot->connection.get()>=0?slot->connection.get():Error(ENOTCONN);
}
int Registry::AuthorizeCreate(GrantHandle handle,const Received& message,SnapshotAuthority* output) {
  if(!impl_)return Error(ESHUTDOWN);
  if(!output||!message.received_||message.request_.operation!=Operation::kCreate)return Error(EINVAL);
  if(impl_->Owner()<0)return -1;
  auto* slot=impl_->Find(handle);if(!slot)return Error(ENOENT);
  const auto& request=message.request_;
  if(slot->phase!=Impl::Phase::kActive||slot->busy)return Error(EBUSY);
  if(!Equal(request.pair,impl_->pair,kDigestBytes)||!Equal(request.token,slot->token,kDigestBytes))return Error(EPERM);
  Peer now;
  if(CaptureSender(impl_->proc.get(),slot->connection.get(),message.credentials_,message.sender_pidfd_.get(),&now)<0){
    impl_->Revoke(*slot);return -1;
  }
  if(!SameSnapshot(now.snapshot,slot->subject.snapshot)||!RoleProfile(now.snapshot.status)){
    impl_->Revoke(*slot);
    return Error(ESTALE);
  }
  CallerPin caller;
  if(PinCaller(now.snapshot,request.caller_tid,&caller)<0||impl_->Recheck(*slot)<0||
     RecheckCaller(caller,slot->subject.snapshot)<0){impl_->Revoke(*slot);return -1;}
  SnapshotAuthority value{};value.proc_fd=slot->subject.snapshot.proc.get();value.subject_pidfd=slot->subject.pidfd.get();
  value.visible_tgid=now.snapshot.visible_pid;value.uid=now.snapshot.status.base.uid[0];value.gid=now.snapshot.status.base.gid[0];value.start_ticks=now.snapshot.start_ticks;
  value.caller_tid=request.caller_tid;value.caller_start_ticks=caller.observation.start_ticks;
  slot->caller=std::move(caller);value.caller_proc_fd=slot->caller.directory.get();
  slot->busy=true;*output=value;return 0;
}
int Registry::FinishCreate(GrantHandle handle) {
  if(!impl_)return Error(ESHUTDOWN);
  if(impl_->Owner()<0)return -1;
  auto* slot=impl_->Find(handle);if(!slot||!slot->busy)return Error(EINVAL);
  if(impl_->Recheck(*slot)<0||RecheckCaller(slot->caller,slot->subject.snapshot)<0){
    impl_->Revoke(*slot);
    return -1;
  }
  slot->caller=CallerPin{};
  slot->busy=false;
  return 0;
}
int Registry::Suspend(GrantHandle handle,const Received& message) {
  if(!impl_)return Error(ESHUTDOWN);
  if(!message.received_||message.request_.operation!=Operation::kSuspend)return Error(EINVAL);
  if(impl_->Owner()<0)return -1;
  auto* slot=impl_->Find(handle);if(!slot)return Error(ENOENT);
  if(slot->phase!=Impl::Phase::kActive||slot->busy)return Error(EBUSY);
  if(!Equal(message.request_.pair,impl_->pair,kDigestBytes)||!Equal(message.request_.token,slot->token,kDigestBytes))return Error(EPERM);
  Peer now;
  if(CaptureSender(impl_->proc.get(),slot->connection.get(),message.credentials_,message.sender_pidfd_.get(),&now)<0){
    impl_->Revoke(*slot);return -1;
  }
  if(!SameSnapshot(now.snapshot,slot->subject.snapshot)||impl_->Recheck(*slot)<0){
    impl_->Revoke(*slot);return Error(ESTALE);
  }
  CallerPin caller;
  if(PinCaller(slot->subject.snapshot,message.request_.caller_tid,&caller)<0||
     impl_->Recheck(*slot)<0||RecheckCaller(caller,slot->subject.snapshot)<0){
    impl_->Revoke(*slot);return -1;
  }
  slot->caller=std::move(caller);
  // Suspend is not yet permission to lose this transport. The owner must
  // successfully acknowledge, then explicitly Detach; any earlier HUP revokes.
  slot->phase=Impl::Phase::kSuspending;return 0;
}
int Registry::Detach(GrantHandle handle) {
  if(!impl_)return Error(ESHUTDOWN);
  if(impl_->Owner()<0)return -1;
  auto* slot=impl_->Find(handle);if(!slot)return Error(ENOENT);
  if(slot->phase!=Impl::Phase::kSuspending||slot->busy)return Error(EINVAL);
  if(impl_->Recheck(*slot)<0||RecheckCaller(slot->caller,slot->subject.snapshot)<0){
    impl_->Revoke(*slot);return -1;
  }
  slot->connection.reset();slot->phase=Impl::Phase::kSuspended;return 0;
}
int Registry::Release(GrantHandle handle,const Received& message) {
  if(!impl_)return Error(ESHUTDOWN);
  if(!message.received_||message.request_.operation!=Operation::kRelease)return Error(EINVAL);
  if(impl_->Owner()<0)return -1;
  auto* slot=impl_->Find(handle);if(!slot)return Error(ENOENT);
  if(slot->busy||!Equal(message.request_.pair,impl_->pair,kDigestBytes)||!Equal(message.request_.token,slot->token,kDigestBytes))return Error(EPERM);
  Peer now;if(CaptureSender(impl_->proc.get(),slot->connection.get(),message.credentials_,message.sender_pidfd_.get(),&now)<0)return -1;
  if(now.snapshot.info.pid!=slot->subject.snapshot.info.pid||now.snapshot.start_ticks!=slot->subject.snapshot.start_ticks)return Error(EPERM);
  impl_->Revoke(*slot);return 0;
}
int Registry::Sweep() {
  if(!impl_)return Error(ESHUTDOWN);
  if(impl_->Owner()<0)return -1;
  const uint64_t now=Now();if(!now)return Error(EIO);
  for(auto& s:impl_->slots){
    if(s.phase==Impl::Phase::kEmpty||s.busy)continue;
    const int live=PidfdLiveness(impl_->SubjectPidfd(s));
    // An interrupted/failed poll is not proof of process death. Never forget
    // a one-time authorization tombstone on a mere observation error.
    if(live<0)return -1;
    if(live==0){impl_->Reset(s);continue;}
    if(s.phase==Impl::Phase::kRevoked)continue;
    if(s.phase==Impl::Phase::kSuspending||s.phase==Impl::Phase::kSuspended){
      const bool transport_required=s.phase==Impl::Phase::kSuspending;
      if(impl_->Recheck(s,transport_required)<0||RecheckCaller(s.caller,s.subject.snapshot)<0){
        impl_->Revoke(s);continue;
      }
      if(!transport_required&&s.connection.get()>=0)impl_->Revoke(s);
    }else if(!ConnectionAlive(s.connection.get())||
             (s.phase==Impl::Phase::kPending&&now>=s.deadline))impl_->Revoke(s);
  }
  return 0;
}
void Registry::Close(GrantHandle handle) {
  // Cleanup remains possible after this owner's credential check poisoned the
  // registry. A foreign shared-VM process/thread must not mutate the owner.
  if(!impl_||impl_->OwnThread()<0)return;
  auto* slot=impl_->Find(handle);if(slot)impl_->Revoke(*slot);
}
}  // namespace droidloom::proc_maps_factory::role_v1
