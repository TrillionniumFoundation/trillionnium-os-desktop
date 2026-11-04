"""One revision08 owned invocation; no same-cell dispatch retry or Main mutation."""
from pathlib import Path
import datetime, hashlib, importlib.util, json, os, re, secrets, stat, subprocess, sys, time, traceback, types
sys.dont_write_bytecode = True
P = Path
SOURCE = 'ffe555f1913e2d3f540ec115298580ddb95849e797926511e13acb0eab126de6'
BUILD = 'e77c1f2b8ff072076a68cd43ea677bc12f8e3c7b80c61e7b614bbffefb257857'
BASE = P('/home/alex/work/pocket4-lmkd-host-pressure-r11-source-08')
ACT = P('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
HELPER = P('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
ACT_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
HELPER_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
QUALIFIER_SHA = '8715fc60396624d8dd8e3c8547ba4eccaee0a70065bdef8016a14e6a6730a8b9'
BINS = {'actor':'4bbf0137a0e8ea089dca4b9e6c2ec800d587e6293fba28eb4ea452d44a898cd9',
        'driver':'a9de6becc67b03ccc877ed54b64ee7c3c1b3398f546fb6464d9b52f707ebe00b',
        'broker':'6ba22d7ba928a2e05dd71e76317252097526672530f43793ad6cdfdb26c93154',
        'android_lmkd':'bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde'}
PROFILES = {'pressure':('p4-lmkd-relay-pressure-r11-02', 'pocket4-lmkd-pressure-r11-coordinator-02'),
            'stale':('p4-lmkd-relay-stale-r11-01', 'pocket4-lmkd-pressure-r11-coordinator-03')}
LIMITS = {'memory.max':'536870912','memory.high':'max','memory.swap.max':'0','cpu.max':'100000 100000','pids.max':'64'}
HARD = 536870912

def need(value, message):
    if not value: raise RuntimeError(message)

def sha(path):
    with P(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

def write(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())

def uint(value, message):
    need(type(value) is str and value.isascii() and value.isdigit(), message)
    return int(value)

def show(unit):
    names = 'Description,InvocationID,LoadState,ActiveState,SubState,Result,ExecMainPID,ExecMainCode,ExecMainStatus,MainPID,ControlGroup,MemoryPeak,MemorySwapPeak,ExecStart,ExecMainStartTimestampMonotonic,ExecMainExitTimestampMonotonic'
    run = subprocess.run(['/usr/bin/systemctl','show',unit,'--property='+names], capture_output=True, text=True, timeout=8)
    need(run.returncode == 0, 'systemctl show failed: '+run.stderr[-1000:])
    return dict(line.split('=',1) for line in run.stdout.splitlines() if '=' in line)

def resource_snapshot(cgroup, invocation):
    fd = os.open(cgroup, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        metadata = os.fstat(fd); held = P('/proc/self/fd') / str(fd)
        limits = {name:(held/name).read_text().strip() for name in LIMITS}
        need(limits == LIMITS, 'first-observed outer limits differ')
        events = {key:int(value) for key,value in (line.split() for line in (held/'memory.events').read_text().splitlines())}
        need(all(events.get(name) == 0 for name in ('max','oom','oom_kill','oom_group_kill')), 'first-observed outer max/OOM nonzero')
        return {'invocation_id':invocation, 'cgroup_device':metadata.st_dev, 'cgroup_inode':metadata.st_ino,
                'observed_monotonic_ns':time.monotonic_ns(), 'limits':limits, 'memory_events':events,
                'memory_current':int((held/'memory.current').read_text()), 'memory_peak':int((held/'memory.peak').read_text()),
                'swap_current':int((held/'memory.swap.current').read_text()), 'swap_peak':int((held/'memory.swap.peak').read_text()),
                'cgroup_events':(held/'cgroup.events').read_text()}
    finally: os.close(fd)

def predecessor(pin):
    need(re.fullmatch('[0-9a-f]{64}', pin) is not None, 'stale requires externally pinned positive result')
    path = P('/home/alex/work/pocket4-lmkd-pressure-r11-coordinator-02/02-pressure-once/result.json')
    need(sha(path) == pin, 'positive predecessor receipt pin changed')
    r = json.loads(path.read_text())
    need(r.get('phase') == 'pressure' and r.get('source_manifest_sha256') == SOURCE and r.get('matching_build_receipt_sha256') == BUILD,
         'positive predecessor source/phase differs')
    need(all(r.get(key) is True for key in ('ok','external_unit_binding_verified','exact_owned_cleanup_verified','main_epoch_unchanged_after_cleanup'))
         and r.get('outcome_unknown') is False and r.get('forced_teardown') is False,
         'positive predecessor normal completion/cleanup missing')
    need(r.get('pressure_qualified') is True or r.get('partial_medium_only') is True, 'positive predecessor rejected/inconclusive')
    return {'path':str(path), 'sha256':pin, 'partial_medium_only':r.get('partial_medium_only',False)}

def bind_terminal(status, first, outer, qualified, unit, invocation):
    identity = {'unit':unit, 'driver_pid':uint(status.get('ExecMainPID',''), 'terminal exact driver PID missing'),
                'cgroup_device':first['cgroup_device'], 'cgroup_inode':first['cgroup_inode']}
    need(qualified.get('outer_identity_for_external_unit_binding') == identity,
         'qualified outer identity does not match first-observed cgroup, unit and terminal ExecMainPID')
    need(first['invocation_id'] == invocation == status.get('InvocationID') and identity['driver_pid'] > 1,
         'first snapshot/terminal driver does not belong to this invocation')
    start_ns = uint(status.get('ExecMainStartTimestampMonotonic',''), 'terminal start monotonic timestamp missing') * 1000
    exit_ns = uint(status.get('ExecMainExitTimestampMonotonic',''), 'terminal exit monotonic timestamp missing') * 1000
    observed_ns = outer['observed_monotonic_ns']
    need(start_ns > 0 and start_ns <= first['observed_monotonic_ns'] <= observed_ns <= exit_ns+999,
         'outer-first/final samples are outside this driver lifetime')
    peak = uint(status.get('MemoryPeak',''), 'terminal MemoryPeak unavailable')
    need(0 < peak < HARD and peak >= outer['memory_peak'] and uint(status.get('MemorySwapPeak',''), 'terminal swap peak unavailable') == 0,
         'terminal memory/swap peak differs or exceeds fixed admission')
    return identity

def main():
    out = state = cgroup = epoch = act = unit = description = None
    invocation = None; validation_ok = False; qualification_code = None; phase = None
    report = {'schema':1, 'ok':False, 'scope':'one owned revision08 PIDFD-only minimal-root phase; no Main deployment',
              'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_manifest_sha256':SOURCE,
              'matching_build_receipt_sha256':BUILD, 'binaries_sha256':BINS, 'dispatch_attempted':False,
              'outcome_unknown':False, 'forced_teardown':False, 'pressure_qualified':False,
              'stale_qualified':False, 'partial_medium_only':False, 'all_apps_production_ready':False}

    def remember(status):
        nonlocal invocation
        current = status.get('InvocationID','')
        need(re.fullmatch('[0-9a-f]{32}', current) is not None and current != '0'*32, 'owned invocation ID missing')
        need(status.get('Description') == description, 'unit description does not match private dispatch nonce')
        need(str(BASE/'target/debug/owned-relay-canary') in status.get('ExecStart','') and str(state) in status.get('ExecStart',''),
             'owned unit executable/state binding differs')
        if invocation is None:
            invocation = current; report['invocation_id'] = current; write(out/'invocation.json', status)
        else: need(current == invocation, 'owned invocation changed')

    try:
        need(len(sys.argv) in (2,3) and sys.argv[1] in PROFILES, 'usage: once.py pressure | stale POSITIVE_RECEIPT_SHA256')
        phase = sys.argv[1]; need(len(sys.argv) == (2 if phase == 'pressure' else 3), 'exact phase argument shape required')
        stem, coordinator = PROFILES[phase]; root = P('/home/alex/work')/coordinator
        state = P('/run')/stem; stage = P('/opt')/stem; unit = stem+'.service'; cgroup = P('/sys/fs/cgroup/system.slice')/unit
        need(os.geteuid() == 0, 'owned systemd invocation requires lifecycle root')
        os.umask(0o077); new_out = root/('02-'+phase+'-once'); new_out.mkdir(mode=0o700); out = new_out
        report.update(phase=phase, unit=unit, coordinator_root=str(root), state=str(state), stage=str(stage))
        write(out/'claim.json', report)
        if phase == 'stale': report['positive_predecessor'] = predecessor(sys.argv[2])
        need(sha(ACT) == ACT_SHA and sha(HELPER) == HELPER_SHA, 'Main epoch helper/activation pin changed')
        act = json.loads(ACT.read_text()); epoch = types.ModuleType('epoch'); epoch.__file__ = str(HELPER)
        exec(compile(HELPER.read_bytes(), str(HELPER), 'exec'), epoch.__dict__)
        epoch.require_unchanged(act['framework_epoch'], action_attempted=False)
        prepared = json.loads((root/'01-prepare/result.json').read_text())
        need(prepared.get('ok') is True and prepared.get('main_epoch_unchanged') is True and prepared.get('phase') == phase
             and prepared.get('unit') == unit and prepared.get('source_manifest_sha256') == SOURCE and prepared.get('matching_build_receipt_sha256') == BUILD,
             'this exact phase has no successful revision08 preparation')
        need(sha(state/'evidence/staging-result.json') == prepared['staging_result_sha256'], 'staging receipt changed')
        need(sha(BASE/'source-manifest.json') == SOURCE and sha(BASE/'build-result.json') == BUILD, 'source/build pin changed')
        manifest = json.loads((BASE/'source-manifest.json').read_text()); need(len(manifest['files']) == 34, 'exact revision08 source count required')
        for name,row in manifest['files'].items():
            path = BASE/name; metadata = path.lstat()
            need(stat.S_ISREG(metadata.st_mode) and metadata.st_size == row['bytes'] and sha(path) == row['sha256'], 'source input changed: '+name)
        for path,role in [(BASE/'target/debug/owned-relay-canary','driver'),(BASE/'target/debug/droidloom-psi-owner','broker'),
                          (BASE/'owned-relay/fixture-init','actor'),(stage/'root/fixture-init','actor'),(stage/'root/system/bin/lmkd','android_lmkd')]:
            need(sha(path) == BINS[role], 'matching executable changed: '+str(path))
        need(show(unit).get('LoadState') == 'not-found' and not cgroup.exists(), 'unit/cgroup must be absent before this single dispatch')
        init = act['framework_epoch']['binding']['processes']['init']['host_pid']
        namespaces = {name:(P('/proc')/str(init)/'ns'/name).stat().st_ino for name in ('pid','mnt','cgroup','ipc','uts','net')}
        available = int(next(line.split()[1] for line in P('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
        need(available > 3*1024**3, 'minimum 3 GiB free host admission failed')
        description = 'p4-owned-r11-rev08-'+phase+'-'+secrets.token_hex(16)
        props = ['Type=exec','RemainAfterExit=yes','Delegate=memory pids cpu','MemoryMax=512M','MemoryHigh=infinity','MemorySwapMax=0',
                 'CPUQuota=100%','CPUQuotaPeriodSec=100ms','TasksMax=64','Nice=10','RuntimeMaxSec=60','TimeoutStopSec=3','KillMode=control-group',
                 'LimitCORE=0','LimitNOFILE=4096','LimitFSIZE=1048576','RestrictRealtime=yes','UMask=0022','StandardInput=null',
                 'Description='+description,'StandardOutput=append:'+str(state/'unit.stdout'),'StandardError=append:'+str(state/'unit.stderr')]
        argv = ['/usr/bin/systemd-run','--unit='+unit,'--no-block','--quiet']+['--property='+value for value in props]+[
                str(BASE/'target/debug/owned-relay-canary'),phase,str(stage/'root'),str(state),unit,BINS['actor'],BINS['android_lmkd'],
                str(BASE/'target/debug/droidloom-psi-owner'),BINS['broker']]+[str(value) for value in namespaces.values()]
        write(out/'dispatch-attempt.json', {'argv':argv,'description':description,'main_namespaces':namespaces,'main_epoch_sha256':act['framework_epoch']['sha256']})
        report.update(dispatch_attempted=True, outcome_unknown=True, description=description, main_namespaces=namespaces,
                      main_epoch_sha256=act['framework_epoch']['sha256'], available_memory_bytes=available)
        run = subprocess.run(argv, capture_output=True, text=True, timeout=12)
        report.update(dispatch_returncode=run.returncode, dispatch_stdout=run.stdout, dispatch_stderr=run.stderr)
        need(run.returncode == 0, 'systemd dispatch failed; reconcile this attempt without redispatch')
        deadline = time.monotonic()+72
        while time.monotonic() < deadline:
            status = show(unit); current = status.get('InvocationID','')
            if re.fullmatch('[0-9a-f]{32}', current): remember(status)
            elif invocation is not None: raise RuntimeError('recorded owned invocation disappeared before terminal receipt')
            if invocation and 'resources_first_observed' not in report and cgroup.is_dir():
                first = resource_snapshot(cgroup, invocation)
                report['resources_first_observed'] = first; write(out/'outer-first.json', first)
            if invocation and status.get('SubState') in ('exited','failed','dead'): break
            time.sleep(0.25)
        else: raise RuntimeError('owned phase deadline; no second dispatch')
        report.update(terminal_status=status, outcome_unknown=False)
        need(invocation is not None and status.get('Result') == 'success' and status.get('ExecMainCode') == '1' and
             status.get('ExecMainStatus') == '0' and status.get('ActiveState') == 'active' and status.get('SubState') == 'exited',
             'owned unit did not exit normally with its retained successful invocation')
        need('resources_first_observed' in report, 'no external first-observed cgroup identity; reject instead of opening deleted cgroup')
        terminal_peak = uint(status.get('MemoryPeak',''), 'terminal MemoryPeak unavailable')
        need(0 < terminal_peak < HARD and uint(status.get('MemorySwapPeak',''), 'terminal swap peak unavailable') == 0,
             'terminal unit resource peaks exceed fixed admission')
        qualifier = BASE/'owned-relay/qualify_pressure.py'; need(sha(qualifier) == QUALIFIER_SHA, 'revision08 qualifier changed')
        spec = importlib.util.spec_from_file_location('pinned_pressure_qualifier', qualifier)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        files = []
        for name in sorted(module.required_names(phase)):
            path = state/'evidence'/name; metadata = path.lstat()
            need(stat.S_ISREG(metadata.st_mode) and 0 < metadata.st_size <= 1048576, 'required evidence not a bounded regular file: '+name)
            files.append({'name':name,'sha256':sha(path),'bytes':metadata.st_size})
        inputs = {'schema':1,'phase':phase,'source_manifest_sha256':SOURCE,'matching_build_receipt_sha256':BUILD,'binaries_sha256':BINS,'files':files}
        input_path = state/'evidence/qualification-inputs.json'; write(input_path, inputs); report['evidence_manifest_sha256'] = sha(input_path)
        q = subprocess.run(['/usr/bin/python3','-I',str(qualifier),'--evidence-dir',str(state/'evidence'),
                            '--manifest-sha256',sha(input_path),'--source-manifest-sha256',SOURCE,'--phase',phase], capture_output=True, text=True, timeout=10)
        write(out/'qualification.stdout', q.stdout.encode()); write(out/'qualification.stderr', q.stderr.encode())
        qualified = json.loads(q.stdout); report.update(qualification_returncode=q.returncode, qualification=qualified)
        need((q.returncode == 0 and qualified.get('qualification_status') == 'pass') or
             (phase == 'pressure' and q.returncode == 2 and qualified.get('qualification_status') == 'partial_medium_only'),
             'scoped qualifier rejected or was inconclusive')
        first = report['resources_first_observed']; outer = json.loads((state/'evidence/outer-final.json').read_text())
        expected_identity = bind_terminal(status, first, outer, qualified, unit, invocation)
        report.update(external_unit_binding_verified=True, outer_identity_bound=expected_identity,
                      resources_retained_before_driver_exit=outer, terminal_peaks_verified=True)
        for name,row in manifest['files'].items(): need(sha(BASE/name) == row['sha256'], 'source changed after owned phase: '+name)
        for path,role in [(BASE/'target/debug/owned-relay-canary','driver'),(BASE/'target/debug/droidloom-psi-owner','broker'),(BASE/'owned-relay/fixture-init','actor')]:
            need(sha(path) == BINS[role], 'matching executable changed after owned phase: '+role)
        epoch.require_unchanged(act['framework_epoch'], action_attempted=False)
        report['main_epoch_unchanged'] = True; validation_ok = True; qualification_code = q.returncode
    except Exception as error:
        report.update(error=type(error).__name__+': '+str(error), traceback=traceback.format_exc())
    finally:
        # Reconcile a timed-out dispatch by its private description and exact
        # invocation; never issue another systemd-run or stop a different owner.
        if report['dispatch_attempted']:
            try:
                current = show(unit)
                if current.get('LoadState') == 'not-found' and not cgroup.exists():
                    report['owned_scope_absent_after_dispatch'] = True
                    need(invocation is not None, 'dispatch history unresolved although owned scope is now absent')
                    report['exact_owned_cleanup_verified'] = True
                    report['post_stop_status'] = current; report['owned_cgroup_after_stop'] = 'absent'
                else:
                    remember(current)
                    report['pre_stop_status'] = current
                    report['forced_teardown'] = current.get('SubState') not in ('exited','failed','dead')
                    stop = subprocess.run(['/usr/bin/systemctl','stop',unit], capture_output=True, text=True, timeout=12)
                    report.update(stop_returncode=stop.returncode, stop_stdout=stop.stdout, stop_stderr=stop.stderr)
                    need(stop.returncode == 0, 'exact owned unit stop failed')
                    reset_done = False; limit = time.monotonic()+8
                    while time.monotonic() < limit:
                        after = show(unit)
                        if after.get('LoadState') == 'not-found' and after.get('MainPID','0') == '0' and not cgroup.exists(): break
                        need(after.get('Description') == description and after.get('InvocationID','') in ('',invocation), 'unit owner changed during cleanup')
                        if after.get('ActiveState') == 'failed' and after.get('MainPID') == '0' and not reset_done:
                            reset = subprocess.run(['/usr/bin/systemctl','reset-failed',unit], capture_output=True, text=True, timeout=8)
                            report.update(reset_failed_returncode=reset.returncode, reset_failed_stdout=reset.stdout, reset_failed_stderr=reset.stderr)
                            need(reset.returncode == 0, 'exact failed-unit record cleanup failed'); reset_done = True
                        time.sleep(0.1)
                    else: raise RuntimeError('exact owned unit/cgroup did not disappear after stop')
                    report.update(post_stop_status=after, owned_cgroup_after_stop='absent', exact_owned_cleanup_verified=True, outcome_unknown=False)
            except Exception as error:
                report.update(cleanup_error=type(error).__name__+': '+str(error), cleanup_traceback=traceback.format_exc())
        if epoch is not None and act is not None:
            try:
                epoch.require_unchanged(act['framework_epoch'], action_attempted=False)
                report['main_epoch_unchanged_after_cleanup'] = True
            except Exception as error:
                report.update(main_fence_error=type(error).__name__+': '+str(error), main_fence_traceback=traceback.format_exc())
        if state is not None and state.is_dir():
            retained = {}
            for path in sorted((state/'evidence').glob('*')):
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= 1048576:
                    retained[path.name] = {'sha256':sha(path),'bytes':path.stat().st_size}
            report['retained_files'] = retained
            for name in ['driver-result.json','phase-result.json','broker-pressure-audit.json','pressure-workload.json','target-cleanup.json','outer-final.json']:
                path = state/'evidence'/name
                if path.is_file() and not path.is_symlink():
                    try: report[name] = json.loads(path.read_text())
                    except Exception as error: report[name+'-parse-error'] = repr(error)
            for name in ('unit.stdout','unit.stderr'):
                path = state/name
                if path.is_file() and not path.is_symlink(): report[name] = path.read_text(errors='replace')[-14000:]
        complete = (validation_ok and report.get('exact_owned_cleanup_verified') is True and
                    report.get('main_epoch_unchanged_after_cleanup') is True and report['outcome_unknown'] is False and
                    report['forced_teardown'] is False and 'cleanup_error' not in report and 'main_fence_error' not in report)
        report.update(ok=complete, pressure_qualified=complete and phase == 'pressure' and qualification_code == 0,
                      stale_qualified=complete and phase == 'stale' and qualification_code == 0,
                      partial_medium_only=complete and phase == 'pressure' and qualification_code == 2,
                      finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        if out is not None: write(out/'result.json', report)
        print(json.dumps({'report':str(out/'result.json') if out is not None else None, 'sha256':sha(out/'result.json') if out is not None else None,
                          **{key:report.get(key) for key in ('ok','phase','pressure_qualified','stale_qualified','partial_medium_only','qualification',
                              'error','cleanup_error','exact_owned_cleanup_verified','main_epoch_unchanged_after_cleanup','invocation_id','outcome_unknown')}}), flush=True)
    return 0 if report['ok'] else 1

if __name__ == '__main__': sys.exit(main())
