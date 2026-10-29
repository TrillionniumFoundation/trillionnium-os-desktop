// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

struct state {
    _Atomic int target_ready, rescue_ready, watchdog_ready, start_rt, rt_ready;
    _Atomic int begin_move, cpu, stop, rescue_started, rescue_done, rescue_rc;
    _Atomic int rescue_errno, watchdog_killed, controller_returned, saw_blocked_controller, rescue_saw_fifo;
};
static int failures, source, destination;
static uint64_t now(void) {
    struct timespec t; if (clock_gettime(CLOCK_MONOTONIC, &t)) _exit(90);
    return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
}
static void sleep_ns(uint64_t ns) {
    struct timespec t={(time_t)(ns/1000000000ULL),(long)(ns%1000000000ULL)};
    while (nanosleep(&t,&t) && errno==EINTR) {}
}
static int cpu(void) {
    unsigned c=UINT32_MAX; return syscall(SYS_getcpu,&c,NULL,NULL) ? -1 : (int)c;
}
static int pin(pid_t pid,int c) {
    cpu_set_t mask; CPU_ZERO(&mask); CPU_SET(c,&mask);
    return sched_setaffinity(pid,sizeof(mask),&mask);
}
static int await(_Atomic int *p, uint64_t timeout) {
    uint64_t end=now()+timeout;
    while (now()<end) { if (atomic_load(p)) return 1; sleep_ns(1000000); }
    return 0;
}
static void check(const char *name,int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n",name,ok?"true":"false"); failures+=!ok;
}
static int join(pid_t pid) {
    int status; return pid>0 && waitpid(pid,&status,0)==pid && WIFEXITED(status) && WEXITSTATUS(status)==0;
}
int main(void) {
    setbuf(stdout,NULL); alarm(12);
    cpu_set_t allowed; int cpus[2],n=0;
    if (!sched_getaffinity(0,sizeof(allowed),&allowed))
        for(int i=0;i<CPU_SETSIZE && n<2;i++) if(CPU_ISSET(i,&allowed)) cpus[n++]=i;
    check("rt_admin_setup_two_cpus",n==2); if(n!=2)return 42;
    source=cpus[0]; destination=cpus[1];
    struct state *s=mmap(NULL,sizeof(*s),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
    if(s==MAP_FAILED)return 43;
    atomic_store(&s->cpu,-1); atomic_store(&s->rescue_rc,-2);
    int parent_ready=!pin(0,destination); sleep_ns(10000000);
    check("rt_admin_controller_on_destination",parent_ready && cpu()==destination);
    pid_t target=fork();
    if(!target) {
        alarm(8); if(pin(0,source))_exit(91); sleep_ns(10000000);
        if(cpu()!=source)_exit(92);
        atomic_store(&s->target_ready,1);
        if(!await(&s->start_rt,2000000000ULL))_exit(93);
        struct sched_param p={.sched_priority=80};
        if(sched_setscheduler(0,SCHED_FIFO,&p))_exit(94);
        atomic_store(&s->rt_ready,1);
        while(!atomic_load(&s->stop))atomic_store(&s->cpu,cpu());
        _exit(0);
    }
    pid_t rescuer=fork();
    if(!rescuer) {
        alarm(8); if(pin(0,source))_exit(95); sleep_ns(10000000);
        if(cpu()!=source)_exit(96);
        atomic_store(&s->rescue_ready,1);
        if(!await(&s->begin_move,2000000000ULL))_exit(97);
        uint64_t end=now()+1000000000ULL;
        while(now()<end && atomic_load(&s->cpu)!=destination)sleep_ns(1000000);
        if(atomic_load(&s->cpu)!=destination)_exit(98);
        sleep_ns(25000000);
        atomic_store(&s->saw_blocked_controller,!atomic_load(&s->controller_returned));
        atomic_store(&s->rescue_saw_fifo,sched_getscheduler(target)==SCHED_FIFO);
        atomic_store(&s->rescue_started,1);
        struct sched_param p={.sched_priority=0}; errno=0;
        int rc=sched_setscheduler(target,SCHED_OTHER,&p);
        atomic_store(&s->rescue_errno,errno); atomic_store(&s->rescue_rc,rc);
        atomic_store(&s->rescue_done,1); _exit(0);
    }
    pid_t watchdog=fork();
    if(!watchdog) {
        alarm(8); if(pin(0,source))_exit(99); sleep_ns(10000000);
        if(cpu()!=source)_exit(100);
        atomic_store(&s->watchdog_ready,1);
        if(!await(&s->begin_move,2000000000ULL))_exit(101);
        if(!await(&s->rescue_done,1500000000ULL)) {
            atomic_store(&s->watchdog_killed,1); kill(target,SIGKILL);
        }
        _exit(0);
    }
    int ready=target>0 && rescuer>0 && watchdog>0 &&
        await(&s->target_ready,1000000000ULL) && await(&s->rescue_ready,1000000000ULL) &&
        await(&s->watchdog_ready,1000000000ULL);
    check("rt_admin_helpers_ready_before_rt",ready);
    atomic_store(&s->start_rt,1);
    int rt=ready && await(&s->rt_ready,1000000000ULL);
    uint64_t end=now()+200000000ULL;
    while(now()<end && atomic_load(&s->cpu)!=source)sleep_ns(1000000);
    check("rt_admin_target_fifo_busy_on_source",rt && atomic_load(&s->cpu)==source);
    atomic_store(&s->begin_move,1); errno=0; int moved=pin(target,destination);
    atomic_store(&s->controller_returned,1);
    int rescued=await(&s->rescue_done,200000000ULL);
    check("rt_admin_force_returned_and_actual_destination",moved==0 && atomic_load(&s->cpu)==destination);
    check("rt_admin_other_writer_proceeds_while_target_runs_fifo_on_destination",rescued &&
        atomic_load(&s->rescue_started) && atomic_load(&s->rescue_saw_fifo) &&
        atomic_load(&s->rescue_rc)==0 && !atomic_load(&s->watchdog_killed));
    check("rt_admin_policy_readback_normal",sched_getscheduler(target)==SCHED_OTHER);
    printf("{\"mode\":\"rt_admin\",\"source\":%d,\"destination\":%d,\"getcpu\":%d,\"rescue_rc\":%d,\"rescue_errno\":%d,\"watchdog_killed\":%d,\"controller_had_not_returned_at_rescue\":%d}\n",
        source,destination,atomic_load(&s->cpu),atomic_load(&s->rescue_rc),atomic_load(&s->rescue_errno),atomic_load(&s->watchdog_killed),atomic_load(&s->saw_blocked_controller));
    atomic_store(&s->stop,1);
    check("rt_admin_target_join",join(target)); check("rt_admin_rescuer_join",join(rescuer));
    check("rt_admin_watchdog_join",join(watchdog)); munmap(s,sizeof(*s));
    return failures?42:0;
}
