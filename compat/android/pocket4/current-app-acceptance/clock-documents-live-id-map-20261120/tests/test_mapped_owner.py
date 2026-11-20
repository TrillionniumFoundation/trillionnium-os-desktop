"""Focused metadata controls; no Android or Main qualification is performed."""
import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
GROUP = 'clock-remaining-runtime-inputs-20261108-8b88-r2'
spec = importlib.util.spec_from_file_location('mapped_common_test', ROOT / 'source' / GROUP / 'app_common.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


class KernelFixture:
    """Actual local proc/map/file FDs with an explicitly modeled Main guard."""
    def __init__(self):
        self.proc_fd = os.open('/proc/self', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.pid_fd = os.pidfd_open(os.getpid(), 0)
        self.expected = {'pid': os.getpid(), 'uid': [str(os.getuid())] * 4}

    @contextmanager
    def lease(self):
        yield

    def close(self):
        os.close(self.pid_fd)
        os.close(self.proc_fd)


class MappingTests(unittest.TestCase):
    def test_shifted_uid_and_distinct_gid_ranges(self):
        self.assertEqual(common._mapped_guest_id(b'         0     100000     100000\n', 10063), 110063)
        self.assertEqual(common._mapped_guest_id(b'0 300000 100000\n', 10063), 310063)
        self.assertNotEqual(10063, common._mapped_guest_id(b'0 100000 100000\n', 10063))

    def test_rejects_unmapped_ambiguous_and_non_integer_inputs(self):
        for raw in [b'', b'0 100000 99999\n', b'1 100000 100000\n', b'0 100000 100000\n0 200000 100000\n',
                    b'0 4294967295 100000\n', b'-1 100000 100000\n', b'0 100000 100000 extra\n']:
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                common._mapped_guest_id(raw, 10063)
        for value in [True, False, -1, 100000, 1.0, '10063', None]:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                common._mapped_guest_id(b'0 100000 100000\n', value)

    def fixture(self):
        target = KernelFixture()
        self.addCleanup(target.close)
        view = common.MainView.__new__(common.MainView)
        view.target = target
        view.baseline = types.SimpleNamespace(value={'framework_epoch': {'binding': {'processes': {
            'init': {'host_pid': os.getpid(), 'uids': [os.getuid()] * 4}}}}})
        view.guard = lambda: {'modeled_guard_only': True, 'host_pid': os.getpid()}
        return view

    def test_actual_kernel_map_and_file_metadata_fds_close(self):
        self.assertEqual(os.getuid(), 0, 'This bounded metadata control runs as root.')
        view = self.fixture()
        with tempfile.TemporaryFile() as file:
            original = common.metadata(os.fstat(file.fileno()))
            count = len(os.listdir('/proc/self/fd'))
            result, owner = common.mapped_file_info(view, file.fileno(), 0)
            self.assertEqual(owner, (os.getuid(), os.getgid()))
            self.assertEqual(common.metadata(result), original)
            self.assertEqual(len(os.listdir('/proc/self/fd')), count)
            self.assertEqual(common.mapped_file_info(view, file.fileno(), 0)[1], owner)
            self.assertEqual(len(os.listdir('/proc/self/fd')), count)

    def test_foreign_main_and_changed_scope_refuse_without_fd_leaks(self):
        view = self.fixture()
        with tempfile.TemporaryFile() as file:
            count = len(os.listdir('/proc/self/fd'))
            view.baseline.value['framework_epoch']['binding']['processes']['init']['host_pid'] += 1
            with self.assertRaisesRegex(RuntimeError, 'ORIGINAL_MAIN_ROOT_UID'):
                common.mapped_file_info(view, file.fileno(), 0)
            self.assertEqual(len(os.listdir('/proc/self/fd')), count)
            view.baseline.value['framework_epoch']['binding']['processes']['init']['host_pid'] -= 1
            common.mapped_file_info(view, file.fileno(), 0)
            binding = view._mapped_file_owner_scope
            view._mapped_file_owner_scope = (*binding[:-1], b'0 1 100000\n')
            with self.assertRaisesRegex(RuntimeError, 'USER_NAMESPACE_OR_ID_MAP_CHANGED'):
                common.mapped_file_info(view, file.fileno(), 0)
            self.assertEqual(len(os.listdir('/proc/self/fd')), count)

    def test_wrong_namespace_type_and_metadata_change_refuse(self):
        view = self.fixture()
        with tempfile.TemporaryFile() as file:
            count = len(os.listdir('/proc/self/fd'))
            with mock.patch.object(common.fcntl, 'ioctl', return_value=0x00020000):
                with self.assertRaisesRegex(RuntimeError, 'KERNEL_USER_NAMESPACE'):
                    common.mapped_file_info(view, file.fileno(), 0)
            self.assertEqual(len(os.listdir('/proc/self/fd')), count)
            called = 0
            def guard():
                nonlocal called
                called += 1
                if called == 2:
                    file.write(b'changed during observation')
                    file.flush()
                return {'modeled_guard_only': True}
            view.guard = guard
            with self.assertRaisesRegex(RuntimeError, 'HELD_FILE_CHANGED'):
                common.mapped_file_info(view, file.fileno(), 0)
            self.assertEqual(len(os.listdir('/proc/self/fd')), count)

    def test_original_methods_and_all_other_modules_unchanged(self):
        predecessors = json.loads((ROOT / 'inputs/predecessors.json').read_bytes())
        changed = {
            (GROUP, 'clock_protection.py'): {'snapshot'},
            (GROUP, 'clock_alarm_reader.py'): {'data_identity'},
            ('ihg-5.111.1-r1', 'clock_protection.py'): {'snapshot'},
            ('documents-saf11-runtime-inputs-20261108-8b88-r2', 'documents_saf_core.py'): {'identity'},
            ('documents-search-sort-runtime-inputs-20261108-8b88-r2', 'documents_package_fixture.py'): {'identity'},
        }
        unchanged = 0
        for group, meta in predecessors.items():
            for ref in meta['files']:
                name = Path(ref['path']).name
                new = (ROOT / 'source' / group / name).read_bytes()
                old_path = ROOT / 'inputs/changed-originals' / group / name
                if old_path.exists():
                    old = old_path.read_bytes()
                    self.assertEqual(hashlib.sha256(old).hexdigest(), ref['sha256'])
                    if name == 'app_common.py':
                        self.assertTrue(new.startswith(old))
                        self.assertEqual(new[len(old):], (ROOT / 'mapped_owner_addition.py').read_bytes())
                        continue
                    before_tree, after_tree = ast.parse(old), ast.parse(new)
                    before = {node.name: ast.dump(node) for node in ast.walk(before_tree)
                              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                    after = {node.name: ast.dump(node) for node in ast.walk(after_tree)
                             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                    self.assertEqual(before.keys(), after.keys())
                    allowed = changed[(group, name)]
                    # The alarm nested function also changes its containing factory's AST.
                    if name == 'clock_alarm_reader.py':
                        allowed = allowed | {'make_reader'}
                    self.assertEqual({n for n in before if before[n] != after[n]}, allowed)
                else:
                    self.assertEqual(len(new), ref['bytes'])
                    self.assertEqual(hashlib.sha256(new).hexdigest(), ref['sha256'])
                    unchanged += 1
        self.assertEqual(unchanged, 97)


if __name__ == '__main__':
    unittest.main()
