#!/usr/bin/env python3
"""Read one exact retired R6 control observation; emit public control metadata only.

No Android, process, namespace, input, screenshot or audio operation. The full
fixed assessment is read only to verify its pinned canonical wire and complete
inspection; output is restricted to its verified control-container subtree.
Unknown commercial text/descriptions and every node outside that subtree are
omitted from output. This retired observation grants no future action authority.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

ROOT=Path('/home/alex/work/pocket4-bilibili-r6-controls-reveal-01')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r6-flow-395ea60f6cff2da163672b2f660131a4')
STEP=FLOW/'steps/controls-reveal-01'
NONCE='395ea60f6cff2da163672b2f660131a4'
INSPECT_NONCE='234fec58dcab499091b31feb950ec438'
SOURCE_SHA='59401749d76711faeb9e9bc0326039d34661c8e27d364d9c9cfdbf23cf63e795'
EPOCH='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
QA_SOURCE=Path('/home/alex/work/pocket4-owned-bili-qa-r6-source-01/source/qa_contract.py')
QA_SHA='871c784812063739a6ab976784fb38243af52266b0d9a95aa1244779ccd2c005'
REVEAL_SOURCE=ROOT/'source/controls_reveal.py'
REVEAL_SHA='8836a366f995f07470210c1ab2d6e25e265572bc1c8aed3685f30a94cf7c8a9b'
WIRE_SHA='73f69809b9a3af386c61f2183b60270077a86c37a8eba4ab9670e230c8a82bc2'
INPUTS={
    'coordinator':(ROOT/'result.json',198643,'acb1b45d1093c47fc38b5c8eb52c9587eb767ec4d1cc6bfdeb514af2c7bb2305',0),
    'stage':(ROOT/'stage-result.json',1647,'62426a0c217286e11f8a8a3c458f3625d8446fd64546de3e5d3c922e2bd4ab2f',0),
    'navigation':(STEP/'result.json',220311,'60f34589dc30aeeec9f9c46278222fa4e26b400f7e7c6b468e619b9ec18314b9',0),
    'cleanup':(FLOW/'steps/cleanup-01/result.json',464,'dce6110752e5747d09d7fd0021c80dd643e3090bef28cbd16a827bcca1254bac',0),
    'source_manifest':(ROOT/'source/SOURCE_PINS.json',992,SOURCE_SHA,0),
    'qa_contract':(QA_SOURCE,39280,QA_SHA,1000),
    'reveal':(REVEAL_SOURCE,10981,REVEAL_SHA,0),
    'independent':(STEP/(INSPECT_NONCE+'.assessment.json'),228168,'60d3cedb4d18aac3146a9607d869c7a5f39c34496f95ebefa849936cbc1e2cab',0),
    'independent_request':(STEP/(INSPECT_NONCE+'.request.json'),None,None,0),
}


PUBLIC_CONTROL_LABELS = frozenset(('Play', 'Pause', 'Resume', 'Back', 'Replay',
    'Fullscreen', 'Full screen', 'Exit full screen', 'Seek', '播放', '暂停',
    '继续播放', '返回', '重播', '全屏', '退出全屏'))

PUBLIC_CLASSES = frozenset(('android.view.View', 'android.view.ViewGroup',
    'android.view.SurfaceView', 'android.widget.FrameLayout', 'android.widget.LinearLayout',
    'android.widget.RelativeLayout', 'android.widget.ImageButton', 'android.widget.ImageView',
    'android.widget.TextView', 'android.widget.Button', 'android.widget.SeekBar',
    'android.widget.ProgressBar', 'android.widget.CheckBox', 'android.widget.ToggleButton'))

ROLE_IDS = {'area': 'tv.danmaku.bili:id/video_area',
    'container': 'tv.danmaku.bili:id/video_container',
    'overlay': 'tv.danmaku.bili:id/video_area_float_layer_container',
    'toolbar': 'tv.danmaku.bili:id/collapsing_toolbar',
    'controls': 'tv.danmaku.bili:id/control_container'}

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

class Reader:
    def __init__(self):
        self.started = time.monotonic(); self.bytes = 0; self.records = []

    def read(self, name):
        need(name in INPUTS, 'FIXED_NINE_INPUT_ALLOWLIST_REQUIRED')
        path, size, expected, owner = INPUTS[name]
        current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); fd = None
        try:
            for component in path.parts[1:-1]:
                nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=current)
                os.close(current); current = nxt
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            first = os.fstat(fd)
            bound = 4096 if name.endswith('_request') else 1048576
            need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_uid == owner
                 and 0 < first.st_size <= bound, 'FIXED_OWNER_SINGLE_FILE_BOUND')
            need(size is None or first.st_size == size, 'EXACT_INPUT_SIZE_CHANGED')
            chunks = []; count = 0
            while True:
                need(time.monotonic() - self.started < 8, 'READ_DEADLINE')
                part = os.read(fd, min(16384, bound + 1 - count))
                if not part:
                    break
                chunks.append(part); count += len(part); self.bytes += len(part)
                need(count <= bound and self.bytes <= 3145728, 'TOTAL_RETAINED_READ_BOUND')
            last = os.fstat(fd)
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
                      'st_size', 'st_mtime_ns', 'st_ctime_ns')
            need(count == first.st_size and all(getattr(first, k) == getattr(last, k) for k in fields),
                 'INPUT_CHANGED')
            raw = b''.join(chunks)
            need(expected is None or sha(raw) == expected, 'EXACT_INPUT_PIN_CHANGED')
            self.records.append({'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)})
            return raw
        finally:
            if fd is not None:
                os.close(fd)
            os.close(current)

def safe_label(node, key):
    # Unknown text is never returned, even if it looks like a UI label.
    value = node.get(key)
    if node.get(key + '_truncated') is False and isinstance(value, str) and value in PUBLIC_CONTROL_LABELS:
        return value
    return None

def controls_metadata(inspection, proof):
    """No action selection: report bounded nodes only inside the verified control-container subtree."""
    nodes = inspection['nodes']; role_nodes = {}
    for role, resource in ROLE_IDS.items():
        rows = [node for node in nodes if node['resource_id'] == resource and
                node['resource_id_truncated'] is False and node['class'] == 'android.widget.FrameLayout'
                and node['class_truncated'] is False and node['visible'] is True
                and node['enabled'] is True and node['password'] is False]
        need(len(rows) == 1, 'VERIFIED_PLAYER_ROLE_MUST_REMAIN_UNIQUE')
        role_nodes[role] = rows[0]
    area_path = role_nodes['controls']['path']
    rows = []; redacted = 0; outside = 0
    for node in nodes:
        inside = node['path'] == area_path or node['path'].startswith(area_path + '/')
        if not inside:
            outside += 1; continue
        if node['visible'] is not True or node['password'] is not False:
            redacted += 1; continue
        need(len(rows) < 128, 'PLAYER_CONTROL_METADATA_ROW_BOUND')
        resource = node['resource_id']
        resource_safe = (node['resource_id_truncated'] is False and isinstance(resource, str) and
                         (resource == '' or re.fullmatch(r'tv\.danmaku\.bili:id/[A-Za-z0-9_]{1,128}', resource)))
        class_safe = node['class_truncated'] is False and node['class'] in PUBLIC_CLASSES
        parent_path = node['path'].rsplit('/', 1)[0] if '/' in node['path'] else None
        row = {'node_sha256': node['node_sha256'], 'path_sha256': sha(node['path'].encode()),
               'parent_path_sha256': sha(parent_path.encode()) if parent_path is not None else None,
               'resource_id': resource if resource_safe else None,
               'resource_id_sha256': node['resource_id_sha256'],
               'resource_id_complete': node['resource_id_truncated'] is False,
               'class_name': node['class'] if class_safe else None, 'class_sha256': node['class_sha256'],
               'class_complete': node['class_truncated'] is False,
               'bounds': node['bounds'], 'child_count': node['child_count'],
               'inside_fixed_roles': {role: node['path'] == value['path'] or
                   node['path'].startswith(value['path'] + '/') for role, value in role_nodes.items()},
               'same_bounds_as_crop': node['bounds'] == proof['crop'],
               'visible': True, 'password': False,
               'enabled': node['enabled'], 'clickable': node['clickable'], 'focused': node['focused'],
               'selected': node['selected'], 'checked': node['checked'], 'editable': node['editable'],
               'supports_set_text': node['supports_set_text'],
               'text_sha256': node['text_sha256'], 'description_sha256': node['content_desc_sha256'],
               'text_complete': node['text_truncated'] is False,
               'description_complete': node['content_desc_truncated'] is False,
               'public_text_label': safe_label(node, 'text'),
               'public_description_label': safe_label(node, 'content_desc'),
               'standalone_time_pattern': node['text_truncated'] is False and
                   re.fullmatch(r'(?:[0-9]{1,2}:)?[0-9]{1,3}:[0-9]{2}', node['text']) is not None}
        rows.append(row)
    return {'rows': rows, 'row_count': len(rows), 'outside_control_container_nodes_omitted': outside,
            'invisible_or_password_nodes_omitted': redacted,
            'clickable_visible_enabled_count': sum(row['clickable'] is True and row['enabled'] is True for row in rows),
            'seekbar_class_count': sum(row['class_name'] == 'android.widget.SeekBar' for row in rows),
            'accessibility_range_or_set_progress_support_observed': False,
            'actions_list_in_original_helper_schema': False,
            'control_presence_does_not_authorize_action': True}

def no_raw_ui(value):
    if isinstance(value, dict):
        need(not ({'nodes', 'text', 'content_desc', 'inspection', 'screenshot', 'pixels',
                   'raw_tree', 'raw_ui_tree'} & set(value)), 'RAW_UI_EXPORT_FORBIDDEN')
        for item in value.values():
            no_raw_ui(item)
    elif isinstance(value, list):
        for item in value:
            no_raw_ui(item)


def validate_retained(c, s, n, cleanup):
    for value in (c, s, n):
        need(value['nonce'] == NONCE and value['source_manifest_sha256'] == SOURCE_SHA
             and value['ok'] is True and value['error'] is None and value['secondary_errors'] == []
             and value['business_success_verified'] is False and value['whole_app_production_ready'] is False,
             'EXACT_RETAINED_SCOPED_SUCCESS_REQUIRED')
    need(c['Main_before'] == c['Main_after'] == s['Main_before'] == s['Main_after']
         and c['Main_before']['Main_epoch_sha256'] == EPOCH
         and c['Main_before']['resource_limits_match'] is True,
         'ORIGINAL_MAIN_GUARD_CHAIN_REQUIRED')
    for parent, key, name in ((s, 'coordinator_result', 'coordinator'),
                              (c, 'navigation_result', 'navigation'), (c, 'cleanup_result', 'cleanup')):
        path, size, digest, _ = INPUTS[name]
        need(parent[key] == {'path':str(path), 'bytes':size, 'sha256':digest},
             'EXACT_RETAINED_PARENT_PIN_REQUIRED')
    need(c['package'] == n['package'] == 'tv.danmaku.bili' and c['uid'] == n['uid'] == 10117
         and c['helper_package'] == n['helper_package'] == 'org.droidloom.qa.bili.r6'
         and c['helper_uid'] == n['helper_uid'] == 10184
         and c['business_outcome_unknown'] is True and n['business_outcome_unknown'] is True
         and n['outcome_unknown'] is True and c['source_and_artifact_unchanged'] is True
         and s['source_unchanged'] is True
         and all(n[k] is True for k in ('final_Main_guard_passed', 'held_binding_released',
             'action_lock_released', 'controls_reveal_and_observation_completed')),
         'EXACT_ORIGINAL_R6_FINAL_GATES_REQUIRED')
    need(c['owned_task']['task'] == 970 and c['owned_task']['prelaunch_task_ids'] == [851, 968, 969]
         and c['owned_task']['prelaunch_absent'] is True and c['owned_task_absent_after_cleanup'] is True
         and cleanup['ok'] is True and cleanup['outcome_unknown'] is False
         and cleanup['epoch_sha256'] == EPOCH
         and ((cleanup.get('new_leaf_removed_and_verified') is True and
               cleanup.get('other_tasks_preserved') is True) or
              (cleanup.get('new_task_already_absent') is True and cleanup.get('removal_attempted') is False)),
         'ORIGINAL_EXACT_TASK_CLEANUP_REQUIRED')
    if 'task_ids_after' in cleanup:
        need(970 not in cleanup['task_ids_after'] and
             set(c['owned_task']['prelaunch_task_ids']).issubset(cleanup['task_ids_after']),
             'ORIGINAL_TASK_RETIREMENT_AND_PREEXISTING_PRESERVATION_REQUIRED')
    record = c['navigation']['controls_reveal_observation']
    need(record == n['controls_reveal_observation'] and record['input_acknowledged'] is True
         and record['independent_read_completed'] is True and record['controls_revealed_observed'] is True
         and record['atomic_input_target_attribution'] is False and record['pause_seek_or_audio_qualified'] is False
         and record['business_success_verified'] is False and record['automatic_retry'] is False,
         'BOUND_ONE_INPUT_AND_INDEPENDENT_OBSERVATION_REQUIRED')
    return record


def collect():
    need(os.getuid() == os.geteuid() == 0, 'ROOT_FIXED_RETAINED_READ_REQUIRED')
    reader = Reader()
    values = {name:json.loads(reader.read(name)) for name in ('coordinator','stage','navigation','cleanup')}
    record = validate_retained(values['coordinator'],values['stage'],values['navigation'],values['cleanup'])
    manifest = json.loads(reader.read('source_manifest'))
    need(manifest['files']['controls_reveal.py'] == {'bytes':10981,'sha256':REVEAL_SHA},
         'EXACT_ORIGINAL_REVEAL_MODULE_REQUIRED')
    qa = types.ModuleType('exact_r6_contract'); qa.__file__ = str(QA_SOURCE)
    exec(compile(reader.read('qa_contract'),str(QA_SOURCE),'exec'),qa.__dict__)
    reveal = types.ModuleType('exact_reveal_observation'); reveal.__file__ = str(REVEAL_SOURCE)
    exec(compile(reader.read('reveal'),str(REVEAL_SOURCE),'exec'),reveal.__dict__)
    need(qa.PROTOCOL == 'pocket4-owned-bili-qa-v6'
         and reveal.POST_PLAN['nonces']['inspect'] == INSPECT_NONCE,
         'EXACT_RETAINED_INDEPENDENT_INSPECTION_PLAN_REQUIRED')
    qa.touch_observation(record['input_lifecycle'],True)
    sequence = record['independent_sequence']; metadata = record['independent_assessment']
    observed = record['independent_observation']; scope = record['final_scope']
    qa.scope(scope)
    need(metadata['nonce'] == INSPECT_NONCE and metadata['operation'] == 'inspect'
         and metadata['assessment_bytes'] == INPUTS['independent'][1]
         and metadata['assessment_sha256'] == INPUTS['independent'][2]
         and metadata['wire_sha256'] == sequence['inspection_wire_sha256'] == WIRE_SHA
         and metadata['actual_command_returncode'] == 0 and metadata['actual_instrumentation_finish_code'] == -1
         and sequence['foreground_before'] == sequence['foreground_after'] == scope
         and sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True
         and sequence['post_state_matches_before'] is True
         and sequence['post_termination_state']['ui_automation_connected'] is False
         and sequence['installed_before'] == sequence['installed_after'] == values['navigation']['live_installed_before']
         and sequence['installed_before']['uid'] == 10184
         and sequence['installed_before']['apk_sha256'] == 'f7df7d6ce8dd0ed2ab7a8cda929d5b06e2b097c358490b32450c4a238bc1562a',
         'EXACT_COMPLETED_INDEPENDENT_SEQUENCE_REQUIRED')
    raw = reader.read('independent'); assessed = json.loads(raw); helper = assessed['helper']
    need(assessed['held_transport_returned_after_post_guard'] is True
         and assessed['actual_command_returncode'] == 0 and assessed['actual_instrumentation_finish_code'] == -1
         and helper['ok'] is True and helper['error'] is None and helper['secondary_errors'] == []
         and helper['protocol'] == qa.PROTOCOL and helper['nonce'] == INSPECT_NONCE and helper['op'] == 'inspect'
         and helper['self_uid'] == 10184 and helper['action_attempted'] is False
         and helper['outcome_unknown'] is False
         and sha(qa.canonical(helper)) == assessed['wire_sha256'] == WIRE_SHA,
         'EXACT_CANONICAL_SUCCESSFUL_READ_ONLY_WIRE_REQUIRED')
    request = json.loads(reader.read('independent_request')); qa.validate_request(request)
    need(request == {'protocol':qa.PROTOCOL,'nonce':INSPECT_NONCE,'op':'inspect','scope':scope}
         and helper['host_scope_attestation'] == scope and sha(qa.canonical(request)) == helper['request_sha256'],
         'EXACT_RETAINED_REQUEST_AND_SCOPE_REQUIRED')
    inspection = qa.inspect_record(helper['inspection'])
    window = qa.window_observation(helper['window_observation'])
    counters = qa.tree_observations(helper['tree_observations'],'inspect',True)
    actual_observed = reveal.controls_evidence(qa,inspection,scope)
    need(actual_observed == observed and observed['complete'] is True and observed['node_count'] == 175
         and len(inspection['nodes']) == 175 and observed['complete_control_descendant_count'] == 8
         and observed['visible_enabled_clickable_count'] == 2 and observed['visible_enabled_seekbar_count'] == 0
         and qa.same_reveal_frame(record['immediate_post_observation']['proof'],observed['proof']),
         'COMPLETE_ORIGINAL_PUBLIC_CONTROLS_OBSERVATION_REQUIRED')
    controls = controls_metadata(inspection,{'crop':observed['proof']['viewport_bounds']})
    need(controls['clickable_visible_enabled_count'] == 2 and controls['seekbar_class_count'] == 0,
         'EXACT_CONTROL_SUBTREE_COUNTS_REQUIRED')
    result = {'schema':1,'state':'COLLECTED_RETIRED_R6_PUBLIC_CONTROL_METADATA_ONLY',
        'flow_nonce':NONCE,'source_manifest_sha256':SOURCE_SHA,'inspection_nonce':INSPECT_NONCE,
        'assessment_sha256':sha(raw),'wire_sha256':WIRE_SHA,'scope':scope,
        'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
        'complete_node_count':175,'complete_control_descendant_count':8,
        'window_ready':window['ready'],'cache_attempts':window['cache_attempts'],
        'cache_clears':window['cache_clears'],'cache_last_result':window['cache_last_result'],
        'tree_observations':counters,
        'proof':observed['proof'],'controls':controls,'original_cleanup':values['cleanup'],
        'original_owned_task':970,'prelaunch_task_ids':[851,968,969],
        'input_file_pins':reader.records,'input_bytes':reader.bytes,
        'outside_control_container_nodes_omitted':True,'observed_task_already_retired':True,
        'reuse_for_click_forbidden':True,'Android_or_process_actions':0,
        'raw_commercial_tree_or_unknown_text_or_descriptions_or_pixels_exported':False,
        'pause_resume_seek_functionality_verified':False,'playback_or_audio_verified':False,
        'business_outcome_unknown_preserved':True,'whole_app_ready':False}
    no_raw_ui(result)
    output = (json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(output) <= 131072, 'COMPLETE_METADATA_OUTPUT_BOUND')
    print(output.decode(),end='',flush=True)
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once',action='store_true'); args=parser.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','fixed_files':[str(v[0]) for v in INPUTS.values()],
            'file_count':len(INPUTS),'complete_output_bound_bytes':131072,
            'Android_or_process_actions':0,'unknown_text_or_pixels_exported':False}))
        return 0
    return collect()


if __name__ == '__main__':
    raise SystemExit(main())
