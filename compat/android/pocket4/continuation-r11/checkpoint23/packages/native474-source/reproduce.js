function reproduce(files){
"use strict";
const need=(ok,m)=>{if(!ok)throw Error(m);};
const H=Function(files["references/pure-verifier.js"]+"\nreturn {utf8,sha256,gitBlob,verifyGitTree};")();
const pin=t=>{const b=H.utf8(t);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==="object"?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
need(pin(files["references/pure-verifier.js"]).git_blob_sha1==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","exact verifier helper");
need(pin(files["diff-util.js"]).git_blob_sha1==="8bcb1f099a710d5dd638322d3a000877ac9d513d","exact diff helper");
const ud=Function("return ("+files["diff-util.js"]+")")();
const call=(path,...args)=>Function("return ("+files[path].trim()+");")()(...args);
const si={android:files["references/baseline472-android.rs"],manifest:files["references/baseline472-manifest.json"],typed473:files["references/actual473-android.rs"],fixture:files["delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"],actual472:files["references/actual-builder472-result.json"]};
const s=call("derive_source.js",si,H,ud);
const ci={compiler:files["references/baseline472-compile_builder.py"],parentProof:files["references/baseline472-composer-entry-proof.json"],parentScope:files["references/baseline472-build-scope.json"],actual472:si.actual472,sourceProof:files["references/source-checkpoint-proof.json"]};
const c=call("derive_compiler.js",ci,s,H);
const qi={stage:files["references/baseline472-stage.py"],transport:files["references/baseline472-transport.py"],generator:files["references/baseline472-make_request.js"],request:files["references/baseline472-exact-request.json"]};
const q=call("derive_request.js",qi,s,c,H);
const expected={
"delta/tools/droidloom-update/src/android.rs":s.source,
"delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp":s.fixture,
"expected-builder474-manifest.json":s.manifest,
"production.patch":s.production,
"compile_builder.py":c.compiler,
"composer-audiocontrol-proof.json":c.proofRaw,
"build-scope.json":c.scopeRaw,
"stage.py":q.stage,"transport.py":q.transport,"make_request.js":q.generator,
"exact-stdin.json":q.stdin,"exact-request.json":q.request,
"request-pins.json":JSON.stringify(q.requestPins,null,2)+"\n",
"compile-builder.diff":ud(ci.compiler,c.compiler,"compile_builder.py"),
"stage.diff":ud(qi.stage,q.stage,"stage.py"),
"transport.diff":ud(qi.transport,q.transport,"transport.py"),
"make-request.diff":ud(qi.generator,q.generator,"make_request.js")
};
for(const [p,t]of Object.entries(expected))need(files[p]===t,"full byte reproduction "+p);
const run=Function(q.generator+"\nreturn generate;")()(q.files,q.stage,H);
need(run.request===files["exact-request.json"]&&run.stdin===files["exact-stdin.json"],"independent exact generator");
const actual=JSON.parse(si.actual472),oldProof=JSON.parse(ci.parentProof),oldScope=JSON.parse(ci.parentScope),projection=JSON.parse(c.proofRaw),scope=JSON.parse(c.scopeRaw);
need(actual.state==="PASS"&&actual.commands.length===71&&actual.commands.every(r=>r.returncode===0&&!r.timed_out)&&actual.focused_tests_passed===32,"actual472 success source boundary");
need(actual.copied_manifest.sha256===pin(si.manifest).sha256&&actual.copied_manifest.bytes===pin(si.manifest).bytes,"parent copied map exact");
need(oldProof.candidate.manifest.sha256===actual.copied_manifest.sha256&&oldProof.baseline.compile_result.sha256===actual.actual_parent470_compile_authority.sha256,"historical parent proof links");
need(actual.composer_entry_proof_authority.sha256===pin(ci.parentProof).sha256&&actual.composer_build_scope_authority.sha256===pin(ci.parentScope).sha256&&equal(oldProof.scope,oldScope),"historical proof and scope originals");
need(projection.baseline.actual.sha256===pin(si.actual472).sha256&&projection.candidate.manifest.sha256===pin(s.manifest).sha256&&equal(projection.scope,scope),"new candidate source proof joins");
const oldMap=JSON.parse(si.manifest),newMap=JSON.parse(s.manifest);
const unchanged=Object.keys(oldMap).filter(k=>equal(oldMap[k],newMap[k]));
need(Object.keys(oldMap).length===500&&Object.keys(newMap).length===501&&unchanged.length===499,"500 to 501 exact map");
for(const a of scope.complete_ACK_production_inputs)need(oldMap[a.path].sha256===a.sha256&&equal(oldMap[a.path],newMap[a.path]),"unchanged ACK source "+a.path);
const registeredNames=[...s.source.matchAll(/^\s*fn (composer_retirement_audiocontrol_example_[a-z_]+)\(\)/gm)].map(m=>"android::tests::"+m[1]);
need(equal(registeredNames,s.testNames),"three exact production method controls");
need(q.requestPins.expected_host_ordinary_commands===74&&q.requestPins.expected_focused_controls===35,"focused counts");
need(run.request_object.memory_max_bytes===1073741824&&run.request_object.cpu_quota_percent===100&&run.request_object.nice===15&&run.request_object.timeout_seconds===600,"original host resource profile");
return{schema:1,source_only:true,source_and_request_reproduced:true,derived_members_checked:Object.keys(expected).length,source_map:{parent:500,candidate:501,unchanged:499,one_replacement:true,one_addition:true},ACK_sources_unchanged:9,request:pin(q.request),stdin:pin(q.stdin),transferred:6,reused_fixed_authorities:14,total_staged:20,inverse_edit_counts:{source:s.edits.length,compiler:c.edits.length,stage:q.edits.stage.length,transport:q.edits.transport.length,generator:q.edits.generator.length},host_tests_executed_here:false,Android_or_Main_actions:0};
}
