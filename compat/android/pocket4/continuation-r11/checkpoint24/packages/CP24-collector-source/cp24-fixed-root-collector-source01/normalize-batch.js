(async function normalizeCp24Batch(H,A,git,input,limit) {
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const binding=A.bindSeed(input.seed_raw,input.authority,input.parent_cut_raw);
need(Number.isSafeInteger(limit)&&limit>0&&limit<=4,"bounded normalization batch");
need(!git.get("cp24:pending-immutable-write"),"unknown immutable write must be read back, never replayed");
const collected=git.get("cp24:collection:"+binding.seed_pin.git_blob_sha1);
need(collected&&collected.collection_complete===true&&collected.errors.length===0&&
 collected.collected_root_count===binding.new_root_count&&
 collected.seed_pin.sha256===binding.seed_pin.sha256&&
 collected.verified_original_blob_count===collected.unique_original_blob_count,
 "all fixed original roots and unique full UTF8 bodies must qualify first");
const key="cp24:normalization:"+binding.seed_pin.git_blob_sha1;
const state=git.get(key)||{
 schema:"cp24-fixed-normalization-progress-v1",checkpoint:24,
 seed_pin:{...binding.seed_pin},cut_utc:binding.authority.cut_utc,
 required_packages:binding.new_root_count,packages:{},derived_blobs:{},errors:[],
 normalization_complete:false,original_leaf_bytes_unchanged:true,
 original_blob_count:collected.verified_original_blob_count,
 archive_reference_documents:collected.archive_reference_documents,
 JSON_links_followed:0,extra_roots_authorized:0,metadata_schema:3,no_ref_change:true};
need(state.seed_pin.git_blob_sha1===binding.seed_pin.git_blob_sha1&&
 state.seed_pin.sha256===binding.seed_pin.sha256&&state.errors.length===0,"exact nonfailed normalization state");
async function saveBlob(raw,pin,packageName,path) {
 const pending={operation:"create_blob",package:packageName,path,...pin,
  state:"PENDING_IMMUTABLE_RESPONSE",do_not_replay_unknown_mutation:true};
 git.set("cp24:pending-immutable-write",pending);
 need(await git.createBlob(raw)===pin.git_blob_sha1,"derived metadata response SHA");
 need(await git.blob(pin.git_blob_sha1)===raw,"complete generated metadata readback");
 git.set("cp24:pending-immutable-write",null);
}
async function saveTree(entries,expected,packageName,rows) {
 git.set("cp24:pending-immutable-write",{operation:"create_tree",package:packageName,
  sha:expected,state:"PENDING_IMMUTABLE_RESPONSE",do_not_replay_unknown_mutation:true});
 need(await git.createTree(entries)===expected,"normalized immutable tree response");
 const value=await git.tree(expected,Boolean(rows));
 if(rows)H.verifyGitTree(value,rows,expected);
 else A.shallow(value,expected);
 git.set("cp24:pending-immutable-write",null);
}
const order=(a,b)=>a.name<b.name?-1:a.name>b.name?1:0;
const todo=[...binding.seed.new_roots].sort(order).filter(r=>!state.packages[r.name]).slice(0,limit);
for(const root of todo) {
 try {
  const w=collected.walks[root.name];
  need(w&&w.original_tree===root.original_tree&&w.name===root.name,"exact collected package");
  const rows=w.leaves.map(row=>{
   const pin=collected.blob_pins[row.git_blob_sha1];
   need(pin&&pin.bytes===row.bytes&&pin.git_blob_sha1===row.git_blob_sha1&&
    pin.full_original_body_read===true&&/^[0-9a-f]{64}$/.test(pin.sha256),"complete original leaf pin");
   return {...row,sha256:pin.sha256,encoding:"utf-8",origin:"unchanged-original-archive-leaf"};
  });
  for(const [path,body]of Object.entries(A.metadata(w))) {
   const bytes=H.utf8(body),pin={path,mode:"100644",bytes:bytes.length,
    sha256:H.sha256(bytes),git_blob_sha1:H.gitBlob(bytes),encoding:"utf-8",
    origin:path==="_dependency-mounts.json"?"derived-canonical-dependency-mounts":"derived-original-tree-reconstruction"};
   if(!state.derived_blobs[pin.git_blob_sha1]) {
    await saveBlob(body,pin,root.name,path);
    state.derived_blobs[pin.git_blob_sha1]={...pin,full_readback_complete:true};
    git.set(key,state);
   } else need(state.derived_blobs[pin.git_blob_sha1].sha256===pin.sha256&&
               state.derived_blobs[pin.git_blob_sha1].full_readback_complete===true,"cached derived metadata");
   rows.push(pin);
  }
  rows.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
  const expected=A.normalizedTree(rows);
  await saveTree(rows.map(r=>({path:r.path,mode:r.mode,type:"blob",sha:r.git_blob_sha1})),
                 expected.sha,root.name,rows);
  state.packages[root.name]={name:root.name,original_tree:root.original_tree,
   normalized_tree:expected.sha,aliases:w.aliases,files:rows.length,
   retained_original_leaf_count:w.leaves.length,dependency_cuts:w.cuts,
   rows,expected,readback_complete:true};
  git.set(key,state);
 }catch(error){
  const message=H.utf8(String(error));
  state.errors.push({name:root.name,error_message_bytes:message.length,
   error_message_sha256:H.sha256(message),pending:git.get("cp24:pending-immutable-write")||null});
  git.set(key,state);
  // Stop on the first failure. No automatic mutation replay and no ref action.
  return {normalization_complete:false,verified_packages:Object.keys(state.packages).length,
   errors:state.errors,pending:git.get("cp24:pending-immutable-write")||null,no_ref_change:true};
 }
}
const packages=Object.values(state.packages).sort(order);
const entries=packages.map(p=>({path:p.name,mode:"040000",type:"tree",sha:p.normalized_tree}));
const expected=H.treeHash(entries.map(({path,...row})=>({name:path,...row})));
await saveTree(entries,expected,"partial-packages-root",null);
state.packages_tree=expected;
state.normalization_complete=packages.length===binding.new_root_count&&
 packages.every(p=>p.readback_complete===true);
state.normalized_packages=packages.length;
state.generated_metadata_blobs=Object.keys(state.derived_blobs).length;
git.set(key,state);
const checkpoint=await git.persist("cp24-normalization-progress",state,
 [{path:"packages",mode:"040000",type:"tree",sha:expected}]);
return {checkpoint,packages_tree:expected,normalized_packages:packages.length,
 required_packages:binding.new_root_count,normalization_complete:state.normalization_complete,
 metadata_full_readback_complete:true,original_leaf_bytes_unchanged:true,
 JSON_links_followed:0,no_ref_change:true};
})
