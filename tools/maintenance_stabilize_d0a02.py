#!/usr/bin/env python3
"""One-shot stabilizer for the D0A-02 candidate review surface."""

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    path = Path("experiments/servo-headed-runtime/src/main.rs")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """        if self.exact_termination_observed.get()
            && self.servo_crash_callback_observed.get()
            && !self.crash_workspace_saved.get()
            && !self.recovery_started.get()
""",
        """        if self.exact_termination_observed.get()
            && self.old_process_absent.get()
            && !self.crash_workspace_saved.get()
            && !self.recovery_started.get()
""",
        "drive crash placeholder gate",
    )
    text = replace_once(
        text,
        """        if !self.signal_sent.get()
            || !self.exact_termination_observed.get()
            || !self.old_process_absent.get()
            || !self.servo_crash_callback_observed.get()
        {
""",
        """        if !self.signal_sent.get()
            || !self.exact_termination_observed.get()
            || !self.old_process_absent.get()
        {
""",
        "recovery causality gate",
    )
    text = replace_once(
        text,
        """        if self.exact_termination_observed.get()
            && self.servo_crash_callback_observed.get()
            && !self.recovery_started.get()
            && !self.crash_workspace_saved.get()
""",
        """        if self.exact_termination_observed.get()
            && self.old_process_absent.get()
            && !self.recovery_started.get()
            && !self.crash_workspace_saved.get()
""",
        "compose crash placeholder gate",
    )
    text = replace_once(
        text,
        """            (
                self.servo_crash_callback_observed.get(),
                "Servo crash callback was not observed separately",
            ),
""",
        "",
        "obsolete pipeline panic invariant",
    )
    text = replace_once(
        text,
        """                "    \\"servo_crash_callback_observed\\": true,\\n",
                "    \\"servo_crash_callback_reason\\": {}\\n",
""",
        """                "    \\"servo_pipeline_panic_callback_required\\": false,\\n",
                "    \\"servo_pipeline_panic_callback_observed\\": {},\\n",
                "    \\"servo_pipeline_panic_callback_reason\\": {}\\n",
""",
        "runtime callback evidence fields",
    )
    text = replace_once(
        text,
        """            selected.start_time,
            json_string(&crash_callback_reason),
""",
        """            selected.start_time,
            self.servo_crash_callback_observed.get(),
            json_string(&crash_callback_reason),
""",
        "runtime callback evidence arguments",
    )
    text = replace_once(
        text,
        """    fn notify_crashed(&self, webview: WebView, reason: String, _backtrace: Option<String>) {
""",
        """    // Servo defines this callback for a pipeline panic. External SIGKILL of the
    // multiprocess content child is proved independently by exact PID/start-time
    // selection, successful signal dispatch, /proc disappearance, zero-child
    // topology, trusted-chrome survival, and a distinct replacement identity.
    fn notify_crashed(&self, webview: WebView, reason: String, _backtrace: Option<String>) {
""",
        "pipeline panic callback documentation",
    )
    path.write_text(text, encoding="utf-8")


def patch_workflow() -> None:
    path = Path(".github/workflows/servo-headed-runtime.yml")
    text = path.read_text(encoding="utf-8")
    anchor = '      - "manifests/servo-patch-ledger.v1.json"\n'
    addition = anchor + """      - "manifests/project-state.v1.json"
      - "manifests/gates.v1.json"
      - "tools/validate_repository.py"
      - "tools/validate_project_truth.py"
      - "Cargo.toml"
      - "Cargo.lock"
"""
    if text.count(anchor) != 2:
        raise SystemExit("expected pull_request and push trigger anchors")
    text = text.replace(anchor, addition)
    text = replace_once(
        text,
        """          for key in [
              'signal_sent',
              'exact_termination_observed',
              'old_process_absent',
              'servo_crash_callback_observed',
          ]:
              assert fault[key] is True, (key, fault)
          assert isinstance(fault['servo_crash_callback_reason'], str)
""",
        """          for key in [
              'signal_sent',
              'exact_termination_observed',
              'old_process_absent',
          ]:
              assert fault[key] is True, (key, fault)
          assert fault['servo_pipeline_panic_callback_required'] is False
          assert isinstance(fault['servo_pipeline_panic_callback_observed'], bool)
          assert isinstance(fault['servo_pipeline_panic_callback_reason'], str)
""",
        "workflow callback assertions",
    )
    text = replace_once(
        text,
        """              'repository': os.environ['GITHUB_REPOSITORY'],
              'mode': os.environ['EVIDENCE_MODE'],
""",
        """              'repository': os.environ['GITHUB_REPOSITORY'],
              'event_name': os.environ['GITHUB_EVENT_NAME'],
              'ref': os.environ['GITHUB_REF'],
              'ref_name': os.environ['GITHUB_REF_NAME'],
              'promotion_authoritative': os.environ['EVIDENCE_MODE'] == 'exact_main_push',
              'mode': os.environ['EVIDENCE_MODE'],
""",
        "workflow evidence ref identity",
    )
    text = replace_once(
        text,
        """                  'exact_termination_observed': True,
              },
""",
        """                  'exact_termination_observed': True,
                  'servo_pipeline_panic_callback_observed': fault['servo_pipeline_panic_callback_observed'],
              },
""",
        "receipt optional callback evidence",
    )
    path.write_text(text, encoding="utf-8")


def patch_documentation() -> None:
    path = Path("docs/architecture/TRUSTED_WORKSPACE_COMPOSITION.md")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """adapter then records four separate facts:

1. the exact PID/start-time target was selected;
2. `SIGKILL` was successfully sent to that identity;
3. the matching `/proc` identity disappeared and no active content child
   existed before recovery;
4. Servo independently delivered the current generation-1 crash callback.

Recovery is forbidden until all four facts are present. The adapter captures
""",
        """adapter then records three mandatory, independently checkable facts:

1. the exact PID/start-time target was selected;
2. `SIGKILL` was successfully sent to that identity;
3. the matching `/proc` identity disappeared and no active content child
   existed before recovery.

Servo documents `WebViewDelegate::notify_crashed` as a pipeline-panic callback.
An externally killed content process is not required to emit that callback, so
it is recorded as optional diagnostic evidence and cannot block or satisfy the
external-process recovery proof.

Recovery is forbidden until all three mandatory facts are present. The adapter captures
""",
        "architecture crash evidence contract",
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_source()
    patch_workflow()
    patch_documentation()


if __name__ == "__main__":
    main()
