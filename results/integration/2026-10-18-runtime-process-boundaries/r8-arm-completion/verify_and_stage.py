#!/usr/bin/env python3
"""Read-only verification of the completed R8 ARM evidence; never runs a gate."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

BASE = Path('/workspace/scratch/98f315e377b2/recovery-r7')
HERE = BASE / 'ci-r8-arm-39106645234'
STAGE = BASE / 'ci-r8-arm-39106645234-stage'
HEAD = '05a7cd23f0a4b90b154ef0c45be89093b129f767'
UPSTREAM = 'f8c9419df6ddeb36ff8b522a50219981fb8d9345'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(BASE / 'repo'), *args])


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    STAGE.mkdir(mode=0o700, exist_ok=False)
    inputs = json.loads((HERE / 'connector-inputs.json').read_text())
    run = json.loads(inputs['run_api_utf8'])
    jobs = json.loads(inputs['jobs_api_utf8'])
    assert run['id'] == 39106645234 and run['head_sha'] == HEAD
    assert run['conclusion'] == 'success' and run['status'] == 'completed' and run['run_attempt'] == 1
    assert jobs['total_count'] == 1 and len(jobs['jobs']) == 1
    job = jobs['jobs'][0]
    assert job['id'] == 117613820420 and job['head_sha'] == HEAD and job['conclusion'] == 'success'
    assert all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in job['steps'])
    artifact = next(x for x in inputs['artifacts_wrapper']['artifacts'] if x['id'] == 12129611289)
    zip_bytes = (HERE / 'evidence.zip').read_bytes()
    assert len(zip_bytes) == artifact['size_in_bytes'] == 1710211
    assert 'sha256:' + digest(zip_bytes) == artifact['digest']
    log = inputs['decoded_job_log_utf8']
    # Drop only GitHub's timestamp prefix for comparison, while archiving the
    # connector-decoded log unchanged, including its initial UTF-8 BOM.
    untimed = '\n'.join(re.sub(r'^\ufeff?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ', '', line)
                        for line in log.split('\n'))
    matched = []

    def verify_source(rel, expected):
        raw = git('show', HEAD + ':' + rel)
        assert digest(raw) == expected, rel
        matched.append({'path': rel, 'sha256': expected, 'bytes': len(raw),
                        'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()})

    with zipfile.ZipFile(HERE / 'evidence.zip') as archive:
        assert archive.testzip() is None
        readonly_raw = archive.read('report.json')
        objective_raw = archive.read('objective-work/report.json')
        readonly = json.loads(readonly_raw)
        objective = json.loads(objective_raw)
        assert readonly_raw.decode() in untimed and objective_raw.decode() in untimed
        assert readonly_raw == archive.read('logs/gate.log')
        assert objective_raw == archive.read('logs/objective-gate.log')
        assert readonly['status'] == readonly['live_agentd_acceptance'] == readonly['persistent_session_acceptance'] == 'passed'
        assert all(x['status'] == 'passed' for x in readonly['steps'])
        assert objective['status'] == 'passed' and objective['runtime_executed'] is True
        assert objective['session_projection_requested'] is True
        for report in (readonly, objective):
            assert report['upstream']['commit'] == UPSTREAM and report['upstream']['clean_checkout'] is True
            assert digest(archive.read('locks/hepta-original-Cargo.lock')) == report['upstream']['cargo_lock_sha256']
        for path, expected in readonly['observer_source_sha256'].items():
            verify_source(path, expected)
        for path, expected in objective['source_sha256'].items():
            verify_source('tests/integration/hepta/' + path, expected)
        verify_source('tests/integration/hepta/original_agentd_probe.rs', readonly['probe_source_sha256'])
        verify_source('tests/integration/hepta/original_session_probe.rs', readonly['session_probe_source_sha256'])
        for line in archive.read('identity/desktop-inputs.sha256').decode().splitlines():
            expected, path = line.split(maxsplit=1)
            verify_source(path, expected)
        assert archive.read('identity/desktop-before.txt') == git('rev-parse', HEAD, HEAD + '^{tree}')
        assert archive.read('identity/consumer-source-trees.txt') == git('rev-parse', HEAD + ':ui', HEAD + ':services/hepta-os')
        before_upstream = archive.read('identity/hepta-before.txt').decode()
        final = json.loads(archive.read('identity/final-checkouts.json'))
        for name in ('desktop', 'hepta'):
            checkout = final['checkouts'][name]
            assert checkout['identity']['exit_code'] == checkout['status']['exit_code'] == 0
            assert checkout['status']['stdout'] == checkout['status']['stderr'] == ''
        assert final['checkouts']['desktop']['identity']['stdout'] == archive.read('identity/desktop-before.txt').decode()
        assert final['checkouts']['hepta']['identity']['stdout'] == before_upstream
        assert final['checkouts']['hepta']['cargo_lock_sha256'] == readonly['upstream']['cargo_lock_sha256']
        assert final['checkouts']['desktop']['cargo_lock_sha256'] == digest(archive.read('locks/observer-Cargo.lock'))
        assert archive.read('gate-exit-code.txt') == archive.read('objective-exit-code.txt') == b'0\n'

        for report, name in ((readonly, 'work/original_agentd_process_probe.log'), (objective, 'objective-work/runtime.log')):
            raw_records = [json.loads(line) for line in archive.read(name).decode().splitlines() if line.startswith('{')]
            assert raw_records == report['runtime_records']
        ro_accept = next(r for r in readonly['runtime_records'] if r.get('event') == 'acceptance_pass')
        session_accept = next(r for r in readonly['runtime_records'] if r.get('event') == 'session_acceptance_pass')
        obj_accept = next(r for r in objective['runtime_records'] if r.get('event') == 'acceptance_pass')
        assert len(ro_accept['checks']) == len(set(ro_accept['checks'])) == 8
        assert len(session_accept['checks']) == len(set(session_accept['checks'])) == 8
        assert len(obj_accept['checks']) == len(set(obj_accept['checks'])) == 10
        obj_checks = [r['check'] for r in objective['runtime_records'] if r.get('event') == 'objective_check']
        assert obj_checks == obj_accept['checks']
        submissions = [r for r in objective['runtime_records'] if r.get('event') == 'submission_observed']
        assert len(submissions) == 7
        assert [r['exit_code'] for r in submissions] == [0, 0, 0, 12, 10, 12, 12]
        ro_phases = [r for r in readonly['runtime_records'] if r.get('event') == 'session_phase_observed']
        obj_phases = [r for r in objective['runtime_records'] if r.get('event') == 'objective_session_phase_observed']
        assert [r['phase'] for r in ro_phases] == ['starting', 'running', 'draining', 'old_spawn_stale', 'recovered_running', 'stopped_stale']
        assert [r['phase'] for r in obj_phases] == ['compiled_run_projected', 'old_endpoint_run_stale', 'replacement_run_projection_missing']
        def phase_identity(p):
            return (p['session_instance'], p['session_pid'], p['worker_tid'])
        assert len({phase_identity(p) for p in ro_phases[:4]}) == 1
        assert len({phase_identity(p) for p in ro_phases[4:]}) == 1
        assert phase_identity(ro_phases[0]) != phase_identity(ro_phases[4])
        assert phase_identity(obj_phases[0]) == phase_identity(obj_phases[1]) != phase_identity(obj_phases[2])
        for report, event in ((readonly, 'session_stopped'), (objective, 'objective_session_stopped')):
            stops = [r for r in report['runtime_records'] if r.get('event') == event]
            assert len(stops) == 2 and all(r['signal'] == 9 and r['exit_code'] is None for r in stops)
        for phase in ro_phases + obj_phases:
            assert phase['snapshot']['tasks'] == []
            assert phase['capture_ack_is_coordination_only'] is True
        assert session_accept['shell_capture_qualified_by_this_record'] is False
        assert obj_accept['isolated_test_issuer'] is True
        for key in ('production_issuer', 'model_turn', 'operations_dispatch', 'canonical_intelligence', 'device_effect', 'historical_run_resumed'):
            assert obj_accept[key] is False
        first_run = obj_phases[0]['snapshot']['hepta']['run']
        stale_run = obj_phases[1]['snapshot']['hepta']['run']
        missing_run = obj_phases[2]['snapshot']['hepta']['run']
        assert first_run['connection'] == 'observed' and first_run['last_observation']['terminal_observed'] is False
        assert stale_run['connection'] == 'stale' and stale_run['observation_gap'] is True
        assert stale_run['last_observation'] == first_run['last_observation']
        assert stale_run['last_attempt_unix_ms'] == first_run['last_attempt_unix_ms']
        assert missing_run['connection'] == 'projection_missing' and missing_run['last_observation'] is None
        shared_binaries = {}
        for name in ('agentd', 'observer', 'session', 'ctl'):
            expected = readonly['session_input_binaries'][name]['sha256'] if name in ('session', 'ctl') else readonly['binary_sha256'][name]
            assert objective['binaries'][name]['sha256'] == expected
            shared_binaries[name] = expected
        prerequisite_counts = [int(n) for n in re.findall(r'^Ran (\d+) tests', archive.read('logs/gate-prerequisites.log').decode(), re.M)]
        objective_counts = [int(n) for n in re.findall(r'^Ran (\d+) tests', archive.read('logs/objective-receipt-contracts.log').decode(), re.M)]
        assert prerequisite_counts == [5, 6, 6] and objective_counts == [12]
        selected = [name for name in archive.namelist() if name.startswith('identity/')]
        selected += ['report.json', 'objective-work/report.json', 'gate-exit-code.txt', 'objective-exit-code.txt',
                     'logs/gate-prerequisites.log', 'logs/objective-receipt-contracts.log', 'logs/native-setup.log',
                     'logs/session-build.log', 'logs/submitter-build.log', 'logs/upstream-checkout.log',
                     'work/original_agentd_build.log', 'work/original_library_probe_build.log',
                     'work/original_agentd_process_probe.log', 'objective-work/probe-build.log', 'objective-work/runtime.log',
                     'objective-work/runtime-evidence/journal-inspection.json']
        members = []
        for name in selected:
            raw = archive.read(name)
            destination = STAGE / 'artifact' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            assert destination.read_bytes() == raw
            members.append({'path': name, 'bytes': len(raw), 'sha256': digest(raw)})

    (STAGE / 'api').mkdir()
    (STAGE / 'api/run.json').write_bytes(inputs['run_api_utf8'].encode())
    (STAGE / 'api/jobs.json').write_bytes(inputs['jobs_api_utf8'].encode())
    write_json(STAGE / 'api/artifacts-connector.json', inputs['artifacts_wrapper'])
    write_json(STAGE / 'api/observed-at.json', inputs['observed_at'])
    (STAGE / 'job-117613820420.log').write_bytes(log.encode())
    workflow = git('show', HEAD + ':.github/workflows/hepta-original-agentd.yml')
    assert workflow == inputs['source_workflow_utf8'].encode()
    (STAGE / 'hepta-original-agentd.yml').write_bytes(workflow)
    shutil.copyfile(HERE / 'download-verification.json', STAGE / 'download-verification.json')
    shutil.copyfile(__file__, STAGE / 'verify_and_stage.py')
    write_json(STAGE / 'source-verification.json', {
        'head': HEAD, 'tree': run['head_commit']['tree_id'], 'upstream': readonly['upstream'],
        'all_recorded_source_hashes_match_fixed_git_objects': True, 'source_checks': matched,
        'desktop_and_upstream_final_checkout_identities_unchanged_and_clean': True,
        'downloaded_elf_archives': False, 'independently_rehashed_elf_bytes': False,
        'ci_packaging_steps_successful': True, 'shared_runtime_binary_hashes_equal_between_reports': shared_binaries,
        'note': 'ELF headers and bytes were checked by the fixed workflow successful package steps. This review reads their source and raw reports, and does not download or independently re-hash either large ELF archive.'})
    write_json(STAGE / 'review.json', {
        'schema': 'r8-original-arm-completion-review-v1',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
        'reviewer': '/root/r6_review_ci', 'run_id': run['id'], 'job_id': job['id'], 'run_attempt': 1,
        'head': HEAD, 'tree': run['head_commit']['tree_id'], 'runner_labels': job['labels'],
        'job_started_at': job['started_at'], 'job_completed_at': job['completed_at'],
        'readonly_original_checks': ro_accept['checks'], 'readonly_session_checks': session_accept['checks'],
        'objective_core_checks': obj_accept['checks'], 'objective_explicit_submissions': len(submissions),
        'objective_submission_exit_codes': [r['exit_code'] for r in submissions],
        'readonly_session_phases': [{'phase': p['phase'], 'identity': phase_identity(p)} for p in ro_phases],
        'objective_session_phases': [{'phase': p['phase'], 'identity': phase_identity(p)} for p in obj_phases],
        'prerequisite_python_counts': prerequisite_counts, 'objective_receipt_python_tests': objective_counts[0],
        'report_json_equal_actual_gate_stdout': True, 'reports_equal_json_records_in_actual_runtime_logs': True,
        'full_reports_present_in_raw_github_job_log': True, 'selected_original_artifact_members': members,
        'new_execution_by_reviewer': False, 'qualification_bound_to_r9': False,
        'scope': 'Native AArch64 original Agentd/read-only Session and separately isolated original ObjectiveStart with known-run Session. Seven means explicit submissions, not seven Session tests. No Shell pixels, production issuer, model turn, operations dispatch, device effect, canonical intelligence or resumed historical run.'})
    print(json.dumps({'stage': str(STAGE), 'status': 'passed', 'source_hash_checks': len(matched),
                      'artifact_members_retained': len(members), 'readonly_checks': [8, 8],
                      'objective_core_checks': 10, 'objective_submissions': 7, 'objective_session_phases': 3}))


if __name__ == '__main__':
    main()
