// SPDX-License-Identifier: GPL-2.0-only
/*
 * K0c: retained controller/actor, non-reused generation and exact original OFD
 * association.  Private disks remain closed even to the matching actor.
 * Nothing here implements a device issuer, a loop probe/configure operation,
 * a mount graph lease, a source grant or asynchronous I/O retirement.
 */
#include <linux/atomic.h>
#include <linux/backing-dev.h>
#include <linux/blkdev.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/file.h>
#include <linux/fs.h>
#include <linux/limits.h>
#include <linux/p4_private_loop_actor.h>
#include <linux/p4_private_loop_lease.h>
#include <linux/pagemap.h>
#include <linux/refcount.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

enum p4_private_loop_state {
	P4_PRIVATE_LOOP_FENCED,
	P4_PRIVATE_LOOP_REVOKED,
};

struct p4_private_loop_lease {
	refcount_t refs;
	atomic_t state;
	atomic_t target_bound;
	u64 generation;
	struct p4_private_loop_actor *controller;
	struct p4_private_loop_actor *actor;
};

struct p4_private_loop_target {
	refcount_t refs;
	spinlock_t lock;
	struct p4_private_loop_lease *lease;
	struct p4_private_loop_authorization *authorization;
	bool bound_once;
};

struct p4_private_loop_authorization {
	refcount_t refs;
	struct p4_private_loop_target *target;
	struct file *file;
	u64 generation;
};

/* Saturate rather than wrap.  Zero is never a valid allocated generation. */
static atomic64_t p4_private_loop_next_generation = ATOMIC64_INIT(0);

static int p4_private_loop_new_generation(u64 *generation)
{
	s64 previous = atomic64_read(&p4_private_loop_next_generation);

	do {
		if (previous < 0 || previous == S64_MAX)
			return -EOVERFLOW;
	} while (!atomic64_try_cmpxchg(&p4_private_loop_next_generation,
				     &previous, previous + 1));
	*generation = previous + 1;
	return 0;
}

struct p4_private_loop_lease *
p4_private_loop_lease_create(struct p4_private_loop_actor *controller,
			     struct p4_private_loop_actor *actor)
{
	struct p4_private_loop_lease *lease;
	int ret;

	if (!controller || !actor)
		return ERR_PTR(-EINVAL);
	ret = p4_private_loop_actor_check_task(controller, current);
	if (ret)
		return ERR_PTR(ret);
	lease = kzalloc(sizeof(*lease), GFP_KERNEL);
	if (!lease)
		return ERR_PTR(-ENOMEM);
	ret = p4_private_loop_new_generation(&lease->generation);
	if (ret) {
		kfree(lease);
		return ERR_PTR(ret);
	}
	refcount_set(&lease->refs, 1);
	atomic_set(&lease->state, P4_PRIVATE_LOOP_FENCED);
	atomic_set(&lease->target_bound, 0);
	lease->controller = p4_private_loop_actor_get(controller);
	lease->actor = p4_private_loop_actor_get(actor);
	return lease;
}

struct p4_private_loop_lease *
p4_private_loop_lease_get(struct p4_private_loop_lease *lease)
{
	if (lease)
		refcount_inc(&lease->refs);
	return lease;
}

void p4_private_loop_lease_put(struct p4_private_loop_lease *lease)
{
	if (!lease || !refcount_dec_and_test(&lease->refs))
		return;
	might_sleep();
	p4_private_loop_actor_put(lease->actor);
	p4_private_loop_actor_put(lease->controller);
	kfree(lease);
}

void p4_private_loop_lease_revoke(struct p4_private_loop_lease *lease)
{
	atomic_cmpxchg(&lease->state, P4_PRIVATE_LOOP_FENCED,
		       P4_PRIVATE_LOOP_REVOKED);
}

u64 p4_private_loop_lease_generation(const struct p4_private_loop_lease *lease)
{
	return lease->generation;
}

static void p4_private_loop_target_put(struct p4_private_loop_target *target)
{
	if (!refcount_dec_and_test(&target->refs))
		return;
	might_sleep();
	WARN_ON_ONCE(target->authorization);
	p4_private_loop_lease_put(target->lease);
	kfree(target);
}

int p4_private_loop_target_attach(struct p4_private_loop_lease *lease,
				struct gendisk *disk)
{
	struct p4_private_loop_target *target;
	struct block_device *part;
	unsigned long index;
	int ret;

	if (!lease || !disk || !disk->part0 || !disk->bdi)
		return -EINVAL;
	ret = p4_private_loop_actor_check_task(lease->controller, current);
	if (ret)
		return ret;
	if (atomic_read(&lease->state) != P4_PRIVATE_LOOP_FENCED)
		return -EKEYREVOKED;
	target = kzalloc(sizeof(*target), GFP_KERNEL);
	if (!target)
		return -ENOMEM;
	refcount_set(&target->refs, 1);
	spin_lock_init(&target->lock);
	target->lease = p4_private_loop_lease_get(lease);

	/* Exclusive construction ownership is required in addition to this lock.
	 * In particular, this never races device_add/bdi_register on a shared disk.
	 */
	mutex_lock(&disk->open_mutex);
	ret = -EBUSY;
	if (READ_ONCE(disk->p4_private_loop_target) ||
	    test_bit(GD_ADDED, &disk->state) || disk_live(disk) ||
	    device_is_registered(disk_to_dev(disk)) ||
	    disk->queue_kobj.state_in_sysfs || disk_openers(disk) ||
	    disk->open_partitions || get_capacity(disk) ||
	    disk->part0->bd_dev || !mapping_empty(disk->part0->bd_mapping) ||
	    disk->bdi->dev || disk->bdi->owner || disk->bdi->id ||
	    test_bit(WB_registered, &disk->bdi->wb.state) ||
	    READ_ONCE(disk->bdi->p4_private_loop_closed))
		goto unlock;
	xa_for_each(&disk->part_tbl, index, part) {
		if (index || part != disk->part0)
			goto unlock;
	}
	if (atomic_read(&lease->state) != P4_PRIVATE_LOOP_FENCED) {
		ret = -EKEYREVOKED;
		goto unlock;
	}
	/* One generation names one target for its entire lifetime, even after
	 * that target is retired.  A later disk requires a newly created lease.
	 */
	if (atomic_cmpxchg(&lease->target_bound, 0, 1)) {
		ret = -EALREADY;
		goto unlock;
	}
	/* The BDI may outlive the disk through ordinary writeback references.
	 * Its one-way closed bit never dereferences the target and is not cleared.
	 */
	WRITE_ONCE(disk->bdi->p4_private_loop_closed, true);
	WRITE_ONCE(disk->p4_private_loop_target, target);
	ret = 0;
unlock:
	mutex_unlock(&disk->open_mutex);
	if (ret)
		p4_private_loop_target_put(target);
	return ret;
}

void p4_private_loop_target_release(struct gendisk *disk)
{
	struct p4_private_loop_target *target;

	/* Only native final disk_release calls this after its queue is drained.
	 * An associated file pins the native block lifetime, so this cannot clear
	 * a marker underneath a live authorization.  Never called from inode RCU.
	 */
	target = xchg(&disk->p4_private_loop_target, NULL);
	if (!target)
		return;
	p4_private_loop_lease_revoke(target->lease);
	p4_private_loop_target_put(target);
}

static bool p4_private_loop_original_file(struct gendisk *disk, struct file *file)
{
	return file && file->f_op == &def_blk_fops &&
		file->f_mapping == disk->part0->bd_mapping &&
		S_ISBLK(file->f_mapping->host->i_mode) &&
		file_bdev(file) == disk->part0 &&
		(file->f_flags & O_ACCMODE) == O_RDWR &&
		(file->f_mode & (FMODE_READ | FMODE_WRITE)) ==
				(FMODE_READ | FMODE_WRITE);
}

struct p4_private_loop_authorization *
p4_private_loop_authorization_bind(struct p4_private_loop_lease *lease,
				  struct gendisk *disk, struct file *file)
{
	struct p4_private_loop_authorization *auth;
	struct p4_private_loop_target *target;
	unsigned long flags;
	int ret;

	if (!lease || !disk || !disk->part0 ||
	    !p4_private_loop_original_file(disk, file))
		return ERR_PTR(-EINVAL);
	ret = p4_private_loop_actor_check_task(lease->controller, current);
	if (ret)
		return ERR_PTR(ret);
	/* Caller already holds the real file and disk lifetimes. */
	target = READ_ONCE(disk->p4_private_loop_target);
	if (!target || target->lease != lease)
		return ERR_PTR(-ESTALE);
	auth = kzalloc(sizeof(*auth), GFP_KERNEL);
	if (!auth)
		return ERR_PTR(-ENOMEM);
	refcount_set(&auth->refs, 1);
	auth->file = get_file(file);
	auth->target = target;
	refcount_inc(&target->refs);
	auth->generation = lease->generation;

	spin_lock_irqsave(&target->lock, flags);
	if (atomic_read(&lease->state) != P4_PRIVATE_LOOP_FENCED)
		ret = -EKEYREVOKED;
	else if (target->bound_once || target->authorization)
		ret = -EALREADY;
	else {
		target->bound_once = true;
		target->authorization = auth;
		ret = 0;
	}
	spin_unlock_irqrestore(&target->lock, flags);
	if (!ret)
		return auth;
	/* No target association was installed; both independent refs are ours. */
	fput(auth->file);
	p4_private_loop_target_put(target);
	kfree(auth);
	return ERR_PTR(ret);
}

struct p4_private_loop_authorization *
p4_private_loop_authorization_get(struct p4_private_loop_authorization *auth)
{
	if (auth)
		refcount_inc(&auth->refs);
	return auth;
}

void p4_private_loop_authorization_put(struct p4_private_loop_authorization *auth)
{
	struct p4_private_loop_target *target;
	unsigned long flags;

	if (!auth || !refcount_dec_and_test(&auth->refs))
		return;
	might_sleep();
	target = auth->target;
	spin_lock_irqsave(&target->lock, flags);
	if (WARN_ON_ONCE(target->authorization != auth)) {
		spin_unlock_irqrestore(&target->lock, flags);
		/* Corrupt/unknown association must not release retained custody. */
		return;
	}
	target->authorization = NULL;
	/* bound_once deliberately stays set: no second OFD/ABA admission. */
	spin_unlock_irqrestore(&target->lock, flags);
	fput(auth->file);
	p4_private_loop_target_put(target);
	kfree(auth);
}

int p4_private_loop_authorization_check_custody(
		const struct p4_private_loop_authorization *auth, struct file *file)
{
	struct p4_private_loop_target *target;
	struct p4_private_loop_lease *lease;
	struct gendisk *disk;
	unsigned long flags;
	int ret;

	if (!auth || file != auth->file)
		return -ESTALE;
	target = auth->target;
	lease = target->lease;
	if (atomic_read(&lease->state) != P4_PRIVATE_LOOP_FENCED)
		return -EKEYREVOKED;
	ret = p4_private_loop_actor_check_task(lease->actor, current);
	if (ret)
		return ret;
	disk = file_bdev(auth->file)->bd_disk;
	if (!p4_private_loop_original_file(disk, file) ||
	    READ_ONCE(disk->p4_private_loop_target) != target ||
	    auth->generation != lease->generation)
		return -ESTALE;
	spin_lock_irqsave(&target->lock, flags);
	ret = target->authorization == auth && target->bound_once ? 0 : -ESTALE;
	if (atomic_read(&lease->state) != P4_PRIVATE_LOOP_FENCED)
		ret = -EKEYREVOKED;
	spin_unlock_irqrestore(&target->lock, flags);
	return ret;
}

int p4_private_loop_disk_gate(const struct gendisk *disk)
{
	/* No state, actor, generation or valid OFD can turn this into an allow. */
	return READ_ONCE(disk->p4_private_loop_target) ? -EACCES : 0;
}

int p4_private_loop_file_gate(struct file *file)
{
	return p4_private_loop_disk_gate(file_bdev(file)->bd_disk);
}

int p4_private_loop_bdi_gate(const struct backing_dev_info *bdi)
{
	return READ_ONCE(bdi->p4_private_loop_closed) ? -EACCES : 0;
}
