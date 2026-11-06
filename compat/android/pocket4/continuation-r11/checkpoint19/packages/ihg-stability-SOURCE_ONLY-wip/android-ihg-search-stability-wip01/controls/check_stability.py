"""Original IHG R1 Session/Policy and bounded full Search readiness with synthetic I/O only."""
import ast,copy,hashlib,json,re,secrets,sys,types
from pathlib import PurePosixPath
raw=sys.stdin.buffer.read(196609)
assert len(raw)<=196608 and hashlib.sha256(raw).hexdigest()=='da84720694a3ac2d8b9aced4adae34c7226c999ccf45321241b78d877087ac28'
p=json.loads(raw)
assert p['schema']==1 and set(p)=={'schema','contract','adapter','public_destination','context','coordinator','stage','nonce_slots','nonce_exclusions'}
TEMPLATE_PINS={"contract":{"bytes":28150,"sha256":"573fdcd691ed51b76f965151b74b38cfcbd12ed5aa972d668146ae136744d7e1"},"adapter":{"bytes":20785,"sha256":"0918dca47db8451baf1cb74fc6c50934e7c87a97e25aff6cc7a568ac21a091f9"},"public_destination":{"bytes":32045,"sha256":"d4d35f9729f4a4a8d0cef0f7ac4712630a00570e6e0d988713939aacd716e932"},"context":{"bytes":16822,"sha256":"6fb62d7e115d48652111fc85eed25be717a044338315a1d9014e10197a2bfed5"},"coordinator":{"bytes":41551,"sha256":"fcb2a890ebe823107b4cce80ac67a1f60141ece3357938d1c143520fb7b17762"},"stage":{"bytes":5038,"sha256":"ab02de5ed42986af37f2191ccdb05e46a6a1da494d9dc0af89bd6708db16c4d5"}}
for name,pin in TEMPLATE_PINS.items():
    data=p[name].encode();assert len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],name
    compile(p[name],'<compile-only-template-'+name+'>','exec')
slots=p['nonce_slots'];old=p['nonce_exclusions']
assert len(slots)==len(set(slots))==36 and all(isinstance(v,str) and len(v)==32 for v in slots)
assert len(old)==len(set(old))==30 and all(re.fullmatch('[0-9a-f]{32}',v) for v in old)
pool=[]
for _ in range(1024):
    value=secrets.token_hex(16)
    if value not in old and value not in pool:pool.append(value)
    if len(pool)==36:break
assert len(pool)==len(set(pool))==36 and not set(pool)&set(old)
BOUND_PINS={}
for name in TEMPLATE_PINS:
    value=p[name]
    for before,after in zip(slots,pool):value=value.replace(before,after)
    assert not any(slot in value for slot in slots)
    p[name]=value
    data=value.encode();BOUND_PINS[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    compile(value,'<compile-only-bound-'+name+'>','exec')
def module(text,name):
    tree=ast.parse(text)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    m=types.ModuleType(name);m.__file__='/pure-control/'+name+'.py';m.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),m.__dict__)
    return m
qa=module(p['contract'],'ihg_actual_r1_contract')
adapter=module(p['adapter'],'ihg_actual_r1_adapter')
public=module(p['public_destination'],'bounded_search_readiness_and_destination_gate')
context=module(p['context'],'ihg_actual_task_context')
base=module(p['coordinator'],'search_readiness_destination_coordinator')
assert qa.PROTOCOL=='pocket4-owned-ihg-qa-v1' and qa.SELF=='org.droidloom.qa.ihg.r1'
cases=[]
def passed(name):cases.append({'case':name,'passed':True})
passed('exact_original_contract_adapter_pins_and_all_template_and_bound_compile')
for plan in (base.SEARCH_PLAN,base.PLAN,base.POST_PLAN,*base.SEARCH_READINESS_PLANS):adapter.validate_plan(plan,qa)
assert [base.NONCE,*[base.SEARCH_PLAN['nonces'][k] for k in ('before','inspect','action','after')],
        *[base.PLAN['nonces'][k] for k in ('before','inspect','action','after')],
        *[base.POST_PLAN['nonces'][k] for k in ('before','inspect','after')],
        *[plan['nonces'][k] for plan in base.SEARCH_READINESS_PLANS for k in ('before','inspect','after')]]==pool
passed('thirty_six_secrets_nonces_ordered_and_disjoint_for_fresh_bounded_flow')

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

def with_search(tree,selected):
    tree['nodes'].extend([
        node('0/1','android.widget.LinearLayout',box=[0,1200,1000,1400]),
        node('0/1/0','android.widget.FrameLayout','Search',True,box=[0,1200,500,1400]),
        node('0/1/1','android.widget.TextView','Search',False,box=[500,1200,1000,1400])])
    for n in tree['nodes']:
        if n['path'] in ('0/1/0','0/1/1'):n['selected']=selected
    return refresh(tree)

def search_fixture(mode='ready'):
    tree={'complete':True,'traversal':'visible-non-password-subtrees',
        'nodes':[node('0','android.view.ViewGroup','SYNTHETIC_PRIVATE_NONPUBLIC_LABEL',box=[0,0,1000,1500])],
        'window':{'bounds':[0,0,1000,1500],'focused':True,'package':qa.PACKAGE,'display':0,'type':1},
        'connection_scoped_window_id':42,'observed_elapsed_ms':100}
    tree=with_search(tree,mode=='already_selected')
    if mode=='missing_search':
        for n in tree['nodes']:
            if n['text']=='Search':n['text']='SYNTHETIC_PRIVATE_UNMATCHED';n['text_sha256']=qa.sha(n['text'].encode())
        refresh(tree)
    return tree

def destination_fixture(mode='ready',selected=True):
    tree=fixture(mode)
    # Recompute the legitimate added subtree, then restore deliberately invalid
    # source fixtures so added Search metadata cannot heal a negative control.
    original_tree_digest=tree.get('tree_sha256')
    tree=with_search(tree,selected)
    if mode=='wrong_child_count':
        next(n for n in tree['nodes'] if n['path']=='0/0/0')['child_count']+=1;refresh(tree,False)
    if mode=='bad_tree_digest':tree['tree_sha256']=original_tree_digest
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

def exercise(mode='ready',failures=(),search_mode='ready',changed_post_task=False,
             changed_destination_task=False,changed_window_phase=None,
             readiness_keys=None,readiness_step_ms=2100,readiness_fault=None,
             changed_after_readiness=False):
    search,click,post=(copy.deepcopy(plan) for plan in (base.SEARCH_PLAN,base.PLAN,base.POST_PLAN))
    readiness=copy.deepcopy(base.SEARCH_READINESS_PLANS)
    readiness_keys=list(readiness_keys or ['A']*8)
    assert len(readiness_keys)==8
    failures=set(failures);calls=[];fake_clock=[0.0];ready_started=[];latest_key=['A']
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
    policy=context.Policy('inspect',qa,['synthetic-resolve'],
        {'search':search,'destination':click,'post':post,'readiness':readiness},step,read,lambda:copy.deepcopy(owned))
    flow=types.SimpleNamespace(contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),
        _private_backend_transport=False,action_attempted=False,command_index=0,step=step,policy=policy)
    def admit(argv,timeout,mutation=False,private=False):
        policy.admit(argv,timeout,mutation,private)
        if not private:flow.command_index+=1
        flow.action_attempted|=mutation
    def current_search_tree(key):
        tree=search_fixture(search_mode)
        root=tree['nodes'][0];root['text']='SYNTHETIC_PRIVATE_READY_'+key
        root['text_sha256']=qa.sha(root['text'].encode())
        return refresh(tree)
    class SyntheticIO(adapter.Session):
        def sequence(self,plan):
            self.synthetic_phase=('search' if plan['nonces']==search['nonces'] else
                'destination' if plan['nonces']==click['nonces'] else
                'post' if plan['nonces']==post['nonces'] else 'readiness')
            self.synthetic_fg_calls=0
            if self.synthetic_phase=='readiness':
                self.synthetic_ready_index=next(index for index,p in enumerate(readiness) if p['nonces']==plan['nonces'])
                ready_started.append(self.synthetic_ready_index)
            return super().sequence(plan)
        def installed(self):
            admit(context.OWN_UID,8);admit(context.OWN_PATH,8)
            return copy.deepcopy(base.INSTALLED)
        def task(self):
            admit(context.STACKS,20)
            phase=getattr(self,'synthetic_phase',None)
            if changed_destination_task and phase=='destination':return dict(owned,task=4322)
            if changed_post_task and phase=='post':return dict(owned,task=4322)
            if phase=='readiness' and readiness_fault=='task_changed' and self.synthetic_ready_index==1:
                return dict(owned,task=4322)
            return copy.deepcopy(owned)
        def foreground(self):
            admit(context.FOREGROUND,15,private=True);self.synthetic_fg_calls+=1
            phase=self.synthetic_phase
            if phase==changed_window_phase and self.synthetic_fg_calls==2:
                return dict(scope,window_token='ab13')
            if phase=='readiness' and readiness_fault=='scope_changed' and self.synthetic_ready_index==1:
                return dict(scope,window_token='ab13')
            return copy.deepcopy(scope)
        def instrument(self,request):
            qa.validate_request(request);nonce,op=request['nonce'],request['op']
            assert nonce not in self.nonces;self.nonces.add(nonce)
            memory[str(step/(nonce+'.request.json'))]=json.dumps(request).encode()
            admit(qa.instrumentation_argv(request),20,mutation=op=='click');calls.append((op,nonce))
            phase=self.synthetic_phase
            plan=(readiness[self.synthetic_ready_index] if phase=='readiness' else
                  {'search':search,'destination':click,'post':post}[phase])
            fault=(phase+'_click' if op=='click' else phase+'_after_state' if nonce==plan['nonces']['after']
                   else phase+'_inspect' if op=='inspect' else None)
            if fault in failures:
                error=RuntimeError('SYNTHETIC_HELPER_'+fault)
                error.details={'action_attempted':op=='click','outcome_unknown':op=='click'}
                raise error
            if phase=='readiness' and ((readiness_fault=='failed_inspect' and op=='inspect') or
                    (readiness_fault=='failed_after' and nonce==plan['nonces']['after'])):
                raise RuntimeError('SYNTHETIC_READINESS_'+readiness_fault.upper())
            if phase=='search' and op=='click' and 'search_unknown' in failures:
                error=RuntimeError('SYNTHETIC_SEARCH_ACTION_OUTCOME_UNKNOWN')
                error.details={'action_attempted':True,'outcome_unknown':True};raise error
            helper={'protocol':qa.PROTOCOL,'op':op,'nonce':nonce,'self_uid':base.HELPER_UID,'ok':True,
                'error':None,'secondary_errors':[],'ui_automation_connected':op!='state',
                'restoration':{'service_info_verified':True}}
            if op=='state':
                helper['state']=copy.deepcopy(state)
                if ((phase=='search' and 'search_state_changed' in failures) or
                    (phase=='readiness' and readiness_fault=='after_state_changed')) and nonce==plan['nonces']['after']:
                    helper['state']['accessibility_enabled']=True
            else:
                helper['accessibility_state_before_connection']=copy.deepcopy(state)
                if phase=='readiness':
                    index=self.synthetic_ready_index;latest_key[0]=readiness_keys[index]
                    tree=current_search_tree(latest_key[0])
                    if readiness_fault=='partial':tree['complete']=False
                    if readiness_fault=='foreign_window':
                        tree['window']['package']='com.synthetic.foreign';refresh(tree)
                    if readiness_fault=='bad_tree_digest':tree['tree_sha256']='f'*64
                    fake_clock[0]=(index+1)*readiness_step_ms/1000
                    if readiness_fault=='deadline':fake_clock[0]=21
                elif phase=='search':
                    tree=current_search_tree('CHANGED' if changed_after_readiness else latest_key[0])
                elif phase=='destination':
                    tree=destination_fixture(mode,selected='search_not_selected' not in failures)
                else:tree=destination_fixture()
                helper['window_observation']=window_observation();helper['tree_observations']=tree_counts(tree,op)
                if phase=='readiness':
                    counter=helper['tree_observations'][0]
                    counter['began_elapsed_ms']=1000+self.synthetic_ready_index*readiness_step_ms
                    counter['last_elapsed_ms']=counter['began_elapsed_ms']+1
                    if readiness_fault=='capture_backwards' and self.synthetic_ready_index==1:
                        counter['began_elapsed_ms']=999;counter['last_elapsed_ms']=1000
                    if readiness_fault=='counter_incomplete':counter['complete']=False
                if op=='inspect':helper['inspection']=tree
                else:
                    helper.update(node_action='ACTION_CLICK',
                        node_action_returned=not(phase=='search' and 'search_ack_unqualified' in failures),
                        action_attempted=True,outcome_unknown=True,inspection_nonce=request['inspection_nonce'],
                        inspection_sha256=request['inspection_sha256'],target_node_sha256=request['node_sha256'],
                        action_window=tree['window'])
            value={'helper':helper,'wire_sha256':qa.sha(qa.canonical(helper)),
                'held_transport_returned_after_post_guard':True,'recorder_command_result_sha256':'a'*64,
                'actual_command_returncode':0,'actual_instrumentation_finish_code':-1}
            memory[str(step/(nonce+'.assessment.json'))]=json.dumps(value,sort_keys=True).encode()
            return value
    seam=types.SimpleNamespace(Session=SyntheticIO,validate_plan=adapter.validate_plan)
    session=public.make_session(seam,flow,None,qa,{},base.HELPER_UID,search,click,post,readiness)
    result={'ok':False,'error':None,'secondary_errors':[]}
    def remember(phase,error):
        row={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if result['error'] is None:result['error']=row
        else:result['secondary_errors'].append(row)
    original_read=base.read;original_time=public.time
    base.read=read;public.time=types.SimpleNamespace(monotonic=lambda:fake_clock[0])
    try:
        for argv in (context.LIST,context.PATHS):admit(argv,15)
        session.installed()
        public.run_sequences(qa,session,base.INSTALLED,search,click,post,readiness,result,
            lambda seq,plan:base.assessment_summary(types.SimpleNamespace(qa=qa),step,seq,plan),remember)
        session.installed()
        for argv in (context.LIST,context.PATHS):admit(argv,15)
    finally:base.read=original_read;public.time=original_time
    assert sum(op=='click' for op,nonce in calls)<=2
    assert calls[-1]==('state',post['nonces']['after'])
    if result.get('search_sequence_started'):assert ('state',search['nonces']['after']) in calls
    if result.get('click_sequence_started'):assert ('state',click['nonces']['after']) in calls
    for index in ready_started:assert ('state',readiness[index]['nonces']['after']) in calls
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(result)
    return result,calls,policy.counts,flow.command_index,session

for mode in ('ready','different_case','description_label','ancestor_at_six'):
    result,calls,counts,commands,session=exercise(mode)
    assert result['error'] is None,(mode,result['error'])
    assert result['explicit_search_then_destination_completed'] is True
    assert result['search_sequence_qualified'] is True and result['public_search_entry']['public_search_entry_selection_verified'] is True
    assert result['destination_click_and_observation_completed'] is True
    assert result['public_destination_observation']['destination_input_semantics_verified'] is False
    assert result['public_destination_observation']['business_success_verified'] is False
    assert len(calls)==20 and [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action'],base.PLAN['nonces']['action']]
    assert counts=={'target_uid':2,'target_path':2,'helper_uid':14,'helper_path':14,'stacks':12,'foreground':18,'instrument':20,'click':2}
    assert commands==64 and result['search_readiness_count']==3 and result['search_readiness_qualified'] is True and all(result[k]['restoration_qualified'] for k in ('search_sequence','sequence','post_sequence'))
    assert result['search_assessments']['action']['outcome_unknown'] is True
    assert result['assessments']['action']['outcome_unknown'] is True
    passed(mode+'_explicit_search_fresh_destination_and_independent_read')
negative_modes=('missing_form','duplicate_destination','duplicate_dates','disabled_label','truncated_label',
 'bad_label_digest','wrong_label_class','editable_label','clickable_label','zero_ancestor','two_ancestors',
 'broad_all_role_container','ancestor_at_seven','outside_window','bad_target_geometry','bad_parent_geometry',
 'missing_ancestor','wrong_container_class','editable_container','foreign_resource','empty_resource',
 'truncated_resource','bad_resource_digest','bad_class_digest','duplicate_current_resource','partial',
 'foreign_window','wrong_display','wrong_child_count','bad_tree_digest')
for mode in negative_modes:
    result,calls,counts,commands,session=exercise(mode)
    assert result['error'] is not None,(mode,result)
    assert [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action']]
    assert result['search_sequence_qualified'] and result['post_inspection_completed']
    assert not result.get('destination_click_and_observation_completed')
    assert 'destination' not in session.action_requests_admitted
    passed(mode+'_destination_denied_after_one_explicit_search')
for mode,reason in [('already_selected','PUBLIC_SEARCH_ALREADY_SELECTED_NO_CLICK_REQUIRED'),
                    ('missing_search','UNIQUE_CURRENT_PUBLIC_SEARCH_ROLE_REQUIRED')]:
    result,calls,counts,commands,session=exercise(search_mode=mode)
    assert result['error']['message']==reason and not any(op=='click' for op,n in calls)
    assert not result.get('click_sequence_started') and result['post_inspection_completed']
    assert not any(n in base.PLAN['nonces'].values() for op,n in calls)
    passed(mode+'_first_search_denied_no_destination')
first_failures={
 'search_click':'SYNTHETIC_HELPER_search_click',
 'search_after_state':'SYNTHETIC_HELPER_search_after_state',
 'search_unknown':'SYNTHETIC_SEARCH_ACTION_OUTCOME_UNKNOWN',
 'search_ack_unqualified':'ACTUAL_CURRENT_SEARCH_CLICK_ACK_REQUIRED',
 'search_state_changed':'POST_TERMINATION_ACCESSIBILITY_STATE_CHANGED'}
for fault,reason in first_failures.items():
    result,calls,counts,commands,session=exercise(failures=(fault,))
    assert result['error']['message']==reason,(fault,result['error'])
    assert result['error']['phase']=='explicit_public_search_click'
    assert result['post_inspection_attempted'] and result['post_inspection_completed']
    assert not result.get('search_sequence_qualified') and not result.get('click_sequence_started')
    assert not any(n in base.PLAN['nonces'].values() for op,n in calls)
    assert [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action']]
    assert result['failed_search_sequence'] is not result['post_sequence']
    passed(fault+'_first_error_and_no_second_sequence')
for fault in ('destination_click','destination_after_state','post_inspect'):
    result,calls,counts,commands,session=exercise(failures=(fault,))
    assert result['error']['message']=='SYNTHETIC_HELPER_'+fault
    assert result['search_sequence_qualified'] and result['post_inspection_attempted']
    assert not result.get('explicit_search_then_destination_completed')
    assert [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action'],base.PLAN['nonces']['action']]
    passed(fault+'_first_error_preserved_with_no_replay')
for first in ('search_unknown','destination_click'):
    result,calls,counts,commands,session=exercise(failures=(first,'post_inspect'))
    expected='SYNTHETIC_SEARCH_ACTION_OUTCOME_UNKNOWN' if first=='search_unknown' else 'SYNTHETIC_HELPER_destination_click'
    assert result['error']['message']==expected
    assert [x['message'] for x in result['secondary_errors']]==['SYNTHETIC_HELPER_post_inspect']
    assert result['post_inspection_attempted'] and not result.get('explicit_search_then_destination_completed')
    passed(first+'_not_overwritten_by_post_failure')
result,calls,*_=exercise(failures=('search_not_selected',))
assert result['error']['message']=='PUBLIC_SEARCH_SELECTION_NOT_OBSERVED'
assert [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action']]
assert result['post_inspection_completed']
passed('search_ACK_without_fresh_selected_role_cannot_authorize_destination')
result,calls,*_=exercise(changed_destination_task=True)
assert result['error']['message']=='QUALIFIED_SEARCH_AND_FRESH_SAME_TASK_DESTINATION_INSPECTION_REQUIRED'
assert [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action']]
passed('different_owned_task_before_destination_denied')
result,calls,*_=exercise(changed_post_task=True)
assert result['error']['message']=='TWO_EXPLICIT_ACKS_AND_INDEPENDENT_SAME_OWNED_TASK_READ_REQUIRED'
passed('different_owned_task_in_independent_post_denied')
for phase,expected_clicks in [('search',0),('destination',1)]:
    result,calls,*_=exercise(changed_window_phase=phase)
    assert result['error']['message']=='ORIGINAL_ACTIVITY_OR_WINDOW_CHANGED_AFTER_INSPECT'
    assert sum(op=='click' for op,n in calls)==expected_clicks and result['post_inspection_completed']
    passed(phase+'_original_pre_action_foreground_guard')
result,calls,_,_,session=exercise()
for role in ('search','destination'):
    before=len(calls)
    try:session.instrument(copy.deepcopy(session._action_bindings[role]))
    except RuntimeError as error:assert str(error)=='ONE_EXPLICIT_FRESH_REQUEST_PER_PUBLIC_ROLE_REQUIRED'
    else:raise AssertionError('action replay admitted')
    assert len(calls)==before
    passed(role+'_replay_rejected_before_IO')

scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.PACKAGE+'/.activity.MainActivity',
       'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH}
for role in ('search','destination'):
    for field,bad in [('nonce','e'*32),('node_path','0/9'),('node_sha256','d'*64),
                     ('inspection_nonce','c'*32),('inspection_sha256','f'*64),('scope',dict(scope,window_token='ab99'))]:
        accesses=[]
        class ProbeBase:
            def __init__(self,*args):pass
            def instrument(self,value):
                accesses.append(value['op']);assert value['op']=='inspect','invalid action reached I/O'
                tree=search_fixture() if value['nonce']==base.SEARCH_PLAN['nonces']['inspect'] else destination_fixture()
                return {'helper':{'inspection':tree,'tree_observations':tree_counts(tree,'inspect')},'wire_sha256':'b'*64}
        probe=types.SimpleNamespace(Session=ProbeBase,validate_plan=adapter.validate_plan)
        sp,cp,pp=(copy.deepcopy(plan) for plan in (base.SEARCH_PLAN,base.PLAN,base.POST_PLAN))
        session=public.make_session(probe,None,None,qa,{},base.HELPER_UID,sp,cp,pp,copy.deepcopy(base.SEARCH_READINESS_PLANS))
        # Isolate the original exact action binding after a synthetic qualified gate;
        # full original state/inspect/state readiness is exercised above and below.
        task={'task':4321};tree=search_fixture()
        obs=public.search_readiness_sample(qa,{'inspection':tree,'tree_observations':tree_counts(tree,'inspect')},scope,task)
        session.sequence_observation={'owned_task':task};session.search_readiness_qualified=True
        session.search_readiness_owned_task=task;session.search_readiness_identity=obs['identity_sha256']
        session.instrument({'protocol':qa.PROTOCOL,'op':'inspect','nonce':sp['nonces']['inspect'],'scope':scope})
        if role=='destination':
            # Isolate exact request binding; full sequencing is exercised above.
            session.search_sequence_qualified=True;session.search_owned_task={'task':4321}
            session.action_requests_admitted={'search'};session.sequence_observation={'owned_task':{'task':4321}}
            session.instrument({'protocol':qa.PROTOCOL,'op':'inspect','nonce':cp['nonces']['inspect'],'scope':scope})
        request=copy.deepcopy(session._action_bindings[role]);request[field]=bad;before=len(accesses)
        admitted_before=set(session.action_requests_admitted)
        try:session.instrument(request)
        except RuntimeError as error:
            assert str(error)==('ONE_EXPLICIT_FRESH_REQUEST_PER_PUBLIC_ROLE_REQUIRED' if field=='nonce'
                                else 'EXACT_FRESH_PUBLIC_ROLE_NODE_REQUEST_REQUIRED')
        else:raise AssertionError(role+' '+field+' changed action admitted')
        assert len(accesses)==before and session.action_requests_admitted==admitted_before
        passed(role+'_changed_action_'+field+'_denied_before_IO')
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


result,calls,counts,commands,session=exercise()
assert result['search_readiness_count']==3 and result['search_readiness_capture_span_ms']>=4000
assert result['search_readiness_future_stability_proven'] is False
assert all(row['sequence']['restoration_qualified'] for row in result['search_readiness_observations'])
assert [row['consecutive_equal'] for row in result['search_readiness_observations']]==[1,2,3]
assert all(row['observation']['connection_scoped_window_id_compared_across_invocations'] is False
           for row in result['search_readiness_observations'])
passed('three_complete_restored_samples_with_capture_span_only_no_future_guarantee')

result,calls,counts,commands,session=exercise(
    readiness_keys=['A','A','A','B','B','B','B','B'],readiness_step_ms=1000)
assert result['error'] is None and result['search_readiness_count']==8
assert [row['consecutive_equal'] for row in result['search_readiness_observations']]==[1,2,3,1,2,3,4,5]
assert result['search_readiness_capture_span_ms']==4001
assert commands==109 and counts=={'target_uid':2,'target_path':2,'helper_uid':24,'helper_path':24,
    'stacks':22,'foreground':33,'instrument':35,'click':2}
assert len(calls)==35 and sum(op=='click' for op,n in calls)==2
passed('fourth_observation_change_resets_run_and_can_qualify_at_eighth_with_exact_max_budget')

for label,options in [
 ('continually_changing_complete_tree',{'readiness_keys':list('ABCDEFGH')}),
 ('eight_equal_samples_insufficient_capture_span',{'readiness_step_ms':500})]:
    result,calls,counts,commands,session=exercise(**options)
    assert result['error']['phase']=='search_readiness'
    assert result['error']['message']=='SEARCH_READINESS_NOT_STABLE_WITHIN_EIGHT_COMPLETE_READS'
    assert len(result['search_readiness_observations'])==8
    assert not result.get('search_sequence_started') and not result.get('click_sequence_started')
    assert result['post_inspection_completed'] and not any(op=='click' for op,n in calls)
    assert not session.action_requests_admitted
    passed(label+'_finite_no_action_failure_and_independent_post')

for fault,maximum_read_inspects in [
 ('partial',1),('failed_inspect',1),('failed_after',1),('after_state_changed',1),
 ('task_changed',2),('scope_changed',2),('deadline',1),('capture_backwards',2),
 ('counter_incomplete',1),('foreign_window',1),('bad_tree_digest',1)]:
    result,calls,counts,commands,session=exercise(readiness_fault=fault)
    assert result['error'] is not None and result['error']['phase']=='search_readiness',(fault,result['error'])
    assert not result.get('search_sequence_started') and not result.get('click_sequence_started')
    assert not result.get('search_readiness_qualified') and not session.action_requests_admitted
    assert result['post_inspection_completed'] and not any(op=='click' for op,n in calls)
    read_inspect_nonces={p['nonces']['inspect'] for p in base.SEARCH_READINESS_PLANS}
    assert sum(n in read_inspect_nonces for op,n in calls)<=maximum_read_inspects
    assert result['failed_search_readiness_sequence']['after_state_attempted'] is True
    if fault!='failed_after':
        assert result['failed_search_readiness_sequence']['after_state_completed'] is True
    passed('readiness_'+fault+'_first_failure_stops_further_sampling_and_all_clicks')

result,calls,counts,commands,session=exercise(changed_after_readiness=True)
assert result['search_readiness_qualified'] and result['search_sequence_started']
assert result['error']['phase']=='explicit_public_search_click'
assert result['error']['message']=='SEARCH_CHANGED_AFTER_READINESS_NO_ACTION'
assert not any(op=='click' for op,n in calls) and not result.get('click_sequence_started')
assert result['failed_search_sequence']['after_state_completed'] and result['post_inspection_completed']
passed('fresh_Search_inspection_change_after_gate_stops_before_action_without_resampling')

result,calls,counts,commands,session=exercise(readiness_fault='failed_inspect',failures=('post_inspect',))
assert result['error']['message']=='SYNTHETIC_READINESS_FAILED_INSPECT'
assert [x['message'] for x in result['secondary_errors']]==['SYNTHETIC_HELPER_post_inspect']
assert result['failed_search_readiness_sequence'] is not result['failed_post_sequence']
assert not any(op=='click' for op,n in calls)
passed('readiness_primary_preserved_when_independent_post_also_fails')

for label,mutate in [('input_plan',lambda plans:plans[0].update(operation='click')),
                     ('ninth_plan',lambda plans:plans.append(copy.deepcopy(plans[0])))]:
    plans=copy.deepcopy(base.SEARCH_READINESS_PLANS);mutate(plans)
    try:
        context.Policy('inspect',qa,['synthetic-resolve'],
            {'search':base.SEARCH_PLAN,'destination':base.PLAN,'post':base.POST_PLAN,'readiness':plans},
            PurePosixPath('/synthetic/no-files-created'),lambda *a:b'',lambda:{})
    except RuntimeError as error:
        assert str(error)=='EXPLICIT_SEARCH_DESTINATION_POST_AND_EIGHT_NO_ACTION_READINESS_PLANS'
    else:raise AssertionError('readiness authority widened')
    passed('readiness_policy_'+label+'_rejected_without_IO')


assert len(cases)==89 and len({x['case'] for x in cases})==89,('control inventory changed',len(cases))
out={'schema':1,'ok':True,'state':'IHG_BOUNDED_SEARCH_READINESS_COMPOSITION_PURE_CONTROLS_PASS','controls':cases,
 'control_count':len(cases),'template_source_pins':TEMPLATE_PINS,'bound_source_pins':BOUND_PINS,
 'control_stdin_sha256':hashlib.sha256(raw).hexdigest(),
 'bound_coordinator_sha256':BOUND_PINS['coordinator']['sha256'],'bound_stage_sha256':BOUND_PINS['stage']['sha256'],
 'original_Session_sequence_and_real_contract_summary_and_policy_executed':True,
 'all_template_and_bound_python_compile':True,'synthetic_in_memory_IO_only':True,'real_Java_helper_executed':False,
 'file_writes':0,'Android_actions':0,'device_or_child_process_commands':0,'fresh_nonce_values':pool,
 'nonce_values_disjoint_prior_IHG_literals':not bool(set(pool)&set(old)),
 'maximum_readiness_sequences':8,'readiness_qualification_seconds':20,'minimum_consecutive_samples':3,
 'minimum_capture_span_ms':4000,'success_durable_commands_formula':'37+9*k; 3<=k<=8',
 'maximum_success_durable_commands':109,'maximum_helper_nonces':35,'maximum_click_actions':2,
 'old_successful_click_outcome_unknown_preserved':True,'actual_UI_readiness_verified':False,
 'old_Main_identity_validated':False,'runtime_flow_dispatched':False,'whole_app_production_ready':False}
encoded=json.dumps(out,sort_keys=True,separators=(',',':'))
assert len(encoded.encode())<=32768
print(encoded,flush=True)
