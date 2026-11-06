#!/usr/bin/env python3
"""Pure local S42 reinterpretation, then a new explicit S43 verifier packet."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent
PARENT = 'official_source_scripts/s42_zbj_operator_verification/'
INPUTS = {}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(rel, size=None, digest=None):
    raw = (BASE / rel).read_bytes()
    need(size is None or len(raw) == size, 'input size differs: ' + rel)
    need(digest is None or sha(raw) == digest, 'input digest differs: ' + rel)
    INPUTS[rel] = {'path': rel, 'bytes': len(raw), 'sha256': sha(raw)}
    return raw


def load(rel, size=None, digest=None):
    return json.loads(read(rel, size, digest))


def definition(raw, name):
    node = next(x for x in ast.parse(raw).body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(raw.decode(), node)


def constant(raw, name):
    node = next(x for x in ast.parse(raw).body if isinstance(x, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == name for t in x.targets))
    return ast.literal_eval(node.value)


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    parent = read(PARENT + 'verify_complete_zbj_as_owner.py', 47626,
                  '135187efc52b0206df1013df6e5c0b58ee634ab96f2563f23a1a19b3514a6ad6')
    prior_request = load(PARENT + 'process-request.json', 48697,
                         '0088435cdae1d4b1e779cb66b00505d2373fd3c159d68f280f6708fba7874073')
    raw = read(PARENT + 'actual/stdout.original.json', 51004,
               '996845dad5c91bd67f16706561d42417ed370ab000f26ac9b16a7d1832576e0c')
    result = json.loads(raw)
    terminal = load(PARENT + 'actual/terminal.original.json')
    start = load(PARENT + 'actual/start.original.txt')
    need(terminal['job_id'] == start['job']['id'] == '1a1b2bf6182-fc05-7f90' and
         terminal['state'] == 'failed' and terminal['exit_code'] == 1 and
         start['job']['args'] == prior_request['args'] and
         start['job']['args'][3].encode() == parent, 'original S42 failed job/source differs')
    need(all(terminal[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed')) and
         all(terminal[k] is False for k in ('timed_out', 'cancelled', 'automatic_retry')), 'S42 terminal incomplete')
    for stream, size in (('stdout', len(raw)), ('stderr', 0)):
        need(terminal['log_bytes'][stream] == {'seen': size, 'stored': size} and
             terminal['log_errors'][stream] is None and terminal['log_truncated'][stream] is False and
             terminal['log_synced'][stream] is True, 'S42 original logs incomplete')
    need(result['ok'] is False and result['status'] == 'COMPLETE_CANDIDATE_VERIFICATION_FAILED' and
         result['errors'] == [{'type': 'AaptObservationIncomplete',
             'reason': 'nonzero return, diagnostic bytes, unrecognized output or parse failure; raw evidence preserved'}] and
         result['candidate_signature_verified'] is True and
         result['vendor_signer_matches_archived_installed_APK'] is True and
         result['candidate_permission_dump_verified'] is True and
         result['held_files'] == {'acquired': 13, 'closed': 13, 'errors': []} and
         result['original_descriptor_identities_restored'] is True and
         result['all_held_files_full_identity_and_hash_unchanged'] is True,
         'S42 failure is not the exact bounded parser-shape failure')
    need(result['candidate']['identity'] == constant(parent, 'APK_IDENTITY') and
         result['candidate']['sha256'] == constant(parent, 'APK_PIN')['sha256'], 'candidate identity differs')
    pure = {'need': need, 're': re, 'PACKAGE': 'com.zhubajie.client'}
    for name in ('aapt_diagnostics', 'normal_child_retired', 'badging_manifest',
                 'quoted_attributes', 'permissions_dump', 'parse_signature'):
        exec(compile(definition(parent, name), '<original-pure-function>', 'exec'), pure, pure)
    commands = {c['name']: c for c in result['commands']}
    need(set(commands) == {'apksigner', 'badging', 'permissions'}, 'exact three actual commands required')
    streams = {}
    for name, cmd in commands.items():
        need(pure['normal_child_retired'](cmd) and cmd['returncode'] == 0, 'actual child did not retire normally')
        for stream in ('stdout', 'stderr'):
            content = read(PARENT + 'actual/' + name + '.' + stream + '.original.txt',
                           cmd[stream]['bytes'], cmd[stream]['sha256'])
            need(stream != 'stderr' or content == b'', 'actual stderr must remain empty')
            streams[(name, stream)] = content
    extension = read('official_source_scripts/s43_zbj_operator_verification/diagnostics_extension.py')
    exec(compile(definition(extension, 'feature_group_diagnostics'), '<new-pure-extension>', 'exec'), pure, pure)
    badging = streams[('badging', 'stdout')]
    new_health = pure['feature_group_diagnostics'](pure['aapt_diagnostics'], 'badging', badging, b'')
    need(new_health['healthy_output_shape'] is True and not new_health['unrecognized_badging_lines'] and
         not new_health['stdout_diagnostic_lines'], 'actual S42 output remains unrecognized')
    old_health = result['command_parser_health'][0]['diagnostics']
    old_unrecognized = {(x['line_number'], x['raw_line']) for x in old_health['unrecognized_badging_lines']}
    new_recognized = {(x['line_number'], x['raw_line']) for x in new_health['recognized_feature_group_extension_rows']}
    need(old_unrecognized == new_recognized and len(old_unrecognized) == 16,
         'extension accepted rows outside the precise S42 rejection')
    manifest = pure['badging_manifest'](badging)
    manifest['native_abi_source'] = result['candidate_manifest_observation']['native_abi_source']
    need(manifest == result['candidate_manifest_observation'], 'manifest fields changed during reinterpretation')
    permissions = pure['permissions_dump'](streams[('permissions', 'stdout')])
    need(permissions == result['candidate_declared_permissions_observation'], 'permission rows changed')
    signature = pure['parse_signature'](streams[('apksigner', 'stdout')], commands['apksigner'])
    need(signature == result['candidate_signature_observation'], 'normal signature evidence changed')
    old_s39 = read('official_source_scripts/s39_szzc_operator_manifest/actual/badging.stdout.original.txt')
    need(pure['feature_group_diagnostics'](pure['aapt_diagnostics'], 'badging', old_s39, b'')['healthy_output_shape'] is True,
         'previously observed S39 form regressed')
    cases = {
        'invalid_install_enum': (badging.replace(b"install-location:'auto'", b"install-location:'arbitrary'"), b''),
        'duplicate_install_row': (badging.replace(b"install-location:'auto'", b"install-location:'auto'\ninstall-location:'auto'"), b''),
        'out_of_group_GL_row': (badging + b"  uses-gl-es: '0x20000'\n", b''),
        'duplicate_group_GL_row': (badging.replace(b"  uses-gl-es: '0x20000'", b"  uses-gl-es: '0x20000'\n  uses-gl-es: '0x20000'"), b''),
        'invalid_width_value': (badging.replace(b"requires-smallest-width:'240'", b"requires-smallest-width:'-1'"), b''),
        'unknown_inside_group': (badging.replace(b"  uses-gl-es: '0x20000'", b"  uses-gl-es: '0x20000'\n  arbitrary-row: name='x'"), b''),
        'stdout_diagnostic': (badging + b'W/ResourceType: diagnostic retained\n', b''),
        'stderr_diagnostic': (badging, b'warning: diagnostic retained\n'),
    }
    controls = {'actual_S42_exact_16_rejected_rows_now_recognized': True,
                'actual_S39_prior_form_still_recognized': True}
    for name, (fixture, stderr) in cases.items():
        observation = pure['feature_group_diagnostics'](pure['aapt_diagnostics'], 'badging', fixture, stderr)
        need(observation['healthy_output_shape'] is False, 'negative syntax accepted: ' + name)
        controls[name + '_rejected'] = True
    derived = {'schema': 'pocket4-S42-local-parser-reinterpretation-v1',
        'original_job_id': terminal['job_id'], 'original_remote_state': 'failed', 'original_exit_code': 1,
        'original_remote_result_reclassified': False, 'original_sources_and_outputs_modified': False,
        'original_result': INPUTS[PARENT + 'actual/stdout.original.json'],
        'original_terminal': INPUTS[PARENT + 'actual/terminal.original.json'],
        'original_shape_failure_preserved': old_health, 'new_pure_shape_observation': new_health,
        'candidate_manifest_fields_unchanged': manifest,
        'signature_evidence_unchanged_from_actual_S42': signature,
        'permission_entry_count': permissions['entry_count'],
        'local_parser_reinterpretation_complete': True,
        'new_full_remote_qualification': 'PENDING_EXPLICIT_S43_EXECUTION',
        'remote_commands': 0, 'installs': 0, 'production_ready': False}
    source = parent.decode()
    old_def = definition(parent, 'feature_group_diagnostics')
    new_def = definition(extension, 'feature_group_diagnostics')
    need(source.count(old_def) == 1, 'single exact old extension required')
    source = source.replace(old_def, new_def, 1)
    old_root = "/home/alex/work/pocket4-zbj-operator-full-verification-20261106-s42"
    new_root = "/home/alex/work/pocket4-zbj-operator-full-verification-20261106-s43"
    need(source.count(old_root) == 1, 'single exact old output root required')
    source = source.replace(old_root, new_root, 1)
    source_raw = source.encode()
    compile(source_raw, 'verify_complete_zbj_as_owner.py', 'exec')
    same = []
    for node in ast.parse(parent).body:
        if isinstance(node, ast.FunctionDef) and node.name != 'feature_group_diagnostics':
            need(definition(parent, node.name) == definition(source_raw, node.name), 'unrelated function changed: ' + node.name)
            same.append(node.name)
    need(source.replace(new_def, old_def, 1).replace(new_root, old_root, 1).encode() == parent,
         'source changed beyond output root and pure syntax extension')
    request = dict(prior_request)
    request['args'] = list(prior_request['args'])
    request['args'][3] = source
    request['idempotency_key'] = 'pocket4-zbj-operator-full-verification-s43-20261106'
    need({k for k in request if request[k] != prior_request[k]} == {'args', 'idempotency_key'},
         'request limits or invocation changed')
    need(request['args'][:3] + request['args'][4:] == prior_request['args'][:3] + prior_request['args'][4:],
         'entry flags changed')
    plan = {'schema': 'pocket4-S43-parser-fix-full-verification-plan-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'parent_actual_source': INPUTS[PARENT + 'verify_complete_zbj_as_owner.py'],
        'parent_failed_result': INPUTS[PARENT + 'actual/stdout.original.json'],
        'parent_failed_terminal': INPUTS[PARENT + 'actual/terminal.original.json'],
        'exact_minimal_change': ['new unique S43 output root/key', 'bounded contextual recognition of the three actual upstream aapt forms'],
        'all_other_functions_byte_equal': same,
        'actual_16_unknown_rows_reinterpreted_without_deleting_raw_output': True,
        'original_S42_FAILED_preserved': True,
        'only_S43_new_actual_durable_success_can_qualify_new_verification': True,
        'limits_and_each_spawn_budget_unchanged': True,
        'same_12_tools_and_one_exact_candidate_identity': True,
        'same_three_normal_full_signature_and_manifest_commands': True,
        'SDK_integrity_overrides': [], 'unknown_diagnostic_stderr_gate_preserved': True,
        'root_execution': False, 'Main_commands': 0, 'Android_commands': 0, 'installs': 0,
        'current_runtime_compatibility': 'UNKNOWN_NOT_EXECUTED',
        'fresh_scope_still_required_before_install': True,
        'production_ready': False, 'cleanup_eligible': False}
    outputs = {
        'verify_complete_zbj_as_owner.py': source_raw, 'process-request.json': encode(request),
        'local-reinterpretation.json': encode(derived),
        'local-controls.json': encode({'pure_local_only': True, 'controls': controls,
                                      'remote_jobs': 0, 'new_actual_candidate_verification_claimed': False}),
        'execution-plan.json': encode(plan),
        'against-actual-S42.diff': ''.join(difflib.unified_diff(parent.decode().splitlines(True),
            source.splitlines(True), fromfile='S42_actual/verify_complete_zbj_as_owner.py',
            tofile='S43_candidate/verify_complete_zbj_as_owner.py')).encode(),
    }
    local_inputs = [HERE / 'prepare_packet.py', HERE / 'diagnostics_extension.py'] + sorted((HERE / 'primary').iterdir())
    manifest_pins = {'schema': 1, 'state': 'PREPARED_NOT_SUBMITTED',
        'outputs': [{'path': name, 'bytes': len(content), 'sha256': sha(content)} for name, content in outputs.items()],
        'inputs': sorted(INPUTS.values(), key=lambda x: x['path']),
        'source_and_primary_references': [{'path': path.relative_to(HERE).as_posix(),
             'bytes': len(path.read_bytes()), 'sha256': sha(path.read_bytes())} for path in local_inputs]}
    outputs['SOURCE_PINS.json'] = encode(manifest_pins)
    for name in outputs:
        need(not (HERE / name).exists(), 'do not overwrite frozen output: ' + name)
    for name, content in outputs.items():
        with (HERE / name).open('xb') as stream:
            stream.write(content)
    print(json.dumps({'source_bytes': len(source_raw), 'source_sha256': sha(source_raw),
        'request_bytes': len(outputs['process-request.json']), 'request_sha256': sha(outputs['process-request.json']),
        'source_pins_bytes': len(outputs['SOURCE_PINS.json']), 'source_pins_sha256': sha(outputs['SOURCE_PINS.json']),
        'unchanged_functions': len(same), 'pure_controls': len(controls),
        'S42_failed_preserved': True, 'remote_processes_started': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
