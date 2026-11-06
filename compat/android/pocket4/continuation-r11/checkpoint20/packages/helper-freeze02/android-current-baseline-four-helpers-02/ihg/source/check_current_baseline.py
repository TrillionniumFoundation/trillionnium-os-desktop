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
            scope={'schema':'pocket4-current-recorder-scope-v1','current_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
                   'epoch_sha256':qa.MAIN_EPOCH,'current_baseline_sha256':qa.MAIN_BASELINE_SHA,
                   'current_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
                   'package':qa.PACKAGE,'uid':qa.UID})
    session_scope['Session'](fixture(),None,qa,{},99999)
    rows.append({'name':'actual_R5_session_scope_positive','passed':True})
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
    qa.require(len(rows)==21,'EXACT_CURRENT_BASELINE_SCOPE_CASES')
    return {'schema':'pocket4-current-baseline-scope-controls-v1','all_passed':True,'count':21,
            'cases':rows,'production_contract_sha256':hashlib.sha256(raw).hexdigest(),
            'production_adapter_sha256':hashlib.sha256(adapter_raw).hexdigest(),'host_recorder_manifest_sha256':host_sha,
            'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
            'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
            'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
            'Android_commands':0,'UI_actions':0,'helper_installed_uid':None}
if __name__=='__main__':print(json.dumps(run_controls(),sort_keys=True))
