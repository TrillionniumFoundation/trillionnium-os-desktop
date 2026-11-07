function cp24Index(U,parentPin,rows){
 const need=(x,m)=>{if(!x)throw Error(m);};
 const indexPath="checkpoint24/payload-index.json";
 need(rows.every(r=>r.path.startsWith("checkpoint24/")&&r.path!==indexPath&&r.mode==="100644"&&Number.isSafeInteger(r.bytes)&&r.bytes>=0&&/^[0-9a-f]{64}$/.test(r.sha256)&&/^[0-9a-f]{40}$/.test(r.git_blob_sha1)),"exact new rows");
 need(new Set(rows.map(r=>r.path)).size===rows.length,"unique new paths");
 const sorted=[...rows].sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
 const index={schema:"pocket4-r11-payload-index-v24",checkpoint:24,cut_utc:"2026-11-07 00:12:51 UTC",base_commit:"32df6ea6403c24588638e3fbbfe6edc1897393e9",base_manifest:parentPin,index_self_excluded:true,index_path:indexPath,indexed_files:sorted.length,payload_files_including_index:sorted.length+1,indexed_bytes:sorted.reduce((n,r)=>n+r.bytes,0),authorized_original_archive_roots:157,normalized_packages_tree:"4e85b20e71474b010b79fda0c2a4213fdd22d25d",Root_status_merged:true,files:sorted};
 const raw=JSON.stringify(index,null,2)+"\n", b=U.utf8(raw);
 return {raw,row:{path:indexPath,mode:"100644",bytes:b.length,sha256:U.sha256(b),git_blob_sha1:U.gitBlob(b),encoding:"utf-8",origin:"Root-complete-checkpoint-index"},rows:sorted};
}
function cp24Master(U,M,parentRaw,parentPin,newRows,statusRaw,payloadTree){
 const need=(x,m)=>{if(!x)throw Error(m);};
 const b=U.utf8(parentRaw);need(b.length===parentPin.bytes&&U.sha256(b)===parentPin.sha256&&U.gitBlob(b)===parentPin.git_blob_sha1,"whole parent manifest");
 const original=M.rootMembers(parentRaw),old=JSON.parse(parentRaw),status=JSON.parse(statusRaw);
 need(old.checkpoint===23&&old.files.length===21330&&old.files_excluding_manifest===21330&&old.bytes_excluding_manifest===484138191,"exact parent");
 need(status.checkpoint===24&&status.cut_utc==="2026-11-07 00:12:51 UTC"&&status.whole_apps_ready===0&&status.apps_in_scope===45&&status.Main_deployed===false&&status.current_Main_runtime_admitted===false,"Root fixed cut status");
 need(/^[0-9a-f]{40}$/.test(payloadTree)&&newRows.every(r=>r.path.startsWith("checkpoint24/")),"new payload only");
 need(new Set([...old.files.map(r=>r.path),...newRows.map(r=>r.path)]).size===old.files.length+newRows.length,"no historical path replacement");
 const oldFiles=original.members.get("files").raw;need(oldFiles.endsWith("]"),"original file array");
 const sorted=[...newRows].sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
 const nextFiles=oldFiles.slice(0,-1)+","+JSON.stringify(sorted,null,2).slice(1);
 const values={checkpoint:24,base_commit:"32df6ea6403c24588638e3fbbfe6edc1897393e9",base_tree:"8519cd805a36d5b17c24f664721734d38a09f730",previous_manifest_sha256:parentPin.sha256,inherited_payload_files:old.files.length,new_payload_files:sorted.length,new_payload_bytes:sorted.reduce((n,r)=>n+r.bytes,0),files_excluding_manifest:old.files.length+sorted.length,bytes_excluding_manifest:old.bytes_excluding_manifest+sorted.reduce((n,r)=>n+r.bytes,0),current_status_key:"checkpoint24",checkpoint24_snapshot_utc:"2026-11-07 00:12:51 UTC",checkpoint24_payload_tree_sha:payloadTree};
 const updates=Object.fromEntries(Object.entries(values).map(([k,x])=>[k,JSON.stringify(x)]));updates.files=nextFiles;updates.checkpoint24=statusRaw.trimEnd();
 const raw=M.updateRootPreservingHistoricalBytes(parentRaw,updates),checked=M.rootMembers(raw);
 need(checked.members.get("files").raw.startsWith(oldFiles.slice(0,-1)),"original file-array prefix byte-identical");
 for(const[k,r]of original.members)if(!(k in updates))need(checked.members.get(k).raw===r.raw,"untouched historical field "+k);
 const check=JSON.parse(raw);need(check.files.length===values.files_excluding_manifest&&check.files.reduce((n,r)=>n+r.bytes,0)===values.bytes_excluding_manifest,"full manifest totals");
 return {raw,updated_root_fields:Object.keys(updates),historical_root_fields_preserved:[...original.members.keys()].filter(k=>!(k in updates)),historical_file_rows_preserved:old.files.length,added_file_rows:sorted.length,total_file_rows:check.files.length,total_logical_bytes:values.bytes_excluding_manifest};
}
