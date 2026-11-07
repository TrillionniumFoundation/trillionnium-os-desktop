async function completeMetadata02(tools,v,ll,w,tok,read,slug) {
 const prefix=slug+"_metadata02",q=JSON.parse(load("large_apk_metadata02_file_"+slug+"/exact-request.json")),packet=JSON.parse(q.stdin);
 const status=load(prefix+"_status_latest");
 if(!status||!["succeeded","failed"].includes(status.state))return {slug,state:"RUNNING",job_id:load(prefix+"_job_id")};
 let stdout=load(prefix+"_stdout_raw"),stderr=load(prefix+"_stderr_raw");
 if(stdout===undefined){const s=await read(tools,v,ll,w,prefix,196608);stdout=s.stdout;stderr=s.stderr;}
 const lines=stdout.trimEnd().split("\n");
 v.assertThat(lines.length===2,"exact worker and stage metadata lines");
 const first=ll(lines[0]),second=ll(lines[1]),r=first.result,s=second.stage;
 const ta=tok(lines[0]),tb=tok(lines[1]);
 const resultRaw=ta.pretty(ta.member(ta.root,"result"))+"\n",stageRaw=tb.pretty(tb.member(tb.root,"stage"))+"\n";
 const rp=w.pin(resultRaw),sp=w.pin(stageRaw);
 v.assertThat(rp.bytes===first.result_file.bytes&&rp.sha256===first.result_file.sha256,"full producer result bytes "+slug);
 v.assertThat(sp.bytes===second.stage_result.bytes&&sp.sha256===second.stage_result.sha256,"full producer stage bytes "+slug);
 store(prefix+"_result_raw",resultRaw);store(prefix+"_stage_raw",stageRaw);
 const checks=[],check=(name,ok)=>{checks.push({name,passed:ok===true});};
 const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 const pkg=r.package;
 const expected=[
 ["/system/bin/cmd","package","list","packages","-U","--show-versioncode","--user","0",pkg],
 ["/system/bin/cmd","package","path","--user","0",pkg],
 ["/system/bin/cmd","package","resolve-activity","--brief","--user","0","-a","android.intent.action.MAIN","-c","android.intent.category.LAUNCHER",pkg],
 ["/system/bin/cmd","package","path","--user","0",pkg],
 ["/system/bin/cmd","package","list","packages","-U","--show-versioncode","--user","0",pkg]];
 check("complete terminal",status.exit_code===0&&status.output_complete&&status.output_durable&&status.terminal_publication_confirmed&&!status.timed_out&&!status.cancelled&&!status.automatic_retry&&stderr==="");
 check("worker and stage complete",r.ok&&s.ok&&r.error===null&&s.error===null&&r.secondary_errors.length===0&&s.secondary_errors.length===0&&s.worker_returncode===0);
 check("exact requested nonce and source",r.nonce===packet.nonce&&s.nonce===packet.nonce&&r.source_sha256===w.pin(packet.source).sha256&&s.source_sha256===r.source_sha256&&s.source_unchanged===true&&packet.source.split("\n").includes("PACKAGE = '"+pkg+"'")&&JSON.parse(load("metadata22_catalog_raw")).some(x=>x.slug===slug&&x.package===pkg));
 check("unchanged Main across worker and stage",!!r.Main_before&&!!r.Main_after&&!!s.Main_before&&!!s.Main_after&&eq(r.Main_before,r.Main_after)&&eq(r.Main_before,s.Main_before)&&eq(r.Main_before,s.Main_after)&&r.final_Main_guard_passed===true);
 check("exact five joined readonly commands",r.package_read_commands_completed===5&&r.command_observations.length===5&&r.command_observations.every((x,i)=>x.index===i+1&&eq(x.argv,expected[i])&&x.returncode===0&&x.joined===true&&x.spawned===true&&!x.host_timed_out&&x.first_error===null&&x.secondary_errors.length===0&&x.recorder_errors.length===0&&x.Android_UI_action===false));
 check("current metadata and directories stable",eq(r.metadata_before,r.metadata_after)&&eq(r.data_directories_before,r.data_directories_after)&&r.actual_package_UID_version_APK_chain_stable===true&&r.metadata_before?.uid>=10000&&r.metadata_before?.uid<100000&&r.metadata_before?.user===0&&r.metadata_before?.package===pkg);
 check("APK complete bound",Array.isArray(r.artifacts)&&r.artifacts.length>=1&&r.artifacts.length<=16&&r.artifacts.every(a=>a.held_file.bytes>0&&a.held_file.bytes<=536870912&&/^[0-9a-f]{64}$/.test(a.sha256))&&r.total_apk_bytes===r.artifacts.reduce((a,b)=>a+b.held_file.bytes,0)&&r.total_apk_bytes<=536870912);
 check("original closures",r.held_binding_released===true&&r.action_lock_released===true&&r.target_directory_cleanup?.held_data_directory_FDs_closed===2&&r.target_directory_cleanup?.contents_read===false);
 check("no UI or production upgrade",r.App_launches===0&&r.UI_actions===0&&r.instrumentation_calls===0&&r.permission_grants===0&&r.settings_writes===0&&r.target_data_directory_contents_read===false&&r.whole_app_production_ready===false&&r.automatic_retry===false);
 const qualified=checks.every(x=>x.passed);
 const review={schema:"root-current-large-apk-metadata02-actual-review-v1",slug,package:pkg,qualified,checks,uid:r.metadata_before?.uid,version_code:r.metadata_before?.version_code,apk_count:r.artifacts?.length,apk_bytes:r.total_apk_bytes,launcher:r.launcher_resolution?.component,result:rp,stage:sp,producer_file_reconstruction:"Exact original JSON tokens with producer indent only; full original bytes and SHA match. No separate disk read is claimed.",whole_app_production_ready:false,automatic_retry:false,signer_independently_verified:r.signer_certificate_independently_verified,shared_helper_process_tree_cleanup_qualified:r.shared_helper.whole_process_tree_cleanup_qualified};
 const files={"stdout.original.ndjson":stdout,"stderr.original.txt":stderr,"terminal.original.json":load(prefix+"_status_latest_text"),"result.original.json":resultRaw,"stage-result.original.json":stageRaw,"root-review.json":JSON.stringify(review,null,2)+"\n"};
 const chunks=load(prefix+"_log_chunk_originals")||[load(prefix+"_process_read0_raw")];
 chunks.forEach((raw,i)=>{if(raw!==undefined)files["process-read-"+i+".original.json"]=raw;});
 const archive=await w.archive(prefix+"_actual",files,{bound:"62d12a798c8a5706c1fac72315c98563788b7a32",preflight:load(prefix+"_preflight_tree"),admission:load(prefix+"_admission_tree")});
 store(prefix+"_review",review);
 const rows=load("large_apk_metadata02_execution_rows"),row=rows.find(x=>x.slug===slug);
 Object.assign(row,{state:qualified?"QUALIFIED_CURRENT_METADATA":"TERMINAL_UNQUALIFIED",job_id:load(prefix+"_job_id"),actual_tree:archive,package:pkg,uid:review.uid,version_code:review.version_code,apk_count:review.apk_count,artifact:rp});store("large_apk_metadata02_execution_rows",rows);
 return {slug,state:row.state,actual_tree:archive,review};
}