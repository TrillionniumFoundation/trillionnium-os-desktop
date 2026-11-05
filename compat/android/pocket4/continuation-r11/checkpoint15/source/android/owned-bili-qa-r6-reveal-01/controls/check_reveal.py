#!/usr/bin/env python3
"""Actual new Python predicates/Session with synthetic complete trees and explicit command seams."""
import copy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent.parent

def load(name,path):
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),value.__dict__);return value

qa=load('reveal_contract',HERE/'source/qa_contract.py')
adapter=load('reveal_adapter',HERE/'source/qa_adapter.py')

def scope():
    return {'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.REVEAL_ACTIVITY,
            'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH}

def node(resource,kind,path,bounds,text=''):
    return {'package':qa.PACKAGE,'resource_id':resource,'resource_id_truncated':False,
            'class':kind,'class_truncated':False,'path':path,'bounds':list(bounds),
            'visible':True,'enabled':True,'password':False,'clickable':False,
            'editable':False,'supports_set_text':False,'child_count':0,
            'text':text,'text_sha256':qa.sha(text.encode()),'text_truncated':False,
            'content_desc':'','content_desc_sha256':qa.sha(b''),'content_desc_truncated':False}

def refresh(value):
    for n in value['nodes']:
        n.pop('node_sha256',None);n['node_sha256']=qa.sha(qa.canonical(n))
    value['tree_sha256']=qa.sha(qa.canonical(value['nodes']))
    value['window_sha256']=qa.sha(qa.canonical(value['window']))
    return value

def fixture():
    full=[320,45,1520,1498];crop=[320,45,1520,720]
    rows=[node(qa.PACKAGE+':id/title','android.widget.TextView','0/1',[320,760,1000,820],
               'Very Basic Calculus 000: Course Introduction'),
          node(qa.PACKAGE+':id/author_name','android.widget.TextView','0/2',[320,830,1000,900],
               'Ayumu爱讲数学'),
          node(qa.PACKAGE+':id/video_area','android.widget.FrameLayout','0/0',full),
          node(qa.PACKAGE+':id/video_container','android.widget.FrameLayout','0/0/0',full),
          node(qa.PACKAGE+':id/video_area_float_layer_container','android.widget.FrameLayout','0/0/1',crop),
          node(qa.PACKAGE+':id/collapsing_toolbar','android.widget.FrameLayout','0/0/2',crop),
          node('','android.widget.FrameLayout','0/0/0/0',full),
          node('','android.view.SurfaceView','0/0/0/0/0',full),
          node('','android.widget.FrameLayout','0/0/0/1',crop),
          node('','android.view.SurfaceView','0/0/0/1/0',crop),
          node(qa.PACKAGE+':id/control_container','android.widget.FrameLayout','0/0/0/2',crop)]
    return refresh({'complete':True,'traversal':'visible-non-password-subtrees','nodes':rows,
        'window':{'bounds':[320,0,1520,1520],'focused':True,'package':qa.PACKAGE,'display':0,'type':1},
        'connection_scoped_window_id':12,'observed_elapsed_ms':100})

def request():
    return {'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'reveal_controls','scope':scope(),
            'inspection_nonce':'2'*32,'inspection_sha256':'3'*64,**qa.reveal_request_fields(fixture(),scope())}

def touch():
    return {'display':0,'point':[920,382],'pointer_count':1,'source':4098,'runtime_sdk':37,
        'explicit_public_display_factory':True,'down_attempted':True,'down_acknowledged':True,
        'up_attempted':True,'up_acknowledged':True,'cancel_creation_attempted':False,'cancel_attempted':False,
        'cancel_acknowledged':False,'down_created':True,'up_created':True,'cancel_created':False,
        'down_recycled':True,'up_recycled':True,'cancel_recycled':False,'all_created_events_recycled':True,
        'input_stream_terminated':True,'down_time_ms':1000,'up_admission_elapsed_ms':5,'finished_time_ms':1006,
        'up_admission_budget_ms':150,'primary_error':None,'secondary_errors':[],
        'atomic_input_target_attribution':False,'controls_revealed':None,'business_success_verified':False}

def main():
    rows=[]
    def passed(name,**extra):rows.append({'case':name,'passed':True,**extra})
    def rejects(name,call,code):
        try:call()
        except (qa.ProtocolError,RuntimeError) as error:assert str(error)==code,(name,str(error),code)
        else:raise AssertionError(name+' accepted')
        passed(name,expected_error=code)
    original=fixture();proof=qa.player_reveal_scope(original,scope());req=request()
    qa.validate_request(req)
    assert req['viewport_bounds']==[320,45,1520,720] and qa.sha(qa.canonical(proof))==req['player_scope_sha256']
    passed('complete_current_player_produces_bound_request_no_node_fallback')
    for name,mutate,code in [
      ('partial_tree',lambda t:t.update(complete=False),'COMPLETE_INSPECTION_REQUIRED'),
      ('unfocused_window',lambda t:t['window'].update(focused=False),'FOCUSED_BILI_WINDOW_REQUIRED'),
      ('other_display',lambda t:t['window'].update(display=1),'FOCUSED_BILI_WINDOW_REQUIRED'),
      ('extra_surface',lambda t:t['nodes'].append(node('','android.view.SurfaceView','0/0/0/3',[320,45,1520,720])), 'REVEAL_EXACT_TWO_SURFACE_ROLES'),
      ('wrong_course',lambda t:t['nodes'][0].update(text='Other course',text_sha256=qa.sha(b'Other course')),'REVEAL_UNIQUE_PLAYER_ROLE_REQUIRED'),
      ('interactive_player',lambda t:t['nodes'][10].update(clickable=True),'REVEAL_ALREADY_INTERACTIVE_PLAYER_REJECTED'),
      ('nonempty_control_container',lambda t:t['nodes'][10].update(child_count=1),'REVEAL_CURRENT_HIDDEN_CONTROL_CONTAINER'),
      ('buffering_player',lambda t:t['nodes'][10].update(text='Buffering...',text_sha256=qa.sha(b'Buffering...')),'REVEAL_BUFFERING_PLAYER_REJECTED'),
      ('surface_parent_moved',lambda t:t['nodes'][8].update(path='0/0/0/5'),'REVEAL_EXACT_DISTINCT_SURFACE_PARENTS')]:
        value=fixture();mutate(value);refresh(value)
        rejects(name,lambda v=value:qa.reveal_request_fields(v,scope()),code)
    arbitrary=request();arbitrary['x']=920
    rejects('caller_coordinates_not_authorized',lambda:qa.validate_request(arbitrary),'EXACT_OPERATION_KEYS_REQUIRED')
    stale=request();stale['inspection_nonce']=stale['nonce']
    rejects('inspection_nonce_cannot_be_action_nonce',lambda:qa.validate_request(stale),'DISTINCT_REVEAL_NONCE_REQUIRED')
    changed=fixture()
    for n in changed['nodes']:n['bounds'][0]-=320;n['bounds'][2]-=320
    changed['window']['bounds'][0]-=320;changed['window']['bounds'][2]-=320;refresh(changed)
    assert not qa.same_reveal_frame(proof,qa.player_reveal_scope(changed,scope()))
    passed('absolute_translation_is_not_same_frame')
    after=fixture();after['nodes'][10]['child_count']=1
    after['nodes'].append(node(qa.PACKAGE+':id/owned_synthetic_control','android.widget.Button','0/0/0/2/0',[900,360,940,400]))
    after['nodes'][-1]['clickable']=True;refresh(after)
    assert qa.same_reveal_frame(proof,qa.player_reveal_scope(after,scope(),False))
    assert after['tree_sha256']!=original['tree_sha256']
    passed('new_control_nodes_need_readback_but_absolute_player_stays_same')
    qa.touch_observation(touch(),True);passed('acknowledged_down_up_without_business_claim')
    for name,mutate in [
      ('unacknowledged_up',lambda t:t.update(up_acknowledged=False)),
      ('cancel_is_cleanup_not_success',lambda t:t.update(up_acknowledged=False,cancel_attempted=True,cancel_acknowledged=True)),
      ('recycle_failure',lambda t:t.update(down_recycled=False,all_created_events_recycled=False)),
      ('secondary_input_failure',lambda t:t.update(secondary_errors=['up_recycle:OWNED']))]:
        t=touch();mutate(t)
        rejects(name,lambda v=t:qa.touch_observation(v,True),'ACTUAL_COMPLETE_DOWN_UP_AND_EVENT_CLEANUP_REQUIRED')
    t=touch();t['controls_revealed']=True
    rejects('input_ack_not_controls_or_business_qualification',lambda:qa.touch_observation(t,True),'EXACT_PUBLIC_SINGLE_POINTER_INPUT_CONTRACT')

    # Actual Session finally with command seams: first error retained; no retry.
    s=object.__new__(adapter.Session);s.qa=qa
    s.installed=lambda:{'stable':True};s.task=lambda:{'stable_task':True};s.foreground=scope
    failure=RuntimeError('OWNED_REVEAL_FAILURE');calls=[]
    state={'accessibility_enabled':False,'touch_exploration_enabled':False,'enabled_service_count':0,
           'enabled_services_sha256':qa.sha(b'')}
    def instrument(req):
        calls.append(req['op'])
        if req['op']=='state':return {'helper':{'state':state,'self_uid':19999,'ui_automation_connected':False},'wire_sha256':'a'*64}
        if req['op']=='inspect':return {'helper':{'inspection':fixture()},'wire_sha256':'b'*64}
        if req['op']=='reveal_controls':raise failure
        raise AssertionError('unexpected operation')
    s.instrument=instrument
    plan={'schema':1,'operation':'reveal_controls','nonces':dict(before='4'*32,inspect='5'*32,action='6'*32,after='7'*32)}
    adapter.validate_plan(plan,qa)
    try:s.sequence(plan)
    except RuntimeError as error:assert error is failure
    else:raise AssertionError('failed input became success')
    assert calls==['state','inspect','reveal_controls','state']
    assert s.sequence_observation['after_state_completed'] and s.sequence_observation['post_state_matches_before']
    assert s.sequence_observation['restoration_qualified'] is False
    passed('actual_sequence_failed_reveal_still_independent_after_state_no_replay')
    report={'schema':1,'passed':len(rows),'controls':rows,'synthetic_public_course_tree':True,
            'actual_inspect_record_and_new_predicates':True,'Session_input_IO_explicit_seam':True,
            'Android_UI_or_namespace_calls':0,'production_source_sha256':{
                n:hashlib.sha256((HERE/'source'/n).read_bytes()).hexdigest() for n in ('qa_contract.py','qa_adapter.py')}}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
