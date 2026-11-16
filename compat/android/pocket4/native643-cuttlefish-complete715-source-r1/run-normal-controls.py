#!/usr/bin/env python3
"""Compile all current Native controls in a new target and execute the exact92/98 set."""
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

SPEC = importlib.util.spec_from_file_location('native715_verifier', Path(__file__).with_name('verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
need = VERIFY.need


def cargo_executable(path, target, package):
    path, target = Path(path).absolute(), Path(target).absolute()
    need(path.resolve() == path and target.resolve() == target and path.is_relative_to(target / 'debug'),
         'actual Cargo executable must stay inside the new private debug target without aliases')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_mode & 0o111 and before.st_nlink in (1, 2)
             and 0 < before.st_size <= 128 * 1024 * 1024, 'bounded actual Cargo executable required')
        profile = target / 'debug'
        candidates = [profile / package] + list((profile / 'deps').glob(package.replace('-', '_') + '-*'))
        need(len(candidates) <= 128, 'finite private Cargo link set required')
        aliases = [item for item in candidates if os.path.lexists(item)
                   and (item.lstat().st_dev, item.lstat().st_ino) == (before.st_dev, before.st_ino)]
        need(len(set(aliases)) == before.st_nlink and path in aliases,
             'all links to the actual ELF must be inside this new target')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read()
        need(raw.startswith(b'\x7fELF') and len(raw) == before.st_size
             and VERIFY.f9(before) == VERIFY.f9(os.fstat(fd)) == VERIFY.f9(path.lstat()),
             'whole stable ELF from the current compilation required')
        for alias in aliases:
            need(alias.resolve() == alias and VERIFY.f9(alias.lstat()) == VERIFY.f9(before), 'private Cargo link changed')
        return {'path': str(path), **VERIFY.digest(raw), 'identity': VERIFY.f9(before),
                'bounded_private_Cargo_aliases': sorted(str(item) for item in aliases)}
    finally:
        os.close(fd)


def artifact_key(message):
    return json.dumps({key: value for key, value in message.items() if key != 'fresh'}, sort_keys=True, separators=(',', ':'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cargo', default='cargo')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    root = args.workspace.absolute()
    need(root.resolve() == root and root.is_dir() and not root.is_relative_to(VERIFY.HERE),
         'independent canonical producer directory required')
    manifest = VERIFY.verify_capsule(args.inventory_sha256)
    before = VERIFY.source_snapshot(root, VERIFY.catalog(manifest, 'head'), VERIFY.HEAD_TREE)
    output = VERIFY.fresh_destination(args.output, [VERIFY.HERE, root])
    output.mkdir(parents=True, mode=0o700)
    target = output / 'target'
    target.mkdir(mode=0o700)
    names = VERIFY.test_catalogs(manifest)
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_BUILD_JOBS='1', CARGO_INCREMENTAL='0', CARGO_TERM_COLOR='never')
    result = {'schema': 'pocket4-native643-complete715-fresh-normal-controls-v1', 'state': 'RUNNING',
        'source_commit': VERIFY.HEAD_COMMIT, 'source_tree': VERIFY.HEAD_TREE, 'source_files': 715,
        'fresh_Cargo_target': str(target), 'historical_tests_counted_as_fresh': 0,
        'historical_ELFs_reused': False, 'commands': [], 'artifacts': {}, 'fresh_origins': {}, 'errors': [],
        'AOSP_source_writes': 0, 'AOSP_full_builds_started': 0, 'Android_starts': 0,
        'runtime_qualified': False, 'production_ready': False, 'started_ns': time.time_ns()}
    origins = {}

    def run(name, argv, timeout=1800):
        outp, errp = output / (name + '.stdout'), output / (name + '.stderr')
        began, timed_out = time.time_ns(), False
        with outp.open('xb') as out, errp.open('xb') as err:
            child = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
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
        row = {'name': name, 'argv': argv, 'pid': child.pid, 'returncode': code,
               'actual_child_reaped': True, 'timed_out': timed_out, 'started_ns': began,
               'finished_ns': time.time_ns(), 'stdout': {'path': str(outp), **VERIFY.digest(stdout)},
               'stderr': {'path': str(errp), **VERIFY.digest(stderr)}}
        result['commands'].append(row)
        VERIFY.write_report(output / (name + '.json'), row, [VERIFY.HERE, root, target])
        need(not timed_out and code == 0, 'ordinary command failed; original logs retained: ' + name)
        return stdout

    def cargo(operation, packages, *rest):
        argv = [args.cargo, operation, '--locked']
        if args.offline:
            argv.append('--offline')
        argv += ['-j', '1']
        for package in packages:
            argv += ['-p', package]
        return argv + list(rest)

    def compile_batch(name, argv):
        rows = VERIFY.successful_cargo_stream(run(name, argv))
        for message in rows:
            if message.get('reason') != 'compiler-artifact' or not message.get('executable'):
                continue
            package = next((p for p in ('droidloom-source', 'droidloom-update')
                            if message.get('manifest_path') == str(root / 'tools' / p / 'Cargo.toml')), None)
            if package is None or message['target']['kind'] not in (['bin'], ['lib']):
                continue
            kind = message['target']['kind'][0]
            target_name = package.replace('-', '_') if kind == 'lib' else package
            if message['target']['name'] != target_name:
                continue
            need(message['target']['src_path'] == str(root / 'tools' / package / 'src' / ('lib.rs' if kind == 'lib' else 'main.rs')),
                 'Cargo executable must compile the fixed complete715 producer')
            key = artifact_key(message)
            current = cargo_executable(message['executable'], target, package)
            if message['fresh'] is False:
                need(key not in origins, 'the same current artifact was unexpectedly rebuilt')
                origins[key] = {'compile_command': name, 'Cargo_message': message, 'ELF': current, 'package': package}
            else:
                need(message['fresh'] is True and key in origins and origins[key]['ELF'] == current,
                     'cached artifact lacks a stable fresh origin in this exact new-target batch')
        return rows

    def select(rows, package, kind, is_test):
        name = package.replace('-', '_') if kind == 'lib' else package
        matches = [row for row in rows if row.get('reason') == 'compiler-artifact' and row.get('executable')
                   and row['target']['name'] == name and row['target']['kind'] == [kind] and row['profile']['test'] is is_test]
        need(len(matches) == 1, 'one exact actual Cargo executable required')
        message = matches[0]
        key = artifact_key(message)
        need(key in origins, 'selected executable lacks an actual fresh current origin')
        current = cargo_executable(message['executable'], target, package)
        need(current == origins[key]['ELF'], 'selected executable changed after its actual fresh compilation')
        label = package + ('-tests' if is_test else '-normal-cli')
        result['artifacts'][label] = {'selected_Cargo_message': message, 'fresh_origin': origins[key]}
        return message['executable']

    def execute(name, binary, expected, *filters):
        raw = run(name, [binary, *filters, '--test-threads=1', '--color', 'never'])
        return VERIFY.test_terminal(raw.decode(), expected)

    try:
        rows = compile_batch('compile-update-tests', cargo('test', ['droidloom-update'], '--no-run', '--message-format=json'))
        update = select(rows, 'droidloom-update', 'bin', True)
        listed = [line[:-6] for line in run('list-update-tests', [update, '--list']).decode().splitlines() if line.endswith(': test')]
        need(all(listed.count(name) == 1 for key in ('pair', 'permissions', 'journal', 'focused') for name in names[key]),
             'every pinned current control must exist exactly once in the real fresh harness')
        executions = 0
        for index, name in enumerate(names['focused']):
            executions += execute('focused-' + str(index), update, [name], name, '--exact')
        executions += execute('all53-pair', update, names['pair'], 'native_generation_pair_build::')
        executions += execute('all7-permissions', update, names['permissions'], 'android::tests::projection_v2_')
        for index, name in enumerate(names['journal']):
            executions += execute('journal-' + str(index), update, [name], name, '--exact')
        rows = compile_batch('compile-source-tests', cargo('test', ['droidloom-source'], '--lib', '--no-run', '--message-format=json'))
        source_test = select(rows, 'droidloom-source', 'lib', True)
        executions += execute('all26-source', source_test, names['source'])
        rows = compile_batch('compile-both-normal-clis', cargo('build', ['droidloom-source', 'droidloom-update'], '--message-format=json'))
        source = select(rows, 'droidloom-source', 'bin', False)
        update_cli = select(rows, 'droidloom-update', 'bin', False)
        for name, binary in (('source', source), ('update', update_cli)):
            help_text = run(name + '-help', [binary, '--help'])
            need(b'Usage:' in help_text, 'actual normal CLI help required')
        lock = str(root / 'android/native-generation-pair/source-lock.json')
        run('source-verify-lock', [source, 'verify-lock', '--lock', lock])
        plan = VERIFY.decode(run('source-plan', [source, 'plan', '--lock', lock]))
        need(len(plan['projects']) == 643 and len(plan['links']) == 8
             and plan['unrestricted_repo_sync'] is False
             and plan['superproject_commit'] == '28f0bbddc24d56c8ec5a8df5342ac7a292184039', 'exact current source plan required')
        need(executions == 98 and len(result['commands']) == 23 and len(result['artifacts']) == 4,
             'complete fresh23-command/92-distinct/98-execution/two-harness/two-CLI set required')
        for key, origin in origins.items():
            need(cargo_executable(origin['ELF']['path'], target, origin['package']) == origin['ELF'],
                 'actual fresh artifact changed during the ordinary batch')
        result['fresh_origins'] = {origin['ELF']['path']: origin for origin in origins.values()}
        need(VERIFY.source_snapshot(root, VERIFY.catalog(manifest, 'head'), VERIFY.HEAD_TREE) == before,
             'all715 original source file and directory F9 must remain unchanged')
        VERIFY.verify_capsule(args.inventory_sha256)
        result.update(state='NORMAL_SOURCE_CONTROLS_PASSED', distinct_tests=92, test_executions=98,
                      actual_commands=23, actual_source_projects=643, actual_root_links=8,
                      all715_source_inputs_unchanged=True, full_source_root_verified=VERIFY.HEAD_TREE)
    except BaseException as error:
        result['state'] = 'FAILED'
        result['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        try:
            result['all715_source_inputs_unchanged'] = (VERIFY.source_snapshot(root, VERIFY.catalog(manifest, 'head'), VERIFY.HEAD_TREE) == before)
        except BaseException as after_error:
            result['all715_source_inputs_unchanged'] = False
            result['errors'].append({'stage': 'source_after', 'message': str(after_error)})
    result['finished_ns'] = time.time_ns()
    VERIFY.write_report(output / 'result.json', result, [VERIFY.HERE, root, target])
    print(json.dumps({key: result[key] for key in ('state', 'errors', 'runtime_qualified', 'production_ready')}, sort_keys=True))
    return 0 if result['state'] == 'NORMAL_SOURCE_CONTROLS_PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
