#!/usr/bin/env python3
"""PRIVATE UI evidence export for one completed owned r3 inspection.

The source is publishable; collected commercial UI nodes are not. The caller
must keep the decoded result in a private evidence directory outside Git.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import types

ROOT=Path('/home/alex/work/pocket4-bilibili-r3-results-observe-01')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r3-flow-6af0a9c20e8c06d7237d8635c46a166a')
STEP=FLOW/'steps/results-observe-01'
NONCE='9e22d4f5a36dd2f762cf1a2858c9c301'
FLOW_NONCE='6af0a9c20e8c06d7237d8635c46a166a'
COORDINATOR_SHA='2743104fae8764747a7b0444095b5f4185f126cbbc1f9223cfdbcf5f4ac73dad'
COORDINATOR_BYTES=102342
STAGE_SHA='f327e820eb2b9ea98d1c2e5175cabb868cbb1c67cda94b79e8274c2fe8f2accf'
STAGE_BYTES=1647
SOURCE_SHA='9015920277c0f732d8668bc8176d5ab1ec08576013908f922050e17494b5ed6e'
QA_SOURCE=Path('/home/alex/work/pocket4-owned-bili-qa-r3-source-01/source/qa_contract.py')
QA_SHA='6789ec1fef825d9738a6f59a14611dc2d60adc994b093f1ee4cfa9eb75ef9470'
FILES={ROOT/'result.json':0,ROOT/'stage-result.json':0,STEP/'result.json':0,
       STEP/(NONCE+'.assessment.json'):0,STEP/(NONCE+'.request.json'):0,QA_SOURCE:1000}


def need(value,reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Reader:
    def __init__(self):
        self.started=time.monotonic();self.bytes=0

    def read(self,path,expected=None,size=None):
        need(path in FILES,'FIXED_PRIVATE_ALLOWLIST_REQUIRED')
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
        try:
            for name in path.parts[1:-1]:
                nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
                os.close(current);current=nxt
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
            first=os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==FILES[path] and
                 0<first.st_size<=1048576,'FIXED_OWNER_SINGLE_FILE_BOUND')
            chunks=[];count=0
            while True:
                need(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,1048577-count))
                if not part:
                    break
                chunks.append(part);count+=len(part);self.bytes+=len(part)
                need(count<=1048576 and self.bytes<=3145728,'TOTAL_PRIVATE_READ_BOUND')
            last=os.fstat(fd)
            keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            need(count==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),'PRIVATE_INPUT_CHANGED')
            raw=b''.join(chunks)
            need(expected is None or sha(raw)==expected,'EXACT_PRIVATE_INPUT_PIN_CHANGED')
            need(size is None or len(raw)==size,'EXACT_PRIVATE_INPUT_SIZE_CHANGED')
            return raw
        finally:
            if fd is not None:
                os.close(fd)
            os.close(current)


def collect():
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    need(all(isinstance(x,str) and len(x)==64 for x in (COORDINATOR_SHA,STAGE_SHA)) and
         all(type(x) is int and 0<x<=262144 for x in (COORDINATOR_BYTES,STAGE_BYTES)),
         'ACTUAL_COMPLETED_EXTERNAL_PINS_REQUIRED')
    reader=Reader()
    c=json.loads(reader.read(ROOT/'result.json',COORDINATOR_SHA,COORDINATOR_BYTES))
    s=json.loads(reader.read(ROOT/'stage-result.json',STAGE_SHA,STAGE_BYTES))
    for value in (c,s):
        need(value.get('ok') is True and value.get('error') is None and value.get('secondary_errors')==[] and
             value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==FLOW_NONCE and
             value.get('Main_before')==value.get('Main_after'),'EXACT_SUCCESSFUL_COMPLETED_FLOW_REQUIRED')
    need(c.get('owned_task_absent_after_cleanup') is True and c.get('source_and_artifact_unchanged') is True and
         s.get('coordinator_result')=={'path':str(ROOT/'result.json'),'bytes':COORDINATOR_BYTES,'sha256':COORDINATOR_SHA},
         'COMPLETED_ORIGINAL_CLEANUP_AND_STAGE_BINDING_REQUIRED')
    pin=c.get('navigation_result')
    need(isinstance(pin,dict) and pin.get('path')==str(STEP/'result.json'),'FIXED_INSPECT_SUMMARY_REQUIRED')
    phase_raw=reader.read(STEP/'result.json',pin['sha256'],pin['bytes']);phase=json.loads(phase_raw)
    need(phase.get('ok') is True and phase.get('phase')=='navigate' and phase.get('helper_uid')==10166 and
         phase.get('helper_package')=='org.droidloom.qa.bili.r3' and
         phase.get('source_manifest_sha256')==SOURCE_SHA and phase.get('nonce')==FLOW_NONCE and
         phase.get('final_Main_guard_passed') is True and phase.get('held_binding_released') is True and
         phase.get('action_lock_released') is True and phase.get('outcome_unknown') is True and
         phase.get('scoped_click_and_post_observation_completed') is True and
         phase.get('query_submission_controls_completed') is True and
         phase.get('final_results_inspection_completed') is True and
         phase.get('results_container_content_observed') is True and
         phase.get('result_content_observation',{}).get('qualified') is True and
         phase.get('business_outcome_unknown') is True,
         'EXACT_SUCCESSFUL_PRIVATE_INSPECT_PHASE_REQUIRED')
    metadata=phase['observed_results_assessments']['inspect']
    selected=phase['result_content_observation']['selected_additional_sequence']
    need(type(selected) is int and 0<=selected<=8,'BOUNDED_SELECTED_RESULTS_OBSERVATION_REQUIRED')
    matches=[row for row in phase['result_content_observation']['observations']
             if row.get('additional_sequence')==selected]
    need(len(matches)==1 and matches[0]['assessments']['inspect']==metadata and
         matches[0]['postcondition'].get('container_content_observed') is True and
         matches[0]['postcondition'].get('loading_control_count')==0 and
         matches[0]['postcondition'].get('visible_pager_descendants',0)>0,
         'ACTUAL_SELECTED_CONTENT_OBSERVATION_REQUIRED')
    need(metadata.get('nonce')==NONCE and metadata.get('operation')=='inspect' and
         metadata.get('actual_command_returncode')==0 and metadata.get('actual_instrumentation_finish_code')==-1,
         'EXACT_SUCCESSFUL_INSPECT_ASSESSMENT_REQUIRED')
    raw=reader.read(STEP/(NONCE+'.assessment.json'),metadata['assessment_sha256'],metadata['assessment_bytes'])
    assessed=json.loads(raw);helper=assessed['helper']
    contract=reader.read(QA_SOURCE,QA_SHA,24987)
    qa=types.ModuleType('exact_r3_qa_contract');qa.__file__=str(QA_SOURCE)
    exec(compile(contract,str(QA_SOURCE),'exec'),qa.__dict__)
    need(assessed.get('held_transport_returned_after_post_guard') is True and
         assessed.get('actual_instrumentation_finish_code')==-1 and helper.get('ok') is True and
         helper.get('error') is None and helper.get('secondary_errors')==[] and
         helper.get('protocol')==qa.PROTOCOL and helper.get('nonce')==NONCE and helper.get('op')=='inspect' and
         helper.get('self_uid')==10166 and helper.get('action_attempted') is False and
         helper.get('outcome_unknown') is False,'BOUND_READ_ONLY_HELPER_RESULT_REQUIRED')
    need(sha(qa.canonical(helper))==assessed['wire_sha256']==metadata['wire_sha256'],
         'EXACT_CANONICAL_PRIVATE_WIRE_REQUIRED')
    request=json.loads(reader.read(STEP/(NONCE+'.request.json')))
    qa.validate_request(request)
    need(request=={'protocol':qa.PROTOCOL,'nonce':NONCE,'op':'inspect','scope':helper['host_scope_attestation']} and
         sha(qa.canonical(request))==helper['request_sha256'],'EXACT_PRIVATE_INSPECTION_REQUEST_REQUIRED')
    inspection=qa.inspect_record(helper['inspection'])
    window=qa.window_observation(helper['window_observation'])
    counters=qa.tree_observations(helper['tree_observations'],'inspect',True)
    need(counters==metadata['tree_observations'],'PRIVATE_TREE_COUNTERS_NOT_SUMMARY_COUNTERS')
    need(inspection['tree_sha256']==metadata['tree_sha256'] and inspection['window_sha256']==metadata['window_sha256'],
         'PRIVATE_TREE_NOT_SUMMARY_TREE')
    payload={'schema':1,'privacy':'PRIVATE_COMMERCIAL_UI_DO_NOT_PUBLISH_OR_COMMIT',
        'read_only_artifact_export':True,'source_manifest_sha256':SOURCE_SHA,
        'coordinator_sha256':COORDINATOR_SHA,'inspect_summary_sha256':sha(phase_raw),
        'assessment_sha256':sha(raw),'wire_sha256':assessed['wire_sha256'],
        'helper_package':'org.droidloom.qa.bili.r3','helper_uid':10166,'inspection_nonce':NONCE,
        'scope':helper['host_scope_attestation'],'inspection':inspection,'window_observation':window,
        'tree_observations':counters,
        'observed_tree_from_already_retired_task':True,'reuse_for_click_forbidden':True,
        'next_action_requires_fresh_launch_and_fresh_inspection':True,
        'Android_or_process_actions':0,'audio_captured':False,'whole_app_ready':False}
    data=(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(data)<=524288,'PRIVATE_EXPORT_BOUND')
    compressed=gzip.compress(data,mtime=0)
    print(json.dumps({'schema':1,'encoding':'gzip-base64','private_UI_data':True,
        'must_not_enter_Git':True,'uncompressed_bytes':len(data),'uncompressed_sha256':sha(data),
        'compressed_bytes':len(compressed),'compressed_sha256':sha(compressed),
        'data':base64.b64encode(compressed).decode('ascii')},sort_keys=True),flush=True)
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once',action='store_true')
    args=parser.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','fixed_files':[str(p) for p in FILES],
            'private_runtime_output_must_not_enter_Git':True,'remote_actions':0}))
        return 0
    return collect()


if __name__=='__main__':
    raise SystemExit(main())
