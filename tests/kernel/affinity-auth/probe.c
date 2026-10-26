// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int get_cpu(void) { unsigned cpu = 0; return syscall(SYS_getcpu, &cpu, NULL, NULL) ? -1 : (int)cpu; }
static int failures;
static void check(const char *name, int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, ok ? "true" : "false");
    failures += !ok;
}
static cpu_set_t one_cpu(int cpu) {
    cpu_set_t mask; CPU_ZERO(&mask); CPU_SET(cpu, &mask); return mask;
}
static int join(pid_t pid) {
    int status = 0;
    return waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
static void authorization(int target_cpu) {
    int ready[2], go[2], report[2];
    if (pipe(ready) || pipe(go) || pipe(report)) exit(77);
    pid_t target = fork();
    if (target < 0) exit(77);
    if (!target) {
        close(ready[0]); close(go[1]); close(report[0]);
        if (setresuid(2001, 2001, 2001)) _exit(80);
        int initial = get_cpu();
        char byte;
        if (write(ready[1], &initial, sizeof(initial)) != sizeof(initial) || read(go[0], &byte, 1) != 1) _exit(81);
        int cpu = get_cpu();
        if (write(report[1], &cpu, sizeof(cpu)) != sizeof(cpu)) _exit(82);
        _exit(0);
    }
    close(ready[1]); close(go[0]); close(report[1]);
    int initial = -1;
    if (read(ready[0], &initial, sizeof(initial)) != sizeof(initial)) exit(77);
    cpu_set_t original = one_cpu(initial);
    if (sched_setaffinity(target, sizeof(original), &original)) exit(77);
    target_cpu = initial == 0 ? target_cpu : 0;
    close(ready[0]);
    pid_t attacker = fork();
    if (attacker < 0) exit(77);
    if (!attacker) {
        if (setresuid(2002, 2002, 2002)) _exit(83);
        cpu_set_t before, after, desired = one_cpu(target_cpu);
        if (sched_getaffinity(target, sizeof(before), &before)) _exit(84);
        errno = 0;
        int denied = sched_setaffinity(target, sizeof(desired), &desired);
        int error = errno;
        if (sched_getaffinity(target, sizeof(after), &after)) _exit(85);
        check("handoff_affinity_other_uid_eperm", denied < 0 && error == EPERM);
        check("handoff_affinity_denied_mask_unchanged", CPU_EQUAL(&before, &after));
        _exit(failures ? 42 : 0);
    }
    int attacker_ok = join(attacker);
    pid_t owner = fork();
    if (owner < 0) exit(77);
    if (!owner) {
        if (setresuid(2001, 2001, 2001)) _exit(88);
        cpu_set_t desired = one_cpu(target_cpu), observed;
        int accepted = !sched_setaffinity(target, sizeof(desired), &desired);
        int readable = !sched_getaffinity(target, sizeof(observed), &observed);
        check("affinity_same_owner_mask_update_allowed", accepted && readable && CPU_EQUAL(&desired, &observed));
        check("affinity_same_owner_original_mask_restored", !sched_setaffinity(target, sizeof(original), &original));
        _exit(failures ? 42 : 0);
    }
    int owner_ok = join(owner);
    if (write(go[1], "g", 1) != 1) exit(77);
    close(go[1]);
    int observed = -1;
    int got = read(report[0], &observed, sizeof(observed)) == sizeof(observed);
    close(report[0]);
    check("handoff_affinity_denied_target_stays_original_cpu", got && observed == initial);
    check("handoff_affinity_authorization_children_reaped", join(target) && attacker_ok && owner_ok);
    errno = 0;
    int gone = sched_setaffinity(target, sizeof(original), &original);
    check("affinity_reaped_target_esrch", gone == -1 && errno == ESRCH);
}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(40);
    cpu_set_t available;
    if (geteuid() || sched_getaffinity(0, sizeof(available), &available) || CPU_COUNT(&available) < 2) return 77;
    int target_cpu = -1;
    for (int cpu = 1; cpu < CPU_SETSIZE; cpu++) if (CPU_ISSET(cpu, &available)) { target_cpu = cpu; break; }
    if (target_cpu < 0) return 77;
    authorization(target_cpu);
    return failures ? 42 : 0;
}
