#!/usr/bin/env python3
"""Actual old/new Python methods, synthetic Session seam; no Android or UI."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
OLD = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/qa/owned-bili-qa-recovery-02/source')


def load(path):
    raw = path.read_bytes(); ast.parse(raw,filename=str(path))
    m = types.ModuleType(path.stem); m.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),m.__dict__)
    return m


def main():
    old,new,qa = load(OLD/'qa_adapter.py'),load(HERE/'source/qa_adapter.py'),load(HERE/'source/qa_contract.py')
    state = {'accessibility_enabled':False,'touch_exploration_enabled':False,'enabled_service_count':0,
             'enabled_services_sha256':hashlib.sha256(b'[]').hexdigest()}
    plan = {'schema':1,'operation':'inspect','nonces':{'before':'1'*32,'inspect':'2'*32,'after':'3'*32}}

    class Fake:
        def __init__(self, scenario):
            self.qa=qa; self.scenario=scenario; self.calls=[]
            self.primary=qa.ProtocolError('EXACT_SUCCESSFUL_FINISH_REQUIRED')
            self.secondary=RuntimeError('OWNED_POSTSTATE_FAILURE')
        def installed(self):
            return {'owned-synthetic-install':True}
        def task(self):
            return {'owned-synthetic-task':7}
        def foreground(self):
            return {'owned-synthetic-scope':True}
        def instrument(self, request):
            phase=next(k for k,v in plan['nonces'].items() if v==request['nonce'])
            self.calls.append(phase)
            if phase=='inspect' and self.scenario in ('inspect_fail','inspect_and_after_fail'):
                raise self.primary
            if phase=='before' and self.scenario=='before_fail':
                raise self.primary
            if phase=='after' and self.scenario=='inspect_and_after_fail':
                raise self.secondary
            observed=dict(state)
            if phase=='after' and self.scenario=='after_changed':
                observed['accessibility_enabled']=True
            helper={'op':request['op'],'nonce':request['nonce'],'self_uid':10165,
                    'ui_automation_connected':False}
            if request['op']=='state': helper['state']=observed
            else: helper.update(accessibility_state_before_connection=dict(state),restoration={'service_info_verified':True})
            return {'helper':helper,'wire_sha256':request['nonce']*2}

    observed=[]
    baseline=Fake('inspect_fail')
    try: old.Session.sequence(baseline,plan)
    except qa.ProtocolError as e: assert e is baseline.primary
    else: raise AssertionError('old false success')
    assert baseline.calls==['before','inspect']
    observed.append({'case':'old_actual_sequence_skips_after_on_inspect_error','outcome':'EXPECTED_RED_REPRODUCED','calls':baseline.calls})
    for case in ('inspect_fail','inspect_and_after_fail','before_fail','after_changed','success'):
        f=Fake(case)
        try:
            result=new.Session.sequence(f,plan)
            assert case=='success' and result['restoration_qualified'] and result['after_state_completed']
        except BaseException as e:
            assert case!='success'
            if case in ('inspect_fail','inspect_and_after_fail','before_fail'): assert e is f.primary
            if case=='after_changed': assert str(e)=='POST_TERMINATION_ACCESSIBILITY_STATE_CHANGED'
            result=f.sequence_observation
            assert result['error'] is not None and not result['restoration_qualified']
            if case=='inspect_and_after_fail':
                assert [x['phase'] for x in result['secondary_errors']]==['independent_after_state']
                assert str(f.primary)=='EXACT_SUCCESSFUL_FINISH_REQUIRED'
        assert f.calls.count('after')==1 and f.calls.count('inspect')<=1
        assert f.calls==(['before','after'] if case=='before_fail' else ['before','inspect','after'])
        observed.append({'case':'new_'+case,'outcome':'PASS','calls':f.calls})
    request={'protocol':qa.PROTOCOL,'nonce':'4'*32,'op':'inspect','scope':{
        'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.PACKAGE+'/'+qa.PACKAGE+'.MainActivityV2',
        'window_token':'abc','main_epoch_sha256':qa.MAIN_EPOCH}}
    body={'protocol':qa.PROTOCOL,'nonce':request['nonce'],'op':'inspect',
        'request_sha256':qa.sha(qa.canonical(request)),'self_uid':10165,'self_pid':77,
        'ok':False,'error':'NO_FOCUSED_APPLICATION_WINDOW','restoration':{'service_info_verified':True},
        'window_observation':{},'inspection':{'nodes':[{'text':'SYNTHETIC_PRIVATE_SENTINEL'}]}}
    raw=qa.canonical(body)
    stdout=b'INSTRUMENTATION_RESULT: owned_qa_result_base64='+base64.b64encode(raw)+b'\nINSTRUMENTATION_CODE: 0\n'
    try: qa.parse_completed(stdout,b'',0,request,10165)
    except qa.ProtocolError as e: assert str(e)=='EXACT_SUCCESSFUL_FINISH_REQUIRED'
    else: raise AssertionError('finish zero qualified')
    diagnostic=qa.failure_diagnostic(stdout,request,10165)
    assert diagnostic['qualified_success'] is False and diagnostic['error']=='NO_FOCUSED_APPLICATION_WINDOW'
    assert 'SYNTHETIC_PRIVATE_SENTINEL' not in json.dumps(diagnostic) and 'inspection' not in diagnostic
    observed.append({'case':'finish0_stays_failure_and_diagnostic_excludes_nodes','outcome':'PASS'})
    window={'display':0,'id':7,'type':1,'focused':True,'active':True,'accessibility_focused':False,'layer':1}
    census={'sample':1,'event_serial':0,'elapsed_ms':1,'displays':[0],'windows':[window]}
    value={'requested_display':0,'selection':'exact-display-0-focused-application','wait_budget_ms':2000,
           'ready':True,'first':census,'last':census,'samples':1,'waited_ms':1,'selected_display':0,'selected_window_id':7}
    assert qa.window_observation(value)==value
    for name,mutate in [('other_display',lambda v:v['last']['windows'][0].update(display=1)),
                        ('window_title',lambda v:v['last']['windows'][0].update(title='SYNTHETIC_PRIVATE_SENTINEL')),
                        ('not_focused',lambda v:v['last']['windows'][0].update(focused=False))]:
        bad=json.loads(json.dumps(value));mutate(bad)
        try: qa.window_observation(bad)
        except qa.ProtocolError: pass
        else: raise AssertionError('bad census accepted: '+name)
        observed.append({'case':name+'_rejected','outcome':'PASS'})
    print(json.dumps({'schema':1,'scope':'actual Python methods with explicit synthetic Session/wire seams',
        'controls':observed,'all_expected_outcomes':True,'private_original_wire_embedded':False,
        'Go_or_Java_compile':False,'Android_or_namespace_calls':0,'actual_helper_UID_or_APK_inferred':False,
        'runtime_qualification':False},sort_keys=True,indent=2))


if __name__=='__main__':
    main()
