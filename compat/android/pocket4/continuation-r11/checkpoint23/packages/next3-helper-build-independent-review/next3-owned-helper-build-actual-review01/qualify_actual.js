function qualifyNext3Actual(slug,candidate,buildOriginal,stageOriginal,h,top){
const need=(v,m)=>{if(!v)throw Error(slug+':'+m)};
const canonical=value=>JSON.stringify((function walk(v){return Array.isArray(v)?v.map(walk):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,walk(v[k])])):v;})(value));
const b=JSON.parse(buildOriginal.raw),s=JSON.parse(stageOriginal.raw),mf=JSON.parse(candidate.files['SOURCE_PINS.json']),pin=h.sha(candidate.files['SOURCE_PINS.json']),f=top(buildOriginal.raw);
need(b.state==='BUILT_STATIC_VERIFIED_ANDROID_UNRUN'&&b.package==='org.droidloom.qa.'+slug+'.r1'&&b.source_manifest_sha256===pin,'completed own build');
need(canonical(b.source_sha256)===canonical(Object.fromEntries(Object.entries(mf.files).map(([k,r])=>[k,r.sha256])))&&b.source_unchanged===true&&b.tools_unchanged===true,'source closure');
for(const[k,r]of Object.entries(mf.files))need(h.sha(candidate.files[k])===r.sha256&&h.utf8(candidate.files[k]).length===r.bytes,'source '+k);
const tools=JSON.parse(candidate.files['build-input-reference.json']).tools;
need(f.tools_before===f.tools_after&&canonical(Object.keys(tools).sort())===canonical(Object.keys(b.tools_before).sort()),'lossless tools equality');
for(const[k,r]of Object.entries(tools))need(b.tools_before[k].declared_path===r.path&&b.tools_before[k].sha256===r.sha256&&Number.isInteger(b.tools_before[k].bytes)&&b.tools_before[k].bytes>0,'tool '+k);
const names=['javac','deep-tree-contract','d8','aapt-package','align','create-owned-signing-key','sign','signature','alignment','badging','permissions','manifest'];
need(canonical(b.commands.map(x=>x.name))===canonical(names)&&b.commands.every(x=>x.returncode===0&&x.owned_child_joined===true&&x.error===null&&x.secondary_errors.length===0),'twelve joined commands');
const scoped=b.current_baseline_scope_controls,r=scoped.report,d=b.deep_tree_protocol_controls;
need(scoped.source_sha256===mf.files['check_current_baseline.py'].sha256&&r.all_passed===true&&r.count===32&&r.cases.length===32&&new Set(r.cases.map(x=>x.name)).size===32&&r.cases.every(x=>x.passed===true)&&r.production_contract_sha256===mf.files['qa_contract.py'].sha256&&r.production_adapter_sha256===mf.files['qa_adapter.py'].sha256,'32 scope controls');
const binding=mf.current_baseline_binding;
need(r.host_recorder_manifest_sha256===binding.host_recorder_source_manifest.sha256&&r.main_epoch_sha256===binding.current_epoch_sha256&&r.main_baseline_schema===binding.current_baseline_schema&&r.main_baseline_sha256===binding.current_baseline.sha256&&r.main_baseline_qualification_sha256===binding.current_qualification.sha256&&r.helper_installed_uid===null,'actual scope identity');
need(d.state==='PASS_PROTOCOL_CONTROLS_ONLY'&&d.cases===16&&d.case_names.length===16&&new Set(d.case_names).size===16&&d.synthetic_only===true&&d.Java_scanner_executed===false&&d.Android_actions===0,'16 deep protocol controls');
need(b.error===null&&b.android_installed===false&&b.Main_mutations===0&&b.Android_UI_actions===0&&b.whole_app_production_ready===false,'build scope');
need(canonical(b.manifest_contract)===canonical({activities:[],compile_sdk_api:31,debuggable:false,instrumentation:b.package+'.ActionRunner',min_sdk:31,native_libraries:[],package:b.package,permissions:[],providers:[],receivers:[],services:[],target_package:b.package,target_sdk:33,test_only:true}),'APK manifest');
need(s.state==='OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN'&&s.source_manifest_sha256===pin&&s.root===candidate.sourceRoot&&s.source===candidate.sourceRoot+'/source'&&s.output===candidate.outputRoot&&s.build_returncode===0&&s.error===null&&s.secondary_errors.length===0,'stage source and output');
need(canonical(s.build_result)===canonical({path:candidate.outputRoot+'/build-result.json',bytes:buildOriginal.bytes,sha256:buildOriginal.sha256}),'stage child binding');
for(const row of[s.owned_before,s.owned_after]){
need(row['memory.max']==='536870912'&&row['memory.swap.max']==='0'&&row['cpu.max']==='100000 100000'&&row['pids.max']==='128'&&row['memory.swap.current']==='0'&&row['memory.swap.peak']==='0','resource limits');
const ev=Object.fromEntries(row['memory.events'].split('\n').map(x=>x.split(' ')));for(const k of['max','oom','oom_kill','oom_group_kill'])need(ev[k]==='0','memory events');
}
need(s.owned_before.cgroup===s.owned_after.cgroup&&s.owned_before.device===s.owned_after.device&&s.owned_before.inode===s.owned_after.inode,'owned cgroup identity');
need(b.APK.path===candidate.outputRoot+'/owned-'+slug+'-qa.apk'&&b.APK.bytes===24720&&/^[0-9a-f]{64}$/.test(b.APK.sha256)&&/^[0-9a-f]{64}$/.test(b.signer_certificate_sha256),'APK and signer');
return {slug,actual_build:{bytes:buildOriginal.bytes,sha256:buildOriginal.sha256,blob:buildOriginal.blob,tree:buildOriginal.tree},actual_stage:{bytes:stageOriginal.bytes,sha256:stageOriginal.sha256,blob:stageOriginal.blob},state:'ACTUAL_STATIC_BUILD_INDEPENDENTLY_QUALIFIED',source_manifest_sha256:pin,source_files:Object.keys(mf.files).length,command_count:12,scope_controls:32,deep_protocol_controls:16,tool_values_unchanged_lossless:true,scope_controls_not_scanner_execution:true,APK:b.APK,signer_certificate_sha256:b.signer_certificate_sha256,helper_UID:null,installed:false,UI_or_launch:false,whole_app_production_ready:false};
}
