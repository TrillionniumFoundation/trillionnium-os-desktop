"""Pure R10 complete protocol validators and current discovery route controls."""
import ast
import copy
import hashlib
import json
import types

def need(ok, code):
    if not ok:
        raise RuntimeError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def run_controls(payload):
    need(set(payload)=={'old_files','new_files','qa_source','adapter_source','failed01_validators','pins','binding_proof'},
         'EXACT_CURRENT_FLOW_CONTROL_INPUT')
    rows=[]
    def yes(name):
        rows.append({'name':name,'passed':True})
    old=payload['old_files'];new=payload['new_files'];pins=payload['pins']
    need(set(old)==set(new)=={'owned_navigation.py','stage_execute.py','video_navigation.py',
         'controls_reveal.py','playback_controls.py','post_foreground.py'},
         'ORIGINAL_SIX_RUNTIME_CLOSURE')
    for group,files in (('old',old),('new',new)):
        for name,source in files.items():
            raw=source.encode('utf-8')
            need(pins[group][name]=={'bytes':len(raw),'sha256':sha(raw)},'SOURCE_PIN')
            compile(source,'<'+group+'/'+name+'>','exec')
    qa_raw=payload['qa_source'].encode('utf-8')
    need(pins['qa']=={'bytes':len(qa_raw),'sha256':sha(qa_raw)},'ACTUAL_R10_QA_PIN')
    adapter_raw=payload['adapter_source'].encode('utf-8')
    need(pins['adapter']=={'bytes':len(adapter_raw),'sha256':sha(adapter_raw)},'ACTUAL_R10_ADAPTER_PIN')
    need(set(payload['failed01_validators'])=={'controls_reveal.py','playback_controls.py'},'EXACT_FAILED01_VALIDATOR_SET')
    for name,source in payload['failed01_validators'].items():
        raw=source.encode('utf-8')
        need(pins['failed01_validators'][name]=={'bytes':len(raw),'sha256':sha(raw)},'FAILED01_VALIDATOR_PIN')
    yes('two_exact_six_file_closures_compile')
    class Names(ast.NodeTransformer):
        def visit_Name(self,node):
            if node.id=='R5_MANIFEST':node.id='R6_MANIFEST'
            return node
        def visit_Attribute(self,node):
            self.generic_visit(node)
            if node.attr=='R5_MANIFEST':node.attr='R6_MANIFEST'
            return node
        def visit_Constant(self,node):
            if isinstance(node.value,str):
                node.value=node.value.replace('R9','R10').replace('INSTALL02_R5','INSTALL02_R6')
                node.value=node.value.replace('owned_bili_r5_session','owned_bili_r6_session')
                if node.value=='pocket4-owned-bili-qa-v9':node.value='pocket4-owned-bili-qa-v10'
            return node
        def visit_List(self,node):
            self.generic_visit(node)
            if len(node.elts)>=2 and isinstance(node.elts[0],ast.Constant) and node.elts[0].value=='/usr/bin/python3' and isinstance(node.elts[1],ast.Constant) and node.elts[1].value=='-I':
                if len(node.elts)<3 or not isinstance(node.elts[2],ast.Constant) or node.elts[2].value!='-B':
                    node.elts.insert(2,ast.Constant(value='-B'))
            return node
    changed={'owned_navigation.py':{'require_actual_install_binding','actual_install','execute','worker','main'},
             'post_foreground.py':{'validate','observe_post_ack'},
             'stage_execute.py':{'main','checked_packet'}}
    unchanged=[]
    for name in sorted(old):
        old_funcs={x.name:x for x in ast.parse(old[name]).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
        new_funcs={x.name:x for x in ast.parse(new[name]).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
        need(set(new_funcs)==set(old_funcs)|({'cleanup_worker'} if name=='owned_navigation.py' else set()),'EXACT_CURRENT_TOP_LEVEL_FUNCTION_SET')
        for fn in old_funcs:
            if fn in changed.get(name,set()):
                continue
            a=Names().visit(copy.deepcopy(old_funcs[fn]))
            need(ast.dump(a,include_attributes=False)==ast.dump(new_funcs[fn],include_attributes=False),
                 'UNCHANGED_BUSINESS_GUARD_AST:'+name+':'+fn)
            unchanged.append(name+':'+fn)
    need(len(unchanged)==49,'FORTY_NINE_UNCHANGED_GUARDS_PLUS_EXPLICIT_TASK_ROUTE_DELTA')
    yes('unchanged_original_business_and_cleanup_guard_bodies')
    nav_ast=ast.parse(new['owned_navigation.py'])
    execute=next(x for x in nav_ast.body if isinstance(x,ast.FunctionDef) and x.name=='execute')
    strings={x.value for x in ast.walk(execute) if isinstance(x,ast.Constant) and isinstance(x.value,str)}
    attrs={x.attr for x in ast.walk(execute) if isinstance(x,ast.Attribute)}
    need({'--current-baseline','--baseline-sha256'}<=strings and
         not({'--activation-after','--activation-sha256'}&strings) and
         {'BASELINE','BASELINE_SHA'}<=attrs and 'ACTIVATION' not in attrs,
         'EXACT_TYPED_BASELINE_INIT_FLAGS_REQUIRED')
    need("source.PACKAGE" in new['owned_navigation.py'] and "source.COMPONENT" in new['owned_navigation.py'] and
         "ref.PACKAGE" not in new['owned_navigation.py'] and "ref.COMPONENT" not in new['owned_navigation.py'],
         'FIXED_R5_TARGET_SOURCE_REQUIRED')
    yes('current_init_and_fixed_target_source_flags')
    from pathlib import Path
    import re
    post=types.ModuleType('pure_post_foreground');post.__file__='<post_foreground.py>'
    exec(compile(new['post_foreground.py'],post.__file__,'exec'),post.__dict__)
    qa=types.ModuleType('pure_actual_r10_qa');qa.__file__='<qa_contract.py>'
    exec(compile(payload['qa_source'],qa.__file__,'exec'),qa.__dict__)
    # Extract exact production pure constants/functions; exclude HERE.resolve()
    # and all file/device entrypoints rather than executing a flow module.
    wanted={'SELF','UID','STATE_COMMAND_INDEX','STATE_COMMAND_SHA','OLD_STATE_WIRE',
            'EXPECTED_INSTALLED_IDENTITY','INSTALL_RECORDS','MAIN_EPOCH','R6_MANIFEST'}
    body=[]
    found=set()
    for node in nav_ast.body:
        if isinstance(node,ast.Assign):
            names={x.id for target in node.targets for x in ast.walk(target) if isinstance(x,ast.Name)}
            if names & wanted:
                need(names<=wanted,'PURE_NAV_ASSIGNMENT_CLOSURE')
                body.append(copy.deepcopy(node));found.update(names)
        elif isinstance(node,ast.FunctionDef) and node.name in ('require','require_actual_install_binding'):
            body.append(copy.deepcopy(node))
    need(found==wanted,'PURE_NAV_CONSTANTS_COMPLETE')
    nav=types.ModuleType('pure_bound_install_constants')
    nav.__dict__.update(Path=Path,re=re)
    exec(compile(ast.Module(body=body,type_ignores=[]),'<pure-nav-bindings>','exec'),nav.__dict__)
    nav.require_actual_install_binding()
    need(nav.UID==payload['binding_proof']['actual_UID'] and nav.MAIN_EPOCH==qa.MAIN_EPOCH and
         nav.R6_MANIFEST==payload['binding_proof']['host_manifest_sha256'],
         'ACTUAL_INSTALL_CONSTANTS_MUST_MATCH_BINDER')
    yes('actual_bound_install_constants_without_flow_entrypoints')
    counter={'commands':0,'guards':0,'tasks':0}
    task={'task':7,'package':qa.PACKAGE,'synthetic_only':True}
    def make_session(qa_view):
        flow=types.SimpleNamespace(action_attempted=False,_private_backend_transport=False,
                                   transport=types.SimpleNamespace(_sequence=0))
        def guard(**unused):
            counter['guards']+=1
        def android(argv,timeout,**options):
            need(argv==['/system/bin/dumpsys','window','displays'] and timeout==15 and options=={'mutation':False},
                 'SYNTHETIC_FOREGROUND_COMMAND_SHAPE')
            counter['commands']+=1
            flow.transport._sequence+=1
            return b'mCurrentFocus=Window{abc u0 tv.danmaku.bili/com.bilibili.search2.main.BiliMainSearchActivity}\n'
        def task_scope():
            counter['tasks']+=1
            return task
        def forbidden_foreground():
            raise RuntimeError('EXPECTED_POST_ACK_BRANCH_NOT_REACHED')
        flow.guard=guard;flow.android=android
        return types.SimpleNamespace(qa=qa_view,flow=flow,task=task_scope,foreground=forbidden_foreground)
    def result():
        return {'click_acknowledged':True,'after_state_completed':True,'restoration_qualified':True,
                'post_state_matches_before':True,'error':None,'secondary_errors':[],
                'post_termination_state':{'wire_sha256':'a'*64},
                'accessibility_restoration':{'wire_sha256':['a'*64,'b'*64,'a'*64]},
                'inspection_wire_sha256':'c'*64,'foreground_before':{'synthetic_only':True},
                'owned_task':task}
    observed=result()
    accepted=post.observe_post_ack(make_session(qa),post.FIRST_PLAN,observed)
    need(accepted['main_baseline_schema']==qa.MAIN_BASELINE_SCHEMA and
         accepted['main_baseline_sha256']==qa.MAIN_BASELINE_SHA and
         accepted['main_baseline_qualification_sha256']==qa.MAIN_BASELINE_QUALIFICATION_SHA and
         observed['first_search_post_ack_foreground']['first_sample_classification']=='expected_search_focus' and
         counter=={'commands':1,'guards':2,'tasks':2},
         'REAL_POST_ACK_CALLBACK_MUST_CONSTRUCT_NEW_SCOPE')
    yes('post_ack_callback_constructs_actual_R10_scope')
    for field in ('MAIN_BASELINE_SCHEMA','MAIN_BASELINE_SHA','MAIN_BASELINE_QUALIFICATION_SHA'):
        view=types.SimpleNamespace(**{k:getattr(qa,k) for k in
            ('PACKAGE','UID','MAIN_EPOCH','MAIN_BASELINE_SCHEMA','MAIN_BASELINE_SHA','MAIN_BASELINE_QUALIFICATION_SHA','scope')})
        setattr(view,field,'wrong-schema' if field=='MAIN_BASELINE_SCHEMA' else '0'*64)
        try:
            post.observe_post_ack(make_session(view),post.FIRST_PLAN,result())
        except qa.ProtocolError:
            pass
        else:
            raise RuntimeError('WRONG_SCOPE_CALLBACK_ACCEPTED:'+field)
        yes('post_ack_callback_rejects_'+field.lower())
    old_scope={k:v for k,v in accepted.items() if k not in
               ('main_baseline_schema','main_baseline_sha256','main_baseline_qualification_sha256')}
    try:
        qa.scope(old_scope)
    except qa.ProtocolError:
        pass
    else:
        raise RuntimeError('OLD_EPOCH_ONLY_SCOPE_ACCEPTED')
    yes('old_epoch_only_scope_rejected_by_production_protocol')
    need(counter=={'commands':4,'guards':8,'tasks':8},'PURE_CALLBACK_CASE_COUNTS')
    # Production module loading and the exact production video_extension entry
    # run against a bounded in-memory source map. Only read() is an I/O fixture;
    # verify_source(), fixed_plan(), all validate() functions and qa/adapter
    # bodies are the actual candidate sources. No Android entrypoint is called.
    from pathlib import PurePosixPath
    def pure_module(source,name):
        tree=ast.parse(source)
        tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
        m=types.ModuleType(name);m.__file__='<pure-'+name+'>'
        m.HERE=PurePosixPath('/pure-current-source')
        exec(compile(tree,m.__file__,'exec'),m.__dict__)
        return m
    adapter=pure_module(payload['adapter_source'],'actual_r10_adapter')
    full=pure_module(new['owned_navigation.py'],'actual_r10_owned_navigation')
    need(adapter.SELF==qa.SELF==full.SELF=='org.droidloom.qa.bili.r10' and
         qa.PROTOCOL=='pocket4-owned-bili-qa-v10' and
         adapter.RECORDER_MANIFEST_SHA==full.R6_MANIFEST,'ACTUAL_CURRENT_COMPONENT_PROTOCOL_CLOSURE')
    manifest={'schema':1,'files':pins['new']}
    manifest_raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode()
    expected=sha(manifest_raw)
    memory={str(full.HERE/name):source.encode() for name,source in new.items()}
    memory[str(full.HERE/'SOURCE_PINS.json')]=manifest_raw
    memory_reads=[]
    def read_memory(path,maximum=1048576,expected=None,size=None):
        name=str(path);need(name in memory,'NO_SOURCE_OUTSIDE_EXACT_CLOSURE')
        raw=memory[name];memory_reads.append(name)
        need(len(raw)<=maximum and (expected is None or sha(raw)==expected) and
             (size is None or len(raw)==size),'EXACT_MEMORY_SOURCE_PIN')
        return raw
    full.read=read_memory
    first=full.fixed_plan()
    base_plans=[full.PLAN,full.POST_PLAN,full.SET_TEXT_PLAN,full.SUBMIT_PLAN,full.RESULTS_PLAN,
        *full.STABILITY_PLANS,*full.QUERY_STABILITY_PLANS,*full.SUBMIT_STABILITY_PLANS,
        *full.RESULT_OBSERVATION_PLANS]
    for plan in base_plans:adapter.validate_plan(plan,qa)
    need(first==full.PLAN and len(base_plans)==29,'EXACT_BASE_COMPLETE_PLAN_COUNT')
    yes('all_complete_base_plans_pass_actual_R10_adapter_validator')
    extension=full.video_extension(expected,adapter,qa)
    need(extension.first_click.FIRST_PLAN==first and
         extension.reveal.REVEAL_PLAN['operation']=='reveal_controls' and
         [row['action']['transition'] for row in extension.playback.PAIRS]==['pause','resume'],
         'ALL_PRODUCTION_COMPONENT_VALIDATORS_RETURNED')
    yes('production_video_extension_loads_and_validates_all_four_actual_components')
    used_base=[full.NONCE,*[n for p in base_plans for n in p['nonces'].values()]]
    video_plans=[extension.VIDEO_PLAN,*extension.VIDEO_STABILITY_PLANS,
        *extension.VIDEO_POST_PLANS,*extension.CONTENT_READY_PLANS]
    extension.validate(adapter,qa,used_base)
    yes('actual_video_validate_accepts_complete_current_plan')
    used_video=used_base+[n for p in video_plans for n in p['nonces'].values()]
    extension.reveal.validate(adapter,qa,used_video)
    yes('actual_reveal_validate_accepts_R10_protocol_and_complete_current_plan')
    used_reveal=used_video+[n for p in (extension.reveal.REVEAL_PLAN,extension.reveal.POST_PLAN)
        for n in p['nonces'].values()]
    extension.playback.validate(adapter,qa,used_reveal)
    yes('actual_playback_validate_accepts_R10_protocol_and_two_complete_transitions')
    extension.first_click.validate(adapter,qa,first)
    yes('actual_first_search_validate_accepts_same_fresh_current_plan')
    all_values=used_reveal+[n for row in extension.playback.PAIRS for p in (row['action'],row['post'])
        for n in p['nonces'].values()]
    need(len(all_values)==len(set(all_values))==146 and full.OLD_STATE_NONCE not in all_values,
         'ALL_146_COMPONENT_NONCES_MUST_BE_DISTINCT')
    need(not any(any(old in source for old in ("pocket4-owned-bili-qa-v8","pocket4-owned-bili-qa-v9","EXACT_R8_","EXACT_R9_")) for source in new.values()),
         'NO_OLD_VERSION_ADMISSION_LITERAL_REMAINS')
    yes('all_146_component_nonces_and_current_protocol_boundary_qualified')
    old_qa=types.ModuleType('old_protocol_view')
    old_qa.__dict__.update(qa.__dict__);old_qa.PROTOCOL='pocket4-owned-bili-qa-v9'
    for name,call,expected_error in [
        ('reveal',lambda:extension.reveal.validate(adapter,old_qa,used_video),'EXACT_R10_REVEAL_PROTOCOL_REQUIRED'),
        ('playback',lambda:extension.playback.validate(adapter,old_qa,used_reveal),'EXACT_R10_TWO_LABEL_TRANSITIONS_REQUIRED'),
        ('production_chain',lambda:full.video_extension(expected,adapter,old_qa),'EXACT_R10_REVEAL_PROTOCOL_REQUIRED')]:
        try:call()
        except qa.ProtocolError as error:need(str(error)==expected_error,'EXPECTED_OLD_PROTOCOL_REJECTION:'+name)
        else:raise RuntimeError('OLD_PROTOCOL_ACCEPTED:'+name)
        yes('actual_'+name+'_rejects_old_protocol_before_any_Android_IO')
    try:qa.validate_request({'protocol':'pocket4-owned-bili-qa-v9','op':'state','nonce':full.POST_PLAN['nonces']['before']})
    except qa.ProtocolError as error:need(str(error)=='PROTOCOL_REQUIRED','OLD_WIRE_PROTOCOL_REJECTION')
    else:raise RuntimeError('OLD_WIRE_PROTOCOL_ACCEPTED')
    yes('actual_R10_wire_contract_rejects_old_protocol')
    for name,used,reason in [
        ('controls_reveal.py',used_video,'EXACT_R8_REVEAL_PROTOCOL_REQUIRED'),
        ('playback_controls.py',used_reveal,'EXACT_R8_TWO_LABEL_TRANSITIONS_REQUIRED')]:
        previous=pure_module(payload['failed01_validators'][name],'failed01_'+name[:-3])
        try:previous.validate(adapter,qa,used)
        except qa.ProtocolError as error:need(str(error)==reason,'EXACT_FAILED01_LITERAL_REPRODUCTION')
        else:raise RuntimeError('FAILED01_VERSION_DEFECT_NOT_REPRODUCED')
    yes('failed01_component_literal_defects_reproduced_without_runtime_or_replay')
    need(len(rows)==21 and len({x['name'] for x in rows})==21,'EXACT_TWENTY_ONE_CURRENT_FLOW_CONTROLS')

    # The new source route is explicit. Shared R6 modules are neither patched
    # nor substituted. Factory/bind discovery semantics were actual-tested by
    # the separate 27 controls; these cases execute this own cleanup entry.
    worker_function=next(n for n in nav_ast.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    factory_calls=[n for n in ast.walk(worker_function) if isinstance(n,ast.Call) and
        isinstance(n.func,ast.Attribute) and n.func.attr=='current_flow_type']
    need(len(factory_calls)==1 and len(factory_calls[0].args)==2 and
         isinstance(factory_calls[0].args[0],ast.Call) and
         isinstance(factory_calls[0].args[0].func,ast.Attribute) and
         factory_calls[0].args[0].func.attr=='verify_source' and
         isinstance(factory_calls[0].args[0].args[0],ast.Name) and
         factory_calls[0].args[0].args[0].id=='INSTALL_MANIFEST_SHA' and
         not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
                 n.func.attr=='Flow' for n in ast.walk(worker_function)),
         'CURRENT_INSTALLED_FACTORY_MUST_OWN_WORKER_FLOW')
    cleanup=next(n for n in nav_ast.body if isinstance(n,ast.FunctionDef) and n.name=='cleanup_worker')
    need(sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
             n.func.attr=='current_flow_type' for n in ast.walk(cleanup))==1 and
         sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
             n.func.attr=='cleanup' for n in ast.walk(cleanup))==1 and
         not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
                 n.func.attr=='lock_file' for n in ast.walk(cleanup)),
         'CURRENT_CLEANUP_ONCE_WITHOUT_OUTER_ACTION_LOCK')
    cleanup_calls=[n for n in ast.walk(execute) if isinstance(n,ast.Call) and
        isinstance(n.func,ast.Attribute) and n.func.attr=='run_cli' and n.args and
        isinstance(n.args[0],ast.Constant) and n.args[0].value=='04-cleanup']
    need(len(cleanup_calls)==1 and '--cleanup-once' in
         [n.value for n in ast.walk(cleanup_calls[0]) if isinstance(n,ast.Constant)] and
         '--source-manifest-sha256' in [n.value for n in ast.walk(cleanup_calls[0]) if isinstance(n,ast.Constant)] and
         not any(isinstance(n,ast.Constant) and n.value=='recorder.py' for n in ast.walk(cleanup_calls[0])),
         'ORIGINAL_CLEANUP_CHILD_MUST_ROUTE_OWN_CURRENT_ENTRY')
    yes('worker_and_cleanup_paths_use_explicit_current_installed_factory')

    def cleanup_case(mode):
        events=[];printed=[];writes=[]
        class FlowBoundary:
            def __init__(self,args):
                need(args.operation=='cleanup' and args.adapter_manifest_sha256==full.R6_MANIFEST and
                     args.flow_dir==full.FLOW and args.step=='cleanup-01' and
                     args.epoch_module==PurePosixPath('/pure-r6/references/framework_epoch.py') and
                     args.task_source==PurePosixPath('/pure-r6/references/task_scope_baseline.py') and
                     args.request is None,'EXACT_ORIGINAL_CLEANUP_ARGUMENTS')
                self.action_attempted=False;self.step=PurePosixPath('/pure-step')
                self.scope={'epoch_sha256':qa.MAIN_EPOCH};events.append('construct')
            def begin(self,args,mutation):
                need(mutation is True,'CLEANUP_ORIGINAL_MUTATION_INTENT')
                events.append('begin')
                if mode=='begin_fail':raise RuntimeError('PRIMARY_BEGIN')
            def cleanup(self):
                events.append('cleanup');self.action_attempted=True
                if mode in ('cleanup_fail','cleanup_and_close_fail'):raise RuntimeError('PRIMARY_CLEANUP')
                return {'new_leaf_removed_and_verified':True,'other_tasks_preserved':True}
            def guard(self,attempted=False):
                need(attempted is True,'ORIGINAL_ATTEMPTED_FINAL_GUARD')
                events.append('guard')
            def close(self):
                events.append('close')
                if mode in ('close_fail','cleanup_and_close_fail'):raise RuntimeError('SECONDARY_CLOSE')
        recorder=types.SimpleNamespace(now=lambda:'memory-utc',
            write_new=lambda path,result:writes.append((path,copy.deepcopy(result))))
        marker=object()
        def verify(value):
            need(value==full.INSTALL_MANIFEST_SHA,'CURRENT_CLEANUP_INSTALL_SOURCE_PIN')
            events.append('install_source_verify');return marker
        def factory(manifest,recorder_arg):
            need(manifest is marker and recorder_arg is recorder,'EXACT_CURRENT_CLEANUP_FACTORY')
            events.append('current_factory');return FlowBoundary
        prior=types.SimpleNamespace(RECORDER_ROOT=PurePosixPath('/pure-r6'),
            recorder_module=lambda:recorder,verify_source=verify,current_flow_type=factory)
        namespace=dict(full.cleanup_worker.__globals__)
        namespace.update(HERE=full.SOURCE,load_prior=lambda:prior,
            os=types.SimpleNamespace(getuid=lambda:0,geteuid=lambda:0,umask=lambda mode:need(mode==0o077,'ORIGINAL_UMASK')),
            print=lambda value,**unused:printed.append(json.loads(value)))
        run=types.FunctionType(full.cleanup_worker.__code__,namespace)
        code=run(expected)
        need(len(printed)==len(writes)==1 and printed[0]==writes[0][1] and
             writes[0][0]==PurePosixPath('/pure-step/result.json') and events.count('close')==1 and
             events.count('current_factory')==1 and events.count('install_source_verify')==1 and
             events.count('cleanup')==(0 if mode=='begin_fail' else 1),
             'ONCE_CLEANUP_AND_DURABLE_ORIGINAL_RESULT_REQUIRED')
        return code,printed[0],events
    for mode in ('positive','begin_fail','cleanup_fail','close_fail','cleanup_and_close_fail'):
        code,observed,events=cleanup_case(mode)
        if mode=='positive':
            need(code==0 and observed['ok'] is True and observed['outcome_unknown'] is False and
                 observed['action_attempted'] is True and
                 observed['new_leaf_removed_and_verified'] is True,'CLEANUP_POSITIVE_ROUTE')
        else:
            first='PRIMARY_BEGIN' if mode=='begin_fail' else (
                'HELD_BINDING_RELEASE_FAILED' if mode=='close_fail' else 'PRIMARY_CLEANUP')
            need(code==2 and observed['ok'] is False and observed['error']==first and
                 observed['action_attempted']==(mode!='begin_fail') and
                 observed['outcome_unknown']==(mode!='begin_fail'),'ORIGINAL_CLEANUP_FAILURE_AND_UNKNOWN_PRESERVED')
            if mode in ('close_fail','cleanup_and_close_fail'):
                need(observed['release_error_type']=='RuntimeError','ORIGINAL_RELEASE_ERROR_RETAINED')
        yes('production_current_cleanup_entry_'+mode+'_without_Android_IO')

    need(len(rows)==27 and len({x['name'] for x in rows})==27,'EXACT_CURRENT_ROUTE_AND_COMPONENT_CONTROLS')
    return {'schema':'pocket4-bili-r10-current-player-component-controls-v1','all_passed':True,
            'count':27,'cases':rows,'unchanged_function_bodies':unchanged,
            'compiled_runtime_sources_per_revision':6,'helper_contract_compiled':True,'helper_adapter_compiled':True,
            'original_current_scope_controls':9,'additional_production_validator_controls':12,
            'current_factory_and_cleanup_route_controls':6,'route_IO_boundaries_are_memory_only':True,
            'production_source_closure_and_video_extension_executed_in_memory':True,
            'production_plan_validators_executed':['base','video','reveal','playback','first_search'],
            'original_guards_preserved_with_explicit_current_route_and_packet_bound_delta':True,
            'source_map_memory_reads':len(memory_reads),'issued_nonce_values_only_validation_data':True,
            'synthetic_callback_scenarios':4,'fixture_is_not_Android_evidence':True,
            'source_only':True,'filesystem_operations':0,'children':0,'Android_commands':0,
            'App_launches':0,'UI_actions':0,'actual_nonce_values_only_read_as_data':True,
            'whole_app_production_ready':False}
