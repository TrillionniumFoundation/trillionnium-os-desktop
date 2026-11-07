function buildCurrentBestBuyControlsSource(old,typedBlockSource){
 const need=(v,m)=>{if(!v)throw Error(m)};let s=old;const edits=[];
 const e=(a,b,n=1)=>{need(s.split(a).length-1===n,"BB_CONTROL_ANCHOR:"+a.slice(0,100));s=s.split(a).join(b);edits.push({old:a,next:b,count:n});};
 const at=s.indexOf("    cases=[]");need(at>0,"original header");
 const oldHeader=s.slice(0,at);
 const header=String.raw`"""Current BestBuy R3 complete-tree readiness, original Session, and typed constructor controls.

All source and historical metadata fixtures are exact in-memory payload strings.
No live Main, private tree, filesystem, process, or Android entry is called.
"""
import ast
import copy
import hashlib
import json
from pathlib import PurePosixPath
import types

def module(source,name):
    tree=ast.parse(source)
    tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='HERE' for t in n.targets))]
    value=types.ModuleType(name);value.__file__='/pure-control/'+name+'.py'
    value.HERE=PurePosixPath('/pure-control')
    exec(compile(tree,'<pure-module-'+name+'>','exec'),value.__dict__)
    return value

def run_controls(p):
    sources=p['sources']
    r=module(sources['business'],'bestbuy_r3_readiness')
    context=module(sources['context'],'bestbuy_current_task_context')
    worker=module(sources['coordinator'],'bestbuy_current_coordinator')
    qa=module(sources['contract'],'actual_bestbuy_r3_contract')
    adapter=module(sources['adapter'],'actual_bestbuy_r3_adapter')
    transport=module(sources['transport'],'actual_bestbuy_current_bound_arun')
    assert qa.PROTOCOL=='pocket4-owned-bestbuy-qa-v3' and qa.SELF=='org.droidloom.qa.bestbuy.r3'
    assert type(worker.HELPER_UID) is int and worker.HELPER_UID==context.HELPER_UID==10155
    assert worker.INSTALLED['uid']==worker.HELPER_UID and worker.INSTALLED['package']==qa.SELF
    assert worker.CURRENT_EPOCH==context.CURRENT_EPOCH==qa.MAIN_EPOCH==transport.FRAMEWORK_EPOCH_SHA256
    assert worker.CURRENT_BASELINE_SHA==context.CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA
    assert worker.CURRENT_QUALIFICATION_SHA==context.CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA
    assert worker.CURRENT_HOST_MANIFEST==context.CURRENT_HOST_MANIFEST==adapter.RECORDER_MANIFEST_SHA
`;
 e(oldHeader,header);
 e("    def defs(path):\n        return {x.name:ast.dump(x,include_attributes=False) for x in ast.parse(path.read_text()).body\n                if isinstance(x,(ast.FunctionDef,ast.ClassDef))}",
   "    def defs(source):\n        return {x.name:ast.dump(x,include_attributes=False) for x in ast.parse(source).body\n                if isinstance(x,(ast.FunctionDef,ast.ClassDef))}");
 const oldCompare="    old=defs(BASE/'android-bestbuy-launch-inspect-01/bestbuy_task_context.py')\n"+
 "    new=defs(CANDIDATE/'bestbuy_task_context.py')\n"+
 "    assert old['Flow']==new['Flow'] and old['open_task_context']==new['open_task_context']\n"+
 "    original=defs(BASE/'android-bestbuy-launch01-public-roles-reader-01/read_roles.py')\n"+
 "    current=defs(CANDIDATE/'bestbuy_readiness.py')\n"+
 "    for name in ('need','sha','no_raw_ui','validated_assessment','public_role_counts'):\n"+
 "        assert original[name]==current[name],name\n"+
 "    passed('Flow_open_context_and_original_public_count_validators_AST_unchanged')";
 const nextCompare=String.raw`    restored=sources['context']
    for row in reversed(p['context_edits']):
        assert restored.count(row['next'])==row['count']
        restored=restored.replace(row['next'],row['old'])
    assert restored==p['prior_context']
    old=defs(p['prior_context']);new=defs(sources['context'])
    assert old['Policy']==new['Policy']
    current_business=sources['business']
    assert current_business.count('=='+str(worker.HELPER_UID))==2
    restored_business=current_business.replace('=='+str(worker.HELPER_UID),'==10198')
    assert restored_business==p['prior_business']
    original=defs(p['prior_business']);current=defs(restored_business)
    for name in ('need','sha','no_raw_ui','validated_assessment','public_role_counts'):
        assert original[name]==current[name],name
    passed('exact_declared_typed_context_inverse_and_original_public_count_guards')
    assert len(sources)==7
    for name,source in sources.items():
        data=source.encode()
        assert p['bound_source_pins'][name]=={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        compile(source,'<all-seven-bound-'+name+'>','exec')
    passed('exact_current_R3_helper_and_seven_source_bindings_compile')
    values=[worker.NONCE]
    for plan in worker.PLANS:
        adapter.validate_plan(plan,qa)
        values.extend(plan['nonces'][name] for name in ('before','inspect','after'))
    assert values==p['fresh_nonce_values'] and len(values)==len(set(values))==10
    passed('production_adapter_validates_all_three_plans_and_actual_ten_nonce_order')
    install_docs={name:json.loads(p['actual_install'][name]) for name in ('coordinator','stage','worker')}
    observed=worker.actual_install(install_docs)
    assert observed['installed']==worker.INSTALLED and observed['actual_state_wire_sha256']==worker.STATE_WIRE
    passed('production_actual_install_validator_accepts_exact_current_parent_worker_receipts')
    old_protocol_docs=copy.deepcopy(install_docs)
    old_protocol_docs['worker']['state']['helper']['protocol']='pocket4-owned-bestbuy-qa-v1'
    rejected('production_actual_install_validator_rejects_old_helper_protocol',
        lambda:worker.actual_install(old_protocol_docs),'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')`;
 e(oldCompare,nextCompare);
 e("    meta_path=BASE/'root-recovery-20261104-02/evidence/bestbuy-launch-five-results-read01/inspect.json'\n    raw=meta_path.read_bytes()",
   "    raw=p['historical_inspect'].encode()");
 e("    sequence=copy.deepcopy(safe['sequence'])\n    metadata=copy.deepcopy(safe['assessments'])",
   "    sequence=copy.deepcopy(safe['sequence'])\n"+
   "    # This is an explicitly synthetic protocol fixture, never current task authority.\n"+
   "    for key in ('foreground_before','foreground_after'):\n"+
   "        sequence[key].update(main_epoch_sha256=qa.MAIN_EPOCH,main_baseline_schema=qa.MAIN_BASELINE_SCHEMA,\n"+
   "            main_baseline_sha256=qa.MAIN_BASELINE_SHA,\n"+
   "            main_baseline_qualification_sha256=qa.MAIN_BASELINE_QUALIFICATION_SHA)\n"+
   "    sequence['installed_before']=copy.deepcopy(worker.INSTALLED)\n"+
   "    sequence['installed_after']=copy.deepcopy(worker.INSTALLED)\n"+
   "    sequence['post_termination_state']['helper_uid']=worker.HELPER_UID\n"+
   "    metadata=copy.deepcopy(safe['assessments'])");
 e("    counters=copy.deepcopy(metadata['inspect']['tree_observations'])",
   "    counters=copy.deepcopy(metadata['inspect']['tree_observations'])\n"+
   "    # Synthetic current-protocol limit, not a claim about the historical capture.\n"+
   "    counters[0]['depth_limit']=qa.MAX_DEPTH");
 e("'self_uid':10198","'self_uid':worker.HELPER_UID",2);
 e("step=Path('/synthetic-bestbuy-control-step')","step=PurePosixPath('/synthetic-bestbuy-control-step')");
 e("worker_tree=ast.parse((CANDIDATE/'owned_inspect.py').read_text())","worker_tree=ast.parse(sources['coordinator'])");
 e('assert "\'semantic_ready\'" in (CANDIDATE/\'owned_inspect.py\').read_text()','assert "\'semantic_ready\'" in sources[\'coordinator\']');
 let block=typedBlockSource.slice(typedBlockSource.indexOf("# Exercise the production Flow"),typedBlockSource.indexOf("assert len(cases)==106"));
 need(block.includes("def construct_flow(scope):")&&block.includes("passed('constructed_current_scope_mutation_stops_before_Main_target_or_IO')"),"TYPED17_SOURCE");
 block=block.replaceAll("IHG","BESTBUY").replaceAll("base.","worker.").replaceAll("amazon_task_source_manifest_sha256","bestbuy_task_source_manifest_sha256").replaceAll("R2_Session","R3_Session");
 const oldPlan="inspect_plan={'search':worker.SEARCH_PLAN,'destination':worker.PLAN,\n            'post':worker.POST_PLAN,'readiness':worker.SEARCH_READINESS_PLANS}";
 need(block.includes(oldPlan),"TYPED_PLAN");block=block.replace(oldPlan,"inspect_plan=worker.PLANS");
 block=block.replace("qa.PACKAGE+'/.activity.MainActivity'","worker.COMPONENT");
 const fixtureStart=block.indexOf("def typed_scope_fixture():");
 const fixtureEnd=block.indexOf("\ndef construct_flow(scope):",fixtureStart);
 need(fixtureStart>=0&&fixtureEnd>fixtureStart,"TYPED_FIXTURE_FUNCTION");
 block=block.slice(0,fixtureStart)+String.raw`def typed_scope_fixture():
    baseline={'schema':qa.MAIN_BASELINE_SCHEMA,'framework_epoch':{'sha256':qa.MAIN_EPOCH},
        'packages':{qa.PACKAGE:qa.UID}}
    ref=types.SimpleNamespace(current_baseline=lambda:baseline,EPOCH=qa.MAIN_EPOCH,
        BASELINE_SHA=qa.MAIN_BASELINE_SHA,QUALIFICATION_SHA=qa.MAIN_BASELINE_QUALIFICATION_SHA)
    return worker.scope_record(types.SimpleNamespace(ref=ref,adapter=adapter),'a'*64)

`+block.slice(fixtureEnd);
 block=block.split("\n").map(line=>line?"    "+line:line).join("\n");
 e("    report={'schema':1,'ok':True,'count':len(cases),'cases':cases,",block+"\n    assert len(cases)==59 and len({x['case'] for x in cases})==59\n"+
 "    report={'schema':1,'ok':True,'count':len(cases),'cases':cases,");
 e("'production_Flow_open_task_context_and_shared_helper_sources_unchanged':True","'typed_context_declared_inverse_verified':True,\n        'production_Flow_BoundArun_Session_constructors_executed':True,\n        'production_typed_constructor_controls':17,\n        'production_actual_install_and_adapter_plan_validators_executed':True");
 e("    print(json.dumps(report,indent=2,sort_keys=True))\n\n\nif __name__=='__main__':main()","    return report");
 need(!s.includes("BASE/")&&!s.includes("CANDIDATE/")&&!s.includes(".read_bytes()")&&!s.includes(".read_text()"),"NO_REAL_FIXTURE_FILE_READS");
 return {source:s,edits,planned_controls:59};
}
