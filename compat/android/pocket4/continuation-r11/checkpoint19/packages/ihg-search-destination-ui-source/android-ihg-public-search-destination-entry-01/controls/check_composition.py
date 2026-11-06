"""Original R1 Session/Policy with synthetic I/O for explicit Search then Destination."""
import ast,copy,hashlib,json,re,sys,types
from pathlib import PurePosixPath
raw=sys.stdin.buffer.read(196609)
assert len(raw)<=196608 and hashlib.sha256(raw).hexdigest()=='a239cc5a96240b9037c1ca4360f31cf2e52a08c7986ac61c0ca74806bf9c9bc2'
p=json.loads(raw)
assert p['schema']==1 and set(p)=={'schema','contract','adapter','public_destination','context','coordinator','stage','nonce_values','nonce_exclusions'}
PINS={"contract":{"bytes":28150,"sha256":"573fdcd691ed51b76f965151b74b38cfcbd12ed5aa972d668146ae136744d7e1"},"adapter":{"bytes":20785,"sha256":"0918dca47db8451baf1cb74fc6c50934e7c87a97e25aff6cc7a568ac21a091f9"},"public_destination":{"bytes":24757,"sha256":"bcb73807e836d1c0632ccc922caecf9c8d859510cdc11e6d667d3dde747f2c6c"},"context":{"bytes":16353,"sha256":"4994282ccdb32bdbb0a5356a498eea848a0cc706de602578dba4826cb9b88458"},"coordinator":{"bytes":39026,"sha256":"551637816ce2551b316d118d1da7e521f1df0638ee192c08db2240856fb750ad"},"stage":{"bytes":5038,"sha256":"d11ed1505b9a066f33b7782b806fef1d02a237763f8bd9c486543a583e25d034"}}
for name,pin in PINS.items():
    data=p[name].encode();assert len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],name
    compile(p[name],'<compile-only-'+name+'>','exec')
pool=p['nonce_values'];old=p['nonce_exclusions']
assert len(pool)==len(set(pool))==12 and len(old)==len(set(old))==18
assert all(re.fullmatch('[0-9a-f]{32}',v) for v in pool+old) and not set(pool)&set(old)
def module(text,name):
    # Only HERE.resolve() is removed in the isolated synthetic namespace.
    tree=ast.parse(text)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    m=types.ModuleType(name);m.__file__='/pure-control/'+name+'.py';m.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),m.__dict__)
    return m
qa=module(p['contract'],'ihg_actual_r1_contract')
adapter=module(p['adapter'],'ihg_actual_r1_adapter')
public=module(p['public_destination'],'explicit_search_destination_gate')
context=module(p['context'],'ihg_actual_task_context')
base=module(p['coordinator'],'search_destination_coordinator')
assert qa.PROTOCOL=='pocket4-owned-ihg-qa-v1' and qa.SELF=='org.droidloom.qa.ihg.r1'
cases=[]
def passed(name):cases.append({'case':name,'passed':True})
passed('exact_original_contract_adapter_pins_and_all_candidate_compile')
for plan in (base.SEARCH_PLAN,base.PLAN,base.POST_PLAN):adapter.validate_plan(plan,qa)
assert [base.NONCE,*[base.SEARCH_PLAN['nonces'][k] for k in ('before','inspect','action','after')],
        *[base.PLAN['nonces'][k] for k in ('before','inspect','action','after')],
        *[base.POST_PLAN['nonces'][k] for k in ('before','inspect','after')]]==pool
passed('twelve_actual_fresh_nonces_ordered_for_two_explicit_clicks_and_post_read')

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
             changed_destination_task=False,changed_window_phase=None):
    search,click,post=(copy.deepcopy(plan) for plan in (base.SEARCH_PLAN,base.PLAN,base.POST_PLAN))
    failures=set(failures);calls=[];fg_count=[0];task_count=[0]
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
        {'search':search,'destination':click,'post':post},step,read,lambda:copy.deepcopy(owned))
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
            if changed_destination_task and 2<task_count[0]<=4:return dict(owned,task=4322)
            if changed_post_task and task_count[0]>4:return dict(owned,task=4322)
            return copy.deepcopy(owned)
        def foreground(self):
            admit(context.FOREGROUND,15,private=True);fg_count[0]+=1
            changed_at=2 if changed_window_phase=='search' else 5 if changed_window_phase=='destination' else None
            return dict(scope,window_token='ab13') if fg_count[0]==changed_at else copy.deepcopy(scope)
        def instrument(self,request):
            qa.validate_request(request);nonce,op=request['nonce'],request['op']
            assert nonce not in self.nonces;self.nonces.add(nonce)
            memory[str(step/(nonce+'.request.json'))]=json.dumps(request).encode()
            admit(qa.instrumentation_argv(request),20,mutation=op=='click');calls.append((op,nonce))
            phase=('search' if nonce in search['nonces'].values() else
                   'destination' if nonce in click['nonces'].values() else 'post')
            fault=(phase+'_click' if op=='click' else
                   phase+'_after_state' if nonce=={'search':search,'destination':click,'post':post}[phase]['nonces']['after']
                   else phase+'_inspect' if op=='inspect' else None)
            if fault in failures:
                error=RuntimeError('SYNTHETIC_HELPER_'+fault)
                error.details={'action_attempted':op=='click','outcome_unknown':op=='click'}
                raise error
            if phase=='search' and op=='click' and 'search_unknown' in failures:
                error=RuntimeError('SYNTHETIC_SEARCH_ACTION_OUTCOME_UNKNOWN')
                error.details={'action_attempted':True,'outcome_unknown':True};raise error
            helper={'protocol':qa.PROTOCOL,'op':op,'nonce':nonce,'self_uid':base.HELPER_UID,'ok':True,
                'error':None,'secondary_errors':[],'ui_automation_connected':op!='state',
                'restoration':{'service_info_verified':True}}
            if op=='state':
                helper['state']=copy.deepcopy(state)
                if phase=='search' and nonce==search['nonces']['after'] and 'search_state_changed' in failures:
                    helper['state']['accessibility_enabled']=True
            else:
                helper['accessibility_state_before_connection']=copy.deepcopy(state)
                tree=(search_fixture(search_mode) if phase=='search' else
                      destination_fixture(mode,selected='search_not_selected' not in failures) if phase=='destination'
                      else destination_fixture())
                helper['window_observation']=window_observation();helper['tree_observations']=tree_counts(tree,op)
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
    session=public.make_session(seam,flow,None,qa,{},base.HELPER_UID,search,click,post)
    result={'ok':False,'error':None,'secondary_errors':[]}
    def remember(phase,error):
        row={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if result['error'] is None:result['error']=row
        else:result['secondary_errors'].append(row)
    original_read=base.read;base.read=read
    try:
        for argv in (context.LIST,context.PATHS):admit(argv,15)
        session.installed()
        public.run_sequences(qa,session,base.INSTALLED,search,click,post,result,
            lambda seq,plan:base.assessment_summary(types.SimpleNamespace(qa=qa),step,seq,plan),remember)
        session.installed()
        for argv in (context.LIST,context.PATHS):admit(argv,15)
    finally:base.read=original_read
    assert sum(op=='click' for op,nonce in calls)<=2
    assert calls[-1]==('state',post['nonces']['after'])
    assert ('state',search['nonces']['after']) in calls
    if result.get('click_sequence_started'):assert ('state',click['nonces']['after']) in calls
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
    assert len(calls)==11 and [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action'],base.PLAN['nonces']['action']]
    assert counts=={'target_uid':2,'target_path':2,'helper_uid':8,'helper_path':8,'stacks':6,'foreground':9,'instrument':11,'click':2}
    assert commands==37 and all(result[k]['restoration_qualified'] for k in ('search_sequence','sequence','post_sequence'))
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
                return {'helper':{'inspection':tree},'wire_sha256':'b'*64}
        probe=types.SimpleNamespace(Session=ProbeBase,validate_plan=adapter.validate_plan)
        sp,cp,pp=(copy.deepcopy(plan) for plan in (base.SEARCH_PLAN,base.PLAN,base.POST_PLAN))
        session=public.make_session(probe,None,None,qa,{},base.HELPER_UID,sp,cp,pp)
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
assert len(cases)==70 and len({x['case'] for x in cases})==70,('control inventory changed',len(cases))
out={'schema':1,'ok':True,'state':'IHG_EXPLICIT_SEARCH_DESTINATION_PURE_CONTROLS_PASS','controls':cases,
 'control_count':len(cases),'source_pins':PINS,'control_stdin_sha256':hashlib.sha256(raw).hexdigest(),
 'bound_coordinator_sha256':PINS['coordinator']['sha256'],'bound_stage_sha256':PINS['stage']['sha256'],
 'original_Session_sequence_and_real_contract_summary_and_policy_executed':True,
 'all_candidate_python_compile':True,'synthetic_in_memory_IO_only':True,'real_Java_helper_executed':False,
 'file_writes':0,'Android_actions':0,'device_or_child_process_commands':0,'fresh_nonce_values':pool,
 'nonce_values_disjoint_prior_IHG_literals':not bool(set(pool)&set(old)),
 'success_durable_commands':37,'success_helper_nonces':11,'maximum_click_actions':2,
 'old_successful_click_outcome_unknown_preserved':True,'actual_UI_readiness_verified':False,
 'runtime_flow_dispatched':False,'whole_app_production_ready':False}
encoded=json.dumps(out,sort_keys=True,separators=(',',':'))
assert len(encoded.encode())<=32768
print(encoded,flush=True)
