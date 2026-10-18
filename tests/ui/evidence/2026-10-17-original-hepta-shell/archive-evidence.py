#!/usr/bin/env python3
"""Copy immutable R6 capture evidence into a fresh, credential-free review bundle."""
import argparse
import hashlib
import json
import stat
import subprocess
import time
from pathlib import Path

BASE = Path('/workspace/scratch/98f315e377b2')
TOOLS = BASE / 'next-tools'
DEST = TOOLS / 'r6-shell-capture-archive'
REPO = BASE / 'next-r6-ui'
PIN = 'f8c9419df6ddeb36ff8b522a50219981fb8d9345'
RUNS = [
    ('01', 'capture01-failed', 'next-r6-runtime-old', 'c50d7b9b688135a22ced2f7f3cbe21c3028d8e17'),
    ('02', 'capture02-r5-passed', 'next-r6-runtime-old-03', '28843c6632fe63db6b3fecb4d05888e90976fd16'),
    ('03', 'capture03-freshness-passed', 'next-r6-runtime-new-03', '145e94c364243789b88c23b1292f9d4d9ca9a0e9'),
]
PUBLISHED = {
    '28843c6632fe63db6b3fecb4d05888e90976fd16': '66dba7f40c2fa8fea2e7828ec2fd4db336bb681f',
    '145e94c364243789b88c23b1292f9d4d9ca9a0e9': '299794f90d4557cec4ee9a7fc92c397031fced4f',
    'aa3fc6feac114ee78910be604fa2a190be080ab0': 'cd92cf08c398bfbf8ea55381acc529d210a5bdc1',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def git(*args, cwd=REPO):
    return subprocess.check_output(['git', *args], cwd=cwd)


def object_id(spec):
    return git('rev-parse', spec).decode().strip()


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as output:
        output.write(data)


def authority_values(path):
    """Read only in memory to prove that no selected text/log contains the cookie."""
    data = path.read_bytes()
    offset = 2  # address family
    fields = []
    for _ in range(4):
        length = int.from_bytes(data[offset:offset + 2], 'big')
        offset += 2
        fields.append(data[offset:offset + length])
        offset += length
    assert offset == len(data) and fields[2] == b'MIT-MAGIC-COOKIE-1'
    cookie = fields[3]
    assert len(cookie) == 16
    return [cookie, cookie.hex().encode(), cookie.hex().upper().encode()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--independent-review', required=True, type=Path)
    args = parser.parse_args()
    assert args.independent_review.is_file()
    assert not DEST.exists(), 'archive path must be new'
    DEST.mkdir()
    manifest = []
    copy_checks = []
    all_cookies = []
    for run, _, _, _ in RUNS:
        all_cookies.extend(authority_values(TOOLS / f'r6-original-shell-{run}' / 'Xauthority'))

    def copy(source, relative):
        assert source.is_file() and not source.is_symlink()
        data = source.read_bytes()
        assert not data.startswith(b'\x7fELF'), 'ELF is not an archive input'
        assert all(cookie not in data for cookie in all_cookies), 'private display cookie appeared in selected evidence'
        destination = DEST / relative
        write(destination, data)
        assert destination.read_bytes() == source.read_bytes()
        manifest.append({'file': str(relative), 'source': str(source), 'bytes': len(data),
                         'sha256': digest(data), 'source_mode': oct(stat.S_IMODE(source.stat().st_mode))})
        return {'file': str(relative), 'bytes': len(data), 'sha256': digest(data)}

    source_bindings = []
    results = []
    for run, dirname, worktree, expected_head in RUNS:
        source = TOOLS / f'r6-original-shell-{run}'
        runtime = TOOLS / 'r6-original-runtime' / f'runtime-{run}'
        capture = read_json(source / 'capture-receipt.json')
        config = read_json(source / 'capture-config.json')
        owner = read_json(runtime / 'receipt.json')
        namespace = read_json(source / 'namespace.json')
        provenance = capture['source_provenance']
        assert provenance == config['provenance']
        assert provenance['harness_commit'] == expected_head
        assert object_id(f'{expected_head}^{{tree}}') == provenance['harness_tree']
        assert git('rev-parse', 'HEAD', cwd=BASE / worktree).decode().strip() == expected_head
        assert git('status', '--porcelain', cwd=BASE / worktree) == b''
        build_commit = provenance['production_ui_commit']
        assert object_id(f'{build_commit}^{{tree}}') == provenance['production_source_tree']
        for commit in (expected_head, build_commit):
            assert object_id(f'{commit}:ui') == provenance['unchanged_ui_subtree']
            for path, expected in provenance['unchanged_session_path_dependency'].items():
                assert object_id(f'{commit}:{path}') == expected
        snapshots = {'harness': 'capture-source.py', 'pixels': 'x11-capture-source.py', 'guard': 'child-guard-source.py'}
        for key, info in provenance['tracked_sources'].items():
            assert object_id(f'{expected_head}:{info["path"]}') == info['git_blob']
            raw = git('show', f'{expected_head}:{info["path"]}')
            assert digest(raw) == info['sha256']
            assert raw == (source / snapshots[key]).read_bytes()
        assert capture['original_hepta_pin'] == PIN
        for ui, owned in [('trill-session', 'session'), ('trill-ctl', 'ctl')]:
            assert provenance['binaries'][ui]['sha256'] == owner['binaries_before'][owned]['sha256']
        assert digest((source / 'package-stage.json').read_bytes()) == provenance['package_stage_sha256']
        assert capture['shell_processes_started'] == 1
        assert capture['synthetic_agentd_fixture_used'] is False and capture['renderer_memory_injected'] is False
        assert capture['objective_submitted'] is False and capture['model_called'] is False and capture['device_effect_tested'] is False
        assert capture['visual_review_completed_by_capture'] is False
        success = run != '01'
        assert capture['capture_passed'] is success
        assert namespace['returncode'] == (0 if success else 1)
        assert owner['status'] == ('passed' if success else 'failed')
        if success:
            assert capture['same_shell_pid_all_phases'] and capture['same_shell_window_all_phases']
            assert owner['private_state_cleanup_complete'] is True
            assert owner['binaries_before'] == owner['binaries_after']
            assert owner['helper_sha256'] == owner['helper_sha256_after']
            assert owner['steps'][-1]['child_guard_armed_after_completion'] is False
        assert len(capture['phases']) == (6 if success else 1)
        phases = []
        for phase in capture['phases']:
            held_path = source / phase['phase_file']
            held = read_json(held_path)
            n = phase['sequence']
            assert digest(held_path.read_bytes()) == phase['phase_sha256']
            assert held_path.read_bytes() == (runtime / 'phases' / f'phase-{n}.json').read_bytes()
            for side in ['before', 'after']:
                if side not in phase:
                    continue
                snapshot = phase[side]
                assert digest((source / snapshot['file']).read_bytes()) == snapshot['sha256']
                assert snapshot['peer_pid'] == held['session_pid']
                assert snapshot['session_instance'] == held['session_instance']
            png = phase['screenshot']
            assert digest((source / png['file']).read_bytes()) == png['sha256']
            ack_path = runtime / 'phases' / f'ack-{n}.json'
            if success:
                assert phase['shell_pid'] == capture['shell_pid']
                assert phase['shell_window_xid'] == capture['shell_window']['xid']
                assert read_json(ack_path) == held['ack']
                copy(ack_path, Path(dirname) / 'coordination' / ack_path.name)
            else:
                assert not ack_path.exists()
            phases.append({'sequence': n, 'phase': phase['phase'], 'session_pid': held['session_pid'],
                           'session_instance': held['session_instance'], 'worker_tid': held['worker_tid'],
                           'original': held['original'], 'png': png['file'], 'png_sha256': png['sha256'],
                           'acknowledged': success})
        for path in sorted(source.iterdir()):
            if path.name == 'Xauthority':
                continue
            if path.is_dir():
                assert not any(p.is_file() for p in path.rglob('*')), 'unexpected private files require explicit exclusion review'
                continue
            assert path.suffix in ['.json', '.log', '.py', '.png', '.conf'], path.name
            copy(path, Path(dirname) / path.name)
        owner_copy = copy(runtime / 'receipt.json', Path(dirname) / 'paired-runtime-receipt.json')
        source_bindings.append({'run': run, 'archive_directory': dirname, 'executed_worktree': str(BASE / worktree),
                                'provenance': provenance, 'paired_runtime_receipt': owner_copy,
                                'original_owner_binaries': owner['binaries_before'],
                                'local_git_tree_and_production_closure_verified': True,
                                'pre_execution_source_snapshots_match_tracked_blobs': True,
                                'root_reported_published_same_tree_object': PUBLISHED.get(expected_head)})
        results.append({'run': run, 'archive_directory': dirname, 'capture_passed': success,
                        'owner_status': owner['status'], 'error': capture.get('error'),
                        'shell_pid': capture['shell_pid'], 'shell_window': capture['shell_window'],
                        'same_shell_pid_all_phases': capture.get('same_shell_pid_all_phases', False),
                        'same_shell_window_all_phases': capture.get('same_shell_window_all_phases', False),
                        'namespace_returncode': namespace['returncode'], 'namespace_started_unix_ms': namespace['started_unix_ms'],
                        'namespace_finished_unix_ms': namespace['finished_unix_ms'],
                        'owned_shell_display_cleanup': capture['cleanup'],
                        'runtime_private_state_cleanup_complete': owner.get('private_state_cleanup_complete'),
                        'phases': phases})
        copy_checks.append({'run': run, 'raw_phase_and_png_and_snapshot_sha256_verified': True,
                            'phase_bytes_equal_original_owner_record': True,
                            'actual_peer_and_session_instance_equal_owner': True,
                            'acknowledgements_checked': 6 if success else 0,
                            'a10_manual_review_included': True})
        if success:
            old_identity = {(p['session_pid'], p['session_instance'], p['worker_tid']) for p in phases[:4]}
            new_identity = {(p['session_pid'], p['session_instance'], p['worker_tid']) for p in phases[4:]}
            assert len(old_identity) == 1 and len(new_identity) == 1 and old_identity != new_identity

    oracle = TOOLS / 'r6-shell-oracle-fix-01'
    for path in sorted(oracle.iterdir()):
        assert path.is_file() and path.suffix in ['.json', '.log', '.py', '.md']
        copy(path, Path('oracle-fix') / path.name)
    tests = read_json(oracle / 'final-tests-receipt.json')
    for path, sha in tests['tested_source_sha256'].items():
        assert digest(git('show', f'{tests["source_commit"]}:{path}')) == sha
        assert object_id(f'{tests["source_commit"]}:{path}') == tests['tested_git_objects'][path]
    candidate_sha = digest(git('show', '68c9aa3df9a45906a44d20bd7f1a0bc684a19f02:tests/ui/probe-original-hepta-shell.py'))
    assert candidate_sha == read_json(oracle / 'raw-frame-replay.json')['oracles']['candidate_fix']['source_sha256']
    copy(TOOLS / 'r6-review' / 'shell-01-starting-independent-review.json', Path('reviews') / 'capture01-independent-review.json')
    copy(TOOLS / 'r6-review' / 'root-shell-visual-review.json', Path('reviews') / 'root-shell-visual-review.json')
    copy(args.independent_review, Path('reviews') / 'independent-original-shell-review.json')
    for name in ['shell-02-independent-review.json', 'shell-03-independent-review.json', 'verify-continuous-captures.py']:
        copy(TOOLS / 'r6-review' / name, Path('reviews') / name)
    copy(Path(__file__).resolve(), Path('archive-evidence.py'))
    copy(TOOLS / 'r6-shell-capture-README.md', Path('README.md'))
    binding = {'original_hepta_pin': PIN, 'runs': source_bindings,
               'oracle_final_commit': tests['source_commit'], 'oracle_final_tree': tests['source_tree'],
               'oracle_candidate_raw_replay_commit': '68c9aa3df9a45906a44d20bd7f1a0bc684a19f02',
               'oracle_candidate_raw_replay_sha256': candidate_sha,
               'published_mapping': {'provided_by': 'root integration agent', 'mapping': PUBLISHED,
                                     'meaning': 'Published objects are reported by root to have identical trees; original execution commit IDs remain unchanged in every raw receipt.',
                                     'remote_objects_independently_fetched_by_a10': False}}
    report = {'status': 'two_six_phase_captures_passed_with_initial_failed_attempt_preserved',
              'recorded_unix_ms': int(time.time() * 1000),
              'recommended_repository_path': 'tests/ui/evidence/2026-10-17-original-hepta-shell',
              'raw_png_count': 13, 'successful_raw_png_count': 12,
              'human_review': {'a10_implementation_agent': '13 images individually inspected',
                               'root_integrator': '13 images individually inspected; separate record',
                               'independent_reviewer': '13 images individually inspected; separate records'},
              'runs': results, 'artifact_binding_checks': copy_checks,
              'source_and_elf_binding': 'source-bindings.json',
              'oracle_tests': {'receipt': 'oracle-fix/final-tests-receipt.json', 'exit_code': tests['exit_code'],
                               'count': 8, 'parent_death_scope': 'actual exec child leader dies by SIGKILL after capture parent dies; no arbitrary-descendant claim'},
              'sampling_boundary': 'PNG pixels are manually read; before/after Session IPC binds a legal projection interval, not a guarantee that the painted sampled_unix_ms equals the final after snapshot.',
              'stale_timing': 'Old R5 stop retained Running generation 6; new GREEN03 stop retained Draining generation 7. Both are real original observations; the difference is not attributed to the UI fix.',
              'marker_boundary': 'A one-shot first-page layout marker is recorded once per Shell. Six PNGs and separate manual review qualify subsequent stages; ACKs are coordination only.',
              'freshness_bug_boundary': 'Delayed queued-response regression and corrected production compilation are in sibling 2026-10-17-observation-freshness evidence. These six-phase runs do not simulate a paused UI queue.',
              'exclusions': ['Xauthority cookies', 'ELFs', 'Cargo targets or caches', 'font bytes', 'private original Agentd state', 'objective/model/device effects'],
              'private_cookie_scan': 'No selected evidence contains any of the three disposable display cookies in raw or hexadecimal representation.',
              'qualification': 'Linux x86_64 native Rust Shell read-only original Hepta projection through real Session IPC and private X11 framebuffer; no physical display, mobile, target kernel, model task, objective ingress, device action, or keyboard input qualification.'}
    write(DEST / 'source-bindings.json', json_bytes(binding))
    write(DEST / 'report.json', json_bytes(report))
    write(DEST / 'copy-manifest.json', json_bytes({'copied_files': manifest, 'source_files_modified': False,
                                                 'private_cookie_scan_passed': True, 'elf_magic_scan_passed': True}))
    files = sorted(path for path in DEST.rglob('*') if path.is_file())
    write(DEST / 'SHA256SUMS', ''.join(f'{digest(path.read_bytes())}  {path.relative_to(DEST)}\n' for path in files).encode())
    for line in (DEST / 'SHA256SUMS').read_text().splitlines():
        expected, relative = line.split('  ', 1)
        assert digest((DEST / relative).read_bytes()) == expected
    all_files = sorted(path for path in DEST.rglob('*') if path.is_file())
    assert sum(path.suffix == '.png' for path in all_files) == 13
    summary = {'archive': str(DEST), 'files': len(all_files), 'bytes': sum(p.stat().st_size for p in all_files),
               'report_sha256': digest((DEST / 'report.json').read_bytes()),
               'sha256sums_sha256': digest((DEST / 'SHA256SUMS').read_bytes()),
               'source_bindings_sha256': digest((DEST / 'source-bindings.json').read_bytes()),
               'copied_sources_unchanged': True, 'checksum_verification': 'passed',
               'raw_png_count': 13}
    write(TOOLS / 'r6-shell-capture-archive-receipt.json', json_bytes(summary))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
