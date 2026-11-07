/* Actual owned temporary directories and production projection code. The root
 * path and mount syscall alone are explicit seams. No namespace or mount is
 * created, and this does not qualify Android or kernel socket projection. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>

static int fixture_root=-1,mount_calls=0,mount_error=EINVAL,mount_contract=0;
static int test_open(const char *path,int flags,...) {
  if(!strcmp(path,"/"))return fcntl(fixture_root,F_DUPFD_CLOEXEC,3);
  mode_t mode=0;
  if(flags&O_CREAT){va_list args;va_start(args,flags);mode=(mode_t)va_arg(args,int);va_end(args);}
  return open(path,flags,mode);
}
static int test_mount(const char *source,const char *target,const char *kind,
                      unsigned long flags,const void *data) {
  ++mount_calls;
  mount_contract=!strcmp(source,"/proc/self/fd/54")&&
    !strncmp(target,"/proc/self/fd/",14)&&strstr(target,"/droidloom-lmkd-psi")&&
    kind==NULL&&flags==MS_BIND&&data==NULL;
  if(mount_error){errno=mount_error;return -1;}return 0;
}
static int test_close(int fd) {
  int result=close(fd);errno=EBADF;return result;
}
#define open test_open
#define mount test_mount
#define close test_close
#define DROIDLOOM_BARRIER_TESTING 1
#include "init_relay_barrier.c"
#undef open
#undef mount
#undef close

static const char *const names[]={"root_group_write_rejected_with_metadata",
  "dev_world_write_rejected_with_metadata","sockets_group_write_rejected_with_metadata",
  "preexisting_target_rejected","mount_errno_survives_close_errors",
  "mounted_non_socket_rejected_with_metadata"};
static const char *const expected_stage[]={"project-root-policy","project-dev-policy",
  "project-sockets-policy","project-target-create","project-bind-mount","project-mounted-policy"};
static const int expected_error[]={EPERM,EPERM,EPERM,EEXIST,EINVAL,EPROTO};

int main(void) {
  if(geteuid()!=0||getegid()!=0){fputs("diagnostic controls require owned root metadata\n",stderr);return 77;}
  for(size_t which=0;which<sizeof(names)/sizeof(names[0]);++which){
    char path[]="/tmp/p4-init-project-diag-XXXXXX";
    if(!mkdtemp(path))return 2;
    fixture_root=open(path,O_PATH|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(fixture_root<0||mkdirat(fixture_root,"dev",0700))return 2;
    int dev=openat(fixture_root,"dev",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(dev<0||mkdirat(dev,"socket",0700))return 2;
    int sockets=openat(dev,"socket",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(sockets<0)return 2;
    if(which==0&&chmod(path,0770))return 2;
    if(which==1&&fchmod(dev,0702))return 2;
    if(which==2&&fchmod(sockets,0770))return 2;
    if(which==3){int target=openat(sockets,DIR_SOCKET_NAME,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(target<0)return 2;close(target);}
    mount_calls=0;mount_contract=0;mount_error=which==5?0:EINVAL;
    struct dir_failure failure;memset(&failure,0,sizeof(failure));
    unsigned char wire[DIR_WIRE_SIZE]={0};
    int rc=dir_project_real(54,wire,&failure),original=errno;
    failure.error=original;
    char line[320];int length=dir_failure_line(line,sizeof(line),&failure);
    unsigned want_metadata=(which<3||which==5)?1:0;
    int ok=rc==-1&&original==expected_error[which]&&
      !strcmp(failure.stage,expected_stage[which])&&failure.metadata==want_metadata&&
      mount_calls==(which>=4?1:0)&&(which<4||mount_contract)&&
      length>0&&length<320&&line[length-1]=='\n';
    if(want_metadata)ok=ok&&failure.uid==0&&failure.gid==0&&failure.inode!=0;
    if(which<3)ok=ok&&S_ISDIR(failure.mode)&&(failure.mode&0022);
    if(which==5)ok=ok&&S_ISREG(failure.mode);
    if(fchmod(sockets,0700)||fchmod(dev,0700)||chmod(path,0700))return 2;
    if(unlinkat(sockets,DIR_SOCKET_NAME,0)&&errno!=ENOENT)return 2;
    close(sockets);if(unlinkat(dev,"socket",AT_REMOVEDIR))return 2;
    close(dev);if(unlinkat(fixture_root,"dev",AT_REMOVEDIR))return 2;
    close(fixture_root);fixture_root=-1;if(rmdir(path))return 2;
    printf("{\"case\":\"%s\",\"ok\":%s}\n",names[which],ok?"true":"false");
    if(!ok)return 1;
  }
  struct dir_failure bounds={.stage="project-mounted-policy",.error=2147483647,
    .metadata=1,.device=UINT64_MAX,.inode=UINT64_MAX,.uid=UINT32_MAX,.gid=UINT32_MAX,.mode=UINT32_MAX};
  char line[320],tiny[2]={'X','Y'};int length=dir_failure_line(line,sizeof(line),&bounds);
  int ok=length>0&&length<320&&dir_failure_line(tiny,1,&bounds)==-1&&tiny[1]=='Y';
  printf("{\"case\":\"failure_line_bounded\",\"ok\":%s}\n",ok?"true":"false");
  if(!ok)return 1;
  puts("{\"ok\":true,\"owned_diagnostic_controls_passed\":7,\"Android_executed\":false,\"kernel_mount_executed\":false}");
  return 0;
}
