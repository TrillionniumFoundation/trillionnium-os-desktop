#!/usr/bin/env python3
"""Offline derivation of one review-only ZBJ installer revision from actual r2/S43."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE_HOST_ROOT = '/home/alex/work/pocket4-successor-install-source-20261106-r3-zbj'
INPUT_ROOT = '/home/alex/work/pocket4-successor-install-input-20261106-zbj-s43-01'
OUTPUT_ROOT = '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-01'
SCOPE_PATH = '/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json'
S43_HOST_ROOT = '/home/alex/work/pocket4-zbj-operator-full-verification-20261106-s43'
PARENT_REL = 'successor_install/source-r2/install_successor_native.py'
S43_REL = 'official_source_scripts/s43_zbj_operator_verification'
INPUTS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()


def read(rel, expected=None):
    raw = (ROOT / rel).read_bytes()
    pin = {'path': rel, 'bytes': len(raw), 'sha256': sha(raw)}
    if expected is not None:
        assert (pin['bytes'], pin['sha256']) == expected, rel
    if pin not in INPUTS:
        INPUTS.append(pin)
    return raw


def put(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    p = HERE / name
    if p.exists():
        assert p.read_bytes() == raw, 'refuse to replace existing different artifact: ' + name
    else:
        p.write_bytes(raw)
    return {'path': name, 'bytes': len(raw), 'sha256': sha(raw)}


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new, 1)


def definitions(source):
    lines = source.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def main():
    parent = read(PARENT_REL, (38684, '7fe3d12fd280539939c930970755e9f33ab7cda51f08a03cc54eb5f9c52508eb')).decode()
    outer_parent = read('successor_install/stage_request_and_invoke_r2.py',
        (5673, 'ebff84d8e8bdee3c3d283afe885d296e1a0fad9a3bb6bdf9c90141f046f5cec4')).decode()
    stage_parent = read('successor_install/source-r2/stage_source.py').decode()
    s43_source = read(S43_REL + '/verify_complete_zbj_as_owner.py',
        (49225, '604e5e99a496d02550056b928b2bdfd98b9530581b7b6b6746df3520ff1eea0c')).decode()
    s43_request_raw = read(S43_REL + '/process-request.json',
        (50329, '5dc89fbef041afa51f74f6f74dc68027fa2051bf0d90c47dc9bf190de15e6dbe'))
    s43_request = json.loads(s43_request_raw)
    assert s43_request['args'] == ['-I', '-B', '-c', s43_source, '--verify-complete-zbj-as-existing-owner-once']
    assert s43_request['executable'] == '/usr/bin/python3'
    read(S43_REL + '/root-source-review.actual.json')
    s43_raw = read(S43_REL + '/actual/stdout.original.json',
        (52573, '96c6931181555e575bffa3e626d704b93254298441095f318691d9d3ab70cb11'))
    s43 = json.loads(s43_raw)
    terminal_raw = read(S43_REL + '/actual/terminal.original.json',
        (733, 'c42a9fd1a5bbf4f6d6ac7e335e0f3d0545379ce754c54fd9f6c99f0ba96e9076'))
    terminal = json.loads(terminal_raw)
    assert terminal['job_id'] == '1a1b2c8fc38-fc05-7fc4' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert terminal['log_bytes']['stdout'] == {'seen': len(s43_raw), 'stored': len(s43_raw)}
    assert terminal['log_bytes']['stderr'] == {'seen': 0, 'stored': 0}
    assert all(terminal[k] is False for k in ('automatic_retry', 'cancelled', 'timed_out'))
    assert all(terminal['log_errors'][s] is None and terminal['log_truncated'][s] is False and
               terminal['log_synced'][s] is True for s in ('stdout', 'stderr'))
    assert s43['ok'] is True and s43['errors'] == [] and s43['candidate_qualified_for_fresh_install_review'] is True
    assert s43['candidate_manifest_observation']['version_code'] == 370
    assert s43['candidate_signature_observation']['signer_certificate_sha256'] == [
        '556246aaaf05f61c8bbb9587dfc0660e01f6c3c6813ec038d18684d3ab378bbe']
    stream_pins = {}
    for cmd in s43['commands']:
        stream_pins[cmd['name']] = {}
        for stream in ('stdout', 'stderr'):
            pin = cmd[stream]
            raw = read(S43_REL + '/actual/' + cmd['name'] + '.' + stream + '.original.txt')
            assert (len(raw), sha(raw)) == (pin['bytes'], pin['sha256'])
            assert raw.decode() == cmd[stream + '_original_utf8']
            assert pin['path'] == S43_HOST_ROOT + '/' + cmd['name'] + '.' + stream
            stream_pins[cmd['name']][stream] = pin
    failed_s42_raw = read('official_source_scripts/s42_zbj_operator_verification/actual/stdout.original.json',
        (51004, '996845dad5c91bd67f16706561d42417ed370ab000f26ac9b16a7d1832576e0c'))
    assert json.loads(failed_s42_raw)['ok'] is False
    read('official_source_scripts/s42_zbj_operator_verification/actual/terminal.original.json',
        (730, 'dd5749e9605d6b7870f8db99ab91cdd136d456f519f92d3d7424ee2a564c0146'))
    scope_raw = read('successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json',
        (58854, '44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f'))
    scope = json.loads(scope_raw)
    packages = sorted(scope['apps'])
    assert len(packages) == 47 and 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1' in packages
    assert scope['apps']['com.zhubajie.client']['version_code'] == 369
    guard_raw = read('recovery/independent_repair_r2/actual-execute-01/current_baseline_guard.py',
        (3213, 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'))
    guard_pins = next(ast.literal_eval(n.value) for n in ast.parse(guard_raw).body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'PINS' for t in n.targets))
    core_manifest_raw = read('recovery/SOURCE_PINS.json')
    assert sha(core_manifest_raw) == guard_pins['manifest_sha']
    core_pin = json.loads(core_manifest_raw)['files']['successor_runtime.py']
    read('recovery/successor_runtime.py', (core_pin['bytes'], core_pin['sha256']))
    baseline_raw = read('recovery/independent_repair_r2/actual-execute-01/baseline.private.json')
    assert sha(baseline_raw) == guard_pins['baseline']['sha256']
    assert json.loads(baseline_raw)['runtime_epoch_sha256'] == scope['runtime_epoch_sha256']
    read('successor_audit_requests/actual/batches-final-r1/batch-12/artifact.original.json',
        (167063, '29b47ba3639c5964a6b7ee0ac802706ed6dfe4a2aa87dcfcb7e2a20bb1233709'))
    read('successor_audit_requests/actual/permissions-fixed45-r1/batch-02/gate-status.stdout.original.json',
        (3152, 'd2ab87f1aa7674003db63a588e650431d7b3c147b59852fd23c8f5a8790dabc8'))
    s38_raw = read('official_source_scripts/s38_szzc_operator_signature/actual/stdout.original.json',
        (25448, '3ba6894d1d084f8d95b4ebfb342a3710990ce3b0aadf0e17710e9f608f8228a6'))
    s38 = json.loads(s38_raw)
    signature_parser = definitions(s43_source)['parse_signature']
    namespace = {'re': re}
    exec(signature_parser, namespace)
    wrong_signature = namespace['parse_signature'](s38['commands'][0]['stdout_original_utf8'].encode(), s38['commands'][0])
    assert wrong_signature['verified'] is True and wrong_signature['signer_certificate_sha256'] != [
        '556246aaaf05f61c8bbb9587dfc0660e01f6c3c6813ec038d18684d3ab378bbe']

    s43_ref = {'path': S43_HOST_ROOT + '/result.json', 'bytes': len(s43_raw), 'sha256': sha(s43_raw)}
    request = {'schema': 'pocket4-successor-single-native-upgrade-v1',
        'guard': {'path': guard_pins['root'] + '/current_baseline_guard.py', 'bytes': len(guard_raw), 'sha256': sha(guard_raw)},
        'app_scope': {'path': SCOPE_PATH, 'bytes': len(scope_raw), 'sha256': sha(scope_raw)},
        'package': 'com.zhubajie.client', 'official_verifier': s43_ref,
        'verifier_terminal': {'path': INPUT_ROOT + '/verifier-terminal.raw.json', 'bytes': len(terminal_raw), 'sha256': sha(terminal_raw)},
        'output_root': OUTPUT_ROOT,
        'coordination': {'unresolved_native_install_jobs': [], 'single_coordinator': True}}
    constants = {
        'ZBJ_PACKAGE': request['package'], 'ZBJ_VENDOR_SIGNER': s43['candidate_signature_observation']['signer_certificate_sha256'][0],
        'REVIEWED_EXPLICIT_PACKAGES': tuple(packages), 'REVIEWED_ZBJ_REQUEST': request,
        'S43_RESULT_REFERENCE': s43_ref, 'S43_JOB_ID': terminal['job_id'], 'S43_ACTUAL_TERMINAL': terminal,
        'S43_CANDIDATE': s43['candidate'], 'S43_MANIFEST': s43['candidate_manifest_observation'],
        'S43_HELD_INPUT_BINDINGS': s43['held_input_bindings'], 'S43_STREAM_PINS': stream_pins,
        'S43_COMMAND_ARGV': {c['name']: c['argv'] for c in s43['commands']},
        'ZBJ_OFFICIAL_URL': s43['download_reference']['official_url']}
    const_text = '\n'.join(k + ' = ' + repr(v) for k, v in constants.items()) + '\n\n'
    functions_raw = read(str((HERE / 'qualification_functions.py').relative_to(ROOT)))
    worker = replace_once(parent,
        " 'com.ss.android.ugc.aweme':('imtt.dd.qq.com',),\n}",
        " 'com.ss.android.ugc.aweme':('imtt.dd.qq.com',),\n 'com.zhubajie.client':('s.shouji.qihucdn.com',),\n}")
    worker = replace_once(worker, 'def verifier(core,request):\n', const_text + functions_raw.decode() +
        "\n\ndef verifier(core,request):\n    if request['package'] == ZBJ_PACKAGE:\n        return zbj_s43_verifier(core,request)\n")
    worker = replace_once(worker,
        "    need(request['coordination']=={'unresolved_native_install_jobs':[],'single_coordinator':True},\n         'NO_UNSETTLED_NATIVE_INSTALL_ALLOWED')\n",
        "    need(request['coordination']=={'unresolved_native_install_jobs':[],'single_coordinator':True},\n         'NO_UNSETTLED_NATIVE_INSTALL_ALLOWED')\n    need(request == REVIEWED_ZBJ_REQUEST, 'THIS_REVISION_ONLY_EXACT_REVIEWED_ZBJ_REQUEST')\n")
    worker = replace_once(worker,
        "        need(scope['schema']=='pocket4-versioned-app-scope-v1' and scope['runtime_epoch_sha256']==baseline['runtime_epoch_sha256']\n             and request['package']in scope['apps'] and MEITUAN in scope['apps'] and len(scope['apps'])==46,\n             'CURRENT_COMPLETE_REVIEWED_APP_SCOPE_REQUIRED')\n",
        "        qualify_explicit47_scope(scope,baseline['runtime_epoch_sha256'])\n")
    worker = replace_once(worker,
        'Revision 2 additionally retains the exact reviewed JD base/split predecessor set. No UI, grants, launch, task claims, ADB, lifecycle or automatic retry.',
        'Revision 3 admits one exact ZBJ request using actual S43 and explicit47. The r2 JD predecessor logic remains unchanged. No UI, grants, launch, task claims, ADB, lifecycle or automatic retry.')
    compile(worker, 'install_successor_native.py', 'exec')
    before_defs, after_defs = definitions(parent), definitions(worker)
    modified = [name for name in before_defs if before_defs[name] != after_defs[name]]
    assert modified == ['verifier', 'validate_request', 'run'], modified
    unchanged = [name for name in before_defs if name not in modified]
    assert all(before_defs[name] == after_defs[name] for name in unchanged)
    worker_pin = put('install_successor_native.py', worker)
    assert worker_pin['bytes'] < 100000

    fixtures = {'s43-result.original.json': s43_raw, 's43-terminal.original.json': terminal_raw,
                's42-failed-result.original.json': failed_s42_raw, 'scope47.original.json': scope_raw}
    fixture_pins = {name: {k:v for k,v in put(name,raw).items() if k != 'path'} for name,raw in fixtures.items()}
    test_body = read(str((HERE / 'test_body.py').relative_to(ROOT))).decode()
    tests = 'import sys\nsys.dont_write_bytecode=True\nFIXTURE_PINS = ' + repr(fixture_pins) + '\n'
    tests += 'WRONG_VENDOR_ACTUAL_SIGNATURE = ' + repr(wrong_signature) + '\n'
    tests += 'WRONG_VENDOR_ACTUAL_SOURCE = ' + repr({'bytes':len(s38_raw),'sha256':sha(s38_raw),
        'path':'official_source_scripts/s38_szzc_operator_signature/actual/stdout.original.json'}) + '\n\n' + test_body
    put('test_install_successor_r3_zbj.py', tests)
    compile(tests, 'test_install_successor_r3_zbj.py', 'exec')
    cp = subprocess.run([sys.executable, '-I', '-B', str(HERE / 'test_install_successor_r3_zbj.py')],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    put('local-controls.stdout.original.json', cp.stdout)
    put('local-controls.stderr.original.txt', cp.stderr)
    assert cp.returncode == 0, cp.stderr.decode()
    control_result = json.loads(cp.stdout)
    assert control_result['ok'] and all(c['pass'] is True for c in control_result['checks'])
    assert control_result['runtime_worker_called'] is False and control_result['actual_host_child_spawns'] == 0

    names = ['install_successor_native.py', 'test_install_successor_r3_zbj.py'] + list(fixtures)
    stage = replace_once(stage_parent, "ROOT='/home/alex/work/pocket4-successor-install-source-20261106-r2'",
                         'ROOT=' + repr(SOURCE_HOST_ROOT))
    stage = replace_once(stage, "NAMES={'install_successor_native.py','test_install_successor_r2.py'}",
        'NAMES={' + ','.join(repr(name) for name in sorted(names)) + '}')
    stage = replace_once(stage,
        "        raw=content.encode();result['files'][name]=write(d,name,raw);compile(raw,ROOT+'/'+name,'exec')",
        "        raw=content.encode();result['files'][name]=write(d,name,raw)\n        if name.endswith('.py'):compile(raw,ROOT+'/'+name,'exec')")
    stage = replace_once(stage, "for name in ('test_install_successor_r2.py',):", "for name in ('test_install_successor_r3_zbj.py',):")
    stage = stage.replace('pocket4-installer-revision2-source-host-controls-v1', 'pocket4-installer-revision3-zbj-source-host-controls-v1')
    stage = stage.replace('pocket4-installer-revision2-source-prep-v1', 'pocket4-installer-revision3-zbj-source-prep-v1')
    put('stage_source.py', stage)
    compile(stage, 'stage_source.py', 'exec')
    assert definitions(stage_parent) == definitions(stage), 'original stage helper bodies changed'
    host_worker_pin = {'path': SOURCE_HOST_ROOT + '/install_successor_native.py',
                       'bytes': worker_pin['bytes'], 'sha256': worker_pin['sha256']}
    source_line = next(line for line in outer_parent.splitlines() if line.startswith('SOURCE = '))
    outer = replace_once(outer_parent, source_line, 'SOURCE = ' + repr(host_worker_pin))
    assert definitions(outer_parent) == definitions(outer), 'outer stage helper bodies changed'
    put('stage_request_and_invoke_r3_zbj.py', outer)
    compile(outer, 'stage_request_and_invoke_r3_zbj.py', 'exec')

    payload = {'files':{name:(HERE/name).read_text() for name in sorted(names)}, 'stager_source':stage}
    payload_raw = encoded(payload)
    assert len(payload_raw) <= 1048576
    put('stage-payload.json', payload_raw)
    source_process = {'host':'pocket4','executable':'/usr/bin/sudo',
        'args':['-n','/usr/bin/python3','-I','-B','-c',stage], 'cwd':'/home/alex/work','stdin':payload_raw.decode(),
        'idempotency_key':'pocket4-zbj-successor-installer-source-r3-stage-01-20261106',
        'timeout_seconds':180,'cpu_quota_percent':100,'memory_max_bytes':536870912,'nice':10}
    put('exact-stage-process-request.json', encoded(source_process))
    request_raw = encoded(request)
    put('install-request.json', request_raw)
    input_raw = encoded({'input_root':INPUT_ROOT,'request_text':request_raw.decode(),'terminal_text':terminal_raw.decode()})
    assert len(input_raw) <= 131072
    put('install-input.json', input_raw)
    install_process = {'host':'pocket4','executable':'/usr/bin/sudo',
        'args':['-n','/usr/bin/python3','-I','-B','-c',outer], 'cwd':'/home/alex/work','stdin':input_raw.decode(),
        'idempotency_key':'pocket4-successor-zbj-s43-signed-native-upgrade-01-20261106',
        'timeout_seconds':900,'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':10}
    put('exact-install-process-request.review-only.json', encoded(install_process))
    for name,left,right in [('worker-against-r2.diff',parent,worker),('source-stage-against-r2.diff',stage_parent,stage),
                            ('outer-stage-against-r2.diff',outer_parent,outer)]:
        put(name, ''.join(difflib.unified_diff(left.splitlines(True),right.splitlines(True),fromfile='actual-parent-r2',tofile='new-r3-zbj')))
    inherited = {'schema':'pocket4-zbj-r3-source-inheritance-v1','parent_worker':INPUTS[0],
        'modified_existing_worker_functions':modified, 'byte_equal_existing_worker_functions_and_classes':unchanged,
        'new_pure_scope_and_S43_qualifier_functions':['qualify_explicit47_scope','qualify_s43_observation','zbj_s43_verifier'],
        'source_stage_original_helpers_byte_equal':sorted(definitions(stage_parent)),
        'outer_stage_original_helpers_byte_equal':sorted(definitions(outer_parent)),
        'original_request_fields_and_schema_retained':True,'new_revision_whole_request_is_exact_and_ZBJ_only':True,
        'only_run_change':'replace old count-46 gate by exact observed 47 package set and same runtime epoch',
        'old_verifier_body_after_new_ZBJ_dispatch_retained':True,
        'normal_native_install_and_recovery_body_unchanged':True,'legacy_receipt_fabricated':False,
        'S42_actual_FAILED_unchanged':True,'S43_first_root_pin_checker_KeyError_not_reclassified':True,
        'pure_controls':{'returncode':cp.returncode,'checks':len(control_result['checks']),'runtime_worker_called':False,
                         'fresh_runtime_or_app_scope_proved':False},
        'stage_and_install_remote_submissions':0}
    put('source-inheritance.json', encoded(inherited))
    plan = {'schema':'pocket4-zbj-successor-installer-r3-review-plan-v1','state':'SEALED_FOR_ROOT_REVIEW_NOT_SUBMITTED',
        'package':'com.zhubajie.client','historical_installed_reference':{'uid':10144,'version_code':369,'version_name':'9.5.11',
            'kind':'batch12 saved APK evidence; fresh same-identity check mandatory under action lock'},
        'candidate':{'version_code':370,'version_name':'9.5.20','min_sdk':26,'target_sdk':30,'native_abis':['arm64-v8a','armeabi-v7a'],
            'normal_v2_signature':True,'vendor_signer':constants['ZBJ_VENDOR_SIGNER'], 'apk':s43['candidate'], 'actual_s43_result':s43_ref},
        'scope':{'input':request['app_scope'],'packages':packages,'count':47,'resolver_complete_claim':False,
            'new_owned_helper_included':True,'runtime_epoch':scope['runtime_epoch_sha256']},
        'execution_order':['root review exact source/fixture/packet closure',
            'one source-only stage under its stable new key; wait for authoritative durable success and all host controls',
            'root confirms no unresolved native install and serializes Main mutations',
            'one reviewed install request; fresh typed guard and all 47 app identities revalidated under original action lock',
            'retain old base APK; prove private candidate complete using original aapt xmltree gate',
            'one normal native PackageManager update; preserve unknown if mutation attempted without complete success',
            'read back same UID, CE/DE directory identities, vendor signer and exact installed bytes; publish linked new 47 scope',
            'separate versioned scope observation and permissions/business QA; no production or cleanup claim'],
        'necessary_new_scope_and_qualifier_changes':[
            'allow only com.zhubajie.client at the observed official s.shouji.qihucdn.com URL',
            'exact whole request restriction; source-r2 remains available unchanged for its old scope/contracts',
            'explicit S43 schema/actual job/terminal/full-result pin and all six original stream pins',
            'all 13 recorded identities and ns strings preserved; checked decimal-to-Python-int normalization only in memory',
            'exact47 package set replaces old46 count; no fresh resolver completeness inferred'],
        'unchanged_gates':['typed guard and full runtime/process binding','action lock held from before fresh guard until final cleanup',
            'unknown Bili evidence pins','Meituan location projection unchanged; effective grant UNKNOWN',
            'normal native credential/socket/daemon/CLI identity checks','complete single APK XML proof before intent',
            'strictly higher version and fresh current PackageManager signer match',
            'CE/DE identity and target UID retained','retain complete old APK set until final readiness permits exact cleanup',
            'fresh all-non-target identity equality','full candidate stat/hash/path recheck','strict owned child capture/join and FD closure',
            'late-error outcome UNKNOWN; no automatic retry','business_ready and production_ready remain false'],
        'budgets':{'inherited_worker_seconds':700,'inherited_native_install_seconds':260,'inherited_XML_seconds':60,
            'inherited_source_test_seconds':30,'source_stage_outer_seconds':180,'source_stage_memory_bytes':536870912,
            'install_outer_seconds':900,'install_memory_bytes':1073741824,'CPU_percent_each':100,'nice_each':10,
            'outer_profiles_are_new_explicit_reviewed_proposals':True,
            'old_installer_exact_process_envelope_not_in_restored_r2_sources':True},
        'fresh_install_is_not_runtime_QA':{'normal_PackageManager_compatibility_checks_retained':True,
            'host_manifest_min_sdk_ceiling_37_inherited_not_a_new_runtime_property_observation':True,
            'native_ABI_execution_or_translation_proof':'UNKNOWN_PENDING_ACTUAL_APP_QA',
            'no_SDK_ABI_signature_override':True,'no_new_permission_grant':True},
        'permissions_followup':{'old47_permissions_capture_still_bound_to_old_versions':True,
            'batch02_microG_bound_failure_and_STOP_retained':True,'new_scope_does_not_qualify_old_permission_gates':True,
            'fresh_declared_permissions_alone_are_not_effective_permissions':True},
        'preflight_old_plus_new_APK_space_if_current_unchanged_bytes':166858796+166873622+32*1024*1024,
        'framework_RAM_observation_or_build':False,'cleanup_eligible':False,'production_ready':False,
        'remote_submissions_by_this_preparation':0}
    put('execution-plan.json', encoded(plan))
    output_names = sorted(name.name for name in HERE.iterdir() if name.is_file() and
        name.name not in ('SOURCE_PINS.json','DELTA_INDEX.json','local-preparation.exec-result.json'))
    output_pins = []
    for name in output_names:
        raw = (HERE/name).read_bytes();output_pins.append({'path':name,'bytes':len(raw),'sha256':sha(raw)})
    manifest = {'schema':'pocket4-zbj-installer-r3-source-and-evidence-pins-v1','state':'SEALED_FOR_ROOT_REVIEW_NOT_SUBMITTED',
        'inputs':INPUTS,'outputs':output_pins,'host_staged_members':sorted(names),
        'remote_submissions':0,'old_failures_preserved':True}
    manifest_pin = put('SOURCE_PINS.json', encoded(manifest))
    print(json.dumps({'ok':True,'candidate':str(HERE),'manifest':manifest_pin,'worker':worker_pin,
        'controls':len(control_result['checks']),'stage_request':{'bytes':len(encoded(source_process)),'sha256':sha(encoded(source_process))},
        'install_request':{'bytes':len(encoded(install_process)),'sha256':sha(encoded(install_process))},
        'worker_unchanged_definitions':len(unchanged),'modified_definitions':modified,'remote_submissions':0},sort_keys=True))


if __name__ == '__main__':
    main()
