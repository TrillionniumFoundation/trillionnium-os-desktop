// SPDX-License-Identifier: Apache-2.0
// Owned host fixture client. No default connection, service or namespace action.
// Link this file against the exact combined candidate's actual implementation.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "berberis/kernel_api/proc_maps_provenance.h"
#include "berberis/kernel_api/proc_maps_raw_metadata_owner.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <linux/magic.h>
#include <linux/nsfs.h>
#include <sys/ioctl.h>
#include <linux/memfd.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <sys/xattr.h>
#include <time.h>
#include <unistd.h>

namespace p=berberis::proc_maps_provenance;
namespace raw=p::raw_metadata_owner;
extern "C" void FixtureBionicBranchView(const void*,void*);
namespace {
constexpr uid_t kClientUid=61171;
constexpr uid_t kDeniedUid=61172;
constexpr char kPayload[]="owned Pocket4 V2 factory control; no application maps payload\n";
class Fd {
 public:
  explicit Fd(int n=-1):n_(n){}
  ~Fd(){reset();}
  Fd(const Fd&)=delete;Fd& operator=(const Fd&)=delete;
  int get()const{return n_;}
  void reset(int n=-1){const int e=errno;if(n_>=0)close(n_);n_=n;errno=e;}
  int release(){int n=n_;n_=-1;return n;}
 private:int n_;
};
uint64_t Now(){timespec v{};if(clock_gettime(CLOCK_MONOTONIC,&v)<0)return 0;
 return static_cast<uint64_t>(v.tv_sec)*1000000000ULL+static_cast<uint64_t>(v.tv_nsec);}
int CountFds(){DIR* d=opendir("/proc/thread-self/fd");if(!d)return -1;
 int count=0;const int own=dirfd(d);errno=0;
 while(dirent* e=readdir(d)) {char* end=nullptr;long n=strtol(e->d_name,&end,10);
  if(end!=e->d_name&&*end=='\0'&&n!=own)++count;}
 const int saved=errno;closedir(d);if(saved){errno=saved;return -1;}return count;}
bool SameStat(const struct stat& a,const struct stat& b) {
 return a.st_dev==b.st_dev&&a.st_ino==b.st_ino&&a.st_mode==b.st_mode&&a.st_nlink==b.st_nlink&&
 a.st_uid==b.st_uid&&a.st_gid==b.st_gid&&a.st_rdev==b.st_rdev&&a.st_size==b.st_size&&
 a.st_blksize==b.st_blksize&&a.st_blocks==b.st_blocks&&
 a.st_atim.tv_sec==b.st_atim.tv_sec&&a.st_atim.tv_nsec==b.st_atim.tv_nsec&&
 a.st_mtim.tv_sec==b.st_mtim.tv_sec&&a.st_mtim.tv_nsec==b.st_mtim.tv_nsec&&
 a.st_ctim.tv_sec==b.st_ctim.tv_sec&&a.st_ctim.tv_nsec==b.st_ctim.tv_nsec;
}
void Hex(const void* source,size_t size,char* text){const auto* b=static_cast<const unsigned char*>(source);
 const char digits[]="0123456789abcdef";for(size_t i=0;i<size;++i){text[2*i]=digits[b[i]>>4];text[2*i+1]=digits[b[i]&15];}text[2*size]=0;}
struct Result {
 const char* name="";bool pass=false;int stage=0,error=0;
 int uid=-1,gid=-1,visible_tgid=-1,start=-99,stop=-99,rights=-1,reply_error=-1;
 int fd_before=-1,fd_after=-1;bool request_sent=false,wire_valid=false;
 bool input_observed=false,new_inode=false,root_inode=false,sealed=false,input_unchanged=false,payload_equal=false;
 bool source_metadata=false,query_virtual=false,projected_stat=false,projected_raw=false;
 bool projected_libc=false,guest_copy=false,errno_preserved=false,bionic_branch=false;
 uint64_t elapsed_ns=0,raw_flags=0,libc_flags=0,bionic_flags=0;
 char raw_bytes[241]{},libc_bytes[241]{},bionic_bytes[241]{};
 char namespace_diagnostic[4096]="null";
 bool Fail(int s,int e){stage=s;error=e;return false;}
};

// Failure-only observations of this owned client's existing credentials and
// the exact namespace syscalls. No credential, policy, namespace or guard change.
void DiagnoseInitialNamespace(Result* r) {
 const int primary_errno=errno;
 uid_t real=static_cast<uid_t>(-1),effective=real,saved=real;
 gid_t greal=static_cast<gid_t>(-1),geffective=greal,gsaved=greal;
 errno=0;const int uid_rc=getresuid(&real,&effective,&saved);const int uid_errno=uid_rc<0?errno:0;
 errno=0;const int gid_rc=getresgid(&greal,&geffective,&gsaved);const int gid_errno=gid_rc<0?errno:0;
 errno=0;const long fsuid=syscall(SYS_setfsuid,static_cast<uid_t>(-1));const int fsuid_errno=errno;
 errno=0;const long fsgid=syscall(SYS_setfsgid,static_cast<gid_t>(-1));const int fsgid_errno=errno;
 struct __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
 struct __user_cap_data_struct caps[2]{};
 errno=0;const long cap_rc=syscall(SYS_capget,&header,caps);const int cap_errno=cap_rc<0?errno:0;
 errno=0;const long dumpable=syscall(SYS_prctl,3,0,0,0,0);const int dump_errno=dumpable<0?errno:0;
 errno=0;const long seccomp=syscall(SYS_prctl,21,0,0,0,0);const int seccomp_errno=seccomp<0?errno:0;
 errno=0;const long nnp=syscall(SYS_prctl,39,0,0,0,0);const int nnp_errno=nnp<0?errno:0;
 errno=0;const long securebits=syscall(SYS_prctl,27,0,0,0,0);const int securebits_errno=securebits<0?errno:0;
 const long tid=syscall(SYS_gettid);
 errno=0;Fd self(static_cast<int>(syscall(SYS_pidfd_open,tid,O_EXCL)));
 const int pidfd_errno=self.get()<0?errno:0;
 int ns_errno=0,stat_rc=-99,stat_errno=0,fs_rc=-99,fs_errno=0,kind=-99,kind_errno=0;
 Fd ns;struct stat info{};struct statfs fs{};
 if(self.get()>=0){errno=0;ns.reset(ioctl(self.get(),_IO(0xff,9),0));ns_errno=ns.get()<0?errno:0;}
 if(ns.get()>=0){
  errno=0;stat_rc=fstat(ns.get(),&info);stat_errno=stat_rc<0?errno:0;
  errno=0;fs_rc=fstatfs(ns.get(),&fs);fs_errno=fs_rc<0?errno:0;
  errno=0;kind=ioctl(ns.get(),NS_GET_NSTYPE,0);kind_errno=kind<0?errno:0;
 }
 const int n=snprintf(r->namespace_diagnostic,sizeof(r->namespace_diagnostic),
  "{\"observed_after_original_guard_failure\":true,\"primary_errno\":%d,"
  "\"getresuid\":{\"rc\":%d,\"errno\":%d,\"real\":%u,\"effective\":%u,\"saved\":%u},"
  "\"getresgid\":{\"rc\":%d,\"errno\":%d,\"real\":%u,\"effective\":%u,\"saved\":%u},"
  "\"fsuid\":%ld,\"fsuid_errno\":%d,\"fsgid\":%ld,\"fsgid_errno\":%d,"
  "\"capget\":{\"rc\":%ld,\"errno\":%d,\"effective\":[%u,%u],\"permitted\":[%u,%u],\"inheritable\":[%u,%u]},"
  "\"dumpable\":%ld,\"dumpable_errno\":%d,\"seccomp\":%ld,\"seccomp_errno\":%d,"
  "\"no_new_privs\":%ld,\"no_new_privs_errno\":%d,\"securebits\":%ld,\"securebits_errno\":%d,"
  "\"tid\":%ld,\"pidfd_thread\":%d,\"pidfd_errno\":%d,\"userns_fd\":%d,\"userns_errno\":%d,"
  "\"fstat_rc\":%d,\"fstat_errno\":%d,\"fstatfs_rc\":%d,\"fstatfs_errno\":%d,"
  "\"namespace_type\":%d,\"namespace_type_errno\":%d,\"namespace_device\":%llu,\"namespace_inode\":%llu,\"namespace_fs_type\":%llu}",
  primary_errno,uid_rc,uid_errno,real,effective,saved,gid_rc,gid_errno,greal,geffective,gsaved,
  fsuid,fsuid_errno,fsgid,fsgid_errno,cap_rc,cap_errno,
  caps[0].effective,caps[1].effective,caps[0].permitted,caps[1].permitted,caps[0].inheritable,caps[1].inheritable,
  dumpable,dump_errno,seccomp,seccomp_errno,nnp,nnp_errno,securebits,securebits_errno,
  tid,self.get(),pidfd_errno,ns.get(),ns_errno,stat_rc,stat_errno,fs_rc,fs_errno,kind,kind_errno,
  static_cast<unsigned long long>(info.st_dev),static_cast<unsigned long long>(info.st_ino),
  static_cast<unsigned long long>(fs.f_type));
 if(n<0||static_cast<size_t>(n)>=sizeof(r->namespace_diagnostic))
  strcpy(r->namespace_diagnostic,"{\"diagnostic_error\":\"bounded_format_failure\"}");
 errno=primary_errno;
}

int Connect(){Fd s(socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0));if(s.get()<0)return -1;
 timeval timeout{4,0};if(setsockopt(s.get(),SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout))<0||
 setsockopt(s.get(),SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))<0)return -1;
 sockaddr_un address{};address.sun_family=AF_UNIX;
 memcpy(address.sun_path+1,p::kSocketName,sizeof(p::kSocketName)-1);
 if(connect(s.get(),reinterpret_cast<sockaddr*>(&address),
 offsetof(sockaddr_un,sun_path)+sizeof(p::kSocketName))<0)return -1;
 return s.release();}
bool SendRequest(int socket,const unsigned char* bytes,size_t size,const int* fds,size_t count){
 if(count>17){errno=EINVAL;return false;}
 alignas(cmsghdr) unsigned char control[CMSG_SPACE(sizeof(int)*17)]{};
 iovec iov{const_cast<unsigned char*>(bytes),size};msghdr message{};
 message.msg_iov=&iov;message.msg_iovlen=1;
 if(count){message.msg_control=control;message.msg_controllen=CMSG_SPACE(count*sizeof(int));
  cmsghdr* h=CMSG_FIRSTHDR(&message);h->cmsg_level=SOL_SOCKET;h->cmsg_type=SCM_RIGHTS;
  h->cmsg_len=CMSG_LEN(count*sizeof(int));memcpy(CMSG_DATA(h),fds,count*sizeof(int));}
 const ssize_t n=sendmsg(socket,&message,MSG_NOSIGNAL);
 if(n<0)return false;
 if(static_cast<size_t>(n)!=size){errno=EPROTO;return false;}return true;
}
struct Reply {
 unsigned char bytes[p::kReplyBytes]{};Fd fd;int count=0,error=0;
 bool valid=false,eof=false;
 bool Receive(int socket){
  alignas(cmsghdr) unsigned char control[CMSG_SPACE(sizeof(int)*32)]{};
  iovec iov{bytes,sizeof(bytes)};msghdr message{};message.msg_iov=&iov;message.msg_iovlen=1;
  message.msg_control=control;message.msg_controllen=sizeof(control);
  const ssize_t n=recvmsg(socket,&message,MSG_CMSG_CLOEXEC|MSG_TRUNC);
  if(n<0)return false;
  eof=n==0;bool ancillary_ok=true;
  for(cmsghdr* h=CMSG_FIRSTHDR(&message);h;h=CMSG_NXTHDR(&message,h)){
   if(h->cmsg_level!=SOL_SOCKET||h->cmsg_type!=SCM_RIGHTS||h->cmsg_len<CMSG_LEN(0)){
    ancillary_ok=false;continue;}
   const size_t bytes_count=h->cmsg_len-CMSG_LEN(0);if(bytes_count%sizeof(int))ancillary_ok=false;
   for(size_t i=0;i+sizeof(int)<=bytes_count;i+=sizeof(int)){
    int received;memcpy(&received,CMSG_DATA(h)+i,sizeof(received));++count;
    if(count==1)fd.reset(received);else close(received);
   }
  }
  bool zero=true;for(size_t i=16;i<sizeof(bytes);++i)zero=zero&&bytes[i]==0;
  valid=n==sizeof(bytes)&&!(message.msg_flags&(MSG_TRUNC|MSG_CTRUNC))&&ancillary_ok&&zero&&
   memcmp(bytes,"DP4REP02",8)==0&&p::GetU32(bytes+8)==2;
  if(valid){const uint32_t e=p::GetU32(bytes+12);valid=e<=4095;error=static_cast<int>(e);}
  return true;
 }
};
bool ValidateSnapshot(Result* r,int output,int source,int input){
 struct stat backing{},original{},input_before{};p::KernelStatfs source_raw{},backing_raw{};
 struct statfs source_libc{};
 if(fstat(output,&backing)<0||fstat(source,&original)<0||
 syscall(SYS_fstatfs,static_cast<long>(source),&source_raw)<0||fstatfs(source,&source_libc)<0||
 syscall(SYS_fstatfs,static_cast<long>(output),&backing_raw)<0)return r->Fail(30,errno);
 r->root_inode=backing.st_uid==0&&backing.st_gid==0&&backing.st_mode==(S_IFREG|0444)&&backing.st_nlink==0;
 r->sealed=(fcntl(output,F_GET_SEALS)&p::kRequiredSeals)==static_cast<int>(p::kRequiredSeals);
 if(input>=0){r->input_observed=true;if(fstat(input,&input_before)<0)return r->Fail(31,errno);
  r->new_inode=backing.st_dev!=input_before.st_dev||backing.st_ino!=input_before.st_ino;
  char original_payload[sizeof(kPayload)]{};const ssize_t n=pread(input,original_payload,sizeof(original_payload),0);
  r->input_unchanged=input_before.st_uid==getuid()&&input_before.st_gid==getgid()&&
   input_before.st_size==sizeof(kPayload)-1&&n==sizeof(kPayload)-1&&
   memcmp(original_payload,kPayload,sizeof(kPayload)-1)==0;
 } // The high-level client's private input is not directly observed here.
 char observed[sizeof(kPayload)]{};const ssize_t n=pread(output,observed,sizeof(observed),0);
 r->payload_equal=n==sizeof(kPayload)-1&&memcmp(observed,kPayload,sizeof(kPayload)-1)==0&&
  backing.st_size==sizeof(kPayload)-1&&lseek(output,0,SEEK_CUR)==0;
 if(fcntl(output,F_GETFD)!=FD_CLOEXEC||fcntl(output,F_GETFL)!=fcntl(source,F_GETFL)||
  backing_raw.f_type!=TMPFS_MAGIC||!r->root_inode||!r->sealed||
  (r->input_observed&&(!r->new_inode||!r->input_unchanged))||!r->payload_equal)return r->Fail(32,EPROTO);
 unsigned char tag[p::kMaxTagBytes]{};const ssize_t tag_size=fgetxattr(output,p::kTagName,tag,sizeof(tag));
 p::Origin origin{};p::KernelStatfs tag_raw{};struct stat tag_stat{};
 if(tag_size<0)return r->Fail(33,errno);
 if(!p::DecodeOrigin(tag,static_cast<size_t>(tag_size),&origin)||!p::DecodeKernelStatfs(origin,&tag_raw)||
  !p::DecodeStat(origin,&tag_stat))return r->Fail(34,EBADMSG);
 char canonical[80];const int path_size=snprintf(canonical,sizeof(canonical),"/proc/%d/maps",getpid());
 r->source_metadata=SameStat(tag_stat,original)&&memcmp(&tag_raw,&source_raw,sizeof(tag_raw))==0&&
  origin.words[p::kOriginTgid]==static_cast<uint64_t>(getpid())&&
  origin.words[p::kBackingDevice]==backing.st_dev&&origin.words[p::kBackingInode]==backing.st_ino&&
  origin.path_size==static_cast<size_t>(path_size)&&memcmp(origin.path,canonical,origin.path_size)==0;
 if(!r->source_metadata)return r->Fail(35,EPROTO);
 r->raw_flags=source_raw.f_flags;r->libc_flags=static_cast<uint64_t>(source_libc.f_flags);
 Hex(&source_raw,sizeof(source_raw),r->raw_bytes);Hex(&source_libc,sizeof(source_libc),r->libc_bytes);
 p::KernelStatfs bionic{};FixtureBionicBranchView(&source_raw,&bionic);
 p::KernelStatfs expected=source_raw;expected.f_flags&=~0x20ULL;
 r->bionic_branch=memcmp(&expected,&bionic,sizeof(bionic))==0;
 r->bionic_flags=bionic.f_flags;Hex(&bionic,sizeof(bionic),r->bionic_bytes);
 r->start=raw::Start();if(r->start<0)return r->Fail(36,errno);
 p::Origin projected_origin{};struct stat projected{};struct statfs libc{};p::KernelStatfs kernel{},guest{};
 bool preserve=true;
 errno=241;r->query_virtual=p::QueryOrigin(output,p::kCandidateConfiguration,&projected_origin)==p::Lookup::kVirtual;
 preserve=preserve&&errno==241;
 errno=242;r->projected_stat=p::Fstat(output,&projected,p::kCandidateConfiguration)==0&&SameStat(projected,original);
 preserve=preserve&&errno==242;
 errno=243;r->projected_raw=p::FstatfsKernel(output,&kernel,p::kCandidateConfiguration)==0&&
  memcmp(&kernel,&source_raw,sizeof(kernel))==0;preserve=preserve&&errno==243;
 errno=244;r->projected_libc=p::Fstatfs(output,&libc,p::kCandidateConfiguration)==0&&
  memcmp(&libc,&source_libc,sizeof(libc))==0;preserve=preserve&&errno==244;
 errno=245;r->guest_copy=p::FstatfsForGuest(output,&guest,p::kCandidateConfiguration)==0&&
  memcmp(&guest,&source_raw,sizeof(guest))==0;preserve=preserve&&errno==245;
 r->errno_preserved=preserve;
 const int operation_error=errno;r->stop=raw::Stop();
 if(r->stop<0)return r->Fail(37,errno);
 if(!r->query_virtual||!r->projected_stat||!r->projected_raw||!r->projected_libc||
  !r->guest_copy||!r->errno_preserved||!r->bionic_branch)return r->Fail(38,operation_error);
 return true;
}
bool Known(const char* name){const char* values[]={"wire_snapshot","create_snapshot","short","long","v1", "rights0","rights1","rights3","rights17","unsealed","wrong_source","wrong_uid","timeout","peer_death","bad_reply"};
 for(const char* s:values)if(!strcmp(name,s))return true;
 return false;}
bool Run(Result* r){
 const char* name=r->name;r->uid=static_cast<int>(getuid());r->gid=static_cast<int>(getgid());
 r->visible_tgid=getpid();
 if((getuid()!=kClientUid&&getuid()!=kDeniedUid)||getgid()!=getuid()||
  p::RequireUnprivilegedInitialNamespace(p::kCandidateConfiguration)<0){
  const int original_error=errno?errno:EPERM;DiagnoseInitialNamespace(r);return r->Fail(1,original_error);}
 Fd source(open(!strcmp(name,"wrong_source")?"/proc/self/status":"/proc/self/maps",O_RDONLY|O_CLOEXEC));
 if(source.get()<0)return r->Fail(2,errno);
 if(!strcmp(name,"create_snapshot")||!strcmp(name,"bad_reply")){
  errno=0;Fd output(p::CreateSnapshot(source.get(),kPayload,sizeof(kPayload)-1,p::kCandidateConfiguration,FD_CLOEXEC));
  const int e=errno;
  if(!strcmp(name,"bad_reply")){r->reply_error=e;return output.get()<0&&e==EPROTO?true:r->Fail(3,e);}
  if(output.get()<0)return r->Fail(4,e);
  return ValidateSnapshot(r,output.get(),source.get(),-1);
 }
 Fd input(static_cast<int>(syscall(SYS_memfd_create,"owned-v2-fixture-input",static_cast<unsigned long>(MFD_CLOEXEC|MFD_ALLOW_SEALING))));
 if(input.get()<0)return r->Fail(5,errno);
 if(write(input.get(),kPayload,sizeof(kPayload)-1)!=sizeof(kPayload)-1)return r->Fail(6,errno);
 if(strcmp(name,"unsealed")&&fcntl(input.get(),F_ADD_SEALS,p::kRequiredSeals)<0)return r->Fail(7,errno);
 Fd connection(Connect());if(connection.get()<0)return r->Fail(8,errno);
 if(!strcmp(name,"timeout")){
  const uint64_t before=Now();Reply reply;if(!reply.Receive(connection.get()))return r->Fail(9,errno);
  r->elapsed_ns=Now()-before;r->rights=reply.count;
  return reply.eof&&reply.count==0&&r->elapsed_ns>=1500000000ULL&&r->elapsed_ns<=4500000000ULL?true:r->Fail(10,EPROTO);
 }
 unsigned char bytes[p::kRequestBytes+1]{};
 p::CreateRequest fields{sizeof(kPayload)-1,static_cast<uint32_t>(syscall(SYS_gettid)),
  static_cast<uint32_t>(fcntl(source.get(),F_GETFL)),FD_CLOEXEC};
 if(!p::EncodeCreateRequest(fields,bytes))return r->Fail(11,EINVAL);
 size_t size=p::kRequestBytes,count=2;int expected=EPROTO;
 if(!strcmp(name,"short"))--size;
 if(!strcmp(name,"long"))++size;
 if(!strcmp(name,"v1")){memcpy(bytes,"DP4REQ01",8);p::PutU32(bytes+8,1);}
 if(!strcmp(name,"rights0"))count=0;
 if(!strcmp(name,"rights1"))count=1;
 if(!strcmp(name,"rights3"))count=3;
 if(!strcmp(name,"rights17"))count=17;
 if(!strcmp(name,"unsealed"))expected=EINVAL;
 if(!strcmp(name,"wrong_source"))expected=ESTALE;
 if(!strcmp(name,"wrong_uid"))expected=EPERM;
 int fds[17];fds[0]=source.get();for(size_t i=1;i<17;++i)fds[i]=input.get();
 if(!SendRequest(connection.get(),bytes,size,fds,count))return r->Fail(12,errno);
 r->request_sent=true;if(!strcmp(name,"peer_death"))return true;
 Reply reply;if(!reply.Receive(connection.get()))return r->Fail(13,errno);
 r->rights=reply.count;r->reply_error=reply.error;r->wire_valid=reply.valid;
 if(!strcmp(name,"wire_snapshot")){
  if(!reply.valid||reply.error||reply.count!=1||reply.fd.get()<0)return r->Fail(14,reply.valid?reply.error:EPROTO);
  return ValidateSnapshot(r,reply.fd.get(),source.get(),input.get());
 }
 return reply.valid&&reply.count==0&&reply.error==expected?true:r->Fail(15,reply.valid?reply.error:EPROTO);
}
void Print(const Result& r){
 printf("{\"schema\":\"pocket4-owned-factory-client-v1\",\"case\":\"%s\",\"pass\":%s,\"stage\":%d,\"errno\":%d,"
 "\"uid\":%d,\"gid\":%d,\"visible_tgid\":%d,\"start\":%d,\"stop\":%d,\"rights\":%d,\"reply_errno\":%d,"
 "\"fd_before\":%d,\"fd_after\":%d,\"request_sent\":%s,\"wire_valid\":%s,"
 "\"input_observed\":%s,\"new_inode\":%s,\"root_inode\":%s,\"sealed\":%s,\"input_unchanged\":%s,\"payload_equal\":%s,"
 "\"source_metadata\":%s,\"query_virtual\":%s,\"projected_stat\":%s,\"projected_raw\":%s,"
 "\"projected_libc\":%s,\"guest_copy\":%s,\"errno_preserved\":%s,\"bionic_branch_fixture\":%s,"
 "\"bionic_api_executed\":false,\"elapsed_ns\":%llu,\"raw_flags\":%llu,\"libc_flags\":%llu,\"bionic_flags\":%llu,"
 "\"raw120\":\"%s\",\"libc120\":\"%s\",\"bionic_branch120\":\"%s\",\"namespace_diagnostic\":%s}\n",
 r.name,r.pass?"true":"false",r.stage,r.error,r.uid,r.gid,r.visible_tgid,r.start,r.stop,r.rights,r.reply_error,
 r.fd_before,r.fd_after,r.request_sent?"true":"false",r.wire_valid?"true":"false",r.input_observed?"true":"false",r.new_inode?"true":"false",
 r.root_inode?"true":"false",r.sealed?"true":"false",r.input_unchanged?"true":"false",r.payload_equal?"true":"false",
 r.source_metadata?"true":"false",r.query_virtual?"true":"false",r.projected_stat?"true":"false",
 r.projected_raw?"true":"false",r.projected_libc?"true":"false",r.guest_copy?"true":"false",
 r.errno_preserved?"true":"false",r.bionic_branch?"true":"false",
 static_cast<unsigned long long>(r.elapsed_ns),static_cast<unsigned long long>(r.raw_flags),
 static_cast<unsigned long long>(r.libc_flags),static_cast<unsigned long long>(r.bionic_flags),
 r.raw_bytes,r.libc_bytes,r.bionic_bytes,r.namespace_diagnostic);fflush(stdout);
}
}
int main(int argc,char** argv){
 if(argc==1){puts("{\"state\":\"PLAN_ONLY\",\"service_started\":false}");return 0;}
 if(argc!=3||strcmp(argv[1],"--owned-client")||!Known(argv[2]))return 64;
 Result result;result.name=argv[2];result.fd_before=CountFds();
 result.pass=result.fd_before>=0&&Run(&result);
 if(result.start==0&&result.stop==-99)result.stop=raw::Stop();
 result.fd_after=CountFds();
 if(result.fd_before<0||result.fd_after!=result.fd_before)result.pass=result.Fail(90,EPROTO);
 Print(result);return result.pass?0:1;
}
