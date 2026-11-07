"""Fixed original NdkTests run and independent retirement worker.
SOURCE_ONLY until complete actual controls and two dedicated phase nonces are
bound externally. Each invocation enters one phase, one fresh root and one lease.
The already completed install is an immutable input, never replayed here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import types

PENDING_BINDING = None
PHASE_ROOTS = {
    'run':Path('/home/alex/work/pocket4-original-ndk-fixture-APK05-run-01'),
    'retire':Path('/home/alex/work/pocket4-original-ndk-fixture-APK05-retire-01'),
}
PHASE_STEPS = {'run':'run-01','retire':'retire-01'}
WORK_SECONDS = 175.0
RESULT_LIMIT = 1048576
PACKAGE = 'com.example.ndk_tests'
BUILD_REPORT = '/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-05-20261106/build-result.json'
BUILD_REPORT_PIN = {'bytes':9811685,'sha256':'d8eb53c924fa6a76bee19304bd8538bf2a57306b7e9bd6a55df8787d4ea33411'}
INSTALL_RESULT = '/home/alex/work/pocket4-original-ndk-fixture-APK05-install-02/result.json'
INSTALL_SOURCE_PIN = {'bytes':1054,'sha256':'684209fb84cf81921a1c65e8c52c7bf95db87ca0167d46badf8a8d974a2ba237'}
INSTALL_NONCE = '06a571251aa6fcc77591494edda1f801'
SOURCE_NAMES = {
    'fixture_contract.py','fixture_context.py','fixture_transport.py',
    'fixture_phases.py','current_discovery.py','phase_lease.py','phase_worker.py',
}
REFERENCE_PINS = json.loads(r'''{"static-build.original.json":{"bytes":4893,"sha256":"c59318c119e43afc810debc6dbfd7367d37f1f9c154313572f732cc645124bae"},"build-terminal.original.json":{"bytes":729,"sha256":"7df30068ee3849645f69085f9c16f1bc1094744fbacc26d765a09be0c21ded3d"},"build-stdout.original.json":{"bytes":228,"sha256":"7e22891b785542a355a55f67b2235180d1dd216d176871338e88ebd6a2d706f6"},"readonly38.original.json":{"bytes":6407,"sha256":"7ff0ed239e77335b04c1b4197eab194ed108d75d2deff8673185a3ee0c7d5256"},"readonly38-terminal.original.json":{"bytes":731,"sha256":"8f02badd8c546fb2aba3e58a2ceab3f23d99811d8c1e6e142d92d1f93b3ad804"},"install-result.original.json":{"bytes":11271,"sha256":"e17df04e2eda0e0f489ec6fee992bcca2c5ae1fd584e9fc4e57a20334fb16143"},"install-summary.original.json":{"bytes":455,"sha256":"8910ed011d65439e3e7d315e4b8f31b928ee892427fa0c8a5789eea5ae823d19"},"install-terminal.original.json":{"bytes":729,"sha256":"80e7fce35bfa39535e0fa0513d10f3e2d4f9e0bfba6a618a0c17426f249951bf"},"global924.original.json":{"bytes":35115,"sha256":"8a718803f7dc905e5c92c3609164c19caf1b213d88b235511554e39403568e25"}}''')
ENTRY_CONTROL_KIND = 'pocket4-original-ndk-runtime-entry-controls01'
ENTRY_CONTROL_COUNTS = {'fixture':38,'manifest':4,'lease':12,'wiring':6}

def need(value, code):
    if not value:
        raise RuntimeError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def load_source(raw, path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    return value

def body(row, maximum):
    need(type(row) is dict and set(row) == {'body','bytes','sha256'} and
         type(row['body']) is str and type(row['bytes']) is int and
         0 < row['bytes'] <= maximum and
         type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),
         'FIXED_PACKET_MEMBER_SHAPE_REQUIRED')
    raw = row['body'].encode()
    need(len(raw) == row['bytes'] and sha(raw) == row['sha256'],
         'FIXED_PACKET_MEMBER_WHOLE_HASH_CHANGED')
    return raw


def check_binding(binding, packet):
    # Complete actual input and source qualification precedes all Main/OS reads.
    need(binding is not None, 'SOURCE_ONLY_RUNTIME_ACTUAL_BINDING_UNBOUND')
    need(type(binding) is dict and set(binding) == {
        'schema','kind','phase','root','source_manifest','entry_controls',
        'entry_controls_terminal','entry_controls_job','entry_controls_stdout_bytes',
        'nonce_material','nonce_terminal','nonce_job','nonce_stdout_bytes',
        'prior_run'} and binding['schema'] == 1 and
        binding['kind'] == 'pocket4-original-ndk-runtime-binding-v1' and
        binding['phase'] in PHASE_ROOTS and
        binding['root'] == str(PHASE_ROOTS[binding['phase']]),
        'EXACT_FIXED_RUNTIME_PHASE_BINDING_REQUIRED')
    phase = binding['phase']
    root = PHASE_ROOTS[phase]
    need(type(packet) is dict and set(packet) == {'schema','sources','manifest','references'} and
         packet['schema'] == 1 and type(packet['sources']) is dict and
         set(packet['sources']) == SOURCE_NAMES, 'FIXED_SEVEN_PHASE_SOURCE_PACKET_REQUIRED')
    sources = {name:body(row,131072) for name,row in packet['sources'].items()}
    manifest_raw = body(packet['manifest'],65536)
    pin = {'bytes':len(manifest_raw),'sha256':sha(manifest_raw)}
    need(pin == binding['source_manifest'], 'EXTERNAL_RUNTIME_SOURCE_MANIFEST_CHANGED')
    manifest = json.loads(manifest_raw)
    need(manifest.get('schema') == 'pocket4-original-ndk-fixture-source-v1' and
         set(manifest.get('files',{})) == SOURCE_NAMES and
         all(manifest['files'][name] == {'bytes':len(raw),'sha256':sha(raw)}
             for name,raw in sources.items()), 'EXACT_SEVEN_WHOLE_PHASE_BODIES_REQUIRED')
    expected = set(REFERENCE_PINS) | {
        'entry-controls.original.json','entry-controls-terminal.original.json',
        'phase-nonce.original.json','phase-nonce-terminal.original.json'}
    if phase == 'retire':
        expected |= {'run-result.original.json','run-summary.original.json','run-terminal.original.json'}
    need(type(packet['references']) is dict and set(packet['references']) == expected,
         'EXACT_PHASE_REFERENCE_SET_REQUIRED')
    refs = {}
    for name,pinned in REFERENCE_PINS.items():
        raw = body(packet['references'][name],131072)
        need({'bytes':len(raw),'sha256':sha(raw)} == pinned, 'ACTUAL_PHASE_REFERENCE_PIN_CHANGED')
        refs[name] = raw
    fixture = load_source(sources['fixture_contract.py'],root/'source'/'fixture_contract.py',
                          'fixed_runtime_ndk_contract')
    for name,pin_name in (
            ('entry-controls.original.json','entry_controls'),
            ('entry-controls-terminal.original.json','entry_controls_terminal'),
            ('phase-nonce.original.json','nonce_material'),
            ('phase-nonce-terminal.original.json','nonce_terminal')):
        raw = body(packet['references'][name],262144)
        need({'bytes':len(raw),'sha256':sha(raw)} == binding[pin_name],
             'EXACT_ACTUAL_PHASE_MATERIAL_PIN_REQUIRED')
        refs[name] = raw
    fixture.terminal(refs['entry-controls-terminal.original.json'],
        binding['entry_controls_terminal'],binding['entry_controls_job'],
        binding['entry_controls_stdout_bytes'])
    entry = json.loads(refs['entry-controls.original.json'])
    need(len(refs['entry-controls.original.json']) == binding['entry_controls_stdout_bytes'] and
         entry.get('kind') == ENTRY_CONTROL_KIND and entry.get('ok') is True and
         entry.get('errors') == [] and entry.get('source_manifest') == pin and
         entry.get('counts') == ENTRY_CONTROL_COUNTS and
         type(entry.get('cases')) is list and len(entry['cases']) == 60 and
         len({x['name'] for x in entry['cases']}) == 60 and
         all(x.get('passed') is True for x in entry['cases']) and
         entry.get('all_owned_control_FDs_closed') is True and
         entry.get('all_owned_control_files_removed') is True and
         entry.get('Main_reads') == entry.get('Android_commands') == entry.get('children') == 0 and
         entry.get('runtime_qualified') is False,
         'SIXTY_ACTUAL_CURRENT_PHASE_SOURCE_CONTROLS_REQUIRED')
    fixture.terminal(refs['phase-nonce-terminal.original.json'],binding['nonce_terminal'],
                     binding['nonce_job'],binding['nonce_stdout_bytes'])
    material = json.loads(refs['phase-nonce.original.json'])
    pool = json.loads(refs['global924.original.json'])
    need(type(pool) is list and len(pool) == len(set(pool)) == 924 and
         pool == sorted(pool) and all(type(x) is str and re.fullmatch('[0-9a-f]{32}',x)
                                      for x in pool),
         'EXACT_GLOBAL924_PHASE_EXCLUSION_REQUIRED')
    need(len(refs['phase-nonce.original.json']) == binding['nonce_stdout_bytes'] and
         material.get('schema') == 1 and
         material.get('kind') == 'pocket4-original-ndk-fixture-run-retire-nonce01' and
         material.get('profile') == 'pocket4-original-ndk-fixture-APK05-run-retire01' and
         material.get('package') == material.get('target_package') == PACKAGE and
         material.get('phase') == 'run_and_independent_retirement' and
         material.get('generator') == 'secrets.token_hex(16)' and
         material.get('requested_count') == material.get('draw_count') == 2 and
         material.get('redraw_attempted') is False and material.get('ok') is True and
         material.get('error') is None and material.get('fresh_against_exact_pool') is True and
         material.get('labels') == ['run_nonce','retire_nonce'] and
         type(material.get('nonces')) is dict and
         set(material['nonces']) == {'run_nonce','retire_nonce'} and
         material.get('exclusion_pool') == {
             'bytes':35115,'count':924,
             'sha256':'8a718803f7dc905e5c92c3609164c19caf1b213d88b235511554e39403568e25',
             'git_blob_sha':'269194afb3b365ca4995f6ff69a2e6539cff6ff7'} and
         material.get('uid') == material.get('gid') == 1000 and
         material.get('Main_reads') == material.get('Android_commands') ==
         material.get('child_processes') == material.get('explicit_filesystem_reads') ==
         material.get('explicit_filesystem_writes') == 0 and
         material.get('standard_library_and_entropy_IO_included_in_counters') is False and
         material.get('runtime_authorized') is False,
         'TWO_ACTUAL_DISTINCT_PHASE_NONCES_REQUIRED')
    run_nonce = fixture.nonce(material['nonces']['run_nonce'])
    retire_nonce = fixture.nonce(material['nonces']['retire_nonce'])
    need(run_nonce != retire_nonce and run_nonce not in pool and retire_nonce not in pool and
         INSTALL_NONCE in pool and 'e4b5a1bdac8be04ff2ea3188a6d946d6' in pool,
         'PHASE_NONCES_CANNOT_REUSE_ANY_ORIGINAL_INSTALL')
    if phase == 'run':
        need(binding['prior_run'] is None, 'RUN_CANNOT_ADOPT_A_PRIOR_RUN_RESULT')
    else:
        prior = binding['prior_run']
        need(type(prior) is dict and set(prior) == {
            'result','summary','terminal','job','stdout_bytes','source_manifest'} and
            type(prior['job']) is str and
            re.fullmatch('[0-9a-f]+-[0-9a-f]{4}-[0-9a-f]{4}',prior['job']),
            'INDEPENDENT_ACTUAL_RUN_BEFORE_RETIREMENT_REQUIRED')
        for name,key,limit in (
            ('run-result.original.json','result',RESULT_LIMIT),
            ('run-summary.original.json','summary',8192),
            ('run-terminal.original.json','terminal',32768)):
            raw = body(packet['references'][name],limit)
            fixture.exact_bytes(raw,prior[key],limit)
            refs[name] = raw
    return sources,manifest_raw,refs,fixture,material['nonces'][phase+'_nonce']


def original_installation(phases, fixture, refs, build):
    pinned = REFERENCE_PINS['install-result.original.json']
    raw = phases.read_exact_file(INSTALL_RESULT,RESULT_LIMIT,pinned)
    need(raw == refs['install-result.original.json'], 'ORIGINAL_INSTALL_RESULT_CHANGED')
    authority = fixture.qualified_installation(raw,pinned,build,INSTALL_SOURCE_PIN)
    value = json.loads(raw)
    fixture.terminal(refs['install-terminal.original.json'],
        REFERENCE_PINS['install-terminal.original.json'],'1a1b2e3bcfa-fc05-8021',455)
    summary = json.loads(refs['install-summary.original.json'])
    need(summary.get('schema') == 1 and
         summary.get('kind') == 'pocket4-original-ndk-install-worker-summary02' and
         summary.get('ok') is True and summary.get('error') is None and
         summary.get('automatic_retry') is False and
         summary.get('original_NdkTests_runtime_qualified') is False and
         summary.get('installed_UID') == authority['installed_tuple']['uid'] and
         summary.get('install_attempted') is True and summary.get('outcome_unknown') is False and
         summary.get('result') == {'path':INSTALL_RESULT,**pinned,
                                  'result_file_and_parent_FDs_closed':True},
         'EXACT_SUCCESSFUL_INSTALL_SUMMARY_REQUIRED')
    need(value.get('entry_kind') == 'pocket4-original-ndk-install-worker02' and
         value.get('all_seven_sources_unchanged') is True and
         value.get('actual_build_and_APK_unchanged') is True and
         value.get('Main_before_lock') == value.get('Main_before') ==
         value.get('Main_after') == value.get('Main_after_worker') and
         value.get('ABI',{}).get('primaryCpuAbi') == 'arm64-v8a' and
         value.get('instrumentation_executed') is False and
         value.get('instrumentation_verified') is False and
         value.get('original_NdkTests_runtime_qualified') is False and
         value.get('target_sdk_bypass_used') is False and
         value.get('permission_grants') == value.get('App_launches') == 0 and
         value.get('feature_default_changed') is False and
         value.get('result_emission_pending') is True and
         value.get('independent_terminal_still_required') is True and
         value.get('whole_invocation_resource_observed_by_worker') is False and
         value.get('shared_helper',{}).get('whole_process_tree_cleanup_qualified') is False and
         authority['install_attempt_nonce'] == INSTALL_NONCE,
         'COMPLETE_ACTUAL_INSTALL_WORKER_FENCE_AND_BOUNDARIES_REQUIRED')
    lease = value.get('install_lease',{})
    need(lease.get('root') == str(Path(INSTALL_RESULT).parent) and
         lease.get('step') == str(Path(INSTALL_RESULT).parent/'steps'/'install-02') and
         lease.get('source_manifest') == INSTALL_SOURCE_PIN and
         lease.get('global_action_lock') == '/run/lock/android-digitalis-actions.lock' and
         lease.get('tracked_FD_count') == lease.get('closed_FD_count') == 23 and
         lease.get('global_lock_attempts') == 1 and lease.get('global_lock_busy_attempts') == 0 and
         lease.get('lease_errors') == [] and lease.get('FD_close_failures') == [] and
         all(lease.get(k) is True for k in (
             'root_create_only','root_created','seven_sources_staged','step_claim_create_only',
             'install_phase_entered_once','global_lock_acquired','flow_lock_exclusive',
             'step_lock_exclusive','all_tracked_lease_FDs_closed',
             'global_action_lock_released','flow_lock_released','step_lock_released')) and
         lease.get('global_ambient_FD_equality_asserted') is False and
         lease.get('recursive_cleanup') is False, 'ACTUAL_INSTALL_LOCKS_AND_FD_CLOSURE_REQUIRED')
    return authority


def prior_run(phases, fixture, refs, binding, installation, phase_material):
    if binding['phase'] == 'run':
        return None
    pinned = binding['prior_run']
    value = fixture.exact_bytes(refs['run-result.original.json'],pinned['result'],RESULT_LIMIT)
    path = str(PHASE_ROOTS['run']/'result.json')
    raw = phases.read_exact_file(path,RESULT_LIMIT,pinned['result'])
    need(raw == refs['run-result.original.json'], 'EXACT_PRIOR_RUN_FILE_CHANGED')
    terminal = fixture.exact_bytes(refs['run-terminal.original.json'],pinned['terminal'],32768)
    need(terminal.get('job_id') == pinned['job'] and
         ((terminal.get('state'),terminal.get('exit_code')) in
          (('succeeded',0),('failed',1))) and
         terminal.get('timed_out') is False and terminal.get('cancelled') is False and
         terminal.get('automatic_retry') is False and terminal.get('output_complete') is True and
         terminal.get('output_durable') is True and
         terminal.get('terminal_publication_confirmed') is True and
         terminal.get('log_bytes') == {
             'stdout':{'seen':pinned['stdout_bytes'],'stored':pinned['stdout_bytes']},
             'stderr':{'seen':0,'stored':0}} and
         all(terminal['log_synced'][k] is True and terminal['log_truncated'][k] is False and
             terminal['log_errors'][k] is None for k in ('stdout','stderr')),
         'PRIOR_RUN_MUST_HAVE_AN_INDEPENDENT_COMPLETE_TERMINAL')
    summary = fixture.exact_bytes(refs['run-summary.original.json'],pinned['summary'],8192)
    fixture.validate_scope(value.get('scope'))
    need(value.get('schema') == 1 and value.get('kind') == 'pocket4-original-ndk-fixture-run-v1' and
         value.get('entry_kind') == 'pocket4-original-ndk-runtime-worker01' and
         value.get('source_manifest') == pinned['source_manifest'] and
         value['scope']['phase'] == 'run' and
         value['scope']['attempt_nonce'] == phase_material['nonces']['run_nonce'] and
         value['scope']['uid'] == installation['installed_tuple']['uid'] and
         value['scope']['build_result'] == BUILD_REPORT_PIN and
         value.get('install_result') == installation['install_result'] and
         value.get('installed_before') == installation['installed_tuple'] and
         value.get('instrumentation_attempted') is True and value.get('retirement_required') is True and
         value.get('held_binding_released') is True and value.get('automatic_retry') is False and
         type(value.get('exact_command_count')) is int and 0 <= value['exact_command_count'] <= 5 and
         type(value.get('ok')) is bool and
         type(value.get('secondary_errors')) is list and
         value.get('native_twelve_tests_qualified') is False and
         value.get('original_NdkTests_runtime_qualified') is False and
         value.get('commercial_App_readiness_qualified') is False and
         value.get('Main_deployment_or_restart') is False,
         'ACTUAL_SAME_OWN_INSTALLATION_RUN_REQUIRES_INDEPENDENT_RETIREMENT')
    need(type(summary) is dict and summary.get('schema') == 1 and
         summary.get('kind') == 'pocket4-original-ndk-runtime-worker-summary01' and
         summary.get('phase') == 'run' and summary.get('ok') == value['ok'] and
         summary.get('error') == value.get('error') and
         summary.get('outcome_unknown') == value.get('outcome_unknown') and
         summary.get('automatic_retry') is False and
         summary.get('installed_UID') == installation['installed_tuple']['uid'] and
         summary.get('original_NdkTests_runtime_qualified') is False and
         summary.get('result') == {'path':path,**pinned['result'],
                                  'result_file_and_parent_FDs_closed':True},
         'EXACT_PRIOR_RUN_SUMMARY_REQUIRED')
    if value['ok']:
        need(value.get('error') is None and value.get('secondary_errors') == [] and
             terminal.get('exit_code') == 0 and value.get('outcome_unknown') is False and
             value.get('instrumentation_verified') is True and
             value.get('exact_command_count') == 5 and
             value.get('current_Main_after_qualified') is True,
             'SUCCESSFUL_PRIOR_RUN_CANNOT_HIDE_FAILURE')
    else:
        need(value.get('error') is not None and terminal.get('exit_code') == 1,
             'FAILED_PRIOR_RUN_FIRST_ERROR_MUST_BE_PRESERVED')
    # A failed/unknown run may still authorize only this owned retirement. It
    # can never satisfy the final original_NdkTests_testMain_accepted condition.
    return value

def original_build(phases, fixture, refs):
    raw = phases.read_exact_file(BUILD_REPORT,67108864,BUILD_REPORT_PIN)
    build = fixture.actual_build(raw,BUILD_REPORT_PIN)
    fixture.terminal(refs['build-terminal.original.json'],
        REFERENCE_PINS['build-terminal.original.json'],'1a1b299fafc-fc05-7edb',228)
    summary = json.loads(refs['build-stdout.original.json'])
    binding = json.loads(refs['static-build.original.json'])
    need(summary.get('success') is True and summary.get('path') == BUILD_REPORT and
         summary.get('bytes') == BUILD_REPORT_PIN['bytes'] and
         summary.get('sha256') == BUILD_REPORT_PIN['sha256'],
         'EXACT_BUILD_SUMMARY_REQUIRED')
    need(binding.get('complete_static_build_qualified') is True and
         binding.get('actual_original_NdkTests_runtime_qualified') is False and
         binding.get('installed_UID') is None and binding.get('install_run_retire_nonces') is None and
         binding['APK'] == build['APK'] and binding['native_members'] == build['native_members'] and
         binding['signature_certificate_sha256'] == build['signer_sha256'] and
         binding['build_result']['bytes'] == BUILD_REPORT_PIN['bytes'] and
         binding['build_result']['sha256'] == BUILD_REPORT_PIN['sha256'] and
         binding['manifest_min_sdk'] == 14 and binding['manifest_target_sdk'] == 24,
         'EXACT_ORIGINAL_SIGNED_APK05_BINDING_REQUIRED')
    artifact = build['APK']
    fields = ('device','inode','mode','uid','gid','nlink','bytes','mtime_ns','ctime_ns')
    need(artifact['path'] == '/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-05-20261106/ndk-tests.apk'
         and artifact['resolved_path'] == artifact['path'] and
         artifact['uid'] == artifact['gid'] == 1000 and artifact['nlink'] == 1 and
         stat.S_IMODE(artifact['mode']) == 0o600, 'ACTUAL_INPUT_APK_METADATA_REQUIRED')
    apk = phases.read_exact_file(artifact['path'],33554432,
        {'bytes':artifact['bytes'],'sha256':artifact['sha256']},
        expected_identity={k:artifact[k] for k in fields})
    return build,apk

def initial_main_guard(sources, context_module):
    raw = sources.fixed_reference(context_module.INSTALLED_SHARED/'source_contract.py',
                                  context_module.CONTRACT_BYTES,context_module.CONTRACT_SHA)
    source = sources.module(raw,context_module.INSTALLED_SHARED/'source_contract.py',
                            'fixed_ndk_before_lock_contract')
    shared = source.SourceContract(context_module.INSTALLED_SHARED/'source-manifest.json',
                                   context_module.SHARED_MANIFEST)
    current = shared.load('current_baseline_guard.py','fixed_ndk_before_lock_guard')
    need(shared.files['current_baseline_guard.py']['sha256'] == context_module.CURRENT_GUARD_SHA,
         'EXACT_BEFORE_LOCK_CURRENT_MAIN_GUARD_REQUIRED')
    baseline = current.current_baseline()
    def guard():
        sources.verify()
        shared.verify()
        return current.current_guard(baseline,action_attempted=False)
    return guard

def emit_result(phases, lease_module, lease, result):
    """Create one bounded result and close every acquired emission FD.
    The JSON records pending emission. Only the returned summary can report that
    its result-file and parent FDs closed; an independent terminal is still required.
    """
    raw = json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    need(len(raw) <= RESULT_LIMIT, 'FIXTURE_INSTALL_RESULT_BOUND')
    fds = []
    primary = None
    row = None
    try:
        need(lease is not None and lease.root_created and lease.closed and
             lease.root_identity is not None, 'OWN_CREATED_ROOT_REQUIRED_FOR_RESULT')
        current = os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        fds.append(current)
        for part in str(lease.root_path)[1:].split('/'):
            current = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|
                              os.O_CLOEXEC,dir_fd=current)
            fds.append(current)
        observed = lease_module.identity(current)
        need(all(observed[k] == lease.root_identity[k] for k in
                 ('device','inode','mode','uid','gid')), 'OWN_RESULT_ROOT_CHANGED')
        fd = os.open('result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|
                     os.O_CLOEXEC,0o600,dir_fd=current)
        fds.append(fd)
        count = 0
        deadline = time.monotonic()+10
        while count < len(raw):
            need(time.monotonic() < deadline, 'OWN_RESULT_WRITE_DEADLINE')
            n = os.write(fd,raw[count:])
            need(n > 0, 'OWN_RESULT_WRITE_STALLED')
            count += n
        os.fchmod(fd,0o400)
        os.fsync(fd)
        row = lease_module.identity(fd)
        named = os.stat('result.json',dir_fd=current,follow_symlinks=False)
        need(row['uid'] == row['gid'] == 0 and row['nlink'] == 1 and
             row['bytes'] == len(raw) and stat.S_IMODE(row['mode']) == 0o400 and
             (named.st_dev,named.st_ino) == (row['device'],row['inode']),
             'OWN_RESULT_FILE_SHAPE_CHANGED')
        os.fsync(current)
    except BaseException as error:
        primary = error
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note('RESULT_FD_CLOSE_FAILED:'+type(error).__name__)
    if primary is not None:
        raise primary
    again = phases.read_exact_file(str(lease.root_path/'result.json'),RESULT_LIMIT,
        {'bytes':len(raw),'sha256':sha(raw)},expected_identity=row)
    need(again == raw, 'OWN_RESULT_READBACK_CHANGED')
    return {'path':str(lease.root_path/'result.json'),'bytes':len(raw),'sha256':sha(raw),
            'result_file_and_parent_FDs_closed':True}


def run_phase(binding=None, packet=None):
    sources_raw,manifest_raw,refs,fixture,attempt = check_binding(binding,packet)
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
         'ROOT_ONLY_FIXED_RUNTIME_PHASE_WORKER_REQUIRED')
    phase = binding['phase']
    root = PHASE_ROOTS[phase]
    source_root = root/'source'
    step = root/'steps'/PHASE_STEPS[phase]
    phases = load_source(sources_raw['fixture_phases.py'],source_root/'fixture_phases.py',
                         'fixed_ndk_runtime_phases')
    context_module = load_source(sources_raw['fixture_context.py'],source_root/'fixture_context.py',
                                 'fixed_ndk_runtime_context')
    lease_module = load_source(sources_raw['phase_lease.py'],source_root/'phase_lease.py',
                               'fixed_ndk_phase_lease')
    need(lease_module.PHASE_ROOTS == PHASE_ROOTS and lease_module.PHASE_STEPS == PHASE_STEPS and
         lease_module.SOURCE_NAMES == SOURCE_NAMES,
         'EXACT_FIXED_PHASE_LEASE_ROOTS_AND_SEVEN_SOURCES_REQUIRED')
    build,apk = original_build(phases,fixture,refs)
    installation = original_installation(phases,fixture,refs,build)
    material = json.loads(refs['phase-nonce.original.json'])
    previous = prior_run(phases,fixture,refs,binding,installation,material)
    scope = fixture.scope(phase,attempt,BUILD_REPORT_PIN,installation['scope_installation'])
    installed = installation['installed_tuple']
    started = time.monotonic()
    deadline = started+WORK_SECONDS
    result = phases.empty_result(scope,binding['source_manifest'])
    result.update({'entry_kind':'pocket4-original-ndk-runtime-worker01',
        'build_result':dict(BUILD_REPORT_PIN),'install_result':dict(installation['install_result']),
        'install_source_manifest':dict(INSTALL_SOURCE_PIN),
        'entry_controls':binding['entry_controls'],
        'entry_controls_terminal':binding['entry_controls_terminal'],
        'phase_nonce_original':binding['nonce_material'],'phase_nonce_terminal':binding['nonce_terminal'],
        'configured_work_seconds':WORK_SECONDS,'result_emission_pending':True,
        'independent_terminal_still_required':True,
        'original_NdkTests_runtime_qualified':False,'feature_default_changed':False,
        'target_sdk_bypass_used':False,'permission_grants':0,'App_launches':0,
        'whole_invocation_resource_observed_by_worker':False})
    if phase == 'retire':
        result['prior_run'] = {'result':binding['prior_run']['result'],
            'terminal':binding['prior_run']['terminal'],'job':binding['prior_run']['job'],
            'ok':previous['ok'],'error':previous['error'],
            'outcome_unknown':previous['outcome_unknown'],
            'instrumentation_verified':previous['instrumentation_verified']}
    lease = sources = guard = None
    before_lock = None
    previous_handler = signal.getsignal(signal.SIGALRM)
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    need(prior_timer == (0.0,0.0), 'NO_AMBIENT_WORKER_TIMER_REQUIRED')
    previous_umask = os.umask(0o077)
    def expired(signum,frame):
        raise TimeoutError('FIXED_RUNTIME_PHASE_WORK_DEADLINE')
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,WORK_SECONDS)
    try:
        lease = lease_module.PhaseLease(scope,binding['source_manifest'],deadline,installation)
        lease.create_and_stage(sources_raw,manifest_raw)
        sources = phases.FixedSources(binding['source_manifest'],source_root=str(source_root))
        guard = initial_main_guard(sources,context_module)
        before_lock = guard()
        lease.acquire_and_claim()
        need(guard() == before_lock, 'MAIN_CHANGED_DURING_RUNTIME_PHASE_LOCK_ADMISSION')
        if phase == 'run':
            phase_result = phases.run_original_once(sources,fixture,context_module,scope,build,
                installed,step,deadline,admission=lease)
        else:
            phase_result = phases.retire_once(sources,fixture,context_module,scope,build,
                installed,previous,step,deadline,admission=lease)
        result.update(phase_result)
        result['Main_before_lock'] = before_lock
        need(result.get('Main_before') == before_lock and
             result.get('Main_after') == before_lock, 'EXACT_THREE_RUNTIME_MAIN_MAPS_REQUIRED')
    except BaseException as error:
        phases.failure(result,'runtime_phase_worker',error)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        if guard is not None:
            try:
                result['Main_after_worker'] = guard()
                need(before_lock is not None and result['Main_after_worker'] == before_lock,
                     'WORKER_MAIN_AFTER_DIFFERS')
            except BaseException as error:
                phases.failure(result,'worker_final_Main',error)
        if sources is not None:
            try:
                sources.verify()
                result['all_seven_sources_unchanged'] = True
            except BaseException as error:
                phases.failure(result,'worker_final_sources',error)
        try:
            final_build,final_apk = original_build(phases,fixture,refs)
            final_installation = original_installation(phases,fixture,refs,final_build)
            need(final_build == build and final_apk == apk and
                 final_installation == installation,
                 'ACTUAL_BUILD_APK_OR_ORIGINAL_INSTALL_INPUT_CHANGED')
            if phase == 'retire':
                need(prior_run(phases,fixture,refs,binding,installation,material) == previous,
                     'ACTUAL_PRIOR_RUN_INPUT_CHANGED')
            result['actual_build_APK_install_and_prior_run_unchanged'] = True
        except BaseException as error:
            phases.failure(result,'worker_final_static_inputs',error)
        if lease is not None:
            try:
                result['phase_lease'] = lease.close()
                need(result['phase_lease']['all_tracked_lease_FDs_closed'] and
                     result['phase_lease']['lease_errors'] == [] and
                     all(result['phase_lease'][k] is True for k in (
                        'global_action_lock_released','flow_lock_released','step_lock_released')),
                     'ALL_RUNTIME_PHASE_LOCKS_AND_OWN_FDS_MUST_CLOSE')
            except BaseException as error:
                phases.failure(result,'runtime_lease_close',error)
        try:
            signal.signal(signal.SIGALRM,previous_handler)
            os.umask(previous_umask)
        except BaseException as error:
            phases.failure(result,'worker_local_state_restore',error)
    result['ok'] = bool(result.get('ok') and result['error'] is None and
        result.get('all_seven_sources_unchanged') is True and
        result.get('actual_build_APK_install_and_prior_run_unchanged') is True and
        result.get('Main_after_worker') == before_lock)
    result['outcome_unknown'] = bool(result['action_attempted'] and not result['ok'])
    result['original_NdkTests_runtime_qualified'] = bool(
        phase == 'retire' and result['ok'] and
        result.get('original_NdkTests_testMain_accepted') is True)
    result['independent_retirement_completed'] = bool(phase == 'retire' and result['ok'])
    result['elapsed_seconds'] = time.monotonic()-started
    summary = {'schema':1,'kind':'pocket4-original-ndk-runtime-worker-summary01',
        'phase':phase,'ok':False,'result':None,'error':result['error'],
        'automatic_retry':False,
        'original_NdkTests_runtime_qualified':result['original_NdkTests_runtime_qualified'],
        'independent_retirement_completed':result['independent_retirement_completed'],
        'installed_UID':installed['uid'],'instrumentation_attempted':
            result.get('instrumentation_attempted',False),
        'outcome_unknown':result['outcome_unknown']}
    try:
        summary['result'] = emit_result(phases,lease_module,lease,result)
        summary['ok'] = result['ok']
    except BaseException as error:
        summary['result_emission_error'] = lease_module.public_error(error)
    raw = canonical(summary)+b'\n'
    need(len(raw) <= 8192, 'BOUNDED_RUNTIME_PHASE_SUMMARY_REQUIRED')
    count = 0
    while count < len(raw):
        amount = os.write(1,raw[count:])
        need(amount > 0, 'RUNTIME_PHASE_SUMMARY_WRITE_STALLED')
        count += amount
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    run_phase(PENDING_BINDING,None)
