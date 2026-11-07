/* Reproduce only the actual60-bound run01. Pure JavaScript; never dispatches. */
function reproduceBoundRun01(input,U,B){
 const need=(x,c)=>{if(!x)throw Error(c);};
 const pin=s=>{const b=U.utf8(s);return {bytes:b.length,sha256:U.sha256(b)};};
 const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 const E={
   binder:{bytes:22965,sha256:'7b8aebf6797b2148237f5b725135c4df3ce89a1026825896474dac2295e4bdc9'},
   wrapper:{bytes:4961,sha256:'09408c678a9a9909ceecf4d09b9a5b256a1ec75e581636751d9eb0d5441db649'},
   actual:{bytes:12881,sha256:'7287ba952efe520d2e4a0d545cf8dbfd6a6e87944ce1a8c1c730946169e6d9b1'},
   terminal:{bytes:733,sha256:'f7ccd18da8171ac768cecb382efa11294256559ac5d1fe3a09b56a601490c54b'},
   envelope:{bytes:243509,sha256:'5bd32e90fbe2a59833bf522aaceb52424aa64c58cd0ba53c2265f792a56e08a8'},
   stdin:{bytes:329707,sha256:'4ea7dac8dc6ddfd82718e9107684171b65aa778b31fb7f25816b736a53aa407c'},
   request:{bytes:330181,sha256:'2c23de3e5f0b4c7055d457926c5746741b7f42648031dd13610f0ba8ddf6a9fd'}
 };
 need(equal(pin(input.binder),E.binder)&&equal(pin(input.wrapper),E.wrapper)&&
   equal(pin(input.actual),E.actual)&&equal(pin(input.terminal),E.terminal),'frozen complete inputs');
 const bound=Function(input.binder+'\nreturn bindRuntimePhase;')()({
   phase:'run',files:input.files,wrapper_template:input.wrapper,
   actual_controls_stdout:input.actual,actual_controls_terminal:input.terminal,
   controls_job:'1a1b3127850-fc05-8092',prior_run:null},U,B);
 const fs=input.files,member=body=>({body,...pin(body)});
 const names=Object.keys(JSON.parse(fs['source/SOURCE_PINS.json']).files).sort();
 need(names.length===7,'seven production sources');
 const refs=Object.fromEntries(Object.entries(fs).filter(([path])=>path.startsWith('references/'))
   .map(([path,raw])=>[path.slice('references/'.length),raw]));
 refs['entry-controls.original.json']=input.actual;
 refs['entry-controls-terminal.original.json']=input.terminal;
 need(Object.keys(refs).length===13,'thirteen complete original references');
 const binding={schema:1,kind:'pocket4-original-ndk-runtime-binding-v1',phase:'run',
   root:'/home/alex/work/pocket4-original-ndk-fixture-APK05-run-01',
   source_manifest:pin(fs['source/SOURCE_PINS.json']),
   entry_controls:pin(input.actual),entry_controls_terminal:pin(input.terminal),
   entry_controls_job:'1a1b3127850-fc05-8092',entry_controls_stdout_bytes:12881,
   nonce_material:pin(refs['phase-nonce.original.json']),
   nonce_terminal:pin(refs['phase-nonce-terminal.original.json']),
   nonce_job:'1a1b2ff0950-fc05-8068',nonce_stdout_bytes:989,prior_run:null};
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
   __PACKET_B64__:encoded,__PHASE__:'run',
   __SOURCE_ROOT__:'/home/alex/work/pocket4-original-ndk-fixture-APK05-run-01/source'})){
   need(stdin.split(slot).length===2,'single wrapper slot '+slot);
   stdin=stdin.replace(slot,value);
 }
 need(stdin===bound.stdin&&equal(pin(stdin),E.stdin),'independent full stdin');
 const request={args:['-n','/usr/bin/python3','-I','-B','-'],cpu_quota_percent:100,
   cwd:'/home/alex/work',executable:'/usr/bin/sudo',host:'pocket4',
   idempotency_key:'p4-ndk-fixture-APK05-run01-'+pin(stdin).sha256.slice(0,16),
   memory_max_bytes:536870912,nice:15,stdin,timeout_seconds:240};
 const requestRaw=JSON.stringify(request,null,2)+'\n';
 need(requestRaw===bound.requestRaw&&equal(pin(requestRaw),E.request),'independent complete request');
 if(input.bound_request!==undefined)need(requestRaw===input.bound_request,'published bound request exact');
 return {schema:1,all_fixed_inputs_verified:true,source_count:7,reference_count:13,
   independently_rebuilt_envelope:pin(envelope),independently_rebuilt_stdin:pin(stdin),
   independently_rebuilt_request:pin(requestRaw),whole_UTF8_base64_roundtrip:true,
   production_sources_and_raw_references_unchanged:true,
   root:binding.root,phase:'run',prior_run:null,
   Python_or_device_executed:false,retirement_request_generated:false};
}
