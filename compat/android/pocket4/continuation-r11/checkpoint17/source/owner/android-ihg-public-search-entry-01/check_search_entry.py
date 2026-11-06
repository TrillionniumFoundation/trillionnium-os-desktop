#!/usr/bin/env python3
"""Original Session flow with synthetic public nodes and explicit local I/O seams."""
from pathlib import Path
import ast,copy,hashlib,json,tempfile,types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

qa=load(ROOT/'owned-ihg-qa-r1-build01/source/qa_contract.py','original_ihg_contract')
adapter=load(ROOT/'owned-ihg-qa-r1-build01/source/qa_adapter.py','original_ihg_adapter')
public=load(HERE/'public_search.py','public_search_candidate')
context=load(HERE/'ihg_task_context.py','search_task_policy')
base=load(HERE/'owned_inspect.py','fresh_search_source')

def node(path,kind,label,clickable=False):
    return {'package':qa.PACKAGE,'resource_id':'','resource_id_truncated':False,'class':kind,'class_truncated':False,
        'path':path,'bounds':[0,0,100,100],'visible':True,'enabled':True,'password':False,'clickable':clickable,
        'selected':False,'editable':False,'supports_set_text':False,'child_count':0,
        'text':label,'text_sha256':qa.sha(label.encode()),'text_truncated':False,
        'content_desc':'','content_desc_sha256':qa.sha(b''),'content_desc_truncated':False}

def refresh(tree):
    for n in tree['nodes']:
        n.pop('node_sha256',None);n['node_sha256']=qa.sha(qa.canonical(n))
    tree['tree_sha256']=qa.sha(qa.canonical(tree['nodes']))
    tree['window_sha256']=qa.sha(qa.canonical(tree['window']))
    return tree

def fixture(mode='ready',selected=False):
    frame=node('0/0','android.widget.FrameLayout','',True)
    frame.update(content_desc='Search',content_desc_sha256=qa.sha(b'Search'))
    text=node('0/1','android.widget.TextView','Search')
    root=node('0','android.view.ViewGroup','SYNTHETIC PRIVATE NONPUBLIC LABEL')
    root['child_count']=2
    tree={'complete':True,'traversal':'visible-non-password-subtrees','nodes':[root,frame,text],
        'window':{'bounds':[0,0,1000,1500],'focused':True,'package':qa.PACKAGE,'display':0,'type':1},
        'connection_scoped_window_id':42,'observed_elapsed_ms':100}
    frame['selected']=text['selected']=selected
    if mode=='duplicate':text['clickable']=True
    if mode=='none':frame['clickable']=False
    if mode=='already_selected':frame['selected']=True
    if mode=='partial':tree['complete']=False
    if mode=='foreign_window':tree['window']['package']='org.synthetic.foreign'
    if mode=='wrong_display':tree['window']['display']=1
    if mode=='editable':frame['editable']=True
    if mode=='truncated':frame['content_desc_truncated']=True
    if mode=='unknown_class':frame['class']='org.synthetic.CustomClickable'
    if mode=='missing_selected':del frame['selected']
    if mode=='parent_only':
        frame['clickable']=False;root['clickable']=True
    if mode=='different_case':
        frame['content_desc']=' SEARCH ';frame['content_desc_sha256']=qa.sha(b' SEARCH ')
        text['text']='search';text['text_sha256']=qa.sha(b'search')
    if mode=='swapped_public_fields':
        frame['text']='Search';frame['text_sha256']=qa.sha(b'Search')
        frame['content_desc']='';frame['content_desc_sha256']=qa.sha(b'')
        text['text']='';text['text_sha256']=qa.sha(b'')
        text['content_desc']='Search';text['content_desc_sha256']=qa.sha(b'Search')
    refresh(tree)
    if mode=='bad_label_digest':
        frame['content_desc_sha256']='f'*64;refresh(tree)
    if mode=='bad_tree_digest':tree['tree_sha256']='f'*64
    return tree

def window_observation():
    window={'display':0,'id':42,'type':1,'focused':True,'active':True,'accessibility_focused':False,'layer':0}
    census={'sample':1,'event_serial':0,'elapsed_ms':1,'displays':[0],'windows':[window]}
    return {'requested_display':0,'selection':'exact-display-0-focused-application','wait_budget_ms':2000,
        'recheck_max_ms':100,'ready':True,'selected_display':0,'selected_window_id':42,
        'samples':1,'waited_ms':1,'sample_timings':[{'sample':1,'event_serial':0,'elapsed_ms':1,'cache_cleared':True}],
        'first':copy.deepcopy(census),'last':copy.deepcopy(census),'cache_api':'android.app.UiAutomation.clearCache()',
        'cache_policy':'require_public_own_connection_clear_before_each_query','cache_runtime_sdk':37,
        'cache_attempts':1,'cache_clears':1,'cache_last_result':True,'cache_last_exception':None}

def tree_counts(tree,operation):
    purposes=['inspection'] if operation=='inspect' else ['action_target','action_final_window']
    return [{'capture':i+1,'purpose':purpose,'node_limit':512,'depth_limit':32,'child_limit':64,
        'json_byte_limit':458752,'attempted_nodes':len(tree['nodes']),'emitted_nodes':len(tree['nodes']),
        'max_attempted_depth':1,'max_observed_children':2,'serialized_bytes':len(qa.canonical(tree)),
        'complete':True,'began_elapsed_ms':100,'last_elapsed_ms':101} for i,purpose in enumerate(purposes)]

def exercise(mode='ready',post_selected=True,fail=None,changed_post_task=False,changed_fresh_window=False):
    click,post=copy.deepcopy(base.PLAN),copy.deepcopy(base.POST_PLAN)
    calls=[];fg_count=[0];task_count=[0];failure=RuntimeError('SYNTHETIC_HELPER_'+str(fail))
    state={'accessibility_enabled':False,'touch_exploration_enabled':False,
        'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')}
    scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.PACKAGE+'/.activity.MainActivity',
        'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH}
    owned={'task':4321,'package':qa.PACKAGE,'prelaunch_absent':True,'cleanup_allowed':True}
    with tempfile.TemporaryDirectory(prefix='ihg-search-pure-') as directory:
        step=Path(directory)
        policy=context.Policy('inspect',qa,['synthetic-resolve'],{'click':click,'post':post},step,
            lambda path,maximum:path.read_bytes(),lambda:copy.deepcopy(owned))
        flow=types.SimpleNamespace(contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),
            _private_backend_transport=False,action_attempted=False,command_index=0,step=step,policy=policy)
        def admit(argv,timeout,mutation=False,private=False):
            policy.admit(argv,timeout,mutation,private)
            if not private:flow.command_index+=1
            flow.action_attempted|=mutation
        class SyntheticIO(adapter.Session):
            def installed(self):
                admit(context.OWN_UID,8);admit(context.OWN_PATH,8)
                return copy.deepcopy(base.INSTALLED)
            def task(self):
                admit(context.STACKS,20);task_count[0]+=1
                return dict(owned,task=4322) if changed_post_task and task_count[0]>2 else copy.deepcopy(owned)
            def foreground(self):
                admit(context.FOREGROUND,15,private=True);fg_count[0]+=1
                return dict(scope,window_token='ab13') if changed_fresh_window and fg_count[0]==2 else copy.deepcopy(scope)
            def instrument(self,request):
                qa.validate_request(request);nonce,op=request['nonce'],request['op']
                assert nonce not in self.nonces;self.nonces.add(nonce)
                (step/(nonce+'.request.json')).write_text(json.dumps(request))
                admit(qa.instrumentation_argv(request),20,mutation=op=='click')
                calls.append((op,nonce))
                if (fail=='click' and op=='click') or (fail=='after_state' and nonce==click['nonces']['after']) or (fail=='post_inspect' and nonce==post['nonces']['inspect']):raise failure
                helper={'protocol':qa.PROTOCOL,'op':op,'nonce':nonce,'self_uid':base.HELPER_UID,'ok':True,
                    'error':None,'secondary_errors':[],'ui_automation_connected':op!='state',
                    'restoration':{'service_info_verified':True}}
                if op=='state':helper['state']=copy.deepcopy(state)
                else:
                    helper['accessibility_state_before_connection']=copy.deepcopy(state)
                    tree=fixture(mode if nonce==click['nonces']['inspect'] else 'ready',
                                 selected=post_selected if nonce==post['nonces']['inspect'] else False)
                    helper['window_observation']=window_observation();helper['tree_observations']=tree_counts(tree,op)
                    if op=='inspect':helper['inspection']=tree
                    else:
                        helper.update(node_action='ACTION_CLICK',node_action_returned=True,action_attempted=True,
                            outcome_unknown=True,inspection_nonce=request['inspection_nonce'],
                            inspection_sha256=request['inspection_sha256'],target_node_sha256=request['node_sha256'],
                            action_window=tree['window'])
                value={'helper':helper,'wire_sha256':qa.sha(qa.canonical(helper)),
                    'held_transport_returned_after_post_guard':True,'recorder_command_result_sha256':'a'*64,
                    'actual_command_returncode':0,'actual_instrumentation_finish_code':-1}
                (step/(nonce+'.assessment.json')).write_text(json.dumps(value,sort_keys=True))
                return value
        seam=types.SimpleNamespace(Session=SyntheticIO,validate_plan=adapter.validate_plan)
        session=public.make_session(seam,flow,None,qa,{},base.HELPER_UID,click,post)
        result={'ok':False,'error':None,'secondary_errors':[]}
        def remember(phase,error):
            row={'phase':phase,'type':type(error).__name__,'message':str(error)}
            if result['error'] is None:result['error']=row
            else:result['secondary_errors'].append(row)
        for argv in (context.LIST,context.PATHS):admit(argv,15)
        session.installed()
        public.run_sequences(qa,session,base.INSTALLED,click,post,result,
            lambda seq,plan:base.assessment_summary(types.SimpleNamespace(qa=qa),step,seq,plan),remember)
        session.installed()
        for argv in (context.LIST,context.PATHS):admit(argv,15)
        assert sum(op=='click' for op,nonce in calls)<=1
        assert calls[-1]==('state',post['nonces']['after'])
        assert ('state',click['nonces']['after']) in calls
        safe=json.dumps(result);assert 'SYNTHETIC PRIVATE' not in safe
        return result,calls,policy.counts,flow.command_index,session,failure

def main():
    cases=[]
    def passed(name):cases.append({'case':name,'passed':True})
    for name,pin in [('qa_contract.py','573fdcd691ed51b76f965151b74b38cfcbd12ed5aa972d668146ae136744d7e1'),
        ('qa_adapter.py','0918dca47db8451baf1cb74fc6c50934e7c87a97e25aff6cc7a568ac21a091f9')]:
        assert hashlib.sha256((ROOT/'owned-ihg-qa-r1-build01/source'/name).read_bytes()).hexdigest()==pin
    passed('original_IHG_R1_contract_and_adapter_bytes_unchanged')
    values=[base.NONCE,*base.PLAN['nonces'].values(),*base.POST_PLAN['nonces'].values()]
    assert len(values)==len(set(values))==8 and base.STATE_NONCE not in values
    old=json.loads((ROOT/'android-ihg-launch-inspect-01/INPUTS.json').read_bytes())
    assert not set(values)&{old['nonce'],*old['read_only_inspection_plan']['nonces'].values()}
    adapter.validate_plan(base.PLAN,qa);adapter.validate_plan(base.POST_PLAN,qa)
    passed('seven_new_helper_nonces_and_flow_disjoint_from_actual_retired_scope')
    for mode in ('ready','different_case','swapped_public_fields'):
        result,calls,counts,commands,session,_=exercise(mode)
        assert result['error'] is None,(mode,result['error'])
        assert result['public_search_entry_completed'] and result['public_search_entry']['public_search_entry_selection_verified']
        assert len(calls)==7 and sum(op=='click' for op,n in calls)==1
        assert counts=={'target_uid':2,'target_path':2,'helper_uid':6,'helper_path':6,'stacks':4,'foreground':6,'instrument':7,'click':1}
        assert commands==27
        assert result['sequence']['after_state_completed'] and result['post_sequence']['after_state_completed']
        assert result['sequence']['restoration_qualified'] and result['post_sequence']['restoration_qualified']
        assert result['public_search_entry']['business_success_verified'] is False
        passed(mode+'_uses_actual_exact_public_field_and_one_original_click_then_independent_read')
    for mode in ('duplicate','none','already_selected','partial','foreign_window','wrong_display','editable','truncated',
        'unknown_class','missing_selected','parent_only','bad_label_digest','bad_tree_digest'):
        result,calls,counts,commands,session,_=exercise(mode)
        assert result['error'] is not None and not any(op=='click' for op,n in calls),(mode,result)
        assert result['post_inspection_attempted'] and result['post_inspection_completed']
        assert not result.get('public_search_entry_completed')
        passed(mode+'_prevents_input_keeps_independent_post_read_and_after_states')
    for failure in ('click','after_state','post_inspect'):
        result,calls,counts,commands,session,error=exercise(fail=failure)
        assert result['error']['message']=='SYNTHETIC_HELPER_'+failure
        assert not result.get('public_search_entry_completed') and sum(op=='click' for op,n in calls)==1
        assert result['post_inspection_attempted']
        passed(failure+'_first_error_retained_no_replay_original_finally_attempted')
    result,calls,*_=exercise(post_selected=False)
    assert result['error']['message']=='PUBLIC_SEARCH_SELECTION_NOT_OBSERVED' and len(calls)==7
    passed('ACK_without_independent_selected_state_does_not_qualify')
    result,calls,*_=exercise(changed_post_task=True)
    assert result['error']['message']=='ACK_AND_INDEPENDENT_SAME_OWNED_TASK_READ_REQUIRED'
    passed('post_read_in_different_owned_task_rejected')
    result,calls,*_=exercise(changed_fresh_window=True)
    assert result['error']['message']=='ORIGINAL_ACTIVITY_OR_WINDOW_CHANGED_AFTER_INSPECT' and not any(op=='click' for op,n in calls)
    passed('original_fresh_window_guard_before_click_preserved')
    selector,target,safe=public.search_selector(qa,fixture())
    request={'protocol':qa.PROTOCOL,'nonce':base.PLAN['nonces']['action'],'op':'click',
        'scope':{'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.PACKAGE+'/.activity.MainActivity',
                 'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH},
        'inspection_nonce':base.PLAN['nonces']['inspect'],'inspection_sha256':'b'*64,**target}
    with tempfile.TemporaryDirectory(prefix='ihg-search-policy-') as directory:
        step=Path(directory)
        def policy():return context.Policy('inspect',qa,['resolve'],{'click':copy.deepcopy(base.PLAN),'post':copy.deepcopy(base.POST_PLAN)},
            step,lambda path,maximum:path.read_bytes(),lambda:{'task':4321})
        (step/(request['nonce']+'.request.json')).write_text(json.dumps(request))
        p=policy();argv=qa.instrumentation_argv(request);p.admit(argv,20,True,False)
        for name,call in [
            ('replayed_action_nonce',lambda:p.admit(argv,20,True,False)),
            ('click_without_mutation_flag',lambda:policy().admit(argv,20,False,False)),
            ('click_through_private_branch',lambda:policy().admit(argv,20,True,True)),
            ('arbitrary_input',lambda:policy().admit(['/system/bin/input','tap','1','2'],20,True,False)),
            ('public_raw_foreground',lambda:policy().admit(context.FOREGROUND,15,False,False))]:
            try:call()
            except RuntimeError:pass
            else:raise AssertionError(name+' admitted')
            passed(name+'_policy_denied')
        unknown=copy.deepcopy(request);unknown['nonce']='f'*32
        try:policy().admit(qa.instrumentation_argv(unknown),20,True,False)
        except RuntimeError:pass
        else:raise AssertionError('unknown nonce admitted')
        passed('unlisted_nonce_denied')
    # A failed held transport is permanently poisoned in the actual unchanged Flow.android.
    flow=object.__new__(context.Flow);flow.closed=False;flow.poisoned=False;flow._private_backend_transport=False
    flow.policy=types.SimpleNamespace(admit=lambda *args:None);attempts=[]
    def fail_transport(*args):attempts.append(args);raise RuntimeError('SYNTHETIC_HELD_TRANSPORT_FAILURE')
    flow.transport=fail_transport
    for i in range(2):
        try:flow.android(context.FOREGROUND,15)
        except RuntimeError as error:assert str(error)==('SYNTHETIC_HELD_TRANSPORT_FAILURE' if i==0 else 'POISONED_AMAZON_COMMAND_NOT_REPLAYABLE')
        else:raise AssertionError('failed transport continued')
    assert len(attempts)==1 and flow._android_mutation is False
    passed('actual_Flow_poison_after_failed_transport_blocks_further_command')
    # The owned hook must reject changed action binding before the original I/O seam.
    for field,bad in [('nonce','e'*32),('node_path','0/9'),('node_sha256','d'*64),
        ('inspection_nonce','c'*32),('inspection_sha256','f'*64),('scope',dict(request['scope'],window_token='ab99'))]:
        accesses=[]
        class ProbeBase:
            def __init__(self,*args):pass
            def instrument(self,value):
                accesses.append(value['op'])
                assert value['op']=='inspect','bad action reached I/O'
                return {'helper':{'inspection':fixture()},'wire_sha256':'b'*64}
        probe_adapter=types.SimpleNamespace(Session=ProbeBase,validate_plan=adapter.validate_plan)
        cp,pp=copy.deepcopy(base.PLAN),copy.deepcopy(base.POST_PLAN)
        session=public.make_session(probe_adapter,None,None,qa,{},base.HELPER_UID,cp,pp)
        session.instrument({'protocol':qa.PROTOCOL,'op':'inspect','nonce':cp['nonces']['inspect'],'scope':request['scope']})
        changed=copy.deepcopy(session._action_binding);changed[field]=bad
        try:session.instrument(changed)
        except RuntimeError as error:assert str(error)=='EXACT_FRESH_PUBLIC_SEARCH_NODE_REQUEST_REQUIRED'
        else:raise AssertionError(field+' action mutation admitted')
        assert accesses==['inspect'] and not session.action_request_admitted
        passed('changed_action_'+field+'_rejected_before_input_IO')
    print(json.dumps({'schema':1,'ok':True,'count':len(cases),'cases':cases,
        'original_Session_sequence_and_real_contract_summary_and_policy_executed':True,
        'explicit_synthetic_IO_seams_only':True,'device_calls':0,'historical_raw_UI_used':False,
        'whole_app_production_ready':False},sort_keys=True,indent=2))

if __name__=='__main__':main()
