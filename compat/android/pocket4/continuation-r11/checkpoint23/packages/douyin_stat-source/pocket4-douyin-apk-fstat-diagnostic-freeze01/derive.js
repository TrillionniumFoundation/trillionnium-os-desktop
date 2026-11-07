function derive(input,H,D) {
  const need=(ok,msg)=>{if(!ok)throw Error(msg);};
  const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s)),git_blob_sha1:H.gitBlob(H.utf8(s))});
  const f=input.fixed, original=JSON.parse(input.original_report);
  need(pin(input.original_report).bytes===f.result.bytes&&pin(input.original_report).sha256===f.result.sha256,"actual report pin");
  need(pin(input.original_source).bytes===f.source.bytes&&pin(input.original_source).sha256===f.source.sha256,"actual metadata source pin");
  need(original.ok===false&&original.error.phase==="held_APK_hash"&&
       original.error.message==="TICKET12306_INSTALLED_APK_SHAPE_OR_BOUND","actual failure phase");
  need(original.package===f.package&&JSON.stringify(original.apk_paths_before)===JSON.stringify([f.apk_path]),"one actual APK");
  for(const k of ["package","uid","user","version_code"])
    need(original.metadata_before[k]===f.observed_metadata[k],"actual metadata "+k);
  const stage=JSON.parse(input.original_request);
  need(JSON.parse(stage.stdin).source===input.original_source,"original request source exact");
  need(stage.idempotency_key!==input.key,"fresh idempotency key");
  need(input.template.split("__FIXED_BINDING_JSON__").length===2,"one binding slot");
  const source=input.template.replace("__FIXED_BINDING_JSON__",JSON.stringify(JSON.stringify(f)));
  need(!source.includes(original.nonce),"no original App nonce in diagnostic source");
  need(!/\b(?:subprocess|fork|Popen|setns|nsenter)\s*[.(]/.test(source),"no child or namespace entry");
  need(!/os\.(?:write|mkdir|makedirs|unlink|rename|replace|chmod|chown|truncate)\s*\(/.test(source),"no filesystem mutation");
  need(!/\bos\.O_(?:WRONLY|RDWR|CREAT|EXCL|TRUNC|APPEND)\b/.test(source),"read-only descriptor flags");
  need((source.match(/os\.read\(/g)||[]).length===1,"only exact authority content reader");
  const apk=source.slice(source.indexOf("class OneApkView:"),source.indexOf("class ReadDeadline"));
  need(!apk.includes("os.read(")&&apk.includes("os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC"),"APK O_PATH metadata only");
  const predicate=input.original_source.match(/            need\(stat\.S_ISREG\(first\['mode'\]\)[\s\S]*?'TICKET12306_INSTALLED_APK_SHAPE_OR_BOUND'\)/g);
  need(predicate&&predicate.length===1,"one original APK predicate");
  need(input.original_source.includes("FILE_LIMIT = 256 * 1024 * 1024")&&
       source.includes("ORIGINAL_FILE_LIMIT = 256 * 1024 * 1024"),"same original size bound");
  const p=pin(source);
  const transport="import hashlib,sys\nraw=sys.stdin.buffer.read("+String(p.bytes+1)+")\n"+
    "if len(raw)!="+String(p.bytes)+" or hashlib.sha256(raw).hexdigest()!="+JSON.stringify(p.sha256)+":\n"+
    "    raise RuntimeError('EXACT_FIXED_DIAGNOSTIC_SOURCE_REQUIRED')\n"+
    "scope={'__name__':'__main__','__file__':"+JSON.stringify("<"+f.kind+">")+"}\n"+
    "exec(compile(raw,"+JSON.stringify("<"+f.kind+">")+",'exec'),scope)\n";
  const request={
    host:"pocket4",executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-B","-c",transport],
    cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:source,
    memory_max_bytes:268435456,cpu_quota_percent:100,nice:15,timeout_seconds:65,
    idempotency_key:input.key
  };
  need(H.utf8(request.stdin).length<1024*1024,"stdin transport bound");
  const requestRaw=JSON.stringify(request,null,2)+"\n";
  const proof={
    schema:1,status:"SOURCE_ONLY_UNRUN",kind:f.kind,original_report:pin(input.original_report),
    original_metadata_source:pin(input.original_source),original_request:pin(input.original_request),
    original_failure_preserved:true,original_failed_predicate_at_failure_time:"UNKNOWN",
    original_uid_version:f.observed_metadata,one_fixed_apk_path:f.apk_path,
    original_predicate_source:predicate[0],original_limit_bytes:268435456,
    fixed_bindings:f,new_source:p,exact_request:pin(requestRaw),exact_stdin:p,transport:pin(transport),
    original_App_nonce_present_in_new_source:false,App_nonce_consumption:0,
    filesystem_writes:0,Android_commands:0,children_spawned:0,APK_content_reads:0,
    directory_enumeration:false,namespace_entry:false,global_ambient_FD_equality_claimed:false,
    unchanged_R6_manifest:"002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff",
    unchanged_R6_guard:"96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150",
    unchanged_R6_held_runtime:"72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4",
    new_owned_read_scope:[
      "Whole bound historical result and its exact metadata source, twice",
      "Unchanged R6 SourceContract, current Main guard and qualified shared-helper source inputs",
      "Existing action-lock file opened O_RDONLY, one nonblocking flock, no creation",
      "Fixed current init proc/pidfd, six namespace FDs and held root",
      "Four fixed APK ancestor components; only O_PATH/fstat/no-follow named stat on the one base.apk"
    ],
    success_means:"Current fstat observation complete, unchanged named/held identity, original source and Main guards passed, all journal FDs closed; not APK metadata admission.",
    errors:"First error retained; each journal close attempted once; final Main/source/name/close/deadline failure forbids collection_complete.",
    validation:{V8_reproduction_and_static_contract_checks:"PASS",Python_compilation:"NOT_PERFORMED",Python_controls:"NOT_PERFORMED",device_execution:"UNRUN"},
    peer_review:"NOT_PERFORMED; App agent prioritized current Main diagnostic",
    raw_originals_reencoded:false
  };
  return {
    "read_apk_metadata.py":source,
    "exact-stdin.py":source,
    "transport.py":transport,
    "exact-request.json":requestRaw,
    "binding-proof.json":JSON.stringify(proof,null,2)+"\n",
    "original-to-diagnostic.diff":D(input.original_source,source,"read_target.py"),
    "source-semantics.json":JSON.stringify({
       schema:1,unchanged_original_functions:["identity (formatting only)"],
       borrowed_unchanged_sources:["R6 SourceContract","R6 current_baseline_guard","R6 main_binding.same_epoch_identity","R6 held_runtime.proc_identity_at/pidfd_alive/NS_TYPES"],
       removed_paths:["metadata stage creation","nonce/claim consumption","discover_main and classpath discovery","all PM commands","packages.list and data-directory reads","APK content hash","result file write"],
       added_paths:["fixed complete original-result binding","per-predicate fstat projection","journaled owned held-init FDs","O_PATH no-follow single-leaf path","whole observation and retirement deadlines"],
       frozen_inputs_mutated:false,existing_app_metadata_gate_changed:false
    },null,2)+"\n"
  };
}