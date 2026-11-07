#!/usr/bin/env python3
"""Narrow actual-source host controls; never invokes Android or remote tools."""
import ast
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-bili-owned-r2-inspect-01'
QA_SOURCE=HERE.parent/'owned-bili-qa-r2-window-01/source/qa_contract.py'
PRIVATE=HERE.parent/'root-recovery-20261104-02/private/qa-r2-inspect01-tree/private-tree.json'

def load(path,name):
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),value.__dict__)
    return value

def sha(raw):return hashlib.sha256(raw).hexdigest()

def run():
    m=load(HERE/'owned_navigation.py','actual_search_entry')
    qa=load(QA_SOURCE,'actual_r2_contract')
    assert sha(QA_SOURCE.read_bytes())=='08b3414576bad55597902627537c61579a663b069c07a1198e5e46fbcf611472'
    rows=[]
    raw=PRIVATE.read_bytes()
    assert len(raw)==65869 and sha(raw)=='9e6ee4ae8cc9e8b6b1057819ea672bc7c2b1285a907fe518c7b376446a259680'
    inspection=json.loads(raw)['inspection']
    node=qa.select_unique_clickable(inspection,m.fixed_plan()['selector'])
    assert sum(n.get('resource_id')=='tv.danmaku.bili:id/expand_search' and n.get('clickable') is True for n in inspection['nodes'])==1
    rows.append({'control':'actual_private_tree_fixed_selector_unique','passed':True,
                 'private_tree_sha256':sha(raw),'selected_node_hash':node['node_sha256'],
                 'private_node_or_text_exported':False,'Android_action':False})
    del raw,inspection,node
    all_names=[m.NONCE,*m.PLAN['nonces'].values(),*m.POST_PLAN['nonces'].values()]
    assert len(set(all_names))==8
    old=load(BASE/'owned_inspect.py','actual_prior_entry')
    assert not set(all_names)&{old.NONCE,*old.PLAN['nonces'].values(),m.OLD_STATE_NONCE}
    rows.append({'control':'eight_fresh_distinct_nonces_against_previous_flow','passed':True})
    orig_summary=m.assessment_summary
    m.assessment_summary=lambda *args:{'explicit_seam':'summary materialization only'}
    class Prior:
        @staticmethod
        def remember(result,phase,error):
            record={'phase':phase,'type':type(error).__name__,'message':str(error)}
            if result['error'] is None:result['error']=record
            else:result['secondary_errors'].append(record)
            result['ok']=False
    class Session:
        def __init__(self,click_error=False,post_error=False):
            self.calls=[];self.click_error=click_error;self.post_error=post_error
        def sequence(self,plan):
            op=plan['operation'];self.calls.append(op)
            self.sequence_observation={'explicit_seam':True,'operation':op}
            if op=='click' and self.click_error:raise RuntimeError('PRIMARY_CLICK_FAILURE')
            if op=='inspect' and self.post_error:raise OSError('SECONDARY_POST_FAILURE')
            return {'installed_before':{'own':'same'},'installed_after':{'own':'same'},
                    'click_acknowledged':op=='click','restoration_qualified':True,'after_state_completed':True}
    for name,click_error,post_error in [('success',False,False),('click_error_post_observed',True,False),('primary_plus_secondary',True,True)]:
        sess=Session(click_error,post_error)
        result={'ok':False,'error':None,'secondary_errors':[]}
        m.navigation_sequences(Prior,qa,types.SimpleNamespace(step=Path('/unopened')),sess,{'own':'same'},result)
        assert sess.calls==['click','inspect']
        assert result['business_outcome_unknown'] is True and result['next_business_action_requires_new_observation_and_admission'] is True
        assert result['scoped_click_and_post_observation_completed'] is (not click_error and not post_error)
        assert result['post_inspection_attempted'] is True
        if click_error:assert result['error']['message']=='PRIMARY_CLICK_FAILURE'
        else:assert result['error'] is None
        assert len(result['secondary_errors'])==int(click_error and post_error)
        if post_error:assert result['secondary_errors'][0]['message']=='SECONDARY_POST_FAILURE'
        rows.append({'control':'actual_navigation_sequences_'+name,'passed':True,
                     'explicit_seams':['Session.sequence (no Android)','assessment_summary (no private writes)'],
                     'operations':sess.calls,'business_outcome_unknown_retained':True})
    m.assessment_summary=orig_summary
    a=ast.parse((BASE/'owned_inspect.py').read_bytes());b=ast.parse((HERE/'owned_navigation.py').read_bytes())
    funcs=lambda t:{n.name:n for n in t.body if isinstance(n,ast.FunctionDef)}
    fa,fb=funcs(a),funcs(b)
    unchanged=['read','require_actual_install_binding','load_prior','actual_install','new_session','owned_scope']
    for name in unchanged:assert ast.dump(fa[name],include_attributes=False)==ast.dump(fb[name],include_attributes=False),name
    old_final=next(n.finalbody for n in fa['execute'].body if isinstance(n,ast.Try))
    new_final=next(n.finalbody for n in fb['execute'].body if isinstance(n,ast.Try))
    assert ast.dump(ast.Module(body=old_final,type_ignores=[]),include_attributes=False)==ast.dump(ast.Module(body=new_final,type_ignores=[]),include_attributes=False)
    rows.append({'control':'original_exact_cleanup_finally_and_identity_consumers_AST_unchanged','passed':True,'functions':unchanged})
    for name in ['owned_navigation.py','stage_execute.py','make_request.py','check_local.py']:
        ast.parse((HERE/name).read_bytes())
    return {'schema':1,'status':'LOCAL_NARROW_CONTROLS_PASS','controls':rows,'count':len(rows),
            'candidate_sha256':sha((HERE/'owned_navigation.py').read_bytes()),
            'Android_or_remote_actions':0,'whole_app_ready':False,'actual_click_not_run':True,
            'private_commercial_UI_exported':False}

if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
