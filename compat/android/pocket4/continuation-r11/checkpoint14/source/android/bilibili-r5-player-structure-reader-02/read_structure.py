#!/usr/bin/env python3
"""Read four retained inspections; export fixed player-structure diagnostics only.

No Android, UI, namespace, process or replay operation. Full commercial nodes,
text, descriptions and pixels are never emitted. The failed runtime stays failed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import types

ROOT=Path('/home/alex/work/pocket4-bilibili-r5-buffer-viewport-01')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r5-flow-1d7f694a43a8a520665a43e26c5ac1cb')
STEP=FLOW/'steps/buffer-viewport-01'
NONCE='1d7f694a43a8a520665a43e26c5ac1cb'
SOURCE_SHA='2eeff204605c6165f6bda6cd11f99124d6074d25df98c2104cc8af1669a4a99f'
COORDINATOR_SHA='46b0fa7515c906a94924f1726f2c8f52d4c31d4d2fed3d36394fcbd586d31ada'
STAGE_SHA='37f6a5d54c26e4270611e8b937ed715588b2b635544a81dfdf17dfaf0af890c5'
NAV_SHA='36193d4574839df942bc52442c2416b1a2500d51124cb079c251e6b87747786c'
CLEANUP_SHA='e992b602875f4bb2a52d622675045f2ed6503cdfec5a96a9a1d0856bcb120aab'
QA_SOURCE=Path('/home/alex/work/pocket4-owned-bili-qa-r5-source-02/source/qa_contract.py')
QA_SHA='f31f55de33d940d247cacbf3277b11760b7a774e4a3da8b2d5969d0dd0466643'
VIEWPORT_SOURCE=ROOT/'source/viewport_observation.py'
VIEWPORT_SHA='80b3883422c72ba0e7702e5d02bf5b20e0f084bee01fd1e17bd2af16e439b6a7'
POST_NONCES=('91c41cc4b66c2500a5099891f490f3d9','6568a1c106dc6844494a501276feab6f','9b275ee12dfe763a6a2b492820bea86d')
FAILED_VIEWPORT_NONCE='5758a443628adc4433103222d3c2d697'
FAILED_VIEWPORT_WIRE='a5009b9860f253271ca24e1e7e4b7855dc4d27b3eda6b8d986c8ced052565ec9'
FAILED_VIEWPORT_ASSESSMENT_SHA='c4d9455fa069461cdb3efe99c63cd335eca68434ee80ef88ffb22b1d2d36032f'
PRIOR_STRUCTURE_RESULT_SHA='4853c34166b422f074b66394bbeca1da09e3f522ff721a6e288a56a1aee4d0bc'
FIRST_ERROR={'phase':'buffer_viewport_observation','type':'RuntimeError',
             'message':'UNIQUE_CURRENT_PLAYER_STRUCTURE_REQUIRED'}
FILES={ROOT/'result.json':0,ROOT/'stage-result.json':0,STEP/'result.json':0,
       FLOW/'steps/cleanup-01/result.json':0,ROOT/'source/SOURCE_PINS.json':0,
       QA_SOURCE:1000,VIEWPORT_SOURCE:0}
for nonce in (*POST_NONCES,FAILED_VIEWPORT_NONCE):
    FILES[STEP/(nonce+'.assessment.json')]=0
    FILES[STEP/(nonce+'.request.json')]=0


def need(value, reason):
    if not value:raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Reader:
    def __init__(self):
        self.started=time.monotonic();self.bytes=0;self.records=[]

    def read(self,path,expected=None,size=None):
        need(path in FILES,'FIXED_FIFTEEN_FILE_ALLOWLIST_REQUIRED')
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


def surface_geometry(inspection,chosen,surfaces):
    # This reports only already-qualified render-node geometry and hashes.
    # It neither selects a surface nor grants any screenshot/action authority.
    need(len(surfaces)<=8,'FIXED_RENDER_GEOMETRY_REPORT_BOUND')
    nodes={n['path']:n for n in inspection['nodes']}
    crop=chosen['overlay']['bounds'] if 'overlay' in chosen else None
    def inside(a,b):
        return bool(a is not None and b is not None and
                    b[0]<=a[0]<a[2]<=b[2] and b[1]<=a[1]<a[3]<=b[3])
    rows=[]
    for n in sorted(surfaces,key=lambda value:value['path']):
        parent_path=n['path'].rsplit('/',1)[0]
        parent=nodes.get(parent_path)
        row={'path_sha256':sha(n['path'].encode()),'parent_path_sha256':sha(parent_path.encode()),
             'node_sha256':n['node_sha256'],'bounds':n['bounds'],
             'resource_id_sha256':sha(n['resource_id'].encode()),
             'resource_id_truncated':n['resource_id_truncated'],
             'parent_present':parent is not None,'crop_is_inside_surface':inside(crop,n['bounds']),
             'surface_is_inside_crop':inside(n['bounds'],crop),
             'surface_is_inside_window':inside(n['bounds'],inspection['window']['bounds']),
             'relative_to_fixed_roles':{role:{'is_direct_child':parent_path==value['path'],
                 'is_descendant':n['path'].startswith(value['path']+'/'),
                 'same_bounds':n['bounds']==value['bounds']} for role,value in chosen.items()}}
        if parent is not None:
            row['parent']={'node_sha256':parent['node_sha256'],'bounds':parent['bounds'],
                           'class_sha256':sha(parent['class'].encode()),
                           'resource_id_sha256':sha(parent['resource_id'].encode())}
        rows.append(row)
    return {'eligible_surfaces':rows,
            'unique_surface_bounds_count':len({tuple(n['bounds']) for n in surfaces}),
            'all_eligible_surfaces_cover_crop':bool(surfaces) and all(inside(crop,n['bounds']) for n in surfaces),
            'crop_matches_toolbar':bool(crop is not None and 'toolbar' in chosen and
                                         crop==chosen['toolbar']['bounds']),
            'surface_selection_performed':False}


def fixed_roles(inspection):
    # Only these already-published structural resource constants are inspected.
    nodes=inspection['nodes'];roles={};chosen={}
    for role,resource in (
        ('area','tv.danmaku.bili:id/video_area'),
        ('container','tv.danmaku.bili:id/video_container'),
        ('overlay','tv.danmaku.bili:id/video_area_float_layer_container'),
        ('toolbar','tv.danmaku.bili:id/collapsing_toolbar')):
        all_rows=[n for n in nodes if n['resource_id']==resource and n['class']=='android.widget.FrameLayout']
        rows=[n for n in all_rows if n['resource_id_truncated'] is False and n['class_truncated'] is False and
              n['visible'] is True and n['enabled'] is True and n['password'] is False]
        roles[role]={'matching_resource_and_class':len(all_rows),'eligible_count':len(rows)}
        if len(rows)==1:
            chosen[role]=rows[0]
            roles[role].update(bounds=rows[0]['bounds'],path_sha256=sha(rows[0]['path'].encode()))
    surfaces=[n for n in nodes if n['class']=='android.view.SurfaceView']
    eligible=[n for n in surfaces if n['class_truncated'] is False and n['visible'] is True and
              n['enabled'] is True and n['password'] is False]
    def child(node,role):
        return role in chosen and node['path'].startswith(chosen[role]['path']+'/')
    container_surfaces=[n for n in eligible if child(n,'container')]
    terms={'one_eligible_SurfaceView_under_container':len(container_surfaces)==1,
           'container_is_descendant_of_area':child(chosen['container'],'area') if 'container' in chosen else None,
           'overlay_is_descendant_of_area':child(chosen['overlay'],'area') if 'overlay' in chosen else None}
    groups={}
    for n in surfaces:
        key=(n['class_truncated'],n['visible'],n['enabled'],n['password'],child(n,'container'),child(n,'area'))
        groups[key]=groups.get(key,0)+1
    grouped=[dict(zip(('class_truncated','visible','enabled','password','under_container','under_area'),k),count=v)
             for k,v in sorted(groups.items())]
    counts={}
    for kind in ('android.view.SurfaceView','android.view.TextureView'):
        counts[kind]={'total':sum(n['class']==kind for n in nodes),
                      'under_container':sum(n['class']==kind and child(n,'container') for n in nodes),
                      'under_area':sum(n['class']==kind and child(n,'area') for n in nodes)}
    return {'fixed_roles':roles,'original_three_terms':terms,
            'all_original_three_terms_true':all(v is True for v in terms.values()),
            'eligible_surface_count_under_container':len(container_surfaces),
            'surface_predicate_groups':grouped,'two_known_render_class_counts':counts,
            'geometry':surface_geometry(inspection,chosen,container_surfaces),
            'unique_eligible_surface_bounds':container_surfaces[0]['bounds'] if len(container_surfaces)==1 else None,
            'window_bounds':inspection['window']['bounds']}


def no_raw_ui(value):
    if isinstance(value,dict):
        need(not ({'nodes','text','content_desc','inspection','screenshot','pixels','raw_tree','raw_ui_tree'}&set(value)),
             'RAW_UI_EXPORT_FORBIDDEN')
        for item in value.values():no_raw_ui(item)
    elif isinstance(value,list):
        for item in value:no_raw_ui(item)


def collect():
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    reader=Reader()
    c=json.loads(reader.read(ROOT/'result.json',COORDINATOR_SHA,6332))
    s=json.loads(reader.read(ROOT/'stage-result.json',STAGE_SHA,1773))
    nav=json.loads(reader.read(STEP/'result.json',NAV_SHA,198786))
    cleanup=json.loads(reader.read(FLOW/'steps/cleanup-01/result.json',CLEANUP_SHA,446))
    for v in (c,s,nav):
        need(v.get('ok') is False and v.get('nonce')==NONCE and
             v.get('source_manifest_sha256')==SOURCE_SHA and v.get('secondary_errors')==[],
             'EXACT_ORIGINAL_FAILED_FLOW_REQUIRED')
    need(c.get('Main_before')==c.get('Main_after')==s.get('Main_before')==s.get('Main_after') and
         c.get('source_and_artifact_unchanged') is True and s.get('source_unchanged') is True and
         s.get('coordinator_result')=={'path':str(ROOT/'result.json'),'bytes':6332,'sha256':COORDINATOR_SHA},
         'ORIGINAL_MAIN_SOURCE_AND_STAGE_BINDING_REQUIRED')
    need(nav.get('error')==FIRST_ERROR and nav.get('helper_package')=='org.droidloom.qa.bili.r5' and
         nav.get('helper_uid')==10170 and nav.get('uid')==10117 and
         all(nav.get(k) is True for k in ('final_Main_guard_passed','held_binding_released','action_lock_released',
             'video_click_acknowledged','video_click_and_observations_completed')),
         'EXACT_RETAINED_STRUCTURE_FAILURE_REQUIRED')
    need(cleanup.get('ok') is True and cleanup.get('new_leaf_removed_and_verified') is True and
         cleanup.get('other_tasks_preserved') is True and cleanup.get('task_ids_after')==[851] and
         c.get('owned_task_absent_after_cleanup') is True,'ORIGINAL_OWNED_TASK_CLEANUP_REQUIRED')
    source=json.loads(reader.read(ROOT/'source/SOURCE_PINS.json',SOURCE_SHA,997))
    need(source['files']['viewport_observation.py']=={'bytes':13830,'sha256':VIEWPORT_SHA},
         'EXACT_ORIGINAL_VIEWPORT_SOURCE_REQUIRED')
    qa=types.ModuleType('exact_r5_qa_contract');qa.__file__=str(QA_SOURCE)
    exec(compile(reader.read(QA_SOURCE,QA_SHA,27891),str(QA_SOURCE),'exec'),qa.__dict__)
    viewport=types.ModuleType('original_viewport');viewport.__file__=str(VIEWPORT_SOURCE)
    exec(compile(reader.read(VIEWPORT_SOURCE,VIEWPORT_SHA,13830),str(VIEWPORT_SOURCE),'exec'),viewport.__dict__)
    need(viewport.PLANS[0]['nonces']['inspect']==FAILED_VIEWPORT_NONCE,'FIXED_FIRST_VIEWPORT_PLAN_CHANGED')
    original=types.SimpleNamespace(require=need,sha=sha,BILI='tv.danmaku.bili')
    observations=nav['video_post_observations']
    need(len(observations)==3,'THREE_ORIGINAL_POST_READS_REQUIRED')
    last=nav['buffer_viewport_observation']['last_sequence']
    need(last.get('inspection_wire_sha256')==FAILED_VIEWPORT_WIRE and last.get('error') is None and
         last.get('after_state_completed') is True and last.get('restoration_qualified') is True and
         last.get('foreground_before')==last.get('foreground_after') and
         nav['buffer_viewport_observation']['reads']==[] and nav['buffer_viewport_observation']['viewport_samples']==[],
         'EXACT_FIRST_VIEWPORT_READ_AND_NO_CROP_REQUIRED')
    cases=[]
    for index,(nonce,observation) in enumerate(zip(POST_NONCES,observations),1):
        need(observation.get('index')==index and observation.get('restoration_qualified') is True and
             observation.get('after_state_completed') is True,'ORIGINAL_POST_RESTORATION_REQUIRED')
        metadata=observation['assessments']['inspect']
        need(metadata.get('nonce')==nonce and metadata.get('actual_command_returncode')==0 and
             metadata.get('actual_instrumentation_finish_code')==-1,'ORIGINAL_POST_ASSESSMENT_REQUIRED')
        cases.append((f'post_{index}',nonce,observation['foreground'],metadata))
    cases.append(('first_viewport',FAILED_VIEWPORT_NONCE,last['foreground_after'],
                  {'wire_sha256':FAILED_VIEWPORT_WIRE,'assessment_bytes':199428,
                   'assessment_sha256':FAILED_VIEWPORT_ASSESSMENT_SHA}))
    records=[]
    for label,nonce,scope,metadata in cases:
        qa.scope(scope)
        need(scope['activity']==viewport.DETAILS,'ORIGINAL_DETAILS_SCOPE_REQUIRED')
        raw=reader.read(STEP/(nonce+'.assessment.json'),metadata.get('assessment_sha256'),metadata.get('assessment_bytes'))
        assessed=json.loads(raw);helper=assessed['helper']
        need(assessed.get('held_transport_returned_after_post_guard') is True and
             assessed.get('actual_command_returncode')==0 and assessed.get('actual_instrumentation_finish_code')==-1 and
             helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors')==[] and
             helper.get('protocol')==qa.PROTOCOL and helper.get('nonce')==nonce and helper.get('op')=='inspect' and
             helper.get('self_uid')==10170 and helper.get('action_attempted') is False and helper.get('outcome_unknown') is False,
             'READ_ONLY_ACTUAL_HELPER_WIRE_REQUIRED')
        need(sha(qa.canonical(helper))==assessed['wire_sha256']==metadata['wire_sha256'],
             'ACTUAL_CANONICAL_WIRE_PIN_REQUIRED')
        request=json.loads(reader.read(STEP/(nonce+'.request.json')))
        qa.validate_request(request)
        need(request=={'protocol':qa.PROTOCOL,'nonce':nonce,'op':'inspect','scope':scope} and
             sha(qa.canonical(request))==helper['request_sha256'] and helper['host_scope_attestation']==scope,
             'EXACT_RETAINED_REQUEST_SCOPE_REQUIRED')
        inspection=qa.inspect_record(helper['inspection'])
        window=qa.window_observation(helper['window_observation'])
        counters=qa.tree_observations(helper['tree_observations'],'inspect',True)
        if label!='first_viewport':
            need(inspection['tree_sha256']==metadata['tree_sha256'] and
                 inspection['window_sha256']==metadata['window_sha256'] and counters==metadata['tree_observations'],
                 'POST_TREE_NOT_ORIGINAL_SUMMARY_TREE')
        predicate_error=None
        try:viewport.viewport(original,qa,inspection,scope)
        except RuntimeError as error:
            message=str(error)
            need(message in ('UNIQUE_CURRENT_PLAYER_STRUCTURE_REQUIRED','CURRENT_OVERLAY_CROP_MUST_BE_INSIDE_OBSERVED_WINDOW',
                             'PLAYER_TEXT_COMPLETENESS_REQUIRED','AMBIGUOUS_BUFFERING_OBSERVATION') or
                 message.startswith('EXACT_CURRENT_VIEWPORT_NODE_REQUIRED:tv.danmaku.bili:id/'),
                 'UNEXPECTED_PURE_PREDICATE_EXCEPTION')
            predicate_error=message
        diagnostic=fixed_roles(inspection)
        if label=='first_viewport':
            need(predicate_error==FIRST_ERROR['message'] and
                 diagnostic['all_original_three_terms_true'] is False,
                 'ORIGINAL_STRUCTURE_FAILURE_DID_NOT_REPRODUCE')
        records.append({'label':label,'nonce':nonce,'assessment_sha256':sha(raw),'assessment_bytes':len(raw),
            'wire_sha256':assessed['wire_sha256'],'tree_sha256':inspection['tree_sha256'],
            'window_sha256':inspection['window_sha256'],'node_count':len(inspection['nodes']),
            'scope':scope,'pure_original_predicate_error':predicate_error,'structure':diagnostic,
            'window_ready':window['ready'],'cache_attempts':window['cache_attempts'],
            'cache_clears':window['cache_clears'],'cache_last_result':window['cache_last_result'],
            'complete_tree_verified':True})
    result={'schema':1,'state':'COLLECTED_RETAINED_STRUCTURE_DIAGNOSTIC_ONLY',
        'scope':'fixed three post observations and first failed viewport predicate; geometry-only refinement',
        'prior_structure_result_sha256':PRIOR_STRUCTURE_RESULT_SHA,
        'flow_nonce':NONCE,'source_manifest_sha256':SOURCE_SHA,'original_failure':FIRST_ERROR,
        'original_flow_failure_preserved':True,'records':records,'input_file_pins':reader.records,
        'raw_commercial_tree_text_descriptions_or_pixels_exported':False,
        'observed_task_already_retired':True,'reuse_for_click_forbidden':True,
        'Android_or_process_actions':0,'runtime_qualification_asserted':False,
        'cache_cause_established':False,'playback_or_audio_verified':False,'whole_app_ready':False}
    no_raw_ui(result)
    raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw)<=32768,'STRUCTURE_ONLY_OUTPUT_BOUND')
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
