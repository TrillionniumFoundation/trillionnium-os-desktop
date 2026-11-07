(async function normalizeBatch(ctx,limit) {
 const {get,set,H,A,createBlob,createTree}=ctx;
 const walks=get("cp23:walks"),pins=get("cp23:blob-pins"),normal=get("cp23:normalized"),derived=get("cp23:derived-blobs")||{},intents=get("cp23:mutation-intents")||[],errors=get("cp23:normalization-errors")||[];
 if(Object.keys(walks).length!==239||Object.keys(pins).length!==1367||get("cp23:blob-read-errors").some(e=>!e.resolved)||errors.length)throw Error("verification incomplete");
 const todo=Object.values(walks).filter(w=>!normal[w.name]).sort((a,b)=>a.name<b.name?-1:1).slice(0,limit);
 for(const w of todo){try{
  const rows=w.leaves.map(r=>{const p=pins[r.git_blob_sha1];if(!p||p.bytes!==r.bytes)throw Error("leaf pin");return{...r,sha256:p.sha256,encoding:"utf-8",origin:"unchanged-original-archive-leaf"};});
  for(const [path,raw]of Object.entries(A.metadata(w))){
   const bytes=H.utf8(raw),sha=H.gitBlob(bytes),pin={path,bytes:bytes.length,sha256:H.sha256(bytes),git_blob_sha1:sha,mode:"100644",encoding:"utf-8",origin:path==="_dependency-mounts.json"?"derived-canonical-dependency-mounts":"derived-original-tree-reconstruction"};
   if(!derived[sha]){
    const intent={operation:"create_blob",package:w.name,path,sha,bytes:bytes.length,state:"PENDING"};intents.push(intent);set("cp23:mutation-intents",intents);
    if(await createBlob(raw)!==sha)throw Error("metadata response SHA");intent.state="CONFIRMED";derived[sha]={raw,...pin};set("cp23:derived-blobs",derived);set("cp23:mutation-intents",intents);
   }
   rows.push(pin);
  }
  rows.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
  const expected=A.normalizedTree(rows),intent={operation:"create_tree",package:w.name,sha:expected.sha,leaf_count:rows.length,state:"PENDING"};intents.push(intent);set("cp23:mutation-intents",intents);
  if(await createTree(rows.map(row=>({path:row.path,mode:row.mode,type:"blob",sha:row.git_blob_sha1})))!==expected.sha)throw Error("normalized tree response SHA");
  intent.state="CONFIRMED";set("cp23:mutation-intents",intents);
  normal[w.name]={name:w.name,original_tree:w.original_tree,normalized_tree:expected.sha,aliases:w.aliases,files:rows.length,retained_original_leaf_count:w.leaves.length,dependency_cuts:w.cuts,rows,expected,readback_complete:false};set("cp23:normalized",normal);
 }catch(e){errors.push({name:w.name,error:String(e)});set("cp23:normalization-errors",errors);break;}}
 const entries=Object.values(normal).sort((a,b)=>a.name<b.name?-1:1).map(p=>({name:p.name,path:p.name,mode:"040000",type:"tree",sha:p.normalized_tree})),expected=H.treeHash(entries);
 if(await createTree(entries.map(({path,mode,type,sha})=>({path,mode,type,sha})))!==expected)throw Error("partial package root");
 const progress={schema:"cp23-normalization-progress-v1",seed_blob:"e605c10d5e7637061e6e7adcb4f6663d966679e5",normalized_packages:Object.keys(normal).length,required_packages:239,partial_packages_tree:expected,all_original_1367_blobs_verified:true,original_leaf_bytes_unchanged:true,packages:Object.values(normal),errors,metadata_full_readback_pending:true};
 const raw=JSON.stringify(progress,null,2)+"\n",sha=H.gitBlob(H.utf8(raw));if(await createBlob(raw)!==sha)throw Error("progress save");
 const tree=await createTree([{path:"packages",mode:"040000",type:"tree",sha:expected},{path:"normalization-progress.json",mode:"100644",type:"blob",sha},{path:"assembly.js",mode:"100644",type:"blob",sha:get("cp23:assembly-helper-blob")},{path:"normalize-batch.js",mode:"100644",type:"blob",sha:get("cp23:normalization-driver-blob")}]);
 const checkpoint={tree,packages_tree:expected,blob:sha,bytes:H.utf8(raw).length,sha256:H.sha256(H.utf8(raw))};set("cp23:normalization-checkpoint-"+Object.keys(normal).length,checkpoint);
 return {normalized_packages:Object.keys(normal).length,derived_blobs:Object.keys(derived).length,checkpoint,errors};
})