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


function makeRequest(source) {
  const bytes = utf8(source);
  if (bytes.length !== 25640 || sha256(bytes) !== "d15efddd41f8035e1727c6c4d39451015cf3af2b3bd0992d0db0937f49692b1a" || gitBlob(bytes) !== "6c8b34d0d03f7e0fdf9d99550d12dc5e11c755b4") throw new Error("FIXED_READER_SOURCE_MISMATCH");
  const request = {
  "host": "pocket4",
  "executable": "/usr/bin/sudo",
  "args": [
    "-n",
    "/usr/bin/python3",
    "-I",
    "-B",
    "-"
  ],
  "cwd": "/",
  "stdin": null,
  "idempotency_key": "pocket4-main-fixed-init-rc-public-read01-20261106",
  "timeout_seconds": 20,
  "cpu_quota_percent": 25,
  "memory_max_bytes": 134217728,
  "nice": 15
};
  request.stdin = source;
  return JSON.stringify(request, null, 2) + "\n";
}
