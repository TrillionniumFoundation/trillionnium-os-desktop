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
SUPPORT = FINAL / 'qualification/business-support-host-20261108-r1'
SUPPORT_REF = {'path': str(SUPPORT / 'source-manifest.json'), 'bytes': 1002,
               'sha256': '8cfa9cb05bb7e7768350dbe04acd4cd6421b9f4e8493746aad49b64c37969e70'}
CLOCK_SUPPORT_REF = {'path': str(FINAL / 'qualification/business-support-host-clock-20261108-r1/source-manifest.json'),
                     'bytes': 1002, 'sha256': '0e1ea6f0d3b02c47f240b1aa26ccccf1b05f82bef7edee65331de421965a53ce'}
SCOPE_SHA = 'e2a9b509102806483c64c181034e59aded211f42e5f05fcfd85057cc25c9fb7a'
GATES = {'path': '/home/alex/work/pocket4-cp13-canonical-app-gates-20261106-r12-01.json',
         'bytes': 24135, 'sha256': '441289f9c04b46f38e1dd6e19f23ec6e4c6729b6a6f814cab81c0ae6fbbb1e78'}
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
        self.environment = self.scope.environment_values(self.baseline.docs['final_baseline']['android_env'])
        self.baseline.guard()
        reader = self.baseline.data
        held = module({'path': str(reader.READER_PATH), 'bytes': 22691, 'sha256': reader.READER_SHA},
                      'final_app_held_runtime')
        identity = self.baseline.value['framework_epoch']['binding']['processes']['init']
        proc = os.open('/proc/' + str(identity['host_pid']),
                       os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            actual = held.proc_identity_at(proc, identity['host_pid'], time.monotonic() + 3)
        finally:
            os.close(proc)
        try:
            self.target = held.HeldTarget(actual, self.scope.HELPER_PATH, self.scope.HELD_HELPER_SHA256)
            helper = module(self.scope.LEGACY_HELPER_CONTRACT, 'final_app_shared_entry_contract_only')
            self.helper_qualification = helper.verify_shared_helper()
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

    def command(self, argv, timeout=20, *, root=False, private=False, inner_timeout=None, output_bound=1024 * 1024):
        need(type(root) is bool and type(private) is bool and type(timeout) in (int, float)
             and 5 < timeout <= 70, 'EXPLICIT_BOUNDED_READ_MODE_REQUIRED')
        self.admission(list(argv), timeout, root, private)
        need(output_bound in (1024 * 1024, 16 * 1024 * 1024), 'QUALIFIED_READ_CAPTURE_BOUND_REQUIRED')
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
        if self.target is not None:
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
    """Bind complete identity, including ctime, to this same hashed FD."""
    fd = target.open_root(artifact['guest_path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        record = {'device': first.st_dev, 'inode': first.st_ino, 'mode': first.st_mode,
            'uid': first.st_uid, 'gid': first.st_gid, 'bytes': first.st_size,
            'mtime_ns': first.st_mtime_ns, 'nlink': first.st_nlink}
        need(stat.S_ISREG(first.st_mode) and record == artifact['held_file'] and
            0 <= first.st_size == artifact['bytes'] <= 128 * 1024 * 1024,
            'SAME_COMPLETE_APK_IDENTITY_DESCRIPTOR_REQUIRED')
        total = 0; digest = hashlib.sha256(); deadline = time.monotonic() + 5
        while True:
            need(time.monotonic() < deadline, 'ORIGINAL_HELD_APK_READ_DEADLINE')
            raw = os.read(fd, min(65536, first.st_size + 1 - total))
            if not raw:
                break
            total += len(raw); need(total <= first.st_size, 'ACTUAL_APK_GREW'); digest.update(raw)
        need(total == first.st_size and digest.hexdigest() == artifact['sha256']
            and metadata(first) == metadata(os.fstat(fd)), 'COMPLETE_APK_FD_HASH_OR_IDENTITY_CHANGED')
        named = target.open_root(artifact['guest_path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(metadata(first) == metadata(os.fstat(named)), 'COMPLETE_APK_NAMED_IDENTITY_CHANGED')
        finally:
            os.close(named)
        return {**record, 'ctime_ns': first.st_ctime_ns}
    finally:
        os.close(fd)


def validate_identity(receipt, expected, baseline_ref, qualification_ref, *, final=True):
    need(receipt.get('schema') == 'pocket4-final-app-identity-v1' and receipt.get('state') == 'OBSERVED'
         and receipt.get('baseline') == baseline_ref and receipt.get('qualification') == qualification_ref
         and receipt.get('source_scope') == 'metadata-signature-resolution-only'
         and receipt.get('Android_UI_actions') == 0 and receipt.get('app_launches') == 0
         and receipt.get('whole_app_business_accepted') is False, 'ACTUAL_NEW_APP_IDENTITY_RECEIPT_REQUIRED')
    qualification_source = parse(read_ref(qualification_ref, 131072)).get('source_manifest')
    need(qualification_source in (SUPPORT_REF, CLOCK_SUPPORT_REF) and
         receipt.get('support_manifest') == qualification_source, 'EXACT_IDENTITY_QUALIFICATION_SOURCE_REQUIRED')
    if final:
        need(receipt.get('held_binding_closed') is True and receipt.get('source_unchanged') is True,
             'COMPLETED_IDENTITY_LEASE_AND_SOURCE_RECHECK_REQUIRED')
    read_ref(receipt['source'])
    need(receipt['expected'] == expected, 'APP_EXPECTATIONS_CHANGED')
    commands = receipt['observations']; wanted = package_commands(expected['package'], bool(expected.get('component')))
    need(len(commands) == len(wanted), 'EXACT_ORIGINAL_READ_COUNT_REQUIRED')
    outputs = []
    for row, argv in zip(commands, wanted):
        need(row['logical']['argv'] == argv and row['logical']['root_read'] is False
             and row['logical']['private_output'] is False and row['logical']['Android_mutation'] is False,
             'APP_OBSERVER_COMMAND_SCOPE_CHANGED')
        observed = parse(read_ref(row['result']))
        transport = parse(read_ref(row['transport']))
        need(transport['schema'] == 'pocket4-final-app-read-transport-v1' and
             transport['logical'] == row['logical'] and transport['lease_entered'] is True
             and transport['lease_released'] is True and transport['host_retirement_proved'] is True
             and transport['error_type'] is None and
             transport['post_guard']['business_baseline_sha256'] == baseline_ref['sha256']
             and transport['post_guard']['business_qualification_sha256'] == qualification_ref['sha256'],
             'ACTUAL_HELD_LEASE_EXIT_AND_NEW_MAIN_POST_GUARD_REQUIRED')
        need(observed['host_retirement_proved'] is True and observed['evidence_complete'] is True
             and observed['returncode'] == 0 and observed['timed_out'] is False
             and observed['errors'] == [] and observed.get('first_error') is None,
             'APP_METADATA_OBSERVER_NOT_SUCCESSFULLY_RETIRED')
        raw = read_ref(observed['stdout'], 1024 * 1024)
        need(read_ref(observed['stderr'], 1024 * 1024) == b'', 'UNEXPECTED_PACKAGE_DIAGNOSTIC')
        outputs.append(raw)
    before = package_metadata(outputs[0], expected); after = package_metadata(outputs[-1], expected)
    need(before == after == receipt['metadata'] and outputs[1] == outputs[-2], 'APP_METADATA_CHANGED_DURING_OBSERVATION')
    paths = apk_paths(outputs[1]); artifacts = receipt['artifacts']
    need([row['guest_path'] for row in artifacts] == paths, 'ARTIFACT_PATH_CHAIN_CHANGED')
    validate_artifacts(artifacts, expected)
    if expected.get('component'):
        need(outputs[2].decode('utf-8', 'strict').splitlines() == [expected['component']]
             and receipt['component'] == expected['component'], 'UNIQUE_ACTUAL_LAUNCHER_REQUIRED')
    for artifact in artifacts:
        need(regular(artifact['private_copy']['path'], 128 * 1024 * 1024, contents=False)
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
    support_ref = parse(read_ref(request['qualification'], 131072)).get('source_manifest')
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
            for k, path in enumerate(paths):
                data, info = view.target.read_file(path, 128 * 1024 * 1024,
                                                 single_link=path.startswith('/data/'))
                artifact = {'guest_path': path, 'bytes': len(data), 'sha256': sha(data), 'held_file': info}
                artifact['stat_file'] = full_artifact(view.target, artifact)
                artifact['private_copy'] = write_new(root / ('apk-%02d.apk' % k), data); del data
                result['artifacts'].append(artifact)
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
        for artifact in result['artifacts']:
            data, info = view.target.read_file(artifact['guest_path'], 128 * 1024 * 1024,
                single_link=artifact['guest_path'].startswith('/data/'))
            need(sha(data) == artifact['sha256'] and info == artifact['held_file'], 'APK_CHANGED_AFTER_SIGNATURE'); del data
            need(full_artifact(view.target, artifact) == artifact['stat_file'], 'APK_COMPLETE_IDENTITY_CHANGED_AFTER_SIGNATURE')
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
    packages, _ = target.read_file('/data/system/packages.list', 1024 * 1024)
    expected = identity['metadata']; matches = []
    for line in packages.decode('utf-8', 'strict').splitlines():
        fields = line.split()
        if fields and fields[0] == expected['package']:
            need(len(fields) >= 2 and fields[1].isdecimal(), 'ACTUAL_PACKAGE_UID_REQUIRED')
            matches.append(int(fields[1]))
    need(matches == [expected['uid']], 'ACTUAL_PACKAGE_UID_CHANGED')
    for artifact in identity['artifacts']:
        raw, info = target.read_file(artifact['guest_path'], 128 * 1024 * 1024,
                                    single_link=artifact['guest_path'].startswith('/data/'))
        need(len(raw) == artifact['bytes'] and sha(raw) == artifact['sha256']
             and info == artifact['held_file'], 'ACTUAL_INSTALLED_APK_BACKING_CHANGED')
        del raw
        if 'stat_file' in artifact:
            need(full_artifact(target, artifact) == artifact['stat_file'], 'ACTUAL_INSTALLED_APK_CTIME_CHANGED')


class HeldArtifacts:
    """Original phase contract: hash at phase boundaries, hold and check FDs.

    Every guard checks the same held and named inode plus full metadata,
    including ctime. It does not repeatedly copy a commercial APK on every
    metadata command. The actual package commands still bracket each phase.
    """
    def __init__(self, target, identities):
        self.target, self.identities, self.files = target, identities, []
        self.closed = False
        try:
            for identity in identities:
                current_artifacts(target, identity)
                for artifact in identity['artifacts']:
                    fd = target.open_root(artifact['guest_path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                    info = os.fstat(fd)
                    self.files.append((fd, artifact['guest_path'], metadata(info)))
                    need(stat.S_ISREG(info.st_mode) and 0 <= info.st_size == artifact['bytes'] <= 128 * 1024 * 1024,
                         'HELD_APK_FILE_REQUIRED')
                    # Match the exact fd_record() schema of the frozen held reader.
                    observed = {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
                                'uid': info.st_uid, 'gid': info.st_gid, 'bytes': info.st_size,
                                'mtime_ns': info.st_mtime_ns, 'nlink': info.st_nlink}
                    need(observed == artifact['held_file'], 'HELD_APK_RECEIPT_BACKING_CHANGED')
                    if 'stat_file' in artifact:
                        need({**observed, 'ctime_ns': info.st_ctime_ns} == artifact['stat_file'],
                             'HELD_APK_COMPLETE_RECEIPT_IDENTITY_CHANGED')
                    # Hash the descriptor that remains held, not a prior pathname read.
                    deadline = time.monotonic() + 5; digest = hashlib.sha256(); count = 0
                    while True:
                        need(time.monotonic() <= deadline, 'HELD_APK_HASH_DEADLINE')
                        block = os.read(fd, min(65536, 128 * 1024 * 1024 + 1 - count))
                        if not block:
                            break
                        count += len(block)
                        need(count <= 128 * 1024 * 1024, 'HELD_APK_HASH_BYTE_BOUND')
                        digest.update(block)
                    need(count == info.st_size and digest.hexdigest() == artifact['sha256'] and
                         metadata(os.fstat(fd)) == metadata(info), 'HELD_APK_HASH_OR_METADATA_CHANGED')
            self.verify()
        except BaseException as primary:
            try:
                self.close()
            except BaseException as secondary:
                primary.add_note('ARTIFACT_CLOSE:' + type(secondary).__name__)
            raise

    def verify(self):
        need(not self.closed, 'HELD_ARTIFACT_SET_CLOSED')
        self.target.verify()
        packages, _ = self.target.read_file('/data/system/packages.list', 1024 * 1024)
        wanted = {identity['metadata']['package']: identity['metadata']['uid'] for identity in self.identities}
        found = {}
        for line in packages.decode('utf-8', 'strict').splitlines():
            fields = line.split()
            if fields and fields[0] in wanted:
                need(fields[0] not in found and len(fields) >= 2 and fields[1].isdecimal(),
                     'EXACT_HELD_ARTIFACT_PACKAGE_UID_REQUIRED')
                found[fields[0]] = int(fields[1])
        need(found == wanted, 'HELD_TARGET_OR_HELPER_UID_CHANGED')
        for fd, path, expected in self.files:
            need(metadata(os.fstat(fd)) == expected, 'HELD_APK_INODE_METADATA_CHANGED')
            named = self.target.open_root(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                need(metadata(os.fstat(named)) == expected, 'ACTIVE_NAMED_APK_BACKING_CHANGED')
            finally:
                os.close(named)

    def revalidate(self):
        self.verify()
        for identity in self.identities:
            current_artifacts(self.target, identity)
        self.verify()

    def close(self):
        errors = []
        for fd, _, _ in self.files:
            try:
                os.close(fd)
            except BaseException as error:
                errors.append(error)
        self.files = []; self.closed = True
        if errors:
            raise RuntimeError('HELD_ARTIFACT_FD_CLOSE_FAILED') from errors[0]


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
                    need(regular(ref['path'], 128 * 1024 * 1024, contents=False) == ref, 'APP_RECEIPT_CHAIN_CHANGED')
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

