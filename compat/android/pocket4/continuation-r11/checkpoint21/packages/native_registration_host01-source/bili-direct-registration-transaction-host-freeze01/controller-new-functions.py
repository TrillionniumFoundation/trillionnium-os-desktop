
def fixture_inputs():
    result = {}
    for name, expected in FIXTURE_PINS.items():
        raw, row = held(HERE/name, 131072)
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'fixed fixture source differs: '+name)
        result[name] = raw
    require(not FIXTURE.exists() and not FIXTURE.is_symlink(), 'fixture root already exists')
    FIXTURE.mkdir(mode=0o700)
    (FIXTURE/'src').mkdir(mode=0o700)
    write_new(FIXTURE/'Cargo.toml', result['fixture-Cargo.toml'])
    write_new(FIXTURE/'src/lib.rs', result['fixture-lib.rs'])
    production, pin = held(COPIED/CONTROL_PATH, 131072)
    require(pin['bytes'] == CONTROL_PIN['bytes'] and pin['sha256'] == CONTROL_PIN['sha256'],
            'copied production coordinator differs before fixture composition')
    combined = production + result['transaction_tests.rs']
    write_new(FIXTURE/'src/control_under_test.rs', combined)
    require(combined[:len(production)] == production and
            combined[len(production):] == result['transaction_tests.rs'],
            'fixture does not preserve the full exact production prefix')
    return {'production_bytes': len(production), 'production_sha256': sha(production),
            'tests_bytes': len(result['transaction_tests.rs']),
            'tests_sha256': sha(result['transaction_tests.rs']),
            'combined_bytes': len(combined), 'combined_sha256': sha(combined),
            'production_method_body_substitution': False,
            'provider_substitution_scope': ['DenialPresentationSink', 'ComposerLifecycle'],
            'Android_Binder_adapters_compiled': False}


def selected_dependencies(metadata, registry, original_lock, fixture_lock):
    require(metadata.get('workspace_root') == str(FIXTURE) and
            metadata.get('target_directory') == str(OUT/'cargo-target') and
            type(metadata.get('packages')) is list and 0 < len(metadata['packages']) <= 64,
            'fixture metadata root/target/package bound differs')
    entries = metadata['packages']
    by_id = {p['id']:p for p in entries}
    require(len(by_id) == len(entries), 'duplicate metadata package identity')
    expected_paths = {name:str(COPIED/relative/'Cargo.toml') for name,relative in PATH_PACKAGES.items()}
    expected_paths[FIXTURE_NAME] = str(FIXTURE/'Cargo.toml')
    paths = [p for p in entries if p['source'] is None]
    require(len(paths) == len(expected_paths) and
            {p['name']:p['manifest_path'] for p in paths} == expected_paths,
            'path package closure differs from real five crates and explicit fixture')
    fixture = [p for p in paths if p['name'] == FIXTURE_NAME]
    require(len(fixture) == 1 and fixture[0]['version'] == '0.0.0' and
            metadata.get('workspace_members') == [fixture[0]['id']] and
            metadata.get('resolve',{}).get('root') == fixture[0]['id'] and
            {node['id'] for node in metadata['resolve']['nodes']} == set(by_id),
            'fixture resolver or workspace membership differs')
    def lock_rows(value):
        result = {}
        for row in value['package']:
            key = (row['name'], row['version'])
            require(key not in result, 'ambiguous original/new lock package')
            result[key] = row
        return result
    old = lock_rows(original_lock)
    new = lock_rows(fixture_lock)
    keys = {(p['name'],p['version']) for p in entries}
    require(set(new) == keys, 'new fixture lock and selected metadata package set differ')
    authority = {(r['name'],r['version']):r for r in registry['packages']}
    require(len(authority) == len(registry['packages']) == 45,
            'duplicate or incomplete qualified registry authority')
    descriptions = []
    collected = {}
    for p in entries:
        key = (p['name'],p['version'])
        locked = new[key]
        if p['source'] is None:
            require(locked.get('source') is None, 'path package acquired a registry source')
            if p['name'] != FIXTURE_NAME:
                require(key in old and old[key].get('source') is None,
                        'copied path package is absent from the immutable original lock')
            descriptions.append({'id':p['id'],'name':p['name'],'version':p['version'],
                                 'kind':'pinned-fixture' if p['name']==FIXTURE_NAME else 'pinned-source',
                                 'manifest':p['manifest_path']})
            continue
        require(key in old and p['source'] == locked.get('source') ==
                old[key].get('source') == 'registry+https://github.com/rust-lang/crates.io-index' and
                locked.get('checksum') == old[key].get('checksum') and
                re.fullmatch(r'[0-9a-f]{64}', locked.get('checksum','')) is not None,
                'offline resolver selected a package outside the immutable original lock')
        observed = authority.get(key)
        require(observed is not None and
                observed['expected_lock_checksum'] == locked['checksum'] and
                observed['comparison']['archive_matches_lock'] is True and
                observed['comparison']['every_archive_file_matches_held_extracted_source'] is True,
                'selected registry package lacks actual archive/source authority')
        directory = Path(observed['source_directory'])
        archive = Path(observed['expected_archive_path'])
        require(directory.is_relative_to(CARGO_HOME/'registry/src') and
                archive.is_relative_to(CARGO_HOME/'registry/cache') and
                p['manifest_path'] == str(directory/'Cargo.toml') and
                '..' not in directory.parts and '..' not in archive.parts,
                'selected registry source escaped its exact authority')
        real_directory(directory)
        real_directory(archive.parent)
        comparison, rows, archive_pin = qualify_cached_archive(
            archive, directory, key[0], key[1], locked['checksum'])
        require(archive_pin['sha256'] == observed['comparison']['archive']['sha256'],
                'selected cached archive changed from actual authority')
        collected[str(archive)] = archive_pin
        for row in rows.values():
            require(len(collected) < 16384, 'selected source closure exceeds file bound')
            collected[row['path']] = row
        manifest_raw, manifest_pin = held(directory/'Cargo.toml', 1024*1024)
        package = tomllib.loads(manifest_raw.decode())['package']
        require(package['name'] == key[0] and package['version'] == key[1] and
                manifest_pin == rows['Cargo.toml'], 'selected cached manifest differs')
        descriptions.append({'id':p['id'],'name':p['name'],'version':p['version'],
                             'kind':'offline-registry','manifest':p['manifest_path'],
                             'archive':archive_pin,'package_checksum':locked['checksum'],
                             'archive_to_source':comparison['source_inventory']})
    return fixture[0]['id'], descriptions, collected


def qualify_fixture_compile(raw, fixture_id, packages, dependency_rows, source_rows, fixture_rows):
    qualified = {p['manifest']:p for p in packages}
    ids = {p['id'] for p in packages}
    observed = set()
    artifacts = []
    completed = []
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        reason = item.get('reason')
        if reason == 'compiler-artifact':
            manifest = item.get('manifest_path')
            require(manifest in qualified and item['package_id'] == qualified[manifest]['id'],
                    'Cargo compiled an unqualified package')
            path = Path(item['target']['src_path'])
            row = dependency_rows.get(str(path))
            if row is None and path.is_relative_to(COPIED):
                row = source_rows.get(str(path.relative_to(COPIED)))
            if row is None and path.is_relative_to(FIXTURE):
                row = fixture_rows.get(str(path.relative_to(FIXTURE)))
            require(row is not None and hash_held(path) == row,
                    'actual compiled target was not in the prequalified source map')
            for filename in item['filenames']:
                require(Path(filename).is_relative_to(OUT/'cargo-target') and
                        '..' not in Path(filename).parts, 'compiled artifact escaped owned target')
            observed.add(item['package_id'])
            if item['package_id'] == fixture_id and item.get('executable'):
                require(item['profile']['test'] is True and item['target']['kind'] == ['lib'] and
                        item['target']['name'] == FIXTURE_NAME.replace('-','_') and
                        item['target']['src_path'] == str(FIXTURE/'src/lib.rs'),
                        'fixture executable is not its exact library test target')
                artifacts.append(Path(item['executable']))
        elif reason == 'build-script-executed':
            require(item['package_id'] in ids and Path(item['out_dir']).is_relative_to(OUT/'cargo-target'),
                    'unqualified build script or output directory')
        elif reason == 'build-finished':
            completed.append(item.get('success'))
        elif reason != 'compiler-message':
            raise RuntimeError('unexpected Cargo JSON record: '+str(reason))
    require(completed == [True] and observed and len(artifacts) == 1 and
            artifacts[0].is_relative_to(OUT/'cargo-target'), 'exact fixture compilation did not complete')
    return artifacts[0], sorted(observed)


def fixture_focused_test(binary, name, index, environment, records):
    path = OUT/('transaction-test-%02d.libtest' % index)
    fd = os.open(path, os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600 and
                before.st_size == 0, 'fresh independent libtest record claim differs')
        output = command([str(binary),'--exact',name,'--test-threads=1','--nocapture','--logfile',str(path)],
                         FIXTURE, environment, 'transaction-test-%02d' % index, records, 30).decode()
        after = os.fstat(fd)
        require((before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_gid,before.st_nlink) ==
                (after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_gid,after.st_nlink) and
                after.st_size <= 4096, 'held independent libtest record changed identity')
        raw = os.pread(fd,4097,0)
        require(len(raw) == after.st_size and identity(after) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held libtest content changed during full read')
        require(raw == ('ok '+name+'\n').encode(), 'independent libtest result is not exactly one success')
        summaries = [line for line in output.splitlines() if line.startswith('test result:')]
        pattern = r'test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; 26 filtered out; finished in \d+(?:\.\d+)?s'
        require(len(TESTS) == 27 and len(summaries) == 1 and re.fullmatch(pattern,summaries[0]) is not None and
                output.splitlines().count('running 1 test') == 1 and output.count('test '+name+' ... ') == 1,
                'stdout and independent libtest success disagree')
        gate = {'exact_name':name,'registered_tests':27,'filtered_out':26,'one_passed':True,
                'independent_logfile':{'path':str(path),'bytes':len(raw),'sha256':sha(raw),'identity':identity(after)}}
        records[-1]['focused_result_gate'] = gate
        return gate
    finally:
        os.close(fd)


def execute():
    global DEADLINE, CHILD_REAPER
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE/'compile_fixture.py', 'exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    (OUT/'tmp').mkdir(mode=0o700)
    DEADLINE = time.monotonic()+450
    report = {'schema':1,'state':'RUNNING','started_utc':utc(),
              'scope':'one exact Composer control.rs change; real coordinator/Core registry host regressions with explicit Denial/Composer I/O fixtures',
              'Main_actions':0,'Main_identity_observed':False,'install_actions':0,
              'Android_Binder_provider_compile':False,'Android_or_Soong_executed':False,
              'installed_Main_source_provenance_qualified':False,'actual_Bili_failure_cause_proven':False,
              'production_ready':False,'commands':[],'expected_test_names':TESTS,
              'network_downloads_permitted':False,'secondary_errors':[]}
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned controller interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    resource_fd = -1
    resource_before = None
    original_rows = {}
    candidate_rows = {}
    fixture_rows = {}
    dependency_rows = {}
    tool_rows = []
    config_rows = []
    config_paths = []
    test_pin = None
    test_binary = None
    def secondary(stage, error):
        report['state'] = 'FAIL'
        report['secondary_errors'].append({'stage':stage,'error':repr(error)})
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        allowed = sorted(os.sched_getaffinity(0))
        require(len(allowed) >= 3, 'cannot leave two logical CPUs free')
        os.sched_setaffinity(0, [allowed[-1]])
        report['allowed_cpus_before'] = allowed
        report['selected_cpus'] = [allowed[-1]]
        CHILD_REAPER = OwnChildReaper()
        CHILD_REAPER.begin()
        env = {'PATH':'/usr/bin:/bin','CARGO_HOME':str(CARGO_HOME),
               'RUSTC':str(RUST_SYSROOT/'bin/rustc'),'RUSTDOC':str(RUST_SYSROOT/'bin/rustdoc'),
               'CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C',
               'TMPDIR':str(OUT/'tmp'),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
               'PYTHONDONTWRITEBYTECODE':'1'}
        python = pin_resolved(Path(sys.executable),[Path('/usr/bin')])
        require(Path(sys.executable) == Path('/usr/bin/python3'), 'admitted Python interpreter path differs')
        tool_rows.append(python)
        report['admitted_python_runtime_observation'] = python
        run_child_lifecycle_controls(report, OUT, env)
        parent_raw, parent_pin = pinned_packet('parent469-result.json',
            '3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5')
        parent = json.loads(parent_raw)
        require(parent_pin['bytes'] == 170316 and parent['state'] == 'PASS' and
                len(parent['commands']) == 65 and
                all(row['returncode'] == 0 and not row['timed_out'] for row in parent['commands']) and
                parent['focused_tests_passed'] == 27 and parent['updater_focused_tests_passed'] == 18 and
                parent['source_resume_tests_passed'] == 9 and
                parent['source_delta']['actual_source_file_count'] == 499 and
                parent['copied_manifest']['bytes'] == 99327 and
                parent['copied_manifest']['sha256'] == PARENT_MANIFEST_SHA and
                parent['builder_elf']['bytes'] == 34767856 and
                parent['builder_elf']['sha256'] == 'c758a1e12bbc1925cc36f8cde3b369ab8449ad1cf460a9854b42d627575627d8' and
                parent['owned_resource_gate']['pass'] is True and
                parent['copied_source_unchanged_after'] is True and
                parent['original_source_unchanged_after'] is True and
                parent['cargo_configs_unchanged_after'] is True and
                not parent['tool_changes'] and not parent['dependency_changes'] and
                not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and
                parent['cleanup']['forced_cleanup'] is False and
                parent['runtime_authorization_enabled'] is False,
                'actual builder469 source/tool qualification differs')
        report['actual_parent469_source_authority'] = parent_pin
        old_raw, _ = pinned_packet('parent469-manifest.json', PARENT_MANIFEST_SHA)
        candidate_raw, _ = pinned_packet('candidate-source-manifest.json', CANDIDATE_MANIFEST_SHA)
        expected = json.loads(old_raw)
        candidate_expected = json.loads(candidate_raw)
        require(len(expected) == len(candidate_expected) == 499 and set(expected) == set(candidate_expected) and
                [name for name in expected if expected[name] != candidate_expected[name]] == [CONTROL_PATH] and
                expected[CONTROL_PATH]['bytes'] == 30368 and
                expected[CONTROL_PATH]['sha256'] == 'f2314f92862bab1d5354220ecb24954acdbbc536529daf36818b0a8974e1499c' and
                candidate_expected[CONTROL_PATH]['bytes'] == CONTROL_PIN['bytes'] and
                candidate_expected[CONTROL_PATH]['sha256'] == CONTROL_PIN['sha256'] and
                expected[CONTROL_PATH]['kind'] == candidate_expected[CONTROL_PATH]['kind'] == 'file' and
                expected[CONTROL_PATH]['mode'] == candidate_expected[CONTROL_PATH]['mode'],
                'candidate is not the single exact coordinator replacement')
        original_rows, copied_before = exact_source_copy(expected)
        report['original_manifest'] = write_new(OUT/'original-source-manifest.json', old_raw)
        data, delta_pin = held(HERE/'candidate-control.rs', 131072)
        require(delta_pin['bytes'] == CONTROL_PIN['bytes'] and delta_pin['sha256'] == CONTROL_PIN['sha256'],
                'candidate coordinator source changed before owned replacement')
        target = COPIED/CONTROL_PATH
        require(hash_held(target) == copied_before[CONTROL_PATH], 'copied baseline coordinator changed')
        fd = os.open(target, os.O_WRONLY|os.O_TRUNC|os.O_CLOEXEC|os.O_NOFOLLOW)
        with os.fdopen(fd,'wb') as stream:
            require(stream.write(data) == len(data), 'short copied coordinator write')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(target, candidate_expected[CONTROL_PATH]['mode'], follow_symlinks=False)
        candidate_rows = regular_tree(COPIED)
        portable(candidate_rows, candidate_expected)
        report['copied_manifest'] = write_new(OUT/'copied-source-manifest.json', candidate_raw)
        report['source_delta'] = {'file':CONTROL_PATH,'before':expected[CONTROL_PATH],
                                  'after':candidate_expected[CONTROL_PATH],'unchanged_files':498,
                                  'source_files':499,'Android_AIDL_adapters_changed':False}
        report['fixture_composition'] = fixture_inputs()
        selected_tools, compiler_rows = toolchain(report, env)
        tool_rows.extend(compiler_rows)
        report['tool_inputs'] = write_new(OUT/'tool-inputs-before.json', tool_rows)
        env.update({'PATH':str(selected_tools['cargo'].parent)+':/usr/bin:/bin',
                    'RUSTC':str(selected_tools['rustc']),'RUSTDOC':str(selected_tools['rustdoc']),
                    'RUSTDOCFLAGS':'','CARGO_ENCODED_RUSTDOCFLAGS':'',
                    'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',
                    'CARGO_TARGET_DIR':str(OUT/'cargo-target'),'CARGO_BUILD_JOBS':'1',
                    'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc'})
        require('/home/alex/.cargo/bin' not in env['PATH'].split(':') and
                all(shutil.which(name,path=env['PATH']) == str(selected_tools[name])
                    for name in ['cargo','rustc','rustdoc']) and
                not any(name.startswith('RUSTUP') for name in env) and
                all(name not in env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')),
                'fixed direct compiler tools were shadowed')
        config_paths = [CARGO_HOME/'config',CARGO_HOME/'config.toml']
        for directory in [COPIED,FIXTURE]:
            for parent_directory in [directory,*directory.parents]:
                config_paths += [parent_directory/'.cargo/config',parent_directory/'.cargo/config.toml']
        config_rows = read_existing_config(config_paths)
        require(config_rows and all(row.get('absent') is True for row in config_rows),
                'unqualified Cargo configuration is present')
        report['cargo_config_inputs_before'] = config_rows
        report['build_environment'] = env
        command([str(selected_tools['cargo']),'generate-lockfile','--offline'],
                FIXTURE,env,'fixture-lock-generation',report['commands'],30)
        generated_lock_raw, generated_lock_pin = held(FIXTURE/'Cargo.lock',1024*1024)
        original_lock_raw, original_lock_pin = held(COPIED/'Cargo.lock',1024*1024)
        require(original_lock_pin == candidate_rows['Cargo.lock'], 'immutable original Cargo.lock changed')
        report['generated_fixture_lock'] = generated_lock_pin
        report['original_lock'] = original_lock_pin
        metadata_raw = command([str(selected_tools['cargo']),'metadata','--offline','--locked',
                                '--format-version','1'],FIXTURE,env,'fixture-metadata',report['commands'],30)
        registry_raw, registry_pin = pinned_packet('registry-result.json',
            'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993')
        registry = json.loads(registry_raw)
        require(registry['state'] == 'PASS' and registry['collection_complete'] is True and
                registry['all_45_archive_and_source_matches'] is True and
                registry['authorities_unchanged_after'] is True and registry['owned_resource_gate']['pass'] is True,
                'actual existing registry qualification is incomplete')
        report['actual_registry_archive_authority'] = registry_pin
        fixture_id, packages, dependency_rows = selected_dependencies(
            json.loads(metadata_raw), registry, tomllib.loads(original_lock_raw.decode()),
            tomllib.loads(generated_lock_raw.decode()))
        report['dependency_inputs'] = write_new(OUT/'dependency-inputs-before.json',
                                                {'packages':packages,'files':dependency_rows})
        fixture_rows = regular_tree(FIXTURE,8,1024*1024)
        require(set(fixture_rows) == {'Cargo.toml','Cargo.lock','src/lib.rs','src/control_under_test.rs'} and
                fixture_rows['Cargo.lock'] == generated_lock_pin,
                'fresh fixture source inventory differs')
        report['fixture_inputs'] = write_new(OUT/'fixture-inputs-before.json',fixture_rows)
        built = command([str(selected_tools['cargo']),'test','--offline','--locked','-j','1',
                         '--lib','--no-run','--message-format=json-render-diagnostics'],
                         FIXTURE,env,'fixture-compile',report['commands'],180)
        test_binary, compiled_ids = qualify_fixture_compile(
            built,fixture_id,packages,dependency_rows,candidate_rows,fixture_rows)
        report['actual_compiled_package_ids'] = compiled_ids
        test_pin = hash_held(test_binary)
        require(stat.S_IMODE(test_pin['identity'][2]) & 0o111, 'actual test artifact is not executable')
        fd = os.open(test_binary,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            require(os.read(fd,4) == b'\x7fELF', 'actual test artifact is not a host ELF')
        finally:
            os.close(fd)
        listing = command([str(test_binary),'--list'],FIXTURE,env,'fixture-list',report['commands'],10).decode()
        listed = [line[:-6] for line in listing.splitlines() if line.endswith(': test')]
        require(len(listed) == len(set(listed)) == len(TESTS) == 27 and set(listed) == set(TESTS) and
                not any(line.endswith(': benchmark') for line in listing.splitlines()),
                'actual libtest registrations differ from 27 fixed controls')
        help_text = command([str(test_binary),'--help'],FIXTURE,env,'fixture-help',report['commands'],10).decode()
        require(re.search(r'^\s*--logfile\s',help_text,re.MULTILINE) is not None and
                'Write logs to the specified file' in help_text, 'independent libtest record option missing')
        report['actual_registered_test_count'] = len(listed)
        report['focused_result_gates'] = []
        for index,name in enumerate(TESTS):
            report['focused_result_gates'].append(fixture_focused_test(
                test_binary,name,index,env,report['commands']))
        require(hash_held(test_binary) == test_pin, 'actual test ELF changed during focused execution')
        report['test_elf'] = test_pin
        report['focused_tests_passed'] = len(report['focused_result_gates'])
        require(len(report['commands']) == 42 and
                all(row.get('returncode') == 0 and row['child_reaped'] and
                    row['owned_tree_cleanup_complete'] and row['pidfd_closed'] and row['output_fds_closed'] and
                    not row['timed_out'] and not row['descendants'] and
                    row.get('leader_alive_before_group_cleanup') is False and
                    row['first_error'] is None and not row['secondary_errors'] for row in report['commands']),
                'fixed fixture command sequence or strict driver cleanup differs')
        require(time.monotonic() < DEADLINE, 'host fixture work qualification deadline exhausted')
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__,'message':str(error),
                                  'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['observed_signals'] = OBSERVED_SIGNALS
        try:
            require(CHILD_REAPER is not None and CHILD_REAPER.active, 'owned subreaper was not established')
            CHILD_REAPER.finish()
        except Exception as error:
            secondary('owned_reaper_final',error)
        report['owned_child_reaper'] = None if CHILD_REAPER is None else CHILD_REAPER.record
        for label, root, before in [
            ('original_source',BASE_SOURCE,original_rows),
            ('copied_source',COPIED,candidate_rows),
            ('fixture_source',FIXTURE,fixture_rows),
        ]:
            try:
                unchanged = bool(before) and regular_tree(root) == before
                report[label+'_unchanged_after'] = unchanged
                require(unchanged, label+' full source identity/content changed or never qualified')
            except Exception as error:
                secondary(label+'_after',error)
        changes = []
        for path,row in dependency_rows.items():
            try:
                if hash_held(Path(path)) != row:
                    changes.append(path)
            except Exception as error:
                changes.append({'path':path,'error':repr(error)})
        report['dependency_changes'] = changes
        if changes:
            secondary('dependency_after', RuntimeError('qualified dependency changed'))
        report['tool_changes'] = verify_resolved(tool_rows)
        if not tool_rows or report['tool_changes']:
            secondary('tool_after', RuntimeError('used tool closure missing or changed'))
        try:
            report['cargo_configs_unchanged_after'] = bool(config_rows) and read_existing_config(config_paths) == config_rows
            require(report['cargo_configs_unchanged_after'], 'Cargo config set changed or was never qualified')
        except Exception as error:
            secondary('cargo_configs_after',error)
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission not observed')
            report['owned_resource_gate'] = finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            secondary('owned_resources_after',error)
        finally:
            if resource_fd >= 0:
                value, resource_fd = resource_fd, -1
                try:
                    os.close(value)
                    report['owned_resource_fd_closed'] = True
                except Exception as error:
                    report['owned_resource_fd_closed'] = False
                    secondary('owned_resource_fd_close',error)
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json',report)
        print(json.dumps({'state':report['state'],'result':result,'test_elf':report.get('test_elf'),
                          'Main_actions':0,'Android_Binder_provider_compile':False,
                          'focused_tests_passed':report.get('focused_tests_passed',0)}),flush=True)
    return 0 if report['state'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'base_source':str(BASE_SOURCE),
                          'requires_explicit_execute_once':True,'production_files_changed':1,
                          'source_files':499,'focused_test_names':TESTS,
                          'host_fixture_only':True,'Main_actions':0,'Android_execution':False}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: compile_fixture.py [--execute-once]')
