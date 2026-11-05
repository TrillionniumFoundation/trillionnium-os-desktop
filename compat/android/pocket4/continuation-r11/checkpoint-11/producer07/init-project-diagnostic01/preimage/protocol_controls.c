/* Ordinary owned-process controls. Collection and mount projection are explicit
 * seams; this program does not claim Android PID1/cgroup/namespace execution. */
#define DROIDLOOM_BARRIER_TESTING 1
#include "init_relay_barrier.c"
#include <dirent.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <sys/un.h>

struct fixture { int project_calls, finish_calls, fail_project, fail_finish; };
static int open_count(void) {
  DIR *directory=opendir("/proc/self/fd");if(!directory)return -1;
  int count=0;struct dirent *entry;
  while((entry=readdir(directory)))if(strcmp(entry->d_name,".")&&strcmp(entry->d_name,".."))++count;
  closedir(directory);return count;
}
static int collect_fake(int fds[DIR_HELLO_RIGHTS],unsigned char wire[DIR_WIRE_SIZE],void *unused) {
  (void)unused;
  for(size_t i=0;i<DIR_HELLO_RIGHTS;++i){fds[i]=open("/dev/null",O_RDONLY|O_CLOEXEC);if(fds[i]<0)return -1;}
  dir_put(wire,48,1,8);dir_put(wire,56,2,8);dir_put(wire,64,536870912,8);
  dir_put(wire,72,402653184,8);dir_put(wire,80,0,8);dir_put(wire,88,DIR_HELLO_RIGHTS,4);return 0;
}
static int project_fake(int fd,const unsigned char ready[DIR_WIRE_SIZE],void *opaque) {
  struct fixture *fixture=opaque;struct stat st;++fixture->project_calls;
  if(fstat(fd,&st)||!S_ISSOCK(st.st_mode)||(uint64_t)st.st_ino!=dir_get(ready,56,8))return -1;
  return fixture->fail_project?dir_error(EPERM):0;
}
static int finish_fake(void *opaque) {
  struct fixture *fixture=opaque;++fixture->finish_calls;
  return fixture->fail_finish?dir_error(ENOMEM):0;
}
static int wait_owned(pid_t child,int pidfd,int *status) {
  uint64_t start,now;if(dir_now(&start))return -1;
  for(;;){
    pid_t got=waitpid(child,status,WNOHANG);
    if(got==child)return 0;
    if(got<0)return -1;
    if(dir_now(&now)||now-start>UINT64_C(3000000000)){
      (void)syscall(__NR_pidfd_send_signal,pidfd,SIGKILL,NULL,0);
      (void)waitpid(child,status,0);return -1;
    }
    struct timespec delay={0,1000000};nanosleep(&delay,NULL);
  }
}
static int send_raw_rights(int channel,const void *data,size_t bytes,const int *fds,size_t count) {
  union{struct cmsghdr align;unsigned char bytes[CMSG_SPACE(4*sizeof(int))];}control;
  memset(&control,0,sizeof(control));struct iovec iov={.iov_base=(void *)data,.iov_len=bytes};
  struct msghdr message={.msg_iov=&iov,.msg_iovlen=1};
  if(count){
    message.msg_control=control.bytes;message.msg_controllen=CMSG_SPACE(count*sizeof(int));
    struct cmsghdr *header=CMSG_FIRSTHDR(&message);header->cmsg_level=SOL_SOCKET;
    header->cmsg_type=SCM_RIGHTS;header->cmsg_len=CMSG_LEN(count*sizeof(int));memcpy(CMSG_DATA(header),fds,count*sizeof(int));
  }
  return sendmsg(channel,&message,MSG_NOSIGNAL)==(ssize_t)bytes?0:-1;
}
static int inherited_socket_check(const char *device,const char *inode) {
  uint64_t wanted_device=strtoull(device,NULL,10),wanted_inode=strtoull(inode,NULL,10);
  for(int fd=3;fd<4096;++fd){
    struct stat st;
    if(!fstat(fd,&st)&&S_ISSOCK(st.st_mode)&&(uint64_t)st.st_dev==wanted_device&&(uint64_t)st.st_ino==wanted_inode)return 1;
  }
  return 0;
}
/* DONE is terminal: the constructor closes its channel immediately afterwards.
 * Drain its exact packet even if EOF is visible in that same poll batch. */
static int receive_done(int channel,const unsigned char expected[DIR_WIRE_SIZE]) {
  struct pollfd p={.fd=channel,.events=POLLIN|POLLRDHUP};
  if(poll(&p,1,1500)<=0||!(p.revents&POLLIN)||(p.revents&(POLLERR|POLLNVAL)))return -1;
  unsigned char data[DIR_WIRE_SIZE];
  union{struct cmsghdr align;unsigned char bytes[CMSG_SPACE(4*sizeof(int))];}control;
  memset(&control,0,sizeof(control));struct iovec iov={.iov_base=data,.iov_len=sizeof(data)};
  struct msghdr message={.msg_iov=&iov,.msg_iovlen=1,.msg_control=control.bytes,.msg_controllen=sizeof(control.bytes)};
  ssize_t n=recvmsg(channel,&message,MSG_DONTWAIT|MSG_CMSG_CLOEXEC|MSG_TRUNC);size_t count=0;
  for(struct cmsghdr *h=CMSG_FIRSTHDR(&message);h;h=CMSG_NXTHDR(&message,h)){
    if(h->cmsg_level==SOL_SOCKET&&h->cmsg_type==SCM_RIGHTS&&h->cmsg_len>=CMSG_LEN(0)){
      size_t bytes=h->cmsg_len-CMSG_LEN(0);
      for(size_t i=0;i<bytes/sizeof(int);++i){int fd;memcpy(&fd,CMSG_DATA(h)+i*sizeof(int),sizeof(fd));close(fd);++count;}
    }else ++count;
  }
  return n==DIR_WIRE_SIZE&&!(message.msg_flags&(MSG_TRUNC|MSG_CTRUNC))&&count==0&&!memcmp(data,expected,DIR_WIRE_SIZE)?0:-1;
}
static const char *const names[]={
 "complete_handshake_closes_capabilities_before_next_exec",
 "wrong_nonce_rejected","wrong_abi_rejected","wrong_phase_rejected",
 "extra_rights_closed","wrong_descriptor_type_rejected","wrong_socket_identity_rejected",
 "wrong_socket_mode_rejected","short_packet_rights_closed","oversized_packet_rights_closed",
 "hup_before_projection_rejected","hup_after_projection_rejected","bounded_timeout_rejected",
 "projection_error_rejected","finish_error_rejected","wrong_commit_nonce_rejected",
 "commit_rights_closed","reserved_bytes_rejected","zero_nonce_rejected"
};
static int run_case(int which) {
  int channels[2]={-1,-1},listener=-1,socket_path_fd=-1,regular=-1,pidfd=-1,status=0;
  int received[DIR_MAX_RIGHTS];for(size_t i=0;i<DIR_MAX_RIGHTS;++i)received[i]=-1;
  size_t count=0;pid_t child=-1;int success=0;char directory[]="/tmp/p4-init-relay-controls-XXXXXX";char path[256]={0};
  struct dir_context server;memset(&server,0,sizeof(server));server.control=-1;server.peer_pidfd=-1;
  unsigned char nonce[32];memset(nonce,0x51,sizeof(nonce));
  if(!mkdtemp(directory)||socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_NONBLOCK|SOCK_CLOEXEC,0,channels))goto cleanup;
  child=fork();if(child<0)goto cleanup;
  if(child==0){
    close(channels[0]);
    struct stat inherited;if(fstat(channels[1],&inherited))_exit(90);
    int before=open_count();struct fixture fixture={.fail_project=which==13,.fail_finish=which==14};
    struct dir_operations operations={collect_fake,project_fake,finish_fake,&fixture};
    if(which==18)memset(nonce,0,sizeof(nonce));
    int result=dir_run(channels[1],nonce,which==12?80:1200,geteuid(),&operations);
    int after=open_count();
    bool expected=(which==0);
    if((result==0)!=expected||before<0||after!=before-1||
       fcntl(channels[1],F_GETFD)!=-1||errno!=EBADF)_exit(91);
    if(expected){
      if(fixture.project_calls!=1||fixture.finish_calls!=1)_exit(92);
      char device[32],inode[32];snprintf(device,sizeof(device),"%llu",(unsigned long long)inherited.st_dev);
      snprintf(inode,sizeof(inode),"%llu",(unsigned long long)inherited.st_ino);
      execl("/proc/self/exe","protocol-controls","--inherited-socket",device,inode,(char *)NULL);_exit(93);
    }
    int projected=(which==11||(which>=13&&which<=16))?1:0;
    int finished=which==14?1:0;
    if(fixture.project_calls!=projected||fixture.finish_calls!=finished)_exit(94);
    _exit(0);
  }
  close(channels[1]);channels[1]=-1;
  pidfd=(int)syscall(__NR_pidfd_open,child,0);if(pidfd<0)goto cleanup;
  if(which==18)goto await_child;
  if(dir_context_open(&server,channels[0],nonce,1800,geteuid()))goto cleanup;
  channels[0]=-1;
  unsigned char hello[DIR_WIRE_SIZE],ready[DIR_WIRE_SIZE],reply[DIR_WIRE_SIZE];
  if(dir_receive(&server,hello,received,&count)||count!=DIR_HELLO_RIGHTS||
     !dir_common(hello,DIR_HELLO,nonce)||dir_get(hello,88,4)!=DIR_HELLO_RIGHTS)goto cleanup;
  dir_close_rights(received,count);count=0;
  if(which==10){dir_close(&server.control);goto await_child;}
  if(which==12)goto await_child;
  if(snprintf(path,sizeof(path),"%s/endpoint",directory)<0)goto cleanup;
  listener=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);if(listener<0)goto cleanup;
  struct sockaddr_un address;memset(&address,0,sizeof(address));address.sun_family=AF_UNIX;
  if(strlen(path)>=sizeof(address.sun_path))goto cleanup;
  memcpy(address.sun_path,path,strlen(path)+1);
  if(bind(listener,(struct sockaddr *)&address,sizeof(address))||chmod(path,0600))goto cleanup;
  socket_path_fd=open(path,O_PATH|O_CLOEXEC|O_NOFOLLOW);if(socket_path_fd<0)goto cleanup;
  struct stat socket_stat;if(fstat(socket_path_fd,&socket_stat))goto cleanup;
  dir_base(ready,DIR_PROJECT,nonce);dir_put(ready,48,(uint64_t)socket_stat.st_dev,8);
  dir_put(ready,56,(uint64_t)socket_stat.st_ino,8);dir_put(ready,64,socket_stat.st_uid,4);
  dir_put(ready,68,socket_stat.st_gid,4);dir_put(ready,72,0600,4);
  int rights[2]={socket_path_fd,socket_path_fd};size_t rights_count=1;
  if(which==1)ready[16]^=1;
  if(which==2)dir_put(ready,8,2,4);
  if(which==3)dir_put(ready,12,DIR_COMMIT,4);
  if(which==4)rights_count=2;
  if(which==5){regular=open("/dev/null",O_RDONLY|O_CLOEXEC);if(regular<0)goto cleanup;rights[0]=regular;}
  if(which==6)dir_put(ready,56,(uint64_t)socket_stat.st_ino+1,8);
  if(which==7)dir_put(ready,72,0660,4);
  if(which==17)ready[127]=1;
  if(which==8){
    if(send_raw_rights(server.control,ready,DIR_WIRE_SIZE-1,rights,1))goto cleanup;
  }else if(which==9){
    unsigned char oversized[DIR_WIRE_SIZE+32];memset(oversized,0,sizeof(oversized));memcpy(oversized,ready,DIR_WIRE_SIZE);
    if(send_raw_rights(server.control,oversized,sizeof(oversized),rights,1))goto cleanup;
  }else if(send_raw_rights(server.control,ready,DIR_WIRE_SIZE,rights,rights_count))goto cleanup;
  if((which>=1&&which<=9)||which==13||which==17)goto await_child;
  if(dir_receive(&server,reply,received,&count)||count||!dir_common(reply,DIR_PROJECTED,nonce))goto cleanup;
  if(which==11){dir_close(&server.control);goto await_child;}
  dir_put(ready,12,DIR_COMMIT,4);
  if(which==15)ready[20]^=1;
  if(send_raw_rights(server.control,ready,DIR_WIRE_SIZE,which==16?&socket_path_fd:NULL,which==16?1:0))goto cleanup;
  if(which==14||which==15||which==16)goto await_child;
  dir_put(ready,12,DIR_DONE,4);
  if(receive_done(server.control,ready))goto cleanup;
await_child:
  if(wait_owned(child,pidfd,&status))goto cleanup;
  child=-1;success=WIFEXITED(status)&&WEXITSTATUS(status)==0;
cleanup:
  if(child>0){
    if(pidfd>=0)(void)syscall(__NR_pidfd_send_signal,pidfd,SIGKILL,NULL,0);
    else (void)kill(child,SIGKILL);
    (void)waitpid(child,&status,0);
  }
  dir_close_rights(received,DIR_MAX_RIGHTS);dir_close(&server.control);dir_close(&server.peer_pidfd);
  dir_close(&channels[0]);dir_close(&channels[1]);dir_close(&listener);dir_close(&socket_path_fd);dir_close(&regular);dir_close(&pidfd);
  if (path[0]) unlink(path);
  rmdir(directory);
  return success;
}
static int daemon_exit_case(void) {
  int channel[2]={-1,-1},client=-1,held_peer=-1,creator_pidfd=-1;
  pid_t creator=-1;int status=0,success=0;
  struct dir_context context;memset(&context,0,sizeof(context));context.control=-1;context.peer_pidfd=-1;
  if(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,channel))goto cleanup;
  creator=fork();if(creator<0)goto cleanup;
  if(creator==0){
    close(channel[0]);int pair[2];
    if(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_NONBLOCK|SOCK_CLOEXEC,0,pair))_exit(80);
    unsigned char payload[DIR_WIRE_SIZE]={0};
    if(send_raw_rights(channel[1],payload,sizeof(payload),pair,2))_exit(81);
    close(pair[0]);close(pair[1]);
    struct pollfd ready={.fd=channel[1],.events=POLLIN};char ack=0;
    if(poll(&ready,1,2000)<=0||read(channel[1],&ack,1)!=1||ack!='X')_exit(82);
    _exit(0);
  }
  close(channel[1]);channel[1]=-1;
  creator_pidfd=(int)syscall(__NR_pidfd_open,creator,0);if(creator_pidfd<0)goto cleanup;
  struct pollfd ready={.fd=channel[0],.events=POLLIN};if(poll(&ready,1,2000)<=0)goto cleanup;
  unsigned char data[DIR_WIRE_SIZE];
  union{struct cmsghdr align;unsigned char bytes[CMSG_SPACE(4*sizeof(int))];}control;
  memset(&control,0,sizeof(control));struct iovec iov={.iov_base=data,.iov_len=sizeof(data)};
  struct msghdr message={.msg_iov=&iov,.msg_iovlen=1,.msg_control=control.bytes,.msg_controllen=sizeof(control.bytes)};
  ssize_t n=recvmsg(channel[0],&message,MSG_CMSG_CLOEXEC);
  int delivered[4]={-1,-1,-1,-1};size_t count=0;int valid=1;
  for(struct cmsghdr *header=CMSG_FIRSTHDR(&message);header;header=CMSG_NXTHDR(&message,header)){
    if(header->cmsg_level!=SOL_SOCKET||header->cmsg_type!=SCM_RIGHTS||header->cmsg_len<CMSG_LEN(0)){valid=0;continue;}
    size_t bytes=header->cmsg_len-CMSG_LEN(0);if(bytes%sizeof(int))valid=0;
    for(size_t i=0;i<bytes/sizeof(int);++i){int fd;memcpy(&fd,CMSG_DATA(header)+i*sizeof(int),sizeof(fd));
      if(count<4)delivered[count++]=fd;else{close(fd);valid=0;}}
  }
  if(n!=DIR_WIRE_SIZE||!valid||count!=2||message.msg_flags&MSG_CTRUNC){dir_close_rights(delivered,4);goto cleanup;}
  client=delivered[0];held_peer=delivered[1];
  unsigned char nonce[32];memset(nonce,0x73,sizeof(nonce));
  if (dir_context_open(&context, client, nonce, 1500, geteuid())) goto cleanup;
  client = -1;
  if(write(channel[0],"X",1)!=1)goto cleanup;
  errno=0;int result=dir_wait(&context,POLLIN);int error=errno;
  struct pollfd held_socket={.fd=context.control,.events=POLLIN|POLLRDHUP};int polled=poll(&held_socket,1,0);
  if (wait_owned(creator, creator_pidfd, &status)) goto cleanup;
  creator = -1;
  success=result==-1&&error==EPIPE&&polled==0&&WIFEXITED(status)&&WEXITSTATUS(status)==0;
cleanup:
  if(creator>0){if(creator_pidfd>=0)(void)syscall(__NR_pidfd_send_signal,creator_pidfd,SIGKILL,NULL,0);else kill(creator,SIGKILL);waitpid(creator,NULL,0);}
  dir_close(&context.control);dir_close(&context.peer_pidfd);dir_close(&channel[0]);dir_close(&channel[1]);
  dir_close(&client);dir_close(&held_peer);dir_close(&creator_pidfd);
  return success;
}
int main(int argc,char **argv) {
  if(argc==4&&!strcmp(argv[1],"--inherited-socket"))return inherited_socket_check(argv[2],argv[3]);
  if(argc!=1)return 2;
  unsigned passed=0;int baseline=open_count();
  for(size_t i=0;i<sizeof(names)/sizeof(names[0]);++i){
    int ok=run_case((int)i)&&open_count()==baseline;
    printf("{\"case\":\"%s\",\"ok\":%s}\n",names[i],ok?"true":"false");fflush(stdout);
    if (!ok) return 1;
    ++passed;
  }
  int ok=daemon_exit_case()&&open_count()==baseline;
  printf("{\"case\":\"daemon_exit_with_socket_still_held_rejected\",\"ok\":%s}\n",ok?"true":"false");
  if (!ok) return 1;
    ++passed;
  printf("{\"ok\":true,\"owned_controls_passed\":%u,\"Android_PID1_executed\":false,\"mounts_or_pressure_executed\":false}\n",passed);
  return 0;
}
