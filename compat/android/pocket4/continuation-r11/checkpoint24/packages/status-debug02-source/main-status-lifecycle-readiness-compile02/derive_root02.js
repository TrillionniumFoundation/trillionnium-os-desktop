"use strict";
function deriveStatusCompile02(oldRequestRaw,oldMaker,actualRaw,pureRaw,H){
  const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha(s)});
  const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function need(v,m){if(!v)throw new Error(m);}
  function hasPin(s,n,h){need(typeof s==="string"&&eq(pin(s),{bytes:n,sha256:h}),"fixed input bytes/hash");}
  hasPin(oldRequestRaw,468678,"db32d3d7abb8821957bd41348784d0abe214b447bfb6962771b0a45c9c13facd");
  hasPin(oldMaker,4105,"f65ac9a4b9603fbf77af51f82290318fdf2d7429aac2098145a00af1917bd5fe");
  hasPin(actualRaw,129588,"95e5075de61ee94e9789c4632db9eab77e29e751df8c08da33f2b633e0b9d796");
  hasPin(pureRaw,2569,"e1e31a233000ba52362173007b1114a93289378844f58f99c3d7761f9bad31c4");
  const a=JSON.parse(actualRaw),p=JSON.parse(pureRaw);
  need(a.state==="FAIL"&&a.commands.length===32&&a.commands.slice(0,31).every(r=>r.returncode===0&&r.child_reaped===true&&r.owned_tree_cleanup_complete===true&&!r.timed_out&&r.first_error===null&&!r.secondary_errors.length),"exact compile01 prefix");
  const failed=a.commands[31];
  need(failed.label==="projection-test-8"&&failed.returncode===101&&failed.child_reaped===true&&failed.owned_tree_cleanup_complete===true&&!failed.timed_out&&failed.first_error.stage==="leader_exit_status","exact first failed CLI command");
  hasPin(failed.stderr,375,"c8c138b30ee36a3fa9a2455fa8f7c113a9a371bbe2a165f91c3b158ac30e5da7");
  need(failed.stderr.includes("path must be shorter than SUN_LEN")&&a.focused_result_gates.length===8&&a.host_child_lifecycle_controls.length===3&&a.host_child_lifecycle_controls.every(x=>x.passed===true)&&a.owned_child_reaper.final_children_empty===true&&a.owned_child_reaper.restored===true&&a.original_source_unchanged_after===true&&a.copied_source_unchanged_after===true&&a.control_source_unchanged_after===true&&a.owned_resource_gate.pass===true&&!a.secondary_errors.length&&!a.dependency_changes.length&&!a.tool_changes.length&&!a.artifact_changes.length&&a.cargo_configs_unchanged_after===true,"original failure and cleanup authority");
  need(p.state==="PASS"&&p.controls.count===20&&p.controls.cases.length===20&&new Set(p.controls.cases.map(x=>x.name)).size===20&&p.controls.cases.every(x=>x.passed===true)&&p.input_fd_journal.acquired===6&&p.input_fd_journal.closed===6&&p.all_acquired_input_fds_closed===true&&p.first_error===null&&!p.secondary_errors.length&&p.Status_or_Readiness_RPC===0&&p.Android_actions===0&&p.new_children===0&&p.filesystem_writes===0&&p.private_baseline_exported===false,"actual pure20");
  const q=JSON.parse(oldRequestRaw),w=JSON.parse(q.stdin);
  const oldRoot="/home/alex/work/pocket4-native-status-lifecycle-readiness-compile-01-20261106";
  const newRoot="/home/alex/work/p4-st02-20261106";
  const oldKey="pocket4-native-status-lifecycle-readiness-compile-01-20261106";
  const newKey="pocket4-native-status-lifecycle-readiness-compile-02-20261106";
  const edits=[];
  function replace(file,s,from,to){need(s.split(from).length===2,"unique replacement "+file);edits.push({file,old:from,new:to});return s.replace(from,to);}
  function line(file,s,name,value){const prior=s.split("\n").find(l=>l.startsWith(name));need(prior!==undefined,"constant line "+name);return replace(file,s,prior,name+value);}
  need(w.schema===1&&eq(Object.keys(w),["schema","stage","packet"])&&Object.keys(w.packet).length===8&&q.idempotency_key===oldKey,"old transport exact shape");
  const packet={...w.packet};
  packet["compile_status.py"]=replace("compile_status.py",packet["compile_status.py"],oldRoot,newRoot);
  packet["build-scope.json"]=replace("build-scope.json",packet["build-scope.json"],oldRoot,newRoot);
  let stage=replace("stage.py",w.stage,oldRoot,newRoot);
  for(const name of ["TRANSFERRED","EXPECTED"]){
    const prior=stage.split("\n").find(l=>l.startsWith(name+"="));
    const value=JSON.parse(prior.slice(name.length+1));
    value["compile_status.py"]=pin(packet["compile_status.py"]);value["build-scope.json"]=pin(packet["build-scope.json"]);
    stage=replace("stage.py",stage,prior,name+"="+JSON.stringify(value));
  }
  const stdin=JSON.stringify({schema:1,stage,packet});
  let boundary=q.args[3];
  boundary=line("transport.py",boundary,"EXPECTED=",JSON.stringify(pin(stdin)));
  boundary=line("transport.py",boundary,"STAGE=",JSON.stringify(pin(stage)));
  const request={...q,args:[...q.args.slice(0,3),boundary],stdin,idempotency_key:newKey};
  const raw=JSON.stringify(request,null,2)+"\n";
  let maker=oldMaker;
  const expected=Object.fromEntries(Object.entries(packet).map(([name,s])=>[name,pin(s)]));
  for(const [name,value] of [["EXPECTED",expected],["STAGE",pin(stage)],["WIRE",pin(stdin)],["REQUEST",pin(raw)],["BOUNDARY",boundary]]){
    maker=line("make_request.js",maker,"  const "+name+" = ",JSON.stringify(value)+";");
  }
  maker=replace("make_request.js",maker,oldKey,newKey);
  const original={"compile_status.py":w.packet["compile_status.py"],"build-scope.json":w.packet["build-scope.json"],"stage.py":w.stage,"transport.py":q.args[3],"make_request.js":oldMaker};
  const derived={"compile_status.py":packet["compile_status.py"],"build-scope.json":packet["build-scope.json"],"stage.py":stage,"transport.py":boundary,"make_request.js":maker};
  for(const [file,s] of Object.entries(derived)){
    let inverse=s;
    for(const e of edits.filter(e=>e.file===file).reverse()){need(inverse.split(e.new).length===2,"unique inverse "+file);inverse=inverse.replace(e.new,e.old);}
    need(inverse===original[file],"complete inverse "+file);
  }
  for(const name of Object.keys(packet))if(!["compile_status.py","build-scope.json"].includes(name))need(packet[name]===w.packet[name],"unchanged production source "+name);
  need(request.executable===q.executable&&eq(request.args.slice(0,3),q.args.slice(0,3))&&request.cwd===q.cwd&&request.cpu_quota_percent===q.cpu_quota_percent&&request.memory_max_bytes===q.memory_max_bytes&&request.nice===q.nice&&request.timeout_seconds===q.timeout_seconds,"unchanged envelope constraints");
  return {request,raw,stdin,stage,boundary,maker,packet,edits,oldRoot,newRoot,oldKey,newKey};
}
