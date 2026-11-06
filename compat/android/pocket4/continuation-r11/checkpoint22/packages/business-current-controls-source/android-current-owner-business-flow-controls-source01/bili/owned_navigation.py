"""One owned Bili navigation, R10 fixed player inputs, and exact task retirement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types
import time
HERE=Path(__file__).resolve().parent
ROOT=Path('/home/alex/work/pocket4-bilibili-r10-pause-resume-01')
SOURCE=ROOT/'source'
NONCE='__FRESH_NONCE_000__'
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r10-flow-'+NONCE)
PLAN={'schema':1,'operation':'click','selector':{'resource_id':'tv.danmaku.bili:id/expand_search','class':'android.widget.LinearLayout','content_desc':'Search bar, button'},'nonces':{'before':'__FRESH_NONCE_001__','inspect':'__FRESH_NONCE_002__','action':'__FRESH_NONCE_003__','after':'__FRESH_NONCE_004__'}}
POST_PLAN={'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_005__','inspect':'__FRESH_NONCE_006__','after':'__FRESH_NONCE_007__'}}
STABILITY_PLANS=[{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_008__','inspect':'__FRESH_NONCE_009__','after':'__FRESH_NONCE_010__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_011__','inspect':'__FRESH_NONCE_012__','after':'__FRESH_NONCE_013__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_014__','inspect':'__FRESH_NONCE_015__','after':'__FRESH_NONCE_016__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_017__','inspect':'__FRESH_NONCE_018__','after':'__FRESH_NONCE_019__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_020__','inspect':'__FRESH_NONCE_021__','after':'__FRESH_NONCE_022__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_023__','inspect':'__FRESH_NONCE_024__','after':'__FRESH_NONCE_025__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_026__','inspect':'__FRESH_NONCE_027__','after':'__FRESH_NONCE_028__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_029__','inspect':'__FRESH_NONCE_030__','after':'__FRESH_NONCE_031__'}}]
STABILITY_SECONDS=12
FIRST_STABILITY_SECONDS=20
FIRST_STABILITY_MATCHES=3
FIRST_STABILITY_SPAN_MS=4000
RESULT_OBSERVATION_SECONDS=20
RESULT_OBSERVATION_PLANS=[{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_032__','inspect':'__FRESH_NONCE_033__','after':'__FRESH_NONCE_034__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_035__','inspect':'__FRESH_NONCE_036__','after':'__FRESH_NONCE_037__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_038__','inspect':'__FRESH_NONCE_039__','after':'__FRESH_NONCE_040__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_041__','inspect':'__FRESH_NONCE_042__','after':'__FRESH_NONCE_043__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_044__','inspect':'__FRESH_NONCE_045__','after':'__FRESH_NONCE_046__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_047__','inspect':'__FRESH_NONCE_048__','after':'__FRESH_NONCE_049__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_050__','inspect':'__FRESH_NONCE_051__','after':'__FRESH_NONCE_052__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_053__','inspect':'__FRESH_NONCE_054__','after':'__FRESH_NONCE_055__'}}]
SEARCH_ACTIVITY='tv.danmaku.bili/com.bilibili.search2.main.BiliMainSearchActivity'
EDIT_SELECTOR={'resource_id':'tv.danmaku.bili:id/search_src_text','class':'android.widget.EditText'}
SUBMIT_SELECTOR={'resource_id':'tv.danmaku.bili:id/action_search','class':'android.widget.TextView'}
PUBLIC_QUERY='微积分'
SET_TEXT_PLAN={'schema':1,'operation':'set_text','selector':{'resource_id':'tv.danmaku.bili:id/search_src_text','class':'android.widget.EditText'},'value':'微积分','nonces':{'before':'__FRESH_NONCE_056__','inspect':'__FRESH_NONCE_057__','action':'__FRESH_NONCE_058__','after':'__FRESH_NONCE_059__'}}
SUBMIT_PLAN={'schema':1,'operation':'click','selector':{'resource_id':'tv.danmaku.bili:id/action_search','class':'android.widget.TextView'},'nonces':{'before':'__FRESH_NONCE_060__','inspect':'__FRESH_NONCE_061__','action':'__FRESH_NONCE_062__','after':'__FRESH_NONCE_063__'}}
RESULTS_PLAN={'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_064__','inspect':'__FRESH_NONCE_065__','after':'__FRESH_NONCE_066__'}}
QUERY_STABILITY_PLANS=[{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_067__','inspect':'__FRESH_NONCE_068__','after':'__FRESH_NONCE_069__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_070__','inspect':'__FRESH_NONCE_071__','after':'__FRESH_NONCE_072__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_073__','inspect':'__FRESH_NONCE_074__','after':'__FRESH_NONCE_075__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_076__','inspect':'__FRESH_NONCE_077__','after':'__FRESH_NONCE_078__'}}]
SUBMIT_STABILITY_PLANS=[{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_079__','inspect':'__FRESH_NONCE_080__','after':'__FRESH_NONCE_081__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_082__','inspect':'__FRESH_NONCE_083__','after':'__FRESH_NONCE_084__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_085__','inspect':'__FRESH_NONCE_086__','after':'__FRESH_NONCE_087__'}},{'schema':1,'operation':'inspect','nonces':{'before':'__FRESH_NONCE_088__','inspect':'__FRESH_NONCE_089__','after':'__FRESH_NONCE_090__'}}]
SELF,UID=("org.droidloom.qa.bili.r10",None)  # Actual R10 installation required.
BILI,BILI_UID=('tv.danmaku.bili',10117)
INSTALL_ROOT=Path("/home/alex/work/pocket4-owned-bili-qa-r10-install-state-02")
INSTALL_SOURCE=INSTALL_ROOT/'source'
INSTALL_ENTRY_SHA="55458ecb899956dd3475c454a4f8993df036a2439992c32527a66cc852cb71c3"
INSTALL_ENTRY_BYTES=39575
INSTALL_MANIFEST_SHA="e3cb2adbcfe46a47ca81ec3b5883f1e1a0cd806b21e964d75944e8fe5cd49387"
R6_MANIFEST="002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff"
SESSION_SHA="d896b750b6e35fc859c773a5f9797c22c33631a9bfc4c3c4d327706438cf0013"
OLD_FLOW=Path("/home/alex/work/pocket4-bilibili-owned-qa-r10-flow-d5a77071f725e6bfb854effcd467cc99")
OLD_STEP=OLD_FLOW/'steps/install-state-r10-01'
OLD_STATE_NONCE="d6a0aab3fd95f4e006a35683d0bd2c7b"
OLD_STATE_WIRE=None  # Actual R10 original receipt required.
OLD_PACKET="ae2e7ccb5cb6eb7a06b69b3e123d7830b01172b885557bb2eec3ba401426f078"
MAIN_EPOCH="7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c"
FILES={'owned_navigation.py','stage_execute.py','video_navigation.py','controls_reveal.py','playback_controls.py','post_foreground.py'}
INSTALL_JOB_ID=None  # Actual R10 original receipt required.
STATE_COMMAND_INDEX=None  # Actual R10 original receipt required.
STATE_COMMAND_SHA=None  # Actual R10 original receipt required.
EXPECTED_INSTALLED_IDENTITY=None  # Actual R10 original receipt required.
INSTALL_RECORDS=None  # Actual R10 original receipt required.
def require(value,reason):
 if not value:
  raise RuntimeError(reason)
def sha(raw):
 return hashlib.sha256(raw).hexdigest()
def read(path,maximum=1048576,expected=None,size=None):
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:
  first=os.fstat(fd)
  require(stat.S_ISREG(first.st_mode)and first.st_nlink==1 and(0<=first.st_size<=maximum),'BOUNDED_SINGLE_REGULAR_FILE_REQUIRED: '+str(path))
  chunks=[]
  count=0
  while True:
   part=os.read(fd,min(65536,maximum+1-count))
   if not part:
    break
   chunks.append(part)
   count+=len(part)
   require(count<=maximum,'INPUT_GREW: '+str(path))
  last=os.fstat(fd)
  fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
  require(count==first.st_size and all((getattr(first,k)==getattr(last,k)for k in fields)),'INPUT_CHANGED: '+str(path))
  raw=b''.join(chunks)
  require(expected is None or sha(raw)==expected,'INPUT_SHA_CHANGED: '+str(path))
  require(size is None or len(raw)==size,'INPUT_SIZE_CHANGED: '+str(path))
  return raw
 finally:
  os.close(fd)
def require_actual_install_binding():
 require(type(UID)is int and 10000<=UID<100000 and(UID not in(10117,10125,10164,10165,10166,10169,10170,10175,10184,10202,10204,10152)),'ACTUAL_R10_INSTALL_UID_PENDING')
 require(type(STATE_COMMAND_INDEX)is int and 1<=STATE_COMMAND_INDEX<=16 and isinstance(STATE_COMMAND_SHA,str)and re.fullmatch('[0-9a-f]{64}',STATE_COMMAND_SHA)and isinstance(OLD_STATE_WIRE,str)and re.fullmatch('[0-9a-f]{64}',OLD_STATE_WIRE),'ACTUAL_R10_STATE_COMMAND_BINDING_PENDING')
 require(isinstance(EXPECTED_INSTALLED_IDENTITY,dict)and EXPECTED_INSTALLED_IDENTITY.get('package')==SELF and(EXPECTED_INSTALLED_IDENTITY.get('uid')==UID),'ACTUAL_R10_INSTALLED_FILE_IDENTITY_PENDING')
 for name,(path,size,pin)in INSTALL_RECORDS.items():
  require(type(size)is int and 0<size<=65536 and isinstance(pin,str)and re.fullmatch('[0-9a-f]{64}',pin),'ACTUAL_R10_INSTALL_RECEIPT_PENDING:'+name)
def load_prior():
 require_actual_install_binding()
 path=INSTALL_SOURCE/'install_state.py'
 raw=read(path,65536,INSTALL_ENTRY_SHA,INSTALL_ENTRY_BYTES)
 prior=types.ModuleType('bili_actual_install02')
 prior.__file__=str(path)
 exec(compile(raw,str(path),'exec'),prior.__dict__)
 manifest=prior.verify_source(INSTALL_MANIFEST_SHA)
 require(prior.RECORDER_MANIFEST==R6_MANIFEST and manifest['files']['session_binding.py']['sha256']==SESSION_SHA,'ACTUAL_INSTALL02_R6_SOURCE_BINDING_CHANGED')
 return prior
def verify_source(expected):
 require(isinstance(expected,str)and re.fullmatch('[0-9a-f]{64}',expected),'EXTERNAL_SOURCE_PIN_REQUIRED')
 manifest=json.loads(read(HERE/'SOURCE_PINS.json',65536,expected))
 require(set(manifest['files'])==FILES,'EXACT_SIX_RUNTIME_FILE_SOURCE_REQUIRED')
 for name,row in manifest['files'].items():
  read(HERE/name,65536,row['sha256'],row['bytes'])
 return manifest
def fixed_plan():
 groups=(STABILITY_PLANS,QUERY_STABILITY_PLANS,SUBMIT_STABILITY_PLANS)
 require(len(STABILITY_PLANS)==8 and all((len(group)==4 for group in groups[1:]))and all((p.get('operation')=='inspect' for group in groups for p in group)),'EXACT_READ_ONLY_STABILITY_PLANS_REQUIRED')
 require(len(RESULT_OBSERVATION_PLANS)==8 and all((p.get('operation')=='inspect' for p in RESULT_OBSERVATION_PLANS)),'ONLY_EIGHT_ADDITIONAL_READ_ONLY_RESULT_PLANS')
 require(SET_TEXT_PLAN['operation']=='set_text' and SET_TEXT_PLAN['value']==PUBLIC_QUERY=='微积分' and(SET_TEXT_PLAN['selector']==EDIT_SELECTOR)and(SUBMIT_PLAN['operation']=='click')and(SUBMIT_PLAN['selector']==SUBMIT_SELECTOR)and(RESULTS_PLAN['operation']=='inspect'),'ONLY_THE_FIXED_OBSERVED_PUBLIC_QUERY_PLAN')
 plans=[PLAN,POST_PLAN,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN,*STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS]
 values=[NONCE,*(nonce for plan in plans for nonce in plan['nonces'].values())]
 require(all((re.fullmatch('[0-9a-f]{32}',value)for value in values))and len(set(values))==91 and(OLD_STATE_NONCE not in values),'FRESH_DISTINCT_NONCES_REQUIRED')
 return json.loads(json.dumps(PLAN))
def actual_install(prior,qa,proof):
 """Consume original pinned success; never relabel install01 or infer UID."""
 rows={name:json.loads(read(path,65536,pin,size))for name,(path,size,pin)in INSTALL_RECORDS.items()}
 c,s,w,cmd=(rows[name]for name in('coordinator','stage','worker','worker_command'))
 for row in(c,s,w):
  require(row.get('ok')is True and row.get('error')is None and(row.get('secondary_errors')==[]),'ACTUAL_INSTALL02_COMPLETE_SUCCESS_REQUIRED')
 require(c.get('source_manifest_sha256')==s.get('source_manifest_sha256')==INSTALL_MANIFEST_SHA and s.get('packet_sha256')==OLD_PACKET and(s.get('coordinator_returncode')==0)and(s.get('source_unchanged')is True)and(c.get('source_and_artifact_unchanged')is True),'ACTUAL_INSTALL02_SOURCE_AND_TERMINAL_REQUIRED')
 require(s.get('coordinator_result')=={'path':str(INSTALL_RECORDS['coordinator'][0]),'bytes':INSTALL_RECORDS['coordinator'][1],'sha256':INSTALL_RECORDS['coordinator'][2]}and c.get('worker_result')=={'path':str(INSTALL_RECORDS['worker'][0]),'bytes':INSTALL_RECORDS['worker'][1],'sha256':INSTALL_RECORDS['worker'][2]},'ACTUAL_INSTALL02_RECEIPT_CHAIN_REQUIRED')
 require(cmd.get('spawned')is True and cmd.get('joined')is True and(cmd.get('returncode')==0)and(cmd.get('timed_out')is False)and(cmd.get('secondary_errors')==[]),'JOINED_INSTALL02_WORKER_REQUIRED')
 require(c.get('owned_package_uid')==w.get('owned_package_uid')==UID and c.get('owned_package_retained_for_separate_UI_admission')is True and(w.get('package')==SELF)and(w.get('package_retained')is True)and(w.get('install_attempted')is True)and(w.get('install_success_observed')is True)and(w.get('state_attempted')is True)and(w.get('outcome_unknown')is False)and(w.get('runtime_recorder_manifest_sha256')==R6_MANIFEST)and(w.get('runtime_session_binding_sha256')==SESSION_SHA)and(w.get('build')==proof),'EXACT_INSTALLED_HELPER_AND_BUILD_REQUIRED')
 require(w.get('final_Main_guard_passed')is True and w.get('held_binding_released')is True and(w.get('action_lock_released')is True)and(w.get('UI_actions')==w.get('audio_actions')==0)and(w.get('UiAutomation_connection_requested')is False)and(w.get('old_v2_helper_called')is False),'ACTUAL_INSTALL02_SCOPE_REQUIRED')
 for row in(c,s):
  require(row.get('Main_before')==row.get('Main_after')=={"Main_epoch_sha256":"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c","authenticated_owner_chain_matches":True,"config_sha256":"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc","current_baseline_qualification_sha256":"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e","current_baseline_sha256":"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364","current_executable_and_root_backing_match":True,"current_user_namespaces_match":True,"framework_exit_cause_resolved":False,"historical_activation_sha256":"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615","historical_verified_sha256":"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387","old_helpers_and_tasks_reauthorized":False,"previous_current_baseline_sha256":"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266","production_ready":False,"resource_limits_match":True,"schema":"pocket4-current-main-guard-v2","seven_processes_match":True,"three_host_processes_match":True},'ACTUAL_INSTALL02_MAIN_CHAIN_REQUIRED')
 installed=w['installed_before_state']
 require(installed==w.get('installed_after_state')and installed.get('package')==SELF and(installed.get('uid')==UID)and(installed.get('apk_sha256')==prior.APK_SHA)and(installed.get('bytes')==prior.APK_BYTES)and(installed.get('signer_bound_by_exact_signed_apk_bytes')==prior.SIGNER_SHA)and(installed==EXPECTED_INSTALLED_IDENTITY)and(installed['held_file']['nlink']==1),'ACTUAL_INSTALLED_APK_IDENTITY_REQUIRED')
 previous=w['state']
 stem=OLD_STEP/('command-%03d'%STATE_COMMAND_INDEX)
 command_raw=read(str(stem)+'.result.json',65536,STATE_COMMAND_SHA)
 command=json.loads(command_raw)
 out=read(str(stem)+'.stdout',1048576,previous['stdout_sha256'])
 err=read(str(stem)+'.stderr',1048576,previous['stderr_sha256'])
 require(command.get('owned_command_joined')is True and command.get('spawned')is True and(command.get('timed_out')is False)and(command.get('errors')==[])and(command.get('stdout_sha256')==sha(out))and(command.get('stderr_sha256')==sha(err)),'ACTUAL_INSTALL02_STATE_COMMAND_REQUIRED')
 assessed=qa.parse_completed(out,err,command['returncode'],{'protocol':qa.PROTOCOL,'nonce':OLD_STATE_NONCE,'op':'state'},UID)
 assessed['recorder_command_result_sha256']=sha(command_raw)
 assessed['held_transport_returned_after_post_guard']=True
 require(assessed==previous and previous['wire_sha256']==c['state_wire_sha256']==OLD_STATE_WIRE and(previous['helper']['ui_automation_connected']is False),'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')
 return(installed,{'install_job':INSTALL_JOB_ID,'receipts':{name:{'path':str(path),'bytes':size,'sha256':pin}for name,(path,size,pin)in INSTALL_RECORDS.items()},'state_wire_sha256':OLD_STATE_WIRE,'uid':UID,'APK_sha256':prior.APK_SHA,'signer_certificate_sha256':prior.SIGNER_SHA,'installed_identity':installed,'historical_state_reparsed':True,'historical_state_used_as_current_baseline':False})
def new_session(prior,adapter,flow,recorder,qa,proof):
 binding=prior.module(INSTALL_SOURCE/'session_binding.py',SESSION_SHA,'owned_bili_r5_session')
 return binding.new_session(adapter,flow,recorder,qa,proof,UID)
def assessment_summary(prior,qa,step,sequence,plan):
 """No node text, descriptions, screenshots or recommendations are returned."""
 values={}
 for phase,nonce in plan['nonces'].items():
  path=step/(nonce+'.assessment.json')
  raw=read(path)
  value=json.loads(raw)
  require(value['helper']['nonce']==nonce and value['helper']['self_uid']==UID and(value['held_transport_returned_after_post_guard']is True),'CURRENT_ASSESSMENT_BINDING_CHANGED')
  values[phase]={'nonce':nonce,'operation':value['helper']['op'],'assessment_sha256':sha(raw),'assessment_bytes':len(raw),'wire_sha256':value['wire_sha256'],'recorder_command_result_sha256':value['recorder_command_result_sha256'],'actual_command_returncode':value['actual_command_returncode'],'actual_instrumentation_finish_code':value['actual_instrumentation_finish_code']}
  if phase=='inspect':
   inspection=qa.inspect_record(value['helper']['inspection'])
   require(value['wire_sha256']==sequence['inspection_wire_sha256'],'CURRENT_INSPECTION_WIRE_CHANGED')
   window=inspection['window']
   values[phase]['inspection_idle_observation']=qa.inspection_idle_observation(value['helper']['inspection_idle_observation'],'inspect',value['helper']['started_elapsed_ms'],True)
   values[phase].update(tree_sha256=inspection['tree_sha256'],window_sha256=inspection['window_sha256'],node_count=len(inspection['nodes']),window={key:window[key]for key in('package','display','type','focused')},window_observation=qa.window_observation(value['helper']['window_observation']),connection_scoped_window_id=inspection['connection_scoped_window_id'],tree_observations=qa.tree_observations(value['helper']['tree_observations'],'inspect',True),complete=True,raw_tree_private_only=True)
  elif phase=='action':
   helper=value['helper']
   require(helper['node_action']==('ACTION_SET_TEXT' if plan['operation']=='set_text' else 'ACTION_CLICK')and helper['node_action_returned']is True and(helper['action_attempted']is True)and(helper['outcome_unknown']is True),'ACTUAL_SINGLE_CLICK_ACK_REQUIRED')
   values[phase].update(node_action=helper['node_action'],node_action_returned=True,action_attempted=True,outcome_unknown=True,target_node_path=helper['target_node_path'],target_node_sha256=helper['target_node_sha256'],inspection_nonce=helper['inspection_nonce'],inspection_sha256=helper['inspection_sha256'],action_window={key:helper['action_window'][key]for key in('package','display','type','focused')},tree_observations=qa.tree_observations(helper['tree_observations'],plan['operation'],True),window_observation=qa.window_observation(helper['window_observation']))
   if plan['operation']=='set_text':
    require(helper['target_resource_id']==EDIT_SELECTOR['resource_id']and helper['requested_value_sha256']==helper['observed_value_sha256']==sha(PUBLIC_QUERY.encode())and(helper['value_readback_verified']is True),'ACTUAL_PUBLIC_QUERY_EDIT_READBACK_REQUIRED')
    values[phase].update(target_resource_id=helper['target_resource_id'],requested_value_sha256=helper['requested_value_sha256'],observed_value_sha256=helper['observed_value_sha256'],value_readback_verified=True)
 names=('before','inspect','action','after')if plan['operation']in('click','set_text','player_button')else('before','inspect','after')
 expected=['state','inspect',plan['operation'],'state']if plan['operation']in('click','set_text','player_button')else['state','inspect','state']
 require([values[k]['operation']for k in names]==expected,'EXACT_NEW_HELPER_COMMAND_SEQUENCE_REQUIRED')
 return values
def stable_before_click(prior,qa,flow,session,installed,result):
 """Sample complete equal trees over a bounded span; never replay failed reads.

    The sampled span is not continuous stability or future action authority.
    The action retains its own fresh full-tree/window/target checks.
    """
 began=time.monotonic()
 previous=None
 previous_end=None
 first_end=None
 matching=[]
 result['pre_action_stability']={'maximum_sequences':8,'deadline_seconds':FIRST_STABILITY_SECONDS,'minimum_matching_sequences':FIRST_STABILITY_MATCHES,'minimum_capture_span_ms':FIRST_STABILITY_SPAN_MS,'observations':[],'qualified':False,'failed_reads_retried':False,'action_retried':False}
 state=result['pre_action_stability']
 for index,plan in enumerate(STABILITY_PLANS,1):
  require(time.monotonic()-began<=FIRST_STABILITY_SECONDS,'STABILITY_OBSERVATION_DEADLINE')
  sequence=session.sequence(json.loads(json.dumps(plan)))
  require(sequence['installed_before']==sequence['installed_after']==installed and sequence['restoration_qualified']is True and(sequence['after_state_completed']is True),'STABILITY_READ_INSTALL_AND_RESTORATION_REQUIRED')
  summaries=assessment_summary(prior,qa,flow.step,sequence,plan)
  observed=summaries['inspect']
  key={'tree_sha256':observed['tree_sha256'],'window_sha256':observed['window_sha256'],'node_count':observed['node_count'],'foreground':sequence['foreground_after'],'accessibility_state':sequence['accessibility_restoration']['state_after']}
  capture=observed['tree_observations'][0]
  start,end=capture['began_elapsed_ms'],capture['last_elapsed_ms']
  require(previous_end is None or start>=previous_end,'STABILITY_CAPTURE_ORDER_REQUIRED')
  if key!=previous:
   matching=[]
   first_end=end
  matching.append(index)
  previous,previous_end=key,end
  span=max(0,start-first_end)
  elapsed=int((time.monotonic()-began)*1000)
  state['observations'].append({'sequence':index,'elapsed_ms':elapsed,'complete_key':key,'assessments':summaries,'restoration_qualified':True,'matching_capture_span_ms':span})
  require(time.monotonic()-began<=FIRST_STABILITY_SECONDS,'STABILITY_OBSERVATION_DEADLINE')
  if len(matching)>=FIRST_STABILITY_MATCHES and span>=FIRST_STABILITY_SPAN_MS:
   state['qualified']=True
   state['matching_sequences']=list(matching)
   state['sampled_capture_span_ms']=span
   state['future_action_still_requires_original_strict_freshness']=True
   return
 raise RuntimeError('COMPLETE_TREE_NOT_STABLE_IN_BOUNDED_READS')
def navigation_sequences(prior,qa,flow,session,installed,result,first_click):
 """One action, then one independent read-only observation, including failures.

    An acknowledged click remains an unknown business outcome. No subsequent
    mutation can consume this step as a successful business postcondition.
    """
 result['click_sequence_started']=False
 try:
  stable_before_click(prior,qa,flow,session,installed,result)
  result['click_sequence_started']=True
  result['click_sequence']=first_click.run(session,fixed_plan())
  sequence=result['click_sequence']
  require(sequence['installed_before']==sequence['installed_after']==installed and sequence.get('click_acknowledged')is True and(sequence['restoration_qualified']is True)and(sequence['after_state_completed']is True),'CLICK_ACK_INSTALL_AND_INDEPENDENT_RESTORATION_REQUIRED')
  result['click_assessments']=assessment_summary(prior,qa,flow.step,sequence,PLAN)
  result['click_acknowledged']=True
 except BaseException as error:
  if hasattr(session,'sequence_observation'):
   result['failed_click_sequence' if result['click_sequence_started']else 'failed_stability_sequence']=session.sequence_observation
  prior.remember(result,'click_sequence' if result['click_sequence_started']else 'pre_action_stability',error)
 finally:
  result['post_inspection_attempted']=True
  try:
   result['post_inspection_sequence']=session.sequence(json.loads(json.dumps(POST_PLAN)))
   sequence=result['post_inspection_sequence']
   require(sequence['installed_before']==sequence['installed_after']==installed and sequence['restoration_qualified']is True and(sequence['after_state_completed']is True),'POST_INSPECTION_INSTALL_AND_INDEPENDENT_RESTORATION_REQUIRED')
   result['post_assessments']=assessment_summary(prior,qa,flow.step,sequence,POST_PLAN)
   result['post_inspection_completed']=True
  except BaseException as error:
   if hasattr(session,'sequence_observation'):
    result['failed_post_inspection_sequence']=session.sequence_observation
   prior.remember(result,'independent_post_inspection',error)
 result['scoped_click_and_post_observation_completed']=result.get('click_acknowledged')is True and result.get('post_inspection_completed')is True and(result['error']is None)and(result['secondary_errors']==[])
 result['navigation_effect_classification']='PENDING_PRIVATE_POST_TREE_REVIEW'
 result['business_outcome_unknown']=True
 result['next_business_action_requires_new_observation_and_admission']=True
def search_page_evidence(qa,step,sequence,summaries,require_public_value):
 """A live exact input/button postcondition, without exporting node text."""
 scope=sequence['foreground_after']
 require(scope==sequence['foreground_before']and scope['activity']==SEARCH_ACTIVITY and(scope['package']==BILI)and(scope['uid']==BILI_UID),'OBSERVED_EXACT_BILI_SEARCH_ACTIVITY_REQUIRED')
 row=summaries['inspect']
 raw=read(step/(row['nonce']+'.assessment.json'),1048576,row['assessment_sha256'],row['assessment_bytes'])
 assessed=json.loads(raw)
 helper=assessed['helper']
 require(assessed.get('actual_command_returncode')==0 and assessed.get('actual_instrumentation_finish_code')==-1 and(helper.get('ok')is True)and(helper.get('error')is None)and(helper.get('secondary_errors')==[])and(helper.get('protocol')==qa.PROTOCOL)and(helper['host_scope_attestation']==scope)and(helper['self_uid']==UID)and(helper['nonce']==row['nonce'])and(helper['op']=='inspect')and(assessed['wire_sha256']==row['wire_sha256']==sha(qa.canonical(helper)))and(assessed['held_transport_returned_after_post_guard']is True),'LIVE_SEARCH_OBSERVATION_RECEIPT_REQUIRED')
 inspection=qa.inspect_record(helper['inspection'])
 edit=qa.select_unique_editable(inspection,EDIT_SELECTOR)
 button=qa.select_unique_clickable(inspection,SUBMIT_SELECTOR)
 input_node=next((node for node in inspection['nodes']if node['path']==edit['node_path']))
 if require_public_value:
  require(input_node.get('text')==PUBLIC_QUERY and input_node.get('text_truncated')is False and(input_node.get('text_sha256')==sha(PUBLIC_QUERY.encode())),'CURRENT_PUBLIC_QUERY_VALUE_NOT_OBSERVED')
 return{'activity':SEARCH_ACTIVITY,'assessment_sha256':row['assessment_sha256'],'wire_sha256':row['wire_sha256'],'tree_sha256':inspection['tree_sha256'],'input_resource_id':EDIT_SELECTOR['resource_id'],'input_node_sha256':edit['node_sha256'],'submit_resource_id':SUBMIT_SELECTOR['resource_id'],'submit_node_sha256':button['node_sha256'],'public_value_required':require_public_value,'public_value_observed':bool(require_public_value),'public_query_sha256':sha(PUBLIC_QUERY.encode()),'raw_node_or_input_text_exported':False}
def stable_search_page(prior,qa,flow,session,installed,result,phase,plans,require_public_value):
 began=time.monotonic()
 previous=None
 record={'maximum_sequences':4,'deadline_seconds':STABILITY_SECONDS,'observations':[],'qualified':False,'failed_reads_retried':False,'action_retried':False}
 result.setdefault('search_page_stability',{})[phase]=record
 for index,plan in enumerate(plans,1):
  require(time.monotonic()-began<=STABILITY_SECONDS,'SEARCH_STABILITY_DEADLINE')
  sequence=session.sequence(json.loads(json.dumps(plan)))
  require(sequence['installed_before']==sequence['installed_after']==installed and sequence['restoration_qualified']is True and(sequence['after_state_completed']is True),'SEARCH_STABILITY_IDENTITY_AND_RESTORATION_REQUIRED')
  summaries=assessment_summary(prior,qa,flow.step,sequence,plan)
  proof=search_page_evidence(qa,flow.step,sequence,summaries,require_public_value)
  key={'tree_sha256':proof['tree_sha256'],'window_sha256':summaries['inspect']['window_sha256'],'foreground':sequence['foreground_after'],'accessibility_state':sequence['accessibility_restoration']['state_after']}
  record['observations'].append({'sequence':index,'elapsed_ms':int((time.monotonic()-began)*1000),'complete_key':key,'search_page_postcondition':proof,'assessments':summaries,'restoration_qualified':True})
  require(time.monotonic()-began<=STABILITY_SECONDS,'SEARCH_STABILITY_DEADLINE')
  if previous==key:
   record['qualified']=True
   record['matching_sequences']=[index-1,index]
   record['future_action_still_requires_original_strict_freshness']=True
   return proof
  previous=key
 raise RuntimeError('SEARCH_PAGE_NOT_STABLE_IN_BOUNDED_READS')
def submit_current_public_query(session,qa,result):
 """Add one predicate to the original action-bound inspection selector.

    Session.sequence and its after-state/freshness behavior are unchanged. The
    contract delegates every other attribute and function to the pinned module.
    """
 require(session.qa is qa,'ORIGINAL_SESSION_CONTRACT_REQUIRED')
 class PublicSubmitContract:
  def __getattr__(self,name):
   return getattr(qa,name)
  def select_unique_clickable(self,inspection,selector):
   require(selector==SUBMIT_SELECTOR,'ONLY_FIXED_PUBLIC_SUBMIT_SELECTOR')
   edit=qa.select_unique_editable(inspection,EDIT_SELECTOR)
   node=next((n for n in inspection['nodes']if n['path']==edit['node_path']))
   require(node.get('text')==PUBLIC_QUERY and node.get('text_truncated')is False and(node.get('text_sha256')==sha(PUBLIC_QUERY.encode())),'ACTION_BOUND_PUBLIC_QUERY_VALUE_REQUIRED')
   target=qa.select_unique_clickable(inspection,selector)
   result['submit_action_bound_value']={'inspection_nonce':SUBMIT_PLAN['nonces']['inspect'],'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],'input_node_sha256':edit['node_sha256'],'submit_node_sha256':target['node_sha256'],'public_query_sha256':sha(PUBLIC_QUERY.encode()),'public_value_observed':True}
   return target
 session.qa=PublicSubmitContract()
 try:
  return session.sequence(json.loads(json.dumps(SUBMIT_PLAN)))
 finally:
  session.qa=qa
def public_query_sequences(prior,qa,flow,session,installed,result,first_click):
 navigation_sequences(prior,qa,flow,session,installed,result,first_click)
 result['public_query_sequences_started']=False
 result['query_submission_controls_completed']=False
 if result['error']is not None:
  return
 result['public_query_sequences_started']=True
 try:
  result['fresh_entry_search_page_postcondition']=search_page_evidence(qa,flow.step,result['post_inspection_sequence'],result['post_assessments'],False)
  result['edit_admission']=stable_search_page(prior,qa,flow,session,installed,result,'before_set_text',QUERY_STABILITY_PLANS,False)
  require(session.foreground()['activity']==SEARCH_ACTIVITY,'SEARCH_ACTIVITY_CHANGED_BEFORE_EDIT_SEQUENCE')
  result['set_text_sequence_started']=True
  edited=session.sequence(json.loads(json.dumps(SET_TEXT_PLAN)))
  result['set_text_sequence']=edited
  require(edited['installed_before']==edited['installed_after']==installed and edited.get('set_text_acknowledged')is True and(edited['restoration_qualified']is True)and(edited['after_state_completed']is True)and(edited['foreground_before']['activity']==SEARCH_ACTIVITY)and(edited['foreground_after']['activity']==SEARCH_ACTIVITY),'EXACT_PUBLIC_EDIT_AND_INDEPENDENT_RESTORATION_REQUIRED')
  result['set_text_assessments']=assessment_summary(prior,qa,flow.step,edited,SET_TEXT_PLAN)
  result['public_query_value_acknowledged']=True
  result['submit_admission']=stable_search_page(prior,qa,flow,session,installed,result,'before_submit',SUBMIT_STABILITY_PLANS,True)
  require(session.foreground()['activity']==SEARCH_ACTIVITY,'SEARCH_ACTIVITY_CHANGED_BEFORE_SUBMIT_SEQUENCE')
  result['submit_sequence_started']=True
  submitted=submit_current_public_query(session,qa,result)
  result['submit_sequence']=submitted
  require(submitted['installed_before']==submitted['installed_after']==installed and submitted.get('click_acknowledged')is True and(submitted['restoration_qualified']is True)and(submitted['after_state_completed']is True)and(submitted['foreground_before']['activity']==SEARCH_ACTIVITY),'EXACT_PUBLIC_SUBMIT_AND_INDEPENDENT_RESTORATION_REQUIRED')
  result['submit_assessments']=assessment_summary(prior,qa,flow.step,submitted,SUBMIT_PLAN)
  require(result['submit_action_bound_value']['tree_sha256']==result['submit_assessments']['inspect']['tree_sha256']and result['submit_action_bound_value']['window_sha256']==result['submit_assessments']['inspect']['window_sha256'],'ACTION_BOUND_PUBLIC_QUERY_INSPECTION_CHANGED')
  result['public_query_submit_acknowledged']=True
 except BaseException as error:
  if hasattr(session,'sequence_observation'):
   result['failed_public_query_sequence']=session.sequence_observation
  prior.remember(result,'public_query_sequences',error)
 finally:
  result['final_results_inspection_attempted']=True
  try:
   observed=session.sequence(json.loads(json.dumps(RESULTS_PLAN)))
   result['results_inspection_sequence']=observed
   require(observed['installed_before']==observed['installed_after']==installed and observed['restoration_qualified']is True and(observed['after_state_completed']is True),'RESULTS_OBSERVATION_AND_INDEPENDENT_RESTORATION_REQUIRED')
   result['results_assessments']=assessment_summary(prior,qa,flow.step,observed,RESULTS_PLAN)
   result['final_results_inspection_completed']=True
  except BaseException as error:
   if hasattr(session,'sequence_observation'):
    result['failed_results_sequence']=session.sequence_observation
   prior.remember(result,'independent_results_observation',error)
 result['query_submission_controls_completed']=result.get('public_query_value_acknowledged')is True and result.get('public_query_submit_acknowledged')is True and(result.get('final_results_inspection_completed')is True)and(result['error']is None)and(result['secondary_errors']==[])
 result['business_outcome_unknown']=True
 result['query_results_content_classification']='PENDING_PRIVATE_RESULTS_TREE_REVIEW'
def results_content_evidence(qa,inspection,scope):
 """Recognize the observed loading shape without claiming video results."""
 qa.scope(scope)
 qa.inspect_record(inspection)
 require(scope['activity']==SEARCH_ACTIVITY,'EXACT_RESULTS_ACTIVITY_REQUIRED')
 nodes=inspection['nodes']
 def exact(resource,kind):
  found=[n for n in nodes if n.get('visible')is True and n.get('enabled')is True and(n.get('password')is False)and(n.get('resource_id')==resource)and(n.get('resource_id_truncated')is False)and(n.get('class')==kind)and(n.get('class_truncated')is False)]
  require(len(found)==1,'EXACT_OBSERVED_RESULTS_CONTROL_REQUIRED:'+resource)
  return found[0]
 marker=exact('tv.danmaku.bili:id/search_fake_text','android.widget.TextView')
 require(marker.get('text')==PUBLIC_QUERY and marker.get('text_truncated')is False and(marker.get('text_sha256')==sha(PUBLIC_QUERY.encode())),'RESULTS_PUBLIC_QUERY_MARKER_CHANGED')
 exact('tv.danmaku.bili:id/search_result_layout','android.widget.FrameLayout')
 pager=exact('tv.danmaku.bili:id/pager','androidx.viewpager.widget.ViewPager')
 loading=[n for n in nodes if n.get('visible')is True and n.get('resource_id')in{'tv.danmaku.bili:id/loading_view','tv.danmaku.bili:id/loading'}]
 descendants=[n for n in nodes if n.get('visible')is True and n['path'].startswith(pager['path']+'/')]
 observed=not loading and bool(descendants)
 return{'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],'node_count':len(nodes),'loading_control_count':len(loading),'visible_pager_descendants':len(descendants),'public_query_marker_verified':True,'public_query_sha256':sha(PUBLIC_QUERY.encode()),'container_content_observed':observed,'classification':'CONTENT_PRESENT_PRIVATE_REVIEW_REQUIRED' if observed else 'LOADING_OR_EMPTY_CONTAINER','video_or_search_result_success_inferred':False,'raw_node_or_text_exported':False}
def observe_result_content(prior,qa,flow,session,installed,result):
 """Only successful reads can lead to another read; never resubmit a query."""
 began=time.monotonic()
 record={'maximum_additional_sequences':8,'deadline_seconds':RESULT_OBSERVATION_SECONDS,'observations':[],'qualified':False,'failed_reads_retried':False,'submit_retried':False}
 result['result_content_observation']=record
 for index,plan in enumerate([None,*RESULT_OBSERVATION_PLANS]):
  require(time.monotonic()-began<=RESULT_OBSERVATION_SECONDS,'RESULTS_OBSERVATION_DEADLINE')
  if plan is None:
   sequence=result['results_inspection_sequence']
   summaries=result['results_assessments']
  else:
   sequence=session.sequence(json.loads(json.dumps(plan)))
   require(sequence['installed_before']==sequence['installed_after']==installed and sequence['restoration_qualified']is True and(sequence['after_state_completed']is True),'RESULTS_READ_IDENTITY_AND_RESTORATION_REQUIRED')
   summaries=assessment_summary(prior,qa,flow.step,sequence,plan)
  scope=sequence['foreground_after']
  require(scope==sequence['foreground_before'],'RESULTS_READ_FOREGROUND_CHANGED')
  row=summaries['inspect']
  raw=read(flow.step/(row['nonce']+'.assessment.json'),1048576,row['assessment_sha256'],row['assessment_bytes'])
  assessed=json.loads(raw)
  helper=assessed['helper']
  require(assessed.get('actual_command_returncode')==0 and assessed.get('actual_instrumentation_finish_code')==-1 and(helper.get('ok')is True)and(helper.get('error')is None)and(helper.get('secondary_errors')==[])and(helper.get('protocol')==qa.PROTOCOL)and(helper['host_scope_attestation']==scope)and(helper['self_uid']==UID)and(helper['nonce']==row['nonce'])and(helper['op']=='inspect')and(assessed['wire_sha256']==row['wire_sha256']==sha(qa.canonical(helper)))and(assessed['held_transport_returned_after_post_guard']is True),'LIVE_RESULT_OBSERVATION_RECEIPT_REQUIRED')
  proof=results_content_evidence(qa,helper['inspection'],scope)
  record['observations'].append({'additional_sequence':index,'postcondition':proof,'elapsed_ms':int((time.monotonic()-began)*1000),'assessments':summaries,'restoration_qualified':sequence['restoration_qualified']})
  require(time.monotonic()-began<=RESULT_OBSERVATION_SECONDS,'RESULTS_OBSERVATION_DEADLINE')
  if proof['container_content_observed']:
   record['qualified']=True
   record['selected_additional_sequence']=index
   result['observed_results_sequence']=sequence
   result['observed_results_assessments']=summaries
   result['results_container_content_observed']=True
   result['results_content_classification']='PENDING_PRIVATE_RESULTS_CONTENT_REVIEW'
   return
 raise RuntimeError('RESULTS_CONTAINER_CONTENT_NOT_OBSERVED_IN_BOUNDED_READS')
def video_extension(expected,adapter,qa):
 manifest=verify_source(expected)
 path=HERE/'video_navigation.py'
 pin=manifest['files'][path.name]
 raw=read(path,65536,pin['sha256'],pin['bytes'])
 module=types.ModuleType('fixed_observed_course')
 module.__file__=str(path)
 exec(compile(raw,str(path),'exec'),module.__dict__)
 plans=[PLAN,POST_PLAN,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN,*STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS]
 module.validate(adapter,qa,[NONCE,*(n for p in plans for n in p['nonces'].values())])
 path=HERE/'controls_reveal.py'
 pin=manifest['files'][path.name]
 module.reveal=types.ModuleType('fixed_player_controls_reveal')
 module.reveal.__file__=str(path)
 exec(compile(read(path,65536,pin['sha256'],pin['bytes']),str(path),'exec'),module.reveal.__dict__)
 plans+=[module.VIDEO_PLAN,*module.VIDEO_STABILITY_PLANS,*module.VIDEO_POST_PLANS,*module.CONTENT_READY_PLANS]
 module.reveal.validate(adapter,qa,[NONCE,*(n for p in plans for n in p['nonces'].values())])
 path=HERE/'playback_controls.py'
 pin=manifest['files'][path.name]
 module.playback=types.ModuleType('fixed_player_button')
 module.playback.__file__=str(path)
 exec(compile(read(path,65536,pin['sha256'],pin['bytes']),str(path),'exec'),module.playback.__dict__)
 plans+=[module.reveal.REVEAL_PLAN,module.reveal.POST_PLAN]
 module.playback.validate(adapter,qa,[NONCE,*(n for p in plans for n in p['nonces'].values())])
 path=HERE/'post_foreground.py'
 pin=manifest['files'][path.name]
 module.first_click=types.ModuleType('owned_first_search_foreground')
 module.first_click.__file__=str(path)
 exec(compile(read(path,65536,pin['sha256'],pin['bytes']),str(path),'exec'),module.first_click.__dict__)
 module.first_click.validate(adapter,qa,PLAN)
 return module
def worker(expected,phase):
 verify_source(expected)
 fixed_plan()
 require(os.getuid()==os.geteuid()==0 and HERE==SOURCE and(phase in('launch','navigate')),'EXACT_ROOT_PHASE_REQUIRED')
 prior=load_prior()
 adapter,qa,proof,apk=prior.qualified_inputs()
 del apk
 video=video_extension(expected,adapter,qa)
 installed,admission=actual_install(prior,qa,proof)
 recorder=prior.recorder_module()
 plan=adapter.validate_plan(fixed_plan(),qa)
 adapter.validate_plan(POST_PLAN,qa)
 for stable_plan in[*STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN]:
  adapter.validate_plan(stable_plan,qa)
 step='launch-01' if phase=='launch' else 'pause-resume-01'
 args=types.SimpleNamespace(operation='launch' if phase=='launch' else 'owned-qa',adapter_manifest_sha256=R6_MANIFEST,flow_dir=FLOW,epoch_module=prior.RECORDER_ROOT/'references/framework_epoch.py',task_source=prior.RECORDER_ROOT/'references/task_scope_baseline.py',step=step,request={'phase':phase,'nonce':NONCE,'plan':plan,'post_plan':POST_PLAN,'stability_plans':STABILITY_PLANS,'set_text_plan':SET_TEXT_PLAN,'submit_plan':SUBMIT_PLAN,'results_plan':RESULTS_PLAN,'query_stability_plans':QUERY_STABILITY_PLANS,'submit_stability_plans':SUBMIT_STABILITY_PLANS,'result_observation_plans':RESULT_OBSERVATION_PLANS,'video_plan':video.VIDEO_PLAN,'video_post_plans':video.VIDEO_POST_PLANS,'content_ready_plans':video.CONTENT_READY_PLANS,'reveal_plan':video.reveal.REVEAL_PLAN,'reveal_post_plan':video.reveal.POST_PLAN,'playback_plans':video.playback.PAIRS,'actual_install':admission},unknown_step=None,observation_step=None,postcondition=None)
 result={'schema':1,'ok':False,'error':None,'secondary_errors':[],'phase':phase,'nonce':NONCE,'package':BILI,'uid':BILI_UID,'helper_package':SELF,'helper_uid':UID,'source_manifest_sha256':expected,'runtime_recorder_manifest_sha256':R6_MANIFEST,'actual_install':admission,'build':proof,'automatic_retry':False,'click_limit':5,'text_action_limit':1,'reveal_input_limit':1,'audio_actions':0,'permission_grants':0,'settings_writes':0,'old_v2_helper_called':False,'raw_ui_tree_private_only':True,'host_foreground_display_independently_verified':False,'required_helper_display':0,'business_success_verified':False,'whole_app_production_ready':False,'business_outcome_unknown':True}
 flow=None
 action_lock=None
 session=None
 try:
  flow=prior.current_flow_type(prior.verify_source(INSTALL_MANIFEST_SHA),recorder)(args)
  flow.begin(args,mutation=True)
  action_lock=recorder.lock_file(recorder.ACTION_LOCK)
  flow.guard()
  session=new_session(prior,adapter,flow,recorder,qa,proof)
  result['live_installed_before']=session.installed()
  require(result['live_installed_before']==installed,'INSTALLED_HELPER_CHANGED_SINCE_INSTALL02')
  if phase=='launch':
   result['launch']=flow.launch_locked()
   require(result['launch'].get('native_launch_acknowledged')is True and result['launch'].get('cleanup_allowed')is True,'OWNED_NATIVE_LAUNCH_REQUIRED')
   result['owned_task']=flow.selected_task()
  else:
   public_query_sequences(prior,qa,flow,session,installed,result,video.first_click)
   if result['error']is None:
    observe_result_content(prior,qa,flow,session,installed,result)
    video.run(types.SimpleNamespace(**globals()),prior,qa,flow,session,installed,result)
    if result['error']is None:
     video.playback.run(types.SimpleNamespace(**globals()),prior,qa,video.reveal,flow,session,installed,result)
  result['ok']=result['error']is None and result['secondary_errors']==[]and(phase=='launch' or(result.get('query_submission_controls_completed')is True and result.get('results_container_content_observed')is True and(result.get('video_click_and_observations_completed')is True)and(result.get('player_content_readiness_completed')is True)and(result.get('controls_reveal_and_observation_completed')is True)and(result.get('playback_button_transitions_completed')is True)))
 except BaseException as error:
  if session is not None and hasattr(session,'sequence_observation'):
   result['failed_inspection_sequence']=session.sequence_observation
  prior.remember(result,phase,error)
 finally:
  if flow is not None:
   try:
    flow.guard(attempted=flow.action_attempted)
    result['final_Main_guard_passed']=True
   except BaseException as error:
    prior.remember(result,'final_Main_guard',error)
   try:
    flow.close()
    result['held_binding_released']=True
   except BaseException as error:
    prior.remember(result,'held_binding_release',error)
  if action_lock is not None:
   try:
    os.close(action_lock)
    result['action_lock_released']=True
   except BaseException as error:
    prior.remember(result,'original_action_lock_release',error)
 result['action_attempted']=bool(flow is not None and flow.action_attempted)
 result['outcome_unknown']=result['action_attempted']and(phase=='navigate' or not result['ok'])
 result['ended_utc']=recorder.now()
 if flow is not None and flow.step is not None:
  try:
   recorder.write_new(flow.step/'result.json',result)
  except BaseException as error:
   prior.remember(result,'durable_phase_result_write',error)
   result['outcome_unknown']=result['action_attempted']
 print(json.dumps(result,ensure_ascii=False),flush=True)
 return 0 if result['ok']else 2
def durable_phase(observed,phase):
 step='launch-01' if phase=='launch' else 'pause-resume-01'
 path=FLOW/'steps'/step/'result.json'
 raw=read(path)
 value=json.loads(raw)
 require(observed==value and value.get('ok')is True and(value.get('phase')==phase)and(value.get('nonce')==NONCE)and(value.get('helper_uid')==UID)and(value.get('runtime_recorder_manifest_sha256')==R6_MANIFEST)and(value.get('outcome_unknown')is(phase=='navigate'))and(value.get('final_Main_guard_passed')is True)and(value.get('held_binding_released')is True)and(value.get('action_lock_released')is True),'ACTUAL_DURABLE_PHASE_REQUIRED:'+phase)
 if phase=='navigate':
  stable=value.get('pre_action_stability',{})
  require(stable.get('qualified')is True and stable.get('maximum_sequences')==8 and(stable.get('deadline_seconds')==FIRST_STABILITY_SECONDS)and(stable.get('minimum_matching_sequences')==FIRST_STABILITY_MATCHES)and(stable.get('minimum_capture_span_ms')==FIRST_STABILITY_SPAN_MS)and(len(stable.get('matching_sequences',[]))>=FIRST_STABILITY_MATCHES)and(stable.get('sampled_capture_span_ms',-1)>=FIRST_STABILITY_SPAN_MS)and(stable.get('future_action_still_requires_original_strict_freshness')is True),'ACTUAL_PRE_ACTION_COMPLETE_TREE_STABILITY_REQUIRED')
  require(value.get('search_page_stability',{}).get('before_set_text',{}).get('qualified')is True and value.get('search_page_stability',{}).get('before_submit',{}).get('qualified')is True and(value.get('submit_admission',{}).get('public_value_observed')is True)and(value.get('submit_action_bound_value',{}).get('public_value_observed')is True),'ACTUAL_EDIT_AND_SUBMIT_POSTCONDITION_REQUIRED')
  require(value.get('action_attempted')is True and value.get('video_click_and_observations_completed')is True and(value.get('player_content_readiness_completed')is True)and(value.get('player_content_readiness',{}).get('qualified')is True)and(value.get('controls_reveal_and_observation_completed')is True)and(value.get('playback_button_transitions_completed')is True)and(value.get('results_container_content_observed')is True)and(value.get('result_content_observation',{}).get('qualified')is True)and(value.get('scoped_click_and_post_observation_completed')is True)and(value.get('query_submission_controls_completed')is True)and(value.get('final_results_inspection_completed')is True)and(value.get('business_outcome_unknown')is True)and(value.get('business_success_verified')is False),'CLICK_OBSERVATION_SCOPE_MUST_RETAIN_UNKNOWN_BUSINESS_OUTCOME')
 return(value,{'path':str(path),'bytes':len(raw),'sha256':sha(raw)})
def owned_scope():
 raw=read(FLOW/'launch-scope.json',65536)
 selected=json.loads(raw)
 require(set(selected)=={'task','package','epoch_sha256','prelaunch_absent','cleanup_allowed','launch_step','prelaunch_task_ids','native_receipt_sha256'}and selected['package']==BILI and(selected['epoch_sha256']==MAIN_EPOCH)and(selected['launch_step']=='launch-01')and(selected['prelaunch_absent']is True)and(selected['cleanup_allowed']is True)and(type(selected['task'])is int)and(selected['task']>0)and isinstance(selected['prelaunch_task_ids'],list)and all((type(task)is int and task>=0 for task in selected['prelaunch_task_ids']))and(selected['task']not in selected['prelaunch_task_ids'])and re.fullmatch('[0-9a-f]{64}',selected['native_receipt_sha256']),'ORIGINAL_EXACT_OWNED_LAUNCH_SCOPE_REQUIRED')
 return(selected,{'path':str(FLOW/'launch-scope.json'),'bytes':len(raw),'sha256':sha(raw)})
def cleanup_worker(expected):
    """Own cleanup entry; original R6 cleanup and completion semantics remain."""
    verify_source(expected)
    require(os.getuid()==os.geteuid()==0 and HERE==SOURCE,'EXACT_ROOT_CLEANUP_REQUIRED')
    prior=load_prior()
    recorder=prior.recorder_module()
    manifest=prior.verify_source(INSTALL_MANIFEST_SHA)
    Flow=prior.current_flow_type(manifest,recorder)
    now=recorder.now
    write_new=recorder.write_new
    args=types.SimpleNamespace(operation='cleanup',adapter_manifest_sha256=R6_MANIFEST,
        flow_dir=FLOW,step='cleanup-01',
        epoch_module=prior.RECORDER_ROOT/'references/framework_epoch.py',
        task_source=prior.RECORDER_ROOT/'references/task_scope_baseline.py',
        request=None,unknown_step=None,observation_step=None,postcondition=None)
    os.umask(0o077)
    flow=Flow(args)
    mutation=True
    result = {'ok': False, 'automatic_retry': False, 'action_attempted': False, 'outcome_unknown': False,
              'business_success_verified': False}
    try:
        flow.begin(args, mutation)
        result.update(flow.cleanup())
        flow.guard(attempted=flow.action_attempted)
        result['ok'] = True
    except BaseException as exc:
        result.update(error_type=type(exc).__name__, error=str(exc), outcome_unknown=flow.action_attempted)
        if hasattr(exc, 'command_observation'):
            result['command_observation'] = exc.command_observation
        if hasattr(exc, 'details'):
            result['transport_failure'] = exc.details
    finally:
        try:
            flow.close()
        except BaseException as exc:
            result['ok'] = False
            result['outcome_unknown'] = flow.action_attempted
            if 'error' not in result:
                result.update(error_type=type(exc).__name__, error='HELD_BINDING_RELEASE_FAILED')
            result['release_error_type'] = type(exc).__name__
    result.update(action_attempted=flow.action_attempted, ended_utc=now(), epoch_sha256=flow.scope['epoch_sha256'])
    if flow.step is not None:
        write_new(flow.step / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    if not result['ok']:
        return 2
    return 0

def execute(expected):
 verify_source(expected)
 fixed_plan()
 require(os.getuid()==os.geteuid()==0 and HERE==SOURCE,'ROOT_EXACT_SOURCE_REQUIRED')
 require(not os.path.lexists(FLOW),'FRESH_UI_FLOW_REQUIRED_NO_PARTIAL_RETRY')
 prior=load_prior()
 ref=prior.references()
 claim=json.loads(read(ROOT/'once.claim.json',65536))
 require(claim.get('nonce')==NONCE and claim.get('source_manifest_sha256')==expected and(claim.get('automatic_retry')is False),'EXACT_ONCE_CLAIM_REQUIRED')
 evidence=ROOT/'evidence'
 evidence.mkdir(mode=448)
 result={'schema':1,'ok':False,'error':None,'secondary_errors':[],'source_manifest_sha256':expected,'nonce':NONCE,'flow':str(FLOW),'package':BILI,'uid':BILI_UID,'helper_package':SELF,'helper_uid':UID,'automatic_retry':False,'launch_worker_requested':False,'navigation_worker_requested':False,'cleanup_requested':False,'click_limit':5,'text_action_limit':1,'reveal_input_limit':1,'audio_actions':0,'old_v2_helper_called':False,'raw_ui_tree_private_only':True,'business_success_verified':False,'whole_app_production_ready':False,'business_outcome_unknown':True}
 activation=epoch=resource_before=recorder=video=None
 try:
  resource_before=prior.prepare_owned_limits()
  result['owned_before']=resource_before
  adapter,qa,proof,apk=prior.qualified_inputs()
  del apk
  video=video_extension(expected,adapter,qa)
  _,result['actual_install']=actual_install(prior,qa,proof)
  adapter.validate_plan(fixed_plan(),qa)
  adapter.validate_plan(POST_PLAN,qa)
  for stable_plan in[*STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN]:
   adapter.validate_plan(stable_plan,qa)
  activation=ref.current_baseline()
  epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'bili_inspect_epoch')
  guard=lambda:ref.main_guard(activation,epoch)
  result['Main_before']=guard()
  recorder=prior.recorder_module()
  source,contract=recorder.source_contract(R6_MANIFEST);contract.verify()
  common=['/usr/bin/python3','-I','-B',str(prior.RECORDER_ROOT/'recorder.py')]
  initial=ref.run_cli('01-init',common+['init','--adapter-manifest-sha256',R6_MANIFEST,'--flow-dir',str(FLOW),'--current-baseline',str(ref.BASELINE),'--baseline-sha256',ref.BASELINE_SHA,'--package',source.PACKAGE,'--component',source.COMPONENT],25,evidence,guard)
  require(initial.get('ok')is True and initial.get('scope_initialized')is True and(initial.get('epoch_sha256')==MAIN_EPOCH),'FRESH_ORIGINAL_FLOW_INIT_REQUIRED')
  result['launch_worker_requested']=True
  launched=ref.run_cli('02-launch',['/usr/bin/python3','-I','-B',str(HERE/'owned_navigation.py'),'--worker-once','launch','--source-manifest-sha256',expected],180,evidence,guard)
  _,result['launch_result']=durable_phase(launched,'launch')
  result['owned_task'],result['owned_scope']=owned_scope()
  result['navigation_worker_requested']=True
  observed=ref.run_cli('03-navigate',['/usr/bin/python3','-I','-B',str(HERE/'owned_navigation.py'),'--worker-once','navigate','--source-manifest-sha256',expected],240,evidence,guard)
  navigated,result['navigation_result']=durable_phase(observed,'navigate')
  result['navigation']={'foreground':navigated['controls_reveal_observation']['final_scope'],'controls_reveal_observation':navigated['controls_reveal_observation'],'playback_button_observation':navigated['playback_button_observation'],'video_selection':navigated['video_action_bound_selection'],'video_stability':navigated['video_stability'],'video_click_assessments':navigated['video_click_assessments'],'video_post_observations':navigated['video_post_observations'],'player_content_readiness':navigated['player_content_readiness'],'result_content_observation':navigated['result_content_observation'],'observed_results_assessments':navigated['observed_results_assessments'],'results_content_classification':navigated['results_content_classification'],'query_submission_controls_completed':navigated['query_submission_controls_completed'],'public_query_sha256':sha(PUBLIC_QUERY.encode()),'search_page_stability':navigated['search_page_stability'],'set_text_assessments':navigated['set_text_assessments'],'submit_assessments':navigated['submit_assessments'],'submit_action_bound_value':navigated['submit_action_bound_value'],'results_assessments':navigated['results_assessments'],'pre_action_stability':navigated['pre_action_stability'],'selector':PLAN['selector'],'click_assessments':navigated['click_assessments'],'post_assessments':navigated['post_assessments'],'click_restoration':navigated['click_sequence']['accessibility_restoration'],'post_restoration':navigated['post_inspection_sequence']['accessibility_restoration'],'click_acknowledged':True,'post_inspection_completed':True,'business_outcome_unknown':True,'effect_classification':'PENDING_PRIVATE_POST_TREE_REVIEW'}
  result['scoped_click_and_post_observation_completed']=True
  result['query_submission_controls_completed']=True
  result['results_container_content_observed']=True
  result['video_click_and_observations_completed']=True
  result['player_content_readiness_completed']=True
  result['controls_reveal_and_observation_completed']=True
  result['playback_button_transitions_completed']=True
  result['ok']=True
 except BaseException as error:
  prior.remember(result,'coordinator',error)
 finally:
  if result['launch_worker_requested']:
   try:
    if os.path.lexists(FLOW/'launch-scope.json'):
     selected,scope_pin=owned_scope()
     result['owned_task']=selected
     result['owned_scope']=scope_pin
     require(activation is not None and epoch is not None,'CLEANUP_MAIN_BINDING_REQUIRED')
     result['cleanup_requested']=True
     cleanup=ref.run_cli('04-cleanup',['/usr/bin/python3','-I','-B',str(HERE/'owned_navigation.py'),'--cleanup-once','--source-manifest-sha256',expected],100,evidence,lambda:ref.main_guard(activation,epoch))
     path=FLOW/'steps/cleanup-01/result.json'
     raw=read(path)
     durable=json.loads(raw)
     require(cleanup==durable and cleanup.get('ok')is True and(cleanup.get('outcome_unknown')is False)and(cleanup.get('epoch_sha256')==MAIN_EPOCH)and(cleanup.get('new_leaf_removed_and_verified')is True and cleanup.get('other_tasks_preserved')is True or(cleanup.get('new_task_already_absent')is True and cleanup.get('removal_attempted')is False)),'EXACT_OWNED_TASK_CLEANUP_REQUIRED')
     result['cleanup_result']={'path':str(path),'bytes':len(raw),'sha256':sha(raw)}
     result['owned_task_absent_after_cleanup']=True
    else:
     result['cleanup_not_authorized_without_original_owned_scope']=True
     result['possible_native_launch_outcome_requires_reconciliation']=os.path.lexists(FLOW/'launch-attempted.json')
   except BaseException as error:
    prior.remember(result,'exact_owned_task_retirement',error)
  if result['ok']and result.get('owned_task_absent_after_cleanup')is not True:
   prior.remember(result,'cleanup_completion',RuntimeError('ACTUAL_OWNED_CLEANUP_MISSING'))
  if video is not None:
   video.playback.retain_phase_results(types.SimpleNamespace(**globals()),prior,result,expected)
  if activation is not None and epoch is not None:
   try:
    result['Main_after']=ref.main_guard(activation,epoch)
   except BaseException as error:
    prior.remember(result,'final_Main_guard',error)
  try:
   verify_source(expected)
   load_prior()
   _,_,_,apk=prior.qualified_inputs()
   del apk
   prior.recorder_module().source_contract(R6_MANIFEST)[1].verify()
   result['source_and_artifact_unchanged']=True
  except BaseException as error:
   prior.remember(result,'final_source_and_artifact',error)
  if resource_before is not None:
   try:
    result['owned_after']=prior.owned_resources()
    prior.resources_qualified(resource_before,result['owned_after'])
   except BaseException as error:
    prior.remember(result,'final_owned_resources',error)
  try:
   pin=ref.write_new(ROOT/'result.json',result)
  except BaseException as error:
   prior.remember(result,'final_result_write',error)
   pin=None
  print(json.dumps({'ok':result['ok'],'result':pin,'error':result['error'],'secondary_errors':result['secondary_errors'],'raw_UI_tree_exported':False,'business_success_verified':False,'whole_app_production_ready':False}),flush=True)
 return 0 if result['ok']else 1
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 modes=parser.add_mutually_exclusive_group()
 modes.add_argument('--execute-once',action='store_true')
 modes.add_argument('--worker-once',choices=('launch','navigate'))
 modes.add_argument('--cleanup-once',action='store_true')
 parser.add_argument('--source-manifest-sha256')
 args=parser.parse_args()
 fixed_plan()
 if not args.execute_once and args.worker_once is None and not args.cleanup_once:
  print(json.dumps({'state':'PLAN_ONLY','root':str(ROOT),'flow':str(FLOW),'helper_uid':UID,'operation':'original launch/query/course open + one R10 reveal + two button label transitions + exact-task cleanup','plan':PLAN,'post_plan':POST_PLAN,'stability_plans':STABILITY_PLANS,'set_text_plan':SET_TEXT_PLAN,'submit_plan':SUBMIT_PLAN,'results_plan':RESULTS_PLAN,'query_stability_plans':QUERY_STABILITY_PLANS,'submit_stability_plans':SUBMIT_STABILITY_PLANS,'result_observation_plans':RESULT_OBSERVATION_PLANS,'click_limit':5,'text_action_limit':1,'reveal_input_limit':1,'audio_actions':0,'old_v2_helper_called':False,'private_raw_tree_not_for_Git':True,'remote_actions':0}))
  return 0
 os.umask(63)
 if args.cleanup_once:return cleanup_worker(args.source_manifest_sha256)
 return worker(args.source_manifest_sha256,args.worker_once)if args.worker_once else execute(args.source_manifest_sha256)
if __name__=='__main__':
 raise SystemExit(main())
