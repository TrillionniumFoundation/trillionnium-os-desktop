#!/usr/bin/env python3
"""Pure actual owned sequence, original validators, synthetic public I/O seams."""
from pathlib import Path
import ast,copy,hashlib,json,types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

fixture=load(ROOT/'owned-bili-qa-r6-reveal-01/controls/check_reveal.py','public_fixture')
qa,adapter=fixture.qa,fixture.adapter
module=load(HERE/'post_foreground.py','owned_post_foreground')
base=load(HERE/'owned_navigation.py','fresh_owned_source')

def focus(package='tv.danmaku.bili',activity='com.bilibili.search2.main.BiliMainSearchActivity',token='ab12',user='0'):
    return ('  mCurrentFocus=Window{'+token+' u'+user+' '+package+'/'+activity+'}\n').encode()

ZERO=b'  mCurrentFocus=null\n'
GOOD=focus()
MULTI=GOOD+focus(token='ab13')
FOREIGN=focus(package='org.synthetic.foreign',activity='PublicActivity')

def exercise(samples,fail=None,task_changed=None,late=None,bad_tree=False,late_install=False,changed_pre_focus=False):
    calls=[];clock=[0.0];reads=[];guard_calls=[];task_calls=[0];fg_calls=[0];install_calls=[0]
    original_failure=RuntimeError('SYNTHETIC_'+str(fail));input_count=[0]
    state={'accessibility_enabled':False,'touch_exploration_enabled':False,
        'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')}
    installed={'synthetic_installed_identity':True}
    owned={'task':12345,'package':qa.PACKAGE,'prelaunch_absent':True,'cleanup_allowed':True}
    scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,
        'activity':'tv.danmaku.bili/com.bilibili.MainActivityV2','window_token':'ab10',
        'main_epoch_sha256':qa.MAIN_EPOCH}
    tree=fixture.fixture()
    node=fixture.node(qa.PACKAGE+':id/expand_search','android.widget.LinearLayout','0',[320,60,1500,100])
    node.update(clickable=True,content_desc='Search bar, button',content_desc_sha256=qa.sha(b'Search bar, button'))
    tree['nodes']=[node];fixture.refresh(tree)
    if bad_tree:tree['complete']=False
    flow=types.SimpleNamespace(_private_backend_transport=False,action_attempted=False,
        transport=types.SimpleNamespace(_sequence=0))
    session=object.__new__(adapter.Session);session.qa=qa;session.uid=10184
    session.flow=flow;session.nonces=set()
    def guard(attempted=False):
        guard_calls.append(attempted)
        if fail=='Main_guard':raise original_failure
    flow.guard=guard
    def task():
        task_calls[0]+=1
        return dict(owned,task=12346) if task_calls[0]==task_changed else copy.deepcopy(owned)
    session.task=task
    def installed_read():
        install_calls[0]+=1
        return dict(installed,changed=True) if late_install and install_calls[0]>1 else copy.deepcopy(installed)
    session.installed=installed_read
    def foreground():
        fg_calls[0]+=1
        if fg_calls[0]>2 and fail in ('click','after_state','restoration'):
            raise RuntimeError('FOREGROUND_UNVERIFIED')
        if changed_pre_focus and fg_calls[0]==2:return dict(scope,window_token='ab11')
        return copy.deepcopy(scope)
    session.foreground=foreground
    def android(argv,timeout=20,mutation=False):
        assert argv==['/system/bin/dumpsys','window','displays'] and timeout==15
        assert mutation is False and flow._private_backend_transport is True
        assert flow.action_attempted and calls[-1]==('state',module.FIRST_PLAN['nonces']['after'])
        flow.transport._sequence+=1
        index=len(reads);reads.append(index)
        value=samples[min(index,len(samples)-1)]
        if isinstance(value,BaseException):raise value
        clock[0]+=13 if late==index else .01
        return value
    flow.android=android
    def instrument(request):
        qa.validate_request(request)
        nonce,op=request['nonce'],request['op']
        assert nonce not in session.nonces
        session.nonces.add(nonce);calls.append((op,nonce))
        if op=='click':
            input_count[0]+=1;flow.action_attempted=True
            assert request['scope']==scope and request['inspection_nonce']==module.FIRST_PLAN['nonces']['inspect']
            assert request['node_sha256']==tree['nodes'][0]['node_sha256']
            if fail=='click':raise original_failure
        if nonce==module.FIRST_PLAN['nonces']['after'] and fail=='after_state':raise original_failure
        helper={'protocol':qa.PROTOCOL,'op':op,'nonce':nonce,'self_uid':session.uid,
            'ui_automation_connected':op!='state','restoration':{'service_info_verified':True}}
        if op=='state':
            helper['state']=copy.deepcopy(state)
            if nonce==module.FIRST_PLAN['nonces']['after'] and fail=='restoration':
                helper['state']['accessibility_enabled']=True
        else:
            helper['accessibility_state_before_connection']=copy.deepcopy(state)
            if op=='inspect':helper['inspection']=copy.deepcopy(tree)
            elif op=='click':helper['action_window']=copy.deepcopy(tree['window'])
        return {'helper':helper,'wire_sha256':qa.sha(qa.canonical(helper)),
            'actual_command_returncode':0,'actual_instrumentation_finish_code':-1,
            'held_transport_returned_after_post_guard':True}
    session.instrument=instrument
    oldtime=module.time
    module.time=types.SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    error=None;result=None
    try:result=module.run(session,copy.deepcopy(base.PLAN))
    except BaseException as caught:error=caught
    finally:module.time=oldtime
    assert flow._private_backend_transport is False
    assert input_count[0]<=1 and calls.count(('state',module.FIRST_PLAN['nonces']['after']))==1
    observed=getattr(session,'sequence_observation',{})
    return types.SimpleNamespace(result=result,error=error,observed=observed,calls=calls,reads=reads,
        input_count=input_count[0],failure=original_failure,fg_calls=fg_calls[0],session=session)

def original_guard_proof():
    paths={
        'qa_adapter':(ROOT/'owned-bili-qa-r6-reveal-01/source/qa_adapter.py','1e939fb27aa4eaa9bb2fd79d7022ff4f48011fdf8824b0e7645bbc6f3308e1c8'),
        'qa_contract':(ROOT/'owned-bili-qa-r6-reveal-01/source/qa_contract.py','871c784812063739a6ab976784fb38243af52266b0d9a95aa1244779ccd2c005'),
        'backend':(ROOT/'android-bili-r3-video-foreground-reference-01/android_backend.py','088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae'),
        'recorder':(ROOT/'android-qa-install-state-01/review-inputs/recorder.py','5f25f22db55ba94e6ac895c2ce274b6959a274b64c9aa82bbc30d8c3c860f511')}
    for path,pin in paths.values():assert hashlib.sha256(path.read_bytes()).hexdigest()==pin
    original=ast.parse(paths['qa_adapter'][0].read_text())
    cls=next(n for n in original.body if isinstance(n,ast.ClassDef) and n.name=='Session')
    function=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='sequence')
    localtree=ast.parse((HERE/'post_foreground.py').read_text())
    local=copy.deepcopy(next(n for n in localtree.body if isinstance(n,ast.FunctionDef) and n.name=='owned_sequence'))
    changes=[]
    for n in ast.walk(local):
        if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='observe_post_ack':
            assert len(n.targets)==1 and ast.unparse(n.targets[0])=="result['foreground_after']"
            assert [ast.unparse(v) for v in n.value.args]==['self','plan','result']
            changes.append(n)
    assert len(changes)==1
    changes[0].value=ast.parse('self.foreground()',mode='eval').body
    local.name='sequence'
    assert ast.dump(local,include_attributes=False)==ast.dump(function,include_attributes=False)
    backend=ast.parse(paths['backend'][0].read_text())
    foreground=next(n for n in backend.body if isinstance(n,ast.FunctionDef) and n.name=='foreground')
    pattern=next(n.args[0].value for n in ast.walk(foreground) if isinstance(n,ast.Call) and ast.unparse(n.func)=='re.search')
    assert pattern==module.FOCUS_PATTERN
    forbidden=[]
    for n in ast.walk(localtree):
        if isinstance(n,(ast.Assign,ast.AugAssign,ast.AnnAssign)):
            targets=n.targets if isinstance(n,ast.Assign) else [n.target]
            for target in targets:
                if isinstance(target,ast.Attribute):
                    assert ast.unparse(target) in ('f._private_backend_transport','self.sequence_observation','primary.details'),ast.unparse(target)
    return {'original_files':{name:{'path':str(path),'sha256':pin} for name,(path,pin) in paths.items()},
        'copied_sequence_AST_identical_except_one_post_foreground_call':True,
        'sequence_AST_sha256':hashlib.sha256(ast.dump(function,include_attributes=False).encode()).hexdigest(),
        'original_focus_regex_identical':True,'shared_objects_or_methods_monkeypatched':False}

def main():
    rows=[]
    def passed(name):rows.append({'case':name,'passed':True})
    module.validate(adapter,qa,base.PLAN)
    proof=original_guard_proof();passed('original_full_sequence_guards_and_finally_AST_preserved_with_one_explicit_call_change')
    for name,samples,count in [('immediate_expected',[GOOD],1),('explicit_null_then_expected',[ZERO,GOOD],2),
        ('two_nulls_then_expected',[ZERO,ZERO,GOOD],3),('duplicate_same_focus_preserves_original_unique_set',[GOOD+GOOD],1)]:
        x=exercise(samples)
        assert x.error is None,(name,str(x.error))
        r=x.result['first_search_post_ack_foreground']
        assert r['qualified'] and len(x.reads)==count and x.input_count==1 and x.fg_calls==2
        assert r['waiting_authorized_by_first_explicit_zero'] is (count>1)
        assert x.result['foreground_after']['activity']==module.EXPECTED_ACTIVITY
        assert x.result['restoration_qualified'] and x.result['after_state_completed']
        assert all(v['original_Main_and_owned_task_guards_passed'] for v in r['observations'])
        assert all(v['stdout_sha256']==hashlib.sha256(samples[min(i,len(samples)-1)]).hexdigest() for i,v in enumerate(r['observations']))
        passed(name)
    categories=[('multiple_then_zero',MULTI,'multiple_distinct_focuses'),
        ('foreign_then_zero',FOREIGN,'foreign_focus'),('foreign_user',focus(user='10'),'foreign_focus'),
        ('wrong_bili_activity',focus(activity='com.bilibili.MainActivityV2'),'unexpected_bili_activity'),
        ('no_focus_field',b'No matching field\n','malformed_or_absent_focus_record'),
        ('malformed_focus',b'mCurrentFocus=unknown\n','malformed_or_absent_focus_record'),
        ('mixed_null_and_focus',ZERO+GOOD,'mixed_null_and_focus'),
        ('valid_plus_malformed',GOOD+b'mCurrentFocus=broken\n','malformed_or_absent_focus_record')]
    for name,raw,category in categories:
        x=exercise([raw,ZERO,GOOD]);r=x.observed['first_search_post_ack_foreground']
        assert str(x.error)=='POST_ACK_FOCUS_REJECTED:'+category,(name,str(x.error))
        assert len(x.reads)==1 and r['first_sample_classification']==category and not r['qualified']
        assert not r['waiting_authorized_by_first_explicit_zero'] and x.input_count==1
        assert x.observed['error']['phase']=='post_foreground' and x.observed['after_state_completed']
        passed(name+'_cannot_be_reclassified_by_later_zero')
    for raw,category in [(MULTI,'multiple_distinct_focuses'),(FOREIGN,'foreign_focus')]:
        x=exercise([ZERO,raw,GOOD]);r=x.observed['first_search_post_ack_foreground']
        assert len(x.reads)==2 and str(x.error)=='POST_ACK_FOCUS_REJECTED:'+category and not r['qualified']
        passed('zero_then_'+category+'_stops_no_third_read')
    x=exercise([ZERO]);r=x.observed['first_search_post_ack_foreground']
    assert str(x.error)=='POST_ACK_SEARCH_FOCUS_NOT_READY_IN_BOUNDED_READS' and len(x.reads)==3 and not r['qualified']
    passed('explicit_null_exhausts_exact_three_samples_no_input_replay')
    failure=RuntimeError('SYNTHETIC_HELD_COMMAND_FAILURE')
    for samples,count in [([failure,ZERO,GOOD],1),([ZERO,failure,GOOD],2)]:
        x=exercise(samples);assert x.error is failure and len(x.reads)==count and x.input_count==1
        assert x.observed['after_state_completed'] and not x.observed['first_search_post_ack_foreground']['qualified']
        passed('failed_command_'+str(count)+'_stops_without_later_reclassification')
    for fail in ('click','after_state','restoration'):
        x=exercise([ZERO,GOOD],fail=fail)
        assert not x.reads and 'first_search_post_ack_foreground' not in x.observed
        assert x.fg_calls==3 and any(v['phase']=='post_foreground' and v['message']=='FOREGROUND_UNVERIFIED' for v in x.observed['secondary_errors'])
        if fail!='restoration':assert x.error is x.failure
        assert x.observed['after_state_attempted'] and x.input_count==1
        passed(fail+'_failure_keeps_original_unclassified_foreground_error_no_wait')
    x=exercise([GOOD],task_changed=2)
    assert str(x.error)=='POST_ACK_OWNED_TASK_CHANGED' and not x.reads
    passed('changed_owned_task_before_first_read_fails')
    x=exercise([GOOD],task_changed=3)
    assert str(x.error)=='POST_ACK_OWNED_TASK_CHANGED' and len(x.reads)==1
    assert not x.observed['first_search_post_ack_foreground']['qualified']
    passed('changed_owned_task_after_expected_read_fails')
    x=exercise([GOOD],late=0)
    assert str(x.error)=='POST_ACK_FOCUS_DEADLINE' and len(x.reads)==1 and x.observed['after_state_completed']
    assert not x.observed['first_search_post_ack_foreground']['qualified']
    passed('late_expected_first_sample_does_not_qualify')
    x=exercise([ZERO,GOOD],late=1)
    assert str(x.error)=='POST_ACK_FOCUS_DEADLINE' and len(x.reads)==2
    passed('late_expected_after_zero_does_not_qualify')
    x=exercise([GOOD],fail='Main_guard')
    assert x.error is x.failure and not x.reads
    passed('Main_guard_failure_prevents_first_read')
    x=exercise([GOOD],late_install=True)
    assert str(x.error)=='OWNED_HELPER_INSTALLATION_CHANGED' and x.observed['error']['phase']=='post_installed_identity'
    passed('original_final_install_identity_guard_still_fails')
    x=exercise([GOOD],bad_tree=True)
    assert str(x.error)=='COMPLETE_INSPECTION_REQUIRED' and not x.reads and x.input_count==0
    passed('original_complete_tree_guard_stops_before_input')
    x=exercise([GOOD],changed_pre_focus=True)
    assert str(x.error)=='ORIGINAL_ACTIVITY_OR_WINDOW_CHANGED_AFTER_INSPECT' and not x.reads and x.input_count==0
    passed('original_fresh_window_guard_stops_before_input')
    x=exercise([GOOD]);session=x.session
    try:module.run(session,copy.deepcopy(base.PLAN))
    except RuntimeError as error:assert str(error)=='FIRST_SEARCH_SEQUENCE_CANNOT_REPLAY'
    else:raise AssertionError('second sequence admitted')
    passed('used_first_plan_cannot_replay')
    raw=FOREIGN+b'PRIVATE SYNTHETIC TEXT MUST NOT APPEAR\n'
    x=exercise([raw]);safe=json.dumps(x.observed['first_search_post_ack_foreground'])
    assert 'PRIVATE SYNTHETIC' not in safe and 'org.synthetic.foreign' not in safe and 'PublicActivity' not in safe
    passed('foreign_raw_window_text_never_exported')
    print(json.dumps({'schema':1,'ok':True,'count':len(rows),'cases':rows,'guard_proof':proof,
        'real_Android_Hepta_or_UI_actions':0,'shared_recorder_backend_adapter_modified':False,
        'synthetic_public_input_seams_only':True,'old04_outcome_unknown_retained':True},sort_keys=True,indent=2))

if __name__=='__main__':main()
