#!/usr/bin/env python3
"""Fixed retired BestBuy R2 public-role projection; no Android action or raw UI export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

ROOT=Path('/home/alex/work/pocket4-bestbuy-owned-r2-launch-inspect-01')
FLOW=Path('/home/alex/work/pocket4-bestbuy-owned-qa-r2-flow-4e923582e649c6d00e5a46c5e673dbe7')
NONCE='4e923582e649c6d00e5a46c5e673dbe7'
INSPECT_NONCE='139ae993b55bac3d4fec87cb88ec0fdb'
SOURCE_SHA='a87f88a8e0767d944d33711ead4fdcd08ce52ade0ea6f4a920452ad8feaeb99a'
HELPER_UID=10203
PACKAGE='com.bestbuy.android'
HELPER_PACKAGE='org.droidloom.qa.bestbuy.r2'
FILES={
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'launch.json':FLOW/'steps/launch-01/result.json',
    'inspect.json':FLOW/'steps/inspect-01/result.json',
    'cleanup.json':FLOW/'steps/cleanup-01/result.json',
    'assessment.json':FLOW/'steps/inspect-01'/(INSPECT_NONCE+'.assessment.json'),
}
PINS={
    'coordinator.json':(13681,'db3ac3a5ddb2e1d3ad6b82103e844f6657fed5fbb6e67f26ff20e818323e1675'),
    'stage.json':(1716,'7de3a15b16afbac406102931b7f618ff3b5b0f3945dabbeed0ab8653fa65555a'),
    'launch.json':(13278,'6f89d64ed16047b2d48cc84514877ad27a08a257db928c2d7768b0e3c85f9acd'),
    'inspect.json':(21211,'0a6c2e4b82c3a549e400da299e992135b8b4b9abed2de133c503847872ecf7f5'),
    'cleanup.json':(12150,'f1d8aa301b3163c85183da9833ce5d541a03adba7f859e49b4c39dafdbce0b31'),
    'assessment.json':(19932,'1cace36a1c299f9f3283866855483951b13b9a01d000b6c0d33b3ef7a1cb7704'),
}
QA_SHA='07ab2e9540593df78f6fef406fcd8ff383d2674f1aec5642bf4cc47724915d5b'
QA_SOURCE="\"\"\"Strict owned-helper wire contract and offline assessor. No process/Android API.\"\"\"\nimport base64\nimport hashlib\nimport json\nimport re\nimport zlib\n\nPROTOCOL = 'pocket4-owned-bestbuy-qa-v2'\nSELF = 'org.droidloom.qa.bestbuy.r2'\nCOMPONENT = SELF + '/' + SELF + '.ActionRunner'\nPACKAGE = 'com.bestbuy.android'\nUID = 10130\nMAIN_EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'\nMAX_REQUEST = 16384\nMAX_RESULT = 524288\nMAX_COMPRESSED_WIRE = 262144\nMAX_STDOUT = 4 * ((MAX_COMPRESSED_WIRE + 2) // 3) + 4096\nMAX_NODES = 512\nMAX_DEPTH = 128\nNODE_PATH_PATTERN = r'0(?:/[0-9]{1,2}){0,%d}' % MAX_DEPTH\n# Legacy text branch remains unreachable: this revision rejects set_text at all request entries.\nPUBLIC_SEARCH_QUERY = \"usb c cable\"\nSCOPE_KEYS = {'package', 'uid', 'user', 'display', 'activity', 'window_token', 'main_epoch_sha256'}\n\n\nclass ProtocolError(RuntimeError):\n    pass\n\n\ndef require(value, code):\n    if not value:\n        raise ProtocolError(code)\n\n\ndef sha(raw):\n    return hashlib.sha256(raw).hexdigest()\n\n\ndef _json_types(value):\n    if isinstance(value, dict):\n        require(all(isinstance(k, str) for k in value), 'JSON_KEYS_NOT_STRINGS')\n        for item in value.values():\n            _json_types(item)\n    elif isinstance(value, list):\n        for item in value:\n            _json_types(item)\n    else:\n        require(value is None or type(value) in (str, int, bool), 'JSON_FLOAT_OR_UNSUPPORTED_TYPE')\n        if type(value) is int:\n            require(-(1 << 63) <= value < (1 << 63), 'INTEGER_RANGE')\n\n\ndef canonical(value):\n    _json_types(value)\n    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')\n\n\ndef nonce(value):\n    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{32}', value), 'EXACT_NONCE_REQUIRED')\n    return value\n\n\ndef digest(value):\n    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'EXACT_DIGEST_REQUIRED')\n    return value\n\n\ndef scope(value):\n    require(isinstance(value, dict) and set(value) == SCOPE_KEYS, 'EXACT_SCOPE_KEYS_REQUIRED')\n    require(value['package'] == PACKAGE and type(value['uid']) is int and value['uid'] == UID and\n            type(value['user']) is int and value['user'] == 0 and type(value['display']) is int and\n            value['display'] == 0 and value['main_epoch_sha256'] == MAIN_EPOCH,\n            'FIXED_MAIN_BESTBUY_SCOPE_REQUIRED')\n    require(isinstance(value['activity'], str) and len(value['activity']) <= 256 and\n            re.fullmatch(r'com\\.bestbuy\\.android/[A-Za-z0-9_.$]+', value['activity']), 'HOST_ACTIVITY_REQUIRED')\n    require(isinstance(value['window_token'], str) and re.fullmatch('[0-9a-f]{1,32}', value['window_token']),\n            'HOST_WINDOW_TOKEN_REQUIRED')\n    return value\n\n\ndef validate_request(value):\n    require(isinstance(value, dict) and value.get('protocol') == PROTOCOL, 'PROTOCOL_REQUIRED')\n    nonce(value.get('nonce'))\n    op = value.get('op')\n    require(op in ('state','inspect','click'),'BESTBUY_READ_INSPECT_CLICK_ONLY')\n    expected = {'protocol', 'nonce', 'op'}\n    if op in ('inspect', 'click', 'set_text'):\n        expected.add('scope')\n        scope(value.get('scope'))\n    if op in ('click','set_text'):\n        expected.update(('inspection_nonce', 'inspection_sha256', 'node_path', 'node_sha256'))\n        require(nonce(value.get('inspection_nonce')) != value['nonce'], 'DISTINCT_ACTION_NONCE_REQUIRED')\n        digest(value.get('inspection_sha256')); digest(value.get('node_sha256'))\n        require(isinstance(value.get('node_path'), str) and\n                re.fullmatch(NODE_PATH_PATTERN, value['node_path']), 'NODE_PATH_REQUIRED')\n    if op == 'set_text':\n        expected.update(('node_resource_id','value'))\n        require(value.get('value') == PUBLIC_SEARCH_QUERY,'ONLY_FIXED_PUBLIC_SEARCH_QUERY_ALLOWED')\n        require(isinstance(value.get('node_resource_id'),str) and\n                re.fullmatch(r'com\\.bestbuy\\.android:id/[A-Za-z0-9_]+',value['node_resource_id']) and\n                len(value['node_resource_id']) <= 256,'EXACT_EDIT_RESOURCE_REQUIRED')\n    require(op in ('state', 'inspect', 'click', 'set_text') and set(value) == expected, 'EXACT_OPERATION_KEYS_REQUIRED')\n    raw = canonical(value)\n    require(0 < len(raw) <= MAX_REQUEST, 'REQUEST_BOUND')\n    return raw\n\n\ndef instrumentation_argv(request):\n    raw = validate_request(request)\n    return ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request',\n            base64.b64encode(raw).decode('ascii'), COMPONENT]\n\n\ndef state(value):\n    require(isinstance(value, dict) and set(value) == {'accessibility_enabled', 'touch_exploration_enabled',\n            'enabled_service_count', 'enabled_services_sha256'}, 'STATE_FIELDS_REQUIRED')\n    require(type(value['accessibility_enabled']) is bool and type(value['touch_exploration_enabled']) is bool,\n            'ACTUAL_STATE_BOOLEAN_REQUIRED')\n    require(type(value['enabled_service_count']) is int and 0 <= value['enabled_service_count'] <= 64,\n            'SERVICE_COUNT_BOUND')\n    digest(value['enabled_services_sha256'])\n    return value\n\n\n\ndef decode_wire(encoded):\n    require(isinstance(encoded,str) and 0<len(encoded)<=4*((MAX_COMPRESSED_WIRE+2)//3),\n            'COMPRESSED_BASE64_BOUND')\n    try:\n        compressed=base64.b64decode(encoded,validate=True)\n    except (ValueError,base64.binascii.Error) as error:\n        raise ProtocolError('INVALID_COMPRESSED_BASE64') from error\n    require(0<len(compressed)<=MAX_COMPRESSED_WIRE and\n            base64.b64encode(compressed).decode('ascii')==encoded,'CANONICAL_COMPRESSED_BASE64_REQUIRED')\n    decoder=zlib.decompressobj(31)\n    try:\n        raw=decoder.decompress(compressed,MAX_RESULT+1)\n    except zlib.error as error:\n        raise ProtocolError('INVALID_GZIP_WIRE') from error\n    require(0<len(raw)<=MAX_RESULT and decoder.eof and not decoder.unconsumed_tail and\n            not decoder.unused_data,'SINGLE_BOUNDED_COMPLETE_GZIP_MEMBER_REQUIRED')\n    return raw\n\n\ndef parse_completed(stdout, stderr, returncode, request, helper_uid):\n    \"\"\"Call only after the held command is joined and its post-guard is recorded.\n\n    This verifies a successful wire result; the caller must retain any original\n    command failure before invoking it. No failing finish code is treated as PASS.\n    \"\"\"\n    raw_request = validate_request(request)\n    require(type(returncode) is int and returncode == 0, 'ACTUAL_COMMAND_FAILED')\n    require(isinstance(stdout, bytes) and isinstance(stderr, bytes) and len(stdout) <= MAX_STDOUT,\n            'COMMAND_OUTPUT_BOUND')\n    require(stderr == b'', 'COMMAND_STDERR_REQUIRES_REVIEW')\n    text = stdout.decode('utf-8', 'strict')\n    require('INSTRUMENTATION_FAILED' not in text and 'INSTRUMENTATION_ABORTED' not in text,\n            'FRAMEWORK_INSTRUMENTATION_FAILED')\n    encoded = re.findall(r'^INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=([^\\r\\n]*)\\r?$', text, re.M)\n    finishes = re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\\r?$', text, re.M)\n    require(len(encoded) == 1 and finishes == ['-1'], 'EXACT_SUCCESSFUL_FINISH_REQUIRED')\n    raw = decode_wire(encoded[0])\n    require(0 < len(raw) <= MAX_RESULT, 'RESULT_BOUND')\n    value = json.loads(raw)\n    require(canonical(value) == raw and isinstance(value, dict), 'CANONICAL_RESULT_REQUIRED')\n    require(value.get('protocol') == PROTOCOL and value.get('nonce') == request['nonce'] and\n            value.get('op') == request['op'] and value.get('request_sha256') == sha(raw_request) and\n            value.get('wire_codec') == 'gzip-canonical-json-v1',\n            'RESULT_REQUEST_BINDING_FAILED')\n    require(type(helper_uid) is int and 10000 <= helper_uid < 100000 and helper_uid not in (UID, 10121, 10129, 10117, 10125, 10164, 10165, 10166, 10169, 10170, 10175, 10184, 10190, 10137, 10196, 10198) and value.get('self_uid') == helper_uid and\n            type(value.get('self_pid')) is int and value['self_pid'] > 1, 'INSTALLED_HELPER_IDENTITY_REQUIRED')\n    require(value.get('ok') is True and value.get('error') is None and value.get('secondary_errors') == [] and\n            value.get('claim_persistence_completed') is True and value.get('helper_work_completed') is True,\n            'HELPER_DID_NOT_COMPLETE_SUCCESSFULLY')\n    require(value.get('automatic_retry') is False and value.get('business_success_verified') is False and\n            value.get('accessibility_mode_restoration_verified') is None,\n            'UNSUPPORTED_SUCCESS_OR_RESTORATION_CLAIM')\n    require(type(value.get('started_elapsed_ms')) is int and type(value.get('finished_elapsed_ms')) is int and\n            0 <= value['finished_elapsed_ms'] - value['started_elapsed_ms'] <= 12000, 'HELPER_ELAPSED_BOUND')\n    restore = value.get('restoration')\n    require(isinstance(restore, dict) and restore.get('service_info_verified') is True, 'OWN_SERVICE_RESTORE_FAILED')\n    if request['op'] == 'state':\n        require(value.get('action_attempted') is False and value.get('outcome_unknown') is False and\n                value.get('ui_automation_connected') is False and value.get('requires_post_termination_state_check') is False and\n                restore.get('service_info_captured') is False, 'STATE_PROBE_MUST_NOT_CONNECT_AUTOMATION')\n        state(value.get('state'))\n        require(value.get('window_observation') == {} and value.get('tree_observations') == [],'STATE_CANNOT_ENUMERATE_WINDOWS_OR_TREES')\n    else:\n        require(value.get('host_scope_attestation') == request['scope'] and value.get('activity_verified_inside_helper') is False and\n                value.get('target_uid_verified') == UID, 'HOST_SCOPE_ECHO_OR_ACTUAL_UID_CHANGED')\n        require(value.get('requires_post_termination_state_check') is True and restore.get('service_info_captured') is True and\n                restore.get('connection_flags') == 1, 'NON_SUPPRESSING_CONNECTION_REQUIRED')\n        for field in ('service_flags_before', 'service_flags_during', 'service_flags_after',\n                      'service_capabilities_before', 'service_capabilities_after'):\n            require(type(restore.get(field)) is int, 'ACTUAL_SERVICE_READBACK_REQUIRED')\n        require(restore['service_flags_before'] == restore['service_flags_after'] and\n                restore['service_capabilities_before'] == restore['service_capabilities_after'] and\n                restore['service_flags_during'] == (restore['service_flags_before'] | 16 | 64) and\n                all(restore[k] & 4 == 0 for k in ('service_flags_before', 'service_flags_during', 'service_flags_after')),\n                'SERVICE_READBACK_OR_TOUCH_EXPLORATION_MISMATCH')\n        state(value.get('accessibility_state_before_connection'))\n        observed_window = window_observation(value.get('window_observation'))\n        observed_trees = tree_observations(value.get('tree_observations'),request['op'],complete_required=True)\n        if request['op'] == 'inspect':\n            require(value.get('action_attempted') is False and value.get('outcome_unknown') is False, 'INSPECTION_CANNOT_ACT')\n            inspect_record(value.get('inspection'))\n            require(observed_window['selected_window_id'] == value['inspection']['connection_scoped_window_id'],\n                    'INSPECTION_WINDOW_NOT_SELECTED_CENSUS_WINDOW')\n            require(observed_trees[0]['emitted_nodes'] == len(value['inspection']['nodes']) and\n                    observed_trees[0]['serialized_bytes'] == len(canonical(value['inspection'])),\n                    'COMPLETE_TREE_COUNTERS_MUST_MATCH_ACTUAL_INSPECTION')\n        else:\n            require(value.get('action_attempted') is True and value.get('outcome_unknown') is True and\n                    value.get('node_action') == ('ACTION_SET_TEXT' if request['op']=='set_text' else 'ACTION_CLICK') and\n                    value.get('node_action_returned') is True,\n                    'CLICK_DISPATCH_NOT_ACKNOWLEDGED')\n            for source_key, result_key in (('inspection_nonce','inspection_nonce'), ('inspection_sha256','inspection_sha256'),\n                                           ('node_path','target_node_path'), ('node_sha256','target_node_sha256')):\n                require(value.get(result_key) == request[source_key], 'CLICK_TARGET_BINDING_FAILED')\n            require(observed_window['selected_window_id'] == value.get('connection_scoped_window_id'),\n                    'ACTION_WINDOW_NOT_SELECTED_CENSUS_WINDOW')\n            if request['op']=='set_text':\n                require(value.get('target_resource_id') == request['node_resource_id'] and\n                        value.get('requested_value_sha256') == value.get('observed_value_sha256') == sha(PUBLIC_SEARCH_QUERY.encode()) and\n                        value.get('value_readback_verified') is True,'ACTUAL_PUBLIC_QUERY_READBACK_REQUIRED')\n    return {'helper': value, 'wire_sha256': sha(raw), 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),\n            'actual_command_returncode': returncode, 'actual_instrumentation_finish_code': -1,\n            'command_join_and_epoch_guards_must_be_bound_separately': True}\n\n\ndef inspect_record(value):\n    require(isinstance(value, dict) and value.get('complete') is True and\n            value.get('traversal') == 'visible-non-password-subtrees', 'COMPLETE_INSPECTION_REQUIRED')\n    window = value.get('window')\n    require(isinstance(window, dict) and window.get('package') == PACKAGE and window.get('display') == 0 and\n            window.get('type') == 1 and window.get('focused') is True, 'FOCUSED_BILI_WINDOW_REQUIRED')\n    require(value.get('window_sha256') == sha(canonical(window)), 'WINDOW_HASH_FAILED')\n    require(type(value.get('observed_elapsed_ms')) is int and value['observed_elapsed_ms'] >= 0 and\n            type(value.get('connection_scoped_window_id')) is int and value['connection_scoped_window_id'] >= 0,\n            'ACTUAL_WINDOW_AND_OBSERVATION_TIME_REQUIRED')\n    nodes = value.get('nodes')\n    require(isinstance(nodes, list) and 0 < len(nodes) <= MAX_NODES and value.get('tree_sha256') == sha(canonical(nodes)),\n            'COMPLETE_TREE_HASH_FAILED')\n    seen = set()\n    for node in nodes:\n        require(isinstance(node, dict) and node.get('package') == PACKAGE and isinstance(node.get('path'), str) and\n                re.fullmatch(NODE_PATH_PATTERN, node['path']) and node['path'] not in seen, 'NODE_SCOPE_OR_PATH_FAILED')\n        seen.add(node['path'])\n        require(node.get('node_sha256') == sha(canonical({k:v for k,v in node.items() if k != 'node_sha256'})), 'NODE_HASH_FAILED')\n        require(type(node.get('editable')) is bool and type(node.get('supports_set_text')) is bool,\n                'ACTUAL_NODE_EDIT_CAPABILITY_REQUIRED')\n        if node.get('password') is True or node.get('visible') is False:\n            require(node.get('content_redacted') is True and not ({'text','text_sha256','content_desc','content_desc_sha256'} & set(node)),\n                    'PASSWORD_OR_INVISIBLE_CONTENT_MUST_NOT_BE_READ')\n    return value\n\n\ndef failure_diagnostic(stdout, request, helper_uid):\n    \"\"\"Bound failure metadata only. This never returns a qualified assessment.\"\"\"\n    validate_request(request)\n    require(isinstance(stdout,bytes) and len(stdout) <= MAX_STDOUT,'FAILURE_OUTPUT_BOUND')\n    text = stdout.decode('utf-8','strict')\n    encoded = re.findall(r'^INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=([^\\r\\n]+)\\r?$',text,re.M)\n    finishes = re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\\r?$',text,re.M)\n    require(len(encoded) == 1 and finishes == ['0'],'EXACT_FAILURE_FINISH_REQUIRED')\n    raw = decode_wire(encoded[0])\n    require(0 < len(raw) <= MAX_RESULT,'FAILURE_WIRE_BOUND')\n    value = json.loads(raw)\n    require(canonical(value) == raw and value.get('protocol') == PROTOCOL and\n            value.get('nonce') == request['nonce'] and value.get('op') == request['op'] and\n            value.get('request_sha256') == sha(canonical(request)) and value.get('self_uid') == helper_uid and\n            value.get('wire_codec') == 'gzip-canonical-json-v1',\n            'FAILURE_REQUEST_IDENTITY_BINDING')\n    require(value.get('ok') is False and isinstance(value.get('error'),str) and\n            re.fullmatch('[A-Z][A-Z0-9_]{0,95}',value['error']),'ACTUAL_HELPER_REJECTION_REQUIRED')\n    # Never include inspection nodes, titles, event text or recommendations.\n    result = {key:value.get(key) for key in ('nonce','op','self_uid','self_pid','error',\n        'claim_persistence_completed','helper_work_completed','action_attempted','outcome_unknown',\n        'started_elapsed_ms','finished_elapsed_ms','requires_post_termination_state_check','restoration')}\n    result.update(wire_sha256=sha(raw),instrumentation_finish_code=0,qualified_success=False)\n    if 'tree_observations' in value:\n        result['tree_observations'] = tree_observations(value['tree_observations'],request['op'],complete_required=False)\n    if 'window_observation' in value:\n        result['window_observation'] = window_observation(value['window_observation'],ready_required=False)\n    return result\n\n\n\ndef tree_observations(value, operation, complete_required):\n    require(isinstance(value,list) and len(value)<=3 and len(canonical(value))<=8192,\n            'SAFE_TREE_COUNTER_BOUND')\n    if operation=='state':\n        require(value==[],'STATE_CANNOT_ENUMERATE_TREES')\n        return value\n    expected=['inspection'] if operation=='inspect' else ['action_target','action_final_window']\n    require(len(value)<=len(expected),'TREE_CAPTURE_COUNT_BOUND')\n    if complete_required:require(len(value)==len(expected),'COMPLETE_TREE_CAPTURE_SEQUENCE_REQUIRED')\n    keys={'capture','purpose','node_limit','depth_limit','child_limit','json_byte_limit','attempted_nodes',\n          'emitted_nodes','max_attempted_depth','max_observed_children','serialized_bytes','complete',\n          'began_elapsed_ms','last_elapsed_ms'}\n    for index,row in enumerate(value):\n        require(isinstance(row,dict) and set(row)==keys and row['capture']==index+1 and\n                row['purpose']==expected[index] and type(row['complete']) is bool and\n                all(type(row[k]) is int for k in keys-{'purpose','complete'}),'EXACT_SAFE_TREE_COUNTERS_REQUIRED')\n        require((row['node_limit'],row['depth_limit'],row['child_limit'],row['json_byte_limit'])==\n                (MAX_NODES,MAX_DEPTH,64,MAX_RESULT-65536),'EXACT_TREE_LIMITS_REQUIRED')\n        require(0<=row['attempted_nodes']<=MAX_NODES+1 and 0<=row['emitted_nodes']<=MAX_NODES and\n                0<=row['max_attempted_depth']<=MAX_DEPTH+1 and 0<=row['max_observed_children']<(1<<31) and\n                0<=row['serialized_bytes']<=33554432 and\n                0<=row['began_elapsed_ms']<=row['last_elapsed_ms'],'TREE_COUNTER_VALUE_BOUND')\n        if complete_required:require(row['complete'],'PARTIAL_TREE_CANNOT_QUALIFY')\n        if row['complete']:\n            require(0<row['emitted_nodes']==row['attempted_nodes']<=MAX_NODES and\n                    row['max_attempted_depth']<=MAX_DEPTH and row['max_observed_children']<=64 and\n                    0<row['serialized_bytes']<=MAX_RESULT-65536,'COMPLETE_TREE_COUNTERS_INCONSISTENT')\n    return value\n\n\ndef window_observation(value, ready_required=True):\n    require(isinstance(value,dict) and len(canonical(value)) <= 32768,'WINDOW_OBSERVATION_BOUND')\n    if not value and not ready_required:\n        return value\n    require(set(value) <= {'requested_display','selection','wait_budget_ms','ready','first','last',\n                          'samples','waited_ms','selected_display','selected_window_id',\n                          'recheck_max_ms','sample_timings','cache_api','cache_policy',\n                          'cache_runtime_sdk','cache_attempts','cache_clears','cache_last_result','cache_last_exception'} and\n            value.get('requested_display') == 0 and value.get('wait_budget_ms') == 2000 and\n            value.get('recheck_max_ms') == 100 and\n            value.get('selection') == 'exact-display-0-focused-application' and\n            type(value.get('ready')) is bool,'EXACT_WINDOW_OBSERVATION_SCOPE')\n    timings = value.get('sample_timings')\n    require(isinstance(timings,list) and len(timings) <= 64,'BOUNDED_WINDOW_SAMPLE_TIMINGS_REQUIRED')\n    attempts, clears = value.get('cache_attempts'), value.get('cache_clears')\n    samples = value.get('samples',0)\n    require({'cache_api','cache_policy','cache_runtime_sdk','cache_attempts','cache_clears',\n             'cache_last_result','cache_last_exception'} <= set(value) and\n            value.get('cache_api') == 'android.app.UiAutomation.clearCache()' and\n            value.get('cache_policy') == 'require_public_own_connection_clear_before_each_query' and\n            type(value.get('cache_runtime_sdk')) is int and value['cache_runtime_sdk'] >= 0 and\n            type(samples) is int and type(attempts) is int and type(clears) is int and\n            0 <= samples <= clears <= attempts <= min(samples+1,64) and\n            (value.get('cache_last_result') is None or type(value['cache_last_result']) is bool) and\n            (value.get('cache_last_exception') is None or\n             (isinstance(value['cache_last_exception'],str) and\n              re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$.]{0,255}',value['cache_last_exception']))),\n            'EXACT_PUBLIC_OWN_CACHE_CLEAR_EVIDENCE_REQUIRED')\n    previous_elapsed = previous_serial = -1\n    for index, row in enumerate(timings,1):\n        require(isinstance(row,dict) and set(row) == {'sample','event_serial','elapsed_ms','cache_cleared'} and\n                type(row['sample']) is int and row['sample'] == index and\n                type(row['event_serial']) is int and row['event_serial'] >= 0 and\n                type(row['elapsed_ms']) is int and row['elapsed_ms'] >= 0 and\n                row['event_serial'] >= previous_serial and row['elapsed_ms'] >= previous_elapsed and\n                row['cache_cleared'] is True,\n                'ORDERED_METADATA_ONLY_WINDOW_SAMPLE_TIMINGS_REQUIRED')\n        previous_elapsed, previous_serial = row['elapsed_ms'], row['event_serial']\n    require(('samples' not in value and not timings) or value.get('samples') == len(timings),\n            'WINDOW_SAMPLE_COUNT_MISMATCH')\n    if ready_required:\n        require(attempts == clears == samples and value.get('cache_last_result') is True and\n                value.get('cache_last_exception') is None and value['cache_runtime_sdk'] >= 34,\n                'EVERY_WINDOW_QUERY_NEEDS_CONFIRMED_CACHE_CLEAR')\n        require(value['ready'] is True and value.get('selected_display') == 0 and\n                type(value.get('selected_window_id')) is int and\n                type(value.get('samples')) is int and 1 <= value['samples'] <= 64 and\n                type(value.get('waited_ms')) is int and 0 <= value['waited_ms'] <= 2000 and\n                timings and timings[-1]['elapsed_ms'] <= value['waited_ms'],\n                'ACTUAL_DISPLAY_ZERO_WINDOW_READINESS_REQUIRED')\n    for name in ('first','last'):\n        if name not in value:\n            require(not ready_required,'COMPLETE_WINDOW_CENSUS_REQUIRED')\n            continue\n        row = value[name]\n        require(isinstance(row,dict) and set(row) == {'sample','event_serial','elapsed_ms','displays','windows'} and\n                type(row['sample']) is int and 1 <= row['sample'] <= 64 and\n                type(row['event_serial']) is int and row['event_serial'] >= 0 and\n                type(row['elapsed_ms']) is int and row['elapsed_ms'] >= 0 and\n                isinstance(row['displays'],list) and len(row['displays']) <= 8 and\n                all(type(d) is int and d >= 0 for d in row['displays']) and\n                isinstance(row['windows'],list) and len(row['windows']) <= 128,'WINDOW_CENSUS_SHAPE')\n        for window in row['windows']:\n            require(isinstance(window,dict) and set(window) == {'display','id','type','focused','active','accessibility_focused','layer'} and\n                    all(type(window[k]) is int for k in ('display','id','type','layer')) and\n                    window['display'] in row['displays'] and\n                    all(type(window[k]) is bool for k in ('focused','active','accessibility_focused')),\n                    'METADATA_ONLY_WINDOW_CENSUS_REQUIRED')\n        require(timings and all(row[key] == timings[0 if name == 'first' else -1][key]\n                for key in ('sample','event_serial','elapsed_ms')), 'WINDOW_CENSUS_TIMING_MISMATCH')\n    if ready_required:\n        require(value['first']['sample'] == 1 and value['last']['sample'] == value['samples'] and\n                sum(window['display'] == 0 and window['type'] == 1 and window['focused'] is True\n                    for window in value['last']['windows']) == 1,'UNIQUE_DISPLAY_ZERO_FOCUSED_WINDOW_REQUIRED')\n        require(sum(window['display'] == 0 and window['id'] == value['selected_window_id'] and\n                    window['type'] == 1 and window['focused'] is True for window in value['last']['windows']) == 1,\n                'SELECTED_WINDOW_MUST_MATCH_ACTUAL_LAST_CENSUS')\n    return value\n\n\ndef select_unique_clickable(inspection, selector):\n    inspect_record(inspection)\n    require(isinstance(selector, dict) and selector and set(selector) <= {'resource_id','text','content_desc','class'},\n            'EXACT_BOUNDED_NODE_SELECTOR_REQUIRED')\n    require(all(isinstance(v, str) and 0 < len(v.encode('utf-8')) <= 256 for v in selector.values()), 'SELECTOR_BOUND')\n    found = [node for node in inspection['nodes'] if node.get('password') is False and\n             node.get('enabled') is True and node.get('visible') is True and node.get('clickable') is True and\n             all(node.get(k) == v and node.get(k + '_truncated') is False for k, v in selector.items())]\n    require(len(found) == 1, 'NODE_SELECTOR_NOT_UNIQUE_AND_ELIGIBLE')\n    return {'node_path': found[0]['path'], 'node_sha256': found[0]['node_sha256']}\n\n\n\ndef select_unique_editable(inspection, selector):\n    inspect_record(inspection)\n    require(isinstance(selector,dict) and {'resource_id','class'}<=set(selector) and\n            set(selector)<={'resource_id','class','text','content_desc'} and\n            selector['class']=='android.widget.EditText' and\n            re.fullmatch(r'com\\.bestbuy\\.android:id/[A-Za-z0-9_]+',selector['resource_id']) and\n            all(isinstance(v,str) and 0<len(v.encode('utf-8'))<=256 for v in selector.values()),\n            'EXACT_OBSERVED_EDIT_RESOURCE_AND_CLASS_REQUIRED')\n    found=[node for node in inspection['nodes'] if node.get('password') is False and\n           node.get('enabled') is True and node.get('visible') is True and node.get('editable') is True and\n           node.get('supports_set_text') is True and\n           all(node.get(k)==v and node.get(k+'_truncated') is False for k,v in selector.items())]\n    require(len(found)==1,'EDIT_SELECTOR_NOT_UNIQUE_AND_ELIGIBLE')\n    return {'node_path':found[0]['path'],'node_sha256':found[0]['node_sha256'],\n            'node_resource_id':found[0]['resource_id']}\n\n\ndef assess_restoration(before, operation, after):\n    \"\"\"These inputs must be parse_completed returns from three joined commands.\"\"\"\n    first, middle, last = before['helper'], operation['helper'], after['helper']\n    require(first['op'] == last['op'] == 'state' and middle['op'] in ('inspect','click','set_text'), 'STATE_OPERATION_STATE_SEQUENCE_REQUIRED')\n    require(len({first['nonce'], middle['nonce'], last['nonce']}) == 3, 'DISTINCT_PHASE_NONCES_REQUIRED')\n    require(first['self_uid'] == middle['self_uid'] == last['self_uid'], 'HELPER_UID_CHANGED')\n    require(first['state'] == middle['accessibility_state_before_connection'] == last['state'] and\n            middle['restoration']['service_info_verified'] is True,\n            'POST_TERMINATION_ACCESSIBILITY_STATE_CHANGED')\n    return {'accessibility_mode_restoration_verified': True,\n            'basis': 'actual own-service readback plus independent no-automation state command after successful instrumentation termination',\n            'state_before': first['state'], 'state_after': last['state'],\n            'wire_sha256': [before['wire_sha256'], operation['wire_sha256'], after['wire_sha256']],\n            'business_success_verified': False, 'whole_app_production_ready': False}\n"
PUBLIC_LABELS=frozenset(('Best Buy','Search','Search Best Buy','Shop','Sign in','Sign In',
    'Continue','Continue as guest','Skip','Loading','Loading...','Loading…','Retry','Try again',
    'Try Again','Cancel','Close','OK','Home','Account','Cart','Not now','Not Now',
    'Accept','Decline','No internet connection','Connection error','Connection Error',
    'Something went wrong','Please try again','Allow','Don\'t allow','While using the app'))
PUBLIC_RESOURCE_IDS=frozenset(('android:id/alertTitle','android:id/message','android:id/button1',
    'android:id/button2','android:id/button3','android:id/content','android:id/progress',
    'android:id/custom','android:id/parentPanel','android:id/topPanel','android:id/buttonPanel',
    'android:id/contentPanel'))
PUBLIC_CLASSES=frozenset(('android.view.View','android.view.ViewGroup','android.widget.FrameLayout',
    'android.widget.LinearLayout','android.widget.RelativeLayout','android.widget.TextView',
    'android.widget.Button','android.widget.ImageButton','android.widget.ImageView',
    'android.widget.EditText','android.widget.ProgressBar','android.widget.ScrollView',
    'android.widget.HorizontalScrollView','android.webkit.WebView','android.app.Dialog',
    'androidx.recyclerview.widget.RecyclerView','androidx.constraintlayout.widget.ConstraintLayout',
    'androidx.appcompat.widget.AppCompatTextView','androidx.appcompat.widget.AppCompatButton',
    'androidx.appcompat.widget.AppCompatImageView'))
BOOL_FIELDS=('visible','enabled','clickable','long_clickable','editable','supports_set_text',
             'password','focusable','focused','selected','checkable','checked','scrollable')

def need(value,reason):
    if not value:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def no_raw_ui(value, path=()):
    if isinstance(value,dict):
        need(not ({'nodes','text','content_desc','raw_tree','raw_ui_tree','screenshot'} & set(value)),
             'RAW_UI_FIELD_FORBIDDEN_IN_SUMMARY_EXPORT')
        for key,item in value.items():
            no_raw_ui(item,path+(key,))
    elif isinstance(value,list):
        for index,item in enumerate(value):
            no_raw_ui(item,path+(str(index),))

class Reader:
    def __init__(self):
        self.started=time.monotonic();self.bytes=0

    def read(self,path,optional=False):
        need(path in FILES.values(),'EXACT_FILE_ALLOWLIST_REQUIRED')
        maximum=262144
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
        try:
            try:
                for name in path.parts[1:-1]:
                    nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
                    os.close(current);current=nxt
                fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
            except FileNotFoundError:
                if optional:
                    return None
                raise
            first=os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
                 0<=first.st_size<=maximum,'ROOT_SINGLE_REGULAR_SUMMARY_BOUND')
            chunks=[];size=0
            while True:
                need(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,maximum+1-size))
                if not part:
                    break
                chunks.append(part);size+=len(part);self.bytes+=len(part)
                need(size<=maximum and self.bytes<=2097152,'TOTAL_READ_BOUND')
            last=os.fstat(fd)
            keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),'FILE_CHANGED')
            return b''.join(chunks)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(current)


def fixed_read(reader,name):
    raw=reader.read(FILES[name])
    need((len(raw),sha(raw))==PINS[name],'EXACT_RETAINED_BYTES_REQUIRED')
    return raw,json.loads(raw.decode('utf-8','strict'))


def public_string(node,key,allowed):
    if key not in node:
        return {'present':False}
    value=node[key]
    need(isinstance(value,str) and len(value.encode('utf-8'))<=2048,'BOUNDED_NODE_STRING_REQUIRED')
    truncated=node.get(key+'_truncated')
    need(truncated is None or type(truncated) is bool,'TRUNCATION_FIELD_TYPE_REQUIRED')
    raw=value.encode('utf-8')
    row={'present':True,'observed_bytes':len(raw),'sha256':sha(raw),'truncated':truncated,
         'public_literal':None,'unknown_content_exported':False}
    if truncated is False and value in allowed:
        row['public_literal']=value
    return row


def project_public_roles(inspection):
    rows=[]
    for node in inspection['nodes']:
        flags={}
        for name in BOOL_FIELDS:
            if name in node:
                need(type(node[name]) is bool,'STRUCTURAL_BOOLEAN_REQUIRED')
                flags[name]=node[name]
        bounds=node.get('bounds')
        need(isinstance(bounds,list) and len(bounds)==4 and
             all(type(x) is int and -32768<=x<=32768 for x in bounds) and
             bounds[0]<=bounds[2] and bounds[1]<=bounds[3],'BOUNDED_NODE_RECT_REQUIRED')
        row={'path':node['path'],'node_sha256':node['node_sha256'],'bounds':bounds,'flags':flags,
             'class':public_string(node,'class',PUBLIC_CLASSES),
             'resource_id':public_string(node,'resource_id',PUBLIC_RESOURCE_IDS),
             'public_label_fields':{}}
        if node.get('password') is False and node.get('visible') is True and not node.get('content_redacted',False):
            for key in ('text','content_desc'):
                row['public_label_fields'][key]=public_string(node,key,PUBLIC_LABELS)
        else:
            row['content_fields_suppressed']=True
        rows.append(row)
    need(len(rows)==12,'EXACT_RETIRED_NODE_COUNT_REQUIRED')
    return rows


def collect():
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    reader=Reader();values={};pins={}
    for name in ('coordinator.json','stage.json','launch.json','inspect.json','cleanup.json'):
        raw,value=fixed_read(reader,name);no_raw_ui(value)
        need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE and
             value.get('package')==PACKAGE and value.get('ok') is True and
             value.get('error') is None and value.get('secondary_errors')==[],
             'EXACT_SUCCESSFUL_RETIRED_PARENT_SCOPE_REQUIRED')
        values[name]=value
        pins[name]={'path':str(FILES[name]),'bytes':len(raw),'sha256':sha(raw)}
    c=values['coordinator.json'];s=values['stage.json'];l=values['launch.json']
    i=values['inspect.json'];r=values['cleanup.json']
    need(s.get('coordinator_result')==pins['coordinator.json'],'STAGE_COORDINATOR_LINK_REQUIRED')
    need(c.get('helper_package')==HELPER_PACKAGE and c.get('helper_uid')==HELPER_UID and
         c.get('uid')==10130 and c.get('flow')==str(FLOW),'EXACT_BESTBUY_HELPER_SCOPE_REQUIRED')
    fields={'launch':'launch_result','inspect':'inspection_result','cleanup':'cleanup_result'}
    need(set(c['retained_phase_results'])==set(fields),'THREE_RETAINED_PHASES_REQUIRED')
    for phase,field in fields.items():
        value=values[phase+'.json']
        need(c[field]==c['retained_phase_results'][phase]==pins[phase+'.json'],
             'PARENT_PHASE_PIN_LINK_REQUIRED')
        need(value.get('phase')==phase and value.get('package')==PACKAGE and value.get('uid')==10130 and
             value.get('helper_package')==HELPER_PACKAGE and value.get('helper_uid')==HELPER_UID and
             value.get('final_Main_guard_passed') is True and value.get('held_binding_released') is True and
             value.get('flow_lock_released') is True and value.get('source_and_artifact_unchanged') is True,
             'EXACT_RETIRED_PHASE_AND_RELEASE_REQUIRED')
        need(value['Main_before_lock']==value['Main_before']==value['Main_after']==c['Main_before']==c['Main_after']==
             s['Main_before']==s['Main_after'],'ORIGINAL_MAIN_FENCE_EQUALITY_REQUIRED')
        need(value['target_before']==value['target_after'],'TARGET_APK_BEFORE_AFTER_REQUIRED')
    task=c['owned_task']
    need(task==l['owned_task']==r['owned_task']==i['sequence']['owned_task'] and
         task['task']==1030 and task['package']==PACKAGE and task['prelaunch_absent'] is True and
         task['prelaunch_task_ids']==[851] and task['cleanup_allowed'] is True,
         'EXACT_HISTORICAL_OWNED_TASK_REQUIRED')
    need(c['owned_task_absent_after_cleanup'] is True and r['owned_task_absent'] is True and
         c['task_ids_after']==r['task_ids_after']==r['cleanup']['task_ids_after']==[851] and
         r['cleanup']['new_leaf_removed_and_verified'] is True and r['cleanup']['other_tasks_preserved'] is True,
         'TASK_ALREADY_RETIRED_REQUIRED')
    need(i['inspection_completed'] is True and i['action_attempted'] is False and i['outcome_unknown'] is False and
         i['sequence']['restoration_qualified'] is True and i['sequence']['post_state_matches_before'] is True and
         i['sequence']['after_state_completed'] is True and i['sequence']['installed_before']==i['sequence']['installed_after'],
         'READ_ONLY_INSPECT_AND_POST_STATE_REQUIRED')
    need(sha(QA_SOURCE.encode('utf-8'))==QA_SHA,'EXACT_PURE_ASSESSOR_SOURCE_REQUIRED')
    qa=types.ModuleType('bestbuy_r2_exact_pure_assessor')
    exec(compile(QA_SOURCE,'<pinned-bestbuy-r2-qa-contract>','exec'),qa.__dict__)
    raw,assessment=fixed_read(reader,'assessment.json')
    pins['assessment.json']={'path':str(FILES['assessment.json']),'bytes':len(raw),'sha256':sha(raw)}
    helper=assessment['helper'];saved=i['assessments']['inspect']
    need(saved['assessment_bytes']==len(raw) and saved['assessment_sha256']==sha(raw) and
         helper['protocol']==qa.PROTOCOL and helper['nonce']==INSPECT_NONCE and helper['op']=='inspect' and
         helper['self_uid']==HELPER_UID and helper['target_uid_verified']==10130 and
         helper['ok'] is True and helper['error'] is None and helper['secondary_errors']==[] and
         helper['action_attempted'] is False and helper['outcome_unknown'] is False and
         assessment['actual_command_returncode']==0 and assessment['actual_instrumentation_finish_code']==-1 and
         assessment['held_transport_returned_after_post_guard'] is True,
         'EXACT_RETAINED_PRIVATE_ASSESSMENT_REQUIRED')
    need(assessment['wire_sha256']==sha(qa.canonical(helper))==saved['wire_sha256']==
         i['sequence']['inspection_wire_sha256']=='a97f329c3f07e7abf89a37602a75796a68b4469a6607b06919beaf9cd73c03be',
         'EXACT_CANONICAL_INSPECTION_WIRE_REQUIRED')
    need(qa.scope(helper['host_scope_attestation'])==i['sequence']['foreground_before']==
         i['sequence']['foreground_after'],'HISTORICAL_FOREGROUND_SCOPE_REQUIRED')
    ins=qa.inspect_record(helper['inspection'])
    window=qa.window_observation(helper['window_observation'])
    counters=qa.tree_observations(helper['tree_observations'],'inspect',True)
    actual={'tree_sha256':ins['tree_sha256'],'window_sha256':ins['window_sha256'],
        'node_count':len(ins['nodes']),'window':{key:ins['window'][key] for key in ('package','display','type','focused')},
        'window_observation':window,'connection_scoped_window_id':ins['connection_scoped_window_id'],
        'tree_observations':counters,'complete':True,'raw_tree_private_only':True}
    need(all(saved[key]==value for key,value in actual.items()),'SAVED_COMPLETE_OBSERVATION_MUST_MATCH')
    need(counters[0]['emitted_nodes']==len(ins['nodes'])==12 and counters[0]['max_attempted_depth']==8 and
         counters[0]['serialized_bytes']==len(qa.canonical(ins)) and
         window['selected_window_id']==ins['connection_scoped_window_id'],'COUNTER_AND_WINDOW_BINDING_REQUIRED')
    roles=project_public_roles(ins)
    report={'schema':1,'kind':'bestbuy-r2-retired-public-roles-read01','collection_complete':True,
        'historical_inputs':pins,'pure_assessor_sha256':QA_SHA,'source_manifest_sha256':SOURCE_SHA,
        'retired_task':1030,'task_ids_after_cleanup':[851],'original_complete_node_count':12,
        'original_max_depth':8,'original_depth_limit':128,'historical_tree_sha256':ins['tree_sha256'],
        'historical_window_sha256':ins['window_sha256'],'original_restoration_qualified':True,
        'public_role_rows':roles,'public_labels_whitelist':sorted(PUBLIC_LABELS),
        'public_resource_ids_whitelist':sorted(PUBLIC_RESOURCE_IDS),
        'raw_UI_or_pixels_exported':False,'unknown_text_description_or_ID_exported':False,
        'runtime_qualification_asserted':False,'new_action_authority':False,
        'landing_or_splash_classification_asserted':False,'depth33_runtime_path_proved':False,
        'Android_or_process_actions':0,'permission_or_original_file_changes':0,
        'read_bytes':reader.bytes,'input_files':6,
        'read_lifecycle':'inherited Reader verifies held stat before/after; no terminal named-path recheck or atomic-snapshot claim'}
    need(time.monotonic()-reader.started<8,'READ_AND_PROJECTION_DEADLINE')
    output=(json.dumps(report,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')
    need(len(output)<=65536,'PUBLIC_ROLE_REPORT_BOUND')
    print(output.decode('ascii'),end='',flush=True)
    return 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collect-once',action='store_true')
    args=p.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','files':{k:str(v) for k,v in FILES.items()},'remote_actions':0}))
        return 0
    try:
        return collect()
    except BaseException as error:
        code=str(error)
        safe=code if re.fullmatch('[A-Z][A-Z0-9_]{0,127}',code) else 'FIXED_PRIVATE_INPUT_OR_PREDICATE_FAILED'
        print(json.dumps({'schema':1,'kind':'bestbuy-r2-retired-public-roles-read01',
            'collection_complete':False,'error_type':type(error).__name__,'error_code':safe,
            'runtime_qualification_asserted':False,'new_action_authority':False,
            'raw_UI_or_pixels_exported':False,'Android_or_process_actions':0},sort_keys=True),flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
