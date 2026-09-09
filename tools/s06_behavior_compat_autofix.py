#!/usr/bin/env python3
"""Close current-stack S06 behavior compatibility gaps without widening authority."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "crates/hepta-browser-actor-simulation/src/lib.rs"


def replace_once(old: str, new: str, label: str) -> None:
    text = SOURCE.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    SOURCE.write_text(text.replace(old, new, 1), encoding="utf-8")


def close_navigation_control_gap() -> None:
    old = '''            BrowserOperation::PageNavigate {
                target,
                expected_document_generation,
            } => {
                let page_snapshot = self.page.as_ref().expect("PageOwner exists").snapshot();
                if page_snapshot.session.revisions.document_generation
                    != *expected_document_generation
                {
                    failure(
                        BrowserErrorCode::StaleDocument,
                        "expected_document_generation is stale",
                    )
                } else {
'''
    new = '''            BrowserOperation::PageNavigate {
                target,
                expected_document_generation,
            } => {
                let page_snapshot = self.page.as_ref().expect("PageOwner exists").snapshot();
                let control_failure = match page_snapshot.session.control {
                    ControlState::HumanActive => Some(failure(
                        BrowserErrorCode::HumanControlActive,
                        "human control lease is active",
                    )),
                    ControlState::HumanImeComposing => Some(failure(
                        BrowserErrorCode::ImeCompositionActive,
                        "human IME composition is active",
                    )),
                    ControlState::Idle => None,
                    ControlState::AgentObserving | ControlState::AgentMutating => Some(failure(
                        BrowserErrorCode::Internal,
                        "Agent control is already active",
                    )),
                };
                if let Some(outcome) = control_failure {
                    outcome
                } else if page_snapshot.session.revisions.document_generation
                    != *expected_document_generation
                {
                    failure(
                        BrowserErrorCode::StaleDocument,
                        "expected_document_generation is stale",
                    )
                } else {
'''
    replace_once(old, new, "PageNavigate control preflight")


def close_terminal_reference_gap() -> None:
    old = '''fn reference_error(
    target: &ElementReference,
    revisions: RevisionClock,
) -> Option<BrowserErrorCode> {
    match classify_reference(
        revisions,
        target.session_generation,
        target.document_generation,
        target.semantic_snapshot_revision,
    ) {
'''
    new = '''fn reference_error(
    target: &ElementReference,
    revisions: RevisionClock,
) -> Option<BrowserErrorCode> {
    // The signed Browser API wire envelope reserves its final representable
    // revision for fail-closed recovery. A terminal current/target value must
    // never compare as fresh merely because both sides contain the same
    // sentinel. Preserve layer precedence so callers receive the strongest
    // stale identity class before any runtime work.
    const LAST_SAFE_REVISION: u64 = i64::MAX as u64 - 1;
    if revisions.session_generation >= LAST_SAFE_REVISION
        || target.session_generation >= LAST_SAFE_REVISION
    {
        return Some(BrowserErrorCode::StaleSession);
    }
    if revisions.document_generation >= LAST_SAFE_REVISION
        || target.document_generation >= LAST_SAFE_REVISION
    {
        return Some(BrowserErrorCode::StaleDocument);
    }
    if revisions.semantic_snapshot_revision >= LAST_SAFE_REVISION
        || target.semantic_snapshot_revision >= LAST_SAFE_REVISION
    {
        return Some(BrowserErrorCode::StaleSnapshot);
    }
    match classify_reference(
        revisions,
        target.session_generation,
        target.document_generation,
        target.semantic_snapshot_revision,
    ) {
'''
    replace_once(old, new, "terminal reference classification")


def decouple_internal_error_tests_from_redacted_display() -> None:
    old = '''        assert!(error.to_string().contains("logical clock exhausted"));
        assert!(observer.inflight.is_empty());
        assert!(observer.inspect().expect("inspect").records.is_empty());
'''
    new = '''        assert!(matches!(
            error,
            AgentPortError::Handler(ref message)
                if message == "receipt logical clock exhausted"
        ));
        assert!(observer.inflight.is_empty());
        assert!(observer.inspect().expect("inspect").records.is_empty());
'''
    replace_once(old, new, "requested logical-clock assertion")

    old = '''        assert!(error.to_string().contains("logical clock exhausted"));
        assert!(observer.inflight.is_empty());
        assert_eq!(
            observer.inspect().expect("inspect").records.len(),
'''
    new = '''        assert!(matches!(
            error,
            AgentPortError::Handler(ref message)
                if message == "receipt logical clock exhausted"
        ));
        assert!(observer.inflight.is_empty());
        assert_eq!(
            observer.inspect().expect("inspect").records.len(),
'''
    replace_once(old, new, "dispatched logical-clock assertion")


def bind_machine_contract() -> None:
    path = ROOT / "contracts/browser-actor.v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    actor = value["browser_actor"]
    actor["agent_navigation_requires_idle_control_before_runtime"] = True
    actor["human_focus_navigation_result"] = "human_control_active"
    actor["ime_navigation_result"] = "ime_composition_active"
    actor["other_agent_control_navigation_result"] = "internal_fail_closed"
    actor["terminal_revision_reference_is_never_current"] = True
    value["receipts"]["internal_error_text_exposed_by_display"] = False
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def extend_authority_tests() -> None:
    path = ROOT / "tests/test_s06_browser_actor.py"
    text = path.read_text(encoding="utf-8")
    old = '''        self.assertTrue(
            contract["browser_actor"]["final_success_released_after_peer_revalidation"]
        )
        self.assertFalse(contract["browser_actor"]["generic_runtime_injection"])
        self.assertFalse(contract["receipts"]["journal_authorizes_execution"])
'''
    new = '''        self.assertTrue(
            contract["browser_actor"]["final_success_released_after_peer_revalidation"]
        )
        self.assertFalse(contract["browser_actor"]["generic_runtime_injection"])
        self.assertTrue(
            contract["browser_actor"][
                "agent_navigation_requires_idle_control_before_runtime"
            ]
        )
        self.assertTrue(
            contract["browser_actor"][
                "terminal_revision_reference_is_never_current"
            ]
        )
        self.assertFalse(
            contract["receipts"]["internal_error_text_exposed_by_display"]
        )
        self.assertFalse(contract["receipts"]["journal_authorizes_execution"])
'''
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"authority contract test insertion: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    close_navigation_control_gap()
    close_terminal_reference_gap()
    decouple_internal_error_tests_from_redacted_display()
    bind_machine_contract()
    extend_authority_tests()


if __name__ == "__main__":
    main()
