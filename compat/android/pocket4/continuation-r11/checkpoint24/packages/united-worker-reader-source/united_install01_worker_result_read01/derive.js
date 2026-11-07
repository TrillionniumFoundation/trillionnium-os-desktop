(function deriveUnitedFixedWorkerReader(input,H){
  const need=(v,m)=>{if(!v)throw Error(m);};
  const pin=s=>{need(typeof s==="string","raw UTF8 string required");const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
  const fixed={
    baseline_source:{bytes:15012,sha256:"7643fc0718b6efa7a6822e374039a4ccd859539b0a8ed8d66a3872b4d8cb809a",git_blob_sha1:"c1446ecb35304cff408c3437e5e2b25e4c5ad592"},
    baseline_request:{bytes:16419,sha256:"03d6ff191192ebc71e649ffaeead1f3a7a230c08d94df5b3dce01d91b369858c",git_blob_sha1:"b8b4cf2d01c8e1fa3ea972644af573583d9d9657"},
    coordinator:{bytes:4469,sha256:"341ee027b4c9767fa3b0dab127444d526be6291f4f2fd38da89d98ab3a1fca0f",git_blob_sha1:"b84048d7c948dfac6b5bd5ecf14491860989e29a"},
    terminal:{bytes:729,sha256:"0b02dcce3efd992d951b3733035978660cf03cbce0575df2639fb60dbfec67d2",git_blob_sha1:"a3b5cd1bdcfc7e794a22f6c8c56787f26a43e870"}
  };
  need(Object.keys(input).sort().join("|")===Object.keys(fixed).sort().join("|"),"exact four inputs");
  for(const [k,p]of Object.entries(fixed))need(JSON.stringify(pin(input[k]))===JSON.stringify(p),"fixed input pin "+k);
  const baseline=input.baseline_source,q=JSON.parse(input.baseline_request),c=JSON.parse(input.coordinator),t=JSON.parse(input.terminal);
  need(q.stdin===baseline,"baseline request source");
  const job="1a1b31ad6e2-fc05-80a1";
  const file={bytes:16495,path:"/home/alex/work/pocket4-owned-united-qa-r1-install-state-01/worker/result.json",sha256:"4b00d7f66902fbcd933599ca5e7d85fa6369833e2feb0b594f9ab395eee6e858"};
  need(t.job_id===job&&t.state==="succeeded"&&t.exit_code===0&&t.output_complete===true&&t.output_durable===true&&t.terminal_publication_confirmed===true&&t.timed_out===false&&t.cancelled===false&&t.automatic_retry===false,"actual success terminal");
  need(t.log_bytes.stdout.seen===682&&t.log_bytes.stdout.stored===682&&t.log_bytes.stderr.seen===0&&t.log_bytes.stderr.stored===0&&["stdout","stderr"].every(k=>t.log_synced[k]===true&&t.log_truncated[k]===false&&t.log_errors[k]===null),"actual full logs");
  need(c.ok===true&&c.error===null&&Array.isArray(c.secondary_errors)&&c.secondary_errors.length===0&&c.source_and_artifact_unchanged===true&&c.package==="org.droidloom.qa.united.r1"&&c.target_package==="com.united.mobile.android"&&c.owned_package_uid===10163&&c.owned_package_retained_for_separate_UI_admission===true&&c.install_state_worker_requested===true,"actual coordinator success");
  need(Object.keys(c.worker_result).sort().join("|")===Object.keys(file).sort().join("|")&&Object.keys(file).every(k=>c.worker_result[k]===file[k]),"actual unique worker result");
  need(c.worker_root==="/home/alex/work/pocket4-owned-united-qa-r1-install-state-01/worker","actual worker root");
  let source=baseline;const edits=[];
  function edit(id,before,after){
    need(typeof before==="string"&&before.length>0&&before!==after,"nonempty changed edit "+id);
    const first=source.indexOf(before);need(first>=0&&first===source.lastIndexOf(before),"unique edit "+id);
    source=source.slice(0,first)+after+source.slice(first+before.length);
    edits.push({id,before,after});
  }
  function line(prefix){const hits=baseline.split("\n").filter(s=>s.startsWith(prefix));need(hits.length===1,"unique baseline line "+prefix);return hits[0];}
  edit("description",'"""Collect only the exact pinned owned Hilton failed worker result; no runtime actions."""','"""Collect only the exact pinned owned United successful worker result; no runtime actions."""');
  edit("single_fixed_file",line("FILES="),"FILES="+JSON.stringify({worker_result:file}));
  edit("full_original_authority",line("AUTHORITY_RAW="),"AUTHORITY_RAW="+JSON.stringify({coordinator:input.coordinator,terminal:input.terminal}));
  edit("full_original_authority_pins",line("AUTHORITY_PINS="),"AUTHORITY_PINS="+JSON.stringify(Object.fromEntries(["coordinator","terminal"].map(k=>[k,{bytes:fixed[k].bytes,sha256:fixed[k].sha256}]))));
  edit("actual_job",line("JOB="),"JOB='"+job+"'");
  edit("reader_kind","'kind':'pocket4-owned-hilton-install01-fixed-worker-result-read01'","'kind':'pocket4-owned-united-install01-fixed-worker-result-read01'");
  const oldTerminal=`        need(t['job_id']==JOB and t['state']=='failed' and t['exit_code']==1 and
             t['output_complete'] is True and t['output_durable'] is True and
             t['terminal_publication_confirmed'] is True and
             t['timed_out'] is False and t['cancelled'] is False and t['automatic_retry'] is False and
             t['log_bytes']=={'stdout':{'seen':919,'stored':919},'stderr':{'seen':0,'stored':0}} and
             all(t['log_synced'][k] is True and t['log_truncated'][k] is False and
                 t['log_errors'][k] is None for k in ('stdout','stderr')),
             'EXACT_COMPLETE_FAILED_TERMINAL')`;
  edit("successful_terminal_contract",oldTerminal,oldTerminal.replace("t['state']=='failed' and t['exit_code']==1","t['state']=='succeeded' and t['exit_code']==0").replace("'seen':919,'stored':919","'seen':682,'stored':682").replace("'EXACT_COMPLETE_FAILED_TERMINAL'","'EXACT_COMPLETE_SUCCESSFUL_TERMINAL'"));
  const oldParent=`        need(parent['ok'] is False and parent['package']=='org.droidloom.qa.hilton.r1' and
             parent['target_package']=='com.hilton.android.hhonors' and
             parent['failed_worker_result']==FILES['worker_result'] and
             parent['package_outcome_requires_exact_worker_reconciliation'] is True,
             'EXACT_FAILED_WORKER_AUTHORITY')`;
  const newParent=`        need(parent['ok'] is True and parent['error'] is None and
             parent['secondary_errors']==[] and parent['source_and_artifact_unchanged'] is True and
             parent['package']=='org.droidloom.qa.united.r1' and
             parent['target_package']=='com.united.mobile.android' and
             parent['worker_result']==FILES['worker_result'] and
             parent['worker_root']=='/home/alex/work/pocket4-owned-united-qa-r1-install-state-01/worker' and
             parent['owned_package_uid']==10163 and
             parent['owned_package_retained_for_separate_UI_admission'] is True and
             parent['install_state_worker_requested'] is True,
             'EXACT_SUCCESSFUL_WORKER_AUTHORITY')`;
  edit("successful_coordinator_contract",oldParent,newParent);
  need(edits.length===8,"exact eight edits");
  let inverse=source;
  for(const e of edits.slice().reverse()){
    const first=inverse.indexOf(e.after);need(first>=0&&first===inverse.lastIndexOf(e.after),"unique inverse "+e.id);
    inverse=inverse.slice(0,first)+e.before+inverse.slice(first+e.after.length);
  }
  need(inverse===baseline,"full inverse original reader");
  const sp=pin(source);
  q.stdin=source;q.idempotency_key="p4-united-install01-worker-result-read01-"+sp.sha256.slice(0,16);
  const request=JSON.stringify(q,null,2)+"\n";
  const priorEnvelope=JSON.parse(input.baseline_request),nextEnvelope=JSON.parse(request);
  for(const o of [priorEnvelope,nextEnvelope]){delete o.stdin;delete o.idempotency_key;}
  need(JSON.stringify(priorEnvelope)===JSON.stringify(nextEnvelope),"entire non-source non-key envelope unchanged");
  const segments=[
    ["read_exact_file","def read_exact_file(", "\nclass ReadDeadline("],
    ["public_error_and_deadline","\nclass ReadDeadline(", "\ndef main():"],
    ["all_read_loops_signal_and_finally","        need(signal.getitimer(",null]
  ].map(([name,start,end])=>{
    function select(s){const p=s.indexOf(start);need(p>=0&&p===s.lastIndexOf(start),"unique segment start "+name);const e=end===null?s.length:s.indexOf(end,p+start.length);need(e>=p,"segment end "+name);return s.slice(p,e);}
    const a=select(baseline),b=select(source);need(a===b,"unchanged segment "+name);return {name,...pin(a),unchanged:true};
  });
  need((source.match(/read_exact_file\(spec\['path'\]/g)||[]).length===2,"two read callsites");
  need(source.includes("need(len(result['read_events'])==2,'EXACT_TWO_COMPLETE_READS')"),"two complete read event gate");
  need(source.includes("'installation_outcome_qualified':False,'runtime_qualified':False"),"collection not installation qualification");
  return {
    source,request,edits,
    proof:{schema:1,state:"SOURCE_ONLY_NOT_DISPATCHED",kind:"united_install01_worker_result_read01",inputs:fixed,
      source:sp,request:pin(request),edits:edits.map(e=>({id:e.id,before:pin(e.before),after:pin(e.after)})),
      exact_edit_count:8,full_inverse_equals_baseline:true,unchanged_segments:segments,
      request_envelope_except_stdin_and_key_unchanged:true,original_authority_strings_preserved:true,
      fixed_file:file,original_job:job,actual_owned_package_uid:10163,
      input_read_passes:2,output_bound:131072,per_file_deadline_seconds:10,collection_deadline_seconds:20,outer_timeout_seconds:30,
      python_executed:false,Hepta_calls:0,device_reads:0,installation_outcome_qualified:false,runtime_qualified:false,
      note:"This source binds observed coordinator/terminal authority; worker content and installation details remain uncollected by this reader until Root dispatch and separate review."}
  };
})
