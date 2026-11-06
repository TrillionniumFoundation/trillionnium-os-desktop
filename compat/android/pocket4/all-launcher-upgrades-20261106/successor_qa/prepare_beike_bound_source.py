#!/usr/bin/env python3
"""Publish new Beike QA source from one real successor and fresh native catalog.

Only status/applications use the original UID1000 native client. The original
scope reader and source generator run without build/install/UI/namespace entry.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

TARGET = 'com.lianjia.beike'
EXISTING_ACTIONS = 'local.pocket4.actions.v2'
PUBLIC_TEXT = '北京'
OPERATIONS = ['state', 'inspect', 'click', 'set_text']
RUNTIME_EPOCH = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'
BASE = '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01'
GUARD = {'path': BASE+'/current_baseline_guard.py', 'bytes': 3213,
         'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}
READER = {'path': BASE+'/source/observe_successor_scope.py', 'bytes': 7695,
          'sha256': '0a61313f518c7308f65f2654254689120df940cb0f5bd95d8873a42d6979914d'}
NATIVE_HELPERS = {'path': '/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/install_successor_native.py',
                  'bytes': 31327, 'sha256': 'ad4227b4c63033018bd1147c3c589b2632168766306791696aabc53583229c96'}
GENERATOR_ROOT = '/home/alex/work/pocket4-successor-qa-generator-source-r2-20261106-01'
GENERATOR = {'path': GENERATOR_ROOT+'/generate_successor_sources.py', 'bytes': 34825,
             'sha256': 'ec53b8444c068e58b0e8d9d8ae25321ed6dddbd7768f3b6a766a35fc1ed8f1ab'}
GENERATOR_MANIFEST = {'path': GENERATOR_ROOT+'/GENERATOR_PINS.json', 'bytes': 5098,
                      'sha256': 'ad32c98479cbb763c6c7728336f65a3e10dd1826de17ea43d0662599f7ce7436'}
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
LAUNCHERS = (
    'com.Hyatt.hyt', 'com.MobileTicket', 'com.amazon.mShop.android.shopping',
    'com.android.calendar', 'com.android.camera2', 'com.android.contacts', 'com.android.deskclock',
    'com.android.dialer', 'com.android.documentsui', 'com.android.gallery3d', 'com.android.messaging',
    'com.android.quicksearchbox', 'com.android.settings', 'com.android.threadnetwork.demoapp',
    'com.bestbuy.android', 'com.ehi.national.mobile', 'com.enflick.android.TextNow', 'com.google.android.gms',
    'com.hertz.android.digital', 'com.hilton.android.hhonors', 'com.ihg.apps.android', 'com.jingdong.app.mall',
    'com.lianjia.beike', 'com.marriott.mrt', 'com.pinger.textfree', 'com.rytong.airchina', 'com.rytong.ceair',
    'com.sankuai.meituan.takeoutnew', 'com.sdu.didi.psnger', 'com.ss.android.ugc.aweme', 'com.szzc',
    'com.taobao.taobao', 'com.tencent.mm', 'com.ubercab', 'com.united.mobile.android', 'com.xunmeng.pinduoduo',
    'com.zhubajie.client', 'com.zillow.android.streeteasy', 'ctrip.android.view', 'jp.co.ana.android.tabidachi',
    'local.pocket4.fixture', 'org.chromium.webview_shell', 'org.droidloom.qa.editorcontract',
    'org.fcitx.fcitx5.android', 'tv.danmaku.bili')


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(value):
        raise RuntimeError('NONFINITE_JSON_NUMBER')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_root_pin(pin, limit=262144):
    need(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'}, 'COMPLETE_SOURCE_PIN_REQUIRED')
    path = pin['path']
    need(type(path) is str and path.startswith('/') and all(x not in ('', '.', '..') for x in path[1:].split('/')),
         'CANONICAL_ABSOLUTE_PIN_PATH')
    need(type(pin['bytes']) is int and 0 < pin['bytes'] <= limit and
         re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'BOUNDED_EXACT_PIN_REQUIRED')
    descriptors = []
    try:
        parent = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC); descriptors.append(parent)
        parts = path[1:].split('/')
        for name in parts[:-1]:
            parent = os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        descriptors.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             before.st_size == pin['bytes'], 'EXACT_ROOT_OWNED_REGULAR_SOURCE_REQUIRED')
        raw, deadline = bytearray(), time.monotonic()+10
        while len(raw) <= limit:
            need(time.monotonic() < deadline, 'PIN_READ_DEADLINE')
            piece = os.read(fd, min(65536, limit+1-len(raw)))
            if not piece:
                break
            raw.extend(piece)
        current = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        descriptors.append(current)
        need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'] and
             all(getattr(before, key) == getattr(os.fstat(fd), key) == getattr(os.fstat(current), key) for key in STAT),
             'PINNED_SOURCE_OR_PATH_CHANGED')
        return bytes(raw)
    finally:
        errors = []
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, 'BOOTSTRAP_FDS_NOT_RETIRED')


def module(pin, name):
    raw = read_root_pin(pin)
    value = types.ModuleType(name); value.__file__ = pin['path']
    exec(compile(raw, pin['path'], 'exec'), value.__dict__)
    return value


def validate_request(request):
    need(type(request) is dict and set(request) == {'schema', 'guard', 'app_scope', 'generation_nonce',
         'package', 'public_text', 'allowed_operations', 'install_or_signature_evidence', 'output_root', 'coordination'},
         'CLOSED_BEIKE_SOURCE_REQUEST')
    need(request['schema'] == 'pocket4-beike-bound-qa-source-preparation-v1' and request['guard'] == GUARD and
         request['package'] == TARGET and request['public_text'] == PUBLIC_TEXT and request['allowed_operations'] == OPERATIONS,
         'ONLY_REVIEWED_BEIKE_PUBLIC_SOURCE_POLICY')
    nonce = request['generation_nonce']
    need(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce) and
         request['output_root'] == '/home/alex/work/pocket4-beike-successor-qa-input-20261106-'+nonce,
         'NEW_NONCE_AND_PREPARATION_ROOT_REQUIRED')
    need(type(request['app_scope']) is dict and set(request['app_scope']) == {'path', 'bytes', 'sha256'} and
         not request['app_scope']['path'].endswith('/initial-app-scope.private.json'), 'ACTUAL_FINAL_VERSIONED_APP_SCOPE_REQUIRED')
    evidence = request['install_or_signature_evidence']
    need(type(evidence) is list and 0 < len(evidence) <= 32 and
         all(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'} for pin in evidence), 'EXACT_REVIEWED_EVIDENCE_PINS_REQUIRED')
    need(request['coordination'] == {'single_coordinator': True, 'unresolved_native_install_jobs': []},
         'SETTLE_INSTALLS_BEFORE_SOURCE_BINDING')


def select_catalog(catalog, owner):
    need(type(catalog) is dict and catalog.get('ok') is True and catalog.get('state') == 'running' and
         catalog.get('host_pid') == owner and not catalog.get('outcome_unknown', False), 'ACTUAL_NATIVE_CATALOG_OWNER_REQUIRED')
    applications = catalog.get('applications')
    need(type(applications) is list and 0 < len(applications) <= 128, 'BOUNDED_ACTUAL_APPLICATION_CATALOG_REQUIRED')
    for row in applications:
        need(type(row) is dict and isinstance(row.get('package'), str) and isinstance(row.get('component'), str) and
             re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]+', row['package']) and
             re.fullmatch(re.escape(row['package'])+r'/[A-Za-z0-9_.$]+', row['component']), 'ACTUAL_COMPONENT_RECORD_FORMAT')
    components = sorted({row['component'] for row in applications if row['package'] == TARGET})
    need(len(components) == 1, 'NO_UNIQUE_OBSERVED_BEIKE_COMPONENT_NO_GUESS')
    actual = {row['package'] for row in applications}
    pairs = sorted({(row['package'], row['component']) for row in applications})
    return components[0], {'reference_packages': list(LAUNCHERS), 'actual_package_count': len(actual),
        'application_records': len(applications), 'added_packages': sorted(actual-set(LAUNCHERS)),
        'missing_packages': sorted(set(LAUNCHERS)-actual), 'package_component_sha256': sha(canonical(pairs)),
        'actual_package_components': [{'package': p, 'component': c} for p, c in pairs],
        'differences_preserved_without_rewriting_catalog': True}


def run(request):
    validate_request(request)
    need(os.getuid() == os.geteuid() == 0, 'EXISTING_ROOT_READ_ONLY_AUTHORITY_REQUIRED')
    started_fds = len(os.listdir('/proc/self/fd'))
    guard = module(GUARD, 'beike_actual_successor_guard')
    core = guard._core()
    reader = module(READER, 'beike_original_scope_reader')
    native_helpers = module(NATIVE_HELPERS, 'beike_existing_native_identity_helpers')
    generator = module(GENERATOR, 'beike_fixed_source_generator')
    read_root_pin(GENERATOR_MANIFEST)
    pool, leases = core.FDs(), core.FDs()
    result = {'schema': 'pocket4-beike-bound-qa-source-preparation-result-v1', 'ok': False,
        'automatic_retry': False, 'runtime_epoch_sha256': RUNTIME_EPOCH, 'package': TARGET,
        'UI_actions': 0, 'installs': 0, 'builds': 0, 'direct_namespace_entries': 0, 'ADB_commands': 0,
        'permission_changes': 0, 'lifecycle_commands': 0, 'business_data_content_reads': 0,
        'source_generation_attempted': False, 'source_identity_is_not_runtime_QA': True,
        'UI_or_install_runtime_admitted': False, 'production_ready': False, 'commands': [], 'errors': []}
    root, root_fd, root_identity, lock = None, None, None, None
    deadline = time.monotonic()+900
    def check_budget():
        need(time.monotonic() < deadline, 'SOURCE_PREPARATION_DEADLINE')
    def same_root():
        fd = core.open_host(pool, root, os.O_PATH | os.O_DIRECTORY)
        try:
            need(all(core.metadata(fd)[key] == root_identity[key] for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')),
                 'PRIVATE_PREPARATION_ROOT_CHANGED')
        finally:
            pool.close(fd)
    def write(name, raw):
        need(root is not None and '/' not in name and name not in ('', '.', '..'), 'OWNED_PREPARATION_FILE_ONLY')
        same_root()
        pin = core.write_new(root+'/'+name, raw)
        need(core.pinned_record(pin, max(len(raw), 1)) == raw, 'OWNED_PUBLICATION_READBACK')
        return pin
    def native_read(operation, held, files, pins, owner):
        need(operation in ('status', 'applications'), 'ONLY_CLOSED_NATIVE_READS')
        check_budget(); native_helpers.recheck_native(core, pool, held, files, pins)
        argv = core.as_user([native_helpers.CLI_PATH, '--socket', native_helpers.SOCKET_PATH, '--json', operation])
        raw, stderr, command = core.bounded_child(argv, seconds=30, limit=262144)
        index = len(result['commands'])+1
        streams = {'stdout_base64': base64.b64encode(raw).decode('ascii'),
                   'stderr_base64': base64.b64encode(stderr).decode('ascii'), 'stdout_bytes': len(raw),
                   'stderr_bytes': len(stderr), 'stdout_sha256': sha(raw), 'stderr_sha256': sha(stderr)}
        saved = write('native-%02d-%s.streams.json' % (index, operation), canonical(streams)+b'\n')
        result['commands'].append({'operation': operation, 'caller_uid': 1000, 'command': command, 'streams': saved})
        native_helpers.recheck_native(core, pool, held, files, pins)
        value = core.native_running(raw, command)
        need(value['host_pid'] == owner, 'NATIVE_OWNER_CHANGED_DURING_FRESH_CATALOG')
        need(guard.current_guard() == result['guard_before'], 'NATIVE_READ_RUNTIME_GUARD_CHANGED')
        return value, raw
    try:
        lock, result['action_lock_identity'] = core.acquire_lock(leases, core.ACTION_LOCK)
        result['guard_before'] = guard.current_guard()
        need(result['guard_before']['schema'] == 'pocket4-successor-main-guard-v1' and
             result['guard_before']['runtime_epoch_sha256'] == RUNTIME_EPOCH, 'EXACT_NEW_TYPED_RUNTIME_REQUIRED')
        baseline = guard.current_baseline()
        binding = baseline['runtime']['held']['process_snapshot']['binding']
        held = core.HeldProcesses(pool, {name: row['host_pid'] for name, row in binding['processes'].items()})
        need(held.before['binding'] == binding, 'EXACT_EIGHT_ROLE_BINDING_REQUIRED')
        core.verify_runtime(pool, held, baseline['runtime'])
        scope = parse(read_root_pin(request['app_scope']))
        need(scope.get('schema') == 'pocket4-versioned-app-scope-v1' and
             scope.get('runtime_epoch_sha256') == RUNTIME_EPOCH and
             set(scope['apps']) == set(LAUNCHERS) | {EXISTING_ACTIONS}, 'COMPLETE_FINAL_46_PACKAGE_SCOPE_REQUIRED')
        packages = sorted(scope['apps'])
        guard.check_app_scope(request['app_scope'], packages)
        core.app_scope(pool, held, packages, scope['apps'], False)
        for evidence in request['install_or_signature_evidence']:
            core.pinned_record(evidence)
        native_helpers.original_unknown(core)
        location = native_helpers.protected_location(core, pool, held, scope['apps'])
        files, native_pins = native_helpers.native_bind(core, pool, held)
        result['native_artifacts'] = native_pins
        owner = binding['processes']['launcher']['host_pid']
        root = request['output_root']
        core.create_private_root(root)
        root_fd = core.open_host(pool, root, os.O_RDONLY | os.O_DIRECTORY)
        root_identity = core.metadata(root_fd)
        result['request'] = write('request.json', canonical(request)+b'\n')
        result['worker_source'] = write('worker-source.py', core.host_read(str(Path(__file__).resolve()), 131072)[0])
        result['intent'] = write('source-preparation-intent.json', canonical({
            'schema': 'pocket4-source-only-preparation-intent-v1', 'request': result['request'],
            'single_fresh_native_catalog': True, 'only_target_package': TARGET,
            'source_output': '/home/alex/work/pocket4-successor-qa-source-'+request['generation_nonce'],
            'build_install_UI_admitted': False, 'automatic_retry': False})+b'\n')
        result['native_before'], _ = native_read('status', held, files, native_pins, owner)
        catalog, catalog_raw = native_read('applications', held, files, native_pins, owner)
        result['native_framework_catalog_query_confirmed'] = True
        catalog_pin = write('native-catalog.stdout.raw.json', catalog_raw)
        result['launcher_catalog'] = catalog_pin
        result['launcher_catalog_raw_utf8'] = catalog_raw.decode('utf-8', 'strict')
        component, result['catalog_comparison'] = select_catalog(catalog, owner)
        result['component'] = component
        result['native_after_catalog'], _ = native_read('status', held, files, native_pins, owner)
        check_budget()
        observation_request = {'schema': 'pocket4-successor-app-observation-request-v1', 'guard': GUARD,
            'packages': sorted([TARGET, EXISTING_ACTIONS]), 'parent_app_scope': request['app_scope'],
            'install_or_signature_evidence': request['install_or_signature_evidence'],
            'output_scope': root+'/beike-and-existing-actions.private.json',
            'output_binding': root+'/qa-build-input.private.json'}
        result['observation_request'] = write('observation-request.json', canonical(observation_request)+b'\n')
        observed = reader.run(observation_request)
        result['observation_result'] = write('observation-result.json', canonical(observed)+b'\n')
        need(observed.get('ok') is True and observed['observation_fds']['remaining'] == 0 and
             observed['observation_fds']['acquired'] == observed['observation_fds']['closed'] and
             observed['observation_fds']['errors'] == [], 'ACTUAL_OBSERVATION_AND_FD_RETIREMENT_REQUIRED')
        observed_scope = parse(core.pinned_record(observed['app_scope']))
        need(core.app_bytes(observed_scope['apps']) == core.app_bytes({name: scope['apps'][name] for name in (TARGET, EXISTING_ACTIONS)}),
             'NEW_OBSERVATION_DIFFERS_FROM_FINAL_APP_SCOPE')
        source_request = {'schema': 'pocket4-successor-qa-source-request-v1',
            'qa_build_input': observed['qa_build_input'], 'launcher_catalog': catalog_pin,
            'package': TARGET, 'component': component, 'generation_nonce': request['generation_nonce'],
            'public_text': PUBLIC_TEXT, 'allowed_operations': OPERATIONS,
            'output_root': '/home/alex/work/pocket4-successor-qa-source-'+request['generation_nonce']}
        generator.validate_request(source_request)
        result['generation_request'] = write('generation-request.json', canonical(source_request)+b'\n')
        guard.check_app_scope(request['app_scope'], packages)
        check_budget(); result['source_generation_attempted'] = True
        generated = generator.generate(source_request, GENERATOR_MANIFEST['sha256'])
        result['generation'] = generated
        need(generated.get('ok') is True and generated.get('build_performed') is False and
             generated.get('install_performed') is False and generated.get('UI_actions') == 0 and
             generated.get('source_identity_is_not_runtime_QA') is True, 'SOURCE_GENERATION_ONLY_REQUIRED')
        for name in ('recorder_manifest', 'helper_manifest', 'build_plan', 'result'):
            core.pinned_record(generated[name])
        for pin in (GUARD, READER, NATIVE_HELPERS, GENERATOR, GENERATOR_MANIFEST):
            read_root_pin(pin)
        generator.reference_closure(GENERATOR_MANIFEST['sha256'])
        for evidence in request['install_or_signature_evidence']:
            core.pinned_record(evidence)
        native_helpers.original_unknown(core)
        need(native_helpers.protected_location(core, pool, held, scope['apps']) == location, 'MEITUAN_LOCATION_FLAGS_CHANGED')
        result['meituan_saved_location_unchanged'] = True
        result['old_Bili_unknown_evidence_unchanged'] = True
        result['native_final'], _ = native_read('status', held, files, native_pins, owner)
        guard.check_app_scope(request['app_scope'], packages)
        core.app_scope(pool, held, packages, scope['apps'], False)
        core.verify_runtime(pool, held, baseline['runtime'])
        native_helpers.recheck_native(core, pool, held, files, native_pins)
        result['guard_after'] = guard.current_guard()
        need(result['guard_after'] == result['guard_before'], 'FINAL_SOURCE_PREPARATION_GUARD_CHANGED')
        same_root(); result['complete_46_app_scope_unchanged'] = True
        result['ok'] = True
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:300]})
    finally:
        if lock is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN); result['action_lock_released'] = True
            except BaseException as error:
                result['ok'] = False; result['errors'].append({'stage': 'unlock', 'type': type(error).__name__})
        for label, group in (('observation_fds', pool), ('lease_fds', leases)):
            try:
                group.close_all()
            except BaseException as error:
                result['ok'] = False; result['errors'].append({'stage': label, 'type': type(error).__name__})
            result[label] = group.summary()
        result['process_fd_count_before'] = started_fds
        result['process_fd_count_after'] = len(os.listdir('/proc/self/fd'))
        if result['process_fd_count_after'] != started_fds:
            result['ok'] = False; result['errors'].append({'stage': 'process_fd_count', 'type': 'DescriptorDifference'})
        result['status'] = 'FRESH_BEIKE_QA_SOURCE_PUBLISHED_ANDROID_UNRUN' if result['ok'] else 'SOURCE_PREPARATION_INCOMPLETE_NO_RETRY'
        if root_identity is not None:
            try:
                raw = canonical(result)+b'\n'
                need(len(raw) <= 196608, 'PREPARATION_RESULT_BOUND')
                result['final_receipt'] = core.write_new(root+'/result.json', raw)
                need(core.pinned_record(result['final_receipt'], 196608) == raw, 'FINAL_RESULT_READBACK')
            except BaseException as error:
                result['ok'] = False; result['status'] = 'SOURCE_PREPARATION_RECEIPT_FAILED'
                result['errors'].append({'stage': 'final_receipt', 'type': type(error).__name__})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--request-bytes', required=True, type=int)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        request = parse(read_root_pin({'path': args.request, 'sha256': args.request_sha256, 'bytes': args.request_bytes}))
        result = run(request)
    except BaseException as error:
        result = {'schema': 'pocket4-beike-qa-source-entry-rejection-v1', 'ok': False,
            'type': type(error).__name__, 'reason': str(error)[:300], 'UI_actions': 0, 'installs': 0, 'builds': 0,
            'automatic_retry': False, 'UI_or_install_runtime_admitted': False, 'production_ready': False}
    raw = canonical(result)
    need(len(raw) <= 196608, 'STDOUT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
