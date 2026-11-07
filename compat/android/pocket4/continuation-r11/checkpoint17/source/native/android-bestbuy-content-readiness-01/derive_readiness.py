#!/usr/bin/env python3
"""Derive local BestBuy readiness sources; this program has no device calls."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import secrets

BASE = Path('/workspace/scratch/94990735b266')
HERE = Path(__file__).resolve().parent
OLD = BASE/'android-bestbuy-launch-inspect-01'
ROLES = BASE/'android-bestbuy-launch01-public-roles-reader-01/read_roles.py'
CANDIDATE = HERE/'candidate'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=True)+'\n').encode()


def replace_once(source, before, after):
    assert source.count(before) == 1, before[:160]
    return source.replace(before, after)


def function(source, name):
    node = next(x for x in ast.parse(source).body
                if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(source, node)


def assign(source, name, value):
    node = next(x for x in ast.parse(source).body if isinstance(x, ast.Assign)
                and len(x.targets) == 1 and isinstance(x.targets[0], ast.Name)
                and x.targets[0].id == name)
    return replace_once(source, ast.get_source_segment(source, node),
                        name+'='+repr(value))


def main():
    assert not CANDIDATE.exists()
    frozen = json.loads((OLD/'FROZEN_FILES.json').read_bytes())
    for name, wanted in frozen['files'].items():
        assert pin((OLD/name).read_bytes()) == wanted, name
    roles = ROLES.read_text()
    assert pin(roles.encode()) == {
        'bytes': 20038,
        'sha256': 'f72a9bbe1d922d40728381c5bc5138a6238387327cf4c4ff0ec8ee2399396a21'}
    known = {}
    for node in ast.parse(roles).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
            if name in ('PUBLIC_ROLES', 'PUBLIC_RESOURCES', 'PUBLIC_CLASSES'):
                known[name] = ast.literal_eval(node.value)
    nonce = secrets.token_hex(16)
    plans = [{'schema': 1, 'operation': 'inspect',
              'nonces': {phase: secrets.token_hex(16) for phase in ('before', 'inspect', 'after')}}
             for _ in range(3)]
    values = [nonce, *[n for p in plans for n in p['nonces'].values()]]
    assert len(values) == len(set(values)) == 10
    remote = '/home/alex/work/pocket4-bestbuy-owned-content-readiness-01'
    key = 'pocket4-bestbuy-owned-content-readiness-01-20261106'

    readiness = '''"""Counts from complete current inspections, with a 30-second qualification deadline.

Only successful all-zero public catalogs permit a later independent read.
The original Session owns its after-state/finally path even beyond this
qualification deadline. No execution kill, UI input or network operation.
"""
import hashlib
import time

MAX_ROUNDS=3
QUALIFICATION_SECONDS=30.0
ROUND_OFFSETS_SECONDS=(0.0,10.0,20.0)
ERROR_ROLES=('retry','fixed_network_error')
SEMANTIC_RESOURCES=('android:id/search_src_text','com.bestbuy.android:id/search_button',
    'com.bestbuy.android:id/search','com.bestbuy.android:id/search_src_text',
    'com.bestbuy.android:id/country','com.bestbuy.android:id/country_selector',
    'com.bestbuy.android:id/continue_button','com.bestbuy.android:id/btn_continue',
    'com.bestbuy.android:id/skip','com.bestbuy.android:id/continue_as_guest')
'''
    readiness += '\n'.join(name+'='+repr(value) for name, value in known.items())+'\n\n'
    for name in ('need', 'sha', 'no_raw_ui', 'validated_assessment', 'public_role_counts'):
        readiness += function(roles, name)+'\n\n'
    readiness += '''def decision(counts):
    """No target is selected; generic buttons and error labels never grant readiness."""
    roles=counts['fixed_public_role_queries']
    resources=counts['fixed_public_resource_queries']
    need(set(roles)==set(PUBLIC_ROLES) and set(resources)==set(PUBLIC_RESOURCES),
         'EXACT_PUBLIC_CATALOG_COUNTS_REQUIRED')
    all_zero=all(row['matching_visible_nonpassword_nodes']==0 for row in roles.values()) and all(
        row['matching_nodes']==0 for row in resources.values())
    errors=any(roles[name]['matching_visible_nonpassword_nodes']>0 for name in ERROR_ROLES)
    actionable_roles=[name for name in PUBLIC_ROLES if name not in ERROR_ROLES and
        roles[name]['distinct_self_or_direct_parent_candidates']>0]
    # An editable flag alone is not used as proof of an actionable public entry.
    actionable_resources=[name for name in SEMANTIC_RESOURCES if resources[name]['eligible_clickable_nodes']>0]
    candidate=bool(not errors and (actionable_roles or actionable_resources))
    reason=('ACTIONABLE_PUBLIC_ENTRY_OR_ONBOARDING' if candidate else
        'PUBLIC_ERROR_OR_RETRY_PRESENT' if errors else
        'COMPLETE_PUBLIC_CATALOG_ALL_ZERO' if all_zero else
        'PUBLIC_CATALOG_NONZERO_WITHOUT_ACTIONABLE_ENTRY')
    return {'catalog_all_zero':all_zero,'public_error_or_retry_present':errors,
        'public_entry_candidate_present':candidate,'reason':reason,
        'actionable_fixed_public_roles':actionable_roles,
        'actionable_fixed_public_resources':actionable_resources,
        'target_selected':False,'input_action_authority':False,
        'business_success_verified':False,'whole_app_production_ready':False}


def qualify_current(qa,assessed,sequence,plan,metadata,owned_task,installed):
    """Rebind the retained current assessment to its just-completed original Session."""
    need(sequence.get('owned_task')==owned_task and
         sequence.get('installed_before')==sequence.get('installed_after')==installed and
         sequence.get('error') is None and sequence.get('secondary_errors')==[] and
         sequence.get('foreground_before')==sequence.get('foreground_after') and
         sequence.get('after_state_completed') is True and sequence.get('restoration_qualified') is True and
         sequence.get('post_state_matches_before') is True and
         sequence['post_termination_state']['nonce']==plan['nonces']['after'] and
         sequence['post_termination_state']['helper_uid']==10198 and
         sequence['post_termination_state']['ui_automation_connected'] is False,
         'CURRENT_COMPLETE_ORIGINAL_SESSION_SAME_TASK_REQUIRED')
    need(set(metadata)=={'before','inspect','after'} and all(
         metadata[name]['nonce']==plan['nonces'][name] for name in metadata),
         'CURRENT_ROUND_ASSESSMENT_NONCES_REQUIRED')
    wire=sequence['inspection_wire_sha256']
    helper,inspection,window,counters=validated_assessment(qa,assessed,
        plan['nonces']['inspect'],wire,sequence['foreground_after'])
    summary=metadata['inspect']
    restore=sequence['accessibility_restoration']
    need(helper['accessibility_state_before_connection']==restore['state_before']==restore['state_after']==
         sequence['post_termination_state']['state'] and
         restore['wire_sha256']==[metadata[name]['wire_sha256'] for name in ('before','inspect','after')] and
         inspection['tree_sha256']==summary['tree_sha256'] and
         inspection['window_sha256']==summary['window_sha256'] and
         len(inspection['nodes'])==summary['node_count'] and
         window==summary['window_observation'] and counters==summary['tree_observations'] and
         assessed['recorder_command_result_sha256']==summary['recorder_command_result_sha256'],
         'CURRENT_ASSESSMENT_TREE_WIRE_STATE_AND_COMMAND_BINDING_REQUIRED')
    counts=public_role_counts(qa,inspection)
    public=decision(counts)
    row={'sequence':sequence,'assessments':metadata,'public_role_counts':counts,
         'public_decision':public,'complete_current_assessment_verified':True,
         'raw_UI_tree_private_only':True,'business_success_verified':False,
         'whole_app_production_ready':False}
    no_raw_ui(row)
    return row


def observation_record():
    return {'maximum_rounds':MAX_ROUNDS,'qualification_window_seconds':QUALIFICATION_SECONDS,
        'round_offsets_seconds':list(ROUND_OFFSETS_SECONDS),'rounds':[],
        'rounds_started':0,'completed_rounds':0,'public_entry_candidate_present':False,
        'qualification_deadline_is_not_execution_kill':True,
        'original_after_state_and_finally_retained':True,
        'continuation_requires_successful_complete_all_31_public_queries_zero':True,
        'new_read_after_failure':False,'automatic_retry':False,
        'business_success_verified':False,'whole_app_production_ready':False}


def observe(plans,collect,guard,result,*,clock=time.monotonic,sleep=time.sleep):
    """At most three distinct original Sessions; exceptions leave all prior rows intact."""
    need(isinstance(plans,list) and len(plans)==MAX_ROUNDS and
         all(p.get('operation')=='inspect' and set(p['nonces'])=={'before','inspect','after'} for p in plans),
         'THREE_FIXED_INSPECT_PLANS_REQUIRED')
    nonces=[n for p in plans for n in p['nonces'].values()]
    need(len(nonces)==len(set(nonces))==9,'NINE_DISTINCT_INSPECTION_NONCES_REQUIRED')
    need(result==observation_record(),'FRESH_READINESS_OBSERVATION_REQUIRED')
    started=clock();deadline=started+QUALIFICATION_SECONDS
    result['qualification_started_monotonic']=started
    result['qualification_deadline_monotonic']=deadline
    try:
        for index,plan in enumerate(plans):
            if index:
                need(result['rounds'][-1]['public_decision']['catalog_all_zero'] is True,
                     'ONLY_SUCCESSFUL_ALL_ZERO_READ_CAN_CONTINUE')
                delay=min(started+ROUND_OFFSETS_SECONDS[index],deadline)-clock()
                if delay>0:
                    guard();sleep(delay);guard()
            if clock()>=deadline:
                result['stop_reason']='QUALIFICATION_DEADLINE_REACHED';break
            guard()
            if clock()>=deadline:
                result['stop_reason']='QUALIFICATION_DEADLINE_REACHED';break
            result['rounds_started']=index+1
            began=clock()
            # No retry or catch/re-enter around an original Session call.
            row=collect(plan,index)
            need(row.get('complete_current_assessment_verified') is True,
                 'COMPLETE_CURRENT_ROUND_REQUIRED')
            no_raw_ui(row)
            ended=clock()
            row['round']=index+1
            row['began_seconds_after_qualification_start']=began-started
            row['completed_seconds_after_qualification_start']=ended-started
            row['completed_within_qualification_window']=ended<=deadline
            result['rounds'].append(row);result['completed_rounds']=len(result['rounds'])
            if ended>deadline:
                result['stop_reason']='COMPLETED_AFTER_QUALIFICATION_DEADLINE';break
            if row['public_decision']['public_entry_candidate_present'] is True:
                result['public_entry_candidate_present']=True
                result['stop_reason']='ACTIONABLE_PUBLIC_ENTRY_OBSERVED';break
            if row['public_decision']['catalog_all_zero'] is not True:
                result['stop_reason']=row['public_decision']['reason'];break
        else:
            result['stop_reason']='THREE_COMPLETE_PUBLIC_CATALOGS_ALL_ZERO'
        need(result['completed_rounds']>0,'NO_COMPLETE_READINESS_OBSERVATION')
        return result
    except BaseException as error:
        result['stop_reason']='READ_OR_QUALIFICATION_FAILED_NO_RETRY'
        result['public_entry_candidate_present']=False
        result['error']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        result['elapsed_seconds']=clock()-started
'''

    worker = (OLD/'owned_inspect.py').read_text()
    worker = worker.replace("One actual-bound BESTBUY launch, read-only QA sequence and owned task cleanup.",
                            "One actual-bound BESTBUY launch, bounded content readiness and owned task cleanup.")
    worker = assign(worker, 'ROOT', None).replace("ROOT=None", "ROOT=Path("+repr(remote)+")", 1)
    worker = assign(worker, 'NONCE', nonce)
    worker = assign(worker, 'PLAN', plans).replace('PLAN='+repr(plans), 'PLANS='+repr(plans), 1)
    worker = assign(worker, 'RUNTIME_FILES',
                    {'owned_inspect.py','bestbuy_task_context.py','bestbuy_readiness.py','INPUTS.json'})
    worker = replace_once(worker, "    adapter.validate_plan(PLAN,qa)\n",
                          "    for plan in PLANS:adapter.validate_plan(plan,qa)\n")
    worker = replace_once(worker, "    values=[NONCE,*PLAN['nonces'].values()]\n    need(len(values)==len(set(values))==4",
                          "    values=[NONCE,*[n for plan in PLANS for n in plan['nonces'].values()]]\n    need(len(values)==len(set(values))==10")
    worker = worker.replace("'EXACT_NEW_FLOW_AND_THREE_HELPER_NONCES'",
                            "'EXACT_NEW_FLOW_AND_NINE_HELPER_NONCES'")
    worker = replace_once(worker,
                          "for k,v in RESOLVER_RECORDS.items()},\n         'EXACT_RUNTIME_INPUT_RECORD_REQUIRED')",
                          "for k,v in RESOLVER_RECORDS.items()}\n         and inputs['read_only_inspection_plans']==PLANS,\n         'EXACT_RUNTIME_INPUT_RECORD_REQUIRED')")
    worker = replace_once(worker, "def assessment_summary(q,step,sequence):",
                          "def assessment_summary(q,step,sequence,plan):")
    worker = replace_once(worker, "    for phase,nonce in PLAN['nonces'].items():",
                          "    for phase,nonce in plan['nonces'].items():")
    worker = replace_once(worker, "'mutation':phase in ('launch','cleanup'),'request':PLAN if phase=='inspect' else None",
                          "'mutation':phase in ('launch','cleanup'),'request':PLANS if phase=='inspect' else None")
    worker = replace_once(worker, "began+PHASE_SECONDS[phase],phase,q.qa,PLAN,q.resolver.RESOLVE,scope_record(q,expected))",
                          "began+PHASE_SECONDS[phase],phase,q.qa,PLANS,q.resolver.RESOLVE,scope_record(q,expected))")
    old_inspect = """            current='state_inspect_state';result['sequence']=session.sequence(json.loads(json.dumps(PLAN)))
            seq=result['sequence']
            need(seq['installed_before']==seq['installed_after']==q.installed and
                 seq['after_state_completed'] is True and seq['restoration_qualified'] is True and
                 seq['foreground_before']==seq['foreground_after'],'EXACT_READ_ONLY_INSPECTION_SCOPE_REQUIRED')
            result['assessments']=assessment_summary(q,step,seq)
            result['inspection_completed']=True"""
    new_inspect = """            current='content_readiness'
            readiness=load(HERE/'bestbuy_readiness.py',
                q.manifest['files']['bestbuy_readiness.py']['sha256'],'bestbuy_current_public_readiness')
            selected=flow.selected_task()
            result['readiness']=readiness.observation_record()
            def collect_round(plan,index):
                nonlocal session
                # A new original Session cannot carry a previous failed observation.
                session=None
                result['active_readiness_round']=index+1
                session=q.adapter.Session(flow,recorder,q.qa,q.proof,HELPER_UID)
                need(not hasattr(session,'sequence_observation'),'FRESH_ORIGINAL_SESSION_REQUIRED')
                flow.policy.begin_round(index)
                seq=session.sequence(json.loads(json.dumps(plan)))
                need(seq['owned_task']==selected and
                     seq['installed_before']==seq['installed_after']==q.installed and
                     seq['after_state_completed'] is True and seq['restoration_qualified'] is True and
                     seq['foreground_before']==seq['foreground_after'],'EXACT_READ_ONLY_INSPECTION_SCOPE_REQUIRED')
                metadata=assessment_summary(q,step,seq,plan)
                raw=read(step/(plan['nonces']['inspect']+'.assessment.json'))
                need(len(raw)==metadata['inspect']['assessment_bytes'] and
                     sha(raw)==metadata['inspect']['assessment_sha256'],'CURRENT_ASSESSMENT_BYTES_CHANGED')
                row=readiness.qualify_current(q.qa,json.loads(raw),seq,plan,metadata,selected,q.installed)
                result['sequence']=seq;result['assessments']=metadata
                return row
            readiness.observe(PLANS,collect_round,flow.guard,result['readiness'])
            result['inspection_completed']=True"""
    worker = replace_once(worker, old_inspect, new_inspect)
    old_counts = """            need(flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':4,'helper_path':4,
                'stacks':2,'instrument':3,'foreground':3} and flow.command_index==17 and
                flow.policy.used_nonces==set(PLAN['nonces'].values()) and flow.action_attempted is False,
                'EXACT_READ_ONLY_INSPECTION_COMMAND_COUNTS_REQUIRED')"""
    new_counts = """            rounds=result['readiness']['completed_rounds']
            need(1<=rounds<=3 and result['readiness']['rounds_started']==rounds and
                flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':2+2*rounds,'helper_path':2+2*rounds,
                'stacks':2*rounds,'instrument':3*rounds,'foreground':3*rounds} and
                flow.command_index==8+9*rounds and
                flow.policy.used_nonces=={n for plan in PLANS[:rounds] for n in plan['nonces'].values()} and
                flow.action_attempted is False,'EXACT_READ_ONLY_INSPECTION_COMMAND_COUNTS_REQUIRED')"""
    worker = replace_once(worker, old_counts, new_counts)
    worker = replace_once(worker, "    result['seconds']=time.monotonic()-began",
                          "    result['semantic_ready']=bool(result['ok'] and phase=='inspect' and\n        result.get('readiness',{}).get('public_entry_candidate_present') is True)\n    result['seconds']=time.monotonic()-began")
    worker = replace_once(worker, """        need(value['inspection_completed'] is True and value['sequence']['restoration_qualified'] is True
             and value['sequence']['after_state_completed'] is True,'ACTUAL_INSPECT_AND_RESTORATION_REQUIRED')""",
                          """        need(value['inspection_completed'] is True and value['sequence']['restoration_qualified'] is True
             and value['sequence']['after_state_completed'] is True and
             1<=value['readiness']['completed_rounds']<=3 and
             type(value['semantic_ready']) is bool,'ACTUAL_INSPECT_AND_RESTORATION_REQUIRED')""")
    worker = replace_once(worker, "        result['assessments']=inspection['assessments']",
                          "        result['readiness']=inspection['readiness']\n        result['inspection_semantic_ready']=inspection['semantic_ready']\n        result['assessments']=inspection['assessments']")
    worker = replace_once(worker, "        try:pin=ref.write_new(ROOT/'result.json',result)",
                          "        result['semantic_ready']=bool(result['ok'] and\n            result.get('owned_task_absent_after_cleanup') is True and result.get('inspection_semantic_ready') is True)\n        try:pin=ref.write_new(ROOT/'result.json',result)")
    worker = replace_once(worker, "'helper_uid':HELPER_UID,'maximum_native_launches':1,'new_helper_operations':['state','inspect','state'],",
                          "'helper_uid':HELPER_UID,'maximum_native_launches':1,'new_helper_operations':[['state','inspect','state']]*3,\n        'maximum_inspection_rounds':3,'qualification_window_seconds':30,'execution_kill_after_30_seconds':False,")

    context = (OLD/'bestbuy_task_context.py').read_text()
    context = context.replace('Only launch, one read-only QA inspection sequence, and exact task retirement',
                              'Only launch, up to three read-only QA inspection sequences, and exact task retirement')
    before = """        need(inspect_plan['operation']=='inspect' and set(inspect_plan['nonces'])=={'before','inspect','after'},
             'ONLY_FIXED_READ_ONLY_INSPECT_PLAN_REQUIRED')
        self.phase,self.qa,self.resolve,self.plan=phase,qa,list(resolve),inspect_plan
        self.step,self.read,self.selected_task=step,read,selected_task
        self.counts={};self.used_nonces=set();self.remove_attempted=False"""
    after = """        need(isinstance(inspect_plan,list) and len(inspect_plan)==3 and all(
             p.get('schema')==1 and p.get('operation')=='inspect' and
             set(p)=={'schema','operation','nonces'} and set(p['nonces'])=={'before','inspect','after'}
             for p in inspect_plan),'ONLY_THREE_FIXED_READ_ONLY_INSPECT_PLANS_REQUIRED')
        values=[qa.nonce(n) for p in inspect_plan for n in p['nonces'].values()]
        need(len(values)==len(set(values))==9,'NINE_DISTINCT_READ_ONLY_HELPER_NONCES_REQUIRED')
        self.phase,self.qa,self.resolve,self.plans=phase,qa,list(resolve),inspect_plan
        self.plan=None;self.round_index=-1;self.round_instruments=0
        self.step,self.read,self.selected_task=step,read,selected_task
        self.counts={};self.used_nonces=set();self.remove_attempted=False

    def begin_round(self,index):
        need(self.phase=='inspect' and type(index) is int and
             index==self.round_index+1 and 0<=index<3 and
             self.used_nonces=={n for p in self.plans[:index] for n in p['nonces'].values()},
             'NEXT_DISTINCT_COMPLETE_READ_ONLY_ROUND_REQUIRED')
        self.round_index=index;self.plan=self.plans[index];self.round_instruments=0"""
    context = replace_once(context, before, after)
    context = replace_once(context, "            # Inspect phase has an outer current identity pair and the original\n            # Session's own before/after pair. Other phases have only outer pair.\n            self.claim('helper_uid' if argv==OWN_UID else 'helper_path',4 if self.phase=='inspect' else 2)",
                           "            # Outer pair plus at most three original Session before/after pairs.\n            self.claim('helper_uid' if argv==OWN_UID else 'helper_path',8 if self.phase=='inspect' else 2)")
    context = replace_once(context, "self.claim('stacks',33 if self.phase=='cleanup' else 2);return",
                           "self.claim('stacks',33 if self.phase=='cleanup' else 6 if self.phase=='inspect' else 2);return")
    context = replace_once(context, "self.claim('foreground',3);return",
                           "self.claim('foreground',9);return")
    context = replace_once(context, "        matches=[]\n        for phase,nonce in self.plan['nonces'].items():",
                           "        need(self.plan is not None and self.round_instruments<3,'CURRENT_READ_ONLY_ROUND_REQUIRED')\n        expected_phase=('before','inspect','after')[self.round_instruments]\n        matches=[]\n        for phase,nonce in self.plan['nonces'].items():\n            if phase!=expected_phase:continue")
    context = replace_once(context, "        self.used_nonces.add(matches[0]);self.claim('instrument',3)",
                           "        self.used_nonces.add(matches[0]);self.claim('instrument',9);self.round_instruments+=1")

    stage = (OLD/'stage_execute.py').read_text().replace(
        'Stage exactly one new BESTBUY task source and execute its reviewed coordinator.',
        'Stage exactly one new BESTBUY no-input readiness source and its reviewed coordinator.')
    stage = assign(stage, 'ROOT', None).replace("ROOT=None", "ROOT=Path("+repr(remote)+")", 1)
    stage = assign(stage, 'NONCE', nonce)
    stage = assign(stage, 'FILES',
                   {'owned_inspect.py','bestbuy_task_context.py','bestbuy_readiness.py','INPUTS.json'})
    stage = replace_once(stage, "        result['ok']=True",
                         "        assert type(observed['semantic_ready']) is bool\n        result['semantic_ready']=observed['semantic_ready']\n        result['readiness']=observed['readiness']\n        result['ok']=True")
    stage = replace_once(stage, "        try:pin=ref.write_new(ROOT/'stage-result.json',result)",
                         "        result['semantic_ready']=bool(result['ok'] and result.get('semantic_ready') is True)\n        try:pin=ref.write_new(ROOT/'stage-result.json',result)")
    inputs = json.loads((OLD/'INPUTS.json').read_bytes())
    inputs['nonce'] = nonce
    inputs.pop('read_only_inspection_plan')
    inputs['read_only_inspection_plans'] = plans
    inputs['state'] = 'ACTUAL_INSTALL_BOUND_FRESH_BESTBUY_CONTENT_READINESS_UNRUN'
    inputs['qualification_window_seconds'] = 30
    inputs['qualification_deadline_is_not_execution_kill'] = True
    inputs['maximum_inspection_rounds'] = 3
    inputs['round_offsets_seconds'] = [0,10,20]
    inputs['original_phase_and_command_timeouts_unchanged'] = True
    inputs['historical_role_counts_only'] = {
        'bytes':12446,'sha256':'ad7febadb3ea1a3216bdabd024041e685c327d0333919f6d752165b9ca1ef62d',
        'retired_task':1012,'old_task_ids_preserved':[851],'complete_node_count':12,
        'all_31_public_queries_zero':True,'persistence_or_current_state_not_inferred':True}
    source = {'owned_inspect.py':worker.encode(),'bestbuy_task_context.py':context.encode(),
              'bestbuy_readiness.py':readiness.encode(),'INPUTS.json':encode(inputs)}
    assert all(0 < len(b) <= 65536 for b in source.values())
    assert sum(map(len,source.values())) < 131072
    for name, raw in source.items():
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
    ast.parse(stage)
    old_context = ast.parse((OLD/'bestbuy_task_context.py').read_text())
    new_context = ast.parse(context)
    for name, kind in [('Flow',ast.ClassDef),('open_task_context',ast.FunctionDef)]:
        a=next(n for n in old_context.body if isinstance(n,kind) and n.name==name)
        b=next(n for n in new_context.body if isinstance(n,kind) and n.name==name)
        assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)
    CANDIDATE.mkdir(mode=0o700)
    for name, raw in {**source,'stage_execute.py':stage.encode()}.items():
        with (CANDIDATE/name).open('xb') as stream:stream.write(raw)
    manifest=encode({'schema':1,'files':{n:pin(b) for n,b in sorted(source.items())}})
    (CANDIDATE/'SOURCE_PINS.json').write_bytes(manifest)
    generator=(OLD/'make_request.py').read_text()
    generator=assign(generator,'MANIFEST_SHA',pin(manifest)['sha256'])
    generator=assign(generator,'STAGE_SHA',pin(stage.encode())['sha256'])
    generator=assign(generator,'STAGE_BYTES',len(stage.encode()))
    generator=assign(generator,'NONCE',nonce)
    generator=assign(generator,'KEY',key)
    generator=replace_once(generator,
        "set(manifest['files'])=={'owned_inspect.py','bestbuy_task_context.py','INPUTS.json'}",
        "set(manifest['files'])=={'owned_inspect.py','bestbuy_task_context.py','bestbuy_readiness.py','INPUTS.json'}")
    (CANDIDATE/'make_request.py').write_text(generator)
    diffs=[]
    for name in ['owned_inspect.py','bestbuy_task_context.py','stage_execute.py','make_request.py','INPUTS.json']:
        diffs.extend(difflib.unified_diff((OLD/name).read_text().splitlines(keepends=True),
            (CANDIDATE/name).read_text().splitlines(keepends=True),
            fromfile='launch-inspect-01/'+name,tofile='content-readiness-01/'+name))
    diffs.extend(difflib.unified_diff([],readiness.splitlines(keepends=True),
                                    fromfile='/dev/null',tofile='content-readiness-01/bestbuy_readiness.py'))
    (CANDIDATE/'source.diff').write_text(''.join(diffs))
    provenance={'schema':1,'baseline_launch_frozen':pin((OLD/'FROZEN_FILES.json').read_bytes()),
        'baseline_launch_request':pin((OLD/'exact-request.json').read_bytes()),
        'original_role_reader':pin(roles.encode()),'role_catalogs_and_count_validator_functions_copied_exactly':True,
        'Flow_and_open_task_context_AST_unchanged':True,'original_qa_adapter_and_contract_not_modified':True,
        'new_root':remote,'new_key':key,'nonce':nonce,'plans':plans,'remote_calls':0,
        'raw_private_UI_read_locally':False,'runtime_qualification_not_yet_performed':True}
    (CANDIDATE/'SOURCE_PROVENANCE.json').write_bytes(encode(provenance))
    print(json.dumps({'candidate':str(CANDIDATE),'source_pins':pin(manifest),
        'source_bytes':{n:len(b) for n,b in source.items()},'full_diff':pin(''.join(diffs).encode()),
        'device_calls':0},indent=2))


if __name__=='__main__':
    main()
