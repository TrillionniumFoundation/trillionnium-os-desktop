function reproduceComposerNormal01(files,H){
 "use strict";
 const need=(v,m)=>{if(!v)throw Error(m);},same=(a,b)=>a===b;
 const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s)),git_blob_sha1:H.gitBlob(H.utf8(s))});
 const dc=Function("return ("+files["derive_controller.js"]+");")();
 const dp=Function("return ("+files["derive_request.js"]+");")();
 const qa=Function("return ("+files["qualify_actual474.js"]+");")();
 const input={baselineRequest:files["references/normal10-exact-request.json"],
   actual:files["actual-builder474-result.json"],compiler:files["references/actual474-compile_builder.py"],
   map:files["expected-builder474-manifest.json"],scope:files["references/actual474-build-scope.json"],
   proof:files["references/actual474-composer-audiocontrol-proof.json"],
   completion:files["composer-completion-functions.py"],controlFragment:files["composer-record-controls.py.fragment"]};
 const a=dp(input,H,dc,qa),ud=Function("return ("+files["diff-util.js"]+")")(),base=JSON.parse(input.baselineRequest),bp=JSON.parse(base.stdin);
 const emitted={...a.files,"stage.py":a.stage,"transport.py":a.transport,"stdin-packet.json":a.wire,"exact-request.json":a.requestText,
   "framework_build.diff":ud(bp.files["framework_build.py"],a.framework,"framework_build.py"),
   "pure_controls.diff":ud(bp.files["pure_controls.py"],a.controls,"pure_controls.py"),
   "fenced_build.diff":ud(bp.files["fenced_build.py"],a.fence,"fenced_build.py"),"stage.diff":ud(bp.stage,a.stage,"stage.py"),
   "transport.diff":ud(base.args[3],a.transport,"transport.py"),
   "controller-inverse.json":JSON.stringify({edits:a.controller.edits,controls:a.controller.controlEdits},null,2)+"\n",
   "packet-inverse.json":JSON.stringify(a.edits,null,2)+"\n",
   "source-scope.json":JSON.stringify(a.controller.sourceScope,null,2)+"\n",
   "request-pins.json":JSON.stringify(a.proof,null,2)+"\n"};
 for(const[name,raw]of Object.entries(emitted))need(same(files[name],raw),"FULL_REPRODUCER_BYTES:"+name);
 const sourceMap=JSON.parse(input.map),rust=files["references/actual474-android.rs"],nb=files["references/actual474-native_bridge.rs"];
 for(const[name,raw]of [["tools/droidloom-update/src/android.rs",rust],["tools/droidloom-update/src/native_bridge.rs",nb]]){
   const p=pin(raw);need(p.bytes===sourceMap[name].bytes&&p.sha256===sourceMap[name].sha256,"ACTUAL_RUST_SOURCE:"+name);
 }
 for(const[name,expectedBytes,expectedSHA,metadataSHA]of[
   ["references/SystemUI-tests.original.Android.bp",3392,"f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da","42118873220b0cc4d07e21a961052ddd5d81ab67be8df5d7c9dba9bd966aaeb5"],
   ["references/audiocontrol-example.original.Android.bp",1869,"9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6","d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93"]]){
   const raw=files[name],p=pin(raw);need(p.bytes===expectedBytes&&p.sha256===expectedSHA,"FIXED_BP_ORIGINAL:"+name);
   let taking=false,metadata="";for(const line of raw.split("\n")){if(line.startsWith("package {")||line.startsWith("license {"))taking=true;if(taking){metadata+=line+"\n";if(line==="}")taking=false;}}
   need(pin(metadata).sha256===metadataSHA,"EXACT_METADATA_PROJECTION:"+name);
 }
 return {schema:1,state:"PASS_FULL_V8_SOURCE_REPRODUCTION",derived_members:Object.keys(emitted).length,packet_members:Object.keys(a.files).length,
   request:pin(a.requestText),stdin:pin(a.wire),actual474_report:pin(input.actual),
   unchanged_baseline_packet_members:a.unchanged.length,unchanged_controller_functions:a.controller.unchangedFunctions.length,
   whole_controller_controls_fence_stage_transport_inverse:true,exact_two_metadata_projection_fixtures:true,
   original_raw_actual_preserved:true,Python_or_Rust_or_Soong_executed:false,normal_build_or_artifact_qualified:false};
}
