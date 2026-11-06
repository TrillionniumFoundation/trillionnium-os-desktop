function qualifyNormal09(i,H){
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
const fixed={
request:{bytes:1037404,sha256:"d5da9237867a577b4076f0b2ecfd975cb5da5d9dcf907bc906d9cb47c75175d1"},
outer:{bytes:24759,sha256:"873a8c03dc51a62e69aaeab28e7929ef2b8b48019d9d1ca949e23ce07d3f3d1a"},
resource:{bytes:2749,sha256:"62bc5109a8ed50722560b6374caa1b0581d53abaa0d300e510adbeb85acfb2cd"},
before:{bytes:6338,sha256:"cc9b0a9953b4ec097378108a2775e042f830b28d48e887b1b164c12cb0f9b4b6"},
after:{bytes:6338,sha256:"9f844120f0eb8def128979c029bd97d5ffc81b8b510e5265ba791ed0cddd4fb1"},
stage:{bytes:5153,sha256:"62404efff7a5d6b7e8acd29b9d4b922aae76467c05cd67cbb41ffc007974d543"},
stdout:{bytes:1319,sha256:"de3c9caa74338ed433c87e8fa7945425f7d975f8906432d0a0645677a5a819e5"},
terminal:{bytes:728,sha256:"281a07e6ec183acab3569fa99e7a0af097a74b456a43cb4b1a466907ae1291bd"}
};
const pins={};for(const [k,p]of Object.entries(fixed)){const v=pin(i[k]);need(v.bytes===p.bytes&&v.sha256===p.sha256,"exact original "+k);pins[k]=v;}
const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==="object"?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
function lossless(raw){
 const sentinel="__exact_JSON_number__";need(!raw.includes(sentinel),"lossless sentinel");
 let result="",at=0;
 while(at<raw.length){
 if(raw[at]==='"'){const start=at++;while(at<raw.length){const c=raw[at++];if(c==="\\"){at++;continue;}if(c==='"')break;}result+=raw.slice(start,at);continue;}
 if(raw[at]==="-"||(raw[at]>="0"&&raw[at]<="9")){
 const m=raw.slice(at).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);need(m,"numeric JSON token");
 result+=JSON.stringify(sentinel+m[0]);at+=m[0].length;continue;
 }result+=raw[at++];
 }
 return JSON.parse(result);
}
const q=JSON.parse(i.request),packet=JSON.parse(q.stdin),o=JSON.parse(i.outer),r=JSON.parse(i.resource),st=JSON.parse(i.stage),terminal=JSON.parse(i.terminal);
const out=i.stdout.trimEnd().split("\n").map(x=>JSON.parse(x));
need(Object.keys(packet.files).length===18&&out.length===2,"exact source packet/stdout rows");
for(const[n,t]of Object.entries(packet.files)){const p=pin(t);need(st.files[n].bytes===p.bytes&&st.files[n].sha256===p.sha256,"actual staged source "+n);}
need(Object.keys(st.files).length===18&&st.pure_controls.state==="PASS"&&st.pure_controls.passed===46&&st.pure_controls.cases.length===46&&new Set(st.pure_controls.cases).size===46,"actual46 pure controls");
const error="RuntimeError('less than 15 GiB MemAvailable for independent zero-swap profile; no automatic retry')";
need(o.state==="FAILED"&&o.error===error&&o.inner_build_called===true&&o.inner_returncode===null,"resource rejection original classification");
need(out[0].state==="FRESH_RESOURCE_ADMISSION_OBSERVED"&&out[0].receipt.bytes===pins.resource.bytes&&out[0].receipt.sha256===pins.resource.sha256&&out[1].state==="FAILED"&&out[1].error===error&&out[1].inner_returncode===null&&out[1].terminal_sha256===pins.outer.sha256,"stdout parents");
need(terminal.job_id==="1a1b26245a3-fc05-7dd3"&&terminal.state==="failed"&&terminal.exit_code===1&&terminal.timed_out===false&&terminal.output_complete===true&&terminal.output_durable===true&&terminal.terminal_publication_confirmed===true&&!terminal.automatic_retry&&!terminal.cancelled&&terminal.log_bytes.stdout.stored===1319&&terminal.log_bytes.stderr.stored===0&&!terminal.log_truncated.stdout&&!terminal.log_truncated.stderr,"actual terminal complete");
const p={memory_max_bytes:10737418240,memory_swap_max_bytes:0,minimum_fresh_MemAvailable_bytes:16106127360,admission_difference_bytes:5368709120,global_swap_is_owned_budget:false};
need(equal(r.profile,p)&&r.state==="OBSERVED_BEFORE_RESOURCE_ADMISSION"&&r.decision_performed===false&&r.historical_sample_used_for_admission===false,"exact resource profile/observation boundary");
const raw=r.meminfo.raw_ascii,rawPin=pin(raw);need(rawPin.bytes===r.meminfo.bytes&&rawPin.sha256===r.meminfo.sha256,"full meminfo hash");
const mem={};for(const n of ["MemTotal","MemAvailable","SwapTotal","SwapFree","SwapCached"]){const lines=raw.split("\n").filter(x=>x.startsWith(n+":"));need(lines.length===1,"one meminfo "+n);const m=lines[0].match(/^[A-Za-z]+:\s+([0-9]+) kB$/);need(m,"meminfo units");mem[n]=Number(m[1])*1024;need(Number.isSafeInteger(mem[n]),"safe meminfo integer");}
need(mem.MemAvailable===14854873088&&mem.MemAvailable<p.minimum_fresh_MemAvailable_bytes&&equal(r.owned_observed,{"memory.max":"10737418240","cpu.max":"200000 100000","memory.swap.max":"0","memory.swap.current":"0"}),"actual lower-than-threshold observation");
const ctr=o.capture_lifecycle_controls,phases=["control-root-timeout","control-root-escaped","control-root-pidfd","control-outer-pidfd","before","after"];
need(ctr.state==="PASS"&&ctr.passed===4&&ctr.rows.length===4&&ctr.rows.every(x=>x.passed&&x.owned_children_empty&&!x.Main_read_performed)&&equal(o.capture_lifecycle_receipts.map(x=>x.phase),phases),"four real lifecycle controls/six receipts");
for(const x of o.capture_lifecycle_receipts){
 const c=x.command;need(x.outer_subreaper.final_children_empty&&x.outer_subreaper.restored&&x.within_absolute_outer_deadline&&!x.secondary_errors.length&&c.child_reaped&&c.owned_tree_cleanup_complete&&c.pidfd_closed&&c.all_acquired_fds_closed&&c.retirement_within_deadline&&!c.remaining_owned_children.length&&!c.secondary_errors.length,"fully retired "+x.phase);
 if(x.phase==="control-outer-pidfd")need(!x.qualified_success&&c.returncode===-9&&x.first_error.errno===24&&c.first_error.errno===24,"preserve expected pidfd failure");
 else need(x.qualified_success&&c.qualified_success&&c.returncode===0&&x.first_error===null&&c.first_error===null,"successful capture "+x.phase);
}
const before=lossless(i.before),after=lossless(i.after);
need(before.ok===true&&after.ok===true&&before.cleanup_errors.length===0&&after.cleanup_errors.length===0,"both Main snapshots closed");
for(const k of ["historical_activation_sha256","old_invalid_QA_epoch_sha256","old_QA_epoch_invalid","new_QA_epoch_qualified","protected_boot_id","protected_identity_source_sha256","actual_baseline02_stdout_sha256","protected_processes","cell_sha256","limits","main_cgroup","main_cgroup_identity","memory_events"])need(equal(before[k],after[k]),"lossless Main invariant "+k);
need(Object.keys(before.protected_processes).length===8&&o.main_fence_assessment.main_fence_pass&&o.main_fence_assessment.identity_or_limit_changes.length===0&&Object.values(o.main_fence_assessment.main_memory_event_deltas).every(x=>x===0)&&o.main_fence_assessment.main_current_resource_deltas["memory.swap.current"]===0&&!o.main_fence_assessment.unobserved_transient_effects_excluded&&!o.main_fence_assessment.causal_attribution_of_counter_changes,"limited pre/post Main conclusions");
const f=packet.files["framework_build.py"],a=f.indexOf("    context = verify_prepared(expected_sha)"),b=f.indexOf("    memory, owned_budget_before, resource_admission_pin = record_resource_admission(cgroup)",a),c=f.indexOf("    subreaper()",b),d=f.indexOf("    ATTEMPT.mkdir(mode=0o700)",c),e=f.indexOf("child = subprocess.Popen",d);
need(a>=0&&b>a&&c>b&&d>c&&e>d,"actual error precedes builder launch in exact controller");
return{schema:1,state:"ORIGINAL_NORMAL09_RESOURCE_REJECTION_VERIFIED",actual_tree:"0364500bdb51a4e38ccfcfe99594edfd41cf548d",pins,observed_utc:r.observed_utc,MemAvailable_bytes:mem.MemAvailable,required_bytes:p.minimum_fresh_MemAvailable_bytes,shortfall_bytes:p.minimum_fresh_MemAvailable_bytes-mem.MemAvailable,inner_build_called_original:true,inner_returncode_original:null,builder_or_Soong_started:false,source_basis_for_prelaunch_failure:"The fixed error is raised by record_resource_admission after verify_prepared and before subreaper, attempt creation and Popen.",pure_controls:46,real_lifecycle_controls:4,capture_retirements:6,Main_lossless_pre_post_roles_equal:8,Main_events_all_zero:true,Main_swap_delta_zero:true,full_interval_noninterference_claimed:false,all_original_JSON_bytes_preserved:true,future_resource_admission_qualified:false,automatic_retry_allowed:false,production_ready:false};
}
