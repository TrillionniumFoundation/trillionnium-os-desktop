(function finalizeCp24(H,A,input,collection,normalization) {
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const SEED="73cd8ae3a9ba939b616028c4b7218e93913faeb1";
const AUTH={bytes:864,sha256:"8fb88ad0d45f2349ac884d6595b071812d5cd3ccec4651601f2a6d136e28052c",git_blob_sha1:"fae290f2ba66ed9ac5afb01280c0e97b7e1501b8"};
const pin=raw=>{const b=H.utf8(raw);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
const samePin=(a,b)=>a&&b&&a.bytes===b.bytes&&a.sha256===b.sha256&&a.git_blob_sha1===b.git_blob_sha1;
const textPin=(raw,expected,label)=>{need(typeof raw==="string"&&samePin(pin(raw),expected),label+" whole original pin");return JSON.parse(raw);};
const authority=textPin(input.authority_raw,AUTH,"root authority");
need(authority.seed.git_blob_sha1===SEED&&authority.cut_utc==="2026-11-07 00:12:51 UTC"&&authority.new_root_count===157&&authority.inherited_root_count===934,"exact CP24 grant");
const binding=A.bindSeed(input.seed_raw,authority,input.parent_cut_raw);
const seed=binding.seed,parent=JSON.parse(input.parent_cut_raw);
for(const [label,state] of [["collection",collection],["normalization",normalization]]) {
 need(state&&state.checkpoint===24&&samePin(state.seed_pin,authority.seed)&&state.cut_utc===authority.cut_utc,label+" seed/cut");
 need(Array.isArray(state.errors)&&state.errors.length===0,label+" errors");
}
need(collection.collection_complete===true&&normalization.normalization_complete===true,"both phases complete");
need(collection.required_new_roots===157&&collection.inherited_canonical_roots===934&&normalization.required_packages===157&&normalization.normalized_packages===157,"exact phase counts");
const sortedNames=seed.new_roots.map(r=>r.name).sort();
need(eq(Object.keys(collection.walks).sort(),sortedNames)&&eq(Object.keys(normalization.packages).sort(),sortedNames),"exact package set");
const combined=[],packages=[],reconstruction=[],usedBlobs=new Set(),usedMetadata=new Set(),uniqueDirectories=new Set(),expectedArchives=[];
let originalLeaves=0,originalBytes=0,directoryOccurrences=0,cutCount=0,inheritedCuts=0,newCuts=0;
for(const name of sortedNames) {
 const root=seed.new_roots.find(r=>r.name===name),walk=collection.walks[name],p=normalization.packages[name];
 need(walk.name===name&&walk.original_tree===root.original_tree&&p.name===name&&p.original_tree===root.original_tree,"package identity "+name);
 need(eq(walk.aliases,[name,...(root.aliases||[])])&&eq(p.aliases,walk.aliases)&&eq(p.dependency_cuts,walk.cuts),"package aliases/cuts "+name);
 const dirs=new Map(),leaves=new Map(),cuts=new Map();
 for(const d of walk.directories){need(!dirs.has(d.path),"duplicate directory");dirs.set(d.path,d);}
 for(const r of walk.leaves){need(!leaves.has(r.path),"duplicate original leaf");leaves.set(r.path,r);}
 for(const c of walk.cuts){need(!cuts.has(c.path)&&c.path!==""&&!dirs.has(c.path)&&!leaves.has(c.path),"cut collision");cuts.set(c.path,c);}
 need(dirs.has("")&&dirs.get("").sha===root.original_tree,"original root directory");
 const seenDirs=new Set([""]),seenLeaves=new Set(),seenCuts=new Set();
 for(const d of walk.directories) {
  need(H.treeHash(d.entries)===d.sha,"original directory Merkle "+name+"/"+d.path);
  const cached=collection.directory_cache[d.sha];
  need(cached&&cached.sha===d.sha&&H.treeHash(cached.entries)===d.sha,"original cached directory");
  const eNames=new Set();
  for(const e of d.entries) {
   need(!eNames.has(e.name)&&e.name!==""&&e.name!=="."&&e.name!==".."&&!/[\\/\x00]/.test(e.name),"original entry name");eNames.add(e.name);
   const path=d.path?d.path+"/"+e.name:e.name;
   if(e.type==="blob") {
    const r=leaves.get(path);need(e.mode==="100644"&&r&&r.mode===e.mode&&r.git_blob_sha1===e.sha&&!seenLeaves.has(path),"original leaf edge");
    const advertised=cached.entries.find(x=>x.name===e.name);
    need(advertised&&advertised.type==="blob"&&advertised.sha===e.sha&&advertised.size===r.bytes,"original advertised leaf size");
    seenLeaves.add(path);
   } else {
    need(e.type==="tree"&&e.mode==="040000","original entry kind");
    const grant=binding.roots.get(e.sha);
    if(grant) {
     const c=cuts.get(path);need(c&&c.tree_sha===e.sha&&c.checkpoint===grant.checkpoint&&c.canonical_package===grant.name&&!seenCuts.has(path),"exact canonical cut edge");
     seenCuts.add(path);
    } else {
     const child=dirs.get(path);need(child&&child.sha===e.sha&&!seenDirs.has(path),"traversed directory edge");seenDirs.add(path);
    }
   }
  }
  uniqueDirectories.add(d.sha);
 }
 need(seenDirs.size===dirs.size&&seenLeaves.size===leaves.size&&seenCuts.size===cuts.size,"all original entries reconstructed");
 const expectedRows=[];
 for(const r of walk.leaves) {
  const q=collection.blob_pins[r.git_blob_sha1];
  need(q&&q.git_blob_sha1===r.git_blob_sha1&&q.bytes===r.bytes&&q.encoding==="utf-8"&&q.full_original_body_read===true&&Number.isSafeInteger(q.bytes)&&q.bytes>=0&&/^[0-9a-f]{64}$/.test(q.sha256),"original full body qualification");
  expectedRows.push({path:r.path,mode:r.mode,bytes:q.bytes,sha256:q.sha256,git_blob_sha1:q.git_blob_sha1,encoding:"utf-8",origin:"unchanged-original-archive-leaf"});
  usedBlobs.add(r.git_blob_sha1);originalLeaves++;originalBytes+=q.bytes;
 }
 const derived=A.metadata(walk);
 need(eq(Object.keys(derived).sort(),["_dependency-mounts.json","_original-tree.json"].sort()),"exact two metadata files");
 for(const [path,raw] of Object.entries(derived)) {
  const q=pin(raw),known=normalization.derived_blobs[q.git_blob_sha1];
  const origin=path==="_dependency-mounts.json"?"derived-canonical-dependency-mounts":"derived-original-tree-reconstruction";
  need(known&&samePin(known,q)&&known.path===path&&known.mode==="100644"&&known.origin===origin&&known.encoding==="utf-8"&&known.full_readback_complete===true,"derived metadata exact readback");
  expectedRows.push({path,mode:"100644",...q,encoding:"utf-8",origin});usedMetadata.add(q.git_blob_sha1);
 }
 expectedRows.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
 need(eq(p.rows,expectedRows),"complete normalized file index "+name);
 const computed=A.normalizedTree(expectedRows);
 need(p.readback_complete===true&&eq(p.expected,computed)&&p.normalized_tree===computed.sha&&p.files===computed.leaf_count&&p.retained_original_leaf_count===walk.leaves.length,"normalized package full Merkle "+name);
 for(const row of expectedRows)combined.push({...row,path:name+"/"+row.path});
 packages.push({name,original_tree:root.original_tree,normalized_tree:p.normalized_tree,aliases:p.aliases,files:p.files,retained_original_leaf_count:p.retained_original_leaf_count,dependency_cuts:p.dependency_cuts});
 reconstruction.push({name,original_tree:root.original_tree,original_directories:walk.directories.length,retained_original_leaves:walk.leaves.length,canonical_cuts:walk.cuts.length,all_original_directory_merkle_and_edges_verified:true});
 directoryOccurrences+=walk.directories.length;cutCount+=walk.cuts.length;
 for(const c of walk.cuts){if(c.checkpoint===24)newCuts++;else inheritedCuts++;}
 expectedArchives.push(...A.archiveReferenceDocuments(walk,collection.blob_pins));
}
need(eq([...usedBlobs].sort(),Object.keys(collection.blob_pins).sort()),"no unused or omitted original blob qualification");
need(eq([...usedMetadata].sort(),Object.keys(normalization.derived_blobs).sort()),"no unused or omitted derived metadata");
need(usedMetadata.size===314&&originalLeaves===970&&usedBlobs.size===731,"collected exact counts");
const archiveSort=x=>[...x].sort((a,b)=>(a.original_tree+"/"+a.path).localeCompare(b.original_tree+"/"+b.path));
need(eq(archiveSort(expectedArchives),archiveSort(collection.archive_reference_documents))&&eq(archiveSort(expectedArchives),archiveSort(normalization.archive_reference_documents)),"all opaque archive references retained");
need(expectedArchives.length===33&&expectedArchives.every(x=>x.JSON_links_followed===0&&x.roots_authorized_by_document===0),"no JSON authority traversal");
combined.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
const whole=A.normalizedTree(combined);
need(whole.sha===normalization.packages_tree&&whole.leaf_count===1284,"complete packages Merkle");
const children=packages.map(p=>({name:p.name,mode:"040000",type:"tree",sha:p.normalized_tree}));
need(H.treeHash(children)===whole.sha,"independent package children Merkle");
const counts={new_original_roots:157,inherited_canonical_roots:934,canonical_roots_after:1091,unique_original_blobs:usedBlobs.size,retained_original_leaf_occurrences:originalLeaves,retained_original_body_bytes:originalBytes,original_directory_occurrences:directoryOccurrences,unique_original_directory_shas:uniqueDirectories.size,canonical_cut_occurrences:cutCount,inherited_cut_occurrences:inheritedCuts,new_cut_occurrences:newCuts,opaque_archive_reference_documents:expectedArchives.length,JSON_links_followed:0,derived_metadata_blobs:usedMetadata.size,normalized_files:whole.leaf_count,normalized_logical_bytes:whole.logical_bytes,normalized_directories:whole.directory_count};
need(originalBytes===22312403&&directoryOccurrences===299&&uniqueDirectories.size===272&&cutCount===116&&inheritedCuts===10&&newCuts===106,"original collection totals");
const fileIndex={schema:"pocket4-r11-cp24-payload-index-v3",checkpoint:24,cut_utc:authority.cut_utc,package_tree:whole.sha,path_prefix:"checkpoint24/packages/",counts,files:combined.map(r=>({...r,path:"checkpoint24/packages/"+r.path}))};
const cutScope={schema:"pocket4-r11-cp24-canonical-root-cut-v3",checkpoint:24,cut_utc:authority.cut_utc,package_tree:whole.sha,packages,canonical_inherited_roots:seed.canonical_inherited_roots,normalization_rule:parent.normalization_rule,fixed_seed:{tree:"fac50d780b8ca143fd41f7e9e067a5f7b04c00de",...authority.seed},root_authority:AUTH,previous_cut_scope:authority.previous_cut_scope,previous_master:authority.previous_master,byte_identical_source_and_evidence:true,public_nonce_pool_source_leaves_preserved_byte_identically:true,nonce_pool_contents_not_printed:true,archive_reference_JSON_is_opaque:true,JSON_links_followed:0,root_seed_privacy:seed.privacy,root_seed_scope_interpretation:seed.scope_interpretation,status_scope:"Root-authored fixed seed is retained verbatim. This assembly adds no operational status or acceptance claims.",parent_master_full_body_verified_by_this_assembler:false};
const proof={schema:"pocket4-r11-cp24-original-reconstruction-proof-v1",checkpoint:24,cut_utc:authority.cut_utc,seed_pin:authority.seed,packages_tree:whole.sha,counts,packages:reconstruction,all_original_leaf_pins_fullread:true,all_derived_metadata_regenerated_exactly:true,all_original_directory_merkle_and_edges_verified:true,all_normalized_package_merkle_verified:true,source_and_evidence_leaf_bodies_modified:0,JSON_links_followed:0,parent_master_full_body_verified_by_this_assembler:false,no_Hepta:true,no_ref_change:true};
const raws={"payload-index.json":JSON.stringify(fileIndex,null,2)+"\n","cut-scope.json":JSON.stringify(cutScope,null,2)+"\n","original-reconstruction-proof.json":JSON.stringify(proof,null,2)+"\n"};
return {counts,packages_tree:whole.sha,package_rows:combined,files:raws,pins:Object.fromEntries(Object.entries(raws).map(([path,raw])=>[path,pin(raw)]))};
})