const FIXED_TARGETS=[
  {
    "slug": "ticket12306",
    "label": "12306",
    "package": "com.MobileTicket",
    "uid": 10121,
    "version": 275,
    "apks": 1,
    "tree": "0e41c4bc51f00ef141261316755f933cfb593f61",
    "job": "1a1b22752af-fc05-7cab",
    "blob": "4118c053d3da58dd50f00cf433eb5083b3adaed6",
    "bytes": 11978,
    "sha256": "f573eb50b3e0c2a098101035df116ba76bfdbf5f486e3dafb7588399661bb868",
    "reference_pin": {
      "bytes": 3513,
      "sha256": "57220958eacec13fb0b82755d4e22ffb6e02e42ecb05224103c6c5d37036db0c"
    }
  },
  {
    "slug": "hilton",
    "label": "Hilton",
    "package": "com.hilton.android.hhonors",
    "uid": 10135,
    "version": 1004,
    "apks": 4,
    "tree": "c6bd83d45273194cfc923bed8d6d39d017dae080",
    "job": "1a1b22928c9-fc05-7cb7",
    "blob": "5e43bfe675aae41e387bc7752668eb08f1825a2d",
    "bytes": 13997,
    "sha256": "cd4f46876a1bd0b48289d6b6a9c8379b2480073b4a24849397f8d990cabeb0dd",
    "reference_pin": {
      "bytes": 5083,
      "sha256": "a7ecc2530967eeb3d340b4d53cdab634223263b50e871382caaef8508c930f6a"
    }
  },
  {
    "slug": "united",
    "label": "United",
    "package": "com.united.mobile.android",
    "uid": 10133,
    "version": 3617,
    "apks": 4,
    "tree": "1e57b20f9f7783db37fa12d3edf43876a35e5a1b",
    "job": "1a1b229e173-fc05-7cbd",
    "blob": "a47962c9d7fb8cd344dd67f8667ed1d3520a7a7f",
    "bytes": 13946,
    "sha256": "7820efe97d7a8ebd55f91b6234d829576e2f0c2c0e6277710f143aca3759dc76",
    "reference_pin": {
      "bytes": 5048,
      "sha256": "9fd00a8b3b3f88e958b75d093247e27d8736747e9191bda26b4ac9955f16cc9a"
    }
  }
];
function forkFixedNext3Helper(slug,parentFiles,metadataRaw,referenceRaw,parentWorkerRaw,h) {
 const need=(v,m)=>{if(!v)throw Error(m);};
 const target=FIXED_TARGETS.find(x=>x.slug===slug);need(target,"ONLY_THREE_EXPLICIT_TARGETS");
 const parentRaw=parentFiles["SOURCE_PINS.json"];
 need(h.utf8(parentRaw).length===4251&&h.sha(parentRaw)==="cda79d5b01ebfd91d6b9148be6853c78495da92130fb4f153422daac7d14ad0b","EXACT_BESTBUY_R4_SOURCE_MANIFEST");
 const parent=JSON.parse(parentRaw),oldBinding=parent.current_baseline_binding;
 need(Object.keys(parentFiles).length===14&&Object.keys(parent.files).length===13,"EXACT_PARENT_SOURCE_SET");
 for(const[n,p]of Object.entries(parent.files))need(typeof parentFiles[n]==="string"&&h.utf8(parentFiles[n]).length===p.bytes&&h.sha(parentFiles[n])===p.sha256,"PARENT_SOURCE:"+n);
 need(h.utf8(metadataRaw).length===target.bytes&&h.sha(metadataRaw)===target.sha256&&h.git(metadataRaw)===target.blob,"EXACT_TARGET_ACTUAL_METADATA");
 need(h.utf8(referenceRaw).length===target.reference_pin.bytes&&h.sha(referenceRaw)===target.reference_pin.sha256,"EXACT_LOSSLESS_TARGET_REFERENCE");
 const meta=JSON.parse(metadataRaw),ref=JSON.parse(referenceRaw);
 need(meta.ok===true&&meta.error===null&&meta.secondary_errors.length===0&&meta.package===target.package&&
  meta.metadata_before.uid===target.uid&&meta.metadata_before.version_code===target.version&&meta.metadata_before.user===0&&
  meta.artifacts.length===target.apks&&meta.final_Main_guard_passed===true&&meta.held_binding_released===true&&meta.action_lock_released===true,
  "ACTUAL_TARGET_METADATA_QUALIFIED");
 need(ref.package===target.package&&ref.uid===target.uid&&ref.version_code===target.version&&ref.current_APK_count===target.apks&&
  ref.helper_UID===null&&ref.helper_APK===null&&ref.helper_signer===null&&ref.whole_app_production_ready===false,
  "NEW_TARGET_REFERENCE_NO_HELPER_AUTHORITY");
 need(h.utf8(parentWorkerRaw).length===15422&&h.sha(parentWorkerRaw)==="f3ec3d475dcccb894c68bd3bb471d85976cfa39f38bf437250d501de47d7b3e3"&&h.git(parentWorkerRaw)==="ed8df6e48ba062706e72784d21a4c4b11f5db85e","PARENT_CURRENT_HELPER_ACTUAL");
 const pw=JSON.parse(parentWorkerRaw);
 need(pw.ok===true&&pw.error===null&&pw.outcome_unknown===false&&pw.owned_package_uid===10160&&
  pw.installed_before_state.uid===10160&&pw.installed_after_state.uid===10160&&
  pw.installed_after_state.package==="org.droidloom.qa.bestbuy.r4"&&pw.state.helper.self_uid===10160,
  "PARENT_HELPER_EXCLUSION_ONLY");
 const self="org.droidloom.qa."+slug+".r1",protocol="pocket4-owned-"+slug+"-qa-v1";
 const sourceRoot="/home/alex/work/pocket4-owned-"+slug+"-qa-r1-source-01";
 const outputRoot="/home/alex/work/pocket4-owned-"+slug+"-qa-r1-build-01";
 const key="pocket4-owned-"+slug+"-qa-r1-cell02-fixed-metadata-build01-20261106";
 const files={},proof={};
 const map=[
  ["org.droidloom.qa.bestbuy.r4",self],
  ["pocket4-owned-bestbuy-qa-v4",protocol],
  ["org/droidloom/qa/bestbuy/r4/","org/droidloom/qa/"+slug+"/r1/"],
  ["owned-bestbuy-qa-r4","owned-"+slug+"-qa-r1"],
  ["com\\\\.bestbuy\\\\.android",target.package.replace(/\./g,"\\\\.")],
  ["com\\.bestbuy\\.android",target.package.replace(/\./g,"\\.")],
  ["com.bestbuy.android",target.package],
  ["bestbuy",slug],["BestBuy",target.label],["BESTBUY",slug.toUpperCase()]
 ];
 for(const[oldName,oldRaw]of Object.entries(parentFiles)){
  if(["SOURCE_PINS.json","current-baseline-binding.json","README.md","target-artifact-reference.json"].includes(oldName))continue;
  if(oldName==="build-input-reference.json"){files[oldName]=oldRaw;proof[oldName]={parent_path:oldName,unchanged:true,parent_sha256:h.sha(oldRaw)};continue;}
  let name=oldName,raw=oldRaw;const edits=[];
  const edit=(a,b,count=null)=>{const positions=[];for(let pos=raw.indexOf(a);pos>=0;pos=raw.indexOf(a,pos+a.length))positions.push(pos);
   const n=positions.length;need(n>0&&(count===null||n===count),"EXACT_EDIT:"+oldName+":"+a);
   const next_positions=positions.map((pos,i)=>pos+i*(b.length-a.length));raw=raw.split(a).join(b);
   edits.push({old:a,next:b,count:n,old_positions:positions,next_positions,offset_units:"JavaScript UTF16; all production sources ASCII"});};
  if(oldName==="check_current_baseline.py")edit("pocket4-owned-bestbuy-qa-v3","__PARENT_HELPER_PROTOCOL_REJECTION__",1);
  for(const[a,b]of map){name=name.split(a).join(b);if(a!==b&&raw.includes(a))edit(a,b);}
  if(oldName==="qa_contract.py"){
   edit("UID = 10130","UID = "+target.uid,1);
   const gate=raw.match(/helper_uid not in \([^)]*\)/g);need(gate&&gate.length===1,"EXACT_QA_HELPER_UID_GATE");
   edit(gate[0],"helper_uid not in (UID, 10160)",1);
  }
  if(oldName==="qa_adapter.py"){
   const gate=raw.match(/helper_uid not in \([^)]*\)/g);need(gate&&gate.length===1,"EXACT_SESSION_HELPER_UID_GATE");
   edit(gate[0],"helper_uid not in ("+target.uid+",10160)",1);
  }
  if(oldName.endsWith("/ActionRunner.java"))edit("TARGET_UID = 10130","TARGET_UID = "+target.uid,1);
  if(oldName==="check_current_baseline.py"){
   edit("__PARENT_HELPER_PROTOCOL_REJECTION__","pocket4-owned-bestbuy-qa-v4",1);
   edit("10155","10160");
   edit("previous_actual_helper_UID","parent_current_helper_UID");
   edit("previous_helper_protocol_rejected","parent_helper_protocol_rejected",1);
  }
  if(oldName==="controls/check_deep_tree.py"){
   edit("10198","10160");
   edit("old_helper_UID_10160_cannot_qualify_r2","parent_helper_UID_10160_cannot_qualify_r1",1);
  }
  if(oldName==="make_build_request.py"){
   const line=raw.match(/^KEY='[^']+'$/m);need(line,"EXACT_KEY_LINE");edit(line[0],"KEY='"+key+"'",1);
  }
  if(oldName==="build_candidate.py")edit("Owned "+target.label+" QA R2","Owned "+target.label+" QA R1",1);
  let inverse=raw;for(const e of edits.slice().reverse()){
   for(const pos of e.next_positions.slice().reverse()){
    need(inverse.slice(pos,pos+e.next.length)===e.next,"INVERSE_POSITION:"+name+":"+pos);
    inverse=inverse.slice(0,pos)+e.old+inverse.slice(pos+e.next.length);
   }
  }
  need(inverse===oldRaw,"BYTE_EXACT_PARENT_INVERSE:"+name);
  files[name]=raw;proof[name]={parent_path:oldName,parent:{bytes:h.utf8(oldRaw).length,sha256:h.sha(oldRaw),blob:h.git(oldRaw)},edits,exact_inverse:true};
 }
 files["target-artifact-reference.json"]=referenceRaw;
 const binding={...oldBinding,app:slug,target_package:target.package,target_uid:target.uid,helper_package:self,protocol,
  parent_source_manifest_sha256:h.sha(parentRaw),previous_helper_uid_exclusion:null,
  parent_source_helper_uid_exclusion:{uid:10160,package:"org.droidloom.qa.bestbuy.r4",actual_worker_result:{bytes:15422,sha256:"f3ec3d475dcccb894c68bd3bb471d85976cfa39f38bf437250d501de47d7b3e3",git_blob:"ed8df6e48ba062706e72784d21a4c4b11f5db85e"},source:"Current parent helper exclusion only. It is not a prior helper for this new target and gives no target runtime authority."},
  actual_target_metadata:{tree:target.tree,job:target.job,bytes:target.bytes,sha256:target.sha256,git_blob:target.blob},
  new_fixed_target_namespace:true,parent_target_scope_reused:false,owned_helper_uid:null,APK_sha256:null,signer_sha256:null,
  helper_built:false,helper_installed:false,UI_actions:0,old_helpers_and_tasks_reauthorized:false,whole_app_production_ready:false};
 files["current-baseline-binding.json"]=JSON.stringify(binding,null,2)+"\n";
 files["README.md"]="# "+target.label+" fixed-target owned helper R1\n\nThis is an independently named source/build candidate for "+target.package+" user0 UID "+target.uid+", bound to the exact current-cell02 metadata result "+target.sha256+". It reuses the complete depth128 collector, original action freshness/window/refresh guards, state restoration, pinned seven-tool build, and R6/B02 scope contract from the fixed BestBuy R4 source. Parent target/package/helper runtime authority is not reused.\n\nThe helper protocol retains state/inspect/click support with set_text unreachable as in its parent. The first separate controller will admit only fresh owned launch and state/complete-inspect/state with independent exact task cleanup; no click/text input is authorized by this source. Scope changes are closed to these three explicitly listed targets and are separately compiled.\n\nThe new namespace has no known installed helper UID, APK or signer. The production wire and Session UID gates reject this target UID and the actually installed parent helper UID10160. They do not inherit unrelated prior-cell helper allocation numbers. The original 32 scope controls and 16 deep-tree protocol controls are retained with the actual parent-helper rejection fixture bound to10160 and the parent protocol. Those controls have not yet run for this helper.\n\nAll Main, complete tree, depth/node/bytes, one-action/freshness, unknown-result, restoration, timeout and resources remain unchanged. Target APK held-file numeric tokens in the reference are preserved verbatim from the actual metadata. Any later install or launch must revalidate target files/directories and resolve the current launcher afresh. Whole-app production readiness is false.\n";
 const manifest={schema:1,artifact:"pocket4-current-baseline-helper-source-v2",current_baseline_binding:binding,
  files:Object.fromEntries(Object.keys(files).sort().map(n=>[n,{bytes:h.utf8(files[n]).length,sha256:h.sha(files[n])}]))};
 files["SOURCE_PINS.json"]=JSON.stringify(manifest,null,2)+"\n";
 need(Object.keys(files).length===14,"EXACT_NEW_SOURCE_SET");
 const packet={schema:1,stage_source:files["stage_build.py"],source_manifest_sha256:h.sha(files["SOURCE_PINS.json"]),
  files:{"SOURCE_PINS.json":files["SOURCE_PINS.json"],...Object.fromEntries(Object.keys(manifest.files).map(n=>[n,files[n]]))}};
 const stdin=JSON.stringify(packet,null,2)+"\n";need(h.utf8(stdin).length<=524288,"BUILD_PACKET_BOUND");
 const wrapper="import sys,json,hashlib;raw=sys.stdin.buffer.read(524289);assert len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=='"+h.sha(stdin)+"';packet=json.loads(raw);source=packet['stage_source'];assert hashlib.sha256(source.encode()).hexdigest()=='"+h.sha(files["stage_build.py"])+"';scope={'__name__':'__main__','__file__':'<verified-owned-"+slug+"-qa-build-stage>','PACKET':packet};exec(compile(source,'stage_build.py','exec'),scope,scope)";
 const request={host:"pocket4",executable:"/usr/bin/python3",args:["-I","-B","-c",wrapper],cwd:"/home/alex/work",
  env:{PYTHONDONTWRITEBYTECODE:"1"},stdin,idempotency_key:key,timeout_seconds:300,cpu_quota_percent:100,memory_max_bytes:536870912,nice:10};
 return {slug,target,files,manifest,binding,proof,sourceRoot,outputRoot,key,packet,request,requestRaw:JSON.stringify(request,null,2)+"\n",Python_or_Java_executed:false};
}
