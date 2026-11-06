
function review(app,p) {
 const need=(x,c)=>{if(!x)throw Error(c)};
 const b=load(p+"_build_result_parsed"),s=load(p+"_stage_result_parsed"),t=load(p+"_status_latest");
 const helper=load("app_helpers02_root_derived").helpers[app],m=JSON.parse(helper.files["SOURCE_PINS.json"]);
 need(t.exit_code===0&&t.output_complete&&t.output_durable&&t.terminal_publication_confirmed&&!t.timed_out&&!t.cancelled&&t.log_bytes.stderr.seen===0&&t.log_bytes.stdout.seen===t.log_bytes.stdout.stored&&!t.log_errors.stdout&&!t.log_errors.stderr&&!t.log_truncated.stdout&&!t.log_truncated.stderr&&t.log_synced.stdout&&t.log_synced.stderr,"terminal");
 need(b.state==="BUILT_STATIC_VERIFIED_ANDROID_UNRUN"&&b.error===null&&b.source_unchanged&&b.tools_unchanged&&!b.android_installed&&!b.whole_app_production_ready&&b.Main_mutations===0&&b.Android_UI_actions===0&&!b.source_or_permissions_gate_relaxed,"build");
 const n=(app==="bili"||app==="amazon")?13:11;
 need(b.commands.length===n&&b.commands.every(x=>x.returncode===0&&x.owned_child_joined&&x.error===null&&!x.secondary_errors.length),"commands");
 need(canon(b.tools_before)===canon(b.tools_after),"tools");
 const hashes=Object.fromEntries(Object.entries(m.files).map(([k,r])=>[k,r.sha256]));
 need(canon(b.source_sha256)===canon(hashes),"source map");
 need(b.source_manifest_sha256===helper.manifest_sha256&&s.source_manifest_sha256===helper.manifest_sha256,"manifest");
 const c=b.current_baseline_scope_controls.report;
 need(c.count===21&&c.all_passed&&c.cases.length===21&&c.cases.every(x=>x.passed)&&c.production_adapter_sha256===hashes["qa_adapter.py"]&&c.production_contract_sha256===hashes["qa_contract.py"]&&c.host_recorder_manifest_sha256==="6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e","scope");
 const controls={current_baseline_and_actual_R5_Session:21};
 for(const[key,count]of[["inspection_idle_gate_controls",22],["inspection_idle_protocol_controls",32]])if(b[key]){need(b[key].report.all_passed&&b[key].report.count===count&&b[key].report.cases.every(x=>x.passed),"idle "+key);controls[key]=count;}
 need(s.state==="OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN"&&s.build_returncode===0&&!s.error&&!s.secondary_errors.length&&s.build_result.sha256===load(p+"_build_result_pin").sha256,"stage");
 need(s.owned_before["memory.events"]===s.owned_after["memory.events"]&&s.owned_after["memory.swap.peak"]==="0","resource");
 for(const k of["cgroup","device","inode","memory.max","memory.swap.max","cpu.max","pids.max"])need(canon(s.owned_before[k])===canon(s.owned_after[k]),"cgroup binding "+k);
 return {schema:1,state:"ACTUAL_CURRENT_HELPER_FREEZE02_STATIC_PASS_NOT_RUNTIME",app,job:load(p+"_job_id"),APK:b.APK,signer_sha256:b.signer_certificate_sha256,build_result:load(p+"_build_result_pin"),stage_result:load(p+"_stage_result_pin"),source_manifest_sha256:helper.manifest_sha256,source_map_exact:true,tools_before_after_exact:true,commands_passed_joined:n,controls,own_memory_peak:Number(s.owned_after["memory.peak"]),own_memory_events_unchanged:true,own_swap_peak:0,private_signing_material_exported:false,Android_installed:false,UI_actions:0,whole_app_production_ready:false};
}
return {review};
