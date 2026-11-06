"""Fixed R9 pause/resume; prior inspect is context, current helper selects once."""
import json
RESOURCE='tv.danmaku.bili:id/gemini_halfscreen_play'
PAIRS=[{'phase':'pause','before_label':'暂停','after_label':'播放','action':{'schema':1,'operation':'player_button','nonces':{'before':'BILI_R9_02_000000000000000000132','inspect':'BILI_R9_02_000000000000000000133','action':'BILI_R9_02_000000000000000000134','after':'BILI_R9_02_000000000000000000135'},'transition':'pause'},'post':{'schema':1,'operation':'inspect','nonces':{'before':'BILI_R9_02_000000000000000000136','inspect':'BILI_R9_02_000000000000000000137','after':'BILI_R9_02_000000000000000000138'}}},{'phase':'resume','before_label':'播放','after_label':'暂停','action':{'schema':1,'operation':'player_button','nonces':{'before':'BILI_R9_02_000000000000000000139','inspect':'BILI_R9_02_000000000000000000140','action':'BILI_R9_02_000000000000000000141','after':'BILI_R9_02_000000000000000000142'},'transition':'resume'},'post':{'schema':1,'operation':'inspect','nonces':{'before':'BILI_R9_02_000000000000000000143','inspect':'BILI_R9_02_000000000000000000144','after':'BILI_R9_02_000000000000000000145'}}}]
def selector(label):
 return{'resource_id':RESOURCE,'class':'android.widget.ImageView','content_desc':label}
def validate(adapter,qa,used):
 qa.require(qa.PROTOCOL=='pocket4-owned-bili-qa-v9' and len(PAIRS)==2,'EXACT_R9_TWO_LABEL_TRANSITIONS_REQUIRED')
 values=[]
 for row,labels in zip(PAIRS,(('pause','暂停','播放'),('resume','播放','暂停'))):
  qa.require((row['phase'],row['before_label'],row['after_label'])==labels,'FIXED_PAUSE_THEN_CONDITIONAL_RESUME_REQUIRED')
  for plan in(row['action'],row['post']):
   adapter.validate_plan(plan,qa)
   values+=list(plan['nonces'].values())
  qa.require(row['action']['operation']=='player_button' and row['action']['transition']==labels[0]and(row['post']['operation']=='inspect'),'ONE_CLICK_AND_ONE_INDEPENDENT_READ_PER_TRANSITION')
 qa.require(len(values)==len(set(values))==14 and(not set(values)&set(used)),'FOURTEEN_NEW_DISTINCT_PLAYBACK_NONCES_REQUIRED')
def select_control(qa,reveal,inspection,scope,anchor,label):
 observed=reveal.controls_evidence(qa,inspection,scope)
 qa.require(qa.same_reveal_frame(anchor,observed['proof']),'ABSOLUTE_PLAYER_CHANGED_BEFORE_TOGGLE')
 nodes=inspection['nodes']
 by_path={n['path']:n for n in nodes}
 rows=[n for n in nodes if n['resource_id']==RESOURCE]
 qa.require(len(rows)==1,'UNIQUE_CURRENT_PLAYBACK_RESOURCE_REQUIRED')
 node=rows[0]
 target=qa.select_unique_clickable(inspection,selector(label))
 controls=[n for n in nodes if n['resource_id']==qa.PACKAGE+':id/control_container']
 qa.require(len(controls)==1,'UNIQUE_CURRENT_CONTROL_CONTAINER_REQUIRED')
 controls=controls[0]
 parent=by_path.get(node['path'].rsplit('/',1)[0])
 crop=observed['proof']['viewport_bounds']
 bounds=node['bounds']
 qa.require(parent is not None and parent['class']=='android.view.ViewGroup' and(parent['class_truncated']is False)and(parent['resource_id']=='')and(parent['resource_id_truncated']is False)and(parent['visible']is True)and(parent['enabled']is True)and(parent['password']is False)and(parent['path'].rsplit('/',1)[0]==controls['path'])and(parent['bounds']==crop)and(controls['child_count']==1)and(node['editable']is False)and(node['text']=='')and(node['text_truncated']is False)and(node['content_desc_sha256']==qa.sha(label.encode()))and(crop[0]<=bounds[0]<bounds[2]<=crop[2])and(crop[1]<=bounds[1]<bounds[3]<=crop[3])and(target=={'node_path':node['path'],'node_sha256':node['node_sha256']}),'EXACT_CURRENT_PLAYER_DIRECT_CONTROL_REQUIRED')
 return(target,{'proof':observed['proof'],'observed_public_label':label,'public_label_sha256':qa.sha(label.encode()),'resource_id':RESOURCE,'node_path_sha256':qa.sha(node['path'].encode()),'node_sha256':node['node_sha256'],'container_node_sha256':controls['node_sha256'],'parent_node_sha256':parent['node_sha256'],'complete_current_inspection':True,'historical_node_or_coordinate_used':False})
def player_sequence(base,qa,reveal,flow,session,row,anchor,owned,record,ready):
 qa.require(session.qa is qa,'ORIGINAL_SESSION_CONTRACT_REQUIRED')
 class Contract:
  def __getattr__(self,name):
   return getattr(qa,name)
  def player_button_request_fields(self,inspection,scope,transition):
   qa.require(transition==row['phase'],'FIXED_PLAYBACK_TRANSITION_REQUIRED')
   current=session.sequence_observation
   qa.require(current['owned_task']==owned and current['foreground_before']==scope==anchor['scope'],'ACTION_CONTEXT_FOREGROUND_AND_OWNED_TASK_REQUIRED')
   if row['phase']=='pause':
    reveal.bind_pause_inspection(base,qa,flow,ready,row['action']['nonces']['inspect'],current['inspection_wire_sha256'],inspection,scope)
   _,proof=select_control(qa,reveal,inspection,scope,anchor,row['before_label'])
   fields=qa.player_button_request_fields(inspection,scope,transition)
   qa.require(fields=={'transition':transition,'player_frame_sha256':qa.sha(qa.canonical(qa.player_frame(proof['proof'])))},'EXACT_PLAYER_FRAME_CONTEXT_FIELDS_REQUIRED')
   record['action_bound_context']=proof
   record['prior_inspection_is_context_only']=True
   return fields
 session.qa=Contract()
 try:
  return session.sequence(json.loads(json.dumps(row['action'])))
 finally:
  session.qa=qa
def current_action(base,qa,reveal,flow,row,anchor,sequence,summaries,part):
 helper,pin=reveal.assessment(base,qa,flow,row['action']['nonces']['action'],'player_button',anchor['scope'],summaries['action']['wire_sha256'])
 context=part['action_bound_context']
 inspection=summaries['inspect']
 request={'protocol':qa.PROTOCOL,'nonce':row['action']['nonces']['action'],'op':'player_button','scope':anchor['scope'],'inspection_nonce':row['action']['nonces']['inspect'],'inspection_sha256':sequence['inspection_wire_sha256'],'transition':row['phase'],'player_frame_sha256':qa.sha(qa.canonical(qa.player_frame(context['proof'])))}
 qa.require(helper['request_sha256']==qa.sha(qa.validate_request(request))and pin['wire_sha256']==sequence['accessibility_restoration']['wire_sha256'][1],'ACTUAL_PLAYER_BUTTON_REQUEST_AND_SESSION_WIRE_REQUIRED')
 counters=qa.tree_observations(helper['tree_observations'],'player_button',True)
 qa.assess_player_button(helper,request,qa.window_observation(helper['window_observation']),counters)
 _,selected=select_control(qa,reveal,helper['player_inspection'],anchor['scope'],anchor,row['before_label'])
 qa.require(sequence.get('player_button_acknowledged')is True and sequence.get('player_transition_requested')==row['phase']and(sequence.get('player_current_inspection_sha256')==helper['player_inspection_sha256'])and(sequence.get('atomic_android_transaction')is False)and(helper['player_scope']==selected['proof'])and(qa.sha(helper['target_node_path'].encode())==selected['node_path_sha256'])and(helper['target_node_sha256']==selected['node_sha256'])and(helper['action_window']==anchor['window'])and(inspection['tree_sha256']==context['proof']['tree_sha256'])and(inspection['window_sha256']==context['proof']['window_sha256']),'ACTUAL_TOGGLE_ACK_MUST_BIND_SAME_INVOCATION_CURRENT_SELECTION')
 part.update(current_action_selection=selected,current_inspection_sha256=helper['player_inspection_sha256'],current_capture_bindings=helper['player_capture_bindings'],current_tree_observations=counters,current_selection_age_ms=helper['player_selection_age_ms'],current_action_admitted_elapsed_ms=helper['player_action_admitted_elapsed_ms'],prior_tree_used_as_current_action_authority=False,atomic_android_transaction=False,click_acknowledged=True,assessments=summaries,action_assessment=pin)
def checked_sequence(qa,sequence,installed,anchor,owned):
 qa.require(sequence['installed_before']==sequence['installed_after']==installed and sequence['owned_task']==owned and(sequence['foreground_before']==sequence['foreground_after']==anchor['scope'])and(sequence['after_state_completed']is True)and(sequence['restoration_qualified']is True)and(sequence['error']is None)and(sequence['secondary_errors']==[]),'TOGGLE_SCOPE_INSTALL_TASK_AND_RESTORATION_REQUIRED')
def run(base,prior,qa,reveal,flow,session,installed,result):
 record={'transitions':[],'automatic_retry':False,'input_kind':'ACTION_CLICK','maximum_clicks':2,'UI_label_transition_only':True,'media_pause_resume_verified':False,'seek_verified':False,'audio_verified':False}
 result['playback_button_observation']=record
 result['playback_button_transitions_completed']=False
 try:
  ready=result['controls_reveal_observation']
  base.require(ready.get('input_acknowledged')is True and ready.get('independent_read_deferred_to_pause_fresh_inspect')is True and(result['error']is None)and(result['secondary_errors']==[]),'RESTORED_REVEAL_INPUT_AND_PENDING_INDEPENDENT_INSPECTION_REQUIRED')
  anchor=ready['immediate_post_observation']['proof']
  owned=ready['input_sequence']['owned_task']
  checked_sequence(qa,ready['input_sequence'],installed,anchor,owned)
  for row in PAIRS:
   phase=row['phase']
   part={'phase':phase,'sequence_started':False,'click_acknowledged':False,'independent_read_attempted':False,'independent_read_completed':False,'transition_observed':False}
   record['transitions'].append(part)
   previous=getattr(session,'sequence_observation',None)
   try:
    part['sequence_started']=True
    sequence=player_sequence(base,qa,reveal,flow,session,row,anchor,owned,part,ready)
    part['sequence']=sequence
    checked_sequence(qa,sequence,installed,anchor,owned)
    if phase=='pause':
     qa.require(ready.get('bound_to_pause_fresh_inspection')is True and ready['independent_assessment']['wire_sha256']==sequence['inspection_wire_sha256'],'INDEPENDENT_OBSERVATION_MUST_BIND_THIS_PAUSE_SEQUENCE')
     ready['independent_sequence_restoration_qualified']=True
     result['controls_reveal_and_observation_completed']=True
    summaries=base.assessment_summary(prior,qa,flow.step,sequence,row['action'])
    current_action(base,qa,reveal,flow,row,anchor,sequence,summaries,part)
   except BaseException as error:
    current=getattr(session,'sequence_observation',None)
    if current is not None and current is not previous:
     part['failed_sequence']=current
    prior.remember(result,phase+'_button',error)
   finally:
    if part['sequence_started']:
     part['independent_read_attempted']=True
     previous=getattr(session,'sequence_observation',None)
     try:
      sequence=session.sequence(json.loads(json.dumps(row['post'])))
      part['independent_sequence']=sequence
      checked_sequence(qa,sequence,installed,anchor,owned)
      helper,pin=reveal.assessment(base,qa,flow,row['post']['nonces']['inspect'],'inspect',anchor['scope'],sequence['inspection_wire_sha256'])
      part.update(independent_read_completed=True,independent_assessment=pin)
      _,observed=select_control(qa,reveal,helper['inspection'],anchor['scope'],anchor,row['after_label'])
      part.update(independent_observation=observed,transition_observed=part['click_acknowledged'])
     except BaseException as error:
      current=getattr(session,'sequence_observation',None)
      if current is not None and current is not previous:
       part['failed_independent_sequence']=current
      prior.remember(result,phase+'_independent_read',error)
   if result['error']is not None or result['secondary_errors']or(not part['transition_observed']):
    break
  result['playback_button_transitions_completed']=len(record['transitions'])==2 and all((p['transition_observed']for p in record['transitions']))and(result['error']is None)and(result['secondary_errors']==[])
 except BaseException as error:
  prior.remember(result,'playback_button_precondition',error)
 result['business_outcome_unknown']=True
 result['playback_or_audio_success_inferred']=False
def retain_phase_results(base,prior,result,expected):
 """Pin fixed receipts after cleanup, including a run_cli failure."""
 result['retained_phase_results']={}
 result['retained_phase_commands']={}
 for phase,flag,step,command,prior_pin in(('launch','launch_worker_requested','launch-01','02-launch','launch_result'),('navigate','navigation_worker_requested','pause-resume-01','03-navigate','navigation_result')):
  if not result[flag]:
   continue
  for kind,path in(('results',base.FLOW/'steps'/step/'result.json'),('commands',base.ROOT/'evidence'/(command+'.result.json'))):
   try:
    if not base.os.path.lexists(path):
     continue
    raw=base.read(path)
    value=json.loads(raw)
    if kind=='results':
     binding={'phase':phase,'nonce':base.NONCE,'package':base.BILI,'uid':base.BILI_UID,'helper_package':base.SELF,'helper_uid':base.UID,'source_manifest_sha256':expected,'runtime_recorder_manifest_sha256':base.R5_MANIFEST}
     base.require(all((value.get(k)==v for k,v in binding.items())),'RETAINED_WORKER_SCOPE_CHANGED')
    else:
     base.require(value.get('name')==command and value.get('argv')==['/usr/bin/python3','-I',str(base.HERE/'owned_navigation.py'),'--worker-once',phase,'--source-manifest-sha256',expected],'RETAINED_COMMAND_SCOPE_CHANGED')
    pin={'path':str(path),'bytes':len(raw),'sha256':base.sha(raw)}
    if kind=='results' and prior_pin in result:
     base.require(result[prior_pin]==pin,'RETAINED_SUCCESSFUL_RECEIPT_CHANGED')
    result['retained_phase_'+kind][phase]=pin
   except BaseException as error:
    prior.remember(result,'retain_'+phase+'_'+kind,error)
