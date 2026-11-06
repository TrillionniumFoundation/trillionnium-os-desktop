function deriveBound(input,H,D,Q) {
  const need=(v,m)=>{if(!v)throw Error(m);};
  const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s)),git_blob_sha1:H.gitBlob(H.utf8(s))});
  const canonical=v=>v===null||typeof v!=="object"?JSON.stringify(v):Array.isArray(v)?"["+v.map(canonical).join(",")+"]":"{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}";
  function topRawFields(raw) {
    // Preserve number tokens verbatim; observations contain nanosecond integers.
    JSON.parse(raw);
    let i=0;const out={};
    const ws=()=>{while(i<raw.length&&/\s/.test(raw[i]))i++;};
    const stringEnd=()=>{need(raw[i]==='"',"JSON string");i++;while(i<raw.length){const c=raw[i++];if(c==="\\"){i++;continue;}if(c==='"')return;}throw Error("unterminated JSON string");};
    ws();need(raw[i++]==="{","top JSON object");ws();
    while(raw[i]!=="}") {
      const keyStart=i;stringEnd();const key=JSON.parse(raw.slice(keyStart,i));ws();
      need(raw[i++]===":"&&!Object.prototype.hasOwnProperty.call(out,key),"unique top JSON key");ws();
      const start=i;let depth=0;
      while(i<raw.length) {
        const c=raw[i];
        if(c==='"'){stringEnd();continue;}
        if(c==="["||c==="{"){depth++;i++;continue;}
        if(c==="]"||c==="}"){if(depth===0)break;depth--;i++;continue;}
        if(c===","&&depth===0)break;
        i++;
      }
      need(depth===0&&i>start,"complete top JSON value");out[key]=raw.slice(start,i).trim();ws();
      if(raw[i]===","){i++;ws();continue;}
      need(raw[i]==="}","top JSON delimiter");
    }
    i++;ws();need(i===raw.length,"top JSON complete EOF");return out;
  }
  const config=input.config, oldRequest=JSON.parse(input.old_request);
  const oldPacket=JSON.parse(oldRequest.stdin), actual=JSON.parse(input.fstat_actual);
  const oldResult=JSON.parse(input.failed_metadata_original);
  const actualRaw=topRawFields(input.fstat_actual);
  const known={
    douyin:{package:"com.ss.android.ugc.aweme",bytes:364363658,
      actual_sha:"7efc18376b14d4b8634b020db27a113a76518595a3ec3baca86d4e44184b4aad",actual_bytes:12124,
      old_source_sha:"8d9bdff0bbc0d4bbcd125c8cfbb9dc3c5cfbb5bf152ec750393f73e2ed10cb43",
      old_source_bytes:30072},
    wechat:{package:"com.tencent.mm",bytes:286319384,
      actual_sha:"9b3e48ea1e8f676593040f8f9eae7f5cbd66b1a6f79eb2bacb91e71c7f3baa32",actual_bytes:12061,
      old_source_sha:"faecbf9ae802c905e58316bf538b992121fa43082f8455739ac340caf08416ad",
      old_source_bytes:30060}
  };
  const k=known[config.id];
  need(k&&config.package===k.package,"exact two package scope");
  need(pin(input.old_source).sha256===k.old_source_sha&&pin(input.old_source).bytes===k.old_source_bytes,"old exact source");
  need(oldPacket.source===input.old_source&&oldPacket.nonce===config.old_consumed_nonce,"old request exact source/nonce");
  need(pin(input.fstat_actual).sha256===k.actual_sha&&pin(input.fstat_actual).bytes===k.actual_bytes,"whole actual fstat pin");
  need(oldResult.ok===false&&oldResult.error.phase==="held_APK_hash"&&
       oldResult.error.message==="TICKET12306_INSTALLED_APK_SHAPE_OR_BOUND"&&oldResult.package===k.package,
       "preserved original failure");
  need(actual.original_result.sha256===pin(input.failed_metadata_original).sha256&&
       actual.original_result.bytes===pin(input.failed_metadata_original).bytes,"fstat parent exact original");
  need(actual.collection_complete===true&&actual.package===k.package&&
       actual.first_error===null&&actual.secondary_errors.length===0,"actual complete");
  need(actual.APK_before.held.bytes===k.bytes&&k.bytes>268435456&&k.bytes<=536870912&&
       actualRaw.APK_before===actualRaw.APK_after&&
       actualRaw.APK_before===actualRaw.APK_final,"three current identical fstats");
  need(canonical(actual.APK_before.failed_original_predicates)==='["bytes_le_256_MiB"]'&&
       canonical(actual.APK_before.original_predicates)===canonical({
         regular:true,nlink_eq_1:true,uid_eq_1000:true,gid_eq_1000:true,mode_has_no_022:true,
         bytes_gt_0:true,bytes_le_256_MiB:false}),"only current size predicate false");
  need(actual.final_Main_guard_passed===true&&actualRaw.Main_before===actualRaw.Main_after&&
       actual.all_journal_FDs_closed===true&&actual.owned_FDs_acquired===actual.owned_FDs_closed&&
       actual.owned_FD_journal.length===actual.owned_FDs_acquired&&
       actual.owned_FD_journal.every(x=>x.closed===true&&x.close_error===null)&&
       actual.action_lock.attempts===1&&actual.action_lock.acquired===true&&actual.action_lock.released===true,
       "actual Main lock and FD cleanup");
  need(actual.APK_content_bytes_read===0&&actual.App_nonce_consumed===false&&
       actual.original_predicates_modified===false&&actual.original_file_limit_bytes===268435456,
       "metadata-only actual boundary");
  const nonceQualification=Q(input.nonce_authority,H)[config.id];
  const nonce=nonceQualification.nonce;
  need(/^[0-9a-f]{32}$/.test(nonce)&&nonce!==oldPacket.nonce,"fresh nonce syntax and no old reuse");
  need(nonceQualification&&nonceQualification.qualified===true&&
       nonceQualification.package===k.package&&nonceQualification.nonce===nonce&&
       nonceQualification.old_pool_count===919&&nonceQualification.new_pool_count===921&&
       nonceQualification.actual_generated_count===2&&
       nonceQualification.new_nonce_absent_from_all_old_919===true&&
       nonceQualification.new_nonce_present_once_in_exact_921===true,
       "caller must first qualify exact actual nonce producer and whole pools");
  const root="/home/alex/work/pocket4-current-cell02-"+config.id+"-metadata-01";
  const freshRoot="/home/alex/work/pocket4-current-cell02-"+config.id+"-metadata-02";
  const slot="__FRESH_"+config.id.toUpperCase()+"_METADATA02_NONCE__";
  const once=(raw,a,b)=>{need(raw.split(a).length===2,"unique exact replacement "+a);return raw.replace(a,b);};
  let source=once(input.old_source,root,freshRoot);
  source=once(source,oldPacket.nonce,nonce);
  source=once(source,"FILE_LIMIT = 256 * 1024 * 1024","FILE_LIMIT = 512 * 1024 * 1024");
  let stage=once(once(input.old_stage,root,freshRoot),oldPacket.nonce,nonce);
  need(source===once(input.source_template,slot,nonce)&&stage===once(input.stage_template,slot,nonce),
       "templates derived exactly from old authority");
  need(once(once(once(source,freshRoot,root),nonce,oldPacket.nonce),
       "FILE_LIMIT = 512 * 1024 * 1024","FILE_LIMIT = 256 * 1024 * 1024")===input.old_source,
       "full source inverse");
  need(once(once(stage,freshRoot,root),nonce,oldPacket.nonce)===input.old_stage,"full stage inverse");
  const expectedTransport=(packetRaw,stageRaw,sourceRaw)=>"import hashlib,json,sys\n"+
      "raw=sys.stdin.buffer.read(65537)\n"+
      "assert len(raw)=="+pin(packetRaw).bytes+" and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(pin(packetRaw).sha256)+"\n"+
      "stage="+JSON.stringify(stageRaw)+"\n"+
      "assert len(stage.encode())=="+pin(stageRaw).bytes+" and hashlib.sha256(stage.encode()).hexdigest()=="+JSON.stringify(pin(stageRaw).sha256)+"\n"+
      "scope={'__name__':'fixed_ticket12306_metadata_stage','__file__':'<verified-fixed-metadata-stage>'}\n"+
      "exec(compile(stage,'stage_execute.py','exec'),scope)\n"+
      "raise SystemExit(scope['main'](json.loads(raw),"+JSON.stringify(pin(sourceRaw).sha256)+"))\n";
  need(oldRequest.args.length===6&&oldRequest.args[5]===expectedTransport(oldRequest.stdin,input.old_stage,input.old_source),
       "exact original transport construction");
  const packet={...oldPacket,nonce,source};
  need(packet.discovery===oldPacket.discovery&&pin(packet.discovery).bytes===8332&&
       pin(packet.discovery).sha256==="9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886",
       "discovery unchanged");
  const packetRaw=JSON.stringify(packet)+"\n";
  need(pin(packetRaw).bytes<=65536&&pin(source).bytes<=32768,"unchanged stage/transport bounds");
  const transport=expectedTransport(packetRaw,stage,source);
  const request={...oldRequest,args:[...oldRequest.args.slice(0,5),transport],stdin:packetRaw,
      idempotency_key:"pocket4-current-cell02-"+config.id+"-metadata-02-20261106"};
  const requestRaw=JSON.stringify(request,null,2)+"\n";
  const oldEnv={...oldRequest,args:oldRequest.args.slice(0,5)};delete oldEnv.stdin;delete oldEnv.idempotency_key;
  const newEnv={...request,args:request.args.slice(0,5)};delete newEnv.stdin;delete newEnv.idempotency_key;
  need(canonical(oldEnv)===canonical(newEnv)&&request.timeout_seconds===240&&
       request.memory_max_bytes===536870912&&request.cpu_quota_percent===100&&request.nice===10,
       "exact original resource/command environment");
  need(!source.includes("__FRESH_")&&!stage.includes("__FRESH_"),"no future slots");
  const proof={
    schema:1,status:"ACTUAL_BOUND_SOURCE_ONLY_UNRUN",package:k.package,root:freshRoot,
    original_source:pin(input.old_source),original_request:pin(input.old_request),
    original_failed_metadata:pin(input.failed_metadata_original),current_fstat_actual:pin(input.fstat_actual),
    current_bytes:k.bytes,current_only_failed_predicate:"bytes_le_256_MiB",
    current_observation_not_retroactively_applied_to_old_failure:true,
    actual_APK_hash_performed_by_fstat_reader:false,
    nonce_qualification:nonceQualification,old_consumed_nonce_reused:false,
    production_change:"Only this exact package FILE_LIMIT 256 MiB -> 512 MiB; fresh ROOT and nonce.",
    source_inverse_exact:true,stage_inverse_exact:true,original_transport_reproduced:true,
    all_function_bodies_unchanged_after_ROOT_and_nonce_normalization:true,
    source:pin(source),stage:pin(stage),packet:pin(packetRaw),transport:pin(transport),request:pin(requestRaw),
    unchanged_limits:{aggregate_bytes:536870912,file_count:16,stream_chunk_bytes:65536,hash_seconds:45,
      whole_work_seconds:140,outer_timeout_seconds:240,memory_max_bytes:536870912,cpu_quota_percent:100,nice:10},
    admission:"Fresh PM identity/path observations and complete streamed APK hash still required by unchanged execute().",
    time_boundary:"No measured hash throughput. The original min(work deadline, hash-start+45s) remains; timeout fails without automatic retry.",
    old_failure_rewritten:false,Main_guards_changed:false,original_UID_and_held_identity_gates_changed:false,
    original_action_lock_and_finally_changed:false,Android_UI_actions:0,App_launches:0,
    Python_execution:"NOT_PERFORMED",metadata02_execution:"UNRUN",whole_app_production_ready:false,
    raw_actuals_reencoded:false
  };
  return {"read_target.py":source,"stage.py":stage,"stdin.json":packetRaw,"transport.py":transport,
    "exact-request.json":requestRaw,"binding-proof.json":JSON.stringify(proof,null,2)+"\n",
    "source01-to-bound02.diff":D(input.old_source,source,"read_target.py"),
    "stage01-to-bound02.diff":D(input.old_stage,stage,"stage.py"),
    "transport01-to-bound02.diff":D(oldRequest.args[5],transport,"transport.py")};
}
