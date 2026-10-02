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

    def test_native_button_forwarding_requires_current_owned_down_or_up_route(self):
        source = self.method("forward_mouse_button")
        self.assertIn("route_button(", source)
        self.assertIn("self.generation.get()", source)
        self.assertIn("owned_button", source)
        self.assertIn("owned_action", source)
        self.assertLess(source.index("route_button("), source.index("MouseButtonEvent::new("))
        self.assertIn("let Some((x, y)) = point else", source)

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
        dispatch = self.method("forward_mouse_button")
        self.assertIn("let event_id = webview.notify_input_event(", dispatch)
        self.assertIn("if owned_action == ButtonAction::Up", dispatch)
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
        self.assertEqual(source.count("state.input.borrow_mut().crashed();\n"),
                         source.count("state.input.borrow_mut().crashed();\n                    state.retire_withdrawn_gesture();")
                         + source.count("state.input.borrow_mut().crashed();\n                state.retire_withdrawn_gesture();")
                         + source.count("state.input.borrow_mut().crashed();\n            state.retire_withdrawn_gesture();"))

    def test_unresolved_latch_cannot_be_cleared_by_fixture_reconstruction(self):
        source = (ROOT / "experiments/servo-headed-runtime/src/input_ownership.rs").read_text()
        start = source.index("    pub fn reconstruct(")
        method = source[start:source.index("    pub fn current_callback", start)]
        self.assertIn("self.recovery_required.is_some()", method)
        self.assertNotIn("self.recovery_required = None", method)
        self.assertNotIn("self.held_buttons.clear()", method)


if __name__ == "__main__":
    unittest.main()
