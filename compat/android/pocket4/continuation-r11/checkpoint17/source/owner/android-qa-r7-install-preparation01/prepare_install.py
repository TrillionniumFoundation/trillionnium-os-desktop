#!/usr/bin/env python3
"""Prepare one R7 install source only after complete actual build receipts.

Default is PLAN_ONLY. This local generator has no dispatch or Android entry.
It does not assign a helper UID. Existing source and actual records are read
only; the candidate directory must be absent before any write.
"""
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import types

WORKSPACE = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
BASE = WORKSPACE / 'android-qa-r6-install-state-01'
BASE_SHA = '8c02c3bf010998e23ed30ae13b88c5e4f5d824775702e055e772788966b93e59'
QA = WORKSPACE / 'owned-bili-qa-r7-player-button-01/source'
QA_SHA = 'f6722f5163403c753a81912944e3390e424858795e2db059ea9a75cf8f56c310'
DESTINATION = WORKSPACE / 'android-qa-r7-install-state-01'
REMOTE_ROOT = '/home/alex/work/pocket4-owned-bili-qa-r7-install-state-01'
REMOTE_QA = '/home/alex/work/pocket4-owned-bili-qa-r7-source-01/source'
REMOTE_BUILD = '/home/alex/work/pocket4-owned-bili-qa-r7-build-01/build-result.json'
REMOTE_STAGE = '/home/alex/work/pocket4-owned-bili-qa-r7-source-01/stage-result.json'
REMOTE_APK = '/home/alex/work/pocket4-owned-bili-qa-r7-build-01/owned-bili-qa.apk'
CODE_FILES = ('install_state.py', 'stage_execute.py', 'make_request.py', 'session_binding.py')
COPY_FILES = ('references/readonly_r3_coordinator.py', 'references/R3-SOURCE-MANIFEST.json',
              'r4/source-manifest.json', 'r4/bound_android_transport.py')
OLD_UID_EXCLUSIONS = '(10117,10125,10164,10165,10166,10169,10170,10175)'
NEW_UID_EXCLUSIONS = '(10117,10125,10164,10165,10166,10169,10170,10175,10184)'


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()


def pin(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def checked_manifest(directory, expected):
    raw = (directory / 'SOURCE_PINS.json').read_bytes()
    need(sha(raw) == expected, 'EXACT_PRIOR_SOURCE_MANIFEST_REQUIRED')
    manifest = json.loads(raw)
    for name, row in manifest['files'].items():
        rel = Path(name)
        need(not rel.is_absolute() and '..' not in rel.parts and rel.as_posix() == name,
             'SOURCE_RELATIVE_NAME_REQUIRED')
        data = (directory / name).read_bytes()
        need(row == {'bytes': len(data), 'sha256': sha(data)}, 'EXACT_PRIOR_SOURCE_FILE_REQUIRED:' + name)
    return manifest


def module(path, expected, name):
    raw = path.read_bytes()
    need(sha(raw) == expected, 'EXACT_MODULE_PIN_REQUIRED')
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def actual_build(args, qa_manifest):
    """Use the frozen R7 parser; no locally synthesized build evidence."""
    need(args.build is not None and args.stage is not None and
         type(args.build_bytes) is int and type(args.stage_bytes) is int and
         0 < args.build_bytes <= 1048576 and 0 < args.stage_bytes <= 1048576 and
         isinstance(args.build_sha256, str) and re.fullmatch('[0-9a-f]{64}', args.build_sha256) and
         isinstance(args.stage_sha256, str) and re.fullmatch('[0-9a-f]{64}', args.stage_sha256),
         'EXTERNAL_ACTUAL_BUILD_AND_STAGE_PINS_REQUIRED')
    need(isinstance(args.actual_job_id, str) and re.fullmatch('1a[0-9a-f]+-[0-9a-f]+-[0-9a-f]+', args.actual_job_id),
         'ROOT_REPORTED_ACTUAL_JOB_ID_REQUIRED')
    adapter = module(QA / 'qa_adapter.py', qa_manifest['files']['qa_adapter.py']['sha256'], 'r7_actual_adapter')
    builder = module(QA / 'build_candidate.py', qa_manifest['files']['build_candidate.py']['sha256'], 'r7_actual_builder')
    need(adapter.own_source(QA_SHA) == qa_manifest, 'COMPLETE_FROZEN_R7_SOURCE_REQUIRED')
    build_raw = adapter.pinned(args.build, args.build_sha256)
    stage_raw = adapter.pinned(args.stage, args.stage_sha256)
    need(len(build_raw) == args.build_bytes and len(stage_raw) == args.stage_bytes,
         'EXTERNAL_ACTUAL_RECEIPT_BYTES_REQUIRED')
    build = json.loads(build_raw)
    stage = json.loads(stage_raw)
    apk = build.get('APK')
    need(isinstance(apk, dict) and set(apk) == {'path', 'bytes', 'sha256'} and apk['path'] == REMOTE_APK,
         'EXACT_R7_BUILD_APK_PATH_REQUIRED')
    bound = types.SimpleNamespace(build_receipt=args.build, build_receipt_sha256=args.build_sha256,
        source_manifest_sha256=QA_SHA, apk_sha256=apk['sha256'],
        signer_certificate_sha256=build.get('signer_certificate_sha256'))
    proof = adapter.qualified_build(bound, qa_manifest, builder)
    need(stage.get('state') == 'OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN' and
         stage.get('source_manifest_sha256') == QA_SHA and stage.get('build_returncode') == 0 and
         stage.get('error') is None and stage.get('secondary_errors') == [] and
         stage.get('build_result') == {'path': REMOTE_BUILD, 'bytes': len(build_raw), 'sha256': sha(build_raw)},
         'EXACT_R7_ACTUAL_BUILD_STAGE_CHAIN_REQUIRED')
    return proof, build_raw, stage_raw


def assignment(text, name, value):
    replacement = name + ' = ' + repr(value)
    result, count = re.subn(r'^' + re.escape(name) + r' = .+$', lambda _: replacement, text, flags=re.MULTILINE)
    need(count == 1, 'ONE_TOP_LEVEL_BINDING_REQUIRED:' + name)
    return result


def replace_once(text, old, new, label):
    need(text.count(old) == 1, 'ONE_EXACT_LITERAL_REQUIRED:' + label)
    return text.replace(old, new)


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(args):
    base_manifest = checked_manifest(BASE, BASE_SHA)
    need(set(base_manifest['files']) == set(CODE_FILES + COPY_FILES + ('INPUTS.json', 'README.md')),
         'EXACT_R6_INSTALL_SOURCE_SET_REQUIRED')
    qa_manifest = checked_manifest(QA, QA_SHA)
    proof, build_raw, stage_raw = actual_build(args, qa_manifest)
    need(not os.path.lexists(DESTINATION), 'NEW_INSTALL_SOURCE_DIRECTORY_REQUIRED')
    flow_nonce, state_nonce = secrets.token_hex(16), secrets.token_hex(16)
    need(flow_nonce != state_nonce, 'DISTINCT_FRESH_INSTALL_NONCES_REQUIRED')
    literals = {
        'r6': 'r7', 'R6': 'R7',
        '2a1065bc6af8a39e6518bd61d8581978': flow_nonce,
        '38224815112bbffd278ea0f29ab48c82': state_nonce,
        '6c75b4a976990d4815de58f504912d3f9a7181c0d5a9094c6319180a1279c419': QA_SHA,
    }
    files = {}
    normalized = {}
    for name in CODE_FILES:
        text = (BASE / name).read_text()
        for old, new in literals.items():
            text = text.replace(old, new)
        normalized[name] = text
        if name == 'install_state.py':
            for key, value in {'BUILD_SHA': sha(build_raw), 'BUILD_BYTES': len(build_raw),
                               'STAGE_SHA': sha(stage_raw), 'STAGE_BYTES': len(stage_raw),
                               'APK_SHA': proof['APK']['sha256'], 'APK_BYTES': proof['APK']['bytes'],
                               'SIGNER_SHA': proof['signer_certificate_sha256']}.items():
                text = assignment(text, key, value)
            text = replace_once(text, OLD_UID_EXCLUSIONS, NEW_UID_EXCLUSIONS, 'reject_old_R6_UID')
        if name == 'make_request.py':
            text = replace_once(text, 'pocket4-owned-bili-qa-r7-install-state-01-20261105',
                                'pocket4-owned-bili-qa-r7-install-state-01-20261106', 'stable_request_key')
        ast.parse(text)
        files[name] = text.encode()
    for name in COPY_FILES:
        files[name] = (BASE / name).read_bytes()
    prior_inputs = json.loads((BASE / 'INPUTS.json').read_bytes())
    recorder = dict(prior_inputs['recorder'])
    recorder['root'] = REMOTE_ROOT + '/source/recorder-r4'
    inputs = {
        'schema': 1, 'state': 'ACTUAL_R7_BUILD_RECEIPTS_BOUND_INSTALL_ANDROID_UNRUN',
        'source_review_only': True, 'actual_install_state_not_run': True,
        'actual_build_job_reported_by_root': args.actual_job_id,
        'actual_original_R7_qualified_build_passed': True,
        'job_terminal_authority_stays_with_root': True,
        'base_install_source_manifest_sha256': BASE_SHA,
        'qa_source_manifest_sha256': QA_SHA,
        'package': 'org.droidloom.qa.bili.r7', 'helper_uid': None,
        'nonces': {'flow': flow_nonce, 'state': state_nonce},
        'build': pin(REMOTE_BUILD, build_raw), 'stage': pin(REMOTE_STAGE, stage_raw),
        'apk': {**proof['APK'], 'signer_certificate_sha256': proof['signer_certificate_sha256']},
        'main_epoch_sha256': prior_inputs['main_epoch_sha256'],
        'recorder': recorder, 'action_lock_admission': prior_inputs['action_lock_admission'],
        'official_cli_reference': prior_inputs['official_cli_reference'],
        'scope': 'First new R7 helper install and one no-UiAutomation state; no player action or launch',
        'older_helper_or_target_UIDs_rejected': list(ast.literal_eval(NEW_UID_EXCLUSIONS)),
        'old_package_mutation_authorized': False, 'qualification_inherited_from_old_helpers': False,
        'state_request_uses_player_button_operation': False,
        'state_wire': 'gzip-canonical-json-v1, exact R7 parser, successful finish -1, no UiAutomation',
        'whole_app_production_ready': False,
    }
    files['INPUTS.json'] = encoded(inputs)
    files['README.md'] = (
        '# R7 helper installation and no-automation state\n\n'
        'This candidate binds complete actual R7 build and stage receipts. The original R6 install '
        'implementation is retained with the new package, paths, nonces, actual build/APK/signer pins, '
        'and rejection of the old R6 UID 10184. The R4 recorder and transport copies are exact.\n\n'
        'One package-absence check includes uninstalled records and all users. Installation retains '
        'the original -R no-replacement flag and fresh owned staging directory. The helper UID comes '
        'only from the actual package-list result, followed by two exact installed-byte observations '
        'around one state invocation. No UiAutomation, app launch, playback input, permission or setting '
        'write is admitted. Main guards, held leases, one global action lock and precise owned staging '
        'cleanup remain intact. Failed or unknown installation is reconciled from fixed receipts, '
        'never retried automatically.\n\n'
        'A separate future UI source requires the complete actual install receipts, installed identity '
        'and a fresh owned task. This source does not provide them.\n'
    ).encode()
    need(set(files) == set(base_manifest['files']), 'UNCHANGED_INSTALL_SOURCE_CLOSURE_REQUIRED')
    need(all(0 < len(raw) <= 65536 for raw in files.values()), 'ORIGINAL_SOURCE_BOUNDS_REQUIRED')
    manifest = {'schema': 1, 'files': {name: {'bytes': len(raw), 'sha256': sha(raw)}
                                   for name, raw in sorted(files.items())}}
    manifest_raw = encoded(manifest)
    files['SOURCE_PINS.json'] = manifest_raw
    review = {
        'schema': 1, 'actual_build_local_pin': pin(args.build, build_raw),
        'actual_stage_local_pin': pin(args.stage, stage_raw), 'actual_build_job_reported_by_root': args.actual_job_id,
        'original_R7_qualified_build_passed': True, 'old_R6_source_unchanged': True,
        'R7_build_source_unchanged': True, 'copied_reference_files_byte_identical': list(COPY_FILES),
        'binding_literals': literals, 'new_UID_exclusion': 10184,
        'APK_and_signer_from_actual_build_only': True, 'actual_helper_UID': None,
        'future_install_or_UI_success_asserted': False, 'source_manifest_sha256': sha(manifest_raw),
        'source_files': len(manifest['files']), 'packet_byte_cap': 262144,
        'request_cpu_percent': 100, 'request_memory_bytes': 536870912,
        'request_timeout_seconds': 300, 'worker_timeout_seconds': 190,
        'dispatch_performed': False, 'remote_device_calls': 0,
    }
    patch = ''.join(''.join(difflib.unified_diff((BASE / name).read_text().splitlines(True),
        files[name].decode().splitlines(True), fromfile='R6/' + name, tofile='R7/' + name))
        for name in CODE_FILES + ('INPUTS.json', 'README.md'))
    residual = ''.join(''.join(difflib.unified_diff(normalized[name].splitlines(True),
        files[name].decode().splitlines(True), fromfile='literal-normalized-R6/' + name,
        tofile='actual-R7/' + name)) for name in CODE_FILES)
    DESTINATION.mkdir(mode=0o700)
    for name, raw in files.items():
        write_new(DESTINATION / name, raw)
    write_new(DESTINATION / 'r6-to-r7-install.patch', patch.encode())
    write_new(DESTINATION / 'normalized-semantic-residual.patch', residual.encode())
    maker = subprocess.run([sys.executable, '-I', str(DESTINATION / 'make_request.py'), '--write-once',
        '--source-manifest-sha256', sha(manifest_raw), '--output', str(DESTINATION / 'exact-request.json')],
        check=False, capture_output=True, timeout=30, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    write_new(DESTINATION / 'request-generation.stdout.log', maker.stdout)
    write_new(DESTINATION / 'request-generation.stderr.log', maker.stderr)
    need(maker.returncode == 0 and maker.stderr == b'', 'LOCAL_REQUEST_GENERATOR_REQUIRED')
    request_raw = (DESTINATION / 'exact-request.json').read_bytes()
    request = json.loads(request_raw)
    packet_raw = request['stdin'].encode()
    stage_module = module(DESTINATION / 'stage_execute.py', manifest['files']['stage_execute.py']['sha256'],
                          'r7_install_stage_packet_review')
    packet, extracted = stage_module.checked_packet(packet_raw)
    need(extracted == files and packet['nonce'] == flow_nonce and
         packet['source_manifest_sha256'] == sha(manifest_raw), 'EXACT_INSTALL_PACKET_REQUIRED')
    original = json.loads((BASE / 'exact-request.json').read_bytes())
    envelope_keys = ('host', 'executable', 'cwd', 'env', 'timeout_seconds', 'cpu_quota_percent',
                     'memory_max_bytes', 'nice')
    need(all(request[k] == original[k] for k in envelope_keys), 'UNCHANGED_INSTALL_RESOURCE_ENVELOPE_REQUIRED')
    need(request['args'][:4] == ['-n', '/usr/bin/python3', '-I', '-c'] and len(request['args']) == 5,
         'ORIGINAL_WRAPPER_SHAPE_REQUIRED')
    review['exact_request'] = pin(DESTINATION / 'exact-request.json', request_raw)
    review['stdin'] = {'bytes': len(packet_raw), 'sha256': sha(packet_raw)}
    review['original_stage_checked_packet_passed'] = True
    review['unchanged_resource_envelope'] = True
    write_new(DESTINATION / 'source-review.json', encoded(review))
    checked_manifest(BASE, BASE_SHA)
    checked_manifest(QA, QA_SHA)
    leaves = {}
    for path in sorted(DESTINATION.rglob('*')):
        if path.is_file():
            raw = path.read_bytes()
            leaves[path.relative_to(DESTINATION).as_posix()] = {'bytes': len(raw), 'sha256': sha(raw)}
    write_new(DESTINATION / 'FROZEN_FILES.json', encoded({'schema': 1, 'files': leaves}))
    return {'state': 'FROZEN_R7_INSTALL_SOURCE_NOT_DISPATCHED', 'directory': str(DESTINATION),
            'actual_helper_UID': None, 'request': review['exact_request'], 'stdin': review['stdin'],
            'source_manifest': pin(DESTINATION / 'SOURCE_PINS.json', manifest_raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-once', action='store_true')
    parser.add_argument('--build', type=Path)
    parser.add_argument('--build-bytes', type=int)
    parser.add_argument('--build-sha256')
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--stage-bytes', type=int)
    parser.add_argument('--stage-sha256')
    parser.add_argument('--actual-job-id')
    args = parser.parse_args()
    if not args.write_once:
        value = {'state': 'PLAN_ONLY', 'destination': str(DESTINATION),
                 'requires_complete_actual_R7_build_and_stage': True,
                 'APK_signer_and_helper_UID_not_generated': True, 'dispatch_calls': 0, 'device_calls': 0}
    else:
        value = prepare(args)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
