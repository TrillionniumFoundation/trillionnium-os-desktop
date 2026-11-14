#!/usr/bin/env python3
"""Run nine fresh runtime input controls and compile both release tools from all430 inputs."""
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

SPEC = importlib.util.spec_from_file_location('runtime_d6_verifier', Path(__file__).with_name('verify.py'))
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


def cargo_executable(path, target, name):
    path, target = path.absolute(), target.absolute()
    VERIFY.need(path.resolve() == path and target.resolve() == target and path.is_relative_to(target),
                'actual fresh Cargo executable must remain inside the private target without aliases')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        VERIFY.need(stat.S_ISREG(before.st_mode) and before.st_mode & 0o111 and before.st_nlink in (1, 2)
                    and 0 < before.st_size <= 128 * 1024 * 1024, 'bounded actual Cargo executable required')
        profile = target / ('release' if path.is_relative_to(target / 'release') else 'debug')
        candidates = [profile / name] + list((profile / 'deps').glob(name.replace('-', '_') + '-*'))
        VERIFY.need(len(candidates) <= 128, 'finite private Cargo link set required')
        aliases = [p for p in candidates if os.path.lexists(p) and p.lstat().st_dev == before.st_dev and p.lstat().st_ino == before.st_ino]
        VERIFY.need(len(set(aliases)) == before.st_nlink and path in aliases, 'all Cargo hardlinks must be inside the current private target')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read()
        VERIFY.need(raw.startswith(b'\x7fELF') and len(raw) == before.st_size
                    and VERIFY.f9(before) == VERIFY.f9(os.fstat(fd)) == VERIFY.f9(path.lstat()),
                    'complete stable actual Cargo ELF required')
        for alias in aliases:
            VERIFY.need(alias.resolve() == alias and VERIFY.f9(alias.lstat()) == VERIFY.f9(before), 'Cargo alias changed')
        return {'path': str(path), **VERIFY.digest(raw), 'identity': VERIFY.f9(before),
                'bounded_private_Cargo_aliases': sorted(str(p) for p in aliases)}
    finally:
        os.close(fd)


def select_artifact(raw, recipe, target, name, kind, test):
    rows = VERIFY.successful_cargo_stream(raw)
    matches = [row for row in rows if row.get('reason') == 'compiler-artifact' and row.get('executable')
               and row['target']['name'] == name and row['target']['kind'] == [kind] and row['profile']['test'] is test]
    VERIFY.need(len(matches) == 1 and matches[0]['fresh'] is False, 'one freshly compiled artifact from this Cargo invocation required')
    row = matches[0]
    relative = 'lib.rs' if kind == 'lib' else ('main.rs' if name == 'droidloom-supervisor' else 'bin/droidloomd.rs')
    VERIFY.need(row['manifest_path'] == str(recipe / 'runtime/droidloom-supervisor/Cargo.toml')
                and row['target']['src_path'] == str(recipe / 'runtime/droidloom-supervisor/src' / relative),
                'actual Cargo artifact must come from this complete430 producer')
    path = Path(row['executable'])
    profile = target / ('debug' if test else 'release')
    VERIFY.need(path.is_relative_to(profile) and path.is_absolute(), 'actual Cargo artifact escaped its fresh profile')
    if not test:
        VERIFY.need(path == profile / name, 'exact current normal release executable required')
    executable = cargo_executable(path, target, 'droidloom-supervisor' if kind == 'lib' else name)
    return {'Cargo_message': row, 'ELF': executable}


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
    result = {'schema': 'runtime-d6-fresh-CI-nine-controls-and-two-release-tools-v1', 'state': 'RUNNING',
              'source_commit': VERIFY.HEAD_COMMIT, 'source_tree': VERIFY.HEAD_TREE, 'source_files': 430,
              'actual_fresh_runtime_input_tests': 0, 'historical_tests_counted_as_fresh': 0,
              'historical_ELFs_reused': False, 'fresh_Cargo_target': str(target), 'commands': [], 'errors': [],
              'Android_builds': 0, 'Android_starts': 0, 'host_policy_writes': 0,
              'ExecutionAdmission_constructible': False, 'actual_SELinux_transition_qualified': False,
              'runtime_qualified': False, 'production_ready': False, 'started_ns': time.time_ns()}

    def run(name, argv, timeout=1800):
        outp, errp = logdir / (name + '.stdout'), logdir / (name + '.stderr')
        timed_out, began = False, time.time_ns()
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
        compile_command, stdout, _ = run('compile-fresh-library-harness', ['cargo', 'test', '--locked', '-j', str(args.jobs),
            '-p', 'droidloom-supervisor', '--lib', '--no-run', '--message-format=json'])
        harness = select_artifact(stdout, recipe, target, 'droidloom_supervisor', 'lib', True)
        result['fresh_test_harness'] = harness
        command, stdout, _ = run('nine-runtime-input-controls', [harness['ELF']['path'],
            'production_mounts::runtime_assets::tests::', '--test-threads=1', '--color', 'never'])
        command['actual_test_names'] = VERIFY.focused_test_log(stdout.decode())
        result['actual_fresh_runtime_input_tests'] = len(command['actual_test_names'])
        VERIFY.need(cargo_executable(Path(harness['ELF']['path']), target, 'droidloom-supervisor') == harness['ELF'],
                    'actual fresh test harness changed during execution')
        release_command, stdout, _ = run('compile-two-fresh-release-tools', ['cargo', 'build', '--release', '--locked', '-j', str(args.jobs),
            '-p', 'droidloom-supervisor', '--bins', '--message-format=json'])
        binaries = {name: select_artifact(stdout, recipe, target, name, 'bin', False)
                    for name in ('droidloom-supervisor', 'droidloomd')}
        for name, binary in binaries.items():
            _, help_text, _ = run(name + '-normal-help', [binary['ELF']['path'], '--help'], 60)
            VERIFY.need(name.encode() in help_text and b'Usage:' in help_text, 'actual fresh release CLI help required')
            VERIFY.need(cargo_executable(Path(binary['ELF']['path']), target, name) == binary['ELF'],
                        'actual fresh release identity changed during entry verification')
        result['fresh_release_tools'] = binaries
        VERIFY.need(len(result['commands']) == 5 and result['actual_fresh_runtime_input_tests'] == 9,
                    'exact five actual CI commands/nine controls/two releases required')
        VERIFY.need(VERIFY.source_snapshot(recipe, rows, VERIFY.HEAD_TREE) == before,
                    'all430 original producer file and directory F9 must remain unchanged after CI')
        VERIFY.verify_capsule(args.inventory_sha256)
        result['all430_after_bytes_Git_blobs_modes_members_F9_verified'] = True
        result['state'] = 'NINE_FRESH_RUNTIME_INPUT_CONTROLS_AND_TWO_RELEASE_TOOLS_PASSED'
    except BaseException as error:
        result['state'] = 'FAILED'
        result['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        try:
            result['all430_after_bytes_Git_blobs_modes_members_F9_verified'] = (VERIFY.source_snapshot(recipe, rows, VERIFY.HEAD_TREE) == before)
        except BaseException as check:
            result['all430_after_bytes_Git_blobs_modes_members_F9_verified'] = False
            result['errors'].append({'producer_after_error': str(check)})
    result['finished_ns'] = time.time_ns()
    VERIFY.write_report(report, result, [VERIFY.HERE, recipe, target, logdir])
    print(json.dumps({'state': result['state'], 'actual_fresh_runtime_input_tests': result['actual_fresh_runtime_input_tests'],
                      'report': str(report), 'Android_builds': 0, 'Android_starts': 0}, sort_keys=True))
    return 0 if result['state'] == 'NINE_FRESH_RUNTIME_INPUT_CONTROLS_AND_TWO_RELEASE_TOOLS_PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
