"""Negative controls for the full-profile gate, never guest qualification."""
import base64
import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('a04_full_under_test', HERE / 'run_full_ubuntu_profile.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def frame(case, *, stdout=None, stderr=b'', code=0):
    name = case['id']
    stdout = m.json_bytes(case['expected_facts']).replace(b'\n', b'') + b'\n' if stdout is None else stdout
    lines = ['A04_FULL_BEGIN=' + name]
    for channel, data in (('STDOUT', stdout), ('STDERR', stderr)):
        encoded = base64.b64encode(data).decode()
        lines.extend('A04_FULL_' + channel + '=' + name + ':' + encoded[index:index + 76]
                     for index in range(0, len(encoded), 76))
    lines.append('A04_FULL_END=' + name + ':' + str(code) + ':' + str(len(stdout))
                 + ':' + m.sha(stdout) + ':' + str(len(stderr)) + ':' + m.sha(stderr))
    return '\n'.join(lines) + '\n'


def serial(profile, *, frames=None, complete='A04_FULL_COMPLETE=32:0', process='A04_FULL_PROCESS_EXIT=0'):
    if frames is None:
        frames = [frame(case) for case in profile['cases']]
    return (''.join(frames) + complete + '\n' + process + '\n' + m.common.BOOT_MARKER + '\n').encode()


def fixture_image():
    init = b'#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_BOOT_OK"\n'
    entries = [m.new_entry('bin', stat.S_IFDIR | 0o755, b'', 10),
               m.new_entry('init', stat.S_IFREG | 0o755, init, 11),
               m.new_entry('bin/busybox', stat.S_IFREG | 0o755, b'original fixture bytes', 12),
               m.new_entry('bin/sh', stat.S_IFLNK | 0o777, b'busybox', 13)]
    entries[0][1][2], entries[0][1][3], entries[0][1][5] = 17, 23, 31415
    original = gzip.compress(m.common.pack(entries), mtime=0)
    data = b'one exact runtime file\n'
    manifest = {'schema': 'a04.ubuntu-full-rootfs.v1', 'file_count': 1, 'regular_bytes': len(data),
                'files': [{'path': '/usr/lib/a04-fixture', 'mode': 0o444,
                           'sha256': m.sha(data), 'bytes': len(data)}]}
    files = {'/usr/lib/a04-fixture': (0o444, data)}
    script = b'#!/bin/sh\nexit 1\n'
    image = m.merge_image(original, files, script)
    return original, files, manifest, script, image


class ContractAndObservationTests(unittest.TestCase):
    def setUp(self):
        self.profile = m.contract()
        self.case = self.profile['cases'][0]
        self.good = json.dumps(self.case['expected_facts'], separators=(',', ':')).encode() + b'\n'

    def test_complete_fixed_matrix_includes_all_python_and_tokio_facts(self):
        self.assertEqual(tuple(case['id'] for case in self.profile['cases']), m.CASE_ORDER)
        self.assertEqual(len(m.CASE_ORDER), 32)
        tokio = next(case for case in self.profile['cases'] if case['id'] == 'rust_tokio')
        self.assertEqual(tokio['expected_facts']['counter'], 4000)
        self.assertEqual(tokio['expected_facts']['std_threads'], 4)
        self.assertEqual(tokio['expected_facts']['tokio_tasks'], 16)
        self.assertTrue(tokio['expected_facts']['unix_socket'])
        self.assertTrue(tokio['expected_facts']['async_fs'])
        self.assertTrue(m.evaluate_case(self.case, self.good, b'', 0, False)['passed'])

    def test_case_requires_real_integer_zero_no_timeout_no_stderr(self):
        for code, timeout, stderr in [(False, False, b''), (True, False, b''), (1, False, b''),
                                      (0, True, b''), (0, 0, b''), (0, False, b'warning\n')]:
            with self.subTest(code=code, timeout=timeout, stderr=stderr):
                self.assertFalse(m.evaluate_case(self.case, self.good, stderr, code, timeout)['passed'])

    def test_wrong_fact_types_and_values_cannot_pass(self):
        for value in (1, False, 'true', None):
            facts = dict(self.case['expected_facts'], ok=value)
            raw = json.dumps(facts).encode() + b'\n'
            self.assertFalse(m.evaluate_case(self.case, raw, b'', 0, False)['passed'])
        facts = copy.deepcopy(self.case['expected_facts'])
        key = next(key for key in facts if key != 'ok')
        facts[key] = 'changed'
        self.assertFalse(m.evaluate_case(self.case, json.dumps(facts).encode() + b'\n', b'', 0, False)['passed'])

    def test_ambiguous_or_extra_stdout_is_rejected(self):
        for raw in (b'', self.good + b'\n', self.good + self.good, b'{"ok":true,"ok":false}\n',
                    b'{"ok":true,"x":NaN}\n', b'\xff\n', b'trace\n' + self.good):
            with self.subTest(raw=raw[:40]):
                self.assertFalse(m.evaluate_case(self.case, raw, b'', 0, False)['passed'])

    def test_reducing_contract_or_inserting_shell_tokens_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'contract.json'
            bad = copy.deepcopy(self.profile)
            bad['cases'].pop()
            path.write_bytes(m.json_bytes(bad))
            with mock.patch.object(m, 'PROFILE_PATH', path), self.assertRaises(ValueError):
                m.contract()
            bad = copy.deepcopy(self.profile)
            bad['cases'][0]['argv'][0] = '/bin/false;touch'
            path.write_bytes(m.json_bytes(bad))
            with mock.patch.object(m, 'PROFILE_PATH', path), self.assertRaises(ValueError):
                m.contract()

    def test_qemu33_requires_every_case_and_exact_completion(self):
        raw = serial(self.profile)
        self.assertTrue(m.evaluate_guest(raw, 33, False, self.profile)['passed'])
        for code, timeout in [(0, False), (1, False), (True, False), (33, True), (33, 0)]:
            self.assertFalse(m.evaluate_guest(raw, code, timeout, self.profile)['passed'])
        bad = serial(self.profile, process='A04_FULL_PROCESS_EXIT=1')
        result = m.evaluate_guest(bad, 33, False, self.profile)
        self.assertFalse(result['passed'])
        self.assertEqual(result['process_exit'], 1)

    def test_each_missing_case_keeps_the_full_denominator(self):
        frames = [frame(case) for case in self.profile['cases']]
        for index in range(32):
            with self.subTest(case=index):
                raw = serial(self.profile, frames=frames[:index] + frames[index + 1:])
                result = m.evaluate_guest(raw, 33, False, self.profile)
                self.assertFalse(result['passed'])
                self.assertEqual(result['required_cases'], 32)

    def test_duplicate_reordered_and_unknown_cases_are_rejected(self):
        frames = [frame(case) for case in self.profile['cases']]
        variants = [frames + [frames[-1]], [frames[1], frames[0], *frames[2:]],
                    [frames[0].replace('dynamic.async_fd', 'unknown.case'), *frames[1:]]]
        for variant in variants:
            self.assertFalse(m.evaluate_guest(serial(self.profile, frames=variant), 33, False, self.profile)['passed'])

    def test_byte_frames_survive_kernel_logs_but_not_tampering(self):
        raw = serial(self.profile)
        noisy = b'\x1b[32m[    1.0] kernel syscall diagnostic\x1b[0m\n'.join(raw.splitlines(keepends=True))
        self.assertTrue(m.evaluate_guest(noisy, 33, False, self.profile)['passed'])
        lines = raw.splitlines(keepends=True)
        index = next(index for index, line in enumerate(lines) if line.startswith(b'A04_FULL_STDOUT='))
        for changed in (lines[:index] + lines[index + 1:],
                        lines[:index] + [lines[index], lines[index]] + lines[index + 1:]):
            self.assertFalse(m.evaluate_guest(b''.join(changed), 33, False, self.profile)['passed'])
        changed = list(lines)
        changed[index] = changed[index].replace(b':', b':!', 1)
        self.assertFalse(m.evaluate_guest(b''.join(changed), 33, False, self.profile)['passed'])

    def test_nonempty_stderr_and_bad_real_exit_fail_inside_valid_frames(self):
        for options in ({'stderr': b'actual warning\n'}, {'code': 1}, {'stdout': b'{"ok":true}\n'}):
            frames = [frame(self.profile['cases'][0], **options)] + [frame(case) for case in self.profile['cases'][1:]]
            result = m.evaluate_guest(serial(self.profile, frames=frames), 33, False, self.profile)
            self.assertFalse(result['passed'])
            self.assertTrue(result['cases_complete'])

    def test_over_bound_application_frames_stop_buffering_and_fail(self):
        frames = [frame(case) for case in self.profile['cases']]
        oversized = 'A04_FULL_STDOUT=' + self.case['id'] + ':' + 'A' * (2 * m.MAX_CASE_BYTES) + '\n'
        frames[0] = frames[0].replace('A04_FULL_END=', oversized * 2 + 'A04_FULL_END=', 1)
        result = m.evaluate_guest(serial(self.profile, frames=frames), 33, False, self.profile)
        self.assertFalse(result['passed'])
        self.assertEqual(result['anomalies'].count('application byte frame exceeds bound'), 1)
        self.assertEqual(result['required_cases'], 32)

    def test_panic_and_duplicate_out_of_order_completion_fail(self):
        raw = serial(self.profile)
        variants = [b'Kernel panic\n' + raw, raw + b'A04_FULL_PROCESS_EXIT=0\n',
                    raw + b'A04_FULL_UNKNOWN=1\n',
                    raw.replace(b'A04_FULL_COMPLETE=32:0\n', b''),
                    raw.replace(b'A04_FULL_COMPLETE=32:0\nA04_FULL_PROCESS_EXIT=0\n',
                                b'A04_FULL_PROCESS_EXIT=0\nA04_FULL_COMPLETE=32:0\n')]
        for variant in variants:
            self.assertFalse(m.evaluate_guest(variant, 33, False, self.profile)['passed'])

    def test_guest_program_bounds_all_commands_and_preserves_each_actual_exit(self):
        script = m.guest_script(self.profile).decode()
        self.assertEqual(script.count('if /bin/busybox timeout -s KILL 45 '), 32)
        self.assertEqual(script.count('case_exit=$?'), 32)
        self.assertEqual(script.count('A04_FULL_END='), 32)
        self.assertNotIn('--proven-only', script)
        self.assertNotIn('--rust auto', script)
        for case in self.profile['cases']:
            self.assertIn(' '.join(case['argv']), script)


class ImageAndRuntimeTests(unittest.TestCase):
    def test_complete_runtime_uses_explicit_bound_without_expanding_small_probe_default(self):
        original, files, manifest, script, _ = fixture_image()
        name = '/usr/lib/a04-fixture'
        data = b'x' * (17 * 1024 * 1024)
        files[name] = (0o444, data)
        manifest['regular_bytes'] = len(data)
        manifest['files'][0].update(bytes=len(data), sha256=m.sha(data))
        image = m.merge_image(original, files, script)
        raw = m.decompressed_image(image)
        with self.assertRaisesRegex(ValueError, 'archive exceeds limit'):
            m.common.unpack(raw)
        entries = m.validate_image(image, original, manifest, script)
        self.assertEqual(next(content for path, _, content in entries
                              if path == name[1:]), data)
        self.assertEqual(m.common.unpack(gzip.decompress(original)),
                         m.common.unpack(gzip.decompress(original), max_bytes=m.MAX_IMAGE_BYTES))

    def test_explicit_cpio_bound_and_decompressed_image_bound_still_reject_overflow(self):
        original, _, manifest, script, image = fixture_image()
        raw = gzip.decompress(image)
        with self.assertRaisesRegex(ValueError, 'archive exceeds limit'):
            m.common.unpack(raw, max_bytes=len(raw) - 1)
        for invalid in (False, True, 0, -1, '268435456'):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                m.common.unpack(raw, max_bytes=invalid)
        with mock.patch.object(m, 'MAX_IMAGE_BYTES', len(raw) - 1):
            with self.assertRaisesRegex(ValueError, 'decompressed image exceeds bound'):
                m.validate_image(image, original, manifest, script)
        with self.assertRaises(ValueError):
            m.common.unpack(raw[:-16], max_bytes=m.MAX_IMAGE_BYTES)

    def test_original_newc_fields_and_bytes_survive_injection(self):
        original, _, manifest, script, image = fixture_image()
        actual = m.validate_image(image, original, manifest, script)
        before = {name: (fields, data) for name, fields, data in m.common.unpack(gzip.decompress(original))}
        after = {name: (fields, data) for name, fields, data in actual}
        for name, pair in before.items():
            if name != 'init':
                self.assertEqual(after[name], pair)
        self.assertIn(b'set -eu', after['init'][1])
        self.assertIn(b'full_profile_exit=$?', after['init'][1])
        self.assertEqual(after[m.SCRIPT_PATH][1], script)

    def test_runtime_cannot_replace_original_image_entries(self):
        original, files, _, script, _ = fixture_image()
        files['/bin/busybox'] = (0o555, b'replacement')
        with self.assertRaises(ValueError):
            m.merge_image(original, files, script)
        with self.assertRaises(ValueError):
            m.merge_image(original, {'/bin/sh/child': (0o444, b'x')}, script)

    def test_changed_bytes_metadata_or_extra_entries_fail_image_validation(self):
        original, _, manifest, script, image = fixture_image()
        entries = m.common.unpack(gzip.decompress(image))
        changed = copy.deepcopy(entries)
        changed[0][1][2] += 1
        variants = [changed, entries + [m.new_entry('unexpected', stat.S_IFREG | 0o444, b'x', 999)]]
        changed = copy.deepcopy(entries)
        index = next(index for index, (name, _, _) in enumerate(changed) if name == 'usr/lib/a04-fixture')
        name, fields, data = changed[index]
        changed[index] = (name, fields, data.replace(b'one', b'two'))
        variants.append(changed)
        for variant in variants:
            altered = gzip.compress(m.common.pack(variant), mtime=0)
            with self.assertRaises(ValueError):
                m.validate_image(altered, original, manifest, script)

    def test_rootfs_verifier_rejects_extra_files_symlinks_and_mode_drift(self):
        _, files, manifest, _, _ = fixture_image()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'usr/lib/a04-fixture'
            path.parent.mkdir(parents=True)
            path.write_bytes(files['/usr/lib/a04-fixture'][1])
            path.chmod(0o444)
            self.assertEqual(m.runtime.verified_files(root, manifest), files)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                m.runtime.verified_files(root, manifest)
            path.chmod(0o444)
            extra = root / 'extra'
            extra.write_bytes(b'added')
            with self.assertRaises(ValueError):
                m.runtime.verified_files(root, manifest)
            extra.unlink()
            extra.symlink_to('usr/lib/a04-fixture')
            with self.assertRaises(ValueError):
                m.runtime.verified_files(root, manifest)

    def test_chroot_extraction_rejects_path_escape_and_detects_changed_bytes(self):
        original, _, manifest, script, image = fixture_image()
        entries = m.validate_image(image, original, manifest, script)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'root'
            m.extract_chroot(entries, root)
            m.verify_chroot(entries, root)
            path = root / 'usr/lib/a04-fixture'
            path.chmod(0o644)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                m.verify_chroot(entries, root)
            with self.assertRaises(ValueError):
                m.extract_chroot([m.new_entry('../escape', stat.S_IFREG | 0o444, b'bad', 1)],
                                 Path(temporary) / 'bad')
            self.assertFalse((Path(temporary) / 'escape').exists())

    def test_native_elf_interpreter_parser_rejects_malformed_headers(self):
        data = Path('/usr/bin/python3.12').read_bytes()
        self.assertEqual(m.elf_interpreter(data), '/lib64/ld-linux-x86-64.so.2')
        for bad in (b'not ELF', data[:63], data[:18] + b'\x03\x00' + data[20:],
                    data[:32] + b'\xff' * 8 + data[40:]):
            with self.assertRaises(ValueError):
                m.elf_interpreter(bad)

    def test_cargo_proxy_command_path_is_not_replaced_by_rustup(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'rustup').write_bytes(b'proxy fixture')
            (directory / 'rustup').chmod(0o755)
            (directory / 'cargo').symlink_to('rustup')
            tool = m.inspect_tool(str(directory / 'cargo'))
            self.assertEqual(tool['path'], str(directory / 'cargo'))
            self.assertEqual(tool['resolved_path'], str(directory / 'rustup'))

    def test_bundle_digest_is_checked_before_source_or_unpack(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'inputs.json').write_bytes(b'altered')
            with mock.patch.object(m, 'source_identity') as source, self.assertRaises(ValueError):
                m.load_bundle(root, '0' * 64)
            source.assert_not_called()

    def test_dso_needed_closure_is_captured_without_a_program_interpreter(self):
        observed = []
        def metadata(arguments):
            observed.append(arguments)
            if arguments[0] == '/usr/bin/ldd':
                return 0, ('libssl.so.3 => /lib/x86_64-linux-gnu/libssl.so.3 (0x10)\n'
                           '/lib64/ld-linux-x86-64.so.2 (0x20)\n')
            if arguments[1] == '-d':
                return 0, '0x1 (NEEDED) Shared library: [libssl.so.3]\n'
            return 0, 'Program Headers: no interpreter in this shared object\n'
        with mock.patch.object(m.runtime, 'tool_output', side_effect=metadata):
            result = m.runtime.elf_metadata(Path('/unit-fixture/_ssl.so'))
        self.assertIsNone(result['interpreter'])
        self.assertEqual(result['needed'], ['libssl.so.3'])
        self.assertIn('/lib/x86_64-linux-gnu/libssl.so.3', result['dependencies'])
        self.assertEqual(observed[-1], ['/usr/bin/ldd', '/unit-fixture/_ssl.so'])
        with mock.patch.object(m.runtime, 'tool_output', side_effect=[
                (0, 'no interpreter'), (0, 'Shared library: [libssl.so.3]'),
                (0, 'libssl.so.3 => not found')]), self.assertRaises(ValueError):
            m.runtime.elf_metadata(Path('/unit-fixture/_ssl.so'))


class ReferenceRecordTests(unittest.TestCase):
    def fixture(self, root):
        profile, digest, image_sha = m.contract(), 'a' * 64, 'b' * 64
        receipt = {'schema': 'a04.ubuntu-full-reference.v1', 'profile': m.PROFILE, 'passed': True,
                   'runtime_inputs_unchanged': True, 'source_inputs_unchanged': True,
                   'process_groups_cleanup_completed': True, 'input_sha256': digest,
                   'image_sha256': image_sha, 'cases': [], 'reference_output': str(root),
                   'reference_chroot': str(root / 'a04-full-linux-fixture/root')}
        frozen = m.json_bytes({'input_sha256': digest, 'image_sha256': image_sha, 'cases': [], 'passed': False,
                               'reference_output': receipt['reference_output'],
                               'reference_chroot': receipt['reference_chroot']})
        (root / 'input.json').write_bytes(frozen)
        receipt['frozen_reference_input_sha256'] = m.sha(frozen)
        for case in profile['cases']:
            child = root / 'cases' / case['id']
            child.mkdir(parents=True)
            stdout = json.dumps(case['expected_facts'], separators=(',', ':')).encode() + b'\n'
            (child / 'stdout.log').write_bytes(stdout)
            (child / 'stderr.log').write_bytes(b'')
            (child / 'exit-code.txt').write_bytes(b'0\n')
            invocation = m.json_bytes(m.reference_invocation(Path(receipt['reference_chroot']), case))
            (child / 'input.json').write_bytes(invocation)
            result = m.evaluate_case(case, stdout, b'', 0, False)
            result.update(process_group_cleanup_completed=True, frozen_case_input_sha256=m.sha(invocation))
            receipt['cases'].append(result)
        (root / 'result.json').write_bytes(m.json_bytes(receipt))
        return profile, digest, image_sha, receipt

    def test_reference_raw_case_bytes_and_frozen_invocation_are_revalidated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile, digest, image_sha, _ = self.fixture(root)
            self.assertEqual(m.load_reference(root, digest, profile, image_sha), m.sha((root / 'result.json').read_bytes()))
            path = root / 'cases/dynamic.async_fd/stdout.log'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                m.load_reference(root, digest, profile, image_sha)

    def test_missing_case_or_fake_zero_exit_cannot_promote_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile, digest, image_sha, receipt = self.fixture(root)
            for changed in ('missing', 'boolean_exit', 'cleanup'):
                bad = copy.deepcopy(receipt)
                if changed == 'missing':
                    bad['cases'].pop()
                elif changed == 'boolean_exit':
                    bad['cases'][0]['process_exit'] = False
                else:
                    bad['cases'][0]['process_group_cleanup_completed'] = False
                (root / 'result.json').write_bytes(m.json_bytes(bad))
                with self.assertRaises(ValueError):
                    m.load_reference(root, digest, profile, image_sha)

    def test_reference_cannot_switch_image_or_change_preexecution_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile, digest, image_sha, _ = self.fixture(root)
            with self.assertRaises(ValueError):
                m.load_reference(root, digest, profile, 'c' * 64)
            path = root / 'cases/dynamic.async_fd/input.json'
            path.write_bytes(b'{}\n')
            with self.assertRaises(ValueError):
                m.load_reference(root, digest, profile, image_sha)

    def test_rehashed_invocation_cannot_change_chroot_uid_or_workload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile, digest, image_sha, receipt = self.fixture(root)
            path = root / 'cases/dynamic.async_fd/input.json'
            original = json.loads(path.read_bytes())
            for before, after in (('--userspec=65534:65534', '--userspec=0:0'),
                                  (receipt['reference_chroot'], '/'),
                                  (profile['cases'][0]['argv'][0], '/bin/true')):
                changed = copy.deepcopy(original)
                changed['argv'][changed['argv'].index(before)] = after
                raw = m.json_bytes(changed)
                path.write_bytes(raw)
                receipt['cases'][0]['frozen_case_input_sha256'] = m.sha(raw)
                (root / 'result.json').write_bytes(m.json_bytes(receipt))
                with self.assertRaises(ValueError):
                    m.load_reference(root, digest, profile, image_sha)

    def test_original_invocation_receipts_remain_verifiable_after_archival(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'original'
            directory.mkdir()
            profile, digest, image_sha, _ = self.fixture(directory)
            archive = Path(temporary) / 'archive'
            directory.rename(archive)
            self.assertEqual(m.load_reference(archive, digest, profile, image_sha),
                             m.sha((archive / 'result.json').read_bytes()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
