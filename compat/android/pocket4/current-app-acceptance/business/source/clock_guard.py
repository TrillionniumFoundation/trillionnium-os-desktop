"""Complete new-Main Clock guard and typed UI boundary contract.

Historical activation/Flow objects are never loaded. The original timer state
machine supplies an immutable semantic intent; native ACKs remain separate
from post-action capture. This guard sends no Android commands.
"""
import atexit
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

PACKAGE = 'com.android.deskclock'
_ENTRIES = {}


def prepare(*, runtime):
    runtime.case_runtime = runtime.c.packet_module(runtime.scope, 'app_runtime.py')
    runtime.case_runtime.prepare(runtime)
    runtime.c.need(runtime.plan['kind'] == 'clock_timer' and runtime.plan['protected_before'] is not None,
                   'ORIGINAL_CLOCK_PROTECTED_PREIMAGE_REQUIRED')
    protected = runtime.c.parse(runtime.c.read_ref(runtime.plan['protected_before']))
    preservation = runtime.c.packet_module(runtime.scope, 'clock_preservation.py')
    validate_protected(runtime.c, protected, preservation, runtime.plan)


def validate_protected(common, value, preservation, plan):
    common.need(value['package'] == PACKAGE and value['epoch_sha256'] == plan['framework_epoch_sha256']
        and value['timer_and_stopwatch_empty'] is True and value['notification_appop_allow'] is True
        and value['alarm_content_sha256'] == preservation.ALARM_SHA
        and value['apk']['bytes'] == 7597225 and value['apk']['sha256'] == plan['target_profile']['apks'][0]['sha256'],
        'ACTUAL_ORIGINAL_CLOCK_PROTECTION_PREIMAGE_REQUIRED')
    preservation.verify_before(value['alarm_state'])
    common.need(preservation.baseline_ids(value['alarm_state']) == {1, 2}, 'ORIGINAL_TWO_ALARM_TEMPLATES_REQUIRED')
    identity = value['identity']
    common.need(identity['uid'] == 10063 and identity['version'] == 37,
                'ORIGINAL_CLOCK_IDENTITY_REQUIRED')
    for label in ('ce', 'de'):
        directory = value['directories'][label]
        common.need(directory['uid'] == directory['gid'] == 10063 and
                    directory['inode'] == identity[label + '_inode'], 'ORIGINAL_CLOCK_DATA_IDENTITY_REQUIRED')


def full_guard(*, attempted=False, runtime):
    return runtime.case_runtime.full(runtime, attempted)


def verify_focus(runtime, ref, selected):
    c = runtime.c; value = c.parse(c.read_ref(ref))
    c.need(set(value) == {'schema', 'scope_sha256', 'phase_lease', 'focus', 'reads', 'stacks'}
        and value['schema'] == 'pocket4-final-clock-focus-v1'
        and value['scope_sha256'] == runtime.scope_ref['sha256'] and
        value['phase_lease'] == runtime.phase_lease_ref and len(value['reads']) == 2,
        'TWO_ACTUAL_IDENTICAL_OWNED_FOCUS_READS_REQUIRED')
    parser = c.packet_module(runtime.scope, 'clock_focus.py')
    raw = [runtime.case_runtime.verify_read(c, row, c.FOREGROUND,
           runtime.scope['business_baseline'], runtime.scope['business_qualification']) for row in value['reads']]
    parsed = [parser.focus_metadata(x.decode('utf-8', 'strict')) for x in raw]
    focus = value['focus']
    c.need(parsed[0] == parsed[1] == focus and focus.get('verified') is True
        and focus.get('task') == selected['task'] and focus.get('package') == PACKAGE
        and focus.get('activity') == PACKAGE + '.DeskClock'
        and focus.get('focused_activity') in (PACKAGE + '.DeskClock', '.DeskClock')
        and focus.get('user') == 0, 'ACTUAL_CLOCK_FOCUS_OR_OWNED_TASK_CHANGED')
    stacks = runtime.case_runtime.verify_read(c, value['stacks'], c.STACKS,
        runtime.scope['business_baseline'], runtime.scope['business_qualification'])
    roots, tasks = runtime.tasks.parse_stacks(stacks.decode('utf-8', 'strict'))
    c.need(runtime.tasks.exact_leaf(roots, selected['task'], PACKAGE) and
        tasks == set(selected['prelaunch_task_ids']) | {selected['task']}, 'ACTUAL_OTHER_TASK_SET_CHANGED')
    return focus


def verify_observation(runtime, ref, selected):
    c = runtime.c; value = c.parse(c.read_ref(ref))
    c.need(set(value) == {'schema', 'scope_sha256', 'focus', 'result', 'png', 'label'}
        and value['schema'] == 'pocket4-final-clock-observation-v1'
        and value['scope_sha256'] == runtime.scope_ref['sha256']
        and Path(value['result']['path']).parent.parent == Path(runtime.scope['flow_root']) / 'steps',
        'ACTUAL_CURRENT_FLOW_OBSERVATION_REQUIRED')
    focus = verify_focus(runtime, value['focus'], selected)
    result = c.parse(c.read_ref(value['result'])); native = result.get('native', result)
    verify_ui_return(runtime, Path(value['result']['path']).parent, result)
    c.need(result.get('ok') is True and result.get('outcome_unknown') is not True
        and native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True,
        'ORIGINAL_OBSERVATION_AND_RESTORATION_REQUIRED')
    window = result['screenshot']['scope']
    c.need(window['package'] == focus['package'] and window['window_token'] == focus['window_token']
        and window['activity'] == PACKAGE + '.DeskClock' and window['display_id'] == 0,
        'OBSERVATION_WINDOW_DOES_NOT_MATCH_ACTUAL_FOCUS')
    # PNG is a separate bounded file; it never crosses the public 16 MiB pipe.
    c.need(c.regular(value['png']['path'], 32 * 1024 * 1024, contents=False) == value['png'],
        'ACTUAL_OBSERVATION_PNG_CHANGED')
    c.need(type(native.get('nodes')) is list, 'ACTUAL_NATIVE_NODES_REQUIRED')
    return value, result, native['nodes']


def verify_ui_return(runtime, step, value):
    c = runtime.c
    actual = c.parse(c.regular(step / 'command-001.result.json')[0])
    logical = c.parse(c.regular(step / 'command-001.logical.json')[0])
    c.need(actual['host_retirement_proved'] is True and actual['evidence_complete'] is True
        and actual['returncode'] == 0 and actual['timed_out'] is False and actual['errors'] == []
        and actual.get('first_error') is None and logical['scope_sha256'] == runtime.scope_ref['sha256']
        and logical['automatic_retry'] is False and
        actual['argv'] == runtime.modules['business_ui_entry.py'].entry_argv(runtime.scope_ref, 'client',
            step.name, 'command-001', logical['argv'][1:]) and
        c.parse(c.read_ref(actual['stdout'])) == value, 'ACTUAL_TYPED_UI_PARENT_RESULT_CHAIN_REQUIRED')
    c.read_ref(actual['stderr'])
    return actual


def validate_ui_context(runtime, request, context, *, step=None):
    c = runtime.c
    fields = {'schema', 'phase_lease', 'focus', 'owned_claim', 'observation',
              'previous_observation', 'action_claim', 'action_lock_grant'}
    c.need(type(context) is dict and set(context) == fields and
        context['schema'] == 'pocket4-final-clock-ui-context-v1' and
        context['phase_lease'] == runtime.phase_lease_ref, 'EXACT_FRESH_CLOCK_UI_CONTEXT_REQUIRED')
    phase = runtime.case_runtime.validate_phase(c, context['phase_lease'], runtime.scope['phase_plan'], runtime.plan)
    grant = c.parse(c.read_ref(context['action_lock_grant']))
    c.need(grant['action_lock'] == runtime.plan['action_lock'] and grant['scope'] == runtime.scope_ref
        and grant['phase_lease'] == runtime.phase_lease_ref and
        (step is None or grant['step'] == str(step)) and grant['automatic_retry'] is False,
        'UI_REQUIRES_ONCE_ONLY_WHOLE_CASE_LOCK_GRANT')
    selected, actual_ref = runtime.scope_module.load_owned_task(runtime.bound)
    c.need(actual_ref == context['owned_claim'], 'UI_NOT_BOUND_TO_ACTUAL_NEW_TASK_CLAIM')
    focus = verify_focus(runtime, context['focus'], selected)
    if request['op'] == 'observe':
        c.need(context['observation'] is context['previous_observation'] is context['action_claim'] is None,
            'CLOCK_OBSERVE_MUST_NOT_CONTAIN_ACTION_AUTHORITY')
        return focus
    c.need(request['op'] == 'click' and request['method'] == 'accessibility'
        and request['accessibility_mode'] == 'none', 'ORIGINAL_TIMER_NATIVE_CLICK_ONLY')
    previous, previous_result, old_nodes = verify_observation(runtime, context['previous_observation'], selected)
    current, current_result, fresh_nodes = verify_observation(runtime, context['observation'], selected)
    c.need(current != previous and current_result['screenshot']['scope']['window_token'] ==
        previous_result['screenshot']['scope']['window_token'] == focus['window_token'],
        'ORIGINAL_FRESH_OBSERVATION_SAME_WINDOW_REQUIRED')
    claim = c.parse(c.read_ref(context['action_claim']))
    c.need(set(claim) == {'schema', 'scope_sha256', 'ui_step', 'number', 'id', 'request', 'intent',
                         'observation', 'previous_observation', 'automatic_retry'} and
        claim['schema'] == 'pocket4-final-clock-action-claim-v1' and
        claim['scope_sha256'] == runtime.scope_ref['sha256'] and claim['automatic_retry'] is False and
        type(claim['number']) is int and 1 <= claim['number'] <= 20 and
        claim['observation'] == context['observation'] and
        claim['previous_observation'] == context['previous_observation'] and
        (step is None or claim['ui_step'] == str(step)), 'ONCE_ONLY_ORIGINAL_TIMER_ACTION_CLAIM_REQUIRED')
    match = re.fullmatch(r't([0-9]{2})-(timer-tab|reopen-timer-tab|digit-[015]|create-start|pause|pause-again|resume|reset|delete|cleanup-pause|cleanup-delete)', claim['id'])
    c.need(match is not None and int(match[1]) == claim['number'] and
        Path(context['action_claim']['path']) == Path(runtime.plan['case_root']) / 'action-claims' / (claim['id'] + '.json'),
        'ORIGINAL_TIMER_ACTION_ID_AND_GLOBAL_TWENTY_INPUT_BOUND')
    if phase['phase'] == 'final_cleanup':
        c.need(match[2] in ('cleanup-pause', 'cleanup-delete'), 'ONLY_ORIGINAL_KNOWN_TIMER_FAILURE_CLEANUP_INPUT')
    original_request = c.parse(c.read_ref(claim['request']))
    intent = c.parse(c.read_ref(claim['intent']))
    c.need(original_request.get('id') == claim['id'] and original_request.get('op') == 'click'
        and original_request.get('observation') == previous['label'], 'ORIGINAL_CONTINUATION_REQUEST_CHANGED')
    selector = original_request['selector']; selectors = c.packet_module(runtime.scope, 'clock_selectors.py')
    old = selectors.candidates(old_nodes, selector, PACKAGE)
    fresh = selectors.candidates(fresh_nodes, selector, PACKAGE)
    c.need(len(old) == len(fresh) == 1 and
        selectors.node_identity(old[0]) == selectors.node_identity(fresh[0]) and
        old[0] == intent['node'] and old[0].get('clickable') is True and
        old[0].get('editable') is False and old[0].get('password') is False,
        'ORIGINAL_OBSERVED_UNIQUE_TIMER_NODE_CHANGED')
    command = {'op': 'click', 'package': PACKAGE, 'window_token': focus['window_token'], 'display': 0,
        'accessibility_mode': 'none', 'method': 'accessibility',
        'selector': dict(selector, package=PACKAGE, enabled=True, clickable=True)}
    c.need(intent['command'] == command and intent['automatic_retry'] is False
        and intent['observed_label_clickable_container'] is None and intent['owned_contact_list_binding'] is None
        and request == {k: command[k] for k in ('op', 'selector', 'accessibility_mode', 'method')},
        'EXACT_ORIGINAL_CONTINUATION_TO_TYPED_CLI_REQUEST_REQUIRED')
    return focus


def _read_source(ref, maximum=2 * 1024 * 1024):
    fd = os.open(ref['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
            raise RuntimeError('BOUNDED_NEW_ENTRY_SOURCE_REQUIRED')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(maximum + 1)
        fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        last = os.fstat(fd); named = Path(ref['path']).lstat()
        if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256'] or not all(
                getattr(before, k) == getattr(last, k) == getattr(named, k) for k in fields):
            raise RuntimeError('NEW_ENTRY_SOURCE_CHANGED')
        return raw
    finally:
        os.close(fd)


def _entry(entry_context):
    key = entry_context['step']
    if key in _ENTRIES:
        runtime = _ENTRIES[key]
        runtime.c.need(runtime.entry_context == entry_context, 'ENTRY_CONTEXT_CHANGED')
        return runtime
    value = entry_context['scope']; packet = json.loads(_read_source(value['task_source_manifest']))
    rows = [r for r in packet['files'] if Path(r['path']).name == 'app_common.py']
    if len(rows) != 1:
        raise RuntimeError('ONE_NEW_APP_COMMON_SOURCE_REQUIRED')
    ref = rows[0]; common = types.ModuleType('fresh_clock_entry_common'); common.__file__ = ref['path']
    exec(compile(_read_source(ref), ref['path'], 'exec'), common.__dict__)
    common.read_ref(value['task_source_manifest']); scope_module, modules = common.support(value['support_manifest'])
    plan = common.parse(common.read_ref(value['phase_plan']))
    intent = common.parse(common.regular(Path(key) / 'intent.json')[0]); context = intent['case_context']
    runtime_module = common.packet_module(value, 'app_runtime.py')
    phase = runtime_module.validate_phase(common, context['phase_lease'], value['phase_plan'], plan)
    # No command can use this held view. Its descriptors only protect actual
    # package bytes and Main identity while the typed entry sends its own calls.
    def reject(*args):
        raise RuntimeError('GUARD_VIEW_CANNOT_SEND_ANDROID_COMMANDS')
    journal = common.private_dir(Path(key))
    view = common.MainView(value['business_baseline'], value['business_qualification'], journal, reject,
                           support_ref=value['support_manifest'])
    runtime = types.SimpleNamespace(c=common, scope=value, scope_ref=entry_context['scope_ref'],
        scope_module=scope_module, modules=modules, view=view, plan=plan, root=Path(value['flow_root']),
        phase='inspect', deadline=phase['deadline_monotonic_ns'] / 1000000000,
        private_context={'phase_lease': context['phase_lease']}, receipt_witness=None, artifacts=None,
        tasks=scope_module.task_functions(), entry_context=entry_context, ui_intent=intent)
    runtime.bound = types.SimpleNamespace(scope=value, scope_ref=runtime.scope_ref, root=runtime.root,
        baseline=view.baseline, commands=modules['business_commands.py'])
    def close():
        try:
            if runtime.receipt_witness is not None:
                runtime.receipt_witness.close()
        finally:
            try:
                if runtime.artifacts is not None:
                    runtime.artifacts.close()
            finally:
                view.close()
    try:
        identities = [common.parse(common.read_ref(value['actual_resolution_receipt']))] + [
            common.parse(common.read_ref(r)) for r in value['installed_helper_receipts']]
        runtime.artifacts = common.HeldArtifacts(view.target, identities)
        prepare(runtime=runtime)
        _ENTRIES[key] = runtime; atexit.register(close)
        return runtime
    except BaseException:
        close()
        raise


def existing_ui_guard(*, attempted=False, entry_context):
    runtime = _entry(entry_context)
    runtime.view.guard(action_attempted=attempted)
    full_guard(attempted=attempted, runtime=runtime)
    request = runtime.ui_intent['request']
    runtime.c.need(entry_context['operation'] == request['op'] and
        entry_context['mutation'] is (request['op'] == 'click'), 'CLOCK_ENTRY_OPERATION_CHANGED')
    validate_ui_context(runtime, request, runtime.ui_intent['case_context'], step=Path(entry_context['step']))


def ui_boundary_contract(*, entry_context):
    runtime = _entry(entry_context)
    context = runtime.ui_intent['case_context']
    focus = validate_ui_context(runtime, runtime.ui_intent['request'], context, step=Path(entry_context['step']))
    return {'scope_sha256': runtime.scope_ref['sha256'],
        'observation': context['observation'] if entry_context['operation'] == 'click' else context['focus'],
        'observed_window': {k: focus[k] for k in ('package', 'activity', 'window_token')} | {'display_id': 0}}


def acquire_action_lock(*, entry_context):
    runtime = _entry(entry_context)
    existing_ui_guard(entry_context=entry_context)
    context = runtime.ui_intent['case_context']
    module = runtime.c.packet_module(runtime.scope, 'app_action_lock.py')
    return module.receive(runtime.c, runtime.case_runtime, runtime.plan['action_lock'],
        context['action_lock_grant'], runtime.scope_ref, Path(entry_context['step']), runtime.phase_lease_ref)
