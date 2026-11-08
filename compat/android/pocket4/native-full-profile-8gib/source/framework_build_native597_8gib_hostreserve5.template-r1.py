#!/usr/bin/env python3
"""Build the ordinary engine and whole ART pair in an explicitly stopped cohort; never deploy."""
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
    require(MEMORY_MAX == 8 * 1024**3 and SWAP_MAX == 0 and
            MIN_AVAILABLE - MEMORY_MAX == 5 * 1024**3,
            "independent eight-GiB zero-swap profile or five-GiB admission difference changed")
    require(owned["memory.max"] == str(MEMORY_MAX) and owned["cpu.max"] == "200000 100000",
            "owned RAM or CPU limit differs before admission")
    require(owned["memory.swap.max"] == "0", "owned swap limit is not zero")
    require(owned["memory.swap.current"] == "0", "existing owned swap is not zero")
    require(memory["MemAvailable"] >= MIN_AVAILABLE,
            "less than 13 GiB MemAvailable for independent zero-swap profile; no automatic retry")
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
        "profile": {"resource_profile_id": RESOURCE_PROFILE_ID, "memory_max_bytes": MEMORY_MAX, "memory_swap_max_bytes": SWAP_MAX,
                    "minimum_fresh_MemAvailable_bytes": MIN_AVAILABLE,
                    "admission_difference_bytes": MIN_AVAILABLE - MEMORY_MAX,
                    "global_swap_is_owned_budget": False},
        "meminfo": {"path": "/proc/meminfo", "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(), "raw_ascii": raw.decode("ascii", "strict")},
        "owned_cgroup": str(cgroup), "owned_observed": owned,
        "decision_performed": False, "historical_sample_used_for_admission": False,
        "Main_actions": 0, "Android_actions": 0, "production_ready": False}
    path = ROOT / "resource-admission-native597-8gib-hostreserve5-20261108-r1.json"
    save(path, receipt)
    pin, _ = held_file(path, 65536)
    print(json.dumps({"state": "FRESH_RESOURCE_ADMISSION_OBSERVED", "receipt": pin}), flush=True)
    # Persist the exact bounded read before parsing or comparing any resource threshold.
    memory = parse_admission_meminfo(raw)
    memory_admission(memory, owned)
    # The outer launcher measures its deadline before input verification. Recheck
    # the same actual job after that work, immediately before builder setup.
    launch_root = ROOT / "attempts/full-build-native597-8gib-hostreserve5-20261108-r1"
    launch_pin, launch_raw = held_file(launch_root / "outer-runtime-admission.json", 65536, True)
    launch = json.loads(launch_raw)
    unit = cgroup.name
    require(unit.startswith("hepta-runtime-job-") and unit.endswith(".service"),
            "exact outer service required for final runtime admission")
    job = unit[len("hepta-runtime-job-"):-len(".service")]
    job_root = P("/home/alex/.local/state/hepta-runtime-mac-worker/jobs") / job
    request_pin, request_raw = held_file(job_root / "request.json", 65536, True)
    runner_pin, _ = held_file(job_root / "runner.py", 65536)
    request = json.loads(request_raw)
    short_request = {key: request_pin[key] for key in ("path", "bytes", "sha256")}
    short_runner = {key: runner_pin[key] for key in ("path", "bytes", "sha256")}
    require(launch["schema"] == "pocket4-native597-outer-runtime-admission-v1"
            and launch["state"] == "ACTUAL_OUTER_RUNTIME_VERIFIED_BUILD_PENDING"
            and launch["job_id"] == job
            and launch["outer_cgroup"] == "0::/" + str(cgroup.relative_to("/sys/fs/cgroup"))
            and launch["actual_request"] == short_request
            and launch["actual_runtime_runner"] == short_runner
            and request["job_id"] == job and request["unit"] + ".service" == unit
            and request["execution_mode"] == "operator" and request["timeout_seconds"] == 23000
            and runner_pin["bytes"] == 40463
            and runner_pin["sha256"] == "65564ce756f3a341def2cf34b2c0d54ef3e75960923c6002c4c56db13564ebf1",
            "same reviewed actual outer request and runner required after preflight")
    observed = subprocess.run(["/usr/bin/systemctl", "--user", "show", unit,
                               "-p", "ActiveState", "-p", "RuntimeMaxUSec",
                               "-p", "ExecMainStartTimestampMonotonic"],
                              check=True, capture_output=True, text=True, timeout=15)
    properties = dict(line.split("=", 1) for line in observed.stdout.splitlines() if "=" in line)
    elapsed = time.monotonic() - int(properties["ExecMainStartTimestampMonotonic"]) / 1000000
    margin = 23000 - elapsed - 21600
    runtime_receipt = {
        "schema": "pocket4-native597-post-preflight-runtime-observation-v1",
        "state": "OBSERVED_AFTER_INPUT_VERIFICATION_BEFORE_BUILDER_SETUP",
        "job_id": job, "owned_cgroup": str(cgroup), "launcher_admission": launch_pin,
        "actual_request": short_request, "actual_runtime_runner": short_runner,
        "actual_unit_properties": properties, "outer_elapsed_seconds": elapsed,
        "outer_timeout_seconds": 23000, "normal_build_timeout_seconds": 21600,
        "remaining_margin_after_input_verification_seconds": margin,
        "required_remaining_margin_seconds": 1200, "decision_performed": False,
        "compiler_invocations_at_observation": 0, "Main_actions": 0, "Android_actions": 0}
    runtime_path = ROOT / "runtime-admission-native597-8gib-hostreserve5-20261108-r1.json"
    save(runtime_path, runtime_receipt)
    runtime_pin, _ = held_file(runtime_path, 65536)
    print(json.dumps({"state": "POST_PREFLIGHT_RUNTIME_OBSERVED", "receipt": runtime_pin}), flush=True)
    require(properties["ActiveState"] == "active" and properties["RuntimeMaxUSec"] == "infinity"
            and properties["ExecMainStartTimestampMonotonic"]
                == launch["actual_unit_properties"]["ExecMainStartTimestampMonotonic"]
            and 0 <= launch["outer_elapsed_seconds"] <= elapsed
            and margin > 1200,
            "actual outer job must retain 1200 seconds beyond the full build after input verification")
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
ROOT = P('/home/alex/work/pocket4-android-final/native')
HERE = ROOT / 'control-source'
WORK = OWNER / 'typed-ingress-framework-work-01-20261105'
OUT = ROOT/'android-out-native597-8gib-hostreserve5-20261108-r1'
ATTEMPT = ROOT/'attempt-native597-8gib-hostreserve5-20261108-r1'
BUILD_PARENT = P('/home/alex/work/pocket4-builder473-recovery-20261107-r1')
BUILD_SOURCE = BUILD_PARENT / 'builder-source'
BUILDER = BUILD_PARENT / 'attempt01/cargo-target/debug/droidloom-update'
BUILDER_SHA = "a6ae54a57cdd8e9f117450f718a5b0b70755cc57f692c10e43096821697698ae"
BUILDER_BYTES = 34773160
BUILD_RESULT = BUILD_PARENT / 'attempt01/result.json'
BUILD_RESULT_SHA = "855cfaa9919eddf11e70c82eac1bd28676ce65e85ebfce90450ba886d7b48160"
BUILD_RESULT_BYTES = 174531
SOURCE_MANIFEST_SHA = "a3426e40f9446b85931c82e8ba08335e72cd9bd0ac4a3f70aa01d54200d1ae13"
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
RESOURCE_PROFILE_ID = 'native597-8gib-hostreserve5-20261108-r1'
HISTORICAL_MIN_AVAILABLE = 15 * 1024**3
MEMORY_MAX = 8 * 1024**3
SWAP_MAX = 0
MIN_AVAILABLE = 13 * 1024**3
TARGETS = ['framework-minus-apex', 'libandroid_runtime']
EXPECTED_TESTS = ["android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes","android::tests::restoration_preserves_original_and_removes_created_file","android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch","android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout","android::patch_tests::interrupted_projection_recovers_before_next_build","tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets","tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory","native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate","native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions","android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata","android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas","android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged","native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change","native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock","native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification","android::tests::typed_hal_provider_projection_restores_real_sources_and_keeps_consumers","android::tests::typed_hal_provider_late_source_drift_restores_earlier_projections","native_role_ingress::tests::hal_provider_extension_preserves_all_prior_projects_and_rejects_unlisted_changes","android::tests::typed_systemui_test_projection_keeps_metadata_parent_providers_and_other_paths","android::tests::typed_systemui_test_projection_rejects_wrong_source_before_journal_or_write","android::tests::typed_systemui_test_projection_recovers_complete_original_from_durable_journal","android::tests::typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources","android::tests::typed_audiocontrol_example_projection_rejects_source_drift_before_write","android::tests::typed_audiocontrol_example_projection_recovers_full_observed_original"]
EXPECTED_TEST_INDICES = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,200,201,202,203,204,205]


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
EXPECTED_COMPILE_LABELS = ["cargo-version","rustc-version","linked-libraries-0","linked-libraries-1","linked-libraries-2","linked-libraries-3","linked-libraries-4","linked-libraries-5","linked-libraries-6","linked-libraries-7","image-linked-libraries-0","image-linked-libraries-1","image-linked-libraries-2","image-linked-libraries-3","image-linked-libraries-4","image-linked-libraries-5","image-linked-libraries-6","image-linked-libraries-7","image-linked-libraries-8","image-linked-libraries-9","image-linked-libraries-10","image-linked-libraries-11","image-linked-libraries-12","image-linked-libraries-13","image-linked-libraries-14","workspace-no-deps","selected-build","selected-test","builder-compile","builder-help","source-resume-cli-help","builder-test-compile","builder-test-list","builder-test-help","projection-test-0","projection-test-1","projection-test-2","projection-test-3","projection-test-4","projection-test-5","projection-test-6","projection-test-7","projection-test-8","projection-test-9","projection-test-10","projection-test-11","projection-test-12","projection-test-13","projection-test-14","projection-test-15","projection-test-16","projection-test-17","projection-test-200","projection-test-201","projection-test-202","projection-test-203","projection-test-204","projection-test-205","source-resume-selected-test","source-resume-test-compile","source-resume-test-list","source-resume-test-help","projection-test-100","projection-test-101","projection-test-102","projection-test-103","projection-test-104","projection-test-105","projection-test-106","projection-test-107","projection-test-108"]
EXPECTED_SOURCE_DELTA = json.loads("{\"Cargo_lock_or_dependency_manifest_changed\":false,\"Go5_or_Blueprint_patch_changed\":false,\"Rust_source_files_changed\":1,\"SystemUI471_projection_and_fixture_unchanged\":true,\"actual_source_file_count\":501,\"added\":[\"android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp\"],\"builder_revision_name\":\"473-fixed-audiocontrol-example-projection\",\"changed_existing\":[\"tools/droidloom-update/src/android.rs\"],\"current_hal_source_lock_unchanged\":true,\"engine_source_files_changed\":0,\"fixed_Audiocontrol_example_BP_original_fixture_added\":true,\"framework_sources_executed_or_built\":false,\"new_exact_hal_provider_source_lock_added\":false,\"new_exact_provider_source_lock_added\":false,\"previous_source_locks_changed\":false,\"real_published_source_accessed\":false,\"real_source_staging_accessed\":false,\"runtime_authorization_enabled\":false,\"source_resume_library_changed\":false,\"typed_ingress_framework_patch_changed\":false,\"unchanged_existing\":499}")



RECOVERY_PARENT = BUILD_PARENT
RECOVERY_SOURCE = BUILD_SOURCE
RECOVERY_BUILDER = BUILDER
RECOVERY_BUILDER_SHA = BUILDER_SHA
RECOVERY_BUILDER_BYTES = BUILDER_BYTES
RECOVERY_RESULT = BUILD_RESULT
RECOVERY_RESULT_SHA = BUILD_RESULT_SHA
RECOVERY_RESULT_BYTES = BUILD_RESULT_BYTES
RECOVERY_MANIFEST_SHA = SOURCE_MANIFEST_SHA
BUILD_PARENT = P('/home/alex/work/pocket4-native-generation-pair-builder-20261107-r2')
CANDIDATE_ROOT = ROOT/'source-evidence/native-known-physical-lock-candidate-20261108-r2'
BUILD_SOURCE = CANDIDATE_ROOT/'builder-source-r4'
BUILDER = CANDIDATE_ROOT/'bin-r4/droidloom-update'
BUILDER_SHA = '75bf728444a101d39428a8c90a876e53d3325c1e45441c132b2552deb74660f0'
BUILDER_BYTES = 3805784
FINAL_BUILDER_RECOVERY_RESULT = CANDIDATE_ROOT/'postfreeze-build-r2/result.json'
FINAL_BUILDER_RECOVERY_SHA = '10e82d6dde1d2f69a28d097b6bc2fdb8e45648f65d127ef7cfb0e0a7dda0a044'
FINAL_BUILDER_RECOVERY_BYTES = 9770
FINAL_BUILDER_BINDING = ROOT/'manifests/native-license-provider-builder-binding.json'
FINAL_BUILDER_BINDING_SHA = 'aef5df53df9e7d342c03ab86aad0a8bb020ee2d2b1e2a8582911cac8477ab42f'
FINAL_BUILDER_BINDING_BYTES = 5373
PAIR_COMPILE_RESULT = BUILD_PARENT/'attempt01/result.json'
BUILD_RESULT = P('/home/alex/work/pocket4-native-generation-pair-builder-validation-20261107-r1/attempt01/result.json')
BUILD_RESULT_SHA = '48fee3c232fbcc918ed577954445a4f395a91a3c77fc7a24447ad88090570301'
BUILD_RESULT_BYTES = 46012
SOURCE_MANIFEST_SHA = 'd7b895e2cacd500b28d1623aff54e856199708cff13b730f0de0f83a12479a36'
TARGETS = ['libberberis_arm64', 'com.android.art']

PAIR_TERMINAL_PINS = {'pair-compile-terminal.original.json': {'bytes': 726, 'sha256': '2555046161ac0f073652c14488fa5237824c3e30b8e04c0ca6178f716364dd68'}, 'pair-validation-terminal.original.json': {'bytes': 729, 'sha256': '570da4afd0a050ae411eaafedb3107b4d4a4847610bdef25f21f991e66055913'}}
PAIR_SOURCE_PINS = {'android/native-generation-pair/engine-source-files.json': {'bytes': 110809, 'sha256': '6633fee76068fa421d5cfd3fd6f3d2440b2fa8d04b92223a1b1b9e7f9eba4139'}, 'android/native-generation-pair/engine.Android.bp': {'bytes': 25403, 'sha256': 'bfd8ee63943b331ff09c67879065f9794bae7c7b897ba049961cbe47cd2d97e7'}, 'tools/droidloom-update/src/android.rs': {'bytes': 310700, 'sha256': 'fbeb3324e24a24863088bc636465ef5884cb3e66e99b2e5eda89344e67f11256'}, 'tools/droidloom-update/src/main.rs': {'bytes': 22755, 'sha256': 'ad3c02a628d585cbd00e0e560387e44ff830136492b9cffa21badb4d6a23a9fc'}, 'tools/droidloom-update/src/native_generation_art.rs': {'bytes': 11217, 'sha256': '6e05ea449c631e7259c7be8f01bd73b189deeafee19077215477d2161700e149'}, 'tools/droidloom-update/src/native_generation_pair_build.rs': {'bytes': 15881, 'sha256': '29cd3127b8eac260752a059cee3b45841cbe29b9c76a6aadbf50d52d6730961c'}}
PAIR_TESTS = ['native_generation_pair_build::tests::ordinary_pair_accepts_only_complete_strict_scope', 'native_generation_pair_build::tests::ordinary_pair_projection_is_exact_and_only_x86_64_arm64', 'native_generation_pair_build::tests::ordinary_pair_rejects_wrong_or_partial_engine_snapshot', 'native_generation_pair_build::tests::ordinary_pair_records_are_create_only', 'native_generation_pair_build::tests::ordinary_pair_effective_engine_rejects_untracked_or_unrelated_edits', 'tests::ordinary_generation_cli_has_fixed_scope_and_explicit_fresh_output', 'native_generation_art::tests::output_rejects_source_overlap_alias_and_reuse', 'native_generation_art::tests::records_are_create_only_and_never_grant_runtime_readiness', 'native_generation::tests::legacy_and_disabled_preserve_the_disabled_mode', 'native_generation::tests::rejects_every_mixed_old_new_combination', 'native_generation::tests::enabled_triplet_requires_exact_contract', 'native_generation::tests::rejects_malformed_foreign_or_ambiguous_marker', 'native_generation::tests::rejects_foreign_elf_and_unrecognized_contract', 'native_generation::tests::rejects_symlinked_components', 'native_generation::tests::rejects_previous_protocol_for_each_role_and_mode', 'native_generation::tests::rejects_previous_protocol_inside_self_consistent_enabled_contract', 'native_generation::tests::rejects_previous_protocol_contract', 'native_generation::tests::real_ext4_apex_extraction_rejects_changed_nested_component', 'native_generation::tests::product_contract_generation_requires_enabled_triplet', 'native_generation::tests::product_contract_generation_is_create_only_and_binds_components', 'android::tests::missing_dependencies_are_rejected_even_if_caller_asks_to_allow_them', 'android::tests::default_dependency_mode_still_overrides_inherited_allow_missing', 'android::tests::target_closure_soong_patch_does_not_change_strict_builds', 'android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes', 'android::tests::restoration_preserves_original_and_removes_created_file', 'android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch', 'android::patch_tests::interrupted_projection_recovers_before_next_build']
ART_PATHS = ('art/libnativebridge/Android.bp', 'art/libnativebridge/droidloom_generation.cc', 'art/libnativebridge/droidloom_generation.h', 'art/libnativebridge/include/nativebridge/droidloom_generation_protocol.h', 'art/libnativebridge/include/nativebridge/native_bridge.h', 'art/libnativebridge/libnativebridge.map.txt', 'art/libnativebridge/native_bridge.cc', 'art/runtime/Android.bp', 'art/runtime/native_bridge_art_interface.cc', 'art/runtime/runtime.cc')

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


def builder_recovery_contract(result):
    # Normal10's original compiled ELF is absent. This successor binds a new,
    # actually executed build, retaining the original result and source meaning.
    recovered, _ = json_pin(RECOVERY_PARENT / 'recovery-stage-receipt.json',
        '811520deb262c0f2e009fc76da0113ab11f9d83af41c8a1ac5745a0bd651b921', 8479)
    staged, _ = json_pin(HERE / 'actual-builder473-recovery-stage.json',
        '811520deb262c0f2e009fc76da0113ab11f9d83af41c8a1ac5745a0bd651b921', 8479)
    require(recovered == staged and recovered['old_builder_absence_observed'] is True and
            recovered['original_absence_reason'] == 'UNKNOWN' and
            recovered['old_result']['sha256'] == 'ec5a6d322a80a9bb169b7998410ed6a2a2cfde56260ae4e1a906b2ccd3294826' and
            recovered['old_result']['bytes'] == 193038 and
            recovered['old_controller']['sha256'] == 'efe59bf47a15825c607782f9d0956eaa2a1a2588ba8477bb305670fcd7b913c8' and
            recovered['new_root'] == str(RECOVERY_PARENT) and
            recovered['new_controller'] == {
                'bytes': 87204, 'sha256': '2f4159d424a274ee8cd612db4c048e47bf01f0656af7667e3471831598b10633'} and
            recovered['profile'] == {'RAM': 2147483648, 'CPUQuota': 100, 'jobs': 1, 'nice': 10, 'swap': 0} and
            recovered['Normal10_fresh_RAM_requirement'] == HISTORICAL_MIN_AVAILABLE and
            recovered['Main_actions'] == recovered['Android_actions'] == 0 and
            recovered['production_ready'] is False and recovered['automatic_retry'] is False,
            'new builder473 recovery identity or historical scope differs')
    controller, _ = held_file(RECOVERY_PARENT / 'control-source/compile_builder.py', 131072)
    require(controller['bytes'] == 87204 and
            controller['sha256'] == recovered['new_controller']['sha256'],
            'actual recovery controller source changed')
    for phase in ('owned_resources_before', 'owned_resources_after'):
        fields = result[phase]['fields']
        require(fields['memory.max'] == '2147483648' and
                fields['cpu.max'] == '100000 100000' and
                fields['memory.swap.max'] == fields['memory.swap.current'] == '0',
                'new builder473 recovery resource envelope differs')
    require(result['owned_memory_swap_peak'] == 0 and
            result['copied_manifest']['sha256'] == RECOVERY_MANIFEST_SHA,
            'new builder473 recovery swap or original 501-file source changed')


def recovered_builder_contract():
    require(isinstance(RECOVERY_BUILDER_SHA, str) and len(RECOVERY_BUILDER_SHA) == 64 and
            all(c in '0123456789abcdef' for c in RECOVERY_BUILDER_SHA) and
            isinstance(RECOVERY_RESULT_SHA, str) and len(RECOVERY_RESULT_SHA) == 64 and
            all(c in '0123456789abcdef' for c in RECOVERY_RESULT_SHA) and
            isinstance(RECOVERY_BUILDER_BYTES, int) and 0 < RECOVERY_BUILDER_BYTES <= 64*1024*1024 and
            isinstance(RECOVERY_RESULT_BYTES, int) and 0 < RECOVERY_RESULT_BYTES <= 4*1024*1024,
            'ACTUAL_BUILDER473_COMPILE01_REQUIRED')
    result, pin = json_pin(RECOVERY_RESULT, RECOVERY_RESULT_SHA, RECOVERY_RESULT_BYTES)
    builder_recovery_contract(result)
    staged, _ = json_pin(HERE / 'actual-builder473-result.json', RECOVERY_RESULT_SHA, RECOVERY_RESULT_BYTES)
    require(result == staged and result['state'] == 'PASS' and
            result['focused_tests_passed'] == 33 and result['updater_focused_tests_passed'] == 24 and
            result['source_resume_tests_passed'] == 9 and result['expected_test_names'] == EXPECTED_TESTS and
            result['expected_source_resume_test_names'] == EXPECTED_SOURCE_TESTS and
            result['actual_registered_test_count'] == 214 and result['source_actual_registered_test_count'] == 20 and
            result['original_projection_tests_passed'] == 7 and result['typed_ingress_lock_tests_passed'] == 2 and
            result['provider_closure_tests_passed'] == 6 and result['hal_provider_tests_passed'] == 3 and
            result['systemui_test_projection_tests_passed'] == 3 and
            result['audiocontrol_example_projection_tests_passed'] == 3,
            'actual builder473 compile01 and exact 33-control qualification differs')
    commands = result['commands']
    require(len(commands) == len(EXPECTED_COMPILE_LABELS) and
            {row['label'] for row in commands} == set(EXPECTED_COMPILE_LABELS) and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in commands),
            'actual compiler command closure is incomplete')
    for indices, names, count, elf_key, gates_key in [
        (EXPECTED_TEST_INDICES, EXPECTED_TESTS, 214, 'test_elf', 'focused_result_gates'),
        (list(range(100, 109)), EXPECTED_SOURCE_TESTS, 20, 'source_test_elf', 'source_resume_result_gates')]:
        require(len(result[gates_key]) == len(names), 'actual focused result gate count differs')
        for position, name in enumerate(names):
            index = indices[position]
            label = 'projection-test-' + str(index)
            command = next(row for row in commands if row['label'] == label)
            expected_log = ('ok ' + name + '\n').encode()
            gate = {'exact_name': name, 'expected_stdout_runs': 1, 'filtered_out_per_run': count-1,
                    'outer_results': 1, 'registered_tests': count, 'summary_and_independent_result_agree': True}
            log_path = str(RECOVERY_PARENT / 'attempt01' / (label + '.libtest'))
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
    require(result['copied_manifest']['sha256'] == RECOVERY_MANIFEST_SHA and
            result['copied_manifest']['bytes'] == 99775 and delta == EXPECTED_SOURCE_DELTA and
            delta['actual_source_file_count'] == 501 and delta['unchanged_existing'] == 499 and
            delta['changed_existing'] == ['tools/droidloom-update/src/android.rs'] and
            delta['added'] == ['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'] and
            delta['builder_revision_name'] == '473-fixed-audiocontrol-example-projection' and
            result['actual_device_staging_reuse_qualified'] is False and
            'HOME' not in result['build_environment'],
            'builder source is not the exact reviewed 501-file Audiocontrol example projection successor')
    require(result['actual_parent471_compile_authority']['bytes'] == 181273 and
            result['actual_parent471_compile_authority']['sha256'] == '466d01e56fa6579636be8e82eedbc4276c31ce3e6b390dc985fe3bc454ead1e9' and
            result['audiocontrol_example_projection_authority']['bytes'] == 6453 and
            result['audiocontrol_example_projection_authority']['sha256'] == 'c642e886b77adeb07d8f38a3dd10d042218e8e6582d6fd523be751ef1317b2e5' and
            result['audiocontrol_example_original_fixture_authority']['bytes'] == 1869 and
            result['audiocontrol_example_original_fixture_authority']['sha256'] == '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6' and
            result['systemui_test_projection_retained_from_parent471'] is True and
            result['unchanged_225_project_lock_authority']['bytes'] == 96957 and
            result['unchanged_225_project_lock_authority']['sha256'] == EXTENDED_LOCK_SHA and
            result['source_lock_writer'] == 'UNKNOWN',
            'builder473 actual parent, exact example projection and unchanged current lock are incomplete')
    require(result['actual_toolchain']['rustup_proxy_executed'] is False and
            result['actual_toolchain']['rustup_proxy_changed_bytes_approved_for_execution'] is False and
            result['runtime_authorization_enabled'] is False and
            result['framework_Java_and_Android_JNI_compiled'] is False and
            result['transitive_framework_closure_qualified'] is False,
            'builder receipt scope was widened')
    # This receipt proves the historical 473 source qualification. The newer
    # 504-file builder below is the only executable authority. Do not require an
    # obsolete compiled artifact to remain installed or reproduce its inode.
    builder = result['builder_elf']
    require(builder['path'] == str(RECOVERY_BUILDER) and
            builder['sha256'] == RECOVERY_BUILDER_SHA and
            builder['bytes'] == RECOVERY_BUILDER_BYTES and
            type(builder['identity']) is list and len(builder['identity']) == 6 and
            all(type(value) is int for value in builder['identity']) and
            builder['identity'][2] & 0o111,
            'historical recovery473 executable receipt differs')
    source_map, source_pin = json_pin(RECOVERY_PARENT / 'attempt01/copied-builder-source-manifest.json',
                                    RECOVERY_MANIFEST_SHA, 99775)
    staged_map, _ = json_pin(HERE / 'expected-builder473-manifest.json', RECOVERY_MANIFEST_SHA, 99775)
    require(source_map == staged_map and len(source_map) == 501 and
            source_map[GO_PATCH]['sha256'] == GO_PATCH_SHA and
            source_map['android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp'] == {
                'bytes': 3392, 'kind': 'file', 'mode': 420,
                'sha256': 'f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da'} and
            source_map['android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp'] == {
                'bytes': 1869, 'kind': 'file', 'mode': 420,
                'sha256': '9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6'} and
            source_map['android/manifest/m2-role-ingress-source-lock.json']['sha256'] == PREVIOUS_TYPED_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-provider-source-lock.json']['sha256'] == PREVIOUS_PROVIDER_LOCK_SHA and
            source_map['android/manifest/m2-role-ingress-hal-provider-source-lock.json']['sha256'] == EXTENDED_LOCK_SHA,
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
            resource_memory['MemAvailable'] < HISTORICAL_MIN_AVAILABLE and
            HISTORICAL_MIN_AVAILABLE - resource_memory['MemAvailable'] == 1251254272,
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

def observe_prepared_inputs(context, first):
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
        require(portable == context['builder_map'], 'actual 515-file final builder source changed')
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
    context['prior_failure_authority_pins'].extend(pair_action_authorities()[4])
    context['initial_observations'] = observe_inputs(context, True)
    return context




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





def verify_inputs_after(context):
    observations = observe_inputs(context, False)
    for wanted in [context['prepared_pin'], context['compiled_pin'], context['inventory_pin'],
                   context['builder_map_pin']]:
        path = P(wanted['path'])
        row, _ = held_file(path, wanted['bytes'])
        require(row == wanted, 'runtime input authority changed: ' + str(path))
    for wanted in context['prior_failure_authority_pins']:
        row, _ = held_file(wanted['path'], wanted['bytes'])
        require(row == wanted, 'original failure or staged source authority changed')
    compiled = pair_action_authorities()[0]
    require(pair_builder_identity(compiled) == context['builder_pin'], 'paired builder alias or inode changed')
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
    claim = {"schema": 1, "state": "STARTING_ORDINARY_ENGINE_AND_WHOLE_ART_PAIR_NORMAL_STRICT_BUILD",
             "started_utc": utc(), "preparation_sha256": expected_sha, "plan": plan(),
             "mem_available_before": memory["MemAvailable"], "swap_free_before": memory["SwapFree"],
             "resource_admission_receipt": resource_admission_pin,
             "resource_admission_qualified": True, "owned_budget_before_builder": owned_budget_before,
             "global_swap_is_owned_budget": False,
             "cpu_affinity_before": affinity,
             "cpu_affinity": selected, "unit": unit, "normal_builder_lock_and_recovery": True,
             "automatic_retry": False, "Main_resource_changes": False}
    claim["filesystem_available_before"] = os.statvfs(ACTIVE_WORK).f_bavail * os.statvfs(ACTIVE_WORK).f_frsize
    save(ATTEMPT / "claim.json", claim)
    save(ATTEMPT / "input-bindings-before.json", {
        "work_preparation": context["prepared_pin"], "actual_builder_compile": context["compiled_pin"],
        "actual_builder_manifest": context["builder_map_pin"], "actual_content_manifests": context["manifest_pins"],
        "reused_inventory_source": context["inventory_pin"], "observations": context["initial_observations"],
        "prior_failure_authorities": context["prior_failure_authority_pins"]})
    print(json.dumps(claim), flush=True)
    env = os.environ.copy()
    env["DROIDLOOM_NATIVE_BRIDGE_SOURCE"] = str(ENGINE_SOURCE)
    # The actual outer affinity selected exactly two CPUs above; do not reserve again.
    env["DROIDLOOM_COMPILER_CPUS_RESERVED"] = "1"
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
                code = child.wait(timeout=21600)
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
        terminal = {"schema": 1, "state": "ORDINARY_PAIR_COMMAND_COMPLETED_QUALIFICATION_PENDING" if failure is None else "FAILED",
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
                    "source_projection_journal_present": (ACTIVE_WORK / "source-projection.json").exists(),
                    "normal_command_completion_gate": artifact,
                    "input_after_qualified": input_after is not None and input_after_error is None,
                    "input_after_error": input_after_error,
                    "work_preparation_sha256": PREPARATION_SHA, "builder_compile_sha256": FINAL_BUILDER_RECOVERY_SHA,
                    "historical_pair_validation_sha256": BUILD_RESULT_SHA,
                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,
                    "prior_failed_inner_sha256": PRIOR_INNER_SHA, "prior_failed_outer_sha256": PRIOR_OUTER_SHA,
                    "published_source_path": str(ACTIVE_SOURCE),
                    "source_reconciliation_uses_normal_builder": True,
                    "old_QA_epoch_invalid": True, "new_QA_epoch_qualified": False,
                    "complete_native_engine_and_ART_TU_qualified": False,
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

def pair_source_delta_contract(base, current):
    added = set(PAIR_SOURCE_PINS) - set(base)
    changed = {name for name in base if current.get(name) != base[name]}
    require(len(base) == 501 and len(current) == 504 and
            set(current) == set(base) | added and added == {
                'android/native-generation-pair/engine-source-files.json',
                'android/native-generation-pair/engine.Android.bp',
                'tools/droidloom-update/src/native_generation_pair_build.rs'} and
            changed == {'tools/droidloom-update/src/android.rs',
                'tools/droidloom-update/src/main.rs',
                'tools/droidloom-update/src/native_generation_art.rs'},
            'ordinary pair source is not the exact reviewed 501-to-504 delta')
    for name, wanted in PAIR_SOURCE_PINS.items():
        row = current[name]
        require(row['kind'] == 'file' and row['bytes'] == wanted['bytes'] and
                row['sha256'] == wanted['sha256'] and
                row['mode'] == (base[name]['mode'] if name in base else 420),
                'ordinary pair exact candidate source differs: ' + name)
    require(sum(current[name] == row for name, row in base.items()) == 498,
            'ordinary pair unchanged source count differs')


def pair_terminal_contract(value, job, success):
    require(value['job_id'] == job and value['state'] == ('succeeded' if success else 'failed') and
            value['exit_code'] == (0 if success else 1) and value['timed_out'] is False and
            value['output_complete'] is True and value['output_durable'] is True and
            value['terminal_publication_confirmed'] is True and
            value['automatic_retry'] is False and value['cancelled'] is False and
            not any(value['log_truncated'].values()) and
            all(value['log_synced'].values()) and not any(value['log_errors'].values()),
            'ordinary pair authoritative terminal differs')


FINAL_BUILDER_SOURCE_MANIFEST = CANDIDATE_ROOT/'postfreeze-build-r2/builder-source-manifest.json'
FINAL_BUILDER_SOURCE_MANIFEST_SHA = '73d23be7f7f4bd416f1837ef0d595d9a09e61f690d75f4d45aec83976131141a'
FINAL_BUILDER_SOURCE_MANIFEST_BYTES = 102763
FIX_TESTS = ['native_generation_pair_build::tests::ordinary_pair_generator_provider_closure_rejects_partial_and_unrelated_inputs', 'android::tests::ordinary_pair_provider_bound_preserves_existing_writer_and_restores', 'android::tests::ordinary_pair_provider_bound_rejects_wrong_mode_and_drift_before_writes', 'android::tests::ordinary_pair_gc_observation_keeps_target_and_dependency_configuration', 'native_generation_pair_build::tests::ordinary_pair_provider_closure_rejects_unlisted_projects_and_prior_plan', 'native_generation_pair_build::tests::ordinary_pair_display_extension_rejects_previous_and_wider_subtrees', 'native_generation_pair_build::tests::ordinary_pair_source_extension_is_exact_and_monotonic', 'native_generation_pair_build::tests::ordinary_pair_source_extension_rejects_revision_policy_and_path_drift', 'native_generation_pair_build::tests::ordinary_pair_source_workspace_rejects_previous_plan_and_alias', 'native_generation_pair_build::tests::ordinary_pair_accepts_only_complete_strict_scope', 'native_generation_pair_build::tests::ordinary_pair_projection_is_exact_and_only_x86_64_arm64', 'native_generation_pair_build::tests::ordinary_pair_rejects_wrong_or_partial_engine_snapshot', 'native_generation_pair_build::tests::ordinary_pair_records_are_create_only', 'native_generation_pair_build::tests::ordinary_pair_effective_engine_rejects_untracked_or_unrelated_edits', 'android::tests::ordinary_pair_local_signer_keeps_exact_real_upstream_modules', 'android::tests::ordinary_pair_local_signer_rejects_unpinned_or_reprojected_source', 'tests::native_pair_reservation_is_applied_once_to_the_actual_job_budget', 'android::tests::normal_serialservice_projection_preserves_real_fuzzer_and_dependencies', 'android::tests::normal_serialservice_projection_rejects_source_drift', 'android::tests::normal_systemui_projection_keeps_real_dagger_defaults', 'android::tests::normal_systemui_projection_rejects_drift_and_keeps_other_roots', 'android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata', 'android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas', 'android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged', 'android::tests::restoration_preserves_original_and_removes_created_file', 'android::patch_tests::interrupted_projection_recovers_before_next_build', 'android::tests::missing_dependencies_are_rejected_even_if_caller_asks_to_allow_them', 'android::tests::default_dependency_mode_still_overrides_inherited_allow_missing', 'android::tests::sdkextensions_provider_requires_complete_pinned_snapshot', 'android::tests::sdkextensions_fallbacks_preserve_original_scope_and_legacy_builds', 'android::tests::original_connectivity_module_sdk_stubs_are_not_shadowed', 'android::tests::original_permission_sdk_stubs_are_not_shadowed']

def historical_source_scope():
    packet, _ = json_pin(ROOT/'attempts/full-build-11/build-packet.json',
        'eef8edc84a6c9a35f515bfb3d62898759b6610148d158ba65deb292645247f2c', 235791)
    source = packet['controller_source']
    require(hashlib.sha256(source.encode()).hexdigest() ==
            '4da41b6640a04be63dfca302b0e52d0ad033842414416f8760e58c4ba1b9846c',
            'preserved historical controller differs')
    scope = {'__name__': 'preserved_native268_input_authorities'}
    exec(compile(source, 'preserved_native268_controller.py', 'exec'), scope, scope)
    return scope



def final_source_builder_proof():
    for name, digest, size, job in (
        ('final-normal-release-terminal.json',
         'ae9a40d4126702e1849a46e014b41df73f652f5cef3caeba5b4f0fa4c25f8f0e', 731,
         '1a1b9755c3b-12894-146a'),
        ('fix18-controls-terminal.json',
         '606da516d45c2b01cb53ebe826edb975b6a136037ec6331e8705f9a59892fbb5', 735,
         '1a1b971cc8d-12894-1455')):
        terminal, _ = json_pin(CANDIDATE_ROOT/name, digest, size)
        pair_terminal_contract(terminal, job, True)
    result, result_pin = json_pin(FINAL_BUILDER_RECOVERY_RESULT,
        FINAL_BUILDER_RECOVERY_SHA, FINAL_BUILDER_RECOVERY_BYTES)
    require(result['schema'] == 'native597-postfreeze-normal-build-v2' and
            result['state'] == 'POSTFREEZE_NORMAL_BUILD_AND_COMPLETE_SOURCE_BINDING_PASSED' and
            result['source_root'] == str(BUILD_SOURCE) and result['source_file_count'] == 515 and
            result['complete_source_before_after_equal'] is True and
            result['complete_file_identities_before_after_equal'] is True and
            result['owned_children_empty'] is True and result['subreaper_restored'] is True and
            result['owned_retirement'] == result['final_retirement'] == [] and
            result['Soong_invocations'] == 0 and result['native_pair_artifact_qualified'] is False and
            result['runtime_qualified'] is False,
            'final complete-source normal release build proof differs')
    build = result['normal_build']
    require(build['returncode'] == 0 and build['argv'] == [
        'build', '--release', '--offline', '--locked', '-j', '1', '-p', 'droidloom-source',
        '-p', 'droidloom-update', '--bins', '--target', 'x86_64-unknown-linux-gnu',
        '--message-format=json'], 'actual normal release build command differs')
    for key in ('stdout', 'stderr'):
        wanted = build[key]
        row, _ = held_file(wanted['path'], wanted['bytes'])
        require(row['sha256'] == wanted['sha256'] and row['bytes'] == wanted['bytes'],
                'actual normal build log changed: ' + key)
    fields = result['resources_after']
    events = dict(line.split() for line in fields['memory.events'].splitlines())
    require(fields['cpu.max'] == '100000 100000' and fields['memory.max'] == '1610612736' and
            fields['memory.swap.max'] == fields['memory.swap.current'] == '0' and
            all(events[name] == '0' for name in ('max', 'oom', 'oom_kill', 'oom_group_kill')),
            'actual final normal release resource gate differs')
    source_map, source_pin = json_pin(FINAL_BUILDER_SOURCE_MANIFEST,
        FINAL_BUILDER_SOURCE_MANIFEST_SHA, FINAL_BUILDER_SOURCE_MANIFEST_BYTES)
    require(len(source_map) == 515 and all(row['kind'] == 'file' for row in source_map.values()) and
            result['source_manifest'] == {'path': str(FINAL_BUILDER_SOURCE_MANIFEST),
                'bytes': FINAL_BUILDER_SOURCE_MANIFEST_BYTES, 'sha256': FINAL_BUILDER_SOURCE_MANIFEST_SHA},
            'exact complete final builder source manifest differs')
    after = result['source_manifest_after']
    after_map, _ = json_pin(after['path'], FINAL_BUILDER_SOURCE_MANIFEST_SHA,
                            FINAL_BUILDER_SOURCE_MANIFEST_BYTES)
    require(after_map == source_map, 'actual final source before/after maps differ')
    control, _ = json_pin(CANDIDATE_ROOT/'visibility-r4-controls/result.json',
        '263c5fbec8b780dfe297a1a91d62484bb20fb6e014eca812e50b32f7c8d8206f', 24916)
    require(control['all_passed'] is True and control['owned_children_empty'] is True and
            control['state'] == 'PASS_EXACT_597_FIX18_VISIBILITY_CONTROLS' and
            len(control['controls_passed']) == 17 and len(control['steps']) == 18 and
            all(row['exit_code'] == 0 for row in control['steps']) and
            control['source_manifest_before']['sha256'] ==
            control['source_manifest_after']['sha256'] == FINAL_BUILDER_SOURCE_MANIFEST_SHA,
            'actual final visibility controls differ')
    for command in control['steps']:
        for key in ('stdout', 'stderr'):
            wanted = command[key]
            row, _ = held_file(wanted['path'], wanted['bytes'])
            require(row['sha256'] == wanted['sha256'] and row['bytes'] == wanted['bytes'],
                    'actual final control output changed: ' + command['label'])
    binaries = {}
    for name, size, digest in (
        ('droidloom-source', 1501880, '9fd7276af58c56b2a970c5586aad792dbfca29ced9a1eab4dea19bec135f5a86'),
        ('droidloom-update', 3805784, '75bf728444a101d39428a8c90a876e53d3325c1e45441c132b2552deb74660f0')):
        recorded = result['binaries'][name]
        wanted = recorded['preserved_binary']
        require(recorded['actual_compiler_artifact_records'] == 1 and
                recorded['normal_output']['sha256'] == wanted['sha256'] == digest and
                recorded['normal_output']['bytes'] == wanted['bytes'] == size and
                wanted['path'] == str(CANDIDATE_ROOT/'bin-r4'/name),
                'normal artifact and preserved binary binding differs: ' + name)
        row, _ = held_file(wanted['path'], 64*1024*1024)
        old = wanted['identity']
        times = [old[7]*1000000000 + old[8], old[9]*1000000000 + old[10]]
        converted = old[:3] + [old[6]] + times
        actual = P(wanted['path']).lstat()
        full = [actual.st_dev, actual.st_ino, actual.st_mode, actual.st_uid, actual.st_gid,
                actual.st_nlink, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns]
        require(row['sha256'] == digest and row['bytes'] == size and row['identity'] == converted and
                full == old[:7] + times and full[3:6] == [1000, 1000, 1] and
                stat.S_IMODE(row['identity'][2]) == 0o700,
                'preserved normal binary content or full file identity changed: ' + name)
        binaries[name] = row
    require(binaries['droidloom-update']['path'] == str(BUILDER) and
            binaries['droidloom-update']['sha256'] == BUILDER_SHA and
            binaries['droidloom-update']['bytes'] == BUILDER_BYTES,
            'final invoked builder does not match normal compiled binary')
    return result, result_pin, source_map, source_pin, binaries['droidloom-update']



def pair_builder_identity(result):
    # Historical controls remain attributed to their original exact executable.
    historical_source_scope()['pair_builder_identity'](result)
    return final_source_builder_proof()[4]


def pair_action_authorities():
    compiled, compile_pin = json_pin(PAIR_COMPILE_RESULT,
        '2f74a726d476940bfa5bf3c2aa5464a596bee9d2520b18ec65e50be8ae0ce6e2', 55564)
    validated, validation_pin = json_pin(BUILD_RESULT, BUILD_RESULT_SHA, BUILD_RESULT_BYTES)
    pins = [compile_pin, validation_pin]
    terminals = {}
    for name, ref in PAIR_TERMINAL_PINS.items():
        value, pin = json_pin(HERE/name, ref['sha256'], ref['bytes'])
        terminals[name] = value
        pins.append(pin)
    pair_terminal_contract(terminals['pair-compile-terminal.original.json'], '1a1b420093f-fc05-8664', False)
    pair_terminal_contract(terminals['pair-validation-terminal.original.json'], '1a1b4294c28-fc05-8688', True)
    require(compiled['state'] == 'FAIL' and
            compiled['error'] == "RuntimeError('host command failed: test-17')" and
            compiled['candidate_source_unchanged'] is True and compiled['original_source_unchanged'] is True and
            compiled['owned_reaper']['final_children_empty'] is True and len(compiled['commands']) == 24,
            'preserved actual pair compile/test failure differs')
    require(validated['state'] == 'PASS' and validated['prior_action_remains_failed'] is True and
            validated['prior_action_job_id'] == '1a1b420093f-fc05-8664' and
            validated['prior_action_result'] == {
                'path': str(PAIR_COMPILE_RESULT), 'bytes': 55564,
                'sha256': '2f74a726d476940bfa5bf3c2aa5464a596bee9d2520b18ec65e50be8ae0ce6e2'} and
            validated['total_tests_passed_across_two_actions'] == 27 and
            validated['preserved_prior_passed_tests'] == PAIR_TESTS[:17] and
            validated['tests_passed_here'] == PAIR_TESTS[17:] and
            validated['qualified_inputs_unchanged_after'] is True and
            validated['owned_reaper']['final_children_empty'] is True and validated['owned_reaper']['restored'] is True and
            validated['compiler_invocations'] == validated['Soong_invocations'] ==
            validated['Main_reads'] == validated['Android_actions'] == 0 and
            validated['runtime_qualified'] is False, 'pair validation coverage or scope differs')
    require(len(validated['commands']) == 10 and
            validated['qualified_inputs_before']['registry_files_unchanged'] == 2706 and
            validated['qualified_inputs_before']['qualified_tools_unchanged'] == 125 and
            len(validated['qualified_inputs_before']['selected_packages']) == 2 and
            all(len(row['package_ids']) == 49 and row['compiler_artifacts'] == 60
                for row in validated['qualified_inputs_before']['selected_packages']),
            'pair actual compiler/dependency closure incomplete')
    for index, name in enumerate(PAIR_TESTS):
        if index < 17:
            row = compiled['commands'][6+index]
            expected_argv = [compiled['tests_elf']['path'], '--exact', name, '--test-threads=1', '--nocapture']
        else:
            row = validated['commands'][index-17]
            logfile = P(BUILD_RESULT).parent/('test-%02d.libtest' % index)
            expected_argv = [compiled['tests_elf']['path'], '--exact', name,
                             '--test-threads=1', '--nocapture', '--logfile', str(logfile)]
            log = row['independent_libtest_result']
            expected = ('ok '+name+'\n').encode()
            require(log['path'] == str(logfile) and log['bytes'] == len(expected) and
                    log['sha256'] == hashlib.sha256(expected).hexdigest(), 'pair independent libtest result differs')
        require(row['argv'] == expected_argv and row['returncode'] == 0 and row['child_reaped'] is True and
                row['owned_tree_cleanup_complete'] is True and row['remaining_owned_children'] == [] and
                not row['errors'] and all(row['capture_eof'].values()) and
                row['subject_RLIMIT_FSIZE_unchanged'] is True, 'pair exact test execution differs: '+name)
    for result, limit in [(compiled, '2147483648'), (validated, '536870912')]:
        for phase in ('resource_before', 'resource_after'):
            fields = result[phase]
            events = dict(line.split() for line in fields['memory.events'].splitlines())
            require(fields['memory.max'] == limit and fields['cpu.max'] == '100000 100000' and
                    fields['memory.swap.max'] == fields['memory.swap.current'] == '0' and
                    all(events[name] == '0' for name in ('oom', 'oom_kill', 'oom_group_kill')),
                    'pair host compile or validation resource contract differs')
    # Validation reached memory.max while hashing old tool inputs. Preserve its
    # real 3305 events; this host observation is not a heavy-build resource gate.
    require(dict(line.split() for line in validated['resource_after']['memory.events'].splitlines())['max'] == '3305',
            'actual bounded cache-pressure observation was changed')
    return compiled, validated, compile_pin, validation_pin, pins


def builder_contract():
    _, _, previous_map, _, _ = historical_source_scope()['builder_contract']()
    result, result_pin, current_map, current_pin, builder = final_source_builder_proof()
    changed = {
        'android/native-generation-pair/source-lock.json':
            '2b699174977614e080cf99a991f3e648774b24581c4ecdc29f1bd53b7b01ef23',
        'tools/droidloom-source/src/lib.rs':
            '9b4fe92d69a561da10687a88301b3f9b655c515944621629a267ca3f5d0cbd97',
        'tools/droidloom-update/src/native_generation_pair_build.rs':
            '0ab04eb4fb8bc87e16e5e04979859906e6b81f607e3f0c897686a642e88d4d26',
        'tools/droidloom-update/src/android.rs':
            '74347a55535975f949a63783b3fdb4ea7a4b0c33f74c9370b6fd6eff8ccb70a3',
    }
    added = {
        'tools/droidloom-source/examples/frozen_pair_recipe.rs',
        'tools/droidloom-source/tests/fixtures/ordinary-pair-cts-279-cones.json',
        'android/native-generation-pair/provider-fixtures/Launcher3.Android.bp',
        'android/native-generation-pair/provider-fixtures/Settings.Android.bp',
        'android/native-generation-pair/provider-fixtures/Shell.Android.bp',
        'android/native-generation-pair/provider-fixtures/aconfigd.Android.bp',
        'tools/droidloom-source/src/.hepta-lock-0544fc952eefa8d170bbd200',
    }
    require(len(previous_map) == 508 and set(current_map) == set(previous_map) | added and
            {name for name in previous_map if previous_map[name] != current_map[name]} == set(changed),
            'unexpected final builder source change')
    for name, digest in changed.items():
        require(current_map[name]['sha256'] == digest, 'exact reviewed source delta differs: ' + name)
    require(current_map['tools/droidloom-source/src/.hepta-lock-0544fc952eefa8d170bbd200'] == {
        'kind': 'file', 'bytes': 0, 'mode': 0o600,
        'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'},
        'exact inherited noncode tool sidecar changed')
    return result, result_pin, current_map, current_pin, builder


ACTIVE_WORK = ROOT/'work'
ACTIVE_SOURCE = ACTIVE_WORK/'aosp-source'
ACTIVE_LOCK = BUILD_SOURCE/'android/native-generation-pair/source-lock.json'
ACTIVE_LOCK_SHA = '94d2a5d2e00d3b5d126752ee58337e71fb88a5763f7b977be4a56471f4e68ee6'
ACTIVE_LOCK_BYTES = 116325
ACTIVE_MANIFEST_SHA = '63cb6c1937f6f2a749fd528b806f6d90f76b8735f21911edb4d0cb182717394a'
ACTIVE_MANIFEST_BYTES = 131148
ACTIVE_PREPARATION = ROOT/'source-materialization-native268-05/result.json'
ACTIVE_PREPARATION_SHA = '0eb13e254fb8f2638113d75da6eee79017235fdcb896951b3df0b44b6343dcb7'
ACTIVE_PREPARATION_BYTES = 709586
ACTIVE_BINDING = ROOT/'manifests/native-license-provider-active-work-binding.json'
ACTIVE_BINDING_SHA = 'afa9d9f753e0613bd6aa155b6f562e413936741ee4427f3c55cf2d23f1032e58'
ACTIVE_BINDING_BYTES = 2369

def historical_active_materialization():
    ACTIVE_BINDING = ROOT/'manifests/native-license-provider-active-work-binding.json'
    ACTIVE_BINDING_SHA = 'afa9d9f753e0613bd6aa155b6f562e413936741ee4427f3c55cf2d23f1032e58'
    ACTIVE_BINDING_BYTES = 2369
    ACTIVE_PREPARATION = ROOT/'source-materialization-native268-05/result.json'
    ACTIVE_PREPARATION_SHA = '0eb13e254fb8f2638113d75da6eee79017235fdcb896951b3df0b44b6343dcb7'
    ACTIVE_PREPARATION_BYTES = 709586
    ACTIVE_LOCK = ROOT/'source/builder/android/native-generation-pair/source-lock.json'
    binding, binding_pin = json_pin(ACTIVE_BINDING, ACTIVE_BINDING_SHA, ACTIVE_BINDING_BYTES)
    require(binding['schema'] == 'pocket4-native-final-active-work-binding-v1' and
            binding['work'] == str(ACTIVE_WORK) and binding['source'] == str(ACTIVE_SOURCE),
            'active source binding scope differs')
    preparation, preparation_pin = json_pin(ACTIVE_PREPARATION, ACTIVE_PREPARATION_SHA, ACTIVE_PREPARATION_BYTES)
    require(preparation['state'] == 'PASS_NORMAL_MATERIALIZED_AND_VERIFIED' and
            preparation['normal_materialization_complete'] is True and
            preparation['owned_children_empty'] is True and preparation['source_locks_released'] is True and
            preparation['production_actions'] == preparation['Soong_invocations'] == 0 and
            preparation['original_work_modified'] is False and
            preparation['projects'] == 268 and preparation['root_links'] == 8 and
            preparation['original_manifest_before'] == preparation['original_manifest_after'] and
            preparation['original_manifest_before']['sha256'] == PUBLISHED_MANIFEST_SHA and
            preparation['lock'] == binding['source_lock'] and
            preparation['active_manifest_after'] == binding['source_manifest'] and
            len(preparation['commands']) == 12,
            'active source lacks actual full normal materialization and verification')
    for label, command in zip(('verify-lock', 'reconcile', 'verify-materialized'), preparation['commands'][:3]):
        expected = [preparation['source_cli']['path'], label, '--lock', str(ACTIVE_LOCK)]
        if label != 'verify-lock':
            expected += ['--output', str(ACTIVE_SOURCE)]
        require(command['argv'] == expected and command['returncode'] == 0 and
                command['owned_children_empty'] is True, 'normal source command proof differs')
    physical = preparation['commands'][3:]
    require([row['label'] for row in physical] ==
            ['nanopb-required-actual-source', 'pigweed-added-original-subtrees', 'vold-aconfig-original-leaf', 'crashrecovery-sdk-api-original-leaves', 'ondevice-latest-sdk-api-original-leaves', 'license-original-inputs-0', 'license-original-inputs-1', 'license-original-inputs-2', 'license-original-inputs-3'] and
            all(row['returncode'] == row['expected_returncode'] == 0 and
                row['owned_children_empty'] is True for row in physical) and
            preparation['nanopb_root_C_header_license_and_generator_count'] == 15 and
            preparation['protobuf_original_python_glob_count'] == 45 and
            preparation['vold_original_aconfig_leaf_count'] == 1 and
            preparation['vold_original_aconfig_leaf']['bytes'] == 248 and
            preparation['vold_original_aconfig_leaf']['sha256'] ==
                'bbdb30bb91045e7daae3c709198b0e9666cc896150ecd2cecff6784087675205' and
            preparation['vold_original_aconfig_leaf']['git_blob'] ==
                'd9c8fe2ebfd0bfaf097a625ac5d7bcf06165c406' and
            preparation['pigweed_added_original_blob_count'] == 505 and
            len(preparation['independent_native_git_before']) == 268 and
            len(preparation['independent_native_git_after']) == 268 and
            all(row['independent_git_common_dir'] is True for row in
                preparation['independent_native_git_before'] + preparation['independent_native_git_after']),
            'exact new generator/source bytes or independent native repository proof differs')
    require(preparation['crashrecovery_original_sdk_api_leaf_count'] == 6 and
            set(preparation['crashrecovery_original_sdk_api_leaves']) ==
                {'packages/modules/CrashRecovery/service/api/' + name for name in
                 ('current.txt', 'removed.txt', 'module-lib-current.txt', 'module-lib-removed.txt',
                  'system-server-current.txt', 'system-server-removed.txt')} and
            all(row['project_commit'] == '02451209cebd4648fd54ad3757f1a85ee9cd628b' for row in
                preparation['crashrecovery_original_sdk_api_leaves'].values()) and
            preparation['original_sdk_api_audit'] ==
                {'path': str(ROOT/'source-evidence/native-java-sdk-api-audit-15/result.json.gz'),
                 'bytes': 228012, 'sha256': '45b587e0a1a8ce8c966def30f11bcb71ad9a9c0a3f10e7e88b812420790801dc'},
            'exact original SDK API input closure differs')
    require(preparation['ondevice_original_latest_api_leaf_count'] == 6 and
            set(preparation['ondevice_original_latest_api_leaves']) ==
                {'prebuilts/sdk/36/' + scope + '/api/framework-ondeviceintelligence' + suffix + '.txt'
                 for scope in ('public', 'system', 'module-lib') for suffix in ('', '-removed')} and
            all(row['project_commit'] == '0f07e8d60ab0aba46129e427101f96ba459a95c1' for row in
                preparation['ondevice_original_latest_api_leaves'].values()) and
            sum(row['bytes'] for row in preparation['ondevice_original_latest_api_leaves'].values()) == 14054 and
            preparation['original_latest_api_evidence'] ==
                {'path': str(ROOT/'source-evidence/native-latest-sdk-api-original-leaves-16/result.json.gz'),
                 'bytes': 204997, 'sha256': '981004257d97d8cc7e6677c974b48e97881a09fba7fd4b6b2db2049db6b83914'},
            'exact original latest API tracking input closure differs')
    require(set(preparation['original_license_inputs']) == {
                'external/libultrahdr/adobe-hdr-gain-map-license/Android.bp',
                'external/libultrahdr/adobe-hdr-gain-map-license/NOTICE',
                'external/vulkan-headers/LICENSES/Apache-2.0.txt',
                'external/vulkan-headers/LICENSES/MIT.txt',
                'external/wpa_supplicant_8/wpa_supplicant/wpa_gui-qt4/icons/LICENSE',
                'prebuilts/misc/darwin-x86/yasm/COPYING',
                'prebuilts/misc/darwin-x86_64/sdl2/include/SDL2/NOTICE',
                'prebuilts/misc/linux-x86/yasm/COPYING'} and
            sum(row['bytes'] for row in preparation['original_license_inputs'].values()) == 26130 and
            preparation['original_license_evidence'] ==
                {'path': str(ROOT/'source-evidence/native-license-original-leaves-17-r2/result.json.gz'),
                 'bytes': 19628, 'sha256': '56b2a5311df565f3cb248bf83b152dca0233bed08750cda74b7f98bea64a7141'} and
            set(preparation['cronet_both_original_license_branches_present']) == {'stable/LICENSE', 'tot/LICENSE'} and
            all(row['materialized'] and row['git_blob'] == '723a2d11655b7b2fa5658a83d112b84df3b4c90e' and
                row['actual']['bytes'] == 437280 and
                row['actual']['sha256'] == 'b9c17d04beeb01717f47116fe2e09e4099f7edc4c8723435c57ededa33801a6f'
                for row in preparation['cronet_both_original_license_branches_present'].values()),
            'exact original license provider and text input closure differs')
    return binding, binding_pin, preparation, preparation_pin



def partial_recovery_predecessor(preparation, historical_binding, historical_preparation):
    require(preparation['schema'] == 'normal-partial-recovery-v1' and
            preparation['qualification_scope'] == 'exact_268_to_597_after_preserved_r2_partial_boundary_failure' and
            preparation['resource_history_clear'] is False,
            'exact normal partial-source recovery with preserved failure history required')
    authorities = []
    def read(reference, expected_path, maximum, document=False):
        require(type(reference) is dict and set(reference) == {'path', 'bytes', 'sha256'} and
                reference['path'] == str(expected_path) and type(reference['bytes']) is int and
                0 <= reference['bytes'] <= maximum,
                'fixed bounded source-history reference required')
        row, raw = held_file(expected_path, maximum, document)
        require(row['bytes'] == reference['bytes'] and row['sha256'] == reference['sha256'] and
                expected_path.lstat().st_nlink == 1,
                'preserved source-history bytes or link count changed')
        authorities.append(row)
        return (json.loads(raw) if document else None), row
    failed, failed_pin = read(preparation['resumed_from_failed_original'],
        CANDIDATE_ROOT/'normal-reconcile-r2/result.json', 4 * 1024 * 1024, True)
    terminal, terminal_pin = read(preparation['resumed_from_failed_terminal'],
        CANDIDATE_ROOT/'normal-reconcile-r2/h-terminal.json', 65536, True)
    boundary, boundary_pin = read(preparation['resumed_from_boundary'],
        CANDIDATE_ROOT/'normal-reconcile-r2-boundary-stop-r1/result.json', 4 * 1024 * 1024, True)
    boundary_terminal, boundary_terminal_pin = read(preparation['resumed_from_boundary_terminal'],
        CANDIDATE_ROOT/'normal-reconcile-r2-boundary-stop-r1/h-terminal.json', 65536, True)
    pair_terminal_contract(terminal, '1a1b9b64e12-12894-1641', False)
    pair_terminal_contract(boundary_terminal, '1a1ba0db3de-12894-1832', True)
    errors = failed['errors']
    require(failed['schema'] == 'native-normal-exact-597-reconcile-v2' and
            failed['state'] == 'NORMAL_MATERIALIZATION_FAILED_PRESERVED' and
            failed['normal_materialization_qualified'] is False and
            failed['owned_retirement_qualified'] is True and failed['source_locks_released'] is True and
            len(errors) == 2 and set(errors[0]) == {'type', 'message', 'traceback'} and
            errors[0]['type'] == 'RuntimeError' and errors[0]['message'] == 'normal materialization cancelled: 15' and
            type(errors[0]['traceback']) is str and 0 < len(errors[0]['traceback']) <= 65536 and
            errors[1] == {'type': 'OwnedResourceGate', 'message': 'memory or swap event during materialization'} and
            failed['Soong_invocations'] == 0 and failed['runtime_qualified'] is False and
            failed['native_pair_artifact_qualified'] is False and
            'materialized_manifest' not in failed and 'materialized_manifest_snapshot' not in failed,
            'only the actual partial r2 boundary stop and preserved resource failure may precede recovery')
    resources = failed['resources']
    rows = [line.split() for line in resources['memory.events'].splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows),
            'historical source memory events malformed')
    events = dict(rows)
    require(len(events) == len(rows) and int(events.get('max', '0')) > 0 and
            all(events.get(name) == '0' for name in ('oom', 'oom_kill', 'oom_group_kill')) and
            resources['cpu.max'] == '200000 100000' and resources['memory.max'] == '3221225472' and
            resources['memory.swap.max'] == resources['memory.swap.current'] == '0' and
            preparation['preserved_prior_resources'] == resources and
            all(type(row['wait_status']) is int and row['wait_status'] == 0 for row in failed['retirement']),
            'r2 resource event or owned-child status history was altered')
    require(boundary['schema'] == 'native597-r2-source-boundary-stop-v1' and
            boundary['state'] == 'ORIGINAL_CONTROLLER_STOPPED_AFTER_GIT_DRAIN' and boundary['errors'] == [] and
            boundary['source_worktree_writes'] == boundary['Git_signals'] == 0 and
            boundary['source_materialization_qualified'] is False and boundary['original_attempt_remains_failed'] is True and
            boundary['materializer_stopped'] is True and boundary['controller_term_sent'] is True and
            boundary['all_observed_git_exit_codes_zero'] is True and boundary['native_source_locks_observed_free'] is True and
            boundary['actual_adopted_retirement'] == failed['retirement'] and
            boundary['original_result'] == preparation['resumed_from_failed_original'],
            'actual successful natural-Git boundary and complete original retirement required')
    controller, materializer, selected = [boundary[name] for name in
        ('controller_identity', 'materializer_identity', 'selected_git')]
    require(controller['pid'] == 1419550 and controller['starttime_ticks'] == 114281139 and controller['uid'] == 1000 and
            materializer['pid'] == materializer['pgrp'] == 1421344 and materializer['ppid'] == controller['pid'] and
            materializer['starttime_ticks'] == 114282777 and materializer['uid'] == 1000 and
            selected['pid'] == 1498263 and selected['starttime_ticks'] == 114579899 and
            selected['ppid'] == materializer['pid'] and selected['comm'] == 'git' and selected['uid'] == 1000 and
            controller['cgroup'] == materializer['cgroup'] == selected['cgroup'] and
            controller['cgroup'].rstrip().endswith('/hepta-runtime-job-1a1b9b64e12-12894-1641.service'),
            'boundary belongs to a different original controller, materializer or selected Git generation')
    runtime = boundary['runtime_admission']
    require(runtime['request_path'] == '/home/alex/.local/state/hepta-runtime-mac-worker/jobs/1a1b9b64e12-12894-1641/request.json' and
            runtime['request_sha256'] == '0a4cd9edfba49477d7b3409756a8d3cafee467818820e40957b1998203213ed5' and
            runtime['unit']['ActiveState'] == 'active' and
            runtime['unit']['ExecMainStartTimestampMonotonic'] == '1142811347283' and
            runtime['watch_seconds'] == boundary['git_completion_watch_seconds'] == 1200 and
            runtime['reserved_after_watch_seconds'] == 200 and runtime['remaining_seconds'] > 1400 and
            runtime['original_deadline_changed'] is False,
            'boundary must preserve the actual original runtime deadline and its finite watch budget')
    fixed_lock = {'path': str(CANDIDATE_ROOT/'builder-source-r4/android/native-generation-pair/source-lock.json'),
                  'bytes': 348102, 'sha256': '2b699174977614e080cf99a991f3e648774b24581c4ecdc29f1bd53b7b01ef23'}
    fixed_cli = {'path': str(CANDIDATE_ROOT/'bin-r4/droidloom-source'), 'bytes': 1501880,
                 'sha256': '9fd7276af58c56b2a970c5586aad792dbfca29ced9a1eab4dea19bec135f5a86'}
    fixed_controller = {'path': str(CANDIDATE_ROOT/'normal-reconcile-r2/controller.py'), 'bytes': 13855,
                        'sha256': '786a751fab5897cf39f9abb1be4263aa345ae6ad9d512014909a29e1a1385ca7'}
    require(failed['frozen_lock'] == preparation['frozen_lock'] == fixed_lock and
            failed['binary'] == preparation['binary'] == fixed_cli and failed['controller'] == fixed_controller and
            failed['previous_lock'] == preparation['previous_lock'] == preparation['original_268_lock']
                == historical_preparation['lock'] and
            failed['previous_manifest'] == preparation['original_268_materialized_manifest'] and
            failed['previous_manifest']['bytes'] == preparation['previous_manifest']['bytes']
                == historical_binding['source_manifest']['bytes'] and
            failed['previous_manifest']['sha256'] == preparation['previous_manifest']['sha256']
                == historical_binding['source_manifest']['sha256'] and
            materializer['exe_sha256'] == fixed_cli['sha256'],
            'preserved original268 and frozen597 normal recovery source chain differs')
    for reference in (fixed_lock, fixed_cli, fixed_controller, failed['previous_lock']):
        read(reference, P(reference['path']), 4 * 1024 * 1024)
    old_manifest, _ = read(failed['previous_manifest'],
        CANDIDATE_ROOT/'normal-reconcile-r2/previous-materialized-manifest.json', 1024 * 1024, True)
    old_lock, _ = json_pin(P(failed['previous_lock']['path']), failed['previous_lock']['sha256'], failed['previous_lock']['bytes'])
    expected = expected_published_manifest(old_lock)
    expected['source_lock_sha256'] = failed['previous_lock']['sha256']
    require(old_manifest == expected and len(old_manifest['plan']['projects']) == 268 and
            len(old_manifest['plan']['links']) == 8,
            'partial recovery must retain the exact original published268 authority')
    earlier = {'path': str(CANDIDATE_ROOT/'normal-reconcile-r1/result.json'), 'bytes': 7687,
               'sha256': '0a6bdd5373f84cac937b4dbd89ab8e0542dcce131151fc356ba61477d7d4b191'}
    require(failed['resumed_from_failed_original'] == preparation['earlier_failed_original'] == earlier,
            'earlier failed source attempt was removed from the history')
    read(earlier, P(earlier['path']), 65536)
    require(len(failed['steps']) == 1, 'only the completed old268 verification may precede the partial stop')
    step = failed['steps'][0]
    require(step['label'] == 'verify_previous' and type(step['exit_code']) is int and step['exit_code'] == 0 and
            step['argv'] == [fixed_cli['path'], 'verify-materialized', '--lock', failed['previous_lock']['path'],
                             '--output', str(ACTIVE_SOURCE)],
            'historical old268 verification failed or changed')
    for stream in ('stdout', 'stderr'):
        read(step[stream], CANDIDATE_ROOT/'normal-reconcile-r2'/('verify_previous.' + stream), 1024 * 1024)
    partial_logs = preparation['preserved_incomplete_step_logs']
    require(type(partial_logs) is dict and set(partial_logs) == {'stdout', 'stderr'},
            'actual incomplete r2 normal-command logs must remain in the history')
    for stream in ('stdout', 'stderr'):
        read(partial_logs[stream], CANDIDATE_ROOT/'normal-reconcile-r2'/('normal_reconcile.' + stream),
             1024 * 1024)
    boundary_source = {'path': str(CANDIDATE_ROOT/'boundary_stop_current_reconcile_r2.r1.py'),
                       'bytes': 17963,
                       'sha256': 'e48fc45df8eb3b5eb8d5841f9a15661fc23b0240ee57edc32ffbd4609d205d84'}
    read(boundary_source, P(boundary_source['path']), 65536)
    current_runtime = preparation['outer_runtime_admission']
    job = current_runtime['job_id']
    require(type(job) is str and 0 < len(job) <= 64 and all(c in '0123456789abcdef-' for c in job),
            'actual new source H job identity required')
    job_root = P('/home/alex/.local/state/hepta-runtime-mac-worker/jobs')/job
    request, _ = read(current_runtime['request'], job_root/'request.json', 65536, True)
    runner_ref = current_runtime['runner']
    require(runner_ref['bytes'] == 40463 and
            runner_ref['sha256'] == '65564ce756f3a341def2cf34b2c0d54ef3e75960923c6002c4c56db13564ebf1',
            'actual reviewed longer-source runtime implementation differs')
    read(runner_ref, job_root/'runner.py', 65536)
    require(request['job_id'] == job and request['unit'] == 'hepta-runtime-job-' + job and
            request['execution_mode'] == 'operator' and request['timeout_seconds'] == 23000 and
            current_runtime['timeout_seconds'] == 23000 and current_runtime['planned_normal_work_seconds'] == 21600 and
            current_runtime['unit']['ActiveState'] == 'active' and current_runtime['unit']['RuntimeMaxUSec'] == 'infinity' and
            current_runtime['unit']['ExecMainStartTimestampMonotonic'].isdigit() and
            22800 < current_runtime['remaining_from_earlier_unit_start_seconds'] <= 23000 and
            current_runtime['remaining_time_review_before_reserved_interval_required'] is True and
            current_runtime['active_r2_runtime_was_not_changed'] is True,
            'actual new source job must retain its reviewed fixed longer budget')
    return {'qualification_scope': preparation['qualification_scope'], 'resource_history_clear': False,
            'failed_materialization': failed_pin, 'failed_H_terminal': terminal_pin,
            'natural_boundary_retirement': boundary_pin, 'boundary_H_terminal': boundary_terminal_pin,
            'actual_source_job_id': job, 'preserved_resource_events': events, 'authority_pins': authorities}



def source_resume_predecessor(preparation, historical_binding, historical_preparation):
    """Consume the actual R8 success while replaying its exact failed history."""
    import ast
    root = CANDIDATE_ROOT / 'normal-reconcile-r8-observed-admission-recovery-host'
    physical_root = CANDIDATE_ROOT / 'normal-reconcile-r8-success-retirement-observation-host-r1'
    job = '1a1bb6057d2-13c47-22d'
    authorities = {}

    def read(reference, expected_path, maximum, document=False, exact=None):
        require(type(reference) is dict and set(reference) == {'path', 'bytes', 'sha256'} and
                reference['path'] == str(expected_path) and type(reference['bytes']) is int and
                0 <= reference['bytes'] <= maximum,
                'exact bounded R8 authority reference required')
        if exact is not None:
            require((reference['bytes'], reference['sha256']) == exact, 'actual R8 authority differs')
        row, raw = held_file(expected_path, maximum, True)
        require(row['bytes'] == reference['bytes'] and row['sha256'] == reference['sha256'] and
                expected_path.lstat().st_nlink == 1, 'R8 authority bytes or link count changed')
        if row['path'] in authorities:
            require(authorities[row['path']] == row, 'R8 authority identity changed during verification')
        authorities[row['path']] = row
        return (json.loads(raw) if document else raw), row

    actual_ref = {'path': str(root / 'result.json'), 'bytes': 68810,
                  'sha256': '1d89dcaa0267cebeb30989428802af8cd4117b4629cbebf985a6d0eb5519755b'}
    actual, actual_pin = read(actual_ref, root / 'result.json', 131072, True)
    require(preparation == actual and preparation['schema'] == 'normal-peer-promisor-recovery-v1' and
            preparation['qualification_scope'] ==
                'exact_268_to_597_after_preserved_complete_promisor_timeout_and_earlier_failures' and
            preparation['state'] == 'NORMAL_EXACT_597_MATERIALIZATION_VERIFIED' and
            preparation['normal_materialization_qualified'] is True and preparation['errors'] == [] and
            preparation['resource_history_clear'] is False and preparation['Soong_invocations'] == 0 and
            preparation['native_pair_artifact_qualified'] is False and preparation['runtime_qualified'] is False,
            'only the actual complete R8 source success may qualify the full builder')
    terminal_ref = {'path': str(root / 'h-terminal.json'), 'bytes': 731,
                    'sha256': '2e51c1181c22cfeb1e371c3e5c9a4d72ecd7e3a3acbf257d5e8c92b57b8c3b8a'}
    terminal, terminal_pin = read(terminal_ref, root / 'h-terminal.json', 65536, True)
    pair_terminal_contract(terminal, job, True)
    controller_ref = {'path': str(root / 'controller.py'), 'bytes': 95391,
                      'sha256': '2db96fab3eb777c9569860557e654cb3ad1b15ec1f97e00ad44d6eda174d09c6'}
    require(preparation['controller'] == controller_ref, 'actual reviewed R8 controller required')
    controller, controller_pin = read(controller_ref, root / 'controller.py', 131072)
    launch_path = CANDIDATE_ROOT / 'normal_source_recover_peer597.host-r8.py'
    read(dict(controller_ref, path=str(launch_path)), launch_path, 131072)
    claim_ref = {'path': str(root / 'claim.json'), 'bytes': 43953,
                 'sha256': '6b298ea7247309b15ca8b79f6a07d4b34d8ad1e746ec7bd201d0e0b5af2bb95d'}
    claim, claim_pin = read(claim_ref, root / 'claim.json', 131072, True)
    require(claim['state'] == 'NORMAL_RECONCILE_STARTED' and claim['normal_materialization_qualified'] is False and
            len(claim['resource_observations']) == 1 and
            preparation['resource_observations'][:1] == claim['resource_observations'] and
            all(preparation[key] == value for key, value in claim.items()
                if key not in ('state', 'normal_materialization_qualified', 'resource_observations')),
            'actual R8 claim and all preserved failed authorities survive unchanged')

    # Load only the pinned controller's existing read-only history predicates.
    # No main, run, save, lock acquisition, subprocess, reaper or signal function
    # is compiled into this scope. Its exact held reads are recorded as inputs.
    names = {'need', 'sha', 'read_exact_pin', 'read_document', 'qualify_h_terminal',
             'qualify_partial_predecessor', 'qualify_network_predecessor', 'qualify_r4_predecessor',
             'short_reference', 'qualify_peer_predecessor', 'qualify_latest_transport_predecessor',
             'qualify_preserved_r7_admission_rejection', 'qualify_recovery_prerequisites',
             'file_identity', 'frozen_source_snapshot'}
    tree = ast.parse(controller)
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    require({node.name for node in definitions} == names, 'exact read-only history function set')
    constants = [node for node in tree.body if isinstance(node, ast.Assign) and node.lineno < 122 and
                 all(isinstance(target, ast.Name) and target.id.isupper() for target in node.targets)]
    scope = {'__name__': 'actual_native_r8_readonly_history', 'pathlib': pathlib,
             'os': os, 'stat': stat, 'json': json, 'hashlib': hashlib}
    exec(compile(ast.Module(body=constants + definitions, type_ignores=[]), str(root / 'controller.py'), 'exec'), scope)
    require(scope['C'] == CANDIDATE_ROOT and scope['R'] == ROOT and scope['SOURCE'] == ACTIVE_SOURCE and
            scope['NEW_LOCK'] == BUILD_SOURCE / 'android/native-generation-pair/source-lock.json' and
            scope['NEW_SHA'] == '2b699174977614e080cf99a991f3e648774b24581c4ecdc29f1bd53b7b01ef23',
            'reused history functions retain their exact original domain')
    original_read = scope['read_exact_pin']
    def tracked_read(reference, expected_path, maximum, allow_empty=False):
        raw = original_read(reference, expected_path, maximum, allow_empty=allow_empty)
        observed, _ = read(reference, expected_path, maximum)
        require(observed == raw, 'history held bytes changed between exact observations')
        return raw
    scope['read_exact_pin'] = tracked_read
    document = scope['read_document']
    r2 = document(scope['R2_RESULT_PIN'])
    scope['qualify_partial_predecessor'](r2, document(scope['R2_H_TERMINAL_PIN']),
        document(scope['BOUNDARY_RESULT_PIN']), document(scope['BOUNDARY_H_TERMINAL_PIN']))
    r3 = document(scope['R3_RESULT_PIN'])
    scope['qualify_network_predecessor'](r3, document(scope['R3_H_TERMINAL_PIN']),
        document(scope['R3_RETIREMENT_PIN']), document(scope['R3_RETIREMENT_H_PIN']))
    r4 = document(scope['R4_RESULT_PIN'])
    scope['qualify_r4_predecessor'](r4, document(scope['R4_H_TERMINAL_PIN']),
        document(scope['R4_RETIREMENT_PIN']), document(scope['R4_RETIREMENT_H_PIN']), r3, r2)
    peer = document(scope['PEER_RESULT_PIN'], 4 * 1024 * 1024)
    scope['qualify_peer_predecessor'](peer, document(scope['PEER_H_PIN']),
        document(scope['PEER_PHYSICAL_PIN']), document(scope['PEER_PHYSICAL_H_PIN']), r4, r2)
    latest = document(scope['LATEST_RESULT_PIN'], 4 * 1024 * 1024)
    scope['qualify_latest_transport_predecessor'](latest, document(scope['LATEST_H_PIN']),
        document(scope['LATEST_PHYSICAL_PIN']), document(scope['LATEST_PHYSICAL_H_PIN']), peer, r4, r2)
    require(preparation['preserved_rejected_admission_r7'] == scope['qualify_preserved_r7_admission_rejection']() and
            preparation['recovery_prerequisites'] == scope['qualify_recovery_prerequisites'](),
            'actual rejected admissions and MemoryHigh evidence remain separate from source success')
    earlier_history = partial_recovery_predecessor(r3, historical_binding, historical_preparation)
    for row in earlier_history['authority_pins']:
        if row['path'] in authorities:
            require(authorities[row['path']] == row, 'retained original268 authority identity changed')
        authorities[row['path']] = row
    require(preparation['original_268_lock'] == r2['previous_lock'] and
            preparation['original_268_materialized_manifest'] == r2['previous_manifest'] and
            preparation['observed_r4_original_268_manifest_reference'] == r4['original_268_materialized_manifest'] and
            preparation['resumed_from_failed_original'] == scope['LATEST_RESULT_PIN'] and
            preparation['earlier_peer_failure'] == scope['PEER_RESULT_PIN'] and
            preparation['earlier_r4_failure'] == scope['R4_RESULT_PIN'] and
            preparation['earlier_r3_failure'] == scope['R3_RESULT_PIN'] and
            preparation['earlier_r2_failure'] == scope['R2_RESULT_PIN'] and
            preparation['preserved_prior_resources'] == latest['resources'] and
            preparation['earlier_peer_resources'] == peer['resources'] and
            preparation['earlier_r4_resources'] == r4['resources'] and
            preparation['earlier_r3_resources'] == r3['resources'] and
            preparation['earlier_r2_resource_events'] == r2['resources'],
            'all actual source failures, raw nonzero statuses and resource events remain preserved')
    old_manifest, _ = read(preparation['previous_manifest'], root / 'previous-materialized-manifest.json', 1048576, True)
    require(preparation['previous_lock'] == r2['previous_lock'] and
            all(preparation['previous_manifest'][key] == historical_binding['source_manifest'][key]
                for key in ('bytes', 'sha256')),
            'R8 starts from the actual retained original268 publication')
    old_lock, _ = read(preparation['previous_lock'], scope['OLD_LOCK'], 1048576, True)
    expected_old = expected_published_manifest(old_lock)
    expected_old['source_lock_sha256'] = scope['OLD_SHA']
    require(old_manifest == expected_old, 'actual R8 previous manifest is the exact original268 plan')

    runtime = preparation['outer_runtime_admission']
    require(runtime['job_id'] == job, 'source result and actual durable H job must match')
    job_root = P('/home/alex/.local/state/hepta-runtime-mac-worker/jobs') / job
    request, _ = read(runtime['request'], job_root / 'request.json', 65536, True,
        (1142, '9e590478362bec33c46bc814c8241ad3142cfc65f0dbc1d2ca1a53b469fa08bf'))
    read(runtime['runner'], job_root / 'runner.py', 65536, exact=
        (40463, '65564ce756f3a341def2cf34b2c0d54ef3e75960923c6002c4c56db13564ebf1'))
    require(request['job_id'] == job and request['unit'] == 'hepta-runtime-job-' + job and
            request['execution_mode'] == 'operator' and request['executable'] == '/usr/bin/python3' and
            request['args'] == [str(launch_path), controller_ref['sha256'], scope['LATEST_RESULT_PIN']['sha256']] and
            request['timeout_seconds'] == runtime['timeout_seconds'] == 23000 and
            request['cpu_quota_percent'] == 200 and request['memory_max_bytes'] == 3221225472 and request['nice'] == 10 and
            runtime['planned_normal_work_seconds'] == 21600 and
            22800 < runtime['remaining_from_earlier_unit_start_seconds'] <= 23000 and
            runtime['unit']['ActiveState'] == 'active' and runtime['unit']['RuntimeMaxUSec'] == 'infinity' and
            runtime['unit']['ExecMainStartTimestampMonotonic'].isdigit() and
            runtime['remaining_time_review_before_reserved_interval_required'] is True and
            runtime['active_r2_runtime_was_not_changed'] is True, 'actual successful R8 fixed execution budget')
    require(all(preparation[key] is True for key in ('owned_retirement_qualified', 'owned_children_empty_after_retirement',
            'subreaper_restored', 'source_locks_released', 'normal_command_logs_complete',
            'complete_frozen_source_before_after_qualified', 'native_projection_absent_after_normal_recovery')) and
            len(preparation['retirement']) == preparation['incremental_reaped_count'] == 48 and
            all(type(row['wait_status']) is int and row['wait_status'] == 0 for row in preparation['retirement']),
            'actual R8 all48 zero statuses and complete source lifecycle')
    contract = {'method': 'direct_regular_files', 'pipe_EOF_observation_applicable': False,
        'all_three_commands_exit_zero': True, 'all_owned_writers_retired': True,
        'all_adopted_exit_statuses_zero': True,
        'fsynced_closed_file_hashes_and_identities_unchanged_after_retirement': True,
        'partial_pipe_capture_receipts_relabelled': False}
    require(preparation['normal_output_capture_contract'] == contract,
            'direct regular source logs must not be relabelled as pipe EOF')
    require([row['label'] for row in preparation['steps']] == ['verify_previous', 'normal_reconcile', 'verify_reconciled'],
            'three exact ordinary materializer commands')
    for row, verb, lock in zip(preparation['steps'], ('verify-materialized', 'reconcile', 'verify-materialized'),
                              (scope['OLD_LOCK'], scope['NEW_LOCK'], scope['NEW_LOCK'])):
        require(type(row['exit_code']) is int and row['exit_code'] == 0 and row['argv'] ==
                [str(scope['BUILDER']), verb, '--lock', str(lock), '--output', str(ACTIVE_SOURCE)],
                'actual R8 ordinary command failed or changed')
        for stream in ('stdout', 'stderr'):
            path = root / (row['label'] + '.' + stream)
            original_read(row[stream], path, 1048576, allow_empty=True)
            read(row[stream], path, 1048576)
            require(scope['file_identity'](path.lstat()) == preparation['completed_log_identities'][row['label']][stream],
                    'actual completed source log file identity changed after owned writers retired')
    phases = ['initial_admission', 'before_verify_previous', 'after_verify_previous', 'after_normal_reconcile',
              'after_verify_reconciled', 'after_owned_retirement']
    require([row['phase'] for row in preparation['resource_observations']] == phases, 'all actual source resource phases retained')
    for values in [row['values'] for row in preparation['resource_observations']] + [preparation['resources']]:
        pairs = [line.split() for line in values['memory.events'].splitlines()]
        events = dict(pairs)
        require(len(events) == len(pairs) and values['cpu.max'] == '200000 100000' and
                values['memory.high'] == '2147483648' and values['memory.max'] == '3221225472' and
                values['memory.swap.max'] == values['memory.swap.current'] == '0' and
                all(events.get(key) == '0' for key in ('max', 'oom', 'oom_kill', 'oom_group_kill')),
                'new source success requires its actual strict high2/max3/zero-hard-event budget')
    require(preparation['resources']['memory.peak'] == '1814171648', 'actual successful source peak remains recorded')
    before_map, before_pin = read(preparation['complete_frozen_source_before'], root / 'frozen-builder-before.json',
        1048576, True, (106708, 'f2a52a64ae686e70c44061d481f7ce61ff4c0873339a8d6bb5a21b74c192bb9b'))
    after_map, after_pin = read(preparation['complete_frozen_source_after'], root / 'frozen-builder-after.json',
        1048576, True, (106708, 'f2a52a64ae686e70c44061d481f7ce61ff4c0873339a8d6bb5a21b74c192bb9b'))
    # Validate all515 current identities and bytes, without copying 515 duplicate
    # file-pin rows into the full-build terminal. The complete immutable map is
    # already retained and the existing final builder proof also checks it.
    scope['read_exact_pin'] = original_read
    current_map = scope['frozen_source_snapshot']()
    scope['read_exact_pin'] = tracked_read
    require(before_map == after_map == current_map and before_map['file_count'] == 515,
            'all515 frozen builder source identities and bytes must remain exact')
    read(scope['FROZEN_MAP_PIN'], P(scope['FROZEN_MAP_PIN']['path']), 1048576)
    manifest, manifest_pin = read(preparation['materialized_manifest_snapshot'], root / 'materialized-manifest.json',
        1048576, True, (386397, 'f92b8096e7df2ea7eeff112be9817e0744cf1a829d28a655c0415d0087232807'))
    frozen, _ = read(preparation['frozen_lock'], scope['NEW_LOCK'], 1048576, True,
        (348102, '2b699174977614e080cf99a991f3e648774b24581c4ecdc29f1bd53b7b01ef23'))
    expected = expected_published_manifest(frozen)
    expected['source_lock_sha256'] = scope['NEW_SHA']
    require(manifest == expected and len(manifest['plan']['projects']) == 597 and len(manifest['plan']['links']) == 8 and
            preparation['materialized_manifest'] == {'path': str(ACTIVE_SOURCE / '.droidloom-source-manifest.json'),
                'bytes': 386397, 'sha256': 'f92b8096e7df2ea7eeff112be9817e0744cf1a829d28a655c0415d0087232807'},
            'actual immutable597 normal manifest and exact live content reference')

    physical_ref = {'path': str(physical_root / 'result.json'), 'bytes': 27226,
                    'sha256': 'd56da1d3238b36dfaddb188fb93443b521726669bde18e2ec9742d9b7d231eea'}
    physical, physical_pin = read(physical_ref, physical_root / 'result.json', 65536, True)
    physical_h_ref = {'path': str(physical_root / 'h-terminal.json'), 'bytes': 732,
                      'sha256': '0db3b7eb3658c4d608189e0519c5a9780fd5999feda218419ee57c0bdb5d0eff'}
    physical_h, physical_h_pin = read(physical_h_ref, physical_root / 'h-terminal.json', 65536, True)
    pair_terminal_contract(physical_h, '1a1bb759de9-13c47-284', True)
    read(physical['observer_source'], physical_root / 'controller.py', 65536,
        exact=(18187, '72962954a6368adf387a8c846d4d25511efa593d630ec7a131a285a78f1ee36e'))
    work_paths = [work / name for work in (ROOT / 'work', ROOT.parent / 'framework/work',
        P('/home/alex/work/pocket4-audio-source-build-20261108-r1/work'))
        for name in ('package-build.lock', 'aosp-source-update.lock')]
    require(physical['schema'] == 'native-r8-exact597-success-physical-observation-v1' and
            physical['job_id'] == job and physical['actual_source_result'] == actual_ref and
            physical['actual_source_H_terminal'] == terminal_ref and physical['actual_source_controller'] == controller_ref and
            physical['passed'] is True and physical['errors'] == [] and physical['physical_runtime_and_six_locks_clear'] is True and
            physical['normal_materialization_qualified_by_original'] is True and physical['original_cgroup_absent'] is True and
            physical['other_source_or_build_owners'] == [] and physical['full515_source_unchanged'] is True and
            physical['actual_normal_commands'] == preparation['steps'] and physical['actual_adopted_statuses'] == preparation['retirement'] and
            physical['original_source_resources'] == preparation['resources'] and physical['original_source_output_contract'] == contract and
            physical['immutable_manifest_snapshot'] == preparation['materialized_manifest_snapshot'] and
            physical['current_manifest'] == preparation['materialized_manifest'] and
            physical['current_manifest_projects'] == 597 and physical['current_manifest_links'] == 8 and
            physical['current_manifest_source_lock_sha256'] == scope['NEW_SHA'] and physical['resource_history_clear'] is False and
            all(physical[key] == 0 for key in ('source_or_Git_writes', 'source_CLI_invocations', 'process_signals', 'Soong_invocations')) and
            physical['global_heavy_admission_granted'] is False,
            'independent actual R8 physical observation must not grant later global admission')
    require(physical['original_unit'] == {'ActiveState': 'inactive', 'ControlGroup': '', 'ControlPID': '0',
                'LoadState': 'not-found', 'MainPID': '0', 'SubState': 'dead'} and
            [row['path'] for row in physical['six_locks_simultaneously_held_for_observation']] == [str(path) for path in work_paths] and
            all(row['observed_free'] is True for row in physical['six_locks_simultaneously_held_for_observation']) and
            len({tuple(row['identity'][:2]) for row in physical['six_locks_simultaneously_held_for_observation']}) == 6 and
            len(physical['observation_lock_descriptors_released']) == 6 and
            all(row['closed'] is True for row in physical['observation_lock_descriptors_released']) and
            {tuple(row['identity_before_release']) for row in physical['observation_lock_descriptors_released']} ==
                {tuple(row['identity']) for row in physical['six_locks_simultaneously_held_for_observation']} and
            len(physical['projection_journals']) == 3 and all(row['absent'] is True for row in physical['projection_journals']),
            'actual six distinct observation locks, original unit and descriptor retirement')
    physical_map, _ = read(physical['current_frozen_source'], physical_root / 'frozen-builder-current.json', 1048576, True,
        (106708, 'f2a52a64ae686e70c44061d481f7ce61ff4c0873339a8d6bb5a21b74c192bb9b'))
    require(physical_map == current_map, 'independent and current515 source maps remain identical')
    read(actual_ref, root / 'result.json', 131072)
    read(terminal_ref, root / 'h-terminal.json', 65536)
    return {'qualification_scope': preparation['qualification_scope'], 'resource_history_clear': False,
        'actual_source_job_id': job, 'actual_source_result': actual_pin, 'actual_source_terminal': terminal_pin,
        'actual_source_controller': controller_pin, 'actual_source_claim': claim_pin,
        'source_output_capture_contract': contract, 'all48_adopted_statuses_zero': True,
        'current_source_resource_events': preparation['resources']['memory.events'],
        'historical_resource_events_preserved': {name: value['resources']['memory.events']
            for name, value in (('R2', r2), ('R3', r3), ('R4', r4), ('peer1ba2', peer), ('peer1f0d', latest))},
        'earlier_partial_recovery_history': earlier_history,
        'current_full515_equals_original_source_before_and_after': True,
        'complete_source_before': before_pin, 'complete_source_after': after_pin,
        'immutable597_manifest_snapshot': manifest_pin,
        'live_manifest_inode_is_not_an_immutable_history_authority': True,
        'independent_physical_retirement': physical_pin, 'independent_physical_terminal': physical_h_pin,
        'authority_pins': [authorities[path] for path in sorted(authorities)]}





def observe_active_inputs(context, first):
    scope = context['inventory_scope']
    report = {'state': 'VERIFYING', 'first_error': None, 'secondary_errors': []}
    state = {'report': report, 'deadline': time.monotonic() + 90, 'bytes_read': 0, 'bytes_copied': 0,
             'directories': {}, 'early_close_errors': [], 'created_directories': set()}
    observations = {}
    failure = None
    try:
        historical_binding, historical_binding_pin, historical_preparation, historical_preparation_pin = \
            historical_active_materialization()
        binding, binding_pin = json_pin(ACTIVE_BINDING, ACTIVE_BINDING_SHA, ACTIVE_BINDING_BYTES)
        require(binding['schema'] == 'pocket4-native597-active-work-binding-v1' and
                binding['work'] == str(ACTIVE_WORK) and binding['source'] == str(ACTIVE_SOURCE) and
                binding['historical_268_binding'] == {
                    'path': historical_binding_pin['path'], 'bytes': historical_binding_pin['bytes'],
                    'sha256': historical_binding_pin['sha256']} and
                binding['historical_268_materialization'] == {
                    'path': historical_preparation_pin['path'], 'bytes': historical_preparation_pin['bytes'],
                    'sha256': historical_preparation_pin['sha256']},
                'final native597 work or retained historical authority differs')
        for key in ('source_copy', 'normal_build_assets', 'source_extension', 'companion_roots'):
            require(binding[key] == historical_binding[key],
                    'retained original normal input authority differs: ' + key)
        require(all(binding['roots'][key][:5] == historical_binding['roots'][key][:5]
                    for key in ('work', 'source')), 'original active work or source root was replaced')
        preparation, preparation_pin = json_pin(ACTIVE_PREPARATION, ACTIVE_PREPARATION_SHA, ACTIVE_PREPARATION_BYTES)
        require(preparation['state'] == 'NORMAL_EXACT_597_MATERIALIZATION_VERIFIED' and
                preparation['normal_materialization_qualified'] is True and
                preparation['owned_retirement_qualified'] is True and
                preparation['source_locks_released'] is True and preparation['errors'] == [] and
                preparation['Soong_invocations'] == 0 and preparation['runtime_qualified'] is False and
                preparation['native_pair_artifact_qualified'] is False and
                preparation['frozen_lock'] == binding['materialization_lock'] and
                preparation['frozen_lock']['sha256'] == ACTIVE_LOCK_SHA and
                preparation['frozen_lock']['bytes'] == ACTIVE_LOCK_BYTES and
                preparation['materialized_manifest'] == binding['source_manifest'] and
                binding['normal_materialization'] == {
                    'path': str(ACTIVE_PREPARATION), 'bytes': ACTIVE_PREPARATION_BYTES,
                    'sha256': ACTIVE_PREPARATION_SHA},
                'actual complete normal597 materialization or retirement proof differs')
        observations['source_resume_predecessor'] = source_resume_predecessor(
            preparation, historical_binding, historical_preparation)
        terminal_ref = binding['normal_materialization_terminal']
        terminal_pin, terminal_raw = held_file(terminal_ref['path'], 65536, True)
        require({key: terminal_pin[key] for key in ('path', 'bytes', 'sha256')} == terminal_ref,
                'actual complete-source H terminal changed')
        pair_terminal_contract(json.loads(terminal_raw),
            observations['source_resume_predecessor']['actual_source_job_id'], True)
        observations['actual_source_H_terminal'] = terminal_pin
        steps = preparation['steps']
        require(len(steps) == 3 and [row['label'] for row in steps] ==
                ['verify_previous', 'normal_reconcile', 'verify_reconciled'],
                'actual source command order differs')
        for command, verb, lock_path in zip(steps,
                ('verify-materialized', 'reconcile', 'verify-materialized'),
                (preparation['previous_lock']['path'], preparation['frozen_lock']['path'],
                 preparation['frozen_lock']['path'])):
            require(command['exit_code'] == 0 and command['argv'] == [
                    preparation['binary']['path'], verb, '--lock', lock_path, '--output', str(ACTIVE_SOURCE)],
                    'actual normal source command failed or changed')
            for key in ('stdout', 'stderr'):
                wanted = command[key]
                row, _ = held_file(wanted['path'], wanted['bytes'])
                require(row['bytes'] == wanted['bytes'] and row['sha256'] == wanted['sha256'],
                        'actual normal source command output changed')
        require(all(os.waitstatus_to_exitcode(row['wait_status']) == 0
                    for row in preparation['retirement']), 'nonzero source child status was suppressed')
        fields = preparation['resources']
        events = dict(line.split() for line in fields['memory.events'].splitlines())
        require(fields['cpu.max'] == '200000 100000' and fields['memory.max'] == '3221225472' and
                fields['memory.swap.max'] == fields['memory.swap.current'] == '0' and
                all(events[name] == '0' for name in ('max', 'oom', 'oom_kill', 'oom_group_kill')),
                'normal source materialization resource gate differs')
        for key in ('previous_manifest', 'materialized_manifest_snapshot', 'frozen_lock', 'controller'):
            wanted = preparation[key]
            row, _ = held_file(wanted['path'], wanted['bytes'])
            require(row['sha256'] == wanted['sha256'] and row['bytes'] == wanted['bytes'],
                    'normal source authority changed: ' + key)
        require(preparation['binary']['bytes'] == 1501880 and
                preparation['binary']['sha256'] ==
                    '9fd7276af58c56b2a970c5586aad792dbfca29ced9a1eab4dea19bec135f5a86',
                'normal materializer differs from the actual compiled source CLI')
        for key, wanted in [('source_copy', binding['source_copy']),
                            ('normal_build_assets', binding['normal_build_assets']),
                            ('source_extension', binding['source_extension'])]:
            row, _ = held_file(wanted['path'], wanted['bytes'])
            require(row['sha256'] == wanted['sha256'] and row['bytes'] == wanted['bytes'],
                    'active source authority changed: ' + key)
            observations[key] = row
        observations['binding'] = binding_pin
        observations['preparation'] = preparation_pin
        work_fd = scope['directory'](ACTIVE_WORK, state)
        source_fd = scope['directory'](ACTIVE_SOURCE, state)
        roots = {'work': scope['full_identity'](os.fstat(work_fd)),
                 'source': scope['full_identity'](os.fstat(source_fd))}
        for key, observed in roots.items():
            require(observed[:5] == binding['roots'][key][:5], 'active root identity/owner/mode differs')
        observations['roots'] = roots
        manifest, manifest_pin = json_pin(ACTIVE_SOURCE / '.droidloom-source-manifest.json',
            ACTIVE_MANIFEST_SHA, ACTIVE_MANIFEST_BYTES)
        lock, lock_pin = json_pin(ACTIVE_LOCK, ACTIVE_LOCK_SHA, ACTIVE_LOCK_BYTES)
        expected = expected_published_manifest(lock)
        expected['source_lock_sha256'] = ACTIVE_LOCK_SHA
        require(manifest == expected and len(manifest['plan']['projects']) == 597 and
                len(manifest['plan']['links']) == 8,
                'active manifest is not the exact normal 597-project materialization')
        observations['source_manifest'] = manifest_pin
        observations['source_lock'] = lock_pin
        cli = preparation['binary']
        cli_pin, _ = held_file(cli['path'], 64 * 1024 * 1024)
        require(cli_pin['bytes'] == cli['bytes'] and cli_pin['sha256'] == cli['sha256'],
                'actual normal materializer ELF changed')
        observations['source_cli'] = cli_pin
        assets = {}
        for asset in scope['ASSETS']:
            row, _ = held_file(ACTIVE_WORK / asset['destination'], asset['bytes'])
            require(row['bytes'] == asset['bytes'] and row['sha256'] == asset['sha256'] and
                    stat.S_IMODE(row['identity'][2]) == stat.S_IMODE(asset['identity'][2]),
                    'active normal fixed input differs: ' + asset['destination'])
            assets[asset['destination']] = row
        observations['fixed_assets'] = assets
        for key, relative in [('mesa-source_copied_content_manifest', 'mesa-source'),
                              ('python_copied_content_manifest', 'python')]:
            observed = scope['tree_inventory'](ACTIVE_WORK / relative, state)
            require(observed['files'] == context['manifests'][key]['files'] and
                    observed['held_root'][:5] == binding['companion_roots'][relative][:5],
                    'active complete companion file/path/mode map differs: ' + relative)
            observations[key] = {'root': str(ACTIVE_WORK / relative), 'held_root': observed['held_root'],
                'counts': observed['counts'], 'metadata_sha256': observed['metadata_sha256'],
                'complete_file_map_matched': True}
        preimages = {}
        for relative in ART_PATHS:
            path = ACTIVE_SOURCE / relative
            try:
                path.lstat()
            except FileNotFoundError:
                preimages[relative] = {'absent': True}
            else:
                row, _ = held_file(path, 1024 * 1024)
                preimages[relative] = {'bytes': row['bytes'], 'sha256': row['sha256'],
                                       'mode': stat.S_IMODE(row['identity'][2])}
        observations['ART_source_preimages'] = preimages
        require(not (ACTIVE_WORK / 'source-projection.json').exists() and
                not (ACTIVE_WORK / 'source-projection.json').is_symlink(),
                'active source projection journal not restored')
        if not first:
            before = context['initial_observations']['active_work']
            for key in ('binding', 'preparation', 'source_copy', 'normal_build_assets', 'source_extension',
                        'source_lock', 'source_cli', 'fixed_assets', 'ART_source_preimages',
                        'source_resume_predecessor', 'actual_source_H_terminal'):
                require(observations[key] == before[key], 'active immutable input or ART preimage changed: ' + key)
        return observations
    except BaseException as error:
        failure = error
        raise
    finally:
        close_errors = []
        for path, (descriptor, _) in reversed(list(state['directories'].items())):
            try:
                os.close(descriptor)
            except OSError as error:
                close_errors.append({'path': path, 'error': repr(error)})
        close_errors.extend(state['early_close_errors'])
        if (close_errors or report['first_error'] is not None) and failure is None:
            raise RuntimeError('active inventory did not qualify its directory retirement: ' + repr({
                'first_error': report['first_error'], 'close_errors': close_errors}))


def qualify_active_completed_manifest(document, lock):
    expected = expected_published_manifest(lock)
    expected['source_lock_sha256'] = ACTIVE_LOCK_SHA
    require(document == expected and len(document['plan']['projects']) == 597 and
            len(document['plan']['links']) == 8,
            'normal completed manifest is not the exact final 597-project source plan')


def observe_inputs(context, first):
    observations = observe_prepared_inputs(context, first)
    preimages = {}
    for relative in ART_PATHS:
        path = PUBLISHED_SOURCE/relative
        try:
            path.lstat()
        except FileNotFoundError:
            preimages[relative] = {'absent': True}
        else:
            row, _ = held_file(path, 1024*1024)
            preimages[relative] = {'bytes': row['bytes'], 'sha256': row['sha256'],
                                   'mode': stat.S_IMODE(row['identity'][2])}
    if not first:
        require(preimages == context['initial_observations']['ART_source_preimages'],
                'paired ART projection did not restore all ten original input states')
    observations['ART_source_preimages'] = preimages
    observations['active_work'] = observe_active_inputs(context, first)
    return observations


def plan():
    return {'schema': 1, 'state': 'PLAN_ORDINARY_ENGINE_AND_WHOLE_ART_PAIR_OFFLINE',
        'root': str(ROOT), 'work': str(ACTIVE_WORK), 'aosp_source': str(ACTIVE_SOURCE), 'out': str(OUT),
        'builder_result_sha256': FINAL_BUILDER_RECOVERY_SHA, 'prior_pair_validation_sha256': BUILD_RESULT_SHA,
        'original_work_preparation_sha256': PREPARATION_SHA, 'active_work_preparation_sha256': ACTIVE_PREPARATION_SHA, 'active_source_lock_sha256': ACTIVE_LOCK_SHA,
        'builder_sha256': BUILDER_SHA, 'builder_source_manifest_sha256': FINAL_BUILDER_SOURCE_MANIFEST_SHA,
        'builder_source_files': 515, 'retained_historical_exact_pair_controls': 27,
        'actual_final_visibility_controls': 17, 'actual_r3_frozen_pair_controls': 11,
        'actual_final_normal_release_job': '1a1b9755c3b-12894-146a',
        'normal_build_timeout_seconds': 21600,
        'outer_runtime_timeout_seconds': 23000,
        'actual_outer_runtime_admission_required': True,
        'post_preflight_runtime_admission_required': True,
        'post_preflight_runtime_margin_seconds': 1200,
        'post_preflight_runtime_admission_receipt': str(ROOT/'runtime-admission-native597-8gib-hostreserve5-20261108-r1.json'),
        'preserved_prior_compile_job_failed': '1a1b420093f-fc05-8664',
        'historical_validation_job': '1a1b4294c28-fc05-8688',
        'argv': [str(BUILDER), '--source', str(BUILD_SOURCE), '--jobs', '2',
                 'native-generation-build', '--work', str(ACTIVE_WORK), '--out', str(OUT)],
        'targets': TARGETS, 'dependency_mode': 'Strict', 'ALLOW_MISSING_DEPENDENCIES': False,
        'source_materialization': 'full normal qualification of exact 597 projects and eight links',
        'source_qualification_scope': 'exact_268_to_597_after_preserved_complete_promisor_timeout_and_earlier_failures',
        'actual_source_job': '1a1bb6057d2-13c47-22d',
        'source_resource_history_clear': False,
        'historical_partial_recovery_scope': 'exact_268_to_597_after_preserved_r2_partial_boundary_failure',
        'historical_partial_recovery_failed_source_job': '1a1b9b64e12-12894-1641',
        'published_source_manifest_sha256': ACTIVE_MANIFEST_SHA,
        'normal_lock_paths': [str(ACTIVE_WORK/'package-build.lock'), str(ACTIVE_WORK/'aosp-source-update.lock')],
        'normal_package_and_source_locks': True, 'normal_projection_journal_and_recovery': True,
        'normal_ART_preimages_required_restored': list(ART_PATHS),
        'complete_engine_snapshot_files': 926, 'old_shared_AOSP_source_modified': False,
        'resource_profile_id': RESOURCE_PROFILE_ID,
        'memory_max_bytes': MEMORY_MAX, 'memory_swap_max_bytes': SWAP_MAX,
        'fresh_MemAvailable_min_bytes': MIN_AVAILABLE, 'global_swap_free_recorded_only': True,
        'owned_swap_current_required_bytes': 0, 'resource_admission_receipt': str(ROOT/'resource-admission-native597-8gib-hostreserve5-20261108-r1.json'),
        'admission_difference_bytes': MIN_AVAILABLE-MEMORY_MAX,
        'cpu_quota_percent': 200, 'jobs': 2,
        'inherited_actual_cpu_reservation': 'DROIDLOOM_COMPILER_CPUS_RESERVED=1', 'nice': 10, 'builder_wait_seconds': 21600,
        'automatic_retry': False, 'Main_actions': 0, 'Android_actions': 0,
        'private_AppZygote_role_authorized': False, 'runtime_authorization_enabled': False,
        'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
        'strict_dependency_failure_not_suppressed': True,
        'native_runtime_and_APEX_signatures_qualified': False}


def pair_contract_shape(pair):
    keys = {'schema', 'abi', 'protocol', 'host_abi', 'engine_sha256', 'art_apex_sha256',
            'libart_sha256', 'libnativebridge_sha256', 'apex_pubkey_sha256'}
    require(type(pair) is dict and set(pair) == keys and pair['schema'] == pair['abi'] == 1 and
            pair['protocol'] == 'DLOOMGE1-PROCMET2' and pair['host_abi'] == 'x86_64' and
            all(type(pair[name]) is str and len(pair[name]) == 64 and
                all(c in '0123456789abcdef' for c in pair[name]) for name in keys if name.endswith('_sha256')),
            'ordinary pair compiled component contract shape differs')



def pair_engine_marker(raw):
    marker = b'DROIDLOOM_NATIVE_GENERATION=1;ROLE=ENGINE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;\0'
    prefix = b'DROIDLOOM_NATIVE_GENERATION='
    require(len(raw) >= 20 and raw[:6] == b'\x7fELF\x02\x01' and
            int.from_bytes(raw[16:18], 'little') == 3 and int.from_bytes(raw[18:20], 'little') == 62,
            'ordinary pair engine is not an x86_64 shared ELF')
    offsets = []
    position = 0
    while True:
        position = raw.find(prefix, position)
        if position < 0:
            break
        offsets.append(position)
        require(raw.startswith(marker, position), 'ordinary pair engine contains foreign or disabled marker')
        position += len(prefix)
    require(offsets, 'ordinary pair engine lacks compiled enabled marker')

def completion_gate(context):
    records = {}
    for name in ('droidloom-native-generation-build-attempt.json',
                 'droidloom-native-generation-build-inputs.json',
                 'droidloom-native-generation-build-command.json'):
        row, raw = held_file(OUT/name, 8*1024*1024, True)
        records[name] = (json.loads(raw), row)
    attempt = records['droidloom-native-generation-build-attempt.json'][0]
    inputs = records['droidloom-native-generation-build-inputs.json'][0]
    command = records['droidloom-native-generation-build-command.json'][0]
    for document in (attempt, inputs, command):
        require(document['targets'] == TARGETS and document['dependency_mode'] == 'Strict' and
                document['private_AppZygote_role_authorized'] is False and
                document['installation_performed'] is False and document['runtime_qualified'] is False,
                'ordinary pair completion scope widened')
    require(attempt['state'] == 'CLAIMED_BEFORE_SOURCE_PROJECTION' and
            attempt['scope'] == inputs['scope'] == 'ordinary-app-complete-engine-art-pair' and
            attempt['source_lock_sha256'] == inputs['source_lock_sha256'] == ACTIVE_LOCK_SHA and
            attempt['engine_compiled_macro'] == attempt['ART_compiled_macro'] == 1 and
            inputs['selected_targets'] == TARGETS and
            inputs['full_translation_unit_qualification_verified'] is False and
            inputs['signature_and_payload_verification_complete'] is False and
            len(inputs['effective_engine_files']) == 926 and len(inputs['frozen_ART_inputs']) == 10,
            'ordinary pair fixed compiled source record differs')
    require(command['state'] == 'NORMAL_BUILD_SUCCEEDED_ACTUAL_PAIR_RECORDED' and
            command['source_projection_restored'] is True and
            command['full_translation_unit_qualification_verified'] is False and
            command['signature_and_payload_verification_complete'] is False,
            'ordinary pair normal completion record differs')
    require(not (ACTIVE_WORK/'source-projection.json').exists() and not (ACTIVE_WORK/'source-projection.json').is_symlink(),
            'ordinary pair source projection journal was not restored')
    pair = command['compiled_engine_ART_pair']
    pair_contract_shape(pair)
    product = OUT/'target/product/droidloom_x86_64'
    pair_row, pair_raw = held_file(product/'droidloom-native-generation-pair.json', 65536, True)
    require(json.loads(pair_raw) == pair, 'actual product pair contract differs')
    engine, raw = held_file(product/'system/lib64/libberberis_arm64.so', 64*1024*1024, True)
    apex, _ = held_file(product/'system/apex/com.android.art.apex', 512*1024*1024)
    require(engine['sha256'] == pair['engine_sha256'] and apex['sha256'] == pair['art_apex_sha256'],
            'actual enabled x86_64 engine or whole ART APEX differs')
    pair_engine_marker(raw)
    lock, _ = json_pin(ACTIVE_LOCK, ACTIVE_LOCK_SHA, ACTIVE_LOCK_BYTES)
    manifest_pin, raw = held_file(ACTIVE_SOURCE/'.droidloom-source-manifest.json', 1024*1024, True)
    qualify_active_completed_manifest(json.loads(raw), lock)
    native_bp, _ = held_file(ACTIVE_SOURCE/'prebuilts/misc/common/robolectric-native-prebuilt/Android.bp', 65536)
    require(native_bp['bytes'] == NATIVE_PREBUILT_BP_BYTES and native_bp['sha256'] == NATIVE_PREBUILT_BP_SHA,
            'locked native prebuilt provider body differs after ordinary pair build')
    return {'state': 'ORDINARY_PAIR_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING',
        'records': {name: row for name, (_, row) in records.items()}, 'pair': pair, 'actual_product_pair': pair_row,
        'engine': engine, 'whole_ART_APEX': apex, 'actual_published_manifest': manifest_pin,
        'published_projects': 597, 'published_root_links': 8, 'targets': TARGETS, 'dependency_mode': 'Strict',
        'source_projection_restored': True, 'full_translation_unit_qualification_verified': False,
        'signature_and_payload_verification_complete': False, 'private_AppZygote_role_authorized': False,
        'runtime_authorization_enabled': False, 'installation_performed': False}

if __name__ == '__main__':
    raise SystemExit(main())
