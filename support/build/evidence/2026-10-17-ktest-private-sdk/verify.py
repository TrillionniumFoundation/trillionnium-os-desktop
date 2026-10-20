#!/usr/bin/env python3
"""Offline source/count verification; never runs captured code or commands."""
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024 * 1024,
            'not a bounded regular file: ' + str(path))
    return path.read_bytes()


def obj(path):
    return json.loads(read(ROOT / path))


def main():
    entries = {}
    for row in read(ROOT / 'SHA256SUMS').decode().splitlines():
        require(re.fullmatch('[0-9a-f]{64}  .+', row) is not None, 'checksum syntax')
        digest, name = row.split('  ', 1)
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and str(path) == name
                and '__pycache__' not in path.parts and not name.endswith(('.pyc', '.pyo'))
                and name not in entries and name != 'SHA256SUMS', 'checksum path/duplicate')
        require(sha(read(ROOT / name)) == digest, 'checksum differs: ' + name)
        entries[name] = digest
    actual = {f.relative_to(ROOT).as_posix() for f in ROOT.rglob('*') if f.is_file()
              and f != ROOT / 'SHA256SUMS' and '__pycache__' not in f.relative_to(ROOT).parts
              and f.suffix not in {'.pyc', '.pyo'}}
    require(set(entries) == actual, 'file closure differs')
    summary = obj('summary.json')
    published = obj('raw/published-source.command.json')
    require(summary['source_commit'] == published['source_commit']
            == 'ff0d09a2c2e0cba1d528d11a06083f588989a9f3'
            and published['exit_code'] == 0 and len(published['files']) == 4, 'published source binding differs')
    for name, spec in summary['source_freeze'].items():
        data = read(ROOT / 'source-after' / name)
        require(len(data) == spec['bytes'] and sha(data) == spec['sha256'], 'candidate source differs')
        require(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                == published['files'][name]['git_blob'], 'published Git blob differs')
    old = read(ROOT / 'source-before/support__build__ktest__run.py').decode()
    new = read(ROOT / 'source-after/run.py').decode()
    require(sha(old.encode()) == summary['old_runner_sha256']
            == '41d23752430ad1a8893c8fc6e970cd1ea816d50be5b019ca11b0b27975ce2e56', 'old source differs')
    require(sha(new.encode()) == summary['new_runner_sha256']
            == '8bc8f712e7e1606d5744596bb390b1979b9d9559ca478dde5bba8c8670d1f59c', 'new source differs')
    def nodes(source):
        return {n.name:n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    a, b = nodes(old), nodes(new)
    proof = obj('raw/source-preservation.json')
    for name, record in proof['protected_top_level'].items():
        before, after = ast.get_source_segment(old, a[name]), ast.get_source_segment(new, b[name])
        require(before == after and ast.dump(a[name], include_attributes=False)
                == ast.dump(b[name], include_attributes=False)
                and sha(before.encode()) == record['sha256'], 'protected helper changed: ' + name)
    require(len(proof['protected_top_level']) == 8, 'protected helper denominator')
    marker = '    if "CARGO_ENCODED_RUSTFLAGS"'
    require(ast.get_source_segment(old, a['run_main']).split(marker, 1)[1]
            == ast.get_source_segment(new, b['run_main']).split(marker, 1)[1], 'existing lock/environment logic changed')
    require('osdk_install_root.mkdir(mode=0o700)' in new
            and 'command = [str(osdk), "osdk", "test"' in new, 'private SDK entry differs')
    test_sha = sha(read(ROOT / 'source-after/test_sdk_isolation_mock.py'))
    result = obj('raw/final700-results.json')
    names = None
    for label, row in zip(['ordinary', 'optimized'], result['checks']):
        require(row['exit_code'] == 0 and row['runner_sha256'] == summary['new_runner_sha256']
                and row['test_sha256'] == test_sha, 'final mock command/source differs')
        text = read(ROOT / ('raw/final700-' + label + '.stderr.log')).decode()
        cases = re.findall(r'^test_\S+ \(([^)]+)\) \.\.\. (.+)$', text, re.M)
        require(len(cases) == len(dict(cases)) == 11 and all(status == 'ok' for _, status in cases)
                and re.findall(r'^Ran (\d+) tests in .+$', text, re.M) == ['11']
                and re.search(r'^OK$', text, re.M) is not None, 'mock outcome/denominator differs')
        require(names is None or names == set(dict(cases)), 'mode test sets differ')
        names = set(dict(cases))
    control = obj('raw/old-runner-final-tests.command.json')
    require(control['exit_code'] == 1 and control['runner_sha256'] == summary['old_runner_sha256']
            and control['test_sha256'] == test_sha, 'old-source control binding differs')
    control_text = read(ROOT / 'raw/old-runner-final-tests.stderr.log').decode()
    require('Ran 11 tests in ' in control_text and 'FAILED (failures=7)' in control_text,
            'old-source control outcome differs')
    require(result['lifecycle_fixture_executed'] is False
            and result['native_kernel_tests_executed'] is False
            and result['subprocess_helpers_executed'] is False
            and result['global_sdk_written'] is False, 'scope claim differs')
    stopped = obj('execution-stop/report.json')
    require(stopped['specific_denied_tool_command'] is None
            and stopped['child_ktest_tool_calls_visible_to_parent'] == []
            and all(record['matches_fixed09aea_before_snapshot']
                    for record in stopped['current_owner_paths'].values()), 'prior failure scope differs')
    require(read(ROOT / 'execution-stop/git-status.stdout.log')
            == b'?? support/build/ktest/test_sdk_isolation.py\n', 'original status record differs')
    quarantine = obj('execution-stop/quarantine/quarantine.json')
    require(quarantine['content_executed'] is False and quarantine['author_known'] is False
            and quarantine['specific_rejected_action_known'] is False
            and quarantine['rename_preserved_identity_and_bytes'] is True
            and quarantine['git_untracked_exit_code'] == 1
            and sha(read(ROOT / 'execution-stop/quarantine/original-bytes.unexecuted'))
            == quarantine['sha256'] == 'ace2be2bc19503611f1bc87fd3b9a402c3f92d0ae3f514972d55a429babeae7e',
            'unexecuted quarantine provenance differs')
    print(json.dumps(dict(result='verified_offline', mocked_tests=[11, 11], old_control_failed=7,
                          protected_nodes_unchanged=8, lifecycle_executed=False, new_kernel_or_qemu=False)))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('ktest SDK evidence failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
