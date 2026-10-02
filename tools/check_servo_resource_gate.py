#!/usr/bin/env python3
"""Validate actual callback/DOM evidence; source tests cannot mint native facts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

try:
    from .artifact_evidence import open_file
except ImportError:
    from artifact_evidence import open_file

PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
MAX_BYTES = 128 * 1024
MAX_CALLBACKS = 64
DOM_TRUE = ("resourceProbesSettled", "sameOriginScriptRejected",
            "wrongMethodFetchRejected", "externalScriptRejected")
CEILING = ("signed_app_admission_connected", "installed_csp_qualified",
           "websocket_confinement", "all_protocol_confinement",
           "network_namespace_confinement", "product_ready")
REPORT_KEYS = {"schema", "servo_commit", "status", "fixture_origin",
               "fixture_network_requests", "generations", "global_cancel_submissions",
               "global_callback_observed", "stale_cancel_submissions",
               "default_resources_admitted", "network_continuations_submitted",
               "callback_bound_exceeded", "claim_ceiling"}
GENERATION_KEYS = {"generation", "callbacks", "local_response_finishes",
                   "cancel_submissions", "same_origin_script_cancels",
                   "wrong_method_fetch_cancels", "external_script_cancels", "dom"}


def closed_object(value: object, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{label} fields are not exact")
    return value


def exact(value: object, expected: object, label: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise ValueError(f"{label} is not the exact required value")


def count(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_CALLBACKS:
        raise ValueError(f"{label} is not a bounded integer")
    return value


def validate(report: object, runtime: object, fixture_origin: str) -> None:
    report = closed_object(report, REPORT_KEYS, "resource report")
    if type(runtime) is not dict:
        raise ValueError("actual runtime report must be an object")
    exact(runtime.get("status"), "PASS_HEADED_LOCAL_FIXTURE_ONLY", "actual runtime status")
    exact(runtime.get("servo_commit"), PIN, "actual runtime Servo pin")
    exact(report["schema"], "trillionnium.desktop.servo-http-resource-gate.v1", "schema")
    exact(report["servo_commit"], PIN, "Servo pin")
    exact(report["status"], "OBSERVED_HTTP_CALLBACK_REFUSALS", "resource status")
    if not re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", fixture_origin):
        raise ValueError("fixture origin is not exact IPv4 loopback with an explicit port")
    if int(fixture_origin.rsplit(":", 1)[1]) > 65535:
        raise ValueError("fixture port is invalid")
    exact(report["fixture_origin"], fixture_origin, "owned fixture origin")
    for key in ("fixture_network_requests", "default_resources_admitted", "network_continuations_submitted"):
        exact(report[key], 0, key)
    exact(report["callback_bound_exceeded"], False, "callback bound")
    ceiling = closed_object(report["claim_ceiling"], set(CEILING), "claim ceiling")
    for key in CEILING:
        exact(ceiling[key], False, key)
    global_count = count(report["global_cancel_submissions"], "global callbacks")
    exact(report["global_callback_observed"], global_count > 0, "observed global callback")
    count(report["stale_cancel_submissions"], "stale callbacks")
    generations = report["generations"]
    if type(generations) is not list or len(generations) != 2:
        raise ValueError("actual resource evidence requires both generations")
    for generation, raw, page_key in zip((1, 2), generations, ("initial_page_evidence", "recovery_page_evidence")):
        facts = closed_object(raw, GENERATION_KEYS, "generation facts")
        exact(facts["generation"], generation, "callback generation")
        callbacks = count(facts["callbacks"], "callbacks", 4)
        finishes = count(facts["local_response_finishes"], "local finishes", 1)
        cancellations = count(facts["cancel_submissions"], "cancel submissions", 3)
        if callbacks != finishes + cancellations:
            raise ValueError("callback totals do not bind finishes and cancellations")
        probes = sum(count(facts[key], key, 1) for key in (
            "same_origin_script_cancels", "wrong_method_fetch_cancels", "external_script_cancels"))
        if probes > cancellations:
            raise ValueError("probe counts exceed actual cancellation submissions")
        dom = closed_object(facts["dom"], set(DOM_TRUE) | {"forbiddenResourceExecuted", "serviceWorkerProbe"}, "DOM facts")
        page = runtime.get(page_key)
        if type(page) is not dict:
            raise ValueError("actual runtime DOM evidence is absent")
        exact(page.get("generation"), generation, "actual DOM generation")
        exact(page.get("loaded"), True, "actual document load")
        for key in DOM_TRUE:
            exact(dom[key], True, key)
            exact(page.get(key), dom[key], f"actual DOM {key}")
        exact(dom["forbiddenResourceExecuted"], False, "forbidden resource execution")
        exact(page.get("forbiddenResourceExecuted"), False, "actual forbidden execution")
        if type(dom["serviceWorkerProbe"]) is not str or dom["serviceWorkerProbe"] not in ("unavailable", "rejected"):
            raise ValueError("worker probe must be unavailable or actually rejected")
        exact(page.get("serviceWorkerProbe"), dom["serviceWorkerProbe"], "actual worker probe")


def pairs(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def read_bounded(path: Path, limit: int) -> bytes:
    # The shared opener pins every absolute directory component, refuses
    # symlinks/FIFOs and requires one hard link. Parsing and hashing use the
    # same retained descriptor and the same bytes, never a pathname reopen.
    with os.fdopen(open_file(path), "rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > limit:
            raise ValueError("actual evidence exceeds size bound")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                                  value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(data) > limit or len(data) != before.st_size or identity(before) != identity(after):
            raise ValueError("actual evidence changed while reading or exceeded its bound")
    return data


def load(path: Path) -> tuple[object, bytes]:
    data = read_bounded(path, MAX_BYTES)
    return json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs), data


def verify_runtime(root: Path) -> dict:
    report, report_bytes = load(root / "resource-gate-result.json")
    runtime, runtime_bytes = load(root / "runtime-result.json")
    origin_bytes = read_bounded(root / "fixture-origin.txt", 64)
    origin = origin_bytes.decode("ascii", "strict").strip()
    validate(report, runtime, origin)
    return {
        "schema": "trillionnium.desktop.servo-http-resource-evidence.v1",
        "resource_result_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "runtime_result_sha256": hashlib.sha256(runtime_bytes).hexdigest(),
        "fixture_origin_sha256": hashlib.sha256(origin_bytes).hexdigest(),
        "global_callback_observed": report["global_callback_observed"],
        "qualification_scope": "two-generation actual HTTP callbacks and matching DOM refusals only",
        "product_ready": False,
    }


def verify_pin(source: Path) -> None:
    observed = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if observed != PIN:
        raise ValueError("Servo checkout is not the exact source pin")
    verify_api(source)


def verify_api(source: Path) -> None:
    snippets = {
        "components/servo/webview_delegate.rs": (
            "fn load_web_resource(&self, _webview: WebView, _load: WebResourceLoad)",
            "WebResourceResponseMsg::DoNotIntercept", "pub fn intercept(", "pub fn cancel("),
        "components/servo/servo_delegate.rs": ("fn load_web_resource(&self, _load: WebResourceLoad)",),
        "components/servo/servo.rs": ("pub fn set_delegate(&self, delegate: Rc<dyn ServoDelegate>)",),
        "components/net/request_interceptor.rs": ("WebResourceResponseMsg::CancelLoad =>", "NetworkError::LoadCancelled"),
    }
    for relative, expected in snippets.items():
        content = (source / relative).read_text(encoding="utf-8")
        for snippet in expected:
            if snippet not in content:
                raise ValueError(f"pinned HTTP API changed: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--servo-source", type=Path)
    args = parser.parse_args()
    if args.runtime_dir is None and args.servo_source is None:
        parser.error("require actual runtime directory or actual pinned source")
    if args.servo_source is not None:
        verify_pin(args.servo_source)
    if args.runtime_dir is not None:
        receipt = verify_runtime(args.runtime_dir)
        print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
