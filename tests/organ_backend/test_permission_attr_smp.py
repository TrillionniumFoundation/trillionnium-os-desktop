#!/usr/bin/env python3
"""Adversarial host tests for the SMP evidence parser; these never run a kernel."""
import copy
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "permission_smp_checker", ROOT / "support/build/ktest/check-permission-smp.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
full_spec = importlib.util.spec_from_file_location("permission_full_checker", ROOT / "support/build/ktest/check.py")
full_checker = importlib.util.module_from_spec(full_spec)
full_spec.loader.exec_module(full_checker)
prepare_spec = importlib.util.spec_from_file_location("permission_test_locks", ROOT / "support/build/ktest/prepare-locks.py")
prepare = importlib.util.module_from_spec(prepare_spec)
prepare_spec.loader.exec_module(prepare)
source_spec = importlib.util.spec_from_file_location("permission_source_verifier", ROOT / "support/build/verify-source.py")
source_verifier = importlib.util.module_from_spec(source_spec)
source_spec.loader.exec_module(source_verifier)


def fixture_serial(control=None):
    failed = checker.FAILURES[control]
    lines = [checker.BOOTSTRAP, '[ktest runner] running 255 tests in 1 crates',
             'running 255 tests in crate "aster-core"', '']
    for case, name in checker.TESTS.items():
        busy = "false" if case in failed else "true"
        fields = f"case={case} cpu_a=0 cpu_b=1 entered=1 lock_busy={busy} a_rc=0 b_rc=0"
        if case == "owner_alias":
            mode = "4755" if case in failed else "755"
            fields += f" uid=1002 mode={mode} alias_uid=1002 alias_mode={mode}"
        elif case == "clear_setid_alias":
            mode = "755" if case in failed else "600"
            fields += f" uid=1000 mode={mode} alias_uid=1000 alias_mode={mode}"
        else:
            mode = "666" if case in failed else "777"
            fields += f" mode=777 sealed_mode={mode} seal_exec=true"
        lines.extend([f"test {name} ...", "PERMISSION_SMP_OBSERVATION " + fields,
                      " FAILED" if case in failed else " ok"])
    status = "FAILED" if failed else "ok"
    lines.extend(['', f'test result: {status}. {3 - len(failed)} passed; {len(failed)} failed; 252 filtered out.'])
    if not failed:
        lines.extend(['', '[ktest runner] All crates tested.'])
    return ('\n'.join(lines) + '\n').encode()


class SerialOracle(unittest.TestCase):
    def test_three_fixed_outcomes(self):
        for control in checker.FAILURES:
            with self.subTest(control=control):
                report = checker.parse_serial(fixture_serial(control), control)
                self.assertEqual(report['failed'], len(checker.FAILURES[control]))

    def test_metadata_counterexample_is_required(self):
        for control in ('ramfs-split-lock', 'memfd-release-seal'):
            raw = fixture_serial(control)
            if control == 'ramfs-split-lock':
                raw = raw.replace(b'mode=4755', b'mode=755')
            else:
                raw = raw.replace(b'sealed_mode=666', b'sealed_mode=777')
            with self.subTest(control=control), self.assertRaises(ValueError):
                checker.parse_serial(raw, control)

    def test_positive_rejects_old_lock_behavior(self):
        for control in ('ramfs-split-lock', 'memfd-release-seal'):
            with self.subTest(control=control), self.assertRaises(ValueError):
                checker.parse_serial(fixture_serial(control))

    def test_rejects_reduced_fabricated_or_incomplete_observations(self):
        good = fixture_serial()
        variants = {
            'missing_bootstrap': good.replace(checker.BOOTSTRAP.encode(), b''),
            'duplicate_bootstrap': good + checker.BOOTSTRAP.encode() + b'\n',
            'fifo_bootstrap': good.replace(b'scheduler=class', b'scheduler=fifo'),
            'bare_runner': good.replace(b'runner_thread=true', b'runner_thread=false'),
            'wrong_runner_cpu': good.replace(b'runner_cpu=0', b'runner_cpu=1'),
            'bootstrap_after_runner': good.replace(checker.BOOTSTRAP.encode() + b'\n', b'')
                                      + checker.BOOTSTRAP.encode() + b'\n',
            'one_cpu': good.replace(b'cpu_b=1', b'cpu_b=0'),
            'no_real_hook': good.replace(b'entered=1', b'entered=0'),
            'no_owner_lock': good.replace(b'lock_busy=true', b'lock_busy=false'),
            'failed_operation': good.replace(b'b_rc=0', b'b_rc=1'),
            'worker_unwound': good.replace(b'a_rc=0', b'a_rc=-998'),
            'alias_disagrees': good.replace(b'alias_uid=1002', b'alias_uid=1000'),
            'missing_case': good.replace(b'case=owner_alias', b'case=missing'),
            'missing_test': good.replace(checker.TESTS['owner_alias'].encode(), b'aster_core::other'),
            'duplicate_test': good.replace(checker.TESTS['memfd_seal'].encode(), checker.TESTS['owner_alias'].encode()),
            'reduced_compiled_suite': good.replace(b'255 tests', b'254 tests').replace(b'252 filtered', b'251 filtered'),
            'filtered_required_test': good.replace(b'3 passed', b'2 passed').replace(b'252 filtered', b'253 filtered'),
            'soft_skip': good.replace(b'case=owner_alias', b'[skipped: SMP unavailable] case=owner_alias'),
            'missing_terminal': good.replace(b' ok\n', b'\n', 1),
            'duplicate_terminal': good.replace(b' ok\n', b' ok\n ok\n', 1),
            'missing_completion': good.replace(b'[ktest runner] All crates tested.', b''),
            'duplicate_runner': good + b'[ktest runner] running 255 tests in 1 crates\n',
            'fatal_panic': good + b'An uncaught panic occurred:\n',
            'observed_outside_test': good + b'PERMISSION_SMP_OBSERVATION case=owner_alias\n',
            'duplicate_field': good.replace(b'cpu_a=0', b'cpu_a=0 cpu_a=0'),
        }
        for label, raw in variants.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                checker.parse_serial(raw)

    def test_rejects_wrong_or_arbitrary_failure_set(self):
        with self.assertRaises(ValueError):
            checker.parse_serial(fixture_serial('ramfs-split-lock'), 'memfd-release-seal')
        with self.assertRaises(ValueError):
            checker.parse_serial(fixture_serial(), 'accept-any-failure')


class TestBaseManifest(unittest.TestCase):
    def test_external_entry_is_enabled_only_by_the_core_smp_feature(self):
        upstream = ROOT / 'kernel/asterinas'
        manifest = tomllib.loads(prepare.generated_manifest(upstream, 'aster-core'))
        self.assertEqual(manifest['features']['permission-attr-smp-ktest'],
                         ['aster-core/permission-attr-smp-ktest', 'osdk-test-kernel/external-entry'])
        self.assertNotIn('features', manifest['dependencies']['osdk-test-kernel'])
        self.assertEqual(manifest['features']['default'], ['cvm_guest'])
        self.assertEqual(manifest['features']['g1c-trusted-observe'],
                         ['aster-core/g1c-trusted-observe'])
        runner = tomllib.loads((upstream / 'osdk/deps/test-kernel/Cargo.toml').read_text())
        self.assertEqual(runner['features'], {'external-entry': []})

    def test_ostd_test_base_keeps_its_original_entry_and_features(self):
        upstream = ROOT / 'kernel/asterinas'
        manifest = tomllib.loads(prepare.generated_manifest(upstream, 'ostd'))
        self.assertNotIn('permission-attr-smp-ktest', manifest['features'])
        self.assertNotIn('features', manifest['dependencies']['osdk-test-kernel'])
        self.assertNotIn('external-entry', json.dumps(manifest['features']))
        self.assertEqual(manifest['features']['default'], ['cvm_guest'])


class SourceVerifierEntry(unittest.TestCase):
    def test_runner_manifest_dispatch_preserves_exact_and_pristine_checks(self):
        # Original pinned upstream blob c22fa69cd833a11dd6116a8a8d1963a5d3bdf2f1.
        # Supply only the two Git reads; main still performs the real file,
        # mode, dispatch, insertion, blob comparison, and report operations.
        original = b'''[package]
name = "osdk-test-kernel"
description = "The OSTD-based kernel for running unit tests with OSDK."
readme = "README.md"
version.workspace = true
repository.workspace = true
license.workspace = true
edition.workspace = true

# See more keys and their definitions at https://doc.rust-lang.org/cargo/reference/manifest.html

[dependencies]
ostd.workspace = true
owo-colors.workspace = true

[lints]
workspace = true
'''
        upstream_blob = 'c22fa69cd833a11dd6116a8a8d1963a5d3bdf2f1'
        actual_blob = hashlib.sha1(f'blob {len(original)}\0'.encode() + original).hexdigest()
        self.assertEqual(actual_blob, upstream_blob)
        name = 'osdk/deps/test-kernel/Cargo.toml'
        current = (ROOT / 'kernel/asterinas' / name).read_bytes()
        with tempfile.TemporaryDirectory(prefix='permission-source-entry-') as directory:
            root = Path(directory)
            source = root / 'kernel/asterinas'
            manifest = source / name
            manifest.parent.mkdir(parents=True)
            (root / 'support').mkdir()
            (root / 'README.md').write_bytes(b'')
            (root / 'support/upstream-lock.json').write_bytes(
                (ROOT / 'support/upstream-lock.json').read_bytes())

            def git_read(argv, *, cwd):
                self.assertEqual(cwd, root)
                if argv == ['git', 'ls-tree', '-rz', source_verifier.PINNED_TREE]:
                    return f'100644 blob {upstream_blob}\t{name}\0'.encode()
                self.assertEqual(argv, ['git', 'cat-file', 'blob', upstream_blob])
                return original

            cases = ((False, current, True), (False, current + b'\n# unrelated edit\n', False),
                     (False, original, False), (True, current, False), (True, original, True))
            for pristine, content, passed in cases:
                with self.subTest(pristine=pristine, content=content, passed=passed):
                    manifest.write_bytes(content)
                    manifest.chmod(0o644)
                    output = io.StringIO()
                    argv = ['verify-source.py'] + (['--pristine'] if pristine else [])
                    with patch.object(source_verifier, 'ROOT', root), \
                            patch.object(source_verifier, 'SOURCE', source), \
                            patch.object(sys, 'argv', argv), \
                            patch.object(source_verifier.subprocess, 'check_output', side_effect=git_read), \
                            redirect_stdout(output):
                        status = source_verifier.main()
                    report = json.loads(output.getvalue())
                    self.assertEqual(status, 0 if passed else 1)
                    self.assertEqual(report['passed'], passed)
                    self.assertEqual(report['checked_files'], int(passed))
                    if not pristine and passed:
                        entry = report['downstream_manifests'][name]
                        self.assertEqual(entry['upstream_blob'], upstream_blob)
                        self.assertEqual(entry['derived_sha256'], hashlib.sha256(current).hexdigest())
                    if not passed:
                        self.assertEqual(len(report['errors']), 1)
                        self.assertIn(f'{name}: blob ', report['errors'][0])


class GuestOracle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='permission-smp-parser-fixture-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.guest = root / 'guest-001'
        self.guest.mkdir()
        self.raw = fixture_serial()
        (self.guest / 'serial.log').write_bytes(self.raw)
        self.kernel, self.bios, self.qemu = root / 'kernel', root / 'bios', root / 'qemu'
        for path in (self.kernel, self.bios, self.qemu):
            path.write_bytes(b'Parser fixture only, never executable: ' + path.name.encode())
        artifacts = {option: {'path': str(path), 'size': path.stat().st_size, 'sha256': checker.sha(path.read_bytes())}
                     for option, path in (('-kernel', self.kernel), ('-bios', self.bios))}
        requested = ['-kernel', str(self.kernel), '-append', 'loglevel=error earlycon console=ttyS0']
        argv = [str(self.qemu), *requested,
                '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(self.bios),
                '-m', '512M', '-smp', '2', '-nodefaults', '-no-user-config', '-no-reboot',
                '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'chardev:serial',
                '-chardev', f"stdio,id=serial,signal=off,logfile={self.guest / 'serial.log'}",
                '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
        self.record = {'crate': 'aster-core', 'ktest_profile': 'permission-attr-smp',
                       'profile': copy.deepcopy(checker.PROFILE), 'raw_exit_code': 33, 'timed_out': False,
                       'argv': argv, 'requested_osdk_args': requested, 'artifacts': artifacts,
                       'qemu_sha256': checker.sha(self.qemu.read_bytes()), 'serial_sha256': checker.sha(self.raw)}
        self.save()

    def save(self, record=None):
        (self.guest / 'qemu.json').write_text(json.dumps(record if record is not None else self.record))

    def test_parser_fixture_round_trip(self):
        self.assertEqual(checker.check_guest(self.guest)['passed'], 3)

    def test_profile_exit_and_command_tampering(self):
        variants = []
        for key, value in [('raw_exit_code', 0), ('timed_out', True), ('ktest_profile', 'default'), ('crate', 'ostd')]:
            changed = copy.deepcopy(self.record)
            changed[key] = value
            variants.append((key, changed))
        for label, operation in [
            ('actual_one_cpu', lambda d: d['argv'].__setitem__(d['argv'].index('-smp') + 1, '1')),
            ('claimed_one_cpu', lambda d: d['profile'].__setitem__('vcpus', 1)),
            ('extra_network', lambda d: d['argv'].extend(['-netdev', 'user,id=net0'])),
            ('extra_disk', lambda d: d['argv'].extend(['-drive', 'file=/tmp/disk'])),
            ('duplicate_smp', lambda d: d['argv'].extend(['-smp', '2'])),
            ('false_kernel_hash', lambda d: d['artifacts']['-kernel'].__setitem__('sha256', '0' * 64)),
            ('false_qemu_hash', lambda d: d.__setitem__('qemu_sha256', '0' * 64)),
            ('false_serial_hash', lambda d: d.__setitem__('serial_sha256', '0' * 64)),
        ]:
            changed = copy.deepcopy(self.record)
            operation(changed)
            variants.append((label, changed))
        for label, record in variants:
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.save(record)
                checker.check_guest(self.guest)

    def test_loaded_input_change_rejected(self):
        for path in (self.kernel, self.bios, self.qemu):
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                checker.check_guest(self.guest)
            path.write_bytes(original)

    def test_preserved_kernel_is_checked_against_original_record(self):
        archive = self.guest.parent / 'preserved-kernel'
        archive.write_bytes(self.kernel.read_bytes())
        self.kernel.write_bytes(b'later mutation overwrote the shared OSDK target')
        self.assertEqual(checker.check_guest(self.guest, kernel_path=archive)['passed'], 3)
        archive.write_bytes(b'wrong preserved kernel')
        with self.assertRaises(ValueError):
            checker.check_guest(self.guest, kernel_path=archive)


class ProfileAndFullDenominator(unittest.TestCase):
    def test_conflicting_smp_selector_rejected_before_build(self):
        with tempfile.TemporaryDirectory(prefix='permission-profile-parser-') as directory:
            output = Path(directory) / 'must-not-be-created'
            for extra in (['--crate', 'ostd'], ['--test-name', 'some_other_test']):
                result = subprocess.run(
                    [sys.executable, '-I', '-B', str(ROOT / 'support/build/ktest/run.py'),
                     '--permission-attr-smp', '--output', str(output), *extra],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                with self.subTest(extra=extra):
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(b'fixes the crate and complete test-name suffix', result.stderr)
                    self.assertFalse(output.exists())

    def test_full_core_requires_original_denominator_and_all_fourteen_names(self):
        required = sorted(full_checker.REQUIRED_CORE_TESTS)
        self.assertEqual(len(required), 14)
        with tempfile.TemporaryDirectory(prefix='permission-full-count-parser-') as directory:
            guest = Path(directory)
            for count, omit_required in ((252, False), (251, False), (252, True), (247, False), (243, False)):
                names = required + [f'aster_core::fixture::case_{index}' for index in range(count - len(required))]
                if omit_required:
                    names[0] = 'aster_core::fixture::replacement'
                lines = [f'[ktest runner] running {count} tests in 1 crates',
                         f'running {count} tests in crate "aster-core"']
                lines.extend('test ' + name + ' ... ok' for name in names)
                lines.extend([f'test result: ok. {count} passed; 0 failed; 0 filtered out.',
                              '[ktest runner] All crates tested.'])
                raw = ('\n'.join(lines) + '\n').encode()
                (guest / 'serial.log').write_bytes(raw)
                (guest / 'qemu.json').write_text(json.dumps({
                    'crate': 'aster-core', 'raw_exit_code': 33, 'timed_out': False,
                    'serial_sha256': checker.sha(raw)}))
                with self.subTest(count=count, omit_required=omit_required):
                    if count == 252 and not omit_required:
                        self.assertEqual(full_checker.check_guest(guest, 'aster-core')['passed'], 252)
                    else:
                        with self.assertRaises(ValueError):
                            full_checker.check_guest(guest, 'aster-core')


if __name__ == '__main__':
    unittest.main()
