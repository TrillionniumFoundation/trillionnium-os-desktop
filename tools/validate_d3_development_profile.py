#!/usr/bin/env python3
"""Ordinary-module facade for the D3 development-profile validator."""

from __future__ import annotations

import functools
import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any, Callable

_IMPL_PATH = Path(__file__).with_name("_validate_d3_development_profile_impl.py")
_SPEC = importlib.util.spec_from_file_location("_trillionnium_d3_profile_impl", _IMPL_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load D3 profile validator implementation: {_IMPL_PATH}")
_impl = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _impl
_SPEC.loader.exec_module(_impl)

_CANONICAL_ROOT = _impl.ROOT
_CANONICAL_ERRORS = _impl.ERRORS
_base_session = _impl.check_session_daemon
_base_fixture = _impl.check_fixture_and_journal


def _sync() -> None:
    root = globals().get("ROOT", _CANONICAL_ROOT)
    _impl.ROOT = root if isinstance(root, Path) else Path(root)
    errors = globals().get("ERRORS", _CANONICAL_ERRORS)
    if not isinstance(errors, list):
        raise RuntimeError("D3 validator ERRORS override must remain a list")
    _impl.ERRORS = errors


def _must(path: str, required: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> str:
    text = _impl.read_text(path)
    for marker in required:
        if marker not in text:
            _impl.fail(f"{path} is missing {marker!r}")
    for marker in forbidden:
        if marker in text:
            _impl.fail(f"{path} contains forbidden marker {marker!r}")
    return text


_CALLBACK_SPEC = importlib.util.spec_from_file_location(
    "_d3_callback_completion_audit", Path(__file__).with_name("audit_event_loop_completion.py")
)
if _CALLBACK_SPEC is None or _CALLBACK_SPEC.loader is None:
    raise RuntimeError("cannot load callback completion audit")
_callback_audit = importlib.util.module_from_spec(_CALLBACK_SPEC)
_CALLBACK_SPEC.loader.exec_module(_callback_audit)
_SERVICE_CALLBACK_SPEC = importlib.util.spec_from_file_location(
    "_d3_callback_service_audit", Path(__file__).with_name("audit_callback_service.py")
)
if _SERVICE_CALLBACK_SPEC is None or _SERVICE_CALLBACK_SPEC.loader is None:
    raise RuntimeError("cannot load callback service audit")
_service_callback_audit = importlib.util.module_from_spec(_SERVICE_CALLBACK_SPEC)
_SERVICE_CALLBACK_SPEC.loader.exec_module(_service_callback_audit)


THREADED_INPUTS = {
    "main": "crates/hepta-d3-development/src/bin/sessiond.rs",
    "service": "crates/hepta-d3-development/src/sessiond/service.rs",
    "engine": "crates/hepta-d3-development/src/sessiond/engine.rs",
    "callback": "crates/hepta-d3-development/src/sessiond/callback_runner.rs",
    "engine_tests": "crates/hepta-d3-development/src/sessiond/engine_tests.rs",
    "service_tests": "crates/hepta-d3-development/src/sessiond/service_threaded_tests.rs",
}
RUNNER_CONTRACT = "contracts/d3-session-engine-runner.v1.json"

# Reuse the reviewed Rust comment/string masker via an exact sibling module.
_HELPER_SPEC = importlib.util.spec_from_file_location(
    "_d3_receipt_source_helpers", Path(__file__).with_name("verify_receipt_journal.py")
)
if _HELPER_SPEC is None or _HELPER_SPEC.loader is None:
    raise RuntimeError("cannot load reviewed source-audit helpers")
_helpers = importlib.util.module_from_spec(_HELPER_SPEC)
_HELPER_SPEC.loader.exec_module(_helpers)


def audit_threaded_sources(inputs: dict[str, str], contract_text: str) -> list[str]:
    """Heuristic source-quality checks with explicit inputs, never runtime proof."""
    import json
    import re

    errors: list[str] = []
    if set(inputs) != set(THREADED_INPUTS):
        return ["D3 threaded source inventory mismatch"]

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate contract key")
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("non-finite contract number")

    try:
        contract = json.loads(contract_text, object_pairs_hook=pairs, parse_constant=bad_constant)
        if not isinstance(contract, dict):
            raise ValueError("contract must be an object")
    except (ValueError, TypeError):
        return ["D3 threaded contract is not strict JSON"]
    expected = {
        "schema": "trillionnium.desktop.d3-session-engine-runner.v1",
        "work_package": "D3-01", "status": "SOURCE_CANDIDATE",
        "binary": "hepta-agent-port-development-sessiond", "runtime": "AtomicFixtureRuntime",
        "runtime_thread": "process_main", "actor_thread": "single_scoped_connection_worker",
        "worker_name": "hepta-d3-connections", "worker_count": 1, "poll_ms": 5,
        "listener_created": False, "listener_nonblocking": True, "accepted_stream_blocking": True,
        "stop_signal": "one_way_observed_before_accept_and_after_connection",
        "worker_join_required": True, "first_attested_snapshot_retained": True,
        "continuity_fields": ["pid", "uid", "gid", "start_time_ticks", "cgroup_v2_path", "systemd_unit", "executable_sha256"],
        "attestation_scope": "request_scoped_pidfd_custody_refreshed_at_actor_and_engine_boundaries",
        "new_runtime_after_retirement": False, "new_deadline_budget": False,
        "native_event_loop": False, "process_ipc": False, "servo_adapter": False,
        "product_agent_port_enabled": False, "external_effect_authority": False,
        "promotion_authoritative": False, "new_environment_selector": False,
        "source_only_self_check": True, "exact_image_qualified": False,
        "document": "docs/architecture/D3_SESSION_ENGINE_RUNNER.md",
        "evidence_ceiling": "LOCAL_THREADED_DEVELOPMENT_FIXTURE_AND_HOST_TRANSPORT_ONLY",
        "required_sources": list(THREADED_INPUTS.values()) + ["crates/hepta-d3-development/src/sessiond/service_managed_tests.rs"],
    }
    if set(contract) != set(expected):
        errors.append("D3 threaded contract field inventory changed")
    for key, value in expected.items():
        if type(contract.get(key)) is not type(value) or contract.get(key) != value:
            errors.append(f"D3 threaded contract lost fixed field: {key}")
    code = {key: _helpers.mask_rust_non_code(value) for key, value in inputs.items()}

    def body(key, name):
        result = _helpers.rust_function_body(code[key], name)
        if not result:
            errors.append(f"missing function {key}.{name}")
        return result

    def require(source, expression, label):
        match = re.search(expression, source, re.S)
        if not match:
            errors.append(f"D3 threaded source lost {label}")
        return match.start() if match else -1

    def order(source, expressions, label):
        offsets = [require(source, exp, label) for exp in expressions]
        if offsets != sorted(offsets):
            errors.append(f"D3 threaded source order changed: {label}")

    order(body("service", "run_service"), [
        r"activation::require_profile\(arguments\)\?", r"activation::require_marker\(\)\?",
        r"activation::inherited_listener\(\)\?", r"listener.set_nonblocking\(true\)\?",
        r"storage::open_configured\(\)\?", r"storage::reconcile_unresolved\(&mut persistent_journal\)\?",
        r"engine::run_on_owner\(AtomicFixtureRuntime::default\(\)",
    ], "startup admission before runner")
    require(body("service", "run_service"), r"run_connections\(", "worker service binding")
    order(body("service", "run_connections"), [
        r"engine::accept_next\(&listener, stop\)\?", r"serve_connection\(",
        r"stop.ensure_active\(\)\?", r"rotate_quiescent_store\(&mut state\)\?",
    ], "retirement before rotation or new connection")
    connection = body("service", "serve_connection")
    order(connection, [
        r"activation::verify_stream_path\(&stream\)\?", r"PeerIdentity::from_stream\(&stream\)\?",
        r"attestor.attest_with_static_executable_digest\(peer, policy, executable\)\?",
        r"verify_continuity\(current, peer, attested.snapshot\(\)\)\?",
        r"PrincipalBinding::bind_attested\(", r"attach_session\(", r"serve_one_with_observer\(",
        r"attested.ensure_alive\(\)\?",
    ], "full identity before attachment and request decode")
    require(connection, r"attested.snapshot\(\).clone\(\)", "first snapshot capture")
    require(connection, r"runtime\s*.take\(\)\s*.ok_or_else", "single endpoint consumption")
    require(body("service", "verify_continuity"),
            r"!same_peer\(current.peer, peer\)\s*\|\|\s*current.peer_snapshot != \*snapshot",
            "complete first process snapshot comparison")
    require(body("service", "attach_session"), r"BrowserActor::new\(binding, runtime\)", "endpoint actor type")
    require(code["service"], r"type D3Actor = BrowserActor<EngineThreadRuntime>", "threaded actor")
    require(body("service", "handle"), r"handle_attested\(context, request, self.attestor, self.attested\)", "dispatch identity refresh")
    require(code["main"], r"mod engine;", "main engine module")
    require(body("engine", "run_on_owner"),
            r"run_callback_on_owner\(ImmediateCallbacks::new\(runtime\)", "immediate fixture callback bridge")
    runner = body("callback", "run_callback_on_owner")
    order(runner, [r"callback_engine_pair\(", r"thread::scope\(", r"\.spawn_scoped\(",
                   r"while !finished.load\(Ordering::Acquire\)", r"owner.pump_one\(\)", r"worker\s*\.join\(\)"],
          "create on main / spawn / pump / join")
    if len(re.findall(r"\.spawn_scoped\(", runner)) != 1:
        errors.append("D3 service requires exactly one scoped worker")
    require(runner, r"CallbackPumpResult::Retired => retired = true", "closed pair retirement observation")
    require(runner, r"if retired\s*\{\s*stop.retire\(\);\s*worker.thread\(\).unpark\(\)", "closed pair retirement")
    accept = body("engine", "accept_next")
    order(accept, [r"stop.ensure_active\(\)\?", r"listener.accept\(\)", r"stop.ensure_active\(\)\?;\s*stream.set_nonblocking\(false\)\?", r"return Ok\(stream\)"], "accept retirement and blocking stream")
    require(code["engine"], r"SERVICE_POLL: Duration = Duration::from_millis\(5\)", "bounded requested poll")
    for key in ("engine", "service", "callback"):
        if re.search(r"\b(?:unsafe|TcpListener|TcpStream)\b|UnixListener::bind|BrowserActor<AtomicFixtureRuntime>", code[key]):
            errors.append(f"D3 {key} acquired a forbidden alternate path")
    for key, names in {
        "engine_tests": ["runner_keeps_non_send_backend_and_drop_on_calling_thread",
                         "retired_engine_interrupts_idle_accept_without_a_client",
                         "worker_panic_is_joined_and_return_value_is_fixed",
                         "deadline_abandonment_retires_actual_service_accept_loop"],
        "service_tests": ["persistent_session_rejects_recycled_pid_with_new_process_birth",
                          "persistent_session_rejects_every_attested_snapshot_drift",
                          "actual_fixture_runs_through_service_owner_and_preserves_sequential_state"],
    }.items():
        for name in names:
            require(code[key], rf"#\[test\]\s*fn {name}\(", f"executable regression {name}")
    return errors


REQUEST_PEER_INPUTS = {'peer': 'crates/hepta-peer-attestation/src/lib.rs', 'lease': 'crates/hepta-peer-attestation/src/request_lease.rs', 'actor': 'crates/hepta-browser-actor/src/lib.rs', 'engine': 'crates/hepta-browser-actor/src/engine_dispatch.rs', 'tests': 'crates/hepta-browser-actor/src/engine_dispatch/authority_tests.rs', 'service': 'crates/hepta-d3-development/src/sessiond/service.rs'}
REQUEST_PEER_CONTRACT = "contracts/request-peer-custody.v1.json"

def audit_request_peer_sources(inputs: dict[str, str], contract_text: str) -> list[str]:
    """Local structural regression checks, NOT proof of kernel or engine behavior."""
    import json
    import re
    if set(inputs) != set(REQUEST_PEER_INPUTS):
        return ["request peer custody source inventory mismatch"]
    errors: list[str] = []
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError("non-finite number")
    try:
        contract = json.loads(contract_text, object_pairs_hook=pairs, parse_constant=bad_constant)
        if not isinstance(contract, dict):
            raise ValueError("object required")
    except (ValueError, TypeError):
        return ["request peer custody contract must be strict JSON"]
    expected = {'schema': 'trillionnium.desktop.request-peer-custody.v1', 'work_package': 'D3-01', 'status': 'SOURCE_CANDIDATE', 'scope': 'in_process_request_identity_continuity_only', 'custody_owners': 1, 'pidfd_duplicates_per_request': 1, 'original_attestor_source_pinned': True, 'original_executable_source_preserved': True, 'custody_drop_revokes': True, 'failure_latches_revocation': True, 'full_refresh_boundaries': ['request_admission', 'engine_entry', 'engine_return', 'actor_return'], 'wait_loop_check': 'revocation_and_pidfd_only_no_image_hash', 'post_dispatch_identity_loss': 'indeterminate_never_automatic', 'request_ids_can_extend_custody': False, 'unattested_compatibility_calls_are_attested': False, 'hard_realtime_bound': False, 'atomic_with_process_exit_or_exec': False, 'servo_adapter': False, 'exact_image_qualified': False, 'production_listener_enabled': False, 'external_effect_authority': False, 'promotion_authoritative': False, 'document': 'docs/architecture/REQUEST_PEER_CUSTODY.md', 'required_sources': ['crates/hepta-peer-attestation/src/lib.rs', 'crates/hepta-peer-attestation/src/request_lease.rs', 'crates/hepta-browser-actor/src/lib.rs', 'crates/hepta-browser-actor/src/engine_dispatch.rs', 'crates/hepta-browser-actor/src/engine_dispatch/authority_tests.rs', 'crates/hepta-d3-development/src/sessiond/service.rs']}
    if set(contract) != set(expected):
        errors.append("request peer custody contract field set changed")
    for key, value in expected.items():
        if type(contract.get(key)) is not type(value) or contract.get(key) != value:
            errors.append(f"request peer custody fixed field changed: {key}")
    code = {k: _helpers.mask_rust_non_code(v) for k, v in inputs.items()}
    def body(key, name):
        text = _helpers.rust_function_body(code[key], name)
        if not text:
            errors.append(f"missing {key}.{name}")
        return text
    def require(text, exp, label):
        match = re.search(exp, text, re.S)
        if not match:
            errors.append(f"request peer custody lost {label}")
        return match.start() if match else -1
    def order(text, expressions, label):
        offset = 0
        for exp in expressions:
            match = re.search(exp, text[offset:], re.S)
            if not match:
                errors.append(f"request peer custody order changed: {label}")
                return
            offset += match.end()
    refresh = body("peer", "refresh_snapshot")
    order(refresh, [r"attestor.proc_root != self.attestor.proc_root", r"self.ensure_alive\(\)\?", r"read_snapshot_with_source", r"refreshed != self.snapshot"], "original identity source")
    lease = body("lease", "request_custody")
    order(lease, [r"self.ensure_alive\(\)\?", r"self.pidfd.try_clone\(\).map_err", r"executable_source: self.executable_source.clone\(\)", r"attestor: self.attestor.clone\(\)", r"custody.verifier\(\).verify_current\(\)\?"], "pidfd and source capture")
    require(code["lease"], r"impl Drop for PeerRequestCustody\s*\{\s*fn drop\(&mut self\)\s*\{\s*self.revoke\(\)", "custody drop revocation")
    require(body("lease", "revoke"), r"revoked.store\(true, Ordering::SeqCst\)", "one-way revoke")
    require(body("lease", "ensure_alive"), r"state.peer.ensure_alive\(\)", "kernel pidfd check")
    require(body("lease", "verify_current"), r"refresh_snapshot\(&self.state.peer.attestor\)", "full refresh source")
    require(body("lease", "verify_current"), r"revoked.store\(true, Ordering::SeqCst\)", "identity failure latch")
    if re.search(r"revoked.store\(false", code["lease"]):
        errors.append("request peer custody must not revive revoked state")
    if "refresh_snapshot" in body("lease", "ensure_alive"):
        errors.append("wait loop cannot rehash executable")
    handler = body("actor", "handle_attested_inner")
    order(handler, [r"refresh_snapshot\(attestor\)", r"verify_dispatch_attestation", r"request_custody\(\)", r"RequestAuthorityScope", r"handle_inner\(context, request\)", r"check_attested_return_deadline\(context, request, page_was_present\)\?", r"verifier.verify_current\(\).is_err\(\)", r"check_attested_return_deadline\(context, request, page_was_present\)\?"], "attested scope and final refresh")
    deadline = body("actor", "check_attested_return_deadline")
    order(deadline, [r"context.remaining\(\)", r"reconcile_after_final_deadline\(context, request, page_was_present\)", r"return Err\(error\)"], "post-refresh deadline reconciliation")
    require(handler, r"self.runtime_unavailable = true", "runtime retirement after identity loss")
    require(handler, r"BrowserErrorCode::Indeterminate", "unknown effect classification")
    require(code["actor"], r"impl Drop for RequestAuthorityScope\s*\{\s*fn drop\(&mut self\)\s*\{\s*\*self.slot.borrow_mut\(\) = self.previous.take\(\)", "scope unwind cleanup")
    for name in ("with_runtime_control", 'reconcile_unbound_create_failure', "reconcile_late_create_after_deadline"):
        require(body("actor", name), r"authority: self.request_authority.borrow\(\).clone\(\)", f"control identity in {name}")
    require(body("actor", "ensure_active"), r"authority\s*\.ensure_alive\(\)", "control cheap liveness")
    require(body("actor", "ensure_current_peer"), r"authority\s*\.verify_current\(\)", "control full refresh")
    pump = body("engine", "pump_one")
    order(pump, [r"call.control.ensure_current_peer\(\)", r"dispatch_call\(&mut self.runtime, &call\)", r"\.ensure_current_peer\(\)\s*.and\(result\)", r"call.reply.try_send\(result\)"], "engine entry and reply refresh")
    require(body("actor", "runtime_failure"), r"RuntimeFailure::PeerIdentityRevoked => failure\(\s*BrowserErrorCode::Indeterminate", "runtime/wire indeterminate mapping")
    require(body("service", "handle"), r"handle_attested\(context, request, self.attestor, self.attested\)", "real service handler")
    for key, names in {
        "tests": ["queued_request_rechecks_cgroup_at_engine_boundary", "queued_request_rechecks_executable_at_engine_boundary", "unwinding_request_revokes_retained_control_and_clears_authority_slot", "attested_socket_navigation_drift_records_indeterminate_without_success_digest"],
        "lease": ["actual_child_exit_revokes_live_pidfd_request", "duplicated_pidfd_is_distinct_cloexec_and_tracks_same_live_peer", "identical_snapshot_from_replacement_proc_root_is_not_original_source"],
    }.items():
        for name in names:
            require(code[key], rf"#\[test\]\s*fn {name}\(", f"non-ignored regression {name}")
    return errors



SESSION_INCARNATION_INPUTS = {'actor': 'crates/hepta-browser-actor/src/lib.rs', 'identity': 'crates/hepta-browser-actor/src/incarnation.rs', 'tests': 'crates/hepta-browser-actor/src/incarnation_tests.rs', 'runtime': 'crates/hepta-d3-development/src/sessiond/runtime.rs', 'runtime_tests': 'crates/hepta-d3-development/src/sessiond/runtime_atomic_tests.rs', 'service_tests': 'crates/hepta-d3-development/src/sessiond/service_threaded_tests.rs'}
SESSION_INCARNATION_CONTRACT = "contracts/session-incarnation.v1.json"
SESSION_INCARNATION_EXPECTED = {'schema': 'trillionnium.desktop.session-incarnation.v1', 'work_package': 'D3-01', 'status': 'SOURCE_CANDIDATE', 'scope': 'actor_reconstruction_and_development_fixture_reference_isolation', 'entropy_bytes': 32, 'entropy_source': 'hepta_agent_transport::OsNonceSource', 'entropy_when': 'first_valid_create_per_actor', 'entropy_failure': 'latched_no_identity_or_runtime_dispatch', 'zero_entropy': 'reject', 'session_id': 'session-<uid>-<namespace>-<ordinal>', 'webview_token': 'webview-<namespace>-<ordinal>', 'namespace': 'sha256_domain_separated_fresh_entropy', 'frame_id': 'sha256_domain_separated_length_delimited_session_webview_local_frame_key', 'frame_id_bytes': 64, 'session_generation_scope': 'within_namespaced_session_not_global_counter', 'existing_v1_wire_schema_changed': False, 'disk_journal_format_changed': False, 'caller_namespace_selection': False, 'production_fault_injection': False, 'automatic_session_resurrection': False, 'reference_is_capability': False, 'absolute_uniqueness_proven': False, 'durable_anti_rollback': False, 'servo_adapter_implemented': False, 'exact_image_qualified': False, 'production_activation_enabled': False, 'external_effect_authority': False, 'promotion_authoritative': False, 'document': 'docs/architecture/SESSION_INCARNATION.md', 'required_sources': ['crates/hepta-browser-actor/src/lib.rs', 'crates/hepta-browser-actor/src/incarnation.rs', 'crates/hepta-browser-actor/src/incarnation_tests.rs', 'crates/hepta-d3-development/src/sessiond/runtime.rs', 'crates/hepta-d3-development/src/sessiond/runtime_atomic_tests.rs', 'crates/hepta-d3-development/src/sessiond/service_threaded_tests.rs']}

def audit_session_incarnation_sources(inputs: dict[str, str], contract_text: str) -> list[str]:
    """Heuristic source wiring checks only; executable regressions are separate."""
    import json
    import re
    if set(inputs) != set(SESSION_INCARNATION_INPUTS):
        return ["session incarnation source inventory mismatch"]
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate contract field")
            result[key] = value
        return result
    def invalid_number(value):
        raise ValueError("non-finite contract number")
    try:
        obj = json.loads(contract_text, object_pairs_hook=pairs, parse_constant=invalid_number)
        if not isinstance(obj, dict):
            raise ValueError("object required")
    except (ValueError, TypeError):
        return ["session incarnation contract is not strict JSON"]
    errors = []
    if set(obj) != set(SESSION_INCARNATION_EXPECTED):
        errors.append("session incarnation contract field inventory changed")
    for key, value in SESSION_INCARNATION_EXPECTED.items():
        if type(obj.get(key)) is not type(value) or obj.get(key) != value:
            errors.append(f"session incarnation contract changed: {key}")
    code = {k: _helpers.mask_rust_non_code(v) for k,v in inputs.items()}
    def body(key, name):
        result = _helpers.rust_function_body(code[key], name)
        if not result:
            errors.append(f"session incarnation missing function {key}.{name}")
        return result
    def require(text, expression, label):
        if not re.search(expression, text, re.S):
            errors.append(f"session incarnation lost {label}")
    def order(text, expressions, label):
        offset = 0
        for expression in expressions:
            match = re.search(expression, text[offset:], re.S)
            if not match:
                errors.append(f"session incarnation sequence changed: {label}")
                return
            offset += match.end()
    require(code['actor'], r"mod incarnation;", "private identity module")
    require(code['actor'], r"incarnation: incarnation::ActorIncarnation", "actor-owned namespace")
    create = body('actor', 'handle_inner')
    order(create, [r"self.session_counter.checked_add\(1\)", r"self.webview_counter.checked_add\(1\)",
                   r"context.remaining\(\)\?", r"self.incarnation.namespace\(\)\?", r"context.remaining\(\)\?",
                   r"self.binding.mechanism.peer.uid, namespace, next_session_counter",
                   r"namespace, next_webview_counter", r"validate_token\(", r"validate_token\(",
                   r"self.session_counter = next_session_counter", r"self.webview_counter = next_webview_counter",
                   r"self.runtime_dispatch_status\("], "reserve/deadline/bind/validate/commit/dispatch")
    namespace = body('identity', 'namespace')
    require(namespace, r"if self.failed", "latched allocation refusal")
    require(namespace, r"if self.namespace.is_none\(\)", "lazy single namespace")
    order(namespace, [r"self.read_entropy\(\)", r"bytes != \[0; NONCE_BYTES\]", r"digest.update\(ACTOR_DOMAIN\)",
                      r"digest.update\(bytes\)", r"self.namespace = Some\(hex\("], "fresh entropy domain separation")
    require(namespace, r"self.failed = true;\s*return Err\(identity_error\(\)\)", "entropy failure with no fallback")
    entropy = body('identity', 'read_entropy')
    require(entropy, r"OsNonceSource.next_nonce\(\)", "OS-selected entropy")
    require(entropy, r"#\[cfg\(test\)\]\s*if let Some\(source\)", "private test-only injection use")
    require(code['identity'], r"#\[cfg\(test\)\]\s*source: Option<Box<dyn NonceSource>>", "private test-only injection field")
    require(code['identity'], r"#\[cfg\(test\)\]\s*pub\(super\) fn with_source", "private test-only injection constructor")
    if re.search(r"std::env|SystemTime|Instant|process::id|FixedNonceSource", code['identity']):
        errors.append("session incarnation acquired a forbidden predictable/input fallback")
    frame = body('identity', 'scoped_frame_id')
    order(frame, [r"digest.update\(FRAME_DOMAIN\)", r"validate_token\(field, value, 128\)",
                  r"digest.update\(\(value.len\(\) as u32\).to_be_bytes\(\)\)",
                  r"digest.update\(value.as_bytes\(\)\)", r"Ok\(hex\(digest.finalize\(\).as_slice\(\)\)\)"], "bounded length-delimited frame namespace")
    require(body('runtime', 'semantic_target'),
            r"hepta_browser_actor::scoped_frame_id\(\s*&coordinates.session_id,\s*&coordinates.webview_token,\s*LOCAL_FRAME_KEY,?\s*\)\?",
            "current owner-scoped frame in fixture")
    order(body('runtime', 'dispatch'), [r"let target = semantic_target\(&coordinates\)\?", r"self.semantic_snapshot = Some"], "frame validation before snapshot publication")
    require(body('runtime', 'validate_binding'), r"snapshot.target != \*target", "full target comparison")
    for key, names in {
        'tests': ['reconstructed_actor_does_not_reissue_session_or_webview_identity', 'previous_incarnation_snapshot_is_rejected_before_dispatch',
                  'entropy_failure_is_latched_without_dispatch_counter_change_or_fallback', 'entropy_read_does_not_extend_deadline_or_consume_identity_ordinal'],
        'runtime_tests': ['stale_fixture_target_cannot_be_reparented_across_webviews', 'frame_scope_changes_even_when_only_outer_session_identity_changes'],
        'service_tests': ['recreated_service_reopens_journal_but_rejects_old_session_and_reparented_target'],
    }.items():
        for name in names:
            require(code[key], rf"#\[test\]\s*fn {name}\(", f"non-ignored {name}")
    return errors

def check_session_daemon() -> None:
    _sync()
    _base_session()
    runtime = _must(
        "crates/hepta-d3-development/src/sessiond/runtime.rs",
        (
            "pub(crate) struct AtomicFixtureRuntime",
            "fn dispatch_page_act",
            "caller_bound_target_revalidated",
            "snapshot.coordinates != *current",
            "snapshot.target != *target",
            "semantic_snapshot_mutation_epoch",
            "effect_applied_exactly_once",
            "servo_adapter_exercised",
        ),
    )
    if runtime.count("control.ensure_active()?;") < 3:
        _impl.fail("atomic PageAct runtime must check cancellation/deadline at dispatch and commit boundaries")
    _must(
        "crates/hepta-d3-development/src/bin/sessiond.rs",
        (
            "mod runtime;",
            '\\"atomic_semantic_page_act_wired\\":true',
            '\\"caller_bound_target_revalidation\\":true',
            '\\"servo_adapter_exercised\\":false',
        ),
    )
    _must(
        "crates/hepta-d3-development/src/sessiond/service.rs",
        (
            "type D3Actor = BrowserActor<EngineThreadRuntime>;",
            "engine::run_on_owner(AtomicFixtureRuntime::default()",
        ),
        (
            "actor: BrowserActor<DeterministicLocalRuntime>",
            "BrowserActor::new(binding, DeterministicLocalRuntime::default())",
        ),
    )

    callback_inputs = {key: _impl.read_text(path) for key, path in _callback_audit.INPUTS.items()}
    for error in _callback_audit.audit(callback_inputs, _impl.read_text(_callback_audit.CONTRACT)):
        _impl.fail(error)

    service_callback_inputs = {key: _impl.read_text(path) for key, path in _service_callback_audit.INPUTS.items()}
    for error in _service_callback_audit.audit(service_callback_inputs, _impl.read_text(_service_callback_audit.CONTRACT)):
        _impl.fail(error)

    inputs = {key: _impl.read_text(path) for key, path in THREADED_INPUTS.items()}
    for error in audit_threaded_sources(inputs, _impl.read_text(RUNNER_CONTRACT)):
        _impl.fail(error)
    request_inputs = {key: _impl.read_text(path) for key, path in REQUEST_PEER_INPUTS.items()}
    for error in audit_request_peer_sources(request_inputs, _impl.read_text(REQUEST_PEER_CONTRACT)):
        _impl.fail(error)
    identity_inputs = {key: _impl.read_text(path) for key, path in SESSION_INCARNATION_INPUTS.items()}
    for error in audit_session_incarnation_sources(identity_inputs, _impl.read_text(SESSION_INCARNATION_CONTRACT)):
        _impl.fail(error)


def check_fixture_and_journal() -> None:
    _sync()
    _base_fixture()
    fixture = _impl._joined_sources(
        (
            "crates/hepta-d3-development/src/bin/fixture.rs",
            "crates/hepta-d3-development/src/fixture/client.rs",
            "crates/hepta-d3-development/src/fixture/corpus.rs",
            "crates/hepta-d3-development/src/fixture/model.rs",
        )
    )
    for marker in (
        "d3-page-act-atomic",
        "element_reference_field",
        "atomic_semantic_resolver_exercised",
        "caller_bound_target_revalidated",
        "effect_applied_exactly_once",
        '\\"atomic_semantic_page_act_exercised\\":true',
        '\\"servo_adapter_exercised\\":false',
    ):
        if marker not in fixture:
            _impl.fail(f"D3 atomic TaskFlow corpus is missing {marker!r}")
    for marker in ("page_act_without_servo_resolver_rejected", "client::error(&acted"):
        if marker in fixture:
            _impl.fail(f"D3 atomic TaskFlow corpus retains obsolete path {marker!r}")


_impl.check_session_daemon = check_session_daemon
_impl.check_fixture_and_journal = check_fixture_and_journal


def _proxy(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        _sync()
        return function(*args, **kwargs)

    return invoke


for _name, _value in vars(_impl).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = (
        _proxy(_value)
        if inspect.isfunction(_value) and _value.__module__ == _impl.__name__
        else _value
    )

ROOT = _CANONICAL_ROOT
ERRORS = _CANONICAL_ERRORS

if __name__ == "__main__":
    raise SystemExit(main())
