#!/usr/bin/env python3
"""Unsealed template: explicit libffi bootstrap + frozen source worker + pidfd retirement.

CONFIG must be sealed from the actual successful host probe and a new reviewed
generation request. This template rejects execution before reading any Main
source, guard, lock, package or runtime identity.
"""
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

CONFIG = {'schema': 'pocket4-beike-library-owned-generation-config-v1', 'probe_stdout': {'path': '/home/alex/work/pocket4-beike-owned-generation-20261106-b34f158f88bbebf112840fd88df25d03/actual-probe.stdout.raw.jsonl', 'bytes': 14135, 'sha256': 'c590487759f7a0e2e32dec8cdb16a7c42b7f932ed88154f760fdde477770ef94'}, 'probe_terminal': {'path': '/home/alex/work/pocket4-beike-owned-generation-20261106-b34f158f88bbebf112840fd88df25d03/actual-probe.terminal.raw.json', 'bytes': 733, 'sha256': '86c28f1ff58512f7b8f3b42c59eb1a62e7bb20ce52edd0a043d54792e35d6762'}, 'probe_job_id': '1a1b16bbf10-fc05-7891', 'new_nonce': 'b34f158f88bbebf112840fd88df25d03', 'stage_root': '/home/alex/work/pocket4-beike-owned-generation-20261106-b34f158f88bbebf112840fd88df25d03', 'request': {'path': '/home/alex/work/pocket4-beike-owned-generation-20261106-b34f158f88bbebf112840fd88df25d03/generation-request.json', 'bytes': 1250, 'sha256': '70da4c77b0d7906c88da9e57afd95164654b7065dd89c9bf2baea8dfab5fdedd'}}
SELF_PIN = None  # Supplied by the fixed stager argv, avoiding a circular source hash.
PROBE_SOURCE = {
    "path": "/home/alex/work/pocket4-ffi-bootstrap-probe-20261106-r1/probe_ffi_bootstrap.py",
    "bytes": 18199, "sha256": "c7fc2c4a9397d861e27f257e3e0788cd76f7867f006d1b873b2916303b35ce82"}
OLD_NONCE = "77fe9d36efe51cf69813f3411099f049"
FROZEN_WORKER = {
    "path": "/home/alex/work/pocket4-beike-qa-source-preparation-worker-20261106-" + OLD_NONCE + "/prepare_beike_bound_source.py",
    "bytes": 22148, "sha256": "9db3af14e7f2903e3b94bc45ed43f202f2ceb243e95f904dcab3c363aa55cbde"}
ORIGINAL_FAILURE = {
    "path": "/home/alex/work/pocket4-beike-successor-qa-input-20261106-" + OLD_NONCE + "/result.json",
    "bytes": 28348, "sha256": "518c1b9bcef120ec80a1a5e46cce36b6c0f4fe3d489652f21bf4bbc14f60ac1e"}
STAT_KEYS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_rdev",
             "st_size", "st_mtime_ns", "st_ctime_ns")
MAX_OUTPUT = 131072  # Existing reviewed probe parent has this same bound.


def require(value, code):
    if not value:
        raise RuntimeError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def sealed():
    require(type(CONFIG) is dict and set(CONFIG) == {"schema", "probe_stdout", "probe_terminal",
            "probe_job_id", "request", "new_nonce", "stage_root"} and
            CONFIG["schema"] == "pocket4-beike-library-owned-generation-config-v1", "UNSEALED_NO_EXECUTION")
    nonce = CONFIG["new_nonce"]
    require(type(nonce) is str and re.fullmatch("[0-9a-f]{32}", nonce) and nonce != OLD_NONCE,
            "EXPLICIT_NEW_NONCE_REQUIRED")
    require(CONFIG["stage_root"] == "/home/alex/work/pocket4-beike-owned-generation-20261106-" + nonce,
            "ONLY_NEW_PRIVATE_STAGE_ROOT")
    require(str(Path(__file__).resolve()) == CONFIG["stage_root"] + "/prepare_beike_owned_lifetime.py",
            "REAL_NEW_STAGED_FILE_REQUIRED")


def entry(mode):
    global SELF_PIN
    require(len(sys.argv) == 6 and sys.argv[1] == mode and
            sys.argv[2] == "--source-sha256" and sys.argv[4] == "--source-bytes" and
            re.fullmatch("[0-9a-f]{64}", sys.argv[3]) and sys.argv[5].isdigit(), "EXACT_PINNED_ENTRY_REQUIRED")
    SELF_PIN = {"path": str(Path(__file__).resolve()), "sha256": sys.argv[3], "bytes": int(sys.argv[5])}
    require(0 < SELF_PIN["bytes"] <= 131072, "BOUNDED_SELF_SOURCE_REQUIRED")


def pinned(pin, limit=262144):
    require(type(pin) is dict and set(pin) == {"path", "bytes", "sha256"} and
            type(pin["bytes"]) is int and 0 <= pin["bytes"] <= limit and
            re.fullmatch("[0-9a-f]{64}", pin["sha256"]), "CLOSED_FILE_PIN_REQUIRED")
    fd = os.open(pin["path"], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                not before.st_mode & 0o022 and before.st_size == pin["bytes"], "ROOT_PIN_FILE_IDENTITY")
        body = bytearray()
        while len(body) <= pin["bytes"]:
            part = os.read(fd, min(65536, pin["bytes"] + 1 - len(body)))
            if not part:
                break
            body.extend(part)
        require(len(body) == pin["bytes"] and hashlib.sha256(body).hexdigest() == pin["sha256"], "PIN_BYTES_DIFFER")
        after = os.fstat(fd)
        path = os.stat(pin["path"], follow_symlinks=False)
        require(all(getattr(before, key) == getattr(after, key) == getattr(path, key)
                    for key in STAT_KEYS), "PIN_FILE_REPLACED")
        return bytes(body)
    finally:
        os.close(fd)


def load_module(pin, name):
    module = types.ModuleType(name)
    module.__file__ = pin["path"]
    exec(compile(pinned(pin), pin["path"], "exec"), module.__dict__)
    return module


def probe_proof():
    raw = pinned(CONFIG["probe_stdout"])
    terminal = json.loads(pinned(CONFIG["probe_terminal"]))
    return validate_probe_proof(raw, terminal, CONFIG["probe_job_id"])


def validate_probe_proof(raw, terminal, expected_job_id):
    lines = raw.splitlines()
    require(len(lines) == 2, "EXACT_PROBE_STDOUT_PROTOCOL")
    stage, value = [json.loads(line) for line in lines]
    require(stage["schema"] == "pocket4-ffi-bootstrap-probe-stage-v1" and
            stage["source"] == PROBE_SOURCE and stage["Main_actions"] == 0 and
            stage["bootstrap_FDs_before"] == stage["bootstrap_FDs_after"], "ACTUAL_PROBE_STAGE_REQUIRED")
    require(terminal["job_id"] == expected_job_id and terminal["state"] == "succeeded" and
            terminal["exit_code"] == 0 and terminal["output_complete"] is True and
            terminal["output_durable"] is True and terminal["terminal_publication_confirmed"] is True and
            terminal["automatic_retry"] is False and terminal["cancelled"] is False and
            terminal["timed_out"] is False, "ACTUAL_PROBE_DURABLE_SUCCESS_REQUIRED")
    for stream, count in (("stdout", len(raw)), ("stderr", 0)):
        require(terminal["log_bytes"][stream] == {"seen": count, "stored": count} and
                terminal["log_errors"][stream] is None and terminal["log_synced"][stream] is True and
                terminal["log_truncated"][stream] is False, "COMPLETE_PROBE_STREAM_REQUIRED")
    life = value["child_lifecycle"]
    require(value["schema"] == "pocket4-ffi-bootstrap-host-probe-v1" and value["ok"] is True and
            value["library_fd_retired_by_owned_process_exit"] is True and value["child_stderr_bytes"] == 0 and
            value["Main_actions"] == value["namespace_entries"] == value["Main_signals"] == 0 and
            value["guards_or_Main_locks_acquired"] == 0 and value["manual_library_FD_close"] is False and
            life["returncode"] == 0 and life["pidfd_acquired"] is True and life["pidfd_closed"] is True and
            life["pidfd_exit_observed"] is True and life["parent_descriptors_restored"] is True and
            life["owned_child_sigkill_count"] == 0 and life["timeout"] is False and life["errors"] == [],
            "ACTUAL_PROBE_AND_OWNED_EXIT_REQUIRED")
    observed = value["child"]
    require(observed["ok"] is True and observed["errors"] == [] and
            observed["no_HeldTarget_or_MainBinding_instance_created"] is True and
            [p["name"] for p in observed["phases"]] == ["import__ctypes", "import_ctypes",
                "import_only_frozen_held_runtime", "after_public_identity_reads_and_gc"],
            "ACTUAL_FOUR_PHASE_HOST_BOOTSTRAP_REQUIRED")
    return observed


def stable_library(value):
    # Virtual addresses and descriptor numbers are observations of one child,
    # not cross-process identity. Each current map/FD is independently checked.
    return {key: value[key] for key in ("path", "bytes", "sha256", "file", "elf")}


def pin_runtime_files(probe, observed):
    for name, limit in (("python_file", 16777216), ("ctypes_python_file", 131072),
                        ("ctypes_extension_file", 4194304)):
        expected = observed[name]
        data, actual = probe.public_file(expected["path"], limit, expected["sha256"])
        require(actual == {key: expected[key] for key in ("path", "bytes", "sha256", "file")},
                "EXACT_OBSERVED_RUNTIME_FILE_REQUIRED")
        if name == "ctypes_extension_file":
            require(probe.elf_identity(data) == expected["elf"], "EXACT_CTYPES_ELF_REQUIRED")
    require(os.path.realpath(sys.executable) == observed["python_file"]["path"] and
            sys.version == observed["python"]["version"] and
            list(sys.version_info) == observed["python"]["version_info"], "EXACT_ACTUAL_PYTHON_REQUIRED")


def initialize_library(probe, observed):
    require("ctypes" not in sys.modules and "_ctypes" not in sys.modules, "FRESH_LIBRARY_BOOTSTRAP_REQUIRED")
    initial = probe.census()
    require(set(initial) == {"0", "1", "2"}, "ONLY_STDIO_INHERITED")
    pin_runtime_files(probe, observed)
    for module_name, key in (("_ctypes", "ctypes_extension_file"), ("ctypes", "ctypes_python_file")):
        spec = importlib.util.find_spec(module_name)
        require(spec is not None and os.path.realpath(spec.origin) == observed[key]["path"],
                "EXACT_IMPORT_ORIGIN_REQUIRED")
    importlib.import_module("_ctypes")
    after_native = probe.census()
    added = set(after_native) - set(initial)
    require(len(added) == 1 and all(probe.fd_identity(row) == probe.fd_identity(after_native[fd])
                                    for fd, row in initial.items()), "ONE_EXACT_LIBRARY_RESOURCE_REQUIRED")
    library_fd = int(next(iter(added)))
    current = probe.library_binding(library_fd, after_native[str(library_fd)])
    require(stable_library(current) == stable_library(observed["library"]), "OBSERVED_LIBRARY_PIN_DIFFERS")
    importlib.import_module("ctypes")
    pin_runtime_files(probe, observed)
    frozen = probe.census()
    require(probe.same_descriptors(after_native, frozen), "BOOTSTRAP_UNKNOWN_FD")
    return initial, frozen, library_fd, current


def child():
    sealed()
    entry("--child")
    require(sys.stdin.buffer.read(1) == b"R", "HELD_PARENT_PIDFD_RELEASE_REQUIRED")
    result = {"schema": "pocket4-beike-owned-generation-child-v1", "ok": False,
              "errors": [], "source_worker_invoked": False, "library_FD_manually_closed": False,
              "unknown_FDs_closed": 0, "UI_actions": 0, "installs": 0, "builds": 0,
              "production_ready": False, "source_result_requires_parent_retirement": True}
    probe = None
    frozen = None
    try:
        require(os.getuid() == os.geteuid() == 0, "ACTUAL_EXISTING_HOST_ROOT_REQUIRED")
        pinned(SELF_PIN)
        probe = load_module(PROBE_SOURCE, "owned_generation_probe_support")
        observed = probe_proof()
        initial, frozen, library_fd, library = initialize_library(probe, observed)
        result["bootstrap_initial_descriptors"] = initial
        result["bootstrap_library_resource"] = library
        result["frozen_descriptors_before_Main"] = frozen
        worker = load_module(FROZEN_WORKER, "original_9db3_source_worker")
        request = json.loads(pinned(CONFIG["request"]))
        worker.validate_request(request)
        require(request["generation_nonce"] == CONFIG["new_nonce"] and
                request["generation_nonce"] != OLD_NONCE, "NO_FAILED_NONCE_REUSE")
        require(not os.path.lexists(request["output_root"]) and
                not os.path.lexists("/home/alex/work/pocket4-successor-qa-source-" + CONFIG["new_nonce"]),
                "NEW_EXPLICIT_GENERATION_ROOTS_REQUIRED")
        failed = json.loads(pinned(ORIGINAL_FAILURE))
        require(failed["ok"] is False, "OLD_FAILURE_MUST_REMAIN_FAILED")
        require(probe.same_descriptors(frozen, probe.census()), "PRE_MAIN_UNKNOWN_FD")
        result["source_worker_invoked"] = True
        result["worker_result"] = worker.run(request)  # Frozen worker, guard and FD count checks unchanged.
        require(result["worker_result"].get("ok") is True, "FROZEN_SOURCE_WORKER_FAILED")
        require(result["worker_result"]["process_fd_count_before"] ==
                result["worker_result"]["process_fd_count_after"], "ORIGINAL_COUNT_GATE_NOT_PASSED")
        for group in ("observation_fds", "lease_fds"):
            row = result["worker_result"][group]
            require(row["acquired"] == row["closed"] and row["remaining"] == 0 and row["errors"] == [],
                    "ALL_EXPLICIT_WORKER_RESOURCES_MUST_CLOSE")
        for action in ("UI_actions", "installs", "builds", "permission_changes", "lifecycle_commands", "ADB_commands"):
            require(result["worker_result"][action] == 0, "SOURCE_ONLY_ACTION_BOUNDARY")
        require(result["worker_result"]["old_Bili_unknown_evidence_unchanged"] is True and
                result["worker_result"]["meituan_saved_location_unchanged"] is True and
                result["worker_result"]["complete_46_app_scope_unchanged"] is True and
                result["worker_result"]["guard_before"] == result["worker_result"]["guard_after"],
                "ORIGINAL_SCOPE_AND_SAFETY_GATES_REQUIRED")
        require(len(result["worker_result"]["commands"]) == 4 and
                all(row["command"]["complete"] is True and row["command"]["joined"] is True and
                    row["command"]["returncode"] == 0 and row["command"]["errors"] == []
                    for row in result["worker_result"]["commands"]), "ALL_NATIVE_READ_CHILDREN_JOINED")
        for pin in (ORIGINAL_FAILURE, FROZEN_WORKER, PROBE_SOURCE, CONFIG["request"], SELF_PIN):
            pinned(pin)
        probe_proof()
        pin_runtime_files(probe, observed)
        final = probe.census()
        require(probe.same_descriptors(frozen, final), "FINAL_UNKNOWN_MISSING_OR_REPLACED_FD")
        require(probe.library_binding(library_fd, final[str(library_fd)]) == library,
                "LIBRARY_RESOURCE_CHANGED_WITHIN_WORKER")
        result["frozen_descriptors_after_Main"] = final
        result["old_failed_result_pin_preserved"] = ORIGINAL_FAILURE
        result["ok"] = True
    except BaseException as exc:
        result["errors"].append({"type": type(exc).__name__, "code": str(exc)[:1024]})
    finally:
        # Never close a descriptor whose owner is not this wrapper. A remaining
        # unknown resource forces failure; the parent retires this entire child.
        if probe is not None and frozen is not None:
            try:
                final = probe.census()
                result["final_descriptors"] = final
                require(probe.same_descriptors(frozen, final), "FINAL_FD_IDENTITY_MISMATCH")
            except BaseException as exc:
                result["ok"] = False
                result["errors"].append({"stage": "final_census", "type": type(exc).__name__, "code": str(exc)[:1024]})
    raw = canonical(result)
    require(len(raw) < MAX_OUTPUT, "CHILD_OUTPUT_BOUND")
    print(raw.decode("ascii"), flush=True)
    return 0 if result["ok"] else 1


def combined_qualification(life, child_value, stderr):
    return (life.get("returncode") == 0 and life.get("pidfd_acquired") is True and
            life.get("pidfd_exit_observed") is True and life.get("pidfd_closed") is True and
            life.get("parent_descriptors_restored") is True and life.get("owned_child_sigkill_count") == 0 and
            life.get("timeout") is False and life.get("errors") == [] and not stderr and
            child_value.get("schema") == "pocket4-beike-owned-generation-child-v1" and
            child_value.get("ok") is True and child_value.get("errors") == [] and
            child_value.get("worker_result", {}).get("ok") is True)


def publish(name, raw):
    require("/" not in name and len(raw) <= 196608, "BOUNDED_OWN_RECEIPT_ONLY")
    directory = os.open(CONFIG["stage_root"], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        st = os.fstat(directory)
        require(st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o700, "OWN_PRIVATE_STAGE_REQUIRED")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            data = memoryview(raw)
            while data:
                size = os.write(fd, data)
                require(size > 0, "RECEIPT_WRITE_PROGRESS")
                data = data[size:]
            os.fchmod(fd, 0o400)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
    finally:
        os.close(directory)
    pin = {"path": CONFIG["stage_root"] + "/" + name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    require(pinned(pin) == raw, "RECEIPT_READBACK")
    return pin


def main():
    result = {"schema": "pocket4-beike-owned-generation-result-v1", "ok": False,
              "automatic_retry": False, "UI_actions": 0, "installs": 0, "builds": 0,
              "production_ready": False, "UI_or_install_runtime_admitted": False,
              "inner_generation_alone_qualifies": False, "errors": []}
    try:
        sealed()
        entry("--execute-new-source-preparation")
        require(os.getuid() == os.geteuid() == 0, "ACTUAL_EXISTING_HOST_ROOT_REQUIRED")
        pinned(SELF_PIN)
        probe = load_module(PROBE_SOURCE, "owned_parent_probe_support")
        observed = probe_proof()
        pin_runtime_files(probe, observed)
        parent_before = probe.census()
        life, raw, stderr = probe.run_owned_child(
            [sys.executable, "-B", "-I", str(Path(__file__).resolve()), "--child",
             "--source-sha256", SELF_PIN["sha256"], "--source-bytes", str(SELF_PIN["bytes"])], seconds=1000)
        result["child_lifecycle"] = life
        result["native_children_after_forced_worker_exit"] = (
            "UNKNOWN_REQUIRES_EXPLICIT_RECONCILIATION" if life["owned_child_sigkill_count"] else
            "REQUIRES_INNER_JOINED_RECEIPTS")
        result["child_stdout"] = publish("child.stdout.raw.json", raw)
        result["child_stderr_bytes"] = len(stderr)
        result["child_stderr_sha256"] = hashlib.sha256(stderr).hexdigest()
        if stderr:
            result["child_stderr"] = publish("child.stderr.raw.txt", stderr)
        child_value = json.loads(raw)
        result["child_result"] = child_value
        require(combined_qualification(life, child_value, stderr), "CHILD_AND_PARENT_JOINT_GATE_FAILED")
        for pin in (ORIGINAL_FAILURE, FROZEN_WORKER, PROBE_SOURCE, CONFIG["request"], SELF_PIN):
            pinned(pin)
        probe_proof()
        pin_runtime_files(probe, observed)
        require(probe.same_descriptors(parent_before, probe.census()), "PARENT_FD_SET_CHANGED")
        result["library_FD_retired_by_held_owned_process_exit"] = True
        result["native_children_after_forced_worker_exit"] = "NORMAL_EXIT_ALL_FOUR_NATIVE_READS_JOINED"
        result["ok"] = True
        result["status"] = "NEW_QA_SOURCE_AND_OWNED_LIFETIME_QUALIFIED_ANDROID_UNRUN"
    except BaseException as exc:
        result["errors"].append({"type": type(exc).__name__, "code": str(exc)[:1024]})
        result["status"] = "SOURCE_GENERATION_OR_LIFETIME_INCOMPLETE_NO_RETRY"
    try:
        if CONFIG is not None:
            result["final_receipt"] = publish("result.json", canonical(result) + b"\n")
    except BaseException as exc:
        result["ok"] = False
        result["errors"].append({"type": type(exc).__name__, "code": "FINAL_OUTER_RECEIPT_FAILED"})
    print(canonical(result).decode("ascii"), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(child() if sys.argv[1:2] == ["--child"] else main())
