"""Two current-player button clicks and independent public-label observations.

Only the installed R6 Session performs input. No old node or coordinate is
authority; each click selects again from its own complete inspection.
"""
import json

RESOURCE = 'tv.danmaku.bili:id/gemini_halfscreen_play'
PAIRS = [{'phase': 'pause', 'before_label': '暂停', 'after_label': '播放', 'action': {'schema': 1, 'operation': 'click', 'nonces': {'before': 'd7aa1b248a3a9f08d33008aca554adad', 'inspect': 'd43da42d98febc6fbab451c00b86b882', 'action': '934e9b47e7c0c12de4e0c27bbea39071', 'after': '43bfa627966c065c6655afc979bc1d7c'}, 'selector': {'resource_id': 'tv.danmaku.bili:id/gemini_halfscreen_play', 'class': 'android.widget.ImageView', 'content_desc': '暂停'}}, 'post': {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '7649ac6ffdbfd555d6160e0d68d250a1', 'inspect': 'f2f75747e578ce98f1cadecf543d5db1', 'after': 'e3dc8aef61225a062adb495e18d0e064'}}}, {'phase': 'resume', 'before_label': '播放', 'after_label': '暂停', 'action': {'schema': 1, 'operation': 'click', 'nonces': {'before': '570cc2c20dcc56348f4197e98a4f514d', 'inspect': '6251d1fe9e4363c09afcc531c24f03b7', 'action': '4cf2e013eed48d205a173b028414ef2d', 'after': '17fc198e320e0ecbd00a97a2e1acc567'}, 'selector': {'resource_id': 'tv.danmaku.bili:id/gemini_halfscreen_play', 'class': 'android.widget.ImageView', 'content_desc': '播放'}}, 'post': {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '59e8c37a4d66518fd9e980daaebf9d41', 'inspect': 'd826b8fe373b7242a8c47a7c048310e6', 'after': '7c2dd7a8b7e5a0940433396eb8e1bd1c'}}}]


def selector(label):
 return {'resource_id':RESOURCE, 'class':'android.widget.ImageView', 'content_desc':label}


def validate(adapter, qa, used):
 qa.require(qa.PROTOCOL == 'pocket4-owned-bili-qa-v6' and len(PAIRS) == 2,
   'EXACT_R6_TWO_LABEL_TRANSITIONS_REQUIRED')
 values = []
 for row, labels in zip(PAIRS, (('pause', '暂停', '播放'), ('resume', '播放', '暂停'))):
  qa.require((row['phase'], row['before_label'], row['after_label']) == labels,
    'FIXED_PAUSE_THEN_CONDITIONAL_RESUME_REQUIRED')
  for plan in (row['action'], row['post']):
   adapter.validate_plan(plan, qa); values += list(plan['nonces'].values())
  qa.require(row['action']['operation'] == 'click' and
    row['action']['selector'] == selector(labels[1]) and row['post']['operation'] == 'inspect',
    'ONE_CLICK_AND_ONE_INDEPENDENT_READ_PER_TRANSITION')
 qa.require(len(values) == len(set(values)) == 14 and not set(values) & set(used),
   'FOURTEEN_NEW_DISTINCT_PLAYBACK_NONCES_REQUIRED')


def select_control(qa, reveal, inspection, scope, anchor, label):
 observed = reveal.controls_evidence(qa, inspection, scope)
 qa.require(qa.same_reveal_frame(anchor, observed['proof']), 'ABSOLUTE_PLAYER_CHANGED_BEFORE_TOGGLE')
 nodes = inspection['nodes']; by_path = {n['path']:n for n in nodes}
 rows = [n for n in nodes if n['resource_id'] == RESOURCE]
 qa.require(len(rows) == 1, 'UNIQUE_CURRENT_PLAYBACK_RESOURCE_REQUIRED')
 node = rows[0]; target = qa.select_unique_clickable(inspection, selector(label))
 controls = [n for n in nodes if n['resource_id'] == qa.PACKAGE + ':id/control_container']
 qa.require(len(controls) == 1, 'UNIQUE_CURRENT_CONTROL_CONTAINER_REQUIRED')
 controls = controls[0]; parent = by_path.get(node['path'].rsplit('/', 1)[0])
 crop = observed['proof']['viewport_bounds']; bounds = node['bounds']
 qa.require(parent is not None and parent['class'] == 'android.view.ViewGroup' and
   parent['class_truncated'] is False and parent['resource_id'] == '' and
   parent['resource_id_truncated'] is False and parent['visible'] is True and
   parent['enabled'] is True and parent['password'] is False and
   parent['path'].rsplit('/', 1)[0] == controls['path'] and parent['bounds'] == crop and
   controls['child_count'] == 1 and node['editable'] is False and
   node['text'] == '' and node['text_truncated'] is False and
   node['content_desc_sha256'] == qa.sha(label.encode()) and
   crop[0] <= bounds[0] < bounds[2] <= crop[2] and
   crop[1] <= bounds[1] < bounds[3] <= crop[3] and
   target == {'node_path':node['path'], 'node_sha256':node['node_sha256']},
   'EXACT_CURRENT_PLAYER_DIRECT_CONTROL_REQUIRED')
 return target, {'proof':observed['proof'], 'observed_public_label':label,
  'public_label_sha256':qa.sha(label.encode()), 'resource_id':RESOURCE,
  'node_path_sha256':qa.sha(node['path'].encode()), 'node_sha256':node['node_sha256'],
  'container_node_sha256':controls['node_sha256'], 'parent_node_sha256':parent['node_sha256'],
  'complete_current_inspection':True, 'historical_node_or_coordinate_used':False}


def click_sequence(base, qa, reveal, flow, session, row, anchor, owned, record, ready):
 qa.require(session.qa is qa, 'ORIGINAL_SESSION_CONTRACT_REQUIRED')
 class Contract:
  def __getattr__(self, name):return getattr(qa, name)
  def select_unique_clickable(self, inspection, requested):
   qa.require(requested == selector(row['before_label']), 'FIXED_PLAYBACK_SELECTOR_REQUIRED')
   current = session.sequence_observation
   qa.require(current['owned_task'] == owned and current['foreground_before'] == anchor['scope'],
     'ACTION_BOUND_FOREGROUND_AND_OWNED_TASK_REQUIRED')
   if row['phase'] == 'pause':
    reveal.bind_pause_inspection(base, qa, flow, ready, row['action']['nonces']['inspect'],
     current['inspection_wire_sha256'], inspection, current['foreground_before'])
   target, proof = select_control(qa, reveal, inspection, current['foreground_before'],
          anchor, row['before_label'])
   record['action_bound_selection'] = proof
   return target
 session.qa = Contract()
 try:return session.sequence(json.loads(json.dumps(row['action'])))
 finally:session.qa = qa


def checked_sequence(qa, sequence, installed, anchor, owned):
 qa.require(sequence['installed_before'] == sequence['installed_after'] == installed and
   sequence['owned_task'] == owned and sequence['foreground_before'] ==
   sequence['foreground_after'] == anchor['scope'] and
   sequence['after_state_completed'] is True and sequence['restoration_qualified'] is True and
   sequence['error'] is None and sequence['secondary_errors'] == [],
   'TOGGLE_SCOPE_INSTALL_TASK_AND_RESTORATION_REQUIRED')


def run(base, prior, qa, reveal, flow, session, installed, result):
 record = {'transitions':[], 'automatic_retry':False, 'input_kind':'ACTION_CLICK',
   'maximum_clicks':2, 'UI_label_transition_only':True,
   'media_pause_resume_verified':False, 'seek_verified':False, 'audio_verified':False}
 result['playback_button_observation'] = record
 result['playback_button_transitions_completed'] = False
 try:
  ready = result['controls_reveal_observation']
  base.require(ready.get('input_acknowledged') is True and
     ready.get('independent_read_deferred_to_pause_fresh_inspect') is True and
     result['error'] is None and result['secondary_errors'] == [],
     'RESTORED_REVEAL_INPUT_AND_PENDING_INDEPENDENT_INSPECTION_REQUIRED')
  anchor = ready['immediate_post_observation']['proof']; owned = ready['input_sequence']['owned_task']
  checked_sequence(qa, ready['input_sequence'], installed, anchor, owned)
  for row in PAIRS:
   phase = row['phase']; part = {'phase':phase, 'sequence_started':False,
    'click_acknowledged':False, 'independent_read_attempted':False,
    'independent_read_completed':False, 'transition_observed':False}
   record['transitions'].append(part)
   previous = getattr(session, 'sequence_observation', None)
   try:
    part['sequence_started'] = True
    sequence = click_sequence(base, qa, reveal, flow, session, row, anchor, owned, part, ready)
    part['sequence'] = sequence; checked_sequence(qa, sequence, installed, anchor, owned)
    if phase == 'pause':
     qa.require(ready.get('bound_to_pause_fresh_inspection') is True and
      ready['independent_assessment']['wire_sha256'] == sequence['inspection_wire_sha256'],
      'INDEPENDENT_OBSERVATION_MUST_BIND_THIS_PAUSE_SEQUENCE')
     ready['independent_sequence_restoration_qualified'] = True
     result['controls_reveal_and_observation_completed'] = True
    summaries = base.assessment_summary(prior, qa, flow.step, sequence, row['action'])
    helper, pin = reveal.assessment(base, qa, flow, row['action']['nonces']['action'],
            'click', anchor['scope'], summaries['action']['wire_sha256'])
    selected = part['action_bound_selection']; inspection = summaries['inspect']
    qa.require(sequence.get('click_acknowledged') is True and
     helper['inspection_nonce'] == row['action']['nonces']['inspect'] and
     helper['inspection_sha256'] == sequence['inspection_wire_sha256'] and
     qa.sha(helper['target_node_path'].encode()) == selected['node_path_sha256'] and
     helper['target_node_sha256'] == selected['node_sha256'] and
     helper['action_window'] == anchor['window'] and
     inspection['tree_sha256'] == selected['proof']['tree_sha256'] and
     inspection['window_sha256'] == selected['proof']['window_sha256'],
     'ACTUAL_TOGGLE_ACK_MUST_BIND_OWN_FRESH_SELECTION')
    part.update(click_acknowledged=True, assessments=summaries, action_assessment=pin)
   except BaseException as error:
    current = getattr(session, 'sequence_observation', None)
    if current is not None and current is not previous:part['failed_sequence'] = current
    prior.remember(result, phase + '_button', error)
   finally:
    if part['sequence_started']:
     part['independent_read_attempted'] = True
     previous = getattr(session, 'sequence_observation', None)
     try:
      sequence = session.sequence(json.loads(json.dumps(row['post'])))
      part['independent_sequence'] = sequence
      checked_sequence(qa, sequence, installed, anchor, owned)
      helper, pin = reveal.assessment(base, qa, flow, row['post']['nonces']['inspect'],
       'inspect', anchor['scope'], sequence['inspection_wire_sha256'])
      part.update(independent_read_completed=True, independent_assessment=pin)
      _, observed = select_control(qa, reveal, helper['inspection'], anchor['scope'],
             anchor, row['after_label'])
      part.update(independent_observation=observed, transition_observed=part['click_acknowledged'])
     except BaseException as error:
      current = getattr(session, 'sequence_observation', None)
      if current is not None and current is not previous:part['failed_independent_sequence'] = current
      prior.remember(result, phase + '_independent_read', error)
   if result['error'] is not None or result['secondary_errors'] or not part['transition_observed']:break
  result['playback_button_transitions_completed'] = (
   len(record['transitions']) == 2 and all(p['transition_observed'] for p in record['transitions']) and
   result['error'] is None and result['secondary_errors'] == [])
 except BaseException as error:prior.remember(result, 'playback_button_precondition', error)
 result['business_outcome_unknown'] = True
 result['playback_or_audio_success_inferred'] = False


def retain_phase_results(base, prior, result, expected):
 """Pin fixed receipts after cleanup, including a run_cli failure."""
 result['retained_phase_results'] = {}; result['retained_phase_commands'] = {}
 for phase, flag, step, command, prior_pin in (
  ('launch','launch_worker_requested','launch-01','02-launch','launch_result'),
  ('navigate','navigation_worker_requested','pause-resume-01','03-navigate','navigation_result')):
  if not result[flag]:continue
  for kind, path in (('results',base.FLOW/'steps'/step/'result.json'),
      ('commands',base.ROOT/'evidence'/(command+'.result.json'))):
   try:
    if not base.os.path.lexists(path):continue
    raw = base.read(path); value = json.loads(raw)
    if kind == 'results':
     binding = {'phase':phase,'nonce':base.NONCE,'package':base.BILI,'uid':base.BILI_UID,
      'helper_package':base.SELF,'helper_uid':base.UID,'source_manifest_sha256':expected,
      'runtime_recorder_manifest_sha256':base.R4_MANIFEST}
     base.require(all(value.get(k) == v for k,v in binding.items()),'RETAINED_WORKER_SCOPE_CHANGED')
    else:
     base.require(value.get('name') == command and value.get('argv') == [
      '/usr/bin/python3','-I',str(base.HERE/'owned_navigation.py'),'--worker-once',phase,
      '--source-manifest-sha256',expected],'RETAINED_COMMAND_SCOPE_CHANGED')
    pin = {'path':str(path),'bytes':len(raw),'sha256':base.sha(raw)}
    if kind == 'results' and prior_pin in result:
     base.require(result[prior_pin] == pin,'RETAINED_SUCCESSFUL_RECEIPT_CHANGED')
    result['retained_phase_'+kind][phase] = pin
   except BaseException as error:prior.remember(result,'retain_'+phase+'_'+kind,error)
