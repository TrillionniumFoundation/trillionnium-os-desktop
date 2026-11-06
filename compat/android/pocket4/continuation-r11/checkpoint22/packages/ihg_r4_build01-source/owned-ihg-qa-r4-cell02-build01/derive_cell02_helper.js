function forkCell02Helper(app,parentFiles,oldInstall,actual,host,h) {
 const need=(v,m)=>{if(!v)throw Error(m);};const r=actual.report;
 const parentManifest=JSON.parse(parentFiles["SOURCE_PINS.json"]),oldBinding=parentManifest.current_baseline_binding;
 need(oldBinding.app===app&&oldInstall.app===app&&r.ok===true,"APP_AND_ACTUAL_BINDING");
 for(const [n,p]of Object.entries(parentManifest.files))need(h.utf8(parentFiles[n]).length===p.bytes&&h.sha(parentFiles[n])===p.sha256,"PARENT_SOURCE:"+n);
 const oldPackage=oldBinding.helper_package,oldProtocol=oldBinding.protocol,oldRevision=Number(oldPackage.match(/\.r(\d+)$/)[1]),revision=oldRevision+1;
 const nextPackage=oldPackage.replace(/\.r\d+$/,".r"+revision),nextProtocol=oldProtocol.replace(/-v\d+$/,"-v"+revision);
 const oldSource=parentFiles["stage_build.py"].match(/ROOT = Path\('([^']+)'\)/)[1];
 const oldBuild=parentFiles["build_candidate.py"].match(/OUTPUT = Path\('([^']+)'\)/)[1];
 const sourceRoot="/home/alex/work/pocket4-owned-"+app+"-qa-r"+revision+"-source-01";
 const outputRoot="/home/alex/work/pocket4-owned-"+app+"-qa-r"+revision+"-build-01";
 const key="pocket4-owned-"+app+"-qa-r"+revision+"-cell02-"+r.baseline.sha256.slice(0,16)+"-host-"+host.manifest_sha256.slice(0,12)+"-build01";
 const oldOwned="owned-"+app+"-qa-r"+oldRevision,nextOwned="owned-"+app+"-qa-r"+revision;
 const map=[
 [oldOwned,nextOwned],
 [oldSource.split(oldOwned).join(nextOwned),sourceRoot],
 [oldBuild.split(oldOwned).join(nextOwned),outputRoot],
 [oldPackage,nextPackage],[oldProtocol,nextProtocol],
 ["org/droidloom/qa/"+app+"/r"+oldRevision+"/","org/droidloom/qa/"+app+"/r"+revision+"/"],
 ["pocket4-current-recorder-scope-v1","pocket4-current-recorder-scope-v2"],
 ["pocket4-main-current-baseline-v1","pocket4-main-current-baseline-v2"],
 [oldBinding.current_epoch_sha256,r.new_epoch_sha256],
 [oldBinding.current_baseline.sha256,r.baseline.sha256],
 [oldBinding.current_qualification.sha256,r.qualification.sha256],
 [oldBinding.host_recorder_source_manifest.sha256,host.manifest_sha256]
 ];
 const unchangedRefs=new Set(["build-input-reference.json","target-artifact-reference.json","public-destination-reference.json"]);
 const files={},proof={};
 for(const [oldName,oldRaw]of Object.entries(parentFiles)){
   if(["SOURCE_PINS.json","current-baseline-binding.json","README.md"].includes(oldName))continue;
   let name=oldName,raw=oldRaw;const edits=[];
   if(!unchangedRefs.has(oldName))for(const [a,b]of map){if(a===b)continue;name=name.split(a).join(b);const count=raw.split(a).length-1;if(count){raw=raw.split(a).join(b);edits.push({old:a,next:b,count});}}
   if(oldName==="qa_contract.py"||oldName==="qa_adapter.py"){
     const matches=[...raw.matchAll(/helper_uid not in \(([^)]*)\)/g)];need(matches.length===1,"EXACT_UID_GATE:"+app+":"+oldName);
     const old=matches[0][0];const items=matches[0][1].split(",").map(x=>x.trim());need(!items.includes(String(oldInstall.uid)),"PREVIOUS_UID_ALREADY_LISTED");
     const sep=matches[0][1].includes(", ")?", ":",";
     const next="helper_uid not in ("+matches[0][1]+sep+oldInstall.uid+")";
     raw=raw.replace(old,next);edits.push({old,next,count:1});
   }
   if(oldName==="make_build_request.py"){
     const keyLine=raw.match(/^KEY='[^']+'$/m);need(keyLine,"EXACT_BUILD_KEY");
     const next="KEY='"+key+"'";raw=raw.replace(keyLine[0],next);edits.push({old:keyLine[0],next,count:1});
     const old="'args':['-I','-c',wrapper]",nextArg="'args':['-I','-B','-c',wrapper]";need(raw.split(old).length===2,"BUILD_REQUEST_ARGS");raw=raw.replace(old,nextArg);edits.push({old,next:nextArg,count:1});
   }
   if(oldName==="build_candidate.py"){
     const old="baseline_controls['count']==21",next="baseline_controls['count']==32";
     need(raw.split(old).length===2,"SCOPE_COUNT_GATE");raw=raw.replace(old,next);edits.push({old,next,count:1});
     const sizeOld="len(baseline_controls['cases'])==21",sizeNext="len(baseline_controls['cases'])==32";
     need(raw.split(sizeOld).length===2,"SCOPE_CASE_ARRAY_GATE");raw=raw.replace(sizeOld,sizeNext);edits.push({old:sizeOld,next:sizeNext,count:1});
   }
   if(oldName==="check_current_baseline.py"){
     const nameOld="actual_R5_session_scope_positive",nameNew="actual_R6_session_scope_positive";
     need(raw.split(nameOld).length===2,"OLD_SESSION_NAME");raw=raw.replace(nameOld,nameNew);edits.push({old:nameOld,next:nameNew,count:1});
     const gate="    qa.require(len(rows)==21,'EXACT_CURRENT_BASELINE_SCOPE_CASES')";
     const addition=`    no('previous_current_epoch',lambda v:v.update(main_epoch_sha256='${oldBinding.current_epoch_sha256}'))
    no('previous_baseline_v1_schema',lambda v:v.update(main_baseline_schema='pocket4-main-current-baseline-v1'))
    no('previous_baseline_digest',lambda v:v.update(main_baseline_sha256='${oldBinding.current_baseline.sha256}'))
    no('previous_qualification_digest',lambda v:v.update(main_baseline_qualification_sha256='${oldBinding.current_qualification.sha256}'))
    host_no('previous_R5_host_manifest',lambda f:setattr(f.contract,'sha256','${oldBinding.host_recorder_source_manifest.sha256}'))
    host_no('previous_typed_scope_v1',lambda f:f.scope.update(schema='pocket4-current-recorder-scope-v1'))
    try:session_scope['Session'](fixture(),None,qa,{},${oldInstall.uid})
    except RuntimeError:pass
    else:raise RuntimeError('PREVIOUS_HELPER_UID_SESSION_ACCEPTED')
    rows.append({'name':'previous_actual_helper_UID_session_rejected','passed':True})
    qa.require(qa.PROTOCOL=='${nextProtocol}' and qa.SELF=='${nextPackage}',
               'EXACT_NEW_HELPER_PROTOCOL_REQUIRED')
    rows.append({'name':'exact_new_helper_protocol_and_package','passed':True})
    req={'protocol':qa.PROTOCOL,'nonce':'1'*32,'op':'state'}
    try:qa.validate_request({**req,'protocol':'${oldProtocol}'})
    except qa.ProtocolError:pass
    else:raise RuntimeError('PREVIOUS_HELPER_PROTOCOL_ACCEPTED')
    rows.append({'name':'previous_helper_protocol_rejected','passed':True})
    import base64,gzip
    def state_value(uid):
        value={'protocol':qa.PROTOCOL,'nonce':req['nonce'],'op':'state',
            'request_sha256':qa.sha(qa.validate_request(req)),'wire_codec':'gzip-canonical-json-v1',
            'self_uid':uid,'self_pid':1234,'ok':True,'error':None,'secondary_errors':[],
            'claim_persistence_completed':True,'helper_work_completed':True,'automatic_retry':False,
            'business_success_verified':False,'accessibility_mode_restoration_verified':None,
            'started_elapsed_ms':100,'finished_elapsed_ms':110,
            'action_attempted':False,'outcome_unknown':False,'ui_automation_connected':False,
            'requires_post_termination_state_check':False,
            'restoration':{'service_info_captured':False,'service_info_verified':True},
            'state':{'accessibility_enabled':False,'touch_exploration_enabled':False,
                     'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')},
            'window_observation':{},'tree_observations':[]}
        ${app==="amazon"||app==="bili"?"value['inspection_idle_observation']={}":"# This helper has no inspection idle metadata field."}
        return value
    def wire(value):
        text=base64.b64encode(gzip.compress(qa.canonical(value),mtime=0)).decode()
        return ('INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64='+text+
                '\\nINSTRUMENTATION_CODE: -1\\n').encode()
    qa.parse_completed(wire(state_value(99999)),b'',0,req,99999)
    rows.append({'name':'actual_state_wire_new_identity_positive','passed':True})
    try:qa.parse_completed(wire(state_value(${oldInstall.uid})),b'',0,req,${oldInstall.uid})
    except qa.ProtocolError as error:
        qa.require(str(error)=='INSTALLED_HELPER_IDENTITY_REQUIRED','PREVIOUS_UID_WRONG_FIRST_CAUSE')
    else:raise RuntimeError('PREVIOUS_HELPER_UID_WIRE_ACCEPTED')
    rows.append({'name':'previous_actual_helper_UID_wire_rejected','passed':True})
    qa.require(len(rows)==32,'EXACT_CURRENT_BASELINE_SCOPE_CASES')`;
     need(raw.split(gate).length===2,"EXACT_21_SCOPE_GATE");raw=raw.replace(gate,addition);edits.push({old:gate,next:addition,count:1});
     const old="'schema':'pocket4-current-baseline-scope-controls-v1','all_passed':True,'count':21",next="'schema':'pocket4-current-baseline-scope-controls-v2','all_passed':True,'count':32";
     need(raw.split(old).length===2,"SCOPE_REPORT_COUNT");raw=raw.replace(old,next);edits.push({old,next,count:1});
   }
   let inv=raw;for(const e of [...edits].reverse()){need(inv.split(e.next).length-1===e.count,"INVERSE_COUNT:"+app+":"+name+":"+e.next.slice(0,36));inv=inv.split(e.next).join(e.old);}need(inv===oldRaw,"INVERSE_BYTE_EXACT:"+app+":"+name);
   files[name]=raw;proof[name]={parent_path:oldName,parent:{bytes:h.utf8(oldRaw).length,sha256:h.sha(oldRaw),git_blob:h.git(oldRaw)},generated:{bytes:h.utf8(raw).length,sha256:h.sha(raw)},edits,inverse_byte_exact:true};
 }
 const binding={schema:"pocket4-current-baseline-helper-source-binding-v2",state:"STATIC_SOURCE_ONLY_ANDROID_UNRUN",app,target_package:oldBinding.target_package,target_uid:oldBinding.target_uid,helper_package:nextPackage,protocol:nextProtocol,current_baseline_schema:"pocket4-main-current-baseline-v2",current_epoch_sha256:r.new_epoch_sha256,current_baseline:r.baseline,current_qualification:r.qualification,actual_baseline_result:{job_id:actual.actual.job,git_tree:actual.actual.tree,git_blob:actual.actual.blob,bytes:actual.actual.bytes,sha256:actual.actual.sha256},host_recorder_source_manifest:{path:"/home/alex/work/pocket4-current-host-r6-source-01/source-manifest.json",bytes:h.utf8(host.manifestRaw).length,sha256:host.manifest_sha256},parent_source_manifest_sha256:h.sha(parentFiles["SOURCE_PINS.json"]),previous_helper_uid_exclusion:{uid:oldInstall.uid,actual_worker_result:{bytes:oldInstall.bytes,sha256:oldInstall.sha256,git_blob:oldInstall.blob},source:"exact historical installed helper receipt; exclusion only, no new cell authority"},owned_helper_uid:null,APK_sha256:null,signer_sha256:null,helper_built:false,helper_installed:false,UI_actions:0,old_helpers_and_tasks_reauthorized:false,unresolved_framework_exit_cause:true,whole_app_production_ready:false};
 if(app==="ihg"){binding.fixed_public_input="London";binding.new_operations=["state","inspect","click","set_text"];}
 files["current-baseline-binding.json"]=JSON.stringify(binding,null,2)+"\n";
 files["README.md"]="# "+app+" owned helper R"+revision+" for current cell baseline02\n\nThis create-only source/build candidate binds the actual baseline02 receipt, typed v2 host scope, and exact R6 host manifest. It derives from the fixed prior helper source manifest `"+binding.parent_source_manifest_sha256+"`.\n\nThe commercial target package, UID, resource selectors, complete-tree/window/freshness checks, public input restrictions, action count limits, independent restoration, and time/resource bounds remain unchanged. Protocol and helper package are a new generation. The prior actual helper UID "+oldInstall.uid+" is rejected at the Session and wire result identity gates. Its historical receipt gives no runtime authority in this cell.\n\nThe build runs the original App-specific controls and 32 current-baseline/protocol/identity controls, then the pinned Java/APK toolchain. This source freeze has not executed Python or Java. APK, signer, and new installed UID remain unknown until separate actual build and install receipts. No business flow, old task, or issued nonce is reauthorized. Whole-App production readiness remains false.\n";
 const manifest={schema:1,artifact:"pocket4-current-baseline-helper-source-v2",current_baseline_binding:binding,files:Object.fromEntries(Object.keys(files).sort().map(k=>[k,{bytes:h.utf8(files[k]).length,sha256:h.sha(files[k])}]))};
 files["SOURCE_PINS.json"]=JSON.stringify(manifest,null,2)+"\n";
 const manifestSha=h.sha(files["SOURCE_PINS.json"]);
 const packet={schema:1,stage_source:files["stage_build.py"],source_manifest_sha256:manifestSha,files:{"SOURCE_PINS.json":files["SOURCE_PINS.json"],...Object.fromEntries(Object.keys(manifest.files).map(k=>[k,files[k]]))}};
 const stdin=JSON.stringify(packet,null,2)+"\n";need(h.utf8(stdin).length<=524288,"BUILD_PACKET_BOUND");
 const wrapper="import sys,json,hashlib;raw=sys.stdin.buffer.read(524289);assert len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=="+("'"+h.sha(stdin)+"'")+";packet=json.loads(raw);source=packet['stage_source'];assert hashlib.sha256(source.encode()).hexdigest()=="+("'"+h.sha(files["stage_build.py"])+"'")+";scope={'__name__':'__main__','__file__':'<verified-owned-"+app+"-qa-build-stage>','PACKET':packet};exec(compile(source,'stage_build.py','exec'),scope,scope)";
 const request={host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",wrapper],cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin,idempotency_key:key,timeout_seconds:300,cpu_quota_percent:100,memory_max_bytes:536870912,nice:10};
 return {app,revision,files,manifest,manifestSha,binding,proof,parent_manifest_raw:parentFiles["SOURCE_PINS.json"],oldInstall:{...oldInstall,raw:undefined},sourceRoot,outputRoot,packet,stdin,wrapper,request,requestRaw:JSON.stringify(request,null,2)+"\n",controlsExpected:32,Python_or_Java_executed:false};
}
