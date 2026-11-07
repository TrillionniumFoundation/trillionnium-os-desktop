function reproduce(files) {
  const H=Function(files["pure-js-binary.js"]+"\nreturn {utf8,sha256,gitBlob};")();
  const D=Function("return ("+files["diff-util.js"]+")")();
  const Q=Function("return ("+files["qualify_nonces.js"]+")")();
  const F=Function("return ("+files["derive_bound.js"]+")")();
  const configs=JSON.parse(files["fixed-config.json"]);
  const authority=Object.fromEntries(["stdout","terminal","global919","global921","generator","catalog","request","admission"].map(k=>[k,files["references/nonce/"+k+".original"]]));
  const qualification=Q(authority,H);
  const reproduced=[];
  const packages=[];
  for (const config of configs) {
    const id=config.id;
    const output=F({
      config,old_source:files[id+"/references/read_target.original.py"],
      old_stage:files[id+"/references/stage.original.py"],
      old_request:files[id+"/references/exact-request.original.json"],
      fstat_actual:files[id+"/references/fstat.original.json"],
      failed_metadata_original:files[id+"/references/failed-metadata.original.json"],
      source_template:files[id+"/read_target.template.py"],
      stage_template:files[id+"/stage.template.py"],
      nonce_authority:authority
    },H,D,Q);
    for(const [name,raw]of Object.entries(output)) {
      const path=id+"/"+name;
      if(files[path]!==raw)throw Error("exact derived mismatch "+path);
      reproduced.push(path);
    }
    const request=JSON.parse(files[id+"/exact-request.json"]);
    const packet=JSON.parse(request.stdin);
    if(request.stdin!==files[id+"/stdin.json"]||packet.source!==files[id+"/read_target.py"]||
       request.args[5]!==files[id+"/transport.py"]||packet.nonce!==qualification[id].nonce)
      throw Error("request wire differs "+id);
    packages.push({id,package:config.package,root:config.new_root,key:request.idempotency_key,
      source:{bytes:H.utf8(packet.source).length,sha256:H.sha256(H.utf8(packet.source))},
      request:{bytes:H.utf8(files[id+"/exact-request.json"]).length,sha256:H.sha256(H.utf8(files[id+"/exact-request.json"]))},
      source_inverse_exact:true,stage_inverse_exact:true,original_transport_reproduced:true});
  }
  return {schema:1,ok:true,validation:"V8_EXACT_DERIVATION_ONLY",reproduced,packages,
    nonce_source_actual_qualified:true,all919_exclusions_checked:true,exact921_union_checked:true,
    nonce_producer_job:"1a1b2b9681b-fc05-7f7a",metadata02_dispatched:false,
    Python_compilation:"NOT_PERFORMED",device_execution:"UNRUN",whole_app_production_ready:false};
}
