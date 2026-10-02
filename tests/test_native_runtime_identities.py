from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

import test_image_workflow_identities as fixture

ROOT = Path(__file__).resolve().parents[1]


class NativeRuntimeIdentityTests(unittest.TestCase):
    setUp = fixture.ImageWorkflowIdentityTests.setUp
    tearDown = fixture.ImageWorkflowIdentityTests.tearDown
    git = fixture.ImageWorkflowIdentityTests.git
    commit = fixture.ImageWorkflowIdentityTests.commit

    def identity(self, event="pull_request", candidate=None, **overrides):
        environment_path = self.directory / "native-env"
        environment_path.write_text("")
        env = dict(os.environ, EVENT_NAME=event, EVENT_HEAD_SHA=candidate or self.head,
                   EXPECTED_BASE_REF="main", GITHUB_REF_NAME="candidate",
                   GITHUB_EVENT_NAME=event, GITHUB_SHA=self.git("rev-parse", "HEAD").strip(),
                   GITHUB_REF="refs/pull/1/merge" if event == "pull_request" else "refs/heads/candidate",
                   GITHUB_REPOSITORY="TrillionniumFoundation/trillionnium-os-desktop",
                   GITHUB_ENV=str(environment_path))
        env.update(overrides)
        result = subprocess.run(["bash", str(ROOT / "tools/run_servo_headed_runtime_gate.sh"), "identities"],
                                cwd=self.repository, env=env, capture_output=True, text=True, timeout=10)
        return result, environment_path.read_text()

    def test_real_merge_uses_its_actual_parents(self):
        result, record = self.identity()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"BASE_SHA={self.base}\n", record)
        self.assertIn(f"CANDIDATE_HEAD_SHA={self.head}\n", record)
        self.assertIn("EVIDENCE_MODE=pr_synthetic_merge\n", record)

    def test_forged_head_is_refused_without_publishing_identity(self):
        result, record = self.identity(candidate="0" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(record, "")

    def test_moved_base_invalidates_old_merge(self):
        self.git("switch", "-c", "moved-main", self.base)
        self.commit("moved main")
        self.git("push", "origin", "HEAD:main")
        self.git("switch", "main")
        result, record = self.identity()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(record, "")

    def test_manual_run_stays_diagnostic(self):
        result, record = self.identity("workflow_dispatch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE_MODE=manual_exact_object\n", record)

    def test_push_cannot_mint_main_authority_from_wrong_checkout(self):
        for builtin_sha in (self.base, self.git("rev-parse", "HEAD").strip()):
            result, record = self.identity("push", GITHUB_REF_NAME="main", GITHUB_REF="refs/heads/main", GITHUB_SHA=builtin_sha)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(record, "")

    def test_builtin_event_repository_and_ref_must_match(self):
        for override in ({"GITHUB_EVENT_NAME":"pull_request"}, {"GITHUB_REPOSITORY":"other/project"},
                         {"GITHUB_REF":"refs/heads/main"}):
            result, record = self.identity("push", **override)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(record, "")

    def test_exact_current_main_push_is_bound_to_remote_object(self):
        self.git("switch", "-c", "actual-main", self.base)
        self.commit("new actual main")
        exact = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "HEAD:main")
        result, record = self.identity("push", GITHUB_REF_NAME="main", GITHUB_REF="refs/heads/main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE_MODE=exact_main_push\n", record)
        self.assertIn(f"TESTED_SHA={exact}\n", record)


class NativeGestureWiringTests(unittest.TestCase):
    """Source wiring guards; executable owner behavior lives in its Rust corpus.

    These checks are not evidence that Servo cancels a held mouse gesture. The
    candidate explicitly retires the input generation and reports that gap.
    """
    def method(self, name):
        source = (ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text()
        marker = f"    fn {name}("
        start = source.index(marker)
        end = source.find("\n    fn ", start + len(marker))
        return source[start:] if end < 0 else source[start:end]

    def test_all_native_types_enter_one_ordered_lane_before_engine_state_changes(self):
        for name in ("forward_pointer_move", "forward_mouse_button", "forward_wheel", "forward_keyboard", "forward_native_ime"):
            source = self.method(name)
            self.assertIn("self.enqueue_native(", source)
            self.assertNotIn("notify_input_event(", source)
            self.assertNotIn("webview.focus()", source)
        key = self.method("forward_keyboard")
        self.assertIn("let point = self.ingress.borrow().point();", key)
        self.assertNotIn(".borrow()", key.split("self.enqueue_native(", 1)[1])
        button = self.method("forward_mouse_button")
        self.assertIn("self.ingress.borrow_mut().button(owned_button, owned_action)", button)
        dispatch = self.method("drain_native_input")
        self.assertIn("route_button_at(", dispatch)
        self.assertIn("ticket.point", dispatch)
        self.assertLess(dispatch.index(".begin(Instant::now(), &owner)"), dispatch.index("webview.focus()"))
        self.assertLess(dispatch.index("route_button_at("), dispatch.index("webview.notify_input_event(payload)"))
        self.assertEqual(dispatch.count("webview.notify_input_event("), 1)
        self.assertIn(".bind(Instant::now(), &current, &ticket, event_id)", dispatch)
        self.assertIn("self.native_owner().as_ref() != Some(&ticket.owner)", dispatch)

    def test_held_retirement_never_synthesizes_mouse_release_or_reconstruction(self):
        source = self.method("retire_withdrawn_gesture")
        self.assertIn("take_withdrawal()", source)
        self.assertIn("outcome.generation != self.generation.get()", source)
        self.assertIn("self.webview.borrow_mut().take()", source)
        self.assertIn("webview.blur()", source)
        self.assertIn("webview.hide()", source)
        self.assertIn("drop(webview)", source)
        self.assertIn("gesture-recovery-required.json", source)
        self.assertIn("servo_mouse_state_reset_proven\\\": false", source)
        self.assertNotIn("MouseButtonAction::Up", source)
        self.assertNotIn("MouseButtonEvent::new", source)
        self.assertNotIn("create_webview()", source)
        self.assertNotIn("reconstruct(", source)

    def test_release_completion_uses_actual_event_id_and_current_generation(self):
        dispatch = self.method("drain_native_input")
        self.assertIn("let event_id = webview.notify_input_event(", dispatch)
        self.assertIn("if let NativeKind::Up(owned_button) = ticket.kind", dispatch)
        self.assertIn(".insert(event_id, owned_button)", dispatch)
        callback = self.method("notify_input_event_handled")
        self.assertIn("if let Some(state) = self.current()", callback)
        self.assertIn(".remove(&event_id)", callback)
        self.assertIn("result.contains(InputEventResult::DispatchFailed)", callback)
        self.assertIn("self.generation, button, outcome", callback)
        self.assertIn("retire_withdrawn_gesture()", callback)
        self.assertLess(callback.index(".remove(&event_id)"),
                        callback.index("acknowledge_release("))

    def test_pointer_and_crash_paths_observe_recovery_required_outcome(self):
        self.assertIn("retire_withdrawn_gesture()", self.method("pointer_left"))
        source = (ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text()
        self.assertIn("focused(focused);", source)
        self.assertIn("if state.retire_withdrawn_gesture()", source)
        self.assertIn("// OS ingress/withdrawal must precede any old Servo ACK", source)
        window = self.method("window_event")
        self.assertLess(window.index("match event"), window.index("state.servo.spin_event_loop()"))
        self.assertIn("state.withdraw_native_input();", window)
        self.assertEqual(source.count("state.input.borrow_mut().crashed();\n"),
                         source.count("state.input.borrow_mut().crashed();\n                    state.withdraw_native_input();")
                         + source.count("state.input.borrow_mut().crashed();\n                state.withdraw_native_input();")
                         + source.count("state.input.borrow_mut().crashed();\n            state.withdraw_native_input();"))
        callback = self.method("notify_input_event_handled")
        self.assertIn(".acknowledge(", callback)
        self.assertIn("owner.view = format!", callback)
        self.assertNotIn("drain_native_input", callback)
        self.assertIn("AppEvent::Drive", callback)
        self.assertIn("ControlFlow::WaitUntil", self.method("about_to_wait"))

    def test_unresolved_latch_cannot_be_cleared_by_fixture_reconstruction(self):
        source = (ROOT / "experiments/servo-headed-runtime/src/input_ownership.rs").read_text()
        start = source.index("    pub fn reconstruct(")
        method = source[start:source.index("    pub fn current_callback", start)]
        self.assertIn("self.recovery_required.is_some()", method)
        self.assertNotIn("self.recovery_required = None", method)
        self.assertNotIn("self.held_buttons.clear()", method)



class NativeBurstVerifierTests(unittest.TestCase):
    """Real private-file mutation corpus; fixtures do not qualify native Servo."""
    @classmethod
    def setUpClass(cls):
        import ast
        runner = (ROOT / 'tools/run_servo_headed_runtime_gate.sh').read_text()
        body = runner.split("step_run_native_burst_v1() {\nunset PYTHONOPTIMIZE\npython3 - <<'PY'\n", 1)[1].split("\nPY\n}", 1)[0]
        tree = ast.parse(body)
        selected = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
        cls.helper = compile(ast.Module(body=selected, type_ignores=[]), str(ROOT / 'tools/run_servo_headed_runtime_gate.sh'), 'exec')

    def setUp(self):
        import tempfile
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, previous_umask)
        self.namespace = {'root': self.directory, 'READ_LIMIT': 2 * 1024 * 1024, 'observed': {}}
        exec(self.helper, self.namespace)
        binary = self.directory / 'private-binary-metadata-fixture'
        binary.write_bytes(b'file metadata fixture only, not a Servo binary')
        metadata = binary.stat()
        self.binary_identity = {'device': metadata.st_dev, 'inode': metadata.st_ino}
        self.namespace['binary_identity'] = dict(self.binary_identity)
        self.native = {'pid': os.getpid(), 'start_time': 12345, 'ppid': os.getppid(),
                       'pgid': os.getpid(), 'session': os.getpid()}
        self.queue = {'schema': 'trillionnium.desktop.native-input-queue.v1', 'source_only': True,
            'owner_pid': self.native['pid'], 'owner_start_time': 12345, 'qualification_ack_profile': False,
            'queue_idle': True, 'maximum_pending_events': 64, 'maximum_payload_bytes': 16384,
            'busy_episode_budget_seconds': 5, 'ack_is_dom_execution_proof': False, 'product_ready': False,
            'records': []}
        kinds = ['move', 'down', 'up'] * 3
        # All arrivals precede any engine dispatch/ACK: no artificial pacing.
        for index, kind in enumerate(kinds):
            point = [[200, 68], [400, 100], [200, 68]][index // 3]
            item = {'phase': 'admitted', 'sequence': index + 1, 'generation': 1, 'view': 'WebViewId(7)',
                'epoch': 1, 'kind': kind, 'point': point, 'event_id': None, 'source': 'native_winit'}
            self.queue['records'].append(item)
        for item in list(self.queue['records']):
            event = {**item, 'phase': 'submitted', 'event_id': f"InputEventId({item['sequence']})"}
            self.queue['records'].extend([event, {**event, 'phase': 'accepted'}])
        for index, kind in enumerate(['key', 'key', 'wheel', 'synthetic_ime', 'synthetic_ime', 'synthetic_ime'], start=10):
            item = {'phase': 'admitted', 'sequence': index, 'generation': 1, 'view': 'WebViewId(7)',
                'epoch': 1, 'kind': kind, 'point': [200, 68] if kind == 'wheel' else None, 'event_id': None,
                'source': 'qualification_synthetic' if kind == 'synthetic_ime' else 'native_winit'}
            event = {**item, 'phase': 'submitted', 'event_id': f"InputEventId({index})"}
            self.queue['records'].extend([item, event, {**event, 'phase': 'accepted'}])

    def verify(self):
        return self.namespace['verify_queue'](self.queue, self.native)

    def write(self, name, value):
        import json
        (self.directory / name).write_text(json.dumps(value))

    def report_fixture(self):
        initial = {'generation': 1, 'loaded': True, 'pointerDowns': 3, 'documentClickEvents': 3,
            'clicks': 1, 'wheels': 1, 'pointerMoves': 3, 'keyDowns': ['k'], 'popupAttempted': True,
            'externalNavigationAttempted': True, 'inputEventOrderOverflow': False, 'inputEventOrder': []}
        for index in range(9):
            point = [[200, 68], [400, 100], [200, 68]][index // 3]
            initial['inputEventOrder'].append({'sequence': index + 1, 'type': ['pointerdown', 'pointerup', 'click'][index % 3],
                'button': 0, 'x': point[0], 'y': point[1]})
        fault = {'mechanism': 'requested_SIGKILL', 'generation': 1, 'pid': 321, 'start_time': 543, 'exact_termination_observed': True}
        report = {'schema': 'trillionnium.desktop.d0a02-headed-runtime.v1', 'status': 'PASS_HEADED_LOCAL_FIXTURE_ONLY',
            'servo_commit': '670ae8a70801b162e186f81cbb5bdd2d59c39108', 'logical_content_webview_peak': 1,
            'initial_generation': 1, 'recovery_generation': 2, 'initial_page_evidence': initial,
            'recovery_page_evidence': {'generation': 2, 'loaded': True}, 'fault_injection': fault,
            'native_button_events': 6, 'native_keyboard_events': 2, 'synthetic_ime_composition_events': 3, 'input_handled_callbacks': 15,
            'authority': {'fixture_listener_loopback_only': True, 'external_navigation_performed': False,
                'webdriver_listener_started': False, 'browser_actor_started': False, 'agent_port_enabled': False,
                'persistent_credentials_used': False, 'product_ready': False}}
        for key in ('window_created', 'trusted_chrome_separate_from_content', 'chrome_initial_pixels_verified',
                    'chrome_crash_pixels_verified', 'chrome_recovery_pixels_verified', 'content_crash_observed', 'trusted_window_survived_content_crash'):
            report[key] = True
        for key in ('native_pointer_events', 'native_wheel_events', 'native_ime_events', 'input_method_controls',
                    'popup_requests_denied', 'external_navigation_requests_denied'):
            report[key] = 1
        report['native_pointer_events'] = 3
        return report

    def verify_report(self, report):
        # These fixed files exercise validation only, not actual process effects.
        self.write('runtime-result.json', report)
        self.write('native-input-queue.json', self.queue)
        self.write('content-process-identity.json', {'generation': 1, 'pid': 321, 'start_time': 543})
        self.write('content-sigkill-sent.json', {'generation': 1, 'pid': 321, 'start_time': 543, 'signal': 'SIGKILL'})
        self.write('process-topology-pre-burst.json', {
            'schema': 'trillionnium.desktop.native-burst-topology.v1', 'native': self.native,
            'content': {'pid': 321, 'start_time': 543, 'ppid': self.native['pid'],
                        'pgid': self.native['pid'], 'session': self.native['pid']},
            'compiled_executable_device': self.binary_identity['device'], 'compiled_executable_inode': self.binary_identity['inode'],
            'content_process_flag_observed': True, 'retained_content_pidfd_alive_at_capture': True,
            'ipc_token_recorded': False, 'source_qualification_only': True, 'product_ready': False})
        self.write('native-burst-stimulus.json', {'compiled_executable_identity': self.binary_identity})
        (self.directory / 'resource-gate-result.json').write_text('{}')
        for name in ('content-generation-1.png', 'content-generation-2.png', 'workspace-generation-1.png',
                     'workspace-crash-placeholder.png', 'workspace-generation-2.png'):
            (self.directory / name).write_bytes(b'\x89PNG\r\n\x1a\nfixture-only')
        # Resource semantics are already covered by the independent checker and
        # actual CI; this fixture only tests native-file/queue/DOM predicates.
        self.namespace['command'] = lambda *args, **kwargs: ''
        return self.namespace['verify_burst'](self.directory, self.native, 0)

    def test_all_unpaced_arrivals_and_matching_real_id_shape_are_required(self):
        result = self.verify()
        self.assertEqual(len(result['accepted_native_button_event_ids']), 6)
        self.assertEqual(result['accepted_native_button_sequences'], [2, 3, 5, 6, 8, 9])
        self.assertEqual(self.verify_report(self.report_fixture())['actual_dom_document_click_events'], 3)

    def test_default_lane_rejects_nonce_qualification_and_overclaim(self):
        for field in ('qualification_ack_profile', 'product_ready', 'ack_is_dom_execution_proof'):
            with self.subTest(field=field):
                self.queue[field] = True
                with self.assertRaisesRegex(RuntimeError, 'claim/idle'):
                    self.verify()
                self.queue[field] = False

    def test_owner_or_nested_record_schema_cannot_drift(self):
        import copy
        original = copy.deepcopy(self.queue)
        for change in ('bool_owner', 'other_owner', 'extra_nested', 'wrong_epoch'):
            self.queue = copy.deepcopy(original)
            if change == 'bool_owner': self.queue['owner_start_time'] = True
            if change == 'other_owner': self.queue['owner_pid'] += 1
            if change == 'extra_nested': self.queue['records'][0]['production_ready'] = True
            if change == 'wrong_epoch': self.queue['records'][1]['epoch'] += 1
            with self.subTest(change=change), self.assertRaises(RuntimeError): self.verify()

    def test_unknown_reused_ack_and_parallel_submission_never_advance(self):
        import copy
        original = copy.deepcopy(self.queue)
        for change in ('unknown_id', 'reused_id', 'parallel', 'missing_ack'):
            self.queue = copy.deepcopy(original)
            if change == 'unknown_id': self.queue['records'][10]['event_id'] = 'InputEventId(999)'
            if change == 'reused_id': self.queue['records'][11]['event_id'] = 'InputEventId(1)'
            if change == 'parallel': self.queue['records'][10], self.queue['records'][11] = self.queue['records'][11], self.queue['records'][10]
            if change == 'missing_ack': self.queue['records'].pop()
            with self.subTest(change=change), self.assertRaises(RuntimeError): self.verify()

    def test_admission_point_and_original_three_pairs_are_bound(self):
        import copy
        original = copy.deepcopy(self.queue)
        for change in ('point', 'dropped_pair', 'synthetic_button'):
            self.queue = copy.deepcopy(original)
            if change == 'point': self.queue['records'][11]['point'] = [20, 20]
            if change == 'dropped_pair':
                for item in self.queue['records']:
                    if item['sequence'] in (8, 9): item['kind'] = 'key'
            if change == 'synthetic_button':
                for item in self.queue['records']:
                    if item['sequence'] in (2, 3): item['source'] = 'qualification_synthetic'
            with self.subTest(change=change), self.assertRaises(RuntimeError): self.verify()

    def test_actual_dom_click_counter_order_point_and_bounds_remain_required(self):
        import copy
        original = self.report_fixture()
        for change in ('missing_click', 'button_only', 'bool_button_click', 'wrong_order', 'wrong_point', 'overflow'):
            report = copy.deepcopy(original)
            page = report['initial_page_evidence']
            if change == 'missing_click': page['documentClickEvents'] = 2
            if change == 'button_only': page['documentClickEvents'] = 0
            if change == 'bool_button_click': page['clicks'] = True
            if change == 'wrong_order': page['inputEventOrder'][1]['type'] = 'click'
            if change == 'wrong_point': page['inputEventOrder'][0]['x'] += 1
            if change == 'overflow': page['inputEventOrderOverflow'] = True
            with self.subTest(change=change), self.assertRaises(RuntimeError): self.verify_report(report)

    def test_runtime_counter_or_synthetic_triplet_cannot_exceed_actual_ack_chain(self):
        report = self.report_fixture(); report['input_handled_callbacks'] += 1
        with self.assertRaisesRegex(RuntimeError, 'complete ACK chain'):
            self.verify_report(report)
        for item in self.queue['records']:
            if item['sequence'] == 15: item['kind'], item['source'] = 'ime', 'native_winit'
        with self.assertRaisesRegex(RuntimeError, 'three actual matching dispatch completions'):
            self.verify()

    def test_float_runtime_counters_cannot_satisfy_integer_source_contract(self):
        for key in ('synthetic_ime_composition_events', 'input_handled_callbacks'):
            report = self.report_fixture()
            report[key] = float(report[key])
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'counters incomplete'):
                self.verify_report(report)

    def test_actual_process_receipts_refuse_boolean_or_float_identity_fields(self):
        import json
        for name in ('content-process-identity.json', 'content-sigkill-sent.json'):
            for field in ('generation', 'pid', 'start_time'):
                for mutation in ('true', 'false', 'float'):
                    self.verify_report(self.report_fixture())
                    receipt = json.loads((self.directory / name).read_text())
                    receipt[field] = float(receipt[field]) if mutation == 'float' else mutation == 'true'
                    self.write(name, receipt)
                    with self.subTest(name=name, field=field, mutation=mutation), self.assertRaisesRegex(
                        RuntimeError, 'receipt identity must use exact integers'
                    ):
                        self.namespace['verify_burst'](self.directory, self.native, 0)

    def test_actual_process_receipt_fields_signal_and_values_are_closed(self):
        import json
        for name in ('content-process-identity.json', 'content-sigkill-sent.json'):
            for mutation in ('extra', 'missing', 'other_pid', 'signal'):
                self.verify_report(self.report_fixture())
                receipt = json.loads((self.directory / name).read_text())
                if mutation == 'extra': receipt['production_ready'] = True
                if mutation == 'missing': del receipt['start_time']
                if mutation == 'other_pid': receipt['pid'] += 1
                if mutation == 'signal': receipt['signal'] = True
                self.write(name, receipt)
                with self.subTest(name=name, mutation=mutation), self.assertRaises(RuntimeError):
                    self.namespace['verify_burst'](self.directory, self.native, 0)

    def test_burst_refuses_missing_own_topology_even_if_old_text_is_present(self):
        self.verify_report(self.report_fixture())
        (self.directory / 'process-topology-pre-burst.json').unlink()
        (self.directory / 'process-topology.txt').write_text('unrelated_old_runtime --content-process')
        with self.assertRaises(ValueError):
            self.namespace['verify_burst'](self.directory, self.native, 0)

    def test_topology_closed_numeric_incarnation_and_claims_are_required(self):
        import json
        for role in ('native', 'content'):
            for field in ('pid', 'start_time', 'ppid', 'pgid', 'session'):
                for mutation in ('bool', 'float', 'other'):
                    self.verify_report(self.report_fixture())
                    topology = json.loads((self.directory / 'process-topology-pre-burst.json').read_text())
                    value = topology[role][field]
                    topology[role][field] = True if mutation == 'bool' else float(value) if mutation == 'float' else value + 1
                    self.write('process-topology-pre-burst.json', topology)
                    with self.subTest(role=role, field=field, mutation=mutation), self.assertRaises(RuntimeError):
                        self.namespace['verify_burst'](self.directory, self.native, 0)
        for mutation in ('extra', 'nested_extra', 'missing', 'pidfd', 'token', 'production'):
            self.verify_report(self.report_fixture())
            topology = json.loads((self.directory / 'process-topology-pre-burst.json').read_text())
            if mutation == 'extra': topology['copied_from_old_runtime'] = True
            if mutation == 'nested_extra': topology['content']['argv'] = 'hidden-token'
            if mutation == 'missing': del topology['content']['ppid']
            if mutation == 'pidfd': topology['retained_content_pidfd_alive_at_capture'] = False
            if mutation == 'token': topology['ipc_token_recorded'] = True
            if mutation == 'production': topology['product_ready'] = True
            self.write('process-topology-pre-burst.json', topology)
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                self.namespace['verify_burst'](self.directory, self.native, 0)
        for field in ('compiled_executable_device', 'compiled_executable_inode'):
            for mutation in ('bool', 'float', 'other'):
                self.verify_report(self.report_fixture())
                topology = json.loads((self.directory / 'process-topology-pre-burst.json').read_text())
                topology[field] = True if mutation == 'bool' else float(topology[field]) if mutation == 'float' else topology[field] + 1
                self.write('process-topology-pre-burst.json', topology)
                with self.subTest(field=field, mutation=mutation), self.assertRaises(RuntimeError):
                    self.namespace['verify_burst'](self.directory, self.native, 0)

    def test_actual_owned_native_and_content_process_topology_uses_pidfd_and_redacts_token(self):
        import json
        import sys
        script = ('import subprocess,sys,time,signal\n'
                  'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)","--content-process","PRIVATE_IPC_TOKEN"] )\n'
                  'signal.signal(signal.SIGTERM,lambda *args:sys.exit(0))\n'
                  'print("READY",flush=True)\n'
                  'try: time.sleep(30)\n'
                  'finally: child.terminate();child.wait(timeout=3)\n')
        log_path = self.directory / 'actual-owner.log'
        with log_path.open('w') as log:
            process, native = self.namespace['spawn']([sys.executable, '-c', script], dict(os.environ), log)
            try:
                self.namespace['wait_for'](lambda: 'READY' in log_path.read_text(), 5, process)
                metadata = Path(sys.executable).stat()
                identity = {'device': metadata.st_dev, 'inode': metadata.st_ino}
                topology = self.namespace['capture_burst_topology'](process, Path(sys.executable), identity)
                self.namespace['verify_burst_topology'](topology, native,
                    {'generation': 1, 'pid': topology['content']['pid'], 'start_time': topology['content']['start_time']}, identity)
                self.assertNotIn('PRIVATE_IPC_TOKEN', json.dumps(topology))
                self.assertNotIn('argv', json.dumps(topology))
                self.assertTrue(topology['retained_content_pidfd_alive_at_capture'])
            finally:
                self.namespace['cleanup'](process)

    def test_actual_owner_without_a_content_entry_is_refused(self):
        import sys
        with (self.directory / 'actual-no-content.log').open('w') as log:
            process, _ = self.namespace['spawn']([sys.executable, '-c', 'import time;time.sleep(30)'], dict(os.environ), log)
            try:
                with self.assertRaisesRegex(RuntimeError, 'exactly one live owned content'):
                    metadata = Path(sys.executable).stat()
                    self.namespace['capture_burst_topology'](process, Path(sys.executable),
                        {'device': metadata.st_dev, 'inode': metadata.st_ino})
            finally:
                self.namespace['cleanup'](process)

    def test_raw_before_launch_executable_snapshot_cannot_be_retyped_or_replaced(self):
        for field in ('device', 'inode'):
            for mutation in ('bool', 'float', 'other', 'missing', 'extra'):
                self.verify_report(self.report_fixture())
                identity = dict(self.binary_identity)
                if mutation == 'missing': del identity[field]
                elif mutation == 'extra': identity['from_topology'] = True
                else: identity[field] = True if mutation == 'bool' else float(identity[field]) if mutation == 'float' else identity[field] + 1
                self.write('native-burst-stimulus.json', {'compiled_executable_identity': identity})
                with self.subTest(field=field, mutation=mutation), self.assertRaises(RuntimeError):
                    self.namespace['verify_burst'](self.directory, self.native, 0)

    def test_unsent_nonbutton_withdrawal_is_recorded_without_forging_dispatch(self):
        record = {**self.queue['records'][0], 'kind': 'local_ime', 'point': None}
        self.queue['records'].insert(0, record)
        self.queue['records'].insert(1, {**record, 'phase': 'withdrawn_unsent'})
        for item in self.queue['records'][2:]:
            item['sequence'] += 1
        self.assertEqual(len(self.verify()['accepted_native_button_event_ids']), 6)
        self.queue['records'][1]['event_id'] = 'InputEventId(55)'
        with self.assertRaisesRegex(RuntimeError, 'unsent withdrawal'):
            self.verify()

    def test_raw_json_refuses_symlink_hardlink_duplicate_or_nonfinite(self):
        path = self.directory / 'raw.json'
        outside = self.directory / 'other.json'
        outside.write_text('{}')
        path.symlink_to(outside)
        with self.assertRaises(ValueError): self.namespace['read_json'](path)
        path.unlink(); os.link(outside, path)
        with self.assertRaisesRegex(RuntimeError, 'single-link'): self.namespace['read_json'](path)
        path.unlink()
        path.write_text('{}'); path.chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, 'single-link'):
            self.namespace['read_json'](path)
        path.chmod(0o600)
        for data in ('{"x":1,"x":2}', '{"x":1e999}', 'x' * (2 * 1024 * 1024 + 1)):
            path.write_text(data)
            with self.subTest(data=data[:25]), self.assertRaises((ValueError, RuntimeError)):
                self.namespace['read_json'](path)

    def test_raw_metadata_and_named_identity_must_survive_actual_read(self):
        from unittest.mock import patch
        path = self.directory / 'raw.json'; path.write_text('{}')
        real_read = os.read
        fired = False
        def mutated(fd, size):
            nonlocal fired
            result = real_read(fd, size)
            if not fired:
                fired = True
                path.rename(self.directory / 'detached.json')
                path.write_text('{}')
            return result
        with patch.object(os, 'read', side_effect=mutated), self.assertRaisesRegex(RuntimeError, 'pathname changed|changed while reading'):
            self.namespace['read_json'](path)

    def test_engine_key_and_composition_completion_are_gated_by_real_lane_ack(self):
        method = NativeGestureWiringTests.method
        dispatch = method(self, 'drain_native_input')
        self.assertLess(dispatch.index('.reserve_key('), dispatch.index('webview.notify_input_event(payload)'))
        self.assertLess(dispatch.index('.reserve_composition('), dispatch.index('webview.notify_input_event(payload)'))
        self.assertGreater(dispatch.index('.bind_completion(event_id'), dispatch.index('webview.notify_input_event(payload)'))
        callback = method(self, 'notify_input_event_handled')
        self.assertLess(callback.index('NativeAck::Accepted'), callback.index('.accepted(event_id)'))
        self.assertNotIn('webview.notify_input_event', callback)
        withdraw = method(self, 'withdraw_native_input')
        self.assertIn('self.auxiliary.borrow().unsettled()', withdraw)
        self.assertIn('LaneError::OwnershipWithdrawn', withdraw)
        drive = method(self, 'drive')
        fault = drive.split('&& self.initial_page_evidence.borrow().is_some()', 1)[1].split('self.trigger_content_crash()', 1)[0]
        self.assertIn('self.native_lane.borrow().idle()', fault)
        self.assertIn('!self.auxiliary.borrow().unsettled()', fault)

    def test_ci_default_rapid_lane_preserves_original_positive_and_no_up_negatives(self):
        runner = (ROOT / 'tools/run_servo_headed_runtime_gate.sh').read_text()
        body = runner.split('step_run_native_burst_v1() {', 1)[1].split("\nPY\n}", 1)[0]
        self.assertIn("environment.pop('HEPTA_D0A02_INPUT_NONCE', None)", body)
        self.assertNotIn('native_input_checkpoints.py', body)
        stimulus = body.split("arguments = ['xdotool', 'mousemove'", 1)[1].split("facts['original_stimulus_argv']", 1)[0]
        self.assertEqual(stimulus.count("'mousedown', '1'"), 3)
        self.assertEqual(stimulus.count("'mouseup', '1'"), 3)
        self.assertNotIn('time.sleep', stimulus)
        self.assertIn("initial['documentClickEvents'] == 3", body)
        self.assertIn("initial['pointerDowns'] == 3", body)
        self.assertIn("initial['clicks'] > 0", body)
        baseline = subprocess.run(['git', 'show', 'HEAD:tools/run_servo_headed_runtime_gate.sh'], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout
        extract = lambda value: value.split('step_run_held_gestures_v1() {', 1)[1].split('step_run_runtime() {', 1)[0]
        self.assertEqual(extract(runner), extract(baseline))
        workflow = (ROOT / '.github/workflows/servo-headed-runtime.yml').read_text()
        self.assertIn('run-native-burst-v1', workflow)
        self.assertIn('native_input_checkpoints.py drive', workflow)
        self.assertIn('run-held-gestures-v1', workflow)


if __name__ == "__main__":
    unittest.main()
