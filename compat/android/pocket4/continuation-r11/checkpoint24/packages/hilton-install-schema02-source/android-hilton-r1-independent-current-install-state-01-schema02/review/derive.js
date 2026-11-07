// Pure reproduction of two previously unsubmitted app installation packages.
// No device, process, filesystem, nonce generation or Git ref action.
const INPUT_PINS = {
  "hilton": {
    "request": {
      "bytes": 214486,
      "sha256": "17a48991cf9651a171f2580911f5c9a2ccdc81cc51908ef8fb5b3744e9f6da91",
      "git_blob_sha1": "86a3c3cded5840a644fcbeebc3fdb92174198cad"
    },
    "context": {
      "bytes": 25248,
      "sha256": "eaf426c17c8818f88f0abcf4d7ab59d86b10e5e536d10640a15db80d6b37d460",
      "git_blob_sha1": "4c01cf3280a38115f583b58cef3ee2436b64b427"
    }
  },
  "united": {
    "request": {
      "bytes": 214390,
      "sha256": "a79110658e78fd8874e4912e2e558a04ad91ad88fd20cc9f434073e42e0f7175",
      "git_blob_sha1": "a1dfdbaa574eeb9a57689bcbd896d5217a19f87b"
    },
    "context": {
      "bytes": 25247,
      "sha256": "afb4ef79a762e6cfc5bca0fd558e77c1611ff8183c85a2333e99cd94415a7e57",
      "git_blob_sha1": "490217ccbb1f2db2da948df5ae4197b58c15d3f5"
    }
  }
};
function deriveCurrentInstallSchema02(utilitySource,contextReproducerSource,label,originalRequestRaw){
  const U=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")();
  const need=(v,m)=>{if(!v)throw Error(m);};
  need(U.gitBlob(U.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_PIN");
  need(U.gitBlob(U.utf8(contextReproducerSource))==="e2042353645031cb3ef9b98ddee97035e1de9741","CONTEXT_REPRODUCER_PIN");
  const info=INPUT_PINS[label];need(info,"ONLY_HILTON_OR_UNITED");
  const pin=s=>({bytes:U.utf8(s).length,sha256:U.sha256(U.utf8(s))});
  need(pin(originalRequestRaw).bytes===info.request.bytes&&pin(originalRequestRaw).sha256===info.request.sha256&&U.gitBlob(U.utf8(originalRequestRaw))===info.request.git_blob_sha1,"ORIGINAL_REQUEST_PIN");
  const sorted=v=>Array.isArray(v)?v.map(sorted):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])])):v;
  const canonical=v=>JSON.stringify(sorted(v))+"\n";
  const original=JSON.parse(originalRequestRaw),packet=JSON.parse(original.stdin),oldManifestRaw=packet.files["SOURCE_PINS.json"],manifest=JSON.parse(oldManifestRaw);
  need(canonical(packet)===original.stdin&&Object.keys(manifest.files).length===15&&Object.keys(packet.files).length===16,"ORIGINAL_PACKET_SET_AND_CANONICAL");
  need(pin(oldManifestRaw).sha256===packet.source_manifest_sha256,"ORIGINAL_MANIFEST_PIN");
  for(const [name,p]of Object.entries(manifest.files))need(JSON.stringify(pin(packet.files[name]))===JSON.stringify(p),"ORIGINAL_SOURCE_PIN_"+name);
  const contextName=label+"_context.py";
  const reproduce=Function(contextReproducerSource+"\nreturn reproduceMetadataSchemaContext;")();
  const candidate=reproduce(utilitySource,label,packet.files[contextName],packet.files["actual-target-metadata.json"],packet.files["target-artifact-reference.json"]);
  const oldFiles={...packet.files},oldKey=original.idempotency_key;
  const newKey="pocket4-owned-"+label+"-qa-r1-current-r6-install-state-01-schema02-"+info.context.sha256.slice(0,16);
  const beforeKey="KEY = '"+oldKey+"'",afterKey="KEY = '"+newKey+"'";
  need(packet.files["make_request.py"].split(beforeKey).length===2,"ONE_MAKE_REQUEST_KEY");
  packet.files[contextName]=candidate;packet.files["make_request.py"]=packet.files["make_request.py"].replace(beforeKey,afterKey);
  for(const name of[contextName,"make_request.py"])manifest.files[name]=pin(packet.files[name]);
  packet.files["SOURCE_PINS.json"]=JSON.stringify(manifest,null,2)+"\n";packet.source_manifest_sha256=pin(packet.files["SOURCE_PINS.json"]).sha256;
  const payload=canonical(packet);need(U.utf8(payload).length<=262144,"ORIGINAL_PACKET_BOUND");
  const root="/home/alex/work/pocket4-owned-"+label+"-qa-r1-install-state-01",stageHash=manifest.files["stage_execute.py"].sha256;
  const wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"+
    "assert hashlib.sha256(raw).hexdigest()=='"+pin(payload).sha256+"'\n"+
    "p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"+
    "assert hashlib.sha256(src).hexdigest()=='"+stageHash+"'\n"+
    "scope={'__name__':'owned_qa_stage','__file__':'"+root+"/source/stage_execute.py'}\n"+
    "exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n";
  need(original.args.length===6&&original.args[5].replace(pin(original.stdin).sha256,pin(payload).sha256)===wrapper,"WRAPPER_ONLY_PACKET_HASH_CHANGED");
  const request={...original,args:[...original.args.slice(0,5),wrapper],stdin:payload,idempotency_key:newKey};
  for(const name of Object.keys(oldFiles))if(![contextName,"make_request.py","SOURCE_PINS.json"].includes(name))need(oldFiles[name]===packet.files[name],"UNCHANGED_SOURCE_"+name);
  const inputs=JSON.parse(packet.files["INPUTS.json"]);
  need(inputs.helper_uid===null&&inputs.nonces.flow===packet.nonce&&inputs.source_qualification_controls===75&&inputs.ordered_worker_Android_commands===13,"ORIGINAL_SCOPE_COUNTS");
  return {sources:packet.files,packetRaw:payload,requestRaw:JSON.stringify(sorted(request),null,2)+"\n",proofRaw:JSON.stringify({schema:1,kind:"fixed-metadata-schema-install-package02",label,status:"SOURCE_ONLY_NOT_EXECUTED",original_request:info.request,context:pin(candidate),root,old_key:oldKey,new_key:newKey,old_unused_nonces:inputs.nonces,nonce_generated:false,helper_uid:null,context_functions_changed:["qualify_target_metadata","baseline_scope"],original_metadata_and_reference_unchanged:true,controls_body_unchanged:true,controls_count:75,ordered_worker_Android_commands:13,Main_guard_and_FD_and_source_contracts_unchanged:true,original_13_other_members_byte_identical:true,packet:pin(payload),source_manifest:pin(packet.files["SOURCE_PINS.json"]),request_dispatched:false,python_executed:false},null,2)+"\n"};
}
