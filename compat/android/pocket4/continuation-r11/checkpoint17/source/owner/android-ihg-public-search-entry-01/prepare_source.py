#!/usr/bin/env python3
"""Bind new owned public Search workflow to exact actual IHG baseline sources."""
from pathlib import Path
import ast,hashlib,json
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-ihg-launch-inspect-01'

def replace(source,before,after,count=1):
    assert source.count(before)==count,(before,source.count(before),count)
    return source.replace(before,after)

def main():
    assert hashlib.sha256((BASE/'SOURCE_PINS.json').read_bytes()).hexdigest()=='704bf0640c6a207ad8177dfc0240896cc785b6fa6db34521fbea5cd02e42a6fd'
    for name,row in json.loads((BASE/'SOURCE_PINS.json').read_bytes())['files'].items():
        raw=(BASE/name).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
    b=json.loads((HERE/'fresh-bindings.json').read_bytes())
    click={'schema':1,'operation':'click','selector':{'text':'Search'},'nonces':b['click_nonces']}
    post={'schema':1,'operation':'inspect','nonces':b['post_nonces']}
    allnonces=[b['flow_nonce'],*click['nonces'].values(),*post['nonces'].values()]
    assert len(allnonces)==len(set(allnonces))==8
    source=(BASE/'owned_inspect.py').read_text().replace('/home/alex/work/pocket4-ihg-owned-launch-inspect-01',b['new_root']).replace('399444a5b72d53139b880a4afefdb31a',b['flow_nonce'])
    source=replace(source,'One actual-bound IHG launch, read-only QA sequence and owned task cleanup.\n\nNo click, text entry, old v2 helper, screenshot, audio, package change, permission\ngrant or settings write. Raw helper tree stays in the new root-private flow.',
        'One actual-bound IHG launch, fresh public Search entry and owned cleanup.\n\nAt most one current semantically bound public Search click, followed by an\nindependent inspection. No text entry, login, booking or purchase. Raw helper\ntrees remain in the new root-private flow.')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PLAN' for t in n.targets))
    lines=source.splitlines(True);lines[node.lineno-1:node.end_lineno]=[
        '# The source label is inert; the exact selector is derived from the current complete inspection.\n',
        'PLAN='+repr(click)+'\nPOST_PLAN='+repr(post)+'\n'];source=''.join(lines)
    source=replace(source,"RUNTIME_FILES={'owned_inspect.py','ihg_task_context.py','INPUTS.json'}","RUNTIME_FILES={'owned_inspect.py','ihg_task_context.py','public_search.py','INPUTS.json'}")
    source=replace(source,'    adapter.validate_plan(PLAN,qa)','    adapter.validate_plan(PLAN,qa);adapter.validate_plan(POST_PLAN,qa)')
    source=replace(source,"    values=[NONCE,*PLAN['nonces'].values()]\n    need(len(values)==len(set(values))==4 and all(re.fullmatch('[0-9a-f]{32}',v) for v in values),\n         'EXACT_NEW_FLOW_AND_THREE_HELPER_NONCES')",
        "    values=[NONCE,*PLAN['nonces'].values(),*POST_PLAN['nonces'].values()]\n    need(len(values)==len(set(values))==8 and STATE_NONCE not in values and\n         all(re.fullmatch('[0-9a-f]{32}',v) for v in values),'EXACT_NEW_FLOW_AND_SEVEN_HELPER_NONCES')")
    source=replace(source,"         'EXACT_RUNTIME_INPUT_RECORD_REQUIRED')","         'EXACT_RUNTIME_INPUT_RECORD_REQUIRED')\n    need(inputs['public_search_click_plan']==PLAN and inputs['independent_post_plan']==POST_PLAN,\n         'EXACT_PUBLIC_SEARCH_PLANS_REQUIRED')\n    public_search=load(HERE/'public_search.py',manifest['files']['public_search.py']['sha256'],'fresh_public_search_entry')")
    source=replace(source,'        adapter=adapter,qa=qa,proof=proof,installed=INSTALLED)','        adapter=adapter,qa=qa,proof=proof,installed=INSTALLED,public_search=public_search)')
    source=replace(source,'def assessment_summary(q,step,sequence):','def assessment_summary(q,step,sequence,plan):')
    source=replace(source,"    for phase,nonce in PLAN['nonces'].items():","    for phase,nonce in plan['nonces'].items():")
    source=replace(source,"             helper['op']==('inspect' if phase=='inspect' else 'state') and","             helper['op']==('click' if phase=='action' else 'inspect' if phase=='inspect' else 'state') and")
    source=replace(source,"        result[phase]=row\n    return result","        elif phase=='action':\n            need(helper['node_action']=='ACTION_CLICK' and helper['node_action_returned'] is True and\n                 helper['action_attempted'] is True and helper['outcome_unknown'] is True and\n                 helper['inspection_nonce']==plan['nonces']['inspect'] and\n                 helper['inspection_sha256']==sequence['inspection_wire_sha256'],'ACTUAL_CURRENT_SEARCH_CLICK_ACK_REQUIRED')\n            row.update(node_action='ACTION_CLICK',node_action_returned=True,action_attempted=True,outcome_unknown=True,\n                target_node_sha256=helper['target_node_sha256'],inspection_nonce=helper['inspection_nonce'],\n                inspection_sha256=helper['inspection_sha256'],\n                action_window={k:helper['action_window'][k] for k in ('package','display','type','focused')},\n                window_observation=q.qa.window_observation(helper['window_observation']),\n                tree_observations=q.qa.tree_observations(helper['tree_observations'],'click',True))\n        result[phase]=row\n    return result")
    source=replace(source,"    q=qualified(expected);u,ref=q.util,q.ref\n    step=FLOW/'steps'/(phase+'-01')","    q=qualified(expected);u,ref=q.util,q.ref\n    click_plan=json.loads(json.dumps(PLAN));post_plan=json.loads(json.dumps(POST_PLAN))\n    plans={'click':click_plan,'post':post_plan}\n    step=FLOW/'steps'/(phase+'-01')")
    source=source.replace("'click_actions':0","'maximum_click_actions':1")
    source=replace(source,"'automatic_retry':False,'mutation':phase in ('launch','cleanup'),'request':PLAN if phase=='inspect' else None}","'automatic_retry':False,'mutation':True,'request':plans if phase=='inspect' else None}")
    source=replace(source,'transport,result,began+PHASE_SECONDS[phase],phase,q.qa,PLAN,q.resolver.RESOLVE,scope_record(q,expected))','transport,result,began+PHASE_SECONDS[phase],phase,q.qa,plans,q.resolver.RESOLVE,scope_record(q,expected))')
    source=replace(source,'        session=q.adapter.Session(flow,recorder,q.qa,q.proof,HELPER_UID)',
        "        session=(q.public_search.make_session(q.adapter,flow,recorder,q.qa,q.proof,HELPER_UID,click_plan,post_plan)\n                 if phase=='inspect' else q.adapter.Session(flow,recorder,q.qa,q.proof,HELPER_UID))")
    start=source.index("        elif phase=='inspect':\n            current='state_inspect_state'")
    end=source.index('        else:\n            current=\'exact_owned_cleanup\'',start)
    source=source[:start]+"        elif phase=='inspect':\n            current='public_search_sequences'\n            q.public_search.run_sequences(q.qa,session,q.installed,click_plan,post_plan,result,\n                lambda seq,plan:assessment_summary(q,step,seq,plan),lambda phase,error:u.remember(result,phase,error))\n"+source[end:]
    source=replace(source,"        if phase=='inspect':\n            need(flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':4,'helper_path':4,\n                'stacks':2,'instrument':3,'foreground':3} and flow.command_index==17 and\n                flow.policy.used_nonces==set(PLAN['nonces'].values()) and flow.action_attempted is False,\n                'EXACT_READ_ONLY_INSPECTION_COMMAND_COUNTS_REQUIRED')\n        result['ok']=True",
        "        if phase=='inspect' and result['error'] is None:\n            need(flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':6,'helper_path':6,\n                'stacks':4,'instrument':7,'foreground':6,'click':1} and flow.command_index==27 and\n                flow.policy.used_nonces==set(PLAN['nonces'].values())|set(POST_PLAN['nonces'].values()) and\n                flow.action_attempted is True and result.get('public_search_entry_completed') is True,\n                'EXACT_SINGLE_SEARCH_CLICK_AND_INDEPENDENT_READ_COUNTS_REQUIRED')\n        result['ok']=result['error'] is None and result['secondary_errors']==[]")
    source=replace(source,"    result['outcome_unknown']=bool(result['action_attempted'] and not result['ok'])","    result['outcome_unknown']=bool(result['action_attempted'] and (phase=='inspect' or not result['ok']))\n    result['click_requests_admitted']=0 if session is None else int(getattr(session,'action_request_admitted',False))")
    source=replace(source,"         value['outcome_unknown'] is False and value['final_Main_guard_passed'] is True and","         value['outcome_unknown'] is (phase=='inspect') and value['final_Main_guard_passed'] is True and")
    source=replace(source,"        need(value['inspection_completed'] is True and value['sequence']['restoration_qualified'] is True\n             and value['sequence']['after_state_completed'] is True,'ACTUAL_INSPECT_AND_RESTORATION_REQUIRED')",
        "        need(value['inspection_completed'] is True and value['sequence']['restoration_qualified'] is True and\n             value['sequence']['after_state_completed'] is True and value['sequence']['click_acknowledged'] is True and\n             value['post_sequence']['after_state_completed'] is True and value['post_sequence']['restoration_qualified'] is True and\n             value['public_search_entry_completed'] is True and value['public_search_entry']['public_search_entry_selection_verified'] is True,\n             'ACTUAL_PUBLIC_SEARCH_ENTRY_AND_BOTH_RESTORATIONS_REQUIRED')")
    source=replace(source,"        result['foreground']=inspection['sequence']['foreground_after']\n        result['restoration']=inspection['sequence']['accessibility_restoration']\n        result['read_only_inspection_completed']=True",
        "        result['post_assessments']=inspection['post_assessments']\n        result['foreground']=inspection['post_sequence']['foreground_after']\n        result['restoration']=inspection['sequence']['accessibility_restoration']\n        result['post_restoration']=inspection['post_sequence']['accessibility_restoration']\n        result['public_search_entry']=inspection['public_search_entry']\n        result['public_search_entry_completed']=True\n        result['business_outcome_unknown']=True")
    source=replace(source,"'helper_uid':HELPER_UID,'maximum_native_launches':1,'new_helper_operations':['state','inspect','state'],\n        'clicks':0", "'helper_uid':HELPER_UID,'maximum_native_launches':1,'new_helper_operations':['state','inspect','click','state','state','inspect','state'],\n        'maximum_clicks':1")
    (HERE/'owned_inspect.py').write_text(source)
    task=(BASE/'ihg_task_context.py').read_text()
    task=replace(task,'Only launch, one read-only QA inspection sequence, and exact task retirement\nare described here. No click/set-text/media/screenshot opcode is admitted.',
        'Only launch, one current public Search click plus independent inspection,\nand exact task retirement are described here. No text/media/screenshot opcode.')
    task=replace(task,"        need(inspect_plan['operation']=='inspect' and set(inspect_plan['nonces'])=={'before','inspect','after'},\n             'ONLY_FIXED_READ_ONLY_INSPECT_PLAN_REQUIRED')",
        "        need(set(inspect_plan)=={'click','post'} and inspect_plan['click']['operation']=='click' and\n             set(inspect_plan['click']['nonces'])=={'before','inspect','action','after'} and\n             inspect_plan['post']['operation']=='inspect' and set(inspect_plan['post']['nonces'])=={'before','inspect','after'},\n             'ONLY_FIXED_SEARCH_CLICK_AND_INDEPENDENT_POST_PLANS')\n        values=[n for plan in inspect_plan.values() for n in plan['nonces'].values()]\n        need(len(values)==len(set(values))==7,'SEVEN_DISTINCT_CURRENT_HELPER_NONCES')")
    task=replace(task,"            # Inspect phase has an outer current identity pair and the original\n            # Session's own before/after pair. Other phases have only outer pair.\n            self.claim('helper_uid' if argv==OWN_UID else 'helper_path',4 if self.phase=='inspect' else 2)",
        "            # Two original Sessions each have before/after pairs, plus outer pair.\n            self.claim('helper_uid' if argv==OWN_UID else 'helper_path',6 if self.phase=='inspect' else 2)")
    task=replace(task,"            self.claim('stacks',33 if self.phase=='cleanup' else 2);return", "            self.claim('stacks',33 if self.phase=='cleanup' else 4 if self.phase=='inspect' else 2);return")
    task=replace(task,"            self.claim('foreground',3);return","            self.claim('foreground',6);return")
    start=task.index("        need(self.phase=='inspect' and timeout==20 and not mutation and not private,")
    end=task.index('\n\n\nclass Flow:',start)
    task=task[:start]+"""        need(self.phase=='inspect' and timeout==20 and not private,
             'NO_OTHER_IHG_COMMAND_ADMITTED')
        matches=[]
        for plan in self.plan.values():
            for phase,nonce in plan['nonces'].items():
                if nonce in self.used_nonces:continue
                path=self.step/(nonce+'.request.json')
                try:raw=self.read(path,65536)
                except FileNotFoundError:continue
                request=json.loads(raw)
                operation='click' if phase=='action' else 'inspect' if phase=='inspect' else 'state'
                need(request.get('nonce')==nonce and request.get('op')==operation,
                     'FIXED_CURRENT_PHASE_REQUEST_REQUIRED')
                self.qa.validate_request(request)
                if self.qa.instrumentation_argv(request)==argv:
                    need(mutation is (operation=='click'),'EXACT_CURRENT_OPERATION_MUTATION_FLAG')
                    matches.append((nonce,operation))
        need(len(matches)==1,'ONLY_ONE_CURRENT_SOURCE_BOUND_HELPER_REQUEST')
        nonce,operation=matches[0]
        self.used_nonces.add(nonce);self.claim('instrument',7)
        if operation=='click':self.claim('click',1)
"""+task[end:]
    (HERE/'ihg_task_context.py').write_text(task)
    stage=(BASE/'stage_execute.py').read_text().replace('/home/alex/work/pocket4-ihg-owned-launch-inspect-01',b['new_root']).replace('399444a5b72d53139b880a4afefdb31a',b['flow_nonce'])
    stage=replace(stage,"FILES={'owned_inspect.py','ihg_task_context.py','INPUTS.json'}","FILES={'owned_inspect.py','ihg_task_context.py','public_search.py','INPUTS.json'}")
    stage=replace(stage,"'maximum_native_launches':1,'click_actions':0","'maximum_native_launches':1,'maximum_click_actions':1")
    stage=replace(stage,"observed['read_only_inspection_completed'] is True","observed['public_search_entry_completed'] is True")
    (HERE/'stage_execute.py').write_text(stage)
    inputs=json.loads((BASE/'INPUTS.json').read_bytes())
    del inputs['read_only_inspection_plan']
    inputs.update(nonce=b['flow_nonce'],state='ACTUAL_INSTALL_BOUND_FRESH_IHG_PUBLIC_SEARCH_ENTRY_UNRUN',
        public_search_click_plan=click,independent_post_plan=post,maximum_public_clicks=1,
        original_full_tree_window_node_freshness_required=True,all_UI_input_requires_current_complete_semantic_selection=True,
        historical_task_or_node_authorizes_action=False,hotel_search_results_verified=False,login_or_booking_verified=False,
        business_success_verified=False,whole_app_production_ready=False,
        public_role_observation={'bytes':12714,'sha256':'ba438fee676cfdfad2bb8bfbf8e630fccc1d0d6ffc8dca13399b7538e19d02cc',
            'retired_task':1002,'fixed_public_Search_matching_nodes':2,'self_or_direct_parent_candidates':1,
            'classes':['android.widget.FrameLayout','android.widget.TextView'],'historical_literal_case_or_field_association_not_assumed':True},
        qualification='Only independent public Search selected-state transition; hotel search, dates, accounts and booking remain unverified')
    (HERE/'INPUTS.json').write_text(json.dumps(inputs,sort_keys=True,ensure_ascii=False,indent=2)+'\n')
    gen=(BASE/'make_request.py').read_text().replace('399444a5b72d53139b880a4afefdb31a',b['flow_nonce']).replace('pocket4-ihg-owned-launch-inspect-01-20261105',b['new_key'])
    gen=gen.replace("{'owned_inspect.py','ihg_task_context.py','INPUTS.json'}","{'owned_inspect.py','ihg_task_context.py','public_search.py','INPUTS.json'}")
    (HERE/'make_request.py').write_text(gen)
    print(json.dumps({'state':'LOCAL_SEARCH_SOURCE_PREPARED','helper_nonces':7,'maximum_clicks':1,'device_calls':0}))

if __name__=='__main__':main()
