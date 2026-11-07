// Pure V8 render. No network, filesystem, Python or application execution.
// utilitySource must be immutable blob 443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d.
function renderEntryControls(utilitySource,packetRaw,templateRaw){
  const U=Function(utilitySource+"\nreturn {utf8,sha1,sha256,gitBlob};")();
  if(U.gitBlob(U.utf8(utilitySource))!=="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d")
    throw Error("UTILITY_BLOB");
  function encode64(bytes){
    if(!(bytes instanceof Uint8Array))throw Error("BASE64_REQUIRES_UTF8_BYTES");
    const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let output="";
    for(let i=0;i<bytes.length;i+=3){
      const count=Math.min(3,bytes.length-i);
      const n=(bytes[i]<<16)|((count>1?bytes[i+1]:0)<<8)|(count>2?bytes[i+2]:0);
      output+=alphabet[(n>>>18)&63]+alphabet[(n>>>12)&63]+
        (count>1?alphabet[(n>>>6)&63]:"=")+(count>2?alphabet[n&63]:"=");
    }
    return output;
  }
  function decode64(text){
    if(!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(text))
      throw Error("BASE64_SHAPE");
    const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const size=text.length/4*3-(text.endsWith("==")?2:text.endsWith("=")?1:0);
    const out=new Uint8Array(size);let at=0;
    for(let i=0;i<text.length;i+=4){
      const n=(alphabet.indexOf(text[i])<<18)|(alphabet.indexOf(text[i+1])<<12)|
        ((text[i+2]==="="?0:alphabet.indexOf(text[i+2]))<<6)|
        (text[i+3]==="="?0:alphabet.indexOf(text[i+3]));
      if(at<size)out[at++]=(n>>>16)&255;
      if(at<size)out[at++]=(n>>>8)&255;
      if(at<size)out[at++]=n&255;
    }
    return out;
  }
  const bytes=U.utf8(packetRaw),digest=U.sha256(bytes),encoded=encode64(bytes),decoded=decode64(encoded);
  if(decoded.length!==bytes.length||decoded.some((v,i)=>v!==bytes[i]))
    throw Error("BASE64_ROUNDTRIP");
  let stdin=templateRaw;
  for(const [key,value] of Object.entries({
    "__PACKET_SHA256__":digest,"__PACKET_BYTES__":String(bytes.length),"__PACKET_B64__":encoded})){
    if(stdin.split(key).length!==2)throw Error("EXACT_SINGLE_TEMPLATE_SLOT_"+key);
    stdin=stdin.replace(key,value);
  }
  const packet=JSON.parse(packetRaw);
  if(packet.schema!==1||packet.kind!=="pocket4-original-ndk-install-entry-controls01")
    throw Error("PACKET_KIND");
  const request={
    args:["-n","/usr/bin/python3","-I","-B","-"],cpu_quota_percent:100,
    cwd:"/home/alex/work",executable:"/usr/bin/sudo",host:"pocket4",
    idempotency_key:"p4-ndk-fixture-install-entry-controls01-"+U.sha256(U.utf8(stdin)).slice(0,16),
    memory_max_bytes:268435456,nice:15,stdin,timeout_seconds:60
  };
  return{stdin,requestRaw:JSON.stringify(request,null,2)+"\n",
    proof:{packet_bytes:bytes.length,packet_sha256:digest,base64_bytes:encoded.length,
      base64_roundtrip_exact:true,template_slots:3,source_only_install_request:false,
      controls_only:true}};
}
