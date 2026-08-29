#![forbid(unsafe_code)]

//! Deterministic session ownership, revision, bounded queueing, Agent/human
//! arbitration, and durable receipt lifecycle core. No Servo object, socket,
//! clock source, or policy authority is owned by this crate; adapters inject
//! events, monotonic timestamps, and receipt facts.

mod machine;
mod queue;
pub mod receipt_journal;
mod types;

pub use machine::{SessionMachine, SessionSnapshot};
pub use queue::{ArbiterQueue, QueueError};
pub use receipt_journal::{
    ArchivedSegment, CommittedRecord, Digest, EffectClass as ReceiptEffectClass, JournalError,
    JournalId, LifecycleState as ReceiptLifecycleState, OpenPolicy as JournalOpenPolicy,
    PrivacyClass, ReceiptEvent, ReceiptJournal, ReceiptOutcome, ReceiptSource, RecoveryReport,
    RecoveredRecord, ReplayDirective, SegmentHeader, SegmentSeal, TailStatus, UnresolvedReceipt,
    export_redacted_jsonl, hex_digest, inspect_path as inspect_receipt_journal,
    retention_candidates,
};
pub use types::{
    ControlSource, ControlState, DEFAULT_HUMAN_LEASE_TTL_MS, HumanLease, MAX_HUMAN_LEASE_TTL_MS,
    SessionEffect, SessionEvent, SessionPhase, TransitionError,
};

#[cfg(test)]
mod tests;
