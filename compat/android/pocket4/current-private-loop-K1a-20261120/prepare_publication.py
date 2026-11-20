#!/usr/bin/env python3
"""Freeze the reviewed source and original object evidence into one Git packet."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'publication'


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    assert not OUT.exists(), 'create-only publication packet'
    manifest = json.loads((ROOT/'MANIFEST.json').read_bytes())
    review = json.loads((ROOT/'ROOT-INDEPENDENT-SOURCE-REVIEW.json').read_bytes())
    actual = json.loads((ROOT/'OBJECT-COMPILE.json').read_bytes())
    assert review['source_review_passed'] and review['patch'] == manifest['patch']
    assert actual['state'] == 'MATCHING_3_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED'
    assert len(actual['objects']) == 3 and len(actual['commands']) == 16
    names = ['README.md', 'K1a.patch', 'MANIFEST.json', 'SOURCE-PACKET.json',
             'prepare.py', 'check_source.py', 'prepare_compile.py', 'compile_objects.py',
             'SOURCE-CONTROLS.json', 'ROOT-INDEPENDENT-SOURCE-REVIEW.json',
             'OBJECT-COMPILE.json', 'ACTUAL-LOGS.json', 'ACTUAL-READBACK.json',
             'HOST-JOBS.json', 'prepare_publication.py']
    names += ['candidate/'+row['path'] for row in manifest['files']+manifest['unchanged_inherited_files']]
    names += ['base/'+row['path'] for row in manifest['files'] if row['before']]
    names += ['additions/'+row['path'] for row in manifest['files'] if row['before'] is None]
    names += ['additions/drivers/block/private_loop_allocation.inc']
    names += [str(path.relative_to(ROOT)) for path in sorted((ROOT/'actual-logs').iterdir())]
    assert len(names) == len(set(names)) and len(names) == 74
    OUT.mkdir()
    for name in names:
        path = OUT/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, path)
    closure = {'schema': 'p4-k1a-source-and-evidence-closure-v1',
               'parent_commit': manifest['parent_K0c_commit'],
               'files': [{'path': name, **pin(OUT/name)} for name in sorted(names)]}
    (OUT/'SOURCE-CLOSURE.json').write_text(json.dumps(closure, sort_keys=True, indent=2)+'\n')
    handoff = {
        'schema': 'p4-k1a-unpublished-native-allocation-handoff-v1',
        'state': 'CLOSED_ALLOCATOR_SOURCE_REVIEW_AND_3_MATCHING_OBJECTS_PASSED',
        'repository': 'TrillionniumFoundation/trillionnium-os-desktop',
        'repository_root': 'compat/android/pocket4/current-private-loop-K1a-20261120',
        'parent_commit': manifest['parent_K0c_commit'],
        'source_closure': pin(OUT/'SOURCE-CLOSURE.json'),
        'kernel_patch': pin(OUT/'K1a.patch'),
        'source_manifest': pin(OUT/'MANIFEST.json'),
        'independent_source_review': pin(OUT/'ROOT-INDEPENDENT-SOURCE-REVIEW.json'),
        'finite_source_controls': pin(OUT/'SOURCE-CONTROLS.json'),
        'actual_compile': pin(OUT/'OBJECT-COMPILE.json'),
        'actual_complete_logs': pin(OUT/'ACTUAL-LOGS.json'),
        'actual_readback': pin(OUT/'ACTUAL-READBACK.json'),
        'compile_host': 'pocket4',
        'compile_job': '1a1f9e701d3-ffbe-1aa2',
        'compile_host_root': '/home/alex/work/p4-private-loop-k1a-20261120-3b9d-r1',
        'actual_C_objects': 3, 'feature_on_objects': 2, 'feature_off_objects': 1,
        'actual_reaped_commands': 16, 'complete_actual_log_files': 32,
        'actual_log_bytes': 27340, 'original_C_dependencies': 692,
        'retained_actual_input_descriptors': 765, 'changed_postimages': 5,
        'unchanged_inherited_K0c_K0b_files': 16,
        'K0c_closed_gates_unchanged': True,
        'next_stage': 'Native control/block OFD, private lookup and original index ABI with full lifecycle',
        'K1_complete': False, 'real_control_or_block_OFD_created': False,
        'private_device_published': False, 'original_control_index_ABI_selected': False,
        'K2_original_probe_configuration_qualified': False, 'K3_graph_IO_retirement_qualified': False,
        'issuer_enabled': False, 'kernel_linked': False, 'kernel_installed': False,
        'kernel_loaded': False, 'kernel_executed': False, 'VM_started': False,
        'Android_started': False, 'original_data_images_opened': False,
        'CURRENT_modified': False, 'runtime_qualified': False, 'production_ready': False,
    }
    (OUT/'HANDOFF.json').write_text(json.dumps(handoff, sort_keys=True, indent=2)+'\n')
    rows = []
    for path in sorted(OUT.rglob('*')):
        if path.is_file():
            raw = path.read_bytes()
            rows.append({'path': str(path.relative_to(OUT)), **pin(path),
                         'git_blob_sha': hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
    publication = {'schema': 'p4-k1a-complete-publication-manifest-v1',
                   'parent_commit': manifest['parent_K0c_commit'], 'files': rows,
                   'issuer_enabled': False, 'runtime_qualified': False, 'production_ready': False}
    (OUT/'PUBLICATION-MANIFEST.json').write_text(json.dumps(publication, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'files': len(rows)+1,
                      'total_bytes': sum(path.stat().st_size for path in OUT.rglob('*') if path.is_file()),
                      'handoff': pin(OUT/'HANDOFF.json'), 'closure': pin(OUT/'SOURCE-CLOSURE.json')}))


if __name__ == '__main__':
    main()
