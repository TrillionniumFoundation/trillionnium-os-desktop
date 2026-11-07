#!/usr/bin/env python3
"""Run a bounded ART-order fixture; not a complete ART TU or owner qualification."""
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import tomllib
import tarfile
from pathlib import PurePosixPath

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def identity(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def held(path, maximum=4*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected file type/size: '+str(path))
        parts = []
        total = 0
        while total <= maximum:
            chunk = os.read(fd, min(65536, maximum+1-total))
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
        data = b''.join(parts)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()), 'source changed during read: '+str(path))
        return data, {'path': str(path), 'bytes': total, 'sha256': sha(data), 'identity': identity(before)}
    finally:
        os.close(fd)

def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data, bytes):
        data = (json.dumps(data, indent=2, sort_keys=True)+'\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}

def real_directory(path):
    for item in (path, *path.parents):
        require(stat.S_ISDIR(item.lstat().st_mode), 'directory alias rejected: '+str(item))

def children():
    return [int(x) for x in Path('/proc/self/task/%d/children' % os.getpid()).read_text().split()]

def cleanup_children():
    initial = children()
    errors = []
    reaped = []
    deadline = time.monotonic()+8
    while children() and time.monotonic() < deadline:
        for pid in children():
            try:
                got, status = os.waitpid(pid, os.WNOHANG)
                if got:
                    reaped.append({'pid': got, 'status': status})
                    continue
                fd = os.pidfd_open(pid, 0)
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)
            except ChildProcessError:
                continue
            except ProcessLookupError:
                continue
            except Exception as error:
                errors.append(repr(error))
        time.sleep(0.02)
    remaining = children()
    return {'initial_owned_children': initial, 'forced_cleanup': bool(initial), 'reaped': reaped, 'remaining': remaining, 'errors': errors}

def command(argv, cwd, env, label, records, maximum_seconds=180):
    require(not children(), 'unreaped child before command')
    maximum_seconds = min(maximum_seconds, DEADLINE-time.monotonic())
    require(maximum_seconds > 0, 'owned overall deadline exhausted')
    stdout = OUT/(label+'.stdout')
    stderr = OUT/(label+'.stderr')
    started = utc()
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True)
        timeout = False
        try:
            code = proc.wait(timeout=maximum_seconds)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                code = proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                code = proc.wait(timeout=3)
    output, outrow = held(stdout, 32*1024*1024)
    _, errrow = held(stderr, 4*1024*1024)
    row = {'argv': [str(x) for x in argv], 'cwd': str(cwd), 'label': label,
           'started_utc': started, 'finished_utc': utc(), 'returncode': code,
           'timed_out': timeout, 'stdout': outrow, 'stderr': errrow}
    records.append(row)
    require(code == 0 and not timeout, 'command failed: '+label)
    require(not children(), 'command left owned children: '+label)
    return output

def resource_text(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        raw = os.read(fd, 32769)
        require(len(raw) <= 32768, 'owned resource observation exceeds bound')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)

def resource_events(text):
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows), 'malformed owned memory.events')
    events = {row[0]:int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(k in events for k in ['oom','oom_kill','oom_group_kill']), 'incomplete or duplicate owned memory.events')
    return events

def resource_snapshot(directory_fd, membership):
    observed = Path('/proc/self/cgroup').read_text().strip()
    require(observed == membership, 'controller cgroup membership changed')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    held_st = os.fstat(directory_fd)
    named_st = path.lstat()
    require(stat.S_ISDIR(held_st.st_mode) and stat.S_ISDIR(named_st.st_mode) and
            (held_st.st_dev,held_st.st_ino) == (named_st.st_dev,named_st.st_ino), 'owned invocation cgroup identity changed')
    fields = {name:resource_text(directory_fd,name) for name in [
        'cgroup.procs','memory.events','memory.current','memory.peak','memory.high','memory.max',
        'memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max']}
    require(str(os.getpid()) in fields['cgroup.procs'].split(), 'controller is not in the held invocation')
    require(fields['memory.max'] == '1073741824' and fields['cpu.max'] == '100000 100000', 'owned resource limits do not match the request')
    for key in ['memory.current','memory.peak','memory.swap.current','memory.swap.peak']:
        require(fields[key].isdigit(), 'invalid owned resource counter: '+key)
    return {'observed_utc':utc(), 'membership':membership, 'path':str(path),
            'directory_identity':[held_st.st_dev,held_st.st_ino],
            'controller_pid':os.getpid(), 'fields':fields, 'events':resource_events(fields['memory.events'])}

def begin_resources():
    membership = Path('/proc/self/cgroup').read_text().strip()
    require('\n' not in membership and membership.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'), 'not the exact owned user invocation')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    require(path.name.startswith('hepta-runtime-job-') and path.name.endswith('.service') and '..' not in path.parts, 'unexpected owned unit path')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = resource_snapshot(fd,membership)
        require(all(before['events'][k] == 0 for k in ['oom','oom_kill','oom_group_kill']), 'owned invocation already recorded OOM before the control')
        return fd,before
    except BaseException:
        os.close(fd)
        raise

def finish_resources(directory_fd, before, report):
    after = resource_snapshot(directory_fd,before['membership'])
    report['owned_resources_after'] = after
    report['owned_memory_peak'] = int(after['fields']['memory.peak'])
    report['owned_memory_swap_peak'] = int(after['fields']['memory.swap.peak'])
    require(after['directory_identity'] == before['directory_identity'], 'owned cgroup object replaced')
    require(set(before['events']) == set(after['events']), 'owned memory event fields changed')
    delta = {key:after['events'][key]-value for key,value in before['events'].items()}
    report['owned_memory_events_delta'] = delta
    require(all(value >= 0 for value in delta.values()), 'owned memory event counters went backwards')
    require(all(delta[key] == 0 for key in ['oom','oom_kill','oom_group_kill']), 'owned OOM event occurred; control is not qualified')
    require(all(before['fields'][key] == after['fields'][key] for key in ['memory.max','memory.high','memory.swap.max','cpu.max']), 'owned cgroup limits changed during control')
    return {'pass':True, 'before':before, 'after':after, 'memory_events_delta':delta,
            'memory_peak':int(after['fields']['memory.peak']), 'memory_swap_peak':int(after['fields']['memory.swap.peak']),
            'resource_settings_changed':False, 'swap_max_observed_only':after['fields']['memory.swap.max']}

ROOT = Path('/home/alex/work/pocket4-art-prefork-quiesce-order-control-01-20261105')
HERE = ROOT/'source'
OUT = ROOT/'attempt01'
DEADLINE = None
OBSERVED_SIGNALS = []
INPUTS = {'preimage-runtime.cc': {'bytes': 147701, 'sha256': '5b10319787af6fbcee27e6bac3e1a7637f18392e669bb52cd04db831ebe3a083'}, 'candidate-runtime.cc': {'bytes': 148153, 'sha256': 'ec7105503380ec505dbe58b822a4ac46edb48311e6093eb3e396d0768e111bc3'}, 'bridge-full.cc': {'bytes': 24851, 'sha256': '4fc33d917915886fccabaf76dbf7a6bee949cf08cd6b8ac9be429dc8614706a4'}, 'art-interface-full.cc': {'bytes': 5919, 'sha256': 'd71e569e0f782ed461bdc167c6228e35414a02b209072b8cba9b7534bc8b3a5a'}, 'lifecycle_fixture.cc': {'bytes': 6544, 'sha256': 'bf166ce963e4fa2a9f43df5d4d4b99d71a4c3421277131b44c6655c50a212389'}}

def function(text, signature):
    require(text.count(signature) == 1, 'function signature is absent or ambiguous: '+signature)
    start = text.index(signature)
    masked = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda match: ''.join('\n' if c == '\n' else ' ' for c in match.group()),
                    text, flags=re.S)
    opening = masked.index('{', start)
    depth = 0
    for end in range(opening, len(masked)):
        if masked[end] == '{':
            depth += 1
        elif masked[end] == '}':
            depth -= 1
            if depth == 0:
                return text[start:end+1]+'\n'
    raise RuntimeError('function body not closed')


def run_case(binary, argument, expected_code, expected_events, label, report):
    require(not children(), 'owned child before case')
    stdout = OUT/(label+'.stdout')
    stderr = OUT/(label+'.stderr')
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen([str(binary), argument], cwd=OUT,
                                env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C'},
                                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                start_new_session=True)
        timeout = False
        try:
            code = proc.wait(timeout=min(12, DEADLINE-time.monotonic()))
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait(timeout=3)
    data, outpin = held(stdout, 65536)
    _, errpin = held(stderr, 65536)
    lines = data.decode().splitlines()
    events = [line[6:] for line in lines if line.startswith('EVENT ')]
    fatals = [line for line in lines if line.startswith('FATAL ')]
    row = {'label':label, 'argv':[str(binary),argument], 'returncode':code,
           'timed_out':timeout, 'stdout':outpin, 'stderr':errpin,
           'events':events, 'fatal_records':fatals, 'direct_child_reaped':True,
           'remaining_owned_children':children(), 'expected_code':expected_code,
           'pass':False}
    report['cases'].append(row)
    require(not timeout and code == expected_code and not row['remaining_owned_children'],
            'owned case exit/reaping differs: '+label)
    require(events == expected_events, 'actual extracted call order differs: '+label)
    if expected_code == 70:
        require(fatals == ['FATAL kernel-single-thread-wait reads=2001 callbacks=0 quiesces=0'],
                'baseline did not reach the actual bounded wait failure')
    elif expected_code == 71:
        require(fatals == ['FATAL bridge-quiesce-rejected reads=0 callbacks=1 quiesces=1'],
                'rejected quiesce was not fatal before the actual kernel wait')
    else:
        require(not fatals, 'unexpected fatal record')
    row['pass'] = True


def execute():
    global DEADLINE
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE/'run_control.py', 'exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    DEADLINE = time.monotonic()+100
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36,1,0,0,0) == 0, 'cannot establish owned subreaper')
    require(not children(), 'unexpected initial owned child')
    report = {'schema':1,'state':'RUNNING','started_utc':utc(),
              'scope':'exact three extracted ART/NativeBridge functions with real owned kernel threads and explicit peripheral fixtures',
              'complete_ART_translation_unit':False, 'production_raw_owner':False,
              'installed_ART_binding':False, 'Android_execution':False, 'Main_actions':0,
              'commands':[], 'cases':[]}
    source_rows = {}
    tool_rows = {}
    resource_fd = -1
    before = None
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned signal '+str(number))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        resource_fd, before = begin_resources()
        report['owned_resources_before'] = before
        sources = {}
        for name, expected in INPUTS.items():
            raw, row = held(HERE/name, 524288)
            require(row['sha256'] == expected['sha256'] and row['bytes'] == expected['bytes'],
                    'frozen source mismatch: '+name)
            source_rows[name] = row
            sources[name] = raw.decode()
        for name in ['/usr/bin/g++','/usr/bin/ld','/usr/bin/as']:
            path = Path(name).resolve(strict=True)
            require(path.is_relative_to('/usr/bin') or path.is_relative_to('/usr/lib'),
                    'compiler tool resolved outside installed system roots')
            _, row = held(path, 128*1024*1024)
            tool_rows[name] = {'resolved':str(path), **row}
        env = {'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C','TMPDIR':str(OUT)}
        command(['/usr/bin/g++','--version'], OUT, env, 'compiler-version', report['commands'], 5)
        wait = function(sources['preimage-runtime.cc'], 'static void WaitUntilSingleThreaded() {')
        require(wait == function(sources['candidate-runtime.cc'], 'static void WaitUntilSingleThreaded() {'),
                'actual wait body changed')
        bridge = function(sources['bridge-full.cc'], 'void PreZygoteForkNativeBridge() {')
        wrapper = function(sources['art-interface-full.cc'], 'void PreZygoteForkNativeBridge() {')
        report['extracted_sources'] = {'wait_sha256':sha(wait.encode()),
                                      'native_bridge_hook_sha256':sha(bridge.encode()),
                                      'art_wrapper_sha256':sha(wrapper.encode())}
        binaries = {}
        for arm, name, flag in [('preimage1','preimage-runtime.cc',1),
                                ('candidate1','candidate-runtime.cc',1),
                                ('candidate0','candidate-runtime.cc',0)]:
            directory = OUT/arm
            directory.mkdir(mode=0o700)
            body = function(sources[name], 'void Runtime::PreZygoteFork() {')
            for filename, text in [('art_wait.inc',wait),('art_prefork.inc',body),
                                   ('native_bridge_prefork.inc',bridge),('art_bridge_wrapper.inc',wrapper)]:
                write_new(directory/filename,text.encode())
            binary = directory/'order-control'
            argv = ['/usr/bin/g++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-pthread',
                    '-DDROIDLOOM_NATIVE_GENERATION_RUNTIME='+str(flag),'-I'+str(directory),
                    str(HERE/'lifecycle_fixture.cc'),'-o',str(binary)]
            command(argv, OUT, env, 'compile-'+arm, report['commands'], 20)
            raw, row = held(binary, 4*1024*1024)
            require(raw.startswith(b'\x7fELF'), 'compiled control is not ELF')
            binaries[arm] = (binary,row)
        run_case(binaries['preimage1'][0], 'worker', 70,
                 ['worker-ready','jit-prefork','art-threadlist-wait','kernel-wait-first-read'],
                 'baseline-owner-prevents-kernel-wait', report)
        run_case(binaries['candidate1'][0], 'worker', 0,
                 ['worker-ready','jit-prefork','legacy-guest-log-close','quiesce-enter',
                  'quiesce-complete','art-threadlist-wait','kernel-wait-first-read','heap-prefork','returned'],
                 'enabled-quiesce-precedes-kernel-wait', report)
        run_case(binaries['candidate0'][0], 'no-worker', 0,
                 ['jit-prefork','art-threadlist-wait','kernel-wait-first-read','heap-prefork',
                  'legacy-guest-log-close','generation-disabled','returned'],
                 'disabled-original-call-order', report)
        run_case(binaries['candidate1'][0], 'reject-stop', 71,
                 ['worker-ready','jit-prefork','legacy-guest-log-close','quiesce-enter'],
                 'enabled-stop-rejection-remains-fatal', report)
        require(all(held(path,4*1024*1024)[1] == row for path,row in binaries.values()),
                'control ELF changed during run')
        report['ELFs'] = {arm:row for arm,(_,row) in binaries.items()}
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__, 'message':str(error),
                                  'errno':getattr(error,'errno',None), 'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup'] = cleanup_children()
        changes = []
        for name,row in source_rows.items():
            try:
                if held(HERE/name,524288)[1] != row: changes.append(name)
            except Exception as error:
                changes.append({'source':name,'error':repr(error)})
        for name,row in tool_rows.items():
            try:
                path = Path(name).resolve(strict=True)
                if str(path) != row['resolved'] or held(path,128*1024*1024)[1] != {k:v for k,v in row.items() if k != 'resolved'}:
                    changes.append(name)
            except Exception as error:
                changes.append({'tool':name,'error':repr(error)})
        report['source_and_compiler_changes'] = changes
        report['observed_signals'] = OBSERVED_SIGNALS
        try:
            require(before is not None and resource_fd >= 0, 'owned resource admission missing')
            report['owned_resource_gate'] = finish_resources(resource_fd,before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            report['state'] = 'FAIL'
        finally:
            if resource_fd >= 0: os.close(resource_fd)
        cleanup = report['cleanup']
        if changes or cleanup['forced_cleanup'] or cleanup['remaining'] or cleanup['errors']:
            report['state'] = 'FAIL'
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json',report)
        print(json.dumps({'state':report['state'],'result':result,'complete_ART_TU':False,'Main_actions':0}),flush=True)
    return 0 if report['state'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'owned_cases':4,'full_ART_TU':False,
                          'actual_kernel_wait':True,'peripheral_ART_and_owner_actions':'explicit fixtures',
                          'requires_explicit_execute_once':True,'Main_actions':0}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: run_control.py [--execute-once]')
