#!/usr/bin/env python3
"""Check recorded source restoration evidence; never run the operational worker."""
from pathlib import Path, PurePosixPath
import gzip
import hashlib
import io
import json
import stat

ROOT = Path(__file__).resolve().parent
GIB = 1024 ** 3
R2_SHA = '67d352ebf88622dc2233ce4f78b4c110a412a9ca4a2c29e9d099896c10c91521'
R1_SHA = 'e9fe709e0c33abbae48ba74646ac1448a9cf8af6f739cf5dbd6583072875ed2c'
TREE = 'fa0382574f4fc18f59b2b5dd67a30939167d8c3a'


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def read(name):
    relative = PurePosixPath(name)
    need(not relative.is_absolute() and '..' not in relative.parts
         and str(relative) == name, 'canonical packet member')
    path = ROOT / name
    info = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(info.st_mode)
         and info.st_nlink == 1 and info.st_size <= 2 * 1024 ** 2,
         'bounded ordinary packet input')
    return path.read_bytes()


def decoded(body):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('nonfinite JSON value')
    return json.loads(body, object_pairs_hook=unique, parse_constant=invalid)


def recorded(name, size, digest):
    with gzip.GzipFile(fileobj=io.BytesIO(read(name))) as stream:
        body = stream.read(size + 1)
    need(len(body) == size and sha(body) == digest,
         'bounded full original decompressed evidence')
    return decoded(body)


def main():
    inventory = {}
    for line in read('FILES.sha256').decode('ascii').splitlines():
        digest, name = line.split('  ', 1)
        need(name not in inventory and len(digest) == 64
             and sha(read(name)) == digest, 'unique whole packet member')
        inventory[name] = digest
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}
    need(actual == set(inventory) | {'FILES.sha256'}, 'complete packet inventory')
    manifest = decoded(read('MANIFEST.json'))
    need(manifest['schema'] == 'pocket4-recorded-same-plan-source-restoration-v1'
         and manifest['runtime_qualified'] is False and manifest['production_ready'] is False,
         'source restoration evidence scope')
    need({row['path'] for row in manifest['files']} == actual - {'MANIFEST.json', 'FILES.sha256'}
         and len(manifest['files']) == len(actual) - 2, 'complete manifest')
    for row in manifest['files']:
        body = read(row['path'])
        need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'manifest body binding')

    before = recorded('history/R1-RESULT.json.gz', 1096163, R1_SHA)
    current = recorded('actual/R2-RESULT.json.gz', 6563547, R2_SHA)
    retirement = decoded(read('actual/R2-INDEPENDENT-RETIREMENT.json'))
    observer = decoded(read('actual/R2-INDEPENDENT-TERMINAL-RAW.json'))
    client = decoded(read('actual/R2-ORIGINAL-CLIENT-READ.json'))
    review = decoded(read('review/R2-REVIEW.json'))
    need(before['schema'] == 'pocket4-normal-same-plan-source-repair-v1'
         and before['state'] == 'FAILED' and before['source_reconcile_dispatched'] is False
         and before['source_reconcile_returned_success'] is False
         and len(before['errors']) == 1
         and before['errors'][0]['message'] == 'complete project must not remain sparse'
         and len(before['commands']) == 1036 and before['all_original_children_reaped'] is True,
         'original R1 failure and no source repair credit retained')
    need(current['schema'] == 'pocket4-normal-same-plan-source-repair-v2'
         and current['state'] == 'PASSED' and current['errors'] == []
         and current['source_tree'] == TREE and current['source_reconcile_dispatched'] is True
         and current['source_reconcile_returned_success'] is True,
         'actual successful R2 normal source repair')
    need(current['actual_R1_failure_retirement']['actual_failed_R1']['sha256'] == R1_SHA
         and current['actual_R1_failure_retirement']['R1_source_repair_credit'] is False,
         'successful successor does not rewrite predecessor failure')
    worker = read('source/repair_same_plan.py')
    need(len(worker) == 56374 and sha(worker) == '7a86286830d5ba83db799bfa2911eaa3f919d12fdfac07a5e5fc8dc8acf2a6a3'
         and current['actual_worker_source']['sha256'] == sha(worker)
         and review['repair_success_established_by_review'] is False,
         'recorded actual worker and pre-execution review remain distinct')
    need(current['adopted_child_retirement'] == [] and current['all_original_children_reaped'] is True
         and current['original_locks_held_through_child_retirement'] is True
         and len(current['actual_original_locks']) == 3, 'original lifecycle and three locks')
    commands = current['commands']
    need(len(commands) == 9131, 'all original actual commands retained')
    for command in commands:
        need(command['exit_code'] == 0 and command['actual_child_reaped'] is True
             and command['original_pidfd_held_until_reaped'] is True
             and command['after_reap_echild'] is True
             and command['waitid'] == {'pid': command['pid'], 'code': 1, 'status': 0},
             'actual original wait-owner and successful terminal')
    normal = [c for c in commands if c['name'].startswith('normal-')]
    need([c['name'] for c in normal] == ['normal-same-plan-reconcile', 'normal-verify-materialized']
         and normal == retirement['actual_normal_commands'], 'two original normal source invocations')
    need(normal[0]['argv'][3] == 'reconcile' and normal[1]['argv'][3] == 'verify-materialized'
         and normal[0]['argv'][:3] == normal[1]['argv'][:3]
         and normal[0]['argv'][4:] == normal[1]['argv'][4:], 'same original tool, lock and checkout')
    streams = decoded(read('actual/NORMAL-STREAMS.json'))
    need(streams['truncated'] is False and len(streams['files']) == 4, 'complete original normal streams')
    files = {f['path']: f for f in streams['files']}
    need(len(files) == 4, 'distinct actual stream paths')
    for command in normal:
        for name in ('stdout', 'stderr'):
            pin = command['saved_' + name]
            item = files[pin['path']]
            body = item['text'].encode('utf-8')
            need(item['eof'] is True and len(body) == item['size'] == pin['bytes']
                 and sha(body) == item['sha256'] == pin['sha256'], 'actual original stream body')
            f9 = pin['f9']
            need(item['version'] == ':'.join(str(f9[i]) for i in (0, 1, 6, 7, 8)),
                 'original stream inode and nanosecond identity')

    totals = current['restored_source_totals']
    need(totals['members_verified'] == 26047 and totals['logical_bytes_verified'] == 13818632037
         and [r['members_verified'] for r in totals['actual_body_receipts']] == [25059, 988]
         and [r['logical_bytes_verified'] for r in totals['actual_body_receipts']] == [12803167854, 1015464183]
         and all(r['every_actual_body_Git_blob_and_SHA256_verified'] is True
                 for r in totals['actual_body_receipts']), 'recorded complete restored payload scope')
    need(current['manifest_body_identical'] is True and current['manifest_F9_identical'] is False
         and current['manifest_before']['original']['sha256'] == current['manifest_after']['original']['sha256']
         == '704ec2a6ba4fec751490b0da492b161887479ef9579f18025374d56ced72f5a3'
         and current['manifest_before']['original']['f9'][1] == 61116705
         and current['manifest_after']['original']['f9'][1] == 61122520,
         'normal manifest rewrite preserves bytes and changes real inode')
    need(current['complete_original_canonical_producer_unchanged'] is True
         and current['canonical_producer_before']['sha256'] == current['canonical_producer_after']['sha256']
         and current['canonical_producer_before']['bytes'] == current['canonical_producer_after']['bytes'] == 717555,
         'recorded canonical producer bookends unchanged')
    resources = current['resources']
    need(resources['preflight_free_floor'] == 160 * GIB and resources['runtime_free_floor'] == 144 * GIB
         and resources['growth_cap'] == 16 * GIB and resources['fixed_worker_seconds'] == 1710
         and resources['hard_unit_seconds'] == 1800
         and resources['maximum_observed_growth'] <= resources['growth_cap']
         and resources['minimum_free_bavail'] >= resources['runtime_free_floor'], 'original resource bounds')
    need(current['worker']['affinity'] == [22, 23]
         and current['worker']['limits'] == {'cpu.max': '200000 100000', 'memory.high': '1610612736',
             'memory.max': '2147483648', 'memory.swap.max': '0', 'pids.max': '256'}, 'actual bounded worker')
    need(retirement['schema'] == 'pocket4-source-repair-r2-independent-retirement-v1'
         and retirement['passed'] is True and retirement['repair_result']['sha256'] == R2_SHA
         and retirement['repair_result']['bytes'] == 6563547
         and retirement['original_client_exit_code'] == 0
         and retirement['original_client_output_complete'] is True
         and retirement['exact_unit_cgroup_absent'] is True
         and retirement['original_three_lock_F9_unchanged_and_locks_released'] is True
         and retirement['all26047_live_F9_match_actual_body_receipts_after_unit_retirement'] is True
         and retirement['all651_original_project_metadata_verified'] is True
         and retirement['original2336_canonical_producer_snapshot_unchanged'] is True
         and retirement['whole651_body_equality_claimed'] is False,
         'independent actual retirement and bounded evidence scope')
    need(observer['passed'] is True and observer['commands_verified'] == 9131
         and observer['projects_verified'] == 651 and observer['canonical_producer_files_verified'] == 2336
         and observer['body_inventory_members'] == 26047 and observer['body_inventory_logical_bytes'] == 13818632037
         and observer['source_mutations'] == 0, 'actual independent observer')
    need(client['status']['state'] == 'exited' and client['status']['exit_code'] == 0
         and client['status']['output_complete'] is True and client['output_complete'] is True
         and client['text_is_lossy'] is False and client['truncated_before_offset'] is False
         and client['offset'] == 0 and client['next_offset'] == client['available_end'],
         'complete original client terminal')
    for value in (before, current, retirement, observer):
        need(value['runtime_qualified'] is False and value['production_ready'] is False,
             'no source evidence promoted to Android qualification')
    need(all(current[k] == 0 for k in ('Android_starts', 'compilations', 'installations',
         'external_CURRENT_mutations', 'owner_or_lease_changes', 'historical_tests_counted_as_fresh')),
         'source restoration does not start Android or compile vendor')
    print(json.dumps({'state': 'PASS_RECORDED_SOURCE_RESTORATION_AND_RETIREMENT_ONLY',
        'packet_files': len(actual), 'recorded_restored_members': 26047,
        'recorded_restored_logical_bytes': 13818632037, 'recorded_project_metadata': 651,
        'recorded_actual_commands': 9131, 'actual_original_normal_streams_verified': 4,
        'historical_R1_failure_preserved': True, 'live_AOSP_bodies_rehashed_here': 0,
        'source_reconcile_executed_here': False, 'vendor_build_executed_here': False,
        'Android_starts': 0, 'runtime_qualified': False, 'production_ready': False}, sort_keys=True))


if __name__ == '__main__':
    main()
