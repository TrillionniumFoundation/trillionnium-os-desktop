// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_INSTANCE_QUERY_H
#define DROIDLOOM_INSTANCE_QUERY_H
#include <stdint.h>
#include <linux/filter.h>
struct droidloom_factory_query {
    /* stdin/stdout/stderr, gate, init/owner/factory pidfds, root,
       user/mnt/ipc/uts/net/cgroup namespaces, fixed executable. */
    int files[15];
    int pid_namespace;
    int cgroup;
    uint64_t deadline_ns;
    const char *const *argv;
    const char *const *envp;
    const struct sock_fprog *filter;
};
/* On every return, a nonnegative pidfd denotes an actually created child that
   the caller must retain and reap, including an unsuccessful namespace restore. */
int droidloom_factory_spawn_query(const struct droidloom_factory_query *,int *,int *);
#endif
