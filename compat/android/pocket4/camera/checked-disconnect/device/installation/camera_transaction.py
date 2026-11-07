#!/usr/bin/python3 -I
"""One data-preserving Camera2 update, exact rollback, or read-only reconciliation.

The default is an inert plan. This module also exposes the held CameraSession
used by the separately reviewed UI acceptance script. It never restarts Main,
the camera provider, or another app; it never grants permissions or clears data.
"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import signal
import stat
import subprocess
import time
import types
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-camera-release08-20261105-r12')
RUN = ROOT / 'install-01'
CANDIDATE = ROOT / 'signed-build-01/Camera2-pocket4-checked-disconnect.apk'
NEW_SHA = '0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e'
OLD_SHA = '0f6fb58ea0b81be5f588ee35796d35e4de65d19e866a51ea0e4ac79b26012c4e'
APK_BYTES = 11892407
CERT_SHA = 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
PACKAGE, UID, VERSION = 'com.android.camera2', 10062, 20002000
MAIN_HOST, MAIN_INIT, INIT_START = 3588089, 3588093, 80797014
EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
EPOCH_SOURCE = Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
EPOCH_SOURCE_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
APP = Path('/usr/local/bin/android-app')
APP_SHA = 'eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66'
HELD_SHA = '72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'
ENTRY = Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry')
ENTRY_SHA = '21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689'
CLI = '/usr/bin/droidloomctl'
CLI_SHA = 'f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79'
RUNUSER = '/usr/sbin/runuser'
RUNUSER_SHA = '7a7f333e1190a1af74ac2ed371018c1b2e3e21bd847a7805e68157fe1805420e'
SOCKET = '/run/droidloom/control.sock'
ALEX_PREFIX = [RUNUSER, '-u', 'alex', '--', CLI, '--socket', SOCKET]
HOST_ENV = {'PATH': '/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}
UI_LOCK = '/run/lock/android-digitalis-actions.lock'
PERMISSIONS = {'android.permission.POST_NOTIFICATIONS', 'android.permission.CAMERA',
               'android.permission.RECORD_AUDIO', 'android.permission.ACCESS_FINE_LOCATION',
               'android.permission.ACCESS_COARSE_LOCATION'}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, expected=None, maximum=32 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                0 <= before.st_size <= maximum, 'REGULAR_BOUNDED_INPUT_REQUIRED')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        attrs = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(len(raw) == before.st_size and
                all(getattr(before, x) == getattr(after, x) for x in attrs), 'INPUT_CHANGED')
        require(expected is None or sha(raw) == expected, 'INPUT_HASH_CHANGED')
        return raw
    finally:
        os.close(fd)


def write_new(path, value, mode=0o600, alex_readable=False):
    path = Path(path)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        if alex_readable:
            os.fchown(fd, 0, 1000)
            os.fchmod(fd, 0o640)
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def load_module(path, pin, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(read_regular(path, pin), str(path), 'exec'), module.__dict__)
    return module


@contextmanager
def ui_lock():
    """Use the existing action lock; never acquire the provider owner lock."""
    fd = os.open(UI_LOCK, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        value = os.fstat(fd)
        require(stat.S_ISREG(value.st_mode) and value.st_uid == 0 and value.st_nlink == 1,
                'UI_LOCK_IDENTITY_INVALID')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def parse_identity(package_dump, guest_path):
    """Only the active package section; the factory copy is not installed state."""
    sections = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', package_dump, re.M | re.S)
    require(len(sections) == 1, 'ACTIVE_PACKAGE_SECTION_AMBIGUOUS')
    block = sections[0]
    require(re.findall(r'^  Package \[([^]]+)\]', block, re.M) == [PACKAGE], 'CAMERA_ACTIVE_PACKAGE_REQUIRED')

    def one(pattern, text=block):
        values = re.findall(pattern, text, re.M)
        require(len(values) == 1, 'ACTIVE_PACKAGE_FIELD_AMBIGUOUS')
        return values[0]

    user = one(r'^    User 0: (.*)$')
    require('installed=true' in user and 'hidden=false' in user and 'suspended=false' in user,
            'CAMERA_USER_STATE_INVALID')
    permissions = re.findall(r'^        (android\.permission\.[A-Z_]+): granted=(true|false), flags=\[(.*?)\]$', block, re.M)
    require(len(permissions) == len(PERMISSIONS) and {x[0] for x in permissions} == PERMISSIONS,
            'CAMERA_PERMISSION_SET_DIFFERS')
    value = {'uid': int(one(r'^    appId=(\d+)$')),
             'ce_inode': int(one(r'^ceDataInode=(\d+)', user)),
             'de_inode': int(one(r'\bdeDataInode=(\d+)', user)),
             'version': int(one(r'^    versionCode=(\d+) minSdk=37 targetSdk=1000$')),
             'data_dir': one(r'^      dataDir=(.*)$'),
             'first_install_time': one(r'^      firstInstallTime=(.*)$'),
             'runtime_permissions': {p: {'granted': g == 'true', 'flags': f} for p, g, f in permissions}}
    require(value['uid'] == UID and value['version'] == VERSION and
            value['data_dir'] == '/data/user/0/' + PACKAGE, 'CAMERA_IDENTITY_DIFFERS')
    require(str(Path(guest_path).parent) == one(r'^    codePath=(.*)$'), 'APK_PATH_AND_PACKAGE_DIFFER')
    return value


class CameraSession:
    """Fixed R16 Main and held namespace entry; no fresh PID selection per command."""
    epoch_sha256 = EPOCH_SHA

    def __init__(self, journal_dir):
        self.journal_dir = Path(journal_dir)
        self.target = None
        self.sequence = 0

    def __enter__(self):
        require(os.geteuid() == 0, 'ROOT_REQUIRED_FOR_HELD_NAMESPACE_ENTRY')
        self.journal_dir.mkdir(mode=0o700)
        self.activation = json.loads(read_regular(ACTIVATION, ACTIVATION_SHA))
        self.epoch = load_module(EPOCH_SOURCE, EPOCH_SOURCE_SHA, 'camera_fixed_epoch')
        self.held = load_module(HERE / 'references/held_runtime_r5.py', HELD_SHA, 'camera_held_runtime')
        self.helper = load_module(APP, APP_SHA, 'camera_original_android_app')
        for path, pin in ((ENTRY, ENTRY_SHA), (CLI, CLI_SHA), (RUNUSER, RUNUSER_SHA)):
            read_regular(path, pin)
        self.guard()
        init, environment, status = self.helper.discover()
        require(init == MAIN_INIT and status.get('host_pid') == MAIN_HOST, 'DISCOVERED_MAIN_DIFFERS')
        expected = self.activation['framework_epoch']['binding']['processes']['init']
        require(expected['host_pid'] == MAIN_INIT and expected['start_ticks'] == INIT_START,
                'ACTIVATION_INIT_BIRTH_DIFFERS')
        proc = os.open('/proc/' + str(MAIN_INIT), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            identity = self.held.proc_identity_at(proc, MAIN_INIT, time.monotonic() + 3)
        finally:
            os.close(proc)
        require(int(identity['start']) == INIT_START and identity['uid'] == ['0'] * 4 and
                identity['ns']['mnt'] == expected['namespaces']['mnt'] and
                identity['ns']['pid'] == expected['namespaces']['pid'], 'HELD_INIT_NOT_FIXED_GENERATION')
        self.target = self.held.HeldTarget(identity, ENTRY, ENTRY_SHA)
        try:
            self.environment = dict(environment)
            self.status = dict(status)
            required = {'PATH', 'BOOTCLASSPATH', 'DEX2OATBOOTCLASSPATH', 'ANDROID_ROOT', 'ANDROID_DATA', 'ANDROID_ART_ROOT'}
            require(required <= set(environment) <= self.helper.ENV_KEYS and
                    all(isinstance(v, str) and '\0' not in v for v in environment.values()), 'ANDROID_ENVIRONMENT_INVALID')
            self.helper.arun = self.android
            self.helper.discover = self.discover_fixed
            self.guard()
            self.caller_status('caller-before')
            write_new(self.journal_dir / 'binding.json', {'epoch_sha256': EPOCH_SHA,
                'activation_sha256': ACTIVATION_SHA, 'held': self.target.record,
                'command_entry_uses_numeric_pid': False, 'caller_uid': 1000, 'android_user': 0})
            return self
        except BaseException:
            self.target.close()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        if self.target is not None:
            self.target.close()

    def guard(self):
        read_regular('/etc/droidloom/cell.json', CELL_SHA)
        require(self.activation['framework_epoch']['sha256'] == EPOCH_SHA, 'FIXED_EPOCH_HASH_DIFFERS')
        self.epoch.require_unchanged(self.activation['framework_epoch'])
        for key in ('daemon_process', 'launcher_process', 'presenter_process'):
            expected = self.activation[key]
            require(self.epoch.process_identity(expected['host_pid']) == expected, 'MAIN_HOST_IDENTITY_CHANGED')
        limits = {key: (Path('/sys/fs/cgroup/system.slice/droidloomd.service') / key).read_text().strip()
                  for key in self.activation['limits']}
        require(limits == self.activation['limits'], 'MAIN_LIMITS_CHANGED')
        if self.target is not None:
            self.target.verify()
        return {'epoch_sha256': EPOCH_SHA, 'host_pid': MAIN_HOST, 'init_pid': MAIN_INIT, 'init_start_ticks': INIT_START}

    def discover_fixed(self):
        self.guard()
        return MAIN_INIT, dict(self.environment), dict(self.status)

    def run_host(self, label, argv, timeout=20, pass_fds=()):
        require(re.fullmatch(r'[a-z0-9-]+', label) and 0 < timeout <= 90, 'COMMAND_LABEL_OR_TIMEOUT_INVALID')
        self.guard()
        self.sequence += 1
        stem = self.journal_dir / ('%03d-' % self.sequence + label)
        record = {'argv': list(map(str, argv)), 'timeout_seconds': timeout, 'spawned': False,
                  'joined': False, 'timed_out': False, 'rc': None, 'automatic_retry': False}
        write_new(str(stem) + '.intent.json', record)
        process = None
        failure = None
        with open(str(stem) + '.stdout', 'xb') as out, open(str(stem) + '.stderr', 'xb') as err:
            try:
                process = subprocess.Popen(record['argv'], stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                           env=HOST_ENV, close_fds=True, pass_fds=pass_fds, start_new_session=True)
                record['spawned'] = True
                try:
                    record['rc'] = process.wait(timeout=timeout)
                    record['joined'] = True
                except subprocess.TimeoutExpired:
                    record['timed_out'] = True
                    # Match the existing recorder: only this newly created
                    # command session, never Main, provider, or Binder app work.
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    record['rc'] = process.wait(timeout=4)
                    record['joined'] = True
            except BaseException as exc:
                failure = exc
                record['error'] = type(exc).__name__ + ': ' + str(exc)
            finally:
                if process is not None and not record['joined']:
                    try:
                        if process.poll() is None:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        record['rc'] = process.wait(timeout=4)
                        record['joined'] = True
                    except BaseException as exc:
                        record['join_error'] = type(exc).__name__
                        if self.target is not None:
                            self.target.poison_unjoined_command()
                out.flush(); os.fsync(out.fileno())
                err.flush(); os.fsync(err.fileno())
        try:
            self.guard()
            record['guard_after'] = True
        except BaseException as exc:
            record['guard_after'] = False
            record['guard_error'] = type(exc).__name__ + ': ' + str(exc)
            failure = failure or exc
        write_new(str(stem) + '.result.json', record)
        if failure is not None:
            raise failure
        require(record['joined'], 'OWNED_COMMAND_NOT_JOINED')
        return {**record, 'stdout': read_regular(str(stem) + '.stdout'),
                'stderr': read_regular(str(stem) + '.stderr', maximum=1048576)}

    def android(self, argv, timeout=20):
        require(argv and all(isinstance(x, str) and x and '\0' not in x for x in argv)
                and argv[0].startswith('/') and 5 < timeout <= 90, 'ANDROID_COMMAND_INVALID')
        command = ['/system/bin/env', '-i'] + [k + '=' + self.environment[k] for k in sorted(self.environment)]
        command += ['/system/xbin/su', '2000', '/system/bin/timeout', '-k', '2', str(timeout - 4), *argv]
        read_regular(ENTRY, ENTRY_SHA)
        with self.target.entry(command) as (entry, descriptors):
            result = self.run_host('android', entry, timeout, descriptors)
        if result['timed_out']:
            raise subprocess.TimeoutExpired('<held Android command>', timeout)
        require(result['rc'] == 0, 'ANDROID_COMMAND_FAILED')
        return result['stdout']

    def caller_status(self, label):
        result = self.run_host(label, [*ALEX_PREFIX, 'status', '--json'], 10)
        require(result['rc'] == 0 and not result['timed_out'], 'ALEX_STATUS_FAILED')
        value = json.loads(result['stdout'])
        require(value.get('ok') is True and value.get('state') == 'running' and
                value.get('host_pid') == MAIN_HOST and 'cell u1000 ' in value.get('message', ''),
                'CLI_CALLER_OR_CELL_DIFFERS')
        return value

    def snapshot(self, label):
        require(re.fullmatch(r'[a-z0-9-]+', label), 'SNAPSHOT_LABEL_INVALID')
        paths = self.android(['/system/bin/pm', 'path', PACKAGE]).decode('utf-8', 'strict').splitlines()
        require(len(paths) == 1 and paths[0].startswith('package:/data/app/') and
                paths[0].endswith('/base.apk'), 'ONE_ACTIVE_CAMERA_APK_REQUIRED')
        guest = paths[0][len('package:'):]
        raw = self.android(['/system/bin/dumpsys', 'package', PACKAGE])
        write_new(self.journal_dir / (label + '-package.txt'), raw)
        identity = parse_identity(raw.decode('utf-8', 'strict'), guest)
        apk, metadata = self.target.read_file(guest, 32 * 1024 * 1024, single_link=True)
        dirs = {}
        for key, path in [('ce', '/data/user/0/' + PACKAGE), ('de', '/data/user_de/0/' + PACKAGE)]:
            fd = self.target.open_root(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                s = os.fstat(fd)
                dirs[key] = {'device': s.st_dev, 'inode': s.st_ino, 'uid': s.st_uid,
                             'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode)}
            finally:
                os.close(fd)
            require(dirs[key]['uid'] == dirs[key]['gid'] == UID and
                    dirs[key]['inode'] == identity[key + '_inode'], 'CAMERA_DATA_DIRECTORY_DIFFERS')
        self.guard()
        value = {'package': PACKAGE, 'epoch_sha256': EPOCH_SHA, 'identity': identity,
                 'directories': dirs, 'apk': {'guest_path': guest, 'bytes': len(apk), 'sha256': sha(apk)}}
        write_new(self.journal_dir / (label + '.json'), value)
        return value


def data_preserved(before, after):
    return (before['identity'] == after['identity'] and before['directories'] == after['directories']
            and before['epoch_sha256'] == after['epoch_sha256'] == EPOCH_SHA)


def verified_response(result):
    if result.get('rc') != 0 or result.get('timed_out') or not result.get('joined') or not result.get('guard_after'):
        return False
    try:
        value = json.loads(result['stdout'])
    except (ValueError, TypeError):
        return False
    # The archived successful install reader establishes rc=0 and ok=true.
    # Status fields are checked independently before and after the transaction;
    # do not guess that the install response must duplicate the status schema.
    return (isinstance(value, dict) and value.get('ok') is True and
            ('host_pid' not in value or value['host_pid'] == MAIN_HOST))


def classify_update(before, after, result, desired=NEW_SHA):
    if not verified_response(result):
        return 'INSTALL_OUTCOME_UNKNOWN'
    if after is None:
        return 'POST_INSTALL_READBACK_FAILED'
    if after['apk']['sha256'] != desired:
        return 'POST_INSTALL_APK_DIFFERS'
    if not data_preserved(before, after):
        return 'POST_INSTALL_DATA_IDENTITY_DIFFERS'
    return 'INSTALLED_VERIFIED'


def verify_signature(session, path, label):
    result = session.run_host(label, ['/usr/bin/apksigner', 'verify', '--verbose', '--print-certs', str(path)], 25)
    require(result['rc'] == 0 and not result['timed_out'], 'APK_SIGNATURE_FAILED')
    text = result['stdout'].decode('utf-8', 'strict')
    certs = re.findall(r'^Signer #\d+ certificate SHA-256 digest: (\w+)$', text, re.M)
    require(certs == [CERT_SHA] and 'Verified using v3 scheme (APK Signature Scheme v3): true' in text,
            'APK_SIGNER_OR_V3_DIFFERS')


def verify_payload(before, candidate):
    def keep(name):
        return not (re.fullmatch(r'classes\d*\.dex', name) or name.upper() == 'META-INF/MANIFEST.MF'
                    or re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC)', name, re.I))
    with zipfile.ZipFile(io.BytesIO(before)) as old, zipfile.ZipFile(io.BytesIO(candidate)) as new:
        require(len(old.namelist()) == len(set(old.namelist())) and len(new.namelist()) == len(set(new.namelist())),
                'DUPLICATE_APK_ENTRIES')
        names = {n for n in old.namelist() if keep(n)}
        require(names == {n for n in new.namelist() if keep(n)} and len(names) == 1045, 'APK_PAYLOAD_SET_DIFFERS')
        require(all(old.read(n) == new.read(n) for n in names), 'MANIFEST_RESOURCES_OR_NATIVE_BYTES_CHANGED')


def install_once(session, path, expected_sha, label):
    read_regular(path, expected_sha)
    session.caller_status(label + '-caller-before')
    # This durable intent is exclusive. Never replace it and never retry it.
    write_new(session.journal_dir / (label + '-dispatch.json'), {'apk_sha256': expected_sha,
        'host_uid': 1000, 'android_user': 0, 'host_pid': MAIN_HOST, 'epoch_sha256': EPOCH_SHA,
        'automatic_retry': False, 'apk_path': str(path)})
    return session.run_host(label, [*ALEX_PREFIX, 'install', str(path), '--user', '0', '--json'], 60)


def execute_update():
    # A busy UI lock must not consume the unique transaction directory.
    with ui_lock():
        return execute_update_locked()


def execute_update_locked():
    # A fixed create-only directory makes a second invocation fail before any update.
    RUN.mkdir(mode=0o750)
    os.chown(RUN, 0, 1000)
    os.chmod(RUN, 0o750)
    result = {'schema': 1, 'state': 'NOT_DISPATCHED', 'package': PACKAGE, 'epoch_sha256': EPOCH_SHA,
              'old_sha256': OLD_SHA, 'new_sha256': NEW_SHA, 'automatic_retry': False,
              'UI_actions': 0, 'provider_actions': 0, 'whole_app_production_ready': False}
    write_new(RUN / 'claim.json', result)
    try:
        with CameraSession(RUN / 'commands') as session:
            before = session.snapshot('before')
            require(before['apk']['sha256'] == OLD_SHA and before['apk']['bytes'] == APK_BYTES, 'PREIMAGE_IS_NOT_RELEASE07')
            tasks = session.android(['/system/bin/cmd', 'activity', 'stack', 'list'])
            write_new(RUN / 'tasks-before.txt', tasks)
            require(PACKAGE.encode() not in tasks, 'CAMERA_TASK_ALREADY_PRESENT')
            original, _ = session.target.read_file(before['apk']['guest_path'], 32 * 1024 * 1024, single_link=True)
            require(sha(original) == OLD_SHA, 'PREIMAGE_CHANGED_BEFORE_BACKUP')
            candidate = read_regular(CANDIDATE, NEW_SHA)
            require(len(candidate) == APK_BYTES, 'CANDIDATE_SIZE_DIFFERS')
            verify_payload(original, candidate)
            backup = RUN / 'release07-before.apk'
            staged = RUN / 'release08-candidate.apk'
            write_new(backup, original, alex_readable=True)
            write_new(staged, candidate, alex_readable=True)
            verify_signature(session, backup, 'old-signature')
            verify_signature(session, staged, 'new-signature')
            write_new(RUN / 'before.json', before)
            result['state'] = 'INSTALL_DISPATCHED'
            call = install_once(session, staged, NEW_SHA, 'install')
            result['install_response_verified'] = verified_response(call)
            after = None
            try:
                after = session.snapshot('after')
            except Exception as exc:
                result['post_read_error'] = type(exc).__name__ + ': ' + str(exc)
            result['state'] = classify_update(before, after, call, NEW_SHA)
            result['observed_apk_sha256'] = after['apk']['sha256'] if after else None
            result['data_identity_preserved'] = after is not None and data_preserved(before, after)
            # A lost daemon response is reconciled by reads only. No retry or rollback
            # may race an install whose completion is not known.
            if result['state'] == 'POST_INSTALL_DATA_IDENTITY_DIFFERS':
                result['state'] = 'ROLLBACK_DISPATCHED'
                rollback = install_once(session, backup, OLD_SHA, 'rollback-after-data-check')
                restored = session.snapshot('rollback-after')
                result['rollback_response_verified'] = verified_response(rollback)
                result['rollback_apk_sha256'] = restored['apk']['sha256']
                result['rollback_data_identity_preserved'] = data_preserved(before, restored)
                result['state'] = ('ROLLED_BACK_VERIFIED' if classify_update(before, restored, rollback, OLD_SHA) == 'INSTALLED_VERIFIED'
                                   else 'ROLLBACK_NOT_FULLY_VERIFIED')
            session.caller_status('caller-after')
            session.guard()
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        if result['state'] == 'INSTALL_DISPATCHED':
            result['state'] = 'INSTALL_OUTCOME_UNKNOWN'
        elif result['state'] == 'ROLLBACK_DISPATCHED':
            result['state'] = 'ROLLBACK_OUTCOME_UNKNOWN'
        elif result['state'] in ('INSTALLED_VERIFIED', 'ROLLED_BACK_VERIFIED'):
            result['state_before_final_guard_failure'] = result['state']
            result['state'] = 'FINAL_IDENTITY_CHECK_FAILED'
    finally:
        write_new(RUN / 'result.json', result)
    return result


def reconcile():
    claim = json.loads(read_regular(RUN / 'claim.json'))
    require(claim['old_sha256'] == OLD_SHA and claim['new_sha256'] == NEW_SHA and claim['epoch_sha256'] == EPOCH_SHA,
            'ORIGINAL_TRANSACTION_REQUIRED')
    before = json.loads(read_regular(RUN / 'before.json'))
    folder = RUN / ('reconcile-' + str(time.time_ns()))
    with ui_lock(), CameraSession(folder) as session:
        now = session.snapshot('current')
        result = {'state': 'READ_ONLY_RECONCILIATION', 'package': PACKAGE, 'epoch_sha256': EPOCH_SHA,
                  'observed_apk_sha256': now['apk']['sha256'], 'data_identity_preserved': data_preserved(before, now),
                  'current_is_release08': now['apk']['sha256'] == NEW_SHA,
                  'current_is_release07': now['apk']['sha256'] == OLD_SHA,
                  'installation_replayed': False, 'rollback_dispatched': False,
                  'historical_daemon_outcome_rewritten': False, 'whole_app_production_ready': False}
        write_new(folder / 'result.json', result)
        return result


def explicit_rollback():
    original = json.loads(read_regular(RUN / 'result.json'))
    require(original['state'] == 'INSTALLED_VERIFIED' and original.get('install_response_verified') is True,
            'ROLLBACK_REQUIRES_KNOWN_COMPLETED_UPDATE')
    before = json.loads(read_regular(RUN / 'before.json'))
    backup = RUN / 'release07-before.apk'
    read_regular(backup, OLD_SHA)
    folder = RUN / 'explicit-rollback-01'
    result = {'state': 'ROLLBACK_NOT_DISPATCHED', 'package': PACKAGE, 'epoch_sha256': EPOCH_SHA,
              'automatic_retry': False, 'whole_app_production_ready': False}
    with ui_lock():
        # CameraSession creates this fixed directory exclusively. Failure before
        # it is created leaves no misleading completed rollback receipt.
        try:
            with CameraSession(folder) as session:
                current = session.snapshot('before-rollback')
                require(current['apk']['sha256'] == NEW_SHA, 'ROLLBACK_REFUSES_UNOWNED_CURRENT_APK')
                require(data_preserved(before, current), 'ROLLBACK_DATA_IDENTITY_CHANGED')
                verify_signature(session, backup, 'rollback-signature')
                result['state'] = 'ROLLBACK_DISPATCHED'
                call = install_once(session, backup, OLD_SHA, 'rollback')
                after = session.snapshot('after-rollback')
                state = classify_update(before, after, call, OLD_SHA)
                result.update(state='ROLLED_BACK_VERIFIED' if state == 'INSTALLED_VERIFIED' else state,
                              rollback_response_verified=verified_response(call),
                              observed_apk_sha256=after['apk']['sha256'],
                              data_identity_preserved=data_preserved(before, after))
                session.caller_status('rollback-caller-after')
                session.guard()
        except BaseException as exc:
            result['error'] = type(exc).__name__ + ': ' + str(exc)
            if result['state'] == 'ROLLBACK_DISPATCHED':
                result['state'] = 'ROLLBACK_OUTCOME_UNKNOWN'
            elif result['state'] == 'ROLLED_BACK_VERIFIED':
                result['state_before_final_guard_failure'] = result['state']
                result['state'] = 'FINAL_IDENTITY_CHECK_FAILED'
        if folder.exists():
            write_new(folder / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('plan', 'install', 'reconcile', 'rollback'), default='plan')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.mode == 'plan':
        value = {'state': 'PLAN_ONLY', 'candidate': str(CANDIDATE), 'candidate_sha256': NEW_SHA,
                 'preimage_sha256': OLD_SHA, 'epoch_sha256': EPOCH_SHA, 'host_uid': 1000, 'android_user': 0,
                 'update_path': str(RUN), 'production_actions': 0}
    else:
        require(os.geteuid() == 0, 'ROOT_REQUIRED')
        require(args.mode == 'reconcile' or args.execute, 'EXPLICIT_EXECUTION_REQUIRED')
        value = {'install': execute_update, 'reconcile': reconcile, 'rollback': explicit_rollback}[args.mode]()
    print(json.dumps(value, indent=2))
    return 0 if value['state'] in ('PLAN_ONLY', 'INSTALLED_VERIFIED', 'ROLLED_BACK_VERIFIED', 'READ_ONLY_RECONCILIATION') else 1


if __name__ == '__main__':
    raise SystemExit(main())
