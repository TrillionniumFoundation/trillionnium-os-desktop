#!/usr/bin/env python3
"""Compile the exact current ordinary test catalog in a separate Cargo target."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import traceback


def need(value, message):
    if not value:
        raise RuntimeError(message)


def fresh_destination(path, protected):
    path = path.absolute()
    need(path.resolve() == path, 'output path or parent is an alias: ' + str(path))
    need(not os.path.lexists(path), 'output must be absent: ' + str(path))
    for root in protected:
        root = root.resolve()
        need(path != root and root not in path.parents, 'output is inside a protected input: ' + str(path))
    return path


def test_terminal(text, expected):
    expected = set(expected)
    records = []
    summaries = []
    running = []
    for line in text.splitlines():
        if line.startswith('test result:'):
            match = re.fullmatch(r'test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out; finished in .+', line)
            need(match is not None, 'malformed Rust test summary')
            summaries.append(match.groups())
        elif line.startswith('test '):
            match = re.fullmatch(r'test (\S+) \.\.\. (ok|FAILED|ignored(?:,.*)?)', line)
            need(match is not None, 'malformed Rust test terminal')
            records.append(match.groups())
        elif line.startswith('running '):
            match = re.fullmatch(r'running (\d+) tests?', line)
            need(match is not None, 'malformed Rust test count')
            running.append(int(match.group(1)))
    need(len(records) == len(expected) and len({n for n, _ in records}) == len(records), 'test identities are missing, extra, or repeated')
    need({n for n, _ in records} == expected and all(status == 'ok' for _, status in records), 'test identity or status differs from exact catalog')
    need(running == [len(expected)] and len(summaries) == 1, 'exactly one complete Rust test run is required')
    status, passed, failed, ignored, measured, filtered = summaries[0]
    need(status == 'ok' and (int(passed), int(failed), int(ignored), int(measured)) == (len(expected), 0, 0, 0), 'Rust test summary contradicts complete passing identities')
    return {'passed': int(passed), 'failed': 0, 'ignored': 0, 'measured': 0, 'filtered': int(filtered), 'names': sorted(expected)}


def source_snapshot(recipe, rows):
    need(len(rows) == len({x['path'] for x in rows}), 'duplicate source manifest path')
    actual = set()
    for root, directories, files in os.walk(recipe, followlinks=False):
        relative_root = Path(root).relative_to(recipe)
        if not relative_root.parts and '.git' in directories:
            directories.remove('.git')
        for name in list(directories):
            p = Path(root) / name
            if p.is_symlink():
                actual.add(str(p.relative_to(recipe)))
                directories.remove(name)
        actual.update(str((Path(root) / name).relative_to(recipe)) for name in files)
    need(actual == {x['path'] for x in rows}, 'complete producer file membership changed')
    result = []
    for row in rows:
        relative = Path(row['path'])
        need(not relative.is_absolute() and '..' not in relative.parts and '.git' not in relative.parts, 'invalid producer path')
        p = recipe / relative
        need(p.parent.resolve() == p.parent, 'producer parent is an alias')
        s = p.lstat()
        need(s.st_nlink == 1, 'producer hardlink is not independent')
        if row['mode'] == '120000':
            need(stat.S_ISLNK(s.st_mode), 'producer symlink kind changed')
            raw = os.readlink(p).encode()
        else:
            need(row['mode'] in ('100644', '100755') and stat.S_ISREG(s.st_mode), 'producer regular file kind changed')
            need(stat.S_IMODE(s.st_mode) == (int(row['mode'], 8) & 0o777), 'producer executable mode changed')
            raw = p.read_bytes()
        need(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'producer bytes changed: ' + row['path'])
        need(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == row['git_blob'], 'producer Git blob changed')
        after = p.lstat()
        identity = tuple(getattr(s, k) for k in ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'])
        need(identity == tuple(getattr(after, k) for k in ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns']), 'producer changed during verification')
        result.append((row['path'], identity, row['sha256']))
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--recipe', type=Path, required=True)
    p.add_argument('--capsule', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--target', type=Path)
    p.add_argument('--jobs', type=int, default=2)
    a = p.parse_args()
    need(1 <= a.jobs <= 4, 'bounded Cargo parallelism required')
    recipe, capsule = a.recipe.resolve(), a.capsule.resolve()
    need(recipe.is_dir() and capsule.is_dir() and recipe != capsule, 'independent existing recipe and capsule required')
    report = fresh_destination(a.report, [recipe, capsule])
    logdir = fresh_destination(report.parent / (report.stem + '-logs'), [recipe, capsule, report])
    target = fresh_destination(a.target or report.parent / (report.stem + '-target'), [recipe, capsule, report, logdir])
    need(target not in report.parents and target not in logdir.parents, 'target cannot contain reports')
    expected = json.loads((capsule / 'test-catalog.json').read_bytes())
    need(all(isinstance(expected[k], list) and len(expected[k]) == len(set(expected[k])) for k in ['source', 'update']), 'unique exact test catalogs required')
    need(expected['total'] == len(expected['source']) + len(expected['update']), 'complete test total differs')
    rows = json.loads((capsule / 'head-files.json').read_bytes())
    manifest = json.loads((capsule / 'manifest.json').read_bytes())
    need(len(rows) == manifest['replay_contract']['head_files'], 'complete producer inventory required')
    filters = [('audio-tests', 'audio_'), ('vendor-tests', 'vendor_policy'), ('production-tests', 'production_'),
               ('permissions-tests', 'projection_v2_'), ('recovery-tests', 'source_recovery')]
    specs = [('source', 'source-tests', ['-p', 'droidloom-source', '--lib'], set(expected['source']))]
    specs += [('update', name, ['-p', 'droidloom-update', '--bin', 'droidloom-update', flt], {n for n in expected['update'] if flt in n}) for name, flt in filters]
    need(set.union(*(x[3] for x in specs if x[0] == 'update')) == set(expected['update']), 'filters do not cover exact current updater catalog')
    need(all(x[3] for x in specs), 'empty ordinary test filter')
    report.parent.mkdir(parents=True, exist_ok=True)
    logdir.mkdir()
    target.mkdir()
    env = dict(os.environ, CARGO_BUILD_JOBS=str(a.jobs), CARGO_TARGET_DIR=str(target), GIT_OPTIONAL_LOCKS='0', CARGO_TERM_COLOR='never')
    result = {'schema': 'audio-current-CI-ordinary-tests-v2', 'state': 'RUNNING', 'commands': [], 'errors': [],
              'Android_starts': 0, 'runtime_qualified': False, 'production_ready': False, 'historical_ELFs_reused': False,
              'source_files': len(rows), 'expected_distinct_tests': expected['total'], 'cargo_target': str(target)}
    before = None
    names = {'source': set(), 'update': set()}
    try:
        before = source_snapshot(recipe, rows)
        for group, name, arguments, wanted in specs:
            argv = ['cargo', 'test', '--locked', '-j', str(a.jobs), *arguments, '--', '--test-threads=1', '--color', 'never']
            outp, errp = logdir / (name + '.stdout'), logdir / (name + '.stderr')
            timed_out = False
            with outp.open('xb') as out, errp.open('xb') as err:
                child = subprocess.Popen(argv, cwd=recipe, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
                try:
                    code = child.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        code = child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        code = child.wait(timeout=10)
            stdout, stderr = outp.read_bytes(), errp.read_bytes()
            command = {'name': name, 'argv': argv, 'exit_code': code, 'timed_out': timed_out,
                       'stdout': str(outp), 'stderr': str(errp), 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                       'stderr_sha256': hashlib.sha256(stderr).hexdigest()}
            result['commands'].append(command)
            need(not timed_out and code == 0, 'ordinary test command failed: ' + name)
            terminal = test_terminal(stdout.decode(), wanted)
            command['actual_terminal'] = terminal
            names[group].update(terminal['names'])
        need(all(names[k] == set(expected[k]) for k in names), 'actual ordinary test identities differ from complete catalog')
        need(source_snapshot(recipe, rows) == before, 'producer source identities changed during ordinary tests')
        result['source_preserved'] = True
        result['state'] = 'ALL_CURRENT_COMPILED_TESTS_PASSED'
    except BaseException as error:
        result['state'] = 'FAILED'
        result['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        try:
            result['source_preserved'] = before is not None and source_snapshot(recipe, rows) == before
        except BaseException as check:
            result['source_preserved'] = False
            result['errors'].append({'source_after_error': str(check)})
    result['actual_distinct_tests'] = sum(map(len, names.values()))
    result['source_tests'], result['updater_tests'] = sorted(names['source']), sorted(names['update'])
    result['test_executions_including_overlap'] = sum(len(c.get('actual_terminal', {}).get('names', [])) for c in result['commands'])
    result['finished_ns'] = time.time_ns()
    with report.open('x') as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write('\n')
    print(json.dumps({'state': result['state'], 'actual_distinct_tests': result['actual_distinct_tests'], 'report': str(report), 'Android_starts': 0}))
    return 0 if result['state'] == 'ALL_CURRENT_COMPILED_TESTS_PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
