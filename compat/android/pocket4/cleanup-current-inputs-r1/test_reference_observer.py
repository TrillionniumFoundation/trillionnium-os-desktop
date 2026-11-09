"""Metadata-realistic proc fixtures plus real Linux FD/mmap observations.

Fixtures model separate task fd tables and mount views; they do not claim to
create actual kernel namespaces. No test imports or invokes a delete executor.
"""
import ast
import importlib.util
import io
import mmap
import os
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import reference_observer as revised

REAL_OBSERVATION = {}
HOST_NAMESPACE = os.readlink('/proc/self/ns/mnt')
root_descriptor = os.open('/', os.O_PATH | os.O_DIRECTORY)
try:
    ROOT_MOUNT_ID = int(next(line.split(':', 1)[1] for line in
        Path('/proc/self/fdinfo', str(root_descriptor)).read_text().splitlines()
        if line.startswith('mnt_id:')))
finally:
    os.close(root_descriptor)


def old_observer():
    path = Path(__file__).parent / 'fixtures/observed_live_references.py'
    spec = importlib.util.spec_from_file_location('original_observer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stat_line(pid, start=100, flags=0, state='S'):
    fields = [state] + ['0'] * 49
    fields[6], fields[19] = str(flags), str(start)
    return str(pid) + ' (fixture task) ' + ' '.join(fields) + '\n'


def escaped(path):
    return str(path).replace('\\', r'\134').replace(' ', r'\040').replace('\t', r'\011').replace('\n', r'\012')


class ProcFixture:
    pid = 424242
    other_tid = 424243

    def __init__(self, root):
        self.base = Path(root)
        self.target = self.base / 'target'
        self.target.mkdir()
        self.file = self.target / 'payload.bin'
        self.file.write_bytes(b'controlled fixture\n')
        self.outside = self.base / 'outside'
        self.outside.mkdir()
        self.proc = self.base / 'proc'
        self.proc.mkdir()
        self.dev = self.target.stat().st_dev
        self.mounts = self.mount('/', '/')
        (self.proc / 'self').mkdir()
        (self.proc / 'self' / 'root').symlink_to('/')
        (self.proc / 'self' / 'mountinfo').write_text(self.mounts)
        self.process = self.proc / str(self.pid)
        self.process.mkdir()
        (self.process / 'task').mkdir()
        self.populate(self.process, self.pid)
        self.leader = self.add_task(self.pid)

    def mount(self, source, point, mount_id=None, parent_id=None):
        mount_id = ROOT_MOUNT_ID if mount_id is None else mount_id
        parent_id = ROOT_MOUNT_ID if parent_id is None else parent_id
        dev = f'{os.major(self.dev)}:{os.minor(self.dev)}'
        return f'{mount_id} {parent_id} {dev} {escaped(source)} {escaped(point)} rw - ext4 /dev/fixture rw\n'

    def populate(self, task, tid, namespace=HOST_NAMESPACE, mounts=None):
        (task / 'stat').write_text(stat_line(tid))
        (task / 'maps').write_text('')
        (task / 'cmdline').write_bytes(b'fixture\x00')
        (task / 'mountinfo').write_text(self.mounts if mounts is None else mounts)
        (task / 'fd').mkdir()
        (task / 'ns').mkdir()
        (task / 'ns' / 'mnt').symlink_to(namespace)
        (task / 'cwd').symlink_to(self.outside)
        (task / 'exe').symlink_to(sys.executable)
        (task / 'root').symlink_to('/')

    def add_task(self, tid=None, namespace=HOST_NAMESPACE, mounts=None):
        tid = self.other_tid if tid is None else tid
        path = self.process / 'task' / str(tid)
        path.mkdir()
        self.populate(path, tid, namespace, mounts)
        return path

    def mapping(self, path=None):
        s = self.file.stat()
        dev = f'{os.major(s.st_dev):02x}:{os.minor(s.st_dev):02x}'
        return f'1000-2000 r--p 00000000 {dev} {s.st_ino} {path or "/alternate/payload.bin"}\n'

    def observe(self, module=revised, roots=None):
        # Model virtual mount traversal with O_PATH descriptors that still
        # refer to real fixture inodes, and matching virtual fdinfo mount IDs.
        # Actual namespace/mount syscalls have separate integration controls.
        real_open, real_close, real_dup, real_path_open = os.open, os.close, os.dup, Path.open
        descriptors = {}
        def mapped(value):
            return self.proc if str(value) == '/proc' else Path(value)
        def mount_rows(task):
            with real_path_open(task / 'mountinfo', 'r') as stream:
                rows = []
                for line in stream:
                    fields = line.split()
                    if len(fields) >= 6:
                        decode = lambda v: re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), v)
                        rows.append((int(fields[0]), decode(fields[3]), decode(fields[4])))
                return rows
        def opened(path, flags, mode=0o777, *, dir_fd=None):
            p = Path(path)
            if dir_fd is None and p.name == 'root' and self.proc in p.parents:
                fd = real_open(path, flags, mode)
                descriptors[fd] = (mount_rows(p.parent), '/', ROOT_MOUNT_ID)
                return fd
            if dir_fd in descriptors:
                rows, parent, mount_id = descriptors[dir_fd]
                virtual = str(Path(parent) / str(path))
                entries = [(mid, source) for mid, source, point in rows
                           if point == virtual and source.startswith('/')]
                if entries:
                    selected = getattr(self, 'vfs_mount_ids', {}).get(virtual)
                    mount_id, source = (next(entry for entry in entries if entry[0] == selected)
                                        if selected is not None else entries[-1])
                    source = getattr(self, 'vfs_overrides', {}).get(virtual, source)
                    fd = real_open(source, flags, mode)
                else:
                    fd = real_open(path, flags, mode, dir_fd=dir_fd)
                descriptors[fd] = (rows, virtual, mount_id)
                return fd
            return real_open(path, flags, mode, dir_fd=dir_fd)
        def duplicated(fd):
            new = real_dup(fd)
            if fd in descriptors:
                descriptors[new] = descriptors[fd]
            return new
        def closed(fd):
            descriptors.pop(fd, None)
            return real_close(fd)
        def path_opened(path, *args, **kwargs):
            if path.parent == Path('/proc/self/fdinfo') and path.name.isdigit():
                fd = int(path.name)
                if fd in descriptors:
                    mode = args[0] if args else kwargs.get('mode', 'r')
                    with real_path_open(path, 'rb') as stream:
                        raw = stream.read()
                    virtual = descriptors[fd][1]
                    mid = str(getattr(self, 'vfs_reported_mount_ids', {}).get(
                        virtual, descriptors[fd][2])).encode()
                    raw = re.sub(rb'(?m)^mnt_id:\s*[0-9]+', b'mnt_id:\t' + mid, raw)
                    return io.BytesIO(raw) if 'b' in mode else io.StringIO(raw.decode())
            return real_path_open(path, *args, **kwargs)
        with patch.object(module, 'Path', mapped), patch.object(os, 'open', opened), \
                patch.object(os, 'dup', duplicated), patch.object(os, 'close', closed), \
                patch.object(Path, 'open', path_opened):
            return module.live_references([str(self.target)] if roots is None else roots)


class ReferenceObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p4-observer-')
        self.addCleanup(self.tmp.cleanup)
        self.f = ProcFixture(self.tmp.name)

    def clear(self, result):
        self.assertEqual([], result['coverage_errors'])
        self.assertEqual([], result['process_or_owner_hits'])
        self.assertEqual([], result['mount_hits'])

    def unknown(self, result, code=None):
        self.assertEqual('UNKNOWN', result['visibility'])
        self.assertTrue(result['coverage_errors'])
        self.assertFalse(result['deletion_authorized'])
        if code:
            self.assertIn(code, [e['error'] for e in result['coverage_errors']])

    def test_complete_unreferenced_fixture_is_observed(self):
        result = self.f.observe()
        self.clear(result)
        self.assertEqual('OBSERVED', result['visibility'])
        self.assertEqual(1, result['tasks'])

    def test_only_nonleader_task_fd_is_detected_original_misses(self):
        task = self.f.add_task()
        (task / 'fd' / '7').symlink_to(self.f.file)
        self.clear(self.f.observe(old_observer()))
        result = self.f.observe()
        self.assertEqual([], result['coverage_errors'])
        self.assertIn({'pid': self.f.pid, 'tid': self.f.other_tid, 'kind': 'fd',
                       'root': str(self.f.target), 'fd': '7'}, result['process_or_owner_hits'])

    def test_fd_alias_is_detected_by_device_inode(self):
        alias = self.f.outside / 'alias'
        os.link(self.f.file, alias)
        (self.f.leader / 'fd' / '8').symlink_to(alias)
        (self.f.process / 'fd' / '8').symlink_to(alias)
        self.clear(self.f.observe(old_observer()))
        result = self.f.observe()
        self.assertEqual([], result['coverage_errors'])
        self.assertTrue(any(h['kind'] == 'fd' for h in result['process_or_owner_hits']))

    def test_maps_alias_is_detected_by_device_inode_original_misses(self):
        for task in (self.f.process, self.f.leader):
            (task / 'maps').write_text(self.f.mapping())
        self.clear(self.f.observe(old_observer()))
        result = self.f.observe()
        self.assertEqual([], result['coverage_errors'])
        self.assertTrue(any(h['kind'] == 'maps' for h in result['process_or_owner_hits']))

    def test_parent_bind_alias_without_reference_is_not_busy(self):
        view = self.f.mounts + self.f.mount(self.f.target.parent, '/bind-alias', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        self.clear(self.f.observe(old_observer()))
        result = self.f.observe()
        self.clear(result)
        self.assertEqual(1, result['ancestor_alias_count'])

    def test_escaped_parent_bind_source_resolves(self):
        parent = self.f.base / 'space parent'
        parent.mkdir()
        target = parent / 'child'
        target.mkdir()
        view = self.f.mounts + self.f.mount(parent, '/alias space', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        result = self.f.observe(roots=[str(target)])
        self.assertEqual([], result['coverage_errors'])
        self.assertEqual([], result['mount_hits'])
        self.assertEqual(1, result['ancestor_alias_count'])

    def test_alias_argument_is_owner_reference(self):
        view = self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        for value in (b'/renamed-parent/target/payload.bin',
                      b'--input=/renamed-parent/target/payload.bin',
                      b'/renamed-parent/irrelevant/../target/payload.bin'):
            with self.subTest(value=value):
                (self.f.leader / 'cmdline').write_bytes(b'fixture\0' + value + b'\0')
                result = self.f.observe()
                self.assertEqual([], result['coverage_errors'])
                self.assertEqual([], result['mount_hits'])
                self.assertTrue(any(h['kind'] == 'owner_argument_reference'
                                    for h in result['process_or_owner_hits']))

    def test_alias_deleted_maps_path_without_inventory_inode_is_busy(self):
        view = self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        (self.f.leader / 'maps').write_text(
            '1000-2000 r--p 00000000 00:00 0 /renamed-parent/target/old-file (deleted)\n')
        result = self.f.observe()
        self.assertEqual([], result['coverage_errors'])
        self.assertTrue(any(h['kind'] == 'maps' for h in result['process_or_owner_hits']))

    def test_mountpoint_below_alias_is_busy(self):
        view = (self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11) +
                self.f.mount(self.f.outside, '/renamed-parent/target/nested', 12))
        (self.f.leader / 'mountinfo').write_text(view)
        result = self.f.observe()
        self.assertEqual([], result['coverage_errors'])
        self.assertTrue(any(h['kind'] == 'mount_at_or_below_target'
                            for h in result['mount_hits']))

    def test_unproved_shadow_or_disconnected_transition_is_unknown(self):
        base = self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11)
        cases = [
            (self.f.mount(self.f.outside, '/renamed-parent', 12), 'alias_missing_without_verified_cover'),
            (self.f.mount(self.f.outside, '/renamed-parent/target', 12), 'alias_mount_transition_unknown'),
        ]
        for extra, code in cases:
            with self.subTest(code=code):
                (self.f.leader / 'mountinfo').write_text(base + extra)
                self.unknown(self.f.observe(), code)

    def test_same_point_alias_uses_kernel_layer_not_row_order(self):
        # The actual top layer is the first row, whose parent is the lower
        # same-point layer. Mountinfo order is deliberately not lookup order.
        view = (self.f.mounts +
                self.f.mount(self.f.target.parent, '/renamed-parent', 11, 12) +
                self.f.mount(self.f.outside, '/renamed-parent', 12))
        self.f.vfs_mount_ids = {'/renamed-parent': 11}
        (self.f.leader / 'mountinfo').write_text(view)
        result = self.f.observe()
        self.clear(result)
        self.assertEqual(0, result['verified_shadowed_alias_path_count'])
        self.assertEqual(2, result['visible_alias_path_count'])

    def masked_parent_view(self):
        return (self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11) +
                self.f.mount(self.f.outside, '/renamed-parent', 12, 11))

    def test_verified_ancestor_mask_missing_route_is_observed(self):
        (self.f.leader / 'mountinfo').write_text(self.masked_parent_view())
        result = self.f.observe()
        self.clear(result)
        self.assertEqual(1, result['verified_shadowed_alias_path_count'])
        self.assertEqual(1, result['ancestor_alias_count'])

    def test_hidden_alias_retains_inode_and_lexical_references(self):
        (self.f.leader / 'mountinfo').write_text(self.masked_parent_view())
        (self.f.leader / 'fd' / '8').symlink_to(self.f.file)
        (self.f.leader / 'cwd').unlink()
        (self.f.leader / 'cwd').symlink_to(self.f.target)
        (self.f.leader / 'maps').write_text(self.f.mapping('/renamed-parent/target/payload.bin') +
            '3000-4000 r--p 00000000 00:00 0 /renamed-parent/target/removed (deleted)\n')
        (self.f.leader / 'cmdline').write_bytes(b'fixture\0--input=/renamed-parent/target/payload.bin\0')
        result = self.f.observe()
        self.assertEqual([], result['coverage_errors'])
        self.assertEqual([], result['mount_hits'])
        self.assertEqual(1, result['verified_shadowed_alias_path_count'])
        kinds = {h['kind'] for h in result['process_or_owner_hits']}
        self.assertTrue({'fd', 'cwd', 'maps', 'owner_argument_reference'} <= kinds)
        self.assertFalse(result['deletion_authorized'])

    def test_missing_on_expected_alias_mount_is_unknown(self):
        view = self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        self.f.vfs_overrides = {'/renamed-parent': str(self.f.outside)}
        self.unknown(self.f.observe(), 'alias_missing_without_verified_cover')

    def test_kernel_mount_id_absent_from_snapshot_is_unknown(self):
        view = self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        self.f.vfs_reported_mount_ids = {'/renamed-parent': 987654321}
        self.unknown(self.f.observe(), 'bound_mount_id_unknown')

    def test_foreign_namespace_hostroot_chroot_cannot_claim_coverage(self):
        self.f.add_task(namespace='mnt:[22222222]')
        result = self.f.observe()
        self.unknown(result, 'persistent_mount_namespace_unobserved')
        self.assertIn('mnt:[22222222]', result['uncovered_mount_namespaces'])
        self.assertEqual(0, result['verified_namespace_witnesses'])

    def test_namespace_descriptor_is_typed_and_counted_without_bind(self):
        (self.f.leader / 'fd' / '7').symlink_to('/proc/self/ns/mnt')
        result = self.f.observe()
        self.clear(result)
        self.assertEqual(1, result['namespace_fd_count'])
        self.assertEqual(0, result['uncovered_mount_namespace_count'])

    def test_alias_kernel_walk_wrong_inode_is_unknown(self):
        view = self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        wrong = self.f.outside / 'target'
        wrong.mkdir()
        self.f.vfs_overrides = {'/renamed-parent': str(self.f.outside)}
        self.unknown(self.f.observe(), 'alias_target_identity_mismatch')

    def test_alias_indices_are_cached_only_for_identical_task_views(self):
        view = self.f.mounts + self.f.mount(self.f.target.parent, '/renamed-parent', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        self.f.add_task(mounts=view)
        result = self.f.observe()
        self.clear(result)
        self.assertEqual(1, result['ancestor_alias_count'])
        (self.f.process / 'task' / str(self.f.other_tid) / 'mountinfo').write_text(self.f.mounts)
        self.unknown(self.f.observe(), 'mount_view_changed')

    def test_mount_source_is_target_descendant(self):
        view = self.f.mounts + self.f.mount(self.f.file, '/alias-file', 11)
        (self.f.leader / 'mountinfo').write_text(view)
        result = self.f.observe()
        self.assertTrue(any(h['kind'] == 'mount_source_inside_target' for h in result['mount_hits']))

    def test_mounted_descendant_inventory_is_unknown(self):
        (self.f.proc / 'self' / 'mountinfo').write_text(
            self.f.mounts + self.f.mount('/', self.f.file, 11))
        self.unknown(self.f.observe(), 'mounted_target_descendant')

    def test_inventory_uses_kernel_mount_id_over_hidden_longest_path(self):
        (self.f.proc / 'self' / 'mountinfo').write_text(
            self.f.mounts + self.f.mount('/different-source', self.f.target.parent, 11))
        # The actual held target FD still reports ROOT_MOUNT_ID. Deriving
        # internal from the longer hidden row would point at the wrong source.
        self.clear(self.f.observe())

    def test_only_verified_empty_single_leader_zombie_may_be_skipped(self):
        for path in (self.f.process, self.f.leader):
            (path / 'stat').write_text(stat_line(self.f.pid, state='Z'))
        for reference in ('ns/mnt', 'cwd', 'exe', 'root'):
            (self.f.leader / reference).unlink()
        (self.f.leader / 'cmdline').write_bytes(b'')
        result = self.f.observe()
        self.clear(result)
        self.assertEqual(1, result['verified_empty_zombies'])

    def test_zombie_with_descriptor_or_cmdline_is_unknown(self):
        (self.f.process / 'stat').write_text(stat_line(self.f.pid, state='Z'))
        (self.f.leader / 'stat').write_text(stat_line(self.f.pid, state='Z'))
        for reference in ('ns/mnt', 'cwd', 'exe', 'root'):
            (self.f.leader / reference).unlink()
        (self.f.leader / 'fd' / '7').symlink_to(self.f.file)
        self.unknown(self.f.observe(), 'zombie_reference_view_not_empty')

    def test_live_namespace_free_thread_is_unknown(self):
        for reference in ('ns/mnt', 'cwd', 'exe', 'root'):
            (self.f.leader / reference).unlink()
        (self.f.leader / 'cmdline').write_bytes(b'')
        self.unknown(self.f.observe())

    def test_partial_zombie_view_has_no_general_missing_link_exemption(self):
        for path in (self.f.process, self.f.leader):
            (path / 'stat').write_text(stat_line(self.f.pid, state='Z'))
        (self.f.leader / 'cmdline').write_bytes(b'')
        (self.f.leader / 'cwd').unlink()
        self.unknown(self.f.observe(), 'missing_task_cwd')

    def test_zombie_identity_changes_is_unknown(self):
        (self.f.process / 'stat').write_text(stat_line(self.f.pid, state='Z'))
        (self.f.leader / 'stat').write_text(stat_line(self.f.pid, state='Z'))
        for reference in ('ns/mnt', 'cwd', 'exe', 'root'):
            (self.f.leader / reference).unlink()
        (self.f.leader / 'cmdline').write_bytes(b'')
        real_open = Path.open
        def replace_stat(path, *a, **kw):
            if path == self.f.leader / 'maps':
                with real_open(self.f.leader / 'stat', 'w') as f:
                    f.write(stat_line(self.f.pid, start=101, state='Z'))
            return real_open(path, *a, **kw)
        with patch.object(Path, 'open', replace_stat):
            self.unknown(self.f.observe(), 'zombie_identity_changed')

    def test_fd_added_or_removed_during_scan_is_unknown(self):
        real_open = Path.open
        for remove in (False, True):
            fd = self.f.leader / 'fd' / '7'
            if remove:
                fd.symlink_to(self.f.outside)
            def change_fds(path, *a, **kw):
                if path == self.f.leader / 'maps':
                    if remove and fd.is_symlink():
                        fd.unlink()
                    elif not remove and not fd.is_symlink():
                        fd.symlink_to(self.f.file)
                return real_open(path, *a, **kw)
            with patch.object(Path, 'open', change_fds):
                self.unknown(self.f.observe(), 'task_fd_set_changed')
            if fd.is_symlink():
                fd.unlink()

    def test_symlink_ancestor_is_unknown(self):
        alias = self.f.base / 'ancestor'
        alias.symlink_to(self.f.target)
        self.unknown(self.f.observe(roots=[str(alias / 'payload.bin')]))

    def test_special_node_inventory_is_unknown(self):
        os.mkfifo(self.f.target / 'fifo')
        self.unknown(self.f.observe(), 'target_symlink_or_special_node')

    def test_missing_live_task_cwd_is_unknown(self):
        (self.f.leader / 'cwd').unlink()
        self.unknown(self.f.observe(), 'missing_task_cwd')

    def test_permission_denied_maps_is_unknown(self):
        real_open = Path.open
        def denied(path, *a, **kw):
            if path == self.f.leader / 'maps':
                raise PermissionError('controlled access denial')
            return real_open(path, *a, **kw)
        with patch.object(Path, 'open', denied):
            self.unknown(self.f.observe(), 'PermissionError')

    def test_thread_namespace_change_is_unknown(self):
        real_open = Path.open
        changed = False
        def change_namespace(path, *a, **kw):
            nonlocal changed
            if path == self.f.leader / 'maps' and not changed:
                changed = True
                ns = self.f.leader / 'ns' / 'mnt'
                ns.unlink()
                ns.symlink_to('mnt:[2]')
            return real_open(path, *a, **kw)
        with patch.object(Path, 'open', change_namespace):
            self.unknown(self.f.observe(), 'task_identity_or_namespace_changed')

    def test_tid_reuse_is_unknown(self):
        real_open = Path.open
        def replace_stat(path, *a, **kw):
            if path == self.f.leader / 'maps':
                with real_open(self.f.leader / 'stat', 'w') as f:
                    f.write(stat_line(self.f.pid, start=101))
            return real_open(path, *a, **kw)
        with patch.object(Path, 'open', replace_stat):
            self.unknown(self.f.observe(), 'task_identity_or_namespace_changed')

    def test_new_thread_during_scan_is_unknown(self):
        real_open = Path.open
        changed = False
        def spawn_task(path, *a, **kw):
            nonlocal changed
            if path == self.f.leader / 'maps' and not changed:
                changed = True
                self.f.add_task()
            return real_open(path, *a, **kw)
        with patch.object(Path, 'open', spawn_task):
            self.unknown(self.f.observe(), 'task_set_or_leader_changed')

    def test_target_changes_during_scan_is_unknown(self):
        real_open = Path.open
        def change_file(path, *a, **kw):
            if path == self.f.leader / 'maps':
                with real_open(self.f.file, 'wb') as f:
                    f.write(b'changed target metadata')
            return real_open(path, *a, **kw)
        with patch.object(Path, 'open', change_file):
            self.unknown(self.f.observe(), 'target_inventory_changed')

    def test_malformed_maps_is_unknown(self):
        (self.f.leader / 'maps').write_text('invalid maps record\n')
        self.unknown(self.f.observe(), 'invalid_maps')

    def test_exact_roots_only_and_bounds(self):
        for roots in ([], [str(self.f.target)] * 129, ['/'], [str(self.f.target) + '/..'],
                      [str(self.f.target) + '//payload.bin']):
            with self.subTest(roots=roots[:2]):
                self.unknown(self.f.observe(roots=roots))

    def test_time_budget_is_unknown(self):
        with patch('time.monotonic', side_effect=[0, 46]):
            self.unknown(self.f.observe(), 'time_bound')


    def test_observed_nsfs_mount_namespace_objects_are_accepted(self):
        # Six actual Pocket4 namespace-object roots, with neutralized names.
        roots = [4026533156, 4026533157, 4026533056,
                 4026534726, 4026533223, 4026533044]
        observed = ''.join(
            f'{100 + i} 1 0:5 mnt:[{inode}] /namespace-object-{i} rw - nsfs nsfs rw\n'
            for i, inode in enumerate(roots))
        for path in (self.f.proc / 'self', self.f.leader):
            (path / 'mountinfo').write_text(self.f.mounts + observed)
        for i, inode in enumerate(roots):
            self.f.add_task(tid=self.f.other_tid + i, namespace=f'mnt:[{inode}]')
        result = self.f.observe()
        # A foreign task with the host-root inode is not a native-root witness.
        self.unknown(result, 'persistent_mount_namespace_unobserved')
        self.assertEqual(7, result['tasks'])
        self.assertEqual(0, result['covered_opaque_mount_namespace_count'])
        self.assertEqual(6, result['uncovered_mount_namespace_count'])
        self.assertNotIn('invalid_mount_path', [e['error'] for e in result['coverage_errors']])

    def test_opaque_nsfs_mountpoint_still_vetoes_target(self):
        point = escaped(self.f.target / 'namespace-object')
        raw = self.f.mounts + f'100 1 0:5 mnt:[4026533156] {point} rw - nsfs nsfs rw\n'
        (self.f.leader / 'mountinfo').write_text(raw)
        result = self.f.observe()
        self.unknown(result, 'persistent_mount_namespace_unobserved')
        self.assertTrue(any(h['kind'] == 'mount_at_or_below_target'
                            for h in result['mount_hits']))

    def test_opaque_nsfs_target_mount_is_unknown(self):
        point = escaped(self.f.target)
        raw = self.f.mounts + f'100 1 0:5 mnt:[4026533156] {point} rw - nsfs nsfs rw\n'
        (self.f.proc / 'self' / 'mountinfo').write_text(raw)
        self.unknown(self.f.observe(), 'mounted_target_root')

    def test_persistent_nsfs_namespace_without_task_view_is_unknown(self):
        raw = self.f.mounts + '100 1 0:5 mnt:[4026533156] /opaque rw - nsfs nsfs rw\n'
        (self.f.proc / 'self' / 'mountinfo').write_text(raw)
        result = self.f.observe()
        self.unknown(result, 'persistent_mount_namespace_unobserved')
        self.assertEqual(['mnt:[4026533156]'], result['uncovered_mount_namespaces'])

    def test_chroot_task_view_does_not_cover_persistent_namespace(self):
        raw = self.f.mounts + '100 1 0:5 mnt:[4026533156] /opaque rw - nsfs nsfs rw\n'
        (self.f.proc / 'self' / 'mountinfo').write_text(raw)
        task = self.f.add_task(namespace='mnt:[4026533156]')
        (task / 'root').unlink()
        (task / 'root').symlink_to(self.f.outside)
        result = self.f.observe()
        self.unknown(result, 'persistent_mount_namespace_unobserved')
        self.assertEqual(0, result['covered_opaque_mount_namespace_count'])

    def test_unknown_non_absolute_mount_formats_remain_unknown(self):
        cases = [
            ('ext4', 'mnt:[4026533156]', '/opaque'),
            ('nsfs', 'net:[4026533156]', '/opaque'),
            ('nsfs', 'mnt:[0]', '/opaque'),
            ('nsfs', 'mnt:[-1]', '/opaque'),
            ('nsfs', 'mnt:[4026533156]/child', '/opaque'),
            ('nsfs', 'unknown', '/opaque'),
            ('nsfs', 'mnt:[4026533156]', 'relative-point'),
        ]
        for filesystem_type, source, point in cases:
            with self.subTest(filesystem_type=filesystem_type, source=source, point=point):
                raw = self.f.mounts + f'100 1 0:5 {source} {point} rw - {filesystem_type} fixture rw\n'
                (self.f.proc / 'self' / 'mountinfo').write_text(raw)
                self.unknown(self.f.observe(), 'invalid_mount_path')

    def test_no_open_file_bodies_or_mutation_calls(self):
        real_open = Path.open
        def refuse_target_body(path, *a, **kw):
            if path == self.f.file:
                raise AssertionError('target body opened')
            return real_open(path, *a, **kw)
        with patch.object(Path, 'open', refuse_target_body):
            self.clear(self.f.observe())
        tree = ast.parse(Path(revised.__file__).read_text())
        prohibited = {'unlink', 'remove', 'rmdir', 'rmtree', 'rename', 'replace',
                      'mkdir', 'makedirs', 'system', 'Popen', 'run', 'execve'}
        self.assertFalse({n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Attribute)} & prohibited)


class RealLinuxObservationTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux procfs required')
    def test_real_self_open_fd_and_mmap_are_detected(self):
        with tempfile.TemporaryDirectory(prefix='p4-real-ref-') as directory:
            target = Path(directory) / 'target'
            target.mkdir()
            payload = target / 'payload'
            payload.write_bytes(b'x' * 4096)
            with payload.open('rb') as held, mmap.mmap(held.fileno(), 4096, access=mmap.ACCESS_READ) as mapped:
                self.assertEqual(b'x', mapped[:1])
                result = revised.live_references([str(target)])
            proc_self_pid = int(os.readlink('/proc/self'))
            self_hits = [h for h in result['process_or_owner_hits'] if h['pid'] == proc_self_pid]
            self.assertTrue(any(h['kind'] == 'fd' for h in self_hits), result)
            self.assertTrue(any(h['kind'] == 'maps' for h in self_hits), result)
            self.assertFalse(result['deletion_authorized'])
            REAL_OBSERVATION.update({
                'control': 'actual Linux procfs with self-held FD and mmap',
                'self_fd_hits': sum(h['kind'] == 'fd' for h in self_hits),
                'self_maps_hits': sum(h['kind'] == 'maps' for h in self_hits),
                'processes': result['processes'], 'tasks': result['tasks'],
                'coverage_errors_retained': len(result['coverage_errors']),
                'visibility': result['visibility'], 'deletion_authorized': False,
                'namespace_child_lifecycle': result['namespace_child_lifecycle'],
                'existing_host_mount_namespace_unchanged': result['existing_host_mount_namespace_unchanged'],
            })
            # Other processes may be unreadable or change in this shared runner;
            # their UNKNOWN is retained, never suppressed to obtain a green run.


if __name__ == '__main__':
    unittest.main()
