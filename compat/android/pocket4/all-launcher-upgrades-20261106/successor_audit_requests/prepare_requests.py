#!/usr/bin/env python3
"""Prepare immutable local requests; never call Pocket4 or execute an audit."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
COLLECTOR = HERE / "reference/audit_successor_apks.py"
COLLECTOR_PIN = {
    "path": "/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/audit_successor_apks.py",
    "bytes": 29242,
    "sha256": "faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a",
}
ACTUAL = PROJECT / "recovery/independent_repair_r2/actual-execute-01"
GUARD = {
    "path": "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py",
    "bytes": 3213,
    "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3",
}
INITIAL_SCOPE = {
    "path": "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/initial-app-scope.private.json",
    "bytes": 57713,
    "sha256": "19d742f98193a09403990ed3ee6944d4624a26690fb953d66cac4361af6f6d77",
}
RUNTIME_EPOCH = "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9"
BATCHES = (
    ("org.fcitx.fcitx5.android",),
    ("com.google.android.gms",),
    ("com.lianjia.beike", "com.rytong.ceair", "com.rytong.airchina", "com.tencent.mm"),
    ("com.Hyatt.hyt", "com.enflick.android.TextNow", "com.szzc", "tv.danmaku.bili"),
    ("com.MobileTicket", "com.amazon.mShop.android.shopping", "com.android.calendar", "com.android.camera2"),
    ("com.android.contacts", "com.android.deskclock", "com.android.dialer", "com.android.documentsui"),
    ("com.android.gallery3d", "com.android.messaging", "com.android.quicksearchbox", "com.android.settings"),
    ("com.android.threadnetwork.demoapp", "com.bestbuy.android", "com.ehi.national.mobile", "com.hertz.android.digital"),
    ("com.hilton.android.hhonors", "com.ihg.apps.android", "com.jingdong.app.mall", "com.marriott.mrt"),
    ("com.pinger.textfree", "com.sankuai.meituan.takeoutnew", "com.sdu.didi.psnger", "com.ss.android.ugc.aweme"),
    ("com.taobao.taobao", "com.ubercab", "com.united.mobile.android", "com.xunmeng.pinduoduo"),
    ("com.zhubajie.client", "com.zillow.android.streeteasy", "ctrip.android.view", "jp.co.ana.android.tabidachi"),
    ("local.pocket4.fixture", "org.chromium.webview_shell", "org.droidloom.qa.editorcontract"),
)


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("ascii")


def canonical_path(value):
    need(isinstance(value, str) and value.startswith("/") and
         all(part not in ("", ".", "..") for part in value[1:].split("/")), "CANONICAL_ABSOLUTE_PATH_REQUIRED")
    return value


def exact_file(path, pin):
    raw = Path(path).read_bytes()
    need(len(raw) == pin["bytes"] and digest(raw) == pin["sha256"], "ACTUAL_LOCAL_FILE_PIN_CHANGED:" + str(path))
    return raw


def new_file(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, "LOCAL_WRITE_PROGRESS")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(path.read_bytes() == raw, "LOCAL_REQUEST_READBACK")
    return {"bytes": len(raw), "sha256": digest(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("initial-reference", "post-upgrades"), default="initial-reference")
    parser.add_argument("--tag", default="initial-reference-r1")
    parser.add_argument("--scope-local", type=Path)
    parser.add_argument("--scope-remote")
    parser.add_argument("--release-local", type=Path)
    parser.add_argument("--release-remote")
    args = parser.parse_args()
    need(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", args.tag) is not None, "FRESH_REQUEST_TAG_REQUIRED")
    need((args.scope_local is None) == (args.scope_remote is None), "SCOPE_LOCAL_AND_REMOTE_PAIR_REQUIRED")
    need((args.release_local is None) == (args.release_remote is None), "RELEASE_LOCAL_AND_REMOTE_PAIR_REQUIRED")
    if args.phase == "post-upgrades":
        need(args.scope_local is not None and args.scope_remote != INITIAL_SCOPE["path"], "ACTUAL_FINAL_VERSIONED_SCOPE_REQUIRED")
    else:
        need(args.scope_local is None and args.scope_remote is None, "INITIAL_REFERENCE_SCOPE_IS_FIXED")

    source = exact_file(COLLECTOR, COLLECTOR_PIN)
    module = types.ModuleType("reviewed_apk_request_validator")
    module.__file__ = str(COLLECTOR)
    exec(compile(source, str(COLLECTOR), "exec"), module.__dict__)
    exact_file(ACTUAL / "current_baseline_guard.py", GUARD)  # Do not import the runtime guard.
    initial = json.loads(exact_file(ACTUAL / "initial-app-scope.private.json", INITIAL_SCOPE))
    if args.scope_local is None:
        scope, scope_pin = initial, INITIAL_SCOPE.copy()
    else:
        raw = args.scope_local.read_bytes()
        scope = json.loads(raw)  # Python preserves the complete integer stat values.
        scope_pin = {"path": canonical_path(args.scope_remote), "bytes": len(raw), "sha256": digest(raw)}
    need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and
         scope.get("runtime_epoch_sha256") == RUNTIME_EPOCH and
         set(scope["apps"]) == set(initial["apps"]) and len(scope["apps"]) == 46,
         "ACTUAL_SAME_SUCCESSOR_46_PACKAGE_SCOPE_REQUIRED")
    flattened = [package for batch in BATCHES for package in batch]
    need(len(BATCHES) == 13 and len(flattened) == len(set(flattened)) == 45 and
         set(flattened) == set(module.PACKAGES), "EXACT_REVIEWED_45_PACKAGE_PARTITION_REQUIRED")

    release_pin = None
    if args.release_local is not None:
        raw = args.release_local.read_bytes()
        release = json.loads(raw)
        need(release.get("schema") == "pocket4-published-release-apk-digests-v1", "RELEASE_REFERENCE_SCHEMA")
        release_pin = {"path": canonical_path(args.release_remote), "bytes": len(raw), "sha256": digest(raw)}

    folder = HERE / args.tag
    folder.mkdir(mode=0o700)  # Existing revisions are never overwritten.
    remote_requests = "/home/alex/work/pocket4-successor-apk-audit-requests-20261106-" + args.tag
    rows = []
    for number, packages in enumerate(BATCHES, 1):
        apks = [apk for package in packages for apk in scope["apps"][package]["apks"]]
        need(all(0 < len(scope["apps"][package]["apks"]) <= 32 for package in packages), "COMPLETE_APK_SET_COUNT_BOUND")
        need(all(type(apk["bytes"]) is int and 0 < apk["bytes"] <= module.MAX_APK for apk in apks), "SINGLE_APK_BYTE_BOUND")
        total = sum(apk["bytes"] for apk in apks)
        need(0 < total <= module.MAX_BATCH_BYTES, "FULL_BATCH_APK_BYTE_BOUND")
        name = "batch-%02d.request.json" % number
        request = {"schema": "pocket4-successor-apk-audit-request-v1", "guard": GUARD,
                   "app_scope": scope_pin, "packages": list(packages),
                   "output_root": module.OUTPUT_PREFIX + args.tag + "-b%02d" % number,
                   "official_release_assets": release_pin}
        module.validate_request(request)
        pin = new_file(folder / name, encode(request))
        request_path = remote_requests + "/" + name
        rows.append({"batch": number, "packages": list(packages), "APK_count": len(apks),
                     "logical_APK_bytes": total, "local_request_file": name,
                     "request": {"path": request_path, **pin}, "output_root": request["output_root"],
                     "coordinator_only_argv": ["/usr/bin/python3", "-I", COLLECTOR_PIN["path"],
                         "--request", request_path, "--request-sha256", pin["sha256"]],
                     "suggested_new_idempotency_key": "pocket4-successor-apk-audit-" + args.tag + "-b%02d-20261106" % number})
    manifest = {"schema": "pocket4-successor-apk-audit-prepared-requests-v1", "phase": args.phase,
                "runtime_epoch_sha256": RUNTIME_EPOCH, "guard": GUARD, "app_scope": scope_pin,
                "collector": COLLECTOR_PIN, "official_release_assets": release_pin,
                "generator": {"bytes": Path(__file__).stat().st_size, "sha256": digest(Path(__file__).read_bytes())},
                "partition": {"batches": 13, "launcher_packages": 45, "scope_packages": 46,
                    "non_launcher_scope_packages": sorted(set(scope["apps"]) - set(flattened)),
                    "actual_scope_APK_bytes_checked_locally": True,
                    "APK_count": sum(row["APK_count"] for row in rows),
                    "logical_APK_bytes": sum(row["logical_APK_bytes"] for row in rows)},
                "reviewed_collector_validate_request_passes": 13, "batches": rows,
                "remote_source_already_staged_by_root": True,
                "requests_staged_remotely_by_this_program": False, "runtime_jobs_submitted": 0,
                "execution_requested": False, "production_ready": False,
                "effective_permission_grants": "UNKNOWN_NOT_QUERIED",
                "initial_reference_must_be_replaced_for_final_post_upgrade_evidence": args.phase == "initial-reference",
                "coordinator_sequence": [
                    "Settle all coordinator-approved normal upgrades and obtain the actual last versioned App scope.",
                    "Generate a new post-upgrades request revision; preserve this revision and every original receipt.",
                    "Root stages exact request bytes in a fresh root-private directory and checks collector source pin.",
                    "Root starts one explicit batch, records its authoritative terminal, raw stdout and complete artifact.",
                    "Proceed serially only after every tool child joined, all FDs closed, action lock released, and final guard passed.",
                    "Stop on any guard/scope mismatch or incomplete retirement; do not automatically retry or replay."]}
    pin = new_file(folder / "REQUEST_MANIFEST.json", encode(manifest))
    directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    print(json.dumps({"prepared_directory": str(folder), "manifest": pin, "partition": manifest["partition"],
                      "validated_requests": 13, "runtime_jobs_submitted": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
