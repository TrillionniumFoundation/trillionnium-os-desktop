"""Final-Main App adapter primitives. Import performs no I/O or admission.

The source packet, Main baseline, package observations, phase plan and every
new recorder scope are separately bound. Historical files are provenance only.
"""
from contextlib import contextmanager
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
import types

FINAL = Path('/home/alex/work/pocket4-android-final')
QUALIFICATION = Path('/var/lib/droidloom/qualification/pocket4')
SUPPORT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/support')
SUPPORT_REF={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/support/source-manifest.json', 'bytes': 1001, 'sha256': 'c72ad0236f61ce7f0bd2e21e8143d2e4963c0c477de5057d92e8912db6dd633e'}
CLOCK_SUPPORT_REF={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/clock-support/source-manifest.json', 'bytes': 1001, 'sha256': '2c37ea0f7a15ffd333c710942aceb064b6dcd6e3a7344c5fd08d1bf310663f29'}
SCOPE_SHA='9a27966cf73b006630d4ee823b76a6a341225a0a49616ce131d8f11880c039f0'
GATES={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/contracts/app-gates.json', 'bytes': 24135, 'sha256': '35d566406aacc77ebe2dbd44430cea7f80533569647947c01772cd118aff3161'}
SIGNER = '/usr/bin/apksigner'
SIGNER_SHA = '52947059a664b85f0475bcdc3dbbe6089b50f8f59e3aa051e6e74cf0ba7db70f'
NATIVE_PREFIX = ['/usr/bin/sudo', '-n', '-u', '#1000', '--', '/usr/bin/env',
                 'XDG_RUNTIME_DIR=/run/user/1000',
                 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
                 '/usr/bin/droidloomctl']
HOST_ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LANG': 'C.UTF-8'}
STACKS = ['/system/bin/cmd', 'activity', 'stack', 'list']
FOREGROUND = ['/system/bin/dumpsys', 'window', 'displays']


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                       allow_nan=False) + '\n').encode('ascii')


def parse(raw):
    def pairs(values):
        out = {}
        for key, value in values:
            need(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    def constant(value):
        raise RuntimeError('NONFINITE_JSON_NUMBER')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def metadata(info):
    return tuple(getattr(info, key) for key in
                 ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
                  'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def regular(path, maximum=16 * 1024 * 1024, contents=True):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'REAL_CANONICAL_FILE_REQUIRED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             0 <= before.st_size <= maximum, 'BOUNDED_SINGLE_LINK_FILE_REQUIRED')
        digest = hashlib.sha256(); chunks = []; total = 0
        while True:
            block = os.read(fd, min(65536, maximum + 1 - total))
            if not block:
                break
            total += len(block); need(total <= maximum, 'FILE_READ_BOUND')
            digest.update(block)
            if contents:
                chunks.append(block)
        need(total == before.st_size and metadata(before) == metadata(os.fstat(fd))
             == metadata(path.lstat()), 'FILE_CHANGED_DURING_READ')
        ref = {'path': str(path), 'bytes': total, 'sha256': digest.hexdigest()}
        return (b''.join(chunks), ref) if contents else ref
    finally:
        os.close(fd)


def read_ref(ref, maximum=16 * 1024 * 1024):
    need(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'} and
         type(ref['bytes']) is int and type(ref['sha256']) is str and
         re.fullmatch('[0-9a-f]{64}', ref['sha256']), 'EXACT_REFERENCE_REQUIRED')
    raw, observed = regular(ref['path'], maximum)
    need(observed == ref, 'REFERENCE_CHANGED')
    return raw


def write_new(path, value, mode=0o600):
    path = Path(path); raw = value if type(value) is bytes else canonical(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def private_dir(path, create=False):
    path = Path(path)
    need(path.is_absolute() and path.parent.resolve() == path.parent, 'EXACT_PRIVATE_PARENT_REQUIRED')
    if create:
        path.mkdir(mode=0o700)
    info = path.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077
         and path.resolve() == path, 'ROOT_PRIVATE_DIRECTORY_REQUIRED')
    return path


@contextmanager
def locked(path, wait_seconds=0):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1,
             'PRIVATE_LOCK_REQUIRED')
        need(type(wait_seconds) in (int, float) and 0 <= wait_seconds <= 5, 'BOUNDED_ORIGINAL_ACTION_LOCK_WAIT')
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(.05, remaining))
        yield
    finally:
        os.close(fd)


def module(ref, name):
    raw = read_ref(ref, 2 * 1024 * 1024)
    value = types.ModuleType(name); value.__file__ = ref['path']
    exec(compile(raw, ref['path'], 'exec'), value.__dict__)
    return value


def support(support_ref=SUPPORT_REF):
    need(support_ref in (SUPPORT_REF, CLOCK_SUPPORT_REF), 'EXACT_REVIEWED_BUSINESS_SUPPORT_REQUIRED')
    manifest = parse(read_ref(support_ref, 131072))
    row = manifest['files']['business_scope.py']
    need(row['sha256'] == SCOPE_SHA, 'FROZEN_SCOPE_HELPER_REQUIRED')
    scope = module({'path': str(Path(support_ref['path']).parent / 'business_scope.py'), **row}, 'final_app_scope_support')
    modules = scope.load_bundle(support_ref)
    return scope, modules


def packet_module(scope_value, name):
    scope, _ = support(scope_value['support_manifest'])
    packet = scope.validate_packet(parse(read_ref(scope_value['task_source_manifest'])), scope_value)
    files = [row for row in packet['files'] if Path(row['path']).name == name]
    need(len(files) == 1, 'EXACT_NEW_PACKET_MODULE_REQUIRED:' + name)
    return module(files[0], 'final_app_packet_' + Path(name).stem)


def match_held(target, baseline, scope):
    expected = baseline.value['framework_epoch']['binding']['processes']['init']
    observed = baseline.value['observation']; raw = target.expected
    need(raw['pid'] == expected['host_pid'] and int(raw['start']) == expected['start_ticks']
         and raw['ppid'] == expected['parent_host_pid'] and raw['uid'] == [str(x) for x in expected['uids']]
         and [int(x) for x in raw['nspid']] == expected['namespace_pids']
         and raw['exe'] == expected['executable'] and raw['cgroup'].splitlines() == expected['cgroup']
         and set(raw['ns']) == {'mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup'}
         and all(raw['ns'][k] == observed['namespaces']['init'][k]['link'] for k in raw['ns'])
         and all(target.root_record[k] == observed['roots']['init'][k] for k in ('device', 'inode')),
         'HELD_INIT_MUST_BE_ACTUAL_NEW_MAIN')
    need(target.helper_path == scope.HELPER_PATH and target.helper_sha256 == scope.HELD_HELPER_SHA256,
         'ORIGINAL_HELD_ENTRY_PROTOCOL_REQUIRED')
    need(target.main_user_namespace == baseline.docs['runtime_observation']['main_user_namespace'],
         'HELD_TARGET_MUST_RETAIN_THE_SAME_MAIN_USER_NAMESPACE')
    target.verify()


class MainView:
    """An actual held Main, with an explicit narrow caller command admission.

    Bootstrap use admits package reads only. A case may additionally admit its
    original literal root SQL reads. It never accepts an arbitrary root argv.
    """
    def __init__(self, baseline_ref, qualification_ref, journal, admission, full_guard=None, support_ref=SUPPORT_REF):
        self.scope, self.modules = support(support_ref); self.commands = self.modules['business_commands.py']
        self.baseline = self.modules['business_baseline.py'].BusinessBaseline(baseline_ref, qualification_ref)
        self.journal = private_dir(journal); self.admission = admission
        self.extra_guard = full_guard; self.index = 0; self.closed = False; self.target = None
        self._apk_custody = None
        self.environment = self.scope.environment_values(self.baseline.docs['runtime_observation']['android_env'])
        self.baseline.guard()
        reader = self.baseline.data
        held = module({'path': str(reader.READER_PATH), 'bytes': reader.READER_BYTES, 'sha256': reader.READER_SHA},
                      'final_app_held_runtime')
        identity = self.baseline.value['framework_epoch']['binding']['processes']['init']
        proc = os.open('/proc/' + str(identity['host_pid']),
                       os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            actual = held.proc_identity_at(proc, identity['host_pid'], time.monotonic() + 3)
        finally:
            os.close(proc)
        try:
            self.target = held.HeldTarget(actual, self.scope.HELPER_PATH, self.scope.HELD_HELPER_SHA256,
                main_user_namespace=self.baseline.docs['runtime_observation']['main_user_namespace'])
            self.target._normal_apk_custody_factory = self.apk_custody
            helper = module(self.scope.HELPER_CONTRACT, 'final_app_shared_entry_contract_only')
            self.helper_qualification = helper.verify_shared_helper(self.baseline)
            self.guard()
        except BaseException:
            if self.target is not None:
                self.target.close()
            raise

    def guard(self, *, action_attempted=False):
        need(not self.closed, 'HELD_MAIN_VIEW_CLOSED')
        value = self.baseline.guard(action_attempted=action_attempted)
        if self.target is not None:
            match_held(self.target, self.baseline, self.scope)
        if self.extra_guard is not None:
            self.extra_guard(attempted=action_attempted)
        return value

    def apk_custody(self):
        need(not self.closed, 'HELD_MAIN_VIEW_CLOSED')
        if self._apk_custody is None:
            self._apk_custody = self.commands.native_channel_module().ComparisonChannel().apk_custody()
        return self._apk_custody

    def _package_command(self, argv, timeout, root_read, private, kind, package):
        need(timeout == 15 and not root_read and not private,
             'FIXED_ROLE_PACKAGE_QUERY_REQUIRES_ORIGINAL_FIFTEEN_SECONDS')
        self.guard(); self.index += 1; name = 'read-%03d' % self.index
        logical = {'argv': list(argv), 'root_read': False, 'private_output': False,
                   'epoch_sha256': self.baseline.value['framework_epoch']['sha256'],
                   'command_timeout_seconds': 15, 'Android_mutation': False, 'automatic_retry': False}
        write_new(self.journal / (name + '.logical.json'), logical)
        primary = None; comparison = None; completed = None; post_guard = None
        try:
            stdout, stderr, comparison = self.apk_custody().package_read(kind, package)
            stdout_ref = write_new(self.journal / (name + '.stdout'), stdout)
            stderr_ref = write_new(self.journal / (name + '.stderr'), stderr)
            compared_ref = write_new(self.journal / (name + '.comparison.json'), comparison)
            completed = {'schema': 'droidloom.native-leaf-package-result.v1',
                         'argv': list(argv), 'stdout': stdout_ref, 'stderr': stderr_ref,
                         'comparison': compared_ref, 'query_retirement_proved': True,
                         'original_apk_reader_retired': False, 'host_subprocess_started': False,
                         'evidence_complete': True, 'returncode': 0, 'timed_out': False,
                         'errors': [], 'first_error': None}
        except BaseException as error:
            primary = error
            comparison = getattr(error, 'native_package_comparison', None)
            if comparison is not None:
                write_new(self.journal / (name + '.failed-comparison.json'), comparison)
        finally:
            try:
                post_guard = self.guard()
            except BaseException as error:
                if primary is None: primary = error
                else: primary.add_note('NORMAL_PACKAGE_POST_GUARD:' + type(error).__name__)
        transport = {'schema': 'droidloom.native-leaf-package-transport.v1',
                     'logical': logical, 'post_guard': post_guard,
                     'normal_factory_query_observed': completed is not None,
                     'host_subprocess_started': False, 'original_apk_reader_retired': False,
                     'error_type': None if primary is None else type(primary).__name__,
                     'Binder_task_cleanup_verified': False, 'Binder_UID_cleanup_verified': False}
        transport_ref = write_new(self.journal / (name + '.transport.json'), transport)
        if primary is not None:
            raise primary
        result_ref = write_new(self.journal / (name + '.result.json'), completed)
        return stdout, {'path': result_ref['path'], 'logical': logical, 'transport': transport_ref,
                        'command_observation': {'normal_query_retirement_proved': True,
                                                'host_subprocess_started': False}}

    def command(self, argv, timeout=20, *, root=False, private=False, inner_timeout=None, output_bound=1024 * 1024):
        need(type(root) is bool and type(private) is bool and type(timeout) in (int, float)
             and 5 < timeout <= 70, 'EXPLICIT_BOUNDED_READ_MODE_REQUIRED')
        self.admission(list(argv), timeout, root, private)
        need(output_bound in (1024 * 1024, 16 * 1024 * 1024), 'QUALIFIED_READ_CAPTURE_BOUND_REQUIRED')
        fixed = fixed_package_read(list(argv))
        if fixed is not None:
            need(inner_timeout is None, 'FIXED_PM_QUERY_HAS_NO_NESTED_TIMEOUT_WRAPPER')
            return self._package_command(list(argv), timeout, root, private, *fixed)
        inner = max(1, timeout - 5) if inner_timeout is None else inner_timeout
        need(inner_timeout is None or (root and timeout == 16 and inner_timeout == 12),
             'EXPLICIT_ORIGINAL_ROOT_SQL_TIMEOUT_ONLY')
        self.guard(); self.index += 1; name = 'read-%03d' % self.index
        logical = {'argv': list(argv), 'root_read': root, 'private_output': private,
                   'epoch_sha256': self.baseline.value['framework_epoch']['sha256'],
                   'inner_timeout_seconds': inner,
                   'Android_mutation': False, 'automatic_retry': False}
        write_new(self.journal / (name + '.logical.json'), logical)
        command = ['/system/bin/env', '-i'] + [k + '=' + self.environment[k] for k in sorted(self.environment)]
        if not root:
            command += ['/system/xbin/su', '2000']
        command += ['/system/bin/timeout', '-k', '2', str(inner), *argv]
        primary = None; completed = None; manager = self.target.entry(command)
        entered = False; released = False; post_guard = None
        try:
            physical, descriptors = manager.__enter__()
            entered = True
            completed = self.commands.run_recorded(name, physical, timeout, self.journal, self.guard,
                protected_pids=self.baseline.protected_pids, mutation=False, pass_fds=descriptors,
                host_env=HOST_ENV, check=False, deferred_post_guard=True,
                private_output=private, output_bound=16 * 1024 * 1024 if private else output_bound)
        except BaseException as error:
            primary = error
            if getattr(error, 'command_observation', {}).get('host_retirement_proved') is not True:
                self.target.poison_unjoined_command()
            else:
                self.target.seal_admission()
        finally:
            try:
                if entered:
                    manager.__exit__(None if primary is None else type(primary), primary,
                                     None if primary is None else primary.__traceback__)
                    released = True
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note('HELD_READ_LEASE_EXIT:' + type(error).__name__)
            try:
                post_guard = self.guard()
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note('HELD_READ_POST_GUARD:' + type(error).__name__)
        transport = {'schema': 'pocket4-final-app-read-transport-v1', 'logical': logical,
            'lease_entered': entered, 'lease_released': released, 'post_guard': post_guard,
            'host_retirement_proved': bool(completed and completed.host_tree_retired),
            'error_type': None if primary is None else type(primary).__name__,
            'Binder_task_cleanup_verified': False, 'Binder_UID_cleanup_verified': False}
        transport_ref = write_new(self.journal / (name + '.transport.json'), transport)
        if primary is not None:
            raise primary
        need(completed.returncode == 0 and completed.recorder_errors == []
             and completed.host_tree_retired and not completed.host_timed_out,
             'ACTUAL_READ_COMMAND_FAILED_OR_UNRETIRED')
        return completed.stdout, {'path': str(self.journal / (name + '.result.json')),
                                 'logical': logical, 'transport': transport_ref,
                                 'command_observation': completed.command_observation}

    def close(self):
        self.closed = True
        if self._apk_custody is not None:
            self._apk_custody.close()
        if self.target is not None:
            self.target._normal_apk_custody_factory = None
            self.target.close()


def package_commands(package, resolve):
    listed = ['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--show-versioncode', '--user', '0', package]
    paths = ['/system/bin/cmd', 'package', 'path', '--user', '0', package]
    result = [listed, paths]
    if resolve:
        result.append(['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
                       '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', package])
    result += [paths, listed]
    return result


def fixed_package_read(argv):
    if not argv or type(argv[-1]) is not str:
        return None
    package = argv[-1]
    values = package_commands(package, True)
    for kind, literal in zip(('identity', 'paths', 'launcher'), values[:3]):
        if argv == literal:
            return kind, package
    return None


def target_apk_custody(target):
    factory = getattr(target, '_normal_apk_custody_factory', None)
    need(callable(factory), 'ACTUAL_NORMAL_MAIN_VIEW_APK_CHANNEL_REQUIRED')
    return factory()


def package_metadata(raw, expected):
    lines = raw.decode('utf-8', 'strict').splitlines()
    need(len(lines) == 1, 'ONE_EXACT_PACKAGE_METADATA_ROW_REQUIRED')
    # Preserve the actual cmd-package --show-versioncode field order; reject extras.
    match = re.fullmatch(r'package:([^\s]+) versionCode:([0-9]+) uid:([0-9]+)', lines[0])
    if match is None:
        match = re.fullmatch(r'package:([^\s]+) uid:([0-9]+) versionCode:([0-9]+)', lines[0])
        need(match is not None, 'EXACT_UID_VERSION_METADATA_REQUIRED')
        package, uid, version = match[1], int(match[2]), int(match[3])
    else:
        package, version, uid = match[1], int(match[2]), int(match[3])
    need(package == expected['package'] and uid == expected['uid'] and
         (expected.get('version_code') is None or version == expected['version_code']),
         'PACKAGE_UID_OR_VERSION_CHANGED')
    return {'package': package, 'uid': uid, 'version_code': version, 'user': 0}


def apk_paths(raw):
    lines = raw.decode('utf-8', 'strict').splitlines()
    need(1 <= len(lines) <= 32 and len(lines) == len(set(lines)), 'EXACT_APK_PATH_SET_REQUIRED')
    paths = []
    for line in lines:
        need(line.startswith('package:/'), 'APK_PATH_PREFIX_REQUIRED')
        path = line[8:]
        need(str(Path(path)) == path and '..' not in Path(path).parts and '\0' not in path
             and path.endswith('.apk') and len(path) <= 1024, 'EXACT_GUEST_APK_PATH_REQUIRED')
        paths.append(path)
    return paths


def validate_artifacts(artifacts, expected):
    need(type(artifacts) is list and len(artifacts) == len(expected['apks']), 'EXACT_APK_COUNT_REQUIRED')
    actual = sorted((row['bytes'], row['sha256']) for row in artifacts)
    wanted = expected['apks']
    if all('bytes' in row for row in wanted):
        need(actual == sorted((row['bytes'], row['sha256']) for row in wanted), 'EXPECTED_APK_BYTES_CHANGED')
    else:
        need(sorted(row['sha256'] for row in artifacts) == sorted(row['sha256'] for row in wanted),
             'EXPECTED_APK_HASH_CHANGED')
    for row in artifacts:
        need(type(row.get('stat_file')) is dict and set(row['stat_file']) == set(row['held_file']) | {'ctime_ns'}
            and all(row['stat_file'][key] == value for key, value in row['held_file'].items())
            and type(row['stat_file']['ctime_ns']) is int and row['stat_file']['ctime_ns'] >= 0,
            'ACTUAL_COMPLETE_APK_FILE_IDENTITY_REQUIRED')


def full_artifact(target, artifact):
    """Recheck the real owner's original FD; this host holds only its comparison."""
    custody = target_apk_custody(target)
    custody.guard(full=True)
    matches = [row for row in custody.originals if row['apk']['path'] == artifact['guest_path']]
    need(len(matches) == 1, 'ORIGINAL_APK_MUST_BELONG_TO_THE_ACTUAL_FIXED_GROUP')
    original = matches[0]; info = original['identity']
    held = {'device': info['dev'], 'inode': info['ino'], 'mode': info['mode'],
            'uid': info['uid'], 'gid': info['gid'], 'bytes': info['bytes'],
            'mtime_ns': info['mtime'] * 10**9 + info['mtime_nsec'], 'nlink': info['nlink']}
    need(artifact['bytes'] == original['apk']['bytes'] and artifact['sha256'] == original['apk']['sha256']
         and artifact['held_file'] == held, 'ACTUAL_COMPLETE_ORIGINAL_APK_IDENTITY_CHANGED')
    return {**held, 'ctime_ns': info['ctime'] * 10**9 + info['ctime_nsec']}


def current_qualification_support(baseline_ref, qualification_ref):
    # The normal v1 qualification binds the compiled source recipe, not an old
    # deployment source_manifest. Both recorder families are fixed source inputs.
    # This value only chooses a comparison module; that module then compares the
    # document with the retained normal Rust channel before returning anything.
    document = parse(read_ref(baseline_ref))
    need(document.get('schema') == 'droidloom.native-leaf-business-baseline.v1',
         'CURRENT_KERNEL_FIRST_BASELINE_REQUIRED')
    package = document['native_owner']['application']['package']
    selected = CLOCK_SUPPORT_REF if package == 'com.android.deskclock' else SUPPORT_REF
    _, modules = support(selected)
    baseline = modules['business_baseline.py'].BusinessBaseline(baseline_ref, qualification_ref)
    need(baseline.value == document, 'CURRENT_BASELINE_CHANGED_DURING_SOURCE_SELECTION')
    baseline.guard()
    return selected


def validate_identity(receipt, expected, baseline_ref, qualification_ref, *, final=True):
    need(receipt.get('schema') == 'pocket4-final-app-identity-v1' and receipt.get('state') == 'OBSERVED'
         and receipt.get('baseline') == baseline_ref and receipt.get('qualification') == qualification_ref
         and receipt.get('source_scope') == 'metadata-signature-resolution-only'
         and receipt.get('Android_UI_actions') == 0 and receipt.get('app_launches') == 0
         and receipt.get('whole_app_business_accepted') is False, 'ACTUAL_NEW_APP_IDENTITY_RECEIPT_REQUIRED')
    qualification_source = current_qualification_support(baseline_ref, qualification_ref)
    need(qualification_source in (SUPPORT_REF, CLOCK_SUPPORT_REF) and
         receipt.get('support_manifest') == qualification_source, 'EXACT_IDENTITY_QUALIFICATION_SOURCE_REQUIRED')
    if final:
        need(receipt.get('held_binding_closed') is True and receipt.get('source_unchanged') is True,
             'COMPLETED_IDENTITY_LEASE_AND_SOURCE_RECHECK_REQUIRED')
    read_ref(receipt['source'])
    need(receipt['expected'] == expected, 'APP_EXPECTATIONS_CHANGED')
    commands = receipt['observations']; wanted = package_commands(expected['package'], bool(expected.get('component')))
    need(len(commands) == len(wanted), 'EXACT_ORIGINAL_READ_COUNT_REQUIRED')
    outputs = []; actual_role = None
    native_main = parse(read_ref(baseline_ref))['native_owner']['main']
    channel_module = support(qualification_source)[1]['business_commands.py'].native_channel_module()
    for row, argv in zip(commands, wanted):
        need(row['logical']['argv'] == argv and row['logical']['root_read'] is False
             and row['logical']['private_output'] is False and row['logical']['Android_mutation'] is False,
             'APP_OBSERVER_COMMAND_SCOPE_CHANGED')
        observed = parse(read_ref(row['result']))
        transport = parse(read_ref(row['transport']))
        need(transport['schema'] == 'droidloom.native-leaf-package-transport.v1'
             and transport['logical'] == row['logical']
             and transport['normal_factory_query_observed'] is True
             and transport['host_subprocess_started'] is False
             and transport['original_apk_reader_retired'] is False
             and transport['error_type'] is None
             and transport['post_guard']['business_baseline_sha256'] == baseline_ref['sha256']
             and transport['post_guard']['business_qualification_sha256'] == qualification_ref['sha256'],
             'ACTUAL_NORMAL_PM_QUERY_AND_MAIN_POST_GUARD_REQUIRED')
        need(observed['schema'] == 'droidloom.native-leaf-package-result.v1'
             and observed['query_retirement_proved'] is True
             and observed['original_apk_reader_retired'] is False
             and observed['host_subprocess_started'] is False
             and observed['evidence_complete'] is True and observed['argv'] == argv
             and observed['returncode'] == 0 and observed['timed_out'] is False
             and observed['errors'] == [] and observed.get('first_error') is None,
             'APP_METADATA_NORMAL_QUERY_NOT_SUCCESSFULLY_RETIRED')
        raw = read_ref(observed['stdout'], 65536)
        need(read_ref(observed['stderr'], 65536) == b'', 'UNEXPECTED_PACKAGE_DIAGNOSTIC')
        comparison = parse(read_ref(observed['comparison'], 262144))
        need(comparison['schema'] == 'droidloom.native-leaf-package-read.v2'
             and comparison['ordinal'] == 0
             and comparison['main_before'] == comparison['main_after'] == native_main
             and comparison['application']['package'] == expected['package']
             and comparison['application']['uid'] == expected['uid']
             and comparison['application']['user'] == 0
             and comparison['receipt']['output_bytes'] == len(raw)
             and comparison['receipt']['output_sha256'] == sha(raw),
             'SAVED_QUERY_OUTPUT_MUST_MATCH_ITS_ACTUAL_FACTORY_COMPARISON')
        # This only reparses a saved comparison. A current run separately borrows
        # its live original APK owner before accepting these identity fields.
        kind = fixed_package_read(argv)[0]
        need(comparison['kind'] == kind, 'SAVED_QUERY_KIND_CHANGED')
        if actual_role is None: actual_role = comparison['application']
        need(comparison['application'] == actual_role, 'SAVED_COMPLETE_ROLE_PM_CHANGED_BETWEEN_QUERIES')
        channel_module._apk_query_receipt(comparison['receipt'], raw, kind)
        encoded = comparison['stdout_base64']
        import base64
        need(base64.b64encode(raw).decode('ascii') == encoded
             and comparison['stderr_base64'] == '' and comparison['stderr_bytes'] == 0
             and comparison['stderr_sha256'] == sha(b''),
             'SAVED_NORMAL_QUERY_COMPLETE_OUTPUT_DIFFERS')
        outputs.append(raw)
    before = package_metadata(outputs[0], expected); after = package_metadata(outputs[-1], expected)
    need(before == after == receipt['metadata'] and outputs[1] == outputs[-2], 'APP_METADATA_CHANGED_DURING_OBSERVATION')
    paths = apk_paths(outputs[1]); artifacts = receipt['artifacts']
    need([row['guest_path'] for row in artifacts] == paths, 'ARTIFACT_PATH_CHAIN_CHANGED')
    validate_artifacts(artifacts, expected)
    need(actual_role is not None and
         sorted((a['path'],a['bytes'],a['sha256']) for a in actual_role['apks']) ==
         sorted((a['guest_path'],a['bytes'],a['sha256']) for a in artifacts),
         'ACTUAL_NORMAL_PM_WHOLE_APK_SET_MUST_MATCH_SIGNED_COPIES')
    if expected.get('component'):
        need(outputs[2].decode('utf-8', 'strict').splitlines() == [expected['component']]
             and receipt['component'] == expected['component'], 'UNIQUE_ACTUAL_LAUNCHER_REQUIRED')
    for artifact in artifacts:
        original, copied = artifact['original_custody'], artifact['sealed_copy']
        need(artifact['original_apk_descriptor_on_host'] is False
             and copied['original'] == original and original['package'] == expected['package']
             and original['apk']['path'] == artifact['guest_path']
             and original['apk']['bytes'] == artifact['bytes']
             and original['apk']['sha256'] == copied['sealed_copy_sha256'] == artifact['sha256']
             and copied['seals'] == channel_module.SEALS,
             'SAVED_ORIGINAL_AND_SEALED_COPY_PROVENANCE_DIFFERS')
        channel_module._apk_file(original['identity'], artifact['bytes'])
        channel_module._apk_file(copied['sealed_copy'], artifact['bytes'], copy=True)
        need((original['identity']['dev'],original['identity']['ino']) !=
             (copied['sealed_copy']['dev'],copied['sealed_copy']['ino']),
             'SEALED_COPY_MUST_NEVER_CLAIM_THE_ORIGINAL_INODE')
        need(regular(artifact['private_copy']['path'], 512 * 1024 * 1024, contents=False)
             == artifact['private_copy'], 'SIGNED_PRIVATE_APK_COPY_CHANGED')
        signed = parse(read_ref(artifact['signature']['result']))
        need(signed['host_retirement_proved'] is True and signed['evidence_complete'] is True
             and signed['returncode'] == 0 and signed['timed_out'] is False
             and signed['errors'] == [] and signed.get('first_error') is None,
             'APK_SIGNATURE_OBSERVER_NOT_SUCCESSFULLY_RETIRED')
        need(signed['argv'] == [SIGNER, 'verify', '--verbose', '--print-certs', artifact['private_copy']['path']],
             'SIGNATURE_OBSERVER_DID_NOT_VERIFY_THIS_APK')
        text = read_ref(signed['stdout']).decode('utf-8', 'strict')
        certificates = re.findall(r'^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})\r?$', text, re.M)
        need(len(certificates) == 1 and re.search(r'^Number of signers: 1\r?$', text, re.M)
             and certificates[0].lower() == artifact['signature']['certificate_sha256'], 'ACTUAL_APK_SIGNATURE_REQUIRED')
        if expected.get('certificate_sha256'):
            need(certificates[0].lower() == expected['certificate_sha256'], 'ORIGINAL_EXPECTED_SIGNER_CHANGED')
        if expected.get('require_v3'):
            need('Verified using v3 scheme (APK Signature Scheme v3): true' in text,
                 'ORIGINAL_V3_SIGNATURE_REQUIREMENT_NOT_MET')
        need(artifact['private_copy']['sha256'] == artifact['sha256']
             and artifact['private_copy']['bytes'] == artifact['bytes'], 'SIGNED_COPY_NOT_ACTUAL_GUEST_APK')
    return receipt


def collect_identity(request, output, expected, source_ref):
    """Five actual target reads and signatures; call only after a real new Main."""
    need(os.getuid() == os.geteuid() == 0 and set(request) == {'baseline', 'qualification'},
         'ACTUAL_NEW_MAIN_REFERENCES_REQUIRED')
    read_ref(source_ref); read_ref(GATES)
    support_ref = current_qualification_support(request['baseline'], request['qualification'])
    need(support_ref in (SUPPORT_REF, CLOCK_SUPPORT_REF), 'EXACT_QUALIFICATION_SUPPORT_COHORT_REQUIRED')
    root = private_dir(output, create=True); journal = private_dir(root / 'commands', create=True)
    wanted = package_commands(expected['package'], bool(expected.get('component'))); index = 0
    def admission(argv, timeout, root_read, private):
        nonlocal index
        need(index < len(wanted) and argv == wanted[index] and timeout == 15
             and not root_read and not private, 'FIVE_ORIGINAL_READONLY_COMMANDS_ONLY')
        index += 1
    view = None; result = {'schema': 'pocket4-final-app-identity-v1', 'state': 'FAILED',
        **request, 'expected': expected, 'source': source_ref, 'support_manifest': support_ref,
        'source_scope': 'metadata-signature-resolution-only', 'observations': [], 'artifacts': [],
        'Android_UI_actions': 0, 'app_launches': 0, 'whole_app_business_accepted': False,
        'commercial_publisher_identity_qualified': False, 'automatic_retry': False}
    try:
        view = MainView(request['baseline'], request['qualification'], journal, admission, support_ref=support_ref)
        outputs = []
        for n, argv in enumerate(wanted):
            raw, row = view.command(argv, 15)
            row['result'] = regular(row.pop('path'), contents=False)
            row.pop('command_observation'); result['observations'].append(row); outputs.append(raw)
            if n != 1:
                continue
            paths = apk_paths(raw)
            result['artifacts'] = view.apk_custody().copy_all(expected['package'], paths, root)
        result['metadata'] = package_metadata(outputs[0], expected)
        result['component'] = expected.get('component')
        validate_artifacts(result['artifacts'], expected)
        signer = Path(SIGNER).resolve(strict=True); signer_pin = regular(signer, contents=False)
        need(signer_pin['sha256'] == SIGNER_SHA, 'ORIGINAL_APKSIGNER_CHANGED')
        for k, artifact in enumerate(result['artifacts']):
            name = 'signature-%02d' % k
            value = view.commands.run_recorded(name, [SIGNER, 'verify', '--verbose', '--print-certs',
                artifact['private_copy']['path']], 45, journal, view.guard,
                protected_pids=view.baseline.protected_pids)
            certs = re.findall(rb'^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})\r?$', value.stdout, re.M)
            need(len(certs) == 1, 'ONE_VERIFIED_APK_SIGNER_REQUIRED')
            artifact['signature'] = {'certificate_sha256': certs[0].decode().lower(),
                'result': regular(journal / (name + '.result.json'), contents=False)}
        need(regular(signer, contents=False) == signer_pin, 'APKSIGNER_CHANGED_DURING_OBSERVATION')
        view.apk_custody().guard(full=True)
        for artifact in result['artifacts']:
            need(regular(artifact['private_copy']['path'], 512 * 1024 * 1024, contents=False)
                 == artifact['private_copy'], 'ACTUAL_SIGNED_PUBLIC_APK_COPY_CHANGED')
        view.guard(); result['epoch_sha256'] = view.baseline.value['framework_epoch']['sha256']
        result['state'] = 'OBSERVED'; validate_identity(result, expected, request['baseline'], request['qualification'], final=False)
    except BaseException as error:
        result['state'] = 'UNKNOWN' if getattr(error, 'command_observation', {}).get('host_retirement_proved') is False else 'FAILED'
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        if view is not None:
            try:
                view.close(); result['held_binding_closed'] = True
            except BaseException as error:
                result['state'] = 'UNKNOWN'; result['held_binding_closed'] = False
                result['close_error'] = type(error).__name__
        try:
            read_ref(source_ref); result['source_unchanged'] = True
        except BaseException as error:
            result['source_unchanged'] = False
            result['state'] = 'UNKNOWN' if result['state'] == 'UNKNOWN' else 'FAILED'
            result['source_recheck_error'] = {'type': type(error).__name__, 'message': str(error)}
        write_new(root / 'result.json', result)
    need(result['state'] == 'OBSERVED' and result['held_binding_closed'], 'IDENTITY_COLLECTION_NOT_COMPLETE')
    return regular(root / 'result.json', contents=False)


def current_artifacts(target, identity):
    target_apk_custody(target).require_identity(identity, full=True)


class HeldArtifacts:
    """The original FDs remain in the normal reader; this host never opens them.

    Explicit V/R and fixed I requests preserve the previous phase checks.
    G itself still only checks the original local Main/data custody.
    """
    def __init__(self, target, identities):
        self.target, self.identities = target, identities
        self.custody = target_apk_custody(target); self.closed = False
        packages = [identity['metadata']['package'] for identity in identities]
        need(packages and len(packages) == len(set(packages)), 'DISTINCT_ACTUAL_IDENTITY_ROLES_REQUIRED')
        for identity in identities: self.custody.match_identity(identity)
        self.revalidate()

    def _check(self, full):
        need(not self.closed, 'HELD_ARTIFACT_SET_CLOSED')
        self.target.verify()
        self.custody.guard(full=full)
        for identity in self.identities:
            self.custody.match_identity(identity)
            self.custody.package_read('identity', identity['metadata']['package'])
        self.target.verify()

    def verify(self):
        self._check(False)

    def revalidate(self):
        self._check(True)

    def close(self):
        # The actual parent retains all original role FDs until its final
        # normal PM/Main observations, full SHA and real reader retirement.
        self.closed = True


class EvidenceWitness:
    """Hold the exact identity/build receipt chain after semantic validation."""
    SKIP = {'baseline', 'qualification', 'business_baseline', 'business_qualification',
            'support_manifest', 'source_preparation', 'task_source_manifest', 'original_gates'}
    def __init__(self, documents):
        self.rows = []; self.closed = False; seen = {}; pending = list(documents)
        def refs(value):
            if type(value) is dict:
                if set(value) == {'path', 'bytes', 'sha256'}:
                    yield value
                else:
                    for key, child in value.items():
                        if key not in self.SKIP:
                            yield from refs(child)
            elif type(value) is list:
                for child in value:
                    yield from refs(child)
        try:
            while pending:
                value = pending.pop()
                for ref in refs(value):
                    if ref['path'] in seen:
                        need(seen[ref['path']] == ref, 'CONFLICTING_APP_RECEIPT_REFERENCE')
                        continue
                    need(len(seen) < 512, 'BOUNDED_PER_APP_RECEIPT_CHAIN_REQUIRED')
                    seen[ref['path']] = dict(ref)
                    named_before = metadata(Path(ref['path']).lstat())
                    need(regular(ref['path'], 512 * 1024 * 1024, contents=False) == ref, 'APP_RECEIPT_CHAIN_CHANGED')
                    fd = os.open(ref['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                    before = os.fstat(fd); self.rows.append((fd, ref['path'], metadata(before)))
                    need(before.st_size == ref['bytes'] and metadata(before) == named_before,
                         'APP_RECEIPT_CHANGED_WHILE_HOLDING')
                    if ref['path'].endswith('.json'):
                        pending.append(parse(read_ref(ref)))
            self.verify()
        except BaseException as primary:
            try:
                self.close()
            except BaseException as secondary:
                primary.add_note('RECEIPT_WITNESS_CLOSE:' + type(secondary).__name__)
            raise

    def verify(self):
        need(not self.closed, 'APP_RECEIPT_WITNESS_CLOSED')
        for fd, path, expected in self.rows:
            need(metadata(os.fstat(fd)) == expected == metadata(Path(path).lstat()),
                 'ACTUAL_APP_RECEIPT_OR_SIGNED_COPY_CHANGED')

    def close(self):
        errors = []
        for fd, _, _ in self.rows:
            try:
                os.close(fd)
            except BaseException as error:
                errors.append(error)
        self.rows = []; self.closed = True
        if errors:
            raise RuntimeError('APP_RECEIPT_WITNESS_CLOSE_FAILED') from errors[0]



def _mapped_guest_id(raw, guest):
    """One actual Android user-zero range; no configured or caller supplied map."""
    need(type(guest) is int and 0 <= guest < 100000,
         'EXACT_ANDROID_USER_ZERO_ID_REQUIRED')
    need(type(raw) is bytes and 0 < len(raw) <= 8192,
         'BOUNDED_ACTUAL_ID_MAP_REQUIRED')
    match = re.fullmatch(rb'[ \t]*([0-9]{1,10})[ \t]+([0-9]{1,10})[ \t]+'
                         rb'([0-9]{1,10})[ \t]*\n', raw)
    need(match is not None, 'ONE_COMPLETE_KERNEL_ID_MAP_REQUIRED')
    inside, outside, count = (int(value) for value in match.groups())
    need(inside == 0 and 100000 <= count <= 0xffffffff
         and 0 <= outside <= 0xffffffff and outside + count <= 0x100000000
         and guest < count, 'COMPLETE_BOUNDED_ANDROID_ID_RANGE_REQUIRED')
    return outside + guest


def mapped_file_info(view, file_fd, guest_uid, guest_gid=None):
    """Read this FD's host ownership against the same held Main's live maps.

    The original MainView still establishes admission. Only metadata from its
    held proc directory is read. The user namespace and both maps bracket the
    fstat; nothing is added to the original seven execution authority FDs.
    A process-local first binding also prevents a later phase from accepting a
    different user namespace or maps on the same otherwise-held process.
    """
    need(type(view) is MainView and type(file_fd) is int and file_fd >= 3,
         'ACTUAL_MAIN_VIEW_AND_CALLER_HELD_FILE_REQUIRED')
    need(type(guest_uid) is int and 0 <= guest_uid < 100000
         and (guest_gid is None or type(guest_gid) is int and 0 <= guest_gid < 100000),
         'EXACT_ANDROID_USER_ZERO_IDS_REQUIRED')
    guest_gid = guest_uid if guest_gid is None else guest_gid
    before_guard = view.guard()
    target = view.target
    proc_fd = target.proc_fd
    before_proc = metadata(os.fstat(proc_fd))
    opened = []
    deadline = time.monotonic() + 3

    def own(fd):
        opened.append(fd)
        need(fd >= 3 and not os.get_inheritable(fd), 'PRIVATE_METADATA_FD_REQUIRED')
        return fd

    def bounded(fd, limit):
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        size = 0
        while True:
            need(time.monotonic() <= deadline, 'ACTUAL_ID_MAP_READ_DEADLINE')
            part = os.read(fd, min(65536, limit + 1 - size))
            if not part:
                return b''.join(chunks)
            size += len(part)
            need(size <= limit, 'ACTUAL_ID_MAP_READ_BOUND')
            chunks.append(part)

    def user_node(fd):
        info = os.fstat(fd)
        need(fcntl.ioctl(fd, 0xb703) == 0x10000000 and info.st_ino > 0,
             'ACTUAL_KERNEL_USER_NAMESPACE_FD_REQUIRED')
        return info.st_dev, info.st_ino

    try:
        with target.lease():
            namespace_fd = own(os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC,
                                       dir_fd=proc_fd))
            namespace = user_node(namespace_fd)
            uid_fd = own(os.open('uid_map', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=proc_fd))
            gid_fd = own(os.open('gid_map', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=proc_fd))
            status_fd = own(os.open('status', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                   dir_fd=proc_fd))
            uid_map, gid_map = bounded(uid_fd, 8192), bounded(gid_fd, 8192)
            host_uid = _mapped_guest_id(uid_map, guest_uid)
            host_gid = _mapped_guest_id(gid_map, guest_gid)
            root_uid, root_gid = _mapped_guest_id(uid_map, 0), _mapped_guest_id(gid_map, 0)
            expected = view.baseline.value['framework_epoch']['binding']['processes']['init']
            need(target.expected['pid'] == expected['host_pid']
                 and target.expected['uid'] == [str(root_uid)] * 4
                 and expected['uids'] == [root_uid] * 4,
                 'ACTUAL_ID_MAP_MUST_BIND_THE_ORIGINAL_MAIN_ROOT_UID')
            gids = re.findall(rb'^Gid:\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$',
                              bounded(status_fd, 65536), re.M)
            need(gids == [(str(root_gid).encode(),) * 4],
                 'ACTUAL_ID_MAP_MUST_BIND_THE_LIVE_MAIN_ROOT_GID')
            binding = (os.getpid(), target, proc_fd, before_proc, namespace, uid_map, gid_map)
            previous = getattr(view, '_mapped_file_owner_scope', None)
            need(previous is None or previous == binding,
                 'ORIGINAL_MAIN_USER_NAMESPACE_OR_ID_MAP_CHANGED')
            info = os.fstat(file_fd)
            need(view.guard() == before_guard and view.target is target,
                 'ORIGINAL_MAIN_CHANGED_DURING_OWNER_OBSERVATION')
            deadline = time.monotonic() + 3
            named_namespace_fd = own(os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC,
                                             dir_fd=proc_fd))
            need(user_node(named_namespace_fd) == namespace
                 and bounded(uid_fd, 8192) == uid_map and bounded(gid_fd, 8192) == gid_map
                 and metadata(os.fstat(proc_fd)) == before_proc,
                 'ACTUAL_MAIN_ID_MAPPING_CHANGED_DURING_FILE_OBSERVATION')
            need(metadata(os.fstat(file_fd)) == metadata(info),
                 'HELD_FILE_CHANGED_DURING_OWNER_OBSERVATION')
            view._mapped_file_owner_scope = binding
            return info, (host_uid, host_gid)
    finally:
        errors = []
        for fd in reversed(opened):
            try:
                os.close(fd)
            except BaseException as error:
                errors.append(error)
        if errors:
            raise RuntimeError('ACTUAL_OWNER_METADATA_FD_CLOSE_FAILED') from errors[0]
