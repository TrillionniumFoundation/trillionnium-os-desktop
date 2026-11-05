#!/usr/bin/env python3
"""One owned Bilibili launch, public query, observed course open and retirement.

Default PLAN is inert. Three exact clicks and one fixed public-query edit are
allowed only after fresh complete observations. Original after-state and task
retirement remain mandatory. No playback controls, audio capture or installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types
import time

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-bilibili-r4-buffer-viewport-01')
SOURCE = ROOT / 'source'
NONCE = '225a2b3fc4969be2f6fd4f9f2f63c0dd'
FLOW = Path('/home/alex/work/pocket4-bilibili-owned-qa-r4-flow-' + NONCE)
PLAN = {'schema': 1, 'operation': 'click', 'selector': {'resource_id': 'tv.danmaku.bili:id/expand_search', 'class': 'android.widget.LinearLayout', 'content_desc': 'Search bar, button'}, 'nonces': {'before': 'fb04ed5aaf3d6355ce5c018dadbb864d', 'inspect': '041be5a9f666c0def463ceba764eed82', 'action': 'ba187ed37a44eacd2f49d5e1e1918a50', 'after': 'c21880920e06d46fccf0ff40d64b70d4'}}
POST_PLAN = {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '26b16855b7a24a4ec94c1c3c7fa81b66', 'inspect': 'fa51a2e32e385a7feb4367e7d69650f8', 'after': 'a5eb8dbfc5730610bd3c1b6d6aeb40b8'}}
STABILITY_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'd691c31a1d2e34355602fb8e7208d254', 'inspect': '9e2104fb13148d95448c53c3d1847661', 'after': 'ffb7618d3f1ac0fa7d04f9b27799d924'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'b5fea0b674c60b0715ef631834488230', 'inspect': '2ec1311106444eaf6b53c656ba23d140', 'after': '22528b31d75d1936d53c1462c854afdb'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'fa72d552dc0bca3bd84354dd0d7846a3', 'inspect': 'c0f3ed454e2fbd21541acc3ef5bf5c5d', 'after': '23e706c27a76d0a99a7029bef441e80a'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '5552a29c291a962234bdf54188b67900', 'inspect': 'a4b3de76354b671d55fb9f6c42b71667', 'after': 'd56c05e1dcb121d9d26a5d3d9ef3270c'}}]
STABILITY_SECONDS = 12
RESULT_OBSERVATION_SECONDS = 20
RESULT_OBSERVATION_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': '1fe30c97201e612a8ef37ad1a7e3b07e', 'inspect': '29264938c4046c82f5cff816283e41e2', 'after': 'f10791f992052727bced8a3680de2e72'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'c0184ad626a92af605d792bea9184d2f', 'inspect': 'f5585a01f89ddaaf876ce4a809c01135', 'after': 'cfb948f147ad8c7af3fc8fc1de365c63'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '1d08cebccb0324078a639b3913882691', 'inspect': '55eceb50ba2397bf08ccaf36383bfec4', 'after': '3d9d032c9f8b38cd140df4deb2c63384'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '3937d4f93d60d06237ca49d7a8871cd8', 'inspect': '88b0edb6520424c898cc88eefe16233f', 'after': '14a66eaf7028f3679c86b280287f887c'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '06725e0c9b72e919b5af3dc44badf660', 'inspect': '567d730e100ad933a8e847a4d87c39f1', 'after': '215b6df052c2ef9878cb10e5285507e7'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '4f7ea416899b4b1685fec37cf745459d', 'inspect': '8d2b643b785f88934e4a99a49c699fa5', 'after': '64e265acced98857bc8f192a451ee772'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'a5ddd1928bef5c1c4cf77f3ff8519508', 'inspect': '28805c46255a16ea0bff68ac3ed3e7bf', 'after': 'baeeef5f80cca63d334b5432a0771dc9'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '1a127744a5205a6ae2e602d496ff5865', 'inspect': 'dadd7f6ea5aed014831d43d8a6813523', 'after': 'a2b0440aac201bf3d6d058110dd37386'}}]
SEARCH_ACTIVITY = 'tv.danmaku.bili/com.bilibili.search2.main.BiliMainSearchActivity'
EDIT_SELECTOR = {'resource_id':'tv.danmaku.bili:id/search_src_text','class':'android.widget.EditText'}
SUBMIT_SELECTOR = {'resource_id':'tv.danmaku.bili:id/action_search','class':'android.widget.TextView'}
PUBLIC_QUERY = '微积分'
SET_TEXT_PLAN = {'schema': 1, 'operation': 'set_text', 'selector': {'resource_id': 'tv.danmaku.bili:id/search_src_text', 'class': 'android.widget.EditText'}, 'value': '微积分', 'nonces': {'before': '9fa14b9dd26fb6121a74ff6a56ce763f', 'inspect': 'c18e98e82cf3e9c1db9ec422a51eae2b', 'action': '829eacda142c655ea8909c43918023a6', 'after': '1d63a0513972b3510eb7e25c474acb64'}}
SUBMIT_PLAN = {'schema': 1, 'operation': 'click', 'selector': {'resource_id': 'tv.danmaku.bili:id/action_search', 'class': 'android.widget.TextView'}, 'nonces': {'before': '8a12a1cd9523b201ad0d2d92812e1418', 'inspect': 'c75b7c2fd015a2ffc9bdf80452166c9b', 'action': '8433d8276134cb592809d5ca144556cb', 'after': '8b0605e3e2f9784e329f256760fd2309'}}
RESULTS_PLAN = {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'c8b1c5887248f5b1f31c22f0a29965f3', 'inspect': '34d332de0bad5f6f68b0509a50cd7b19', 'after': '86b35c55c90de536dbd592174cc32fe6'}}
QUERY_STABILITY_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'df97c12fd26d9be43b2b22b0775dc626', 'inspect': 'e1b37c71702bb90e93876d0b5049abc7', 'after': 'd66db7c8e399a4fa9abf9fb77cf75b27'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '7d10e5815451b70b4537859edc336ef7', 'inspect': 'ac22f3b8c7aa6e068ae39d5e98a3c4d1', 'after': 'a7469cef4d3c99012a88a45ed90a0580'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'a80131a5a86d6d1d76caf9b98752e0a9', 'inspect': '2dbbd1e2115ef0d511ae8400e1f7cb8b', 'after': '06f9972037817f076e8cadaedc2280e6'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'b3dbba732c04c157cc6db5a518e8bb24', 'inspect': '04a6c394f28a8bb451171129f4695991', 'after': '2bdb0996dab3963694ad53360add1dc4'}}]
SUBMIT_STABILITY_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': '76111d6f1f29d08556102cece5a2bc21', 'inspect': 'e5357f9ff8a239549835cf4306457f99', 'after': 'e6bd2743cedf55c9c2b40e4bcb5468d5'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'fb17413ff446c92f30d528e06dd9d49c', 'inspect': '3fd4153526cd51a37dd22863d3834d9a', 'after': '2be5fa2d80d785f7d739f69cd306cc84'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'ea94bd9f4a5f39b3ce66751031a65ab2', 'inspect': 'fde51ae1465dd1a5d8a0be6b1cee5398', 'after': '86575f483d1191a53873827014bb3b90'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '1b1ba00e74f142f075a91ab039c76d90', 'inspect': 'fee599cadbce41854ae5b40fcbc9ce77', 'after': '92c43d58e89c907c4c4116e68e8c62ac'}}]
SELF, UID = 'org.droidloom.qa.bili.r4', 10169
BILI, BILI_UID = 'tv.danmaku.bili', 10117
INSTALL_ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r4-install-state-01')
INSTALL_SOURCE = INSTALL_ROOT / 'source'
INSTALL_ENTRY_SHA = '830d4d4bd849784f851139c42919965c7df50ef83265f309dc181acd596ca1f2'
INSTALL_ENTRY_BYTES = 28024
INSTALL_MANIFEST_SHA = 'd5360f83e2d48e480edd94989dda2597b440c009657b58f1747f2714c19286b2'
R4_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
SESSION_SHA = '481c97520ba9b57760a1ffcbd7c383d0ce75333f52984f3de1bd6b2fd58b9a97'
OLD_FLOW = Path('/home/alex/work/pocket4-bilibili-owned-qa-r4-flow-dbe9123975207fa1dce3ed2a35ddcfa7')
OLD_STEP = OLD_FLOW / 'steps/install-state-r4-01'
OLD_STATE_NONCE = '395066c472be8e687d2a1579315ddb9b'
OLD_STATE_WIRE = '10aa779d2943a22e3dc4167e85ea4db1b53ad569ee40c79b47088d4f0a7f8867'
OLD_PACKET = 'e5d1949d7cd0ddbec5fb4ff377da3dc71caa6a551adac71d90781dafd6519f4d'
MAIN_EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
FILES = {'owned_navigation.py','stage_execute.py','make_request.py','INPUTS.json','README.md','video_navigation.py','viewport_observation.py'}
# Exact actual r4 install/readback values. No older helper UID or artifact is inherited.
INSTALL_JOB_ID = '1a1aa3517da-fc05-3f20'
STATE_COMMAND_INDEX = 6
STATE_COMMAND_SHA = 'e9b2a3055bd7ddddfaa96e409b7e845ce9bb1cfa822f80b09d7567c0c290eab6'
EXPECTED_INSTALLED_IDENTITY = {'package': 'org.droidloom.qa.bili.r4', 'uid': 10169, 'base_apk': '/data/app/~~bbpn1GOVxii60aWdc5Mmeg==/org.droidloom.qa.bili.r4-Tg09dr8bAXwIELobH9ab_Q==/base.apk', 'apk_sha256': '2055dd59a489929a51127822474e101e1635ec8de7885564fa9462b41fd1bf32', 'bytes': 24720, 'held_file': {'device': 1811, 'inode': 789199, 'mode': 33188, 'uid': 1000, 'gid': 1000, 'bytes': 24720, 'mtime_ns': 1793856970133806199, 'nlink': 1}, 'signer_bound_by_exact_signed_apk_bytes': 'b02b2c2fecf0627667bfeef51bca62ffe865292c09a91fa4089df83c650a3ab8'}
INSTALL_RECORDS = {'coordinator':(INSTALL_ROOT/'result.json',3025,'2e19bc64b71461430c0581deec9c47db1f2c2144851e908371963b25e214d50f'),'stage':(INSTALL_ROOT/'stage-result.json',2032,'f466e61fba902d171d1c8fd42544d7e0a84067c73215740732d2a482a355c39e'),'worker':(OLD_STEP/'result.json',6995,'eedfc9aa8a534c63986c9fe39b0b98f2dc163df7069a19994b5ccbf13a07b3ea'),'worker_command':(INSTALL_ROOT/'evidence/02-install-state.result.json',1152,'f42e353ca8dee45c1873ddc8110f21ec8b0faa0decea3c7c36af5f232d6f22e4')}


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
    require(type(UID) is int and 10000 <= UID < 100000 and UID not in (10117,10125,10164,10165,10166),
            'ACTUAL_R4_INSTALL_UID_PENDING')
    require(type(STATE_COMMAND_INDEX) is int and 1 <= STATE_COMMAND_INDEX <= 16 and
            isinstance(STATE_COMMAND_SHA,str) and re.fullmatch('[0-9a-f]{64}',STATE_COMMAND_SHA) and
            isinstance(OLD_STATE_WIRE,str) and re.fullmatch('[0-9a-f]{64}',OLD_STATE_WIRE),
            'ACTUAL_R4_STATE_COMMAND_BINDING_PENDING')
    require(isinstance(EXPECTED_INSTALLED_IDENTITY,dict) and
            EXPECTED_INSTALLED_IDENTITY.get('package') == SELF and
            EXPECTED_INSTALLED_IDENTITY.get('uid') == UID,
            'ACTUAL_R4_INSTALLED_FILE_IDENTITY_PENDING')
    for name,(path,size,pin) in INSTALL_RECORDS.items():
        require(type(size) is int and 0 < size <= 65536 and isinstance(pin,str) and
                re.fullmatch('[0-9a-f]{64}',pin),'ACTUAL_R4_INSTALL_RECEIPT_PENDING:'+name)


def load_prior():
    require_actual_install_binding()
    path = INSTALL_SOURCE/'install_state.py'
    raw = read(path,65536,INSTALL_ENTRY_SHA,INSTALL_ENTRY_BYTES)
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
    require(set(manifest['files']) == FILES,'EXACT_SEVEN_FILE_SOURCE_REQUIRED')
    for name,row in manifest['files'].items():
        read(HERE/name,65536,row['sha256'],row['bytes'])
    return manifest


def fixed_plan():
    groups = (STABILITY_PLANS,QUERY_STABILITY_PLANS,SUBMIT_STABILITY_PLANS)
    require(all(len(group) == 4 and all(p.get('operation') == 'inspect' for p in group) for group in groups),
            'EXACT_READ_ONLY_STABILITY_PLANS_REQUIRED')
    require(len(RESULT_OBSERVATION_PLANS) == 8 and
            all(p.get('operation') == 'inspect' for p in RESULT_OBSERVATION_PLANS),
            'ONLY_EIGHT_ADDITIONAL_READ_ONLY_RESULT_PLANS')
    require(SET_TEXT_PLAN['operation'] == 'set_text' and SET_TEXT_PLAN['value'] == PUBLIC_QUERY == '微积分'
            and SET_TEXT_PLAN['selector'] == EDIT_SELECTOR and SUBMIT_PLAN['operation'] == 'click'
            and SUBMIT_PLAN['selector'] == SUBMIT_SELECTOR and RESULTS_PLAN['operation'] == 'inspect',
            'ONLY_THE_FIXED_OBSERVED_PUBLIC_QUERY_PLAN')
    plans = [PLAN,POST_PLAN,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN,
             *STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS]
    values = [NONCE,*(nonce for plan in plans for nonce in plan['nonces'].values())]
    require(all(re.fullmatch('[0-9a-f]{32}',value) for value in values) and
            len(set(values)) == 79 and OLD_STATE_NONCE not in values,'FRESH_DISTINCT_NONCES_REQUIRED')
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
                tree_observations=qa.tree_observations(value['helper']['tree_observations'],'inspect',True),
                complete=True,raw_tree_private_only=True)
        elif phase == 'action':
            helper = value['helper']
            require(helper['node_action'] == ('ACTION_SET_TEXT' if plan['operation'] == 'set_text' else 'ACTION_CLICK') and helper['node_action_returned'] is True and
                    helper['action_attempted'] is True and helper['outcome_unknown'] is True,
                    'ACTUAL_SINGLE_CLICK_ACK_REQUIRED')
            values[phase].update(node_action=helper['node_action'],node_action_returned=True,
                action_attempted=True,outcome_unknown=True,
                target_node_path=helper['target_node_path'],target_node_sha256=helper['target_node_sha256'],
                inspection_nonce=helper['inspection_nonce'],inspection_sha256=helper['inspection_sha256'],
                action_window={key:helper['action_window'][key] for key in ('package','display','type','focused')},
                tree_observations=qa.tree_observations(helper['tree_observations'],plan['operation'],True),
                window_observation=qa.window_observation(helper['window_observation']))
            if plan['operation'] == 'set_text':
                require(helper['target_resource_id'] == EDIT_SELECTOR['resource_id'] and
                        helper['requested_value_sha256'] == helper['observed_value_sha256'] == sha(PUBLIC_QUERY.encode()) and
                        helper['value_readback_verified'] is True,'ACTUAL_PUBLIC_QUERY_EDIT_READBACK_REQUIRED')
                values[phase].update(target_resource_id=helper['target_resource_id'],
                    requested_value_sha256=helper['requested_value_sha256'],
                    observed_value_sha256=helper['observed_value_sha256'],value_readback_verified=True)
    names = ('before','inspect','action','after') if plan['operation'] in ('click','set_text') else ('before','inspect','after')
    expected = ['state','inspect',plan['operation'],'state'] if plan['operation'] in ('click','set_text') else ['state','inspect','state']
    require([values[k]['operation'] for k in names] == expected,'EXACT_NEW_HELPER_COMMAND_SEQUENCE_REQUIRED')
    return values


def stable_before_click(prior, qa, flow, session, installed, result):
    """Observe two consecutive complete equal trees; never replay a failed read.

    This gate is additional. The actual action still takes its own fresh
    inspection and the original Java whole-tree/window/target checks.
    """
    began = time.monotonic()
    previous = None
    result['pre_action_stability'] = {'maximum_sequences':4,'deadline_seconds':STABILITY_SECONDS,
        'observations':[],'qualified':False,'failed_reads_retried':False,'action_retried':False}
    state = result['pre_action_stability']
    for index, plan in enumerate(STABILITY_PLANS,1):
        require(time.monotonic()-began <= STABILITY_SECONDS,'STABILITY_OBSERVATION_DEADLINE')
        sequence = session.sequence(json.loads(json.dumps(plan)))
        require(sequence['installed_before'] == sequence['installed_after'] == installed and
                sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True,
                'STABILITY_READ_INSTALL_AND_RESTORATION_REQUIRED')
        summaries = assessment_summary(prior,qa,flow.step,sequence,plan)
        observed = summaries['inspect']
        key = {'tree_sha256':observed['tree_sha256'],'window_sha256':observed['window_sha256'],
            'node_count':observed['node_count'],'foreground':sequence['foreground_after'],
            'accessibility_state':sequence['accessibility_restoration']['state_after']}
        elapsed = int((time.monotonic()-began)*1000)
        state['observations'].append({'sequence':index,'elapsed_ms':elapsed,'complete_key':key,
            'assessments':summaries,'restoration_qualified':True})
        require(time.monotonic()-began <= STABILITY_SECONDS,'STABILITY_OBSERVATION_DEADLINE')
        if previous == key:
            state['qualified'] = True
            state['matching_sequences'] = [index-1,index]
            state['future_action_still_requires_original_strict_freshness'] = True
            return
        previous = key
    raise RuntimeError('COMPLETE_TREE_NOT_STABLE_IN_BOUNDED_READS')


def navigation_sequences(prior, qa, flow, session, installed, result):
    """One action, then one independent read-only observation, including failures.

    An acknowledged click remains an unknown business outcome. No subsequent
    mutation can consume this step as a successful business postcondition.
    """
    result['click_sequence_started'] = False
    try:
        stable_before_click(prior,qa,flow,session,installed,result)
        result['click_sequence_started'] = True
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
            result['failed_click_sequence' if result['click_sequence_started'] else 'failed_stability_sequence'] = session.sequence_observation
        prior.remember(result,'click_sequence' if result['click_sequence_started'] else 'pre_action_stability',error)
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


def search_page_evidence(qa, step, sequence, summaries, require_public_value):
    """A live exact input/button postcondition, without exporting node text."""
    scope = sequence['foreground_after']
    require(scope == sequence['foreground_before'] and scope['activity'] == SEARCH_ACTIVITY and
            scope['package'] == BILI and scope['uid'] == BILI_UID,
            'OBSERVED_EXACT_BILI_SEARCH_ACTIVITY_REQUIRED')
    row = summaries['inspect']
    raw = read(step/(row['nonce']+'.assessment.json'),1048576,row['assessment_sha256'],row['assessment_bytes'])
    assessed = json.loads(raw);helper = assessed['helper']
    require(assessed.get('actual_command_returncode') == 0 and assessed.get('actual_instrumentation_finish_code') == -1 and
            helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors') == [] and
            helper.get('protocol') == qa.PROTOCOL and helper['host_scope_attestation'] == scope and helper['self_uid'] == UID and
            helper['nonce'] == row['nonce'] and helper['op'] == 'inspect' and
            assessed['wire_sha256'] == row['wire_sha256'] == sha(qa.canonical(helper)) and
            assessed['held_transport_returned_after_post_guard'] is True,
            'LIVE_SEARCH_OBSERVATION_RECEIPT_REQUIRED')
    inspection = qa.inspect_record(helper['inspection'])
    edit = qa.select_unique_editable(inspection,EDIT_SELECTOR)
    button = qa.select_unique_clickable(inspection,SUBMIT_SELECTOR)
    input_node = next(node for node in inspection['nodes'] if node['path'] == edit['node_path'])
    if require_public_value:
        require(input_node.get('text') == PUBLIC_QUERY and input_node.get('text_truncated') is False and
                input_node.get('text_sha256') == sha(PUBLIC_QUERY.encode()),'CURRENT_PUBLIC_QUERY_VALUE_NOT_OBSERVED')
    return {'activity':SEARCH_ACTIVITY,'assessment_sha256':row['assessment_sha256'],
        'wire_sha256':row['wire_sha256'],'tree_sha256':inspection['tree_sha256'],
        'input_resource_id':EDIT_SELECTOR['resource_id'],'input_node_sha256':edit['node_sha256'],
        'submit_resource_id':SUBMIT_SELECTOR['resource_id'],'submit_node_sha256':button['node_sha256'],
        'public_value_required':require_public_value,'public_value_observed':bool(require_public_value),
        'public_query_sha256':sha(PUBLIC_QUERY.encode()),'raw_node_or_input_text_exported':False}


def stable_search_page(prior, qa, flow, session, installed, result, phase, plans, require_public_value):
    began = time.monotonic();previous = None
    record = {'maximum_sequences':4,'deadline_seconds':STABILITY_SECONDS,'observations':[],
        'qualified':False,'failed_reads_retried':False,'action_retried':False}
    result.setdefault('search_page_stability',{})[phase] = record
    for index, plan in enumerate(plans,1):
        require(time.monotonic()-began <= STABILITY_SECONDS,'SEARCH_STABILITY_DEADLINE')
        sequence = session.sequence(json.loads(json.dumps(plan)))
        require(sequence['installed_before'] == sequence['installed_after'] == installed and
                sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True,
                'SEARCH_STABILITY_IDENTITY_AND_RESTORATION_REQUIRED')
        summaries = assessment_summary(prior,qa,flow.step,sequence,plan)
        proof = search_page_evidence(qa,flow.step,sequence,summaries,require_public_value)
        key = {'tree_sha256':proof['tree_sha256'],'window_sha256':summaries['inspect']['window_sha256'],
            'foreground':sequence['foreground_after'],
            'accessibility_state':sequence['accessibility_restoration']['state_after']}
        record['observations'].append({'sequence':index,'elapsed_ms':int((time.monotonic()-began)*1000),
            'complete_key':key,'search_page_postcondition':proof,'assessments':summaries,
            'restoration_qualified':True})
        require(time.monotonic()-began <= STABILITY_SECONDS,'SEARCH_STABILITY_DEADLINE')
        if previous == key:
            record['qualified'] = True;record['matching_sequences'] = [index-1,index]
            record['future_action_still_requires_original_strict_freshness'] = True
            return proof
        previous = key
    raise RuntimeError('SEARCH_PAGE_NOT_STABLE_IN_BOUNDED_READS')


def submit_current_public_query(session, qa, result):
    """Add one predicate to the original action-bound inspection selector.

    Session.sequence and its after-state/freshness behavior are unchanged. The
    contract delegates every other attribute and function to the pinned module.
    """
    require(session.qa is qa,'ORIGINAL_SESSION_CONTRACT_REQUIRED')

    class PublicSubmitContract:
        def __getattr__(self,name):
            return getattr(qa,name)

        def select_unique_clickable(self,inspection,selector):
            require(selector == SUBMIT_SELECTOR,'ONLY_FIXED_PUBLIC_SUBMIT_SELECTOR')
            edit = qa.select_unique_editable(inspection,EDIT_SELECTOR)
            node = next(n for n in inspection['nodes'] if n['path'] == edit['node_path'])
            require(node.get('text') == PUBLIC_QUERY and node.get('text_truncated') is False and
                    node.get('text_sha256') == sha(PUBLIC_QUERY.encode()),
                    'ACTION_BOUND_PUBLIC_QUERY_VALUE_REQUIRED')
            target = qa.select_unique_clickable(inspection,selector)
            result['submit_action_bound_value'] = {
                'inspection_nonce':SUBMIT_PLAN['nonces']['inspect'],
                'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
                'input_node_sha256':edit['node_sha256'],'submit_node_sha256':target['node_sha256'],
                'public_query_sha256':sha(PUBLIC_QUERY.encode()),'public_value_observed':True}
            return target

    session.qa = PublicSubmitContract()
    try:
        return session.sequence(json.loads(json.dumps(SUBMIT_PLAN)))
    finally:
        session.qa = qa


def public_query_sequences(prior, qa, flow, session, installed, result):
    # Preserve the already qualified entry sequence and its independent final read.
    navigation_sequences(prior,qa,flow,session,installed,result)
    result['public_query_sequences_started'] = False
    result['query_submission_controls_completed'] = False
    if result['error'] is not None:return
    result['public_query_sequences_started'] = True
    try:
        result['fresh_entry_search_page_postcondition'] = search_page_evidence(
            qa,flow.step,result['post_inspection_sequence'],result['post_assessments'],False)
        result['edit_admission'] = stable_search_page(prior,qa,flow,session,installed,result,
            'before_set_text',QUERY_STABILITY_PLANS,False)
        require(session.foreground()['activity'] == SEARCH_ACTIVITY,'SEARCH_ACTIVITY_CHANGED_BEFORE_EDIT_SEQUENCE')
        result['set_text_sequence_started'] = True
        edited = session.sequence(json.loads(json.dumps(SET_TEXT_PLAN)))
        result['set_text_sequence'] = edited
        require(edited['installed_before'] == edited['installed_after'] == installed and
                edited.get('set_text_acknowledged') is True and edited['restoration_qualified'] is True and
                edited['after_state_completed'] is True and edited['foreground_before']['activity'] == SEARCH_ACTIVITY and
                edited['foreground_after']['activity'] == SEARCH_ACTIVITY,
                'EXACT_PUBLIC_EDIT_AND_INDEPENDENT_RESTORATION_REQUIRED')
        result['set_text_assessments'] = assessment_summary(prior,qa,flow.step,edited,SET_TEXT_PLAN)
        result['public_query_value_acknowledged'] = True
        # A successful live observation of the exact value is required before
        # the separately admitted submit action; the edit acknowledgement alone
        # does not authorize another business decision.
        result['submit_admission'] = stable_search_page(prior,qa,flow,session,installed,result,
            'before_submit',SUBMIT_STABILITY_PLANS,True)
        require(session.foreground()['activity'] == SEARCH_ACTIVITY,'SEARCH_ACTIVITY_CHANGED_BEFORE_SUBMIT_SEQUENCE')
        result['submit_sequence_started'] = True
        submitted = submit_current_public_query(session,qa,result)
        result['submit_sequence'] = submitted
        require(submitted['installed_before'] == submitted['installed_after'] == installed and
                submitted.get('click_acknowledged') is True and submitted['restoration_qualified'] is True and
                submitted['after_state_completed'] is True and submitted['foreground_before']['activity'] == SEARCH_ACTIVITY,
                'EXACT_PUBLIC_SUBMIT_AND_INDEPENDENT_RESTORATION_REQUIRED')
        result['submit_assessments'] = assessment_summary(prior,qa,flow.step,submitted,SUBMIT_PLAN)
        require(result['submit_action_bound_value']['tree_sha256'] == result['submit_assessments']['inspect']['tree_sha256'] and
                result['submit_action_bound_value']['window_sha256'] == result['submit_assessments']['inspect']['window_sha256'],
                'ACTION_BOUND_PUBLIC_QUERY_INSPECTION_CHANGED')
        result['public_query_submit_acknowledged'] = True
    except BaseException as error:
        if hasattr(session,'sequence_observation'):result['failed_public_query_sequence'] = session.sequence_observation
        prior.remember(result,'public_query_sequences',error)
    finally:
        result['final_results_inspection_attempted'] = True
        try:
            observed = session.sequence(json.loads(json.dumps(RESULTS_PLAN)))
            result['results_inspection_sequence'] = observed
            require(observed['installed_before'] == observed['installed_after'] == installed and
                    observed['restoration_qualified'] is True and observed['after_state_completed'] is True,
                    'RESULTS_OBSERVATION_AND_INDEPENDENT_RESTORATION_REQUIRED')
            result['results_assessments'] = assessment_summary(prior,qa,flow.step,observed,RESULTS_PLAN)
            result['final_results_inspection_completed'] = True
        except BaseException as error:
            if hasattr(session,'sequence_observation'):result['failed_results_sequence'] = session.sequence_observation
            prior.remember(result,'independent_results_observation',error)
    result['query_submission_controls_completed'] = (
        result.get('public_query_value_acknowledged') is True and
        result.get('public_query_submit_acknowledged') is True and
        result.get('final_results_inspection_completed') is True and result['error'] is None and
        result['secondary_errors'] == [])
    result['business_outcome_unknown'] = True
    result['query_results_content_classification'] = 'PENDING_PRIVATE_RESULTS_TREE_REVIEW'


def results_content_evidence(qa, inspection, scope):
    """Recognize the observed loading shape without claiming video results."""
    qa.scope(scope);qa.inspect_record(inspection)
    require(scope['activity'] == SEARCH_ACTIVITY,'EXACT_RESULTS_ACTIVITY_REQUIRED')
    nodes = inspection['nodes']
    def exact(resource,kind):
        found = [n for n in nodes if n.get('visible') is True and n.get('enabled') is True and
            n.get('password') is False and n.get('resource_id') == resource and
            n.get('resource_id_truncated') is False and n.get('class') == kind and
            n.get('class_truncated') is False]
        require(len(found) == 1,'EXACT_OBSERVED_RESULTS_CONTROL_REQUIRED:'+resource)
        return found[0]
    marker = exact('tv.danmaku.bili:id/search_fake_text','android.widget.TextView')
    require(marker.get('text') == PUBLIC_QUERY and marker.get('text_truncated') is False and
            marker.get('text_sha256') == sha(PUBLIC_QUERY.encode()),'RESULTS_PUBLIC_QUERY_MARKER_CHANGED')
    exact('tv.danmaku.bili:id/search_result_layout','android.widget.FrameLayout')
    pager = exact('tv.danmaku.bili:id/pager','androidx.viewpager.widget.ViewPager')
    loading = [n for n in nodes if n.get('visible') is True and n.get('resource_id') in
        {'tv.danmaku.bili:id/loading_view','tv.danmaku.bili:id/loading'}]
    descendants = [n for n in nodes if n.get('visible') is True and
        n['path'].startswith(pager['path']+'/')]
    observed = not loading and bool(descendants)
    return {'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
        'node_count':len(nodes),'loading_control_count':len(loading),
        'visible_pager_descendants':len(descendants),'public_query_marker_verified':True,
        'public_query_sha256':sha(PUBLIC_QUERY.encode()),'container_content_observed':observed,
        'classification':'CONTENT_PRESENT_PRIVATE_REVIEW_REQUIRED' if observed else 'LOADING_OR_EMPTY_CONTAINER',
        'video_or_search_result_success_inferred':False,'raw_node_or_text_exported':False}


def observe_result_content(prior, qa, flow, session, installed, result):
    """Only successful reads can lead to another read; never resubmit a query."""
    began = time.monotonic()
    record = {'maximum_additional_sequences':8,'deadline_seconds':RESULT_OBSERVATION_SECONDS,
        'observations':[],'qualified':False,'failed_reads_retried':False,'submit_retried':False}
    result['result_content_observation'] = record
    for index, plan in enumerate([None,*RESULT_OBSERVATION_PLANS]):
        require(time.monotonic()-began <= RESULT_OBSERVATION_SECONDS,'RESULTS_OBSERVATION_DEADLINE')
        if plan is None:
            sequence = result['results_inspection_sequence'];summaries = result['results_assessments']
        else:
            sequence = session.sequence(json.loads(json.dumps(plan)))
            require(sequence['installed_before'] == sequence['installed_after'] == installed and
                    sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True,
                    'RESULTS_READ_IDENTITY_AND_RESTORATION_REQUIRED')
            summaries = assessment_summary(prior,qa,flow.step,sequence,plan)
        scope = sequence['foreground_after']
        require(scope == sequence['foreground_before'],'RESULTS_READ_FOREGROUND_CHANGED')
        row = summaries['inspect']
        raw = read(flow.step/(row['nonce']+'.assessment.json'),1048576,row['assessment_sha256'],row['assessment_bytes'])
        assessed = json.loads(raw);helper = assessed['helper']
        require(assessed.get('actual_command_returncode') == 0 and assessed.get('actual_instrumentation_finish_code') == -1 and
                helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors') == [] and
                helper.get('protocol') == qa.PROTOCOL and helper['host_scope_attestation'] == scope and
                helper['self_uid'] == UID and helper['nonce'] == row['nonce'] and helper['op'] == 'inspect' and
                assessed['wire_sha256'] == row['wire_sha256'] == sha(qa.canonical(helper)) and
                assessed['held_transport_returned_after_post_guard'] is True,
                'LIVE_RESULT_OBSERVATION_RECEIPT_REQUIRED')
        proof = results_content_evidence(qa,helper['inspection'],scope)
        record['observations'].append({'additional_sequence':index,'postcondition':proof,
            'elapsed_ms':int((time.monotonic()-began)*1000),'assessments':summaries,
            'restoration_qualified':sequence['restoration_qualified']})
        require(time.monotonic()-began <= RESULT_OBSERVATION_SECONDS,'RESULTS_OBSERVATION_DEADLINE')
        if proof['container_content_observed']:
            record['qualified'] = True;record['selected_additional_sequence'] = index
            result['observed_results_sequence'] = sequence
            result['observed_results_assessments'] = summaries
            result['results_container_content_observed'] = True
            result['results_content_classification'] = 'PENDING_PRIVATE_RESULTS_CONTENT_REVIEW'
            return
    raise RuntimeError('RESULTS_CONTAINER_CONTENT_NOT_OBSERVED_IN_BOUNDED_READS')


def video_extension(expected,adapter,qa):
    manifest=verify_source(expected);path=HERE/'video_navigation.py';pin=manifest['files'][path.name]
    raw=read(path,65536,pin['sha256'],pin['bytes'])
    module=types.ModuleType('fixed_observed_course');module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    plans=[PLAN,POST_PLAN,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN,
        *STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS]
    module.validate(adapter,qa,[NONCE,*(n for p in plans for n in p['nonces'].values())])
    path=HERE/'viewport_observation.py';pin=manifest['files'][path.name]
    module.viewport=types.ModuleType('fixed_player_viewport');module.viewport.__file__=str(path)
    exec(compile(read(path,65536,pin['sha256'],pin['bytes']),str(path),'exec'),module.viewport.__dict__)
    plans += [module.VIDEO_PLAN,*module.VIDEO_STABILITY_PLANS,*module.VIDEO_POST_PLANS]
    module.viewport.validate(adapter,qa,[NONCE,*(n for p in plans for n in p['nonces'].values())])
    return module


def worker(expected, phase):
    verify_source(expected); fixed_plan()
    require(os.getuid() == os.geteuid() == 0 and HERE == SOURCE and phase in ('launch','navigate'),
            'EXACT_ROOT_PHASE_REQUIRED')
    prior = load_prior(); adapter,qa,proof,apk = prior.qualified_inputs(); del apk
    video=video_extension(expected,adapter,qa)
    installed,admission = actual_install(prior,qa,proof)
    recorder = prior.recorder_module()
    plan = adapter.validate_plan(fixed_plan(),qa)
    adapter.validate_plan(POST_PLAN,qa)
    for stable_plan in [*STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN]: adapter.validate_plan(stable_plan,qa)
    step = 'launch-01' if phase == 'launch' else 'buffer-viewport-01'
    args = types.SimpleNamespace(operation='launch' if phase == 'launch' else 'owned-qa',
        adapter_manifest_sha256=R4_MANIFEST,flow_dir=FLOW,
        epoch_module=prior.RECORDER_ROOT/'references/framework_epoch.py',
        task_source=prior.RECORDER_ROOT/'references/task_scope_baseline.py',step=step,
        request={'phase':phase,'nonce':NONCE,'plan':plan,'post_plan':POST_PLAN,'stability_plans':STABILITY_PLANS,'set_text_plan':SET_TEXT_PLAN,'submit_plan':SUBMIT_PLAN,'results_plan':RESULTS_PLAN,'query_stability_plans':QUERY_STABILITY_PLANS,'submit_stability_plans':SUBMIT_STABILITY_PLANS,'result_observation_plans':RESULT_OBSERVATION_PLANS,'video_plan':video.VIDEO_PLAN,'video_post_plans':video.VIDEO_POST_PLANS,'viewport_plans':video.viewport.PLANS,'actual_install':admission},
        unknown_step=None,observation_step=None,postcondition=None)
    result = {'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'phase':phase,'nonce':NONCE,'package':BILI,'uid':BILI_UID,'helper_package':SELF,'helper_uid':UID,
        'source_manifest_sha256':expected,'runtime_recorder_manifest_sha256':R4_MANIFEST,
        'actual_install':admission,'build':proof,'automatic_retry':False,
        'click_limit':3,'text_action_limit':1,'audio_actions':0,'permission_grants':0,'settings_writes':0,
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
            public_query_sequences(prior,qa,flow,session,installed,result)
            if result['error'] is None:
                observe_result_content(prior,qa,flow,session,installed,result)
                video.run(types.SimpleNamespace(**globals()),prior,qa,flow,session,installed,result)
        result['ok'] = result['error'] is None and result['secondary_errors'] == [] and (
            phase == 'launch' or (result.get('query_submission_controls_completed') is True and
                                 result.get('results_container_content_observed') is True and
                                 result.get('video_click_and_observations_completed') is True and result.get('buffer_viewport_observation_completed') is True))
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
    step = 'launch-01' if phase == 'launch' else 'buffer-viewport-01'
    path = FLOW/'steps'/step/'result.json'
    raw = read(path); value = json.loads(raw)
    require(observed == value and value.get('ok') is True and value.get('phase') == phase and
            value.get('nonce') == NONCE and value.get('helper_uid') == UID and
            value.get('runtime_recorder_manifest_sha256') == R4_MANIFEST and
            value.get('outcome_unknown') is (phase == 'navigate') and value.get('final_Main_guard_passed') is True and
            value.get('held_binding_released') is True and value.get('action_lock_released') is True,
            'ACTUAL_DURABLE_PHASE_REQUIRED:'+phase)
    if phase == 'navigate':
        stable = value.get('pre_action_stability',{})
        require(stable.get('qualified') is True and stable.get('maximum_sequences') == 4 and
                stable.get('deadline_seconds') == STABILITY_SECONDS and
                stable.get('future_action_still_requires_original_strict_freshness') is True,
                'ACTUAL_PRE_ACTION_COMPLETE_TREE_STABILITY_REQUIRED')
        require(value.get('search_page_stability',{}).get('before_set_text',{}).get('qualified') is True and
                value.get('search_page_stability',{}).get('before_submit',{}).get('qualified') is True and
                value.get('submit_admission',{}).get('public_value_observed') is True and
                value.get('submit_action_bound_value',{}).get('public_value_observed') is True,
                'ACTUAL_EDIT_AND_SUBMIT_POSTCONDITION_REQUIRED')
        require(value.get('action_attempted') is True and
                value.get('video_click_and_observations_completed') is True and
                value.get('buffer_viewport_observation_completed') is True and
                value.get('results_container_content_observed') is True and
                value.get('result_content_observation',{}).get('qualified') is True and
                value.get('scoped_click_and_post_observation_completed') is True and
                value.get('query_submission_controls_completed') is True and value.get('final_results_inspection_completed') is True and
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
        'cleanup_requested':False,'click_limit':3,'text_action_limit':1,'audio_actions':0,
        'old_v2_helper_called':False,'raw_ui_tree_private_only':True,
        'business_success_verified':False,'whole_app_production_ready':False,
        'business_outcome_unknown':True}
    activation = epoch = resource_before = recorder = None
    try:
        resource_before = prior.prepare_owned_limits(); result['owned_before'] = resource_before
        adapter,qa,proof,apk = prior.qualified_inputs(); del apk
        video_extension(expected,adapter,qa)
        _,result['actual_install'] = actual_install(prior,qa,proof)
        adapter.validate_plan(fixed_plan(),qa)
        adapter.validate_plan(POST_PLAN,qa)
        for stable_plan in [*STABILITY_PLANS,*QUERY_STABILITY_PLANS,*SUBMIT_STABILITY_PLANS,*RESULT_OBSERVATION_PLANS,SET_TEXT_PLAN,SUBMIT_PLAN,RESULTS_PLAN]: adapter.validate_plan(stable_plan,qa)
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
        result['navigation'] = {'foreground':navigated['buffer_viewport_observation']['final_scope'],
            'buffer_viewport_observation':navigated['buffer_viewport_observation'],
             'video_selection':navigated['video_action_bound_selection'],
            'video_stability':navigated['video_stability'],
            'video_click_assessments':navigated['video_click_assessments'],
            'video_post_observations':navigated['video_post_observations'],
            'result_content_observation':navigated['result_content_observation'],
            'observed_results_assessments':navigated['observed_results_assessments'],
            'results_content_classification':navigated['results_content_classification'],
            'query_submission_controls_completed':navigated['query_submission_controls_completed'],
            'public_query_sha256':sha(PUBLIC_QUERY.encode()),
            'search_page_stability':navigated['search_page_stability'],
            'set_text_assessments':navigated['set_text_assessments'],'submit_assessments':navigated['submit_assessments'],
            'submit_action_bound_value':navigated['submit_action_bound_value'],
            'results_assessments':navigated['results_assessments'],
            'pre_action_stability':navigated['pre_action_stability'],
            'selector':PLAN['selector'],'click_assessments':navigated['click_assessments'],
            'post_assessments':navigated['post_assessments'],
            'click_restoration':navigated['click_sequence']['accessibility_restoration'],
            'post_restoration':navigated['post_inspection_sequence']['accessibility_restoration'],
            'click_acknowledged':True,'post_inspection_completed':True,
            'business_outcome_unknown':True,'effect_classification':'PENDING_PRIVATE_POST_TREE_REVIEW'}
        result['scoped_click_and_post_observation_completed'] = True
        result['query_submission_controls_completed'] = True
        result['results_container_content_observed'] = True
        result['video_click_and_observations_completed'] = True
        result['buffer_viewport_observation_completed'] = True
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
            'operation':'original launch/query/course open + bounded buffer reads + private viewport crops + exact-task cleanup',
            'plan':PLAN,'post_plan':POST_PLAN,'stability_plans':STABILITY_PLANS,'set_text_plan':SET_TEXT_PLAN,'submit_plan':SUBMIT_PLAN,'results_plan':RESULTS_PLAN,'query_stability_plans':QUERY_STABILITY_PLANS,'submit_stability_plans':SUBMIT_STABILITY_PLANS,'result_observation_plans':RESULT_OBSERVATION_PLANS,'click_limit':3,'text_action_limit':1,'audio_actions':0,'old_v2_helper_called':False,
            'private_raw_tree_not_for_Git':True,'remote_actions':0}))
        return 0
    os.umask(0o077)
    return worker(args.source_manifest_sha256,args.worker_once) if args.worker_once else execute(args.source_manifest_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
