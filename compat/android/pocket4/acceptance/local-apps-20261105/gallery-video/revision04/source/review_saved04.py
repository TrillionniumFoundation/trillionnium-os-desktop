#!/usr/bin/env python3
"""Recheck downloaded, immutable Gallery04 evidence without device operations."""
from pathlib import Path
import base64
import hashlib
import importlib.util
import json
import sys
from PIL import Image

HERE = Path(__file__).resolve().parent
RESULT_SHA = '550d1525bd28cd074d3317dd4e3c3c38c43e78924209612a751d01bbb7c787fb'
EXPORT_SHA = 'd9aa8e8bf8da9c3cc9e1ff04ea9fdacc82fbb88c4dc6090ae08d4286b21db1af'
PACKAGE = 'com.android.gallery3d'
ACTIVITY = PACKAGE + '.app.MovieActivity'


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def canon(value):
    return json.loads(json.dumps(value, sort_keys=True))


def immutable_json(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    if path.exists():
        assert path.read_bytes() == raw, 'PREEXISTING_REVIEW_DIFFERS'
    else:
        with path.open('xb') as out:
            out.write(raw)


def main():
    assert pin(HERE / 'result-original.json')['sha256'] == RESULT_SHA
    assert pin(HERE / 'saved-export-original.json')['sha256'] == EXPORT_SHA
    result = read(HERE / 'result-original.json')
    saved = read(HERE / 'saved-export-original.json')
    assert saved['original_result_sha256'] == RESULT_SHA
    assert all(saved[k] == 0 for k in ('new_android_commands', 'new_ui_inputs', 'new_current_process_reads'))
    assert saved['original_files_modified'] is False
    assert result['state'] == 'VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED'
    assert result['business_scope_completed'] is True
    assert result['owned_tasks'] == result['normal_closed_tasks'] == [966, 967]
    assert result['pending_effect'] is result['close_pending'] is None
    assert result['install_pending'] is result['uninstall_pending'] is False
    assert result['gallery_before'] == result['gallery_after']
    assert result['native_actions_before'] == result['native_actions_after']
    assert result['guard_before'] == result['guard_after']
    assert result['gallery_after']['apk_sha256'] == '347c376f07a4365fa3828ddf9f011994fe527a53fd2f5bd059997ffd3904d46e'
    assert result['native_actions_after']['apk_sha256'] == 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
    assert result['cleanup']['errors'] == []
    assert all(result['cleanup'][k] for k in ('package_absent', 'staged_apk_removed', 'video_deleted'))
    assert result['owned_directory_removed'] and result['original_media_preserved']
    assert result['diagnostics']['clear'] is True
    assert result['ui_input_decisions'] == len(result['inputs']) == 3

    manifest = read(HERE / 'FLOW_SOURCE_MANIFEST.json')
    for name, expected in manifest['files'].items():
        assert pin(HERE / name) == expected
    # Reproduce the frozen verifier on downloaded bytes; this is an offline
    # evidence check, not an independently implemented video decoder.
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location('saved_video_verifier', HERE / 'verify_video.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    def record(label):
        matches = [(name, item) for name, item in saved['ui_records'].items() if name[4:-5] == label]
        assert len(matches) == 1
        return matches[0]

    frames = {}
    proofs = {}
    assert len(saved['frames']) == 8 and len(saved['ui_records']) == 22
    for name, item in saved['frames'].items():
        raw = base64.b64decode(item['base64'], validate=True)
        assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
        path = HERE / 'saved-frames' / name
        assert path.read_bytes() == raw
        journal_name, entry = record(name[:-4])
        value = entry['value']
        image = Image.open(path)
        assert image.mode == 'RGB' and list(image.size) == value['image_size'] == [1200, 1520]
        assert hashlib.sha256(image.tobytes()).hexdigest() == value['pixel_sha256']
        assert item['sha256'] == value['png_sha256']
        snapshot = value['snapshot']
        assert snapshot['scope']['package'] == PACKAGE and snapshot['scope']['activity'] == ACTIVITY
        assert snapshot['scope']['android_init_host_pid'] == 3588093
        assert snapshot['scope_bounds'] == snapshot['scope']['window_bounds'] == [320, 0, 1520, 1520]
        assert snapshot['scope']['display_id'] == 0
        frames[name] = {'bytes': len(raw), 'png_sha256': item['sha256'],
            'pixel_sha256': value['pixel_sha256'], 'size': list(image.size),
            'original_journal': {'name': journal_name, 'bytes': entry['bytes'], 'sha256': entry['sha256']},
            'capture_seconds': value['capture_seconds'],
            'monotonic_sample_midpoint': value['monotonic_sample_midpoint'],
            'scope': snapshot['scope'], 'scope_bounds': snapshot['scope_bounds'],
            'atomic_snapshot': snapshot['atomic_snapshot']}
        if not name.startswith('paused-'):
            proof = canon(verifier.verify_video_frame(image))
            assert proof == value['pattern']
            proofs[name] = proof
            frames[name]['reproduced_pattern'] = proof
        image.close()

    advancing = []
    for label in ('round-0-playing', 'resumed', 'round-1-playing'):
        a, b = frames[label + '-a.png'], frames[label + '-b.png']
        elapsed = b['monotonic_sample_midpoint'] - a['monotonic_sample_midpoint']
        proof = verifier.verify_advancing(proofs[label + '-a.png'], proofs[label + '-b.png'], elapsed)
        assert proof == record(label + '-advance')[1]['value']
        assert a['scope']['window_token'] == b['scope']['window_token']
        advancing.append({'phase': label, 'start_code': proofs[label + '-a.png']['visual_second_code'],
            'end_code': proofs[label + '-b.png']['visual_second_code'], **proof})
    paused_a, paused_b = frames['paused-a.png'], frames['paused-b.png']
    pause_seconds = paused_b['monotonic_sample_midpoint'] - paused_a['monotonic_sample_midpoint']
    assert 2.5 <= pause_seconds <= 12
    assert paused_a['pixel_sha256'] == paused_b['pixel_sha256']
    assert paused_a['png_sha256'] == paused_b['png_sha256']
    assert paused_a['scope']['window_token'] == paused_b['scope']['window_token']
    assert result['pixel_rounds'][0]['pause']['elapsed_seconds'] == pause_seconds

    def native(label, expected_desc=None):
        name, item = record(label)
        value = item['value']
        reply = value['native']
        assert reply['ok'] and reply['accessibility_mode_restoration_verified']
        assert reply['accessibility_mode'] == 'none' and reply['touch_exploration_after'] is False
        context = reply['window_context']
        assert context['null_child_count'] == 0
        window = context['selected_window']
        assert window is not None and window['active'] and window['focused'] and window['display_id'] == 0
        assert window['bounds'] == [320, 0, 1520, 1520]
        if 'focus' in value:
            assert value['focus']['verified'] and value['focus']['package'] == PACKAGE
            assert value['focus']['activity'] == ACTIVITY and value['focus']['task'] == 966
            assert value['focus']['window_token'] == paused_a['scope']['window_token']
        selected = [n for n in reply['nodes'] if n.get('visible') and n.get('enabled')
            and n.get('package') == PACKAGE and n.get('content-desc') == expected_desc] if expected_desc else []
        if expected_desc:
            assert len(selected) == 1 and selected[0]['clickable'] is True
        return {'source_record': name, 'bytes': item['bytes'], 'sha256': item['sha256'],
            'node_count': len(reply['nodes']), 'matching_nodes': selected,
            'selected_window': window, 'complete_tree_null_children': 0,
            'accessibility_mode_restoration_verified': True}

    controls = {'visible_after_show': native('show-controls-native-after', 'Pause video'),
        'visible_after_pause': native('pause-post', 'Play video'),
        'visible_after_pause_interval': native('paused-state-after-interval', 'Play video'),
        'visible_after_resume': native('resume-post', 'Pause video')}
    actions = []
    for label, desc in (('show-controls-native', None), ('pause', 'Pause video'), ('resume', 'Play video')):
        intent_name, intent_item = record(label + '-intent')
        receipt_name, receipt_item = record(label + '-receipt')
        intent, receipt = intent_item['value'], receipt_item['value']
        request = intent['request']
        assert request['expected_package'] == PACKAGE and request['accessibility_mode'] == 'none'
        assert request['display'] == 0 and request['op'] == 'click' and intent['automatic_retry'] is False
        assert receipt['ok'] and receipt['performed'] == 'click'
        assert receipt['accessibility_mode_restoration_verified'] and receipt['touch_exploration_after'] is False
        for target_key in ('target', 'actual_target'):
            target = receipt[target_key]
            for key, value in request['selector'].items():
                assert target[{'id': 'resource-id', 'desc': 'content-desc'}.get(key, key)] == value
        if desc:
            assert request['method'] == 'accessibility' and request['selector']['desc'] == desc
        else:
            assert request['method'] == receipt['method'] == 'mouse'
            assert receipt['source'] == 'native_bounds_mouse'
            assert receipt['target']['bounds_array'] == receipt['actual_target']['bounds_array'] == [320, 310, 1520, 1210]
            assert receipt['coordinates'] == [920, 760]
        actions.append({'intent': {'name': intent_name, 'bytes': intent_item['bytes'], 'sha256': intent_item['sha256'], 'value': intent},
            'receipt': {'name': receipt_name, 'bytes': receipt_item['bytes'], 'sha256': receipt_item['sha256'], 'value': receipt},
            'ACK_alone_does_not_prove_business_effect': True})

    review = {'schema': 'gallery04-saved-byte-evidence-review/v1',
        'state': 'PLAY_PAUSE_RESUME_SEPARATE_REOPEN_AND_CLEANUP_VERIFIED',
        'original_result': pin(HERE / 'result-original.json'),
        'original_saved_export': pin(HERE / 'saved-export-original.json'),
        'original_export_gzip': pin(HERE / 'saved-export-original.json.gz'),
        'frozen_verifier_pins': {n: manifest['files'][n] for n in ('verify_pattern.py', 'verify_video.py')},
        'verification_method': 'Recomputed PNG and RGB hashes; replayed frozen pixel verifier on six moving frames; exact paused full-frame equality plus actual control transitions; reviewed three original owned screenshots visually.',
        'frames': frames, 'advancing_phases': advancing, 'controls': controls, 'actual_inputs': actions,
        'pause': {'elapsed_seconds': pause_seconds, 'entire_application_RGB_and_PNG_bytes_equal': True,
            'actual_Play_control_before_and_after_interval': True, 'paused_timecode_decode_claimed': False,
            'visible_overlay_obscures_part_of_timecode': True},
        'gallery_identity': result['gallery_after'], 'native_action_identity': result['native_actions_after'],
        'guard_before': result['guard_before'], 'guard_after': result['guard_after'],
        'owned_tasks_normally_closed': result['normal_closed_tasks'],
        'pending_effect': result['pending_effect'], 'close_pending': result['close_pending'],
        'cleanup': result['cleanup'], 'original_media_preserved': result['original_media_preserved'],
        'owned_directory_removed': result['owned_directory_removed'], 'diagnostics': result['diagnostics'],
        'runtime_sampler_summary': {k: result['runtime_evidence'][k] for k in
            ('sample_count', 'elapsed_seconds', 'thread_joined', 'errors', 'scan_error_count', 'stable_complete_mapping_samples')},
        'new_Android_commands': 0, 'new_UI_inputs': 0, 'new_current_process_reads': 0,
        'full_gallery_open_gate_passed': False, 'album_enumeration_qualified': False,
        'rotation_qualified': False, 'seek_qualified': False, 'audio_qualified': False,
        'runtime_engine_or_stress_gate_passed': False, 'whole_app_production_ready': False,
        'retained_previous_runs': {'01': 'Failed initial palette verifier; no control inputs.',
            '02': 'Rejected changed Main limits before Android operations.',
            '03': 'Failed screenshot freshness checks before control dispatch; actual playback and cleanup retained.'}}
    immutable_json(HERE / 'SAVED_REVIEW.json', review)
    print(json.dumps({'state': review['state'], 'frames_verified': len(frames),
        'actual_inputs': len(actions), 'advancing_phases': advancing, 'pause_seconds': pause_seconds,
        'review': pin(HERE / 'SAVED_REVIEW.json'), 'whole_app_production_ready': False}))


if __name__ == '__main__':
    main()
