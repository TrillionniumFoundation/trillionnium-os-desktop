#!/usr/bin/env python3
"""Derive one fixed BestBuy install/state request from the qualified IHG source.

This is a local-only source builder. It does not dispatch or access Android.
"""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import types

BASE = Path('/workspace/scratch/94990735b266')
OLD = BASE / 'android-ihg-qa-r1-install-state-01'
OUT = BASE / 'android-bestbuy-qa-r1-install-state-01'
ACTUAL = BASE / 'root-recovery-20261104-02/evidence/bestbuy-r1-build01'
QA = BASE / 'owned-bestbuy-qa-r1-build01/source'
READER = BASE / 'android-bestbuy-artifact-launcher-readonly-01/read_bestbuy.py'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def checked(path, size, sha):
    raw = path.read_bytes()
    assert pin(raw) == {'bytes': size, 'sha256': sha}, str(path)
    return raw


def write(name, raw):
    if not isinstance(raw, bytes):
        raw = raw.encode() if isinstance(raw, str) else encoded(raw)
    path = OUT / name
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return pin(raw)


def main():
    assert not OUT.exists(), 'CREATE_ONLY_SOURCE_REQUIRED'
    baseline_raw = checked(OLD / 'SOURCE_PINS.json', 1435,
        'eec0bb01cbc2440918800026c2d1260bdc62fbab1f377776b9fccf7467596902')
    baseline = json.loads(baseline_raw)
    for name, value in baseline['files'].items():
        checked(OLD / name, value['bytes'], value['sha256'])
    build_raw = checked(ACTUAL / 'build-result.json', 17438,
        'e0cdcc62bd7e59b696864ce0e244e2c5f441707692c334758dd0e343c6d095cd')
    stage_raw = checked(ACTUAL / 'stage-result.json', 1951,
        'c01137e4488d93d9d878fe6007c03b99e7bef328a25303591dd0510369984b83')
    review_raw = checked(ACTUAL / 'root-actual-review.json', 2004,
        '5bfd269b4f29f6375f9cc3abc5bfe19300845b47d7272d8cbccf927fbbb4cc28')
    reader_raw = checked(READER, 21069,
        'ce4ff1399953fe0d5e89bc0210ae9cdb323d1e08e436327df1521f6cb167ef77')
    build, stage = json.loads(build_raw), json.loads(stage_raw)
    assert build['state'] == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN'
    assert stage['state'] == 'OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN'
    qa_manifest_raw = checked(QA / 'SOURCE_PINS.json', 1461,
        '1dc5ae021d8b4d3165ac81dd09aef7035651118a9a81380139bdd1caaef668f8')
    target = json.loads((QA / 'target-artifact-reference.json').read_text())
    expected_target = {'package': 'com.bestbuy.android', 'uid': 10130,
                       'user': 0, 'version_code': 2012312321}
    assert all(target[key] == value for key, value in expected_target.items())
    assert len(target['current_artifacts']) == 3
    assert sum(row['held_file']['bytes'] for row in target['current_artifacts']) == 245511693
    install_nonce, state_nonce = secrets.token_hex(16), secrets.token_hex(16)
    assert install_nonce != state_nonce
    replacements = [
        ('com.ihg.apps.android', 'com.bestbuy.android'),
        ('org.droidloom.qa.ihg.r1', 'org.droidloom.qa.bestbuy.r1'),
        ('owned-ihg-qa', 'owned-bestbuy-qa'),
        ('ihg_context.py', 'bestbuy_context.py'),
        ('ihg_transport.py', 'bestbuy_transport.py'),
        ('read_ihg.py', 'read_bestbuy.py'),
        ('b637e01d62293f5e7c909e75d2b36d50', install_nonce),
        ('c815375703e1143b2a8ce8d7d3c44d6e', state_nonce),
        ('ab971f5b361f1d97b8036c954a6b88734b7faedbeed6349b873ead85fa79d5f3',
         build['source_manifest_sha256']),
        ('26a45b337c5dad2bd98b18ce093b321b8c0805de7cb9d759d5dd4088be05a053', pin(build_raw)['sha256']),
        ('94bfea341c50b648a2da13752044434cff04e74b7e7549c0d0e0b10c2ce77c41', pin(stage_raw)['sha256']),
        ('3f3164062d8b4f0ebd49d631953ef1a667ec315d2ab7ac0fab8b3b933a6b7324', build['APK']['sha256']),
        ('c1502f9d917628e7c64a03b197e1edb2a641a3171afba15b15311aeb23954553',
         build['signer_certificate_sha256']),
        ('51ecf1c0a12d8bfa9ed721265e14c4f06ef3eff72cbf5840de9569eb09797d40', pin(reader_raw)['sha256']),
        ('BUILD_BYTES = 17246', 'BUILD_BYTES = 17438'),
        ('STAGE_BYTES = 1935', 'STAGE_BYTES = 1951'),
        ('10137', '10130'), ('50023219', '2012312321'),
        ('IHG', 'BestBuy'), ('AMAZON', 'BESTBUY'), ('amazon', 'bestbuy'),
        ('its exact one current APK', 'its exact three current APKs'),
        ('The exact one installed commercial APK', 'The exact three installed commercial APKs'),
        ('ACTUAL_ONE_BestBuy_APK_PATH_CHANGED', 'ACTUAL_THREE_BESTBUY_APK_PATH_CHANGED'),
        ('ONE_APK_TOTAL_BOUND', 'THREE_APK_TOTAL_BOUND'),
        ('EXACT_ONE_HELD_APK_REQUIRED', 'EXACT_THREE_HELD_APKS_REQUIRED'),
        ('OPEN_ONE_APK_SET_REQUIRED', 'OPEN_THREE_APK_SET_REQUIRED'),
    ]
    semantic = {
        'install_state.py': [
            ('uid not in (10130,10129,10117,10125,10164,10165,10166,10169,10170,10175)',
             'uid not in (10130,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190,10137,10196)'),
            ('len(artifacts.records)==1', 'len(artifacts.records)==3'),
        ],
        'bestbuy_context.py': [
            ('len(values) == 1', 'len(values) == 3'),
            ('len(self.opened) == len(self.records) == 1', 'len(self.opened) == len(self.records) == 3'),
        ],
    }
    names = {
        'install_state.py': 'install_state.py',
        'ihg_context.py': 'bestbuy_context.py',
        'ihg_transport.py': 'bestbuy_transport.py',
        'stage_execute.py': 'stage_execute.py',
        'make_request.py': 'make_request.py',
    }
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    source_files, residual, full_diff = {}, '', ''
    for old_name, new_name in names.items():
        old = (OLD / old_name).read_text()
        literal = old
        for before, after in replacements:
            literal = literal.replace(before, after)
        candidate = literal
        for before, after in semantic.get(new_name, []):
            assert before in candidate, (new_name, before)
            candidate = candidate.replace(before, after)
        ast.parse(candidate)
        source_files[new_name] = write(new_name, candidate)
        residual += ''.join(difflib.unified_diff(literal.splitlines(True), candidate.splitlines(True),
            fromfile='literal-derived/' + new_name, tofile='BestBuy/' + new_name))
        full_diff += ''.join(difflib.unified_diff(old.splitlines(True), candidate.splitlines(True),
            fromfile='qualified-IHG/' + old_name, tofile='BestBuy/' + new_name))
    source_files['references/read_bestbuy.py'] = write('references/read_bestbuy.py', reader_raw)
    ref = 'references/readonly_r3_coordinator.py'
    source_files[ref] = write(ref, (OLD / ref).read_bytes())
    target_reference = {
        'schema': 1, 'state': 'ACTUAL_READONLY_IDENTITY_REFERENCE_REQUIRES_FRESH_RUNTIME_REVALIDATION',
        'job': target['actual_read_job'], 'worker_result': target['actual_read_result'],
        'target': expected_target, 'artifacts': target['current_artifacts'],
        'current_launcher_reference_only': target['current_launcher'],
        'data_source': target['data_source'], 'source_reader_sha256': pin(reader_raw)['sha256'],
        'remote_held_result_file_readback_performed': False,
        'future_target_APK_hashes_and_UID_require_revalidation': True,
        'runtime_UI_or_launch_actions': 0, 'signer_certificate_independently_verified': False,
        'whole_app_production_ready': False,
    }
    source_files['target-artifact-reference.json'] = write('target-artifact-reference.json', target_reference)
    inputs = json.loads((OLD / 'INPUTS.json').read_text())
    inputs.update({
        'APK': build['APK'], 'actual_build_job': '1a1ae188f2b-fc05-5d5f',
        'actual_build_review': {'path': str(ACTUAL / 'root-actual-review.json'), **pin(review_raw)},
        'build_receipt': {'path': '/home/alex/work/pocket4-owned-bestbuy-qa-r1-build-01/build-result.json', **pin(build_raw)},
        'stage_receipt': {'path': '/home/alex/work/pocket4-owned-bestbuy-qa-r1-source-01/stage-result.json', **pin(stage_raw)},
        'nonces': {'install_nonce': install_nonce, 'state_nonce': state_nonce},
        'owned_package': build['package'], 'source_manifest_sha256': build['source_manifest_sha256'],
        'signer_certificate_sha256': build['signer_certificate_sha256'],
        'target': expected_target, 'target_APK_bytes': 245511693, 'target_APKs': 3,
        'purpose': 'Install one exact new BestBuy self-instrumentation helper and observe no-UiAutomation state once',
    })
    source_files['INPUTS.json'] = write('INPUTS.json', inputs)
    source_files['README.md'] = write('README.md',
        '# BestBuy R1 install and state\n\n'
        'This fixed request installs the actual signed owned helper once, only if absent across all users and retained records. '
        'It runs one state observation with no UiAutomation connection, commercial App launch, UI action, settings write, permission grant or audio action.\n\n'
        'The original held Main identity, source, command, APK and cleanup gates remain. All three commercial APK files are revalidated before and after. '
        'The thirteen-command plan and bounded resources are unchanged. The new helper UID must be read from the actual install; it is not guessed. '
        'The owned helper remains installed for a separately reviewed fresh UI flow. Failed or unknown installs are never automatically repeated or uninstalled.\n\n'
        'This request has not been dispatched. Whole-App production readiness is false.\n')
    manifest_pin = write('SOURCE_PINS.json', {'schema': 1, 'files': source_files})
    write('literal-substitutions.json', {'schema': 1, 'replacements': replacements, 'semantic_changes': semantic})
    write('IHG-to-BestBuy-install.patch', full_diff)
    write('normalized-semantic-residual.patch', residual)
    request_path = OUT / 'exact-request.json'
    done = subprocess.run([sys.executable, '-I', str(OUT / 'make_request.py'), '--write-once',
        '--source-manifest-sha256', manifest_pin['sha256'], '--output', str(request_path)],
        check=True, capture_output=True, timeout=10)
    assert not done.stderr
    write('request-pins.json', done.stdout)
    request = json.loads(request_path.read_text())
    packet = request['stdin'].encode()
    stage_module = types.ModuleType('local_packet_validation')
    stage_module.__file__ = str(OUT / 'stage_execute.py')
    exec(compile((OUT / 'stage_execute.py').read_bytes(), stage_module.__file__, 'exec'), stage_module.__dict__)
    stage_module.checked_packet(packet)
    # Pure source/plan binding. No context, process, device or mock success is constructed.
    context = types.ModuleType('local_context')
    context.__file__ = str(OUT / 'bestbuy_context.py')
    exec(compile((OUT / 'bestbuy_context.py').read_bytes(), context.__file__, 'exec'), context.__dict__)
    qa = types.ModuleType('local_qa')
    qa.__file__ = str(QA / 'qa_contract.py')
    exec(compile((QA / 'qa_contract.py').read_bytes(), qa.__file__, 'exec'), qa.__dict__)
    guest = '/data/local/tmp/pocket4-owned-bestbuy-qa-' + install_nonce + '/owned-bestbuy-qa.apk'
    plan = context.ordered_commands(qa, build['package'], guest, state_nonce)
    assert len(plan) == 13 and sum(mutation for _, _, mutation in plan) == 1
    assert plan[3][0] == ['/system/bin/cmd', 'package', 'install', '-R', '-t', '--user', '0', '--pkg', build['package'], guest]
    assert all('/system/bin/am' not in argv or 'instrument' in argv for argv, _, _ in plan)
    validation = {'schema': 1, 'state': 'LOCAL_SOURCE_AND_PACKET_VALIDATED_ANDROID_UNRUN',
        'baseline_manifest': pin(baseline_raw), 'actual_build': pin(build_raw),
        'actual_stage': pin(stage_raw), 'actual_build_review': pin(review_raw),
        'source_manifest': manifest_pin, 'request': pin(request_path.read_bytes()),
        'stdin': pin(packet), 'command_count': len(plan), 'install_commands': 1,
        'helper_UID': None, 'target_APKs': 3, 'target_APK_bytes': 245511693,
        'original_bound_reader_copied_exact': pin(reader_raw), 'local_only': True,
        'Android_or_Hepta_actions': 0, 'automatic_retry': False, 'whole_app_production_ready': False}
    write('source-review.json', validation)
    files = {str(p.relative_to(OUT)): pin(p.read_bytes()) for p in sorted(OUT.rglob('*')) if p.is_file()}
    write('FROZEN_FILES.json', {'schema': 1, 'files': files, 'payload_count': len(files),
        'state': 'EXACT_INSTALL_STATE_REQUEST_NOT_SUBMITTED', 'remote_actions': 0})
    print(json.dumps(validation, sort_keys=True))


if __name__ == '__main__':
    main()
