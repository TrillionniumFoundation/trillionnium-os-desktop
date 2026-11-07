#!/usr/bin/env python3
"""Read three exact retained R6 assessments; export role counts and fixed errors.

This is historical file analysis only. No Android, process, UI, namespace,
new observation, replay, lock mutation or release operation is available.
No commercial nodes, text, descriptions, unknown labels or pixels are emitted.
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

ROOT=Path('/home/alex/work/pocket4-bilibili-r6-pause-resume-02')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r6-flow-8f28dc51812add5280cb6b7ba411aad0')
STEP=FLOW/'steps/pause-resume-01'
NONCE='8f28dc51812add5280cb6b7ba411aad0'
SOURCE_SHA='0611a55350a19de18b14b1da7fe6342caed8f8e6082746e83b028b345abd8d97'
COORDINATOR_SHA='d04701a323982b972cdfde1dad4ae0e476f4f2a3b47efcdb973c762b0c9d1f00'
STAGE_SHA='9ad3fdbd324dedd87bb4570bf0e09c7c5265f92b44f6133f63e1e29b409ad15b'
NAV_SHA='e7403db0e2a65637281ed00489d2fa70e796881b06cf8d23720cce28fac834d6'
CLEANUP_SHA='1f5bc45e0d60e3b94d9c2c2946bca5d3e969bede051fa5714f8987b1a6077a40'
QA_SOURCE=Path('/home/alex/work/pocket4-owned-bili-qa-r6-source-01/source/qa_contract.py')
QA_SHA='871c784812063739a6ab976784fb38243af52266b0d9a95aa1244779ccd2c005'
QA_MANIFEST='6c75b4a976990d4815de58f504912d3f9a7181c0d5a9094c6319180a1279c419'
FIRST_ERROR={'phase':'controls_reveal_input','type':'ProtocolError','message':'REVEAL_UNIQUE_PLAYER_ROLE_REQUIRED'}
SECONDARY_ERROR={'phase':'independent_controls_readback','type':'ProtocolError','message':'REVEAL_UNIQUE_PLAYER_ROLE_REQUIRED'}
CASES=(
 ('last_video_post','75b18ea61c126b869c8598097cefc528','0937c0e5678012708d8c1c5cf18392045341a821926a2c606702050073e36b64',
  101178,'145489a5313ff2debc8cf46f2cdb0969990d80b497e13eec0ecff2bfab1247d0'),
 ('reveal_admission','6996ba8e828fd43f664e57ded3ac3925','748999e4565f8772b518ea809501fd4907a4cb65cc2614ba19e3f423f602dd8e',None,None),
 ('failed_reveal_finally','5fae7f824e27026ed285fd4634a00408','08690ce9cde9a5a1e54c095c47f22e9239ef249b2f9f4ef9d7cb097073516b92',None,None),
)
FILES={ROOT/'result.json':0,ROOT/'stage-result.json':0,STEP/'result.json':0,
       FLOW/'steps/cleanup-01/result.json':0,QA_SOURCE:1000}
for _,nonce,_,_,_ in CASES:FILES[STEP/(nonce+'.assessment.json')]=0

def need(value, reason):
    if not value:raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

class Reader:
    def __init__(self):
        self.started=time.monotonic();self.bytes=0;self.records=[]

    def read(self,path,expected=None,size=None):
        need(path in FILES,'FIXED_EIGHT_FILE_ALLOWLIST_REQUIRED')
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


def validate_retained(c,s,nav,cleanup):
    for value in (c,s,nav):
        need(value.get('nonce')==NONCE and value.get('source_manifest_sha256')==SOURCE_SHA and
             value.get('ok') is False and value.get('business_success_verified') is False and
             value.get('whole_app_production_ready') is False,'EXACT_ORIGINAL_FAILED_FLOW_REQUIRED')
    need(c.get('secondary_errors')==s.get('secondary_errors')==[] and
         c.get('Main_before')==c.get('Main_after')==s.get('Main_before')==s.get('Main_after') and
         c.get('source_and_artifact_unchanged') is True and s.get('source_unchanged') is True,
         'ORIGINAL_MAIN_AND_SOURCE_CHAIN_REQUIRED')
    need(s.get('coordinator_result')=={'path':str(ROOT/'result.json'),'bytes':7406,'sha256':COORDINATOR_SHA} and
         c.get('retained_phase_results',{}).get('navigate')=={'path':str(STEP/'result.json'),'bytes':214331,'sha256':NAV_SHA} and
         c.get('cleanup_result')=={'path':str(FLOW/'steps/cleanup-01/result.json'),'bytes':448,'sha256':CLEANUP_SHA},
         'EXACT_RETAINED_PARENT_PINS_REQUIRED')
    need({k:nav.get('error',{}).get(k) for k in FIRST_ERROR}==FIRST_ERROR and
         nav.get('secondary_errors')==[SECONDARY_ERROR] and
         nav.get('helper_package')=='org.droidloom.qa.bili.r6' and nav.get('helper_uid')==10184 and
         nav.get('package')=='tv.danmaku.bili' and nav.get('uid')==10117 and
         nav.get('build',{}).get('source_manifest_sha256')==QA_MANIFEST and
         all(nav.get(k) is True for k in ('video_click_and_observations_completed','video_click_acknowledged',
             'final_Main_guard_passed','held_binding_released','action_lock_released')) and
         'playback_button_observation' not in nav,'EXACT_REVEAL_ROLE_FAILURE_BEFORE_PAUSE_REQUIRED')
    need(c.get('owned_task',{}).get('task')==998 and c['owned_task'].get('prelaunch_task_ids')==[851] and
         c.get('owned_task_absent_after_cleanup') is True and cleanup.get('ok') is True and
         cleanup.get('new_leaf_removed_and_verified') is True and cleanup.get('other_tasks_preserved') is True and
         cleanup.get('task_ids_after')==[851] and cleanup.get('outcome_unknown') is False,
         'EXACT_RETIRED_TASK_AND_OLD_TASK_PRESERVATION_REQUIRED')
    record=nav['controls_reveal_observation']
    need(record.get('input_sequence_started') is True and record.get('input_acknowledged') is False and
         record.get('independent_read_attempted') is True and record.get('independent_read_completed') is False and
         record.get('controls_revealed_observed') is False and
         'independent_read_deferred_to_pause_fresh_inspect' not in record,
         'ORIGINAL_FAILED_REVEAL_AND_FINALLY_READ_REQUIRED')
    failed=record['failed_input_sequence'];final=record['independent_sequence']
    need(failed.get('error')=={'phase':'state_inspection_or_action','type':'ProtocolError',
         'message':FIRST_ERROR['message']} and not failed.get('reveal_input_acknowledged',False) and
         final.get('error') is None and record.get('failed_independent_sequence')==final,
         'HOST_PREDICATE_FAILURE_AND_SUCCESSFUL_INDEPENDENT_INSPECT_REQUIRED')
    scopes={}
    for label,seq,wire in (('reveal_admission',failed,CASES[1][2]),('failed_reveal_finally',final,CASES[2][2])):
        need(seq.get('inspection_wire_sha256')==wire and seq.get('secondary_errors')==[] and
             seq.get('after_state_completed') is True and seq.get('restoration_qualified') is True and
             seq.get('post_state_matches_before') is True and
             seq.get('foreground_before')==seq.get('foreground_after') and
             seq.get('installed_before')==seq.get('installed_after')==nav['live_installed_before'] and
             seq.get('owned_task')==c['owned_task'],'EXACT_RESTORED_RETAINED_SEQUENCE_REQUIRED')
        scopes[label]=seq['foreground_after']
    posts=nav['video_post_observations'];need(len(posts)==3,'THREE_ORIGINAL_VIDEO_POSTS_REQUIRED')
    post=posts[2];meta=post['assessments']['inspect']
    need(post.get('index')==3 and post.get('restoration_qualified') is True and post.get('after_state_completed') is True and
         meta.get('nonce')==CASES[0][1] and meta.get('wire_sha256')==CASES[0][2] and
         meta.get('assessment_bytes')==CASES[0][3] and meta.get('assessment_sha256')==CASES[0][4] and
         meta.get('complete') is True,'EXACT_LAST_VIDEO_POST_ASSESSMENT_REQUIRED')
    scopes['last_video_post']=post['foreground']
    need(scopes['last_video_post']==scopes['reveal_admission']==scopes['failed_reveal_finally'],
         'RETAINED_SAME_HOST_SCOPE_REQUIRED')
    return scopes,meta


def role_counts(qa,inspection):
    nodes=inspection['nodes'];result={};chosen={}
    def eligible(n):
        return n.get('visible') is True and n.get('enabled') is True and n.get('password') is False and n.get('class_truncated') is False and n.get('resource_id_truncated') is False
    roles=(('title','title','android.widget.TextView',qa.REVEAL_TITLE),
           ('author','author_name','android.widget.TextView',qa.REVEAL_AUTHOR),
           ('area','video_area','android.widget.FrameLayout',None),
           ('container','video_container','android.widget.FrameLayout',None),
           ('overlay','video_area_float_layer_container','android.widget.FrameLayout',None),
           ('toolbar','collapsing_toolbar','android.widget.FrameLayout',None),
           ('controls','control_container','android.widget.FrameLayout',None))
    for label,resource,kind,text_hash in roles:
        matching_resource=[n for n in nodes if n.get('resource_id')==qa.PACKAGE+':id/'+resource]
        matching=[n for n in matching_resource if n.get('class')==kind]
        accepted=[n for n in matching if eligible(n)]
        exact=[n for n in accepted if text_hash is None or
               (n.get('text_truncated') is False and isinstance(n.get('text'),str) and
                n.get('text_sha256')==text_hash==sha(n['text'].encode()))]
        row={'matching_resource_count':len(matching_resource),'matching_resource_and_class_count':len(matching),
             'eligible_count':len(accepted),'qualified_count':len(exact),'unique_qualified':len(exact)==1,
             'eligibility_rejection_counts':{
                 'not_visible':sum(n.get('visible') is not True for n in matching),
                 'not_enabled':sum(n.get('enabled') is not True for n in matching),
                 'not_non_password':sum(n.get('password') is not False for n in matching),
                 'class_incomplete':sum(n.get('class_truncated') is not False for n in matching),
                 'resource_incomplete':sum(n.get('resource_id_truncated') is not False for n in matching)}}
        if text_hash is not None:
            row['expected_text_digest_match_count']=len(exact)
            row['eligible_incomplete_text_count']=sum(n.get('text_truncated') is not False or not isinstance(n.get('text'),str) for n in accepted)
            row['eligible_nonmatching_complete_text_count']=sum(n.get('text_truncated') is False and isinstance(n.get('text'),str) and n.get('text_sha256')!=text_hash for n in accepted)
        if len(exact)==1:chosen[label]=exact[0]
        result[label]=row
    container=chosen.get('container')
    underneath=[] if container is None else [n for n in nodes if n['path'].startswith(container['path']+'/')]
    return {'role_order':[x[0] for x in roles],'roles':result,
        'first_nonunique_role_in_declared_order':next((x[0] for x in roles if result[x[0]]['qualified_count']!=1),None),
        'known_render_class_counts':{kind:sum(n['class']==kind for n in nodes)
            for kind in ('android.view.SurfaceView','android.view.TextureView')},
        'visible_buffering_prefix_count_under_unique_container':None if container is None else
            sum(n.get('visible') is True and isinstance(n.get('text'),str) and n['text'].startswith('Buffering...') for n in underneath),
        'no_unknown_node_labels_or_text_digests_emitted':True,'action_selection_performed':False}


def validated_assessment(qa,assessed,nonce,wire,scope):
    helper=assessed['helper']
    need(assessed.get('held_transport_returned_after_post_guard') is True and
         assessed.get('actual_command_returncode')==0 and assessed.get('actual_instrumentation_finish_code')==-1 and
         helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors')==[] and
         helper.get('protocol')==qa.PROTOCOL and helper.get('nonce')==nonce and helper.get('op')=='inspect' and
         helper.get('self_uid')==10184 and helper.get('action_attempted') is False and helper.get('outcome_unknown') is False and
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


def predicate_errors(qa,inspection,scope):
    results={}
    for name,hidden in (('require_hidden',True),('allow_shown',False)):
        error=None
        try:qa.player_reveal_scope(inspection,scope,hidden)
        except qa.ProtocolError as caught:
            error=str(caught)
            need(re.fullmatch(r'REVEAL_[A-Z0-9_]{1,100}',error),'ONLY_FIXED_PUBLIC_PREDICATE_ERROR_ALLOWED')
        results[name]=error
    return results


def collect():
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    reader=Reader()
    c=json.loads(reader.read(ROOT/'result.json',COORDINATOR_SHA,7406))
    s=json.loads(reader.read(ROOT/'stage-result.json',STAGE_SHA,1773))
    nav=json.loads(reader.read(STEP/'result.json',NAV_SHA,214331))
    cleanup=json.loads(reader.read(FLOW/'steps/cleanup-01/result.json',CLEANUP_SHA,448))
    scopes,last_metadata=validate_retained(c,s,nav,cleanup)
    qa=types.ModuleType('fixed_actual_r6_pure_contract');qa.__file__=str(QA_SOURCE)
    exec(compile(reader.read(QA_SOURCE,QA_SHA,39280),str(QA_SOURCE),'exec'),qa.__dict__)
    need(qa.PROTOCOL=='pocket4-owned-bili-qa-v6' and qa.SELF=='org.droidloom.qa.bili.r6' and
         qa.PACKAGE=='tv.danmaku.bili' and qa.UID==10117,'EXACT_R6_PURE_CONTRACT_REQUIRED')
    records=[]
    for label,nonce,wire,size,digest in CASES:
        scope=scopes[label];qa.scope(scope)
        need(scope['activity']==qa.REVEAL_ACTIVITY,'EXACT_RETAINED_COURSE_ACTIVITY_REQUIRED')
        raw=reader.read(STEP/(nonce+'.assessment.json'),digest,size)
        assessed=json.loads(raw)
        helper,inspection,window,counters=validated_assessment(qa,assessed,nonce,wire,scope)
        if label=='last_video_post':
            need(inspection['tree_sha256']==last_metadata['tree_sha256'] and
                 inspection['window_sha256']==last_metadata['window_sha256'] and
                 counters==last_metadata['tree_observations'] and
                 assessed['recorder_command_result_sha256']==last_metadata['recorder_command_result_sha256'],
                 'LAST_POST_NOT_ORIGINAL_SUMMARY_TREE')
        errors=predicate_errors(qa,inspection,scope)
        if label=='reveal_admission':need(errors['require_hidden']==FIRST_ERROR['message'],'ORIGINAL_REVEAL_ADMISSION_ERROR_NOT_REPRODUCED')
        if label=='failed_reveal_finally':need(errors['allow_shown']==SECONDARY_ERROR['message'],'ORIGINAL_FINALLY_PREDICATE_ERROR_NOT_REPRODUCED')
        records.append({'label':label,'nonce':nonce,'assessment_bytes':len(raw),'assessment_sha256':sha(raw),
            'external_assessment_file_hash_available':digest is not None,'external_canonical_helper_wire_hash_verified':True,
            'wire_sha256':wire,'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
            'node_count':len(inspection['nodes']),'scope':scope,'original_pure_predicate_errors':errors,
            'role_diagnostic':role_counts(qa,inspection),'window_ready':window['ready'],
            'window_samples':window['samples'],'cache_clears':window['cache_clears'],
            'capture_began_elapsed_ms':counters[0]['began_elapsed_ms'],
            'capture_last_elapsed_ms':counters[0]['last_elapsed_ms'],'complete_tree_verified':True})
    result={'schema':1,'state':'RETAINED_REVEAL_ROLE_DIAGNOSTIC_ONLY','flow_nonce':NONCE,
        'source_manifest_sha256':SOURCE_SHA,'original_failure':FIRST_ERROR,'original_secondary_error':SECONDARY_ERROR,
        'original_failed_attempt_preserved':True,'records':records,'input_file_pins':reader.records,
        'all_observations_from_retired_task':True,'current_runtime_or_future_action_authority':False,
        'UI_window_release_claimed_by_reader':False,'raw_commercial_tree_text_or_pixels_exported':False,
        'Android_or_process_actions':0,'runtime_qualification_asserted':False,
        'cause_inferred_from_node_count':False,'whole_app_production_ready':False}
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
            'file_count':len(FILES),'raw_UI_export':False,'Android_or_process_actions':0}))
        return 0
    return collect()


if __name__=='__main__':raise SystemExit(main())
