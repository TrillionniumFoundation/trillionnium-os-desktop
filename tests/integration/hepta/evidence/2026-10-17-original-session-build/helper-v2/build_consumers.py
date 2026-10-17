#!/usr/bin/env python3
"""After the successful native Agentd build, build actual observer/probe only.

This reuses the task's new copied cache, preserves original source/old outputs,
and does not execute Agentd, Session or Shell. It is a staged build, not a stock
run_original_agentd --execute run or a second fresh eight-GiB gate invocation.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
import common as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop-commit', default=c.DEFAULT_COMMIT)
    parser.add_argument('--agentd-receipt', type=Path, default=c.DEFAULT_AGENTD_RECEIPT)
    parser.add_argument('--work-dir', type=Path, default=c.HOME_DIR / 'build-02')
    args = parser.parse_args()
    work = args.work_dir.resolve()
    c.require(work.parent == c.HOME_DIR and not work.exists(), 'build work directory must be fresh under the task runtime root')
    gate = c.load_gate()
    desktop = c.desktop_identity(gate, args.desktop_commit)
    original = c.original_build_identity(gate, args.agentd_receipt)  # Must pass before any Cargo launch.
    retained = json.loads((c.RETAINED / 'ownership.json').read_text())
    c.require(retained['root'] == str(c.RETAINED) and retained['source_pin'] == gate.PIN,
              'retained compiler input identity mismatch')
    previous_path = c.HOME_DIR / 'build-01/receipt.json'
    previous = json.loads(previous_path.read_text())
    c.require(previous.get('status') == 'failed' and not previous.get('runtime_probe_attempted'),
              'preserved first consumer failure has changed')
    work.mkdir(mode=0o700)
    record = {'started_at_utc': c.now(), 'qualification': 'staged_original_session_consumer_build',
              'status': 'running', 'desktop': desktop, 'original_build': original, 'helper_version': 2,
              'previous_failed_consumer_build': {'path': str(previous_path), 'sha256': gate.sha256(previous_path),
                                                 'error': previous.get('error'), 'status': 'failed'},
              'runtime_probe_attempted': False, 'stock_fresh_work_gate_reexecuted': False,
              'retained_r4_inputs_modified': False, 'steps': [],
              'helper_sha256': {path.name: gate.sha256(path) for path in
                  [Path(__file__), Path(c.__file__)]}}
    code = 1
    try:
        observer_target = work / 'observer-target'
        observer_env = c.environment(gate, observer_target)
        command = [str(c.RUSTUP), 'run', '1.88.0', 'cargo', 'build', '--locked', '--offline',
                   '--manifest-path', str(c.DESKTOP / 'services/hepta-os/Cargo.toml'), '--bin', 'hepta-observe']
        c.checked_command(gate, command, c.DESKTOP, observer_env, work / 'observer-build.log', 900, record)
        runner = work / 'probe'
        record['probe_patch_omission'] = gate.prepare_runner(c.ORIGINAL, runner)
        original_env = c.environment(gate, c.ORIGINAL_BUILD / 'target', original=True)
        record['build_environment_paths'] = {key: original_env[key] for key in
            ['CARGO_HOME', 'RUSTUP_HOME', 'CARGO_TARGET_DIR', 'PATH', 'TMPDIR', 'CARGO_BUILD_JOBS', 'CARGO_INCREMENTAL']}
        prefix = [str(c.RUSTUP), 'run', '1.95.0', 'cargo']
        metadata = prefix + ['metadata', '--offline', '--format-version', '1', '--manifest-path', str(runner / 'Cargo.toml')]
        c.checked_command(gate, metadata, runner, original_env, work / 'probe-resolution.log', 300, record)
        record['probe_lock_validation'] = gate.verify_runner_lock(c.ORIGINAL, runner)
        record['probe_lock_stability'] = {'sha256': gate.sha256(runner / 'Cargo.lock'), 'locked_metadata_passes': 0}
        for ordinal in [1, 2]:
            c.checked_command(gate, metadata + ['--locked'], runner, original_env,
                              work / f'probe-locked-metadata-{ordinal}.log', 300, record)
            c.require(gate.sha256(runner / 'Cargo.lock') == record['probe_lock_stability']['sha256']
                      and gate.verify_runner_lock(c.ORIGINAL, runner) == record['probe_lock_validation'],
                      'probe lock changed during consecutive locked metadata')
            record['probe_lock_stability']['locked_metadata_passes'] += 1
        common = ['--locked', '--offline', '--profile', 'dev-small', '--manifest-path', str(runner / 'Cargo.toml'), '-j1']
        c.checked_command(gate, prefix + ['build', *common], runner, original_env, work / 'probe-build.log', 1200, record)
        c.checked_command(gate, prefix + ['test', *common, '--bin', gate.RUNNER_NAME, 'original_session_probe::tests::'],
                          runner, original_env, work / 'probe-stale-tests.log', 600, record)
        text = (work / 'probe-stale-tests.log').read_text()
        c.require('2 passed; 0 failed' in text, 'both actual Rust stale-contract tests must execute successfully')
        gate.verify_runner_lock(c.ORIGINAL, runner)
        c.require(gate.sha256(runner / 'Cargo.lock') == record['probe_lock_stability']['sha256'],
                  'probe lock changed during locked compilation or Rust tests')
        shutil.copyfile(runner / 'Cargo.lock', work / 'resolved-probe-Cargo.lock')
        record['probe_manifest_sha256'] = gate.sha256(runner / 'Cargo.toml')
        record['resolved_probe_lock_sha256'] = gate.sha256(runner / 'Cargo.lock')
        record['probe_sources_sha256'] = {path.name: gate.sha256(path) for path in sorted((runner / 'src').glob('*.rs'))}
        record['binaries'] = {
            'agentd': original['binary'],
            'observer': c.binary_identity(gate, observer_target / 'debug/hepta-observe'),
            'probe': c.binary_identity(gate, c.ORIGINAL_BUILD / 'target/dev-small' / gate.RUNNER_NAME),
        }
        record['desktop_after'] = c.desktop_identity(gate, args.desktop_commit)
        record['original_after'] = c.original_build_identity(gate, args.agentd_receipt)
        c.require(record['desktop_after'] == desktop and record['original_after'] == original,
                  'source or original Agentd binary changed during consumer build')
        record['helper_sha256_after'] = {path.name: gate.sha256(path) for path in [Path(__file__), Path(c.__file__)]}
        c.require(record['helper_sha256_after'] == record['helper_sha256'], 'executed helper source changed')
        record['status'] = 'passed'
        code = 0
    except Exception as error:
        record['status'] = 'failed'
        record['error'] = {'type': type(error).__name__, 'detail': str(error)}
    finally:
        record['ended_at_utc'] = c.now()
        c.save_new(work / 'receipt.json', record)
        print(json.dumps({'status': record['status'], 'receipt': str(work / 'receipt.json'),
                          'runtime_probe_attempted': False, 'error': record.get('error')}), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
