#!/usr/bin/env python3
"""Require the retained-owner regression to fail only under its frozen old behavior.

The original full kernel gate runs first in the candidate checkout. This entry
creates a separate local Git commit containing the one production mutation,
runs the unchanged original core gate, and preserves its genuine failure. It
does not convert that gate's result into a product success or alter its checks.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'tests/organ_backend/cpu_owner_current_slot_negative.patch'
PATCH_SHA = '96dbb29fec63b3946bcb18a95567a7a2d2191130cc3ec9f7feeafad29e1a28a2'
CPU_PATH = 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs'
PREFIX = 'aster_core::fs::fs_impls::cgroupfs::controller::cpu::owner_retention_regressions::'
FAILED_NAMES = {PREFIX + name for name in (
    'controller_publication_charges_the_entire_prefix_to_the_old_incarnation',
    'retained_leaf_debits_its_original_ancestor_chain_after_parent_replacement',
    'exited_task_resumes_its_retained_incarnation_after_replacement_and_reap',
)}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def test_results(serial):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', serial.decode()).replace('\r', '')
    require(len(re.findall(r'\[ktest runner\] running \d+ tests in \d+ crates', text)) == 1,
            'kernel runner start is missing or repeated')
    headers = list(re.finditer(r'^running (\d+) tests in crate "([^"]+)"$', text, re.M))
    require(len(headers) == 1 and headers[0][2] == 'aster-core',
            'core header is missing, repeated or belongs to another crate')
    summaries = list(re.finditer(
        r'^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.$',
        text, re.M))
    require(len(summaries) == 1, 'kernel summary is missing or repeated')
    summary = summaries[0]
    require(headers[0].end() < summary.start(), 'core summary precedes its tests')
    section = text[headers[0].end():summary.start()]
    starts = list(re.finditer(r'^test ([\w:]+) \.\.\.', section, re.M))
    require(len(starts) == len({test[1] for test in starts}) == int(headers[0][1])
            and all(test[1].startswith('aster_core::') for test in starts),
            'core test names are missing, repeated or incomplete')
    tests = []
    for index, test in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(section)
        body = section[test.end():end]
        # The original runner prints the name before invoking the test, then
        # prints the colored result after it returns. Device and expected-panic
        # logs may occupy the intervening lines. Require one terminal outcome
        # in each complete test segment instead of requiring a single line.
        outcomes = re.findall(r' (ok|FAILED)\n', body)
        terminal = re.search(r' (ok|FAILED)\n\n*\Z', body)
        require(len(outcomes) == 1 and terminal is not None
                and outcomes[0] == terminal[1], 'test outcome is missing or ambiguous: ' + test[1])
        tests.append((test[1], terminal[1]))
    status, passed, failed, filtered = summary.groups()
    require(int(filtered) == 0 and int(passed) == sum(result == 'ok' for _, result in tests)
            and int(failed) == sum(result == 'FAILED' for _, result in tests), 'kernel counts differ')
    require((status == 'ok') == (int(failed) == 0), 'kernel summary status differs from its failures')
    # The original runner returns immediately after a complete failed crate;
    # it emits the all-crates marker only when every selected crate succeeded.
    require(text.count('[ktest runner] All crates tested.') == int(status == 'ok'),
            'kernel runner completion differs from the original failure path')
    require('[skipped:' not in text, 'core test was skipped')
    require(not any(marker in text for marker in (
        'An uncaught panic occurred:', 'Uncaught panic:', 'unknown panic payload!',
        'Non-resettable panic!', 'The panic handler panicked', 'Panicked in `PanicGuard`')),
        'kernel failed outside the expected assertions')
    return status, dict(tests)


def run(args, out, result):
    candidate = module('owner_candidate', ROOT / 'tests/kernel/control/run_queryabi_candidate_guest.py')
    checker = module('owner_ktest_check', ROOT / 'support/build/ktest/check.py')
    head = git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    tree = git(ROOT, 'rev-parse', 'HEAD^{tree}').decode().strip()
    before = candidate.source_snapshot(ROOT, head, tree)
    save(out / 'candidate-source-before.json', before)
    result.update(candidate_head=head, candidate_tree=tree)
    require(sha(PATCH.read_bytes()) == PATCH_SHA, 'negative-control patch differs')
    shutil.copyfile(PATCH, out / 'declared-negative-control.patch')

    green = args.green_evidence.resolve()
    green_env = json.loads((green / 'environment.json').read_text())
    require(green_env['git_head'] == head and green_env['git_status'] == ''
            and green_env['test_name'] is None and green_env['toolchain'] == 'nightly-2026-07-21',
            'green gate is not the clean unfiltered candidate')
    require(json.loads((green / 'result.json').read_text())['passed'] is True,
            'original full kernel gate did not pass')
    green_guests = sorted((green / 'aster-core/guests').glob('guest-*'))
    require(len(green_guests) == 1, 'green core guest count differs')
    green_report = checker.check_guest(green_guests[0], 'aster-core')
    green_record = json.loads((green_guests[0] / 'qemu.json').read_text())
    green_raw = (green_guests[0] / 'serial.log').read_bytes()
    status, green_tests = test_results(green_raw)
    require(status == 'ok' and len(green_tests) >= 189 and FAILED_NAMES <= green_tests.keys(),
            'green test denominator lacks the retained-owner regression')
    save(out / 'green-core-validation.json', green_report)
    result['green_serial_sha256'] = sha(green_raw)

    negative = args.worktree.absolute()
    require(not negative.exists() and not negative.is_symlink(), 'negative worktree must be new')
    git(ROOT, 'worktree', 'add', '--detach', str(negative), head)
    git(negative, 'apply', '--index', str(PATCH))
    require(git(negative, 'diff', '--cached', '--name-only').decode().splitlines() == [CPU_PATH],
            'negative mutation changed an unexpected path')
    git(negative, '-c', 'user.name=A06 negative control', '-c', 'user.email=a06-negative@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-m', 'test: identified local current-slot CPU owner negative control')
    negative_head = git(negative, 'rev-parse', 'HEAD').decode().strip()
    negative_tree = git(negative, 'rev-parse', 'HEAD^{tree}').decode().strip()
    result.update(negative_head=negative_head, negative_tree=negative_tree)
    (out / 'applied-negative-control.patch').write_bytes(git(negative, 'diff', head, negative_head))
    negative_before = candidate.source_snapshot(negative, negative_head, negative_tree)
    save(out / 'negative-source-before.json', negative_before)
    changed = [name for name, record in before['files'].items()
               if negative_before['files'].get(name) != record]
    require(set(negative_before['files']) == set(before['files']) and changed == [CPU_PATH],
            'negative source set differs beyond the declared CPU mutation')

    env = os.environ.copy()
    env['VDSO_LIBRARY_DIR'] = str(ROOT / 'support/build/out/linux-vdso')
    command = [sys.executable, '-I', '-B', str(negative / 'support/build/ktest/run.py'),
               '--crate', 'aster-core', '--skip-osdk-install', '--output', str(out / 'gate')]
    save(out / 'command.json', {'argv': command, 'cwd': str(negative),
                               'vdso_library_dir': env['VDSO_LIBRARY_DIR']})
    with (out / 'gate-wrapper.log').open('wb') as log:
        completed = subprocess.run(command, cwd=negative, env=env, stdout=log, stderr=subprocess.STDOUT)
    result['original_gate_exit'] = completed.returncode
    save(out / 'original-gate-exit.json', {'exit_code': completed.returncode})
    negative_after = candidate.source_snapshot(negative, negative_head, negative_tree)
    save(out / 'negative-source-after.json', negative_after)
    require(negative_before == negative_after, 'negative source changed during execution')
    require(before == candidate.source_snapshot(ROOT, head, tree), 'candidate changed during the negative gate')
    gate = out / 'gate'
    environment = json.loads((gate / 'environment.json').read_text())
    require(environment['git_head'] == negative_head and environment['git_status'] == ''
            and environment['test_name'] is None, 'negative gate source or filter differs')
    for key in ('toolchain', 'rustc', 'cargo', 'build_inputs_sha256', 'osdk_sha256', 'vdso_sha256'):
        require(environment[key] == green_env[key], 'negative build input differs: ' + key)
    guests = sorted((gate / 'aster-core/guests').glob('guest-*'))
    require(len(guests) == 1, 'negative core guest count differs')
    record = json.loads((guests[0] / 'qemu.json').read_text())
    raw = (guests[0] / 'serial.log').read_bytes()
    require(sha(raw) == record['serial_sha256'], 'negative raw serial differs')
    require(record['raw_exit_code'] == 65 and record['timed_out'] is False and record['crate'] == 'aster-core',
            'negative guest is not the expected real test failure')
    require(completed.returncode != 0 and int((gate / 'aster-core/osdk-exit-code.txt').read_text()) != 0,
            'original gate incorrectly accepted the negative guest')
    for key in ('qemu_sha256', 'qemu_version', 'profile'):
        require(record[key] == green_record[key], 'negative QEMU input differs: ' + key)
    require(record['artifacts']['-bios'] == green_record['artifacts']['-bios'], 'negative firmware differs')
    status, negative_tests = test_results(raw)
    require(status == 'FAILED' and negative_tests.keys() == green_tests.keys(),
            'negative denominator differs from the full green core suite')
    require({name for name, outcome in negative_tests.items() if outcome == 'FAILED'} == FAILED_NAMES,
            'negative failed-name set differs')
    elf = Path(record['artifacts']['-kernel']['path'])
    data = elf.read_bytes()
    require(sha(data) == record['artifacts']['-kernel']['sha256'] and len(data) == record['artifacts']['-kernel']['size'],
            'negative kernel ELF differs')
    (out / 'negative-control-kernel.elf').write_bytes(data)
    require((gate / 'aster-core/generated.Cargo.lock').read_bytes() ==
            (ROOT / 'support/build/ktest/locks/aster-core.Cargo.lock').read_bytes(), 'negative Cargo lock differs')
    result.update(passed=True, negative_control_detected=True, product_qualification=False,
                  total_core_tests=len(green_tests), negative_passed=len(green_tests) - 3,
                  negative_failed=sorted(FAILED_NAMES), raw_qemu_exit=65, timed_out=False,
                  negative_kernel_sha256=sha(data), negative_serial_sha256=sha(raw),
                  all_other_source_files_unchanged=True, source_snapshots_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--green-evidence', type=Path, required=True)
    parser.add_argument('--worktree', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'a06.cpu-owner-negative.v1', 'passed': False,
              'product_qualification': False, 'patch_sha256': PATCH_SHA}
    save(out / 'result.json', result)
    try:
        run(args, out, result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result['error'] = str(error)
    save(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
