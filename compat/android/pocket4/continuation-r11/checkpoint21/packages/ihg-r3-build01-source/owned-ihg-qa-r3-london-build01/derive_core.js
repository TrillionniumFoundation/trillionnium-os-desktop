
return function deriveIhgR3Core(h,d,parent,workerRaw){
 const manifest=JSON.parse(parent.files["SOURCE_PINS.json"]);
 for(const [name,pin]of Object.entries(manifest.files))if(h.utf8(parent.files[name]).length!==pin.bytes||h.sha(parent.files[name])!==pin.sha256)throw Error("parent source pin "+name);
 const worker=JSON.parse(workerRaw);
 if(worker.ok!==true||worker.owned_package_uid!==10153||worker.state.helper.self_uid!==10153)throw Error("prior IHG actual");
 let files={},proof={},functional=[];
 const replacements=[["org.droidloom.qa.ihg.r2","org.droidloom.qa.ihg.r3"],["org/droidloom/qa/ihg/r2","org/droidloom/qa/ihg/r3"],["pocket4-owned-ihg-qa-v2","pocket4-owned-ihg-qa-v3"],["owned-ihg-qa-r2","owned-ihg-qa-r3"],["/home/alex/work/pocket4-owned-ihg-qa-r3-source-02","/home/alex/work/pocket4-owned-ihg-qa-r3-source-01"],["/home/alex/work/pocket4-owned-ihg-qa-r3-build-02","/home/alex/work/pocket4-owned-ihg-qa-r3-build-01"]];
 for(const [oldName,raw]of Object.entries(parent.files)){
  if(["SOURCE_PINS.json","current-baseline-binding.json","README.md"].includes(oldName))continue;
  let name=oldName,next=raw,edits=[];
  if(!["build-input-reference.json","target-artifact-reference.json","check_current_baseline.py"].includes(oldName))for(const[from,to]of replacements){const count=next.split(from).length-1;if(count){next=next.split(from).join(to);edits.push({from,to,count});}name=name.split(from).join(to);}
  let inverse=next;for(const e of [...edits].reverse())inverse=inverse.split(e.to).join(e.from);if(inverse!==raw)throw Error("inverse "+oldName);
  files[name]=next;proof[name]={parent_path:oldName,parent:{bytes:h.utf8(raw).length,sha256:h.sha(raw)},literal_edits:edits,inverse_before_functional_edits_byte_exact:true};
 }
 function edit(name,from,to,count=1){const actual=files[name].split(from).length-1;if(actual!==count)throw Error("edit count "+name+" "+actual+" "+from);files[name]=files[name].split(from).join(to);functional.push({name,from,to,count});}
 edit("qa_contract.py","# Legacy text branch remains unreachable: this revision rejects set_text at all request entries.\nPUBLIC_SEARCH_QUERY = \"usb c cable\"","# R3 admits only the fixed public destination value through the existing exact resource action.\nPUBLIC_SEARCH_QUERY = \"London\"");
 edit("qa_contract.py","require(op in ('state','inspect','click'),'IHG_READ_INSPECT_CLICK_ONLY')","require(op in ('state','inspect','click','set_text'),'IHG_FIXED_PUBLIC_DESTINATION_OPERATIONS_ONLY')");
 edit("qa_adapter.py","plan.get('operation') in ('state','inspect','click'), 'OWNED_PLAN_REQUIRED'","plan.get('operation') in ('state','inspect','click','set_text'), 'OWNED_PLAN_REQUIRED'");
 edit("qa_contract.py","10175, 10184, 10190) and value.get('self_uid')","10175, 10184, 10190, 10196, 10153) and value.get('self_uid')");
 edit("qa_adapter.py","10175,10184,10190),","10175,10184,10190,10196,10153),");
 const java="src/org/droidloom/qa/ihg/r3/ActionRunner.java";
 edit(java,"    // Legacy set_text branch is unreachable: onStart rejects it before claim/connection.\n    static final String PUBLIC_SEARCH_QUERY = \"usb c cable\";","    // R3 admits only the fixed public destination value through the original guarded resource action.\n    static final String PUBLIC_SEARCH_QUERY = \"London\";");
 edit(java,'need(op.equals("state") || op.equals("inspect") || op.equals("click"), "IHG_READ_INSPECT_CLICK_ONLY");','need(op.equals("state") || op.equals("inspect") || op.equals("click") || op.equals("set_text"), "IHG_FIXED_PUBLIC_DESTINATION_OPERATIONS_ONLY");');
 edit("make_build_request.py","KEY='pocket4-owned-ihg-qa-r3-current-163e3e3914f4ccbb-host-6d99374e1580-build02'","KEY='pocket4-owned-ihg-qa-r3-public-London-current-163e3e3914f4ccbb-host-6d99374e1580-build01'");
 const binding={...parent.binding,helper_package:"org.droidloom.qa.ihg.r3",protocol:"pocket4-owned-ihg-qa-v3",parent_source_manifest_sha256:parent.manifest_sha256,previous_helper_uid_exclusion:{uids:[10196,10153],current_r2_actual_worker:{bytes:12552,sha256:"81f25ba7fcced82ecc0534ce41f70b7b98ce1f152aa1e5e6c132db825d65fb58",git_blob:"afc854a602a1b85d19e995f4df9c8f55e7ad13ed"}},new_operations:["state","inspect","click","set_text"],fixed_public_input:"London",new_helper_uid:null,new_APK_sha256:null,new_signer_sha256:null,helper_built:false,helper_installed:false};
 files["current-baseline-binding.json"]=JSON.stringify(binding,null,2)+"\n";
 let diff=[];for(const[name,p]of Object.entries(proof)){const old=parent.files[p.parent_path];if(old!==files[name])diff.push(d.unified(old,files[name],"r2/"+p.parent_path,"r3/"+name));}
 return{files,proof,functional_edits:functional,binding,core_diff:diff.join("\n"),state:"SOURCE_PREPARATION_NOT_FROZEN_NOT_EXECUTED"};
}