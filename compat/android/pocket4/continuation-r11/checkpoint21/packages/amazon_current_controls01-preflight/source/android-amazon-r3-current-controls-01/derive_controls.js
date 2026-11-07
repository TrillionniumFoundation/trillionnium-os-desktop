function buildCurrentAmazonControlsSource(attribution,typedSource){
 const need=(v,m)=>{if(!v)throw Error(m)};
 const helperStart=attribution.indexOf("def one("),helperEnd=attribution.indexOf("\ndef main(",helperStart);
 need(helperStart>=0&&helperEnd>helperStart,"ATTRIBUTION_HELPERS");
 const helpers=attribution.slice(helperStart,helperEnd);
 const bodyStart=attribution.indexOf("    actual=json.loads(actual_raw)"),bodyEnd=attribution.indexOf("    report=",bodyStart);
 need(bodyStart>=0&&bodyEnd>bodyStart,"NINE_CASES");
 let cases=attribution.slice(bodyStart,bodyEnd);
 cases=cases.replace("passed('only_new_pure_helper_and_worker_except_change_entire_module_AST')","passed('full_declared_typed_source_inverse_and_original_attribution_guards')");
 let block=typedSource.slice(typedSource.indexOf("# Exercise the production Flow"),typedSource.indexOf("assert len(cases)==106"));
 block=block.replaceAll("IHG","AMAZON").replaceAll("base.","worker.").replaceAll("R2_Session","R3_Session");
 const oldPlan="inspect_plan={'search':worker.SEARCH_PLAN,'destination':worker.PLAN,\n            'post':worker.POST_PLAN,'readiness':worker.SEARCH_READINESS_PLANS}";
 need(block.includes(oldPlan),"TYPED_PLAN");block=block.replace(oldPlan,"inspect_plan=worker.PLAN");
 const start=block.indexOf("def typed_scope_fixture():"),end=block.indexOf("\ndef construct_flow(scope):",start);
 need(start>=0&&end>start,"TYPED_SCOPE");
 block=block.slice(0,start)+String.raw`def typed_scope_fixture():
    baseline={'schema':qa.MAIN_BASELINE_SCHEMA,'framework_epoch':{'sha256':qa.MAIN_EPOCH},
        'packages':{qa.PACKAGE:qa.UID}}
    ref=types.SimpleNamespace(current_baseline=lambda:baseline,EPOCH=qa.MAIN_EPOCH,
        BASELINE_SHA=qa.MAIN_BASELINE_SHA,QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA)
    return worker.scope_record(types.SimpleNamespace(ref=ref,adapter=adapter),'a'*64)

`+block.slice(end);
 block=block.split("\n").map(x=>x?"    "+x:x).join("\n");
 const source=String.raw`"""Current Amazon R3 exact attribution, plan, install, and typed constructor controls.

Every fixture is in memory. No original private UI tree, Main, file, child, or
Android entry is called. Historical failure/unknown receipts remain unchanged.
"""
import ast
import copy
import hashlib
import json
from pathlib import PurePosixPath
import types
NAME='retain_navigation_failure_observations'

def module(source,name):
    tree=ast.parse(source)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    value=types.ModuleType(name);value.__file__='/pure-control/'+name+'.py'
    value.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),value.__dict__)
    return value

`+helpers+String.raw`

def run_controls(p):
    sources=p['sources']
    qa=module(sources['contract'],'actual_amazon_r3_contract')
    adapter=module(sources['adapter'],'actual_amazon_r3_adapter')
    navigation=module(sources['business'],'original_amazon_search_navigation')
    context=module(sources['context'],'current_amazon_task_context')
    worker=module(sources['coordinator'],'current_amazon_coordinator')
    transport=module(sources['transport'],'current_amazon_bound_arun')
    assert qa.PROTOCOL=='pocket4-owned-amazon-qa-v3' and qa.SELF=='org.droidloom.qa.amazon.r3'
    assert type(worker.HELPER_UID) is int and worker.HELPER_UID==context.HELPER_UID==10154
    assert worker.INSTALLED['uid']==worker.HELPER_UID and worker.INSTALLED['package']==qa.SELF
    assert worker.CURRENT_EPOCH==context.CURRENT_EPOCH==qa.MAIN_EPOCH==transport.FRAMEWORK_EPOCH_SHA256
    assert worker.CURRENT_BASELINE_SHA==context.CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA
    assert worker.CURRENT_QUALIFICATION_SHA==context.CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA
    assert worker.CURRENT_HOST_MANIFEST==context.CURRENT_HOST_MANIFEST==adapter.RECORDER_MANIFEST_SHA
    old=ast.parse(p['attribution_baseline'])
    new=ast.parse(sources['coordinator'])
    previous=ast.parse(p['attribution_candidate'])
    # No guard body is silently removed: undo exactly the declared source edits.
    for name,prior,key in [('coordinator',p['attribution_candidate'],'coordinator_edits'),
                           ('context',p['prior_context'],'context_edits')]:
        restored=sources[name]
        for row in p['nonce_mapping']:
            restored=restored.replace(row['value'],row['slot'])
        for row in reversed(p[key]):
            assert restored.count(row['next'])==row['count']
            restored=restored.replace(row['next'],row['old'])
        assert restored==prior,name
    assert sources['business']==p['prior_business']
    assert ast.dump(one(new.body,ast.FunctionDef,NAME),include_attributes=False)==ast.dump(
        one(previous.body,ast.FunctionDef,NAME),include_attributes=False)
    assert [ast.dump(x,include_attributes=False) for x in handler(new).body]==[
        ast.dump(x,include_attributes=False) for x in handler(previous).body]
    actual_raw=p['attribution_actual_inspection']
`+cases+String.raw`
    assert len(cases)==9
    for name,source in sources.items():
        data=source.encode()
        assert p['bound_source_pins'][name]=={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        compile(source,'<seven-current-source-'+name+'>','exec')
    assert len(sources)==7
    passed('exact_current_R3_helper_and_seven_source_bindings_compile')
    plans=navigation.plans(worker.PLAN)
    for plan in plans:adapter.validate_plan(plan,qa)
    ordered=[worker.NONCE]
    for plan in worker.PLAN['stability']:
        ordered.extend(plan['nonces'][name] for name in ('before','inspect','after'))
    ordered.extend(worker.PLAN['entry']['nonces'][name] for name in ('before','inspect','action','after'))
    ordered.extend(worker.PLAN['post']['nonces'][name] for name in ('before','inspect','after'))
    assert ordered==p['fresh_nonce_values'] and len(ordered)==len(set(ordered))==32
    passed('production_adapter_validates_all_ten_plans_and_actual_thirty_two_nonce_order')
    install_docs={name:json.loads(p['actual_install'][name]) for name in ('coordinator','stage','worker')}
    observed=worker.actual_install(install_docs)
    assert observed['installed']==worker.INSTALLED and observed['actual_state_wire_sha256']==worker.STATE_WIRE
    passed('production_actual_install_accepts_exact_current_parent_worker_receipts')
    old_docs=copy.deepcopy(install_docs)
    old_docs['worker']['state']['helper']['protocol']='pocket4-owned-amazon-qa-v1'
    try:worker.actual_install(old_docs)
    except RuntimeError as error:assert str(error)=='ACTUAL_NO_AUTOMATION_STATE_REQUIRED'
    else:raise AssertionError('old Amazon helper protocol accepted')
    passed('production_actual_install_rejects_old_helper_protocol')
`+block+String.raw`
    assert len(cases)==30 and len({x['name'] for x in cases})==30
    return {'schema':1,'ok':True,'count':30,'cases':cases,
        'current_attribution_controls':9,'production_typed_constructor_controls':17,
        'production_scope_record_Flow_BoundArun_and_Session_executed':True,
        'production_actual_install_and_all_plan_validators_executed':True,
        'current_typed_source_exact_declared_inverse':True,
        'unchanged_search_readiness_and_full_tree_action_guards':True,
        'historical_failure_unknown_not_reclassified':True,
        'all_fixtures_in_memory':True,'file_writes':0,'child_processes':0,
        'Android_actions':0,'Main_accessed':False,'real_Java_helper_executed':False,
        'runtime_UI_dispatched':False,'whole_app_production_ready':False}
`;
 return {source,planned_controls:30};
}
