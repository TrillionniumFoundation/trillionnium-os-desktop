#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'publication'
M=json.loads((ROOT/'MANIFEST.json').read_bytes())


def pin(path):
    b=path.read_bytes()
    return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def main():
    assert not OUT.exists(),'create-only immutable publication packet'
    OUT.mkdir()
    names=['README.md','K0c.patch','MANIFEST.json','SOURCE-PACKET.json','prepare.py',
        'check_source.py','prepare_compile.py','compile_objects.py','ORIGINAL-INPUTS.json',
        'SOURCE-CONTROLS.json','ROOT-INDEPENDENT-SOURCE-REVIEW.json','OBJECT-COMPILE.json',
        'ACTUAL-LOGS.json','HOST-JOBS.json','prepare_publication.py']
    names += ['candidate/'+row['path'] for row in M['files']+M['unchanged_K0b_inherited_files']]
    names += ['base/'+row['path'] for row in M['files'] if row['before']]
    names += ['base/'+p for p in ['mm/Makefile','drivers/block/Makefile','block/partitions/Makefile','scripts/Makefile.lib']]
    names += ['additions/'+row['path'] for row in M['files'] if row['before'] is None]
    names += ['revisions/compile-r1/'+p for p in ['compile_objects.py','prepare_compile.py',
        'SOURCE-PACKET.json','ORIGINAL-INPUTS.json','OBJECT-COMPILE.json','DIAGNOSTICS.json']]
    assert len(names)==len(set(names))
    for name in names:
        p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    closure={'schema':'p4-k0c-source-and-evidence-publication-closure-v1',
        'kernel_patch':pin(ROOT/'K0c.patch'),'base_K0b_commit':M['base_K0b_commit'],
        'files':[{'path':name,**pin(OUT/name)} for name in sorted(names)]}
    (OUT/'SOURCE-CLOSURE.json').write_text(json.dumps(closure,sort_keys=True,indent=2)+'\n')
    handoff={'schema':'p4-k0c-closed-foundation-handoff-v1',
        'state':'CLOSED_SOURCE_REVIEW_AND_24_MATCHING_OBJECTS_PASSED',
        'repository':'TrillionniumFoundation/trillionnium-os-desktop',
        'repository_root':'compat/android/pocket4/current-private-loop-K0c-20261120',
        'parent_commit':M['base_K0b_commit'],'source_closure':pin(OUT/'SOURCE-CLOSURE.json'),
        'kernel_patch':pin(OUT/'K0c.patch'),'source_manifest':pin(OUT/'MANIFEST.json'),
        'independent_source_review':pin(OUT/'ROOT-INDEPENDENT-SOURCE-REVIEW.json'),
        'finite_source_controls':pin(OUT/'SOURCE-CONTROLS.json'),
        'actual_compile':pin(OUT/'OBJECT-COMPILE.json'),'actual_complete_logs':pin(OUT/'ACTUAL-LOGS.json'),
        'compile_job':'1a1f9cfad14-ffbe-1a5c','compile_host':'pocket4',
        'compile_host_root':'/home/alex/work/p4-private-loop-k0c-20261120-3b9d-r2',
        'actual_C_objects':24,'feature_on_objects':15,'feature_off_objects':9,
        'actual_reaped_commands':121,'complete_actual_log_files':242,
        'original_C_dependencies':1076,'retained_actual_input_descriptors':1148,
        'postimage_count':15,'unchanged_inherited_K0b_files':4,
        'original_probe_cleanup_completion_function_bodies_preserved':28,
        'first_recipe_failure_preserved':True,'C_source_changed_to_fix_recipe':False,
        'next_stage':'K1 exact closed realm/control/allocator source; native OFD lifetime and all publish paths require review',
        'K1_allocator_complete':False,'K2_original_probe_and_source_configuration_complete':False,
        'K3_graph_IO_retirement_complete':False,'issuer_enabled':False,'kernel_linked':False,
        'kernel_installed':False,'kernel_loaded':False,'kernel_executed':False,'VM_started':False,
        'Android_started':False,'original_data_images_opened':False,'CURRENT_modified':False,
        'runtime_qualified':False,'production_ready':False}
    (OUT/'HANDOFF.json').write_text(json.dumps(handoff,sort_keys=True,indent=2)+'\n')
    rows=[]
    for p in sorted(OUT.rglob('*')):
        if not p.is_file():continue
        raw=p.read_bytes();rows.append({'path':str(p.relative_to(OUT)),**pin(p),
            'git_blob_sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
    publication={'schema':'p4-k0c-complete-publication-manifest-v1',
        'parent_commit':M['base_K0b_commit'],'files':rows,
        'private_loop_issuer_enabled':False,'runtime_qualified':False,'production_ready':False}
    (OUT/'PUBLICATION-MANIFEST.json').write_text(json.dumps(publication,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'files':len(rows)+1,'total_bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),
        'handoff':pin(OUT/'HANDOFF.json'),'closure':pin(OUT/'SOURCE-CLOSURE.json')}))


if __name__=='__main__':main()
