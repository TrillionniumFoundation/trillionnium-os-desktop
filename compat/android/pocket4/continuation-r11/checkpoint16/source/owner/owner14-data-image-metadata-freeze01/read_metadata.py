"""Fixed retired Owner14 image/tool metadata only; no child, mount or image write."""
import errno
import hashlib
import json
import os
import stat
import sys
import time
import traceback

STATE_NAME = 'p4-owner14-normal-20261105-01-state'
NONCE = '4b8b529f0b32b58c89a18cbc6adc43884b5c5cd3c5acde5d68c656a073aa0cf7'
UNIT = 'p4-owner14-normal-20261105-01.service'
INVOCATION = '5ccbffb9ae354e719c6ee2dbb49ec7dd'
ACTOR_PID = 2204107
SPEC_SHA256 = '527d9fc3582289341092e4219bee4c257353423d2830c3eba2fb7c64375913e5'
STATE_ID = {'device': 66306, 'inode': 44189296}
IMAGE_ID = {'device': 66306, 'inode': 44189317}
IMAGE_BYTES = 8589934592
IMAGE_UUID_HEX = 'cb90133d9e2c447785cca0636da228eb'
IMAGE_LABEL = 'p4owner07data'
IMAGE_PATH = '/opt/' + STATE_NAME + '/data/data.img'
RECORDS = {
    'prepared.json': (55139, '5771673f20af6833e070da267b0ad9bcbbf58c87e03542104ac57fb9a4466770'),
    'runtime-result.json': (57774, '954fa535427e79780cb3764d0eb28e2ab12b4a4af642c4bccf3244a4e1c97fea'),
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
OUTPUT_LIMIT = 65536
DEADLINE_SECONDS = 10


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
    need(name in ('prepared.json', 'runtime-result.json', 'data.img', 'debugfs'),
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
    images = [row for row in prepared['data_images'] if row['name'] == 'data.img']
    need(len(images) == 1 and images[0]['identity'] == IMAGE_ID and images[0]['bytes'] == IMAGE_BYTES and
         images[0]['fresh_sparse_created'] is True and images[0]['existing_userdata_copied'] is False and
         images[0]['returncode'] == 0, 'image does not bind original fresh creation')
    need('cb90133d-9e2c-4477-85cc-a0636da228eb' in images[0]['stdout'],
         'original mkfs UUID absent')
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
    need(superblock[104:120].hex() == IMAGE_UUID_HEX, 'image UUID differs from original mkfs')
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
    return raw, {'path': IMAGE_PATH, 'identity': before, 'uuid_hex': IMAGE_UUID_HEX,
                 'volume_label': label, 'block_size': block_size, 'blocks': blocks,
                 'ext4_state_bits': int.from_bytes(superblock[58:60], 'little'),
                 'ext4_incompat_features': incompat,
                 'ext4_needs_recovery': bool(incompat & 0x4),
                 'first_4096_sha256': hashlib.sha256(raw).hexdigest(),
                 'full_image_sha256_computed': False, 'image_contents_extracted': False,
                 'guest_mountpoint': '/data',
                 'future_fixed_image_paths': ['/tombstones', '/system/shutdown-checkpoints'],
                 'future_directories_observed': False}


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


def main():
    report = {'schema': 1, 'kind': 'owner14-retired-data-image-metadata01',
              'collection_complete': False, 'first_error': None, 'errors': [],
              'qualification': False, 'image_written': False, 'image_mounted': False,
              'journal_replayed': False, 'tools_executed': False, 'processes_started': False,
              'namespace_changes': False, 'kernel_journal_read': False}
    held = []
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        need(os.geteuid() == os.getegid() == 0, 'fixed protected metadata read requires root')
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
        image, image_stamp = regular('data.img', data, held, IMAGE_BYTES)
        header, report['image'] = image_metadata(image, image_stamp)
        usr = directory('usr', slash, held)
        sbin = directory('sbin', usr, held)
        tool, tool_stamp = regular('debugfs', sbin, held, TOOL_LIMIT)
        tool_raw, report['debugfs'] = tool_metadata(tool, tool_stamp, deadline)
        # All source objects remain held; repeat data bytes and named/held authority checks.
        need(os.pread(image, 4096, 0) == header, 'image header changed during metadata read')
        need(read_exact(tool, tool_stamp['bytes'], deadline) == tool_raw, 'debugfs bytes changed')
        for name, (fd, before, original) in record_fds.items():
            raw, _ = read_record(fd, before, name, deadline)
            need(raw == original, 'original record changed at final check')
        recheck(held)
        check_time(deadline)
        report['held_named_identity_unchanged'] = True
        report['file_descriptors_opened'] = len(held)
        report['collection_complete'] = True
    except BaseException as error:
        record = {'error': repr(error), 'traceback': traceback.format_exc()}
        report['first_error'] = record
        report['errors'].append(record)
    finally:
        for fd, _, name, _, _ in reversed(held):
            try:
                os.close(fd)
            except OSError as error:
                record = {'close_error': repr(error), 'name': name}
                if report['first_error'] is None:
                    report['first_error'] = record
                report['errors'].append(record)
        report['collection_complete'] = report['collection_complete'] and not report['errors']
    report['elapsed_seconds'] = time.monotonic() - (deadline - DEADLINE_SECONDS)
    raw = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(raw) <= OUTPUT_LIMIT, 'metadata report exceeds fixed output bound')
    sys.stdout.buffer.write(raw)
    return 0 if report['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
