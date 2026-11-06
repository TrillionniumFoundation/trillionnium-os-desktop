"""Pure attribution controls; no imported project module or device action."""
import ast
import copy
import hashlib
import json
import types

BASELINE_SHA='c9a430a8260db4d9189bd56fe42b425538f47b76b410ff6a0fc0ed9786e175c6'
CANDIDATE_SHA='0e861800ce12cbb63f9ca5cfa80abbf9ecf9bfde00392c2d03cae9827af31ec1'
ACTUAL_SHA='682e902089a959915d4f3b3f75616cdccd60f9ef76c68ddf78d96fe7c72018a2'
NAME='retain_navigation_failure_observations'


def one(nodes, kind, name=None):
    rows=[n for n in nodes if isinstance(n,kind) and (name is None or n.name==name)]
    assert len(rows)==1
    return rows[0]


def handler(module):
    worker=one(module.body,ast.FunctionDef,'worker')
    block=one([n for n in worker.body if isinstance(n,ast.Try) and n.finalbody],ast.Try)
    assert len(block.handlers)==1
    return block.handlers[0]


def execute_handler(module, seed, last, phase='inspect'):
    result=copy.deepcopy(seed)
    primary=RuntimeError('retained primary')
    calls=[]
    def remember(value,current,error):
        assert value is result and current=='original_phase' and error is primary
        calls.append(True)
    scope={'result':result,'phase':phase,'session':types.SimpleNamespace(sequence_observation=last),
           'u':types.SimpleNamespace(remember=remember),'current':'original_phase','error':primary}
    definitions=[copy.deepcopy(n) for n in module.body if isinstance(n,ast.FunctionDef) and n.name==NAME]
    source=ast.fix_missing_locations(ast.Module(body=definitions+copy.deepcopy(handler(module).body),type_ignores=[]))
    exec(compile(source,'<attribution-handler-only>','exec'),scope)
    assert calls==[True] and result.get('error')==seed.get('error')
    assert result.get('search_entry')==seed.get('search_entry')
    return result


def main(candidate, baseline, actual_raw):
    assert hashlib.sha256(candidate.encode()).hexdigest()==CANDIDATE_SHA
    assert hashlib.sha256(baseline.encode()).hexdigest()==BASELINE_SHA
    assert hashlib.sha256(actual_raw.encode()).hexdigest()==ACTUAL_SHA
    old=ast.parse(baseline);new=ast.parse(candidate)
    normalized=copy.deepcopy(new)
    normalized.body=[n for n in normalized.body if not(isinstance(n,ast.FunctionDef) and n.name==NAME)]
    handler(normalized).body=copy.deepcopy(handler(old).body)
    assert ast.dump(normalized,include_attributes=False)==ast.dump(old,include_attributes=False)
    actual=json.loads(actual_raw)
    original=actual['search_entry']['failed_sequence_observation']
    post=actual['search_entry']['post_sequence']
    assert original['restoration_qualified'] is False and post['restoration_qualified'] is True
    assert actual['error']['details']['previous_details']['owned_helper_failure']['helper_rejection']['error']=='TREE_CHANGED_NULL_CHILD'
    assert actual['failed_sequence_observation']==post
    cases=[]
    def passed(name):cases.append({'name':name,'passed':True})
    passed('only_new_pure_helper_and_worker_except_change_entire_module_AST')
    seed={'error':actual['error'],'search_entry':actual['search_entry']}
    old_result=execute_handler(old,seed,post)
    assert old_result['failed_sequence_observation']==post
    passed('actual_old_top_level_overwrites_first_failure_with_successful_post')
    new_result=execute_handler(new,seed,post)
    assert new_result['failed_sequence_observation']==original
    assert new_result['independent_post_sequence_observation']==post
    assert 'independent_failed_post_sequence_observation' not in new_result
    passed('actual_first_failure_and_independent_successful_post_both_retained')
    failed_post={'error':{'phase':'post-only'},'restoration_qualified':False,'test_marker':'post_failure'}
    early={'error':{'phase':'stable_search_entry_or_click'},'failed_sequence_observation':original,
           'failed_post_sequence_observation':failed_post}
    result=execute_handler(new,{'error':{'original':1},'search_entry':early},failed_post)
    assert result['failed_sequence_observation']==original and result['independent_failed_post_sequence_observation']==failed_post
    passed('secondary_post_failure_never_replaces_earlier_sequence')
    post_first={'error':{'phase':'independent_post_entry_inspection'},'failed_post_sequence_observation':failed_post}
    result=execute_handler(new,{'error':{'original':2},'search_entry':post_first},failed_post)
    assert result['failed_sequence_observation']==failed_post and result['independent_failed_post_sequence_observation']==failed_post
    passed('post_first_failure_is_primary_when_no_earlier_failure')
    missing={'error':{'phase':'stable_search_entry_or_click'},'failed_post_sequence_observation':failed_post}
    result=execute_handler(new,{'error':{'original':3},'search_entry':missing},post)
    assert 'failed_sequence_observation' not in result and result['independent_failed_post_sequence_observation']==failed_post
    passed('missing_primary_observation_does_not_fall_back_to_secondary_or_last')
    result=execute_handler(new,{'error':{'original':4}},post)
    assert 'failed_sequence_observation' not in result
    passed('no_navigation_record_does_not_invent_failure_from_stale_session')
    result=execute_handler(new,{'error':{'original':5},'search_entry':{'error':None,'post_sequence':post}},post)
    assert 'failed_sequence_observation' not in result and result['independent_post_sequence_observation']==post
    passed('later_non_sequence_failure_keeps_post_separate')
    result=execute_handler(new,{'error':{'original':6}},post,'launch')
    assert result['failed_sequence_observation']==post
    passed('non_inspect_original_handler_behavior_unchanged')
    report={'schema':1,'state':'PASS_ATTRIBUTION_CONTROLS_ONLY','count':len(cases),'controls':cases,
            'baseline_sha256':BASELINE_SHA,'candidate_sha256':CANDIDATE_SHA,'actual_inspection_sha256':ACTUAL_SHA,
            'whole_module_AST_except_declared_delta_equal':True,'original_first_error_and_navigation_records_preserved':True,
            'new_UI_request_generated':False,'device_actions':0,'Main_accessed':False,'process_children':0,'new_files':0,
            'production_or_App_qualification':False}
    print(json.dumps(report,sort_keys=True),flush=True)
    return 0
