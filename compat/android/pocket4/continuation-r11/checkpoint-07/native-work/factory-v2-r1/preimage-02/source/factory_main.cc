// SPDX-License-Identifier: Apache-2.0
// New V2 root factory. Default invocation performs no service action.
// Deployment supplies and owns the listening/control sockets. This process
// never binds a socket, mounts a filesystem, changes credentials or signals apps.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "factory_context.h"
#include "berberis/kernel_api/proc_maps_factory_protocol.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/magic.h>
#include <linux/memfd.h>
#include <linux/nsfs.h>
#include <poll.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <sys/xattr.h>
#include <time.h>
#include <unistd.h>
namespace droidloom::proc_maps_factory {
namespace p=berberis::proc_maps_provenance;
namespace {
constexpr int kPeerPidfd=77;
constexpr unsigned long kPidfdPidNamespace=_IO(0xff,5);
constexpr unsigned long kPidfdUserNamespace=_IO(0xff,9);
constexpr short kDead=POLLERR|POLLHUP|POLLNVAL|POLLRDHUP;
constexpr uint64_t kRequestNanos=2000000000ULL;
class Fd {
 public:
  explicit Fd(int value=-1):value_(value){}
  ~Fd(){reset();}
  Fd(const Fd&)=delete;Fd& operator=(const Fd&)=delete;
  int get()const{return value_;}
  int release(){const int value=value_;value_=-1;return value;}
  void reset(int value=-1){const int saved=errno;if(value_>=0)close(value_);value_=value;errno=saved;}
 private:int value_;
};
int Error(int error){errno=error;return -1;}
bool SameInode(const struct stat& a,const struct stat& b) {
  return a.st_dev==b.st_dev&&a.st_ino==b.st_ino;
}
uint64_t Now() {
  struct timespec time{};
  if(clock_gettime(CLOCK_MONOTONIC,&time)<0||time.tv_sec<0||time.tv_nsec<0||
     time.tv_nsec>=1000000000||static_cast<uint64_t>(time.tv_sec)>(UINT64_MAX-999999999)/1000000000)
    return 0;
  return static_cast<uint64_t>(time.tv_sec)*1000000000+static_cast<uint64_t>(time.tv_nsec);
}
int SocketOption(int fd,int option,int* output) {
  socklen_t size=sizeof(*output);
  if(getsockopt(fd,SOL_SOCKET,option,output,&size)<0)return -1;
  return size==sizeof(*output)?0:Error(EPROTO);
}
bool Alive(int pidfd) {
  struct pollfd value{pidfd,POLLIN,0};
  const int result=poll(&value,1,0);
  if(result<0)return false;
  if(result!=0||value.revents){Error(EPIPE);return false;}
  return true;
}
int NamespaceIdentity(int fd,int type,struct stat* output) {
  struct statfs fs{};
  if(fstat(fd,output)<0||fstatfs(fd,&fs)<0)return -1;
  const int kind=ioctl(fd,NS_GET_NSTYPE,0UL);
  if(kind<0)return -1;
  if(kind!=type||static_cast<uint64_t>(fs.f_type)!=NSFS_MAGIC)return Error(EXDEV);
  return 0;
}
int InitialUserNamespace(int fd) {
  struct stat identity{};
  if(NamespaceIdentity(fd,CLONE_NEWUSER,&identity)<0)return -1;
  if(static_cast<uint64_t>(identity.st_dev)!=p::kTrustedUserNamespaceDevice||
     static_cast<uint64_t>(identity.st_ino)!=p::kTrustedUserNamespaceInode)return Error(EXDEV);
  return 0;
}
int SameNamespace(int fd,const struct stat& expected,int type) {
  struct stat value{};
  if(NamespaceIdentity(fd,type,&value)<0)return -1;
  return SameInode(value,expected)?0:Error(EXDEV);
}
// A procfs mount can expose another PID namespace's numeric names. Bind the
// held view using its actual PID 1 namespace, never by its display pathname.
int VerifyProcView(int proc,const struct stat& expected_pidns) {
  struct statfs fs{};
  if(fstatfs(proc,&fs)<0)return -1;
  if(static_cast<uint64_t>(fs.f_type)!=PROC_SUPER_MAGIC)return Error(EXDEV);
  Fd namespace_fd(openat(proc,"1/ns/pid",O_RDONLY|O_CLOEXEC));
  if(namespace_fd.get()<0)return -1;
  return SameNamespace(namespace_fd.get(),expected_pidns,CLONE_NEWPID);
}
ssize_t ReadFileAt(int directory,const char* path,char* output,size_t capacity) {
  Fd fd(openat(directory,path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW));
  if(fd.get()<0)return -1;
  size_t used=0;
  while(used<capacity) {
    const ssize_t count=read(fd.get(),output+used,capacity-used);
    if(count<0){if(errno==EINTR)continue;return -1;}
    if(count==0)return static_cast<ssize_t>(used);
    used+=static_cast<size_t>(count);
  }
  return Error(EOVERFLOW);
}
int ReadStatus(int proc,const char* path,ProcessStatus* output) {
  char text[16384];const ssize_t size=ReadFileAt(proc,path,text,sizeof(text));
  if(size<0)return -1;
  return ParseStatus(text,static_cast<size_t>(size),output)?0:Error(EBADMSG);
}
int Path(char* output,size_t size,const char* suffix,uint32_t pid) {
  const int n=snprintf(output,size,"%u/%s",pid,suffix);
  return n>0&&static_cast<size_t>(n)<size?0:Error(EOVERFLOW);
}
struct Authority {
  Fd listener,control,owner_pidfd,proc,self_pidfd,self_pidns,self_userns;
  struct stat pidns{};
  uint32_t uid_min{},uid_max{};
};
int OwnerLive(const Authority& authority) {
  struct pollfd control{authority.control.get(),static_cast<short>(POLLIN|POLLRDHUP),0};
  const int result=poll(&control,1,0);
  if(result<0)return -1;
  // Parent closes the control endpoint to stop this service. Unsolicited
  // control input is also terminal; there is no ambient command interpreter.
  if(result||control.revents||!Alive(authority.owner_pidfd.get()))return Error(ECANCELED);
  return 0;
}
int Wait(const Authority& authority,int fd,short events,int peer,uint64_t deadline) {
  uint64_t last=Now();
  if(last==0)return Error(EIO);
  for(;;) {
    const uint64_t now=Now();
    if(now<last||now==0||now>=deadline)return Error(ETIMEDOUT);
    last=now;
    int timeout=static_cast<int>((deadline-now+999999)/1000000);
    if(timeout>100)timeout=100;
    struct pollfd items[4]={
      {fd,static_cast<short>(events|POLLRDHUP),0},
      {authority.control.get(),static_cast<short>(POLLIN|POLLRDHUP),0},
      {authority.owner_pidfd.get(),POLLIN,0},{peer,POLLIN,0}};
    const int result=poll(items,peer<0?3:4,timeout);
    if(result<0){if(errno==EINTR)continue;return -1;}
    if(items[1].revents||items[2].revents)return Error(ECANCELED);
    if((items[0].revents&kDead)||(peer>=0&&items[3].revents))return Error(EPIPE);
    if(items[0].revents&events)return 0;
  }
}
int ValidateRoot(Authority* authority) {
  uid_t real,effective,saved;gid_t greal,geffective,gsaved;
  if(getresuid(&real,&effective,&saved)<0||getresgid(&greal,&geffective,&gsaved)<0)return -1;
  if(real||effective||saved||greal||geffective||gsaved||
     syscall(SYS_setfsuid,static_cast<long>(static_cast<uid_t>(-1)))!=0||
     syscall(SYS_setfsgid,static_cast<long>(static_cast<gid_t>(-1)))!=0||
     syscall(SYS_gettid)!=getpid())return Error(EPERM);
  authority->self_pidfd.reset(static_cast<int>(syscall(SYS_pidfd_open,static_cast<long>(getpid()),
                                                       static_cast<unsigned long>(O_EXCL))));
  if(authority->self_pidfd.get()<0)return -1;
  authority->self_userns.reset(ioctl(authority->self_pidfd.get(),kPidfdUserNamespace,0UL));
  authority->self_pidns.reset(ioctl(authority->self_pidfd.get(),kPidfdPidNamespace,0UL));
  if(authority->self_userns.get()<0||authority->self_pidns.get()<0)return -1;
  if(InitialUserNamespace(authority->self_userns.get())<0||
     NamespaceIdentity(authority->self_pidns.get(),CLONE_NEWPID,&authority->pidns)<0)return -1;
  authority->proc.reset(open("/proc",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));
  return authority->proc.get()<0?-1:VerifyProcView(authority->proc.get(),authority->pidns);
}
int ValidateSocket(int fd,bool listener) {
  int domain,kind,accepting;
  if(SocketOption(fd,SO_DOMAIN,&domain)<0||SocketOption(fd,SO_TYPE,&kind)<0||
     SocketOption(fd,SO_ACCEPTCONN,&accepting)<0)return -1;
  const int status=fcntl(fd,F_GETFL),flags=fcntl(fd,F_GETFD);
  if(domain!=AF_UNIX||kind!=SOCK_SEQPACKET||accepting!=(listener?1:0)||
     status<0||flags<0||!(status&O_NONBLOCK))return Error(EPROTO);
  return fcntl(fd,F_SETFD,flags|FD_CLOEXEC);
}
int Prepare(Authority* authority,int listener,int control,uint32_t low,uint32_t high) {
  if(listener<3||control<3||listener==control||low==0||low>high||high>INT_MAX)return Error(EINVAL);
  authority->listener.reset(listener);authority->control.reset(control);
  authority->uid_min=low;authority->uid_max=high;
  if(ValidateRoot(authority)<0||ValidateSocket(listener,true)<0||
     ValidateSocket(control,false)<0)return -1;
  struct sockaddr_un address{};socklen_t size=sizeof(address);
  if(getsockname(listener,reinterpret_cast<struct sockaddr*>(&address),&size)<0)return -1;
  constexpr size_t name_size=sizeof(p::kSocketName)-1;
  if(size!=offsetof(struct sockaddr_un,sun_path)+1+name_size||address.sun_family!=AF_UNIX||
     address.sun_path[0]!=0||memcmp(address.sun_path+1,p::kSocketName,name_size))return Error(EPROTO);
  struct ucred owner{};socklen_t owner_size=sizeof(owner);
  if(getsockopt(control,SOL_SOCKET,SO_PEERCRED,&owner,&owner_size)<0)return -1;
  if(owner_size!=sizeof(owner)||owner.uid||owner.gid||owner.pid<=0||owner.pid==getpid())return Error(EPERM);
  int pidfd=-1;if(SocketOption(control,kPeerPidfd,&pidfd)<0)return -1;
  authority->owner_pidfd.reset(pidfd);
  const int owner_flags=fcntl(pidfd,F_GETFD);
  if(pidfd<0||owner_flags<0||!(owner_flags&FD_CLOEXEC)||!Alive(pidfd))return Error(EPROTO);
  Fd userns(ioctl(pidfd,kPidfdUserNamespace,0UL));
  Fd pidns(ioctl(pidfd,kPidfdPidNamespace,0UL));
  if(userns.get()<0||pidns.get()<0||InitialUserNamespace(userns.get())<0||
     SameNamespace(pidns.get(),authority->pidns,CLONE_NEWPID)<0)return -1;
  return OwnerLive(*authority);
}
struct Peer {
  Fd pidfd,userns,pidns,root,proc;
  struct ucred credentials{};
  struct stat pidns_identity{},root_identity{};
  ProcessStatus status{};
  uint32_t visible_tgid{};
  uint64_t start_ticks{};
};
int CapturePeer(const Authority& authority,int connection,const p::CreateRequest& request,Peer* peer) {
  socklen_t size=sizeof(peer->credentials);
  if(getsockopt(connection,SOL_SOCKET,SO_PEERCRED,&peer->credentials,&size)<0)return -1;
  const auto& credentials=peer->credentials;
  if(size!=sizeof(credentials)||credentials.pid<=0||credentials.uid<authority.uid_min||
     credentials.uid>authority.uid_max||credentials.gid==0)return Error(EPERM);
  int pidfd=-1;if(SocketOption(connection,kPeerPidfd,&pidfd)<0)return -1;
  peer->pidfd.reset(pidfd);
  const int peer_flags=fcntl(pidfd,F_GETFD);
  if(pidfd<0||peer_flags<0||!(peer_flags&FD_CLOEXEC)||!Alive(pidfd))return Error(EPROTO);
  peer->userns.reset(ioctl(pidfd,kPidfdUserNamespace,0UL));
  peer->pidns.reset(ioctl(pidfd,kPidfdPidNamespace,0UL));
  if(peer->userns.get()<0||peer->pidns.get()<0||InitialUserNamespace(peer->userns.get())<0||
     NamespaceIdentity(peer->pidns.get(),CLONE_NEWPID,&peer->pidns_identity)<0)return -1;
  char path[80];
  if(Path(path,sizeof(path),"status",static_cast<uint32_t>(credentials.pid))<0||
     ReadStatus(authority.proc.get(),path,&peer->status)<0)return -1;
  if(!Unprivileged(peer->status,credentials.uid,credentials.gid)||
     peer->status.tgid!=static_cast<uint32_t>(credentials.pid))return Error(EPERM);
  for(size_t i=0;i<peer->status.tgid_depth;++i)
    if(peer->status.namespace_pids[i]!=peer->status.namespace_tgids[i])return Error(EPROTO);
  peer->visible_tgid=peer->status.namespace_tgids[peer->status.tgid_depth-1];
  if(Path(path,sizeof(path),"stat",static_cast<uint32_t>(credentials.pid))<0)return -1;
  char stat_text[16384];const ssize_t count=ReadFileAt(authority.proc.get(),path,stat_text,sizeof(stat_text));
  if(count<0)return -1;
  if(!ParseStartTicks(stat_text,static_cast<size_t>(count),credentials.pid,&peer->start_ticks))return Error(EBADMSG);
  if(Path(path,sizeof(path),"root",static_cast<uint32_t>(credentials.pid))<0)return -1;
  // Following this proc magic link gives the peer's held root/mount view.
  // No setns/chroot or string substitution is used.
  peer->root.reset(openat(authority.proc.get(),path,O_PATH|O_DIRECTORY|O_CLOEXEC));
  if(peer->root.get()<0||fstat(peer->root.get(),&peer->root_identity)<0)return -1;
  peer->proc.reset(openat(peer->root.get(),"proc",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));
  if(peer->proc.get()<0||VerifyProcView(peer->proc.get(),peer->pidns_identity)<0)return -1;
  if(Path(path,sizeof(path),"status",peer->visible_tgid)<0)return -1;
  ProcessStatus in_view{};
  if(ReadStatus(peer->proc.get(),path,&in_view)<0)return -1;
  if(in_view.tgid_depth!=1||in_view.tgid!=peer->visible_tgid||
     in_view.namespace_pids[0]!=peer->visible_tgid||
     !Unprivileged(in_view,credentials.uid,credentials.gid))return Error(EXDEV);
  const int n=snprintf(path,sizeof(path),"%u/task/%u/status",peer->visible_tgid,request.caller_tid);
  if(n<=0||static_cast<size_t>(n)>=sizeof(path))return Error(EOVERFLOW);
  ProcessStatus caller{};
  if(ReadStatus(peer->proc.get(),path,&caller)<0)return -1;
  if(caller.tgid_depth!=1||caller.tgid!=peer->visible_tgid||
     caller.namespace_pids[0]!=request.caller_tid||
     !Unprivileged(caller,credentials.uid,credentials.gid))return Error(EXDEV);
  return Alive(pidfd)?0:-1;
}
int RecheckPeer(const Authority& authority,const Peer& peer) {
  if(OwnerLive(authority)<0||!Alive(peer.pidfd.get()))return -1;
  Fd userns(ioctl(peer.pidfd.get(),kPidfdUserNamespace,0UL));
  Fd pidns(ioctl(peer.pidfd.get(),kPidfdPidNamespace,0UL));
  if(userns.get()<0||pidns.get()<0||InitialUserNamespace(userns.get())<0||
     SameNamespace(pidns.get(),peer.pidns_identity,CLONE_NEWPID)<0)return -1;
  char path[80];
  if(Path(path,sizeof(path),"status",static_cast<uint32_t>(peer.credentials.pid))<0)return -1;
  ProcessStatus status{};
  if(ReadStatus(authority.proc.get(),path,&status)<0)return -1;
  if(!SameAuthority(status,peer.status))return Error(ESTALE);
  if(Path(path,sizeof(path),"root",static_cast<uint32_t>(peer.credentials.pid))<0)return -1;
  Fd root(openat(authority.proc.get(),path,O_PATH|O_DIRECTORY|O_CLOEXEC));
  struct stat root_identity{};
  if(root.get()<0||fstat(root.get(),&root_identity)<0)return -1;
  if(!SameInode(root_identity,peer.root_identity))return Error(ESTALE);
  if(Path(path,sizeof(path),"stat",static_cast<uint32_t>(peer.credentials.pid))<0)return -1;
  char text[16384];const ssize_t size=ReadFileAt(authority.proc.get(),path,text,sizeof(text));
  uint64_t ticks=0;
  if(size<0)return -1;
  if(!ParseStartTicks(text,static_cast<size_t>(size),peer.credentials.pid,&ticks)||ticks!=peer.start_ticks)
    return Error(ESTALE);
  return Alive(peer.pidfd.get())?0:-1;
}
void StoreMetadata(const struct stat& source,const p::KernelStatfs& fs,p::Origin* origin) {
  auto* w=origin->words;
  w[p::kStatDevice]=source.st_dev;w[p::kStatInode]=source.st_ino;
  w[p::kStatMode]=source.st_mode;w[p::kStatNlink]=source.st_nlink;
  w[p::kStatUid]=source.st_uid;w[p::kStatGid]=source.st_gid;w[p::kStatRdev]=source.st_rdev;
  w[p::kStatSize]=static_cast<uint64_t>(source.st_size);
  w[p::kStatBlockSize]=static_cast<uint64_t>(source.st_blksize);
  w[p::kStatBlocks]=static_cast<uint64_t>(source.st_blocks);
  w[p::kStatAtimeSeconds]=static_cast<uint64_t>(source.st_atim.tv_sec);
  w[p::kStatAtimeNanoseconds]=static_cast<uint64_t>(source.st_atim.tv_nsec);
  w[p::kStatMtimeSeconds]=static_cast<uint64_t>(source.st_mtim.tv_sec);
  w[p::kStatMtimeNanoseconds]=static_cast<uint64_t>(source.st_mtim.tv_nsec);
  w[p::kStatCtimeSeconds]=static_cast<uint64_t>(source.st_ctim.tv_sec);
  w[p::kStatCtimeNanoseconds]=static_cast<uint64_t>(source.st_ctim.tv_nsec);
  w[p::kFsType]=fs.f_type;w[p::kFsBlockSize]=fs.f_bsize;
  w[p::kFsBlocks]=fs.f_blocks;w[p::kFsBlocksFree]=fs.f_bfree;
  w[p::kFsBlocksAvailable]=fs.f_bavail;w[p::kFsFiles]=fs.f_files;w[p::kFsFilesFree]=fs.f_ffree;
  w[p::kFsId0]=fs.f_fsid[0];w[p::kFsId1]=fs.f_fsid[1];
  w[p::kFsNameLength]=fs.f_namelen;w[p::kFsFragmentSize]=fs.f_frsize;w[p::kFsFlags]=fs.f_flags;
  for(unsigned i=0;i<4;++i)w[p::kFsSpare0+i]=fs.f_spare[i];
}
int MakeSnapshot(const Authority& authority,const Peer& peer,const p::CreateRequest& request,
                 int source_fd,int input_fd,uint64_t deadline) {
  struct stat source{},canonical{},input{};
  p::KernelStatfs source_fs{},input_fs{};
  if(fstat(source_fd,&source)<0||syscall(SYS_fstatfs,static_cast<long>(source_fd),&source_fs)<0||
     fstat(input_fd,&input)<0||syscall(SYS_fstatfs,static_cast<long>(input_fd),&input_fs)<0)return -1;
  const int source_flags=fcntl(source_fd,F_GETFL),input_flags=fcntl(input_fd,F_GETFL);
  if(source_flags<0||input_flags<0)return -1;
  if(static_cast<uint32_t>(source_flags)!=request.source_flags||
     (source_flags&(O_ACCMODE|O_PATH))!=O_RDONLY||source.st_mode!=(S_IFREG|0444)||
     source_fs.f_type!=PROC_SUPER_MAGIC)return Error(EINVAL);
  char path[80];
  if(Path(path,sizeof(path),"maps",peer.visible_tgid)<0)return -1;
  Fd canonical_fd(openat(peer.proc.get(),path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW));
  if(canonical_fd.get()<0||fstat(canonical_fd.get(),&canonical)<0)return -1;
  if(!SameInode(source,canonical)||source.st_mode!=canonical.st_mode||
     source.st_uid!=canonical.st_uid||source.st_gid!=canonical.st_gid)return Error(ESTALE);
  const int seals=fcntl(input_fd,F_GET_SEALS);
  if(seals<0)return -1;
  if(!S_ISREG(input.st_mode)||input_fs.f_type!=TMPFS_MAGIC||input.st_nlink!=0||
     input.st_uid!=peer.credentials.uid||input.st_gid!=peer.credentials.gid||
     input.st_size<=0||static_cast<uint64_t>(input.st_size)!=request.payload_size||
     (input_flags&O_PATH)||(input_flags&O_ACCMODE)==O_WRONLY||
     (seals&p::kRequiredSeals)!=p::kRequiredSeals)return Error(EINVAL);
  Fd output(static_cast<int>(syscall(SYS_memfd_create,p::kSnapshotName,
                                    static_cast<unsigned long>(MFD_CLOEXEC|MFD_ALLOW_SEALING))));
  if(output.get()<0)return -1;
  char buffer[65536];uint64_t offset=0;
  while(offset<request.payload_size) {
    const uint64_t now=Now();
    if(now==0||now>=deadline||OwnerLive(authority)<0||!Alive(peer.pidfd.get()))return Error(ETIMEDOUT);
    size_t wanted=sizeof(buffer);
    if(request.payload_size-offset<wanted)wanted=static_cast<size_t>(request.payload_size-offset);
    const ssize_t count=pread(input_fd,buffer,wanted,static_cast<off_t>(offset));
    if(count<0){if(errno==EINTR)continue;return -1;}
    if(count==0)return Error(EIO);
    size_t written=0;
    while(written<static_cast<size_t>(count)) {
      const ssize_t amount=write(output.get(),buffer+written,static_cast<size_t>(count)-written);
      if(amount<0){if(errno==EINTR)continue;return -1;}
      if(amount==0)return Error(EIO);
      written+=static_cast<size_t>(amount);
    }
    offset+=static_cast<uint64_t>(count);
  }
  struct stat backing{};struct statfs backing_fs{};
  if(fstat(output.get(),&backing)<0||fstatfs(output.get(),&backing_fs)<0)return -1;
  if(backing.st_uid||backing.st_gid||backing.st_nlink||
     static_cast<uint64_t>(backing.st_size)!=request.payload_size||
     static_cast<uint64_t>(backing_fs.f_type)!=TMPFS_MAGIC)return Error(EPROTO);
  p::Origin origin{};
  origin.words[p::kFactoryUsernsDevice]=p::kTrustedUserNamespaceDevice;
  origin.words[p::kFactoryUsernsInode]=p::kTrustedUserNamespaceInode;
  origin.words[p::kBackingDevice]=backing.st_dev;origin.words[p::kBackingInode]=backing.st_ino;
  origin.words[p::kBackingSize]=request.payload_size;
  origin.words[p::kOriginTgid]=peer.visible_tgid;origin.words[p::kOriginStartTicks]=peer.start_ticks;
  StoreMetadata(source,source_fs,&origin);
  const int path_size=snprintf(origin.path,sizeof(origin.path),"/proc/%u/maps",peer.visible_tgid);
  if(path_size<=0||static_cast<size_t>(path_size)>=sizeof(origin.path))return Error(EOVERFLOW);
  origin.path_size=static_cast<size_t>(path_size);
  unsigned char tag[p::kMaxTagBytes];
  const size_t tag_size=p::EncodeOrigin(origin,tag,sizeof(tag));
  if(!tag_size)return Error(EBADMSG);
  if(fsetxattr(output.get(),p::kTagName,tag,tag_size,XATTR_CREATE)<0||
     fchmod(output.get(),0444)<0||fcntl(output.get(),F_ADD_SEALS,p::kRequiredSeals)<0)return -1;
  // This is the factory's own held fdtable. Reopen through thread-self and
  // verify the resulting object, not /proc/self/fd of a different owner.
  Fd directory(open("/proc/thread-self/fd",O_PATH|O_DIRECTORY|O_CLOEXEC));
  struct statfs directory_fs{};
  if(directory.get()<0||fstatfs(directory.get(),&directory_fs)<0)return -1;
  if(static_cast<uint64_t>(directory_fs.f_type)!=PROC_SUPER_MAGIC)return Error(EXDEV);
  char number[32];const int n=snprintf(number,sizeof(number),"%d",output.get());
  if(n<=0||static_cast<size_t>(n)>=sizeof(number))return Error(EOVERFLOW);
  Fd readable(openat(directory.get(),number,source_flags|O_CLOEXEC));
  struct stat final_info{};
  if(readable.get()<0||fstat(readable.get(),&final_info)<0)return -1;
  if(!SameInode(backing,final_info)||final_info.st_mode!=(S_IFREG|0444)||final_info.st_uid||final_info.st_gid||
     final_info.st_nlink||final_info.st_size!=backing.st_size||
     fcntl(readable.get(),F_GET_SEALS)!=static_cast<int>(p::kRequiredSeals)||
     fcntl(readable.get(),F_GETFL)!=source_flags||fcntl(readable.get(),F_GETFD)!=FD_CLOEXEC||
     lseek(readable.get(),0,SEEK_CUR)!=0)return Error(EPROTO);
  unsigned char observed[p::kMaxTagBytes];
  const ssize_t tag_read=fgetxattr(readable.get(),p::kTagName,observed,sizeof(observed));
  if(tag_read<0)return -1;
  if(static_cast<size_t>(tag_read)!=tag_size||memcmp(observed,tag,tag_size))return Error(ESTALE);
  if(RecheckPeer(authority,peer)<0)return -1;
  return readable.release();
}
struct Rights {
  int values[16];size_t count=0;
  Rights(){for(int& value:values)value=-1;}
  ~Rights(){const int saved=errno;for(int value:values)if(value>=0)close(value);errno=saved;}
};
int Receive(const Authority& authority,int connection,p::CreateRequest* request,Rights* rights,uint64_t deadline) {
  for(;;) {
    if(Wait(authority,connection,POLLIN,-1,deadline)<0)return -1;
    unsigned char bytes[p::kRequestBytes];
    union{struct cmsghdr alignment;unsigned char bytes[CMSG_SPACE(16*sizeof(int))];} control{};
    struct iovec iov{bytes,sizeof(bytes)};struct msghdr message{};
    message.msg_iov=&iov;message.msg_iovlen=1;
    message.msg_control=control.bytes;message.msg_controllen=sizeof(control.bytes);
    const ssize_t count=recvmsg(connection,&message,MSG_DONTWAIT|MSG_CMSG_CLOEXEC|MSG_TRUNC);
    if(count<0){if(errno==EINTR||errno==EAGAIN||errno==EWOULDBLOCK)continue;return -1;}
    bool valid=count==sizeof(bytes)&&!(message.msg_flags&(MSG_TRUNC|MSG_CTRUNC));
    size_t headers=0;
    for(struct cmsghdr* header=CMSG_FIRSTHDR(&message);header;header=CMSG_NXTHDR(&message,header)) {
      ++headers;
      if(header->cmsg_level!=SOL_SOCKET||header->cmsg_type!=SCM_RIGHTS||header->cmsg_len<CMSG_LEN(0)){
        valid=false;continue;
      }
      const size_t size=header->cmsg_len-CMSG_LEN(0);
      if(size%sizeof(int))valid=false;
      for(size_t i=0;i<size/sizeof(int);++i) {
        int fd;memcpy(&fd,CMSG_DATA(header)+i*sizeof(int),sizeof(fd));
        if(rights->count<16)rights->values[rights->count++]=fd;
        else{close(fd);valid=false;}
      }
    }
    if(!valid||headers!=1||rights->count!=2||
       !p::DecodeCreateRequest(bytes,sizeof(bytes),request))return Error(EPROTO);
    for(size_t i=0;i<rights->count;++i) {
      const int flags=fcntl(rights->values[i],F_GETFD);
      if(flags<0||!(flags&FD_CLOEXEC))return Error(EPROTO);
    }
    return 0;
  }
}
int Send(const Authority& authority,int connection,int peer,uint32_t error,int fd,uint64_t deadline) {
  unsigned char reply[p::kReplyBytes];p::EncodeReply(error,reply);
  for(;;) {
    if(Wait(authority,connection,POLLOUT,peer,deadline)<0)return -1;
    union{struct cmsghdr alignment;unsigned char bytes[CMSG_SPACE(sizeof(int))];} control{};
    struct iovec iov{reply,sizeof(reply)};struct msghdr message{};
    message.msg_iov=&iov;message.msg_iovlen=1;
    if(fd>=0) {
      message.msg_control=control.bytes;message.msg_controllen=sizeof(control.bytes);
      struct cmsghdr* header=CMSG_FIRSTHDR(&message);
      header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
      header->cmsg_len=CMSG_LEN(sizeof(fd));memcpy(CMSG_DATA(header),&fd,sizeof(fd));
    }
    const ssize_t sent=sendmsg(connection,&message,MSG_DONTWAIT|MSG_NOSIGNAL);
    if(sent<0){if(errno==EINTR||errno==EAGAIN||errno==EWOULDBLOCK)continue;return -1;}
    return sent==sizeof(reply)?0:Error(EPROTO);
  }
}
void ServeOne(const Authority& authority,int connection) {
  const uint64_t now=Now();
  if(!now||now>UINT64_MAX-kRequestNanos)return;
  const uint64_t deadline=now+kRequestNanos;
  Rights rights;p::CreateRequest request{};Peer peer;Fd output;
  int result=Receive(authority,connection,&request,&rights,deadline);
  if(result==0)result=CapturePeer(authority,connection,request,&peer);
  if(result==0) {
    output.reset(MakeSnapshot(authority,peer,request,rights.values[0],rights.values[1],deadline));
    result=output.get()<0?-1:0;
  }
  const int error=result<0?errno:0;
  const uint32_t bounded_error=error>0&&error<=4095?static_cast<uint32_t>(error):static_cast<uint32_t>(EIO);
  // No payload/path, App maps, or App-controlled text is logged.
  (void)Send(authority,connection,peer.pidfd.get(),result<0?bounded_error:0,output.get(),deadline);
}
int Ready(const Authority& authority) {
  unsigned char wire[40]{};
  memcpy(wire,"DP4RDY02",8);p::PutU32(wire+8,p::kVersion);p::PutU32(wire+12,sizeof(wire));
  p::PutU32(wire+16,static_cast<uint32_t>(getpid()));
  p::PutU64(wire+24,p::kTrustedUserNamespaceDevice);p::PutU64(wire+32,p::kTrustedUserNamespaceInode);
  if(OwnerLive(authority)<0)return -1;
  const ssize_t result=send(authority.control.get(),wire,sizeof(wire),MSG_DONTWAIT|MSG_NOSIGNAL);
  return result==sizeof(wire)?0:Error(EPROTO);
}
int Run(int listener,int control,uint32_t low,uint32_t high) {
  Authority authority;
  if(Prepare(&authority,listener,control,low,high)<0||Ready(authority)<0)return -1;
  for(;;) {
    struct pollfd items[3]={
      {authority.listener.get(),POLLIN,0},
      {authority.control.get(),static_cast<short>(POLLIN|POLLRDHUP),0},
      {authority.owner_pidfd.get(),POLLIN,0}};
    const int count=poll(items,3,1000);
    if(count<0){if(errno==EINTR)continue;return -1;}
    if(items[1].revents||items[2].revents)return 0;
    if(items[0].revents&kDead)return Error(EPIPE);
    if(!(items[0].revents&POLLIN))continue;
    Fd connection(accept4(authority.listener.get(),nullptr,nullptr,SOCK_CLOEXEC|SOCK_NONBLOCK));
    if(connection.get()<0){if(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR)continue;return -1;}
    ServeOne(authority,connection.get());
    if(OwnerLive(authority)<0)return 0;
  }
}
}  // namespace
}  // namespace droidloom::proc_maps_factory
int main(int argc,char** argv) {
  using namespace droidloom::proc_maps_factory;
  if(argc==1) {
    puts("{\"state\":\"DISABLED_REQUIRES_PINNED_INHERITED_OWNER\",\"protocol\":2,\"service_started\":false,\"production_ready\":false}");
    return 0;
  }
  if(argc!=6||strcmp(argv[1],"--serve-inherited"))return 64;
  uint64_t values[4]{};
  for(unsigned i=0;i<4;++i)
    if(!ParseDecimal(argv[2+i],strlen(argv[2+i]),INT_MAX,&values[i]))return 64;
  if(values[0]<3||values[1]<3||values[0]==values[1]||values[2]==0||values[2]>values[3])return 64;
  const int result=Run(static_cast<int>(values[0]),static_cast<int>(values[1]),
                       static_cast<uint32_t>(values[2]),static_cast<uint32_t>(values[3]));
  if(result<0){fprintf(stderr,"proc-maps V2 factory stopped: errno=%d\n",errno);return 1;}
  return 0;
}
