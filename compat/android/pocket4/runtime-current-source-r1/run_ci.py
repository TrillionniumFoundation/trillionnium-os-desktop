#!/usr/bin/env python3
"""Run the complete current ordinary catalog and normal release builds in fresh CI."""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import traceback

SPEC = importlib.util.spec_from_file_location('current_source_verifier', Path(__file__).with_name('verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
HERE = Path(__file__).resolve().parent
UPDATER = ('droidloom-update', 'droidloom-update')


def configuration():
    targets = VERIFY.decode(VERIFY.regular(HERE / 'EXPECTED-TARGETS.json'))
    bins = VERIFY.decode(VERIFY.regular(HERE / 'EXPECTED-BINS.json'))
    catalogs = VERIFY.decode(VERIFY.regular(HERE / 'EXPECTED-CATALOG.json'))
    exact = VERIFY.decode(VERIFY.regular(HERE / 'UPDATER-EXACT64.json'))
    result = []
    for rows, count in [(targets, 49), (bins, 19)]:
        mapped = {}
        for row in rows:
            VERIFY.need(set(row) == {'package','target','kind','source_path','required_features','test'}, 'exact target fields')
            VERIFY.safe(row['source_path'])
            key = (row['package'], row['target'])
            VERIFY.need(key not in mapped and row['test'] is True and row['required_features'] == []
                        and row['kind'] in (['lib'],['bin'],['test']), 'one explicit testable source target')
            mapped[key] = row
        VERIFY.need(len(mapped) == count, 'complete target set')
        result.append(mapped)
    registered = {}
    for row in catalogs:
        key = (row['package'], row['target'])
        VERIFY.need(set(row) == {'package','target','all','ignored'} and key not in registered,
                    'distinct complete catalog target')
        VERIFY.need(row['all'] == sorted(set(row['all'])) and row['ignored'] == sorted(set(row['ignored']))
                    and set(row['ignored']) <= set(row['all']), 'exact catalog and ignored names')
        registered[key] = row
    VERIFY.need(set(registered) == set(result[0]) and len({k[0] for k in result[0]}) == 28,
                'all28 packages and49 test targets')
    VERIFY.need(sum(len(r['all']) for r in registered.values()) == 1329
                and sum(len(r['ignored']) for r in registered.values()) == 30, 'complete1329/30 catalog')
    VERIFY.need(len(exact) == len(set(exact)) == 64
                and set(exact) <= set(registered[UPDATER]['all']) - set(registered[UPDATER]['ignored']),
                '64 disjoint ordinary updater names')
    return *result, registered, exact


def canonical_target(package, target, producer):
    source = Path(target['src_path']).absolute()
    VERIFY.need(source.resolve() == source and source.is_relative_to(producer), 'target source outside current producer')
    return {'package':package, 'target':target['name'], 'kind':target['kind'],
            'source_path':source.relative_to(producer).as_posix(),
            'required_features':target.get('required-features', []), 'test':target['test']}


def metadata_targets(raw, producer, wanted_tests, wanted_bins):
    meta = VERIFY.decode(raw)
    members = set(meta['workspace_members'])
    packages = {p['id']:p for p in meta['packages'] if p['id'] in members}
    VERIFY.need(len(members) == len(packages) == 28, 'exact28 current workspace members')
    tests, bins = {}, {}
    for package in packages.values():
        for target in package['targets']:
            if target['kind'] not in (['lib'],['bin'],['test']):
                continue
            row = canonical_target(package['name'], target, producer)
            key = (row['package'], row['target'])
            if target['test']:
                VERIFY.need(key not in tests, 'duplicate metadata test target')
                tests[key] = row
            if target['kind'] == ['bin']:
                VERIFY.need(key not in bins, 'duplicate metadata binary target')
                bins[key] = row
    VERIFY.need(tests == wanted_tests and bins == wanted_bins, 'full actual metadata target set differs')
    return {key:value['name'] for key,value in packages.items()}


def artifacts(raw, package_ids, producer, target, expected, test_profile, profile_dir='release', complete=True):
    result = {}
    for row in VERIFY.successful_cargo_stream(raw):
        if row.get('reason') != 'compiler-artifact' or not row.get('executable'):
            continue
        if row['target']['kind'] == ['custom-build']:
            continue
        if row['profile']['test'] is not test_profile:
            continue
        VERIFY.need(row['package_id'] in package_ids, 'executable from a foreign package')
        spec = canonical_target(package_ids[row['package_id']], row['target'], producer)
        key = (spec['package'], spec['target'])
        VERIFY.need(key in expected and spec == expected[key] and key not in result and row['fresh'] is False,
                    'one freshly built exact source target required')
        path = Path(row['executable']).absolute()
        folder = target / ('debug/deps' if test_profile else profile_dir)
        VERIFY.need(path.resolve() == path and path.parent == folder, 'unexpected actual artifact location')
        if not test_profile:
            VERIFY.need(path.name == spec['target'] and spec['kind'] == ['bin'], 'exact normal release target')
        result[key] = {'message':row, 'path':path}
    VERIFY.need(set(result) == set(expected) if complete else set(result) <= set(expected), 'missing or extra compiled targets')
    return result


def elf(path, with_body=False):
    path = Path(path).absolute()
    VERIFY.need(path.resolve() == path, 'artifact parent alias')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        VERIFY.need(stat.S_ISREG(before.st_mode) and before.st_mode & 0o111
                    and 0 < before.st_size <= 128 * 1024**2, 'bounded actual executable')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            body = stream.read(before.st_size + 1)
        VERIFY.need(len(body) == before.st_size and body[:6] == b'\x7fELF\x02\x01'
                    and int.from_bytes(body[18:20], 'little') == 62
                    and VERIFY.f9(before) == VERIFY.f9(os.fstat(fd)) == VERIFY.f9(path.lstat()),
                    'whole unchanged x86_64 ELF')
        ref = {'path':str(path), **VERIFY.digest(body), 'identity':VERIFY.f9(before)}
        return (ref,body) if with_body else ref
    finally:
        os.close(fd)


def catalog(raw, expected):
    lines = raw.decode('utf-8','strict').splitlines()
    names, summaries = [], []
    for line in lines:
        if not line:
            continue
        if line.endswith(': test'):
            names.append(line[:-6])
        else:
            match = re.fullmatch(r'(\d+) tests?, 0 benchmarks?', line)
            VERIFY.need(match is not None, 'unexpected catalog output')
            summaries.append(int(match[1]))
    VERIFY.need(names == sorted(set(names)) == sorted(expected)
                and summaries in ([], [len(names)]), 'complete exact catalog names')
    return names


def aliases(ref, profile_root):
    found = []
    for directory, children, names in os.walk(profile_root, followlinks=False):
        for name in names:
            path = Path(directory) / name
            observed = path.lstat()
            if stat.S_ISREG(observed.st_mode) and (observed.st_dev,observed.st_ino) == tuple(ref['identity'][:2]):
                VERIFY.need(VERIFY.f9(observed) == ref['identity'], 'original Cargo alias changed')
                found.append(path)
    original = Path(ref['path'])
    VERIFY.need(len(found) == ref['identity'][5] and len(found) in (1,2) and original in found
                and all(p == original or p.parent == profile_root/'deps' for p in found),
                'all original Cargo aliases must stay inside this fresh target')
    return [str(path) for path in sorted(found)]


def cli_bindings(compiled, debug, producer, target):
    frozen = {key:elf(row['path']) for key,row in debug.items()}
    bindings = []
    for key,item in sorted(compiled.items()):
        message = item['message']
        if message['target']['kind'] != ['test']:
            continue
        source = Path(message['target']['src_path'])
        names = sorted(set(re.findall(r'CARGO_BIN_EXE_([A-Za-z0-9_-]+)', VERIFY.regular(source).decode())))
        if not names:
            continue
        _, body = elf(item['path'], with_body=True)
        rows = []
        for name in names:
            selected = (key[0],name)
            VERIFY.need(selected in debug and str(debug[selected]['path']).encode() in body,
                        'integration test must embed its actual newly compiled normal CLI')
            VERIFY.need(elf(debug[selected]['path']) == frozen[selected], 'normal CLI changed during binding')
            rows.append({'target':name,'artifact':frozen[selected],
                         'aliases':aliases(frozen[selected],target/'debug')})
        bindings.append({'package':key[0],'target':key[1],'source_path':source.relative_to(producer).as_posix(),
                         'actual_absolute_CLI_paths_present':True,'normal_debug_binaries':rows})
    return bindings,frozen


def owned_children():
    result = set()
    for task in Path('/proc/self/task').iterdir():
        result.update(int(value) for value in (task / 'children').read_text().split())
    return result


def reap_descendants(grace_seconds=3):
    until = time.monotonic() + grace_seconds
    retired = []
    while True:
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                pid = 0
            if not pid:
                break
            retired.append({'pid':pid, 'wait_status':status, 'forced':False})
        children = owned_children()
        if not children:
            return retired
        if time.monotonic() >= until:
            break
        time.sleep(0.02)
    cleanup_until = time.monotonic() + 10
    while owned_children():
        VERIFY.need(time.monotonic() < cleanup_until, 'owned descendants did not retire within cleanup interval')
        for pid in sorted(owned_children()):
            try:
                fd = os.pidfd_open(pid)
            except ProcessLookupError:
                continue
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            finally:
                os.close(fd)
            retired.append({'pid':pid, 'forced':True})
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not pid:
                break
            retired.append({'pid':pid, 'wait_status':status, 'reaped':True})
        time.sleep(0.02)
    return retired


def interrupted(signum, frame):
    raise TimeoutError('CI controller interrupted by signal ' + str(signum))


def execute_child(argv, cwd, env, out, err, timeout):
    child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=out, stderr=err, start_new_session=True)
    fd = None; start_ticks = None; error = None; cleanup_errors = []; descendants = []
    try:
        fd = os.pidfd_open(child.pid)
        proc = Path('/proc/'+str(child.pid)+'/stat').read_text()
        start_ticks = int(proc[proc.rfind(')')+2:].split()[19])
        child.wait(timeout=timeout)
    except BaseException as failure:
        error = failure
    finally:
        old_signals = {signum:signal.signal(signum,signal.SIG_IGN) for signum in (signal.SIGTERM,signal.SIGINT)}
        try:
            # The direct child's PID cannot be recycled before this parent reaps it.
            if child.returncode is None:
                for signum in (signal.SIGTERM,signal.SIGKILL):
                    try:
                        os.killpg(child.pid,signum)
                    except ProcessLookupError:
                        pass
                    except BaseException as failure:
                        cleanup_errors.append('group signal: '+repr(failure))
                        try:
                            if fd is not None: signal.pidfd_send_signal(fd,signum)
                            else: child.send_signal(signum)
                        except ProcessLookupError: pass
                        except BaseException as nested: cleanup_errors.append('direct signal: '+repr(nested))
                    try:
                        child.wait(timeout=5)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                    except BaseException as failure:
                        cleanup_errors.append('direct wait: '+repr(failure))
                if child.returncode is None:
                    cleanup_errors.append('original child not reaped after finite cleanup')
            try:
                descendants = reap_descendants()
            except BaseException as failure:
                cleanup_errors.append('descendant retirement: '+repr(failure))
        finally:
            if fd is not None: os.close(fd)
            for signum,handler in old_signals.items(): signal.signal(signum,handler)
    return {'pid':child.pid,'start_ticks':start_ticks,'exit_code':child.returncode,
            'original_pidfd_held_until_reaped':fd is not None and child.returncode is not None,
            'actual_child_reaped':child.returncode is not None,'retired_descendants':descendants,
            'owned_descendants_remaining':len(owned_children()),
            'timed_out':isinstance(error,subprocess.TimeoutExpired),
            'error':None if error is None else {'type':type(error).__name__,'message':str(error)},
            'cleanup_errors':cleanup_errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--erofs-prefix', type=Path, required=True)
    args = parser.parse_args()
    VERIFY.need(os.geteuid() != 0 and os.uname().machine == 'x86_64', 'ordinary Linux x86_64 CI user required')
    cpus = sorted(os.sched_getaffinity(0))
    VERIFY.need(len(cpus) >= 4, 'two test CPUs and two reserved logical CPUs required')
    os.sched_setaffinity(0, set(cpus[:2]))
    libc = ctypes.CDLL(None, use_errno=True)
    VERIFY.need(libc.prctl(36, 1, 0, 0, 0) == 0, 'child subreaper admission failed')
    VERIFY.need(not owned_children(), 'unexpected preexisting CI child')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    capsule = VERIFY.verify_capsule(args.inventory_sha256)
    producer = args.producer.absolute()
    before = VERIFY.source_snapshot(producer, capsule['rows'], VERIFY.HEAD_TREE)
    work = VERIFY.fresh_destination(args.work, [HERE, producer])
    report = VERIFY.fresh_destination(args.report, [HERE, producer, work])
    work.mkdir(mode=0o700)
    target, cache, temporary, logs, test_cwd, pathbin = [work / name for name in
        ('target','cargo-home','tmp','logs','test-cwd','bin')]
    for path in (target, cache, temporary, logs, test_cwd, pathbin):
        path.mkdir(mode=0o700)
    fakeroot = Path('/usr/bin/fakeroot-sysv')
    script = VERIFY.regular(fakeroot)
    VERIFY.need(script.startswith(b'#!/bin/sh\n') and b'faked-sysv' in script, 'actual SysV fakeroot script required')
    (pathbin / 'fakeroot').write_bytes(script)
    (pathbin / 'fakeroot').chmod(0o500)
    erofs = args.erofs_prefix.absolute()
    VERIFY.need(erofs.resolve() == erofs and erofs.is_dir(), 'private actual EROFS prefix required')
    tools = {}
    for path in [Path('/usr/sbin')/name for name in ('mke2fs','debugfs','e2fsck')]:
        VERIFY.need(path.is_file() and not path.is_symlink() and os.access(path, os.X_OK), 'fixed regular ext4 tool required')
        tools[str(path)] = VERIFY.digest(VERIFY.regular(path))
    for name in ('mkfs.erofs','fsck.erofs','dump.erofs'):
        path = erofs / 'bin' / name
        VERIFY.need(os.access(path, os.X_OK), 'missing private EROFS tool')
        tools[str(path)] = VERIFY.digest(VERIFY.regular(path))
    for path in [fakeroot, Path('/usr/bin/faked-sysv'), Path('/usr/lib/x86_64-linux-gnu/libfakeroot/libfakeroot-sysv.so').resolve()]:
        tools[str(path)] = VERIFY.digest(VERIFY.regular(path))
    env = dict(os.environ)
    exact_overrides = {'RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER',
        'RUSTC','RUSTDOC','RUSTDOCFLAGS','CARGO_ENCODED_RUSTDOCFLAGS','LD_LIBRARY_PATH','LD_PRELOAD',
        'CARGO_BUILD_TARGET','CARGO_BUILD_RUSTFLAGS','CARGO_BUILD_RUSTC','CARGO_BUILD_RUSTC_WRAPPER',
        'CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER','CARGO_BUILD_RUSTDOC','CC','CXX','CPP','AR','LD','RANLIB',
        'CPPFLAGS','LDFLAGS','PKG_CONFIG','BINDGEN_EXTRA_CLANG_ARGS','RUSTC_BOOTSTRAP',
        'RUST_TEST_THREADS','RUST_TEST_NOCAPTURE'}
    override_prefixes = ('CARGO_TARGET_','CARGO_PROFILE_','CC_','CXX_','CFLAGS','CXXFLAGS','CPPFLAGS_',
        'LDFLAGS_','AR_','LD_','PKG_CONFIG_','BINDGEN_EXTRA_CLANG_ARGS_','CARGO_BUILD_','CARGO_NET_')
    for key in list(env):
        if key in exact_overrides or key.startswith(override_prefixes):
            del env[key]
    env.update(CARGO_HOME=str(cache), CARGO_TARGET_DIR=str(target), CARGO_INCREMENTAL='0',
        CARGO_BUILD_JOBS='1', CARGO_TERM_COLOR='never', RAYON_NUM_THREADS='1', RUSTUP_TOOLCHAIN='1.93.0',
        RUSTUP_AUTO_INSTALL='0', LANG='C.UTF-8', LC_ALL='C.UTF-8', PYTHONDONTWRITEBYTECODE='1',
        TMPDIR=str(temporary), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_NO_LAZY_FETCH='1',
        GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0', PKG_CONFIG='/usr/bin/pkgconf', CC='/usr/bin/x86_64-linux-gnu-gcc-13',
        PATH=str(pathbin)+':'+str(erofs/'bin')+':'+os.environ['PATH'])
    for key in ('LD_PRELOAD','FAKEROOTKEY','FAKED_MODE','DROIDLOOM_IMAGE_POLICY_TEST','DROIDLOOM_GAPPS_EROFS_TEST',
                'DROIDLOOM_TEST_DRM_NODE','DBUS_SESSION_BUS_ADDRESS','WAYLAND_DISPLAY','DISPLAY','RUST_MIN_STACK','CARGO_NET_OFFLINE'):
        env.pop(key, None)
    result = {'schema':'p4-current-fresh-ordinary-and-release-ci-v1','state':'RUNNING',
        'source_commit':VERIFY.HEAD_COMMIT,'source_parent_commit':VERIFY.PARENT_COMMIT,
        'source_tree':VERIFY.HEAD_TREE,'source_files':VERIFY.SOURCE_FILES,
        'source_bytes':VERIFY.SOURCE_BYTES,'source_overlay_sha256':VERIFY.OVERLAY['sha256'],
        'started_ns':time.time_ns(),'commands':[],'errors':[],'fresh_ordinary_passed':0,
        'fresh_test_targets':0,'fresh_release_binaries':{},'ignored_not_executed':[],
        'historical_tests_counted_as_fresh':0,'historical_ELFs_reused':False,'jobs':1,'test_threads':1,
        'affinity':cpus[:2],'reserved_cpus':cpus[2:],'tool_identities':tools,
        'Android_builds':0,'Android_starts':0,'runtime_qualified':False,'production_ready':False,
        'doc_tests_executed':False,'full_workspace_qualified':False,'positive_hardware_branches_inferred':False}
    deadline = time.monotonic() + 5400

    def run(name, argv, timeout, cwd=producer):
        VERIFY.need(not owned_children(), 'previous command still owns descendants')
        remaining = deadline - time.monotonic()
        VERIFY.need(remaining > timeout + 15, 'remaining whole CI interval cannot cover command and cleanup')
        outpath, errpath = logs/(name+'.stdout'), logs/(name+'.stderr')
        began = time.time_ns()
        with outpath.open('xb') as out, errpath.open('xb') as err:
            execution = execute_child(argv,cwd,env,out,err,timeout)
        stdout, stderr = VERIFY.regular(outpath), VERIFY.regular(errpath)
        row = {'name':name,'argv':argv,'cwd':str(cwd),**execution,
            'started_ns':began,'finished_ns':time.time_ns(),
            'stdout':{'path':str(outpath),**VERIFY.digest(stdout)},'stderr':{'path':str(errpath),**VERIFY.digest(stderr)}}
        result['commands'].append(row)
        VERIFY.need(execution['error'] is None and not execution['cleanup_errors']
                    and execution['exit_code'] == 0 and execution['actual_child_reaped']
                    and execution['original_pidfd_held_until_reaped'] and not owned_children()
                    and not any(r.get('forced') for r in execution['retired_descendants']),
                    'fresh command or complete retirement failed: '+name)
        VERIFY.need(time.monotonic() < deadline, 'whole CI deadline expired after command')
        return row, stdout

    try:
        expected_tests, expected_bins, catalogs, exact = configuration()
        result['ignored_not_executed'] = [{'package':p,'target':t,'case':name}
            for (p,t),cat in sorted(catalogs.items()) for name in cat['ignored']]
        run('dependency-fetch', ['cargo','+1.93.0','fetch','--locked'], 900)
        env['CARGO_NET_OFFLINE'] = 'true'
        _, raw = run('workspace-metadata',['cargo','+1.93.0','metadata','--offline','--locked','--no-deps','--format-version=1'],60)
        ids = metadata_targets(raw, producer, expected_tests, expected_bins)
        packages = sorted(set(ids.values()))
        batches = [('updater',['droidloom-update']),('remaining27',[p for p in packages if p!='droidloom-update'])]
        VERIFY.need(len(batches[1][1])==27 and set(batches[0][1]+batches[1][1])==set(packages),
                    'two disjoint complete compilation batches')
        compiled, debug, compilation_by_target = {}, {}, {}
        for label,selected in batches:
            expected = {k:v for k,v in expected_tests.items() if k[0] in selected}
            normal = {k:v for k,v in expected_bins.items() if k[0] in selected}
            selection = [value for package in selected for value in ('-p',package)]
            target_flags = [flag for kind,flag in [('lib','--lib'),('bin','--bins'),('test','--tests')]
                            if any(row['kind']==[kind] for row in expected.values())]
            compilation, raw = run('compile-'+label,['cargo','+1.93.0','test','--offline','--locked',*selection,
                '-j1',*target_flags,'--no-run','--message-format=json'],900)
            actual = artifacts(raw,ids,producer,target,expected,True)
            actual_debug = artifacts(raw,ids,producer,target,normal,False,profile_dir='debug',complete=False)
            VERIFY.need(not set(compiled)&set(actual) and not set(debug)&set(actual_debug), 'overlapping compile batch')
            compiled.update(actual);debug.update(actual_debug)
            compilation_by_target.update({key:compilation for key in actual})
        VERIFY.need(set(compiled)==set(expected_tests), 'actual disjoint compile union must contain all49 targets')
        result['compile_time_CLI_bindings'], debug_frozen = cli_bindings(compiled,debug,producer,target)
        frozen = {key:elf(row['path']) for key,row in compiled.items()}
        result['fresh_test_targets'] = len(frozen)
        for key, ref in frozen.items():
            compilation = compilation_by_target[key]
            VERIFY.need(compilation['started_ns'] <= ref['identity'][7] <= compilation['finished_ns'], 'harness predates this compile')
        result['harnesses'] = [{'package':k[0],'target':k[1],**v} for k,v in sorted(frozen.items())]
        for index, (key, item) in enumerate(sorted(compiled.items())):
            binary = str(item['path']); cat = catalogs[key]; prefix = 'target-%02d'%index
            VERIFY.need(elf(item['path']) == frozen[key], 'harness changed before catalog')
            _, raw = run(prefix+'-catalog',[binary,'--list','--color','never'],30,test_cwd)
            catalog(raw,cat['all'])
            _, raw = run(prefix+'-ignored',[binary,'--ignored','--list','--color','never'],30,test_cwd)
            catalog(raw,cat['ignored'])
            passed = set(cat['all']) - set(cat['ignored'])
            if key == UPDATER:
                for number, case in enumerate(exact):
                    row, raw = run('updater-exact-%02d'%number,[binary,'--exact',case,'--test-threads=1','--color','never'],60,test_cwd)
                    row['actual_tests'] = VERIFY.test_terminal(raw.decode(),[case],[],len(cat['all'])-1,catalog=cat['all'])
                    result['fresh_ordinary_passed'] += 1
                skip = [value for case in exact for value in ('--skip',case)]
                _, raw = run('updater-bulk-filtered-catalog',[binary,'--list',*skip,'--color','never'],30,test_cwd)
                catalog(raw,set(cat['all'])-set(exact))
                row, raw = run('updater-bulk421',[binary,*skip,'--test-threads=1','--color','never'],300,test_cwd)
                row['actual_tests'] = VERIFY.test_terminal(raw.decode(),passed-set(exact),cat['ignored'],64,catalog=cat['all'])
                result['fresh_ordinary_passed'] += len(passed)-64
            else:
                row, raw = run(prefix+'-ordinary',[binary,'--test-threads=1','--color','never'],300,test_cwd)
                row['actual_tests'] = VERIFY.test_terminal(raw.decode(),passed,cat['ignored'],0,catalog=cat['all'])
                result['fresh_ordinary_passed'] += len(passed)
            VERIFY.need(elf(item['path']) == frozen[key], 'harness changed after execution')
        VERIFY.need(result['fresh_ordinary_passed'] == 1299 and len(result['ignored_not_executed']) == 30,
                    'complete fresh1299 ordinary and30 unchanged ignored cases required')
        for key,ref in debug_frozen.items():
            VERIFY.need(elf(debug[key]['path']) == ref, 'normal debug binary changed during ordinary tests')
        released, release_by_target = {}, {}
        for label,selected in batches:
            expected = {k:v for k,v in expected_bins.items() if k[0] in selected}
            selection = [value for package in selected for value in ('-p',package)]
            release, raw = run('normal-release-'+label,['cargo','+1.93.0','build','--offline','--locked',*selection,
                '--release','-j1','--bins','--message-format=json'],900)
            actual = artifacts(raw,ids,producer,target,expected,False)
            VERIFY.need(not set(released)&set(actual), 'overlapping normal release batch')
            released.update(actual);release_by_target.update({key:release for key in actual})
        VERIFY.need(set(released)==set(expected_bins), 'actual disjoint normal release union must contain all19 targets')
        for key, item in sorted(released.items()):
            release = release_by_target[key]
            ref = elf(item['path'])
            VERIFY.need(release['started_ns'] <= ref['identity'][7] <= release['finished_ns']
                        and release['started_ns'] <= ref['identity'][8] <= release['finished_ns'],
                        'release ELF predates actual normal build')
            result['fresh_release_binaries'][key[1]] = {'package':key[0],**ref,
                'all_original_aliases':aliases(ref,target/'release')}
        VERIFY.need(len(result['fresh_release_binaries']) == 19, 'all19 normal binary artifacts required')
        result['all_source_bookends_equal'] = VERIFY.source_snapshot(producer,capsule['rows'],VERIFY.HEAD_TREE) == before
        VERIFY.need(result['all_source_bookends_equal'] and not owned_children(), 'source changed or command descendants remain')
        VERIFY.need(time.monotonic() < deadline, 'whole CI deadline expired during final artifact/source readback')
        result['state'] = 'ALL1299_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED'
    except BaseException as error:
        result['state'] = 'FAILED'
        result['errors'].append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
        try: result['all_source_bookends_equal'] = VERIFY.source_snapshot(producer,capsule['rows'],VERIFY.HEAD_TREE) == before
        except BaseException as after: result['errors'].append({'source_after_error':str(after)})
    finally:
        try:
            final_children = reap_descendants()
            result['final_descendant_retirement'] = final_children
            VERIFY.need(not owned_children() and not any(r.get('forced') for r in final_children),
                        'CI finalizer had to retire unexpected children')
        except BaseException as error:
            result['state'] = 'FAILED'
            result['errors'].append({'final_cleanup_error':str(error)})
        if time.monotonic() >= deadline:
            result['state'] = 'FAILED'
            result['errors'].append({'whole_deadline_expired':True})
    result['finished_ns'] = time.time_ns()
    VERIFY.write_report(report,result,[HERE,producer,work])
    print(json.dumps({'state':result['state'],'fresh_ordinary_passed':result['fresh_ordinary_passed'],
        'fresh_normal_release_count':len(result['fresh_release_binaries']),'report':str(report),'production_ready':False},sort_keys=True))
    return 0 if result['state'] == 'ALL1299_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
