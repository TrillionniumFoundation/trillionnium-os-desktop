#!/usr/bin/python3 -I
"""Frozen current-Gallery video-and-seek entry; inspection has no live side effects."""
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
TRANSPORT_ROOT = FINAL / 'qualification/gallery-rotation-current-preparation-20261107-r7'
TRANSPORT_PREPARATION = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-rotation-current-preparation-20261107-r7/preparation.json', 'bytes': 10488, 'sha256': '41d16fa49e5bec646824ba2308037d975076008adb4740b7ee773b6c5f9907ac'}
TRANSPORT_ENTRY = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-rotation-current-preparation-20261107-r7/source/gallery_rotation_entry.py', 'bytes': 14884, 'sha256': '99b18c7c860f1913df25a56606ad236ddd0d67dad038c7de4b8c9d76023ab3bd'}
PRIOR = {'bytes': 67738, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/550d1525bd28cd07-result.json', 'sha256': '550d1525bd28cd074d3317dd4e3c3c38c43e78924209612a751d01bbb7c787fb'}
ORIGINALS = {'diagnostics_source.py': {'bytes': 31308, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/93cf4567c19f6033-diagnostics_source.py', 'sha256': '93cf4567c19f6033dce0b120d068a7120a2b27952a4a1d0d4cfdd8b988ebfbcb'}, 'gallery_base.py': {'bytes': 23888, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/06a182dae066e4d1-gallery_base.py', 'sha256': '06a182dae066e4d1c9d0387371711145754378747e561f16543e5315051aefb2'}, 'package_fixture.py': {'bytes': 9973, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/5cb30798c5ce70e5-package_fixture.py', 'sha256': '5cb30798c5ce70e5dd56175e7a7d4382908086f30c3cbeda16b6dc10c18ab068'}, 'run_saf10.py': {'bytes': 36496, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/d1426a5d52e80d40-run_saf10.py', 'sha256': 'd1426a5d52e80d4064430070193e5b4c083f69ae7b7a44a733e6cbb413edaae4'}, 'run_video01.py': {'bytes': 33524, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/7d3e8e81c36eb18a-run_video01.py', 'sha256': '7d3e8e81c36eb18a4d0f1c46c23e37ec2ba657fc885f2e5197cfb730c4657d26'}, 'runtime_evidence.py': {'bytes': 15114, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/670af6f9a2ecd165-runtime_evidence.py', 'sha256': '670af6f9a2ecd16591babc3e40387dc6f25474d27f73fc93f42b881d3d60d5df'}, 'ui_preflight04.py': {'bytes': 23786, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/d02821d751736a9e-ui_preflight04.py', 'sha256': 'd02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58'}, 'verify_pattern.py': {'bytes': 3231, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/80cd758ca6da90fa-verify_pattern.py', 'sha256': '80cd758ca6da90fa404368907fc645adb9524b86be96966dc328599c2e8f7e7f'}, 'verify_video.py': {'bytes': 2254, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/2b52f1514fff4507-verify_video.py', 'sha256': '2b52f1514fff4507a9618ac5695d0dd64820f2e34f9c242cb5d640f6c79fe93d'}}
EXTERNALS = {'contract.json': {'bytes': 1069, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/repro/video-fixture-source/contract.json', 'sha256': '8bd567bc9c495ba191d81220676db901ac60b964f349843d2aff12578564800b'}, 'fixture-build-result.json': {'bytes': 34019, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/fixtures/video/build-result.json', 'sha256': '632e5c0aa13a758f7245939b227577c1b8416a3c950e55eddbc5e0bb61d735b9'}, 'frozen-video-preparation': {'bytes': 10172, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-video-current-preparation-20261107-r1/preparation.json', 'sha256': 'c0e245aee94ed56d5b9b8257e118025fe245490cd8c6bf41e73275cd9b6f2ead'}, 'movie-source-result.json': {'bytes': 24856, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/inputs/current-movie-source.json', 'sha256': 'ac4dee6dda805bd163fc0a4274e5c15a173b9fb2224e65113852aa51676d670f'}, 'owned-media.apk': {'bytes': 139532, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/fixtures/video/owned-media.apk', 'sha256': '7fc4dadcc33c94cd41d0425473622df38138d60801c2e5585c4d28cf7db68933'}, 'seek-source-extract': {'bytes': 27922, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-seek-source-review-20261107-r1/seek-source-extract.json', 'sha256': '4527235b6ec7ca199b915f215e9e3819be66a54a97c8c04d8e75e807aaa846e7'}, 'task-option-proof.json': {'bytes': 17797, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/fixtures/9cb008b7050d3bb0-task-option-proof.json', 'sha256': '9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'}}
EXTERNALS.update({'frozen-video-preparation': {'path': str(FINAL / 'qualification/gallery-video-current-preparation-20261107-r1/preparation.json'), 'bytes': 10172, 'sha256': 'c0e245aee94ed56d5b9b8257e118025fe245490cd8c6bf41e73275cd9b6f2ead'},
    'seek-source-extract': {'path': str(FINAL / 'qualification/gallery-seek-source-review-20261107-r1/seek-source-extract.json'), 'bytes': 27922, 'sha256': '4527235b6ec7ca199b915f215e9e3819be66a54a97c8c04d8e75e807aaa846e7'}})
SOURCE_NAMES = {'video_seek.py', 'video_policy.py', 'verify_video.py', 'video_diagnostics.py', 'video_case.py', 'video_runtime.py', 'video_fixture.py', 'video_session.py', 'verify_pattern.py', 'video_entry.py', 'video_identity.py', 'video_flow.py', 'video_base.py', 'video_ui.py'}
META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


SUPPORT_MIGRATION_HELPER = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/gallery_qpr1_binding_migration_r2.py', 'bytes': 8713, 'sha256': 'a80d9491c62f5e925a8949cb16c95591515fc299f0722cda93193b78965a586b'}
SUPPORT_MIGRATION_BASE = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-seek-current-preparation-20261107-r4/preparation.json', 'bytes': 12558, 'sha256': 'dd47fc01d54e3b321d7c72bb899f63f2371c015087ce97de5e7c1f6e2bdc1e05'}


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
    prepared = json.loads(read(preparation_ref))
    need(prepared['schema'] == 'pocket4-gallery-seek-current-preparation-v1'
        and prepared['state'] == 'ORIGINAL_VIDEO_AND_REVIEWED_SEEK_HOST_BOUNDARIES_QUALIFIED_ACTUAL_MAIN_PENDING'
        and prepared['actual_Main_execution_pending'] is True and prepared['whole_app_business_accepted'] is False
        and prepared['historical_runtime_authority_transferred'] is False
        and prepared['current_installation_preparation'] == CURRENT_PREPARATION
        and prepared['transport_preparation'] == TRANSPORT_PREPARATION
        and prepared['prior_cleanup'] == PRIOR and prepared['original_source_refs'] == ORIGINALS
        and prepared['external_fixture_refs'] == EXTERNALS and set(prepared['files']) == SOURCE_NAMES,
        'EXACT_CURRENT_VIDEO_SOURCE_PREPARATION')
    source_root = Path(preparation_ref['path']).parent / 'source'
    need(Path(__file__).resolve() == source_root / 'video_entry.py'
        and source_root.parent.parent == FINAL / 'qualification' and re.fullmatch(
            'gallery-seek-current-preparation-20261107-r[0-9]+', source_root.parent.name),
        'ONLY_THE_FROZEN_CURRENT_VIDEO_ENTRY')
    # Admit all externally pinned source bytes before executing any task code.
    for name, ref in prepared['files'].items():
        need(ref['path'] == str(source_root / name), 'NO_EXTERNAL_VIDEO_TASK_MODULES'); read(ref, 262144)
    for ref in [*ORIGINALS.values(), *EXTERNALS.values(), PRIOR, CURRENT_PREPARATION,
                TRANSPORT_PREPARATION, TRANSPORT_ENTRY]:
        read(ref, 262144)
    migrated = module(SUPPORT_MIGRATION_HELPER, 'gallery_support_migration')
    migration_base = migrated.verify(prepared['support_migration'], prepared, read, SUPPORT_MIGRATION_BASE, 'video_entry.py', SUPPORT_MIGRATION_HELPER)
    controls = json.loads(read(prepared['qualified_host_controls']))
    need(controls['schema'] == 'pocket4-gallery-current-seek-host-controls-v1'
        and controls['state'] == 'HOST_BOUNDARIES_PASSED' and controls['passed'] == controls['total']
        and controls['total'] > 0 and controls['source_files'] == migration_base['files']
        and controls['transport_preparation'] == migration_base['transport_preparation']
        and controls['all_actual_owned_trees_retired'] is True
        and controls['Main_actions'] == controls['Android_actions'] == controls['package_mutations'] == 0,
        'ACTUAL_EXACT_CURRENT_VIDEO_HOST_CONTROLS_REQUIRED')
    transport_entry = module(TRANSPORT_ENTRY, 'gallery_video_qualified_transport_entry')
    transport, support, common, original_modules, held, current_modules, shared, transport_guard = (
        transport_entry.bootstrap(TRANSPORT_PREPARATION))
    need(transport['current_installation_preparation'] == CURRENT_PREPARATION,
        'SAME_CURRENT_GALLERY_INSTALLATION_AND_TRANSPORT')
    guard_refs = [preparation_ref, CURRENT_PREPARATION, TRANSPORT_PREPARATION, TRANSPORT_ENTRY, PRIOR,
        prepared['qualified_host_controls'], *ORIGINALS.values(), *EXTERNALS.values(), *prepared['files'].values()]
    def source_guard():
        transport_guard()
        for ref in guard_refs:
            read(ref)
    components = {name: module(ref, 'gallery_video_component_' + name[:-3])
                  for name, ref in prepared['files'].items() if name != 'video_entry.py'}
    components.update(shared_case=shared['gallery_rotation_case.py'],
        shared_session=shared['gallery_rotation_session.py'], shared_api=shared['gallery_rotation_api.py'])
    return prepared, support, common, original_modules, held, current_modules, components, source_guard


def resource_admission():
    need(os.getuid() == os.geteuid() == 0, 'ROOT_CURRENT_VIDEO_CONTROLLER_REQUIRED')
    current = Path('/proc/self/cgroup').read_text().strip()
    need(current.startswith('0::/') and current != '0::/', 'OWN_BOUNDED_VIDEO_JOB_REQUIRED')
    group = Path('/sys/fs/cgroup') / current[3:].lstrip('/')
    need(group.name.startswith('hepta-runtime-job-') and (group / 'memory.max').read_text().strip() == '2147483648',
         'EXACT_PRIVATE_TWO_GIB_VIDEO_JOB')
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
            'original_business_scope': 'owned silent video pixels, pause, resume, normal reopen, midpoint seek and exact cleanup',
            'audio_output_qualified': False, 'seek_qualified': False, 'album_enumeration_qualified': False,
            'original_business_seconds': 600, 'original_cleanup_seconds': 120,
            'Main_actions': 0, 'Android_actions': 0, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    need(args.request and args.expect_request_sha256, 'EXPLICIT_FRESH_MAIN_VIDEO_REQUEST')
    request_ref = supplied(args.request, args.expect_request_sha256); request = c.parse(read(request_ref, 131072))
    need(set(request) == {'schema', 'baseline', 'qualification', 'installation', 'output'}
        and request['schema'] == 'pocket4-gallery-current-seek-request-v1', 'EXACT_CURRENT_VIDEO_REQUEST_FIELDS')
    for key in ('baseline', 'qualification', 'installation'):
        need(type(request[key]) is dict and request[key]['path'].startswith(str(FINAL / 'qualification') + '/'),
            'ACTUAL_FINAL_RUNTIME_QUALIFICATION_REFERENCES_ONLY'); read(request[key])
    root = Path(request['output'])
    need(root.parent == FINAL / 'qualification' and re.fullmatch('gallery-current-seek-20261107-r[0-9]+', root.name)
        and not os.path.lexists(root), 'FRESH_CREATE_ONLY_VIDEO_RESULT_REQUIRED')
    for prefix, expected in [('gallery-current-video-20261107-r*',
            'CURRENT_MAIN_VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED'),
            ('gallery-current-seek-20261107-r*', components['video_case.py'].SUCCESS)]:
        for other in root.parent.glob(prefix):
            if other == root:
                continue
            previous = c.parse(c.regular(other / 'result.json', 4 * 1024 * 1024)[0])
            need(previous.get('state') == expected and previous.get('outcome_unknown') is False,
                'PRIOR_CURRENT_VIDEO_OR_SEEK_REQUIRES_EXPLICIT_RECONCILIATION')
    resource_admission(); support.resources()
    cancelled = []; handlers = {}; phase = 'entry'; committed = False; result = None; created = False
    def cancel(number, frame):
        nonlocal phase
        cancelled.append(number)
        if not committed and phase == 'action':
            phase = 'converging'; raise Cancelled('CURRENT_VIDEO_CANCELLED_BEFORE_PUBLICATION')
    def enter_retirement():
        nonlocal phase
        phase = 'converging'
    for number in (signal.SIGINT, signal.SIGTERM):
        handlers[number] = signal.getsignal(number); signal.signal(number, cancel)
    try:
        c.private_dir(root, create=True); created = True
        c.write_new(root / 'request.json', request)
        c.write_new(root / 'entry-intent.json', {'schema': 'pocket4-gallery-current-seek-entry-intent-v1',
            'request': request_ref, 'preparation': preparation_ref, 'automatic_retry': False})
        phase = 'action'
        try:
            need(not cancelled, 'CANCELLED_BEFORE_CURRENT_VIDEO')
            result = components['video_case.py'].execute(request, preparation_ref, root, c, support,
                originals, held, CURRENT_PREPARATION, current_modules, components, source_guard, PRIOR, cancelled,
                enter_retirement)
        finally:
            phase = 'converging'
        source_guard(); read(request_ref, 131072)
        need(type(result) is dict, 'COMPLETE_ORIGINAL_CURRENT_VIDEO_RESULT_REQUIRED')
    except BaseException as error:
        if result is None:
            result = {'schema': 'pocket4-gallery-current-owned-video-seek-v1', 'state': 'UNKNOWN_NO_AUTOMATIC_REPLAY',
                'outcome_unknown': created, 'whole_app_business_accepted': False, 'automatic_retry': False,
                'source_preparation': preparation_ref, 'request': request_ref}
        result['entry_error'] = type(error).__name__ + ':' + str(error)
        if result.get('state') == components['video_case.py'].SUCCESS:
            result['state'] = 'FAILED'
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        pending = signal.sigpending() & {signal.SIGINT, signal.SIGTERM}
        result['entry_cancellation_signals'] = list(cancelled) + sorted(pending)
        if result['entry_cancellation_signals'] and result['state'] == components['video_case.py'].SUCCESS:
            result['state'] = 'FAILED'; result['cancellation_precluded_pass'] = True
        result['entry_finished_unix_ns'] = time.time_ns()
        if created:
            c.write_new(root / 'result.json', result)
        committed = True
        print(json.dumps({'state': result['state'], 'result': None if not created else c.regular(root / 'result.json', contents=False),
            'outcome_unknown': result.get('outcome_unknown', False), 'whole_app_business_accepted': False}, sort_keys=True))
        return 0 if result['state'] == components['video_case.py'].SUCCESS else 1
    finally:
        # Owned retirement already ended. Commit/readback failure preserves the
        # durable intent and never starts another cleanup or automatic replay.
        # Keep cancellation blocked until this dedicated process exits, even
        # if terminal serialization failed.
        phase = 'terminal'


if __name__ == '__main__':
    raise SystemExit(main())
