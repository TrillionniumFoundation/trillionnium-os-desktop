"""Exact live audio composition functions after preserved Sensor staging."""
import copy

import grp

import hashlib

import json

from pathlib import Path

import re

import stat

BASE_PINS = {
    'deployment/host-build-input.json': 'b09d91fdc663275ae1c0ed049795f3c00467eecca74f94844c2c2b6d7184d535',
    'deployment/transaction-runner.py': '1ebd5406c5cf37d84e9b16b6caa5783554918e624537bddcd0ed64e044049de0',
    'qualification/qualify_final.py': '914ba73aa6f68a5cf685a73cba01cb2ee04543d8c30bd02f3e02cc58076abeba',
}

COHORT = ('droidloom-supervisor', 'droidloomd', 'droidloomctl', 'droidloom-applications')

COHORT_TARGETS = tuple('/usr/bin/' + name for name in COHORT)

SOCKETS = ('droidloom-audio-host.socket', 'droidloom-audio-capture.socket')

SERVICES = ('droidloom-audio-host.service', 'droidloom-audio-capture.service')

UNIT_ROOT = '/usr/lib/systemd/system/'

UNIT_PATHS = tuple(UNIT_ROOT + name for name in SOCKETS + SERVICES)

DROPIN = UNIT_ROOT + 'droidloomd.service.d/50-pocket4-audio.conf'

HELPERS = {
    SERVICES[0]: '/usr/lib/droidloom/runtime/pocket4/bin/droidloom-audio-host',
    SERVICES[1]: '/usr/lib/droidloom/runtime/pocket4/bin/droidloom-audio-capture',
}

APEX_GUEST = '/vendor/apex/com.android.hardware.audio.droidloom.apex'

APEX_TARGET = '/usr/lib/droidloom/runtime/pocket4' + APEX_GUEST

NEW_TARGETS = tuple(HELPERS.values()) + (APEX_TARGET,) + UNIT_PATHS + (DROPIN,)

ALL_TARGETS = NEW_TARGETS + COHORT_TARGETS

ENDPOINTS = {SOCKETS[0]: '/run/droidloom/audio/1000/audio.sock',
             SOCKETS[1]: '/run/droidloom/audio/1000/audio-input.sock'}

FINAL_COUNTS = {'checksums_verified': 53, 'install_count': 38,
                'file_overrides': 50, 'runtime_directories': 4}

STAGE_COUNT = 27

def relative(target):
    return 'deployment/payload/' + target.lstrip('/')

def allowlist():
    return set(BASE_PINS) | {relative(p) for p in ALL_TARGETS}

def compose(io, model, base, built, audio):
    """Extend the already qualified native/Sensor composition deterministically."""
    manifest = built['manifest']
    plan = built['transaction']
    qplan = built['qualification_plan']
    output = built['metadata']
    sources = audio['sources']
    original_manifest = base['values']['deployment/manifest.json']
    payloads = {r['install_target']: r for r in manifest['payload']}
    operations = {r['target']: r for r in plan['install_operations']}
    for target in ALL_TARGETS:
        source = sources[target]
        mode = 0o755 if target in COHORT_TARGETS or target in HELPERS.values() else 0o644
        staged = relative(target).removeprefix('deployment/')
        if target in COHORT_TARGETS:
            payload, operation = payloads[target], operations[target]
            io.need(payload['role'] == 'matched_host_runtime'
                    and operation['expected_current'] != {'absent': True}, 'ONLY_EXISTING_COMPLETE_HOST_COHORT_REPLACED')
            payload['prior_staged_source'] = copy.deepcopy(payload['source'])
        else:
            io.need(target not in payloads and target not in operations, 'EXACT_NEW_AUDIO_PAYLOAD')
            role = 'android_file_override' if target == APEX_TARGET else 'host_audio_runtime'
            payload = {'install_target': target, 'install_owner': {'uid': 0, 'gid': 0},
                       'install_mode': mode, 'mode': mode, 'role': role,
                       'path': str(model.DEPLOY / staged), 'relative_path': staged}
            operation = {'target': target, 'uid': 0, 'gid': 0, 'mode': mode,
                         'expected_current': {'absent': True}, 'staged_relative_path': staged}
            manifest['payload'].append(payload)
            plan['install_operations'].append(operation)
        payload.update(bytes=source['bytes'], sha256=source['sha256'], source=model.source_record(source),
                       qualified_source=copy.deepcopy(audio['packet']['files'][target]))
        operation['sha256'] = source['sha256']
        built['payload_sources'][relative(target)] = source
    io.need(not any(r['guest_target'] == APEX_GUEST for r in manifest['android_file_overrides']), 'NEW_AUDIO_APEX_OVERRIDE_ONLY')
    manifest['android_file_overrides'].append({'candidate_source': APEX_TARGET, 'guest_target': APEX_GUEST,
        'operation': 'install_staged', 'staged_relative_path': relative(APEX_TARGET).removeprefix('deployment/'),
        'qualified_source': copy.deepcopy(audio['packet']['files'][APEX_TARGET])})
    lifecycle = {'schema': 'pocket4-final-audio-lifecycle-v1', 'socket_uid': 1000, 'socket_gid': 1041,
        'socket_mode': 0o660, 'endpoints': dict(ENDPOINTS), 'helper_paths': dict(HELPERS),
        'guest_endpoints': ['/dev/socket/droidloom/audio', '/dev/socket/droidloom/audio-input'],
        'peer_cgroup': '/system.slice/droidloomd.service', 'peer_uid': 1041, 'peer_gid': 1041,
        'files': {target: {'bytes': sources[target]['bytes'], 'sha256': sources[target]['sha256'],
                  'mode': 0o755 if target in HELPERS.values() else 0o644} for target in NEW_TARGETS},
        'source_qualification': audio['packet_ref'], 'runtime_qualified': False,
        'activation': 'daemon Requires/After both system sockets; real HAL connection activates corresponding helper',
        'retirement': 'normal Main stop, daemon stop, both helper cgroups empty, listeners removed; unknown command outcomes retain all preimages'}
    manifest['audio_lifecycle'] = copy.deepcopy(lifecycle)
    plan['audio_lifecycle'] = copy.deepcopy(lifecycle)
    manifest['actual_component_source_qualification']['audio'] = audio['packet_ref']
    plan['actual_component_source_qualification']['audio'] = audio['packet_ref']
    built['source_qualification']['audio'] = audio['packet_ref']
    qplan['maintenance']['audio_build_complete'] = copy.deepcopy(audio['gate'])
    qplan['references']['host_build'] = copy.deepcopy(audio['evidence']['host_build'])
    qplan['references']['host_mount'] = copy.deepcopy(audio['evidence']['host_mount'])
    qplan['references']['audio_source_qualification'] = audio['packet_ref']
    qplan['references']['audio_deployment_extension_controls'] = copy.deepcopy(audio['evidence']['deployment_extension_controls'])
    cli = qplan['component_inputs']['camera']['host_cli']
    io.need(cli['path'] == '/usr/bin/droidloomctl', 'UNCHANGED_CANONICAL_CAMERA_HOST_CLI')
    cli['sha256'] = sources['/usr/bin/droidloomctl']['sha256']
    cell = io.parse(output['deployment/cell.candidate.json'])
    cell['android_file_overrides'] = [{'source': r['candidate_source'], 'target': r['guest_target']}
                                     for r in manifest['android_file_overrides']]
    io.need(cell['android_runtime_directories'] == base['values']['deployment/cell.candidate.json']['android_runtime_directories'],
            'AUDIO_SOCKET_BINDING_IS_IN_NORMAL_COHORT_NOT_A_NEW_RUNTIME_DIRECTORY')
    camera_entry = io.parse(output['camera/runtime-entry.json'])
    camera_entry['component_inputs.camera'] = copy.deepcopy(qplan['component_inputs']['camera'])
    old_host = base['values']['deployment/host-build-input.json']
    new_host = copy.deepcopy(old_host)
    new_host.update(binaries=[{'target': p, 'bytes': sources[p]['bytes'], 'sha256': sources[p]['sha256']}
                              for p in COHORT_TARGETS],
        build_receipt=model.source_record(audio['evidence_pins']['host_build']),
        mount_qualification_receipt=model.source_record(audio['evidence_pins']['host_mount']),
        source_commit=audio['packet']['host_source_base_commit'], source_tree=audio['packet']['host_source_tree'],
        source_manifest=audio['packet']['host_source_manifest'], previous_staged_cohort=copy.deepcopy(old_host),
        observed_unix=audio['packet']['observed_unix'], production_installed=False)
    io.need(new_host['source_commit'] == '5957addac279b11110c6cdd406e32ef871a7c511'
            and re.fullmatch('[0-9a-f]{40}', new_host['source_tree']), 'MATCHED_AUDIO_COHORT_BASE_AND_COMPLETE_TREE')
    output['deployment/host-build-input.json'] = io.encode(new_host)
    host_ref = model.new_ref(model.DEPLOY / 'host-build-input.json', output['deployment/host-build-input.json'], manifest['host_build_input'])
    manifest['host_build_input'] = copy.deepcopy(host_ref)
    plan['host_build_input'] = copy.deepcopy(host_ref)
    for name, target in (('transaction-runner.py', 'deployment/transaction-runner.py'),
                         ('qualify_final.py', 'qualification/qualify_final.py')):
        output[target] = model.EXTENSION_CONTENTS[name]
    runner_ref = model.new_ref(model.DEPLOY / 'transaction-runner.py', output['deployment/transaction-runner.py'], manifest['transaction_runner'])
    manifest['transaction_runner'] = copy.deepcopy(runner_ref)
    plan['transaction_runner'] = copy.deepcopy(runner_ref)
    prior_tooling = copy.deepcopy(original_manifest['qualification_tooling'])
    current_sources = copy.deepcopy(prior_tooling['candidate_sources'])
    for row in current_sources:
        if row['path'] == str(model.DEPLOY / 'transaction-runner.py'):
            row.update({k: runner_ref[k] for k in ('bytes', 'sha256')})
        if row['path'] == str(model.FINAL / 'qualification/qualify_final.py'):
            raw = output['qualification/qualify_final.py']
            row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    tooling = {'schema': 'pocket4-qualified-audio-deployment-tooling-v1',
        'candidate_sources': current_sources, 'prior_source_qualification': prior_tooling,
        'extension_controls': copy.deepcopy(audio['evidence']['deployment_extension_controls']),
        'scope': 'audio install and lifecycle extension; original six post-start checks retained; runtime not run',
        'production_changed': False}
    manifest['qualification_tooling'] = copy.deepcopy(tooling)
    plan['qualification_tooling'] = copy.deepcopy(tooling)
    output['qualification/plan.json'] = io.encode(qplan)
    output['deployment/cell.candidate.json'] = io.encode(cell)
    output['camera/runtime-entry.json'] = io.encode(camera_entry)
    cell_ref = model.new_ref(model.DEPLOY / 'cell.candidate.json', output['deployment/cell.candidate.json'], manifest['candidate_cell'])
    manifest['candidate_cell'] = cell_ref
    plan['candidate_cell_sha256'] = plan['cell_operation']['sha256'] = cell_ref['sha256']
    config = io.parse(output['deployment/qualification-config.json'])
    qref = model.new_ref(model.FINAL / 'qualification/plan.json', output['qualification/plan.json'])
    for name, phase in (('maintenance_gate', 'maintenance'), ('post_start_qualification', 'post')):
        config[name]['sha256'] = hashlib.sha256(output['qualification/qualify_final.py']).hexdigest()
        config[name]['args'] = ['--phase', phase, '--plan', qref['path'], '--expect-plan-sha256', qref['sha256']]
    output['deployment/qualification-config.json'] = io.encode(config)
    manifest['qualification_config'] = model.new_ref(model.DEPLOY / 'qualification-config.json',
        output['deployment/qualification-config.json'], manifest['qualification_config'])
    camera_ref = model.new_ref(model.FINAL / 'camera/runtime-entry.json', output['camera/runtime-entry.json'])
    manifest['camera_runtime_entry'] = plan['camera_runtime_entry'] = camera_ref
    output['deployment/transaction-plan.json'] = io.encode(plan)
    manifest['transaction_plan'] = model.new_ref(model.DEPLOY / 'transaction-plan.json',
        output['deployment/transaction-plan.json'], manifest['transaction_plan'])
    output['deployment/manifest.json'] = io.encode(manifest)
    verification = io.parse(output['deployment/verification.json'])
    verification.update(manifest_sha256=hashlib.sha256(output['deployment/manifest.json']).hexdigest(),
        plan_sha256=manifest['transaction_plan']['sha256'], candidate_cell_sha256=cell_ref['sha256'],
        qualified_tool_repair=tooling, actual_component_source_qualification=copy.deepcopy(built['source_qualification']),
        candidate_counts={'checksums': 53, 'payload': 38, 'overrides': 50, 'runtime_directories': 4},
        audio_lifecycle=lifecycle)
    output['deployment/verification.json'] = io.encode(verification)
    digests = {name.removeprefix('deployment/'): hashlib.sha256(raw).hexdigest()
               for name, raw in output.items() if name.startswith('deployment/') and name != 'deployment/SHA256SUMS'}
    digests.update({name.removeprefix('deployment/'): row['sha256'] for name, row in built['payload_sources'].items()})
    sums = [(digests.get(name, old_sha), name) for old_sha, name in built['final_sums']]
    for target in NEW_TARGETS:
        name = relative(target).removeprefix('deployment/')
        io.need(name not in {n for _, n in sums}, 'NEW_AUDIO_CHECKSUM_DUPLICATE')
        sums.append((sources[target]['sha256'], name))
    io.need(len(sums) == len({n for _, n in sums}) == 53, 'EXACT_53_SUMS_WITH_EIGHT_NEW_AUDIO_PAYLOADS')
    output['deployment/SHA256SUMS'] = ''.join(sha + '  ' + name + '\n' for sha, name in sums).encode()
    built['final_sums'] = sums
    io.need(len(manifest['payload']) == len(plan['install_operations']) == 38
            and len(manifest['android_file_overrides']) == 50
            and len(manifest['android_runtime_directories']) == 4, 'EXACT_AUDIO_EXTENDED_38_50_4_COMPOSITION')
    io.need(set(output) == set(model.BASE_PINS) | set(BASE_PINS)
            and len(set(output) | set(built['payload_sources'])) == STAGE_COUNT, 'EXACT_27_CANDIDATE_WRITES')
    return built
