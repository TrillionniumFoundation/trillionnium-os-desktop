#!/usr/bin/env python3
"""Assemble a create-only ordinary-owner object compile, never a kernel run."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
manifest = json.loads((ROOT/'MANIFEST.json').read_bytes())
k0b = json.loads((PARENT/'p4_private_loop_k0b/MANIFEST.json').read_bytes())
packet = {'schema':'p4-k0c-matching-object-source-packet-v1', 'manifest':manifest,
    'sources':{row['path']:(ROOT/'candidate'/row['path']).read_text()
        for row in manifest['files']+manifest['unchanged_K0b_inherited_files']},
    'original_checks':[{**row['before'], 'path':row['path']}
        for row in manifest['files'] if row['before']] +
        [{**row['before'], 'path':row['path']} for row in k0b['files']],
    'fresh_original_inputs':json.loads((ROOT/'ORIGINAL-INPUTS.json').read_bytes())}
raw = (json.dumps(packet,sort_keys=True,indent=2)+'\n').encode()
(ROOT/'SOURCE-PACKET.json').write_bytes(raw)
packet_pin={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
old=(PARENT/'p4_private_loop_k0b/compile_objects.py').read_text()
prefix=old[:old.index('def main():')]
prefix=prefix.replace('p4-private-loop-k0b-20261120-3b9d-r1','p4-private-loop-k0c-20261120-3b9d-r2')
prefix=prefix.replace('p4-k0b-matching-kernel-object-compile-v1','p4-k0c-matching-closed-block-object-compile-v1')
prefix=prefix.replace('OUT = ROOT / \'out\'', 'OUT_ROOT = ROOT / \'out\'\nOUT = OUT_ROOT')
start=prefix.index('UNITS = ');end=prefix.index('\n\n\n',start)
prefix=prefix[:start]+'''NEW_UNITS = ('block/p4_private_loop_lease', 'block/fops', 'block/ioctl',
    'block/bdev', 'block/genhd', 'block/blk-sysfs', 'block/blk-core',
    'block/partitions/core', 'drivers/block/loop', 'mm/backing-dev')
INHERITED_UNITS = ('fs/fs_struct', 'block/p4_private_loop_actor', 'kernel/fork',
    'fs/exec', 'kernel/p4_guest_mntns')'''+prefix[end:]
prefix=prefix.replace('source = OVERLAY/(unit+\'.c\') if unit in UNITS[:2] else SOURCE/(unit+\'.c\')',
    'source = OVERLAY/(unit+\'.c\') if (OVERLAY/(unit+\'.c\')).is_file() else SOURCE/(unit+\'.c\')')
assert prefix.count('        result.append(arg)') == 1
prefix=prefix.replace('        result.append(arg)', '''        # Actual scripts/Makefile.lib name-fix-token; MODFILE remains a path.
        if arg.startswith(('-DKBUILD_BASENAME=', '-DKBUILD_MODNAME=', '-D__KBUILD_MODNAME=')):
            key, value = arg.split('=', 1)
            arg = key + '=' + value.replace('-', '_').replace(',', '_')
        result.append(arg)''')
prefix=prefix.replace('# The only additional include directory contains exactly the two reviewed\n    # headers.',
    '# The additional include directory contains exactly the reviewed\n    # K0b/K0c headers.')
prefix=prefix.replace("raise TimeoutError('bounded K0b object compile expired')", "raise TimeoutError('bounded K0c object compile expired')")
prefix=prefix.replace('Compile isolated K0b objects', 'Compile isolated K0c enabled/disabled objects')

main='''def main():
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
    need(packet['schema'] == 'p4-k0c-matching-object-source-packet-v1'
         and manifest['base_K0b_commit'] == '69e7c31c9e7e34fa39d3422df1c22d4c5f33d9ce'
         and manifest['kernel_version'] == '6.18.64' and len(manifest['files']) == 15
         and manifest['issuer_enabled'] is False and manifest['production_ready'] is False,
         'exact closed source-only K0c packet')
    needed = manifest['files']+manifest['unchanged_K0b_inherited_files']
    need(len(needed) == 19 and set(packet['sources']) == {row['path'] for row in needed},
         'only 15 new/changed postimages and four unchanged K0b source bodies')
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
    need(b'CONFIG_BLK_DEV_LOOP=y\\n' in config_raw, 'matching built-in original loop driver')
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
        compile_only_feature_macros=['CONFIG_P4_PRIVATE_LOOP_ACTOR=1','CONFIG_P4_PRIVATE_LOOP_LEASE=1'],
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
                args[index:index] = ['-DCONFIG_P4_PRIVATE_LOOP_ACTOR=1','-DCONFIG_P4_PRIVATE_LOOP_LEASE=1']
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
            if unit == 'block/p4_private_loop_lease':
                for name in ('p4_private_loop_actor_get','p4_private_loop_actor_put','p4_private_loop_actor_check_task'):
                    need(' U '+name+'\\n' in symbols, 'real K0b actor references linked into compiled foundation')
                for name in ('p4_private_loop_disk_gate','p4_private_loop_bdi_gate','p4_private_loop_authorization_bind'):
                    need(' T '+name+'\\n' in symbols, 'actual closed gate/OFD constructor compiled')
                need('__ksymtab' not in symbols, 'no new module symbol exports')
            OBS['objects'].append({'mode':mode,'unit':unit,'compile_argv':args,
                'dependency_count':len(before),'gcc_object':gcc_object,'object_after_objtool':ref(object_path),
                'C_compiler_passed':True,'objtool_passed':True,'actual_dependency_closure_equal':True})
        immutable(configuration)
    for _,reference in HELD.values(): immutable(reference)
    for reference in postimages: immutable(reference)
    for entry in generated: immutable(entry['copy'])
    immutable(staged_tool)
    OBS.update(state='MATCHING_24_C_OBJECTS_AND_ORIGINAL_OBJTOOL_PASSED',
        dependency_count=len(all_dependencies),dependency_refs=list(all_dependencies.values()),
        generated_C_headers=generated,retained_original_refs=[row for _,row in HELD.values()],
        all_original_input_F9_and_complete_body_bookends_equal=True,
        actual_C_dependency_closures_equal=True,target_kernel_objects_compiled=True,
        full_kernel_built=False,live_actor_or_private_loop_issued=False)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        OBS.update(state='FAILED',error=type(error).__name__+': '+str(error))
        raise
    finally:
        for fd,_ in HELD.values(): os.close(fd)
        raw=(json.dumps(OBS,sort_keys=True,indent=2)+'\\n').encode()
        create(RESULT,raw)
        print(json.dumps({'state':OBS['state'],'receipt':str(RESULT),'bytes':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'runtime_qualified':False,'production_ready':False}),flush=True)
'''
runner=prefix+'PACKET_PIN = '+repr(packet_pin)+'\n\n'+main
compile(runner,'compile_objects.py','exec')
(ROOT/'compile_objects.py').write_text(runner)
print(json.dumps({'source_packet':packet_pin,'runner':{'bytes':len(runner.encode()),'sha256':hashlib.sha256(runner.encode()).hexdigest()}}))
