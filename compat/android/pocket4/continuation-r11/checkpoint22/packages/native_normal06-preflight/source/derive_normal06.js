
return function derive(oldRequestText, baselineText, H){
 const need=(x,m)=>{if(!x)throw Error(m)},sha=s=>H.sha256(H.utf8(s)),pin=s=>({bytes:H.utf8(s).length,sha256:sha(s)});
 need(sha(oldRequestText)==="21bb4053bea941ae32efb01c560180e241dd546e4d2f5007142a8720649794e2","original Normal05 exact request");
 need(sha(baselineText)==="107bf1487ace30a38c113057812a0a18415e3430640f11db0b5131e462d05269","actual baseline02 original stdout");
 const old=JSON.parse(oldRequestText),packet=JSON.parse(old.stdin),actual=JSON.parse(baselineText);
 const files={...packet.files},changes=[],once=(body,from,to,label)=>{
   need(body.split(from).length===2,"single preimage "+label);
   changes.push({label,from,to});return body.replace(from,to);
 };
 const replace=(name,from,to,label)=>{files[name]=once(files[name],from,to,name+":"+label)};
 const oldRoot="typed-ingress-framework-provider-build-05-20261106",newRoot="typed-ingress-framework-provider-build-06-20261106";
 need(Object.keys(actual.protected_processes).sort().join(",")==="android_init,daemon,launcher,owner_intermediary,presenter,surfaceflinger,system_server,zygote64","eight actual protected roles");
 const identities={};
 for(const[role,r]of Object.entries(actual.protected_processes)){
  need(Object.keys(r).sort().join(",")==="cgroup,host_pid,namespace_pids,namespaces,parent_host_pid,root_identity,start_ticks,uids","actual projection closed shape "+role);
  need(Number.isSafeInteger(r.host_pid)&&Number.isSafeInteger(r.start_ticks)&&r.cgroup.length===1&&r.cgroup.every(x=>/^0::\/[^\n\r\0]*$/.test(x)),"actual identity type "+role);
  identities[role]={pid:r.host_pid,start_ticks:r.start_ticks,ppid:r.parent_host_pid,uids:r.uids,namespace_pids:r.namespace_pids,cgroup:r.cgroup.join("\n")+"\n",namespaces:r.namespaces,root_identity:r.root_identity};
 }
 const line=files["main_snapshot.py"].match(/^EXPECTED=json.loads\(.*\)$/m);
 need(line&&line.length===1,"old exact identity literal");
 replace("main_snapshot.py",line[0],"EXPECTED=json.loads("+JSON.stringify(JSON.stringify(identities))+")","actual eight identity projection");
 replace("main_snapshot.py","3918e517ac2ce2e2ee19aa862ac60b7631e48bf383c14788a1db2c0e0f4bccb7","a949d51bad870db6e95941849faac1c91e95c6fe574bf270702c6c039fa4313e","identity source");
 replace("main_snapshot.py","b49bbb4276c5a95de610956c878b0d23a1abdde0a8411bea310dbaca585396a6","107bf1487ace30a38c113057812a0a18415e3430640f11db0b5131e462d05269","actual identity receipt");
 for(const n of ["main_snapshot.py","pure_controls.py","fenced_build.py"]){
  const oldBody=files[n];
  files[n]=files[n].replaceAll("ACTUAL_READ02","ACTUAL_BASELINE02").replaceAll("actual_read02_stdout_sha256","actual_baseline02_stdout_sha256").replaceAll("seven-role","eight-role").replaceAll("seven_roles","eight_roles").replaceAll("current seven process","current eight process");
  if(oldBody!==files[n])changes.push({label:n+": provenance labels and eight-role wording",before_sha256:sha(oldBody),after_sha256:sha(files[n])});
 }
 replace("main_snapshot.py","len(rows) == 7, 'FIXED_SEVEN_ROLES_INCOMPLETE'","len(rows) == 8, 'FIXED_EIGHT_ROLES_INCOMPLETE'","eight-role count");
 replace("capture_lifecycle.py","PROTECTED_PIDS = frozenset((3588093, 3588022, 3588089, 3588024, 3588912, 90360, 90516))","PROTECTED_PIDS = frozenset(("+Object.values(identities).map(r=>r.pid).join(", ")+"))","actual protected PIDs");
 replace("pure_controls.py","len(passed) == len(set(passed)) == 45","len(passed) == len(set(passed)) == 46","one additional actual protected role");
 replace("fenced_build.py","{'android_init', 'daemon', 'launcher', 'presenter', 'surfaceflinger', 'zygote64', 'system_server'}","{'android_init', 'daemon', 'launcher', 'owner_intermediary', 'presenter', 'surfaceflinger', 'zygote64', 'system_server'}","closed eight-role result gate");
 for(const n of ["framework_build.py","fenced_build.py"])replace(n,oldRoot,newRoot,"fresh isolated output root");
 replace("root_snapshot_supervisor.py","the seven protected Main PIDs","the eight protected Main PIDs","actual exclusion wording");
 const oldPins=Object.fromEntries(Object.entries(packet.files).map(([n,s])=>[n,pin(s)]));
 for(const[n,c]of [["root_snapshot_supervisor.py","capture_lifecycle.py"],["root_snapshot_supervisor.py","main_snapshot.py"],["fenced_build.py","framework_build.py"],["fenced_build.py","capture_lifecycle.py"],["fenced_build.py","root_snapshot_supervisor.py"],["fenced_build.py","main_snapshot.py"]])
  replace(n,oldPins[c].sha256,sha(files[c]),"rebind "+c);
 const expected=Object.fromEntries(Object.entries(files).map(([n,s])=>[n,pin(s)]));
 let stage=once(packet.stage,oldRoot,newRoot,"stage fresh root");
 stage=once(stage,"EXPECTED = "+JSON.stringify(oldPins),"EXPECTED = "+JSON.stringify(expected),"stage exact propagated source pins");
 stage=once(stage,"controls['passed']!=45","controls['passed']!=46","stage actual 46 controls");
 const wire=JSON.stringify({schema:1,stage,files})+"\n";
 let boundary=old.args[3];
 boundary=once(boundary,"WIRE_BYTES = "+H.utf8(old.stdin).length,"WIRE_BYTES = "+H.utf8(wire).length,"wire length");
 boundary=once(boundary,sha(old.stdin),sha(wire),"wire sha");
 boundary=once(boundary,"STAGE_BYTES = "+H.utf8(packet.stage).length,"STAGE_BYTES = "+H.utf8(stage).length,"stage length");
 boundary=once(boundary,sha(packet.stage),sha(stage),"stage sha");
 const request={...old,args:[...old.args],stdin:wire,idempotency_key:old.idempotency_key.replace("-05-20261106","-06-20261106")};
 request.args[3]=boundary;
 need(request.idempotency_key!==old.idempotency_key,"fresh idempotency key");
 need(request.memory_max_bytes===10737418240&&request.cpu_quota_percent===200&&request.timeout_seconds===6400&&request.nice===10,"existing resource envelope");
 const requestText=JSON.stringify(request,null,2)+"\n";
 const changed=Object.entries(files).filter(([n,s])=>s!==packet.files[n]).map(([n,s])=>({name:n,before:pin(packet.files[n]),after:pin(s)}));
 const unchanged=Object.keys(files).filter(n=>files[n]===packet.files[n]);
 return {files,stage,wire,boundary,request,requestText,expected,identities,changes,changed,unchanged,proof:{
  schema:1,prior_request:pin(oldRequestText),actual_baseline02:pin(baselineText),request:pin(requestText),wire:pin(wire),stage:pin(stage),
  changed,unchanged,protected_roles:Object.keys(identities),controls_expected:46,capture_lifecycle_controls_expected:4,
  main_resource_contract_unchanged:true,build_memory_max_bytes:10737418240,build_cpu_quota_percent:200,build_nice:10,minimum_MemAvailable_bytes:16106127360,
  original_build_targets:["framework-minus-apex","libandroid_runtime"],source_projection_restoration_unchanged:true,
  historical_QA_flags_describe_this_snapshot_only:"This read-only build fence does not qualify a QA epoch. Its protected identities come from the independently successful baseline02.",
  Main_actions:0,Android_runtime_actions:0,actual_execution_pending:true,production_ready:false
 }};
}
