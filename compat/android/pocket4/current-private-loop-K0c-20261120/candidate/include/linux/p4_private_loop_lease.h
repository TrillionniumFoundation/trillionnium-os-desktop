/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_P4_PRIVATE_LOOP_LEASE_H
#define _LINUX_P4_PRIVATE_LOOP_LEASE_H

#include <linux/types.h>

struct backing_dev_info;
struct file;
struct gendisk;
struct p4_private_loop_actor;
struct p4_private_loop_lease;
struct p4_private_loop_authorization;

/*
 * K0c is reference custody and a CLOSED block boundary, not an issuer.
 * There is no ACTIVE state, userspace API, module export or permitted private
 * operation.  Only a new, exclusively owned, unpublished empty disk can be
 * marked.  Ordinary disks cannot be converted after registration or opening.
 * K1--K3 must supply the allocator, original request/source/graph admission,
 * actual I/O references and terminal reconciliation before any gate can open.
 */
#ifdef CONFIG_P4_PRIVATE_LOOP_LEASE
/* Caller owns both actor references.  The controller must be current. */
struct p4_private_loop_lease *
p4_private_loop_lease_create(struct p4_private_loop_actor *controller,
			     struct p4_private_loop_actor *actor);
struct p4_private_loop_lease *
p4_private_loop_lease_get(struct p4_private_loop_lease *lease);
/* Final put is sleepable and must be outside spinlocks/RCU callbacks. */
void p4_private_loop_lease_put(struct p4_private_loop_lease *lease);
/* Monotonic FENCED -> REVOKED only.  It neither drops custody nor drains I/O. */
void p4_private_loop_lease_revoke(struct p4_private_loop_lease *lease);
u64 p4_private_loop_lease_generation(const struct p4_private_loop_lease *lease);

/*
 * Caller exclusively owns the fresh disk: it is not shared with a registration
 * or I/O thread.  This is a kernel construction precondition, not a promise
 * inferred from a userspace PID/path.  The native open_mutex additionally
 * protects the checked block state.  The target stays attached until the
 * native final disk_release; its BDI gets a permanent closed marker.
 */
int p4_private_loop_target_attach(struct p4_private_loop_lease *lease,
				struct gendisk *disk);
void p4_private_loop_target_release(struct gendisk *disk);

/*
 * Bind exactly one real O_RDWR block open-file description.  The caller owns
 * the file and lease references and must be the original controller.  This
 * takes independent get_file/target references; it does NOT occupy
 * file->private_data, change the native holder, open a device or confer access.
 * K0c has no way to obtain such a private OFD because all opens stay closed.
 * Rebinding, including after the first association is dropped, is forbidden.
 */
struct p4_private_loop_authorization *
p4_private_loop_authorization_bind(struct p4_private_loop_lease *lease,
				  struct gendisk *disk, struct file *file);
struct p4_private_loop_authorization *
p4_private_loop_authorization_get(struct p4_private_loop_authorization *auth);
/* Final put removes association under its lock, then releases outside it. */
void p4_private_loop_authorization_put(struct p4_private_loop_authorization *auth);
/*
 * A bounded exact-actor/current and OFD custody observation ONLY.  Even a zero
 * result never admits a syscall, request, mount graph or I/O.  All gates below
 * still reject the private target.  Caller already owns the auth reference.
 */
int p4_private_loop_authorization_check_custody(
		const struct p4_private_loop_authorization *auth,
		struct file *file);

/* Native callers hold the disk/file/BDI lifetime.  No allocation or sleep. */
int p4_private_loop_disk_gate(const struct gendisk *disk);
int p4_private_loop_file_gate(struct file *file);
int p4_private_loop_bdi_gate(const struct backing_dev_info *bdi);
#else
static inline void p4_private_loop_target_release(struct gendisk *disk) { }
static inline int p4_private_loop_disk_gate(const struct gendisk *disk)
{
	return 0;
}
static inline int p4_private_loop_file_gate(struct file *file)
{
	return 0;
}
static inline int p4_private_loop_bdi_gate(const struct backing_dev_info *bdi)
{
	return 0;
}
#endif

#endif /* _LINUX_P4_PRIVATE_LOOP_LEASE_H */
