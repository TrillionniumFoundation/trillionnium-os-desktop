// SPDX-License-Identifier: GPL-2.0-only
/* K1a: actual native allocations behind the unchanged CLOSED K0c gates. */
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/list.h>
#include <linux/mutex.h>
#include <linux/p4_private_loop_actor.h>
#include <linux/p4_private_loop_lease.h>
#include <linux/p4_private_loop_realm.h>
#include <linux/refcount.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/slab.h>

#define P4_PRIVATE_LOOP_REALM_MAX_DEVICES 256U

struct p4_private_loop_realm {
	refcount_t refs;
	struct mutex lock;
	struct list_head allocations;
	struct p4_private_loop_actor *controller;
	struct p4_private_loop_actor *actor;
	struct task_struct *actor_task;
	unsigned int max_devices;
	unsigned int slots;
	bool revoked;
};

struct p4_private_loop_allocation {
	struct list_head realm_node;
	struct p4_private_loop_realm *realm;
	struct p4_private_loop_lease *lease;
	struct p4_private_loop_device *device;
	bool retiring;
};

static int p4_private_loop_realm_check_locked(struct p4_private_loop_realm *realm)
{
	int ret;

	lockdep_assert_held(&realm->lock);
	if (realm->revoked)
		return -EKEYREVOKED;
	ret = p4_private_loop_actor_check_task(realm->controller, current);
	if (ret)
		return ret;
	return p4_private_loop_actor_check_task(realm->actor, realm->actor_task);
}

static void p4_private_loop_realm_revoke_locked(struct p4_private_loop_realm *realm)
{
	struct p4_private_loop_allocation *allocation;

	lockdep_assert_held(&realm->lock);
	realm->revoked = true;
	list_for_each_entry(allocation, &realm->allocations, realm_node)
		p4_private_loop_lease_revoke(allocation->lease);
}

struct p4_private_loop_realm *
p4_private_loop_realm_create(struct p4_private_loop_actor *controller,
			     struct p4_private_loop_actor *actor,
			     struct task_struct *actor_task,
			     unsigned int max_devices)
{
	struct p4_private_loop_realm *realm;
	int ret;

	if (!controller || !actor || !actor_task || !max_devices ||
	    max_devices > P4_PRIVATE_LOOP_REALM_MAX_DEVICES)
		return ERR_PTR(-EINVAL);
	ret = p4_private_loop_actor_check_task(controller, current);
	if (!ret)
		ret = p4_private_loop_actor_check_task(actor, actor_task);
	if (ret)
		return ERR_PTR(ret);
	realm = kzalloc(sizeof(*realm), GFP_KERNEL);
	if (!realm)
		return ERR_PTR(-ENOMEM);
	refcount_set(&realm->refs, 1);
	mutex_init(&realm->lock);
	INIT_LIST_HEAD(&realm->allocations);
	realm->controller = p4_private_loop_actor_get(controller);
	realm->actor = p4_private_loop_actor_get(actor);
	realm->actor_task = get_task_struct(actor_task);
	realm->max_devices = max_devices;
	mutex_lock(&realm->lock);
	ret = p4_private_loop_realm_check_locked(realm);
	mutex_unlock(&realm->lock);
	if (ret) {
		p4_private_loop_realm_put(realm);
		return ERR_PTR(ret);
	}
	return realm;
}

struct p4_private_loop_realm *
p4_private_loop_realm_get(struct p4_private_loop_realm *realm)
{
	if (realm)
		refcount_inc(&realm->refs);
	return realm;
}

void p4_private_loop_realm_put(struct p4_private_loop_realm *realm)
{
	if (!realm || !refcount_dec_and_test(&realm->refs))
		return;
	might_sleep();
	/* Every reserved/owned allocation carries an independent realm ref. */
	if (WARN_ON_ONCE(realm->slots || !list_empty(&realm->allocations)))
		return;
	put_task_struct(realm->actor_task);
	p4_private_loop_actor_put(realm->actor);
	p4_private_loop_actor_put(realm->controller);
	mutex_destroy(&realm->lock);
	kfree(realm);
}

void p4_private_loop_realm_revoke(struct p4_private_loop_realm *realm)
{
	mutex_lock(&realm->lock);
	p4_private_loop_realm_revoke_locked(realm);
	mutex_unlock(&realm->lock);
}

int p4_private_loop_allocate_closed(struct p4_private_loop_realm *realm,
				    struct p4_private_loop_allocation **owned)
{
	struct p4_private_loop_allocation *allocation;
	int ret;

	if (!realm || !owned || *owned)
		return -EINVAL;
	allocation = kzalloc(sizeof(*allocation), GFP_KERNEL);
	if (!allocation)
		return -ENOMEM;
	INIT_LIST_HEAD(&allocation->realm_node);
	ret = mutex_lock_killable(&realm->lock);
	if (ret)
		goto free_allocation;
	ret = p4_private_loop_realm_check_locked(realm);
	if (ret) {
		p4_private_loop_realm_revoke_locked(realm);
		goto unlock;
	}
	if (realm->slots >= realm->max_devices) {
		ret = -ENOSPC;
		goto unlock;
	}
	realm->slots++;
	allocation->realm = p4_private_loop_realm_get(realm);
	mutex_unlock(&realm->lock);

	/* Reservation owns quota and the realm while native allocation may sleep.
	 * Revocation need not wait for allocation; the final bookend catches it.
	 */
	allocation->lease = p4_private_loop_lease_create(realm->controller,
						       realm->actor);
	if (IS_ERR(allocation->lease)) {
		ret = PTR_ERR(allocation->lease);
		allocation->lease = NULL;
		goto undo_reservation;
	}
	allocation->device =
		p4_private_loop_device_alloc_unpublished(allocation->lease);
	if (IS_ERR(allocation->device)) {
		ret = PTR_ERR(allocation->device);
		allocation->device = NULL;
		goto put_lease;
	}

	mutex_lock(&realm->lock);
	/* Publish only an internal cleanup handle, never a device or permission.
	 * Even a failed bookend returns this real handle so custody is not lost.
	 */
	list_add_tail(&allocation->realm_node, &realm->allocations);
	ret = p4_private_loop_realm_check_locked(realm);
	if (ret)
		p4_private_loop_realm_revoke_locked(realm);
	*owned = allocation;
	mutex_unlock(&realm->lock);
	return ret;

put_lease:
	p4_private_loop_lease_revoke(allocation->lease);
	p4_private_loop_lease_put(allocation->lease);
undo_reservation:
	mutex_lock(&realm->lock);
	realm->slots--;
	mutex_unlock(&realm->lock);
	p4_private_loop_realm_put(realm);
	goto free_allocation;
unlock:
	mutex_unlock(&realm->lock);
free_allocation:
	kfree(allocation);
	return ret;
}

int p4_private_loop_retire_closed(struct p4_private_loop_allocation **owned)
{
	struct p4_private_loop_allocation *allocation;
	struct p4_private_loop_realm *realm;
	int ret;

	if (!owned || !*owned)
		return -EINVAL;
	allocation = *owned;
	realm = allocation->realm;
	mutex_lock(&realm->lock);
	if (allocation->retiring) {
		mutex_unlock(&realm->lock);
		return -EBUSY;
	}
	allocation->retiring = true;
	p4_private_loop_lease_revoke(allocation->lease);
	mutex_unlock(&realm->lock);

	/* No current-task admission here: owners may have exited. The driver
	 * requires the actual unpublished/unbound/no-open/no-work state instead.
	 */
	ret = p4_private_loop_device_retire_unpublished(allocation->device);
	mutex_lock(&realm->lock);
	if (ret) {
		allocation->retiring = false;
		p4_private_loop_realm_revoke_locked(realm);
		mutex_unlock(&realm->lock);
		return ret;
	}
	list_del(&allocation->realm_node);
	realm->slots--;
	mutex_unlock(&realm->lock);
	*owned = NULL;
	p4_private_loop_lease_put(allocation->lease);
	kfree(allocation);
	p4_private_loop_realm_put(realm);
	return 0;
}

u64 p4_private_loop_allocation_generation(
		const struct p4_private_loop_allocation *allocation)
{
	return p4_private_loop_lease_generation(allocation->lease);
}
