#![forbid(unsafe_code)]

//! Deterministic session ownership, revision, bounded queueing, Agent/human
//! arbitration, and durable receipt lifecycle core. No Servo object, socket,
//! clock source, or policy authority is owned by this crate; adapters inject
//! events, monotonic timestamps, and receipt facts.

mod admission;
mod authoritative_export;
mod machine;
mod queue;
#[path = "receipt_journal.rs"]
mod receipt_journal_impl;
mod types;

/// Compatibility namespace for bounded chain limits only.
///
/// The journal implementation is intentionally not public as a module because
/// its historical report-based export functions accept caller-constructible
/// recovery data. Evidence-bearing export is available only through the
/// path-verified crate-root functions.
pub mod receipt_journal {
    pub use super::receipt_journal_impl::{MAX_CHAIN_BYTES, MAX_CHAIN_RECORDS, MAX_CHAIN_SEGMENTS};

    pub(crate) use super::receipt_journal_impl::{
        Digest, EffectClass, JournalError, JournalId, LifecycleState, PrivacyClass,
        ReceiptEnvelope, ReceiptEvent, ReceiptJournal, ReceiptOutcome, ReceiptSource,
        RecoveredRecord, RecoveryReport, TailStatus, export_journal_redacted_jsonl,
        export_receipt_envelopes_jsonl, inspect_chain, inspect_path,
    };
}

pub use admission::SessionMachine;
pub use authoritative_export::{
    export_forensic_prefix_jsonl, export_receipt_envelopes_jsonl, export_redacted_jsonl,
};
pub use machine::SessionSnapshot;
pub use queue::{ArbiterQueue, QueueError};
pub use receipt_journal_impl::{
    ArchivedSegment, CommittedRecord, CopiedReceiptSegment, Digest,
    EffectClass as ReceiptEffectClass, JournalError, JournalId,
    LifecycleState as ReceiptLifecycleState, MAX_CHAIN_BYTES, MAX_CHAIN_RECORDS,
    MAX_CHAIN_SEGMENTS, ManagedOpenPolicy, OpenPolicy as JournalOpenPolicy, PrivacyClass,
    ReceiptEnvelope, ReceiptEvent, ReceiptJournal, ReceiptMigrationReport, ReceiptOutcome,
    ReceiptSource, ReceiptStatus, RecoveredRecord, RecoveryReport, ReplayDirective, SegmentHeader,
    SegmentSeal, TailStatus, UnresolvedReceipt, hex_digest, inspect_chain,
    inspect_path as inspect_receipt_journal, retention_candidates,
};
pub use types::{
    ControlSource, ControlState, DEFAULT_HUMAN_LEASE_TTL_MS, HumanLease, MAX_HUMAN_LEASE_TTL_MS,
    SessionEffect, SessionEvent, SessionPhase, TransitionError,
};

#[cfg(test)]
mod tests;
