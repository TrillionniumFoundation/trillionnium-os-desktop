function verifySource(files,H) {
  const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const pin=s=>{const b=H.utf8(s);return {bytes:b.length,sha256:H.sha256(b),git_blob_sha1:H.gitBlob(b)};};
  const edits=JSON.parse(files["exact-edits.json"]);
  for(const path of Object.keys(edits.edits)) {
    let raw=files["candidate/"+path];
    if(!equal(pin(raw),edits.candidates[path]))throw Error("candidate pin "+path);
    for(const e of edits.edits[path].slice().reverse()) {
      if(raw.split(e.after).length!==2)throw Error("ambiguous inverse "+e.label);
      raw=raw.replace(e.after,e.before);
    }
    if(raw!==files["baseline/"+path]||!equal(pin(raw),edits.bases[path]))throw Error("inverse "+path);
  }
  const old=JSON.parse(files["baseline/actual470-source-manifest.json"]);
  const current=JSON.parse(files["expected-source-manifest.json"]);
  const scope=JSON.parse(files["build-scope.json"]);
  const changed=Object.keys(old).filter(p=>!equal(old[p],current[p]));
  const added=Object.keys(current).filter(p=>!old[p]);
  if(Object.keys(old).length!==499||Object.keys(current).length!==500||changed.length!==10||added.length!==1)throw Error("map counts");
  if(!equal(changed.slice().sort(),scope.map_delta_from_actual470.replaced.slice().sort())||!equal(added,scope.map_delta_from_actual470.added))throw Error("map classification");
  for(const [key,value]of Object.entries(files))if(key.startsWith("candidate/")){
    const path=key.slice(10),observed=pin(value);
    if(!current[path]||current[path].bytes!==observed.bytes||current[path].sha256!==observed.sha256)throw Error("candidate map "+path);
  }
  for(const row of scope.complete_ACK_production_inputs){
    const observed=pin(files["candidate/"+row.path]);
    if(observed.bytes!==row.bytes||observed.sha256!==row.sha256||observed.git_blob_sha1!==row.git_blob_sha1)throw Error("ACK "+row.path);
  }
  if(current[scope.source_lock.path].sha256!=="72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d")throw Error("wrong lock");
  return {source_only:true,exact_inverse:true,old_rows:499,new_rows:500,unchanged:489,replaced:10,added:1,ACK9_exact:true,Rust_executed:false,Soong_executed:false};
}
