"""New-cohort Settings pages and font-scale source; native release still required."""
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
        raise RuntimeError('EXTERNAL_FROZEN_SETTINGS_PREPARATION_PIN_REQUIRED')
    packet = json.loads(raw)
    rows = [r for r in packet['files'] if Path(r['path']).name == 'app_common.py']
    if len(rows) != 1:
        raise RuntimeError('ONE_FROZEN_COMMON_SOURCE_REQUIRED')
    ref = rows[0]; source = read(ref['path'], 2 * 1024 * 1024)
    if len(source) != ref['bytes'] or hashlib.sha256(source).hexdigest() != ref['sha256']:
        raise RuntimeError('COMMON_SOURCE_PIN_CHANGED')
    c = types.ModuleType('fresh_settings_common'); c.__file__ = ref['path']
    exec(compile(source, ref['path'], 'exec'), c.__dict__)
    prep = {'path': args.preparation, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    def load(name):
        found = [r for r in packet['files'] if Path(r['path']).name == name]
        c.need(len(found) == 1, 'ONE_SETTINGS_PREPARATION_MODULE:' + name)
        return c.module(found[0], 'new_settings_' + Path(name).stem)
    plan = load('settings_plan.py'); plan.preparation(c, prep)
    own = [r for r in packet['files'] if Path(r['path']).name == 'settings_entry.py']
    actual = c.regular(Path(__file__).resolve(), contents=False)
    c.need(len(own) == 1 and (actual['bytes'], actual['sha256']) == (own[0]['bytes'], own[0]['sha256']),
           'ACTUAL_EXECUTED_SETTINGS_ENTRY_SOURCE')
    return c, packet, prep, plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation',required=True)
    parser.add_argument('--expect-preparation-sha256',required=True)
    parser.add_argument('mode',choices=('inspect-source','identity','plan','execute'))
    parser.add_argument('--request');parser.add_argument('--expect-request-sha256')
    parser.add_argument('--role',choices=('settings','native-helper'));parser.add_argument('--output')
    args=parser.parse_args();c,packet,prep,planner=bootstrap(args)
    native_rows=[r for r in packet['files'] if Path(r['path']).name=='native_settings_release.py']
    if args.mode=='inspect-source':
        print(json.dumps({'source_preparation':prep,'source_files':len(packet['files']),
            'business_consumer_entrypoints_present':True,'native_execution_binding_present':len(native_rows)==1,
            'native_profile_adoption_required':'settings-pages','Android_actions':0,
            'source_publication_authorizes_Android':False,'whole_app_business_accepted':False},sort_keys=True))
        return 0
    c.need(os.getuid()==os.geteuid()==0 and args.request and args.expect_request_sha256,
           'EXPLICIT_REAL_SETTINGS_REQUEST_AND_EXTERNAL_PIN')
    raw,request_ref=c.regular(args.request,131072)
    c.need(request_ref['sha256']==args.expect_request_sha256,'SETTINGS_REQUEST_PIN_CHANGED')
    request=c.parse(raw)
    if args.mode=='identity':
        c.need(args.role is not None and args.output is not None,'EXACT_SETTINGS_IDENTITY_ARGUMENTS')
        profile=planner.named(c,packet,'settings_profiles.py')
        target=profile.TARGET if args.role=='settings' else profile.HELPER
        c.need(c.parse(c.read_ref(request['qualification'])).get('source_manifest')==c.SUPPORT_REF,
               'ACTUAL_NEW_MAIN_SUPPORT_REQUIRED_FOR_SETTINGS_IDENTITY')
        source=next(r for r in packet['files'] if Path(r['path']).name=='settings_entry.py')
        result=c.collect_identity(request,args.output,target,source)
    elif args.mode=='plan':
        c.need(args.role is None and args.output is not None,'EXPLICIT_SETTINGS_PLAN_ARGUMENTS')
        result=planner.create(c,request,args.output,prep)
    else:
        c.need(set(request)=={'base_plan'} and args.role is args.output is None,
               'EXECUTE_ONE_EXACT_NEW_SETTINGS_PLAN')
        # The new native route has not yet been adopted. Missing dedicated
        # source fails before creating execute-once, a lease, or an Android
        # scope. Gallery/Calendar validators cannot authorize this package.
        c.need(len(native_rows)==1,'DEDICATED_SETTINGS_NATIVE_RELEASE_SOURCE_NOT_YET_PREPARED')
        base=c.parse(c.read_ref(request['base_plan']))
        c.need(base['source_preparation']==prep,'SETTINGS_PLAN_IS_NOT_THIS_PREPARATION')
        task=planner.source_packet(c,base,packet)
        modules={Path(row['path']).name:c.module(row,'actual_settings_'+Path(row['path']).stem)
                 for row in task['files'] if row['path'].endswith('.py')}
        native=modules['native_settings_release.py']
        with native.bind_current(prep) as release:
            scope=release.admit_owned_leaf_resources()
            c.need(type(scope) is native.OwnedLeafResources,'EXACT_LIVE_SETTINGS_RESOURCE_SCOPE_CLASS')
            modules['settings_runtime.py'].resource_report(c,scope);release.guard()
            actual,outcome=modules['settings_case.py'].execute(c,request['base_plan'],modules,release,scope)
            c.read_ref(request_ref);release.guard()
            print(json.dumps({'result':actual,'state':outcome['state'],
                'case_business_success_verified':outcome['case_business_success_verified'],
                'scope':['settings.pages','settings.roundtrip'],'whole_app_business_accepted':False},sort_keys=True))
            return 0 if outcome['case_business_success_verified'] else 1
    c.read_ref(request_ref)
    print(json.dumps({'result':result,'whole_app_business_accepted':False},sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())

