#!/usr/bin/env python3
"""Local-only assembly from exact frozen sources and actual original receipts."""
import ast
import base64
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
QA = HERE.parent


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def document(raw):
    return json.loads(raw.decode('utf-8'))


def save(name, body):
    with (HERE / name).open('xb') as output:
        output.write(body)


def encoded(raw):
    return base64.b64encode(raw).decode('ascii')


def function(source, name):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    need(len(nodes) == 1, 'ONE_FROZEN_FUNCTION')
    return ast.get_source_segment(source, nodes[0])


prior_raw = (QA / 'inspect878_reader_r1/read_completed_inspect878.py').read_bytes()
need(len(prior_raw) == 27620 and sha(prior_raw) ==
     'f068d9907ba9fe4bc5f22ca76a273156c6f1e39d7e19927ddc157eada4122272', 'ACTUAL_FROZEN_READER_SOURCE')
prior = prior_raw.decode('utf-8')
constants = {}
for node in ast.parse(prior).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in ('BASE', 'CORE', 'QA', 'TRANSPORT', 'UI_SOURCE', 'SCOPE'):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
flow = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
generated = QA / 'reconstructed/source-generation-r2'
remote_helper = '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03'
case_root = QA / 'explore_home_search_case_r1'
case_raw = (case_root / 'case.review-only.json').read_bytes()
request_raw = (case_root / 'request.review-only.json').read_bytes()
need((len(case_raw), sha(case_raw)) == (1435, '2049bd107278f39cab66fccf14a6d9dda5c66db40723761d8eb64b436ee4ae95'), 'ACTUAL_DECLARED_CASE_PIN')
need((len(request_raw), sha(request_raw)) == (1808, '5886781c82e9e392d8e1ff33b95b28bb5dba615011a50eb53cc2d1d903c026af'), 'ACTUAL_REQUEST_PIN')
actual_raw = (case_root / 'actual/stdout.original.jsonl').read_bytes()
terminal_raw = (case_root / 'actual/status-02.original.txt').read_bytes()
need((len(actual_raw), sha(actual_raw)) == (5920, '78ab558a72b5cb14ad00d6d74c978a935272d9252cd13e6a66215dbac1a3abe2'), 'ACTUAL_FAILED_STDOUT_PIN')
outer = document(actual_raw); terminal = document(terminal_raw)
need(terminal['job_id'] == '1a1b272ec9d-fc05-7e0d' and terminal['state'] == 'failed' and terminal['exit_code'] == 1,
     'ACTUAL_FAILED_TERMINAL')
child = document(outer['child_stdout_original'].encode('utf-8'))
source_files = {
    'base': (QA / 'owned_cleanup_r1/cleanup_owned_task_once.py', constants['BASE']),
    'core': (QA / 'owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py', constants['CORE']),
    'qa': (generated / 'helper/qa_contract.py', constants['QA']),
    'transport': (generated / 'recorder/bound_android_transport.py', constants['TRANSPORT']),
    'worker': (QA / 'reusable_owned_ui_r1/owned_ui_request_once.py', constants['UI_SOURCE']),
    'adapter': (generated / 'helper/qa_adapter.py', {'path': remote_helper + '/qa_adapter.py', 'bytes': 29378,
        'sha256': 'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c'}),
    'run_case': (generated / 'helper/run_case.py', {'path': remote_helper + '/run_case.py', 'bytes': 9595,
        'sha256': 'cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b'})}
for path, pin in source_files.values():
    raw = path.read_bytes()
    need((len(raw), sha(raw)) == (pin['bytes'], pin['sha256']), 'SOURCE_CLOSURE_ORIGINAL_BYTES')
config = {'sources': {key: pin for key, (_, pin) in source_files.items()}, 'scope': constants['SCOPE'],
    'launch': {'path': flow + '/launch-scope.json', 'bytes': None,
               'sha256': '54a669eb54fa0dcf6df5afcd17848af7511c2122623192051eb6370e42bfbb06'},
    'case': child['input_artifact'], 'request': outer['request'],
    'actual_stdout_base64': encoded(actual_raw), 'actual_stdout_sha256': sha(actual_raw),
    'terminal_base64': encoded(terminal_raw), 'terminal_bytes': len(terminal_raw), 'terminal_sha256': sha(terminal_raw),
    'child_stdout_sha256': outer['child_stdout_sha256'], 'original_case_stdout_sha256': child['original_stdout_sha256']}
# Only this file's hash/size metadata is extracted from the prior private reader.
# Its node content is never copied to this source, proof, packet or manifest.
private_reader = QA.parents[1] / 'p4_private_ui/inspect878-reader-r1/stdout.private.original.json'
private_raw = private_reader.read_bytes()
need((len(private_raw), sha(private_raw)) == (18671,
     '7dd40d2079fbfcc081cffcce9ed60308060f3fad696300d2a4cc0bdc27b1c63d'), 'ACTUAL_PRIOR_PRIVATE_READER_PIN')
metadata = document(private_raw)['files'][config['launch']['path']]
need(metadata['sha256'] == config['launch']['sha256'] and type(metadata['bytes']) is int,
     'ACTUAL_LAUNCH_SCOPE_METADATA_ONLY')
config['launch']['bytes'] = metadata['bytes']
template = (HERE / 'reader_body.py.in').read_text()
need(template.count('CONFIG = None') == template.count('BASE = None') == 1, 'ONE_LITERAL_CONFIGURATION_SLOT')
source = template.replace('CONFIG = None', 'CONFIG = ' + repr(config), 1).replace('BASE = None', 'BASE = ' + repr(constants['BASE']), 1)
for name, marker in (('load_base', '# EXACT_PREVIOUS_LOAD_BASE'), ('census', '# EXACT_PREVIOUS_CENSUS')):
    need(source.count(marker) == 1, 'ONE_FROZEN_FUNCTION_SLOT')
    source = source.replace(marker, function(prior, name), 1)
raw = source.encode('utf-8'); compile(raw, str(HERE / 'read_failed_case.py'), 'exec')
packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo', 'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', source,
    '--collect-once', '--source-sha256', sha(raw)], 'cwd': '/home/alex/work', 'timeout_seconds': 150,
    'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10,
    'idempotency_key': 'pocket4-beike-task878-case-failure-host-reader-r1-20261106'}
packet_raw = (json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
save('read_failed_case.py', raw)
save('process-request.review-only.json', packet_raw)
proof = {'local_only': True, 'remote_submitted': False, 'source': {'bytes': len(raw), 'sha256': sha(raw)},
    'packet': {'bytes': len(packet_raw), 'sha256': sha(packet_raw)},
    'exact_frozen_load_base_and_census': True, 'actual_controller_failure_bytes_embedded': True,
    'actual_case_original_returncode': child['original_returncode'], 'actual_original_outcome_unknown': True,
    'actual_launch_scope_pin': config['launch'], 'source_inputs_checked': len(source_files),
    'Main_operations': 0, 'production_ready': False}
save('LOCAL_PACKET_PROOF.json', (json.dumps(proof, indent=2, sort_keys=True) + '\n').encode())
print(json.dumps(proof, sort_keys=True))
