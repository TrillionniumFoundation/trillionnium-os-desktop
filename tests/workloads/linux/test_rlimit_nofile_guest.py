#!/usr/bin/env python3
"""Negative verdict/input regressions and real owned-child cleanup checks.

Parser/CPIO fixtures are not guest execution or Linux compatibility evidence.
The actual qualification runs the compiled C ELF through the two runner modes.
"""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    'nofile_guest_runner', Path(__file__).with_name('run_rlimit_nofile_guest.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def linux_lines():
    return [*(f'NOFILE_CASE name={name} result=PASS line=0' for name in runner.CASE_ORDER),
            runner.COMPLETE]


def raw(lines):
    return ('\n'.join(lines) + '\n').encode()


class VerdictTests(unittest.TestCase):
    def complete(self):
        return [*linux_lines(), runner.PROCESS_EXIT, runner.BOOT_MARKER]

    def verdict(self, lines, code=33, timed_out=False):
        return runner.evaluate_guest(raw(lines), code, timed_out)['passed']

    def test_fixed_37_case_denominator_matches_the_c_probe(self):
        source = Path(__file__).with_name('rlimit_nofile_probe.c').read_text()
        body = source.split('static const struct test_case cases[] = {', 1)[1].split('};', 1)[0]
        self.assertEqual(tuple(re.findall(r'CASE\((\w+)\)', body)), runner.CASE_ORDER)
        self.assertEqual(len(runner.CASE_ORDER), 37)
        self.assertEqual(runner.CASE_COUNT, 37)
        self.assertTrue(self.verdict(self.complete()))

    def test_qemu_status_alone_never_qualifies_the_guest(self):
        for code in (0, 1, None, True, 33.0, '33'):
            with self.subTest(code=code):
                self.assertFalse(self.verdict(self.complete(), code))
        for timed_out in (True, 0, None):
            self.assertFalse(self.verdict(self.complete(), timed_out=timed_out))
        self.assertFalse(self.verdict([runner.BOOT_MARKER]))

    def test_missing_duplicate_unknown_reordered_and_skipped_cases_rejected(self):
        mutations = [self.complete()[1:], [*self.complete(), self.complete()[0]]]
        for replacement in (self.complete()[1], 'NOFILE_CASE name=unknown result=PASS line=0',
                            self.complete()[0].replace('PASS', 'SKIP'),
                            self.complete()[0] + ' unchecked=yes'):
            mutations.append([replacement, *self.complete()[1:]])
        reordered = self.complete()
        reordered[0], reordered[1] = reordered[1], reordered[0]
        mutations.append(reordered)
        for lines in mutations:
            with self.subTest(lines=lines[:2]):
                self.assertFalse(self.verdict(lines))

    def test_failed_case_or_assertion_cannot_be_overridden_by_a_success_summary(self):
        for replacement in ('FAIL line=17', 'PASS line=17', 'PASS line=0 signal=14'):
            lines = self.complete()
            lines[0] = lines[0].replace('PASS line=0', replacement)
            self.assertFalse(self.verdict(lines))
        for diagnostic in ('NOFILE_ASSERT line=17 expression=x errno=24',
                           'NOFILE_SETUP fork/wait: resource unavailable'):
            self.assertFalse(self.verdict([diagnostic, *self.complete()]))

    def test_signalled_case_is_complete_red_with_its_actual_signal(self):
        lines = self.complete()
        lines[0] = lines[0].replace('PASS line=0', 'FAIL line=0 signal=14')
        lines[37] = 'NOFILE_COMPLETE total=37 passed=36 failed=1'
        lines[38] = 'NOFILE_PROCESS_EXIT=1'
        result = runner.evaluate_guest(raw(lines), 33, False)
        self.assertTrue(result['cases_complete'])
        self.assertTrue(result['summary_consistent'])
        self.assertEqual(result['cases'][0]['signal'], 14)
        self.assertEqual(result['probe_exit'], 1)
        self.assertFalse(result['passed'])
        for sig in (0, 65):
            broken = lines.copy()
            broken[0] = broken[0].replace('signal=14', f'signal={sig}')
            self.assertFalse(runner.evaluate_probe(raw(broken))['cases_complete'])

    def test_inconsistent_duplicate_and_out_of_order_markers_rejected(self):
        for summary in ('NOFILE_COMPLETE total=36 passed=36 failed=0',
                        'NOFILE_COMPLETE total=37 passed=36 failed=1',
                        'NOFILE_COMPLETE total=37 passed=37 failed=0 extra=yes'):
            lines = self.complete()
            lines[37] = summary
            self.assertFalse(self.verdict(lines))
        for marker in (runner.COMPLETE, runner.PROCESS_EXIT, runner.BOOT_MARKER):
            self.assertFalse(self.verdict([*self.complete(), marker]))
        for left, right in ((0, 37), (37, 38), (38, 39)):
            lines = self.complete()
            lines[left], lines[right] = lines[right], lines[left]
            self.assertFalse(self.verdict(lines))

    def test_probe_status_and_kernel_panics_cannot_be_masked_by_qemu_33(self):
        for probe_exit in ('1', '-14', '0 extra=yes'):
            lines = self.complete()
            lines[38] = f'NOFILE_PROCESS_EXIT={probe_exit}'
            self.assertFalse(self.verdict(lines))
        for panic in ('Kernel panic', 'thread panicked at a source file', 'fatal exception'):
            self.assertFalse(self.verdict([*self.complete(), panic]))

    def test_linux_reference_requires_exact_stdout_empty_stderr_and_real_exit(self):
        stdout = raw(linux_lines())
        self.assertTrue(runner.evaluate_reference(stdout, b'', 0, False)['passed'])
        for code in (1, -14, None, False, 0.0, '0'):
            self.assertFalse(runner.evaluate_reference(stdout, b'', code, False)['passed'])
        for changed in (stdout[:-1], stdout + b'ignored output\n', raw(linux_lines()[1:]),
                        stdout.replace(b'PASS line=0', b'FAIL line=17', 1)):
            self.assertFalse(runner.evaluate_reference(changed, b'', 0, False)['passed'])
        self.assertFalse(runner.evaluate_reference(stdout, b'warning\n', 0, False)['passed'])
        self.assertFalse(runner.evaluate_reference(stdout, b'', 0, True)['passed'])


class InputTests(unittest.TestCase):
    def test_oversize_serial_failure_keeps_actual_qemu_exit_without_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            serial = Path(directory) / 'serial.log'
            with serial.open('xb') as output:
                output.truncate(runner.SERIAL_LIMIT + 1)
            report = {'passed': False}
            with self.assertRaisesRegex(ValueError, 'input exceeds size limit'):
                runner.record_guest_run(report, serial, 33, False, 1.25)
            self.assertEqual(report['qemu_exit'], 33)
            self.assertIs(report['timed_out'], False)
            self.assertEqual(report['elapsed_seconds'], 1.25)
            self.assertIs(report['passed'], False)

    def reference(self, root):
        # Controlled parser fixture only; run_guest additionally requires a static ELF.
        probe, stdout, stderr = b'ELF identity fixture; never execute', raw(linux_lines()), b''
        digest = runner.sha(probe)
        before = {'schema': 'a04.rlimit-nofile-linux.v1', 'probe_sha256': digest}
        before_bytes = (json.dumps(before) + '\n').encode()
        receipt = {**before, 'passed': True, 'probe_inputs_unchanged': True,
                   'runner_inputs_unchanged': True, 'process_group_cleanup_completed': True,
                   'frozen_input_sha256': runner.sha(before_bytes), 'process_exit': 0,
                   'timed_out': False, 'stdout_sha256': runner.sha(stdout),
                   'stderr_sha256': runner.sha(stderr)}
        for name, data in (('probe.elf', probe), ('stdout.log', stdout), ('stderr.log', stderr),
                           ('input.json', before_bytes), ('exit-code.txt', b'0\n'),
                           ('probe.sha256', f'{digest}  probe.elf\n'.encode())):
            (root / name).write_bytes(data)
        (root / 'result.json').write_text(json.dumps(receipt))
        return probe, digest, receipt

    def test_linux_elf_and_pre_execution_digest_cannot_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe, digest, _ = self.reference(root)
            self.assertEqual(runner.load_reference(root, digest)[0], probe)
            (root / 'probe.elf').write_bytes(b'changed after reference execution')
            with self.assertRaisesRegex(ValueError, 'SHA256 differs'):
                runner.load_reference(root, digest)
            self.reference(root)
            (root / 'probe.sha256').write_text(f'{"0" * 64}  probe.elf\n')
            with self.assertRaisesRegex(ValueError, 'pre-execution Linux digest differs'):
                runner.load_reference(root, digest)

    def test_failed_or_incomplete_reference_receipt_rejected(self):
        for field in ('passed', 'probe_inputs_unchanged', 'runner_inputs_unchanged',
                      'process_group_cleanup_completed'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, digest, receipt = self.reference(root)
                receipt[field] = False
                (root / 'result.json').write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, 'Linux reference did not pass'):
                    runner.load_reference(root, digest)

    def test_rehashed_bad_linux_logs_cannot_be_approved_by_receipt_boolean(self):
        for kind in ('missing_case', 'stderr', 'exit', 'timeout', 'input'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, digest, receipt = self.reference(root)
                if kind == 'missing_case':
                    data = raw(linux_lines()[1:])
                    (root / 'stdout.log').write_bytes(data)
                    receipt['stdout_sha256'] = runner.sha(data)
                elif kind == 'stderr':
                    data = b'NOFILE_ASSERT line=17 expression=x errno=24\n'
                    (root / 'stderr.log').write_bytes(data)
                    receipt['stderr_sha256'] = runner.sha(data)
                elif kind == 'exit':
                    receipt['process_exit'] = 1
                    (root / 'exit-code.txt').write_bytes(b'1\n')
                elif kind == 'timeout':
                    receipt['timed_out'] = True
                else:
                    data = json.dumps({'schema': receipt['schema'], 'probe_sha256': '0' * 64}).encode()
                    (root / 'input.json').write_bytes(data)
                    receipt['frozen_input_sha256'] = runner.sha(data)
                (root / 'result.json').write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    runner.load_reference(root, digest)

    def test_raw_linux_logs_and_actual_exit_record_are_bound_to_receipt(self):
        for name, data in (('stdout.log', b'replaced\n'), ('stderr.log', b'replaced\n'),
                           ('exit-code.txt', b'1\n'), ('input.json', b'{}')):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, digest, _ = self.reference(root)
                (root / name).write_bytes(data)
                with self.assertRaises(ValueError):
                    runner.load_reference(root, digest)

    def test_existing_product_source_gate_rejects_other_heads_and_failed_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head, tree = '1' * 40, '2' * 40
            kernel = b'\x7fELF\x02\x01' + b'\0' * 12 + b'\x03\x00' + b'product identity fixture'
            snapshot = {'head': head, 'tree': tree, 'files': {'tracked-file': '3' * 64}}
            receipt = {'schema': 'a06.g1-queryabi-product-candidate.v1', 'passed': True,
                       'source_inputs_unchanged': True, 'stage': 'complete',
                       'product_wrapper_exit': 0, 'product_boot_raw_exit': 33,
                       'qemu_exit': 33, 'timed_out': False, 'source_head': head,
                       'source_tree': tree, 'source_file_count': 1,
                       'kernel_elf_sha256': runner.sha(kernel)}
            (root / 'product-kernel.elf').write_bytes(kernel)
            (root / 'result.json').write_text(json.dumps(receipt))
            for name in ('source-before.json', 'source-after-boot.json', 'source-after-guest.json'):
                (root / name).write_text(json.dumps(snapshot))
            self.assertEqual(runner.common.product_input(root, head, tree)[0], kernel)
            for checked_head, checked_tree in (('4' * 40, tree), (head, '4' * 40)):
                with self.assertRaisesRegex(ValueError, 'reviewed source identity'):
                    runner.common.product_input(root, checked_head, checked_tree)
            receipt['passed'] = False
            (root / 'result.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'product build/boot gate did not pass'):
                runner.common.product_input(root, head, tree)
            receipt['passed'] = True
            (root / 'result.json').write_text(json.dumps(receipt))
            snapshot['files']['tracked-file'] = '4' * 64
            (root / 'source-after-guest.json').write_text(json.dumps(snapshot))
            with self.assertRaisesRegex(ValueError, 'source snapshots changed'):
                runner.common.product_input(root, head, tree)


class PackagingTests(unittest.TestCase):
    def initrd(self, init=b'set -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n', extra=()):
        fields = [1, 0o100755, 7, 8, 1, 123, 0, 2, 3, 4, 5, 0, 0]
        return gzip.compress(runner.common.pack(
            [('init', fields, init), ('original', fields, b'preserved'), *extra]), mtime=0)

    def test_all_original_fields_and_payloads_survive_except_injected_init_size(self):
        original = self.initrd()
        result = runner.build_initramfs(original, b'probe fixture')
        self.assertEqual(result, runner.build_initramfs(original, b'probe fixture'))
        before = {name: (fields, data) for name, fields, data in
                  runner.common.unpack(gzip.decompress(original))}
        after = {name: (fields, data) for name, fields, data in
                 runner.common.unpack(gzip.decompress(result))}
        self.assertEqual(set(after), set(before) | {runner.PROBE_PATH})
        self.assertEqual(after['original'], before['original'])
        self.assertEqual(after[runner.PROBE_PATH][1], b'probe fixture')
        for index in range(13):
            if index != 6:
                self.assertEqual(after['init'][0][index], before['init'][0][index])
        init = after['init'][1]
        self.assertIn(b'set -eu', init)
        self.assertIn(b'if /bin/rlimit-nofile-probe; then', init)
        self.assertIn(b'nofile_probe_exit=$?', init)
        self.assertIn(b'echo "NOFILE_PROCESS_EXIT=$nofile_probe_exit"', init)
        self.assertLess(init.index(b'NOFILE_PROCESS_EXIT'), init.index(b'TRILLIONNIUM_A01_BOOT_OK'))

    def test_missing_ambiguous_unchecked_or_preinjected_init_rejected(self):
        for init in (b'set -eu\n', b'echo "TRILLIONNIUM_A01_BOOT_OK"\n',
                     b'set -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\necho "TRILLIONNIUM_A01_BOOT_OK"\n'):
            with self.assertRaises(ValueError):
                runner.build_initramfs(self.initrd(init), b'probe fixture')
        fields = [2, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        for name, data in ((runner.PROBE_PATH, b'already present'),
                           ('./init', b'set -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n')):
            with self.assertRaises(ValueError):
                runner.build_initramfs(self.initrd(extra=[(name, fields, data)]), b'probe fixture')


class ProcessTests(unittest.TestCase):
    def test_all_real_leader_terminal_states_use_anchored_cleanup(self):
        # Exercise this caller with real owned Linux children. The common guard
        # separately tests descendant writers and loss of the WNOWAIT anchor.
        programs = (("import os; os._exit(0)", 0, False),
                    ("import os; os._exit(7)", 7, False),
                    ("import os, signal; os.kill(os.getpid(), signal.SIGALRM)", -signal.SIGALRM, False),
                    ("import signal; signal.pause()", None, True))
        terminate = runner.groups.terminate_group
        for source, expected, timeout in programs:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                observed = []

                def checked_cleanup(group):
                    observed.append((group.process.pid, group.observe_exit()))
                    return terminate(group)

                with patch.object(runner.groups, 'terminate_group', side_effect=checked_cleanup), \
                     patch.object(runner.groups, 'GROUP_GRACE_SECONDS', 0.02):
                    code, timed_out = runner.reference_process(
                        [sys.executable, '-I', '-B', '-c', source], Path(directory),
                        timeout_seconds=0.1 if timeout else 5)
                self.assertEqual(timed_out, timeout)
                self.assertEqual(len(observed), 1)
                if expected is not None:
                    self.assertEqual(code, expected)
                    self.assertIsNotNone(observed[0][1])
                else:
                    self.assertLess(code, 0)
                with self.assertRaises(ChildProcessError):
                    os.waitid(os.P_PID, observed[0][0], os.WEXITED | os.WNOWAIT | os.WNOHANG)

    def test_missing_waitable_anchor_rejects_before_spawn(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runner.groups, 'child_anchor_available', return_value=False), \
             patch.object(runner.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(runner.groups.GateError, 'waitable_child_anchor_required'):
                runner.reference_process(['must-not-run'], Path(directory))
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
