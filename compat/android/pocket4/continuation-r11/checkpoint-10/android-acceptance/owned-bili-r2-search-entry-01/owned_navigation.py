#!/usr/bin/env python3
"""One fresh Bilibili launch, exact search-entry click, observation and retirement.

Default PLAN is inert. One resource-bound ACTION_CLICK is allowed only after a
fresh inspection. A separate post-inspection preserves the actual result. No
text, playback, audio, install or settings action is provided; trees stay private.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-bilibili-r2-search-entry-01')
SOURCE = ROOT / 'source'
NONCE = '69b2d59b9d416e3d6c082a3610b45b63'
FLOW = Path('/home/alex/work/pocket4-bilibili-owned-qa-r2-flow-' + NONCE)
PLAN = {'schema': 1, 'operation': 'click', 'selector': {'resource_id': 'tv.danmaku.bili:id/expand_search', 'class': 'android.widget.LinearLayout', 'content_desc': 'Search bar, button'}, 'nonces': {'before': '7f379363fab11375e075a03c842960ec', 'inspect': 'd09eae3f89850fa2ae08d7ff7397ba43', 'action': '32275761f7cd00ae05a885f2732cc184', 'after': 'c9f88106b407b46ccb93ea594eb148b7'}}
POST_PLAN = {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'a84bcca86eceb025d3f1ac6a7b966997', 'inspect': '24dae2a7972bcaacd44990d9b3a9112d', 'after': 'ce95537f902655940e154edf325623c6'}}
SELF, UID = 'org.droidloom.qa.bili.r2', 10165
BILI, BILI_UID = 'tv.danmaku.bili', 10117
INSTALL_ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r2-install-state-01')
INSTALL_SOURCE = INSTALL_ROOT / 'source'
INSTALL_ENTRY_SHA = '03643e2c2ec4ff9fa42f2594c36e4fc3fe9ec871405f1d4b04ebb5a607d7008e'
INSTALL_MANIFEST_SHA = '6b58391ffaa0c1bbc65ad6a374026c7344ae9a37fcbd4ca377a18a9fc1e2353d'
R4_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
SESSION_SHA = 'e743be1ed97d730a49543a316576c8093bd2dda38d3185d270efb6e3ac14c652'
OLD_FLOW = Path('/home/alex/work/pocket4-bilibili-owned-qa-r2-flow-1c5dfa5297c2f249a3f19ecabbf86b55')
OLD_STEP = OLD_FLOW / 'steps/install-state-r2-01'
OLD_STATE_NONCE = '58986b6022b724c5854f57d4b10fffe7'
OLD_STATE_WIRE = 'dd158bdc78d6a84c34744d23b2c8ae393243a88d118e40b353304bf0ec5b8c7b'
OLD_PACKET = 'e0a24cad4cddf6922dc28b42e0498071ee8f130ed3d25d5defe04e4410bc8ff4'
MAIN_EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
FILES = {'owned_navigation.py','stage_execute.py','make_request.py','INPUTS.json','README.md'}
# Actual values below came from the fixed r2 install reader; none are inherited from r1.
INSTALL_JOB_ID = '1a1a95ffd50-fc05-34b4'
STATE_COMMAND_INDEX = 6
STATE_COMMAND_SHA = '58374b097ab9521ad18b205470e34281304ba31624ab6f854232208575e898c0'
EXPECTED_INSTALLED_IDENTITY = {'package': 'org.droidloom.qa.bili.r2', 'uid': 10165, 'base_apk': '/data/app/~~VMciBKn8QBVwkM_5mNHf4w==/org.droidloom.qa.bili.r2-BIxeY8VSnLgI5U9qHIc7PQ==/base.apk', 'apk_sha256': 'af478cebd9c4157471c8c7ee46b74463e55b8f47eb0a859af870b5950acee66b', 'bytes': 20624, 'held_file': {'device': 1811, 'inode': 788313, 'mode': 33188, 'uid': 1000, 'gid': 1000, 'bytes': 20624, 'mtime_ns': 1793843004601129506, 'nlink': 1}, 'signer_bound_by_exact_signed_apk_bytes': 'bbd4116f64c4d1c25387c0a70fb1f9eee71752065f242e8caa7d7522ce2c3d0a'}
INSTALL_RECORDS = {
    'coordinator':(INSTALL_ROOT/'result.json',3025,'9cef3fda15853de2edf2bc46e7965a6e2e017b466b34b567507fcb1ecdfa43ab'),
    'stage':(INSTALL_ROOT/'stage-result.json',2032,'01a1e40957b53b4e63c96839808d3c390a507b4417e57bc73cef1f1728bb4ab5'),
    'worker':(OLD_STEP/'result.json',6918,'2d2c1845a9877fc4fa025e6fc0af600349d9a77b7687dda9938944cb52da29cc'),
    'worker_command':(INSTALL_ROOT/'evidence/02-install-state.result.json',1151,'a609de8a82bd4b5c2a13ee42b9b6fafe85345eb76bc497209fb478f6f78b2158')}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=1048576, expected=None, size=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and
                0 <= first.st_size <= maximum, 'BOUNDED_SINGLE_REGULAR_FILE_REQUIRED: '+str(path))
        chunks = []; count = 0
        while True:
            part = os.read(fd,min(65536,maximum+1-count))
            if not part:
                break
            chunks.append(part); count += len(part)
            require(count <= maximum,'INPUT_GREW: '+str(path))
        last = os.fstat(fd)
        fields = ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        require(count == first.st_size and all(getattr(first,k) == getattr(last,k) for k in fields),
                'INPUT_CHANGED: '+str(path))
        raw = b''.join(chunks)
        require(expected is None or sha(raw) == expected,'INPUT_SHA_CHANGED: '+str(path))
        require(size is None or len(raw) == size,'INPUT_SIZE_CHANGED: '+str(path))
        return raw
    finally:
        os.close(fd)


def require_actual_install_binding():
    require(type(UID) is int and 10000 <= UID < 100000 and UID not in (10117,10125,10164),
            'ACTUAL_R2_INSTALL_UID_PENDING')
    require(type(STATE_COMMAND_INDEX) is int and 1 <= STATE_COMMAND_INDEX <= 16 and
            isinstance(STATE_COMMAND_SHA,str) and re.fullmatch('[0-9a-f]{64}',STATE_COMMAND_SHA) and
            isinstance(OLD_STATE_WIRE,str) and re.fullmatch('[0-9a-f]{64}',OLD_STATE_WIRE),
            'ACTUAL_R2_STATE_COMMAND_BINDING_PENDING')
    require(isinstance(EXPECTED_INSTALLED_IDENTITY,dict) and
            EXPECTED_INSTALLED_IDENTITY.get('package') == SELF and
            EXPECTED_INSTALLED_IDENTITY.get('uid') == UID,
            'ACTUAL_R2_INSTALLED_FILE_IDENTITY_PENDING')
    for name,(path,size,pin) in INSTALL_RECORDS.items():
        require(type(size) is int and 0 < size <= 65536 and isinstance(pin,str) and
                re.fullmatch('[0-9a-f]{64}',pin),'ACTUAL_R2_INSTALL_RECEIPT_PENDING:'+name)


def load_prior():
    require_actual_install_binding()
    path = INSTALL_SOURCE/'install_state.py'
    raw = read(path,65536,INSTALL_ENTRY_SHA,28012)
    prior = types.ModuleType('bili_actual_install02'); prior.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),prior.__dict__)
    manifest = prior.verify_source(INSTALL_MANIFEST_SHA)
    require(prior.RECORDER_MANIFEST == R4_MANIFEST and
            manifest['files']['session_binding.py']['sha256'] == SESSION_SHA,
            'ACTUAL_INSTALL02_R4_SOURCE_BINDING_CHANGED')
    return prior


def verify_source(expected):
    require(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected),'EXTERNAL_SOURCE_PIN_REQUIRED')
    manifest = json.loads(read(HERE/'SOURCE_PINS.json',65536,expected))
    require(set(manifest['files']) == FILES,'EXACT_FIVE_FILE_SOURCE_REQUIRED')
    for name,row in manifest['files'].items():
        read(HERE/name,65536,row['sha256'],row['bytes'])
    return manifest


def fixed_plan():
    values = [NONCE,*PLAN['nonces'].values(),*POST_PLAN['nonces'].values()]
    require(all(re.fullmatch('[0-9a-f]{32}',value) for value in values) and
            len(set(values)) == 8 and OLD_STATE_NONCE not in values,'FRESH_DISTINCT_NONCES_REQUIRED')
    return json.loads(json.dumps(PLAN))


def actual_install(prior, qa, proof):
    """Consume original pinned success; never relabel install01 or infer UID."""
    rows = {name:json.loads(read(path,65536,pin,size))
            for name,(path,size,pin) in INSTALL_RECORDS.items()}
    c,s,w,cmd = (rows[name] for name in ('coordinator','stage','worker','worker_command'))
    for row in (c,s,w):
        require(row.get('ok') is True and row.get('error') is None and row.get('secondary_errors') == [],
                'ACTUAL_INSTALL02_COMPLETE_SUCCESS_REQUIRED')
    require(c.get('source_manifest_sha256') == s.get('source_manifest_sha256') == INSTALL_MANIFEST_SHA and
            s.get('packet_sha256') == OLD_PACKET and s.get('coordinator_returncode') == 0 and
            s.get('source_unchanged') is True and c.get('source_and_artifact_unchanged') is True,
            'ACTUAL_INSTALL02_SOURCE_AND_TERMINAL_REQUIRED')
    require(s.get('coordinator_result') == {'path':str(INSTALL_RECORDS['coordinator'][0]),
        'bytes':INSTALL_RECORDS['coordinator'][1],'sha256':INSTALL_RECORDS['coordinator'][2]} and
        c.get('worker_result') == {'path':str(INSTALL_RECORDS['worker'][0]),
        'bytes':INSTALL_RECORDS['worker'][1],'sha256':INSTALL_RECORDS['worker'][2]},'ACTUAL_INSTALL02_RECEIPT_CHAIN_REQUIRED')
    require(cmd.get('spawned') is True and cmd.get('joined') is True and cmd.get('returncode') == 0 and
            cmd.get('timed_out') is False and cmd.get('secondary_errors') == [],'JOINED_INSTALL02_WORKER_REQUIRED')
    require(c.get('owned_package_uid') == w.get('owned_package_uid') == UID and
            c.get('owned_package_retained_for_separate_UI_admission') is True and
            w.get('package') == SELF and w.get('package_retained') is True and
            w.get('install_attempted') is True and w.get('install_success_observed') is True and
            w.get('state_attempted') is True and w.get('outcome_unknown') is False and
            w.get('runtime_recorder_manifest_sha256') == R4_MANIFEST and
            w.get('runtime_session_binding_sha256') == SESSION_SHA and w.get('build') == proof,
            'EXACT_INSTALLED_HELPER_AND_BUILD_REQUIRED')
    require(w.get('final_Main_guard_passed') is True and w.get('held_binding_released') is True and
            w.get('action_lock_released') is True and w.get('UI_actions') == w.get('audio_actions') == 0 and
            w.get('UiAutomation_connection_requested') is False and w.get('old_v2_helper_called') is False,
            'ACTUAL_INSTALL02_SCOPE_REQUIRED')
    for row in (c,s):
        require(row.get('Main_before') == row.get('Main_after') and
                row['Main_before'].get('Main_epoch_sha256') == MAIN_EPOCH and
                row['Main_before'].get('three_host_processes_match') is True and
                row['Main_before'].get('resource_limits_match') is True,'ACTUAL_INSTALL02_MAIN_CHAIN_REQUIRED')
    installed = w['installed_before_state']
    require(installed == w.get('installed_after_state') and installed.get('package') == SELF and
            installed.get('uid') == UID and installed.get('apk_sha256') == prior.APK_SHA and
            installed.get('bytes') == prior.APK_BYTES and
            installed.get('signer_bound_by_exact_signed_apk_bytes') == prior.SIGNER_SHA and
            installed == EXPECTED_INSTALLED_IDENTITY and
            installed['held_file']['nlink'] == 1,'ACTUAL_INSTALLED_APK_IDENTITY_REQUIRED')
    # The historical command number is read only from the fixed Install02
    # record. New UI commands are never assumed to share transport numbering.
    previous = w['state']
    stem = OLD_STEP/('command-%03d' % STATE_COMMAND_INDEX)
    command_raw = read(str(stem)+'.result.json',65536,
        STATE_COMMAND_SHA)
    command = json.loads(command_raw)
    out = read(str(stem)+'.stdout',1048576,previous['stdout_sha256'])
    err = read(str(stem)+'.stderr',1048576,previous['stderr_sha256'])
    require(command.get('owned_command_joined') is True and command.get('spawned') is True and
            command.get('timed_out') is False and command.get('errors') == [] and
            command.get('stdout_sha256') == sha(out) and command.get('stderr_sha256') == sha(err),
            'ACTUAL_INSTALL02_STATE_COMMAND_REQUIRED')
    assessed = qa.parse_completed(out,err,command['returncode'],
        {'protocol':qa.PROTOCOL,'nonce':OLD_STATE_NONCE,'op':'state'},UID)
    assessed['recorder_command_result_sha256'] = sha(command_raw)
    assessed['held_transport_returned_after_post_guard'] = True
    require(assessed == previous and previous['wire_sha256'] == c['state_wire_sha256'] == OLD_STATE_WIRE and
            previous['helper']['ui_automation_connected'] is False,'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')
    return installed, {'install_job':INSTALL_JOB_ID,
        'receipts':{name:{'path':str(path),'bytes':size,'sha256':pin}
                    for name,(path,size,pin) in INSTALL_RECORDS.items()},
        'state_wire_sha256':OLD_STATE_WIRE,'uid':UID,'APK_sha256':prior.APK_SHA,
        'signer_certificate_sha256':prior.SIGNER_SHA,'installed_identity':installed,
        'historical_state_reparsed':True,'historical_state_used_as_current_baseline':False}


def new_session(prior, adapter, flow, recorder, qa, proof):
    binding = prior.module(INSTALL_SOURCE/'session_binding.py',SESSION_SHA,'owned_bili_r4_session')
    return binding.new_session(adapter,flow,recorder,qa,proof,UID)


def assessment_summary(prior, qa, step, sequence, plan):
    """No node text, descriptions, screenshots or recommendations are returned."""
    values = {}
    for phase,nonce in plan['nonces'].items():
        path = step/(nonce+'.assessment.json')
        raw = read(path); value = json.loads(raw)
        require(value['helper']['nonce'] == nonce and value['helper']['self_uid'] == UID and
                value['held_transport_returned_after_post_guard'] is True,'CURRENT_ASSESSMENT_BINDING_CHANGED')
        values[phase] = {'nonce':nonce,'operation':value['helper']['op'],
            'assessment_sha256':sha(raw),'assessment_bytes':len(raw),
            'wire_sha256':value['wire_sha256'],
            'recorder_command_result_sha256':value['recorder_command_result_sha256'],
            'actual_command_returncode':value['actual_command_returncode'],
            'actual_instrumentation_finish_code':value['actual_instrumentation_finish_code']}
        if phase == 'inspect':
            inspection = qa.inspect_record(value['helper']['inspection'])
            require(value['wire_sha256'] == sequence['inspection_wire_sha256'],
                    'CURRENT_INSPECTION_WIRE_CHANGED')
            window = inspection['window']
            values[phase].update(tree_sha256=inspection['tree_sha256'],
                window_sha256=inspection['window_sha256'],node_count=len(inspection['nodes']),
                window={key:window[key] for key in ('package','display','type','focused')},
                window_observation=qa.window_observation(value['helper']['window_observation']),
                connection_scoped_window_id=inspection['connection_scoped_window_id'],
                complete=True,raw_tree_private_only=True)
        elif phase == 'action':
            helper = value['helper']
            require(helper['node_action'] == 'ACTION_CLICK' and helper['node_action_returned'] is True and
                    helper['action_attempted'] is True and helper['outcome_unknown'] is True,
                    'ACTUAL_SINGLE_CLICK_ACK_REQUIRED')
            values[phase].update(node_action=helper['node_action'],node_action_returned=True,
                action_attempted=True,outcome_unknown=True,
                target_node_path=helper['target_node_path'],target_node_sha256=helper['target_node_sha256'],
                inspection_nonce=helper['inspection_nonce'],inspection_sha256=helper['inspection_sha256'],
                action_window={key:helper['action_window'][key] for key in ('package','display','type','focused')},
                window_observation=qa.window_observation(helper['window_observation']))
    names = ('before','inspect','action','after') if plan['operation'] == 'click' else ('before','inspect','after')
    expected = ['state','inspect','click','state'] if plan['operation'] == 'click' else ['state','inspect','state']
    require([values[k]['operation'] for k in names] == expected,'EXACT_NEW_HELPER_COMMAND_SEQUENCE_REQUIRED')
    return values


def navigation_sequences(prior, qa, flow, session, installed, result):
    """One action, then one independent read-only observation, including failures.

    An acknowledged click remains an unknown business outcome. No subsequent
    mutation can consume this step as a successful business postcondition.
    """
    result['click_sequence_started'] = True
    try:
        result['click_sequence'] = session.sequence(fixed_plan())
        sequence = result['click_sequence']
        require(sequence['installed_before'] == sequence['installed_after'] == installed and
                sequence.get('click_acknowledged') is True and sequence['restoration_qualified'] is True and
                sequence['after_state_completed'] is True,
                'CLICK_ACK_INSTALL_AND_INDEPENDENT_RESTORATION_REQUIRED')
        result['click_assessments'] = assessment_summary(prior,qa,flow.step,sequence,PLAN)
        result['click_acknowledged'] = True
    except BaseException as error:
        if hasattr(session,'sequence_observation'):
            result['failed_click_sequence'] = session.sequence_observation
        prior.remember(result,'click_sequence',error)
    finally:
        # A one-shot read never replays an uncertain click. Its own state probes
        # are fresh and the existing transport can still reject a poisoned gate.
        result['post_inspection_attempted'] = True
        try:
            result['post_inspection_sequence'] = session.sequence(json.loads(json.dumps(POST_PLAN)))
            sequence = result['post_inspection_sequence']
            require(sequence['installed_before'] == sequence['installed_after'] == installed and
                    sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True,
                    'POST_INSPECTION_INSTALL_AND_INDEPENDENT_RESTORATION_REQUIRED')
            result['post_assessments'] = assessment_summary(prior,qa,flow.step,sequence,POST_PLAN)
            result['post_inspection_completed'] = True
        except BaseException as error:
            if hasattr(session,'sequence_observation'):
                result['failed_post_inspection_sequence'] = session.sequence_observation
            prior.remember(result,'independent_post_inspection',error)
    result['scoped_click_and_post_observation_completed'] = (
        result.get('click_acknowledged') is True and result.get('post_inspection_completed') is True and
        result['error'] is None and result['secondary_errors'] == [])
    result['navigation_effect_classification'] = 'PENDING_PRIVATE_POST_TREE_REVIEW'
    result['business_outcome_unknown'] = True
    result['next_business_action_requires_new_observation_and_admission'] = True


def worker(expected, phase):
    verify_source(expected); fixed_plan()
    require(os.getuid() == os.geteuid() == 0 and HERE == SOURCE and phase in ('launch','navigate'),
            'EXACT_ROOT_PHASE_REQUIRED')
    prior = load_prior(); adapter,qa,proof,apk = prior.qualified_inputs(); del apk
    installed,admission = actual_install(prior,qa,proof)
    recorder = prior.recorder_module()
    plan = adapter.validate_plan(fixed_plan(),qa)
    adapter.validate_plan(POST_PLAN,qa)
    step = 'launch-01' if phase == 'launch' else 'search-entry-01'
    args = types.SimpleNamespace(operation='launch' if phase == 'launch' else 'owned-qa',
        adapter_manifest_sha256=R4_MANIFEST,flow_dir=FLOW,
        epoch_module=prior.RECORDER_ROOT/'references/framework_epoch.py',
        task_source=prior.RECORDER_ROOT/'references/task_scope_baseline.py',step=step,
        request={'phase':phase,'nonce':NONCE,'plan':plan,'post_plan':POST_PLAN,'actual_install':admission},
        unknown_step=None,observation_step=None,postcondition=None)
    result = {'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'phase':phase,'nonce':NONCE,'package':BILI,'uid':BILI_UID,'helper_package':SELF,'helper_uid':UID,
        'source_manifest_sha256':expected,'runtime_recorder_manifest_sha256':R4_MANIFEST,
        'actual_install':admission,'build':proof,'automatic_retry':False,
        'click_limit':1,'text_actions':0,'audio_actions':0,'permission_grants':0,'settings_writes':0,
        'old_v2_helper_called':False,'raw_ui_tree_private_only':True,
        'host_foreground_display_independently_verified':False,'required_helper_display':0,
        'business_success_verified':False,'whole_app_production_ready':False,
        'business_outcome_unknown':True}
    flow = None; action_lock = None; session = None
    try:
        flow = recorder.Flow(args)
        flow.begin(args,mutation=True)
        action_lock = recorder.lock_file(recorder.ACTION_LOCK)
        flow.guard()
        session = new_session(prior,adapter,flow,recorder,qa,proof)
        result['live_installed_before'] = session.installed()
        require(result['live_installed_before'] == installed,'INSTALLED_HELPER_CHANGED_SINCE_INSTALL02')
        if phase == 'launch':
            # Original launch implementation, under the same original action
            # lock as the live APK proof. Do not reacquire via Flow.launch().
            result['launch'] = flow.launch_locked()
            require(result['launch'].get('native_launch_acknowledged') is True and
                    result['launch'].get('cleanup_allowed') is True,'OWNED_NATIVE_LAUNCH_REQUIRED')
            result['owned_task'] = flow.selected_task()
        else:
            navigation_sequences(prior,qa,flow,session,installed,result)
        result['ok'] = result['error'] is None and result['secondary_errors'] == [] and (
            phase == 'launch' or result.get('scoped_click_and_post_observation_completed') is True)
    except BaseException as error:
        if session is not None and hasattr(session,'sequence_observation'):
            result['failed_inspection_sequence'] = session.sequence_observation
        prior.remember(result,phase,error)
    finally:
        if flow is not None:
            try:
                flow.guard(attempted=flow.action_attempted)
                result['final_Main_guard_passed'] = True
            except BaseException as error:
                prior.remember(result,'final_Main_guard',error)
            try:
                flow.close(); result['held_binding_released'] = True
            except BaseException as error:
                prior.remember(result,'held_binding_release',error)
        if action_lock is not None:
            try:
                os.close(action_lock); result['action_lock_released'] = True
            except BaseException as error:
                prior.remember(result,'original_action_lock_release',error)
    result['action_attempted'] = bool(flow is not None and flow.action_attempted)
    result['outcome_unknown'] = result['action_attempted'] and (phase == 'navigate' or not result['ok'])
    result['ended_utc'] = recorder.now()
    if flow is not None and flow.step is not None:
        try:
            recorder.write_new(flow.step/'result.json',result)
        except BaseException as error:
            prior.remember(result,'durable_phase_result_write',error)
            result['outcome_unknown'] = result['action_attempted']
    # This result contains only scope, hashes, counters and restoration state.
    # All raw helper assessments and command stdout remain private.
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['ok'] else 2


def durable_phase(observed, phase):
    step = 'launch-01' if phase == 'launch' else 'search-entry-01'
    path = FLOW/'steps'/step/'result.json'
    raw = read(path); value = json.loads(raw)
    require(observed == value and value.get('ok') is True and value.get('phase') == phase and
            value.get('nonce') == NONCE and value.get('helper_uid') == UID and
            value.get('runtime_recorder_manifest_sha256') == R4_MANIFEST and
            value.get('outcome_unknown') is (phase == 'navigate') and value.get('final_Main_guard_passed') is True and
            value.get('held_binding_released') is True and value.get('action_lock_released') is True,
            'ACTUAL_DURABLE_PHASE_REQUIRED:'+phase)
    if phase == 'navigate':
        require(value.get('action_attempted') is True and
                value.get('scoped_click_and_post_observation_completed') is True and
                value.get('business_outcome_unknown') is True and value.get('business_success_verified') is False,
                'CLICK_OBSERVATION_SCOPE_MUST_RETAIN_UNKNOWN_BUSINESS_OUTCOME')
    return value, {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}


def owned_scope():
    raw = read(FLOW/'launch-scope.json',65536); selected = json.loads(raw)
    require(set(selected) == {'task','package','epoch_sha256','prelaunch_absent','cleanup_allowed',
        'launch_step','prelaunch_task_ids','native_receipt_sha256'} and
        selected['package'] == BILI and selected['epoch_sha256'] == MAIN_EPOCH and
        selected['launch_step'] == 'launch-01' and selected['prelaunch_absent'] is True and
        selected['cleanup_allowed'] is True and type(selected['task']) is int and selected['task'] > 0 and
        isinstance(selected['prelaunch_task_ids'],list) and
        all(type(task) is int and task >= 0 for task in selected['prelaunch_task_ids']) and
        selected['task'] not in selected['prelaunch_task_ids'] and
        re.fullmatch('[0-9a-f]{64}',selected['native_receipt_sha256']),
        'ORIGINAL_EXACT_OWNED_LAUNCH_SCOPE_REQUIRED')
    return selected, {'path':str(FLOW/'launch-scope.json'),'bytes':len(raw),'sha256':sha(raw)}


def execute(expected):
    verify_source(expected); fixed_plan()
    require(os.getuid() == os.geteuid() == 0 and HERE == SOURCE,'ROOT_EXACT_SOURCE_REQUIRED')
    require(not os.path.lexists(FLOW),'FRESH_UI_FLOW_REQUIRED_NO_PARTIAL_RETRY')
    prior = load_prior(); ref = prior.references()
    claim = json.loads(read(ROOT/'once.claim.json',65536))
    require(claim.get('nonce') == NONCE and claim.get('source_manifest_sha256') == expected and
            claim.get('automatic_retry') is False,'EXACT_ONCE_CLAIM_REQUIRED')
    evidence = ROOT/'evidence'; evidence.mkdir(mode=0o700)
    result = {'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'source_manifest_sha256':expected,'nonce':NONCE,'flow':str(FLOW),
        'package':BILI,'uid':BILI_UID,'helper_package':SELF,'helper_uid':UID,
        'automatic_retry':False,'launch_worker_requested':False,'navigation_worker_requested':False,
        'cleanup_requested':False,'click_limit':1,'text_actions':0,'audio_actions':0,
        'old_v2_helper_called':False,'raw_ui_tree_private_only':True,
        'business_success_verified':False,'whole_app_production_ready':False,
        'business_outcome_unknown':True}
    activation = epoch = resource_before = recorder = None
    try:
        resource_before = prior.prepare_owned_limits(); result['owned_before'] = resource_before
        adapter,qa,proof,apk = prior.qualified_inputs(); del apk
        _,result['actual_install'] = actual_install(prior,qa,proof)
        adapter.validate_plan(fixed_plan(),qa)
        adapter.validate_plan(POST_PLAN,qa)
        activation = json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
        epoch = ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'bili_inspect_epoch')
        guard = lambda: ref.main_guard(activation,epoch)
        result['Main_before'] = guard()
        recorder = prior.recorder_module()
        recorder.source_contract(R4_MANIFEST)[1].verify()
        common = ['/usr/bin/python3','-I',str(prior.RECORDER_ROOT/'recorder.py')]
        initial = ref.run_cli('01-init',common+['init','--adapter-manifest-sha256',R4_MANIFEST,
            '--flow-dir',str(FLOW),'--activation-after',str(ref.ACTIVATION),
            '--activation-sha256',ref.ACTIVATION_SHA,'--package',ref.PACKAGE,'--component',ref.COMPONENT],
            25,evidence,guard)
        require(initial.get('ok') is True and initial.get('scope_initialized') is True and
                initial.get('epoch_sha256') == MAIN_EPOCH,'FRESH_ORIGINAL_FLOW_INIT_REQUIRED')
        result['launch_worker_requested'] = True
        launched = ref.run_cli('02-launch',['/usr/bin/python3','-I',str(HERE/'owned_navigation.py'),
            '--worker-once','launch','--source-manifest-sha256',expected],180,evidence,guard)
        _,result['launch_result'] = durable_phase(launched,'launch')
        result['owned_task'],result['owned_scope'] = owned_scope()
        result['navigation_worker_requested'] = True
        observed = ref.run_cli('03-navigate',['/usr/bin/python3','-I',str(HERE/'owned_navigation.py'),
            '--worker-once','navigate','--source-manifest-sha256',expected],240,evidence,guard)
        navigated,result['navigation_result'] = durable_phase(observed,'navigate')
        result['navigation'] = {'foreground':navigated['post_inspection_sequence']['foreground_after'],
            'selector':PLAN['selector'],'click_assessments':navigated['click_assessments'],
            'post_assessments':navigated['post_assessments'],
            'click_restoration':navigated['click_sequence']['accessibility_restoration'],
            'post_restoration':navigated['post_inspection_sequence']['accessibility_restoration'],
            'click_acknowledged':True,'post_inspection_completed':True,
            'business_outcome_unknown':True,'effect_classification':'PENDING_PRIVATE_POST_TREE_REVIEW'}
        result['scoped_click_and_post_observation_completed'] = True
        result['ok'] = True
    except BaseException as error:
        prior.remember(result,'coordinator',error)
    finally:
        # A failed inspection/evidence write does not suppress independently
        # authorized retirement. Only the original positive owned scope can
        # authorize this one cleanup CLI. No package-wide close/force-stop.
        if result['launch_worker_requested']:
            try:
                if os.path.lexists(FLOW/'launch-scope.json'):
                    selected,scope_pin = owned_scope()
                    result['owned_task'] = selected; result['owned_scope'] = scope_pin
                    require(activation is not None and epoch is not None,'CLEANUP_MAIN_BINDING_REQUIRED')
                    result['cleanup_requested'] = True
                    cleanup = ref.run_cli('04-cleanup',[
                        '/usr/bin/python3','-I',str(prior.RECORDER_ROOT/'recorder.py'),'cleanup',
                        '--adapter-manifest-sha256',R4_MANIFEST,'--flow-dir',str(FLOW),
                        '--step','cleanup-01'],100,evidence,lambda:ref.main_guard(activation,epoch))
                    path = FLOW/'steps/cleanup-01/result.json'
                    raw = read(path); durable = json.loads(raw)
                    require(cleanup == durable and cleanup.get('ok') is True and
                        cleanup.get('outcome_unknown') is False and cleanup.get('epoch_sha256') == MAIN_EPOCH and
                        ((cleanup.get('new_leaf_removed_and_verified') is True and
                          cleanup.get('other_tasks_preserved') is True) or
                         (cleanup.get('new_task_already_absent') is True and
                          cleanup.get('removal_attempted') is False)),'EXACT_OWNED_TASK_CLEANUP_REQUIRED')
                    result['cleanup_result'] = {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}
                    result['owned_task_absent_after_cleanup'] = True
                else:
                    result['cleanup_not_authorized_without_original_owned_scope'] = True
                    result['possible_native_launch_outcome_requires_reconciliation'] = os.path.lexists(FLOW/'launch-attempted.json')
            except BaseException as error:
                prior.remember(result,'exact_owned_task_retirement',error)
        if result['ok'] and result.get('owned_task_absent_after_cleanup') is not True:
            prior.remember(result,'cleanup_completion',RuntimeError('ACTUAL_OWNED_CLEANUP_MISSING'))
        if activation is not None and epoch is not None:
            try:
                result['Main_after'] = ref.main_guard(activation,epoch)
            except BaseException as error:
                prior.remember(result,'final_Main_guard',error)
        try:
            verify_source(expected); load_prior()
            _,_,_,apk = prior.qualified_inputs(); del apk
            prior.recorder_module().source_contract(R4_MANIFEST)[1].verify()
            result['source_and_artifact_unchanged'] = True
        except BaseException as error:
            prior.remember(result,'final_source_and_artifact',error)
        if resource_before is not None:
            try:
                result['owned_after'] = prior.owned_resources()
                prior.resources_qualified(resource_before,result['owned_after'])
            except BaseException as error:
                prior.remember(result,'final_owned_resources',error)
        try:
            pin = ref.write_new(ROOT/'result.json',result)
        except BaseException as error:
            prior.remember(result,'final_result_write',error); pin = None
        print(json.dumps({'ok':result['ok'],'result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'raw_UI_tree_exported':False,
            'business_success_verified':False,'whole_app_production_ready':False}),flush=True)
    return 0 if result['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--execute-once',action='store_true')
    modes.add_argument('--worker-once',choices=('launch','navigate'))
    parser.add_argument('--source-manifest-sha256')
    args = parser.parse_args(); fixed_plan()
    if not args.execute_once and args.worker_once is None:
        print(json.dumps({'state':'PLAN_ONLY','root':str(ROOT),'flow':str(FLOW),'helper_uid':UID,
            'operation':'original launch + fresh inspect/exact search click + fresh post-inspect + exact-task cleanup',
            'plan':PLAN,'post_plan':POST_PLAN,'click_limit':1,'audio_actions':0,'old_v2_helper_called':False,
            'private_raw_tree_not_for_Git':True,'remote_actions':0}))
        return 0
    os.umask(0o077)
    return worker(args.source_manifest_sha256,args.worker_once) if args.worker_once else execute(args.source_manifest_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
