#!/usr/bin/env python3
"""Read only completed exact-head GitHub API/log evidence; run no project code."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parent / 'repo'
STAGE = HERE.parent / 'ci-r9-5060-a10-stage'
HEAD = '5060ac6976b56b32647c728991e489cdee1cce9d'
TREE = 'ae588699126910065c16b77d83f3ef20b53509f2'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1')
    return subprocess.check_output(['git', '-C', str(REPO), *args], env=env)


def write(rel, raw):
    path = STAGE / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    assert path.read_bytes() == raw


def output(rel, obj):
    write(rel, (json.dumps(obj, indent=2) + '\n').encode())


def main():
    inputs = json.loads((HERE / 'a10-connector-inputs.json').read_text())
    codeql = json.loads((HERE / 'codeql-connector-inputs.json').read_text())
    src = inputs['inputs']
    def parsed(key):
        return json.loads(src[key]['content'])
    run = parsed('poll01_a10_run')
    jobs = parsed('poll01_a10_jobs')
    checks = parsed('poll02_checks')
    artifact = src['poll01_a10_artifacts']['artifacts'][0]
    native = src['poll01_a10_native_log']['content']
    guard = src['poll01_a10_guard_log']['content']
    assert git('rev-parse', HEAD + '^{tree}').decode().strip() == TREE
    assert run['id'] == 39182491046 and run['head_sha'] == HEAD
    assert run['head_commit']['tree_id'] == TREE and run['run_attempt'] == 1
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    assert jobs['total_count'] == len(jobs['jobs']) == 2
    assert {j['id'] for j in jobs['jobs']} == {117838018520, 117838093786}
    for job in jobs['jobs']:
        assert job['head_sha'] == HEAD and job['status'] == 'completed' and job['conclusion'] == 'success'
        assert all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in job['steps'])
    for raw in (native, guard):
        assert HEAD in raw and 'Checking out the ref' in raw
    assert 'A10 Rust source exists; host build and Wayland tests are required.' in guard
    assert artifact['id'] == 12157021582 and artifact['size_in_bytes'] == 17613832
    assert artifact['workflow_run']['head_sha'] == HEAD
    assert artifact['digest'] == 'sha256:9f21774fff8c40e6ab852f1f345a3b4c64f981a548a64b924aea2320d957fbc3'
    assert artifact['digest'].split(':')[1] in native
    lock = git('show', HEAD + ':ui/Cargo.lock')
    assert sha(lock) == 'e484809d742a264a296046b0d272e843d167b02b634232e793ef702757cc70e1'
    assert sha(lock) + '  ui/Cargo.lock' in native
    assert git('cat-file', '-s', HEAD + ':README.md') == b'0\n'

    # Decode neither terminal escapes nor timestamps in the archived original.
    # A separate list associates every Cargo summary with its preceding binary.
    summaries = []
    component = None
    for number, line in enumerate(native.splitlines(), 1):
        body = re.sub(r'^\ufeff?\d{4}-\d{2}-\d{2}T\S+Z ', '', line)
        if re.search(r'Running (unittests|tests/)', body) or 'Doc-tests ' in body:
            component = body.strip()
        result = re.search(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;', body)
        if result:
            assert component is not None and int(result[2]) == 0
            summaries.append({'raw_job_log_line': number, 'component': component,
                              'passed': int(result[1]), 'failed': int(result[2]), 'ignored': int(result[3])})
    expected = [11, 2, 30, 2, 4, 1, 63, 24, 0,
                1, 0, 0, 0, 16, 0,
                2, 0, 0, 8, 15, 16, 2,
                39, 0, 0, 8, 0]
    assert [r['passed'] for r in summaries] == expected
    assert [i for i, r in enumerate(summaries) if r['ignored']] == [0, 6]
    groups = [
        ('ui_workspace', 0, 9, 137, 2, 'cargo test --manifest-path ui/Cargo.toml --workspace --locked'),
        ('hepta_default', 9, 15, 17, 0, 'cargo test --manifest-path services/hepta-os/Cargo.toml --locked'),
        ('hepta_objective_feature', 15, 22, 43, 0, 'cargo test --manifest-path services/hepta-os/Cargo.toml --locked --offline --features objective-transport'),
        ('support_ui', 22, 24, 39, 0, 'cargo test --manifest-path support/ui/Cargo.toml --locked'),
        ('tests_ui_contracts', 24, 27, 8, 0, 'cargo test --manifest-path tests/ui/Cargo.toml --locked'),
    ]
    counts = []
    host_source = git('show', HEAD + ':tests/ui/check-host.sh').decode()
    for name, start, end, passed, ignored, command in groups:
        assert command in host_source
        records = summaries[start:end]
        assert sum(r['passed'] for r in records) == passed
        assert sum(r['ignored'] for r in records) == ignored
        counts.append({'scope': name, 'actual_command': command, 'passed': passed,
                       'ignored': ignored, 'summaries': records})
    kill_tests = ['killed_before_stdin_eof_has_no_receipt_or_connection',
                  'killed_after_complete_request_has_no_receipt_and_no_retry']
    for name in kill_tests:
        assert 'test ' + name + ' ... ok' in native
    py = [int(n) for n in re.findall(r'\bRan (\d+) tests', native)]
    assert py == [6, 8, 10]
    positive_markers = [
        'A10 host flock: PASS',
        'A10 scoped smoke cleanup: PASS',
        'A10 actual zombie process liveness guard: PASS',
        'PASS: Session/facade/UDS fixture observation and stale-state retention',
        'A10 REAL RUNTIME OWNERSHIP PASS',
        'A10 SO_PEERCRED live BIDIRECTIONAL refusal PASS',
        'A10 REAL forged Session refusal PASS',
        'A10 STRICT REQUEST IPC PASS: 8 forged frames rejected',
        'A10 REAL Linux ELF replay PASSED',
        'A10 host Rust checks passed',
        'Wayland host Shell first layout, restarted Shell layout, three app layouts and observed cancellation: PASS',
        'PASS: actual Rust Hepta-page egui layout consumed a fresh Session projection from the scripted UDS fixture',
        'Compositor crash/restart PASS: same Session, socket epoch change, new Wayland client first layout, confirmed cancellation',
        'A10 Weston headless client/session and crash/restart smoke: PASSED on this Linux runner',
    ]
    assert all(marker in native for marker in positive_markers)
    assert 'A10 X11 mapping NOT VERIFIED: host Xvfb/x11-utils/xauth unavailable' in native
    assert 'NOT VERIFIED: pre-crash client window continuity, CJK candidates, GPU reset or target OS' in native
    for j in jobs['jobs']:
        if j['id'] == 117838093786:
            assert next(s for s in j['steps'] if 'Clippy' in s['name'])['conclusion'] == 'success'
            assert next(s for s in j['steps'] if 'dependency lock' in s['name'])['conclusion'] == 'success'
    qrun, qjobs = json.loads(codeql['run_utf8']), json.loads(codeql['jobs_utf8'])
    assert qrun['id'] == 39182489120 and qrun['head_sha'] == HEAD
    assert qrun['path'] == 'dynamic/github-code-scanning/codeql' and qrun['conclusion'] == 'success'
    assert qjobs['total_count'] == 1 and qjobs['jobs'][0]['id'] == 117838016177
    assert qjobs['jobs'][0]['head_sha'] == HEAD and qjobs['jobs'][0]['conclusion'] == 'success'
    assert checks['total_count'] == 5
    for c in checks['check_runs']:
        assert c['head_sha'] == HEAD
        if c['id'] in (117838143069, 117838016177):
            assert c['status'] == 'completed' and c['conclusion'] == 'success'
    assert parsed('poll02_arm_run')['conclusion'] is None

    STAGE.mkdir(mode=0o700, exist_ok=False)
    for key, value in src.items():
        if key.endswith('_log'):
            continue
        if 'content' in value:
            write('api/' + key + '.json', value['content'].encode())
        else:
            output('api/' + key + '-connector.json', value)
    output('api/observed-at.json', inputs['observations'])
    write('api/codeql-run.json', codeql['run_utf8'].encode())
    write('api/codeql-jobs.json', codeql['jobs_utf8'].encode())
    output('api/codeql-recorded-at.json', codeql['recorded_at'])
    write('job-117838093786-native.log', native.encode())
    write('job-117838018520-source-guard.log', guard.encode())
    paths = ['.github/workflows/a10-host.yml', 'tests/ui/check-host.sh',
             'tests/ui/headless-weston.sh', 'tests/ui/smoke-wayland.sh',
             'tests/ui/compositor-restart.sh', 'tests/ui/probe-hepta-session.py',
             'tests/ui/replay-packaged-host.sh', 'support/ui/package-host-binaries.sh',
             'services/hepta-os/tests/objective_cli.rs', 'services/hepta-os/Cargo.toml',
             'ui/core/src/hepta.rs', 'ui/core/src/observation.rs',
             'ui/session/src/hepta.rs', 'ui/shell/src/hepta_panel.rs']
    sources = []
    for path in paths:
        raw = git('show', HEAD + ':' + path)
        sources.append({'path': path, 'bytes': len(raw), 'sha256': sha(raw),
                        'git_blob': git('rev-parse', HEAD + ':' + path).decode().strip()})
        # Gates establish the meaning of the observed successful markers.
        # Larger production files remain fixed-Git references plus byte hashes.
        if path.endswith(('.sh', '.yml')) or path == 'services/hepta-os/Cargo.toml':
            write('source/' + path, raw)
    subtrees = {p: git('rev-parse', HEAD + ':' + p).decode().strip()
                for p in ('ui', 'services/hepta-os', 'support/ui', 'tests/ui', 'tests/integration/hepta', 'libs/os-abi')}
    output('source-verification.json', {
        'head': HEAD, 'tree': TREE, 'subtrees': subtrees, 'source_inputs': sources,
        'checkout_head_in_both_job_logs_and_run_api': True,
        'ui_lock_sha256': sha(lock), 'ui_lock_hash_present_in_native_log': True,
        'root_readme_bytes': 0, 'large_artifact_downloaded': False,
        'independently_rehashed_ci_elf_bytes': False,
        'ci_package_and_replay_steps_succeeded': True,
        'elf_qualification_limit': 'The successful fixed workflow packages and replays its four native ELF files. This reviewer read its source and complete job logs, but did not download the combined binary-bearing artifact or independently rehash those ELF bytes.'})
    output('review.json', {
        'schema': 'r9-a10-exact-head-completion-review-v1', 'reviewer': '/root/r6_review_ci',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
        'head': HEAD, 'tree': TREE, 'run_id': run['id'], 'run_attempt': 1,
        'run_url': run['html_url'], 'jobs': [{k: j[k] for k in ('id', 'name', 'started_at', 'completed_at', 'conclusion', 'labels')} for j in jobs['jobs']],
        'cargo_groups': counts, 'aggregate_distinct_rust_test_count_claimed': False,
        'count_note': 'Default A07 baseline tests execute again under the objective feature. Counts are grouped by actual command; they are not summed into a distinct-test total.',
        'sigkill_cli_regressions_passed': kill_tests,
        'python_groups': [{'scope': name, 'passed': n} for name, n in zip(('original_process_guard', 'original_shell_contracts', 'original_objective_shell_contracts'), py)],
        'feature_off_all_targets_check': 'passed', 'strict_clippy_ui_and_feature_hepta': 'passed',
        'rustfmt_four_manifests': 'passed', 'committed_ui_lock_enforcement': 'passed',
        'observed_pass_markers': positive_markers,
        'unverified_in_this_run': ['X11 mapping (optional tools absent)', 'CJK candidate interaction',
                                 'two real-font tests (ignored without selected host font)',
                                 'pre-crash client window continuity', 'physical GPU reset', 'Asterinas target graphics'],
        'hepta_wayland_page_source': 'scripted UDS fixture; not original Agentd',
        'separate_original_arm_run_id': 39182491155,
        'arm_status_at_poll02': 'in_progress; no completion qualification in this A10 archive',
        'default_codeql_run_id': 39182489120,
        'default_codeql_scope': 'Dynamic GitHub code-scanning run; not part of the nine repository workflow path predictions.',
        'exact_head_check_snapshot': [{k: c[k] for k in ('id', 'name', 'head_sha', 'status', 'conclusion', 'started_at', 'completed_at', 'details_url')} for c in checks['check_runs']],
        'codeql_note': 'Both CodeQL and Analyze (python) completed successfully. This is a check-status observation, not a security-completeness claim.',
        'artifact_metadata_only': artifact,
        'new_execution_by_reviewer': False, 'inherited_r8_qualification': False,
        'raw_log_note': 'Connector-decoded full UTF-8 job logs preserved unchanged including initial BOM; no binary job-log ZIP download was made.'})
    write('verify_and_stage_a10.py', Path(__file__).read_bytes())
    readme = '''# R9 exact-head A10 completion

This archive independently reviews GitHub run 39182491046, attempt 1, at
5060ac6976b56b32647c728991e489cdee1cce9d (tree ae588699126910065c16b77d83f3ef20b53509f2).
Both A10 jobs completed successfully on 2026-10-19 UTC. Full connector-decoded
job logs and original API text are retained, including earlier incomplete snapshots.

## Executed scopes

UI workspace: 137 passed, 2 host-font tests ignored. Hepta default: 17 passed;
Hepta objective feature: 43 passed, including both real CLI SIGKILL boundaries.
The default baseline is repeated in the feature suite, so these are separate
command counts, not an aggregate of distinct tests. support/ui: 39; tests/ui
Rust contracts: 8. Python process guard, original Shell and original Objective
Shell contracts: 6, 8 and 10 respectively. Feature-off check, strict UI/A07
Clippy, four-manifest rustfmt, and committed UI lock enforcement succeeded.

Actual Weston first layouts, app layouts and cancellation passed. A subsequent
separate compositor test passed crash/restart with the same Session, a new socket
epoch and a new client first layout. It does not prove continuity of pre-crash
client windows. The Hepta page used a scripted UDS fixture. X11 mapping was
explicitly NOT VERIFIED because optional X11 tools were absent. No CJK IME,
physical GPU or Asterinas graphics qualification is claimed.

The fixed CI workflow built, packaged and replayed four native ELF files.
Artifact 12157021582 is recorded by metadata and upload digest only; its combined
binary-bearing ZIP was not downloaded, and this reviewer did not independently
rehash CI ELF bytes. See source-verification.json for this boundary.

The exact-head CodeQL and Analyze (python) checks also succeeded, in the separate
dynamic GitHub code-scanning run 39182489120. That run was outside the nine
repository workflow path predictions. Original ARM run 39182491155 remained in
progress at the retained poll02 snapshot; this archive grants it no qualification.
R8 results are not inherited. No project code or test was rerun by this reviewer.

review.json records exact groups and raw-log locations; SHA256SUMS covers every
payload except itself, and MANIFEST.json records the remaining file catalogue.
'''
    write('README.md', readme.encode())
    members = [{'path': str(p.relative_to(STAGE)), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
               for p in sorted(STAGE.rglob('*')) if p.is_file()]
    output('MANIFEST.json', {'schema': 'byte-catalogue-v1', 'files': members})
    checksum_files = [p for p in sorted(STAGE.rglob('*')) if p.is_file()]
    write('SHA256SUMS', ''.join(sha(p.read_bytes()) + '  ' + str(p.relative_to(STAGE)) + '\n' for p in checksum_files).encode())
    print(json.dumps({'stage': str(STAGE), 'files': len(checksum_files) + 1,
                      'sha256sums': sha((STAGE / 'SHA256SUMS').read_bytes()),
                      'cargo_counts': [(x['scope'], x['passed'], x['ignored']) for x in counts],
                      'python_counts': py, 'status': 'passed'}))


if __name__ == '__main__':
    main()
