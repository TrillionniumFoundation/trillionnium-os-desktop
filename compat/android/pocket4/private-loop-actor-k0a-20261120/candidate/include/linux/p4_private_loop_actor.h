/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_P4_PRIVATE_LOOP_ACTOR_H
#define _LINUX_P4_PRIVATE_LOOP_ACTOR_H

struct task_struct;
struct p4_private_loop_actor;

/*
 * Internal, retained task-context identity only.  This is NOT a private-loop
 * lease, an access decision, a mount-graph snapshot, or a device issuer.
 * There is no userspace constructor and no exported module symbol.
 *
 * A future issuer must separately bind a fresh original request, controller,
 * exact actor/thread, default mount graph, device generation, operation and
 * deadline, and cover every block entry and graph/IO lifetime.  In particular,
 * a successful check below must never make an ordinary host loop private.
 */

/*
 * Caller already owns a live task reference obtained by its separately
 * reviewed kernel binding.  Numeric PID lookup is deliberately not supplied.
 * Capture may sleep, takes its own references, and returns ERR_PTR on failure.
 * Its counted fs reference affects shared-fs/exec/unshare decisions. This is
 * deliberate lifetime custody, not an observationally transparent monitor.
 * It accepts an exact nonleader userspace thread; it never promotes a TID to
 * the thread-group leader.  The caller retains its original task reference.
 */
struct p4_private_loop_actor *
p4_private_loop_actor_capture(struct task_struct *task);

/* Caller must already own a reference.  No reference can be resurrected. */
struct p4_private_loop_actor *
p4_private_loop_actor_get(struct p4_private_loop_actor *actor);

/* Final put may release paths and task state; do not call under a spinlock. */
void p4_private_loop_actor_put(struct p4_private_loop_actor *actor);

/*
 * Check a caller-held task against the retained exact task context.  This is
 * one bounded observation, not authority that survives a subsequent mutation.
 * A syscall entry must pass current, never a task supplied by userspace.
 * Returns 0, -ESRCH for exit, or -ESTALE for any identity/context difference.
 * No task, credential, namespace, filesystem or device is changed.
 */
int p4_private_loop_actor_check_task(const struct p4_private_loop_actor *actor,
				   struct task_struct *task);

#endif /* _LINUX_P4_PRIVATE_LOOP_ACTOR_H */
