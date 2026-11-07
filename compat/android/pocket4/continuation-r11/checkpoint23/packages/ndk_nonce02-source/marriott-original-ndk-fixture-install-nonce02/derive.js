// Pure derivation; no entropy, IO, process, Main, Android or nonce consumption.
// utility functions are from immutable Git blob 443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d.
const INPUTS={
  "old_source": {
    "bytes": 37193,
    "sha256": "4510114c716912b31687d69ae4cb7d2e6e70d84748e7de74b57acd90fab8b339",
    "git_blob_sha1": "ed23905da748939bc99100dcf612c1f9136f759e"
  },
  "old_request": {
    "bytes": 40279,
    "sha256": "0b96a071491ab9e5591a4e512a18943303fe9aef6663cf162fb8099728416b38",
    "git_blob_sha1": "9eb9ca78ff58ef58f56db2139859ae919b7dc9e3"
  },
  "global921": {
    "bytes": 35001,
    "sha256": "735f9acaf4100e82bf7bfdacbecf9510286b1099f8dee92bf668e942e8780bac",
    "git_blob_sha1": "ffda46203066f1fa704ab92071de8b86867c3589"
  }
};
function deriveNonce02(input,U){
 function need(v,m){if(!v)throw Error(m);}
 function check(k,s){need(typeof s==="string","text "+k);const b=U.utf8(s),p=INPUTS[k];need(b.length===p.bytes&&U.sha256(b)===p.sha256&&U.gitBlob(b)===p.git_blob_sha1,"pin "+k);}
 for(const k of Object.keys(INPUTS))check(k,input[k]);
 const n=JSON.parse(input.global921);need(Array.isArray(n)&&n.length===921&&new Set(n).size===921&&n.every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x))&&JSON.stringify(n)===JSON.stringify([...n].sort()),"pool shape");
 need(n.includes("e4b5a1bdac8be04ff2ea3188a6d946d6"),"prior consumed install nonce absent");
 const marker="POOL_RAW = r'''",a=input.old_source.indexOf(marker);need(a>=0&&input.old_source.indexOf(marker,a+1)<0,"one pool start");
 const z=input.old_source.indexOf("'''.encode('ascii')",a+marker.length);need(z>a,"pool end");
 const oldPool=input.old_source.slice(a+marker.length,z);
 const changes=[
 ["KIND = 'pocket4-original-ndk-fixture-install-nonce01'","KIND = 'pocket4-original-ndk-fixture-install-nonce02'"],
 ["PROFILE = 'pocket4-original-ndk-fixture-APK03-install01'","PROFILE = 'pocket4-original-ndk-fixture-APK05-install02'"],
 [oldPool,input.global921],
 ["POOL_BYTES = 33823","POOL_BYTES = 35001"],
 ["POOL_SHA256 = '62066a9a8b68629be8ea7bf0ec74f112ef5d7714d1a19fb61bdc815bddf5fa1e'","POOL_SHA256 = '735f9acaf4100e82bf7bfdacbecf9510286b1099f8dee92bf668e942e8780bac'"],
 ["POOL_GIT_BLOB = '2df00e13580bb0d17124263affd9e43c86ab6c14'","POOL_GIT_BLOB = 'ffda46203066f1fa704ab92071de8b86867c3589'"],
 ["'git_blob_sha': POOL_GIT_BLOB, 'count': 890","'git_blob_sha': POOL_GIT_BLOB, 'count': 921"],
 ["'EXACT_GLOBAL_890_BYTES_REQUIRED'","'EXACT_GLOBAL_921_BYTES_REQUIRED'"],
 ["len(old) == 890 and len(set(old)) == 890","len(old) == 921 and len(set(old)) == 921"],
 ["'EXACT_UNIQUE_GLOBAL_890_SHAPE_REQUIRED'","'EXACT_UNIQUE_GLOBAL_921_SHAPE_REQUIRED'"]];
 let source=input.old_source;
 for(const[a,b]of changes){need(source.split(a).length===2,"unique old replacement");source=source.replace(a,b);}
 let inverse=source;for(const[a,b]of [...changes].reverse()){need(inverse.split(b).length===2,"unique reverse replacement");inverse=inverse.replace(b,a);}need(inverse===input.old_source,"exact inverse");
 const q=JSON.parse(input.old_request);need(q.stdin===input.old_source,"old request source");const original={...q};delete original.stdin;delete original.idempotency_key;
 q.stdin=source;q.idempotency_key="p4-original-ndk-fixture-install-nonce02-"+U.sha256(U.utf8(source)).slice(0,16);
 const request=JSON.stringify(q,null,2)+"\n";const same={...q};delete same.stdin;delete same.idempotency_key;need(JSON.stringify(same)===JSON.stringify(original),"request envelope changed");
 need(q.executable==="/usr/bin/python3"&&JSON.stringify(q.args)===JSON.stringify(["-I","-B","-"])&&q.timeout_seconds===20&&q.cpu_quota_percent===100&&q.memory_max_bytes===67108864&&q.nice===15,"actual envelope");
 return{source,request,inverse_exact:true,pool_count:921,new_nonce_generated:false,install_authorized:false};
}
