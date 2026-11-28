"""One new owned helper install and state-only probe on actual final Main.

The thirteen original ordered commands are retained. No UiAutomation connection,
commercial package write, App launch, task removal or uninstall is authorized.
UNKNOWN retains the new package and owned staging files for reconciliation.
"""
import os
from pathlib import Path
import re
import secrets
import time
import types

SELF = 'org.droidloom.qa.ihg.finalmain.r1'
TARGET = 'com.ihg.apps.android'
ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'


def install(common, build_ref, target_identity_ref, output, profiles_ref, staging_ref, builder_ref):
    common.need(os.getuid() == os.geteuid() == 0, 'ROOT_HELD_INSTALL_OBSERVER_REQUIRED')
    profiles = common.module(profiles_ref, 'actual_install_profiles')
    builder = common.module(builder_ref, 'actual_final_helper_builder')
    build, source, baseline, modules = builder.verify_build(common, build_ref)
    preserved_uids = baseline.require_preinstall_inventory()
    identity = common.parse(common.read_ref(target_identity_ref))
    common.validate_identity(identity, profiles.IHG, source['baseline'], source['qualification'])
    root = Path(output)
    common.need(root.parent == common.QUALIFICATION and
                re.fullmatch(r'business-ihg-install-[0-9a-f]{32}', root.name), 'NEW_PRIVATE_ONCE_INSTALL_ROOT_REQUIRED')
    common.private_dir(root, create=True); journal = common.private_dir(root / 'commands', create=True)
    nonce = secrets.token_hex(16); state_nonce = secrets.token_hex(16)
    guest_name = 'pocket4-final-ihg-qa-' + nonce; guest = '/data/local/tmp/' + guest_name + '/owned-ihg-qa.apk'
    qa = common.module(source['files']['qa_contract.py'], 'actual_final_install_state_protocol')
    staging = common.module(staging_ref, 'actual_new_owned_APK_staging')
    request = {'protocol': qa.PROTOCOL, 'nonce': state_nonce, 'op': 'state'}
    listed, paths = common.package_commands(TARGET, False)[:2]
    own_uid = ['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', '0', SELF]
    own_path = ['/system/bin/cmd', 'package', 'path', '--user', '0', SELF]
    absent = ['/system/bin/cmd', 'package', 'list', 'packages', '-u', '-U', '--user', 'all', SELF]
    installed_all = ['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', 'all', SELF]
    install_argv = ['/system/bin/cmd', 'package', 'install', '-R', '-t', '--user', '0', '--pkg', SELF, guest]
    plan = [(listed, 15, False), (paths, 15, False), (absent, 8, False), (install_argv, 40, True),
            (own_uid, 8, False), (own_uid, 8, False), (own_path, 8, False),
            (qa.instrumentation_argv(request), 20, False), (own_uid, 8, False), (own_path, 8, False),
            (installed_all, 8, False), (listed, 15, False), (paths, 15, False)]
    common.write_new(root / 'once.claim.json', {'build': build_ref, 'target_identity': target_identity_ref,
        'baseline': source['baseline'], 'qualification': source['qualification'], 'nonce': nonce,
        'state_nonce': state_nonce, 'commands': plan, 'automatic_retry': False})
    result = {'schema': 'pocket4-final-ihg-helper-install-v1', 'state': 'FAILED', 'build': build_ref,
        'source': build['source'], 'target_identity': target_identity_ref, 'baseline': source['baseline'],
        'qualification': source['qualification'], 'package': SELF, 'nonce': nonce, 'state_nonce': state_nonce,
        'user_zero_inventory_before': baseline.value['user_zero_package_inventory'],
        'commands': [], 'install_attempted': False, 'install_success_observed': False, 'error': None,
        'UI_actions': 0, 'UiAutomation_connection_requested': False, 'App_launches': 0,
        'commercial_package_writes': 0, 'task_removals': 0, 'uninstalls': 0, 'automatic_retry': False,
        'Binder_UID_cleanup_verified': False, 'whole_app_business_accepted': False}
    view = artifacts = staged = None; deadline = time.monotonic() + 175; next_command = 0
    runtime = common.module(source['files']['app_runtime.py'], 'actual_helper_install_deadline')
    commands = runtime.PhaseCommands(modules['business_commands.py'], types.SimpleNamespace(c=common, deadline=deadline))
    def guard(*, action_attempted=False):
        common.need(time.monotonic() < deadline, 'ORIGINAL_INSTALL_WORK_LEASE_EXPIRED')
        common.read_ref(build_ref); common.read_ref(target_identity_ref)
        for ref in (profiles_ref, staging_ref, builder_ref):
            common.read_ref(ref)
        if artifacts is not None:
            artifacts.verify()
        return view.guard(action_attempted=action_attempted) if view is not None else baseline.guard()
    def command(argv, timeout=8, mutation=False):
        nonlocal next_command
        common.need(next_command < len(plan) and (argv, timeout, mutation) == plan[next_command],
                    'ORIGINAL_ORDERED_THIRTEEN_INSTALL_COMMANDS_ONLY')
        guard(); next_command += 1; name = 'command-%03d' % next_command
        common.write_new(journal / (name + '.logical.json'), {'argv': argv, 'timeout': timeout,
            'mutation': mutation, 'baseline': source['baseline'], 'automatic_retry': False})
        suffix = ['/system/bin/env', '-i'] + [k + '=' + view.environment[k] for k in sorted(view.environment)]
        suffix += ['/system/xbin/su', '2000', '/system/bin/timeout', '-k', '2', str(max(1, timeout - 5)), *argv]
        manager = view.target.entry(suffix); entered = False; completed = None; primary = None; released = False
        try:
            physical, fds = manager.__enter__(); entered = True
            completed = commands.run_recorded(name, physical, timeout, journal, guard,
                protected_pids=baseline.protected_pids, mutation=mutation, pass_fds=fds, host_env=common.HOST_ENV,
                check=False, deferred_post_guard=True)
        except BaseException as error:
            primary = error
            if getattr(error, 'command_observation', {}).get('host_retirement_proved') is not True:
                view.target.poison_unjoined_command()
        finally:
            if entered:
                try:
                    manager.__exit__(None if primary is None else type(primary), primary,
                                     None if primary is None else primary.__traceback__)
                    released = True
                except BaseException as error:
                    if primary is None:
                        primary = error
                    else:
                        primary.add_note('INSTALL_LEASE_EXIT:' + type(error).__name__)
            try:
                post = guard(action_attempted=mutation)
            except BaseException as error:
                post = None
                if primary is None:
                    primary = error
                else:
                    primary.add_note('INSTALL_POST_GUARD:' + type(error).__name__)
        transport = common.write_new(journal / (name + '.transport.json'), {'lease_entered': entered,
            'lease_released': released, 'post_guard': post, 'baseline': source['baseline'],
            'error_type': None if primary is None else type(primary).__name__,
            'host_retirement_proved': bool(completed and completed.host_tree_retired)})
        if primary is not None:
            raise primary
        common.need(completed.returncode == 0 and completed.host_tree_retired and not completed.host_timed_out and
                    completed.recorder_errors == [] and completed.stderr == b'', 'ACTUAL_JOINED_QUIET_INSTALL_COMMAND_REQUIRED')
        row = {'argv': argv, 'timeout': timeout, 'mutation': mutation, 'transport': transport,
               'result': common.regular(journal / (name + '.result.json'), contents=False)}
        result['commands'].append(row)
        return completed.stdout
    def uid_from(raw):
        match = re.fullmatch(re.escape('package:' + SELF + ' uid:') + r'([0-9]+)\n', raw.decode('utf-8', 'strict'))
        common.need(match is not None, 'ONE_EXACT_NEW_HELPER_UID_REQUIRED')
        uid = int(match[1]); profiles.helper_expected(common, build, uid)
        common.need(uid not in preserved_uids.values(), 'NEW_HELPER_MUST_NOT_SHARE_PRESERVED_APP_UID')
        return uid
    def installed(uid):
        common.need(uid_from(command(own_uid)) == uid, 'NEW_HELPER_UID_CHANGED')
        paths_observed = common.apk_paths(command(own_path))
        common.need(len(paths_observed) == 1 and paths_observed[0].startswith('/data/app/') and paths_observed[0].endswith('/base.apk'),
                    'SINGLE_ACTUAL_NEW_HELPER_APK_REQUIRED')
        raw, metadata = view.target.read_file(paths_observed[0], 2097152, single_link=True)
        common.need(len(raw) == build['APK']['bytes'] and common.sha(raw) == build['APK']['sha256'],
                    'INSTALLED_HELPER_NOT_ACTUAL_SIGNED_NEW_BUILD')
        return {'package': SELF, 'uid': uid, 'base_apk': paths_observed[0], 'bytes': len(raw),
            'apk_sha256': common.sha(raw), 'held_file': metadata,
            'signer_bound_by_exact_signed_apk_bytes': build['signer_certificate_sha256']}
    try:
        with common.locked(ACTION_LOCK, wait_seconds=5):
            def no_read_route(*unused):
                raise RuntimeError('INSTALL_REQUIRES_ITS_EXACT_ORDERED_COMMAND_CHANNEL')
            view = common.MainView(source['baseline'], source['qualification'], journal, no_read_route)
            artifacts = common.HeldArtifacts(view.target, [identity]); result['Main_before'] = guard()
            result['target_before'] = {'metadata': common.package_metadata(command(listed, 15), profiles.IHG),
                                      'paths': common.apk_paths(command(paths, 15))}
            common.need(result['target_before']['paths'] == [x['guest_path'] for x in identity['artifacts']], 'TARGET_ACTIVE_APK_PATH_CHANGED')
            common.need(command(absent) == b'', 'NEW_PACKAGE_OR_RETAINED_RECORD_ALREADY_EXISTS')
            staged = staging.OwnedApk(view.target, build['APK'], guest_name)
            result['staged_apk'] = staged.stage(common.read_ref(build['APK'], 2097152))
            result['install_attempted'] = True
            common.need(command(install_argv, 40, True) == b'Success\n', 'INSTALL_DID_NOT_REPORT_EXACT_SUCCESS')
            result['install_success_observed'] = True; uid = uid_from(command(own_uid))
            result['installed_before_state'] = installed(uid)
            raw = command(qa.instrumentation_argv(request), 20)
            state = qa.parse_completed(raw, b'', 0, request, uid)
            common.need(state['helper']['ui_automation_connected'] is False and state['helper']['op'] == 'state',
                        'STATE_PROBE_MUST_NOT_CONNECT_UIAUTOMATION')
            result['state_observation'] = common.write_new(root / 'state-observation.json', state)
            result['installed_after_state'] = installed(uid)
            common.need(result['installed_after_state'] == result['installed_before_state'], 'HELPER_CHANGED_ACROSS_STATE_PROBE')
            common.need(uid_from(command(installed_all)) == uid, 'HELPER_APPEARED_FOR_OTHER_USER_OR_UID')
            result['target_after'] = {'metadata': common.package_metadata(command(listed, 15), profiles.IHG),
                                     'paths': common.apk_paths(command(paths, 15))}
            common.need(result['target_after'] == result['target_before'] and next_command == len(result['commands']) == 13,
                        'TARGET_PRESERVATION_OR_EXACT_INSTALL_COMMAND_COUNT_FAILED')
            artifacts.revalidate(); result['Main_after'] = guard()
            common.need(result['Main_before'] == result['Main_after'], 'MAIN_CHANGED_DURING_NEW_HELPER_INSTALL')
            result.update(state='INSTALLED_STATE_OBSERVED', helper_uid=uid, package_retained=True)
    except BaseException as error:
        result['state'] = 'UNKNOWN' if result['install_attempted'] or getattr(error, 'command_observation', {}).get('host_retirement_proved') is False else 'FAILED'
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'notes': getattr(error, '__notes__', [])}
        raise
    finally:
        if staged is not None:
            try:
                result['staging_cleanup'] = staged.close(retire_files=result['state'] != 'UNKNOWN')
            except BaseException as error:
                result['state'] = 'UNKNOWN'; result['staging_cleanup_error'] = type(error).__name__
        for obj, name in ((artifacts, 'artifact_FDs'), (view, 'held_Main')):
            if obj is not None:
                try:
                    obj.close(); result[name + '_closed'] = True
                except BaseException as error:
                    result['state'] = 'UNKNOWN'; result[name + '_closed'] = False
                    result[name + '_close_error'] = type(error).__name__
        common.write_new(root / 'result.json', result)
    common.need(result['state'] == 'INSTALLED_STATE_OBSERVED', 'INSTALL_NOT_COMPLETED')
    return common.regular(root / 'result.json', contents=False)


def verify_install(common, install_ref, build, source, qa, target_identity_ref):
    value = common.parse(common.read_ref(install_ref))
    if value.get('schema') == V2_INSTALL:
        return verify_native_install(common,value,build,source,qa,target_identity_ref)
    common.need(value['schema'] == 'pocket4-final-ihg-helper-install-v1' and value['state'] == 'INSTALLED_STATE_OBSERVED'
        and value['package'] == SELF and value['source'] == build['source'] and
        value['baseline'] == source['baseline'] and value['qualification'] == source['qualification'] and
        value['target_identity'] == target_identity_ref and value['error'] is None and
        value['install_attempted'] is True and value['install_success_observed'] is True and
        value['UI_actions'] == value['App_launches'] == value['commercial_package_writes'] == value['task_removals'] == value['uninstalls'] == 0 and
        value['UiAutomation_connection_requested'] is False and value['artifact_FDs_closed'] is True and
        value['held_Main_closed'] is True and value['Main_before'] == value['Main_after'],
        'COMPLETED_ACTUAL_NEW_HELPER_INSTALL_REQUIRED')
    common.need(value['staging_cleanup']['staged_apk_removed'] is True and
                value['staging_cleanup']['staged_directory_removed'] is True and
                value['staging_cleanup']['authority_fds_closed'] is True, 'KNOWN_OWNED_STAGING_NOT_RETIRED')
    common.need(re.fullmatch('[0-9a-f]{32}', value['nonce']) and re.fullmatch('[0-9a-f]{32}', value['state_nonce'])
                and value['nonce'] != value['state_nonce'], 'ACTUAL_DISTINCT_INSTALL_NONCES_REQUIRED')
    guest = '/data/local/tmp/pocket4-final-ihg-qa-' + value['nonce'] + '/owned-ihg-qa.apk'
    listed, paths = common.package_commands(TARGET, False)[:2]
    own_uid = ['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', '0', SELF]
    own_path = ['/system/bin/cmd', 'package', 'path', '--user', '0', SELF]
    request = {'protocol': qa.PROTOCOL, 'nonce': value['state_nonce'], 'op': 'state'}
    expected = [(listed, 15, False), (paths, 15, False),
        (['/system/bin/cmd', 'package', 'list', 'packages', '-u', '-U', '--user', 'all', SELF], 8, False),
        (['/system/bin/cmd', 'package', 'install', '-R', '-t', '--user', '0', '--pkg', SELF, guest], 40, True),
        (own_uid, 8, False), (own_uid, 8, False), (own_path, 8, False),
        (qa.instrumentation_argv(request), 20, False), (own_uid, 8, False), (own_path, 8, False),
        (['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', 'all', SELF], 8, False),
        (listed, 15, False), (paths, 15, False)]
    common.need(len(value['commands']) == 13, 'EXACT_THIRTEEN_ACTUAL_INSTALL_COMMANDS_REQUIRED')
    outputs = []
    for item, (argv, timeout, mutation) in zip(value['commands'], expected):
        common.need((item['argv'], item['timeout'], item['mutation']) == (argv, timeout, mutation),
                    'ACTUAL_INSTALL_SEQUENCE_DIFFERS_FROM_ORIGINAL_ADMISSION')
        row = common.parse(common.read_ref(item['result'])); transport = common.parse(common.read_ref(item['transport']))
        common.need(row['host_retirement_proved'] is True and row['evidence_complete'] is True and row['returncode'] == 0 and
            row['timed_out'] is False and row['errors'] == [] and row.get('first_error') is None and
            row['argv'][-len(argv):] == argv and common.read_ref(row['stderr']) == b'' and
            transport['lease_entered'] is True and transport['lease_released'] is True and
            transport['host_retirement_proved'] is True and transport['error_type'] is None and
            transport['post_guard']['business_baseline_sha256'] == source['baseline']['sha256'] and
            transport['post_guard']['business_qualification_sha256'] == source['qualification']['sha256'],
            'ACTUAL_INSTALL_COMMAND_OR_HELD_POST_GUARD_NOT_VERIFIED')
        outputs.append(common.read_ref(row['stdout']))
    identity = common.parse(common.read_ref(target_identity_ref))
    common.need(outputs[0] == outputs[11] and outputs[1] == outputs[12] and outputs[2] == b'' and outputs[3] == b'Success\n'
        and common.apk_paths(outputs[1]) == [a['guest_path'] for a in identity['artifacts']], 'ACTUAL_INSTALL_TARGET_PRESERVATION_FAILED')
    expected_uid = ('package:' + SELF + ' uid:' + str(value['helper_uid']) + '\n').encode()
    common.need(all(outputs[i] == expected_uid for i in (4, 5, 8, 10)) and outputs[6] == outputs[9] and
        value['installed_before_state'] == value['installed_after_state'] and
        common.apk_paths(outputs[6]) == [value['installed_before_state']['base_apk']] and
        value['installed_before_state']['apk_sha256'] == build['APK']['sha256'] and
        value['installed_before_state']['bytes'] == build['APK']['bytes'], 'ACTUAL_HELPER_IDENTITY_CHAIN_CHANGED')
    observed = qa.parse_completed(outputs[7], b'', 0, request, value['helper_uid'])
    common.need(observed == common.parse(common.read_ref(value['state_observation'])) and
        observed['helper']['ui_automation_connected'] is False and observed['helper']['op'] == 'state',
        'ACTUAL_STATE_ONLY_INSTALL_PROBE_REQUIRED')
    _, modules = common.support()
    baseline = modules['business_baseline.py'].BusinessBaseline(source['baseline'], source['qualification'])
    common.need(value['user_zero_inventory_before'] == baseline.value['user_zero_package_inventory'],
                'INSTALL_FULL_USER0_PREIMAGE_CHANGED')
    baseline.require_installed_helper_inventory(value['helper_uid'])
    return value

# v2 is produced only after Rust's actual same-Main factory transaction and
# state-only query. This Python step independently parses the complete original
# helper protocol; it has no guest command path and does not mint an owner.
V2_INSTALL = 'droidloom.ihg-static-helper-install.v2'
V2_VALIDATION = 'droidloom.ihg-static-helper-validation.v2'
V2_FIELDS = {'schema','state','package','build','source','target_identity','baseline','qualification',
    'normal_installation','helper_uid','installed_identity','state_nonce','state_observation',
    'Main_before','Main_after','install_attempted','install_success_observed','UI_actions',
    'UiAutomation_connection_requested','App_launches','commercial_package_writes','task_removals',
    'uninstalls','automatic_retry','whole_app_business_accepted','error'}

def _same_table(common, first, second):
    common.need(type(first) is dict and type(second) is dict and first['epoch'] == second['epoch']
        and first['records'] == second['records'] and first['records_sha256'] == second['records_sha256'],
        'SAME_EPOCH_COMPLETE_PACKAGE_TABLE_REQUIRED')

def _native_observation(common, native_ref, build, source, target_identity_ref, qa):
    native = common.parse(common.read_ref(native_ref))
    common.need(set(native) == {'schema','build','target_identity','main_binding','installation',
        'state','helper_before_state','automatic_retry','whole_app_business_accepted'} and
        native['schema'] == 'droidloom.ihg-static-helper-observation.v2' and
        native['target_identity'] == target_identity_ref and native['automatic_retry'] is False and
        native['whole_app_business_accepted'] is False, 'EXACT_ACTUAL_NATIVE_IHG_OBSERVATION')
    expected_binding={'main_epoch_sha256':source['framework_epoch_sha256'],
        'main_baseline_schema':'droidloom.native-leaf-business-baseline.v1',
        'main_baseline_sha256':source['baseline']['sha256'],
        'main_baseline_qualification_sha256':source['qualification']['sha256']}
    common.need(native['main_binding'] == expected_binding, 'ACTUAL_RUNTIME_MAIN_BINDING_CHANGED')
    observed=native['installation']; state=native['state']; primary=observed['request']['target']
    common.need(observed['schema']=='droidloom.ihg-helper-install-reply.v2'
        and observed['request']['schema']=='droidloom.ihg-helper-install-request.v2'
        and primary['package']==TARGET and primary['user']==0 and primary['uid']==10137
        and observed['request']['binding']==expected_binding
        and observed['before_main']==observed['after_main']==observed['request']['main']
        and state['schema']=='droidloom.ihg-helper-state-reply.v2'
        and state['request']['schema']=='droidloom.ihg-helper-state-request.v2'
        and state['before_main']==state['after_main']==observed['before_main']
        and state['request']['main']==observed['before_main']
        and state['request']['target']==primary and state['request']['binding']==expected_binding,
        'ACTUAL_NATIVE_INSTALL_STATE_MAIN_CHAIN_CHANGED')
    _same_table(common,observed['request']['before_inventory'],observed['before_inventory'])
    first={r['package']:r['uid'] for r in observed['before_inventory']['records']}
    after={r['package']:r['uid'] for r in observed['after_inventory']['records']}
    actual=native['helper_before_state'];uid=actual['uid']
    common.need(observed['before_inventory']['epoch']==observed['after_inventory']['epoch']
        and SELF not in first and uid not in first.values() and 10000<=uid<100000
        and after=={**first,SELF:uid} and actual['package']==SELF and actual['user']==0
        and actual['version_code']==1 and actual['epoch']==primary['epoch']
        and state['request']['helper']==actual and len(actual['apks'])==1
        and actual['apks'][0]['name']=='base.apk' and actual['apks'][0]['path'].startswith('/data/app/')
        and actual['apks'][0]['path'].endswith('/base.apk')
        and actual['apks'][0]['bytes']==build['APK']['bytes']
        and actual['apks'][0]['sha256']==build['APK']['sha256'],
        'ACTUAL_NEW_HELPER_COMPLETE_IDENTITY_OR_SINGLETON_INVENTORY_CHANGED')
    transaction=observed['installation'];sid=transaction['session']
    common.need(set(transaction)=={'session','user','bytes','segments','commands'} and type(sid) is int and sid>0
        and transaction['user']==0 and transaction['bytes']==build['APK']['bytes']
        and transaction['segments']==[{'index':0,'bytes':build['APK']['bytes'],'sha256':build['APK']['sha256']}]
        and [r['command'] for r in transaction['commands']]==[
            {'install':'CreateOnly','bytes':build['APK']['bytes']},
            {'install':'Write','session':sid,'index':0,'bytes':build['APK']['bytes']},
            {'install':'Commit','session':sid}], 'ACTUAL_CREATE_ONLY_TRANSACTION_REQUIRED')
    commands=[observed['absence']]+[{'receipt':r['receipt']} for r in transaction['commands']]+[state['command']]
    for item in commands:
        receipt=item['receipt']
        common.need(receipt['schema']==2 and receipt['cgroup_removed'] is True
            and receipt['query_waitid_code']==1 and receipt['query_waitid_status']==0
            and receipt['lifecycle']['release_acknowledged'] is True,
            'ACTUAL_NORMAL_FACTORY_RETIREMENT_REQUIRED')
    common.need(observed['absence']['stdout']==[] and observed['absence']['stderr']==[]
        and state['command']['stderr']==[], 'FULL_RETAINED_ABSENCE_AND_QUIET_STATE_REQUIRED')
    raw=bytes(state['command']['stdout']);err=bytes(state['command']['stderr'])
    common.need(state['command']['receipt']['output_bytes']==len(raw)
        and state['command']['receipt']['output_sha256']==common.sha(raw)
        and state['command']['stderr_bytes']==len(err) and state['command']['stderr_sha256']==common.sha(err),
        'COMPLETE_STATE_OUTPUT_REQUIRED')
    request={'protocol':qa.PROTOCOL,'nonce':state['request']['nonce'],'op':'state'}
    parsed=qa.parse_completed(raw,err,0,request,uid)
    common.need(parsed['helper']['ui_automation_connected'] is False and parsed['helper']['op']=='state',
        'STATE_ONLY_HELPER_OBSERVATION_REQUIRED')
    return native,actual,parsed

def validate_native_install(common, build_ref, target_identity_ref, native_ref, output, profiles_ref, builder_ref):
    common.need(os.getuid()==os.geteuid()==0, 'ROOT_NORMAL_INSTALL_VALIDATOR_REQUIRED')
    profiles=common.module(profiles_ref,'normal_ihg_static_profiles')
    builder=common.module(builder_ref,'normal_ihg_static_builder')
    build,source,baseline,_=builder.verify_build(common,build_ref)
    common.need(build['schema']=='droidloom.ihg-prebuilt-helper-binding.v2', 'NORMAL_STATIC_BUILD_REQUIRED')
    identity=common.parse(common.read_ref(target_identity_ref))
    common.validate_identity(identity,profiles.IHG,source['baseline'],source['qualification'])
    qa=common.module(source['files']['qa_contract.py'],'normal_ihg_static_state_protocol')
    native,actual,parsed=_native_observation(common,native_ref,build,source,target_identity_ref,qa)
    common.need(native['build']==build_ref,'ACTUAL_NATIVE_BUILD_REFERENCE_CHANGED')
    root=Path(output)
    common.need(root.parent==common.QUALIFICATION and re.fullmatch(r'business-ihg-install-[0-9a-f]{32}',root.name),
        'NEW_NORMAL_INSTALL_COMPARISON_ROOT')
    common.private_dir(root,create=True)
    state_ref=common.write_new(root/'state-observation.json',parsed)
    result={'schema':V2_VALIDATION,'state':'INSTALLED_STATE_OBSERVED','package':SELF,'build':build_ref,
        'source':build['source'],'target_identity':target_identity_ref,'baseline':source['baseline'],
        'qualification':source['qualification'],'normal_installation':native_ref,'helper_uid':actual['uid'],
        'installed_identity':actual,'state_nonce':native['state']['request']['nonce'],'state_observation':state_ref,
        'Main_before':native['installation']['before_main'],'Main_after':native['state']['after_main'],
        'install_attempted':True,'install_success_observed':True,'UI_actions':0,
        'UiAutomation_connection_requested':False,'App_launches':0,'commercial_package_writes':0,
        'task_removals':0,'uninstalls':0,'automatic_retry':False,'whole_app_business_accepted':False,'error':None}
    common.need(set(result)==V2_FIELDS,'CLOSED_NATIVE_INSTALL_VALIDATION_SHAPE')
    baseline.guard()
    return common.write_new(root/'result.json',result)

def verify_native_install(common, value, build, source, qa, target_identity_ref):
    common.need(set(value)==V2_FIELDS|{'validation','actual_post_helper','actual_post_main','actual_post_inventory'}
        and value['schema']==V2_INSTALL and value['state']=='INSTALLED_STATE_OBSERVED'
        and value['package']==SELF and value['source']==build['source']
        and value['baseline']==source['baseline'] and value['qualification']==source['qualification']
        and value['target_identity']==target_identity_ref and value['error'] is None
        and value['install_attempted'] is True and value['install_success_observed'] is True
        and value['automatic_retry'] is False and value['whole_app_business_accepted'] is False
        and value['UiAutomation_connection_requested'] is False
        and all(value[k]==0 for k in ('UI_actions','App_launches','commercial_package_writes','task_removals','uninstalls')),
        'EXACT_NATIVE_INSTALL_FINAL_FACTS')
    validation=common.parse(common.read_ref(value['validation']))
    common.need(validation=={k:(V2_VALIDATION if k=='schema' else value[k]) for k in V2_FIELDS},
        'ACTUAL_PYTHON_VALIDATION_CHANGED')
    native,actual,parsed=_native_observation(common,value['normal_installation'],build,source,target_identity_ref,qa)
    common.need(native['build']==value['build'] and value['installed_identity']==actual
        and value['helper_uid']==actual['uid'] and value['actual_post_helper']==actual
        and value['state_nonce']==native['state']['request']['nonce']
        and value['Main_before']==value['Main_after']==value['actual_post_main']==native['state']['after_main']
        and common.parse(common.read_ref(value['state_observation']))==parsed,
        'ACTUAL_POST_INSTALL_HELPER_MAIN_OR_PARSED_STATE_CHANGED')
    _same_table(common,value['actual_post_inventory'],native['installation']['after_inventory'])
    _,modules=common.support()
    baseline=modules['business_baseline.py'].BusinessBaseline(source['baseline'],source['qualification'])
    baseline.require_installed_helper_inventory(value['helper_uid'])
    return value
