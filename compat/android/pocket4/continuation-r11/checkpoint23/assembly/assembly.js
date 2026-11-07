(function(H) {
"use strict";
const need=(v,m)=>{if(!v)throw Error(m);};
function canonical(seed) {
 need(seed.schema==="root-checkpoint23-fixed-seed-v1"&&seed.cut_utc==="2026-11-06 21:56:09 UTC","fixed seed");
 need(seed.new_roots.length===239&&seed.canonical_inherited_roots.length===695,"root counts");
 const roots=new Map(),names=new Set();
 for(const row of seed.canonical_inherited_roots){need(!roots.has(row.original_tree),"duplicate inherited SHA");roots.set(row.original_tree,{...row,kind:"inherited"});}
 for(const row of seed.new_roots){
  need(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(row.name)&&!names.has(row.name),"new package name");
  need(/^[0-9a-f]{40}$/.test(row.original_tree)&&!roots.has(row.original_tree),"new root collision");
  names.add(row.name);roots.set(row.original_tree,{...row,checkpoint:23,kind:"new"});
 }
 return roots;
}
function shallow(raw,sha) {
 const object=typeof raw==="string"?JSON.parse(raw):raw;
 need(object.sha===sha&&object.truncated===false&&Array.isArray(object.tree),"shallow tree identity/truncation");
 const seen=new Set();
 const entries=object.tree.map(e=>{
  need(typeof e.path==="string"&&e.path&&e.path!=="."&&e.path!==".."&&!/[\\/\x00]/.test(e.path)&&!seen.has(e.path),"shallow tree name");seen.add(e.path);
  need(/^[0-9a-f]{40}$/.test(e.sha),"entry SHA");
  need((e.type==="tree"&&e.mode==="040000")||(e.type==="blob"&&e.mode==="100644"),"entry type/mode");
  if(e.type==="blob")need(Number.isSafeInteger(e.size)&&e.size>=0,"leaf advertised size");
  return {name:e.path,mode:e.mode,type:e.type,sha:e.sha,...(e.type==="blob"?{size:e.size}:{})};
 });
 need(H.treeHash(entries)===sha,"original directory Merkle mismatch "+sha);
 return {sha,entries};
}
async function traverse(root,roots,getShallow) {
 const directories=[],leaves=[],cuts=[],visiting=new Set();
 async function visit(sha,path,depth) {
  need(depth<=64&&!visiting.has(sha),"tree depth/cycle");
  const cut=path?roots.get(sha):null;
  if(cut){cuts.push({path,tree_sha:sha,checkpoint:cut.checkpoint,canonical_package:cut.name});return;}
  visiting.add(sha);
  const dir=await getShallow(sha);
  need(dir.sha===sha,"cached shallow SHA");
  directories.push({path,sha,entries:dir.entries.map(({name,mode,type,sha})=>({name,mode,type,sha}))});
  need(directories.length<=100000,"directory count");
  for(const e of dir.entries){
   const p=path?path+"/"+e.name:e.name;
   if(e.type==="tree")await visit(e.sha,p,depth+1);
   else {leaves.push({path:p,mode:e.mode,git_blob_sha1:e.sha,bytes:e.size});need(leaves.length<=100000,"leaf count");}
  }
  visiting.delete(sha);
 }
 await visit(root.original_tree,"",0);
 const order=(a,b)=>a.path<b.path?-1:a.path>b.path?1:0;
 directories.sort(order);leaves.sort(order);cuts.sort(order);
 need(!leaves.some(e=>e.path==="_original-tree.json"||e.path==="_dependency-mounts.json"),"reserved metadata collision");
 return {name:root.name,original_tree:root.original_tree,aliases:[root.name,...(root.aliases||[])],directories,leaves,cuts};
}
function metadata(walk) {
 const dep={schema:3,original_tree:walk.original_tree,canonical_root_key:"original_tree_sha",cuts:walk.cuts,scope:"Reconstruct each omitted directory from its exact canonical checkpoint package and recursively apply that package metadata; all original file body bytes are unchanged."};
 const original={schema:3,original_tree:walk.original_tree,derived_reconstruction_map:true,not_original_API_response_bytes:true,directories:walk.directories,retained_leaf_count:walk.leaves.length,retained_body_bytes_unchanged:true};
 return {"_dependency-mounts.json":JSON.stringify(dep,null,2)+"\n","_original-tree.json":JSON.stringify(original,null,2)+"\n"};
}
function verifyBlob(raw,sha,size) {
 need(typeof raw==="string","blob is not text");
 const bytes=H.utf8(raw);
 need(bytes.length===size&&H.gitBlob(bytes)===sha,"blob full UTF8 size/Git mismatch "+sha);
 return {bytes:bytes.length,sha256:H.sha256(bytes),git_blob_sha1:sha,encoding:"utf-8"};
}
function normalizedTree(rows) {
 const dirs=new Map([["",[]]]),paths=new Set();
 for(const row of rows) {
  need(!paths.has(row.path)&&row.mode==="100644"&&/^[0-9a-f]{40}$/.test(row.git_blob_sha1),"normalized leaf collision/mode");paths.add(row.path);
  const parts=row.path.split("/");need(parts.every(p=>p&&p!=="."&&p!==".."),"normalized path");
  for(let i=1;i<parts.length;i++){const d=parts.slice(0,i).join("/");if(!dirs.has(d))dirs.set(d,[]);}
  const parent=parts.slice(0,-1).join("/");
  dirs.get(parent).push({name:parts.at(-1),type:"blob",mode:"100644",sha:row.git_blob_sha1});
 }
 const hashes=new Map();
 for(const path of [...dirs.keys()].sort((a,b)=>b.split("/").length-a.split("/").length||b.length-a.length)){
  const sha=H.treeHash(dirs.get(path));hashes.set(path,sha);
  if(path){const parts=path.split("/"),parent=parts.slice(0,-1).join("/");dirs.get(parent).push({name:parts.at(-1),type:"tree",mode:"040000",sha});}
 }
 return {sha:hashes.get(""),directory_count:dirs.size,leaf_count:rows.length,logical_bytes:rows.reduce((n,r)=>n+r.bytes,0)};
}
return {canonical,shallow,traverse,metadata,verifyBlob,normalizedTree};
})