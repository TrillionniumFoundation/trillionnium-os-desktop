#!/usr/bin/env python3
"""Fixed historical current-IHG Destination public edit structure; no UI or process action.

Only one exact retired-task assessment is inspected in memory. Unknown text,
labels, identifiers, nodes, coordinates and pixels are never exported.
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

ROOT=Path('/home/alex/work/pocket4-ihg-r2-public-search-destination-entry-01')
FLOW=Path('/home/alex/work/pocket4-ihg-owned-qa-r2-flow-b2cd08fcaad1f2faaed5de2ff5df01af')
STEP=FLOW/'steps/inspect-01'
NONCE='b2cd08fcaad1f2faaed5de2ff5df01af'
SOURCE_SHA='996ad8e7072afdf3a4288eebb8488d5dcfcdd073f533b0c535d127b3e6c0424d'
QA_SOURCE=Path('/home/alex/work/pocket4-owned-ihg-qa-r2-source-02/source/qa_contract.py')
QA_SHA='e48cc66772f7340ddb2e70abbc1f6151ea3c3300e17b7468aadeae3cf4372f4a'
QA_MANIFEST='aac50aec5289c542268c8cff29a07d91ef1be68eb57acb4474c6196850836d38'
INSPECT_NONCE='cbc5587e16902bdaffb4463c7ec48be4'
INSPECT_WIRE='0defbeba8ab922da5d5d1aa9edd485ad3d0fe1d3b00c684897a5a56dbc896319'
PINS={
 ROOT/'result.json':(66601,'4e8a10c1397238f9e90b95b5a210fa209dde5d45891b6483afce443c69d1166a'),
 ROOT/'stage-result.json':(2624,'1567db7d80f57f93a1046cebb33108b770007a85b6f4f7a448859a2116381fb0'),
 STEP/'result.json':(175619,'0d7b3f8fa1ec2ad1012bd3cc85983a1ba36d23b7720ed6be575691e20906a96b'),
 FLOW/'steps/cleanup-01/result.json':(11440,'385216fb4be313de0f2f1c54fcc917bfd44a05ba30d450261845200d3264c2ec'),
 QA_SOURCE:(28714,QA_SHA),
 STEP/(INSPECT_NONCE+'.assessment.json'):(81588,'67b166c181f530cabd8523ed2975c80b756545a9ff1297557ed3068fecc31ef9'),
}
FILES={p:1000 if p==QA_SOURCE else 0 for p in PINS}
# Query candidates only: none of these labels or resource IDs is claimed observed.
PUBLIC_ROLES={
 'find_hotel':('find a hotel','find hotels','search hotels','search for hotels','book a hotel','find and book','find & book'),
 'search_tab':('search',),'hotels_tab':('hotels',),'book_tab':('book',),'home_tab':('home',),
 'guest_continue':('continue as guest','continue without signing in','browse as guest'),
 'defer_signin':('not now','maybe later','skip'),
 'onboarding_continue':('get started','next','continue'),
 'destination':('destination','where are you going?','city, airport or hotel','search destinations'),
 'dates':('dates','check-in','check out','check-out','check in'),
 'rooms_guests':('rooms','guests','rooms and guests','rooms & guests'),
 'sign_in':('sign in','log in'),'join':('join','join now','create account','create an account'),
 'retry':('retry','try again'),'fixed_network_error':('no internet connection','something went wrong'),
 'find_hotel_zh':('查找酒店','搜索酒店','酒店搜索','预订酒店'),
 'guest_continue_zh':('以游客身份继续','游客访问','暂不登录','跳过'),
 'destination_zh':('目的地','城市、机场或酒店'),
}
PUBLIC_RESOURCES=(
 'android:id/button1','android:id/button2','android:id/button3','android:id/search_src_text',
 'com.ihg.apps.android:id/search_button','com.ihg.apps.android:id/btn_search',
 'com.ihg.apps.android:id/search','com.ihg.apps.android:id/destination',
 'com.ihg.apps.android:id/book','com.ihg.apps.android:id/skip',
 'com.ihg.apps.android:id/continue_as_guest','com.ihg.apps.android:id/bottom_navigation',
)
PUBLIC_CLASSES=('android.widget.TextView','android.widget.Button','android.widget.EditText',
 'android.widget.ImageButton','android.widget.ImageView','android.widget.FrameLayout',
 'android.widget.LinearLayout','android.view.ViewGroup','android.view.View','android.webkit.WebView')

def need(value, reason):
    if not value:raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

class Reader:
    def __init__(self):
        self.started=time.monotonic();self.bytes=0;self.records=[]

    def read(self,path,expected=None,size=None):
        need(path in FILES,'FIXED_SIX_FILE_ALLOWLIST_REQUIRED')
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
        try:
            for name in path.parts[1:-1]:
                nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
                os.close(current);current=nxt
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
            first=os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==FILES[path]
                 and 0<first.st_size<=1048576,'FIXED_OWNER_SINGLE_FILE_BOUND')
            chunks=[];count=0
            while True:
                need(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,1048577-count))
                if not part:break
                chunks.append(part);count+=len(part);self.bytes+=len(part)
                need(count<=1048576 and self.bytes<=3145728,'TOTAL_STRUCTURE_READ_BOUND')
            last=os.fstat(fd)
            keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            need(count==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),'INPUT_CHANGED')
            raw=b''.join(chunks)
            need(expected is None or sha(raw)==expected,'EXACT_INPUT_PIN_CHANGED')
            need(size is None or len(raw)==size,'EXACT_INPUT_SIZE_CHANGED')
            self.records.append({'path':str(path),'bytes':len(raw),'sha256':sha(raw)})
            return raw
        finally:
            try:
                if fd is not None:os.close(fd)
            finally:os.close(current)

def no_raw_ui(value):
    if isinstance(value,dict):
        need(not ({'nodes','text','content_desc','inspection','screenshot','pixels','raw_tree','raw_ui_tree'}&set(value)),
             'RAW_UI_EXPORT_FORBIDDEN')
        for item in value.values():no_raw_ui(item)
    elif isinstance(value,list):
        for item in value:no_raw_ui(item)

def validated_assessment(qa,assessed,nonce,wire,scope):
    helper=assessed['helper']
    need(assessed.get('held_transport_returned_after_post_guard') is True and
         assessed.get('actual_command_returncode')==0 and assessed.get('actual_instrumentation_finish_code')==-1 and
         helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors')==[] and
         helper.get('protocol')==qa.PROTOCOL and helper.get('nonce')==nonce and helper.get('op')=='inspect' and
         helper.get('self_uid')==10153 and helper.get('action_attempted') is False and helper.get('outcome_unknown') is False and
         helper.get('claim_persistence_completed') is True and helper.get('helper_work_completed') is True and
         helper.get('automatic_retry') is False and helper.get('business_success_verified') is False,
         'ACTUAL_SUCCESSFUL_NO_ACTION_INSPECTION_REQUIRED')
    need(sha(qa.canonical(helper))==assessed.get('wire_sha256')==wire,'ACTUAL_CANONICAL_HELPER_WIRE_PIN_REQUIRED')
    expected_request={'protocol':qa.PROTOCOL,'nonce':nonce,'op':'inspect','scope':scope}
    raw_request=qa.validate_request(expected_request)
    need(helper.get('request_sha256')==sha(raw_request) and helper.get('host_scope_attestation')==scope and
         helper.get('target_uid_verified')==qa.UID,'EXACT_RETAINED_REQUEST_SCOPE_REQUIRED')
    restore=helper.get('restoration')
    need(isinstance(restore,dict) and restore.get('service_info_verified') is True and
         restore.get('service_info_captured') is True and restore.get('connection_flags')==1 and
         helper.get('requires_post_termination_state_check') is True,'ORIGINAL_OWN_SERVICE_RESTORATION_REQUIRED')
    inspection=qa.inspect_record(helper['inspection'])
    window=qa.window_observation(helper['window_observation'])
    counters=qa.tree_observations(helper['tree_observations'],'inspect',True)
    need(window['selected_window_id']==inspection['connection_scoped_window_id'] and
         counters[0]['emitted_nodes']==len(inspection['nodes']) and
         counters[0]['serialized_bytes']==len(qa.canonical(inspection)),
         'ORIGINAL_COMPLETE_INSPECTION_AND_WINDOW_COUNTERS_REQUIRED')
    return helper,inspection,window,counters

def fixed_pin(path):
    size,digest=PINS[path]
    return {'path':str(path),'bytes':size,'sha256':digest}


def validate_retained(c,s,phase,cleanup):
    for value in (c,s,phase,cleanup):
        need(value.get('nonce')==NONCE and value.get('source_manifest_sha256')==SOURCE_SHA and
             value.get('package')=='com.ihg.apps.android' and value.get('ok') is True and
             value.get('error') is None and value.get('secondary_errors')==[] and
             value.get('business_success_verified') is False and value.get('whole_app_production_ready') is False,
             'EXACT_COMPLETED_CURRENT_IHG_FLOW_REQUIRED')
        need(value.get('Main_before')==value.get('Main_after')==c['Main_before'],
             'EXACT_ORIGINAL_MAIN_CHAIN_REQUIRED')
    main=c['Main_before']
    need(main.get('schema')=='pocket4-current-main-guard-v1' and
         main.get('Main_epoch_sha256')=='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2' and
         main.get('current_baseline_sha256')=='163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266' and
         main.get('current_baseline_qualification_sha256')=='f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6',
         'EXACT_CURRENT_TYPED_HISTORICAL_MAIN_REQUIRED')
    need(c.get('flow')==str(FLOW) and c.get('helper_uid')==10153 and
         c.get('helper_package')=='org.droidloom.qa.ihg.r2' and c.get('uid')==10137 and
         c.get('explicit_search_then_destination_completed') is True and
         c.get('destination_click_and_observation_completed') is True and c.get('business_outcome_unknown') is True and
         c.get('source_and_artifact_unchanged') is True and s.get('source_unchanged') is True,
         'EXACT_IHG_HELPER_AND_SOURCE_REQUIRED')
    need(s.get('coordinator_result')==fixed_pin(ROOT/'result.json') and
         c.get('inspection_result')==c.get('retained_phase_results',{}).get('inspect')==fixed_pin(STEP/'result.json') and
         c.get('cleanup_result')==c.get('retained_phase_results',{}).get('cleanup')==fixed_pin(FLOW/'steps/cleanup-01/result.json'),
         'EXACT_PARENT_CHILD_RESULT_PINS_REQUIRED')
    for value,kind in ((phase,'inspect'),(cleanup,'cleanup')):
        need(value.get('phase')==kind and value.get('helper_package')=='org.droidloom.qa.ihg.r2' and
             value.get('helper_uid')==10153 and value.get('uid')==10137 and
             value.get('outcome_unknown') is (kind=='inspect') and
             value.get('held_binding_released') is True and value.get('flow_lock_released') is True and
             value.get('final_Main_guard_passed') is True and value.get('Main_before_lock')==c['Main_before'] and
             value.get('source_and_artifact_unchanged') is True and
             value.get('build',{}).get('source_manifest_sha256')==QA_MANIFEST,
             'EXACT_CLOSED_IHG_PHASE_PRESERVE_INSPECT_UNKNOWN')
    need(phase.get('action_attempted') is True and phase.get('action_lock_released') is True and
         phase.get('click_requests_admitted')==2 and phase.get('search_click_acknowledged') is True and
         phase.get('click_acknowledged') is True and phase.get('post_inspection_completed') is True and
         phase.get('explicit_search_then_destination_completed') is True,
         'EXACT_RETIRED_TWO_CLICK_PHASE_REQUIRED')
    task=c['owned_task']
    need(task.get('task')==871 and task.get('prelaunch_task_ids')==[870] and task.get('prelaunch_absent') is True and
         task.get('cleanup_allowed') is True and c.get('owned_task_absent_after_cleanup') is True and
         cleanup.get('owned_task')==task and cleanup.get('owned_task_absent') is True and
         cleanup.get('task_ids_after')==c.get('task_ids_after')==[870] and
         cleanup.get('cleanup',{}).get('new_leaf_removed_and_verified') is True and
         cleanup.get('cleanup',{}).get('other_tasks_preserved') is True,'EXACT_RETIRED_TASK_REQUIRED')
    sequence=phase['post_sequence'];meta=phase['post_assessments']['inspect'];scope=sequence['foreground_after']
    need(sequence.get('error') is None and sequence.get('secondary_errors')==[] and
         sequence.get('owned_task')==task and sequence.get('foreground_before')==scope and
         sequence.get('installed_before')==sequence.get('installed_after')==phase['helper_before']==phase['helper_after'] and
         sequence.get('after_state_completed') is True and sequence.get('restoration_qualified') is True and
         sequence.get('post_state_matches_before') is True and
         sequence['accessibility_restoration']==c['post_restoration'] and
         sequence['accessibility_restoration']['state_before']==sequence['accessibility_restoration']['state_after']==sequence['post_termination_state']['state'] and
         sequence['post_termination_state']['ui_automation_connected'] is False and
         sequence['post_termination_state']['helper_uid']==10153,
         'EXACT_RESTORED_INDEPENDENT_POST_STATE_REQUIRED')
    need(meta==c['post_assessments']['inspect'] and meta['nonce']==INSPECT_NONCE and
         meta['wire_sha256']==sequence['inspection_wire_sha256']==INSPECT_WIRE and
         meta['assessment_bytes']==PINS[STEP/(INSPECT_NONCE+'.assessment.json')][0] and
         meta['assessment_sha256']==PINS[STEP/(INSPECT_NONCE+'.assessment.json')][1] and
         meta.get('complete') is True and meta.get('node_count')==60,'EXACT_PRIVATE_POST_ASSESSMENT_PIN_REQUIRED')
    need(scope['activity']=='com.ihg.apps.android/com.ihg.apps.android.activity.MainActivity',
         'EXACT_RETAINED_MAIN_ACTIVITY_REQUIRED')
    return scope,meta,sequence['accessibility_restoration']['state_before']

def public_role_counts(qa,inspection):
    qa.inspect_record(inspection)
    nodes=inspection['nodes'];by_path={n['path']:n for n in nodes}
    def eligible(n):
        return (isinstance(n,dict) and n.get('visible') is True and n.get('enabled') is True and
            n.get('password') is False and n.get('class_truncated') is False and n.get('resource_id_truncated') is False)
    def normalized(value):return ' '.join(value.split()).casefold()
    result={}
    for role,variants in PUBLIC_ROLES.items():
        matches=[];via_text=via_description=0;self_targets=set();parent_targets=set();classes={}
        for node in nodes:
            if node.get('visible') is not True or node.get('password') is not False:continue
            fields=[]
            for field in ('text','content_desc'):
                value=node.get(field)
                if isinstance(value,str) and node.get(field+'_truncated') is False and normalized(value) in variants:
                    need(node.get(field+'_sha256')==qa.sha(value.encode()),'PUBLIC_LABEL_DIGEST_MISMATCH')
                    fields.append(field)
            if not fields:continue
            matches.append(node);via_text+='text' in fields;via_description+='content_desc' in fields
            kind=node.get('class');kind=kind if kind in PUBLIC_CLASSES else 'other'
            classes[kind]=classes.get(kind,0)+1
            if eligible(node):
                if node.get('clickable') is True:self_targets.add(node['path'])
                if '/' in node['path']:
                    parent=by_path.get(node['path'].rsplit('/',1)[0])
                    if eligible(parent) and parent.get('clickable') is True:parent_targets.add(parent['path'])
        result[role]={'fixed_public_variants':list(variants),'matching_visible_nonpassword_nodes':len(matches),
            'via_complete_public_text_count':via_text,'via_complete_public_description_count':via_description,
            'eligible_matching_nodes':sum(eligible(n) for n in matches),
            'eligible_clickable_self_count':len(self_targets),
            'eligible_direct_clickable_parent_count':len(parent_targets),
            'distinct_self_or_direct_parent_candidates':len(self_targets|parent_targets),
            'editable_matching_nodes':sum(eligible(n) and n.get('editable') is True for n in matches),
            'known_class_counts':classes,'current_or_future_action_authority':False}
    resources={}
    for resource in PUBLIC_RESOURCES:
        rows=[n for n in nodes if n.get('resource_id')==resource]
        resources[resource]={'matching_nodes':len(rows),'eligible_nodes':sum(eligible(n) for n in rows),
            'eligible_clickable_nodes':sum(eligible(n) and n.get('clickable') is True for n in rows),
            'eligible_editable_nodes':sum(eligible(n) and n.get('editable') is True for n in rows)}
    return {'fixed_public_role_queries':result,'fixed_public_resource_queries':resources,
        'fixed_known_class_counts':{kind:sum(n.get('class')==kind for n in nodes) for kind in PUBLIC_CLASSES},
        'other_class_count':sum(n.get('class') not in PUBLIC_CLASSES for n in nodes),
        'unknown_labels_identifiers_paths_or_coordinates_exported':False,
        'query_catalog_not_asserted_observed':True,'action_selection_performed':False}


def public_edit_structure(qa,inspection):
    qa.inspect_record(inspection)
    nodes=inspection['nodes'];by_path={n['path']:n for n in nodes}
    def known_class(n):return n.get('class') if n.get('class') in PUBLIC_CLASSES else 'other'
    def visible(n):return n.get('visible') is True and n.get('password') is False and n.get('package')==qa.PACKAGE
    def eligible(n):
        return (visible(n) and n.get('enabled') is True and n.get('class_truncated') is False and
                n.get('resource_id_truncated') is False)
    def rect(value):
        return isinstance(value,list) and len(value)==4 and all(type(v) is int for v in value) and value[0]<value[2] and value[1]<value[3]
    def contains(outer,inner):
        return rect(outer) and rect(inner) and outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3]
    def under(node,parent):return node['path'].startswith(parent['path']+'/')
    def roles(n):
        result=[]
        if not visible(n):return result
        for role in ('destination','destination_zh','dates','rooms_guests','search_tab','find_hotel','sign_in','join'):
            for field in ('text','content_desc'):
                value=n.get(field)
                if isinstance(value,str) and n.get(field+'_truncated') is False and ' '.join(value.split()).casefold() in PUBLIC_ROLES[role]:
                    need(n.get(field+'_sha256')==qa.sha(value.encode()),'PUBLIC_LABEL_DIGEST_MISMATCH')
                    result.append(role);break
        return result
    labels={role:[n for n in nodes if role in roles(n)] for role in
            ('destination','destination_zh','dates','rooms_guests','search_tab','find_hotel','sign_in','join')}
    editors=[n for n in nodes if n.get('class')=='android.widget.EditText']
    rows=[]
    for editor in editors:
        chain=[];path=editor['path']
        for distance in range(1,7):
            if '/' not in path:break
            path=path.rsplit('/',1)[0]
            parent=by_path.get(path)
            if parent is None:
                chain.append({'distance':distance,'ancestor_present':False});break
            children=[n for n in nodes if '/' in n['path'] and n['path'].rsplit('/',1)[0]==parent['path']]
            chain.append({'distance':distance,'ancestor_present':True,'known_class':known_class(parent),
                'eligible':eligible(parent),'clickable':parent.get('clickable') is True,
                'complete_direct_children':len(children)==parent.get('child_count'),
                'direct_child_count':len(children),'declared_child_count':parent.get('child_count'),
                'contains_editor_bounds':contains(parent.get('bounds'),editor.get('bounds')),
                'inside_window_bounds':contains(inspection['window'].get('bounds'),parent.get('bounds')),
                'public_label_descendant_counts':{role:sum(n is parent or under(n,parent) for n in values) for role,values in labels.items()},
                'editable_descendant_count':sum(eligible(n) and n.get('editable') is True and under(n,parent) for n in nodes)})
        rows.append({'known_class':'android.widget.EditText','belongs_to_target':editor.get('package')==qa.PACKAGE,
            'visible':editor.get('visible') is True,'enabled':editor.get('enabled') is True,
            'password':editor.get('password') is True,'editable':editor.get('editable') is True,
            'supports_set_text':editor.get('supports_set_text') is True,'eligible':eligible(editor),
            'clickable':editor.get('clickable') is True,'bounds_positive':rect(editor.get('bounds')),
            'inside_window_bounds':contains(inspection['window'].get('bounds'),editor.get('bounds')),
            'class_complete':editor.get('class_truncated') is False,'resource_complete':editor.get('resource_id_truncated') is False,
            'resource_utf8_bytes':len(editor['resource_id'].encode()),'resource_sha256':qa.sha(editor['resource_id'].encode()),
            'resource_matches_target_id_namespace':bool(re.fullmatch(re.escape(qa.PACKAGE)+r':id/[A-Za-z0-9_]+',editor['resource_id'])),
            'fixed_public_roles_matching_editor':roles(editor),
            'fixed_resource_literal':editor.get('resource_id') if editor.get('resource_id') in PUBLIC_RESOURCES else None,
            'unknown_resource_literal_exported':False,'finite_ancestor_limit':6,'ancestors':chain})
    return {'fixed_class_EditText_count':len(editors),
        'eligible_nonpassword_editable_set_text_count':sum(eligible(n) and n.get('editable') is True and n.get('supports_set_text') is True for n in editors),
        'eligible_editors_with_request_bounded_target_resource_count':sum(row['eligible'] and row['editable'] and row['supports_set_text'] and
            row['resource_matches_target_id_namespace'] and row['resource_utf8_bytes']<=256 for row in rows),
        'public_label_counts':{role:len(values) for role,values in labels.items()},'editor_structure_rows':rows,
        'node_paths_coordinates_unknown_text_descriptions_and_identifiers_exported':False,
        'retired_nodes_are_not_current_action_authority':True,'input_or_click_requested':False,
        'destination_input_semantics_qualified':False}

def collect():
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    reader=Reader()
    def read_json(path):
        size,digest=PINS[path]
        return json.loads(reader.read(path,digest,size))
    c=read_json(ROOT/'result.json');s=read_json(ROOT/'stage-result.json')
    phase=read_json(STEP/'result.json');cleanup=read_json(FLOW/'steps/cleanup-01/result.json')
    scope,metadata,state_before=validate_retained(c,s,phase,cleanup)
    qa=types.ModuleType('fixed_actual_ihg_r2_pure_contract');qa.__file__=str(QA_SOURCE)
    exec(compile(reader.read(QA_SOURCE,QA_SHA,28714),str(QA_SOURCE),'exec'),qa.__dict__)
    need(qa.PROTOCOL=='pocket4-owned-ihg-qa-v2' and qa.SELF=='org.droidloom.qa.ihg.r2' and
         qa.PACKAGE=='com.ihg.apps.android' and qa.UID==10137,'EXACT_IHG_R2_PURE_CONTRACT_REQUIRED')
    qa.scope(scope)
    assessed=read_json(STEP/(INSPECT_NONCE+'.assessment.json'))
    helper,inspection,window,counters=validated_assessment(qa,assessed,INSPECT_NONCE,INSPECT_WIRE,scope)
    need(helper['accessibility_state_before_connection']==state_before and
         inspection['tree_sha256']==metadata['tree_sha256'] and
         inspection['window_sha256']==metadata['window_sha256'] and counters==metadata['tree_observations'] and
         window==metadata['window_observation'] and
         assessed['recorder_command_result_sha256']==metadata['recorder_command_result_sha256'],
         'EXACT_ORIGINAL_SUMMARY_TREE_STATE_AND_COMMAND_BINDING_REQUIRED')
    role_counts=public_role_counts(qa,inspection)
    need(role_counts==phase['post_public_roles']==c['public_destination_observation']['public_role_counts'],
         'EXACT_PREVIOUS_PUBLIC_COUNTS_REPRODUCED')
    result={'schema':1,'state':'RETAINED_CURRENT_IHG_DESTINATION_PUBLIC_EDIT_STRUCTURE_ONLY','flow_nonce':NONCE,
        'source_manifest_sha256':SOURCE_SHA,'owned_task_retired':871,'old_task_ids_preserved':[870],
        'assessment_nonce':INSPECT_NONCE,'canonical_helper_wire_sha256':INSPECT_WIRE,
        'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
        'node_count':len(inspection['nodes']),'scope':scope,'complete_tree_verified':True,
        'window_ready':window['ready'],'capture_began_elapsed_ms':counters[0]['began_elapsed_ms'],
        'capture_last_elapsed_ms':counters[0]['last_elapsed_ms'],'public_role_counts':role_counts,'public_edit_structure':public_edit_structure(qa,inspection),
        'historical_inspect_action_attempted':True,'historical_inspect_outcome_unknown':True,
        'input_file_pins':reader.records,'all_observations_from_retired_task':True,
        'current_runtime_or_future_action_authority':False,'raw_commercial_tree_or_user_text_or_pixels_exported':False,
        'Android_or_process_actions':0,'runtime_qualification_asserted':False,
        'hotel_search_login_or_booking_verified':False,'whole_app_production_ready':False}
    no_raw_ui(result)
    raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw)<=32768,'ROLE_DIAGNOSTIC_ONLY_OUTPUT_BOUND')
    print(raw.decode(),end='',flush=True)
    return 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect-once',action='store_true')
    a=p.parse_args(argv)
    if not a.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','fixed_files':[str(x) for x in FILES],
            'file_count':len(FILES),'raw_UI_export':False,'Android_or_process_actions':0}));return 0
    return collect()


if __name__=='__main__':raise SystemExit(main())
