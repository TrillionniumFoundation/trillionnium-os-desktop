"""Reject incomplete or contradictory UDP evidence without executing a socket."""
import gzip
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('udp_local_guest', HERE / 'run_udp_local_error_guest.py')
udp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(udp)
NONCE = 'a5' * 32


def guest_bytes(payload=None):
    return (b'ordinary guest boot\n' + (udp.BEGIN + NONCE + '\n').encode()
            + (udp.expected_output() if payload is None else payload)
            + (udp.END + NONCE + ' exit=0\n' + udp.BOOT + '\n').encode())


class UdpOracleTests(unittest.TestCase):
    def test_actual_linux_transcript_is_complete(self):
        raw = udp.expected_output()
        self.assertEqual(udp.sha(raw), udp.EXPECTED_SHA)
        self.assertEqual(len(raw.splitlines()), 49)
        self.assertEqual(raw.count(b' passed [got '), 43)
        self.assertEqual(raw.count(b' tests passed, 0 tests failed\n'), 6)
        self.assertTrue(udp.evaluate_reference(b'', raw, 0, False)['passed'])
        self.assertTrue(udp.evaluate_guest(guest_bytes(), 33, False, NONCE)['passed'])

    def test_linux_needs_actual_zero_exit_no_timeout_and_exact_streams(self):
        raw = udp.expected_output()
        for stdout, stderr, code, timed_out in (
                (b'noise', raw, 0, False), (b'', raw, 1, False),
                (b'', raw, -9, False), (b'', raw, False, False),
                (b'', raw, None, False), (b'', raw, 0, True),
                (b'', raw, 0, None), (b'', raw + b'ignored\n', 0, False)):
            with self.subTest(code=code, timed_out=timed_out, stdout=stdout):
                self.assertFalse(udp.evaluate_reference(stdout, stderr, code, timed_out)['passed'])

    def test_no_summary_only_count_only_or_inconsistent_pass(self):
        raw = udp.expected_output()
        lines = raw.splitlines(keepends=True)
        mutations = {
            'summary only': b''.join(line for line in lines if b' summary:' in line),
            'missing check': b''.join(lines[1:]),
            'duplicate check': lines[0] + raw,
            'same count wrong check': lines[0] + lines[0] + b''.join(lines[2:]),
            'failed check but green summary': raw.replace(b' passed [got ', b' failed [got ', 1),
            'failed summary': raw.replace(b'11 tests passed, 0 tests failed', b'10 tests passed, 1 tests failed'),
            'reordered': b''.join([lines[1], lines[0], *lines[2:]]),
            'extra malformed check': raw + b'test_missing: truncated\n',
            'skip': raw + b'test_self_delivery_has_no_error skipped: forced\n',
            'fatal setup': raw + b'fatal error: setup failed\n',
        }
        for name, payload in mutations.items():
            with self.subTest(name=name):
                self.assertFalse(udp.evaluate_reference(b'', payload, 0, False)['passed'])
                self.assertFalse(udp.evaluate_guest(guest_bytes(payload), 33, False, NONCE)['passed'])

    def test_guest_nonce_exit_boot_order_and_kernel_failure(self):
        raw = guest_bytes()
        changes = (
            raw.replace(NONCE.encode(), b'00' * 32, 1),
            raw.replace(b' exit=0', b' exit=1'),
            raw + (udp.END + NONCE + ' exit=0\n').encode(),
            raw.replace((udp.BOOT + '\n').encode(), b''),
            (udp.BOOT + '\n').encode() + raw,
            raw.replace((udp.BEGIN + NONCE + '\n').encode(), b''),
            udp.expected_output() + (udp.BEGIN + NONCE + '\n' + udp.END + NONCE
                                     + ' exit=0\n' + udp.BOOT + '\n').encode(),
            raw + b'panicked at kernel.rs\n', raw + b'HEPTA_KTRACE_V2 record\n',
        )
        for data in changes:
            with self.subTest(data=data[-100:]):
                self.assertFalse(udp.evaluate_guest(data, 33, False, NONCE)['passed'])
        for code, timed_out in ((0, False), (-9, False), (None, False), (True, False), (33, True), (33, None)):
            self.assertFalse(udp.evaluate_guest(raw, code, timed_out, NONCE)['passed'])

    def test_guest_only_normalizes_terminal_escapes_and_line_endings(self):
        raw = b'\x1b[32m' + guest_bytes().replace(b'\n', b'\r\n') + b'\x1b[0m'
        self.assertTrue(udp.evaluate_guest(raw, 33, False, NONCE)['passed'])

    def test_initramfs_preserves_original_entries_and_captures_actual_exit(self):
        original = [
            ('init', [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
             b'#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n'),
            ('etc/hosts', [2, 0o100644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], b'unchanged\n'),
        ]
        archive = gzip.compress(udp.common.pack(original), mtime=0)
        parsed = udp.common.unpack(gzip.decompress(udp.build_initramfs(archive, b'probe bytes', NONCE)))
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[1][2], b'unchanged\n')
        self.assertEqual(parsed[2][0], udp.PROBE_PATH)
        self.assertEqual(parsed[2][2], b'probe bytes')
        self.assertIn(b'else udp_exit=$?; fi', parsed[0][2])
        self.assertIn(NONCE.encode(), parsed[0][2])
        with self.assertRaises(ValueError):
            udp.build_initramfs(archive, b'probe', 'injected shell text')
        with self.assertRaises(ValueError):
            udp.build_initramfs(gzip.compress(udp.common.pack(parsed)), b'probe', NONCE)

    def test_static_elf_rejects_dynamic_linking_and_malformed_tables(self):
        data = bytearray(176)
        data[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<HH', data, 16, 2, 62)
        struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 1)
        struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, len(data), len(data), 4096)
        udp.require_static_elf(data)
        interp = bytearray(data)
        struct.pack_into('<I', interp, 64, 3)
        with self.assertRaises(ValueError):
            udp.require_static_elf(interp)
        needed = bytearray(data)
        struct.pack_into('<IIQQQQQQ', needed, 64, 2, 4, 120, 0, 0, 32, 32, 8)
        struct.pack_into('<qQ', needed, 120, 1, 1)
        with self.assertRaises(ValueError):
            udp.require_static_elf(needed)
        for invalid in (b'not ELF', data[:80]):
            with self.assertRaises(ValueError):
                udp.require_static_elf(invalid)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'existing'
            out.mkdir()
            original = b'{"original": true}\n'
            (out / 'result.json').write_bytes(original)
            with self.assertRaises(ValueError):
                udp.main(['reference', '--expected-source-head', 'a' * 40,
                          '--expected-source-tree', 'b' * 40, '--output', str(out)])
            self.assertEqual((out / 'result.json').read_bytes(), original)

    def test_linux_record_rechecks_actual_bytes_exit_and_elf(self):
        # This is a synthetic parser fixture, never executed or represented as
        # a compiler/kernel result. The actual transcript is the pinned input.
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            elf = bytearray(120)
            elf[:7] = b'\x7fELF\x02\x01\x01'
            struct.pack_into('<HH', elf, 16, 2, 62)
            struct.pack_into('<Q', elf, 32, 64)
            struct.pack_into('<HH', elf, 54, 56, 1)
            struct.pack_into('<IIQQQQQQ', elf, 64, 1, 5, 0, 0, 0, 120, 120, 4096)
            digest = udp.sha(elf)
            snapshot = {'head': 'a' * 40, 'tree': 'b' * 40, 'files': {}}
            code = {'returncode': 0, 'timed_out': False, 'process_group_cleanup_completed': True}
            for name, data in (('probe.elf', elf), ('probe.sha256', f'{digest}  probe.elf\n'.encode()),
                               ('compile.stdout.log', b''), ('compile.stderr.log', b''),
                               ('process.stdout.log', b''), ('process.stderr.log', udp.expected_output())):
                (out / name).write_bytes(data)
            for prefix in ('compile', 'process'):
                (out / (prefix + '-execution.json')).write_text(json.dumps(code))
                (out / (prefix + '-invocation.json')).write_text('{"synthetic_unit_fixture":true}\n')
            frozen = {'source': snapshot, 'probe_sha256': digest, 'expected_stderr_sha256': udp.EXPECTED_SHA}
            for name, key in (('compile-execution.json', 'compile_execution_sha256'),
                              ('compile-invocation.json', 'compile_invocation_sha256'),
                              ('compile.stdout.log', 'compile_stdout_sha256'),
                              ('compile.stderr.log', 'compile_stderr_sha256')):
                frozen[key] = udp.sha((out / name).read_bytes())
            (out / 'input.json').write_text(json.dumps(frozen))
            receipt = {'schema': 'a06.udp-local-linux.v1', 'passed': True,
                       'source_inputs_unchanged': True, 'probe_inputs_unchanged': True,
                       'source': snapshot, 'probe_sha256': digest, 'compile': code, 'process': code,
                       'input_sha256': udp.sha((out / 'input.json').read_bytes()),
                       'stdout_sha256': udp.sha(b''), 'stderr_sha256': udp.EXPECTED_SHA,
                       'process_invocation_sha256': udp.sha((out / 'process-invocation.json').read_bytes())}
            (out / 'result.json').write_text(json.dumps(receipt))
            self.assertEqual(udp.load_reference(out, digest, snapshot)[0], bytes(elf))
            for name, changed in (('probe.elf', bytes(elf) + b'changed'),
                                   ('process.stderr.log', udp.expected_output()[:-1]),
                                   ('process-execution.json', json.dumps({**code, 'returncode': 1}).encode()),
                                   ('compile.stderr.log', b'unrecorded compiler warning')):
                path = out / name
                original = path.read_bytes()
                path.write_bytes(changed)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    udp.load_reference(out, digest, snapshot)
                path.write_bytes(original)
            with self.assertRaises(ValueError):
                udp.load_reference(out, '0' * 64, snapshot)
            with self.assertRaises(ValueError):
                udp.load_reference(out, digest, {**snapshot, 'tree': 'c' * 40})


if __name__ == '__main__':
    unittest.main(verbosity=2)
