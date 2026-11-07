"""Current-baseline scope controls using this generated production parser."""
import ast,copy,hashlib,json,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
def run_controls():
    raw=(HERE/'qa_contract.py').read_bytes()
    qa=types.ModuleType('actual_current_baseline_qa')
    qa.__file__=str(HERE/'qa_contract.py')
    exec(compile(raw,qa.__file__,'exec'),qa.__dict__)
    base={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,
          'activity':qa.PACKAGE+'/Fixture','window_token':'1234',
          'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
          'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
          'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}
    rows=[]
    def ok(name,value):
        qa.require(qa.scope(value)==base,'CURRENT_SCOPE_POSITIVE_FAILED')
        rows.append({'name':name,'passed':True})
    def no(name,change):
        v=copy.deepcopy(base);change(v)
        try:qa.scope(v)
        except qa.ProtocolError:pass
        else:raise RuntimeError('CURRENT_SCOPE_NEGATIVE_ACCEPTED')
        rows.append({'name':name,'passed':True})
    ok('exact_new_current_scope',copy.deepcopy(base))
    for key in ('main_baseline_schema','main_baseline_sha256','main_baseline_qualification_sha256'):
        no('missing_'+key,lambda v,k=key:v.pop(k))
    no('old_epoch',lambda v:v.update(main_epoch_sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))
    no('old_baseline_schema',lambda v:v.update(main_baseline_schema='pocket4-framework-epoch-v1'))
    no('wrong_baseline_digest',lambda v:v.update(main_baseline_sha256='0'*64))
    no('wrong_qualification_digest',lambda v:v.update(main_baseline_qualification_sha256='0'*64))
    no('extra_scope_field',lambda v:v.update(unbound=True))
    no('wrong_target_uid',lambda v:v.update(uid=qa.UID+1))
    no('foreign_package',lambda v:v.update(package='example.unrelated'))
    no('wrong_display',lambda v:v.update(display=1))
    adapter_raw=(HERE/'qa_adapter.py').read_bytes()
    tree=ast.parse(adapter_raw)
    original_session=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Session')
    selected_init=[x for x in original_session.body if isinstance(x,ast.FunctionDef) and x.name=='__init__']
    qa.require(len(selected_init)==1,'EXACT_PRODUCTION_SESSION_CONSTRUCTOR_REQUIRED')
    session_class=copy.deepcopy(original_session);session_class.body=copy.deepcopy(selected_init)
    selected=[x for x in tree.body if
              (isinstance(x,ast.FunctionDef) and x.name=='require') or
              (isinstance(x,ast.Assign) and len(x.targets)==1 and isinstance(x.targets[0],ast.Name) and
               x.targets[0].id=='RECORDER_MANIFEST_SHA')]+[session_class]
    qa.require(len(selected)==3,'EXACT_PRODUCTION_SESSION_GUARD_SELECTION_REQUIRED')
    session_scope={}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'actual_session_constructor','exec'),session_scope)
    host_sha=session_scope['RECORDER_MANIFEST_SHA']
    def fixture():
        return types.SimpleNamespace(contract=types.SimpleNamespace(sha256=host_sha),_private_backend_transport=False,
            scope={'schema':'pocket4-current-recorder-scope-v2','current_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
                   'epoch_sha256':qa.MAIN_EPOCH,'current_baseline_sha256':qa.MAIN_BASELINE_SHA,
                   'current_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
                   'package':qa.PACKAGE,'uid':qa.UID})
    session_scope['Session'](fixture(),None,qa,{},99999)
    rows.append({'name':'actual_R6_session_scope_positive','passed':True})
    def host_no(name,change):
        flow=fixture();change(flow)
        try:session_scope['Session'](flow,None,qa,{},99999)
        except RuntimeError:pass
        else:raise RuntimeError('CURRENT_HOST_SESSION_NEGATIVE_ACCEPTED')
        rows.append({'name':name,'passed':True})
    host_no('old_R4_recorder_rejected',lambda f:setattr(f.contract,'sha256','52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'))
    host_no('missing_typed_flow_schema',lambda f:f.scope.pop('schema'))
    host_no('wrong_current_baseline_schema',lambda f:f.scope.update(current_baseline_schema='old-activation'))
    host_no('old_host_epoch',lambda f:f.scope.update(epoch_sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))
    host_no('wrong_host_baseline',lambda f:f.scope.update(current_baseline_sha256='0'*64))
    host_no('wrong_host_qualification',lambda f:f.scope.update(current_baseline_qualification_sha256='0'*64))
    host_no('foreign_host_package',lambda f:f.scope.update(package='example.unrelated'))
    host_no('bool_host_uid',lambda f:f.scope.update(uid=True))
    no('previous_current_epoch',lambda v:v.update(main_epoch_sha256='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'))
    no('previous_baseline_v1_schema',lambda v:v.update(main_baseline_schema='pocket4-main-current-baseline-v1'))
    no('previous_baseline_digest',lambda v:v.update(main_baseline_sha256='163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266'))
    no('previous_qualification_digest',lambda v:v.update(main_baseline_qualification_sha256='f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6'))
    host_no('previous_R5_host_manifest',lambda f:setattr(f.contract,'sha256','6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'))
    host_no('previous_typed_scope_v1',lambda f:f.scope.update(schema='pocket4-current-recorder-scope-v1'))
    try:session_scope['Session'](fixture(),None,qa,{},10160)
    except RuntimeError:pass
    else:raise RuntimeError('PREVIOUS_HELPER_UID_SESSION_ACCEPTED')
    rows.append({'name':'parent_current_helper_UID_session_rejected','passed':True})
    qa.require(qa.PROTOCOL=='pocket4-owned-hilton-qa-v1' and qa.SELF=='org.droidloom.qa.hilton.r1',
               'EXACT_NEW_HELPER_PROTOCOL_REQUIRED')
    rows.append({'name':'exact_new_helper_protocol_and_package','passed':True})
    req={'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'state'}
    try:qa.validate_request({**req,'protocol':'pocket4-owned-bestbuy-qa-v4'})
    except qa.ProtocolError:pass
    else:raise RuntimeError('PREVIOUS_HELPER_PROTOCOL_ACCEPTED')
    rows.append({'name':'parent_helper_protocol_rejected','passed':True})
    import base64,gzip
    def state_value(uid):
        value={'protocol':qa.PROTOCOL,'nonce':req['nonce'],'op':'state',
            'request_sha256':qa.sha(qa.validate_request(req)),'wire_codec':'gzip-canonical-json-v1',
            'self_uid':uid,'self_pid':1234,'ok':True,'error':None,'secondary_errors':[],
            'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,
            'business_success_verified':False,'accessibility_mode_restoration_verified':None,
            'started_elapsed_ms':100,'finished_elapsed_ms':110,
            'action_attempted':False,'outcome_unknown':False,'ui_automation_connected':False,
            'requires_post_termination_state_check':False,
            'restoration':{'service_info_captured':False,'service_info_verified':True},
            'state':{'accessibility_enabled':False,'touch_exploration_enabled':False,
                     'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')},
            'window_observation':{},'tree_observations':[]}
        # This helper has no inspection idle metadata field.
        return value
    def wire(value):
        text=base64.b64encode(gzip.compress(qa.canonical(value),mtime=0)).decode()
        return ('INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64='+text+
                '\nINSTRUMENTATION_CODE: -1\n').encode()
    qa.parse_completed(wire(state_value(99999)),b'',0,req,99999)
    rows.append({'name':'actual_state_wire_new_identity_positive','passed':True})
    try:qa.parse_completed(wire(state_value(10160)),b'',0,req,10160)
    except qa.ProtocolError as error:
        qa.require(str(error)=='INSTALLED_HELPER_IDENTITY_REQUIRED','PREVIOUS_UID_WRONG_FIRST_CAUSE')
    else:raise RuntimeError('PREVIOUS_HELPER_UID_WIRE_ACCEPTED')
    rows.append({'name':'parent_current_helper_UID_wire_rejected','passed':True})
    qa.require(len(rows)==32,'EXACT_CURRENT_BASELINE_SCOPE_CASES')
    return {'schema':'pocket4-current-baseline-scope-controls-v2','all_passed':True,'count':32,
            'cases':rows,'production_contract_sha256':hashlib.sha256(raw).hexdigest(),
            'production_adapter_sha256':hashlib.sha256(adapter_raw).hexdigest(),'host_recorder_manifest_sha256':host_sha,
            'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
            'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
            'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
            'Android_commands':0,'UI_actions':0,'helper_installed_uid':None}
if __name__=='__main__':print(json.dumps(run_controls(),sort_keys=True))
