function auditAPK05Part1(r,c,U,B) {
  const failures=[];let checks=0;
  const ok=(v,msg)=>{checks++;if(!v)failures.push(msg);};
  const canon=v=>JSON.stringify(v,(_,x)=>x&&typeof x==="object"&&!Array.isArray(x)?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a.localeCompare(b))):x);
  const eq=(a,b)=>canon(a)===canon(b);
  const pin=s=>({bytes:U.utf8(s).length,sha256:U.sha256(U.utf8(s))});
  const fields=["path","resolved_path","device","inode","mode","uid","gid","nlink","bytes","mtime_ns","ctime_ns","sha256"];
  const tuple=v=>Object.fromEntries(fields.map(k=>[k,v[k]]));
  const subset=(v,x)=>Object.keys(x).every(k=>eq(v[k],x[k]));
  ok(r.schema===1&&r.kind==="p4-marriott-real-arm64-ndk-apk-build05"&&r.root===c.root,"exact kind/root");
  ok(r.success===true&&eq(r.errors,[])&&eq(r.post_input_errors,[])&&eq(r.input_FD_close_failures,[]),"no errors");
  for(const k of ["all_children_reaped","all_inputs_unchanged","all_tracked_input_FDs_closed","original_default_zero_retained"])ok(r[k]===true,k);
  for(const k of ["ARM64_objects_executed","ART_runtime_qualified","commercial_App_reproduction_asserted","feature_default_enabled","installed"])ok(r[k]===false,k);
  ok(r.Android_actions===0&&r.Main_actions===0,"no Main/Android actions");
  ok(r.commands.length===50&&r.objects.length===16&&r.linked_libraries.length===7,"50/16/7 counts");
  ok(r.input_FD_event_count===10902,"10902 input FD events");
  const execs=new Set([c.compiler.path,c.linker.path,...Object.values(c.java_tools).map(x=>x.path)]);
  let stderrCommands=0;
  for(const [i,x] of r.commands.entries()){
    const p="command "+i+" ";
    ok(x.cwd===c.root&&Array.isArray(x.argv)&&execs.has(x.argv[0]),p+"cwd/executable");
    ok(x.child_started===true&&x.child_reaped===true&&x.returncode===0&&x.timed_out===false,p+"exited zero/joined");
    ok(x.first_error===null&&eq(x.secondary_errors,[])&&eq(x.descendants,[]),p+"no errors/descendants");
    for(const k of ["kill_attempted","owned_group_kill_attempted","owned_group_kill_completed","leader_unreaped_before_group_cleanup","pidfd_closed","output_fds_closed","owned_tree_cleanup_complete"])ok(x[k]===true,p+k);
    ok(x.leader_alive_before_group_cleanup===false,p+"leader not alive before group cleanup");
    for(const k of ["leader_observed_before_reap","leader_observed_without_reap"])ok(eq(x[k],{code:1,pid:x.pid,status:0}),p+k);
    for(const channel of ["stdout","stderr"]){
      ok(typeof x[channel]==="string"&&x[channel+"_complete"]===true,p+channel+" complete");
      const actual=pin(x[channel]);
      ok(actual.bytes===x[channel+"_bytes"]&&actual.sha256===x[channel+"_sha256"],p+channel+" whole pin");
    }
    if(x.stderr_bytes)stderrCommands++;
    ok(typeof x.cleanup_elapsed_seconds==="number"&&x.cleanup_elapsed_seconds>=0&&x.cleanup_elapsed_seconds<=5,p+"cleanup bound");
    ok(Number.isFinite(x.timeout_seconds)&&x.timeout_seconds>0&&x.timeout_seconds<=90,p+"timeout bound");
  }
  const compile=r.commands.filter(x=>x.argv[0]===c.compiler.path),link=r.commands.filter(x=>x.argv[0]===c.linker.path);
  ok(compile.length===32&&link.length===8,"32 compiler/8 linker/10 APK commands");
  for(const x of compile){
    const target=x.argv[x.argv.indexOf("-target")+1];
    ok(["aarch64-linux-android10000","aarch64-linux-android21"].includes(target),"exact ARM64 compiler target");
    ok(x.argv.includes("-nostdlibinc")&&x.argv.includes("-fPIC"),"compiler explicit Android include/PIC");
  }
  ok(eq(r.compiler_before,{...c.compiler.actual_C20_tuple,nlink:1}),"actual C20 compiler full tuple");
  ok(eq(r.linker_before,{...c.linker,nlink:1}),"actual linker full tuple");
  for(const[k,x]of Object.entries(c.java_tools))ok(subset(r.java_tools_before[k],x),"Java tool "+k);
  ok(Object.keys(r.java_tools_before).length===7,"seven exact Java tools");
  ok(subset(r.candidate07_manifest,c.candidate_manifest),"949 source manifest pin");
  ok(Object.keys(r.source_before).length===16&&Object.keys(c.sources).length===16,"16 inline sources");
  for(const[k,x]of Object.entries(c.sources)){
    const b=B.dec(x.base64),p=r.source_before[k];
    ok(b.length===x.bytes&&U.sha256(b)===x.sha256,"inline body "+k);
    ok(p.bytes===x.bytes&&p.sha256===x.sha256&&p.path===c.root+"/source/"+k&&p.resolved_path===p.path,"inline actual "+k);
  }
  let dependencyRows=0;
  ok(Object.keys(r.dependency_before).length===16&&eq(r.dependency_before,r.dependency_after),"all 16 dependencies before/after exact");
  for(const o of r.objects){
    const rows=r.dependency_before[o.name];
    ok(o.machine===183&&o.type==="REL"&&o.executed===false,"object "+o.name+" ARM64 REL unexecuted");
    ok(rows&&Object.keys(rows).length===o.dependency_count,"object "+o.name+" dependency count");
    dependencyRows+=Object.keys(rows||{}).length;
    const conf=Object.values(rows||{}).filter(x=>x.path.endsWith("/__config_site"));
    const expect=["gtest-all","proc-self-maps-test","shared-library-test","user-apk-test","jni-test","jni-test-main"].includes(o.name);
    ok(expect?conf.length===1&&eq(conf[0],c.android_cxx_configuration.arm64_ndk_config.actual_tuple):conf.length===0,"object "+o.name+" exact ARM64 __config_site");
    if(expect)ok(Object.keys(rows).some(p=>p.endsWith("/gtest/gtest.h")),"object "+o.name+" actual GTest header");
  }
  ok(dependencyRows===4880,"4880 full named dependencies");
  const watch=new Map();let duplicateRows=0;
  function collect(v,path){
    if(!v||typeof v!=="object")return;
    if(!Array.isArray(v)&&fields.every(k=>k in v)){
      const p=tuple(v);
      ok(typeof p.path==="string"&&/^[0-9a-f]{64}$/.test(p.sha256)&&p.bytes>=0&&p.nlink===1,"metadata shape "+path);
      if(watch.has(p.path)){duplicateRows++;ok(eq(watch.get(p.path),p),"same path full tuple "+p.path);}
      else watch.set(p.path,p);
    }
    if(Array.isArray(v))v.forEach((x,i)=>collect(x,path+"["+i+"]"));
    else for(const[k,x]of Object.entries(v))collect(x,path+"."+k);
  }
  for(const[k,x]of Object.entries(r))if(k!=="source_after")collect(x,k);
  for(const[path,before]of watch){
    const after=r.source_after[path];
    ok(after!==undefined&&eq(tuple(after),before),"final full tuple "+path);
  }
  const extra=Object.keys(r.source_after).filter(p=>!watch.has(p)).sort();
  ok(eq(extra,[c.root+"/classes/com/example/ndk_tests/NdkTests.class",c.root+"/classes/com/example/ndk_tests/NdkTestsActivity.class",c.root+"/dex/classes.dex"].sort()),"only three additional known Java/Dex outputs");
  ok(Object.keys(r.source_after).length===976&&watch.size===973,"973 prior watched rows/976 final rows");
  for(const[name,x]of Object.entries(c.gtest_sources)){
    const path=c.aosp+"/external/googletest/googletest/"+name;
    ok(subset(r.source_after[path]||{},x),"full real GTest source "+name);
  }
  for(const x of Object.values(c.android_cxx_configuration))ok(eq(r.source_after[x.actual_tuple.path],x.actual_tuple),"Soong exact target configuration source");
  const child=r.child_tree_guard;
  ok(child.begin_passed===true&&child.final_children_empty===true&&child.restored===true&&child.original_subreaper_flag===0&&child.cleanup_seconds_per_command===5&&child.max_adopted===128,"subreaper final closure");
  const h=r.resource_health;
  ok(h.held_own_cgroup_gate_passed===true&&h.cgroup_files_written===false&&h.expected_memory_max===1073741824&&h.expected_cpu_count===1,"resource own gate");
  ok(h.whole_invocation_resource_qualified===false&&h.swap_zero_claimed===false,"original partial resource claims preserved");
  const limits={"cpu.max":[100000,100000],"memory.high":"max","memory.max":1073741824,"memory.swap.max":"max","pids.max":30053};
  ok(eq(h.before.limits,limits)&&eq(h.after.limits,limits),"actual exact limits, no invented caps");
  for(const k of ["cgroup_identity","mount_identity","membership","namespaces","pid"])ok(eq(h.before[k],h.after[k]),"same own cgroup "+k);
  ok(h.before.membership.includes("1a1b299fafc-fc05-7edb"),"own exact job cgroup");
  ok(Object.values(h.memory_event_delta).every(x=>x===0)&&h.after.memory_peak===504676352&&h.after.memory_swap_current===0&&h.after.memory_swap_peak===0,"observed peak/events/swap");
  return {checks,failures,dependency_rows:dependencyRows,unique_watch_before:watch.size,final_rows:Object.keys(r.source_after).length,duplicate_rows_checked:duplicateRows,command_stderr_nonempty:stderrCommands,extra_known_java_dex_outputs:extra,group_signal_attempted:50,memory_peak:h.after.memory_peak};
}