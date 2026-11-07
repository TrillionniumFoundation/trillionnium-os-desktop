/* Ordinary owned-directory controls. fstatfs is an explicit seam; no mount,
 * namespace, Android or PSI execution is claimed by these controls. */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <unistd.h>

static char fixture_root[256];
static ino_t view_ino, target_ino;
static int variant;
static int test_open(const char *path,int flags,...) {
  mode_t mode=0;
  if(flags&O_CREAT){va_list args;va_start(args,flags);mode=(mode_t)va_arg(args,int);va_end(args);}
  return open(!strcmp(path,"/")?fixture_root:path,flags,mode);
}
static int test_fstatfs(int fd,struct statfs *out) {
  int result=fstatfs(fd,out);struct stat st;
  if(result||fstat(fd,&st))return -1;
  out->f_type=st.st_ino==view_ino?0x63677270:0x01021994;
  if(variant==1&&st.st_ino==target_ino)out->f_type=0x63677270;
  if(variant==6&&st.st_ino==view_ino)out->f_type=0x01021994;
  return 0;
}
static int test_fstat(int fd,struct stat *out) {
  int result=fstat(fd,out);
  if(!result&&variant==2&&out->st_ino==target_ino)++out->st_dev;
  return result;
}
static int test_close(int fd) { int result=close(fd);errno=EBADF;return result; }
#define open test_open
#define fstatfs test_fstatfs
#define fstat test_fstat
#define close test_close
#define DROIDLOOM_BARRIER_TESTING 1
#include "init_relay_barrier.c"
#undef open
#undef fstatfs
#undef fstat
#undef close

static int fd_count(void) {
  DIR *directory=opendir("/proc/self/fd");if(!directory)return -1;
  int count=0;struct dirent *entry;
  while((entry=readdir(directory)))if(strcmp(entry->d_name,".")&&strcmp(entry->d_name,".."))++count;
  closedir(directory);return count;
}
static int path(char *out,size_t size,const char *relative) {
  int n=snprintf(out,size,"%s/%s",fixture_root,relative);
  return n>0&&(size_t)n<size?0:-1;
}
static int new_directory(const char *relative) {
  char p[512];return path(p,sizeof(p),relative)?-1:mkdir(p,0700);
}
static int new_file(const char *relative,const char *data) {
  char p[512];if(path(p,sizeof(p),relative))return -1;
  int fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)return -1;
  size_t len=strlen(data);ssize_t n=write(fd,data,len);int saved=errno;close(fd);errno=saved;
  return n==(ssize_t)len?0:-1;
}
static const char *const names[]={"holding_domain_and_stock_tmpfs_target_accepted",
  "premounted_native_cgroup_target_rejected","foreign_tmpfs_target_rejected",
  "writable_holding_rejected","symlink_domain_rejected","symlink_native_target_rejected",
  "non_cgroup_holding_view_rejected","missing_holding_preserves_errno"};
static const char *const stages[]={"collect-domain-filesystem","collect-native-target-filesystem",
  "collect-native-target-filesystem","collect-holding-policy","collect-domain-open",
  "collect-native-target-open","collect-domain-filesystem","collect-holding-open"};
static const int errors[]={0,EPROTO,EPROTO,EPERM,ENOTDIR,ENOTDIR,EPROTO,ENOENT};

static int run_case(int which) {
  char p[512],backup[512];int good=0,before=-1,after=-1;
  strcpy(fixture_root,"/tmp/p4-cgroup-view-controls-XXXXXX");
  if(!mkdtemp(fixture_root))return -1;
  variant=0;
  if(new_directory("dev")||new_directory("dev/.droidloom-cgroups")||
     new_directory("dev/.droidloom-cgroups/relay-v2")||new_directory("sys")||
     new_directory("sys/fs")||new_directory("sys/fs/cgroup")||
     new_file("dev/.droidloom-cgroups/relay-v2/memory.max","536870912\n")||
     new_file("dev/.droidloom-cgroups/relay-v2/memory.high","402653184\n")||
     new_file("dev/.droidloom-cgroups/relay-v2/memory.swap.max","0\n"))goto done;
  struct stat st;
  if(path(p,sizeof(p),"dev/.droidloom-cgroups/relay-v2")||stat(p,&st))goto done;
  view_ino=st.st_ino;
  if(path(p,sizeof(p),"sys/fs/cgroup")||stat(p,&st))goto done;
  target_ino=st.st_ino;
  if(which==3){if(path(p,sizeof(p),"dev/.droidloom-cgroups")||chmod(p,0770))goto done;}
  if(which==4||which==5||which==7){
    const char *relative=which==4?"dev/.droidloom-cgroups/relay-v2":which==5?"sys/fs/cgroup":"dev/.droidloom-cgroups";
    if(path(p,sizeof(p),relative)||snprintf(backup,sizeof(backup),"%s-held",p)<0||rename(p,backup))goto done;
    if(which!=7&&symlink(backup,p))goto done;
  }
  variant=which;
  int rights[DIR_HELLO_RIGHTS];for(size_t i=0;i<DIR_HELLO_RIGHTS;++i)rights[i]=-1;
  unsigned char wire[DIR_WIRE_SIZE];memset(wire,0,sizeof(wire));
  struct dir_failure failure={.stage="initial"};
  before=fd_count();int result=dir_collect_domain(&rights[0],wire,&failure),saved=errno;
  if(!result){
    int flags=fcntl(rights[0],F_GETFD);
    if(fstat(rights[0],&st)||st.st_ino!=view_ino||flags<0||!(flags&FD_CLOEXEC)||
       dir_get(wire,64,8)!=536870912||dir_get(wire,72,8)!=402653184||dir_get(wire,80,8)!=0)result=-2;
  }
  dir_close_rights(rights,DIR_HELLO_RIGHTS);after=fd_count();
  good=(which==0?result==0:result==-1&&saved==errors[which])&&
       !strcmp(failure.stage,stages[which])&&before>=0&&before==after;
  if(!good)fprintf(stderr,"case=%d rc=%d errno=%d stage=%s before=%d after=%d\n",
                  which,result,saved,failure.stage,before,after);
done:
  variant=0;
  if(which==4||which==5||which==7){
    const char *relative=which==4?"dev/.droidloom-cgroups/relay-v2":which==5?"sys/fs/cgroup":"dev/.droidloom-cgroups";
    if(!path(p,sizeof(p),relative)&&snprintf(backup,sizeof(backup),"%s-held",p)>0){
      if(which!=7)unlink(p);
      if(rename(backup,p)&&errno!=ENOENT)good=0;
    }
  }
  for(size_t i=0;i<3;++i){
    const char *files[]={"memory.max","memory.high","memory.swap.max"};
    char relative[128];snprintf(relative,sizeof(relative),"dev/.droidloom-cgroups/relay-v2/%s",files[i]);
    if(!path(p,sizeof(p),relative)&&unlink(p)&&errno!=ENOENT)good=0;
  }
  const char *dirs[]={"dev/.droidloom-cgroups/relay-v2","dev/.droidloom-cgroups","dev","sys/fs/cgroup","sys/fs","sys"};
  for(size_t i=0;i<sizeof(dirs)/sizeof(dirs[0]);++i)if(!path(p,sizeof(p),dirs[i])&&rmdir(p)&&errno!=ENOENT)good=0;
  if(rmdir(fixture_root))good=0;
  printf("{\"case\":\"%s\",\"ok\":%s,\"scope\":\"owned_files_with_filesystem_seam\"}\n",names[which],good?"true":"false");
  return good?0:-1;
}
int main(void) {
  if(getuid()||geteuid()||getgid()||getegid())return 2;
  for(int which=0;which<8;++which)if(run_case(which))return 1;
  printf("{\"ok\":true,\"cases\":8,\"namespace_or_mount_executed\":false}\n");return 0;
}
