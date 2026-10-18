"""Validate archived host-only SDK isolation evidence without running fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path)

def require(condition, detail=None):
    if not condition:
        raise ValueError('evidence validation failed: ' + repr(detail))
args = parser.parse_args()
root = Path(__file__).resolve().parent
expected = {}
for line in (root / 'SHA256SUMS').read_text().splitlines():
    sha, name = line.split('  ', 1)
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts and (name not in expected), name)
    expected[name] = sha
actual = {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file() and path != root / 'SHA256SUMS'}
require(actual == set(expected), (actual - set(expected), set(expected) - actual))
for name, sha in expected.items():
    path = root / name
    require(not path.is_symlink(), name)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == sha, name)

def read(name):
    return json.loads((root / name).read_text())
manifest = read('manifest.json')
ready = read('host-validation/private-sdk-validation-ready-v2.json')
require(ready['status'] == 'ready_after_independent_v2_approval', 'check at verifier source line 31')
require(ready['source_sha256'] == manifest['source_sha256'], 'check at verifier source line 32')
for name, sha in ready['source_sha256'].items():
    archived = root / 'source/final' / name
    require(hashlib.sha256(archived.read_bytes()).hexdigest() == sha, name)
    if args.repo:
        data = subprocess.check_output(['git', '-C', str(args.repo), 'show', manifest['published_code_commit'] + ':' + name])
        require(hashlib.sha256(data).hexdigest() == sha, name)
for result in ready['results']:
    log = root / 'host-validation' / result['log']
    content = log.read_text()
    require(hashlib.sha256(log.read_bytes()).hexdigest() == result['sha256'], 'check at verifier source line 42')
    require(f"Ran {result['tests']} tests" in content and content.rstrip().endswith('OK'), 'check at verifier source line 43')
    require(result['observed_tool_returncode'] == 0 and result['passed'], 'check at verifier source line 44')
require([result['tests'] for result in ready['results']] == [40, 40, 9, 32], 'check at verifier source line 45')
optimized = read('host-validation/private-sdk-optimized-validation.json')
require(optimized['source_sha256'] == ready['source_sha256'], 'optimized source freeze')
require(optimized['command'][:3] == ['python3', '-I', '-O'], 'optimized interpreter flags')
require(optimized['tests'] == 40 and optimized['observed_tool_returncode'] == 0, 'optimized test outcome')
optimized_log = root / 'host-validation' / optimized['log']
require(hashlib.sha256(optimized_log.read_bytes()).hexdigest() == optimized['log_sha256'], 'optimized log bytes')
require('Ran 40 tests' in optimized_log.read_text() and optimized_log.read_text().rstrip().endswith('OK'), 'optimized log summary')
old = root / 'host-validation/private-sdk-validation-ready.json'
require(hashlib.sha256(old.read_bytes()).hexdigest() == ready['supersedes']['sha256'], 'check at verifier source line 47')
require(ready['supersedes']['status'] == 'superseded_not_final_acceptance', 'check at verifier source line 48')
make = read('make-before/results/report.json')
require(len(make['cases']) == 6, 'check at verifier source line 50')
for case in make['cases']:
    before = case['variant'] == 'original'
    require(case['returncode'] == (2 if before else 0), 'check at verifier source line 53')
    require(case['cargo_calls'][-1]['returncode'] == (73 if before else 0), 'check at verifier source line 54')
    require([call['operation'] for call in case['cargo_calls']] == (['osdk'] if before else ['install', 'osdk']), 'check at verifier source line 55')
lookup = read('real-cargo-lookup/cargo-lookup-results/report.json')
require([case['result']['selected'] for case in lookup['cases']] == ['GLOBAL', 'PRIVATE', 'GLOBAL'], 'check at verifier source line 57')
require(all((case['returncode'] == 0 for case in lookup['cases'])), 'check at verifier source line 58')
independent = read('independent-review/final-v2/final-review.json')
require(independent['review_outcome'] == 'approved_after_actual_Cargo_dotdot_counterexample_fixed', 'check at verifier source line 60')
require(independent['remaining_concrete_scoped_review_blocker'] is None, 'check at verifier source line 61')
require(independent['corrected_actual_wrapper_guard_checks'] == 8 and independent['corrected_actual_wrapper_guard_all_passed'], 'check at verifier source line 62')
require(independent['real_lookup_private_exit47_propagated_without_global_fallback'], 'check at verifier source line 63')
require(not independent['actual_SDK_installed'] and (not independent['Rust_compilation']) and (not independent['new_QEMU_execution']), 'check at verifier source line 64')
require({item['path']: item['sha256'] for item in independent['source_files']} == ready['source_sha256'], 'check at verifier source line 65')
review_lookup = read('independent-review/real-cargo-path-lookup/results.json')
counterexamples = [case for case in review_lookup['cases'] if not case['passed']]
require(len(counterexamples) == 1 and counterexamples[0]['name'] == 'absolute-dotdot', 'check at verifier source line 68')
require(counterexamples[0]['result']['selected'] == 'GLOBAL', 'check at verifier source line 69')
require(read('independent-review/default-home-dotdot-v2/report.json')['stdout'] == 'GLOBAL\n', 'check at verifier source line 70')
require(read('independent-review/slash-forms/results.json')['all_passed'], 'check at verifier source line 71')
profile = read('profile-path-inputs/profile-host-path-results/report.json')
require(profile['registry_incoming_metadata_equal'] and (not profile['registry_canonical_identity_equal']) and (not profile['local_consumer_metadata_equal']), 'check at verifier source line 73')
print(json.dumps({'evidence_integrity_passed': True, 'files': len(expected), 'source_code_commit': manifest['published_code_commit'], 'scope': 'host-only support isolation; no full SDK/Rust kernel/QEMU result in this phase', 'expected_failure_evidence_preserved': True, 'final_host_tests_passed': 161}, sort_keys=True))
