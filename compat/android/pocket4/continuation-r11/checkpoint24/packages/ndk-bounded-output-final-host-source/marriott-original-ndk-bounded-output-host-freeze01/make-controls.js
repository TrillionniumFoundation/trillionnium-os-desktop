/* Pure V8 reproduction: every source must be exact UTF8, base64 receives bytes. */
function makeBoundedOutputControls(files,template,U,B){
  const need=(v,m)=>{if(!v)throw new Error(m);};
  const pin=s=>{const b=U.utf8(s);return {bytes:b.length,sha256:U.sha256(b)};};
  const names=['fixture_context.py','fixture_transport.py','fixture_contract.py',
               'recorder.py','check_bounded_output.py'];
  need(files&&typeof files==='object'&&Object.keys(files).sort().join('\n')===
       [...names].sort().join('\n'),'exact five host-only source members');
  const members=names.map(path=>{
    const raw=files[path];need(typeof raw==='string','raw source '+path);
    const bytes=U.utf8(raw),body_b64=B.enc(bytes),decoded=B.dec(body_b64);
    need(decoded.length===bytes.length&&decoded.every((v,i)=>v===bytes[i]),
         'complete UTF8/base64 roundtrip '+path);
    need(bytes.length>0&&bytes.length<=131072,'member bound '+path);
    return {path,...pin(raw),body_b64};
  });
  const packetRaw=JSON.stringify({schema:1,kind:'p4-ndk-bounded-output-host-controls01',members},null,2)+'\n';
  need(pin(packetRaw).bytes<=524288,'packet bound');
  need(template.split('PACKET_B64=None').length===2&&template.split('PACKET_PIN=None').length===2,
       'exact two unbound envelope slots');
  const encoded=B.enc(U.utf8(packetRaw)),d=B.dec(encoded),p=U.utf8(packetRaw);
  need(d.length===p.length&&d.every((v,i)=>v===p[i]),'full packet UTF8 roundtrip');
  const b64Slot='PACKET_B64='+JSON.stringify(encoded);
  const pinSlot='PACKET_PIN=json.loads('+JSON.stringify(JSON.stringify(pin(packetRaw)))+')';
  const stdin=template.replace('PACKET_B64=None',b64Slot).replace('PACKET_PIN=None',pinSlot);
  need(stdin.replace(b64Slot,'PACKET_B64=None').replace(pinSlot,'PACKET_PIN=None')===template,
       'only two envelope substitutions');
  const request={args:['-I','-B','-'],cpu_quota_percent:100,cwd:'/home/alex/work',
    executable:'/usr/bin/python3',host:'pocket4',
    idempotency_key:'p4-ndk-output-host-controls01-'+pin(stdin).sha256.slice(0,16),
    memory_max_bytes:268435456,nice:15,stdin,timeout_seconds:60};
  const requestRaw=JSON.stringify(request,null,2)+'\n';
  return {packetRaw,stdin,requestRaw,proof:{
    schema:1,source_members:Object.fromEntries(members.map(x=>[x.path,{bytes:x.bytes,sha256:x.sha256}])),
    template:pin(template),packet:pin(packetRaw),stdin:pin(stdin),request:pin(requestRaw),
    exact_real_host_children:5,exact_no_child_order_controls:2,
    whole_packet_base64_roundtrip:true,member_byte_roundtrips:true,
    only_template_slots_changed:true,
    synthetic_passed_FDs_do_not_authorize_Main_namespaces:true,
    no_new_runtime_request:true,Python_executed_during_reproduction:false}};
}
