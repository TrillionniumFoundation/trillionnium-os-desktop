"""One fixed reboot-reason file from retired Owner15 metadata.img; no mount/write/replay."""
import base64
import errno
import fcntl
import gzip
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

STATE_NAME = 'p4-owner15-normal-20261105-01-state'
NONCE = '7524a823ccabd18edd4bb65a6424a37362514dd7ec66ba913fc83a508b3be5ab'
UNIT = 'p4-owner15-normal-20261105-01.service'
INVOCATION = '3390cef640ed48b597413bcbbcdf3bac'
ACTOR_PID = 2875997
SPEC_SHA256 = 'b408e9902e3670a41c51dbbde0d6223d5b3d111c074183879f1c8f6bb1c56833'
STATE_ID = {'device': 66306, 'inode': 44574133}
IMAGE_ID = {'device': 66306, 'inode': 44574155}
IMAGE_BYTES = 134217728
IMAGE_LABEL = 'p4owner07meta'
IMAGE_PATH = '/opt/' + STATE_NAME + '/data/metadata.img'
RECORDS = {
    'prepared.json': (55139, 'cdcf0db96db1c7100c17faa5c4b0926b544f8c41b8da8960e49788dee3926de8'),
    'runtime-result.json': (59461, '6d35b126c24604d373175479c9bc69e0246a45c05f2061bb8f8077399f0926d5'),
}
DEBUGFS = {
    'path': '/usr/sbin/debugfs', 'bytes': 231368,
    'sha256': '864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f',
    'device': 66306, 'inode': 108006000, 'uid': 0, 'gid': 0, 'mode': 0o755,
    'mtime_ns': 1770985020000000000, 'ctime_ns': 1791083649320555768,
}
TOOL_OBSERVATION_SHA256 = '04b8c44dce6b42cb3d9a9675db037bdf0ef7d2e37d5289a1c6cbb8ce98843599'
RECORD_LIMIT = 1048576
TOOL_LIMIT = 4194304
OUTPUT_LIMIT = 262144
DEADLINE_SECONDS = 35


def need(value, message):
    if not value:
        raise RuntimeError(message)


def check_time(deadline):
    need(time.monotonic() <= deadline, 'metadata collection deadline exceeded')


def identity(value):
    return {'device': value.st_dev, 'inode': value.st_ino}


def stamp(value):
    return {'device': value.st_dev, 'inode': value.st_ino, 'bytes': value.st_size,
            'mode': stat.S_IMODE(value.st_mode), 'type': stat.S_IFMT(value.st_mode),
            'uid': value.st_uid, 'gid': value.st_gid, 'nlink': value.st_nlink,
            'mtime_ns': value.st_mtime_ns, 'ctime_ns': value.st_ctime_ns}


def directory_stamp(value):
    # Shared ancestor contents can change independently; identity and authority cannot.
    return {k: stamp(value)[k] for k in ('device', 'inode', 'type', 'mode', 'uid', 'gid')}


def directory(name, parent, held):
    need(name == '/' if parent is None else name not in ('', '.', '..') and '/' not in name,
         'invalid fixed directory component')
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 **({} if parent is None else {'dir_fd': parent}))
    try:
        value = os.fstat(fd)
        need(stat.S_ISDIR(value.st_mode) and value.st_uid == value.st_gid == 0 and
             not value.st_mode & 0o22, 'fixed directory ownership/type/mode differs')
        before = directory_stamp(value)
        named = os.stat(name, follow_symlinks=False,
                        **({} if parent is None else {'dir_fd': parent}))
        need(directory_stamp(named) == before, 'directory named/held identity differs')
    except BaseException:
        os.close(fd)
        raise
    held.append((fd, parent, name, before, 'directory'))
    return fd


def regular(name, parent, held, maximum):
    need(name in ('prepared.json', 'runtime-result.json', 'metadata.img', 'debugfs'),
         'outside fixed file allowlist')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        value = os.fstat(fd)
        need(stat.S_ISREG(value.st_mode) and value.st_uid == value.st_gid == 0 and
             value.st_nlink == 1 and not value.st_mode & 0o6022 and
             0 < value.st_size <= maximum, 'fixed file ownership/type/mode/nlink/bound differs')
        before = stamp(value)
        need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == before,
             'file named/held identity differs')
    except BaseException:
        os.close(fd)
        raise
    held.append((fd, parent, name, before, 'file'))
    return fd, before


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
    images = [row for row in prepared['data_images'] if row['name'] == 'metadata.img']
    need(len(images) == 1 and images[0]['identity'] == IMAGE_ID and images[0]['bytes'] == IMAGE_BYTES and
         images[0]['fresh_sparse_created'] is True and images[0]['existing_userdata_copied'] is False and
         images[0]['returncode'] == 0, 'image does not bind original fresh creation')
    return {'attempt_nonce': NONCE, 'unit': UNIT, 'invocation': INVOCATION,
            'actor_pid': ACTOR_PID, 'original_runtime_success': False,
            'original_cleanup_bound': True, 'main_before_after_equal': True,
            'continuous_main_claimed': False, 'image_creation_identity': IMAGE_ID}


def image_metadata(fd, before):
    need({k: before[k] for k in ('device', 'inode')} == IMAGE_ID and
         before['bytes'] == IMAGE_BYTES and before['mode'] == 0o600,
         'held image differs from fresh prepared inode/size/mode')
    raw = os.pread(fd, 4096, 0)
    need(len(raw) == 4096 and raw[1080:1082] == bytes.fromhex('53ef'),
         'image ext4 header absent/short')
    superblock = raw[1024:2048]
    observed_uuid_hex = superblock[104:120].hex()
    label = superblock[120:136].split(b'\0', 1)[0].decode('ascii')
    need(label == IMAGE_LABEL, 'image volume label differs')
    log_block_size = int.from_bytes(superblock[24:28], 'little')
    need(log_block_size <= 6, 'invalid ext4 block-size exponent')
    block_size = 1024 << log_block_size
    incompat = int.from_bytes(superblock[96:100], 'little')
    blocks = int.from_bytes(superblock[4:8], 'little')
    if incompat & 0x80:
        blocks |= int.from_bytes(superblock[336:340], 'little') << 32
    need(blocks * block_size == IMAGE_BYTES, 'ext4 geometry differs from fixed image')
    return raw, {'path': IMAGE_PATH, 'identity': before, 'uuid_hex': observed_uuid_hex, 'prior_uuid_available': False,
                 'uuid_bound_to_prior_observation': False,
                 'volume_label': label, 'block_size': block_size, 'blocks': blocks,
                 'ext4_state_bits': int.from_bytes(superblock[58:60], 'little'),
                 'ext4_incompat_features': incompat,
                 'ext4_needs_recovery': bool(incompat & 0x4),
                 'first_4096_sha256': hashlib.sha256(raw).hexdigest(),
                 'full_image_sha256_computed': False, 'image_contents_extracted': False,
                 'guest_mountpoint': '/metadata', 'fixed_reason_path': IMAGE_REASON_PATH,
                 'reason_presence_observed': False}


def tool_metadata(fd, before, deadline):
    for key in ('device', 'inode', 'bytes', 'mode', 'uid', 'gid', 'mtime_ns', 'ctime_ns'):
        need(before[key] == DEBUGFS[key], 'debugfs prior actual identity differs: ' + key)
    need(os.pread(fd, 4, 0) == b'\x7fELF', 'debugfs is not native ELF')
    try:
        caps = os.getxattr(fd, 'security.capability')
    except OSError as error:
        need(error.errno in (errno.ENODATA, errno.EOPNOTSUPP), 'cannot read debugfs capabilities')
        caps = b''
    need(not caps, 'debugfs file capabilities differ')
    raw = read_exact(fd, before['bytes'], deadline)
    need(hashlib.sha256(raw).hexdigest() == DEBUGFS['sha256'], 'debugfs prior actual digest differs')
    return raw, {'path': DEBUGFS['path'], 'identity': before, 'sha256': DEBUGFS['sha256'],
                 'file_capabilities': None, 'prior_observation_sha256': TOOL_OBSERVATION_SHA256,
                 'executed': False}


def recheck(held):
    for fd, parent, name, before, kind in held:
        describe = directory_stamp if kind == 'directory' else stamp
        need(describe(os.fstat(fd)) == before, 'held object changed: ' + name)
        named = os.stat(name, follow_symlinks=False,
                        **({} if parent is None else {'dir_fd': parent}))
        need(describe(named) == before, 'named object changed: ' + name)


IMAGE_NAME = 'metadata.img'
GUEST_REASON_PATH = '/metadata/bootstat/persist.sys.boot.reason'
IMAGE_REASON_PATH = '/bootstat/persist.sys.boot.reason'
STAT_PATHS = ('/', '/bootstat', IMAGE_REASON_PATH)
COMMAND_SECONDS = 8
REAP_SECONDS = 3
STDOUT_LIMIT = 4096
STDERR_LIMIT = 8192
WIRE_LIMIT = 131072
REASON_LIMIT = 4096
DEBUGFS_BANNER = b'debugfs 1.47.2 (1-Jan-2025)\n'


def remembered(row, phase, error):
    record = {'phase': phase, 'error': repr(error)[:4096],
              'traceback': traceback.format_exc()[-8192:]}
    if row['first_error'] is None:
        row['first_error'] = record
    row['errors'].append(record)


def reason_argv(tool_fd, image_fd, operation, path):
    need(type(tool_fd) is type(image_fd) is int and tool_fd >= 3 and image_fd >= 3 and
         tool_fd != image_fd, 'distinct held image/tool FDs required')
    need((operation == 'stat' and path in STAT_PATHS) or
         (operation == 'cat' and path == IMAGE_REASON_PATH),
         'only fixed metadata and one fixed reason body are allowed')
    return [DEBUGFS['path'], '-R', operation + ' ' + path,
            '/proc/self/fd/' + str(image_fd)], '/proc/self/fd/' + str(tool_fd)


def stream_record(body, eof, limit):
    raw = bytes(body)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'base64': base64.b64encode(raw).decode('ascii'),
            'eof': eof, 'byte_limit': limit}


def collect_owned(process, deadline):
    """Drain exactly this Popen child's two pipes; failures retain the original prefix."""
    row = {'pid': process.pid, 'spawned': True, 'pidfd_held': False,
           'joined': False, 'forced_kill': False, 'returncode': None,
           'capture_complete': False, 'first_error': None, 'errors': []}
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    eof = {'stdout': False, 'stderr': False}
    limits = {'stdout': STDOUT_LIMIT, 'stderr': STDERR_LIMIT}
    pidfd = None
    selector = None
    started = time.monotonic()
    try:
        selector = selectors.DefaultSelector()
        # No poll/wait precedes pidfd acquisition: an already exited own child remains waitable.
        pidfd = os.pidfd_open(process.pid, 0)
        row['pidfd_held'] = True
        for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
            need(stream is not None, 'owned child capture pipe missing')
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            need(time.monotonic() < deadline, 'owned debugfs output deadline exceeded')
            for key, _ in selector.select(min(0.1, max(0.0, deadline - time.monotonic()))):
                name = key.data
                remaining = limits[name] - len(streams[name])
                try:
                    block = os.read(key.fd, min(8192, remaining + 1))
                except BlockingIOError:
                    continue
                if not block:
                    eof[name] = True
                    selector.unregister(key.fileobj)
                    continue
                streams[name].extend(block[:remaining])
                need(len(block) <= remaining, 'owned debugfs ' + name + ' byte bound exceeded')
        row['returncode'] = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        row['joined'] = True
        row['capture_complete'] = all(eof.values())
    except BaseException as error:
        remembered(row, 'capture_or_wait', error)
    finally:
        if not row['joined']:
            # The Popen handle is still our exact unreaped child; no numeric PID lookup grants action.
            try:
                if process.poll() is None:
                    row['forced_kill'] = True
                    try:
                        if pidfd is not None:
                            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass  # A concurrent exit does not remove our independent wait obligation.
            except BaseException as error:
                remembered(row, 'exact_child_signal', error)
            try:
                row['returncode'] = process.wait(timeout=REAP_SECONDS)
                row['joined'] = True
            except BaseException as error:
                remembered(row, 'exact_child_retirement', error)
        for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
            if stream is not None:
                try:
                    stream.close()
                except BaseException as error:
                    remembered(row, name + '_pipe_close', error)
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                remembered(row, 'selector_close', error)
        if pidfd is not None:
            try:
                os.close(pidfd)
            except BaseException as error:
                remembered(row, 'pidfd_close', error)
    row['capture_complete'] = (row['capture_complete'] and row['joined'] and
                               not row['forced_kill'] and not row['errors'])
    for name in streams:
        row[name] = stream_record(streams[name], eof[name], limits[name])
    row['elapsed_seconds'] = time.monotonic() - started
    return row


def query_reason(tool_fd, image_fd, operation, path, deadline):
    need((fcntl.fcntl(image_fd, fcntl.F_GETFL) & os.O_ACCMODE) == os.O_RDONLY and
         (fcntl.fcntl(tool_fd, fcntl.F_GETFL) & os.O_ACCMODE) == os.O_RDONLY,
         'image and tool must be held read-only')
    need(fcntl.fcntl(image_fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC and
         fcntl.fcntl(tool_fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC,
         'parent authority FDs must be close-on-exec')
    argv, executable = reason_argv(tool_fd, image_fd, operation, path)
    row = {'image_path': path, 'operation': operation, 'argv': argv,
           'executable_held_path': executable, 'executable_sha256': DEBUGFS['sha256'],
           'default_read_only_mode': True, 'write_option_present': False,
           'journal_replay_requested': False, 'presence_inferred_from_returncode': False}
    child_deadline = min(deadline - REAP_SECONDS - 1, time.monotonic() + COMMAND_SECONDS)
    need(child_deadline > time.monotonic(), 'insufficient remaining collection budget')
    process = subprocess.Popen(argv, executable=executable, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
        pass_fds=(tool_fd, image_fd), cwd='/',
        env={'PATH': '/usr/sbin:/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC',
             'DEBUGFS_PAGER': '__none__', 'PAGER': '__none__', 'E2FSPROGS_UNDO_DIR': 'none'})
    row.update(collect_owned(process, child_deadline))
    return row


def command_bytes(row, name):
    part = row[name]
    raw = base64.b64decode(part['base64'], validate=True)
    need(len(raw) == part['bytes'] and hashlib.sha256(raw).hexdigest() == part['sha256'],
         'owned command stream binding differs')
    return raw


def parse_stat(row, expected_type):
    need(row['operation'] == 'stat' and row['image_path'] in STAT_PATHS and
         row['capture_complete'] is True, 'complete fixed stat required')
    out = command_bytes(row, 'stdout')
    err = command_bytes(row, 'stderr')
    # Tool errors are preserved as observations, never converted into proof of absence.
    if row['returncode'] != 0 or err != DEBUGFS_BANNER:
        return None
    first = re.findall(rb'^Inode: ([0-9]+) +Type: ([a-z]+) +Mode: +([0-7]+) +Flags: (0x[0-9a-fA-F]+)\n', out, re.M)
    sizes = re.findall(rb'^User: +([0-9]+) +Group: +([0-9]+) +Project: +([0-9]+) +Size: ([0-9]+)\n', out, re.M)
    links = re.findall(rb'^Links: ([0-9]+) +Blockcount: ([0-9]+)\n', out, re.M)
    if len(first) != 1 or len(sizes) != 1 or len(links) != 1:
        return None
    inode, kind, mode, flags = first[0]
    uid, gid, project, size = sizes[0]
    if kind.decode('ascii') != expected_type or int(inode) <= 0 or int(links[0][0]) <= 0:
        return None
    value = {'inode': int(inode), 'type': expected_type, 'mode': int(mode, 8),
             'flags': int(flags, 16), 'uid': int(uid), 'gid': int(gid),
             'project': int(project), 'bytes': int(size), 'links': int(links[0][0]),
             'complete_stat_stdout_sha256': row['stdout']['sha256']}
    if row['image_path'] == '/' and value['inode'] != 2:
        return None
    return value


def observed_reason(stats):
    need(len(stats) == 3 and [r['image_path'] for r in stats] == list(STAT_PATHS),
         'exact ordered parent and reason stats required')
    parsed = [parse_stat(row, kind) for row, kind in zip(stats, ('directory', 'directory', 'regular'))]
    eligible = (all(row is not None for row in parsed) and
                len({row['inode'] for row in parsed}) == 3 and
                parsed[2]['links'] == 1 and parsed[2]['bytes'] <= REASON_LIMIT)
    return {'stat_observations': parsed, 'eligible_for_bounded_reason_read': eligible,
            'reason_byte_limit': REASON_LIMIT, 'absence_inferred': False,
            'upstream_reference_is_actual_init_source_proof': False}


def collect_reason(tool, image, header, held, report, deadline):
    def command(operation, path):
        recheck(held)
        need(os.pread(image, 4096, 0) == header, 'image header changed before fixed query')
        row = query_reason(tool, image, operation, path, deadline)
        report['commands'].append(row)
        need(row['capture_complete'] is True, 'owned query capture/retirement incomplete')
        need(os.pread(image, 4096, 0) == header, 'image header changed after fixed query')
        recheck(held)
        return row
    before = [command('stat', path) for path in STAT_PATHS]
    report['reason_observation'] = observed_reason(before)
    if report['reason_observation']['eligible_for_bounded_reason_read']:
        report['reason_read_attempted'] = True
        row = command('cat', IMAGE_REASON_PATH)
        need(row['returncode'] == 0 and command_bytes(row, 'stderr') == DEBUGFS_BANNER,
             'fixed reason body command failed')
        raw = command_bytes(row, 'stdout')
        need(len(raw) == report['reason_observation']['stat_observations'][2]['bytes'],
             'fixed reason body length differs from prior stat')
        # Raw bytes are bounded and retained. No text interpretation or cause attribution here.
        report['image']['image_contents_extracted'] = True
        report['image']['reason_presence_observed'] = True
        report['reason'] = {'guest_path': GUEST_REASON_PATH, 'image_path': IMAGE_REASON_PATH,
                            'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                            'base64': base64.b64encode(raw).decode('ascii')}
    after = [command('stat', path) for path in STAT_PATHS]
    for original, final in zip(before, after):
        need(original['returncode'] == final['returncode'] and
             command_bytes(original, 'stdout') == command_bytes(final, 'stdout') and
             command_bytes(original, 'stderr') == command_bytes(final, 'stderr'),
             'fixed image path metadata changed during reason collection')
    report['reason_stat_unchanged_before_after'] = True
    report['reason_body_collected'] = report['reason_read_attempted'] and 'reason' in report
    report['body_reads_attempted'] = sum(row['operation'] == 'cat' for row in report['commands'])
    need(report['body_reads_attempted'] == int(report['reason_read_attempted']),
         'only one fixed reason body attempt is permitted')
    return len(report['commands']) == 6 + int(report['reason_read_attempted'])


def emit(report):
    raw = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(raw) <= OUTPUT_LIMIT, 'bounded directory report exceeds output limit')
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    envelope = {'schema': 1, 'kind': 'owner15-reboot-reason-read01-gzip',
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'gzip_bytes': len(compressed), 'gzip_sha256': hashlib.sha256(compressed).hexdigest(),
                'gzip_base64': base64.b64encode(compressed).decode('ascii')}
    wire = (json.dumps(envelope, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(wire) <= WIRE_LIMIT, 'bounded directory wire exceeds output limit')
    sys.stdout.buffer.write(wire)


def main():
    report = {'schema': 1, 'kind': 'owner15-retired-reboot-reason-read01',
              'collection_complete': False, 'first_error': None, 'errors': [], 'commands': [],
              'qualification': False, 'owner_failure_cause_proved': False,
              'image_written': False, 'image_mounted': False, 'journal_replayed': False,
              'namespace_changes': False, 'kernel_journal_read': False,
              'live_Main_checked': False, 'reason_read_attempted': False,
              'reason_body_collected': False, 'absence_inferred': False,
              'reason_read_validated_after_final_checks': False,
              'full_image_digest_computed': False, 'external_opener_exclusivity_proved': False,
              'atomic_image_snapshot_claimed': False}
    held = []
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        need(os.geteuid() == os.getegid() == 0, 'fixed protected reason read requires root')
        need(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
             'own child must retain default waitable SIGCHLD semantics')
        slash = directory('/', None, held)
        opt = directory('opt', slash, held)
        state = directory(STATE_NAME, opt, held)
        need(identity(os.fstat(state)) == STATE_ID, 'state inode differs from original prepared')
        records = {}
        record_fds = {}
        report['records'] = {}
        for name in RECORDS:
            fd, before = regular(name, state, held, RECORD_LIMIT)
            raw, value = read_record(fd, before, name, deadline)
            records[name] = value
            record_fds[name] = (fd, before, raw)
            report['records'][name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                                       'identity': before}
        report['binding'] = validate_records(records['prepared.json'], records['runtime-result.json'])
        data = directory('data', state, held)
        image, image_stamp = regular(IMAGE_NAME, data, held, IMAGE_BYTES)
        header, report['image'] = image_metadata(image, image_stamp)
        need(report['image']['ext4_needs_recovery'] is False and
             report['image']['ext4_state_bits'] == 1,
             'unclean fixed ext4 image; no replay, repair or content interpretation permitted')
        usr = directory('usr', slash, held)
        sbin = directory('sbin', usr, held)
        tool, tool_stamp = regular('debugfs', sbin, held, TOOL_LIMIT)
        tool_raw, report['debugfs'] = tool_metadata(tool, tool_stamp, deadline)
        completed = collect_reason(tool, image, header, held, report, deadline)
        need(read_exact(tool, tool_stamp['bytes'], deadline) == tool_raw, 'debugfs bytes changed')
        for name, (fd, before, original) in record_fds.items():
            raw, _ = read_record(fd, before, name, deadline)
            need(raw == original, 'original record changed at final check')
        recheck(held)
        check_time(deadline)
        report['held_named_identity_unchanged'] = True
        report['image_header_and_stat_unchanged'] = True
        report['file_descriptors_opened'] = len(held)
        report['all_command_returncodes_zero'] = all(row['returncode'] == 0 for row in report['commands'])
        report['collection_complete'] = completed
    except BaseException as error:
        remembered(report, 'fixed_reason_collection', error)
    finally:
        for fd, _, name, _, _ in reversed(held):
            try:
                os.close(fd)
            except OSError as error:
                remembered(report, 'held_' + name + '_close', error)
        report['collection_complete'] = report['collection_complete'] and not report['errors']
        report['reason_read_validated_after_final_checks'] = (report['collection_complete'] and
                                                            report['reason_body_collected'])
    report['processes_started'] = sum(row.get('spawned') is True for row in report['commands'])
    if 'debugfs' in report:
        report['debugfs']['executed'] = report['processes_started'] != 0
    report['elapsed_seconds'] = time.monotonic() - (deadline - DEADLINE_SECONDS)
    emit(report)
    return 0 if report['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
