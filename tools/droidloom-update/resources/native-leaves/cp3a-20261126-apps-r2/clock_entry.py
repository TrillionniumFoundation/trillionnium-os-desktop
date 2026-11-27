"""Externally pinned fresh-Main Clock entry. Import performs no operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import types


def bootstrap(args):
    def read(path,limit):
        path=Path(path)
        if not path.is_absolute() or path.resolve()!=path:raise RuntimeError('CANONICAL_PREPARATION_SOURCE_REQUIRED')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            first=os.fstat(fd)
            if not stat.S_ISREG(first.st_mode) or first.st_nlink!=1 or not 0<first.st_size<=limit:raise RuntimeError('BOUNDED_SOURCE_REQUIRED')
            with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
            after=os.fstat(fd);named=path.lstat();keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
            if len(raw)!=first.st_size or not all(getattr(first,k)==getattr(after,k)==getattr(named,k) for k in keys):raise RuntimeError('SOURCE_CHANGED_DURING_READ')
            return raw
        finally:os.close(fd)
    raw=read(args.preparation,131072)
    if hashlib.sha256(raw).hexdigest()!=args.expect_preparation_sha256:raise RuntimeError('EXTERNAL_PREPARATION_PIN_REQUIRED')
    packet=json.loads(raw);rows=[r for r in packet['files'] if Path(r['path']).name=='app_common.py']
    if len(rows)!=1:raise RuntimeError('ONE_FROZEN_COMMON_SOURCE_REQUIRED')
    row=rows[0];source=read(row['path'],2097152)
    if len(source)!=row['bytes'] or hashlib.sha256(source).hexdigest()!=row['sha256']:raise RuntimeError('FROZEN_COMMON_CHANGED')
    c=types.ModuleType('actual_clock_common');c.__file__=row['path'];exec(compile(source,row['path'],'exec'),c.__dict__)
    prep={'path':args.preparation,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    found=[r for r in packet['files'] if Path(r['path']).name=='clock_plan.py'];c.need(len(found)==1,'ONE_EXTERNAL_CLOCK_PLANNER')
    planner=c.module(found[0],'actual_clock_trusted_plan');planner.preparation(c,prep)
    own=[r for r in packet['files'] if Path(r['path']).name=='clock_entry.py'];actual=c.regular(Path(__file__).resolve(),contents=False)
    c.need(len(own)==1 and (actual['bytes'],actual['sha256'])==(own[0]['bytes'],own[0]['sha256']),
        'ACTUAL_EXECUTED_FROZEN_CLOCK_ENTRY')
    return c,packet,prep,planner


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation',required=True);p.add_argument('--expect-preparation-sha256',required=True)
    p.add_argument('mode',choices=('inspect-source','identity','source','plan','execute','execute-worker'))
    p.add_argument('--request');p.add_argument('--expect-request-sha256');p.add_argument('--output')
    p.add_argument('--role',choices=('clock','native-helper'))
    p.add_argument('--monitor-fd',type=int);p.add_argument('--monitor-parent');p.add_argument('--expect-monitor-parent-sha256')
    args=p.parse_args();c,packet,prep,planner=bootstrap(args)
    monitor_flags=(args.monitor_fd,args.monitor_parent,args.expect_monitor_parent_sha256)
    c.need(all(value is None for value in monitor_flags) if args.mode!='execute-worker'
        else all(value is not None for value in monitor_flags),'MONITOR_FLAGS_ONLY_ON_PARENT_OWNED_EXPIRY_WORKER')
    if args.mode=='inspect-source':
        print(json.dumps({'source_preparation':prep,'source_files':len(packet['files']),'source_entrypoints_present':True,
            'Android_UI_actions':0,'source_publication_authorizes_Android':False,
            'original_scopes':['timer15','expiry06_with_expiry05_delivery_observation','alarm04'],
            'whole_app_business_accepted':False},sort_keys=True));return 0
    c.need(os.getuid()==os.geteuid()==0 and args.request and args.expect_request_sha256,
        'EXPLICIT_ROOT_ACTUAL_CLOCK_REQUEST_AND_PIN')
    raw,request_ref=c.regular(args.request,131072);c.need(request_ref['sha256']==args.expect_request_sha256,'ACTUAL_REQUEST_PIN_CHANGED')
    request=c.parse(raw)
    if args.mode=='identity':
        c.need(args.role is not None and args.output is not None,'EXPLICIT_CLOCK_IDENTITY_ROLE')
        profiles=planner.named(c,packet,'clock_profiles.py')
        profile={'clock':profiles.CLOCK,'native-helper':profiles.NATIVE_HELPER}[args.role]
        c.need(c.current_qualification_support(request['baseline'], request['qualification'])==c.CLOCK_SUPPORT_REF,
            'ACTUAL_R8_RETAINED_PREIMAGE_CLOCK_BASELINE')
        own=next(row for row in packet['files'] if Path(row['path']).name=='clock_entry.py')
        result=c.collect_identity(request,args.output,profile,own)
    else:
        c.need(args.role is None,'NO_IDENTITY_ROLE_ON_OTHER_CLOCK_ENTRIES')
        if args.mode=='source':
            c.need(args.output is not None,'EXPLICIT_NEW_CLOCK_CASE_ROOT');result=planner.create_source(c,request,args.output,prep)
        elif args.mode=='plan':
            c.need(args.output is None,'CLOCK_PLAN_LOCATION_FIXED_BY_SOURCE');result=planner.bind(c,request,prep)
        else:
            c.need(set(request)=={'plan'} and args.output is None,'ONE_EXPLICIT_PREPARED_CLOCK_PLAN')
            plan=c.parse(c.read_ref(request['plan']));c.need(plan['source_preparation']==prep,'CLOCK_PLAN_EXTERNAL_PREPARATION')
            source=c.parse(c.read_ref(plan['source']));c.need(source['source_preparation']==prep,'CLOCK_SOURCE_EXTERNAL_PREPARATION')
            task=planner.source_packet(c,source,packet)
            # The trusted planner validates actual Main and package receipts as
            # well as the externally frozen copy before importing task code.
            planner.validate_plan(c,request['plan'],prep)
            modules={Path(row['path']).name:c.module(row,'actual_clock_case_'+Path(row['path']).stem)
                for row in task['files'] if row['path'].endswith('.py')}
            if args.mode=='execute-worker':
                c.need(plan['kind']=='expiry06','ONLY_EXPIRY_HAS_PASSIVE_MONITOR_SIBLING')
                _,parent=c.regular(args.monitor_parent,131072)
                c.need(parent['sha256']==args.expect_monitor_parent_sha256,'ACTUAL_NOTIFY_PARENT_PIN')
                monitor=modules['clock_monitor_channel.py'].Client(c,modules['app_runtime.py'],args.monitor_fd,
                    parent,request['plan'],prep,plan['case_root'])
                try:result,outcome=modules['clock_case.py'].execute(c,request['plan'],prep,modules,monitor)
                finally:monitor.close()
            elif plan['kind']=='expiry06':
                result,outcome=modules['clock_notify_supervisor.py'].Supervisor(c,request['plan'],prep,modules,request_ref).run()
            else:result,outcome=modules['clock_case.py'].execute(c,request['plan'],prep,modules)
            print(json.dumps({'result':result,'state':outcome['state'],
                'case_business_success_verified':outcome['case_business_success_verified'],
                'whole_app_business_accepted':False},sort_keys=True))
            return 0 if outcome['case_business_success_verified'] else 1
    c.read_ref(request_ref);print(json.dumps({'result':result,'whole_app_business_accepted':False},sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
