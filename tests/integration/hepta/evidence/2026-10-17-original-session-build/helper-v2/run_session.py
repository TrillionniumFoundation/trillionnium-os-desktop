#!/usr/bin/env python3
"""Run the source-bound original Agentd/Session probe with six Shell barriers.

Prerequisites are passed actual Agentd and consumer build receipts. This task
helper reuses those verified outputs; it does not claim the stock fresh-work
gate was invoked. It never acknowledges a capture barrier on behalf of Shell.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
import common as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop-commit', default=c.DEFAULT_COMMIT)
    parser.add_argument('--agentd-receipt', type=Path, default=c.DEFAULT_AGENTD_RECEIPT)
    parser.add_argument('--build-dir', type=Path, default=c.HOME_DIR / 'build-02')
    parser.add_argument('--work-dir', type=Path, default=c.HOME_DIR / 'runtime-01')
    parser.add_argument('--ack-seconds', type=int, default=120, choices=range(1, 121))
    args = parser.parse_args()
    work = args.work_dir.resolve()
    c.require(work.parent == c.HOME_DIR and not work.exists(), 'runtime work directory must be fresh under task root')
    gate = c.load_gate()
    desktop = c.desktop_identity(gate, args.desktop_commit)
    original = c.original_build_identity(gate, args.agentd_receipt)
    build_path = args.build_dir.resolve() / 'receipt.json'
    build = json.loads(build_path.read_text())
    c.require(build.get('status') == 'passed' and build.get('qualification') == 'staged_original_session_consumer_build',
              'actual original-linked consumer build has not passed')
    c.require(build.get('helper_version') == 2 and build.get('probe_lock_stability', {}).get('locked_metadata_passes') == 2,
              'the lock-stable consumer build has not passed')
    c.require(build.get('desktop') == desktop and build.get('desktop_after') == desktop,
              'consumer build was not bound to current frozen desktop source')
    c.require(build.get('original_build') == original and build.get('original_after') == original,
              'original source or Agentd build changed since consumer build')
    binaries = {}
    for name in ['agentd', 'probe', 'observer']:
        item = build['binaries'][name]
        actual = c.binary_identity(gate, Path(item['path']))
        c.require(item == actual, f'{name} bytes changed since actual build')
        binaries[name] = actual
    ui = c.ui_inputs(gate, desktop)
    binaries.update(ui['binaries'])
    work.mkdir(mode=0o700)
    record = {
        'started_at_utc': c.now(), 'qualification': 'staged_original_agentd_persistent_session_runtime',
        'status': 'running', 'desktop': desktop, 'original_build': original, 'helper_version': 2,
        'consumer_build_receipt': {'path': str(build_path), 'sha256': gate.sha256(build_path)},
        'ui_build': ui, 'binaries_before': binaries, 'steps': [],
        'stock_fresh_work_gate_reexecuted': False, 'runtime_probe_attempted': False,
        'live_agentd_acceptance': 'not_run', 'persistent_session_acceptance': 'not_run',
        'shell_capture_qualification': 'separate_consumer_receipt_required',
        'phase_dir': str(work / 'phases'), 'capture_ack_seconds': args.ack_seconds,
        'objective_submission': False, 'model_turn': False, 'device_effect': False,
        'helper_sha256': {path.name: gate.sha256(path) for path in [Path(__file__), Path(c.__file__)]},
    }
    code = 1
    try:
        with tempfile.TemporaryDirectory(prefix='hp-', dir='/tmp') as temporary:
            state = Path(temporary)
            record['private_original_state_root'] = str(state)
            command = [binaries['probe']['path'], binaries['agentd']['path'], binaries['observer']['path'],
                       str(state), '0', '--session-bin', binaries['session']['path'], '--ctl-bin', binaries['ctl']['path'],
                       '--session-phase-dir', str(work / 'phases'), '--session-ack-seconds', str(args.ack_seconds)]
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HEPTA_COGNITIVE_RETRIEVAL_MODE': 'compatibility'}
            timeout = 360 + 6 * args.ack_seconds
            record['runtime_probe_attempted'] = True
            record['live_agentd_acceptance'] = 'failed'
            record['persistent_session_acceptance'] = 'failed'
            c.save_new(work / 'allocation.json', record)
            print(json.dumps({'event': 'original_session_probe_launch', 'phase_dir': record['phase_dir'],
                              'source_commit': desktop['commit'], 'deadline_seconds': timeout}), flush=True)
            try:
                c.checked_command(gate, command, c.DESKTOP, env, work / 'original-session-process.log', timeout, record)
            finally:
                for path in sorted((state / 'ui-runtime').glob('session-*.log')):
                    shutil.copyfile(path, work / path.name)
            log = work / 'original-session-process.log'
            c.require(log.stat().st_size <= 1024 * 1024, 'original Session runtime log exceeded its bound')
            records = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
            gate.validate_runtime_records(records, True)
            c.save_new(work / 'runtime-records.json', records)
            phase_records = [item for item in records if item.get('event') == 'session_phase_observed']
            acknowledgments = [item for item in records if item.get('event') == 'session_phase_acknowledged']
            c.require([item.get('ack') for item in acknowledgments] == [item['ack'] for item in phase_records],
                      'all six exact capture coordination barriers must be acknowledged')
            record['runtime_records'] = records
        record['private_state_cleanup_complete'] = not Path(record['private_original_state_root']).exists()
        record['desktop_after'] = c.desktop_identity(gate, args.desktop_commit)
        record['original_after'] = c.original_build_identity(gate, args.agentd_receipt)
        record['binaries_after'] = {name: c.binary_identity(gate, Path(item['path'])) for name, item in binaries.items()}
        c.require(record['desktop_after'] == desktop and record['original_after'] == original,
                  'source changed during runtime')
        c.require(record['binaries_after'] == binaries, 'actual executable bytes changed during runtime')
        c.require(record['private_state_cleanup_complete'], 'owned private state cleanup incomplete')
        record['helper_sha256_after'] = {path.name: gate.sha256(path) for path in [Path(__file__), Path(c.__file__)]}
        c.require(record['helper_sha256_after'] == record['helper_sha256'], 'executed helper source changed')
        record['live_agentd_acceptance'] = 'passed'
        record['persistent_session_acceptance'] = 'passed'
        record['status'] = 'passed'
        code = 0
    except Exception as error:
        record['status'] = 'failed'
        record['error'] = {'type': type(error).__name__, 'detail': str(error)}
    finally:
        record['ended_at_utc'] = c.now()
        artifacts = [path for path in work.rglob('*') if path.is_file()]
        record['raw_artifacts'] = {str(path.relative_to(work)): {'bytes': path.stat().st_size, 'sha256': gate.sha256(path)}
                                   for path in sorted(artifacts)}
        c.save_new(work / 'receipt.json', record)
        print(json.dumps({'status': record['status'], 'receipt': str(work / 'receipt.json'),
                          'live_agentd_acceptance': record['live_agentd_acceptance'],
                          'persistent_session_acceptance': record['persistent_session_acceptance'],
                          'error': record.get('error')}), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
