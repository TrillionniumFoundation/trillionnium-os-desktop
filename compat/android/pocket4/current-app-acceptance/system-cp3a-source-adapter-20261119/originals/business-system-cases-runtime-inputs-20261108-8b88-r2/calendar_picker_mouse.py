"""Independent new-Main component; no historical Session, Main or execute entry."""
import copy
ROLES = {'start-date-step', 'end-date-step', 'timezone-option', 'repeat-open', 'repeat-option'}

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def normal(node):
    need(isinstance(node, dict) and type(node.get('window_id')) is int and (node['window_id'] >= 0), 'PICKER_CONNECTION_WINDOW_REQUIRED')
    return {k: v for k, v in node.items() if k != 'window_id'}

def select(node):
    return {'package': node['package'], 'class': node['class'], 'id': node['resource-id'], 'text': node['text'], 'desc': node['content-desc'], 'enabled': True, 'clickable': node['clickable'], 'editable': False}

def matches(node, selector):
    aliases = {'id': 'resource-id', 'desc': 'content-desc'}
    return all((node.get(aliases.get(k, k)) == v for k, v in selector.items()))

def input(ui, obs, label, node, role, context, popup=False):
    need(role in ROLES and bool(context) and (popup == (role == 'repeat-open')), 'REVIEWED_PICKER_ROLE_REQUIRED')
    ui.budget()
    need(not ui.pending, 'PICKER_PENDING_NO_REPLAY')
    ui.check_tasks('before-' + label)
    need(ui.focus() == obs['focus'], 'PICKER_OWNED_FOCUS_CHANGED')
    shot = obs['screenshot']
    scope = shot['scope']
    need(scope['package'] == node.get('package') == 'com.android.calendar' and node.get('visible') is True and (node.get('enabled') is True) and (node.get('editable') is False) and (node.get('password') is False) and (type(node.get('clickable')) is bool), 'VISIBLE_NONEDITABLE_CALENDAR_PICKER_REQUIRED')
    center = ui.box(obs, node)
    selector = select(node)
    need(len([n for n in obs['nodes'] if matches(n, selector)]) == 1, 'PICKER_LEAF_NOT_UNIQUE')
    request = {'package': scope['package'], 'display': 0, 'accessibility_mode': 'none', 'window_token': scope['window_token'], 'context_token': shot['context_token']}
    first = ui.s.helper.capture(request)
    ui.validate_text_window(shot, first, label, 'picker-first')
    fresh = ui.s.helper.ui({'op': 'dump', 'expected_package': scope['package'], 'display': 0, 'accessibility_mode': 'none'})
    ui.record(label + '-fresh-picker', fresh)
    need(fresh.get('ok') is True and fresh.get('outcome_unknown') is not True and (fresh.get('accessibility_mode_restoration_verified') is True), 'FRESH_PICKER_NOT_VERIFIED')
    found = [n for n in fresh.get('nodes', []) if matches(n, selector)]
    need(len(found) == 1 and normal(found[0]) == normal(node), 'FULL_PICKER_LEAF_CHANGED')
    target_window = found[0]['window_id']
    for expected in context:
        found = [n for n in fresh.get('nodes', []) if normal(n) == normal(expected)]
        need(len(found) == 1 and found[0]['window_id'] == target_window, 'PICKER_CONTEXT_NODE_CHANGED_OR_CROSS_WINDOW')
    last = ui.s.helper.capture(request)
    ui.validate_text_window(shot, last, label, 'picker-last')
    ui.check_tasks('last-' + label)
    need(ui.focus() == obs['focus'], 'LAST_PICKER_FOCUS_CHANGED')
    command = {'op': 'click', 'method': 'mouse', 'package': scope['package'], 'display': 0, 'accessibility_mode': 'none', 'window_token': scope['window_token'], 'selector': selector}
    ui.record(label + '-intent', {'request': command, 'role': role, 'node': node, 'context': context, 'native_derives_coordinates': True, 'automatic_retry': False, 'business_success_verified': False})
    ui.actions += 1
    ui.pending[label] = {'input_acknowledged': False, 'kind': 'tap'}
    ui.s.guard()
    original = ui.s.helper.ui
    acks = []

    def capture_ack(r):
        value = original(r)
        if r.get('op') == 'click':
            acks.append(copy.deepcopy(value))
            ui.record(label + '-native-ack', acks[-1])
        return value
    ui.s.helper.ui = capture_ack
    try:
        reply = ui.s.helper.dispatch(command)
    except BaseException as exc:
        ui.record(label + '-dispatch-exception', {'error': str(exc), 'details': getattr(exc, 'details', {}), 'captured_native_receipts': len(acks), 'pending_retained': True, 'input_acknowledged': False, 'automatic_retry': False})
        raise
    finally:
        ui.s.helper.ui = original
    ui.s.guard()
    ui.record(label + '-response', reply)
    need(len(acks) == 1, 'ONE_PICKER_NATIVE_RECEIPT_REQUIRED')
    ack = acks[0]
    need(ack.get('ok') is True and ack.get('performed') == 'click' and (ack.get('method') == 'mouse') and (ack.get('source') == 'native_bounds_mouse') and (ack.get('outcome_unknown') is not True) and (ack.get('accessibility_mode_restoration_verified') is True) and (ack.get('visual_verified') is False) and (ack.get('business_success_verified') is False), 'PICKER_NATIVE_OUTCOME_UNKNOWN')
    need(ack.get('coordinates') == center and all((type(v) is int for v in ack['coordinates'])) and (normal(ack.get('target')) == normal(node)) and (ack.get('target') == ack.get('actual_target')), 'PICKER_NATIVE_ACTUAL_TARGET_DIFFERS')
    need(reply.get('ok') is True and reply.get('performed') == 'click' and all((reply.get(k) == ack.get(k) for k in ('method', 'source', 'coordinates', 'target', 'actual_target', 'accessibility_mode_restoration_verified', 'visual_verified', 'business_success_verified'))) and (reply.get('outcome_unknown') is not True or reply.get('post_action_observation_available') is False), 'PICKER_HELPER_OUTCOME_UNKNOWN')
    ui.pending[label].update(input_acknowledged=True, post_capture_outcome_unknown=reply.get('outcome_unknown') is True)
    if popup:
        ui.popup_grant = {'task': obs['focus']['task'], 'parent': scope['window_token']}
    return reply
