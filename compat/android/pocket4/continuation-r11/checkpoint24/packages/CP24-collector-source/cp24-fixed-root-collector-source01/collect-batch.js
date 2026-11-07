(async function collectCp24Batch(H,A,git,input,limits) {
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const binding=A.bindSeed(input.seed_raw,input.authority,input.parent_cut_raw);
if(limits===undefined)limits={roots:1,blobs:8};
need(limits&&Number.isSafeInteger(limits.roots)&&limits.roots>=0&&limits.roots<=4&&
 Number.isSafeInteger(limits.blobs)&&limits.blobs>=0&&limits.blobs<=16&&
 limits.roots+limits.blobs>0,"bounded explicit collection batch");
need(!git.get("cp24:pending-immutable-write"),"unresolved immutable response; readback before resuming");
const key="cp24:collection:"+binding.seed_pin.git_blob_sha1;
let state=git.get(key);
if(state) {
 need(state.schema==="cp24-fixed-root-collection-progress-v1"&&
  state.seed_pin.git_blob_sha1===binding.seed_pin.git_blob_sha1&&
  state.seed_pin.bytes===binding.seed_pin.bytes&&state.seed_pin.sha256===binding.seed_pin.sha256&&
  state.cut_utc===binding.authority.cut_utc&&state.errors.length===0,"exact nonfailed collection state");
} else {
 state={schema:"cp24-fixed-root-collection-progress-v1",checkpoint:24,
  seed_pin:{...binding.seed_pin},cut_utc:binding.authority.cut_utc,
  previous_cut_scope:{...binding.parent_cut_scope_pin},
  previous_master_pin:{...binding.seed.previous_master},
  required_new_roots:binding.new_root_count,
  inherited_canonical_roots:binding.inherited_root_count,
  walks:{},directory_cache:{},blob_pins:{},errors:[],batches:0,
  collected_root_count:0,unique_original_blob_count:0,verified_original_blob_count:0,
  archive_reference_documents:[],JSON_links_followed:0,extra_roots_authorized:0,
  collection_complete:false,parent_master_body_verified_by_this_collector:false,
  ref_or_PR_changed:false,status:"COLLECTION_IN_PROGRESS"};
}
const newByName=new Map(binding.seed.new_roots.map(r=>[r.name,r]));
const ordered=[...binding.seed.new_roots].sort((a,b)=>a.name<b.name?-1:a.name>b.name?1:0);
for(const [name,w]of Object.entries(state.walks)) {
 const authorized=newByName.get(name);
 need(authorized&&w.name===name&&w.original_tree===authorized.original_tree,"cached walk exact authorization");
 for(const cut of w.cuts) {
  const grant=binding.roots.get(cut.tree_sha);
  need(grant&&cut.canonical_package===grant.name&&cut.checkpoint===grant.checkpoint,"cached canonical cut");
 }
}
for(const [sha,dir]of Object.entries(state.directory_cache))
 need(dir.sha===sha&&H.treeHash(dir.entries)===sha,"cached original directory Merkle");
async function shallow(sha) {
 let value=state.directory_cache[sha];
 if(!value){value=A.shallow(await git.tree(sha,false),sha);state.directory_cache[sha]=value;git.set(key,state);}
 need(value.sha===sha&&H.treeHash(value.entries)===sha,"original shallow Merkle");
 return value;
}
function failure(operation,object,error) {
 const message=String(error),bytes=H.utf8(message);
 state.errors.push({operation,object,error_type:error&&error.name||"Error",
  error_message_bytes:bytes.length,error_message_sha256:H.sha256(bytes),
  raw_error_or_blob_body_exported:false});
 state.status="COLLECTION_BLOCKED";
 state.collection_complete=false;
}
for(const root of ordered.filter(r=>!state.walks[r.name]).slice(0,limits.roots)) {
 try {state.walks[root.name]=await A.traverse(root,binding.roots,shallow);git.set(key,state);}
 catch(error){failure("original-root-traversal",root.original_tree,error);break;}
}
const required={};
if(state.errors.length===0) {
 try {
  for(const w of Object.values(state.walks))for(const leaf of w.leaves) {
   const old=required[leaf.git_blob_sha1];
   need(!old||old.bytes===leaf.bytes,"same Git blob advertised different size");
   required[leaf.git_blob_sha1]={bytes:leaf.bytes,git_blob_sha1:leaf.git_blob_sha1};
  }
  for(const [sha,p]of Object.entries(state.blob_pins)) {
   need(required[sha]&&required[sha].bytes===p.bytes&&p.git_blob_sha1===sha&&
    p.encoding==="utf-8"&&/^[0-9a-f]{64}$/.test(p.sha256)&&p.full_original_body_read===true,
    "cached full-read pin must belong to a traversed authorized leaf");
  }
 } catch(error) {failure("leaf-requirements",binding.seed_pin.git_blob_sha1,error);}
}
if(state.errors.length===0) {
 const todo=Object.values(required).filter(r=>!state.blob_pins[r.git_blob_sha1])
  .sort((a,b)=>a.git_blob_sha1<b.git_blob_sha1?-1:1).slice(0,limits.blobs);
 for(let i=0;i<todo.length;i+=4) {
  const group=todo.slice(i,i+4);
  const results=await Promise.allSettled(group.map(async row=>{
   const originalRaw=await git.blob(row.git_blob_sha1);
   const p=A.verifyBlob(originalRaw,row.git_blob_sha1,row.bytes);
   return {...p,full_original_body_read:true};
  }));
  for(let j=0;j<results.length;j++) {
   const result=results[j],row=group[j];
   if(result.status==="fulfilled")state.blob_pins[row.git_blob_sha1]=result.value;
   else failure("original-full-UTF8-read",row.git_blob_sha1,result.reason);
  }
  git.set(key,state);
  if(state.errors.length)break;
 }
}
state.batches+=1;
state.collected_root_count=Object.keys(state.walks).length;
state.unique_original_blob_count=Object.keys(required).length;
state.verified_original_blob_count=Object.keys(state.blob_pins).length;
state.original_directory_count=Object.keys(state.directory_cache).length;
state.collection_complete=state.errors.length===0&&
 state.collected_root_count===binding.new_root_count&&
 state.unique_original_blob_count===state.verified_original_blob_count&&
 Object.keys(required).every(sha=>state.blob_pins[sha]&&state.blob_pins[sha].bytes===required[sha].bytes);
if(state.collection_complete) {
 state.archive_reference_documents=Object.values(state.walks)
  .flatMap(w=>A.archiveReferenceDocuments(w,state.blob_pins));
 state.status="COLLECTED_AND_FULL_ORIGINALS_VERIFIED";
}
git.set(key,state);
const checkpoint=await git.persist("cp24-root-collection-progress",state);
return {checkpoint,seed:binding.seed_pin,cut_utc:binding.authority.cut_utc,
 collected_roots:state.collected_root_count,required_roots:binding.new_root_count,
 original_directories:state.original_directory_count,unique_original_blobs:state.unique_original_blob_count,
 verified_original_blobs:state.verified_original_blob_count,
 archive_reference_documents:state.archive_reference_documents.length,
 JSON_links_followed:0,collection_complete:state.collection_complete,
 errors:state.errors.length,no_ref_change:true};
})
