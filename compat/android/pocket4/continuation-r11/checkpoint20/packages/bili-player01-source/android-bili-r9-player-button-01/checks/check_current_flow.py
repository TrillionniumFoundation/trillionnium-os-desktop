"""Pure R9 flow compile/guard correspondence and current-scope callback controls."""
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
    need(set(payload)=={'old_files','new_files','qa_source','pins','binding_proof'},
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
    need(len(rows)==9 and len({x['name'] for x in rows})==9,'EXACT_NINE_CURRENT_FLOW_CONTROLS')
    return {'schema':'pocket4-bili-r9-current-flow-source-controls-v1','all_passed':True,
            'count':9,'cases':rows,'unchanged_function_bodies':unchanged,
            'compiled_runtime_sources_per_revision':6,'helper_contract_compiled':True,
            'synthetic_callback_scenarios':4,'fixture_is_not_Android_evidence':True,
            'source_only':True,'filesystem_operations':0,'children':0,'Android_commands':0,
            'App_launches':0,'UI_actions':0,'actual_nonce_values_only_read_as_data':True,
            'whole_app_production_ready':False}
