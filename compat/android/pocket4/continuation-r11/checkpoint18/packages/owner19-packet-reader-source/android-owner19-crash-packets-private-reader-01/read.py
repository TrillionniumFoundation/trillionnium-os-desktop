"""Private read of one exact retired Owner19 crash-buffer file.

No subprocess, socket, namespace, scan, device mutation, or runtime action.
The original runtime is checked internally and is never emitted. Only the
externally pinned packet file may leave this reader, as PRIVATE base64.
"""
import base64
import hashlib
import json
import os
import stat
import struct
import sys
import time

STATE_NAME = 'p4-owner19-normal-20261105-01-state'
SOURCE_NAME = 'p4-owner19-normal-20261105-01'
UNIT = 'p4-owner19-normal-20261105-01.service'
INVOCATION = '0c03d2ff679f4cfc9e70717280f93075'
ATTEMPT = '08eae45fbb6c6c42c38bd67a6bdcc20b1a6fbe915a3e0fa0ce182a51b58029ed'
PREPARED_SHA256 = 'e6b02798bb03598310905852664eec5cbe2329b990571b0d02e71f43d15aa163'
GENERATION = 'f3872123c12730a76fe362337169ddb5a14bc116ecd24dffc013b79a2bafa677'
RUNTIME_BYTES = 708698
RUNTIME_SHA256 = '6e489440223b2515301d56125a19c9357a4ae211ea960b4a41bf96d0ffe9fce5'
SOURCE_BYTES = 35850
SOURCE_SHA256 = '3e9f0ff5d55c5ea0189173fada455820bf1a88ff3a1f15484893c6cbb2b2db68'
FILE_BYTES = 28314
FILE_SHA256 = '34fe9d3ec735cf18e8852b453cdf2616f32498bedf966346ac66a34ef4ba9deb'
FILE_TUPLE = (66306, 45663422, 28314, 0, 0, 0o400, 1)
MAGIC = b'P4_GENERATION_CRASH_BUFFER4_V1\n'
PACKET_LIMIT = 5 * 1024
RECORD_LIMIT = 2048
CAPACITY = 256 * 1024
HEADER = struct.Struct('<HHiIIIII')
INPUT_LIMIT = 2 * 1024 * 1024
OUTPUT_LIMIT = 131072
SECONDS = 8.0


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def stamp(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink]


def directory_identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid]


def packet_tuple(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_uid,
            value.st_gid, stat.S_IMODE(value.st_mode), value.st_nlink)


class Reader:
    def __init__(self):
        self.deadline = time.monotonic() + SECONDS
        self.fds = []
        self.directories = []
        self.files = []
        self.total_read = 0

    def check_time(self):
        need(time.monotonic() <= self.deadline, 'fixed private read deadline exceeded')

    def own_open(self, name, flags, parent=None):
        self.check_time()
        need(len(self.fds) < 16, 'fixed FD bound exceeded')
        fd = os.open(name, flags, **({} if parent is None else {'dir_fd': parent}))
        self.fds.append(fd)
        return fd

    def directory(self, name, parent=None):
        fd = self.own_open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                           os.O_CLOEXEC, parent)
        value = os.fstat(fd)
        need(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and value.st_gid == 0
             and not value.st_mode & 0o22,
             'protected directory type/owner/mode differs')
        self.directories.append((fd, parent, name, directory_identity(value)))
        return fd

    def member(self, parent, name, expected_bytes, expected_sha256, packet=False):
        need((name, expected_bytes, expected_sha256) in (
             ('runtime-result.json', RUNTIME_BYTES, RUNTIME_SHA256),
             ('crash_log.py', SOURCE_BYTES, SOURCE_SHA256),
             ('generation-crash-buffer4.bin', FILE_BYTES, FILE_SHA256)),
             'outside fixed three-file allowlist')
        fd = self.own_open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, parent)
        value = os.fstat(fd)
        need(stat.S_ISREG(value.st_mode) and value.st_uid == 0 and value.st_gid == 0
             and value.st_nlink == 1 and not value.st_mode & 0o6022
             and value.st_size == expected_bytes,
             'fixed member type/owner/mode/size differs')
        if packet:
            need(packet_tuple(value) == FILE_TUPLE, 'actual packet inode tuple differs')
        row = {'fd': fd, 'parent': parent, 'name': name, 'stamp': stamp(value),
               'bytes': expected_bytes, 'sha256': expected_sha256}
        self.files.append(row)
        return row, self.read(row)

    def read(self, row):
        self.check_time()
        need(stamp(os.fstat(row['fd'])) == row['stamp'],
             'held member changed before read')
        chunks = []
        offset = 0
        while offset <= row['bytes']:
            self.check_time()
            chunk = os.pread(row['fd'], min(32768, row['bytes'] + 1 - offset), offset)
            if not chunk:
                break
            chunks.append(chunk)
            offset += len(chunk)
            self.total_read += len(chunk)
            need(offset <= row['bytes'] and self.total_read <= INPUT_LIMIT,
                 'fixed read or aggregate bound exceeded')
        body = b''.join(chunks)
        need(len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256'],
             'externally pinned whole member differs')
        need(stamp(os.fstat(row['fd'])) == row['stamp'] ==
             stamp(os.stat(row['name'], dir_fd=row['parent'], follow_symlinks=False)),
             'held/named member changed during read')
        return body

    def recheck(self):
        for row in self.files:
            self.read(row)
        for fd, parent, name, identity in reversed(self.directories):
            self.check_time()
            named = os.stat(name, follow_symlinks=False,
                            **({} if parent is None else {'dir_fd': parent}))
            need(directory_identity(os.fstat(fd)) == identity == directory_identity(named),
                 'held/named protected directory identity changed')

    def close(self, errors):
        while self.fds:
            fd = self.fds.pop()
            try:
                os.close(fd)
            except BaseException as error:
                errors.append({'stage': 'close', 'type': type(error).__name__,
                               'message': str(error)[:500]})


def packet_header(packet):
    """Accept only a complete reference v4 crash packet; retain original bytes."""
    need(HEADER.size == 28 and 28 < len(packet) <= PACKET_LIMIT,
         'crash packet size outside reference bound')
    size, header_size, pid, tid, sec, nsec, lid, uid = HEADER.unpack_from(packet)
    need(header_size == 28 and len(packet) == header_size + size,
         'crash packet is incomplete or has a different header schema')
    need(pid > 0 and tid > 0 and sec > 0 and nsec < 1_000_000_000 and lid == 4,
         'crash packet identity/time/buffer differs')
    payload = packet[header_size:]
    need(len(payload) >= 4 and 1 <= payload[0] <= 8 and payload[-1] == 0,
         'crash packet priority or terminator differs')
    boundary = payload.find(b'\0', 1)
    need(1 < boundary <= 129 and boundary < len(payload) - 1,
         'crash packet tag boundary differs')
    tag = payload[1:boundary]
    public = tag.decode('ascii') if tag in (b'DEBUG', b'libc', b'hwservicemanager') else None
    return {'pid': pid, 'tid': tid, 'seconds': sec, 'nanoseconds': nsec,
            'buffer': lid, 'uid': uid, 'priority': payload[0],
            'public_tag': public, 'tag_sha256': hashlib.sha256(tag).hexdigest(),
            'packet_bytes': len(packet)}


def validate_authority(body):
    need(body.isascii(), 'original runtime writer encoding differs')
    runtime = json.loads(body)
    need(runtime['attempt_nonce'] == ATTEMPT and runtime['prepared_sha256'] == PREPARED_SHA256,
         'original attempt/prepared binding differs')
    need(runtime['success'] is False and runtime['first_error']['stage'] == 'normal_coordinator',
         'original normal failure was not preserved')
    actor = runtime['actor_result']
    need(actor['attempt_nonce'] == ATTEMPT and actor['prepared_sha256'] == PREPARED_SHA256
         and actor['success'] is False and actor['invocation'] == INVOCATION
         and actor['first_error']['stage'] == 'normal',
         'original actor attempt/failure differs')
    need(runtime['exact_unit_cleanup'] == {
         'unit': UNIT, 'invocation': INVOCATION, 'unit_not_found': True,
         'cgroup_absent': True, 'original_actor_dead': True}
         and runtime['cleanup_stop_returncode'] == 0,
         'exact retired actor/unit/cgroup authority is absent')
    children = actor['child_retirement']
    need(len(children) == 4 and
         [(r['role'], r['pid'], r['returncode'], r['reaped'], r['forced_kill']) for r in children]
         == [('daemon', 3956199, 0, True, False),
             ('presenter', 3956184, -15, True, False),
             ('sway', 3956144, 0, True, False), ('bus', 3956140, 0, True, False)],
         'original four-child retirement differs')
    main = runtime['main_before']
    need(main == runtime['main_before_gate'] == runtime['main_after']
         and main['held_cgroup_identity'] == [30, 26651611]
         and main['resources']['pids.max'] == '12288'
         and main['installed_contract_unchanged'] is True
         and main['original_processes_alive_and_unchanged'] is True,
         'retained original Main identity gate differs')
    relay = actor['latest_status']['relay_lifecycle']
    need(relay == actor['failure_cleanup_stop']['relay_lifecycle']
         and relay['nonce'] == GENERATION and relay['cleanup_failure'] is None
         and relay['retirement_failure'] is None and relay['recording_error'] is None
         and relay['recording_incomplete'] is False and relay['retained_after_exit'] is True,
         'retained generation/retirement records differ')
    expected_events = ('prepared', 'owner_attached', 'init_hello', 'broker_ready',
                       'init_project_sent', 'init_projected_accepted', 'init_commit_sent',
                       'init_done_accepted', 'retiring', 'broker_retired', 'processes_dead',
                       'domain_empty', 'retired', 'resources_removed', 'claim_released')
    need(len(relay['records']) == 15 and
         tuple((r['sequence'], r['detail']['event']) for r in relay['records']) ==
         tuple(enumerate(expected_events, 1)), 'ordered original lifecycle records differ')
    observation = actor['crash_buffer_observation']
    need(observation['generation_nonce'] == GENERATION and
         observation['state'] == 'BOUNDED_PREFIX_CLOSED' and
         observation['first_error'] is None and observation['secondary_errors'] == [] and
         observation['held_fds_closed'] is True and
         observation['source_qualified_before_request'] is True and
         observation['initial_user_namespace_root_verified'] is True and
         observation['connection_attempts'] == 1 and observation['read_request_attempts'] == 1 and
         observation['read_request_completed'] is True and observation['protocol_observed'] is True,
         'original qualified single-request capture differs')
    need(observation['received_packets'] == 257 and observation['records'] == 257
         and observation['packet_bytes'] == 27190 and observation['eof_observed'] is True
         and observation['capacity_reached'] is False
         and observation['record_bound_reached'] is False
         and observation['public_tag_counts'] == {'DEBUG': 244, 'libc': 13,
                                                  'hwservicemanager': 0, 'other': 0},
         'original bounded packet counts differ')
    need(observation['packet_file'] == {
         'bytes': FILE_BYTES, 'complete_packets_only': True, 'device': FILE_TUPLE[0],
         'gid': 0, 'inode': FILE_TUPLE[1], 'mode': 0o400, 'nlink': 1,
         'relative': 'evidence/generation-crash-buffer4.bin', 'sha256': FILE_SHA256,
         'type': stat.S_IFREG, 'uid': 0}, 'actual packet output record differs')
    elf = observation['fixed_logd_elf_observed']
    need(elf['uid'] == 1036 and elf['gid'] == 1036 and elf['bytes'] == 801680 and
         elf['access_0777'] == 0o550 and elf['special_permission_bits'] == 0 and
         elf['type'] == stat.S_IFREG and elf['read_only_view'] is True and
         elf['sha256'] == '00b71cfeea17a2fa6b2fa4047fb320bdd9d7b64ce16366bbbd2abdbda09d0905'
         and observation['peer_credentials'] == {'pid': 3957526, 'uid': 1036, 'gid': 1036},
         'original observed logd ELF or peer credentials differ')
    need(all(observation[k] is False for k in (
         'Main_logs_read', 'namespace_or_UID_change_requested', 'new_child_started',
         'log_mutation_requested', 'original_stop_delayed_for_logs',
         'hws_attribution_qualified', 'empty_proves_hws_health',
         'complete_log_stream_claimed')) and actor['crash_buffer_HWS_health_qualified'] is False,
         'original capture scope/qualification differs')
    return observation


def parse_packets(body, observation):
    prefix = MAGIC + GENERATION.encode('ascii') + b'\n'
    need(len(prefix) == 96 and body.startswith(prefix), 'generation file framing differs')
    offset = len(prefix)
    records = []
    packet_bytes = 0
    counts = {'DEBUG': 0, 'libc': 0, 'hwservicemanager': 0, 'other': 0}
    while offset < len(body):
        need(len(records) < RECORD_LIMIT and offset + 4 <= len(body),
             'frame count or length header bound differs')
        size, = struct.unpack_from('<I', body, offset)
        offset += 4
        need(28 < size <= PACKET_LIMIT and offset + size <= len(body),
             'complete framed packet length differs')
        packet = body[offset:offset + size]
        offset += size
        record = packet_header(packet)
        records.append(record)
        packet_bytes += size
        counts[record['public_tag'] or 'other'] += 1
    need(offset == len(body) <= CAPACITY and len(records) == 257
         and packet_bytes == 27190 and counts == observation['public_tag_counts'],
         'complete file framing/counts differ from capture')
    need(records[0] == observation['first_header'] and
         records[-1] == observation['last_header'],
         'first/last complete protocol header differs')
    return {'framing_header_bytes': len(prefix), 'complete_records': len(records),
            'packet_bytes': packet_bytes, 'frame_length_bytes': 4 * len(records),
            'public_tag_counts': counts, 'first_header': records[0],
            'last_header': records[-1], 'private_message_body_exported_in_summary': False}


def main():
    result = {'schema': 1, 'kind': 'owner19-retired-crash-packet-private-read01',
              'collection_complete': False, 'held_fds_closed': False,
              'private_output': True, 'raw_output_must_not_be_published': True,
              'runtime_qualification_asserted': False, 'hws_health_asserted': False,
              'read_only': True, 'new_runtime_action': False, 'errors': []}
    reader = Reader()
    packet_body = None
    checked = False
    try:
        need(os.geteuid() == 0 and os.getegid() == 0, 'root-only exact private read required')
        slash = reader.directory('/')
        opt = reader.directory('opt', slash)
        state = reader.directory(STATE_NAME, opt)
        evidence = reader.directory('evidence', state)
        package = reader.directory(SOURCE_NAME, opt)
        source_dir = reader.directory('source', package)
        runtime_row, runtime_body = reader.member(state, 'runtime-result.json',
                                                  RUNTIME_BYTES, RUNTIME_SHA256)
        observation = validate_authority(runtime_body)
        source_row, source_body = reader.member(source_dir, 'crash_log.py',
                                               SOURCE_BYTES, SOURCE_SHA256)
        need(source_body.isascii(), 'fixed collector source encoding differs')
        packet_row, packet_body = reader.member(evidence, 'generation-crash-buffer4.bin',
                                               FILE_BYTES, FILE_SHA256, packet=True)
        result['framing'] = parse_packets(packet_body, observation)
        reader.recheck()
        result['inputs'] = [{'path': '/opt/' + STATE_NAME + '/runtime-result.json',
                             'bytes': RUNTIME_BYTES, 'sha256': RUNTIME_SHA256,
                             'identity': runtime_row['stamp'], 'body_emitted': False},
                            {'path': '/opt/' + SOURCE_NAME + '/source/crash_log.py',
                             'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA256,
                             'identity': source_row['stamp'], 'body_emitted': False},
                            {'path': '/opt/' + STATE_NAME + '/evidence/generation-crash-buffer4.bin',
                             'bytes': FILE_BYTES, 'sha256': FILE_SHA256,
                             'identity': packet_row['stamp'], 'body_emitted': False}]
        result['authority'] = {'attempt_nonce': ATTEMPT, 'prepared_sha256': PREPARED_SHA256,
                               'generation_nonce': GENERATION, 'unit': UNIT,
                               'invocation': INVOCATION, 'original_runtime_success': False,
                               'retained_exact_cleanup_verified': True,
                               'current_process_or_Main_probe_performed': False,
                               'source_qualified_capture_record_verified': True}
        result['second_whole_reads_and_final_held_named_checks'] = True
        checked = True
    except BaseException as error:
        result['errors'].append({'stage': 'collection', 'type': type(error).__name__,
                                 'message': str(error)[:500]})
    finally:
        before_close = len(result['errors'])
        reader.close(result['errors'])
        result['held_fds_closed'] = len(result['errors']) == before_close and not reader.fds
    result['collection_complete'] = checked and result['held_fds_closed'] and not result['errors']
    if result['collection_complete']:
        result['inputs'][2]['body_emitted'] = True
        result['private_file'] = {'encoding': 'base64', 'bytes': FILE_BYTES,
                                  'sha256': FILE_SHA256,
                                  'data': base64.b64encode(packet_body).decode('ascii')}
    result['bounded_read_bytes'] = reader.total_read
    raw = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(raw) <= OUTPUT_LIMIT, 'private plain envelope bound exceeded')
    need(sys.stdout.buffer.write(raw) == len(raw), 'private output write incomplete')
    sys.stdout.buffer.flush()
    return 0 if result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
