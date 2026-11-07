"""Pure checks of the production Amazon R2 wire parser. Called by the pinned build process."""
import base64
import copy
import gzip
import hashlib
import types


def run(contract_source):
    qa=types.ModuleType('owned_amazon_r2_idle_contract_controls')
    exec(compile(contract_source,'qa_contract.py','exec'),qa.__dict__)
    rows=[]

    def need(value,reason):
        if not value:raise AssertionError(reason)

    def check(name,body):
        body();rows.append({'name':name,'passed':True})

    def idle():
        return {'schema':1,'operation':'inspect','invoked':True,'call_count':1,
                'operation_started_elapsed_ms':1000,'began_elapsed_ms':1100,'last_elapsed_ms':1600,
                'waited_ms':500,'quiet_timeout_ms':500,'global_timeout_cap_ms':2000,
                'global_timeout_ms':2000,'operation_deadline_ms':8000,'api_returned':True,'qualified':True,
                'exception_class':'','secondary_clock_exception_class':'','gate_error':'',
                'event_quiet_only':True,'content_ready_proven':False,'future_stability_proven':False}

    request={'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'inspect',
             'scope':{'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,
                      'activity':qa.PACKAGE+'/com.amazon.mShop.home.HomeActivity',
                      'window_token':'abc','main_epoch_sha256':qa.MAIN_EPOCH, 'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
                      'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
                      'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}}
    state={'accessibility_enabled':False,'touch_exploration_enabled':False,
           'enabled_service_count':0,'enabled_services_sha256':'0'*64}
    window={'package':qa.PACKAGE,'display':0,'type':1,'focused':True}
    node={'package':qa.PACKAGE,'path':'0','password':False,'visible':True,'editable':False,'supports_set_text':False}
    node['node_sha256']=qa.sha(qa.canonical(node))
    inspection={'complete':True,'traversal':'visible-non-password-subtrees','window':window,
                'window_sha256':qa.sha(qa.canonical(window)),'observed_elapsed_ms':1700,
                'connection_scoped_window_id':1,'nodes':[node],'tree_sha256':qa.sha(qa.canonical([node]))}
    timing={'sample':1,'event_serial':0,'elapsed_ms':0,'cache_cleared':True}
    census={'sample':1,'event_serial':0,'elapsed_ms':0,'displays':[0],
            'windows':[{'display':0,'id':1,'type':1,'focused':True,'active':True,
                        'accessibility_focused':False,'layer':0}]}
    observed_window={'requested_display':0,'selection':'exact-display-0-focused-application',
                     'wait_budget_ms':2000,'recheck_max_ms':100,'ready':True,'first':census,'last':census,
                     'samples':1,'waited_ms':0,'selected_display':0,'selected_window_id':1,
                     'sample_timings':[timing],'cache_api':'android.app.UiAutomation.clearCache()',
                     'cache_policy':'require_public_own_connection_clear_before_each_query','cache_runtime_sdk':34,
                     'cache_attempts':1,'cache_clears':1,'cache_last_result':True,'cache_last_exception':None}
    counter={'capture':1,'purpose':'inspection','node_limit':512,'depth_limit':32,'child_limit':64,
             'json_byte_limit':qa.MAX_RESULT-65536,'attempted_nodes':1,'emitted_nodes':1,
             'max_attempted_depth':0,'max_observed_children':0,'serialized_bytes':len(qa.canonical(inspection)),
             'complete':True,'began_elapsed_ms':1600,'last_elapsed_ms':1700}
    baseline={'protocol':qa.PROTOCOL,'nonce':request['nonce'],'op':'inspect',
              'request_sha256':qa.sha(qa.canonical(request)),'wire_codec':'gzip-canonical-json-v1',
              'self_uid':30000,'self_pid':99999,'ok':True,'error':None,'secondary_errors':[],
              'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,
              'business_success_verified':False,'accessibility_mode_restoration_verified':None,
              'started_elapsed_ms':1000,'finished_elapsed_ms':1800,'action_attempted':False,'outcome_unknown':False,
              'restoration':{'service_info_verified':True,'service_info_captured':True,'connection_flags':1,
                             'service_flags_before':0,'service_flags_during':80,'service_flags_after':0,
                             'service_capabilities_before':0,'service_capabilities_after':0},
              'host_scope_attestation':request['scope'],'activity_verified_inside_helper':False,'target_uid_verified':qa.UID,
              'requires_post_termination_state_check':True,'accessibility_state_before_connection':state,
              'window_observation':observed_window,'tree_observations':[counter],'inspection':inspection,
              'inspection_idle_observation':idle()}

    def wire(value,finish=-1):
        data=base64.b64encode(gzip.compress(qa.canonical(value),mtime=0))
        return b'INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64='+data+b'\nINSTRUMENTATION_CODE: '+str(finish).encode()+b'\n'

    def parse(value,req=request,uid=30000):
        return qa.parse_completed(wire(value),b'',0,req,uid)

    def reject(name,mutator,code):
        def body():
            value=copy.deepcopy(baseline);mutator(value)
            try:parse(value)
            except qa.ProtocolError as error:need(str(error)==code,'wrong rejection '+str(error))
            else:raise AssertionError('negative control passed')
        check(name,body)

    def alter_idle(**fields):
        return lambda value:value['inspection_idle_observation'].update(fields)

    check('actual_parser_accepts_complete_inspection_after_idle',lambda:parse(copy.deepcopy(baseline)))
    def immediate():
        value=copy.deepcopy(baseline);value['inspection_idle_observation'].update(last_elapsed_ms=1100,waited_ms=0)
        parse(value)
    check('actual_parser_accepts_already_quiet_immediate_return',immediate)

    def state_without_idle():
        req={'protocol':qa.PROTOCOL,'nonce':'2'*32,'op':'state'}
        value=copy.deepcopy(baseline)
        value.update(op='state',nonce=req['nonce'],request_sha256=qa.sha(qa.canonical(req)),
                     ui_automation_connected=False,requires_post_termination_state_check=False,state=state,
                     window_observation={},tree_observations=[],inspection_idle_observation={})
        value['restoration']['service_info_captured']=False
        parse(value,req)
    check('state_success_keeps_no_automation_idle_or_capture',state_without_idle)
    reject('missing_idle_record_rejected',lambda v:v.pop('inspection_idle_observation'),'SAFE_INSPECTION_IDLE_BOUND')
    reject('empty_idle_cannot_qualify_inspect',lambda v:v.update(inspection_idle_observation={}),
           'INSPECTION_IDLE_OBSERVATION_REQUIRED')
    reject('extra_idle_key_rejected',alter_idle(extra=True),'EXACT_INSPECTION_IDLE_FIELDS_REQUIRED')
    reject('non_boolean_qualified_rejected',alter_idle(qualified=1),'EXACT_INSPECTION_IDLE_FIELDS_REQUIRED')
    reject('call_count_cannot_exceed_one',alter_idle(call_count=2),'INSPECTION_IDLE_TIME_OR_CALL_BOUND')
    reject('quiet_budget_constant_cannot_change',alter_idle(quiet_timeout_ms=499),'INSPECTION_IDLE_ORIGINAL_BUDGET_REQUIRED')
    reject('global_cap_cannot_change',alter_idle(global_timeout_cap_ms=2001),'INSPECTION_IDLE_ORIGINAL_BUDGET_REQUIRED')
    reject('original_operation_budget_cannot_change',alter_idle(operation_deadline_ms=8001),'INSPECTION_IDLE_ORIGINAL_BUDGET_REQUIRED')
    reject('effective_global_must_equal_remaining_budget',alter_idle(global_timeout_ms=1999),
           'INSPECTION_IDLE_REMAINING_BUDGET_MISMATCH')
    reject('operation_start_must_bind_same_helper',alter_idle(operation_started_elapsed_ms=999),
           'INSPECTION_IDLE_ORIGINAL_BUDGET_REQUIRED')
    reject('boolean_time_rejected',alter_idle(waited_ms=True),'EXACT_INSPECTION_IDLE_FIELDS_REQUIRED')
    reject('content_readiness_claim_rejected',alter_idle(content_ready_proven=True),'IDLE_CANNOT_PROVE_CONTENT_OR_FUTURE_STABILITY')
    reject('future_stability_claim_rejected',alter_idle(future_stability_proven=True),'IDLE_CANNOT_PROVE_CONTENT_OR_FUTURE_STABILITY')
    reject('event_quiet_scope_must_be_explicit',alter_idle(event_quiet_only=False),'IDLE_CANNOT_PROVE_CONTENT_OR_FUTURE_STABILITY')
    reject('api_ack_without_qualification_rejected',alter_idle(qualified=False),'SUCCESSFUL_BOUNDED_EVENT_IDLE_REQUIRED')
    reject('no_api_return_cannot_qualify',alter_idle(api_returned=False),'SUCCESSFUL_BOUNDED_EVENT_IDLE_REQUIRED')
    reject('gate_error_cannot_qualify',alter_idle(gate_error='INSPECTION_IDLE_TIMEOUT'),'SUCCESSFUL_BOUNDED_EVENT_IDLE_REQUIRED')
    reject('cause_cannot_qualify',alter_idle(exception_class='java.util.concurrent.TimeoutException'),
           'SUCCESSFUL_BOUNDED_EVENT_IDLE_REQUIRED')
    reject('secondary_clock_error_cannot_qualify',alter_idle(secondary_clock_exception_class='java.lang.IllegalStateException'),
           'SUCCESSFUL_BOUNDED_EVENT_IDLE_REQUIRED')
    reject('actual_wait_duration_must_match_clocks',alter_idle(waited_ms=499),'INSPECTION_IDLE_TIME_OR_CALL_BOUND')
    reject('returned_api_after_global_budget_rejected',alter_idle(last_elapsed_ms=3101,waited_ms=2001),
           'SUCCESSFUL_BOUNDED_EVENT_IDLE_REQUIRED')
    reject('idle_observation_cannot_outlive_helper_result',alter_idle(last_elapsed_ms=1801,waited_ms=701),
           'INSPECTION_IDLE_OUTLIVES_HELPER_RESULT')
    reject('tree_capture_cannot_precede_idle_end',
           lambda v:v['tree_observations'][0].update(began_elapsed_ms=1599),
           'INSPECTION_CAPTURE_MUST_FOLLOW_ITS_IDLE_OBSERVATION')
    reject('event_idle_cannot_qualify_partial_tree',lambda v:v['tree_observations'][0].update(complete=False),
           'PARTIAL_TREE_CANNOT_QUALIFY')

    def original_null_child_failure():
        value=copy.deepcopy(baseline);value.update(ok=False,error='TREE_CHANGED_NULL_CHILD')
        value['tree_observations'][0].update(complete=False,attempted_nodes=2,emitted_nodes=1,serialized_bytes=0)
        got=qa.failure_diagnostic(wire(value,0),request,30000)
        need(got['error']=='TREE_CHANGED_NULL_CHILD' and got['qualified_success'] is False and
             got['action_attempted'] is False and got['outcome_unknown'] is False and
             got['inspection_idle_observation']['qualified'] is True and
             got['tree_observations'][0]['complete'] is False and 'inspection' not in got,'first capture failure preserved')
    check('later_null_child_retains_original_failure_and_idle_only_metadata',original_null_child_failure)

    def timeout_failure():
        value=copy.deepcopy(baseline);value.update(ok=False,error='INSPECTION_IDLE_TIMEOUT',finished_elapsed_ms=3200,
                                                  window_observation={},tree_observations=[])
        value['inspection_idle_observation'].update(qualified=False,api_returned=False,last_elapsed_ms=3101,
            waited_ms=2001,gate_error='INSPECTION_IDLE_TIMEOUT',exception_class='java.util.concurrent.TimeoutException')
        got=qa.failure_diagnostic(wire(value,0),request,30000)
        need(got['error']=='INSPECTION_IDLE_TIMEOUT' and not got['qualified_success'] and
             got['inspection_idle_observation']['exception_class']=='java.util.concurrent.TimeoutException' and
             got['tree_observations']==[] and got['window_observation']=={},'timeout diagnostic retained')
        try:qa.parse_completed(wire(value,0),b'',0,request,30000)
        except qa.ProtocolError as error:need(str(error)=='EXACT_SUCCESSFUL_FINISH_REQUIRED','failed finish changed')
        else:raise AssertionError('failure finish accepted')
    check('timeout_remains_failed_without_capture_or_successful_finish',timeout_failure)

    def before_gate_failure():
        value=copy.deepcopy(baseline);value.update(ok=False,error='TARGET_UID_MISMATCH',
            window_observation={},tree_observations=[],inspection_idle_observation={})
        got=qa.failure_diagnostic(wire(value,0),request,30000)
        need(got['inspection_idle_observation']=={} and not got['qualified_success'],'uncalled idle not invented')
    check('failure_before_gate_can_only_have_empty_idle_metadata',before_gate_failure)

    def other_operations():
        for op in ('state','click','set_text'):
            need(qa.inspection_idle_observation({},op,1000,True)=={},'empty noninspect metadata')
            try:qa.inspection_idle_observation(idle(),op,1000,True)
            except qa.ProtocolError as error:need(str(error)=='ONLY_INSPECT_MAY_WAIT_FOR_EVENT_IDLE','wrong operation gate')
            else:raise AssertionError('idle permitted in action or state')
    check('all_noninspect_operations_require_empty_idle_metadata',other_operations)

    def old_uid():
        value=copy.deepcopy(baseline);value['self_uid']=10175
        try:parse(value,uid=10175)
        except qa.ProtocolError as error:need(str(error)=='INSTALLED_HELPER_IDENTITY_REQUIRED','wrong UID rejection')
        else:raise AssertionError('old Amazon R1 UID accepted')
    check('old_amazon_r1_uid_rejected_even_when_wire_uid_matches_argument',old_uid)

    need(len(rows)==32,'exact idle protocol case count')
    return {'schema':1,'all_passed':True,'count':len(rows),'cases':rows,
            'android_calls':0,'tree_captures':0,'input_actions':0,
            'production_contract_sha256':hashlib.sha256(contract_source.encode()).hexdigest()}
