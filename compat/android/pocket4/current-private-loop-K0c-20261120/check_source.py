#!/usr/bin/env python3
"""Finite patch/source preservation checks, not kernel/runtime tests."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile
import prepare

ROOT=Path(__file__).resolve().parent
M=json.loads((ROOT/'MANIFEST.json').read_bytes())
commands=[]


def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def run(argv,cwd):
    q=subprocess.run(argv,cwd=cwd,capture_output=True,check=False)
    commands.append({'argv':argv,'exit_code':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()})
    assert q.returncode==0,(argv,q.stderr.decode())


def function(path,name,which):
    raw=(ROOT/which/path).read_text();a,b=prepare.function_span(raw,name)
    return raw[a:b].encode()


def main():
    rows=[]
    for row in M['files']:
        raw=(ROOT/'candidate'/row['path']).read_bytes();assert pin(raw)==row['after']
        if row['before']:assert pin((ROOT/'base'/row['path']).read_bytes())==row['before']
        rows.append({'path':row['path'],'whole_before_and_after_pins_match':True})
    for row in M['unchanged_K0b_inherited_files']:
        raw=(ROOT/'candidate'/row['path']).read_bytes()
        old=(ROOT.parent/'p4_private_loop_k0b/candidate'/row['path']).read_bytes()
        assert raw==old and pin(raw)=={'bytes':row['bytes'],'sha256':row['sha256']}
    patch=(ROOT/'K0c.patch').read_bytes();assert pin(patch)==M['patch']
    with tempfile.TemporaryDirectory(prefix='p4-k0c-source-') as name:
        temp=Path(name)
        for row in M['files']:
            if row['before']:
                p=temp/row['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/'base'/row['path']).read_bytes())
        run(['/usr/bin/git','apply','--check',str(ROOT/'K0c.patch')],temp)
        run(['/usr/bin/git','apply',str(ROOT/'K0c.patch')],temp)
        for row in M['files']:assert (temp/row['path']).read_bytes()==(ROOT/'candidate'/row['path']).read_bytes()
        run(['/usr/bin/git','apply','--reverse','--check',str(ROOT/'K0c.patch')],temp)
        run(['/usr/bin/git','apply','--reverse',str(ROOT/'K0c.patch')],temp)
        for row in M['files']:
            if row['before']:assert (temp/row['path']).read_bytes()==(ROOT/'base'/row['path']).read_bytes()
            else:assert not (temp/row['path']).exists()
    unchanged={
        'drivers/block/loop.c':['loop_configure','__loop_clr_fd','loop_clr_fd','lo_release','lo_free_disk','loop_handle_cmd','loop_process_work','loop_workfn','loop_rootcg_workfn','loop_remove'],
        'block/bdev.c':['bdev_release','bdev_fput','bdev_free_inode','blkdev_put_whole','blkdev_put_part','bdev_unhash','bdev_drop'],
        'block/fops.c':['blkdev_release'],
        'block/blk-core.c':['bio_poll','iocb_bio_iopoll'],
        'block/genhd.c':['__del_gendisk','del_gendisk'],
        'block/ioctl.c':['bio_cmd_bio_end_io','blk_cmd_complete'],
        'mm/backing-dev.c':['bdi_unregister','release_bdi'],
        'block/partitions/core.c':['drop_partition','part_release'],
    }
    preserved=[]
    for path,names in unchanged.items():
        for name in names:
            before=function(path,name,'base');after=function(path,name,'candidate')
            assert before==after,(path,name,'original probe/cleanup/completion byte preservation')
            preserved.append({'path':path,'function':name,**pin(after)})
    holder_rows=[]
    for row in M['files']:
        if not row['path'].endswith('.c') or row['before'] is None:continue
        before=(ROOT/'base'/row['path']).read_text();after=(ROOT/'candidate'/row['path']).read_text()
        pattern=r'^.*\bprivate_data\s*=(?!=).*$'
        x=re.findall(pattern,before,re.M);y=re.findall(pattern,after,re.M)
        assert x==y,(row['path'],'all original holder assignments preserved')
        holder_rows.append({'path':row['path'],'assignment_lines':x})
    new=(ROOT/'candidate/block/p4_private_loop_lease.c').read_text()
    assert re.search(r'\bprivate_data\s*=',new) is None
    assert not re.search(r'EXPORT_SYMBOL|copy_from_user|copy_to_user|SYSCALL_DEFINE|misc_register|ioctl\s*=',new)
    assert 'P4_PRIVATE_LOOP_ACTIVE' not in new
    assert 'previous == S64_MAX' in new and 'atomic64_try_cmpxchg' in new
    assert 'atomic_cmpxchg(&lease->target_bound, 0, 1)' in new
    assert 'get_file(file)' in new and 'target->bound_once = true;' in new
    assert 'file->f_op == &def_blk_fops' in new
    assert 'WRITE_ONCE(disk->bdi->p4_private_loop_closed, true);' in new
    assert not re.search(r'p4_private_loop_closed\s*,\s*false',new)
    conf=(ROOT/'candidate/block/Kconfig').read_text()
    section=conf.split('config P4_PRIVATE_LOOP_LEASE\n',1)[1].split('source ',1)[0]
    assert 'depends on P4_PRIVATE_LOOP_ACTOR && BLK_DEV_LOOP=y' in section and 'default n' in section
    out={'schema':'p4-k0c-exact-source-preservation-controls-v1','state':'PASSED_FINITE_SOURCE_CHECKS',
        'postimage_pins':rows,'inherited_K0b_full_bodies_equal':True,'patch_apply_and_reverse_commands':commands,
        'whole_patch_forward_and_reverse_equal':True,'original_probe_cleanup_completion_functions':preserved,
        'original_native_holder_assignments':holder_rows,'new_private_data_assignments':0,
        'normal_devices_keep_original_handlers_after_zero_gate':True,
        'kernel_runtime_tests_executed':False,'closed_foundation_only':True,
        'private_loop_issuer_enabled':False,'K1_K2_K3_qualified':False,'runtime_qualified':False,'production_ready':False}
    raw=(json.dumps(out,sort_keys=True,indent=2)+'\n').encode();(ROOT/'SOURCE-CONTROLS.json').write_bytes(raw)
    print(json.dumps({'state':out['state'],'postimages':len(rows),'unchanged_functions':len(preserved),**pin(raw)}))


if __name__=='__main__':main()
