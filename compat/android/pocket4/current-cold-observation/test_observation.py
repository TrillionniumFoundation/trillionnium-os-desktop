"""Local regression tests for the read-only controller observation additions.

These import the candidate without invoking its main entry point. No VM, QMP,
systemd, policy load, remote process, or production path is touched.
"""
import ast
import collections
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent


def controller():
    spec = importlib.util.spec_from_file_location('observed_controller_test', HERE / 'controller.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AccountingTests(unittest.TestCase):
    def test_fields_survive_spaces_and_parentheses_in_comm(self):
        module = controller()
        fields = ['0'] * 50
        fields[0] = 'R'
        fields[11], fields[12], fields[40] = '1571', '2150', '746'
        raw = '435345 (qemu ) name with spaces) ' + ' '.join(fields) + '\n'
        self.assertEqual(module.cpu_observation_accounting(raw), {
            'utime_ticks': 1571, 'stime_ticks': 2150, 'guest_time_ticks': 746})

    def test_counter_rounding_is_preserved_not_clamped(self):
        module = controller()
        fields = ['0'] * 50
        fields[0] = 'S'
        fields[11], fields[12], fields[40] = '101', '170', '104'
        parsed = module.cpu_observation_accounting('42 (qemu) ' + ' '.join(fields))
        self.assertEqual(parsed['guest_time_ticks'], 104)
        self.assertEqual(parsed['utime_ticks'], 101)

    def test_missing_or_signed_counter_is_rejected(self):
        module = controller()
        with self.assertRaises(RuntimeError):
            module.cpu_observation_accounting('42 (qemu) R 1 2')
        fields = ['0'] * 50
        fields[0] = 'R'
        fields[40] = '-1'
        with self.assertRaises(RuntimeError):
            module.cpu_observation_accounting('42 (qemu) ' + ' '.join(fields))


class SerialObservationTests(unittest.TestCase):
    def setUp(self):
        self.module = controller()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'qemu-tmp').mkdir()
        self.module.D = self.root
        self.module.COMPONENT_LOG = self.root / 'qemu-tmp/guest-component.ndjson'
        for path in [self.root / 'qemu.stdout', self.root / 'qemu.stderr', self.module.COMPONENT_LOG]:
            path.write_bytes(b'')
            path.chmod(0o600)
        def ref(path):
            return {'path': str(path), 'bytes': 0, 'identity': self.module.f9(path.stat())}
        self.module.REPORT = {
            'console_logs_initial': {name: ref(self.root / name) for name in ('qemu.stdout', 'qemu.stderr')},
            'component_log_initial': ref(self.module.COMPONENT_LOG),
        }

    def tearDown(self):
        self.module.cpu_observation_close()
        self.temp.cleanup()

    def test_growth_is_observed_without_content_reads(self):
        self.module.serial_observation_prepare()
        first = self.module.serial_observation_snapshot()
        payload = b'P4_MAC_POLICY_CHUNK {"index":0,"hex":"' + b'00' * 4096 + b'"}\n'
        with self.module.COMPONENT_LOG.open('ab') as stream:
            stream.write(payload)
        second = self.module.serial_observation_snapshot()
        self.assertEqual(first['files']['component_stdout']['bytes'], 0)
        self.assertEqual(second['files']['component_stdout']['bytes'], len(payload))
        self.assertLessEqual(first['monotonic_end_ns'], second['monotonic_start_ns'])
        for row in (first, second):
            self.assertLessEqual(row['monotonic_start_ns'], row['monotonic_end_ns'])
        self.assertEqual(first['files']['component_stdout']['identity'][:6],
                         second['files']['component_stdout']['identity'][:6])
        self.assertTrue(self.module.REPORT['serial_observation_contract']['metadata_only'])
        self.assertEqual(self.module.REPORT['serial_observation_contract']['running_content_reads'], 0)

    def test_replaced_path_cannot_rebind_held_output_inode(self):
        self.module.serial_observation_prepare()
        self.module.COMPONENT_LOG.unlink()
        self.module.COMPONENT_LOG.write_bytes(b'replacement')
        self.module.COMPONENT_LOG.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'same held original'):
            self.module.serial_observation_snapshot()

    def test_truncation_after_growth_is_rejected(self):
        self.module.serial_observation_prepare()
        self.module.COMPONENT_LOG.write_bytes(b'original-output')
        self.module.serial_observation_snapshot()
        self.module.COMPONENT_LOG.write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError, 'nondecreasing'):
            self.module.serial_observation_snapshot()

    def test_symlink_is_rejected_and_partial_descriptors_are_closed(self):
        path = self.root / 'qemu.stderr'
        path.unlink()
        path.symlink_to(self.root / 'qemu.stdout')
        with self.assertRaises(OSError) as caught:
            self.module.serial_observation_prepare()
        self.assertEqual(caught.exception.errno, errno.ELOOP)
        held = [row['fd'] for row in self.module.SERIAL_OBSERVATION_FILES.values()]
        self.assertEqual(len(held), 1)
        self.module.cpu_observation_close()
        self.assertFalse(self.module.SERIAL_OBSERVATION_FILES)
        for fd in held:
            with self.assertRaises(OSError) as closed:
                os.fstat(fd)
            self.assertEqual(closed.exception.errno, errno.EBADF)

    def test_new_hardlink_is_rejected(self):
        self.module.serial_observation_prepare()
        os.link(self.module.COMPONENT_LOG, self.root / 'extra-link')
        with self.assertRaisesRegex(RuntimeError, 'same held original'):
            self.module.serial_observation_snapshot()

    def test_fifo_replacement_is_rejected_within_outer_two_second_deadline(self):
        self.module.COMPONENT_LOG.unlink()
        os.mkfifo(self.module.COMPONENT_LOG, 0o600)
        child = r'''
import errno, importlib.util, json, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('fifo_observer_test', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.D = Path(sys.argv[2])
module.COMPONENT_LOG = module.D / 'qemu-tmp/guest-component.ndjson'
module.REPORT = json.loads(sys.argv[3])
try:
    module.serial_observation_prepare()
except RuntimeError as error:
    assert str(error) == 'held original single-link serial output inode', str(error)
    held = [row['fd'] for row in module.SERIAL_OBSERVATION_FILES.values()]
    module.cpu_observation_close()
    for fd in held:
        try:
            os.fstat(fd)
        except OSError as closed:
            assert closed.errno == errno.EBADF
        else:
            raise AssertionError('partially prepared observation descriptor leaked')
    print(json.dumps({'fifo_rejected_before_read': True, 'partial_descriptors_closed': True}))
else:
    module.cpu_observation_close()
    raise AssertionError('FIFO was accepted as a regular serial output')
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', child,
            str(HERE / 'controller.py'), str(self.root), json.dumps(self.module.REPORT)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=2, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            'fifo_rejected_before_read': True, 'partial_descriptors_closed': True})

    def test_output_over_existing_serial_limit_is_rejected(self):
        self.module.serial_observation_prepare()
        self.module.SERIAL_LIMIT = 8
        self.module.COMPONENT_LOG.write_bytes(b'123456789')
        with self.assertRaisesRegex(RuntimeError, 'bounded nondecreasing'):
            self.module.serial_observation_snapshot()


class RegularLogReadTests(unittest.TestCase):
    def setUp(self):
        self.module = controller()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fifo_call(self, operation, expected_error):
        fifo = self.root / 'log-fifo'
        os.mkfifo(fifo, 0o600)
        child = r'''
import errno, importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location('regular_log_fifo_test', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert sys.argv[2] in ('pin', 'sync_regular_log')
actual_open = os.open
opened = []
def observed_open(*args, **kwargs):
    fd = actual_open(*args, **kwargs)
    opened.append(fd)
    return fd
def forbidden(*args, **kwargs):
    raise AssertionError('FIFO content read or fsync before regular-file rejection')
os.open = observed_open
os.read = forbidden
os.fsync = forbidden
try:
    getattr(module, sys.argv[2])(sys.argv[3])
except RuntimeError as error:
    assert str(error) == sys.argv[4], str(error)
else:
    raise AssertionError('FIFO was accepted')
assert len(opened) == 1
for fd in opened:
    try:
        os.fstat(fd)
    except OSError as closed:
        assert closed.errno == errno.EBADF
    else:
        raise AssertionError('rejected FIFO descriptor leaked')
print(json.dumps({'rejected_before_read_or_fsync': True, 'descriptor_closed': True}))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', child,
            str(HERE / 'controller.py'), operation, str(fifo), expected_error],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=2, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            'rejected_before_read_or_fsync': True, 'descriptor_closed': True})

    def test_pin_fifo_rejected_within_outer_two_second_deadline(self):
        self.fifo_call('pin', 'bounded regular input')

    def test_log_sync_fifo_rejected_before_fsync_within_outer_two_second_deadline(self):
        self.fifo_call('sync_regular_log', 'regular log descriptor before fsync')

    def test_regular_log_descriptor_closes_when_fsync_fails(self):
        path = self.root / 'regular-log'
        path.write_bytes(b'complete-log\n')
        synced = []
        def fail_sync(fd):
            synced.append(fd)
            raise OSError(errno.EIO, 'injected fsync failure')
        with mock.patch.object(self.module.os, 'fsync', side_effect=fail_sync):
            with self.assertRaises(OSError) as caught:
                self.module.sync_regular_log(path)
        self.assertEqual(caught.exception.errno, errno.EIO)
        self.assertEqual(len(synced), 1)
        with self.assertRaises(OSError) as closed:
            os.fstat(synced[0])
        self.assertEqual(closed.exception.errno, errno.EBADF)

    def test_regular_pin_still_returns_complete_exact_contents_and_identity(self):
        path = self.root / 'regular-input'
        raw = b'whole regular input\x00with exact bytes\n'
        path.write_bytes(raw)
        expected = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        observed, contents = self.module.pin(path, expected, contents=True)
        self.assertEqual(contents, raw)
        self.assertEqual(observed['identity'], self.module.f9(path.lstat()))
        self.assertEqual(observed['sha256'], expected['sha256'])


class UnchangedAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads((HERE / 'verification_baseline.json').read_text())
        cls.after = ast.parse((HERE / 'controller.py').read_text())

    @staticmethod
    def digest(node):
        return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

    def test_all_existing_need_guards_remain_present(self):
        def guards(tree):
            return collections.Counter(self.digest(node)
                for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == 'need')
        old, new = collections.Counter(self.baseline['need_guards']), guards(self.after)
        self.assertFalse(old - new)

    def test_only_reviewed_functions_and_main_change(self):
        def functions(tree):
            return {node.name: self.digest(node)
                    for node in tree.body if isinstance(node, ast.FunctionDef)}
        old, new = self.baseline['functions'], functions(self.after)
        changed = {name for name in old if old[name] != new[name]}
        self.assertEqual(changed, {'pin', 'cpu_observation_prepare', 'cpu_observation_sample_inner',
                                   'cpu_observation_close', 'main'})

    def test_vm_arguments_resource_properties_and_qmp_call_unchanged(self):
        def selected(tree):
            result = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                    and target.id in ('QEMU', 'properties') for target in node.targets):
                    result.append(self.digest(node))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == 'start_exact_owned_cpu':
                    result.append(self.digest(node))
            return result
        self.assertEqual(self.baseline['fixed_vm_arguments_resource_properties_and_qmp_call'],
                         selected(self.after))


if __name__ == '__main__':
    unittest.main(verbosity=2)
