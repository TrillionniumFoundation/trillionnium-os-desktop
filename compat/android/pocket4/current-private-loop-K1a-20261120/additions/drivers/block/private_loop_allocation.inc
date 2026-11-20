#ifdef CONFIG_P4_PRIVATE_LOOP_REALM
/* Internal allocation handle, deliberately absent from the global loop IDR. */
struct p4_private_loop_device {
	struct loop_device *lo;
};

struct p4_private_loop_device *
p4_private_loop_device_alloc_unpublished(struct p4_private_loop_lease *lease)
{
	struct queue_limits lim = { .max_hw_sectors = 2560u };
	struct p4_private_loop_device *device;
	struct loop_device *lo;
	struct gendisk *disk;
	int ret;

	if (!lease)
		return ERR_PTR(-EINVAL);
	device = kzalloc(sizeof(*device), GFP_KERNEL);
	if (!device)
		return ERR_PTR(-ENOMEM);
	lo = kzalloc(sizeof(*lo), GFP_KERNEL);
	if (!lo) {
		ret = -ENOMEM;
		goto free_device;
	}
	lo->worker_tree = RB_ROOT;
	INIT_LIST_HEAD(&lo->idle_worker_list);
	timer_setup(&lo->timer, loop_free_idle_workers_timer, TIMER_DEFERRABLE);
	lo->lo_state = Lo_unbound;
	/* No global loop index has been allocated or can name this object. */
	lo->lo_number = -1;
	mutex_init(&lo->lo_mutex);
	spin_lock_init(&lo->lo_lock);
	spin_lock_init(&lo->lo_work_lock);
	INIT_WORK(&lo->rootcg_work, loop_rootcg_workfn);
	INIT_LIST_HEAD(&lo->rootcg_cmd_list);
	lo->tag_set.ops = &loop_mq_ops;
	lo->tag_set.nr_hw_queues = 1;
	lo->tag_set.queue_depth = LOOP_DEFAULT_HW_Q_DEPTH;
	lo->tag_set.numa_node = NUMA_NO_NODE;
	lo->tag_set.cmd_size = sizeof(struct loop_cmd);
	lo->tag_set.flags = BLK_MQ_F_STACKING | BLK_MQ_F_NO_SCHED_BY_DEFAULT;
	lo->tag_set.driver_data = lo;
	ret = blk_mq_alloc_tag_set(&lo->tag_set);
	if (ret)
		goto free_loop;
	disk = blk_mq_alloc_disk(&lo->tag_set, &lim, lo);
	if (IS_ERR(disk)) {
		ret = PTR_ERR(disk);
		goto free_tags;
	}
	lo->lo_disk = disk;
	lo->lo_queue = disk->queue;
	disk->fops = &lo_fops;
	disk->private_data = lo;
	disk->flags = GENHD_FL_HIDDEN | GENHD_FL_NO_PART;
	set_bit(GD_SUPPRESS_PART_SCAN, &disk->state);
	snprintf(disk->disk_name, sizeof(disk->disk_name), "p4loop-%llu",
		 (unsigned long long)p4_private_loop_lease_generation(lease));
	/* No major/minor allocation, add_disk, bdev_add, BDI/queue registration,
	 * sysfs node, event, idr_visible update, control FD or block FD follows.
	 */
	ret = p4_private_loop_target_attach(lease, disk);
	if (ret)
		goto put_unpublished_disk;
	device->lo = lo;
	return device;

put_unpublished_disk:
	/* Native never-added disk release first drains/exits its queue. */
	put_disk(disk);
free_tags:
	blk_mq_free_tag_set(&lo->tag_set);
free_loop:
	loop_free_device(lo);
free_device:
	kfree(device);
	return ERR_PTR(ret);
}

int p4_private_loop_device_retire_unpublished(struct p4_private_loop_device *device)
{
	struct loop_device *lo;
	struct gendisk *disk;
	int ret = -EBUSY;

	if (!device)
		return -EINVAL;
	lo = device->lo;
	disk = lo->lo_disk;
	/* Match native block open -> loop open lock order. There can be no
	 * admitted private operation, so a changed state is a real refusal.
	 */
	mutex_lock(&disk->open_mutex);
	mutex_lock(&lo->lo_mutex);
	if (!p4_private_loop_disk_gate(disk) || disk_live(disk) ||
	    test_bit(GD_ADDED, &disk->state) ||
	    device_is_registered(disk_to_dev(disk)) ||
	    disk->queue_kobj.state_in_sysfs ||
	    test_bit(QUEUE_FLAG_REGISTERED, &disk->queue->queue_flags) ||
	    disk_openers(disk) || disk->open_partitions || get_capacity(disk) ||
	    disk->major || disk->first_minor || disk->minors ||
	    disk->part0->bd_dev || !mapping_empty(disk->part0->bd_mapping) ||
	    disk->bdi->dev || disk->bdi->owner ||
	    test_bit(WB_registered, &disk->bdi->wb.state) ||
	    !p4_private_loop_bdi_gate(disk->bdi) ||
	    lo->idr_visible || lo->lo_number != -1 || lo->lo_state != Lo_unbound ||
	    lo->lo_backing_file || lo->lo_device || lo->workqueue ||
	    lo->lo_flags || lo->lo_offset || lo->lo_sizelimit || lo->sysfs_inited ||
	    !RB_EMPTY_ROOT(&lo->worker_tree) ||
	    !list_empty(&lo->idle_worker_list) ||
	    !list_empty(&lo->rootcg_cmd_list) ||
	    work_pending(&lo->rootcg_work) || timer_pending(&lo->timer))
		goto unlock;
	lo->lo_state = Lo_deleting;
	ret = 0;
unlock:
	mutex_unlock(&lo->lo_mutex);
	mutex_unlock(&disk->open_mutex);
	if (ret)
		return ret;
	/* The never-published disk has no external device reference or holder.
	 * Its native release does not call free_disk when GD_ADDED was never set.
	 * Keep the exact original allocation-failure order: queue/disk, tags, lo.
	 * Do not dereference disk after put_disk; its inode release may be deferred.
	 */
	put_disk(disk);
	blk_mq_free_tag_set(&lo->tag_set);
	loop_free_device(lo);
	kfree(device);
	return 0;
}
#endif /* CONFIG_P4_PRIVATE_LOOP_REALM */

