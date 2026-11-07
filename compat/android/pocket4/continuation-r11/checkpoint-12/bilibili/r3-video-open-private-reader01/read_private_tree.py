#!/usr/bin/env python3
"""PRIVATE export of one independent successful read after a FAILED flow.

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

ROOT=Path('/home/alex/work/pocket4-bilibili-r3-video-open-01')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r3-flow-7561068625f1b605caacbe007f99ccd1')
STEP=FLOW/'steps/video-open-01'
NONCE='1df84e9e6460ae4f3c5c5ea26e9eb2e1'
FLOW_NONCE='7561068625f1b605caacbe007f99ccd1'
COORDINATOR_SHA='6aba41ba7e5282e759e8af39fe8fb0bc18f9ce41aafd9407408680d98dd7f0be'
COORDINATOR_BYTES=6332
STAGE_SHA='fec96b8c21e2d59db03a842140a1ace571a25d7dfe2ad7dc58d5f9de9ee60fa2'
STAGE_BYTES=1771
SOURCE_SHA='6426ed88fba950f49c4fdc8c4f21d321f5fdc852318e1df3de3c0ee927ac3164'
PHASE_SHA='526be5a089308cb1a0a1918b2b18c27a5b1150fdfd234600a0dc7b67cfd6561c'
PHASE_BYTES=154798
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
        need(value.get('ok') is False and isinstance(value.get('error'),dict) and
             value.get('secondary_errors')==[] and value.get('source_manifest_sha256')==SOURCE_SHA and
             value.get('nonce')==FLOW_NONCE and value.get('Main_before')==value.get('Main_after'),
             'EXACT_ORIGINAL_FAILED_FLOW_REQUIRED')
    need(c.get('owned_task_absent_after_cleanup') is True and c.get('source_and_artifact_unchanged') is True and
         s.get('coordinator_result')=={'path':str(ROOT/'result.json'),'bytes':COORDINATOR_BYTES,'sha256':COORDINATOR_SHA},
         'COMPLETED_ORIGINAL_CLEANUP_AND_STAGE_BINDING_REQUIRED')
    phase_raw=reader.read(STEP/'result.json',PHASE_SHA,PHASE_BYTES);phase=json.loads(phase_raw)
    need(phase.get('ok') is False and phase.get('phase')=='navigate' and phase.get('helper_uid')==10166 and
         phase.get('helper_package')=='org.droidloom.qa.bili.r3' and
         phase.get('source_manifest_sha256')==SOURCE_SHA and phase.get('nonce')==FLOW_NONCE and
         phase.get('final_Main_guard_passed') is True and phase.get('held_binding_released') is True and
         phase.get('action_lock_released') is True and phase.get('secondary_errors')==[] and
         phase.get('error',{}).get('phase')=='video_open' and
         phase.get('error',{}).get('message')=='FOREGROUND_UNVERIFIED',
         'EXACT_FAILED_VIDEO_FOREGROUND_PHASE_REQUIRED')
    failed=phase.get('failed_video_sequence',{})
    need(failed.get('click_acknowledged') is True and failed.get('after_state_completed') is True and
         failed.get('restoration_qualified') is True and failed.get('secondary_errors')==[] and
         failed.get('error')=={'phase':'post_foreground','type':'ControlError','message':'FOREGROUND_UNVERIFIED'},
         'ORIGINAL_ACK_WITH_POST_FOREGROUND_FAILURE_REQUIRED')
    observations=phase.get('video_post_observations')
    need(isinstance(observations,list) and len(observations)==1 and observations[0].get('index')==1 and
         observations[0].get('restoration_qualified') is True and observations[0].get('after_state_completed') is True and
         observations[0]['foreground']['activity']=='tv.danmaku.bili/com.bilibili.ship.theseus.detail.UnitedBizDetailsActivity',
         'ONE_ACTUAL_INDEPENDENT_SUCCESSFUL_PRIVATE_READ_REQUIRED')
    metadata=observations[0]['assessments']['inspect']
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
        'original_flow_failed_and_preserved':True,'post_observation_index':1,
        'original_click_ACK_and_after_state_observed':True,'original_post_foreground_failure':'FOREGROUND_UNVERIFIED',
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
