#!/usr/bin/python3
"""Verify this immutable packet and rerun its actual 41 / 440 Git controls."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def sha(body):
    return hashlib.sha256(body).hexdigest()


def verify_files():
    expected = {}
    for line in (HERE / 'FILES.sha256').read_text().splitlines():
        digest, relative = line.split('  ', 1)
        path = Path(relative)
        assert len(digest) == 64 and not path.is_absolute() and '..' not in path.parts
        assert relative not in expected and (HERE / path).is_file() and not (HERE / path).is_symlink()
        assert sha((HERE / path).read_bytes()) == digest, relative
        expected[relative] = digest
    actual = {str(path.relative_to(HERE)) for path in HERE.rglob('*') if path.is_file()}
    assert actual == set(expected) | {'FILES.sha256'}, 'exact packet file roster'
    return expected


def read(path):
    return json.loads(path.read_bytes())


def verify_report(report, expected):
    assert report['schema'] == 'p4-text-auto-and-executable-crlf-real-git-controls-v1'
    assert report['passed'] is True and report['tests_run'] == len(report['cases']) == 41
    assert all(row['passed'] is True for row in report['cases'])
    assert report['actual_fixture_files_replayed'] == len(report['actual_fixture_replays']) == 440
    assert report['baseline_sha256'] == expected['baseline/vendor_source_bookends_r19_9907.py']
    assert report['successor_sha256'] == expected['vendor_source_bookends_text_auto_9907.py']
    assert report['test_source_sha256'] == expected['test_text_auto.py']
    assert report['actual_fixture_sha256'] == expected['fixtures/actual-conversions.json.gz']
    assert report['unchanged_previous_control_cases'] == 26
    for name in ('all_fixture_children_reaped', 'all_fixture_process_groups_gone',
                 'original_pidfds_held_until_reaped', 'temporary_repositories_removed'):
        assert report[name] is True, name
    assert report['operational_source_mutations'] == report['Android_actions'] == 0
    assert report['source_restore_executed'] is report['runtime_qualified'] is report['production_ready'] is False
    for row in report['fixture_git_commands']:
        assert row['exit_code'] == 0 and row['actual_child_reaped'] is True
        assert row['process_group_gone'] is row['original_pidfd_held_until_reaped'] is True
    for row in report['actual_fixture_replays']:
        assert row['Git_checkout_whole_bytes_equal_actual_working_body'] is True
        assert row['successor_accepted_complete_original_blob_equivalence'] is True
        assert all(command['exit_code'] == 0 and command['actual_child_reaped'] is True
                   for command in row['actual_bookend_commands'])


def verify_original_target(expected):
    raw = gzip.decompress((HERE / 'evidence/TARGET-CONTROLS.json.gz').read_bytes())
    controls = json.loads(raw)
    verify_report(controls, expected)
    execution = read(HERE / 'evidence/TARGET-EXECUTION.json')
    client = read(HERE / 'evidence/TARGET-CLIENT.json')
    retired = read(HERE / 'evidence/TARGET-RETIREMENT.json')
    assert len(raw) == execution['controls']['bytes'] and sha(raw) == execution['controls']['sha256']
    assert controls['git_version'] == 'git version 2.53.0' and controls['uid'] == 1000
    assert controls['git'] == execution['git']
    assert controls['git']['sha256'] == 'ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362'
    assert len(controls['fixture_git_commands']) == 1084
    assert execution['passed'] is execution['actual_child_reaped'] is True
    assert execution['child_exit_code'] == 0 and execution['child_process_group_gone'] is True
    assert execution['all_input_bytes_and_F9_preserved'] is execution['temporary_fixture_root_empty'] is True
    for field in ('stdout', 'stderr'):
        body = (HERE / ('evidence/TARGET-' + field.upper() + '.log')).read_bytes()
        assert len(body) == execution[field]['bytes'] and sha(body) == execution[field]['sha256']
    state = client['status']
    body = (HERE / 'evidence/TARGET-CLIENT.stdout').read_bytes()
    assert state['state'] == 'exited' and state['exit_code'] == 0
    assert state['output_complete'] is True and state['capture_error'] is None
    assert state['bytes_seen'] == state['bytes_stored'] == client['stdout_bytes'] == len(body)
    assert sha(body) == client['stdout_sha256'] == retired['original_client_stdout']['sha256']
    assert retired['read_only'] is True and retired['errors'] == []
    assert retired['all_original_input_and_result_bodies_and_F9_unchanged'] is True
    for target in retired['targets']:
        assert all(row['exists'] is False for row in target['pids'])
        assert target['absent_cgroup_paths'] == [
            '/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/' + target['unit'],
            '/sys/fs/cgroup/system.slice/' + target['unit']]
        assert target['unit_observation']['properties'] == {
            'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
            'MainPID': '0', 'ControlGroup': '', 'InvocationID': ''}
    return {'original_target_git': controls['git_version'], 'controls': 41, 'replayed_files': 440,
            'fixture_commands': 1084, 'target_test_client_exit_code': 0, 'full_output_retained': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    expected = verify_files()
    original = verify_original_target(expected)
    if args.output_dir is None:
        output = Path(tempfile.mkdtemp(prefix='p4-text-auto-ci-'))
    else:
        output = args.output_dir.resolve()
        assert HERE != output and HERE not in output.parents, 'CI results must remain outside the packet'
        output.mkdir(parents=True, exist_ok=False)
    tmp = output / 'tmp'
    tmp.mkdir()
    result_path = output / 'CONTROLS.json'
    environment = dict(os.environ, TMPDIR=str(tmp))
    with (output / 'stdout.log').open('xb') as stdout, (output / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen([sys.executable, '-I', '-B', str(HERE / 'test_text_auto.py'),
                                  '--result', str(result_path)], env=environment,
                                 stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
        pidfd = os.pidfd_open(child.pid, 0)
        try:
            try:
                returncode = child.wait(timeout=200)
            except BaseException:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=10)
                raise
            assert returncode == 0, 'see CI stderr.log and CONTROLS.json'
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError('test runner process group remains')
        finally:
            os.close(pidfd)
    current = read(result_path)
    verify_report(current, expected)
    assert list(tmp.iterdir()) == [], 'owned temporary fixtures must be removed'
    assert expected == verify_files(), 'packet bytes unchanged through real Git tests'
    summary = {'schema': 'p4-text-auto-public-ci-result-v1', 'passed': True,
               'original_target_evidence': original, 'current_git': current['git_version'],
               'current_tests': 41, 'current_replays': 440,
               'current_fixture_commands': len(current['fixture_git_commands']),
               'report_bytes': result_path.stat().st_size, 'report_sha256': sha(result_path.read_bytes()),
               'packet_files': len(expected), 'source_restore_executed': False,
               'runtime_qualified': False, 'production_ready': False}
    with (output / 'SUMMARY.json').open('x') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({**summary, 'output_dir': str(output)}, sort_keys=True))


if __name__ == '__main__':
    main()
