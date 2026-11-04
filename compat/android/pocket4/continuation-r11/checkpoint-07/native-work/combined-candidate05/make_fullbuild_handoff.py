#!/usr/bin/env python3
"""Create-only local request generation from actual candidate05 receipts."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'fullbuild-plan-01/freeze-01'
FENCES = HERE.parent / 'build-admission-fences-02'
CONTROLLER04_SHA = 'ba4dffc59b224b32e6f42f7f66222d35cdd62eecb82dabea67d05dc888635d6d'
FENCES02_SHA = 'bc31ba59729166c7d87aebcfab699d5abc7f8433b58a34eee9cfea229b90adbc'
SNAPSHOT_SHA = 'f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb'
BASE_MANIFEST_SHA = '00a19fef1ca8e86a3da18eecfb16eedb41e9de55e2934b96987845fa8b749fbd'
COMPONENT_SHA = 'd087c114ecbeb76086abc2d91736d5f9fcbfa9e093cdff32bb63771f434cc202'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, why):
    if not value:
        raise RuntimeError(why)


def valid_sha(value):
    require(len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'explicit actual SHA required')
    return value


def read_pinned(path, wanted):
    raw = path.read_bytes()
    require(sha(raw) == valid_sha(wanted), 'input changed: ' + str(path))
    return raw


def put(root, name, raw):
    with (root / name).open('xb') as stream:
        stream.write(raw)
    (root / name).chmod(0o444)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def prepare_request(args):
    source_raw = read_pinned(args.source_report, args.source_report_sha256)
    gate_raw = read_pinned(args.gate_report, args.gate_report_sha256)
    source = json.loads(source_raw)
    gate = json.loads(gate_raw)
    wanted = valid_sha(source['source_manifest_sha256'])
    require(source['state'] == 'CANDIDATE05_FROZEN_GATES_PENDING' and
            source['base_manifest_sha256'] == BASE_MANIFEST_SHA and
            source['component_pins_sha256'] == COMPONENT_SHA and
            source['source_files'] == 948 and source['engine_files'] == 925 and
            source['six_signal_outputs_unchanged'] is True and
            set(source['production_changed_files']) == {'host-factory-v2/source/factory_main.cc',
                                                       'engine/kernel_api/proc_maps_provenance.cc'} and
            source['reference_changed_files'] == ['references/v2-component-SOURCE_PINS.json'],
            'unexpected candidate05 source receipt')
    require(gate['state'] == 'MATCHED_SMALL_GATES_PASSED' and gate['source_manifest_sha256'] == wanted and
            gate['source_unchanged'] is True and gate['all_commands_pass'] is True and
            gate['actual_host_adapter_checks'] == 8 and gate['actual_ancillary_cases'] == 34 and
            gate['actual_listener_inheritance_fixed'] is True and len(gate['commands']) == 8 and
            all(command['returncode'] == 0 for command in gate['commands']), 'candidate05 matched gate is incomplete')
    for key in ('full_engine_built', 'full_ART_built', 'factory_service_started', 'Android_executed',
                'default_feature_enabled', 'production_ready'):
        require(source[key] is False and gate[key] is False, 'source/gate scope unexpectedly widened')
    original = read_pinned(PREVIOUS / 'combined_build.py', CONTROLLER04_SHA).decode()
    text = original.replace('candidate-04', 'candidate-05').replace('candidate04', 'candidate05')
    text = text.replace('combined04', 'combined05').replace('COMBINED04', 'COMBINED05')
    require(text.count(BASE_MANIFEST_SHA) == 1, 'controller manifest placeholder changed')
    text = text.replace(BASE_MANIFEST_SHA, wanted)
    anchor = "FEATURE = \"BERBERIS_PROCMAPS_RAW_METADATA_OWNER\"\n"
    require(text.count(anchor) == 1, 'controller feature anchor changed')
    text = text.replace(anchor, anchor +
        'MATCHED_GATE = COMPOSITION / "combined-ancillary-controls-07/report.json"\n' +
        'MATCHED_GATE_SHA = ' + repr(args.gate_report_sha256) + '\n')
    gate_function = '''def matched_gate_contract():
    require(digest(MATCHED_GATE) == MATCHED_GATE_SHA, "matched candidate05 gate changed")
    gate = json.loads(MATCHED_GATE.read_bytes())
    require(gate["state"] == "MATCHED_SMALL_GATES_PASSED" and
            gate["source_manifest_sha256"] == MANIFEST_SHA and
            gate["source_unchanged"] is True and gate["all_commands_pass"] is True and
            gate["actual_host_adapter_checks"] == 8 and gate["actual_ancillary_cases"] == 34 and
            gate["actual_listener_inheritance_fixed"] is True and
            len(gate["commands"]) == 8 and all(row["returncode"] == 0 for row in gate["commands"]),
            "matched candidate05 gate is not complete")

'''
    require(text.count('def source_contract():\n') == 1, 'source-contract anchor changed')
    text = text.replace('def source_contract():\n', gate_function + 'def source_contract():\n    matched_gate_contract()\n')
    ast.parse(text)
    controller = text.encode()
    controller_sha = sha(controller)
    wrapper = ("import sys,hashlib;raw=sys.stdin.buffer.read();expected=" + repr(controller_sha) +
               ";assert hashlib.sha256(raw).hexdigest()==expected;"
               "scope={'__name__':'__main__','__file__':'<verified-combined05-controller>',"
               "'VERIFIED_CONTROLLER_SHA256':expected};"
               "exec(compile(raw,'combined_build05.py','exec'),scope,scope)")
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3', 'args': ['-I', '-c', wrapper, '--prepare'],
               'cwd': '/home/alex/work', 'env': {'PYTHONDONTWRITEBYTECODE': '1'}, 'stdin': text,
               'idempotency_key': 'pocket4-native-combined05-full-source-preparation-01-20261104',
               'timeout_seconds': 300, 'cpu_quota_percent': 100, 'memory_max_bytes': 1073741824, 'nice': 10}
    root = args.output_dir
    root.mkdir(mode=0o700)
    put(root, 'combined_build05.py', controller)
    put(root, 'actual-source-report.json', source_raw)
    put(root, 'actual-matched-gate-report.json', gate_raw)
    put(root, 'exact-preparation-request.json', encoded(request))
    patch = ''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
                                        fromfile='a/frozen-combined04.py', tofile='b/combined_build05.py'))
    put(root, 'controller04-to-controller05.patch', patch.encode())
    rows = {p.name: {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size} for p in root.iterdir() if p.is_file()}
    manifest = {'schema': 1, 'state': 'NEW_CANDIDATE05_PREPARATION_REQUEST_NOT_SUBMITTED', 'files': rows,
                'controller_sha256': controller_sha, 'candidate05_manifest_sha256': wanted,
                'matched_gate_sha256': args.gate_report_sha256, 'actual_preparation_observed': False,
                'base_controller_sha256': CONTROLLER04_SHA, 'Main_actions': 0, 'fullbuild_started': False}
    put(root, 'STAGE_PINS.json', encoded(manifest))
    print(json.dumps({'root': str(root), 'controller_sha256': controller_sha,
                      'request_sha256': rows['exact-preparation-request.json']['sha256'],
                      'stage_pins_sha256': sha((root / 'STAGE_PINS.json').read_bytes()), 'submitted': False}))


def build_request(args):
    raw = read_pinned(args.stage_dir / 'STAGE_PINS.json', args.stage_pins_sha256)
    stage = json.loads(raw)
    require(stage['state'] == 'NEW_CANDIDATE05_PREPARATION_REQUEST_NOT_SUBMITTED', 'wrong stage')
    for name, row in stage['files'].items():
        require(Path(name).name == name, 'unexpected stage path')
        value = read_pinned(args.stage_dir / name, row['sha256'])
        require(len(value) == row['bytes'], 'stage size changed')
    preparation_sha = valid_sha(args.preparation_sha256)
    controller = read_pinned(args.stage_dir / 'combined_build05.py', stage['controller_sha256']).decode()
    original = read_pinned(FENCES / 'fenced_build.py', FENCES02_SHA).decode()
    snapshot = read_pinned(FENCES / 'main_snapshot.py', SNAPSHOT_SHA).decode()
    text = original.replace(CONTROLLER04_SHA, stage['controller_sha256'])
    text = text.replace('30044956dbcc2d73a067750abb36f62e4ff52d5aa703f5321aedcba80397c743', preparation_sha)
    text = text.replace('full-build-combined04-01', 'full-build-combined05-01').replace('build-fences-02', 'build-fences-03')
    require('full-build-combined04-01' not in text and CONTROLLER04_SHA not in text, 'old controller retained')
    ast.parse(text)
    packet = {'schema': 1, 'outer_source': text, 'outer_sha256': sha(text.encode()),
              'controller_source': controller, 'snapshot_source': snapshot, 'snapshot_sha256': SNAPSHOT_SHA}
    packet_raw = encoded(packet)
    wrapper = ("import sys,hashlib,json;raw=sys.stdin.buffer.read();assert hashlib.sha256(raw).hexdigest()==" +
               repr(sha(packet_raw)) + ";packet=json.loads(raw);source=packet['outer_source'];"
               "assert hashlib.sha256(source.encode()).hexdigest()==" + repr(sha(text.encode())) + ";"
               "scope={'__name__':'__main__','__file__':'<verified-combined05-fenced-build>','PACKET':packet};"
               "exec(compile(source,'fenced_build05.py','exec'),scope,scope)")
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3',
               'args': ['-I', '-c', wrapper, '--execute-once'], 'cwd': '/home/alex/work',
               'env': {'PYTHONDONTWRITEBYTECODE': '1'}, 'stdin': packet_raw.decode(),
               'idempotency_key': 'pocket4-native-combined05-fenced-full-engine-flag0-build-01-20261104',
               'timeout_seconds': 6400, 'cpu_quota_percent': 200, 'memory_max_bytes': 11811160064, 'nice': 10}
    root = args.output_dir
    root.mkdir(mode=0o700)
    put(root, 'fenced_build05.py', text.encode())
    put(root, 'main_snapshot.py', snapshot.encode())
    put(root, 'verified-source-packet.json', packet_raw)
    put(root, 'exact-fullbuild-request.json', encoded(request))
    patch = ''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
                                        fromfile='a/fenced-build02.py', tofile='b/fenced-build05.py'))
    put(root, 'fence02-to-fence03.patch', patch.encode())
    rows = {p.name: {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size} for p in root.iterdir() if p.is_file()}
    manifest = {'schema': 1, 'state': 'CANDIDATE05_FENCED_BUILD_REQUEST_NOT_SUBMITTED', 'files': rows,
                'actual_preparation_sha256': preparation_sha, 'prepared_source_stage_pins_sha256': args.stage_pins_sha256,
                'candidate05_manifest_sha256': stage['candidate05_manifest_sha256'],
                'Main_snapshot_source_sha256': SNAPSHOT_SHA, 'main_observed_invariants_and_oom_gate': True,
                'resource_budget': {'cpu_quota_percent': 200, 'memory_max_bytes': 11811160064,
                                    'own_memory_swap_max_bytes': 1073741824, 'normal_builder_jobs': 1},
                'feature_enabled': False, 'ART_built': False, 'factory_service_started': False,
                'whole_apps_ready': False, 'submitted': False}
    put(root, 'REQUEST_PINS.json', encoded(manifest))
    print(json.dumps({'root': str(root), 'request_sha256': rows['exact-fullbuild-request.json']['sha256'],
                      'request_pins_sha256': sha((root / 'REQUEST_PINS.json').read_bytes()), 'submitted': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare-request')
    prepare.add_argument('--source-report', type=Path, required=True)
    prepare.add_argument('--source-report-sha256', required=True)
    prepare.add_argument('--gate-report', type=Path, required=True)
    prepare.add_argument('--gate-report-sha256', required=True)
    prepare.add_argument('--output-dir', type=Path, required=True)
    build = commands.add_parser('build-request')
    build.add_argument('--stage-dir', type=Path, required=True)
    build.add_argument('--stage-pins-sha256', required=True)
    build.add_argument('--preparation-sha256', required=True)
    build.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    (prepare_request if args.command == 'prepare-request' else build_request)(args)


if __name__ == '__main__':
    main()
