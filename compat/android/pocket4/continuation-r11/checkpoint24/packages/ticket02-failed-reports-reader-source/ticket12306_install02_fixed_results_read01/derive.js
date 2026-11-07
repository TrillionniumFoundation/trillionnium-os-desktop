(function deriveTicket02FixedResultsReader(input,H){
  const need=(ok,msg)=>{if(!ok)throw Error(msg);};
  const pin=s=>{need(typeof s==="string","raw UTF8 required");const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
  const required={
    "hilton-failed-two-reader.original.py":{bytes:11181,sha256:"e47300f9fbdb19e111e1142f848b55b44259bb9ae0edf8d071b57d48c2e92919",git_blob_sha1:"888527619ff962d5eabf8c999313a6823899a5ce"},
    "hilton-failed-two-request.original.json":{bytes:12094,sha256:"7f816c9eb886d9ddfa2997343e7fe1c9830f6a69eb2f35d1310fb0744baf476d",git_blob_sha1:"8ecfc613d1793497e5165609c1f73aca8c810a65"},
    "ticket-stdout.original.json":{bytes:1042,sha256:"63306308126c6e7e0f41e86bc992caba51a19d31fae15b17fcf28df480e1ef1f",git_blob_sha1:"65fb0fdbd3991470392176da08478ddc9a3d91fd"},
    "ticket-terminal.original.json":{bytes:728,sha256:"9caf0d62124b0b78faf6128bce6ebd7a748228e2be3e81203e6c084a1c306beb",git_blob_sha1:"153620fa590bc72497438f3b2ebeac83bceb6dd9"},
    "scope.json":{bytes:713,sha256:"a9d64c7bf33db314e824fab63570277c92a74bcb96799cc4b4ec0c0a12c0fe5b",git_blob_sha1:"805526586c7c79d30a205d88716b84e59e9346cd"}
  };
  need(Object.keys(input).sort().join("|")===Object.keys(required).sort().join("|"),"exact five seed originals");
  for(const [path,p]of Object.entries(required))need(JSON.stringify(pin(input[path]))===JSON.stringify(p),"fixed seed pin "+path);
  // scope.json is preserved provenance only. It supplies no runtime authority or outcome.
  const baseline=input["hilton-failed-two-reader.original.py"],originalRequest=input["hilton-failed-two-request.original.json"];
  const q=JSON.parse(originalRequest);need(q.stdin===baseline,"baseline exact stdin");
  const stdout=input["ticket-stdout.original.json"],terminal=input["ticket-terminal.original.json"];
  const summaries=stdout.trimEnd().split("\n").map(s=>JSON.parse(s)),t=JSON.parse(terminal);
  const job="1a1b32bc2a2-fc05-80e9";
  const targetFiles={
    result:{path:"/home/alex/work/pocket4-owned-ticket12306-qa-r1-install-state-02/result.json",bytes:3498,sha256:"8953cdd7a45d0c12624e3654e31cadfcfad72c045aea325b4d94bd7785fb44f5"},
    stage_result:{path:"/home/alex/work/pocket4-owned-ticket12306-qa-r1-install-state-02/stage-result.json",bytes:12969,sha256:"8761ae4760095dd408f32ebdfba40d9b31fff47cd2b199235d75bc595371d499"}
  };
  const eq=(a,b)=>Object.keys(a).sort().join("|")===Object.keys(b).sort().join("|")&&Object.keys(b).every(k=>a[k]===b[k]);
  need(summaries.length===2&&summaries.every(x=>x.ok===false)&&eq(summaries[0].result,targetFiles.result)&&eq(summaries[1].stage_result,targetFiles.stage_result),"exact two actual failed summary pins");
  need(summaries[0].package==="org.droidloom.qa.ticket12306.r1","actual package");
  need(summaries[0].error.phase==="coordinator"&&summaries[0].error.type==="RuntimeError"&&summaries[0].error.message==="01-install-state did not complete exactly once with a preserved Main fence","actual primary failure");
  need(summaries[0].secondary_errors.length===1&&summaries[0].secondary_errors[0].phase==="coordinator_final_Main"&&summaries[0].secondary_errors[0].type==="RuntimeError"&&summaries[0].secondary_errors[0].message==="OWNER_SINGLE_DIRECT_CHILD_REQUIRED","actual secondary guard failure");
  need(t.job_id===job&&t.state==="failed"&&t.exit_code===1&&t.output_complete===true&&t.output_durable===true&&t.terminal_publication_confirmed===true&&t.timed_out===false&&t.cancelled===false&&t.automatic_retry===false,"actual failed terminal");
  need(t.log_bytes.stdout.seen===1042&&t.log_bytes.stdout.stored===1042&&t.log_bytes.stderr.seen===0&&t.log_bytes.stderr.stored===0&&["stdout","stderr"].every(k=>t.log_synced[k]===true&&t.log_truncated[k]===false&&t.log_errors[k]===null),"actual full output");
  let source=baseline;const edits=[];
  const baselineLine=prefix=>{const rows=baseline.split("\n").filter(s=>s.startsWith(prefix));need(rows.length===1,"baseline line "+prefix);return rows[0];};
  function edit(id,before,after){
    need(before.length>0&&before!==after,"changed edit "+id);const at=source.indexOf(before);need(at>=0&&at===source.lastIndexOf(before),"unique edit "+id);
    source=source.slice(0,at)+after+source.slice(at+before.length);edits.push({id,before,after});
  }
  edit("description",'"""Collect exactly two pinned owned Hilton failure reports; no runtime actions."""','"""Collect exactly two pinned owned Ticket12306 failure reports; no runtime actions."""');
  edit("two_fixed_actual_files",baselineLine("FILES="),"FILES="+JSON.stringify(targetFiles));
  edit("full_original_authority",baselineLine("AUTHORITY_RAW="),"AUTHORITY_RAW="+JSON.stringify({stdout,terminal}));
  edit("full_original_authority_pins",baselineLine("AUTHORITY_PINS="),"AUTHORITY_PINS="+JSON.stringify({stdout:{bytes:1042,sha256:required["ticket-stdout.original.json"].sha256},terminal:{bytes:728,sha256:required["ticket-terminal.original.json"].sha256}}));
  edit("actual_job",baselineLine("JOB="),"JOB='"+job+"'");
  edit("reader_kind","'kind':'pocket4-owned-hilton-install01-fixed-two-results-read01'","'kind':'pocket4-owned-ticket12306-install02-fixed-two-results-read01'");
  edit("actual_stdout_length","t['log_bytes']=={'stdout':{'seen':919,'stored':919},'stderr':{'seen':0,'stored':0}}","t['log_bytes']=={'stdout':{'seen':1042,'stored':1042},'stderr':{'seen':0,'stored':0}}");
  need(edits.length===7,"exact seven binding edits");
  let reverse=source;
  for(const e of edits.slice().reverse()){const at=reverse.indexOf(e.after);need(at>=0&&at===reverse.lastIndexOf(e.after),"unique inverse "+e.id);reverse=reverse.slice(0,at)+e.before+reverse.slice(at+e.after.length);}
  need(reverse===baseline,"exact full inverse");
  const preserved=[
    ["read_exact_file","def read_exact_file(","\nclass ReadDeadline("],
    ["public_error_and_deadline","\nclass ReadDeadline(","\ndef main():"],
    ["summary_gate_all_IO_and_finally","        summaries=[json.loads(line)",null]
  ].map(([name,start,end])=>{
    const select=s=>{const p=s.indexOf(start);need(p>=0&&p===s.lastIndexOf(start),"segment start "+name);const z=end===null?s.length:s.indexOf(end,p+start.length);need(z>=p,"segment end "+name);return s.slice(p,z);};
    const a=select(baseline),b=select(source);need(a===b,"preserved "+name);return {name,...pin(a),unchanged:true};
  });
  need(source.includes("t['state']=='failed' and t['exit_code']==1")&&source.includes("'EXACT_COMPLETE_FAILED_TERMINAL'"),"failed terminal semantics retained");
  need(source.includes("need(len(result['read_events'])==4,'EXACT_FOUR_COMPLETE_READS')"),"four complete reads retained");
  need(source.includes("'installation_outcome_qualified':False,'runtime_qualified':False"),"unqualified outcomes retained");
  need(!source.includes("scope_unknown_until_full_worker"),"incorrect seed metadata not injected");
  q.stdin=source;q.idempotency_key="p4-ticket12306-install02-two-results-read01-"+pin(source).sha256.slice(0,16);
  const request=JSON.stringify(q,null,2)+"\n";
  const a=JSON.parse(originalRequest),b=JSON.parse(request);for(const x of [a,b]){delete x.stdin;delete x.idempotency_key;}
  need(JSON.stringify(a)===JSON.stringify(b),"request envelope unchanged except stdin/key");
  return {source,request,edits,proof:{schema:1,state:"SOURCE_ONLY_NOT_DISPATCHED",prefix:"ticket12306_install02_fixed_results_read01",seed_tree:"b03735ad15e00042506cf5485d55d67509369c42",input_pins:required,source:pin(source),request:pin(request),exact_edit_count:7,edits:edits.map(e=>({id:e.id,before:pin(e.before),after:pin(e.after)})),full_inverse_equals_baseline:true,preserved_segments:preserved,request_envelope_except_stdin_and_key_unchanged:true,failed_terminal_semantics_retained:true,original_authority_strings_preserved:true,files:targetFiles,original_job:job,complete_read_events:4,source_scope_correction:{seed_scope_original_field:"scope_unknown_until_full_worker",seed_scope_original_value:false,seed_scope_is_authority:false,correct_scope_unknown_until_full_worker:true,installation_outcome:"UNKNOWN_UNTIL_WORKER_ORIGINAL_REVIEW",worker_not_yet_read:true,scope_original_preserved:true},read_limits:{per_file_seconds:10,collection_seconds:20,outer_seconds:30,output_bytes:131072},Python_executed:false,Hepta_calls:0,installation_outcome_qualified:false,runtime_qualified:false,original_installation_replayed:false}};
})
