// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#define WORKERS 5
#define THREADS (WORKERS + 1)
struct shared { atomic_int futex; atomic_int returned[THREADS]; atomic_int result[THREADS]; atomic_int errors[THREADS]; int timeout_ms; };
struct ready { int kind; pid_t tid; };
struct observed { pid_t tid; char state; };
static struct shared *shared;
static int readyfd, blockedfd, failed, cases;
static pthread_barrier_t barrier;
static const char *mode;
static long long now_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (long long)t.tv_sec*1000+t.tv_nsec/1000000; }
static void check(const char *name, bool ok) { ++cases; failed+=!ok; printf("{\"suite\":\"stop_all\",\"mode\":\"%s\",\"case\":\"%s\",\"passed\":%s}\n",mode,name,ok?"true":"false"); fflush(stdout); }
static void nap(int ms) { struct timespec t={ms/1000,(ms%1000)*1000000L}; while(nanosleep(&t,&t)<0 && errno==EINTR) {} }
static void ready(int kind) { struct ready r={kind,(pid_t)syscall(SYS_gettid)}; if(write(readyfd,&r,sizeof r)!=(ssize_t)sizeof r) _exit(21); }
static void *worker(void *arg) {
 int kind=(int)(long)arg;
 pthread_barrier_wait(&barrier); ready(kind);
 for(;;) {
  if(kind==1) sched_yield();
  else {
   int result;
   if(kind==2) { struct timespec t={shared->timeout_ms/1000,(shared->timeout_ms%1000)*1000000L}; result=nanosleep(&t,NULL); }
   else if(kind==3) result=(int)syscall(SYS_futex,&shared->futex,FUTEX_WAIT,0,NULL,NULL,0);
   else if(kind==4) { char b; result=(int)read(blockedfd,&b,1); }
   else { struct pollfd p={blockedfd,POLLIN,0}; result=poll(&p,1,shared->timeout_ms==3600000?-1:shared->timeout_ms); }
   atomic_store(&shared->errors[kind],result<0?errno:0);
   atomic_store(&shared->result[kind],result);
   atomic_fetch_add(&shared->returned[kind],1);
   for(;;) pause();
  }
 }
 return NULL;
}
static void child(int ready_write,int gate_read,int block_read,bool self_stop) {
 readyfd=ready_write;blockedfd=block_read;
 pthread_t threads[WORKERS];
 if(pthread_barrier_init(&barrier,NULL,THREADS)) _exit(23);
 for(int i=0;i<WORKERS;++i) if(pthread_create(&threads[i],NULL,worker,(void *)(long)(i+1))) _exit(24);
 pthread_barrier_wait(&barrier);ready(0);
 char b; ssize_t n; do { n=read(gate_read,&b,1); } while(n<0 && errno==EINTR);
 if(n!=1) _exit(25);
 if(self_stop && kill(getpid(),SIGSTOP)) _exit(26);
 for(;;) pause();
}
static int compare(const void *a,const void *b) { pid_t x=((const struct observed*)a)->tid,y=((const struct observed*)b)->tid;return (x>y)-(x<y); }
static int snapshot(pid_t pid,struct observed *obs) {
 char path[96];snprintf(path,sizeof path,"/proc/%d/task",pid);DIR*d=opendir(path);if(!d)return -1;
 int n=0;struct dirent*e;
 while((e=readdir(d))) {
  if(e->d_name[0]=='.')continue;
  char *end;long id=strtol(e->d_name,&end,10);if(*end||id<=0||n==128){closedir(d);return -1;}
  snprintf(path,sizeof path,"/proc/%d/task/%ld/status",pid,id);FILE*f=fopen(path,"r");if(!f){closedir(d);return -1;}
  char line[512],state=0;while(fgets(line,sizeof line,f))if(!strncmp(line,"State:",6)){if(sscanf(line+6," %c",&state)!=1)state=0;break;}
  fclose(f);if(!state){closedir(d);return -1;}obs[n++]=(struct observed){(pid_t)id,state};
 }
 closedir(d);qsort(obs,(size_t)n,sizeof*obs,compare);return n;
}
static void emit(const char *stage,struct observed *obs,int n) {
 printf("{\"suite\":\"stop_all\",\"mode\":\"%s\",\"observation\":\"%s\",\"threads\":[",mode,stage);
 for(int i=0;i<n;++i)printf("%s{\"tid\":%d,\"state\":\"%c\"}",i?",":"",obs[i].tid,obs[i].state);
 puts("]}");fflush(stdout);
}
static bool matches(struct observed *obs,int n,struct ready *ids) {
 if(n!=THREADS)return false;
 for(int i=0;i<THREADS;++i){bool found=false;for(int j=0;j<n;++j)found|=ids[i].tid==obs[j].tid;if(!found)return false;}
 return true;
}
static void run(int scenario) {
 bool self_stop=scenario!=0;
 mode=scenario==0?"external":scenario==1?"self":scenario==2?"self_kill_stopped":scenario==3?"self_deadlines":scenario==4?"self_io_while_stopped":"self_thread_directed_continue";
 shared->timeout_ms=scenario==3?1000:3600000;
 for(int i=0;i<THREADS;++i){atomic_store(&shared->returned[i],0);atomic_store(&shared->result[i],-99);atomic_store(&shared->errors[i],0);}
 int rp[2],gp[2],bp[2];if(pipe(rp)||pipe(gp)||pipe(bp)){check("pipe_setup",false);return;}
 pid_t p=fork();if(p==0){close(rp[0]);close(gp[1]);close(bp[1]);child(rp[1],gp[0],bp[0],self_stop);_exit(27);}
 close(rp[1]);close(gp[0]);close(bp[0]);check("child_created",p>0);if(p<=0)return;
 struct ready ids[THREADS];int got=0;
 long long deadline=now_ms()+5000;
 while(got<THREADS && now_ms()<deadline){struct pollfd r={rp[0],POLLIN,0};if(poll(&r,1,100)>0){ssize_t n=read(rp[0],&ids[got],sizeof ids[got]);if(n!=(ssize_t)sizeof ids[got])break;++got;}}
 bool complete=got==THREADS;
 check("six_distinct_ready_tids",complete);
 if(!complete)goto cleanup;
 for(int i=0;i<THREADS;++i)for(int j=0;j<i;++j)if(ids[i].tid==ids[j].tid)complete=false;
 check("ready_tids_unique",complete);
 struct observed before[128],last[128],cur[128];int count=0;
 bool blocked=false;deadline=now_ms()+5000;
 do {
  count=snapshot(p,before);blocked=matches(before,count,ids);
  for(int i=0;i<THREADS&&blocked;++i) if(ids[i].kind!=1) {bool asleep=false;for(int j=0;j<count;++j)if(before[j].tid==ids[i].tid)asleep=before[j].state=='S';blocked&=asleep;}
  if(!blocked)nap(20);
 } while(!blocked && now_ms()<deadline);
 emit("before_stop",before,count>0?count:0);
 check("leader_and_sleep_futex_read_poll_blocked",blocked);
 bool no_returns=true;for(int i=2;i<THREADS;++i)no_returns&=atomic_load(&shared->returned[i])==0;
 check("all_blocking_calls_entered_without_return",no_returns);
 bool stop_ok=self_stop?(write(gp[1],"s",1)==1):(kill(p,SIGSTOP)==0);
 check("stop_requested",stop_ok);
 bool stopped=false;int previous=0;deadline=now_ms()+5000;
 do {
  count=snapshot(p,cur);bool all=matches(cur,count,ids);
  for(int i=0;i<count&&all;++i)all&=cur[i].state=='T';
  bool same=all&&previous==count;
  for(int i=0;i<count&&same;++i)same&=cur[i].tid==last[i].tid;
  if(same){stopped=true;break;}
  previous=all?count:0;if(all)memcpy(last,cur,(size_t)count*sizeof*cur);
  nap(20);
 } while(now_ms()<deadline);
 emit("stop_final",cur,count>0?count:0);
 check("all_six_T_twice_same_set_20ms",stopped);
 int status=0;pid_t wr=waitpid(p,&status,WUNTRACED|WNOHANG);
 check("parent_observes_SIGSTOP",wr==p&&WIFSTOPPED(status)&&WSTOPSIG(status)==SIGSTOP);
 if((wr==p && (WIFEXITED(status)||WIFSIGNALED(status))) || (wr<0 && errno==ECHILD)) {
  /* waitpid has already reaped the owned child; never signal a reused PID. */
  close(rp[0]);close(gp[1]);close(bp[1]);return;
 }
 if(scenario==2)goto cleanup;
 if(scenario==3 || scenario==4) {
  if(scenario==4)check("two_bytes_sent_while_all_stopped",write(bp[1],"ab",2)==2);
  nap(scenario==3?1200:100);
  count=snapshot(p,cur);bool held=matches(cur,count,ids);
  for(int i=0;i<count&&held;++i)held&=cur[i].state=='T';
  check("all_remain_T_after_timer_or_io_event",held);
 }
 if(self_stop) {
  bool unchanged=true;for(int i=2;i<THREADS;++i)unchanged&=atomic_load(&shared->returned[i])==0;
  check("no_blocking_call_returns_while_stopped",unchanged);
 }
 pid_t continue_tid=0;
 for(int i=0;i<THREADS;++i)if(ids[i].kind==2)continue_tid=ids[i].tid;
 check("continue_requested",scenario==5?syscall(SYS_tgkill,p,continue_tid,SIGCONT)==0:kill(p,SIGCONT)==0);
 bool resumed=false;deadline=now_ms()+3000;
 do {count=snapshot(p,cur);resumed=matches(cur,count,ids);for(int i=0;i<count&&resumed;++i)resumed&=cur[i].state!='T';if(!resumed)nap(20);}while(!resumed&&now_ms()<deadline);
 emit("after_continue",cur,count>0?count:0);
 check("all_six_leave_T",resumed);
 if(self_stop) {
  nap(scenario==3?100:250);
  if(scenario==3) {
   check("nanosleep_original_deadline_not_restarted",atomic_load(&shared->returned[2])==1&&atomic_load(&shared->result[2])==0);
   check("poll_original_deadline_not_restarted",atomic_load(&shared->returned[5])==1&&atomic_load(&shared->result[5])==0);
   check("untimed_waits_remain_blocked",atomic_load(&shared->returned[3])==0&&atomic_load(&shared->returned[4])==0);
  } else if(scenario==4) {
   check("read_event_preserved_until_continue",atomic_load(&shared->returned[4])==1&&atomic_load(&shared->result[4])==1);
   check("poll_event_preserved_until_continue",atomic_load(&shared->returned[5])==1&&atomic_load(&shared->result[5])==1);
   check("unrelated_sleep_futex_still_waiting",atomic_load(&shared->returned[2])==0&&atomic_load(&shared->returned[3])==0);
  } else if(scenario==5) {
   check("targeted_continue_keeps_original_signal_return",atomic_load(&shared->returned[2])==1&&atomic_load(&shared->result[2])==-1&&atomic_load(&shared->errors[2])==EINTR);
   check("unaddressed_blocked_threads_keep_waiting",atomic_load(&shared->returned[3])==0&&atomic_load(&shared->returned[4])==0&&atomic_load(&shared->returned[5])==0);
   check("subsequent_stop_requested",kill(p,SIGSTOP)==0);
   bool stopped_again=false;previous=0;deadline=now_ms()+5000;
   do {
    count=snapshot(p,cur);bool all=matches(cur,count,ids);
    for(int i=0;i<count&&all;++i)all&=cur[i].state=='T';
    bool same=all&&previous==count;for(int i=0;i<count&&same;++i)same&=cur[i].tid==last[i].tid;
    if(same){stopped_again=true;break;}
    previous=all?count:0;if(all)memcpy(last,cur,(size_t)count*sizeof*cur);nap(20);
   }while(now_ms()<deadline);
   emit("second_stop_after_targeted_continue",cur,count>0?count:0);
   check("old_continue_does_not_cancel_new_stop",stopped_again);
  } else {
   bool unchanged=true;for(int i=2;i<THREADS;++i)unchanged&=atomic_load(&shared->returned[i])==0;
   check("continue_preserves_blocking_calls_without_EINTR",unchanged);
  }
 }
cleanup:
 check("owned_child_killed",kill(p,SIGKILL)==0);
 int final=0;pid_t reaped;do{reaped=waitpid(p,&final,0);}while(reaped<0&&errno==EINTR);
 check("owned_child_reaped_SIGKILL",reaped==p&&WIFSIGNALED(final)&&WTERMSIG(final)==SIGKILL);
 close(rp[0]);close(gp[1]);close(bp[1]);
}
int main(void) {
 setvbuf(stdout,NULL,_IONBF,0);
 shared=mmap(NULL,sizeof*shared,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
 if(shared==MAP_FAILED)return 2;
 atomic_init(&shared->futex,0);
 for(int scenario=0;scenario<6;++scenario)run(scenario);
 printf("{\"suite\":\"stop_all\",\"cases\":%d,\"failed\":%d,\"passed\":%s}\n",cases,failed,failed?"false":"true");
 return failed?1:0;
}
