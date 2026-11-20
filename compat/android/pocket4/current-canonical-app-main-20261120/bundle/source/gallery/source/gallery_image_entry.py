#!/usr/bin/python3 -I
"""Original-image Gallery inspection and four bounded existing business cases.

Source inspection is inert. Execute takes the current qualified Main
baseline, its qualification, the adopted native release and a fresh output directory. There is no argument
for a saved custody receipt, Gallery install, replacement APK, socket or PID.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import types

ROOT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/gallery')
FINAL=Path('/var/lib/droidloom/qualification/pocket4')
CASES = {'identity', 'rotation', 'video', 'seek', 'album'}
META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')
CLI_PATH = '/usr/bin/droidloom-applications'
SOCKET = '/run/droidloom/control.sock'
CUSTODY_PROTOCOL = 'droidloom-image-application-custody-v1'
COMMON={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/shared/app_common.py', 'bytes': 44516, 'sha256': '682e0805008846437882162bf4b21fdd4982937c1003a5804f64d7aa4d2e2211'}
HELD={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main/held_runtime.py', 'bytes': 27507, 'sha256': '6f0951391d95baa2e548826d3d7700b634ef89f1a6770d8a6d45b9e6eaaddd4e'}


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def parse(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    def nonfinite(value):
        raise RuntimeError('NONFINITE_JSON')
    return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs, parse_constant=nonfinite)


def read(ref, maximum=4*1024*1024):
    need(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'}
         and type(ref['bytes']) is int and 0 < ref['bytes'] <= maximum
         and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}', ref['sha256']),
         'EXTERNALLY_PINNED_BOUNDED_REFERENCE_REQUIRED')
    path = Path(ref['path'])
    need(path.is_absolute() and path.resolve() == path, 'CANONICAL_PINNED_FILE_REQUIRED')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == ref['bytes'],
             'EXACT_SINGLE_LINK_SOURCE_REQUIRED')
        body = bytearray()
        while len(body) < before.st_size:
            part = os.read(fd, min(65536, before.st_size-len(body)))
            need(part, 'SHORT_PINNED_FILE_READ'); body.extend(part)
        need(os.read(fd, 1) == b'' and hashlib.sha256(body).hexdigest() == ref['sha256']
             and all(getattr(before, key) == getattr(os.fstat(fd), key) == getattr(path.lstat(), key)
                     for key in META), 'PINNED_FILE_CHANGED')
        return bytes(body)
    finally:
        os.close(fd)


def supplied(path, expected):
    need(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected), 'EXTERNAL_EXPECTED_SHA_REQUIRED')
    return {'path': str(Path(path)), 'bytes': Path(path).lstat().st_size, 'sha256': expected}


def module(ref, name):
    raw = read(ref, 262144)
    value = types.ModuleType(name); value.__file__ = ref['path']
    exec(compile(raw, ref['path'], 'exec'), value.__dict__)
    return value


def bootstrap(preparation_ref):
    preparation = parse(read(preparation_ref))
    need(type(preparation) is dict and preparation['schema'] == 'pocket4-gallery-image-source-v1'
         and preparation['case'] in CASES
         and preparation['state'] == 'CURRENT_IMAGE_CONSUMER_SOURCE_PREPARED_RUNTIME_PENDING'
         and preparation['producer_cli_path'] == CLI_PATH and preparation['control_socket'] == SOCKET
         and preparation['custody_protocol'] == CUSTODY_PROTOCOL and preparation['native_release_required'] is True
         and preparation['common'] == COMMON and preparation['held'] == HELD
         and preparation['runtime_qualified'] is False and preparation['business_qualified'] is False
         and preparation['data_continuity_qualified'] is False and preparation['production_ready'] is False
         and preparation['historical_runtime_authority_transferred'] is False,
         'EXACT_IMAGE_SOURCE_PREPARATION_WITH_NO_RUNTIME_CREDIT')
    need(Path(preparation_ref['path']) == ROOT.parent.parent/'preparations'/('gallery-'+preparation['case']+'.json')
         and Path(__file__).resolve() == ROOT/'source/gallery_image_entry.py', 'EXACT_NEW_IMAGE_ENTRY_LOCATION')
    files = preparation['files']
    need(type(files) is dict and files and all(type(name) is str and '..' not in name.split('/')
         and Path(ref['path']) == ROOT/name for name, ref in files.items()), 'CLOSED_NEW_IMAGE_SOURCE_GRAPH')
    need(files['source/gallery_image_entry.py']['path'] == str(Path(__file__).resolve())
         and 'source/gallery_image_custody.py' in files
         and 'source/native_release_guard.py' in files
         and 'generated/shared/gallery_image_identity.py' in files
         and 'generated/shared/gallery_image_support.py' in files,
         'ALL_NEW_IMAGE_CONSUMERS_MUST_BE_PINNED')
    # Read every expected source before importing the first one. Old standalone
    # install/ART/retired entry modules are excluded from this graph.
    for name, ref in files.items():
        need(name.endswith('.py') and not name.endswith(('gallery_current_entry.py', 'gallery_current_install.py',
             'gallery_current_verify.py', 'gallery_rotation_entry.py', 'video_entry.py')),
             'RETIRED_GALLERY_ENTRY_CANNOT_BE_REACTIVATED')
        read(ref, 262144)
    read(COMMON); read(HELD)
    external = preparation['external_refs']
    need(type(external) is list, 'EXPLICIT_ORIGINAL_FIXTURE_AND_API_REFERENCES')
    for ref in external:
        read(ref)
    guard_refs = [preparation_ref, COMMON, HELD, *files.values(), *external]
    def source_guard():
        for ref in guard_refs:
            read(ref)
    c = module(COMMON, 'current_image_common')
    held = module(HELD, 'current_image_held_runtime')
    support = module(files['generated/shared/gallery_image_support.py'], 'current_image_resources')
    identity = module(files['generated/shared/gallery_image_identity.py'], 'current_image_identity')
    custody = module(files['source/gallery_image_custody.py'], 'current_image_native_custody')
    modules = {name: module(ref, 'current_image_'+name.replace('/', '_').replace('.', '_'))
               for name, ref in files.items() if name.startswith('generated/rotation/')}
    shared = {Path(name).name: value for name, value in modules.items()}
    selected = preparation['case']
    if selected in ('video', 'seek', 'album'):
        components = {Path(name).name: module(ref, 'current_'+selected+'_'+Path(name).stem)
                      for name, ref in files.items() if name.startswith('generated/'+selected+'/')}
        components.update(shared_case=shared['gallery_rotation_case.py'],
                          shared_session=shared['gallery_rotation_session.py'], shared_api=shared['gallery_rotation_api.py'])
    else:
        components = shared
    # Original support bootstrap remains a real, unmodified code gate. This
    # does not instantiate a MainView or qualify an Android generation.
    c.support(c.SUPPORT_REF)
    source_guard()
    return preparation, c, held, support, identity, custody, components, source_guard


def validate_request(request, case):
    need(type(request) is dict and set(request) == {'schema', 'baseline', 'qualification', 'output', 'native_release'}
         and request['schema'] == 'pocket4-gallery-image-request-v1', 'NO_IMPORTED_IMAGE_RECEIPT_OR_INSTALL_REQUEST')
    for key in ('baseline', 'qualification'):
        need(type(request[key]) is dict and Path(request[key]['path']).is_relative_to(FINAL),
             'CURRENT_FINAL_MAIN_QUALIFICATION_ONLY')
        read(request[key])
    root = Path(request['output'])
    need(root.parent == FINAL and re.fullmatch('gallery-image-'+case+'-20261120-r[0-9]+', root.name)
         and not os.path.lexists(root), 'FRESH_CREATE_ONLY_IMAGE_BUSINESS_RESULT')
    # A previous attempt's unknown effect is never silently superseded.
    for earlier in FINAL.glob('gallery-image-'+case+'-20261120-r*'):
        result_path = earlier/'result.json'
        need(result_path.is_file(), 'PRIOR_IMAGE_ATTEMPT_HAS_NO_TERMINAL_RECONCILIATION')
        raw = result_path.read_bytes()
        need(len(raw) <= 4*1024*1024, 'BOUNDED_PRIOR_IMAGE_RESULT')
        previous = parse(raw)
        need(previous.get('state') in ('CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED',
                                     'CURRENT_IMAGE_OBSERVED_BUSINESS_PENDING')
             and previous.get('outcome_unknown') is False,
             'PRIOR_IMAGE_ATTEMPT_REQUIRES_EXPLICIT_RECONCILIATION')
    return root


def resource_admission(release):
    need(os.getuid() == os.geteuid() == 0, 'ORIGINAL_ROOT_BUSINESS_CONTROLLER_REQUIRED')
    # The native parent creates and owns the bounded child. Admission must
    # prove that live relationship and local controls before business starts;
    # the consumer never repairs shared ancestors or accepts only a name.
    return release.admit_owned_leaf_resources()


def native_observation(c, custody, source_guard, cli_pin, request, root, name):
    journal = c.private_dir(root/name, create=True)
    def no_android_dispatch(*unused):
        raise RuntimeError('IMAGE_CAPTURE_USES_ONLY_ORIGINAL_DAEMON_INSPECTION')
    view = None
    try:
        view = c.MainView(request['baseline'], request['qualification'], journal,
                          no_android_dispatch, support_ref=c.SUPPORT_REF)
        return custody.capture(c, view, source_guard, cli_pin, SOCKET, journal)
    finally:
        if view is not None:
            view.close()


class Cancelled(BaseException):
    pass


def execute(preparation_ref, preparation, c, held, support, identity, custody, components,
            source_guard, request_ref, request, root):
    native_release = module(preparation['files']['source/native_release_guard.py'], 'current_native_leaf_release_guard')
    static_source_guard = source_guard
    # Preserve the actual lease object through both complete image captures,
    # the unchanged business/cleanup phases and final source/result publication.
    # Nested native readers use the same shared original lock order.
    with native_release.bind_release(request['native_release'], preparation_ref) as release:
        resource_scope = resource_admission(release)
        need(type(resource_scope) is native_release.OwnedLeafResources, 'EXACT_LIVE_NATIVE_RESOURCE_SCOPE_CLASS')
        support.bind_resource_scope(resource_scope); support.resources()
        cli_pin = dict(release.cli_reference)
        def bound_source_guard():
            static_source_guard()
            need(release.guard() == cli_pin, 'ADOPTED_NATIVE_BINARY_PIN_CHANGED')
        bound_source_guard()
        return execute_bound(preparation_ref, preparation, c, held, support, identity, custody, components,
                             bound_source_guard, request_ref, request, root, cli_pin)


def execute_bound(preparation_ref, preparation, c, held, support, identity, custody, components,
                  source_guard, request_ref, request, root, cli_pin):
    cancelled = []; previous_handlers = {}; phase = 'capture'; result = {
        'schema': 'pocket4-gallery-image-scope-v1', 'state': 'FAILED', 'case': preparation['case'],
        'request': request_ref, 'source_preparation': preparation_ref,
        'baseline': request['baseline'], 'qualification': request['qualification'],
        'native_release': request['native_release'],
        'business_scope_completed': False,
        'runtime_qualified': False, 'business_qualified': False, 'data_continuity_qualified': False,
        'production_ready': False, 'whole_app_business_accepted': False,
        'historical_runtime_authority_transferred': False, 'automatic_retry': False,
        'Gallery_install_attempts': 0, 'original_business_seconds': 600, 'original_cleanup_seconds': 120,
        'each_current_image_capture_seconds': custody.CAPTURE_SECONDS, 'outcome_unknown': False}
    def cancel(number, frame):
        cancelled.append(number)
        if phase != 'retirement':
            raise Cancelled('CURRENT_IMAGE_SCOPE_CANCELLED')
    def enter_retirement():
        nonlocal phase
        phase = 'retirement'
    for number in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[number] = signal.getsignal(number); signal.signal(number, cancel)
    c.private_dir(root, create=True)
    try:
        c.write_new(root/'request.json', request)
        c.write_new(root/'entry-intent.json', {'request': request_ref, 'source_preparation': preparation_ref,
                                             'automatic_retry': False, 'Gallery_install_attempts': 0})
        before = native_observation(c, custody, source_guard, cli_pin, request, root, 'image-before')
        result['image_before'] = before.reference
        if preparation['case'] == 'identity':
            result['state'] = 'CURRENT_IMAGE_OBSERVED_BUSINESS_PENDING'
        else:
            phase = 'business'
            case_name = 'gallery_rotation_case.py' if preparation['case'] == 'rotation' else 'video_case.py'
            case = components[case_name]
            business = case.execute(request, preparation_ref, root, c, support, {'identity': identity}, held,
                                    before, components, source_guard, preparation['prior_cleanup'],
                                    cancelled, enter_retirement)
            result['business'] = business
            result['outcome_unknown'] = business.get('outcome_unknown') is not False
            need(business.get('state') == case.SUCCESS and business.get('outcome_unknown') is False,
                 'ORIGINAL_FINITE_BUSINESS_AND_COMPLETE_CLEANUP_REQUIRED')
            need(not cancelled, 'CANCELLED_BUSINESS_CANNOT_RECEIVE_IMAGE_ACCEPTANCE')
            phase = 'capture-after'
            after = native_observation(c, custody, source_guard, cli_pin, request, root, 'image-after')
            result['image_after'] = after.reference
            before.same_images(after)
            result['current_image_owner_and_complete_bytes_preserved'] = True
            result['business_scope_completed'] = True
            result['state'] = 'CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED'
        source_guard(); read(request_ref)
        result['resources_after'] = support.resources()
    except BaseException as error:
        result['state'] = 'FAILED'; result['error'] = type(error).__name__ + ':' + str(error)
        observation = getattr(error, 'command_observation', {})
        result['outcome_unknown'] |= phase == 'business' or bool(
            observation.get('spawned') and observation.get('host_retirement_proved') is not True)
    finally:
        phase = 'retirement'
        result['cancelled_signals'] = list(cancelled)
        result['entry_cancellation_signals'] = list(cancelled)
        if cancelled:
            result['state'] = 'FAILED'
        result['completed_unix_ns'] = time.time_ns()
        for number, previous in previous_handlers.items():
            signal.signal(number, previous)
    # Source-only and finite-scope success never promotes whole-application,
    # persistent-data, runtime-release or production gates.
    source_guard()
    result_ref = c.write_new(root/'result.json', result)
    print(json.dumps({'state': result['state'], 'case': result['case'], 'result': result_ref,
                      'runtime_qualified': False, 'production_ready': False,
                      'whole_app_business_accepted': False,
                      'outcome_unknown': result['outcome_unknown']}, sort_keys=True))
    return 0 if result['state'] != 'FAILED' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True); parser.add_argument('--expect-preparation-sha256', required=True)
    parser.add_argument('mode', choices=('inspect-source', 'execute'), nargs='?', default='inspect-source')
    parser.add_argument('--request'); parser.add_argument('--expect-request-sha256')
    args = parser.parse_args()
    ref = supplied(args.preparation, args.expect_preparation_sha256)
    prepared, c, held, support, identity, custody, components, source_guard = bootstrap(ref)
    if args.mode == 'inspect-source':
        need(args.request is None and args.expect_request_sha256 is None, 'SOURCE_INSPECTION_HAS_NO_LIVE_REQUEST')
        print(json.dumps({'state': prepared['state'], 'case': prepared['case'], 'preparation': ref,
                          'source_files': len(prepared['files']), 'Main_actions': 0, 'Android_actions': 0,
                          'Gallery_install_attempts': 0, 'runtime_qualified': False,
                          'business_qualified': False, 'production_ready': False}, sort_keys=True))
        return 0
    need(args.request and args.expect_request_sha256, 'EXPLICIT_FRESH_CURRENT_MAIN_REQUEST')
    request_ref = supplied(args.request, args.expect_request_sha256)
    request = parse(read(request_ref, 131072)); root = validate_request(request, prepared['case'])
    return execute(ref, prepared, c, held, support, identity, custody, components,
                   source_guard, request_ref, request, root)


if __name__ == '__main__':
    raise SystemExit(main())
