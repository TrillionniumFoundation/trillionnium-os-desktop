return function makeReader(app, rows) {
 const src=load("app_"+app+"_install02_packet"), inputs=JSON.parse(src.files["INPUTS.json"]),rev=app==="ihg"?2:3;
 const root="/home/alex/work/pocket4-owned-"+app+"-qa-r"+rev+"-install-state-02";
 let s=load("app_bili_install_three_read02_source_text"); const changes=[];
 function edit(old,next,count=1){const hits=s.split(old).length-1;if(hits!==count)throw Error("reader anchor "+old.slice(0,100)+" "+hits);s=s.split(old).join(next);changes.push({old,next,count});}
 function constant(name,next){const m=s.match(new RegExp("^"+name+" = .*$","m"));if(!m)throw Error(name);edit(m[0],name+" = "+next);}
 if(rows.length!==2||!rows.every(r=>r.ok===true&&r.error===null&&r.secondary_errors.length===0))throw Error("actual success parent");
 const cp=rows[0].result,sp=rows[1].stage_result;if(cp.path!==root+"/result.json"||sp.path!==root+"/stage-result.json")throw Error("parent root");
 constant("ROOT","Path("+JSON.stringify(root)+")");constant("STEP","ROOT/'worker'");constant("NONCE",JSON.stringify(inputs.nonces.state));constant("PACKAGE",JSON.stringify(inputs.helper_package));constant("PROTOCOL",JSON.stringify("pocket4-owned-"+app+"-qa-v"+rev));constant("INSTALL_NONCE",JSON.stringify(inputs.nonces.flow));constant("SOURCE_SHA",JSON.stringify(src.source_manifest_sha256));
 constant("PINS","{'coordinator.json': ("+cp.bytes+", '"+cp.sha256+"'), 'stage.json': ("+sp.bytes+", '"+sp.sha256+"')}");
 edit("'worker.json':STEP/'result.json',","'worker.json':STEP/'result.json',\n    'worker-command.json':ROOT/'evidence/01-install-state.result.json',\n    'state-command.json':STEP/'steps/install-state-01/command-008.result.json',");
 edit("EXACT_THREE_FILE_ALLOWLIST_REQUIRED","EXACT_FIVE_FILE_ALLOWLIST_REQUIRED");
 edit("runtime_recorder_manifest_sha256","runtime_shared_recorder_manifest_sha256");
 edit("worker.get('runtime_session_binding_sha256')=='aa6f468fa8e058882e681362aeb7fb4ba5b726d3d34c8dcfdc2b947aa6fb8b7e'",
      "worker.get('runtime_ticket_context_sha256')=="+JSON.stringify(v.sha256(v.utf8(src.files[app+"_context.py"])))+" and\n            worker.get('runtime_ticket_transport_sha256')=="+JSON.stringify(v.sha256(v.utf8(src.files[app+"_transport.py"])))+" and\n            worker.get('source_manifest_sha256')==SOURCE_SHA and worker.get('exact_command_count')==13 and worker.get('App_launches')==0");
 edit("4eb11cf497615272c1bef280bbd849de4f983ba4147ea9356356dff076ce9c56",inputs.qa_source_manifest_sha256);
 edit("e1cad62bba0266e646e7be4ce5250917fbf5df910ac604dddfe0a8aa25ac320b",inputs.APK.sha256);
 edit("10198,10203,10204)","10198,10203,10204,10152)");
 edit("    r.add('worker.json',BASE['worker.json'],raw)","    r.add('worker.json',BASE['worker.json'],raw)\n"+
 "    command=json.loads(r.add('worker-command.json',BASE['worker-command.json']));no_raw_ui(command)\n"+
 "    expected_argv=['/usr/bin/python3','-I',str(ROOT/'source/install_state.py'),'--worker-once','--source-manifest-sha256',SOURCE_SHA]\n"+
 "    printed=(json.dumps(worker,ensure_ascii=False)+'\\n').encode('utf-8')\n"+
 "    require(command.get('name')=='01-install-state' and command.get('argv')==expected_argv and\n"+
 "            command.get('spawned') is True and command.get('joined') is True and command.get('returncode')==0 and\n"+
 "            command.get('timed_out') is False and command.get('secondary_errors')==[] and\n"+
 "            command.get('Main_before') is True and command.get('Main_after')==coordinator.get('Main_after') and\n"+
 "            command.get('stdout')=={'bytes':len(printed),'sha256':sha(printed)} and\n"+
 "            command.get('stderr')=={'bytes':0,'sha256':sha(b'')},'EXACT_JOINED_WORKER_COMMAND_CHAIN')\n"+
 "    state_raw=r.add('state-command.json',BASE['state-command.json']);state_command=json.loads(state_raw);no_raw_ui(state_command)\n"+
 "    state=worker['state']\n"+
 "    require(sha(state_raw)==state['recorder_command_result_sha256'] and\n"+
 "            state_command.get('owned_command_joined') is True and state_command.get('spawned') is True and\n"+
 "            state_command.get('timed_out') is False and state_command.get('returncode')==0 and state_command.get('errors')==[] and\n"+
 "            state_command.get('stdout_sha256')==state['stdout_sha256'] and\n"+
 "            state_command.get('stderr_sha256')==state['stderr_sha256'],'EXACT_NO_UI_STATE_COMMAND_CHAIN')");
 edit("'parent_bound_worker_original_exported':True","'parent_bound_worker_original_exported':True,'state_command_index':8,'worker_and_state_command_metadata_exported':True");
 s=s.replaceAll("BILI R9",app.toUpperCase()+" R"+rev).replaceAll("BILI_R9",app.toUpperCase()+"_R"+rev).replaceAll("bili-r9-install-parent-bound-worker-and-no-automation-state",app+"-r"+rev+"-install02-parent-bound-worker-and-no-automation-state");
 const q={host:"pocket4",executable:"/usr/bin/sudo",args:["-n","/usr/bin/python3","-I","-c",s,"--collect-once"],cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:"",idempotency_key:"pocket4-"+app+"-r"+rev+"-current-install02-five-read01-20261106",timeout_seconds:30,cpu_quota_percent:50,memory_max_bytes:134217728,nice:10};
 return {source:s,request:q,edits:changes,source_manifest_sha256:src.source_manifest_sha256};
};