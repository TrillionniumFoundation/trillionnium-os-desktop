(function makeCp24GitAdapter(tools,H,A,get,set,collectorSourceTree) {
"use strict";
const repository="TrillionniumFoundation/trillionnium-os-desktop";
const need=(x,m)=>{if(!x)throw Error(m);};
const isSHA=x=>typeof x==="string"&&/^[0-9a-f]{40}$/.test(x);
need(isSHA(collectorSourceTree)&&typeof get==="function"&&typeof set==="function","fixed collector source and state adapters");
async function blob(sha) {
 need(isSHA(sha),"exact blob SHA");
 const result=await tools.mcp__codex_apps__github_fetch_blob({repository_full_name:repository,blob_sha:sha});
 const raw=result&&result.structuredContent&&result.structuredContent.content;
 need(typeof raw==="string","complete UTF8 original blob unavailable");
 need(H.gitBlob(H.utf8(raw))===sha,"complete original Git blob mismatch");
 return raw;
}
async function tree(sha,recursive=false) {
 need(isSHA(sha)&&typeof recursive==="boolean","exact tree SHA");
 const result=await tools.mcp__codex_apps__github_fetch({
  url:"https://api.github.com/repos/"+repository+"/git/trees/"+sha+(recursive?"?recursive=1":"")});
 const raw=result&&result.structuredContent&&result.structuredContent.content;
 need(typeof raw==="string","complete Git tree response unavailable");
 const value=JSON.parse(raw);
 need(value.sha===sha&&value.truncated===false&&Array.isArray(value.tree),"exact untruncated Git tree");
 return value;
}
async function createBlob(raw) {
 need(typeof raw==="string","immutable UTF8 blob body");
 const expected=H.gitBlob(H.utf8(raw));
 const r=await tools.mcp__codex_apps__github_create_blob({repository_full_name:repository,content:raw,encoding:"utf-8"});
 need(r&&r.structuredContent&&r.structuredContent.sha===expected,"immutable blob response mismatch");
 return expected;
}
async function createTree(entries) {
 need(Array.isArray(entries)&&entries.every(x=>typeof x.path==="string"&&x.path.length>0&&
  !/[\\\x00]/.test(x.path)&&x.path.split("/").every(p=>p&&p!=="."&&p!=="..")&&
  isSHA(x.sha)&&((x.mode==="100644"&&x.type==="blob")||(x.mode==="040000"&&x.type==="tree"))),
  "exact immutable tree entries");
 const r=await tools.mcp__codex_apps__github_create_tree({repository_full_name:repository,tree_elements:entries});
 need(r&&r.structuredContent&&isSHA(r.structuredContent.sha),"immutable tree response required");
 return r.structuredContent.sha;
}
async function persist(label,state,mounts=[]) {
 need(/^[a-z0-9][a-z0-9-]{0,63}$/.test(label),"fixed progress label");
 need(!get("cp24:pending-immutable-write"),"prior immutable write outcome requires explicit readback");
 need(state&&state.seed_pin&&isSHA(state.seed_pin.git_blob_sha1),"bound original seed pin");
 const raw=JSON.stringify(state,null,2)+"\n",bytes=H.utf8(raw);
 const pin={bytes:bytes.length,sha256:H.sha256(bytes),git_blob_sha1:H.gitBlob(bytes)};
 const entries=[
  {path:label+".json",mode:"100644",type:"blob",sha:pin.git_blob_sha1},
  {path:"fixed-seed.json",mode:"100644",type:"blob",sha:state.seed_pin.git_blob_sha1},
  {path:"collector-source",mode:"040000",type:"tree",sha:collectorSourceTree},
  ...mounts];
 need(new Set(entries.map(x=>x.path)).size===entries.length&&
  entries.every(x=>!x.path.includes("/")),"flat progress mount names");
 const expectedTree=H.treeHash(entries.map(({path,...row})=>({name:path,...row})));
 const intent={label,blob:pin,tree:expectedTree,state:"PENDING_IMMUTABLE_RESPONSE",
  no_ref_change:true,do_not_replay_unknown_mutation:true};
 set("cp24:pending-immutable-write",intent);
 await createBlob(raw);
 need(await blob(pin.git_blob_sha1)===raw,"progress blob exact readback");
 need(await createTree(entries)===expectedTree,"progress tree response");
 A.shallow(await tree(expectedTree),expectedTree);
 set("cp24:pending-immutable-write",null);
 const receipt={tree:expectedTree,...pin,raw_original_seed_retained:true,
  immutable_tree_readback_complete:true,source_tree:collectorSourceTree,no_ref_change:true};
 set("cp24:last-durable-progress",receipt);
 return receipt;
}
return {get,set,blob,tree,createBlob,createTree,persist,collectorSourceTree};
})
