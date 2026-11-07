function bindR9FiveReader(h,baseRequestRaw,flowRequestRaw,terminal){
 const need=(v,c)=>{if(!v)throw Error(c)};
 const pin=s=>({bytes:h.utf8(s).length,sha256:h.sha(s)});
 need(h.utf8(baseRequestRaw).length===12501&&h.sha(baseRequestRaw)==='643d08a34b7a8b6be88daea5114b77cb98a69f2c067f4088192bfc9d0a6b6b75','EXACT_AUDITED_READER_PARENT');
 need(h.utf8(flowRequestRaw).length===133937&&h.sha(flowRequestRaw)==='338b3a87abff1cd01d3d4c6b93607f7f689df8b526aee563609245ac0b2a7586','EXACT_FROZEN_R9_FLOW');
 const q=JSON.parse(baseRequestRaw),flowQ=JSON.parse(flowRequestRaw),packet=JSON.parse(flowQ.stdin);
 need(packet.source_manifest_sha256==='f8a3bc391e241dca776e7c919b46115c9c1b23228af261af19875b77cfc160bb'&&packet.nonce==='fc02c98cd9a6fbf64ad55cc2c180d0df','EXACT_R9_FLOW_SOURCE');
 const root='/home/alex/work/pocket4-bilibili-r9-pause-resume-01';
 need(terminal&&typeof terminal.ok==='boolean'&&Object.keys(terminal).sort().join(',')==='coordinator,job_id,ok,stage'&&typeof terminal.job_id==='string'&&/^(?:job)?[0-9a-f]+(?:-[0-9a-f]+)+$/.test(terminal.job_id),'ACTUAL_TERMINAL_REQUIRED');
 for(const name of ['coordinator','stage']){const r=terminal[name];need(r&&Object.keys(r).sort().join(',')==='bytes,path,sha256'&&r.path===root+'/'+(name==='coordinator'?'result.json':'stage-result.json')&&Number.isInteger(r.bytes)&&r.bytes>0&&r.bytes<=262144&&typeof r.sha256==='string'&&/^[0-9a-f]{64}$/.test(r.sha256),'EXACT_ACTUAL_PARENT:'+name);}
 let source=q.stdin;const edits=[];
 function edit(old,next,count=1){need(source.split(old).length-1===count,'EXACT_READER_ANCHOR:'+old.slice(0,60));source=source.split(old).join(next);edits.push({old,next,count});}
 const constants={ROOT:"Path('"+root+"')",FLOW:"Path('/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-"+packet.nonce+"')",NONCE:"'"+packet.nonce+"'",SOURCE_SHA:"'"+packet.source_manifest_sha256+"'",HELPER_UID:"10152",COORDINATOR_BYTES:String(terminal.coordinator.bytes),STAGE_BYTES:String(terminal.stage.bytes),COORDINATOR_SHA:"'"+terminal.coordinator.sha256+"'",STAGE_SHA:"'"+terminal.stage.sha256+"'",PARENT_EXPECTED_OK:terminal.ok?'True':'False'};
 for(const[name,value]of Object.entries(constants)){const m=source.match(new RegExp('^'+name+'=.*$','m'));need(m,'READER_CONSTANT:'+name);edit(m[0],name+'='+value);}
 edit('org.droidloom.qa.bili.r7','org.droidloom.qa.bili.r9',3);
 edit('fixed-r7-player-button01-actual-navigation-and-retirement-only','fixed-r9-player-button01-actual-navigation-and-retirement-only');
 const oldTransport="    compressed=gzip.compress(raw,mtime=0)\n    print(json.dumps({'schema':1,'encoding':'gzip-base64','private_UI_data':False,\n        'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),\n        'compressed_bytes':len(compressed),'compressed_sha256':sha(compressed),\n        'data':base64.b64encode(compressed).decode('ascii')},sort_keys=True),flush=True)";
 const nextTransport="    print(json.dumps({'schema':1,'encoding':'base64','private_UI_data':False,\n        'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),\n        'data':base64.b64encode(raw).decode('ascii')},sort_keys=True),flush=True)";
 edit(oldTransport,nextTransport);
 need(h.utf8(source).length<=16384,'UNCHANGED_READER_SOURCE_BOUND');
 let inverse=source;for(const e of [...edits].reverse())inverse=inverse.split(e.next).join(e.old);
 need(inverse===q.stdin,'FULL_READER_INVERSE');
 const wrapper="import sys,hashlib;raw=sys.stdin.buffer.read(16385);assert 0<len(raw)<=16384 and hashlib.sha256(raw).hexdigest()=='"+h.sha(source)+"';scope={'__name__':'fixed_owned_summary_reader','__file__':'<verified-fixed-summary-reader>'};exec(compile(raw,'read_summary.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once', '--coordinator-sha256', '"+terminal.coordinator.sha256+"', '--stage-sha256', '"+terminal.stage.sha256+"']))";
 return {source,request:{...q,stdin:source,args:['-n','/usr/bin/python3','-I','-c',wrapper],idempotency_key:'pocket4-bilibili-r9-player-button01-five-safe-readonly01-20261106'},proof:{parent:pin(baseRequestRaw),flow:pin(flowRequestRaw),terminal,full_inverse:true,Reader_and_all_privacy_and_parent_scope_guards_unchanged:true,original_max_file_and_total_deadline_bounds_unchanged:true,output_transport_only:'uncompressed base64 carrier',no_Android_commands:true,cleanup_release_asserted:false},edits};
}
