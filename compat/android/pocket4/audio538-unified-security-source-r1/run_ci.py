#!/usr/bin/env python3
"""Run four fresh security tests and compile both release tools from all1557 inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time
import traceback

SPEC = importlib.util.spec_from_file_location('audio538_verifier', Path(__file__).with_name('verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def destinations(recipe, target, report):
    recipe = Path(recipe).absolute()
    VERIFY.need(recipe.resolve() == recipe and recipe.is_dir() and not recipe.is_relative_to(VERIFY.HERE),
                'independent canonical producer directory required')
    report = VERIFY.fresh_destination(report, [VERIFY.HERE, recipe])
    logdir = VERIFY.fresh_destination(report.parent / (report.stem + '-logs'), [VERIFY.HERE, recipe, report])
    target = VERIFY.fresh_destination(target, [VERIFY.HERE, recipe, report, logdir])
    VERIFY.need(not report.is_relative_to(target) and not logdir.is_relative_to(target),
                'fresh Cargo target cannot contain reports or logs')
    return recipe, target, report, logdir


def release_binary(path):
    path = path.absolute()
    VERIFY.need(path.resolve() == path, 'release binary parent is aliased')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        VERIFY.need(stat.S_ISREG(before.st_mode) and before.st_mode & 0o111 and 0 < before.st_size <= 128 * 1024 * 1024,
                    'actual bounded executable release binary required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read()
        VERIFY.need(raw.startswith(b'\x7fELF') and len(raw) == before.st_size
                    and VERIFY.f9(before) == VERIFY.f9(os.fstat(fd)) == VERIFY.f9(path.lstat()),
                    'complete same-generation release ELF required')
        return {'path': str(path), **VERIFY.digest(raw), 'identity': VERIFY.f9(before)}
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--producer', required=True, type=Path)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    VERIFY.need(args.jobs in (1, 2), 'one or two Cargo jobs required')
    manifest = VERIFY.verify_capsule(args.inventory_sha256)
    recipe, target, report, logdir = destinations(args.producer, args.target, args.report)
    rows = VERIFY.catalog(manifest, 'head')
    before = VERIFY.source_snapshot(recipe, rows, VERIFY.HEAD_TREE)
    logdir.parent.mkdir(parents=True, exist_ok=True)
    logdir.mkdir(mode=0o700)
    target.mkdir(mode=0o700)
    env = dict(os.environ, CARGO_BUILD_JOBS=str(args.jobs), CARGO_TARGET_DIR=str(target),
               CARGO_INCREMENTAL='0', CARGO_TERM_COLOR='never', GIT_OPTIONAL_LOCKS='0')
    result = {'schema': 'audio538-fresh-CI-tests-and-release-tools-v1', 'state': 'RUNNING',
              'source_commit': VERIFY.HEAD_COMMIT, 'source_tree': VERIFY.HEAD_TREE, 'source_files': 1557,
              'actual_fresh_security_tests': 0, 'historical_tests_counted_as_fresh': 0,
              'historical_ELFs_reused': False, 'fresh_Cargo_target': str(target), 'commands': [], 'errors': [],
              'Android_builds': 0, 'APEX_installs': 0, 'official_regression_executed': False, 'runtime_qualified': False, 'production_ready': False,
              'started_ns': time.time_ns()}

    def run(name, argv, timeout=1800):
        outp, errp = logdir / (name + '.stdout'), logdir / (name + '.stderr')
        timed_out = False
        began = time.time_ns()
        with outp.open('xb') as out, errp.open('xb') as err:
            child = subprocess.Popen(argv, cwd=recipe, env=env, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=err, start_new_session=True)
            try:
                code = child.wait(timeout=timeout)
            except BaseException:
                timed_out = True
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    code = child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    code = child.wait(timeout=10)
        stdout, stderr = VERIFY.regular(outp), VERIFY.regular(errp)
        command = {'name': name, 'argv': argv, 'pid': child.pid, 'exit_code': code,
                   'actual_child_reaped': True, 'timed_out': timed_out, 'started_ns': began,
                   'finished_ns': time.time_ns(), 'stdout': {'path': str(outp), **VERIFY.digest(stdout)},
                   'stderr': {'path': str(errp), **VERIFY.digest(stderr)}}
        result['commands'].append(command)
        VERIFY.need(not timed_out and code == 0, 'actual CI command failed: ' + name)
        return command, stdout, stderr

    try:
        for name, package, selection, expected in (
            ('source-libueventd-test', 'droidloom-source', ['--lib'], VERIFY.SOURCE_TESTS),
            ('updater-libueventd-tests', 'droidloom-update', ['--bin','droidloom-update'], VERIFY.UPDATE_TESTS)):
            command, stdout, _ = run(name, ['cargo','test','--locked','-j',str(args.jobs),'-p',package,
                *selection,'libueventd538','--','--test-threads=1','--color','never'])
            command['actual_test_names'] = VERIFY.focused_test_log(stdout.decode(), expected)
            result['actual_fresh_security_tests'] += len(command['actual_test_names'])
        VERIFY.need(result['actual_fresh_security_tests'] == 4,'all four cross-crate exact tests required')
        run('release-both-tools', ['cargo', 'build', '--release', '--locked', '-j', str(args.jobs),
                                  '-p', 'droidloom-source', '-p', 'droidloom-update'])
        binaries = {name: release_binary(target / 'release' / name) for name in ('droidloom-source', 'droidloom-update')}
        _, updater_help, _ = run('security-release-entry', [binaries['droidloom-update']['path'], 'aac-security-build', '--help'], 60)
        _, source_help, _ = run('source-release-entry', [binaries['droidloom-source']['path'], '--help'], 60)
        VERIFY.need(b'aac-security-build' in updater_help and b'Usage:' in updater_help
                    and b'droidloom-source' in source_help and b'Usage:' in source_help,
                    'actual normal release command entries required')
        for entry in ('intentresolver-security-build','vendor-policy-bundle-build'):
            _, help_text, _ = run(entry+'-release-entry',[binaries['droidloom-update']['path'],entry,'--help'],60)
            VERIFY.need(entry.encode() in help_text and b'Usage:' in help_text,'retained current normal entry missing')
        VERIFY.need({name: release_binary(target / 'release' / name) for name in binaries} == binaries,
                    'fresh release tool identities changed after entry execution')
        result['fresh_release_tools'] = binaries
        VERIFY.need(VERIFY.source_snapshot(recipe, rows, VERIFY.HEAD_TREE) == before,
                    'all1557 original producer file and directory F9 must remain unchanged after CI')
        result['all1557_after_bytes_Git_blobs_modes_members_F9_verified'] = True
        result['state'] = 'FOUR_FRESH_SECURITY_TESTS_AND_BOTH_RELEASE_TOOLS_PASSED'
    except BaseException as error:
        result['state'] = 'FAILED'
        result['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        try:
            result['all1557_after_bytes_Git_blobs_modes_members_F9_verified'] = (
                VERIFY.source_snapshot(recipe, rows, VERIFY.HEAD_TREE) == before)
        except BaseException as check:
            result['all1557_after_bytes_Git_blobs_modes_members_F9_verified'] = False
            result['errors'].append({'producer_after_error': str(check)})
    result['finished_ns'] = time.time_ns()
    VERIFY.write_report(report, result, [VERIFY.HERE, recipe, target, logdir])
    print(json.dumps({'state': result['state'], 'actual_fresh_security_tests': result['actual_fresh_security_tests'],
                      'report': str(report), 'Android_builds': 0}, sort_keys=True))
    return 0 if result['state'] == 'FOUR_FRESH_SECURITY_TESTS_AND_BOTH_RELEASE_TOOLS_PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
