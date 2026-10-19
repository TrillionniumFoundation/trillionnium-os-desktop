#!/usr/bin/env python3
"""Bind completed final commands to source, exact test counts and native ELFs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import time

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r9_owned_runner', BASE / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def read_json(path):
    return json.loads(path.read_text())


def main():
    before = runner.source()
    final = read_json(BASE / 'test-03/source-before.json')
    assert before == final
    for label in ['test-03', 'clippy-02', 'fmt-02', 'build-01']:
        receipt = read_json(BASE / label / 'receipt.json')
        assert receipt['exit_code'] == 0 and receipt['source_equal'] is True
        assert read_json(BASE / label / 'source-before.json') == final
        assert read_json(BASE / label / 'source-after.json') == final

    counts = []
    binary = None
    log = (BASE / 'test-03/stdout-stderr.log').read_text()
    for line in log.splitlines():
        if line.lstrip().startswith('Running '):
            binary = line.strip()
        elif line.lstrip().startswith('Doc-tests '):
            binary = line.strip()
        match = re.fullmatch(
            r'test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; '
            r'(\d+) ignored; (\d+) measured; (\d+) filtered out; finished in (.+)', line)
        if match:
            assert binary is not None
            counts.append({'test_binary': binary, 'result': match[1],
                           **dict(zip(['passed', 'failed', 'ignored', 'measured', 'filtered_out'],
                                      map(int, match.groups()[1:6]))),
                           'duration_reported': match[7]})
            binary = None
    assert len(counts) == 9
    totals = {key: sum(row[key] for row in counts)
              for key in ['passed', 'failed', 'ignored', 'measured', 'filtered_out']}
    assert totals == {'passed': 137, 'failed': 0, 'ignored': 2,
                      'measured': 0, 'filtered_out': 0}
    runner.write_json(BASE / 'test-03/test-counts.json', {
        'raw_log_sha256': hashlib.sha256(log.encode()).hexdigest(),
        'binaries': counts, 'totals': totals,
        'ignored_scope': 'Two real-host-font tests require an explicitly selected font; not executed in this R9 gate.'})

    bins = {}
    for name in ['trill-shell', 'trill-session', 'trill-ctl', 'trill-app-window']:
        path = runner.TARGET / 'debug' / name
        data = path.read_bytes()
        assert data[:6] == b'\x7fELF\x02\x01'
        assert struct.unpack('<H', data[18:20])[0] == 62
        bins[name] = {'path': str(path), 'sha256': runner.digest(data),
                      'bytes': len(data), 'elf_class': 'ELF64',
                      'elf_data': 'little-endian', 'elf_machine': 'x86-64',
                      'elf_header_64_hex': data[:64].hex()}
    after = runner.source()
    assert before == after
    runner.write_json(BASE / 'build-01/production-binaries.json', {
        'sampled_unix': time.time(),
        'collector_sha256': runner.digest(Path(__file__).read_bytes()),
        'build_receipt_sha256': runner.digest((BASE / 'build-01/receipt.json').read_bytes()),
        'build_launch_sha256': runner.digest((BASE / 'build-01/launch.json').read_bytes()),
        'source_before': before, 'source_after': after, 'source_equal': True,
        'binaries': bins,
        'scope': 'Four production ELF outputs from the completed locked workspace bins build; no native window, original Agentd or device execution.'})

    test_receipt = read_json(BASE / 'test-03/receipt.json')
    assert len(test_receipt['shell_executables']) == 1
    test_path, identity = next(iter(test_receipt['shell_executables'].items()))
    data = Path(test_path).read_bytes()
    assert runner.digest(data) == identity['sha256'] and len(data) == identity['bytes']
    retained = BASE / 'test-03/executed-test-elf'
    with retained.open('xb') as stream:
        stream.write(data)
    runner.write_json(BASE / 'test-03/preserved-test-elf.json', {
        'executed_path': test_path, 'preserved_path': str(retained),
        **identity, 'source_sha256': final['canonical_sources_sha256'],
        'scope': 'Actual final Shell unit-test ELF. Byte copy is retained locally and excluded from the published evidence archive.'})

    names = ['ui/core/src/conversation.rs', 'ui/core/src/hepta.rs',
             'ui/session/src/hepta.rs', 'ui/session/tests/hepta_run.rs',
             'ui/shell/src/hepta_panel.rs', 'ui/shell/src/main.rs',
             'ui/shell/OBSERVATION_FRESHNESS.md', 'support/ui/HEPTA_OBSERVER.md']
    files = {}
    for name in names:
        data = (runner.ROOT / name).read_bytes()
        files[name] = {'sha256': runner.digest(data), 'bytes': len(data)}
    patch = subprocess.check_output(['git', 'diff', '--', *names], cwd=runner.ROOT)
    (BASE / 'final-source.patch').write_bytes(patch)
    runner.write_json(BASE / 'final-source.json', {
        'head_at_execution': final['head'],
        'red_committed_after_execution': '00796f6f6e10027e12b83d37d9ab4b8ab913f72e',
        'compiled_closure_sha256': final['canonical_sources_sha256'],
        'compiled_closure_record': 'test-03/source-before.json',
        'changed_files': files, 'final_patch_sha256': runner.digest(patch),
        'final_patch_bytes': len(patch),
        'source_equal_at_final_inventory': runner.source() == final,
        'scope': 'Execution is bound to recorded HEAD plus the exact working source patch and per-file hashes. A later integration commit is not the executed HEAD.'})
    print(json.dumps({'totals': totals, 'binaries': bins,
                      'compiled_closure_sha256': final['canonical_sources_sha256']}, sort_keys=True))


if __name__ == '__main__':
    main()
