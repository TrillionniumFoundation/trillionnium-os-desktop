function bindIhgR2CurrentFiveReader(h,parentRaw,flowRaw,terminal){
 const need=(v,m)=>{if(!v)throw Error(m)},pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 need(h.utf8(parentRaw).length===8752&&h.sha(parentRaw)==="2e007c363973105645024afc957eb7df886304ceb114d34d3068f20d400b11aa","EXACT_ACTUAL_HISTORICAL_IHG_READER");
 need(h.utf8(flowRaw).length===118688&&h.sha(flowRaw)==="4144d110ccc53c15dbfe7b5376c265d41c7ca447478b567711ed7230cca4ae64","EXACT_CURRENT_IHG_UI_SOURCE");
 const q=JSON.parse(parentRaw),uq=JSON.parse(flowRaw),p=JSON.parse(uq.stdin);
 const root="/home/alex/work/pocket4-ihg-r2-public-search-destination-entry-01";
 need(h.sha(p.files["SOURCE_PINS.json"])==="996ad8e7072afdf3a4288eebb8488d5dcfcdd073f533b0c535d127b3e6c0424d"&&p.nonce==="b2cd08fcaad1f2faaed5de2ff5df01af","CURRENT_IHG_PACKET_BINDING");
 need(terminal.job==="1a1b00b2311-fc05-6daf"&&terminal.ok===true,"ACTUAL_CURRENT_IHG_TERMINAL");
 for(const name of ["coordinator","stage"]){const v=terminal[name];need(v.path===root+"/"+(name==="coordinator"?"result.json":"stage-result.json")&&Number.isInteger(v.bytes)&&v.bytes>0&&v.bytes<=262144&&/^[0-9a-f]{64}$/.test(v.sha256),"EXACT_ACTUAL_TERMINAL_PIN:"+name);}
 let s=q.stdin;const edits=[];const edit=(old,next,count=1)=>{need(s.split(old).length-1===count,"READER_ANCHOR:"+old.slice(0,80));s=s.split(old).join(next);edits.push({old,next,count});};
 for(const[n,value]of Object.entries({ROOT:"Path("+JSON.stringify(root)+")",FLOW:"Path("+JSON.stringify("/home/alex/work/pocket4-ihg-owned-qa-r2-flow-"+p.nonce)+")",NONCE:JSON.stringify(p.nonce),SOURCE_SHA:JSON.stringify(h.sha(p.files["SOURCE_PINS.json"])),HELPER_UID:"10153"})){
  const m=s.match(new RegExp("^"+n+"=.*$","m"));need(m,"CONST:"+n);edit(m[0],n+"="+value);
 }
 edit("sizes={'coordinator.json':7398,'stage.json':1824}","sizes={'coordinator.json':"+terminal.coordinator.bytes+",'stage.json':"+terminal.stage.bytes+"}");
 edit("org.droidloom.qa.ihg.r1","org.droidloom.qa.ihg.r2",2);
 edit("fixed-IHG-public-search-destination01-terminal-parents-and-three-parent-bound-phase-results","fixed-current-IHG-R2-search-destination01-terminal-parents-and-three-parent-bound-phase-results");
 // The supplied audited parent has a 262144-byte read limit already. Narrow the
 // coordinator only to its actual 66601 bytes; do not pretend an absent 65536 gate.
 edit("        maximum=262144","        maximum="+terminal.coordinator.bytes+" if path==FILES['coordinator.json'] else 262144");
 let inverse=s;for(const e of [...edits].reverse()){need(inverse.split(e.next).length-1===e.count,"READER_INVERSE_COUNT");inverse=inverse.split(e.next).join(e.old);}need(inverse===q.stdin,"FULL_READER_INVERSE");
 need(h.utf8(s).length<=16384,"ORIGINAL_SOURCE_BOUND");
 const wrapper="import sys,hashlib;raw=sys.stdin.buffer.read(16385);assert 0<len(raw)<=16384 and hashlib.sha256(raw).hexdigest()=='"+h.sha(s)+"';scope={'__name__':'fixed_owned_summary_reader','__file__':'<verified-fixed-summary-reader>'};exec(compile(raw,'read_summary.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once', '--coordinator-sha256', '"+terminal.coordinator.sha256+"', '--stage-sha256', '"+terminal.stage.sha256+"']))";
 const request={...q,args:["-n","/usr/bin/python3","-I","-c",wrapper],stdin:s,idempotency_key:"pocket4-ihg-r2-current-search-destination01-five-safe-readonly01-20261106"};
 return {source:s,request,edits,proof:{parent_request:pin(parentRaw),current_UI_request:pin(flowRaw),terminal,full_inverse:true,
 original_parent_read_limit:262144,current_coordinator_read_limit:terminal.coordinator.bytes,other_file_read_limits_unchanged:262144,
 original_read_deadline_seconds:8,original_total_read_bound:2097152,original_bundle_bound:3145728,
 exact_five_path_allowlist:true,phase_pins_only_from_externally_pinned_parent:true,
 raw_UI_privacy_guard_unchanged:true,original_unknown_and_success_fields_preserved:true,
 no_Main_or_Android_actions:true,cleanup_or_UI_slot_release_not_claimed:true,local_Python_compile_or_controls:false}};
}
