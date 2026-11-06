#!/usr/bin/env python3
"""R7 actual parser/predicates/Session exercised with explicit synthetic data and I/O seams."""
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent.parent
def load(name,path):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__);return module
reference=load('synthetic_public_course_fixture',HERE/'controls/check_reveal.py')
qa,adapter=reference.qa,reference.adapter
def fixture(transition='pause'):
    tree=reference.fixture();tree['nodes'][10]['child_count']=1
    crop=[320,45,1520,720]
    parent=reference.node('','android.view.ViewGroup','0/0/0/2/0',crop);parent['child_count']=1
    button=reference.node(qa.PLAYER_BUTTON_RESOURCE,'android.widget.ImageView','0/0/0/2/0/0',[340,70,400,130])
    label=qa.PLAYER_BUTTON_LABELS[transition]
    button.update(clickable=True,content_desc=label,content_desc_sha256=qa.sha(label.encode()))
    tree['nodes']+=[parent,button];return reference.refresh(tree)
def request(transition='pause'):
    return {'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'player_button','scope':reference.scope(),
        'inspection_nonce':'2'*32,'inspection_sha256':'3'*64,
        **qa.player_button_request_fields(fixture(transition),reference.scope(),transition)}
def window():
    sample={'sample':1,'event_serial':0,'elapsed_ms':1,'displays':[0],
        'windows':[{'display':0,'id':12,'type':1,'focused':True,'active':True,'accessibility_focused':False,'layer':0}]}
    return {'requested_display':0,'selection':'exact-display-0-focused-application','wait_budget_ms':2000,
        'ready':True,'first':copy.deepcopy(sample),'last':sample,'samples':1,'waited_ms':1,
        'selected_display':0,'selected_window_id':12,'recheck_max_ms':100,
        'sample_timings':[{'sample':1,'event_serial':0,'elapsed_ms':1,'cache_cleared':True}],
        'cache_api':'android.app.UiAutomation.clearCache()','cache_policy':'require_public_own_connection_clear_before_each_query',
        'cache_runtime_sdk':37,'cache_attempts':1,'cache_clears':1,'cache_last_result':True,'cache_last_exception':None}
STATE={'accessibility_enabled':False,'touch_exploration_enabled':False,'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'[]')}
RESTORE={'service_info_verified':True,'service_info_captured':True,'connection_flags':1,'service_flags_before':0,
    'service_flags_after':0,'service_flags_during':80,'service_capabilities_before':11,'service_capabilities_after':11}
def value(req):
    tree=fixture(req['transition']);target,proof=qa.player_button_current(tree,req['scope'],req['transition'])
    bindings=[{'tree_sha256':tree['tree_sha256'],'window_sha256':tree['window_sha256'],
        'connection_scoped_window_id':12,'observed_elapsed_ms':time} for time in (100,200,300)]
    observations=[{'capture':i+1,'purpose':purpose,'node_limit':512,'depth_limit':32,'child_limit':64,
        'json_byte_limit':458752,'attempted_nodes':len(tree['nodes']),'emitted_nodes':len(tree['nodes']),
        'max_attempted_depth':6,'max_observed_children':4,'serialized_bytes':len(qa.canonical(tree)),
        'complete':True,'began_elapsed_ms':90+i*100,'last_elapsed_ms':110+i*100}
        for i,purpose in enumerate(('player_selection','action_target','action_final_window'))]
    return {'protocol':qa.PROTOCOL,'nonce':req['nonce'],'op':'player_button','request_sha256':qa.sha(qa.canonical(req)),
        'wire_codec':'gzip-canonical-json-v1','self_uid':19999,'self_pid':1234,'ok':True,'error':None,'secondary_errors':[],
        'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,'business_success_verified':False,
        'accessibility_mode_restoration_verified':None,'started_elapsed_ms':0,'finished_elapsed_ms':500,
        'restoration':RESTORE,'host_scope_attestation':req['scope'],'activity_verified_inside_helper':False,
        'target_uid_verified':qa.UID,'requires_post_termination_state_check':True,'accessibility_state_before_connection':STATE,
        'window_observation':window(),'tree_observations':observations,'action_attempted':True,'outcome_unknown':True,
        'node_action':'ACTION_CLICK','node_action_returned':True,'inspection_nonce':req['inspection_nonce'],
        'inspection_sha256':req['inspection_sha256'],'transition':req['transition'],'player_frame_sha256':req['player_frame_sha256'],
        'prior_inspection_is_context_only':True,'atomic_android_transaction':False,'same_connection_full_tree_rechecks':2,
        'player_inspection':tree,'player_inspection_sha256':qa.sha(qa.canonical(tree)),'player_scope':proof,
        'target_node_path':target['node_path'],'target_node_sha256':target['node_sha256'],'action_window':tree['window'],
        'connection_scoped_window_id':12,'player_capture_bindings':bindings,'player_action_admitted_elapsed_ms':310,
        'player_selection_age_ms':210,'player_selection_age_limit_ms':1000}
def parse(v,req,finish=-1):
    wire=base64.b64encode(gzip.compress(qa.canonical(v),mtime=0))
    stdout=b'INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64='+wire+b'\nINSTRUMENTATION_CODE: '+str(finish).encode()+b'\n'
    return qa.parse_completed(stdout,b'',0,req,19999)

def main():
    rows=[]
    def passed(name,**extra):rows.append({'case':name,'passed':True,**extra})
    def rejects(name,call):
        try:call()
        except (qa.ProtocolError,RuntimeError) as error:passed(name,error=str(error))
        else:raise AssertionError(name+' accepted')
    for transition in ('pause','resume'):
        req=request(transition);qa.validate_request(req);out=parse(value(req),req)
        assert out['helper']['transition']==transition
        passed('full_success_wire_'+transition+'_fixed_role_current_three_captures')
    for name,mutate in [
        ('unknown_transition',lambda x:x.update(transition='toggle')),
        ('caller_node_forbidden',lambda x:x.update(node_path='0/1')),
        ('caller_coordinates_forbidden',lambda x:x.update(x=920,y=382)),
        ('arbitrary_selector_forbidden',lambda x:x.update(selector={'text':'any'})),
        ('same_context_action_nonce',lambda x:x.update(inspection_nonce=x['nonce'])),
        ('wrong_context_activity',lambda x:x['scope'].update(activity=qa.PACKAGE+'/OtherActivity'))]:
        req=copy.deepcopy(request());mutate(req);rejects(name,lambda req=req:qa.validate_request(req))
    for name,mutate in [
        ('wrong_public_label',lambda t:t['nodes'][-1].update(content_desc='播放',content_desc_sha256=qa.sha('播放'.encode()))),
        ('duplicate_control',lambda t:t['nodes'].append(copy.deepcopy(t['nodes'][-1])|{'path':'0/9'})),
        ('missing_control',lambda t:t['nodes'].pop()),
        ('wrong_control_parent',lambda t:t['nodes'][-2].update(resource_id='other')),
        ('wrong_renderer_parent',lambda t:t['nodes'][8].update(path='0/0/0/5')),
        ('wrong_geometry',lambda t:t['nodes'][5].update(bounds=[0,0,10,10])),
        ('missing_metadata',lambda t:t['nodes'][0].update(resource_id='other')),
        ('truncated_button_description',lambda t:t['nodes'][-1].update(content_desc_truncated=True)),
        ('disabled_button',lambda t:t['nodes'][-1].update(enabled=False)),
        ('partial_tree',lambda t:t.update(complete=False))]:
        tree=fixture();mutate(tree);reference.refresh(tree)
        rejects(name,lambda tree=tree:qa.player_button_request_fields(tree,reference.scope(),'pause'))
    for name,mutate in [
        ('target_capture_tree_changed',lambda v:v['player_capture_bindings'][1].update(tree_sha256='0'*64)),
        ('final_capture_tree_changed',lambda v:v['player_capture_bindings'][2].update(tree_sha256='0'*64)),
        ('window_changed',lambda v:v['player_capture_bindings'][2].update(window_sha256='0'*64)),
        ('different_connection_window',lambda v:v['player_capture_bindings'][2].update(connection_scoped_window_id=13)),
        ('reversed_capture_time',lambda v:v['player_capture_bindings'][2].update(observed_elapsed_ms=99)),
        ('missing_final_capture',lambda v:v['tree_observations'].pop()),
        ('stale_current_selection',lambda v:v.update(player_action_admitted_elapsed_ms=1101,player_selection_age_ms=1001,finished_elapsed_ms=1200)),
        ('changed_current_node',lambda v:v.update(target_node_sha256='0'*64)),
        ('old_context_frame_changed',lambda v:v.update(player_frame_sha256='0'*64)),
        ('false_ACK',lambda v:v.update(node_action_returned=False)),
        ('unsupported_atomicity_claim',lambda v:v.update(atomic_android_transaction=True))]:
        req=request();v=value(req);mutate(v);rejects(name,lambda v=v,req=req:parse(v,req))
    req=request();rejects('failure_finish_never_success',lambda:parse(value(req),req,0))
    context=fixture();context['nodes'].append(reference.node('','android.widget.TextView','0/9',[320,950,500,1000],'synthetic changing public counter'))
    reference.refresh(context)
    assert context['tree_sha256']!=fixture()['tree_sha256']
    assert qa.player_button_request_fields(context,reference.scope(),'pause')==qa.player_button_request_fields(fixture(),reference.scope(),'pause')
    passed('prior_context_tree_not_new_action_authority_current_full_tree_rechecks_still_required')
    plan={'schema':1,'operation':'player_button','transition':'pause','nonces':dict(before='4'*32,inspect='5'*32,action='6'*32,after='7'*32)}
    adapter.validate_plan(plan,qa)
    altered=copy.deepcopy(plan);altered['selector']={'text':'pause'}
    rejects('plan_rejects_arbitrary_selector',lambda:adapter.validate_plan(altered,qa))
    flow=types.SimpleNamespace(contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),_private_backend_transport=False)
    rejects('old_R6_UID_not_R7',lambda:adapter.Session(flow,None,qa,{},10184))
    for after_failure in (False,True):
        session=object.__new__(adapter.Session);session.qa=qa
        session.installed=lambda:{'stable':True};session.task=lambda:{'same_owned_task':True};session.foreground=reference.scope
        primary=RuntimeError('OWNED_PLAYER_ACTION_FAILURE');secondary=RuntimeError('OWNED_AFTER_STATE_FAILURE');calls=[]
        def instrument(req):
            calls.append(req['op'])
            if req['op']=='state':
                if req['nonce']==plan['nonces']['after'] and after_failure:raise secondary
                return {'helper':{'state':STATE,'self_uid':19999,'ui_automation_connected':False},'wire_sha256':'a'*64}
            if req['op']=='inspect':return {'helper':{'inspection':fixture()},'wire_sha256':'b'*64}
            if req['op']=='player_button':raise primary
            raise AssertionError('unexpected operation')
        session.instrument=instrument
        try:session.sequence(copy.deepcopy(plan))
        except RuntimeError as error:assert error is primary
        else:raise AssertionError('failure upgraded')
        assert calls==['state','inspect','player_button','state']
        assert session.sequence_observation['restoration_qualified'] is False
        assert session.sequence_observation['after_state_completed'] is (not after_failure)
        assert len(session.sequence_observation['secondary_errors'])==int(after_failure)
        passed('original_finally_after_action_failure_'+('with_secondary' if after_failure else 'restores_state')+'_no_retry')
    print(json.dumps({'schema':1,'passed':len(rows),'controls':rows,'actual_production_parser_predicates_and_Session':True,
        'synthetic_public_data_and_command_IO_seams':True,'Android_Hepta_or_UI_actions':0,
        'source_sha256':{n:hashlib.sha256((HERE/'source'/n).read_bytes()).hexdigest() for n in ('qa_contract.py','qa_adapter.py')}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
