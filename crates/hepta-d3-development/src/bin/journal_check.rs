//! Verify the exact-image D3 receipt corpus after the persistent daemon stops.

use hepta_session_core::{
    ReceiptEffectClass, ReceiptLifecycleState, ReceiptOutcome, TailStatus, hex_digest,
    inspect_receipt_journal,
};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const EXPECTED_RECEIPTS: [&str; 12] = [
    "d3-health",
    "d3-create",
    "d3-snapshot",
    "d3-navigate-local",
    "d3-observe",
    "d3-wait",
    "d3-extract",
    "d3-stale-document",
    "d3-external-denied",
    "d3-page-act-unsupported",
    "d3-close",
    "d3-post-close-stale",
];

fn main() {
    match run() {
        Ok(report) => {
            if let Err(error) = write_output(&report.output, &report.json) {
                eprintln!("hepta-d3-journal-check: failed to write output: {error}");
                std::process::exit(1);
            }
            println!("{}", report.json);
        }
        Err(error) => {
            eprintln!("hepta-d3-journal-check: {error}");
            std::process::exit(1);
        }
    }
}

fn run() -> Result<CheckResult, CheckError> {
    let mut journal = None;
    let mut output = None;
    let mut arguments = std::env::args().skip(1);
    while let Some(argument) = arguments.next() {
        match argument.as_str() {
            "--journal" => {
                journal = Some(PathBuf::from(
                    arguments
                        .next()
                        .ok_or(CheckError::Usage("--journal requires a value"))?,
                ));
            }
            "--output" => {
                output = Some(PathBuf::from(
                    arguments
                        .next()
                        .ok_or(CheckError::Usage("--output requires a value"))?,
                ));
            }
            "--help" | "-h" => {
                println!("Usage: hepta-d3-journal-check --journal PATH --output PATH");
                std::process::exit(0);
            }
            _ => return Err(CheckError::Usage("unknown argument")),
        }
    }
    let journal = journal.ok_or(CheckError::Usage("--journal is required"))?;
    let output = output.ok_or(CheckError::Usage("--output is required"))?;
    let report = inspect_receipt_journal(&journal)?;
    if report.tail != TailStatus::Clean {
        return Err(CheckError::Invariant("journal tail is not clean"));
    }
    if !report.unresolved.is_empty() {
        return Err(CheckError::Invariant("journal has unresolved receipts"));
    }

    let mut groups = BTreeMap::<String, Vec<_>>::new();
    for record in &report.records {
        groups
            .entry(record.event.receipt_id.clone())
            .or_default()
            .push(record);
    }
    let actual_receipts: BTreeSet<_> = groups.keys().map(String::as_str).collect();
    let expected_receipts: BTreeSet<_> = EXPECTED_RECEIPTS.into_iter().collect();
    if actual_receipts != expected_receipts {
        return Err(CheckError::UnexpectedReceipts {
            expected: expected_receipts.into_iter().map(str::to_owned).collect(),
            actual: actual_receipts.into_iter().map(str::to_owned).collect(),
        });
    }

    let mut completed = 0_usize;
    let mut succeeded = 0_usize;
    let mut refused = 0_usize;
    let mut failed = 0_usize;
    let mut operations = BTreeSet::new();
    let mut principal_bound = true;
    let mut potential_effects_completed_without_execution_claim = 0_usize;

    for (receipt_id, records) in &groups {
        if records.len() != 3
            || records[0].event.lifecycle != ReceiptLifecycleState::Requested
            || records[1].event.lifecycle != ReceiptLifecycleState::Dispatched
            || !records[2].event.lifecycle.is_terminal()
        {
            return Err(CheckError::InvalidLifecycle(receipt_id.clone()));
        }
        if records
            .windows(2)
            .any(|window| window[0].sequence >= window[1].sequence)
        {
            return Err(CheckError::InvalidLifecycle(receipt_id.clone()));
        }
        if records.iter().any(|record| {
            record.event.plan_revision != "2026-08-29-d6"
                || record.event.image_id != "trillionnium-d2i-d3-candidate"
                || record.event.source.as_str() != "agent"
        }) {
            return Err(CheckError::IdentityDrift(receipt_id.clone()));
        }
        principal_bound &= records.iter().all(|record| {
            record
                .event
                .detail
                .as_deref()
                .is_some_and(|detail| detail == "principal=taskflow-d2i-d3")
        });
        operations.insert(records[0].event.operation.clone());
        match records[2].event.lifecycle {
            ReceiptLifecycleState::Completed => {
                completed += 1;
                match records[2].event.outcome {
                    Some(ReceiptOutcome::Succeeded) => succeeded += 1,
                    Some(ReceiptOutcome::Refused) => refused += 1,
                    Some(ReceiptOutcome::Failed | ReceiptOutcome::Cancelled) => failed += 1,
                    None => return Err(CheckError::InvalidLifecycle(receipt_id.clone())),
                }
                if records[2].event.response_sha256.is_none() {
                    return Err(CheckError::InvalidLifecycle(receipt_id.clone()));
                }
                if records[2].event.effect_class == ReceiptEffectClass::PotentialExternalEffect
                    && records[2].event.outcome == Some(ReceiptOutcome::Refused)
                {
                    potential_effects_completed_without_execution_claim += 1;
                }
            }
            ReceiptLifecycleState::Interrupted | ReceiptLifecycleState::Indeterminate => {
                return Err(CheckError::UnexpectedTerminal(receipt_id.clone()));
            }
            ReceiptLifecycleState::Requested | ReceiptLifecycleState::Dispatched => {
                return Err(CheckError::InvalidLifecycle(receipt_id.clone()));
            }
        }
    }

    if !principal_bound {
        return Err(CheckError::Invariant(
            "receipt principal binding is missing",
        ));
    }
    if completed != EXPECTED_RECEIPTS.len() || succeeded != 8 || refused != 2 || failed != 2 {
        return Err(CheckError::UnexpectedOutcomes {
            completed,
            succeeded,
            refused,
            failed,
        });
    }
    if potential_effects_completed_without_execution_claim != 2 {
        return Err(CheckError::Invariant(
            "potential-effect refusal coverage is incomplete",
        ));
    }
    let expected_operations: BTreeSet<String> = [
        "health",
        "session_create",
        "session_snapshot",
        "page_navigate",
        "page_observe",
        "page_wait",
        "page_extract",
        "page_act",
        "session_close",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    if operations != expected_operations {
        return Err(CheckError::UnexpectedOperations {
            expected: expected_operations.into_iter().collect(),
            actual: operations.into_iter().collect(),
        });
    }

    let last_record_sha256 = hex_digest(report.last_record_sha256);
    let json = format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d3-receipt-corpus.v1\",",
            "\"status\":\"PASS\",\"journal_tail_clean\":true,",
            "\"unresolved_receipts\":0,\"receipt_count\":{},",
            "\"record_count\":{},\"completed\":{},\"succeeded\":{},",
            "\"refused\":{},\"failed\":{},\"principal_bound\":true,",
            "\"requested_dispatched_terminal_for_every_receipt\":true,",
            "\"potential_external_effects_never_auto_replayed\":true,",
            "\"last_record_sha256\":\"{}\",",
            "\"product_agent_port_enabled\":false,",
            "\"external_effect_execution_claimed\":false}}"
        ),
        groups.len(),
        report.records.len(),
        completed,
        succeeded,
        refused,
        failed,
        last_record_sha256,
    );
    Ok(CheckResult { output, json })
}

fn write_output(path: &Path, json: &str) -> Result<(), io::Error> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, format!("{json}\n"))
}

struct CheckResult {
    output: PathBuf,
    json: String,
}

#[derive(Debug)]
enum CheckError {
    Io(io::Error),
    Journal(hepta_session_core::JournalError),
    Usage(&'static str),
    Invariant(&'static str),
    InvalidLifecycle(String),
    IdentityDrift(String),
    UnexpectedTerminal(String),
    UnexpectedReceipts {
        expected: Vec<String>,
        actual: Vec<String>,
    },
    UnexpectedOperations {
        expected: Vec<String>,
        actual: Vec<String>,
    },
    UnexpectedOutcomes {
        completed: usize,
        succeeded: usize,
        refused: usize,
        failed: usize,
    },
}

impl fmt::Display for CheckError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "I/O failed: {error}"),
            Self::Journal(error) => write!(formatter, "journal inspection failed: {error}"),
            Self::Usage(message) => write!(formatter, "usage error: {message}"),
            Self::Invariant(message) => write!(formatter, "journal invariant failed: {message}"),
            Self::InvalidLifecycle(receipt) => {
                write!(formatter, "receipt {receipt} has an invalid lifecycle")
            }
            Self::IdentityDrift(receipt) => {
                write!(formatter, "receipt {receipt} changes evidence identity")
            }
            Self::UnexpectedTerminal(receipt) => {
                write!(
                    formatter,
                    "receipt {receipt} has an unexpected terminal state"
                )
            }
            Self::UnexpectedReceipts { expected, actual } => write!(
                formatter,
                "receipt set mismatch: expected {expected:?}, actual {actual:?}"
            ),
            Self::UnexpectedOperations { expected, actual } => write!(
                formatter,
                "operation coverage mismatch: expected {expected:?}, actual {actual:?}"
            ),
            Self::UnexpectedOutcomes {
                completed,
                succeeded,
                refused,
                failed,
            } => write!(
                formatter,
                "outcome counts changed: completed={completed}, succeeded={succeeded}, refused={refused}, failed={failed}"
            ),
        }
    }
}

impl std::error::Error for CheckError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Journal(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for CheckError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<hepta_session_core::JournalError> for CheckError {
    fn from(error: hepta_session_core::JournalError) -> Self {
        Self::Journal(error)
    }
}
