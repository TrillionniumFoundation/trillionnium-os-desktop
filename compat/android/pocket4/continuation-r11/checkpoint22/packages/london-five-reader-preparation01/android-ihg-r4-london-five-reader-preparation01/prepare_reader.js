function bindLondon170SafeFiveReader(h, oldRequestRaw, uiRequestRaw, parents) {
  const need=(v,m)=>{if(!v)throw Error(m);};
  const pin=raw=>({bytes:h.utf8(raw).length,sha256:h.sha(raw)});
  const same=(a,b)=>a.bytes===b.bytes&&a.sha256===b.sha256;
  need(same(pin(oldRequestRaw),{bytes:8816,sha256:"bf29c7e9585c6e60e8e944299d1beb2c78c454aa8499dcfb54537383e6274ff6"}),"EXACT_ACTUAL_PRIOR_READER");
  need(same(pin(uiRequestRaw),{bytes:138849,sha256:"fdd91d10c04b0af40d48acbc83474e115aa48e965f1a129f570cc4c7de8b866a"}),"EXACT_REVIEWED_LONDON_UI_REQUEST");
  const old=JSON.parse(oldRequestRaw),q=JSON.parse(uiRequestRaw),packet=JSON.parse(q.stdin);
  const root="/home/alex/work/pocket4-ihg-r4-public-london-input-01";
  const nonce="ec4f2977574102b1e5869d2494e8416b";
  const flow="/home/alex/work/pocket4-ihg-owned-qa-r4-flow-"+nonce;
  need(packet.nonce===nonce&&packet.files&&q.idempotency_key==="pocket4-ihg-r4-current-search-destination-london01-20261106","FIXED_CURRENT_FLOW");
  const sourceSHA=h.sha(packet.files["SOURCE_PINS.json"]);
  need(sourceSHA==="24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f","EXACT_UI_RUNTIME_SOURCE");
  need(parents&&Object.keys(parents).sort().join(",")==="coordinator,stage","TWO_ACTUAL_TERMINAL_PINS_REQUIRED");
  for(const [name,p]of Object.entries(parents)){
    need(p&&Object.keys(p).sort().join(",")==="bytes,path,sha256"&&Number.isSafeInteger(p.bytes)&&p.bytes>0&&p.bytes<=262144&&
      typeof p.sha256==="string"&&/^[0-9a-f]{64}$/.test(p.sha256)&&
      p.path===root+(name==="coordinator"?"/result.json":"/stage-result.json"),"FIXED_BOUNDED_ACTUAL_PARENT:"+name);
  }
  let source=old.stdin;
  const edits=[];
  function one(before,after){
    const i=source.indexOf(before);need(i>=0&&source.indexOf(before,i+before.length)<0,"EXACT_SOURCE_EDIT:"+before);
    source=source.slice(0,i)+after+source.slice(i+before.length);edits.push({offset:i,before,after});
  }
  one('ROOT=Path("/home/alex/work/pocket4-ihg-r2-public-search-destination-entry-01")','ROOT=Path('+JSON.stringify(root)+')');
  one('FLOW=Path("/home/alex/work/pocket4-ihg-owned-qa-r2-flow-b2cd08fcaad1f2faaed5de2ff5df01af")','FLOW=Path('+JSON.stringify(flow)+')');
  one('NONCE="b2cd08fcaad1f2faaed5de2ff5df01af"','NONCE='+JSON.stringify(nonce));
  one('SOURCE_SHA="996ad8e7072afdf3a4288eebb8488d5dcfcdd073f533b0c535d127b3e6c0424d"','SOURCE_SHA='+JSON.stringify(sourceSHA));
  one('HELPER_UID=10153','HELPER_UID=10158');
  one("maximum=66601 if path==FILES['coordinator.json'] else 262144","maximum="+parents.coordinator.bytes+" if path==FILES['coordinator.json'] else 262144");
  one("sizes={'coordinator.json':66601,'stage.json':2624}","sizes={'coordinator.json':"+parents.coordinator.bytes+",'stage.json':"+parents.stage.bytes+"}");
  one("coordinator.get('helper_package')=='org.droidloom.qa.ihg.r2'","coordinator.get('helper_package')=='org.droidloom.qa.ihg.r4'");
  one("value.get('phase')==phase and value.get('helper_package')=='org.droidloom.qa.ihg.r2'","value.get('phase')==phase and value.get('helper_package')=='org.droidloom.qa.ihg.r4'");
  one("fixed-current-IHG-R2-search-destination01-terminal-parents-and-three-parent-bound-phase-results","fixed-current-IHG-R4-London01-terminal-parents-and-three-parent-bound-phase-results");
  let inverse=source;
  for(const e of [...edits].reverse()){
    need(inverse.slice(e.offset,e.offset+e.after.length)===e.after,"INVERSE_EDIT");
    inverse=inverse.slice(0,e.offset)+e.before+inverse.slice(e.offset+e.after.length);
  }
  need(inverse===old.stdin,"COMPLETE_ORIGINAL_READER_INVERSE");
  need(h.utf8(source).length<=16384,"ORIGINAL_READER_SOURCE_BOUND");
  const wrapper="import sys,hashlib;raw=sys.stdin.buffer.read(16385);assert 0<len(raw)<=16384 and hashlib.sha256(raw).hexdigest()=="+
    JSON.stringify(h.sha(source))+";scope={'__name__':'fixed_owned_summary_reader','__file__':'<verified-fixed-summary-reader>'};exec(compile(raw,'read_summary.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once','--coordinator-sha256',"+
    JSON.stringify(parents.coordinator.sha256)+",'--stage-sha256',"+JSON.stringify(parents.stage.sha256)+"]))";
  need(old.executable==="/usr/bin/sudo"&&old.args.slice(0,4).join("\0")==="-n\0/usr/bin/python3\0-I\0-c"&&
    old.timeout_seconds===30&&old.memory_max_bytes===134217728,"ORIGINAL_READER_ENVELOPE");
  const request={...old,args:["-n","/usr/bin/python3","-I","-B","-c",wrapper],stdin:source,
    idempotency_key:"pocket4-ihg-r4-current-london01-five-safe-readonly01-20261106"};
  return {source,source_pin:pin(source),request,request_raw:JSON.stringify(request,null,2)+"\n",edits,
    proof:{complete_source_inverse:true,external_actual_parents:parents,actual_parent_sizes_only:true,
    original_child262144_and_total2MiB_bounds:true,all_three_retained_phases_required:true,
    original_private_UI_field_exclusion_unchanged:true,original_failure_unknown_values_unmodified:true,
    explicit_no_bytecode:true,device_or_UI_actions:0,dispatched:false}};
}