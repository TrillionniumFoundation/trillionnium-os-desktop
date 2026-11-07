(function deriveTicket02WorkerResultReader(input,H){
 const need=(v,m)=>{if(!v)throw Error(m);},pin=s=>{need(typeof s==="string","raw UTF8 required");const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
 const pins={
  baseline_source:{bytes:15012,sha256:"7643fc0718b6efa7a6822e374039a4ccd859539b0a8ed8d66a3872b4d8cb809a",git_blob_sha1:"c1446ecb35304cff408c3437e5e2b25e4c5ad592"},
  baseline_request:{bytes:16419,sha256:"03d6ff191192ebc71e649ffaeead1f3a7a230c08d94df5b3dce01d91b369858c",git_blob_sha1:"b8b4cf2d01c8e1fa3ea972644af573583d9d9657"},
  coordinator:{bytes:3498,sha256:"8953cdd7a45d0c12624e3654e31cadfcfad72c045aea325b4d94bd7785fb44f5",git_blob_sha1:"83c40bf6ae18e3dc61d28217c5cd88aaf529a145"},
  terminal:{bytes:728,sha256:"9caf0d62124b0b78faf6128bce6ebd7a748228e2be3e81203e6c084a1c306beb",git_blob_sha1:"153620fa590bc72497438f3b2ebeac83bceb6dd9"}
 };
 need(Object.keys(input).sort().join("|")===Object.keys(pins).sort().join("|"),"exact four inputs");
 for(const [k,p]of Object.entries(pins))need(JSON.stringify(pin(input[k]))===JSON.stringify(p),"fixed raw authority "+k);
 const original=input.baseline_source,q=JSON.parse(input.baseline_request),c=JSON.parse(input.coordinator),t=JSON.parse(input.terminal),job="1a1b32bc2a2-fc05-80e9";
 need(q.stdin===original,"baseline request exact source");
 const file={bytes:7230,path:"/home/alex/work/pocket4-owned-ticket12306-qa-r1-install-state-02/worker/result.json",sha256:"e8bd8ead8cb65ee26e5ac6ff493cc22aabc79a1a8b2cf79b2fefe86e820ee81b"};
 need(c.ok===false&&c.package==="org.droidloom.qa.ticket12306.r1"&&c.target_package==="com.MobileTicket"&&c.package_outcome_requires_exact_worker_reconciliation===true,"actual failed coordinator");
 need(Object.keys(c.failed_worker_result).sort().join("|")===Object.keys(file).sort().join("|")&&Object.keys(file).every(k=>c.failed_worker_result[k]===file[k]),"exact failed_worker_result");
 need(c.error.phase==="coordinator"&&c.error.type==="RuntimeError"&&c.error.message==="01-install-state did not complete exactly once with a preserved Main fence","primary error preserved");
 need(c.secondary_errors.length===1&&c.secondary_errors[0].phase==="coordinator_final_Main"&&c.secondary_errors[0].type==="RuntimeError"&&c.secondary_errors[0].message==="OWNER_SINGLE_DIRECT_CHILD_REQUIRED","secondary Main error preserved");
 need(t.job_id===job&&t.state==="failed"&&t.exit_code===1&&t.output_complete===true&&t.output_durable===true&&t.terminal_publication_confirmed===true&&t.timed_out===false&&t.cancelled===false&&t.automatic_retry===false,"actual failed terminal");
 need(t.log_bytes.stdout.seen===1042&&t.log_bytes.stdout.stored===1042&&t.log_bytes.stderr.seen===0&&t.log_bytes.stderr.stored===0&&["stdout","stderr"].every(k=>t.log_synced[k]===true&&t.log_truncated[k]===false&&t.log_errors[k]===null),"actual complete durable output");
 let source=original;const edits=[];
 const line=prefix=>{const x=original.split("\n").filter(s=>s.startsWith(prefix));need(x.length===1,"unique baseline line "+prefix);return x[0];};
 function edit(id,before,after){need(before.length>0&&before!==after,"changed edit "+id);const p=source.indexOf(before);need(p>=0&&p===source.lastIndexOf(before),"unique edit "+id);source=source.slice(0,p)+after+source.slice(p+before.length);edits.push({id,before,after});}
 edit("description",'"""Collect only the exact pinned owned Hilton failed worker result; no runtime actions."""','"""Collect only the exact pinned owned Ticket12306 failed worker result; no runtime actions."""');
 edit("single_actual_worker_result",line("FILES="),"FILES="+JSON.stringify({worker_result:file}));
 edit("full_original_authorities",line("AUTHORITY_RAW="),"AUTHORITY_RAW="+JSON.stringify({coordinator:input.coordinator,terminal:input.terminal}));
 edit("full_original_authority_pins",line("AUTHORITY_PINS="),"AUTHORITY_PINS="+JSON.stringify(Object.fromEntries(["coordinator","terminal"].map(k=>[k,{bytes:pins[k].bytes,sha256:pins[k].sha256}]))));
 edit("actual_job",line("JOB="),"JOB='"+job+"'");
 edit("reader_kind","'kind':'pocket4-owned-hilton-install01-fixed-worker-result-read01'","'kind':'pocket4-owned-ticket12306-install02-fixed-worker-result-read01'");
 edit("actual_stdout_length","t['log_bytes']=={'stdout':{'seen':919,'stored':919},'stderr':{'seen':0,'stored':0}}","t['log_bytes']=={'stdout':{'seen':1042,'stored':1042},'stderr':{'seen':0,'stored':0}}");
 const oldParent=`        need(parent['ok'] is False and parent['package']=='org.droidloom.qa.hilton.r1' and
             parent['target_package']=='com.hilton.android.hhonors' and
             parent['failed_worker_result']==FILES['worker_result'] and
             parent['package_outcome_requires_exact_worker_reconciliation'] is True,
             'EXACT_FAILED_WORKER_AUTHORITY')`;
 edit("actual_failed_package_names",oldParent,oldParent.replace("org.droidloom.qa.hilton.r1","org.droidloom.qa.ticket12306.r1").replace("com.hilton.android.hhonors","com.MobileTicket"));
 need(edits.length===8,"exact eight edits");
 let inverse=source;
 for(const e of edits.slice().reverse()){const p=inverse.indexOf(e.after);need(p>=0&&p===inverse.lastIndexOf(e.after),"unique inverse "+e.id);inverse=inverse.slice(0,p)+e.before+inverse.slice(p+e.after.length);}
 need(inverse===original,"full original inverse");
 const preserved=[
  ["read_exact_file","def read_exact_file(","\nclass ReadDeadline("],
  ["public_error_and_deadline","\nclass ReadDeadline(","\ndef main():"],
  ["two_complete_reads_signal_and_FD_finally","        need(signal.getitimer(",null]
 ].map(([name,start,end])=>{
  const select=s=>{const p=s.indexOf(start);need(p>=0&&p===s.lastIndexOf(start),"segment start "+name);const e=end===null?s.length:s.indexOf(end,p+start.length);need(e>=p,"segment end "+name);return s.slice(p,e);};
  const a=select(original),b=select(source);need(a===b,"preserved "+name);return {name,...pin(a),unchanged:true};
 });
 need(source.includes("t['state']=='failed' and t['exit_code']==1")&&source.includes("'EXACT_COMPLETE_FAILED_TERMINAL'")&&source.includes("'EXACT_FAILED_WORKER_AUTHORITY'"),"failed semantics unchanged");
 need(source.includes("need(len(result['read_events'])==2,'EXACT_TWO_COMPLETE_READS')")&&source.includes("'installation_outcome_qualified':False,'runtime_qualified':False"),"two reads and unqualified outcome");
 q.stdin=source;q.idempotency_key="p4-ticket12306-install02-worker-result-read01-"+pin(source).sha256.slice(0,16);
 const request=JSON.stringify(q,null,2)+"\n",a=JSON.parse(input.baseline_request),b=JSON.parse(request);
 for(const x of [a,b]){delete x.stdin;delete x.idempotency_key;}need(JSON.stringify(a)===JSON.stringify(b),"all other envelope fields unchanged");
 return {source,request,edits,proof:{schema:1,state:"SOURCE_ONLY_NOT_DISPATCHED",prefix:"ticket12306_install02_worker_result_read01",input_pins:pins,source:pin(source),request:pin(request),exact_edit_count:8,edits:edits.map(e=>({id:e.id,before:pin(e.before),after:pin(e.after)})),full_inverse_original_source:true,preserved_segments:preserved,failed_terminal_and_coordinator_semantics_retained:true,request_envelope_except_stdin_and_key_unchanged:true,original_authorities_preserved_raw:true,worker_result:file,original_job:job,complete_read_count:2,worker_result_read_by_candidate:false,installation_outcome:"UNKNOWN_PENDING_FULL_WORKER_REVIEW",stage_final_Main_equality_does_not_erase_coordinator_failure:true,stage_used_as_runtime_authority:false,Python_executed:false,Hepta_calls:0,original_installation_replayed:false,installation_outcome_qualified:false,runtime_qualified:false}};
})
