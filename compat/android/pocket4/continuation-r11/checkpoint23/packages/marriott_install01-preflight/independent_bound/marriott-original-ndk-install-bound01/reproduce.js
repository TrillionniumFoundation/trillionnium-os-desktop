// Pure V8 reproduction of the one actual-bound install candidate.
// Supply rawByName for base-packet.json plus every bound-file key below.
// This code neither submits the request nor executes Python/Main/Android.
const REQUIRED = {
  "base-packet.json": {
    "bytes": 232975,
    "sha256": "05d80d6473fd35bc172aab79a0eaa4c96afe038bc8187c7baf2399637529dcb7",
    "git_blob_sha1": "ceea1acc0a45f2fce1493b6a839afaddfbf6461e"
  },
  "inputs/bind_install.js": {
    "bytes": 15280,
    "sha256": "f3388feef031c5aa2a8eb7fa542d2228367be478d8a47a2103405ddabf69bd9e",
    "git_blob_sha1": "990abbbbab55bb56de3d5c4fbbf6b828762052f4"
  },
  "inputs/wrapper-template.py": {
    "bytes": 4710,
    "sha256": "2edb2be25dbe6db762634c2b926022348a6940210f264d8fda8ed67dd06a65c7",
    "git_blob_sha1": "03a74cff654f959e7f9169fea462290f186418f3"
  },
  "actual/entry-controls.original.json": {
    "bytes": 9826,
    "sha256": "2bf1df7891dfd1617874d9885c3e562afa46be9924896dcca08ba54941b6b735",
    "git_blob_sha1": "0394073c517b30b16d09855057a3b1b608a441ee"
  },
  "actual/entry-controls-terminal.original.json": {
    "bytes": 731,
    "sha256": "14183ad72c510bc49d143eff5ffabe13b480df5e3aaea2a5c9d6e754e49437f0",
    "git_blob_sha1": "9ec5cd281164328fcd90a7fd64b6e0e676c05784"
  },
  "binding.json": {
    "bytes": 624,
    "sha256": "999c4f7975ca481f555c253e1bc9d643afd38e5e2eec8535bd3e4fea31fab924",
    "git_blob_sha1": "343b89e1ebe91744cd4287f173a76edd66a6e798"
  },
  "packet.json": {
    "bytes": 244815,
    "sha256": "9b32e984e805289cbf85fdca8c97215c9b1f5b79efbd2895ff75011822b2f383",
    "git_blob_sha1": "cc61aa1ed51398ed57613e7916d7a5657f424f35"
  },
  "transport.json": {
    "bytes": 245707,
    "sha256": "65b9238639647ba6a8f48bde48d3cb872de5c853b859eaf15893a93c87b21a5e",
    "git_blob_sha1": "8370a06599d45dd94d7a286ecb8b4d7efed8ff3e"
  },
  "stdin.py": {
    "bytes": 332345,
    "sha256": "4a2e1cadda16fa4b6cba127d3fd281235695b4c304ebd24cf53b90da1b9198cb",
    "git_blob_sha1": "db7ab423210cc0bcec5c2e014572c95ef429aee7"
  },
  "exact-request.json": {
    "bytes": 332806,
    "sha256": "2419f56447d1097e23ec4cacfcc5daa6097b1c001136089c025e07045b666d22",
    "git_blob_sha1": "1ad6d95f5c07a6a4a9816308390252b812c42dee"
  },
  "binding-proof.json": {
    "bytes": 2173,
    "sha256": "72f39467ba8757a9eee39f5b0e66cce8ae848e36326bdd7c53a489a066407b09",
    "git_blob_sha1": "dff3d44344a68bef7c062c8364317e6c3f799a25"
  }
};
function reproduceOriginalNdkInstall(utilitySource,rawByName){
  function need(ok,message){if(!ok)throw Error(message);}
  const U=Function(utilitySource+"\nreturn {utf8,sha1,sha256,gitBlob};")();
  need(U.gitBlob(U.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_PIN");
  for(const [name,p] of Object.entries(REQUIRED)){
    const raw=rawByName[name];need(typeof raw==="string","MISSING_RAW_"+name);
    const b=U.utf8(raw);
    need(b.length===p.bytes&&U.sha256(b)===p.sha256&&U.gitBlob(b)===p.git_blob_sha1,"PIN_"+name);
  }
  const actual={stdout_raw:rawByName["actual/entry-controls.original.json"],
    stdout_pin:{bytes:9826,sha256:"2bf1df7891dfd1617874d9885c3e562afa46be9924896dcca08ba54941b6b735"},
    terminal_raw:rawByName["actual/entry-controls-terminal.original.json"],
    terminal_pin:{bytes:731,sha256:"14183ad72c510bc49d143eff5ffabe13b480df5e3aaea2a5c9d6e754e49437f0"},
    job_id:"1a1b26c09d7-fc05-7dfb"};
  const bind=Function(rawByName["inputs/bind_install.js"]+"\nreturn bindOriginalNdkInstall;")();
  const result=bind(utilitySource,rawByName["base-packet.json"],rawByName["inputs/wrapper-template.py"],actual);
  for(const [k,n] of Object.entries({bindingRaw:"binding.json",packetRaw:"packet.json",
    transportRaw:"transport.json",stdin:"stdin.py",requestRaw:"exact-request.json",
    proofRaw:"binding-proof.json",entryRaw:"actual/entry-controls.original.json",
    terminalRaw:"actual/entry-controls-terminal.original.json"}))
    need(result[k]===rawByName[n],"FULL_BINDER_REPLAY_"+n);
  const packet=JSON.parse(result.packetRaw),base=JSON.parse(rawByName["base-packet.json"]);
  need(Object.keys(packet.sources).length===7,"SEVEN_SOURCES");
  for(const name of Object.keys(base.sources))
    need(JSON.stringify(packet.sources[name])===JSON.stringify(base.sources[name]),"SOURCE_INVERSE_"+name);
  for(const name of Object.keys(base.references))
    need(JSON.stringify(packet.references[name])===JSON.stringify(base.references[name]),"REFERENCE_INVERSE_"+name);
  for(const [name,raw] of [["entry-controls.original.json",actual.stdout_raw],
                         ["entry-controls-terminal.original.json",actual.terminal_raw]]){
    need(packet.references[name].body===raw,"ACTUAL_REFERENCE_BODY_"+name);
    delete packet.references[name];
  }
  need(JSON.stringify(packet,null,2)+"\n"===rawByName["base-packet.json"],"PACKET_ONLY_TWO_ACTUAL_ADDITIONS");
  const stdin=result.stdin;
  const encoded=(stdin.match(/^PACKET_B64 = '([A-Za-z0-9+/=]+)'$/m)||[])[1];
  need(typeof encoded==="string"&&encoded.length%4===0,"EXACT_BASE64_LINE");
  const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const bytes=[];let buffer=0,bits=0,ended=false;
  for(const c of encoded){
    if(c==="="){ended=true;continue;}
    need(!ended&&alphabet.includes(c),"BASE64_BODY");
    buffer=(buffer<<6)|alphabet.indexOf(c);bits+=6;
    if(bits>=8){bits-=8;bytes.push((buffer>>>bits)&255);}
  }
  const transport=U.utf8(result.transportRaw);
  need(bytes.length===transport.length&&bytes.every((b,i)=>b===transport[i]),"INDEPENDENT_BASE64_DECODE_EQUALS_TRANSPORT");
  let inverse=stdin;
  for(const [pattern,value] of [
      [/^PACKET_BYTES = [0-9]+$/m,"PACKET_BYTES = __PACKET_BYTES__"],
      [/^PACKET_SHA256 = '[0-9a-f]{64}'$/m,"PACKET_SHA256 = '__PACKET_SHA256__'"],
      [/^PACKET_B64 = '[A-Za-z0-9+/=]+'$/m,"PACKET_B64 = '__PACKET_B64__'"]]){
    need(pattern.test(inverse),"ONE_BOUND_SLOT");inverse=inverse.replace(pattern,value);
  }
  need(inverse===rawByName["inputs/wrapper-template.py"],"THREE_SLOT_WRAPPER_INVERSE");
  const q=JSON.parse(result.requestRaw);
  need(q.stdin===stdin&&q.executable==="/usr/bin/sudo"&&
    JSON.stringify(q.args)===JSON.stringify(["-n","/usr/bin/python3","-I","-B","-"])&&
    q.cpu_quota_percent===100&&q.memory_max_bytes===536870912&&q.nice===15&&q.timeout_seconds===240&&
    q.cwd==="/home/alex/work"&&q.host==="pocket4"&&
    q.idempotency_key==="p4-ndk-fixture-APK03-install01-4a2e1cadda16fa4b","FIXED_SINGLE_INSTALL_ENVELOPE");
  return{schema:1,ok:true,all_required_raw_pins_verified:true,whole_binder_replay_exact:true,
    seven_sources_byte_identical:true,nine_historical_reference_bodies_byte_identical:true,
    packet_only_two_actual_additions:true,wrapper_only_three_transport_slots:true,
    independent_UTF8_base64_roundtrip_exact:true,actual50_job:actual.job_id,
    request_idempotency_key:q.idempotency_key,installed_UID:null,
    Android_or_Main_actions:0,dispatch_performed:false,runtime_qualified:false};
}
