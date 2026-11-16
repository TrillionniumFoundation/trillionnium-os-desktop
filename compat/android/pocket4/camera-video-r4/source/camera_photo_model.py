"""Preserved Camera photo parsers and checks; no historical runtime constructor.

Only explicit caller-provided current session inputs are consumed. Import does
not discover Main, open a device, load a transaction, or dispatch a command.
"""
import hashlib
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = 'com.android.camera2'
COMPONENT = PACKAGE + '/com.android.camera.CameraLauncher'
MAX_PHOTO = 32 * 1024 * 1024
MEDIA_FIELDS = ('_id', '_data', '_display_name', 'mime_type', '_size', 'width',
                'height', 'orientation', 'date_added', 'is_pending', 'owner_package_name')

class Stop(RuntimeError):
    pass

def require(value, reason):
    if not value:
        raise Stop(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def parse_stacks(raw):
    """The proven task_scope parser, with no historical epoch or process IDs."""
    roots, tasks = {}, set()
    for block in re.split(r'(?=^RootTask id=)', raw, flags=re.M):
        if not block.startswith('RootTask id='):
            continue
        head = block.splitlines()[0]
        rid = int(re.search(r'^RootTask id=(\d+)\b', head)[1])
        display = int(re.search(r'\bdisplayId=(\d+)\b', head)[1])
        user = int(re.search(r'\buserId=(\d+)\b', head)[1])
        children = []
        for line in block.splitlines():
            match = re.match(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b', line)
            require(not re.match(r'\s*taskId=', line) or match is not None, 'UNPARSED_TASK_LINE')
            if match:
                tid = int(match[1])
                require(tid not in tasks, 'DUPLICATE_TASK')
                tasks.add(tid)
                children.append({'id': tid, 'component': match[2], 'user': int(match[3])})
        require(rid not in roots, 'DUPLICATE_ROOT')
        roots[rid] = {'display': display, 'user': user,
                      'freeform': 'mWindowingMode=freeform' in block, 'children': children}
    require(bool(roots) and bool(tasks), 'UNRECOGNIZED_STACK_LIST')
    return roots, tasks

def exact_leaf(roots, task):
    root = roots.get(task)
    return bool(root and root['display'] == 0 and root['user'] == 0 and root['freeform']
                and len(root['children']) == 1 and root['children'][0]['id'] == task
                and root['children'][0]['user'] == 0
                and root['children'][0]['component'].split('/')[0] == PACKAGE)

def native_task(value, host_pid):
    require(type(value) is dict and value.get('ok') is True
            and value.get('host_pid') == host_pid and value.get('state') == 'running'
            and value.get('outcome_unknown') is not True, 'NATIVE_LAUNCH_RECEIPT_UNCERTAIN')
    match = re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)',
                         value.get('launch', ''))
    require(match is not None and int(match[3]) == 0, 'NATIVE_TASK_ID_INVALID')
    return int(match[4])

def content_rows(raw, fields):
    text = raw.decode('utf-8', 'strict').strip()
    if text == 'No result found.':
        return []
    require(bool(text), 'MEDIASTORE_RESPONSE_EMPTY')
    rows = []
    for line in text.splitlines():
        match = re.fullmatch(r'Row: (\d+) (.*)', line)
        require(match is not None and int(match[1]) == len(rows), 'MEDIASTORE_ROW_FORMAT_UNKNOWN')
        parts = re.split(r', (?=[A-Za-z_][A-Za-z0-9_]*=)', match[2])
        pairs = [part.split('=', 1) for part in parts]
        require(all(len(p) == 2 for p in pairs) and len(pairs) == len(fields), 'MEDIASTORE_COLUMNS_UNKNOWN')
        row = dict(pairs)
        require(set(row) == set(fields) and len(row) == len(pairs), 'MEDIASTORE_COLUMNS_DIFFER')
        rows.append(row)
    return rows

def media_ids(raw):
    rows = content_rows(raw, ('_id',))
    require(all(re.fullmatch(r'[1-9]\d*', row['_id']) for row in rows), 'MEDIASTORE_ID_INVALID')
    ids = {int(row['_id']) for row in rows}
    require(len(ids) == len(rows), 'MEDIASTORE_DUPLICATE_ID')
    return ids

def new_image_id(before, after):
    require(before <= after, 'PREEXISTING_MEDIASTORE_ROW_DISAPPEARED')
    added = after - before
    require(len(added) <= 1, 'MORE_THAN_ONE_NEW_IMAGE')
    return next(iter(added)) if added else None

def image_record(raw, image_id, shutter_seconds):
    rows = content_rows(raw, MEDIA_FIELDS)
    require(len(rows) == 1, 'NEW_IMAGE_ROW_MISSING_OR_AMBIGUOUS')
    row = rows[0]
    for key in ('_id', 'date_added', 'is_pending'):
        require(re.fullmatch(r'\d+', row[key]) is not None, 'NEW_IMAGE_NUMERIC_FIELD_INVALID')
        row[key] = int(row[key])
    require(row['_id'] == image_id and row['owner_package_name'] == PACKAGE, 'NEW_IMAGE_OWNER_UNVERIFIED')
    require(row['date_added'] >= int(shutter_seconds) - 3, 'NEW_IMAGE_PREDATES_SHUTTER')
    require(re.fullmatch(r'/storage/emulated/0/DCIM/Camera/[^/\x00\r\n]+\.(?:jpg|jpeg)', row['_data'], re.I)
            is not None, 'NEW_IMAGE_PATH_OUTSIDE_CAMERA')
    require(Path(row['_data']).name == row['_display_name'], 'NEW_IMAGE_FILENAME_DIFFERS')
    require(row['mime_type'] == 'image/jpeg', 'NEW_IMAGE_NOT_JPEG')
    if row['is_pending'] != 0 or row['_size'] in ('0', 'NULL', 'null'):
        return None
    for key in ('_size', 'width', 'height', 'orientation'):
        require(re.fullmatch(r'\d+', row[key]) is not None, 'NEW_IMAGE_NUMERIC_FIELD_INVALID')
        row[key] = int(row[key])
    require(0 < row['_size'] <= MAX_PHOTO and 0 < row['width'] <= 8192
            and 0 < row['height'] <= 8192 and row['orientation'] in (0, 90, 180, 270), 'NEW_IMAGE_METADATA_INVALID')
    return row

def decoded_photo(raw, row):
    from PIL import Image
    require(len(raw) == row['_size'] and len(raw) <= MAX_PHOTO, 'NEW_IMAGE_FILE_SIZE_DIFFERS')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            require(image.format == 'JPEG' and 0 < image.width * image.height <= 32_000_000,
                    'NEW_IMAGE_FORMAT_OR_DIMENSIONS_INVALID')
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()  # Decode pixels; a JPEG header alone is insufficient.
            dimensions = [image.width, image.height]
            expected = [row['width'], row['height']]
            require(dimensions == expected or
                    (row['orientation'] in (90, 270) and dimensions[::-1] == expected), 'NEW_IMAGE_DIMENSIONS_DIFFER')
    except Stop:
        raise
    except Exception as exc:
        raise Stop('NEW_IMAGE_DECODE_FAILED') from exc
    return {'sha256': sha(raw), 'bytes': len(raw), 'dimensions': dimensions, 'fully_decoded': True}

def journal_records(raw):
    lines = raw.decode('utf-8', 'strict').splitlines()
    require(len(lines) < 1024, 'PROVIDER_JOURNAL_LIMIT_REACHED')
    rows = [json.loads(line) for line in lines if line.strip()]
    require(all(isinstance(r, dict) and isinstance(r.get('__CURSOR'), str) for r in rows),
            'PROVIDER_JOURNAL_FORMAT_UNKNOWN')
    return rows

def provider_proof(rows):
    """Recognize only the provider's observed JSON event grammar."""
    events = []
    for row in rows:
        message = row.get('MESSAGE')
        require(isinstance(message, str), 'PROVIDER_MESSAGE_FORMAT_UNKNOWN')
        try:
            event = json.loads(message)
        except ValueError:
            continue
        if isinstance(event, dict) and isinstance(event.get('event'), str):
            events.append(event)
    opened = [x for x in events if x['event'] == 'physical_camera_open']
    closed = [x for x in events if x['event'] == 'physical_camera_closed']
    connected, producer_closed = [], []
    for index, event in enumerate(events):
        if event['event'] != 'producer':
            continue
        message = event.get('message', '')
        if match := re.fullmatch(r'Pocket4LiveCamera source_connected session=(\d+) peer_uid=(\d+)', message):
            connected.append((int(match[1]), index))
        if match := re.fullmatch(r'Pocket4LiveCamera source_closed session=(\d+) frames=(\d+)', message):
            producer_closed.append((int(match[1]), int(match[2]), index))
    require(len(opened) == len(closed) == len(connected) == len(producer_closed) == 1,
            'PROVIDER_FRAME_WINDOW_UNVERIFIED')
    require(connected[0][0] == producer_closed[0][0] and producer_closed[0][1] >= 2
            and connected[0][1] < producer_closed[0][2]
            and events.index(opened[0]) < events.index(closed[0]),
            'PRODUCER_DID_NOT_DELIVER_MULTIPLE_FRAMES')
    last = closed[0]
    require(last.get('exit') == 0 and type(last.get('frames')) is int and last['frames'] >= 2,
            'PHYSICAL_CAPTURE_FAILED')
    return {'physical_frames': last['frames'], 'producer_frames': producer_closed[0][1],
            'physical_open_close_pairs': 1, 'producer_open_close_pairs': 1, 'capture_exit': 0}

def exit_events(text):
    events = set()
    require(text.startswith('ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)'),
            'EXIT_INFO_HEADER_UNKNOWN')
    blocks = re.split(r'(?=^\s*ApplicationExitInfo #\d+:)', text, flags=re.M)[1:]
    if not blocks:
        require(re.search(r'^\s*(?:No records\.?|\(nothing\))\s*$', text, re.M) is not None,
                'EXIT_INFO_EMPTY_FORMAT_UNKNOWN')
    for block in blocks:
        fields = {}
        for name, pattern in {
            'timestamp': r'\btimestamp=([^\n]+)', 'pid': r'\bpid=(\d+)',
            'uid': r'\brealUid=(\d+)', 'reason': r'\breason=(\d+)\s*\(',
            'process': r'\bprocess=([^\s]+)',
        }.items():
            matches = re.findall(pattern, block)
            require(len(matches) == 1, 'EXIT_INFO_FIELD_UNKNOWN')
            fields[name] = matches[0].strip()
        events.add(tuple(fields[key] for key in ('timestamp', 'pid', 'uid', 'reason', 'process')))
    return events

def fresh_crashes(before, after, uid, since):
    added = exit_events(after['exits']) - exit_events(before['exits'])
    require(all(int(row[2]) == uid and row[4] == PACKAGE for row in added), 'EXIT_INFO_UID_OR_PACKAGE_DIFFERS')
    fatal_exits = [row for row in added if int(row[3]) in (3, 4, 5, 6, 7)]
    fresh_uid_crash, fresh_events = [], []
    for key, target, limit in [('crash', fresh_uid_crash, 512), ('events', fresh_events, 2048)]:
        timed = []
        for line in after[key].splitlines():
            match = re.match(r'^\s*(\d+\.\d+)\s+', line)
            if match:
                stamp = float(match[1]); timed.append(stamp)
                if stamp >= since and (key == 'crash' or
                        (re.search(r'\bam_(?:crash|anr)\s*:', line) and PACKAGE in line)):
                    target.append(line)
        require(len(timed) < limit or min(timed) <= since, 'CRASH_OBSERVATION_WINDOW_TRUNCATED')
    return {'new_exit_events': len(added), 'new_crash_or_anr_exits': len(fatal_exits),
            'new_uid_crash_lines': len(fresh_uid_crash), 'new_package_crash_anr_events': len(fresh_events),
            'clear': not fatal_exits and not fresh_uid_crash and not fresh_events}

def require_completed_lifecycle(trial):
    # An already-disappeared owned task is safe to leave alone in cleanup, but
    # cannot qualify as a deliberately closed and observed lifecycle phase.
    require(trial.launch_calls == 2 and trial.remove_calls == 2 and trial.shutter_calls == 1
            and not trial.pending_effects, 'TWO_NORMAL_CLOSES_AND_ONE_SHUTTER_NOT_VERIFIED')

def photo_mode_verified(session):
    # CameraActivity.getModeIndex() uses KEY_STARTUP_MODULE_INDEX for the MAIN
    # launcher. Exact source: Keys.java camera.startup_module; SettingsManager
    # default shared preferences stores String; arrays.xml camera_mode_photo=0.
    # Read only this key, never publish the private preferences document.
    path = '/data/user/0/' + PACKAGE + '/shared_prefs/' + PACKAGE + '_preferences.xml'
    session.guard()
    raw, _ = session.target.read_file(path, 128 * 1024)
    session.guard()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise Stop('CAMERA_MODE_PREFERENCES_INVALID') from exc
    require(root.tag == 'map', 'CAMERA_MODE_PREFERENCES_INVALID')
    matches = [node for node in root if node.get('name') == 'camera.startup_module']
    require(len(matches) == 1 and matches[0].tag == 'string' and matches[0].text == '0',
            'PHOTO_MODE_NOT_VERIFIED_NO_SHUTTER')
    return {'camera_startup_module': '0', 'source_mode_photo_integer': 0,
            'preferences_sha256': sha(raw), 'preference_writes': 0}
