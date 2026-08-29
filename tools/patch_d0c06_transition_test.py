#!/usr/bin/env python3
from pathlib import Path

path = Path("crates/hepta-session-core/src/receipt_journal.rs")
text = path.read_text(encoding="utf-8")
old = """        let error = journal
            .append(event(\"receipt-1\", LifecycleState::Completed))
            .expect_err(\"completion before request must fail\");
        assert!(matches!(error, JournalError::InvalidTransition { .. }));
"""
new = """        let mut completed = event(\"receipt-1\", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(2));
        let error = journal
            .append(completed)
            .expect_err(\"completion before request must fail\");
        assert!(matches!(error, JournalError::InvalidTransition { .. }));
"""
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one lifecycle test block, found {count}")
path.write_text(text.replace(old, new), encoding="utf-8")
