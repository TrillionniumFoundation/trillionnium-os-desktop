#!/usr/bin/env python3
"""Adapt the already executed matching object recipe to the two K1a C units."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
K0C = ROOT.parent/'p4_private_loop_k0c'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def once(body, old, new):
    assert body.count(old) == 1, (old, body.count(old))
    return body.replace(old, new)


def main():
    old_raw = (K0C/'compile_objects.py').read_bytes()
    assert pin(old_raw) == {'bytes': 18600, 'sha256': '7d2b0b33f916db37171e3fce7fca768cc2e8c9834f363056b604034fadbeb224'}
    old_packet_raw = (K0C/'SOURCE-PACKET.json').read_bytes()
    assert pin(old_packet_raw) == {'bytes': 453150, 'sha256': '62cecfa6ac59ce6077a87d61600811da7421a63d6899cf642e0444d3c3afae6b'}
    old_packet = json.loads(old_packet_raw)
    manifest = json.loads((ROOT/'MANIFEST.json').read_bytes())
    packet = {
        'schema': 'p4-k1a-matching-native-allocation-object-source-packet-v1',
        'manifest': manifest,
        'sources': {row['path']: (ROOT/'candidate'/row['path']).read_text()
                    for row in manifest['files']+manifest['unchanged_inherited_files']},
        'original_checks': old_packet['original_checks'],
        'fresh_original_inputs': old_packet['fresh_original_inputs'],
        'prior_K0c_source_packet': pin(old_packet_raw),
    }
    raw = (json.dumps(packet, sort_keys=True, indent=2)+'\n').encode()
    (ROOT/'SOURCE-PACKET.json').write_bytes(raw)
    runner = old_raw.decode()
    runner = runner.replace('p4-private-loop-k0c-20261120-3b9d-r2', 'p4-private-loop-k1a-20261120-3b9d-r1')
    runner = runner.replace('Compile isolated K0c enabled/disabled objects', 'Compile isolated K1a native allocator and normal loop objects')
    runner = runner.replace('p4-k0c-matching-closed-block-object-compile-v1', 'p4-k1a-matching-native-allocation-object-compile-v1')
    runner = runner.replace('bounded K0c object compile expired', 'bounded K1a object compile expired')
    runner = runner.replace('K0b/K0c headers.', 'K0b/K0c/K1a headers.')
    start = runner.index('NEW_UNITS = ')
    end = runner.index('\n\n\n', start)
    runner = runner[:start]+"NEW_UNITS = ('block/p4_private_loop_realm', 'drivers/block/loop')\nINHERITED_UNITS = ()"+runner[end:]
    runner = once(runner, "PACKET_PIN = "+repr(pin(old_packet_raw)), "PACKET_PIN = "+repr(pin(raw)))
    runner = once(runner, "packet['schema'] == 'p4-k0c-matching-object-source-packet-v1'\n         and manifest['base_K0b_commit'] == '69e7c31c9e7e34fa39d3422df1c22d4c5f33d9ce'\n         and manifest['kernel_version'] == '6.18.64' and len(manifest['files']) == 15",
        "packet['schema'] == 'p4-k1a-matching-native-allocation-object-source-packet-v1'\n         and manifest['parent_K0c_commit'] == 'f83f52dde3594d7eef4a1e44785f940c824467d5'\n         and len(manifest['files']) == 5 and manifest['K1_complete'] is False")
    runner = runner.replace('exact closed source-only K0c packet', 'exact closed native-allocation K1a source packet')
    runner = runner.replace("manifest['unchanged_K0b_inherited_files']", "manifest['unchanged_inherited_files']")
    runner = runner.replace('len(needed) == 19', 'len(needed) == 21')
    runner = runner.replace('only 15 new/changed postimages and four unchanged K0b source bodies', 'only five changed/new and sixteen inherited exact source bodies')
    point = '    original_checks = []\n'
    runner = once(runner, point, '''    prior_K0c_ref, prior_raw = read(
        Path('/home/alex/work/p4-private-loop-k0c-20261120-3b9d-r2/OBJECT-COMPILE.json'),
        {'bytes':1616986,'sha256':'8e0e4ea16f225c0b531eea33fc8f74e781a5f3e80984ee1c1acf7ae6582f3204'}, True)
    prior = json.loads(prior_raw)
    need(prior['state'] == 'MATCHING_24_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED'
         and len(prior['objects']) == 24
         and prior['source_packet']['sha256'] == packet['prior_K0c_source_packet']['sha256'],
         'actual prior K0c matching compilation, not new runtime credit')
    OBS['prior_actual_K0c_objects'] = prior_K0c_ref
'''+point)
    runner = runner.replace("'CONFIG_P4_PRIVATE_LOOP_ACTOR=1','CONFIG_P4_PRIVATE_LOOP_LEASE=1'", "'CONFIG_P4_PRIVATE_LOOP_ACTOR=1','CONFIG_P4_PRIVATE_LOOP_LEASE=1','CONFIG_P4_PRIVATE_LOOP_REALM=1'")
    runner = runner.replace("'-DCONFIG_P4_PRIVATE_LOOP_ACTOR=1','-DCONFIG_P4_PRIVATE_LOOP_LEASE=1'", "'-DCONFIG_P4_PRIVATE_LOOP_ACTOR=1','-DCONFIG_P4_PRIVATE_LOOP_LEASE=1','-DCONFIG_P4_PRIVATE_LOOP_REALM=1'")
    old_check = '''            if unit == 'block/p4_private_loop_lease':
                for name in ('p4_private_loop_actor_get','p4_private_loop_actor_put','p4_private_loop_actor_check_task'):
                    need(' U '+name+'\\n' in symbols, 'real K0b actor references linked into compiled foundation')
                for name in ('p4_private_loop_disk_gate','p4_private_loop_bdi_gate','p4_private_loop_authorization_bind'):
                    need(' T '+name+'\\n' in symbols, 'actual closed gate/OFD constructor compiled')
                need('__ksymtab' not in symbols, 'no new module symbol exports')
'''
    new_check = '''            if unit == 'block/p4_private_loop_realm':
                for name in ('p4_private_loop_actor_check_task', 'p4_private_loop_lease_create',
                             'p4_private_loop_device_alloc_unpublished', 'p4_private_loop_device_retire_unpublished'):
                    need(' U '+name+'\\n' in symbols, 'real existing actor/lease and native driver API calls')
                for name in ('p4_private_loop_realm_create', 'p4_private_loop_allocate_closed',
                             'p4_private_loop_retire_closed'):
                    need(' T '+name+'\\n' in symbols, 'actual internal realm allocation and retirement compiled')
                need('__ksymtab' not in symbols, 'no new realm module symbol exports')
            if mode == 'enabled' and unit == 'drivers/block/loop':
                for name in ('blk_mq_alloc_tag_set', '__blk_mq_alloc_disk',
                             'blk_mq_free_tag_set', 'p4_private_loop_target_attach'):
                    need(' U '+name+'\\n' in symbols, 'actual native allocator or closed target API')
                for name in ('p4_private_loop_device_alloc_unpublished',
                             'p4_private_loop_device_retire_unpublished'):
                    need(' T '+name+'\\n' in symbols, 'actual unpublished native loop constructor/retirement')
'''
    runner = once(runner, old_check, new_check)
    runner = once(runner, "OBS.update(state='MATCHING_24_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED',", "OBS.update(state='MATCHING_3_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED',")
    runner = once(runner, 'full_kernel_built=False,live_actor_or_private_loop_issued=False)',
        'full_kernel_built=False,live_actor_or_private_loop_issued=False,\n        K1_complete=False,real_control_or_block_OFD_created=False,private_device_published=False)')
    compile(runner, 'compile_objects.py', 'exec')
    (ROOT/'compile_objects.py').write_text(runner)
    print(json.dumps({'source_packet': pin(raw), 'runner': pin(runner.encode()),
                      'enabled_units': 2, 'disabled_units': 1}))


if __name__ == '__main__':
    main()
