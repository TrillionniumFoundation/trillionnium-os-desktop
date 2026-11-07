"""Strict owned-helper wire contract and offline assessor. No process/Android API."""
import base64
import hashlib
import json
import re
import zlib

PROTOCOL = 'pocket4-owned-amazon-qa-v3'
SELF = 'org.droidloom.qa.amazon.r3'
COMPONENT = SELF + '/' + SELF + '.ActionRunner'
PACKAGE = 'com.amazon.mShop.android.shopping'
UID = 10129
MAIN_EPOCH = '734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
MAIN_BASELINE_SCHEMA = 'pocket4-main-current-baseline-v1'
MAIN_BASELINE_SHA = '163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266'
MAIN_BASELINE_QUALIFICATION_SHA = 'f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6'
MAX_REQUEST = 16384
MAX_RESULT = 524288
MAX_COMPRESSED_WIRE = 262144
MAX_STDOUT = 4 * ((MAX_COMPRESSED_WIRE + 2) // 3) + 4096
MAX_NODES = 512
MAX_DEPTH = 32
PUBLIC_SEARCH_QUERY = "usb c cable"
SCOPE_KEYS = {'package', 'uid', 'user', 'display', 'activity', 'window_token', 'main_epoch_sha256', 'main_baseline_schema', 'main_baseline_sha256', 'main_baseline_qualification_sha256'}


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
            value['display'] == 0 and value['main_epoch_sha256'] == MAIN_EPOCH and
            value['main_baseline_schema'] == MAIN_BASELINE_SCHEMA and
            value['main_baseline_sha256'] == MAIN_BASELINE_SHA and
            value['main_baseline_qualification_sha256'] == MAIN_BASELINE_QUALIFICATION_SHA,
            'FIXED_MAIN_AMAZON_SCOPE_REQUIRED')
    require(isinstance(value['activity'], str) and len(value['activity']) <= 256 and
            re.fullmatch(r'com\.amazon\.mShop\.android\.shopping/[A-Za-z0-9_.$]+', value['activity']), 'HOST_ACTIVITY_REQUIRED')
    require(isinstance(value['window_token'], str) and re.fullmatch('[0-9a-f]{1,32}', value['window_token']),
            'HOST_WINDOW_TOKEN_REQUIRED')
    return value


def validate_request(value):
    require(isinstance(value, dict) and value.get('protocol') == PROTOCOL, 'PROTOCOL_REQUIRED')
    nonce(value.get('nonce'))
    op = value.get('op')
    expected = {'protocol', 'nonce', 'op'}
    if op in ('inspect', 'click', 'set_text'):
        expected.add('scope')
        scope(value.get('scope'))
    if op in ('click','set_text'):
        expected.update(('inspection_nonce', 'inspection_sha256', 'node_path', 'node_sha256'))
        require(nonce(value.get('inspection_nonce')) != value['nonce'], 'DISTINCT_ACTION_NONCE_REQUIRED')
        digest(value.get('inspection_sha256')); digest(value.get('node_sha256'))
        require(isinstance(value.get('node_path'), str) and
                re.fullmatch(r'0(?:/[0-9]{1,2}){0,32}', value['node_path']), 'NODE_PATH_REQUIRED')
    if op == 'set_text':
        expected.update(('node_resource_id','value'))
        require(value.get('value') == PUBLIC_SEARCH_QUERY,'ONLY_FIXED_PUBLIC_SEARCH_QUERY_ALLOWED')
        require(isinstance(value.get('node_resource_id'),str) and
                re.fullmatch(r'com\.amazon\.mShop\.android\.shopping:id/[A-Za-z0-9_]+',value['node_resource_id']) and
                len(value['node_resource_id']) <= 256,'EXACT_EDIT_RESOURCE_REQUIRED')
    require(op in ('state', 'inspect', 'click', 'set_text') and set(value) == expected, 'EXACT_OPERATION_KEYS_REQUIRED')
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



def decode_wire(encoded):
    require(isinstance(encoded,str) and 0<len(encoded)<=4*((MAX_COMPRESSED_WIRE+2)//3),
            'COMPRESSED_BASE64_BOUND')
    try:
        compressed=base64.b64decode(encoded,validate=True)
    except (ValueError,base64.binascii.Error) as error:
        raise ProtocolError('INVALID_COMPRESSED_BASE64') from error
    require(0<len(compressed)<=MAX_COMPRESSED_WIRE and
            base64.b64encode(compressed).decode('ascii')==encoded,'CANONICAL_COMPRESSED_BASE64_REQUIRED')
    decoder=zlib.decompressobj(31)
    try:
        raw=decoder.decompress(compressed,MAX_RESULT+1)
    except zlib.error as error:
        raise ProtocolError('INVALID_GZIP_WIRE') from error
    require(0<len(raw)<=MAX_RESULT and decoder.eof and not decoder.unconsumed_tail and
            not decoder.unused_data,'SINGLE_BOUNDED_COMPLETE_GZIP_MEMBER_REQUIRED')
    return raw


def parse_completed(stdout, stderr, returncode, request, helper_uid):
    """Call only after the held command is joined and its post-guard is recorded.

    This verifies a successful wire result; the caller must retain any original
    command failure before invoking it. No failing finish code is treated as PASS.
    """
    raw_request = validate_request(request)
    require(type(returncode) is int and returncode == 0, 'ACTUAL_COMMAND_FAILED')
    require(isinstance(stdout, bytes) and isinstance(stderr, bytes) and len(stdout) <= MAX_STDOUT,
            'COMMAND_OUTPUT_BOUND')
    require(stderr == b'', 'COMMAND_STDERR_REQUIRES_REVIEW')
    text = stdout.decode('utf-8', 'strict')
    require('INSTRUMENTATION_FAILED' not in text and 'INSTRUMENTATION_ABORTED' not in text,
            'FRAMEWORK_INSTRUMENTATION_FAILED')
    encoded = re.findall(r'^INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=([^\r\n]*)\r?$', text, re.M)
    finishes = re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\r?$', text, re.M)
    require(len(encoded) == 1 and finishes == ['-1'], 'EXACT_SUCCESSFUL_FINISH_REQUIRED')
    raw = decode_wire(encoded[0])
    require(0 < len(raw) <= MAX_RESULT, 'RESULT_BOUND')
    value = json.loads(raw)
    require(canonical(value) == raw and isinstance(value, dict), 'CANONICAL_RESULT_REQUIRED')
    require(value.get('protocol') == PROTOCOL and value.get('nonce') == request['nonce'] and
            value.get('op') == request['op'] and value.get('request_sha256') == sha(raw_request) and
            value.get('wire_codec') == 'gzip-canonical-json-v1',
            'RESULT_REQUEST_BINDING_FAILED')
    require(type(helper_uid) is int and 10000 <= helper_uid < 100000 and helper_uid not in (UID, 10117, 10125, 10164, 10165, 10166, 10169, 10170, 10175) and value.get('self_uid') == helper_uid and
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
    observed_idle=inspection_idle_observation(value.get('inspection_idle_observation'),request['op'],
                                               value['started_elapsed_ms'],success_required=True)
    if observed_idle:
        require(observed_idle['last_elapsed_ms']<=value['finished_elapsed_ms'],
                'INSPECTION_IDLE_OUTLIVES_HELPER_RESULT')
    if request['op'] == 'state':
        require(value.get('action_attempted') is False and value.get('outcome_unknown') is False and
                value.get('ui_automation_connected') is False and value.get('requires_post_termination_state_check') is False and
                restore.get('service_info_captured') is False, 'STATE_PROBE_MUST_NOT_CONNECT_AUTOMATION')
        state(value.get('state'))
        require(value.get('window_observation') == {} and value.get('tree_observations') == [],'STATE_CANNOT_ENUMERATE_WINDOWS_OR_TREES')
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
        observed_trees = tree_observations(value.get('tree_observations'),request['op'],complete_required=True)
        if request['op'] == 'inspect':
            require(value.get('action_attempted') is False and value.get('outcome_unknown') is False, 'INSPECTION_CANNOT_ACT')
            inspect_record(value.get('inspection'))
            require(observed_trees[0]['began_elapsed_ms']>=observed_idle['last_elapsed_ms'],
                    'INSPECTION_CAPTURE_MUST_FOLLOW_ITS_IDLE_OBSERVATION')
            require(observed_window['selected_window_id'] == value['inspection']['connection_scoped_window_id'],
                    'INSPECTION_WINDOW_NOT_SELECTED_CENSUS_WINDOW')
            require(observed_trees[0]['emitted_nodes'] == len(value['inspection']['nodes']) and
                    observed_trees[0]['serialized_bytes'] == len(canonical(value['inspection'])),
                    'COMPLETE_TREE_COUNTERS_MUST_MATCH_ACTUAL_INSPECTION')
        else:
            require(value.get('action_attempted') is True and value.get('outcome_unknown') is True and
                    value.get('node_action') == ('ACTION_SET_TEXT' if request['op']=='set_text' else 'ACTION_CLICK') and
                    value.get('node_action_returned') is True,
                    'CLICK_DISPATCH_NOT_ACKNOWLEDGED')
            for source_key, result_key in (('inspection_nonce','inspection_nonce'), ('inspection_sha256','inspection_sha256'),
                                           ('node_path','target_node_path'), ('node_sha256','target_node_sha256')):
                require(value.get(result_key) == request[source_key], 'CLICK_TARGET_BINDING_FAILED')
            require(observed_window['selected_window_id'] == value.get('connection_scoped_window_id'),
                    'ACTION_WINDOW_NOT_SELECTED_CENSUS_WINDOW')
            if request['op']=='set_text':
                require(value.get('target_resource_id') == request['node_resource_id'] and
                        value.get('requested_value_sha256') == value.get('observed_value_sha256') == sha(PUBLIC_SEARCH_QUERY.encode()) and
                        value.get('value_readback_verified') is True,'ACTUAL_PUBLIC_QUERY_READBACK_REQUIRED')
    return {'helper': value, 'wire_sha256': sha(raw), 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
            'actual_command_returncode': returncode, 'actual_instrumentation_finish_code': -1,
            'command_join_and_epoch_guards_must_be_bound_separately': True}


def inspection_idle_observation(value, operation, started, success_required):
    """Safe event-quiet metadata only; neither complete-tree nor future-action qualification."""
    require(isinstance(value,dict) and len(canonical(value))<=4096,'SAFE_INSPECTION_IDLE_BOUND')
    if operation!='inspect':
        require(value=={},'ONLY_INSPECT_MAY_WAIT_FOR_EVENT_IDLE')
        return value
    if value=={}:
        require(not success_required,'INSPECTION_IDLE_OBSERVATION_REQUIRED')
        return value
    keys={'schema','operation','invoked','call_count','operation_started_elapsed_ms',
          'began_elapsed_ms','last_elapsed_ms','waited_ms','quiet_timeout_ms',
          'global_timeout_cap_ms','global_timeout_ms','operation_deadline_ms','api_returned',
          'qualified','exception_class','secondary_clock_exception_class','gate_error',
          'event_quiet_only','content_ready_proven','future_stability_proven'}
    integer_keys={'schema','call_count','operation_started_elapsed_ms','began_elapsed_ms',
                  'last_elapsed_ms','waited_ms','quiet_timeout_ms','global_timeout_cap_ms',
                  'global_timeout_ms','operation_deadline_ms'}
    require(set(value)==keys and all(type(value[k]) is int for k in integer_keys) and
            value['schema']==1 and value['operation']=='inspect' and value['invoked'] is True and
            type(value['api_returned']) is bool and type(value['qualified']) is bool,
            'EXACT_INSPECTION_IDLE_FIELDS_REQUIRED')
    require(value['event_quiet_only'] is True and value['content_ready_proven'] is False and
            value['future_stability_proven'] is False,'IDLE_CANNOT_PROVE_CONTENT_OR_FUTURE_STABILITY')
    require(type(started) is int and 0<=started<(1<<63) and value['operation_started_elapsed_ms']==started and
            (value['quiet_timeout_ms'],value['global_timeout_cap_ms'],value['operation_deadline_ms'])==(500,2000,8000),
            'INSPECTION_IDLE_ORIGINAL_BUDGET_REQUIRED')
    began,last=value['began_elapsed_ms'],value['last_elapsed_ms']
    require(0<=began<(1<<63) and 0<=last<(1<<63) and value['waited_ms']==last-began and
            value['call_count'] in (0,1),'INSPECTION_IDLE_TIME_OR_CALL_BOUND')
    expected=min(2000,max(0,started+8000-began)) if began>=started and started<=(1<<63)-1-8000 else 0
    require(value['global_timeout_ms']==expected,'INSPECTION_IDLE_REMAINING_BUDGET_MISMATCH')
    for name in ('exception_class','secondary_clock_exception_class'):
        item=value[name]
        require(isinstance(item,str) and len(item)<=192 and (item=='' or
                re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*',item)),
                'INSPECTION_IDLE_EXCEPTION_CLASS_BOUND')
    allowed={'','INSPECTION_IDLE_CLOCK_FAILED','INSPECTION_IDLE_CLOCK_INVALID',
             'INSPECTION_IDLE_BUDGET_EXHAUSTED','INSPECTION_IDLE_TIMEOUT',
             'INSPECTION_IDLE_WAIT_FAILED','INSPECTION_IDLE_BUDGET_EXCEEDED'}
    require(isinstance(value['gate_error'],str) and value['gate_error'] in allowed,
            'INSPECTION_IDLE_ERROR_REQUIRED')
    if value['call_count']==0:
        require(value['api_returned'] is False and last==began and value['waited_ms']==0 and
                value['gate_error'] in ('INSPECTION_IDLE_CLOCK_FAILED','INSPECTION_IDLE_CLOCK_INVALID',
                                       'INSPECTION_IDLE_BUDGET_EXHAUSTED'),
                'INSPECTION_IDLE_UNCALLED_FAILURE_REQUIRED')
    else:
        require(value['global_timeout_ms']>=500,'INSPECTION_IDLE_TOO_LITTLE_BUDGET_TO_CALL')
    if success_required or value['qualified']:
        require(value['qualified'] is True and value['call_count']==1 and value['api_returned'] is True and
                value['gate_error']==value['exception_class']==value['secondary_clock_exception_class']=='' and
                began>=started and 0<=value['waited_ms']<=value['global_timeout_ms'] and last<=started+8000,
                'SUCCESSFUL_BOUNDED_EVENT_IDLE_REQUIRED')
    else:
        require(value['gate_error']!='','INSPECTION_IDLE_FAILURE_CANNOT_BE_EMPTY')
    return value

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
                re.fullmatch(r'0(?:/[0-9]{1,2}){0,32}', node['path']) and node['path'] not in seen, 'NODE_SCOPE_OR_PATH_FAILED')
        seen.add(node['path'])
        require(node.get('node_sha256') == sha(canonical({k:v for k,v in node.items() if k != 'node_sha256'})), 'NODE_HASH_FAILED')
        require(type(node.get('editable')) is bool and type(node.get('supports_set_text')) is bool,
                'ACTUAL_NODE_EDIT_CAPABILITY_REQUIRED')
        if node.get('password') is True or node.get('visible') is False:
            require(node.get('content_redacted') is True and not ({'text','text_sha256','content_desc','content_desc_sha256'} & set(node)),
                    'PASSWORD_OR_INVISIBLE_CONTENT_MUST_NOT_BE_READ')
    return value


def failure_diagnostic(stdout, request, helper_uid):
    """Bound failure metadata only. This never returns a qualified assessment."""
    validate_request(request)
    require(isinstance(stdout,bytes) and len(stdout) <= MAX_STDOUT,'FAILURE_OUTPUT_BOUND')
    text = stdout.decode('utf-8','strict')
    encoded = re.findall(r'^INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=([^\r\n]+)\r?$',text,re.M)
    finishes = re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\r?$',text,re.M)
    require(len(encoded) == 1 and finishes == ['0'],'EXACT_FAILURE_FINISH_REQUIRED')
    raw = decode_wire(encoded[0])
    require(0 < len(raw) <= MAX_RESULT,'FAILURE_WIRE_BOUND')
    value = json.loads(raw)
    require(canonical(value) == raw and value.get('protocol') == PROTOCOL and
            value.get('nonce') == request['nonce'] and value.get('op') == request['op'] and
            value.get('request_sha256') == sha(canonical(request)) and value.get('self_uid') == helper_uid and
            value.get('wire_codec') == 'gzip-canonical-json-v1',
            'FAILURE_REQUEST_IDENTITY_BINDING')
    require(value.get('ok') is False and isinstance(value.get('error'),str) and
            re.fullmatch('[A-Z][A-Z0-9_]{0,95}',value['error']),'ACTUAL_HELPER_REJECTION_REQUIRED')
    # Never include inspection nodes, titles, event text or recommendations.
    result = {key:value.get(key) for key in ('nonce','op','self_uid','self_pid','error',
        'claim_persistence_completed','helper_work_completed','action_attempted','outcome_unknown',
        'started_elapsed_ms','finished_elapsed_ms','requires_post_termination_state_check','restoration')}
    result.update(wire_sha256=sha(raw),instrumentation_finish_code=0,qualified_success=False)
    if 'tree_observations' in value:
        result['tree_observations'] = tree_observations(value['tree_observations'],request['op'],complete_required=False)
    if 'window_observation' in value:
        result['window_observation'] = window_observation(value['window_observation'],ready_required=False)
    if 'inspection_idle_observation' in value:
        result['inspection_idle_observation']=inspection_idle_observation(
            value['inspection_idle_observation'],request['op'],value.get('started_elapsed_ms'),success_required=False)
    return result



def tree_observations(value, operation, complete_required):
    require(isinstance(value,list) and len(value)<=3 and len(canonical(value))<=8192,
            'SAFE_TREE_COUNTER_BOUND')
    if operation=='state':
        require(value==[],'STATE_CANNOT_ENUMERATE_TREES')
        return value
    expected=['inspection'] if operation=='inspect' else ['action_target','action_final_window']
    require(len(value)<=len(expected),'TREE_CAPTURE_COUNT_BOUND')
    if complete_required:require(len(value)==len(expected),'COMPLETE_TREE_CAPTURE_SEQUENCE_REQUIRED')
    keys={'capture','purpose','node_limit','depth_limit','child_limit','json_byte_limit','attempted_nodes',
          'emitted_nodes','max_attempted_depth','max_observed_children','serialized_bytes','complete',
          'began_elapsed_ms','last_elapsed_ms'}
    for index,row in enumerate(value):
        require(isinstance(row,dict) and set(row)==keys and row['capture']==index+1 and
                row['purpose']==expected[index] and type(row['complete']) is bool and
                all(type(row[k]) is int for k in keys-{'purpose','complete'}),'EXACT_SAFE_TREE_COUNTERS_REQUIRED')
        require((row['node_limit'],row['depth_limit'],row['child_limit'],row['json_byte_limit'])==
                (MAX_NODES,MAX_DEPTH,64,MAX_RESULT-65536),'EXACT_TREE_LIMITS_REQUIRED')
        require(0<=row['attempted_nodes']<=MAX_NODES+1 and 0<=row['emitted_nodes']<=MAX_NODES and
                0<=row['max_attempted_depth']<=MAX_DEPTH+1 and 0<=row['max_observed_children']<(1<<31) and
                0<=row['serialized_bytes']<=33554432 and
                0<=row['began_elapsed_ms']<=row['last_elapsed_ms'],'TREE_COUNTER_VALUE_BOUND')
        if complete_required:require(row['complete'],'PARTIAL_TREE_CANNOT_QUALIFY')
        if row['complete']:
            require(0<row['emitted_nodes']==row['attempted_nodes']<=MAX_NODES and
                    row['max_attempted_depth']<=MAX_DEPTH and row['max_observed_children']<=64 and
                    0<row['serialized_bytes']<=MAX_RESULT-65536,'COMPLETE_TREE_COUNTERS_INCONSISTENT')
    return value


def window_observation(value, ready_required=True):
    require(isinstance(value,dict) and len(canonical(value)) <= 32768,'WINDOW_OBSERVATION_BOUND')
    if not value and not ready_required:
        return value
    require(set(value) <= {'requested_display','selection','wait_budget_ms','ready','first','last',
                          'samples','waited_ms','selected_display','selected_window_id',
                          'recheck_max_ms','sample_timings','cache_api','cache_policy',
                          'cache_runtime_sdk','cache_attempts','cache_clears','cache_last_result','cache_last_exception'} and
            value.get('requested_display') == 0 and value.get('wait_budget_ms') == 2000 and
            value.get('recheck_max_ms') == 100 and
            value.get('selection') == 'exact-display-0-focused-application' and
            type(value.get('ready')) is bool,'EXACT_WINDOW_OBSERVATION_SCOPE')
    timings = value.get('sample_timings')
    require(isinstance(timings,list) and len(timings) <= 64,'BOUNDED_WINDOW_SAMPLE_TIMINGS_REQUIRED')
    attempts, clears = value.get('cache_attempts'), value.get('cache_clears')
    samples = value.get('samples',0)
    require({'cache_api','cache_policy','cache_runtime_sdk','cache_attempts','cache_clears',
             'cache_last_result','cache_last_exception'} <= set(value) and
            value.get('cache_api') == 'android.app.UiAutomation.clearCache()' and
            value.get('cache_policy') == 'require_public_own_connection_clear_before_each_query' and
            type(value.get('cache_runtime_sdk')) is int and value['cache_runtime_sdk'] >= 0 and
            type(samples) is int and type(attempts) is int and type(clears) is int and
            0 <= samples <= clears <= attempts <= min(samples+1,64) and
            (value.get('cache_last_result') is None or type(value['cache_last_result']) is bool) and
            (value.get('cache_last_exception') is None or
             (isinstance(value['cache_last_exception'],str) and
              re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$.]{0,255}',value['cache_last_exception']))),
            'EXACT_PUBLIC_OWN_CACHE_CLEAR_EVIDENCE_REQUIRED')
    previous_elapsed = previous_serial = -1
    for index, row in enumerate(timings,1):
        require(isinstance(row,dict) and set(row) == {'sample','event_serial','elapsed_ms','cache_cleared'} and
                type(row['sample']) is int and row['sample'] == index and
                type(row['event_serial']) is int and row['event_serial'] >= 0 and
                type(row['elapsed_ms']) is int and row['elapsed_ms'] >= 0 and
                row['event_serial'] >= previous_serial and row['elapsed_ms'] >= previous_elapsed and
                row['cache_cleared'] is True,
                'ORDERED_METADATA_ONLY_WINDOW_SAMPLE_TIMINGS_REQUIRED')
        previous_elapsed, previous_serial = row['elapsed_ms'], row['event_serial']
    require(('samples' not in value and not timings) or value.get('samples') == len(timings),
            'WINDOW_SAMPLE_COUNT_MISMATCH')
    if ready_required:
        require(attempts == clears == samples and value.get('cache_last_result') is True and
                value.get('cache_last_exception') is None and value['cache_runtime_sdk'] >= 34,
                'EVERY_WINDOW_QUERY_NEEDS_CONFIRMED_CACHE_CLEAR')
        require(value['ready'] is True and value.get('selected_display') == 0 and
                type(value.get('selected_window_id')) is int and
                type(value.get('samples')) is int and 1 <= value['samples'] <= 64 and
                type(value.get('waited_ms')) is int and 0 <= value['waited_ms'] <= 2000 and
                timings and timings[-1]['elapsed_ms'] <= value['waited_ms'],
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
        require(timings and all(row[key] == timings[0 if name == 'first' else -1][key]
                for key in ('sample','event_serial','elapsed_ms')), 'WINDOW_CENSUS_TIMING_MISMATCH')
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



def select_unique_editable(inspection, selector):
    inspect_record(inspection)
    require(isinstance(selector,dict) and {'resource_id','class'}<=set(selector) and
            set(selector)<={'resource_id','class','text','content_desc'} and
            selector['class']=='android.widget.EditText' and
            re.fullmatch(r'com\.amazon\.mShop\.android\.shopping:id/[A-Za-z0-9_]+',selector['resource_id']) and
            all(isinstance(v,str) and 0<len(v.encode('utf-8'))<=256 for v in selector.values()),
            'EXACT_OBSERVED_EDIT_RESOURCE_AND_CLASS_REQUIRED')
    found=[node for node in inspection['nodes'] if node.get('password') is False and
           node.get('enabled') is True and node.get('visible') is True and node.get('editable') is True and
           node.get('supports_set_text') is True and
           all(node.get(k)==v and node.get(k+'_truncated') is False for k,v in selector.items())]
    require(len(found)==1,'EDIT_SELECTOR_NOT_UNIQUE_AND_ELIGIBLE')
    return {'node_path':found[0]['path'],'node_sha256':found[0]['node_sha256'],
            'node_resource_id':found[0]['resource_id']}


def assess_restoration(before, operation, after):
    """These inputs must be parse_completed returns from three joined commands."""
    first, middle, last = before['helper'], operation['helper'], after['helper']
    require(first['op'] == last['op'] == 'state' and middle['op'] in ('inspect','click','set_text'), 'STATE_OPERATION_STATE_SEQUENCE_REQUIRED')
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
