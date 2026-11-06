function buildBiliIndependentRetirement(material,h){
 const {actual,nativeRef,currentRef,parser,template,hostManifest}=material;
 const a=JSON.parse(actual.raw),native=JSON.parse(nativeRef.raw),current=JSON.parse(currentRef.raw);
 function need(v,c){if(!v)throw Error(c);}
 function verify(x){need(h.utf8(x.raw).length===x.pin.bytes&&h.sha(x.raw)===x.pin.sha256&&h.git(x.raw)===x.blob,"ACTUAL_ORIGINAL_PIN");}
 for(const x of [actual,nativeRef,currentRef])verify(x);
 need(a.ok===true&&a.errors.length===0&&a.control_count===27&&a.controls.every(x=>x.passed===true)&&a.reader_opened_fds===40&&a.reader_closed_fds===40&&a.source_sha256===h.sha(parser)&&Object.values(a.bindings).every(x=>x===true),"ACTUAL_PARSER_QUALIFICATION");
 for(const k of ["complete_wrapper_match","complete_closed_error_shape"])need(a.projection[k]===true,k);
 for(const k of ["reference_source_format_match","opaque_prefix_semantics_known","installed_source_version_verified","task_cleanup_authority_created"])need(a.projection[k]===false,k);
 need(current.ok===true&&current.errors.length===0&&current.two_current_samples_equal===true&&JSON.stringify(current.current_observations[0].tasks)===JSON.stringify(current.current_observations[1].tasks),"CURRENT_ACTUAL");
 need(native.collection_complete===true&&native.errors.length===0&&Object.values(native.bindings).every(x=>x===true),"NATIVE_ACTUAL");
 const pin=x=>({bytes:x.bytes,sha256:x.sha256});
 const inputs={
  schema:"pocket4-independent-native-launch-retirement-input-v1",task:873,historical_launch_outcome:"unknown_retained",existing_launch_scope_must_remain_absent:true,
  actual_error_reader:{job_id:actual.job_id,git_tree:actual.tree,git_blob:actual.blob,...actual.pin,source_sha256:h.sha(parser)},
  actual_error_projection:a.projection,
  actual_native_chain:{job_id:nativeRef.job_id,git_tree:nativeRef.tree,git_blob:nativeRef.blob,...nativeRef.pin},
  actual_previous_current_read:{job_id:currentRef.job_id,git_blob:currentRef.blob,...currentRef.pin},
  worker_pin:pin(native.observations.worker),scope_pin:pin(native.observations.scope),attempted_pin:pin(native.observations.attempted),
  prelaunch_stacks_pin:pin(native.observations.prelaunch_stacks),
  previous_current_stack_pin:{bytes:current.current_observations[1].raw_stack_bytes,sha256:current.current_observations[1].raw_stack_sha256},
  previous_current_command_pin:pin(current.command_records[1]),
  historical_scope:native.diagnostic.launch_attempt_metadata.scope,historical_attempted:native.diagnostic.launch_attempt_metadata.attempted,
  prelaunch_task_baseline:{task_ids:native.diagnostic.prelaunch_task_baseline.task_ids,roots:native.diagnostic.prelaunch_task_baseline.roots},
  previous_current_task_summary:current.current_observations[1].tasks,
  guard_source_root:"/home/alex/work/pocket4-current-host-r5-source-01",guard_manifest_sha256:hostManifest,
  original_unknown_reclassified:false,installed_native_source_match_verified:false,
  cleanup_authority:"explicit_new_independent_retirement_only_after_complete_chain_and_fresh_same_leaf",
  maximum_remove_commands:1,original_native_registration_replayed:false
 };
 let s=template;const edits=[];
 function rep(before,after,label){need(s.split(before).length===2,"REPLACEMENT_"+label);s=s.replace(before,after);edits.push({label,before,after});}
 const oldParser="1be3e65b359788a11b0f875ad8e6a4cce17b04f5b0ef4ffbc2ec4820d4f9a21f";
 need(s.split(oldParser).length===3,"OLD_PARSER_PINS");
 s=s.split(oldParser).join(h.sha(parser));edits.push({label:"actual_executed_parser04",before:oldParser,after:h.sha(parser),count:2});
 rep("  library.qualify_native(library.strict_json(raw['native_intent']),library.strict_json(raw['native_result']),original)",
 "  native_intent=library.strict_json(raw['native_intent']);native_result=library.strict_json(raw['native_result'])\n  library.qualify_native(native_intent,native_result,original)","retain_actual_native_order_fields");
 rep("       parsed['task_cleanup_authority_created'] is False,'EXACT_NATIVE_REPORTED_TASK_BINDING_REQUIRED')",
 "       parsed['task_cleanup_authority_created'] is False and\n       parsed['reference_source_format_match'] is False and parsed['opaque_prefix_semantics_known'] is False and\n       parsed['installed_source_version_verified'] is False,'EXACT_NATIVE_REPORTED_TASK_BINDING_REQUIRED')","retain_explicit_source_semantics_limits");
 rep("          'historical_reader_FDs_opened':reader.opened,'historical_reader_FDs_closed':reader.closed}",
 "          'historical_reader_FDs_opened':reader.opened,'historical_reader_FDs_closed':reader.closed,\n          'native_started_utc':native_intent['started_utc'],'native_ended_utc':native_result['ended_utc']}","retain_timestamps");
 rep("  read_exact(FLOW/'launch-attempted.json',INPUTS['attempted_pin'])",
 "  attempted=json.loads(read_exact(FLOW/'launch-attempted.json',INPUTS['attempted_pin']))\n  need(saved_scope==INPUTS['historical_scope'] and attempted==INPUTS['historical_attempted'] and\n       attempted['scope']==saved_scope and attempted['step']=='launch-01' and\n       saved_scope['component']==COMPONENT and saved_scope['user']==0 and\n       saved_scope['automatic_retry'] is False,'EXACT_ORIGINAL_LAUNCH_SCOPE_AND_ATTEMPT')\n  need(datetime.datetime.fromisoformat(saved_scope['created_utc'])<=\n       datetime.datetime.fromisoformat(attempted['time_utc'])<=\n       datetime.datetime.fromisoformat(result['historical_attribution']['native_started_utc'])<=\n       datetime.datetime.fromisoformat(result['historical_attribution']['native_ended_utc']),\n       'ORIGINAL_SCOPE_ATTEMPT_NATIVE_TIME_ORDER')","explicit_actual_scope_attempt_order");
 rep("  read_exact(FLOW/'steps/native-reconciliation-stacks-read-01/command-002.result.json',\n      INPUTS['previous_current_command_pin'])",
 "  previous_command=json.loads(read_exact(FLOW/'steps/native-reconciliation-stacks-read-01/command-002.result.json',\n      INPUTS['previous_current_command_pin']))\n  qualify_joined_command(previous_command,current_raw,False)\n  need(datetime.datetime.fromisoformat(result['historical_attribution']['native_ended_utc'])<=\n       datetime.datetime.fromisoformat(previous_command['ended_utc']),'CURRENT_OBSERVATION_FOLLOWS_NATIVE')","qualify_prior_observation_command");
 rep("  flow=recorder.Flow(args)\n  need(flow.scope==saved_scope",
 "  flow=recorder.Flow(args)\n  need(not os.path.lexists(FLOW/'launch-scope.json') and not os.path.lexists(MARKER) and\n       not os.path.lexists(RECONCILIATION),'NO_SCOPE_OR_RETIREMENT_CREATED_BEFORE_FLOW_LOCK')\n  need(flow.scope==saved_scope","recheck_no_replay_under_original_flow_lock");
 const prefix="import json\nINPUTS=json.loads("+JSON.stringify(JSON.stringify(inputs))+")\nHISTORICAL_PARSER_SOURCE="+JSON.stringify(parser)+"\n";
 const source=prefix+s,sourcePin={bytes:h.utf8(source).length,sha256:h.sha(source)};
 need(sourcePin.bytes<=131072,"SOURCE_PACKET_CAP");
 const request={
  host:"pocket4",executable:"/usr/bin/sudo",
  args:["-n","/usr/bin/python3","-I","-c","import sys,hashlib;raw=sys.stdin.buffer.read(131073);assert 0<len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=="+JSON.stringify(sourcePin.sha256)+";scope={'__name__':'fixed_independent_bili_retirement','__file__':'<verified-independent-bili-retirement>'};exec(compile(raw,scope['__file__'],'exec'),scope);raise SystemExit(scope['run']("+JSON.stringify(sourcePin.sha256)+"))"],
  cwd:"/home/alex/work",env:{PYTHONDONTWRITEBYTECODE:"1"},stdin:source,timeout_seconds:180,memory_max_bytes:268435456,cpu_quota_percent:100,nice:10,
  idempotency_key:"pocket4-bili-r9-player02-independent-Android-leaf-retirement01-20261106"
 };
 return {inputs,parser,controller:s,source,source_pin:sourcePin,request,request_raw:JSON.stringify(request)+"\n",edits};
}
