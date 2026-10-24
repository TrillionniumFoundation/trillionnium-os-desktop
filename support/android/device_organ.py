#!/usr/bin/env python3
"""Pocket4 Android host adapter: pinned observations and non-authorizing intents.

The executable exposes qualification and observation only. It never invokes a
device mutation, issues authority, retries a helper call, or stores a ledger.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

if __package__:
    from .device_organ_transport import AdapterError, OperationDeadline, PinnedTool, canonical_bytes, parse_object, run_bounded
else:
    from device_organ_transport import AdapterError, OperationDeadline, PinnedTool, canonical_bytes, parse_object, run_bounded


HELPER_PATH = "/usr/local/libexec/android-digitalis-observe-helper"
CTL_PATH = "/usr/bin/droidloomctl"
REVIEWED_HELPER_SHA256 = "8c9856a3791f0a208e59b00137547466c9f84d3a60d7a2cae700980de43f677b"
DEVICE_REF = "pocket4"
PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
SHA256 = re.compile(r"[0-9a-f]{64}")
WINDOW_TOKEN = re.compile(r"[0-9a-f]{1,32}")
STRING_SELECTORS = {"text", "id", "desc", "package", "class"}
BOOL_SELECTORS = {"focused", "editable", "enabled", "clickable", "scrollable", "selected", "checked"}


def require(condition, code):
    if not condition:
        raise AdapterError(code)


def text(value, limit, code):
    require(isinstance(value, str) and "\0" not in value, code)
    try:
        require(len(value.encode("utf-8", "strict")) <= limit, code)
    except UnicodeError:
        raise AdapterError(code) from None
    return value


def digest(value):
    require(isinstance(value, str) and SHA256.fullmatch(value) is not None, "INVALID_SHA256")
    return value


def hash_json(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def helper_reply(reply):
    """Do not turn a timeout, malformed reply or screenshot change into success."""
    if reply.returncode != 0:
        try:
            failure = parse_object(reply.stderr)
        except AdapterError:
            failure = {}
        code = failure.get("error")
        if not isinstance(code, str) or re.fullmatch(r"[A-Z0-9_]{1,96}", code) is None:
            code = "TRANSPORT_RESULT_UNKNOWN"
        raise AdapterError(code, attempted=True, outcome_unknown=True)
    try:
        value = parse_object(reply.stdout)
    except AdapterError as error:
        raise AdapterError(error.code, attempted=True, outcome_unknown=True) from None
    if value.get("ok") is not True or value.get("outcome_unknown") is True:
        raise AdapterError("HELPER_RESULT_UNKNOWN", attempted=True, outcome_unknown=True)
    return value


def capabilities():
    """Source-reviewed support is distinct from a runtime effect qualification."""
    return {
        "identity": "read_only_transport",
        "window_observation": "source_reviewed_not_exercised_by_identity_probe",
        "semantic_intent": "exact_selector_window_and_hash_binding",
        "set_text_utf8": "source_reviewed_4096_byte_limit_not_effect_qualified",
        "commit_text": "NOT_CONFIGURED",
        "semantic_action_receiver_binding": "NOT_CONFIGURED",
        "original_effect_owner": "NOT_CONFIGURED",
        "effect_dispatch": "NOT_CONFIGURED",
        "automatic_retry": False,
    }


class AndroidDeviceAdapter:
    """Host I/O client for one reviewed helper; no effect-capable public method."""

    def __init__(self, droidloomctl_sha256, *, droidloomctl_owner_uid=0, timeout_seconds=55):
        require(type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 60,
                "INVALID_TIMEOUT")
        require(type(droidloomctl_owner_uid) is int and 0 <= droidloomctl_owner_uid < 1 << 32,
                "INVALID_TOOL_OWNER")
        require(droidloomctl_owner_uid in (0, os.geteuid()), "TOOL_OWNER_OUTSIDE_OPERATOR")
        self.helper = PinnedTool(HELPER_PATH, REVIEWED_HELPER_SHA256)
        self.control = PinnedTool(CTL_PATH, digest(droidloomctl_sha256),
                                  owner_uid=droidloomctl_owner_uid)
        self.timeout_seconds = timeout_seconds

    def _invoke(self, tool, argv, request=b"", *, deadline):
        deadline.remaining()
        before = tool.measure()
        remaining = deadline.remaining()
        try:
            reply = run_bounded(argv, request, remaining)
        except AdapterError as error:
            error.attempted = error.attempted or deadline.attempted
            error.outcome_unknown = error.outcome_unknown or deadline.attempted
            raise
        deadline.attempted = True
        deadline.remaining()
        try:
            after = tool.measure()
        except AdapterError as error:
            raise AdapterError(error.code, attempted=True, outcome_unknown=True) from None
        if before != after:
            raise AdapterError("TOOL_CHANGED_DURING_OBSERVATION", attempted=True, outcome_unknown=True)
        deadline.remaining()
        return reply

    def read_helper(self, request, *, _deadline=None):
        """The receiver-side allowlist precedes any privileged helper attempt."""
        deadline = _deadline or OperationDeadline(self.timeout_seconds)
        require(isinstance(request, dict), "OBJECT_REQUEST_REQUIRED")
        op = request.get("op")
        if op == "commit-text":
            raise AdapterError("COMMIT_TEXT_NOT_CONFIGURED")
        if op not in ("status", "observe"):
            raise AdapterError("EFFECT_OWNER_NOT_CONFIGURED")
        if op == "status":
            require(set(request) == {"op"}, "UNKNOWN_ARGUMENT")
        else:
            require(set(request) == {"op", "package", "display", "with_png", "accessibility_mode"},
                    "UNKNOWN_ARGUMENT")
            require(isinstance(request["package"], str)
                    and PACKAGE.fullmatch(request["package"]) is not None, "INVALID_PACKAGE")
            text(request["package"], 256, "INVALID_PACKAGE")
            require(type(request["display"]) is int and request["display"] == 0,
                    "ONLY_DEFAULT_DISPLAY_SUPPORTED")
            require(request["with_png"] is False and request["accessibility_mode"] == "none",
                    "READ_ONLY_PROFILE_REQUIRED")
        raw = canonical_bytes(request) + b"\n"
        reply = self._invoke(self.helper, ["/usr/bin/sudo", "-n", HELPER_PATH], raw,
                             deadline=deadline)
        result = helper_reply(reply), hashlib.sha256(reply.stdout).hexdigest()
        deadline.remaining()
        return result

    def qualify(self, *, _deadline=None):
        """Read daemon and cell identity. No UI dump, click, install or launch."""
        deadline = _deadline or OperationDeadline(self.timeout_seconds)
        control_reply = self._invoke(self.control, [CTL_PATH, "status", "--json"],
                                     deadline=deadline)
        if control_reply.returncode != 0:
            raise AdapterError("DROIDLOOM_STATUS_UNKNOWN", attempted=True, outcome_unknown=True)
        try:
            control = parse_object(control_reply.stdout)
        except AdapterError as error:
            raise AdapterError(error.code, attempted=True, outcome_unknown=True) from None
        status, status_sha256 = self.read_helper({"op": "status"}, _deadline=deadline)
        try:
            for name in ("android", "sdk", "boot_completed", "adbd", "usb_config", "persist_usb_config",
                         "adb_tcp_port", "persist_adb_tcp_port", "native_bridge", "berberis_flags"):
                text(status.get(name), 4096, "INVALID_DEVICE_STATUS")
        except AdapterError as error:
            raise AdapterError(error.code, attempted=True, outcome_unknown=True) from None
        host_pid = status.get("host_pid")
        init_pid = status.get("android_init_host_pid")
        checks = {
            "daemon_running": control.get("state") == "running",
            "daemon_ready": isinstance(control.get("message"), str)
                            and "Android is ready" in control["message"],
            "same_recorded_host": type(host_pid) is int and host_pid > 1
                                  and type(control.get("host_pid")) is int
                                  and host_pid == control["host_pid"],
            "android_init_present": type(init_pid) is int and init_pid > 1,
            "reviewed_backend": status.get("backend") == "droidloom-teto-digitalis-derived",
            "cell_running": status.get("running") is True,
            "boot_completed": status["boot_completed"] == "1",
            "android_release": status["android"] == "17",
            "sdk": status["sdk"] == "37",
            "adbd_stopped": status["adbd"] == "stopped",
            "adb_tcp_disabled": status["adb_tcp_port"] in ("", "-1", "0")
                                and status["persist_adb_tcp_port"] in ("", "-1", "0"),
            "usb_adb_disabled": all("adb" not in status[key].split(",")
                                    for key in ("usb_config", "persist_usb_config")),
        }
        identity = {
            "device_ref": DEVICE_REF,
            "execution_environment": "existing_droidloom_android_cell",
            "android_release": status["android"], "sdk": status["sdk"],
            "host_pid": host_pid, "android_init_host_pid": init_pid,
            "native_bridge": status["native_bridge"], "berberis_flags": status["berberis_flags"],
            "adbd": status["adbd"],
        }
        result = {
            "schema_version": 1, "profile": "pocket4-digitalis-read-only-v1",
            "observed_unix_ms": time.time_ns() // 1_000_000,
            "qualified": all(checks.values()), "checks": checks,
            "identity": identity, "identity_sha256": hash_json(identity),
            "helper": {"path": HELPER_PATH, "sha256": REVIEWED_HELPER_SHA256, "owner_uid": 0},
            "droidloomctl": {"path": CTL_PATH, "sha256": self.control.sha256,
                            "owner_uid": self.control.owner_uid},
            "runtime_operator_uid": os.geteuid(),
            "helper_status_reply_sha256": status_sha256,
            "capabilities": capabilities(),
            "ui_observation_executed": False, "device_mutation_attempts": 0,
            "original_owner_integration": "NOT_CONFIGURED",
            "host_binding": "original_runtime_operator_target_required",
            "host_identity_verified_by_adapter": False,
            "production_authority": False, "device_effect_verified": False,
            "android_on_asterinas_verified": False, "physical_handset_verified": False,
            "process_ids_are_durable_incarnation": False, "automatic_retry": False,
        }
        deadline.remaining()
        return result

    def observe(self, package):
        deadline = OperationDeadline(self.timeout_seconds)
        identity = self.qualify(_deadline=deadline)
        if not identity["qualified"]:
            raise AdapterError("IDENTITY_NOT_QUALIFIED", attempted=True)
        result, raw_sha256 = self.read_helper({
            "op": "observe", "package": package, "display": 0,
            "with_png": False, "accessibility_mode": "none",
        }, _deadline=deadline)
        try:
            projected = project_observation(result, raw_sha256, identity, package)
            deadline.remaining()
            return projected
        except AdapterError as error:
            raise AdapterError(error.code, attempted=True, outcome_unknown=True) from None


def window_context(window, bounds, screen):
    # Match the original helper's ensure_ascii=True context serialization.
    return hashlib.sha256(json.dumps(
        {"window": window, "scope": bounds, "screen": screen},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def checked_geometry(window, scope_bounds, screen):
    require(isinstance(screen, list) and len(screen) == 2, "INVALID_SCREEN_SIZE")
    width, height = screen
    require(type(width) is int and type(height) is int and 0 < width <= 8192
            and 0 < height <= 8192 and width * height <= 32_000_000, "INVALID_SCREEN_SIZE")
    for value in (window.get("window_bounds"), scope_bounds):
        require(isinstance(value, list) and len(value) == 4
                and all(type(v) is int for v in value), "INVALID_WINDOW_BOUNDS")
        left, top, right, bottom = value
        require(0 <= left < right <= width and 0 <= top < bottom <= height, "INVALID_WINDOW_BOUNDS")
    require(scope_bounds == window["window_bounds"], "UNEXPECTED_OBSERVATION_CROP")


def project_observation(result, raw_sha256, identity, package):
    """Retain exact source hashes without emitting private UI tree contents."""
    require(isinstance(result, dict) and result.get("ok") is True, "INVALID_OBSERVATION")
    screenshot = result.get("screenshot")
    require(isinstance(screenshot, dict), "INVALID_OBSERVATION")
    scope = screenshot.get("scope")
    require(isinstance(scope, dict), "INVALID_WINDOW_SCOPE")
    require(scope.get("package") == package and isinstance(package, str)
            and PACKAGE.fullmatch(package) is not None, "WINDOW_PACKAGE_MISMATCH")
    token = scope.get("window_token")
    require(isinstance(token, str) and WINDOW_TOKEN.fullmatch(token) is not None,
            "INVALID_WINDOW_TOKEN")
    require(type(scope.get("display_id")) is int and scope["display_id"] == 0,
            "ONLY_DEFAULT_DISPLAY_SUPPORTED")
    require(type(scope.get("android_init_host_pid")) is int
            and scope["android_init_host_pid"] == identity["identity"]["android_init_host_pid"],
            "DEVICE_INSTANCE_CHANGED")
    require(scope.get("accessibility_mode") == "none", "READ_ONLY_PROFILE_REQUIRED")
    activity = text(scope.get("activity"), 512, "INVALID_ACTIVITY")
    require(bool(activity), "INVALID_ACTIVITY")
    width, height = screenshot.get("width"), screenshot.get("height")
    checked_geometry(scope, screenshot.get("scope_bounds"), [width, height])
    window_bounds = list(scope["window_bounds"])
    scope_bounds = list(screenshot["scope_bounds"])
    stable = {"package": package, "activity": activity, "window_token": token,
              "display_id": 0, "window_bounds": window_bounds,
              "android_init_host_pid": scope["android_init_host_pid"]}
    context = window_context(stable, scope_bounds, [width, height])
    require(digest(screenshot.get("context_token")) == context, "WINDOW_CONTEXT_HASH_MISMATCH")
    require(screenshot.get("source") == "android_screencap"
            and screenshot.get("atomic_snapshot") is False, "UNREVIEWED_OBSERVATION_SEMANTICS")
    captured = screenshot.get("captured_unix_ms")
    require(type(captured) is int and captured > 0, "INVALID_CAPTURE_TIME")
    native = result.get("native")
    require(isinstance(native, dict), "NATIVE_OBSERVATION_MISSING")
    return {
        "schema_version": 1, "device_ref": DEVICE_REF,
        "identity_sha256": identity["identity_sha256"],
        "helper_sha256": REVIEWED_HELPER_SHA256,
        "raw_observation_sha256": digest(raw_sha256),
        "native_snapshot_sha256": hash_json(native),
        "window": stable, "frame_sha256": digest(screenshot.get("frame_sha256")),
        "scope_bounds": scope_bounds, "screen_size": [width, height],
        "scope_sha256": digest(screenshot.get("scope_sha256")), "context_token": context,
        "captured_unix_ms": captured, "atomic_snapshot": False,
        "authority": "none", "device_effect_verified": False,
        "private_ui_text_included": False, "automatic_retry": False,
    }


def prepare_semantic_intent(observation, operation_id, action, selector, value=None):
    """Build an exact payload for the original owner, never a grant or command.

    The current helper drops window/hash fields for semantic actions. Therefore
    this adapter intentionally has no path from this intent to helper execution.
    """
    require(isinstance(observation, dict) and type(observation.get("schema_version")) is int
            and observation["schema_version"] == 1
            and observation.get("device_ref") == DEVICE_REF, "INVALID_OBSERVATION")
    require(observation.get("helper_sha256") == REVIEWED_HELPER_SHA256, "UNREVIEWED_HELPER")
    require(observation.get("authority") == "none", "OBSERVATION_IS_NOT_AUTHORITY")
    text(operation_id, 256, "INVALID_OPERATION_ID")
    require(bool(operation_id) and re.fullmatch(r"[A-Za-z0-9._:/-]+", operation_id) is not None,
            "INVALID_OPERATION_ID")
    if action == "commit-text":
        raise AdapterError("COMMIT_TEXT_NOT_CONFIGURED")
    require(action in ("click", "set-text"), "UNSUPPORTED_SEMANTIC_ACTION")
    require(isinstance(selector, dict) and bool(selector)
            and not set(selector) - STRING_SELECTORS - BOOL_SELECTORS, "INVALID_SELECTOR")
    require(bool(set(selector) & {"id", "text", "desc"}), "EXACT_TARGET_SELECTOR_REQUIRED")
    for key, field in selector.items():
        if key in STRING_SELECTORS:
            text(field, 4096, "INVALID_SELECTOR_VALUE")
            require(bool(field), "EMPTY_SELECTOR_VALUE")
        else:
            require(type(field) is bool, "INVALID_SELECTOR_VALUE")
    window = observation.get("window")
    require(isinstance(window, dict), "INVALID_WINDOW_SCOPE")
    require(set(window) == {"package", "activity", "window_token", "display_id",
                           "window_bounds", "android_init_host_pid"}, "INVALID_WINDOW_SCOPE")
    require(isinstance(window["package"], str) and PACKAGE.fullmatch(window["package"]) is not None,
            "INVALID_PACKAGE")
    require("package" not in selector or selector["package"] == window.get("package"),
            "SELECTOR_PACKAGE_MISMATCH")
    require(isinstance(window.get("window_token"), str)
            and WINDOW_TOKEN.fullmatch(window["window_token"]) is not None, "INVALID_WINDOW_TOKEN")
    require(type(window["display_id"]) is int and window["display_id"] == 0,
            "ONLY_DEFAULT_DISPLAY_SUPPORTED")
    require(type(window["android_init_host_pid"]) is int and window["android_init_host_pid"] > 1,
            "INVALID_DEVICE_INSTANCE")
    require(bool(text(window["activity"], 512, "INVALID_ACTIVITY")), "INVALID_ACTIVITY")
    text(window["package"], 256, "INVALID_PACKAGE")
    checked_geometry(window, observation.get("scope_bounds"), observation.get("screen_size"))
    require(observation.get("atomic_snapshot") is False, "UNREVIEWED_OBSERVATION_SEMANTICS")
    require(observation.get("context_token") == window_context(
        window, observation.get("scope_bounds"), observation.get("screen_size")),
        "WINDOW_CONTEXT_HASH_MISMATCH")
    if action == "set-text":
        text(value, 4096, "INVALID_TEXT_VALUE")
    else:
        require(value is None, "UNEXPECTED_TEXT_VALUE")
    payload = {
        "schema_version": 1, "kind": "android_semantic_intent", "authority": "none",
        "operation_id": operation_id, "device_ref": DEVICE_REF,
        "identity_sha256": digest(observation.get("identity_sha256")),
        "helper_sha256": REVIEWED_HELPER_SHA256,
        "raw_observation_sha256": digest(observation.get("raw_observation_sha256")),
        "native_snapshot_sha256": digest(observation.get("native_snapshot_sha256")),
        "window": {**window, "window_bounds": list(window["window_bounds"])},
        "frame_sha256": digest(observation.get("frame_sha256")),
        "scope_bounds": list(observation["scope_bounds"]), "screen_size": list(observation["screen_size"]),
        "scope_sha256": digest(observation.get("scope_sha256")),
        "context_token": digest(observation.get("context_token")),
        "action": action, "selector": {**selector, "package": window["package"]},
        "matching": "exact_unique", "value": value,
    }
    raw = canonical_bytes(payload)
    require(len(raw) <= 16384, "INTENT_TOO_LARGE")
    return {"payload": payload, "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "dispatch_status": "NOT_CONFIGURED", "original_owner_required": True,
            "receiver_window_binding_required": True, "selector_resolution": "NOT_EXECUTED",
            "automatic_retry": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--droidloomctl-sha256", required=True)
    parser.add_argument("--droidloomctl-owner-uid", type=int, default=0,
                        help="explicit tool-owner pin; root or the current original operator UID")
    parser.add_argument("--timeout-seconds", type=float, default=55)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("qualify")
    observe = commands.add_parser("observe")
    observe.add_argument("--package", required=True)
    args = parser.parse_args(argv)
    try:
        adapter = AndroidDeviceAdapter(args.droidloomctl_sha256,
                                       droidloomctl_owner_uid=args.droidloomctl_owner_uid,
                                       timeout_seconds=args.timeout_seconds)
        result = adapter.qualify() if args.command == "qualify" else adapter.observe(args.package)
        code = 0 if result.get("qualified", True) else 3
    except AdapterError as error:
        result, code = error.receipt(), 2
    result["adapter_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["transport_sha256"] = hashlib.sha256(
        Path(__file__).with_name("device_organ_transport.py").read_bytes()).hexdigest()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
