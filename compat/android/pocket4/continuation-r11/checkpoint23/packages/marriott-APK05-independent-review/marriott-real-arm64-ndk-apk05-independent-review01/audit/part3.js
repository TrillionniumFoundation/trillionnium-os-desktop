function auditAPK05Part3(raw,derived,terminalRaw,summaryRaw,U) {
  const failures=[];let checks=0;const ok=(v,m)=>{checks++;if(!v)failures.push(m);};
  const pin=s=>({bytes:U.utf8(s).length,sha256:U.sha256(U.utf8(s)),git_blob_sha:U.gitBlob(U.utf8(s))});
  const expected={bytes:9811685,sha256:"d8eb53c924fa6a76bee19304bd8538bf2a57306b7e9bd6a55df8787d4ea33411",git_blob_sha:"b9e554da10457c28186be38db3c8916bc7edb79f"};
  const original=pin(raw);ok(JSON.stringify(original)===JSON.stringify(expected),"complete original raw SHA/Git");
  const termPin=pin(terminalRaw),outPin=pin(summaryRaw);
  ok(termPin.bytes===729&&termPin.sha256==="7df30068ee3849645f69085f9c16f1bc1094744fbacc26d765a09be0c21ded3d"&&termPin.git_blob_sha==="58a7513006a1085082c0b2d4f94c0d6c492a0ec1","independent exact terminal bytes");
  ok(outPin.bytes===228&&outPin.sha256==="7e22891b785542a355a55f67b2235180d1dd216d176871338e88ebd6a2d706f6"&&outPin.git_blob_sha==="cb42b8b497a934e40aedd2c6e9c2d708edb7d6ea","independent exact stdout bytes");
  const t=JSON.parse(terminalRaw),o=JSON.parse(summaryRaw);
  ok(t.job_id==="1a1b299fafc-fc05-7edb"&&t.state==="succeeded"&&t.exit_code===0&&t.output_complete===true&&t.output_durable===true&&t.terminal_publication_confirmed===true&&t.timed_out===false&&t.cancelled===false&&t.automatic_retry===false,"independent successful terminal");
  for(const k of ["stdout","stderr"])ok(t.log_synced[k]===true&&t.log_truncated[k]===false&&t.log_errors[k]===null&&t.log_bytes[k].seen===(k==="stdout"?228:0)&&t.log_bytes[k].stored===(k==="stdout"?228:0),"full durable "+k);
  ok(o.success===true&&o.path==="/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-05-20261106/build-result.json"&&o.bytes===expected.bytes&&o.sha256===expected.sha256&&o.first_error===null,"summary points to full original");
  const slot="CFG = None  # The immutable packet generator fills this exactly once.";
  const generated=derived.template.replace(slot,"CFG = json.loads(r'''"+derived.config+"''')");
  ok(derived.template.split(slot).length===2&&generated===derived.build,"exact entire source/config reproduction");
  const q=JSON.parse(derived.request),bp=pin(derived.build),cp=pin(derived.config);
  ok(q.stdin===derived.build&&q.idempotency_key==="p4-marriott-real-arm64-ndk-apk-build05-"+bp.sha256.slice(0,16),"whole request/source/key reproduction");
  ok(bp.bytes===465074&&bp.sha256==="ad576973a9afe9044ec6aea493c3cd41da254256eb54f593e63e3473900cb955"&&cp.bytes===380712&&cp.sha256==="51ae5c50bea97d087a72feeecb21dd7d6c5687d14498fabc2bd60e62245ab17b","exact frozen build/config pins");
  ok(JSON.stringify(q.args)===JSON.stringify(["-I","-B","-"])&&q.executable==="/usr/bin/python3"&&q.host==="pocket4"&&q.timeout_seconds===660&&q.memory_max_bytes===1073741824&&q.cpu_quota_percent===100&&q.nice===15,"original static build envelope unchanged");
  return {checks,failures,original,terminal:{...termPin,job_id:t.job_id},stdout:outPin,outer_terminal_closes_process_lifetime:true,raw_not_JSON_resequenced:true,exact_source_request_reproduction:true};
}