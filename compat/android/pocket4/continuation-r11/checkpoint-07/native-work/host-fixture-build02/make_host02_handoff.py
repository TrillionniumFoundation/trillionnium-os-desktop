#!/usr/bin/env python3
"""Create a host-build02 request from pinned actual candidate05 receipts; never submit it."""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'factory-host-fixture-01'
OLD_RECEIPT = HERE.parents[1] / 'root-cp07/factory-host-build01/build-result.json'
OLD_RECEIPT_SHA = 'adb1b0cb4bfa12d3d154c0538e931a7752046f8ab295e2bab77687615af6c81e'
BASE_MANIFEST_SHA = '00a19fef1ca8e86a3da18eecfb16eedb41e9de55e2934b96987845fa8b749fbd'
COMPONENT_SHA = 'd087c114ecbeb76086abc2d91736d5f9fcbfa9e093cdff32bb63771f434cc202'
OLD_SOURCE_PINS = {
    'client_control.cc': 'cdcbbab212b5d4be64094d8050b46c96111cc4bfbc88b2a7348978962d94bd50',
    'bionic_branch_view.cc': '0eaf591282192e3675c44be6ad8ecb37441237082013cd8743b4f5d8ad664857',
    'audit_worker_binary.py': 'bda5819b28745571a9a236199052e047b806a96a7d094e0f61732d3858e71bc9',
    'build_fixture.py': 'f2cd2b63362e2149e0cd166b24f3fd3666b00d2693430fdf3306fd0aede6b9f0',
}
UNITS = ('factory-main', 'factory-context', 'factory-wire', 'client', 'bionic-branch',
         'proc_maps_raw_metadata_owner', 'proc_maps_fd_owner', 'proc_maps_path', 'proc_maps_provenance')
COMMANDS = tuple(name + '-dependencies' for name in UNITS) + tuple(name + '-compile' for name in UNITS) + (
    'factory-link', 'client-link', 'fixed-worker-closure')
REMOTE_SOURCE = '/home/alex/work/pocket4-owned-factory-v2-host-source-02'
REMOTE_OUT = '/home/alex/work/pocket4-owned-factory-v2-host-build-02'


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def valid_sha(value: str) -> str:
    require(len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'explicit SHA256 required')
    return value


def read_pinned(path: Path, wanted: str) -> bytes:
    raw = path.read_bytes()
    require(sha(raw) == valid_sha(wanted), 'pinned input changed: ' + str(path))
    return raw


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def replace_once(text: str, old: str, new: str) -> str:
    require(text.count(old) == 1, 'derivation anchor changed: ' + old[:120])
    return text.replace(old, new, 1)


def receipt_contract(source: dict, gate: dict) -> str:
    manifest = valid_sha(source['source_manifest_sha256'])
    require(source['state'] == 'CANDIDATE05_FROZEN_GATES_PENDING' and
            source['base_manifest_sha256'] == BASE_MANIFEST_SHA and
            source['component_pins_sha256'] == COMPONENT_SHA and
            source['source_files'] == 948 and source['engine_files'] == 925 and
            source['six_signal_outputs_unchanged'] is True and
            set(source['production_changed_files']) == {'host-factory-v2/source/factory_main.cc',
                                                       'engine/kernel_api/proc_maps_provenance.cc'} and
            source['reference_changed_files'] == ['references/v2-component-SOURCE_PINS.json'],
            'unexpected candidate05 source receipt')
    require(gate['state'] == 'MATCHED_SMALL_GATES_PASSED' and
            gate['source_manifest_sha256'] == manifest and gate['source_unchanged'] is True and
            gate['all_commands_pass'] is True and gate['actual_host_adapter_checks'] == 8 and
            gate['actual_ancillary_cases'] == 34 and gate['actual_listener_inheritance_fixed'] is True and
            len(gate['commands']) == 8 and all(row['returncode'] == 0 for row in gate['commands']),
            'candidate05 matched gate is incomplete')
    for key in ('full_engine_built', 'full_ART_built', 'factory_service_started', 'Android_executed',
                'default_feature_enabled', 'production_ready'):
        require(source[key] is False and gate[key] is False, 'source/gate scope unexpectedly widened')
    return manifest


def derive_builder(original: str, manifest: str, source_sha: str, gate_sha: str) -> str:
    text = original.replace('candidate-04', 'candidate-05')
    text = replace_once(text, BASE_MANIFEST_SHA, manifest)
    anchor = "COMPILER_SHA = 'e6718f7e0c7d057c3ff77b550c603da9bc4030e3ede3c053705acce1293dbe4d'\n"
    text = replace_once(text, anchor, anchor +
        "SOURCE_RECEIPT = CANDIDATE.parent / 'candidate-05-report.json'\n" +
        'SOURCE_RECEIPT_SHA = ' + repr(source_sha) + '\n' +
        "MATCHED_GATE = CANDIDATE.parent / 'combined-ancillary-controls-07/report.json'\n" +
        'MATCHED_GATE_SHA = ' + repr(gate_sha) + '\n' +
        'EXACT_SOURCE = Path(' + repr(REMOTE_SOURCE) + ')\n' +
        'EXACT_OUT = Path(' + repr(REMOTE_OUT) + ')\n')
    contract = '''def matched_gate_contract() -> None:
    source_raw = SOURCE_RECEIPT.read_bytes()
    gate_raw = MATCHED_GATE.read_bytes()
    if digest(source_raw) != SOURCE_RECEIPT_SHA or digest(gate_raw) != MATCHED_GATE_SHA:
        raise RuntimeError('actual candidate05 receipts changed')
    source, gate = json.loads(source_raw), json.loads(gate_raw)
    if not (source['source_manifest_sha256'] == MANIFEST_SHA and
            gate['state'] == 'MATCHED_SMALL_GATES_PASSED' and gate['source_manifest_sha256'] == MANIFEST_SHA and
            gate['source_unchanged'] is True and gate['all_commands_pass'] is True and
            gate['actual_host_adapter_checks'] == 8 and gate['actual_ancillary_cases'] == 34 and
            gate['actual_listener_inheritance_fixed'] is True and len(gate['commands']) == 8 and
            all(row['returncode'] == 0 for row in gate['commands'])):
        raise RuntimeError('actual candidate05 matched gate is incomplete')


'''
    text = replace_once(text, 'def inventory() -> dict[str, str]:\n', contract +
                        'def inventory() -> dict[str, str]:\n    matched_gate_contract()\n')
    text = replace_once(text,
        "    if out is None or out.parent != Path('/home/alex/work') or not out.name.startswith('pocket4-owned-factory-v2-host-build-'):\n",
        '    if out != EXACT_OUT:\n')
    text = replace_once(text, '    source = Path(__file__).resolve().parent\n',
        '    source = Path(__file__).resolve().parent\n' +
        "    if source != EXACT_SOURCE:\n        raise RuntimeError('exact fresh fixture source02 required')\n")
    text = replace_once(text, "              'candidate_manifest_sha256': MANIFEST_SHA, 'candidate_files': 948, 'engine_files': 925,\n",
        "              'candidate_manifest_sha256': MANIFEST_SHA, 'candidate_files': 948, 'engine_files': 925,\n" +
        "              'actual_source_receipt_sha256': SOURCE_RECEIPT_SHA, 'matched_gate_sha256': MATCHED_GATE_SHA,\n" +
        "              'prior_build01_receipt_sha256': '" + OLD_RECEIPT_SHA + "',\n")
    text = replace_once(text, '        inputs_before = {str(path): pin(path) for path in input_paths}\n',
        "        if len(input_paths) != 291:\n            raise RuntimeError('host fixture dependency cardinality changed')\n" +
        '        inputs_before = {str(path): pin(path) for path in input_paths}\n')
    ast.parse(text)
    return text


def make_entry(source_pins: dict) -> str:
    return '''#!/usr/bin/env python3
"""Create-only matched host source02 and build02; no service, namespace or Android execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE = Path(''' + repr(REMOTE_SOURCE) + ''')
OUT = Path(''' + repr(REMOTE_OUT) + ''')
EXPECTED = ''' + repr(source_pins) + '''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-once', action='store_true')
    args = parser.parse_args()
    if not args.execute_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'source': str(SOURCE), 'output': str(OUT),
                          'service_started': False, 'Android_execution': False}))
        return 0
    if os.geteuid() == 0:
        raise RuntimeError('existing unprivileged operator required')
    packet = globals().get('PACKET')
    if not isinstance(packet, dict) or packet.get('schema') != 1 or set(packet.get('files', {})) != set(EXPECTED):
        raise RuntimeError('verified four-file packet required')
    raw_files = {}
    for name, wanted in EXPECTED.items():
        row = packet['files'][name]
        raw = row['text'].encode()
        if len(raw) != wanted['bytes'] or hashlib.sha256(raw).hexdigest() != wanted['sha256']:
            raise RuntimeError('source packet pin differs: ' + name)
        if row['sha256'] != wanted['sha256'] or row['bytes'] != wanted['bytes']:
            raise RuntimeError('source packet declaration differs: ' + name)
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        raw_files[name] = raw
    if SOURCE.parent != Path('/home/alex/work') or OUT.parent != SOURCE.parent:
        raise RuntimeError('fixed task roots required')
    if SOURCE.exists() or SOURCE.is_symlink() or OUT.exists() or OUT.is_symlink():
        raise RuntimeError('source02 or build02 already exists; do not overwrite or retry')
    build = raw_files['build_fixture.py']
    scope = {'__name__': '_verified_host_build02_preflight', '__file__': str(SOURCE / 'build_fixture.py')}
    exec(compile(build, str(SOURCE / 'build_fixture.py'), 'exec'), scope, scope)
    scope['inventory']()
    if scope['pin'](scope['COMPILER'])['sha256'] != scope['COMPILER_SHA']:
        raise RuntimeError('compiler changed before source creation')
    SOURCE.mkdir(mode=0o700)
    for name, raw in raw_files.items():
        descriptor = os.open(SOURCE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for name, wanted in EXPECTED.items():
        raw = (SOURCE / name).read_bytes()
        if len(raw) != wanted['bytes'] or hashlib.sha256(raw).hexdigest() != wanted['sha256']:
            raise RuntimeError('created source differs')
    sys.argv = [str(SOURCE / 'build_fixture.py'), '--execute', '--out', str(OUT)]
    return scope['main']()


if __name__ == '__main__':
    raise SystemExit(main())
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-report', type=Path, required=True)
    parser.add_argument('--source-report-sha256', required=True)
    parser.add_argument('--gate-report', type=Path, required=True)
    parser.add_argument('--gate-report-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source_raw = read_pinned(args.source_report, args.source_report_sha256)
    gate_raw = read_pinned(args.gate_report, args.gate_report_sha256)
    manifest = receipt_contract(json.loads(source_raw), json.loads(gate_raw))
    old_raw = read_pinned(OLD_RECEIPT, OLD_RECEIPT_SHA)
    old = json.loads(old_raw)
    require(old['success'] is True and old['input_count'] == 291 and old['worker_audit_pass'] is True and
            old['actual_MD_equals_preflight'] is True and old['inputs_unchanged'] is True and
            old['candidate_source_unchanged'] is True and old['fixture_sources_unchanged'] is True and
            tuple(row['name'] for row in old['commands']) == COMMANDS and
            all(row['returncode'] == 0 for row in old['commands']), 'prior build01 contract differs')
    files = {name: read_pinned(OLD / name, wanted) for name, wanted in OLD_SOURCE_PINS.items()}
    for name, wanted in OLD_SOURCE_PINS.items():
        row = old['input_source_pins']['/home/alex/work/pocket4-owned-factory-v2-host-source-01/' + name]
        require(row['sha256'] == wanted and row['bytes'] == len(files[name]), 'old receipt/source binding differs')
    original = files['build_fixture.py'].decode()
    text = derive_builder(original, manifest, args.source_report_sha256, args.gate_report_sha256)
    files['build_fixture.py'] = text.encode()
    source_pins = {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in files.items()}
    entry = make_entry(source_pins)
    ast.parse(entry)
    packet = {'schema': 1, 'candidate_manifest_sha256': manifest,
              'source_receipt_sha256': args.source_report_sha256, 'matched_gate_sha256': args.gate_report_sha256,
              'entry_source': entry, 'entry_sha256': sha(entry.encode()),
              'files': {name: {**source_pins[name], 'text': raw.decode()} for name, raw in files.items()}}
    packet_raw = encoded(packet)
    wrapper = ("import sys,hashlib,json;raw=sys.stdin.buffer.read();assert hashlib.sha256(raw).hexdigest()==" +
               repr(sha(packet_raw)) + ";packet=json.loads(raw);entry=packet['entry_source'];"
               "assert hashlib.sha256(entry.encode()).hexdigest()==" + repr(sha(entry.encode())) + ";"
               "scope={'__name__':'__main__','__file__':'<verified-factory-build02-entry>','PACKET':packet};"
               "exec(compile(entry,'stage_and_build02.py','exec'),scope,scope)")
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3', 'args': ['-I', '-c', wrapper, '--execute-once'],
               'cwd': '/home/alex/work', 'env': {'PYTHONDONTWRITEBYTECODE': '1'}, 'stdin': packet_raw.decode(),
               'idempotency_key': 'pocket4-owned-factory-v2-host-build-02-20261104',
               'timeout_seconds': 600, 'cpu_quota_percent': 100, 'memory_max_bytes': 1073741824, 'nice': 10}
    patch = ''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
                                        fromfile='a/actual-build01/build_fixture.py', tofile='b/build02/build_fixture.py'))
    contents = {**files, 'stage_and_build02.py': entry.encode(), 'verified-source-packet.json': packet_raw,
                'exact-process-start-request.json': encoded(request), 'build01-to-build02.patch': patch.encode(),
                'actual-candidate05-source-report.json': source_raw, 'actual-candidate05-matched-gate.json': gate_raw,
                'actual-prior-build01-result.json': old_raw}
    root = args.output_dir
    root.mkdir(mode=0o700)
    for name, raw in contents.items():
        with (root / name).open('xb') as stream:
            stream.write(raw)
        (root / name).chmod(0o444)
    stage = {'schema': 1, 'state': 'ACTUAL_CANDIDATE05_HOST_BUILD02_REQUEST_NOT_SUBMITTED',
             'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in contents.items()},
             'candidate_manifest_sha256': manifest, 'source_receipt_sha256': args.source_report_sha256,
             'matched_gate_sha256': args.gate_report_sha256, 'prior_build01_receipt_sha256': OLD_RECEIPT_SHA,
             'remote_source': REMOTE_SOURCE, 'remote_output': REMOTE_OUT, 'expected_commands': list(COMMANDS),
             'expected_actual_dependency_count': 291, 'old_client_and_auditor_unchanged': True,
             'worker_audit_required': True, 'generated_controller_sha256': sha(text.encode()),
             'entry_sha256': sha(entry.encode()), 'service_started': False, 'Android_execution': False,
             'actual_build02_observed': False, 'submitted': False, 'production_ready': False}
    stage_raw = encoded(stage)
    with (root / 'STAGE_PINS.json').open('xb') as stream:
        stream.write(stage_raw)
    (root / 'STAGE_PINS.json').chmod(0o444)
    print(json.dumps({'root': str(root), 'source_manifest_sha256': manifest,
                      'controller_sha256': sha(text.encode()), 'entry_sha256': sha(entry.encode()),
                      'request_sha256': sha(contents['exact-process-start-request.json']),
                      'stage_pins_sha256': sha(stage_raw), 'submitted': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
