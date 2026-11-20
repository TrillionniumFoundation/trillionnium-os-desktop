#!/usr/bin/python3
"""Compile isolated K0b objects using the actual matching 6.18.64 inputs.

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

ROOT = Path('/home/alex/work/p4-private-loop-k0b-20261120-3b9d-r1')
OLD = Path('/home/alex/work/p4-private-loop-k0a-compile-20261120-3b9d-r1')
SOURCE = OLD / 'source/linux-6.18.64'
OVERLAY = ROOT / 'overlay'
OUT = ROOT / 'out'
RESULT = ROOT / 'OBJECT-COMPILE.json'
DEADLINE = None
HELD = {}
OBS = {'schema': 'p4-k0b-matching-kernel-object-compile-v1', 'state': 'PENDING',
       'commands': [], 'objects': [], 'kernel_linked': False, 'kernel_loaded': False,
       'kernel_installed': False, 'VM_started': False, 'Android_started': False,
       'kernel_runtime_tests_executed': False, 'runtime_qualified': False,
       'production_ready': False, 'Kbuild_configuration_selection_executed': False}
UNITS = ('fs/fs_struct', 'block/p4_private_loop_actor', 'kernel/fork',
         'fs/exec', 'kernel/p4_guest_mntns')


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
        result.append(arg)
    # The only additional include directory contains exactly the two reviewed
    # headers. All architecture/config/generated headers remain original.
    position = result.index('-I'+str(SOURCE/'include'))
    result.insert(position, '-I'+str(OVERLAY/'include'))
    source = OVERLAY/(unit+'.c') if unit in UNITS[:2] else SOURCE/(unit+'.c')
    result[-1] = str(source)
    index = result.index('-c')
    need(result[index:index+3] == ['-c', '-o', unit+'.o'], 'one isolated selected C output')
    return result


def alarm(signum, frame):
    raise TimeoutError('bounded K0b object compile expired')


def main():
    global DEADLINE
    need(os.getuid() == os.geteuid() == os.getgid() == 1000, 'ordinary nonprivileged Pocket4 owner')
    need(ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE
         and not os.path.lexists(RESULT), 'original tree and fresh isolated result')
    need(23 in os.sched_getaffinity(0), 'reserved independent CPU23')
    os.sched_setaffinity(0, {23}); os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))
    signal.signal(signal.SIGALRM, alarm); signal.alarm(240); DEADLINE = time.monotonic()+220
    audit_ref, raw = read(ROOT/'FIXED-FS-LIFETIME-AUDIT.json',
        {'bytes':89735,'sha256':'3e50402974edc061da06e8eff21dc0f8a12b648d8b5b384c06ed0da182586f82'}, True)
    audit = json.loads(raw)
    originals = {row['reference']['path']: row['reference'] for row in audit['files']}
    for row in [*audit['all_66_final_candidate_and_4_K0a_bodies_checked'], *originals.values()]:
        reference, _ = read(row['path'], row, True)
        need(reference == row, 'same actually audited original complete source identity')
    preparation_ref, raw = read(OLD/'TREE-PREPARATION.json',
        {'bytes':23008,'sha256':'232793bb6e70cfdd0aba664c1a0be17f2a623d465cc2507a884582f65f18b243'}, True)
    preparation = json.loads(raw)
    old_compile_ref, raw = read(OLD/'OBJECT-COMPILE.json',
        {'bytes':251396,'sha256':'6b47c885ba790987a3adb0b18a327068529e9ac612964fd05eb0c5393e0c532d'}, True)
    old_compile = json.loads(raw)
    need(old_compile['state'] == 'MATCHING_KERNEL_C_OBJECT_AND_ORIGINAL_OBJTOOL_PASSED',
         'actual complete prior matching compile')
    script_ref, _ = read(Path(__file__), retain=True)
    packet_ref, raw = read(ROOT/'SOURCE-PACKET.json',
        {'bytes':17339,'sha256':'352b228f3cc5b0c05b45bde68483741595e03ea474639ec1ab5f6f5cd8995f40'}, True)
    packet = json.loads(raw); manifest = packet['manifest']
    need(manifest['schema'] == 'p4-k0b-independent-fs-lifetime-source-v1'
         and manifest['base_K0a_commit'] == '0bf19546e570a80247a5982d292de463cf0f4496'
         and manifest['kernel_compiled'] is False and len(manifest['files']) == 4,
         'explicit source-only K0b input packet')
    need(set(packet['sources']) == {x['path'] for x in manifest['files']} == {
        'include/linux/fs_struct.h', 'include/linux/p4_private_loop_actor.h',
        'block/p4_private_loop_actor.c', 'fs/fs_struct.c'}, 'only four exact reviewed postimages')
    need(os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize >= 1024**3,
         'at least 1 GiB actual free space for isolated objects and logs')
    for directory in (OVERLAY, OUT, ROOT/'logs'):
        need(not os.path.lexists(directory), 'create-only new compile directory')
        directory.mkdir(mode=0o700)
    postimages = []
    for entry in manifest['files']:
        original_ref, _ = read(SOURCE/entry['path'], entry['before'], True)
        raw = packet['sources'][entry['path']].encode()
        need((len(raw),hashlib.sha256(raw).hexdigest())
             == (entry['after']['bytes'],entry['after']['sha256']), 'whole exact reviewed postimage')
        postimages.append(create(OVERLAY/entry['path'], raw))
    generated = []
    config_ref, raw = read(OLD/'out/.config',
        {'bytes':304072,'sha256':'bccb147083a909408e25dc63f1dd58cf465ee19bcabc660916a1fa28cc67a3e1'}, True)
    configuration = create(OUT/'.config', raw)
    for entry in preparation['generated_C_headers']:
        original, raw = read(OLD/'out'/entry['path'], entry, True)
        generated.append({'original': original, 'copy': create(OUT/entry['path'], raw)})
    need(len(generated) == 43, 'all original actually generated C headers, without substitutes')
    for directory in ('block', 'fs', 'kernel'):
        (OUT/directory).mkdir(mode=0o700)
    compiler, _ = read(old_compile['compiler']['path'], old_compile['compiler'], True)
    need(compiler == old_compile['compiler'], 'same actual GCC binary and full identity')
    linker, _ = read(old_compile['linker']['path'], old_compile['linker'], True)
    command_ref, raw = read(OLD/'inputs/COMPILE-COMMAND-SOURCE.json',
        preparation['input_refs']['COMPILE-COMMAND-SOURCE.json'], True)
    commands = json.loads(raw)
    need(commands[1]['active_config_differences'] == [
        {'key':'CONFIG_LOCK_DOWN_IN_SECURE_BOOT','tu':None,'full':'y'},
        {'key':'CONFIG_SECURITY_PERF_EVENTS_RESTRICT','tu':None,'full':'y'}],
        'same two explicit original security configuration additions')
    prefix = 'savedcmd_kernel/p4_guest_mntns.o := '
    saved = commands[0]['command']
    need(saved.startswith(prefix) and saved.count(' ; ') == 1, 'complete original compile and objtool recipe')
    compile_command, objtool_command = saved[len(prefix):].split(' ; ')
    makefiles = []
    for name, size, sha in (('fs/Makefile',4461,'2f119848d8b5a1659e24697adf5f05ee3372f6a49137ed7ac66130613f3ceec2'),
                            ('kernel/Makefile',7251,'4e782a200ab368e5418e52e8c98123c7359970a44ff96d4e0451db27e081739a')):
        reference, _ = read(SOURCE/name, {'bytes':size,'sha256':sha}, True)
        makefiles.append(reference)
    tool, raw = read(OLD/'inputs/objtool-original',
        {'bytes':979400,'sha256':'2453a7416b1f9aa1799ee6c900ef5dba6641182f99f5a8b50b604c106959e3ba'}, True)
    staged_tool = create(ROOT/'objtool-staged', raw, 0o700)
    OBS.update(state='MATCHING_INPUTS_PREPARED', affinity=[23], jobs=1,
        address_space_limit_bytes=2*1024**3, total_deadline_seconds=220,
        fixed_original_source_audit=audit_ref, original_matching_preparation=preparation_ref,
        prior_matching_K0a_compile=old_compile_ref, source_packet=packet_ref, compiler_runner=script_ref,
        postimages=postimages, compiler=compiler, linker=linker, configuration=configuration,
        original_configuration=config_ref, generated_C_headers=generated,
        original_saved_recipe=command_ref, source_makefiles=makefiles,
        original_objtool=tool, staged_objtool=staged_tool, configuration_changed=False,
        old_K0a_source_tree_modified=False, existing_grant_source_modified=False)
    run('gcc-version', [compiler['path'], '--version'])
    result = run('new-reference-symbol-collision', ['/usr/bin/rg', '-n', '--no-heading', '--color', 'never',
        '--glob', '*.[ch]', '--', r'\b(get_fs_struct_ref|put_fs_struct_ref)\b', str(SOURCE)], expected=1)
    need(result['stdout']['bytes'] == 0, 'new lifetime symbols do not collide with an existing implementation')
    all_dependencies = {}
    for unit in UNITS:
        label = unit.replace('/', '-')
        args = compiler_arguments(compile_command, unit, compiler)
        index = args.index('-c')
        scan = OUT/(unit+'.preflight.d')
        dep_args = [arg for arg in args[:index] if not arg.startswith('-Wp,-MMD,')]
        dep_args += ['-M', '-MF', str(scan), args[-1]]
        OBS['state'] = 'REAL_GCC_DEPENDENCY_SCAN:'+unit
        run(label+'-dependencies', dep_args)
        paths = dependencies(scan)
        need(OVERLAY/'include/linux/fs_struct.h' in paths
             and SOURCE/'include/linux/fs_struct.h' not in paths,
             'each actual translation unit uses precisely the new fs lifetime declaration')
        before = {str(path): read(path, retain=True)[0] for path in paths}
        all_dependencies.update(before)
        OBS['state'] = 'REAL_GCC_OBJECT_COMPILE:'+unit
        run(label+'-compile', args)
        directory, basename = unit.rsplit('/', 1)
        compiled_dependencies = dependencies(OUT/directory/('.'+basename+'.o.d'))
        need(set(map(str, compiled_dependencies)) == set(before),
             'actual scanned and compiled dependency closures agree')
        for reference in before.values(): immutable(reference)
        object_path = OUT/(unit+'.o'); gcc_object = ref(object_path)
        objtool_args = shlex.split(objtool_command)
        need(objtool_args[0] == './tools/objtool/objtool' and objtool_args[-1] == 'kernel/p4_guest_mntns.o',
             'original fixed objtool recipe')
        objtool_args[0] = staged_tool['path']; objtool_args[-1] = unit+'.o'
        run(label+'-objtool', objtool_args)
        run(label+'-elf-header', ['/usr/bin/readelf', '-h', str(object_path)])
        run(label+'-symbols', ['/usr/bin/nm', str(object_path)])
        if unit == 'fs/fs_struct':
            symbols = (ROOT/'logs'/(label+'-symbols.stdout')).read_text()
            for name in ('get_fs_struct_ref','put_fs_struct_ref','free_fs_struct','copy_fs_struct','exit_fs'):
                need(' T '+name+'\n' in symbols, 'actual fs lifetime definition compiled: '+name)
        if unit == 'block/p4_private_loop_actor':
            symbols = (ROOT/'logs'/(label+'-symbols.stdout')).read_text()
            for name in ('get_fs_struct_ref','put_fs_struct_ref'):
                need(' U '+name+'\n' in symbols, 'actual actor calls the independent lifetime API')
            need(' U free_fs_struct\n' not in symbols, 'actor no longer retires users aggregate')
        OBS['objects'].append({'unit': unit, 'compile_argv': args,
            'dependency_count': len(before), 'gcc_object': gcc_object,
            'object_after_objtool': ref(object_path), 'C_compiler_passed': True,
            'objtool_passed': True, 'actual_dependency_closure_equal': True})
    for _, reference in HELD.values(): immutable(reference)
    for reference in postimages: immutable(reference)
    for entry in generated: immutable(entry['copy'])
    immutable(configuration); immutable(staged_tool)
    OBS.update(state='MATCHING_FIVE_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED',
        dependency_count=len(all_dependencies), dependency_refs=list(all_dependencies.values()),
        retained_original_refs=[reference for _,reference in HELD.values()],
        all_original_input_F9_and_complete_body_bookends_equal=True,
        actual_C_dependency_closures_equal=True, target_kernel_objects_compiled=True,
        full_kernel_built=False, live_actor_or_private_loop_issued=False)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        OBS.update(state='FAILED', error=type(error).__name__+': '+str(error))
        raise
    finally:
        for fd, _ in HELD.values():
            os.close(fd)
        raw = (json.dumps(OBS, sort_keys=True, indent=2)+'\n').encode()
        create(RESULT, raw)
        print(json.dumps({'state': OBS['state'], 'receipt': str(RESULT), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'runtime_qualified': False,
            'production_ready': False}), flush=True)
