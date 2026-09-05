"""Function-local callback-service regression guards, not native/image evidence."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re

INPUTS = {
    'entry': 'crates/hepta-d3-development/src/sessiond/engine.rs',
    'runner': 'crates/hepta-d3-development/src/sessiond/callback_runner.rs',
    'bridge': 'crates/hepta-browser-actor/src/engine_dispatch/immediate_callbacks.rs',
    'tests': 'crates/hepta-d3-development/src/sessiond/callback_runner_tests.rs',
    'transport': 'crates/hepta-d3-development/src/sessiond/service_threaded_tests.rs',
    'main': 'crates/hepta-d3-development/src/bin/sessiond.rs',
}
CONTRACT = 'contracts/d3-callback-service-runner.v1.json'
DOCUMENT = 'docs/architecture/D3_CALLBACK_SERVICE_RUNNER.md'
EXPECTED = {
    'schema': 'trillionnium.desktop.d3-callback-service-runner.v1',
    'work_package': 'D3-01', 'status': 'SOURCE_CANDIDATE',
    'constructor': 'run_callback_on_owner', 'default_bridge': 'ImmediateCallbacks<AtomicFixtureRuntime>',
    'worker_count': 1, 'worker_lifetime': 'scoped_explicit_join',
    'owner_wait': 'private_latched_condition_variable', 'owner_idle_polling': False,
    'clear_notification': 'before_owner_event_drain', 'worker_finished': 'release_before_notify_acquire_before_wait',
    'native_timer': 'original_absolute_instant', 'request_timer': 'original_callback_owner_deadline',
    'driver_error': 'retire_before_join_fixed_diagnostic', 'poison': 'fail_closed_no_reset',
    'bridge_control': 'original_request_control_by_reference', 'generic_act': 'unsupported_no_fallback',
    'accept_poll_ms': 5, 'new_threads_per_request': False, 'new_listener': False,
    'servo_adapter': False, 'winit_event_loop': False, 'exact_image_qualified': False,
    'external_effect_authority': False, 'product_agent_port_enabled': False,
    'promotion_authoritative': False, 'new_environment_selector': False,
    'required_sources': list(INPUTS.values()), 'document': DOCUMENT,
}
_SPEC = importlib.util.spec_from_file_location('_service_callback_helpers', Path(__file__).with_name('verify_receipt_journal.py'))
assert _SPEC and _SPEC.loader
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)

def audit(inputs: dict[str, str], contract_text: str) -> list[str]:
    if set(inputs) != set(INPUTS):
        return ['callback service source inventory mismatch']
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate key')
            result[key] = value
        return result
    def bad(value): raise ValueError('nonfinite number')
    try:
        contract = json.loads(contract_text, object_pairs_hook=pairs, parse_constant=bad)
        if not isinstance(contract, dict): raise ValueError('not an object')
    except (TypeError, ValueError):
        return ['callback service contract is not strict JSON']
    errors = []
    if set(contract) != set(EXPECTED): errors.append('callback service contract field inventory changed')
    for key, value in EXPECTED.items():
        if type(contract.get(key)) is not type(value) or contract.get(key) != value:
            errors.append('callback service contract lost ' + key)
    code = {key: _HELPERS.mask_rust_non_code(value) for key, value in inputs.items()}
    def body(key, name):
        found = _HELPERS.rust_function_body(code[key], name)
        if not found: errors.append(f'missing callback service function {key}.{name}')
        return found
    def require(text, pattern, label):
        match = re.search(pattern, text, re.S)
        if not match: errors.append('callback service lost ' + label)
        return match.start() if match else -1
    def order(text, patterns, label):
        positions = [require(text, pattern, label) for pattern in patterns]
        if positions != sorted(positions): errors.append('callback service order changed: ' + label)
    require(body('entry', 'run_on_owner'), r'run_callback_on_owner\(ImmediateCallbacks::new\(runtime\),', 'real fixture bridge route')
    runner = body('runner', 'run_callback_on_owner')
    order(runner, [r'callback_engine_pair\(', r'thread::scope\(', r'\.spawn_scoped\(', r'while !finished.load\(Ordering::Acquire\)', r'wake.begin_cycle\(\)\?', r'catch_unwind\(AssertUnwindSafe\(&mut advance\)\)', r'owner.pump_one\(\)', r'earliest\(owner.next_wake_deadline\(\), native_deadline\)', r'wake.wait_until\(deadline\)\?'], 'clear before drain and original timer')
    require(runner, r'if !finished.load\(Ordering::Acquire\)\s*\{\s*wake.wait_until', 'completion predicate before wait')
    require(runner, r'if let Err\(error\) = cycle\s*\{\s*failure = Some\(error\);\s*stop.retire\(\);\s*owner.retire\(\);\s*worker.thread\(\).unpark\(\);\s*break;', 'driver failure cleanup before join')
    require(runner, r'let joined = worker\s*\.join\(\)', 'explicit join')
    require(runner, r'if let Some\(error\) = failure\s*\{\s*return Err\(error\);', 'do not hide driver error in worker success')
    if len(re.findall(r'\.spawn_scoped\(', runner)) != 1: errors.append('callback service must own one scoped worker')
    if re.search(r'thread::(?:park|sleep)|worker.is_finished\(', runner): errors.append('owner wait must use independent latch and finished predicate')
    order(body('runner', 'drop'), [r'self.finished.store\(true, Ordering::Release\)', r'self.wake.notify\(\)'], 'finished published before wake')
    order(body('runner', 'notify'), [r'self\s*\.pending\s*\.lock\(\)', r'\*pending = true', r'self.changed.notify_one\(\)'], 'latched notify')
    require(body('runner', 'begin_cycle'), r'\*pending = false', 'drain start clears previous notifications')
    wait = body('runner', 'wait_until')
    order(wait, [r'self\s*\.pending\s*\.lock\(\)', r'while !\*pending', r'self\s*\.changed\s*\.wait\(pending\)', r'at.saturating_duration_since\(Instant::now\(\)\)', r'self\s*\.changed\s*\.wait_timeout\(pending, remaining\)'], 'predicate-loop absolute wait')
    if re.search(r'pending\s*=\s*false', wait): errors.append('wait cannot erase a notification after drain')
    if 'clear_poison' in code['runner']: errors.append('poison cannot be cleared')
    start = body('bridge', 'start')
    order(start, [r'completion.ensure_current_peer\(\)', r'BrowserActorMessage::Act', r'\.dispatch\(owner, message, &completion.control\)', r'completion.complete\(result\)'], 'immediate bridge authority and original control')
    order(body('bridge', 'start_page_act'), [r'completion.ensure_current_peer\(\)', r'\.dispatch_page_act\(owner, target, action, &completion.control\)', r'completion.complete\(result\)'], 'dedicated semantic bridge')
    require(body('bridge', 'retire'), r'drop\(self.runtime.take\(\)\)', 'one-time backend drop')
    if re.search(r'RequestControl\s*\{|RequestControl::|thread::spawn|unsafe', code['bridge']): errors.append('bridge may not replace control or thread boundary')
    for name in ['callback_runner_yields_and_completes_deferred_work_on_owner', 'event_driver_error_cancels_pending_request_before_join', 'wake_latch_is_not_consumed_by_unrelated_thread_parking', 'worker_completion_publishes_finished_before_wake', 'poisoned_notification_state_is_rejected_not_reinitialized']:
        require(code['tests'], rf'#\[test\]\s*fn {name}\(', 'executable regression '+name)
    require(code['transport'], r'#\[test\]\s*fn deferred_fixture_uses_actual_callback_runner_and_preserves_fifteen_receipts\(', 'delayed service transport regression')
    for key in ['callback_service_runner_exercised', 'servo_adapter_exercised', 'product_agent_port_enabled', 'external_effect_authority']:
        if '\\"'+key+'\\":false' not in inputs['main']: errors.append('self-check lost explicit non-claim '+key)
    return errors
