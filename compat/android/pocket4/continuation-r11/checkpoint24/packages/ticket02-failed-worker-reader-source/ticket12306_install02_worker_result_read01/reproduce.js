(function reproduceTicket02WorkerReader(files){
 const need=(v,m)=>{if(!v)throw Error(m);},H=Function(files["pure-git-verifier.js"]+"\nreturn {utf8,sha256,gitBlob};")();
 const pin=s=>{need(typeof s==="string","missing raw");const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
 const mf=JSON.parse(files["FROZEN_PINS.json"]);need(mf.schema===1&&mf.prefix==="ticket12306_install02_worker_result_read01","manifest kind");
 need(Object.keys(files).sort().join("|")===[...mf.files.map(r=>r.path),"FROZEN_PINS.json"].sort().join("|"),"exact paths");
 for(const r of mf.files){const p=pin(files[r.path]);need(r.mode==="100644"&&p.bytes===r.bytes&&p.sha256===r.sha256&&p.git_blob_sha1===r.git_blob_sha1,"leaf "+r.path);}
 const input={baseline_source:files["references/hilton-reader.original.py"],baseline_request:files["references/hilton-request.original.json"],coordinator:files["references/ticket-coordinator.original.json"],terminal:files["references/ticket-terminal.original.json"]};
 const o=Function("return "+files["derive.js"])()(input,H);
 need(o.source===files["read.py"]&&o.request===files["exact-request.json"],"source/request exact");
 need(JSON.stringify(o.edits,null,2)+"\n"===files["exact-edits.json"]&&JSON.stringify(o.proof,null,2)+"\n"===files["derivation-proof.json"],"edits/proof exact");
 need(Function("return ("+files["diff-util.js"]+")")()(input.baseline_source,o.source,"read.py")===files["source.diff"],"diff exact");
 need(JSON.parse(o.request).stdin===o.source,"exact stdin");
 const s=JSON.parse(files["references/ticket-stage.original.json"]);
 need(s.ok===false&&s.error.message==="ACTUAL_INSTALL_STATE_NOT_QUALIFIED"&&JSON.stringify(s.Main_before)===JSON.stringify(s.Main_after),"stage evidence kept distinct");
 return {schema:1,source:pin(o.source),request:pin(o.request),leaf_count:mf.files.length+1,source_request_edits_proof_diff_exact:true,full_inverse_original_source:true,failed_semantics_preserved:true,two_reads_IO_FD_finally_unchanged:true,installation_outcome:"UNKNOWN_PENDING_FULL_WORKER_REVIEW",Python_executed:false,Hepta_calls:0};
})
