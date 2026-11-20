#!/usr/bin/env python3
"""Create K1a actual unpublished native allocator postimages on exact K0c."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT=Path(__file__).resolve().parent
K0C=ROOT.parent/'p4_private_loop_k0c'


def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def write(path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
def once(body,before,after):
    assert body.count(before)==1,(before,body.count(before))
    return body.replace(before,after)


def main():
    m=json.loads((K0C/'MANIFEST.json').read_bytes())
    all_rows=m['files']+m['unchanged_K0b_inherited_files']
    expected={r['path']:r.get('after',r) for r in all_rows}
    for path,row in expected.items():
        raw=(K0C/'candidate'/path).read_bytes();assert pin(raw)=={'bytes':row['bytes'],'sha256':row['sha256']}
        write(ROOT/'candidate'/path,raw)
    changes=[]
    def change(path,body):
        before=(K0C/'candidate'/path).read_bytes();assert body.encode()!=before
        write(ROOT/'base'/path,before);write(ROOT/'candidate'/path,body.encode())
        changes.append({'path':path,'before':pin(before),'after':pin(body.encode())})
    before=(K0C/'candidate/drivers/block/loop.c').read_text()
    body=once(before,'#include <linux/p4_private_loop_lease.h>\n',
        '#include <linux/p4_private_loop_lease.h>\n#include <linux/p4_private_loop_realm.h>\n#include <linux/backing-dev.h>\n')
    old='''static void lo_free_disk(struct gendisk *disk)
{
	struct loop_device *lo = disk->private_data;

'''
    body=once(body,old,'''static void loop_free_device(struct loop_device *lo)
{
''')
    body=once(body,'static const struct block_device_operations lo_fops = {',
        '''static void lo_free_disk(struct gendisk *disk)
{
	loop_free_device(disk->private_data);
}

static const struct block_device_operations lo_fops = {''')
    addition=(ROOT/'additions/drivers/block/private_loop_allocation.inc').read_text()
    body=once(body,'static int loop_add(int i)\n{',addition+'static int loop_add(int i)\n{')
    change('drivers/block/loop.c',body)
    before=(K0C/'candidate/block/Kconfig').read_text()
    addition='''config P4_PRIVATE_LOOP_REALM
	bool "Unpublished closed private-loop native allocations"
	depends on P4_PRIVATE_LOOP_LEASE
	default n
	help
	  Build a retained internal realm and a bounded native loop/blk-mq
	  allocator. Its objects have no device number, global loop index,
	  node, control FD, block FD, userspace ABI or permitted operation.
	  All K0c entry gates stay closed; this does not enable an issuer.

	  Say N outside development of the separately reviewed private realm.

'''
    change('block/Kconfig',once(before,'source "block/Kconfig.iosched"\n',addition+'source "block/Kconfig.iosched"\n'))
    before=(K0C/'candidate/block/Makefile').read_text()
    change('block/Makefile',before+'obj-$(CONFIG_P4_PRIVATE_LOOP_REALM) += p4_private_loop_realm.o\n')
    for path in ('block/p4_private_loop_realm.c','include/linux/p4_private_loop_realm.h'):
        raw=(ROOT/'additions'/path).read_bytes();write(ROOT/'candidate'/path,raw)
        changes.append({'path':path,'before':None,'after':pin(raw)})
    patch=''
    for row in changes:
        path=row['path'];before=(ROOT/'base'/path).read_text() if row['before'] else ''
        after=(ROOT/'candidate'/path).read_text()
        patch+=''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),
            fromfile='a/'+path if row['before'] else '/dev/null',tofile='b/'+path))
    write(ROOT/'K1a.patch',patch.encode())
    inherited=[{'path':path,**pin((ROOT/'candidate'/path).read_bytes())} for path in expected if path not in {r['path'] for r in changes}]
    manifest={'schema':'p4-private-loop-K1a-unpublished-allocator-source-v1',
        'parent_K0c_commit':'f83f52dde3594d7eef4a1e44785f940c824467d5',
        'base_K0c_patch':m['patch'],'files':changes,'unchanged_inherited_files':inherited,
        'patch':pin(patch.encode()),'state':'SOURCE_CANDIDATE_UNPUBLISHED_NATIVE_ALLOCATIONS',
        'kernel_object_compile_passed':False,'independent_review_passed':False,
        'K1_complete':False,'real_control_or_block_OFD_created':False,'private_device_published':False,
        'original_control_index_ABI_selected':False,'issuer_enabled':False,'kernel_executed':False,
        'VM_started':False,'Android_started':False,'runtime_qualified':False,'production_ready':False}
    write(ROOT/'MANIFEST.json',(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({'new_or_changed':len(changes),'unchanged_inherited':len(inherited),'patch':manifest['patch']}))


if __name__=='__main__':main()
