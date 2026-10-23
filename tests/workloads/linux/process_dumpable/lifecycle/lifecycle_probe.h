#ifndef DUMPABLE_LIFECYCLE_PROBE_H
#define DUMPABLE_LIFECYCLE_PROBE_H
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/fsuid.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

/* Bounded regression: only this program's own children, public sentinel,
 * controlled environment and /dev/null. No injection or unrelated PID. */
void check(const char *name, long actual, long expected);
void require(int okay, const char *name);
void exact(int fd, void *buffer, size_t length, int writing);
void no_caps(void);
void bound_caps(void);
void unprivileged(uid_t real, uid_t effective, uid_t saved,
                  gid_t greal, gid_t geffective, gid_t gsaved);
void reap(pid_t child, const char *name);
int actor(int input, int output, int after_exec);
void sensitive_paths(void);
void local_lifecycle(void);
void credential_case(unsigned number);
extern unsigned failures;
extern int reset_policy;
#endif
