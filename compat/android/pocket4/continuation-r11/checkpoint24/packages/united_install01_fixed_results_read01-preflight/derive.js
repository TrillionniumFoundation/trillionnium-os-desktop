function deriveOwnedHelperTwoReports(oldSource,oldRequestRaw,label,stdoutRaw,terminalRaw,H) {
 const need=(x,m)=>{if(!x)throw Error(m);},pin=s=>({bytes:H.utf8(s).length,sha256:H.sha256(H.utf8(s))});
 need(H.gitBlob(H.utf8(oldSource))==="888527619ff962d5eabf8c999313a6823899a5ce","original exact fixed two reader");
 need(["united","hilton","ticket12306"].includes(label),"fixed three owned helpers");
 const term=JSON.parse(terminalRaw),parts=stdoutRaw.trimEnd().split("\n").map(x=>JSON.parse(x));
 need(parts.length===2&&parts.every(x=>x.ok===true&&x.error===null&&x.secondary_errors.length===0)&&term.state==="succeeded"&&term.exit_code===0&&term.output_complete&&term.output_durable&&!term.timed_out&&!term.cancelled&&!term.automatic_retry,"complete actual successful terminal and summaries");
 need(term.log_bytes.stdout.seen===pin(stdoutRaw).bytes&&term.log_bytes.stdout.stored===pin(stdoutRaw).bytes&&term.log_bytes.stderr.seen===0&&term.log_bytes.stderr.stored===0,"complete logs");
 const specs={result:parts[0].result,stage_result:parts[1].stage_result};
 const root="/home/alex/work/pocket4-owned-"+label+"-qa-r1-install-state-"+(label==="united"?"01":"02");
 for(const [key,leaf]of [["result","result.json"],["stage_result","stage-result.json"]]) {
  const s=specs[key];need(s.path===root+"/"+leaf&&Number.isSafeInteger(s.bytes)&&s.bytes>0&&s.bytes<=1048576&&/^[a-f0-9]{64}$/.test(s.sha256),"exact fixed report path and pin");
 }
 let source=oldSource;const edits=[];
 function replace(a,b){need(source.split(a).length===2,"unique edit");source=source.replace(a,b);edits.push({before:a,after:b});}
 function constant(name,value){const old=source.split("\n").find(x=>x.startsWith(name+"="));need(old!==undefined,"constant");replace(old,name+"="+JSON.stringify(value));}
 replace('"""Collect exactly two pinned owned Hilton failure reports; no runtime actions."""','"""Collect exactly two pinned owned '+label+' successful reports; no runtime actions."""');
 constant("FILES",specs);constant("AUTHORITY_RAW",{stdout:stdoutRaw,terminal:terminalRaw});constant("AUTHORITY_PINS",{stdout:pin(stdoutRaw),terminal:pin(terminalRaw)});constant("JOB",term.job_id);
 replace("'kind':'pocket4-owned-hilton-install01-fixed-two-results-read01'","'kind':'pocket4-owned-"+label+"-install"+(label==="united"?"01":"02")+"-fixed-two-results-read01'");
 replace("t['state']=='failed' and t['exit_code']==1","t['state']=='succeeded' and t['exit_code']==0");
 replace("'stdout':{'seen':919,'stored':919}","'stdout':{'seen':"+pin(stdoutRaw).bytes+",'stored':"+pin(stdoutRaw).bytes+"}");
 replace("'EXACT_COMPLETE_FAILED_TERMINAL'","'EXACT_COMPLETE_SUCCESSFUL_TERMINAL'");
 replace("all(x['ok'] is False for x in summaries)","all(x['ok'] is True for x in summaries)");
 let inverse=source;for(const e of [...edits].reverse()){need(inverse.split(e.after).length===2,"unique inverse");inverse=inverse.replace(e.after,e.before);}
 need(inverse===oldSource,"complete inverse");
 const old=JSON.parse(oldRequestRaw);need(old.stdin===oldSource&&old.timeout_seconds===30&&old.memory_max_bytes===134217728,"original bounded reader envelope");
 const q={...old,stdin:source,idempotency_key:"p4-"+label+"-fixed-two-results-read01-"+pin(source).sha256.slice(0,16)};
 return {source,request:JSON.stringify(q,null,2)+"\n",edits,proof:{schema:1,source:pin(source),request:pin(JSON.stringify(q,null,2)+"\n"),original_reader_full_inverse:true,read_exact_file_body_unchanged:true,actual_terminal_job:term.job_id,actual_stdout:pin(stdoutRaw),actual_terminal:pin(terminalRaw),fixed_reports:specs,read_only:true,Main_reads:0,Android_commands:0,children:0,writes:0,installation_outcome_qualified:false}};
}