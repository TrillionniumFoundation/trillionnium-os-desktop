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
