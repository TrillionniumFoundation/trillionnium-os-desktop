"""Current AudioFlinger rows and exact host protocol attribution.

The grammar is taken from frameworks/av at
475269ec44acec82792be6b01fb8e16357d4d2c8, Threads.cpp and Tracks.cpp.
These pure functions do not inspect Main, trust a historical dump or qualify
physical audio. The caller must collect each dump through its held current
Main, hold the app/HAL process generations and preserve the raw receipts.
"""
import copy
import hashlib
import json
import math
import re

FRAMEWORK_COMMIT = '475269ec44acec82792be6b01fb8e16357d4d2c8'
SOURCE_PINS = {
    'services/audioflinger/Threads.cpp': (490438, 'a5416ff05a3683712075ca1a383a73ebfb9331b18e88bfadfbc6aba2b62a13bc'),
    'services/audioflinger/Tracks.cpp': (154428, '420040347f18e8708e2faeec1991c06238a467558190435788492b8e1648b6e2'),
    'services/audioflinger/AudioFlinger.cpp': (209703, '4906b0655b008b9fdb5584bca19128ecbe0beee3ec1105a103f17b4ce06e1a76'),
}
HAL_PATH = '/apex/com.android.hardware.audio.droidloom/bin/hw/android.hardware.audio.service-aidl.droidloom'
CAMERA_UID = 10062
GALLERY_UID = 10064
SOURCE_NAME = 'alsa_input.pci-0000_c5_00.6.analog-stereo'
SINK_NAME = 'alsa_output.pci-0000_c5_00.6.analog-stereo'
BUS_PATH = 'pci-0000:c5:00.6'
INPUT_PORT = 'analog-input-internal-mic'
OUTPUT_PORT = 'analog-output-speaker'
THREAD = re.compile(r'^(Input|Output) thread (0x[0-9a-f]+), name ([A-Za-z0-9_ -]+), tid ([1-9][0-9]*), type ([0-9]+) \(([A-Z_]+)\):$', re.M)
RECORD = re.compile(r'^\s*(F)?\s*(yes|no)\s+([0-9]+)\s+([0-9]+)\s*/\s*([0-9]+)\s+'
    r'([0-9]+)\s+([0-9]+)\s+(\S+)\s+0x([0-9a-fA-F]+)\s+'
    r'([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+([0-9]+)\s+([0-9a-fA-F]+)\s+'
    r'([0-9a-fA-F]{8})\s+([0-9]+)\s+([0-9]+)\s+([sn])'
    r'(?:\s+(?:[0-9]+\.[0-9]+\s+[tk]|unavail|new))?\s*$', re.M)
DB = r'(?:[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[-+]?[0-9]+)?|[-+]?(?:inf|nan))'
PLAYBACK = re.compile(r'^\s*(F[0-9]+)?\s*([SP?])?\s*([0-9]+)\s+(yes|no)\s+'
    r'([0-9]+)\s*/\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+(\S+)\s+0x([0-9a-fA-F]+)\s+'
    r'([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+([0-9]+)\s+'
    r'([0-9]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+'
    + r'\s+'.join('(' + DB + ')' for _ in range(4)) + r'(A)?\s+(' + DB + r')\s+(true|false)\s+'
    r'([0-9a-fA-F]{8})\s+([0-9]+)([re])?\s+([0-9]+)\s+([IfFA?])\s+'
    r'([0-9]+)([<*?])?\s+([0-9]+)\s+(true|false)\s+(true|false)'
    r'(?:\s+(?:[0-9]+\.[0-9]+\s+[tk]|unavail|new))?\s*$', re.M)


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def one(pattern, text):
    rows = re.findall(pattern, text, re.M)
    need(len(rows) == 1, 'ONE_EXACT_CURRENT_AUDIO_FIELD:' + pattern)
    return rows[0]


def record_row(match):
    v = match.groups()
    return {'fast': v[0] is not None, 'active': v[1] == 'yes', 'id': int(v[2]),
        'pid': int(v[3]), 'uid': int(v[4]), 'session': int(v[5]), 'port': int(v[6]),
        'state': v[7], 'flags': int(v[8], 16), 'format': int(v[9], 16),
        'channel_mask': int(v[10], 16), 'sample_rate': int(v[11]), 'source': int(v[12], 16),
        'server_frames': int(v[13], 16), 'buffer_frames': int(v[14]),
        'ready_frames': int(v[15]), 'silenced': v[16] == 's'}


def playback_row(match):
    v = match.groups()
    # Preserve printed float strings, including legitimate -inf on inactive
    # tracks. Only the selected active playback below must have audible volume.
    return {'fast_slot': v[0], 'track_type': v[1] or 'normal', 'id': int(v[2]),
        'active': v[3] == 'yes', 'pid': int(v[4]), 'uid': int(v[5]),
        'session': int(v[6]), 'port': int(v[7]), 'state': v[8], 'flags': int(v[9], 16),
        'format': int(v[10], 16), 'channel_mask': int(v[11], 16), 'sample_rate': int(v[12]),
        'stream': int(v[13]), 'usage': int(v[14], 16), 'content_type': int(v[15], 16),
        'final_volume_db': v[16], 'left_db': v[17], 'right_db': v[18],
        'shaper_db': v[19], 'shaper_active': v[20] == 'A', 'port_volume_db': v[21],
        'port_muted': v[22] == 'true', 'server_frames': int(v[23], 16),
        'buffer_frames': int(v[24]), 'buffer_modified': v[25], 'ready_frames': int(v[26]),
        'filling': v[27], 'underrun_frames': int(v[28]), 'underrun_state': v[29],
        'flushed_frames': int(v[30]), 'bit_perfect': v[31] == 'true', 'internal_muted': v[32] == 'true'}


def flinger(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_ACTUAL_AUDIOFLINGER_DUMP')
    text = raw.decode('utf-8', 'strict')
    need('Permission Denial' not in text and 'Thread may be deadlocked' not in text
        and 'AudioFlinger may be deadlocked' not in text, 'LIVE_COMPLETE_AUDIO_DUMP_REQUIRED')
    begin, end = '\n ## BEGIN thread dump \n', '\n ## BEGIN setParameters dump \n'
    need(text.count(' ## BEGIN thread dump ') == text.count(begin) == 1
        and text.count(' ## BEGIN setParameters dump ') == text.count(end) == 1
        and text.index(begin) < text.index(end),
         'LOCKED_AUDIOFLINGER_CURRENT_THREAD_SECTION')
    body = text.split(begin, 1)[1].split(end, 1)[0]
    # AudioFlinger::dump emits every current thread via ThreadBase::dump,
    # before ThreadLog. Historical thread lines use the separate "- " prefix
    # in AudioFlinger::dumpToThreadLog_l; they cannot supply current rows.
    history = re.search(r'^Historical Thread Log ', body, re.M)
    if 'Historical Thread Log ' in body:
        need(history is not None and body.index('Historical Thread Log ') == history.start(),
             'UNRECOGNIZED_HISTORICAL_AUDIO_THREAD_BOUNDARY')
        need(not re.search(r'^(?:Input|Output) thread\b', body[history.start():], re.M),
             'CURRENT_AUDIO_THREAD_AFTER_HISTORICAL_BOUNDARY')
        body = body[:history.start()]
    headers = list(THREAD.finditer(body))
    # Zero matches are not evidence of idle audio. Every nonempty current
    # top-level line must be a complete pinned ThreadBase header. Opaque HAL,
    # effect or scheduler text at column zero is unsupported and is refused;
    # no unknown thread grammar can be skipped as an empty track table.
    need(1 <= len(headers) <= 64, 'COMPLETE_NONEMPTY_CURRENT_AUDIO_THREAD_SET')
    need(not body[:headers[0].start()].strip()
        and all(THREAD.fullmatch(line) for line in body.split('\n')
                if line and not line[0].isspace())
        and not re.search(r'^[ \t]+(?:Input|Output) thread\b', body, re.M),
         'UNRECOGNIZED_CURRENT_AUDIO_THREAD_FRAMING')
    need('  Orphan Effect Chains\n' not in body, 'UNQUALIFIED_ORPHAN_AUDIO_EFFECT_CHAINS')
    result = []
    for index, header in enumerate(headers):
        segment = body[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(body)]
        endings = list(re.finditer(r'^  Local log:\n', segment, re.M))
        need(len(endings) == 1, 'EXACT_CURRENT_THREAD_END')
        current = segment[:endings[0].start()]
        direction, pointer, name, tid, _, kind = header.groups()
        # Mmap has a separate table. Refuse it (and every other unsupported
        # kind) for every UID, even when its own table reports zero tracks.
        kinds = ('RECORD', 'DIRECT_RECORD') if direction == 'Input' else (
            'MIXER', 'DIRECT', 'DUPLICATING', 'OFFLOAD', 'SPATIALIZER')
        need(kind in kinds, 'UNQUALIFIED_AUDIO_THREAD_TYPE:' + kind)
        need('The following tracks are in the active list but not in the track list' not in current,
             'INCONSISTENT_CURRENT_ACTIVE_TRACK_LIST')
        io = int(one(r'^  I/O handle: ([0-9]+)$', current))
        standby = one(r'^  Standby: (yes|no)$', current) == 'yes'
        count = re.findall(r'^  ([0-9]+) Tracks(?: of which ([0-9]+) are active)?$', current, re.M)
        need(len(count) == 1, 'ONE_COMPLETE_CURRENT_TRACK_TABLE')
        total, active = int(count[0][0]), int(count[0][1] or 0)
        need(0 <= active <= total <= 128 and (total == 0) == (count[0][1] == ''), 'ACTUAL_TRACK_COUNTS')
        rows = [record_row(m) for m in RECORD.finditer(current)] if direction == 'Input' else [playback_row(m) for m in PLAYBACK.finditer(current)]
        need(len(rows) == total and sum(row['active'] for row in rows) == active
            and len({row['id'] for row in rows}) == len(rows), 'FULL_ACTUAL_TRACK_TABLE_OR_FORMAT_MISMATCH')
        key = 'read' if direction == 'Input' else 'written'
        frames = int(one(r'^  Frames ' + key + r': ([0-9]+)$', current))
        row = {'direction': direction, 'pointer': pointer, 'name': name, 'tid': int(tid),
            'kind': kind, 'io_handle': io, 'standby': standby, 'frames': frames, 'tracks': rows}
        if direction == 'Input':
            source, source_name = one(r'^  Audio source: ([0-9]+) \(([^\n]+)\)$', current)
            row.update(audio_source=int(source), audio_source_name=source_name,
                hardware_silenced=one(r'^  Hw silenced: (yes|no)$', current) == 'yes')
        else:
            row['master_muted'] = one(r'^  Master mute: (on|off)$', current) == 'on'
        result.append(row)
    need(len({row['io_handle'] for row in result}) == len(result), 'UNIQUE_CURRENT_IO_HANDLES')
    return {'raw_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'framework_commit': FRAMEWORK_COMMIT, 'current_thread_headers': len(headers),
        'historical_thread_log_excluded': history is not None,
        'threads': result, 'runtime_qualified': False}


def active_tracks(value):
    need(value['framework_commit'] == FRAMEWORK_COMMIT
        and 1 <= len(value['threads']) == value['current_thread_headers'] <= 64,
         'PINNED_NONEMPTY_CURRENT_AUDIO_TABLES_REQUIRED')
    return [(thread, track) for thread in value['threads']
            for track in thread['tracks'] if track['active']]


def quiescent(value):
    need(not active_tracks(value), 'UNEXPECTED_ACTIVE_ANDROID_AUDIO_TRACK')
    # This receipt is scoped to current Android track tables at one sample.
    # It does not prove host PipeWire quiescence or exclusivity between samples.
    return {'scope': 'android-audioflinger-current-track-tables-all-uids',
        'framework_commit': FRAMEWORK_COMMIT, 'raw_sha256': value['raw_sha256'],
        'observed_threads': value['current_thread_headers'], 'active_track_count': 0,
        'host_audio_quiescence_qualified': False, 'continuous_exclusivity_qualified': False,
        'runtime_qualified': False}


def owned_track(value, *, direction, uid, pid):
    need(direction in ('Input', 'Output') and type(uid) is type(pid) is int and pid > 0,
         'CURRENT_APPLICATION_PID_UID_REQUIRED')
    rows = active_tracks(value)
    need(len(rows) == 1 and rows[0][0]['direction'] == direction
        and rows[0][1]['uid'] == uid and rows[0][1]['pid'] == pid,
         'ONE_EXCLUSIVE_CURRENT_APP_ATTRIBUTED_ACTIVE_AUDIO_TRACK')
    thread, track = rows[0]
    need(thread['standby'] is False and track['session'] > 0 and track['port'] > 0
        and track['buffer_frames'] > 0 and 8000 <= track['sample_rate'] <= 192000,
         'ACTUAL_RUNNING_APP_AUDIO_GEOMETRY')
    if direction == 'Input':
        need(uid == CAMERA_UID and track['source'] == 5 and thread['audio_source'] == 5
            and thread['audio_source_name'] == 'AUDIO_SOURCE_CAMCORDER'
            and track['silenced'] is False and thread['hardware_silenced'] is False,
             'REAL_UNSILENCED_CAMERA_CAMCORDER_TRACK')
    else:
        need(uid == GALLERY_UID and track['stream'] == 3 and track['usage'] == 1
            and thread['master_muted'] is False and track['port_muted'] is False
            and track['internal_muted'] is False and all(math.isfinite(float(track[k]))
            for k in ('final_volume_db', 'left_db', 'right_db', 'port_volume_db')),
             'REAL_UNMUTED_GALLERY_MEDIA_PLAYBACK_TRACK')
    return {'thread': copy.deepcopy(thread), 'track': copy.deepcopy(track)}


def advancing(first, second, *, direction, uid, pid, elapsed_ns):
    need(type(elapsed_ns) is int and 200_000_000 <= elapsed_ns <= 8_000_000_000,
         'BOUNDED_DISTINCT_LIVE_AUDIO_OBSERVATIONS')
    a = owned_track(first, direction=direction, uid=uid, pid=pid)
    b = owned_track(second, direction=direction, uid=uid, pid=pid)
    need(all(a['thread'][key] == b['thread'][key] for key in ('pointer', 'tid', 'kind', 'io_handle'))
        and all(a['track'][key] == b['track'][key] for key in
            ('id', 'pid', 'uid', 'session', 'port', 'format', 'channel_mask', 'sample_rate')),
         'SAME_ACTUAL_AUDIO_THREAD_TRACK_AND_SESSION')
    increment = (b['track']['server_frames'] - a['track']['server_frames']) & 0xffffffff
    maximum = math.ceil(a['track']['sample_rate'] * elapsed_ns / 1e9) * 4 + a['track']['buffer_frames'] * 4
    need(0 < increment <= maximum and b['thread']['frames'] > a['thread']['frames'],
         'ACTUAL_AUDIO_FRAMES_MUST_ADVANCE_IN_OBSERVED_INTERVAL')
    return {'first': a, 'second': b, 'elapsed_ns': elapsed_ns,
        'track_frames_advanced': increment, 'thread_frames_advanced': b['thread']['frames'] - a['thread']['frames'],
        'physical_audio_qualified': False, 'runtime_qualified': False}


def absent(value, uid, direction):
    need(not any(track['active'] and track['uid'] == uid
        for thread in value['threads'] if thread['direction'] == direction for track in thread['tracks']),
        'OWNED_APP_AUDIO_TRACK_STILL_ACTIVE')
    return True


def journal(raw, *, unit, invocation, manager_pid, boot_id):
    need(type(raw) is bytes and len(raw) <= 16777216 and type(manager_pid) is int and manager_pid > 1
        and unit in ('droidloom-audio-capture.service', 'droidloom-audio-host.service')
        and re.fullmatch('[0-9a-f]{32}', invocation) and re.fullmatch('[0-9a-f-]{36}', boot_id),
        'EXACT_CURRENT_AUDIO_HELPER_JOURNAL_BINDING')
    rows = []; seen = set(); previous = 0
    for line in raw.decode('utf-8', 'strict').splitlines():
        if not line:
            continue
        need(len(line) <= 131072 and len(rows) < 16384, 'BOUNDED_CURRENT_AUDIO_JOURNAL')
        row = json.loads(line)
        need(row.get('_SYSTEMD_UNIT') == unit and row.get('_SYSTEMD_INVOCATION_ID') == invocation
            and row.get('_PID') == str(manager_pid) and row.get('_BOOT_ID') == boot_id.replace('-', ''),
             'JOURNAL_NOT_FROM_HELD_EXACT_AUDIO_HELPER_GENERATION')
        cursor = row.get('__CURSOR'); timestamp = row.get('__MONOTONIC_TIMESTAMP')
        need(type(cursor) is str and cursor and cursor not in seen and type(timestamp) is str and timestamp.isdecimal(),
             'UNIQUE_ACTUAL_JOURNAL_CURSOR_AND_MONOTONIC_TIME')
        now = int(timestamp); need(now >= previous, 'AUDIO_JOURNAL_TIME_REGRESSION')
        seen.add(cursor); previous = now
        try:
            value = json.loads(row.get('MESSAGE', ''))
        except (ValueError, TypeError):
            continue
        if type(value) is dict and 'event' in value:
            need(value['event'] not in ('stream_error', 'host_error', 'capture_error'), 'CURRENT_AUDIO_PROTOCOL_ERROR')
            rows.append({'cursor': cursor, 'monotonic_us': now, 'value': value})
    return {'unit': unit, 'invocation': invocation, 'manager_pid': manager_pid, 'boot_id': boot_id,
        'raw_sha256': hashlib.sha256(raw).hexdigest(), 'rows': rows}


def protocol_window(document, *, role, hal_pid, hal_uid, hal_gid, hal_cgroup, begin_ns, end_ns):
    need(role in ('input', 'output') and type(hal_pid) is int and hal_pid > 1
        and type(hal_uid) is type(hal_gid) is int and 0 <= hal_uid < 4294967295 and 0 <= hal_gid < 4294967295
        and type(begin_ns) is type(end_ns) is int and 0 < begin_ns < end_ns
        and 200_000_000 <= end_ns - begin_ns <= 25_000_000_000,
         'CURRENT_HELD_HAL_AND_FINITE_BUSINESS_AUDIO_INTERVAL')
    expected_unit = 'droidloom-audio-capture.service' if role == 'input' else 'droidloom-audio-host.service'
    need(document['unit'] == expected_unit, 'PROTOCOL_ROLE_MISMATCH')
    rows = [r for r in document['rows'] if r['monotonic_us'] * 1000 <= end_ns]
    peers = [i for i, r in enumerate(rows) if r['value'].get('event') == 'peer']
    need(peers, 'ACTUAL_HAL_PEER_BOUNDARY_REQUIRED')
    start = peers[-1]; peer = rows[start]['value']
    # The helper's SO_PEERCRED values use its observing user namespace. The
    # caller binds that namespace to the held /proc observer and maps guest
    # HAL UID/GID 1041 there; Android AudioFlinger continues to use guest IDs.
    need(peer.get('pid') == hal_pid and peer.get('uid') == hal_uid and peer.get('gid') == hal_gid
        and peer.get('expected_cgroup') == hal_cgroup and peer.get('identity') == 'SO_PEERPIDFD',
         'SO_PEERPIDFD_MUST_BE_CURRENT_AUDIO_APEX_HAL_PROCESS')
    connection = rows[start + 1:]
    closed = 'capture_closed' if role == 'input' else 'stream_closed'
    need(not any(r['value'].get('event') == closed and r['monotonic_us'] * 1000 < begin_ns
        for r in connection), 'OLD_CLOSED_AUDIO_CONNECTION_CANNOT_BE_ADOPTED')
    ready = [r for r in connection if r['value'].get('event') == 'stream_ready']
    need(len(ready) == 1, 'ONE_CURRENT_PULSE_STREAM_READY')
    info = ready[0]['value']
    if role == 'input':
        need(info.get('source') == SOURCE_NAME and type(info.get('source_index')) is int
            and info.get('bus_path') == BUS_PATH and info.get('active_port') == INPUT_PORT
            and (info.get('rate'), info.get('channels'), info.get('format')) == (48000, 1, 's16le'),
             'REAL_CONFIGURED_INTERNAL_MIC_SOURCE_REQUIRED')
    else:
        # Output's stream_ready only carries its actual index, not its sink.
        # The caller must join it to the current pactl sink-input and exact
        # PCI/speaker snapshot; never fabricate a sink field in this event.
        need(type(info.get('pulse_stream_index')) is int and info['pulse_stream_index'] >= 0
            and (info.get('rate'), info.get('channels'), info.get('format')) == (48000, 2, 's16le'),
             'REAL_OUTPUT_STREAM_GEOMETRY_REQUIRED')
    event = 'capture_ack' if role == 'input' else 'ack'
    field = 'captured_frames_acked' if role == 'input' else 'ack_sent_frames'
    acknowledgements = [r for r in connection if r['value'].get('event') == event]
    counts = [r['value'].get(field) for r in acknowledgements]
    need(counts and all(type(x) is int and x >= 0 for x in counts)
        and all(a <= b for a, b in zip(counts, counts[1:])), 'EXACT_MONOTONIC_PROTOCOL_FRAME_COUNTERS')
    before = [r for r in acknowledgements if r['monotonic_us'] * 1000 < begin_ns]
    during = [r for r in acknowledgements if begin_ns <= r['monotonic_us'] * 1000 <= end_ns]
    old_count = before[-1]['value'][field] if before else 0
    need(during and during[-1]['value'][field] > old_count, 'NO_ACKNOWLEDGED_AUDIO_IN_THIS_BUSINESS_WINDOW')
    return {'peer': peer, 'peer_cursor': rows[start]['cursor'], 'stream_ready': info,
        'first_window_cursor': during[0]['cursor'], 'last_window_cursor': during[-1]['cursor'],
        'frames_before': old_count, 'frames_after': during[-1]['value'][field],
        'acknowledged_frames_in_window': during[-1]['value'][field] - old_count,
        'begin_ns': begin_ns, 'end_ns': end_ns, 'physical_audio_qualified': False, 'runtime_qualified': False}
