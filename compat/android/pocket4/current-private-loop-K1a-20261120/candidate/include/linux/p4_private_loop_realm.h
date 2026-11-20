/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_P4_PRIVATE_LOOP_REALM_H
#define _LINUX_P4_PRIVATE_LOOP_REALM_H

#include <linux/types.h>

struct task_struct;
struct p4_private_loop_actor;
struct p4_private_loop_lease;
struct p4_private_loop_realm;
struct p4_private_loop_allocation;
struct p4_private_loop_device;

#ifdef CONFIG_P4_PRIVATE_LOOP_REALM
/*
 * K1a internal CLOSED construction only. There is no control FD, block FD,
 * node, lookup registry, global loop index, ioctl or userspace constructor.
 * No caller can obtain access authority from these objects. The existing
 * K0c disk/file/BIO/BDI gates remain closed and the runtime issuer stays empty.
 *
 * The original verified kernel binding must supply already-owned exact actor
 * references and the corresponding held task. No numeric PID lookup exists.
 * max_devices is a fixed kernel-owner resource policy, not an ioctl argument;
 * the source ceiling is 256 and no production value is selected here.
 */
struct p4_private_loop_realm *
p4_private_loop_realm_create(struct p4_private_loop_actor *controller,
			     struct p4_private_loop_actor *actor,
			     struct task_struct *actor_task,
			     unsigned int max_devices);
/* Caller must already own a reference. Final put is sleepable. */
struct p4_private_loop_realm *
p4_private_loop_realm_get(struct p4_private_loop_realm *realm);
void p4_private_loop_realm_put(struct p4_private_loop_realm *realm);
/* Stop further construction and revoke all retained leases; do not free them. */
void p4_private_loop_realm_revoke(struct p4_private_loop_realm *realm);

/*
 * Returns an exclusively owned cleanup handle through *owned. A negative
 * result CAN leave a non-NULL handle when an identity/revoke bookend failed
 * after real native allocation: the caller MUST still retire that handle.
 * Zero means only a closed object was constructed, never device access.
 * Do not share a handle concurrently with retirement. No get-disk/get-file
 * operation is provided. Each handle owns one quota slot and one realm ref.
 */
int __must_check p4_private_loop_allocate_closed(
		struct p4_private_loop_realm *realm,
		struct p4_private_loop_allocation **owned);
/*
 * Consumes *owned and sets it to NULL only after actual native closed-device
 * retirement. On failure, the handle, slot and all references stay owned;
 * the realm is revoked. The caller must not substitute success or discard it.
 * Cleanup is allowed after actor/controller exit; it is not actor admission.
 */
int __must_check p4_private_loop_retire_closed(
		struct p4_private_loop_allocation **owned);
/* Reporting only, while the caller still owns the exclusive handle. */
u64 p4_private_loop_allocation_generation(
		const struct p4_private_loop_allocation *allocation);

/*
 * Internal loop-driver side of this constructor. Only realm construction owns
 * these opaque pointers. No module symbols or userspace operations are added.
 */
struct p4_private_loop_device *
p4_private_loop_device_alloc_unpublished(struct p4_private_loop_lease *lease);
int __must_check p4_private_loop_device_retire_unpublished(
		struct p4_private_loop_device *device);
#endif

#endif /* _LINUX_P4_PRIVATE_LOOP_REALM_H */
