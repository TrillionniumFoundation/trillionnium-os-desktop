#!/usr/bin/env python3
"""Independent candidate05 Go4/9GiB profile. Default: plan; no automatic retry."""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
import pathlib
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time

P = pathlib.Path
OWNER = P("/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01")
COMPOSITION = OWNER / "overlay-reconstruction-09"
CANDIDATE = COMPOSITION / "candidate-05"
MANIFEST = COMPOSITION / "candidate-05-source-manifest.json"
MANIFEST_SHA = "4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba"
BUILDER_ORIGIN = P("/home/alex/work/pocket4-signal-mask-r11-build-memory-01/builder-source")
BUILDER_MANIFEST = BUILDER_ORIGIN.parent / "builder-source-after.json"
BUILDER_MANIFEST_SHA = "e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017"
BUILDER = P("/home/alex/work/pocket4-signal-semantics-r15-20261104/cargo-target/debug/droidloom-update")
BUILDER_SHA = "16df26d88391c22c9f076917531f022907ec5608bd31e58e05c898605db9dcc4"
R16 = P("/home/alex/work/pocket4-proc-maps-offset-r16-20261104/source")
R16_RECEIPT = R16.parent / "frozen-build-01/target/product/droidloom_x86_64/droidloom-native-engine-source.json"
R16_RECEIPT_SHA = "9b46dca0395ecc77a75fa493d6788c3ea8c9e7a8f3b844c7a57aa5e78bfccf11"
SIGNAL_INPUTS = P("/home/alex/work/pocket4-signal-mask-r11-build-01/android-out/target/product/droidloom_x86_64/droidloom-native-engine-inputs.json")
SIGNAL_INPUTS_SHA = "ccf2ebc89bfb4a06722719e292723669332e69691894717d702ff96eaf30e898"
R16_HEAD = "a9496d886a85752ba407b76509952c06cd79ddb8"
TETO_BASE = "917021cf3ecd077eb1581146a79d2265011755b8"
TETO_URL = "https://github.com/denialwm/teto.git"
WORK = P("/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1")
ROOT = OWNER / "full-build-combined05-go4-01"
BUILD_SOURCE = ROOT / "builder-source"
ENGINE_SOURCE = ROOT / "engine-working"
OUT = ROOT / "android-out"
ATTEMPT = ROOT / "attempt-01"
MEMORY_MAX = 9 * 1024**3
SWAP_MAX = 1024**3
MIN_AVAILABLE = 13 * 1024**3
GO_PATCH = "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"
GO_PATCH_PREIMAGE_SHA = '6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e'
GO_PATCH_SHA = '0f51b488dfcb6200281d25d4b6d3da594870c6e747d2629f7b2e1bed8ae4ddbd'
GO_PATCH_SOURCE = b'--- a/ui/build/soong.go\n+++ b/ui/build/soong.go\n@@ -215,5 +215,9 @@\n \tcommonArgs = append(commonArgs, "-l", filepath.Join(pb.config.FileListDir(), "Android.bp.list"))\n \tinvocationEnv := make(map[string]string)\n+\t// Private leaf build on a 24 GiB desktop. env -i drops outer Go settings;\n+\t// give the analyzer the supported Go soft memory budget explicitly.\n+\t// This changes collection frequency, not module or dependency validation.\n+\tinvocationEnv["GOMEMLIMIT"] = "4GiB"\n \tif pb.debugPort != "" {\n \t\t//debug mode\n \t\tcommonArgs = append(commonArgs, "--delve_listen", pb.debugPort,\n'
SOONG_SOURCE = "build/soong/ui/build/soong.go"
FEATURE = "BERBERIS_PROCMAPS_RAW_METADATA_OWNER"
MATCHED_GATE = COMPOSITION / "combined-ancillary-controls-07/report.json"
MATCHED_GATE_SHA = 'e53c3e9e5846d36f971bae6140c394b837fa54525c0e2df4ac153c9ef5540803'
DISABLED_MARKER = b"DROIDLOOM_NATIVE_GENERATION=0;ROLE=ENGINE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;"
ENABLED_MARKER = b"DROIDLOOM_NATIVE_GENERATION=1;ROLE=ENGINE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;"
EXTERNAL_FIELDS = ("schema_version", "source", "source_lock_sha256", "native_bridge_lock_sha256",
                   "superproject", "compiler_project", "compiler_revision", "compiler_entry_sha256",
                   "link_references", "local_source_import_policy")
SIGNAL = {
    "guest_os_primitives/arm64/guest_context_arch.h": "c4234d83ce70c526d96cbd9b843dbca1e0645c18d7f371654552d2a8e2f07140",
    "guest_os_primitives/guest_signal_handling.cc": "7ca556ea512b2262e2bf28709bbb7962d4ef5cb7e4c53c012437b6603fd9623a",
    "guest_os_primitives/guest_signal_handling_arch.cc": "5fc077ed8538255bac2ac921b1231a3bf60314659f85c79237d724c41f0460b5",
    "guest_os_primitives/include/berberis/guest_os_primitives/guest_signal.h": "ebcc5ac4e092c50916a0f9668c94d3cb2266cece0ff728bc19513e8f7eb218ca",
    "guest_os_primitives/include/berberis/guest_os_primitives/guest_thread.h": "90a35d504656e32520ab84968ae8a3b586264c835489d13f85f42444cb0764c0",
    "guest_os_primitives/scoped_guest_signal_mask.h": "52c18a437a05e00be80420c39ef03d24b4ec86a2470b66b548c29d8888eecde9",
}

def digest(path):
    with P(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def regular(path):
    info = P(path).lstat()
    require(stat.S_ISREG(info.st_mode), "not a regular file: " + str(path))
    require(not (info.st_mode & (stat.S_ISUID | stat.S_ISGID)), "set-ID input: " + str(path))
    return info

def relative(name):
    value = pathlib.PurePosixPath(name)
    require(value.parts and str(value) == name and not value.is_absolute() and
            all(x not in ("", ".", "..", ".git") for x in value.parts),
            "invalid source relative path")
    return value

def inventory(base, skip_git=False):
    rows = {}
    for directory, dirs, files in os.walk(base, followlinks=False):
        if skip_git:
            dirs[:] = [x for x in dirs if x != ".git"]
            files = [x for x in files if x != ".git"]
        for name in sorted(dirs + files):
            path = P(directory) / name
            rel = str(path.relative_to(base))
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                rows[rel] = {"kind": "file", "sha256": digest(path),
                             "bytes": info.st_size, "mode": stat.S_IMODE(info.st_mode)}
            elif stat.S_ISLNK(info.st_mode):
                rows[rel] = {"kind": "symlink", "target": os.readlink(path)}
            else:
                require(stat.S_ISDIR(info.st_mode), "unsupported source object: " + rel)
    return rows

def hashes(base, skip_git=False):
    rows = inventory(base, skip_git)
    require(all(row["kind"] == "file" for row in rows.values()),
            "this frozen candidate requires regular source files")
    return {name: row["sha256"] for name, row in rows.items()}

def save(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())

def output(argv, timeout=30):
    value = subprocess.run(argv, check=True, capture_output=True, timeout=timeout)
    require(len(value.stdout) <= 65536 and len(value.stderr) <= 65536, "unexpected command output")
    return value.stdout.decode("utf-8").strip()

def git(base, *args):
    return output(["/usr/bin/git", "-C", str(base), *args])

def no_alias(path):
    require(path.is_absolute() and ".." not in path.parts, "non-absolute or parent path")
    for parent in [path, *path.parents]:
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode), "path aliases a symlink or non-directory")

def reference_inputs():
    require(digest(SIGNAL_INPUTS) == SIGNAL_INPUTS_SHA, "prior successful build inputs changed")
    reference = json.loads(SIGNAL_INPUTS.read_bytes())
    require(reference["scope"] == "native-engine-only" and
            reference["status"] == "inputs_captured" and
            all(field in reference for field in EXTERNAL_FIELDS), "incomplete reference input schema")
    return reference

def matched_gate_contract():
    require(digest(MATCHED_GATE) == MATCHED_GATE_SHA, "matched candidate05 gate changed")
    gate = json.loads(MATCHED_GATE.read_bytes())
    require(gate["state"] == "MATCHED_SMALL_GATES_PASSED" and
            gate["source_manifest_sha256"] == MANIFEST_SHA and
            gate["source_unchanged"] is True and gate["all_commands_pass"] is True and
            gate["actual_host_adapter_checks"] == 8 and gate["actual_ancillary_cases"] == 34 and
            gate["actual_listener_inheritance_fixed"] is True and
            len(gate["commands"]) == 8 and all(row["returncode"] == 0 for row in gate["commands"]),
            "matched candidate05 gate is not complete")

def go_builder_inventory(base):
    require(len(base) == 449, "base builder inventory is not the pinned 449-file set")
    row = base[GO_PATCH]
    require(row["kind"] == "file" and row["sha256"] == GO_PATCH_PREIMAGE_SHA and
            row["bytes"] == len(GO_PATCH_SOURCE) == 583,
            "base Go patch inventory changed")
    require(hashlib.sha256(GO_PATCH_SOURCE).hexdigest() == GO_PATCH_SHA and
            GO_PATCH_SOURCE.count(b'invocationEnv["GOMEMLIMIT"] = "4GiB"') == 1,
            "embedded Go4 patch changed")
    result = {name: dict(value) for name, value in base.items()}
    result[GO_PATCH]["sha256"] = GO_PATCH_SHA
    require([name for name in base if result[name] != base[name]] == [GO_PATCH],
            "unexpected builder inventory delta")
    return result


def write_owned_go_patch():
    # copytree produced a private ordinary file. Check the opened inode before
    # any write: neither a symlink nor a hardlink may redirect this mutation.
    path = BUILD_SOURCE / GO_PATCH
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                "copied Go patch is not a private regular inode")
        raw = os.pread(fd, 584, 0)
        require(len(raw) == 583 and hashlib.sha256(raw).hexdigest() == GO_PATCH_PREIMAGE_SHA,
                "copied Go patch preimage changed")
        require(raw.count(b'invocationEnv["GOMEMLIMIT"] = "6GiB"') == 1 and
                raw.replace(b'"6GiB"', b'"4GiB"', 1) == GO_PATCH_SOURCE and
                sum(a != b for a, b in zip(raw, GO_PATCH_SOURCE)) == 1,
                "Go patch is not exactly the one-byte budget change")
        require(os.pwrite(fd, GO_PATCH_SOURCE, 0) == len(GO_PATCH_SOURCE),
                "short write to owned Go patch")
        os.fsync(fd)
    finally:
        os.close(fd)


def go_projection_contract(inputs, reference):
    old = reference["effective_projection"]
    actual = inputs["effective_projection"]
    require(old["patches"][GO_PATCH] == GO_PATCH_PREIMAGE_SHA,
            "prior successful projection used a different Go patch")
    expected_patches = dict(old["patches"])
    expected_patches[GO_PATCH] = GO_PATCH_SHA
    require(actual["patches"] == expected_patches,
            "actual projection patch set differs beyond the one Go4 patch")
    projected_hash = actual["files"][SOONG_SOURCE]
    require(isinstance(projected_hash, str) and len(projected_hash) == 64 and
            all(c in "0123456789abcdef" for c in projected_hash) and
            projected_hash != old["files"][SOONG_SOURCE],
            "actual projected Soong file was not changed and pinned")
    return {"patch_path": GO_PATCH, "patch_sha256": GO_PATCH_SHA,
            "base_patch_sha256": GO_PATCH_PREIMAGE_SHA,
            "projected_soong_path": SOONG_SOURCE,
            "projected_soong_sha256": projected_hash,
            "projected_soong_precomputed_hash_comparison": False,
            "normal_builder_records_patch_after_successful_git_apply": True,
            "all_other_applied_patch_hashes_equal_reference": True}


def memory_admission(memory):
    require(MIN_AVAILABLE - MEMORY_MAX == 4 * 1024**3,
            "new profile must preserve the four-GiB admission difference")
    require(memory["MemAvailable"] >= MIN_AVAILABLE,
            "less than 13 GiB MemAvailable for independent Go4 profile; no automatic retry")
    require(memory["SwapFree"] >= SWAP_MAX,
            "less than the required 1 GiB free swap; no automatic lower-budget retry")


def source_contract():
    matched_gate_contract()
    for root in (CANDIDATE, BUILDER_ORIGIN, R16):
        no_alias(root)
    require(digest(MANIFEST) == MANIFEST_SHA, "candidate manifest changed")
    manifest = json.loads(MANIFEST.read_bytes())
    files = manifest["files"]
    require(len(files) == 948, "candidate file count changed")
    for name, wanted in files.items():
        relative(name)
        regular(CANDIDATE / name)
        require(digest(CANDIDATE / name) == wanted, "candidate byte mismatch: " + name)
    require(hashes(CANDIDATE) == files, "candidate has missing/extra files")
    engine = {name[len("engine/"):]: value for name, value in files.items() if name.startswith("engine/")}
    require(len(engine) == 925, "engine count changed")
    for name, wanted in SIGNAL.items():
        require(engine[name] == wanted, "frozen signal delta changed")
    header = CANDIDATE / "engine/kernel_api/include/berberis/kernel_api/proc_maps_raw_metadata_owner.h"
    require(("#define " + FEATURE + " 0") in header.read_text(), "candidate default enable flag changed")
    require(digest(BUILDER) == BUILDER_SHA, "builder executable changed")
    reference_inputs()
    require(digest(BUILDER_MANIFEST) == BUILDER_MANIFEST_SHA, "builder manifest changed")
    builder_files = json.loads(BUILDER_MANIFEST.read_bytes())
    require(len(builder_files) == 449 and inventory(BUILDER_ORIGIN) == builder_files,
            "builder source changed")
    go_builder_inventory(builder_files)
    require(digest(BUILDER_ORIGIN / GO_PATCH) == GO_PATCH_PREIMAGE_SHA,
            "original Go6 patch changed")
    require(digest(R16_RECEIPT) == R16_RECEIPT_SHA, "R16 receipt changed")
    baseline = json.loads(R16_RECEIPT.read_bytes())
    require(baseline["source_snapshot"]["commit"] == R16_HEAD, "R16 recorded git head changed")
    old = baseline["source_snapshot"]["files"]
    require(len(old) == 908 and hashes(R16, True) == old, "R16 source is not the frozen baseline")
    require(git(R16, "rev-parse", "HEAD") == R16_HEAD, "R16 actual git head changed")
    require(git(R16, "remote", "get-url", "origin") == TETO_URL, "R16 origin changed")
    git(R16, "merge-base", "--is-ancestor", TETO_BASE, R16_HEAD)
    require(set(old) <= set(engine), "unexpected deletion from baseline")
    projected = baseline["effective_teto_files"]
    require(set(projected) == set(old), "R16 projection inventory differs")
    changes = {name: projected[name] for name in old if old[name] != projected[name]}
    require(len(changes) == 22, "R16 projection set changed")
    # All 22 source inputs to these existing projector transforms are unmodified.
    require(all(engine[name] == old[name] for name in changes),
            "a changed projector input needs a new explicit effective-source expectation")
    expected_effective = dict(engine)
    expected_effective.update(changes)
    return files, engine, builder_files, baseline, expected_effective

def plan():
    return {"schema": 1, "state": "PLAN_ONLY", "candidate": str(CANDIDATE),
            "candidate_manifest_sha256": MANIFEST_SHA, "candidate_files": 948, "engine_files": 925,
            "new_root": str(ROOT), "new_output": str(OUT), "new_attempt": str(ATTEMPT),
            "targets": ["libberberis_arm64", "berberis_arm64_host_tests"],
            "argv": [str(BUILDER), "--source", str(BUILD_SOURCE), "--jobs", "1",
                     "native-engine-build", "--work", str(WORK), "--tests", "--out", str(OUT)],
            "source_env": {"DROIDLOOM_NATIVE_BRIDGE_SOURCE": str(ENGINE_SOURCE)},
            "CPUQuota": 200, "MemoryMax": MEMORY_MAX, "MemorySwapMax": SWAP_MAX,
            "MemAvailable_minimum": MIN_AVAILABLE, "SwapFree_minimum": SWAP_MAX,
            "Go_soft_heap": "4GiB", "profile": "independent-combined05-go4-01",
            "builder_source_changed_files": [GO_PATCH], "Go_patch_sha256": GO_PATCH_SHA,
            "base_builder_manifest_sha256": BUILDER_MANIFEST_SHA,
            "admission_headroom_bytes": MIN_AVAILABLE - MEMORY_MAX,
            "headroom_is_reserved": False,
            "feature_default_enabled": False, "ART_target_built": False, "factory_target_built": False,
            "tests_executed_by_build": False, "service_started": False, "Android_actions": 0,
            "Main_actions": 0, "production_ready": False}

def prepare():
    require(os.getuid() == 1000 and os.geteuid() == 1000, "preparation requires the original operator uid")
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    files, engine, builder_files, baseline, effective = source_contract()
    no_alias(ROOT)
    require(not ROOT.exists(), "new preparation root already exists; reconcile instead of overwriting")
    require(not OUT.exists(), "output must be fresh")
    ROOT.mkdir(mode=0o700)
    save(ROOT / "preparation-claim.json", {"schema": 1, "state": "PREPARING",
                                         "started_utc": utc(), "plan": plan()})
    try:
        shutil.copytree(BUILDER_ORIGIN, BUILD_SOURCE, symlinks=True)
        require(inventory(BUILD_SOURCE) == builder_files, "copied base builder differs")
        builder_files = go_builder_inventory(builder_files)
        write_owned_go_patch()
        require(inventory(BUILD_SOURCE) == builder_files, "copied Go4 builder differs")
        # No hardlinks or alternates: the old repo's objects and refs stay independent.
        output(["/usr/bin/git", "clone", "--local", "--no-checkout", "--no-hardlinks",
                "--", str(R16), str(ENGINE_SOURCE)], timeout=120)
        require(not (ENGINE_SOURCE / ".git/objects/info/alternates").exists(),
                "independent clone unexpectedly uses alternates")
        git(ENGINE_SOURCE, "config", "core.hooksPath", "/dev/null")
        git(ENGINE_SOURCE, "config", "core.autocrlf", "false")
        git(ENGINE_SOURCE, "remote", "set-url", "origin", TETO_URL)
        git(ENGINE_SOURCE, "update-ref", "--no-deref", "HEAD", R16_HEAD)
        git(ENGINE_SOURCE, "read-tree", R16_HEAD)
        require(hashes(ENGINE_SOURCE, True) == {}, "no-checkout clone produced working files")
        modes = {}
        for name, wanted in engine.items():
            relative(name)
            source = CANDIDATE / "engine" / name
            destination = ENGINE_SOURCE / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            # The immutable freeze removed executable bits. Restore executable
            # intent only from the exact original R16 file, never from a name.
            original = R16 / name
            mode = 0o755 if name in baseline["source_snapshot"]["files"] and regular(original).st_mode & 0o111 else 0o644
            with destination.open("xb") as stream:
                stream.write(source.read_bytes())
            destination.chmod(mode)
            modes[name] = mode
            require(digest(destination) == wanted, "copied engine differs: " + name)
        require(hashes(ENGINE_SOURCE, True) == engine, "working source inventory differs")
        require(git(ENGINE_SOURCE, "rev-parse", "HEAD") == R16_HEAD, "new git head differs")
        require(git(ENGINE_SOURCE, "remote", "get-url", "origin") == TETO_URL, "new git origin differs")
        git(ENGINE_SOURCE, "merge-base", "--is-ancestor", TETO_BASE, "HEAD")
        require(source_contract()[0] == files, "frozen inputs changed during preparation")
        save(ROOT / "engine-working-mode-manifest.json", modes)
        save(ROOT / "expected-effective-teto-files.json", effective)
        save(ROOT / "copied-builder-source-manifest.json", builder_files)
        receipt = {"schema": 1, "state": "PREPARED_NOT_BUILT", "finished_utc": utc(),
                   "candidate_manifest_sha256": MANIFEST_SHA,
                   "builder_manifest_sha256": digest(ROOT / "copied-builder-source-manifest.json"),
                   "base_builder_manifest_sha256": BUILDER_MANIFEST_SHA, "builder_sha256": BUILDER_SHA,
                   "builder_source_delta": {"path": GO_PATCH, "preimage_sha256": GO_PATCH_PREIMAGE_SHA,
                                            "sha256": GO_PATCH_SHA, "bytes": 583, "changed_bytes": 1},
                   "R16_receipt_sha256": R16_RECEIPT_SHA, "git_head": R16_HEAD, "git_base": TETO_BASE,
                   "original_success_inputs_sha256": SIGNAL_INPUTS_SHA,
                   "origin": TETO_URL, "engine_files": engine, "engine_file_count": len(engine),
                   "engine_modes_sha256": digest(ROOT / "engine-working-mode-manifest.json"),
                   "effective_teto_expectation_sha256": digest(ROOT / "expected-effective-teto-files.json"),
                   "normal_import_policy": "checksum-no-times-v1", "source_working_tree": True,
                   "base_and_candidate_unchanged": True, "feature_default_enabled": False,
                   "full_engine_built": False, "ART_built": False, "factory_built": False,
                   "installed": False, "Main_actions": 0, "plan": plan()}
        save(ROOT / "preparation.json", receipt)
        print(json.dumps({"state": receipt["state"], "path": str(ROOT / "preparation.json"),
                          "sha256": digest(ROOT / "preparation.json"), "engine_files": len(engine)}), flush=True)
        return 0
    except BaseException as error:
        save(ROOT / "preparation-failure.json", {"state": "PREPARATION_FAILED",
             "error": repr(error), "full_build_started": False, "Main_actions": 0})
        raise

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

def verify_prepared(expected_sha):
    require(len(expected_sha) == 64 and all(x in "0123456789abcdef" for x in expected_sha),
            "preparation SHA must be explicit")
    for root in (ROOT, BUILD_SOURCE, ENGINE_SOURCE):
        no_alias(root)
    require(digest(ROOT / "preparation.json") == expected_sha, "preparation receipt changed")
    receipt = json.loads((ROOT / "preparation.json").read_bytes())
    require(receipt["state"] == "PREPARED_NOT_BUILT" and receipt["candidate_manifest_sha256"] == MANIFEST_SHA,
            "wrong preparation receipt")
    files, engine, builder_files, baseline, effective = source_contract()
    builder_files = go_builder_inventory(builder_files)
    require(receipt["engine_files"] == engine and receipt["base_builder_manifest_sha256"] == BUILDER_MANIFEST_SHA and
            receipt["builder_sha256"] == BUILDER_SHA and receipt["plan"] == plan(),
            "prepared source or independent resource profile differs")
    require(receipt["builder_source_delta"] == {"path": GO_PATCH, "preimage_sha256": GO_PATCH_PREIMAGE_SHA,
                                                "sha256": GO_PATCH_SHA, "bytes": 583, "changed_bytes": 1},
            "prepared builder delta differs")
    copied_manifest = ROOT / "copied-builder-source-manifest.json"
    require(digest(copied_manifest) == receipt["builder_manifest_sha256"] and
            json.loads(copied_manifest.read_bytes()) == builder_files and
            inventory(BUILD_SOURCE) == builder_files, "copied Go4 builder source or manifest changed")
    require(hashes(ENGINE_SOURCE, True) == engine, "working source changed")
    modes = json.loads((ROOT / "engine-working-mode-manifest.json").read_bytes())
    require(digest(ROOT / "engine-working-mode-manifest.json") == receipt["engine_modes_sha256"],
            "source mode manifest changed")
    require(set(modes) == set(engine), "source mode manifest is incomplete")
    require(all(stat.S_IMODE(regular(ENGINE_SOURCE / name).st_mode) == mode for name, mode in modes.items()),
            "working source mode changed")
    require(digest(ROOT / "expected-effective-teto-files.json") == receipt["effective_teto_expectation_sha256"],
            "effective expectation changed")
    require(json.loads((ROOT / "expected-effective-teto-files.json").read_bytes()) == effective,
            "effective expectation differs")
    require(git(ENGINE_SOURCE, "rev-parse", "HEAD") == R16_HEAD and
            git(ENGINE_SOURCE, "remote", "get-url", "origin") == TETO_URL, "working git identity changed")
    return receipt, files, engine, builder_files, baseline, effective

def artifact_gate(engine, effective, builder_files):
    directory = OUT / "target/product/droidloom_x86_64"
    before_path = directory / "droidloom-native-engine-inputs.json"
    final_path = directory / "droidloom-native-engine-source.json"
    inputs = json.loads(before_path.read_bytes())
    final = json.loads(final_path.read_bytes())
    require(inputs["scope"] == "native-engine-only" and inputs["status"] == "inputs_captured", "input scope mismatch")
    require(final["status"] == "selected_artifacts_built", "final status mismatch")
    require(inputs["output_directory"] == str(OUT), "output identity mismatch")
    require(inputs["logical_targets"] == ["libberberis_arm64", "berberis_arm64_host_tests"], "target mismatch")
    # These external inputs are unchanged by the combined engine-only delta.
    # Capture their actual values and reject drift instead of treating the
    # compiler revision name or the builder's successful return as a pin.
    reference = reference_inputs()
    go_projection = go_projection_contract(inputs, reference)
    for field in EXTERNAL_FIELDS:
        require(inputs[field] == reference[field], "external input drift: " + field)
    require(inputs["builder_files"] == {
        name: builder_files[name]["sha256"] for name in (
            "Cargo.lock", "tools/droidloom-update/src/main.rs", "tools/droidloom-update/src/android.rs",
            "tools/droidloom-update/src/native_bridge.rs", "tools/droidloom-update/src/native_engine.rs")
    }, "actual builder-source inputs differ")
    require(inputs["tests_requested"] is True, "matching host tests were not requested")
    require(inputs["source_snapshot"]["files"] == engine and inputs["effective_teto_files"] == effective,
            "actual raw/effective source differs")
    require(inputs["source_snapshot"]["commit"] == R16_HEAD and
            inputs["source_snapshot"]["base_commit"] == TETO_BASE and
            inputs["source_snapshot"]["working_tree"] is True, "actual source genealogy differs")
    for name, wanted in SIGNAL.items():
        require(inputs["source_snapshot"]["files"][name] == wanted and
                inputs["effective_teto_files"][name] == wanted, "signal regression in actual build inputs")
    expected_final = dict(inputs)
    expected_final["engine"] = final["engine"]
    expected_final["host_tests"] = final["host_tests"]
    expected_final["status"] = "selected_artifacts_built"
    require(final == expected_final, "input/final source receipt drift")
    binary = P(final["engine"]["path"])
    require(binary == directory / "system/lib64/libberberis_arm64.so", "wrong engine path")
    require(digest(binary) == final["engine"]["sha256"], "engine digest mismatch")
    value = binary.read_bytes()
    require(DISABLED_MARKER in value and ENABLED_MARKER not in value, "actual enable marker mismatch")
    exports = {x.split("@")[0] for x in final["engine"]["metadata"]["exported_dynamic_symbols"]}
    require("NativeBridgeItf" in exports and "DroidloomBerberisGenerationV1" in exports,
            "private generation entry missing from actual ELF exports")
    require(final["engine"]["metadata"]["soname"] == "libberberis_arm64.so", "wrong SONAME")
    require(final["host_tests"]["built"] is True and final["host_tests"]["executed"] is False,
            "host artifact scope mismatch")
    for flag in ("installation_performed", "runtime_compatibility_verified", "full_product_qualified", "full_runtime_rebuilt"):
        require(final[flag] is False, "unexpected widened builder qualification")
    test = final["host_tests"]
    test_directory = OUT / "host/linux-x86/nativetest64/berberis_arm64_host_tests"
    require(test["directory"] == str(test_directory) and
            test["binary_path"] == str(test_directory / "berberis_arm64_host_tests") and
            test["shared_library_directory"] == str(OUT / "host/linux-x86/lib64"),
            "host artifact directory escaped the fresh output")
    require(test["variant"] == "linux_glibc_x86_64" and test["guest_architecture"] == "arm64",
            "host test architecture mismatch")
    require(set(test["data"]) == {"decoder/arm64_test/arm64_decoder_encodings.txt",
                                  "decoder/arm64_test/arm64_decoder_undefined_baseline.txt",
                                  "heavy_optimizer/arm64/arm64_tier_coverage.txt"} and
            set(test["shared_libraries"]) == {"libbase.so", "liblog.so", "libc++.so"},
            "host test data or library closure is incomplete")
    require(digest(test["binary_path"]) == test["binary"]["sha256"], "host binary digest mismatch")
    for name, wanted in test["data"].items():
        require(digest(P(test["directory"]) / name) == wanted, "host corpus drift")
    for name, wanted in test["shared_libraries"].items():
        require(digest(P(test["shared_library_directory"]) / name) == wanted["sha256"], "host shared library drift")
    return {"input_receipt_sha256": digest(before_path), "final_receipt_sha256": digest(final_path),
            "engine": final["engine"], "host_tests": test, "feature_default_enabled": False,
            "private_entry_export_observed": True, "Go4_projection": go_projection,
            "raw_source_files": len(engine),
            "effective_source_files": len(effective), "six_signal_hashes_match": True,
            "host_suite_executed": False, "Android_executed": False, "ART_built": False,
            "factory_built": False, "installed": False, "production_ready": False}

def build(expected_sha):
    require(os.getuid() == 1000 and os.geteuid() == 1000, "build requires original operator uid")
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    prepared, files, engine, builder_files, baseline, effective = verify_prepared(expected_sha)
    no_alias(ATTEMPT)
    no_alias(OUT)
    require(not ATTEMPT.exists() and not OUT.exists(), "attempt and output must both be fresh")
    memory = {a: int(b.split()[0]) * 1024 for a, b in
              (line.split(":", 1) for line in P("/proc/meminfo").read_text().splitlines())}
    # This read occurs in this new invocation immediately before owned-unit
    # verification and launch. No earlier diagnostic sample admits a build.
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
    claim = {"schema": 1, "state": "STARTING_COMBINED05_GO4_FLAG0_FULL_BUILD",
             "started_utc": utc(), "preparation_sha256": expected_sha, "plan": plan(),
             "mem_available_before": memory["MemAvailable"], "cpu_affinity_before": affinity,
             "cpu_affinity": selected, "unit": unit, "normal_builder_lock_and_recovery": True,
             "automatic_retry": False, "Main_resource_changes": False}
    save(ATTEMPT / "claim.json", claim)
    print(json.dumps(claim), flush=True)
    env = os.environ.copy()
    env["DROIDLOOM_NATIVE_BRIDGE_SOURCE"] = str(ENGINE_SOURCE)
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
        artifact = artifact_gate(engine, effective, builder_files)
        require(source_contract()[0] == files, "frozen input changed during full build")
        require(inventory(BUILD_SOURCE) == builder_files and hashes(ENGINE_SOURCE, True) == engine,
                "owned input changed during full build")
        require(digest(BUILDER) == BUILDER_SHA, "builder binary changed during full build")
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
        observation_errors = []
        def observe(label, operation):
            try:
                return operation()
            except Exception as error:
                observation_errors.append({"observation": label, "error": repr(error)})
                return None
        terminal = {"schema": 1, "state": "ARTIFACTS_BUILT_QUALIFICATION_PENDING" if failure is None else "FAILED",
                    "builder_returncode": code, "error": failure, "seconds": time.monotonic() - start,
                    "finished_utc": utc(), "cleanup": cleanup,
                    "stdout_sha256": observe("stdout", lambda: digest(ATTEMPT / "build.stdout")),
                    "stderr_sha256": observe("stderr", lambda: digest(ATTEMPT / "build.stderr")),
                    "memory_events": observe("memory_events", lambda: (cgroup / "memory.events").read_text()),
                    "memory_peak": observe("memory_peak", lambda: (cgroup / "memory.peak").read_text().strip()),
                    "memory_swap_peak": observe("memory_swap_peak", lambda: (cgroup / "memory.swap.peak").read_text().strip()),
                    "source_projection_journal_present": (WORK / "source-projection.json").exists(),
                    "artifact_gate": artifact, "Main_actions": 0, "Android_actions": 0,
                    "service_started": False, "all_apps_ready": False}
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--build", action="store_true")
    parser.add_argument("--preparation-sha256")
    args = parser.parse_args(argv)
    if not args.prepare and not args.build:
        require(args.preparation_sha256 is None, "SHA provided without build mode")
        print(json.dumps(plan(), indent=2))
        return 0
    if args.prepare:
        require(args.preparation_sha256 is None, "preparation cannot consume a prior receipt")
        return prepare()
    require(args.preparation_sha256 is not None, "build requires an actual preparation receipt SHA")
    return build(args.preparation_sha256)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"state": "ADMISSION_OR_PREPARATION_FAILED", "error": repr(error),
                          "Main_actions": 0, "service_started": False}), flush=True)
        sys.exit(1)
