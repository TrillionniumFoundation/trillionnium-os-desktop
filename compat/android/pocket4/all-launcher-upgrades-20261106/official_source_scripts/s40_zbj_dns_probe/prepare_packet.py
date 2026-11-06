#!/usr/bin/env python3
"""Seal a local review packet. Never executes the DNS worker or remote tools."""
from pathlib import Path
import ast
import hashlib
import json
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def write_new(name, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, ('FROZEN_PACKET_DIFFERS', name)
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return pin(path)


source_path = HERE / 'probe_once.py'
source = source_path.read_text()
tree = ast.parse(source)
compile(source, str(source_path), 'exec')
functions = {node.name: ast.get_source_segment(source, node)
             for node in tree.body if isinstance(node, ast.FunctionDef)}
parent_path = PROJECT / 'official_source_scripts/s38_szzc_operator_signature/observe_signature_as_owner.py'
parent_source = parent_path.read_text()
parent_ast = ast.parse(parent_source)
parent_census = next(ast.get_source_segment(parent_source, node) for node in parent_ast.body
                     if isinstance(node, ast.FunctionDef) and node.name == 'census')
assert functions['census'] == parent_census

authority_path = PROJECT / 'official_source_scripts/s34_zbj_tail/actual-r1/com.zhubajie.client-result.raw.json'
authority_bytes = authority_path.read_bytes()
assert hashlib.sha256(authority_bytes).hexdigest() == 'c49b3c374226329c92810d11bacee29c75023c26bf648bf5c4a6ebf7ea741135'
authority = json.loads(authority_bytes)
assert urlsplit(authority['url']).scheme == 'https'
assert urlsplit(authority['url']).hostname == 's.shouji.qihucdn.com'
assert authority['status'] == 'SEGMENTED_TRANSFER_FAILED'
readback_path = PROJECT / 'reference/rail-zbj-delivery-research-r1/receipt-readback-r1/verification.json'
readback_raw = readback_path.read_bytes()
assert hashlib.sha256(readback_raw).hexdigest() == 'b4a65754c4c39931b821458c08de049ecf5421b2de28b531c2c4708e79981882'
readback = json.loads(readback_raw)
assert readback['all_ns_exact'] is True and readback['receipts_read'] == 3
assert readback['body_file_info_only'] == 3 and readback['new_DNS_observation'] is False

getaddrinfo_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'socket' and node.func.attr == 'getaddrinfo']
assert len(getaddrinfo_calls) == 1
assert len(getaddrinfo_calls[0].args) == 6 and not getaddrinfo_calls[0].keywords
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        assert all(item.name in {'fcntl', 'json', 'os', 'signal', 'socket', 'sys', 'time'} for item in node.names)
    assert not isinstance(node, ast.ImportFrom)
    if isinstance(node, ast.Call):
        assert not (isinstance(node.func, ast.Name) and node.func.id in {'eval', 'exec', 'open', 'compile', '__import__'})
        if isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {'system', 'popen', 'fork', 'forkpty', 'posix_spawn', 'posix_spawnp',
                                          'execv', 'execve', 'execvp', 'execvpe', 'spawn', 'connect',
                                          'create_connection', 'send', 'sendto', 'sendall', 'kill',
                                          'mkdir', 'unlink', 'remove', 'rename', 'replace', 'chmod', 'chown',
                                          'putenv', 'unsetenv'}

request = {
    'host': 'pocket4', 'executable': '/usr/bin/python3',
    'args': ['-I', '-B', '-c', source, '--resolve-zbj-official-host-once'],
    'cwd': '/home/alex/work',
    'idempotency_key': 'pocket4-zbj-system-resolver-observation-20261106-r1',
    'cpu_quota_percent': 100, 'memory_max_bytes': 134217728,
    'nice': 10, 'timeout_seconds': 45,
}
request_ref = write_new('process-request.json', request)
controls_ref = write_new('local-static-controls.json', {
    'schema': 'pocket4-zbj-dns-local-static-controls-v1',
    'syntax_compiled_without_execution': True,
    'exactly_one_getaddrinfo_callsite': True,
    'original_s38_census_function_byte_equal': True,
    's34_authority_raw_full_sha_verified': True,
    'hostname_derived_from_actual_official_URL': True,
    'three_receipts_and_body_identity_actual_readback_bound': True,
    'no_http_client_subprocess_or_mutation_callsite': True,
    'actual_DNS_calls_during_preparation': 0,
    'actual_probe_executed': False,
})
plan_ref = write_new('execution-plan.json', {
    'schema': 'pocket4-zbj-dns-one-shot-plan-v1',
    'state': 'SEALED_FOR_ROOT_REVIEW_NOT_EXECUTED',
    'purpose': 'Observe whether the ordinary Pocket4 OS resolver currently resolves the exact official CDN hostname after the settled S34 curl6 failure.',
    'hostname': 's.shouji.qihucdn.com',
    'hostname_authority': pin(authority_path),
    'official_URL_literal': authority['url'],
    'prior_failure_kept': 'official_source_scripts/s34_zbj_tail/actual-r1/range-0003.raw.json',
    'completed_readback': pin(readback_path),
    'request': request_ref, 'source': pin(source_path),
    'inherited_census_source': pin(parent_path),
    'operation': 'socket.getaddrinfo(hostname,443,AF_UNSPEC,SOCK_STREAM,IPPROTO_TCP,0) exactly once',
    'system_configuration': 'Use existing OS/NSS resolver unchanged. Normal resolver internal retransmissions and IPv4/IPv6 queries are not controlled or represented as a single wire packet.',
    'timer': 'The owned probe sets a20s ITIMER_REAL with SIG_DFL; if libc stalls, SIGALRM terminates only this process. Remote supervisor timeout45s is the outer bound.',
    'timeout_interpretation': 'A signal/timeout/missing final JSON is failure or incomplete observation, never PASS. The started marker does not prove successful resolution or FD restoration.',
    'success_gate': ['actual durable exit0', 'one complete started marker and one complete final JSON',
                     'ordinary UID/EUID/GID/EGID1000', 'exact hostname and one getaddrinfo call',
                     'nonempty bounded TCP IPv4/IPv6 answers for port443', 'no error',
                     'elapsed less than20s', 'original self FD identities restored',
                     'no supervisor timeout/cancellation/log truncation'],
    'failure_action': 'Keep original output/terminal and stop. No new key, automatic retry, address override or download follows.',
    'source_read_scope_at_runtime': 'Normal interpreter/library/NSS inputs and /proc/self/fd only. No Android path, Main FD, business data, APK or root-private dependency file.',
    'stdout_owner': 'Hepta durable process capture; worker creates no output files.',
    'interpreter_provenance': 'Existing /usr/bin/python3 -I -B entry used by the actual S38/S39 operator jobs. This probe records sys.executable/version; it does not falsely claim a full current interpreter hash qualification.',
    'allowed_followup_after_success': 'A separately reviewed explicit finite continuation candidate may cite this narrow DNS observation. It proves neither TLS/HTTP reachability nor stable future DNS or complete APK integrity.',
    'remote_process_started_by_this_preparation': False,
    'HTTP_requests': 0, 'APK_downloads': 0, 'Android_commands': 0,
    'Main_actions': 0, 'installs': 0, 'production_ready': False,
})
files = [pin(path) for path in sorted(HERE.iterdir()) if path.is_file() and path.name != 'SOURCE_PINS.json']
pins_ref = write_new('SOURCE_PINS.json', {'schema': 'pocket4-zbj-dns-source-pins-v1',
    'files': files, 'total_bytes': sum(row['bytes'] for row in files),
    'actual_runtime_execution': False})
print(json.dumps({'request': request_ref, 'source': pin(source_path), 'plan': plan_ref,
                  'local_static_controls': controls_ref, 'source_pins': pins_ref}, indent=2))
