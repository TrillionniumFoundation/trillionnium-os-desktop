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

def parse_admission_meminfo(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 16384,
            "fixed meminfo byte bound differs")
    names = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "SwapCached"}
    memory = {}
    for line in raw.decode("ascii", "strict").splitlines():
        name, separator, value = line.partition(":")
        if name not in names:
            continue
        require(name not in memory, "duplicate required meminfo field")
        words = value.split()
        require(separator == ":" and len(words) == 2 and words[0].isdigit() and words[1] == "kB",
                "required meminfo field units differ")
        memory[name] = int(words[0]) * 1024
    require(set(memory) == names, "required meminfo fields incomplete")
    require(0 < memory["MemTotal"] and 0 <= memory["MemAvailable"] <= memory["MemTotal"] and
            0 <= memory["SwapFree"] <= memory["SwapTotal"] and memory["SwapCached"] >= 0,
            "required meminfo values inconsistent")
    return memory


def memory_admission(memory, owned):
    require(MEMORY_MAX == 10 * 1024**3 and SWAP_MAX == 0 and
            MIN_AVAILABLE - MEMORY_MAX == 5 * 1024**3,
            "independent ten-GiB zero-swap profile or five-GiB admission difference changed")
    require(owned["memory.max"] == str(MEMORY_MAX) and owned["cpu.max"] == "200000 100000",
            "owned RAM or CPU limit differs before admission")
    require(owned["memory.swap.max"] == "0", "owned swap limit is not zero")
    require(owned["memory.swap.current"] == "0", "existing owned swap is not zero")
    require(memory["MemAvailable"] >= MIN_AVAILABLE,
            "less than 15 GiB MemAvailable for independent zero-swap profile; no automatic retry")
    # Global swap is recorded, never counted as this build's available budget.


def record_resource_admission(cgroup):
    owned = {}
    for name in ("memory.max", "cpu.max", "memory.swap.max", "memory.swap.current"):
        with (cgroup / name).open("r", encoding="ascii") as stream:
            value = stream.read(65)
        require(0 < len(value) <= 64, "owned resource scalar bound differs")
        owned[name] = value.strip()
    with P("/proc/meminfo").open("rb") as stream:
        raw = stream.read(16385)
    require(0 < len(raw) <= 16384, "fixed meminfo byte bound differs")
    receipt = {
        "schema": 1, "state": "OBSERVED_BEFORE_RESOURCE_ADMISSION",
        "observed_utc": utc(), "observed_unix_ns_decimal": str(time.time_ns()),
        "profile": {"memory_max_bytes": MEMORY_MAX, "memory_swap_max_bytes": SWAP_MAX,
                    "minimum_fresh_MemAvailable_bytes": MIN_AVAILABLE,
                    "admission_difference_bytes": MIN_AVAILABLE - MEMORY_MAX,
                    "global_swap_is_owned_budget": False},
        "meminfo": {"path": "/proc/meminfo", "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(), "raw_ascii": raw.decode("ascii", "strict")},
        "owned_cgroup": str(cgroup), "owned_observed": owned,
        "decision_performed": False, "historical_sample_used_for_admission": False,
        "Main_actions": 0, "Android_actions": 0, "production_ready": False}
    path = ROOT / "resource-admission.json"
    save(path, receipt)
    pin, _ = held_file(path, 65536)
    print(json.dumps({"state": "FRESH_RESOURCE_ADMISSION_OBSERVED", "receipt": pin}), flush=True)
    # Persist the exact bounded read before parsing or comparing any resource threshold.
    memory = parse_admission_meminfo(raw)
    memory_admission(memory, owned)
    return memory, owned, pin

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
ROOT = OWNER / 'typed-ingress-framework-systemui-provider-build-06-20261106'
HERE = ROOT / 'control-source'
WORK = OWNER / 'typed-ingress-framework-work-01-20261105'
OUT = ROOT / 'android-out'
ATTEMPT = ROOT / 'attempt-01'
BUILD_PARENT = P('/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106')
BUILD_SOURCE = BUILD_PARENT / 'builder-source'
BUILDER = BUILD_PARENT / 'compile01/cargo-target/debug/droidloom-update'
BUILDER_SHA = 'e1d3dd7caf023e4709c2617318de97cc17906aae595b33c4c3290358e7d0dee5'
BUILDER_BYTES = 34817256
BUILD_RESULT = BUILD_PARENT / 'compile01/result.json'
BUILDER_MANIFEST = BUILD_PARENT / 'candidate-source-manifest.json'
QUALIFICATION_RESULT = BUILD_RESULT
QUALIFICATION_SHA = '6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8'
BUILD_RESULT_SHA = '6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8'
BUILD_RESULT_BYTES = 76136
SOURCE_MANIFEST_SHA = 'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'
PREPARE_PARENT = OWNER / 'typed-framework-work-preparation-01-20261105'
PREPARATION = PREPARE_PARENT / 'attempt01/result.json'
PREPARATION_SHA = 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'
INVENTORY_SOURCE_SHA = '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'
ENGINE_SOURCE = OWNER / 'full-build-combined07-go5-streaming-01/engine-working'
TETO_HEAD = 'a9496d886a85752ba407b76509952c06cd79ddb8'
EXTENDED_LOCK_SHA = 'f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772'
PREVIOUS_NATIVE_PROVIDER_LOCK_SHA = '72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d'
PREVIOUS_PROVIDER_LOCK_SHA = '5c28f77e998cb75fd04de121e43a36fc3d8515c18249930268a2ffb6e5e372f7'
PREVIOUS_TYPED_LOCK_SHA = 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54'
ORIGINAL_LOCK_SHA = '4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178'
GO_PATCH = 'android/apex-compat/0008-soong-leaf-go-memory-budget.patch'
GO_PATCH_SHA = '39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f'
MEMORY_MAX = 10 * 1024**3
SWAP_MAX = 0
MIN_AVAILABLE = 15 * 1024**3
TARGETS = ['framework-minus-apex', 'libandroid_runtime']
EXPECTED_TESTS = ['android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes', 'android::tests::restoration_preserves_original_and_removes_created_file', 'android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch', 'android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout', 'android::patch_tests::interrupted_projection_recovers_before_next_build', 'tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets', 'tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory', 'native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate', 'native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions', 'android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata', 'android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas', 'android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged', 'native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change', 'native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock', 'native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification', 'native_role_ingress::tests::native_provider_extension_rejects_missing_or_unpinned_providers', 'android::tests::typed_systemui_defaults_preserve_real_consumers_and_dependency_edges', 'android::tests::typed_systemui_projection_preserves_loaded_ordinary_dependencies', 'native_role_ingress::tests::systemui_extension_rejects_missing_provider_wrong_revision_or_scope']


PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-native-provider-build-05-20261106'
PUBLISHED_SOURCE = WORK / 'aosp-source'
PUBLISHED_MANIFEST_SHA = '5ae96f8d2bc32986fdbf8fea12f54dbcb02b1ed1601894b2b23998f61aba0d7d'
PUBLISHED_MANIFEST_BYTES = 109252
NATIVE_PREBUILT_BP_SHA = 'd1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a'
NATIVE_PREBUILT_BP_BYTES = 1017
NATIVE_PREBUILT_BP_GIT_SHA = '68246c4206ea702c8a66b73c37bfcacb51524086'
PRIOR_INNER_SHA = '232a63a6a48c4248346921ee7f9cb86f13d17dcd3abcb32e6a52856cda0dbbde'
PRIOR_OUTER_SHA = '1353fe85e19ae79f4b615e7f38efcbb2f45f8a34529a3be6c59a6ed585e1a1f2'
EXPECTED_SOURCE_TESTS = ['resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify', 'resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock', 'resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected', 'resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest', 'resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed', 'resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout', 'resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging', 'resume::tests::mismatched_staging_manifest_is_preserved_and_not_published', 'resume::tests::sparse_parent_normalization_keeps_exact_locked_selection']
EXPECTED_COMPILE_LABELS = ['rust-version', 'build', 'test-compile', 'test-list', 'projection-test-0', 'projection-test-1', 'projection-test-2', 'projection-test-3', 'projection-test-4', 'projection-test-5', 'projection-test-6', 'projection-test-7', 'projection-test-8', 'projection-test-9', 'projection-test-10', 'projection-test-11', 'projection-test-12', 'projection-test-13', 'projection-test-14', 'projection-test-15', 'projection-test-16', 'projection-test-17', 'projection-test-18']
EXPECTED_SOURCE_DELTA = {'unchanged_existing': 491, 'changed_existing': ['tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/native_role_ingress.rs'], 'added': ['android/manifest/m2-role-ingress-provider3-source-lock.json', 'android/native-role-ingress/provider-fixtures/SystemUI-pods-build.Android.bp', 'android/native-role-ingress/provider-fixtures/SystemUI-pods-policy.Android.bp', 'android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp', 'android/native-role-ingress/provider-fixtures/WindowManager-Shell.Android.bp'], 'actual_source_file_count': 498}


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


def match_compile_pin(observed, recorded):
    identity_value = recorded['identity']
    require(len(identity_value) == 5 and all(isinstance(value, int) for value in identity_value[:3]) and
            all(isinstance(value, str) and value.isdecimal() for value in identity_value[3:]),
            'compile02 exact identity format differs')
    expected_identity = identity_value[:3] + [recorded['bytes'],
        int(identity_value[3]), int(identity_value[4])]
    require(recorded['resolved_path'] == recorded['path'] == observed['path'] and
            observed['bytes'] == recorded['bytes'] and observed['sha256'] == recorded['sha256'] and
            observed['identity'] == expected_identity,
            'actual compile02 held file identity/content differs')


def qualify_builder470_receipt(result):
    # This checks the pinned actual receipt. It does not compile or run tests.
    require(result['state'] == 'RUST_BUILD_AND_19_INDEPENDENT_FOCUSED_TESTS_PASS' and
            result['test_names'] == EXPECTED_TESTS and result['tests_passed'] == 19 and
            result['registered_tests'] == 209 and result['source_files'] == 498 and
            result['new_project_count'] == 242 and
            result['source_manifest_sha256'] == SOURCE_MANIFEST_SHA,
            'actual builder470 result/source/test closure differs')
    require([row['label'] for row in result['commands']] == EXPECTED_COMPILE_LABELS and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in result['commands']) and
            len(result['independent_result_gates']) == 19,
            'actual builder470 command or independent gate closure differs')
    require(all(result[key] is True for key in ['candidate_source_unchanged_after',
                'baseline_source_unchanged_after', 'registry_input_bytes_and_full_identities_unchanged_after',
                'tool_inputs_unchanged_after']) and
            result['cleanup'] == {'complete': True, 'children': [], 'errors': []} and
            result['owned_resource_gate']['pass'] is True and
            all(result['owned_resource_gate']['events'][key] == 0 for key in ['oom', 'oom_kill', 'oom_group_kill']) and
            result['memory_peak'] == '1073741824' and result['owned_resource_gate']['events']['max'] == 657 and
            result['swap_peak'] == '0' and result['Soong_invoked'] is False and
            result['full_Android_Java_JNI_compiled'] is False and
            result['runtime_authorization_enabled'] is False and result['production_ready'] is False and
            result['Main_actions'] == result['Android_actions'] == result['install_actions'] == 0 and
            'HOME' not in result['build_environment'] and
            result['build_environment']['CARGO_NET_OFFLINE'] == 'true' and
            result['build_environment']['CARGO_BUILD_JOBS'] == '1',
            'actual builder470 source/resource/child/scope qualification differs')
    for index, name in enumerate(EXPECTED_TESTS):
        row = result['commands'][index + 4]
        log_path = BUILD_RESULT.parent / ('projection-test-' + str(index) + '.libtest')
        expected_log = ('ok ' + name + '\n').encode()
        gate = {'exact_name': name, 'expected_stdout_runs': 1, 'filtered_out_per_run': 208,
                'outer_results': 1, 'registered_tests': 209, 'summary_and_independent_result_agree': True}
        require(row['argv'] == [result['test_executable']['path'], '--exact', name,
                '--test-threads=1', '--nocapture', '--logfile', str(log_path)] and
                row['focused_result_gate'] == result['independent_result_gates'][index] == gate and
                row['independent_libtest_result']['path'] == str(log_path) and
                row['independent_libtest_result']['bytes'] == len(expected_log) and
                row['independent_libtest_result']['sha256'] == hashlib.sha256(expected_log).hexdigest(),
                'actual builder470 independent exact test differs: ' + name)
    continuity = result['dependency_continuity']
    require(continuity['all_source_bytes_and_full_identities_equal_before'] is True and
            continuity['recorded_files_and_archives'] == 2706 and continuity['selected_packages'] == 49 and
            continuity['registry_packages'] == 45 and continuity['new_dependency_fetches'] == 0 and
            len(continuity['actual_build_packages']) == len(set(continuity['actual_build_packages'])) == 49 and
            continuity['actual_build_packages'] == continuity['actual_test_compile_packages'] and
            result['source_delta'] == EXPECTED_SOURCE_DELTA,
            'actual builder470 dependency or seven-file successor differs')


def builder_contract():
    # Preserve the genuine normal05 predecessor contract and all its old
    # authorities. Neither its source nor receipts are rewritten as builder470.
    parent_path = HERE / 'parent-normal05-framework_build.py'
    parent_pin, parent_raw = held_file(parent_path, 65536, True)
    require(parent_pin['bytes'] == 60970 and
            parent_pin['sha256'] == 'f4ab5e09fc22b759811bfa9480c2de555dbc5096bc1258a984dbd33809db734b',
            'original normal05 builder contract changed')
    parent_scope = {'__name__': 'original_normal05_builder_contract', '__file__': str(parent_path)}
    exec(compile(parent_raw, str(parent_path), 'exec'), parent_scope, parent_scope)
    parent_compiled, parent_compiled_pin, parent_map, parent_map_pin, parent_builder = parent_scope['builder_contract']()
    parent_qualification, parent_qualification_pin = json_pin(
        parent_scope['QUALIFICATION_RESULT'], parent_scope['QUALIFICATION_SHA'], 65386)

    result, pin = json_pin(BUILD_RESULT, BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    staged, _ = json_pin(HERE / 'actual-builder470-result.json', BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    require(result == staged and result['baseline_compile'] == parent_compiled_pin and
            result['baseline_independent_qualification'] == parent_qualification_pin and
            result['baseline_manifest'] == parent_map_pin,
            'actual builder470 predecessor authority differs')
    qualify_builder470_receipt(result)
    # The inherited normal preflight keeps command and independent-result files
    # identity-bound on the host; no log replay or test execution is performed.
    for row in result['commands']:
        for stream in ('stdout', 'stderr'):
            observed, _ = held_file(row[stream]['path'], 32*1024*1024)
            require(observed == row[stream], 'actual builder470 command output identity changed')
    for index, name in enumerate(EXPECTED_TESTS):
        row = result['commands'][index + 4]
        actual_log, raw_log = held_file(row['independent_libtest_result']['path'], 4096, True)
        require(actual_log == row['independent_libtest_result'] and raw_log == ('ok ' + name + '\n').encode(),
                'actual held builder470 independent libtest log changed: ' + name)

    continuity = result['dependency_continuity']
    dependency_authority, _ = held_file(continuity['authority']['path'], 2*1024*1024)
    expected_packages = sorted(value.replace(str(parent_scope['BUILD_SOURCE']), str(BUILD_SOURCE))
                               for value in parent_compiled['actual_build_packages'])
    require(dependency_authority == continuity['authority'] and
            {key: continuity['authority'][key] for key in ('path', 'bytes', 'sha256')} ==
                parent_compiled['dependency_inputs'] and
            continuity['actual_build_packages'] == expected_packages and
            result['profile_authority'] == parent_qualification['original_compiler03_authority'],
            'actual builder470 original dependency/profile authority differs')
    admission, admission_pin = json_pin(BUILD_PARENT / 'compile01/resource-admission.json',
        '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031', 2746)
    staged_admission, _ = json_pin(HERE / 'actual-builder470-resource-admission.json',
        '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031', 2746)
    recorded_admission = result['resource_admission']
    require(admission == staged_admission and
            {key: admission_pin[key] for key in ('path', 'bytes', 'sha256')} ==
                {key: recorded_admission[key] for key in ('path', 'bytes', 'sha256')} and
            admission_pin['identity'] == recorded_admission['identity'][:3] +
                [recorded_admission['bytes']] + [int(value) for value in recorded_admission['identity'][3:]] and
            admission['profile'] == {'memory_max_bytes': 1073741824, 'memory_swap_max_bytes': 0,
                'minimum_fresh_MemAvailable_bytes': 3221225472, 'admission_difference_bytes': 2147483648,
                'global_swap_is_owned_budget': False} and
            admission['owned_observed'] == {'memory.max': '1073741824', 'cpu.max': '100000 100000',
                'memory.swap.max': '0', 'memory.swap.current': '0'} and
            parse_admission_meminfo(admission['meminfo']['raw_ascii'].encode('ascii'))['MemAvailable'] >= 3*1024**3 and
            len(result['cpu_affinity']) == 1,
            'actual builder470 one-GiB Rust resource authority differs')

    source_map, source_pin = json_pin(BUILDER_MANIFEST, SOURCE_MANIFEST_SHA, 99075)
    staged_map, _ = json_pin(HERE / 'expected-builder470-manifest.json', SOURCE_MANIFEST_SHA, 99075)
    changed = sorted(name for name in parent_map if source_map.get(name) != parent_map[name])
    added = sorted(set(source_map) - set(parent_map))
    require(source_map == staged_map and result['candidate_manifest'] == source_pin and
            len(source_map) == 498 and set(parent_map) <= set(source_map) and
            changed == EXPECTED_SOURCE_DELTA['changed_existing'] and added == EXPECTED_SOURCE_DELTA['added'] and
            source_map[GO_PATCH]['sha256'] == GO_PATCH_SHA and
            source_map['android/manifest/m2-role-ingress-source-lock.json']['sha256'] == PREVIOUS_TYPED_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider-source-lock.json']['sha256'] == PREVIOUS_PROVIDER_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider2-source-lock.json']['sha256'] == PREVIOUS_NATIVE_PROVIDER_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider3-source-lock.json']['sha256'] == EXTENDED_LOCK_SHA,
            'full builder470 source manifest is not the exact seven-file successor')
    builder, _ = held_file(BUILDER, 64*1024*1024)
    match_compile_pin(builder, result['builder'])
    require(builder['sha256'] == BUILDER_SHA and builder['bytes'] == BUILDER_BYTES and
            builder['identity'][2] & 0o111,
            'actual builder470 ELF changed')
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
        (PREVIOUS_ROOT / 'attempt-01/terminal.json', 'prior-framework-inner-terminal.json', PRIOR_INNER_SHA, 3176),
        (PREVIOUS_ROOT / 'build-fences-01/terminal.json', 'prior-framework-outer-terminal.json', PRIOR_OUTER_SHA, 24715),
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
    require(inner['state'] == 'FAILED' and inner['builder_returncode'] == 1 and
            inner['error'] == "RuntimeError('normal builder returned 1')" and
            inner['cleanup']['complete'] is True and not inner['cleanup']['errors'] and
            len(inner['cleanup']['children']) == 4 and
            all(row['reaped'] is True for row in inner['cleanup']['children']) and
            inner['normal_command_completion_gate'] is None and
            inner['source_projection_journal_present'] is False and
            inner['input_after_qualified'] is True and inner['input_after_error'] is None and
            inner['owned_resource_gate']['pass'] is True and
            inner['memory_swap_peak'] == inner['memory_swap_current'] == inner['memory_swap_max'] == '0' and
            inner['stdout_sha256'] == '5453e358a70d1531218699641b289e58dfbe13202d7ad369f46b5fbf016eb151' and
            inner['stderr_sha256'] == '615d8e9d5fdd2e2fb31c605e4eed204e92a5f0ab21621765bb6c27115d0c339e',
            'prior normal05 strict failure or complete owned-child retirement differs')
    require(outer['state'] == 'FAILED' and outer['inner_returncode'] == 1 and
            outer['main_fence_assessment']['main_fence_pass'] is True and
            outer['main_fence_assessment']['identity_or_limit_changes'] == [] and
            outer['main_fence_assessment']['main_oom_delta_zero'] is True and
            outer['capture_lifecycle_controls']['state'] == 'PASS' and
            outer['capture_lifecycle_controls']['passed'] == 4 and
            outer['before_observed'] is True and outer['after_observed'] is True,
            'prior fixed Main fence result differs')
    published, row = json_pin(HERE / 'actual-published-source-manifest.json',
                             PUBLISHED_MANIFEST_SHA, PUBLISHED_MANIFEST_BYTES)
    pins.append(row)
    require(published['schema_version'] == 1 and published['source_lock_sha256'] == PREVIOUS_NATIVE_PROVIDER_LOCK_SHA and
            published['plan']['schema_version'] == 1 and published['plan']['unrestricted_repo_sync'] is False and
            published['plan']['superproject_commit'] == '28f0bbddc24d56c8ec5a8df5342ac7a292184039' and
            len(published['plan']['projects']) == 225 and len(published['plan']['links']) == 8,
            'actual current provider2 published source manifest differs')
    bp_row, bp_raw = held_file(HERE / 'actual-native-prebuilt-Android.bp', 65536, True)
    require(bp_row['bytes'] == NATIVE_PREBUILT_BP_BYTES and bp_row['sha256'] == NATIVE_PREBUILT_BP_SHA and
            hashlib.sha1(b'blob ' + str(len(bp_raw)).encode() + b'\0' + bp_raw).hexdigest() == NATIVE_PREBUILT_BP_GIT_SHA,
            'actual locked native prebuilt provider body differs')
    pins.append(bp_row)
    return published, pins

def fresh_published_binding(context, scope, state, current_work):
    require(current_work[:5] == [66306, 41861500, 16832, 1000, 1000],
            'published workspace no longer has the fixed owned directory identity')
    fd = scope['directory'](PUBLISHED_SOURCE, state)
    actual = scope['full_identity'](os.fstat(fd))
    require(actual[:5] == [66306, 41861660, 16832, 1000, 1000],
            'published source is not the actual observed private directory object')
    manifest, row = json_pin(PUBLISHED_SOURCE / '.droidloom-source-manifest.json',
                             PUBLISHED_MANIFEST_SHA, PUBLISHED_MANIFEST_BYTES)
    require(manifest == context['published_manifest'], 'published source manifest changed before normal qualification')
    journal = WORK / 'source-projection.json'
    try:
        journal.lstat()
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError('unexpected existing source projection journal')
    return {'work_identity': current_work, 'source_identity': actual,
        'published_source_path': str(PUBLISHED_SOURCE), 'manifest': row,
        'previous_locked_projects': 225, 'new_locked_projects': 242, 'root_links': 8,
        'all_projects_reuse_qualified_by_wrapper': False,
        'all_project_qualification_deferred_to_normal_builder_under_existing_work_source_locks': True,
        'normal_full_old_lock_verification_then_monotonic_reconciliation': True,
        'source_manifest_written_by_wrapper': False, 'explicit_resume_staging': None}

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
            observations['published_source'] = fresh_published_binding(context, scope, state, current_work)
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
        require(portable == context['builder_map'], 'actual 498-file builder source changed')
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
            published_fd = scope['directory'](PUBLISHED_SOURCE, state)
            published_identity = scope['full_identity'](os.fstat(published_fd))
            require(published_identity[:5] ==
                    context['initial_observations']['published_source']['source_identity'][:5],
                    'published source directory object changed during the normal build')
            observations['published_source_identity_after'] = published_identity
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
    context['qualification_pin'] = json_pin(QUALIFICATION_RESULT, QUALIFICATION_SHA, BUILD_RESULT_BYTES)[1]
    context['published_manifest'], context['prior_failure_authority_pins'] = prior_failure_contract()
    context['initial_observations'] = observe_inputs(context, True)
    return context


def plan():
    return {'schema': 1, 'state': 'PLAN_NORMAL_STRICT_FRAMEWORK_PROVIDER_BUILD',
        'root': str(ROOT), 'work': str(WORK), 'aosp_source': str(PUBLISHED_SOURCE), 'out': str(OUT),
        'builder_result_sha256': BUILD_RESULT_SHA, 'work_preparation_sha256': PREPARATION_SHA,
        'builder_sha256': BUILDER_SHA, 'builder_source_manifest_sha256': SOURCE_MANIFEST_SHA,
        'builder_source_files': 498, 'actual_host_compile_commands': 23, 'actual_current_exact_controls': 19,
        'qualification_commands': 19, 'qualification_commands_included_in_host_compile': True,
        'separate_qualification_commands': 0, 'unchanged_source_resume_controls_inherited': 9,
        'source_resume_controls_rerun_in_successor': False, 'qualification_result_sha256': QUALIFICATION_SHA,
        'argv': [str(BUILDER), '--source', str(BUILD_SOURCE), '--jobs', '1',
                 'native-role-ingress-build', '--work', str(WORK), '--out', str(OUT)],
        'targets': TARGETS, 'dependency_mode': 'Strict', 'ALLOW_MISSING_DEPENDENCIES': False,
        'source_materialization': 'fresh verification of the published 225-project provider2 lock, then normal monotonic reconciliation to 242 locked projects and 8 root links',
        'published_source_manifest_sha256': PUBLISHED_MANIFEST_SHA,
        'reuse_qualified_by_plan': False, 'prior_inner_failure_sha256': PRIOR_INNER_SHA,
        'prior_outer_failure_sha256': PRIOR_OUTER_SHA, 'prior_reaped_children': 4,
        'actual_builder470_job_id': '1a1b1d86cb7-fc05-7b1f',
        'prior_compile_status_timeout_preserved_then_authoritatively_settled': True,
        'first_attempt_timeout_and_296_reaped_history_retained': True,
        'normal_lock_paths': [str(WORK / 'package-build.lock'), str(WORK / 'aosp-source-update.lock')],
        'normal_package_and_source_locks': True, 'normal_projection_journal_and_recovery': True,
        'old_shared_AOSP_source_modified': False, 'source_manifest_fabrication': False,
        'memory_max_bytes': MEMORY_MAX, 'memory_swap_max_bytes': SWAP_MAX,
        'fresh_MemAvailable_min_bytes': MIN_AVAILABLE, 'fresh_SwapFree_min_bytes': None,
        'global_swap_free_recorded_only': True, 'owned_swap_current_required_bytes': 0,
        'resource_admission_receipt': str(ROOT / 'resource-admission.json'),
        'admission_difference_bytes': MIN_AVAILABLE - MEMORY_MAX,
        'prior_normal_peak_bytes': 3168141312, 'prior_normal_swap_peak_bytes': 0,
        'actual_static_compile_peak_bytes': 1073741824, 'actual_static_compile_memory_max_events': 657,
        'static_compile_pressure_not_normal_Soong_qualification': True,
        'cpu_quota_percent': 200, 'jobs': 1, 'builder_wait_seconds': 6100,
        'automatic_retry': False, 'Main_actions': 0, 'Android_actions': 0,
        'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
        'runtime_authorization_enabled': False, 'Mesa_tools_not_fabricated_or_prequalified': True,
        'strict_dependency_failure_not_suppressed': True,
        'normal_build_success_not_complete_Java_JNI_qualification': True}

def expected_published_manifest(lock):
    projects = []
    for project in lock['projects']:
        row = {'path': project['path'], 'url': lock['remote_base'] + project['name'],
               'commit': project['commit'], 'purpose': project['purpose']}
        if project.get('sparse_paths'):
            row['sparse_paths'] = project['sparse_paths']
        projects.append(row)
    return {'schema_version': 1, 'source_lock_sha256': EXTENDED_LOCK_SHA,
            'plan': {'schema_version': 1, 'superproject_commit': lock['superproject']['commit'],
                     'projects': projects, 'links': lock['links'], 'unrestricted_repo_sync': False}}


def qualify_completed_manifest(document, lock):
    expected = expected_published_manifest(lock)
    require(document == expected and len(document['plan']['projects']) == 242 and
            len(document['plan']['links']) == 8,
            'normal published manifest is not the exact complete new locked plan')


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
    require(inputs['previous_typed_source_lock_sha256'] == PREVIOUS_TYPED_LOCK_SHA and
            inputs['provider_source_lock_extension_exact'] is True and
            inputs['previous_provider_source_lock_sha256'] == PREVIOUS_PROVIDER_LOCK_SHA and
            inputs['native_provider_extension_exact'] is True and
            inputs['previous_native_provider_source_lock_sha256'] == PREVIOUS_NATIVE_PROVIDER_LOCK_SHA and
            inputs['systemui_provider_extension_exact'] is True and
            inputs['host_only_libandroid_runtime_is_insufficient'] is True and
            inputs['complete_framework_Java_and_Android_TU_verified'] is False and
            inputs['transitive_build_closure_qualified'] is False,
            'framework input record claims an unverified artifact or host-only qualification')
    lock, _ = json_pin(BUILD_SOURCE / 'android/manifest/m2-role-ingress-provider3-source-lock.json',
                       EXTENDED_LOCK_SHA, 103409)
    manifest_pin, manifest_raw = held_file(PUBLISHED_SOURCE / '.droidloom-source-manifest.json', 1024*1024, True)
    qualify_completed_manifest(json.loads(manifest_raw), lock)
    native_bp, _ = held_file(PUBLISHED_SOURCE / 'prebuilts/misc/common/robolectric-native-prebuilt/Android.bp', 65536)
    require(native_bp['bytes'] == NATIVE_PREBUILT_BP_BYTES and native_bp['sha256'] == NATIVE_PREBUILT_BP_SHA,
            'locked native prebuilt provider body differs after the normal build')
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
        'actual_published_manifest': manifest_pin, 'published_projects': 242, 'published_root_links': 8,
        'actual_locked_native_prebuilt_provider': native_bp,
        'targets': TARGETS, 'dependency_mode': 'Strict', 'source_projection_restored': True,
        'Java_framework_implementation_jar_qualified': False, 'Android_JNI_TU_and_linked_library_qualified': False,
        'host_only_ELF_or_header_jar_is_sufficient': False, 'runtime_authorization_enabled': False,
        'installation_performed': False}


def verify_inputs_after(context):
    observations = observe_inputs(context, False)
    for path, wanted in [(PREPARATION, context['prepared_pin']), (BUILD_RESULT, context['compiled_pin']),
                         (HERE / 'frozen-work-inventory.py', context['inventory_pin']),
                         (BUILDER_MANIFEST, context['builder_map_pin']),
                         (QUALIFICATION_RESULT, context['qualification_pin'])]:
        row, _ = held_file(path, wanted['bytes'])
        require(row == wanted, 'runtime input authority changed: ' + str(path))
    for wanted in context['prior_failure_authority_pins']:
        row, _ = held_file(wanted['path'], wanted['bytes'])
        require(row == wanted, 'original failure or staged source authority changed')
    return observations


def build(expected_sha):
    require(os.getuid() == 1000 and os.geteuid() == 1000, "build requires original operator uid")
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    context = verify_prepared(expected_sha)
    no_alias(ATTEMPT)
    no_alias(OUT)
    require(not ATTEMPT.exists() and not OUT.exists(), "attempt and output must both be fresh")
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
                    "MemorySwapMax=0"], check=True, capture_output=True, timeout=15)
    # Only this exact owned job is changed. Its observed zero swap limit/current
    # and a fresh kernel RAM sample are saved before admission can pass or fail.
    memory, owned_budget_before, resource_admission_pin = record_resource_admission(cgroup)
    subreaper()
    require(child_ids() == [], "controller has preexisting children or cannot enumerate its own children")
    ATTEMPT.mkdir(mode=0o700)
    claim = {"schema": 1, "state": "STARTING_TYPED_FRAMEWORK_NORMAL_STRICT_PROVIDER_TWO_TARGET_BUILD",
             "started_utc": utc(), "preparation_sha256": expected_sha, "plan": plan(),
             "mem_available_before": memory["MemAvailable"], "swap_free_before": memory["SwapFree"],
             "resource_admission_receipt": resource_admission_pin,
             "resource_admission_qualified": True, "owned_budget_before_builder": owned_budget_before,
             "global_swap_is_owned_budget": False,
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
                    "memory_swap_current": observe("memory_swap_current", lambda: (cgroup / "memory.swap.current").read_text().strip()),
                    "memory_swap_max": observe("memory_swap_max", lambda: (cgroup / "memory.swap.max").read_text().strip()),
                    "resource_admission_receipt": resource_admission_pin,
                    "owned_budget_before_builder": owned_budget_before,
                    "global_swap_is_owned_budget": False,
                    "source_projection_journal_present": (WORK / "source-projection.json").exists(),
                    "normal_command_completion_gate": artifact,
                    "input_after_qualified": input_after is not None and input_after_error is None,
                    "input_after_error": input_after_error,
                    "work_preparation_sha256": PREPARATION_SHA, "builder_compile_sha256": BUILD_RESULT_SHA,
                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,
                    "prior_failed_inner_sha256": PRIOR_INNER_SHA, "prior_failed_outer_sha256": PRIOR_OUTER_SHA,
                    "published_source_path": str(PUBLISHED_SOURCE),
                    "source_reconciliation_uses_normal_builder": True,
                    "old_QA_epoch_invalid": True, "new_QA_epoch_qualified": False,
                    "complete_framework_Java_and_Android_TU_qualified": False,
                    "runtime_authorization_enabled": False, "Main_actions": 0, "Android_actions": 0,
                    "service_started": False, "all_apps_ready": False}
        try:
            terminal["owned_resource_gate"] = owned_resource_gate(terminal["memory_events"])
            require(terminal["memory_swap_max"] == "0" and terminal["memory_swap_current"] == "0",
                    "owned zero-swap budget changed after build")
            terminal["owned_resource_gate"]["zero_swap_limit_and_current_observed_after"] = True
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
