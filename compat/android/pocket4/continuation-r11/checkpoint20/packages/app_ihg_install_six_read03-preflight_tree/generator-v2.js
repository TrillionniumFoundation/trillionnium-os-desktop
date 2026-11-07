return function makeReaderV2(app,rows){
 const d=Function("load","v",load("current_three_install_five_reader_generator_source"))(load,v)(app,rows);
 let s=d.source;const fixes=[];
 function edit(a,b,n=1){if(s.split(a).length-1!==n)throw Error("v2 anchor "+a.slice(0,80));s=s.split(a).join(b);fixes.push({old:a,next:b,count:n});}
 edit("'worker-command.json':ROOT/'evidence/01-install-state.result.json',","'worker-command.json':ROOT/'evidence/01-install-state.result.json',\n    'worker-stdout.json':ROOT/'evidence/01-install-state.stdout',");
 edit("EXACT_FIVE_FILE_ALLOWLIST_REQUIRED","EXACT_SIX_FILE_ALLOWLIST_REQUIRED");
 edit("    printed=(json.dumps(worker,ensure_ascii=False)+'\\n').encode('utf-8')",
 "    printed=r.read(BASE['worker-stdout.json'])\n"+
 "    require(command.get('stdout')=={'bytes':len(printed),'sha256':sha(printed)},'ACTUAL_WORKER_STDOUT_PARENT_PIN')\n"+
 "    printed_value=json.loads(printed);no_raw_ui(printed_value)\n"+
 "    require(printed_value==worker,'ACTUAL_WORKER_STDOUT_AND_DURABLE_JSON_SEMANTICS')\n"+
 "    r.add('worker-stdout.json',BASE['worker-stdout.json'],printed)");
 edit("'worker_and_state_command_metadata_exported':True","'worker_and_state_command_metadata_exported':True,'owned_worker_json_stdout_exported':True");
 d.source=s;d.fixes=fixes;d.request={...d.request,args:["-n","/usr/bin/python3","-I","-c",s,"--collect-once"],idempotency_key:d.request.idempotency_key.replace("five-read01","six-read02")};return d;
};