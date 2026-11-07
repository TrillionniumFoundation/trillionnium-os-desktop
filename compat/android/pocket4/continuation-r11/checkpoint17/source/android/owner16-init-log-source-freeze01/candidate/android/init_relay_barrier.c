/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
 *
 * Opt-in second-stage PID1 barrier. No thread, fork, pressure allocation, PSI
 * threshold write or process signal occurs here. The constructor owns every
 * supplied/received authority descriptor and closes it before returning to
 * init. An optional generation-private bounded log writer stays only in the
 * cached logger, is CLOEXEC, and is never exported in a service environment.
 */
#define _GNU_SOURCE
#include "init_relay_protocol.h"
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#ifndef O_PATH
#define O_PATH 010000000
#endif
#ifndef SO_PEERPIDFD
#define SO_PEERPIDFD 77
#endif
#ifndef CGROUP2_SUPER_MAGIC
#define CGROUP2_SUPER_MAGIC 0x63677270
#endif
#ifndef TMPFS_MAGIC
#define TMPFS_MAGIC 0x01021994
#endif
#ifndef MOVE_MOUNT_F_EMPTY_PATH
#define MOVE_MOUNT_F_EMPTY_PATH 0x00000004
#endif
#ifndef MOVE_MOUNT_T_EMPTY_PATH
#define MOVE_MOUNT_T_EMPTY_PATH 0x00000040
#endif
#define DIR_BAD (POLLERR | POLLHUP | POLLRDHUP | POLLNVAL)

static const unsigned char dir_magic[8] = {'P','4','I','B','V','3','!','!'};
static const char *const dir_ns_names[10] = {
  "pid", "pid_for_children", "mnt", "cgroup", "user",
  "net", "ipc", "uts", "time", "time_for_children"
};
static uint64_t dir_get(const unsigned char *p, size_t offset, size_t bytes) {
  uint64_t out = 0;
  for (size_t i = 0; i < bytes; ++i) out |= (uint64_t)p[offset+i] << (8*i);
  return out;
}
static void dir_put(unsigned char *p, size_t offset, uint64_t value, size_t bytes) {
  for (size_t i = 0; i < bytes; ++i) p[offset+i] = (unsigned char)(value >> (8*i));
}
static int dir_error(int error) { errno = error; return -1; }
/* Failure-only, bounded diagnostics. No new authority or protocol field. */
struct dir_failure {
  const char *stage;
  int error;
  unsigned metadata;
  uint64_t device, inode;
  uint32_t uid, gid, mode;
};
static void dir_stage(struct dir_failure *failure, const char *stage) {
  failure->stage=stage;failure->metadata=0;
  failure->device=0;failure->inode=0;failure->uid=0;failure->gid=0;failure->mode=0;
}
static void dir_metadata(struct dir_failure *failure, const struct stat *value) {
  failure->metadata=1;failure->device=(uint64_t)value->st_dev;failure->inode=(uint64_t)value->st_ino;
  failure->uid=(uint32_t)value->st_uid;failure->gid=(uint32_t)value->st_gid;
  failure->mode=(uint32_t)value->st_mode;
}
static int dir_failure_line(char *out, size_t size, const struct dir_failure *failure) {
  int written=snprintf(out,size,"Droidloom init relay bootstrap failed closed stage=%s errno=%d metadata=%u dev=%llu ino=%llu uid=%u gid=%u mode=%o\n",
    failure->stage,failure->error,failure->metadata,(unsigned long long)failure->device,
    (unsigned long long)failure->inode,failure->uid,failure->gid,failure->mode);
  return written>0&&(size_t)written<size?written:-1;
}
static void dir_close(int *fd) { if (*fd >= 0) close(*fd); *fd = -1; }
static void dir_close_rights(int *fds, size_t count) {
  for (size_t i = 0; i < count; ++i) dir_close(&fds[i]);
}
static int dir_now(uint64_t *out) {
  struct timespec value;
  if (clock_gettime(CLOCK_MONOTONIC, &value) || value.tv_sec < 0 ||
      value.tv_nsec < 0 || value.tv_nsec >= 1000000000 ||
      (uint64_t)value.tv_sec > (UINT64_MAX - (uint64_t)value.tv_nsec)/1000000000) return -1;
  *out = (uint64_t)value.tv_sec*1000000000+(uint64_t)value.tv_nsec;
  return *out ? 0 : dir_error(EPROTO);
}
static int dir_clock(struct dir_context *c) {
  uint64_t now;
  if (dir_now(&now) || now < c->last_clock || now >= c->deadline) return dir_error(ETIMEDOUT);
  c->last_clock = now; return 0;
}
static int dir_wait(struct dir_context *c, short wanted) {
  for (;;) {
    if (dir_clock(c)) return -1;
    uint64_t ms = (c->deadline-c->last_clock+999999)/1000000;
    if (ms > 100) ms = 100;
    struct pollfd p[2] = {
      {.fd=c->control,.events=(short)(wanted|POLLRDHUP)},
      {.fd=c->peer_pidfd,.events=POLLIN}
    };
    int n = poll(p,2,(int)ms);
    if (n < 0 && errno == EINTR) continue;
    if (n < 0 || (p[0].revents & DIR_BAD) || p[1].revents) return dir_error(EPIPE);
    if (dir_clock(c)) return -1;
    if (p[0].revents & wanted) return 0;
  }
}
static int dir_socket_int(int fd, int option, int *out) {
  socklen_t length = sizeof(*out);
  if (getsockopt(fd,SOL_SOCKET,option,out,&length) || length != sizeof(*out)) return -1;
  return 0;
}
static int dir_context_open(struct dir_context *c, int fd, const unsigned char nonce[32],
                            unsigned timeout_ms, uid_t expected_uid) {
  memset(c,0,sizeof(*c)); c->control=fd; c->peer_pidfd=-1;
  if (fd < 3 || timeout_ms < 10 || timeout_ms > 20000) return dir_error(EINVAL);
  int flags=fcntl(fd,F_GETFD), status=fcntl(fd,F_GETFL), kind=0, domain=0;
  if (flags < 0 || status < 0 || fcntl(fd,F_SETFD,flags|FD_CLOEXEC) ||
      dir_socket_int(fd,SO_TYPE,&kind) || kind != SOCK_SEQPACKET ||
      dir_socket_int(fd,SO_DOMAIN,&domain) || domain != AF_UNIX ||
      !(status & O_NONBLOCK)) return dir_error(EPROTO);
  struct ucred peer; socklen_t length=sizeof(peer);
  if (getsockopt(fd,SOL_SOCKET,SO_PEERCRED,&peer,&length) || length != sizeof(peer) ||
      peer.uid != expected_uid || peer.gid != expected_uid || peer.pid < 0 ||
      dir_socket_int(fd,SO_PEERPIDFD,&c->peer_pidfd) || c->peer_pidfd < 0) return dir_error(EPROTO);
  flags=fcntl(c->peer_pidfd,F_GETFD);
  if (flags < 0 || !(flags & FD_CLOEXEC)) return dir_error(EPROTO);
  unsigned char any=0;
  for (size_t i=0;i<32;++i) { c->nonce[i]=nonce[i]; any|=nonce[i]; }
  uint64_t now;
  if (!any || dir_now(&now) || now > UINT64_MAX-(uint64_t)timeout_ms*1000000) return dir_error(EPROTO);
  c->last_clock=now;c->deadline=now+(uint64_t)timeout_ms*1000000;
  struct pollfd pinned={.fd=c->peer_pidfd,.events=POLLIN};
  if (poll(&pinned,1,0) != 0 || pinned.revents) return dir_error(EPIPE);
  return 0;
}
static void dir_base(unsigned char wire[DIR_WIRE_SIZE], unsigned kind,
                     const unsigned char nonce[32]) {
  memset(wire,0,DIR_WIRE_SIZE);memcpy(wire,dir_magic,8);
  dir_put(wire,8,DIR_ABI,4);dir_put(wire,12,kind,4);memcpy(wire+16,nonce,32);
}
static int dir_common(const unsigned char wire[DIR_WIRE_SIZE], unsigned kind,
                       const unsigned char nonce[32]) {
  return memcmp(wire,dir_magic,8)==0 && dir_get(wire,8,4)==DIR_ABI &&
    dir_get(wire,12,4)==kind && memcmp(wire+16,nonce,32)==0;
}
static int dir_send(struct dir_context *c, const unsigned char wire[DIR_WIRE_SIZE],
                     const int *fds, size_t count) {
  if (count > DIR_HELLO_RIGHTS) return dir_error(EINVAL);
  union { struct cmsghdr alignment; unsigned char bytes[CMSG_SPACE(DIR_HELLO_RIGHTS*sizeof(int))]; } ancillary;
  for (;;) {
    if (dir_wait(c,POLLOUT)) return -1;
    memset(&ancillary,0,sizeof(ancillary));
    struct iovec vector={.iov_base=(void *)wire,.iov_len=DIR_WIRE_SIZE};
    struct msghdr msg={.msg_iov=&vector,.msg_iovlen=1};
    if (count) {
      msg.msg_control=ancillary.bytes;msg.msg_controllen=CMSG_SPACE(count*sizeof(int));
      struct cmsghdr *header=CMSG_FIRSTHDR(&msg);
      header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
      header->cmsg_len=CMSG_LEN(count*sizeof(int));memcpy(CMSG_DATA(header),fds,count*sizeof(int));
    }
    ssize_t n=sendmsg(c->control,&msg,MSG_DONTWAIT|MSG_NOSIGNAL);
    if (n < 0 && (errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR)) continue;
    if (n != DIR_WIRE_SIZE || dir_clock(c)) return dir_error(EPROTO);
    return 0;
  }
}
static int dir_receive(struct dir_context *c, unsigned char wire[DIR_WIRE_SIZE],
                        int out[DIR_MAX_RIGHTS], size_t *count) {
  *count=0;for (size_t i=0;i<DIR_MAX_RIGHTS;++i) out[i]=-1;
  for (;;) {
    if (dir_wait(c,POLLIN)) return -1;
    union { struct cmsghdr alignment; unsigned char bytes[CMSG_SPACE(DIR_MAX_RIGHTS*sizeof(int))]; } ancillary;
    memset(&ancillary,0,sizeof(ancillary));
    struct iovec vector={.iov_base=wire,.iov_len=DIR_WIRE_SIZE};
    struct msghdr msg={.msg_iov=&vector,.msg_iovlen=1,.msg_control=ancillary.bytes,.msg_controllen=sizeof(ancillary.bytes)};
    ssize_t n=recvmsg(c->control,&msg,MSG_DONTWAIT|MSG_CMSG_CLOEXEC|MSG_TRUNC);
    if (n < 0 && (errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR)) continue;
    bool valid=n==DIR_WIRE_SIZE && !(msg.msg_flags&(MSG_TRUNC|MSG_CTRUNC));
    size_t headers=0;
    for (struct cmsghdr *header=CMSG_FIRSTHDR(&msg);header;header=CMSG_NXTHDR(&msg,header)) {
      ++headers;
      if (header->cmsg_level!=SOL_SOCKET || header->cmsg_type!=SCM_RIGHTS || header->cmsg_len<CMSG_LEN(0)) { valid=false;continue; }
      size_t bytes=header->cmsg_len-CMSG_LEN(0);
      if (bytes%sizeof(int)) valid=false;
      for (size_t i=0;i<bytes/sizeof(int);++i) {
        int fd;memcpy(&fd,CMSG_DATA(header)+i*sizeof(int),sizeof(fd));
        if (*count<DIR_MAX_RIGHTS) out[(*count)++]=fd;
        else { close(fd);valid=false; }
      }
    }
    if (headers>1 || !valid || dir_clock(c)) {
      dir_close_rights(out,*count);*count=0;return dir_error(EPROTO);
    }
    return 0;
  }
}
static int dir_ready(const unsigned char wire[DIR_WIRE_SIZE], struct dir_context *c, int fd,
                     struct dir_failure *failure) {
  dir_stage(failure,"project-wire");
  if (!dir_common(wire,DIR_PROJECT,c->nonce) || !dir_get(wire,48,8) ||
      !dir_get(wire,56,8) || dir_get(wire,72,4)!=0600) return dir_error(EPROTO);
  for (size_t i=76;i<DIR_WIRE_SIZE;++i) if (wire[i]) return dir_error(EPROTO);
  struct stat value;
  dir_stage(failure,"project-fd-stat");
  if (fstat(fd,&value)) return -1;
  dir_stage(failure,"project-fd-policy");dir_metadata(failure,&value);
  int status=fcntl(fd,F_GETFL),flags=fcntl(fd,F_GETFD);
  if (!S_ISSOCK(value.st_mode) || status<0 || !(status&O_PATH) ||
      flags<0 || !(flags&FD_CLOEXEC) || (uint64_t)value.st_dev!=dir_get(wire,48,8) ||
      (uint64_t)value.st_ino!=dir_get(wire,56,8) || value.st_uid!=dir_get(wire,64,4) ||
      value.st_gid!=dir_get(wire,68,4) || (value.st_mode&07777)!=0600) return dir_error(EPROTO);
  return 0;
}
static int dir_run(int control, const unsigned char nonce[32], unsigned timeout_ms,
                    uid_t expected_uid, const struct dir_operations *operations,
                    struct dir_failure *failure) {
  struct dir_context context;
  int rights[DIR_HELLO_RIGHTS],received[DIR_MAX_RIGHTS];
  for (size_t i=0;i<DIR_HELLO_RIGHTS;++i)rights[i]=-1;
  for (size_t i=0;i<DIR_MAX_RIGHTS;++i)received[i]=-1;
  size_t count=0;int result=-1;
  memset(failure,0,sizeof(*failure));dir_stage(failure,"context");
  unsigned char wire[DIR_WIRE_SIZE],ready[DIR_WIRE_SIZE],expected[DIR_WIRE_SIZE];
  if (dir_context_open(&context,control,nonce,timeout_ms,expected_uid)) goto done;
  dir_base(wire,DIR_HELLO,nonce);
  dir_stage(failure,"hello-collect");
  if (operations->collect(rights,wire,operations->opaque)) goto done;
  dir_stage(failure,"hello-send");
  if (dir_send(&context,wire,rights,DIR_HELLO_RIGHTS)) goto done;
  dir_close_rights(rights,DIR_HELLO_RIGHTS);
  dir_stage(failure,"project-receive");
  if (dir_receive(&context,ready,received,&count)) goto done;
  dir_stage(failure,"project-rights");
  if (count!=1) { errno=EPROTO;goto done; }
  if (dir_ready(ready,&context,received[0],failure)) goto done;
  dir_stage(failure,"project-effect");
  if (operations->project(received[0],ready,operations->opaque)) goto done;
  dir_close_rights(received,count);count=0;
  memcpy(wire,ready,DIR_WIRE_SIZE);dir_put(wire,12,DIR_PROJECTED,4);
  dir_stage(failure,"projected-send");
  if (dir_send(&context,wire,NULL,0)) goto done;
  dir_stage(failure,"commit-receive");
  if (dir_receive(&context,wire,received,&count)) goto done;
  dir_stage(failure,"commit-rights");
  if (count) { errno=EPROTO;goto done; }
  memcpy(expected,ready,DIR_WIRE_SIZE);dir_put(expected,12,DIR_COMMIT,4);
  dir_stage(failure,"commit-wire");
  if (memcmp(wire,expected,DIR_WIRE_SIZE)) { errno=EPROTO;goto done; }
  dir_stage(failure,"finish");
  if (operations->finish(operations->opaque)) goto done;
  /* All authority FDs except this one private control channel are gone.
   * The optional bounded diagnostic writer is CLOEXEC and absent from env.
   * Environment cleanup has succeeded. No fallible work follows final send. */
  memcpy(wire,ready,DIR_WIRE_SIZE);dir_put(wire,12,DIR_DONE,4);
  dir_stage(failure,"done-send");
  if (dir_send(&context,wire,NULL,0)) goto done;
  dir_stage(failure,"complete");
  result=0;
done:
  /* A close failure cannot replace the first protocol/projection failure. */
  failure->error=result?errno:0;
  if(result&&!failure->error)failure->error=EPROTO;
  dir_close_rights(rights,DIR_HELLO_RIGHTS);dir_close_rights(received,DIR_MAX_RIGHTS);
  dir_close(&context.peer_pidfd);dir_close(&context.control);
  if(result)errno=failure->error;
  return result;
}
static int dir_u64_file(int directory,const char *name,uint64_t *out) {
  int fd=openat(directory,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
  if (fd<0)return -1;
  char data[64];size_t used=0;
  for (;;) {
    ssize_t n=read(fd,data+used,sizeof(data)-used);
    if (n<0&&errno==EINTR)continue;
    if (n<0){close(fd);return -1;}
    if (!n)break;
    used+=(size_t)n;if(used==sizeof(data)){close(fd);return dir_error(EOVERFLOW);}
  }
  close(fd);
  if (!used || data[used-1]!='\n')return dir_error(EPROTO);
  --used;if(!used)return dir_error(EPROTO);
  uint64_t value=0;
  for(size_t i=0;i<used;++i){
    if(data[i]<'0'||data[i]>'9'||value>(UINT64_MAX-(uint64_t)(data[i]-'0'))/10)return dir_error(EPROTO);
    value=value*10+(uint64_t)(data[i]-'0');
  }
  *out=value;return 0;
}
static int dir_root_directory(int fd,struct dir_failure *failure,
                              const char *stat_stage,const char *policy_stage);
/* ABI3 uses an owned holding view. Do not mount over, skip, or fabricate
 * success for the stock Android target. Both sides check that target is
 * still on the original synthetic sys tmpfs before returning to real init. */
static int dir_open_cgroup_view(struct dir_failure *failure) {
  int root=-1,dev=-1,holding=-1,view=-1,sys=-1,fsdir=-1,target=-1,result=-1,saved=0;
  struct statfs sysfs,targetfs,holdingfs;struct stat sys_st,target_st;
  dir_stage(failure,"collect-root-open");
  root=open("/",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(root,failure,"collect-root-stat","collect-root-policy"))goto done;
  dir_stage(failure,"collect-dev-open");
  dev=openat(root,"dev",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(dev,failure,"collect-dev-stat","collect-dev-policy"))goto done;
  dir_stage(failure,"collect-holding-open");
  holding=openat(dev,".droidloom-cgroups",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(holding,failure,"collect-holding-stat","collect-holding-policy"))goto done;
  dir_stage(failure,"collect-holding-filesystem");
  if(fstatfs(holding,&holdingfs))goto done;
  if(holdingfs.f_type!=TMPFS_MAGIC){errno=EPROTO;goto done;}
  dir_stage(failure,"collect-domain-open");
  view=openat(holding,"relay-v2",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(view,failure,"collect-domain-stat","collect-domain-policy"))goto done;
  dir_stage(failure,"collect-sys-open");
  sys=openat(root,"sys",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(sys,failure,"collect-sys-stat","collect-sys-policy"))goto done;
  dir_stage(failure,"collect-fs-open");
  fsdir=openat(sys,"fs",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(fsdir,failure,"collect-fs-stat","collect-fs-policy"))goto done;
  dir_stage(failure,"collect-native-target-open");
  target=openat(fsdir,"cgroup",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(target,failure,"collect-native-target-stat","collect-native-target-policy"))goto done;
  dir_stage(failure,"collect-native-target-filesystem");
  if(fstatfs(sys,&sysfs)||fstatfs(target,&targetfs)||fstat(sys,&sys_st)||fstat(target,&target_st))goto done;
  if(sysfs.f_type!=TMPFS_MAGIC||targetfs.f_type!=TMPFS_MAGIC||sys_st.st_dev!=target_st.st_dev){errno=EPROTO;goto done;}
  result=view;view=-1;
done:
  saved=errno;
  dir_close(&target);dir_close(&fsdir);dir_close(&sys);dir_close(&view);
  dir_close(&holding);dir_close(&dev);dir_close(&root);
  errno=saved;return result;
}
static int dir_collect_domain(int *domain,unsigned char wire[DIR_WIRE_SIZE],struct dir_failure *failure) {
  *domain=dir_open_cgroup_view(failure);
  struct statfs fs;struct stat st;
  if(*domain<0)return -1;
  dir_stage(failure,"collect-domain-filesystem");
  if(fstatfs(*domain,&fs)||fstat(*domain,&st))return -1;
  if(fs.f_type!=CGROUP2_SUPER_MAGIC)return dir_error(EPROTO);
  uint64_t maximum,high,swap;
  if(dir_u64_file(*domain,"memory.max",&maximum)||dir_u64_file(*domain,"memory.high",&high)||
     dir_u64_file(*domain,"memory.swap.max",&swap)||!maximum||!high||high>=maximum||swap!=0)return dir_error(EPROTO);
  dir_put(wire,48,(uint64_t)st.st_dev,8);dir_put(wire,56,(uint64_t)st.st_ino,8);
  dir_put(wire,64,maximum,8);dir_put(wire,72,high,8);dir_put(wire,80,swap,8);
  return 0;
}
static int dir_collect_real(int rights[DIR_HELLO_RIGHTS],unsigned char wire[DIR_WIRE_SIZE],void *opaque) {
  if(dir_collect_domain(&rights[0],wire,(struct dir_failure *)opaque))return -1;
  rights[1]=(int)syscall(__NR_pidfd_open,getpid(),0);if(rights[1]<0)return -1;
  for(size_t i=0;i<10;++i){
    char path[64];int n=snprintf(path,sizeof(path),"/proc/self/ns/%s",dir_ns_names[i]);
    if(n<=0||(size_t)n>=sizeof(path))return dir_error(EOVERFLOW);
    rights[2+i]=open(path,O_RDONLY|O_CLOEXEC);if(rights[2+i]<0)return -1;
  }
  dir_put(wire,88,DIR_HELLO_RIGHTS,4);
  return 0;
}
static int dir_root_directory(int fd,struct dir_failure *failure,
                              const char *stat_stage,const char *policy_stage) {
  struct stat value;
  if(fd<0)return 0;
  dir_stage(failure,stat_stage);
  if(fstat(fd,&value))return 0;
  dir_stage(failure,policy_stage);dir_metadata(failure,&value);
  if(S_ISDIR(value.st_mode)&&value.st_uid==0&&value.st_gid==0&&!(value.st_mode&0022))return 1;
  errno=EPERM;return 0;
}
static int dir_project_real(int socket_fd,const unsigned char ready[DIR_WIRE_SIZE],void *opaque) {
  struct dir_failure *failure=opaque;
  dir_stage(failure,"project-root-open");
  int root=open("/",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW),dev=-1,sockets=-1,target=-1;
  int result=-1,saved=0;
  if(!dir_root_directory(root,failure,"project-root-stat","project-root-policy"))goto done;
  dir_stage(failure,"project-dev-open");
  dev=openat(root,"dev",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(dev,failure,"project-dev-stat","project-dev-policy"))goto done;
  dir_stage(failure,"project-sockets-open");
  sockets=openat(dev,"socket",O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(!dir_root_directory(sockets,failure,"project-sockets-stat","project-sockets-policy"))goto done;
  dir_stage(failure,"project-target-create");
  target=openat(sockets,DIR_SOCKET_NAME,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
  if(target<0)goto done;
  /* ABI 2 supplies a detached mount root, cloned by the source namespace
   * owner. Keep our O_EXCL target held through the exact single attachment.
   * A raw foreign FD or an old sender fails closed; there is no bind fallback. */
  dir_stage(failure,"project-move-mount");
  if(syscall(__NR_move_mount,socket_fd,"",target,"",
             MOVE_MOUNT_F_EMPTY_PATH|MOVE_MOUNT_T_EMPTY_PATH))goto done;
  struct stat st;
  dir_stage(failure,"project-mounted-stat");
  if(fstatat(sockets,DIR_SOCKET_NAME,&st,AT_SYMLINK_NOFOLLOW))goto done;
  dir_stage(failure,"project-mounted-policy");dir_metadata(failure,&st);
  if(!S_ISSOCK(st.st_mode)||
     (uint64_t)st.st_dev!=dir_get(ready,48,8)||(uint64_t)st.st_ino!=dir_get(ready,56,8)||
      st.st_uid!=dir_get(ready,64,4)||st.st_gid!=dir_get(ready,68,4)||(st.st_mode&07777)!=0600){errno=EPROTO;goto done;}
  result=0;
done:
  saved=errno;
  dir_close(&target);dir_close(&sockets);dir_close(&dev);dir_close(&root);
  errno=saved;return result;
}
static int dir_finish_real(void *unused) {
  (void)unused;
  const char *keys[]={DIR_ABI_ENV,DIR_REQUIRED_ENV,DIR_FD_ENV,DIR_NONCE_ENV,DIR_TIMEOUT_ENV,
    DIR_LOG_ABI_ENV,DIR_LOG_FD_ENV};
  for(size_t i=0;i<sizeof(keys)/sizeof(keys[0]);++i)if(unsetenv(keys[i]))return -1;
  /* The barrier is not needed by init re-exec, service children or apps.
   * Preserve the existing SELinux compatibility preload exactly. */
#if defined(__x86_64__)
  return setenv("LD_PRELOAD","/system/lib64/libclang_rt.asan-x86_64-android.so",1);
#elif defined(__aarch64__)
  return setenv("LD_PRELOAD","/system/lib64/bootstrap/libclang_rt.hwasan-aarch64-android.so",1);
#else
#error unsupported Android architecture
#endif
}
static int dir_parse_decimal(const char *text,unsigned maximum,unsigned *out) {
  if (!text || !*text) return -1;
  unsigned value = 0;
  for(const unsigned char *p=(const unsigned char *)text;*p;++p){
    if(*p<'0'||*p>'9'||(unsigned)(*p-'0')>maximum||value>(maximum-(unsigned)(*p-'0'))/10)return -1;
    value=value*10+(unsigned)(*p-'0');
  }
  *out=value;return 0;
}
static int dir_nonce(const char *text,unsigned char nonce[32]) {
  if (!text || strlen(text) != 64) return -1;
  unsigned char any = 0;
  for(size_t i=0;i<32;++i){
    unsigned byte=0;
    for(size_t j=0;j<2;++j){
      unsigned char c=(unsigned char)text[2*i+j];unsigned n;
      if(c>='0'&&c<='9')n=(unsigned)(c-'0');
      else if(c>='a'&&c<='f')n=(unsigned)(c-'a'+10);
      else return -1;
      byte = byte * 16 + n;
    }
    nonce[i]=(unsigned char)byte;any|=nonce[i];
  }
  return any?0:-1;
}
static int dir_second_stage(void) {
  int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;
  char data[1024];size_t used=0;
  for(;;){
    ssize_t n=read(fd,data+used,sizeof(data)-used);
    if(n<0&&errno==EINTR)continue;
    if(n<0){close(fd);return -1;}if(!n)break;
    used+=(size_t)n;if(used==sizeof(data)){close(fd);return -1;}
  }
  close(fd);
  static const char wanted[]="/init\0second_stage\0";
  return used==sizeof(wanted)-1&&!memcmp(data,wanted,sizeof(wanted)-1)?0:-1;
}

/* C++ calling convention is conditional on the exact observed ELF symbol,
 * not a claim of a stable platform API. The fixed actual init/import and
 * defining library evidence must be bound by the build/runtime controller.
 * The host additionally requires the real logger-written nonce bytes after
 * HELLO. A non-null dlsym result alone never admits the channel. */
typedef void (*dir_kernel_logger)(int,int,const char *,const char *,unsigned,const char *);
#define DIR_KERNEL_LOGGER_SYMBOL "_ZN7android4base12KernelLoggerENS0_5LogIdENS0_11LogSeverityEPKcS4_jS4_"

static int dir_log_writer(int fd) {
  struct stat st;struct statfs fs;
  int flags=fcntl(fd,F_GETFL);if(flags<0)return -1;
  int seals=fcntl(fd,F_GET_SEALS);if(seals<0)return -1;
  if(fstat(fd,&st)||fstatfs(fd,&fs))return -1;
  if(!S_ISREG(st.st_mode)||st.st_uid!=getuid()||st.st_gid!=getgid()||st.st_nlink!=0||
     (st.st_mode&07777)!=0600||st.st_size!=DIR_LOG_CAPACITY||fs.f_type!=TMPFS_MAGIC||
     (flags&O_ACCMODE)!=O_WRONLY||!(flags&O_NONBLOCK)||(flags&(O_APPEND|O_PATH))||
     seals!=(F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL))return dir_error(EPROTO);
  int descriptor=fcntl(fd,F_GETFD);if(descriptor<0)return -1;
  if(fcntl(fd,F_SETFD,descriptor|FD_CLOEXEC))return -1;
  off_t position=lseek(fd,0,SEEK_CUR);
  if(position<0)return -1;
  return position==0?0:dir_error(EPROTO);
}

/* The seam is solely the lookup/call of the actual library function. Owned
 * controls exercise the real memfd, seals, fd flags, environment and exec;
 * they do not certify the Android library or its cache implementation. */
static int dir_prime_log(int fd,const char *nonce_text,dir_kernel_logger logger) {
  int first=0;
  char descriptor[16],message[128];
  if(!logger)return dir_error(ENOSYS);
  if(dir_log_writer(fd))return -1;
  if(getenv("ANDROID_FILE__dev_kmsg"))return dir_error(EPROTO);
  int n=snprintf(descriptor,sizeof(descriptor),"%d",fd);
  int m=snprintf(message,sizeof(message),"P4_INIT_LOG_V1 nonce=%s",nonce_text);
  if(n<=0||(size_t)n>=sizeof(descriptor)||m<=0||(size_t)m>=sizeof(message))return dir_error(EOVERFLOW);
  if(setenv("ANDROID_FILE__dev_kmsg",descriptor,1))return -1;
  /* LogId DEFAULT=0, LogSeverity INFO=2; this intentionally writes via the
   * resolved library, never directly substitutes the expected marker. */
  logger(0,2,"droidloom-init-log",__FILE__,0,message);
  off_t position=lseek(fd,0,SEEK_CUR);
  if(position<0)first=errno;
  else if(position!=(off_t)(strlen("<6>droidloom-init-log: ")+(size_t)m+1))first=EPROTO;
  if(unsetenv("ANDROID_FILE__dev_kmsg")&&!first)first=errno;
  if(unsetenv(DIR_LOG_ABI_ENV)&&!first)first=errno;
  if(unsetenv(DIR_LOG_FD_ENV)&&!first)first=errno;
  if(first)return dir_error(first);
  /* Verify the cached route once more after removing every diagnostic env
   * key. A logger that only consulted the env on the first call is not enough
   * evidence that later init logs will use this same private object. */
  m=snprintf(message,sizeof(message),"P4_INIT_LOG_CACHED_V1 nonce=%s",nonce_text);
  if(m<=0||(size_t)m>=sizeof(message))return dir_error(EOVERFLOW);
  logger(0,2,"droidloom-init-log",__FILE__,0,message);
  off_t after=lseek(fd,0,SEEK_CUR);
  if(after<0)return -1;
  if(after!=position+(off_t)(strlen("<6>droidloom-init-log: ")+(size_t)m+1))return dir_error(EPROTO);
  return 0;
}

static int dir_setup_log(const char *nonce_text) {
  const char *abi=getenv(DIR_LOG_ABI_ENV),*fdtext=getenv(DIR_LOG_FD_ENV);
  if(!abi&&!fdtext)return 0; /* Existing ABI3/default behaviour is unchanged. */
  unsigned fd=0;
  if(!abi||strcmp(abi,"1")||dir_parse_decimal(fdtext,1023,&fd)||fd!=DIR_LOG_FD)
    return dir_error(EPROTO);
  if(dir_log_writer((int)fd))return -1;
  dlerror();
  void *symbol=dlsym(RTLD_DEFAULT,DIR_KERNEL_LOGGER_SYMBOL);
  const char *lookup_error=dlerror();
  if(!symbol||lookup_error)return dir_error(ENOSYS);
  Dl_info definition;
  if(!dladdr(symbol,&definition)||!definition.dli_fname||!definition.dli_sname||
     definition.dli_saddr!=symbol||strcmp(definition.dli_sname,DIR_KERNEL_LOGGER_SYMBOL))
    return dir_error(EPROTO);
  const char *name=strrchr(definition.dli_fname,'/');
  name=name?name+1:definition.dli_fname;
  if(strcmp(name,"libbase.so")||definition.dli_fname[0]!='/'||
     strnlen(definition.dli_fname,257)>256)return dir_error(EPROTO);
  for(const unsigned char *p=(const unsigned char *)definition.dli_fname;*p;++p)
    if(*p<0x21||*p>0x7e)return dir_error(EPROTO);
  dir_kernel_logger logger;
  _Static_assert(sizeof(logger)==sizeof(symbol),"native function-pointer representation differs");
  memcpy(&logger,&symbol,sizeof(logger));
  if(dir_prime_log((int)fd,nonce_text,logger))return -1;
  /* Retain the actual defining object path as an observation. Its bytes/build
   * are not certified by dladdr and must not be claimed as read here. */
  char observation[512];int length=snprintf(observation,sizeof(observation),
    "P4_INIT_LOG_DEFINITION_V1 object=%s symbol=%s",definition.dli_fname,DIR_KERNEL_LOGGER_SYMBOL);
  if(length<=0||(size_t)length>=sizeof(observation))return dir_error(EOVERFLOW);
  off_t before=lseek((int)fd,0,SEEK_CUR);if(before<0)return -1;
  logger(0,2,"droidloom-init-log",__FILE__,0,observation);
  off_t after=lseek((int)fd,0,SEEK_CUR);if(after<0)return -1;
  return after==before+(off_t)(strlen("<6>droidloom-init-log: ")+(size_t)length+1)?0:dir_error(EPROTO);
}
__attribute__((visibility("default"))) uint32_t droidloom_init_relay_barrier_abi(void) { return DIR_ABI; }
#ifndef DROIDLOOM_BARRIER_TESTING
__attribute__((constructor(101))) static void dir_constructor(void) {
  const char *required=getenv(DIR_REQUIRED_ENV),*abi=getenv(DIR_ABI_ENV),*fdtext=getenv(DIR_FD_ENV);
  const char *nonce_text=getenv(DIR_NONCE_ENV),*timeout=getenv(DIR_TIMEOUT_ENV);
  if(!required&&!abi&&!fdtext&&!nonce_text&&!timeout&&
     !getenv(DIR_LOG_ABI_ENV)&&!getenv(DIR_LOG_FD_ENV))return;
  unsigned fd=0,ms=0;unsigned char nonce[32];
  const char *marker=getenv("DROIDLOOM_CELL");
  if(!required||strcmp(required,"1")||!abi||strcmp(abi,DIR_ABI_TEXT)||!marker||strcmp(marker,"1")||
     getpid()!=1||getuid()!=0||geteuid()!=0||getgid()!=0||getegid()!=0||dir_second_stage()||
     dir_parse_decimal(fdtext,1023,&fd)||fd<3||dir_parse_decimal(timeout,20000,&ms)||ms<10||dir_nonce(nonce_text,nonce)) {
    static const char message[]="Droidloom init relay bootstrap contract rejected\n";
    ssize_t logged = write(STDERR_FILENO, message, sizeof(message) - 1);
    (void)logged;
    _exit(127);
  }
  struct dir_failure failure;
  if(dir_setup_log(nonce_text)) {
    int first=errno?errno:EPROTO;
    char message[160];int length=snprintf(message,sizeof(message),
      "Droidloom init diagnostic logger setup failed closed errno=%d\n",first);
    if(length>0&&(size_t)length<sizeof(message)){
      ssize_t logged=write(STDERR_FILENO,message,(size_t)length);(void)logged;
    }
    _exit(127);
  }
  const struct dir_operations operations={dir_collect_real,dir_project_real,dir_finish_real,&failure};
  if(dir_run((int)fd,nonce,ms,0,&operations,&failure)) {
    char message[320];int length=dir_failure_line(message,sizeof(message),&failure);
    static const char fallback[]="Droidloom init relay bootstrap failed closed diagnostic-unavailable\n";
    ssize_t logged = length>0?write(STDERR_FILENO,message,(size_t)length):
      write(STDERR_FILENO,fallback,sizeof(fallback)-1);
    (void)logged;
    _exit(127);
  }
}
#endif
