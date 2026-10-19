#!/usr/bin/env python3
"""Require exact CPU/clock regressions to fail under their frozen old behavior.

The original full kernel gate runs first in the candidate checkout. This entry
creates a separate local Git commit containing the one production mutation,
runs the unchanged original core gate at the original OSDK-bound source path,
then restores the candidate. It preserves both exact source identities and
the genuine failure without altering the original gate or its acceptance.
"""
import argparse
from contextlib import contextmanager
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
PATCH_SHA = '04b19a7a89b8f8591d9a18766390167201e999a9617febcd9d0c70902005f1bd'
CPU_PATH = 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs'
SCHED_PATH = 'kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs'
CLOCK_PATH = 'kernel/asterinas/kernel/core/comps/time/src/clocksource.rs'
VDSO_PATH = 'kernel/asterinas/kernel/core/src/vdso.rs'
PREFIX = 'aster_core::fs::fs_impls::cgroupfs::controller::cpu::owner_retention_regressions::'
FAILED_NAMES = {PREFIX + name for name in (
    'controller_publication_charges_the_entire_prefix_to_the_old_incarnation',
    'retained_leaf_debits_its_original_ancestor_chain_after_parent_replacement',
    'exited_task_resumes_its_retained_incarnation_after_replacement_and_reap',
)}
CLOCK_PREFIX = 'aster_core::vdso::clocksource_regressions::'
HANDOFF_PREFIX = 'aster_core::fs::fs_impls::cgroupfs::controller::cpu::scheduler_handoff_regressions::'
USAGE_PREFIX = 'aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::usage_tests::'
HANDOFF_NAMES = (
    'outgoing_tail_ends_at_the_incoming_segment_start',
    'handoff_debits_the_old_window_before_rechecking_a_shared_ancestor',
    'waiting_dequeue_retains_its_owner_through_selection_retries',
    'exiting_dequeue_retains_its_owner_through_selection_retries',
)

# The caller can select only reviewed production mutations, never arbitrary
# source, expected failures, count reductions or test filters. Each mutation
# is applied separately to the same complete green source and suite.
CONTROLS = {
    'owner-current-slot': (PATCH.name, PATCH_SHA, CPU_PATH, FAILED_NAMES, 189),
    'clocksource-drop-fraction': (
        'clocksource_drop_fraction_negative.patch',
        '6aeb53178b4facbe105c7fd4ff3e8086d5a9b57f2715f80781efc2764338a442',
        CLOCK_PATH, {CLOCK_PREFIX + name for name in (
            'fragmented_refreshes_preserve_fractional_time_and_endpoint_differences',
            'vdso_and_kernel_share_the_fractional_phase_at_the_next_nanosecond',
            'full_width_vdso_fraction_survives_second_rollover_and_checks_realtime_overflow')} | {
                USAGE_PREFIX + 'fragmented_three_ghz_runtime_keeps_absolute_endpoint_precision'}, 201),
    'vdso-drop-fraction': (
        'vdso_drop_fraction_negative.patch',
        'a1e116c7af6a57add22693b4fa985b8bb45809df3ad6765b52ea8efa979975c9',
        VDSO_PATH, {CLOCK_PREFIX + name for name in (
            'vdso_and_kernel_share_the_fractional_phase_at_the_next_nanosecond',
            'full_width_vdso_fraction_survives_second_rollover_and_checks_realtime_overflow',
            'mapped_vdso_publishes_the_phase_and_fault_mode_under_the_existing_sequence')}, 201),
    'vdso-skip-fault-mode': (
        'vdso_skip_fault_mode_negative.patch',
        'da1f7c360136bfe330cba58acef4cf894d423043e1b3b9790958b923d4fcd452',
        VDSO_PATH, {CLOCK_PREFIX + 'mapped_vdso_publishes_the_phase_and_fault_mode_under_the_existing_sequence'}, 201),
    'handoff-drop-tail': (
        'cpu_handoff_drop_tail_negative.patch',
        '2e9a87cdf9044f29dbcb8c932e72079eaf3fc9ecde791c9627b45b9b06257ffc',
        SCHED_PATH, {HANDOFF_PREFIX + name for name in HANDOFF_NAMES}, 201),
    'handoff-eligibility-first': (
        'cpu_handoff_eligibility_first_negative.patch',
        '8a90266278c3610c337e9ce780130e3a179ccce6942bbd4db05c53cfd805546c',
        SCHED_PATH, {HANDOFF_PREFIX + HANDOFF_NAMES[1]}, 201),
    'dequeue-drop-owner': (
        'cpu_dequeue_drop_owner_negative.patch',
        'b6fc10180e9fe292249409c758151763401dddb39bb4b2851bf53f71b3c959dd',
        SCHED_PATH, {HANDOFF_PREFIX + name for name in HANDOFF_NAMES[2:]}, 201),
}


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


def checked_green_kernel(record, retained_path=None):
    """A later mutation cannot replace the original successful ELF identity."""
    artifact = record['artifacts']['-kernel']
    path = retained_path if retained_path is not None else Path(artifact['path'])
    data = Path(path).read_bytes()
    require(sha(data) == artifact['sha256'] and len(data) == artifact['size'],
            'green core ELF does not match the original QEMU record')
    return data


@contextmanager
def identified_checkout(root, candidate_head, negative_head):
    """Use the original OSDK compile-time path and restore a clean candidate."""
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == candidate_head,
            'checkout head changed before the negative run')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'),
            'checkout is dirty before the negative run')
    branch = subprocess.run(['git', 'symbolic-ref', '--quiet', '--short', 'HEAD'],
                            cwd=root, stdout=subprocess.PIPE, check=False)
    require(branch.returncode in (0, 1), 'cannot identify original checkout ref')
    restore = branch.stdout.decode().strip() if branch.returncode == 0 else candidate_head
    git(root, 'checkout', '--detach', negative_head)
    try:
        yield
    finally:
        # Never use --force or discard unexpected tracked changes. Failure to
        # restore is a real gate failure; later product steps cannot proceed.
        git(root, 'checkout', restore)
        require(git(root, 'rev-parse', 'HEAD').decode().strip() == candidate_head,
                'candidate head was not restored after the negative run')


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
    patch_name, patch_sha, changed_path, failed_names, minimum_tests = CONTROLS[args.control]
    patch = ROOT / 'tests/organ_backend' / patch_name
    candidate = module('owner_candidate', ROOT / 'tests/kernel/control/run_queryabi_candidate_guest.py')
    checker = module('owner_ktest_check', ROOT / 'support/build/ktest/check.py')
    head = git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    tree = git(ROOT, 'rev-parse', 'HEAD^{tree}').decode().strip()
    before = candidate.source_snapshot(ROOT, head, tree)
    save(out / 'candidate-source-before.json', before)
    result.update(candidate_head=head, candidate_tree=tree)
    require(sha(patch.read_bytes()) == patch_sha, 'negative-control patch differs')
    shutil.copyfile(patch, out / 'declared-negative-control.patch')

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
    require(status == 'ok' and len(green_tests) >= minimum_tests and failed_names <= green_tests.keys(),
            'green test denominator lacks the selected complete regression')
    save(out / 'green-core-validation.json', green_report)
    result['green_serial_sha256'] = sha(green_raw)
    green_bytes = checked_green_kernel(green_record, args.green_kernel)
    (out / 'green-core-kernel.elf').write_bytes(green_bytes)

    negative = args.worktree.absolute()
    require(not negative.exists() and not negative.is_symlink(), 'negative worktree must be new')
    git(ROOT, 'worktree', 'add', '--detach', str(negative), head)
    git(negative, 'apply', '--index', str(patch))
    require(git(negative, 'diff', '--cached', '--name-only').decode().splitlines() == [changed_path],
            'negative mutation changed an unexpected path')
    git(negative, '-c', 'user.name=A06 negative control', '-c', 'user.email=a06-negative@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-m', 'test: identified local ' + args.control + ' negative control')
    negative_head = git(negative, 'rev-parse', 'HEAD').decode().strip()
    negative_tree = git(negative, 'rev-parse', 'HEAD^{tree}').decode().strip()
    result.update(negative_head=negative_head, negative_tree=negative_tree)
    (out / 'applied-negative-control.patch').write_bytes(git(negative, 'diff', head, negative_head))
    archived_negative = candidate.source_snapshot(negative, negative_head, negative_tree)
    save(out / 'negative-archive-source.json', archived_negative)
    changed = [name for name, record in before['files'].items()
               if archived_negative['files'].get(name) != record]
    require(set(archived_negative['files']) == set(before['files']) and changed == [changed_path],
            'negative source set differs beyond the declared CPU mutation')

    env = os.environ.copy()
    env['VDSO_LIBRARY_DIR'] = str(ROOT / 'support/build/out/linux-vdso')
    command = [sys.executable, '-I', '-B', str(ROOT / 'support/build/ktest/run.py'),
               '--crate', 'aster-core', '--skip-osdk-install', '--output', str(out / 'gate')]
    save(out / 'command.json', {'argv': command, 'cwd': str(ROOT),
                               'execution_head': negative_head,
                               'negative_archive_worktree': str(negative),
                               'vdso_library_dir': env['VDSO_LIBRARY_DIR']})
    with identified_checkout(ROOT, head, negative_head):
        negative_before = candidate.source_snapshot(ROOT, negative_head, negative_tree)
        save(out / 'negative-source-before.json', negative_before)
        require(negative_before['files'] == archived_negative['files'],
                'negative execution checkout differs from the identified archive')
        with (out / 'gate-wrapper.log').open('wb') as log:
            completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        result['original_gate_exit'] = completed.returncode
        save(out / 'original-gate-exit.json', {'exit_code': completed.returncode})
        negative_after = candidate.source_snapshot(ROOT, negative_head, negative_tree)
        save(out / 'negative-source-after.json', negative_after)
        require(negative_before == negative_after, 'negative source changed during execution')
    restored = candidate.source_snapshot(ROOT, head, tree)
    save(out / 'candidate-source-after.json', restored)
    require(before == restored, 'candidate was not exactly restored after the negative gate')
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
    require({name for name, outcome in negative_tests.items() if outcome == 'FAILED'} == failed_names,
            'negative failed-name set differs')
    elf = Path(record['artifacts']['-kernel']['path'])
    data = elf.read_bytes()
    require(sha(data) == record['artifacts']['-kernel']['sha256'] and len(data) == record['artifacts']['-kernel']['size'],
            'negative kernel ELF differs')
    (out / 'negative-control-kernel.elf').write_bytes(data)
    require((gate / 'aster-core/generated.Cargo.lock').read_bytes() ==
            (ROOT / 'support/build/ktest/locks/aster-core.Cargo.lock').read_bytes(), 'negative Cargo lock differs')
    result.update(passed=True, negative_control_detected=True, product_qualification=False,
                  total_core_tests=len(green_tests), negative_passed=len(green_tests) - len(failed_names),
                  negative_failed=sorted(failed_names), raw_qemu_exit=65, timed_out=False,
                  negative_kernel_sha256=sha(data), negative_serial_sha256=sha(raw),
                  green_kernel_sha256=sha(green_bytes),
                  same_osdk_binary_and_source_path=True,
                  all_other_source_files_unchanged=True, source_snapshots_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', choices=sorted(CONTROLS), default='owner-current-slot')
    parser.add_argument('--green-evidence', type=Path, required=True)
    parser.add_argument('--green-kernel', type=Path,
                        help='Archived original green ELF, required after a prior mutation rebuilt the shared target')
    parser.add_argument('--worktree', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'a06.cpu-owner-negative.v1', 'passed': False,
              'product_qualification': False, 'control': args.control,
              'patch_sha256': CONTROLS[args.control][1],
              'declared_changed_path': CONTROLS[args.control][2]}
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
