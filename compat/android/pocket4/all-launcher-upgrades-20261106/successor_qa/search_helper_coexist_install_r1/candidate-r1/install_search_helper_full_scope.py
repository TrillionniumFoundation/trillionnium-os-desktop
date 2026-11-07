"""One fresh owned-helper install and no-UiAutomation state check on R5.

PLAN_ONLY unless --install-once is explicit. The target App is not installed,
started, clicked, granted permissions, or instrumented. No automatic retry,
replacement, uninstall or residual deletion is implemented.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

HERE = Path('/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1')
SELF = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2'
RECORDER_MANIFEST_SHA = '646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=1048576):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_nlink == 1 and 0 <= a.st_size <= maximum, 'BOUNDED_SINGLE_INPUT')
        raw = bytearray()
        while len(raw) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        def meta(s):
            return tuple(getattr(s, k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
        need(len(raw) == a.st_size and meta(a) == meta(os.fstat(fd)) == meta(os.stat(path, follow_symlinks=False)), 'HELD_INPUT_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def load(path, pin, name):
    raw = read(path)
    need(sha(raw) == pin, 'MODULE_SOURCE_PIN')
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def command(flow, argv, timeout=8, mutation=False):
    before = flow.command_index
    raw = flow.android(argv, timeout, mutation=mutation)
    need(flow.command_index == before + 1, 'ONE_HELD_COMMAND_REQUIRED')
    stem = flow.step / ('command-%03d' % flow.command_index)
    receipt = json.loads(read(str(stem) + '.result.json', 65536))
    stderr = read(str(stem) + '.stderr')
    need(receipt['returncode'] == 0 and receipt['spawned'] is True and
         receipt['owned_command_joined'] is True and receipt['timed_out'] is False and
         receipt['errors'] == [] and receipt['stdout_sha256'] == sha(raw) and
         receipt['stderr_sha256'] == sha(stderr) and stderr == b'', 'JOINED_QUIET_HELD_COMMAND_REQUIRED')
    return raw


class Stage:
    def __init__(self, target, nonce):
        self.target = target
        self.fds = []
        self.name = 'pocket4-successor-owned-qa-' + nonce
        self.path = '/data/local/tmp/' + self.name + '/owned-qa.apk'

    def stage(self, data, expected):
        need(sha(data) == expected and 0 < len(data) <= 2097152, 'ACTUAL_NEW_HELPER_APK')
        self.parent = self.target.open_root('/data/local/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fds.append(self.parent)
        os.mkdir(self.name, 0o711, dir_fd=self.parent)
        self.directory = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.parent)
        self.fds.append(self.directory)
        os.fchmod(self.directory, 0o711)
        self.file = os.open('owned-qa.apk', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=self.directory)
        self.fds.append(self.file)
        rest = memoryview(data)
        while rest:
            n = os.write(self.file, rest)
            need(n > 0, 'OWNED_APK_WRITE_PROGRESS')
            rest = rest[n:]
        os.fchmod(self.file, 0o444)
        os.fsync(self.file)
        os.fsync(self.directory)
        os.fsync(self.parent)
        actual, metadata = self.target.read_file(self.path, len(data), single_link=True)
        held = os.fstat(self.file)
        need(sha(actual) == expected and held.st_uid == 0 and held.st_nlink == 1 and
             (metadata['device'],metadata['inode'],metadata['bytes']) == (held.st_dev,held.st_ino,len(data)), 'OWNED_GUEST_APK_IDENTITY')
        self.record = {'path':self.path,'bytes':len(data),'sha256':expected,'device':held.st_dev,'inode':held.st_ino,
                       'retained_until_reviewed_production_cleanup':True}

    def close(self):
        errors = []
        for fd in reversed(self.fds):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        self.fds = []
        need(not errors, 'OWNED_STAGE_FD_CLOSE_FAILED')


# This extension is outside the frozen helper build closure. It only adds
# whole-scope pre/post proof to the original normal PM install transaction.
PARENT_SCOPE = {'path': '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-full48-r4-01/app-scope-after.private.json', 'bytes': 59259, 'sha256': '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'}
ORIGINAL_PACKAGES = ['com.Hyatt.hyt', 'com.MobileTicket', 'com.amazon.mShop.android.shopping', 'com.android.calendar', 'com.android.camera2', 'com.android.contacts', 'com.android.deskclock', 'com.android.dialer', 'com.android.documentsui', 'com.android.gallery3d', 'com.android.messaging', 'com.android.quicksearchbox', 'com.android.settings', 'com.android.threadnetwork.demoapp', 'com.bestbuy.android', 'com.ehi.national.mobile', 'com.enflick.android.TextNow', 'com.example.ndk_tests', 'com.google.android.gms', 'com.hertz.android.digital', 'com.hilton.android.hhonors', 'com.ihg.apps.android', 'com.jingdong.app.mall', 'com.lianjia.beike', 'com.marriott.mrt', 'com.pinger.textfree', 'com.rytong.airchina', 'com.rytong.ceair', 'com.sankuai.meituan.takeoutnew', 'com.sdu.didi.psnger', 'com.ss.android.ugc.aweme', 'com.szzc', 'com.taobao.taobao', 'com.tencent.mm', 'com.ubercab', 'com.united.mobile.android', 'com.xunmeng.pinduoduo', 'com.zhubajie.client', 'com.zillow.android.streeteasy', 'ctrip.android.view', 'jp.co.ana.android.tabidachi', 'local.pocket4.actions.v2', 'local.pocket4.fixture', 'org.chromium.webview_shell', 'org.droidloom.qa.editorcontract', 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1', 'org.fcitx.fcitx5.android', 'tv.danmaku.bili']
CURRENT_GUARD = {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py', 'bytes': 3213, 'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}
SCOPE_READER = {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/source/observe_successor_scope.py', 'bytes': 7695, 'sha256': '0a61313f518c7308f65f2654254689120df940cb0f5bd95d8873a42d6979914d'}
EXPECTED_HELPER_MANIFEST = '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489'
OLD_HELPER = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'
RUNTIME_EPOCH = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'


def validate_parent_scope(parent):
    need(type(parent) is dict and parent.get('schema') == 'pocket4-versioned-app-scope-v1' and
         parent.get('runtime_epoch_sha256') == RUNTIME_EPOCH and type(parent.get('apps')) is dict and
         sorted(parent['apps']) == ORIGINAL_PACKAGES and len(parent['apps']) == 48 and
         SELF not in parent['apps'], 'EXACT_LATEST_48_PARENT_NOT_A_SUBSET')
    need(sum(len(row['apks']) for row in parent['apps'].values()) == 88,
         'EXACT_PARENT_88_APKS')
    old = parent['apps'][OLD_HELPER]
    need(old['uid'] == 10157 and old['version_code'] == 1 and len(old['apks']) == 1 and
         old['apks'][0]['bytes'] == 37008 and
         old['apks'][0]['sha256'] == '006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9',
         'ORIGINAL_R1_HELPER_MUST_REMAIN')
    return parent


def validate_scope_transition(parent, observed, proof, uid, installed):
    validate_parent_scope(parent)
    names = sorted((*ORIGINAL_PACKAGES, SELF))
    need(type(observed) is dict and observed.get('schema') == 'pocket4-versioned-app-scope-v1' and
         observed.get('runtime_epoch_sha256') == RUNTIME_EPOCH and
         observed.get('kind') == 'explicit-current-app-observation' and observed.get('parent_app_scope') == PARENT_SCOPE and
         type(observed.get('apps')) is dict and sorted(observed['apps']) == names and len(observed['apps']) == 49,
         'EXACT_OBSERVED_49_SCOPE_REQUIRED')
    need(observed.get('fresh_signature_verification_performed') is False and
         observed.get('UI_or_install_runtime_admitted') is False and
         observed.get('external_evidence_policy_validated_by_this_reader') is False,
         'OBSERVER_IDENTITY_SCOPE_CANNOT_PROMOTE_ITSELF')
    need({name: observed['apps'][name] for name in ORIGINAL_PACKAGES} == parent['apps'],
         'ALL_48_COMPLETE_ORIGINAL_ROWS_MUST_REMAIN_UNCHANGED')
    need(type(uid) is int and 10000 <= uid < 100000 and uid not in {row['uid'] for row in parent['apps'].values()},
         'ACTUAL_NEW_HELPER_UID_MUST_NOT_SHARE_OLD_SCOPE')
    row = observed['apps'][SELF]
    need(row['package'] == SELF and row['uid'] == uid and row['version_code'] == 1 and
         row['package_manager_certificate_sha256'] == [proof['signer_certificate_sha256']] and
         proof['signer_certificate_sha256'] not in parent['apps'][OLD_HELPER]['package_manager_certificate_sha256'],
         'OBSERVED_NEW_HELPER_PM_IDENTITY_AND_NEW_OWNED_SIGNER')
    need(len(row['apks']) == 1 and sum(len(app['apks']) for app in observed['apps'].values()) == 89,
         'EXACTLY_ONE_NEW_BASE_APK_AND_89_TOTAL')
    apk = row['apks'][0]
    need(row['code_path'] + '/base.apk' == apk['path'] == installed['base_apk'] and
         apk['sha256'] == installed['apk_sha256'] == proof['APK']['sha256'] and
         apk['bytes'] == installed['bytes'] == proof['APK']['bytes'] and
         installed['package'] == SELF and installed['uid'] == uid and
         installed['signer_bound_by_exact_signed_apk_bytes'] == proof['signer_certificate_sha256'],
         'SAME_ACTUAL_SIGNED_APK_FROM_PM_AND_ORIGINAL_SESSION')
    mapping = {'device': 'st_dev', 'inode': 'st_ino', 'mode': 'st_mode', 'uid': 'st_uid', 'gid': 'st_gid',
               'bytes': 'st_size', 'mtime_ns': 'st_mtime_ns', 'nlink': 'st_nlink'}
    need(set(installed['held_file']) == set(mapping) and
         all(installed['held_file'][key] == apk['file'][field] for key, field in mapping.items()),
         'NEW_HELPER_SAME_HELD_APK_IDENTITY')
    need(set(row['data_directories']) == {'user', 'user_de'} and
         all(item['status'] == 'PRESENT' and item['uid'] == uid and item['gid'] == uid
             for item in row['data_directories'].values()), 'NEW_HELPER_CE_DE_OWNERSHIP_REQUIRED')
    return {'protected_original_packages': 48, 'observed_packages': 49, 'observed_APKs': 89,
            'all_original_rows_byte_structure_equal': True, 'only_new_package': SELF,
            'new_UID': uid, 'original_r1_retained': True,
            'normal_PM_signature_and_exact_verified_APK_bound': True,
            'new_CE_DE_owned_by_actual_new_UID': True,
            'full_Android_installed_inventory_or_launcher_enumeration_claimed': False,
            'effective_permission_AppOps_role_regression_completed': False,
            'UI_or_install_runtime_admitted_by_scope': False, 'production_ready': False}


class WholeScopeProtection:
    def __init__(self, flow, args, proof, recorder):
        self.flow, self.args, self.proof, self.recorder = flow, args, proof, recorder
        self.guard = flow.current_guard
        need(flow.source.BINDING['runtime_guard'] == CURRENT_GUARD and
             args.source_manifest_sha256 == EXPECTED_HELPER_MANIFEST,
             'EXACT_EXISTING_TYPED_GUARD_AND_FROZEN_HELPER_CLOSURE')
        self.core = self.guard._core()
        self.parent = validate_parent_scope(self.core.parse(self.core.pinned_record(PARENT_SCOPE)))
        self.before_guard = None

    def verify_parent(self):
        current = self.guard.current_guard(action_attempted=self.flow.action_attempted)
        need(current['schema'] == 'pocket4-successor-main-guard-v1' and
             current['runtime_epoch_sha256'] == RUNTIME_EPOCH and
             (self.before_guard is None or current == self.before_guard), 'COEXISTENCE_TYPED_RUNTIME_UNCHANGED')
        need(self.core.parse(self.core.pinned_record(PARENT_SCOPE)) == self.parent, 'ORIGINAL_SCOPE_BYTES_CHANGED')
        value = self.guard.check_app_scope(PARENT_SCOPE, ORIGINAL_PACKAGES)
        need(value['packages'] == ORIGINAL_PACKAGES and value['app_scope_sha256'] == PARENT_SCOPE['sha256'] and
             value['current_apk_paths_and_file_identities_match'] is True, 'EXACT_ALL_48_CURRENT_GUARD_REQUIRED')
        self.before_guard = current
        return value

    def admit(self):
        need(self.proof['signer_certificate_sha256'] not in self.parent['apps'][OLD_HELPER]['package_manager_certificate_sha256'],
             'NEW_HELPER_REQUIRES_ITS_NEW_OWNED_SIGNER')
        return self.verify_parent()

    def publish_after(self, result):
        need(result['install_success_observed'] is True and result['state_attempted'] is True and
             result['installed_before_state'] == result['installed_after_state'] and
             result['state']['helper']['ui_automation_connected'] is False and
             result['state']['helper']['action_attempted'] is False and result['state']['helper']['outcome_unknown'] is False,
             'ORIGINAL_NORMAL_INSTALL_AND_STATE_ONLY_PROOF_REQUIRED')
        before = self.verify_parent()
        build_raw = read(self.args.build_receipt)
        need(sha(build_raw) == self.args.build_receipt_sha256 == self.proof['build_receipt_sha256'],
             'ACTUAL_REVIEWED_BUILD_RECEIPT_STILL_EXACT')
        build_pin = {'path': str(self.args.build_receipt), 'bytes': len(build_raw), 'sha256': sha(build_raw)}
        install_observation = {
            'schema': 'pocket4-owned-helper-normal-install-before-whole-scope-v1',
            'package': SELF, 'parent_app_scope': PARENT_SCOPE, 'build': self.proof,
            'helper_source_manifest_sha256': EXPECTED_HELPER_MANIFEST,
            'installer_source_sha256': self.args.coexistence_source_sha256,
            'normal_PM_install_success_observed': True, 'replacement': False,
            'installed_before_state': result['installed_before_state'],
            'installed_after_state': result['installed_after_state'], 'state': result['state'],
            'actual_scope_after_pending': True, 'outer_owned_child_and_durable_terminal_pending': True,
            'automatic_retry': False, 'UI_actions': 0, 'production_ready': False}
        observation_pin = self.core.write_new(str(self.flow.step / 'normal-install-before-scope.private.json'),
                                              self.core.canonical(install_observation) + b'\n')
        reader_raw = self.core.pinned_record(SCOPE_READER, 65536)
        reader = types.ModuleType('unchanged_actual_explicit_app_scope_reader')
        reader.__file__ = SCOPE_READER['path']
        exec(compile(reader_raw, reader.__file__, 'exec'), reader.__dict__)
        request = {'schema': 'pocket4-successor-app-observation-request-v1', 'guard': CURRENT_GUARD,
                   'packages': sorted((*ORIGINAL_PACKAGES, SELF)), 'parent_app_scope': PARENT_SCOPE,
                   'install_or_signature_evidence': [build_pin, observation_pin],
                   'output_scope': str(self.flow.step / 'app-scope-after.private.json'),
                   'output_binding': str(self.flow.step / 'observation-binding.private.json')}
        request_pin = self.core.write_new(str(self.flow.step / 'scope-observation-request.json'),
                                         self.core.canonical(request) + b'\n')
        observed = reader.run(request)
        need(observed.get('ok') is True and observed['observation_fds']['acquired'] == observed['observation_fds']['closed'] and
             observed['observation_fds']['remaining'] == 0 and observed['observation_fds']['errors'] == [],
             'ORIGINAL_SCOPE_READER_AND_ALL_FDS_MUST_COMPLETE')
        scope = self.core.parse(self.core.pinned_record(observed['app_scope']))
        proof = validate_scope_transition(self.parent, scope, self.proof, result['helper_uid'], result['installed_after_state'])
        need(observed['app_scope_guard']['packages'] == request['packages'] and
             observed['app_scope_guard']['app_scope_sha256'] == observed['app_scope']['sha256'] and
             observed['app_scope_guard']['current_apk_paths_and_file_identities_match'] is True,
             'ORIGINAL_FRESH_49_SCOPE_GUARD')
        after = self.verify_parent()
        need(before == after, 'ALL_48_PRE_POST_SCOPE_GUARD_IDENTICAL')
        self.core.pinned_record(SCOPE_READER, 65536)
        self.core.pinned_record(build_pin)
        return {'parent_app_scope': PARENT_SCOPE, 'normal_install_observation': observation_pin,
                'observer_request': request_pin, 'observation': observed, 'transition': proof,
                'next_app_scope': observed['app_scope'], 'original_48_guard_before': before,
                'original_48_guard_after': after, 'outer_owned_child_and_durable_terminal_still_required': True}


def execute(args):
    need(os.getuid() == os.geteuid() == 0, 'ROOT_HELD_INSTALL_REQUIRED')
    need(re.fullmatch('[0-9a-f]{64}', args.coexistence_source_sha256) and
         sha(read(Path(__file__).resolve())) == args.coexistence_source_sha256 and
         args.source_manifest_sha256 == EXPECTED_HELPER_MANIFEST, 'EXACT_SEPARATELY_REVIEWED_COEXISTENCE_SOURCE')
    need(re.fullmatch(r'/home/alex/work/pocket4-successor-qa-flow-[0-9a-f]{32}', str(args.flow_dir)) and
         args.flow_dir.resolve() == args.flow_dir and args.recorder_root.resolve() == args.recorder_root and
         re.fullmatch('[0-9a-f]{32}', args.state_nonce), 'NEW_CANONICAL_FLOW_AND_STATE_NONCE')
    source_raw = read(HERE/'SOURCE_PINS.json', 131072)
    need(sha(source_raw) == args.source_manifest_sha256, 'EXTERNAL_HELPER_SOURCE_PIN')
    source = json.loads(source_raw)
    adapter = load(HERE/'qa_adapter.py', source['files']['qa_adapter.py']['sha256'], 'successor_install_adapter')
    source = adapter.own_source(args.source_manifest_sha256)
    qa = adapter.load(HERE/'qa_contract.py',source['files']['qa_contract.py']['sha256'],'successor_install_contract')
    builder = adapter.load(HERE/'build_candidate.py',source['files']['build_candidate.py']['sha256'],'successor_install_build')
    proof = adapter.qualified_build(args,source,builder)
    apk = adapter.pinned(Path(proof['APK']['path']), args.apk_sha256, 2097152)
    need(len(apk) == proof['APK']['bytes'], 'ACTUAL_BUILD_APK_SIZE')
    recorder_source = adapter.pinned(args.recorder_root/'source-manifest.json', RECORDER_MANIFEST_SHA, 131072)
    recorder_manifest = json.loads(recorder_source)
    recorder = load(args.recorder_root/'recorder.py',recorder_manifest['files']['recorder.py']['sha256'],'successor_install_recorder')
    flow_args = types.SimpleNamespace(operation='owned-helper-install', adapter_manifest_sha256=RECORDER_MANIFEST_SHA,
        flow_dir=args.flow_dir, epoch_module=args.recorder_root/'references/framework_epoch.py',
        task_source=args.recorder_root/'references/task_scope_baseline.py', step=args.step,
        request={'package':SELF,'build':proof,'state_nonce':args.state_nonce,'replacement':False,
                 'parent_app_scope':PARENT_SCOPE,'coexistence_source_sha256':args.coexistence_source_sha256},
        unknown_step=None,observation_step=None,postcondition=None)
    result = {'schema':'pocket4-successor-owned-helper-coexist-install-v1','ok':False,'package':SELF,'build':proof,
        'install_attempted':False,'install_success_observed':False,'state_attempted':False,
        'UI_actions':0,'permission_grants':0,'App_launches':0,'old_v2_helper_called':False,
        'automatic_retry':False,'production_ready':False,'errors':[]}
    flow = stage = lock = protection = None
    try:
        flow = recorder.Flow(flow_args)
        flow.begin(flow_args, mutation=True)
        lock = recorder.lock_file(recorder.ACTION_LOCK)
        flow.guard()
        held = flow.bind()
        protection = WholeScopeProtection(flow,args,proof,recorder)
        result['whole_scope_before'] = protection.admit()
        absence = command(flow,['/system/bin/cmd','package','list','packages','-u','-U','--user','all',SELF])
        need(absence == b'', 'NEW_HELPER_OR_RETAINED_PACKAGE_ALREADY_EXISTS')
        stage = Stage(held.target,args.state_nonce)
        stage.stage(apk,args.apk_sha256)
        result['guest_stage'] = stage.record
        del apk
        result['install_attempted'] = True
        output = command(flow,['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',SELF,stage.path],40,True)
        need(output == b'Success\n','EXACT_NEW_HELPER_INSTALL_SUCCESS_REQUIRED')
        result['install_success_observed'] = True
        uid_raw = command(flow,['/system/bin/cmd','package','list','packages','-U','--user','0',SELF]).decode('utf-8','strict')
        match = re.fullmatch(re.escape('package:'+SELF+' uid:')+r'([0-9]+)\n',uid_raw)
        need(match is not None,'EXACT_INSTALLED_HELPER_UID')
        uid = int(match[1])
        need(uid not in {row['uid'] for row in protection.parent['apps'].values()}, 'NEW_UID_CANNOT_SHARE_ANY_ORIGINAL_48')
        session = adapter.Session(flow,recorder,qa,proof,uid)
        result['installed_before_state'] = session.installed()
        result['state_attempted'] = True
        result['state'] = session.instrument({'protocol':qa.PROTOCOL,'nonce':args.state_nonce,'op':'state'})
        need(result['state']['helper']['ui_automation_connected'] is False,'STATE_MUST_NOT_CONNECT_UIAUTOMATION')
        result['installed_after_state'] = session.installed()
        need(result['installed_after_state'] == result['installed_before_state'],'HELPER_CHANGED_DURING_STATE')
        need(command(flow,['/system/bin/cmd','package','list','packages','-U','--user','all',SELF]).decode('utf-8','strict') == uid_raw,
             'OTHER_USER_OR_UID_APPEARED')
        result.update(helper_uid=uid,helper_retained=True)
        result['whole_scope_after'] = protection.publish_after(result)
        result['next_app_scope'] = result['whole_scope_after']['next_app_scope']
        result['scope_requires_outer_owned_child_and_durable_terminal'] = True
        result['ok'] = True
    except BaseException as error:
        result['errors'].append({'phase':'install_or_state','type':type(error).__name__,'code':str(error)[:256]})
    finally:
        if stage is not None:
            try:
                stage.close()
            except BaseException as error:
                result['errors'].append({'phase':'stage_fd_close','type':type(error).__name__})
        if protection is not None:
            try:
                result['whole_scope_final_guard'] = protection.verify_parent()
            except BaseException as error:
                result['errors'].append({'phase':'final_all_48_scope_guard','type':type(error).__name__,'code':str(error)[:256]})
        if flow is not None:
            for phase, operation in (('final_runtime_and_app_guard',lambda:flow.guard(attempted=flow.action_attempted)),('held_binding_close',flow.close)):
                try:
                    operation()
                except BaseException as error:
                    result['errors'].append({'phase':phase,'type':type(error).__name__})
        if result['errors']:
            result['ok'] = False
        result['action_attempted'] = bool(flow is not None and flow.action_attempted)
        result['outcome_unknown'] = result['action_attempted'] and not result['ok']
        result['ended_utc'] = recorder.now()
        result['action_lock_held_through_durable_result'] = lock is not None
        try:
            if flow is not None and flow.step is not None:
                recorder.write_new(flow.step/'result.json',result)
        finally:
            if lock is not None:
                os.close(lock)
    print(json.dumps(result,sort_keys=True,ensure_ascii=True),flush=True)
    return 0 if result['ok'] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--install-once',action='store_true')
    for name in ('coexistence-source-sha256','source-manifest-sha256','build-receipt-sha256','apk-sha256','signer-certificate-sha256','state-nonce','step'):
        p.add_argument('--'+name)
    for name in ('build-receipt','recorder-root','flow-dir'):
        p.add_argument('--'+name,type=Path)
    args = p.parse_args()
    if not args.install_once:
        print(json.dumps({'status':'PLAN_ONLY','package':SELF,'replacement':False,'UiAutomation_connection_requested':False}))
        return 0
    os.umask(0o077)
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
