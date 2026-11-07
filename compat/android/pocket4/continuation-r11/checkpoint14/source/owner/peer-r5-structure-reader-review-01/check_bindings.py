#!/usr/bin/env python3
"""Local fixed-source and safe-summary binding checks; never reads commercial assessments."""
import ast
import hashlib
import json
from pathlib import Path
import types

BASE=Path('/workspace/scratch/94990735b266')
FROZEN=BASE/'android-bili-r5-player-structure-reader-01'
SAFE=BASE/'root-recovery-20261104-02/evidence/bili-r5-buffer-viewport01-read01'
OUT=Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw=path.read_bytes()
    return {'bytes':len(raw),'sha256':sha(raw)}


def main():
    frozen=json.loads((FROZEN/'SOURCE_PINS.json').read_bytes())
    for row in frozen['files']:
        assert pin(FROZEN/row['path'])=={k:row[k] for k in ['bytes','sha256']}
    source=(FROZEN/'read_structure.py').read_bytes()
    assert len(source)==15988 and sha(source)=='8b3b222fa6075d01124f600e4ddf7cf66e40c96f1c9c66cc9781e86eee26cf5e'
    module=types.ModuleType('peer_fixed_structure_source_only')
    exec(compile(source,'<frozen source definitions only>','exec'),module.__dict__)
    assert len(module.FILES)==15
    request=json.loads((FROZEN/'exact-request.json').read_bytes())
    assert request['stdin'].encode()==source
    expected="import sys,hashlib;raw=sys.stdin.buffer.read(16385);assert len(raw)==15988 and hashlib.sha256(raw).hexdigest()=="+repr(sha(source))+";scope={'__name__':'fixed_retained_structure_reader','__file__':'<verified-retained-structure-reader>'};exec(compile(raw,'read_structure.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once']))"
    assert request['args']==['-n','/usr/bin/python3','-I','-c',expected]
    assert request['executable']=='/usr/bin/sudo' and request['memory_max_bytes']==134217728
    assert request['timeout_seconds']==30 and request['cpu_quota_percent']==100 and request['nice']==10
    ast.parse(expected)
    safe_raw=(SAFE/'reader-report.json').read_bytes()
    assert len(safe_raw)==235562 and sha(safe_raw)=='fc8c3793d272111554db6e188067ec5eb2b2e72c11a50d92530903dac682a5e1'
    safe=json.loads(safe_raw)
    assert len(safe['files'])==8 and safe['missing']==[]
    for name,row in safe['files'].items():
        raw=row['text'].encode()
        assert len(raw)==row['bytes'] and sha(raw)==row['sha256'] and raw==(SAFE/name).read_bytes()
    objects={}
    expected_files={'coordinator.json':(6332,module.COORDINATOR_SHA),'stage.json':(1773,module.STAGE_SHA),
                    'navigation.json':(198786,module.NAV_SHA),'cleanup.json':(446,module.CLEANUP_SHA)}
    for name,(size,digest) in expected_files.items():
        raw=(SAFE/name).read_bytes();assert len(raw)==size and sha(raw)==digest
        objects[name]=json.loads(raw)
    c,s,nav,cleanup=(objects[name] for name in expected_files)
    for value in (c,s,nav):
        assert value['ok'] is False and value['nonce']==module.NONCE
        assert value['source_manifest_sha256']==module.SOURCE_SHA and value['secondary_errors']==[]
    assert c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after']
    assert c['source_and_artifact_unchanged'] is True and s['source_unchanged'] is True
    assert s['coordinator_result']=={'path':str(module.ROOT/'result.json'),'bytes':6332,'sha256':module.COORDINATOR_SHA}
    assert nav['error']==module.FIRST_ERROR and nav['helper_package']=='org.droidloom.qa.bili.r5'
    assert nav['helper_uid']==10170 and nav['uid']==10117
    assert all(nav[k] is True for k in ['final_Main_guard_passed','held_binding_released','action_lock_released',
                                      'video_click_acknowledged','video_click_and_observations_completed'])
    assert cleanup['ok'] is True and cleanup['new_leaf_removed_and_verified'] is True
    assert cleanup['other_tasks_preserved'] is True and cleanup['task_ids_after']==[851]
    assert c['owned_task_absent_after_cleanup'] is True
    source_pins=BASE/'android-bili-r5-buffer-viewport-01/SOURCE_PINS.json'
    assert pin(source_pins)=={'bytes':997,'sha256':module.SOURCE_SHA}
    viewport_path=BASE/'android-bili-r5-buffer-viewport-01/viewport_observation.py'
    qa_path=BASE/'owned-bili-qa-r5-cache-build02-work-01/source/qa_contract.py'
    assert pin(viewport_path)=={'bytes':13830,'sha256':module.VIEWPORT_SHA}
    assert pin(qa_path)=={'bytes':27891,'sha256':module.QA_SHA}
    qa=types.ModuleType('peer_exact_r5_qa')
    viewport=types.ModuleType('peer_exact_viewport')
    exec(compile(qa_path.read_bytes(),str(qa_path),'exec'),qa.__dict__)
    exec(compile(viewport_path.read_bytes(),str(viewport_path),'exec'),viewport.__dict__)
    assert viewport.PLANS[0]['nonces']['inspect']==module.FAILED_VIEWPORT_NONCE
    observations=nav['video_post_observations'];assert len(observations)==3
    for index,(nonce,value) in enumerate(zip(module.POST_NONCES,observations),1):
        assert value['index']==index and value['restoration_qualified'] is True and value['after_state_completed'] is True
        metadata=value['assessments']['inspect']
        assert metadata['nonce']==nonce and metadata['actual_command_returncode']==0
        assert metadata['actual_instrumentation_finish_code']==-1
        qa.scope(value['foreground']);assert value['foreground']['activity']==viewport.DETAILS
    last=nav['buffer_viewport_observation']['last_sequence']
    assert last['inspection_wire_sha256']==module.FAILED_VIEWPORT_WIRE
    assert last['error'] is None and last['after_state_completed'] is True and last['restoration_qualified'] is True
    assert last['foreground_before']==last['foreground_after']
    qa.scope(last['foreground_after']);assert last['foreground_after']['activity']==viewport.DETAILS
    assert nav['buffer_viewport_observation']['reads']==[] and nav['buffer_viewport_observation']['viewport_samples']==[]
    result={'schema':1,'result':'PASS_LOCAL_SOURCE_AND_SAFE8_BINDING_ONLY',
            'reviewed_frozen_files':len(frozen['files']),'fixed_allowlist_files':15,
            'exact_request_stdin_and_wrapper':True,'safe8_originals_rehashed':8,
            'four_original_flow_pins':{name:pin(SAFE/name) for name in expected_files},
            'actual_first_viewport_wire':last['inspection_wire_sha256'],
            'actual_original_failed_first_error':nav['error'],
            'first_viewport_assessment_file_sha_previously_known':False,
            'full_request_canonical_wire_and_inspection_checks_still_required_at_collection':True,
            'pure_loaded_source_pins':{'qa':pin(qa_path),'viewport':pin(viewport_path)},
            'collector_or_original_viewport_executed':False,'commercial_assessments_read':False,
            'Android_Hepta_or_UI_actions':0,'qualification':False}
    raw=(json.dumps(result,indent=2)+'\n').encode()
    with (OUT/'checks-result.json').open('xb') as stream:stream.write(raw)
    print(json.dumps({'path':str(OUT/'checks-result.json'),'bytes':len(raw),'sha256':sha(raw)}))


if __name__=='__main__':
    main()
