/* Reproduce the independently bound retirement of actual FAILED run01. No dispatch. */
function reproduceBoundRetire01(input,U,B){
 const need=(x,c)=>{if(!x)throw Error(c);};
 const pin=s=>{const b=U.utf8(s);return {bytes:b.length,sha256:U.sha256(b)};};
 const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 const E={
   binder:{bytes:22965,sha256:'7b8aebf6797b2148237f5b725135c4df3ce89a1026825896474dac2295e4bdc9'},
   wrapper:{bytes:4961,sha256:'09408c678a9a9909ceecf4d09b9a5b256a1ec75e581636751d9eb0d5441db649'},
   actual:{bytes:12881,sha256:'7287ba952efe520d2e4a0d545cf8dbfd6a6e87944ce1a8c1c730946169e6d9b1'},
   terminal:{bytes:733,sha256:'f7ccd18da8171ac768cecb382efa11294256559ac5d1fe3a09b56a601490c54b'},
   run:{bytes:10868,sha256:'6164de7cd4d97420ce2058846e413b93e0770fd16d9fdcc3b7b21759ef504c98'},
   run_summary:{bytes:615,sha256:'500273f04924c42fc47a6cd7ce05c156b9ecfc878fdc73d63f31f44fee5be1e1'},
   run_terminal:{bytes:726,sha256:'405a1a61ef1aad65241dc797be40a11a89e85b562358efbc19e5e29f93fd7b52'},
   envelope:{bytes:257743,sha256:'64471eb73df05a631f97080808717abdded8741ccbd822ace395e973bf08945f'},
   stdin:{bytes:348693,sha256:'ab0551a7d89ff29ea5d5ab4deb06d97932451c323f6dacfd4d5d84a0af6b192b'},
   request:{bytes:349170,sha256:'f8a5c03ba762282ff609c70ed76dae19e5ae2a2a97fcaea872ca5ccfa527fc0f'}
 };
 for(const name of ['binder','wrapper','actual','terminal','run','run_summary','run_terminal'])
   need(equal(pin(input[name]),E[name]),'complete fixed input '+name);
 const bound=Function(input.binder+'\nreturn bindRuntimePhase;')()({
   phase:'retire',files:input.files,wrapper_template:input.wrapper,
   actual_controls_stdout:input.actual,actual_controls_terminal:input.terminal,
   controls_job:'1a1b3127850-fc05-8092',prior_run:{job:'1a1b31bedf5-fc05-80a3',
     result_raw:input.run,summary_raw:input.run_summary,terminal_raw:input.run_terminal}},U,B);
 const fs=input.files,member=body=>({body,...pin(body)});
 const names=Object.keys(JSON.parse(fs['source/SOURCE_PINS.json']).files).sort();
 need(names.length===7,'seven original production sources');
 const refs=Object.fromEntries(Object.entries(fs).filter(([path])=>path.startsWith('references/'))
   .map(([path,raw])=>[path.slice('references/'.length),raw]));
 refs['entry-controls.original.json']=input.actual;
 refs['entry-controls-terminal.original.json']=input.terminal;
 refs['run-result.original.json']=input.run;
 refs['run-summary.original.json']=input.run_summary;
 refs['run-terminal.original.json']=input.run_terminal;
 need(Object.keys(refs).length===16,'sixteen complete original references');
 const binding={schema:1,kind:'pocket4-original-ndk-runtime-binding-v1',phase:'retire',
   root:'/home/alex/work/pocket4-original-ndk-fixture-APK05-retire-01',
   source_manifest:pin(fs['source/SOURCE_PINS.json']),
   entry_controls:pin(input.actual),entry_controls_terminal:pin(input.terminal),
   entry_controls_job:'1a1b3127850-fc05-8092',entry_controls_stdout_bytes:12881,
   nonce_material:pin(refs['phase-nonce.original.json']),
   nonce_terminal:pin(refs['phase-nonce-terminal.original.json']),
   nonce_job:'1a1b2ff0950-fc05-8068',nonce_stdout_bytes:989,
   prior_run:{result:E.run,summary:E.run_summary,terminal:E.run_terminal,
     job:'1a1b31bedf5-fc05-80a3',stdout_bytes:615,source_manifest:pin(fs['source/SOURCE_PINS.json'])}};
 const packet={schema:1,sources:Object.fromEntries(names.map(n=>[n,member(fs['source/'+n])])),
   manifest:member(fs['source/SOURCE_PINS.json']),
   references:Object.fromEntries(Object.keys(refs).sort().map(n=>[n,member(refs[n])]))};
 const envelope=JSON.stringify({binding,packet},null,2)+'\n';
 need(envelope===bound.envelopeRaw&&equal(pin(envelope),E.envelope),'independent full envelope');
 const encoded=B.enc(U.utf8(envelope)),decoded=B.dec(encoded),bytes=U.utf8(envelope);
 need(decoded.length===bytes.length&&decoded.every((b,i)=>b===bytes[i]),'UTF8 exact base64 bytes');
 let stdin=input.wrapper;
 for(const [slot,value]of Object.entries({
   __PACKET_BYTES__:String(bytes.length),__PACKET_SHA256__:pin(envelope).sha256,
   __PACKET_B64__:encoded,__PHASE__:'retire',
   __SOURCE_ROOT__:'/home/alex/work/pocket4-original-ndk-fixture-APK05-retire-01/source'})){
   need(stdin.split(slot).length===2,'single wrapper slot '+slot);
   stdin=stdin.replace(slot,value);
 }
 need(stdin===bound.stdin&&equal(pin(stdin),E.stdin),'independent full stdin');
 const request={args:['-n','/usr/bin/python3','-I','-B','-'],cpu_quota_percent:100,
   cwd:'/home/alex/work',executable:'/usr/bin/sudo',host:'pocket4',
   idempotency_key:'p4-ndk-fixture-APK05-retire01-'+pin(stdin).sha256.slice(0,16),
   memory_max_bytes:536870912,nice:15,stdin,timeout_seconds:240};
 const requestRaw=JSON.stringify(request,null,2)+'\n';
 need(requestRaw===bound.requestRaw&&equal(pin(requestRaw),E.request),'independent complete request');
 if(input.bound_request!==undefined)need(requestRaw===input.bound_request,'published bound request exact');
 const failed=JSON.parse(input.run);
 need(failed.ok===false&&failed.outcome_unknown===true&&failed.instrumentation_attempted===true&&
   failed.instrumentation_verified===false&&failed.native_twelve_tests_qualified===false&&
   failed.original_NdkTests_runtime_qualified===false,'failed prior run not reclassified');
 return {schema:1,all_fixed_inputs_verified:true,source_count:7,reference_count:16,
   independently_rebuilt_envelope:pin(envelope),independently_rebuilt_stdin:pin(stdin),
   independently_rebuilt_request:pin(requestRaw),whole_UTF8_base64_roundtrip:true,
   production_sources_and_raw_references_unchanged:true,
   root:binding.root,phase:'retire',prior_run:binding.prior_run,
   prior_run_FAILED_UNKNOWN_preserved:true,native_twelve_tests_may_not_be_upgraded:true,
   Python_or_device_executed:false,new_run_request_generated:false};
}
