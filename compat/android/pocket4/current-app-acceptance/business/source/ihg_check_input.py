"""Direct production R3 input validators; synthetic fixtures, no Android/process calls."""
import ast,base64,copy,gzip,hashlib,json,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
EXPECTED_CASES=45
def run_controls():
    rows=[]
    def load(name):
        raw=(HERE/name).read_bytes();module=types.ModuleType('actual_'+name.replace('.','_'))
        module.__file__=str(HERE/name);exec(compile(raw,module.__file__,'exec'),module.__dict__)
        return module,raw
    qa,qa_raw=load('qa_contract.py');adapter,adapter_raw=load('ihg_session.py')
    def yes(name,call):
        value=call()
        if value is False:raise RuntimeError('POSITIVE_FALSE:'+name)
        rows.append({'name':name,'passed':True});return value
    def no(name,call):
        try:call()
        except RuntimeError:rows.append({'name':name,'passed':True});return
        raise RuntimeError('NEGATIVE_ACCEPTED:'+name)
    scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,
        'activity':qa.PACKAGE+'/'+qa.PACKAGE+'.activity.MainActivity','window_token':'1234',
        'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
        'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
        'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}
    resource=qa.PACKAGE+':id/fixture_destination'
    request={'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'set_text','scope':scope,
        'inspection_nonce':'2'*32,'inspection_sha256':'a'*64,'node_path':'0','node_sha256':'b'*64,
        'node_resource_id':resource,'value':'London'}
    yes('actual_final_protocol_identity',lambda:qa.PROTOCOL=='pocket4-owned-ihg-qa-final-main-v1' and
        qa.SELF==adapter.SELF=='org.droidloom.qa.ihg.finalmain.r1' and qa.PUBLIC_SEARCH_QUERY=='London')
    for op in ('state','inspect','click','set_text'):
        value=copy.deepcopy(request)
        if op=='state':value={k:value[k] for k in ('protocol','nonce','op')}
        elif op=='inspect':value={k:value[k] for k in ('protocol','nonce','op','scope')}
        elif op=='click':
            value.pop('node_resource_id');value.pop('value')
        value['op']=op
        yes('actual_request_'+op,lambda v=value:qa.validate_request(v))
    for name,changes in (
        ('old_protocol',{'protocol':'pocket4-owned-ihg-qa-v2'}),
        ('old_public_query',{'value':'usb c cable'}),
        ('different_city',{'value':'Paris'}),
        ('wrong_case',{'value':'london'}),
        ('foreign_resource',{'node_resource_id':'other.app:id/fixture_destination'}),
        ('resource_path_injection',{'node_resource_id':resource+'/child'}),
        ('duplicate_action_nonce',{'inspection_nonce':'1'*32}),
        ('extra_request_key',{'unbound':True}),
    ):
        no(name,lambda c=changes:qa.validate_request({**request,**c}))
    plan={'schema':1,'operation':'set_text','selector':{'resource_id':resource,'class':'android.widget.EditText'},
        'value':'London','nonces':{'before':'3'*32,'inspect':'4'*32,'action':'5'*32,'after':'6'*32}}
    yes('actual_plan_set_text',lambda:adapter.validate_plan(copy.deepcopy(plan),qa))
    def change_plan(changes):
        value=copy.deepcopy(plan);changes(value);return adapter.validate_plan(value,qa)
    no('plan_old_query',lambda:change_plan(lambda v:v.update(value='usb c cable')))
    no('plan_wrong_class',lambda:change_plan(lambda v:v['selector'].update({'class':'android.widget.TextView'})))
    no('plan_foreign_resource',lambda:change_plan(lambda v:v['selector'].update(resource_id='other.app:id/x')))
    no('plan_duplicate_nonce',lambda:change_plan(lambda v:v['nonces'].update(after=v['nonces']['before'])))
    no('plan_extra_field',lambda:change_plan(lambda v:v.update(unbound=True)))
    def node(**changes):
        value={'package':qa.PACKAGE,'path':'0','password':False,'visible':True,'enabled':True,
            'editable':True,'supports_set_text':True,'resource_id':resource,'resource_id_truncated':False,
            'class':'android.widget.EditText','class_truncated':False,'content_redacted':False}
        value.update(changes);value['node_sha256']=qa.sha(qa.canonical(value));return value
    def tree(nodes=None,**changes):
        window={'package':qa.PACKAGE,'display':0,'type':1,'focused':True}
        nodes=[node()] if nodes is None else nodes
        value={'complete':True,'traversal':'visible-non-password-subtrees','window':window,
            'window_sha256':qa.sha(qa.canonical(window)),'observed_elapsed_ms':100,
            'connection_scoped_window_id':42,'nodes':nodes,'tree_sha256':qa.sha(qa.canonical(nodes))}
        value.update(changes);return value
    selector=plan['selector']
    yes('actual_unique_editable_selection',lambda:qa.select_unique_editable(tree(),selector))
    no('duplicate_editable',lambda:qa.select_unique_editable(tree([node(),node(path='0/0')]),selector))
    for name,changes in (
        ('password',{'password':True,'content_redacted':True}),
        ('invisible',{'visible':False,'content_redacted':True}),
        ('disabled',{'enabled':False}),('not_editable',{'editable':False}),
        ('no_set_text_support',{'supports_set_text':False}),
        ('truncated_resource',{'resource_id_truncated':True}),
        ('truncated_class',{'class_truncated':True}),
        ('wrong_actual_class',{'class':'android.widget.TextView'}),
    ):
        no('selection_'+name,lambda c=changes:qa.select_unique_editable(tree([node(**c)]),selector))
    no('partial_tree',lambda:qa.select_unique_editable(tree(complete=False),selector))
    no('window_hash_mismatch',lambda:qa.select_unique_editable(tree(window_sha256='0'*64),selector))
    bad=node();bad['node_sha256']='0'*64
    no('node_hash_mismatch',lambda:qa.select_unique_editable(tree([bad]),selector))
    state={'accessibility_enabled':False,'touch_exploration_enabled':False,
        'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')}
    def base_value(req,uid):
        return {'protocol':qa.PROTOCOL,'nonce':req['nonce'],'op':req['op'],
            'request_sha256':qa.sha(qa.validate_request(req)),'wire_codec':'gzip-canonical-json-v1',
            'self_uid':uid,'self_pid':1234,'ok':True,'error':None,'secondary_errors':[],
            'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,
            'business_success_verified':False,'accessibility_mode_restoration_verified':None,
            'started_elapsed_ms':100,'finished_elapsed_ms':110}
    def wire(value,finish=-1):
        encoded=base64.b64encode(gzip.compress(qa.canonical(value),mtime=0)).decode()
        return ('INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64='+encoded+'\nINSTRUMENTATION_CODE: '+str(finish)+'\n').encode()
    state_req={'protocol':qa.PROTOCOL,'nonce':'7'*32,'op':'state'}
    def state_value(uid):
        return {**base_value(state_req,uid),'action_attempted':False,'outcome_unknown':False,
            'ui_automation_connected':False,'requires_post_termination_state_check':False,
            'restoration':{'service_info_captured':False,'service_info_verified':True},
            'state':state,'window_observation':{},'tree_observations':[]}
    yes('actual_state_wire_positive',lambda:qa.parse_completed(wire(state_value(99999)),b'',0,state_req,99999))
    no('prior_R1_uid_rejected_by_production_denylist',lambda:qa.parse_completed(wire(state_value(10196)),b'',0,state_req,10196))
    no('prior_R2_uid_rejected_by_production_denylist',lambda:qa.parse_completed(wire(state_value(10153)),b'',0,state_req,10153))
    def flow():
        return types.SimpleNamespace(support_sha256=adapter.SUPPORT_MANIFEST_SHA, _private_backend_transport=False,
            baseline_schema=qa.MAIN_BASELINE_SCHEMA,
            scope={'schema':'pocket4-final-business-recorder-scope-v1',
                   'framework_epoch_sha256':qa.MAIN_EPOCH,
                   'business_baseline':{'sha256':qa.MAIN_BASELINE_SHA},
                   'business_qualification':{'sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA},
                   'package':qa.PACKAGE,'uid':qa.UID})
    yes('actual_session_constructor_positive',lambda:adapter.Session(flow(),None,qa,{},99999))
    no('session_prior_R1_uid',lambda:adapter.Session(flow(),None,qa,{},10196))
    no('session_prior_R2_uid',lambda:adapter.Session(flow(),None,qa,{},10153))
    census={'sample':1,'event_serial':0,'elapsed_ms':0,'displays':[0],
        'windows':[{'display':0,'id':42,'type':1,'focused':True,'active':True,'accessibility_focused':False,'layer':0}]}
    window={'requested_display':0,'selection':'exact-display-0-focused-application','wait_budget_ms':2000,
        'ready':True,'first':census,'last':census,'samples':1,'waited_ms':0,'selected_display':0,
        'selected_window_id':42,'recheck_max_ms':100,
        'sample_timings':[{'sample':1,'event_serial':0,'elapsed_ms':0,'cache_cleared':True}],
        'cache_api':'android.app.UiAutomation.clearCache()','cache_policy':'require_public_own_connection_clear_before_each_query',
        'cache_runtime_sdk':34,'cache_attempts':1,'cache_clears':1,'cache_last_result':True,'cache_last_exception':None}
    captures=[{'capture':i,'purpose':purpose,'node_limit':512,'depth_limit':32,'child_limit':64,
        'json_byte_limit':qa.MAX_RESULT-65536,'attempted_nodes':1,'emitted_nodes':1,
        'max_attempted_depth':0,'max_observed_children':0,'serialized_bytes':256,
        'complete':True,'began_elapsed_ms':100+i,'last_elapsed_ms':101+i}
        for i,purpose in enumerate(('action_target','action_final_window'),1)]
    action_value={**base_value(request,99999),'host_scope_attestation':scope,'activity_verified_inside_helper':False,
        'target_uid_verified':qa.UID,'requires_post_termination_state_check':True,
        'restoration':{'service_info_verified':True,'service_info_captured':True,'connection_flags':1,
            'service_flags_before':0,'service_flags_during':80,'service_flags_after':0,
            'service_capabilities_before':0,'service_capabilities_after':0},
        'accessibility_state_before_connection':state,'window_observation':window,'tree_observations':captures,
        'action_attempted':True,'outcome_unknown':True,'node_action':'ACTION_SET_TEXT','node_action_returned':True,
        'inspection_nonce':request['inspection_nonce'],'inspection_sha256':request['inspection_sha256'],
        'target_node_path':request['node_path'],'target_node_sha256':request['node_sha256'],
        'connection_scoped_window_id':42,'target_resource_id':resource,
        'requested_value_sha256':qa.sha(b'London'),'observed_value_sha256':qa.sha(b'London'),'value_readback_verified':True}
    yes('actual_set_text_wire_and_readback',lambda:qa.parse_completed(wire(action_value),b'',0,request,99999))
    no('wrong_value_readback',lambda:qa.parse_completed(wire({**action_value,'observed_value_sha256':qa.sha(b'Paris')}),b'',0,request,99999))
    no('missing_value_readback',lambda:qa.parse_completed(wire({**action_value,'value_readback_verified':False}),b'',0,request,99999))
    no('wrong_actual_resource',lambda:qa.parse_completed(wire({**action_value,'target_resource_id':resource+'2'}),b'',0,request,99999))
    no('failed_finish_not_success',lambda:qa.parse_completed(wire(action_value,0),b'',0,request,99999))
    no('no_action_ACK',lambda:qa.parse_completed(wire({**action_value,'node_action_returned':False}),b'',0,request,99999))
    partial=copy.deepcopy(action_value);partial['tree_observations'][1]['complete']=False
    no('partial_final_action_tree',lambda:qa.parse_completed(wire(partial),b'',0,request,99999))
    qa.require(len(rows)==EXPECTED_CASES,'EXACT_DESTINATION_INPUT_CONTROL_COUNT')
    return {'schema':'pocket4-ihg-r3-public-destination-input-controls-v1','all_passed':True,'count':len(rows),'cases':rows,
        'production_contract_sha256':hashlib.sha256(qa_raw).hexdigest(),
        'production_adapter_sha256':hashlib.sha256(adapter_raw).hexdigest(),
        'fixed_public_value':'London','protocol':qa.PROTOCOL,'target_package':qa.PACKAGE,
        'current_epoch_sha256':qa.MAIN_EPOCH,'actual_installed_helper_uid':None,
        'Android_commands':0,'UI_actions':0,'processes_spawned':0,
        'synthetic_private_labels_only':True,'historical_resource_literal_not_reused':True,
        'Java_action_runtime_executed':False,'business_success_verified':False}
if __name__=='__main__':print(json.dumps(run_controls(),sort_keys=True))
