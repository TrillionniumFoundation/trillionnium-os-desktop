"""Owned first-search post-ACK observation; no recorder/backend replacements.

The first post-click sample is classified here. An old unclassified exception
never authorizes another read. Only explicit null focus permits bounded reads.
The copied R10 sequence below differs only at its post-foreground call.
"""
import hashlib
import re
import time
FIRST_PLAN={'schema':1,'operation':'click','selector':{'resource_id':'tv.danmaku.bili:id/expand_search','class':'android.widget.LinearLayout','content_desc':'Search bar, button'},'nonces':{'before':'536878436ee181ff61e75a85554e1066','inspect':'310fc54429702c7861fd990c916f7e2f','action':'dc5bc64aaa98fac791f6cd56c409f79e','after':'99f5c1b27968739ac363d73e82445891'}}
EXPECTED_ACTIVITY='tv.danmaku.bili/com.bilibili.search2.main.BiliMainSearchActivity'
FOCUS_PATTERN='\\bWindow\\{([0-9a-fA-F]+)\\s+u\\d+\\s+([A-Za-z_][A-Za-z0-9_.]*)/([A-Za-z0-9_.$]+)'
MAX_SAMPLES=3
DEADLINE_SECONDS=12
PAUSE_SECONDS=0.1
def require(value,reason):
 if not value:
  raise RuntimeError(reason)
def validate(adapter,qa,plan):
 require(plan==FIRST_PLAN and plan['operation']=='click' and(plan['selector']=={'resource_id':'tv.danmaku.bili:id/expand_search','class':'android.widget.LinearLayout','content_desc':'Search bar, button'}),'ONLY_FRESH_FIRST_SEARCH_CLICK_PLAN')
 adapter.validate_plan(plan,qa)
 require(qa.PACKAGE=='tv.danmaku.bili' and qa.UID==10117 and(qa.MAIN_EPOCH=='7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'),'ORIGINAL_MAIN_BILI_SCOPE_REQUIRED')
def classify(raw):
 """Retain counts/hash and a recognized scope, never raw dumpsys text."""
 require(isinstance(raw,bytes)and 0<len(raw)<=262144,'FOCUS_OBSERVATION_BYTE_BOUND')
 lines=[line.strip()for line in raw.decode('utf8','replace').splitlines()if 'mCurrentFocus=' in line]
 values=[]
 nulls=0
 invalid=0
 foreign_user=False
 for line in lines:
  if line=='mCurrentFocus=null':
   nulls+=1
   continue
  match=re.search(FOCUS_PATTERN,line)
  user=re.search('\\bWindow\\{[0-9a-fA-F]+\\s+u([0-9]+)\\s+',line)
  if not line.startswith('mCurrentFocus=')or match is None or user is None:
   invalid+=1
   continue
  foreign_user|=user.group(1)!='0'
  values.append((match.group(1).lower(),match.group(2),match.group(3)))
 unique=set(values)
 foreign_package=any((value[1]!='tv.danmaku.bili' for value in unique))
 record={'stdout_bytes':len(raw),'stdout_sha256':hashlib.sha256(raw).hexdigest(),'focus_line_count':len(lines),'parsed_focus_count':len(values),'unique_focus_count':len(unique),'explicit_null_count':nulls,'unparsed_focus_count':invalid,'foreign_package_present':foreign_package,'foreign_user_present':foreign_user,'raw_text_exported':False}
 value=None
 if not lines or invalid:
  kind='malformed_or_absent_focus_record'
 elif len(unique)>1:
  kind='multiple_distinct_focuses'
 elif foreign_package or foreign_user:
  kind='foreign_focus'
 elif not unique and nulls==len(lines):
  kind='explicit_zero_focus'
 elif nulls:
  kind='mixed_null_and_focus'
 else:
  require(len(unique)==1,'FOREGROUND_UNVERIFIED')
  token,package,activity=values[0]
  if package+'/'+activity==EXPECTED_ACTIVITY:
   kind='expected_search_focus'
   value={'package':package,'activity':activity,'window_token':token}
  else:
   kind='unexpected_bili_activity'
 record['classification']=kind
 return(record,value)
def observe_post_ack(self,plan,result):
 """First-sample authority is never borrowed from a later observation."""
 if not(plan==FIRST_PLAN and result.get('click_acknowledged')is True and(result.get('after_state_completed')is True)and(result.get('restoration_qualified')is True)and(result.get('post_state_matches_before')is True)and(result.get('error')is None)and(result.get('secondary_errors')==[])):
  return self.foreground()
 qa,f=(self.qa,self.flow)
 record={'schema':1,'qualified':False,'input_replayed':False,'additional_input_count':0,'maximum_samples':MAX_SAMPLES,'qualification_deadline_seconds':DEADLINE_SECONDS,'command_timeout_seconds':15,'first_sample_classification':None,'waiting_authorized_by_first_explicit_zero':False,'observations':[],'after_state_nonce':plan['nonces']['after'],'after_state_wire_sha256':result['post_termination_state']['wire_sha256'],'action_nonce':plan['nonces']['action'],'action_wire_sha256':result['accessibility_restoration']['wire_sha256'][1],'inspection_wire_sha256':result['inspection_wire_sha256'],'scope_before':result['foreground_before'],'owned_task':result['owned_task'],'raw_text_exported':False,'host_foreground_display_independently_verified':False,'original_unknown_actions_reclassified':False}
 result['first_search_post_ack_foreground']=record
 started=time.monotonic()
 for index in range(MAX_SAMPLES):
  require(time.monotonic()-started<DEADLINE_SECONDS,'POST_ACK_FOCUS_DEADLINE')
  row={'index':index,'classification':'not_observed','held_command_returned':False}
  record['observations'].append(row)
  try:
   f.guard(attempted=f.action_attempted)
   require(self.task()==result['owned_task'],'POST_ACK_OWNED_TASK_CHANGED')
   require(not f._private_backend_transport,'NO_NESTED_PRIVATE_BACKEND')
   before=f.transport._sequence
   f._private_backend_transport=True
   try:
    raw=f.android(['/system/bin/dumpsys','window','displays'],15,mutation=False)
   finally:
    f._private_backend_transport=False
   row['held_command_returned']=True
   row['transport_sequence']=f.transport._sequence
   require(row['transport_sequence']==before+1,'ONE_HELD_FOCUS_COMMAND_REQUIRED')
   classified,value=classify(raw)
   del raw
   row.update(classified)
   if index==0:
    record['first_sample_classification']=row['classification']
   require(row['classification']in('explicit_zero_focus','expected_search_focus'),'POST_ACK_FOCUS_REJECTED:'+row['classification'])
   f.guard(attempted=f.action_attempted)
   require(self.task()==result['owned_task'],'POST_ACK_OWNED_TASK_CHANGED')
   row['original_Main_and_owned_task_guards_passed']=True
   row['elapsed_ms']=int((time.monotonic()-started)*1000)
   require(time.monotonic()-started<=DEADLINE_SECONDS,'POST_ACK_FOCUS_DEADLINE')
   if value is not None:
    accepted=qa.scope({'package':value['package'],'uid':qa.UID,'user':0,'display':0,'activity':value['package']+'/'+value['activity'],'window_token':value['window_token'],'main_epoch_sha256':qa.MAIN_EPOCH,'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,'main_baseline_sha256':qa.MAIN_BASELINE_SHA,'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA})
    record['qualified']=True
    record['accepted_scope']=accepted
    return accepted
   if index==0:
    record['waiting_authorized_by_first_explicit_zero']=True
   require(record['waiting_authorized_by_first_explicit_zero']is True,'FIRST_ACTUAL_SAMPLE_MUST_AUTHORIZE_WAIT')
  except BaseException as error:
   row['error']={'type':type(error).__name__,'message':str(error)}
   raise
  if index+1<MAX_SAMPLES:
   time.sleep(min(PAUSE_SECONDS,max(0,DEADLINE_SECONDS-(time.monotonic()-started))))
 raise RuntimeError('POST_ACK_SEARCH_FOCUS_NOT_READY_IN_BOUNDED_READS')
def run(self,plan):
 require(plan==FIRST_PLAN,'ONLY_FRESH_FIRST_SEARCH_CLICK_PLAN')
 require(not set(plan['nonces'].values())&self.nonces,'FIRST_SEARCH_SEQUENCE_CANNOT_REPLAY')
 return owned_sequence(self,plan)
def owned_sequence(self,plan):
 qa=self.qa
 names=plan['nonces']
 result={'installed_before':self.installed(),'old_v2_helper_called':False,'business_success_verified':False,'audio_verified':False}
 def request(phase,op,**extra):
  return{'protocol':qa.PROTOCOL,'nonce':names[phase],'op':op,**extra}
 if plan['operation']=='state':
  result['state_only']=self.instrument(request('state','state'))
  result['installed_after']=self.installed()
  require(result['installed_before']==result['installed_after'],'OWNED_HELPER_INSTALLATION_CHANGED')
  return result
 primary=None
 before=middle=after=scope=None
 state_sequence_started=False
 result.update(error=None,secondary_errors=[],after_state_attempted=False,after_state_completed=False,restoration_qualified=False)
 self.sequence_observation=result
 def remember(phase,error):
  nonlocal primary
  record={'phase':phase,'type':type(error).__name__,'message':str(error)}
  if primary is None:
   primary=error
   result['error']=record
  else:
   result['secondary_errors'].append(record)
   primary.add_note(phase+': '+type(error).__name__+': '+str(error))
 try:
  result['owned_task']=self.task()
  state_sequence_started=True
  before=self.instrument(request('before','state'))
  scope=self.foreground()
  result['foreground_before']=scope
  inspected=self.instrument(request('inspect','inspect',scope=scope))
  require(self.foreground()==scope,'ORIGINAL_ACTIVITY_OR_WINDOW_CHANGED_AFTER_INSPECT')
  middle=inspected
  result['inspection_wire_sha256']=inspected['wire_sha256']
  if plan['operation']in('click','set_text'):
   editing=plan['operation']=='set_text'
   node=(qa.select_unique_editable if editing else qa.select_unique_clickable)(inspected['helper']['inspection'],plan['selector'])
   extra={'value':plan['value']}if editing else{}
   action=request('action',plan['operation'],scope=scope,inspection_nonce=names['inspect'],inspection_sha256=inspected['wire_sha256'],**node,**extra)
   middle=None
   middle=self.instrument(action)
   require(middle['helper']['action_window']==inspected['helper']['inspection']['window'],'ACKNOWLEDGED_ACTION_WINDOW_DIFFERS')
   result['set_text_acknowledged' if editing else 'click_acknowledged']=True
  elif plan['operation']=='reveal_controls':
   fields=qa.reveal_request_fields(inspected['helper']['inspection'],scope)
   action=request('action','reveal_controls',scope=scope,inspection_nonce=names['inspect'],inspection_sha256=inspected['wire_sha256'],**fields)
   middle=None
   middle=self.instrument(action)
   require(middle['helper']['action_window']==inspected['helper']['inspection']['window'],'REVEAL_ACKNOWLEDGED_WINDOW_DIFFERS')
   result['reveal_input_acknowledged']=True
   result['controls_revealed']=None
   result['post_input_inspection_sha256']=qa.sha(qa.canonical(middle['helper']['post_inspection']))
  elif plan['operation']=='player_button':
   fields=qa.player_button_request_fields(inspected['helper']['inspection'],scope,plan['transition'])
   action=request('action','player_button',scope=scope,inspection_nonce=names['inspect'],inspection_sha256=inspected['wire_sha256'],**fields)
   middle=None
   middle=self.instrument(action)
   require(middle['helper']['action_window']==inspected['helper']['inspection']['window'],'PLAYER_BUTTON_ACKNOWLEDGED_WINDOW_DIFFERS')
   result['player_button_acknowledged']=True
   result['player_transition_requested']=plan['transition']
   result['player_current_inspection_sha256']=middle['helper']['player_inspection_sha256']
   result['atomic_android_transaction']=False
 except BaseException as error:
  remember('state_inspection_or_action',error)
 finally:
  if state_sequence_started:
   result['after_state_attempted']=True
   try:
    after=self.instrument(request('after','state'))
    result['after_state_completed']=True
    result['post_termination_state']={'nonce':names['after'],'wire_sha256':after['wire_sha256'],'state':after['helper']['state'],'helper_uid':after['helper']['self_uid'],'ui_automation_connected':after['helper']['ui_automation_connected']}
    if before is not None:
     result['post_state_matches_before']=before['helper']['state']==after['helper']['state']
     require(result['post_state_matches_before'],'POST_TERMINATION_ACCESSIBILITY_STATE_CHANGED')
    if before is not None and middle is not None:
     result['accessibility_restoration']=qa.assess_restoration(before,middle,after)
     result['restoration_qualified']=True
   except BaseException as error:
    remember('independent_after_state',error)
  if scope is not None:
   try:
    result['foreground_after']=observe_post_ack(self,plan,result)
    if plan['operation']in('inspect','reveal_controls','player_button'):
     require(result['foreground_after']==scope,'READ_ONLY_INSPECT_FOREGROUND_CHANGED')
   except BaseException as error:
    remember('post_foreground',error)
  if 'owned_task' in result:
   try:
    require(self.task()==result['owned_task'],'POST_OPERATION_OWNED_TASK_CHANGED')
   except BaseException as error:
    remember('post_owned_task',error)
  try:
   result['installed_after']=self.installed()
   require(result['installed_before']==result['installed_after'],'OWNED_HELPER_INSTALLATION_CHANGED')
  except BaseException as error:
   remember('post_installed_identity',error)
 if primary is not None:
  primary.details={'previous_details':getattr(primary,'details',None),'qa_sequence_observation':result}
  raise primary
 require(result['after_state_completed']and result['restoration_qualified'],'INDEPENDENT_AFTER_STATE_AND_RESTORATION_REQUIRED')
 return result
