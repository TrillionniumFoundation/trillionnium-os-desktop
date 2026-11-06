#!/usr/bin/env python3
"""Create an immutable App observation + QA input from one pinned successor.

This utility performs no install, launch, namespace entry or QA action. It does
not interpret external install/signature receipts as authorization. A reviewed
new flow must check those exact receipts and build/rebind its QA source closure.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import time
import types

sys.dont_write_bytecode = True


def read_pinned(path, pin, limit):
    if not path.startswith("/") or any(p in ("", ".", "..") for p in path[1:].split("/")):
        raise RuntimeError("CANONICAL_PATH_REQUIRED")
    fds = []
    try:
        d = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        fds.append(d)
        parts = path[1:].split("/")
        for p in parts[:-1]:
            d = os.open(p, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
            fds.append(d)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
            raise RuntimeError("BOUNDED_REGULAR_REQUIRED")
        raw, end = bytearray(), time.monotonic() + 5
        while len(raw) <= limit:
            if time.monotonic() >= end:
                raise RuntimeError("READ_DEADLINE")
            data = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not data:
                break
            raw.extend(data)
        def meta(s):
            return s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_mtime_ns, s.st_ctime_ns
        final = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(final)
        if (len(raw) != before.st_size or meta(os.fstat(fd)) != meta(before) or meta(os.fstat(final)) != meta(before)
                or hashlib.sha256(raw).hexdigest() != pin):
            raise RuntimeError("SOURCE_PIN_OR_IDENTITY_CHANGED")
        return bytes(raw)
    finally:
        failed = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                failed.append(fd)
        if failed:
            raise RuntimeError("SOURCE_FD_RETIREMENT_FAILED")


def run(request):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED")
    if set(request) != {"schema", "guard", "packages", "parent_app_scope", "install_or_signature_evidence", "output_scope", "output_binding"}:
        raise RuntimeError("CLOSED_REQUEST_SCHEMA")
    if request["schema"] != "pocket4-successor-app-observation-request-v1":
        raise RuntimeError("REQUEST_SCHEMA")
    pin = request["guard"]
    raw = read_pinned(pin["path"], pin["sha256"], 65536)
    guard = types.ModuleType("pinned_successor_observation_guard")
    guard.__file__ = pin["path"]
    exec(compile(raw, pin["path"], "exec"), guard.__dict__)
    core = guard._core()
    before = guard.current_guard()
    core.need(before["schema"] == "pocket4-successor-main-guard-v1", "SUCCESSOR_GUARD_REQUIRED")
    baseline = guard.current_baseline()
    parent_raw = core.pinned_record(request["parent_app_scope"])
    parent = core.parse(parent_raw)
    core.need(parent["schema"] == "pocket4-versioned-app-scope-v1" and
              parent["runtime_epoch_sha256"] == baseline["runtime_epoch_sha256"], "SAME_RUNTIME_APP_PARENT_REQUIRED")
    packages = request["packages"]
    core.need(type(packages) is list and 0 < len(packages) <= 128 and len(set(packages)) == len(packages), "EXACT_PACKAGES_REQUIRED")
    core.need(type(request["install_or_signature_evidence"]) is list and len(request["install_or_signature_evidence"]) <= 32,
              "EVIDENCE_REFERENCE_BOUND")
    for evidence in request["install_or_signature_evidence"]:
        core.pinned_record(evidence)
    pool = core.FDs()
    try:
        runtime = baseline["runtime"]
        expected = runtime["held"]["process_snapshot"]
        held = core.HeldProcesses(pool, {role: row["host_pid"] for role, row in expected["binding"]["processes"].items()})
        core.need(held.before["binding"] == expected["binding"], "RUNTIME_CHANGED")
        core.verify_runtime(pool, held, runtime)
        observed = core.app_scope(pool, held, packages)
        core.app_scope(pool, held, packages, observed, False)
        core.verify_runtime(pool, held, runtime)
        init = held.extra["android_init"]["held_proc"]
    finally:
        pool.close_all()
    after = guard.current_guard()
    core.need(before == after, "GUARD_CHANGED_DURING_APP_OBSERVATION")
    for evidence in request["install_or_signature_evidence"]:
        core.pinned_record(evidence)
    document = {"schema": "pocket4-versioned-app-scope-v1", "kind": "explicit-current-app-observation",
                "runtime_epoch_sha256": baseline["runtime_epoch_sha256"], "apps": observed,
                "parent_app_scope": request["parent_app_scope"],
                "external_install_or_signature_evidence": request["install_or_signature_evidence"],
                "external_evidence_policy_validated_by_this_reader": False,
                "fresh_signature_verification_performed": False, "UI_or_install_runtime_admitted": False}
    app_pin = core.write_new(request["output_scope"], core.canonical(document) + b"\n")
    directories = {kind + "/0/" + package: {key: row[key] for key in ("device", "inode", "uid", "gid")}
                   for package, app in observed.items() for kind, row in app["data_directories"].items()
                   if row["status"] == "PRESENT"}
    binding = {"schema": "pocket4-successor-qa-build-input-v1", "runtime_guard": pin, "app_scope": app_pin,
               "runtime_epoch_sha256": baseline["runtime_epoch_sha256"], "framework_epoch": baseline["framework_epoch"],
               "status": {"host_pid": runtime["held"]["process_snapshot"]["binding"]["processes"]["launcher"]["host_pid"]},
               "held_init_identity": init, "classpath_values": runtime["classpath"]["values"],
               "packages": {package: app["uid"] for package, app in observed.items()}, "app_directories": directories,
               "helper_source_binary_qualification_inherited": False, "build_performed": False,
               "UI_or_install_runtime_admitted": False, "production_ready": False}
    binding_pin = core.write_new(request["output_binding"], core.canonical(binding) + b"\n")
    check = guard.check_app_scope(app_pin, packages)
    return {"schema": "pocket4-successor-app-observation-result-v1", "ok": True, "app_scope": app_pin,
            "qa_build_input": binding_pin, "app_scope_guard": check, "observation_fds": pool.summary(),
            "build_performed": False, "UI_or_install_runtime_admitted": False, "new_signature_verification_performed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        request = json.loads(read_pinned(args.request, args.request_sha256, 262144))
        result = run(request)
    except BaseException as error:
        result = {"ok": False, "type": type(error).__name__, "UI_or_install_runtime_admitted": False}
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode()) > 65536:
        raise RuntimeError("STDOUT_BOUND")
    print(text, flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
