// Derived control: real socketpair delivery, no recvmsg or poll seam. Listener inheritance remains untested.
// Independent owned local control: invoke the exact candidate Receive function.
// Does not call Prepare/Run, launch a factory service, or enter any namespace.
#define main candidate_factory_disabled_main
#include "/workspace/scratch/94990735b266/native-new-env-01/factory-v2-r1/source/factory_main.cc"
#undef main
#include <dirent.h>
#include <set>
#include <string>
#include <sys/utsname.h>

namespace {
using namespace droidloom::proc_maps_factory;
std::set<int> SnapshotFds() {
  DIR* directory=opendir("/proc/thread-self/fd");
  if(!directory){perror("opendir");exit(70);}
  const int own=dirfd(directory);
  std::set<int> result;
  while(dirent* entry=readdir(directory)) {
    char* end=nullptr;long fd=strtol(entry->d_name,&end,10);
    if(end!=entry->d_name && *end==0 && fd>=0 && fd<=INT_MAX && fd!=own)
      result.insert(static_cast<int>(fd));
  }
  closedir(directory);return result;
}
void Must(bool ok,const char* operation) {
  if(!ok){perror(operation);exit(70);}
}
bool RunOne(bool pass_pidfd) {
  Authority authority;
  int control[2];
  Must(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_NONBLOCK|SOCK_CLOEXEC,0,control)==0,"control socketpair");
  authority.control.reset(control[0]);Fd keep_control(control[1]);
  authority.owner_pidfd.reset(static_cast<int>(syscall(SYS_pidfd_open,getpid(),0)));
  Must(authority.owner_pidfd.get()>=0,"own pidfd");

  int request_pair[2];
  Must(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_NONBLOCK|SOCK_CLOEXEC,0,request_pair)==0,"request socketpair");
  Fd connection(request_pair[0]),client(request_pair[1]);
  const int enabled=pass_pidfd?1:0;
  Must(setsockopt(connection.get(),SOL_SOCKET,76,&enabled,sizeof(enabled))==0,"SO_PASSPIDFD");
  const int validate_result=ValidateSocket(connection.get(),false);
  Must(validate_result==0,"actual ValidateSocket nonlistener");
  int inherited=-1;socklen_t inherited_size=sizeof(inherited);
  Must(getsockopt(connection.get(),SOL_SOCKET,76,&inherited,&inherited_size)==0,"receiver option");
  Must(inherited_size==sizeof(inherited) && inherited==enabled,"receiver option exact");

  Fd input(open("/dev/null",O_RDONLY|O_CLOEXEC));
  Must(input.get()>=0,"own input");
  p::CreateRequest request{};
  request.payload_size=1;request.caller_tid=static_cast<uint32_t>(syscall(SYS_gettid));
  request.source_flags=O_RDONLY;request.original_fd_flags=FD_CLOEXEC;
  unsigned char packet[p::kRequestBytes];
  Must(p::EncodeCreateRequest(request,packet),"request encode");
  union {cmsghdr alignment;unsigned char bytes[CMSG_SPACE(2*sizeof(int))];} ancillary{};
  iovec vector{packet,sizeof(packet)};msghdr message{};
  message.msg_iov=&vector;message.msg_iovlen=1;
  message.msg_control=ancillary.bytes;message.msg_controllen=sizeof(ancillary.bytes);
  cmsghdr* header=CMSG_FIRSTHDR(&message);
  header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
  header->cmsg_len=CMSG_LEN(2*sizeof(int));
  const int sent[2]={input.get(),input.get()};memcpy(CMSG_DATA(header),sent,sizeof(sent));
  Must(sendmsg(client.get(),&message,MSG_NOSIGNAL)==sizeof(packet),"send request");
  const auto before=SnapshotFds();
  int result,error;size_t adopted;
  {
    Rights received;p::CreateRequest decoded{};
    errno=0;result=Receive(authority,connection.get(),&decoded,&received,Now()+kRequestNanos);
    error=errno;adopted=received.count;
  }
  const auto after=SnapshotFds();
  size_t added=0,pidfds=0;
  for(int fd:after)if(!before.count(fd)) {
    ++added;char path[64],target[256];
    snprintf(path,sizeof(path),"/proc/thread-self/fd/%d",fd);
    const ssize_t n=readlink(path,target,sizeof(target)-1);
    if(n>=0){target[n]=0;if(std::string(target)=="anon_inode:[pidfd]")++pidfds;}
    close(fd);  // Close only actual newly installed objects from this request.
  }
  const bool restored=SnapshotFds()==before;
  const bool observed=pass_pidfd?(result==-1 && error==EPROTO && added==1 && pidfds==1):
                               (result==0 && added==0);
  printf("{\"case\":\"%s\",\"validate_socket_rc\":%d,\"receiver_passpidfd\":%d,"
         "\"receive_rc\":%d,\"receive_errno\":%d,\"adopted_scm_rights\":%zu,"
         "\"fds_after_rights_destructor_delta\":%zu,\"unowned_pidfds\":%zu,"
         "\"control_closed_leaks\":true,\"fd_table_restored\":%s,\"finding_reproduced\":%s}\n",
         pass_pidfd?"passpidfd":"ordinary",validate_result,inherited,result,error,adopted,
         added,pidfds,restored?"true":"false",observed?"true":"false");
  return observed&&restored;
}
}
int main() {
  utsname kernel{};Must(uname(&kernel)==0,"uname");
  printf("{\"scope\":\"actual Receive with real socketpairs and ancillary; no listener inheritance, service or namespace\",\"kernel\":\"%s\"}\n",kernel.release);
  const auto before=SnapshotFds();
  const bool ordinary=RunOne(false),negative=RunOne(true);
  const bool all_closed=SnapshotFds()==before;
  printf("{\"all_control_descriptors_closed\":%s}\n",all_closed?"true":"false");
  return ordinary&&negative&&all_closed?0:1;
}
