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
ROOT = OWNER / 'composer-retirement-normal-build-01-20261106'
HERE = ROOT / 'control-source'
WORK = OWNER / 'typed-ingress-framework-work-01-20261105'
OUT = ROOT / 'android-out'
ATTEMPT = ROOT / 'attempt-01'
BUILD_PARENT = P("/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106")
BUILD_SOURCE = BUILD_PARENT / 'builder-source'
BUILDER = BUILD_PARENT / 'attempt01/cargo-target/debug/droidloom-update'
BUILDER_SHA = "b0ec0e8a52008a0806a310fa07ec48e8eeb0d9b8b30ef293e5303f4d08fdaedc"
BUILDER_BYTES = 34888128
BUILD_RESULT = BUILD_PARENT / 'attempt01/result.json'
BUILD_RESULT_SHA = "d3b0264441b2af0684c9f147bbb32e274a6d42f96fd83c19f0f24ba6937ad294"
BUILD_RESULT_BYTES = 197750
SOURCE_MANIFEST_SHA = "e18fe837795e9c3bd684592f3c91228604b2b21ca9d918ac56cebdb4b40754dd"
PREPARE_PARENT = OWNER / 'typed-framework-work-preparation-01-20261105'
PREPARATION = PREPARE_PARENT / 'attempt01/result.json'
PREPARATION_SHA = 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'
INVENTORY_SOURCE_SHA = '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'
ENGINE_SOURCE = OWNER / 'full-build-combined07-go5-streaming-01/engine-working'
TETO_HEAD = 'a9496d886a85752ba407b76509952c06cd79ddb8'
EXTENDED_LOCK_SHA = '72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d'
PREVIOUS_PROVIDER_LOCK_SHA = '5c28f77e998cb75fd04de121e43a36fc3d8515c18249930268a2ffb6e5e372f7'
PREVIOUS_TYPED_LOCK_SHA = 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54'
ORIGINAL_LOCK_SHA = '4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178'
GO_PATCH = 'android/apex-compat/0008-soong-leaf-go-memory-budget.patch'
GO_PATCH_SHA = '39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f'
MEMORY_MAX = 10 * 1024**3
SWAP_MAX = 0
MIN_AVAILABLE = 15 * 1024**3
TARGETS = ["android.hardware.graphics.composer3-service.droidloom","droidloom-composer-aidl-tests"]
EXPECTED_TESTS = ["android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes","android::tests::restoration_preserves_original_and_removes_created_file","android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch","android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout","android::patch_tests::interrupted_projection_recovers_before_next_build","tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets","tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory","native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate","native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions","android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata","android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas","android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged","native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change","native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock","native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification","android::tests::typed_hal_provider_projection_restores_real_sources_and_keeps_consumers","android::tests::typed_hal_provider_late_source_drift_restores_earlier_projections","native_role_ingress::tests::hal_provider_extension_preserves_all_prior_projects_and_rejects_unlisted_changes","tests::composer_retirement_cli_requires_exact_workspace_and_fresh_output","android::tests::composer_retirement_route_is_strict_and_disjoint_from_framework","android::tests::composer_retirement_fixed_sources_reject_alias_drift_and_restore_projection","android::tests::composer_retirement_workspace_rejects_prior_lock_and_manifest_only","android::tests::composer_retirement_exact_systemui_projection_rejects_drift_and_recovers","android::tests::composer_retirement_audiocontrol_example_projection_keeps_metadata_and_sibling_sources","android::tests::composer_retirement_audiocontrol_example_projection_rejects_source_drift_before_write","android::tests::composer_retirement_audiocontrol_example_projection_recovers_full_observed_original"]
EXPECTED_TEST_INDICES = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,200,201,202,203,204,205,206,207]


PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-provider-build-08-20261106'
RESOURCE_REJECTED_ROOT = OWNER / 'typed-ingress-framework-provider-build-09-20261106'
PUBLISHED_SOURCE = WORK / 'aosp-source'
PUBLISHED_MANIFEST_SHA = '5ae96f8d2bc32986fdbf8fea12f54dbcb02b1ed1601894b2b23998f61aba0d7d'
PUBLISHED_MANIFEST_BYTES = 109252
NATIVE_PREBUILT_BP_SHA = 'd1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a'
NATIVE_PREBUILT_BP_BYTES = 1017
NATIVE_PREBUILT_BP_GIT_SHA = '68246c4206ea702c8a66b73c37bfcacb51524086'
PRIOR_INNER_SHA = '58a68cae2784bf401315c8016108304576e11d16bf3d5c64552698d4c3a2bb57'
PRIOR_OUTER_SHA = '2e10bdca3a1b88fe8e72f87dde5f38d972f8db41ce087386fa189c40ad231612'
EXPECTED_SOURCE_TESTS = ['resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify', 'resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock', 'resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected', 'resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest', 'resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed', 'resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout', 'resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging', 'resume::tests::mismatched_staging_manifest_is_preserved_and_not_published', 'resume::tests::sparse_parent_normalization_keeps_exact_locked_selection']
EXPECTED_COMPILE_LABELS = ["cargo-version","rustc-version","linked-libraries-0","linked-libraries-1","linked-libraries-2","linked-libraries-3","linked-libraries-4","linked-libraries-5","linked-libraries-6","linked-libraries-7","image-linked-libraries-0","image-linked-libraries-1","image-linked-libraries-2","image-linked-libraries-3","image-linked-libraries-4","image-linked-libraries-5","image-linked-libraries-6","image-linked-libraries-7","image-linked-libraries-8","image-linked-libraries-9","image-linked-libraries-10","image-linked-libraries-11","image-linked-libraries-12","image-linked-libraries-13","image-linked-libraries-14","workspace-no-deps","selected-build","selected-test","builder-compile","builder-help","source-resume-cli-help","composer-retirement-cli-help","builder-test-compile","builder-test-list","builder-test-help","projection-test-0","projection-test-1","projection-test-2","projection-test-3","projection-test-4","projection-test-5","projection-test-6","projection-test-7","projection-test-8","projection-test-9","projection-test-10","projection-test-11","projection-test-12","projection-test-13","projection-test-14","projection-test-15","projection-test-16","projection-test-17","projection-test-200","projection-test-201","projection-test-202","projection-test-203","projection-test-204","projection-test-205","projection-test-206","projection-test-207","source-resume-selected-test","source-resume-test-compile","source-resume-test-list","source-resume-test-help","projection-test-100","projection-test-101","projection-test-102","projection-test-103","projection-test-104","projection-test-105","projection-test-106","projection-test-107","projection-test-108"]
EXPECTED_SOURCE_DELTA = json.loads("{\"ACK_nine_production_sources_unchanged_from_actual_Wayland03\":true,\"Cargo_lock_or_dependency_manifest_changed\":false,\"Composer472_entry_and_SystemUI_projection_retained\":true,\"Go5_or_Blueprint_patch_changed\":false,\"Rust_source_files_changed\":1,\"actual_source_file_count\":501,\"added\":[\"android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp\"],\"builder_revision_name\":\"474-composer-audiocontrol-example-projection\",\"changed_existing\":[\"tools/droidloom-update/src/android.rs\"],\"current_hal_source_lock_unchanged\":true,\"engine_source_files_changed\":0,\"fixed_Audiocontrol_example_BP_original_fixture_added\":true,\"framework_sources_executed_or_built\":false,\"new_exact_hal_provider_source_lock_added\":false,\"new_exact_provider_source_lock_added\":false,\"previous_source_locks_changed\":false,\"real_published_source_accessed\":false,\"real_source_staging_accessed\":false,\"runtime_authorization_enabled\":false,\"source_resume_library_changed\":false,\"typed_builder473_not_changed_or_used_as_baseline\":true,\"typed_ingress_framework_patch_changed\":false,\"unchanged_existing\":499}")


COMPOSER_INPUTS = json.loads("{\"graphics/droidloom-denial-protocol/src/lib.rs\":{\"bytes\":105464,\"sha256\":\"6c7f8df133f2a9e55bd375da4b39dcba5b00d0c4c3ba6531a6b8be329ebce41c\"},\"graphics/droidloom-denial-endpoint/src/lib.rs\":{\"bytes\":63752,\"sha256\":\"062b65857160eb6e3aeba2a78c4ce3d8503c02572f24353f8c944d950e52308c\"},\"graphics/droidloom-wayland/src/retirement.rs\":{\"bytes\":11118,\"sha256\":\"383f4c6f7490c8568f1853af6e9449fdb35bdb088348de4a9856d75f97306873\"},\"graphics/droidloom-wayland/src/main.rs\":{\"bytes\":110131,\"sha256\":\"0f56264e971db9f246d8db34d7fd5de157fd389a97bfb34492a6f53376d27459\"},\"graphics/droidloom-wayland/src/layers.rs\":{\"bytes\":35990,\"sha256\":\"d0a81ce5339c5020496e9b73e007d52ee206449827269b272e4ef6ef43df5ecc\"},\"graphics/droidloom-composer-aidl/src/denial.rs\":{\"bytes\":50513,\"sha256\":\"d6f13720da4267ff46f369617faecbb8c6446eca2c624e381c1ff51ddaebbf09\"},\"graphics/droidloom-composer/src/denial.rs\":{\"bytes\":25541,\"sha256\":\"ed0080cd33a3a4fa67b3a0c2e95bc274ab38e992ec073ab01d87b910bf2db3c8\"},\"graphics/droidloom-composer-service/src/main.rs\":{\"bytes\":19202,\"sha256\":\"567c60fd293f35e2e0957db6f38bc967cc0c3fa90354b98491d461a7decdb4ce\"},\"graphics/droidloom-composer-service/src/control.rs\":{\"bytes\":42491,\"sha256\":\"d3d9f4b763a6e80b6549119e42b4d6c3c6ab7368359f3cc71d2e090f05a881ca\"}}")
COMPOSER_DECLARATIONS = json.loads("{\"Android.bp\":{\"bytes\":13561,\"sha256\":\"5f124886cad4dbf79ddac0c71bb2a8743f235ec218c8821d0b9befaf08f1fd80\"},\"android/hardware/composer/aidl-lock.json\":{\"bytes\":863,\"sha256\":\"7b128d4738e1b645571c6e03b8d29de5c2e8d8a4d53b56b9e53832c9652d5077\"},\"android/hardware/composer/service-contract.json\":{\"bytes\":2636,\"sha256\":\"18470ab9ce8ee4262871275a3eaf3fe98085d8d820696a69430cccd748e799ac\"}}")
COMPOSER_PROJECTED_BLUEPRINTS = json.loads("{\"frameworks/base/packages/SystemUI/tests/Android.bp\":{\"bytes\":3392,\"sha256\":\"f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da\",\"projected_sha256\":\"42118873220b0cc4d07e21a961052ddd5d81ab67be8df5d7c9dba9bd966aaeb5\"},\"hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp\":{\"bytes\":1869,\"sha256\":\"9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6\",\"projected_sha256\":\"d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93\"}}")


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
            'ACTUAL_BUILDER474_COMPILE01_REQUIRED')
    result, pin = json_pin(BUILD_RESULT, BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    staged, _ = json_pin(HERE / 'actual-builder474-result.json', BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    require(result == staged and result['state'] == 'PASS' and
            result['focused_tests_passed'] == 35 and result['updater_focused_tests_passed'] == 26 and
            result['source_resume_tests_passed'] == 9 and result['expected_test_names'] == EXPECTED_TESTS and
            result['expected_source_resume_test_names'] == EXPECTED_SOURCE_TESTS and
            result['actual_registered_test_count'] == 216 and result['source_actual_registered_test_count'] == 20 and
            result['original_projection_tests_passed'] == 7 and result['typed_ingress_lock_tests_passed'] == 2 and
            result['provider_closure_tests_passed'] == 6 and result['hal_provider_tests_passed'] == 3 and
            result['composer_entry_tests_passed'] == 5 and
            result['composer_audiocontrol_projection_tests_passed'] == 3,
            'actual builder474 compile01 and exact 35-control qualification differs')
    commands = result['commands']
    require(len(commands) == len(EXPECTED_COMPILE_LABELS) and
            {row['label'] for row in commands} == set(EXPECTED_COMPILE_LABELS) and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in commands),
            'actual compiler command closure is incomplete')
    for indices, names, count, elf_key, gates_key in [
        (EXPECTED_TEST_INDICES, EXPECTED_TESTS, 216, 'test_elf', 'focused_result_gates'),
        (list(range(100, 109)), EXPECTED_SOURCE_TESTS, 20, 'source_test_elf', 'source_resume_result_gates')]:
        require(len(result[gates_key]) == len(names), 'actual focused result gate count differs')
        for position, name in enumerate(names):
            index = indices[position]
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
            result['copied_manifest']['bytes'] == 99750 and delta == EXPECTED_SOURCE_DELTA and
            delta['actual_source_file_count'] == 501 and delta['unchanged_existing'] == 499 and
            delta['changed_existing'] == ['tools/droidloom-update/src/android.rs'] and
            delta['added'] == ['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'] and
            delta['builder_revision_name'] == '474-composer-audiocontrol-example-projection' and
            result['actual_device_staging_reuse_qualified'] is False and
            'HOME' not in result['build_environment'],
            'builder source is not the exact reviewed 501-file Audiocontrol example projection successor')
    require(result['actual_parent472_compile_authority']['bytes'] == 185025 and
            result['actual_parent472_compile_authority']['sha256'] == '4c2f97bee3d6dbcc742f736c46fa18e9dc869830fe82211fb83c0afed6dfdbf4' and
            result['parent472_build_scope_authority']['bytes'] == 6535 and
            result['parent472_build_scope_authority']['sha256'] == 'f43cd778b75e484d53899eab543680e6b32ae5e54d6eca373b34223dcfcc8af9' and
            result['composer_entry_proof_authority']['bytes'] == 11586 and
            result['composer_entry_proof_authority']['sha256'] == '3bc022c9924dc13f7e2ad8d6ed85a079af1dec61733433b88c2c76d0df0c60da' and
            result['composer_build_scope_authority']['bytes'] == 7076 and
            result['composer_build_scope_authority']['sha256'] == '65f48507f685808728c1cd5a7f4a44e09e9b57f0588befbb97ba77a94a25da3d' and
            result['composer_audiocontrol_projection_authority']['bytes'] == 12564 and
            result['composer_audiocontrol_projection_authority']['sha256'] == '2a3d0c6c6727e83aa8c325c63488e932774d8c9fa41e32065b5a5952b8f5a1ab' and
            result['audiocontrol_example_original_fixture_authority']['bytes'] == 1869 and
            result['audiocontrol_example_original_fixture_authority']['sha256'] == '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6' and
            result['actual_prior_wayland03_check_authority']['bytes'] == 81805 and
            result['actual_prior_wayland03_check_authority']['sha256'] == '57546b6c6c2d4e05aea6099097944cdbe6746bbcc0124768a314414ec5663abd' and
            result['unchanged_225_project_lock_authority']['bytes'] == 96957 and
            result['unchanged_225_project_lock_authority']['sha256'] == EXTENDED_LOCK_SHA and
            result['source_lock_writer'] == 'UNKNOWN',
            'builder474 actual parent, Composer sources, projection and unchanged current lock are incomplete')
    require(result['actual_toolchain']['rustup_proxy_executed'] is False and
            result['actual_toolchain']['rustup_proxy_changed_bytes_approved_for_execution'] is False and
            result['runtime_authorization_enabled'] is False and
            result['Composer_Android_Binder_ABI_compiled'] is False and
            result['Composer_service_or_AIDL_tests_executed'] is False and
            result['Main_identity_observed'] is False and result['Main_actions'] == 0 and
            result['framework_Java_and_Android_JNI_compiled'] is False and
            result['transitive_framework_closure_qualified'] is False,
            'builder receipt scope was widened')
    builder, _ = held_file(BUILDER, 64*1024*1024)
    require(builder == result['builder_elf'] and builder['sha256'] == BUILDER_SHA and
            builder['bytes'] == BUILDER_BYTES and builder['identity'][2] & 0o111,
            'actual builder ELF identity/content changed')
    source_map, source_pin = json_pin(BUILD_PARENT / 'attempt01/copied-builder-source-manifest.json',
                                    SOURCE_MANIFEST_SHA, 99750)
    staged_map, _ = json_pin(HERE / 'expected-builder474-manifest.json', SOURCE_MANIFEST_SHA, 99750)
    require(source_map == staged_map and len(source_map) == 501 and
            source_map[GO_PATCH]['sha256'] == GO_PATCH_SHA and
            source_map['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'] == {
                'bytes': 1869, 'kind': 'file', 'mode': 420,
                'sha256': '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6'} and
            source_map['android/manifest/m2-role-ingress-source-lock.json']['sha256'] == PREVIOUS_TYPED_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider-source-lock.json']['sha256'] == PREVIOUS_PROVIDER_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-hal-provider-source-lock.json']['sha256'] == EXTENDED_LOCK_SHA,
            'full builder source manifest differs')
    for fixed in [COMPOSER_INPUTS, COMPOSER_DECLARATIONS]:
        for relative, wanted in fixed.items():
            require(source_map[relative]['kind'] == 'file' and
                    source_map[relative]['bytes'] == wanted['bytes'] and
                    source_map[relative]['sha256'] == wanted['sha256'],
                    'actual Composer production source or declaration differs: ' + relative)
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
        (PREVIOUS_ROOT / 'attempt-01/terminal.json', 'prior-framework-inner-terminal.json', PRIOR_INNER_SHA, 2898),
        (PREVIOUS_ROOT / 'build-fences-01/terminal.json', 'prior-framework-outer-terminal.json', PRIOR_OUTER_SHA, 24714),
        (RESOURCE_REJECTED_ROOT / 'build-fences-01/terminal.json', 'prior-normal09-outer-terminal.json',
         '873a8c03dc51a62e69aaeab28e7929ef2b8b48019d9d1ca949e23ce07d3f3d1a', 24759),
        (RESOURCE_REJECTED_ROOT / 'resource-admission.json', 'prior-normal09-resource-admission.json',
         '62bc5109a8ed50722560b6374caa1b0581d53abaa0d300e510adbeb85acfb2cd', 2749),
    ]
    documents = []
    pins = []
    for remote, staged_name, digest_value, size in authorities:
        document, row = json_pin(remote, digest_value, size)
        staged, staged_row = json_pin(HERE / staged_name, digest_value, size)
        require(document == staged, 'original failed authority differs from its frozen actual bytes')
        documents.append(document)
        pins.extend([row, staged_row])
    inner, outer, rejected_outer, rejected_resource = documents
    require(inner['state'] == 'FAILED' and inner['builder_returncode'] == 1 and
            inner['error'] == "RuntimeError('normal builder returned 1')" and
            inner['cleanup'] == json.loads("{\"complete\":true,\"children\":[{\"pid\":1067696,\"wait_status\":65280,\"reaped\":true}],\"errors\":[]}") and
            inner['normal_command_completion_gate'] is None and
            inner['source_projection_journal_present'] is False and
            inner['input_after_qualified'] is True and inner['input_after_error'] is None and
            inner['owned_resource_gate']['pass'] is True and
            inner['stdout_sha256'] == 'b1432c4cbb985f2909b4325a235e7f4edd03afe91b5dc109cd90d74829732834' and
            inner['stderr_sha256'] == 'cbbc3ea39583d9c3bdb10b7934bd4c568be1a269e336f9b3ce0f91cf25517c14' and
            inner['memory_swap_max'] == inner['memory_swap_current'] == inner['memory_swap_peak'] == '0' and
            inner['owned_resource_gate']['zero_swap_limit_and_current_observed_after'] is True,
            'prior normal strict failure or complete owned-child retirement differs')
    require(outer['state'] == 'FAILED' and outer['inner_returncode'] == 1 and
            outer['main_fence_assessment']['main_fence_pass'] is True and
            outer['main_fence_assessment']['identity_or_limit_changes'] == [] and
            outer['main_fence_assessment']['main_oom_delta_zero'] is True,
            'prior fixed Main fence result differs')
    controls = outer['capture_lifecycle_controls']
    require(outer['before_observed'] is True and outer['after_observed'] is True and
            controls['state'] == 'PASS' and controls['passed'] == 4 and
            len(controls['rows']) == 4 and all(row['passed'] is True and
                row['owned_children_empty'] is True and row['Main_read_performed'] is False
                for row in controls['rows']),
            'prior four actual owned lifecycle controls are incomplete')
    captures = outer['capture_lifecycle_receipts']
    phases = ['control-root-timeout', 'control-root-escaped', 'control-root-pidfd',
              'control-outer-pidfd', 'before', 'after']
    require([row['phase'] for row in captures] == phases,
            'prior six actual capture retirement records differ')
    for row in captures:
        command = row['command']
        require(row['outer_subreaper']['final_children_empty'] is True and
                row['within_absolute_outer_deadline'] is True and not row['secondary_errors'] and
                command['child_reaped'] is True and command['owned_tree_cleanup_complete'] is True and
                command['pidfd_closed'] is True and command['all_acquired_fds_closed'] is True and
                command['retirement_within_deadline'] is True and
                not command['remaining_owned_children'] and not command['secondary_errors'],
                'prior owned capture was not completely retired')
        if row['phase'] == 'control-outer-pidfd':
            require(row['qualified_success'] is False and command['returncode'] == -9 and
                    row['first_error']['errno'] == 24 and command['first_error']['errno'] == 24,
                    'prior expected pidfd allocation failure was relabeled')
        else:
            require(row['qualified_success'] is True and command['qualified_success'] is True and
                    command['returncode'] == 0 and row['first_error'] is None and
                    command['first_error'] is None, 'prior capture failed unexpectedly')
    # Normal09 rejected the fresh RAM gate before its owned builder was started.
    # Preserve that failure independently of Normal08's genuine Soong failure.
    # These historical bytes never satisfy the new run's fresh resource admission.
    require(rejected_outer['state'] == 'FAILED' and
            rejected_outer['error'] == "RuntimeError('less than 15 GiB MemAvailable for independent zero-swap profile; no automatic retry')" and
            rejected_outer['inner_build_called'] is True and rejected_outer['inner_returncode'] is None and
            rejected_outer['before_observed'] is True and rejected_outer['after_observed'] is True and
            rejected_outer['main_fence_assessment']['main_fence_pass'] is True and
            rejected_outer['main_fence_assessment']['identity_or_limit_changes'] == [] and
            rejected_outer['main_fence_assessment']['main_oom_delta_zero'] is True and
            all(value == 0 for value in rejected_outer['main_fence_assessment']['main_memory_event_deltas'].values()) and
            rejected_outer['main_fence_assessment']['main_current_resource_deltas']['memory.swap.current'] == 0 and
            rejected_outer['main_fence_assessment']['unobserved_transient_effects_excluded'] is False and
            rejected_outer['main_fence_assessment']['causal_attribution_of_counter_changes'] is False,
            'prior Normal09 resource rejection or limited Main fence result differs')
    resource_controls = rejected_outer['capture_lifecycle_controls']
    require(resource_controls['state'] == 'PASS' and resource_controls['passed'] == 4 and
            len(resource_controls['rows']) == 4 and all(row['passed'] is True and
                row['owned_children_empty'] is True and row['Main_read_performed'] is False
                for row in resource_controls['rows']) and
            [row['phase'] for row in rejected_outer['capture_lifecycle_receipts']] == phases,
            'prior Normal09 four real controls or six capture records differ')
    for row in rejected_outer['capture_lifecycle_receipts']:
        command = row['command']
        require(row['outer_subreaper']['final_children_empty'] is True and
                row['outer_subreaper']['restored'] is True and
                row['within_absolute_outer_deadline'] is True and not row['secondary_errors'] and
                command['child_reaped'] is True and command['owned_tree_cleanup_complete'] is True and
                command['pidfd_closed'] is True and command['all_acquired_fds_closed'] is True and
                command['retirement_within_deadline'] is True and
                not command['remaining_owned_children'] and not command['secondary_errors'],
                'prior Normal09 capture was not completely retired')
        if row['phase'] == 'control-outer-pidfd':
            require(row['qualified_success'] is False and command['returncode'] == -9 and
                    row['first_error']['errno'] == 24 and command['first_error']['errno'] == 24,
                    'prior Normal09 expected pidfd failure was relabeled')
        else:
            require(row['qualified_success'] is True and command['qualified_success'] is True and
                    command['returncode'] == 0 and row['first_error'] is None and
                    command['first_error'] is None, 'prior Normal09 capture failed unexpectedly')
    require(rejected_resource['schema'] == 1 and
            rejected_resource['state'] == 'OBSERVED_BEFORE_RESOURCE_ADMISSION' and
            rejected_resource['profile'] == {
                'memory_max_bytes': 10737418240, 'memory_swap_max_bytes': 0,
                'minimum_fresh_MemAvailable_bytes': 16106127360,
                'admission_difference_bytes': 5368709120, 'global_swap_is_owned_budget': False} and
            rejected_resource['owned_observed'] == {
                'memory.max': '10737418240', 'cpu.max': '200000 100000',
                'memory.swap.max': '0', 'memory.swap.current': '0'} and
            rejected_resource['decision_performed'] is False and
            rejected_resource['historical_sample_used_for_admission'] is False,
            'prior Normal09 resource receipt shape or original zero-swap profile differs')
    resource_raw = rejected_resource['meminfo']['raw_ascii'].encode('ascii', 'strict')
    require(len(resource_raw) == rejected_resource['meminfo']['bytes'] == 1672 and
            hashlib.sha256(resource_raw).hexdigest() == rejected_resource['meminfo']['sha256'] ==
                'f8edcc866dfa4f605af8a5e50f3a42172b716bf819030f11ed6b533323219b38',
            'prior Normal09 exact bounded meminfo differs')
    resource_memory = parse_admission_meminfo(resource_raw)
    require(resource_memory['MemAvailable'] == 14854873088 and
            resource_memory['MemAvailable'] < MIN_AVAILABLE and
            MIN_AVAILABLE - resource_memory['MemAvailable'] == 1251254272,
            'prior Normal09 failed RAM threshold was changed')
    published, row = json_pin(HERE / 'actual-current225-source-manifest.json',
                             PUBLISHED_MANIFEST_SHA, PUBLISHED_MANIFEST_BYTES)
    pins.append(row)
    require(published['schema_version'] == 1 and published['source_lock_sha256'] == EXTENDED_LOCK_SHA and
            published['plan']['schema_version'] == 1 and published['plan']['unrestricted_repo_sync'] is False and
            published['plan']['superproject_commit'] == '28f0bbddc24d56c8ec5a8df5342ac7a292184039' and
            len(published['plan']['projects']) == 225 and len(published['plan']['links']) == 8,
            'actual published source manifest differs')
    lock, lock_pin = json_pin(HERE / 'actual-hal-provider-source-lock.json', EXTENDED_LOCK_SHA, 96957)
    require(published == expected_published_manifest(lock),
            'current exact published plan differs from the adopted lock')
    pins.append(lock_pin)
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
        'previous_locked_projects': 225, 'new_locked_projects': 225, 'root_links': 8,
        'all_projects_reuse_qualified_by_wrapper': False,
        'all_project_qualification_deferred_to_normal_builder_under_existing_work_source_locks': True,
        'normal_full_current_lock_verification_and_prepare': True,
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
        require(portable == context['builder_map'], 'actual 501-file builder source changed')
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
    context['published_manifest'], context['prior_failure_authority_pins'] = prior_failure_contract()
    context['initial_observations'] = observe_inputs(context, True)
    return context


def plan():
    return {'schema': 1, 'state': 'PLAN_NORMAL_STRICT_COMPOSER_SERVICE_AND_AIDL_TEST_BUILD',
        'root': str(ROOT), 'work': str(WORK), 'aosp_source': str(PUBLISHED_SOURCE), 'out': str(OUT),
        'builder_result_sha256': BUILD_RESULT_SHA, 'work_preparation_sha256': PREPARATION_SHA,
        'builder_sha256': BUILDER_SHA, 'builder_source_manifest_sha256': SOURCE_MANIFEST_SHA,
        'builder_source_files': 501, 'actual_host_compile_commands': 74, 'actual_exact_controls': 35,
        'argv': [str(BUILDER), '--source', str(BUILD_SOURCE), '--jobs', '1',
                 'composer-retirement-build', '--work', str(WORK), '--out', str(OUT)],
        'targets': TARGETS, 'dependency_mode': 'Strict', 'ALLOW_MISSING_DEPENDENCIES': False,
        'source_materialization': 'fresh full verification and normal prepare of the published exact current 225-project lock and 8 root links',
        'published_source_manifest_sha256': PUBLISHED_MANIFEST_SHA,
        'reuse_qualified_by_plan': False, 'workspace_prior_typed_inner_failure_sha256': PRIOR_INNER_SHA,
        'workspace_prior_typed_outer_failure_sha256': PRIOR_OUTER_SHA, 'prior_reaped_children': 1,
        'first_attempt_timeout_and_296_reaped_history_retained': True,
        'normal_lock_paths': [str(WORK / 'package-build.lock'), str(WORK / 'aosp-source-update.lock')],
        'normal_package_and_source_locks': True, 'normal_projection_journal_and_recovery': True,
        'old_shared_AOSP_source_modified': False, 'source_manifest_fabrication': False, 'source_lock_writer': 'UNKNOWN',
        'memory_max_bytes': MEMORY_MAX, 'memory_swap_max_bytes': SWAP_MAX,
        'fresh_MemAvailable_min_bytes': MIN_AVAILABLE, 'fresh_SwapFree_min_bytes': None,
        'global_swap_free_recorded_only': True, 'owned_swap_current_required_bytes': 0,
        'resource_admission_receipt': str(ROOT / 'resource-admission.json'),
        'admission_difference_bytes': MIN_AVAILABLE - MEMORY_MAX,
        'prior_normal_peak_bytes': 8141615104, 'prior_normal_swap_peak_bytes': 0,
        'actual_builder474_static_compile_peak_bytes': 1073741824, 'actual_builder474_static_compile_memory_max_events': 205,
        'static_compile_pressure_not_normal_Soong_qualification': True,
        'cpu_quota_percent': 200, 'jobs': 1, 'builder_wait_seconds': 6100,
        'automatic_retry': False, 'Main_actions': 0, 'Android_actions': 0,
        'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
        'runtime_authorization_enabled': False, 'Mesa_tools_not_fabricated_or_prequalified': True,
        'strict_dependency_failure_not_suppressed': True,
        'normal_build_success_not_ELF_AIDL_or_native_link_qualification': True,
        'fixed_ACK_production_inputs': COMPOSER_INPUTS, 'fixed_checkout_declarations': COMPOSER_DECLARATIONS,
        'exact_private_Blueprint_projection_scope': COMPOSER_PROJECTED_BLUEPRINTS,
        'tests_executed': False, 'Android_Binder_ABI_qualified': False,
        'Wayland_GPU_runtime_qualified': False, 'service_activation_performed': False}

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
    require(document == expected and len(document['plan']['projects']) == 225 and
            len(document['plan']['links']) == 8,
            'normal published manifest is not the exact complete new locked plan')


def qualify_composer_records(attempt, inputs, command, manifest_sha, source_map):
    require(set(attempt) == {
        'schema', 'state', 'targets', 'dependency_mode', 'source_lock', 'source_lock_sha256',
        'locked_projects', 'fixed_production_inputs', 'fixed_checkout_declarations',
        'source_projection_journal', 'command_completed', 'tests_executed',
        'Android_Binder_ABI_qualified', 'Wayland_GPU_runtime_qualified',
        'installation_performed', 'service_activation_performed'} and
        set(inputs) == {
            'schema', 'targets', 'dependency_mode', 'ALLOW_MISSING_DEPENDENCIES',
            'source_lock_sha256', 'materialized_manifest_sha256', 'fixed_production_inputs',
            'nine_production_vendor_mirrors_exact', 'fixed_checkout_declarations',
            'effective_vendor_Android_bp_sha256', 'source_projection', 'tests_executed',
            'Android_Binder_ABI_qualified', 'Wayland_GPU_runtime_qualified',
            'installation_performed', 'service_activation_performed'} and
        set(command) == {
            'schema', 'state', 'targets', 'dependency_mode', 'source_projection_restored',
            'tests_executed', 'actual_ELF_AIDL_and_native_link_inputs_qualified',
            'Android_Binder_ABI_qualified', 'Wayland_GPU_runtime_qualified',
            'installation_performed', 'service_activation_performed'},
        'COMPOSER_RECORD_FIELDS')
    for document in [attempt, inputs, command]:
        require(type(document['schema']) is int and document['schema'] == 1 and
                document['targets'] == TARGETS and document['dependency_mode'] == 'Strict' and
                all(document[key] is False for key in [
                    'tests_executed', 'Android_Binder_ABI_qualified',
                    'Wayland_GPU_runtime_qualified', 'installation_performed',
                    'service_activation_performed']), 'COMPOSER_RECORD_SCOPE')
    require(attempt['state'] == 'CLAIMED_BEFORE_FRESH_SOURCE_VERIFICATION_OR_PROJECTION' and
            attempt['source_lock'] == str(BUILD_SOURCE / 'android/manifest/m2-role-ingress-hal-provider-source-lock.json') and
            attempt['source_lock_sha256'] == EXTENDED_LOCK_SHA and
            type(attempt['locked_projects']) is int and attempt['locked_projects'] == 225 and
            attempt['source_projection_journal'] == str(WORK / 'source-projection.json') and
            attempt['command_completed'] is False, 'COMPOSER_ATTEMPT_BINDING')
    for document in [attempt, inputs]:
        require(document['fixed_production_inputs'] == COMPOSER_INPUTS and
                document['fixed_checkout_declarations'] == COMPOSER_DECLARATIONS,
                'COMPOSER_FIXED_INPUTS')
    require(inputs['ALLOW_MISSING_DEPENDENCIES'] is False and
            inputs['source_lock_sha256'] == EXTENDED_LOCK_SHA and
            inputs['materialized_manifest_sha256'] == manifest_sha and
            inputs['nine_production_vendor_mirrors_exact'] is True,
            'COMPOSER_INPUT_BINDING')
    projection = inputs['source_projection']
    require(isinstance(projection, dict) and set(projection) == {'files', 'patches'} and
            isinstance(projection['files'], dict) and isinstance(projection['patches'], dict),
            'COMPOSER_PROJECTION_SHAPE')
    for kind in ['files', 'patches']:
        for relative, value in projection[kind].items():
            require(isinstance(relative, str) and bool(relative) and
                    not pathlib.PurePosixPath(relative).is_absolute() and
                    '..' not in pathlib.PurePosixPath(relative).parts and
                    str(pathlib.PurePosixPath(relative)) == relative and
                    (value is None and kind == 'files' or
                     isinstance(value, str) and len(value) == 64 and
                     all(c in '0123456789abcdef' for c in value)),
                    'COMPOSER_PROJECTION_SHAPE')
    require(all(projection['files'].get(relative) == row['projected_sha256']
                for relative, row in COMPOSER_PROJECTED_BLUEPRINTS.items()),
            'COMPOSER_EXACT_PROJECTION')
    effective = inputs['effective_vendor_Android_bp_sha256']
    # The exact Composer route copies this root Blueprint unchanged. Only the
    # disjoint NativeBridge-only route projects it after the vendor mirror.
    require(effective == COMPOSER_DECLARATIONS['Android.bp']['sha256'] and
            'vendor/droidloom/Android.bp' not in projection['files'],
            'COMPOSER_VENDOR_BLUEPRINT')
    for relative, value in projection['patches'].items():
        require(relative in source_map and source_map[relative]['kind'] == 'file' and
                source_map[relative]['sha256'] == value, 'COMPOSER_PROJECTED_PATCH')
    require(projection['patches'].get(GO_PATCH) == GO_PATCH_SHA and
            projection['patches'].get('android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch') ==
                source_map['android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch']['sha256'] and
            'android/apex-compat/0007-transitive-default-missing-dependencies.patch' not in projection['patches'],
            'COMPOSER_STRICT_PATCH_SCOPE')
    require(command['state'] == 'NORMAL_BUILD_COMMAND_SUCCEEDED' and
            command['source_projection_restored'] is True and
            command['actual_ELF_AIDL_and_native_link_inputs_qualified'] is False,
            'COMPOSER_COMMAND')


def completion_gate(context):
    records = {}
    for name in ['droidloom-composer-retirement-attempt.json',
                 'droidloom-composer-retirement-inputs.json',
                 'droidloom-composer-retirement-command.json']:
        row, raw = held_file(OUT / name, 8*1024*1024, True)
        records[name] = (json.loads(raw), row)
    attempt = records['droidloom-composer-retirement-attempt.json'][0]
    inputs = records['droidloom-composer-retirement-inputs.json'][0]
    command = records['droidloom-composer-retirement-command.json'][0]
    require(not (WORK / 'source-projection.json').exists() and
            not (WORK / 'source-projection.json').is_symlink(),
            'normal source projection did not finish restoration')
    lock, _ = json_pin(BUILD_SOURCE / 'android/manifest/m2-role-ingress-hal-provider-source-lock.json',
                       EXTENDED_LOCK_SHA, 96957)
    manifest_pin, manifest_raw = held_file(PUBLISHED_SOURCE / '.droidloom-source-manifest.json', 1024*1024, True)
    qualify_completed_manifest(json.loads(manifest_raw), lock)
    qualify_composer_records(attempt, inputs, command, manifest_pin['sha256'], context['builder_map'])
    native_bp, _ = held_file(PUBLISHED_SOURCE / 'prebuilts/misc/common/robolectric-native-prebuilt/Android.bp', 65536)
    require(native_bp['bytes'] == NATIVE_PREBUILT_BP_BYTES and native_bp['sha256'] == NATIVE_PREBUILT_BP_SHA,
            'locked native prebuilt provider body differs after the normal build')
    restored = {}
    for relative, expected in COMPOSER_PROJECTED_BLUEPRINTS.items():
        row, _ = held_file(PUBLISHED_SOURCE / relative, 65536)
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'Composer exact Blueprint original was not restored: ' + relative)
        restored[relative] = row
    vendor_bp, _ = held_file(PUBLISHED_SOURCE / 'vendor/droidloom/Android.bp', 65536)
    require(vendor_bp['bytes'] == COMPOSER_DECLARATIONS['Android.bp']['bytes'] and
            vendor_bp['sha256'] == COMPOSER_DECLARATIONS['Android.bp']['sha256'],
            'Composer vendor Blueprint differs from the exact copied source')
    mirrors = {}
    for relative, expected in COMPOSER_INPUTS.items():
        row, _ = held_file(PUBLISHED_SOURCE / 'vendor/droidloom' / relative, 1024*1024)
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'Composer fixed production mirror changed after build: ' + relative)
        mirrors[relative] = row
    return {'state': 'COMPOSER_NORMAL_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING',
        'records': {name: row for name, (_, row) in records.items()},
        'actual_published_manifest': manifest_pin, 'published_projects': 225, 'published_root_links': 8,
        'actual_locked_native_prebuilt_provider': native_bp,
        'two_exact_Blueprint_originals_restored': restored,
        'exact_vendor_Blueprint_after_build': vendor_bp,
        'nine_production_vendor_mirrors': mirrors,
        'checkout_declarations_verified_by_actual_builder_and_complete_source_map': COMPOSER_DECLARATIONS,
        'targets': TARGETS, 'dependency_mode': 'Strict', 'source_projection_restored': True,
        'actual_ELF_AIDL_and_native_link_inputs_qualified': False,
        'Android_Binder_ABI_qualified': False, 'Wayland_GPU_runtime_qualified': False,
        'tests_executed': False, 'runtime_authorization_enabled': False,
        'installation_performed': False, 'service_activation_performed': False}


def verify_inputs_after(context):
    observations = observe_inputs(context, False)
    for path, wanted in [(PREPARATION, context['prepared_pin']), (BUILD_RESULT, context['compiled_pin']),
                         (HERE / 'frozen-work-inventory.py', context['inventory_pin']),
                         (BUILD_PARENT / 'attempt01/copied-builder-source-manifest.json', context['builder_map_pin'])]:
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
    claim = {"schema": 1, "state": "STARTING_COMPOSER_NORMAL_STRICT_SERVICE_AND_AIDL_TEST_BUILD",
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
        terminal = {"schema": 1, "state": "COMPOSER_COMMAND_COMPLETED_QUALIFICATION_PENDING" if failure is None else "FAILED",
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
                    "actual_ELF_AIDL_and_native_link_inputs_qualified": False,
                    "Android_Binder_ABI_qualified": False, "Wayland_GPU_runtime_qualified": False,
                    "tests_executed": False,
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
