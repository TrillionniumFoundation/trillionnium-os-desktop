function qualifyNonceAuthority(a,H) {
  const need=(v,m)=>{if(!v)throw Error(m);};
  const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s)),git_blob_sha1:H.gitBlob(H.utf8(s))});
  const expected={
    stdout:[852,"3da40b6094acc06425ee522d6318525454702f2f98691c6643118da60375dec5"],
    terminal:[729,"8a74b83232ea66985938c2584eec9f49e3dafb35f4cdd705bf1e969680dbd408"],
    global919:[34925,"0a796c3907ea9fb3cd834752ef4b52f7728f0eca4fe0b4ad36d10b4f4aeb8d45"],
    global921:[35001,"735f9acaf4100e82bf7bfdacbecf9510286b1099f8dee92bf668e942e8780bac"],
    generator:[33847,"b6fc31724690e0b7361871818b4d298e4bea98dde652691b25d3686b9eb743f5"],
    catalog:[694,"b69ceff9156987a4b88d6da29a532caa324e3083085f57aff1ef5b38efe4df2c"],
    request:[36555,"d8bb67d281cde6810a2e3ded49aa4907e014ddddf169863bf98b5420f174f72b"],
    admission:[1497,"5311eb8bde8763e79bb6d8f987a4212d6eb21d7db5fdeb56eedf33f89d03c10a"]
  };
  for(const [key,[bytes,sha]]of Object.entries(expected))
    need(typeof a[key]==="string"&&pin(a[key]).bytes===bytes&&pin(a[key]).sha256===sha,"exact nonce authority "+key);
  const report=JSON.parse(a.stdout),terminal=JSON.parse(a.terminal),old=JSON.parse(a.global919),
        all=JSON.parse(a.global921),catalog=JSON.parse(a.catalog),request=JSON.parse(a.request),admission=JSON.parse(a.admission);
  const job="1a1b2b9681b-fc05-7f7a";
  need(terminal.job_id===job&&terminal.state==="succeeded"&&terminal.exit_code===0&&
       terminal.timed_out===false&&terminal.cancelled===false&&terminal.automatic_retry===false&&
       terminal.output_complete===true&&terminal.output_durable===true&&terminal.audit_recorded===true&&
       terminal.terminal_publication_confirmed===true&&terminal.terminal_publication_protocol===1&&
       terminal.log_synced.stdout===true&&terminal.log_synced.stderr===true&&
       terminal.log_errors.stdout===null&&terminal.log_errors.stderr===null&&
       terminal.log_truncated.stdout===false&&terminal.log_truncated.stderr===false&&
       terminal.log_bytes.stdout.seen===852&&terminal.log_bytes.stdout.stored===852&&
       terminal.log_bytes.stderr.seen===0&&terminal.log_bytes.stderr.stored===0,"actual nonce terminal");
  need(admission.job.id===job&&admission.reused===false&&admission.launch.ok===true&&
       admission.job.launch_error===null&&admission.job.launch_state==="launched"&&
       request.stdin===a.generator&&admission.job.idempotency_key===request.idempotency_key&&
       admission.job.host===request.host&&admission.job.executable===request.executable&&
       JSON.stringify(admission.job.args)===JSON.stringify(request.args),"same admitted generator");
  const labels=["douyin_metadata02","wechat_metadata02"],packages=["com.ss.android.ugc.aweme","com.tencent.mm"];
  need(report.schema==="pocket4-current-cell02-large-apk-metadata-nonce-material-v1"&&
       report.source_sha256===pin(a.generator).sha256&&report.target_catalog_sha256===pin(a.catalog).sha256&&
       report.count===2&&report.draw_count===2&&report.source_uid===1000&&report.no_redraw===true&&
       report.excluded_all_919===true&&report.excluded_count===919&&report.global_count_after===921&&
       JSON.stringify(report.labels)===JSON.stringify(labels)&&
       ["Android_commands","child_processes","file_writes","UI_actions"].every(k=>report[k]===0)&&
       report.whole_app_production_ready===false,"actual nonce output");
  need(Array.isArray(old)&&old.length===919&&new Set(old).size===919&&
       Array.isArray(all)&&all.length===921&&new Set(all).size===921&&
       [...old,...all].every(x=>typeof x==="string"&&/^[0-9a-f]{32}$/.test(x))&&
       JSON.stringify(old)===JSON.stringify([...old].sort())&&JSON.stringify(all)===JSON.stringify([...all].sort()),
       "whole nonce pools unique and sorted");
  const compact=JSON.stringify(old)+"\n";
  need(H.sha256(H.utf8(compact))===report.excluded_compact_sha256&&
       report.excluded_compact_sha256==="91578219c996818871d796002f735382834e522e259fa6db8dc1c9d6427d259f",
       "complete 919 exclusion SHA");
  const embedded=a.generator.match(/^EXCLUDED=(.*)$/m);
  need(embedded&&JSON.stringify(JSON.parse(embedded[1]))===JSON.stringify(old),"all old exclusions embedded");
  need(Array.isArray(report.generated)&&report.generated.length===2&&catalog.targets.length===2,
       "two ordered generated nonces and targets");
  const values=report.generated.map((row,i)=>{
    need(row.label===labels[i]&&row.package===packages[i]&&
         catalog.targets[i].label===labels[i]&&catalog.targets[i].package===packages[i]&&
         /^[0-9a-f]{32}$/.test(row.nonce)&&row.nonce!=="0".repeat(32)&&!old.includes(row.nonce),
         "exact generated package nonce "+i);
    return row.nonce;
  });
  need(new Set(values).size===2&&JSON.stringify([...old,...values].sort())===JSON.stringify(all),"exact 919 plus 2 equals 921");
  const result={};
  for(let i=0;i<2;i++) result[["douyin","wechat"][i]]={
    qualified:true,package:packages[i],label:labels[i],nonce:values[i],job_id:job,
    old_pool_count:919,new_pool_count:921,actual_generated_count:2,
    new_nonce_absent_from_all_old_919:true,new_nonce_present_once_in_exact_921:true,
    one_draw_per_label:true,no_redraw:true,metadata02_not_dispatched_by_binder:true,
    authority_pins:Object.fromEntries(Object.entries(a).map(([k,v])=>[k,pin(v)])),
    raw_actuals_reencoded:false
  };
  return result;
}
