"""Controlled proc-model tests for deferred empty task views.

The collector is replaced only in an AST-compiled test copy, with explicit
synthetic witnesses and retirement records. These tests make no real setns,
fork, child-lifecycle or host-admission claim. The separate privileged fixture
exercises the unmodified production collector and real chrooted Linux tasks.
"""
import ast
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

import reference_observer as revised
import test_reference_observer as ordinary


def controlled_module(factory):
    tree = ast.parse(Path(revised.__file__).read_text())
    live = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'live_references')
    original = next(n for n in live.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'make_namespace_view_collector')
    replacement = ast.parse('def make_namespace_view_collector(deadline, max_read, max_children):\n'
                            '    return _controlled_factory(deadline, max_read, max_children)\n').body[0]
    live.body[live.body.index(original)] = replacement
    module = types.ModuleType('controlled_empty_view_observer')
    module._controlled_factory = factory
    exec(compile(ast.fix_missing_locations(tree), '<controlled proc fixture>', 'exec'), module.__dict__)
    return module


class ModelCollector:
    """Test-only stand-in; it never creates a real child or namespace."""
    def __init__(self, case):
        self.case = case
        self.records = []
        self.retirement = []
        self.closed = False
        case.events.append(('factory', case.proc_enumerations))
        case.on_factory()

    def acquire(self, fd, expected):
        case, fixture = self.case, self.case.f
        actual = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) != tuple(expected):
            raise RuntimeError('model_namespace_handle_mismatch')
        if self.records:
            return self.records[0]
        if case.refuse_witness:
            raise RuntimeError('model_witness_unavailable')
        pid = fixture.pid + 100
        process = fixture.proc / str(pid)
        process.mkdir()
        (process / 'task').mkdir()
        fixture.populate(process, pid)
        task = process / 'task' / str(pid)
        task.mkdir()
        raw = fixture.mounts + case.extra_witness_mounts
        fixture.populate(task, pid, mounts=raw)
        root = os.stat('/')
        witness = types.SimpleNamespace(pid=pid, starttime=100, namespace=tuple(expected),
            root_identity=(root.st_dev, root.st_ino), root_displayed='/',
            root_mnt_id=ordinary.ROOT_MOUNT_ID, raw=raw.encode())
        self.records.append(witness)
        case.events.append(('acquire', case.proc_enumerations))
        return witness

    def verify(self, witness):
        if self.closed or not any(item is witness for item in self.records):
            raise RuntimeError('model_foreign_or_closed_witness')
        return True

    def matches(self, witness, pid, start, namespace, root_identity, displayed, raw):
        self.verify(witness)
        if (pid, start, tuple(namespace), tuple(root_identity), displayed, raw) != (
                witness.pid, witness.starttime, witness.namespace, witness.root_identity,
                witness.root_displayed, witness.raw):
            raise RuntimeError('model_scanner_witness_mismatch')
        return True

    def close(self):
        if not self.closed:
            for witness in self.records:
                shutil.rmtree(self.case.f.proc / str(witness.pid))
                self.retirement.append({'pid': witness.pid, 'namespace': witness.namespace,
                                        'reaped': True, 'exit_code': 0, 'synthetic_fixture': True})
            self.closed = True
            self.case.events.append(('close', self.case.proc_enumerations))
            self.case.on_close()
        if self.case.fail_close:
            raise RuntimeError('model_close_failed')


class EmptyTaskViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p4-empty-view-model-')
        self.addCleanup(self.tmp.cleanup)
        self.f = ordinary.ProcFixture(self.tmp.name)
        self.jail = self.f.base / 'jail'
        self.jail.mkdir()
        self.task = self.f.add_task(mounts='')
        (self.task / 'root').unlink()
        (self.task / 'root').symlink_to(self.jail)
        self.events = []
        self.proc_enumerations = 0
        self.extra_witness_mounts = ''
        self.refuse_witness = self.fail_close = False
        self.on_factory = lambda: None
        self.on_close = lambda: None
        self.pools = []
        self.displayed_root = None
        self.module = controlled_module(self.factory)

    def factory(self, deadline, max_read, max_children):
        self.assertEqual(32, max_children)
        self.assertEqual(16 * 1024 * 1024, max_read)
        pool = ModelCollector(self)
        self.pools.append(pool)
        return pool

    def observe(self):
        real_stat, real_open, real_readlink, real_scandir = os.stat, os.open, os.readlink, os.scandir
        real_namespace = '/proc/self/ns/mnt'
        def is_task_namespace(path):
            value = Path(path)
            return value.name == 'mnt' and self.f.proc in value.parents
        def stated(path, *args, **kwargs):
            if not isinstance(path, int) and is_task_namespace(path):
                if real_readlink(path) == ordinary.HOST_NAMESPACE:
                    return real_stat(real_namespace, *args, **kwargs)
            return real_stat(path, *args, **kwargs)
        def opened(path, flags, mode=0o777, *, dir_fd=None):
            if dir_fd is None and is_task_namespace(path):
                if real_readlink(path) == ordinary.HOST_NAMESPACE:
                    return real_open(real_namespace, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)
        def linked(path, *args, **kwargs):
            if self.displayed_root is not None and Path(path) == self.task / 'root':
                return self.displayed_root
            return real_readlink(path, *args, **kwargs)
        def scanned(path):
            if not isinstance(path, int) and Path(path) == self.f.proc:
                self.proc_enumerations += 1
                self.events.append(('process-set', self.proc_enumerations))
            return real_scandir(path)
        with patch.object(os, 'stat', stated), patch.object(os, 'open', opened), \
                patch.object(os, 'readlink', linked), patch.object(os, 'scandir', scanned):
            return self.f.observe(module=self.module)

    def unknown(self, result, code=None):
        self.assertEqual('UNKNOWN', result['visibility'], result)
        self.assertTrue(result['coverage_errors'], result)
        self.assertFalse(result['deletion_authorized'])
        if code:
            self.assertIn(code, [row['error'] for row in result['coverage_errors']], result)

    def clear(self, result):
        self.assertEqual('OBSERVED', result['visibility'], result)
        for key in ('coverage_errors', 'process_or_owner_hits', 'mount_hits'):
            self.assertEqual([], result[key], result)
        self.assertEqual(1, result['empty_task_mount_views'])
        self.assertEqual(1, result['verified_empty_task_mount_views'])
        self.assertFalse(result['deletion_authorized'])

    def test_empty_host_namespace_still_requires_owned_witness_after_initial_census(self):
        result = self.observe()
        self.clear(result)
        self.assertEqual(1, len(self.pools))
        self.assertGreaterEqual(next(value for event, value in self.events if event == 'factory'), 2)
        close = next(i for i, (event, _) in enumerate(self.events) if event == 'close')
        self.assertTrue(any(event == 'process-set' for event, _ in self.events[close + 1:]))
        self.assertTrue(all(pool.closed for pool in self.pools))

    def test_empty_view_held_target_fd_is_still_a_specific_reference(self):
        (self.task / 'fd' / '17').symlink_to(self.f.file)
        result = self.observe()
        self.assertEqual('OBSERVED', result['visibility'], result)
        self.assertTrue(any(h['kind'] == 'fd' and h['tid'] == self.f.other_tid
                            and h.get('fd') == '17' for h in result['process_or_owner_hits']), result)

    def test_empty_view_target_mmap_is_still_a_specific_reference(self):
        (self.task / 'maps').write_text(self.f.mapping('/pre-chroot/payload'))
        result = self.observe()
        self.assertEqual('OBSERVED', result['visibility'], result)
        self.assertTrue(any(h['kind'] == 'maps' and h['tid'] == self.f.other_tid
                            for h in result['process_or_owner_hits']), result)

    def test_empty_view_outside_cwd_is_still_a_specific_reference(self):
        (self.task / 'cwd').unlink()
        (self.task / 'cwd').symlink_to(self.f.target)
        result = self.observe()
        self.assertEqual('OBSERVED', result['visibility'], result)
        self.assertTrue(any(h['kind'] == 'cwd' and h['tid'] == self.f.other_tid
                            for h in result['process_or_owner_hits']), result)

    def test_task_root_relative_argument_uses_verified_projection(self):
        (self.task / 'root').unlink()
        (self.task / 'root').symlink_to(self.f.base)
        (self.task / 'cmdline').write_bytes(b'fixture\x00/target/payload.bin\x00')
        result = self.observe()
        self.assertEqual('OBSERVED', result['visibility'], result)
        self.assertTrue(any(h['kind'] == 'owner_argument_reference' and h['tid'] == self.f.other_tid
                            for h in result['process_or_owner_hits']), result)

    def test_empty_view_without_a_witness_is_unknown(self):
        self.refuse_witness = True
        self.unknown(self.observe(), 'empty_task_mount_view_unresolved')

    def test_same_inode_wrong_mount_id_is_unknown(self):
        self.f.vfs_task_root_mount_ids = {str(self.task): ordinary.ROOT_MOUNT_ID + 100}
        self.unknown(self.observe(), 'empty_task_root_binding_mismatch')

    def test_displayed_root_wrong_inode_is_unknown(self):
        other = self.f.base / 'different-root'
        other.mkdir()
        self.displayed_root = str(other)
        self.unknown(self.observe(), 'empty_task_root_binding_mismatch')

    def test_symlink_in_root_route_is_not_followed(self):
        link = self.f.base / 'root-link'
        link.symlink_to(self.jail)
        self.displayed_root = str(link)
        self.unknown(self.observe())

    def test_noncanonical_root_route_is_unknown(self):
        self.displayed_root = str(self.jail) + '/../jail'
        self.unknown(self.observe(), 'empty_task_root_path_unknown')

    def test_root_changed_after_first_census_is_unknown(self):
        def change():
            (self.task / 'root').unlink()
            (self.task / 'root').symlink_to(self.f.outside)
        self.on_factory = change
        self.unknown(self.observe(), 'empty_task_view_changed')

    def test_raw_view_changed_after_first_census_is_unknown(self):
        self.on_factory = lambda: (self.task / 'mountinfo').write_text(self.f.mounts)
        self.unknown(self.observe(), 'empty_task_view_changed')

    def test_starttime_changed_after_first_census_is_unknown(self):
        self.on_factory = lambda: (self.task / 'stat').write_text(
            ordinary.stat_line(self.f.other_tid, start=999))
        self.unknown(self.observe(), 'empty_task_view_changed')

    def test_fd_number_set_changed_between_phases_is_unknown(self):
        self.on_factory = lambda: (self.task / 'fd' / '17').symlink_to(self.f.outside)
        self.unknown(self.observe(), 'task_fd_set_changed')

    def test_fd_slot_replaced_by_namespace_handle_is_not_omitted(self):
        slot = self.task / 'fd' / '17'
        slot.symlink_to(self.f.outside)
        def change():
            slot.unlink()
            slot.symlink_to('/proc/self/ns/mnt')
        self.on_factory = change
        self.unknown(self.observe(), 'task_fd_identity_changed')

    def test_process_set_change_after_collector_retirement_is_unknown(self):
        self.on_close = lambda: (self.f.proc / '989898').mkdir()
        self.unknown(self.observe(), 'process_set_changed_after_namespace_views')

    def test_empty_claim_at_native_root_is_not_a_restricted_view(self):
        (self.task / 'root').unlink()
        (self.task / 'root').symlink_to('/')
        self.unknown(self.observe(), 'empty_task_view_contains_mountpoint')

    def test_late_persistent_namespace_cannot_escape_coverage(self):
        self.extra_witness_mounts = '9876 1 0:5 mnt:[987654321] /opaque rw - nsfs nsfs rw\n'
        result = self.observe()
        self.unknown(result, 'persistent_mount_namespace_unobserved')
        self.assertIn('mnt:[987654321]', result['uncovered_mount_namespaces'])

    def test_earlier_failure_prevents_collector_and_is_retained(self):
        (self.f.leader / 'maps').write_text('malformed\n')
        result = self.observe()
        self.unknown(result, 'invalid_maps')
        self.assertEqual([], self.pools)
        self.assertIn('empty_task_mount_view_unresolved', [x['error'] for x in result['coverage_errors']])

    def test_collector_close_failure_remains_unknown(self):
        self.fail_close = True
        result = self.observe()
        self.unknown(result)
        self.assertFalse(result['namespace_child_lifecycle']['close_succeeded'])


class FirstVerifiedRepresentativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p4-first-view-model-')
        self.addCleanup(self.tmp.cleanup)
        self.f = ordinary.ProcFixture(self.tmp.name)
        self.other = self.f.add_task()

    def test_later_same_view_does_not_replace_first_verified_representative(self):
        real_open = Path.open
        reads = 0
        def opened(path, *args, **kwargs):
            nonlocal reads
            if path == self.other / 'stat':
                reads += 1
                if reads > 2:
                    raise FileNotFoundError('late model representative unavailable')
            return real_open(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            result = self.f.observe()
        self.assertEqual('OBSERVED', result['visibility'], result)
        self.assertEqual([], result['coverage_errors'])
        self.assertEqual(2, reads)

    def test_first_verified_representative_loss_still_refuses(self):
        real_open = Path.open
        reads = 0
        def opened(path, *args, **kwargs):
            nonlocal reads
            if path == self.f.leader / 'stat':
                reads += 1
                if reads > 2:
                    raise FileNotFoundError('first model representative unavailable')
            return real_open(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            result = self.f.observe()
        self.assertEqual('UNKNOWN', result['visibility'], result)
        self.assertIn('FileNotFoundError', [x['error'] for x in result['coverage_errors']])

    def test_later_view_disagreement_is_not_ignored(self):
        (self.other / 'mountinfo').write_text(self.f.mounts + self.f.mount('/', '/other', 9876))
        result = self.f.observe()
        self.assertEqual('UNKNOWN', result['visibility'], result)
        self.assertIn('mount_view_changed', [x['error'] for x in result['coverage_errors']])

    def test_a_failed_task_never_becomes_representative_and_error_is_retained(self):
        (self.f.leader / 'maps').write_text('invalid\n')
        result = self.f.observe()
        self.assertEqual('UNKNOWN', result['visibility'], result)
        self.assertIn('invalid_maps', [x['error'] for x in result['coverage_errors']])
        # The later fully checked host-root task can prove this view, while
        # the failed first task still prevents admission.
        self.assertEqual(0, result['uncovered_mount_namespace_count'])


if __name__ == '__main__':
    unittest.main()
