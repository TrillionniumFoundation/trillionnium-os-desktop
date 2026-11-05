"""Strict owned-helper wire contract and offline assessor. No process/Android API."""
import base64
import hashlib
import json
import re

PROTOCOL = 'pocket4-owned-bili-qa-v2'
SELF = 'org.droidloom.qa.bili.r2'
COMPONENT = SELF + '/' + SELF + '.ActionRunner'
PACKAGE = 'tv.danmaku.bili'
UID = 10117
MAIN_EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
MAX_REQUEST = 16384
MAX_RESULT = 262144
MAX_NODES = 128
SCOPE_KEYS = {'package', 'uid', 'user', 'display', 'activity', 'window_token', 'main_epoch_sha256'}


class ProtocolError(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise ProtocolError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json_types(value):
    if isinstance(value, dict):
        require(all(isinstance(k, str) for k in value), 'JSON_KEYS_NOT_STRINGS')
        for item in value.values():
            _json_types(item)
    elif isinstance(value, list):
        for item in value:
            _json_types(item)
    else:
        require(value is None or type(value) in (str, int, bool), 'JSON_FLOAT_OR_UNSUPPORTED_TYPE')
        if type(value) is int:
            require(-(1 << 63) <= value < (1 << 63), 'INTEGER_RANGE')


def canonical(value):
    _json_types(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def nonce(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{32}', value), 'EXACT_NONCE_REQUIRED')
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'EXACT_DIGEST_REQUIRED')
    return value


def scope(value):
    require(isinstance(value, dict) and set(value) == SCOPE_KEYS, 'EXACT_SCOPE_KEYS_REQUIRED')
    require(value['package'] == PACKAGE and type(value['uid']) is int and value['uid'] == UID and
            type(value['user']) is int and value['user'] == 0 and type(value['display']) is int and
            value['display'] == 0 and value['main_epoch_sha256'] == MAIN_EPOCH,
            'FIXED_MAIN_BILI_SCOPE_REQUIRED')
    require(isinstance(value['activity'], str) and len(value['activity']) <= 256 and
            re.fullmatch(r'tv\.danmaku\.bili/[A-Za-z0-9_.$]+', value['activity']), 'HOST_ACTIVITY_REQUIRED')
    require(isinstance(value['window_token'], str) and re.fullmatch('[0-9a-f]{1,32}', value['window_token']),
            'HOST_WINDOW_TOKEN_REQUIRED')
    return value


def validate_request(value):
    require(isinstance(value, dict) and value.get('protocol') == PROTOCOL, 'PROTOCOL_REQUIRED')
    nonce(value.get('nonce'))
    op = value.get('op')
    expected = {'protocol', 'nonce', 'op'}
    if op in ('inspect', 'click'):
        expected.add('scope')
        scope(value.get('scope'))
    if op == 'click':
        expected.update(('inspection_nonce', 'inspection_sha256', 'node_path', 'node_sha256'))
        require(nonce(value.get('inspection_nonce')) != value['nonce'], 'DISTINCT_ACTION_NONCE_REQUIRED')
        digest(value.get('inspection_sha256')); digest(value.get('node_sha256'))
        require(isinstance(value.get('node_path'), str) and
                re.fullmatch(r'0(?:/[0-9]{1,2}){0,24}', value['node_path']), 'NODE_PATH_REQUIRED')
    require(op in ('state', 'inspect', 'click') and set(value) == expected, 'EXACT_OPERATION_KEYS_REQUIRED')
    raw = canonical(value)
    require(0 < len(raw) <= MAX_REQUEST, 'REQUEST_BOUND')
    return raw


def instrumentation_argv(request):
    raw = validate_request(request)
    return ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request',
            base64.b64encode(raw).decode('ascii'), COMPONENT]


def state(value):
    require(isinstance(value, dict) and set(value) == {'accessibility_enabled', 'touch_exploration_enabled',
            'enabled_service_count', 'enabled_services_sha256'}, 'STATE_FIELDS_REQUIRED')
    require(type(value['accessibility_enabled']) is bool and type(value['touch_exploration_enabled']) is bool,
            'ACTUAL_STATE_BOOLEAN_REQUIRED')
    require(type(value['enabled_service_count']) is int and 0 <= value['enabled_service_count'] <= 64,
            'SERVICE_COUNT_BOUND')
    digest(value['enabled_services_sha256'])
    return value


def parse_completed(stdout, stderr, returncode, request, helper_uid):
    """Call only after the held command is joined and its post-guard is recorded.

    This verifies a successful wire result; the caller must retain any original
    command failure before invoking it. No failing finish code is treated as PASS.
    """
    raw_request = validate_request(request)
    require(type(returncode) is int and returncode == 0, 'ACTUAL_COMMAND_FAILED')
    require(isinstance(stdout, bytes) and isinstance(stderr, bytes) and len(stdout) <= 4 * MAX_RESULT + 4096,
            'COMMAND_OUTPUT_BOUND')
    require(stderr == b'', 'COMMAND_STDERR_REQUIRES_REVIEW')
    text = stdout.decode('utf-8', 'strict')
    require('INSTRUMENTATION_FAILED' not in text and 'INSTRUMENTATION_ABORTED' not in text,
            'FRAMEWORK_INSTRUMENTATION_FAILED')
    encoded = re.findall(r'^INSTRUMENTATION_RESULT: owned_qa_result_base64=([^\r\n]*)\r?$', text, re.M)
    finishes = re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\r?$', text, re.M)
    require(len(encoded) == 1 and finishes == ['-1'], 'EXACT_SUCCESSFUL_FINISH_REQUIRED')
    raw = base64.b64decode(encoded[0], validate=True)
    require(0 < len(raw) <= MAX_RESULT, 'RESULT_BOUND')
    value = json.loads(raw)
    require(canonical(value) == raw and isinstance(value, dict), 'CANONICAL_RESULT_REQUIRED')
    require(value.get('protocol') == PROTOCOL and value.get('nonce') == request['nonce'] and
            value.get('op') == request['op'] and value.get('request_sha256') == sha(raw_request),
            'RESULT_REQUEST_BINDING_FAILED')
    require(type(helper_uid) is int and 10000 <= helper_uid < 100000 and helper_uid not in (UID, 10125, 10164) and value.get('self_uid') == helper_uid and
            type(value.get('self_pid')) is int and value['self_pid'] > 1, 'INSTALLED_HELPER_IDENTITY_REQUIRED')
    require(value.get('ok') is True and value.get('error') is None and value.get('secondary_errors') == [] and
            value.get('claim_persistence_completed') is True and value.get('helper_work_completed') is True,
            'HELPER_DID_NOT_COMPLETE_SUCCESSFULLY')
    require(value.get('automatic_retry') is False and value.get('business_success_verified') is False and
            value.get('accessibility_mode_restoration_verified') is None,
            'UNSUPPORTED_SUCCESS_OR_RESTORATION_CLAIM')
    require(type(value.get('started_elapsed_ms')) is int and type(value.get('finished_elapsed_ms')) is int and
            0 <= value['finished_elapsed_ms'] - value['started_elapsed_ms'] <= 12000, 'HELPER_ELAPSED_BOUND')
    restore = value.get('restoration')
    require(isinstance(restore, dict) and restore.get('service_info_verified') is True, 'OWN_SERVICE_RESTORE_FAILED')
    if request['op'] == 'state':
        require(value.get('action_attempted') is False and value.get('outcome_unknown') is False and
                value.get('ui_automation_connected') is False and value.get('requires_post_termination_state_check') is False and
                restore.get('service_info_captured') is False, 'STATE_PROBE_MUST_NOT_CONNECT_AUTOMATION')
        state(value.get('state'))
        require(value.get('window_observation') == {},'STATE_CANNOT_ENUMERATE_WINDOWS')
    else:
        require(value.get('host_scope_attestation') == request['scope'] and value.get('activity_verified_inside_helper') is False and
                value.get('target_uid_verified') == UID, 'HOST_SCOPE_ECHO_OR_ACTUAL_UID_CHANGED')
        require(value.get('requires_post_termination_state_check') is True and restore.get('service_info_captured') is True and
                restore.get('connection_flags') == 1, 'NON_SUPPRESSING_CONNECTION_REQUIRED')
        for field in ('service_flags_before', 'service_flags_during', 'service_flags_after',
                      'service_capabilities_before', 'service_capabilities_after'):
            require(type(restore.get(field)) is int, 'ACTUAL_SERVICE_READBACK_REQUIRED')
        require(restore['service_flags_before'] == restore['service_flags_after'] and
                restore['service_capabilities_before'] == restore['service_capabilities_after'] and
                restore['service_flags_during'] == (restore['service_flags_before'] | 16 | 64) and
                all(restore[k] & 4 == 0 for k in ('service_flags_before', 'service_flags_during', 'service_flags_after')),
                'SERVICE_READBACK_OR_TOUCH_EXPLORATION_MISMATCH')
        state(value.get('accessibility_state_before_connection'))
        observed_window = window_observation(value.get('window_observation'))
        if request['op'] == 'inspect':
            require(value.get('action_attempted') is False and value.get('outcome_unknown') is False, 'INSPECTION_CANNOT_ACT')
            inspect_record(value.get('inspection'))
            require(observed_window['selected_window_id'] == value['inspection']['connection_scoped_window_id'],
                    'INSPECTION_WINDOW_NOT_SELECTED_CENSUS_WINDOW')
        else:
            require(value.get('action_attempted') is True and value.get('outcome_unknown') is True and
                    value.get('node_action') == 'ACTION_CLICK' and value.get('node_action_returned') is True,
                    'CLICK_DISPATCH_NOT_ACKNOWLEDGED')
            for source_key, result_key in (('inspection_nonce','inspection_nonce'), ('inspection_sha256','inspection_sha256'),
                                           ('node_path','target_node_path'), ('node_sha256','target_node_sha256')):
                require(value.get(result_key) == request[source_key], 'CLICK_TARGET_BINDING_FAILED')
            require(observed_window['selected_window_id'] == value.get('connection_scoped_window_id'),
                    'ACTION_WINDOW_NOT_SELECTED_CENSUS_WINDOW')
    return {'helper': value, 'wire_sha256': sha(raw), 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
            'actual_command_returncode': returncode, 'actual_instrumentation_finish_code': -1,
            'command_join_and_epoch_guards_must_be_bound_separately': True}


def inspect_record(value):
    require(isinstance(value, dict) and value.get('complete') is True and
            value.get('traversal') == 'visible-non-password-subtrees', 'COMPLETE_INSPECTION_REQUIRED')
    window = value.get('window')
    require(isinstance(window, dict) and window.get('package') == PACKAGE and window.get('display') == 0 and
            window.get('type') == 1 and window.get('focused') is True, 'FOCUSED_BILI_WINDOW_REQUIRED')
    require(value.get('window_sha256') == sha(canonical(window)), 'WINDOW_HASH_FAILED')
    require(type(value.get('observed_elapsed_ms')) is int and value['observed_elapsed_ms'] >= 0 and
            type(value.get('connection_scoped_window_id')) is int and value['connection_scoped_window_id'] >= 0,
            'ACTUAL_WINDOW_AND_OBSERVATION_TIME_REQUIRED')
    nodes = value.get('nodes')
    require(isinstance(nodes, list) and 0 < len(nodes) <= MAX_NODES and value.get('tree_sha256') == sha(canonical(nodes)),
            'COMPLETE_TREE_HASH_FAILED')
    seen = set()
    for node in nodes:
        require(isinstance(node, dict) and node.get('package') == PACKAGE and isinstance(node.get('path'), str) and
                re.fullmatch(r'0(?:/[0-9]{1,2}){0,24}', node['path']) and node['path'] not in seen, 'NODE_SCOPE_OR_PATH_FAILED')
        seen.add(node['path'])
        require(node.get('node_sha256') == sha(canonical({k:v for k,v in node.items() if k != 'node_sha256'})), 'NODE_HASH_FAILED')
        if node.get('password') is True or node.get('visible') is False:
            require(node.get('content_redacted') is True and not ({'text','text_sha256','content_desc','content_desc_sha256'} & set(node)),
                    'PASSWORD_OR_INVISIBLE_CONTENT_MUST_NOT_BE_READ')
    return value


def failure_diagnostic(stdout, request, helper_uid):
    """Bound failure metadata only. This never returns a qualified assessment."""
    validate_request(request)
    require(isinstance(stdout,bytes) and len(stdout) <= 2*MAX_RESULT,'FAILURE_OUTPUT_BOUND')
    text = stdout.decode('utf-8','strict')
    encoded = re.findall(r'^INSTRUMENTATION_RESULT: owned_qa_result_base64=([^\r\n]+)\r?$',text,re.M)
    finishes = re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\r?$',text,re.M)
    require(len(encoded) == 1 and finishes == ['0'],'EXACT_FAILURE_FINISH_REQUIRED')
    raw = base64.b64decode(encoded[0],validate=True)
    require(0 < len(raw) <= MAX_RESULT,'FAILURE_WIRE_BOUND')
    value = json.loads(raw)
    require(canonical(value) == raw and value.get('protocol') == PROTOCOL and
            value.get('nonce') == request['nonce'] and value.get('op') == request['op'] and
            value.get('request_sha256') == sha(canonical(request)) and value.get('self_uid') == helper_uid,
            'FAILURE_REQUEST_IDENTITY_BINDING')
    require(value.get('ok') is False and isinstance(value.get('error'),str) and
            re.fullmatch('[A-Z][A-Z0-9_]{0,95}',value['error']),'ACTUAL_HELPER_REJECTION_REQUIRED')
    # Never include inspection nodes, titles, event text or recommendations.
    result = {key:value.get(key) for key in ('nonce','op','self_uid','self_pid','error',
        'claim_persistence_completed','helper_work_completed','action_attempted','outcome_unknown',
        'started_elapsed_ms','finished_elapsed_ms','requires_post_termination_state_check','restoration')}
    result.update(wire_sha256=sha(raw),instrumentation_finish_code=0,qualified_success=False)
    if 'window_observation' in value:
        result['window_observation'] = window_observation(value['window_observation'],ready_required=False)
    return result


def window_observation(value, ready_required=True):
    require(isinstance(value,dict) and len(canonical(value)) <= 32768,'WINDOW_OBSERVATION_BOUND')
    if not value and not ready_required:
        return value
    require(set(value) <= {'requested_display','selection','wait_budget_ms','ready','first','last',
                          'samples','waited_ms','selected_display','selected_window_id'} and
            value.get('requested_display') == 0 and value.get('wait_budget_ms') == 2000 and
            value.get('selection') == 'exact-display-0-focused-application' and
            type(value.get('ready')) is bool,'EXACT_WINDOW_OBSERVATION_SCOPE')
    if ready_required:
        require(value['ready'] is True and value.get('selected_display') == 0 and
                type(value.get('selected_window_id')) is int and
                type(value.get('samples')) is int and 1 <= value['samples'] <= 64 and
                type(value.get('waited_ms')) is int and 0 <= value['waited_ms'] <= 2000,
                'ACTUAL_DISPLAY_ZERO_WINDOW_READINESS_REQUIRED')
    for name in ('first','last'):
        if name not in value:
            require(not ready_required,'COMPLETE_WINDOW_CENSUS_REQUIRED')
            continue
        row = value[name]
        require(isinstance(row,dict) and set(row) == {'sample','event_serial','elapsed_ms','displays','windows'} and
                type(row['sample']) is int and 1 <= row['sample'] <= 64 and
                type(row['event_serial']) is int and row['event_serial'] >= 0 and
                type(row['elapsed_ms']) is int and row['elapsed_ms'] >= 0 and
                isinstance(row['displays'],list) and len(row['displays']) <= 8 and
                all(type(d) is int and d >= 0 for d in row['displays']) and
                isinstance(row['windows'],list) and len(row['windows']) <= 128,'WINDOW_CENSUS_SHAPE')
        for window in row['windows']:
            require(isinstance(window,dict) and set(window) == {'display','id','type','focused','active','accessibility_focused','layer'} and
                    all(type(window[k]) is int for k in ('display','id','type','layer')) and
                    window['display'] in row['displays'] and
                    all(type(window[k]) is bool for k in ('focused','active','accessibility_focused')),
                    'METADATA_ONLY_WINDOW_CENSUS_REQUIRED')
    if ready_required:
        require(value['first']['sample'] == 1 and value['last']['sample'] == value['samples'] and
                sum(window['display'] == 0 and window['type'] == 1 and window['focused'] is True
                    for window in value['last']['windows']) == 1,'UNIQUE_DISPLAY_ZERO_FOCUSED_WINDOW_REQUIRED')
        require(sum(window['display'] == 0 and window['id'] == value['selected_window_id'] and
                    window['type'] == 1 and window['focused'] is True for window in value['last']['windows']) == 1,
                'SELECTED_WINDOW_MUST_MATCH_ACTUAL_LAST_CENSUS')
    return value


def select_unique_clickable(inspection, selector):
    inspect_record(inspection)
    require(isinstance(selector, dict) and selector and set(selector) <= {'resource_id','text','content_desc','class'},
            'EXACT_BOUNDED_NODE_SELECTOR_REQUIRED')
    require(all(isinstance(v, str) and 0 < len(v.encode('utf-8')) <= 256 for v in selector.values()), 'SELECTOR_BOUND')
    found = [node for node in inspection['nodes'] if node.get('password') is False and
             node.get('enabled') is True and node.get('visible') is True and node.get('clickable') is True and
             all(node.get(k) == v and node.get(k + '_truncated') is False for k, v in selector.items())]
    require(len(found) == 1, 'NODE_SELECTOR_NOT_UNIQUE_AND_ELIGIBLE')
    return {'node_path': found[0]['path'], 'node_sha256': found[0]['node_sha256']}


def assess_restoration(before, operation, after):
    """These inputs must be parse_completed returns from three joined commands."""
    first, middle, last = before['helper'], operation['helper'], after['helper']
    require(first['op'] == last['op'] == 'state' and middle['op'] in ('inspect','click'), 'STATE_OPERATION_STATE_SEQUENCE_REQUIRED')
    require(len({first['nonce'], middle['nonce'], last['nonce']}) == 3, 'DISTINCT_PHASE_NONCES_REQUIRED')
    require(first['self_uid'] == middle['self_uid'] == last['self_uid'], 'HELPER_UID_CHANGED')
    require(first['state'] == middle['accessibility_state_before_connection'] == last['state'] and
            middle['restoration']['service_info_verified'] is True,
            'POST_TERMINATION_ACCESSIBILITY_STATE_CHANGED')
    return {'accessibility_mode_restoration_verified': True,
            'basis': 'actual own-service readback plus independent no-automation state command after successful instrumentation termination',
            'state_before': first['state'], 'state_after': last['state'],
            'wire_sha256': [before['wire_sha256'], operation['wire_sha256'], after['wire_sha256']],
            'business_success_verified': False, 'whole_app_production_ready': False}
