def failure_detail(error, phase):
    frames = []
    trace = error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        frames.append({'file': code.co_filename, 'function': code.co_name, 'line': trace.tb_lineno})
        trace = trace.tb_next
    return {'phase': phase, 'type': type(error).__name__, 'repr': repr(error),
        'errno': getattr(error, 'errno', None),
        'filename': str(error.filename) if getattr(error, 'filename', None) is not None else None,
        'frames': frames[:64]}


def owner_identity(path, owner=1000):
    path = P(path)
    no_alias(path.parent)
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode) and value.st_uid == owner and value.st_gid == owner and
            not value.st_mode & 0o6002, 'owned regular input required: ' + str(path))
    return {'path': str(path), 'uid': value.st_uid, 'gid': value.st_gid,
        'nlink': value.st_nlink, 'identity': identity(value)}


def authority(name, observations):
    expected = AUTHORITIES[name]
    path = P(expected['path'])
    document, observed = pinned_json(path, expected['sha256'], expected['bytes'])
    require(observed['bytes'] == expected['bytes'] and
            ('identity' not in expected or observed['identity'] == expected['identity']),
            'authority byte count or exact original identity differs: ' + name)
    observations[name] = {'pin': observed, 'owner': owner_identity(path)}
    return document


def source_observation(manifest):
    no_alias(SOURCE)
    root = SOURCE.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == root.st_gid == 1000 and
            not root.st_mode & 0o002, 'current source directory owner differs')
    require(inventory(SOURCE) == manifest, 'complete current 498-file map differs')
    files = {}
    for name in sorted(manifest):
        path = SOURCE / name
        files[name] = {'pin': hash_held(path), 'owner': owner_identity(path)}
    directories = {}
    for here, names, unused in os.walk(SOURCE, followlinks=False):
        for path in [P(here), *(P(here) / name for name in names)]:
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 1000 and
                    not info.st_mode & 0o002, 'current source directory identity differs')
            directories[str(path.relative_to(SOURCE))] = {
                'identity': identity(info), 'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink}
    return {'files': files, 'directories': directories}


def current_artifact(row, path):
    require(row['path'] == row['resolved_path'] == str(path), 'exact current artifact path required')
    observed = hash_pin(path)
    require(observed == row and observed['identity'][2] & 0o111,
            'existing qualified builder470 artifact identity or bytes changed')
    return {'pin': observed, 'owner': owner_identity(path)}


def verify_source_ancestry(old491, old493, current):
    require(len(old491) == 491 and len(old493) == 493 and len(current) == 498,
            'closed source ancestry counts differ')
    expected_changed = ['tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/native_role_ingress.rs']
    changes = []
    for label, earlier, later, added in [
        ('491-to-493', old491, old493, [
            'android/manifest/m2-role-ingress-provider2-source-lock.json',
            'android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp']),
        ('493-to-498', old493, current, EXPECTED_SOURCE_DELTA['added']),
    ]:
        changed = sorted(name for name in earlier if later.get(name) != earlier[name])
        observed_added = sorted(set(later) - set(earlier))
        require(set(earlier) <= set(later) and changed == expected_changed and observed_added == added,
                'exact retained source ancestry differs: ' + label)
        changes.append({'stage': label, 'changed': changed, 'added': observed_added,
                        'removed': [], 'unchanged_count': len(earlier) - len(changed)})
    unchanged = [name for name in current if name.startswith('tools/droidloom-source/')]
    unchanged += ['Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml']
    require(len(set(unchanged)) == 7 and
            all(old491[name] == old493[name] == current[name] for name in unchanged),
            'source-resume library, dependency declarations or pinned toolchain changed')
    require(current['android/manifest/m2-role-ingress-provider3-source-lock.json']['sha256'] ==
            'f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772',
            'current exact provider3 lock changed')
    return {'transitions': changes, 'unchanged_resume_and_cargo_inputs': sorted(unchanged),
            'legacy_source_directories_claimed_current': False}


def cargo_config_paths():
    paths = set()
    for parent in [SOURCE, *SOURCE.parents, P('/home/alex/.cargo')]:
        for name in ('config', 'config.toml'):
            paths.add(parent / ('.cargo/' + name) if parent != P('/home/alex/.cargo') else parent / name)
    return sorted(paths)


def no_cargo_config(paths):
    require(all(not path.exists() and not path.is_symlink() for path in paths),
            'unexpected Cargo configuration input')


def fd_census():
    require(len(os.listdir('/proc/self/task')) == 1, 'single owned controller thread required')
    observed = {}
    for value in os.listdir('/proc/self/fd'):
        try:
            fd = int(value)
            info = os.fstat(fd)
            observed[value] = {'target': os.readlink('/proc/self/fd/' + value),
                'identity': [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink],
                'fd_flags': fcntl.fcntl(fd, fcntl.F_GETFD), 'file_flags': fcntl.fcntl(fd, fcntl.F_GETFL)}
        except OSError as error:
            if error.errno not in (errno.EBADF, errno.ENOENT):
                raise
    return observed


def explicit_library_baseline():
    # The existing owned-bootstrap probe established that importing _ctypes
    # opens this process-lifetime library FD. Bind it at an explicit early phase;
    # never adopt an unknown descriptor found after work has started.
    global ctypes
    require('ctypes' not in sys.modules and '_ctypes' not in sys.modules,
            'fresh explicit ctypes import required')
    inherited = fd_census()
    require(set(inherited) == {'0', '1', '2'}, 'only stdio may be inherited')
    import ctypes
    descriptors = fd_census()
    require(all(descriptors.get(name) == row for name, row in inherited.items()),
            'stdio changed during explicit ctypes import')
    require(set(descriptors) == {'0', '1', '2', '3'}, 'only stdio and explicit ctypes library are allowed')
    library = descriptors['3']
    require(library['target'] == LIBFFI['path'] and library['identity'] ==
            [66306, 108020388, 33188, 0, 0, 1] and library['fd_flags'] == fcntl.FD_CLOEXEC and
            library['file_flags'] == 32768,
            'explicit ctypes library descriptor differs')
    first = os.fstat(3)
    content = os.pread(3, LIBFFI['bytes'] + 1, 0)
    final = os.fstat(3)
    named = P(LIBFFI['path']).lstat()
    require(len(content) == LIBFFI['bytes'] == first.st_size and sha(content) == LIBFFI['sha256'] and
            identity(first) == identity(final) == identity(named) == LIBFFI['identity'],
            'explicit library pin changed')
    return descriptors, {'path': LIBFFI['path'], 'bytes': len(content), 'sha256': sha(content),
                         'inherited_stdio': inherited, 'explicit_import_added_FDs': ['3'],
                         'identity': identity(first), 'manual_close': False,
                         'retirement': 'authoritative durable normal process exit'}


def final_descriptor_gate(before, library):
    require(fd_census() == before, 'owned descriptor identities differ after qualification')
    require(identity(os.fstat(3)) == library['identity'] == identity(P(LIBFFI['path']).lstat()),
            'explicit process-lifetime library changed')


def current_receipt_outputs(receipt):
    checked = []
    for row in receipt['commands']:
        for stream in ('stdout', 'stderr'):
            path = P(row[stream]['path'])
            require(path.parent == ACTIVE / 'compile01' and hash_held(path, 32 * 1024 * 1024) == row[stream],
                    'actual current compile output identity changed')
            checked.append({'pin': row[stream], 'owner': owner_identity(path)})
    for index, name in enumerate(TESTS):
        expected = receipt['commands'][index + 4]['independent_libtest_result']
        path = ACTIVE / 'compile01' / ('projection-test-' + str(index) + '.libtest')
        raw, observed = held(path, 4096)
        require(observed == expected and raw == ('ok ' + name + '\n').encode(),
                'original current independent result changed')
        checked.append({'pin': observed, 'owner': owner_identity(path)})
    return checked


def registered_tests(executable, name, expected, required, environment, records):
    output = command([str(executable), '--list'], SOURCE, environment, name, records, 20).decode()
    observed = [line[:-6] for line in output.splitlines() if line.endswith(': test')]
    require(len(observed) == len(set(observed)) == expected and set(required) <= set(observed),
            'exact current test registration differs')
    return observed


def qualification_complete(result):
    return (result.get('errors') == [] and
            result.get('cleanup') == {'complete': True, 'children': [], 'errors': []} and
            set(result.get('gates', {})) == set(EXPECTED_GATES) and
            all(value is True for value in result['gates'].values()) and
            [row.get('label') for row in result.get('commands', [])] == EXPECTED_FRESH_LABELS and
            all(row.get('returncode') == 0 and row.get('timed_out') is False for row in result['commands']) and
            result.get('command_count') == 34 and result.get('tests_passed') == 28 and
            [row.get('exact_name') for row in result.get('fresh_updater_independent_result_gates', [])] == TESTS and
            [row.get('exact_name') for row in result.get('fresh_source_resume_independent_result_gates', [])] == SOURCE_TESTS)


def run_current_qualification(expected_source_sha):
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000,
            'unprivileged original operator required')
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    no_alias(ROOT)
    root_info = ROOT.lstat()
    require(stat.S_ISDIR(root_info.st_mode) and root_info.st_uid == root_info.st_gid == 1000 and
            stat.S_IMODE(root_info.st_mode) == 0o700 and
            set(os.listdir(ROOT)) == {'qualify_current470.py', 'stage-receipt.json'},
            'fresh closed current-qualification stage required')
    own_raw, own_pin = held(P(__file__), 131072)
    require(own_pin['sha256'] == expected_source_sha and P(__file__) == ROOT / 'qualify_current470.py',
            'fixed qualifier source differs')
    own_info = P(__file__).lstat()
    require(own_info.st_uid == own_info.st_gid == 1000 and own_info.st_nlink == 1 and
            stat.S_IMODE(own_info.st_mode) == 0o400, 'fixed qualifier source owner/mode differs')
    stage_raw, stage_pin = held(ROOT / 'stage-receipt.json', 65536)
    stage_receipt = json.loads(stage_raw)
    stage_owner = owner_identity(ROOT / 'stage-receipt.json')
    require(stage_receipt['schema'] == 'pocket4-current470-qualification-stage-v1' and
            stage_receipt['state'] == 'SOURCE_STAGED_ONLY' and
            stage_receipt['qualifier_source'] == own_pin and
            stage_receipt['compiler_invoked'] is False and stage_receipt['Main_actions'] == 0,
            'closed new stage receipt does not bind this qualifier source')
    require(not OUT.exists(), 'qualification output already exists; reconcile original job')
    OUT.mkdir(mode=0o700)
    before, library = explicit_library_baseline()
    records = []
    errors = []
    observations = {}
    current = old491 = old493 = source_before = None
    dependencies = dependency_owners = tools_before = tool_owners = None
    configs = None
    current_artifacts = None
    current_output_pins = None
    cgroup = None
    result = {'schema': 'pocket4-builder470-explicit-current-qualification-v1',
        'state': 'FAILED_BEFORE_QUALIFICATION', 'started_utc': utc(),
        'qualifier_source': own_pin, 'stage_receipt': stage_pin, 'explicit_library_resource': library,
        'Main_actions': 0, 'Android_actions': 0, 'install_actions': 0,
        'Soong_invoked': False, 'runtime_authorization_enabled': False,
        'full_Android_Java_JNI_compiled': False, 'production_ready': False, 'cleanup_eligible': False,
        'new_authorization_contract_connected': False, 'historical_originals_rewritten': False,
        'legacy_binary_paths_written': False, 'legacy_binary_identities_claimed_current': False,
        'updater_rebuilt': False, 'automatic_retry': False,
        'acceptance_requires_final_stdout_and_authoritative_durable_terminal': True,
        'gates': {}, 'errors': errors}
    phase = 'current_and_historical_authorities'
    try:
        compile470 = authority('current470-result', observations)
        qualify_builder470_receipt(compile470)
        prior_admission = authority('current470-resource-admission', observations)
        recorded = compile470['resource_admission']
        expected_recorded = dict(recorded)
        expected_recorded['identity'] = recorded['identity'][:3] + [recorded['bytes']] + [int(x) for x in recorded['identity'][3:]]
        require(observations['current470-resource-admission']['pin'] == expected_recorded and
                prior_admission['profile'] == {'memory_max_bytes': 1073741824, 'memory_swap_max_bytes': 0,
                    'minimum_fresh_MemAvailable_bytes': 3221225472, 'admission_difference_bytes': 2147483648,
                    'global_swap_is_owned_budget': False} and
                prior_admission['owned_observed'] == {'memory.max': '1073741824', 'cpu.max': '100000 100000',
                    'memory.swap.max': '0', 'memory.swap.current': '0'} and
                parse_admission_meminfo(prior_admission['meminfo']['raw_ascii'].encode('ascii'))['MemAvailable'] >= 3*1024**3 and
                len(compile470['cpu_affinity']) == 1, 'actual original current Rust resource authority differs')
        legacy468 = authority('legacy468-result', observations)
        legacy469 = authority('legacy469-result', observations)
        legacy469_qualification = authority('legacy469-qualification', observations)
        require(legacy468['state'] == 'PASS' and legacy468['focused_tests_passed'] == 24 and
                legacy468['expected_source_resume_test_names'] == SOURCE_TESTS and
                legacy468['source_actual_registered_test_count'] == 20 and
                legacy469['state'] == 'RUST_BUILD_AND_FOCUSED_TESTS_PASS' and
                legacy469_qualification['state'] == 'ACTUAL_COMPILE02_INPUT_CONTINUITY_AND_16_INDEPENDENT_TESTS_PASS',
                'immutable historical capability provenance differs')
        result['historical_provenance'] = {'468': observations['legacy468-result'],
            '469_compile': observations['legacy469-result'], '469_qualification': observations['legacy469-qualification'],
            'classification': 'historical evidence only; no live legacy ELF identity assertion',
            'missing468_diagnostic_job': '1a1b2240691-fc05-7c96',
            'missing468_diagnostic_stdout_sha256': '2a8c2c6c141a76bbc604c039d4dfcc22ab2daac80b6d51286b06718f19e6207b',
            'missing468_diagnostic_state': 'DIAGNOSIS_FAILED',
            'missing468_diagnostic_secondary_FD_failure_preserved': True}
        result['current_compile_authority'] = observations['current470-result']
        require(compile470['baseline_compile'] == observations['legacy469-result']['pin'] ==
                    legacy469_qualification['actual_compile02'] and
                compile470['baseline_independent_qualification'] == observations['legacy469-qualification']['pin'] and
                compile470['profile_authority'] == observations['legacy468-result']['pin'] ==
                    legacy469_qualification['original_compiler03_authority'] and
                legacy468['expected_test_names'] == TESTS[:15] and
                legacy469['test_names'] == legacy469_qualification['expected_test_names'] == TESTS[:16] and
                legacy469_qualification['unchanged_source_resume_controls']['names'] == SOURCE_TESTS,
                'exact current and historical capability bindings differ')
        result['gates']['actual_current_470_compile_receipt_and_19_original_gates'] = True

        phase = 'fresh_owned_Rust_resource_admission'
        affinity = sorted(os.sched_getaffinity(0))
        require(len(affinity) >= 3, 'at least two logical CPUs must remain free')
        os.sched_setaffinity(0, affinity[-1:])
        result['cpu_affinity_before'] = affinity
        result['cpu_affinity'] = affinity[-1:]
        member = P('/proc/self/cgroup').read_text().strip()
        require(member.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),
                'exact newly owned user cgroup required')
        cgroup = P('/sys/fs/cgroup') / member[3:].lstrip('/')
        unit = cgroup.name
        require(unit.endswith('.service') and str(os.getpid()) in (cgroup / 'cgroup.procs').read_text().split(),
                'owned cgroup process identity differs')
        require((cgroup / 'memory.max').read_text().strip() == str(MEMORY_MAX) and
                (cgroup / 'cpu.max').read_text().strip() == '100000 100000', 'owned Rust limits differ')
        subprocess.run(['/usr/bin/systemctl', '--user', 'set-property', '--runtime', unit, 'MemorySwapMax=0'],
                       check=True, capture_output=True, timeout=15)
        memory, owned, admission = record_resource_admission(cgroup)
        result['resource_admission'] = admission
        result['owned_unit'] = unit
        subreaper()
        require(child_ids() == [], 'preexisting owned children')
        result['gates']['fresh_3GiB_and_owned_1GiB_1CPU_zero_swap'] = True

        phase = 'complete_current_source_and_ancestry'
        current = authority('current498-manifest', observations)
        old493 = authority('legacy493-manifest', observations)
        old491 = authority('legacy491-manifest', observations)
        result['source_ancestry'] = verify_source_ancestry(old491, old493, current)
        require(compile470['candidate_manifest'] == observations['current498-manifest']['pin'] and
                compile470['baseline_manifest'] == legacy469_qualification['candidate_manifest'] ==
                    observations['legacy493-manifest']['pin'] and
                legacy469_qualification['baseline_manifest'] == observations['legacy491-manifest']['pin'],
                'exact current manifest ancestry identities differ')
        source_before = source_observation(current)
        candidate_rows = {name: row['pin'] for name, row in source_before['files'].items()}
        current_lock, unused = held(SOURCE / 'android/manifest/m2-role-ingress-provider3-source-lock.json', 1048576)
        lock = json.loads(current_lock)
        require(len(lock['projects']) == 242 and len(lock['links']) == 8 and
                lock['remote_base'] == 'https://android.googlesource.com/' and
                lock['superproject']['commit'] == '28f0bbddc24d56c8ec5a8df5342ac7a292184039' and
                lock['policy']['allow_unrestricted_repo_sync'] is False and
                lock['policy']['require_exact_commits'] is True and
                lock['policy']['add_dependencies_only_from_superproject'] is True,
                'current locked provider source policy differs')
        resume, unused = held(SOURCE / 'tools/droidloom-source/src/resume.rs', 65536)
        require(sha(resume) == '2026055997ba7d8392bada503d0e1c229cad13bba931f13b410457ac86daafe6' and
                b'#[cfg(test)]\n    command.args(["-c", "protocol.https.allow=never"]);' in resume and
                b'let temporary = tempfile::tempdir().unwrap();' in resume,
                'current source-resume test network and private-fixture boundary changed')
        result['gates']['complete498_source_and_exact491_493_498_ancestry'] = True
        result['gates']['exact242_project_lock_and_private_offline_resume_fixture_source'] = True

        phase = 'current_artifacts_and_original_compile_outputs'
        current_artifacts = {
            'builder': current_artifact(compile470['builder'], ACTIVE / 'compile01/cargo-target/debug/droidloom-update'),
            'test': current_artifact(compile470['test_executable'],
                ACTIVE / 'compile01/cargo-target/debug/deps/droidloom_update-77fdace49114cd0d')}
        current_output_pins = current_receipt_outputs(compile470)
        result['current_artifacts'] = current_artifacts
        result['gates']['existing470_ELF_and_test_exact_original_identity_owner_and_SHA'] = True
        result['gates']['original23_command_outputs_and19_independent_logs_revalidated'] = True

        phase = 'closed_registry_toolchain_and_configuration_inputs'
        dependency_document = authority('dependency-inputs', observations)
        require(observations['dependency-inputs']['pin'] == compile470['dependency_continuity']['authority'] ==
                    legacy469_qualification['dependency_continuity']['authority'],
                'original dependency authority full identity differs')
        dependencies = dependency_document['files']
        packages = dependency_document['packages']
        require(len(dependencies) == 2706 and len(packages) == 49 and
                sum(p['kind'] == 'offline-registry' for p in packages) == 45,
                'complete registry closure differs')
        dependency_owners = {}
        for name, row in dependencies.items():
            path = P(name)
            require(path.is_absolute() and str(path) == row['path'] and
                    path.is_relative_to(P('/home/alex/.cargo/registry')), 'registry path escaped its bound root')
            no_alias(path.parent)
            require(hash_held(path) == row, 'qualified registry bytes or full identity changed: ' + name)
            dependency_owners[name] = owner_identity(path)
        remapped = json.loads(json.dumps(packages).replace(str(PROFILE_BASE / 'builder-source'), str(SOURCE)))
        require(sum(p['kind'] == 'pinned-builder-source' for p in remapped) == 4 and
                sorted(p['id'] for p in remapped) == compile470['dependency_continuity']['actual_build_packages'],
                'exact current 49-package ancestry differs')
        expected_source_packages = sorted(value.replace(str(PROFILE_BASE / 'builder-source'), str(SOURCE))
                                         for value in legacy468['actual_source_test_compile_packages'])
        require(len(expected_source_packages) == 46 and set(expected_source_packages) <= {p['id'] for p in remapped},
                'exact current source-resume library subset differs')
        configs = cargo_config_paths()
        no_cargo_config(configs)
        original_tools = authority('tool-inputs', observations)
        pins = {}
        collect_pins(original_tools, pins)
        pins.pop('/home/alex/.cargo/bin/rustup', None)
        rustroot = '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu'
        for suffix, count, checksum in EXPLICIT_RUST_TOOLS:
            path = rustroot + suffix
            row = {'bytes': count, 'sha256': checksum, 'resolved_path': path}
            require(path not in pins or pins[path] == row, 'explicit pinned toolchain differs')
            pins[path] = row
        require(len(pins) == 70, 'exact full compiler/runtime tool closure differs')
        tools_before = checked_tools(pins)
        original_current_tools = authority('current470-tool-inputs', observations)
        require(len(original_current_tools) == 70 and tools_before == original_current_tools,
                'full current tool identities differ from actual470 pre-compile inputs')
        original_modes = {}
        for row in original_tools:
            path = row.get('requested_path') or row['path']
            require(path not in original_modes or original_modes[path] == row['identity'][2],
                    'inconsistent original tool mode')
            original_modes[path] = row['identity'][2]
        require(set(original_modes) == set(pins), 'original tool mode closure differs')
        tool_owners = {}
        for path, row in tools_before.items():
            info = P(row['resolved_path']).lstat()
            expected_owner = 1000 if row['resolved_path'].startswith('/home/alex/.rustup/') else 0
            require(row['resolved_path'].startswith(('/home/alex/.rustup/', '/usr/')) and
                    info.st_uid == info.st_gid == expected_owner and
                    info.st_mode == original_modes[path] and not info.st_mode & 0o6002,
                    'tool differs from original mode or explicit current owner policy')
            tool_owners[path] = {'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
                                 'identity': identity(info)}
        save(OUT / 'source-inputs-before.json', source_before)
        save(OUT / 'tool-inputs-before.json', {'pins': tools_before, 'owners': tool_owners})
        result['dependency_continuity'] = {'authority': observations['dependency-inputs'],
            'selected_packages': 49, 'registry_packages': 45, 'recorded_files_and_archives': 2706,
            'current_updater_packages': sorted(p['id'] for p in remapped),
            'expected_source_resume_packages': expected_source_packages, 'new_dependency_fetches': 0}
        result['gates']['all2706_registry_files_and49_package_inputs_qualified'] = True
        result['gates']['all70_tools_and_explicit_Rust1_93_and_no_Cargo_config'] = True

        phase = 'explicit_current_commands'
        (OUT / 'tmp').mkdir(mode=0o700)
        (OUT / 'cargo-target').mkdir(mode=0o700)
        environment = {'PATH': rustroot + '/bin:/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
            'CARGO_HOME': '/home/alex/.cargo', 'CARGO_TARGET_DIR': str(OUT / 'cargo-target'),
            'CARGO_NET_OFFLINE': 'true', 'CARGO_BUILD_JOBS': '1', 'RUSTC': rustroot + '/bin/rustc',
            'RUSTDOC': rustroot + '/bin/rustdoc', 'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER': '/usr/bin/cc',
            'RUSTC_WRAPPER': '', 'RUSTC_WORKSPACE_WRAPPER': '', 'RUSTFLAGS': '', 'RUSTDOCFLAGS': '',
            'CARGO_ENCODED_RUSTFLAGS': '', 'CARGO_ENCODED_RUSTDOCFLAGS': '',
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_OPTIONAL_LOCKS': '0',
            'TMPDIR': str(OUT / 'tmp')}
        result['command_environment'] = environment
        version = command([rustroot + '/bin/rustc', '-Vv'], SOURCE, environment, 'rust-version', records, 20)
        require('release: 1.93.0\n' in version.decode(), 'actual current Rust version differs')
        builder = P(compile470['builder']['path'])
        test = P(compile470['test_executable']['path'])
        general_help = command([str(builder), '--help'], SOURCE, environment, 'current-builder-help', records, 20)
        typed_help = command([str(builder), 'native-role-ingress-build', '--help'], SOURCE, environment,
                             'current-typed-ingress-help', records, 20)
        require(b'native-role-ingress-build' in general_help and b'--work' in typed_help and
                b'--resume-source-staging' in typed_help, 'actual current fixed typed-ingress CLI surface differs')
        names = registered_tests(test, 'updater-test-list', 209, TESTS, environment, records)
        updater_gates = [focused_test(test, name, index, len(names), environment, records)
                         for index, name in enumerate(TESTS)]
        result['fresh_updater_independent_result_gates'] = updater_gates
        result['gates']['current_CLI_help_and19_updater_independent_tests'] = len(updater_gates) == 19

        phase = 'current_source_resume_test_compilation_and_execution'
        source_log = command([rustroot + '/bin/cargo', 'test', '--offline', '--locked', '-j', '1',
            '-p', 'droidloom-source', '--lib', '--no-run', '--message-format=json-render-diagnostics'],
            SOURCE, environment, 'source-resume-test-compile', records, 300)
        actual_packages = qualify_compiler_inputs(source_log, remapped, dependencies, candidate_rows)
        require(actual_packages == expected_source_packages, 'actual source-resume compilation closure differs')
        artifacts = [json.loads(line) for line in source_log.decode().splitlines() if line.startswith('{')]
        executables = [item['executable'] for item in artifacts if item.get('reason') == 'compiler-artifact' and
            item.get('target', {}).get('name') == 'droidloom_source' and
            item.get('target', {}).get('kind') == ['lib'] and
            item.get('manifest_path') == str(SOURCE / 'tools/droidloom-source/Cargo.toml') and
            item.get('profile', {}).get('test') is True and item.get('executable')]
        require(len(executables) == 1, 'exactly one actual current source-resume test executable is required')
        source_test = P(executables[0])
        require(source_test.is_relative_to(OUT / 'cargo-target') and not source_test.is_symlink(),
                'new source-resume test executable escaped its owned target')
        source_test_pin = hash_pin(source_test)
        source_test_owner = owner_identity(source_test)
        source_names = registered_tests(source_test, 'source-resume-test-list', 20, SOURCE_TESTS, environment, records)
        source_gates = [focused_test(source_test, name, 100 + index, len(source_names), environment, records)
                        for index, name in enumerate(SOURCE_TESTS)]
        require(hash_pin(source_test) == source_test_pin and owner_identity(source_test) == source_test_owner,
                'new source-resume executable changed during its tests')
        result['fresh_source_resume_independent_result_gates'] = source_gates
        result['source_resume_test_executable'] = {'pin': source_test_pin, 'owner': source_test_owner}
        result['actual_source_resume_compile_packages'] = actual_packages
        result['source_resume_test_compiled_from_current498_source'] = True
        result['source_resume_test_fixtures_network_disabled_by_exact_cfg_test_source'] = True
        result['gates']['fresh_current_source_resume_compile_and9_independent_tests'] = len(source_gates) == 9
        require([row['label'] for row in records] == EXPECTED_FRESH_LABELS and
                all(row['returncode'] == 0 and row['timed_out'] is False for row in records),
                'exact fresh 34-command closure differs')
        result['gates']['exact34_fresh_commands_and28_independent_tests'] = True
    except BaseException as error:
        errors.append(failure_detail(error, phase))
    finally:
        try:
            cleanup = cleanup_children()
            result['cleanup'] = cleanup
            require(cleanup.get('complete') is True and cleanup.get('children') == [] and cleanup.get('errors') == [],
                    'owned child cleanup incomplete or residual child retirement occurred')
            result['gates']['strict_no_residual_owned_children'] = True
        except BaseException as error:
            errors.append(failure_detail(error, 'owned_children_final'))
        try:
            for name, row in observations.items():
                require(hash_held(P(row['pin']['path']), AUTHORITIES[name]['bytes']) == row['pin'] and
                        owner_identity(P(row['pin']['path'])) == row['owner'], 'authority changed during qualification')
            if source_before is not None:
                require(source_observation(current) == source_before, 'complete current source identity changed')
            if current_artifacts is not None:
                require(current_artifact(compile470['builder'], P(compile470['builder']['path'])) == current_artifacts['builder'] and
                        current_artifact(compile470['test_executable'], P(compile470['test_executable']['path'])) == current_artifacts['test'],
                        'current builder or test artifact changed after qualification')
            if current_output_pins is not None:
                require(current_receipt_outputs(compile470) == current_output_pins, 'current original result evidence changed')
            if dependencies is not None:
                for path, row in dependencies.items():
                    require(hash_held(P(path)) == row and owner_identity(P(path)) == dependency_owners[path],
                            'registry bytes, owner or identity changed after qualification')
            if tools_before is not None:
                require(checked_tools(pins) == tools_before, 'tool bytes or full identity changed after qualification')
                for path, row in tools_before.items():
                    info = P(row['resolved_path']).lstat()
                    require(tool_owners[path] == {'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
                            'identity': identity(info)}, 'tool owner changed after qualification')
            if configs is not None:
                no_cargo_config(configs)
            require(held(P(__file__), 131072)[1] == own_pin and
                    held(ROOT / 'stage-receipt.json', 65536)[1] == stage_pin and
                    owner_identity(ROOT / 'stage-receipt.json') == stage_owner,
                    'qualifier source or closed-stage receipt changed')
            require(set(observations) == set(AUTHORITIES) and source_before is not None and
                    current_artifacts is not None and current_output_pins is not None and
                    dependencies is not None and tools_before is not None and configs is not None,
                    'full mandatory continuity observation was not reached')
            result['gates']['all_bound_inputs_and_owners_unchanged_after'] = True
        except BaseException as error:
            errors.append(failure_detail(error, 'input_continuity_final'))
        try:
            if cgroup is not None:
                result['memory_events'] = (cgroup / 'memory.events').read_text()
                result['owned_resource_gate'] = owned_resource_gate(result['memory_events'])
                require(result['owned_resource_gate']['pass'] is True and
                        all(result['owned_resource_gate']['events'][name] == 0
                            for name in ('oom', 'oom_kill', 'oom_group_kill')), 'owned OOM gate failed')
                result['memory_peak'] = (cgroup / 'memory.peak').read_text().strip()
                result['swap_peak'] = (cgroup / 'memory.swap.peak').read_text().strip()
                require(result['swap_peak'] == '0' and (cgroup / 'memory.swap.max').read_text().strip() == '0' and
                        (cgroup / 'memory.swap.current').read_text().strip() == '0', 'owned zero-swap gate failed')
                result['gates']['owned_no_OOM_and_zero_swap'] = True
            final_descriptor_gate(before, library)
            result['gates']['exact_stdio_and_prequalified_library_FD_set'] = True
        except BaseException as error:
            errors.append(failure_detail(error, 'resource_and_descriptor_final'))
    result['authority_observations'] = observations
    result['commands'] = records
    result['command_count'] = len(records)
    result['tests_passed'] = len(result.get('fresh_updater_independent_result_gates', [])) + len(result.get('fresh_source_resume_independent_result_gates', []))
    result['expected_gates'] = EXPECTED_GATES
    qualified = qualification_complete(result)
    result['current_builder_qualification_complete'] = qualified
    result['state'] = 'CURRENT470_EXPLICIT_28_TEST_QUALIFICATION_PASS' if qualified else 'FAILED'
    result['finished_utc'] = utc()
    save(OUT / 'result.json', result)
    result_raw, result_pin = held(OUT / 'result.json', 1048576)
    late_error = None
    try:
        final_descriptor_gate(before, library)
        require(child_ids() == [], 'owned child appeared after result publication')
    except BaseException as error:
        late_error = failure_detail(error, 'after_result_publication')
    final_ok = qualified and late_error is None
    print(json.dumps({'schema': 'pocket4-current470-qualification-final-summary-v1',
        'state': 'PASS' if final_ok else 'FAILED', 'current_builder_qualification_complete': final_ok,
        'result': result_pin, 'commands': len(records), 'tests_passed': result['tests_passed'],
        'late_error': late_error, 'Main_actions': 0, 'Soong_invoked': False,
        'new_authorization_contract_connected': False, 'production_ready': False,
        'cleanup_eligible': False, 'authoritative_durable_exit_zero_still_required': True}), flush=True)
    return 0 if final_ok else 1


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print(json.dumps({'state': 'PLAN_ONLY', 'Main_actions': 0, 'compiler_invoked': False}))
    else:
        require(len(sys.argv) == 4 and sys.argv[1:3] == ['--qualify-once', '--source-sha256'] and
                re.fullmatch('[0-9a-f]{64}', sys.argv[3]), 'exact once-only qualification arguments required')
        raise SystemExit(run_current_qualification(sys.argv[3]))
