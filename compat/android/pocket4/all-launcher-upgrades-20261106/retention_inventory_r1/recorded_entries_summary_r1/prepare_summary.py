#!/usr/bin/env python3
"""Freeze a single-file host-only projection of the completed r2 observation."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUTS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + '\n').encode()


def pin(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def read(path, expected=None):
    raw = (ROOT / path).read_bytes()
    value = pin(path, raw)
    if expected is not None:
        assert (value['bytes'], value['sha256']) == expected, path
    if value not in INPUTS:
        INPUTS.append(value)
    return raw


def put(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, 'refuse different existing artifact: ' + name
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return pin(name, raw)


def definitions(raw):
    lines = raw.decode().splitlines(True)
    return {node.name: ''.join(lines[node.lineno - 1:node.end_lineno]) for node in ast.parse(raw).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def main():
    artifact_raw = read('retention_inventory_r1/observer-candidate-r2/actual-public/artifact.original.json',
        (62484, '19ad825b48aef18d1e2c0264228c298c0e92311932347992c15877964a4b270c'))
    artifact = json.loads(artifact_raw)
    root_proof_raw = read('retention_inventory_r1/observer-candidate-r2/actual-public/root-validation.actual.json')
    proof = json.loads(root_proof_raw)
    assert proof['status'] == 'PASS_BOUNDED_METADATA_ONLY' and proof['job_id'] == '1a1b31db305-fc05-80a6'
    assert proof['artifact_sha256'] == sha(artifact_raw) and proof['deletions'] == 0
    assert artifact['ok'] is True and artifact['errors'] == []
    assert artifact['bounded_observation_finished'] is True and artifact['all_tree_scans_complete'] is False
    assert artifact['exact_reference_summary'] == {'count': 797, 'observed': 776, 'absent': 20, 'unresolved': 1}
    assert artifact['reference_path_changes'] == [] and artifact['reclaimable_bytes'] is None
    original_stream = artifact['entries_private']
    assert original_stream['bytes'] == 27782209
    assert original_stream['sha256'] == 'b016cbfc28c4aca2c52d85127cc89683043a50f3ed44ee15c574077e5e3636d5'
    scope_raw = read('retention_inventory_r1/observer-candidate-r2/scope.review-only.json',
        (126003, 'd7ad8e49ea6d94d0705342c665f4bb5c88b531e0aecd7ef94f2da5f34c7c9e5c'))
    scope = json.loads(scope_raw)
    protection_raw = read('retention_inventory_r1/DEPENDENCY_PROTECTION.json')
    protection = json.loads(protection_raw)
    references = scope['references']
    lookup = {(row['coordinate'], row['path']): row for row in references}
    assert len(lookup) == len(references) == 797
    targets = []
    for item in protection['retained_previous_APKs']:
        known = lookup[('host', item['path'])]
        if 'file' in item:
            original_field, original_stat = 'file', item['file']
            normalized_stat = dict(original_stat)
        else:
            original_field, original_stat = 'stat', item['stat']
            assert set(original_stat) == {'dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns'}
            normalized_stat = {'st_' + key: value for key, value in original_stat.items()}
        assert set(normalized_stat) == {'st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'}
        assert all(type(value) is int for value in normalized_stat.values())
        targets.append({'reference_id': known['id'], 'package': item['package'],
                        'historical_retained_pin': {'bytes': item['bytes'], 'sha256': item['sha256'],
                            'file': normalized_stat, 'original_stat_field': original_field,
                            'original_stat': original_stat,
                            'normalization': 'prefix st_ only for actual first-four-install short stat keys; integer values unchanged'}})
    assert len(targets) == 12 and sum(row['historical_retained_pin']['bytes'] for row in targets) == 2136945962
    request = {'schema': 'pocket4-recorded-retention-summary-request-v1',
        'observation_binding': {'actual_job': proof['job_id'],
            'artifact': pin('retention_inventory_r1/observer-candidate-r2/actual-public/artifact.original.json', artifact_raw),
            'root_joint_validation': pin('retention_inventory_r1/observer-candidate-r2/actual-public/root-validation.actual.json', root_proof_raw),
            'actual_outer_stdout_sha256': proof['stdout_sha256'], 'actual_terminal_sha256': proof['terminal_sha256'],
            'actual_scope': scope['protected_scope_reference'],
            'sampled_before_ZBJ_full48_upgrade': True,
            'not_a_current_post_upgrade_target_observation': True,
            'observation_incomplete_trees': [{key: row[key] for key in ('path', 'status')} for row in artifact['tree_observations']
                if row['status'] != 'COMPLETE_METADATA_WALK'],
            'all_tree_scans_complete': False, 'reclaimable_bytes': None, 'original_failed_receipts_changed': False},
        'entries': original_stream, 'references': references, 'previous_APKs': targets,
        'expected_reference_summary': artifact['exact_reference_summary'], 'reference_path_changes': []}
    request_raw = encoded(request)
    assert len(request_raw) <= 262144
    request_pin = put('summary-request.review-only.json', request_raw)
    body = (HERE / 'summary_body.py').read_bytes()
    source = ("#!/usr/bin/env python3\nREQUEST_BYTES = " + repr(len(request_raw)) +
              "\nREQUEST_SHA256 = " + repr(sha(request_raw)) +
              "\nEXACT_ENTRIES_PATH = " + repr(original_stream['path']) + "\n\n").encode() + body
    compile(source, 'summarize_recorded_entries.py', 'exec')
    source_pin = put('summarize_recorded_entries.py', source)
    legacy = read('successor_audit_requests/diagnostics/calendar-aapt2-stderr-summary-r1/summarize_fixed_stderr.py')
    census_source = read('successor_audit_requests/diagnostics/google-maven-aapt2-host-proof-r3/prepare_official_aapt2.py')
    assert definitions(source)['census'] == definitions(census_source)['census']
    assert definitions(source)['need'] == definitions(legacy)['need']
    observer_source = read('retention_inventory_r1/observer-candidate-r2/observe_retention.py',
        (37625, '7974525bda72cd2b20d1e364aa765df4f3ebcdde0f9931180b0e344f37b64670'))
    put('reader-against-actual-stderr-summary.diff', ''.join(difflib.unified_diff(legacy.decode().splitlines(True),
        source.decode().splitlines(True), fromfile='actual-calendar-fixed-stderr-summary', tofile='review-only-recorded-retention-selection')))
    cp = subprocess.run([sys.executable, '-I', '-B', str(HERE / 'test_summary.py')],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
    put('local-controls.stdout.original.json', cp.stdout)
    put('local-controls.stderr.original.txt', cp.stderr)
    assert cp.returncode == 0, cp.stderr.decode()
    controls = json.loads(cp.stdout)
    assert controls['ok'] and len(controls['checks']) == 3 and all(row['passed'] for row in controls['checks'])
    assert controls['original_private_stream_read'] is False and controls['whole_process_descriptor_identities_restored'] is True
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', source.decode()], 'cwd': '/home/alex/work',
        'stdin': request_raw.decode(), 'timeout_seconds': 60, 'cpu_quota_percent': 50,
        'memory_max_bytes': 268435456, 'nice': 10,
        'idempotency_key': 'sidecar-evidence-20261106-retention-recorded-entry-summary-r1'}
    packet_pin = put('process-request.review-only.json', encoded(packet))
    review = {'schema': 'pocket4-recorded-retention-summary-source-review-v1',
        'state': 'LOCAL_PREPARED_NOT_SUBMITTED', 'original_observation_job': proof['job_id'],
        'worker': source_pin, 'input': request_pin, 'packet': packet_pin,
        'only_host_file_opened_besides_self_FD_metadata': original_stream,
        'known_reference_scope_rows': 797, 'published_previous_APK_rows': 12,
        'expected_published_gap_rows': 21, 'output_paths_must_equal_original_reviewed_reference_scope': True,
        'stream_bound_bytes': 33554432, 'actual_stream_bytes': 27782209,
        'stream_line_bound_bytes': 65536, 'whole_stream_read_seconds': 30,
        'outer_seconds': 60, 'memory_bytes': 268435456, 'public_output_bound_bytes': 131072,
        'full_original_stream_stat_binding_including_blocks': True,
        'absolute_nofollow_chain_reopened_after_read': True,
        'private_tree_names_or_other_contents_exported': False,
        'recorded_paths_reopened_or_scanned': False, 'runtime_guard_or_action_lock_acquired': False,
        'metadata_is_as_of_original_observation_not_new_target_state': True,
        'old_APK_hash_is_archived_reference_not_new_APK_content_verification': True,
        'allocated_bytes_are_not_reclaimable': True, 'production_ready': False, 'cleanup_eligible': False,
        'borrowed_stream_local_controls': controls, 'root_private_path_reader_actual_test_claim': False,
        'remote_submissions': 0}
    put('SOURCE_REVIEW.json', encoded(review))
    put('README.md', '''# Projection of the completed retention observation

This proposal opens only the exact root-owned entries.private.jsonl produced by
the completed r2 metadata observation. Its 27,782,209 original bytes, full
recorded stat (including allocated blocks), entire SHA256 and absolute nofollow
path must remain equal before and after a bounded sequential read.

The input fixes all 797 previously reviewed reference IDs and paths. The reader
checks both complete observation phases, publishes only the 12 retained older
APK references plus the 20 absent and one unresolved reference, and omits all
other reference and tree paths. It reads no APK, recorded directory, existing
process, mount, business data or permission content. Only its own descriptor
metadata is inspected for complete original-identity restoration.

The output is a projection of the prior observation, not a fresh target scan.
It was sampled before the new ZBJ full48 upgrade; no post-upgrade current-target
claim is made. The first four older receipts use short stat field names; the
request retains that original shape and explicitly maps only the st_ prefix,
preserving every integer. The other eight retained-file records use file/st_*.
Historical retained-APK SHA256 values are explicitly references only; this
reader does not hash those APKs. Allocated blocks and hardlink/inode aggregation
do not establish reclaimable space, absence of external aliases, or permission
to remove anything. The original shared-work-tree budget stop and unvisited
build08 tree remain incomplete. Production readiness and deletion eligibility
remain false.

Three local controls use a real owned temporary stream: bounded full-hash
projection with exact large integers and inode deduplication, a wrong-hash
rejection, and a duplicate-phase rejection. They also verify the borrowed FD
offset/stat/liveness and the complete original process FD identities. They do
not execute the root-only private-path reader or read the original stream.

The exact process request is review-only and uses one new stable key. Root
dispatches and settles it; no request has been submitted by this preparation.
''')
    outputs = [pin(path.name, path.read_bytes()) for path in sorted(HERE.iterdir()) if path.is_file()
               and path.name not in ('SOURCE_PINS.json', 'FINAL_LOCAL_VALIDATION.json')]
    manifest = {'schema': 'pocket4-recorded-retention-summary-source-pins-v1', 'inputs': INPUTS,
                'outputs': outputs, 'remote_submissions': 0, 'runtime_actions': 0}
    manifest_pin = put('SOURCE_PINS.json', encoded(manifest))
    print(json.dumps({'ok': True, 'worker': source_pin, 'input': request_pin, 'packet': packet_pin,
                      'manifest': manifest_pin, 'local_controls': 3, 'remote_submissions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
