#!/usr/bin/python3 -I
"""Local exact-source controls. No Main, Android, device or legacy entry runs."""
import argparse
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import time
import types

BASE = Path(__file__).resolve().parent
PACKAGE = 'com.android.camera2'


def need(value, reason):
    if not value:
        raise AssertionError(reason)


def ref(path):
    path = Path(path); raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(path, value):
    path = Path(path)
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    with path.open('xb') as handle:
        handle.write(raw)
    return ref(path)


def load(name):
    path = BASE / 'candidate' / name; raw = path.read_bytes()
    module = types.ModuleType('camera_control_' + path.stem); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def rejection(invoke, expected):
    try:
        invoke()
    except BaseException as error:
        need(expected in str(error), ('UNEXPECTED_REJECTION', type(error).__name__, str(error), expected))
        return {'type': type(error).__name__, 'message': str(error)}
    raise AssertionError('EXPECTED_REJECTION:' + expected)


def source_equivalence(modules, root):
    original = ast.parse((BASE / 'originals/diagnostics_source.py').read_bytes())
    old_functions = {x.name: x for x in original.body if isinstance(x, ast.FunctionDef)}
    model = ast.parse((BASE / 'candidate/camera_photo_model.py').read_bytes())
    checked = []
    for item in model.body:
        if isinstance(item, ast.FunctionDef):
            need(ast.dump(item) == ast.dump(old_functions[item.name]), 'ORIGINAL_PHOTO_FUNCTION_CHANGED:' + item.name)
            checked.append(item.name)
    old_class = next(x for x in original.body if isinstance(x, ast.ClassDef) and x.name == 'Trial')
    old_methods = {x.name: x for x in old_class.body if isinstance(x, ast.FunctionDef)}
    trial = ast.parse((BASE / 'candidate/camera_photo_trial.py').read_bytes())
    new_class = next(x for x in ast.walk(trial) if isinstance(x, ast.ClassDef) and x.name == 'CameraPhotoTrial')
    methods = []
    for item in new_class.body:
        if isinstance(item, ast.FunctionDef):
            need(ast.dump(item) == ast.dump(old_methods[item.name]), 'ORIGINAL_PHOTO_METHOD_CHANGED:' + item.name)
            methods.append(item.name)
    need(len(checked) == 18 and len(methods) == 14, 'COMPLETE_ORIGINAL_PHOTO_LOGIC')
    return {'passed': True, 'functions': checked, 'methods': methods,
            'original': ref(BASE / 'originals/diagnostics_source.py'), 'old_constructor_or_entry_called': False}


def trial_factory(modules, root, helper=None):
    model = modules['camera_photo_model.py']; records = []
    def record(path, value):
        record_ref = write(path, value); records.append(record_ref); return record_ref
    evidence = types.SimpleNamespace(write_new=record)
    session = types.SimpleNamespace(guard=lambda **kw: {'fixture_only': True}, helper=helper)
    cls = modules['camera_photo_trial.py'].make_trial(model, evidence)
    return cls(session, evidence, root), session, records


def historical_readiness(modules, root):
    trial, _, _ = trial_factory(modules, root)
    rows = []
    for path in sorted((BASE / 'originals/release08').rglob('*preview*.json')):
        value = json.loads(path.read_bytes())
        rows.append({'input': ref(path), 'rejection': rejection(lambda: trial.ready(value), 'ONE_READY_SHUTTER_REQUIRED')})
    need(len(rows) == 3, 'THREE_REAL_HISTORICAL_UI_FAILURES')
    ready = {'native': {'ok': True, 'accessibility_mode_restoration_verified': True, 'nodes': [{
        'package': PACKAGE, 'resource-id': PACKAGE + ':id/shutter_button', 'visible': True,
        'enabled': True, 'clickable': True}]}}
    need(trial.ready(ready) == ready['native']['nodes'][0], 'EXPLICIT_SYNTHETIC_READY_FIXTURE')
    duplicate = copy.deepcopy(ready); duplicate['native']['nodes'] *= 2
    rows.append({'fixture': 'two_ready_shutters', 'rejection': rejection(lambda: trial.ready(duplicate), 'ONE_READY_SHUTTER_REQUIRED')})
    return {'passed': True, 'rows': rows, 'old_epoch_is_only_parser_input': True, 'real_UI_actions': 0}


def media_and_pixels(modules, root):
    m = modules['camera_photo_model.py']
    from PIL import Image
    pixels = Image.new('RGB', (40, 30))
    pixels.putdata([(x * 6, y * 8, (x * 7 + y * 11) % 256) for y in range(30) for x in range(40)])
    output = io.BytesIO(); pixels.save(output, format='JPEG'); pixels.close(); raw = output.getvalue()
    row = {'_id': 43, '_data': '/storage/emulated/0/DCIM/Camera/fixture.jpg', '_display_name': 'fixture.jpg',
        'mime_type': 'image/jpeg', '_size': len(raw), 'width': 40, 'height': 30, 'orientation': 0,
        'date_added': 1000, 'is_pending': 0, 'owner_package_name': PACKAGE}
    def encode(value):
        return ('Row: 0 ' + ', '.join(key + '=' + str(value[key]) for key in m.MEDIA_FIELDS) + '\n').encode()
    decoded = m.image_record(encode(row), 43, 1000.1)
    need(decoded == row and m.new_image_id({9, 42}, {9, 42, 43}) == 43, 'ONE_EXACT_NEW_MEDIASTORE_ROW')
    proof = m.decoded_photo(raw, row)
    need(proof['fully_decoded'] and proof['dimensions'] == [40, 30], 'FULL_JPEG_PIXEL_DECODE')
    negatives = []
    for key, value, message in [('_id', 44, 'OWNER_UNVERIFIED'), ('owner_package_name', 'another.app', 'OWNER_UNVERIFIED'),
        ('date_added', 900, 'PREDATES_SHUTTER'), ('_data', '/storage/emulated/0/DCIM/old.jpg', 'PATH_OUTSIDE_CAMERA'),
        ('_display_name', 'different.jpg', 'FILENAME_DIFFERS'), ('mime_type', 'image/png', 'NOT_JPEG'),
        ('width', 8193, 'METADATA_INVALID')]:
        changed = {**row, key: value}
        negatives.append({'change': key, 'rejection': rejection(lambda: m.image_record(encode(changed), 43, 1000.1), message)})
    need(m.image_record(encode({**row, 'is_pending': 1}), 43, 1000.1) is None, 'PENDING_MEDIA_MUST_NOT_QUALIFY')
    negatives.append({'change': 'two_new_ids', 'rejection': rejection(lambda: m.new_image_id({9}, {9, 42, 43}), 'MORE_THAN_ONE_NEW_IMAGE')})
    negatives.append({'change': 'old_id_missing', 'rejection': rejection(lambda: m.new_image_id({9, 42}, {42, 43}), 'PREEXISTING_MEDIASTORE_ROW_DISAPPEARED')})
    negatives.append({'change': 'truncated_jpeg', 'rejection': rejection(lambda: m.decoded_photo(raw[:100], {**row, '_size': 100}), 'DECODE_FAILED')})
    negatives.append({'change': 'wrong_pixel_dimensions', 'rejection': rejection(lambda: m.decoded_photo(raw, {**row, 'width': 39}), 'DIMENSIONS_DIFFER')})
    return {'passed': True, 'fixture_jpeg': write(root / 'synthetic-pattern.jpg', raw), 'decoded': proof,
        'negative_controls': negatives, 'matching_real_preview_or_business_qualified': False}


def stack_text(camera=True):
    rows = 'RootTask id=9 displayId=0 userId=0 mWindowingMode=freeform\n  taskId=9: fixture.preexisting/.Activity userId=0\n'
    if camera:
        rows += 'RootTask id=17 displayId=0 userId=0 mWindowingMode=freeform\n  taskId=17: com.android.camera2/com.android.camera.CameraLauncher userId=0\n'
    return rows.encode()


def once_unknown_close(modules, root):
    actions = []
    def dispatch(request):
        actions.append(copy.deepcopy(request))
        return {'ok': True, 'performed': 'click', 'outcome_unknown': True, 'post_action_observation_available': False}
    trial, session, records = trial_factory(modules, root, types.SimpleNamespace(dispatch=dispatch))
    trial.launch_calls = 1; trial.owned = (17, {9}, 'open')
    removed = False; removals = []
    def android(argv, timeout):
        nonlocal removed
        if argv == ['/system/bin/cmd', 'activity', 'stack', 'list']:
            return stack_text(not removed)
        need(argv == ['/system/bin/cmd', 'activity', 'stack', 'remove', '17'], 'ONE_FIXTURE_OWNED_REMOVE')
        need(trial.owned is None and trial.pending_effects == {'shutter', 'open-remove'}, 'OWNERSHIP_BURNED_BEFORE_REMOVE')
        removals.append(argv); removed = True; return b''
    session.android = android
    request = {'op': 'click', 'package': PACKAGE, 'display': 0, 'method': 'accessibility',
        'selector': {'id': PACKAGE + ':id/shutter_button', 'enabled': True, 'clickable': True}}
    first = rejection(lambda: trial.ui('fixture-one-shutter', request), 'UI_RESPONSE_UNCERTAIN')
    need(trial.shutter_calls == 1 and trial.pending_effects == {'shutter'}, 'UNKNOWN_SHUTTER_MUST_REMAIN_PENDING')
    second = rejection(lambda: trial.ui('fixture-replay', request), 'ONLY_ONE_SHUTTER_ALLOWED')
    trial.close(); trial.close()
    need(len(actions) == len(removals) == 1 and trial.owned is None and trial.pending_effects == {'shutter'},
        'ONE_INDEPENDENT_NORMAL_CLOSE_MUST_NOT_CLEAR_UNKNOWN_SHUTTER')
    rejection(lambda: modules['camera_photo_model.py'].require_completed_lifecycle(trial), 'TWO_NORMAL_CLOSES_AND_ONE_SHUTTER_NOT_VERIFIED')
    return {'passed': True, 'first_unknown': first, 'replay_rejected': second,
        'actual_original_shutter_calls': trial.shutter_calls, 'actual_original_remove_calls': trial.remove_calls,
        'pending': sorted(trial.pending_effects), 'original_records': records,
        'synthetic_Binder_inputs': True, 'Android_commands': 0}


def unknown_remove(modules, root):
    trial, session, records = trial_factory(modules, root)
    trial.launch_calls = 1; trial.owned = (17, {9}, 'open'); removes = []
    def android(argv, timeout):
        if argv[-1] == 'list':
            return stack_text()
        need(trial.owned is None and trial.pending_effects == {'open-remove'}, 'BURN_REMOVE_AUTHORITY')
        removes.append(argv); raise RuntimeError('FIXTURE_LOST_REMOVE_REPLY')
    session.android = android
    rejection(trial.close, 'FIXTURE_LOST_REMOVE_REPLY'); trial.close()
    need(len(removes) == 1 and trial.remove_calls == 1 and trial.pending_effects == {'open-remove'},
        'UNKNOWN_REMOVE_REPLAYED_OR_PENDING_LOST')
    return {'passed': True, 'remove_calls': len(removes), 'pending': sorted(trial.pending_effects),
        'original_records': records, 'Android_commands': 0}


def second_scope(modules, root):
    outcomes = []
    for mode in ('known_absent', 'remove_unknown', 'still_present', 'other_task_changed'):
        cls = modules['camera_session.py'].Session; s = cls.__new__(cls)
        s.c = types.SimpleNamespace(need=need, NATIVE_PREFIX=['fixture-native-client'])
        s.native_launches = 1; s.scope_index = 0; s.phase_name = 'business'; s.active_api = None
        s.trial = types.SimpleNamespace(owned=None, launch_calls=2, pending_effects={'reopen-launch'})
        s.baseline_roots = {9: {'fixture': True}}; s.baseline_tasks = {9}
        s.last_stacks = (copy.deepcopy(s.baseline_roots), set(s.baseline_tasks))
        if mode == 'still_present':
            s.last_stacks = ({**s.baseline_roots, 17: {}}, {9, 17})
        if mode == 'other_task_changed':
            s.last_stacks = ({**s.baseline_roots, 20: {}}, {9, 20})
        calls = []
        old = types.SimpleNamespace(policy=types.SimpleNamespace(remove_sent=mode != 'remove_unknown'),
            selected_task=lambda: {'task': 17}, close=lambda: calls.append('old_closed'))
        s.flow = old; s.consume_original_intent = lambda *args: calls.append('once_intent')
        def new_flow(index):
            need(index == 1 and calls[-1] == 'old_closed', 'OLD_SCOPE_FDS_MUST_CLOSE_FIRST')
            calls.append('new_scope'); return types.SimpleNamespace(native_launch=lambda: calls.append('new_launch'))
        s.new_flow = new_flow
        argv = s.c.NATIVE_PREFIX + ['launch', PACKAGE, '--component', PACKAGE + '/com.android.camera.CameraLauncher', '--json']
        if mode == 'known_absent':
            s.run_host('reopen-launch', argv, 45)
            need(calls == ['once_intent', 'old_closed', 'new_scope', 'new_launch'] and s.native_launches == 2,
                'EXACT_TWO_FRESH_SCOPE_ORDER')
        else:
            rejection(lambda: s.run_host('reopen-launch', argv, 45), 'FIRST_CAMERA_SCOPE_ACTUALLY_RETIRED_BEFORE_NEW_SCOPE')
            need(calls == ['once_intent'] and s.flow is old and s.native_launches == 1, 'UNSAFE_SECOND_SCOPE_WAS_CREATED')
        outcomes.append({'mode': mode, 'calls': calls})
    return {'passed': True, 'actual_Session_method': True, 'fixture_Binder_state_only': True, 'outcomes': outcomes}


def provider_cycles(modules, root):
    o = modules['camera_observations.py']; m = modules['camera_photo_model.py']
    invocation = '1' * 32; boot = '2' * 32; pid = 12345
    events = [
        {'event': 'physical_camera_open', 'device': str(o.DEVICE), 'capture_pid': 12346},
        {'event': 'producer', 'message': 'Pocket4LiveCamera source_connected session=4 peer_uid=0'},
        {'event': 'live_frames', 'frames': 8, 'age_ms': 15},
        {'event': 'producer', 'message': 'Pocket4LiveCamera source_closed session=4 frames=8'},
        {'event': 'physical_camera_closed', 'frames': 8, 'exit': 0}]
    rows = [{'MESSAGE': json.dumps(event), '_SYSTEMD_INVOCATION_ID': invocation,
        '_BOOT_ID': boot, '_PID': str(pid), '__MONOTONIC_TIMESTAMP': str(1000 + i), '__CURSOR': 'fixture-' + str(i)}
        for i, event in enumerate(events)]
    def raw(values):
        return b'\n'.join(json.dumps(v).encode() for v in values)
    parsed = o.journal_events(raw(rows), invocation, pid, boot)
    cycles = o.physical_cycles(parsed, 999, 1006, expected=1)
    need(len(cycles) == 1 and m.provider_proof(rows)['physical_frames'] == 8, 'BOTH_EXACT_PHYSICAL_AND_ORIGINAL_PRODUCER_PROOFS')
    errors = []
    for field, value, reason in [('_BOOT_ID', '3' * 32, 'boot differs'),
        ('_SYSTEMD_INVOCATION_ID', '4' * 32, 'another service invocation'), ('_PID', '999', 'another manager PID')]:
        changed = copy.deepcopy(rows); changed[0][field] = value
        errors.append(rejection(lambda: o.journal_events(raw(changed), invocation, pid, boot), reason))
    changed = copy.deepcopy(parsed); changed[0]['device'] = '/dev/video99'
    errors.append(rejection(lambda: o.physical_cycles(changed, 999, 1006, 1), 'identity/sequence'))
    changed = [item for item in copy.deepcopy(parsed) if item['event'] != 'live_frames']
    errors.append(rejection(lambda: o.physical_cycles(changed, 999, 1006, 1), 'without live frames'))
    changed = copy.deepcopy(parsed); changed[-1]['frames'] = 7
    errors.append(rejection(lambda: o.physical_cycles(changed, 999, 1006, 1), 'count/retirement failed'))
    errors.append(rejection(lambda: o.physical_cycles(parsed, 1002, 1006, 1), 'outside measured probe interval'))
    return {'passed': True, 'synthetic_journal': write(root / 'synthetic-journal.jsonl', raw(rows)),
        'negative_controls': errors, 'live_physical_frames_observed': 0, 'Camera2_or_app_pass': False}


CASES = (source_equivalence, historical_readiness, media_and_pixels, once_unknown_close,
         unknown_remove, second_scope, provider_cycles)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True); args = p.parse_args()
    output = Path(args.output); need(output.is_absolute() and not output.exists(), 'NEW_ABSOLUTE_CONTROL_DIRECTORY')
    output.mkdir(mode=0o700); modules = {path.name: load(path.name) for path in sorted((BASE / 'candidate').glob('*.py'))}
    before = [ref(path) for path in sorted((BASE / 'candidate').glob('*.py'))]; rows = []
    for case in CASES:
        root = output / case.__name__; root.mkdir(mode=0o700)
        try:
            value = case(modules, root)
        except BaseException as error:
            import traceback
            value = {'passed': False, 'error': type(error).__name__ + ':' + str(error), 'traceback': traceback.format_exc()}
        rows.append({'name': case.__name__, 'result': write(root / 'result.json', value), 'passed': value['passed']})
    after = [ref(path) for path in sorted((BASE / 'candidate').glob('*.py'))]
    result = {'schema': 'pocket4-camera-photo-local-pure-controls-v1', 'source_before': before,
        'source_after': after, 'source_unchanged': before == after, 'cases': rows,
        'passed': before == after and all(row['passed'] for row in rows), 'Main_actions': 0,
        'Android_UI_actions': 0, 'live_camera_opened': False, 'whole_app_business_accepted': False}
    result_ref = write(output / 'result.json', result)
    print(json.dumps({'result': result_ref, 'passed': result['passed'],
        'passed_cases': sum(row['passed'] for row in rows), 'expected_cases': len(rows)}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
