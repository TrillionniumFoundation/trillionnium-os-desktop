#!/usr/bin/env python3
"""Run the normal builder on an independent prepared framework workspace; never deploy."""
import argparse, ctypes, datetime, hashlib, json, os, pathlib, resource, signal, stat, subprocess, time
P = pathlib.Path

def digest(path):
    with P(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def save(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())

def no_alias(path):
    require(path.is_absolute() and ".." not in path.parts, "non-absolute or parent path")
    for parent in [path, *path.parents]:
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode), "path aliases a symlink or non-directory")

def memory_admission(memory):
    require(MIN_AVAILABLE - MEMORY_MAX == 3 * 1024**3,
            "new profile requires an explicit three-GiB admission difference")
    require(MIN_FREE_SWAP - SWAP_MAX == 1024**3,
            "new profile requires at least one-GiB swap admission difference")
    require(memory["MemAvailable"] >= MIN_AVAILABLE,
            "less than 13 GiB MemAvailable for fresh Go5 streaming profile; no automatic retry")
    require(memory["SwapFree"] >= MIN_FREE_SWAP,
            "less than the required 2 GiB free swap; no automatic retry")

def owned_resource_gate(text):
    require(isinstance(text, str), "owned memory.events was not observed")
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows),
            "malformed owned memory.events")
    events = {row[0]: int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(name in events for name in ("oom", "oom_kill", "oom_group_kill")),
            "incomplete or duplicate owned memory.events")
    require(events["oom_kill"] == 0 and events["oom_group_kill"] == 0,
            "owned OOM kill observed; build is not qualified")
    return {"pass": True, "events": events, "owned_oom_kills_zero": True}

def subreaper():
    # Only this newly owned controller process is changed.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    require(libc.prctl(36, 1, 0, 0, 0) == 0, "cannot establish owned-child subreaper")

def child_ids():
    # The controller is single threaded and owns all of its subprocesses.
    require(os.readlink("/proc/self") == str(os.getpid()),
            "controller proc view does not match its PID namespace")
    text = P("/proc/thread-self/children").read_text()
    values = [int(x) for x in text.split()]
    require(len(values) <= 4096 and all(x > 1 for x in values), "unexpected owned child set")
    return values

def cleanup_children():
    records = []
    errors = []
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            children = child_ids()
        except Exception as error:
            return {"complete": False, "children": records,
                    "errors": errors + [{"operation": "enumerate", "error": repr(error)}]}
        if not children:
            return {"complete": not errors, "children": records, "errors": errors}
        for pid in children:
            if time.monotonic() >= deadline:
                break
            fd = -1
            try:
                fd = os.pidfd_open(pid, 0)
                # No other thread/handler reaps a child. A zombie still holds its
                # PID until this exact waitpid; pidfd binds the kernel object.
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL, None, 0)
                except ProcessLookupError:
                    pass
                stop = min(deadline, time.monotonic() + 1)
                status = None
                while time.monotonic() < stop:
                    got, value = os.waitpid(pid, os.WNOHANG)
                    if got == pid:
                        status = value
                        break
                    time.sleep(0.01)
                records.append({"pid": pid, "wait_status": status, "reaped": status is not None})
            except Exception as error:
                errors.append({"pid": pid, "operation": "pidfd_stop_or_wait", "error": repr(error)})
            finally:
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError as error:
                        errors.append({"pid": pid, "operation": "close_pidfd", "error": repr(error)})
        time.sleep(0.01)
    try:
        remaining = child_ids()
    except Exception as error:
        remaining = None
        errors.append({"operation": "final_enumerate", "error": repr(error)})
    return {"complete": remaining == [] and not errors, "children": records,
            "errors": errors, "remaining": remaining}

# Input and completion bindings for the existing normal builder lifecycle.
OWNER = P('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01')
ROOT = OWNER / 'typed-ingress-framework-resume-build-01-20261106'
HERE = ROOT / 'control-source'
WORK = OWNER / 'typed-ingress-framework-work-01-20261105'
OUT = ROOT / 'android-out'
ATTEMPT = ROOT / 'attempt-01'
BUILD_PARENT = P('/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106')
BUILD_SOURCE = BUILD_PARENT / 'builder-source'
BUILDER = BUILD_PARENT / 'attempt01/cargo-target/debug/droidloom-update'
BUILDER_SHA = 'fd4ef1903fa506512f2605fa03b39b5af0712680ff26dfbebfb4683c1b9ec288'
BUILDER_BYTES = 34579760
BUILD_RESULT = BUILD_PARENT / 'attempt01/result.json'
BUILD_RESULT_SHA = 'cd9f61ca21dd83210299f24dd50b68f5aa7aeba7eab94ac9cada71271d660e28'
BUILD_RESULT_BYTES = 140163
SOURCE_MANIFEST_SHA = '71768da388021a870ef5f5516cc3efbfd956288a8fa74cb9b176b312f68d7605'
PREPARE_PARENT = OWNER / 'typed-framework-work-preparation-01-20261105'
PREPARATION = PREPARE_PARENT / 'attempt01/result.json'
PREPARATION_SHA = 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'
INVENTORY_SOURCE_SHA = '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'
ENGINE_SOURCE = OWNER / 'full-build-combined07-go5-streaming-01/engine-working'
TETO_HEAD = 'a9496d886a85752ba407b76509952c06cd79ddb8'
EXTENDED_LOCK_SHA = 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54'
ORIGINAL_LOCK_SHA = '4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178'
GO_PATCH = 'android/apex-compat/0008-soong-leaf-go-memory-budget.patch'
GO_PATCH_SHA = '39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f'
MEMORY_MAX = 10 * 1024**3
SWAP_MAX = 1024**3
MIN_AVAILABLE = 13 * 1024**3
MIN_FREE_SWAP = 2 * 1024**3
TARGETS = ['framework-minus-apex', 'libandroid_runtime']
EXPECTED_TESTS = [
    'android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes',
    'android::tests::restoration_preserves_original_and_removes_created_file',
    'android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch',
    'android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout',
    'android::patch_tests::interrupted_projection_recovers_before_next_build',
    'tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets',
    'tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory',
    'native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate',
    'native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions',
]


PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-build-01-20261105'
RESUME_STAGING = WORK / '.droidloom-source-a2fqBK'
PRIOR_INNER_SHA = '139163acad47d9db707faa950e4b4dcecaf3e72b655bce8b6b3db089ce542bdf'
PRIOR_OUTER_SHA = '3626270e88e72c4e46d8beee09b5351e1f7d53bab18043241204ca314855e04d'
STAGING_OBSERVATION_SHA = 'c62f32b7002d043e4813eadd598f33d088a0f20cc9f562ddc19d35c2ccddf664'
EXPECTED_SOURCE_TESTS = ['resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify', 'resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock', 'resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected', 'resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest', 'resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed', 'resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout', 'resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging', 'resume::tests::mismatched_staging_manifest_is_preserved_and_not_published', 'resume::tests::sparse_parent_normalization_keeps_exact_locked_selection']
EXPECTED_COMPILE_LABELS = ['cargo-version', 'rustc-version', 'linked-libraries-0', 'linked-libraries-1', 'linked-libraries-2', 'linked-libraries-3', 'linked-libraries-4', 'linked-libraries-5', 'linked-libraries-6', 'image-linked-libraries-0', 'image-linked-libraries-1', 'image-linked-libraries-2', 'image-linked-libraries-3', 'image-linked-libraries-4', 'image-linked-libraries-5', 'image-linked-libraries-6', 'image-linked-libraries-7', 'image-linked-libraries-8', 'image-linked-libraries-9', 'image-linked-libraries-10', 'image-linked-libraries-11', 'image-linked-libraries-12', 'image-linked-libraries-13', 'image-linked-libraries-14', 'workspace-no-deps', 'selected-build', 'selected-test', 'builder-compile', 'builder-help', 'builder-test-compile', 'builder-test-list', 'builder-test-help', 'projection-test-0', 'projection-test-1', 'projection-test-2', 'projection-test-3', 'projection-test-4', 'projection-test-5', 'projection-test-6', 'projection-test-7', 'projection-test-8', 'linked-libraries-7', 'source-resume-cli-help', 'source-resume-selected-test', 'source-resume-test-compile', 'source-resume-test-list', 'source-resume-test-help', 'projection-test-9', 'projection-test-10', 'projection-test-11', 'projection-test-12', 'projection-test-13', 'projection-test-14', 'projection-test-15', 'projection-test-16', 'projection-test-17']


def identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def held_file(path, bound, include_bytes=False):
    path = P(path)
    no_alias(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and not before.st_mode & 0o6000 and
                0 <= before.st_size <= bound, 'regular held file bound differs: ' + str(path))
        digest_value = hashlib.sha256()
        pieces = []
        count = 0
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            count += len(block)
            require(count <= bound, 'held file grew beyond bound: ' + str(path))
            digest_value.update(block)
            if include_bytes:
                pieces.append(block)
        require(count == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held/named file changed: ' + str(path))
        row = {'path': str(path), 'bytes': count, 'sha256': digest_value.hexdigest(), 'identity': identity(before)}
        return row, b''.join(pieces) if include_bytes else None
    finally:
        os.close(fd)


def json_pin(path, wanted_sha, wanted_bytes, bound=4*1024*1024):
    row, raw = held_file(path, bound, True)
    require(row['bytes'] == wanted_bytes and row['sha256'] == wanted_sha,
            'fixed JSON authority changed: ' + str(path))
    return json.loads(raw), row


def builder_contract():
    require(isinstance(BUILDER_SHA, str) and len(BUILDER_SHA) == 64 and
            all(c in '0123456789abcdef' for c in BUILDER_SHA) and
            isinstance(BUILD_RESULT_SHA, str) and len(BUILD_RESULT_SHA) == 64 and
            all(c in '0123456789abcdef' for c in BUILD_RESULT_SHA) and
            isinstance(BUILDER_BYTES, int) and 0 < BUILDER_BYTES <= 64*1024*1024 and
            isinstance(BUILD_RESULT_BYTES, int) and 0 < BUILD_RESULT_BYTES <= 4*1024*1024,
            'UNBOUND_TEMPLATE_REQUIRES_ACTUAL_BUILDER467_COMPILE_PASS')
    result, pin = json_pin(BUILD_RESULT, BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    staged, _ = json_pin(HERE / 'actual-builder467-result.json', BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    require(result == staged and result['state'] == 'PASS' and
            result['focused_tests_passed'] == 18 and result['updater_focused_tests_passed'] == 9 and
            result['source_resume_tests_passed'] == 9 and result['expected_test_names'] == EXPECTED_TESTS and
            result['expected_source_resume_test_names'] == EXPECTED_SOURCE_TESTS and
            result['actual_registered_test_count'] == 199 and result['source_actual_registered_test_count'] == 20 and
            result['original_projection_tests_passed'] == 7 and result['typed_ingress_lock_tests_passed'] == 2,
            'actual builder467 compile and recovery-control qualification differs')
    commands = result['commands']
    require(len(commands) == len(EXPECTED_COMPILE_LABELS) and
            {row['label'] for row in commands} == set(EXPECTED_COMPILE_LABELS) and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in commands),
            'actual compiler command closure is incomplete')
    for offset, names, count, elf_key, gates_key in [
        (0, EXPECTED_TESTS, 199, 'test_elf', 'focused_result_gates'),
        (9, EXPECTED_SOURCE_TESTS, 20, 'source_test_elf', 'source_resume_result_gates')]:
        require(len(result[gates_key]) == len(names), 'actual focused result gate count differs')
        for position, name in enumerate(names):
            index = offset + position
            label = 'projection-test-' + str(index)
            command = next(row for row in commands if row['label'] == label)
            expected_log = ('ok ' + name + '\n').encode()
            gate = {'exact_name': name, 'expected_stdout_runs': 1, 'filtered_out_per_run': count-1,
                    'outer_results': 1, 'registered_tests': count, 'summary_and_independent_result_agree': True}
            log_path = str(BUILD_PARENT / 'attempt01' / (label + '.libtest'))
            require(command['argv'] == [result[elf_key]['path'], '--exact', name,
                    '--test-threads=1', '--nocapture', '--logfile', log_path] and
                    command['focused_result_gate'] == gate and result[gates_key][position] == gate and
                    command['independent_libtest_result']['path'] == log_path and
                    command['independent_libtest_result']['bytes'] == len(expected_log) and
                    command['independent_libtest_result']['sha256'] == hashlib.sha256(expected_log).hexdigest(),
                    'actual independent exact test result differs: ' + name)
    require(result['actual_build_packages'] == result['actual_test_compile_packages'] and
            len(set(result['actual_build_packages'])) == 49 and
            sum(name.startswith('registry+') for name in result['actual_build_packages']) == 45 and
            result['actual_source_test_compile_packages'] and
            set(result['actual_source_test_compile_packages']).issubset(result['actual_build_packages']) and
            all(result[key] is True for key in ['copied_source_unchanged_after', 'original_source_unchanged_after',
                'cargo_configs_unchanged_after', 'source_test_fixtures_network_disabled']) and
            not result['dependency_changes'] and not result['tool_changes'] and not result['observed_signals'],
            'actual builder source/tool/dependency closure is incomplete')
    require(result['cleanup'] == {'errors': [], 'forced_cleanup': False, 'initial_owned_children': [],
                'reaped': [], 'remaining': []} and result['owned_resource_gate']['pass'] is True and
            all(result['owned_memory_events_delta'][key] == 0 for key in ['oom', 'oom_kill', 'oom_group_kill']),
            'actual builder resource or child gate differs')
    delta = result['source_delta']
    require(result['copied_manifest']['sha256'] == SOURCE_MANIFEST_SHA and
            result['copied_manifest']['bytes'] == 91945 and delta['actual_source_file_count'] == 466 and
            delta['changed_existing'] == ['tools/droidloom-source/src/lib.rs',
                'tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/main.rs'] and
            delta['added'] == ['tools/droidloom-source/src/resume.rs'] and delta['unchanged_existing'] == 462 and
            delta['builder_revision_name'] == '467-source-resume' and
            delta['Cargo_lock_or_dependency_manifest_changed'] is False and
            delta['Go5_or_Blueprint_patch_changed'] is False and delta['source_lock_changed'] is False and
            delta['real_source_staging_accessed'] is False and result['actual_device_staging_reuse_qualified'] is False,
            'builder source is not the exact reviewed three-replacement/one-module successor')
    require(result['actual_toolchain']['rustup_proxy_executed'] is False and
            result['actual_toolchain']['rustup_proxy_changed_bytes_approved_for_execution'] is False and
            result['runtime_authorization_enabled'] is False and
            result['framework_Java_and_Android_JNI_compiled'] is False and
            result['transitive_framework_closure_qualified'] is False,
            'builder receipt scope was widened')
    builder, _ = held_file(BUILDER, 64*1024*1024)
    require(builder == result['builder_elf'] and builder['sha256'] == BUILDER_SHA and
            builder['bytes'] == BUILDER_BYTES and builder['identity'][2] & 0o111,
            'actual builder ELF identity/content changed')
    source_map, source_pin = json_pin(BUILD_PARENT / 'attempt01/copied-builder-source-manifest.json',
                                    SOURCE_MANIFEST_SHA, 91945)
    staged_map, _ = json_pin(HERE / 'expected-builder467-manifest.json', SOURCE_MANIFEST_SHA, 91945)
    require(source_map == staged_map and len(source_map) == 466 and
            source_map[GO_PATCH]['sha256'] == GO_PATCH_SHA and
            source_map['android/manifest/m2-role-ingress-source-lock.json']['sha256'] == EXTENDED_LOCK_SHA,
            'full builder source manifest differs')
    return result, pin, source_map, source_pin, builder


def inventory_module():
    path = HERE / 'frozen-work-inventory.py'
    row, raw = held_file(path, 65536, True)
    require(row['bytes'] == 48443 and row['sha256'] == INVENTORY_SOURCE_SHA,
            'previously reviewed bounded inventory implementation changed')
    scope = {'__name__': 'frozen_work_inventory_readonly', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), scope, scope)
    return scope, row


def preparation_contract(expected_sha):
    require(expected_sha == PREPARATION_SHA, 'actual independent work receipt is required')
    result, row = json_pin(PREPARATION, expected_sha, 11091)
    staged, _ = json_pin(HERE / 'actual-work-preparation.json', expected_sha, 11091)
    require(result == staged and result['state'] == 'PREPARED_INPUTS_NOT_MATERIALIZED_OR_BUILT' and
            result['first_error'] is None and not result['secondary_errors'] and
            result['owned_resource_gate']['pass'] is True and
            result['fixed_assets_copied'] == 20 and
            result['new_work_exact_top_level'] == ['base-system', 'framework-res.apk', 'mesa-source', 'python'] and
            result['new_work_identity'][:5] == [66306, 41861500, 16832, 1000, 1000],
            'actual independent work preparation differs')
    require(all(result[key] is True for key in ['fixed_assets_source_and_copy_unchanged_after',
                'mesa-source_source_and_copy_unchanged_after', 'python_source_and_copy_unchanged_after',
                'Teto_all_926_files_and_modes_match', 'Teto_source_and_authorities_unchanged_after']) and
            result['cleanup'] == {'forced_cleanup': False, 'remaining_children': '', 'subprocesses_started': 0} and
            result['materialize_invoked'] is False and result['Soong_invoked'] is False and
            result['builder_invoked'] is False and result['old_source_modified'] is False,
            'work copy or retained-source closure is incomplete')
    manifests = {}
    pins = {}
    for key, filename in [
        ('mesa-source_observed_content_manifest', 'mesa-source-source-manifest.json'),
        ('mesa-source_copied_content_manifest', 'mesa-source-copied-manifest.json'),
        ('python_observed_content_manifest', 'python-source-manifest.json'),
        ('python_copied_content_manifest', 'python-copied-manifest.json'),
        ('Teto_observed_content_manifest', 'Teto-source-manifest.json'),
    ]:
        reference = result[key]
        path = PREPARE_PARENT / 'attempt01' / filename
        require(reference['path'] == str(path), 'actual content manifest escaped its fixed directory')
        document, observed = json_pin(path, reference['sha256'], reference['bytes'])
        require(observed['identity'] == [reference['identity'][i] for i in (0, 1, 2, 5, 6, 7)],
                'actual held content manifest object changed: ' + key)
        manifests[key] = document
        pins[key] = observed
    require(manifests['mesa-source_observed_content_manifest']['files'] ==
                manifests['mesa-source_copied_content_manifest']['files'] and
            manifests['python_observed_content_manifest']['files'] ==
                manifests['python_copied_content_manifest']['files'],
            'actual source and copied manifest maps differ')
    for key, root in [('mesa-source_copied_content_manifest', WORK / 'mesa-source'),
                      ('python_copied_content_manifest', WORK / 'python'),
                      ('Teto_observed_content_manifest', ENGINE_SOURCE)]:
        require(manifests[key]['root'] == str(root), 'actual manifest root differs: ' + key)
    return result, row, manifests, pins


def prior_failure_contract():
    authorities = [
        (PREVIOUS_ROOT / 'attempt-01/terminal.json', 'prior-framework-inner-terminal.json', PRIOR_INNER_SHA, 28758),
        (PREVIOUS_ROOT / 'build-fences-01/terminal.json', 'prior-framework-outer-terminal.json', PRIOR_OUTER_SHA, 1177),
    ]
    documents = []
    pins = []
    for remote, staged_name, digest_value, size in authorities:
        document, row = json_pin(remote, digest_value, size)
        staged, staged_row = json_pin(HERE / staged_name, digest_value, size)
        require(document == staged, 'original failed authority differs from its frozen actual bytes')
        documents.append(document)
        pins.extend([row, staged_row])
    inner, outer = documents
    require(inner['state'] == 'FAILED' and inner['builder_returncode'] == -9 and
            inner['error'].startswith('TimeoutExpired(') and inner['error'].endswith(', 6100)') and
            inner['cleanup']['complete'] is True and inner['cleanup']['errors'] == [] and
            len(inner['cleanup']['children']) == 296 and
            len({row['pid'] for row in inner['cleanup']['children']}) == 296 and
            all(row['reaped'] is True for row in inner['cleanup']['children']) and
            inner['normal_command_completion_gate'] is None and
            inner['source_projection_journal_present'] is False and inner['input_after_qualified'] is True,
            'prior framework timeout or complete owned-child retirement is not the actual fixed result')
    require(outer['state'] == 'FAILED' and outer['inner_returncode'] == 1 and
            outer['main_fence_assessment']['main_fence_pass'] is True and
            outer['main_fence_assessment']['identity_or_limit_changes'] == [] and
            outer['main_fence_assessment']['main_oom_delta_zero'] is True,
            'prior fixed Main fence result differs')
    observed, row = json_pin(HERE / 'actual-staging-read03.json', STAGING_OBSERVATION_SHA, 211213)
    pins.append(row)
    require(observed['complete'] is True and observed['error'] is None and observed['read_only'] is True and
            observed['source_lock_sha256'] == EXTENDED_LOCK_SHA and len(observed['projects']) == 214 and
            observed['HEAD_and_origin_match_candidates'] == 145 and
            observed['staging_before'] == observed['staging_after'] and
            observed['reuse_authorized'] is False and observed['production_ready'] is False and
            all(row['reuse_qualified'] is False for row in observed['projects']),
            'actual known-staging observation was changed or promoted to reuse qualification')
    return observed, pins


def fresh_staging_binding(context, scope, state, current_work):
    observed = context['staging_observation']
    keys = ['device', 'inode', 'mode', 'uid', 'gid', 'bytes', 'mtime_ns', 'ctime_ns']
    require(current_work == [observed['work'][key] for key in keys],
            'workspace metadata differs from the complete post-timeout observation')
    fd = scope['directory'](RESUME_STAGING, state)
    actual = scope['full_identity'](os.fstat(fd))
    require(actual == [observed['staging_after'][key] for key in keys] and
            actual[:5] == [66306, 41861660, 16832, 1000, 1000],
            'explicit staging is not the actual observed private directory object')
    for path in [WORK / 'aosp-source', WORK / 'source-projection.json',
                 RESUME_STAGING / '.droidloom-source-manifest.json']:
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        raise RuntimeError('unexpected existing resume publication/journal/manifest: ' + str(path))
    return {'work_identity': current_work, 'staging_identity': actual,
        'known_staging_path': str(RESUME_STAGING), 'historical_HEAD_origin_candidates': 145,
        'candidate_prefix_reuse_qualified': False, 'project146_reuse_qualified': False,
        'all_project_qualification_deferred_to_normal_builder_under_existing_work_source_locks': True,
        'project146_unresolved_branch_absent_index_empty_private_lock_and_exact_origin_sparse_are_fresh_gates': True,
        'source_manifest_written_by_wrapper': False}


def observe_inputs(context, first):
    scope = context['inventory_scope']
    report = {'state': 'VERIFYING', 'first_error': None, 'secondary_errors': []}
    state = {'report': report, 'deadline': time.monotonic() + 60, 'bytes_read': 0, 'bytes_copied': 0,
             'directories': {}, 'early_close_errors': [], 'created_directories': set()}
    observations = {}
    primary = None
    try:
        work_fd = scope['directory'](WORK, state)
        current_work = scope['full_identity'](os.fstat(work_fd))
        require(current_work[:5] == context['prepared']['new_work_identity'][:5],
                'owned work directory identity/owner/mode changed')
        if first:
            observations['resume_staging'] = fresh_staging_binding(context, scope, state, current_work)
        fixed = {}
        for asset in scope['ASSETS']:
            row, _ = held_file(WORK / asset['destination'], asset['bytes'])
            require(row['sha256'] == asset['sha256'] and row['bytes'] == asset['bytes'] and
                    stat.S_IMODE(row['identity'][2]) == stat.S_IMODE(asset['identity'][2]),
                    'copied fixed build input changed: ' + asset['destination'])
            fixed[asset['destination']] = row
        observations['fixed_assets'] = fixed
        for key, root in [('mesa-source_copied_content_manifest', WORK / 'mesa-source'),
                          ('python_copied_content_manifest', WORK / 'python'),
                          ('Teto_observed_content_manifest', ENGINE_SOURCE)]:
            expected = context['manifests'][key]
            observed = scope['tree_inventory'](root, state, skip_root_git=(root == ENGINE_SOURCE))
            require(observed['files'] == expected['files'] and
                    observed['held_root'][:5] == expected['held_root'][:5],
                    'actual complete input file/path/mode map changed: ' + key)
            observations[key] = {'root': str(root), 'counts': observed['counts'],
                'held_root': observed['held_root'], 'complete_file_map_matched': True,
                'metadata_sha256': observed['metadata_sha256']}
        builder_tree = scope['tree_inventory'](BUILD_SOURCE, state)
        portable = {name: row for name, row in builder_tree['files'].items() if row['kind'] != 'directory'}
        require(portable == context['builder_map'], 'actual 466-file builder source changed')
        observations['builder_source'] = {'complete_file_map_matched': True, 'files': len(portable),
                                          'held_root': builder_tree['held_root']}
        head, head_bytes = held_file(ENGINE_SOURCE / '.git/HEAD', 128, True)
        require(head_bytes == (TETO_HEAD + '\n').encode() and
                head['sha256'] == context['prepared']['Teto_HEAD_authority']['sha256'],
                'held Teto HEAD differs')
        observations['Teto_HEAD'] = head
        binary, _ = held_file(BUILDER, 64*1024*1024)
        require(binary == context['builder_pin'], 'actual builder ELF changed')
        observations['builder_elf'] = binary
        for key, row in context['manifest_pins'].items():
            after, _ = held_file(row['path'], row['bytes'])
            require(after == row, 'held actual content manifest changed: ' + key)
        if not first:
            require(fixed == context['initial_observations']['fixed_assets'] and
                    head == context['initial_observations']['Teto_HEAD'],
                    'fixed asset or HEAD object changed during the normal build')
    except BaseException as error:
        primary = error
    finally:
        for path, (fd, _) in reversed(list(state['directories'].items())):
            try:
                os.close(fd)
            except BaseException as error:
                report['secondary_errors'].append({'phase': 'input-directory-close', 'path': path, 'error': repr(error)})
        report['secondary_errors'].extend(state['early_close_errors'])
    if primary is not None:
        raise primary
    require(report['first_error'] is None and not report['secondary_errors'],
            'input observation cleanup failed: ' + repr({'first_error': report['first_error'],
                                                        'secondary_errors': report['secondary_errors']}))
    observations['inventory_bytes_read'] = state['bytes_read']
    observations['source_copies_or_subprocesses_started'] = 0
    return observations


def verify_prepared(expected_sha):
    prepared, prepared_pin, manifests, manifest_pins = preparation_contract(expected_sha)
    compiled, compiled_pin, builder_map, builder_map_pin, builder_pin = builder_contract()
    scope, inventory_pin = inventory_module()
    context = {'prepared': prepared, 'prepared_pin': prepared_pin, 'manifests': manifests,
        'manifest_pins': manifest_pins, 'compiled': compiled, 'compiled_pin': compiled_pin,
        'builder_map': builder_map, 'builder_map_pin': builder_map_pin, 'builder_pin': builder_pin,
        'inventory_scope': scope, 'inventory_pin': inventory_pin}
    context['staging_observation'], context['prior_failure_authority_pins'] = prior_failure_contract()
    context['initial_observations'] = observe_inputs(context, True)
    return context


def plan():
    return {'schema': 1, 'state': ('PLAN_NORMAL_STRICT_FRAMEWORK_RESUME' if BUILD_RESULT_SHA is not None else
                             'UNBOUND_TEMPLATE_AWAITING_ACTUAL_BUILDER467_COMPILE_PASS'), 'root': str(ROOT),
        'work': str(WORK), 'aosp_source': str(WORK / 'aosp-source'), 'out': str(OUT),
        'builder_result_sha256': BUILD_RESULT_SHA, 'work_preparation_sha256': PREPARATION_SHA,
        'builder_sha256': BUILDER_SHA, 'builder_source_manifest_sha256': SOURCE_MANIFEST_SHA,
        'argv': [str(BUILDER), '--source', str(BUILD_SOURCE), '--jobs', '1',
                 'native-role-ingress-build', '--work', str(WORK), '--out', str(OUT),
                 '--resume-source-staging', str(RESUME_STAGING)],
        'targets': TARGETS, 'dependency_mode': 'Strict', 'source_materialization': 'normal 214 locked projects and 8 root links; explicit owned staging, all projects requalified',
        'resume_staging': str(RESUME_STAGING), 'historical_HEAD_origin_candidates': 145,
        'reuse_qualified_by_plan': False, 'prior_inner_failure_sha256': PRIOR_INNER_SHA,
        'prior_outer_failure_sha256': PRIOR_OUTER_SHA, 'prior_reaped_children': 296,
        'normal_lock_paths': [str(WORK / 'package-build.lock'), str(WORK / 'aosp-source-update.lock')],
        'normal_package_and_source_locks': True, 'normal_projection_journal_and_recovery': True,
        'old_shared_AOSP_source_modified': False, 'source_manifest_fabrication': False,
        'memory_max_bytes': MEMORY_MAX, 'memory_swap_max_bytes': SWAP_MAX,
        'fresh_MemAvailable_min_bytes': MIN_AVAILABLE, 'fresh_SwapFree_min_bytes': MIN_FREE_SWAP,
        'cpu_quota_percent': 200, 'jobs': 1, 'builder_wait_seconds': 6100,
        'automatic_retry': False, 'Main_actions': 0, 'Android_actions': 0, 'runtime_authorization_enabled': False,
        'Mesa_tools_not_fabricated_or_prequalified': True,
        'strict_dependency_failure_not_suppressed': True,
        'normal_build_success_not_complete_Java_JNI_qualification': True}


def completion_gate(context):
    records = {}
    for name in ['droidloom-role-ingress-attempt.json', 'droidloom-role-ingress-inputs.json',
                 'droidloom-role-ingress-command.json']:
        row, raw = held_file(OUT / name, 8*1024*1024, True)
        records[name] = (json.loads(raw), row)
    attempt = records['droidloom-role-ingress-attempt.json'][0]
    inputs = records['droidloom-role-ingress-inputs.json'][0]
    command = records['droidloom-role-ingress-command.json'][0]
    for document in [attempt, inputs]:
        require(document['targets'] == TARGETS and document['dependency_mode'] == 'Strict' and
                document['source_lock_sha256'] == EXTENDED_LOCK_SHA and
                document['original_source_lock_sha256'] == ORIGINAL_LOCK_SHA and
                document['runtime_authorization_enabled'] is False,
                'normal exact source/target projection record differs')
    require(command['state'] == 'NORMAL_BUILD_COMMAND_SUCCEEDED' and
            command['source_projection_restored'] is True and command['installation_performed'] is False and
            command['runtime_authorization_enabled'] is False and
            command['complete_framework_Java_and_Android_TU_verified'] is False and
            command['actual_Java_JNI_pair_and_platform_lifecycle_qualified'] is False,
            'normal command completion record differs')
    require(not (WORK / 'source-projection.json').exists() and not (WORK / 'source-projection.json').is_symlink(),
            'normal source projection did not finish restoration')
    require(inputs['host_only_libandroid_runtime_is_insufficient'] is True and
            inputs['complete_framework_Java_and_Android_TU_verified'] is False and
            inputs['transitive_build_closure_qualified'] is False,
            'framework input record claims an unverified artifact or host-only qualification')
    restored = {}
    expected_paths = {
        'core/java/com/android/internal/os/Zygote.java',
        'core/java/com/android/internal/os/ZygoteArguments.java',
        'core/java/com/android/internal/os/ZygoteConnection.java',
        'core/jni/com_android_internal_os_Zygote.cpp',
        'core/jni/droidloom_app_zygote_spec.h',
    }
    projected = inputs['typed_ingress_sources']
    require(len(projected) == 5 and {row['path'] for row in projected} == expected_paths,
            'normal typed projection file set differs')
    for projected_input in projected:
        path = WORK / 'aosp-source/frameworks/base' / projected_input['path']
        before = projected_input['before']
        if before is None:
            require(projected_input['path'] == 'core/jni/droidloom_app_zygote_spec.h' and
                    not path.exists() and not path.is_symlink(),
                    'normal projection did not remove its new typed header')
            restored[projected_input['path']] = {'absent_after_restoration': True}
        else:
            row, _ = held_file(path, 1024*1024)
            require(row['sha256'] == before['sha256'] and row['bytes'] == before['bytes'],
                    'normal projection did not restore an exact typed preimage')
            restored[projected_input['path']] = row
    return {'state': 'NORMAL_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING',
        'records': {name: row for name, (_, row) in records.items()},
        'typed_originals_restored': restored,
        'targets': TARGETS, 'dependency_mode': 'Strict', 'source_projection_restored': True,
        'Java_framework_implementation_jar_qualified': False, 'Android_JNI_TU_and_linked_library_qualified': False,
        'host_only_ELF_or_header_jar_is_sufficient': False, 'runtime_authorization_enabled': False,
        'installation_performed': False}


def verify_inputs_after(context):
    observations = observe_inputs(context, False)
    for path, wanted in [(PREPARATION, context['prepared_pin']), (BUILD_RESULT, context['compiled_pin']),
                         (HERE / 'frozen-work-inventory.py', context['inventory_pin']),
                         (BUILD_PARENT / 'attempt01/copied-builder-source-manifest.json', context['builder_map_pin'])]:
        row, _ = held_file(path, wanted['bytes'])
        require(row == wanted, 'runtime input authority changed: ' + str(path))
    for wanted in context['prior_failure_authority_pins']:
        row, _ = held_file(wanted['path'], wanted['bytes'])
        require(row == wanted, 'original failure/staging observation authority changed')
    return observations


def build(expected_sha):
    require(os.getuid() == 1000 and os.geteuid() == 1000, "build requires original operator uid")
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    context = verify_prepared(expected_sha)
    no_alias(ATTEMPT)
    no_alias(OUT)
    require(not ATTEMPT.exists() and not OUT.exists(), "attempt and output must both be fresh")
    memory = {a: int(b.split()[0]) * 1024 for a, b in
              (line.split(":", 1) for line in P("/proc/meminfo").read_text().splitlines())}
    # Fresh kernel counters are read above at this actual attempt; historical
    # diagnostic samples are evidence only, never admission authorization.
    memory_admission(memory)
    affinity = sorted(os.sched_getaffinity(0))
    require(len(affinity) >= 4, "original two-core placement requires at least four allowed CPUs")
    selected = affinity[-2:]
    os.sched_setaffinity(0, selected)
    text = P("/proc/self/cgroup").read_text().strip()
    require(text.startswith("0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-"),
            "not the exact owned user build unit")
    cgroup = P("/sys/fs/cgroup") / text[3:].lstrip("/")
    unit = cgroup.name
    require(unit.startswith("hepta-runtime-job-") and unit.endswith(".service"), "unexpected unit")
    require(str(os.getpid()) in (cgroup / "cgroup.procs").read_text().split(), "controller not in its claimed unit")
    require((cgroup / "memory.max").read_text().strip() == str(MEMORY_MAX), "wrong MemoryMax")
    require((cgroup / "cpu.max").read_text().strip() == "200000 100000", "wrong CPUQuota")
    subprocess.run(["/usr/bin/systemctl", "--user", "set-property", "--runtime", unit,
                    "MemorySwapMax=1073741824"], check=True, capture_output=True, timeout=15)
    require((cgroup / "memory.swap.max").read_text().strip() == str(SWAP_MAX), "wrong swap bound")
    subreaper()
    require(child_ids() == [], "controller has preexisting children or cannot enumerate its own children")
    ATTEMPT.mkdir(mode=0o700)
    claim = {"schema": 1, "state": "STARTING_TYPED_FRAMEWORK_NORMAL_STRICT_RESUME_TWO_TARGET_BUILD",
             "started_utc": utc(), "preparation_sha256": expected_sha, "plan": plan(),
             "mem_available_before": memory["MemAvailable"], "swap_free_before": memory["SwapFree"],
             "cpu_affinity_before": affinity,
             "cpu_affinity": selected, "unit": unit, "normal_builder_lock_and_recovery": True,
             "automatic_retry": False, "Main_resource_changes": False}
    claim["filesystem_available_before"] = os.statvfs(WORK).f_bavail * os.statvfs(WORK).f_frsize
    save(ATTEMPT / "claim.json", claim)
    save(ATTEMPT / "input-bindings-before.json", {
        "work_preparation": context["prepared_pin"], "actual_builder_compile": context["compiled_pin"],
        "actual_builder_manifest": context["builder_map_pin"], "actual_content_manifests": context["manifest_pins"],
        "reused_inventory_source": context["inventory_pin"], "observations": context["initial_observations"],
        "prior_failure_authorities": context["prior_failure_authority_pins"]})
    print(json.dumps(claim), flush=True)
    env = os.environ.copy()
    env["DROIDLOOM_NATIVE_BRIDGE_SOURCE"] = str(ENGINE_SOURCE)
    env["PATH"] = "/usr/bin:/usr/sbin:/bin:/sbin"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    argv = plan()["argv"]
    start = time.monotonic()
    child = None
    code = None
    failure = None
    artifact = None
    cleanup = {"complete": False, "children": []}
    def interrupted(signum, frame):
        raise InterruptedError("owned build controller received signal " + str(signum))
    old_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        with (ATTEMPT / "build.stdout").open("xb") as stdout, (ATTEMPT / "build.stderr").open("xb") as stderr:
            child = subprocess.Popen(argv, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = child.wait(timeout=6100)
            except BaseException:
                # No other thread/handler reaps this direct child. On a timed
                # out/interrupted wait its PID is retained until our exact wait;
                # this session/PGID was created solely for this owned builder.
                if child.returncode is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    code = child.wait(timeout=8)
                raise
        cleanup = cleanup_children()
        require(cleanup["complete"], "owned build descendants remain")
        require(code == 0, "normal builder returned " + str(code))
        artifact = completion_gate(context)
    except BaseException as error:
        failure = repr(error)
    finally:
        # A second interrupt must not abort bounded retirement after the first
        # one was recorded. Only this owned controller changes these handlers.
        old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if not cleanup["complete"]:
            try:
                cleanup = cleanup_children()
            except Exception as error:
                cleanup = {"complete": False, "error": repr(error), "children": []}
        if not cleanup["complete"] and failure is None:
            failure = "owned descendants were not proven retired"
        input_after = None
        input_after_error = None
        try:
            input_after = verify_inputs_after(context)
            save(ATTEMPT / "input-bindings-after.json", input_after)
        except BaseException as error:
            input_after_error = repr(error)
            if failure is None:
                failure = "post-build input qualification failed: " + repr(error)
        observation_errors = []
        def observe(label, operation):
            try:
                return operation()
            except Exception as error:
                observation_errors.append({"observation": label, "error": repr(error)})
                return None
        terminal = {"schema": 1, "state": "FRAMEWORK_COMMAND_COMPLETED_QUALIFICATION_PENDING" if failure is None else "FAILED",
                    "builder_returncode": code, "error": failure, "seconds": time.monotonic() - start,
                    "finished_utc": utc(), "cleanup": cleanup,
                    "stdout_sha256": observe("stdout", lambda: digest(ATTEMPT / "build.stdout")),
                    "stderr_sha256": observe("stderr", lambda: digest(ATTEMPT / "build.stderr")),
                    "memory_events": observe("memory_events", lambda: (cgroup / "memory.events").read_text()),
                    "memory_peak": observe("memory_peak", lambda: (cgroup / "memory.peak").read_text().strip()),
                    "memory_swap_peak": observe("memory_swap_peak", lambda: (cgroup / "memory.swap.peak").read_text().strip()),
                    "source_projection_journal_present": (WORK / "source-projection.json").exists(),
                    "normal_command_completion_gate": artifact,
                    "input_after_qualified": input_after is not None and input_after_error is None,
                    "input_after_error": input_after_error,
                    "work_preparation_sha256": PREPARATION_SHA, "builder_compile_sha256": BUILD_RESULT_SHA,
                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,
                    "prior_failed_inner_sha256": PRIOR_INNER_SHA, "prior_failed_outer_sha256": PRIOR_OUTER_SHA,
                    "explicit_resume_staging": str(RESUME_STAGING),
                    "source_progress_path": str(OUT / "droidloom-source-progress.jsonl"),
                    "complete_framework_Java_and_Android_TU_qualified": False,
                    "runtime_authorization_enabled": False, "Main_actions": 0, "Android_actions": 0,
                    "service_started": False, "all_apps_ready": False}
        try:
            terminal["owned_resource_gate"] = owned_resource_gate(terminal["memory_events"])
        except Exception as error:
            terminal["owned_resource_gate"] = {"pass": False, "error": repr(error)}
            if failure is None:
                failure = "owned resource qualification failed: " + repr(error)
                terminal["state"] = "FAILED"
                terminal["error"] = failure
        if observation_errors:
            terminal["observation_errors"] = observation_errors
            if failure is None:
                failure = "terminal resource/artifact observations incomplete"
                terminal["state"] = "FAILED"
                terminal["error"] = failure
        try:
            save(ATTEMPT / "terminal.json", terminal)
            print(json.dumps({"state": terminal["state"], "builder_returncode": code,
                              "terminal_sha256": digest(ATTEMPT / "terminal.json"),
                              "cleanup_complete": cleanup["complete"], "error": failure}), flush=True)
        finally:
            signal.signal(signal.SIGINT, old_int)
            signal.signal(signal.SIGTERM, old_term)
    return 0 if failure is None and cleanup["complete"] else 1

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--preparation-sha256')
    args = parser.parse_args(argv)
    if not args.build:
        require(args.preparation_sha256 is None, 'SHA provided without build mode')
        print(json.dumps(plan(), indent=2))
        return 0
    require(args.preparation_sha256 is not None, 'build requires its actual work receipt')
    return build(args.preparation_sha256)

if __name__ == '__main__':
    raise SystemExit(main())
