function assertThat(ok, message) { if (!ok) throw new Error(message); }

function utf8(text) {
  const out=[];
  for(let i=0;i<text.length;i++){
    let c=text.charCodeAt(i);
    if(c>=0xd800&&c<=0xdbff){const lo=text.charCodeAt(++i);assertThat(lo>=0xdc00&&lo<=0xdfff,"invalid UTF16 high surrogate");c=0x10000+((c-0xd800)<<10)+(lo-0xdc00);}
    else assertThat(!(c>=0xdc00&&c<=0xdfff),"invalid UTF16 low surrogate");
    if(c<0x80)out.push(c);
    else if(c<0x800)out.push(0xc0|(c>>>6),0x80|(c&63));
    else if(c<0x10000)out.push(0xe0|(c>>>12),0x80|((c>>>6)&63),0x80|(c&63));
    else out.push(0xf0|(c>>>18),0x80|((c>>>12)&63),0x80|((c>>>6)&63),0x80|(c&63));
  }
  return new Uint8Array(out);
}

function concatBytes(parts){const out=new Uint8Array(parts.reduce((n,p)=>n+p.length,0));let at=0;for(const p of parts){out.set(p,at);at+=p.length;}return out;}

function padded(bytes){const n=Math.ceil((bytes.length+9)/64)*64;const out=new Uint8Array(n);out.set(bytes);out[bytes.length]=128;const view=new DataView(out.buffer);const bits=bytes.length*8;view.setUint32(n-8,Math.floor(bits/4294967296),false);view.setUint32(n-4,bits>>>0,false);return out;}

function sha1(bytes){
  const b=padded(bytes),view=new DataView(b.buffer),w=new Uint32Array(80);
  let h0=0x67452301,h1=0xefcdab89,h2=0x98badcfe,h3=0x10325476,h4=0xc3d2e1f0;
  const rol=(x,n)=>((x<<n)|(x>>>(32-n)))>>>0;
  for(let off=0;off<b.length;off+=64){
    for(let i=0;i<16;i++)w[i]=view.getUint32(off+i*4,false);
    for(let i=16;i<80;i++)w[i]=rol(w[i-3]^w[i-8]^w[i-14]^w[i-16],1);
    let a=h0,c=h2,d=h3,e=h4,q=h1;
    for(let i=0;i<80;i++){let f,k;if(i<20){f=(q&c)|((~q)&d);k=0x5a827999;}else if(i<40){f=q^c^d;k=0x6ed9eba1;}else if(i<60){f=(q&c)|(q&d)|(c&d);k=0x8f1bbcdc;}else{f=q^c^d;k=0xca62c1d6;}
      const t=(rol(a,5)+f+e+k+w[i])>>>0;e=d;d=c;c=rol(q,30);q=a;a=t;
    }
    h0=(h0+a)>>>0;h1=(h1+q)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;h4=(h4+e)>>>0;
  }
  return [h0,h1,h2,h3,h4].map(v=>v.toString(16).padStart(8,"0")).join("");
}

function sha256(bytes){
  const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19],b=padded(bytes),v=new DataView(b.buffer),w=new Uint32Array(64),ror=(x,n)=>(x>>>n)|(x<<(32-n));
  for(let off=0;off<b.length;off+=64){
    for(let i=0;i<16;i++)w[i]=v.getUint32(off+i*4,false);
    for(let i=16;i<64;i++){const a=w[i-15],z=w[i-2],s0=ror(a,7)^ror(a,18)^(a>>>3),s1=ror(z,17)^ror(z,19)^(z>>>10);w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;}
    let [a,c,d,e,f,g,h,q]=H;
    for(let i=0;i<64;i++){const s1=ror(f,6)^ror(f,11)^ror(f,25),ch=(f&g)^((~f)&h),t1=(q+s1+ch+K[i]+w[i])>>>0,s0=ror(a,2)^ror(a,13)^ror(a,22),maj=(a&c)^(a&d)^(c&d),t2=(s0+maj)>>>0;q=h;h=g;g=f;f=(e+t1)>>>0;e=d;d=c;c=a;a=(t1+t2)>>>0;}
    const xs=[a,c,d,e,f,g,h,q];for(let i=0;i<8;i++)H[i]=(H[i]+xs[i])>>>0;
  }
  return H.map(v=>v.toString(16).padStart(8,"0")).join("");
}

function hexBytes(text){assertThat(/^[0-9a-f]{40}$/.test(text),"bad SHA1");return new Uint8Array(text.match(/../g).map(x=>parseInt(x,16)));}

function gitBlob(bytes){return sha1(concatBytes([utf8("blob "+bytes.length+"\0"),bytes]));}

function byteCmp(a,b){const n=Math.min(a.length,b.length);for(let i=0;i<n;i++)if(a[i]!==b[i])return a[i]-b[i];return a.length-b.length;}

function treeHash(entries){
  const parts=entries.map(e=>({key:utf8(e.name+(e.type==="tree"?"/":"")),body:concatBytes([utf8((e.type==="tree"?"40000":e.mode)+" "+e.name+"\0"),hexBytes(e.sha)])})).sort((a,b)=>byteCmp(a.key,b.key));
  const body=concatBytes(parts.map(x=>x.body));return sha1(concatBytes([utf8("tree "+body.length+"\0"),body]));
}

function verifyGitTree(tree,rows,root){
  assertThat(tree.sha===root&&!tree.truncated,"tree root or truncation");
  const actual=new Map(tree.tree.map(e=>[e.path,e]));assertThat(actual.size===tree.tree.length,"duplicate Git paths");
  const files=new Map(rows.map(r=>[r.path,r]));assertThat(files.size===rows.length,"duplicate expected paths");const dirs=new Set([""]);
  for(const [path,r] of files){assertThat(!path.startsWith("/")&&path.split("/").every(p=>p!==""&&p!=="."&&p!==".."),"unsafe path");const a=actual.get(path);assertThat(a&&a.type==="blob"&&a.mode==="100644"&&a.sha===r.git_blob_sha1&&a.size===r.bytes,"leaf mismatch "+path);const p=path.split("/");for(let i=1;i<p.length;i++)dirs.add(p.slice(0,i).join("/"));}
  assertThat(actual.size===files.size+dirs.size-1,"path count mismatch");
  for(const path of actual.keys())assertThat(files.has(path)||dirs.has(path),"unexpected path "+path);
  const children=new Map();for(const e of actual.values()){const k=e.path.lastIndexOf("/"),parent=k<0?"":e.path.slice(0,k),name=e.path.slice(k+1);if(!children.has(parent))children.set(parent,[]);children.get(parent).push({...e,name});assertThat(e.type==="blob"?e.mode==="100644":e.type==="tree"&&e.mode==="040000","type/mode");}
  const ordered=[...dirs].sort((a,b)=>b.split("/").length-a.split("/").length||b.length-a.length),hashes=new Map();
  for(const dir of ordered){const es=children.get(dir)||[];for(const e of es)if(e.type==="tree")assertThat(hashes.get(e.path)===e.sha,"child directory hash mismatch");const hash=treeHash(es);assertThat(hash===(dir===""?root:actual.get(dir)?.sha),"directory hash "+dir);hashes.set(dir,hash);}
  return {tree:root,leaf_count:files.size,logical_bytes:rows.reduce((n,r)=>n+r.bytes,0),directory_count_including_root:dirs.size,recursive_entries:actual.size,truncated:false,all_paths_modes_sizes_blob_sha1_match:true,all_directory_tree_sha1_recomputed:true};
}

function verifyCP17(inputs){
  assertThat(sha1(utf8(""))==="da39a3ee5e6b4b0d3255bfef95601890afd80709","SHA1 empty control");
  assertThat(sha1(utf8("abc"))==="a9993e364706816aba3e25717850c26c9cd0d89d","SHA1 abc control");
  assertThat(sha256(utf8(""))==="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","SHA256 empty control");
  assertThat(sha256(utf8("abc"))==="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","SHA256 abc control");
  assertThat(gitBlob(utf8(""))==="e69de29bb2d1d6434b8b29ae775ad8c2e48c5391","Git empty blob control");
  assertThat([...utf8("é€😀")].map(x=>x.toString(16).padStart(2,"0")).join("")==="c3a9e282acf09f9880","UTF8 multibyte control");
  const expected={
    index:[2747603,"c2e6b5047a559731cb52a7277d8dd1f66896405a00f5d9bf3bdae4d4fe86582c","2a2b0dbe7c97105921d6e3b396ee0368b1788b27"],
    manifest:[3767769,"c12fcddeb62d7868a8f847a6d44cf4c6250fc29e885d4d30e0d9ce47f6335803","3c2b69be8dc6bc5ebfc26df9b6e70da5f2fee98e"],
    old_manifest:[2879819,"e7151e0aaa5f30da09499a6ed3d157ca19ba5df3668bf15041071faeeb948dfa","897d16c787fef6a71fbd548b7215886c12ced6ca"]
  },pins={};
  for(const [name,[size,hash,blob]] of Object.entries(expected)){const b=utf8(inputs[name]);assertThat(b.length===size&&sha256(b)===hash&&gitBlob(b)===blob,"actual full Git blob bytes mismatch "+name);pins[name]={bytes:size,sha256:hash,git_blob_sha1:blob,entire_remote_body_independently_verified:true};}
  const index=JSON.parse(inputs.index),manifest=JSON.parse(inputs.manifest),old=JSON.parse(inputs.old_manifest),cp=JSON.parse(inputs.checkpoint),outer=JSON.parse(inputs.outer);
  assertThat(index.file_count===2558&&index.files.length===2558&&index.bytes===45232539,"index counts");
  assertThat(index.checkpoint_subtree_sha==="d28deed485cdfff7aa8335e7064c63f2979bc02c","index tree");
  assertThat(manifest.files.length===11939&&manifest.files_excluding_manifest===11939&&manifest.bytes_excluding_manifest===208190597,"manifest counts");
  assertThat(old.files.length===9381&&old.bytes_excluding_manifest===162958058,"old manifest counts");
  const safeNumbers=x=>{if(typeof x==="number")assertThat(Number.isSafeInteger(x),"file-row unsafe numeric field");else if(x&&typeof x==="object")for(const v of Object.values(x))safeNumbers(v);};safeNumbers(old.files);safeNumbers(manifest.files);
  assertThat(JSON.stringify(manifest.files.slice(0,9381))===JSON.stringify(old.files),"inherited rows differ");
  const additional=manifest.files.slice(9381);for(let i=0;i<index.files.length;i++){const a=additional[i],r=index.files[i];for(const k of ["path","sha256","bytes","encoding","git_blob_sha1","mode"])assertThat(a[k]===(k==="path"?"checkpoint17/"+r[k]:r[k]),"manifest increment mismatch "+i+" "+k);}
  assertThat(manifest.files.reduce((n,r)=>n+r.bytes,0)===208190597,"total bytes sum");
  assertThat(JSON.stringify(manifest.files.find(r=>r.path==="README.md"))===JSON.stringify(old.files.find(r=>r.path==="README.md")),"old README changed");
  assertThat(manifest.current_status_key==="checkpoint17"&&manifest.checkpoint17.whole_apps_ready===0&&manifest.checkpoint17.launcher_apps===45&&!manifest.checkpoint17.all_apps_production_ready,"production readiness state");
  const checkpoint=verifyGitTree(cp,index.files,"d28deed485cdfff7aa8335e7064c63f2979bc02c");
  const wantedMetadata=["delivery-manifest.json","publication/payload-index.json","publication/candidate-payload-index.json","publication/manifest-increment.json","publication/exclusions.json","publication/catalog-provenance.json","publication/assembly-review.json","publication/index_candidate.py","publication/assemble_candidate.py","publication/prepare_preservation.py"];
  const actualOuter=new Map(outer.tree.map(e=>[e.path,e]));
  const metadata=wantedMetadata.map(path=>{const e=actualOuter.get(path);assertThat(e&&e.type==="blob"&&e.mode==="100644","missing outer metadata "+path);return {path,bytes:e.size,git_blob_sha1:e.sha};});
  const knownMetadata={
    "delivery-manifest.json":[3767769,"3c2b69be8dc6bc5ebfc26df9b6e70da5f2fee98e"],
    "publication/payload-index.json":[2747603,"2a2b0dbe7c97105921d6e3b396ee0368b1788b27"],
    "publication/candidate-payload-index.json":[2745105,"f025d34ed904c10a74918a56c3f0606bcaef43a4"],
    "publication/manifest-increment.json":[861622,"7754cb1a4bb401563f69a80816a957b618b5549f"],
    "publication/exclusions.json":[664817,"5ef5120ef51d3cc25095db0e70ddfd36a698f8d7"],
    "publication/catalog-provenance.json":[15123,"d1b3281726828c47f07c7ae54eb307a84f37c3c1"],
    "publication/assembly-review.json":[3411,"a7c68fc697483d46202d9b5c6dd57727ad344624"]
  };
  for(const [p,[size,sha]] of Object.entries(knownMetadata)){const e=actualOuter.get(p);assertThat(e.size===size&&e.sha===sha,"outer metadata pin "+p);}
  const outerVerification=verifyGitTree(outer,[...index.files.map(r=>({...r,path:"checkpoint17/"+r.path})),...metadata],"7c599da56b8d8d767b8fcc3f55ada341acfe4f92");
  assertThat(actualOuter.get("checkpoint17").sha===checkpoint.tree,"outer checkpoint link");
  for(const name of ["checkpoint","outer"]){const b=utf8(inputs[name]);pins[name+"_recursive_api_body"]={bytes:b.length,sha256:sha256(b),tree:JSON.parse(inputs[name]).sha};}
  return {schema:1,state:"PASS_ACTUAL_IMMUTABLE_GIT_TREE_AND_FULL_MANIFEST_BODY_VERIFICATION",repository:"TrillionniumFoundation/trillionnium-os-desktop",primary_cut:"2026-11-06T01:20:18+00:00",explicit_addendum_cut:"2026-11-06T01:27:34+00:00",checkpoint,outer:outerVerification,publication_metadata:metadata,input_pins:pins,inherited_9381_rows_identical_in_order_and_values:true,old_root_README_row_identical:true,all_2558_manifest_increment_rows_match_verified_Git_index:true,whole_apps_ready:0,launcher_apps:45,all_apps_production_ready:false,Git_ref_branch_commit_PR_mutations:0,Hepta_calls:0,filesystem_calls:0,hash_controls:"SHA1 and SHA256 empty/abc; empty Git blob; explicit multibyte UTF8; all three large known body pins matched",integer_scope:"Original remote UTF8 strings were hashed without JSON reserialization. Only file-row safe integer sizes are compared as JS numbers; ns fields are not republished or normalized.",scope:"Complete nontruncated tree metadata, every expected checkpoint leaf, all directory hashes, exact outer root/path set and metadata, and entire new/old manifest plus index bodies from immutable Git. Individual source/evidence blob bodies were already independently hashed locally before environment loss; this pass does not redownload all 2558 bodies.",Root_prior_independent_local_review:{bytes:1128,sha256:"e252c74d7b39a8c1fc85842f69c00fcfc5ee7d84b832b028f4fe55ddfd034365"},unavailable_environment_local_final_verifier:"NOT_CLAIMED_EXECUTED; pending local cell terminated; replaced by this no-filesystem verification",BestBuy_R2:"NOT_STARTED"};
}
