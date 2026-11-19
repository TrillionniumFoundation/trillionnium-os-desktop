"""Explicit final-Main factories and once-only original case entrypoints.

Loading or publishing this file sends no Android command. Every operation
requires an external frozen preparation pin and actual new-Main inputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types


def bootstrap(args):
    def read(path, maximum):
        path = Path(path)
        if not path.is_absolute() or path.resolve() != path:
            raise RuntimeError('CANONICAL_PREPARATION_SOURCE_REQUIRED')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            first = os.fstat(fd)
            if not stat.S_ISREG(first.st_mode) or first.st_nlink != 1 or not 0 < first.st_size <= maximum:
                raise RuntimeError('BOUNDED_PREPARATION_SOURCE_REQUIRED')
            with os.fdopen(os.dup(fd), 'rb') as stream:
                raw = stream.read(maximum + 1)
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            last = os.fstat(fd); named = path.lstat()
            if len(raw) != first.st_size or not all(getattr(first, k) == getattr(last, k) == getattr(named, k) for k in fields):
                raise RuntimeError('PREPARATION_SOURCE_CHANGED')
            return raw
        finally:
            os.close(fd)
    raw = read(args.preparation, 131072)
    if hashlib.sha256(raw).hexdigest() != args.expect_preparation_sha256:
        raise RuntimeError('EXTERNAL_FROZEN_PREPARATION_PIN_REQUIRED')
    packet = json.loads(raw); matches = [r for r in packet['files'] if Path(r['path']).name == 'app_common.py']
    if len(matches) != 1:
        raise RuntimeError('ONE_ACTUAL_NEW_COMMON_SOURCE_REQUIRED')
    row = matches[0]; code = read(row['path'], 2 * 1024 * 1024)
    if len(code) != row['bytes'] or hashlib.sha256(code).hexdigest() != row['sha256']:
        raise RuntimeError('FROZEN_COMMON_SOURCE_CHANGED')
    common = types.ModuleType('actual_final_case_common'); common.__file__ = row['path']
    exec(compile(code, row['path'], 'exec'), common.__dict__)
    ref = {'path': str(args.preparation), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    planner = load(common, packet, 'app_plan.py'); planner.preparation(common, ref)
    own = next(r for r in packet['files'] if Path(r['path']).name == 'app_entry.py')
    actual = common.regular(Path(__file__).resolve(), 2 * 1024 * 1024, contents=False)
    common.need(actual['bytes'] == own['bytes'] and actual['sha256'] == own['sha256'], 'ACTUAL_EXECUTED_ENTRY_SOURCE_PIN')
    return common, packet, ref


def source_ref(common, packet, name):
    rows = [r for r in packet['files'] if Path(r['path']).name == name]
    common.need(len(rows) == 1, 'ONE_EXACT_NEW_PACKET_SOURCE:' + name)
    return rows[0]


def load(common, packet, name):
    return common.module(source_ref(common, packet, name), 'new_entry_' + Path(name).stem)


def external_ref(common, path, digest):
    ref = common.regular(path, contents=False)
    common.need(ref['sha256'] == digest, 'EXTERNAL_ACTUAL_INPUT_PIN_CHANGED')
    return ref


def run_case(common, packet, preparation_ref, base_ref):
    base = common.parse(common.read_ref(base_ref)); _, modules = common.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    planner = load(common, packet, 'app_plan.py'); planner.validate(common, base, baseline)
    common.need(base['source_preparation'] == preparation_ref, 'PLAN_NOT_THIS_FROZEN_PREPARATION')
    runtime = load(common, packet, 'app_runtime.py')
    root = common.private_dir(Path(base['case_root']) / 'coordinator', create=True)
    task = common.parse(common.read_ref(base['task_source_manifest']))
    entry = next(r for r in task['files'] if Path(r['path']).name == 'app_entry.py')
    common.read_ref(entry)
    request_path = root / 'dispatch.json'
    mode = 'clock-worker' if base['kind'] == 'clock_timer' else 'ihg-coordinator'
    request = {'schema': 'pocket4-final-app-coordinator-dispatch-v1', 'base_plan': base_ref,
        'source_preparation': preparation_ref, 'worker_entry': entry, 'worker_mode': mode,
        'operator': runtime.process(common, os.getpid()), 'boot_id': runtime.boot(),
        'automatic_retry': False, 'whole_app_business_accepted': False}
    dispatch_ref = common.write_new(request_path, request, 0o400)
    argv = ['/usr/bin/python3', '-I', '-B', entry['path'], '--preparation', preparation_ref['path'],
        '--expect-preparation-sha256', preparation_ref['sha256'], mode,
        '--request', dispatch_ref['path'], '--expect-request-sha256', dispatch_ref['sha256']]
    result = {'schema': 'pocket4-final-app-case-coordinator-result-v1', 'base_plan': base_ref,
        'dispatch': dispatch_ref, 'ok': False, 'error': None, 'whole_app_business_accepted': False,
        'Binder_UID_cleanup_verified': False, 'automatic_retry': False}
    def guard(*, action_attempted=False):
        common.read_ref(dispatch_ref); common.read_ref(base_ref); common.read_ref(entry)
        planner.preparation(common, preparation_ref)
        return baseline.guard(action_attempted=action_attempted)
    try:
        completed = modules['business_commands.py'].run_recorded('case-worker', argv,
            410 if base['kind'] == 'clock_timer' else 620, root, guard,
            protected_pids=baseline.protected_pids, mutation=True, check=False, output_bound=1024 * 1024)
        result['worker_host_result'] = common.regular(root / 'case-worker.result.json', contents=False)
        common.need(completed.host_tree_retired and not completed.host_timed_out and completed.recorder_errors == [],
                    'CASE_WORKER_NOT_ACTUALLY_RETIRED')
        child_ref = common.regular(Path(base['case_root']) / 'result.json', contents=False)
        child = common.parse(common.read_ref(child_ref)); printed = common.parse(completed.stdout)
        common.need(printed == {'result': child_ref, 'ok': child['ok'], 'whole_app_business_accepted': False}
            and child['base_plan'] == base_ref and child['whole_app_business_accepted'] is False
            and completed.returncode == (0 if child['ok'] else 2), 'DURABLE_CASE_RESULT_AND_REAL_PARENT_EXIT_REQUIRED')
        result['worker_result'] = child_ref
        common.need(child['ok'] is True and child['error'] is None and child['secondary_errors'] == [],
                    'ORIGINAL_CASE_DID_NOT_COMPLETE')
        guard(action_attempted=True); result['ok'] = True
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error),
            'command_observation': getattr(error, 'command_observation', None)}
    ref = common.write_new(root / 'result.json', result)
    return ref, result


def internal_case(common, packet, preparation_ref, request_ref, mode):
    request = common.parse(common.read_ref(request_ref)); runtime = load(common, packet, 'app_runtime.py')
    common.need(set(request) == {'schema', 'base_plan', 'source_preparation', 'worker_entry', 'worker_mode',
        'operator', 'boot_id', 'automatic_retry', 'whole_app_business_accepted'}
        and request['schema'] == 'pocket4-final-app-coordinator-dispatch-v1'
        and request['source_preparation'] == preparation_ref and request['worker_mode'] == mode
        and request['boot_id'] == runtime.boot() and request['automatic_retry'] is False
        and request['whole_app_business_accepted'] is False
        and Path(request['worker_entry']['path']) == Path(__file__).resolve(), 'ACTUAL_NEW_COORDINATOR_DISPATCH_REQUIRED')
    common.read_ref(request['worker_entry']); runtime.descendant(common, request['operator'])
    common.need(os.getpid() != request['operator']['pid'], 'CASE_MUST_BE_AN_ACTUAL_OWNED_WORKER')
    case = load(common, packet, 'clock_case.py' if mode == 'clock-worker' else 'ihg_case.py')
    return case.execute(common, request['base_plan'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True, type=Path)
    parser.add_argument('--expect-preparation-sha256', required=True)
    commands = parser.add_subparsers(dest='mode', required=True)
    for name in ('identity', 'helper-source', 'helper-build', 'helper-install', 'plan',
                 'execute', 'clock-worker', 'ihg-coordinator'):
        command = commands.add_parser(name)
        command.add_argument('--request', required=True, type=Path)
        command.add_argument('--expect-request-sha256', required=True)
        if name in ('identity', 'helper-source', 'helper-build', 'helper-install', 'plan'):
            command.add_argument('--output', required=True, type=Path)
        if name == 'identity':
            command.add_argument('--role', required=True, choices=('clock', 'clock-helper', 'ihg', 'ihg-helper'))
        if name == 'plan':
            command.add_argument('--kind', required=True, choices=('clock_timer', 'ihg_london'))
    command = commands.add_parser('ihg-worker')
    command.add_argument('--scope', required=True, type=Path); command.add_argument('--expect-scope-sha256', required=True)
    command.add_argument('--phase', required=True, choices=('launch', 'inspect', 'cleanup'))
    args = parser.parse_args(); os.umask(0o077)
    common, packet, preparation_ref = bootstrap(args)
    common.need(os.getuid() == os.geteuid() == 0, 'ROOT_NEW_CASE_OPERATOR_REQUIRED')
    if args.mode == 'ihg-worker':
        scope_ref = external_ref(common, args.scope, args.expect_scope_sha256)
        scope = common.parse(common.read_ref(scope_ref)); active = common.parse(common.read_ref(scope['phase_plan']))
        common.need(active['source_preparation'] == preparation_ref, 'ACTUAL_IHG_WORKER_PREPARATION_REQUIRED')
        ref, result = load(common, packet, 'ihg_case.py').worker(common, scope_ref, args.phase)
    else:
        request_ref = external_ref(common, args.request, args.expect_request_sha256)
        request = common.parse(common.read_ref(request_ref))
        if args.mode in ('clock-worker', 'ihg-coordinator'):
            ref, result = internal_case(common, packet, preparation_ref, request_ref, args.mode)
        elif args.mode == 'execute':
            common.need(set(request) == {'plan'}, 'ONE_EXACT_NEW_PLAN_EXECUTION_INPUT')
            ref, result = run_case(common, packet, preparation_ref, request['plan'])
        elif args.mode == 'plan':
            ref = load(common, packet, 'app_plan.py').create(common, args.kind, request, args.output, preparation_ref)
            result = {'ok': True}
        elif args.mode == 'helper-source':
            ref = load(common, packet, 'ihg_helper_factory.py').create(common, request, args.output, preparation_ref)
            result = {'ok': True}
        elif args.mode == 'helper-build':
            common.need(set(request) == {'source'}, 'ONE_ACTUAL_HELPER_SOURCE_REFERENCE')
            ref = load(common, packet, 'ihg_helper_build.py').build(common, request['source'], args.output)
            result = {'ok': True}
        elif args.mode == 'helper-install':
            common.need(set(request) == {'build', 'target_identity'}, 'EXACT_ACTUAL_HELPER_INSTALL_INPUTS')
            ref = load(common, packet, 'ihg_helper_install.py').install(common, request['build'], request['target_identity'],
                args.output, source_ref(common, packet, 'app_profiles.py'), source_ref(common, packet, 'ihg_staging.py'),
                source_ref(common, packet, 'ihg_helper_build.py'))
            result = {'ok': True}
        else:
            profiles = load(common, packet, 'app_profiles.py')
            expected = {'clock': profiles.CLOCK, 'clock-helper': profiles.CLOCK_HELPER, 'ihg': profiles.IHG}.get(args.role)
            if args.role == 'ihg-helper':
                common.need(set(request) == {'baseline', 'qualification', 'build', 'install', 'target_identity'},
                            'NEW_HELPER_IDENTITY_REQUIRES_ACTUAL_INSTALL_CHAIN')
                builder = load(common, packet, 'ihg_helper_build.py')
                build, source, _, _ = builder.verify_build(common, request['build'])
                common.need(source['baseline'] == request['baseline'] and source['qualification'] == request['qualification'],
                            'ACTUAL_HELPER_IDENTITY_MAIN_CHANGED')
                qa = common.module(source['files']['qa_contract.py'], 'new_actual_identity_helper_protocol')
                install = load(common, packet, 'ihg_helper_install.py').verify_install(common, request['install'],
                    build, source, qa, request['target_identity'])
                expected = profiles.helper_expected(common, build, install['helper_uid'])
            else:
                common.need(set(request) == {'baseline', 'qualification'}, 'ACTUAL_NEW_MAIN_IDENTITY_INPUTS')
            common.need(args.output.parent == common.FINAL / 'qualification'
                and common.re.fullmatch(r'business-app-identity-[0-9a-f]{32}', args.output.name), 'NEW_IDENTITY_OUTPUT_ROOT')
            ref = common.collect_identity({k: request[k] for k in ('baseline', 'qualification')}, args.output,
                expected, source_ref(common, packet, 'app_common.py'))
            result = {'ok': True}
    print(json.dumps({'result': ref, 'ok': result['ok'], 'whole_app_business_accepted': False}, sort_keys=True), flush=True)
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'ok': False, 'error': type(error).__name__, 'message': str(error),
            'automatic_retry': False, 'whole_app_business_accepted': False}), file=sys.stderr, flush=True)
        raise SystemExit(2)
