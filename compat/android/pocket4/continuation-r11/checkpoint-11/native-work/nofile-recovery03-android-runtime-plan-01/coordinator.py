#!/usr/bin/env python3
"""One serial pair of exact owned NOFILE APK cycles; default PLAN only."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import zipfile

RUNNER = Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-01/run-r4.py')
RUNNER_SHA = 'c16015f7a51f857d114d92691dbf4ac4d0ccf758c2f99c7c541653ce1957ea62'
ENTRY = Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json')
ENTRY_SHA = '3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3'
BUILD_ROOT = Path('/home/alex/work/pocket4-nofile-owner-recovery03-android-build-01-20261105')
BUILD = BUILD_ROOT / 'coordinator01/result.json'
BUILD_SHA = 'f3617407f8c624357f4bf9a9cc53e1e78a217b3c0b8bc9a51448c09569e2ea06'
HERE = Path('/home/alex/work/pocket4-owned-nofile-recovery03-android-cycle-source-01-20261105')
REVIEW = HERE / 'entry-review.json'
REVIEW_SHA = '2dbe0c31ec31733fab9bbfb851ab3642dc0c2d7aef3937165084d1fb11b9548c'
CASE_PLAN = HERE / 'CASE_PLAN.json'
CASE_PLAN_SHA = '5ad4e7985eee2d1c9a7dd1322a2c933e74d734a5c98a37d4bb0c5b88e101ee09'
ROOT = Path('/home/alex/work/pocket4-owned-nofile-recovery03-android-cycle-01-20261105')
ARM_ROOTS = {arm: Path('/home/alex/work/pocket4-owned-nofile-recovery03-' + arm + '-android-01-20261105')
             for arm in ('preimage', 'candidate')}
NONCES = {arm: 'p4_nofile_recovery03_' + arm + '_20261105_a1' for arm in ARM_ROOTS}
EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
PACKAGE = 'local.pocket4.fdownerprobe.r11'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
MAIN_GROUP = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
FIELDS = ('memory.events', 'memory.current', 'memory.peak', 'memory.swap.current',
          'memory.swap.peak', 'memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max')


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def unique(items):
    result = {}
    for key, value in items:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pinned(path, expected, bound=1048576):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= bound, 'bounded regular input required: ' + str(path))
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(bound + 1)
        after = os.fstat(fd)
        same = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(len(raw) <= bound and hashlib.sha256(raw).hexdigest() == expected and
             same(before) == same(after) == same(path.lstat()), 'held input changed: ' + str(path))
        return raw
    finally:
        os.close(fd)


def save(name, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def no_alias(path):
    for parent in (path, *path.parents):
        if parent.exists() or parent.is_symlink():
            need(stat.S_ISDIR(parent.lstat().st_mode), 'owned path aliases a nondirectory')


def qualification():
    need(os.geteuid() == 0 and os.getegid() == 0 and not sys.flags.optimize, 'fixed root nonoptimized coordinator required')
    pinned(RUNNER, RUNNER_SHA, 16384)
    entry = decode(pinned(ENTRY, ENTRY_SHA, 8192))
    review = decode(pinned(REVIEW, REVIEW_SHA, 8192))
    cases = decode(pinned(CASE_PLAN, CASE_PLAN_SHA, 16384))['cases']
    build = decode(pinned(BUILD, BUILD_SHA, 65536))
    need(build['state'] == 'PASS' and build['source_unchanged_after'] is True and
         build['APK_ELF_unchanged_after'] is True and build['authority_unchanged_after'] is True and
         build['original_26_case_assertions_unchanged'] is True and not build['tool_changes'] and
         build['owned_resource_gate']['pass'] is True and
         not build['cleanup']['forced_cleanup'] and not build['cleanup']['remaining'] and not build['cleanup']['errors'],
         'matching Android build is not qualified')
    need(entry['qualified_for_owned_namespace_entry'] is True and entry['owned_runner_sha256'] == RUNNER_SHA and
         entry['helper_binary_sha256'] == '21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689' and
         entry['qualified_for_whole_process_tree_cleanup'] is False,
         'original held namespace entry qualification differs')
    need(review['matching_build_result_sha256'] == BUILD_SHA and review['no_new_concrete_entry_blocker_found'] is True and
         review['scoped_owned_Android_cycle_source_ready'] is True and len(cases) == 26,
         'actual entry review or case plan differs')
    for arm in ARM_ROOTS:
        rows = build['source_inputs'][arm]
        need(len(rows) == 22, 'complete fixed 22-source arm required')
        for name, row in rows.items():
            path = BUILD_ROOT / arm / name
            need(str(path) == row['path'] and Path(name).is_absolute() is False and '..' not in Path(name).parts,
                 'source escapes exact arm')
            pinned(path, row['sha256'])
        artifact = build['arms'][arm]
        receipt = decode(pinned(Path(artifact['build_receipt']['path']), artifact['build_receipt']['sha256'], 32768))
        audit = decode(pinned(Path(artifact['worker_audit']['path']), artifact['worker_audit']['sha256'], 8192))
        pinned(Path(artifact['entry_disassembly']['path']), artifact['entry_disassembly']['sha256'], 65536)
        need(audit['qualified_worker_closure'] is True and audit['errors'] == [] and
             audit['elf_sha256'] == artifact['ELF']['sha256'] and
             receipt['state'] == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN' and receipt['package'] == PACKAGE and
             receipt['ABI'] == 'x86_64' and receipt['APK']['sha256'] == artifact['APK']['sha256'],
             'actual APK/ELF audit is incomplete')
        pinned(Path(artifact['ELF']['path']), artifact['ELF']['sha256'], 262144)
        apk = Path(artifact['APK']['path'])
        raw = pinned(apk, artifact['APK']['sha256'], 262144)
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            wanted = 'lib/x86_64/libfdownerprobe.so'
            need(archive.namelist().count(wanted) == 1 and
                 hashlib.sha256(archive.read(wanted)).hexdigest() == artifact['ELF']['sha256'],
                 'installed APK would contain a different ELF')
        need(review['actual_inputs'][arm + '-APK']['sha256'] == artifact['APK']['sha256'] and
             review['actual_inputs'][arm + '-ELF']['sha256'] == artifact['ELF']['sha256'], 'reviewed actual artifact differs')
    return build, cases


def group_snapshot(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd); fields = {}
        for name in FIELDS:
            source = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            try:
                raw = os.read(source, 16385)
                need(len(raw) <= 16384, 'resource field exceeded fixed bound')
                fields[name] = raw.decode('ascii').strip()
            finally:
                os.close(source)
        after = os.fstat(fd); named = path.lstat()
        need((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino) == (named.st_dev, named.st_ino),
             'resource group identity changed')
        return {'path': str(path), 'identity': [before.st_dev, before.st_ino], 'fields': fields,
                'events': {k: int(v) for k, v in (line.split() for line in fields['memory.events'].splitlines())}}
    finally:
        os.close(fd)


def fences():
    activation = decode(pinned(ACTIVATION, ACTIVATION_SHA, 131072))
    membership = Path('/proc/self/cgroup').read_text().strip()
    need(re.fullmatch(r'0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-[a-z0-9-]+\.service', membership),
         'coordinator is outside its owned job')
    own = group_snapshot(Path('/sys/fs/cgroup') / membership[3:].lstrip('/'))
    main = group_snapshot(MAIN_GROUP)
    need(own['fields']['memory.max'] == '268435456' and own['fields']['cpu.max'] == '50000 100000',
         'owned coordinator resource budget differs')
    need(all(main['fields'][key] == value for key, value in activation['limits'].items()),
         'Main resource limits differ from original activation')
    return {'own': own, 'Main': main, 'activation_sha256': ACTIVATION_SHA}


def compare_fences(before, after):
    result = {}
    for key in ('own', 'Main'):
        a, b = before[key], after[key]
        need(a['path'] == b['path'] and a['identity'] == b['identity'], 'resource scope identity changed')
        limits = ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max')
        need(all(a['fields'][name] == b['fields'][name] for name in limits), 'resource settings changed')
        need(set(a['events']) == set(b['events']), 'resource event schema changed')
        delta = {name: b['events'][name] - value for name, value in a['events'].items()}
        need(all(value >= 0 for value in delta.values()) and all(delta[name] == 0 for name in ('oom', 'oom_kill', 'oom_group_kill')),
             key + ' encountered an OOM event')
        result[key] = {'identity': b['identity'], 'memory_events_delta': delta,
                       'memory_peak': b['fields']['memory.peak'], 'memory_swap_peak': b['fields']['memory.swap.peak']}
    result['only_pre_post_observation_claimed'] = True
    return result


def validate_native(arm, raw, cases, uid):
    result = decode(raw)
    preimage = arm == 'preimage'; expected_pass = 15 if preimage else 26
    need(result['preimage'] == preimage and result['uid'] == uid and result['case_count'] == 26 and result['observed'] == 26 and
         result['function_passed'] == expected_pass and result['matched_expected'] == 26 and
         result['direct_children_reaped'] == 26 and result['direct_children_finished'] == 26 and
         result['nested_started'] == result['nested_reaped'] == 5 and result['parent_capabilities_unchanged'] is True and
         result['unexpected_cleanup'] == 0 and result['pass'] is True and result['lost_harness_PASS_inherited'] is False,
         'actual Android 26-case aggregate differs')
    need(len(result['cases']) == 26, 'actual case membership differs')
    for expected, observed in zip(cases, result['cases']):
        wanted = expected['preimage_expected_function_pass'] if preimage else expected['candidate_expected_function_pass']
        need(observed['index'] == expected['index'] and observed['name'] == expected['name'] and
             observed['expected_function_pass'] == wanted and observed['function_pass'] == wanted and
             observed['matches_expectation'] is True and observed['known_red_boundary'] == expected['known_red_boundary_remains'],
             'actual case result differs: ' + expected['name'])
        outer = observed['outer']
        need(all(outer[k] == 1 for k in ('entered', 'finished', 'reaped', 'persistent_tid_clear', 'inherited_tid_clear',
                                        'caps_zero', 'guarded', 'mask_preserved')) and
             all(outer[k] == 0 for k in ('timeout', 'status', 'cleanup_stop', 'cap_clear', 'unexpected_cleanup')),
             'actual case lifecycle/authority failed: ' + expected['name'])
        if not wanted:
            extra = observed['added']
            need(extra['setup_done'] == 1 and extra['primary_rc'] == -1 and extra['primary_errno'] == 24 and
                 extra['failed_snapshot_untouched'] == 1, 'preimage negative is not exact EMFILE')
    return result


def assess_instrumentation(arm, report, cases):
    text = report['instrumentation_output']
    values = {}
    for line in text.splitlines():
        prefix = 'INSTRUMENTATION_RESULT: '
        if line.startswith(prefix):
            key, value = line[len(prefix):].split('=', 1)
            need(key not in values, 'duplicate instrumentation result key')
            values[key] = value
    codes = re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$', text, re.M)
    need(codes == ['-1'] and 'error' not in values and values['nonce'] == NONCES[arm] and
         values['sdk'] == '37' and values['debuggable'] == 'false', 'owned instrumentation did not complete its exact contract')
    uid = report['installed_identity']['uid']
    need(uid >= 10000 and int(values['uid']) == uid and int(values['pid']) > 0, 'app UID/Java identity differs')
    native = validate_native(arm, values['probe_result'], cases, uid)
    return {'uid': uid, 'pid': int(values['pid']), 'sdk': 37, 'native': native,
            'policy_text_observed_in_original_instrumentation_output': True,
            'native_source_Android_qualification_flag_retained_false': native['Android_qualification'] is False}


def execute():
    build, cases = qualification()
    need(Path(__file__).absolute() == HERE / 'coordinator.py', 'exact staged coordinator required')
    for path in (ROOT, *ARM_ROOTS.values()):
        no_alias(path); need(not path.exists(), 'owned attempt exists; no replay or replacement')
    os.umask(0o077); ROOT.mkdir(mode=0o700)
    result = {'schema': 1, 'state': 'RUNNING', 'started_utc': utc(), 'build_sha256': BUILD_SHA,
              'entry_review_sha256': REVIEW_SHA, 'runner_sha256': RUNNER_SHA, 'entry_qualification_sha256': ENTRY_SHA,
              'scope': 'Two fresh owned nondebug x86_64 Android app UIDs; no engine deployment or commercial app actions.',
              'arms': [], 'errors': [], 'recording_errors': [], 'production_ready': False,
              'known_red_boundaries_remain': ['initial NOFILE0 authority', 'first private-fork generation startup after NOFILE0',
                                             'trusted virtual O_PATH reopening unqualified'],
              'automatic_retry': False, 'production_source_changed': False}
    before = None
    def record(name, value):
        try:
            save(name, value)
        except Exception as error:
            result['recording_errors'].append({'file': name, 'error': repr(error)})
    def interrupted(number, frame):
        raise InterruptedError('owned Android cycle interrupted by signal ' + str(number))
    original_signals = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT)}
    def phase(arm, name, step, extra):
        root = ARM_ROOTS[arm]
        argv = ['/usr/bin/python3', '-I', str(RUNNER), name, '--kind', 'owner', '--root', str(root), '--step', step] + extra
        item = {'phase': name, 'argv': argv, 'started_utc': utc()}
        try:
            process = subprocess.run(argv, capture_output=True, timeout=95)
            record(arm + '-' + step + '.stdout', process.stdout)
            record(arm + '-' + step + '.stderr', process.stderr)
            item['returncode'] = process.returncode
            path = root / step / 'result.json'
            item['report'] = decode(path.read_bytes()) if path.is_file() else {'ok': False, 'outcome_unknown': True, 'missing_result': True}
        except BaseException as error:
            item.update(error=repr(error), report={'ok': False, 'outcome_unknown': True})
            if isinstance(error, subprocess.TimeoutExpired):
                record(arm + '-' + step + '-timeout.stdout', error.stdout or b'')
                record(arm + '-' + step + '-timeout.stderr', error.stderr or b'')
        item['finished_utc'] = utc()
        print(json.dumps({'arm': arm, 'phase': name, 'returncode': item.get('returncode'),
                          'ok': item['report'].get('ok'), 'outcome_unknown': item['report'].get('outcome_unknown')}), flush=True)
        return item
    try:
        before = fences(); record('resources-before.json', before)
        record('coordinator-claim.json', {'started_utc': utc(), 'build_sha256': BUILD_SHA, 'runner_sha256': RUNNER_SHA,
                                        'arms': {k: str(v) for k, v in ARM_ROOTS.items()}, 'nonces': NONCES,
                                        'no_automatic_retry': True, 'no_existing_package_replacement': True})
        need(not result['recording_errors'], 'claim or resource recording failed before any Android action')
        for arm in ('preimage', 'candidate'):
            item = {'arm': arm, 'root': str(ARM_ROOTS[arm]), 'steps': [], 'native_pass': False}
            result['arms'].append(item)
            ARM_ROOTS[arm].mkdir(mode=0o700)
            try:
                apk = build['arms'][arm]['APK']
                install = phase(arm, 'install', '01-install', ['--apk', apk['path'], '--apk-sha256', apk['sha256']])
                item['steps'].append(install)
                if install['report'].get('ok') is True and install.get('returncode') == 0:
                    run = phase(arm, 'run', '02-run', ['--nonce', NONCES[arm]])
                    item['steps'].append(run)
                    if run['report'].get('ok') is True and run.get('returncode') == 0:
                        try:
                            item['assessment'] = assess_instrumentation(arm, run['report'], cases)
                            item['native_pass'] = True
                        except Exception as error:
                            item['native_error'] = repr(error)
            finally:
                # A recording/assessment failure must never suppress exact removal.
                # The unchanged R4 remover independently rechecks UID/version/APK.
                if (ARM_ROOTS[arm] / 'install-verified.json').is_file():
                    previous = {number: signal.signal(number, signal.SIG_IGN) for number in original_signals}
                    try:
                        item['steps'].append(phase(arm, 'remove', '03-remove', []))
                    finally:
                        for number, handler in previous.items(): signal.signal(number, handler)
                else:
                    item['cleanup_error'] = 'No verified owned identity; no blind removal.'
            item['exact_owned_package_removed'] = any(s['phase'] == 'remove' and s.get('returncode') == 0 and
                                                       s['report'].get('only_exact_owned_package_removed') is True for s in item['steps'])
            item['transport_complete'] = len(item['steps']) == 3 and all(s.get('returncode') == 0 and
                                         s['report'].get('ok') is True and s['report'].get('outcome_unknown') is False and
                                         s['report'].get('framework_epoch_sha256') == EPOCH_SHA for s in item['steps'])
            record(arm + '-result.json', item)
            if not item['exact_owned_package_removed'] or not item['transport_complete'] or result['recording_errors']:
                raise RuntimeError('owned cycle not safely complete; the next APK arm was not started')
        need(len(result['arms']) == 2 and all(a['native_pass'] for a in result['arms']), 'native Android comparison did not pass')
    except BaseException as error:
        result['errors'].append(repr(error))
    finally:
        try:
            after = fences(); record('resources-after.json', after)
            need(before is not None, 'pre-execution resource snapshot missing')
            result['resource_fences'] = compare_fences(before, after)
            qualification()
            result['source_artifact_authority_unchanged_after'] = True
        except BaseException as error:
            result['errors'].append('final qualification: ' + repr(error))
        result['finished_utc'] = utc()
        complete = (len(result['arms']) == 2 and all(a.get('native_pass') and a.get('transport_complete') and
                    a.get('exact_owned_package_removed') for a in result['arms']) and
                    not result['errors'] and not result['recording_errors'])
        result['state'] = 'PASS_OWNED_ANDROID_26CASE_PAIR' if complete else 'FAILED_OR_INCOMPLETE_NO_RETRY'
        try:
            save('coordinator-result.json', result)
        finally:
            for number, handler in original_signals.items(): signal.signal(number, handler)
        print(json.dumps({'state': result['state'], 'errors': result['errors'],
                          'arms': [{k: a.get(k) for k in ('arm', 'native_pass', 'transport_complete', 'exact_owned_package_removed', 'native_error')}
                                   for a in result['arms']]}), flush=True)
    return 0 if complete else 1


if __name__ == '__main__':
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'arms': list(ARM_ROOTS), 'matching_build_sha256': BUILD_SHA,
                          'installed': False, 'Android_executed': False, 'Main_actions': 0, 'production_ready': False}))
    else:
        raise SystemExit(execute())
