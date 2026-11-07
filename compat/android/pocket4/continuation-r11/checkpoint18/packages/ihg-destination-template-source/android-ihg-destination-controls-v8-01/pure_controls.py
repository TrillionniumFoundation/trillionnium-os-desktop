"""Actual R1 Session/Policy with in-memory synthetic I/O; no Android or file writes."""
import ast,copy,hashlib,json,re,secrets,sys,types
from pathlib import PurePosixPath
raw=sys.stdin.buffer.read(131073)
assert len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=='49c64e23ac0707d06623d2c358d00b0c7cdf8010bb5bf5e68b9f8e123e7a21ed'
p=json.loads(raw)
assert p['schema']==1 and set(p)=={'schema','contract','adapter','public_destination','context','coordinator','stage','nonce_slots','nonce_exclusions'}
PINS={"contract":{"bytes":28150,"sha256":"573fdcd691ed51b76f965151b74b38cfcbd12ed5aa972d668146ae136744d7e1"},"adapter":{"bytes":20785,"sha256":"0918dca47db8451baf1cb74fc6c50934e7c87a97e25aff6cc7a568ac21a091f9"},"public_destination":{"bytes":16138,"sha256":"6b381a19706c2fb92f639d104a465eb1f474e690df43ce01e7df9bb0e40fa501"},"context":{"bytes":16243,"sha256":"2661114607c46ccad216d0e1abe37cb38171fec877bba6a70b3c91b7ea183468"},"coordinator":{"bytes":37490,"sha256":"722c26b20ffd684ac649583bfdf7afa26e04d624daa1dad145dbb2682f6e3faf"},"stage":{"bytes":4953,"sha256":"4a875fc2de2c89e039e6174768b0a3987338d4030aeb862fbebee2cd7a8dd11d"}}
for name,pin in PINS.items():
    data=p[name].encode();assert len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],name
    compile(p[name],'<compile-only-'+name+'>','exec')
slots=p['nonce_slots'];old=p['nonce_exclusions']
assert len(slots)==len(set(slots))==8 and len(old)==len(set(old))==10
assert slots==['IHG_DEST_NEW_NONCE_'+str(i).zfill(13) for i in range(8)]
assert all(re.fullmatch('[0-9a-f]{32}',v) for v in old)
synthetic={slot:format(i+1,'032x') for i,slot in enumerate(slots)}
assert not set(synthetic.values())&set(old)
def bound(text,mapping):
    for before,after in mapping.items():text=text.replace(before,after)
    return text
def module(text,name):
    # Remove only HERE.resolve(); all definitions stay exact in this isolated namespace.
    tree=ast.parse(text)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    m=types.ModuleType(name);m.__file__='/pure-control/'+name+'.py';m.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),m.__dict__)
    return m
qa=module(p['contract'],'ihg_actual_r1_contract')
adapter=module(p['adapter'],'ihg_actual_r1_adapter')
public=module(p['public_destination'],'owned_destination_gate')
context=module(p['context'],'ihg_actual_task_context')
base=module(bound(p['coordinator'],synthetic),'destination_coordinator')
assert qa.PROTOCOL=='pocket4-owned-ihg-qa-v1' and qa.SELF=='org.droidloom.qa.ihg.r1'
cases=[]
def passed(name):cases.append({'case':name,'passed':True})
passed('exact_original_contract_adapter_context_pins_and_all_candidate_compile')
adapter.validate_plan(base.PLAN,qa);adapter.validate_plan(base.POST_PLAN,qa)
assert len({base.NONCE,*base.PLAN['nonces'].values(),*base.POST_PLAN['nonces'].values()})==8
passed('eight_synthetic_nonces_only_and_one_click_one_independent_read_plan')

def node(path,kind,label='',clickable=False,resource='',box=None):
    n={'package':qa.PACKAGE,'path':path,'bounds':box or [0,0,500,100],
       'visible':True,'enabled':True,'password':False,'clickable':clickable,
       'selected':False,'focused':False,'checked':False,'editable':False,'supports_set_text':False,'child_count':0}
    for key,value in [('resource_id',resource),('class',kind),('text',label),('content_desc','')]:
        n[key]=value;n[key+'_truncated']=False;n[key+'_sha256']=qa.sha(value.encode())
    return n
def refresh(tree,children=True):
    if children:
        for n in tree['nodes']:
            n['child_count']=sum('/' in c['path'] and c['path'].rsplit('/',1)[0]==n['path'] for c in tree['nodes'])
    for n in tree['nodes']:
        n.pop('node_sha256',None);n['node_sha256']=qa.sha(qa.canonical(n))
    tree['tree_sha256']=qa.sha(qa.canonical(tree['nodes']))
    tree['window_sha256']=qa.sha(qa.canonical(tree['window']))
    return tree
def fixture(mode='ready'):
    distance=6 if mode=='ancestor_at_six' else 7 if mode=='ancestor_at_seven' else 2
    root=node('0','android.view.ViewGroup','SYNTHETIC_PRIVATE_NONPUBLIC_LABEL',box=[0,0,1000,1500])
    form=node('0/0','android.widget.LinearLayout',box=[0,0,1000,1500])
    nodes=[root,form];labels={};containers={}
    for index,label in enumerate(('Destination','Dates','Rooms')):
        path='0/0/'+str(index);box=[0,index*200,500,index*200+100]
        resource=qa.PACKAGE+':id/SYNTHETIC_PRIVATE_CONTAINER_'+str(index)
        container=node(path,'android.view.ViewGroup',clickable=True,resource=resource,box=box)
        containers[label]=container;nodes.append(container)
        for _ in range((distance if index==0 else 2)-1):
            path+='/0';nodes.append(node(path,'android.widget.LinearLayout',box=box))
        path+='/0';n=node(path,'android.widget.TextView',label,box=box)
        labels[label]=n;nodes.append(n)
    dest=containers['Destination'];label=labels['Destination']
    tree={'complete':True,'traversal':'visible-non-password-subtrees','nodes':nodes,
          'window':{'bounds':[0,0,1000,1500],'focused':True,'package':qa.PACKAGE,'display':0,'type':1},
          'connection_scoped_window_id':42,'observed_elapsed_ms':100}
    if mode=='different_case':label.update(text=' DESTINATION ',text_sha256=qa.sha(b' DESTINATION '))
    if mode=='description_label':label.update(text='',text_sha256=qa.sha(b''),content_desc='Destination',content_desc_sha256=qa.sha(b'Destination'))
    if mode=='missing_form':nodes.remove(labels['Rooms'])
    if mode=='duplicate_destination':nodes.append(node('0/9','android.widget.TextView','Destination',box=[0,700,500,800]))
    if mode=='duplicate_dates':nodes.append(node('0/9','android.widget.TextView','Dates',box=[0,700,500,800]))
    if mode=='disabled_label':label['enabled']=False
    if mode=='truncated_label':label['text_truncated']=True
    if mode=='bad_label_digest':label['text_sha256']='f'*64
    if mode=='wrong_label_class':label.update(**{'class':'android.widget.Button','class_sha256':qa.sha(b'android.widget.Button')})
    if mode=='editable_label':label['editable']=True
    if mode=='clickable_label':label['clickable']=True
    if mode=='zero_ancestor':dest['clickable']=False
    if mode=='two_ancestors':form['clickable']=True
    if mode=='broad_all_role_container':
        dest['clickable']=False;form.update(clickable=True,**{'class':'android.view.ViewGroup','class_sha256':qa.sha(b'android.view.ViewGroup')})
    if mode=='outside_window':dest['bounds']=[-1,0,500,100]
    if mode=='bad_target_geometry':dest['bounds']=[0,0,10,10]
    if mode=='bad_parent_geometry':
        next(n for n in nodes if n['path']==label['path'].rsplit('/',1)[0])['bounds']=[0,0,10,10]
    if mode=='missing_ancestor':
        nodes.remove(next(n for n in nodes if n['path']==label['path'].rsplit('/',1)[0]))
    if mode=='wrong_container_class':dest.update(**{'class':'android.widget.FrameLayout','class_sha256':qa.sha(b'android.widget.FrameLayout')})
    if mode=='editable_container':dest['editable']=True
    if mode=='foreign_resource':dest.update(resource_id='org.synthetic.foreign:id/control',resource_id_sha256=qa.sha(b'org.synthetic.foreign:id/control'))
    if mode=='empty_resource':dest.update(resource_id='',resource_id_sha256=qa.sha(b''))
    if mode=='truncated_resource':dest['resource_id_truncated']=True
    if mode=='bad_resource_digest':dest['resource_id_sha256']='f'*64
    if mode=='bad_class_digest':dest['class_sha256']='f'*64
    if mode=='duplicate_current_resource':
        nodes.append(node('0/9','android.view.ViewGroup',clickable=True,resource=dest['resource_id'],box=[0,700,500,800]))
    if mode=='partial':tree['complete']=False
    if mode=='foreign_window':tree['window']['package']='org.synthetic.foreign'
    if mode=='wrong_display':tree['window']['display']=1
    refresh(tree)
    if mode=='wrong_child_count':dest['child_count']+=1;refresh(tree,False)
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
        'max_attempted_depth':max(n['path'].count('/') for n in tree['nodes']),
        'max_observed_children':max(n['child_count'] for n in tree['nodes']),
        'serialized_bytes':len(qa.canonical(tree)),'complete':True,'began_elapsed_ms':100,
        'last_elapsed_ms':101} for i,purpose in enumerate(purposes)]
def exercise(mode='ready',fail=None,changed_post_task=False,changed_fresh_window=False):
    click,post=copy.deepcopy(base.PLAN),copy.deepcopy(base.POST_PLAN)
    calls=[];fg_count=[0];task_count=[0];failure=RuntimeError('SYNTHETIC_HELPER_'+str(fail))
    state={'accessibility_enabled':False,'touch_exploration_enabled':False,
        'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')}
    scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.PACKAGE+'/.activity.MainActivity',
        'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH}
    owned={'task':4321,'package':qa.PACKAGE,'prelaunch_absent':True,'cleanup_allowed':True}
    step=PurePosixPath('/synthetic/no-files-created');memory={}
    def read(path,maximum=1048576,*args,**kwargs):
        try:data=memory[str(path)]
        except KeyError:raise FileNotFoundError(str(path))
        assert len(data)<=maximum;return data
    policy=context.Policy('inspect',qa,['synthetic-resolve'],{'click':click,'post':post},step,read,lambda:copy.deepcopy(owned))
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
            memory[str(step/(nonce+'.request.json'))]=json.dumps(request).encode()
            admit(qa.instrumentation_argv(request),20,mutation=op=='click');calls.append((op,nonce))
            if (fail=='click' and op=='click') or (fail=='after_state' and nonce==click['nonces']['after']) or (fail=='post_inspect' and nonce==post['nonces']['inspect']):raise failure
            helper={'protocol':qa.PROTOCOL,'op':op,'nonce':nonce,'self_uid':base.HELPER_UID,'ok':True,
                'error':None,'secondary_errors':[],'ui_automation_connected':op!='state',
                'restoration':{'service_info_verified':True}}
            if op=='state':helper['state']=copy.deepcopy(state)
            else:
                helper['accessibility_state_before_connection']=copy.deepcopy(state)
                tree=fixture(mode if nonce in (click['nonces']['inspect'],click['nonces']['action']) else 'ready')
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
            memory[str(step/(nonce+'.assessment.json'))]=json.dumps(value,sort_keys=True).encode()
            return value
    seam=types.SimpleNamespace(Session=SyntheticIO,validate_plan=adapter.validate_plan)
    session=public.make_session(seam,flow,None,qa,{},base.HELPER_UID,click,post)
    result={'ok':False,'error':None,'secondary_errors':[]}
    def remember(phase,error):
        row={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if result['error'] is None:result['error']=row
        else:result['secondary_errors'].append(row)
    original_read=base.read;base.read=read
    try:
        for argv in (context.LIST,context.PATHS):admit(argv,15)
        session.installed()
        public.run_sequences(qa,session,base.INSTALLED,click,post,result,
            lambda seq,plan:base.assessment_summary(types.SimpleNamespace(qa=qa),step,seq,plan),remember)
        session.installed()
        for argv in (context.LIST,context.PATHS):admit(argv,15)
    finally:base.read=original_read
    assert sum(op=='click' for op,nonce in calls)<=1
    assert calls[-1]==('state',post['nonces']['after'])
    assert ('state',click['nonces']['after']) in calls
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(result)
    return result,calls,policy.counts,flow.command_index,session,failure

for mode in ('ready','different_case','description_label','ancestor_at_six'):
    result,calls,counts,commands,session,_=exercise(mode)
    assert result['error'] is None,(mode,result['error'])
    assert result['destination_click_and_observation_completed'] is True
    assert result['public_destination_observation']['current_public_destination_click_and_independent_read_verified'] is True
    assert result['public_destination_observation']['destination_input_semantics_verified'] is False
    assert result['public_destination_observation']['business_success_verified'] is False
    assert len(calls)==7 and sum(op=='click' for op,n in calls)==1
    assert counts=={'target_uid':2,'target_path':2,'helper_uid':6,'helper_path':6,'stacks':4,'foreground':6,'instrument':7,'click':1}
    assert commands==27 and result['sequence']['restoration_qualified'] and result['post_sequence']['restoration_qualified']
    passed(mode+'_one_current_ancestor_click_and_independent_read')
negative_modes=('missing_form','duplicate_destination','duplicate_dates','disabled_label','truncated_label',
 'bad_label_digest','wrong_label_class','editable_label','clickable_label','zero_ancestor','two_ancestors',
 'broad_all_role_container','ancestor_at_seven','outside_window','bad_target_geometry','bad_parent_geometry',
 'missing_ancestor','wrong_container_class','editable_container','foreign_resource','empty_resource',
 'truncated_resource','bad_resource_digest','bad_class_digest','duplicate_current_resource','partial',
 'foreign_window','wrong_display','wrong_child_count','bad_tree_digest')
for mode in negative_modes:
    result,calls,counts,commands,session,_=exercise(mode)
    assert result['error'] is not None and not any(op=='click' for op,n in calls),(mode,result)
    assert result['post_inspection_attempted'] and result['post_inspection_completed']
    assert not result.get('destination_click_and_observation_completed')
    passed(mode+'_no_input_with_original_after_states_and_independent_read')
for failure in ('click','after_state','post_inspect'):
    result,calls,counts,commands,session,error=exercise(fail=failure)
    assert result['error']['message']=='SYNTHETIC_HELPER_'+failure
    assert not result.get('destination_click_and_observation_completed') and sum(op=='click' for op,n in calls)==1
    assert result['post_inspection_attempted']
    passed(failure+'_first_error_preserved_no_replay')
result,calls,*_=exercise(changed_post_task=True)
assert result['error']['message']=='ACK_AND_INDEPENDENT_SAME_OWNED_TASK_READ_REQUIRED'
passed('independent_post_in_different_owned_task_rejected')
result,calls,*_=exercise(changed_fresh_window=True)
assert result['error']['message']=='ORIGINAL_ACTIVITY_OR_WINDOW_CHANGED_AFTER_INSPECT' and not any(op=='click' for op,n in calls)
passed('original_before_action_foreground_guard_unchanged')
result,calls,_,_,session,_=exercise()
before=len(calls)
try:session.instrument(copy.deepcopy(session._action_binding))
except RuntimeError as error:assert str(error)=='ONE_FRESH_PUBLIC_DESTINATION_REQUEST_REQUIRED'
else:raise AssertionError('action replay admitted')
assert len(calls)==before
passed('second_action_rejected_before_synthetic_IO')

scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.PACKAGE+'/.activity.MainActivity',
       'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH}
for field,bad in [('nonce','e'*32),('node_path','0/9'),('node_sha256','d'*64),
 ('inspection_nonce','c'*32),('inspection_sha256','f'*64),('scope',dict(scope,window_token='ab99'))]:
    accesses=[]
    class ProbeBase:
        def __init__(self,*args):pass
        def instrument(self,value):
            accesses.append(value['op']);assert value['op']=='inspect','invalid action reached I/O'
            return {'helper':{'inspection':fixture()},'wire_sha256':'b'*64}
    probe=types.SimpleNamespace(Session=ProbeBase,validate_plan=adapter.validate_plan)
    cp,pp=copy.deepcopy(base.PLAN),copy.deepcopy(base.POST_PLAN)
    session=public.make_session(probe,None,None,qa,{},base.HELPER_UID,cp,pp)
    session.instrument({'protocol':qa.PROTOCOL,'op':'inspect','nonce':cp['nonces']['inspect'],'scope':scope})
    request=copy.deepcopy(session._action_binding);request[field]=bad
    try:session.instrument(request)
    except RuntimeError as error:assert str(error)=='EXACT_FRESH_PUBLIC_DESTINATION_NODE_REQUEST_REQUIRED'
    else:raise AssertionError(field+' changed action admitted')
    assert accesses==['inspect'] and session.action_request_admitted is False
    passed('changed_action_'+field+'_denied_before_IO')
flow=object.__new__(context.Flow);flow.closed=False;flow.poisoned=False;flow._private_backend_transport=False
flow.policy=types.SimpleNamespace(admit=lambda *args:None);attempts=[]
def fail_transport(*args):attempts.append(args);raise RuntimeError('SYNTHETIC_HELD_TRANSPORT_FAILURE')
flow.transport=fail_transport
for index in range(2):
    try:flow.android(context.FOREGROUND,15)
    except RuntimeError as error:assert str(error)==('SYNTHETIC_HELD_TRANSPORT_FAILURE' if index==0 else 'POISONED_AMAZON_COMMAND_NOT_REPLAYABLE')
    else:raise AssertionError('failed transport reused')
assert len(attempts)==1 and flow._android_mutation is False
passed('original_transport_poison_still_stops_future_command')
bad_plan=copy.deepcopy(base.PLAN);bad_plan['operation']='set_text'
try:adapter.validate_plan(bad_plan,qa)
except RuntimeError as error:assert str(error)=='OWNED_PLAN_REQUIRED'
else:raise AssertionError('text plan enabled')
passed('original_R1_adapter_still_rejects_text')
request={'protocol':qa.PROTOCOL,'nonce':'e'*32,'op':'set_text'}
try:qa.validate_request(request)
except RuntimeError as error:assert str(error)=='IHG_READ_INSPECT_CLICK_ONLY'
else:raise AssertionError('text helper protocol enabled')
passed('original_R1_contract_still_rejects_text')
assert len(cases)==51 and len({x['case'] for x in cases})==51,('control inventory changed',len(cases))
pool=[]
for _ in range(128):
    value=secrets.token_hex(16)
    if value not in old and value not in pool:pool.append(value)
    if len(pool)==8:break
assert len(pool)==8,'bounded secure nonce pool exhausted'
actual_mapping=dict(zip(slots,pool))
bound_coordinator=bound(p['coordinator'],actual_mapping);bound_stage=bound(p['stage'],actual_mapping)
compile(bound_coordinator,'<actual-nonce-bound-coordinator>','exec')
compile(bound_stage,'<actual-nonce-bound-stage>','exec')
out={'schema':1,'ok':True,'state':'IHG_DESTINATION_PURE_CONTROLS_PASS','controls':cases,
 'control_count':len(cases),'source_pins':PINS,'control_stdin_sha256':hashlib.sha256(raw).hexdigest(),
 'bound_coordinator_sha256':hashlib.sha256(bound_coordinator.encode()).hexdigest(),
 'bound_stage_sha256':hashlib.sha256(bound_stage.encode()).hexdigest(),
 'original_Session_sequence_and_real_contract_summary_and_policy_executed':True,
 'all_candidate_python_compile':True,'synthetic_in_memory_IO_only':True,'real_Java_helper_executed':False,
 'file_writes':0,'Android_actions':0,'device_or_child_process_commands':0,'secrets_nonce_pool':pool,
 'nonce_pool_disjoint_prior_IHG_literals':not bool(set(pool)&set(old)),
 'actual_UI_readiness_verified':False,'runtime_flow_dispatched':False,'whole_app_production_ready':False}
encoded=json.dumps(out,sort_keys=True,separators=(',',':'))
assert len(encoded.encode())<=32768
print(encoded,flush=True)
