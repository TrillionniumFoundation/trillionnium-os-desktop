#!/usr/bin/env python3
"""Reproduce K0c exact postimages from pinned 6.18.64 + K0b bodies."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'apex-private-loop-design/base/linux-6.18.64'
K0A = ROOT.parent / 'p4_private_loop_k0a/candidate'
K0B = ROOT.parent / 'p4_private_loop_k0b/candidate'
BASE = ROOT / 'base'
OUT = ROOT / 'candidate'
CHANGES = []


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def original(path, origin, sha):
    raw = (origin / path).read_bytes()
    assert pin(raw)['sha256'] == sha, (path, 'exact whole base')
    if origin != BASE:
        write(BASE / path, raw)
    return raw.decode()


def once(body, before, after):
    assert body.count(before) == 1, ('unique replacement', before, body.count(before))
    return body.replace(before, after)


def function_span(body, name):
    pattern = r'^((?:static |inline |__\w+ |const |unsigned |long |struct |void |int |ssize_t |loff_t |bool |blk_status_t |\w+\s*\*\s*)[^;{}]*?\b' + re.escape(name) + r'\([^;{}]*?\)\s*\n\{)'
    hits = list(re.finditer(pattern, body, re.M))
    assert len(hits) == 1, (name, 'one actual C definition', len(hits))
    start = hits[0].start(); pos = hits[0].end(); depth = 1; state = 'code'
    while depth:
        ch = body[pos]; pair = body[pos:pos+2]
        if state == 'line':
            if ch == '\n': state = 'code'
        elif state == 'comment':
            if pair == '*/': state = 'code'; pos += 1
        elif state in ('"', "'"):
            if ch == '\\': pos += 1
            elif ch == state: state = 'code'
        elif pair == '/*': state = 'comment'; pos += 1
        elif pair == '//': state = 'line'; pos += 1
        elif ch in ('"', "'"): state = ch
        elif ch == '{': depth += 1
        elif ch == '}': depth -= 1
        pos += 1
    return start, pos


def within(body, function, before, after):
    start, end = function_span(body, function)
    return body[:start] + once(body[start:end], before, after) + body[end:]


def include(body):
    at = body.index('#include ')
    return body[:at] + '#include <linux/p4_private_loop_lease.h>\n' + body[at:]


def output(path, before, after):
    assert before != after, (path, 'nonempty source change')
    write(OUT / path, after.encode())
    CHANGES.append({'path': path, 'before': pin(before.encode()), 'after': pin(after.encode())})


def main():
    before = original('include/linux/blkdev.h', OLD, '6547ab1965c06f48a13cebd60fc7e7829fee5a66590d047d57cba9b2082e3c8f')
    after = once(before, 'struct blk_crypto_profile;\n', 'struct blk_crypto_profile;\nstruct p4_private_loop_target;\n')
    after = once(after, '\tvoid *private_data;\n', '\tvoid *private_data;\n#ifdef CONFIG_P4_PRIVATE_LOOP_LEASE\n\t/* Immutable association until native final disk_release. */\n\tstruct p4_private_loop_target *p4_private_loop_target;\n#endif\n')
    output('include/linux/blkdev.h', before, after)

    before = original('include/linux/backing-dev-defs.h', BASE, 'dd69a35b4def6f5e34a6a950790cc8920b79209bb7af6a39fabd3d7473d24e03')
    after = once(before, 'struct backing_dev_info {\n', 'struct backing_dev_info {\n#ifdef CONFIG_P4_PRIVATE_LOOP_LEASE\n\t/* One-way closed marker; no borrowed target pointer or access grant. */\n\tbool p4_private_loop_closed;\n#endif\n')
    output('include/linux/backing-dev-defs.h', before, after)

    before = original('block/Kconfig', K0A, '53db5a3e3e17cd78ae8800ace8f8f7e24a5392e2d18106dc3ad1ea3fedd1915f')
    addition = '''config P4_PRIVATE_LOOP_LEASE
	bool "Closed private-loop lease reference foundation"
	depends on P4_PRIVATE_LOOP_ACTOR && BLK_DEV_LOOP=y
	default n
	help
	  Retain exact controller, actor, generation and original block-file
	  references for a fresh unpublished private target. Every private
	  operation and publication remains denied. No active state, userspace
	  API, module symbol, allocator or runtime issuer is supplied.

	  This changes internal disk/BDI layout and requires a coherent kernel
	  build. Say N outside the separately reviewed development work.

'''
    after = once(before, 'source "block/Kconfig.iosched"\n', addition + 'source "block/Kconfig.iosched"\n')
    output('block/Kconfig', before, after)
    before = original('block/Makefile', K0A, '6ba584cce900e0209fb4a2c53f3dbd5ff972ab852165833500666140041a19e9')
    output('block/Makefile', before, before + 'obj-$(CONFIG_P4_PRIVATE_LOOP_LEASE) += p4_private_loop_lease.o\n')

    before = original('block/bdev.c', OLD, 'b6eee2eab56791b70f0e290ef5e552c764e9a41bd98a47c25272e6b6fc6deac6')
    after = include(before)
    after = within(after, 'set_blocksize', '\tret = bdev_validate_blocksize(bdev, size);', '\tret = p4_private_loop_file_gate(file);\n\tif (ret)\n\t\treturn ret;\n\n\tret = bdev_validate_blocksize(bdev, size);')
    after = within(after, 'bdev_open', '\tint ret;\n', '\tint ret;\n\n\tret = p4_private_loop_disk_gate(disk);\n\tif (ret)\n\t\treturn ret;\n')
    after = within(after, 'bdev_set_nr_sectors', '\tspin_lock(&bdev->bd_size_lock);', '\t/* Zero remains available to original invalidation/teardown. */\n\tif (sectors && p4_private_loop_disk_gate(bdev->bd_disk))\n\t\treturn;\n\tspin_lock(&bdev->bd_size_lock);')
    after = within(after, 'bdev_add', '\tstruct inode *inode = BD_INODE(bdev);\n', '\tstruct inode *inode = BD_INODE(bdev);\n\n\t/* Also close direct inode publication, independently of add_disk. */\n\tif (p4_private_loop_disk_gate(bdev->bd_disk))\n\t\treturn;\n')
    output('block/bdev.c', before, after)

    before = original('block/fops.c', OLD, 'c65a43f6cec9e0bf877aeb1b7406696fd32b058742cb0037327815e224fcc5bc')
    after = include(before)
    after = within(after, 'blkdev_llseek', '\tinode_lock(bd_inode);', '\tretval = p4_private_loop_file_gate(file);\n\tif (retval)\n\t\treturn retval;\n\n\tinode_lock(bd_inode);')
    after = within(after, 'blkdev_fsync', '\terror = file_write_and_wait_range(filp, start, end);', '\terror = p4_private_loop_file_gate(filp);\n\tif (error)\n\t\treturn error;\n\n\terror = file_write_and_wait_range(filp, start, end);')
    after = within(after, 'blkdev_write_iter', '\tif (bdev_read_only(bdev))', '\tret = p4_private_loop_file_gate(file);\n\tif (ret)\n\t\treturn ret;\n\n\tif (bdev_read_only(bdev))')
    after = within(after, 'blkdev_read_iter', '\tif (unlikely(pos + iov_iter_count(to) > size)) {', '\tret = p4_private_loop_file_gate(iocb->ki_filp);\n\tif (ret)\n\t\treturn ret;\n\n\tif (unlikely(pos + iov_iter_count(to) > size)) {')
    after = within(after, 'blkdev_fallocate', '\t/* Fail if we don\'t recognize the flags. */', '\terror = p4_private_loop_file_gate(file);\n\tif (error)\n\t\treturn error;\n\n\t/* Fail if we don\'t recognize the flags. */')
    after = within(after, 'blkdev_mmap_prepare', '\tstruct file *file = desc->file;\n', '\tstruct file *file = desc->file;\n\tint ret = p4_private_loop_file_gate(file);\n\n\tif (ret)\n\t\treturn ret;\n')
    wrappers = '''/* Generic splice helpers can read cached pages without a fresh BIO. */
static ssize_t blkdev_splice_read(struct file *in, loff_t *ppos,
		struct pipe_inode_info *pipe, size_t len, unsigned int flags)
{
	int ret = p4_private_loop_file_gate(in);

	if (ret)
		return ret;
	return filemap_splice_read(in, ppos, pipe, len, flags);
}

static ssize_t blkdev_splice_write(struct pipe_inode_info *pipe,
		struct file *out, loff_t *ppos, size_t len, unsigned int flags)
{
	int ret = p4_private_loop_file_gate(out);

	if (ret)
		return ret;
	return iter_file_splice_write(pipe, out, ppos, len, flags);
}

'''
    after = once(after, 'const struct file_operations def_blk_fops = {', wrappers + 'const struct file_operations def_blk_fops = {')
    after = once(after, '\t.splice_read\t= filemap_splice_read,', '\t.splice_read\t= blkdev_splice_read,')
    after = once(after, '\t.splice_write\t= iter_file_splice_write,', '\t.splice_write\t= blkdev_splice_write,')
    output('block/fops.c', before, after)

    before = original('block/ioctl.c', OLD, '26fbdea91fdd33702d035588184cd811981387910403efc72035599ac4d60207')
    after = include(before)
    for name in ('blkdev_ioctl', 'compat_blkdev_ioctl'):
        after = within(after, name, '\tswitch (cmd) {', '\tret = p4_private_loop_file_gate(file);\n\tif (ret)\n\t\treturn ret;\n\n\tswitch (cmd) {')
    after = within(after, 'blkdev_compat_ptr_ioctl', '\tstruct gendisk *disk = bdev->bd_disk;\n', '\tstruct gendisk *disk = bdev->bd_disk;\n\tint ret = p4_private_loop_disk_gate(disk);\n\n\tif (ret)\n\t\treturn ret;\n')
    after = within(after, 'blkdev_uring_cmd', '\tu32 cmd_op = cmd->cmd_op;\n', '\tu32 cmd_op = cmd->cmd_op;\n\tint ret = p4_private_loop_file_gate(cmd->file);\n\n\tif (ret)\n\t\treturn ret;\n')
    output('block/ioctl.c', before, after)

    before = original('block/genhd.c', BASE, 'a26b11e1d93479c46cb05f2844e52f2c645338bdf121e8b2e1f29c7cfd52178b')
    after = include(before)
    after = within(after, '__add_disk', '\tif (WARN_ON_ONCE(bdev_nr_sectors(disk->part0) > BLK_DEV_MAX_SECTORS))', '\t/* K0c never publishes a private disk into the global device graph. */\n\tret = p4_private_loop_disk_gate(disk);\n\tif (ret)\n\t\treturn ret;\n\n\tif (WARN_ON_ONCE(bdev_nr_sectors(disk->part0) > BLK_DEV_MAX_SECTORS))')
    after = within(after, 'disk_scan_partitions', '\tif (!disk_has_partscan(disk))', '\tret = p4_private_loop_disk_gate(disk);\n\tif (ret)\n\t\treturn ret;\n\n\tif (!disk_has_partscan(disk))')
    after = within(after, 'set_capacity_and_notify', '\tset_capacity(disk, size);', '\tif (p4_private_loop_disk_gate(disk))\n\t\treturn false;\n\n\tset_capacity(disk, size);')
    after = within(after, 'disk_release', '\tbdev_drop(disk->part0);\t/* frees the disk */', '\tp4_private_loop_target_release(disk);\n\tbdev_drop(disk->part0);\t/* frees the disk */')
    after = within(after, 'disk_badblocks_store', '\tif (!disk->bb)', '\tif (p4_private_loop_disk_gate(disk))\n\t\treturn -EACCES;\n\n\tif (!disk->bb)')
    after = within(after, 'part_fail_store', '\tif (count > 0', '\tif (p4_private_loop_disk_gate(dev_to_bdev(dev)->bd_disk))\n\t\treturn -EACCES;\n\n\tif (count > 0')
    output('block/genhd.c', before, after)

    before = original('block/blk-sysfs.c', OLD, 'ac564ed7e11899e76643678d0bc1b81534a4400c4056874d49cfd8918a639afb')
    after = include(before)
    after = within(after, 'queue_attr_show', '\tif (!entry->show && !entry->show_limit)', '\tif (p4_private_loop_disk_gate(disk))\n\t\treturn -EACCES;\n\n\tif (!entry->show && !entry->show_limit)')
    after = within(after, 'queue_attr_store', '\tif (!entry->store_limit && !entry->store)', '\tif (p4_private_loop_disk_gate(disk))\n\t\treturn -EACCES;\n\n\tif (!entry->store_limit && !entry->store)')
    after = within(after, 'blk_register_queue', '\tret = kobject_add(', '\tret = p4_private_loop_disk_gate(disk);\n\tif (ret)\n\t\treturn ret;\n\n\tret = kobject_add(')
    output('block/blk-sysfs.c', before, after)

    before = original('mm/backing-dev.c', BASE, '2f5c23c55a0138dd58098b53aa776a9c948547c2ccaaf3e1dd345d1f7387c72d')
    after = include(before)
    after = within(after, 'bdi_register_va', '\tif (bdi->dev)', '\tif (p4_private_loop_bdi_gate(bdi))\n\t\treturn -EACCES;\n\n\tif (bdi->dev)')
    for name in ('read_ahead_kb', 'min_ratio', 'min_ratio_fine', 'max_ratio', 'max_ratio_fine', 'min_bytes', 'max_bytes', 'strict_limit'):
        start, end = function_span(after, name+'_store')
        fun = after[start:end]
        anchor = re.search(r'\tret = kstr\w+\(', fun).group()
        after = within(after, name+'_store', anchor, '\tret = p4_private_loop_bdi_gate(bdi);\n\tif (ret)\n\t\treturn ret;\n\n'+anchor)
    output('mm/backing-dev.c', before, after)

    before = original('block/partitions/core.c', BASE, 'ad767ffaeaaa5657fee61150083657911162a756215f97b2e0a17cd4b11d49e3')
    after = include(before)
    after = within(after, 'add_partition', '\tlockdep_assert_held(&disk->open_mutex);', '\tlockdep_assert_held(&disk->open_mutex);\n\tif (p4_private_loop_disk_gate(disk))\n\t\treturn ERR_PTR(-EACCES);')
    for name in ('bdev_add_partition', 'bdev_del_partition', 'bdev_resize_partition'):
        after = within(after, name, '\tmutex_lock(&disk->open_mutex);', '\tif (p4_private_loop_disk_gate(disk))\n\t\treturn -EACCES;\n\n\tmutex_lock(&disk->open_mutex);')
    after = within(after, 'bdev_disk_changed', '\tlockdep_assert_held(&disk->open_mutex);', '\tlockdep_assert_held(&disk->open_mutex);\n\tif (p4_private_loop_disk_gate(disk))\n\t\treturn -EACCES;')
    after = within(after, 'read_part_sector', '\tif (n >= get_capacity(state->disk)) {', '\tif (p4_private_loop_disk_gate(state->disk))\n\t\tgoto out;\n\n\tif (n >= get_capacity(state->disk)) {')
    output('block/partitions/core.c', before, after)

    before = original('block/blk-core.c', BASE, '224d059cfd5b51a7cb7ab0998c772183233016ec184e2cd568ffbbd5e38e3101')
    after = include(before)
    deny = '\tif (p4_private_loop_disk_gate(bio->bi_bdev->bd_disk)) {\n\t\tbio_endio_status(bio, BLK_STS_IOERR);\n\t\treturn;\n\t}\n\n'
    after = within(after, '__submit_bio', '\tif (unlikely(!blk_crypto_bio_prep(bio)))', deny + '\tif (unlikely(!blk_crypto_bio_prep(bio)))')
    start, end = function_span(after, 'submit_bio_noacct_nocheck')
    fun = after[start:end]
    # This actual entry has no local declaration; deny before accounting/list admission.
    opening = fun.index('{\n') + 2
    after = after[:start] + fun[:opening] + deny + fun[opening:] + after[end:]
    after = within(after, 'submit_bio_noacct', '\tif (should_fail_bio(bio))', deny + '\tif (should_fail_bio(bio))')
    output('block/blk-core.c', before, after)

    before = original('drivers/block/loop.c', OLD, '327185cdd1ccb63f39648c397a814b2e1fc5de079c42649b2fb5ec2cfafebbbe')
    after = include(before)
    for name in ('lo_ioctl', 'lo_compat_ioctl'):
        anchor = '\tswitch (cmd) {' if name == 'lo_ioctl' else '\tswitch(cmd) {'
        after = within(after, name, anchor, '\terr = p4_private_loop_disk_gate(bdev->bd_disk);\n\tif (err)\n\t\treturn err;\n\n' + anchor)
    after = within(after, 'lo_open', '\terr = mutex_lock_killable(&lo->lo_mutex);', '\terr = p4_private_loop_disk_gate(disk);\n\tif (err)\n\t\treturn err;\n\n\terr = mutex_lock_killable(&lo->lo_mutex);')
    after = within(after, 'loop_attr_show', '\treturn callback(lo, page);', '\tif (p4_private_loop_disk_gate(disk))\n\t\treturn -EACCES;\n\n\treturn callback(lo, page);')
    after = within(after, 'loop_queue_rq', '\tblk_mq_start_request(rq);', '\t/* Workers do not inherit the issuing task: this closed gate never\n\t * substitutes current for a future retained I/O authorization.\n\t */\n\tif (p4_private_loop_disk_gate(lo->lo_disk))\n\t\treturn BLK_STS_IOERR;\n\n\tblk_mq_start_request(rq);')
    after = within(after, 'loop_control_remove', '\tif (!lo || !lo->idr_visible)\n\t\tret = -ENODEV;\n\telse', '\tif (!lo || !lo->idr_visible)\n\t\tret = -ENODEV;\n\telse if (p4_private_loop_disk_gate(lo->lo_disk))\n\t\tret = -EACCES;\n\telse')
    after = within(after, 'loop_control_get_free', '\t\tif (lo->idr_visible && data_race(lo->lo_state) == Lo_unbound)', '\t\tif (lo->idr_visible && !p4_private_loop_disk_gate(lo->lo_disk) &&\n\t\t    data_race(lo->lo_state) == Lo_unbound)')
    output('drivers/block/loop.c', before, after)

    for path in ('include/linux/p4_private_loop_lease.h', 'block/p4_private_loop_lease.c'):
        raw = (ROOT/'additions'/path).read_bytes()
        write(OUT/path, raw)
        CHANGES.append({'path': path, 'before': None, 'after': pin(raw)})
    inherited = []
    for path in ('include/linux/fs_struct.h', 'fs/fs_struct.c', 'include/linux/p4_private_loop_actor.h', 'block/p4_private_loop_actor.c'):
        raw = (K0B/path).read_bytes()
        write(OUT/path, raw)
        inherited.append({'path': path, **pin(raw)})
    patch = ''
    for row in CHANGES:
        path = row['path']; before = (BASE/path).read_text() if row['before'] else ''
        after = (OUT/path).read_text()
        patch += ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile='a/'+path if row['before'] else '/dev/null', tofile='b/'+path))
    write(ROOT/'K0c.patch', patch.encode())
    manifest = {'schema':'p4-private-loop-closed-lease-K0c-source-v1',
        'base_K0b_commit':'69e7c31c9e7e34fa39d3422df1c22d4c5f33d9ce', 'kernel_version':'6.18.64',
        'files': CHANGES, 'unchanged_K0b_inherited_files':inherited, 'patch':pin(patch.encode()),
        'state':'SOURCE_CANDIDATE_CLOSED_NO_ISSUER', 'source_review_passed':False,
        'matching_objects_compiled':False, 'kernel_linked':False, 'kernel_executed':False,
        'private_device_published':False, 'original_apexd_probe_qualified':False,
        'issuer_enabled':False, 'Android_started':False, 'runtime_qualified':False, 'production_ready':False}
    write(ROOT/'MANIFEST.json', (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'changed_or_added':len(CHANGES), 'inherited_unchanged':len(inherited), 'patch':manifest['patch']}))


if __name__ == '__main__':
    main()
