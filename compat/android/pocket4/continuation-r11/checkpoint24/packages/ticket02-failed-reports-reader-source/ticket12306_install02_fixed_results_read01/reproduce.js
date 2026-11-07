(function reproduceTicket02FixedResultsReader(files){
  const need=(v,m)=>{if(!v)throw Error(m);};
  const H=Function(files["pure-git-verifier.js"]+"\nreturn {utf8,sha256,gitBlob};")();
  const pin=s=>{need(typeof s==="string","missing raw text");const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
  const mf=JSON.parse(files["FROZEN_PINS.json"]);
  need(mf.schema===1&&mf.prefix==="ticket12306_install02_fixed_results_read01","fixed manifest kind");
  need(Object.keys(files).sort().join("|")===[...mf.files.map(r=>r.path),"FROZEN_PINS.json"].sort().join("|"),"exact paths");
  for(const r of mf.files){const p=pin(files[r.path]);need(r.mode==="100644"&&p.bytes===r.bytes&&p.sha256===r.sha256&&p.git_blob_sha1===r.git_blob_sha1,"leaf pin "+r.path);}
  const inputs=Object.fromEntries(["hilton-failed-two-reader.original.py","hilton-failed-two-request.original.json","ticket-stdout.original.json","ticket-terminal.original.json","scope.json"].map(p=>[p,files["references/"+p]]));
  const derive=Function("return "+files["derive.js"])(),o=derive(inputs,H);
  need(o.source===files["read.py"]&&o.request===files["exact-request.json"],"source/request exact");
  need(JSON.stringify(o.edits,null,2)+"\n"===files["exact-edits.json"],"edits exact");
  need(JSON.stringify(o.proof,null,2)+"\n"===files["derivation-proof.json"],"proof exact");
  const diff=Function("return ("+files["diff-util.js"]+")")();
  need(diff(inputs["hilton-failed-two-reader.original.py"],o.source,"read.py")===files["source.diff"],"diff exact");
  need(JSON.parse(o.request).stdin===o.source,"exact stdin");
  need(o.proof.source_scope_correction.correct_scope_unknown_until_full_worker===true&&!o.proof.source_scope_correction.seed_scope_is_authority,"conservative scope correction");
  return {schema:1,source:pin(o.source),request:pin(o.request),leaf_count:mf.files.length+1,
    source_request_edits_proof_diff_exact:true,full_inverse_original_source:true,failed_semantics_preserved:true,
    four_complete_reads_IO_and_FD_finally_unchanged:true,scope_unknown_until_full_worker:true,
    Python_executed:false,Hepta_calls:0,installation_outcome_qualified:false};
})
