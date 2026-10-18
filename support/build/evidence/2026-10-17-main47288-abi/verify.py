#!/usr/bin/env python3
"""Offline integrity and denominator verification; does not rerun acceptance."""
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

HERE = Path(__file__).resolve().parent
COMMIT = '47288c4465720d125658b392efc655b333c90868'
TREE = '58c26d033df0b8b1476afa9aa0de185f46a03bd7'
NIGHTLY = 'nightly-2026-07-21'
RUSTC = '87e5904f5eb6398af6b22eac2802c78934260c48'
RAW_SUM = '6bc20d143502734c341b517212eb542e01a1087ad2bf6e492226a57bce9c131c'
CHECKS = ('golden_hos2', 'golden_edges', 'golden_transport', 'python_discovery',
          'python', 'python_optimized', 'python_mutations', 'rust_discovery',
          'rust', 'rustfmt', 'clippy', 'bare_no_std', 'compiled_mutations')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, limit=4 * 1024 * 1024):
    require(path.is_file() and not path.is_symlink(), 'nonregular or linked file: ' + str(path))
    require(path.stat().st_size <= limit, 'oversize file: ' + str(path))
    data = path.read_bytes()
    require(len(data) <= limit, 'file grew during read')
    return data


def table(directory):
    entries = {}
    for line in read(directory / 'SHA256SUMS').decode().splitlines():
        require(re.fullmatch(r'[0-9a-f]{64}  .+', line) is not None, 'bad checksum line')
        digest, name = line.split('  ', 1)
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and str(path) == name,
                'unsafe checksum path')
        require('__pycache__' not in path.parts and not name.endswith(('.pyc', '.pyo')),
                'Python cache must not be an evidence input')
        require(name not in entries and name != 'SHA256SUMS', 'duplicate checksum entry')
        entries[name] = digest
        require(sha(read(directory / name)) == digest, 'checksum differs: ' + name)
    observed = set()
    for child in directory.rglob('*'):
        if '__pycache__' in child.relative_to(directory).parts or child.suffix in {'.pyc', '.pyo'}:
            continue
        require(not child.is_symlink(), 'linked bundle entry')
        if child.is_file() and child != directory / 'SHA256SUMS':
            observed.add(child.relative_to(directory).as_posix())
    require(set(entries) == observed, 'checksum closure differs')
    return entries


def obj(name):
    return json.loads(read(HERE / 'raw' / name))


def success(command):
    require(command['returncode'] == 0 and command['timed_out'] is False,
            'recorded command did not succeed')


def rust_cases(command, expected, failures=0):
    output = command['stdout']
    lines = re.findall(r'^test (.*?) \.\.\. (ok|FAILED|ignored)$', output, re.M)
    require(len(lines) == len(dict(lines)) == len(expected) and set(dict(lines)) == set(expected),
            'Rust executed test names/denominator differ')
    require(sum(status == 'FAILED' for _, status in lines) == failures
            and all(status in {'ok', 'FAILED'} for _, status in lines), 'Rust outcomes differ')
    totals = re.findall(r'^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; '
                        r'(\d+) ignored; (\d+) measured; (\d+) filtered out;', output, re.M)
    require(bool(totals), 'Rust result summaries absent')
    counts = [sum(int(row[i]) for row in totals) for i in range(1, 6)]
    require(counts == [len(expected) - failures, failures, 0, 0, 0], 'Rust summary counts differ')
    return dict(lines)


def python_cases(command, expected):
    text = command['stdout'] + command['stderr']
    lines = re.findall(r'^\S+ \(([^)]+)\) \.\.\. (.+)$', text, re.M)
    require(len(lines) == len(dict(lines)) == len(expected) and set(dict(lines)) == set(expected),
            'Python executed test names/denominator differ')
    require(all(outcome == 'ok' for _, outcome in lines), 'Python skipped/failed test')
    require(re.findall(r'^Ran (\d+) tests? in .+$', text, re.M) == [str(len(expected))]
            and re.search(r'^OK$', text, re.M) is not None, 'Python summary differs')


def main():
    table(HERE)
    require(sha(read(HERE / 'raw' / 'SHA256SUMS')) == RAW_SUM, 'original raw manifest changed')
    require(len(table(HERE / 'raw')) == 36, 'original 37-file bundle closure differs')
    report, mutations = obj('acceptance-report.json'), obj('acceptance-mutations.json')
    summary, controller = obj('summary.json'), obj('controller-result.json')
    require(controller['source_commit'] == summary['source_commit'] == COMMIT
            and controller['exit_code'] == 0 and controller['new_kernel_or_guest_test'] is False,
            'controller source/scope/exit differs')
    require(summary['source_tree'] == TREE and report['toolchain'] == NIGHTLY
            and report['toolchain_override'] is False, 'tree/toolchain differs')
    require(report['success'] is True and report['errors'] == [] and report['not_executed'] == []
            and report['original_inputs_unchanged'] is True and report['readme_bytes'] == 0,
            'acceptance incomplete or source changed')
    require(report['input_sha256'] == report['original_input_sha256_after'], 'post-source hashes differ')
    require(obj('acceptance.stdout.log')['success'] is True
            and obj('acceptance.stdout.log')['errors'] == []
            and obj('acceptance.stdout.log')['not_executed'] == [], 'outer acceptance stdout differs')
    records = controller['records']
    expected_labels = ['source-head', 'source-status-before', 'source-trees', 'changed-input-blobs',
                       'rustc-identity', 'cargo-identity', 'acceptance', 'source-status-after',
                       'source-head-after']
    require([row['label'] for row in records] == expected_labels, 'controller command closure differs')
    for row in records:
        require(row['exit_code'] == 0 and obj(row['label'] + '.command.json') == row,
                'controller command receipt differs')
        require(bool(row['command']) and row['cwd'] == report['repo_root'], 'controller argv/cwd differs')
        require(datetime.datetime.fromisoformat(row['start_utc'])
                <= datetime.datetime.fromisoformat(row['finish_utc']), 'controller UTC order differs')
    for label in ['source-head', 'source-head-after']:
        require(read(HERE / 'raw' / (label + '.stdout.log')).decode().strip() == COMMIT,
                'actual Git HEAD differs')
    for label in ['source-status-before', 'source-status-after']:
        require(read(HERE / 'raw' / (label + '.stdout.log')) == b'', 'actual source status is dirty')
    require(read(HERE / 'raw' / 'source-trees.stdout.log').decode().splitlines()[0] == TREE,
            'actual Git tree differs')
    require(report['executables']['rustc']['version']['stdout']
            == read(HERE / 'raw' / 'rustc-identity.stdout.log').decode(), 'Rust full versions differ')
    require(report['executables']['cargo']['version']['stdout']
            == read(HERE / 'raw' / 'cargo-identity.stdout.log').decode(), 'Cargo full versions differ')
    require('commit-hash: ' + RUSTC + '\n' in report['executables']['rustc']['version']['stdout']
            and 'release: 1.99.0-nightly\n' in report['executables']['rustc']['version']['stdout']
            and 'commit-hash: 3efb1f477e99b42974b982d939fd100303cdf7db\n'
            in report['executables']['cargo']['version']['stdout'], 'fixed compiler/Cargo identity differs')
    for tool, info in report['executables'].items():
        success(info['version'])
        require(NIGHTLY in info['path'] and re.fullmatch('[0-9a-f]{64}', info['sha256']) is not None,
                'unidentified fixed executable: ' + tool)
    require(report['environment']['RUSTUP_TOOLCHAIN'] == NIGHTLY
            and report['environment']['CARGO_NET_OFFLINE'] == 'true'
            and report['environment']['RUSTC_WRAPPER'] == ''
            and report['environment']['RUSTC_WORKSPACE_WRAPPER'] == '', 'compiler environment differs')

    compressed = read(HERE / 'raw' / 'consumed-source.tar.gz')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        source_tar = stream.read(4 * 1024 * 1024 + 1)
    require(len(source_tar) <= 4 * 1024 * 1024, 'source archive exceeds bound')
    members, index = {}, obj('consumed-source.members.json')
    with tarfile.open(fileobj=io.BytesIO(source_tar), mode='r:') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            require(member.isfile() and not path.is_absolute() and '..' not in path.parts
                    and str(path) == member.name and member.name not in members, 'unsafe source member')
            require(member.name in index and member.size == index[member.name]['bytes'] <= 1024 * 1024,
                    'source member size/name differs')
            data = archive.extractfile(member).read(member.size + 1)
            require(len(data) == member.size and sha(data) == index[member.name]['sha256'],
                    'source member content differs')
            members[member.name] = data
    require(set(members) == set(index) and len(members) == 29, 'source member closure differs')
    require(set(members) == set(report['input_sha256']) | {'libs/os-abi/Cargo.lock'},
            'consumed source closure differs from acceptance')
    for name, expected in report['input_sha256'].items():
        require(sha(members[name]) == expected, 'acceptance source hash differs: ' + name)
    blobs = {'libs/os-abi/src/lib.rs': '356c76178a0b3a8a2a9babdf186b88977ec4d60c',
             'libs/os-abi/tests/response_snapshot.rs': '105fd38a808561ff9628aa9b2eb3fdc8c2360bb7',
             'tests/abi/run_acceptance.py': 'cb3cf715142d192dd0206fbdce0103c77fbbf372'}
    ls_tree = read(HERE / 'raw' / 'changed-input-blobs.stdout.log').decode()
    for name, expected in blobs.items():
        data = members[name]
        require(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == expected
                and '100644 blob ' + expected + '\t' + name + '\n' in ls_tree,
                'source Git blob differs: ' + name)

    checks = {entry['name']: entry for entry in report['checks']}
    require(tuple(checks) == CHECKS and len(report['checks']) == len(CHECKS) == 13,
            '13 required checks differ')
    for name, check in checks.items():
        success(check)
        require(check['passed'] is True and check['cwd'] == report['snapshot_root']
                and check['argv'], 'check source/argv/pass differs: ' + name)
    expected_python = report['discovered_python_tests']
    require(len(expected_python) == len(set(expected_python)) == 52
            and json.loads(checks['python_discovery']['stdout']) == expected_python, 'Python discovery differs')
    for name in ['python', 'python_optimized']:
        python_cases(checks[name], expected_python)
    python_cases(checks['python_mutations'], [x for x in expected_python if x.startswith('test_mutations.')])
    require(len([x for x in expected_python if x.startswith('test_mutations.')]) == 9,
            'Python mutation denominator differs')
    expected_rust = report['discovered_rust_tests']
    require(len(expected_rust) == len(set(expected_rust)) == 75
            and re.findall(r'^(.+): test$', checks['rust_discovery']['stdout'], re.M) == expected_rust,
            'Rust discovery differs')
    rust_cases(checks['rust'], expected_rust)
    require(sum(' - ' in name for name in expected_rust) == 1, 'Rust doctest denominator differs')
    require([checks[name]['vectors'] for name in CHECKS[:3]] == [12, 24, 1], 'golden vector counts differ')
    require('--target' in checks['bare_no_std']['argv']
            and 'x86_64-unknown-none' in checks['bare_no_std']['argv']
            and checks['clippy']['argv'][-3:] == ['--', '-D', 'warnings'], 'no_std/strict lint argv differs')

    require(mutations['success'] is True and mutations['errors'] == []
            and mutations['requested_toolchain'] == NIGHTLY
            and mutations['expected_mutants'] == mutations['mutants_killed'] == len(mutations['mutants']) == 12,
            'compiled mutation completion differs')
    require(json.loads(checks['compiled_mutations']['stdout']) == mutations,
            'embedded and standalone mutation raw reports differ')
    for name, expected in mutations['input_sha256'].items():
        require(sha(members['libs/os-abi/' + name]) == expected, 'mutation original source differs: ' + name)
    reference = mutations['reference_toolchain_identity']
    def compiler_identity(identity):
        require(identity['valid'] is True
                and identity['effective_environment']['RUSTUP_TOOLCHAIN'] == NIGHTLY
                and identity['rustc']['stdout'] == reference['rustc']['stdout']
                and identity['cargo']['stdout'] == reference['cargo']['stdout'], 'mutant compiler identity differs')
        success(identity['rustc']); success(identity['cargo'])
    compiler_identity(reference)
    require(reference['rustc']['stdout'] == report['executables']['rustc']['version']['stdout'],
            'mutation compiler differs from acceptance')
    require(reference['cargo']['stdout']
            == report['executables']['cargo']['version']['stdout'].splitlines()[0] + '\n',
            'mutation Cargo differs from acceptance')
    failures = 0
    for name, total in [('baseline', 8), ('baseline_semantic_edges', 12), ('baseline_profile_boundaries', 7)]:
        case = mutations[name]
        require(case['passed'] is True and case['compiled'] is True and case['expected_tests'] == total,
                'mutation baseline differs')
        success(case['compilation']); success(case['test'])
        require(len(case['tests']['cases']) == total
                and set(case['required_tests']) <= set(case['tests']['cases']), 'baseline oracle subset differs')
        rust_cases(case['test'], list(case['tests']['cases']))
        compiler_identity(case['toolchain_identity']); compiler_identity(case['test_toolchain_identity'])
    for case in mutations['mutants']:
        require(case['killed'] is True and case['compiled'] is True and case['expected_test_failed'] is True
                and case['toolchain_matches_reference'] is True, 'mutant kill flags differ')
        success(case['compilation'])
        require(case['test']['returncode'] == 101 and case['test']['timed_out'] is False, 'mutant failure differs')
        compiler_identity(case['toolchain_identity']); compiler_identity(case['test_toolchain_identity'])
        failed = case['tests']['failed']; failures += failed
        require(len(case['tests']['cases']) == case['expected_tests']
                == mutations['expected_tests_by_suite'][case['suite']]
                and set(case['required_tests']) <= set(case['tests']['cases']), 'mutant suite denominator differs')
        outcomes = rust_cases(case['test'], list(case['tests']['cases']), failed)
        require(outcomes[case['expected_failure']] == 'FAILED', 'required mutant oracle was not killed')
    require(failures == summary['expected_negative_assertions'] == 17, 'expected negative assertions differ')
    require(all(summary[key] is True for key in ['original_inputs_unchanged', 'source_status_before_clean',
                                                'source_status_after_clean']), 'summary source custody differs')
    print(json.dumps(dict(result='verified_offline', source_commit=COMMIT, raw_files=37,
                          consumed_source_files=29, checks=13, python=[52, 52], rust=75,
                          mutants=12, expected_negative_assertions=17, new_kernel_or_guest_test=False)))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print('ABI evidence verification failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
