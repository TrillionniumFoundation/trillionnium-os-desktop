function buildIhgCurrentControls(h,oldHarness,sources,helperFiles,transportSource,nonceSpec){
  const need=(v,m)=>{if(!v)throw Error(m)};
  const once=(s,a,b)=>{need(s.split(a).length===2,"control anchor "+a.slice(0,80));return s.replace(a,b)};
  need(nonceSpec.count===36&&nonceSpec.exclude_count===337&&new Set(nonceSpec.exclude_values).size===337,"current nonce specification");
  const names={contract:helperFiles["qa_contract.py"],adapter:helperFiles["qa_adapter.py"],
    public_destination:sources["public_destination.py"],context:sources["ihg_task_context.py"],
    coordinator:sources["owned_inspect.py"],stage:sources["stage_execute.py"],transport:transportSource};
  need(Object.values(names).every(x=>typeof x==="string"),"full exact source texts");
  const payload={schema:2,...names,nonce_slots:nonceSpec.slot_mapping.map(x=>x.slot),nonce_exclusions:nonceSpec.exclude_values};
  const raw=JSON.stringify(payload), pins=Object.fromEntries(Object.entries(names).map(([name,s])=>[name,{bytes:h.utf8(s).length,sha256:h.sha(s)}]));
  need(h.utf8(raw).length<=262144,"pure controls input bound");
  let s=oldHarness;
  s=once(s,'"""Original IHG R1 Session/Policy and bounded full Search readiness with synthetic I/O only."""',
    '"""Current IHG R2 Session/typed Flow and bounded Search readiness; synthetic I/O only."""');
  s=once(s,"raw=sys.stdin.buffer.read(196609)\nassert len(raw)<=196608 and hashlib.sha256(raw).hexdigest()=='da84720694a3ac2d8b9aced4adae34c7226c999ccf45321241b78d877087ac28'",
    "raw=sys.stdin.buffer.read(262145)\nassert len(raw)=="+h.utf8(raw).length+" and hashlib.sha256(raw).hexdigest()=='"+h.sha(raw)+"'");
  s=once(s,"assert p['schema']==1 and set(p)=={'schema','contract','adapter','public_destination','context','coordinator','stage','nonce_slots','nonce_exclusions'}",
    "assert p['schema']==2 and set(p)=={'schema','contract','adapter','public_destination','context','coordinator','stage','transport','nonce_slots','nonce_exclusions'}");
  const oldPins=s.match(/^TEMPLATE_PINS=.*$/m);need(oldPins,"old template pins");
  s=once(s,oldPins[0],"TEMPLATE_PINS="+JSON.stringify(pins));
  s=once(s,"assert len(old)==len(set(old))==30 and all(re.fullmatch('[0-9a-f]{32}',v) for v in old)",
    "assert len(old)==len(set(old))==337 and all(re.fullmatch('[0-9a-f]{32}',v) for v in old)");
  s=once(s,"qa=module(p['contract'],'ihg_actual_r1_contract')","qa=module(p['contract'],'ihg_actual_r2_contract')");
  s=once(s,"adapter=module(p['adapter'],'ihg_actual_r1_adapter')","adapter=module(p['adapter'],'ihg_actual_r2_adapter')");
  s=once(s,"assert qa.PROTOCOL=='pocket4-owned-ihg-qa-v1' and qa.SELF=='org.droidloom.qa.ihg.r1'",
    "assert qa.PROTOCOL=='pocket4-owned-ihg-qa-v2' and qa.SELF=='org.droidloom.qa.ihg.r2'\n"+
    "transport=module(p['transport'],'current_IHG_bound_arun_constructor')\n"+
    "assert type(base.HELPER_UID) is int and base.HELPER_UID==context.HELPER_UID and isinstance(base.INSTALLED,dict)\n"+
    "assert base.INSTALLED['uid']==base.HELPER_UID and base.INSTALLED['package']==qa.SELF\n"+
    "assert base.CURRENT_EPOCH==context.CURRENT_EPOCH==qa.MAIN_EPOCH==transport.FRAMEWORK_EPOCH_SHA256\n"+
    "assert base.CURRENT_BASELINE_SHA==context.CURRENT_BASELINE_SHA==qa.MAIN_BASELINE_SHA\n"+
    "assert base.CURRENT_QUALIFICATION_SHA==context.CURRENT_QUALIFICATION_SHA==qa.MAIN_BASELINE_QUALIFICATION_SHA\n"+
    "assert base.CURRENT_HOST_MANIFEST==context.CURRENT_HOST_MANIFEST==adapter.RECORDER_MANIFEST_SHA");
  need(s.split("'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH}").length===3,"two exact fixture scopes");
  s=s.split("'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH}").join("'window_token':'ab12','main_epoch_sha256':qa.MAIN_EPOCH,\n"+
    "        'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,'main_baseline_sha256':qa.MAIN_BASELINE_SHA,\n"+
    "        'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}");
  s=once(s,"flow=types.SimpleNamespace(contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),\n        _private_backend_transport=False,action_attempted=False,command_index=0,step=step,policy=policy)",
    "flow=types.SimpleNamespace(contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),\n"+
    "        scope={'schema':'pocket4-current-recorder-scope-v1','current_baseline_schema':qa.MAIN_BASELINE_SCHEMA,\n"+
    "            'epoch_sha256':qa.MAIN_EPOCH,'current_baseline_sha256':qa.MAIN_BASELINE_SHA,\n"+
    "            'current_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,\n"+
    "            'package':qa.PACKAGE,'uid':qa.UID,'user':0},\n"+
    "        _private_backend_transport=False,action_attempted=False,command_index=0,step=step,policy=policy)");
  s=s.replace("passed('original_R1_adapter_still_rejects_text')","passed('original_read_inspect_click_adapter_still_rejects_text')");
  s=s.replace("passed('original_R1_contract_still_rejects_text')","passed('original_read_inspect_click_contract_still_rejects_text')");
  const typedBlock=String.raw`# Exercise the production Flow and BoundArun constructors, with only in-memory
# target/callback fixtures. No command, held entry, file operation or Main read
# is allowed by these fixtures.
class SyntheticPrivatePath(PurePosixPath):
    def is_dir(self):return True

def typed_scope_fixture():
    return {'schema':'pocket4-current-recorder-scope-v1',
        'current_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
        'package':qa.PACKAGE,'component':qa.PACKAGE+'/.activity.MainActivity',
        'uid':qa.UID,'user':0,'nonce':base.NONCE,'epoch_sha256':qa.MAIN_EPOCH,
        'current_baseline_sha256':qa.MAIN_BASELINE_SHA,
        'current_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,
        'amazon_task_source_manifest_sha256':'a'*64,'automatic_retry':False,
        'original_recorder_manifest_sha256':adapter.RECORDER_MANIFEST_SHA,
        'actual_resolution_result_sha256':'b'*64}

def construct_flow(scope):
    accesses=[]
    def forbidden(*args,**kwargs):
        accesses.append('FORBIDDEN_IO')
        raise AssertionError('pure constructor reached command/file/entry')
    root=SyntheticPrivatePath('/synthetic/current-IHG-flow')
    step=root/'steps'/'inspect-01'
    target=types.SimpleNamespace(expected={'pid':42},
        helper_sha256=transport.HELD_HELPER_SHA256,
        verify=lambda:accesses.append('target'),entry=forbidden,close=forbidden)
    recorder=types.SimpleNamespace(write_new=forbidden,
        Flow=types.SimpleNamespace(command=forbidden))
    flow=context.Flow(recorder=recorder,
        contract=types.SimpleNamespace(sha256=adapter.RECORDER_MANIFEST_SHA),
        target=target,environment={key:'/synthetic/non-authority' for key in transport.REQUIRED_ENV},
        transport=transport,main_guard=lambda:accesses.append('Main'),
        root=root,step=step,phase='inspect',scope=scope,
        activation={'framework_epoch':{'binding':{'processes':{'init':{'host_pid':42}}}}},
        tasks={},qa=qa,inspect_plan={'search':base.SEARCH_PLAN,'destination':base.PLAN,
            'post':base.POST_PLAN,'readiness':base.SEARCH_READINESS_PLANS},
        resolve=['synthetic-resolve'],read=forbidden,deadline=context.time.monotonic()+60)
    return flow,accesses

flow,accesses=construct_flow(typed_scope_fixture())
assert not accesses and type(flow.transport) is transport.BoundArun
assert flow.transport.target is flow.target and flow.transport.environment=={
    key:'/synthetic/non-authority' for key in transport.REQUIRED_ENV}
assert flow.current_qualified_scope==flow.scope and flow.current_qualified_scope is not flow.scope
session=adapter.Session(flow,None,qa,{},base.HELPER_UID)
flow.guard()
assert accesses==['Main','target'] and session.uid==base.HELPER_UID
passed('production_typed_Flow_BoundArun_and_R2_Session_positive_without_IO')

for name,mutate,expected in [
    ('old_scope_schema',lambda v:v.update(schema='old-recorder-scope'),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_baseline_schema',lambda v:v.update(current_baseline_schema='old-deployment'),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('foreign_package',lambda v:v.update(package='com.bilibili.app'),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('foreign_target_uid',lambda v:v.update(uid=10117),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('boolean_uid',lambda v:v.update(uid=True),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('boolean_user',lambda v:v.update(user=False),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_epoch',lambda v:v.update(epoch_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_baseline_sha',lambda v:v.update(current_baseline_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('wrong_qualification_sha',lambda v:v.update(current_baseline_qualification_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('old_recorder_manifest',lambda v:v.update(original_recorder_manifest_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('legacy_activation_extra',lambda v:v.update(activation_sha256='e'*64),'EXACT_TYPED_CURRENT_IHG_TASK_SCOPE'),
    ('foreign_component',lambda v:v.update(component='com.synthetic.foreign/.Main'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
    ('invalid_nonce',lambda v:v.update(nonce='not-a-nonce'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
    ('invalid_task_manifest',lambda v:v.update(amazon_task_source_manifest_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT'),
    ('invalid_resolver_pin',lambda v:v.update(actual_resolution_result_sha256='bad'),'EXACT_CURRENT_TASK_SOURCE_NONCE_AND_COMPONENT')]:
    value=typed_scope_fixture();mutate(value)
    try:construct_flow(value)
    except RuntimeError as error:assert str(error)==expected,(name,str(error))
    else:raise AssertionError(name+' accepted by production Flow')
    passed('production_Flow_'+name+'_rejected_before_transport')

flow,accesses=construct_flow(typed_scope_fixture())
flow.scope['component']=qa.PACKAGE+'/.activity.OtherActivity'
try:flow.guard()
except RuntimeError as error:assert str(error)=='CURRENT_IHG_TASK_SCOPE_CHANGED'
else:raise AssertionError('mutated constructed scope admitted')
assert accesses==[]
passed('constructed_current_scope_mutation_stops_before_Main_target_or_IO')

`;
  s=once(s,"assert len(cases)==89 and len({x['case'] for x in cases})==89,('control inventory changed',len(cases))",
    typedBlock+"assert len(cases)==106 and len({x['case'] for x in cases})==106,('control inventory changed',len(cases))");
  s=once(s,"'IHG_BOUNDED_SEARCH_READINESS_COMPOSITION_PURE_CONTROLS_PASS'","'IHG_CURRENT_TYPED_BOUNDED_SEARCH_READINESS_PURE_CONTROLS_PASS'");
  s=once(s,"'nonce_values_disjoint_prior_IHG_literals':not bool(set(pool)&set(old)),",
    "'nonce_values_disjoint_all_fixed_prior_literals':not bool(set(pool)&set(old)),\n"+
    " 'nonce_exclusion_count':len(old),'production_Flow_and_BoundArun_constructors_executed':True,\n"+
    " 'production_typed_constructor_controls':17,'actual_Main_and_target_callbacks':False,");
  s=once(s,"'old_Main_identity_validated':False,","'live_Main_identity_validated':False,");
  need(!s.includes("ihg_actual_r1")&&!s.includes("pocket4-owned-ihg-qa-v1"),"old protocol remains in harness");
  return {payload,raw,source:s,source_pin:{bytes:h.utf8(s).length,sha256:h.sha(s)},pins,
    planned_controls:106,Python_execution_performed:false,requires_actual_installed_UID:true};
}