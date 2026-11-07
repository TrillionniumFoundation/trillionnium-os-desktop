const repository="TrillionniumFoundation/trillionnium-os-desktop";
const pin=s=>{const b=v.utf8(s);return{bytes:b.length,sha256:v.sha256(b),git_blob_sha1:v.gitBlob(b)};};
const rawOf=r=>{const a=r?.content?.filter(x=>x.type==="text");v.assertThat(a?.length===1&&typeof a[0].text==="string","single original tool text");return a[0].text;};
async function archive(prefix,files,refs={}){
 const elements=[];for(const[path,content]of Object.entries(files)){v.assertThat(!path.includes("/")&&typeof content==="string","flat exact archive");elements.push({path,mode:"100644",type:"blob",content});}
 for(const[path,sha]of Object.entries(refs)){v.assertThat(!path.includes("/")&&/^[0-9a-f]{40}$/.test(sha),"tree reference");elements.push({path,mode:"040000",type:"tree",sha});}
 const expected=v.treeHash(elements.map(e=>({name:e.path,mode:e.mode,type:e.type,sha:e.sha||pin(e.content).git_blob_sha1})));
 const r=await tools.mcp__codex_apps__github_create_tree({repository_full_name:repository,tree_elements:elements});
 store(prefix+"_archive_response",r);store(prefix+"_expected_tree",expected);v.assertThat(!r.isError&&r.structuredContent?.sha===expected,"archive Merkle equality");store(prefix+"_tree",expected);return expected;
}
async function start(prefix,q,preflight){
 const known=load("dispatch_known_prefixes")||[];
 v.assertThat(!load(prefix+"_dispatch_intent")&&!load(prefix+"_admission_text")&&!known.includes(prefix),"NO_REPLAY_EXISTING_DISPATCH");
 v.assertThat(q.host==="pocket4"&&typeof q.stdin==="string"&&v.utf8(q.stdin).length<=1048576&&/^[0-9a-f]{40}$/.test(preflight),"fixedhost wire preflight");
 const intent={request:pin(JSON.stringify(q,null,2)+"\n"),preflight_tree:preflight,idempotency_key:q.idempotency_key,automatic_retry:false};
 store(prefix+"_dispatch_intent",intent);store(prefix+"_preflight_tree",preflight);store(prefix+"_exact_request",q);store("dispatch_known_prefixes",[...known,prefix]);
 let response;try{response=await tools.mcp__codex_apps__heptaruntime_mac_controller_process_start(q);}catch(e){store(prefix+"_admission_unknown",true);await archive(prefix+"_admission_unknown",{"unknown.json":JSON.stringify({state:"ADMISSION_UNKNOWN_NO_REPLAY",intent,error:String(e)},null,2)+"\n"},{preflight});throw e;}
 const raw=rawOf(response);store(prefix+"_admission_text",raw);
 const tree=await archive(prefix+"_admission",{"admission.tool-original.json":raw,"dispatch-intent.json":JSON.stringify(intent,null,2)+"\n"},{preflight});
 const a=ll(raw);v.assertThat(!response.isError&&typeof a.job?.id==="string","ADMISSION_UNKNOWN_NO_REPLAY");
 store(prefix+"_job_id",a.job.id);return{job_id:a.job.id,admission_tree:tree,reused:a.reused,launch_state:a.job.launch_state};
}
async function status(prefix){
 const job=load(prefix+"_job_id");v.assertThat(typeof job==="string","fixed known job");
 const r=await tools.mcp__codex_apps__heptaruntime_mac_controller_process_status({host:"pocket4",job_id:job}),raw=rawOf(r);
 store(prefix+"_status_latest_text",raw);store(prefix+"_status_latest_pin",pin(raw));v.assertThat(!r.isError,"status failed");
 const d=ll(raw);store(prefix+"_status_latest",d);return d;
}
return{pin,rawOf,archive,start,status};