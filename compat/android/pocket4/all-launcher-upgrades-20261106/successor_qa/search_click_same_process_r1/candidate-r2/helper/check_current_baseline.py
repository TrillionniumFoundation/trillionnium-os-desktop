"""Current-baseline scope controls using this generated production parser."""
import copy,hashlib,json,types
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
          'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
          'runtime_epoch_sha256':qa.RUNTIME_EPOCH, 'app_scope_sha256':qa.APP_SCOPE_SHA}
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
    for key in ('runtime_epoch_sha256','app_scope_sha256'):
        no('missing_'+key,lambda v,k=key:v.pop(k))
        no('wrong_'+key,lambda v,k=key:v.update({k:'0'*64}))
    qa.require(len(rows)==16,'EXACT_CURRENT_BASELINE_SCOPE_CASES')
    return {'schema':'pocket4-successor-app-scope-controls-v1','all_passed':True,'count':16,
            'cases':rows,'production_contract_sha256':hashlib.sha256(raw).hexdigest(),
            'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
            'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
            'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
            'Android_commands':0,'UI_actions':0,'helper_installed_uid':None}
if __name__=='__main__':print(json.dumps(run_controls(),sort_keys=True))
