function deriveNormal10(i,H){
"use strict";
const need=(ok,m)=>{if(!ok)throw Error(m);};
const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b)};};
const expectedInput={request:{bytes:1037404,sha256:"d5da9237867a577b4076f0b2ecfd975cb5da5d9dcf907bc906d9cb47c75175d1"},outer:{bytes:24759,sha256:"873a8c03dc51a62e69aaeab28e7929ef2b8b48019d9d1ca949e23ce07d3f3d1a"},resource:{bytes:2749,sha256:"62bc5109a8ed50722560b6374caa1b0581d53abaa0d300e510adbeb85acfb2cd"}};
for(const[k,p]of Object.entries(expectedInput))need(JSON.stringify(pin(i[k]))===JSON.stringify(p),"fixed Normal09 original "+k);
const old=JSON.parse(i.request),oldPacket=JSON.parse(old.stdin),files={...oldPacket.files};
need(Object.keys(files).length===18,"original eighteen source members");
const oldRoot="typed-ingress-framework-provider-build-09-20261106",newRoot="typed-ingress-framework-provider-build-10-20261106";
const edits={framework:[],fence:[],stage:[],transport:[]};
let framework=files["framework_build.py"],fence=files["fenced_build.py"],stage=oldPacket.stage,transport=old.args[3];
function edit(which,before,after){
let s=which==="framework"?framework:which==="fence"?fence:which==="stage"?stage:transport;
const at=s.indexOf(before);need(at>=0&&s.indexOf(before,at+before.length)<0,"one exact "+which+" preimage "+before.slice(0,70));edits[which].push({at,before,after});s=s.slice(0,at)+after+s.slice(at+before.length);
if(which==="framework")framework=s;else if(which==="fence")fence=s;else if(which==="stage")stage=s;else transport=s;
}
edit("framework","ROOT = OWNER / '"+oldRoot+"'","ROOT = OWNER / '"+newRoot+"'");
const anchor="PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-provider-build-08-20261106'";
edit("framework",anchor,anchor+"\nRESOURCE_REJECTED_ROOT = OWNER / '"+oldRoot+"'");
const prior="        (PREVIOUS_ROOT / 'build-fences-01/terminal.json', 'prior-framework-outer-terminal.json', PRIOR_OUTER_SHA, 24714),\n";
edit("framework",prior,prior+
"        (RESOURCE_REJECTED_ROOT / 'build-fences-01/terminal.json', 'prior-normal09-outer-terminal.json',\n"+
"         '873a8c03dc51a62e69aaeab28e7929ef2b8b48019d9d1ca949e23ce07d3f3d1a', 24759),\n"+
"        (RESOURCE_REJECTED_ROOT / 'resource-admission.json', 'prior-normal09-resource-admission.json',\n"+
"         '62bc5109a8ed50722560b6374caa1b0581d53abaa0d300e510adbeb85acfb2cd', 2749),\n");
edit("framework","    inner, outer = documents\n","    inner, outer, rejected_outer, rejected_resource = documents\n");
const block=`    # Normal09 rejected the fresh RAM gate before its owned builder was started.
    # Preserve that failure independently of Normal08's genuine Soong failure.
    # These historical bytes never satisfy the new run's fresh resource admission.
    require(rejected_outer['state'] == 'FAILED' and
            rejected_outer['error'] == "RuntimeError('less than 15 GiB MemAvailable for independent zero-swap profile; no automatic retry')" and
            rejected_outer['inner_build_called'] is True and rejected_outer['inner_returncode'] is None and
            rejected_outer['before_observed'] is True and rejected_outer['after_observed'] is True and
            rejected_outer['main_fence_assessment']['main_fence_pass'] is True and
            rejected_outer['main_fence_assessment']['identity_or_limit_changes'] == [] and
            rejected_outer['main_fence_assessment']['main_oom_delta_zero'] is True and
            all(value == 0 for value in rejected_outer['main_fence_assessment']['main_memory_event_deltas'].values()) and
            rejected_outer['main_fence_assessment']['main_current_resource_deltas']['memory.swap.current'] == 0 and
            rejected_outer['main_fence_assessment']['unobserved_transient_effects_excluded'] is False and
            rejected_outer['main_fence_assessment']['causal_attribution_of_counter_changes'] is False,
            'prior Normal09 resource rejection or limited Main fence result differs')
    resource_controls = rejected_outer['capture_lifecycle_controls']
    require(resource_controls['state'] == 'PASS' and resource_controls['passed'] == 4 and
            len(resource_controls['rows']) == 4 and all(row['passed'] is True and
                row['owned_children_empty'] is True and row['Main_read_performed'] is False
                for row in resource_controls['rows']) and
            [row['phase'] for row in rejected_outer['capture_lifecycle_receipts']] == phases,
            'prior Normal09 four real controls or six capture records differ')
    for row in rejected_outer['capture_lifecycle_receipts']:
        command = row['command']
        require(row['outer_subreaper']['final_children_empty'] is True and
                row['outer_subreaper']['restored'] is True and
                row['within_absolute_outer_deadline'] is True and not row['secondary_errors'] and
                command['child_reaped'] is True and command['owned_tree_cleanup_complete'] is True and
                command['pidfd_closed'] is True and command['all_acquired_fds_closed'] is True and
                command['retirement_within_deadline'] is True and
                not command['remaining_owned_children'] and not command['secondary_errors'],
                'prior Normal09 capture was not completely retired')
        if row['phase'] == 'control-outer-pidfd':
            require(row['qualified_success'] is False and command['returncode'] == -9 and
                    row['first_error']['errno'] == 24 and command['first_error']['errno'] == 24,
                    'prior Normal09 expected pidfd failure was relabeled')
        else:
            require(row['qualified_success'] is True and command['qualified_success'] is True and
                    command['returncode'] == 0 and row['first_error'] is None and
                    command['first_error'] is None, 'prior Normal09 capture failed unexpectedly')
    require(rejected_resource['schema'] == 1 and
            rejected_resource['state'] == 'OBSERVED_BEFORE_RESOURCE_ADMISSION' and
            rejected_resource['profile'] == {
                'memory_max_bytes': 10737418240, 'memory_swap_max_bytes': 0,
                'minimum_fresh_MemAvailable_bytes': 16106127360,
                'admission_difference_bytes': 5368709120, 'global_swap_is_owned_budget': False} and
            rejected_resource['owned_observed'] == {
                'memory.max': '10737418240', 'cpu.max': '200000 100000',
                'memory.swap.max': '0', 'memory.swap.current': '0'} and
            rejected_resource['decision_performed'] is False and
            rejected_resource['historical_sample_used_for_admission'] is False,
            'prior Normal09 resource receipt shape or original zero-swap profile differs')
    resource_raw = rejected_resource['meminfo']['raw_ascii'].encode('ascii', 'strict')
    require(len(resource_raw) == rejected_resource['meminfo']['bytes'] == 1672 and
            hashlib.sha256(resource_raw).hexdigest() == rejected_resource['meminfo']['sha256'] ==
                'f8edcc866dfa4f605af8a5e50f3a42172b716bf819030f11ed6b533323219b38',
            'prior Normal09 exact bounded meminfo differs')
    resource_memory = parse_admission_meminfo(resource_raw)
    require(resource_memory['MemAvailable'] == 14854873088 and
            resource_memory['MemAvailable'] < MIN_AVAILABLE and
            MIN_AVAILABLE - resource_memory['MemAvailable'] == 1251254272,
            'prior Normal09 failed RAM threshold was changed')
`;
const at="    published, row = json_pin(HERE / 'actual-current225-source-manifest.json',\n";
edit("framework",at,block+at);
files["framework_build.py"]=framework;
edit("fence",oldRoot,newRoot);
edit("fence",'CONTROLLER_SHA = "'+pin(oldPacket.files["framework_build.py"]).sha256+'"','CONTROLLER_SHA = "'+pin(framework).sha256+'"');
files["fenced_build.py"]=fence;
files["prior-normal09-outer-terminal.json"]=i.outer;
files["prior-normal09-resource-admission.json"]=i.resource;
need(Object.keys(files).length===20,"exact twenty source members");
const unchanged=Object.keys(oldPacket.files).filter(k=>files[k]===oldPacket.files[k]);
need(unchanged.length===16&&unchanged.includes("main_snapshot.py")&&unchanged.includes("pure_controls.py")&&unchanged.includes("capture_lifecycle.py")&&unchanged.includes("root_snapshot_supervisor.py")&&unchanged.includes("actual-builder473-result.json"),"same16 source/actual authorities");
edit("stage",oldRoot,newRoot);
const expected=Object.fromEntries(Object.entries(files).map(([k,v])=>[k,pin(v)]));
edit("stage","EXPECTED = "+JSON.stringify(Object.fromEntries(Object.entries(oldPacket.files).map(([k,v])=>[k,pin(v)]))),"EXPECTED = "+JSON.stringify(expected));
const wire=JSON.stringify({schema:1,stage,files})+"\n";
need(pin(wire).bytes<=1024*1024,"actual tool one MiB stdin cap");
edit("transport","WIRE_BYTES = "+pin(old.stdin).bytes,"WIRE_BYTES = "+pin(wire).bytes);
edit("transport",pin(old.stdin).sha256,pin(wire).sha256);
edit("transport","STAGE_BYTES = "+pin(oldPacket.stage).bytes,"STAGE_BYTES = "+pin(stage).bytes);
edit("transport",pin(oldPacket.stage).sha256,pin(stage).sha256);
const request={...old,args:[...old.args],stdin:wire,idempotency_key:old.idempotency_key.replace("-09-20261106","-10-20261106")};
request.args[3]=transport;
need(request.idempotency_key!==old.idempotency_key&&request.memory_max_bytes===10737418240&&request.cpu_quota_percent===200&&request.nice===10&&request.timeout_seconds===6400,"fresh key and original resource envelope");
const requestText=JSON.stringify(request,null,2)+"\n";
const before={framework:oldPacket.files["framework_build.py"],fence:oldPacket.files["fenced_build.py"],stage:oldPacket.stage,transport:old.args[3]},after={framework,fence,stage,transport};
for(const [k,list]of Object.entries(edits)){let v=after[k];for(const e of [...list].reverse()){need(v.slice(e.at,e.at+e.after.length)===e.after,"inverse segment "+k);v=v.slice(0,e.at)+e.before+v.slice(e.at+e.after.length);}need(v===before[k],"whole inverse "+k);}
const funcs=t=>{const m=[...t.matchAll(/^def (\w+)\([^\n]*:\n/gm)];need(m.length===[...t.matchAll(/^def /gm)].length,"fixed single-line function headers");return Object.fromEntries(m.map(v=>{const bodyStart=v.index+v[0].length,rest=t.slice(bodyStart),end=rest.search(/^\S/gm);return[v[1],t.slice(v.index,end<0?t.length:bodyStart+end).trimEnd()];}));};
const f0=funcs(before.framework),f1=funcs(framework),changed=Object.keys(f0).filter(k=>f0[k]!==f1[k]);
need(changed.length===1&&changed[0]==="prior_failure_contract","only historical failure contract body changes");
const unchangedFunctions=Object.keys(f0).filter(k=>f0[k]===f1[k]);
for(const name of ["record_resource_admission","memory_admission","parse_admission_meminfo","builder_contract","verify_prepared","build","main"])need(unchangedFunctions.includes(name),"unchanged execution gate "+name);
return{files,framework,fence,stage,transport,wire,request,requestText,expected,edits,unchanged,unchangedFunctions,proof:{schema:1,state:"NORMAL10_BOUND_SOURCE_ONLY_PENDING_FRESH_RESOURCE_OBSERVATION",root:"/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/"+newRoot,request:pin(requestText),stdin:pin(wire),stage:pin(stage),source_members:20,unchanged_source_members:16,actual_builder_revision:473,actual_builder_unchanged:true,Normal08_Soong_failure_remains_bound:true,Normal09_resource_rejection_remains_bound:true,resource_admission_function_unchanged:true,Main8_and_46pure_and_4actual_lifecycle_sources_unchanged:true,own_memory_bytes:10737418240,fresh_MemAvailable_required_bytes:16106127360,own_swap_max:0,CPU:2,jobs:1,nice:10,inner_timeout_seconds:6100,outer_timeout_seconds:6400,source_lock_225_SHA256:"72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d",targets:["framework-minus-apex","libandroid_runtime"],ALLOW_MISSING_DEPENDENCIES:false,prior_failure_histories_preserved:true,independent_fresh_resource_observation_obtained:false,execution_or_retry_performed:false,Soong_or_Java_JNI_qualified:false}};
}
