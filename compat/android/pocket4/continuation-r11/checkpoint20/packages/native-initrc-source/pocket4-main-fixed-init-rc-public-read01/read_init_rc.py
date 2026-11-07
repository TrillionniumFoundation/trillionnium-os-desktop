#!/usr/bin/env python3
"""Read two fixed Main init files; closed public projection, no execution."""
import signal
import time
_STARTED = time.monotonic()
_OBSERVE_DEADLINE = _STARTED + 12.0
_FINAL_DEADLINE = _STARTED + 14.0
signal.signal(signal.SIGALRM, signal.SIG_DFL)
signal.setitimer(signal.ITIMER_REAL, 15.0)
# No file/child acquisition occurs before this self-only watchdog.
import ctypes
import hashlib
import json
import os
import resource
import select
import stat
import sys

BOOT_ID = '981ff371-cd72-4f81-9be3-a862111afdb1'
EXPECTED = json.loads("{\"pid\":3588093,\"start_ticks\":80797014,\"ppid\":3588092,\"uids\":[0,0,0,0],\"namespace_pids\":[3588093,1],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533284]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}}")
CATALOG = json.loads("{\"zygote_header\":\"service zygote /system/bin/app_process64 -Xzygote /system/bin --zygote --start-system-server --socket-name=zygote\",\"import_zygote\":\"import /system/etc/init/hw/init.${ro.zygote}.rc\",\"start_header\":\"on zygote-start\",\"restart\":[[\"onrestart exec_background - system system -- /system/bin/vdc volume abort_fuse\",\"ONRESTART_ABORT_FUSE\",[\"exec_background\",\"vdc\",\"volume\",\"abort_fuse\"]],[\"onrestart write /sys/power/state on\",\"ONRESTART_POWER_STATE_ON\",[\"write\",\"/sys/power/state\",\"on\"]],[\"onrestart write /sys/power/wake_lock zygote_kwl\",\"ONRESTART_ZYGOTE_WAKE_LOCK\",[\"write\",\"/sys/power/wake_lock\",\"zygote_kwl\"]],[\"onrestart restart audioserver\",\"ONRESTART_AUDIOSERVER\",[\"restart\",\"audioserver\"]],[\"onrestart restart cameraserver\",\"ONRESTART_CAMERASERVER\",[\"restart\",\"cameraserver\"]],[\"onrestart restart media\",\"ONRESTART_MEDIA\",[\"restart\",\"media\"]],[\"onrestart restart --only-if-running media.tuner\",\"ONRESTART_MEDIA_TUNER_IF_RUNNING\",[\"restart\",\"--only-if-running\",\"media.tuner\"]],[\"onrestart restart netd\",\"ONRESTART_NETD\",[\"restart\",\"netd\"]],[\"onrestart restart wificond\",\"ONRESTART_WIFICOND\",[\"restart\",\"wificond\"]]],\"start\":[[\"wait_for_prop odsign.verification.done 1\",\"ZYGOTE_START_WAITS_FOR_ODSIGN\",[\"wait_for_prop\",\"odsign.verification.done\",\"1\"]],[\"start statsd\",\"ZYGOTE_START_STATSD\",[\"start\",\"statsd\"]],[\"start zygote\",\"ZYGOTE_START_PRIMARY\",[\"start\",\"zygote\"]],[\"start zygote_secondary\",\"ZYGOTE_START_SECONDARY\",[\"start\",\"zygote_secondary\"]]]}")
FILES = json.loads("[{\"id\":\"main_init_rc\",\"name\":\"init.rc\",\"path\":\"/proc/3588093/root/system/etc/init/hw/init.rc\",\"limit\":131072,\"upstream\":{\"bytes\":56559,\"sha256\":\"8b8d9d9c2c17fcb1f907b0a369aae03632976dff8f4cf603b1d5ef83cad78225\",\"git_blob_sha1\":\"5e26d127ac4aec5fd7b4a7c7c4e17460c4828638\"}},{\"id\":\"main_zygote64_rc\",\"name\":\"init.zygote64.rc\",\"path\":\"/proc/3588093/root/system/etc/init/hw/init.zygote64.rc\",\"limit\":16384,\"upstream\":{\"bytes\":901,\"sha256\":\"7be8fde03ec2cc4417aecf1a79163e0e4088fdff02ee6cd2426d02f91127e479\",\"git_blob_sha1\":\"342212123de59bebaf3eb4d4c3dca7147affe5c4\"}}]")
PUBLIC_SOURCE_COMMIT = '545d2487e38192a2ce25040897ced877cf6b4f53'
SAFE_CODES = {
    'OBSERVATION_DEADLINE', 'FINAL_DEADLINE', 'ROOT_REQUIRED', 'NONDUMP_FAILED',
    'BOOT_CHANGED', 'PROC_STAT_SCHEMA', 'PROC_STAT_FIELDS', 'PROCESS_NOT_LIVE',
    'INIT_IDENTITY_CHANGED', 'STATUS_FIELDS', 'NS_LINK_SCHEMA', 'PROC_READ_BOUND',
    'PIDFD_DEAD', 'ROOT_IDENTITY_CHANGED', 'DIRECTORY_IDENTITY_CHANGED',
    'NOT_DIRECTORY', 'NOT_REGULAR', 'FILE_READ_BOUND', 'FILE_IDENTITY_CHANGED',
    'FILE_SIZE_CHANGED', 'FIXED_FILE_ID', 'FILE_ENCODING', 'PUBLIC_OUTPUT_BOUND',
    'CONTROL_FAILED', 'FD_CLEANUP_FAILED', 'FINAL_AUTHORITY_CHANGED',
}
FDS = []
CLEANUP_ERRORS = []

def need(value, code):
    if not value:
        raise RuntimeError(code)

def check():
    need(time.monotonic() < _OBSERVE_DEADLINE, 'OBSERVATION_DEADLINE')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def safe_error(error):
    value = {'type': type(error).__name__, 'errno': getattr(error, 'errno', None)}
    if isinstance(error, RuntimeError) and str(error) in SAFE_CODES:
        value['code'] = str(error)
    return value

def acquire(path, flags, label, parent=None):
    check()
    fd = os.open(path, flags, dir_fd=parent)
    row = {'label': label, 'fd': fd, 'close_attempted': False, 'closed': False}
    FDS.append(row)
    return row

def close_one(row):
    if row['close_attempted']:
        return
    row['close_attempted'] = True
    try:
        os.close(row['fd'])
        row['closed'] = True
    except BaseException as error:
        item = {'phase': 'fd_close', 'label': row['label'], 'error': safe_error(error)}
        row['close_error'] = item['error']
        CLEANUP_ERRORS.append(item)
        # Do not retry close: the numeric FD may already have been retired.

def read_fd(row, bound, code):
    parts = []
    total = 0
    while True:
        check()
        chunk = os.read(row['fd'], min(8192, bound + 1 - total))
        if not chunk:
            return b''.join(parts)
        parts.append(chunk)
        total += len(chunk)
        need(total <= bound, code)

def small(path, bound, label):
    row = acquire(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW |
                  os.O_NONBLOCK, label)
    try:
        return read_fd(row, bound, 'PROC_READ_BOUND')
    finally:
        close_one(row)

def metadata(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
            'size': info.st_size, 'mtime_ns': str(info.st_mtime_ns),
            'ctime_ns': str(info.st_ctime_ns)}

def directory_identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid}

def proc_stat(phase):
    raw = small('/proc/3588093/stat', 8192, phase + '_init_stat')
    at = raw.rfind(b') ')
    need(at > 0 and raw[:at].startswith(b'3588093 ('), 'PROC_STAT_SCHEMA')
    fields = raw[at + 2:].split()
    need(len(fields) >= 20, 'PROC_STAT_FIELDS')
    need(fields[0] not in (b'Z', b'X', b'x'), 'PROCESS_NOT_LIVE')
    return {'pid': 3588093, 'start_ticks': int(fields[19]),
            'ppid': int(fields[1])}

def init_identity(phase, pidfd):
    check()
    need(not select.select([pidfd], [], [], 0)[0], 'PIDFD_DEAD')
    before = proc_stat(phase + '_before')
    need(before == {key: EXPECTED[key] for key in ('pid', 'start_ticks', 'ppid')},
         'INIT_IDENTITY_CHANGED')
    raw = small('/proc/3588093/status', 65536, phase + '_init_status')
    status = {}
    for line in raw.decode('ascii', 'strict').splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        if key in ('Uid', 'NSpid', 'PPid'):
            need(key not in status, 'STATUS_FIELDS')
            status[key] = value.split()
    need(set(status) == {'Uid', 'NSpid', 'PPid'} and
         all(item.isdecimal() for values in status.values() for item in values),
         'STATUS_FIELDS')
    need(len(status['Uid']) == 4 and len(status['PPid']) == 1,
         'STATUS_FIELDS')
    namespaces = {}
    for key in ('mnt', 'pid', 'user'):
        check()
        text = os.readlink('/proc/3588093/ns/' + key)
        need(text.startswith(key + ':[') and text.endswith(']') and
             text[len(key) + 2:-1].isdecimal(), 'NS_LINK_SCHEMA')
        namespaces[key] = text
    cgroup = small('/proc/3588093/cgroup', 8192, phase + '_init_cgroup')
    root_info = os.stat('/proc/3588093/root')
    observed = dict(before)
    observed.update({
        'uids': [int(item) for item in status['Uid']],
        'namespace_pids': [int(item) for item in status['NSpid']],
        'cgroup': cgroup.decode('ascii', 'strict'), 'namespaces': namespaces,
        'root_identity': {'device': root_info.st_dev, 'inode': root_info.st_ino},
    })
    need(int(status['PPid'][0]) == before['ppid'] and observed == EXPECTED,
         'INIT_IDENTITY_CHANGED')
    need(proc_stat(phase + '_after') == before and
         not select.select([pidfd], [], [], 0)[0], 'INIT_IDENTITY_CHANGED')
    return observed

def project(file_id, raw):
    need(file_id in ('main_init_rc', 'main_zygote64_rc'), 'FIXED_FILE_ID')
    try:
        raw.decode('utf-8', 'strict')
    except UnicodeDecodeError:
        raise RuntimeError('FILE_ENCODING') from None
    # Deliberately no general Android init grammar. Exact ASCII public lines only.
    restart = {line.encode(): (code, args) for line, code, args in CATALOG['restart']}
    start = {line.encode(): (code, args) for line, code, args in CATALOG['start']}
    matches = []
    unknown_relevant = []
    context = None
    continued = False
    unknown_lines = 0
    blank_or_comment = 0
    selected_blocks = 0
    lines = raw.split(b'\n')
    if lines and lines[-1] == b'':
        lines.pop()
    def emit(number, code, args):
        matches.append({'line': number, 'code': code, 'public_arguments': args})
        need(len(matches) <= 128, 'PUBLIC_OUTPUT_BOUND')
    for number, line in enumerate(lines, 1):
        body = line.strip(b' \t')
        was_continued = continued
        continued = body.endswith(b'\\')
        if was_continued or continued:
            unknown_lines += 1
            context = None
            continue
        if not body or body.startswith(b'#'):
            blank_or_comment += 1
            continue
        indented = line[:1] in (b' ', b'\t')
        if not indented:
            context = None
            if (file_id == 'main_init_rc' and
                    body == CATALOG['import_zygote'].encode()):
                emit(number, 'IMPORT_PROPERTY_SELECTED_ZYGOTE_RC',
                     ['/system/etc/init/hw/init.$' + '{ro.zygote}.rc'])
                continue
            if (file_id == 'main_init_rc' and
                    body == CATALOG['start_header'].encode()):
                context = 'zygote_start'
                selected_blocks += 1
                emit(number, 'ZYGOTE_START_TRIGGER', ['zygote-start'])
                continue
            if (file_id == 'main_zygote64_rc' and
                    body == CATALOG['zygote_header'].encode()):
                context = 'zygote_service'
                selected_blocks += 1
                emit(number, 'ZYGOTE_SERVICE_APP_PROCESS64_SYSTEM_SERVER',
                     ['zygote', '/system/bin/app_process64', '--start-system-server'])
                continue
        known = restart if context == 'zygote_service' else start if context == 'zygote_start' else {}
        if indented and body in known:
            code, args = known[body]
            emit(number, code, args)
            continue
        unknown_lines += 1
        if context is not None:
            unknown_relevant.append({'line': number, 'bytes': len(line),
                                     'sha256': sha(line), 'context': context})
            need(len(unknown_relevant) <= 128, 'PUBLIC_OUTPUT_BOUND')
    return {
        'closed_catalog_scanned_to_eof': True,
        'line_count': len(lines), 'selected_exact_blocks': selected_blocks,
        'matched_public_occurrences': matches,
        'unknown_or_unselected_line_count': unknown_lines,
        'blank_or_comment_line_count': blank_or_comment,
        'unmatched_lines_inside_selected_blocks': unknown_relevant,
        'full_init_syntax_qualified': False, 'import_resolved': False,
        'ro_zygote_value_observed': False, 'runtime_actions_proved': False,
        'SIGKILL_sender_proved': False, 'OOM_proved': False,
    }

def run_controls():
    names = []
    header = CATALOG['zygote_header'].encode()
    def codes(value):
        return [item['code'] for item in value['matched_public_occurrences']]
    def case(name, value):
        need(value, 'CONTROL_FAILED')
        names.append(name)
    raw = header + b'\n    onrestart restart netd\n    onrestart restart wificond\n'
    case('exact_zygote_block_two_public_restart_actions',
         codes(project('main_zygote64_rc', raw)) == [
             'ZYGOTE_SERVICE_APP_PROCESS64_SYSTEM_SERVER', 'ONRESTART_NETD',
             'ONRESTART_WIFICOND'])
    raw = b'import /system/etc/init/hw/init.$' + b'{ro.zygote}.rc\non zygote-start\n    start zygote\n    start zygote_secondary\n'
    case('exact_import_and_zygote_start_context',
         codes(project('main_init_rc', raw)) == [
             'IMPORT_PROPERTY_SELECTED_ZYGOTE_RC', 'ZYGOTE_START_TRIGGER',
             'ZYGOTE_START_PRIMARY', 'ZYGOTE_START_SECONDARY'])
    case('foreign_service_does_not_project_restart',
         not codes(project('main_zygote64_rc',
             b'service private /private\n    onrestart restart netd\n')))
    changed = header + b'\n    onrestart restart netd PRIVATE_SENTINEL\n'
    value = project('main_zygote64_rc', changed)
    case('suffix_private_text_is_hash_only',
         codes(value) == ['ZYGOTE_SERVICE_APP_PROCESS64_SYSTEM_SERVER'] and
         len(value['unmatched_lines_inside_selected_blocks']) == 1 and
         'PRIVATE_SENTINEL' not in json.dumps(value))
    case('comment_is_not_public_action',
         codes(project('main_zygote64_rc',
             header + b'\n    # onrestart restart netd\n')) ==
         ['ZYGOTE_SERVICE_APP_PROCESS64_SYSTEM_SERVER'])
    case('continuation_does_not_create_public_action',
         codes(project('main_zygote64_rc',
             header + b'\n    private \\\n    onrestart restart netd\n')) ==
         ['ZYGOTE_SERVICE_APP_PROCESS64_SYSTEM_SERVER'])
    case('unindented_action_resets_context',
         codes(project('main_zygote64_rc',
             header + b'\nonrestart restart netd\n    onrestart restart wificond\n')) ==
         ['ZYGOTE_SERVICE_APP_PROCESS64_SYSTEM_SERVER'])
    value = project('main_zygote64_rc',
                    header + b'\n    onrestart restart netd\n    onrestart restart netd\n')
    case('duplicate_occurrences_preserved',
         codes(value).count('ONRESTART_NETD') == 2 and
         [item['line'] for item in value['matched_public_occurrences'][1:]] == [2, 3])
    case('file_scope_is_not_interchangeable',
         not codes(project('main_init_rc', header + b'\n    onrestart restart netd\n')))
    case('zygote_start_requires_exact_header',
         not codes(project('main_init_rc',
             b'on zygote-start && property:private=value\n    start zygote\n')))
    case('CR_is_not_silently_normalized_to_catalog',
         not codes(project('main_zygote64_rc', header + b'\r\n    onrestart restart netd\r\n')))
    try:
        project('main_init_rc', b'\xff\n')
    except RuntimeError as error:
        case('invalid_utf8_fails_without_raw_output', str(error) == 'FILE_ENCODING')
    else:
        need(False, 'CONTROL_FAILED')
    try:
        project('main_zygote64_rc', header + b'\n' +
                b'    onrestart restart netd\n' * 128)
    except RuntimeError as error:
        case('public_occurrence_bound_is_failure', str(error) == 'PUBLIC_OUTPUT_BOUND')
    else:
        need(False, 'CONTROL_FAILED')
    try:
        project('main_zygote64_rc', header + b'\n' + b'    private\n' * 129)
    except RuntimeError as error:
        case('unknown_relevant_bound_is_failure', str(error) == 'PUBLIC_OUTPUT_BOUND')
    else:
        need(False, 'CONTROL_FAILED')
    need(len(names) == 14, 'CONTROL_FAILED')
    return {'state': 'PASS', 'count': len(names), 'names': names,
            'scope': 'Only exact public projection and rejection paths; no process or FD fixture execution.'}

def capture():
    result = {
        'schema': 1, 'collection_complete': False, 'state': 'FAILED',
        'fixed_paths': [item['path'] for item in FILES], 'files': [],
        'current_phase': 'entry', 'current_fixed_path': None,
        'directories': [], 'init_identity_before': None, 'init_identity_after': None,
        'boot_before_qualified': False, 'boot_after_qualified': False,
        'Main_actions': 0, 'Android_actions': 0, 'subprocesses_started': 0,
        'recursive_scans': 0, 'fallback_paths': 0, 'raw_rc_text_exported': False,
        'raw_cmdline_exported': False, 'runtime_authorization_enabled': False,
        'SIGKILL_sender_proved': False, 'OOM_proved': False,
        'upstream_commit': PUBLIC_SOURCE_COMMIT,
        'old_epoch_is_not_current_authority': True,
        'new_QA_epoch_qualified_by_this_reader': False,
        'scope': 'Two fixed held Main root files only. Literal public source occurrence does not prove an action executed, causal order or signal sender.',
    }
    failure = None
    root = None
    pidrow = None
    parent = None
    directory_rows = []
    leaf_rows = []
    try:
        need(os.getuid() == 0 and os.geteuid() == 0, 'ROOT_REQUIRED')
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                              ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        need(libc.prctl(4, 0, 0, 0, 0) == 0 and
             libc.prctl(3, 0, 0, 0, 0) == 0, 'NONDUMP_FAILED')
        result['current_phase'] = 'public_projection_controls'
        result['controls'] = run_controls()
        check()
        need(small('/proc/sys/kernel/random/boot_id', 128, 'boot_before').decode('ascii').strip() == BOOT_ID,
             'BOOT_CHANGED')
        result['boot_before_qualified'] = True
        result['current_phase'] = 'fixed_init_identity'
        result['current_fixed_path'] = '/proc/3588093'
        first = proc_stat('acquire')
        need(first == {key: EXPECTED[key] for key in ('pid', 'start_ticks', 'ppid')},
             'INIT_IDENTITY_CHANGED')
        fd = os.pidfd_open(3588093, 0)
        pidrow = {'label': 'held_main_init_pidfd', 'fd': fd,
                  'close_attempted': False, 'closed': False}
        FDS.append(pidrow)
        result['init_identity_before'] = init_identity('before', fd)
        result['current_phase'] = 'held_main_root'
        result['current_fixed_path'] = '/proc/3588093/root'
        root = acquire('/proc/3588093/root',
                       os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                       'held_main_init_root')
        # The single permitted proc root magic link is bound to the live fixed init.
        root_info = os.fstat(root['fd'])
        need(stat.S_ISDIR(root_info.st_mode), 'NOT_DIRECTORY')
        need({'device': root_info.st_dev, 'inode': root_info.st_ino} ==
             EXPECTED['root_identity'], 'ROOT_IDENTITY_CHANGED')
        root_identity = directory_identity(root_info)
        result['root_identity_before'] = root_identity
        parent = root
        components = []
        for name in ('system', 'etc', 'init', 'hw'):
            components.append(name)
            result['current_phase'] = 'fixed_directory'
            result['current_fixed_path'] = '/proc/3588093/root/' + '/'.join(components)
            named = os.stat(name, dir_fd=parent['fd'], follow_symlinks=False)
            public = {'component': name, 'named_before': directory_identity(named)}
            result['directories'].append(public)
            need(stat.S_ISDIR(named.st_mode), 'NOT_DIRECTORY')
            row = acquire(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC |
                          os.O_NOFOLLOW | os.O_NONBLOCK,
                          'directory_' + name, parent['fd'])
            info = os.fstat(row['fd'])
            public['held_before'] = directory_identity(info)
            need(stat.S_ISDIR(info.st_mode), 'NOT_DIRECTORY')
            need(public['named_before'] == public['held_before'],
                 'DIRECTORY_IDENTITY_CHANGED')
            directory_rows.append((parent, row, name, public))
            parent = row
        for spec in FILES:
            result['current_phase'] = 'fixed_file'
            result['current_fixed_path'] = spec['path']
            public = {'id': spec['id'], 'path': spec['path'], 'complete': False,
                      'upstream_reference': spec['upstream']}
            result['files'].append(public)
            named = os.stat(spec['name'], dir_fd=parent['fd'], follow_symlinks=False)
            public['named_before'] = metadata(named)
            need(stat.S_ISREG(named.st_mode), 'NOT_REGULAR')
            need(0 < named.st_size <= spec['limit'], 'FILE_READ_BOUND')
            row = acquire(spec['name'], os.O_RDONLY | os.O_CLOEXEC |
                          os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME,
                          'file_' + spec['id'], parent['fd'])
            info = os.fstat(row['fd'])
            public['held_before'] = metadata(info)
            need(stat.S_ISREG(info.st_mode), 'NOT_REGULAR')
            need(public['named_before'] == public['held_before'], 'FILE_IDENTITY_CHANGED')
            raw = read_fd(row, spec['limit'], 'FILE_READ_BOUND')
            public['bytes'] = len(raw)
            public['sha256'] = sha(raw)
            need(len(raw) == info.st_size, 'FILE_SIZE_CHANGED')
            public['closed_public_projection'] = project(spec['id'], raw)
            public['matches_exact_pinned_upstream'] = (
                len(raw) == spec['upstream']['bytes'] and
                public['sha256'] == spec['upstream']['sha256'])
            leaf_rows.append((spec, row, public))
        # Keep both leaf FDs open until every read has finished, then recheck names.
        for spec, row, public in leaf_rows:
            result['current_phase'] = 'fixed_file_final_guard'
            result['current_fixed_path'] = spec['path']
            public['held_final'] = metadata(os.fstat(row['fd']))
            public['named_final'] = metadata(os.stat(
                spec['name'], dir_fd=parent['fd'], follow_symlinks=False))
            need(public['named_before'] == public['held_before'] ==
                 public['held_final'] == public['named_final'], 'FILE_IDENTITY_CHANGED')
            public['complete'] = True
        result['current_phase'] = 'directory_and_root_final_guards'
        result['current_fixed_path'] = '/proc/3588093/root/system/etc/init/hw'
        for old_parent, row, name, public in directory_rows:
            public['held_final'] = directory_identity(os.fstat(row['fd']))
            public['named_final'] = directory_identity(os.stat(
                name, dir_fd=old_parent['fd'], follow_symlinks=False))
            need(public['named_before'] == public['held_before'] ==
                 public['held_final'] == public['named_final'], 'DIRECTORY_IDENTITY_CHANGED')
        result['root_identity_final'] = directory_identity(os.fstat(root['fd']))
        named_root = directory_identity(os.stat('/proc/3588093/root'))
        need(result['root_identity_before'] == result['root_identity_final'] ==
             named_root, 'ROOT_IDENTITY_CHANGED')
        result['current_phase'] = 'fixed_init_final_guard'
        result['current_fixed_path'] = '/proc/3588093'
        result['init_identity_after'] = init_identity('after', pidrow['fd'])
        need(result['init_identity_before'] == result['init_identity_after'] ==
             EXPECTED, 'FINAL_AUTHORITY_CHANGED')
        need(small('/proc/sys/kernel/random/boot_id', 128, 'boot_after').decode('ascii').strip() == BOOT_ID,
             'BOOT_CHANGED')
        result['boot_after_qualified'] = True
        check()
        result['current_phase'] = 'observations_completed'
        result['current_fixed_path'] = None
    except BaseException as error:
        failure = safe_error(error)
    finally:
        for row in reversed(FDS):
            close_one(row)
    result['error'] = failure
    result['fd_retirement'] = FDS
    result['cleanup_errors'] = CLEANUP_ERRORS
    result['all_fds_closed'] = bool(FDS) and all(row['closed'] for row in FDS)
    result['elapsed_seconds'] = time.monotonic() - _STARTED
    result['observation_deadline_seconds'] = 12
    result['final_deadline_seconds'] = 14
    result['self_watchdog_seconds'] = 15
    if result['error'] is None and (CLEANUP_ERRORS or not result['all_fds_closed']):
        result['error'] = {'type': 'RuntimeError', 'errno': None, 'code': 'FD_CLEANUP_FAILED'}
    if time.monotonic() >= _FINAL_DEADLINE:
        if result['error'] is None:
            result['error'] = {'type': 'RuntimeError', 'errno': None, 'code': 'FINAL_DEADLINE'}
        result['final_deadline_pass'] = False
    else:
        result['final_deadline_pass'] = True
    if result['error'] is None:
        result['collection_complete'] = True
        result['state'] = 'PASS_FIXED_SOURCE_READ_ONLY'
    return result

if __name__ == '__main__':
    result = capture()
    payload = json.dumps(result, ensure_ascii=True, separators=(',', ':'))
    if len(payload.encode('ascii')) > 65536:
        payload = json.dumps({'schema': 1, 'collection_complete': False,
            'state': 'FAILED', 'error': result.get('error') or {'type': 'RuntimeError', 'code': 'PUBLIC_OUTPUT_BOUND'},
            'output_error': {'type': 'RuntimeError', 'code': 'PUBLIC_OUTPUT_BOUND'},
            'all_fds_closed': result.get('all_fds_closed'),
            'cleanup_errors': result.get('cleanup_errors'),
            'Main_actions': 0, 'Android_actions': 0, 'subprocesses_started': 0,
            'SIGKILL_sender_proved': False, 'OOM_proved': False})
        result['collection_complete'] = False
    # No success output precedes FD cleanup and final deadline qualification.
    sys.stdout.write(payload + '\n')
    sys.stdout.flush()
    signal.setitimer(signal.ITIMER_REAL, 0.0)
    raise SystemExit(0 if result['collection_complete'] else 1)
