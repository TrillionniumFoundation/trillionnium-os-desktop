"""Fixed original NDK fixture contract. Source only; no Android or OS actions here."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET

PACKAGE = 'com.example.ndk_tests'
RUNNER = PACKAGE+'/android.test.InstrumentationTestRunner'
JAVA_TEST = PACKAGE+'.NdkTests#testMain'
MAIN_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
SCOPE_SCHEMA = 'pocket4-owned-original-ndk-fixture-v1'
REGISTRY = json.loads(r'''["JNI.Ellipsis","JNI.OnLoad","JNI.RegisterNatives","JNI.WrappersABI","ProcSelfMaps.CloseRangeOfOnlyOwnedFdDoesNotKeepMapsAttribution","ProcSelfMaps.ClosedFdAndBadDirfdKeepKernelErrors","ProcSelfMaps.Dup2ReplacementDoesNotKeepMapsAttribution","ProcSelfMaps.DuplicatedAliasesKeepOriginAfterOriginalClose","ProcSelfMaps.ExecutableFromFileBackedMmap","ProcSelfMaps.ExecutableFromMmap","ProcSelfMaps.ExecutableFromMprotect","ProcSelfMaps.ReadlinkHasCanonicalOwnerPath","ProcSelfMaps.ReadlinkLengthAndNoTerminatorSemantics","ProcSelfMaps.ReusedClosedNumberDoesNotKeepMapsAttribution","ProcSelfMaps.SealedLookalikeMemfdIsNotTrustedMaps","ProcSelfMaps.UnwritableBufferReturnsEfaultWithoutAProcessFault","Shared.CallFunction","Shared.DlIteratePhdr","Shared.DlOpen","Shared.DlOpenGreylistedLibrariesAndroidM","Shared.DlOpenSystemLibraries","Shared.DlSym","User.getuid"]''')
FOCUS = json.loads(r'''["ProcSelfMaps.CloseRangeOfOnlyOwnedFdDoesNotKeepMapsAttribution","ProcSelfMaps.ClosedFdAndBadDirfdKeepKernelErrors","ProcSelfMaps.Dup2ReplacementDoesNotKeepMapsAttribution","ProcSelfMaps.DuplicatedAliasesKeepOriginAfterOriginalClose","ProcSelfMaps.ExecutableFromFileBackedMmap","ProcSelfMaps.ExecutableFromMmap","ProcSelfMaps.ExecutableFromMprotect","ProcSelfMaps.ReadlinkHasCanonicalOwnerPath","ProcSelfMaps.ReadlinkLengthAndNoTerminatorSemantics","ProcSelfMaps.ReusedClosedNumberDoesNotKeepMapsAttribution","ProcSelfMaps.SealedLookalikeMemfdIsNotTrustedMaps","ProcSelfMaps.UnwritableBufferReturnsEfaultWithoutAProcessFault"]''')
PENDING_ACTUALS = None
XML_PATH = '/data/data/'+PACKAGE+'/cache/out.xml'
ALL_PACKAGE = ['/system/bin/cmd','package','list','packages','-u','-U','--user','all',PACKAGE]
PACKAGE_STATE = ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]
PACKAGE_PATH = ['/system/bin/cmd','package','path','--user','0',PACKAGE]
OWN_PS = ['/system/bin/ps','-A','-o','UID,PID,NAME']
STACKS = ['/system/bin/cmd','activity','stack','list']
FORCE_STOP = ['/system/bin/am','force-stop','--user','0',PACKAGE]
MAX_PUBLIC_OUTPUT = 262144
MAX_XML = 1048576

def need(value, code):
    if not value:
        raise RuntimeError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def exact_bytes(raw, pin, maximum):
    need(type(raw) is bytes and type(pin) is dict and
         set(pin) == {'bytes','sha256'} and type(pin['bytes']) is int and
         0 < pin['bytes'] <= maximum and len(raw) == pin['bytes'] and
         type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}',pin['sha256']) and
         sha(raw) == pin['sha256'], 'EXACT_WHOLE_ORIGINAL_REQUIRED')
    return json.loads(raw)

def actual_build(raw, pin):
    value = exact_bytes(raw,pin,67108864)
    need(value.get('kind') == 'p4-marriott-real-arm64-ndk-apk-build02' and
         value.get('success') is True and value.get('errors') == [] and
         value.get('all_inputs_unchanged') is True and
         value.get('post_input_errors') == [] and
         value.get('all_tracked_input_FDs_closed') is True and
         value.get('all_children_reaped') is True and
         value.get('Android_actions') == value.get('Main_actions') == 0 and
         value.get('installed') is False and value.get('ARM64_objects_executed') is False and
         value.get('ART_runtime_qualified') is False and value.get('feature_default_enabled') is False,
         'REAL_APK_STATIC_BUILD_ONLY_REQUIRED')
    commands = value.get('commands')
    need(type(commands) is list and len(commands) == 50 and
         all(x.get('returncode') == 0 and x.get('child_started') is True and
             x.get('child_reaped') is True and x.get('timed_out') is False and
             x.get('first_error') is None and x.get('secondary_errors') == [] and
             x.get('pidfd_closed') is True and x.get('output_fds_closed') is True and
             x.get('owned_tree_cleanup_complete') is True and
             x.get('stdout_complete') is True and x.get('stderr_complete') is True
             for x in commands), 'COMPLETE_FIFTY_REAL_COMMANDS_REQUIRED')
    need(len(value.get('objects',[])) == 16 and
         all(x.get('machine') == 183 and x.get('type') == 'REL' and
             x.get('executed') is False for x in value['objects']) and
         len(value.get('linked_libraries',[])) == 7, 'REAL_ARM64_BUILD_CLOSURE_REQUIRED')
    registry = value.get('linked_test_registry',{})
    need(registry.get('expected_count') == 23 and registry.get('expected_focus_count') == 12 and
         set(registry.get('linked_TestBody_symbols',{})) == set(REGISTRY) and
         registry.get('test_execution') is False and
         registry.get('registration_runtime_observed') is False,
         'EXACT_STATIC_23_NOT_RUNTIME_QUALIFICATION')
    contract = value.get('APK_contract',{})
    need(contract.get('package') == PACKAGE and contract.get('min_sdk') == 14 and
         contract.get('target_sdk') == 23 and contract.get('java_classes') == 2 and
         contract.get('instrumentation') == 'android.test.InstrumentationTestRunner' and
         contract.get('SDK_interfaces_packaged') is False and contract.get('runtime_executed') is False and
         contract.get('runtime_must_use_instrumentation_with_nonempty_23_test_list') is True and
         contract.get('Activity_empty_test_list_route_admitted') is False and
         re.fullmatch('[0-9a-f]{64}',contract.get('signature_certificate_sha256','')),
         'ORIGINAL_MANIFEST_SIGNER_AND_NATIVE_PAYLOAD_REQUIRED')
    members = contract.get('native_members',[])
    need(len(members) == 2 and
         {x['member'] for x in members} == {
             'lib/arm64-v8a/libberberis_ndk_tests.so',
             'lib/arm64-v8a/libberberis_ndk_tests_shared_lib.so'} and
         all(type(x.get('bytes')) is int and 0 < x['bytes'] <= 33554432 and
             re.fullmatch('[0-9a-f]{64}',x.get('sha256','')) for x in members),
         'TWO_ACTUAL_ARM64_IMPLEMENTATIONS_REQUIRED')
    artifact = value.get('APK',{})
    need(type(artifact.get('bytes')) is int and 0 < artifact['bytes'] <= 33554432 and
         re.fullmatch('[0-9a-f]{64}',artifact.get('sha256','')) and
         artifact.get('path') ==
         '/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-02-20261106/ndk-tests.apk' and
         artifact.get('resolved_path') == artifact['path'],
         'FIXED_ACTUAL_APK_ARTIFACT_REQUIRED')
    return {'build_result':dict(pin),'APK':artifact,'signer_sha256':contract['signature_certificate_sha256'],
            'native_members':members,'min_sdk':14,'target_sdk':23,'ABI':'arm64-v8a',
            'runtime_qualified':False}

def terminal(raw, pin, job, stdout_bytes):
    value = exact_bytes(raw,pin,32768)
    need(value.get('job_id') == job and value.get('state') == 'succeeded' and
         value.get('exit_code') == 0 and value.get('output_complete') is True and
         value.get('output_durable') is True and value.get('terminal_publication_confirmed') is True and
         value.get('timed_out') is False and value.get('cancelled') is False and
         value.get('automatic_retry') is False and
         value.get('log_bytes') == {'stdout':{'seen':stdout_bytes,'stored':stdout_bytes},
                                   'stderr':{'seen':0,'stored':0}} and
         all(value['log_synced'][k] is True and value['log_truncated'][k] is False and
             value['log_errors'][k] is None for k in ('stdout','stderr')),
         'COMPLETE_INDEPENDENT_TERMINAL_REQUIRED')
    return value

def nonce(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{32}',value) and value != '0'*32,
         'ACTUAL_FRESH_FIXTURE_NONCE_REQUIRED')
    return value

def scope(phase, attempt, build_pin, installed=None):
    need(phase in ('install','run','retire'), 'FIXED_FIXTURE_PHASE_REQUIRED')
    nonce(attempt)
    need(type(build_pin) is dict and re.fullmatch('[0-9a-f]{64}',build_pin.get('sha256','')) and
         type(build_pin.get('bytes')) is int and build_pin['bytes'] > 0,
         'ACTUAL_BUILD_PIN_REQUIRED')
    uid = None
    if phase != 'install':
        need(type(installed) is dict and installed.get('package') == PACKAGE and
             type(installed.get('uid')) is int and 10000 <= installed['uid'] < 100000 and
             installed.get('user') == 0 and installed.get('owned_install_qualified') is True and
             installed.get('Main_epoch') == MAIN_EPOCH and
             installed.get('build_result') == build_pin,
             'ACTUAL_OWN_NDK_INSTALLATION_REQUIRED')
        uid = installed['uid']
    else:
        need(installed is None, 'INSTALL_CANNOT_ADOPT_OLD_UID_OR_SCOPE')
    return {'schema':SCOPE_SCHEMA,'phase':phase,'package':PACKAGE,'uid':uid,'user':0,
            'attempt_nonce':attempt,'Main_epoch':MAIN_EPOCH,'baseline_sha256':BASELINE_SHA,
            'qualification_sha256':QUALIFICATION_SHA,'build_result':dict(build_pin),
            'commercial_App_scope_inherited':False,'automatic_retry':False}

def validate_scope(value):
    need(type(value) is dict and set(value) == {
        'schema','phase','package','uid','user','attempt_nonce','Main_epoch',
        'baseline_sha256','qualification_sha256','build_result',
        'commercial_App_scope_inherited','automatic_retry'} and
        value['schema'] == SCOPE_SCHEMA and value['phase'] in ('install','run','retire') and
        value['package'] == PACKAGE and type(value['user']) is int and value['user'] == 0 and
        value['Main_epoch'] == MAIN_EPOCH and value['baseline_sha256'] == BASELINE_SHA and
        value['qualification_sha256'] == QUALIFICATION_SHA and
        value['commercial_App_scope_inherited'] is False and value['automatic_retry'] is False,
        'FIXED_CURRENT_NDK_SCOPE_REQUIRED')
    nonce(value['attempt_nonce'])
    need((value['phase'] == 'install' and value['uid'] is None) or
         (value['phase'] != 'install' and type(value['uid']) is int and
          10000 <= value['uid'] < 100000), 'UID_MUST_BE_UNALLOCATED_OR_ACTUALLY_BOUND')
    pin=value['build_result']
    need(type(pin) is dict and set(pin) == {'bytes','sha256'} and
         type(pin['bytes']) is int and 0 < pin['bytes'] <= 67108864 and
         type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}',pin['sha256']),
         'EXACT_ACTUAL_BUILD_PIN_IN_SCOPE_REQUIRED')
    return value

def installation_plan(value, guest_apk):
    validate_scope(value)
    need(value['phase'] == 'install' and guest_apk ==
         '/data/local/tmp/p4-ndk-'+value['attempt_nonce']+'/owned-ndk-fixture.apk',
         'EXACT_FRESH_STAGE_PATH_REQUIRED')
    # No -r replacement, -g grant, low-target-SDK bypass, launch or instrumentation.
    return [
        (ALL_PACKAGE,8,False),
        (['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',PACKAGE,guest_apk],40,True),
        (PACKAGE_STATE,8,False),(PACKAGE_STATE,8,False),(PACKAGE_PATH,8,False),
        (['/system/bin/dumpsys','package',PACKAGE],12,False),
        (ALL_PACKAGE,8,False),(OWN_PS,8,False),
    ]

def instrumentation_argv():
    need(len(REGISTRY) == len(set(REGISTRY)) == 23 and len(FOCUS) == len(set(FOCUS)) == 12 and
         set(FOCUS) == {x for x in REGISTRY if x.startswith('ProcSelfMaps.')},
         'FIXED_COMPLETE_ORIGINAL_REGISTRY_REQUIRED')
    return ['/system/bin/am','instrument','-w','-r','--user','0',
            '-e','class',JAVA_TEST,
            '-e','atf-gtest-list',':'.join(REGISTRY),
            '-e','atf-gtest-filter','ProcSelfMaps.*',RUNNER]

def run_plan(value):
    validate_scope(value)
    need(value['phase'] == 'run', 'RUN_PHASE_REQUIRED')
    # Run context has no force-stop capability. Its outcome is preserved before
    # the independently qualified retirement context opens its own plan.
    return [(PACKAGE_STATE,8,False),(PACKAGE_PATH,8,False),(OWN_PS,8,False),(STACKS,8,False),
            (instrumentation_argv(),60,True)]

def retirement_plan(value):
    validate_scope(value)
    need(value['phase'] == 'retire', 'RETIREMENT_REQUIRES_NEW_SCOPE')
    # One fixed stop, followed by two distinct complete empty-UID observations.
    # The two samples do not prove a future interval free of processes.
    return [(PACKAGE_STATE,8,False),(PACKAGE_PATH,8,False),
            (FORCE_STOP,12,True),(OWN_PS,8,False),(OWN_PS,8,False),
            (STACKS,8,False),(PACKAGE_PATH,8,False),(PACKAGE_STATE,8,False)]

def package_absent(raw):
    need(type(raw) is bytes and raw == b'', 'PREEXISTING_NDK_PACKAGE_MUST_NOT_BE_REPLACED')
    return {'all_users_package_absent':True,'uninstalled_records_absent':True}

def package_metadata(raw, protected_uids):
    need(type(raw) is bytes and len(raw) <= 4096 and type(protected_uids) is set and
         all(type(x) is int for x in protected_uids), 'EXACT_METADATA_INPUT_REQUIRED')
    match = re.fullmatch(re.escape('package:'+PACKAGE)+r' versionCode:([0-9]+) uid:([0-9]+)\n',
                         raw.decode('utf-8','strict'))
    need(match is not None, 'EXACT_NDK_PACKAGE_UID_VERSION_ROW_REQUIRED')
    version,uid = map(int,match.groups())
    need(10000 <= uid < 100000 and uid not in protected_uids,
         'NEW_UID_CANNOT_ALIAS_BASELINE_PACKAGES')
    return {'package':PACKAGE,'uid':uid,'user':0,'version_code':version}

def package_path(raw):
    need(type(raw) is bytes and len(raw) <= 4096, 'ONE_APK_PATH_BOUND')
    text = raw.decode('utf-8','strict')
    match = re.fullmatch(r'package:(/data/app/[A-Za-z0-9_./~+=-]+/base[.]apk)\n',text)
    need(match is not None,'ONE_EXACT_INSTALLED_NDK_APK_REQUIRED')
    path = match[1]
    need(all(part not in ('','.','..') for part in path[1:].split('/')) and
         '/'+PACKAGE+'-' in path, 'EXACT_OWN_PACKAGE_INSTALL_PATH_REQUIRED')
    return path

def package_abi(raw):
    need(type(raw) is bytes and len(raw) <= MAX_PUBLIC_OUTPUT,'OWN_PACKAGE_DUMP_BOUND')
    text = raw.decode('utf-8','strict')
    primary = re.findall(r'^\s*primaryCpuAbi=([^\s]+)\s*$',text,re.M)
    need(primary == ['arm64-v8a'], 'ACTUAL_INSTALLED_ARM64_ABI_REQUIRED')
    return {'primaryCpuAbi':'arm64-v8a','original_bytes':len(raw),'original_sha256':sha(raw),
            'other_package_dump_content_exported':False}

def own_processes(raw, uid):
    need(type(raw) is bytes and len(raw) <= MAX_PUBLIC_OUTPUT and
         type(uid) is int and 10000 <= uid < 100000,'BOUND_OWN_UID_PS_REQUIRED')
    lines = raw.decode('utf-8','strict').splitlines()
    need(lines and lines[0].split() == ['UID','PID','NAME'] and len(lines) <= 4097,
         'BOUNDED_FIXED_NUMERIC_PROCESS_TABLE_REQUIRED')
    selected = []
    seen = set()
    for line in lines[1:]:
        fields=line.split(None,2)
        need(len(fields)==3 and fields[0].isdecimal() and fields[1].isdecimal(),
             'PROCESS_TABLE_SCHEMA_CHANGED')
        row_uid,pid=int(fields[0]),int(fields[1])
        need(pid > 0 and pid not in seen, 'DUPLICATE_PROCESS_TABLE_PID')
        seen.add(pid)
        if row_uid == uid:
            need(len(selected)<16 and fields[2] == PACKAGE,
                 'OWN_FIXTURE_HAS_UNEXPECTED_PROCESS')
            selected.append({'uid':uid,'namespace_pid':pid,'name':PACKAGE})
    return {'own_processes':selected,'own_count':len(selected),
            'other_process_rows_exported':False,'original_bytes':len(raw),'original_sha256':sha(raw),
            'kernel_process_identity_or_pidfd_qualification':False}

def instrumentation_result(raw):
    need(type(raw) is bytes and len(raw) <= MAX_PUBLIC_OUTPUT,'FIXED_INSTRUMENTATION_OUTPUT_BOUND')
    text=raw.decode('utf-8','strict')
    need(re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\r?$',text,re.M) == ['-1'] and
         re.findall(r'^INSTRUMENTATION_STATUS_CODE: (-?[0-9]+)\r?$',text,re.M) == ['1','0'] and
         re.findall(r'^INSTRUMENTATION_STATUS: class=(.*)\r?$',text,re.M) ==
             [PACKAGE+'.NdkTests',PACKAGE+'.NdkTests'] and
         re.findall(r'^INSTRUMENTATION_STATUS: test=(.*)\r?$',text,re.M) == ['testMain','testMain'] and
         not re.search(r'^INSTRUMENTATION_(?:FAILED|ABORTED):',text,re.M),
         'ONE_ORIGINAL_JAVA_TEST_MUST_COMPLETE_SUCCESSFULLY')
    return {'Java_test':JAVA_TEST,'status_codes':[1,0],'final_code':-1,
            'original_bytes':len(raw),'original_sha256':sha(raw),
            'output_text_exported':False,'native_XML_still_required':True}

def native_xml(raw):
    need(type(raw) is bytes and 0<len(raw)<=MAX_XML and
         b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),
         'BOUNDED_ENTITY_FREE_OWN_XML_REQUIRED')
    root=ET.fromstring(raw)
    root_keys={'tests','failures','disabled','errors','time','timestamp','name'}
    need(root.tag=='testsuites' and set(root.attrib)==root_keys and
         root.attrib['name']=='AllTests' and root.attrib['tests']=='12' and
         all(root.attrib[k]=='0' for k in ('failures','disabled','errors')),
         'TWELVE_SUCCESSFUL_NATIVE_TESTS_REQUIRED')
    suites=list(root)
    need(len(suites)==1 and suites[0].tag=='testsuite','EXACT_PROC_MAPS_SUITE_REQUIRED')
    suite=suites[0]
    need(set(suite.attrib)=={'name','tests','failures','disabled','skipped','errors','time','timestamp'} and
         suite.attrib['name']=='ProcSelfMaps' and suite.attrib['tests']=='12' and
         all(suite.attrib[k]=='0' for k in ('failures','disabled','skipped','errors')),
         'NO_FAILED_ERRORED_DISABLED_OR_SKIPPED_TEST_ALLOWED')
    found=[]
    for case in suite:
        need(case.tag=='testcase' and set(case.attrib)=={
             'name','file','line','status','result','time','timestamp','classname'} and
             case.attrib['classname']=='ProcSelfMaps' and case.attrib['status']=='run' and
             case.attrib['result']=='completed' and len(case)==0 and
             (case.text is None or not case.text.strip()),
             'EXACT_COMPLETED_TESTCASE_REQUIRED')
        name='ProcSelfMaps.'+case.attrib['name']
        need(name in FOCUS and name not in found,'UNEXPECTED_OR_DUPLICATE_TESTCASE')
        found.append(name)
    need(len(found)==12 and set(found)==set(FOCUS),'EXACT_TWELVE_TESTCASE_SET_REQUIRED')
    return {'native_test_names':sorted(found),'tests':12,'failures':0,'errors':0,'skipped':0,
            'disabled':0,'original_bytes':len(raw),'original_sha256':sha(raw),
            'raw_XML_or_failure_body_exported':False,
            'freshness_and_same_owned_UID_binding_still_required':True}

def pending_gate():
    need(PENDING_ACTUALS is not None,'SOURCE_ONLY_ACTUAL_APK_INSTALL_UID_NONCES_UNBOUND')
    raise RuntimeError('SOURCE_ONLY_NO_RUNTIME_BINDER_OR_DISPATCH_REQUEST')

if __name__ == '__main__':
    pending_gate()
