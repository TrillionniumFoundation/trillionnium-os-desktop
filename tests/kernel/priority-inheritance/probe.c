// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <linux/capability.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

struct attr {
    uint32_t size, policy; uint64_t flags; int32_t nice; uint32_t priority;
    uint64_t runtime, deadline, period; uint32_t util_min, util_max;
};
_Static_assert(sizeof(struct attr)==56, "Linux scheduling attribute ABI");
static int failures;
static const char *outer_name="setup";
static void check(const char *s, const char *part, int ok) {
    printf("{\"case\":\"priority_%s_%s_%s\",\"passed\":%s}\n",outer_name,s,part,ok?"true":"false");
    failures += !ok;
}
static void must(int ok) { if (!ok) _exit(80); }
static int getattr(pid_t tid, struct attr *a) {
    memset(a,0,sizeof(*a)); return syscall(SYS_sched_getattr,tid,a,sizeof(*a),0);
}
static void set_attr(int policy,int nice,int prio) {
    struct attr a={.size=sizeof(a),.policy=policy,.nice=nice,.priority=prio};
    must(!syscall(SYS_sched_setattr,0,&a,0));
}
static void drop_caps(uid_t uid) {
    if (uid) must(!syscall(SYS_setresuid,uid,uid,uid));
    struct __user_cap_header_struct h={.version=_LINUX_CAPABILITY_VERSION_3};
    struct __user_cap_data_struct d[2]={{0},{0}};
    must(!syscall(SYS_capset,&h,d));
}
static void limits(rlim_t nice) {
    struct rlimit r={nice,nice}; must(!setrlimit(RLIMIT_NICE,&r));
}
static void prepare(int policy,int nice,int prio,rlim_t limit) {
    limits(limit); set_attr(SCHED_OTHER,nice,0);
    if (policy!=SCHED_OTHER) set_attr(policy,0,prio);
}
static void observe(const char *s,pid_t tid,int policy,int nice,int prio) {
    struct attr a; int rc=getattr(tid,&a);
    check(s,"attributes",!rc && a.policy==(unsigned)policy && a.nice==nice && a.priority==(unsigned)prio);
    errno=0; int got=getpriority(PRIO_PROCESS,tid),error=errno;
    check(s,"getpriority",!error && got==nice);
}
static void proc_observe(const char *s,pid_t tid,int policy,int nice,int prio) {
    char path[100],buf[4096]; snprintf(path,sizeof(path),"/proc/self/task/%d/stat",tid);
    FILE *f=fopen(path,"r"); int ok=f && fgets(buf,sizeof(buf),f);
    if (f) fclose(f);
    if (!ok) { check(s,"proc_stat",0); return; }
    char *tail=strrchr(buf,')'); if (!tail) { check(s,"proc_stat",0); return; }
    char *save=NULL,*v=strtok_r(tail+2," ",&save); long n=999,r=999,p=999;
    for (int field=3;v;field++,v=strtok_r(NULL," ",&save)) {
        if (field==19) n=strtol(v,NULL,10);
        if (field==40) r=strtol(v,NULL,10);
        if (field==41) p=strtol(v,NULL,10);
    }
    check(s,"proc_stat",n==nice && r==prio && p==policy);
}
static int joined(pid_t p) { int status;return waitpid(p,&status,0)==p && WIFEXITED(status) && !WEXITSTATUS(status); }
struct simple { const char *name; int policy,nice,prio,new_nice,error,privileged,uid_zero; rlim_t limit; };
static void simple_case(const struct simple *s) {
    prepare(s->policy,s->nice,s->prio,s->limit);
    if (!s->privileged) drop_caps(s->uid_zero?0:2001);
    char before[100];snprintf(before,sizeof(before),"%s_before",s->name);
    observe(before,0,s->policy,s->nice,s->prio);
    proc_observe(before,(pid_t)syscall(SYS_gettid),s->policy,s->nice,s->prio);
    errno=0; int rc=setpriority(PRIO_PROCESS,0,s->new_nice),error=errno;
    check(s->name,"result",s->error?rc==-1 && error==s->error:rc==0);
    int expected=s->error?s->nice:s->new_nice;
    if (expected>19) expected=19;
    if (expected< -20) expected=-20;
    observe(s->name,0,s->policy,expected,s->prio);
    proc_observe(s->name,(pid_t)syscall(SYS_gettid),s->policy,expected,s->prio);
}
static void *inherit_thread(void *arg) {
    int *p=arg; observe("clone_thread",0,p[0],8,p[1]);
    proc_observe("clone_thread",(pid_t)syscall(SYS_gettid),p[0],8,p[1]);
    return NULL;
}
static void inheritance(int policy) {
    int prio=policy==SCHED_FIFO?10:0;
    prepare(policy,8,prio,0); drop_caps(2001);
    observe("parent_before_fork",0,policy,8,prio);
    fflush(NULL); pid_t child=fork(); must(child>=0);
    if (!child) {
        failures=0; observe("fork_child",0,policy,8,prio);
        proc_observe("fork_child",(pid_t)syscall(SYS_gettid),policy,8,prio);
        _exit(failures?42:0);
    }
    check("fork_child","reaped_success",joined(child));
    int p[2]={policy,prio}; pthread_t t;
    must(!pthread_create(&t,NULL,inherit_thread,p)); must(!pthread_join(t,NULL));
    observe("parent_after_clone",0,policy,8,prio);
}
struct worker { int ready[2],go[2],uid,nice; };
static void *target_worker(void *arg) {
    struct worker *w=arg; set_attr(SCHED_OTHER,7,0);
    pid_t tid=syscall(SYS_gettid); must(write(w->ready[1],&tid,sizeof(tid))==sizeof(tid));
    char c; must(read(w->go[0],&c,1)==1);
    observe("nonleader_target",0,SCHED_OTHER,9,0);
    errno=0; int rc=setpriority(PRIO_PROCESS,0,11);
    check("worker_who_zero","result",!rc);
    observe("worker_who_zero",0,SCHED_OTHER,11,0);
    proc_observe("worker_who_zero",tid,SCHED_OTHER,11,0);
    return NULL;
}
static void nonleader(void) {
    prepare(SCHED_OTHER,3,0,0); drop_caps(2001);
    struct worker w; must(!pipe(w.ready)&&!pipe(w.go)); pthread_t t;
    must(!pthread_create(&t,NULL,target_worker,&w)); pid_t tid;
    must(read(w.ready[0],&tid,sizeof(tid))==sizeof(tid));
    check("nonleader","distinct_tid",tid!=(pid_t)syscall(SYS_gettid));
    errno=0; int rc=setpriority(PRIO_PROCESS,tid,9);
    check("nonleader_explicit_tid","result",!rc);
    observe("nonleader_from_caller",tid,SCHED_OTHER,9,0);
    observe("leader_unchanged",0,SCHED_OTHER,3,0);
    must(write(w.go[1],"g",1)==1); must(!pthread_join(t,NULL));
    observe("leader_after_worker_who_zero",0,SCHED_OTHER,3,0);
    errno=0; rc=getpriority(PRIO_PROCESS,tid);
    check("reaped_nonleader","esrch",rc==-1&&errno==ESRCH);
}
static void *group_worker(void *arg) {
    struct worker *w=arg; drop_caps(w->uid); set_attr(SCHED_OTHER,w->nice,0);
    pid_t tid=syscall(SYS_gettid); must(write(w->ready[1],&tid,sizeof(tid))==sizeof(tid));
    char c; must(read(w->go[0],&c,1)==1); return NULL;
}
static void query(const char *name,int which,int who,int expected) {
    errno=0; int got=getpriority(which,who),error=errno;
    check(name,"aggregate",!error&&got==expected);
}
static void groups(void) {
    must(!setpgid(0,0)); prepare(SCHED_OTHER,12,0,40);
    struct worker a={.uid=6001,.nice=4},b={.uid=6002,.nice=9}; pthread_t ta,tb;
    must(!pipe(a.ready)&&!pipe(a.go)&&!pipe(b.ready)&&!pipe(b.go));
    must(!pthread_create(&ta,NULL,group_worker,&a));must(!pthread_create(&tb,NULL,group_worker,&b));
    pid_t at,bt;must(read(a.ready[0],&at,sizeof(at))==sizeof(at));must(read(b.ready[0],&bt,sizeof(bt))==sizeof(bt));
    drop_caps(6001);struct rlimit r={0,40};must(!setrlimit(RLIMIT_NICE,&r));
    query("group_minimum",PRIO_PGRP,0,4);query("own_user_minimum",PRIO_USER,0,4);query("other_thread_user",PRIO_USER,6002,9);
    errno=0;int rc=setpriority(PRIO_USER,0,8);
    check("user_partial_resource","eacces",rc==-1&&errno==EACCES);
    observe("partial_resource_leader",0,SCHED_OTHER,12,0);observe("partial_resource_permitted",at,SCHED_OTHER,8,0);observe("partial_resource_other_user",bt,SCHED_OTHER,9,0);
    errno=0;rc=setpriority(PRIO_USER,6001,15);check("matching_user_update","success",!rc);
    observe("user_update_leader",0,SCHED_OTHER,15,0);observe("user_update_matching_thread",at,SCHED_OTHER,15,0);observe("user_update_other_thread",bt,SCHED_OTHER,9,0);
    errno=0;rc=setpriority(PRIO_PGRP,0,16);check("group_partial_owner","eperm",rc==-1&&errno==EPERM);
    observe("group_update_leader",0,SCHED_OTHER,16,0);observe("group_update_matching_thread",at,SCHED_OTHER,16,0);observe("group_denied_foreign_thread",bt,SCHED_OTHER,9,0);
    query("group_minimum_after_partial",PRIO_PGRP,0,9);query("own_user_after_partial",PRIO_USER,0,16);query("other_user_after_partial",PRIO_USER,6002,9);
    errno=0;rc=getpriority(PRIO_USER,6109);check("unmatched_user","esrch",rc==-1&&errno==ESRCH);
    must(write(a.go[1],"s",1)==1&&write(b.go[1],"s",1)==1);must(!pthread_join(ta,NULL)&&!pthread_join(tb,NULL));
}
static void foreign(void) {
    int ready[2],stop[2];must(!pipe(ready)&&!pipe(stop));fflush(NULL);pid_t target=fork();must(target>=0);
    if (!target) {drop_caps(2001);char c;must(write(ready[1],"r",1)==1&&read(stop[0],&c,1)==1);_exit(0);}
    char c;must(read(ready[0],&c,1)==1);
    for (int kind=0;kind<4;kind++) {
        fflush(NULL);pid_t actor=fork();must(actor>=0);
        if (!actor) {
            failures=0;const char *name=kind==0?"different_uid":kind==1?"uid_zero_without_cap":kind==2?"same_owner":"capable_foreign";
            if (kind<3) drop_caps(kind==0?2002:kind==1?0:2001);
            int value=kind==3?-5:5;errno=0;int rc=setpriority(PRIO_PROCESS,target,value),error=errno;
            check(name,"authorization",kind<2?rc==-1&&error==EPERM:rc==0);
            observe(name,target,SCHED_OTHER,kind<2?0:value,0);_exit(failures?42:0);
        }
        char actor_name[40];snprintf(actor_name,sizeof(actor_name),"foreign_actor_%d",kind);
        check(actor_name,"reaped_success",joined(actor));
        struct attr a={.size=sizeof(a),.policy=SCHED_OTHER,.nice=0};must(!syscall(SYS_sched_setattr,target,&a,0));
    }
    must(write(stop[1],"s",1)==1);check("foreign_target","reaped_success",joined(target));
}
int main(void) {
    setvbuf(stdout,NULL,_IOLBF,0);alarm(90);if (geteuid()) return 77;
    const struct simple cases[]={
        {.name="attr_then_priority",.nice=8,.new_nice=8},
        {.name="same_owner_lower",.new_nice=5},
        {.name="same_nice",.new_nice=0},
        {.name="denied_raise_positive",.nice=8,.new_nice=0,.error=EACCES},
        {.name="limit25_allows_minus5",.new_nice=-5,.limit=25},
        {.name="infinite_limit",.new_nice=-20,.limit=RLIM_INFINITY},
        {.name="cap_overrides_limit",.new_nice=-20,.privileged=1},
        {.name="uid_zero_no_cap_raise",.new_nice=-1,.error=EACCES,.uid_zero=1},
        {.name="clamp_high",.new_nice=100},
        {.name="rt_static_nice",.policy=SCHED_FIFO,.nice=8,.prio=10,.new_nice=9},
        {.name="idle_static_nice",.policy=SCHED_IDLE,.nice=8,.new_nice=9},
        {.name="rt_negative_static_nice",.policy=SCHED_FIFO,.nice=8,.prio=10,.new_nice=-5,.limit=25},
        {.name="idle_negative_static_nice",.policy=SCHED_IDLE,.nice=8,.new_nice=-5,.limit=25},
    };
    int bad=0;
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
        fflush(NULL);pid_t p=fork();must(p>=0);if(!p){failures=0;outer_name=cases[i].name;simple_case(&cases[i]);_exit(failures?42:0);}bad+=!joined(p);
    }
    for(int i=0;i<6;i++) {
        fflush(NULL);pid_t p=fork();must(p>=0);
        if(!p){failures=0;const char *names[]={"inherit_normal","inherit_rt","inherit_idle","nonleader","groups","foreign"};outer_name=names[i];if(i<3)inheritance(i==0?SCHED_OTHER:i==1?SCHED_FIFO:SCHED_IDLE);else if(i==3)nonleader();else if(i==4)groups();else foreign();_exit(failures?42:0);}bad+=!joined(p);
    }
    return bad?42:0;
}
