"""Fixed original NDK fixture installation worker; no default execution.
Only a separately frozen exact binding with actual nonce and successful current
source controls can enter run_install. No installed UID is supplied by a caller.
Run/instrumentation/retirement remain separate, unbound routes.
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
ROOT = Path('/home/alex/work/pocket4-original-ndk-fixture-APK05-install-02')
SOURCE = ROOT/'source'
STEP = ROOT/'steps'/'install-02'
WORK_SECONDS = 175.0
RESULT_LIMIT = 1048576
PACKAGE = 'com.example.ndk_tests'
INSTALL_NONCE = '06a571251aa6fcc77591494edda1f801'
BUILD_REPORT = '/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-05-20261106/build-result.json'
BUILD_REPORT_PIN = {'bytes':9811685,'sha256':'d8eb53c924fa6a76bee19304bd8538bf2a57306b7e9bd6a55df8787d4ea33411'}
SOURCE_NAMES = {
    'fixture_contract.py','fixture_context.py','fixture_transport.py',
    'fixture_phases.py','current_discovery.py','install_lease.py','install_worker.py',
}
REFERENCE_PINS = json.loads(r'''{"static-build.original.json":{"bytes":4893,"sha256":"c59318c119e43afc810debc6dbfd7367d37f1f9c154313572f732cc645124bae"},"build-terminal.original.json":{"bytes":729,"sha256":"7df30068ee3849645f69085f9c16f1bc1094744fbacc26d765a09be0c21ded3d"},"build-stdout.original.json":{"bytes":228,"sha256":"7e22891b785542a355a55f67b2235180d1dd216d176871338e88ebd6a2d706f6"},"readonly38.original.json":{"bytes":6407,"sha256":"7ff0ed239e77335b04c1b4197eab194ed108d75d2deff8673185a3ee0c7d5256"},"readonly38-terminal.original.json":{"bytes":731,"sha256":"8f02badd8c546fb2aba3e58a2ceab3f23d99811d8c1e6e142d92d1f93b3ad804"},"install-nonce.original.json":{"bytes":796,"sha256":"8cad97eca9ec88beb9a2e7e285f9a61eeb752bac01058ac4e4afc6af9addf960"},"install-nonce-terminal.original.json":{"bytes":729,"sha256":"52e68d12c4fd510a66342540c96fa26f2ee04d6a99b314c036782930b96c21e7"},"global921.original.json":{"bytes":35001,"sha256":"735f9acaf4100e82bf7bfdacbecf9510286b1099f8dee92bf668e942e8780bac"},"global922.original.json":{"bytes":35039,"sha256":"31d5455e4c3cbe6f1951d032a45d94c442c2535ce3eddc3f745769f7a8969520"}}''')
ENTRY_CONTROL_KIND = 'pocket4-original-ndk-install-entry-controls02'
ENTRY_CONTROL_COUNTS = {'fixture':38,'manifest':4,'lease':8}


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
    # This is before UID, Main, file or namespace observations.
    need(binding is not None, 'SOURCE_ONLY_INSTALL_ACTUAL_BINDING_UNBOUND')
    need(type(binding) is dict and set(binding) == {
        'schema','kind','root','source_manifest','entry_controls',
        'entry_controls_terminal','entry_controls_job','entry_controls_stdout_bytes'} and
        binding['schema'] == 1 and binding['kind'] == 'pocket4-original-ndk-install-binding-v1' and
        binding['root'] == str(ROOT), 'EXACT_SINGLE_INSTALL_BINDING_REQUIRED')
    need(type(packet) is dict and set(packet) == {'schema','sources','manifest','references'} and
         packet['schema'] == 1 and type(packet['sources']) is dict and
         set(packet['sources']) == SOURCE_NAMES,
         'FIXED_SEVEN_SOURCE_PACKET_REQUIRED')
    sources = {name:body(row,131072) for name,row in packet['sources'].items()}
    manifest_raw = body(packet['manifest'],65536)
    pin = {'bytes':len(manifest_raw),'sha256':sha(manifest_raw)}
    need(pin == binding['source_manifest'], 'EXTERNAL_INSTALL_SOURCE_MANIFEST_CHANGED')
    manifest = json.loads(manifest_raw)
    need(manifest.get('schema') == 'pocket4-original-ndk-fixture-source-v1' and
         set(manifest.get('files',{})) == SOURCE_NAMES and
         all(manifest['files'][name] == {'bytes':len(raw),'sha256':sha(raw)}
             for name,raw in sources.items()), 'EXACT_SEVEN_WHOLE_SOURCE_BODIES_REQUIRED')
    need(type(packet['references']) is dict and set(packet['references']) ==
         set(REFERENCE_PINS) | {'entry-controls.original.json','entry-controls-terminal.original.json'},
         'EXACT_ACTUAL_REFERENCE_SET_REQUIRED')
    refs = {}
    for name,pinned in REFERENCE_PINS.items():
        raw = body(packet['references'][name],131072)
        need({'bytes':len(raw),'sha256':sha(raw)} == pinned, 'ACTUAL_REFERENCE_PIN_CHANGED')
        refs[name] = raw
    fixture = load_source(sources['fixture_contract.py'],SOURCE/'fixture_contract.py','fixed_ndk_contract')
    for name,pin_name in (
            ('entry-controls.original.json','entry_controls'),
            ('entry-controls-terminal.original.json','entry_controls_terminal')):
        raw = body(packet['references'][name],262144)
        need({'bytes':len(raw),'sha256':sha(raw)} == binding[pin_name],
             'ACTUAL_ENTRY_CONTROL_PIN_REQUIRED')
        refs[name] = raw
    entry = json.loads(refs['entry-controls.original.json'])
    fixture.terminal(refs['entry-controls-terminal.original.json'],
        binding['entry_controls_terminal'],binding['entry_controls_job'],
        binding['entry_controls_stdout_bytes'])
    need(len(refs['entry-controls.original.json']) == binding['entry_controls_stdout_bytes'] and
         entry.get('kind') == ENTRY_CONTROL_KIND and entry.get('ok') is True and
         entry.get('errors') == [] and entry.get('source_manifest') == pin and
         entry.get('counts') == ENTRY_CONTROL_COUNTS and
         type(entry.get('cases')) is list and len(entry['cases']) == 50 and
         len({x['name'] for x in entry['cases']}) == 50 and
         all(x.get('passed') is True for x in entry['cases']) and
         entry.get('all_owned_control_FDs_closed') is True and
         entry.get('all_owned_control_files_removed') is True and
         entry.get('Main_reads') == entry.get('Android_commands') == entry.get('children') == 0 and
         entry.get('runtime_qualified') is False,
         'FIFTY_CURRENT_SOURCE_ENTRY_CONTROLS_AND_CLOSURE_REQUIRED')
    old = json.loads(refs['readonly38.original.json'])
    fixture.terminal(refs['readonly38-terminal.original.json'],
        REFERENCE_PINS['readonly38-terminal.original.json'],'1a1b2ce69a8-fc05-7fd6',6407)
    need(old.get('ok') is True and old.get('errors') == [] and
         old.get('controls',{}).get('count') == 38 and
         len(old['controls']['cases']) == 38 and
         all(x.get('passed') is True for x in old['controls']['cases']) and
         old.get('complete_static_APK_report_qualified') is True and
         old.get('report_two_full_reads_completed') is True and
         old.get('report_read_functions_returned_after_close') is True and
         old.get('report_pin') == BUILD_REPORT_PIN and
         old.get('actual_installed_UID') is None and old.get('fixture_attempt_nonces') is None and
         old.get('runtime_dispatch_authorized') is False,
         'ACTUAL_ORIGINAL_38_AND_STATIC_REPORT_REQUIRED')
    nonce = json.loads(refs['install-nonce.original.json'])
    fixture.terminal(refs['install-nonce-terminal.original.json'],
        REFERENCE_PINS['install-nonce-terminal.original.json'],'1a1b2d0e7ab-fc05-7fdf',796)
    previous = json.loads(refs['global921.original.json'])
    latest = json.loads(refs['global922.original.json'])
    need(type(previous) is list and len(previous) == len(set(previous)) == 921 and
         type(latest) is list and len(latest) == len(set(latest)) == 922 and
         previous == sorted(previous) and latest == sorted(latest) and
         all(type(x) is str and re.fullmatch('[0-9a-f]{32}',x) for x in latest) and
         nonce.get('kind') == 'pocket4-original-ndk-fixture-install-nonce02' and
         nonce.get('profile') == 'pocket4-original-ndk-fixture-APK05-install02' and
         nonce.get('package') == PACKAGE and nonce.get('phase') == 'install' and
         nonce.get('nonce') == INSTALL_NONCE and nonce.get('draw_count') == 1 and
         nonce.get('generator') == 'secrets.token_hex(16)' and
         nonce.get('redraw_attempted') is False and nonce.get('ok') is True and
         nonce.get('error') is None and nonce.get('fresh_against_exact_pool') is True and
         nonce.get('uid') == nonce.get('gid') == 1000 and
         nonce.get('runtime_authorized') is False and
         INSTALL_NONCE not in previous and latest == sorted(previous+[INSTALL_NONCE]),
         'ONE_UNCONSUMED_INSTALL_ONLY_ACTUAL_NONCE_REQUIRED')
    return sources,manifest_raw,refs,fixture


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
        for part in str(ROOT)[1:].split('/'):
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
    again = phases.read_exact_file(str(ROOT/'result.json'),RESULT_LIMIT,
        {'bytes':len(raw),'sha256':sha(raw)},expected_identity=row)
    need(again == raw, 'OWN_RESULT_READBACK_CHANGED')
    return {'path':str(ROOT/'result.json'),'bytes':len(raw),'sha256':sha(raw),
            'result_file_and_parent_FDs_closed':True}


def run_install(binding=None, packet=None):
    sources_raw,manifest_raw,refs,fixture = check_binding(binding,packet)
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
         'ROOT_ONLY_FIXED_INSTALL_WORKER_REQUIRED')
    phases = load_source(sources_raw['fixture_phases.py'],SOURCE/'fixture_phases.py','fixed_ndk_phases')
    context_module = load_source(sources_raw['fixture_context.py'],SOURCE/'fixture_context.py','fixed_ndk_context')
    lease_module = load_source(sources_raw['install_lease.py'],SOURCE/'install_lease.py','fixed_ndk_lease')
    need(lease_module.ROOT == ROOT and lease_module.SOURCE == SOURCE and lease_module.STEP == STEP and
         lease_module.SOURCE_NAMES == SOURCE_NAMES, 'FIXED_LEASE_ROOT_AND_SOURCE_SET_REQUIRED')
    build,apk = original_build(phases,fixture,refs)
    scope = fixture.scope('install',INSTALL_NONCE,BUILD_REPORT_PIN)
    started = time.monotonic()
    deadline = started+WORK_SECONDS
    result = phases.empty_result(scope,binding['source_manifest'])
    result.update({'entry_kind':'pocket4-original-ndk-install-worker02',
        'build_result':dict(BUILD_REPORT_PIN),'entry_controls':binding['entry_controls'],
        'entry_controls_terminal':binding['entry_controls_terminal'],
        'install_nonce_original':REFERENCE_PINS['install-nonce.original.json'],
        'install_nonce_terminal':REFERENCE_PINS['install-nonce-terminal.original.json'],
        'configured_work_seconds':WORK_SECONDS,'result_emission_pending':True,
        'independent_terminal_still_required':True,'instrumentation_executed':False,
        'original_NdkTests_runtime_qualified':False,'feature_default_changed':False,
        'target_sdk_bypass_used':False,'permission_grants':0,'App_launches':0,
        'whole_invocation_resource_observed_by_worker':False})
    lease = sources = guard = None
    before_lock = None
    previous_handler = signal.getsignal(signal.SIGALRM)
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    need(prior_timer == (0.0,0.0), 'NO_AMBIENT_WORKER_TIMER_REQUIRED')
    previous_umask = os.umask(0o077)
    def expired(signum,frame):
        raise TimeoutError('FIXED_INSTALL_WORK_DEADLINE')
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,WORK_SECONDS)
    try:
        lease = lease_module.InstallLease(scope,binding['source_manifest'],deadline)
        lease.create_and_stage(sources_raw,manifest_raw)
        sources = phases.FixedSources(binding['source_manifest'],source_root=str(SOURCE))
        guard = initial_main_guard(sources,context_module)
        before_lock = guard()
        lease.acquire_and_claim()
        need(guard() == before_lock, 'MAIN_CHANGED_DURING_INSTALL_LOCK_ADMISSION')
        phase_result = phases.install_once(sources,fixture,context_module,scope,build,apk,
                                           STEP,deadline,admission=lease)
        result.update(phase_result)
        result['Main_before_lock'] = before_lock
        need(result.get('Main_before') == before_lock and
             result.get('Main_after') == before_lock,'EXACT_THREE_INSTALL_MAIN_MAPS_REQUIRED')
    except BaseException as error:
        phases.failure(result,'install_worker',error)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        # This independent guard cannot replace a missing or failed original phase sample.
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
            need(final_build == build and final_apk == apk,'ACTUAL_APK_OR_BUILD_INPUT_CHANGED')
            result['actual_build_and_APK_unchanged'] = True
        except BaseException as error:
            phases.failure(result,'worker_final_static_inputs',error)
        if lease is not None:
            try:
                result['install_lease'] = lease.close()
                need(result['install_lease']['all_tracked_lease_FDs_closed'] and
                     result['install_lease']['lease_errors'] == [] and
                     all(result['install_lease'][k] is True for k in (
                        'global_action_lock_released','flow_lock_released','step_lock_released')),
                     'ALL_INSTALL_LOCKS_AND_OWN_FDS_MUST_CLOSE')
            except BaseException as error:
                phases.failure(result,'install_lease_close',error)
        try:
            signal.signal(signal.SIGALRM,previous_handler)
            os.umask(previous_umask)
        except BaseException as error:
            phases.failure(result,'worker_local_state_restore',error)
    result['ok'] = bool(result.get('ok') and result['error'] is None and
        result.get('owned_install_qualified') is True and
        result.get('all_seven_sources_unchanged') is True and
        result.get('actual_build_and_APK_unchanged') is True and
        result.get('Main_after_worker') == before_lock)
    result['owned_install_qualified'] = result['ok']
    result['outcome_unknown'] = bool(result['action_attempted'] and not result['ok'])
    result['possible_owned_package_retained'] = bool(result.get('install_attempted') and not result['ok'])
    result['elapsed_seconds'] = time.monotonic()-started
    summary = {'schema':1,'kind':'pocket4-original-ndk-install-worker-summary02',
        'ok':False,'result':None,'error':result['error'],
        'automatic_retry':False,'original_NdkTests_runtime_qualified':False,
        'installed_UID':result.get('owned_package_uid'),
        'install_attempted':result.get('install_attempted',False),
        'outcome_unknown':result['outcome_unknown']}
    try:
        summary['result'] = emit_result(phases,lease_module,lease,result)
        summary['ok'] = result['ok']
    except BaseException as error:
        summary['result_emission_error'] = lease_module.public_error(error)
    raw = canonical(summary)+b'\n'
    need(len(raw) <= 8192,'BOUNDED_INSTALL_SUMMARY_REQUIRED')
    count = 0
    while count < len(raw):
        amount = os.write(1,raw[count:])
        need(amount > 0,'INSTALL_SUMMARY_WRITE_STALLED')
        count += amount
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    # A future exact outer binder calls run_install with the immutable packet.
    # Executing this unbound file cannot acquire locks or touch Main/Android.
    run_install(PENDING_BINDING,None)
