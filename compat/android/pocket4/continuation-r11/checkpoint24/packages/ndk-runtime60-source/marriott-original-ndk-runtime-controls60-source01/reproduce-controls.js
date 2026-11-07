function reproduceRuntimeControls(files, baselineRequestRaw, U, B) {
  const need=(ok,message)=>{if(!ok)throw Error(message);};
  const pin=s=>({bytes:U.utf8(s).length,sha256:U.sha256(U.utf8(s))});
  const member=s=>({body:s,...pin(s)});
  const sourceNames=['current_discovery.py','fixture_context.py','fixture_contract.py',
    'fixture_phases.py','fixture_transport.py','phase_lease.py','phase_worker.py'].sort();
  const controlNames=['check_fixture.py','check_external_manifest.py','check_phase_lease.py','check_phase_wiring.py'].sort();
  const referenceNames=['static-build.original.json','install-result.original.json',
    'install-summary.original.json','install-terminal.original.json'];
  const sources=Object.fromEntries(sourceNames.map(n=>[n,files['source/'+n]]));
  need(Object.values(sources).every(s=>typeof s==='string'),'source missing');
  const manifest=JSON.stringify({schema:'pocket4-original-ndk-fixture-source-v1',
    files:Object.fromEntries(sourceNames.map(n=>[n,pin(sources[n])]))},null,2)+'\n';
  need(manifest===files['source/SOURCE_PINS.json'],'manifest differs');
  const packet=JSON.stringify({schema:1,kind:'pocket4-original-ndk-runtime-entry-controls01',
    sources:Object.fromEntries(sourceNames.map(n=>[n,member(sources[n])])),
    manifest:member(manifest),
    controls:Object.fromEntries(controlNames.map(n=>[n,member(files['controls/'+n])])),
    references:Object.fromEntries(referenceNames.map(n=>[n,member(files['references/'+n])]))},null,2)+'\n';
  need(packet===files['requests/controls-packet.json'],'packet differs');
  const template=files['requests/controls-runner-template.py'];
  for(const slot of ['__PACKET_SHA256__','__PACKET_BYTES__','__PACKET_B64__'])
    need(template.split(slot).length===2,'slot uniqueness');
  const pp=pin(packet),base64=B.enc(U.utf8(packet));
  need(U.sha256(B.dec(base64))===pp.sha256 && B.dec(base64).length===pp.bytes,'base64 UTF8 roundtrip');
  const stdin=template.replace('__PACKET_SHA256__',pp.sha256)
    .replace('__PACKET_BYTES__',String(pp.bytes)).replace('__PACKET_B64__',base64);
  need(stdin===files['requests/controls-stdin.py'],'stdin differs');
  const baseline=JSON.parse(baselineRequestRaw);
  const request=JSON.stringify({...baseline,stdin,idempotency_key:
    'p4-ndk-fixture-runtime-entry-controls01-'+pin(stdin).sha256.slice(0,16)},null,2)+'\n';
  need(request===files['requests/controls-request.json'],'request differs');
  const normalize=s=>s.replace(/^PACKET_SHA256 = .*$/m,"PACKET_SHA256 = '__PACKET_SHA256__'")
    .replace(/^PACKET_BYTES = .*$/m,"PACKET_BYTES = __PACKET_BYTES__")
    .replace(/^PACKET_B64 = .*$/m,"PACKET_B64 = '__PACKET_B64__'");
  let inverse=template;
  for(const e of JSON.parse(files['review/controls-runner-substitutions.json']).reverse()){
    need(inverse.split(e.after).length-1===e.count,'inverse count');
    inverse=inverse.split(e.after).join(e.before);
  }
  need(inverse===normalize(baseline.stdin),'normalized original complete runner differs');
  return {manifest:pin(manifest),packet:pp,stdin:pin(stdin),request:pin(request),
    complete_runner_inverse:true,strict_UTF8_base64_roundtrip:true,Python_executed:false};
}
