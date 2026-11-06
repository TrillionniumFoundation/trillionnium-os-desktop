"""Pure R9 protocol closure, real production plan validators, and original scope controls."""
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
    need(pins['qa']=={'bytes':len(qa_raw),'sha256':sha(qa_raw)},'ACTUAL_R9_QA_PIN')
    adapter_raw=payload['adapter_source'].encode('utf-8')
    need(pins['adapter']=={'bytes':len(adapter_raw),'sha256':sha(adapter_raw)},'ACTUAL_R9_ADAPTER_PIN')
    need(set(payload['failed01_validators'])=={'controls_reveal.py','playback_controls.py'},'EXACT_FAILED01_VALIDATOR_SET')
    for name,source in payload['failed01_validators'].items():
        raw=source.encode('utf-8')
        need(pins['failed01_validators'][name]=={'bytes':len(raw),'sha256':sha(raw)},'FAILED01_VALIDATOR_PIN')
    yes('two_exact_six_file_closures_compile')
    class Names(ast.NodeTransformer):
        def visit_Name(self,node):
            if node.id=='R4_MANIFEST':
                node.id='R5_MANIFEST'
            return node
        def visit_Attribute(self,node):
            self.generic_visit(node)
            if node.attr=='R4_MANIFEST':
                node.attr='R5_MANIFEST'
            return node
        def visit_Constant(self,node):
            if isinstance(node.value,str):
                node.value=node.value.replace('R8 ','R9 ').replace('ACTUAL_R8','ACTUAL_R9').replace('INSTALL02_R4','INSTALL02_R5').replace('owned_bili_r4_session','owned_bili_r5_session')
                if node.value=='pocket4-owned-bili-qa-v8':node.value='pocket4-owned-bili-qa-v9'
                if node.value=='EXACT_R8_REVEAL_PROTOCOL_REQUIRED':node.value='EXACT_R9_REVEAL_PROTOCOL_REQUIRED'
                if node.value=='EXACT_R8_TWO_LABEL_TRANSITIONS_REQUIRED':node.value='EXACT_R9_TWO_LABEL_TRANSITIONS_REQUIRED'
            return node
    changed={'owned_navigation.py':{'require_actual_install_binding','actual_install','execute'},
             'post_foreground.py':{'validate','observe_post_ack'},
             'stage_execute.py':{'main'}}
    unchanged=[]
    for name in sorted(old):
        old_funcs={x.name:x for x in ast.parse(old[name]).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
        new_funcs={x.name:x for x in ast.parse(new[name]).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
        need(set(old_funcs)==set(new_funcs),'TOP_LEVEL_FUNCTION_SET_CHANGED')
        for fn in old_funcs:
            if fn in changed.get(name,set()):
                continue
            a=Names().visit(copy.deepcopy(old_funcs[fn]))
            need(ast.dump(a,include_attributes=False)==ast.dump(new_funcs[fn],include_attributes=False),
                 'UNCHANGED_BUSINESS_GUARD_AST:'+name+':'+fn)
            unchanged.append(name+':'+fn)
    need(len(unchanged)==52,'ORIGINAL_FIFTY_TWO_GUARD_FUNCTIONS')
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
    qa=types.ModuleType('pure_actual_r9_qa');qa.__file__='<qa_contract.py>'
    exec(compile(payload['qa_source'],qa.__file__,'exec'),qa.__dict__)
    # Extract exact production pure constants/functions; exclude HERE.resolve()
    # and all file/device entrypoints rather than executing a flow module.
    wanted={'SELF','UID','STATE_COMMAND_INDEX','STATE_COMMAND_SHA','OLD_STATE_WIRE',
            'EXPECTED_INSTALLED_IDENTITY','INSTALL_RECORDS','MAIN_EPOCH','R5_MANIFEST'}
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
         nav.R5_MANIFEST==payload['binding_proof']['host_manifest_sha256'],
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
    yes('post_ack_callback_constructs_actual_R9_scope')
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
    adapter=pure_module(payload['adapter_source'],'actual_r9_adapter')
    full=pure_module(new['owned_navigation.py'],'actual_r9_owned_navigation')
    need(adapter.SELF==qa.SELF==full.SELF=='org.droidloom.qa.bili.r9' and
         qa.PROTOCOL=='pocket4-owned-bili-qa-v9' and
         adapter.RECORDER_MANIFEST_SHA==full.R5_MANIFEST,'ACTUAL_CURRENT_COMPONENT_PROTOCOL_CLOSURE')
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
    yes('all_complete_base_plans_pass_actual_R9_adapter_validator')
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
    yes('actual_reveal_validate_accepts_R9_protocol_and_complete_current_plan')
    used_reveal=used_video+[n for p in (extension.reveal.REVEAL_PLAN,extension.reveal.POST_PLAN)
        for n in p['nonces'].values()]
    extension.playback.validate(adapter,qa,used_reveal)
    yes('actual_playback_validate_accepts_R9_protocol_and_two_complete_transitions')
    extension.first_click.validate(adapter,qa,first)
    yes('actual_first_search_validate_accepts_same_fresh_current_plan')
    all_values=used_reveal+[n for row in extension.playback.PAIRS for p in (row['action'],row['post'])
        for n in p['nonces'].values()]
    need(len(all_values)==len(set(all_values))==146 and full.OLD_STATE_NONCE not in all_values,
         'ALL_146_COMPONENT_NONCES_MUST_BE_DISTINCT')
    need(not any("pocket4-owned-bili-qa-v8" in source or "EXACT_R8_" in source for source in new.values()),
         'NO_OLD_VERSION_ADMISSION_LITERAL_REMAINS')
    yes('all_146_component_nonces_and_current_protocol_boundary_qualified')
    old_qa=types.ModuleType('old_protocol_view')
    old_qa.__dict__.update(qa.__dict__);old_qa.PROTOCOL='pocket4-owned-bili-qa-v8'
    for name,call,expected_error in [
        ('reveal',lambda:extension.reveal.validate(adapter,old_qa,used_video),'EXACT_R9_REVEAL_PROTOCOL_REQUIRED'),
        ('playback',lambda:extension.playback.validate(adapter,old_qa,used_reveal),'EXACT_R9_TWO_LABEL_TRANSITIONS_REQUIRED'),
        ('production_chain',lambda:full.video_extension(expected,adapter,old_qa),'EXACT_R9_REVEAL_PROTOCOL_REQUIRED')]:
        try:call()
        except qa.ProtocolError as error:need(str(error)==expected_error,'EXPECTED_OLD_PROTOCOL_REJECTION:'+name)
        else:raise RuntimeError('OLD_PROTOCOL_ACCEPTED:'+name)
        yes('actual_'+name+'_rejects_old_protocol_before_any_Android_IO')
    try:qa.validate_request({'protocol':'pocket4-owned-bili-qa-v8','op':'state','nonce':full.POST_PLAN['nonces']['before']})
    except qa.ProtocolError as error:need(str(error)=='PROTOCOL_REQUIRED','OLD_WIRE_PROTOCOL_REJECTION')
    else:raise RuntimeError('OLD_WIRE_PROTOCOL_ACCEPTED')
    yes('actual_R9_wire_contract_rejects_old_protocol')
    for name,used,reason in [
        ('controls_reveal.py',used_video,'EXACT_R8_REVEAL_PROTOCOL_REQUIRED'),
        ('playback_controls.py',used_reveal,'EXACT_R8_TWO_LABEL_TRANSITIONS_REQUIRED')]:
        previous=pure_module(payload['failed01_validators'][name],'failed01_'+name[:-3])
        try:previous.validate(adapter,qa,used)
        except qa.ProtocolError as error:need(str(error)==reason,'EXACT_FAILED01_LITERAL_REPRODUCTION')
        else:raise RuntimeError('FAILED01_VERSION_DEFECT_NOT_REPRODUCED')
    yes('failed01_component_literal_defects_reproduced_without_runtime_or_replay')
    need(len(rows)==21 and len({x['name'] for x in rows})==21,'EXACT_TWENTY_ONE_CURRENT_FLOW_CONTROLS')
    return {'schema':'pocket4-bili-r9-player02-component-controls-v1','all_passed':True,
            'count':21,'cases':rows,'unchanged_function_bodies':unchanged,
            'compiled_runtime_sources_per_revision':6,'helper_contract_compiled':True,'helper_adapter_compiled':True,
            'original_current_scope_controls':9,'additional_production_validator_controls':12,
            'production_source_closure_and_video_extension_executed_in_memory':True,
            'production_plan_validators_executed':['base','video','reveal','playback','first_search'],
            'original_52_function_guards_preserved_with_two_exact_protocol_literal_updates':True,
            'source_map_memory_reads':len(memory_reads),'issued_nonce_values_only_validation_data':True,
            'synthetic_callback_scenarios':4,'fixture_is_not_Android_evidence':True,
            'source_only':True,'filesystem_operations':0,'children':0,'Android_commands':0,
            'App_launches':0,'UI_actions':0,'actual_nonce_values_only_read_as_data':True,
            'whole_app_production_ready':False}
