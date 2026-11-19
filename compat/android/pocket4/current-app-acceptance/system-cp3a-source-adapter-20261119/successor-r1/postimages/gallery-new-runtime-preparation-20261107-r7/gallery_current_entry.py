#!/usr/bin/python3 -I
"""Frozen Gallery new-Main entry. Default inspection performs no live action."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import signal
import stat
import sys
import time
import types

FINAL = Path('/home/alex/work/pocket4-android-final')
SOURCE_NAMES = {'gallery_current_entry.py', 'gallery_runtime_support_current.py',
                'gallery_current_closure.py', 'gallery_current_verify.py',
                'gallery_current_install.py', 'gallery_oat_status_current.py'}
META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')


SUPPORT_MIGRATION_HELPER = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/gallery_qpr1_binding_migration_r2.py', 'bytes': 8713, 'sha256': 'a80d9491c62f5e925a8949cb16c95591515fc299f0722cda93193b78965a586b'}
SUPPORT_MIGRATION_BASE = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-new-runtime-preparation-20261107-r5/preparation.json', 'bytes': 7293, 'sha256': '87028049e98d5abce0ded3fefe4b8fe73721e9e57f973e9945e83aa19e740783'}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(info):
    return tuple(getattr(info, name) for name in META)


def read(reference, maximum=2 * 1024 * 1024):
    need(type(reference) is dict and set(reference) == {'path', 'bytes', 'sha256'}
         and type(reference['bytes']) is int and 0 < reference['bytes'] <= maximum
         and re.fullmatch(r'[0-9a-f]{64}', reference['sha256']), 'EXACT_FROZEN_REFERENCE_REQUIRED')
    path = Path(reference['path'])
    need(path.is_absolute() and path.resolve() == path, 'CANONICAL_FROZEN_INPUT_REQUIRED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and before.st_size == reference['bytes'], 'FROZEN_INPUT_SHAPE')
        chunks = []; total = 0
        while total < before.st_size:
            block = os.read(fd, min(65536, before.st_size - total))
            need(block, 'FROZEN_INPUT_SHORT_READ'); chunks.append(block); total += len(block)
        raw = b''.join(chunks)
        need(os.read(fd, 1) == b'' and sha(raw) == reference['sha256']
             and metadata(before) == metadata(os.fstat(fd)) == metadata(path.lstat()),
             'FROZEN_INPUT_CHANGED')
        return raw
    finally:
        os.close(fd)


def supplied_ref(path, digest):
    need(re.fullmatch(r'[0-9a-f]{64}', digest) is not None, 'EXPLICIT_EXPECTED_HASH_REQUIRED')
    path = Path(path)
    return {'path': str(path), 'bytes': path.lstat().st_size, 'sha256': digest}


def module(reference, name):
    raw = read(reference, 262144)
    value = types.ModuleType(name); value.__file__ = reference['path']
    exec(compile(raw, reference['path'], 'exec'), value.__dict__)
    return value


def bootstrap(reference):
    raw = read(reference); preparation = json.loads(raw)
    need(preparation['schema'] == 'pocket4-gallery-current-runtime-preparation-v1'
         and preparation['state'] == 'SOURCE_AND_HOST_BOUNDARIES_QUALIFIED_PENDING_ACTUAL_MAIN'
         and preparation['actual_Main_execution_pending'] is True
         and preparation['historical_runtime_authority_transferred'] is False
         and preparation['whole_app_business_accepted'] is False
         and set(preparation['files']) == SOURCE_NAMES, 'COMPLETE_NEW_GALLERY_SOURCE_PACKET_REQUIRED')
    source_root = Path(reference['path']).parent / 'source'
    need(Path(__file__).resolve() == source_root / 'gallery_current_entry.py'
         and source_root.parent.parent == FINAL / 'qualification'
         and re.fullmatch(r'gallery-new-runtime-preparation-20261107-r[0-9]+', source_root.parent.name),
         'EXACT_FROZEN_ENTRY_LOCATION_REQUIRED')
    for name, ref in preparation['files'].items():
        need(ref['path'] == str(source_root / name), 'NO_EXTERNAL_PACKET_CODE')
        read(ref, 262144)
    migrated = module(SUPPORT_MIGRATION_HELPER, 'gallery_support_migration')
    migration_base = migrated.verify(preparation['support_migration'], preparation, read, SUPPORT_MIGRATION_BASE, 'gallery_current_entry.py', SUPPORT_MIGRATION_HELPER)
    support = module(preparation['files']['gallery_runtime_support_current.py'], 'gallery_current_support')
    common, originals, held = support.bootstrap()
    need(preparation['common_preparation'] == support.APP_PREPARATION_REF
         and preparation['original_sources'] == support.ORIGINALS, 'ORIGINAL_PROVENANCE_BINDING_CHANGED')
    parser = common.parse(common.read_ref(preparation['parser_qualified_controls']))
    parser_inputs = common.parse(common.read_ref(preparation['qpr1_parser_inputs']))
    for ref in parser_inputs['files'].values():
        common.read_ref(ref)
    need(parser_inputs['schema'] == 'gallery-qpr1-parser-current-inputs-v1'
         and parser_inputs['controls'] == preparation['parser_qualified_controls']
         and parser_inputs['current_parser']['sha256'] == preparation['files']['gallery_oat_status_current.py']['sha256']
         and parser['schema'] == 'gallery-qpr1-parser-synthetic-controls-v1'
         and parser['passed'] is True and parser['tests_run'] == 17
         and parser['failures'] == parser['errors'] == parser['skipped'] == 0
         and parser['fixture_expected_classes'] == 2144
         and parser['historical_controls_transferred'] is False
         and parser['actual_oatdump_executed'] is parser['runtime_qualified'] is False
         and parser['Main_actions'] == parser['Android_actions'] == 0,
         'CURRENT_QPR1_SEVENTEEN_SYNTHETIC_PARSER_CONTROLS_REQUIRED')
    host_refs = preparation['qpr1_host_inputs']
    host_controls = common.parse(common.read_ref(host_refs['controls']))
    host_publication = common.parse(common.read_ref(host_refs['publication']))
    common.read_ref(host_refs['contract'])
    need(host_controls['schema'] == 'QPR1-Gallery-current-host-leaf-controls-v1'
         and host_controls['passed'] is True and host_controls['passed_count'] == host_controls['total'] == 14
         and host_controls['skipped'] == host_controls['old_root_opens'] == 0
         and all(row['passed'] is True for row in host_controls['controls'])
         and host_controls['Main_actions'] == host_controls['Android_actions'] == host_controls['runtime_acceptance_count'] == 0
         and host_controls['contract'] == host_refs['contract']
         and host_publication['actual_host_leaf_controls'] == host_refs['controls']
         and host_publication['contract'] == host_refs['contract'],
         'ACTUAL_COMPLETE_CURRENT_QPR1_HOST_LEAF_CONTROLS_REQUIRED')
    current_host = originals['install'].host_evidence()
    need(current_host == host_publication['actual_host_evidence'],
         'ACTUAL_CURRENT_QPR1_HOST_INPUTS_MUST_STILL_MATCH')
    transport = common.parse(common.read_ref(preparation['transport_qualified_controls']))
    need(transport['schema'] == 'pocket4-gallery-current-transport-host-controls-v1'
         and transport['state'] == 'HOST_CONTROLS_PASSED'
         and transport['source_sha256'] == migration_base['files']['gallery_runtime_support_current.py']['sha256']
         and transport['passed'] == transport['total'] and transport['total'] > 0
         and all(row['passed'] is True for row in transport['cases'])
         and transport['all_actual_owned_trees_retired'] is True
         and transport['Android_actions'] == transport['Main_actions'] == 0,
         'ACTUAL_CURRENT_TRANSPORT_HOST_BOUNDARIES_REQUIRED')
    loaded = {key: module(preparation['files'][name], 'gallery_current_' + key) for key, name in
              [('closure', 'gallery_current_closure.py'), ('verify', 'gallery_current_verify.py'),
               ('install', 'gallery_current_install.py'), ('parser', 'gallery_oat_status_current.py')]}
    return preparation, support, common, originals, held, loaded


class ControllerCancelled(BaseException):
    pass


def failed_install_pending(root, created, initial_identity, result):
    """Recover only this invocation's intent when execute() did not publish.

    Presence alone is enough to refuse replay. A partial/unreadable marker or
    lost output-directory identity cannot prove that no dispatch occurred.
    No old output directory, marker contents or guessed default is authority.
    """
    observation = {'path': str(root / 'install-pending.json'),
                   'marker_contents_used_as_authority': False}
    attempted = result.get('install_attempts')
    known_attempt = type(attempted) is int and attempted > 0
    possible = known_attempt or result.get('installed') is True or result.get('outcome_unknown') is True
    if not created:
        observation['state'] = 'THIS_OUTPUT_NOT_CREATED_NO_EXECUTE_DISPATCH'
    else:
        try:
            current = root.lstat()
            directory_identity = (current.st_dev, current.st_ino, current.st_mode,
                                  current.st_uid, current.st_gid)
            need(stat.S_ISDIR(current.st_mode) and directory_identity == initial_identity,
                 'FRESH_OUTPUT_DIRECTORY_IDENTITY_CHANGED')
            try:
                marker = (root / 'install-pending.json').lstat()
            except FileNotFoundError:
                current = root.lstat()
                need((current.st_dev, current.st_ino, current.st_mode, current.st_uid, current.st_gid)
                     == initial_identity, 'FRESH_OUTPUT_DIRECTORY_CHANGED_DURING_ABSENCE_CHECK')
                observation['state'] = 'ABSENT_IN_SAME_FRESH_OUTPUT'
            else:
                observation.update(state='PRESENT_DO_NOT_REPLAY', bytes=marker.st_size,
                                   mode=marker.st_mode, device=marker.st_dev, inode=marker.st_ino)
                possible = True
                # This counts the durable install intent, not a proven Popen.
                attempted = max(attempted if type(attempted) is int else 0, 1)
        except BaseException as error:
            observation.update(state='UNOBSERVABLE_DO_NOT_REPLAY',
                               error=type(error).__name__ + ':' + str(error))
            possible = True
            if not known_attempt:
                attempted = None
    result['entry_install_pending_observation'] = observation
    if possible:
        result.update(state='INSTALL_ATTEMPTED_OUTCOME_UNKNOWN_NO_AUTOMATIC_REPLAY',
                      install_attempts=attempted, install_attempt_count_known=type(attempted) is int,
                      install_pending=True, outcome_unknown=True, automatic_retry=False)
    else:
        result.update(install_attempts=0, install_attempt_count_known=True,
                      install_pending=False, outcome_unknown=False)


def main():
    raise RuntimeError('CP3A_OFFICIAL_FULL_GSI_ONLY_OLD_MODIFIED_CANDIDATE_RUNTIME_ENTRY_RETIRED')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True)
    parser.add_argument('--expect-preparation-sha256', required=True)
    parser.add_argument('mode', choices=('inspect', 'verify', 'install'), nargs='?', default='inspect')
    parser.add_argument('--request')
    parser.add_argument('--expect-request-sha256')
    args = parser.parse_args()
    preparation_ref = supplied_ref(args.preparation, args.expect_preparation_sha256)
    preparation, support, common, originals, held, modules = bootstrap(preparation_ref)
    if args.mode == 'inspect':
        need(args.request is None and args.expect_request_sha256 is None, 'INSPECTION_HAS_NO_LIVE_REQUEST')
        print(json.dumps({'state': 'SOURCE_AND_HOST_BOUNDARIES_QUALIFIED_PENDING_ACTUAL_MAIN',
            'preparation': preparation_ref, 'modes': ['verify', 'install'],
            'Android_actions': 0, 'Main_actions': 0, 'package_mutations': 0,
            'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    need(os.getuid() == os.geteuid() == 0 and args.request and args.expect_request_sha256,
         'ROOT_AND_EXPLICIT_LIVE_REQUEST_REQUIRED')
    request_ref = supplied_ref(args.request, args.expect_request_sha256)
    request = common.parse(read(request_ref, 131072))
    expected_fields = {'schema', 'baseline', 'qualification', 'output'}
    if args.mode == 'install':
        expected_fields.add('art_qualification')
    need(set(request) == expected_fields and request['schema'] == 'pocket4-gallery-current-' + args.mode + '-request-v1',
         'EXACT_TYPED_GALLERY_REQUEST_REQUIRED')
    for name in expected_fields - {'schema', 'output'}:
        ref = request[name]
        need(type(ref) is dict and ref['path'].startswith(str(FINAL / 'qualification') + '/'),
             'ACTUAL_FINAL_QUALIFICATION_REFERENCE_REQUIRED')
        common.read_ref(ref)
    root = Path(request['output'])
    need(root.parent == FINAL / 'qualification' and re.fullmatch(
        r'gallery-current-' + args.mode + r'-20261107-r[0-9]+', root.name), 'FRESH_FIXED_GALLERY_OUTPUT_LOCATION')
    need(not os.path.lexists(root), 'EXCLUSIVE_ONCE_ONLY_OUTPUT_REQUIRED')
    cancelled = []; old_handlers = {}; result = None; created = False; commit = False
    phase = 'entry'; initial_output_identity = None

    def cancellation(number, frame):
        nonlocal phase
        cancelled.append(number)
        if not commit and phase == 'action':
            # Change phase before raising: repeated cancellation cannot interrupt
            # execute's retirement or this entry's error convergence.
            phase = 'converging'
            raise ControllerCancelled('CONTROLLER_CANCELLED_BEFORE_PUBLICATION_BOUNDARY')

    for number in (signal.SIGINT, signal.SIGTERM):
        old_handlers[number] = signal.getsignal(number); signal.signal(number, cancellation)
    try:
        common.private_dir(root, create=True); created = True
        info = root.lstat()
        initial_output_identity = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)
        common.write_new(root / 'request.json', request)
        common.write_new(root / 'entry-intent.json', {'schema': 'pocket4-gallery-current-entry-intent-v1',
            'mode': args.mode, 'request': request_ref, 'preparation': preparation_ref,
            'source': preparation['files']['gallery_current_entry.py'], 'automatic_retry': False})
        phase = 'action'
        try:
            need(not cancelled, 'CONTROLLER_CANCELLED_BEFORE_ACTION')
            if args.mode == 'verify':
                result = modules['verify'].execute(request, preparation_ref, root, common, originals,
                                                   held, support, modules['closure'], modules['parser'])
            else:
                result = modules['install'].execute(request, preparation_ref, root, common, originals,
                                                    held, support, modules['closure'])
        finally:
            phase = 'converging'
        for ref in preparation['files'].values():
            read(ref, 262144)
        read(preparation_ref)
        read(request_ref, 131072)
    except BaseException as error:
        phase = 'converging'
        if result is None:
            result = {'schema': 'pocket4-gallery-current-entry-failure-v1', 'state': 'FAILED',
                'mode': args.mode, 'request': request_ref, 'preparation': preparation_ref,
                'automatic_retry': False, 'whole_app_business_accepted': False}
        else:
            result['state'] = 'FAILED_AFTER_ACTION_SOURCE_OR_REQUEST_CHECK'
            if result.get('install_attempts'):
                result['install_pending'] = result['outcome_unknown'] = True
        result['entry_error'] = type(error).__name__ + ':' + str(error)
    finally:
        # Freeze the decision only after execute() returned and every normal
        # context exit/postcheck completed. Signals already pending at this
        # boundary prevent a PASS. Later signals cannot split a saved success
        # from a contradictory exit status. A PASS independently requires the
        # completed command receipts, closed session, and normal context exits.
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        pending = sorted(signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
        commit = True
    if result is None:
        result = {'schema': 'pocket4-gallery-current-entry-failure-v1', 'state': 'FAILED_NO_RESULT',
                  'mode': args.mode, 'automatic_retry': False, 'whole_app_business_accepted': False}
    result['entry_cancellation'] = {'observed_before_commit': cancelled, 'pending_at_commit': pending,
                                  'decision_frozen_after_context_exit': True}
    if cancelled or pending:
        if result['state'] == modules['install'].ART_STATE:
            result['state'] = 'CANCELLED_BEFORE_QUALIFICATION_PUBLICATION'
        elif result['state'] == 'CURRENT_ART_VERIFIED_GALLERY_INSTALLED_ALL_PROTECTED_IDENTITY_PRESERVED':
            result['state'] = 'CANCELLED_AFTER_PROTECTED_INSTALL_COMPLETION'
    if args.mode == 'install' and result['state'] != 'CURRENT_ART_VERIFIED_GALLERY_INSTALLED_ALL_PROTECTED_IDENTITY_PRESERVED':
        failed_install_pending(root, created, initial_output_identity, result)
    if not created:
        print(json.dumps({'state': result['state'], 'error': result.get('entry_error'),
                          'new_output_created': False}, sort_keys=True))
        return 130 if cancelled or pending else 1
    receipt = common.write_new(root / 'result.json', result)
    passed = result['state'] in {modules['install'].ART_STATE,
                                'CURRENT_ART_VERIFIED_GALLERY_INSTALLED_ALL_PROTECTED_IDENTITY_PRESERVED'}
    print(json.dumps({'state': result['state'], 'result': receipt, 'mode': args.mode,
        'installed': result.get('installed', False), 'outcome_unknown': result.get('outcome_unknown', False),
        'whole_app_business_accepted': False}, sort_keys=True), flush=True)
    return 0 if passed else (130 if cancelled or pending else 1)


if __name__ == '__main__':
    raise SystemExit(main())
