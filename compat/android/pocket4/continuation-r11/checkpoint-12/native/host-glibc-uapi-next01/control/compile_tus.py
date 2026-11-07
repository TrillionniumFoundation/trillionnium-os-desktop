#!/usr/bin/env python3
"""Compile complete proc-maps translation units with the actual failed Soong host argv."""
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

def hash_held(path, maximum=512*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected held file type/size: '+str(path))
        digest = hashlib.sha256()
        total = 0
        while True:
            raw = os.read(fd,65536)
            if not raw:
                break
            total += len(raw)
            require(total <= maximum, 'held file grew beyond bound: '+str(path))
            digest.update(raw)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held file changed: '+str(path))
        return {'path':str(path),'bytes':total,'sha256':digest.hexdigest(),'identity':identity(before)}
    finally:
        os.close(fd)

ROOT = Path('/home/alex/work/pocket4-native-host-glibc-uapi-tu-control-01-20261105')
HERE = ROOT/'source'
OUT = ROOT/'attempt01'
AOSP = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
DEADLINE = None
OBSERVED_SIGNALS = []

def pinned(name, expected, maximum=4*1024*1024):
    raw, row = held(HERE/name, maximum)
    require(row['sha256'] == expected, 'frozen input differs: '+name)
    return raw, row


def source_pins():
    raw, _ = held(HERE/'INPUT_PINS.json', 131072)
    expected = json.loads(raw)
    result = {}
    for name, wanted in expected.items():
        require('..' not in Path(name).parts and not Path(name).is_absolute(), 'unsafe input path')
        row = hash_held(HERE/name, 4*1024*1024)
        require(row['sha256'] == wanted['sha256'] and row['bytes'] == wanted['bytes'],
                'complete staged input mismatch: '+name)
        result[name] = row
    return result


def current_header_authority(authority):
    result = {}
    require(len(authority['files']) == 16 and authority['all_fixed_observations_complete'] is True,
            'actual UAPI observation incomplete')
    for item in authority['files']:
        relative = item['relative']
        require('..' not in Path(relative).parts and not Path(relative).is_absolute(), 'unsafe UAPI path')
        path = AOSP/relative
        if item['complete']:
            row = hash_held(path, 131072)
            require(row['sha256'] == item['sha256'] and row['bytes'] == item['bytes'],
                    'observed UAPI source changed: '+relative)
            result[relative] = row
        else:
            require(item['error']['errno'] == 2, 'unqualified missing-header observation')
            try:
                path.lstat()
            except FileNotFoundError:
                result[relative] = {'absent':True}
            else:
                raise RuntimeError('observed missing fixed header appeared: '+relative)
    return result


def argv_for(original, source, include, output, mode='compile'):
    args = list(original)
    require(args[-1] == 'frameworks/libs/binary_translation/kernel_api/proc_maps_provenance.cc',
            'original source selector differs')
    require(args.count('-c') == args.count('-MD') == args.count('-MF') == args.count('-o') == 1,
            'original compiler phase/output options are not singular')
    args[-1] = str(source)
    args[args.index('-MF')+1] = str(output)+'.d'
    args[args.index('-o')+1] = str(output)
    # Only the actual candidate-private headers are overlaid. Every original
    # sysroot, system/project include, warning, target and macro stays present.
    args.insert(1, '-I'+str(include))
    if mode in ('dependencies','macros'):
        args[args.index('-c')] = '-M' if mode == 'dependencies' else '-E'
        args.remove('-MD')
        index = args.index('-o')
        del args[index:index+2]
        if mode == 'macros':
            index = args.index('-MF')
            del args[index:index+2]
            args.insert(1,'-dM')
    return args


def dependency_files(path):
    import shlex
    raw, _ = held(path, 1048576)
    text = raw.decode().replace(chr(92)+chr(10),' ')
    require(':' in text, 'dependency output has no target')
    names = shlex.split(text.split(':',1)[1])
    require(0 < len(names) <= 2048, 'dependency set outside bound')
    result = {}
    for name in names:
        source = Path(name)
        if not source.is_absolute():
            source = AOSP/source
        source = source.resolve(strict=True)
        require(source.is_relative_to(AOSP) or source.is_relative_to(HERE),
                'compiler dependency escaped observed AOSP and owned candidate')
        result[str(source)] = hash_held(source, 16*1024*1024)
    return result


def execute():
    global DEADLINE
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator required')
    require(Path(__file__).absolute() == HERE/'compile_tus.py', 'exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'fresh compile output already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    DEADLINE = time.monotonic()+160
    libc = ctypes.CDLL(None,use_errno=True)
    require(libc.prctl(36,1,0,0,0) == 0, 'owned subreaper setup failed')
    require(not children(), 'unexpected owned initial child')
    report = {'schema':1,'state':'RUNNING','started_utc':utc(),'commands':[],
              'scope':'original Soong host sysroot and warning flags; five complete candidate proc-maps TUs',
              'full_engine_built':False,'objects_executed':False,'installed':False,'Main_actions':0,
              'kernel_ABI_compatibility_runtime_not_claimed_by_compilation':True,
              'sources_modified_outside_owned_root':False,'baseline_reproduced':False,
              'actual_system_and_generated_dependencies':{},'compiled_TUs':[]}
    source_before = {}; header_before = {}; compiler_before = None
    resource_fd = -1; resource_before = None; authority = None
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned compile interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    try:
        resource_fd,resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        source_before = source_pins()
        data,_ = pinned('references/inputs.json','8206e05341acd16dccf6d5b0e8e3ad63d83ebc095842f5efbfea1dfdb7105b4d')
        inputs = json.loads(data)
        data,_ = pinned('references/uapi-header-observation.json','7009a70300587706ff78df67b7fb472ce89f7a43538331f00662500505db64ca')
        authority = json.loads(data)
        header_before = current_header_authority(authority)
        command_raw,_ = held(HERE/'original-failed-command.json',65536)
        original = json.loads(command_raw)
        require(original['inputs_sha256'] == '8206e05341acd16dccf6d5b0e8e3ad63d83ebc095842f5efbfea1dfdb7105b4d' and
                original['cwd'] == str(AOSP) and original['env_assignment'] == {'PWD':'/proc/self/cwd'},
                'original failed command authority changed')
        argv = original['argv']
        require(argv[0] == 'prebuilts/clang/host/linux-x86/clang-r584948b/bin/clang++', 'wrong compiler entry')
        compiler_path = (AOSP/argv[0]).resolve(strict=True)
        require(compiler_path.is_relative_to(AOSP/'prebuilts/clang/host/linux-x86/clang-r584948b'),
                'compiler entry resolves outside the pinned compiler project')
        compiler_before = hash_held(compiler_path)
        require(compiler_before['sha256'] == inputs['compiler_entry_sha256'] == original['compiler_entry_sha256'],
                'actual compiler bytes differ from the failed build')
        report['compiler'] = compiler_before
        for name,row in source_before.items():
            if name.startswith('preimage/'):
                relative = name[len('preimage/'):]
                require(inputs['effective_teto_files'].get(relative) == row['sha256'],
                        'preimage is not the actual failed effective source: '+relative)
        env = {'PATH':'/usr/bin:/bin','PWD':'/proc/self/cwd','LANG':'C','LC_ALL':'C','TMPDIR':str(OUT)}
        command([argv[0],'--version'],AOSP,env,'compiler-version',report['commands'],10)
        # Observe actual compiler-resolved macros, not guesses from one missing
        # fixed asm/bits path in a multiarch sysroot.
        macro_source = OUT/'host-macros.cc'
        write_new(macro_source,b'#include <fcntl.h>\n#include <sys/syscall.h>\n#include <sys/ioctl.h>\n#include <linux/magic.h>\n')
        macro_args = argv_for(argv,macro_source,HERE/'preimage/kernel_api/include',OUT/'host-macros','macros')
        macros = command(macro_args,AOSP,env,'host-macros',report['commands'],20).decode()
        wanted = ['SYS_memfd_create','SYS_pidfd_open','SYS_pidfd_getfd','SYS_close_range',
                  'SYS_process_vm_readv','SYS_process_vm_writev','F_ADD_SEALS','F_GET_SEALS',
                  'NSFS_MAGIC','NS_GET_NSTYPE','MFD_CLOEXEC','MFD_ALLOW_SEALING']
        report['actual_original_macros'] = {name:[line for line in macros.splitlines() if line.startswith('#define '+name+' ')] for name in wanted}
        pre_args = argv_for(argv,HERE/'preimage/kernel_api/proc_maps_provenance.cc',
                            HERE/'preimage/kernel_api/include',OUT/'preimage-provenance.o')
        try:
            command(pre_args,AOSP,env,'preimage-provenance',report['commands'],30)
        except RuntimeError:
            last = report['commands'][-1]
            error, _ = held(OUT/'preimage-provenance.stderr',1048576)
            plain_error = re.sub(rb'\x1b\[[0-9;]*m', b'', error)
            require(last['label'] == 'preimage-provenance' and last['returncode'] != 0 and not last['timed_out'] and
                    b"fatal error: 'linux/memfd.h' file not found" in plain_error,
                    'negative control did not reproduce the observed missing-header failure')
            last['expected_failure'] = True
            report['baseline_reproduced'] = True
        require(report['baseline_reproduced'], 'unpatched preimage unexpectedly compiled')
        for name in ['proc_maps_provenance','proc_maps_raw_metadata_owner','proc_maps_fd_owner',
                     'proc_maps_path','proc_maps_factory_wire']:
            source = HERE/('candidate/kernel_api/'+name+'.cc')
            include = HERE/'candidate/kernel_api/include'
            target = OUT/(name+'.o')
            command(argv_for(argv,source,include,target,'dependencies'),AOSP,env,name+'-dependencies',report['commands'],20)
            before = dependency_files(Path(str(target)+'.d'))
            command(argv_for(argv,source,include,target),AOSP,env,name+'-compile',report['commands'],30)
            after = dependency_files(Path(str(target)+'.d'))
            require(before == after, 'actual compiler input set or content changed: '+name)
            report['actual_system_and_generated_dependencies'].update(after)
            raw, row = held(target,16*1024*1024)
            require(raw[:6] == b'\x7fELF\x02\x01' and int.from_bytes(raw[16:18],'little') == 1 and
                    int.from_bytes(raw[18:20],'little') == 62,'candidate output is not x86_64 ELF REL')
            report['compiled_TUs'].append({'name':name,'object':row,'dependency_count':len(after),
                                           'original_warning_target_and_sysroot_flags_preserved':True})
        require(len(report['compiled_TUs']) == 5,'complete candidate TU set not compiled')
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__,'message':str(error),
                                  'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup'] = cleanup_children()
        changes = []
        for name,row in source_before.items():
            try:
                if hash_held(HERE/name,4*1024*1024) != row: changes.append(name)
            except Exception as error: changes.append({'source':name,'error':repr(error)})
        for path,row in report['actual_system_and_generated_dependencies'].items():
            try:
                if hash_held(Path(path),16*1024*1024) != row: changes.append(path)
            except Exception as error: changes.append({'dependency':path,'error':repr(error)})
        try:
            if authority is None or current_header_authority(authority) != header_before:
                changes.append('fixed header authority')
            if compiler_before is None or hash_held(Path(compiler_before['path'])) != compiler_before:
                changes.append('compiler entry')
        except Exception as error: changes.append({'authority_error':repr(error)})
        report['input_changes'] = changes
        try:
            require(resource_fd >= 0 and resource_before is not None,'owned resource admission missing')
            report['owned_resource_gate'] = finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            report['state'] = 'FAIL'
        finally:
            if resource_fd >= 0: os.close(resource_fd)
        cleanup = report['cleanup']
        if changes or cleanup['forced_cleanup'] or cleanup['remaining'] or cleanup['errors']:
            report['state'] = 'FAIL'
        report['observed_signals'] = OBSERVED_SIGNALS
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json',report)
        print(json.dumps({'state':report['state'],'result':result,'Main_actions':0,'full_engine_built':False}),flush=True)
    return 0 if report['state'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'complete_candidate_TUs':5,
                          'original_host_sysroot_and_warning_flags':True,'objects_executed':False,
                          'requires_explicit_execute_once':True,'Main_actions':0}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: compile_tus.py [--execute-once]')
