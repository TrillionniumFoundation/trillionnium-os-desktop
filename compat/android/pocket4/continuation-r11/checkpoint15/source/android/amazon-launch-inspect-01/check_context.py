#!/usr/bin/env python3
"""Local production policy/original-method controls; all Android I/O is a seam.

No device, namespace, UI or helper process is started. Real temporary-file
claims and the original task parser/retirement lock are exercised locally.
"""
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import types

ROOT=Path('/workspace/scratch/94990735b266')
HERE=Path(__file__).resolve().parent

def module(path,name,expected=None):
    b=path.read_bytes()
    if expected:assert hashlib.sha256(b).hexdigest()==expected
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(b,str(path),'exec'),m.__dict__)
    return m


def main():
    ctx=module(HERE/'amazon_task_context.py','task_context')
    entry=module(HERE/'owned_inspect.py','entry')
    original=module(ROOT/'android-qa-install-state-01/review-inputs/recorder.py','actual_shared_recorder',
        '5f25f22db55ba94e6ac895c2ce274b6959a274b64c9aa82bbc30d8c3c860f511')
    task_path=HERE/'task_scope_baseline_reference.py'
    assert hashlib.sha256(task_path.read_bytes()).hexdigest()==original.TASK_SHA
    tasks=original.task_functions(task_path)
    qa=module(ROOT/'owned-amazon-qa-r1-build01/source/qa_contract.py','actual_amazon_contract',
        'aebd0f44bcec8433586fb9cdab1ce0e0be9ac2adedf5c5c5c485425a13bc3402')
    adapter=module(ROOT/'owned-amazon-qa-r1-build01/source/qa_adapter.py','actual_amazon_session',
        '3f705d3a7a605b9436beb0e77bd156923cd8e581fe9f3f6d4635eb62910cce59')
    resolver=module(ROOT/'android-amazon-launcher-resolve-readonly-01/resolve_amazon.py','actual_resolver',entry.RESOLVER_SHA)
    rows=[]
    def case(name,fn):
        fn();rows.append({'case':name,'expected_met':True})
    def rejected(call,part):
        try:call()
        except BaseException as e:assert part in str(e),(part,repr(e));return
        raise AssertionError('expected rejection '+part)
    def stacks(amazon=False,foreign=False):
        out='RootTask id=851 displayId=0 userId=0 mWindowingMode=freeform\n taskId=851: owned.fixture.home/Home userId=0\n'
        if amazon:
            pkg='owned.fixture.other' if foreign else ctx.PACKAGE
            out+='RootTask id=936 displayId=0 userId=0 mWindowingMode=freeform\n taskId=936: '+pkg+'/Home userId=0\n'
        return out.encode()
    actual_dir=ROOT/'root-recovery-20261104-02/evidence/amazon-launcher-resolve01'
    records={}
    for name,(path,size,digest) in entry.RESOLVER_RECORDS.items():
        raw=(actual_dir/path).read_bytes();assert len(raw)==size and hashlib.sha256(raw).hexdigest()==digest
        records[name]=json.loads(raw)
    case('actual_resolver_retained_source_component_and_retirement_binding',
         lambda:entry.actual_resolver(copy.deepcopy(records),resolver.INSTALLED))
    def wrong_component():
        r=copy.deepcopy(records);r['worker']['launcher']['component']=ctx.PACKAGE+'/Other'
        rejected(lambda:entry.actual_resolver(r,resolver.INSTALLED),'EXACT_COMPONENT')
    case('wrong_component_receipt_rejected',wrong_component)
    def wrong_uid():
        r=copy.deepcopy(records);r['worker']['helper_after']['uid']=10170
        rejected(lambda:entry.actual_resolver(r,resolver.INSTALLED),'SCOPE_STABILITY')
    case('old_Bili_helper_UID_rejected',wrong_uid)
    def wrong_cleanup():
        r=copy.deepcopy(records);r['worker']['held_binding_released']=False
        rejected(lambda:entry.actual_resolver(r,resolver.INSTALLED),'RETIRED')
    case('unreleased_resolver_rejected',wrong_cleanup)

    with tempfile.TemporaryDirectory(prefix='owned-amazon-api-control-',dir=HERE) as td:
        parent=Path(td);original.ACTION_LOCK=str(parent/'actual-original-action.lock')
        serial=[0]
        class Target:
            record={'fixture':True}
            def verify(self):pass
            def close(self):self.closed=True
            def read_file(self,path,limit):
                assert path=='/data/app/owned-fixture/base.apk';return b'owned-fixture-apk',{'fixture':True}
        backend_path=ROOT/'android-bili-r3-video-foreground-reference-01/android_backend.py'
        class Contract:
            sha256=adapter.RECORDER_MANIFEST_SHA
            def load(self,path,name):
                assert path=='references/android_backend.py'
                return module(backend_path,name,'088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae')
        def make(phase,queue,scope_file=False):
            serial[0]+=1;root=parent/str(serial[0]);root.mkdir();step=root/(phase+'-01');step.mkdir()
            observations={'native':0,'remove':0,'instrument':[],'commands':[]}
            class Transport:
                FRAMEWORK_EPOCH_SHA256=qa.MAIN_EPOCH
                class BoundArun:
                    def __init__(self,**kwargs):self.kwargs=kwargs
                    def __call__(self,argv,timeout):
                        observations['commands'].append(list(argv))
                        if argv==ctx.STACKS:
                            assert queue;return queue.pop(0)
                        if argv==ctx.OWN_UID:return ('package:'+ctx.SELF+' uid:10175\n').encode()
                        if argv==ctx.OWN_PATH:return b'package:/data/app/owned-fixture/base.apk\n'
                        if argv==ctx.FOREGROUND:return ('mCurrentFocus=Window{ab u0 '+entry.COMPONENT+'}\n').encode()
                        if argv[:4]==['/system/bin/cmd','activity','stack','remove']:
                            observations['remove']+=1;return b''
                        if argv[:3]==['/system/bin/am','instrument','-w']:
                            observations['instrument'].append(argv);return b''
                        raise AssertionError('unexpected fake Android request '+repr(argv))
            def native(self,argv,timeout,**kwargs):
                assert kwargs['mutation'] is True and kwargs['label']=='One native launch'
                observations['native']+=1;self.action_attempted=True;self.command_index+=1
                return json.dumps({'ok':True,'state':'running','host_pid':100,
                    'launch':'object=1 composer_display=0 android_display=0 task=936'}).encode()
            shared=types.SimpleNamespace(**original.__dict__)
            shared.Flow=types.SimpleNamespace(command=native,launch_locked=original.Flow.launch_locked,
                cleanup=original.Flow.cleanup,stacks=original.Flow.stacks,selected_task=original.Flow.selected_task)
            flow=ctx.Flow(recorder=shared,contract=Contract(),target=Target(),environment={},transport=Transport,
                main_guard=lambda:None,root=root,step=step,phase=phase,
                scope={'package':ctx.PACKAGE,'uid':ctx.UID,'user':0,'epoch_sha256':qa.MAIN_EPOCH,
                    'component':entry.COMPONENT},activation={'status':{'host_pid':100},
                    'framework_epoch':{'binding':{'processes':{'init':{'host_pid':123}}}}},
                tasks=tasks,qa=qa,inspect_plan=entry.PLAN,resolve=resolver.RESOLVE,
                read=entry.read,deadline=time.monotonic()+30)
            if scope_file:
                original.write_new(root/'launch-scope.json',{'task':936,'package':ctx.PACKAGE,
                    'epoch_sha256':qa.MAIN_EPOCH,'prelaunch_absent':True,'cleanup_allowed':True,
                    'launch_step':'launch-01','prelaunch_task_ids':[851],'native_receipt_sha256':'a'*64})
            return flow,observations
        def normal_launch():
            f,o=make('launch',[stacks(),stacks(True)])
            r=f.launch_locked();assert r['native_launch_acknowledged'] and f.selected_task()['task']==936
            assert o['native']==1 and o['remove']==0 and f.policy.counts=={'stacks':2}
            rejected(f.launch_locked,'ALREADY_ATTEMPTED');assert o['native']==1
        case('actual_original_launch_with_new_policy_and_exact_owned_scope_once',normal_launch)
        def existing_target():
            f,o=make('launch',[stacks(True)]);rejected(f.launch_locked,'PREEXISTING')
            assert o['native']==o['remove']==0 and not (f.root/'launch-attempted.json').exists()
        case('preexisting_Amazon_task_preserved_before_launch',existing_target)
        def wrong_leaf():
            f,o=make('launch',[stacks(),stacks(True,True)]);rejected(f.launch_locked,'NOT_EXACT_LEAF')
            assert o['native']==1 and not (f.root/'launch-scope.json').exists()
        case('ambiguous_native_result_does_not_authorize_cleanup',wrong_leaf)
        def normal_cleanup():
            f,o=make('cleanup',[stacks(True),stacks()],True)
            r=f.cleanup();assert r['new_leaf_removed_and_verified'] and r['task_ids_after']==[851] and o['remove']==1
            rejected(f.cleanup,'ALREADY_ATTEMPTED');assert o['remove']==1
            # Actual original lock is released. No outer action-lock was held.
            lock=original.lock_file(original.ACTION_LOCK);os.close(lock)
        case('actual_original_cleanup_one_remove_same_lock_released_others_preserved',normal_cleanup)
        def already_absent():
            f,o=make('cleanup',[stacks()],True);r=f.cleanup()
            assert r['new_task_already_absent'] and not r['removal_attempted'] and o['remove']==0
            assert f.last_stack_task_ids==[851]
        case('already_absent_cleanup_has_no_remove_and_records_current_tasks',already_absent)
        def foreign_leaf():
            f,o=make('cleanup',[stacks(True,True)],True);rejected(f.cleanup,'TASK_SCOPE_CHANGED');assert o['remove']==0
        case('foreign_current_leaf_cannot_be_removed',foreign_leaf)
        def extras():
            for argv,mutation in ((['/system/bin/input','tap','100','100'],True),
                 (['/system/bin/cmd','activity','stack','remove','851'],True),
                 (['/system/bin/cmd','package','install','-r','evil.apk'],True)):
                f,o=make('inspect',[],True)
                rejected(lambda:f.android(argv,20,mutation=mutation),'NO_OTHER_AMAZON_COMMAND')
                assert not o['commands']
        case('tap_other_task_remove_and_install_denied_before_transport',extras)

        def original_sequence(fail_inspect=False):
            f,o=make('inspect',[stacks(True),stacks(True)],True)
            proof={'APK':{'bytes':len(b'owned-fixture-apk'),'sha256':hashlib.sha256(b'owned-fixture-apk').hexdigest()},
                   'signer_certificate_sha256':'fixture-only-not-actual-signature'}
            ownedqa=types.SimpleNamespace(**qa.__dict__)
            ownedqa.assess_restoration=lambda before,middle,after:{'fixture_restoration_only':True}
            session=adapter.Session(f,original,ownedqa,proof,10175)
            calls=[]
            def instrument(request):
                # Request validation, argv, new Policy and original sequence are
                # real; helper execution/results and restoration are I/O seams.
                qa.validate_request(request);original.write_new(f.step/(request['nonce']+'.request.json'),request)
                f.android(qa.instrumentation_argv(request),20,mutation=False);calls.append(request['op'])
                if fail_inspect and request['op']=='inspect':raise RuntimeError('FIXTURE_PRIMARY_INSPECTION_FAILURE')
                return {'wire_sha256':'a'*64,'helper':{'nonce':request['nonce'],'self_uid':10175,
                    'state':{'fixture':'unchanged'},'ui_automation_connected':False}}
            session.instrument=instrument
            if fail_inspect:
                rejected(lambda:session.sequence(copy.deepcopy(entry.PLAN)),'FIXTURE_PRIMARY_INSPECTION_FAILURE')
                assert calls==['state','inspect','state'] and session.sequence_observation['after_state_completed']
                assert not session.sequence_observation['restoration_qualified']
            else:
                v=session.sequence(copy.deepcopy(entry.PLAN))
                assert v['after_state_completed'] and v['restoration_qualified'] and calls==['state','inspect','state']
                assert f.policy.counts=={'helper_uid':2,'helper_path':2,'stacks':2,'instrument':3,'foreground':3}
            assert f.policy.used_nonces==set(entry.PLAN['nonces'].values()) and not f.action_attempted
            assert o['native']==o['remove']==0
        case('original_Session_actual_new_policy_API_counts_and_3_private_foregrounds',original_sequence)
        case('original_Session_failed_inspect_still_new_after_state_first_error_kept',lambda:original_sequence(True))
        def coordinator_failure(cleanup_fails):
            serial[0]+=1;control_root=parent/str(serial[0]);control_root.mkdir()
            flow_root=parent/(str(serial[0])+'-flow');source=control_root/'source';source.mkdir()
            fields=('ROOT','FLOW','HERE','SOURCE','qualified')
            saved={k:getattr(entry,k) for k in fields}
            main_reads=[];calls=[];expected='c'*64
            try:
                entry.ROOT=control_root;entry.FLOW=flow_root;entry.HERE=entry.SOURCE=source
                ref=types.SimpleNamespace(ACTIVATION=control_root/'activation-input.json',
                    VERIFIED=control_root/'verified-input.json',ACTIVATION_SHA='a'*64,VERIFIED_SHA='b'*64,
                    EPOCH=qa.MAIN_EPOCH,EPOCH_SOURCE=control_root/'epoch-input.py',EPOCH_SOURCE_SHA='d'*64,
                    read=lambda *a,**k:b'{}',module=lambda *a,**k:object(),
                    write_new=lambda p,v,**k:_write(p,v))
                def _write(path,value):
                    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
                    with Path(path).open('xb') as stream:stream.write(raw)
                    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                def guard(*args):main_reads.append(True);return {'fixture_Main':'same'}
                ref.main_guard=guard
                def remember(result,phase,error):
                    row={'phase':phase,'type':type(error).__name__,'message':str(error)}
                    if result['error'] is None:result['error']=row
                    else:result['secondary_errors'].append(row)
                    result['ok']=False
                util=types.SimpleNamespace(prepare_owned_limits=lambda:{'fixture_resource':'same'},
                    owned_resources=lambda:{'fixture_resource':'same'},resources_qualified=lambda a,b:None,
                    remember=remember)
                q=types.SimpleNamespace(util=util,ref=ref,install={'fixture':True},resolution={'component':entry.COMPONENT},
                    adapter=types.SimpleNamespace(RECORDER_MANIFEST_SHA=adapter.RECORDER_MANIFEST_SHA))
                entry.qualified=lambda wanted:q if wanted==expected else None
                _write(control_root/'once.claim.json',{'nonce':entry.NONCE,'source_manifest_sha256':expected,'automatic_retry':False})
                def run_cli(name,argv,timeout,evidence,main_guard):
                    phase=argv[argv.index('--worker-once')+1];calls.append(phase);main_guard()
                    if phase=='inspect':raise RuntimeError('FIXTURE_PRIMARY_INSPECT_FAILED')
                    if phase=='cleanup' and cleanup_fails:raise RuntimeError('FIXTURE_SECONDARY_CLEANUP_FAILED')
                    step=flow_root/'steps'/(phase+'-01');step.mkdir()
                    result={'phase':phase,'nonce':entry.NONCE,'source_manifest_sha256':expected,
                        'package':entry.PACKAGE,'uid':entry.UID,'helper_package':entry.SELF,'helper_uid':entry.HELPER_UID,
                        'ok':True,'error':None,'secondary_errors':[],'outcome_unknown':False,'final_Main_guard_passed':True,
                        'held_binding_released':True,'flow_lock_released':True,'action_lock_released':True,
                        'target_FD_cleanup':{'held_APK_FDs_closed':3},'target_before':{},'target_after':{},
                        'helper_before':{},'helper_after':{},'source_and_artifact_unchanged':True}
                    if phase=='launch':
                        result['launch']={'native_launch_acknowledged':True}
                        _write(flow_root/'launch-scope.json',{'task':936,'package':entry.PACKAGE,
                            'epoch_sha256':qa.MAIN_EPOCH,'prelaunch_absent':True,'cleanup_allowed':True,
                            'launch_step':'launch-01','prelaunch_task_ids':[851],'native_receipt_sha256':'a'*64})
                    else:result.update(owned_task_absent=True,task_ids_after=[851])
                    _write(step/'result.json',result)
                    return result
                ref.run_cli=run_cli
                with contextlib.redirect_stdout(io.StringIO()):rc=entry.execute(expected)
                final=json.loads((control_root/'result.json').read_text())
                assert rc==1 and not final['ok'] and calls==['launch','inspect','cleanup']
                assert final['error']['message']=='FIXTURE_PRIMARY_INSPECT_FAILED'
                assert final['Main_after']==final['Main_before'] and len(main_reads)>=4
                if cleanup_fails:
                    assert any(x['message']=='FIXTURE_SECONDARY_CLEANUP_FAILED' for x in final['secondary_errors'])
                    assert not final.get('owned_task_absent_after_cleanup')
                else:
                    assert final['owned_task_absent_after_cleanup'] and final['task_ids_after']==[851]
                    assert final['secondary_errors']==[]
            finally:
                for k,v in saved.items():setattr(entry,k,v)
        case('actual_coordinator_failed_inspect_still_calls_exact_cleanup_once_and_retains_FAIL',lambda:coordinator_failure(False))
        case('actual_coordinator_cleanup_error_secondary_Main_finally_still_runs',lambda:coordinator_failure(True))
    print(json.dumps({'schema':1,'state':'PASS','cases':rows,
        'actual_retained_resolver_reference_pins_verified':True,
        'original_recorder_sha256':'5f25f22db55ba94e6ac895c2ce274b6959a274b64c9aa82bbc30d8c3c860f511',
        'original_task_source_sha256':original.TASK_SHA,
        'current_source_pins':{n:{'bytes':(HERE/n).stat().st_size,'sha256':hashlib.sha256((HERE/n).read_bytes()).hexdigest()} for n in ('owned_inspect.py','amazon_task_context.py')},
        'actual_API_methods_executed':['new Policy.admit','new Flow launch/stacks/cleanup delegation','original Flow.launch_locked/cleanup/stacks/selected_task','original parse_stacks/exact_leaf/wait_for_removal','original Session.sequence/installed/foreground/task','new coordinator execute/finally/durable/owned_scope'],
        'explicit_seams':['Android commands and native launch return synthetic owned-fixture bytes','held target/guard and APK bytes are local stand-ins','helper instrument results and assess_restoration are I/O seams; not helper/platform qualification','coordinator failure controls replace qualified input loading, child invocation, resource reads and Main guard with owned fixtures'],
        'real_local_effects':['temporary once claims/results','original exclusive file lock and release'],
        'device_or_namespace_or_UI_calls':0,'commercial_UI_or_pixels_read':False,
        'actual_launch_inspect_qualification':'NOT_RUN'},indent=2,sort_keys=True))


if __name__=='__main__':main()
