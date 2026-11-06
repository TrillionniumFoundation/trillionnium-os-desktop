#!/usr/bin/env python3
"""Read exact current cell roles and bounded native service logs after repair.
No namespace entry, Android command, signal, install or guard publication.
"""
import base64, hashlib, json, os, time, types, zlib
from pathlib import Path

SOURCE='/home/alex/work/pocket4-cell-recovery-preflight-20261106-r1/source'
MANIFEST='b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f'
REPAIR='/home/alex/work/pocket4-orphan-cell-retirement-20261106-r1'

def main():
    assert os.getuid()==os.geteuid()==0
    pins=json.loads(Path(SOURCE+'/SOURCE_PINS.json').read_bytes())
    assert hashlib.sha256(Path(SOURCE+'/SOURCE_PINS.json').read_bytes()).hexdigest()==MANIFEST
    raw=Path(SOURCE+'/successor_runtime.py').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==pins['files']['successor_runtime.py']['sha256']
    core=types.ModuleType('exact_post_retirement_diagnostic');core.__file__=SOURCE+'/successor_runtime.py'
    exec(compile(raw,core.__file__,'exec'),core.__dict__);core.configure(SOURCE,MANIFEST)
    repair=json.loads(core.pinned_record({'path':REPAIR+'/result.json','bytes':3043,'sha256':'4c322a72ea61f3e7ff7e9c369c7996256beed8c74be1cd8c4b10524da285008d'}))
    assert repair['ok'] is True and repair['outcome_unknown'] is False and repair['old_namespace_members_after']==[]
    lineage=core.parse(core.host_read(REPAIR+'/lineage.stdout.raw.json',65536,'106e92009c87248f9a078ac454b6c2883121fc41297483cd9dba3cf88e83c867')[0])
    checkpoint=core.parse(core.host_read(REPAIR+'/checkpoint.private.json',262144)[0])
    expected=checkpoint['expected_processes'];init=expected['new_init'];owner=expected['new_launcher']
    pool=core.FDs();observations=[];error=None
    try:
        for label in ('new_init','new_launcher','daemon','presenter'):
            row=expected[label]
            assert core.E.process_identity(row['host_pid'])==row
            fd=pool.own(os.pidfd_open(row['host_pid'],0));assert not core.pidfd_dead(fd)
        for sample in range(2):
            rows=[];end=time.monotonic()+8
            for name in os.listdir('/proc'):
                assert time.monotonic()<end
                if not name.isdecimal() or not core.cgroup_member(int(name)):continue
                try:
                    ns=os.readlink('/proc/'+name+'/ns/pid')
                    if ns!=init['namespaces']['pid']:continue
                    exe=os.readlink('/proc/'+name+'/exe')
                    argv=core.host_pseudo('/proc/'+name+'/cmdline',8192)
                    interesting=exe in ('/system/bin/init','/system/bin/app_process64','/system/bin/surfaceflinger',core.COMPOSER_EXE) or any(x in argv for x in (b'zygote',b'system_server',b'crash_dump',b'artd'))
                    if interesting:
                        row=core.E.process_identity(int(name));row['state']=core.E._stat(int(name))[3];rows.append(row)
                except (FileNotFoundError,ProcessLookupError,core.E.EpochError):continue
            observations.append({'monotonic_ns':time.monotonic_ns(),'same_exact_init':core.E.process_identity(init['host_pid'])==init,'roles':rows})
            if sample==0:time.sleep(2)
        journal,err,command=core.bounded_child(['/usr/bin/journalctl','--unit=droidloomd.service','--since=2026-11-06 11:36:00 UTC','--lines=180','--no-pager','--output=short-iso'],15,limit=196608)
        for label in ('new_init','new_launcher','daemon','presenter'):assert core.E.process_identity(expected[label]['host_pid'])==expected[label]
        out={'schema':'pocket4-exact-cell-after-retirement-observation-v1','observations':observations,
            'native_service_journal':{'bytes':len(journal),'sha256':hashlib.sha256(journal).hexdigest(),'zlib_base64':base64.b64encode(zlib.compress(journal)).decode(),'stderr':err.decode('utf-8','replace'),'command':command},
            'expected_current_owner':owner,'expected_current_init':init,'identity_qualified':False,'guard_publication':False,
            'signals':0,'restarts':0,'Android_commands':0,'namespace_entries':0,'UI_actions':0,'installs':0}
    finally:
        pool.close_all()
    out['observation_fds']=pool.summary();print(json.dumps(out,sort_keys=True,separators=(',',':')),flush=True)

if __name__=='__main__':main()
