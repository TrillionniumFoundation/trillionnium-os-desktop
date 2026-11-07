"use strict";
function assembleCatalogPublicSource(manifestRaw,scopeRaw,bodies,H){
  const need=(ok,why)=>{if(!ok)throw new Error(why);};
  need(typeof manifestRaw==="string"&&H.utf8(manifestRaw).length===103724&&H.sha(manifestRaw)==="9ff887e3edd168647ebe8c11c4ae904a5fc7e404aef8c67266d82355c21591f8"&&H.git(manifestRaw)==="273774e0c102c0c511ffbd52b72d27731d964235","CURRENT_UNIFIED518_REQUIRED");
  need(typeof scopeRaw==="string"&&H.utf8(scopeRaw).length===49134&&H.sha(scopeRaw)==="e0ebc9359ae7ac6347ec5d2053943e8b846b5e43f30b8786c73c64783c98caff"&&H.git(scopeRaw)==="5a9527a77c552e085c171b4f21d59feab509f822","FIXED_SOURCE_SCOPE_REQUIRED");
  const manifest=JSON.parse(manifestRaw),scope=JSON.parse(scopeRaw),expected=new Map(scope.paths.map(r=>[r.path,r]));
  need(expected.size===211&&scope.workspace_members.length===28&&Object.keys(manifest).length===518,"EXACT_OBSERVED_SCOPE_REQUIRED");
  need(bodies&&typeof bodies==="object"&&!Array.isArray(bodies),"BODY_MAP_REQUIRED");
  const actualKeys=Object.keys(bodies);need(actualKeys.every(p=>expected.has(p)),"UNDECLARED_BODY_REJECTED");
  const verified=[],missing=[];
  for(const[path,row]of expected){
    need(!path.startsWith("/")&&!path.split("/").some(x=>x==="."||x===".."||x===".git")&&!path.endsWith("m831-provenance.json"),"PRIVATE_OR_UNSAFE_PATH_REJECTED");
    need(manifest[path]&&manifest[path].kind==="file"&&manifest[path].bytes===row.bytes&&manifest[path].sha256===row.sha256&&manifest[path].mode===row.observed_mode,"SCOPE_MANIFEST_DISAGREEMENT");
    if(!Object.prototype.hasOwnProperty.call(bodies,path)){missing.push(row);continue;}
    const raw=bodies[path];need(typeof raw==="string"&&H.utf8(raw).length===row.bytes&&H.sha(raw)===row.sha256,"SOURCE_BODY_PIN:"+path);
    verified.push({path,bytes:row.bytes,sha256:row.sha256,git_blob:H.git(raw),git_mode:(row.observed_mode&73)?"100755":"100644"});
  }
  const result={schema:"pocket4-public-catalog-source-assembly-v1",state:missing.length?"INCOMPLETE_NO_SOURCE_TREE":"COMPLETE_BYTES_NOT_A_NEW_BUILD",scope_blob:H.git(scopeRaw),source_root:scope.source_root,expected_leaves:211,verified_leaves:verified.length,missing,all_original28_member_manifests_exact:scope.workspace_members.every(p=>verified.some(x=>x.path===p+"/Cargo.toml")),actual47_selected40_exact:scope.selected_actual47_files.every(p=>verified.some(x=>x.path===p)),git_tree_elements:null,source_subtree_sha:null,ref_changed:false,build_executed:false,entire_workspace_tests_or_packager_qualified:false,Main_or_Android_actions:0};
  if(missing.length)return result;
  // Audit only literal compile includes. Unsupported syntax requires explicit review.
  const normalize=parts=>{const out=[];for(const p of parts.split("/")){if(p===".."){need(out.length>0,"COMPILE_INCLUDE_ESCAPE");out.pop();}else if(p&&p!==".")out.push(p);}return out.join("/");};
  const includeEdges=[];
  for(const[path,raw]of Object.entries(bodies)){
    if(!path.endsWith(".rs"))continue;
    const complete=[...raw.matchAll(/\b(include_str|include_bytes|include)\s*!\s*\(\s*"([^"]+)"\s*\)/g)];
    const all=[...raw.matchAll(/\b(include_str|include_bytes|include)\s*!/g)];
    need(all.length===complete.length,"NONLITERAL_INCLUDE_REQUIRES_REVIEW:"+path);
    for(const match of complete){
      const literal=match[2];
      need(!literal.startsWith("/")&&!/^[A-Za-z]:/.test(literal)&&!literal.includes("\\")&&!/[\x00-\x1f\x7f]/.test(literal),"UNSUPPORTED_COMPILE_INCLUDE_PATH:"+path);
      const target=normalize(path.slice(0,path.lastIndexOf("/")+1)+literal);
      need(expected.has(target),"NEW_COMPILE_INCLUDE_REQUIRED:"+target);
      includeEdges.push({source:path,macro:match[1],target});
    }
  }
  const nodes={};
  for(const row of verified){let n=nodes;const parts=row.path.split("/");for(const p of parts.slice(0,-1))n=n[p]??={};n[parts.at(-1)]={leaf:row};}
  const hashNode=n=>H.treeHash(Object.entries(n).map(([name,v])=>v.leaf?{name,mode:v.leaf.git_mode,type:"blob",sha:v.leaf.git_blob}:{name,mode:"40000",type:"tree",sha:hashNode(v)}));
  result.source_subtree_sha=hashNode(nodes);result.git_tree_elements=verified.map(r=>({path:scope.source_root+r.path,mode:r.git_mode,type:"blob",sha:r.git_blob}));result.literal_compile_include_edges=includeEdges;
  result.notes=["Source Git executable bit follows observed mode; this is not runtime metadata replacement.","Original28 Cargo.toml/Cargo.lock are exact bytes; registry/platform dependencies remain external.","Generated tree entries are data only. The caller still must review a fixed branch base and explicitly perform publication; this function has no tool, filesystem, process or ref capability.","The independent366B source rc is the SDK03 source input. The367B deployment rc and1020B bridge copy remain separate reviewed derivations."];
  return result;
}
