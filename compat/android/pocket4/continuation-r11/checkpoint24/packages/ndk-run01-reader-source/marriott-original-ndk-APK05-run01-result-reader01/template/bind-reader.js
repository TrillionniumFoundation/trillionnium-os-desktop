/* Fixed terminal-result reader binder. No process, network, file or device operation.
 * Run and retirement each require their own actual summary and independent terminal.
 * Raw authority strings are retained verbatim; no future result pin is invented.
 */
function bindRuntimeResultReader(input,U){
  const need=(ok,why)=>{if(!ok)throw Error(why);};
  const equal=(a,b)=>{
    if(a===b)return true;
    if(a===null||b===null||typeof a!==typeof b||typeof a!=='object')return false;
    const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();
    return ak.length===bk.length&&ak.every((k,i)=>k===bk[i]&&equal(a[k],b[k]));
  };
  const pin=raw=>{need(typeof raw==='string','raw UTF8 original required');
    const bytes=U.utf8(raw);return {bytes:bytes.length,sha256:U.sha256(bytes)};};
  const expected={
    template:{bytes:13200,sha256:'73dc0b3546d7eba06c572401c6e5a38b06959ef6a17a211f26b7b90f66fd8e10'},
    nonce:{bytes:989,sha256:'1c625b299ba3067436b13e12a3bdc89ef29296f571ec43452ee214d77a7cd7bf'},
    nonce_terminal:{bytes:729,sha256:'e958d89377f8a3fcc6fdaa13948a721d63fea2b07afde768324eb7a09a33e95b'},
    source_manifest:{bytes:1050,sha256:'7ea8d117de4a6c4cbeceebc4d5d4cf56fd7f075f3cb068b8f3610be4283df582'}
  };
  function terminal(raw,summary,job,allowFailure){
    need(typeof raw==='string'&&pin(raw).bytes>0&&pin(raw).bytes<=32768,'bounded actual terminal');
    const t=JSON.parse(raw),n=pin(summary).bytes;
    need(t.job_id===job&&((t.state==='succeeded'&&t.exit_code===0)||
      (allowFailure&&t.state==='failed'&&t.exit_code===1))&&
      t.output_complete===true&&t.output_durable===true&&t.terminal_publication_confirmed===true&&
      t.timed_out===false&&t.cancelled===false&&t.automatic_retry===false&&
      equal(t.log_bytes,{stdout:{seen:n,stored:n},stderr:{seen:0,stored:0}})&&
      ['stdout','stderr'].every(k=>t.log_synced[k]===true&&
        t.log_truncated[k]===false&&t.log_errors[k]===null),'complete independent terminal required');
    return t;
  }
  need(input&&typeof input==='object'&&['run','retire'].includes(input.phase),
       'only fixed run or retirement result');
  need(equal(pin(input.template),expected.template),'exact reader template');
  need(equal(pin(input.nonce_original),expected.nonce)&&
       equal(pin(input.nonce_terminal),expected.nonce_terminal),'original actual two phase nonces');
  terminal(input.nonce_terminal,input.nonce_original,'1a1b2ff0950-fc05-8068',false);
  const n=JSON.parse(input.nonce_original);
  need(n.schema===1&&n.kind==='pocket4-original-ndk-fixture-run-retire-nonce01'&&
    n.profile==='pocket4-original-ndk-fixture-APK05-run-retire01'&&
    n.package==='com.example.ndk_tests'&&n.target_package==='com.example.ndk_tests'&&
    n.phase==='run_and_independent_retirement'&&n.ok===true&&n.error===null&&
    n.requested_count===2&&n.draw_count===2&&n.redraw_attempted===false&&
    n.fresh_against_exact_pool===true&&n.runtime_authorized===false&&
    equal(n.labels,['run_nonce','retire_nonce'])&&
    equal(Object.keys(n.nonces).sort(),['retire_nonce','run_nonce'])&&
    Object.values(n.nonces).every(v=>typeof v==='string'&&/^[0-9a-f]{32}$/.test(v)&&v!=='0'.repeat(32))&&
    n.nonces.run_nonce!==n.nonces.retire_nonce,'exact assigned phase material');
  need(typeof input.actual_summary==='string'&&typeof input.actual_terminal==='string'&&
    pin(input.actual_summary).bytes>0&&pin(input.actual_summary).bytes<=8192&&
    typeof input.job==='string'&&/^[0-9a-f]+-[0-9a-f]+-[0-9a-f]+$/.test(input.job),
    'actual phase summary and terminal are still unbound');
  const t=terminal(input.actual_terminal,input.actual_summary,input.job,true);
  const s=JSON.parse(input.actual_summary),phase=input.phase;
  const root='/home/alex/work/pocket4-original-ndk-fixture-APK05-'+phase+'-01';
  need(s.schema===1&&s.kind==='pocket4-original-ndk-runtime-worker-summary01'&&s.phase===phase&&
    typeof s.ok==='boolean'&&s.ok===(t.exit_code===0)&&s.automatic_retry===false&&
    typeof s.outcome_unknown==='boolean'&&typeof s.original_NdkTests_runtime_qualified==='boolean'&&
    s.installed_UID===10162&&s.result&&
    equal(Object.keys(s.result).sort(),['bytes','path','result_file_and_parent_FDs_closed','sha256'])&&
    s.result.path===root+'/result.json'&&s.result.result_file_and_parent_FDs_closed===true&&
    Number.isSafeInteger(s.result.bytes)&&s.result.bytes>0&&s.result.bytes<=1048576&&
    typeof s.result.sha256==='string'&&/^[0-9a-f]{64}$/.test(s.result.sha256),
    'exact actual phase summary with a durable fixed result');
  const binding={schema:1,phase,job:input.job,nonce:n.nonces[phase==='run'?'run_nonce':'retire_nonce'],
    result:{bytes:s.result.bytes,sha256:s.result.sha256},
    summary_raw:input.actual_summary,summary_pin:pin(input.actual_summary),
    terminal_raw:input.actual_terminal,terminal_pin:pin(input.actual_terminal)};
  need(input.template.split('BINDING=None').length===2,'one unbound reader slot');
  const replacement='BINDING=json.loads('+JSON.stringify(JSON.stringify(binding))+')';
  const stdin=input.template.replace('BINDING=None',replacement);
  need(stdin.split(replacement).length===2&&stdin.replace(replacement,'BINDING=None')===input.template,
    'binding is the only template difference');
  const request={args:['-n','/usr/bin/python3','-I','-B','-'],cpu_quota_percent:100,
    cwd:'/home/alex/work',executable:'/usr/bin/sudo',host:'pocket4',
    idempotency_key:'p4-ndk-APK05-'+phase+'01-result-read01-'+pin(stdin).sha256.slice(0,16),
    memory_max_bytes:134217728,nice:15,stdin,timeout_seconds:30};
  const requestRaw=JSON.stringify(request,null,2)+'\n';
  return {binding,stdin,requestRaw,proof:{schema:1,phase,job:input.job,template:expected.template,
    source_manifest:expected.source_manifest,result:binding.result,summary:binding.summary_pin,
    terminal:binding.terminal_pin,original_nonce:expected.nonce,nonce_terminal:expected.nonce_terminal,
    stdin:pin(stdin),request:pin(requestRaw),only_template_binding_changed:true,
    original_raw_authority_strings_preserved:true,source_result_bytes_never_reserialized:true,
    producer_ok:s.ok,producer_outcome_unknown:s.outcome_unknown,
    runtime_qualified_by_reader:false,Python_or_device_executed_by_binder:false,
    Root_dispatch_still_required:true}};
}
