"""Current IHG R4 Search, Destination and London input; synthetic I/O only."""
import ast,copy,hashlib,json,re,secrets,sys,types
from pathlib import PurePosixPath
CONTROL_INPUT_BYTES=239605
CONTROL_INPUT_SHA256="03db8ccb36e5028d35106465d499b15fcc7986f578ef30b1f6dafd09116b3fa8"
CONTROL_SOURCE_PINS={"adapter":{"bytes":21676,"sha256":"4da61e732e72e8db4f0bea4134d7e538271abcfa261c8d2c50c76f13d2e76f1e"},"context":{"bytes":19574,"sha256":"9224e8c896dedbe2294618604d5e67972b535cef5bef58c5ef2e07752974ce91"},"contract":{"bytes":28757,"sha256":"5d83ba26324fd180abfd9069538a077a90a661d94c7a3d123694197b39430405"},"coordinator":{"bytes":46630,"sha256":"562629c6c00d40a41cdf6fe2edf3df01292fb6f78409f8fd08b7776f02bf7bb0"},"public_destination":{"bytes":42662,"sha256":"813fd9a4d17047df6e4dba2a5fe9142f890e27427034996fad303e40fb8553f8"},"stage":{"bytes":5193,"sha256":"09ad6954cada7348632a2d102bf20a49c63a4538bcac8bdc77a66462e1be3ef9"},"transport":{"bytes":15606,"sha256":"aa4836f35ea0251fbf3942033db2a45e37a882ebf6f7b6076b45c63970d5c516"}}
CONTROL_EXCLUSION_COUNT=659
CONTROL_NONCE_RECEIPT={"actual_helper_uid":10158,"bytes":2575,"count":40,"excluded_count":659,"excluded_sha256":"1cc2123d4223f0ed94f232c70264e847ebb91de2dba84e516f659dc56fcd36a3","generator":"secrets.token_hex(16)","git_blob":"b8bcfd1a535f3f6ecb2be8a0317d3a9342996961","job_id":"1a1b1c08bfd-fc05-7aa4","no_redraw":True,"sha256":"6bee83bf5f7e17a82314b9cd4d7f3f11b4bd565052a3a9081008ce5c05e1791e"}
CONTROL_ACTUAL_INSTALL_PINS={"coordinator":{"bytes":4455,"sha256":"c1129d2c99210e47d12ca985b604ad0056d26c11d9c2d2f071fc3dc7e678ede4"},"stage":{"bytes":10553,"sha256":"ac3451c8a45ff6d0543cbb97e14d5619c116e83d2f71ccba0a1484e2e69c3a5b"},"worker":{"bytes":13294,"sha256":"e9c478188a0f71b5e2d6f8449e16858f9bf2b2f65980f91847027056539bfb03"}}
def run_task_discovery_route_controls(task_module, coordinator, qa):
    """Execute production open_task_context with explicit in-memory I/O seams.

    The already actual-tested installed discovery API is an observed boundary.
    These cases test forwarding, no legacy bypass, and original close-on-error;
    they do not claim real /proc, held-FD, baseline, or Android qualification.
    """
    import ast
    import copy
    import json
    import stat
    import types
    from pathlib import PurePosixPath
    rows=[]
    def need(value,reason):
        if not value:raise RuntimeError(reason)
    def case(mode):
        calls=[];state={'closed':False,'flow':False,'discover':0,'legacy':0}
        class MemoryPath(type(PurePosixPath('/'))):
            def lstat(self):
                return types.SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
        root=MemoryPath('/memory-flow');step=root/'steps/inspect'
        source_root=MemoryPath('/memory-install/source')
        host_root=MemoryPath('/memory-host')
        expected='d'*64
        install_pin=coordinator.INSTALL_SOURCE_SHA
        need(isinstance(install_pin,str) and len(install_pin)==64,'FIXED_INSTALL02_SOURCE_REQUIRED')
        baseline={'schema':qa.MAIN_BASELINE_SCHEMA,'kind':'current-cell-generation',
            'deployment_performed':False,'framework_exit_cause_resolved':False,
            'whole_app_production_ready':False,'packages':{qa.PACKAGE:qa.UID},
            'framework_epoch':{'sha256':qa.MAIN_EPOCH,
                'binding':{'processes':{'init':{'host_pid':12001}}}},
            'status':{'host_pid':12000}}
        ref=types.SimpleNamespace(current_baseline=lambda:copy.deepcopy(baseline),
            BASELINE=MemoryPath('/memory-baseline'),BASELINE_SHA=qa.MAIN_BASELINE_SHA,
            QUALIFICATION=MemoryPath('/memory-qualification'),
            QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA,
            EPOCH=qa.MAIN_EPOCH,EPOCH_SOURCE=MemoryPath('/memory-epoch.py'),EPOCH_SOURCE_SHA='e'*64)
        scope=coordinator.scope_record(types.SimpleNamespace(ref=ref,
            adapter=types.SimpleNamespace(RECORDER_MANIFEST_SHA=task_module.CURRENT_HOST_MANIFEST)),expected)
        scope_raw=json.dumps(scope).encode()
        epoch=object()
        def source_verify(value):
            need(value==expected,'TASK_SOURCE_MANIFEST_CHANGED');calls.append('task_source_verify')
        def read(path,maximum=1048576,expected=None,size=None):
            if path==root/'scope.json':return scope_raw
            return b'memory'
        ref.read=read
        ref.module=lambda raw,path,name:epoch
        def main_guard(value,module):
            need(value==baseline and module is epoch,'ORIGINAL_MAIN_CALLBACK_ARGUMENTS')
            calls.append('Main_guard');return {'in_memory':True}
        ref.main_guard=main_guard
        writes=[]
        ref.write_new=lambda path,value:writes.append((path,value))
        class Target:
            def __init__(self,identity,path,digest):
                need(identity==baseline['framework_epoch']['binding']['processes']['init'],
                     'ORIGINAL_HELD_TARGET_IDENTITY')
                self.record={'in_memory_target':True}
            def close(self):state['closed']=True
        held=types.SimpleNamespace(HeldTarget=Target,
            proc_identity_at=lambda fd,pid,deadline:copy.deepcopy(baseline['framework_epoch']['binding']['processes']['init']))
        def classpaths(held_arg,target,observed,module,guard):
            need(held_arg is held and observed==baseline['framework_epoch'] and module is epoch,
                 'ORIGINAL_CLASSPATH_ARGUMENTS')
            guard();return {'BOOTCLASSPATH':'/memory.jar'},{'fixture':True}
        binding=types.SimpleNamespace(same_epoch_identity=lambda a,b:a==b,main_classpaths=classpaths)
        recorder=types.SimpleNamespace(APP='/memory-android-app.py',APP_SHA='a'*64,
            task_functions=lambda path:types.SimpleNamespace())
        loads={'recorder.py':recorder,'references/held_runtime_r5.py':held,'main_binding.py':binding}
        contract=types.SimpleNamespace(sha256=task_module.CURRENT_HOST_MANIFEST,
            verify=lambda:calls.append('contract_verify'),load=lambda name,label:loads[name])
        shared=types.SimpleNamespace(SourceContract=lambda path,digest:contract,
            HELPER_PATH=MemoryPath('/memory-helper'),HELPER_BYTES=6,HELPER_SHA='f'*64,
            verify_shared_helper=lambda:{'whole_process_tree_cleanup_qualified':False})
        def legacy():
            state['legacy']+=1;raise RuntimeError('LEGACY_DISCOVERY_BYPASS')
        app=types.SimpleNamespace(discover=legacy)
        def module(path,digest,label):
            if str(path)==str(host_root/'source_contract.py'):
                need(digest=='b'*64,'EXACT_SHARED_CONTRACT_PIN');return shared
            need(str(path)==recorder.APP and digest==recorder.APP_SHA,
                 'EXACT_LEGACY_REFERENCE_PIN');return app
        def verify_install(value):
            need(value==install_pin,'INSTALL_SOURCE_MANIFEST_CHANGED')
            if mode=='source_changed':raise RuntimeError('EXACT_INSTALL_SOURCE_STOP')
            calls.append('install_source_verify');return {'in_memory_manifest':True}
        util=types.SimpleNamespace(HERE=source_root,module=module,read=read,verify_source=verify_install)
        def current_discovery(util_arg,manifest,verify,where,app_arg,base,epoch_arg,guard):
            need(util_arg is util and manifest==install_pin and verify is verify_install and
                 where==source_root and app_arg is app and base==baseline and epoch_arg is epoch,
                 'EXPLICIT_PINNED_DISCOVERY_ARGUMENTS_REQUIRED')
            verify(manifest)
            state['discover']+=1
            guard()
            status={'host_pid':12000}
            return (12002 if mode=='wrong_init' else 12001),{'BOOTCLASSPATH':'/memory.jar'},status
        context=types.SimpleNamespace(INSTALLED_SHARED=host_root,CONTRACT_SHA='b'*64,
            SHARED_MANIFEST=task_module.CURRENT_HOST_MANIFEST,
            baseline_scope=lambda ref_arg,base:{'package':qa.PACKAGE,'uid':qa.UID},
            current_discovery=current_discovery,
            verify_target_data=lambda target,base,binding_arg:need(
                base==baseline and binding_arg is binding,'ORIGINAL_TARGET_DATA_GUARD'))
        transport=types.SimpleNamespace(environment_values=lambda value:copy.deepcopy(value))
        def flow_factory(**values):
            need(values['recorder'] is recorder and values['contract'] is contract and
                 values['transport'] is transport and values['qa'] is qa and
                 values['scope']==scope and values['activation']==baseline,
                 'UNCHANGED_FLOW_CONSTRUCTOR_ARGUMENTS')
            state['flow']=True
            return types.SimpleNamespace(**values)
        namespace=dict(task_module.open_task_context.__globals__)
        namespace['Path']=MemoryPath
        namespace['time']=types.SimpleNamespace(monotonic=lambda:1.0)
        namespace['os']=types.SimpleNamespace(O_RDONLY=0,O_DIRECTORY=1,O_NOFOLLOW=2,O_CLOEXEC=4,
            open=lambda path,flags:(need(path=='/proc/12001','EXACT_PROTECTED_INIT_PROC') or 10),
            close=lambda fd:need(fd==10,'ONLY_MEMORY_PROC_FD'))
        namespace['Flow']=flow_factory
        gate=types.FunctionType(task_module.open_task_context.__code__,namespace)
        result={}
        def run():
            return gate(ref,util,context,expected,source_verify,root,step,transport,result,
                20.0,'inspect',qa,{},[],scope,install_source_manifest=install_pin)
        return run,state,calls,writes,result
    run,state,calls,writes,result=case('positive')
    flow,recorder,guard=run()
    need(state['discover']==1 and state['legacy']==0 and state['flow'] and not state['closed'] and
         len(writes)==1 and calls.count('install_source_verify')==1 and
         calls.count('Main_guard')==4 and result['Main_before']=={'in_memory':True},
         'PRODUCTION_TASK_OPEN_MUST_REACH_CURRENT_DISCOVERY')
    rows.append({'name':'production_open_task_context_routes_pinned_current_discovery','passed':True})
    for mode,error,name in [
        ('source_changed','EXACT_INSTALL_SOURCE_STOP','changed_install_source_stops_before_discovery'),
        ('wrong_init','FIXED_MAIN_DISCOVERY_CHANGED','wrong_discovered_init_retains_original_guard')]:
        run,state,calls,writes,result=case(mode)
        try:run()
        except RuntimeError as caught:need(str(caught)==error,'WRONG_TASK_ROUTE_FIRST_ERROR:'+name)
        else:raise RuntimeError('TASK_ROUTE_NEGATIVE_ACCEPTED:'+name)
        need(state['closed'] and not state['flow'] and state['legacy']==0 and not writes,
             'FAILED_TASK_ROUTE_MUST_CLOSE_HELD_TARGET')
        if mode=='source_changed':need(state['discover']==0,'SOURCE_FAILURE_REACHED_DISCOVERY')
        rows.append({'name':'production_open_task_context_'+name,'passed':True})
    return rows


raw=sys.stdin.buffer.read(262145)
assert len(raw)==CONTROL_INPUT_BYTES and hashlib.sha256(raw).hexdigest()==CONTROL_INPUT_SHA256
p=json.loads(raw)
assert p['schema']==3 and set(p)=={'schema','contract','adapter','public_destination','context','coordinator','stage','transport','fresh_nonces','nonce_exclusions','nonce_receipt','actual_install_originals'}
TEMPLATE_PINS=CONTROL_SOURCE_PINS
for name,pin in TEMPLATE_PINS.items():
    data=p[name].encode();assert len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],name
    compile(p[name],'<compile-only-actual-bound-'+name+'>','exec')
pool=p['fresh_nonces'];old=p['nonce_exclusions']
assert len(pool)==len(set(pool))==40 and all(re.fullmatch('[0-9a-f]{32}',v) for v in pool)
assert len(old)==len(set(old))==CONTROL_EXCLUSION_COUNT and all(re.fullmatch('[0-9a-f]{32}',v) for v in old)
assert not set(pool)&set(old)
assert p['nonce_receipt']==CONTROL_NONCE_RECEIPT
BOUND_PINS=copy.deepcopy(TEMPLATE_PINS)
def module(text,name):
    tree=ast.parse(text)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    m=types.ModuleType(name);m.__file__='/pure-control/'+name+'.py';m.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),m.__dict__)
    return m
qa=module(p['contract'],'ihg_actual_r4_contract')
adapter=module(p['adapter'],'ihg_actual_r4_adapter')
public=module(p['public_destination'],'bounded_search_readiness_and_destination_gate')
context=module(p['context'],'ihg_actual_task_context')
base=module(p['coordinator'],'search_readiness_destination_coordinator')
assert qa.PROTOCOL=='pocket4-owned-ihg-qa-v4' and qa.SELF=='org.droidloom.qa.ihg.r4' and qa.PUBLIC_SEARCH_QUERY=='London'
transport=module(p['transport'],'current_IHG_bound_arun_constructor')
assert type(base.HELPER_UID) is int and base.HELPER_UID==context.HELPER_UID and isinstance(base.INSTALLED,dict)
assert base.INSTALLED['uid']==base.HELPER_UID and base.INSTALLED['package']==qa.SELF
assert base.CURRENT_EPOCH==context.CURRENT_EPOCH==qa.MAIN_EPOCH==transport.FRAMEWORK_EPOCH_SHA256
assert base.CURRENT_BASELINE_SHA==context.CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA
assert base.CURRENT_QUALIFICATION_SHA==context.CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA
assert base.CURRENT_HOST_MANIFEST==context.CURRENT_HOST_MANIFEST==adapter.RECORDER_MANIFEST_SHA
cases=[]
def passed(name):cases.append({'case':name,'passed':True})
passed('exact_original_contract_adapter_pins_and_all_template_and_bound_compile')
for plan in (base.SEARCH_PLAN,base.PLAN,base.POST_PLAN,*base.SEARCH_READINESS_PLANS):adapter.validate_plan(plan,qa)
public.validate_pending_input_plan(qa,base.INPUT_PLAN)
assert [base.NONCE,*[base.SEARCH_PLAN['nonces'][k] for k in ('before','inspect','action','after')],
        *[base.PLAN['nonces'][k] for k in ('before','inspect','action','after')],
        *[base.INPUT_PLAN['nonces'][k] for k in ('before','inspect','action','after')],
        *[base.POST_PLAN['nonces'][k] for k in ('before','inspect','after')],
        *[plan['nonces'][k] for plan in base.SEARCH_READINESS_PLANS for k in ('before','inspect','after')]]==pool
passed('forty_actual_secrets_nonces_ordered_and_disjoint_for_fresh_London_flow')

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

def editor_fixture(mode='ready',value=''):
    distance=6 if mode=='ancestor_at_six' else 7 if mode=='ancestor_at_seven' else 1
    root=node('0','android.view.ViewGroup','SYNTHETIC_PRIVATE_NONPUBLIC_LABEL',box=[0,0,1000,1500])
    container=node('0/0','android.view.ViewGroup',box=[0,0,900,400])
    nodes=[root,container];path=container['path']
    for _ in range(distance-1):
        path+='/0';nodes.append(node(path,'android.widget.LinearLayout',box=[0,100,800,200]))
    editor=node(path+'/0','android.widget.EditText',value,resource=qa.PACKAGE+':id/SYNTHETIC_EDITOR_A',box=[0,100,800,200])
    editor.update(editable=True,supports_set_text=True)
    label=node('0/0/1','android.widget.TextView','Destination',box=[0,0,800,100])
    other=node('0/0/2','android.widget.ImageView',box=[800,0,900,100])
    nodes.extend([editor,label,other])
    tree={'complete':True,'traversal':'visible-non-password-subtrees','nodes':nodes,
        'window':{'bounds':[0,0,1000,1500],'focused':True,'package':qa.PACKAGE,'display':0,'type':1},
        'connection_scoped_window_id':42,'observed_elapsed_ms':100}
    if mode=='fresh_different_resource':
        editor.update(resource_id=qa.PACKAGE+':id/SYNTHETIC_EDITOR_B',resource_id_sha256=qa.sha((qa.PACKAGE+':id/SYNTHETIC_EDITOR_B').encode()))
    if mode=='description_label':
        label.update(text='',text_sha256=qa.sha(b''),content_desc='Destination',content_desc_sha256=qa.sha(b'Destination'))
    if mode=='chinese_label':
        label.update(text='目的地',text_sha256=qa.sha('目的地'.encode()))
    if mode=='missing_editor':nodes.remove(editor)
    if mode=='duplicate_editor':
        duplicate=copy.deepcopy(editor);duplicate['path']='0/0/3';nodes.append(duplicate)
    if mode=='disabled_editor':editor['enabled']=False
    if mode=='hidden_editor':editor['visible']=False
    if mode=='password_editor':editor['password']=True
    if mode=='not_editable':editor['editable']=False
    if mode=='no_set_text':editor['supports_set_text']=False
    if mode=='wrong_editor_class':editor.update(**{'class':'android.widget.TextView','class_sha256':qa.sha(b'android.widget.TextView')})
    if mode=='foreign_resource':editor.update(resource_id='org.other:id/editor',resource_id_sha256=qa.sha(b'org.other:id/editor'))
    if mode=='empty_resource':editor.update(resource_id='',resource_id_sha256=qa.sha(b''))
    if mode=='truncated_resource':editor['resource_id_truncated']=True
    if mode=='bad_resource_digest':editor['resource_id_sha256']='f'*64
    if mode=='resource_too_long':
        resource=qa.PACKAGE+':id/'+('x'*257);editor.update(resource_id=resource,resource_id_sha256=qa.sha(resource.encode()))
    if mode=='missing_label':nodes.remove(label)
    if mode=='duplicate_label':nodes.append(node('0/0/3','android.widget.TextView','Destination',box=[0,200,800,300]))
    if mode=='truncated_label':label['text_truncated']=True
    if mode=='disabled_label':label['enabled']=False
    if mode=='bad_label_digest':label['text_sha256']='f'*64
    if mode=='wrong_label_class':label.update(**{'class':'android.widget.Button','class_sha256':qa.sha(b'android.widget.Button')})
    if mode=='other_public_role':
        other.update(**{'class':'android.widget.TextView','class_sha256':qa.sha(b'android.widget.TextView'),'text':'Dates','text_sha256':qa.sha(b'Dates')})
    if mode=='bad_editor_geometry':editor['bounds']=[-1,100,800,200]
    if mode=='bad_parent_geometry':container['bounds']=[0,0,10,10]
    if mode=='wrong_parent_class':container.update(**{'class':'android.widget.Button','class_sha256':qa.sha(b'android.widget.Button')})
    if mode=='missing_parent':nodes.remove(container)
    if mode=='partial':tree['complete']=False
    if mode=='foreign_window':tree['window']['package']='org.other'
    if mode=='wrong_display':tree['window']['display']=1
    if mode=='truncated_text':editor['text_truncated']=True
    if mode=='bad_text_digest':editor['text_sha256']='f'*64
    refresh(tree)
    if mode=='wrong_child_count':container['child_count']+=1;refresh(tree,False)
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

def exercise(mode='ready',failures=(),search_mode='ready',changed_post_task=False,
             changed_destination_task=False,changed_window_phase=None,
             readiness_keys=None,readiness_step_ms=2100,readiness_fault=None,
             changed_after_readiness=False,input_mode='ready',changed_input_task=False,
             post_editor_mode='ready',post_value=None):
    search,click,typing,post=(copy.deepcopy(plan) for plan in (base.SEARCH_PLAN,base.PLAN,base.INPUT_PLAN,base.POST_PLAN))
    readiness=copy.deepcopy(base.SEARCH_READINESS_PLANS)
    readiness_keys=list(readiness_keys or ['A']*8)
    assert len(readiness_keys)==8
    failures=set(failures);calls=[];fake_clock=[0.0];ready_started=[];latest_key=['A'];typed_value=['']
    state={'accessibility_enabled':False,'touch_exploration_enabled':False,
        'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')}
    scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,'activity':qa.PACKAGE+'/.activity.MainActivity',
        'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH,
        'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
        'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}
    owned={'task':4321,'package':qa.PACKAGE,'prelaunch_absent':True,'cleanup_allowed':True}
    step=PurePosixPath('/synthetic/no-files-created');memory={}
    def read(path,maximum=1048576,*args,**kwargs):
        try:data=memory[str(path)]
        except KeyError:raise FileNotFoundError(str(path))
        assert len(data)<=maximum;return data
    policy=context.Policy('inspect',qa,['synthetic-resolve'],
        {'search':search,'destination':click,'input':typing,'post':post,'readiness':readiness},step,read,lambda:copy.deepcopy(owned))
    flow=types.SimpleNamespace(contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),
        scope={'schema':'pocket4-current-recorder-scope-v2','current_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
            'epoch_sha256':qa.MAIN_EPOCH,'current_baseline_sha256':qa.MAIN_BASELINE_SHA,
            'current_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
            'package':qa.PACKAGE,'uid':qa.UID,'user':0},
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
                'input' if plan['nonces']==typing['nonces'] else
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
            if changed_input_task and phase=='input':return dict(owned,task=4322)
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
            admit(qa.instrumentation_argv(request),20,mutation=op in ('click','set_text'));calls.append((op,nonce))
            phase=self.synthetic_phase
            plan=(readiness[self.synthetic_ready_index] if phase=='readiness' else
                  {'search':search,'destination':click,'input':typing,'post':post}[phase])
            fault=(phase+'_click' if op=='click' else phase+'_input' if op=='set_text' else phase+'_after_state' if nonce==plan['nonces']['after']
                   else phase+'_inspect' if op=='inspect' else None)
            if fault in failures:
                error=RuntimeError('SYNTHETIC_HELPER_'+fault)
                error.details={'action_attempted':op in ('click','set_text'),'outcome_unknown':op in ('click','set_text')}
                raise error
            if phase=='readiness' and ((readiness_fault=='failed_inspect' and op=='inspect') or
                    (readiness_fault=='failed_after' and nonce==plan['nonces']['after'])):
                raise RuntimeError('SYNTHETIC_READINESS_'+readiness_fault.upper())
            if phase=='search' and op=='click' and 'search_unknown' in failures:
                error=RuntimeError('SYNTHETIC_SEARCH_ACTION_OUTCOME_UNKNOWN')
                error.details={'action_attempted':True,'outcome_unknown':True};raise error
            if phase=='input' and op=='set_text' and 'input_unknown' in failures:
                error=RuntimeError('SYNTHETIC_INPUT_ACTION_OUTCOME_UNKNOWN')
                error.details={'action_attempted':True,'outcome_unknown':True};raise error
            helper={'protocol':qa.PROTOCOL,'op':op,'nonce':nonce,'self_uid':base.HELPER_UID,'ok':True,
                'error':None,'secondary_errors':[],'ui_automation_connected':op!='state',
                'restoration':{'service_info_verified':True}}
            if op=='state':
                helper['state']=copy.deepcopy(state)
                if ((phase=='search' and 'search_state_changed' in failures) or
                    (phase=='input' and 'input_state_changed' in failures) or
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
                elif phase=='input':tree=editor_fixture(input_mode,typed_value[0])
                else:tree=editor_fixture(post_editor_mode,typed_value[0] if post_value is None else post_value)
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
                    helper.update(node_action='ACTION_SET_TEXT' if op=='set_text' else 'ACTION_CLICK',
                        node_action_returned=not((phase=='search' and 'search_ack_unqualified' in failures) or
                            (phase=='input' and 'input_ack_unqualified' in failures)),
                        action_attempted=True,outcome_unknown=True,inspection_nonce=request['inspection_nonce'],
                        inspection_sha256=request['inspection_sha256'],target_node_sha256=request['node_sha256'],
                        action_window=tree['window'])
                    if op=='set_text':
                        helper.update(target_resource_id=request['node_resource_id'],requested_value_sha256=qa.sha(b'London'),
                            observed_value_sha256=qa.sha(b'Paris' if 'input_readback_mismatch' in failures else b'London'),
                            value_readback_verified=True)
                        if helper['node_action_returned']:typed_value[0]='London'
            value={'helper':helper,'wire_sha256':qa.sha(qa.canonical(helper)),
                'held_transport_returned_after_post_guard':True,'recorder_command_result_sha256':'a'*64,
                'actual_command_returncode':0,'actual_instrumentation_finish_code':-1}
            memory[str(step/(nonce+'.assessment.json'))]=json.dumps(value,sort_keys=True).encode()
            return value
    seam=types.SimpleNamespace(Session=SyntheticIO,validate_plan=adapter.validate_plan)
    session=public.make_session(seam,flow,None,qa,{},base.HELPER_UID,search,click,typing,post,readiness)
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
        public.run_sequences(qa,session,base.INSTALLED,search,click,typing,post,readiness,result,
            lambda seq,plan:base.assessment_summary(types.SimpleNamespace(qa=qa),step,seq,plan),remember)
        session.installed()
        for argv in (context.LIST,context.PATHS):admit(argv,15)
    finally:base.read=original_read;public.time=original_time
    assert sum(op=='click' for op,nonce in calls)<=2 and sum(op=='set_text' for op,nonce in calls)<=1
    assert calls[-1]==('state',post['nonces']['after'])
    if result.get('search_sequence_started'):assert ('state',search['nonces']['after']) in calls
    if result.get('click_sequence_started'):assert ('state',click['nonces']['after']) in calls
    if result.get('input_sequence_started'):assert ('state',typing['nonces']['after']) in calls
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
    assert len(calls)==24 and result['public_london_input_and_readback_completed'] is True
    assert [n for op,n in calls if op=='set_text']==[base.INPUT_PLAN['nonces']['action']]
    assert [n for op,n in calls if op=='click']==[base.SEARCH_PLAN['nonces']['action'],base.PLAN['nonces']['action']]
    assert counts=={'target_uid':2,'target_path':2,'helper_uid':16,'helper_path':16,'stacks':14,'foreground':21,'instrument':24,'click':2,'set_text':1}
    assert commands==74 and result['search_readiness_count']==3 and result['search_readiness_qualified'] is True and all(result[k]['restoration_qualified'] for k in ('search_sequence','sequence','input_sequence','post_sequence'))
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
assert result['error']['message']=='THREE_EXPLICIT_ACKS_AND_INDEPENDENT_SAME_OWNED_TASK_READ_REQUIRED'
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
       'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH,
        'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
        'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}
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
        sp,cp,ip,pp=(copy.deepcopy(plan) for plan in (base.SEARCH_PLAN,base.PLAN,base.INPUT_PLAN,base.POST_PLAN))
        session=public.make_session(probe,None,None,qa,{},base.HELPER_UID,sp,cp,ip,pp,copy.deepcopy(base.SEARCH_READINESS_PLANS))
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
bad_plan=copy.deepcopy(base.INPUT_PLAN)
bad_plan['selector']={'class':'android.widget.EditText','resource_id':qa.PACKAGE+':id/SYNTHETIC_EDITOR'}
bad_plan['value']='usb c cable'
try:adapter.validate_plan(bad_plan,qa)
except RuntimeError as error:assert str(error)=='ONLY_OBSERVED_EXACT_EDIT_RESOURCE_AND_PUBLIC_QUERY'
else:raise AssertionError('old public value enabled')
passed('R4_adapter_rejects_old_unrelated_public_value')
request={'protocol':qa.PROTOCOL,'nonce':'e'*32,'op':'set_text','scope':scope,
    'inspection_nonce':'d'*32,'inspection_sha256':'a'*64,'node_path':'0/0','node_sha256':'b'*64,
    'node_resource_id':qa.PACKAGE+':id/SYNTHETIC_EDITOR','value':'usb c cable'}
try:qa.validate_request(request)
except RuntimeError as error:assert str(error)=='ONLY_FIXED_PUBLIC_SEARCH_QUERY_ALLOWED'
else:raise AssertionError('old query helper protocol enabled')
passed('R4_helper_contract_rejects_old_unrelated_public_value')


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
assert commands==119 and counts=={'target_uid':2,'target_path':2,'helper_uid':26,'helper_path':26,
    'stacks':24,'foreground':36,'instrument':39,'click':2,'set_text':1}
assert len(calls)==39 and sum(op=='click' for op,n in calls)==2 and sum(op=='set_text' for op,n in calls)==1
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
            {'search':base.SEARCH_PLAN,'destination':base.PLAN,'input':base.INPUT_PLAN,'post':base.POST_PLAN,'readiness':plans},
            PurePosixPath('/synthetic/no-files-created'),lambda *a:b'',lambda:{})
    except RuntimeError as error:
        assert str(error)=='EXPLICIT_SEARCH_DESTINATION_LONDON_POST_AND_EIGHT_NO_ACTION_READINESS_PLANS'
    else:raise AssertionError('readiness authority widened')
    passed('readiness_policy_'+label+'_rejected_without_IO')


# Exercise the production Flow and BoundArun constructors, with only in-memory
# target/callback fixtures. No command, held entry, file operation or Main read
# is allowed by these fixtures.
class SyntheticPrivatePath(PurePosixPath):
    def is_dir(self):return True

def typed_scope_fixture():
    return {'schema':'pocket4-current-recorder-scope-v2',
        'current_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
        'package':qa.PACKAGE,'component':qa.PACKAGE+'/.activity.MainActivity',
        'uid':qa.UID,'user':0,'nonce':base.NONCE,'epoch_sha256':qa.MAIN_EPOCH,
        'current_baseline_sha256':qa.MAIN_BASELINE_SHA,
        'current_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
        'amazon_task_source_manifest_sha256':'a'*64,'automatic_retry':False,
        'original_recorder_manifest_sha256':adapter.RECORDER_MANIFEST_SHA,
        'actual_resolution_result_sha256':'b'*64}

def construct_flow(scope):
    accesses=[]
    def forbidden(*args,**kwargs):
        accesses.append('FORBIDDEN_IO')
        raise AssertionError('pure constructor reached command/file/entry')
    root=SyntheticPrivatePath('/synthetic/current-IHG-flow')
    step=root/'steps'/'inspect-01'
    target=types.SimpleNamespace(expected={'pid':42},
        helper_sha256=transport.HELD_HELPER_SHA256,
        verify=lambda:accesses.append('target'),entry=forbidden,close=forbidden)
    recorder=types.SimpleNamespace(write_new=forbidden,
        Flow=types.SimpleNamespace(command=forbidden))
    flow=context.Flow(recorder=recorder,
        contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),
        target=target,environment={key:'/synthetic/non-authority' for key in transport.REQUIRED_ENV},
        transport=transport,main_guard=lambda:accesses.append('Main'),
        root=root,step=step,phase='inspect',scope=scope,
        activation={'framework_epoch':{'binding':{'processes':{'init':{'host_pid':42}}}}},
        tasks={},qa=qa,inspect_plan={'search':base.SEARCH_PLAN,'destination':base.PLAN,
            'input':base.INPUT_PLAN,'post':base.POST_PLAN,'readiness':base.SEARCH_READINESS_PLANS},
        resolve=['synthetic-resolve'],read=forbidden,deadline=context.time.monotonic()+60)
    return flow,accesses

flow,accesses=construct_flow(typed_scope_fixture())
assert not accesses and type(flow.transport) is transport.BoundArun
assert flow.transport.target is flow.target and flow.transport.environment=={
    key:'/synthetic/non-authority' for key in transport.REQUIRED_ENV}
assert flow.current_qualified_scope==flow.scope and flow.current_qualified_scope is not flow.scope
session=adapter.Session(flow,None,qa,{},base.HELPER_UID)
flow.guard()
assert accesses==['Main','target'] and session.uid==base.HELPER_UID
passed('production_typed_Flow_BoundArun_and_R4_Session_positive_without_IO')

for name,mutate,expected in [
    ('old_scope_schema',lambda v:v.update(schema='pocket4-current-recorder-scope-v1'),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_baseline_schema',lambda v:v.update(current_baseline_schema='pocket4-main-current-baseline-v1'),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('foreign_package',lambda v:v.update(package='com.bilibili.app'),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('foreign_target_uid',lambda v:v.update(uid=10117),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('boolean_uid',lambda v:v.update(uid=True),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('boolean_user',lambda v:v.update(user=False),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_epoch',lambda v:v.update(epoch_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_baseline_sha',lambda v:v.update(current_baseline_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_qualification_sha',lambda v:v.update(current_baseline_qualification_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('old_recorder_manifest',lambda v:v.update(original_recorder_manifest_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('legacy_activation_extra',lambda v:v.update(activation_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('foreign_component',lambda v:v.update(component='com.synthetic.foreign/.Main'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
    ('invalid_nonce',lambda v:v.update(nonce='not-a-nonce'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
    ('invalid_task_manifest',lambda v:v.update(amazon_task_source_manifest_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
    ('invalid_resolver_pin',lambda v:v.update(actual_resolution_result_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT')]:
    value=typed_scope_fixture();mutate(value)
    try:construct_flow(value)
    except RuntimeError as error:assert str(error)==expected,(name,str(error))
    else:raise AssertionError(name+' accepted by production Flow')
    passed('production_Flow_'+name+'_rejected_before_transport')

flow,accesses=construct_flow(typed_scope_fixture())
flow.scope['component']=qa.PACKAGE+'/.activity.OtherActivity'
try:flow.guard()
except RuntimeError as error:assert str(error)=='CURRENT_IHG_TASK_SCOPE_CHANGED'
else:raise AssertionError('mutated constructed scope admitted')
assert accesses==[]
passed('constructed_current_scope_mutation_stops_before_Main_target_or_IO')

assert len(cases)==106 and len({x['case'] for x in cases})==106,('control inventory changed',len(cases))

actual_rows={}
assert set(p['actual_install_originals'])=={'coordinator','stage','worker'}
for name,pin in CONTROL_ACTUAL_INSTALL_PINS.items():
    raw_install=p['actual_install_originals'][name].encode('utf-8')
    assert len(raw_install)==pin['bytes'] and hashlib.sha256(raw_install).hexdigest()==pin['sha256']
    actual_rows[name]=json.loads(raw_install)
install_proof=base.actual_install(actual_rows)
assert install_proof['installed']==base.INSTALLED and install_proof['actual_state_wire_sha256']==base.STATE_WIRE
passed('actual_R4_three_originals_through_production_actual_install')

class QualificationBoundaryReached(Exception):pass
saved_verify=base.verify_source;qualification_reads=[]
def before_file_boundary(expected):
    assert expected=='f'*64
    qualification_reads.append('verify_source')
    raise QualificationBoundaryReached()
base.verify_source=before_file_boundary
try:
    try:base.qualified('f'*64)
    except QualificationBoundaryReached:pass
    else:raise AssertionError('production initial qualification did not reach source boundary')
finally:base.verify_source=saved_verify
assert qualification_reads==['verify_source'] and all(type(v) is tuple for v in base.PRIOR.values())
passed('actual_R4_tuple_binding_passes_real_qualified_entry_before_IO')

saved_prior=base.PRIOR;saved_verify=base.verify_source;qualification_reads.clear()
base.PRIOR={**saved_prior,'worker':list(saved_prior['worker'])};base.verify_source=before_file_boundary
try:
    try:base.qualified('f'*64)
    except RuntimeError as error:assert str(error)=='ACTUAL_IHG_INSTALL_BINDING_NOT_READY'
    else:raise AssertionError('JSON array PRIOR passed original tuple gate')
finally:base.PRIOR=saved_prior;base.verify_source=saved_verify
assert qualification_reads==[]
passed('JSON_array_PRIOR_rejected_by_real_qualified_entry_before_IO')


public.validate_pending_input_plan(qa,copy.deepcopy(base.INPUT_PLAN))
assert set(base.INPUT_PLAN)=={'schema','operation','value','nonces'} and 'selector' not in base.INPUT_PLAN
passed('London_pending_spec_has_no_node_or_resource_authority')
for label,change in [
    ('preset_selector',{'selector':{'class':'android.widget.EditText','resource_id':qa.PACKAGE+':id/SYNTHETIC_EDITOR_A'}}),
    ('different_value',{'value':'Paris'}),
    ('duplicate_nonce',{'nonces':dict(base.INPUT_PLAN['nonces'],action=base.INPUT_PLAN['nonces']['inspect'])})]:
    plan=copy.deepcopy(base.INPUT_PLAN);plan.update(change)
    try:public.validate_pending_input_plan(qa,plan)
    except RuntimeError:pass
    else:raise AssertionError('invalid pending input spec accepted: '+label)
    passed('London_pending_spec_'+label+'_rejected')

for mode in ["ready","fresh_different_resource","description_label","chinese_label","ancestor_at_six"]:
    tree=editor_fixture(mode)
    selector,selected,proof=public.destination_editor_selector(qa,tree)
    assert selector['class']=='android.widget.EditText' and selector['resource_id'].startswith(qa.PACKAGE+':id/')
    assert selected==qa.select_unique_editable(tree,selector)
    assert proof['complete_tree_verified'] is True and proof['historical_node_task_or_resource_used_as_authority'] is False
    assert proof['container_eligible_editor_count']==1 and proof['finite_ancestor_limit']==6
    assert not any(key in proof for key in ('resource_id','node_path','bounds','text'))
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(proof)
    plan=copy.deepcopy(base.INPUT_PLAN);plan['selector']=selector
    adapter.validate_plan(plan,qa)
    passed('London_fresh_editor_'+mode+'_production_selector_and_plan')

for mode in ["missing_editor","duplicate_editor","password_editor","not_editable","no_set_text","wrong_editor_class","foreign_resource","truncated_resource","bad_resource_digest","resource_too_long","missing_label","duplicate_label","other_public_role","bad_editor_geometry","bad_parent_geometry","wrong_parent_class","missing_parent","partial","foreign_window","bad_tree_digest","wrong_child_count","ancestor_at_seven"]:
    try:public.destination_editor_selector(qa,editor_fixture(mode))
    except RuntimeError:pass
    else:raise AssertionError('unqualified editor accepted: '+mode)
    passed('London_fresh_editor_'+mode+'_rejected_without_input')

_,_,before_proof=public.destination_editor_selector(qa,editor_fixture())
observed=public.destination_input_readback(qa,editor_fixture(value='London'),before_proof)
assert observed['current_public_destination_input_and_independent_read_verified'] is True
assert observed['fixed_public_value']=='London' and observed['hotel_search_results_verified'] is False
passed('London_independent_current_editor_value_positive')
for label,tree in [
    ('wrong_value',editor_fixture(value='Paris')),
    ('truncated_value',editor_fixture('truncated_text','London')),
    ('changed_resource',editor_fixture('fresh_different_resource','London'))]:
    try:public.destination_input_readback(qa,tree,before_proof)
    except RuntimeError:pass
    else:raise AssertionError('bad independent value accepted: '+label)
    passed('London_independent_'+label+'_rejected')

for fault,reason in [
    ('input_input','SYNTHETIC_HELPER_input_input'),
    ('input_after_state','SYNTHETIC_HELPER_input_after_state'),
    ('input_unknown','SYNTHETIC_INPUT_ACTION_OUTCOME_UNKNOWN'),
    ('input_ack_unqualified','ACTUAL_CURRENT_SEARCH_CLICK_ACK_REQUIRED'),
    ('input_state_changed','POST_TERMINATION_ACCESSIBILITY_STATE_CHANGED'),
    ('input_readback_mismatch','ACTUAL_PUBLIC_LONDON_INPUT_READBACK')]:
    result,calls,counts,commands,session=exercise(failures=(fault,))
    assert result['error']['message']==reason,(fault,result['error'])
    assert result['error']['phase']=='public_destination_set_text'
    assert result['destination_sequence_qualified'] and result['input_sequence_started']
    assert result['post_inspection_completed'] and not result.get('public_london_input_and_readback_completed')
    assert sum(op=='click' for op,n in calls)==2 and sum(op=='set_text' for op,n in calls)==1
    assert ('state',base.INPUT_PLAN['nonces']['after']) in calls
    assert result['failed_input_sequence'] is not result['post_sequence']
    passed('London_'+fault+'_first_error_restoration_and_no_replay')

result,calls,counts,commands,session=exercise(changed_input_task=True)
assert result['error']['message']=='QUALIFIED_DESTINATION_AND_FRESH_SAME_TASK_EDITOR_INSPECTION_REQUIRED'
assert not any(op=='set_text' for op,n in calls) and result['post_inspection_completed']
passed('London_changed_owned_task_rejected_before_input')
result,calls,counts,commands,session=exercise(changed_window_phase='input')
assert result['error']['message']=='ORIGINAL_ACTIVITY_OR_WINDOW_CHANGED_AFTER_INSPECT'
assert not any(op=='set_text' for op,n in calls) and result['post_inspection_completed']
passed('London_original_foreground_guard_before_input')
result,calls,counts,commands,session=exercise(failures=('input_unknown','post_inspect'))
assert result['error']['message']=='SYNTHETIC_INPUT_ACTION_OUTCOME_UNKNOWN'
assert [x['message'] for x in result['secondary_errors']]==['SYNTHETIC_HELPER_post_inspect']
assert sum(op=='set_text' for op,n in calls)==1 and not result.get('public_london_input_and_readback_completed')
passed('London_unknown_input_primary_not_overwritten_by_independent_post')
result,calls,counts,commands,session=exercise(post_value='Paris')
assert result['error']['message']=='INDEPENDENT_PUBLIC_LONDON_VALUE_READBACK_REQUIRED'
assert result['post_inspection_completed'] and not result.get('public_london_input_and_readback_completed')
passed('London_ACK_cannot_replace_independent_value_observation')
result,calls,counts,commands,session=exercise()
before=len(calls)
try:session.instrument(copy.deepcopy(session._action_bindings['input']))
except RuntimeError as error:assert str(error)=='ONE_EXPLICIT_FRESH_REQUEST_PER_PUBLIC_ROLE_REQUIRED'
else:raise AssertionError('input replay admitted')
assert len(calls)==before
passed('London_input_replay_rejected_before_IO')

# Isolate exact input binding with qualified synthetic prior phases; the full
# state/inspect/action/after composition is exercised by exercise() above.
for field,bad in [('value','Paris'),('node_resource_id',qa.PACKAGE+':id/OTHER_EDITOR')]:
    accesses=[]
    class InputProbeBase:
        def __init__(self,*args):pass
        def instrument(self,value):
            accesses.append(value['op']);assert value['op']=='inspect','bad input reached I/O'
            tree=editor_fixture()
            return {'helper':{'inspection':tree,'tree_observations':tree_counts(tree,'inspect')},'wire_sha256':'b'*64}
    probe=types.SimpleNamespace(Session=InputProbeBase,validate_plan=adapter.validate_plan)
    sp,cp,ip,pp=(copy.deepcopy(plan) for plan in (base.SEARCH_PLAN,base.PLAN,base.INPUT_PLAN,base.POST_PLAN))
    session=public.make_session(probe,None,None,qa,{},base.HELPER_UID,sp,cp,ip,pp,copy.deepcopy(base.SEARCH_READINESS_PLANS))
    session.destination_sequence_qualified=True;session.search_sequence_qualified=True
    session.search_owned_task={'task':4321};session.sequence_observation={'owned_task':{'task':4321}}
    session.action_requests_admitted={'search','destination'}
    session.instrument({'protocol':qa.PROTOCOL,'op':'inspect','nonce':ip['nonces']['inspect'],'scope':scope})
    request=copy.deepcopy(session._action_bindings['input']);request[field]=bad
    before=len(accesses)
    try:session.instrument(request)
    except RuntimeError as error:assert str(error)=='EXACT_FRESH_PUBLIC_ROLE_NODE_REQUEST_REQUIRED'
    else:raise AssertionError('changed fresh input binding accepted')
    assert len(accesses)==before and session.action_requests_admitted=={'search','destination'}
    passed('London_changed_input_'+field+'_rejected_before_IO')

assert [x['case'] for x in cases[109:]]==["London_pending_spec_has_no_node_or_resource_authority","London_pending_spec_preset_selector_rejected","London_pending_spec_different_value_rejected","London_pending_spec_duplicate_nonce_rejected","London_fresh_editor_ready_production_selector_and_plan","London_fresh_editor_fresh_different_resource_production_selector_and_plan","London_fresh_editor_description_label_production_selector_and_plan","London_fresh_editor_chinese_label_production_selector_and_plan","London_fresh_editor_ancestor_at_six_production_selector_and_plan","London_fresh_editor_missing_editor_rejected_without_input","London_fresh_editor_duplicate_editor_rejected_without_input","London_fresh_editor_password_editor_rejected_without_input","London_fresh_editor_not_editable_rejected_without_input","London_fresh_editor_no_set_text_rejected_without_input","London_fresh_editor_wrong_editor_class_rejected_without_input","London_fresh_editor_foreign_resource_rejected_without_input","London_fresh_editor_truncated_resource_rejected_without_input","London_fresh_editor_bad_resource_digest_rejected_without_input","London_fresh_editor_resource_too_long_rejected_without_input","London_fresh_editor_missing_label_rejected_without_input","London_fresh_editor_duplicate_label_rejected_without_input","London_fresh_editor_other_public_role_rejected_without_input","London_fresh_editor_bad_editor_geometry_rejected_without_input","London_fresh_editor_bad_parent_geometry_rejected_without_input","London_fresh_editor_wrong_parent_class_rejected_without_input","London_fresh_editor_missing_parent_rejected_without_input","London_fresh_editor_partial_rejected_without_input","London_fresh_editor_foreign_window_rejected_without_input","London_fresh_editor_bad_tree_digest_rejected_without_input","London_fresh_editor_wrong_child_count_rejected_without_input","London_fresh_editor_ancestor_at_seven_rejected_without_input","London_independent_current_editor_value_positive","London_independent_wrong_value_rejected","London_independent_truncated_value_rejected","London_independent_changed_resource_rejected","London_input_input_first_error_restoration_and_no_replay","London_input_after_state_first_error_restoration_and_no_replay","London_input_unknown_first_error_restoration_and_no_replay","London_input_ack_unqualified_first_error_restoration_and_no_replay","London_input_state_changed_first_error_restoration_and_no_replay","London_input_readback_mismatch_first_error_restoration_and_no_replay","London_changed_owned_task_rejected_before_input","London_original_foreground_guard_before_input","London_unknown_input_primary_not_overwritten_by_independent_post","London_ACK_cannot_replace_independent_value_observation","London_input_replay_rejected_before_IO","London_changed_input_value_rejected_before_IO","London_changed_input_node_resource_id_rejected_before_IO"]
assert len(cases)==157 and len({x['case'] for x in cases})==157,('R4 control inventory changed',len(cases))

# New cell02 receipt checks execute the real production validator. Every Main
# occurrence is changed together, so the full current guard is the rejecting gate.
for name,field,value in [
    ('previous_guard_schema','schema','pocket4-current-main-guard-v1'),
    ('owner_chain_unqualified','authenticated_owner_chain_matches',False),
    ('user_namespace_unqualified','current_user_namespaces_match',False),
    ('executable_root_unqualified','current_executable_and_root_backing_match',False),
    ('previous_baseline_chain_changed','previous_current_baseline_sha256','e'*64),
    ('old_helper_authority_forged','old_helpers_and_tasks_reauthorized',True)]:
    rows=copy.deepcopy(actual_rows)
    changed=copy.deepcopy(rows['worker']['Main_before']);changed[field]=value
    for role,fields in {'worker':('Main_before_lock','Main_before','Main_after'),
                        'coordinator':('Main_before','Main_after'),
                        'stage':('Main_before','Main_after')}.items():
        for key in fields:rows[role][key]=copy.deepcopy(changed)
    try:base.actual_install(rows)
    except RuntimeError as error:
        assert str(error)=='ACTUAL_INSTALL_TYPED_CURRENT_BASELINE_REQUIRED',(name,str(error))
    else:raise AssertionError(name+' accepted by actual_install')
    passed('current_cell02_actual_install_'+name+'_rejected')

def cell02_scope_candidate(baseline):
    ref=types.SimpleNamespace(current_baseline=lambda:copy.deepcopy(baseline),
        EPOCH=qa.MAIN_EPOCH,BASELINE_SHA=qa.MAIN_BASELINE_SHA,
        QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA)
    return base.scope_record(types.SimpleNamespace(ref=ref,adapter=adapter),'a'*64)

current_baseline_fixture={'schema':qa.MAIN_BASELINE_SCHEMA,'kind':'current-cell-generation',
    'deployment_performed':False,'framework_exit_cause_resolved':False,'whole_app_production_ready':False,
    'framework_epoch':{'sha256':qa.MAIN_EPOCH},'packages':{qa.PACKAGE:qa.UID}}
current_scope=cell02_scope_candidate(current_baseline_fixture)
assert current_scope==context.current_task_scope(current_scope,qa,
    types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA))
assert current_scope['schema']=='pocket4-current-recorder-scope-v2'
passed('current_cell02_real_scope_record_and_current_task_scope_positive')
for name,field,value in [
    ('wrong_generation_kind','kind','unrelated-generation'),
    ('forged_deployment','deployment_performed',True)]:
    baseline=copy.deepcopy(current_baseline_fixture);baseline[field]=value
    try:cell02_scope_candidate(baseline)
    except RuntimeError as error:
        assert str(error)=='CURRENT_TYPED_OWN_TARGET_SCOPE_REQUIRED',(name,str(error))
    else:raise AssertionError(name+' accepted by scope_record')
    passed('current_cell02_scope_record_'+name+'_rejected')
assert len(cases)==166 and len({x['case'] for x in cases})==166,('R4 current cell02 control inventory changed',len(cases))
for row in run_task_discovery_route_controls(context,base,qa):passed(row['name'])
assert len(cases)==169 and len({x['case'] for x in cases})==169,('current discovery route inventory changed',len(cases))


# Exact current protocol remains a production admission gate. The old helper
# view is synthetic; it grants no node authority and makes no I/O request.
old_input_protocol=types.SimpleNamespace(PROTOCOL='pocket4-owned-ihg-qa-v3',
    PUBLIC_SEARCH_QUERY=qa.PUBLIC_SEARCH_QUERY,nonce=qa.nonce)
try:public.validate_pending_input_plan(old_input_protocol,copy.deepcopy(base.INPUT_PLAN))
except RuntimeError as error:
    assert str(error)=='EXACT_NODE_UNBOUND_PUBLIC_LONDON_INPUT_SPECIFICATION',str(error)
else:raise AssertionError('previous R3 input protocol accepted')
passed('London_previous_R3_protocol_rejected_by_production_pending_input_validator')
assert len(cases)==170 and len({x['case'] for x in cases})==170,('R4 exact input protocol inventory changed',len(cases))

out={'schema':1,'ok':True,'state':'IHG_R4_CURRENT_SEARCH_DESTINATION_LONDON_PURE_CONTROLS_PASS','controls':cases,
 'control_count':len(cases),'template_source_pins':TEMPLATE_PINS,'bound_source_pins':BOUND_PINS,
 'control_stdin_sha256':hashlib.sha256(raw).hexdigest(),
 'bound_coordinator_sha256':BOUND_PINS['coordinator']['sha256'],'bound_stage_sha256':BOUND_PINS['stage']['sha256'],
 'original_Session_sequence_and_real_contract_summary_and_policy_executed':True,
 'all_template_and_bound_python_compile':True,'synthetic_in_memory_IO_only':True,'real_Java_helper_executed':False,
 'file_writes':0,'Android_actions':0,'device_or_child_process_commands':0,'fresh_nonce_values':pool,
 'nonce_material_is_prior_actual_not_regenerated':True,'nonce_values_disjoint_all_fixed_prior_literals':not bool(set(pool)&set(old)),
 'nonce_exclusion_count':len(old),'production_Flow_and_BoundArun_constructors_executed':True,
 'production_typed_constructor_controls':17,'current_cell02_install_and_scope_controls':9,'current_owner_task_route_controls':3,'current_public_input_protocol_controls':1,'actual_prior_install_validator_executed':True,'production_qualified_initial_admission_executed':True,'actual_install_validation_performs_no_IO':True,'actual_Main_and_target_callbacks':False,
 'maximum_readiness_sequences':8,'readiness_qualification_seconds':20,'minimum_consecutive_samples':3,
 'minimum_capture_span_ms':4000,'success_durable_commands_formula':'47+9*k; 3<=k<=8',
 'maximum_success_durable_commands':119,'maximum_helper_nonces':39,'maximum_click_actions':2,'maximum_set_text_actions':1,'fixed_public_input':'London',
 'old_successful_click_outcome_unknown_preserved':True,'actual_UI_readiness_verified':False,'actual_destination_input_verified':False,
 'live_Main_identity_validated':False,'runtime_flow_dispatched':False,'whole_app_production_ready':False}
encoded=json.dumps(out,sort_keys=True,separators=(',',':'))
assert len(encoded.encode())<=32768
print(encoded,flush=True)
