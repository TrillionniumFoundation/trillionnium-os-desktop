#!/usr/bin/env python3
"""Compile and execute only the complete affected crate on the full successor."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import traceback

SPEC = importlib.util.spec_from_file_location('current_leaf_selection_verify', Path(__file__).with_name('verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
HERE = Path(__file__).resolve().parent


def exact_catalog(raw, wanted):
    names = []
    for line in raw.decode().splitlines():
        if not line or re.fullmatch(r'\d+ tests?, 0 benchmarks?', line):
            continue
        VERIFY.need(line.endswith(': test'), 'unexpected harness catalog output')
        names.append(line[:-6])
    VERIFY.need(len(names) == len(set(names)) and sorted(names) == wanted,
                'complete compiled catalog differs')


def exact_terminal(raw, wanted):
    text = raw.decode()
    records = []
    started = finished = False
    for line in text.splitlines():
        if not line:
            continue
        VERIFY.need(not finished, 'output after complete harness summary')
        if not started:
            VERIFY.need(line == f'running {len(wanted)} tests', 'exact harness count required')
            started = True
            continue
        match = re.fullmatch(r'test (\S+) \.\.\. ok', line)
        if match:
            records.append(match[1])
            continue
        match = re.fullmatch(r'test result: ok\. (\d+) passed; 0 failed; 0 ignored; 0 measured; '
                            r'0 filtered out; finished in [0-9.]+s', line)
        VERIFY.need(match is not None and int(match[1]) == len(wanted),
                    'one successful unfiltered harness terminal required')
        finished = True
    VERIFY.need(started and finished and len(records) == len(set(records))
                and sorted(records) == wanted, 'actual tests must equal the complete bound catalog')
    return len(records)


def cargo_terminal(raw):
    rows = [VERIFY.decode(line) for line in raw.splitlines() if line]
    terminals = [row for row in rows if row.get('reason') == 'build-finished']
    VERIFY.need(rows and rows[-1] == {'reason': 'build-finished', 'success': True}
                and terminals == [rows[-1]], 'one complete successful Cargo terminal required')
    VERIFY.need(not any(row.get('reason') == 'compiler-message'
                        and row.get('message', {}).get('level') == 'error' for row in rows),
                'Cargo stream contains a compiler error')
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--fetch', action='store_true', help='perform an explicit locked dependency fetch first')
    args = parser.parse_args()
    VERIFY.need(1 <= args.jobs <= 2, 'one or two bounded compilation jobs required')
    packet = VERIFY.verify_packet(args.inventory_sha256)
    producer = args.producer.absolute()
    before = VERIFY.source_snapshot(producer, packet['after'], packet['manifest']['successor']['source_tree'])
    work = VERIFY.fresh_destination(args.work, [HERE, producer])
    report = VERIFY.fresh_destination(args.report, [HERE, producer, work])
    work.mkdir(mode=0o700)
    (work / 'logs').mkdir()
    (work / 'target').mkdir()
    (work / 'tmp').mkdir()
    env = os.environ.copy()
    for name in ('RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'RUSTC_WRAPPER',
                 'RUSTC_WORKSPACE_WRAPPER', 'CARGO_BUILD_TARGET', 'RUSTDOCFLAGS'):
        env.pop(name, None)
    env.update({'CARGO_TARGET_DIR': str(work / 'target'), 'CARGO_BUILD_JOBS': str(args.jobs),
                'TMPDIR': str(work / 'tmp'), 'TMP': str(work / 'tmp'), 'TEMP': str(work / 'tmp'),
                'CARGO_TERM_COLOR': 'never', 'RUSTUP_TOOLCHAIN': '1.93.0',
                'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                'GIT_TERMINAL_PROMPT': '0', 'PYTHONDONTWRITEBYTECODE': '1'})
    env.pop('CARGO_NET_OFFLINE', None)
    result = {'schema': 'p4-current-leaf-selection-complete-crate-ci-v1', 'state': 'RUNNING',
              'packet_inventory_sha256': args.inventory_sha256,
              'source_tree': packet['manifest']['successor']['source_tree'],
              'complete_source_files': len(packet['after']), 'workspace_manifest_modified': False,
              'lockfile_modified': False, 'cargo_jobs': args.jobs, 'commands': [],
              'harnesses': [], 'fresh_passed': 0, 'source_unchanged': False,
              'format_check_run': False, **packet['manifest']['scope']}

    def run(label, argv, seconds=900):
        stdout_path = work / 'logs' / (label + '.stdout')
        stderr_path = work / 'logs' / (label + '.stderr')
        row = {'label': label, 'argv': argv, 'cwd': str(producer), 'timeout_seconds': seconds}
        result['commands'].append(row)
        started = time.monotonic()
        print(json.dumps({'starting': label}), flush=True)
        with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
            child = subprocess.Popen(argv, cwd=producer, env=env, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, start_new_session=True)
            row['pid'] = child.pid
            try:
                code = child.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                row['timed_out'] = True
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=10)
                code = child.returncode
            row['exit_code'] = code
            row['parent_reaped'] = True
        row['seconds'] = round(time.monotonic() - started, 3)
        try:
            os.killpg(child.pid, 0)
            row['process_group_gone'] = False
        except ProcessLookupError:
            row['process_group_gone'] = True
        out = VERIFY.regular(stdout_path)
        err = VERIFY.regular(stderr_path)
        row['stdout'] = {'path': str(stdout_path), **VERIFY.digest(out)}
        row['stderr'] = {'path': str(stderr_path), **VERIFY.digest(err)}
        VERIFY.need(code == 0 and not row.get('timed_out') and row['process_group_gone'],
                    'actual command failed, timed out or left descendants: ' + label)
        return out

    try:
        version = run('toolchain', ['rustc', '+1.93.0', '--version'], 30).decode().strip()
        VERIFY.need(version.startswith('rustc 1.93.0 '), 'fixed Rust toolchain required')
        result['toolchain'] = version
        if args.fetch:
            run('locked-dependency-fetch', ['cargo', '+1.93.0', 'fetch', '--locked'])
        prefix = ['cargo', '+1.93.0']
        common = ['--offline', '--locked', '-p', 'droidloom-applications', '--all-targets']
        run('format-leaf-routes', ['rustfmt', '+1.93.0', '--check', '--edition', '2024',
                                 str(producer / VERIFY.CHANGED_PATH)], 60)
        result['format_check_run'] = True
        result['format_check_scope'] = [VERIFY.CHANGED_PATH]
        cargo_terminal(run('check-all-targets', prefix + ['check'] + common + ['--message-format=json']))
        compiled = cargo_terminal(run('compile-all-tests', prefix + ['test'] + common
                                     + ['--no-run', '--message-format=json']))
        expected = VERIFY.decode(VERIFY.regular(HERE / 'EXPECTED-CATALOG.json'))
        wanted = {(row['kind'], row['target']): row for row in expected}
        VERIFY.need(len(wanted) == 2 and sum(len(row['tests']) for row in wanted.values()) == 42
                    and all(not row['ignored'] and row['tests'] == sorted(set(row['tests']))
                            for row in wanted.values()), 'complete exact affected-crate catalog required')
        actual = {}
        for row in compiled:
            if row.get('reason') != 'compiler-artifact' or not row.get('profile', {}).get('test') or not row.get('executable'):
                continue
            kinds = row['target']['kind']
            VERIFY.need(len(kinds) == 1, 'one explicit test target kind required')
            key = (kinds[0], row['target']['name'])
            VERIFY.need(key in wanted and key not in actual, 'unexpected or duplicate compiled test executable')
            binary = Path(row['executable']).absolute()
            VERIFY.need(binary.is_relative_to(work / 'target'), 'fresh target must own each harness')
            raw = VERIFY.regular(binary)
            VERIFY.need(raw.startswith(b'\x7fELF'), 'actual compiled ELF required')
            actual[key] = {'path': str(binary), **VERIFY.digest(raw)}
        VERIFY.need(set(actual) == set(wanted), 'both compiled application harnesses required')
        for index, (key, row) in enumerate(sorted(actual.items())):
            binary = row['path']
            catalog = wanted[key]['tests']
            exact_catalog(run(f'harness-{index}-catalog', [binary, '--list', '--color', 'never'], 60), catalog)
            exact_catalog(run(f'harness-{index}-ignored', [binary, '--ignored', '--list', '--color', 'never'], 60), [])
            count = exact_terminal(run(f'harness-{index}-tests', [binary, '--test-threads=2', '--color', 'never'], 300), catalog)
            VERIFY.need(VERIFY.digest(VERIFY.regular(binary)) == {key: row[key] for key in ('bytes', 'sha256')},
                        'compiled harness changed during test execution')
            result['harnesses'].append({'kind': key[0], 'target': key[1], **row, 'passed': count})
            result['fresh_passed'] += count
        VERIFY.need(result['fresh_passed'] == 42, 'all 37 original and five new tests must pass')
        after = VERIFY.source_snapshot(producer, packet['after'], packet['manifest']['successor']['source_tree'])
        VERIFY.need(before == after, 'complete successor source changed during compilation or tests')
        VERIFY.verify_packet(args.inventory_sha256)
        result['source_unchanged'] = True
        result['state'] = 'COMPLETE'
    except Exception as error:
        result['state'] = 'FAILED'
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    VERIFY.write_report(report, result, [HERE, producer, work])
    print(json.dumps({key: result[key] for key in ('state', 'source_tree', 'fresh_passed', 'source_unchanged')}), flush=True)
    raise SystemExit(0 if result['state'] == 'COMPLETE' else 1)


if __name__ == '__main__':
    main()
