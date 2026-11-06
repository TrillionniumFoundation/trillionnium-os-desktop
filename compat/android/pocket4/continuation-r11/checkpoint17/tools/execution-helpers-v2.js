// Durable receipts, exact source loading, and a one-admission remote boundary.
// This file is the recovery source if transient code-mode storage is cleared.
const ROOT = "/workspace/scratch/94990735b266/";
function need(value, message) { if (!value) throw new Error(message); }
function pin(text) { const b = u.utf8Bytes(text); return {bytes:b.length, sha256:u.sha256(b)}; }
function path64(path) {
  need(typeof path === "string" && path.startsWith(ROOT) && !path.split("/").includes(".."), "local workspace path required");
  return u.encode64(u.utf8Bytes(path));
}
async function python(lines, max_output_tokens = 2000) {
  const r = await tools.exec_command({cmd:"python3 - <<'P4_HELPER_PY'\n" + lines.join("\n") + "\nP4_HELPER_PY", workdir:"/", max_output_tokens});
  need(r.exit_code === 0 && !r.session_id, "local helper failed: " + r.output);
  return r.output;
}
async function save(path, text, exclusive = false) {
  need(typeof text === "string", "save accepts exact UTF-8 text");
  const raw = u.utf8Bytes(text), expected = pin(text), encodedPath = path64(path);
  const count = Math.max(1, Math.ceil(raw.length / 32768));
  for (let i=0;i<count;i++) {
    const part = raw.slice(i*32768, (i+1)*32768);
    await python([
      "from pathlib import Path",
      "import os,base64",
      "p=Path(base64.b64decode('" + encodedPath + "').decode())",
      "d=Path(str(p)+'.transport-parts');d.mkdir(parents=True,exist_ok=True)",
      "assert d.is_dir() and not d.is_symlink()",
      "q=d/'" + String(i).padStart(4,"0") + "'",
      "b=base64.b64decode('" + u.encode64(part) + "',validate=True)",
      "if q.exists():",
      " assert q.is_file() and not q.is_symlink() and q.read_bytes()==b,'retained transport differs'",
      "else:",
      " fd=os.open(q,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)",
      " with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())"
    ]);
  }
  await python([
    "from pathlib import Path",
    "import os,base64,hashlib",
    "p=Path(base64.b64decode('" + encodedPath + "').decode());d=Path(str(p)+'.transport-parts')",
    "b=b''.join((d/format(i,'04d')).read_bytes() for i in range(" + count + "))",
    "assert len(b)==" + expected.bytes + " and hashlib.sha256(b).hexdigest()=='" + expected.sha256 + "'",
    "p.parent.mkdir(parents=True,exist_ok=True)",
    "if p.exists() or p.is_symlink():",
    " assert " + (exclusive ? "False" : "True") + ",'durable one-shot destination already exists'",
    " assert p.is_file() and not p.is_symlink() and p.read_bytes()==b,'retained destination differs'",
    "else:",
    " fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)",
    " with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())"
  ]);
  return {path,...expected};
}
async function loader(path, bytes, sha256) {
  const encodedPath = path64(path);
  need(Number.isSafeInteger(bytes) && bytes>=0 && /^[0-9a-f]{64}$/.test(sha256), "exact local pin required");
  const result = new Uint8Array(bytes); let firstIdentity;
  for (let offset=0;offset<Math.max(1,bytes);offset+=32768) {
    const response=JSON.parse(await python([
      "from pathlib import Path",
      "import os,base64,hashlib,json,stat",
      "p=Path(base64.b64decode('" + encodedPath + "').decode());s=p.lstat()",
      "assert stat.S_ISREG(s.st_mode) and not p.is_symlink()",
      "b=p.read_bytes();a=p.stat()",
      "ident=lambda x:[str(x.st_dev),str(x.st_ino),str(x.st_size),str(x.st_mtime_ns),str(x.st_ctime_ns)]",
      "assert ident(s)==ident(a) and len(b)==" + bytes + " and hashlib.sha256(b).hexdigest()=='" + sha256 + "'",
      "print(json.dumps({'identity':ident(s),'data':base64.b64encode(b[" + offset + ":" + (offset+32768) + "]).decode()}))"
    ],30000));
    const identity=JSON.stringify(response.identity);
    if(firstIdentity===undefined)firstIdentity=identity;
    need(identity===firstIdentity,"local source changed between chunks");
    const chunk=u.decode64(response.data);need(chunk.length===Math.min(32768,bytes-offset),"local chunk length");
    result.set(chunk,offset);
  }
  need(u.sha256(result)===sha256,"full local hash");
  return u.utf8Decode(result);
}
function originalText(response) {
  need(response && Array.isArray(response.content), "tool content required");
  const blocks=response.content.filter(x=>x.type==="text");
  need(blocks.length===1 && typeof blocks[0].text==="string","exact single tool text required");
  return blocks[0].text;
}
async function dispatch(x) {
  need(!load(x.prefix+"_dispatch_intent") && !load(x.prefix+"_admission"),"prefix already admitted or attempted");
  const raw=await loader(x.path,x.bytes,x.sha256),q=JSON.parse(raw);
  need(q.host==="pocket4" && q.idempotency_key===x.key,"exact configured host/key required");
  await save(x.review_path,JSON.stringify(x.review,null,2)+"\n");
  const intent={idempotency_key:x.key,request_sha256:x.sha256,automatic_retry:false};
  // O_EXCL on this durable file prevents re-execution after store/session loss.
  await save(x.evidence_dir+"/dispatch-intent.json",JSON.stringify(intent,null,2)+"\n",true);
  store(x.prefix+"_dispatch_intent",intent);store(x.prefix+"_exact_request_text",raw);store(x.prefix+"_exact_request",q);
  let response;
  try { response=await tools.mcp__codex_apps__heptaruntime_mac_controller_process_start(q); }
  catch(error) {
    const failure={state:"ADMISSION_UNKNOWN_NO_AUTOMATIC_RETRY",error:String(error),...intent};
    store(x.prefix+"_admission_unknown",failure);
    await save(x.evidence_dir+"/admission-unknown.json",JSON.stringify(failure,null,2)+"\n");
    throw error;
  }
  store(x.prefix+"_admission_raw",response);
  const text=originalText(response);
  await save(x.evidence_dir+"/admission.tool-original.json",text);
  const admission=JSON.parse(text);store(x.prefix+"_admission",admission);
  need(!response.isError && admission.job && typeof admission.job.id==="string","admission not established; retain original and do not retry");
  return {prefix:x.prefix,job_id:admission.job.id,launch:admission.launch,reused:admission.reused,launch_state:admission.job.launch_state,remote_job_dir:admission.job.remote_job_dir};
}
async function readRemote(x) {
  need(x.host==="pocket4" && typeof x.path==="string" && x.path.startsWith("/"),"fixed configured remote path required");
  need(x.bytes===undefined || (Number.isSafeInteger(x.bytes) && x.bytes>=0),"remote expected size");
  let offset=0,total,version;const chunks=[],originals=[],metadata=[];
  do {
    const args={host:x.host,path:x.path,offset,limit:65536};
    if(version!==undefined)args.expected_version=version;
    const response=await tools.mcp__codex_apps__heptaruntime_mac_controller_binary_read(args);
    const original=originalText(response);
    need(!response.isError,"remote read error: "+original);
    const value=JSON.parse(original),chunk=u.decode64(value.data_base64);
    need(u.sha256(chunk)===value.chunk_sha256 && value.offset===offset && value.next_offset===offset+chunk.length,"remote chunk binding");
    if(total===undefined) {
      total=value.size;version=value.version;
      need(typeof version==="string" && version.length>0,"remote stable version required");
      need(Number.isSafeInteger(total) && total>=0 && total<=(x.maximum_bytes??16*1024*1024),"remote size bound");
      need(x.bytes===undefined || x.bytes===total,"remote size differs from original pin");
    }
    need(value.size===total && value.version===version && value.path===x.path,"remote file/version changed");
    need(chunk.length>0 || value.eof,"nonadvancing remote read");
    chunks.push(chunk);originals.push(original);
    metadata.push({offset:value.offset,next_offset:value.next_offset,bytes:chunk.length,sha256:value.chunk_sha256});
    offset=value.next_offset;need(offset<=total,"remote excess");
    if(value.eof){need(offset===total,"premature remote EOF");break;}
  }while(true);
  const raw=new Uint8Array(total);let at=0;for(const chunk of chunks){raw.set(chunk,at);at+=chunk.length;}
  const hash=u.sha256(raw);need(x.sha256===undefined || hash===x.sha256,"full remote SHA differs from original pin");
  const text=u.utf8Decode(raw),record={path:x.path,bytes:total,sha256:hash,version,chunks:metadata};
  if(x.prefix){store(x.prefix+"_result_text",text);store(x.prefix+"_result_pin",record);store(x.prefix+"_binary_chunks_raw",originals);}
  if(x.local_path)await save(x.local_path,text);
  return {text,pin:record,originals};
}
async function readStdout(x) {
  const s=x.terminal??load(x.prefix+"_terminal_status"),a=x.admission??load(x.prefix+"_admission");
  need(s && ["succeeded","failed","cancelled"].includes(s.state) && s.output_complete===true && s.output_durable===true && s.terminal_publication_confirmed===true,"durable terminal output required");
  need(s.log_errors.stdout===null && s.log_errors.stderr===null && !s.log_truncated.stdout && !s.log_truncated.stderr && s.log_synced.stdout && s.log_synced.stderr,"terminal logs incomplete");
  need(s.log_bytes.stdout.seen===s.log_bytes.stdout.stored && s.log_bytes.stderr.stored===0 && s.log_bytes.stderr.seen===0,"known single stdout collector only");
  const jobId=x.job_id??a?.job?.id??a?.job_id;need(jobId===s.job_id,"terminal job binding");
  const remote=a?.job?.remote_job_dir??("/home/alex/.local/state/hepta-runtime-mac-worker/jobs/"+jobId);
  const value=await readRemote({host:"pocket4",path:remote+"/stdout.log",bytes:s.log_bytes.stdout.stored,prefix:x.prefix+"_stdout",local_path:x.dir+"/stdout.log"});
  for(let i=0;i<value.originals.length;i++)await save(x.dir+"/stdout-binary-"+String(i).padStart(4,"0")+".tool-original.json",value.originals[i]);
  const record={schema:1,job_id:jobId,terminal_output_complete:true,terminal_output_durable:true,stderr_bytes:0,...value.pin};
  await save(x.dir+"/known-terminal-binary-read-verification.json",JSON.stringify(record,null,2)+"\n");
  store(x.prefix+"_stdout_text",value.text);store(x.prefix+"_stdout_pin",record);
  return {prefix:x.prefix,job_id:jobId,bytes:value.pin.bytes,sha256:value.pin.sha256};
}
return {save,loader,pin,dispatch,readRemote,readStdout,originalText};
