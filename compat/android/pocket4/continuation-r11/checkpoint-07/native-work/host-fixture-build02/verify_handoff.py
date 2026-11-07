#!/usr/bin/env python3
"""Offline request checks only. Never execute a build, factory, namespace or Android action."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
STAGE = HERE / 'actual-handoff-01'
OLD = HERE.parent / 'factory-host-fixture-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(argv, stdin=b''):
    result = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    return result


def main():
    pins_raw = (STAGE / 'STAGE_PINS.json').read_bytes()
    pins = json.loads(pins_raw)
    checks = []

    def record(name, passed, **details):
        checks.append({'name': name, 'pass': bool(passed), **details})
        if not passed:
            raise RuntimeError(name)

    record('all_generated_file_pins', all(
        len((STAGE / name).read_bytes()) == row['bytes'] and sha((STAGE / name).read_bytes()) == row['sha256']
        for name, row in pins['files'].items()))
    unchanged = ('client_control.cc', 'bionic_branch_view.cc', 'audit_worker_binary.py')
    record('actual_build01_client_and_audit_bytes_retained', all(
        (STAGE / name).read_bytes() == (OLD / name).read_bytes() for name in unchanged))
    for name in ('build_fixture.py', 'stage_and_build02.py'):
        result = run([sys.executable, '-I', str(STAGE / name)])
        record('default_plan_' + name, result.returncode == 0 and json.loads(result.stdout)['state'] == 'PLAN_ONLY',
               stdout=result.stdout.decode(), stderr_bytes=len(result.stderr))
    request = json.loads((STAGE / 'exact-process-start-request.json').read_bytes())
    packet_raw = request['stdin'].encode()
    wrapper = request['args'][2]
    result = run([sys.executable, '-I', '-c', wrapper], packet_raw)
    record('actual_request_packet_default_plan', result.returncode == 0 and
           json.loads(result.stdout)['state'] == 'PLAN_ONLY', stdout=result.stdout.decode())
    result = run([sys.executable, '-I', '-c', wrapper], packet_raw + b' ')
    record('whole_packet_mutation_rejected_before_entry', result.returncode != 0 and result.stdout == b'' and
           b'AssertionError' in result.stderr, returncode=result.returncode)
    original_tree = ast.parse((OLD / 'build_fixture.py').read_bytes())
    derived_tree = ast.parse((STAGE / 'build_fixture.py').read_bytes())
    def command_body(tree):
        return [ast.dump(node, include_attributes=False) for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == 'command']
    record('original_command_runner_retained', command_body(original_tree) == command_body(derived_tree))
    record('fixed_build_resources_and_paths', request['cpu_quota_percent'] == 100 and
           request['memory_max_bytes'] == 1073741824 and request['timeout_seconds'] == 600 and
           request['idempotency_key'] == 'pocket4-owned-factory-v2-host-build-02-20261104' and
           pins['remote_source'] == '/home/alex/work/pocket4-owned-factory-v2-host-source-02' and
           pins['remote_output'] == '/home/alex/work/pocket4-owned-factory-v2-host-build-02' and
           len(pins['expected_commands']) == 21 and pins['expected_actual_dependency_count'] == 291)
    with tempfile.TemporaryDirectory(prefix='host02-request-negative-') as temporary:
        root = Path(temporary)
        source = STAGE / 'actual-candidate05-source-report.json'
        gate = json.loads((STAGE / 'actual-candidate05-matched-gate.json').read_bytes())
        gate['actual_ancillary_cases'] = 33
        bad_raw = (json.dumps(gate) + '\n').encode()
        bad = root / 'incomplete-gate.json'
        bad.write_bytes(bad_raw)
        output = root / 'must-not-exist'
        result = run([sys.executable, '-I', str(HERE / 'make_host02_handoff.py'),
                      '--source-report', str(source), '--source-report-sha256', sha(source.read_bytes()),
                      '--gate-report', str(bad), '--gate-report-sha256', sha(bad_raw), '--output-dir', str(output)])
        record('self_consistent_but_incomplete_gate_rejected_before_output', result.returncode != 0 and
               not output.exists() and b'matched gate is incomplete' in result.stderr,
               returncode=result.returncode, fixture_only=True)
    record('generated_stage_remains_unchanged', (STAGE / 'STAGE_PINS.json').read_bytes() == pins_raw and all(
        sha((STAGE / name).read_bytes()) == row['sha256'] for name, row in pins['files'].items()))
    report = {'schema': 1, 'scope': 'local request generation and default/no-action entry validation only',
              'stage_pins_sha256': sha(pins_raw), 'checks': checks, 'pass': all(row['pass'] for row in checks),
              'actual_build02_executed': False, 'actual_dependency_count_measured_in_build02': False,
              'service_executed': False, 'Android_executed': False, 'Hepta_calls': 0,
              'negative_receipt_fixture_deleted': True, 'production_ready': False}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
