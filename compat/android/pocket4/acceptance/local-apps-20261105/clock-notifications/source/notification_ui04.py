#!/usr/bin/python3 -I
"""One Clock-specific notification switch, through an owned Settings task.

Preparation only until the actual ActivityManager --task proof is pinned.
No alarm, timer, default ringtone, volume, or other App setting is changed.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, signal, time, types

HERE = Path(__file__).resolve().parent
CONTACT = Path('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01')
ROOT = Path('/home/alex/work/pocket4-clock-notification-ui-20261105-r12-04')
SETTINGS = 'com.android.settings'
CLOCK = 'com.android.deskclock'
COMPONENT = SETTINGS + '/.Settings$AppNotificationSettingsActivity'
ACTIVITY = SETTINGS + '.Settings$AppNotificationSettingsActivity'
TASK_PROOF = HERE / 'task-option-proof.json'
TASK_PROOF_SHA = '9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'
PINS = {
    'base': (str(CONTACT / 'ui_preflight04.py'), 'd02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58'),
    'model': (str(HERE / 'read_clock.py'), 'fd3ffdfbb397b561bf251236c117966ea18b2ca176e4908c6a31ad0db4cc0048'),
    'shared': (str(HERE / 'stopwatch02.py'), 'cab5252688463cd0527a3d8e4cb8d9e2b9d498d2cdd3016beda274ba16283cab'),
    'timer': (str(HERE / 'read_timer.py'), 'c3bf02f38e05ab7a55285ca2245ffe2bda3eb528cc1f85d54723294047948b08'),
    'permission': (str(HERE / 'notification_preflight01.py'), '88798eca424590435cc06ff51ebbdbabbd438b1b5339ce959bd2d069f4572fb6'),
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def load(path, expected):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'NOTIFICATION_SOURCE_CHANGED')
    result = types.ModuleType('clock_notification_' + Path(path).stem)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def component(raw):
    # Actual --brief includes a priority metadata line before the component.
    matches = [line.strip() for line in raw.splitlines()
               if re.fullmatch(r'[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+', line.strip())]
    require(len(matches) == 1, 'RESOLVED_COMPONENT_NOT_UNIQUE')
    return matches[0]


def parse_appop(raw):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    matches = [re.fullmatch(r'(?:Uid mode: )?POST_NOTIFICATION: ([a-z_]+)(?:;[^\n]*)?', line)
               for line in lines]
    modes = [match[1] for match in matches if match is not None]
    explicit = len(lines) in (1, 2) and len(modes) == len(lines) and all(mode == 'allow' for mode in modes)
    # The service reports its actual default when no operation is stored. Do
    # not infer a default from absence, or from a bare MODE_DEFAULT record.
    reported_allow = lines == ['No operations.', 'Default mode: allow']
    return {'raw': raw, 'observed_modes': modes, 'allow_verified': explicit or reported_allow,
            'evidence_kind': 'explicit_allow' if explicit else 'service_reported_default_allow' if reported_allow else 'not_verified'}


def selected_switch(nodes):
    visible = [n for n in nodes if n.get('package') == SETTINGS
               and n.get('visible') is True and n.get('enabled') is True]
    # Actual trial03 exposes the App name as these two content descriptions,
    # with no TextView whose text is Clock. Bind both exact observed roles.
    bars = [n for n in visible if n.get('resource-id') == SETTINGS + ':id/collapsing_toolbar'
            and n.get('class') == 'android.widget.FrameLayout' and n.get('content-desc') == 'Clock']
    icons = [n for n in visible if n.get('resource-id') == SETTINGS + ':id/entity_header_icon'
             and n.get('class') == 'android.widget.ImageView' and n.get('content-desc') == 'Clock']
    require(len(bars) == len(icons) == 1 and type(bars[0].get('window_id')) is int
            and bars[0]['window_id'] == icons[0].get('window_id'), 'ACTUAL_CLOCK_APP_HEADER_REQUIRED')
    labels = [n for n in visible if n.get('resource-id') == SETTINGS + ':id/switch_text'
              and n.get('class') == 'android.widget.TextView' and n.get('text') == 'All Clock notifications'
              and n.get('window_id') == bars[0]['window_id']]
    require(len(labels) == 1, 'ONE_EXPLICIT_APP_NOTIFICATION_LABEL_REQUIRED')
    label = labels[0]
    # The actual native node schema exposes checked, not checkable. The concrete
    # Switch class and its observed false state supply this specific predicate.
    switches = [n for n in visible if n.get('class') in ('android.widget.Switch', 'androidx.appcompat.widget.SwitchCompat')
                and n.get('checked') is False
                and type(n.get('clickable')) is bool and n.get('editable') is False and n.get('password') is False
                and n.get('window_id') == label.get('window_id')]
    require(len(switches) == 1, 'ONE_ACTUAL_UNCHECKED_NOTIFICATION_SWITCH_REQUIRED')
    switch = switches[0]
    bounds = switch.get('bounds_array')
    require(type(switch.get('window_id')) is int and isinstance(bounds, list) and len(bounds) == 4
            and all(type(x) is int for x in bounds) and bounds[0] < bounds[2] and bounds[1] < bounds[3],
            'NOTIFICATION_SWITCH_BOUNDS_UNKNOWN')
    # A unique notification label and a sole switch must share the same row.
    lb = label.get('bounds_array')
    require(isinstance(lb, list) and len(lb) == 4 and all(type(x) is int for x in lb)
            and max(lb[1], bounds[1]) < min(lb[3], bounds[3]), 'NOTIFICATION_LABEL_ROW_MISMATCH')
    binding = {'header': {'toolbar': bars[0], 'icon': icons[0]}, 'label': label,
               'switch': switch, 'tap_node': switch, 'clickable_container': None}
    if switch.get('clickable') is not True:
        # A visually explicit main Switch may delegate touches to its real
        # parent. Keep the child's actual clickable=false value in evidence.
        def contains(outer, inner):
            return (isinstance(outer, list) and len(outer) == 4
                and all(type(x) is int for x in outer)
                and outer[0] <= inner[0] < inner[2] <= outer[2]
                and outer[1] <= inner[1] < inner[3] <= outer[3])
        containers = [n for n in visible if n.get('window_id') == switch['window_id']
            and n.get('clickable') is True and n.get('editable') is False and n.get('password') is False
            and n.get('bounds_array') != bounds and n.get('bounds_array') != lb
            and contains(n.get('bounds_array'), bounds) and contains(n.get('bounds_array'), lb)]
        inner = [n for n in containers if not any(n is not other
            and n['bounds_array'] != other['bounds_array']
            and contains(n['bounds_array'], other['bounds_array']) for other in containers)]
        require(len(inner) == 1 and all(n is inner[0] or n['bounds_array'] != inner[0]['bounds_array']
            and contains(n['bounds_array'], inner[0]['bounds_array']) for n in containers),
            'UNIQUE_INNER_NOTIFICATION_SWITCH_CONTAINER_REQUIRED')
        binding.update(tap_node=label, clickable_container=inner[0])
    return binding


def stable_binding(value):
    # Native IDs are scoped to each accessibility connection. Within every
    # observation selected_switch requires one consistent native window; across
    # observations the actual WM token/frame/scope/context remain mandatory.
    if isinstance(value, dict):
        return {k: stable_binding(v) for k, v in value.items() if k != 'window_id'}
    if isinstance(value, list):
        return [stable_binding(v) for v in value]
    return value


def expired(signum, frame):
    raise TimeoutError('NOTIFICATION_UI_LEASE_EXPIRED_NO_REPLAY')


def execute():
    require(re.fullmatch('[0-9a-f]{64}', TASK_PROOF_SHA), 'TASK_OPTION_PROOF_NOT_REVIEWED')
    require(hashlib.sha256(TASK_PROOF.read_bytes()).hexdigest() == TASK_PROOF_SHA, 'TASK_OPTION_PROOF_CHANGED')
    modules = {name: load(*pin) for name, pin in PINS.items()}
    base, model, shared, timer, permissions = [modules[x] for x in ('base', 'model', 'shared', 'timer', 'permission')]
    tx = model.load_session()
    base.PACKAGE, base.ROOT = SETTINGS, ROOT
    result = {'state': 'FAILED', 'whole_app_production_ready': False, 'automatic_retry': False,
              'permission_change_verified': False, 'setting_inputs': 0, 'intent_calls': 0,
              'alarm_timer_writes': 0, 'global_sound_writes': 0, 'pending_effect': None,
              'source_pins': PINS, 'task_option_proof_sha256': TASK_PROOF_SHA,
              'started_utc': datetime.now(timezone.utc).isoformat()}
    trial = None
    previous = signal.signal(signal.SIGALRM, expired)
    try:
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            signal.setitimer(signal.ITIMER_REAL, 180)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = base.Trial(session, tx)
                def permission(label):
                    value = permissions.permission(session.android(['/system/bin/dumpsys', 'package', CLOCK]).decode())
                    trial.record(label, value)
                    return value
                def appop(label):
                    raw = session.android(['/system/bin/cmd', 'appops', 'get', '--user', '0', CLOCK, 'POST_NOTIFICATION']).decode()
                    value = parse_appop(raw)
                    trial.record(label, value)
                    return value
                def observe(label):
                    focus = trial.ready_focus(False)
                    require(focus['package'] == SETTINGS and focus['activity'] == ACTIVITY
                            and focus['focused_activity'] in (ACTIVITY, '.Settings$AppNotificationSettingsActivity'),
                            'EXACT_CLOCK_NOTIFICATION_ACTIVITY_REQUIRED')
                    nodes = trial.observe(label, focus)
                    require(trial.last_observation['screenshot']['scope']['activity'] == ACTIVITY,
                            'NOTIFICATION_SCREENSHOT_ACTIVITY_CHANGED')
                    return focus, nodes
                try:
                    result['identity_before'] = model.identity(session)
                    result['alarms_before'] = model.state(session)
                    model.verify_before(result['alarms_before'])
                    result['alarm_sha_before'] = shared.alarm_fingerprint(session, model)
                    require(result['alarm_sha_before'] == '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea',
                            'ORIGINAL_ALARM_CONTENTS_CHANGED')
                    result['timers_before'] = timer.read(session); timer.empty(result['timers_before'])
                    before = permission('permission-before'); result['permission_before'] = before
                    result['appop_before'] = appop('clock-appop-before')
                    require(before['granted'] is False and before['observed_user_decision_flag'] is False
                            and before['policy_fixed'] is False, 'ONLY_UNCONFIGURED_CLOCK_NOTIFICATIONS_ALLOWED')
                    raw = session.android(['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
                        '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', SETTINGS]).decode()
                    base.COMPONENT = component(raw)
                    require(base.COMPONENT.split('/')[0] == SETTINGS, 'SETTINGS_LAUNCHER_RESOLVED_ELSEWHERE')
                    trial.record('actual-settings-launcher', {'raw': raw, 'component': base.COMPONENT})
                    result['pending_effect'] = 'native-settings-launch'
                    trial.launch(); result['owned_task'] = trial.owned[0]
                    trial.observe('owned-settings-main', trial.ready_focus(False))
                    result['pending_effect'] = None
                    task = trial.owned[0]
                    argv = ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0', '--task', str(task),
                            '--activity-clear-top', '-a', 'android.settings.APP_NOTIFICATION_SETTINGS', '-n', COMPONENT,
                            '--es', 'android.provider.extra.APP_PACKAGE', CLOCK, '--ei', 'app_uid', '10063']
                    trial.ready_focus(False)
                    trial.record('clock-notification-intent', {'argv': argv, 'owned_task': task, 'automatic_retry': False})
                    result['pending_effect'] = 'exact-clock-settings-intent'; result['intent_calls'] += 1
                    raw = session.android(argv, 35).decode()
                    trial.record('clock-notification-intent-response', {'stdout': raw})
                    require(re.findall(r'^Status:\s*(\S+)', raw, re.M) == ['ok']
                            and 'Error:' not in raw and 'Exception' not in raw, 'NOTIFICATION_INTENT_OUTCOME_UNKNOWN')
                    focus, nodes = observe('actual-clock-notifications')
                    result['pending_effect'] = None
                    binding = selected_switch(nodes)
                    oldshot = trial.last_observation['screenshot']
                    second, fresh = observe('fresh-clock-notifications')
                    require(second == focus and stable_binding(selected_switch(fresh)) == stable_binding(binding),
                            'OBSERVED_NOTIFICATION_SWITCH_CHANGED')
                    shot = trial.last_observation['screenshot']
                    require(all(shot[k] == oldshot[k] for k in ('frame_sha256', 'scope_sha256', 'context_token')),
                            'NOTIFICATION_SNAPSHOT_CHANGED')
                    require(permission('permission-immediately-before-input') == before,
                            'NOTIFICATION_PERMISSION_CHANGED_BEFORE_INPUT')
                    require(trial.ready_focus(False) == focus, 'NOTIFICATION_FOCUS_CHANGED_BEFORE_INPUT')
                    box = binding['tap_node']['bounds_array']
                    request = {'op': 'snapshot-tap', 'package': SETTINGS, 'display': 0, 'accessibility_mode': 'none',
                        'input_source': 'touch', 'window_token': focus['window_token'],
                        'coords': [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2],
                        **{k: shot[k] for k in ('frame_sha256', 'scope_sha256', 'context_token')}}
                    trial.record('one-clock-notification-switch-intent', {'request': request, 'binding': binding,
                        'target_package': CLOCK, 'target_uid': 10063, 'owned_task': task, 'automatic_retry': False})
                    result['pending_effect'] = 'clock-notification-switch'; result['setting_inputs'] += 1
                    session.guard(); response = session.helper.dispatch(request); session.guard()
                    trial.record('one-clock-notification-switch-response', response)
                    result['original_switch_response'] = response
                    require(response.get('ok') is True and response.get('performed') == 'snapshot-tap'
                            and response.get('input_command_completed') is True, 'NOTIFICATION_INPUT_OUTCOME_UNKNOWN')
                    # Original post-capture unknown remains in the receipt. The permission
                    # readback is a separate result and never authorizes a second tap.
                    for attempt in range(3):
                        after = permission('permission-after-input-%d' % attempt)
                        if after['granted']:
                            break
                        time.sleep(.25)
                    require(after['granted'] is True and after['policy_fixed'] is False,
                            'CLOCK_NOTIFICATION_ENABLE_NOT_READ_BACK')
                    result['permission_after'] = after
                    result['appop_after'] = appop('clock-appop-after')
                    require(result['appop_after']['allow_verified'] is True,
                            'ACTUAL_CLOCK_NOTIFICATION_APPOP_ALLOW_NOT_VERIFIED')
                    result['pending_effect'] = None
                    result['permission_change_verified'] = True
                    result['state'] = 'CLOCK_NOTIFICATION_ENABLED_VIA_EXACT_OWNED_SETTINGS_UI'
                except BaseException as exc:
                    result.update(state='FAILED', error=type(exc).__name__ + ': ' + str(exc))
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 35)
                    try:
                        trial.close()
                    except BaseException as exc:
                        result.update(state='FAILED', close_error=type(exc).__name__ + ': ' + str(exc))
                    result['permission_current'] = permission('permission-final-read-only')
                    result['appop_current'] = appop('clock-appop-final-read-only')
                    result['identity_after'] = model.identity(session)
                    result['alarms_after'] = model.state(session)
                    result['alarm_sha_after'] = shared.alarm_fingerprint(session, model)
                    result['timers_after'] = timer.read(session)
                    require(result.get('alarms_before') == result['alarms_after']
                            and result.get('alarm_sha_before') == result['alarm_sha_after']
                            and result.get('timers_before') == result['timers_after'], 'CLOCK_DATA_CHANGED_DURING_NOTIFICATION_UI')
                    expected_identity = dict(result['identity_before'], notifications_granted=result['permission_current']['granted'])
                    require(result['identity_after'] == expected_identity, 'CLOCK_APK_UID_OR_VERSION_CHANGED')
                    session.caller_status('clock-notifications-final-caller')
                    if result['permission_change_verified']:
                        require(trial.removals == 1 and trial.result.get('other_tasks_preserved') is True
                                and result['pending_effect'] is None, 'NOTIFICATION_SUCCESS_REQUIRES_NORMAL_OWNED_CLOSE')
    except BaseException as exc:
        result.update(state='FAILED', terminal_error=type(exc).__name__ + ': ' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        result.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                      native_launch_calls=trial.launches if trial else 0,
                      owned_task_remove_calls=trial.removals if trial else 0)
        if ROOT.is_dir():
            tx.write_new(ROOT / 'result.json', result)
        tx.write_new(HERE / 'clock-notification-ui04-result.json', result, alex_readable=True)
        print(json.dumps({k: result.get(k) for k in ('state', 'error', 'terminal_error', 'setting_inputs', 'pending_effect')}))
    return 0 if result['state'] == 'CLOCK_NOTIFICATION_ENABLED_VIA_EXACT_OWNED_SETTINGS_UI' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if parser.parse_args().execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'INERT', 'task_proof_pinned': True, 'UI_actions': 0,
                      'permission_writes': 0, 'whole_app_production_ready': False}))
