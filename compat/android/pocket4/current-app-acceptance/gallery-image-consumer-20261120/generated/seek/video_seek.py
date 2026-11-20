"""One source-bound midpoint seek, joined to independently decoded video pixels.

The target is the fresh native TimeBar node. Its center is selected by the
already qualified native-bounds mouse path; no historical coordinates are used.
The original 60-second owned clip has six-bit timecodes and no audio track.
"""
import copy
import math
import time

GALLERY = 'com.android.gallery3d'
DESCRIPTION = 'Video player time bar'
EXPECTED_SECOND = 30


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def observed_timebar(nodes, window_bounds):
    matches = [n for n in nodes if n.get('package') == GALLERY
        and n.get('class') == 'android.view.View' and n.get('content-desc') == DESCRIPTION
        and n.get('visible') is True and n.get('enabled') is True
        and n.get('clickable') is False and n.get('important_for_accessibility') is True]
    need(len(matches) == 1, 'ONE_ACTUAL_CURRENT_VIDEO_TIMEBAR_REQUIRED')
    node = matches[0]; bounds = node.get('bounds_array')
    need(type(window_bounds) is list and len(window_bounds) == 4
        and all(type(x) is int for x in window_bounds)
        and type(bounds) is list and len(bounds) == 4 and all(type(x) is int for x in bounds)
        and window_bounds[0] <= bounds[0] < bounds[2] <= window_bounds[2]
        and window_bounds[1] <= bounds[1] < bounds[3] <= window_bounds[3],
        'CURRENT_VIDEO_TIMEBAR_OUTSIDE_OWNED_WINDOW')
    need(type(node.get('window_id')) is int and node['window_id'] >= 0,
        'CURRENT_VIDEO_TIMEBAR_WINDOW_ID_REQUIRED')
    return node


def verify_jump(before, after, dispatch_started, dispatch_finished):
    """Reject ordinary playback, stale samples and an unbounded capture interval."""
    def sample(value):
        second = value['pattern']['visual_second_code']
        middle, duration = value['monotonic_sample_midpoint'], value['capture_seconds']
        need(type(second) is int and 0 <= second < 60
            and type(middle) in (int, float) and math.isfinite(middle)
            and type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration <= 8,
            'BOUNDED_DECODED_VIDEO_SAMPLE_REQUIRED')
        return second, middle - duration / 2, middle + duration / 2
    b, b_start, b_end = sample(before); a, a_start, a_end = sample(after)
    need(all(type(t) in (int, float) and math.isfinite(t) for t in (dispatch_started, dispatch_finished))
        and b < 20 and b_end <= dispatch_started <= dispatch_finished <= a_start
        and dispatch_finished - dispatch_started <= 30 and a_end - dispatch_started <= 35,
        'ORDERED_BOUNDED_SEEK_SAMPLES_REQUIRED')
    # The native mutation occurred within the actual dispatch interval. Decode
    # quantization and a short decoder transition get two seconds of tolerance.
    expected_lower = EXPECTED_SECOND + a_start - dispatch_finished - 2
    expected_upper = EXPECTED_SECOND + a_end - dispatch_started + 2
    natural_upper = b + a_end - b_start + 2
    need(expected_lower <= a <= expected_upper, 'PIXELS_DO_NOT_MATCH_MIDPOINT_SEEK')
    need(a >= natural_upper + 5, 'SEEK_PIXELS_COULD_BE_ORDINARY_PLAYBACK')
    return {'verified': True, 'expected_seek_second': EXPECTED_SECOND,
        'decoded_before_second': b, 'decoded_after_second': a,
        'actual_dispatch_interval': [dispatch_started, dispatch_finished],
        'expected_post_seek_second_interval': [expected_lower, expected_upper],
        'no_seek_playback_upper_second': natural_upper,
        'minimum_discontinuity_margin_seconds': 5,
        'actual_discontinuity_margin_seconds': a - natural_upper,
        'native_ack_alone_is_not_business_success': True, 'audio_output_qualified': False}


def seek_midpoint(flow, entry):
    need(entry['index'] == 1 and len(flow.result['pixel_rounds']) == 1
        and flow.result['pixel_rounds'][0].get('normal_close_verified') is True
        and flow.seek_attempts == 0 and flow.pending is None and flow.inputs < 12,
        'ONE_SEEK_IN_SECOND_NORMAL_OWNED_VIDEO_ROUND')
    before = copy.deepcopy(entry['initial_playback']['after'])
    need(before['pattern']['visual_second_code'] < 20, 'MIDPOINT_SEEK_REQUIRES_EARLY_DECODED_FRAME')
    flow.ensure_controls()
    focus, nodes, scope = flow.native_controls('seek-midpoint-before')
    need(flow.control(nodes, flow.s.components['video_flow.py'].PAUSE_LABELS) is not None
        and flow.control(nodes, flow.s.components['video_flow.py'].PLAY_LABELS) is None,
        'MIDPOINT_SEEK_REQUIRES_ACTUAL_PLAYING_CONTROL')
    node = observed_timebar(nodes, scope); bounds = node['bounds_array']
    need(flow.movie_focus() == focus, 'OWNED_MOVIE_FOCUS_CHANGED_BEFORE_SEEK')
    started = time.monotonic()
    natural_latest = before['pattern']['visual_second_code'] + started - (
        before['monotonic_sample_midpoint'] - before['capture_seconds'] / 2) + 2
    need(natural_latest < 25, 'SEEK_PRECONDITION_TOO_CLOSE_TO_MIDPOINT_NO_INPUT')
    selector = {'package': GALLERY, 'class': 'android.view.View', 'desc': DESCRIPTION,
        'enabled': True, 'clickable': False}
    request = {'op': 'click', 'expected_package': GALLERY, 'display': 0,
        'accessibility_mode': 'none', 'method': 'mouse', 'selector': selector}
    flow.record('seek-midpoint-intent', {'request': request, 'observed_control': node,
        'focus': focus, 'source_frame': before, 'expected_seek_second': EXPECTED_SECOND,
        'source_semantics': 'TimeBar.onTouchEvent -> onScrubbingEnd -> MoviePlayer.onSeekEnd -> VideoView.seekTo',
        'automatic_retry': False})
    flow.pending = 'seek-midpoint'; flow.seek_attempts += 1; flow.inputs += 1
    try:
        reply = flow.s.helper.ui(request)
    except BaseException as error:
        details = getattr(error, 'details', {})
        if details.get('outcome_unknown') is False:
            flow.record('seek-midpoint-explicit-no-effect', {'error': str(error), 'details': details})
            flow.pending = None
        raise
    finished = time.monotonic()
    flow.record('seek-midpoint-receipt', reply); target = reply.get('actual_target', {})
    need(reply.get('ok') is True and reply.get('performed') == 'click' and reply.get('method') == 'mouse'
        and reply.get('source') == 'native_bounds_mouse' and reply.get('outcome_unknown') is not True
        and reply.get('accessibility_mode_restoration_verified') is True
        and target.get('package') == GALLERY and target.get('class') == 'android.view.View'
        and target.get('content-desc') == DESCRIPTION and target.get('bounds_array') == bounds
        and reply.get('coordinates') == [(bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2],
        'ACTUAL_CURRENT_TIMEBAR_MOUSE_ACK_NOT_JOINED')
    current, fresh, _ = flow.native_controls('seek-midpoint-after')
    need(current == focus and flow.control(fresh, flow.s.components['video_flow.py'].PAUSE_LABELS) is not None
        and flow.control(fresh, flow.s.components['video_flow.py'].PLAY_LABELS) is None,
        'MIDPOINT_SEEK_CHANGED_OWNED_MOVIE_OR_PLAYBACK_STATE')
    flow.runtime.phase_changed('second-round-seek')
    advancing = flow.advancing('seek-midpoint-playing')
    proof = verify_jump(before, advancing['before'], started, finished)
    proof.update(owned_task=focus['task'], window_token=focus['window_token'],
        actual_target=target, observed_control=node, before=before, after=advancing,
        automatic_retry=False, seek_attempts=flow.seek_attempts)
    flow.record('seek-midpoint-pixel-proof', proof)
    flow.result['seek_observation'] = proof; entry['seek'] = proof
    flow.pending = None
    flow.result['inputs'].append({'label': 'seek-midpoint', 'method': 'native_bounds_mouse',
        'actual_target': target, 'owned_task': focus['task'], 'pixel_discontinuity_verified': True})
    return proof
