#!/usr/bin/env python3
"""Seal a separate launch after exact actual init evidence; no remote execution."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = {
    'new_session_once.py': (28943, 'eb02cc1e7669be21ad7f741af2438b7442fbac767a83587a0b285f764f34c909'),
    'actual-init/stdout.original.jsonl': (6447, 'a5510436a8adfdb3a0f3568b795ae6cdaec259613fb4d2ee04f7ef2e3913ae1d'),
    'actual-init/status-1.original.txt': (731, '526f6539990d6768cbab556dd6a628c40d86b41f54135938a9d1dda1d3740e25'),
}
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
ROOT = '/home/alex/work/pocket4-beike-owned-new-session-20261106-r1'
ACTUAL_ARTIFACT = {'path': ROOT + '/init-owned-lifetime.json', 'bytes': 5491,
    'sha256': 'f50079a535947f1029264fe04336cc295ec7928e536aae630015c5bcc1f97185'}
ACTUAL_SCOPE = {'path': FLOW + '/scope.json', 'bytes': 1002,
    'sha256': '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + '\n').encode('ascii')


def once(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view); require(count > 0, 'WRITE_PROGRESS'); view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    require(path.read_bytes() == raw, 'NEW_LOCAL_FILE_READBACK')


def main():
    files = {}
    for relative, (size, digest) in EXPECTED.items():
        path = HERE / relative
        require(path.is_file() and not path.is_symlink(), 'EXACT_LOCAL_REGULAR_INPUT')
        raw = path.read_bytes()
        require(len(raw) == size and sha(raw) == digest, 'ACTUAL_INIT_OR_SOURCE_PIN_CHANGED:' + relative)
        files[relative] = raw
    status = json.loads(files['actual-init/status-1.original.txt'])
    require(status.get('job_id') == '1a1b23c7c67-fc05-7d17' and status.get('state') == 'succeeded' and
        type(status.get('exit_code')) is int and status['exit_code'] == 0 and
        all(status.get(k) is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed', 'audit_recorded')) and
        all(status.get(k) is False for k in ('timed_out', 'cancelled', 'automatic_retry')) and
        status.get('log_bytes') == {'stdout': {'seen': 6447, 'stored': 6447}, 'stderr': {'seen': 0, 'stored': 0}} and
        status.get('log_errors') == {'stdout': None, 'stderr': None} and
        status.get('log_synced') == {'stdout': True, 'stderr': True} and
        status.get('log_truncated') == {'stdout': False, 'stderr': False}, 'ACTUAL_INIT_DURABLE_ZERO_EXIT')
    rows = files['actual-init/stdout.original.jsonl'].splitlines()
    require(len(rows) == 2, 'ACTUAL_TWO_OUTPUT_ROWS')
    value = json.loads(rows[1])
    source = {'path': ROOT + '/new_session_once.py', 'bytes': EXPECTED['new_session_once.py'][0],
              'sha256': EXPECTED['new_session_once.py'][1]}
    require(value.get('schema') == 'pocket4-original-new-session-owned-result-v1' and value.get('operation') == 'init' and
        value.get('ok') is True and value.get('errors') == [] and value.get('outcome_unknown') is False and
        value.get('flow') == FLOW and value.get('source') == source and value.get('joint_artifact') == ACTUAL_ARTIFACT and
        value.get('new_scope') == ACTUAL_SCOPE and value.get('native_launches') == 0 and
        value.get('old_close_outcome') == 'unknown_retained' and value.get('old_unknown_rewritten') is False and
        value.get('reconciliation_published') is False and value.get('all_owned_child_resources_retired_by_normal_pidfd_exit') is True,
        'ACTUAL_INIT_SCOPE_AND_JOINT_RESULT')
    base_path = HERE.parent / 'owned_cleanup_r1/cleanup_owned_task_once.py'
    require(sha(base_path.read_bytes()) == '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf', 'FROZEN_EXIT_VALIDATOR')
    spec = importlib.util.spec_from_file_location('unchanged_cleanup_definitions_only', base_path)
    base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
    base.require_owned_exit(value['child_lifecycle'], b'')
    child_raw = value['child_stdout_original'].encode('utf-8')
    require(len(child_raw) == value['child_stdout_bytes'] == 3651 and
        sha(child_raw) == value['child_stdout_sha256'] == 'b6febf47125254903c41e78c524d04e337012dc241b360342aecf9ba15f8348a2' and
        value.get('child_stderr_bytes') == 0 and value.get('child_stderr_original') == '', 'ACTUAL_ORIGINAL_CHILD_BYTES')
    child = json.loads(child_raw)
    require(child.get('schema') == 'pocket4-original-new-session-owned-child-v1' and child.get('ok') is True and
        child.get('errors') == [] and child.get('outcome_unknown') is False and child.get('operation') == 'init' and
        child.get('flow') == FLOW and child.get('source') == source and child.get('new_scope') == ACTUAL_SCOPE and
        child.get('old_original_files_preserved') == 177 and child.get('old_original_bytes_preserved') == 888207 and
        child.get('owned_QA_helper_runtime_revalidated') is False, 'ACTUAL_INIT_CHILD_AND_LIMITS')
    artifact_value = dict(value); del artifact_value['joint_artifact']
    reconstructed = canonical(artifact_value) + b'\n'
    require(len(reconstructed) == ACTUAL_ARTIFACT['bytes'] and sha(reconstructed) == ACTUAL_ARTIFACT['sha256'],
            'ACTUAL_DECLARED_ARTIFACT_EXACT_CANONICAL_RECONSTRUCTION')
    # This is explicitly reconstructed from actual stdout, not a new remote read.
    artifact_name = 'init-owned-lifetime.reconstructed-from-actual-stdout.json'
    once(HERE / 'actual-init' / artifact_name, reconstructed)
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', source['path'], '--launch-once',
                 '--source-sha256', source['sha256'], '--source-bytes', str(source['bytes']),
                 '--init-proof-sha256', ACTUAL_ARTIFACT['sha256'], '--init-proof-bytes', str(ACTUAL_ARTIFACT['bytes'])],
        'cwd': '/home/alex/work',
        'idempotency_key': 'pocket4-beike-owned-native-launch-r1-20261106-b6de2bd4f04bcd572a074ef984ba7dbe',
        'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10, 'timeout_seconds': 300}
    packet_raw = encode(packet); once(HERE / 'launch-process-request.review-only.json', packet_raw)
    proof = {'schema': 'pocket4-new-session-launch-local-sealing-proof-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'actual_init_job_id': status['job_id'], 'actual_init_terminal': {'bytes': len(files['actual-init/status-1.original.txt']),
            'sha256': sha(files['actual-init/status-1.original.txt'])},
        'actual_init_stdout': {'bytes': len(files['actual-init/stdout.original.jsonl']), 'sha256': sha(files['actual-init/stdout.original.jsonl'])},
        'source': source, 'joint_artifact': ACTUAL_ARTIFACT, 'new_scope': ACTUAL_SCOPE,
        'artifact_derivation': 'deterministic original canonical reconstruction from full actual stdout; not a fresh remote read',
        'candidate_request': {'path': 'launch-process-request.review-only.json', 'bytes': len(packet_raw), 'sha256': sha(packet_raw)},
        'source_or_original_evidence_modified': False, 'old_UNKNOWN_rewritten': False, 'remote_calls': 0,
        'Main_actions': 0, 'native_launches_by_sealer': 0, 'UI_actions': 0, 'production_ready': False,
        'launch_still_requires_fresh_original_Main_guard_and_no_preexisting_Beike_task': True}
    proof_raw = encode(proof); once(HERE / 'LAUNCH_SEALING_PROOF.json', proof_raw)
    print(json.dumps({'request': proof['candidate_request'], 'proof': {'bytes': len(proof_raw), 'sha256': sha(proof_raw)},
        'actual_init_artifact': ACTUAL_ARTIFACT, 'remote_calls': 0, 'Main_actions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
