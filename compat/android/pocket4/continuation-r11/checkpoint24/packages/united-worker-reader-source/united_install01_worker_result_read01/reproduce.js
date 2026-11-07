(function reproduceUnitedWorkerReader(files){
  const need=(v,m)=>{if(!v)throw Error(m);};
  const H=Function(files["pure-git-verifier.js"]+"\nreturn {utf8,sha256,gitBlob};")();
  const pin=s=>{need(typeof s==="string","missing raw text");const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
  const manifest=JSON.parse(files["FROZEN_PINS.json"]);
  need(manifest.schema===1&&manifest.prefix==="united_install01_worker_result_read01","fixed manifest kind");
  need(Object.keys(files).sort().join("|")===[...manifest.files.map(r=>r.path),"FROZEN_PINS.json"].sort().join("|"),"exact bundle paths");
  for(const r of manifest.files){const p=pin(files[r.path]);need(r.mode==="100644"&&p.bytes===r.bytes&&p.sha256===r.sha256&&p.git_blob_sha1===r.git_blob_sha1,"bundle leaf "+r.path);}
  const derive=Function("return "+files["derive.js"])();
  const inputs={baseline_source:files["references/hilton-reader.original.py"],baseline_request:files["references/hilton-request.original.json"],coordinator:files["references/united-coordinator.original.json"],terminal:files["references/united-terminal.original.json"]};
  const o=derive(inputs,H);
  need(o.source===files["read.py"]&&o.request===files["exact-request.json"],"exact source/request reproduction");
  need(JSON.stringify(o.edits,null,2)+"\n"===files["exact-edits.json"],"exact edits reproduction");
  need(JSON.stringify(o.proof,null,2)+"\n"===files["derivation-proof.json"],"exact proof reproduction");
  const diff=Function("return ("+files["diff-util.js"]+")")();
  need(diff(inputs.baseline_source,o.source,"read.py")===files["source.diff"],"exact source diff reproduction");
  need(JSON.parse(o.request).stdin===o.source,"request exact stdin");
  return {schema:1,source:pin(o.source),request:pin(o.request),bundle_leaf_count:manifest.files.length+1,
    exact_source_request_edits_proof_and_diff_reproduced:true,full_inverse_original_source:true,
    unchanged_io_segments:o.proof.unchanged_segments,Python_executed:false,Hepta_calls:0,installation_outcome_qualified:false};
})
