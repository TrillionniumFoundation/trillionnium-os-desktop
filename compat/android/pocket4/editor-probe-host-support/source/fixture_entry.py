"""Explicit source-bound Editor03/Probe03 entry. Import is inert."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import types


def bootstrap(args):
    def read(path, maximum):
        path = Path(path)
        if not path.is_absolute() or path.resolve() != path:
            raise RuntimeError('EXACT_CANONICAL_NEW_SOURCE')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            first = os.fstat(fd)
            if not stat.S_ISREG(first.st_mode) or first.st_nlink != 1 or not 0 < first.st_size <= maximum:
                raise RuntimeError('BOUNDED_NEW_SOURCE_FILE')
            with os.fdopen(os.dup(fd), 'rb') as stream:
                raw = stream.read(maximum + 1)
            keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            after = os.fstat(fd); named = path.lstat()
            if len(raw) != first.st_size or not all(getattr(first, k) == getattr(after, k) == getattr(named, k) for k in keys):
                raise RuntimeError('NEW_SOURCE_CHANGED_DURING_READ')
            return raw
        finally:
            os.close(fd)
    raw = read(args.preparation, 131072)
    if hashlib.sha256(raw).hexdigest() != args.expect_preparation_sha256:
        raise RuntimeError('EXTERNAL_FROZEN_SYSTEM_PREPARATION_PIN_REQUIRED')
    packet = json.loads(raw)
    rows = [r for r in packet['files'] if Path(r['path']).name == 'app_common.py']
    if len(rows) != 1:
        raise RuntimeError('ONE_FROZEN_COMMON_SOURCE_REQUIRED')
    ref = rows[0]; source = read(ref['path'], 2 * 1024 * 1024)
    if len(source) != ref['bytes'] or hashlib.sha256(source).hexdigest() != ref['sha256']:
        raise RuntimeError('COMMON_SOURCE_PIN_CHANGED')
    c = types.ModuleType('fresh_system_common'); c.__file__ = ref['path']
    exec(compile(source, ref['path'], 'exec'), c.__dict__)
    prep = {'path': args.preparation, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    def load(name):
        found = [r for r in packet['files'] if Path(r['path']).name == name]
        c.need(len(found) == 1, 'ONE_SYSTEM_PREPARATION_MODULE:' + name)
        return c.module(found[0], 'new_system_' + Path(name).stem)
    plan = load('fixture_plan.py'); plan.preparation(c, prep)
    own = [r for r in packet['files'] if Path(r['path']).name == 'fixture_entry.py']
    actual = c.regular(Path(__file__).resolve(), contents=False)
    c.need(len(own) == 1 and (actual['bytes'], actual['sha256']) == (own[0]['bytes'], own[0]['sha256']),
           'ACTUAL_EXECUTED_SYSTEM_ENTRY_SOURCE')
    return c, packet, prep, plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation', required=True); p.add_argument('--expect-preparation-sha256', required=True)
    p.add_argument('mode', choices=('inspect-source', 'identity', 'plan', 'execute'))
    p.add_argument('--request'); p.add_argument('--expect-request-sha256')
    p.add_argument('--kind', choices=('qa_probe03', 'editor_ui03'))
    p.add_argument('--role', choices=('qa-probe', 'editor', 'native-helper'))
    p.add_argument('--output')
    args = p.parse_args(); c, packet, prep, planner = bootstrap(args)
    if args.mode == 'inspect-source':
        print(json.dumps({'source_preparation': prep, 'source_files': len(packet['files']),
            'source_entrypoints_present': True, 'Android_UI_actions': 0,
            'source_publication_authorizes_Android': False, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    c.need(os.getuid() == os.geteuid() == 0 and args.request and args.expect_request_sha256,
           'EXPLICIT_REAL_INPUT_REQUEST_AND_EXTERNAL_PIN')
    raw, request_ref = c.regular(args.request, 131072)
    c.need(request_ref['sha256'] == args.expect_request_sha256, 'ACTUAL_REQUEST_PIN_CHANGED')
    request = c.parse(raw)
    if args.mode == 'identity':
        c.need(args.role is not None and args.output is not None and args.kind is None,
               'EXACT_METADATA_ONLY_IDENTITY_ARGUMENTS')
        profiles = planner.named(c, packet, 'fixture_profiles.py')
        target = {'qa-probe': profiles.PROBE, 'editor': profiles.EDITOR,
            'native-helper': profiles.NATIVE_HELPER}[args.role]
        c.need(c.parse(c.read_ref(request['qualification'])).get('source_manifest') == c.SUPPORT_REF,
               'ACTUAL_HOST_BUSINESS_BASELINE_FOR_THESE_TWO_CASES')
        source = next(r for r in packet['files'] if Path(r['path']).name == 'fixture_entry.py')
        result = c.collect_identity(request, args.output, target, source)
    elif args.mode == 'plan':
        c.need(args.kind is not None and args.output is not None and args.role is None, 'EXPLICIT_ORIGINAL_CASE_PLAN_ARGUMENTS')
        result = planner.create(c, args.kind, request, args.output, prep)
    else:
        c.need(set(request) == {'base_plan'} and args.kind is args.output is args.role is None,
               'EXECUTE_ONLY_ONE_PREPARED_NEW_PLAN')
        base = c.parse(c.read_ref(request['base_plan']))
        c.need(base['source_preparation'] == prep, 'PLAN_NOT_FROM_THIS_FROZEN_PREPARATION')
        # The trusted planner is loaded from the external preparation pin.
        # Reject differing task code before executing any task module; each
        # module's self-declared digest alone cannot establish that relation.
        task = planner.source_packet(c, base, packet)
        components = {Path(row['path']).name: c.module(row, 'actual_system_case_' + Path(row['path']).stem)
            for row in task['files'] if row['path'].endswith('.py')}
        actual, outcome = components['fixture_case.py'].execute(c, request['base_plan'], components)
        print(json.dumps({'result': actual, 'state': outcome['state'],
            'case_business_success_verified': outcome['case_business_success_verified'],
            'whole_app_business_accepted': False}, sort_keys=True))
        return 0 if outcome['case_business_success_verified'] else 1
    c.read_ref(request_ref)
    print(json.dumps({'result': result, 'whole_app_business_accepted': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
