async function metadataBatch(tools,v,ll,w,tok,read,complete,limit) {
 let completed=0;
 while(completed<limit){
  const rows=load("metadata22_execution_rows"),row=rows.find(x=>x.state!=="QUALIFIED_CURRENT_METADATA");
  if(!row)return {done:true,completed};
  const slug=row.slug,p="metadata22_"+slug+"01";
  if(row.state==="TERMINAL_UNQUALIFIED")return {blocked:slug,state:row.state,completed};
  if(row.state==="NOT_DISPATCHED"){
   const q=load("metadata22_root_bound_requests")[slug];
   const pre=await w.archive(p+"_preflight",{"root-review.json":JSON.stringify({slug,exact_request:w.pin(JSON.stringify(q,null,2)+"\n"),full22_review_tree:"a600ebe93c1553c1589ff2adfcd92b418a028d78",exact_five_readonly_commands:true,all_previous_targets_complete:true,UI_actions:0,automatic_retry:false},null,2)+"\n"},{bound:"a600ebe93c1553c1589ff2adfcd92b418a028d78",nonce_actual:"2a13c99fd080a145c1a42f9c7efcbf227226f1ef"});
   await w.start(p,q,pre);
   row.state="ADMITTED";row.job_id=load(p+"_job_id");store("metadata22_execution_rows",rows);
  }else if(row.state!=="ADMITTED")throw Error("unknown metadata state "+slug);
  const status=await w.status(p);
  if(!["succeeded","failed"].includes(status.state))return {running:slug,job_id:load(p+"_job_id"),completed};
  const result=await complete(tools,v,ll,w,tok,read,slug);
  notify({metadata:slug,state:result.state,uid:result.review.uid,version_code:result.review.version_code,APKs:result.review.apk_count,actual_tree:result.actual_tree});
  completed++;
  if(result.state!=="QUALIFIED_CURRENT_METADATA")return {blocked:slug,completed,checks:result.review.checks};
 }
 return {completed,pending:load("metadata22_execution_rows").filter(x=>x.state!=="QUALIFIED_CURRENT_METADATA").length};
}