#!/usr/bin/python3 -I
"""Release08 Camera preview, one new photo, close/reopen persistence acceptance.

Inert unless --execute is supplied. Import the separately reviewed, SHA-pinned
CameraSession; never rediscover Main or touch the camera provider's owner lock.
Raw observations and images remain in a new private directory, outside Git.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import stat
import time
import types
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = 'com.android.camera2'
COMPONENT = PACKAGE + '/com.android.camera.CameraLauncher'
APK_SHA = '0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e'
APK_BYTES = 11892407
TRANSACTION_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
IMAGE_URI = 'content://media/external/images/media'
OWNER_LOCK = Path('/run/pocket4-live-camera/owner.lock')
PROVIDER_UNIT = 'pocket4-live-camera.service'
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


def write_new(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'bytes': len(raw), 'sha256': sha(raw)}


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
    # Images inserted without RELATIVE_PATH use MediaProvider's Pictures default.
    # Ownership, one new row, shutter time, exact filename and decode gates remain.
    require(re.fullmatch(r'/storage/emulated/0/(?:DCIM/Camera|Pictures)/[^/\x00\r\n]+\.(?:jpg|jpeg)', row['_data'], re.I)
            is not None, 'NEW_IMAGE_PATH_OUTSIDE_SUPPORTED_IMAGE_DIRECTORIES')
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


def provider_owner():
    """Read lock identity only. Never flock, open for write, or signal its owner."""
    item = OWNER_LOCK.stat()
    owners = []
    for line in Path('/proc/locks').read_text().splitlines():
        match = re.fullmatch(r'\d+:\s+FLOCK\s+ADVISORY\s+WRITE (\d+) ([0-9a-f]+):([0-9a-f]+):(\d+) 0 EOF', line)
        if match and (int(match[2], 16), int(match[3], 16), int(match[4])) == (
                os.major(item.st_dev), os.minor(item.st_dev), item.st_ino):
            owners.append(int(match[1]))
    require(len(owners) == 1 and owners[0] > 1, 'PROVIDER_OWNER_UNKNOWN')
    pid = owners[0]
    raw = Path('/proc/%d/stat' % pid).read_text()
    return {'device': item.st_dev, 'inode': item.st_ino, 'pid': pid,
            'start_ticks': int(raw[raw.rfind(')') + 2:].split()[19])}


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


class Trial:
    def __init__(self, session, transaction, output):
        self.s, self.tx, self.output = session, transaction, output
        self.owned = None
        self.sequence = 0
        self.shutter_calls = 0
        self.launch_calls = 0
        self.remove_calls = 0
        self.uncertain = False
        self.pending_effects = set()

    def record(self, stem, value):
        self.sequence += 1
        return write_new(self.output / ('%03d-' % self.sequence + stem + '.json'), value)

    def stacks(self, stem):
        raw = self.s.android(['/system/bin/cmd', 'activity', 'stack', 'list'], timeout=15).decode()
        parsed = parse_stacks(raw)
        self.record(stem, {'raw_stacks': raw, 'task_ids': sorted(parsed[1]), 'at': now()})
        return parsed

    def launch(self, phase):
        before_roots, before_tasks = self.stacks(phase + '-before-launch')
        require(not any(child['component'].split('/')[0] == PACKAGE
                        for root in before_roots.values() for child in root['children']), 'PREEXISTING_CAMERA_TASK_PRESERVED')
        _, _, status = self.s.discover_fixed()
        command = [*self.tx.ALEX_PREFIX, 'launch', PACKAGE, '--component', COMPONENT, '--json']
        self.record(phase + '-launch-intent', {'argv': command, 'automatic_retry': False})
        self.launch_calls += 1
        self.uncertain = True
        self.pending_effects.add(phase + '-launch')
        result = self.s.run_host(phase + '-launch', command, 45)
        require(result['rc'] == 0 and not result['timed_out'] and result['joined'], 'LAUNCH_OUTCOME_UNKNOWN')
        task = native_task(json.loads(result['stdout']), status['host_pid'])
        require(task not in before_tasks and task not in before_roots, 'LAUNCH_DID_NOT_CREATE_OWN_TASK')
        # Ownership comes from the successful native receipt + prelaunch absence.
        self.owned = (task, before_tasks, phase)
        roots, tasks = self.stacks(phase + '-after-launch')
        require(exact_leaf(roots, task) and tasks == before_tasks | {task}, 'LAUNCH_TASK_TOPOLOGY_CHANGED')
        self.uncertain = False
        self.pending_effects.discard(phase + '-launch')
        return task

    def close(self):
        if self.owned is None:
            return
        task, preserved, phase = self.owned
        roots, tasks = self.stacks(phase + '-before-close')
        require(tasks - {task} == preserved, 'OTHER_TASK_SET_CHANGED')
        if task not in tasks and task not in roots:
            self.owned = None
            return
        require(exact_leaf(roots, task), 'OWNED_TASK_SCOPE_CHANGED_NO_REMOVE')
        command = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(task)]
        self.record(phase + '-remove-intent', {'argv': command, 'automatic_retry': False, 'prelaunch_absent': True})
        self.remove_calls += 1
        self.uncertain = True
        self.pending_effects.add(phase + '-remove')
        # Never replay this command even if transport or readback is uncertain.
        self.owned = None
        self.s.android(command, timeout=15)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            time.sleep(.25)
            roots, tasks = self.stacks(phase + '-close-readback')
            require(tasks - {task} == preserved, 'OTHER_TASK_SET_CHANGED')
            if task not in tasks and task not in roots:
                self.uncertain = False
                self.pending_effects.discard(phase + '-remove')
                self.record(phase + '-closed', {'own_task_removed': True, 'other_tasks_preserved': True})
                return
            root = roots.get(task)
            shrinking = bool(root and task not in tasks and root['display'] == 0 and root['user'] == 0
                             and root['freeform'] and root['children'] == [])
            require(exact_leaf(roots, task) or shrinking, 'OWNED_TASK_SCOPE_CHANGED_DURING_CLOSE')
        raise Stop('TASK_CLOSE_READBACK_UNCERTAIN')

    def ui(self, stem, request):
        require(request.get('package') == PACKAGE and request.get('op') in ('observe', 'dump', 'click'), 'UI_SCOPE_INVALID')
        if request['op'] == 'click':
            require(request.get('selector', {}).get('id') == PACKAGE + ':id/shutter_button'
                    and request.get('method') == 'accessibility' and self.shutter_calls == 0, 'ONLY_ONE_SHUTTER_ALLOWED')
            require(self.owned is not None, 'SHUTTER_REQUIRES_OWNED_TASK')
            task, preserved, _ = self.owned
            roots, tasks = self.stacks('before-shutter-task')
            require(exact_leaf(roots, task) and tasks == preserved | {task}, 'SHUTTER_TASK_SCOPE_CHANGED')
            self.record(stem + '-intent', {'request': request, 'automatic_retry': False})
            self.shutter_calls += 1
            self.uncertain = True
            self.pending_effects.add('shutter')
        self.s.guard()
        value = self.s.helper.dispatch(request)
        self.s.guard()
        require(isinstance(value, dict), 'UI_RESPONSE_INVALID')
        png = value.pop('screenshot_png_base64', None)
        if png is not None:
            write_new(self.output / (stem + '.png'), base64.b64decode(png, validate=True))
        self.record(stem, value)
        require(value.get('ok') is True and value.get('outcome_unknown') is not True, 'UI_RESPONSE_UNCERTAIN')
        if request['op'] == 'click':
            self.uncertain = False
            self.pending_effects.discard('shutter')
        return value

    def ready(self, value):
        native = value.get('native', value)
        require(native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True,
                'CAMERA_TREE_UNVERIFIED')
        matches = [node for node in native.get('nodes', [])
                   if node.get('package') == PACKAGE and node.get('resource-id') == PACKAGE + ':id/shutter_button'
                   and node.get('visible') is True and node.get('enabled') is True and node.get('clickable') is True]
        require(len(matches) == 1, 'ONE_READY_SHUTTER_REQUIRED')
        return matches[0]

    def preview(self, phase):
        # A real preview may precede the App's ready-for-capture callback. Only
        # read the existing owned window while its one visible shutter is
        # explicitly disabled; never click a disabled shutter or relaunch here.
        started = time.monotonic()
        for number in range(10):
            require(time.monotonic() - started < 15, 'PREVIEW_READINESS_DEADLINE')
            require(self.owned is not None, 'PREVIEW_REQUIRES_OWNED_TASK')
            task, preserved, _ = self.owned
            roots, tasks = self.stacks(phase + '-preview-owned-' + str(number))
            require(exact_leaf(roots, task) and tasks == preserved | {task},
                    'PREVIEW_TASK_SCOPE_CHANGED')
            value = self.ui(phase + '-preview-' + str(number), {'op': 'observe',
                'package': PACKAGE, 'display': 0, 'accessibility_mode': 'none', 'with_png': True})
            require(time.monotonic() - started < 15, 'PREVIEW_READINESS_DEADLINE')
            native = value.get('native', value)
            require(native.get('ok') is True and
                    native.get('accessibility_mode_restoration_verified') is True,
                    'CAMERA_TREE_UNVERIFIED')
            require(value['screenshot']['scope']['package'] == PACKAGE,
                    'CAMERA_PREVIEW_SCOPE_CHANGED')
            controls = [node for node in native.get('nodes', [])
                if node.get('package') == PACKAGE and node.get('visible') is True
                and node.get('resource-id') == PACKAGE + ':id/shutter_button']
            require(len(controls) == 1 and controls[0].get('clickable') is True,
                    'ONE_VISIBLE_SHUTTER_REQUIRED_NO_WAIT')
            if controls[0].get('enabled') is True:
                self.ready(value)
                return {'screenshot_scope_sha256': value['screenshot']['scope_sha256'],
                        'shutter_ready': True, 'readiness_observations': number + 1,
                        'readiness_elapsed_seconds': round(time.monotonic() - started, 3),
                        'readiness_inputs': 0}
            require(controls[0].get('enabled') is False, 'SHUTTER_ENABLED_STATE_UNKNOWN')
            if number < 9 and time.monotonic() - started + .4 < 15:
                time.sleep(.4)
        raise Stop('SHUTTER_REMAINED_DISABLED_DURING_BOUNDED_OBSERVATION')

    def ids(self, stem):
        raw = self.s.android(['/system/bin/content', 'query', '--user', '0', '--uri', IMAGE_URI,
                              '--projection', '_id'], timeout=15)
        require(len(raw) <= 4 * 1024 * 1024, 'MEDIASTORE_ID_SET_TOO_LARGE')
        ids = media_ids(raw)
        self.record(stem, {'image_ids': sorted(ids)})
        return ids

    def row(self, image_id, shutter_seconds):
        raw = self.s.android(['/system/bin/content', 'query', '--user', '0', '--uri', IMAGE_URI + '/' + str(image_id),
                              '--projection', ':'.join(MEDIA_FIELDS)], timeout=15)
        self.record('new-photo-row', {'raw': raw.decode('utf-8', 'strict')})
        return image_record(raw, image_id, shutter_seconds)

    def read_photo(self, row, name, save=False):
        self.s.guard()
        data, metadata = self.s.target.read_file(row['_data'], MAX_PHOTO)
        self.s.guard()
        proof = decoded_photo(data, row)
        self.record(name, {'file_metadata': metadata, **proof})
        if save:
            write_new(self.output / 'new-test-photo.jpg', data)
        return proof

    def diagnostics(self, stem, uid):
        clock = self.s.android(['/system/bin/date', '+%s'], timeout=8).decode().strip()
        require(clock.isdigit() and abs(time.time() - int(clock)) <= 3, 'GUEST_CLOCK_UNVERIFIED')
        commands = {
            'exits': ['/system/bin/dumpsys', 'activity', 'exit-info', PACKAGE],
            'events': ['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'],
            'crash': ['/system/bin/logcat', '--uid=' + str(uid), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'],
        }
        result = {'guest_seconds': int(clock)}
        for key, command in commands.items():
            raw = self.s.android(command, timeout=15)
            require(len(raw) <= 4 * 1024 * 1024, 'DIAGNOSTIC_LIMIT_REACHED')
            result[key] = raw.decode('utf-8', 'strict')
        self.record(stem, result)
        return result

    def journal(self, cursor=None):
        argv = ['/usr/bin/journalctl', '-u', PROVIDER_UNIT, '--no-pager', '-o', 'json']
        argv += ['--after-cursor', cursor, '-n', '1024'] if cursor else ['-n', '1']
        result = self.s.run_host('provider-journal', argv, 15)
        require(result['rc'] == 0 and not result['timed_out'], 'PROVIDER_JOURNAL_UNAVAILABLE')
        rows = journal_records(result['stdout'])
        if cursor is None:
            require(len(rows) == 1, 'PROVIDER_CURSOR_UNAVAILABLE')
            return rows[0]['__CURSOR']
        self.record('provider-window', {'rows': rows})
        return rows

    def provider_after_close(self, cursor):
        deadline = time.monotonic() + 5
        while True:
            rows = self.journal(cursor)
            try:
                return provider_proof(rows)
            except Stop as exc:
                if str(exc) != 'PROVIDER_FRAME_WINDOW_UNVERIFIED' or time.monotonic() >= deadline:
                    raise
                time.sleep(.25)


def load_transaction(path, expected_sha):
    raw = path.read_bytes()
    require(expected_sha == TRANSACTION_SHA and sha(raw) == expected_sha,
            'TRANSACTION_SOURCE_HASH_CHANGED')
    module = types.ModuleType('camera_acceptance_held_transaction')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    require(module.NEW_SHA == APK_SHA and module.PACKAGE == PACKAGE, 'TRANSACTION_CANDIDATE_DIFFERS')
    return module


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


def execute(args, transaction):
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    require(stat.S_IMODE(output.stat().st_mode) == 0o700, 'PRIVATE_OUTPUT_MODE_REQUIRED')
    summary = {'schema': 'pocket4-camera-release08-acceptance-v1', 'started_utc': now(),
               'apk_sha256': APK_SHA, 'success': False, 'production_ready': False,
               'visual_review_required': True, 'images_published': False,
               'prior_photos_modified_or_deleted_by_script': False, 'automatic_retry': False}
    trial = None
    try:
        with transaction.ui_lock(), transaction.CameraSession(output / 'held-main') as session:
            trial = Trial(session, transaction, output)
            before = session.snapshot('acceptance-before')
            require(before['apk']['sha256'] == APK_SHA and before['apk']['bytes'] == APK_BYTES,
                    'RELEASE08_NOT_CURRENTLY_INSTALLED')
            uid = before['identity']['uid']
            baseline = trial.diagnostics('diagnostics-before', uid)
            exit_events(baseline['exits'])
            trial.record('photo-mode-before-launch', photo_mode_verified(session))
            owner = provider_owner()
            ids_before = trial.ids('media-before')
            initial_tasks = trial.stacks('all-tasks-before')[1]
            summary['epoch_sha256'] = session.epoch_sha256
            try:
                cursor = trial.journal()
                trial.launch('open')
                trial.record('photo-mode-after-launch', photo_mode_verified(session))
                summary['first_preview'] = trial.preview('open')
                ready = trial.ui('before-shutter', {'op': 'dump', 'package': PACKAGE, 'display': 0})
                trial.ready(ready)
                trial.record('photo-mode-before-shutter', photo_mode_verified(session))
                shutter_seconds = time.time()
                trial.ui('single-shutter', {'op': 'click', 'package': PACKAGE, 'display': 0,
                         'method': 'accessibility', 'selector': {'id': PACKAGE + ':id/shutter_button',
                                                              'enabled': True, 'clickable': True}})
                deadline = time.monotonic() + 25
                row = None
                while time.monotonic() < deadline:
                    image_id = new_image_id(ids_before, trial.ids('media-after-shutter'))
                    row = trial.row(image_id, shutter_seconds) if image_id is not None else None
                    if row is not None:
                        break
                    time.sleep(.4)
                require(row is not None, 'ONE_NEW_PHOTO_NOT_PERSISTED')
                photo = trial.read_photo(row, 'new-photo-decoded', save=True)
                trial.close()
                summary['first_provider'] = trial.provider_after_close(cursor)
                require(provider_owner() == owner, 'PROVIDER_OWNER_CHANGED')
                require(trial.row(image_id, shutter_seconds) == row, 'PHOTO_ROW_CHANGED_AFTER_CLOSE')
                require(trial.read_photo(row, 'photo-after-close') == photo, 'PHOTO_BYTES_CHANGED_AFTER_CLOSE')
                cursor = trial.journal()
                trial.launch('reopen')
                trial.record('photo-mode-after-reopen', photo_mode_verified(session))
                summary['reopened_preview'] = trial.preview('reopen')
                require(trial.row(image_id, shutter_seconds) == row, 'PHOTO_ROW_CHANGED_AFTER_REOPEN')
                require(trial.read_photo(row, 'photo-after-reopen') == photo, 'PHOTO_BYTES_CHANGED_AFTER_REOPEN')
                trial.close()
                summary['reopened_provider'] = trial.provider_after_close(cursor)
                require(provider_owner() == owner, 'PROVIDER_OWNER_CHANGED')
                require(trial.ids('media-final') == ids_before | {image_id}, 'FINAL_MEDIASTORE_DELTA_DIFFERS')
                require(trial.stacks('all-tasks-final')[1] == initial_tasks, 'OTHER_TASKS_NOT_PRESERVED')
                after_diag = trial.diagnostics('diagnostics-after', uid)
                summary['crash_observation'] = fresh_crashes(baseline, after_diag, uid, baseline['guest_seconds'])
                require(summary['crash_observation']['clear'], 'NEW_CAMERA_CRASH_OR_ANR')
                after = session.snapshot('acceptance-after')
                require(after == before, 'CAMERA_APK_OR_DATA_IDENTITY_CHANGED')
                session.guard()
                require_completed_lifecycle(trial)
                summary.update(success=True, photo=photo, one_new_image=True,
                               photo_persisted_after_close=True, photo_persisted_after_reopen=True,
                               current_main_preserved=True, other_tasks_preserved=True,
                               installed_apk_and_data_identity_preserved=True,
                               provider_owner_preserved=True)
            finally:
                if trial.owned is not None:
                    try:
                        trial.close()
                    except Exception as exc:
                        summary['success'] = False
                        summary['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)[:160]
    except Exception as exc:
        summary.update(success=False, error_type=type(exc).__name__, error=str(exc)[:200])
    finally:
        if trial is not None:
            summary.update(native_launch_calls=trial.launch_calls, shutter_calls=trial.shutter_calls,
                           own_task_remove_calls=trial.remove_calls, outcome_unknown=bool(trial.pending_effects))
        summary['finished_utc'] = now()
        write_new(output / 'public-summary.json', summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary['success'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--transaction', type=Path)
    parser.add_argument('--transaction-sha', default=TRANSACTION_SHA)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'execute': False, 'ui_actions': 0, 'apk_sha256': APK_SHA,
                          'planned_native_launches': 2, 'maximum_shutter_clicks': 1,
                          'photo_mode_precondition': 'unchanged current startup mode string 0',
                          'production_ready': False}, indent=2))
        return 0
    require(args.transaction and args.transaction_sha and args.output, 'EXPLICIT_INPUTS_REQUIRED')
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    os.umask(0o077)
    transaction = load_transaction(args.transaction.resolve(), args.transaction_sha)
    return execute(args, transaction)


if __name__ == '__main__':
    raise SystemExit(main())
