"""One owned Camera video: actual native boundaries and independent readback.

This is a new state machine for the original camera.video gate. It does not
discover Main or dispatch any command. The source-admitted Session records
real native returns before the final backend can append post-capture fields.
No state can turn a missing ACK, timeout or orphaned operation into success.
"""
import copy
import hashlib
import json
import re

PACKAGE = 'com.android.camera2'
SHUTTER = PACKAGE + ':id/shutter_button'
TIMER = PACKAGE + ':id/recording_time'
MODE_TOGGLE = PACKAGE + ':id/accessibility_mode_toggle_button'
VIDEO_DESCRIPTION = 'Switch to Video Camera'
PHOTO_DESCRIPTION = 'Switch to Camera Mode'
MAX_RECORDING_SECONDS = 20


class Refusal(RuntimeError):
    pass


def need(value, why):
    if not value:
        raise Refusal(why)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def ref(value):
    need(type(value) is dict and set(value) == {'path', 'bytes', 'sha256'}
        and type(value['path']) is str and value['path'].startswith('/')
        and type(value['bytes']) is int and value['bytes'] > 0
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']),
        'EXACT_CURRENT_VIDEO_EVIDENCE_REFERENCE')
    return copy.deepcopy(value)


def focus(value, task):
    need(type(value) is dict and value.get('verified') is True
        and value.get('package') == PACKAGE and value.get('task') == task
        and type(task) is int and task > 0 and value.get('user') == 0
        and value.get('activity') in ('com.android.camera.CameraLauncher', 'com.android.camera.CameraActivity')
        and value.get('focused_activity') == value['activity']
        and re.fullmatch('[0-9a-f]{1,32}', value.get('window_token', '')),
        'ACTUAL_OWNED_CAMERA_WINDOW_REQUIRED')
    # Native accessibility connection IDs are intentionally not a cross-call
    # identity. They are validated inside each current dump below.
    return copy.deepcopy(value)


def native_nodes(value):
    need(type(value) is dict and value.get('ok') is True
        and value.get('outcome_unknown') is not True,
        'CURRENT_CAMERA_OBSERVATION_REQUIRED')
    native = value.get('native', value)
    need(type(native) is dict and native.get('ok') is True
        and native.get('accessibility_mode_restoration_verified') is True
        and native.get('outcome_unknown') is not True and type(native.get('nodes')) is list,
        'ACTUAL_RESTORED_NATIVE_CAMERA_TREE_REQUIRED')
    context = native.get('window_context', {})
    window = context.get('selected_window')
    need(type(window) is dict and type(window.get('window_id')) is int
        and context.get('snapshot_complete') is True and context.get('truncated') is False
        and context.get('display_id') == 0 and window.get('active') is True
        and window.get('display_id') == 0 and window.get('focused') is True
        and window.get('type') == 1 and window.get('root', {}).get('package') == PACKAGE,
        'ONE_FOCUSED_NATIVE_CAMERA_APPLICATION_WINDOW')
    nodes = native['nodes']
    need(len(nodes) <= 4096 and all(type(n) is dict for n in nodes), 'BOUNDED_NATIVE_CAMERA_TREE')
    return nodes, window


def one_control(value, *, ident=None, description=None):
    nodes, window = native_nodes(value)
    matches = [n for n in nodes if n.get('package') == PACKAGE
        and n.get('visible') is True and n.get('enabled') is True and n.get('clickable') is True
        and (ident is None or n.get('resource-id') == ident)
        and (description is None or n.get('content-desc') == description)]
    need(len(matches) == 1, 'ONE_ACTUAL_CAMERA_CONTROL_REQUIRED')
    node = matches[0]
    need(node.get('window_id') == window['window_id'], 'CAMERA_NODE_NOT_CURRENT_NATIVE_WINDOW')
    bounds = node.get('bounds_array')
    need(type(bounds) is list and len(bounds) == 4 and all(type(x) is int for x in bounds)
        and bounds[0] >= 0 and bounds[1] >= 0 and bounds[0] < bounds[2] <= 8192
        and bounds[1] < bounds[3] <= 8192, 'BOUNDED_ACTUAL_CAMERA_CONTROL')
    selector = {'enabled': True, 'clickable': True}
    if ident is not None:
        selector['id'] = ident
    if description is not None:
        selector['desc'] = description
    return {'node': copy.deepcopy(node), 'selector': selector,
            'selected_window': copy.deepcopy(window)}


def recording_clock(value):
    nodes, window = native_nodes(value)
    matches = [n for n in nodes if n.get('package') == PACKAGE
               and n.get('resource-id') == TIMER and n.get('visible') is True]
    need(len(matches) <= 1, 'AMBIGUOUS_CAMERA_RECORDING_CLOCK')
    if not matches:
        return None
    node = matches[0]
    need(node.get('window_id') == window['window_id'], 'RECORDING_CLOCK_NATIVE_WINDOW_MISMATCH')
    text = node.get('text')
    # The locked VideoModule.updateRecordingTime uses whole mm:ss (hh:mm:ss
    # only once hours>0); countdown/centiseconds are not this short case.
    if text == '':
        # VideoUI briefly makes the timer visible with empty text before its
        # first whole-second update. Preserve that transitional observation.
        return {'seconds': None, 'text': text, 'node': copy.deepcopy(node),
                'selected_window': copy.deepcopy(window)}
    need(type(text) is str and re.fullmatch('[0-5][0-9]:[0-5][0-9]', text),
         'ACTUAL_SHORT_RECORDING_CLOCK_FORMAT')
    minutes, seconds = map(int, text.split(':'))
    seconds += 60 * minutes
    need(seconds <= MAX_RECORDING_SECONDS, 'CAMERA_RECORDING_EXCEEDED_EXPLICIT_CASE_BOUND')
    return {'seconds': seconds, 'text': text, 'node': copy.deepcopy(node),
            'selected_window': copy.deepcopy(window)}


def known_click(request, reply):
    need(type(request) is dict and request.get('op') == 'click'
        and request.get('expected_package') == PACKAGE and request.get('display') == 0
        and request.get('method') == 'accessibility' and request.get('accessibility_mode', 'none') == 'none',
        'UNCHANGED_ACTUAL_NATIVE_CLICK_REQUEST')
    need(type(reply) is dict and reply.get('ok') is True and reply.get('performed') == 'click'
        and reply.get('outcome_unknown') is False and reply.get('automatic_retry') is False
        and reply.get('accessibility_mode_restoration_verified') is True,
        'ACTUAL_NATIVE_CLICK_ACK_REQUIRED')
    selector = request['selector']
    need(type(selector) is dict and {'enabled', 'clickable'} <= set(selector)
        and selector['enabled'] is selector['clickable'] is True
        and set(selector) <= {'id', 'desc', 'enabled', 'clickable'}
        and ('id' in selector or 'desc' in selector), 'EXACT_OBSERVED_VIDEO_CONTROL_SELECTOR')
    for key, field in (('id', 'resource-id'), ('desc', 'content-desc')):
        if key in selector:
            need(reply.get('target', {}).get(field) == selector[key]
                and reply.get('actual_target', {}).get(field) == selector[key],
                'NATIVE_CLICK_ACK_TARGET_DIFFERS')
    return copy.deepcopy(reply)


class Recording:
    """Each action is durably claimed once; native ACK and effect stay separate."""
    def __init__(self, *, nonce, scope, phase, epoch_sha256, task, emit):
        need(type(nonce) is str and re.fullmatch('[0-9a-f]{16}', nonce)
            and nonce != '0' * 16, 'NEW_NONZERO_ACOUSTIC_NONCE_REQUIRED')
        need(type(epoch_sha256) is str and re.fullmatch('[0-9a-f]{64}', epoch_sha256), 'FRESH_MAIN_EPOCH_REQUIRED')
        need(type(task) is int and task > 0 and callable(emit), 'OWNED_CAMERA_TASK_AND_DURABLE_RECORDER')
        self.nonce, self.scope, self.phase = nonce, ref(scope), ref(phase)
        self.epoch_sha256, self.task, self.emit = epoch_sha256, task, emit
        self.state = 'NEW'; self.pending = None; self.attempted = set(); self.actions = []
        self.observations = []; self.initial_mode = None; self.recording = []
        self.start_ack = self.stop_ack = None; self.media = self.audio = self.playback = None
        self.retired = False; self._last_native = None; self.mode_restored = False

    def observe(self, *, value, focus_value, mode, monotonic_ns, observation_ref):
        need(not self.retired and type(monotonic_ns) is int and monotonic_ns > 0,
             'CURRENT_VIDEO_OBSERVATION_TIME')
        actual_focus = focus(focus_value, self.task)
        native_nodes(value)
        need(mode in ('0', '1'), 'ONLY_ORIGINAL_CAMERA_PHOTO_AND_VIDEO_MODES')
        if self.observations:
            need(monotonic_ns > self.observations[-1]['monotonic_ns'], 'RECORDING_OBSERVATION_TIME_REGRESSED')
        clock = recording_clock(value)
        row = {'reference': ref(observation_ref), 'focus': actual_focus, 'mode': mode,
            'monotonic_ns': monotonic_ns, 'clock': clock,
            'native_tree_sha256': digest(value.get('native', value)), 'scope': self.scope, 'phase': self.phase}
        if self.initial_mode is None:
            need(self.state == 'NEW' and clock is None, 'NO_PREEXISTING_CAMERA_RECORDING_TO_ADOPT')
            self.initial_mode = mode
            self.state = 'VIDEO_READY' if mode == '1' else 'PHOTO_READY'
        self.observations.append(row)
        self._last_native = copy.deepcopy(value.get('native', value))
        self.emit('video-observation', row)
        if self.pending is not None and self.pending['native_ack'] is not None:
            action = self.pending['action']
            after_ack = monotonic_ns > self.pending['ack_monotonic_ns']
            if action == 'select_video' and after_ack and mode == '1' and clock is None:
                self._complete('VIDEO_READY', row)
            elif action == 'restore_photo' and after_ack and mode == '0' and clock is None:
                self.mode_restored = True
                self._complete('MODE_RESTORED', row)
            elif action == 'start' and after_ack and mode == '1' and clock is not None and clock['seconds'] is not None:
                need(clock['seconds'] <= 5, 'RECORDING_ALREADY_OLD_WHEN_START_WAS_OBSERVED')
                self.recording.append(row)
                self._complete('RECORDING', row)
            elif action == 'stop' and after_ack and mode == '1' and clock is None:
                self._complete('STOPPED_UNSAVED', row)
        elif self.state == 'RECORDING':
            need(mode == '1' and clock is not None and clock['seconds'] is not None,
                 'RECORDING_DISAPPEARED_WITHOUT_OWN_STOP')
            previous = self.recording[-1]
            need(clock['seconds'] >= previous['clock']['seconds'], 'RECORDING_CLOCK_REGRESSED')
            elapsed = (monotonic_ns - previous['monotonic_ns']) / 1e9
            need(clock['seconds'] - previous['clock']['seconds'] <= elapsed + 2,
                 'RECORDING_CLOCK_NOT_COHERENT_WITH_ACTUAL_OBSERVATION_TIME')
            self.recording.append(row)
        return copy.deepcopy(row)

    def claim(self, *, action, request, control, focus_value, monotonic_ns):
        need(not self.retired and self.pending is None and action not in self.attempted
            and self.observations, 'NO_PENDING_OR_REPLAYED_CAMERA_VIDEO_ACTION')
        allowed = {'mode_menu': ('PHOTO_READY',),
            'select_video': ('MODE_MENU',), 'start': ('VIDEO_READY',),
            'stop': ('RECORDING',), 'restore_photo': ('RESTORE_MENU',),
            'restore_menu': ('SAVED', 'PLAYBACK_VERIFIED')}
        need(action in allowed and self.state in allowed[action], 'CAMERA_VIDEO_ACTION_STATE_MISMATCH')
        now_focus = focus(focus_value, self.task); last = self.observations[-1]
        need(now_focus == last['focus'] and type(monotonic_ns) is int
            and last['monotonic_ns'] <= monotonic_ns <= last['monotonic_ns'] + 5_000_000_000,
            'ACTUAL_CAMERA_WINDOW_CHANGED_OR_OBSERVATION_TOO_OLD')
        expected = {'op': 'click', 'package': PACKAGE, 'display': 0, 'method': 'accessibility',
                    'selector': copy.deepcopy(control['selector'])}
        need(request == expected, 'UNCHANGED_CURRENT_VIDEO_CONTROL_REQUEST')
        selector = control['selector']
        need(control == one_control(self._last_native, ident=selector.get('id'),
            description=selector.get('desc')), 'CONTROL_MUST_BE_FROM_THE_LATEST_ACTUAL_CAMERA_DUMP')
        if action in ('start', 'stop'):
            need(selector == {'id': SHUTTER, 'enabled': True, 'clickable': True}, 'SAME_ORIGINAL_VIDEO_SHUTTER')
        elif action in ('mode_menu', 'restore_menu'):
            need(selector == {'id': MODE_TOGGLE, 'enabled': True, 'clickable': True}, 'ORIGINAL_CAMERA_MODE_MENU')
        else:
            wanted = VIDEO_DESCRIPTION if action == 'select_video' else PHOTO_DESCRIPTION
            need(selector == {'desc': wanted, 'enabled': True, 'clickable': True}, 'ORIGINAL_SOURCE_VIDEO_OR_PHOTO_MODE')
        if action == 'start':
            need(last['mode'] == '1' and last['clock'] is None, 'VIDEO_MODE_AND_NOT_RECORDING_BEFORE_START')
        if action == 'stop':
            need(len(self.recording) >= 2 and self.recording[-1]['clock']['seconds'] > self.recording[0]['clock']['seconds']
                and self.recording[-1]['monotonic_ns'] - self.recording[0]['monotonic_ns'] >= 1_000_000_000,
                'STOP_REQUIRES_KNOWN_START_AND_ACTUAL_ADVANCING_CLOCK')
        item = {'action': action, 'request': expected, 'observed_control': copy.deepcopy(control),
            'observed_focus': now_focus, 'observation': last['reference'],
            'claimed_monotonic_ns': monotonic_ns, 'scope': self.scope, 'phase': self.phase,
            'epoch_sha256': self.epoch_sha256, 'nonce': self.nonce, 'automatic_retry': False}
        item['intent_ref'] = ref(self.emit('video-' + action + '-intent', item))
        # Burning authority is independent of later command/receipt success.
        self.attempted.add(action); self.pending = {**item, 'native_ack': None,
                                                   'ack_monotonic_ns': None, 'dispatch_returned': False}
        return copy.deepcopy(item)

    def native_return(self, *, request, reply, monotonic_ns, boundary_ref):
        item = self.pending
        need(item is not None and item['native_ack'] is None and type(monotonic_ns) is int
            and monotonic_ns >= item['claimed_monotonic_ns'], 'ONE_NATIVE_RETURN_FOR_CURRENT_VIDEO_INTENT')
        projected = dict(item['request']); projected['expected_package'] = projected.pop('package')
        need(request == projected, 'NATIVE_VIDEO_REQUEST_DIFFERS_FROM_CURRENT_CLAIM')
        ack = known_click(request, reply)
        # Persist the unmodified native result before accepting it in memory.
        value = {'intent': item['intent_ref'], 'native_request': copy.deepcopy(request), 'native_response': ack,
            'boundary': ref(boundary_ref), 'monotonic_ns': monotonic_ns, 'scope': self.scope, 'phase': self.phase}
        ack_ref = ref(self.emit('video-' + item['action'] + '-native-ack', value))
        item['native_ack'], item['ack_monotonic_ns'] = ack_ref, monotonic_ns
        if item['action'] == 'start':
            self.start_ack = ack_ref
        elif item['action'] == 'stop':
            self.stop_ack = ack_ref

    def dispatch_return(self, value):
        need(self.pending is not None, 'VIDEO_RETURN_WITHOUT_ONCE_CLAIM')
        self.pending['dispatch_returned'] = True
        # An ACK followed by screenshot failure retains the pending effect.
        # Only a new read observation can prove it. Never replay the input.
        need(type(value) is dict and value.get('ok') is True
            and value.get('outcome_unknown') is not True and self.pending['native_ack'] is not None,
            'VIDEO_DISPATCH_UNKNOWN_KEEP_ONCE_INTENT')
        if self.pending['action'] in ('mode_menu', 'restore_menu'):
            # The next native dump must supply the actual desired mode item;
            # no claim about menu visibility is derived from the click ACK.
            next_state = 'MODE_MENU' if self.pending['action'] == 'mode_menu' else 'RESTORE_MENU'
            self._complete(next_state, {'native_ack_only': True})

    def _complete(self, state, evidence):
        item = self.pending
        need(item is not None and item['native_ack'] is not None, 'REAL_NATIVE_ACK_BEFORE_EFFECT_COMPLETION')
        value = {'intent': item['intent_ref'], 'native_ack': item['native_ack'],
                 'effect_readback': copy.deepcopy(evidence), 'next_state': state,
                 'scope': self.scope, 'phase': self.phase, 'automatic_retry': False}
        self.emit('video-' + item['action'] + '-effect', value)
        self.actions.append(copy.deepcopy(item)); self.pending = None; self.state = state

    def saved(self, row, row_ref, decode, decode_ref):
        need(self.state == 'STOPPED_UNSAVED' and self.pending is None and self.start_ack and self.stop_ack,
             'OWNED_RECORDING_AND_STOP_MUST_PRECEDE_SAVED_VIDEO')
        need(row['is_pending'] == 0 and row['owner_package_name'] == PACKAGE
            and decode.get('full_video_decode') is True and decode.get('full_audio_decode') is True
            and decode.get('file_sha256') == row['file_sha256'] and decode.get('file_bytes') == row['_size']
            and decode.get('uri') == row['uri'] and decode.get('nonce') == self.nonce,
            'ACTUAL_FINAL_MEDIA_ROW_AND_FULL_OWNED_CLIP_DECODE')
        self.media = {'row': copy.deepcopy(row), 'row_ref': ref(row_ref),
                      'decode': ref(decode_ref), 'decode_result': copy.deepcopy(decode)}
        self.emit('video-owned-saved', self.media); self.state = 'SAVED'

    def audio_and_playback(self, *, audio_ref, audio, playback_ref, playback):
        need(self.state in ('SAVED', 'MODE_RESTORED') and self.pending is None and self.media is not None,
             'SAVED_OWNED_CLIP_REQUIRED_FOR_AUDIO_AND_PLAYBACK')
        for value in (audio, playback):
            need(value.get('nonce') == self.nonce and value.get('epoch_sha256') == self.epoch_sha256
                and value.get('uri') == self.media['row']['uri']
                and value.get('file_sha256') == self.media['row']['file_sha256']
                and value.get('scope') == self.scope and value.get('phase') == self.phase
                and value.get('outcome_unknown') is False, 'AUDIO_PLAYBACK_MUST_BE_THIS_FRESH_RECORDING')
        need(audio.get('decoded_own_audio_nonce_match') is True
            and audio.get('CAMCORDER_uid') == 10062 and audio.get('actual_HAL_input_session_bound') is True
            and audio.get('actual_physical_source_bound') is True
            and audio.get('baseline_negative_passed') is True and audio.get('decoy_negative_passed') is True,
            'NONZERO_PCM_OR_OLD_HOST_CHALLENGE_IS_NOT_CAMERA_AUDIO')
        need(playback.get('actual_owned_uri_intent') is True and playback.get('actual_video_decoder_outputs_advanced') is True
            and playback.get('two_current_foreground_pixel_observations') is True
            and playback.get('physical_presented_frame_claim') is False
            and playback.get('actual_Android_output_session_bound') is True
            and playback.get('physical_playback_nonce_match') is True
            and playback.get('owned_player_closed') is True and playback.get('foreign_tasks_unchanged') is True,
            'SAME_OWNED_URI_VIDEO_AND_PHYSICAL_PLAYBACK_REQUIRED')
        self.audio, self.playback = ref(audio_ref), ref(playback_ref)
        self.emit('video-audio-and-playback', {'audio': self.audio, 'playback': self.playback})
        self.state = 'PLAYBACK_VERIFIED'

    def terminal(self, *, final_mode, task_closed, preserved_state, host_retired):
        # Restoring Photo after verified playback moves the state to MODE_RESTORED.
        # The audio/playback receipts below still gate success in either order.
        restored = (self.state in ('PLAYBACK_VERIFIED', 'MODE_RESTORED') and
                    (self.initial_mode == '1' or self.initial_mode == '0' and self.mode_restored))
        complete = bool(restored and final_mode == self.initial_mode and task_closed is True
            and preserved_state is True and host_retired is True and self.pending is None
            and self.media is not None and self.audio is not None and self.playback is not None)
        return {'state': 'CAMERA_VIDEO_RECORD_AUDIO_PLAYBACK_VERIFIED' if complete else 'FAILED_OR_UNKNOWN_RETAINED',
            'camera_video_verified': complete, 'outcome_unknown': self.pending is not None,
            'pending': copy.deepcopy(self.pending), 'attempted': sorted(self.attempted),
            'nonce': self.nonce, 'scope': self.scope, 'phase': self.phase, 'epoch_sha256': self.epoch_sha256,
            'original_mode': self.initial_mode, 'final_mode': final_mode, 'owned_task_closed': task_closed,
            'preserved_state': preserved_state, 'host_retired': host_retired,
            'automatic_retry': False, 'camera_recovery_qualified': False,
            'whole_app_business_accepted': False}
