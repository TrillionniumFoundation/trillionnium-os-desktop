async function readPinnedZlibReport(prefix,row,maxChunks=8){
 const need=(ok,msg)=>{if(!ok)throw Error(msg);};
 need(["marriott04","native_host01"].includes(row.role)&&row.output_path.startsWith("/home/alex/work/p4-report-transport01-20261106/")&&row.output_bytes>0&&row.output_bytes<=1048576,"fixed transport scope");
 let parts=load(prefix+"_zlib_parts")||[],offset=parts.reduce((n,x)=>n+x.bytes,0),version=load(prefix+"_zlib_version");
 const originals=load(prefix+"_zlib_originals")||[];
 for(let step=0;offset<row.output_bytes&&step<maxChunks;step++){
  const args={host:"pocket4",path:row.output_path,offset,limit:65536};
  if(version!==undefined)args.expected_version=version;
  const response=await tools.mcp__codex_apps__heptaruntime_mac_controller_binary_read(args);
  const blocks=response.content?.filter(x=>x.type==="text");need(blocks?.length===1,"one exact binary result");
  const raw=blocks[0].text;const attempts=load(prefix+"_zlib_attempts")||[];attempts.push(raw);store(prefix+"_zlib_attempts",attempts);
  need(!response.isError,"binary read failed");
  const x=ll(raw),chunk=u.decode64(x.data_base64);
  need(x.path===row.output_path&&x.size===row.output_bytes&&x.offset===offset&&x.next_offset===offset+chunk.length&&u.sha256(chunk)===x.chunk_sha256&&chunk.length>0,"bound compressed chunk");
  if(version===undefined){need(typeof x.version==="string"&&x.version.length>0,"version token");version=x.version;store(prefix+"_zlib_version",version);}
  need(x.version===version&&x.next_offset<=row.output_bytes&&x.eof===(x.next_offset===row.output_bytes),"version/end continuity");
  parts.push({offset,bytes:chunk.length,sha256:x.chunk_sha256,base64:x.data_base64});originals.push(raw);offset=x.next_offset;
  store(prefix+"_zlib_parts",parts);store(prefix+"_zlib_originals",originals);
  text({prefix,compressed_bytes_read:offset,total_compressed_bytes:row.output_bytes});
 }
 if(offset<row.output_bytes)return {complete:false,offset};
 const compressed=new Uint8Array(row.output_bytes);let n=0;for(const part of parts){const bytes=u.decode64(part.base64);compressed.set(bytes,n);n+=bytes.length;}
 need(u.sha256(compressed)===row.output_sha256,"complete compressed SHA");
 const expanded=Function(load("p4_receipt_inflate_source"))()(compressed,row.input_bytes);
 need(expanded.length===row.input_bytes&&u.sha256(expanded)===row.input_sha256,"complete independent original SHA");
 const raw=u.utf8Decode(expanded);need(u.sha256(u.utf8Bytes(raw))===row.input_sha256,"lossless UTF-8 conversion");
 const pin={path:row.input_path,bytes:expanded.length,sha256:row.input_sha256,git_blob_sha1:v.gitBlob(expanded),read_method:"lossless-zlib-transport",compressed:{path:row.output_path,bytes:row.output_bytes,sha256:row.output_sha256,version,chunks:parts.length},transport_job_id:load("report_transport01_job_id"),decoder_sha256:u.sha256(u.utf8Bytes(load("p4_receipt_inflate_source")))};
 store(prefix+"_result_text",raw);store(prefix+"_result_pin",pin);store(prefix+"_result",ll(raw));store(prefix+"_complete_original_sha_verified",true);
 return {complete:true,pin,report_keys:Object.keys(load(prefix+"_result"))};
}
return readPinnedZlibReport;