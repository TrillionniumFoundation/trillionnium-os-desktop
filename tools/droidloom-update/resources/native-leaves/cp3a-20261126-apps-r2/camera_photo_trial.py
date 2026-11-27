"""Preserved photo-only state machine, requiring explicit fresh adapters.

The Session and evidence adapter are injected by the new typed runtime. This
module has no default session, legacy loader, execution entry or device access.
"""
import base64
import json
import time

PACKAGE = 'com.android.camera2'
COMPONENT = PACKAGE + '/com.android.camera.CameraLauncher'
IMAGE_URI = 'content://media/external/images/media'
PROVIDER_UNIT = 'pocket4-live-camera.service'
MAX_PHOTO = 32 * 1024 * 1024
MEDIA_FIELDS = ('_id', '_data', '_display_name', 'mime_type', '_size', 'width',
                'height', 'orientation', 'date_added', 'is_pending', 'owner_package_name')


def make_trial(model, evidence):
    "Bind only previously source-admitted pure helpers and fresh private evidence."
    require = model.require
    now = model.now
    parse_stacks = model.parse_stacks
    exact_leaf = model.exact_leaf
    native_task = model.native_task
    media_ids = model.media_ids
    image_record = model.image_record
    decoded_photo = model.decoded_photo
    journal_records = model.journal_records
    provider_proof = model.provider_proof
    Stop = model.Stop
    write_new = evidence.write_new

    class CameraPhotoTrial:
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
            self.s.flow.bound.commands.native_channel_module().ComparisonChannel().observe_running_engine()
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
            value = self.ui(phase + '-preview', {'op': 'observe', 'package': PACKAGE,
                            'display': 0, 'accessibility_mode': 'none', 'with_png': True})
            self.ready(value)
            require(value['screenshot']['scope']['package'] == PACKAGE, 'CAMERA_PREVIEW_SCOPE_CHANGED')
            return {'screenshot_scope_sha256': value['screenshot']['scope_sha256'], 'shutter_ready': True}
    
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

    return CameraPhotoTrial
