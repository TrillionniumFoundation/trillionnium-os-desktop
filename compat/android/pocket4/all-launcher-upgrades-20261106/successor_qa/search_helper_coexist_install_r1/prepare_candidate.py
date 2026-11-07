#!/usr/bin/env python3
"""Prepare an unsubmitted source-only coexistence installer; no Android calls."""
import ast
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
BASE = PROJECT / 'successor_qa/search_click_same_process_r1/candidate-r2/helper'
DEST = HERE / 'candidate-r1'
SCOPE_PATH = PROJECT / 'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json'
SCOPE_READER_SOURCE = PROJECT / 'recovery/observe_successor_scope.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def save(name, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    path = DEST / name
    with path.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    assert path.read_bytes() == raw
    return pin(path)


def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def functions(text):
    result = {}
    def take(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, ast.FunctionDef):
                result[prefix + node.name] = ast.dump(node, include_attributes=False)
            elif isinstance(node, ast.ClassDef):
                take(node.body, prefix + node.name + '.')
    take(ast.parse(text).body)
    return result


def main():
    base_raw = (BASE / 'install_owned_helper.py').read_bytes()
    assert (len(base_raw), sha(base_raw)) == (11045, '85bf80e8823f64413583b778f4d934b680d66e6b9b3dc1bab4555da3b351317a')
    manifest_raw = (BASE / 'SOURCE_PINS.json').read_bytes()
    assert sha(manifest_raw) == '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489'
    manifest = json.loads(manifest_raw)
    for name, expected in manifest['files'].items():
        raw = (BASE / name).read_bytes()
        assert expected == {'bytes': len(raw), 'sha256': sha(raw)}
    scope_raw = SCOPE_PATH.read_bytes()
    assert (len(scope_raw), sha(scope_raw)) == (59259, '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a')
    scope = json.loads(scope_raw)
    assert len(scope['apps']) == 48 and sum(len(row['apks']) for row in scope['apps'].values()) == 88
    reader_raw = SCOPE_READER_SOURCE.read_bytes()
    assert (len(reader_raw), sha(reader_raw)) == (7695, '0a61313f518c7308f65f2654254689120df940cb0f5bd95d8873a42d6979914d')
    parent = {'path': '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-full48-r4-01/app-scope-after.private.json',
              'bytes': len(scope_raw), 'sha256': sha(scope_raw)}
    guard = {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py',
             'bytes': 3213, 'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}
    reader = {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/source/observe_successor_scope.py',
              'bytes': len(reader_raw), 'sha256': sha(reader_raw)}
    fragment = (HERE / 'scope_extension.py.fragment').read_text()
    for token, value in (('@PARENT_SCOPE@', parent), ('@ORIGINAL_PACKAGES@', sorted(scope['apps'])),
                         ('@CURRENT_GUARD@', guard), ('@SCOPE_READER@', reader)):
        assert fragment.count(token) == 1
        fragment = fragment.replace(token, repr(value))
    original = base_raw.decode('utf-8')
    source = replace(original, 'HERE = Path(__file__).resolve().parent',
                     "HERE = Path('/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1')")
    source = replace(source, '\ndef execute(args):\n', '\n' + fragment + '\n\ndef execute(args):\n')
    source = replace(source, "    need(os.getuid() == os.geteuid() == 0, 'ROOT_HELD_INSTALL_REQUIRED')",
        "    need(os.getuid() == os.geteuid() == 0, 'ROOT_HELD_INSTALL_REQUIRED')\n"
        "    need(re.fullmatch('[0-9a-f]{64}', args.coexistence_source_sha256) and\n"
        "         sha(read(Path(__file__).resolve())) == args.coexistence_source_sha256 and\n"
        "         args.source_manifest_sha256 == EXPECTED_HELPER_MANIFEST, 'EXACT_SEPARATELY_REVIEWED_COEXISTENCE_SOURCE')")
    source = replace(source, "request={'package':SELF,'build':proof,'state_nonce':args.state_nonce,'replacement':False},",
        "request={'package':SELF,'build':proof,'state_nonce':args.state_nonce,'replacement':False,\n"
        "                 'parent_app_scope':PARENT_SCOPE,'coexistence_source_sha256':args.coexistence_source_sha256},")
    source = replace(source, "result = {'schema':'pocket4-successor-owned-helper-install-v1'", 
        "result = {'schema':'pocket4-successor-owned-helper-coexist-install-v1'")
    source = replace(source, '    flow = stage = lock = None\n', '    flow = stage = lock = protection = None\n')
    source = replace(source, '        held = flow.bind()\n',
        "        held = flow.bind()\n"
        "        protection = WholeScopeProtection(flow,args,proof,recorder)\n"
        "        result['whole_scope_before'] = protection.admit()\n")
    source = replace(source, '        uid = int(match[1])\n',
        "        uid = int(match[1])\n"
        "        need(uid not in {row['uid'] for row in protection.parent['apps'].values()}, 'NEW_UID_CANNOT_SHARE_ANY_ORIGINAL_48')\n")
    source = replace(source, '        result.update(ok=True,helper_uid=uid,helper_retained=True)\n',
        "        result.update(helper_uid=uid,helper_retained=True)\n"
        "        result['whole_scope_after'] = protection.publish_after(result)\n"
        "        result['next_app_scope'] = result['whole_scope_after']['next_app_scope']\n"
        "        result['scope_requires_outer_owned_child_and_durable_terminal'] = True\n"
        "        result['ok'] = True\n")
    source = replace(source, "        if flow is not None:\n            for phase, operation in (('final_runtime_and_app_guard'",
        "        if protection is not None:\n"
        "            try:\n"
        "                result['whole_scope_final_guard'] = protection.verify_parent()\n"
        "            except BaseException as error:\n"
        "                result['errors'].append({'phase':'final_all_48_scope_guard','type':type(error).__name__,'code':str(error)[:256]})\n"
        "        if flow is not None:\n            for phase, operation in (('final_runtime_and_app_guard'")
    source = replace(source, "for name in ('source-manifest-sha256','build-receipt-sha256','apk-sha256','signer-certificate-sha256','state-nonce','step'):",
        "for name in ('coexistence-source-sha256','source-manifest-sha256','build-receipt-sha256','apk-sha256','signer-certificate-sha256','state-nonce','step'):")
    compile(source, 'install_search_helper_full_scope.py', 'exec')
    a, b = functions(original), functions(source)
    changed = [name for name in a if a[name] != b[name]]
    assert changed == ['execute', 'main'] and not set(a) - set(b)
    unchanged = [name for name in a if a[name] == b[name]]
    assert all(name in unchanged for name in ('command','Stage.__init__','Stage.stage','Stage.close','read','load'))
    assert "['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',SELF,stage.path]" in source
    assert "absence == b''" in source and "['/system/bin/cmd','package','list','packages','-u','-U','--user','all',SELF]" in source
    DEST.mkdir()
    source_pin = save('install_search_helper_full_scope.py', source.encode('utf-8'))
    diff = ''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True),
                                      fromfile='frozen-helper-candidate-r2/install_owned_helper.py',
                                      tofile='separate-coexistence-candidate-r1/install_search_helper_full_scope.py'))
    diff_pin = save('SOURCE_DIFF.patch', diff.encode('utf-8'))
    inheritance = {'schema': 'pocket4-new-helper-coexistence-source-inheritance-v1', 'source': source_pin,
        'base_installer': pin(BASE / 'install_owned_helper.py'), 'frozen_helper_manifest': pin(BASE / 'SOURCE_PINS.json'),
        'original_observer': pin(SCOPE_READER_SOURCE), 'parent_scope_actual_raw': pin(SCOPE_PATH),
        'unchanged_functions': unchanged, 'changed_functions': changed, 'added_functions': sorted(set(b)-set(a)),
        'frozen_helper_files_modified': False, 'original_PM_argv_unchanged': True,
        'original_all_users_retained_package_absence_check_unchanged': True,
        'original_build_signature_and_APK_qualification_unchanged': True,
        'original_Flow_UNKNOWN_and_guard_and_action_lock_path_unchanged': True,
        'original_state_only_instrumentation_path_unchanged': True,
        'new_scope_uses_original_reader_fullbytes': True, 'source_or_installer_executed_remotely': False}
    inheritance_pin = save('INHERITANCE.json', inheritance)

    # These are ordinary pure-function controls, not an installation result.
    module = types.ModuleType('local_coexistence_scope_projection_controls')
    module.__file__ = str(DEST / 'install_search_helper_full_scope.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    original_scope = json.loads(scope_raw)
    module.validate_parent_scope(original_scope)
    uid = 65500
    assert uid not in {row['uid'] for row in original_scope['apps'].values()}
    signer = '11'*32
    new_row = copy.deepcopy(original_scope['apps'][module.OLD_HELPER])
    new_row.update(package=module.SELF, uid=uid, code_path='/data/app/CONTROL_ONLY_NEVER_INSTALLED',
                   package_manager_certificate_sha256=[signer])
    new_row['apks'][0]['path'] = new_row['code_path'] + '/base.apk'
    for item in new_row['data_directories'].values():
        item['uid'] = item['gid'] = uid
    observed = {'schema':'pocket4-versioned-app-scope-v1','kind':'explicit-current-app-observation',
        'runtime_epoch_sha256':module.RUNTIME_EPOCH,'parent_app_scope':parent,
        'fresh_signature_verification_performed':False,'UI_or_install_runtime_admitted':False,
        'external_evidence_policy_validated_by_this_reader':False,
        'apps':{**copy.deepcopy(original_scope['apps']),module.SELF:new_row}}
    apk = new_row['apks'][0]
    proof = {'signer_certificate_sha256':signer, 'APK':{'sha256':apk['sha256'],'bytes':apk['bytes']}}
    mapping = {'device':'st_dev','inode':'st_ino','mode':'st_mode','uid':'st_uid','gid':'st_gid',
               'bytes':'st_size','mtime_ns':'st_mtime_ns','nlink':'st_nlink'}
    installed = {'package':module.SELF,'uid':uid,'base_apk':apk['path'],'apk_sha256':apk['sha256'],'bytes':apk['bytes'],
        'signer_bound_by_exact_signed_apk_bytes':signer, 'held_file':{k:apk['file'][v] for k,v in mapping.items()}}
    module.validate_scope_transition(original_scope,observed,proof,uid,installed)
    cases = [{'name':'exact_projection_control_only','passed':True}]
    negatives = [
        ('missing_one_original_package', lambda value: value['apps'].pop('com.Hyatt.hyt')),
        ('changed_original_APK_full_stat', lambda value: value['apps']['com.Hyatt.hyt']['apks'][0]['file'].__setitem__('st_mtime_ns', 0)),
        ('wrong_new_PM_signer', lambda value: value['apps'][module.SELF].__setitem__('package_manager_certificate_sha256',['22'*32])),
        ('changed_new_held_APK_inode', lambda value: value['apps'][module.SELF]['apks'][0]['file'].__setitem__('st_ino',0)),
        ('wrong_new_CE_owner', lambda value: value['apps'][module.SELF]['data_directories']['user'].__setitem__('uid',10157)),
    ]
    for name, change in negatives:
        fixture = copy.deepcopy(observed); change(fixture)
        try:
            module.validate_scope_transition(original_scope,fixture,proof,uid,installed)
        except RuntimeError as error:
            cases.append({'name':name,'passed':True,'actual_rejection':str(error)})
        else:
            raise AssertionError(name)
    try:
        module.validate_scope_transition(original_scope,observed,proof,10157,installed)
    except RuntimeError as error:
        cases.append({'name':'reuse_original_UID','passed':True,'actual_rejection':str(error)})
    else:
        raise AssertionError('reuse_original_UID')
    controls_pin = save('LOCAL_SCOPE_CONTROLS.json', {'schema':'pocket4-local-pure-coexistence-projection-controls-v1',
        'candidate_source':source_pin,'all_passed':True,'count':len(cases),'cases':cases,
        'synthetic_new_helper_fixture_only':True,'fixture_saved_as_scope_or_install_result':False,
        'Android_commands':0,'installer_execute_called':False,'Main_reads':0,'installations':0,
        'actual_new_helper_UID_or_signer_proven':False})
    design = {'schema':'pocket4-fixed-search-helper-coexistence-install-design-v1',
        'status':'SOURCE_ONLY_NOT_SEALED_FOR_EXECUTION','source':source_pin,'frozen_helper_manifest':pin(BASE/'SOURCE_PINS.json'),
        'parent_scope':parent,'parent_scope_local_actual_raw':pin(SCOPE_PATH),'before_packages':48,'before_APKs':88,
        'after_explicit_packages_required':49,'after_APKs_required':89,'new_package':module.SELF,
        'runtime_guard':guard,'original_scope_reader':reader,
        'new_helper_build_signer_UID_APK_values': 'NOT_SUPPLIED; must be actual root-reviewed build/install evidence',
        'normal_install_contract':{'replacement':False,'delete_or_uninstall_old_helper':False,'same_UID_requested':False,
            'pm_install_arguments':['install','-R','-t','--user','0','--pkg',module.SELF,'fresh-owned-staged-APK'],
            'meaning':'Original normal non-replacing testOnly-package install; regular signature/integrity path; no downgrade/permission-grant/verification-skip flag.',
            'state_probe':'Original state operation only; ui_automation_connected must be false.'},
        'lock_contract':'Original flow.lock and global actions lock cover absence, PM install, state proof, complete49 observation, unchanged48 checks and durable result. Flow.lock lifetime remains original; outer owned process exit is required.',
        'known_UNKNOWNS':'Original failed case remains FAILED/UNKNOWN. Original Flow.begin rejects mutation until separate no-action Stage B is actually published and accepted by unchanged Flow.reconciled.',
        'scope_transition':['Verify exact 59259-byte parent raw/hash and all48 current identities using original typed guard.','Keep original all-user, retained-package absence query for .r2 and original single PM install.','Use actual PM-assigned UID, exact signed APK path/hash/stat, original no-automation state and repeated installed-APK readback.','Call original observe_successor_scope.run for sorted original48 plus .r2, using actual install/core/build pins as explicit evidence references.','Require literal equality of all original48 rows including APK fullstat, CE/DE identities, UID, version and PM signer. Require new single baseAPK, actual UID, signer and CE/DE owners.','Treat scope49 as explicit identity observation only; adoption needs final all-guards/FDs/owned-child/durable terminal success. Retain incomplete outputs after any failure without advancing current scope.'],
        'output_paths':'Only inside the new original Flow step: normal-install-before-scope.private.json, scope-observation-request.json, app-scope-after.private.json, observation-binding.private.json and original result.json.',
        'consumer_transition':'After actual success root binds the new exact scope49 pin into subsequent whole-scope QA/permission/framework inputs. Earlier 48/47 observations and failed permission batches remain historical; no baseline rewrite or blind old-scope reuse.',
        'inner_Beike_scope_changed':False,'complete_PM_or_launcher_inventory_claimed':False,
        'permission_boundary':'No active permission grants, no Meituan FINE/COARSE changes, no Bili action. New manifest declares no permissions. This scope proof does not replace permission/AppOps/role regression.',
        'pending_actual_inputs_before_final_packet':['Actual new source-stage durable result and source-byte readback.','Actual new build durable terminal, complete build-result, APK bytes/hash and new signer certificate.','Actual no-action Stage B durable success and immutable reconciliation record.','Fresh exact install step/state nonce, the existing owned task/flow and new helper absence.','Root-reviewed outer owned child wrapper and exact staged source closure; source byte hash must be provided externally.'],
        'original_install_outer_budget_reference':{'CPU_percent':100,'memory_bytes':1073741824,'timeout_seconds':600},
        'budgets_not_changed_by_this_source_plan':True,'normal_installer_functions_changed':['execute additive scope checks','main extra source-pin argument'],
        'no_process_request_created':True,'no_remote_execution':True,'production_ready':False,'cleanup_eligible':False}
    design_pin = save('DESIGN.json',design)
    pins = [pin(path) for path in sorted(DEST.iterdir()) if path.is_file()]
    index = save('SOURCE_PINS.json', {'schema':'pocket4-fixed-search-coexistence-source-only-index-v1',
        'files':pins,'inputs':[pin(BASE/'install_owned_helper.py'),pin(BASE/'SOURCE_PINS.json'),pin(SCOPE_PATH),pin(SCOPE_READER_SOURCE),
                               pin(HERE/'prepare_candidate.py'),pin(HERE/'scope_extension.py.fragment')],
        'request_sealed':False,'APK_build_or_install_executed':False,'private_UI_included':False})
    print(json.dumps({'source':source_pin,'diff':diff_pin,'inheritance':inheritance_pin,'controls':controls_pin,
                      'design':design_pin,'index':index,'execution_request_created':False},sort_keys=True))


if __name__ == '__main__':
    main()
