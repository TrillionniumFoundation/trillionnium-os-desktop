#!/usr/bin/env python3
"""Local new-policy/original-Session controls; no Android or private UI reads."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def load(path,name,expected=None):
    raw=path.read_bytes()
    if expected:assert hashlib.sha256(raw).hexdigest()==expected
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def main():
    entry=load(HERE/'owned_inspect.py','entry')
    nav=load(HERE/'search_navigation.py','navigation')
    ctx=load(HERE/'amazon_task_context.py','context')
    qa=load(ROOT/'owned-amazon-qa-r1-build01/source/qa_contract.py','actual_qa',
        'aebd0f44bcec8433586fb9cdab1ce0e0be9ac2adedf5c5c5c485425a13bc3402')
    adapter=load(ROOT/'owned-amazon-qa-r1-build01/source/qa_adapter.py','actual_session',
        '3f705d3a7a605b9436beb0e77bd156923cd8e581fe9f3f6d4635eb62910cce59')
    spec=entry.PLAN
    for p in nav.plans(spec):adapter.validate_plan(p,qa)
    scope={'package':qa.PACKAGE,'uid':qa.UID,'user':0,'display':0,
        'activity':nav.ENTRY_ACTIVITY,'window_token':'fab123','main_epoch_sha256':qa.MAIN_EPOCH}
    installed={'fixture_identity':True,'uid':10175}
    cases=[]
    def case(name,fn):
        fn();cases.append({'case':name,'expected_met':True})
    def reject(fn,reason):
        try:fn()
        except BaseException as error:
            assert reason in str(error),(reason,repr(error));return error
        raise AssertionError('expected rejection '+reason)
    def inspection(variant=0,clickable=True):
        node={'package':qa.PACKAGE,'path':'0','class':'android.widget.ImageButton',
            'resource_id':nav.SELECTOR['resource_id'],'content_desc':'Search',
            'class_truncated':False,'resource_id_truncated':False,'content_desc_truncated':False,
            'visible':True,'enabled':True,'password':False,'clickable':clickable,
            'editable':False,'supports_set_text':False,'bounds':[0,0,100,100],'fixture_variant':variant}
        node['node_sha256']=qa.sha(qa.canonical(node));nodes=[node]
        window={'package':qa.PACKAGE,'display':0,'type':1,'focused':True,'bounds':[0,0,200,300]}
        return {'complete':True,'traversal':'visible-non-password-subtrees',
            'window':window,'window_sha256':qa.sha(qa.canonical(window)),
            'observed_elapsed_ms':1,'connection_scoped_window_id':1,
            'nodes':nodes,'tree_sha256':qa.sha(qa.canonical(nodes))}
    def write(path,value):
        raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
        with path.open('xb') as stream:stream.write(raw)
        return raw

    with tempfile.TemporaryDirectory(prefix='owned-search-control-',dir=HERE) as directory:
        root=Path(directory);serial=[0]
        def fresh_policy():
            serial[0]+=1;step=root/str(serial[0]);step.mkdir()
            policy=ctx.Policy('inspect',qa,['fixture-resolve'],copy.deepcopy(spec),step,entry.read,lambda:None)
            return policy,step
        def permit(policy,step,request,mutation=None):
            write(step/(request['nonce']+'.request.json'),request)
            return policy.admit(qa.instrumentation_argv(request),20,
                request['op']=='click' if mutation is None else mutation,False)
        def request(nonce,op,**extra):return {'protocol':qa.PROTOCOL,'nonce':nonce,'op':op,**extra}
        def entry_request(**extra):
            return request(spec['entry']['nonces']['action'],'click',scope=scope,
                inspection_nonce=spec['entry']['nonces']['inspect'],inspection_sha256='a'*64,
                node_path='0',node_sha256='b'*64,**extra)
        def exact_allowlist():
            p,s=fresh_policy()
            for plan in nav.plans(spec):
                for phase,n in plan['nonces'].items():
                    if phase=='action':r=entry_request()
                    else:r=request(n,'inspect',scope=scope) if phase=='inspect' else request(n,'state')
                    permit(p,s,r)
            assert len(p.used_nonces)==22 and p.counts=={'instrument':22}
            assert p.action_nonces=={spec['entry']['nonces']['action']}
            reject(lambda:p.admit(qa.instrumentation_argv(entry_request()),20,True,False),'ONLY_ONE_CURRENT')
        case('actual_policy_exact_22_nonces_one_click_and_replay_rejection',exact_allowlist)
        def wrong_mutation():
            p,s=fresh_policy();r=entry_request()
            reject(lambda:permit(p,s,r,False),'ONLY_FIXED_CLICK_IS_MUTATING')
            assert not p.used_nonces and not p.action_nonces
        case('click_cannot_hide_as_read_only',wrong_mutation)
        def wrong_prior():
            p,s=fresh_policy();r=entry_request();r['inspection_nonce']=spec['stability'][0]['nonces']['inspect']
            reject(lambda:permit(p,s,r),'CLICK_MUST_USE_ITS_OWN_FRESH_INSPECTION')
            assert not p.used_nonces
        case('earlier_stability_nonce_cannot_authorize_click',wrong_prior)
        def unplanned():
            p,s=fresh_policy();r=request('f'*32,'inspect',scope=scope)
            reject(lambda:permit(p,s,r),'ONLY_ONE_CURRENT');assert not p.used_nonces
            reject(lambda:p.admit(['/system/bin/input','tap','20','20'],20,True,False),'ONLY_ONE_CURRENT')
        case('unplanned_nonce_and_direct_touch_denied_before_transport',unplanned)

        def scenario(variants,fail_inspect=None,fail_click=False,fail_post=False,wrong_action_activity=False):
            policy,step=fresh_policy();calls=[];inspect_count=[0];command_index=[0];current_plan=['stable']
            localqa=types.SimpleNamespace(**qa.__dict__)
            localqa.assess_restoration=lambda before,middle,after:{'fixture_restoration_only':True}
            session=object.__new__(adapter.Session)
            session.qa=localqa
            current_scope=dict(scope)
            def installed_read():
                policy.admit(ctx.OWN_UID,8,False,False);policy.admit(ctx.OWN_PATH,8,False,False)
                command_index[0]+=2;return dict(installed)
            def task_read():
                policy.admit(ctx.STACKS,20,False,False);command_index[0]+=1
                return {'fixture_owned_task':1}
            def foreground():
                policy.admit(ctx.FOREGROUND,15,False,True)
                value=dict(current_scope)
                if wrong_action_activity and current_plan[0]=='entry':
                    value['activity']=qa.PACKAGE+'/FixtureUnexpectedActivity'
                return value
            def instrument(r):
                if r['nonce']==spec['entry']['nonces']['before']:current_plan[0]='entry'
                elif r['nonce']==spec['post']['nonces']['before']:current_plan[0]='post'
                qa.validate_request(r);permit(policy,step,r);command_index[0]+=1
                calls.append((r['nonce'],r['op']))
                if r['op']=='inspect':
                    inspect_count[0]+=1
                    if fail_inspect==inspect_count[0]:raise RuntimeError('FIXTURE_PRIMARY_READ_FAILURE')
                    if fail_post and r['nonce']==spec['post']['nonces']['inspect']:
                        raise RuntimeError('FIXTURE_POST_READ_FAILURE')
                if r['op']=='click' and fail_click:raise RuntimeError('FIXTURE_PRIMARY_CLICK_FAILURE')
                helper={'nonce':r['nonce'],'op':r['op'],'self_uid':10175,'state':{'fixture':'unchanged'},
                    'ui_automation_connected':False}
                if r['op']=='inspect':
                    variant=variants[min(inspect_count[0]-1,len(variants)-1)]
                    helper['inspection']=inspection(variant)
                if r['op']=='click':helper['action_window']=inspection()['window']
                assessed={'helper':helper,'wire_sha256':qa.sha(qa.canonical(helper))}
                write(step/(r['nonce']+'.assessment.json'),assessed)
                return assessed
            session.installed=installed_read;session.task=task_read
            session.foreground=foreground;session.instrument=instrument
            q=types.SimpleNamespace(qa=localqa,installed=installed)
            def summary(q,step,seq,plan):
                raw=entry.read(step/(plan['nonces']['inspect']+'.assessment.json'));v=json.loads(raw)
                return {'inspect':{'assessment_sha256':entry.sha(raw),'wire_sha256':v['wire_sha256']}}
            base=types.SimpleNamespace(read=entry.read,sha=entry.sha,assessment_summary=summary)
            result={};error=None
            try:nav.run(base,q,session,step,copy.deepcopy(spec),result)
            except BaseException as e:error=e
            assert session.qa is localqa,'temporary action selector was not restored'
            return result,error,calls,policy,command_index[0]
        def success():
            r,e,c,p,n=scenario([0,0,0,1]);assert e is None and r['search_entry']['ok']
            assert r['search_entry']['stable_read_indices']==[0,1]
            assert sum(op=='click' for _,op in c)==1 and n==37
            assert r['search_entry']['entry_sequence']['after_state_completed']
            assert r['search_entry']['post_sequence']['after_state_completed']
            assert p.counts=={'helper_uid':8,'helper_path':8,'stacks':8,'instrument':13,'foreground':12}
        case('original_Session_four_sequences_with_new_policy_current_selection_and_post_read',success)
        def three_reads():
            r,e,c,p,n=scenario([0,1,1,1,2]);assert e is None
            assert r['search_entry']['stable_read_indices']==[1,2] and sum(op=='click' for _,op in c)==1
        case('only_successful_complete_read_variation_can_wait_for_stability',three_reads)
        def fifth_read_pair():
            r,e,c,p,n=scenario([0,1,2,3,3,3,4]);assert e is None
            assert r['search_entry']['stable_read_indices']==[3,4]
            assert sum(op=='click' for _,op in c)==1 and n==64
            assert p.counts=={'helper_uid':14,'helper_path':14,'stacks':14,'instrument':22,'foreground':21}
            assert r['search_entry']['entry_sequence']['after_state_completed']
            assert r['search_entry']['post_sequence']['after_state_completed']
        case('fifth_successful_read_matches_fourth_then_original_fresh_action_and_post',fifth_read_pair)
        def never_stable():
            r,e,c,p,n=scenario([0,1,2,3,4]);assert 'TWO_CONSECUTIVE' in str(e)
            assert sum(op=='click' for _,op in c)==0 and r['search_entry']['post_inspection_completed']
        case('five_unstable_reads_no_click_one_independent_post',never_stable)
        def failed_read():
            r,e,c,p,n=scenario([0,0,0],fail_inspect=2);assert str(e)=='FIXTURE_PRIMARY_READ_FAILURE'
            assert sum(op=='click' for _,op in c)==0 and r['search_entry']['post_inspection_completed']
            assert r['search_entry']['failed_sequence_observation']['after_state_completed']
            assert not r['search_entry']['failed_sequence_observation']['restoration_qualified']
        case('failed_stability_read_not_replayed_original_after_state_and_post_remain',failed_read)
        def failed_click():
            r,e,c,p,n=scenario([0,0,0,1],fail_click=True);assert str(e)=='FIXTURE_PRIMARY_CLICK_FAILURE'
            assert sum(op=='click' for _,op in c)==1 and r['search_entry']['post_inspection_completed']
            assert r['search_entry']['failed_sequence_observation']['after_state_completed']
        case('failed_click_once_no_replay_independent_after_and_post',failed_click)
        def double_failure():
            r,e,c,p,n=scenario([0,0,0,1],fail_click=True,fail_post=True)
            assert str(e)=='FIXTURE_PRIMARY_CLICK_FAILURE' and sum(op=='click' for _,op in c)==1
            assert r['search_entry']['secondary_errors'][0]['message']=='FIXTURE_POST_READ_FAILURE'
            assert r['search_entry']['failed_post_sequence_observation']['after_state_completed']
        case('post_failure_secondary_keeps_original_click_error_and_after_state',double_failure)
        def moved_activity():
            r,e,c,p,n=scenario([0,0,0,1],wrong_action_activity=True)
            assert 'ACTION_BOUND_CURRENT_SEARCH_ENTRY_SCOPE_REQUIRED' in str(e)
            assert sum(op=='click' for _,op in c)==0
            assert r['search_entry']['failed_sequence_observation']['after_state_completed']
        case('current_action_sequence_activity_change_prevents_click',moved_activity)
        # A dedicated one-action view avoids fabricating successful tree census.
        # The plan's inspect nonce remains available to the production branch.
        # Exercise that branch using an iterator with only the action item.
        def action_summary_branch():
            class Names(dict):
                def items(self):return [('action',self['action'])]
            p,s=fresh_policy();n=spec['entry']['nonces']['action']
            helper={'nonce':n,'self_uid':10175,'op':'click','ok':True,'error':None,'secondary_errors':[],
                'node_action_returned':True,'node_action':'ACTION_CLICK',
                'inspection_nonce':spec['entry']['nonces']['inspect'],'action_window':inspection()['window']}
            assessed={'helper':helper,'actual_command_returncode':0,'actual_instrumentation_finish_code':-1,
                'held_transport_returned_after_post_guard':True,'wire_sha256':qa.sha(qa.canonical(helper)),
                'recorder_command_result_sha256':'c'*64}
            path=s/(n+'.assessment.json');write(path,assessed)
            plan={'operation':'click','nonces':Names(action=n,inspect=spec['entry']['nonces']['inspect'])}
            value=entry.assessment_summary(types.SimpleNamespace(qa=qa),s,{},plan)
            assert value['action']['action_acknowledged']
            assessed['helper']['node_action_returned']=False
            assessed['wire_sha256']=qa.sha(qa.canonical(assessed['helper']))
            path.unlink();write(path,assessed)
            reject(lambda:entry.assessment_summary(types.SimpleNamespace(qa=qa),s,{},plan),'ONE_ACTUAL_SOURCE_BOUND')
        case('summary_uses_actual_Java_node_action_returned_field_false_rejected',action_summary_branch)
    print(json.dumps({'schema':1,'state':'PASS','cases':cases,'count':len(cases),
        'actual_production_functions_executed':['Policy.admit','ActionBoundSearchContract.select_unique_clickable',
            'stable_entry','run','original Session.sequence','original qa request/selector/complete-tree validators',
            'new action branch of assessment_summary'],
        'seams':['No Android: instrument/installed/task/foreground return explicit owned fixtures',
            'Helper execution, restoration proof and inspection summary are I/O seams in sequence controls',
            'The summary branch-only Names view is a control seam, not a permitted runtime plan'],
        'raw_private_UI_read':False,'device_calls':0,'actual_functional_qualification':'NOT_RUN'},
        indent=2,sort_keys=True))


if __name__=='__main__':main()
