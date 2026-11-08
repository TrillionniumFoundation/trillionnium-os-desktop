#!/usr/bin/python3 -I
"""Reproduce the minimal video adapter from exact qualified display sources."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '2a062fdc1e93bb8ca494bc2b2ade1196efb48527399b0843886920e06a8674e9'
HOLDER_SHA = '68fef3e0a46ab2f1b5d783ab5640add6d2f6625c9655a803efb25409ad79917f'
LEASE_SHA = '81f34cdbc75a2cf4e092a961fe4dce5d23522842c0ec54cdcff4fc9c99e4dbfd'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source(node, text):
    return ''.join(text.splitlines(True)[node.lineno - 1:node.end_lineno])


def function(text, name, cls=None):
    body = ast.parse(text).body
    if cls:
        body = next(n for n in body if isinstance(n, ast.ClassDef) and n.name == cls).body
    return next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)


def replace(text, node, value):
    lines = text.splitlines(True)
    lines[node.lineno - 1:node.end_lineno] = [value.rstrip() + '\n']
    return ''.join(lines)


def assignment(text, name, value):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return replace(text, node, name + ' = ' + value)


def main():
    raw = (ROOT / 'provenance/photo_display_wrapper.py').read_bytes()
    holder_raw = (ROOT / 'provenance/display_holder.py').read_bytes()
    lease_raw = (ROOT / 'display/display_lease.py').read_bytes()
    assert digest(raw) == BASE_SHA and digest(holder_raw) == HOLDER_SHA and digest(lease_raw) == LEASE_SHA
    original = raw.decode()
    extension = (ROOT / 'tools/video_display_contract.py').read_text()
    result = original.replace('Bind the frozen photo-only Camera case to one qualified normal display lease.',
                              'Bind one fresh Camera video/acoustic case to the owned normal display lease.')
    result = assignment(result, 'PREPARED', 'Path(__file__).resolve().parent')
    result = assignment(result, 'PHOTO_PREPARED', 'None  # Historical photo preparation is never loaded.')
    result = assignment(result, 'PREPARATION_REF', 'None')
    result = assignment(result, 'WRAPPER_SECONDS', '665')
    result = assignment(result, 'CAMERA_SECONDS', '510  # Includes acoustic owner retirement.')
    result = assignment(result, 'CAMERA_GRACE_SECONDS', '90  # Worker cleanup60 + acoustic retirement30.')
    holder = holder_raw.decode()
    assert holder.count('default=475') == holder.count('args.max_seconds == 475') == 1
    holder = holder.replace('default=475', 'default=665').replace('args.max_seconds == 475', 'args.max_seconds == 665')
    holder_digest = digest(holder.encode())
    sources = """{
    'holder': (PREPARED / 'display_holder.py', %r, 16384),
    'lease': (PREPARED / 'display_lease.py', %r, 32768),
    'lifecycle': (ROOT.parent / 'framework/runtime_support/capture_lifecycle.py',
                  '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877', 32768),
}""" % (holder_digest, LEASE_SHA)
    result = assignment(result, 'SOURCES', sources)
    globals_text = """
VIDEO_CONTEXT = None
VIDEO_INVENTORY_SHA256 = '28e61371c50638a3ac33d4e28b0466754bc2b81c9f5d015f262d43e60243dd00'
VIDEO_ENTRY_PIN = (9811, '55607f576146c9adc8792fdeb510c1992512ac4d782ccd0efcb75415c81ac4f9')
"""
    result = result.replace('\nMAX_PACKET = 65536', globals_text + '\nMAX_PACKET = 65536', 1)
    for old, new in [('__init__', 'supervisor_init'), ('launch_camera', 'launch_camera'),
                     ('validate_camera_result', 'validate_camera_result')]:
        snippet = source(function(extension, new), extension).replace('def ' + new + '(', 'def ' + old + '(', 1)
        result = replace(result, function(result, old, 'Supervisor'), textwrap.indent(snippet, '    '))
    for name in ('configure_video_preparation', 'validate_video_terminals'):
        snippet = source(function(extension, name), extension)
        result = result.replace('\nclass Supervisor:', '\n' + snippet + '\n\nclass Supervisor:', 1)
    result = replace(result, function(result, 'main'), source(function(extension, 'main'), extension))
    node = function(result, 'run', 'Supervisor')
    run = source(node, result)
    run = run.replace('full 40 s finally', 'full 60 s worker finally and 30 s acoustic retirement')
    run = run.replace("and self.record.get('independent_release_observation', {}).get('current', {}).get('locked') is True)",
        "and self.record.get('independent_release_observation', {}).get('current', {}).get('locked') is True\n"
        "            and self.record.get('adopted_retirement', {}).get('owned_tree_cleanup_complete') is True\n"
        "            and self.record['adopted_retirement'].get('descendants') == []\n"
        "            and set(self.actors) == {'camera', 'holder', 'release_observer'}\n"
        "            and all(all(item['lifecycle'].get(k) is True for k in ('child_reaped', 'pidfd_closed'))\n"
        "                and item['lifecycle'].get('returncode') == 0 for item in self.actors.values()))")
    run = run.replace('pocket4-final-camera-photo-display-result-v1', 'pocket4-current-camera-video-display-result-v1')
    run = run.replace("'photo_capture_persistence_verified': complete", "'camera_video_and_display_verified': complete, 'case_business_success_verified': complete")
    run = run.replace("'inner_photo_state'", "'inner_video_state'")
    run = run.replace('PHOTO_AND_DISPLAY_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING', 'VIDEO_AND_DISPLAY_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING')
    run = run.replace("'video_audio_playback_qualified': False", "'video_audio_playback_qualified': complete, 'runtime_qualified': False")
    run = run.replace('photo_capture_persistence_verified=False',
        'camera_video_and_display_verified=False, case_business_success_verified=False, video_audio_playback_qualified=False')
    result = replace(result, node, run)
    compile(result, 'video_display_wrapper.py', 'exec')
    compile(holder, 'display_holder.py', 'exec')
    base_class = next(n for n in ast.parse(original).body if isinstance(n, ast.ClassDef) and n.name == 'Supervisor')
    new_class = next(n for n in ast.parse(result).body if isinstance(n, ast.ClassDef) and n.name == 'Supervisor')
    old_methods = {n.name: n for n in base_class.body if isinstance(n, ast.FunctionDef)}
    new_methods = {n.name: n for n in new_class.body if isinstance(n, ast.FunctionDef)}
    changed = [name for name in old_methods if ast.dump(old_methods[name], include_attributes=False)
               != ast.dump(new_methods[name], include_attributes=False)]
    assert set(changed) == {'__init__', 'launch_camera', 'validate_camera_result', 'run'}
    unchanged = [name for name in old_methods if name not in changed]
    assert all(source(old_methods[n], original) == source(new_methods[n], result) for n in unchanged)
    old_holder = ast.parse(holder_raw)
    new_holder = ast.parse(holder)
    old_constants = [n for n in ast.walk(old_holder) if isinstance(n, ast.Constant) and n.value == 475]
    assert len(old_constants) == 2
    for node in old_constants:
        node.value = 665
    assert ast.dump(old_holder, include_attributes=False) == ast.dump(new_holder, include_attributes=False)
    display = ROOT / 'display'
    display.mkdir(exist_ok=True)
    (display / 'video_display_wrapper.py').write_text(result)
    (display / 'display_holder.py').write_text(holder)
    patch = ''.join(difflib.unified_diff(original.splitlines(True), result.splitlines(True),
                    fromfile='a/photo_display_wrapper.py', tofile='b/video_display_wrapper.py'))
    patch += ''.join(difflib.unified_diff(holder_raw.decode().splitlines(True), holder.splitlines(True),
                    fromfile='a/display_holder.py', tofile='b/display_holder.py'))
    (ROOT / 'review/video-display-adaptation.diff').write_text(patch)
    report = {'schema': 'pocket4-camera-video-display-source-adaptation-v1',
        'base_wrapper_sha256': BASE_SHA, 'base_holder_sha256': HOLDER_SHA,
        'video_wrapper_sha256': digest(result.encode()), 'video_holder_sha256': holder_digest,
        'lease_sha256_unchanged': LEASE_SHA, 'changed_supervisor_methods': changed,
        'unchanged_supervisor_methods': unchanged,
        'unchanged_methods_are_byte_identical': True,
        'holder_AST_only_changes': [{'from': 475, 'to': 665, 'occurrences': 2}],
        'budgets': {'outer_seconds': 665, 'ready_seconds': 20, 'acoustic_supervisor_seconds': 510,
                    'cancellation_grace_seconds': 90, 'caller_seconds_minimum': 675},
        'real_display_qualification_pending': True, 'real_Main_epoch_and_device_inputs_pending': True,
        'runtime_qualified': False, 'whole_app_business_accepted': False}
    (ROOT / 'review/video-display-source-adaptation.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
