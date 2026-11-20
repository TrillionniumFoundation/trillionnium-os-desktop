#!/usr/bin/python3
"""Compile isolated K1a native allocator and normal loop objects using the actual matching 6.18.64 inputs.

No Kbuild reconfiguration, original-tree write, kernel link, installation,
device access, VM, reboot or Android action is performed.
"""
from pathlib import Path
import hashlib
import json
import os
import resource
import shlex
import signal
import stat
import subprocess
import time

ROOT = Path('/home/alex/work/p4-private-loop-k1a-20261120-3b9d-r1')
OLD = Path('/home/alex/work/p4-private-loop-k0a-compile-20261120-3b9d-r1')
SOURCE = OLD / 'source/linux-6.18.64'
OVERLAY = ROOT / 'overlay'
OUT_ROOT = ROOT / 'out'
OUT = OUT_ROOT
RESULT = ROOT / 'OBJECT-COMPILE.json'
DEADLINE = None
HELD = {}
OBS = {'schema': 'p4-k1a-matching-native-allocation-object-compile-v1', 'state': 'PENDING',
       'commands': [], 'objects': [], 'kernel_linked': False, 'kernel_loaded': False,
       'kernel_installed': False, 'VM_started': False, 'Android_started': False,
       'kernel_runtime_tests_executed': False, 'runtime_qualified': False,
       'production_ready': False, 'Kbuild_configuration_selection_executed': False}
NEW_UNITS = ('block/p4_private_loop_realm', 'drivers/block/loop')
INHERITED_UNITS = ()


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def read(path, pin=None, retain=False):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'canonical exact input')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(stat.S_ISREG(before[2]) and before[5] == 1 and 0 <= before[6] <= 16 * 1024**2,
             'bounded actual regular single-link input')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            body = stream.read(16 * 1024**2 + 1)
        need(len(body) == before[6] and before == f9(os.fstat(fd)) == f9(path.lstat()),
             'whole body and original descriptor/path identity')
        row = {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
               'identity': before}
        if pin is not None:
            need((row['bytes'], row['sha256']) == (pin['bytes'], pin['sha256']),
                 'exact pinned input: ' + str(path))
        if retain:
            if str(path) in HELD:
                need(HELD[str(path)][1] == row, 'same retained original input')
            else:
                HELD[str(path)] = (fd, row); fd = None
        return row, body
    finally:
        if fd is not None:
            os.close(fd)


def ref(path, pin=None):
    return read(path, pin)[0]


def immutable(row):
    need(ref(row['path']) == row, 'original input changed: ' + row['path'])
    if row['path'] in HELD:
        need(f9(os.fstat(HELD[row['path']][0])) == row['identity'],
             'original retained descriptor changed')


def create(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    need(path.parent.resolve() == path.parent, 'canonical new isolated parent')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return ref(path)


def run(name, argv, expected=0, maximum=90):
    stdout_path = ROOT/'logs'/(name+'.stdout'); stderr_path = ROOT/'logs'/(name+'.stderr')
    started = time.monotonic_ns(); timeout = min(maximum, DEADLINE-time.monotonic())
    need(timeout > 0, 'single bounded compile deadline')
    with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=OUT, stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=stderr, start_new_session=True, close_fds=True,
            env={'PATH':'/usr/bin:/bin', 'LC_ALL':'C'})
        pidfd = None
        try:
            pidfd = os.pidfd_open(child.pid)
            code = child.wait(timeout=timeout)
        except BaseException:
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            time.sleep(0.1)
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait(timeout=10)
            raise
        finally:
            if pidfd is not None:
                os.close(pidfd)
    row = {'name': name, 'argv': argv, 'pid': child.pid, 'exit_code': code,
        'actual_direct_child_reaped': True, 'original_pidfd_held_until_reaped': True,
        'started_ns': started, 'finished_ns': time.monotonic_ns(),
        'stdout': ref(stdout_path), 'stderr': ref(stderr_path)}
    OBS['commands'].append(row)
    need(code == expected and row['stderr']['bytes'] == 0,
         'actual command result or diagnostics require review: ' + name)
    return row


def dependencies(path):
    body = Path(path).read_text().replace('\\\n', ' ')
    need(':' in body, 'actual GCC dependency target')
    result = []
    for word in shlex.split(body.split(':', 1)[1]):
        path = Path(word)
        if not path.is_absolute():
            path = OUT/path
        path = path.resolve()
        need(any(path.is_relative_to(parent) for parent in (SOURCE, OVERLAY, OUT)),
             'dependency confined to actual matching inputs and isolated postimages')
        result.append(path)
    need(len(result) > 100, 'actual complete kernel C dependency closure')
    return sorted(set(result))


def compiler_arguments(raw, unit, compiler):
    old_source = '/home/qq/work/p4-kernel-6.18.64-cp3a-20261118-r1/source/linux-6.18.64'
    args = shlex.split(raw)
    need(args[0] == compiler['path'] and args[-1] == old_source+'/kernel/p4_guest_mntns.c',
         'original exact compiler recipe')
    directory, basename = unit.rsplit('/', 1)
    result = []
    for arg in args:
        arg = arg.replace(old_source, str(SOURCE))
        arg = arg.replace('kernel/.p4_guest_mntns.o.d', directory+'/.'+basename+'.o.d')
        arg = arg.replace('kernel/p4_guest_mntns', unit)
        arg = arg.replace('p4_guest_mntns', basename)
        if arg == '-Ikernel': arg = '-I'+directory
        if arg == '-I'+str(SOURCE/'kernel'): arg = '-I'+str(SOURCE/directory)
        # Actual scripts/Makefile.lib name-fix-token; MODFILE remains a path.
        if arg.startswith(('-DKBUILD_BASENAME=', '-DKBUILD_MODNAME=', '-D__KBUILD_MODNAME=')):
            key, value = arg.split('=', 1)
            arg = key + '=' + value.replace('-', '_').replace(',', '_')
        result.append(arg)
    # The additional include directory contains exactly the reviewed
    # K0b/K0c/K1a headers. All architecture/config/generated headers remain original.
    position = result.index('-I'+str(SOURCE/'include'))
    result.insert(position, '-I'+str(OVERLAY/'include'))
    source = OVERLAY/(unit+'.c') if (OVERLAY/(unit+'.c')).is_file() else SOURCE/(unit+'.c')
    result[-1] = str(source)
    index = result.index('-c')
    need(result[index:index+3] == ['-c', '-o', unit+'.o'], 'one isolated selected C output')
    return result


def alarm(signum, frame):
    raise TimeoutError('bounded K1a object compile expired')


PACKET_PIN = {'bytes': 468361, 'sha256': 'e0fc3057b42445182644b1ab7b0dcf512a5c30b63d2a2135b0764abe5192a988'}

def main():
    global DEADLINE, OUT
    need(os.getuid() == os.geteuid() == os.getgid() == 1000,
         'ordinary nonprivileged Pocket4 owner')
    need(ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE
         and not os.path.lexists(RESULT), 'exact immutable source and new isolated result')
    need(23 in os.sched_getaffinity(0), 'reserved independent CPU23')
    os.sched_setaffinity(0, {23}); os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (420, 420))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024**2, 64*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (8192, 8192))
    signal.signal(signal.SIGALRM, alarm); signal.alarm(480); DEADLINE = time.monotonic()+450
    packet_ref, raw = read(ROOT/'SOURCE-PACKET.json', PACKET_PIN, True)
    packet = json.loads(raw); manifest = packet['manifest']
    need(packet['schema'] == 'p4-k1a-matching-native-allocation-object-source-packet-v1'
         and manifest['parent_K0c_commit'] == 'f83f52dde3594d7eef4a1e44785f940c824467d5'
         and len(manifest['files']) == 5 and manifest['K1_complete'] is False
         and manifest['issuer_enabled'] is False and manifest['production_ready'] is False,
         'exact closed native-allocation K1a source packet')
    needed = manifest['files']+manifest['unchanged_inherited_files']
    need(len(needed) == 21 and set(packet['sources']) == {row['path'] for row in needed},
         'only five changed/new and sixteen inherited exact source bodies')
    prior_K0c_ref, prior_raw = read(
        Path('/home/alex/work/p4-private-loop-k0c-20261120-3b9d-r2/OBJECT-COMPILE.json'),
        {'bytes':1616986,'sha256':'8e0e4ea16f225c0b531eea33fc8f74e781a5f3e80984ee1c1acf7ae6582f3204'}, True)
    prior = json.loads(prior_raw)
    need(prior['state'] == 'MATCHING_24_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED'
         and len(prior['objects']) == 24
         and prior['source_packet']['sha256'] == packet['prior_K0c_source_packet']['sha256'],
         'actual prior K0c matching compilation, not new runtime credit')
    OBS['prior_actual_K0c_objects'] = prior_K0c_ref
    original_checks = []
    for row in packet['original_checks']:
        original_checks.append(read(SOURCE/row['path'], row, True)[0])
    preparation_ref, raw = read(OLD/'TREE-PREPARATION.json',
        {'bytes':23008,'sha256':'232793bb6e70cfdd0aba664c1a0be17f2a623d465cc2507a884582f65f18b243'}, True)
    preparation = json.loads(raw)
    old_compile_ref, raw = read(OLD/'OBJECT-COMPILE.json',
        {'bytes':251396,'sha256':'6b47c885ba790987a3adb0b18a327068529e9ac612964fd05eb0c5393e0c532d'}, True)
    old_compile = json.loads(raw)
    need(old_compile['state'] == 'MATCHING_KERNEL_C_OBJECT_AND_ORIGINAL_OBJTOOL_PASSED',
         'actual prior matching compiler recipe')
    script_ref, _ = read(Path(__file__), retain=True)
    need(os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize >= 1024**3,
         'at least 1 GiB free for bounded isolated outputs')
    for directory in (OVERLAY, OUT_ROOT, ROOT/'logs'):
        need(not os.path.lexists(directory), 'create-only isolated compile directory')
        directory.mkdir(mode=0o700)
    postimages = []
    for row in needed:
        raw = packet['sources'][row['path']].encode()
        expected = row.get('after', row)
        need((len(raw),hashlib.sha256(raw).hexdigest()) == (expected['bytes'],expected['sha256']),
             'full exact reviewed body: '+row['path'])
        postimages.append(create(OVERLAY/row['path'], raw))
    compiler, _ = read(old_compile['compiler']['path'], old_compile['compiler'], True)
    need(compiler == old_compile['compiler'], 'unchanged actual GCC identity')
    command_ref, raw = read(OLD/'inputs/COMPILE-COMMAND-SOURCE.json',
        preparation['input_refs']['COMPILE-COMMAND-SOURCE.json'], True)
    commands = json.loads(raw)
    need(commands[1]['active_config_differences'] == [
        {'key':'CONFIG_LOCK_DOWN_IN_SECURE_BOOT','tu':None,'full':'y'},
        {'key':'CONFIG_SECURITY_PERF_EVENTS_RESTRICT','tu':None,'full':'y'}],
        'same explicitly recorded original security configuration')
    prefix = 'savedcmd_kernel/p4_guest_mntns.o := '
    saved = commands[0]['command']
    need(saved.startswith(prefix) and saved.count(' ; ') == 1, 'one original compile/objtool recipe')
    compile_command, objtool_command = saved[len(prefix):].split(' ; ')
    makefiles = []
    for path in ('block/Makefile','block/Kconfig','mm/Makefile','drivers/block/Makefile','block/partitions/Makefile','scripts/Makefile.lib'):
        choices = packet['fresh_original_inputs']['files']+packet['fresh_original_inputs']['additional_makefiles']
        row = next(row for row in choices if row['path'] == str(SOURCE/path))
        makefiles.append(read(SOURCE/path, {'bytes':row['size'],'sha256':row['sha256']}, True)[0])
    tool, raw = read(OLD/'inputs/objtool-original',
        {'bytes':979400,'sha256':'2453a7416b1f9aa1799ee6c900ef5dba6641182f99f5a8b50b604c106959e3ba'}, True)
    staged_tool = create(ROOT/'objtool-staged', raw, 0o700)
    config_ref, config_raw = read(OLD/'out/.config',
        {'bytes':304072,'sha256':'bccb147083a909408e25dc63f1dd58cf465ee19bcabc660916a1fa28cc67a3e1'}, True)
    need(b'CONFIG_BLK_DEV_LOOP=y\n' in config_raw, 'matching built-in original loop driver')
    generated = []
    original_generated = []
    for row in preparation['generated_C_headers']:
        reference, body = read(OLD/'out'/row['path'], row, True)
        original_generated.append((row['path'], reference, body))
    need(len(original_generated) == 43, 'all original generated headers, no substituted stubs')
    OBS.update(state='MATCHING_INPUTS_PREPARED', affinity=[23], jobs=1,
        address_space_limit_bytes=2*1024**3, total_deadline_seconds=450,
        original_matching_preparation=preparation_ref, prior_matching_K0a_compile=old_compile_ref,
        source_packet=packet_ref, compiler_runner=script_ref, postimages=postimages,
        compiler=compiler, original_configuration=config_ref, original_saved_recipe=command_ref,
        source_makefiles=makefiles, original_objtool=tool, staged_objtool=staged_tool,
        original_source_before_checks=original_checks, original_configuration_changed=False,
        old_K0a_source_tree_modified=False, existing_grant_source_modified=False,
        compile_only_feature_macros=['CONFIG_P4_PRIVATE_LOOP_ACTOR=1','CONFIG_P4_PRIVATE_LOOP_LEASE=1','CONFIG_P4_PRIVATE_LOOP_REALM=1'],
        Kbuild_configuration_selection_executed=False, private_loop_issuer_enabled=False)
    OUT = OUT_ROOT
    run('gcc-version', [compiler['path'],'--version'])
    all_dependencies = {}
    for mode in ('enabled', 'disabled'):
        OUT = OUT_ROOT/mode; OUT.mkdir(mode=0o700)
        configuration = create(OUT/'.config', config_raw)
        for path, reference, body in original_generated:
            generated.append({'mode':mode,'original':reference,'copy':create(OUT/path,body)})
        units = NEW_UNITS+INHERITED_UNITS if mode == 'enabled' else NEW_UNITS[1:]
        for unit in units:
            label = mode+'-'+unit.replace('/','-')
            (OUT/unit).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            args = compiler_arguments(compile_command, unit, compiler)
            index = args.index('-c')
            if mode == 'enabled':
                args[index:index] = ['-DCONFIG_P4_PRIVATE_LOOP_ACTOR=1','-DCONFIG_P4_PRIVATE_LOOP_LEASE=1','-DCONFIG_P4_PRIVATE_LOOP_REALM=1']
                index = args.index('-c')
            scan = OUT/(unit+'.preflight.d')
            dep_args = [arg for arg in args[:index] if not arg.startswith('-Wp,-MMD,')]
            dep_args += ['-M','-MF',str(scan),args[-1]]
            OBS['state'] = 'REAL_GCC_DEPENDENCY_SCAN:'+label
            run(label+'-dependencies', dep_args)
            paths = dependencies(scan)
            need(SOURCE/'include/linux/fs_struct.h' not in paths
                 and SOURCE/'include/linux/blkdev.h' not in paths
                 and SOURCE/'include/linux/backing-dev-defs.h' not in paths,
                 'modified layout declarations cannot fall back to original headers')
            before = {str(path):read(path,retain=True)[0] for path in paths}
            all_dependencies.update(before)
            OBS['state'] = 'REAL_GCC_OBJECT_COMPILE:'+label
            run(label+'-compile',args)
            directory,basename=unit.rsplit('/',1)
            compiled=dependencies(OUT/directory/('.'+basename+'.o.d'))
            need(set(map(str,compiled)) == set(before), 'preflight and actual compiler dependency closure agree')
            for reference in before.values(): immutable(reference)
            object_path=OUT/(unit+'.o'); gcc_object=ref(object_path)
            objtool_args=shlex.split(objtool_command)
            need(objtool_args[0]=='./tools/objtool/objtool' and objtool_args[-1]=='kernel/p4_guest_mntns.o',
                 'original exact objtool recipe')
            objtool_args[0]=staged_tool['path'];objtool_args[-1]=unit+'.o'
            run(label+'-objtool',objtool_args)
            run(label+'-elf-header',['/usr/bin/readelf','-h',str(object_path)])
            run(label+'-symbols',['/usr/bin/nm',str(object_path)])
            symbols=(ROOT/'logs'/(label+'-symbols.stdout')).read_text()
            if mode == 'disabled':
                need('p4_private_loop_' not in symbols, 'default-off object has no private-loop link dependency')
            if unit == 'block/p4_private_loop_realm':
                for name in ('p4_private_loop_actor_check_task', 'p4_private_loop_lease_create',
                             'p4_private_loop_device_alloc_unpublished', 'p4_private_loop_device_retire_unpublished'):
                    need(' U '+name+'\n' in symbols, 'real existing actor/lease and native driver API calls')
                for name in ('p4_private_loop_realm_create', 'p4_private_loop_allocate_closed',
                             'p4_private_loop_retire_closed'):
                    need(' T '+name+'\n' in symbols, 'actual internal realm allocation and retirement compiled')
                need('__ksymtab' not in symbols, 'no new realm module symbol exports')
            if mode == 'enabled' and unit == 'drivers/block/loop':
                for name in ('blk_mq_alloc_tag_set', '__blk_mq_alloc_disk',
                             'blk_mq_free_tag_set', 'p4_private_loop_target_attach'):
                    need(' U '+name+'\n' in symbols, 'actual native allocator or closed target API')
                for name in ('p4_private_loop_device_alloc_unpublished',
                             'p4_private_loop_device_retire_unpublished'):
                    need(' T '+name+'\n' in symbols, 'actual unpublished native loop constructor/retirement')
            OBS['objects'].append({'mode':mode,'unit':unit,'compile_argv':args,
                'dependency_count':len(before),'gcc_object':gcc_object,'object_after_objtool':ref(object_path),
                'C_compiler_passed':True,'objtool_passed':True,'actual_dependency_closure_equal':True})
        immutable(configuration)
    for _,reference in HELD.values(): immutable(reference)
    for reference in postimages: immutable(reference)
    for entry in generated: immutable(entry['copy'])
    immutable(staged_tool)
    OBS.update(state='MATCHING_3_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED',
        dependency_count=len(all_dependencies),dependency_refs=list(all_dependencies.values()),
        generated_C_headers=generated,retained_original_refs=[row for _,row in HELD.values()],
        all_original_input_F9_and_complete_body_bookends_equal=True,
        actual_C_dependency_closures_equal=True,target_kernel_objects_compiled=True,
        full_kernel_built=False,live_actor_or_private_loop_issued=False,
        K1_complete=False,real_control_or_block_OFD_created=False,private_device_published=False)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        OBS.update(state='FAILED',error=type(error).__name__+': '+str(error))
        raise
    finally:
        for fd,_ in HELD.values(): os.close(fd)
        raw=(json.dumps(OBS,sort_keys=True,indent=2)+'\n').encode()
        create(RESULT,raw)
        print(json.dumps({'state':OBS['state'],'receipt':str(RESULT),'bytes':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'runtime_qualified':False,'production_ready':False}),flush=True)
