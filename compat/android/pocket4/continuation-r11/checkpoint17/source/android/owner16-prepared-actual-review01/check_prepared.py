"""Local retained-record review only; no remote action or production import."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/workspace/scratch/94990735b266')
SOURCE = BASE / 'android-owner16-normal01-freeze-01'
EVIDENCE = BASE / 'root-recovery-20261104-02/evidence'
OUT = Path(__file__).parent
PREPARED_SHA = '6a7e5f8eb4532a019506c7f0f6077d0739fe51bf31c45455a53bab700ace73d9'
checks = []


def sha(body):
    return hashlib.sha256(body).hexdigest()


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


def original(path, size, digest):
    body = path.read_bytes()
    check('exact original ' + str(path.relative_to(BASE)), len(body) == size and sha(body) == digest)
    return body, json.loads(body)


def terminal(path, job, count):
    row = json.loads(path.read_bytes())
    check('terminal ' + job, row['job_id'] == job and row['state'] == 'succeeded'
          and row['exit_code'] == 0 and row['output_complete'] is True
          and row['output_durable'] is True and row['terminal_publication_confirmed'] is True
          and row['timed_out'] is False and row['cancelled'] is False
          and row['log_errors'] == {'stderr': None, 'stdout': None}
          and row['log_truncated'] == {'stderr': False, 'stdout': False}
          and row['log_synced'] == {'stderr': True, 'stdout': True}
          and row['log_bytes'] == {'stderr': {'seen': 0, 'stored': 0}, 'stdout': {'seen': count, 'stored': count}})


def main():
    body, actual = original(EVIDENCE / 'owner16-prepared-read01/prepared.json', 55140, PREPARED_SHA)
    _, wire = original(EVIDENCE / 'owner16-prepared-read01/stdout.log', 11867,
                       '3b91e4105cd9a212563dcbbdd3d7c28aa0d895728d149131bf21d269d101608c')
    compressed = base64.b64decode(wire['gzip_base64'], validate=True)
    check('complete compressed wire', len(compressed) == wire['gzip_bytes'] and sha(compressed) == wire['gzip_sha256'])
    envelope_raw = gzip.decompress(compressed)
    check('complete envelope', len(envelope_raw) == wire['bytes'] and sha(envelope_raw) == wire['sha256']
          and wire['collection_complete'] is True and wire['qualification'] is False)
    envelope = json.loads(envelope_raw)
    member = envelope['files']['prepared.json']
    check('single fixed member and exact original body', set(envelope['files']) == {'prepared.json'}
          and member['path'] == '/opt/p4-owner16-normal-20261105-01-state/prepared.json'
          and member['bytes'] == len(body) and member['sha256'] == PREPARED_SHA
          and member['content'].encode() == body and envelope['collection_complete'] is True
          and envelope['errors'] == [] and envelope['mutations'] is False and envelope['qualification'] is False)
    terminal(EVIDENCE / 'owner16-prepared-read01/status01.tool-original.json', '1a1adcd8120-fc05-5ae2', 11867)
    terminal(EVIDENCE / 'owner16-normal-prepare01/status01.tool-original.json', '1a1adca5b04-fc05-5ad8', 233)
    _, summary = original(EVIDENCE / 'owner16-normal-prepare01/stdout.log', 233,
                          '765fc844b0a2524b3f52620adcdd36190739d0ef23968cdd3cd241e2643fc321')
    check('post-close preparation summary', summary == {'success': True, 'result_path': member['path'],
          'bytes': len(body), 'sha256': PREPARED_SHA, 'first_error': None, 'runtime_executed': False})
    manifest_raw, manifest = original(SOURCE / 'manifest.json', 4632,
                                      'b9a9cbdc3dcdd1a7c54f72c29eea762cd18d7f1b6e64a5e0a2d33c46d296913d')
    check('28 frozen source payloads', len(manifest['files']) == 28 and len({r['path'] for r in manifest['files']}) == 28)
    for row in manifest['files']:
        raw = (SOURCE / row['path']).read_bytes()
        if len(raw) != row['bytes'] or sha(raw) != row['sha256']:
            raise AssertionError('frozen source member ' + row['path'])
    checks.append('every frozen payload whole size and SHA256')
    plan = json.loads((SOURCE / 'plan.json').read_bytes())
    canonical = json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode()
    sorted_plan = (json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()
    check('canonical CellSpec and actual pretty plan serialization', canonical == (SOURCE / 'cell.json').read_bytes()
          and sha(canonical) == actual['canonical_spec_sha256'] == plan['canonical_spec_sha256']
          and sha(sorted_plan) == actual['plan_sha256'])
    check('successful preparation only', actual['kind'] == 'owner16-normal-preparation01'
          and actual['success'] is True and actual['errors'] == [] and actual.get('first_error') is None
          and actual['runtime_executed'] is False and actual['namespace_or_network_changed'] is False
          and actual['production_ready'] is False and actual['attempt_nonce'] == plan['attempt_nonce'])
    sources = {name: {'bytes': len((SOURCE / 'source' / name).read_bytes()),
                     'sha256': sha((SOURCE / 'source' / name).read_bytes())}
               for name in ['actor.py', 'coordinator.py', 'owned.py', 'pinned_support.py', 'prepare.py', 'qualify.py']}
    check('all six source files', actual['source_files'] == sources)
    _, host = original(EVIDENCE / 'owner16-host-log-compile02/compile-result.json', 49729,
                       'dad36fe9fd79aa782bcc255e74b8cc1b1ee241a341318e179ccaa9e7f1c785ea')
    _, android = original(EVIDENCE / 'owner16-android-log-build01/build-result.json', 661519,
                          '2c53bba3ab02b396d2698dfd6e04d870ce69cc55724c6077003dca81ae9a2e0b')
    _, ordinary = original(EVIDENCE / 'owner16-host-log-ordinary02/run-result.json', 37632,
                           '5186036b7acab780f9f7d23ed6979773e1592532f896bab2679d33601f236095')
    check('actual compile and ordinary receipt pins', host['success'] is True and android['success'] is True
          and android['errors'] == [] and ordinary['success'] is True
          and plan['actual_ordinary_receipt_sha256'] == '5186036b7acab780f9f7d23ed6979773e1592532f896bab2679d33601f236095')
    for name in ['droidloomd', 'droidloom-supervisor', 'droidloom-psi-owner']:
        check('actual Host16 artifact ' + name, {k: v for k, v in plan['artifacts'][name].items()
              if k != 'destination'} == host['artifacts'][name])
    check('actual paired C16 artifact', all(plan['artifacts']['init-barrier'][k] == android['Android_artifact'][k]
          for k in ['bytes', 'sha256', 'path', 'device', 'inode']))
    _, old = original(BASE / 'android-owner15-normal01-runtime-freeze-01/actual-prepared.json', 55139,
                      'cdcf0db96db1c7100c17faa5c4b0926b544f8c41b8da8960e49788dee3926de8')
    check('old LMKD artifact remains bound', all(actual['copied_artifacts']['lmkd'][k]
          == old['copied_artifacts']['lmkd'][k] for k in ['bytes', 'sha256']))
    check('exact five copied artifacts', set(actual['copied_artifacts']) == set(plan['artifacts'])
          and len(actual['copied_artifacts']) == 5)
    for name, row in actual['copied_artifacts'].items():
        target = plan['artifacts'][name]
        check('copied artifact ' + name, row['path'] == plan['package'] + '/' + target['destination']
              and row['bytes'] == target['bytes'] and row['sha256'] == target['sha256']
              and row['identity']['device'] > 0 and row['identity']['inode'] > 0)
    check('all 86 base records before after and original identity', actual['base_before'] == actual['base_after']
          == old['base_before'] and len(actual['base_before']) == len(plan['base']['records']) == 86)
    check('every base record equals frozen expected path size hash', all(
        {k: a[k] for k in ['relative', 'bytes', 'sha256']} == {k: b[k] for k in ['relative', 'bytes', 'sha256']}
        for a, b in zip(actual['base_before'], plan['base']['records'])))
    check('all eight tools complete retained identity and SHA', len(actual['tools']) == 8
          and set(actual['tools']) == set(plan['tools_fixed_paths']) == set(plan['tools_sha256'])
          and actual['tools'] == old['tools'] and all(row['sha256'] == plan['tools_sha256'][path]
          and row['path'] == path and row['bytes'] > 0 and row['mode'] == 0o755
          for path, row in actual['tools'].items()))
    check('presenter complete retained identity', actual['presenter'] == old['presenter']
          and all(actual['presenter'][k] == plan['presenter'][k] for k in ['path', 'sha256']))
    check('Main three maps original identity and all limits', actual['main_before'] == actual['main_after']
          == actual['main_final'] == old['main_before']
          and actual['main_before']['daemon'] == plan['main']['daemon']
          and actual['main_before']['resources'] == plan['main']['resources']
          and actual['main_before']['resources']['pids.max'] == '12288'
          and actual['main_before']['framework_sha256'] == plan['main']['framework_sha256']
          and actual['main_before']['held_cgroup_identity'] == [30, 26651611]
          and actual['main_before']['installed_contract_unchanged'] is True
          and actual['main_before']['original_processes_alive_and_unchanged'] is True)
    ids = actual['id_availability']
    check('actual UID range absence observation no reservation', ids['host_uid'] == plan['spec']['host_uid'] == 61288
          and ids['subordinate_range'] == plan['spec']['subordinate_uids'] == plan['spec']['subordinate_gids']
          and ids['available_at_observation'] is True and ids['reservation_created_in_passwd_or_subid_tables'] is False
          and 0 < ids['processes_observed'] <= 20000 and set(ids['tables']) == {'/etc/subuid', '/etc/subgid'})
    check('two fresh ext4 images exact sizes and successful mkfs', len(actual['data_images']) == len(plan['data_images']) == 2
          and all(a['name'] == p['name'] and a['bytes'] == p['bytes'] and a['returncode'] == 0
                  and a['fresh_sparse_created'] is True and a['existing_userdata_copied'] is False
                  and a['identity'] != old['data_images'][i]['identity']
                  and 'Creating filesystem with ' in a['stdout'] and 'Writing superblocks and filesystem accounting information:' in a['stdout']
                  for i, (a, p) in enumerate(zip(actual['data_images'], plan['data_images']))))
    check('new package and state separate identities', actual['package_identity'] != actual['state_identity']
          and actual['package_identity'] != old['package_identity'] and actual['state_identity'] != old['state_identity'])
    check('helper groups unchanged', actual['helper_groups'] == old['helper_groups'] and plan['helper_uid'] == plan['helper_gid'] == 1000)
    resources = actual['resources_before']
    check('prepare resource observation only', resources['MemAvailable_bytes'] >= plan['mem_available_min_bytes']
          and resources['disk_available_bytes'] >= plan['disk_available_min_bytes']
          and float(re.search(r'^full avg10=([0-9.]+)', resources['memory_pressure'], re.M)[1]) <= plan['host_memory_full_avg10_max'])
    report = {'schema': 1, 'scope': 'LOCAL_RETAINED_OWNER16_PREPARED_RECORD_FULL_BINDING',
              'checks_passed': checks, 'count': len(checks), 'prepared_bytes': len(body), 'prepared_sha256': PREPARED_SHA,
              'source_manifest_sha256': sha(manifest_raw), 'source_manifest_members': 28,
              'actual_copied_artifacts': 5, 'actual_fresh_ext4_images': 2, 'base_records': 86,
              'source_files': 6, 'tools': 8, 'Main_maps_exactly_equal': True,
              'prepared_kind': actual['kind'], 'attempt_nonce': actual['attempt_nonce'],
              'canonical_spec_sha256': actual['canonical_spec_sha256'], 'plan_sha256': actual['plan_sha256'],
              'live_UID_observation': ids, 'data_images': [{k: x[k] for k in ['name', 'bytes', 'identity', 'returncode', 'fresh_sparse_created', 'existing_userdata_copied']} for x in actual['data_images']],
              'prepared_fd_close_scope': 'The exact source saves prepared.json before final data/package/state closes, but emits the matched 233-byte summary only after all normal closes; the actual successful terminal and summary complete that source path. This is not an independent post-exit FD inventory.',
              'historical_prepare_available_memory_bytes': resources['MemAvailable_bytes'],
              'runtime_resource_window_reserved': False, 'runtime_dispatch_held_until_Root_releases_heavy_framework_window': True,
              'runtime_dispatched_by_this_review': False, 'runtime_executed': False,
              'init_logger_actual_runtime_qualified': False, 'production_or_App_qualification': False,
              'prior_failures_reclassified': False, 'remote_action': False}
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    with (OUT / 'report.json').open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'checks': len(checks), 'report_bytes': len(raw), 'report_sha256': sha(raw),
                      'prepared_sha256': PREPARED_SHA, 'runtime_dispatch': False}, indent=2))


if __name__ == '__main__':
    main()
