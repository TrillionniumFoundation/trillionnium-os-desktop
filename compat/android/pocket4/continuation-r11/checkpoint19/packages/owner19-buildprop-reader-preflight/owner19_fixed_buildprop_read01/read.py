"""Fixed retired Owner19 host override and image build properties; no extraction or mutation."""
import base64
import errno
import fcntl
import selectors
import signal
import subprocess
import hashlib
import json
import os
import stat
import sys
import time
import traceback
import re

STATE_NAME = 'p4-owner19-normal-20261105-01-state'
NONCE = '08eae45fbb6c6c42c38bd67a6bdcc20b1a6fbe915a3e0fa0ce182a51b58029ed'
UNIT = 'p4-owner19-normal-20261105-01.service'
INVOCATION = '0c03d2ff679f4cfc9e70717280f93075'
ACTOR_PID = 3956131
SPEC_SHA256 = '0e0e3e9b67f4d43a9d66b12ba28e9953941926487e58bd4010f678f36d04a320'
STATE_ID = {'device': 66306, 'inode': 45663385}
IMAGE_ID = {'device': 66306, 'inode': 39237163}
IMAGE_BYTES = 742322176
IMAGE_PACKAGE = 'p4-media-composer-diagnostic-20261102-chat2-r5'
IMAGE_SHA256 = '358a7f008bbfbcd09fb9655d4ed1ff5f07071f89349735aabf7dd381d738b2cf'
IMAGE_PATH = '/opt/' + IMAGE_PACKAGE + '/images/system.img'
RECORDS = {
    'prepared.json': (55273, 'e6b02798bb03598310905852664eec5cbe2329b990571b0d02e71f43d15aa163'),
    'runtime-result.json': (708698, '6e489440223b2515301d56125a19c9357a4ae211ea960b4a41bf96d0ffe9fce5'),
}



DUMP_PATH = '/usr/bin/dump.erofs'
DUMP_SHA256 = '5269be9ba1d20e0f016c4934cb2ab6a7d41e543168527b81b0be15dac044e6a2'
DUMP_IDENTITY = {"bytes":88912,"ctime_ns":1792397752046021992,"device":66306,"gid":0,"inode":108010828,"mode":493,"mtime_ns":1772553600000000000,"nlink":1,"type":32768,"uid":0}
TOOL_OBSERVATION_SHA256 = '92b8161cae5e75305ec1067c2453b8c3de48339f97302c015515e042e1cc7e35'
IMAGE_TIMESTAMP_NS = 1793634278483432061
IMAGE_HEADER_SHA256 = '26adbeb39f761b16b2d7d3d31671c6beb3beb622f4db0cf74c2e5732df7a0e75'
IMAGE_PROPERTY_PATH = '/system/build.prop'
FIXED_BASE_FILES = {
    'payload/41/system-build.prop': {
        'identity': {'device': 66306, 'inode': 39736830}, 'bytes': 6130,
        'sha256': '5efb9d762bdae59c7c8d48e436dbf49a41640045121ea8ccaadde222f08814ba',
        'mode': 0o444},
}
PROPERTY_KEYS = frozenset((
    'ro.build.version.sdk', 'ro.build.version.sdk_full',
    'ro.build.version.release', 'ro.build.version.release_or_codename',
    'ro.build.version.codename', 'ro.build.version.all_codenames',
    'ro.build.type', 'ro.build.fingerprint',
    'ro.system.build.version.sdk', 'ro.system.build.version.sdk_full',
))
RECORD_LIMIT = 1048576
TOOL_LIMIT = 4194304
CONFIG_LIMIT = 32768
ELF_LIMIT = CONFIG_LIMIT  # Existing bounded stream helper uses this legacy cap name.
STDOUT_LIMIT = 16384
STDERR_LIMIT = 8192
OUTPUT_LIMIT = 262144
WIRE_LIMIT = 131072
DEADLINE_SECONDS = 35
COMMAND_SECONDS = 8
REAP_SECONDS = 3


def need(value, message):
    if not value:
        raise RuntimeError(message)


def remember(report, phase, error):
    row = {'phase': phase, 'error': repr(error)[:2048],
           'traceback': traceback.format_exc()[-4096:]}
    if report['first_error'] is None:
        report['first_error'] = row
    report['errors'].append(row)


def check_time(deadline):
    need(time.monotonic() <= deadline, 'metadata collection deadline exceeded')


def identity(value):
    return {'device': value.st_dev, 'inode': value.st_ino}


def stamp(value):
    return {'device': value.st_dev, 'inode': value.st_ino,
            'bytes': value.st_size, 'type': stat.S_IFMT(value.st_mode),
            'mode': stat.S_IMODE(value.st_mode), 'uid': value.st_uid,
            'gid': value.st_gid, 'nlink': value.st_nlink,
            'mtime_ns': value.st_mtime_ns, 'ctime_ns': value.st_ctime_ns}


def directory_stamp(value):
    return {key: stamp(value)[key] for key in ('device', 'inode', 'type', 'mode', 'uid', 'gid')}


def recheck(held):
    for row in held:
        need(row['before'] is not None, 'an opened input did not complete qualification')
        describe = directory_stamp if row['directory'] else stamp
        current = describe(os.fstat(row['fd']))
        named = os.stat(row['name'], follow_symlinks=False,
                        **({} if row['parent'] is None else {'dir_fd': row['parent']}))
        need(current == row['before'] == describe(named), 'fixed input changed: ' + row['name'])


def read_exact(fd, size, deadline):
    body = bytearray()
    while len(body) < size:
        check_time(deadline)
        chunk = os.pread(fd, min(65536, size - len(body)), len(body))
        need(bool(chunk), 'short fixed file read')
        body.extend(chunk)
    need(not os.pread(fd, 1, size), 'fixed file grew past expected size')
    return bytes(body)


def read_record(fd, before, name, deadline):
    size, digest = RECORDS[name]
    need(before['bytes'] == size, 'externally pinned record size differs')
    raw = read_exact(fd, size, deadline)
    need(hashlib.sha256(raw).hexdigest() == digest, 'externally pinned record SHA differs')
    return raw, json.loads(raw.decode('utf-8'))


def validate_records(prepared, runtime):
    need(prepared['attempt_nonce'] == runtime['attempt_nonce'] == NONCE,
         'fixed attempt nonce differs')
    need(prepared['success'] is True and prepared['runtime_executed'] is False and
         prepared['errors'] == [] and prepared['state_identity'] == STATE_ID and
         prepared['canonical_spec_sha256'] == SPEC_SHA256, 'prepared contract differs')
    need(prepared['main_before'] == prepared['main_after'] == prepared['main_final'],
         'prepared Main fence differs')
    need(runtime['success'] is False and runtime['production_ready'] is False and
         runtime['installed_owner_qualified'] is False and
         runtime['prepared_sha256'] == RECORDS['prepared.json'][1],
         'original failed runtime binding differs')
    need(runtime['main_before'] == runtime['main_before_gate'] == runtime['main_after'] ==
         prepared['main_before'], 'actual Main before/after fences differ')
    unit = runtime['first_unit']
    need(unit['InvocationID'] == INVOCATION and int(unit['ExecMainPID']) == ACTOR_PID and
         unit['ControlGroup'] == '/system.slice/' + UNIT, 'original unit identity differs')
    cleanup = runtime['exact_unit_cleanup']
    need(cleanup == {'unit': UNIT, 'invocation': INVOCATION, 'original_actor_dead': True,
                     'unit_not_found': True, 'cgroup_absent': True} and
         runtime['cleanup_stop_returncode'] == 0, 'exact original unit cleanup incomplete')
    actor = runtime['actor_result']
    need(actor['attempt_nonce'] == NONCE and actor['actor_pid'] == ACTOR_PID and
         actor['invocation'] == INVOCATION and actor['success'] is False,
         'original actor identity/outcome differs')
    retired = actor['child_retirement']
    need(len(retired) == 4 and {r['role'] for r in retired} == {'daemon', 'presenter', 'sway', 'bus'} and
         all(r['reaped'] is True and r['forced_kill'] is False for r in retired),
         'exact original child retirement incomplete')
    audit = actor['latest_status']['relay_lifecycle']
    need(audit['canonical_spec_sha256'] == SPEC_SHA256 and audit['retirement_failure'] is None and
         audit['cleanup_failure'] is None and audit['recording_error'] is None and
         audit['recording_incomplete'] is False, 'original typed cleanup audit incomplete')
    events = [r['detail']['event'] for r in audit['records']]
    need(events[-6:] == ['broker_retired', 'processes_dead', 'domain_empty', 'retired',
                         'resources_removed', 'claim_released'] and 'active' not in events,
         'original typed terminal sequence differs')
    need(prepared['base_before'] == prepared['base_after'] and len(prepared['base_before']) == 86,
         'actual immutable base inventory differs')
    images = [row for row in prepared['base_before'] if row['relative'] == 'images/system.img']
    need(images == [{'relative': 'images/system.img', 'identity': IMAGE_ID,
                     'bytes': IMAGE_BYTES, 'sha256': IMAGE_SHA256}],
         'fixed base image does not bind exact prepared inventory')
    for relative, expected in FIXED_BASE_FILES.items():
        matching = [row for row in prepared['base_before'] if row['relative'] == relative]
        need(matching == [{'relative': relative, 'identity': expected['identity'],
                           'bytes': expected['bytes'], 'sha256': expected['sha256']}],
             'fixed base ELF/config does not bind exact prepared inventory')
    return {'attempt_nonce': NONCE, 'unit': UNIT, 'invocation': INVOCATION,
            'actor_pid': ACTOR_PID, 'original_runtime_success': False,
            'original_cleanup_bound': True, 'main_before_after_equal': True,
            'continuous_main_claimed': False, 'base_image_identity': IMAGE_ID,
            'prepared_full_image_sha256': IMAGE_SHA256}


def no_capabilities(fd):
    try:
        value = os.getxattr(fd, 'security.capability')
    except OSError as error:
        need(error.errno in (errno.ENODATA, errno.EOPNOTSUPP),
             'cannot establish fixed tool file capabilities')
        value = b''
    need(value == b'', 'fixed tool has file capabilities')



def opened(name, parent, held, is_directory, maximum=None):
    need(name == '/' if parent is None else name not in ('', '.', '..') and '/' not in name,
         'invalid fixed path component')
    if not is_directory:
        need(name in ('prepared.json', 'runtime-result.json', 'system.img', 'dump.erofs',
                      'system-build.prop'),
             'outside fixed file allowlist')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    if is_directory:
        flags |= os.O_DIRECTORY
    fd = os.open(name, flags, **({} if parent is None else {'dir_fd': parent}))
    row = {'fd': fd, 'parent': parent, 'name': name, 'directory': is_directory,
           'before': None}
    # Register before every fallible metadata operation, including fstat.
    held.append(row)
    need(len(held) <= 20, 'fixed held descriptor count exceeded')
    value = os.fstat(fd)
    if is_directory:
        need(stat.S_ISDIR(value.st_mode) and value.st_uid == value.st_gid == 0 and
             not value.st_mode & 0o022, 'fixed directory authority differs')
        describe = directory_stamp
    else:
        need(type(maximum) is int and stat.S_ISREG(value.st_mode) and
             value.st_uid == value.st_gid == 0 and value.st_nlink == 1 and
             not value.st_mode & 0o6022 and 0 < value.st_size <= maximum,
             'fixed file authority/type/nlink/size differs')
        describe = stamp
    row['before'] = describe(value)
    named = os.stat(name, follow_symlinks=False,
                    **({} if parent is None else {'dir_fd': parent}))
    need(describe(named) == row['before'], 'fixed named and held object differ')
    return fd


def image_metadata(fd, before):
    need(identity(os.fstat(fd)) == IMAGE_ID and before['bytes'] == IMAGE_BYTES and
         before['mode'] == 0o444 and before['mtime_ns'] == before['ctime_ns'] ==
         IMAGE_TIMESTAMP_NS, 'actual fixed image identity/size/mode/timestamps differ')
    raw = os.pread(fd, 4096, 0)
    need(len(raw) == 4096 and hashlib.sha256(raw).hexdigest() == IMAGE_HEADER_SHA256,
         'actual fixed image header differs')
    need(raw[1024:1028] == bytes.fromhex('e2e1f5e0') and
         raw[1080:1082] == bytes.fromhex('a1b7'), 'actual EROFS signature differs')
    return raw, {'path': IMAGE_PATH, 'identity': before, 'format_observed': 'erofs',
                 'first_4096_sha256': IMAGE_HEADER_SHA256,
                 'erofs_magic_hex': raw[1024:1028].hex(),
                 'ext4_offset_bytes_hex': raw[1080:1082].hex(),
                 'prior_prepared_full_sha256': IMAGE_SHA256,
                 'full_image_sha256_computed': False,
                 'guest_and_image_target': IMAGE_PROPERTY_PATH}


def tool_metadata(fd, before, deadline):
    need(before == DUMP_IDENTITY, 'actual dump.erofs full identity differs')
    raw = read_exact(fd, before['bytes'], deadline)
    need(raw[:4] == b'\x7fELF' and hashlib.sha256(raw).hexdigest() == DUMP_SHA256,
         'actual dump.erofs ELF bytes differ')
    no_capabilities(fd)
    return raw, {'path': DUMP_PATH, 'identity': before, 'sha256': DUMP_SHA256,
                 'file_capabilities': None,
                 'prior_help_observation_sha256': TOOL_OBSERVATION_SHA256}


def collect_owned(process, deadline, binary_limit=None, binary_store=None):
    """Join our one child; retain bounded ELF bytes only in the caller's private memory."""
    binary = binary_limit is not None
    row = {'pid': process.pid, 'spawned': True, 'pidfd_held': False, 'joined': False,
           'forced_kill': False, 'returncode': None, 'capture_complete': False,
           'first_error': None, 'errors': []}
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    counts = {'stdout': 0, 'stderr': 0}
    digests = {'stdout': hashlib.sha256(), 'stderr': hashlib.sha256()}
    eof = {'stdout': False, 'stderr': False}
    limits = {'stdout': binary_limit if binary else STDOUT_LIMIT, 'stderr': STDERR_LIMIT}
    first_four = bytearray()
    pidfd = selector = None
    started = time.monotonic()
    try:
        need(not binary or type(binary_limit) is int and 0 < binary_limit <= ELF_LIMIT,
             'bounded metadata-derived binary length required')
        need((binary and isinstance(binary_store, bytearray)) or
             (not binary and binary_store is None), 'binary memory ownership differs')
        selector = selectors.DefaultSelector()
        pidfd = os.pidfd_open(process.pid, 0)
        row['pidfd_held'] = True
        for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
            need(stream is not None, 'owned capture pipe missing')
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            need(time.monotonic() < deadline, 'owned dump output deadline exceeded')
            for key, _ in selector.select(min(0.1, max(0.0, deadline - time.monotonic()))):
                name = key.data
                remaining = limits[name] - counts[name]
                try:
                    block = os.read(key.fd, min(8192, remaining + 1))
                except BlockingIOError:
                    continue
                if not block:
                    eof[name] = True
                    selector.unregister(key.fileobj)
                    continue
                accepted = block[:remaining]
                counts[name] += len(accepted)
                digests[name].update(accepted)
                if name == 'stdout' and binary:
                    first_four.extend(accepted[:max(0, 4 - len(first_four))])
                    binary_store.extend(accepted)
                else:
                    streams[name].extend(accepted)
                need(len(block) <= remaining, 'owned dump ' + name + ' byte bound exceeded')
        row['returncode'] = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        row['joined'] = True
        row['capture_complete'] = all(eof.values())
    except BaseException as error:
        remember(row, 'capture_or_wait', error)
    finally:
        if not row['joined']:
            try:
                if process.poll() is None:
                    row['forced_kill'] = True
                    try:
                        if pidfd is not None:
                            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
            except BaseException as error:
                remember(row, 'exact_child_signal', error)
            try:
                row['returncode'] = process.wait(timeout=REAP_SECONDS)
                row['joined'] = True
            except BaseException as error:
                remember(row, 'exact_child_retirement', error)
        for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
            if stream is not None:
                try:
                    stream.close()
                except BaseException as error:
                    remember(row, name + '_pipe_close', error)
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                remember(row, 'selector_close', error)
        if pidfd is not None:
            try:
                os.close(pidfd)
            except BaseException as error:
                remember(row, 'pidfd_close', error)
    row['capture_complete'] = (row['capture_complete'] and row['joined'] and
                               not row['forced_kill'] and not row['errors'])
    for name in counts:
        value = {'bytes': counts[name], 'sha256': digests[name].hexdigest(),
                 'eof': eof[name], 'byte_limit': limits[name],
                 'digest_scope': 'observed_prefix_until_independently_validated'}
        if binary and name == 'stdout':
            value.update(binary_body_suppressed=True,
                         first_four_bytes_hex=bytes(first_four).hex())
        else:
            value['base64'] = base64.b64encode(streams[name]).decode('ascii')
        row[name] = value
    row['elapsed_seconds'] = time.monotonic() - started
    return row


def command_bytes(row, name):
    part = row[name]
    raw = base64.b64decode(part['base64'], validate=True)
    need(len(raw) == part['bytes'] and hashlib.sha256(raw).hexdigest() == part['sha256'],
         'owned text output integrity differs')
    return raw


def parse_metadata(row):
    need(row['operation'] in ('metadata_before', 'metadata_after') and
         row['capture_complete'] is True and row['returncode'] == 0 and
         command_bytes(row, 'stderr') == b'', 'complete error-free metadata output required')
    raw = command_bytes(row, 'stdout')
    text = raw.decode('ascii', 'strict')
    need(text.endswith('\n'), 'complete newline-terminated metadata required')
    lines = text.splitlines()
    need(len(lines) == 6 and all(0 < len(line) <= 512 for line in lines),
         'fixed complete metadata line schema differs')
    patterns = (
        r'Path[ ]*:[ ]*(' + re.escape(IMAGE_PROPERTY_PATH) + r')[ ]*',
        r'Size:[ ]*([0-9]+)[ ]+On-disk size:[ ]*([0-9]+)[ ]+regular file[ ]*',
        r'NID:[ ]*([0-9]+)[ ]+Links:[ ]*([0-9]+)[ ]+Layout:[ ]*([0-9]+)[ ]+Compression ratio:[ ]*([0-9]+[.][0-9]+)%[ ]*',
        r'Inode size:[ ]*([0-9]+)[ ]+Xattr size:[ ]*([0-9]+)[ ]*',
        r'Uid:[ ]*([0-9]+)[ ]+Gid:[ ]*([0-9]+)[ ]+Access:[ ]*([0-7]{4})/([rwx-]{9})[ ]*',
        r'Timestamp:[ ]*([ -~]{1,128})',
    )
    matches = [re.fullmatch(pattern, line) for pattern, line in zip(patterns, lines)]
    need(all(match is not None for match in matches), 'fixed EROFS inode text schema differs')
    size, disk = (int(x) for x in matches[1].groups())
    nid, links, layout = (int(x) for x in matches[2].groups()[:3])
    inode_size, xattr_size = (int(x) for x in matches[3].groups())
    uid, gid = (int(x) for x in matches[4].groups()[:2])
    access = int(matches[4].group(3), 8)
    permissions = matches[4].group(4)
    symbolic = ''.join(letter if access & (1 << (8 - i)) else '-'
                       for i, letter in enumerate('rwxrwxrwx'))
    need(0 < size <= CONFIG_LIMIT and 0 <= disk <= IMAGE_BYTES and
         0 < nid < (IMAGE_BYTES // 32) and 1 <= links <= 65535 and
         0 <= layout <= 7 and inode_size in (32, 64) and
         0 <= xattr_size <= IMAGE_BYTES and 0 <= uid <= 0xffffffff and
         0 <= gid <= 0xffffffff and 0 <= access <= 0o777 and
         permissions == symbolic, 'fixed EROFS inode tuple outside bounds')
    # The tool prints i_mode & 0777. It does not expose set-ID/sticky bits here.
    return {'path': IMAGE_PROPERTY_PATH, 'type_observed': 'regular file', 'bytes': size,
            'on_disk_bytes': disk, 'nid': nid, 'links': links, 'layout': layout,
            'inode_size': inode_size, 'xattr_size': xattr_size, 'uid': uid, 'gid': gid,
            'access_0777': access, 'access_octal': format(access, '04o'),
            'access_symbolic': permissions, 'complete_mode': None,
            'special_permission_bits_observed': False,
            'metadata_stdout_sha256': row['stdout']['sha256'],
            'complete_metadata_stdout_bytes': row['stdout']['bytes']}


def property_record(body, label, path):
    need(0 < len(body) <= CONFIG_LIMIT, 'fixed build property bytes outside bound')
    text = body.decode('utf-8', 'strict')
    need(text.endswith('\n') and '\x00' not in text,
         'fixed build property text is not complete UTF-8')
    lines = text.splitlines()
    need(len(lines) <= 2048 and all(len(line.encode('utf-8')) <= 4096 for line in lines),
         'fixed build property lines outside bounds')
    values = {key: [] for key in sorted(PROPERTY_KEYS)}
    ignored_non_assignment_lines = 0
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if '=' not in stripped:
            ignored_non_assignment_lines += 1
            continue
        key, value = stripped.split('=', 1)
        key, value = key.strip(), value.strip()
        if key in values:
            values[key].append({'line': number, 'value': value})
    return {'label': label, 'path': path, 'bytes': len(body),
            'sha256': hashlib.sha256(body).hexdigest(),
            'public_build_property_utf8': text, 'selected_properties': values,
            'total_lines': len(lines),
            'non_assignment_lines_not_followed': ignored_non_assignment_lines,
            'selected_keys_with_multiple_occurrences': [key for key in sorted(values)
                                                        if len(values[key]) > 1],
            'imports_or_referenced_paths_read': False,
            'property_value_synthesized': False,
            'valid_replacement_property_values_qualified': False}


def collect_target(tool, image, header, held, report, deadline):
    before = after = None
    property_body = bytearray()

    def command(operation, binary_limit=None):
        need(operation in ('metadata_before', 'cat', 'metadata_after'),
             'outside fixed operation allowlist')
        need(not any(r['operation'] == operation for r in report['commands']),
             'fixed operation cannot be replayed')
        need((operation == 'cat') == (binary_limit is not None), 'bounded stream operation mismatch')
        if operation == 'cat':
            need(before is not None and report.get('metadata_before') is not None and
                 binary_limit == report['metadata_before']['bytes'],
                 'one cat requires this attempt complete regular metadata')
        recheck(held)
        need(os.pread(image, 4096, 0) == header, 'image header changed before query')
        for fd in (tool, image):
            need((fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE) == os.O_RDONLY and
                 fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC,
                 'held tool/image access flags differ')
        child_deadline = min(deadline - REAP_SECONDS - 1,
                             time.monotonic() + COMMAND_SECONDS)
        need(child_deadline > time.monotonic(), 'insufficient remaining query budget')
        argv = [DUMP_PATH, '--path=' + IMAGE_PROPERTY_PATH]
        if operation == 'cat':
            argv.append('--cat')
        argv.append('/proc/self/fd/' + str(image))
        row = {'operation': operation, 'argv': argv,
               'executable': '/proc/self/fd/' + str(tool),
               'executable_sha256': DUMP_SHA256, 'spawned': False, 'joined': False,
               'binary_stdout_expected': operation == 'cat'}
        report['commands'].append(row)
        if operation == 'cat':
            report['property_read_attempted'] = True
        process = subprocess.Popen(argv, executable=row['executable'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, pass_fds=(tool, image), cwd='/',
            env={'PATH': '/usr/bin:/usr/sbin', 'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC'})
        row['spawned'] = True
        row.update(collect_owned(process, child_deadline, binary_limit,
                                 property_body if operation == 'cat' else None))
        need(row['joined'] and row['capture_complete'] and row['returncode'] == 0,
             'fixed query did not complete and join successfully')
        need(command_bytes(row, 'stderr') == b'', 'fixed query emitted an error')
        need(os.pread(image, 4096, 0) == header, 'image header changed after query')
        recheck(held)
        return row

    try:
        before = command('metadata_before')
        report['metadata_before'] = parse_metadata(before)
        inode = report['metadata_before']
        need(inode['uid'] == inode['gid'] == 0 and not inode['access_0777'] & 0o022,
             'fixed image build property owner/access differs')
        row = command('cat', inode['bytes'])
        part = row['stdout']
        need(part['bytes'] == inode['bytes'] and part['eof'] is True and
             part.get('binary_body_suppressed') is True and 'base64' not in part,
             'single fixed property read is not a complete metadata-sized stream')
        need(len(property_body) == part['bytes'] and
             hashlib.sha256(property_body).hexdigest() == part['sha256'],
             'private property buffer does not match complete child stream')
        report['image_property'] = property_record(
            bytes(property_body), 'trusted immutable system image property file',
            IMAGE_PROPERTY_PATH)
        report['image_property']['validated_by_final_checks'] = False
    except BaseException as error:
        remember(report, 'metadata_or_single_property_read', error)
    finally:
        # Independent post-observation; never retry metadata-before or cat.
        # No new child is admitted if a prior owned child was not reaped.
        if any(r.get('spawned') is True for r in report['commands']):
            try:
                need(all(r.get('spawned') is not True or r.get('joined') is True
                         for r in report['commands']), 'prior owned child was not joined')
                after = command('metadata_after')
                report['metadata_after'] = parse_metadata(after)
                need(before is not None and report.get('metadata_before') is not None and
                     command_bytes(before, 'stdout') == command_bytes(after, 'stdout') and
                     command_bytes(before, 'stderr') == command_bytes(after, 'stderr') and
                     report['metadata_before'] == report['metadata_after'],
                     'independent fixed image property metadata is not identical')
                report['metadata_unchanged_before_after'] = True
            except BaseException as error:
                remember(report, 'independent_metadata_after', error)
        property_body.clear()


def emit(report):
    raw = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(raw) <= OUTPUT_LIMIT, 'fixed metadata report exceeds output bound')
    need(len(raw) <= WIRE_LIMIT, 'fixed metadata wire exceeds output bound')
    sys.stdout.buffer.write(raw)


def main():
    report = {'schema': 1, 'kind': 'owner19-fixed-build-property-read01',
              'collection_complete': False, 'qualification': False,
              'owner_failure_cause_proved': False, 'actual_running_peer_bound': False,
              'first_error': None, 'errors': [], 'commands': [], 'records': {},
              'image_written': False, 'image_mounted': False, 'extraction_requested': False,
              'files_created': False, 'namespace_or_UID_changes': False,
              'Main_or_services_touched': False, 'kernel_journal_read': False,
              'live_Main_checked': False, 'property_read_attempted': False,
              'raw_ELF_binary_exported': False, 'raw_runtime_log_exported': False,
              'bounded_system_ELF_code_windows_requested': False,
              'new_tool_execution_requested': False, 'actual_failure_cause_asserted': False,
              'absence_inferred': False, 'property_read_validated_after_final_checks': False,
              'full_image_digest_computed': False, 'external_opener_exclusivity_proved': False,
              'atomic_image_snapshot_claimed': False, 'metadata_unchanged_before_after': False,
              'held_named_unchanged': False, 'held_fds_closed': False}
    held = []
    record_fds = {}
    base_file_fds = {}
    tool = tool_raw = image = header = None
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    try:
        need(os.geteuid() == os.getegid() == 0, 'fixed protected image read requires root')
        need(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
             'own child must retain default waitable SIGCHLD')
        slash = opened('/', None, held, True)
        opt = opened('opt', slash, held, True)
        state = opened(STATE_NAME, opt, held, True)
        need(identity(os.fstat(state)) == STATE_ID, 'original state inode differs')
        records = {}
        for name in RECORDS:
            fd = opened(name, state, held, False, RECORD_LIMIT)
            before_stamp = stamp(os.fstat(fd))
            raw, value = read_record(fd, before_stamp, name, deadline)
            record_fds[name] = (fd, before_stamp, raw)
            records[name] = value
            report['records'][name] = {'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'identity': before_stamp}
        report['binding'] = validate_records(records['prepared.json'], records['runtime-result.json'])
        base = opened(IMAGE_PACKAGE, opt, held, True)
        images = opened('images', base, held, True)
        image = opened('system.img', images, held, False, IMAGE_BYTES)
        header, report['image'] = image_metadata(image, stamp(os.fstat(image)))
        usr = opened('usr', slash, held, True)
        directory = opened('bin', usr, held, True)
        tool = opened('dump.erofs', directory, held, False, TOOL_LIMIT)
        tool_raw, report['dump_erofs'] = tool_metadata(tool, stamp(os.fstat(tool)), deadline)
        payload = opened('payload', base, held, True)
        property_parent = opened('41', payload, held, True)
        property_fd = opened('system-build.prop', property_parent, held, False, CONFIG_LIMIT)
        relative = 'payload/41/system-build.prop'
        expected = FIXED_BASE_FILES[relative]
        value = stamp(os.fstat(property_fd))
        need(identity(os.fstat(property_fd)) == expected['identity'] and
             value['bytes'] == expected['bytes'] and value['mode'] == expected['mode'],
             'fixed host build property metadata differs')
        raw = read_exact(property_fd, expected['bytes'], deadline)
        need(hashlib.sha256(raw).hexdigest() == expected['sha256'],
             'fixed host build property full hash differs')
        base_file_fds[relative] = (property_fd, raw)
        report['fixed_base_files'] = {relative: {'identity': value,
            'sha256': expected['sha256'], 'bytes': len(raw)}}
        report['host_property'] = property_record(
            raw, 'actual pinned host override mounted at /system/build.prop',
            '/opt/' + IMAGE_PACKAGE + '/' + relative)
        collect_target(tool, image, header, held, report, deadline)
    except BaseException as error:
        remember(report, 'fixed_build_property_collection', error)
    finally:
        try:
            if tool_raw is not None:
                need(read_exact(tool, len(tool_raw), deadline) == tool_raw, 'tool bytes changed')
                no_capabilities(tool)
            if header is not None:
                need(os.pread(image, 4096, 0) == header, 'fixed image header changed')
            for name, (fd, original_stamp, original) in record_fds.items():
                raw, _ = read_record(fd, original_stamp, name, deadline)
                need(raw == original, 'original protected record changed')
            for relative, (fd, original) in base_file_fds.items():
                need(read_exact(fd, len(original), deadline) == original,
                     'fixed base ELF/config bytes changed: ' + relative)
            recheck(held)
            report['held_named_unchanged'] = True
        except BaseException as error:
            remember(report, 'final_input_recheck', error)
        closed = True
        for row in reversed(held):
            try:
                os.close(row['fd'])
            except BaseException as error:
                closed = False
                remember(report, 'held_' + row['name'] + '_close', error)
        report['held_fds_closed'] = closed and not any(
            e['phase'].endswith('_close') for c in report['commands'] for e in c.get('errors', []))
    report['held_descriptor_count'] = len(held)
    report['processes_started'] = sum(r.get('spawned') is True for r in report['commands'])
    report['body_reads_attempted'] = sum(r['operation'] == 'cat' for r in report['commands'])
    report['elapsed_seconds'] = time.monotonic() - started
    report['collection_complete'] = (
        not report['errors'] and report['held_named_unchanged'] and report['held_fds_closed'] and
        report['metadata_unchanged_before_after'] and report['body_reads_attempted'] == 1 and
        [r['operation'] for r in report['commands']] == ['metadata_before', 'cat', 'metadata_after'] and
        all(r.get('joined') is True and r.get('capture_complete') is True and
            r.get('returncode') == 0 for r in report['commands']) and
        'image_property' in report and 'host_property' in report and
        len(base_file_fds) == 1 and time.monotonic() <= deadline)
    if time.monotonic() > deadline:
        try:
            raise RuntimeError('fixed metadata observation exceeded its bounded deadline')
        except RuntimeError as error:
            remember(report, 'final_deadline', error)
            report['collection_complete'] = False
    report['property_read_validated_after_final_checks'] = report['collection_complete']
    if 'image_property' in report:
        report['image_property']['validated_by_final_checks'] = report['collection_complete']
    emit(report)
    return 0 if report['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
