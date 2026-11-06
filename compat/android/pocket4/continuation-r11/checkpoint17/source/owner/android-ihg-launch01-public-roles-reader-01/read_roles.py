#!/usr/bin/env python3
"""Fixed historical IHG public hotel-entry role counts; no UI or process action.

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

ROOT=Path('/home/alex/work/pocket4-ihg-owned-launch-inspect-01')
FLOW=Path('/home/alex/work/pocket4-ihg-owned-qa-r1-flow-399444a5b72d53139b880a4afefdb31a')
STEP=FLOW/'steps/inspect-01'
NONCE='399444a5b72d53139b880a4afefdb31a'
SOURCE_SHA='704bf0640c6a207ad8177dfc0240896cc785b6fa6db34521fbea5cd02e42a6fd'
QA_SOURCE=Path('/home/alex/work/pocket4-owned-ihg-qa-r1-source-01/source/qa_contract.py')
QA_SHA='573fdcd691ed51b76f965151b74b38cfcbd12ed5aa972d668146ae136744d7e1'
QA_MANIFEST='ab971f5b361f1d97b8036c954a6b88734b7faedbeed6349b873ead85fa79d5f3'
INSPECT_NONCE='212fb7088216fc6760d30b7224f245ee'
INSPECT_WIRE='902c325a2ceaecafced4abc93a4654ad22699dddce216a3af3f8d7c6d938fa3a'
PINS={
 ROOT/'result.json':(13631,'6a354bc4cfe0066263b8f6041be90d674fce05700cd57b21dcf5880122312211'),
 ROOT/'stage-result.json':(1710,'bb34503b97e7702a8b10c6da10cb4bb6e3a95043168ff59859a15cbdf56d7bf1'),
 STEP/'result.json':(19064,'6ded83f7b28e3b9658efe9c1d166513734b58d21a05267d5612b6ddce6d4f836'),
 FLOW/'steps/cleanup-01/result.json':(10012,'eea9b4b856e6a799255626f02213c643ceefced73a86ae503c82119faba9591f'),
 QA_SOURCE:(28150,QA_SHA),
 STEP/(INSPECT_NONCE+'.assessment.json'):(86558,'2e0a9c2af7c403b330e92566a058dd8a0e790654b8c2f89e1a89330e035123de'),
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
            if fd is not None:os.close(fd)
            os.close(current)

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
         helper.get('self_uid')==10196 and helper.get('action_attempted') is False and helper.get('outcome_unknown') is False and
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
             'EXACT_COMPLETED_IHG_FLOW_REQUIRED')
        need(value.get('Main_before')==value.get('Main_after')==c['Main_before'],
             'EXACT_ORIGINAL_MAIN_CHAIN_REQUIRED')
    need(c.get('flow')==str(FLOW) and c.get('helper_uid')==10196 and
         c.get('helper_package')=='org.droidloom.qa.ihg.r1' and c.get('uid')==10137 and
         c.get('read_only_inspection_completed') is True and c.get('source_and_artifact_unchanged') is True and
         s.get('source_unchanged') is True,'EXACT_IHG_HELPER_AND_SOURCE_REQUIRED')
    need(s.get('coordinator_result')==fixed_pin(ROOT/'result.json') and
         c.get('inspection_result')==c.get('retained_phase_results',{}).get('inspect')==fixed_pin(STEP/'result.json') and
         c.get('cleanup_result')==c.get('retained_phase_results',{}).get('cleanup')==fixed_pin(FLOW/'steps/cleanup-01/result.json'),
         'EXACT_PARENT_CHILD_RESULT_PINS_REQUIRED')
    for value,kind in ((phase,'inspect'),(cleanup,'cleanup')):
        need(value.get('phase')==kind and value.get('helper_package')=='org.droidloom.qa.ihg.r1' and
             value.get('helper_uid')==10196 and value.get('uid')==10137 and value.get('outcome_unknown') is False and
             value.get('held_binding_released') is True and value.get('flow_lock_released') is True and
             value.get('final_Main_guard_passed') is True and value.get('Main_before_lock')==c['Main_before'] and
             value.get('source_and_artifact_unchanged') is True and
             value.get('build',{}).get('source_manifest_sha256')==QA_MANIFEST,'EXACT_CLOSED_IHG_PHASE_REQUIRED')
    need(phase.get('action_attempted') is False and phase.get('action_lock_released') is True and
         phase.get('inspection_completed') is True,'EXACT_ORIGINAL_NO_ACTION_PHASE_REQUIRED')
    task=c['owned_task']
    need(task.get('task')==1002 and task.get('prelaunch_task_ids')==[851] and task.get('prelaunch_absent') is True and
         task.get('cleanup_allowed') is True and c.get('owned_task_absent_after_cleanup') is True and
         cleanup.get('owned_task')==task and cleanup.get('owned_task_absent') is True and
         cleanup.get('task_ids_after')==c.get('task_ids_after')==[851] and
         cleanup.get('cleanup',{}).get('new_leaf_removed_and_verified') is True and
         cleanup.get('cleanup',{}).get('other_tasks_preserved') is True,'EXACT_RETIRED_TASK_REQUIRED')
    sequence=phase['sequence'];meta=phase['assessments']['inspect'];scope=sequence['foreground_after']
    need(sequence.get('error') is None and sequence.get('secondary_errors')==[] and
         sequence.get('owned_task')==task and sequence.get('foreground_before')==scope==c.get('foreground') and
         sequence.get('installed_before')==sequence.get('installed_after')==phase['helper_before']==phase['helper_after'] and
         sequence.get('after_state_completed') is True and sequence.get('restoration_qualified') is True and
         sequence.get('post_state_matches_before') is True and
         sequence['accessibility_restoration']==c['restoration'] and
         sequence['accessibility_restoration']['state_before']==sequence['accessibility_restoration']['state_after']==sequence['post_termination_state']['state'] and
         sequence['post_termination_state']['ui_automation_connected'] is False,
         'EXACT_RESTORED_INDEPENDENT_NO_AUTOMATION_STATE_REQUIRED')
    need(meta==c['assessments']['inspect'] and meta['nonce']==INSPECT_NONCE and
         meta['wire_sha256']==sequence['inspection_wire_sha256']==INSPECT_WIRE and
         meta['assessment_bytes']==PINS[STEP/(INSPECT_NONCE+'.assessment.json')][0] and
         meta['assessment_sha256']==PINS[STEP/(INSPECT_NONCE+'.assessment.json')][1] and
         meta.get('complete') is True and meta.get('node_count')==63,'EXACT_PRIVATE_ASSESSMENT_PIN_REQUIRED')
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


def collect():
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    reader=Reader()
    def read_json(path):
        size,digest=PINS[path]
        return json.loads(reader.read(path,digest,size))
    c=read_json(ROOT/'result.json');s=read_json(ROOT/'stage-result.json')
    phase=read_json(STEP/'result.json');cleanup=read_json(FLOW/'steps/cleanup-01/result.json')
    scope,metadata,state_before=validate_retained(c,s,phase,cleanup)
    qa=types.ModuleType('fixed_actual_ihg_r1_pure_contract');qa.__file__=str(QA_SOURCE)
    exec(compile(reader.read(QA_SOURCE,QA_SHA,28150),str(QA_SOURCE),'exec'),qa.__dict__)
    need(qa.PROTOCOL=='pocket4-owned-ihg-qa-v1' and qa.SELF=='org.droidloom.qa.ihg.r1' and
         qa.PACKAGE=='com.ihg.apps.android' and qa.UID==10137,'EXACT_IHG_R1_PURE_CONTRACT_REQUIRED')
    qa.scope(scope)
    assessed=read_json(STEP/(INSPECT_NONCE+'.assessment.json'))
    helper,inspection,window,counters=validated_assessment(qa,assessed,INSPECT_NONCE,INSPECT_WIRE,scope)
    need(helper['accessibility_state_before_connection']==state_before and
         inspection['tree_sha256']==metadata['tree_sha256'] and
         inspection['window_sha256']==metadata['window_sha256'] and counters==metadata['tree_observations'] and
         window==metadata['window_observation'] and
         assessed['recorder_command_result_sha256']==metadata['recorder_command_result_sha256'],
         'EXACT_ORIGINAL_SUMMARY_TREE_STATE_AND_COMMAND_BINDING_REQUIRED')
    result={'schema':1,'state':'RETAINED_IHG_PUBLIC_ROLE_COUNTS_ONLY','flow_nonce':NONCE,
        'source_manifest_sha256':SOURCE_SHA,'owned_task_retired':1002,'old_task_ids_preserved':[851],
        'assessment_nonce':INSPECT_NONCE,'canonical_helper_wire_sha256':INSPECT_WIRE,
        'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
        'node_count':len(inspection['nodes']),'scope':scope,'complete_tree_verified':True,
        'window_ready':window['ready'],'capture_began_elapsed_ms':counters[0]['began_elapsed_ms'],
        'capture_last_elapsed_ms':counters[0]['last_elapsed_ms'],'public_role_counts':public_role_counts(qa,inspection),
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
