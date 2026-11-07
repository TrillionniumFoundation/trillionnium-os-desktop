
function need(ok,m){if(!ok)throw Error(m);}
const repository="TrillionniumFoundation/trillionnium-os-desktop";
const pin=s=>({bytes:v.utf8(s).length,sha256:v.sha256(v.utf8(s)),git_blob_sha1:v.gitBlob(v.utf8(s))});
const rawOf=r=>{need(r&&Array.isArray(r.content),"original content");const a=r.content.filter(x=>x.type==="text");need(a.length===1&&typeof a[0].text==="string","single original text");return a[0].text;};
async function archive(prefix,files,refs={}){
 const entries=[],elements=[];
 for(const[name,content]of Object.entries(files)){need(!name.includes("/")&&typeof content==="string","flat exact text archive");const p=pin(content);entries.push({name,type:"blob",mode:"100644",sha:p.git_blob_sha1});elements.push({path:name,mode:"100644",type:"blob",content});}
 for(const[name,sha]of Object.entries(refs)){need(!name.includes("/")&&/^[0-9a-f]{40}$/.test(sha),"exact archive tree ref");entries.push({name,type:"tree",mode:"040000",sha});elements.push({path:name,mode:"040000",type:"tree",sha});}
 const expected=v.treeHash(entries);store(prefix+"_expected_tree",expected);
 const r=await tools.mcp__codex_apps__github_create_tree({repository_full_name:repository,tree_elements:elements});store(prefix+"_tree_response",r);
 need(r.structuredContent?.sha===expected,"archive returned different tree");store(prefix+"_tree",expected);return expected;
}
async function start(prefix,q,preflight){
 need(!load(prefix+"_dispatch_intent")&&!load(prefix+"_admission_text"),"no replay: existing dispatch");
 need(q.host==="pocket4"&&typeof q.stdin==="string"&&v.utf8(q.stdin).length<=1048576,"host/wire");
 need(typeof preflight==="string"&&/^[0-9a-f]{40}$/.test(preflight),"durable preflight");
 const intent={request:pin(JSON.stringify(q,null,2)+"\n"),preflight_tree:preflight,idempotency_key:q.idempotency_key,automatic_retry:false};
 store(prefix+"_dispatch_intent",intent);store(prefix+"_exact_request",q);store(prefix+"_preflight_tree",preflight);
 let r;
 try{r=await tools.mcp__codex_apps__heptaruntime_mac_controller_process_start(q);}
 catch(error){const failure={state:"ADMISSION_UNKNOWN_NO_REPLAY",intent,error:String(error)};store(prefix+"_admission_unknown",failure);await archive(prefix+"_admission_unknown",{"unknown.json":JSON.stringify(failure,null,2)+"\n"},{preflight});throw error;}
 store(prefix+"_admission_response",r);
 const raw=rawOf(r);store(prefix+"_admission_text",raw);store(prefix+"_admission_pin",pin(raw));
 const tree=await archive(prefix+"_admission",{"admission.tool-original.json":raw,"dispatch-intent.json":JSON.stringify(intent,null,2)+"\n"},{preflight});
 const a=ll(raw);store(prefix+"_admission_parsed",a);
 need(!r.isError&&a.job&&typeof a.job.id==="string","admission not established; do not replay");
 store(prefix+"_job_id",a.job.id);
 return {job_id:a.job.id,admission_tree:tree,reused:a.reused,launch:a.launch,launch_state:a.job.launch_state};
}
async function status(prefix){
 const job=load(prefix+"_job_id");need(typeof job==="string","job id");
 const r=await tools.mcp__codex_apps__heptaruntime_mac_controller_process_status({host:"pocket4",job_id:job});
 const raw=rawOf(r),p=pin(raw);const records=load(prefix+"_status_originals")??[];
 records.push({raw,pin:p,is_error:r.isError===true});store(prefix+"_status_originals",records);
 store(prefix+"_status_latest_text",raw);store(prefix+"_status_latest_pin",p);
 need(!r.isError,"status error; no replay");const d=ll(raw);store(prefix+"_status_latest",d);return d;
}
return {pin,rawOf,archive,start,status};
