#!/usr/bin/env python3
"""One fixed search_click bound to actual completed r2 inspect. No retry or business-success assertion."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

sys.dont_write_bytecode = True
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
BASE = {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py', 'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}
SESSION = {'path': '/home/alex/work/pocket4-beike-owned-new-session-20261106-r1/new_session_once.py', 'bytes': 28943, 'sha256': 'eb02cc1e7669be21ad7f741af2438b7442fbac767a83587a0b285f764f34c909'}
LAUNCH = {'path': '/home/alex/work/pocket4-beike-owned-new-session-20261106-r1/launch-owned-lifetime.json', 'bytes': 8135, 'sha256': 'a9e3c77e8b179e7c7702296ab23d97188ee809f2632bfdbcc44969774def68d4'}
LAUNCH_STDOUT = {'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/launch.stdout.original.jsonl', 'bytes': 8339, 'sha256': '8a9a32bb54dad115d49fdc814ba10337cba43a04144c621f3a4d0a405b8db211'}
LAUNCH_TERMINAL = {'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/launch.terminal.original.json', 'bytes': 731, 'sha256': '96292fcfeed27a538996f05b924feefc963d4f304759ea8423295e82c2380579'}
SCOPE = {'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/scope.json', 'bytes': 1002, 'sha256': '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'}
LAUNCH_SCOPE_SHA = '54a669eb54fa0dcf6df5afcd17848af7511c2122623192051eb6370e42bfbb06'
RECORDER_ROOT = '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder'
TASK = 878
ROOT = '/home/alex/work/pocket4-beike-r2-fixed-search-click-20261107-r1'
ADAPTER = {'path': '/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1/qa_adapter.py', 'bytes': 31253, 'sha256': '15559f9f1cd59bb1e9540251d4270a4f37a9e229bf86d9ec1e2f9b65d625692f'}
HELPER_MANIFEST = '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489'
BUILD = '/home/alex/work/pocket4-successor-qa-build-362bdb6f45eeb344b3584aa998cb03e1/build-result.json'
BUILD_SHA = '0d6a4e19388358032c9ba4ad4f034e714470d7d194c36599226bd0ba6745330f'
APK_SHA = '968c23aac929130a76dfa49d796fbe5264c073f805b7f048b68737e427d96372'
SIGNER_SHA = 'f5eb5f24311fb19187b37219db272837d2d68632d9e8b855a89b2b6518904143'
HELPER_PACKAGE = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2'
HELPER_UID = 10167
INSTALL_OWNER = {'bytes': 39677, 'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/owned_install_once.py', 'sha256': '0288098834b039fad646331dce2caa2c4bde7166224a1b770866c7c09b5cae41'}
INSTALL_REQUEST = {'bytes': 2066, 'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/request.json', 'sha256': 'b2ed2b01358ff4e15fcc997554042cdf1edf7bfdf6da1d4af73bc58ad70d7324'}
INSTALL_RESULT = {'bytes': 18441, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/install-search-helper-r2-01/result.json', 'sha256': '18b1ab38ab246ab33d07a863701c5c1c4ad80d8ce387990bff2ad018e3bf778e'}
INSTALL_JOB = '1a1b34fadf6-fc05-81f2'
INSTALL_JOINT = {'bytes': 33367, 'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/owned-install-joint.json', 'sha256': '19f172494dcf57397d19c95934dd9e2ff1826d11fa601e7098ac5d87516b703b'}
INSTALL_STDOUT = {'path': '/home/alex/work/pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1/install.stdout.original.json', 'bytes': 33582, 'sha256': '5d7d4e22f8351a3ab58b99bb9236bda69bcf51a1a3a115f079f2834d8d83fbcf'}
INSTALL_TERMINAL = {'path': '/home/alex/work/pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1/install.terminal.original.json', 'bytes': 733, 'sha256': '5350ed913cfb078591d6bf2a13a7fc39b7f74990d9e26009f38bb16a67365bfc'}
CURRENT_SCOPE = {'bytes': 60614, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/install-search-helper-r2-01/app-scope-after.private.json', 'sha256': '7187bc544cf6812ad47efdf141cd111897a1124b9532f84b7cf599b0c0fee1e3'}
CURRENT_GUARD = {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py', 'bytes': 3213, 'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}
RUNTIME_EPOCH = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'
ALL_PACKAGES = ['com.Hyatt.hyt', 'com.MobileTicket', 'com.amazon.mShop.android.shopping', 'com.android.calendar', 'com.android.camera2', 'com.android.contacts', 'com.android.deskclock', 'com.android.dialer', 'com.android.documentsui', 'com.android.gallery3d', 'com.android.messaging', 'com.android.quicksearchbox', 'com.android.settings', 'com.android.threadnetwork.demoapp', 'com.bestbuy.android', 'com.ehi.national.mobile', 'com.enflick.android.TextNow', 'com.example.ndk_tests', 'com.google.android.gms', 'com.hertz.android.digital', 'com.hilton.android.hhonors', 'com.ihg.apps.android', 'com.jingdong.app.mall', 'com.lianjia.beike', 'com.marriott.mrt', 'com.pinger.textfree', 'com.rytong.airchina', 'com.rytong.ceair', 'com.sankuai.meituan.takeoutnew', 'com.sdu.didi.psnger', 'com.ss.android.ugc.aweme', 'com.szzc', 'com.taobao.taobao', 'com.tencent.mm', 'com.ubercab', 'com.united.mobile.android', 'com.xunmeng.pinduoduo', 'com.zhubajie.client', 'com.zillow.android.streeteasy', 'ctrip.android.view', 'jp.co.ana.android.tabidachi', 'local.pocket4.actions.v2', 'local.pocket4.fixture', 'org.chromium.webview_shell', 'org.droidloom.qa.editorcontract', 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1', 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2', 'org.fcitx.fcitx5.android', 'tv.danmaku.bili']
INSTALLED_HELPER = {'apk_sha256': '968c23aac929130a76dfa49d796fbe5264c073f805b7f048b68737e427d96372', 'base_apk': '/data/app/~~JXDsFn3iELFB7Qsu2biSdg==/org.droidloom.qa.successor.p8f89f253350ba2fa.r2-Cena3iBWf04tEYE0_iVnsA==/base.apk', 'bytes': 41104, 'held_file': {'bytes': 41104, 'device': 1811, 'gid': 1000, 'inode': 656461, 'mode': 33188, 'mtime_ns': 1794009719346538707, 'nlink': 1, 'uid': 1000}, 'package': 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2', 'signer_bound_by_exact_signed_apk_bytes': 'f5eb5f24311fb19187b37219db272837d2d68632d9e8b855a89b2b6518904143', 'uid': 10167}
INSTALLED_HELPER_SCOPE_ROW = {'apks': [{'bytes': 41104, 'file': {'st_ctime_ns': 1794009719346538707, 'st_dev': 1811, 'st_gid': 1000, 'st_ino': 656461, 'st_mode': 33188, 'st_mtime_ns': 1794009719346538707, 'st_nlink': 1, 'st_size': 41104, 'st_uid': 1000}, 'path': '/data/app/~~JXDsFn3iELFB7Qsu2biSdg==/org.droidloom.qa.successor.p8f89f253350ba2fa.r2-Cena3iBWf04tEYE0_iVnsA==/base.apk', 'sha256': '968c23aac929130a76dfa49d796fbe5264c073f805b7f048b68737e427d96372'}], 'code_path': '/data/app/~~JXDsFn3iELFB7Qsu2biSdg==/org.droidloom.qa.successor.p8f89f253350ba2fa.r2-Cena3iBWf04tEYE0_iVnsA==', 'data_directories': {'user': {'device': 1811, 'gid': 10167, 'inode': 143016, 'status': 'PRESENT', 'uid': 10167}, 'user_de': {'device': 1811, 'gid': 10167, 'inode': 152887, 'status': 'PRESENT', 'uid': 10167}}, 'fresh_signature_verification': False, 'package': 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2', 'package_manager_certificate_sha256': ['f5eb5f24311fb19187b37219db272837d2d68632d9e8b855a89b2b6518904143'], 'uid': 10167, 'version_code': 1}
FIXED_REQUEST = {'schema': 'pocket4-fixed-r2-search-click-request-v1', 'kind': 'plan', 'step': 'r2-fixed-search-click-01', 'payload_text': '{"nonces":{"action":"c9df0017d7a64731b9e27df9973ac928","after":"8aa4e9f3aa2e4556b22dd0ca7c10f3ed","before":"2dcf1b82a4f34e4b974beb48d4156d19","inspect":"1396fd1e88454afdabba7b73a1bb8a96"},"operation":"search_click","schema":1,"selector":{"class":"android.widget.TextView","resource_id":"com.lianjia.beike:id/tv_nav_right_search_text","text":"\\u641c\\u7d22"}}\n', 'payload_sha256': '31e03eacb0ef1a13b85b42146c061b140e2a99f3d28344aba87bcb6dfdda90e8'}
INSPECT_INPUTS_BOUND = True
INSPECT_OWNER = {'path': '/home/alex/work/pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1/owned_readonly_inspect_once.py', 'bytes': 37462, 'sha256': 'a7734300638acbd93535b2bdf03df8af2bf186e782cba47809bab058e5379ab1'}
INSPECT_REQUEST = {'path': '/home/alex/work/pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1/request.json', 'bytes': 405, 'sha256': 'a800f1eb0bef99f1bb6ad6fd4d22cc349c68bd3a3d9baa3d523d74de82412acc'}
INSPECT_JOB = '1a1b35f9774-fc05-827f'
INSPECT_STDOUT = {'path': '/home/alex/work/pocket4-beike-r2-fixed-search-click-20261107-r1/inspect.stdout.original.json', 'bytes': 24661, 'sha256': '7e4c812377d3562ad9fd236899ba151c2bb11772672c3f04956e02a469d487ed'}
INSPECT_TERMINAL = {'path': '/home/alex/work/pocket4-beike-r2-fixed-search-click-20261107-r1/inspect.terminal.original.json', 'bytes': 733, 'sha256': 'e58b70b49e0a9e61be8d7dcfe72517652cedc8e890f135f618c9558b3c70b6f0'}
INSPECT_RESULT = {'bytes': 6362, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/r2-readonly-inspect-01/result.json', 'sha256': 'e9537722eab7ef9e575597d1c420549388b9540ac348cab472409dc699e8ab1a'}
INSPECT_JOINT = {'bytes': 24390, 'path': '/home/alex/work/pocket4-beike-search-helper-r2-readonly-inspect-20261107-r1/result-a800f1eb0bef99f1bb6ad6fd4d22cc349c68bd3a3d9baa3d523d74de82412acc.json', 'sha256': '58607e7ab4d3463ac50f7d915b4c886ea7286d57cd6ea77a9fd8d392990aed47'}
INSPECT_WIRE_SHA = 'c44cfe0deb683261c272029d938b2ae13d41bf94b09243130a08b3ff70785223'
SELF = REQUEST = None


def need(value, reason):
    if not value:
        raise RuntimeError(reason)



def sha(raw):
    return hashlib.sha256(raw).hexdigest()



def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')



def load_base():
    """Bootstrap only the already deployed exact root-owned utility module."""
    path = Path(BASE['path']); fds = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); fds.append(parent)
        for name in path.parts[1:-1]:
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            fds.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); fds.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             not before.st_mode & 0o022 and before.st_size == BASE['bytes'], 'EXACT_ROOT_UTILITY_FILE')
        raw = bytearray()
        while len(raw) <= before.st_size:
            part = os.read(fd, before.st_size + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        after, named = os.fstat(fd), os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(len(raw) == BASE['bytes'] and sha(raw) == BASE['sha256'] and
             all(getattr(before, key) == getattr(after, key) == getattr(named, key) for key in keys), 'UTILITY_SOURCE_CHANGED')
    finally:
        for fd in reversed(fds):
            os.close(fd)
    module = types.ModuleType('unchanged_cleanup_utilities_only'); module.__file__ = str(path)
    exec(compile(bytes(raw), str(path), 'exec'), module.__dict__)
    return module



def entry(mode):
    global SELF, REQUEST
    need(INSPECT_INPUTS_BOUND is True and FIXED_REQUEST is not None, 'ACTUAL_R2_INSPECT_AND_ACTION_REQUEST_NOT_YET_BOUND')
    need(os.getuid() == os.geteuid() == 0 and len(sys.argv) == 10 and sys.argv[1] == mode and
         sys.argv[2] == '--source-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[3]) and
         sys.argv[4] == '--source-bytes' and sys.argv[5].isdigit() and
         sys.argv[6] == '--request-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[7]) and
         sys.argv[8] == '--request-bytes' and sys.argv[9].isdigit() and 0 < int(sys.argv[9]) <= 65536,
         'EXACT_ROOT_FIXED_SOURCE_AND_PER_STEP_INPUT')
    need(str(Path(__file__).resolve()) == ROOT + '/owned_fixed_search_click_once.py', 'REAL_FIXED_R2_SEARCH_CLICK_ENTRY_LOCATION')
    SELF = {'path': str(Path(__file__).resolve()), 'bytes': int(sys.argv[5]), 'sha256': sys.argv[3]}
    REQUEST = {'path': ROOT + '/request.json', 'bytes': int(sys.argv[9]), 'sha256': sys.argv[7]}
    os.umask(0o077)
    base = load_base(); base.pinned(SELF)
    return base



def outer_request(raw, core):
    value = core.document(raw)
    need(set(value) == {'schema', 'kind', 'step', 'payload_text', 'payload_sha256'} and
         value == FIXED_REQUEST and value['schema'] == 'pocket4-fixed-r2-search-click-request-v1' and value['kind'] == 'plan' and
         type(value['step']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value['step']) and
         type(value['payload_text']) is str and re.fullmatch('[0-9a-f]{64}', value['payload_sha256']),
         'CLOSED_FIXED_UI_REQUEST_NO_COMMAND_OR_PATH_PARAMETERS')
    body = value['payload_text'].encode('utf-8')
    need(0 < len(body) <= 16384 and sha(body) == value['payload_sha256'],
         'EXACT_BOUNDED_DECLARED_PLAN_OR_CASE_BYTES')
    payload = core.document(body)
    return value, body, payload



def declared_request(raw, core, adapter, qa):
    request, body, payload = outer_request(raw, core)
    adapter.validate_plan(payload, qa)
    need(payload['operation'] == 'search_click' and payload['selector'] == qa.SEARCH_SELECTOR,
         'ONLY_THE_COMPILED_FIXED_BEIKE_SEARCH_CLICK')
    return request, body, payload, True


def write_once(base, path, raw):
    path = Path(path)
    need(path.parent.as_posix() in (ROOT, FLOW) and path.name not in ('', '.', '..'), 'FIXED_OWNED_OUTPUT_DIRECTORY')
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(directory)
        need(before.st_uid == 0 and stat.S_IMODE(before.st_mode) == 0o700 and path.parent.resolve() == path.parent,
             'ROOT_PRIVATE_FIXED_OUTPUT_PARENT')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=directory)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); need(count > 0, 'WRITE_PROGRESS'); view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        named = os.stat(path.parent, follow_symlinks=False)
        need(all(getattr(before, key) == getattr(named, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')),
             'OUTPUT_PARENT_REPLACED')
    finally:
        os.close(directory)
    need(base.read(path)[0] == raw, 'EXACT_IMMUTABLE_OUTPUT_READBACK')
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}



def launch_gate(base, core):
    stdout = base.pinned(LAUNCH_STDOUT); terminal = core.document(base.pinned(LAUNCH_TERMINAL))
    need(terminal.get('job_id') == '1a1b240f7fd-fc05-7d2d' and terminal.get('state') == 'succeeded' and
         terminal.get('exit_code') == 0 and all(terminal.get(k) is True for k in
             ('output_complete', 'output_durable', 'terminal_publication_confirmed', 'audit_recorded')) and
         all(terminal.get(k) is False for k in ('timed_out', 'cancelled', 'automatic_retry')) and
         terminal.get('log_bytes') == {'stdout': {'seen': 8339, 'stored': 8339}, 'stderr': {'seen': 0, 'stored': 0}} and
         terminal.get('log_errors') == {'stdout': None, 'stderr': None} and
         terminal.get('log_synced') == {'stdout': True, 'stderr': True} and
         terminal.get('log_truncated') == {'stdout': False, 'stderr': False}, 'ACTUAL_NATIVE_LAUNCH_DURABLE_ZERO')
    value = core.document(stdout)
    need(value.get('schema') == 'pocket4-original-new-session-owned-result-v1' and value.get('operation') == 'launch' and
         value.get('ok') is True and value.get('errors') == [] and value.get('outcome_unknown') is False and
         value.get('flow') == FLOW and value.get('source') == SESSION and value.get('joint_artifact') == LAUNCH and
         value.get('new_scope') == SCOPE and value.get('old_close_outcome') == 'unknown_retained' and
         value.get('old_unknown_rewritten') is False and value.get('reconciliation_published') is False,
         'ACTUAL_FIXED_NEW_FLOW_LAUNCH_RESULT')
    base.require_owned_exit(value['child_lifecycle'], b'')
    artifact = dict(value); del artifact['joint_artifact']
    need(base.pinned(LAUNCH) == canonical(artifact) + b'\n', 'REAL_LAUNCH_JOINT_ARTIFACT_MATCHES_ACTUAL_STDOUT')
    scope = core.document(base.pinned(SCOPE)); core.fixed_scope(scope)
    selected_raw, _ = base.read(Path(FLOW) / 'launch-scope.json')
    need(sha(selected_raw) == LAUNCH_SCOPE_SHA, 'UNCHANGED_ACTUAL_NATIVE_LAUNCH_SCOPE')
    selected = core.document(selected_raw)
    need(selected.get('task') == TASK and selected.get('package') == core.PACKAGE and selected.get('epoch_sha256') == core.MAIN_EPOCH and
         selected.get('prelaunch_absent') is True and selected.get('cleanup_allowed') is True and
         selected.get('launch_step') == 'native-launch-01' and selected.get('prelaunch_task_ids') == [875, 877] and
         selected.get('native_receipt_sha256') == value['launch']['native_identity']['receipt_sha256'] and
         value['launch'].get('task') == TASK and value['launch'].get('launch_scope_sha256') == LAUNCH_SCOPE_SHA,
         'EXACT_FRESH_NATIVE_OWNERSHIP_NO_TASK_TRANSFER')
    return scope, selected



def original_argv(request, body_path):
    return [ADAPTER['path'], '--execute-once', '--interactive-production',
        '--source-manifest-sha256', HELPER_MANIFEST, '--build-receipt', BUILD,
        '--build-receipt-sha256', BUILD_SHA, '--apk-sha256', APK_SHA,
        '--signer-certificate-sha256', SIGNER_SHA,
        '--plan', str(body_path), '--plan-sha256', request['payload_sha256'],
        '--step', request['step'], '--recorder-root', RECORDER_ROOT,
        '--flow-dir', FLOW, '--helper-uid', str(HELPER_UID)]



def verify_original(base, core, request, payload, mutation, raw, scope, selected):
    need(mutation is True and request['kind'] == 'plan' and payload['operation'] == 'search_click', 'FIXED_SEARCH_CLICK_PLAN_ONLY')
    need(raw.endswith(b'\n') and len(raw.splitlines()) == 1, 'ONE_ORIGINAL_ADAPTER_OR_CASE_RESULT')
    result = core.document(raw); folder = Path(FLOW) / 'steps' / request['step']
    saved_raw, _ = base.read(folder / 'result.json')
    need(core.document(saved_raw) == result, 'ORIGINAL_RESULT_FILE_EQUALS_ORIGINAL_STDOUT')
    need(result.get('ok') is True and result.get('automatic_retry') is False and
         result.get('action_attempted') is mutation and result.get('outcome_unknown') is mutation and
         result.get('business_success_verified') is False and result.get('epoch_sha256') == core.MAIN_EPOCH,
         'ORIGINAL_SUCCESS_AND_MUTATION_UNKNOWN_RETAINED')
    intent = core.document(base.read(folder / 'intent.json')[0])
    need(intent.get('scope') == scope and intent.get('mutation') is mutation and
         intent.get('operation') == ('owned-qa' if request['kind'] == 'plan' else 'owned-qa-case') and
         all(intent.get(k) is None for k in ('unknown_step', 'observation_step', 'postcondition')),
         'ORIGINAL_FLOW_BEGIN_AND_FIXED_NEW_SCOPE')
    if request['kind'] == 'plan':
        need(intent['request'].get('plan') == payload and intent['request'].get('plan_sha256') == request['payload_sha256'] and
             result.get('plan_sha256') == request['payload_sha256'] and result.get('source_manifest_sha256') == HELPER_MANIFEST and
             result.get('owned_task') == selected and result.get('error') is None and result.get('secondary_errors') == [] and
             result.get('after_state_completed') is True and result.get('restoration_qualified') is True and
             result.get('post_state_matches_before') is True and
             result.get('next_business_mutation_requires_explicit_postcondition_reconciliation') is mutation and
             result.get('installed_before') == result.get('installed_after') and
             result['installed_before'].get('uid') == HELPER_UID and result['installed_before'].get('apk_sha256') == APK_SHA,
             'FULL_ORIGINAL_OWNED_PLAN_RESTORATION_AND_HELPER_IDENTITY')
    need(result['installed_before'] == INSTALLED_HELPER, 'ACTUAL_NORMAL_INSTALL_IDENTITY_UNCHANGED')
    need(result.get('search_click_acknowledged') is True and result.get('atomic_android_transaction') is False and
         type(result.get('search_selection_sha256')) is str and re.fullmatch('[0-9a-f]{64}', result['search_selection_sha256']),
         'EXACT_ORIGINAL_FIXED_SEARCH_ACK_AND_FULL_TREE_SELECTION')
    return result, {'path': str(folder / 'result.json'), 'bytes': len(saved_raw), 'sha256': sha(saved_raw)}



def completed_install_header(base, partial, raw, terminal):
    partial.original_terminal(terminal, INSTALL_JOB, len(raw))
    outer = partial.document(raw)
    need(outer.get('schema') == 'pocket4-owned-search-helper-coexist-result-v1' and
         outer.get('ok') is True and outer.get('errors') == [] and outer.get('source') == INSTALL_OWNER and
         outer.get('request') == INSTALL_REQUEST and outer.get('flow') == FLOW and outer.get('package') == HELPER_PACKAGE and
         outer.get('helper_uid') == HELPER_UID and outer.get('next_app_scope') == CURRENT_SCOPE and
         outer.get('original_result') == INSTALL_RESULT and outer.get('joint_artifact') == INSTALL_JOINT and
         outer.get('step') == 'install-search-helper-r2-01' and
         outer.get('observed_explicit_packages') == 49 and outer.get('observed_APKs') == 89 and
         all(outer.get(k) is True for k in ('all_original48_unchanged', 'normal_PM_install_success_observed',
             'state_without_UiAutomation_verified', 'original_action_attempted',
             'all_owned_child_resources_retired_by_normal_pidfd_exit', 'parent_whole_process_FD_identity_restored',
             'current_scope_adoption_requires_this_actual_durable_terminal',
             'later_QA_permissions_and_framework_must_rebind_actual_new_scope')) and
         all(outer.get(k) is False for k in ('original_action_outcome_unknown', 'outcome_unknown',
             'original_FAILED_UNKNOWN_rewritten', 'reconciliation_published', 'old_helper_uninstalled',
             'old_products_deleted', 'production_ready', 'automatic_retry', 'full_PM_or_launcher_inventory_claimed')) and
         all(type(outer.get(k)) is int and outer[k] == 0 for k in ('UI_actions', 'permission_grants', 'target_App_launches')),
         'ACTUAL_COMPLETED_NORMAL_R2_INSTALL_AND_ALL49_SCOPE')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(outer.get('child_stdout_bytes') == len(child_raw) and outer.get('child_stdout_sha256') == sha(child_raw) and
         outer.get('child_stderr_bytes') == len(stderr) == 0 and outer.get('child_stderr_sha256') == sha(stderr),
         'EXACT_INSTALL_CHILD_STREAMS')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    child = partial.document(child_raw)
    need(child.get('schema') == 'pocket4-owned-search-helper-coexist-child-v1' and child.get('ok') is True and
         child.get('errors') == [] and child.get('source') == INSTALL_OWNER and child.get('request') == INSTALL_REQUEST and
         child.get('flow') == FLOW and child.get('step') == outer['step'] and
         child.get('original_entry_invoked') is True and child.get('original_returncode') == 0 and
         child.get('original_action_attempted') is True and child.get('original_action_outcome_unknown') is False and
         child.get('outcome_unknown') is False and child.get('original_namespace_authority_released') is True and
         child.get('normal_process_exit_required_for_lock_and_library') is True and
         child.get('unknown_descriptors_closed') == 0 and child.get('manual_library_close') is False and
         child.get('original_private_UI_nodes_exported') is False and
         child.get('original_result') == outer['original_result'] and child.get('helper_uid') == HELPER_UID and
         child.get('next_app_scope') == CURRENT_SCOPE and child.get('completed_build') == outer['completed_build'] and
         child.get('completed_no_action_B') == outer['completed_no_action_B'],
         'SAME_COMPLETED_INSTALL_CHILD_PARENT_AND_NORMAL_EXIT')
    original_raw = child['original_stdout'].encode('utf-8')
    need(len(original_raw) == child['original_stdout_bytes'] and sha(original_raw) == child['original_stdout_sha256'],
         'COMPLETE_ORIGINAL_INSTALLER_STREAM')
    return outer, child, original_raw



def completed_install_gate(base, core):
    """Read only actual install/build/B evidence, never invoke those owners."""
    owner = base.load(INSTALL_OWNER, 'completed_install_readonly_definitions')
    partial = base.load(owner.NO_ACTION_CORE, 'unchanged_completed_terminal_predicate')
    outer, child, original_raw = completed_install_header(base, partial, base.pinned(INSTALL_STDOUT),
        partial.document(base.pinned(INSTALL_TERMINAL)))
    joint = dict(outer); joint.pop('joint_artifact')
    need(base.pinned(INSTALL_JOINT) == canonical(joint) + b'\n', 'ACTUAL_PUBLISHED_INSTALL_JOINT_EQUALS_ORIGINAL_STDOUT')
    request = owner.request_value(base.pinned(INSTALL_REQUEST), core)
    build = owner.completed_build_gate(base)
    no_action = owner.completed_b_gate(base)
    need(build == outer['completed_build'] and no_action == outer['completed_no_action_B'],
         'COMPLETED_BUILD_AND_NO_ACTION_B_UNCHANGED')
    original, result_pin = owner.verify_install(base, core, request, build['qualified_build'], original_raw)
    need(result_pin == INSTALL_RESULT and original['helper_uid'] == HELPER_UID and
         original['next_app_scope'] == CURRENT_SCOPE and original['installed_after_state'] == INSTALLED_HELPER and
         child['whole_scope_transition'] == original['whole_scope_after']['transition'],
         'ACTUAL_INSTALLED_R2_UID_APK_CERT_CEDE_AND_ORIGINAL_SCOPE_VALIDATOR')
    return {'job_id': INSTALL_JOB, 'source': INSTALL_OWNER, 'request': INSTALL_REQUEST,
            'stdout': INSTALL_STDOUT, 'terminal': INSTALL_TERMINAL, 'joint': INSTALL_JOINT,
            'original_result': INSTALL_RESULT, 'helper_uid': HELPER_UID, 'installed_helper': INSTALLED_HELPER,
            'actual_scope49': CURRENT_SCOPE, 'normal_PM_and_no_automation_state_verified': True,
            'actual_build_and_completed_B_rechecked_readonly': True,
            'install_or_B_execution_entries_called': False, 'production_ready': False}



def validate_scope49(value):
    need(type(value) is dict and value.get('schema') == 'pocket4-versioned-app-scope-v1' and
         value.get('kind') == 'explicit-current-app-observation' and
         value.get('runtime_epoch_sha256') == RUNTIME_EPOCH and type(value.get('apps')) is dict and
         sorted(value['apps']) == ALL_PACKAGES and len(value['apps']) == 49 and
         sum(len(row['apks']) for row in value['apps'].values()) == 89 and
         value['apps'][HELPER_PACKAGE] == INSTALLED_HELPER_SCOPE_ROW and
         value.get('fresh_signature_verification_performed') is False and
         value.get('UI_or_install_runtime_admitted') is False and
         value.get('external_evidence_policy_validated_by_this_reader') is False,
         'EXACT_ACTUAL_EXPLICIT49_NOT_SUBSET_OR_SELF_PROMOTED')
    return value



def whole_scope_guard(base, core, *, action_attempted=False):
    validate_scope49(core.document(base.pinned(CURRENT_SCOPE)))
    guard = base.load(CURRENT_GUARD, 'unchanged_typed_current_Main_guard')
    typed = guard.current_guard(action_attempted=action_attempted)
    need(typed.get('schema') == 'pocket4-successor-main-guard-v1' and
         typed.get('runtime_epoch_sha256') == RUNTIME_EPOCH, 'SAME_ACTUAL_CURRENT_TYPED_RUNTIME')
    current = guard.check_app_scope(CURRENT_SCOPE, ALL_PACKAGES)
    need(current.get('schema') == 'pocket4-app-scope-guard-v1' and
         current.get('runtime_epoch_sha256') == RUNTIME_EPOCH and current.get('packages') == ALL_PACKAGES and
         current.get('app_scope_sha256') == CURRENT_SCOPE['sha256'] and
         current.get('current_apk_paths_and_file_identities_match') is True and
         current.get('new_signature_verification_performed') is False and
         current.get('UI_or_install_runtime_admitted') is False, 'ALL49_FRESH_FILE_AND_UID_IDENTITIES')
    return {'typed_runtime': typed, 'current_apps': current, 'scope_pin': CURRENT_SCOPE,
            'complete_PM_or_launcher_enumeration_claimed': False}



def completed_inspect_header(base, partial, raw, terminal):
    need(INSPECT_INPUTS_BOUND is True, 'ACTUAL_COMPLETED_R2_INSPECT_NOT_YET_BOUND')
    partial.original_terminal(terminal, INSPECT_JOB, len(raw))
    outer = partial.document(raw)
    need(outer.get('schema') == 'pocket4-fixed-r2-readonly-inspect-result-v1' and
         outer.get('ok') is True and outer.get('errors') == [] and
         outer.get('source') == INSPECT_OWNER and outer.get('request') == INSPECT_REQUEST and
         outer.get('flow') == FLOW and outer.get('task') == TASK and outer.get('kind') == 'plan' and
         outer.get('step') == 'r2-readonly-inspect-01' and outer.get('helper_uid') == HELPER_UID and
         outer.get('current_explicit_scope') == CURRENT_SCOPE and outer.get('original_result') == INSPECT_RESULT and
         outer.get('joint_artifact') == INSPECT_JOINT and
         all(outer.get(k) is True for k in ('all49_guard_before_after_equal',
             'all_owned_child_resources_retired_by_normal_pidfd_exit',
             'acceptance_requires_original_stdout_and_authoritative_durable_terminal')) and
         all(outer.get(k) is False for k in ('original_action_attempted', 'original_action_outcome_unknown',
             'outcome_unknown', 'original_UNKNOWN_rewritten', 'reconciliation_published', 'production_ready',
             'automatic_retry', 'full_PM_or_launcher_inventory_claimed',
             'allows_new_mutation_without_original_Flow_checks')),
         'EXACT_ACTUAL_READONLY_INSPECT_COMPLETE_AND_DURABLE')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(outer['child_stdout_bytes'] == len(child_raw) and outer['child_stdout_sha256'] == sha(child_raw) and
         outer['child_stderr_bytes'] == len(stderr) == 0 and outer['child_stderr_sha256'] == sha(stderr),
         'ACTUAL_PRIOR_INSPECT_CHILD_STREAMS')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    child = partial.document(child_raw)
    need(child.get('schema') == 'pocket4-fixed-r2-readonly-inspect-child-v1' and child.get('ok') is True and
         child.get('errors') == [] and child.get('source') == INSPECT_OWNER and child.get('request') == INSPECT_REQUEST and
         child.get('flow') == FLOW and child.get('task') == TASK and child.get('kind') == 'plan' and
         child.get('step') == outer['step'] and child.get('helper_uid') == HELPER_UID and
         child.get('current_explicit_scope') == CURRENT_SCOPE and child.get('original_result') == INSPECT_RESULT and
         child.get('original_entry_invoked') is True and child.get('original_returncode') == 0 and
         child.get('declared_mutation') is False and child.get('original_action_attempted') is False and
         child.get('original_action_outcome_unknown') is False and child.get('outcome_unknown') is False and
         child.get('whole_scope_before') == child.get('whole_scope_after') and
         child.get('completed_install') == outer.get('completed_install') and
         child.get('original_namespace_authority_released') is True and
         child.get('normal_process_exit_required_for_lock_and_library') is True and
         child.get('unknown_descriptors_closed') == 0 and child.get('manual_library_close') is False and
         child.get('original_private_UI_nodes_exported') is False,
         'ACTUAL_PRIOR_READONLY_CHILD_AND_NORMAL_RETIREMENT')
    original_raw = child['original_stdout'].encode('utf-8')
    need(child['original_stdout_bytes'] == len(original_raw) and child['original_stdout_sha256'] == sha(original_raw),
         'ACTUAL_PRIOR_ORIGINAL_ADAPTER_BYTES')
    return outer, child, original_raw


def prior_inspect_gate(base, core):
    """Read completed observer evidence; do not reuse its nodes for dispatch."""
    need(INSPECT_INPUTS_BOUND is True, 'ACTUAL_COMPLETED_R2_INSPECT_NOT_YET_BOUND')
    previous = base.load(INSPECT_OWNER, 'completed_readonly_inspect_definitions_only')
    install_owner = base.load(INSTALL_OWNER, 'completed_install_terminal_parser_reference_only')
    partial = base.load(install_owner.NO_ACTION_CORE, 'unchanged_original_terminal_parser_only')
    outer, child, original_raw = completed_inspect_header(base, partial, base.pinned(INSPECT_STDOUT),
        partial.document(base.pinned(INSPECT_TERMINAL)))
    joint = dict(outer); joint.pop('joint_artifact')
    need(base.pinned(INSPECT_JOINT) == canonical(joint) + b'\n',
         'ACTUAL_PRIOR_INSPECT_PUBLISHED_JOINT_EQUALS_FULL_STDOUT')
    request, body, payload = previous.outer_request(base.pinned(INSPECT_REQUEST), core)
    scope, selected = previous.launch_gate(base, core)
    original, original_pin = previous.verify_original(base, core, request, payload, False, original_raw, scope, selected)
    need(original_pin == INSPECT_RESULT and original['inspection_wire_sha256'] == INSPECT_WIRE_SHA and
         original['installed_before'] == INSTALLED_HELPER and original['installed_after'] == INSTALLED_HELPER,
         'ACTUAL_COMPLETED_R2_INSPECT_AND_SAME_INSTALLED_HELPER')
    return {'job_id': INSPECT_JOB, 'source': INSPECT_OWNER, 'request': INSPECT_REQUEST,
            'stdout': INSPECT_STDOUT, 'terminal': INSPECT_TERMINAL, 'joint': INSPECT_JOINT,
            'original_result': INSPECT_RESULT, 'inspection_wire_sha256': INSPECT_WIRE_SHA,
            'actual_helper_uid': HELPER_UID, 'actual_scope49': CURRENT_SCOPE,
            'previous_nodes_reused_for_action': False, 'search_page_navigation_proved': False,
            'current_button_presence_prejudged': False,
            'dispatch_still_requires_new_original_inspection_and_fixed_full_tree_transaction': True,
            'prior_observer_execution_entry_called': False}



def child():
    base = entry('--child')
    need(sys.stdin.buffer.read(1) == b'R', 'PARENT_HELD_PIDFD_RELEASE_REQUIRED')
    result = {'schema': 'pocket4-fixed-r2-search-click-child-v1', 'ok': False, 'errors': [], 'source': SELF, 'request': REQUEST,
        'flow': FLOW, 'task': TASK, 'original_entry_invoked': False, 'original_sources_modified': False,
        'original_UNKNOWN_rewritten': False, 'reconciliation_published': False, 'permission_changes': 0,
        'installs': 0, 'native_launches': 0, 'cleanup_or_focus_actions': 0, 'production_ready': False,
        'automatic_retry': False, 'allows_new_mutation_without_original_Flow_checks': False}
    try:
        session = base.load(SESSION, 'unchanged_session_support_only')
        support = base.load(base.SUPPORT, 'unchanged_library_bootstrap')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_owned_child_probe')
        observed = support.probe_proof(); _, frozen, library_fd, library = support.initialize_library(probe, observed)
        core = base.load(base.CORE, 'unchanged_pure_evidence_core')
        bodies, identities, old_scope = session.predecessor(base, core)
        scope, selected = launch_gate(base, core)
        _, same_scope = session.new_scope(base, core, old_scope); need(same_scope == SCOPE, 'UNCHANGED_NEW_SCOPE')
        result['prior_readonly_inspect'] = prior_inspect_gate(base, core)
        result['completed_install'] = completed_install_gate(base, core)
        result['whole_scope_before'] = whole_scope_guard(base, core)
        adapter = base.load(ADAPTER, 'unchanged_actual_r2_owned_adapter')
        manifest = adapter.own_source(HELPER_MANIFEST)
        qa = adapter.load(Path(ADAPTER['path']).with_name('qa_contract.py'), manifest['files']['qa_contract.py']['sha256'], 'unchanged_actual_qa_contract')
        request, body, payload, mutation = declared_request(base.pinned(REQUEST), core, adapter, qa)
        result.update(kind=request['kind'], step=request['step'], declared_mutation=mutation)
        need(not os.path.lexists(Path(FLOW) / 'steps' / request['step']), 'ORIGINAL_STEP_MUST_BE_FRESH_NO_REPLAY')
        body_path = Path(FLOW) / ('qa-' + request['step'] + '.' + request['kind'] + '.json')
        result['input_artifact'] = write_once(base, body_path, body)
        _, lock_metadata = base.read(Path(FLOW) / 'flow.lock', 65536)
        need(stat.S_IMODE(lock_metadata['st_mode']) == 0o600, 'EXACT_EXISTING_NEW_FLOW_LOCK')
        need(probe.same_descriptors(frozen, probe.census()), 'NO_PRE_ENTRY_UNKNOWN_DESCRIPTOR')
        argv = original_argv(request, body_path)
        saved, output, returned = sys.argv, io.StringIO(), None
        result['original_entry_invoked'] = True
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(output):
                try:
                    returned = adapter.main()
                except SystemExit as error:
                    returned = error.code
        finally:
            sys.argv = saved
            raw = output.getvalue().encode('utf-8')
            result.update(original_returncode=returned, original_stdout=raw.decode('utf-8'), original_stdout_bytes=len(raw),
                          original_stdout_sha256=sha(raw), original_argv=argv)
        need(type(returned) is int and returned == 0, 'ORIGINAL_ENTRY_FAILED_NO_RETRY')
        original, result_pin = verify_original(base, core, request, payload, mutation, raw, scope, selected)
        result['whole_scope_after'] = whole_scope_guard(base, core, action_attempted=original['action_attempted'])
        need(result['whole_scope_after'] == result['whole_scope_before'], 'ALL49_AND_TYPED_RUNTIME_CHANGED_DURING_INSPECT')
        need(completed_install_gate(base, core) == result['completed_install'], 'ACTUAL_INSTALL_BUILD_B_AND_OLD_FAILURES_CHANGED')
        need(prior_inspect_gate(base, core) == result['prior_readonly_inspect'], 'ACTUAL_PRIOR_INSPECT_EVIDENCE_CHANGED')
        base.preserved(bodies, identities)
        launch_gate(base, core)
        for pin in (SELF, REQUEST, BASE, SESSION, ADAPTER, LAUNCH_STDOUT, LAUNCH_TERMINAL, INSTALL_OWNER, INSTALL_REQUEST, INSTALL_STDOUT, INSTALL_TERMINAL, INSPECT_OWNER, INSPECT_REQUEST, INSPECT_STDOUT, INSPECT_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.RECORDER, base.CORE, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        final = probe.census(); extra = set(final) - set(frozen)
        need(len(extra) == 1 and probe.same_descriptors(frozen, {k: v for k, v in final.items() if k in frozen}), 'ONLY_DECLARED_ORIGINAL_FLOW_LOCK_MAY_REMAIN')
        held = final[next(iter(extra))]
        need(held['link'] == FLOW + '/flow.lock' and held['fstat'] == lock_metadata and held['descriptor_flags'] == 1 and
             held['status_flags'] & os.O_ACCMODE == os.O_RDWR and
             support.stable_library(probe.library_binding(library_fd, final[str(library_fd)])) == support.stable_library(library),
             'ORIGINAL_FLOW_LOCK_AND_EXPLICIT_LIBRARY_UNCHANGED')
        result.update(ok=True, helper_uid=HELPER_UID, current_explicit_scope=CURRENT_SCOPE, original_result=result_pin,
            search_click_acknowledged=original['search_click_acknowledged'], search_selection_sha256=original['search_selection_sha256'],
            atomic_android_transaction=False, search_page_navigation_verified=False, independent_after_inspect_required=True, original_action_attempted=original['action_attempted'],
            original_action_outcome_unknown=original['outcome_unknown'], original_old_close_outcome='unknown_retained',
            original_namespace_authority_released=True, normal_process_exit_required_for_lock_and_library=True,
            final_descriptors=final, unknown_descriptors_closed=0, manual_library_close=False,
            original_private_UI_nodes_exported=False)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    result['outcome_unknown'] = bool(result.get('original_action_outcome_unknown', result['original_entry_invoked'] and not result['ok']))
    raw = canonical(result); need(len(raw) <= 131072, 'CHILD_OUTPUT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1



def parent():
    base = entry('--execute-request')
    result = {'schema': 'pocket4-fixed-r2-search-click-result-v1', 'ok': False, 'errors': [], 'source': SELF,
        'request': REQUEST, 'flow': FLOW, 'task': TASK, 'original_UNKNOWN_rewritten': False, 'reconciliation_published': False,
        'production_ready': False, 'automatic_retry': False, 'permission_changes': 0, 'installs': 0,
        'native_launches': 0, 'cleanup_or_focus_actions': 0, 'old_products_deleted': False,
        'acceptance_requires_original_stdout_and_authoritative_durable_terminal': True}
    invoked = False
    try:
        support = base.load(base.SUPPORT, 'unchanged_owned_library_functions')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_pidfd_lifetime_functions')
        observed = support.probe_proof(); support.pin_runtime_files(probe, observed)
        before = probe.census(); need(set(before) == {'0', '1', '2'}, 'PARENT_INITIAL_STDIO_ONLY')
        core = base.load(base.CORE, 'unchanged_request_json_parser')
        request, _, _ = outer_request(base.pinned(REQUEST), core)
        marker = Path(ROOT) / ('attempt-' + REQUEST['sha256'] + '.json')
        write_once(base, marker, canonical({'source': SELF, 'request': REQUEST, 'step': request['step'],
                   'automatic_retry': False, 'child_not_yet_started': True}) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_DESCRIPTORS_BEFORE_CHILD')
        argv = [sys.executable, '-I', '-B', SELF['path'], '--child', '--source-sha256', SELF['sha256'], '--source-bytes', str(SELF['bytes']),
                '--request-sha256', REQUEST['sha256'], '--request-bytes', str(REQUEST['bytes'])]
        invoked = True
        life, raw, stderr = probe.run_owned_child(argv, seconds=360)
        result.update(child_lifecycle=life, child_stdout_original=raw.decode('utf-8', 'strict'), child_stdout_bytes=len(raw),
            child_stdout_sha256=sha(raw), child_stderr_original=stderr.decode('utf-8', 'replace'),
            child_stderr_bytes=len(stderr), child_stderr_sha256=sha(stderr))
        value = core.document(raw); base.require_owned_exit(life, stderr)
        need(value.get('schema') == 'pocket4-fixed-r2-search-click-child-v1' and value.get('ok') is True and value.get('errors') == [] and
             value.get('source') == SELF and value.get('request') == REQUEST and value.get('flow') == FLOW and value.get('task') == TASK and
             value.get('step') == request['step'] and value.get('kind') == request['kind'] and
             value.get('original_action_attempted') is True and value.get('original_action_outcome_unknown') is True and
             value.get('declared_mutation') is True and value.get('search_click_acknowledged') is True and
             value.get('atomic_android_transaction') is False and value.get('search_page_navigation_verified') is False and
             value.get('independent_after_inspect_required') is True and
             value.get('prior_readonly_inspect', {}).get('job_id') == INSPECT_JOB and
             value.get('helper_uid') == HELPER_UID and value.get('current_explicit_scope') == CURRENT_SCOPE and
             value.get('whole_scope_before') == value.get('whole_scope_after') and
             value.get('completed_install', {}).get('job_id') == INSTALL_JOB,
             'ORIGINAL_QA_SUCCESS_AND_NORMAL_CHILD_EXIT_JOINTLY_REQUIRED')
        for pin in (SELF, REQUEST, BASE, SESSION, ADAPTER, LAUNCH_STDOUT, LAUNCH_TERMINAL, INSTALL_OWNER, INSTALL_REQUEST, INSTALL_STDOUT, INSTALL_TERMINAL, INSPECT_OWNER, INSPECT_REQUEST, INSPECT_STDOUT, INSPECT_TERMINAL, CURRENT_SCOPE, CURRENT_GUARD, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_RESTORED')
        result.update(ok=True, step=request['step'], kind=request['kind'], original_result=value['original_result'],
            helper_uid=HELPER_UID, current_explicit_scope=CURRENT_SCOPE, completed_install=value['completed_install'],
            all49_guard_before_after_equal=True, full_PM_or_launcher_inventory_claimed=False,
            prior_readonly_inspect=value['prior_readonly_inspect'], search_click_acknowledged=True,
            search_selection_sha256=value['search_selection_sha256'], atomic_android_transaction=False,
            search_page_navigation_verified=False, independent_after_inspect_required=True,
            original_action_attempted=value['original_action_attempted'], original_action_outcome_unknown=value['original_action_outcome_unknown'],
            outcome_unknown=value['original_action_outcome_unknown'], all_owned_child_resources_retired_by_normal_pidfd_exit=True,
            allows_new_mutation_without_original_Flow_checks=False, original_old_close_outcome='unknown_retained')
        artifact = write_once(base, Path(ROOT) / ('result-' + REQUEST['sha256'] + '.json'), canonical(result) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_AFTER_ARTIFACT')
        result['joint_artifact'] = artifact
    except BaseException as error:
        result['ok'] = False
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    if not result['ok']:
        result['outcome_unknown'] = invoked
    raw = canonical(result); need(len(raw) <= 262144, 'PARENT_OUTPUT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1



if __name__ == '__main__':
    mode = sys.argv[1:2]
    if mode == ['--child']:
        raise SystemExit(child())
    need(mode == ['--execute-request'], 'CLOSED_ONE_FIXED_SEARCH_CLICK_ENTRY')
    raise SystemExit(parent())
