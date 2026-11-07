function reproduceNormal09(saved){
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const H=Function(saved["pure-verifier.js"]+"\nreturn {utf8,sha256,gitBlob};")();
const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
const derive=Function("return ("+saved["derive_normal09_templates.js"]+")")();
const input={framework:saved["references/normal08-framework.template.py"],fence:saved["references/normal08-fence.template.py"],request08:saved["references/normal08-exact-request.json"],map473:saved["expected-builder473-manifest.json"],prior08inner:saved["prior-framework-inner-terminal.json"],prior08outer:saved["prior-framework-outer-terminal.json"]};
const D=derive(input,H);need(D.framework===saved["framework_build.template.py"]&&D.fence===saved["fenced_build.template.py"],"exact template reproduction");
const deriveBinder=Function("return ("+saved["derive_normal09_binder.js"]+")")();
const B=deriveBinder(saved["references/normal08-bind.js"],D,H);need(B.source===saved["bind_normal09.js"],"exact binder reproduction");
const bind=Function(B.source+"\nreturn bindNormal09;")();
const bound=bind(D.templateFiles,saved["actual-builder473-result.json"],saved["references/actual473-stdout.original.json"],input.request08,H);
for(const[n,s]of Object.entries(bound.files))need(saved[n]===s,"exact packet "+n);
for(const[n,s]of [["stage.py",bound.stage],["transport.py",bound.boundary],["exact-request.json",bound.requestText],["exact-stdin.json",bound.wire]])need(saved[n]===s,"exact transport "+n);
const ud=Function("return ("+saved["diff-util.js"]+")")();
for(const[n,s]of [
["framework.diff",ud(input.framework,D.framework,"framework_build.py")],
["fence.diff",ud(input.fence,D.fence,"fenced_build.py")],
["binder.diff",ud(saved["references/normal08-bind.js"],B.source,"bind_normal.js")]
])need(saved[n]===s,"exact diff "+n);
const manifest=JSON.parse(saved["SOURCE_PINS.json"]);
need(Object.keys(saved).length===manifest.payload_files.length+1&&Object.keys(saved).includes("SOURCE_PINS.json"),"closed artifact set");
for(const row of manifest.payload_files)need(JSON.stringify(pin(saved[row.path]))===JSON.stringify(row.pin),"whole payload "+row.path);
return {state:"EXACT_REPRODUCTION_PASS_NOT_REMOTE_EXECUTION",packet_files:Object.keys(bound.files).length,unchanged_authorities:D.unchanged.length,request:pin(bound.requestText),stdin:pin(bound.wire),focused:33,commands:71,normal_controls:46,Main_runtime_actions_performed:0};
}
