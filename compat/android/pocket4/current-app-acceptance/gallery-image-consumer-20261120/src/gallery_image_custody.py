"""Consume only a fresh 2360 daemon observation through the pinned native CLI.

JSON is evidence, never an execution permit.  ``validate_response`` is pure and
cannot construct ``CapturedImage``.  Only ``capture`` can do that, after the
original bounded host recorder has joined the actual native CLI and its tree.
The independent production daemon still owns readiness, namespaces, image
descriptors, peer authorization and the seven original read-executor receipts.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

PACKAGE = 'com.android.gallery3d'
APK_BYTES = 7390425
APK_SHA256 = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
SYSTEM_BYTES = 2294853632
SYSTEM_SHA256 = 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'
APK_SOURCE = '/system/product/app/Gallery2/Gallery2.apk'
APK_PATHS = (APK_SOURCE, '/product/app/Gallery2/Gallery2.apk')
MAX_OUTPUT = 3 * 1024 * 1024
CAPTURE_SECONDS = 340
_CAPTURE_TOKEN = object()
_META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
         'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact(value, keys, reason):
    need(type(value) is dict and set(value) == set(keys.split()), reason)


def integer(value, minimum=0, maximum=2**64 - 1):
    return type(value) is int and minimum <= value <= maximum


def digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def decode(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'BOUNDED_NATIVE_CUSTODY_JSON')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_NATIVE_CUSTODY_JSON_KEY')
            result[key] = value
        return result
    def nonfinite(value):
        raise RuntimeError('NONFINITE_NATIVE_CUSTODY_JSON')
    return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                      parse_constant=nonfinite)


def file_identity(value):
    exact(value, 'device inode mode uid gid links bytes modified changed', 'EXACT_CUSTODY_FILE')
    need(all(integer(value[key]) for key in ('device', 'inode', 'mode', 'uid', 'gid', 'links', 'bytes'))
         and value['device'] > 0 and value['inode'] > 0, 'CUSTODY_FILE_NUMBERS')
    for name in ('modified', 'changed'):
        stamp = value[name]
        need(type(stamp) is list and len(stamp) == 2
             and integer(stamp[0], -(2**63), 2**63 - 1)
             and integer(stamp[1], 0, 999999999), 'CUSTODY_FILE_TIMESTAMP')


def namespace(value):
    exact(value, 'name device inode', 'EXACT_CUSTODY_NAMESPACE')
    need(type(value['name']) is str and integer(value['device'], 1)
         and integer(value['inode'], 1), 'CUSTODY_NAMESPACE_IDENTITY')


def regular(value):
    file_identity(value)
    need(stat.S_ISREG(value['mode']) and value['uid'] == value['gid'] == 0
         and value['links'] == 1 and value['mode'] & 0o022 == 0,
         'ROOT_OWNED_SINGLE_LINK_CUSTODY_FILE')


def validate_response(value, epoch):
    """Check a producer-shaped value; deliberately grants no runtime authority."""
    exact(value, 'operation observation image_custody data_continuity_qualified '
          'production_ready runtime_qualified app_launches', 'EXACT_NATIVE_INSPECTION_RESPONSE')
    need(value['operation'] == 'inspect_installed_application'
         and value['data_continuity_qualified'] is False
         and value['production_ready'] is False and value['runtime_qualified'] is False
         and integer(value['app_launches'], 0, 0), 'INSPECTION_HAS_NO_ACCEPTANCE_CREDIT')
    app = value['observation']
    exact(app, 'package user uid version_code epoch apks', 'EXACT_CURRENT_APPLICATION')
    exact(app['epoch'], 'boot_id cell_host_pid framework_host_pid framework_start_ticks',
          'EXACT_CURRENT_FRAMEWORK_EPOCH')
    need(type(app['epoch']['boot_id']) is str
         and re.fullmatch('[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', app['epoch']['boot_id'])
         and all(integer(app['epoch'][key], 1) for key in
                 ('cell_host_pid', 'framework_host_pid', 'framework_start_ticks'))
         and app['epoch'] == epoch, 'CUSTODY_AND_BUSINESS_CURRENT_EPOCH_DIFFER')
    need(app['package'] == PACKAGE and integer(app['user'], 0, 0)
         and integer(app['uid'], 1, 99999) and integer(app['version_code'], 40030, 40030)
         and type(app['apks']) is list and len(app['apks']) == 1, 'ORIGINAL_IMAGE_GALLERY_ONLY')
    apk = app['apks'][0]
    exact(apk, 'name path bytes sha256', 'EXACT_CURRENT_APK')
    need(apk['name'] == 'base.apk' and apk['path'] in APK_PATHS
         and integer(apk['bytes'], APK_BYTES, APK_BYTES) and apk['sha256'] == APK_SHA256,
         'EXACT_OFFICIAL_IMAGE_APK_REQUIRED')
    proof = value['image_custody']
    exact(proof, 'schema application owner cohort original_apk after_cohort '
          'after_original_apk reads elapsed_millis data_continuity_qualified '
          'runtime_qualified business_qualified production_ready', 'LIVE_IMAGE_CUSTODY_REQUIRED')
    need(proof['schema'] == 'droidloom-image-application-custody-v1'
         and proof['application'] == app and proof['after_cohort'] == proof['cohort']
         and proof['after_original_apk'] == proof['original_apk']
         and integer(proof['elapsed_millis'], 0, 299999)
         and all(proof[key] is False for key in ('data_continuity_qualified', 'runtime_qualified',
                                               'business_qualified', 'production_ready')),
         'WHOLE_CURRENT_IMAGE_CUSTODY_AND_UNQUALIFIED_GATES_REQUIRED')
    owner, cohort = proof['owner'], proof['cohort']
    exact(owner, 'host_uid cell_host_pid cell_start_ticks selection_binding_sha256 '
          'base_cohort_sha256 runtime_manifest_sha256 namespaces', 'EXACT_ORIGINAL_READY_OWNER')
    exact(cohort, 'manifest_path manifest manifest_sha256 host_uid user_namespace uid_range '
          'gid_range system vendor', 'COMPLETE_CURRENT_BASE_COHORT')
    need(integer(owner['host_uid'], 1, 2**32-2) and integer(cohort['host_uid'], 1, 2**32-2)
         and owner['host_uid'] == cohort['host_uid']
         and integer(owner['cell_host_pid'], 1) and owner['cell_host_pid'] == epoch['cell_host_pid']
         and integer(owner['cell_start_ticks'], 1)
         and all(digest(owner[key]) for key in
                 ('selection_binding_sha256', 'base_cohort_sha256', 'runtime_manifest_sha256'))
         and digest(cohort['manifest_sha256'])
         and owner['base_cohort_sha256'] == cohort['manifest_sha256']
         and cohort['manifest_path'] == '/etc/droidloom/cohorts/' + cohort['manifest_sha256'] + '.json',
         'ORIGINAL_OWNER_COMPLETE_COHORT_BINDING_REQUIRED')
    regular(cohort['manifest'])
    need(0 < cohort['manifest']['bytes'] <= 16384, 'BOUNDED_CURRENT_COHORT_MANIFEST')
    need(type(owner['namespaces']) is list and len(owner['namespaces']) == 7,
         'ALL_SEVEN_ORIGINAL_NAMESPACES')
    for row in owner['namespaces']:
        namespace(row)
    namespace(cohort['user_namespace'])
    need({row['name'] for row in owner['namespaces']} ==
         {'user', 'mount', 'pid', 'ipc', 'uts', 'net', 'cgroup'}
         and [row for row in owner['namespaces'] if row['name'] == 'user'] == [cohort['user_namespace']],
         'ORIGINAL_NAMESPACE_AND_COHORT_USER_NAMESPACE_DIFFER')
    for key in ('uid_range', 'gid_range'):
        value_range = cohort[key]
        need(type(value_range) is list and len(value_range) == 2
             and integer(value_range[0], 0, 2**32-1) and integer(value_range[1], 1, 2**32-1)
             and value_range[0] + 2000 < 2**32, 'ACTUAL_MAPPED_ANDROID_SHELL_REQUIRED')
    for role in ('system', 'vendor'):
        image = cohort[role]
        exact(image, 'role path file sha256 loop_node loop_device loop_number loop_source_device '
              'loop_source_inode loop_offset loop_size_limit loop_flags mount_id mount_root '
              'mount_flags filesystem', 'WHOLE_IMAGE_LOOP_AND_MOUNT_CUSTODY')
        regular(image['file']); file_identity(image['loop_node']); file_identity(image['mount_root'])
        need(all(integer(image[key]) for key in ('loop_device', 'loop_number', 'loop_source_device',
             'loop_source_inode', 'loop_offset', 'loop_size_limit', 'loop_flags', 'mount_id', 'mount_flags'))
             and image['role'] == role
             and image['path'] == '/var/lib/droidloom/cohorts/' + cohort['manifest_sha256'] + '/images/' + role + '.img'
             and 4096 <= image['file']['bytes'] <= 8*1024**3 and image['file']['bytes'] % 512 == 0
             and digest(image['sha256']) and stat.S_ISBLK(image['loop_node']['mode'])
             and image['loop_node']['uid'] == 0 and image['loop_node']['mode'] & 0o002 == 0
             and image['loop_offset'] == image['loop_size_limit'] == 0 and image['loop_flags'] == 5
             and image['loop_source_device'] == image['file']['device']
             and image['loop_source_inode'] == image['file']['inode'] and image['mount_id'] > 0
             and image['mount_root']['device'] == image['loop_device']
             and stat.S_ISDIR(image['mount_root']['mode'])
             and image['mount_root']['uid'] == cohort['uid_range'][0]
             and image['mount_root']['gid'] == cohort['gid_range'][0]
             and image['mount_flags'] & 7 == 7 and image['filesystem'] in ('ext4', 'erofs'),
             'ORIGINAL_READONLY_WHOLE_IMAGE_BINDING_REQUIRED')
    source = proof['original_apk']
    exact(source, 'path file sha256 mount_id', 'ORIGINAL_SYSTEM_IMAGE_MEMBER')
    file_identity(source['file'])
    need(source['path'] == APK_SOURCE and source['sha256'] == APK_SHA256
         and source['file']['bytes'] == APK_BYTES and stat.S_ISREG(source['file']['mode'])
         and integer(source['mount_id'], 1) and source['mount_id'] == cohort['system']['mount_id']
         and source['file']['device'] == cohort['system']['mount_root']['device']
         and cohort['system']['file']['bytes'] == SYSTEM_BYTES
         and cohort['system']['sha256'] == SYSTEM_SHA256
         and (cohort['system']['file']['device'], cohort['system']['file']['inode']) !=
             (cohort['vendor']['file']['device'], cohort['vendor']['file']['inode']),
         'OFFICIAL_COMPLETE_SYSTEM_AND_ORIGINAL_APK_INODE_REQUIRED')
    reads = proof['reads']
    need(type(reads) is list and len(reads) == 7, 'COMPLETE_SEVEN_READ_LEDGER_REQUIRED')
    package_argv = ['/system/bin/cmd', 'package', 'list', 'packages', '--user', '0', '-U',
                    '--show-versioncode', PACKAGE]
    path_argv = ['/system/bin/cmd', 'package', 'path', '--user', '0', PACKAGE]
    stat_argv = ['/system/bin/toybox', 'stat', '-c', '%d:%i:%s:%y:%z', apk['path']]
    expected_argv = [package_argv, path_argv, stat_argv,
                     ['/system/bin/toybox', 'sha256sum', apk['path']], stat_argv, package_argv, path_argv]
    for read, argv in zip(reads, expected_argv):
        exact(read, 'argv stdout receipt', 'EXACT_ORIGINAL_READ_TRANSCRIPT')
        need(read['argv'] == argv and type(read['stdout']) is str, 'LITERAL_SEVEN_READ_ORDER')
        raw = read['stdout'].encode()
        receipt = read['receipt']
        exact(receipt, 'worker_pid worker_waitid_code worker_waitid_status query_pid query_waitid_code '
              'query_waitid_status exec output_bytes output_sha256 elapsed_millis cgroup_removed',
              'ORIGINAL_EXECUTOR_RETIREMENT_RECEIPT_REQUIRED')
        need(len(raw) <= 65536 and integer(receipt['output_bytes'], len(raw), len(raw))
             and receipt['output_sha256'] == sha(raw)
             and integer(receipt['worker_pid'], 1) and integer(receipt['query_pid'], 1)
             and receipt['worker_pid'] != receipt['query_pid']
             and integer(receipt['worker_waitid_code'], 1, 1)
             and integer(receipt['query_waitid_code'], 1, 1)
             and integer(receipt['worker_waitid_status'], 0, 0)
             and integer(receipt['query_waitid_status'], 0, 0)
             and integer(receipt['elapsed_millis'], 0, 29999) and receipt['cgroup_removed'] is True,
             'COMPLETE_JOINED_ORIGINAL_QUERY_OUTPUT_REQUIRED')
        execution = receipt['exec']
        exact(execution, 'query_start_ticks original_parent_pid tracer_tid waitid_code waitid_status '
              'event_previous_tid executable executable_mount_id executable_sha256 executable_selinux '
              'process_selinux process_apparmor uid gid no_new_privileges seccomp_filter_mode',
              'ORIGINAL_STOPPED_EXEC_OBSERVATION_REQUIRED')
        need(all(integer(execution[key], 1) for key in
                 ('query_start_ticks', 'original_parent_pid', 'tracer_tid', 'executable_mount_id'))
             and integer(execution['waitid_code'], 4, 4) and integer(execution['waitid_status'], 1029, 1029)
             and integer(execution['event_previous_tid'], 1)
             and execution['event_previous_tid'] == receipt['query_pid']
             and type(execution['executable']) is dict and digest(execution['executable_sha256'])
             and execution['executable_selinux'] == 'u:object_r:droidloom_query_exec:s0'
             and execution['process_selinux'] == 'u:r:droidloom_query:s0'
             and execution['process_apparmor'] == 'droidloom-production-android//&droidloom-production-broker (enforce)'
             and execution['no_new_privileges'] is True and integer(execution['seccomp_filter_mode'], 2, 2)
             and integer(execution['uid'], cohort['uid_range'][0]+2000, cohort['uid_range'][0]+2000)
             and integer(execution['gid'], cohort['gid_range'][0]+2000, cohort['gid_range'][0]+2000),
             'ORIGINAL_EXEC_MAC_AND_MAPPED_SHELL_REQUIRED')
    package_lines = [line for line in reads[0]['stdout'].splitlines()
                     if line.split() and line.split()[0] == 'package:' + PACKAGE]
    need(len(package_lines) == 1, 'ONE_ACTUAL_PM_PACKAGE')
    fields = package_lines[0].split()
    need([part for part in fields if part.startswith('uid:')] == ['uid:' + str(app['uid'])]
         and [part for part in fields if part.startswith('versionCode:')] == ['versionCode:40030']
         and reads[0]['stdout'] == reads[5]['stdout'], 'PM_IDENTITY_TRANSCRIPT_DIFFER')
    need([row for row in reads[1]['stdout'].splitlines() if row.strip()] == ['package:' + apk['path']]
         and reads[1]['stdout'] == reads[6]['stdout'], 'PM_PATH_TRANSCRIPT_DIFFER')
    stat_fields = reads[2]['stdout'].strip().split(':', 3)
    need(len(stat_fields) == 4 and stat_fields[:3] == [str(source['file'][key])
         for key in ('device', 'inode', 'bytes')]
         and reads[2]['stdout'].strip() == reads[4]['stdout'].strip(), 'PM_APK_IS_NOT_ORIGINAL_MOUNT_INODE')
    need(reads[3]['stdout'].strip() == APK_SHA256 + '  ' + apk['path'], 'PM_WHOLE_APK_HASH_DIFFERS')
    return copy.deepcopy(value)


def current_epoch(view):
    view.guard()
    processes = view.baseline.value['framework_epoch']['binding']['processes']
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'cell_host_pid': view.baseline.docs['final_baseline']['daemon_status']['host_pid'],
            'framework_host_pid': processes['system_server']['host_pid'],
            'framework_start_ticks': processes['system_server']['start_ticks']}


class CapturedImage:
    def __init__(self, token, value, reference, main_guard):
        need(token is _CAPTURE_TOKEN, 'SERIALIZED_RECEIPTS_CANNOT_CREATE_CAPTURE_AUTHORITY')
        self._value = canonical(value)
        self._reference = copy.deepcopy(reference)
        self._main_guard = copy.deepcopy(main_guard)
        self._pid = os.getpid()

    def bind(self, view):
        need(self._pid == os.getpid(), 'CAPTURE_CANNOT_TRANSFER_TO_ANOTHER_PROCESS')
        need(view.guard() == self._main_guard, 'IMAGE_CAPTURE_AND_BUSINESS_MAIN_DIFFER')
        value = validate_response(decode(self._value), current_epoch(view))
        return value['observation']

    def mapped_owner(self, view, guest_uid, guest_gid=None):
        """Translate guest PM IDs using this captured owner's real UID/GID maps."""
        self.bind(view)
        need(integer(guest_uid, 0, 99999) and (guest_gid is None or integer(guest_gid, 0, 99999)),
             'BOUNDED_ANDROID_USER_ZERO_IDS_REQUIRED')
        proof = decode(self._value)['image_custody']
        # The existing business helper retains six entry namespaces and a root
        # FD. Observe its same held process's user namespace only for metadata
        # comparison; never add this FD to its execution authority set.
        namespace_fd = os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=view.target.proc_fd)
        try:
            observed = os.fstat(namespace_fd)
            expected = proof['cohort']['user_namespace']
            need((observed.st_dev, observed.st_ino) == (expected['device'], expected['inode']),
                 'HELD_BUSINESS_USER_NAMESPACE_DIFFERS_FROM_CURRENT_IMAGE_OWNER')
        finally:
            os.close(namespace_fd)
        mapped = []
        for name, guest in (('uid', guest_uid), ('gid', guest_uid if guest_gid is None else guest_gid)):
            begin, count = proof['cohort'][name + '_range']
            need(guest < count, 'GUEST_ID_OUTSIDE_ORIGINAL_MAPPED_RANGE')
            fd = os.open(name + '_map', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=view.target.proc_fd)
            try:
                raw = os.read(fd, 8193)
                need(len(raw) <= 8192, 'BOUNDED_ORIGINAL_OWNER_ID_MAP')
                rows = [tuple(map(int, row.split())) for row in raw.decode('ascii').splitlines()]
                need(rows == [(0, begin, count)], 'ACTUAL_BUSINESS_ID_MAP_AND_PRODUCER_COHORT_DIFFER')
            finally:
                os.close(fd)
            mapped.append(begin + guest)
        view.guard()
        return tuple(mapped)

    @property
    def reference(self):
        return copy.deepcopy(self._reference)

    def same_images(self, other):
        need(type(other) is CapturedImage and self._pid == other._pid == os.getpid(),
             'TWO_ACTUAL_SAME_PROCESS_NATIVE_CAPTURES_REQUIRED')
        left, right = decode(self._value), decode(other._value)
        need(left['observation'] == right['observation']
             and all(left['image_custody'][key] == right['image_custody'][key]
                     for key in ('owner', 'cohort', 'original_apk'))
             and self._main_guard == other._main_guard,
             'CURRENT_IMAGE_OWNER_COHORT_OR_APK_CHANGED_DURING_BUSINESS')
        return True


def capture(c, view, source_guard, cli_reference, socket_path, journal):
    """One fixed live inspection; no retry, install, imported proof or PID input."""
    need(type(cli_reference) is dict and set(cli_reference) == {'path', 'bytes', 'sha256'}
         and integer(cli_reference['bytes'], 1, 64*1024*1024) and digest(cli_reference['sha256']),
         'CURRENT_ADMITTED_RELEASE_NATIVE_CLI_REQUIRED')
    # The source graph intentionally contains no hash of the binary that
    # embeds its catalog. The original CURRENT/owner-anchored release guard
    # supplies this pin after final CI; source_guard rechecks that admission.
    cli_bytes, cli_sha = cli_reference['bytes'], cli_reference['sha256']
    path = Path(cli_reference['path'])
    need(str(path) == '/usr/bin/droidloom-applications' and path.resolve() == path,
         'CANONICAL_INSTALLED_NATIVE_CLI_REQUIRED')
    need(socket_path == '/run/droidloom/control.sock' and Path(socket_path).resolve() == Path(socket_path),
         'ORIGINAL_PRODUCTION_CONTROL_SOCKET_REQUIRED')
    source_guard(); before = view.guard(); epoch = current_epoch(view)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        identity = os.fstat(fd)
        need(stat.S_ISREG(identity.st_mode) and identity.st_uid == identity.st_gid == 0
             and identity.st_nlink == 1 and identity.st_mode & 0o022 == 0
             and identity.st_mode & 0o111 != 0 and identity.st_size == cli_bytes,
             'INSTALLED_EXECUTABLE_NATIVE_CLI_OWNER_MODE_SIZE')
        body = os.pread(fd, cli_bytes + 1, 0)
        need(len(body) == cli_bytes and sha(body) == cli_sha, 'CURRENT_CI_CLI_BODY_DIFFERS')
        original = tuple(getattr(identity, key) for key in _META)
        def guard(**unused):
            source_guard()
            need(tuple(getattr(os.fstat(fd), key) for key in _META) == original
                 and tuple(getattr(path.lstat(), key) for key in _META) == original,
                 'INSTALLED_CLI_REPLACED_DURING_CAPTURE')
            need(sha(os.pread(fd, cli_bytes + 1, 0)) == cli_sha,
                 'INSTALLED_CLI_BODY_CHANGED_DURING_CAPTURE')
            need(view.guard() == before and current_epoch(view) == epoch, 'MAIN_CHANGED_DURING_NATIVE_CAPTURE')
            return before
        guard()
        # The original host recorder admits zero FDs for host commands, or its
        # exact seven held namespace FDs for Android commands. Do not enlarge
        # that contract or pad a descriptor set. The root-owned fixed installed
        # executable is protected by whole-body and F9 checks around dispatch.
        argv = [str(path), '--inspect-package', PACKAGE, '--user', '0', '--socket', socket_path]
        completed = view.commands.run_recorded('native-image-custody', argv, CAPTURE_SECONDS, journal, guard,
            protected_pids=view.baseline.protected_pids, mutation=False, pass_fds=(),
            host_env=c.HOST_ENV, check=False, output_bound=MAX_OUTPUT)
        need(completed.returncode == 0 and completed.host_tree_retired is True
             and completed.host_timed_out is False and not completed.recorder_errors
             and completed.stderr == b''
             and completed.command_observation.get('host_retirement_proved') is True
             and not completed.command_observation.get('cancellation', {}).get('count'),
             'NATIVE_CLI_NOT_SUCCESSFULLY_JOINED_WITHOUT_CANCELLATION')
        value = validate_response(decode(completed.stdout), epoch)
        guard()
        reference = c.write_new(Path(journal) / 'current-image-custody.json', value)
        return CapturedImage(_CAPTURE_TOKEN, value, reference, before)
    finally:
        os.close(fd)
