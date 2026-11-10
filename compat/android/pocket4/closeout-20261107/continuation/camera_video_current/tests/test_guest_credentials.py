"""Guest/observer credential regressions, without Android or device access.

The foreign namespace/proc trees below are explicit filesystem fixtures. Live
pidfds and the same-namespace control use the real Linux kernel, but these tests
do not qualify a deployed Android process, socket service, camera or audio path.
"""
import hashlib
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


RUNTIME = load(ROOT / 'source/camera_audio_runtime.py', 'camera_guest_credentials_runtime')
BINDING = load(ROOT / 'source/camera_audio_binding.py', 'camera_guest_credentials_binding')
DRIVER = load(ROOT / 'source/camera_video_driver.py', 'camera_guest_credentials_driver')
BASE = load(ROOT / 'source/camera_base_session.py', 'camera_guest_credentials_base')
OBSERVATIONS = load(ROOT / 'source/camera_observations.py', 'camera_guest_credentials_observations')


def fd_table():
    rows = {}
    for name in os.listdir('/proc/self/fd'):
        try: rows[int(name)] = os.readlink('/proc/self/fd/' + name)
        except FileNotFoundError: pass
    return rows


class TargetFixture:
    def __init__(self, root, uid_map=b'0 200000 100000\n', gid_map=b'0 300000 100000\n'):
        self.path = root / 'target'; (self.path / 'ns').mkdir(parents=True)
        self.namespace = root / 'fixture-user-namespace'; self.namespace.write_bytes(b'explicit namespace fixture')
        (self.path / 'ns/user').symlink_to(self.namespace)
        (self.path / 'stat').write_bytes(Path('/proc/self/stat').read_bytes())
        (self.path / 'uid_map').write_bytes(uid_map); (self.path / 'gid_map').write_bytes(gid_map)
        self.proc_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.root_fd = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        self.namespaces = {key: os.open('/proc/self/ns/' + key, os.O_RDONLY | os.O_CLOEXEC)
            for key in ('pid', 'uts', 'ipc', 'net', 'cgroup')}
        self.closed = False; self.verifications = 0

    def verify(self):
        if self.closed: raise RuntimeError('fixture target closed')
        self.verifications += 1

    def close(self):
        for fd in (*self.namespaces.values(), self.root_fd, self.proc_fd): os.close(fd)
        self.closed = True


class GuestCredentialControls(unittest.TestCase):
    def setUp(self):
        self.before = fd_table()
        self.addCleanup(lambda: self.assertEqual(fd_table(), self.before))
        self.temporary = tempfile.TemporaryDirectory(prefix='camera-credential-contract-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def target(self, **maps):
        target = TargetFixture(self.root, **maps)
        self.addCleanup(target.close)
        return target

    def credentials(self, target):
        value = RUNTIME.GuestCredentials(target)
        self.addCleanup(value.close)
        return value

    def process_fixture(self, target, *, uid=210062, gid=310062, name=None, user_namespace=None):
        pid = os.getpid() if name is None else name
        path = self.root / str(pid); (path / 'ns').mkdir(parents=True)
        (path / 'stat').write_bytes(Path('/proc/self/stat').read_bytes().replace(
            str(os.getpid()).encode() + b' ', str(pid).encode() + b' ', 1))
        (path / 'status').write_text('Uid:\t' + '\t'.join([str(uid)] * 4) + '\nGid:\t'
            + '\t'.join([str(gid)] * 4) + '\nNSpid:\t' + str(pid) + '\t42\nGroups:\t\n')
        (path / 'cgroup').write_text('0::/system.slice/droidloomd.service\n')
        (path / 'cmdline').write_bytes(b'com.android.camera2\x00')
        for key in ('mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup', 'user'):
            link = os.readlink('/proc/self/ns/' + key)
            if key == 'user': link = user_namespace or 'user:[' + str(target.namespace.stat().st_ino) + ']'
            (path / 'ns' / key).symlink_to(link)
        (path / 'exe').symlink_to(Path(sys.executable).resolve())
        (path / 'root').symlink_to('/')
        return pid, path

    def proc_routes(self, paths):
        real_open, real_listdir = os.open, os.listdir
        def route(path, flags, *args, **kwargs):
            if isinstance(path, str) and path in paths and 'dir_fd' not in kwargs: path = paths[path]
            return real_open(path, flags, *args, **kwargs)
        def listing(path):
            return [Path(key).name for key in paths] if path == '/proc' else real_listdir(path)
        return mock.patch.multiple(RUNTIME.os, open=route, listdir=listing)

    def test_segmented_uid_and_gid_maps_use_independent_ranges(self):
        target = self.target(uid_map=b'0 400000 1000\n10000 510000 1000\n1000 200000 9000\n',
            gid_map=b'0 600000 20000\n')
        value = self.credentials(target)
        self.assertEqual(value.observer_id('uid', 10062), 510062)
        self.assertEqual(value.observer_id('gid', 10062), 610062)
        self.assertEqual(value.observer_id('uid', 1041), 200041)
        self.assertEqual(value.receipt['maps']['uid']['sha256'], hashlib.sha256((target.path / 'uid_map').read_bytes()).hexdigest())

    def test_map_holes_and_exclusive_upper_boundary_reject(self):
        value = self.credentials(self.target(uid_map=b'10000 210000 10\n10020 210020 10\n'))
        for uid in (0, 9999, 10010, 10019, 10030, 4294967295, -1, True):
            with self.subTest(uid=uid), self.assertRaises(RuntimeError): value.observer_id('uid', uid)
        self.assertEqual(value.observer_id('uid', 10029), 210029)

    def test_overlap_overflow_unmapped_and_malformed_maps_reject(self):
        invalid = (b'', b'0 0 0\n', b'0 0 4294967296\n', b'1 0 4294967295\n',
            b'0 4294967295 1\n', b'0 4294967294 2\n', b'0 100 10\n9 200 1\n',
            b'0 100 10\n20 109 1\n', b'0 100 1\n0 100 1\n', b'-1 100 1\n',
            b'0 100 1 extra\n', b'0 100 1', b'0 100 1\r\n', b'0 100 1\n\n',
            b'0 100 1\n' * 341, b'9' * 16385)
        for raw in invalid:
            with self.subTest(raw=raw[:80]), self.assertRaises(RuntimeError): RUNTIME.id_map(raw)
        self.assertEqual(RUNTIME.id_map(b'         0          0 4294967295\n'), ((0, 0, 4294967295),))

    def test_missing_map_has_no_identity_fallback_and_no_fd_leak(self):
        target = self.target(); (target.path / 'uid_map').unlink(); before = fd_table()
        with self.assertRaises(FileNotFoundError): RUNTIME.GuestCredentials(target)
        self.assertEqual(fd_table(), before)

    def test_same_real_user_namespace_uses_observer_ids_not_parent_map(self):
        target = self.target()
        (target.path / 'ns/user').unlink(); (target.path / 'ns/user').symlink_to('/proc/thread-self/ns/user')
        for kind in ('uid', 'gid'): (target.path / (kind + '_map')).write_bytes(Path('/proc/self/' + kind + '_map').read_bytes())
        value = self.credentials(target)
        self.assertTrue(value.receipt['same_user_namespace'])
        self.assertEqual(value.observer_id('uid', os.getuid()), os.getuid())
        self.assertEqual(value.observer_id('gid', os.getgid()), os.getgid())

    def test_foreign_identity_map_is_supported_without_guessing(self):
        value = self.credentials(self.target(uid_map=b'0 0 4294967295\n', gid_map=b'0 0 4294967295\n'))
        self.assertFalse(value.receipt['same_user_namespace'])
        self.assertEqual(value.observer_id('uid', 10062), 10062)
        self.assertEqual(value.observer_id('gid', 1041), 1041)

    def test_target_user_namespace_replacement_is_rejected(self):
        target = self.target(); value = self.credentials(target)
        other = self.root / 'other-user-namespace'; other.write_bytes(b'another explicit fixture')
        (target.path / 'ns/user').unlink(); (target.path / 'ns/user').symlink_to(other)
        with self.assertRaisesRegex(RuntimeError, 'USER_NAMESPACE_CHANGED'): value.verify()

    def test_observer_user_namespace_replacement_is_rejected(self):
        value = self.credentials(self.target()); other = self.root / 'another-observer'; other.touch()
        real_stat = os.stat
        def changed(path, *args, **kwargs):
            return real_stat(other if path == '/proc/thread-self/ns/user' else path, *args, **kwargs)
        with mock.patch.object(RUNTIME.os, 'stat', changed):
            with self.assertRaisesRegex(RuntimeError, 'USER_NAMESPACE_CHANGED'): value.verify()

    def test_held_map_change_or_closed_handle_is_rejected(self):
        target = self.target(); value = self.credentials(target)
        (target.path / 'gid_map').write_bytes(b'0 400000 100000\n')
        with self.assertRaisesRegex(RuntimeError, 'CREDENTIAL_MAP_CHANGED'): value.verify()
        value.close()
        with self.assertRaisesRegex(RuntimeError, 'CREDENTIAL_MAP_CLOSED'): value.observer_id('uid', 1041)

    def test_scope_close_preserves_owned_map_but_another_main_is_rejected(self):
        target = self.target(); value = self.credentials(target)
        reopened = os.open(target.path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, reopened)
        # The scope closes its borrowed proc FD. The map owns an independent
        # FD and pidfd, while the next scope must bind the same proc inode.
        old_proc = target.proc_fd; target.proc_fd = os.dup(reopened); os.close(old_proc)
        value.verify_for(types.SimpleNamespace(proc_fd=reopened, verify=lambda: None))
        self.assertEqual(value.observer_id('uid', 10064), 210064)
        other = self.root / 'other-main'; other.mkdir()
        other_fd = os.open(other, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, other_fd)
        with self.assertRaisesRegex(RuntimeError, 'CURRENT_FLOW_MAIN_DIFFERS'):
            value.verify_for(types.SimpleNamespace(proc_fd=other_fd, verify=lambda: None))

    def test_main_pidfd_exit_rejects_still_readable_fixture_maps(self):
        child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(20)'])
        try:
            target = self.target(); (target.path / 'stat').write_bytes(Path('/proc/' + str(child.pid) + '/stat').read_bytes())
            value = self.credentials(target)
            child.terminate(); child.wait(timeout=3)
            with self.assertRaisesRegex(RuntimeError, 'HELD_MAIN_CREDENTIAL_PROCESS_EXITED'): value.verify()
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=3)

    def test_mapped_guest_is_found_in_pinned_namespace(self):
        target = self.target(); pid, path = self.process_fixture(target)
        with self.proc_routes({'/proc/' + str(pid): path}):
            row = RUNTIME.find_guest(target, 10062, guest_pid=42,
                executable_inode=RUNTIME.inode(Path(sys.executable).resolve().stat()), deadline=time.monotonic() + 2)
        self.assertEqual(row['host_pid'], pid)
        self.assertEqual(row['uids'], [210062] * 4)

    def test_same_pid_namespace_and_uid_in_another_userns_is_not_adopted(self):
        target = self.target(); pid, path = self.process_fixture(target)
        other, other_path = self.process_fixture(target, name=pid + 100000, user_namespace='user:[999]')
        with self.proc_routes({'/proc/' + str(pid): path, '/proc/' + str(other): other_path}):
            row = RUNTIME.find_guest(target, 10062, guest_pid=42, deadline=time.monotonic() + 2)
        self.assertEqual(row['host_pid'], pid)

    def test_mapped_process_binds_pidfd_root_elf_and_rejects_credential_drift(self):
        target = self.target(); pid, path = self.process_fixture(target)
        with self.proc_routes({'/proc/' + str(pid): path}):
            handle = RUNTIME.HeldProcess(pid, 10062, RUNTIME.inode(Path(sys.executable).resolve().stat()),
                target=target, guest_pid=42, package='com.android.camera2')
            try:
                self.assertEqual(handle.verify()['uids'], [210062] * 4)
                (path / 'status').write_bytes((path / 'status').read_bytes().replace(b'210062', b'10062'))
                with self.assertRaisesRegex(RuntimeError, 'EXITED_OR_CHANGED'): handle.verify()
            finally: handle.close()

    def test_untranslated_guest_uid_is_not_accepted_from_host_proc(self):
        target = self.target(); pid, path = self.process_fixture(target, uid=10062)
        with self.proc_routes({'/proc/' + str(pid): path}):
            with self.assertRaisesRegex(RuntimeError, 'ONE_EXACT_CURRENT_MAIN_PROCESS'):
                RUNTIME.find_guest(target, 10062, guest_pid=42, deadline=time.monotonic() + 2)
            with self.assertRaisesRegex(RuntimeError, 'EXACT_REAL_AUDIO_PROCESS_UID'):
                RUNTIME.HeldProcess(pid, 10062, RUNTIME.inode(Path(sys.executable).resolve().stat()), target=target, guest_pid=42)

    def test_host_process_without_guest_map_still_binds_and_detects_exit(self):
        child = subprocess.Popen([sys.executable, '-I', '-B', '-c',
            'import os,time; os.write(1,b"R"); time.sleep(20)'], stdout=subprocess.PIPE)
        handle = None
        try:
            # Popen's exec handshake precedes interpreter initialization. Bind
            # only after the owned child explicitly reports its steady state;
            # the production process-state equality must remain strict.
            self.assertTrue(select.select([child.stdout], [], [], 3)[0])
            self.assertEqual(child.stdout.read(1), b'R')
            handle = RUNTIME.HeldProcess(child.pid, os.getuid(), RUNTIME.inode(Path(sys.executable).resolve().stat()))
            self.assertEqual(handle.verify()['uids'], [os.getuid()] * 4)
            child.terminate(); child.wait(timeout=3)
            with self.assertRaisesRegex(RuntimeError, 'EXITED_OR_CHANGED'): handle.verify()
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=3)
            if handle is not None: handle.close()
            child.stdout.close()

    def test_gallery_directory_owners_are_compared_in_observer_namespace(self):
        value = self.credentials(self.target(uid_map=('10064 %d 1\n' % os.getuid()).encode(),
            gid_map=('10064 %d 1\n' % os.getgid()).encode()))
        ce, de = self.root / 'ce', self.root / 'de'; ce.mkdir(); de.mkdir()
        package = 'com.android.gallery3d'
        raw = ('Packages:\n  Package [' + package + '] (fixture):\n    appId=10064\n'
            '    versionCode=40030 minSdk=1\n    codePath=/data/app/gallery-fixture\n'
            '    User 0: installed=true hidden=false suspended=false enabled=0 ceDataInode=%d deDataInode=%d\n'
            '        android.permission.READ_MEDIA_AUDIO: granted=true, flags=[]\n'
            '      firstInstallTime=2026-11-08 00:00:00\n') % (ce.stat().st_ino, de.stat().st_ino)
        def android(argv, timeout):
            return raw.encode() if argv[0] == '/system/bin/dumpsys' else b'package:/data/app/gallery-fixture/base.apk\n'
        session = types.SimpleNamespace(android=android, audio=types.SimpleNamespace(credentials=lambda: value),
            target=types.SimpleNamespace(read_file=lambda *args, **kwargs: (b'explicit APK fixture', {}),
                open_root=lambda path, flags: os.open(ce if '/data/user/' in path else de, flags)))
        driver = object.__new__(DRIVER.Driver); driver.s = session
        driver.c = types.SimpleNamespace(need=RUNTIME.need, sha=lambda raw: hashlib.sha256(raw).hexdigest())
        driver.record = lambda *args: None
        result = driver.gallery_identity('fixture')
        self.assertEqual(result['uid'], 10064)
        self.assertEqual(result['directories']['ce']['st_uid'], os.getuid())
        self.assertEqual(result['guest_credential_map'], value.receipt)

    def test_camera_directory_owners_are_compared_in_observer_namespace(self):
        value = self.credentials(self.target(uid_map=('10062 %d 1\n' % os.getuid()).encode(),
            gid_map=('10062 %d 1\n' % os.getgid()).encode()))
        ce, de = self.root / 'ce', self.root / 'de'; ce.mkdir(); de.mkdir()
        raw = ('Packages:\n  Package [com.android.camera2] (fixture):\n    appId=10062\n'
            '    versionCode=20002000 minSdk=37 targetSdk=1000\n    codePath=/data/app/camera-fixture\n'
            '    User 0: ceDataInode=%d deDataInode=%d installed=true hidden=false suspended=false\n'
            '      dataDir=/data/user/0/com.android.camera2\n'
            '      firstInstallTime=2026-11-08 00:00:00\n') % (ce.stat().st_ino, de.stat().st_ino)
        raw += ''.join('        ' + p + ': granted=true, flags=[]\n' for p in sorted(OBSERVATIONS.PERMISSIONS))
        def android(argv, timeout):
            return raw.encode() if argv[0] == '/system/bin/dumpsys' else b'package:/data/app/camera-fixture/base.apk\n'
        session = types.SimpleNamespace(android=android, audio=types.SimpleNamespace(credentials=lambda: value),
            target=types.SimpleNamespace(read_file=lambda *args, **kwargs: (b'explicit APK fixture', {}),
                open_root=lambda path, flags: os.open(ce if '/data/user/' in path else de, flags)),
            components={'camera_observations.py': OBSERVATIONS}, evidence_root=self.root,
            active={'framework_epoch_sha256': '0' * 64}, guard=lambda: None,
            tx=types.SimpleNamespace(write_new=lambda *args: None),
            c=types.SimpleNamespace(need=RUNTIME.need, sha=lambda raw: hashlib.sha256(raw).hexdigest()))
        result = BASE.Session.snapshot(session, 'acceptance-before')
        self.assertEqual(result['identity']['uid'], 10062)
        self.assertEqual(result['directories']['ce']['uid'], os.getuid())
        self.assertEqual(result['guest_credential_map'], value.receipt)


def protocol_document(uid=201041, gid=301041):
    values = [(900000, {'event': 'peer', 'pid': 9001, 'uid': uid, 'gid': gid,
        'expected_cgroup': '/system.slice/droidloomd.service', 'identity': 'SO_PEERPIDFD'}),
        (950000, {'event': 'stream_ready', 'source': BINDING.SOURCE_NAME, 'source_index': 3,
            'bus_path': BINDING.BUS_PATH, 'active_port': BINDING.INPUT_PORT,
            'rate': 48000, 'channels': 1, 'format': 's16le'}),
        (990000, {'event': 'capture_ack', 'captured_frames_acked': 10}),
        (1900000, {'event': 'capture_ack', 'captured_frames_acked': 43210})]
    return {'unit': 'droidloom-audio-capture.service', 'rows':
        [{'cursor': str(i), 'monotonic_us': timestamp, 'value': value} for i, (timestamp, value) in enumerate(values)]}


class PeerCredentialControls(unittest.TestCase):
    def window(self, doc, **overrides):
        kwargs = dict(role='input', hal_pid=9001, hal_uid=201041, hal_gid=301041,
            hal_cgroup='/system.slice/droidloomd.service', begin_ns=1000000000, end_ns=2000000000)
        kwargs.update(overrides)
        return BINDING.protocol_window(doc, **kwargs)

    def test_observer_peer_ids_and_distinct_gid_are_required(self):
        value = self.window(protocol_document())
        self.assertEqual(value['acknowledged_frames_in_window'], 43200)
        self.assertEqual(value['peer']['uid'], 201041)
        self.assertFalse(value['runtime_qualified'])

    def test_guest_peer_ids_and_wrong_gid_are_rejected(self):
        for uid, gid in ((1041, 1041), (201041, 201041), (201042, 301041)):
            with self.subTest(uid=uid, gid=gid), self.assertRaisesRegex(RuntimeError, 'SO_PEERPIDFD'):
                self.window(protocol_document(uid, gid))

    def test_invalid_expected_credentials_cannot_admit_a_peer(self):
        for values in ({'hal_uid': True}, {'hal_gid': -1}, {'hal_uid': 4294967295}, {'hal_gid': '301041'}):
            with self.subTest(values=values), self.assertRaises(RuntimeError): self.window(protocol_document(), **values)


if __name__ == '__main__':
    unittest.main(verbosity=2)
