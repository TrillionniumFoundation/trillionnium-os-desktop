"use strict";
function deriveStatusRelease01(oldRequestRaw,oldMaker,actualRaw,pureRaw,controllerEditsRaw,H){
  const pin=s=>({bytes:H.utf8(s).length,sha256:H.sha(s)});
  const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function need(v,m){if(!v)throw new Error(m);}
  function hasPin(s,n,h){need(typeof s==="string"&&eq(pin(s),{bytes:n,sha256:h}),"fixed input bytes/hash");}
  hasPin(oldRequestRaw,468543,"9b6a7be869ef3c71c9cf199cd5adad3440f3fc764b4c4f03762e3e09d664f5e8");
  hasPin(oldMaker,4105,"e1d3556d3b91cb1940a745ab6436f0309893571f474b2a24885e304d63b17621");
  hasPin(actualRaw,144339,"9fa8108aab968a2a7428906fea074c44010e7a12bac545d78361c04c27e9cae6");
  hasPin(pureRaw,2569,"e1e31a233000ba52362173007b1114a93289378844f58f99c3d7761f9bad31c4");
  hasPin(controllerEditsRaw,12034,"97b85f1544b94f6649e3c4a35472c755139115decc0b08ce36ec020465ca7cc4");
  const a=JSON.parse(actualRaw),p=JSON.parse(pureRaw),q=JSON.parse(oldRequestRaw),w=JSON.parse(q.stdin);
  need(a.state==="PASS"&&a.compiled_status_protocol_qualified===true&&a.commands.length===38&&
    a.commands.every(r=>r.returncode===0&&r.child_reaped===true&&r.owned_tree_cleanup_complete===true&&
    r.pidfd_closed===true&&r.output_fds_closed===true&&r.stdout_complete===true&&r.stderr_complete===true&&
    !r.timed_out&&r.first_error===null&&!r.secondary_errors.length)&&a.focused_tests_passed===15&&
    a.focused_result_gates.length===15&&a.focused_result_gates.every(r=>r.summary_and_independent_result_agree===true&&r.outer_results===1)&&
    a.host_child_lifecycle_controls.length===3&&a.host_child_lifecycle_controls.every(r=>r.passed===true)&&
    a.owned_child_reaper.final_children_empty===true&&a.owned_child_reaper.restored===true&&
    a.original_source_unchanged_after===true&&a.copied_source_unchanged_after===true&&a.control_source_unchanged_after===true&&
    a.owned_resource_gate.pass===true&&a.owned_resource_fd_closed===true&&!a.secondary_errors.length&&
    !a.dependency_changes.length&&!a.tool_changes.length&&!a.artifact_changes.length&&a.cargo_configs_unchanged_after===true&&
    a.source_delta.actual_source_file_count===502&&a.deployed===false&&a.production_ready===false,"complete actual debug02 authority");
  need(p.state==="PASS"&&p.controls.count===20&&p.controls.cases.length===20&&
    new Set(p.controls.cases.map(x=>x.name)).size===20&&p.controls.cases.every(x=>x.passed===true)&&
    p.all_acquired_input_fds_closed===true&&p.first_error===null&&!p.secondary_errors.length&&
    p.Status_or_Readiness_RPC===0&&p.Android_actions===0&&p.new_children===0&&p.filesystem_writes===0&&
    p.private_baseline_exported===false,"actual pure20 consumer boundary");
  const oldRoot="/home/alex/work/p4-st02-20261106",newRoot="/home/alex/work/p4-sr01-20261106";
  const oldKey="pocket4-native-status-lifecycle-readiness-compile-02-20261106";
  const newKey="pocket4-native-status-lifecycle-readiness-release-01-20261106";
  const edits=[];
  function replace(file,s,from,to){need(s.split(from).length===2,"unique replacement "+file);edits.push({file,old:from,new:to});return s.replace(from,to);}
  function line(file,s,name,value){const prior=s.split("\n").find(l=>l.startsWith(name));need(prior!==undefined,"constant line "+name);return replace(file,s,prior,name+value);}
  need(w.schema===1&&eq(Object.keys(w),["schema","stage","packet"])&&Object.keys(w.packet).length===8&&q.idempotency_key===oldKey,"old transport exact shape");
  const packet={...w.packet};
  for(const e of JSON.parse(controllerEditsRaw)){
    need(typeof e.before==="string"&&typeof e.after==="string"&&e.before!==e.after,"explicit controller edit");
    packet["compile_status.py"]=replace("compile_status.py",packet["compile_status.py"],e.before,e.after);
  }
  const scope=JSON.parse(packet["build-scope.json"]);
  need(scope.root===oldRoot&&scope.candidate_source_count===502&&scope.expected_ordinary_commands===38&&
    scope.expected_host_child_lifecycle_controls===3,"previous exact source-only build scope");
  scope.root=newRoot;
  scope.build_profile="release";
  scope.profile_authority={
    workspace:{path:"Cargo.toml",bytes:1996,sha256:"e33185d2fc5a65e0a4ed6df552e4f8f8f40c793ec07f7289ed27e3c0d5fa4e60",blob:"af55bc93ef30f0a8a4eac1e29dc364d0784b0dfc"},
    workspace_profile_override:false,cargo_switch:"--release",new_LTO_strip_or_panic_override:false,
    cargo_configs_must_be_absent:true,environment_profile_overrides_not_forwarded:true,
    six_executable_profiles_must_be_observed:true,dependencies_not_assumed_opt_level_3:true};
  scope.actual_debug02_parent={
    tree:"cb84df470d6d1fab3c781bb1ccecc5a3e44dea41",
    blob:"1ef0797cf5fac90dbdd7a06dd3dd2428fdaea7ca",
    path:oldRoot+"/attempt01/result.json",bytes:144339,
    sha256:"9fa8108aab968a2a7428906fea074c44010e7a12bac545d78361c04c27e9cae6",
    debug_ELFs_reused:false};
  scope.consumer.actual_pure20={
    tree:"a53d11553369adb96bdb22caf20eada948731d19",
    blob:"3a44530e188b607580186617ba23424e131c7609",
    bytes:2569,sha256:"e1e31a233000ba52362173007b1114a93289378844f58f99c3d7761f9bad31c4",
    production_runtime_qualification:false};
  packet["build-scope.json"]=replace("build-scope.json",packet["build-scope.json"],
    packet["build-scope.json"],JSON.stringify(scope,null,2)+"\n");
  let stage=replace("stage.py",w.stage,oldRoot,newRoot);
  const authorityLine=stage.split("\n").find(l=>l.startsWith("REUSED_AUTHORITY="));
  const authority=JSON.parse(authorityLine.slice("REUSED_AUTHORITY=".length));
  need(Object.keys(authority).length===5,"old five authorities");
  authority["status-debug02-result.json"]={path:oldRoot+"/attempt01/result.json",bytes:144339,
    sha256:"9fa8108aab968a2a7428906fea074c44010e7a12bac545d78361c04c27e9cae6",mode:384};
  stage=replace("stage.py",stage,authorityLine,"REUSED_AUTHORITY="+JSON.stringify(authority));
  for(const name of ["TRANSFERRED","EXPECTED"]){
    const prior=stage.split("\n").find(l=>l.startsWith(name+"="));
    const value=JSON.parse(prior.slice(name.length+1));
    value["compile_status.py"]=pin(packet["compile_status.py"]);
    value["build-scope.json"]=pin(packet["build-scope.json"]);
    if(name==="EXPECTED")value["status-debug02-result.json"]={bytes:144339,sha256:"9fa8108aab968a2a7428906fea074c44010e7a12bac545d78361c04c27e9cae6"};
    stage=replace("stage.py",stage,prior,name+"="+JSON.stringify(value));
  }
  stage=replace("stage.py",stage,"len(REUSED_AUTHORITY)==5 and len(EXPECTED)==13","len(REUSED_AUTHORITY)==6 and len(EXPECTED)==14");
  stage=replace("stage.py",stage,"All five fixed actual/source inputs","All six fixed actual/source inputs");
  const stdin=JSON.stringify({schema:1,stage,packet});
  let boundary=line("transport.py",q.args[3],"EXPECTED=",JSON.stringify(pin(stdin)));
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
    for(const e of edits.filter(e=>e.file===file).reverse()){
      need(inverse.split(e.new).length===2,"unique inverse "+file);inverse=inverse.replace(e.new,e.old);
    }
    need(inverse===original[file],"complete inverse "+file);
  }
  for(const name of Object.keys(packet))if(!["compile_status.py","build-scope.json"].includes(name))
    need(packet[name]===w.packet[name],"unchanged production source "+name);
  need(eq(JSON.parse(packet["expected-status-manifest.json"]),JSON.parse(w.packet["expected-status-manifest.json"])),"same502manifest");
  need(request.executable===q.executable&&eq(request.args.slice(0,3),q.args.slice(0,3))&&
    request.cwd===q.cwd&&request.cpu_quota_percent===q.cpu_quota_percent&&request.memory_max_bytes===q.memory_max_bytes&&
    request.nice===q.nice&&request.timeout_seconds===q.timeout_seconds,"unchanged envelope constraints");
  return {request,raw,stdin,stage,boundary,maker,packet,edits,oldRoot,newRoot,oldKey,newKey};
}
