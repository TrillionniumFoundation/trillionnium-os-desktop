"""Pure controls for the exact candidate function. No device or process invocation."""
import ast, copy, hashlib, json, re, secrets, sys
from pathlib import PurePosixPath
from types import SimpleNamespace

raw=sys.stdin.buffer.read(131073)
assert len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=='5aa00cf4f5db2448a023bfcf82a24c25ffa34224620bfd716923f00d4de9f27c'
packet=json.loads(raw)
assert set(packet)=={'schema','original_source','template_source','nonce_slots','nonce_exclusions'} and packet['schema']==1
original=packet['original_source']; template=packet['template_source']
assert hashlib.sha256(original.encode()).hexdigest()=='14c72e48693aba988d78258851f534302f3898c519cf94bf20ae2f8997c5de6b'
assert hashlib.sha256(template.encode()).hexdigest()=='98c90a686bfac4b3369e31d568e6742017a638d6f6a9674b5e9cec0dd6bc856c'
slots=packet['nonce_slots']; exclusions=packet['nonce_exclusions']
assert len(slots)==len(set(slots))==146 and len(exclusions)==len(set(exclusions))==136
assert all(isinstance(x,str) and re.fullmatch('[0-9a-f]{32}',x) for x in slots[:134]+exclusions)
assert set(slots[:134])<=set(exclusions)
assert slots[134:]==['BILI_NEW_STABILITY_SLOT_'+str(i).zfill(8) for i in range(12)]
for value in (original,template): compile(value,'<source-only-no-module-execution>','exec')
old_ast=ast.parse(original); new_ast=ast.parse(template)
changed_functions={'fixed_plan','stable_before_click','durable_phase'}
changed_assignments={'STABILITY_PLANS','FIRST_STABILITY_SECONDS','FIRST_STABILITY_MATCHES','FIRST_STABILITY_SPAN_MS'}
def keep(node):
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in changed_functions:return False
    if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in changed_assignments:return False
    return True
def dump(nodes):return ast.dump(ast.Module(body=nodes,type_ignores=[]),include_attributes=False)
assert dump([x for x in old_ast.body if keep(x)])==dump([x for x in new_ast.body if keep(x)])
old_functions={x.name:ast.get_source_segment(original,x) for x in old_ast.body if isinstance(x,ast.FunctionDef)}
new_functions={x.name:ast.get_source_segment(template,x) for x in new_ast.body if isinstance(x,ast.FunctionDef)}
assert set(old_functions)==set(new_functions)
unchanged=[n for n in old_functions if n not in changed_functions]
assert all(old_functions[n]==new_functions[n] for n in unchanged)
assert not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='sleep'
               for x in ast.walk(next(x for x in new_ast.body if isinstance(x,ast.FunctionDef) and x.name=='stable_before_click')))
def literal_scope(text):
    tree=ast.parse(text)
    env={'json':json,'re':re,'hashlib':hashlib,'__name__':'pure_control_namespace'}
    def put(target,value):
        if isinstance(target,ast.Name):env[target.id]=value
        elif isinstance(target,(ast.Tuple,ast.List)):
            assert len(target.elts)==len(value)
            for t,v in zip(target.elts,value):put(t,v)
        else:raise AssertionError('unsupported literal target')
    for node in tree.body:
        if not isinstance(node,ast.Assign):continue
        try:value=ast.literal_eval(node.value)
        except (ValueError,TypeError):continue
        for target in node.targets:put(target,value)
    selected=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in
              {'require','sha','fixed_plan','stable_before_click','durable_phase'}]
    assert len(selected)==5
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<exact-production-functions>','exec'),env)
    env['FLOW']=PurePosixPath('/pure-control/no-files-created')
    return env
results=[]
def record(name,**extra):results.append({'name':name,'passed':True,**extra})
def must_fail(name,callback,error):
    try:callback()
    except RuntimeError as exc:assert str(exc)==error,(name,str(exc),error)
    else:raise AssertionError(name+': required rejection missing')
    record(name)
unbound=literal_scope(template)
must_fail('unbound_template_cannot_pass_plan_admission',unbound['fixed_plan'],'FRESH_DISTINCT_NONCES_REQUIRED')
synthetic={slot:format(i+1,'032x') for i,slot in enumerate(slots)}
assert not set(synthetic.values())&set(exclusions)
test_source=template
for old,new in synthetic.items():test_source=test_source.replace(old,new)
compile(test_source,'<synthetic-controls-only>','exec')
plan_env=literal_scope(test_source)
assert plan_env['fixed_plan']()==plan_env['PLAN']
assert plan_env['STABILITY_SECONDS']==12 and plan_env['FIRST_STABILITY_SECONDS']==20
assert len(plan_env['STABILITY_PLANS'])==8 and len(plan_env['QUERY_STABILITY_PLANS'])==len(plan_env['SUBMIT_STABILITY_PLANS'])==4
record('valid_bound_plan_and_unchanged_later_budgets')
def plan_negative(name,change,error):
    env=literal_scope(test_source);change(env);must_fail(name,env['fixed_plan'],error)
plan_negative('seven_first_reads_rejected',lambda e:e['STABILITY_PLANS'].pop(),'EXACT_READ_ONLY_STABILITY_PLANS_REQUIRED')
plan_negative('nine_first_reads_rejected',lambda e:e['STABILITY_PLANS'].append(copy.deepcopy(e['STABILITY_PLANS'][0])),'EXACT_READ_ONLY_STABILITY_PLANS_REQUIRED')
plan_negative('query_budget_change_rejected',lambda e:e['QUERY_STABILITY_PLANS'].pop(),'EXACT_READ_ONLY_STABILITY_PLANS_REQUIRED')
plan_negative('submit_budget_change_rejected',lambda e:e['SUBMIT_STABILITY_PLANS'].append(copy.deepcopy(e['SUBMIT_STABILITY_PLANS'][0])),'EXACT_READ_ONLY_STABILITY_PLANS_REQUIRED')
plan_negative('input_in_sampling_rejected',lambda e:e['STABILITY_PLANS'][0].update(operation='click'),'EXACT_READ_ONLY_STABILITY_PLANS_REQUIRED')
plan_negative('duplicate_sampling_nonce_rejected',lambda e:e['STABILITY_PLANS'][1]['nonces'].update(inspect=e['STABILITY_PLANS'][0]['nonces']['inspect']),'FRESH_DISTINCT_NONCES_REQUIRED')
plan_negative('old_state_nonce_rejected',lambda e:e['STABILITY_PLANS'][0]['nonces'].update(inspect=e['OLD_STATE_NONCE']),'FRESH_DISTINCT_NONCES_REQUIRED')
plan_negative('result_read_budget_unchanged',lambda e:e['RESULT_OBSERVATION_PLANS'].pop(),'ONLY_EIGHT_ADDITIONAL_READ_ONLY_RESULT_PLANS')
plan_negative('public_query_constraint_unchanged',lambda e:e.update(PUBLIC_QUERY='control-only-wrong-query'),'ONLY_THE_FIXED_OBSERVED_PUBLIC_QUERY_PLAN')
record('unchanged_function_source_and_remaining_module_ast',functions=len(unchanged))

def sample(start,tag='a',wall=None,**extra):
    row={'start':start,'end':start+100,'tag':tag,'wall':(start+100)/1000 if wall is None else wall}
    row.update(extra);return row
class Clock:
    def __init__(self,overrides):self.value=0;self.calls=0;self.overrides=overrides or {}
    def monotonic(self):
        self.calls+=1
        return self.overrides.get(self.calls,self.value)
def stable_case(name,rows,error=None,calls=None,matching=None,overrides=None):
    env=literal_scope(test_source);clock=Clock(overrides);env['time']=clock
    installed={'identity':'synthetic-control-only'}
    summary_calls=[]
    class Session:
        def __init__(self):self.calls=[]
        def sequence(self,plan):
            index=len(self.calls)
            assert index<len(rows),'unexpected extra read'
            assert plan==env['STABILITY_PLANS'][index] and plan['operation']=='inspect'
            assert not any(set(plan['nonces'].values())&set(p['nonces'].values()) for p in self.calls)
            self.calls.append(plan);row=rows[index];clock.value=row['wall']
            if row.get('session_error'):raise RuntimeError(row['session_error'])
            return {'installed_before':row.get('installed_before',installed),
                    'installed_after':row.get('installed_after',installed),
                    'restoration_qualified':row.get('restoration',True),
                    'after_state_completed':row.get('after_state',True),
                    'foreground_after':row.get('foreground',{'task':1,'activity':'synthetic-expected'}),
                    'accessibility_restoration':{'state_after':row.get('state',{'connected':False})},
                    '_row':row}
    session=Session()
    def summaries(prior,qa,step,sequence,plan):
        summary_calls.append(plan)
        row=sequence['_row']
        if row.get('summary_error'):raise RuntimeError(row['summary_error'])
        return {'inspect':{'tree_sha256':row.get('tree',row['tag']*64),
                           'window_sha256':row.get('window','f'*64),
                           'node_count':row.get('count',10),
                           'tree_observations':[{'began_elapsed_ms':row['start'],'last_elapsed_ms':row['end']}]}}
    env['assessment_summary']=summaries
    result={}
    try:env['stable_before_click'](None,None,SimpleNamespace(step='synthetic-no-file'),session,installed,result)
    except RuntimeError as exc:
        assert error is not None and str(exc)==error,(name,str(exc),error)
        assert result['pre_action_stability']['qualified'] is False
    else:
        assert error is None,name+': missing failure'
        state=result['pre_action_stability']
        assert state['qualified'] is True and state['matching_sequences']==matching
        assert state['sampled_capture_span_ms']>=4000 and len(state['matching_sequences'])>=3
        assert state['future_action_still_requires_original_strict_freshness'] is True
    assert len(session.calls)==calls,(name,len(session.calls),calls)
    assert all(p['operation']=='inspect' for p in session.calls)
    assert result['pre_action_stability']['action_retried'] is False
    assert result['pre_action_stability']['failed_reads_retried'] is False
    record(name,reads=len(session.calls),summary_calls=len(summary_calls),input_actions=0)
stable_case('three_samples_exact_span', [sample(0),sample(2100),sample(4100)],calls=3,matching=[1,2,3])
stable_case('three_fast_samples_do_not_qualify', [sample(i*400) for i in range(8)],error='COMPLETE_TREE_NOT_STABLE_IN_BOUNDED_READS',calls=8)
stable_case('two_samples_even_long_span_do_not_qualify', [sample(0),sample(4100)]+[sample(4300+i*200,chr(98+i)) for i in range(6)],error='COMPLETE_TREE_NOT_STABLE_IN_BOUNDED_READS',calls=8)
stable_case('span_3999_is_insufficient', [sample(0),sample(2000),sample(4099)]+[sample(4300+i*200,chr(98+i)) for i in range(5)],error='COMPLETE_TREE_NOT_STABLE_IN_BOUNDED_READS',calls=8)
stable_case('fourth_read_change_can_qualify_seventh', [sample(0),sample(1000),sample(2000),sample(3000,'b'),sample(4500,'b'),sample(6000,'b'),sample(7500,'b')],calls=7,matching=[4,5,6,7])
stable_case('fifth_read_change_can_qualify_eighth', [sample(0),sample(900),sample(1800),sample(2700),sample(4000,'b'),sample(5500,'b'),sample(7000,'b'),sample(8500,'b')],calls=8,matching=[5,6,7,8])
stable_case('old_key_return_starts_new_run', [sample(0),sample(1500),sample(3000,'b'),sample(4500),sample(6600),sample(8600)],calls=6,matching=[4,5,6])
for field,value in [('tree','b'*64),('window','e'*64),('count',11),('foreground',{'task':2,'activity':'synthetic-expected'}),('state',{'connected':True})]:
    stable_case('full_key_'+field+'_change_resets_run',
                [sample(0),sample(2000)]+[sample(t,**{field:value}) for t in (4200,6300,8400)],
                calls=5,matching=[3,4,5])
for field,value in [('installed_before',{'wrong':'identity'}),('installed_after',{'wrong':'identity'}),('restoration',False),('after_state',False)]:
    stable_case(field+'_failure_stops_without_retry',[sample(0),sample(2100,**{field:value}),sample(4100)],
                error='STABILITY_READ_INSTALL_AND_RESTORATION_REQUIRED',calls=2)
stable_case('read_failure_stops_without_retry',[sample(0),sample(2100,session_error='SYNTHETIC_READ_FAILURE'),sample(4100)],error='SYNTHETIC_READ_FAILURE',calls=2)
stable_case('assessment_failure_stops_without_retry',[sample(0),sample(2100,summary_error='SYNTHETIC_ASSESSMENT_REJECTED'),sample(4100)],error='SYNTHETIC_ASSESSMENT_REJECTED',calls=2)
stable_case('capture_order_reversal_rejected',[sample(0),sample(50),sample(4100)],error='STABILITY_CAPTURE_ORDER_REQUIRED',calls=2)
stable_case('deadline_after_read_prevents_qualification',[sample(0),sample(2100),sample(4100,wall=20.001)],error='STABILITY_OBSERVATION_DEADLINE',calls=3)
stable_case('deadline_before_read_stops_next_read',[sample(0),sample(2100)],error='STABILITY_OBSERVATION_DEADLINE',calls=1,overrides={5:20.001})
stable_case('exact_deadline_is_inclusive',[sample(0),sample(2100),sample(4100,wall=20)],calls=3,matching=[1,2,3])
stable_case('eight_nonmatching_samples_exhaust_budget',[sample(i*1500,chr(97+i)) for i in range(8)],error='COMPLETE_TREE_NOT_STABLE_IN_BOUNDED_READS',calls=8)

def durable_value(env):
    value={'ok':True,'phase':'navigate','nonce':env['NONCE'],'helper_uid':env['UID'],
           'runtime_recorder_manifest_sha256':env['R4_MANIFEST'],'outcome_unknown':True,
           'final_Main_guard_passed':True,'held_binding_released':True,'action_lock_released':True,
           'pre_action_stability':{'qualified':True,'maximum_sequences':8,'deadline_seconds':20,
               'minimum_matching_sequences':3,'minimum_capture_span_ms':4000,
               'matching_sequences':[1,2,3],'sampled_capture_span_ms':4000,
               'future_action_still_requires_original_strict_freshness':True},
           'search_page_stability':{'before_set_text':{'qualified':True},'before_submit':{'qualified':True}},
           'submit_admission':{'public_value_observed':True},
           'submit_action_bound_value':{'public_value_observed':True},
           'player_content_readiness':{'qualified':True},
           'result_content_observation':{'qualified':True},
           'business_success_verified':False}
    for name in ('action_attempted','video_click_and_observations_completed','player_content_readiness_completed',
                 'controls_reveal_and_observation_completed','playback_button_transitions_completed',
                 'results_container_content_observed','scoped_click_and_post_observation_completed',
                 'query_submission_controls_completed','final_results_inspection_completed','business_outcome_unknown'):
        value[name]=True
    return value
def durable_case(name,change=None,error=None):
    env=literal_scope(test_source);value=durable_value(env)
    if change:change(value)
    encoded=json.dumps(value).encode()
    env['read']=lambda path:encoded
    if error:must_fail(name,lambda:env['durable_phase'](value,'navigate'),error)
    else:
        got,pin=env['durable_phase'](value,'navigate')
        assert got==value and pin['bytes']==len(encoded) and pin['sha256']==hashlib.sha256(encoded).hexdigest()
        record(name)
durable_case('durable_new_sampling_gate_accepts_exact_valid_summary')
for name,change in [
    ('durable_old_maximum_rejected',lambda v:v['pre_action_stability'].update(maximum_sequences=4)),
    ('durable_old_deadline_rejected',lambda v:v['pre_action_stability'].update(deadline_seconds=12)),
    ('durable_only_two_matches_rejected',lambda v:v['pre_action_stability'].update(matching_sequences=[1,2])),
    ('durable_short_span_rejected',lambda v:v['pre_action_stability'].update(sampled_capture_span_ms=3999)),
    ('durable_future_guard_must_remain',lambda v:v['pre_action_stability'].update(future_action_still_requires_original_strict_freshness=False))]:
    durable_case(name,change,'ACTUAL_PRE_ACTION_COMPLETE_TREE_STABILITY_REQUIRED')
durable_case('unknown_outcome_must_not_be_relabelled',lambda v:v.update(outcome_unknown=False),'ACTUAL_DURABLE_PHASE_REQUIRED:navigate')
durable_case('whole_business_success_must_stay_false',lambda v:v.update(business_success_verified=True),'CLICK_OBSERVATION_SCOPE_MUST_RETAIN_UNKNOWN_BUSINESS_OUTCOME')
assert len(results)==43,('unexpected control inventory',len(results))
pool=[]
for _ in range(1024):
    value=secrets.token_hex(16)
    if value not in exclusions and value not in pool:pool.append(value)
    if len(pool)==146:break
assert len(pool)==146,'bounded secrets nonce generation exhausted'
bound=template
for old,new in zip(slots,pool):bound=bound.replace(old,new)
assert not any(slot in bound for slot in slots)
compile(bound,'<fresh-bound-source-only>','exec')
bound_env=literal_scope(bound);assert bound_env['fixed_plan']()==bound_env['PLAN']
out={'schema':1,'ok':True,'state':'EXACT_PRODUCTION_FUNCTION_PURE_CONTROLS_PASS',
     'original_source_sha256':hashlib.sha256(original.encode()).hexdigest(),
     'template_source_sha256':hashlib.sha256(template.encode()).hexdigest(),
     'bound_navigation_sha256_before_new_root':hashlib.sha256(bound.encode()).hexdigest(),
     'control_stdin_sha256':hashlib.sha256(raw).hexdigest(),'controls':results,
     'python_full_source_compile':True,'exact_candidate_function_executed_with_synthetic_session':True,
     'real_qa_parser_executed':False,'private_UI_or_app_readiness_verified':False,
     'Android_actions':0,'process_or_device_commands':0,'file_writes':0,'production_module_executed':False,
     'secrets_nonce_pool':pool,'nonce_pool_size':len(pool),'nonce_pool_disjoint_originals':not bool(set(pool)&set(exclusions)),
     'runtime_flow_dispatched':False,'whole_app_production_ready':False}
encoded=json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))
assert len(encoded.encode())<=32768
print(encoded,flush=True)
