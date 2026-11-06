/* Actual owned memfd/fd/env/exec controls. KernelLogger is an explicit seam;
 * no Android library, namespace, root service or production constructor runs. */
#define DROIDLOOM_BARRIER_TESTING
#include "../candidate/android/init_relay_barrier.c"
#include <dirent.h>
#include <sys/mman.h>
#include <sys/wait.h>

static unsigned assertions;
#define CHECK(x) do { ++assertions; if(!(x)) { \
  fprintf(stderr,"control failed line=%d expression=%s errno=%d\n",__LINE__,#x,errno); exit(1); \
} } while(0)

struct owned { int master,writer; };
static int cached=-1,called=0;
static void cached_logger(int id,int level,const char *tag,const char *file,unsigned line,const char *message) {
  (void)file;(void)line;
  CHECK(id==0&&level==2&&!strcmp(tag,"droidloom-init-log"));
  if(cached<0) {
    const char *value=getenv("ANDROID_FILE__dev_kmsg");unsigned fd;
    CHECK(value&&dir_parse_decimal(value,1023,&fd)==0);
    cached=(int)fd;
  }
  char raw[512];int length=snprintf(raw,sizeof(raw),"<6>%s: %s\n",tag,message);
  CHECK(length>0&&(size_t)length<sizeof(raw));
  CHECK(write(cached,raw,(size_t)length)==length);
  ++called;
}
static void noop_logger(int a,int b,const char*c,const char*d,unsigned e,const char*f) {
  (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;++called;
}
static void uncached_logger(int id,int level,const char *tag,const char *file,unsigned line,const char *message) {
  if(!getenv("ANDROID_FILE__dev_kmsg")){++called;return;}
  cached_logger(id,level,tag,file,line,message);
}
static void closed_logger(int a,int b,const char*c,const char*d,unsigned e,const char*f) {
  (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;
  CHECK(close((int)DIR_LOG_FD)==0);++called;
}
static struct owned create(int with_seals) {
  struct owned o={-1,-1};
  CHECK(fcntl((int)DIR_LOG_FD,F_GETFD)<0&&errno==EBADF);
  o.master=memfd_create("owned-init-log-control",MFD_CLOEXEC|MFD_ALLOW_SEALING);
  CHECK(o.master>=3);
  CHECK(fchmod(o.master,0600)==0&&ftruncate(o.master,DIR_LOG_CAPACITY)==0);
  if(with_seals)CHECK(fcntl(o.master,F_ADD_SEALS,F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL)==0);
  char path[64];int n=snprintf(path,sizeof(path),"/proc/self/fd/%d",o.master);
  CHECK(n>0&&(size_t)n<sizeof(path));
  int opened=open(path,O_WRONLY|O_NONBLOCK|O_CLOEXEC);CHECK(opened>=3);
  CHECK(dup3(opened,(int)DIR_LOG_FD,O_CLOEXEC)==(int)DIR_LOG_FD);CHECK(close(opened)==0);
  o.writer=(int)DIR_LOG_FD;return o;
}
static void destroy(struct owned *o) {
  if(o->writer>=0){CHECK(close(o->writer)==0);o->writer=-1;}
  if(o->master>=0){CHECK(close(o->master)==0);o->master=-1;}
  CHECK(unsetenv("ANDROID_FILE__dev_kmsg")==0);
  CHECK(unsetenv(DIR_LOG_ABI_ENV)==0&&unsetenv(DIR_LOG_FD_ENV)==0);
  cached=-1;called=0;
}
static int fd_count(void) {
  DIR *d=opendir("/proc/self/fd");CHECK(d!=NULL);int count=0;
  struct dirent *e;while((e=readdir(d)))if(e->d_name[0]!='.')++count;
  CHECK(closedir(d)==0);return count;
}
static void child_exec(const char *self) {
  pid_t child=fork();CHECK(child>=0);
  if(child==0){execl(self,self,"--verify-exec",NULL);_exit(125);}
  int status;CHECK(waitpid(child,&status,0)==child);
  CHECK(WIFEXITED(status)&&WEXITSTATUS(status)==0);
}

int main(int argc,char **argv) {
  if(argc==2&&!strcmp(argv[1],"--verify-exec")) {
    return (getenv("ANDROID_FILE__dev_kmsg")||getenv(DIR_LOG_ABI_ENV)||getenv(DIR_LOG_FD_ENV)||
      fcntl((int)DIR_LOG_FD,F_GETFD)>=0||errno!=EBADF)?1:0;
  }
  CHECK(argc==1);int before=fd_count();
  const char *nonce="0707070707070707070707070707070707070707070707070707070707070707";
  struct owned o=create(1);
  CHECK(setenv(DIR_LOG_ABI_ENV,"1",1)==0&&setenv(DIR_LOG_FD_ENV,"202",1)==0);
  CHECK(dir_prime_log(o.writer,nonce,cached_logger)==0&&called==2);
  CHECK(!getenv("ANDROID_FILE__dev_kmsg")&&!getenv(DIR_LOG_ABI_ENV)&&!getenv(DIR_LOG_FD_ENV));
  CHECK((fcntl(o.writer,F_GETFD)&FD_CLOEXEC)!=0);
  off_t primed=lseek(o.writer,0,SEEK_CUR);CHECK(primed>0);
  char expected[256],actual[256]={0};
  int n=snprintf(expected,sizeof(expected),"<6>droidloom-init-log: P4_INIT_LOG_V1 nonce=%s\n<6>droidloom-init-log: P4_INIT_LOG_CACHED_V1 nonce=%s\n",nonce,nonce);
  CHECK(primed==n&&pread(o.master,actual,(size_t)n,0)==n&&!memcmp(actual,expected,(size_t)n));
  cached_logger(0,2,"droidloom-init-log","seam",0,"cache-after-env-removal");
  CHECK(lseek(o.writer,0,SEEK_CUR)>primed&&called==3);
  child_exec(argv[0]);destroy(&o);CHECK(fd_count()==before);

  o=create(1);CHECK(dir_prime_log(o.writer,nonce,noop_logger)<0&&errno==EPROTO&&called==1);
  CHECK(!getenv("ANDROID_FILE__dev_kmsg"));destroy(&o);CHECK(fd_count()==before);

  o=create(1);CHECK(dir_prime_log(o.writer,nonce,uncached_logger)<0&&errno==EPROTO&&called==2);
  CHECK(!getenv("ANDROID_FILE__dev_kmsg")&&!getenv(DIR_LOG_ABI_ENV)&&!getenv(DIR_LOG_FD_ENV));
  destroy(&o);CHECK(fd_count()==before);

  o=create(1);CHECK(dir_prime_log(o.writer,nonce,closed_logger)<0&&errno==EBADF&&called==1);
  o.writer=-1;CHECK(!getenv("ANDROID_FILE__dev_kmsg"));destroy(&o);CHECK(fd_count()==before);

  o=create(0);CHECK(dir_log_writer(o.writer)<0&&errno==EPROTO);
  destroy(&o);CHECK(fd_count()==before);

  o=create(1);CHECK(dir_log_writer(o.master)<0&&errno==EPROTO);
  CHECK(write(o.writer,"x",1)==1);CHECK(dir_log_writer(o.writer)<0&&errno==EPROTO);
  destroy(&o);CHECK(fd_count()==before);

  o=create(1);CHECK(setenv("ANDROID_FILE__dev_kmsg","777",1)==0);
  CHECK(dir_prime_log(o.writer,nonce,cached_logger)<0&&errno==EPROTO&&called==0);
  CHECK(lseek(o.writer,0,SEEK_CUR)==0);destroy(&o);CHECK(fd_count()==before);

  o=create(1);unsigned char *fill=malloc(DIR_LOG_CAPACITY);CHECK(fill!=NULL);
  memset(fill,0x61,DIR_LOG_CAPACITY);
  CHECK(write(o.writer,fill,DIR_LOG_CAPACITY)==DIR_LOG_CAPACITY);free(fill);
  CHECK(write(o.writer,"x",1)<0&&errno==EPERM);
  CHECK(ftruncate(o.master,DIR_LOG_CAPACITY+1)<0&&errno==EPERM);
  CHECK(ftruncate(o.master,1)<0&&errno==EPERM);
  CHECK(lseek(o.writer,0,SEEK_CUR)==DIR_LOG_CAPACITY);
  unsigned char ends[2];CHECK(pread(o.master,&ends[0],1,0)==1&&
    pread(o.master,&ends[1],1,DIR_LOG_CAPACITY-1)==1&&ends[0]==0x61&&ends[1]==0x61);
  destroy(&o);CHECK(fd_count()==before);

  CHECK(dir_setup_log(nonce)==0);CHECK(setenv(DIR_LOG_ABI_ENV,"1",1)==0);
  CHECK(dir_setup_log(nonce)<0&&errno==EPROTO);CHECK(unsetenv(DIR_LOG_ABI_ENV)==0);
  o=create(1);CHECK(setenv(DIR_LOG_ABI_ENV,"1",1)==0&&setenv(DIR_LOG_FD_ENV,"202",1)==0);
  CHECK(dir_setup_log(nonce)<0&&errno==ENOSYS);
  destroy(&o);CHECK(fd_count()==before);
  printf("{\"controls\":9,\"assertions\":%u,\"real_memfd\":true,\"real_child_exec\":true,"
         "\"kernel_logger_call\":\"explicit fixture seam\",\"android_or_namespace_executed\":false,"
         "\"all_owned_fds_closed\":true,\"success\":true}\n",assertions);
  return 0;
}
