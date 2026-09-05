"""Structural callback-boundary regressions; not Rust or native-engine proof."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

_INPUTS = {
    'dispatch': 'crates/hepta-browser-actor/src/engine_dispatch.rs',
    'owner': 'crates/hepta-browser-actor/src/engine_dispatch/event_loop.rs',
    'tests': 'crates/hepta-browser-actor/src/engine_dispatch/event_loop_tests.rs',
    'transport': 'crates/hepta-browser-actor/src/engine_dispatch/event_loop_transport_tests.rs',
}
INPUTS = dict(_INPUTS)
CONTRACT = 'contracts/event-loop-completion.v1.json'
DOCUMENT = 'docs/architecture/EVENT_LOOP_COMPLETION.md'

# Reuse the same reviewed Rust comment/string masker as the D3 facade.
_SPEC = importlib.util.spec_from_file_location(
    '_callback_rust_source_helpers', Path(__file__).with_name('verify_receipt_journal.py')
)
assert _SPEC and _SPEC.loader
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)

EXPECTED = {
    'schema': 'trillionnium.desktop.event-loop-completion.v1', 'work_package': 'D3-01',
    'status': 'SOURCE_CANDIDATE', 'constructor': 'callback_engine_pair',
    'owner': 'CallbackEngineOwner', 'backend_trait': 'CallbackPageRuntime',
    'completion': 'EngineCompletion', 'client': 'EngineThreadRuntime',
    'owner_send': False, 'owner_sync': False, 'completion_cloneable': False,
    'completion_consumes_self': True, 'constructor_spawns_threads': False,
    'request_queue_limit': 1, 'active_call_limit': 1, 'completion_queue_limit': 1,
    'cancel_poll_ms': 5, 'deadline': 'original_monotonic_instant_no_reset',
    'owner_waits_for_callback': False,
    'wakes': ['request_enqueue', 'wait_abandonment', 'endpoint_drop', 'callback_result', 'callback_drop'],
    'atomic_hook': 'CallbackPageRuntime::start_page_act', 'generic_act': 'unsupported_no_fallback',
    'full_identity_checks': ['before_start', 'eventual_action_backend_responsibility', 'before_final_reply'],
    'pending_check': 'cancel_deadline_and_pidfd_only',
    'callback_drop': 'browser_crashed_not_empty_success',
    'retire': 'permanent_invalidate_pending_and_cleanup_at_most_once',
    'queued_is_durable_success': False, 'hard_realtime_bound': False, 'panic_hook_redacted': False,
    'process_ipc': False, 'servo_adapter': False, 'native_event_loop_exercised': False,
    'development_daemon_switched_to_callback': False, 'new_environment_selector': False,
    'production_listener_enabled': False, 'external_effect_authority': False,
    'promotion_authoritative': False, 'required_sources': list(_INPUTS.values()),
    'document': DOCUMENT, 'evidence_ceiling': 'HOST_CALLBACK_FIXTURE_NOT_NATIVE_ENGINE_OR_IMAGE',
}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('non-finite constant')


def _same_typed(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(right, list):
        return len(left) == len(right) and all(_same_typed(a, b) for a, b in zip(left, right))
    if isinstance(right, dict):
        return left.keys() == right.keys() and all(_same_typed(left[k], v) for k, v in right.items())
    return left == right


def audit(inputs: dict[str, str], contract_text: str) -> list[str]:
    if set(inputs) != set(_INPUTS):
        return ['callback source inventory mismatch']
    errors = []
    try:
        contract = json.loads(contract_text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, TypeError):
        return ['callback contract must be strict JSON']
    if not _same_typed(contract, EXPECTED):
        errors.append('callback contract field/type/claim mismatch')
    code = {k: _HELPERS.mask_rust_non_code(v) for k, v in inputs.items()}

    def function(key, name, within=None):
        source = code[key]
        if within:
            at = source.find(within)
            if at < 0:
                errors.append('missing callback impl: ' + within)
                return ''
            source = source[at:]
        body = _HELPERS.rust_function_body(source, name)
        if not body:
            errors.append(f'missing callback function: {key}.{name}')
        return body

    def require(source, expression, label):
        match = re.search(expression, source, re.S)
        if not match:
            errors.append('callback source lost ' + label)
        return match.start() if match else -1

    def order(source, expressions, label):
        # Consume successive matches: repeated guards must be separate calls,
        # rather than both requirements accidentally matching the first one.
        position = 0
        for expression in expressions:
            match = re.search(expression, source[position:], re.S)
            if not match:
                errors.append('callback order changed or missing: ' + label)
                return
            position += match.end()

    require(code['dispatch'], r'pub mod event_loop;', 'public module wiring')
    require(code['owner'], r'_thread_affinity: PhantomData<Rc<\(\)>>', 'creator thread affinity')
    if re.search(r'\bunsafe\b|\.recv\(|\.recv_timeout\(|thread::(?:spawn|sleep|park)|\.join\(|UnixListener|TcpStream|TcpListener', code['owner']):
        errors.append('callback owner acquired blocking, unsafe or transport operations')
    if re.search(r'impl\s+Clone\s+for\s+EngineCompletion|#\[derive\([^]]*Clone[^]]*\)\]\s*pub struct EngineCompletion', code['owner']):
        errors.append('callback completion acquired cloning')
    require(code['owner'], r'pub fn complete\(\s*mut self,', 'consuming completion')
    require(code['owner'], r'sender: Option<SyncSender<Result<RuntimeReply, RuntimeFailure>>>', 'private single-use sender')
    if re.search(r'pub(?:\([^)]*\))?\s+sender:', code['owner']):
        errors.append('completion sender exposed')
    order(function('owner', 'callback_engine_pair'), [r'sync_channel\(ENGINE_PENDING_LIMIT\)', r'thread::current\(\).id\(\)', r'CallbackEngineOwner\s*\{'], 'constructor channel/owner')
    pump = function('owner', 'pump_one')
    order(pump, [r'self.active.is_some\(\)', r'self.receiver.try_recv\(\)', r'call.control.ensure_current_peer\(\)', r'mpsc::sync_channel\(1\)', r'self.active = Some\(ActiveCall', r'self.runtime.start_page_act\('], 'active before backend callback')
    require(pump, r'ordinary_message\(&active.call\)', 'shared operation mapping')
    require(pump, r'started.is_err\(\)', 'start panic retirement')
    poll = function('owner', 'poll_active')
    order(poll, [r'active.call.control.ensure_active\(\)', r'active.completion.try_recv\(\)', r'\.ensure_current_peer\(\)', r'\.and_then\(bound_reply\)', r'active.valid.store\(false', r'active.call.reply.try_send\(result\)'], 'completion final identity/bounds/invalidation')
    require(poll, r'Err\(TryRecvError::Empty\) => return CallbackPumpResult::Pending', 'pending does not repeat start')
    order(function('owner', 'ensure_current_peer'), [r'self.ensure_active\(\)\?', r'self.control.ensure_current_peer\(\)\?', r'self.ensure_active\(\)'], 'eventual callback authority')
    complete = function('owner', 'complete')
    order(complete, [r'self.sender.take\(\)', r'self.valid.load\(', r'\.and_then\(bound_reply\)', r'sender.try_send\(result\)', r'notify_engine\('], 'single-use result enqueue')
    require(function('owner', 'drop', 'impl Drop for EngineCompletion'), r'Err\(RuntimeFailure::BrowserCrashed\)', 'lost callback fails closed')
    # Explicit owner method, not the trait declaration with no body.
    retirement = function('owner', 'retire', 'impl<R: CallbackPageRuntime> CallbackEngineOwner<R>')
    order(retirement, [r'if self.retired', r'self.retired = true', r'self.closed.store\(true', r'active.valid.store\(false', r'active.call.control.cancel\(\)', r'self.runtime.retire\(\)'], 'idempotent revoke before cleanup')
    require(function('owner', 'next_wake_deadline'), r'\.deadline\s*\.min\(Instant::now\(\) \+ ENGINE_CANCEL_POLL\)', 'original deadline timer')
    for impl in ('impl Drop for EngineThreadRuntime', "impl Drop for PendingWait<'_>"):
        body = function('dispatch', 'drop', impl)
        order(body, [r'self.closed.store\(true', r'notify_engine\('], 'retirement wake: ' + impl)
    require(function('dispatch', 'ordinary_message'), r'BrowserOperation::PageAct \{ \.\. \} =>\s*\{\s*return Err\(RuntimeFailure::Unsupported', 'no generic semantic fallback')
    for key, names in {
        'tests': ['owner_yields_until_native_callback_and_never_restarts_the_operation', 'cancellation_while_callback_pending_retires_once_and_rejects_late_token', 'dropping_uncompleted_callback_is_failure_not_empty_success', 'buffered_callback_success_is_rechecked_against_current_request_identity', 'semantic_act_uses_distinct_callback_hook_and_keeps_expected_owner'],
        'transport': ['attested_host_chain_yields_for_native_callbacks_and_preserves_twelve_receipts', 'attested_deferred_navigation_identity_loss_is_indeterminate_not_success'],
    }.items():
        for name in names:
            require(code[key], rf'#\[test\]\s*fn {name}\(', 'executable regression ' + name)
    return errors
