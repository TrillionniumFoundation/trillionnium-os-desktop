#!/usr/bin/env python3
"""Seal review-only source publication and build requests; no execution."""
import ast
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
FINAL = HERE / 'candidate-r2/helper'
DEST = HERE / 'candidate-r2/hostprep-r1'
NONCE = '362bdb6f45eeb344b3584aa998cb03e1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def pinned(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def save(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode('ascii')
    with path.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    assert path.read_bytes() == raw
    return pinned(path)


def main():
    manifest_raw = (FINAL / 'SOURCE_PINS.json').read_bytes()
    assert len(manifest_raw) == 3259 and sha(manifest_raw) == '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489'
    manifest = json.loads(manifest_raw)
    files = {}
    for name, pin in manifest['files'].items():
        raw = (FINAL / name).read_bytes()
        assert pin == {'bytes': len(raw), 'sha256': sha(raw)}
        files[name] = raw.decode('utf-8')
    stager = (PROJECT / 'successor_qa/stage_helper_source.py').read_bytes()
    assert (len(stager), sha(stager)) == (5608, '745e0f15f8619c2b00a7d54c890837de826eb04e192bcbf273eb3687b6baeac6')
    payload = canonical({'schema': 'pocket4-fixed-search-helper-source-payload-v1',
                         'manifest_text': manifest_raw.decode('utf-8'), 'files': files,
                         'stage_source': stager.decode('utf-8')}) + b'\n'
    assert len(payload) < 524288
    template = (HERE / 'fragments/publish_source_once.py.in').read_text()
    assert template.count('@PAYLOAD_BYTES@') == template.count('@PAYLOAD_SHA@') == 1
    source = template.replace('@PAYLOAD_BYTES@', str(len(payload))).replace('@PAYLOAD_SHA@', sha(payload)).encode('utf-8')
    # Import as a pure module only. The sole validation function does not touch
    # files or launch anything, and main is never called in this local sealer.
    scope = types.ModuleType('local_fixed_source_payload_validation')
    exec(compile(source, 'publish_source_once.py', 'exec'), scope.__dict__)
    decoded_manifest, decoded_files, decoded_stage = scope.validated_payload(payload)
    assert decoded_manifest == manifest_raw and decoded_stage == stager
    assert decoded_files == {name: text.encode('utf-8') for name, text in files.items()}
    old_stage = json.loads((PROJECT / 'successor_qa/actual/helper-source-stage-r1/process-request.json').read_bytes())
    old_build = json.loads((PROJECT / 'successor_qa/actual/helper-build-r1/process-request.json').read_bytes())
    stage = dict(old_stage)
    stage.update(args=['-n', '/usr/bin/python3', '-I', '-B', '-c', source.decode('utf-8')],
                 stdin=payload.decode('ascii'), idempotency_key='pocket4-beike-fixed-search-helper-source-stage-r2-20261106-' + NONCE)
    build = dict(old_build)
    build.update(args=['-I', '/home/alex/work/pocket4-successor-qa-build-source-' + NONCE + '/build_candidate.py',
                       '--build-once', '--source-manifest-sha256', sha(manifest_raw)],
                 idempotency_key='pocket4-beike-fixed-search-helper-build-r2-20261106-' + NONCE)
    assert {key: value for key, value in stage.items() if key not in ('args', 'stdin', 'idempotency_key')} == {
        key: value for key, value in old_stage.items() if key not in ('args', 'stdin', 'idempotency_key')}
    assert {key: value for key, value in build.items() if key not in ('args', 'idempotency_key')} == {
        key: value for key, value in old_build.items() if key not in ('args', 'idempotency_key')}
    assert stage['memory_max_bytes'] == 268435456 and stage['timeout_seconds'] == 60 and stage['cpu_quota_percent'] == 50
    assert build['memory_max_bytes'] == 1073741824 and build['timeout_seconds'] == 300 and build['cpu_quota_percent'] == 100
    assert build['executable'] == '/usr/bin/python3' and stage['executable'] == '/usr/bin/sudo'
    DEST.mkdir()
    outputs = [save(DEST / 'source-payload.json', payload), save(DEST / 'publish_source_once.py', source),
               save(DEST / 'stage_helper_source.py', stager), save(DEST / 'exact-stage-request.json', stage),
               save(DEST / 'exact-build-request.json', build)]
    current_scope_path = PROJECT / 'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json'
    current_scope = pinned(current_scope_path)
    assert current_scope['bytes'] == 59259 and current_scope['sha256'] == '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'
    plan = {'schema': 'pocket4-fixed-search-helper-hostprep-review-v1', 'status': 'UNSUBMITTED_REVIEW_ONLY',
        'helper_manifest': pinned(FINAL / 'SOURCE_PINS.json'), 'published_source_members': 15,
        'new_package': manifest['helper_package'], 'new_signer': 'UNKNOWN_REQUIRES_ACTUAL_OWNED_KEY_GENERATION',
        'new_UID': 'UNKNOWN_NOT_INSTALLED', 'new_package_absence_proven': False,
        'source_stage': {'CPU_percent': 50, 'memory_bytes': 268435456, 'seconds': 60,
                        'new_root': str(scope.ROOT), 'new_output': str(scope.OUTPUT), 'original_stager_sha256': sha(stager),
                        'stdin_bytes': len(payload), 'stdin_max_bytes': 524288, 'reviewed_request_pin': outputs[3]},
        'build': {'UID': 1000, 'CPU_percent': 100, 'memory_bytes': 1073741824, 'seconds': 300,
                  'original_inner_deadline_seconds': 230, 'original_pinned_JDK_SDK_tools_retained': True,
                  'original_per_tool_output_max_bytes': 1048576, 'actual_source_stage_durable_success_required_first': True,
                  'normal_compile_package_sign_verify_required': True, 'reviewed_request_pin': outputs[4]},
        'runtime_contract': {'new_operation': 'search_click', 'allowed': ['state', 'inspect', 'search_click'],
                             'old_helper_retained': True, 'old_case_FAILED_UNKNOWN_retained': True,
                             'whole_tree_comparisons': 2, 'fresh_full_captures_one_connection': 3,
                             'target_refreshes': 2, 'selector': {'resource_id': 'com.lianjia.beike:id/tv_nav_right_search_text',
                                                               'class': 'android.widget.TextView', 'text': '\u641c\u7d22'},
                             'original_act_changed': False, 'Bili_and_general_action_opened': False},
        'current_whole48_scope_reference': current_scope,
        'scope_transition': 'Host staging/build do not touch Main. No installation/UI packet is sealed. A future install must bind fresh current full48, prove the new package absent, preserve original48, retain old r1 helper and publish actual49 after install; rerun current resolver if it changed. This does not replace the inner Beike scope.',
        'no_action_reconciliation': 'Separate app_history A/B against old r1 UID10157. No direct consumer or old record changes by this candidate.',
        'host_remote_executions': 0, 'Android_commands': 0, 'install_request_sealed': False,
        'UI_request_sealed': False, 'production_ready': False, 'cleanup_eligible': False,
        'local_control_limits': 'Local Java --release8 attempt failed; Java21-only pure transaction control passed. The real pinned host JDK --release8 and Android compile are still required.'}
    outputs.append(save(DEST / 'EXECUTION_PLAN.json', plan))
    validation = {'schema': 'pocket4-fixed-search-hostprep-packet-closure-v1', 'all_fifteen_members_and_manifest_exact': True,
                  'original_stager_fullbytes_exact': True, 'payload_canonical_and_bounded': True,
                  'original_stage_and_build_resource_parameters_equal': True,
                  'decoded_code_compiles_only': True, 'stage_main_executed_locally': False,
                  'build_executed_locally': False, 'remote_submitted': False, 'outputs': outputs}
    validation_pin = save(DEST / 'PACKET_CLOSURE.derived.json', validation)
    print(json.dumps({'outputs': outputs, 'closure': validation_pin, 'unsubmitted': True}, sort_keys=True))


if __name__ == '__main__':
    main()
