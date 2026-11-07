function derive(input,H,D) {
  const need=(v,m)=>{if(!v)throw Error(m);};
  const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s)),git_blob_sha1:H.gitBlob(H.utf8(s))});
  const exact=(raw,bytes,sha)=>{need(typeof raw==="string"&&pin(raw).bytes===bytes&&pin(raw).sha256===sha,"exact input "+sha);};
  const canonical=v=>v===null||typeof v!=="object"?JSON.stringify(v):Array.isArray(v)?"["+v.map(canonical).join(",")+"]":"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}";
  exact(input.original_report,13115,"4e087d0a84cb0a640206d25cb3c958181b6aba11e7869f60eadff96caad7a0ce");
  exact(input.original_source,30076,"ae72ce1347b32b010fc44b1714ab1f7cb2e9af8ed0c950a20db5421b2f513b78");
  exact(input.original_request,46280,"b47359fa7f2c2c6cde0789fc9cda17d5d68a9853dad781967ffb9b222539c9d4");
  exact(input.historical_report,6042,"89a368ff75ae9b47697dac3b3c2f7475a7bb6bda420fcce90d424c4b26a91ab6");
  exact(input.base_diagnostic,29330,"0878c762de8ee0b6b19b3b8836a236120e6294ed4cfffc7a40ea621c2b73c076");
  const fixed=input.fixed,current=JSON.parse(input.original_report),history=JSON.parse(input.historical_report);
  const request01=JSON.parse(input.original_request),packet01=JSON.parse(request01.stdin);
  need(packet01.source===input.original_source&&current.source_sha256===pin(input.original_source).sha256,
       "current source parent exact");
  need(fixed.package==="com.Hyatt.hyt"&&current.package===fixed.package&&history.package===fixed.package&&
       current.ok===true&&current.error===null&&current.secondary_errors.length===0&&
       current.metadata_before.version_code===26090096&&history.version_code===26090096&&
       current.metadata_before.uid===10138&&current.actual_package_UID_version_APK_chain_stable===true,
       "separate current and historical metadata qualification");
  const observed=current.artifacts.map(row=>({filename:row.path.split("/").pop(),bytes:row.held_file.bytes,sha256:row.sha256}));
  need(canonical(observed)===canonical(history.installed_inputs.apks)&&
       canonical(observed)===canonical(fixed.historical_apks)&&observed.length===3&&
       observed.reduce((n,row)=>n+row.bytes,0)===140798759&&
       JSON.stringify(current.apk_paths_before)===JSON.stringify(fixed.apks.map(row=>row.path))&&
       current.artifacts.every((row,i)=>row.path===fixed.apks[i].path&&row.sha256===fixed.apks[i].sha256&&
                                      row.held_file.bytes===fixed.apks[i].bytes),"complete old/current three APK comparison");
  need(history.fresh_crash.returned_jni_version===-500&&
       history.fresh_crash.native_library_basename==="libdexprotector.so"&&
       history.fresh_crash.underlying_library_return_reason_established===false,
       "historical failure and unknown cause retained");
  need(fixed.target_member==="lib/arm64-v8a/libdexprotector.so"&&
       fixed.result.bytes===pin(input.original_report).bytes&&fixed.result.sha256===pin(input.original_report).sha256&&
       fixed.source.bytes===pin(input.original_source).bytes&&fixed.source.sha256===pin(input.original_source).sha256,
       "fixed input member and parent pins");
  need(input.template.split("__FIXED_BINDING_JSON__").length===2,"one fixed binding slot");
  const source=input.template.replace("__FIXED_BINDING_JSON__",JSON.stringify(JSON.stringify(fixed)));
  need(!source.includes(current.nonce)&&!/\b(?:subprocess|fork|Popen|setns|nsenter)\s*[.(]/.test(source),"no nonce or execution path");
  need(!/os\.(?:write|mkdir|makedirs|unlink|rename|replace|chmod|chown|truncate|listdir|scandir)\s*\(/.test(source)&&
       !/\bos\.O_(?:WRONLY|RDWR|CREAT|EXCL|TRUNC|APPEND)\b/.test(source),"read-only fixed file scope");
  const names=["need","sha","identity","named_identity","directory_identity","deadline","public_error",
       "remember","Journal","read_exact_file","module","original_predicates","ExistingActionLock",
       "HeldInitView","ReadDeadline","alarm_handler"];
  function block(raw,name) {
    const lines=raw.split("\n"),rx=new RegExp("^(?:def|class) "+name+"(?:\\(|:)");
    const at=lines.findIndex(line=>rx.test(line));need(at>=0,"definition "+name);
    let end=at+1;while(end<lines.length&&(lines[end].trim()===""||/^[ \t]/.test(lines[end])))end++;
    return lines.slice(at,end).join("\n").trimEnd()+"\n";
  }
  for(const name of names)need(block(input.base_diagnostic,name)===block(source,name),"unchanged lifecycle helper "+name);
  const guard=raw=>raw.slice(raw.indexOf("        def original_guard(final=False):"),raw.indexOf("        guard = original_guard"));
  need(guard(source)===guard(input.base_diagnostic),"nested original source/Main guard exact");
  need(source.includes("APK_READ_LIMIT = 384 * 1024 * 1024")&&
       source.includes("MAX_MEMBER_COMPRESSED = 32 * 1024 * 1024")&&
       source.includes("MAX_ELF_BYTES = 64 * 1024 * 1024")&&
       source.includes("OBSERVATION_SECONDS = 120\nFINAL_SECONDS = 150\nALARM_SECONDS = 165")&&
       source.includes("OUTPUT_LIMIT = 131072"),"fixed read/time/output bounds");
  const p=pin(source);
  const transport="import hashlib,sys\nraw=sys.stdin.buffer.read("+String(p.bytes+1)+")\n"+
       "if len(raw)!="+String(p.bytes)+" or hashlib.sha256(raw).hexdigest()!="+JSON.stringify(p.sha256)+":\n"+
       "    raise RuntimeError('EXACT_FIXED_DIAGNOSTIC_SOURCE_REQUIRED')\n"+
       "scope={'__name__':'__main__','__file__':"+JSON.stringify("<"+fixed.kind+">")+"}\n"+
       "exec(compile(raw,"+JSON.stringify("<"+fixed.kind+">")+",'exec'),scope)\n";
  const request={host:"pocket4",executable:"/usr/bin/sudo",
    args:["-n","/usr/bin/python3","-I","-B","-c",transport],cwd:"/home/alex/work",
    env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:source,memory_max_bytes:268435456,
    cpu_quota_percent:100,nice:15,timeout_seconds:180,
    idempotency_key:"pocket4-current-cell02-hyatt-exact-apk-elf-diagnostic-01-20261106"};
  need(p.bytes<1024*1024,"stdin cap");
  const requestRaw=JSON.stringify(request,null,2)+"\n";
  const proof={
    schema:1,status:"SOURCE_ONLY_UNRUN",kind:fixed.kind,source:p,exact_request:pin(requestRaw),transport:pin(transport),
    historical_report:pin(input.historical_report),current_metadata_original:pin(input.original_report),
    current_metadata_source:pin(input.original_source),current_metadata_request:pin(input.original_request),
    base_diagnostic:pin(input.base_diagnostic),old_current_APKs_exact:observed,
    current_UID:10138,current_version:26090096,current_paths:fixed.apks.map(x=>x.path),
    raw_originals_reencoded:false,unsafe_ns_identity_checked_by_runtime_Python_integer_comparison:true,
    historical_minus500_reinterpreted:false,static_metadata_cannot_establish_runtime_cause:true,
    fixed_member_path_previously_observed:false,
    fixed_member_policy:"Only exact lib/arm64-v8a/libdexprotector.so. No fallback; absent or duplicate fails and retains bounded basename metadata.",
    no_fresh_PM_query:true,App_nonce_consumption:0,Android_commands:0,children_spawned:0,
    namespace_entry:false,filesystem_mutations:0,APK_or_ELF_bytes_exported:false,
    unchanged_lifecycle_helpers:names,unchanged_nested_Main_guard:true,
    R6_source_manifest:"002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff",
    current_guard:"96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150",
    current_epoch:"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c",
    limits:{APK_total_bytes:140798759,two_complete_hash_bytes:281597518,
      all_APK_content_reads_max:402653184,one_pread_max:1048576,central_per_APK_max:8388608,
      ZIP_entries_per_APK_max:65534,compressed_member_max:33554432,member_max:67108864,
      ELF_symbols_max:131072,linear_instruction_window_max:16384,public_instruction_rows_max:128,
      observation_seconds:120,final_qualification_seconds:150,self_alarm_seconds:165,outer_seconds:180,
      output_bytes_max:131072,memory_max_bytes:268435456,cpu_quota_percent:100,nice:15},
    parser_controls:{count:15,implementation:"Production functions with explicit memory APK fixtures",Python_execution:"NOT_PERFORMED",does_not_test_Main_or_FD_lifecycle:true},
    cleanup:"First error plus secondary errors retained. Every explicit acquired FD is journaled before qualification; close once. Main/source, leaf identity/hash, close and deadline errors forbid complete.",
    global_ambient_FD_equality_asserted:false,
    qualification_boundary:"Static member ELF metadata and bounded linear instruction features only. No App process maps, execution, return-value cause, ABI/GPU/runtime acceptance or policy bypass.",
    validation:{V8_derivation:"PASS",Python_compilation:"NOT_PERFORMED",device_execution:"UNRUN"},
    prior_WIP_preserved:["42e640eaf2d1f605b04bfca02eac52214485f004","efecdb24ce0eab8410ca88bb90b47381d5a8fc11","4b85ab25b62082ed1f4abe7160b6283044d80c07"]
  };
  return {"read_elf.py":source,"exact-stdin.py":source,"transport.py":transport,
    "exact-request.json":requestRaw,"binding-proof.json":JSON.stringify(proof,null,2)+"\n",
    "base-diagnostic-to-elf.diff":D(input.base_diagnostic,source,"read_apk_metadata.py")};
}
