function(i,s,c,H){
"use strict";
const require=(ok,reason)=>{if(!ok)throw new Error(reason);};
const pin=t=>{const b=H.utf8(t);return{bytes:b.length,sha256:H.sha256(b)};};
const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const parents={"stage":{"bytes":14834,"sha256":"51559fe3bc57d75e0668d9bdec451cf9bf551ccdb6ac9a4eef9839bd38033643"},"transport":{"bytes":1013,"sha256":"11f51a6591e1c5fd39e6b59648f20a405728e250f1701f653a238583f60b308b"},"generator":{"bytes":4101,"sha256":"e80332a39da1064454a715e5304565e43cb5fa83a29a02e60190572627cd7b12"},"request":{"bytes":646415,"sha256":"ddb7f892a6c5b5278260d459989a10900d04fdea64a1d762e3333caac6244bf8"}};
for(const name of Object.keys(parents))require(eq(pin(i[name]),parents[name]),"actual472 "+name+" bytes/hash");
const oldRoot="/home/alex/work/pocket4-native-builder472-composer-retirement-entry-compile-01-20261106";
const newRoot="/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106";
require(c.root===newRoot,"fixed compiler root");
const fileOrder=["compile_builder.py","expected-builder474-manifest.json","composer-audiocontrol-proof.json","build-scope.json","delta/tools/droidloom-update/src/android.rs","delta/android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"];
const files={};
for(const [j,t] of [c.compiler,s.manifest,c.proofRaw,c.scopeRaw,s.source,s.fixture].entries())files[fileOrder[j]]=t;
const transferred=Object.fromEntries(fileOrder.map(n=>[n,pin(files[n])]));
const assignment=(text,name)=>{
 const prefix=name+"=";const ls=text.split("\n").filter(l=>l.startsWith(prefix));require(ls.length===1,"one fixed stage literal "+name);return JSON.parse(ls[0].slice(prefix.length));
};
const oldReuse=assignment(i.stage,"REUSED_AUTHORITY");
require(Object.keys(oldReuse).length===21,"old reuse count");
const firstNine=["go-control-result.json","image-tools-result.json","prior-compile01-failure.json","registry-result.json","rust193-tools-recheck-read03-result.json","selected-build.stdout","selection-result.json","typed-lock-derivation.json","typed-root-trees-result.json"];
require(eq(Object.keys(oldReuse).slice(0,9),firstNine),"nine original authority order");
const reused={};for(const name of firstNine)reused[name]=oldReuse[name];
reused["compiled-parent472-manifest.json"]={path:oldRoot+"/attempt01/copied-builder-source-manifest.json",bytes:99523,sha256:"fcbf72b891d9a9bbbcd015777e50cc3ade436f25732a603b51de261eab9cb27a",mode:384};
reused["compiled-parent472-result.json"]={path:oldRoot+"/attempt01/result.json",bytes:185025,sha256:"4c2f97bee3d6dbcc742f736c46fa18e9dc869830fe82211fb83c0afed6dfdbf4",mode:384};
reused["parent472-entry-proof.json"]={path:oldRoot+"/control-source/composer-entry-proof.json",bytes:11586,sha256:"3bc022c9924dc13f7e2ad8d6ed85a079af1dec61733433b88c2c76d0df0c60da",mode:256};
reused["parent472-build-scope.json"]={path:oldRoot+"/control-source/build-scope.json",bytes:6535,sha256:"f43cd778b75e484d53899eab543680e6b32ae5e54d6eca373b34223dcfcc8af9",mode:256};
reused["actual-wayland03-result.json"]=oldReuse["actual-wayland03-result.json"];
require(Object.keys(reused).length===14,"fourteen reusable authorities");
const expected={...transferred};for(const [name,p] of Object.entries(reused))expected[name]={bytes:p.bytes,sha256:p.sha256};
const edits={stage:[],transport:[],generator:[]};
let stage=i.stage,transport=i.transport,generator=i.generator;
function edit(which,old,newValue){
 let current=which==="stage"?stage:which==="transport"?transport:generator;
 const at=current.indexOf(old);require(at>=0&&current.indexOf(old,at+old.length)<0,"one exact edit "+which+" "+old.slice(0,90));
 edits[which].push({at,before:old,after:newValue});
 current=current.slice(0,at)+newValue+current.slice(at+old.length);
 if(which==="stage")stage=current;else if(which==="transport")transport=current;else generator=current;
}
edit("stage",'ROOT=Path('+JSON.stringify(oldRoot)+')','ROOT=Path('+JSON.stringify(newRoot)+')');
for(const [key,value] of Object.entries({TRANSFERRED:transferred,REUSED_AUTHORITY:reused,EXPECTED:expected})){
const oldLine=i.stage.split("\n").find(l=>l.startsWith(key+"="));edit("stage",oldLine,key+"="+JSON.stringify(value));
}
edit("stage","len(REUSED_AUTHORITY)==21 and len(EXPECTED)==27","len(REUSED_AUTHORITY)==14 and len(EXPECTED)==20");
edit("stage","# All twenty-one fixed actual/source inputs are re-read before creating ROOT.","# All fourteen fixed actual/source inputs are re-read before creating ROOT.");
require(stage.slice(stage.indexOf("\ndef require("))===i.stage.slice(i.stage.indexOf("\ndef require(")).replace("len(REUSED_AUTHORITY)==21 and len(EXPECTED)==27","len(REUSED_AUTHORITY)==14 and len(EXPECTED)==20").replace("# All twenty-one fixed actual/source inputs are re-read before creating ROOT.","# All fourteen fixed actual/source inputs are re-read before creating ROOT."),"original stage functions unchanged except closed counts/comment");
const stagePin=pin(stage);
const stdin=JSON.stringify({schema:1,stage,packet:files});const wirePin=pin(stdin);
require(wirePin.bytes<1024*1024,"actual process_start stdin bound");
edit("transport",i.transport.split("\n").find(l=>l.startsWith("EXPECTED=")),"EXPECTED="+JSON.stringify(wirePin));
edit("transport",i.transport.split("\n").find(l=>l.startsWith("STAGE=")),"STAGE="+JSON.stringify(stagePin));
const oldQ=JSON.parse(i.request);
require(eq(oldQ.args.slice(0,3),["-I","-B","-c"])&&oldQ.args[3]===i.transport&&JSON.parse(oldQ.stdin).stage===i.stage,"actual472 parent request joins");
const q={...oldQ,args:["-I","-B","-c",transport],stdin,idempotency_key:newRoot.split("/").at(-1)};
const request=JSON.stringify(q,null,2)+"\n";const requestPin=pin(request);
const constants={FILE_ORDER:fileOrder,EXPECTED:transferred,STAGE:stagePin,WIRE:wirePin,REQUEST:requestPin,BOUNDARY:transport,BASE:Object.fromEntries(Object.entries(q).filter(([k])=>k!=="args"&&k!=="stdin"))};
for(const [key,value] of Object.entries(constants)){
const prefix="const "+key+" = ";const ls=i.generator.split("\n").filter(l=>l.startsWith(prefix));require(ls.length===1,"one generator constant "+key);edit("generator",ls[0],prefix+JSON.stringify(value)+";");
}
require(generator.slice(generator.indexOf("function generate("))===i.generator.slice(i.generator.indexOf("function generate(")),"generator body unchanged");
const reproduce=Function(generator+"\nreturn generate;")()(files,stage,H);
require(reproduce.request===request&&reproduce.stdin===stdin,"exact request generator roundtrip");
for(const which of Object.keys(edits)){
let r=which==="stage"?stage:which==="transport"?transport:generator;
for(const e of [...edits[which]].reverse()){require(r.slice(e.at,e.at+e.after.length)===e.after,"inverse "+which);r=r.slice(0,e.at)+e.before+r.slice(e.at+e.after.length);}
require(r===i[which],"full inverse "+which);
}
const requestPins={schema:1,status:"SOURCE_ONLY_UNRUN",root:newRoot,idempotency_key:q.idempotency_key,request:requestPin,stdin:wirePin,stage:stagePin,transport:pin(transport),generator:pin(generator),transferred,transferred_count:6,reused_authorities:reused,reused_count:14,staged_count:20,actual_parent472_report:reused["compiled-parent472-result.json"],future_builder474_ELF_bound:false,old_472_and_typed473_unchanged:true,Main_actions:0,Android_actions:0,Soong_commands:0,resource_profile:{memory_max_bytes:q.memory_max_bytes,cpu_quota_percent:q.cpu_quota_percent,nice:q.nice,timeout_seconds:q.timeout_seconds},expected_host_ordinary_commands:74,expected_focused_controls:35,source_only_not_Android_ABI_or_runtime_qualification:true};
return{files,fileOrder,transferred,reused,expected,stage,transport,generator,stdin,request,requestPins,edits};
}
