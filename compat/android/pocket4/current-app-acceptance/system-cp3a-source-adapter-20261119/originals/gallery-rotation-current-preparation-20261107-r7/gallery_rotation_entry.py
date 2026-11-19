#!/usr/bin/python3 -I
"""Frozen current-Gallery rotation entry; inspection has no live side effects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import time
import types

FINAL = Path('/home/alex/work/pocket4-android-final')
CURRENT_ROOT = FINAL / 'qualification/gallery-new-runtime-preparation-20261107-r7'
CURRENT_PREPARATION = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-new-runtime-preparation-20261107-r7/preparation.json', 'bytes': 8898, 'sha256': 'dc50b4a6abb81c6c203cf1eca2de8f62d7c350bd35cbb0f6bff2725aa4f3cb18'}
CURRENT_ENTRY = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-new-runtime-preparation-20261107-r7/source/gallery_current_entry.py', 'bytes': 18187, 'sha256': '0e8f214ee884586bfb1da812b48b5f71995899d7b097bffc01daf209c9bf7425'}
PRIOR = {'path': str(FINAL / 'qualification/gallery-rotation-prior-reconciliation-20261107-r2/result.json'),
    'bytes': 69198, 'sha256': 'ebd4ce9a89d80ddd8d33a93d9561e826b97d09c97d5ba94c37223dcc1ebe9357'}
SYSTEM_API = {'path': str(FINAL / 'qualification/business-system-cases-frozen-resume-20261107-r1/source/system_ui.py'),
    'bytes': 11407, 'sha256': 'c0f431942857047f5540dc9dc66d5f992aefb436b60bbb5e7417e0e1ac0b58c8'}
ORIGINAL_ROOT = Path('/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/rotation-original')
ORIGINALS = {
    'run_rotation06.py': (32544, 'e26aa7cd23d94213630d6b04d3c78a473561a5b0316d2efcf56ae29396fe3f56'),
    'rotation_ui.py': (36431, 'd290900f48d3c1f27b8d13b5efee0978bd5ebba365023d440f354c8a8ffdc7f4'),
    'rotation_package.py': (10876, '44abbfe0193905a7b3a6137b4bb95dafc8d6cec4d795e8b258b97508cdd83dd4'),
    'owned_media.py': (20857, '95b6c90fbc9ac22c41ca2c35d9ba3a13ce140de9cc52f710f2b5fd080506ae9b'),
    'verify_rotation.py': (4638, '934c70dd3e3f9c4174aaafbbb47b5ee8b2eb195d15c4fa18d2891ec995973093'),
    'bounded_diagnostics.py': (6528, 'c0eaf47627b31793b3c90d875ce74761ae9c98e749fc437a422e73c2da66a947')}
SOURCE_NAMES = {'gallery_rotation_entry.py', 'gallery_rotation_case.py', 'gallery_rotation_session.py',
    'gallery_rotation_policy.py', 'gallery_rotation_api.py', 'gallery_rotation_flow.py',
    'rotation_ui.py', 'rotation_package.py', 'owned_media.py', 'verify_rotation.py', 'bounded_diagnostics.py'}
META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


SUPPORT_MIGRATION_HELPER = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/gallery_qpr1_binding_migration_r2.py', 'bytes': 8713, 'sha256': 'a80d9491c62f5e925a8949cb16c95591515fc299f0722cda93193b78965a586b'}
SUPPORT_MIGRATION_BASE = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-rotation-current-preparation-20261107-r5/preparation.json', 'bytes': 9624, 'sha256': '4b3d93532451d2f196c1965ac7c773fa6b1f823279516e594085cd0d74001533'}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(reference, maximum=4 * 1024 * 1024):
    need(type(reference) is dict and set(reference) == {'path', 'bytes', 'sha256'}
        and type(reference['bytes']) is int and 0 < reference['bytes'] <= maximum
        and re.fullmatch('[0-9a-f]{64}', reference['sha256']) is not None, 'EXACT_FROZEN_GALLERY_REFERENCE')
    path = Path(reference['path']); need(path.is_absolute() and path.resolve() == path, 'CANONICAL_FROZEN_GALLERY_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd); need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
            and before.st_size == reference['bytes'], 'FROZEN_GALLERY_FILE_SHAPE')
        raw = bytearray()
        while len(raw) < before.st_size:
            part = os.read(fd, min(65536, before.st_size - len(raw))); need(part, 'SHORT_FROZEN_GALLERY_READ'); raw.extend(part)
        need(os.read(fd, 1) == b'' and sha(raw) == reference['sha256']
            and all(getattr(before, key) == getattr(os.fstat(fd), key) == getattr(path.lstat(), key) for key in META),
            'FROZEN_GALLERY_INPUT_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def supplied(path, expected):
    need(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected), 'EXTERNAL_EXPECTED_SHA_REQUIRED')
    return {'path': str(Path(path)), 'bytes': Path(path).lstat().st_size, 'sha256': expected}


def module(ref, name):
    raw = read(ref, 262144); value = types.ModuleType(name); value.__file__ = ref['path']
    exec(compile(raw, ref['path'], 'exec'), value.__dict__); return value


def bootstrap(preparation_ref):
    raw = read(preparation_ref); prepared = json.loads(raw)
    need(prepared['schema'] == 'pocket4-gallery-rotation-current-preparation-v1'
        and prepared['state'] == 'ORIGINAL_BUSINESS_SOURCES_AND_HOST_BOUNDARIES_QUALIFIED_ACTUAL_MAIN_PENDING'
        and prepared['actual_Main_execution_pending'] is True and prepared['whole_app_business_accepted'] is False
        and prepared['historical_runtime_authority_transferred'] is False
        and prepared['current_installation_preparation'] == CURRENT_PREPARATION
        and prepared['prior_cleanup'] == PRIOR and prepared['original_api_source'] == SYSTEM_API
        and set(prepared['files']) == SOURCE_NAMES, 'EXACT_CURRENT_ROTATION_SOURCE_PREPARATION')
    source_root = Path(preparation_ref['path']).parent / 'source'
    need(Path(__file__).resolve() == source_root / 'gallery_rotation_entry.py'
        and source_root.parent.parent == FINAL / 'qualification' and re.fullmatch(
            'gallery-rotation-current-preparation-20261107-r[0-9]+', source_root.parent.name),
        'ONLY_THE_FROZEN_CURRENT_ROTATION_ENTRY')
    # Check all external expectations and all task bytes before executing even
    # one task module. A self-reported internal manifest is never authority.
    for name, ref in prepared['files'].items():
        need(ref['path'] == str(source_root / name), 'NO_EXTERNAL_GALLERY_TASK_MODULES'); read(ref, 262144)
    originals = {name: {'path': str(ORIGINAL_ROOT / name), 'bytes': values[0], 'sha256': values[1]}
                 for name, values in ORIGINALS.items()}
    need(prepared['original_source_refs'] == originals, 'EXACT_ORIGINAL_ROTATION_SOURCE_CUSTODY')
    for ref in originals.values():
        read(ref, 262144)
    read(PRIOR); read(SYSTEM_API); read(CURRENT_PREPARATION); read(CURRENT_ENTRY)
    migrated = module(SUPPORT_MIGRATION_HELPER, 'gallery_support_migration')
    migration_base = migrated.verify(prepared['support_migration'], prepared, read, SUPPORT_MIGRATION_BASE, 'gallery_rotation_entry.py', SUPPORT_MIGRATION_HELPER)
    controls = json.loads(read(prepared['qualified_host_controls']))
    need(controls['schema'] == 'pocket4-gallery-current-rotation-host-controls-v1'
        and controls['state'] == 'HOST_BOUNDARIES_PASSED' and controls['passed'] == controls['total']
        and controls['total'] > 0 and controls['source_files'] == migration_base['files']
        and controls['all_actual_owned_trees_retired'] is True
        and controls['Main_actions'] == controls['Android_actions'] == controls['package_mutations'] == 0,
        'ACTUAL_EXACT_CURRENT_GALLERY_HOST_CONTROLS_REQUIRED')
    current_entry = module(CURRENT_ENTRY, 'gallery_rotation_qualified_installation_entry')
    current, support, common, original_modules, held, current_modules = current_entry.bootstrap(CURRENT_PREPARATION)
    guard_refs = [preparation_ref, CURRENT_PREPARATION, CURRENT_ENTRY, PRIOR, SYSTEM_API,
        prepared['qualified_host_controls'], *originals.values(), *prepared['files'].values(), *current['files'].values()]
    def source_guard():
        for ref in guard_refs:
            read(ref)
    components = {name: module(ref, 'gallery_rotation_component_' + name[:-3])
                  for name, ref in prepared['files'].items() if name != 'gallery_rotation_entry.py'}
    # The caller map includes only task modules; entry and supplied JSON cannot
    # introduce a callable into the original business scope.
    return prepared, support, common, original_modules, held, current_modules, components, source_guard


def resource_admission():
    need(os.getuid() == os.geteuid() == 0, 'ROOT_CURRENT_ROTATION_CONTROLLER_REQUIRED')
    current = Path('/proc/self/cgroup').read_text().strip()
    need(current.startswith('0::/') and current != '0::/', 'OWN_BOUNDED_ROTATION_JOB_REQUIRED')
    group = Path('/sys/fs/cgroup') / current[3:].lstrip('/')
    need(group.name.startswith('hepta-runtime-job-') and (group / 'memory.max').read_text().strip() == '2147483648',
         'EXACT_PRIVATE_TWO_GIB_ROTATION_JOB')
    (group / 'memory.swap.max').write_text('0'); (group / 'pids.max').write_text('64')
    os.sched_setaffinity(0, {20}); resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class Cancelled(BaseException):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True); parser.add_argument('--expect-preparation-sha256', required=True)
    parser.add_argument('mode', choices=('inspect', 'execute'), nargs='?', default='inspect')
    parser.add_argument('--request'); parser.add_argument('--expect-request-sha256')
    args = parser.parse_args(); preparation_ref = supplied(args.preparation, args.expect_preparation_sha256)
    prepared, support, c, originals, held, current_modules, components, source_guard = bootstrap(preparation_ref)
    if args.mode == 'inspect':
        need(args.request is None and args.expect_request_sha256 is None, 'INSPECTION_HAS_NO_LIVE_REQUEST')
        print(json.dumps({'state': prepared['state'], 'preparation': preparation_ref,
            'original_required_gates': sorted(components['gallery_rotation_flow.py'].REQUIRED),
            'original_business_seconds': 600, 'original_cleanup_seconds': 120,
            'Main_actions': 0, 'Android_actions': 0, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    need(args.request and args.expect_request_sha256, 'EXPLICIT_FRESH_MAIN_ROTATION_REQUEST')
    request_ref = supplied(args.request, args.expect_request_sha256); request = c.parse(read(request_ref, 131072))
    need(set(request) == {'schema', 'baseline', 'qualification', 'installation', 'output'}
        and request['schema'] == 'pocket4-gallery-current-rotation-request-v1', 'EXACT_CURRENT_ROTATION_REQUEST_FIELDS')
    for key in ('baseline', 'qualification', 'installation'):
        need(type(request[key]) is dict and request[key]['path'].startswith(str(FINAL / 'qualification') + '/'),
            'ACTUAL_FINAL_RUNTIME_QUALIFICATION_REFERENCES_ONLY'); read(request[key])
    root = Path(request['output'])
    need(root.parent == FINAL / 'qualification' and re.fullmatch('gallery-current-rotation-20261107-r[0-9]+', root.name)
        and not os.path.lexists(root), 'FRESH_CREATE_ONLY_ROTATION_RESULT_REQUIRED')
    for other in root.parent.glob('gallery-current-rotation-20261107-r*'):
        if other == root:
            continue
        previous = c.parse(c.regular(other / 'result.json', 4 * 1024 * 1024)[0])
        need(previous.get('state') == components['gallery_rotation_case.py'].SUCCESS
            and previous.get('outcome_unknown') is False, 'PRIOR_CURRENT_ROTATION_REQUIRES_EXPLICIT_RECONCILIATION')
    resource_admission(); support.resources()
    cancelled = []; handlers = {}; phase = 'entry'; committed = False; result = None; created = False
    def cancel(number, frame):
        nonlocal phase
        cancelled.append(number)
        if not committed and phase == 'action':
            phase = 'converging'; raise Cancelled('CURRENT_ROTATION_CANCELLED_BEFORE_PUBLICATION')
    def enter_retirement():
        nonlocal phase
        phase = 'converging'
    for number in (signal.SIGINT, signal.SIGTERM):
        handlers[number] = signal.getsignal(number); signal.signal(number, cancel)
    try:
        c.private_dir(root, create=True); created = True
        c.write_new(root / 'request.json', request)
        c.write_new(root / 'entry-intent.json', {'schema': 'pocket4-gallery-current-rotation-entry-intent-v1',
            'request': request_ref, 'preparation': preparation_ref, 'automatic_retry': False})
        phase = 'action'
        try:
            need(not cancelled, 'CANCELLED_BEFORE_CURRENT_ROTATION')
            result = components['gallery_rotation_case.py'].execute(request, preparation_ref, root, c, support,
                originals, held, CURRENT_PREPARATION, current_modules, components, source_guard, PRIOR, cancelled,
                enter_retirement)
        finally:
            phase = 'converging'
        source_guard(); read(request_ref, 131072)
        need(type(result) is dict, 'COMPLETE_ORIGINAL_CURRENT_ROTATION_RESULT_REQUIRED')
    except BaseException as error:
        if result is None:
            result = {'schema': 'pocket4-current-owned-gallery-jpeg-rotation-v1', 'state': 'UNKNOWN_NO_AUTOMATIC_REPLAY',
                'outcome_unknown': created, 'whole_app_business_accepted': False, 'automatic_retry': False,
                'source_preparation': preparation_ref, 'request': request_ref}
        result['entry_error'] = type(error).__name__ + ':' + str(error)
        if result.get('state') == components['gallery_rotation_case.py'].SUCCESS:
            result['state'] = 'FAILED'
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        pending = signal.sigpending() & {signal.SIGINT, signal.SIGTERM}
        result['entry_cancellation_signals'] = list(cancelled) + sorted(pending)
        if result['entry_cancellation_signals'] and result['state'] == components['gallery_rotation_case.py'].SUCCESS:
            result['state'] = 'FAILED'; result['cancellation_precluded_pass'] = True
        result['entry_finished_unix_ns'] = time.time_ns()
        if created:
            c.write_new(root / 'result.json', result)
        committed = True
        print(json.dumps({'state': result['state'], 'result': None if not created else c.regular(root / 'result.json', contents=False),
            'outcome_unknown': result.get('outcome_unknown', False), 'whole_app_business_accepted': False}, sort_keys=True))
        return 0 if result['state'] == components['gallery_rotation_case.py'].SUCCESS else 1
    finally:
        # Owned retirement already ended. Commit/readback failure preserves the
        # durable intent and never starts another cleanup or automatic replay.
        # Keep cancellation blocked until this dedicated process exits, even
        # if terminal serialization failed.
        phase = 'terminal'


if __name__ == '__main__':
    raise SystemExit(main())
