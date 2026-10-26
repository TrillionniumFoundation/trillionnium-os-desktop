// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <linux/capability.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

struct linux_attr {
    uint32_t size, policy;
    uint64_t flags;
    int32_t nice;
    uint32_t priority;
    uint64_t runtime, deadline, period;
    uint32_t util_min, util_max;
};
_Static_assert(sizeof(struct linux_attr) == 56, "Linux scheduling attribute ABI");
static int failures;
static int getattr(struct linux_attr *a) {
    memset(a, 0, sizeof(*a));
    return syscall(SYS_sched_getattr, 0, a, sizeof(*a), 0);
}
static int setattr(int policy, int prio, int nice, uint64_t flags) {
    struct linux_attr a = {.size = sizeof(a), .policy = policy, .nice = nice,
                           .priority = prio, .flags = flags};
    return syscall(SYS_sched_setattr, 0, &a, 0);
}
static void check(const char *name, const char *part, int ok, int rc, int error,
                  const struct linux_attr *a) {
    printf("{\"case\":\"limits_%s_%s\",\"passed\":%s,\"rc\":%d,\"errno\":%d,"
           "\"policy\":%u,\"priority\":%u,\"nice\":%d}\n", name, part,
           ok ? "true" : "false", rc, error, a->policy, a->priority, a->nice);
    failures += !ok;
}
enum operation { ATTR, SCHEDULER, PARAM };
struct scenario {
    const char *name;
    enum operation op;
    int initial_policy, initial_prio, initial_nice;
    rlim_t rt_limit, nice_limit;
    int policy, prio, nice, expected_errno, expected_nice;
    uint64_t flags;
    int privileged, uid_zero;
};
static void exercise(const struct scenario *s) {
    struct rlimit rt = {s->rt_limit, s->rt_limit}, ni = {s->nice_limit, s->nice_limit};
    if (setrlimit(RLIMIT_RTPRIO, &rt) || setrlimit(RLIMIT_NICE, &ni)) _exit(80);
    // Set a real initial Fair nice, then optionally move into RT. Its static
    // nice must survive an eventual sched_setscheduler return to Normal.
    if (setattr(SCHED_OTHER, 0, s->initial_nice, 0)) _exit(81);
    if (s->initial_policy != SCHED_OTHER &&
        setattr(s->initial_policy, s->initial_prio, 0, 0)) _exit(82);
    if (!s->privileged) {
        if (!s->uid_zero && setresuid(2001, 2001, 2001)) _exit(83);
        struct __user_cap_header_struct h = {.version = _LINUX_CAPABILITY_VERSION_3};
        struct __user_cap_data_struct data[2] = {{0}, {0}};
        if (syscall(SYS_capset, &h, data)) _exit(84);
    }
    struct linux_attr before, after;
    if (getattr(&before)) _exit(85);
    check(s->name, "before_static_nice", before.nice == s->initial_nice, 0, 0, &before);
    struct sched_param p = {.sched_priority = s->prio};
    errno = 0;
    int rc = s->op == ATTR ? setattr(s->policy, s->prio, s->nice, s->flags) :
             s->op == SCHEDULER ? sched_setscheduler(0, s->policy, &p) : sched_setparam(0, &p);
    int error = errno;
    if (getattr(&after)) _exit(86);
    struct sched_param observed;
    int reported_policy = sched_getscheduler(0);
    int param_rc = sched_getparam(0, &observed);
    check(s->name, "getters_agree", reported_policy == (int)after.policy && !param_rc &&
          observed.sched_priority == (int)after.priority, rc, error, &after);
    int allowed = !s->expected_errno;
    check(s->name, "result", allowed ? rc == 0 : rc == -1 && error == s->expected_errno,
          rc, error, &after);
    if (allowed) {
        uint32_t expected_policy = s->op == PARAM ? before.policy : (uint32_t)s->policy;
        check(s->name, "state", after.policy == (unsigned)expected_policy &&
              after.priority == (unsigned)s->prio && after.nice == s->expected_nice,
              rc, error, &after);
    } else {
        check(s->name, "unchanged", before.policy == after.policy &&
              before.priority == after.priority && before.nice == after.nice,
              rc, error, &after);
    }
}
#define CASE(n, op_, ip, ir, in, rl, nl, p, pr, ni, err, en) \
    {.name=n, .op=op_, .initial_policy=ip, .initial_prio=ir, .initial_nice=in, \
     .rt_limit=rl, .nice_limit=nl, .policy=p, .prio=pr, .nice=ni, .expected_errno=err, .expected_nice=en}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(60);
    if (geteuid()) return 77;
    const struct scenario cases[] = {
        CASE("fifo_zero_limit", SCHEDULER, SCHED_OTHER,0,0,0,0,SCHED_FIFO,1,0,EPERM,0),
        CASE("rr_zero_limit", ATTR, SCHED_OTHER,0,0,0,0,SCHED_RR,1,0,EPERM,0),
        CASE("rt_param_raise_zero", PARAM, SCHED_FIFO,10,0,0,0,SCHED_FIFO,11,0,EPERM,0),
        CASE("rt_param_lower_zero", PARAM, SCHED_FIFO,10,0,0,0,SCHED_FIFO,5,0,0,0),
        CASE("rt_param_same_zero", PARAM, SCHED_FIFO,10,0,0,0,SCHED_FIFO,10,0,0,0),
        CASE("rt_switch_zero", SCHEDULER, SCHED_FIFO,10,0,0,0,SCHED_RR,5,0,EPERM,0),
        CASE("fifo_at_limit", SCHEDULER, SCHED_OTHER,0,0,10,0,SCHED_FIFO,10,0,0,0),
        CASE("fifo_above_limit", SCHEDULER, SCHED_OTHER,0,0,10,0,SCHED_FIFO,11,0,EPERM,0),
        CASE("rt_lower_above_limit", ATTR, SCHED_FIFO,20,0,10,0,SCHED_FIFO,15,0,0,0),
        CASE("rt_raise_above_both", ATTR, SCHED_FIFO,20,0,10,0,SCHED_FIFO,21,0,EPERM,0),
        CASE("rt_switch_nonzero", SCHEDULER, SCHED_FIFO,20,0,10,0,SCHED_RR,15,0,0,0),
        CASE("nice_raise_zero", ATTR, SCHED_OTHER,0,0,0,0,SCHED_OTHER,0,-1,EPERM,0),
        CASE("nice_at_limit", ATTR, SCHED_OTHER,0,0,0,25,SCHED_OTHER,0,-5,0,-5),
        CASE("nice_above_limit", ATTR, SCHED_OTHER,0,0,0,25,SCHED_OTHER,0,-6,EPERM,0),
        CASE("nice_lower_zero", ATTR, SCHED_OTHER,0,0,0,0,SCHED_OTHER,0,8,0,8),
        CASE("nice_same_zero", ATTR, SCHED_OTHER,0,0,0,0,SCHED_OTHER,0,0,0,0),
        CASE("normal_preserve_nice", SCHEDULER, SCHED_OTHER,0,8,0,0,SCHED_OTHER,0,0,0,8),
        CASE("normal_param_preserve_nice", PARAM, SCHED_OTHER,0,8,0,0,SCHED_OTHER,0,0,0,8),
        CASE("rt_normal_preserve_nice", SCHEDULER, SCHED_FIFO,10,8,0,0,SCHED_OTHER,0,0,0,8),
        {.name="cap_overrides_rt_limit", .op=ATTR, .policy=SCHED_RR, .prio=90, .privileged=1},
        {.name="cap_overrides_nice_limit", .op=ATTR, .policy=SCHED_OTHER, .nice=-20, .expected_nice=-20, .privileged=1},
        {.name="uid_zero_no_cap_rt", .op=ATTR, .policy=SCHED_FIFO, .prio=1, .expected_errno=EPERM, .uid_zero=1},
        {.name="uid_zero_no_cap_nice", .op=ATTR, .policy=SCHED_OTHER, .nice=-1, .expected_errno=EPERM, .uid_zero=1},
        {.name="reset_on_fork_unsupported", .op=ATTR, .flags=1, .expected_errno=EOPNOTSUPP},
        {.name="keep_policy_unsupported", .op=ATTR, .flags=8, .expected_errno=EOPNOTSUPP},
        {.name="keep_params_unsupported", .op=ATTR, .flags=16, .expected_errno=EOPNOTSUPP},
        {.name="util_min_unsupported", .op=ATTR, .flags=32, .expected_errno=EOPNOTSUPP},
        {.name="util_max_unsupported", .op=ATTR, .flags=64, .expected_errno=EOPNOTSUPP},
        {.name="unknown_flags", .op=ATTR, .flags=UINT64_C(1)<<63, .expected_errno=EINVAL},
        CASE("normal_nice19_readback", ATTR, SCHED_OTHER,0,0,0,0,SCHED_OTHER,0,19,0,19),
        CASE("declared_idle_static_nice", ATTR, SCHED_OTHER,0,8,0,0,SCHED_IDLE,0,0,0,8),
        CASE("idle_normal_with_limit", SCHEDULER, SCHED_IDLE,0,8,0,12,SCHED_OTHER,0,0,0,8),
        CASE("idle_normal_without_limit", SCHEDULER, SCHED_IDLE,0,8,0,0,SCHED_OTHER,0,0,EPERM,8),
        CASE("idle_rt_with_limits", SCHEDULER, SCHED_IDLE,0,8,10,12,SCHED_RR,5,0,0,8),
        CASE("idle_rt_without_nice_limit", SCHEDULER, SCHED_IDLE,0,8,10,0,SCHED_RR,5,0,EPERM,8),
        CASE("rt_retains_static_nice", ATTR, SCHED_OTHER,0,8,10,0,SCHED_FIFO,1,0,0,8),
        CASE("positive_nice_raise_zero", ATTR, SCHED_OTHER,0,8,0,0,SCHED_OTHER,0,0,EPERM,8),
        CASE("positive_nice_raise_with_limit", ATTR, SCHED_OTHER,0,8,0,13,SCHED_OTHER,0,7,0,7),
        CASE("nice_infinite_limit", ATTR, SCHED_OTHER,0,0,0,RLIM_INFINITY,SCHED_OTHER,0,-20,0,-20),
        CASE("rt_infinite_limit", ATTR, SCHED_OTHER,0,0,RLIM_INFINITY,0,SCHED_FIFO,99,0,0,0),

    };
    int bad = 0;
    for (unsigned i=0; i<sizeof(cases)/sizeof(cases[0]); ++i) {
        fflush(NULL); pid_t child=fork(); if (child<0) return 77;
        if (!child) { exercise(&cases[i]); _exit(failures ? 42 : 0); }
        int status;
        if (waitpid(child,&status,0)!=child || !WIFEXITED(status) || WEXITSTATUS(status)) ++bad;
    }
    return bad ? 42 : 0;
}
