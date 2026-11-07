"""Private historical chain qualification for a new current IHG877 retirement scope."""
def verify_historical(hist,inputs,read_exact,qualify_joined_command):
 need(inputs['schema']=='pocket4-independent-current-IHG877-retirement-input-v1' and inputs['task']==TASK and
  inputs['package']==PACKAGE and inputs['component']==COMPONENT and
  inputs['original_launch_outcome']=='unknown_retained' and inputs['native_reported_task_id'] is None and
  inputs['old_task876_disappearance_attributed'] is False,'EXACT_CURRENT_RETIREMENT_INPUTS')
 r=hist.Reader();observed={};primary=None
 def get(name):
  expected=inputs['fixed_historical_files'][name]
  need(expected['path']==str(hist.FILES[name]),'EXACT_HISTORICAL_ALLOWLIST_PATH')
  raw=r.access(name,True);p={'bytes':expected['bytes'],'sha256':expected['sha256']}
  need(pin(raw)==p,'FIXED_HISTORICAL_ORIGINAL_CHANGED')
  observed[name]={'path':expected['path'],**p};return raw
 try:
  fixed={name:get(name) for name in hist.PINS}
  c,s,w=(hist.strict_json(fixed[k]) for k in ('coordinator','stage','worker'))
  original=hist.qualify_worker(c,s,w)
  parse,exact_leaf=hist.task_parser(fixed['task_parser'])
  intent=hist.strict_json(get('native_intent'));native_result=hist.strict_json(get('native_result'))
  hist.qualify_intent(intent,native_result,original)
  streams={name:get('native_'+name) for name in ('stdout','stderr')}
  for name,raw in streams.items():need(sha(raw)==hist.NATIVE_STREAMS[name],'ORIGINAL_NATIVE_STREAM_SHA')
  projection=hist.classify_native(streams['stdout'],streams['stderr'])
  need(projection==inputs['native_projection'] and projection['closed_child_matches']==[] and
   projection['whole_error_attribution_qualified'] is False and
   projection['task_cleanup_authority_created'] is False and projection['ok'] is False and
   projection['host_pid']==3268774 and projection['stderr_exactly_repeats_complete_message'] is True,
   'HISTORICAL_TIMEOUT_OBSERVATION_NOT_NATIVE_TASK_ATTRIBUTION')
  scope=hist.strict_json(get('scope'));attempt=hist.strict_json(get('attempted'))
  hist.qualify_scope(scope,attempt)
  raw=get('prelaunch_stacks');recorded=get('prelaunch_stdout')
  pr=hist.strict_json(get('prelaunch_result'));transport=hist.strict_json(get('prelaunch_transport'))
  need(raw==recorded,'COMPLETE_PRELAUNCH_STDOUT_BYTES')
  qualify_joined_command(pr,raw,False)
  command_sha=sha(json.dumps(hist.STACKS,separators=(',',':')).encode())
  need(transport.get('sequence')==6 and transport.get('epoch_sha256')==scope['epoch_sha256'] and
   transport.get('package')==PACKAGE and transport.get('uid')==10137 and transport.get('command_sha256')==command_sha and
   transport.get('returncode')==0 and transport.get('stdout_sha256')==sha(raw) and
   transport.get('stdout_bytes')==len(raw) and transport.get('stderr_bytes')==0 and
   transport.get('stderr_sha256')==sha(b'') and transport.get('outcome_unknown') is False and
   transport.get('automatic_retry') is False and transport.get('numeric_pid_target_used') is False,
   'EXACT_PRELAUNCH_HELD_TRANSPORT')
  need(hist.utc(pr['ended_utc'])<=hist.utc(attempt['time_utc'])<=hist.utc(intent['started_utc'])<=hist.utc(native_result['ended_utc']),
   'ORIGINAL_LAUNCH_TIME_ORDER')
  old_roots,old_tasks=parse(raw.decode('utf-8','strict'))
  need(hist.task_projection(raw,old_roots,old_tasks)==inputs['prelaunch'] and
   old_tasks=={875,876} and TASK not in old_tasks and TASK not in old_roots and
   not any(child['component'].split('/')[0]==PACKAGE for root in old_roots.values() for child in root['children']),
   'NO_IHG_PACKAGE_OR_TASK877_IN_COMPLETE_ORIGINAL_PRELAUNCH')
  need(r.access('launch_scope',False,optional=True) is None,'ORIGINAL_LAUNCH_SCOPE_MUST_REMAIN_ABSENT')
  samples=[]
  for number,row in enumerate(inputs['current_saved'],1):
   expected_path=FLOW/'steps/native-launch-state-read-02'/('current-stacks-%02d.txt'%number)
   command_path=FLOW/'steps/native-launch-state-read-02'/('command-%03d.result.json'%(number+4))
   need(row['sample']==number and row['path']==str(expected_path) and row['command']['path']==str(command_path),
    'EXACT_TWO_FIXED_SAVED_OBSERVATIONS')
   raw=read_exact(expected_path,{k:row[k] for k in ('bytes','sha256')},131072)
   cr=hist.strict_json(read_exact(command_path,{k:row['command'][k] for k in ('bytes','sha256')}))
   qualify_joined_command(cr,raw,False)
   need(hist.utc(native_result['ended_utc'])<=hist.utc(cr['ended_utc']),'SAVED_OBSERVATION_FOLLOWS_ORIGINAL_LAUNCH')
   roots,tasks=parse(raw.decode('utf-8','strict'))
   need(sha(canon(roots))==row['parsed_roots_sha256'] and tasks=={875,TASK} and set(roots)=={1,TASK} and
    exact_leaf(roots,TASK,PACKAGE) and roots[TASK]['children']==[{'id':TASK,'component':COMPONENT,'user':0}] and
    sha(canon(roots[1]))==inputs['preserved_root1_sha256'] and
    sha(canon(roots[TASK]))==inputs['current_root877_sha256'] and roots[1]==old_roots[1],
    'COMPLETE_SAVED_CURRENT_IHG877_AND_PRESERVED875')
   samples.append((roots,tasks))
  need(len(samples)==2 and samples[0]==samples[1],'EXACT_TWO_SAVED_TABLES_EQUAL')
  preserved_roots={k:v for k,v in samples[0][0].items() if k!=TASK}
  preserved_tasks=set(samples[0][1])-{TASK}
  need(preserved_tasks==set(inputs['preserved_current_tasks'])=={875} and
   set(preserved_roots)==set(inputs['preserved_current_root_ids'])=={1},'EXACT_CURRENT_PRESERVATION_BASELINE')
  need(r.opened==r.closed,'HISTORICAL_READER_FD_CLOSURE')
  safe={'fixed_historical_pins':observed,'actual_readers':inputs['evidence'],
   'native_intent_component':hist.COMPONENT,'canonical_public_component':COMPONENT,
   'component_not_present_in_original_prelaunch':True,'native_reported_task_id':None,
   'historical_launch_outcome':'unknown_retained','original_missing_Main_after_retained':True,
   'original_launch_scope_created':False,'original_task876_disappearance_attributed':False,
   'original_prelaunch_tasks':[875,876],'historical_current_tasks':[875,TASK],
   'preserved_current_tasks':[875],'entire_original_prelaunch_baseline_restored':False,
   'current_installed_native_source_version_verified':False,'whole_error_attribution_qualified':False,
   'reader_FDs_opened':r.opened,'reader_FDs_closed':r.closed,
   'current_saved_file_pins':inputs['current_saved']}
  return scope,preserved_roots,preserved_tasks,parse,exact_leaf,safe
 except BaseException as error:
  primary=error;raise
 finally:
  if r.opened!=r.closed:
   if primary is None:raise RuntimeError('HISTORICAL_READER_FD_CLOSURE')
   primary.add_note('HISTORICAL_READER_FD_CLOSURE')
