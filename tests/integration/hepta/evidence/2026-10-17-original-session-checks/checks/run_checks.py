"""Archive one bounded run of the final 17 Python source/gate checks."""

import json
import os
from pathlib import Path
import re
import sys
import traceback

sys.dont_write_bytecode = True
BASE = Path('/workspace/scratch/98f315e377b2')
WORK = Path(__file__).resolve().parent
HELPER = BASE / 'next-tools/r6-original-runtime/helper-v3/common.py'
sys.path.insert(0, str(HELPER.parent))
import common as c

c.DESKTOP = BASE / 'next-r6-runtime-new-03'
EXPECTED = '145e94c364243789b88c23b1292f9d4d9ca9a0e9'
EXPECTED_TREE = '98dee80a7ec855a84c777b350fed8ef675e31fc1'
TEST_PATHS = [
    'tests/integration/hepta/test_original_build_manifest.py',
    'tests/integration/hepta/test_original_process_guard.py',
    'tests/integration/hepta/test_original_session_receipts.py',
]


def main():
    c.require(set(path.name for path in WORK.iterdir()) == {'run_checks.py'},
              'this check directory must be new and contain only its wrapper')
    WORK.chmod(0o700)
    gate = c.load_gate()
    record = {
        'qualification': 'frozen_source_python_gate_checks',
        'status': 'running',
        'started_at_utc': c.now(),
        'expected_tests': 17,
        'test_scope': {
            'manifest_and_lock_contract': 5,
            'disposable_owned_linux_child_guard': 6,
            'synthetic_session_receipt_rejections': 6,
        },
        'original_agentd_runtime_attempted': False,
        'session_runtime_attempted': False,
        'shell_capture_attempted': False,
        'cargo_resolution_or_compilation_attempted': False,
        'objective_submission': False,
        'model_turn': False,
        'device_effect': False,
        'steps': [],
    }
    code = 1
    try:
        record['desktop'] = c.desktop_identity(gate, EXPECTED)
        c.require(record['desktop']['tree'] == EXPECTED_TREE, 'unexpected frozen source tree')
        record['original'] = gate.verify_source(c.ORIGINAL)
        record['test_sources'] = {path: gate.sha256(c.DESKTOP / path) for path in TEST_PATHS}
        record['wrapper_sha256'] = gate.sha256(Path(__file__))
        record['helper'] = {'path': str(HELPER), 'sha256': gate.sha256(HELPER)}
        environment = {
            'PATH': '/usr/bin:/bin',
            'LANG': 'C.UTF-8',
            'PYTHONDONTWRITEBYTECODE': '1',
            'HEPTA_ORIGINAL_SOURCE': str(c.ORIGINAL),
        }
        record['environment'] = environment
        log = WORK / 'python-gate-tests.log'
        c.checked_command(
            gate,
            [sys.executable, '-B', '-m', 'unittest', 'discover',
             '-s', 'tests/integration/hepta', '-p', 'test_original_*.py', '-v'],
            c.DESKTOP, environment, log, 90, record,
        )
        raw = log.read_text()
        passed = re.findall(r'^test_[^\n]+ \.\.\. ok$', raw, flags=re.MULTILINE)
        record['observed_tests_passed'] = len(passed)
        record['test_result_lines'] = passed
        c.require(len(passed) == 17 and re.search(r'^Ran 17 tests in [0-9.]+s$', raw, re.MULTILINE)
                  and raw.rstrip().endswith('\nOK'), 'the raw log must show exactly 17 passing tests')
        record['desktop_after'] = c.desktop_identity(gate, EXPECTED)
        record['original_after'] = gate.verify_source(c.ORIGINAL)
        record['test_sources_after'] = {path: gate.sha256(c.DESKTOP / path) for path in TEST_PATHS}
        c.require(record['desktop_after'] == record['desktop'], 'desktop source changed during checks')
        c.require(record['original_after'] == record['original'], 'original source changed during checks')
        c.require(record['test_sources_after'] == record['test_sources'], 'test inputs changed during checks')
        c.require(gate.sha256(HELPER) == record['helper']['sha256']
                  and gate.sha256(Path(__file__)) == record['wrapper_sha256'],
                  'executed helper or wrapper changed during checks')
        record['source_and_helper_unchanged'] = True
        record['status'] = 'passed'
        code = 0
    except BaseException as error:
        record['status'] = 'failed'
        record['error'] = str(error)
        record['traceback'] = traceback.format_exc()
    finally:
        record['exit_code'] = code
        record['ended_at_utc'] = c.now()
        c.save_new(WORK / 'receipt.json', record)
        print(json.dumps({'status': record['status'], 'exit_code': code,
                          'observed_tests_passed': record.get('observed_tests_passed'),
                          'receipt_path': str(WORK / 'receipt.json')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
