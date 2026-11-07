function reproduceNormal10(saved){
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const H=Function(saved["pure-verifier.js"]+"\nreturn {utf8,sha256,gitBlob};")();
const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
need(pin(saved["pure-verifier.js"]).git_blob_sha1==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","fixed verifier helper");
const i={request:saved["references/normal09-exact-request.json"],outer:saved["prior-normal09-outer-terminal.json"],resource:saved["prior-normal09-resource-admission.json"],before:saved["references/normal09-Main-before.original.json"],after:saved["references/normal09-Main-after.original.json"],stage:saved["references/normal09-stage-receipt.original.json"],stdout:saved["references/normal09-stdout.original.ndjson"],terminal:saved["references/normal09-terminal.tool-original.json"]};
const qualifier=Function("return ("+saved["qualify_normal09.js"].trim()+");")();
const review=qualifier(i,H);need(JSON.stringify(review,null,2)+"\n"===saved["normal09-independent-review.json"],"full original failure qualification reproduced");
const derive=Function("return ("+saved["derive_normal10.js"].trim()+");")(),d=derive(i,H);
for(const [n,t]of Object.entries(d.files))need(saved[n]===t,"exact packet source "+n);
for(const [n,t]of [["stage.py",d.stage],["transport.py",d.transport],["exact-stdin.json",d.wire],["exact-request.json",d.requestText],["normal10-binding.json",JSON.stringify(d.proof,null,2)+"\n"]])need(saved[n]===t,"exact transport/proof "+n);
const old=JSON.parse(i.request),op=JSON.parse(old.stdin),ud=Function("return ("+saved["diff-util.js"]+")")();
for(const[n,t]of [["framework.diff",ud(op.files["framework_build.py"],d.framework,"framework_build.py")],["fence.diff",ud(op.files["fenced_build.py"],d.fence,"fenced_build.py")],["stage.diff",ud(op.stage,d.stage,"stage.py")],["transport.diff",ud(old.args[3],d.transport,"transport.py")]])need(saved[n]===t,"full minimal diff "+n);
if(saved["SOURCE_PINS.json"]){const index=JSON.parse(saved["SOURCE_PINS.json"]);need(Object.keys(saved).length===index.files.length+1,"exact artifact closure");for(const r of index.files)need(JSON.stringify(pin(saved[r.path]))===JSON.stringify(r.pin),"full file pin "+r.path);}
return{schema:1,state:"SOURCE_REPRODUCTION_PASS_NOT_NEW_RESOURCE_ADMISSION",request:pin(d.requestText),stdin:pin(d.wire),source_members:20,unchanged_source_members:16,unchanged_controller_functions:d.unchangedFunctions.length,inverse_edits:Object.fromEntries(Object.entries(d.edits).map(([k,v])=>[k,v.length])),past_Normal09_failure_reverified:true,original_Normal08_Soong_failure_retained:true,fresh_resource_observation_performed:false,host_or_Android_execution_performed:false};
}
