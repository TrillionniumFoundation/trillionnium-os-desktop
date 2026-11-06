function packageComposerNormal01(i,H,deriveController,qualify474){
 "use strict";
 const need=(v,m)=>{if(!v)throw Error(m);},pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s))});
 need(pin(i.baselineRequest).bytes===1077067&&pin(i.baselineRequest).sha256==="5b34f85412fb23dd0b2089069c1021afe45bac1ea514884db2f016ad4494a8ea","NORMAL10_BASE_REQUEST");
 const base=JSON.parse(i.baselineRequest),old=JSON.parse(base.stdin);
 const ci={...i,framework:old.files["framework_build.py"],controls:old.files["pure_controls.py"]};
 const c=deriveController(ci,H,qualify474),files={};
 for(const[name,raw]of Object.entries(old.files)){
   if(name==="expected-builder473-manifest.json")files["expected-builder474-manifest.json"]=i.map;
   else if(name==="actual-builder473-result.json")files["actual-builder474-result.json"]=i.actual;
   else if(name==="framework_build.py")files[name]=c.framework;
   else if(name==="pure_controls.py")files[name]=c.controls;
   else files[name]=raw;
 }
 const oldRoot="/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-provider-build-10-20261106";
 let fence=files["fenced_build.py"],stage=old.stage,transport=base.args[3];const edits={fence:[],stage:[],transport:[]};
 function edit(which,before,after){let value=which==="fence"?fence:which==="stage"?stage:transport;const at=value.indexOf(before);need(at>=0&&value.indexOf(before,at+before.length)<0,"PACKET_PREIMAGE:"+which+":"+before.slice(0,64));edits[which].push({at,before,after});value=value.slice(0,at)+after+value.slice(at+before.length);if(which==="fence")fence=value;else if(which==="stage")stage=value;else transport=value;}
 edit("fence",oldRoot,c.root);
 edit("fence",'CONTROLLER_SHA = "'+pin(old.files["framework_build.py"]).sha256+'"','CONTROLLER_SHA = "'+pin(c.framework).sha256+'"');
 files["fenced_build.py"]=fence;
 need(Object.keys(files).length===20,"EXACT_TWENTY_SOURCE_MEMBERS");
 edit("stage",oldRoot,c.root);
 const oldExpected=Object.fromEntries(Object.entries(old.files).map(([k,v])=>[k,pin(v)])),expected=Object.fromEntries(Object.entries(files).map(([k,v])=>[k,pin(v)]));
 edit("stage","EXPECTED = "+JSON.stringify(oldExpected),"EXPECTED = "+JSON.stringify(expected));
 edit("stage","controls['passed']!=46","controls['passed']!=56");
 const wire=JSON.stringify({schema:1,stage,files})+"\n";
 need(pin(wire).bytes<=1048576,"ONE_MIB_TOOL_STDIN_CAP");
 edit("transport","WIRE_BYTES = "+pin(base.stdin).bytes,"WIRE_BYTES = "+pin(wire).bytes);
 edit("transport",pin(base.stdin).sha256,pin(wire).sha256);
 edit("transport","STAGE_BYTES = "+pin(old.stage).bytes,"STAGE_BYTES = "+pin(stage).bytes);
 edit("transport",pin(old.stage).sha256,pin(stage).sha256);
 edit("transport","normal framework exact source packet changed","normal Composer exact source packet changed");
 const request={...base,args:[...base.args],stdin:wire,idempotency_key:"pocket4-native-composer-retirement-strict-service-aidl-build-01-20261106"};
 request.args[3]=transport;
 need(request.memory_max_bytes===10737418240&&request.cpu_quota_percent===200&&request.nice===10&&request.timeout_seconds===6400&&request.host==="pocket4"&&request.executable==="/usr/bin/python3"&&JSON.stringify(request.env)===JSON.stringify(base.env),"UNCHANGED_RESOURCE_AND_ENV_ENVELOPE");
 const requestText=JSON.stringify(request,null,2)+"\n",before={fence:old.files["fenced_build.py"],stage:old.stage,transport:base.args[3]},after={fence,stage,transport};
 for(const[k,es]of Object.entries(edits)){let text=after[k];for(const e of [...es].reverse()){need(text.slice(e.at,e.at+e.after.length)===e.after,"PACKET_INVERSE_SEGMENT:"+k);text=text.slice(0,e.at)+e.before+text.slice(e.at+e.after.length);}need(text===before[k],"PACKET_WHOLE_INVERSE:"+k);}
 const unchanged=Object.keys(old.files).filter(k=>files[k]===old.files[k]);
 need(unchanged.length===15&&["main_snapshot.py","capture_lifecycle.py","root_snapshot_supervisor.py","actual-hal-provider-source-lock.json","prior-normal09-outer-terminal.json","prior-normal09-resource-admission.json"].every(k=>unchanged.includes(k)),"UNCHANGED_AUTHORITIES_AND_MAIN_LIFECYCLE");
 const proof={schema:1,state:"ACTUAL474_BOUND_SOURCE_ONLY_NORMAL_BUILD_HELD_FOR_FRESH_RESOURCES",root:c.root,builder_parent:c.build_parent,request:pin(requestText),stdin:pin(wire),stage:pin(stage),transport:pin(transport),packet_members:20,unchanged_baseline_packet_members:15,unchanged_Main8_and_capture_sources:true,original_46_pure_controls_retained:true,new_Composer_record_pure_controls:10,planned_pure_controls:56,real_capture_controls:4,actual_474_report:pin(i.actual),actual_474_compiler:pin(i.compiler),actual_474_map:pin(i.map),actual_474_scope:pin(i.scope),actual_474_projection_proof:pin(i.proof),normal_compiler_entry:"composer-retirement-build",fixed_targets:c.sourceScope.targets,dependency_mode:"Strict",ALLOW_MISSING_DEPENDENCIES:false,zero_swap_and_RAM_admission_unchanged:true,Normal08_Soong_and_Normal09_resource_failures_preserved:true,Normal10_typed_candidate_not_modified:true,Python_or_Soong_executed:false,new_fresh_Main_identity_qualified:false,new_fresh_resource_admission_qualified:false,Android_Binder_ABI_qualified:false,Wayland_GPU_runtime_qualified:false,installation:false,service_activation:false,Main_actions:0};
 return {files,framework:c.framework,controls:c.controls,fence,stage,transport,wire,request,requestText,expected,edits,controller:c,unchanged,proof};
}
