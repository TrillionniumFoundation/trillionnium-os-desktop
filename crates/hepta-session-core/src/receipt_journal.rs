//! Durable, hash-chained operation receipts.
//!
//! The journal is deliberately independent from Servo and from policy
//! authority. It records admitted lifecycle facts and never replays an
//! operation. A potential external effect that was dispatched without a
//! terminal receipt is always recovered as `NeverAutomatic`.

use sha2::{Digest as _, Sha256};
use std::collections::HashMap;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};

pub type Digest = [u8; 32];

const SEGMENT_MAGIC: &[u8; 8] = b"HPTJRNL1";
const RECORD_MAGIC: &[u8; 8] = b"HPTREC01";
const FORMAT_VERSION: u16 = 1;
const SEGMENT_HEADER_PREFIX_LEN: usize = 116;
const SEGMENT_HEADER_LEN: usize = 148;
const RECORD_PREFIX_LEN: usize = 208;
const RECORD_DIGEST_LEN: usize = 32;
const MAX_RECORD_PAYLOAD_BYTES: usize = 64 * 1024;
const MAX_SEGMENT_BYTES: u64 = 64 * 1024 * 1024;
const MAX_DETAIL_BYTES: usize = 4096;
const WRITER_LOCK_SUFFIX: &str = "writer-lock";
const ZERO_DIGEST: Digest = [0; 32];

// The product is Linux-only.  Keep the final path component pinned while
// opening an existing journal; this prevents a symlink swap between the
// metadata preflight and the actual open.  The fallback preserves compilation
// for other Unix targets, where their platform-specific no-follow constant is
// not part of Rust's standard library.
#[cfg(target_os = "linux")]
const OPEN_NOFOLLOW_FLAG: i32 = 0o400000; // O_NOFOLLOW from asm-generic/fcntl.h
#[cfg(not(target_os = "linux"))]
const OPEN_NOFOLLOW_FLAG: i32 = 0;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum LifecycleState {
    Requested = 1,
    Dispatched = 2,
    Completed = 3,
    Indeterminate = 4,
    Interrupted = 5,
}

impl LifecycleState {
    fn from_wire(value: u8) -> Result<Self, JournalError> {
        match value {
            1 => Ok(Self::Requested),
            2 => Ok(Self::Dispatched),
            3 => Ok(Self::Completed),
            4 => Ok(Self::Indeterminate),
            5 => Ok(Self::Interrupted),
            _ => Err(JournalError::InvalidRecord("unknown lifecycle state")),
        }
    }

    pub const fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Indeterminate | Self::Interrupted
        )
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Requested => "requested",
            Self::Dispatched => "dispatched",
            Self::Completed => "completed",
            Self::Indeterminate => "indeterminate",
            Self::Interrupted => "interrupted",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum ReceiptOutcome {
    Succeeded = 1,
    Failed = 2,
    Refused = 3,
    Cancelled = 4,
}

/// The status vocabulary used by the public `receipt.v1` operation envelope.
///
/// The durable journal intentionally stores the finer-grained requested and
/// dispatched lifecycle facts.  An envelope is emitted only after that
/// lifecycle has reached a terminal state, so the two pre-dispatch states do
/// not appear in this enum.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReceiptStatus {
    Succeeded,
    Failed,
    Refused,
    Cancelled,
    Interrupted,
    Indeterminate,
}

impl ReceiptStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Succeeded => "succeeded",
            Self::Failed => "failed",
            Self::Refused => "refused",
            Self::Cancelled => "cancelled",
            Self::Interrupted => "interrupted",
            Self::Indeterminate => "indeterminate",
        }
    }

    const fn requires_error(self) -> bool {
        !matches!(self, Self::Succeeded)
    }
}

/// Canonical operation-evidence projection defined by
/// `contracts/receipt.v1.schema.json`.
///
/// `ReceiptEvent` remains the append-only lifecycle record.  This projection
/// deliberately omits journal-only fields (effect/privacy classes and request
/// or response digests) because they are not members of the v1 envelope
/// schema.  The journal still retains those fields and its hash chain remains
/// the authoritative durability/recovery evidence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ReceiptEnvelope {
    pub schema: String,
    pub receipt_id: String,
    pub plan_revision: String,
    pub image_id: String,
    pub servo_commit: String,
    pub browserd_version: String,
    pub session_id: String,
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub mutation_epoch: u64,
    pub source: ReceiptSource,
    pub operation: String,
    pub status: ReceiptStatus,
    pub error_code: Option<String>,
    pub started_monotonic_ms: u64,
    pub finished_monotonic_ms: u64,
    pub wall_clock_unix_ms: Option<u64>,
}

impl ReceiptEnvelope {
    pub const SCHEMA: &'static str = "trillionnium.desktop.receipt.v1";

    /// Build one envelope from all lifecycle records for one receipt ID.
    ///
    /// A missing terminal record is an export error rather than an invented
    /// status.  This is intentionally fail-closed: callers must reconcile an
    /// unresolved journal entry and append its `interrupted` or
    /// `indeterminate` terminal fact before publishing operation evidence.
    pub fn from_records(records: &[RecoveredRecord]) -> Result<Self, JournalError> {
        let first = records.first().ok_or_else(|| {
            JournalError::InvalidInput("cannot build an envelope from no records".into())
        })?;
        let first_event = &first.event;
        if first_event.lifecycle != LifecycleState::Requested {
            return Err(JournalError::InvalidInput(format!(
                "receipt {} does not begin with requested lifecycle",
                first_event.receipt_id
            )));
        }
        if records
            .iter()
            .any(|record| record.event.receipt_id != first_event.receipt_id)
        {
            return Err(JournalError::InvalidInput(
                "envelope records contain multiple receipt identifiers".into(),
            ));
        }
        let Some(terminal_index) = records
            .iter()
            .position(|record| record.event.lifecycle.is_terminal())
        else {
            return Err(JournalError::InvalidInput(format!(
                "receipt {} has no terminal lifecycle record",
                first_event.receipt_id
            )));
        };
        if terminal_index + 1 != records.len() {
            return Err(JournalError::InvalidInput(format!(
                "receipt {} has lifecycle records after its terminal record",
                first_event.receipt_id
            )));
        }

        let mut previous_lifecycle = None;
        // Identity and operation metadata are part of the evidence binding.
        // Do not silently choose one value if a malformed/corrupt report has
        // mixed metadata across lifecycle records.
        for record in records {
            let event = &record.event;
            event.validate()?;
            validate_transition(&event.receipt_id, previous_lifecycle, event.lifecycle)?;
            previous_lifecycle = Some(event.lifecycle);
            if event.plan_revision != first_event.plan_revision
                || event.image_id != first_event.image_id
                || event.servo_commit != first_event.servo_commit
                || event.browserd_version != first_event.browserd_version
                || event.session_id != first_event.session_id
                || event.session_generation != first_event.session_generation
                || event.document_generation != first_event.document_generation
                || event.semantic_snapshot_revision != first_event.semantic_snapshot_revision
                || event.mutation_epoch != first_event.mutation_epoch
                || event.source != first_event.source
                || event.operation != first_event.operation
            {
                return Err(JournalError::InvalidInput(format!(
                    "receipt {} changes identity or operation metadata across lifecycle",
                    first_event.receipt_id
                )));
            }
        }

        let terminal = &records[terminal_index].event;
        if terminal.monotonic_ms < first_event.monotonic_ms {
            return Err(JournalError::InvalidInput(format!(
                "receipt {} terminal monotonic time precedes admission",
                first_event.receipt_id
            )));
        }
        let status = match terminal.lifecycle {
            LifecycleState::Completed => match terminal.outcome {
                Some(ReceiptOutcome::Succeeded) => ReceiptStatus::Succeeded,
                Some(ReceiptOutcome::Failed) => ReceiptStatus::Failed,
                Some(ReceiptOutcome::Refused) => ReceiptStatus::Refused,
                Some(ReceiptOutcome::Cancelled) => ReceiptStatus::Cancelled,
                None => {
                    return Err(JournalError::InvalidInput(
                        "completed receipt has no terminal outcome".into(),
                    ));
                }
            },
            LifecycleState::Interrupted => ReceiptStatus::Interrupted,
            LifecycleState::Indeterminate => ReceiptStatus::Indeterminate,
            LifecycleState::Requested | LifecycleState::Dispatched => {
                return Err(JournalError::InvalidInput(
                    "non-terminal lifecycle cannot produce an envelope".into(),
                ));
            }
        };

        let envelope = Self {
            schema: Self::SCHEMA.to_owned(),
            receipt_id: first_event.receipt_id.clone(),
            plan_revision: first_event.plan_revision.clone(),
            image_id: first_event.image_id.clone(),
            servo_commit: first_event.servo_commit.clone(),
            browserd_version: first_event.browserd_version.clone(),
            session_id: first_event.session_id.clone(),
            session_generation: first_event.session_generation,
            document_generation: first_event.document_generation,
            semantic_snapshot_revision: first_event.semantic_snapshot_revision,
            mutation_epoch: first_event.mutation_epoch,
            source: first_event.source,
            operation: first_event.operation.clone(),
            status,
            error_code: terminal.error_code.clone(),
            started_monotonic_ms: first_event.monotonic_ms,
            finished_monotonic_ms: terminal.monotonic_ms,
            wall_clock_unix_ms: Some(terminal.wall_clock_unix_ms),
        };
        envelope.validate()?;
        Ok(envelope)
    }

    /// Validate the exact field/value constraints represented by
    /// `contracts/receipt.v1.schema.json` before serializing.
    pub fn validate(&self) -> Result<(), JournalError> {
        if self.schema != Self::SCHEMA {
            return Err(JournalError::InvalidInput(
                "receipt envelope schema identifier is invalid".into(),
            ));
        }
        validate_token("receipt_id", &self.receipt_id, 1, 128)?;
        validate_plan_revision(&self.plan_revision)?;
        validate_token("image_id", &self.image_id, 1, 128)?;
        validate_lower_hex("servo_commit", &self.servo_commit, 40)?;
        validate_text("browserd_version", &self.browserd_version, 1, 64)?;
        validate_token("session_id", &self.session_id, 1, 128)?;
        if self.session_generation == 0 {
            return Err(JournalError::InvalidInput(
                "receipt envelope session_generation must be non-zero".into(),
            ));
        }
        if self.document_generation == 0 {
            return Err(JournalError::InvalidInput(
                "receipt envelope document_generation must be non-zero".into(),
            ));
        }
        validate_operation(&self.operation)?;
        if self.status.requires_error() {
            let Some(error_code) = self.error_code.as_deref() else {
                return Err(JournalError::InvalidInput(
                    "non-success receipt envelope requires error_code".into(),
                ));
            };
            validate_error_code(error_code)?;
        } else if self.error_code.is_some() {
            return Err(JournalError::InvalidInput(
                "successful receipt envelope may not carry error_code".into(),
            ));
        }
        if self.finished_monotonic_ms < self.started_monotonic_ms {
            return Err(JournalError::InvalidInput(
                "receipt envelope finished_monotonic_ms precedes started_monotonic_ms".into(),
            ));
        }
        Ok(())
    }

    /// Serialize with stable field ordering and no fields outside receipt.v1.
    pub fn to_canonical_json(&self) -> Result<String, JournalError> {
        self.validate()?;
        let mut output = String::new();
        output.push_str("{\"schema\":\"");
        output.push_str(&json_escape(&self.schema));
        output.push_str("\",\"receipt_id\":\"");
        output.push_str(&json_escape(&self.receipt_id));
        output.push_str("\",\"plan_revision\":\"");
        output.push_str(&json_escape(&self.plan_revision));
        output.push_str("\",\"image_id\":\"");
        output.push_str(&json_escape(&self.image_id));
        output.push_str("\",\"servo_commit\":\"");
        output.push_str(&json_escape(&self.servo_commit));
        output.push_str("\",\"browserd_version\":\"");
        output.push_str(&json_escape(&self.browserd_version));
        output.push_str("\",\"session_id\":\"");
        output.push_str(&json_escape(&self.session_id));
        output.push_str("\",\"session_generation\":");
        output.push_str(&self.session_generation.to_string());
        output.push_str(",\"document_generation\":");
        output.push_str(&self.document_generation.to_string());
        output.push_str(",\"semantic_snapshot_revision\":");
        output.push_str(&self.semantic_snapshot_revision.to_string());
        output.push_str(",\"mutation_epoch\":");
        output.push_str(&self.mutation_epoch.to_string());
        output.push_str(",\"source\":\"");
        output.push_str(self.source.as_str());
        output.push_str("\",\"operation\":\"");
        output.push_str(&json_escape(&self.operation));
        output.push_str("\",\"status\":\"");
        output.push_str(self.status.as_str());
        if let Some(error_code) = &self.error_code {
            output.push_str("\",\"error_code\":\"");
            output.push_str(&json_escape(error_code));
        }
        output.push_str("\",\"started_monotonic_ms\":");
        output.push_str(&self.started_monotonic_ms.to_string());
        output.push_str(",\"finished_monotonic_ms\":");
        output.push_str(&self.finished_monotonic_ms.to_string());
        if let Some(wall_clock_unix_ms) = self.wall_clock_unix_ms {
            output.push_str(",\"wall_clock_unix_ms\":");
            output.push_str(&wall_clock_unix_ms.to_string());
        }
        output.push('}');
        Ok(output)
    }
}

impl ReceiptOutcome {
    fn from_wire(value: u8) -> Result<Option<Self>, JournalError> {
        match value {
            0 => Ok(None),
            1 => Ok(Some(Self::Succeeded)),
            2 => Ok(Some(Self::Failed)),
            3 => Ok(Some(Self::Refused)),
            4 => Ok(Some(Self::Cancelled)),
            _ => Err(JournalError::InvalidRecord("unknown receipt outcome")),
        }
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Succeeded => "succeeded",
            Self::Failed => "failed",
            Self::Refused => "refused",
            Self::Cancelled => "cancelled",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum ReceiptSource {
    Agent = 1,
    Human = 2,
    System = 3,
}

impl ReceiptSource {
    fn from_wire(value: u8) -> Result<Self, JournalError> {
        match value {
            1 => Ok(Self::Agent),
            2 => Ok(Self::Human),
            3 => Ok(Self::System),
            _ => Err(JournalError::InvalidRecord("unknown receipt source")),
        }
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Agent => "agent",
            Self::Human => "human",
            Self::System => "system",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum EffectClass {
    Observation = 1,
    LocalInteraction = 2,
    PotentialExternalEffect = 3,
}

impl EffectClass {
    fn from_wire(value: u8) -> Result<Self, JournalError> {
        match value {
            1 => Ok(Self::Observation),
            2 => Ok(Self::LocalInteraction),
            3 => Ok(Self::PotentialExternalEffect),
            _ => Err(JournalError::InvalidRecord("unknown effect class")),
        }
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Observation => "observation",
            Self::LocalInteraction => "local_interaction",
            Self::PotentialExternalEffect => "potential_external_effect",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum PrivacyClass {
    Public = 1,
    Internal = 2,
    Sensitive = 3,
    SecretRedacted = 4,
}

impl PrivacyClass {
    fn from_wire(value: u8) -> Result<Self, JournalError> {
        match value {
            1 => Ok(Self::Public),
            2 => Ok(Self::Internal),
            3 => Ok(Self::Sensitive),
            4 => Ok(Self::SecretRedacted),
            _ => Err(JournalError::InvalidRecord("unknown privacy class")),
        }
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Public => "public",
            Self::Internal => "internal",
            Self::Sensitive => "sensitive",
            Self::SecretRedacted => "secret_redacted",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReplayDirective {
    CallerMayReadmit,
    CallerMayReobserve,
    NeverAutomatic,
}

impl ReplayDirective {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::CallerMayReadmit => "caller_may_readmit",
            Self::CallerMayReobserve => "caller_may_reobserve",
            Self::NeverAutomatic => "never_automatic",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ReceiptEvent {
    pub receipt_id: String,
    pub plan_revision: String,
    pub image_id: String,
    pub servo_commit: String,
    pub browserd_version: String,
    pub session_id: String,
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub mutation_epoch: u64,
    pub source: ReceiptSource,
    pub operation: String,
    pub lifecycle: LifecycleState,
    pub outcome: Option<ReceiptOutcome>,
    pub effect_class: EffectClass,
    pub privacy_class: PrivacyClass,
    pub request_sha256: Digest,
    pub response_sha256: Option<Digest>,
    pub error_code: Option<String>,
    pub detail: Option<String>,
    pub monotonic_ms: u64,
    pub wall_clock_unix_ms: u64,
}

impl ReceiptEvent {
    pub fn validate(&self) -> Result<(), JournalError> {
        validate_token("receipt_id", &self.receipt_id, 1, 128)?;
        validate_plan_revision(&self.plan_revision)?;
        validate_token("image_id", &self.image_id, 1, 128)?;
        validate_lower_hex("servo_commit", &self.servo_commit, 40)?;
        validate_text("browserd_version", &self.browserd_version, 1, 64)?;
        validate_token("session_id", &self.session_id, 1, 128)?;
        validate_operation(&self.operation)?;
        if self.session_generation == 0 {
            return Err(JournalError::InvalidInput(
                "session_generation must be non-zero".into(),
            ));
        }
        if self.document_generation == 0 {
            return Err(JournalError::InvalidInput(
                "document_generation must be non-zero".into(),
            ));
        }
        if self.request_sha256 == ZERO_DIGEST {
            return Err(JournalError::InvalidInput(
                "request_sha256 must not be all zero".into(),
            ));
        }
        if self.response_sha256 == Some(ZERO_DIGEST) {
            return Err(JournalError::InvalidInput(
                "response_sha256 must not be all zero when present".into(),
            ));
        }
        if let Some(error_code) = &self.error_code {
            validate_error_code(error_code)?;
        }
        if let Some(detail) = &self.detail {
            validate_text("detail", detail, 0, MAX_DETAIL_BYTES)?;
        }
        if self.privacy_class == PrivacyClass::SecretRedacted && self.detail.is_some() {
            return Err(JournalError::InvalidInput(
                "secret_redacted receipts may not persist detail".into(),
            ));
        }

        match self.lifecycle {
            LifecycleState::Requested | LifecycleState::Dispatched => {
                if self.outcome.is_some()
                    || self.response_sha256.is_some()
                    || self.error_code.is_some()
                {
                    return Err(JournalError::InvalidInput(
                        "requested/dispatched events cannot carry outcome, response, or error"
                            .into(),
                    ));
                }
            }
            LifecycleState::Completed => {
                let outcome = self.outcome.ok_or_else(|| {
                    JournalError::InvalidInput("completed event requires a terminal outcome".into())
                })?;
                if self.response_sha256.is_none() {
                    return Err(JournalError::InvalidInput(
                        "completed event requires response_sha256".into(),
                    ));
                }
                if outcome == ReceiptOutcome::Succeeded && self.error_code.is_some() {
                    return Err(JournalError::InvalidInput(
                        "successful completion cannot carry error_code".into(),
                    ));
                }
                if outcome != ReceiptOutcome::Succeeded && self.error_code.is_none() {
                    return Err(JournalError::InvalidInput(
                        "non-success completion requires error_code".into(),
                    ));
                }
            }
            LifecycleState::Indeterminate | LifecycleState::Interrupted => {
                if self.outcome.is_some() || self.response_sha256.is_some() {
                    return Err(JournalError::InvalidInput(
                        "indeterminate/interrupted events cannot claim an outcome or response"
                            .into(),
                    ));
                }
                if self.error_code.is_none() {
                    return Err(JournalError::InvalidInput(
                        "indeterminate/interrupted events require error_code".into(),
                    ));
                }
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct JournalId(pub [u8; 16]);

impl JournalId {
    pub fn validate(self) -> Result<(), JournalError> {
        if self.0 == [0; 16] {
            Err(JournalError::InvalidInput(
                "journal_id must not be all zero".into(),
            ))
        } else {
            Ok(())
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SegmentHeader {
    pub journal_id: JournalId,
    pub segment_number: u64,
    pub first_sequence: u64,
    pub previous_segment_sha256: Digest,
    pub previous_record_sha256: Digest,
    pub created_wall_clock_unix_ms: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveredRecord {
    pub sequence: u64,
    pub record_sha256: Digest,
    pub event: ReceiptEvent,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TailStatus {
    Clean,
    TornTail {
        offset: u64,
        bytes_available: usize,
        bytes_expected: Option<usize>,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnresolvedReceipt {
    pub receipt_id: String,
    pub last_state: LifecycleState,
    pub effect_class: EffectClass,
    pub replay: ReplayDirective,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveryReport {
    pub header: SegmentHeader,
    pub records: Vec<RecoveredRecord>,
    pub tail: TailStatus,
    pub last_complete_offset: u64,
    pub next_sequence: u64,
    pub last_record_sha256: Digest,
    pub unresolved: Vec<UnresolvedReceipt>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct OpenPolicy {
    pub repair_torn_tail: bool,
    pub recover_stale_writer_lease: bool,
}

impl OpenPolicy {
    pub const STRICT: Self = Self {
        repair_torn_tail: false,
        recover_stale_writer_lease: false,
    };

    pub const RECOVER_CRASH: Self = Self {
        repair_torn_tail: true,
        recover_stale_writer_lease: true,
    };
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CommittedRecord {
    pub sequence: u64,
    pub record_sha256: Digest,
    pub end_offset: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SegmentSeal {
    pub segment_number: u64,
    pub bytes: u64,
    pub segment_sha256: Digest,
    pub last_sequence: Option<u64>,
    pub last_record_sha256: Digest,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ArchivedSegment {
    pub path: PathBuf,
    pub segment_number: u64,
    pub sealed_sha256: Digest,
    pub exported_source_sha256: Option<Digest>,
    pub active: bool,
}

#[derive(Debug)]
pub enum JournalError {
    Io(io::Error),
    StorageFull,
    WriterBusy,
    StaleWriterLease,
    InsecurePath(String),
    InvalidInput(String),
    InvalidRecord(&'static str),
    Corruption {
        offset: u64,
        reason: String,
    },
    TornTailNeedsRepair {
        offset: u64,
    },
    InvalidTransition {
        receipt_id: String,
        from: Option<LifecycleState>,
        to: LifecycleState,
    },
    SegmentTooLarge(u64),
    WriterPoisoned,
}

impl fmt::Display for JournalError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "journal I/O error: {error}"),
            Self::StorageFull => formatter.write_str("journal storage is full"),
            Self::WriterBusy => formatter.write_str("journal already has an active writer"),
            Self::StaleWriterLease => {
                formatter.write_str("journal has a stale writer lease requiring recovery")
            }
            Self::InsecurePath(reason) => write!(formatter, "insecure journal path: {reason}"),
            Self::InvalidInput(reason) => write!(formatter, "invalid journal input: {reason}"),
            Self::InvalidRecord(reason) => write!(formatter, "invalid journal record: {reason}"),
            Self::Corruption { offset, reason } => {
                write!(formatter, "journal corruption at byte {offset}: {reason}")
            }
            Self::TornTailNeedsRepair { offset } => {
                write!(
                    formatter,
                    "journal torn tail at byte {offset} requires explicit repair"
                )
            }
            Self::InvalidTransition {
                receipt_id,
                from,
                to,
            } => write!(
                formatter,
                "invalid receipt transition for {receipt_id}: {from:?} -> {to:?}"
            ),
            Self::SegmentTooLarge(bytes) => {
                write!(formatter, "journal segment exceeds bound: {bytes} bytes")
            }
            Self::WriterPoisoned => formatter.write_str(
                "journal writer is poisoned after an interrupted append; reopen and recover",
            ),
        }
    }
}

impl std::error::Error for JournalError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for JournalError {
    fn from(error: io::Error) -> Self {
        map_io_error(error)
    }
}

#[derive(Clone, Debug)]
struct ReceiptProgress {
    last_state: LifecycleState,
    effect_class: EffectClass,
}

#[derive(Debug)]
struct WriterLease {
    // Keep the lock descriptor open for the complete journal lifetime.  The
    // descriptor carries an advisory OS file lock.  The sidecar pathname is
    // intentionally never unlinked during Drop: a metadata check followed by
    // `remove_file` has a rename race in which teardown could delete a
    // replacement lock installed by another same-UID process.
    _file: File,
}

impl WriterLease {
    fn acquire(journal_path: &Path, recover_stale: bool) -> Result<Self, JournalError> {
        let path = writer_lock_path(journal_path)?;
        let identity = ProcessIdentity::current()?;
        let payload = identity.encode();
        match create_private_file(&path, true) {
            Ok(mut file) => {
                lock_file(&file)?;
                file.write_all(payload.as_bytes()).map_err(map_io_error)?;
                file.sync_all().map_err(map_io_error)?;
                sync_parent(&path)?;
                Self::from_locked_file(path, file)
            }
            Err(JournalError::Io(error)) if error.kind() == io::ErrorKind::AlreadyExists => {
                // Open and lock the existing inode before reading its
                // identity.  A creator may have only written a partial
                // payload; treating parse/I/O failures as "stale" and
                // unlinking the path would let a second writer race the
                // first one.  Fail closed instead.
                let mut file = open_existing_file(&path, true)?;
                lock_file(&file)?;
                let metadata = file.metadata().map_err(map_io_error)?;
                if !path_matches_metadata(&path, &metadata)? {
                    return Err(JournalError::WriterBusy);
                }
                let existing = process_identity_from_file(&mut file)?;
                if !existing.released {
                    let active = existing.is_active()?;
                    if active {
                        return Err(JournalError::WriterBusy);
                    }
                    if !recover_stale {
                        return Err(JournalError::StaleWriterLease);
                    }
                }
                // We hold the inode lock, so recover in place rather than
                // removing/recreating the path.  This keeps any contender's
                // descriptor tied to the same inode and eliminates a
                // check-then-unlink window.
                file.set_len(0).map_err(map_io_error)?;
                file.seek(SeekFrom::Start(0)).map_err(map_io_error)?;
                file.write_all(payload.as_bytes()).map_err(map_io_error)?;
                file.sync_all().map_err(map_io_error)?;
                sync_parent(&path)?;
                Self::from_locked_file(path, file)
            }
            Err(error) => Err(error),
        }
    }

    fn from_locked_file(path: PathBuf, file: File) -> Result<Self, JournalError> {
        let metadata = file.metadata().map_err(map_io_error)?;
        if !path_matches_metadata(&path, &metadata)? {
            return Err(JournalError::WriterBusy);
        }
        Ok(Self { _file: file })
    }
}

impl Drop for WriterLease {
    fn drop(&mut self) {
        // Keep the sidecar inode in place and publish a clean-release marker
        // while the advisory lock is still held.  A contender therefore sees
        // either WriterBusy (until unlock), a complete `released=1` marker,
        // or a malformed/partial payload that is rejected fail closed.  We do
        // not unlink the pathname: checking identity and then unlinking is a
        // TOCTOU window that can remove a replacement lock.
        if self._file.set_len(0).is_ok()
            && self._file.seek(SeekFrom::Start(0)).is_ok()
            && self._file.write_all(b"released=1\n").is_ok()
        {
            let _ = self._file.sync_all();
        }
    }
}

fn lock_file(file: &File) -> Result<(), JournalError> {
    match file.try_lock() {
        Ok(()) => Ok(()),
        Err(std::fs::TryLockError::WouldBlock) => Err(JournalError::WriterBusy),
        Err(std::fs::TryLockError::Error(error)) => Err(map_io_error(error)),
    }
}

fn path_matches_metadata(path: &Path, metadata: &fs::Metadata) -> Result<bool, JournalError> {
    let path_metadata = fs::symlink_metadata(path).map_err(map_io_error)?;
    Ok(path_metadata.file_type().is_file()
        && path_metadata.dev() == metadata.dev()
        && path_metadata.ino() == metadata.ino())
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ProcessIdentity {
    pid: u32,
    start_time_ticks: u64,
    boot_id: String,
    released: bool,
}

impl ProcessIdentity {
    fn current() -> Result<Self, JournalError> {
        // `/proc/self` is resolved by the procfs mount visible to this
        // process.  In a PID namespace the numeric value returned by
        // `process::id()` may refer to a different (host) namespace than the
        // `/proc/<pid>` hierarchy mounted for the process.  Read both values
        // from the same `/proc/self/stat` record so the lease remains
        // self-consistent regardless of the procfs/PID namespace pairing.
        let (pid, start_time_ticks) = current_process_stat()?;
        let boot_id =
            read_bounded_text(Path::new("/proc/sys/kernel/random/boot_id"), 128, "boot_id")?;
        Ok(Self {
            pid,
            start_time_ticks,
            boot_id: boot_id.trim().to_owned(),
            released: false,
        })
    }

    fn encode(&self) -> String {
        format!(
            "pid={}\nstart_time_ticks={}\nboot_id={}\n",
            self.pid, self.start_time_ticks, self.boot_id
        )
    }

    fn is_active(&self) -> Result<bool, JournalError> {
        if self.released {
            return Ok(false);
        }
        let current_boot =
            read_bounded_text(Path::new("/proc/sys/kernel/random/boot_id"), 128, "boot_id")?;
        if current_boot.trim() != self.boot_id {
            return Ok(false);
        }
        match process_start_time(self.pid) {
            Ok(start) => Ok(start == self.start_time_ticks),
            Err(JournalError::Io(error)) if error.kind() == io::ErrorKind::NotFound => Ok(false),
            Err(error) => Err(error),
        }
    }
}

fn process_identity_from_file(file: &mut File) -> Result<ProcessIdentity, JournalError> {
    file.seek(SeekFrom::Start(0)).map_err(map_io_error)?;
    let mut bytes = Vec::new();
    file.take(1025)
        .read_to_end(&mut bytes)
        .map_err(map_io_error)?;
    if bytes.len() > 1024 {
        return Err(JournalError::InvalidInput(
            "writer lease exceeds bound".into(),
        ));
    }
    let text = String::from_utf8(bytes)
        .map_err(|_| JournalError::InvalidInput("writer lease is not UTF-8".into()))?;
    let mut pid = None;
    let mut start_time_ticks = None;
    let mut boot_id = None;
    let mut released = false;
    for line in text.lines() {
        if let Some(value) = line.strip_prefix("pid=") {
            pid = value.parse::<u32>().ok();
        } else if let Some(value) = line.strip_prefix("start_time_ticks=") {
            start_time_ticks = value.parse::<u64>().ok();
        } else if let Some(value) = line.strip_prefix("boot_id=") {
            boot_id = Some(value.to_owned());
        } else if line == "released=1" {
            released = true;
        }
    }
    if released {
        if pid.is_some() || start_time_ticks.is_some() || boot_id.is_some() {
            return Err(JournalError::InvalidRecord(
                "writer lease release marker is mixed with identity",
            ));
        }
        return Ok(ProcessIdentity {
            pid: 0,
            start_time_ticks: 0,
            boot_id: String::new(),
            released: true,
        });
    }
    Ok(ProcessIdentity {
        pid: pid.ok_or(JournalError::InvalidRecord("writer lease lacks pid"))?,
        start_time_ticks: start_time_ticks
            .ok_or(JournalError::InvalidRecord("writer lease lacks start time"))?,
        boot_id: boot_id.ok_or(JournalError::InvalidRecord("writer lease lacks boot id"))?,
        released: false,
    })
}

pub struct ReceiptJournal {
    path: PathBuf,
    file: File,
    _lease: WriterLease,
    header: SegmentHeader,
    next_sequence: u64,
    previous_record_sha256: Digest,
    progress: HashMap<String, ReceiptProgress>,
    // Highest durable lifecycle timestamp observed in this segment.  The
    // value is advisory (the journal intentionally accepts events from
    // multiple clocks), but carrying it into a new observer prevents a
    // reopened writer from restarting its logical sequence at zero.
    last_monotonic_ms: u64,
    end_offset: u64,
    file_device: u64,
    file_inode: u64,
    poisoned: bool,
}

impl ReceiptJournal {
    pub fn create(
        path: impl AsRef<Path>,
        journal_id: JournalId,
        created_wall_clock_unix_ms: u64,
    ) -> Result<Self, JournalError> {
        Self::create_segment(
            path.as_ref(),
            SegmentHeader {
                journal_id,
                segment_number: 1,
                first_sequence: 1,
                previous_segment_sha256: ZERO_DIGEST,
                previous_record_sha256: ZERO_DIGEST,
                created_wall_clock_unix_ms,
            },
            false,
            HashMap::new(),
            0,
        )
    }

    fn create_segment(
        path: &Path,
        header: SegmentHeader,
        recover_stale_writer_lease: bool,
        prior_progress: HashMap<String, ReceiptProgress>,
        prior_last_monotonic_ms: u64,
    ) -> Result<Self, JournalError> {
        validate_new_path(path)?;
        validate_segment_header(&header)?;
        let lease = WriterLease::acquire(path, recover_stale_writer_lease)?;
        let mut file = create_private_file(path, true)?;
        // Lock the journal inode itself in addition to the pathname lease.
        // A hard-link alias has a different sidecar pathname but resolves to
        // this same inode; the advisory lock makes that alias fail closed.
        lock_file(&file)?;
        let encoded = encode_segment_header(&header)?;
        commit_bytes(&mut file, &encoded)?;
        sync_parent(path)?;
        let metadata = file.metadata().map_err(map_io_error)?;
        Ok(Self {
            path: path.to_owned(),
            file,
            _lease: lease,
            next_sequence: header.first_sequence,
            previous_record_sha256: header.previous_record_sha256,
            // A rotated segment shares the journal's receipt namespace with
            // every predecessor.  Carry the terminal progress map forward so
            // a request identifier that already reached a terminal state
            // cannot be admitted again immediately after rotation.
            progress: prior_progress,
            last_monotonic_ms: prior_last_monotonic_ms,
            end_offset: encoded.len() as u64,
            file_device: metadata.dev(),
            file_inode: metadata.ino(),
            header,
            poisoned: false,
        })
    }

    pub fn open(path: impl AsRef<Path>, policy: OpenPolicy) -> Result<Self, JournalError> {
        let path = path.as_ref();
        // Capture the no-follow pathname identity before opening.  A
        // concurrent rename can otherwise replace A with a different regular
        // file B between metadata validation and `open`; comparing the FD's
        // device/inode against this snapshot rejects that substitution before
        // any bytes are recovered or written.
        let expected_identity = validate_existing_path_identity(path)?;
        // Pin and lock the journal inode before touching the pathname
        // sidecar.  Between metadata validation and a sidecar-only acquire,
        // a same-user actor could rename a different regular file over this
        // path; opening first lets us compare the path after lease admission
        // and ensures all writes use the originally pinned descriptor.
        let mut file = open_existing_file_checked(path, true, expected_identity)?;
        let inode_metadata = file.metadata().map_err(map_io_error)?;
        lock_file(&file)?;
        let lease = WriterLease::acquire(path, policy.recover_stale_writer_lease)?;
        if !path_matches_metadata(path, &inode_metadata)? {
            return Err(JournalError::InsecurePath(
                "journal path changed while acquiring writer lease".into(),
            ));
        }
        let mut report = recover_file(&mut file)?;
        if let TailStatus::TornTail { offset, .. } = report.tail {
            if !policy.repair_torn_tail {
                return Err(JournalError::TornTailNeedsRepair { offset });
            }
            file.set_len(report.last_complete_offset)
                .map_err(map_io_error)?;
            file.sync_data().map_err(map_io_error)?;
            report = recover_file(&mut file)?;
            if report.tail != TailStatus::Clean {
                return Err(JournalError::Corruption {
                    offset: report.last_complete_offset,
                    reason: "torn-tail repair did not produce a clean segment".into(),
                });
            }
        }
        let progress = progress_from_records(&report.records)?;
        let last_monotonic_ms = report
            .records
            .iter()
            .map(|record| record.event.monotonic_ms)
            .max()
            .unwrap_or(0);
        file.seek(SeekFrom::Start(report.last_complete_offset))
            .map_err(map_io_error)?;
        Ok(Self {
            path: path.to_owned(),
            file,
            _lease: lease,
            header: report.header,
            next_sequence: report.next_sequence,
            previous_record_sha256: report.last_record_sha256,
            progress,
            last_monotonic_ms,
            end_offset: report.last_complete_offset,
            file_device: inode_metadata.dev(),
            file_inode: inode_metadata.ino(),
            poisoned: false,
        })
    }

    fn verify_active_append_state(&self, expected_offset: u64) -> Result<(), JournalError> {
        let expected = (self.file_device, self.file_inode);
        let file_metadata = self.file.metadata().map_err(map_io_error)?;
        if !metadata_matches_identity(&file_metadata, expected) {
            return Err(JournalError::InsecurePath(
                "journal inode changed while open".into(),
            ));
        }
        if file_metadata.len() != expected_offset {
            return Err(JournalError::Corruption {
                offset: expected_offset,
                reason: format!(
                    "journal length changed while open (expected {}, found {})",
                    expected_offset,
                    file_metadata.len()
                ),
            });
        }
        let path_metadata = fs::symlink_metadata(&self.path).map_err(map_io_error)?;
        if !metadata_matches_identity(&path_metadata, expected) {
            return Err(JournalError::InsecurePath(
                "journal path no longer names the open inode".into(),
            ));
        }
        Ok(())
    }

    pub fn append(&mut self, event: ReceiptEvent) -> Result<CommittedRecord, JournalError> {
        if self.poisoned {
            return Err(JournalError::WriterPoisoned);
        }
        if let Err(error) = self.verify_active_append_state(self.end_offset) {
            self.poisoned = true;
            return Err(error);
        }
        // Reserve the successor sequence before writing any bytes.  Without
        // this preflight, a journal at `u64::MAX` would commit a record and
        // then fail the increment below, leaving the in-memory cursor on the
        // old offset; a subsequent append could overwrite that durable
        // record and break the hash chain.
        let next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or_else(|| JournalError::InvalidInput("sequence overflow".into()))?;
        event.validate()?;
        let previous = self
            .progress
            .get(&event.receipt_id)
            .map(|progress| progress.last_state);
        validate_transition(&event.receipt_id, previous, event.lifecycle)?;
        if let Some(progress) = self.progress.get(&event.receipt_id)
            && progress.effect_class != event.effect_class
        {
            return Err(JournalError::InvalidInput(
                "effect class cannot change within one receipt lifecycle".into(),
            ));
        }
        let (bytes, digest) =
            encode_record(self.next_sequence, self.previous_record_sha256, &event)?;
        let new_size = self
            .end_offset
            .checked_add(bytes.len() as u64)
            .ok_or(JournalError::SegmentTooLarge(u64::MAX))?;
        if new_size > MAX_SEGMENT_BYTES {
            return Err(JournalError::SegmentTooLarge(new_size));
        }
        self.file
            .seek(SeekFrom::Start(self.end_offset))
            .map_err(map_io_error)?;
        if let Err(error) = commit_bytes(&mut self.file, &bytes) {
            self.poisoned = true;
            return Err(error);
        }
        if let Err(error) = self.verify_active_append_state(new_size) {
            self.poisoned = true;
            return Err(error);
        }
        let committed = CommittedRecord {
            sequence: self.next_sequence,
            record_sha256: digest,
            end_offset: new_size,
        };
        self.next_sequence = next_sequence;
        self.previous_record_sha256 = digest;
        self.end_offset = new_size;
        self.last_monotonic_ms = self.last_monotonic_ms.max(event.monotonic_ms);
        self.progress.insert(
            event.receipt_id,
            ReceiptProgress {
                last_state: event.lifecycle,
                effect_class: event.effect_class,
            },
        );
        Ok(committed)
    }

    pub fn inspect(&mut self) -> Result<RecoveryReport, JournalError> {
        let report = recover_file(&mut self.file)?;
        self.last_monotonic_ms = self.last_monotonic_ms.max(
            report
                .records
                .iter()
                .map(|record| record.event.monotonic_ms)
                .max()
                .unwrap_or(0),
        );
        Ok(report)
    }

    pub fn seal(&mut self) -> Result<SegmentSeal, JournalError> {
        if self.poisoned {
            return Err(JournalError::WriterPoisoned);
        }
        self.file.sync_all().map_err(map_io_error)?;
        let report = recover_file(&mut self.file)?;
        if report.tail != TailStatus::Clean {
            return Err(JournalError::TornTailNeedsRepair {
                offset: report.last_complete_offset,
            });
        }
        let bytes = read_segment_bytes(&mut self.file)?;
        Ok(SegmentSeal {
            segment_number: report.header.segment_number,
            bytes: bytes.len() as u64,
            segment_sha256: sha256(&bytes),
            last_sequence: report.records.last().map(|record| record.sequence),
            last_record_sha256: report.last_record_sha256,
        })
    }

    pub fn rotate(
        mut self,
        next_path: impl AsRef<Path>,
        created_wall_clock_unix_ms: u64,
    ) -> Result<(SegmentSeal, Self), JournalError> {
        if self
            .progress
            .values()
            .any(|progress| !progress.last_state.is_terminal())
        {
            return Err(JournalError::InvalidInput(
                "rotation requires a quiescent journal with no unresolved receipts".into(),
            ));
        }
        // Rotation derives the successor header from the in-memory cursor.
        // Verify the active inode and exact offset before and after sealing so
        // an out-of-band append/rename cannot produce a successor that points
        // at a different record chain or silently skips sequence numbers.
        if let Err(error) = self.verify_active_append_state(self.end_offset) {
            self.poisoned = true;
            return Err(error);
        }
        let seal = match self.seal() {
            Ok(seal) => seal,
            Err(error) => {
                self.poisoned = true;
                return Err(error);
            }
        };
        if let Err(error) = self.verify_active_append_state(self.end_offset) {
            self.poisoned = true;
            return Err(error);
        }
        let expected_last_sequence = self
            .next_sequence
            .checked_sub(1)
            .filter(|sequence| *sequence >= self.header.first_sequence);
        if seal.last_sequence != expected_last_sequence
            || seal.last_record_sha256 != self.previous_record_sha256
        {
            self.poisoned = true;
            return Err(JournalError::Corruption {
                offset: self.end_offset,
                reason: "journal cursor disagrees with sealed records during rotation".into(),
            });
        }
        let next =
            Self::create_segment(
                next_path.as_ref(),
                SegmentHeader {
                    journal_id: self.header.journal_id,
                    segment_number: self.header.segment_number.checked_add(1).ok_or_else(|| {
                        JournalError::InvalidInput("segment number overflow".into())
                    })?,
                    first_sequence: self.next_sequence,
                    previous_segment_sha256: seal.segment_sha256,
                    previous_record_sha256: self.previous_record_sha256,
                    created_wall_clock_unix_ms,
                },
                false,
                self.progress.clone(),
                self.last_monotonic_ms,
            )?;
        Ok((seal, next))
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Return the greatest durable lifecycle timestamp observed by this
    /// journal writer.  Callers that create a new lifecycle observer after a
    /// reopen can continue from this value instead of restarting at zero.
    pub fn last_monotonic_ms(&self) -> u64 {
        self.last_monotonic_ms
    }
}

pub fn inspect_path(path: impl AsRef<Path>) -> Result<RecoveryReport, JournalError> {
    let path = path.as_ref();
    let expected_identity = validate_existing_path_identity(path)?;
    let mut file = open_existing_file_checked(path, false, expected_identity)?;
    recover_file(&mut file)
}

/// Inspect an ordered, complete ReceiptJournal segment chain.
///
/// Unlike [`inspect_path`], this verifies the cross-segment links emitted by
/// [`ReceiptJournal::rotate`]: one journal ID, contiguous segment numbers and
/// global record sequences, a clean predecessor before every successor, and
/// both predecessor digests.  The caller must provide the complete chain in
/// ascending segment order beginning with segment one; a missing or reordered
/// segment is rejected.  The returned reports retain the same per-segment
/// recovery details as [`inspect_path`].
pub fn inspect_chain<I, P>(paths: I) -> Result<Vec<RecoveryReport>, JournalError>
where
    I: IntoIterator<Item = P>,
    P: AsRef<Path>,
{
    let paths: Vec<PathBuf> = paths
        .into_iter()
        .map(|path| path.as_ref().to_owned())
        .collect();
    if paths.is_empty() {
        return Err(JournalError::InvalidInput(
            "segment chain must contain at least one path".into(),
        ));
    }

    let mut inspected = Vec::with_capacity(paths.len());
    for (index, path) in paths.iter().enumerate() {
        let expected_identity = validate_existing_path_identity(path)?;
        let mut file = open_existing_file_checked(path, false, expected_identity).map_err(
            |error| match error {
                JournalError::InsecurePath(reason)
                    if reason == "journal path changed before opening" =>
                {
                    JournalError::InsecurePath(format!(
                        "segment chain entry {index} changed before opening"
                    ))
                }
                other => other,
            },
        )?;
        let bytes = read_segment_bytes(&mut file)?;
        let digest = sha256(&bytes);
        let report = recover_bytes(&bytes)?;
        if report.tail != TailStatus::Clean {
            return Err(JournalError::Corruption {
                offset: report.last_complete_offset,
                reason: format!(
                    "segment chain entry {index} has a torn tail; repair before chain inspection"
                ),
            });
        }
        inspected.push((report, digest));
    }

    let first = &inspected[0].0;
    if first.header.segment_number != 1 {
        return Err(JournalError::Corruption {
            offset: 0,
            reason: "segment chain does not begin with segment one".into(),
        });
    }

    for (index, window) in inspected.windows(2).enumerate() {
        let (previous, previous_digest) = &window[0];
        let (current, _) = &window[1];
        if !previous.unresolved.is_empty() {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: format!(
                    "segment chain predecessor at index {index} has unresolved receipts"
                ),
            });
        }
        if current.header.journal_id != first.header.journal_id {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: format!(
                    "segment chain entry {} has a different journal ID",
                    index + 1
                ),
            });
        }
        let expected_segment_number =
            previous
                .header
                .segment_number
                .checked_add(1)
                .ok_or_else(|| JournalError::Corruption {
                    offset: 0,
                    reason: "segment number overflow in chain".into(),
                })?;
        if current.header.segment_number != expected_segment_number {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: format!(
                    "segment number is not contiguous: expected {expected_segment_number}, found {}",
                    current.header.segment_number
                ),
            });
        }
        if current.header.first_sequence != previous.next_sequence {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: format!(
                    "first sequence is not contiguous: expected {}, found {}",
                    previous.next_sequence, current.header.first_sequence
                ),
            });
        }
        if current.header.previous_segment_sha256 != *previous_digest {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: "previous-segment digest link mismatch".into(),
            });
        }
        if current.header.previous_record_sha256 != previous.last_record_sha256 {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: "previous-record digest link across segments mismatch".into(),
            });
        }
    }

    // Lifecycle identity is global to a journal, not scoped to one segment.
    // `ReceiptJournal::rotate` carries this map for the in-memory successor,
    // but chain inspection must independently enforce the same rule when a
    // process reopens archived segments.  Without this pass a completed
    // receipt could be followed by a fresh `Requested` record with the same
    // identifier in a later segment, defeating duplicate/admission guards and
    // permitting a caller to replay an operation after rotation.
    let mut chain_progress: HashMap<String, ReceiptProgress> = HashMap::new();
    for (segment_index, (report, _)) in inspected.iter().enumerate() {
        for record in &report.records {
            let receipt_id = &record.event.receipt_id;
            let previous = chain_progress.get(receipt_id).map(|item| item.last_state);
            validate_transition(receipt_id, previous, record.event.lifecycle).map_err(|error| {
                JournalError::Corruption {
                    offset: 0,
                    reason: format!(
                        "segment chain entry {segment_index} has invalid cross-segment receipt lifecycle: {error}"
                    ),
                }
            })?;
            if let Some(item) = chain_progress.get(receipt_id)
                && item.effect_class != record.event.effect_class
            {
                return Err(JournalError::Corruption {
                    offset: 0,
                    reason: format!(
                        "segment chain entry {segment_index} changes effect class for receipt {receipt_id}"
                    ),
                });
            }
            chain_progress.insert(
                receipt_id.clone(),
                ReceiptProgress {
                    last_state: record.event.lifecycle,
                    effect_class: record.event.effect_class,
                },
            );
        }
    }

    Ok(inspected.into_iter().map(|(report, _)| report).collect())
}

/// Export canonical `receipt.v1` operation envelopes.
///
/// Lifecycle records are grouped by receipt ID.  Every group must contain a
/// terminal record; unresolved requested/dispatched records are rejected
/// rather than being downgraded to a made-up status.  The output is private,
/// atomically committed JSONL and each line is valid against the v1 envelope
/// contract (with journal-only fields intentionally omitted).
pub fn export_receipt_envelopes_jsonl(
    report: &RecoveryReport,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError> {
    let destination = destination.as_ref();
    validate_new_path(destination)?;
    let mut groups: Vec<(String, Vec<RecoveredRecord>)> = Vec::new();
    let mut group_indexes: HashMap<String, usize> = HashMap::new();
    for record in &report.records {
        if let Some(index) = group_indexes.get(&record.event.receipt_id).copied() {
            let (_, records) = &mut groups[index];
            records.push(record.clone());
        } else {
            let index = groups.len();
            group_indexes.insert(record.event.receipt_id.clone(), index);
            groups.push((record.event.receipt_id.clone(), vec![record.clone()]));
        }
    }

    let mut bytes = Vec::new();
    for (_, records) in groups {
        let envelope = ReceiptEnvelope::from_records(&records)?;
        bytes.extend_from_slice(envelope.to_canonical_json()?.as_bytes());
        bytes.push(b'\n');
    }
    let digest = sha256(&bytes);
    let mut file = create_private_file(destination, true)?;
    commit_bytes(&mut file, &bytes)?;
    sync_parent(destination)?;
    Ok(digest)
}

/// Export the append-level lifecycle facts in the historical journal format.
///
/// This is retained for forensic/debug consumers that need sequence, record
/// digest, lifecycle, effect class, privacy class, and request/response
/// digest fields.  Public operation evidence should use
/// [`export_receipt_envelopes_jsonl`] (or its compatibility alias
/// [`export_redacted_jsonl`]).
pub fn export_journal_redacted_jsonl(
    report: &RecoveryReport,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError> {
    let destination = destination.as_ref();
    validate_new_path(destination)?;
    let mut bytes = Vec::new();
    for record in &report.records {
        let event = &record.event;
        let detail = match event.privacy_class {
            PrivacyClass::Public | PrivacyClass::Internal => event.detail.as_deref(),
            PrivacyClass::Sensitive | PrivacyClass::SecretRedacted => None,
        };
        let response = event.response_sha256.map(hex_digest);
        let outcome = event.outcome.map(ReceiptOutcome::as_str);
        let line = format!(
            "{{\"sequence\":{},\"record_sha256\":\"{}\",\"receipt_id\":\"{}\",\"session_id\":\"{}\",\"source\":\"{}\",\"operation\":\"{}\",\"lifecycle\":\"{}\",\"outcome\":{},\"effect_class\":\"{}\",\"privacy_class\":\"{}\",\"request_sha256\":\"{}\",\"response_sha256\":{},\"error_code\":{},\"detail\":{}}}\n",
            record.sequence,
            hex_digest(record.record_sha256),
            json_escape(&event.receipt_id),
            json_escape(&event.session_id),
            event.source.as_str(),
            json_escape(&event.operation),
            event.lifecycle.as_str(),
            json_option(outcome),
            event.effect_class.as_str(),
            event.privacy_class.as_str(),
            hex_digest(event.request_sha256),
            json_option(response.as_deref()),
            json_option(event.error_code.as_deref()),
            json_option(detail),
        );
        bytes.extend_from_slice(line.as_bytes());
    }
    let digest = sha256(&bytes);
    let mut file = create_private_file(destination, true)?;
    commit_bytes(&mut file, &bytes)?;
    sync_parent(destination)?;
    Ok(digest)
}

/// Compatibility entry point for public redacted receipt export.
///
/// Prior versions emitted journal-internal lifecycle objects from this name,
/// which could not satisfy `contracts/receipt.v1.schema.json`.  Keep the API
/// stable while making its output the canonical operation envelope.
pub fn export_redacted_jsonl(
    report: &RecoveryReport,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError> {
    export_receipt_envelopes_jsonl(report, destination)
}

pub fn retention_candidates(
    segments: &[ArchivedSegment],
    keep_latest: usize,
) -> Result<Vec<PathBuf>, JournalError> {
    if keep_latest == 0 {
        return Err(JournalError::InvalidInput(
            "retention must keep at least one segment".into(),
        ));
    }
    let mut ordered = segments.to_vec();
    ordered.sort_by_key(|segment| segment.segment_number);
    let cutoff = ordered.len().saturating_sub(keep_latest);
    let mut candidates = Vec::new();
    for segment in ordered.into_iter().take(cutoff) {
        if segment.active {
            continue;
        }
        if segment.exported_source_sha256 == Some(segment.sealed_sha256) {
            candidates.push(segment.path);
        }
    }
    Ok(candidates)
}

pub fn hex_digest(digest: Digest) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(64);
    for byte in digest {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

fn replay_directive(state: LifecycleState, effect: EffectClass) -> ReplayDirective {
    if effect == EffectClass::PotentialExternalEffect {
        return ReplayDirective::NeverAutomatic;
    }
    match (state, effect) {
        (LifecycleState::Requested, _) => ReplayDirective::CallerMayReadmit,
        (LifecycleState::Dispatched, EffectClass::Observation) => {
            ReplayDirective::CallerMayReobserve
        }
        _ => ReplayDirective::NeverAutomatic,
    }
}

fn progress_from_records(
    records: &[RecoveredRecord],
) -> Result<HashMap<String, ReceiptProgress>, JournalError> {
    let mut progress = HashMap::new();
    for record in records {
        let previous = progress
            .get(&record.event.receipt_id)
            .map(|item: &ReceiptProgress| item.last_state);
        validate_transition(&record.event.receipt_id, previous, record.event.lifecycle)?;
        if let Some(item) = progress.get(&record.event.receipt_id)
            && item.effect_class != record.event.effect_class
        {
            return Err(JournalError::InvalidRecord(
                "effect class changed within receipt lifecycle",
            ));
        }
        progress.insert(
            record.event.receipt_id.clone(),
            ReceiptProgress {
                last_state: record.event.lifecycle,
                effect_class: record.event.effect_class,
            },
        );
    }
    Ok(progress)
}

fn validate_transition(
    receipt_id: &str,
    previous: Option<LifecycleState>,
    next: LifecycleState,
) -> Result<(), JournalError> {
    let valid = matches!(
        (previous, next),
        (None, LifecycleState::Requested)
            | (Some(LifecycleState::Requested), LifecycleState::Dispatched)
            | (Some(LifecycleState::Requested), LifecycleState::Interrupted)
            | (Some(LifecycleState::Dispatched), LifecycleState::Completed)
            | (
                Some(LifecycleState::Dispatched),
                LifecycleState::Indeterminate
            )
            | (
                Some(LifecycleState::Dispatched),
                LifecycleState::Interrupted
            )
    );
    if valid {
        Ok(())
    } else {
        Err(JournalError::InvalidTransition {
            receipt_id: receipt_id.to_owned(),
            from: previous,
            to: next,
        })
    }
}

fn encode_segment_header(header: &SegmentHeader) -> Result<Vec<u8>, JournalError> {
    validate_segment_header(header)?;
    let mut bytes = Vec::with_capacity(SEGMENT_HEADER_LEN);
    bytes.extend_from_slice(SEGMENT_MAGIC);
    put_u16(&mut bytes, FORMAT_VERSION);
    put_u16(&mut bytes, SEGMENT_HEADER_LEN as u16);
    bytes.extend_from_slice(&header.journal_id.0);
    put_u64(&mut bytes, header.segment_number);
    put_u64(&mut bytes, header.first_sequence);
    bytes.extend_from_slice(&header.previous_segment_sha256);
    bytes.extend_from_slice(&header.previous_record_sha256);
    put_u64(&mut bytes, header.created_wall_clock_unix_ms);
    debug_assert_eq!(bytes.len(), SEGMENT_HEADER_PREFIX_LEN);
    let digest = sha256(&bytes);
    bytes.extend_from_slice(&digest);
    debug_assert_eq!(bytes.len(), SEGMENT_HEADER_LEN);
    Ok(bytes)
}

fn decode_segment_header(bytes: &[u8]) -> Result<SegmentHeader, JournalError> {
    if bytes.len() < SEGMENT_HEADER_LEN {
        return Err(JournalError::InvalidRecord("segment header is truncated"));
    }
    if &bytes[0..8] != SEGMENT_MAGIC {
        return Err(JournalError::InvalidRecord("segment magic mismatch"));
    }
    let mut cursor = Cursor::new(bytes);
    cursor.skip(8)?;
    if cursor.u16()? != FORMAT_VERSION {
        return Err(JournalError::InvalidRecord("segment version mismatch"));
    }
    if cursor.u16()? as usize != SEGMENT_HEADER_LEN {
        return Err(JournalError::InvalidRecord(
            "segment header length mismatch",
        ));
    }
    let journal_id = JournalId(cursor.array::<16>()?);
    let segment_number = cursor.u64()?;
    let first_sequence = cursor.u64()?;
    let previous_segment_sha256 = cursor.array::<32>()?;
    let previous_record_sha256 = cursor.array::<32>()?;
    let created_wall_clock_unix_ms = cursor.u64()?;
    let expected = cursor.array::<32>()?;
    let actual = sha256(&bytes[..SEGMENT_HEADER_PREFIX_LEN]);
    if expected != actual {
        return Err(JournalError::InvalidRecord(
            "segment header digest mismatch",
        ));
    }
    let header = SegmentHeader {
        journal_id,
        segment_number,
        first_sequence,
        previous_segment_sha256,
        previous_record_sha256,
        created_wall_clock_unix_ms,
    };
    validate_segment_header(&header)?;
    Ok(header)
}

fn validate_segment_header(header: &SegmentHeader) -> Result<(), JournalError> {
    header.journal_id.validate()?;
    if header.segment_number == 0 {
        return Err(JournalError::InvalidInput(
            "segment_number must be non-zero".into(),
        ));
    }
    if header.first_sequence == 0 {
        return Err(JournalError::InvalidInput(
            "first_sequence must be non-zero".into(),
        ));
    }
    if header.segment_number == 1
        && (header.previous_segment_sha256 != ZERO_DIGEST
            || header.previous_record_sha256 != ZERO_DIGEST
            || header.first_sequence != 1)
    {
        return Err(JournalError::InvalidInput(
            "first segment must begin the sequence and both chains".into(),
        ));
    }
    if header.segment_number > 1
        && (header.previous_segment_sha256 == ZERO_DIGEST
            || header.previous_record_sha256 == ZERO_DIGEST
            || header.first_sequence <= 1)
    {
        return Err(JournalError::InvalidInput(
            "rotated segment must bind prior segment and record chains".into(),
        ));
    }
    Ok(())
}

fn encode_record(
    sequence: u64,
    previous_record_sha256: Digest,
    event: &ReceiptEvent,
) -> Result<(Vec<u8>, Digest), JournalError> {
    event.validate()?;
    if sequence == 0 {
        return Err(JournalError::InvalidInput(
            "record sequence must be non-zero".into(),
        ));
    }
    let payload = encode_payload(event)?;
    if payload.len() > MAX_RECORD_PAYLOAD_BYTES {
        return Err(JournalError::InvalidInput(
            "record payload exceeds bound".into(),
        ));
    }
    let response = event.response_sha256.unwrap_or(ZERO_DIGEST);
    let mut flags = 0_u8;
    if event.response_sha256.is_some() {
        flags |= 1;
    }
    if event.error_code.is_some() {
        flags |= 2;
    }
    if event.detail.is_some() {
        flags |= 4;
    }
    let mut bytes = Vec::with_capacity(RECORD_PREFIX_LEN + payload.len() + 32);
    bytes.extend_from_slice(RECORD_MAGIC);
    put_u16(&mut bytes, FORMAT_VERSION);
    put_u16(&mut bytes, RECORD_PREFIX_LEN as u16);
    bytes.push(event.lifecycle as u8);
    bytes.push(event.effect_class as u8);
    bytes.push(event.privacy_class as u8);
    bytes.push(event.source as u8);
    bytes.push(event.outcome.map_or(0, |value| value as u8));
    bytes.push(flags);
    put_u16(&mut bytes, 0);
    put_u64(&mut bytes, sequence);
    put_u64(&mut bytes, event.monotonic_ms);
    put_u64(&mut bytes, event.wall_clock_unix_ms);
    put_u64(&mut bytes, event.session_generation);
    put_u64(&mut bytes, event.document_generation);
    put_u64(&mut bytes, event.semantic_snapshot_revision);
    put_u64(&mut bytes, event.mutation_epoch);
    bytes.extend_from_slice(&event.request_sha256);
    bytes.extend_from_slice(&response);
    bytes.extend_from_slice(&previous_record_sha256);
    put_u32(&mut bytes, payload.len() as u32);
    bytes.extend_from_slice(&sha256(&payload));
    debug_assert_eq!(bytes.len(), RECORD_PREFIX_LEN);
    bytes.extend_from_slice(&payload);
    let digest = sha256(&bytes);
    bytes.extend_from_slice(&digest);
    Ok((bytes, digest))
}

fn decode_record(
    bytes: &[u8],
    offset: usize,
    expected_sequence: u64,
    expected_previous: Digest,
) -> Result<RecoveredRecord, JournalError> {
    if bytes.len() < RECORD_PREFIX_LEN + RECORD_DIGEST_LEN {
        return Err(JournalError::InvalidRecord("record is truncated"));
    }
    if &bytes[0..8] != RECORD_MAGIC {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "record magic mismatch".into(),
        });
    }
    let mut cursor = Cursor::new(bytes);
    cursor.skip(8)?;
    if cursor.u16()? != FORMAT_VERSION {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "record version mismatch".into(),
        });
    }
    if cursor.u16()? as usize != RECORD_PREFIX_LEN {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "record prefix length mismatch".into(),
        });
    }
    let lifecycle = LifecycleState::from_wire(cursor.u8()?)?;
    let effect_class = EffectClass::from_wire(cursor.u8()?)?;
    let privacy_class = PrivacyClass::from_wire(cursor.u8()?)?;
    let source = ReceiptSource::from_wire(cursor.u8()?)?;
    let outcome = ReceiptOutcome::from_wire(cursor.u8()?)?;
    let flags = cursor.u8()?;
    if flags & !0b111 != 0 || cursor.u16()? != 0 {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "record flags or reserved bytes are invalid".into(),
        });
    }
    let sequence = cursor.u64()?;
    if sequence != expected_sequence {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: format!("sequence mismatch: expected {expected_sequence}, found {sequence}"),
        });
    }
    let monotonic_ms = cursor.u64()?;
    let wall_clock_unix_ms = cursor.u64()?;
    let session_generation = cursor.u64()?;
    let document_generation = cursor.u64()?;
    let semantic_snapshot_revision = cursor.u64()?;
    let mutation_epoch = cursor.u64()?;
    let request_sha256 = cursor.array::<32>()?;
    let response_wire = cursor.array::<32>()?;
    let previous_record_sha256 = cursor.array::<32>()?;
    if previous_record_sha256 != expected_previous {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "previous-record digest chain mismatch".into(),
        });
    }
    let payload_len = cursor.u32()? as usize;
    if payload_len > MAX_RECORD_PAYLOAD_BYTES {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "payload length exceeds bound".into(),
        });
    }
    let payload_sha256 = cursor.array::<32>()?;
    let total = RECORD_PREFIX_LEN
        .checked_add(payload_len)
        .and_then(|value| value.checked_add(RECORD_DIGEST_LEN))
        .ok_or_else(|| JournalError::Corruption {
            offset: offset as u64,
            reason: "record length overflow".into(),
        })?;
    if bytes.len() != total {
        return Err(JournalError::InvalidRecord("record slice length mismatch"));
    }
    let payload = &bytes[RECORD_PREFIX_LEN..RECORD_PREFIX_LEN + payload_len];
    if sha256(payload) != payload_sha256 {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "payload digest mismatch".into(),
        });
    }
    let digest_offset = RECORD_PREFIX_LEN + payload_len;
    let expected_digest: Digest = bytes[digest_offset..]
        .try_into()
        .map_err(|_| JournalError::InvalidRecord("record digest length mismatch"))?;
    let actual_digest = sha256(&bytes[..digest_offset]);
    if expected_digest != actual_digest {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "record digest mismatch".into(),
        });
    }
    let mut event = decode_payload(payload)?;
    event.lifecycle = lifecycle;
    event.effect_class = effect_class;
    event.privacy_class = privacy_class;
    event.source = source;
    event.outcome = outcome;
    event.monotonic_ms = monotonic_ms;
    event.wall_clock_unix_ms = wall_clock_unix_ms;
    event.session_generation = session_generation;
    event.document_generation = document_generation;
    event.semantic_snapshot_revision = semantic_snapshot_revision;
    event.mutation_epoch = mutation_epoch;
    event.request_sha256 = request_sha256;
    event.response_sha256 = if flags & 1 != 0 {
        Some(response_wire)
    } else {
        if response_wire != ZERO_DIGEST {
            return Err(JournalError::Corruption {
                offset: offset as u64,
                reason: "response digest present without flag".into(),
            });
        }
        None
    };
    if (event.error_code.is_some()) != (flags & 2 != 0)
        || (event.detail.is_some()) != (flags & 4 != 0)
    {
        return Err(JournalError::Corruption {
            offset: offset as u64,
            reason: "optional payload flags do not match payload".into(),
        });
    }
    event.validate().map_err(|error| JournalError::Corruption {
        offset: offset as u64,
        reason: error.to_string(),
    })?;
    Ok(RecoveredRecord {
        sequence,
        record_sha256: actual_digest,
        event,
    })
}

fn encode_payload(event: &ReceiptEvent) -> Result<Vec<u8>, JournalError> {
    let mut bytes = Vec::new();
    put_string(&mut bytes, &event.receipt_id)?;
    put_string(&mut bytes, &event.plan_revision)?;
    put_string(&mut bytes, &event.image_id)?;
    put_string(&mut bytes, &event.servo_commit)?;
    put_string(&mut bytes, &event.browserd_version)?;
    put_string(&mut bytes, &event.session_id)?;
    put_string(&mut bytes, &event.operation)?;
    put_optional_string(&mut bytes, event.error_code.as_deref())?;
    put_optional_string(&mut bytes, event.detail.as_deref())?;
    Ok(bytes)
}

fn decode_payload(payload: &[u8]) -> Result<ReceiptEvent, JournalError> {
    let mut cursor = Cursor::new(payload);
    let receipt_id = cursor.string()?;
    let plan_revision = cursor.string()?;
    let image_id = cursor.string()?;
    let servo_commit = cursor.string()?;
    let browserd_version = cursor.string()?;
    let session_id = cursor.string()?;
    let operation = cursor.string()?;
    let error_code = cursor.optional_string()?;
    let detail = cursor.optional_string()?;
    if cursor.remaining() != 0 {
        return Err(JournalError::InvalidRecord(
            "record payload has trailing bytes",
        ));
    }
    Ok(ReceiptEvent {
        receipt_id,
        plan_revision,
        image_id,
        servo_commit,
        browserd_version,
        session_id,
        session_generation: 0,
        document_generation: 0,
        semantic_snapshot_revision: 0,
        mutation_epoch: 0,
        source: ReceiptSource::System,
        operation,
        lifecycle: LifecycleState::Requested,
        outcome: None,
        effect_class: EffectClass::Observation,
        privacy_class: PrivacyClass::Internal,
        request_sha256: ZERO_DIGEST,
        response_sha256: None,
        error_code,
        detail,
        monotonic_ms: 0,
        wall_clock_unix_ms: 0,
    })
}

fn recover_file(file: &mut File) -> Result<RecoveryReport, JournalError> {
    let bytes = read_segment_bytes(file)?;
    recover_bytes(&bytes)
}

fn recover_bytes(bytes: &[u8]) -> Result<RecoveryReport, JournalError> {
    if bytes.len() < SEGMENT_HEADER_LEN {
        return Err(JournalError::Corruption {
            offset: 0,
            reason: "segment header is incomplete".into(),
        });
    }
    let header = decode_segment_header(&bytes[..SEGMENT_HEADER_LEN]).map_err(|error| {
        JournalError::Corruption {
            offset: 0,
            reason: error.to_string(),
        }
    })?;
    let mut records = Vec::new();
    let mut offset = SEGMENT_HEADER_LEN;
    let mut expected_sequence = header.first_sequence;
    let mut expected_previous = header.previous_record_sha256;
    let mut progress: HashMap<String, ReceiptProgress> = HashMap::new();
    let mut tail = TailStatus::Clean;

    while offset < bytes.len() {
        let available = bytes.len() - offset;
        if available < RECORD_PREFIX_LEN {
            tail = TailStatus::TornTail {
                offset: offset as u64,
                bytes_available: available,
                bytes_expected: Some(RECORD_PREFIX_LEN),
            };
            break;
        }
        if &bytes[offset..offset + 8] != RECORD_MAGIC {
            return Err(JournalError::Corruption {
                offset: offset as u64,
                reason: "record magic mismatch".into(),
            });
        }
        let payload_len = u32::from_be_bytes(
            bytes[offset + 172..offset + 176]
                .try_into()
                .map_err(|_| JournalError::InvalidRecord("payload length slice"))?,
        ) as usize;
        if payload_len > MAX_RECORD_PAYLOAD_BYTES {
            return Err(JournalError::Corruption {
                offset: offset as u64,
                reason: "payload length exceeds bound".into(),
            });
        }
        let total = RECORD_PREFIX_LEN
            .checked_add(payload_len)
            .and_then(|value| value.checked_add(RECORD_DIGEST_LEN))
            .ok_or_else(|| JournalError::Corruption {
                offset: offset as u64,
                reason: "record length overflow".into(),
            })?;
        if available < total {
            tail = TailStatus::TornTail {
                offset: offset as u64,
                bytes_available: available,
                bytes_expected: Some(total),
            };
            break;
        }
        let record = decode_record(
            &bytes[offset..offset + total],
            offset,
            expected_sequence,
            expected_previous,
        )
        .map_err(|error| match error {
            JournalError::Corruption { .. } => error,
            other => JournalError::Corruption {
                offset: offset as u64,
                reason: other.to_string(),
            },
        })?;
        let previous_state = progress
            .get(&record.event.receipt_id)
            .map(|item| item.last_state);
        validate_transition(
            &record.event.receipt_id,
            previous_state,
            record.event.lifecycle,
        )
        .map_err(|error| JournalError::Corruption {
            offset: offset as u64,
            reason: error.to_string(),
        })?;
        if let Some(item) = progress.get(&record.event.receipt_id)
            && item.effect_class != record.event.effect_class
        {
            return Err(JournalError::Corruption {
                offset: offset as u64,
                reason: "effect class changed within receipt lifecycle".into(),
            });
        }
        progress.insert(
            record.event.receipt_id.clone(),
            ReceiptProgress {
                last_state: record.event.lifecycle,
                effect_class: record.event.effect_class,
            },
        );
        expected_sequence =
            expected_sequence
                .checked_add(1)
                .ok_or_else(|| JournalError::Corruption {
                    offset: offset as u64,
                    reason: "sequence overflow".into(),
                })?;
        expected_previous = record.record_sha256;
        records.push(record);
        offset += total;
    }

    let mut unresolved: Vec<_> = progress
        .into_iter()
        .filter_map(|(receipt_id, item)| {
            (!item.last_state.is_terminal()).then(|| UnresolvedReceipt {
                receipt_id,
                last_state: item.last_state,
                effect_class: item.effect_class,
                replay: replay_directive(item.last_state, item.effect_class),
            })
        })
        .collect();
    unresolved.sort_by(|left, right| left.receipt_id.cmp(&right.receipt_id));

    Ok(RecoveryReport {
        header,
        records,
        tail,
        last_complete_offset: offset as u64,
        next_sequence: expected_sequence,
        last_record_sha256: expected_previous,
        unresolved,
    })
}

trait DurableWrite: Write {
    fn durable_sync(&mut self) -> io::Result<()>;
}

impl DurableWrite for File {
    fn durable_sync(&mut self) -> io::Result<()> {
        self.sync_data()
    }
}

fn commit_bytes<W: DurableWrite>(writer: &mut W, bytes: &[u8]) -> Result<(), JournalError> {
    writer.write_all(bytes).map_err(map_io_error)?;
    writer.durable_sync().map_err(map_io_error)
}

fn read_segment_bytes(file: &mut File) -> Result<Vec<u8>, JournalError> {
    let length = file.metadata().map_err(map_io_error)?.len();
    if length > MAX_SEGMENT_BYTES {
        return Err(JournalError::SegmentTooLarge(length));
    }
    file.seek(SeekFrom::Start(0)).map_err(map_io_error)?;
    let mut bytes = Vec::with_capacity(length as usize);
    file.take(MAX_SEGMENT_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(map_io_error)?;
    if bytes.len() as u64 > MAX_SEGMENT_BYTES {
        return Err(JournalError::SegmentTooLarge(bytes.len() as u64));
    }
    Ok(bytes)
}

fn create_private_file(path: &Path, create_new: bool) -> Result<File, JournalError> {
    validate_parent_components(path)?;
    OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(create_new)
        .mode(0o600)
        .custom_flags(OPEN_NOFOLLOW_FLAG)
        .open(path)
        .map_err(map_io_error)
}

fn open_existing_file(path: &Path, writable: bool) -> Result<File, JournalError> {
    validate_parent_components(path)?;
    let mut options = OpenOptions::new();
    options
        .read(true)
        .write(writable)
        .custom_flags(OPEN_NOFOLLOW_FLAG);
    let file = options.open(path).map_err(|error| {
        #[cfg(target_os = "linux")]
        if error.raw_os_error() == Some(40) {
            return JournalError::InsecurePath(
                "journal path became a symlink while opening".into(),
            );
        }
        map_io_error(error)
    })?;
    validate_opened_file(&file)?;
    Ok(file)
}

fn open_existing_file_checked(
    path: &Path,
    writable: bool,
    expected_identity: (u64, u64),
) -> Result<File, JournalError> {
    let file = open_existing_file(path, writable)?;
    let metadata = file.metadata().map_err(map_io_error)?;
    if !metadata_matches_identity(&metadata, expected_identity) {
        return Err(JournalError::InsecurePath(
            "journal path changed before opening".into(),
        ));
    }
    Ok(file)
}

fn validate_opened_file(file: &File) -> Result<(), JournalError> {
    let metadata = file.metadata().map_err(map_io_error)?;
    if !metadata.is_file() {
        return Err(JournalError::InsecurePath(
            "journal must be a regular file".into(),
        ));
    }
    if metadata.nlink() != 1 {
        return Err(JournalError::InsecurePath(
            "journal must have exactly one hard link".into(),
        ));
    }
    if metadata.permissions().mode() & 0o077 != 0 {
        return Err(JournalError::InsecurePath(
            "journal permissions must not grant group/other access".into(),
        ));
    }
    Ok(())
}

fn validate_new_path(path: &Path) -> Result<(), JournalError> {
    if path.as_os_str().is_empty() || path.file_name().is_none() {
        return Err(JournalError::InsecurePath(
            "path must name a regular file".into(),
        ));
    }
    validate_parent_components(path)?;
    if fs::symlink_metadata(path).is_ok() {
        return Err(JournalError::InsecurePath(
            "destination already exists".into(),
        ));
    }
    Ok(())
}

fn validate_existing_path_identity(path: &Path) -> Result<(u64, u64), JournalError> {
    validate_parent_components(path)?;
    let metadata = fs::symlink_metadata(path).map_err(map_io_error)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(JournalError::InsecurePath(
            "journal must be a regular non-symlink file".into(),
        ));
    }
    if metadata.nlink() != 1 {
        return Err(JournalError::InsecurePath(
            "journal must have exactly one hard link".into(),
        ));
    }
    if metadata.permissions().mode() & 0o077 != 0 {
        return Err(JournalError::InsecurePath(
            "journal permissions must not grant group/other access".into(),
        ));
    }
    Ok((metadata.dev(), metadata.ino()))
}

fn metadata_matches_identity(metadata: &fs::Metadata, identity: (u64, u64)) -> bool {
    metadata.file_type().is_file()
        && metadata.nlink() == 1
        && metadata.dev() == identity.0
        && metadata.ino() == identity.1
}

/// Validate every directory component above a journal file before opening it.
///
/// Checking only the immediate parent leaves an ancestor symlink or a
/// group/other-writable directory available for path substitution.  The
/// journal is commonly placed below `/tmp` in tests; a root-owned sticky
/// directory such as `/tmp` is the one deliberate exception to the
/// write-permission rule because sticky semantics prevent an unrelated user
/// from renaming entries owned by the journal user.  Ownership is otherwise
/// intentionally not constrained: the D3 service's private directory is
/// owned by `hepta-browserd`, not root.
fn validate_parent_components(path: &Path) -> Result<(), JournalError> {
    if path
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(JournalError::InsecurePath(
            "journal path must not contain '..'".into(),
        ));
    }

    let mut parent = path
        .parent()
        .ok_or_else(|| JournalError::InsecurePath("journal path has no parent directory".into()))?;
    loop {
        // `Path::parent` returns an empty path for a single relative
        // component.  The existing path validators will reject that case;
        // there is no directory component left for this helper to inspect.
        if parent.as_os_str().is_empty() {
            break;
        }
        let metadata = fs::symlink_metadata(parent).map_err(map_io_error)?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(JournalError::InsecurePath(format!(
                "journal parent {} must be a real directory",
                parent.display()
            )));
        }
        let mode = metadata.permissions().mode();
        let root_owned_sticky = metadata.uid() == 0 && mode & 0o1000 != 0;
        if mode & 0o022 != 0 && !root_owned_sticky {
            return Err(JournalError::InsecurePath(format!(
                "journal parent {} must not be group/other writable",
                parent.display()
            )));
        }
        let Some(next) = parent.parent() else {
            break;
        };
        if next == parent {
            break;
        }
        parent = next;
    }
    Ok(())
}

fn writer_lock_path(journal_path: &Path) -> Result<PathBuf, JournalError> {
    let file_name = journal_path
        .file_name()
        .ok_or_else(|| JournalError::InsecurePath("journal path has no file name".into()))?;
    let mut lock_name = file_name.to_os_string();
    lock_name.push(".");
    lock_name.push(WRITER_LOCK_SUFFIX);
    Ok(journal_path.with_file_name(lock_name))
}

fn sync_parent(path: &Path) -> Result<(), JournalError> {
    validate_parent_components(path)?;
    let parent = path
        .parent()
        .ok_or_else(|| JournalError::InsecurePath("path has no parent directory".into()))?;
    File::open(parent)
        .and_then(|directory| directory.sync_all())
        .map_err(map_io_error)
}

fn process_start_time(pid: u32) -> Result<u64, JournalError> {
    let path = PathBuf::from(format!("/proc/{pid}/stat"));
    let stat = read_bounded_text(&path, 64 * 1024, "process stat")?;
    parse_process_stat(&stat).map(|(_, start_time)| start_time)
}

fn current_process_stat() -> Result<(u32, u64), JournalError> {
    let stat = read_bounded_text(Path::new("/proc/self/stat"), 64 * 1024, "process stat")?;
    parse_process_stat(&stat)
}

fn parse_process_stat(stat: &str) -> Result<(u32, u64), JournalError> {
    let pid_end = stat
        .find(' ')
        .ok_or(JournalError::InvalidRecord("process stat lacks pid"))?;
    let pid = stat[..pid_end]
        .parse::<u32>()
        .map_err(|_| JournalError::InvalidRecord("process pid is invalid"))?;
    let end = stat.rfind(')').ok_or(JournalError::InvalidRecord(
        "process stat lacks command terminator",
    ))?;
    let fields: Vec<&str> = stat[end + 1..].split_whitespace().collect();
    let value = fields
        .get(19)
        .ok_or(JournalError::InvalidRecord("process stat lacks start time"))?;
    let start_time_ticks = value
        .parse::<u64>()
        .map_err(|_| JournalError::InvalidRecord("process start time is invalid"))?;
    if start_time_ticks == 0 {
        return Err(JournalError::InvalidRecord(
            "process start time must be non-zero",
        ));
    }
    Ok((pid, start_time_ticks))
}

fn read_bounded_text(
    path: &Path,
    max_bytes: usize,
    label: &'static str,
) -> Result<String, JournalError> {
    let file = File::open(path).map_err(map_io_error)?;
    let mut bytes = Vec::new();
    file.take(max_bytes as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(map_io_error)?;
    if bytes.len() > max_bytes {
        return Err(JournalError::InvalidInput(format!("{label} exceeds bound")));
    }
    String::from_utf8(bytes)
        .map_err(|_| JournalError::InvalidInput(format!("{label} is not UTF-8")))
}

fn validate_token(
    name: &'static str,
    value: &str,
    minimum: usize,
    maximum: usize,
) -> Result<(), JournalError> {
    let length = value.len();
    if length < minimum || length > maximum {
        return Err(JournalError::InvalidInput(format!(
            "{name} length is outside {minimum}..={maximum}"
        )));
    }
    if !value
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-'))
    {
        return Err(JournalError::InvalidInput(format!(
            "{name} contains a forbidden character"
        )));
    }
    Ok(())
}

fn validate_operation(value: &str) -> Result<(), JournalError> {
    validate_token("operation", value, 1, 128)?;
    if !value
        .bytes()
        .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"._:-".contains(&byte))
    {
        return Err(JournalError::InvalidInput(
            "operation must use lowercase token characters".into(),
        ));
    }
    Ok(())
}

fn validate_plan_revision(value: &str) -> Result<(), JournalError> {
    // D3 emits the active d6 revision.  Keep the exact d5 value admissible for
    // historical journals/fixtures, but require an explicit schema update for
    // every future revision so receipts cannot silently outrun the contract.
    if !matches!(value, "2026-08-28-d5" | "2026-08-29-d6") {
        return Err(JournalError::InvalidInput(
            "plan_revision must be 2026-08-29-d6 or historical 2026-08-28-d5".into(),
        ));
    }
    Ok(())
}

fn validate_error_code(value: &str) -> Result<(), JournalError> {
    if value.is_empty()
        || value.len() > 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
    {
        return Err(JournalError::InvalidInput(
            "error_code must be lowercase alphanumeric/underscore".into(),
        ));
    }
    Ok(())
}

fn validate_lower_hex(
    name: &'static str,
    value: &str,
    expected_length: usize,
) -> Result<(), JournalError> {
    if value.len() != expected_length
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(JournalError::InvalidInput(format!(
            "{name} must be {expected_length} lowercase hexadecimal characters"
        )));
    }
    Ok(())
}

fn validate_text(
    name: &'static str,
    value: &str,
    minimum: usize,
    maximum: usize,
) -> Result<(), JournalError> {
    if value.len() < minimum || value.len() > maximum {
        return Err(JournalError::InvalidInput(format!(
            "{name} length is outside {minimum}..={maximum}"
        )));
    }
    if value
        .chars()
        .any(|character| character.is_control() && !matches!(character, '\n' | '\t'))
    {
        return Err(JournalError::InvalidInput(format!(
            "{name} contains a forbidden control character"
        )));
    }
    Ok(())
}

fn put_u16(bytes: &mut Vec<u8>, value: u16) {
    bytes.extend_from_slice(&value.to_be_bytes());
}

fn put_u32(bytes: &mut Vec<u8>, value: u32) {
    bytes.extend_from_slice(&value.to_be_bytes());
}

fn put_u64(bytes: &mut Vec<u8>, value: u64) {
    bytes.extend_from_slice(&value.to_be_bytes());
}

fn put_string(bytes: &mut Vec<u8>, value: &str) -> Result<(), JournalError> {
    let length = u16::try_from(value.len())
        .map_err(|_| JournalError::InvalidInput("string exceeds u16 length".into()))?;
    if length == u16::MAX {
        return Err(JournalError::InvalidInput(
            "required string collides with optional sentinel".into(),
        ));
    }
    put_u16(bytes, length);
    bytes.extend_from_slice(value.as_bytes());
    Ok(())
}

fn put_optional_string(bytes: &mut Vec<u8>, value: Option<&str>) -> Result<(), JournalError> {
    match value {
        Some(value) => put_string(bytes, value),
        None => {
            put_u16(bytes, u16::MAX);
            Ok(())
        }
    }
}

fn sha256(bytes: &[u8]) -> Digest {
    Sha256::digest(bytes).into()
}

fn map_io_error(error: io::Error) -> JournalError {
    if matches!(error.raw_os_error(), Some(28) | Some(122)) {
        JournalError::StorageFull
    } else {
        JournalError::Io(error)
    }
}

fn json_escape(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character <= '\u{001f}' => {
                use std::fmt::Write as _;
                let _ = write!(output, "\\u{:04x}", character as u32);
            }
            character => output.push(character),
        }
    }
    output
}

fn json_option(value: Option<&str>) -> String {
    match value {
        Some(value) => format!("\"{}\"", json_escape(value)),
        None => "null".to_owned(),
    }
}

struct Cursor<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, offset: 0 }
    }

    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.offset)
    }

    fn skip(&mut self, length: usize) -> Result<(), JournalError> {
        self.take(length).map(|_| ())
    }

    fn take(&mut self, length: usize) -> Result<&'a [u8], JournalError> {
        let end = self
            .offset
            .checked_add(length)
            .ok_or(JournalError::InvalidRecord("cursor overflow"))?;
        let slice = self
            .bytes
            .get(self.offset..end)
            .ok_or(JournalError::InvalidRecord("unexpected end of record"))?;
        self.offset = end;
        Ok(slice)
    }

    fn array<const N: usize>(&mut self) -> Result<[u8; N], JournalError> {
        self.take(N)?
            .try_into()
            .map_err(|_| JournalError::InvalidRecord("fixed array length mismatch"))
    }

    fn u8(&mut self) -> Result<u8, JournalError> {
        Ok(self.take(1)?[0])
    }

    fn u16(&mut self) -> Result<u16, JournalError> {
        Ok(u16::from_be_bytes(self.array()?))
    }

    fn u32(&mut self) -> Result<u32, JournalError> {
        Ok(u32::from_be_bytes(self.array()?))
    }

    fn u64(&mut self) -> Result<u64, JournalError> {
        Ok(u64::from_be_bytes(self.array()?))
    }

    fn string(&mut self) -> Result<String, JournalError> {
        let length = self.u16()?;
        if length == u16::MAX {
            return Err(JournalError::InvalidRecord(
                "required string uses optional sentinel",
            ));
        }
        String::from_utf8(self.take(length as usize)?.to_vec())
            .map_err(|_| JournalError::InvalidRecord("record string is not UTF-8"))
    }

    fn optional_string(&mut self) -> Result<Option<String>, JournalError> {
        let length = self.u16()?;
        if length == u16::MAX {
            return Ok(None);
        }
        String::from_utf8(self.take(length as usize)?.to_vec())
            .map(Some)
            .map_err(|_| JournalError::InvalidRecord("record string is not UTF-8"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    use std::process;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::thread;

    static NEXT_TEST_ID: AtomicU64 = AtomicU64::new(1);

    fn temp_dir(name: &str) -> PathBuf {
        let id = NEXT_TEST_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "hepta-receipt-journal-{name}-{}-{id}",
            process::id()
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir(&path).expect("create test directory");
        path
    }

    #[test]
    fn process_identity_uses_procfs_self_pid_and_start_time() {
        // `/proc/self/stat` reports the PID in the procfs namespace visible
        // to this process.  This is intentionally not compared with
        // `process::id()`: under a host-mounted procfs they can differ.
        let identity = ProcessIdentity::current().expect("read current process identity");
        let (procfs_pid, procfs_start) = current_process_stat().expect("read /proc/self/stat");
        assert_eq!(identity.pid, procfs_pid);
        assert_eq!(identity.start_time_ticks, procfs_start);
        assert!(identity.is_active().expect("current process is active"));
    }

    #[test]
    fn process_stat_parser_uses_last_command_terminator() {
        // The command field may contain a closing parenthesis.  The Linux
        // procfs format terminates it at the final `)` before the state field.
        let stat = "42 (worker ) name) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 12345 20";
        assert_eq!(
            parse_process_stat(stat).expect("parse synthetic stat"),
            (42, 12345)
        );
    }

    #[test]
    fn process_stat_parser_rejects_zero_start_time() {
        let stat = "42 (worker) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 0 20";
        assert!(matches!(
            parse_process_stat(stat),
            Err(JournalError::InvalidRecord(
                "process start time must be non-zero"
            ))
        ));
    }

    #[test]
    fn malformed_writer_lock_is_never_recovered_as_stale() {
        let directory = temp_dir("malformed-writer-lock");
        let path = directory.join("journal.bin");
        let journal =
            ReceiptJournal::create(&path, JournalId([21; 16]), 1).expect("create journal");
        drop(journal);

        let lock = writer_lock_path(&path).expect("writer lock path");
        let mut lock_file = OpenOptions::new()
            .read(true)
            .write(true)
            .truncate(true)
            .open(&lock)
            .expect("open malformed lock");
        lock_file
            .write_all(b"pid=\n")
            .expect("write partial lock payload");
        lock_file.sync_all().expect("sync partial lock payload");
        drop(lock_file);

        // Even crash-recovery mode must not unlink a lock whose payload is
        // malformed or only partially committed: the original writer may
        // still be finishing its payload.
        assert!(matches!(
            ReceiptJournal::open(&path, OpenPolicy::RECOVER_CRASH),
            Err(JournalError::InvalidRecord(_))
        ));
        assert_eq!(fs::read(&lock).expect("malformed lock remains"), b"pid=\n");
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn partially_written_locked_lease_is_busy_not_recovered() {
        let directory = temp_dir("partial-writer-lock");
        let path = directory.join("journal.bin");
        let journal =
            ReceiptJournal::create(&path, JournalId([23; 16]), 1).expect("create journal");
        drop(journal);

        let lock = writer_lock_path(&path).expect("writer lock path");
        let mut lock_file = OpenOptions::new()
            .read(true)
            .write(true)
            .truncate(true)
            .open(&lock)
            .expect("open partial lock");
        lock_file.try_lock().expect("hold partial lock");
        lock_file
            .write_all(b"pid=")
            .expect("write partial lock payload");
        lock_file.sync_all().expect("sync partial lock payload");

        // The second opener must observe the OS lock before parsing the
        // incomplete payload.  Returning WriterBusy avoids treating a live
        // creator as stale and unlinking its lock.
        assert!(matches!(
            ReceiptJournal::open(&path, OpenPolicy::RECOVER_CRASH),
            Err(JournalError::WriterBusy)
        ));
        assert_eq!(fs::read(&lock).expect("partial lock remains"), b"pid=");
        drop(lock_file);
        fs::remove_file(&lock).expect("remove partial lock");
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn writer_lock_drop_does_not_unlink_replacement_inode() {
        let directory = temp_dir("writer-lock-replacement");
        let path = directory.join("journal.bin");
        let journal =
            ReceiptJournal::create(&path, JournalId([22; 16]), 1).expect("create journal");
        let lock = writer_lock_path(&path).expect("writer lock path");
        let displaced = directory.join("displaced-lock");
        fs::rename(&lock, &displaced).expect("displace owned lock");
        let mut replacement = create_private_file(&lock, true).expect("create replacement lock");
        replacement
            .write_all(b"replacement")
            .expect("write replacement marker");
        replacement.sync_all().expect("sync replacement marker");

        drop(journal);
        assert!(
            lock.exists(),
            "tearing down an old lease must not remove a replacement lock"
        );
        drop(replacement);
        fs::remove_file(&lock).expect("remove replacement lock");
        fs::remove_file(&displaced).expect("remove displaced lock");
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn clean_writer_drop_leaves_reusable_release_marker() {
        let directory = temp_dir("writer-lock-release-marker");
        let path = directory.join("journal.bin");
        let journal =
            ReceiptJournal::create(&path, JournalId([29; 16]), 1).expect("create journal");
        let lock = writer_lock_path(&path).expect("writer lock path");
        drop(journal);
        assert_eq!(
            fs::read(&lock).expect("release marker remains"),
            b"released=1\n"
        );
        // A clean marker is safe to reuse even under STRICT; active or
        // malformed payloads retain the fail-closed behavior above.
        let reopened = ReceiptJournal::open(&path, OpenPolicy::STRICT).expect("strict reopen");
        drop(reopened);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn existing_journal_symlink_paths_are_rejected() {
        let directory = temp_dir("symlink");
        let target = directory.join("journal.bin");
        let link = directory.join("journal-link.bin");
        let journal =
            ReceiptJournal::create(&target, JournalId([17; 16]), 1).expect("create target journal");
        drop(journal);
        symlink(&target, &link).expect("create symlink");

        assert!(matches!(
            inspect_path(&link),
            Err(JournalError::InsecurePath(_))
        ));
        assert!(matches!(
            ReceiptJournal::open(&link, OpenPolicy::STRICT),
            Err(JournalError::InsecurePath(_))
        ));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn hardlinked_journal_aliases_are_rejected() {
        let directory = temp_dir("hardlink-alias");
        let target = directory.join("journal.bin");
        let alias = directory.join("journal-alias.bin");
        let journal =
            ReceiptJournal::create(&target, JournalId([24; 16]), 1).expect("create journal");
        drop(journal);
        fs::hard_link(&target, &alias).expect("create hard-link alias");

        assert!(matches!(
            ReceiptJournal::open(&alias, OpenPolicy::STRICT),
            Err(JournalError::InsecurePath(reason))
                if reason.contains("exactly one hard link")
        ));
        assert!(matches!(
            inspect_path(&alias),
            Err(JournalError::InsecurePath(reason))
                if reason.contains("exactly one hard link")
        ));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn journal_inode_identity_check_rejects_rename_replacement() {
        let directory = temp_dir("rename-replacement");
        let path = directory.join("journal.bin");
        let displaced = directory.join("journal.displaced");
        let journal =
            ReceiptJournal::create(&path, JournalId([25; 16]), 1).expect("create journal");
        drop(journal);

        // Model the interval between the initial open and sidecar admission:
        // retain the original inode, replace the pathname with another
        // private regular file, and verify that the post-admission identity
        // comparison rejects the substitution.
        let file = open_existing_file(&path, true).expect("open original journal");
        lock_file(&file).expect("lock original journal");
        let original = file.metadata().expect("original metadata");
        fs::rename(&path, &displaced).expect("displace original path");
        let replacement = create_private_file(&path, true).expect("create replacement");
        drop(replacement);
        assert!(!path_matches_metadata(&path, &original).expect("compare path identity"));
        drop(file);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn journal_preopen_identity_check_rejects_replacement_inode() {
        let directory = temp_dir("preopen-rename-replacement");
        let path = directory.join("journal.bin");
        let displaced = directory.join("journal.displaced");
        let journal =
            ReceiptJournal::create(&path, JournalId([26; 16]), 1).expect("create journal");
        drop(journal);

        // Capture the same no-follow metadata snapshot used by `open`, then
        // replace the pathname before opening it.  The FD now names B, so the
        // pre-open identity comparison must reject it rather than silently
        // recovering a foreign journal.
        let expected = validate_existing_path_identity(&path).expect("identity");
        fs::rename(&path, &displaced).expect("displace original path");
        let replacement = create_private_file(&path, true).expect("create replacement");
        drop(replacement);
        assert!(matches!(
            open_existing_file_checked(&path, true, expected),
            Err(JournalError::InsecurePath(reason))
                if reason.contains("changed before opening")
        ));

        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn nofollow_open_rejects_symlink_even_without_metadata_preflight() {
        let directory = temp_dir("symlink-nofollow");
        let target = directory.join("target.bin");
        let link = directory.join("link.bin");
        let mut file = create_private_file(&target, true).expect("create target");
        file.write_all(b"fixture").expect("write target");
        file.sync_all().expect("sync target");
        drop(file);
        symlink(&target, &link).expect("create symlink");

        assert!(matches!(
            open_existing_file(&link, false),
            Err(JournalError::InsecurePath(_))
        ));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn parent_component_symlink_is_rejected() {
        let directory = temp_dir("parent-symlink");
        let real = directory.join("real");
        let link = directory.join("link");
        fs::create_dir(&real).expect("create real parent");
        symlink(&real, &link).expect("create parent symlink");

        // Keep the immediate parent a real directory so this specifically
        // exercises validation of an ancestor component rather than the
        // existing direct-parent check.
        let immediate_parent = link.join("nested");
        fs::create_dir(&immediate_parent).expect("create nested parent");
        let path = immediate_parent.join("journal.bin");
        assert!(matches!(
            ReceiptJournal::create(&path, JournalId([18; 16]), 1),
            Err(JournalError::InsecurePath(reason))
                if reason.contains("must be a real directory")
        ));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn writable_parent_component_is_rejected() {
        let directory = temp_dir("parent-permissions");
        let outer = directory.join("outer");
        let inner = outer.join("inner");
        fs::create_dir(&outer).expect("create outer parent");
        fs::create_dir(&inner).expect("create inner parent");
        let path = inner.join("journal.bin");
        let journal =
            ReceiptJournal::create(&path, JournalId([19; 16]), 1).expect("create journal");
        drop(journal);

        fs::set_permissions(&outer, fs::Permissions::from_mode(0o775))
            .expect("make ancestor group writable");
        assert!(matches!(
            inspect_path(&path),
            Err(JournalError::InsecurePath(reason))
                if reason.contains("must not be group/other writable")
        ));
        // Restore a private mode before removing the temporary tree so the
        // test remains valid under a non-root runner as well.
        fs::set_permissions(&outer, fs::Permissions::from_mode(0o755))
            .expect("restore ancestor permissions");
        fs::remove_dir_all(directory).expect("cleanup");
    }

    fn digest(byte: u8) -> Digest {
        [byte; 32]
    }

    fn event(receipt_id: &str, lifecycle: LifecycleState) -> ReceiptEvent {
        ReceiptEvent {
            receipt_id: receipt_id.to_owned(),
            plan_revision: "2026-08-28-d5".to_owned(),
            image_id: "image-fixture".to_owned(),
            servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".to_owned(),
            browserd_version: "0.1.0".to_owned(),
            session_id: "session-1".to_owned(),
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 1,
            mutation_epoch: 0,
            source: ReceiptSource::Agent,
            operation: "page.observe".to_owned(),
            lifecycle,
            outcome: None,
            effect_class: EffectClass::Observation,
            privacy_class: PrivacyClass::Internal,
            request_sha256: digest(1),
            response_sha256: None,
            error_code: None,
            detail: Some("fixture".to_owned()),
            monotonic_ms: 10,
            wall_clock_unix_ms: 20,
        }
    }

    #[test]
    fn receipt_plan_revision_accepts_d6_and_historical_d5_only() {
        for revision in ["2026-08-29-d6", "2026-08-28-d5"] {
            let mut value = event("revision", LifecycleState::Requested);
            value.plan_revision = revision.to_owned();
            value.validate().expect("supported plan revision");
        }
        for revision in ["2026-08-27-d4", "2026-08-29-d7", "2026-08-29-d06"] {
            let mut value = event("revision", LifecycleState::Requested);
            value.plan_revision = revision.to_owned();
            assert!(matches!(
                value.validate(),
                Err(JournalError::InvalidInput(message))
                    if message.contains("plan_revision")
            ));
        }
    }

    #[test]
    fn append_recover_and_chain_three_lifecycle_records() {
        let directory = temp_dir("roundtrip");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([7; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append requested");
        journal
            .append(event("receipt-1", LifecycleState::Dispatched))
            .expect("append dispatched");
        let mut completed = event("receipt-1", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(2));
        journal.append(completed).expect("append completion");
        let seal = journal.seal().expect("seal");
        drop(journal);

        let report = inspect_path(&path).expect("recover");
        assert_eq!(report.tail, TailStatus::Clean);
        assert_eq!(report.records.len(), 3);
        assert!(report.unresolved.is_empty());
        assert_eq!(report.next_sequence, 4);
        assert_eq!(seal.last_sequence, Some(3));
        assert_eq!(seal.last_record_sha256, report.last_record_sha256);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn reopen_preserves_highest_monotonic_lifecycle_timestamp() {
        let directory = temp_dir("monotonic-reopen");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([30; 16]), 1).expect("create journal");
        let mut first = event("clock-1", LifecycleState::Requested);
        first.monotonic_ms = 41;
        journal.append(first).expect("append first");
        let mut second = event("clock-1", LifecycleState::Dispatched);
        second.monotonic_ms = 7;
        journal.append(second).expect("append second");
        assert_eq!(journal.last_monotonic_ms(), 41);
        drop(journal);

        let reopened = ReceiptJournal::open(&path, OpenPolicy::STRICT).expect("reopen");
        assert_eq!(
            reopened.last_monotonic_ms(),
            41,
            "reopened writer must not reset its logical timestamp"
        );
        drop(reopened);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn rotation_preserves_highest_monotonic_lifecycle_timestamp() {
        let directory = temp_dir("monotonic-rotation");
        let first = directory.join("segment-1.bin");
        let second = directory.join("segment-2.bin");
        let mut journal =
            ReceiptJournal::create(&first, JournalId([31; 16]), 1).expect("create journal");
        let mut requested = event("clock-rotate", LifecycleState::Requested);
        requested.monotonic_ms = 91;
        journal.append(requested).expect("append request");
        let mut dispatched = event("clock-rotate", LifecycleState::Dispatched);
        dispatched.monotonic_ms = 12;
        journal.append(dispatched).expect("append dispatch");
        let mut completed = event("clock-rotate", LifecycleState::Completed);
        completed.monotonic_ms = 7;
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(3));
        journal.append(completed).expect("append completion");

        let (_, next) = journal.rotate(&second, 2).expect("rotate");
        assert_eq!(next.last_monotonic_ms(), 91);
        drop(next);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn invalid_lifecycle_transition_is_rejected() {
        let directory = temp_dir("transition");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([8; 16]), 1).expect("create journal");
        let mut completed = event("receipt-1", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(2));
        let error = journal
            .append(completed)
            .expect_err("completion before request must fail");
        assert!(matches!(error, JournalError::InvalidTransition { .. }));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn sequence_overflow_is_rejected_before_durable_append() {
        let directory = temp_dir("sequence-overflow");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([20; 16]), 1).expect("create journal");
        let before = fs::read(&path).expect("read header");

        // Exercise the terminal cursor directly; reaching this value through
        // normal appends is infeasible, but a persisted/corrupt input must
        // still fail without writing a record.
        journal.next_sequence = u64::MAX;
        let error = journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect_err("sequence overflow must fail before write");
        assert!(matches!(
            error,
            JournalError::InvalidInput(message) if message == "sequence overflow"
        ));
        assert_eq!(journal.next_sequence, u64::MAX);
        assert_eq!(fs::read(&path).expect("read unchanged journal"), before);
        drop(journal);

        // Reopening proves the rejected attempt left a clean, appendable
        // journal rather than a torn or partially committed record.
        let mut reopened = ReceiptJournal::open(&path, OpenPolicy::STRICT).expect("reopen");
        let committed = reopened
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append after rejected overflow");
        assert_eq!(committed.sequence, 1);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn append_rejects_active_path_inode_replacement_and_poisons_writer() {
        let directory = temp_dir("append-inode-replacement");
        let path = directory.join("journal.bin");
        let displaced = directory.join("journal.displaced");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([27; 16]), 1).expect("create journal");
        fs::rename(&path, &displaced).expect("displace open path");
        let replacement = create_private_file(&path, true).expect("create replacement");
        drop(replacement);

        let error = journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect_err("append must reject path replacement");
        assert!(matches!(
            error,
            JournalError::InsecurePath(reason)
                if reason.contains("open inode") || reason.contains("inode changed")
        ));
        assert!(matches!(
            journal.append(event("receipt-1", LifecycleState::Requested)),
            Err(JournalError::WriterPoisoned)
        ));
        drop(journal);
        assert!(
            path.exists(),
            "replacement path must not be removed by old writer"
        );
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn append_rejects_external_length_drift_and_poisons_writer() {
        let directory = temp_dir("append-length-drift");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([28; 16]), 1).expect("create journal");
        let mut external = OpenOptions::new()
            .append(true)
            .open(&path)
            .expect("open external append handle");
        external.write_all(b"tamper").expect("write drift");
        external.sync_all().expect("sync drift");
        drop(external);

        let error = journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect_err("append must reject external length drift");
        assert!(matches!(error, JournalError::Corruption { .. }));
        assert!(matches!(
            journal.append(event("receipt-1", LifecycleState::Requested)),
            Err(JournalError::WriterPoisoned)
        ));
        drop(journal);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn completed_event_requires_response_digest() {
        let mut completed = event("receipt-1", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        let error = completed
            .validate()
            .expect_err("completed event without response digest must fail");
        assert!(matches!(
            error,
            JournalError::InvalidInput(message)
                if message == "completed event requires response_sha256"
        ));
    }

    #[test]
    fn torn_tail_requires_explicit_repair_and_preserves_last_complete_record() {
        let directory = temp_dir("torn-tail");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([9; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append");
        let clean_offset = journal.end_offset;
        drop(journal);
        let mut file = OpenOptions::new().append(true).open(&path).expect("open");
        file.write_all(&RECORD_MAGIC[..4]).expect("partial write");
        file.sync_data().expect("sync partial");
        drop(file);

        let report = inspect_path(&path).expect("inspect torn tail");
        assert!(matches!(report.tail, TailStatus::TornTail { .. }));
        assert_eq!(report.last_complete_offset, clean_offset);
        assert!(matches!(
            ReceiptJournal::open(&path, OpenPolicy::STRICT),
            Err(JournalError::TornTailNeedsRepair { .. })
        ));
        let mut repaired =
            ReceiptJournal::open(&path, OpenPolicy::RECOVER_CRASH).expect("repair torn tail");
        assert_eq!(repaired.inspect().expect("inspect").tail, TailStatus::Clean);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn complete_record_tampering_is_hard_corruption() {
        let directory = temp_dir("corruption");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([10; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append");
        drop(journal);
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .expect("open");
        file.seek(SeekFrom::Start(
            (SEGMENT_HEADER_LEN + RECORD_PREFIX_LEN + 4) as u64,
        ))
        .expect("seek");
        file.write_all(&[0xff]).expect("tamper");
        file.sync_data().expect("sync");
        drop(file);
        assert!(matches!(
            inspect_path(&path),
            Err(JournalError::Corruption { .. })
        ));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn dispatched_external_effect_recovers_never_automatic() {
        let directory = temp_dir("external-effect");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([11; 16]), 1).expect("create journal");
        let mut requested = event("effect-1", LifecycleState::Requested);
        requested.operation = "page.navigate".to_owned();
        requested.effect_class = EffectClass::PotentialExternalEffect;
        journal.append(requested.clone()).expect("request");
        requested.lifecycle = LifecycleState::Dispatched;
        journal.append(requested).expect("dispatch");
        drop(journal);
        let report = inspect_path(&path).expect("recover");
        assert_eq!(report.unresolved.len(), 1);
        assert_eq!(report.unresolved[0].replay, ReplayDirective::NeverAutomatic);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn sensitive_export_redacts_detail_and_binds_source_segment() {
        let directory = temp_dir("export");
        let path = directory.join("journal.bin");
        let export = directory.join("export.jsonl");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([12; 16]), 1).expect("create journal");
        let mut requested = event("receipt-1", LifecycleState::Requested);
        requested.privacy_class = PrivacyClass::Sensitive;
        requested.detail = Some("must-not-export".to_owned());
        journal.append(requested).expect("append");
        let report = journal.inspect().expect("inspect");
        let export_digest = export_journal_redacted_jsonl(&report, &export).expect("export");
        let text = fs::read_to_string(&export).expect("read export");
        assert!(!text.contains("must-not-export"));
        assert!(text.contains("\"detail\":null"));
        assert_ne!(export_digest, ZERO_DIGEST);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn canonical_export_matches_receipt_v1_envelope_shape() {
        let directory = temp_dir("canonical-export");
        let path = directory.join("journal.bin");
        let export = directory.join("receipt.jsonl");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([40; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-canonical", LifecycleState::Requested))
            .expect("append request");
        journal
            .append(event("receipt-canonical", LifecycleState::Dispatched))
            .expect("append dispatch");
        let mut completed = event("receipt-canonical", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(8));
        journal.append(completed).expect("append completion");
        let report = journal.inspect().expect("inspect");
        let digest = export_redacted_jsonl(&report, &export).expect("canonical export");
        let text = fs::read_to_string(&export).expect("read export");
        let line = text.trim_end_matches('\n');
        assert_eq!(text.lines().count(), 1);
        assert!(line.starts_with("{\"schema\":\"trillionnium.desktop.receipt.v1\""));
        for field in [
            "receipt_id",
            "plan_revision",
            "image_id",
            "servo_commit",
            "browserd_version",
            "session_id",
            "session_generation",
            "document_generation",
            "semantic_snapshot_revision",
            "mutation_epoch",
            "source",
            "operation",
            "status",
            "started_monotonic_ms",
            "finished_monotonic_ms",
        ] {
            assert!(line.contains(&format!("\"{field}\":")), "missing {field}");
        }
        assert!(line.contains("\"status\":\"succeeded\""));
        assert!(!line.contains("\"error_code\":"));
        assert!(!line.contains("\"lifecycle\":"));
        assert!(!line.contains("\"record_sha256\":"));
        assert_ne!(digest, ZERO_DIGEST);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn canonical_export_maps_indeterminate_and_rejects_unresolved() {
        let directory = temp_dir("canonical-indeterminate");
        let path = directory.join("journal.bin");
        let export = directory.join("receipt.jsonl");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([41; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-indeterminate", LifecycleState::Requested))
            .expect("append request");
        journal
            .append(event("receipt-indeterminate", LifecycleState::Dispatched))
            .expect("append dispatch");
        let mut terminal = event("receipt-indeterminate", LifecycleState::Indeterminate);
        terminal.error_code = Some("browser_crashed".to_owned());
        journal.append(terminal).expect("append indeterminate");
        let report = journal.inspect().expect("inspect");
        export_redacted_jsonl(&report, &export).expect("canonical export");
        let text = fs::read_to_string(&export).expect("read export");
        assert!(text.contains("\"status\":\"indeterminate\""));
        assert!(text.contains("\"error_code\":\"browser_crashed\""));

        let unresolved_path = directory.join("unresolved.bin");
        let unresolved_export = directory.join("unresolved.jsonl");
        let mut unresolved =
            ReceiptJournal::create(&unresolved_path, JournalId([42; 16]), 1).expect("create");
        unresolved
            .append(event("receipt-open", LifecycleState::Requested))
            .expect("append request");
        let unresolved_report = unresolved.inspect().expect("inspect unresolved");
        assert!(matches!(
            export_redacted_jsonl(&unresolved_report, &unresolved_export),
            Err(JournalError::InvalidInput(message))
                if message.contains("has no terminal lifecycle record")
        ));
        assert!(!unresolved_export.exists());
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn receipt_envelope_validation_rejects_schema_rule_drift() {
        let mut succeeded = ReceiptEnvelope {
            schema: ReceiptEnvelope::SCHEMA.to_owned(),
            receipt_id: "receipt-schema".to_owned(),
            plan_revision: "2026-08-29-d6".to_owned(),
            image_id: "image-fixture".to_owned(),
            servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".to_owned(),
            browserd_version: "0.1.0".to_owned(),
            session_id: "session-1".to_owned(),
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 0,
            mutation_epoch: 0,
            source: ReceiptSource::Agent,
            operation: "page.observe".to_owned(),
            status: ReceiptStatus::Succeeded,
            error_code: None,
            started_monotonic_ms: 10,
            finished_monotonic_ms: 11,
            wall_clock_unix_ms: Some(12),
        };
        succeeded.validate().expect("valid succeeded envelope");

        succeeded.error_code = Some("internal".to_owned());
        assert!(matches!(
            succeeded.validate(),
            Err(JournalError::InvalidInput(message))
                if message.contains("may not carry error_code")
        ));

        succeeded.status = ReceiptStatus::Indeterminate;
        succeeded.error_code = None;
        assert!(matches!(
            succeeded.validate(),
            Err(JournalError::InvalidInput(message))
                if message.contains("requires error_code")
        ));

        succeeded.error_code = Some("internal".to_owned());
        succeeded.finished_monotonic_ms = 9;
        assert!(matches!(
            succeeded.validate(),
            Err(JournalError::InvalidInput(message))
                if message.contains("finished_monotonic_ms")
        ));

        succeeded.finished_monotonic_ms = 11;
        succeeded.document_generation = 0;
        assert!(matches!(
            succeeded.validate(),
            Err(JournalError::InvalidInput(message))
                if message.contains("document_generation")
        ));
    }

    #[test]
    fn rotation_continues_global_sequence_and_binds_segments() {
        let directory = temp_dir("rotation");
        let first = directory.join("segment-1.bin");
        let second = directory.join("segment-2.bin");
        let mut journal =
            ReceiptJournal::create(&first, JournalId([13; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append request");
        journal
            .append(event("receipt-1", LifecycleState::Dispatched))
            .expect("append dispatch");
        let mut completed = event("receipt-1", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(2));
        journal.append(completed).expect("append completion");
        let (seal, mut next) = journal.rotate(&second, 2).expect("rotate");
        let committed = next
            .append(event("receipt-2", LifecycleState::Requested))
            .expect("append second segment");
        assert_eq!(committed.sequence, 4);
        let report = next.inspect().expect("inspect");
        assert_eq!(report.header.previous_segment_sha256, seal.segment_sha256);
        assert_eq!(
            report.header.previous_record_sha256,
            seal.last_record_sha256
        );
        let chain = inspect_chain([&first, &second]).expect("verify segment chain");
        assert_eq!(chain.len(), 2);
        assert_eq!(chain[0].header.segment_number, 1);
        assert_eq!(chain[1].header.segment_number, 2);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn rotation_preserves_receipt_namespace_and_chain_rejects_replay() {
        let directory = temp_dir("rotation-receipt-namespace");
        let first = directory.join("segment-1.bin");
        let second = directory.join("segment-2.bin");
        let mut journal =
            ReceiptJournal::create(&first, JournalId([29; 16]), 1).expect("create journal");
        journal
            .append(event("replay-me", LifecycleState::Requested))
            .expect("append request");
        journal
            .append(event("replay-me", LifecycleState::Dispatched))
            .expect("append dispatch");
        let mut completed = event("replay-me", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(9));
        journal.append(completed).expect("append completion");

        // The in-memory successor inherits terminal receipt progress.  A
        // reused ID must be rejected before any bytes are appended.
        let (_, mut next) = journal.rotate(&second, 2).expect("rotate");
        assert!(matches!(
            next.append(event("replay-me", LifecycleState::Requested)),
            Err(JournalError::InvalidTransition {
                from: Some(LifecycleState::Completed),
                to: LifecycleState::Requested,
                ..
            })
        ));
        next.append(event("fresh-id", LifecycleState::Requested))
            .expect("fresh receipt remains admissible");
        drop(next);

        // A process that reopens only the new segment starts with no in-memory
        // predecessor map.  Simulate that legacy/restarted writer: the
        // duplicate can be appended to the segment itself, but chain
        // inspection must independently carry progress across the boundary
        // and reject it.
        let mut reopened = ReceiptJournal::open(&second, OpenPolicy::STRICT).expect("reopen");
        reopened
            .append(event("replay-me", LifecycleState::Requested))
            .expect("legacy writer can append duplicate locally");
        drop(reopened);

        assert!(matches!(
            inspect_chain([&first, &second]),
            Err(JournalError::Corruption { reason, .. })
                if reason.contains("cross-segment receipt lifecycle")
        ));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn rotation_rejects_out_of_band_append_before_creating_successor() {
        let directory = temp_dir("rotation-drift");
        let first = directory.join("segment-1.bin");
        let second = directory.join("segment-2.bin");
        let mut journal =
            ReceiptJournal::create(&first, JournalId([31; 16]), 1).expect("create journal");
        journal
            .append(event("rotation-drift", LifecycleState::Requested))
            .expect("append request");
        journal
            .append(event("rotation-drift", LifecycleState::Dispatched))
            .expect("append dispatch");
        let mut completed = event("rotation-drift", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(10));
        journal.append(completed).expect("append completion");

        // Simulate a same-UID writer that ignores advisory locks and appends
        // after the in-memory cursor was last checked. Rotation must fail
        // closed rather than sealing the drifted bytes and creating a broken
        // successor header.
        let mut external = OpenOptions::new()
            .append(true)
            .open(&first)
            .expect("open external append handle");
        external.write_all(b"out-of-band").expect("append drift");
        external.sync_all().expect("sync drift");
        drop(external);

        let error = match journal.rotate(&second, 2) {
            Ok(_) => panic!("rotation must reject cursor drift"),
            Err(error) => error,
        };
        assert!(matches!(error, JournalError::Corruption { .. }));
        assert!(
            !second.exists(),
            "failed rotation must not create successor"
        );
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn chain_rejects_missing_or_reordered_segments() {
        let directory = temp_dir("chain-order");
        let first = directory.join("segment-1.bin");
        let second = directory.join("segment-2.bin");
        let third = directory.join("segment-3.bin");
        let mut journal =
            ReceiptJournal::create(&first, JournalId([15; 16]), 1).expect("create journal");

        for (receipt_id, response_byte) in [("receipt-1", 1_u8), ("receipt-2", 2_u8)] {
            journal
                .append(event(receipt_id, LifecycleState::Requested))
                .expect("append request");
            journal
                .append(event(receipt_id, LifecycleState::Dispatched))
                .expect("append dispatch");
            let mut completed = event(receipt_id, LifecycleState::Completed);
            completed.outcome = Some(ReceiptOutcome::Succeeded);
            completed.response_sha256 = Some(digest(response_byte));
            journal.append(completed).expect("append completion");
            if receipt_id == "receipt-1" {
                let (_, next) = journal.rotate(&second, 2).expect("rotate to second");
                journal = next;
            }
        }
        let (_, third_journal) = journal.rotate(&third, 3).expect("rotate to third");
        drop(third_journal);

        // Segment three cannot be linked directly to segment one, and a
        // suffix or reversed order cannot masquerade as a complete chain.
        assert!(matches!(
            inspect_chain([&first, &third]),
            Err(JournalError::Corruption { .. })
        ));
        assert!(matches!(
            inspect_chain([&second, &third]),
            Err(JournalError::Corruption { .. })
        ));
        assert!(matches!(
            inspect_chain([&third, &second]),
            Err(JournalError::Corruption { .. })
        ));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn chain_rejects_tampered_predecessor_digest_link() {
        let directory = temp_dir("chain-link");
        let first = directory.join("segment-1.bin");
        let second = directory.join("segment-2.bin");
        let mut journal =
            ReceiptJournal::create(&first, JournalId([16; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append request");
        journal
            .append(event("receipt-1", LifecycleState::Dispatched))
            .expect("append dispatch");
        let mut completed = event("receipt-1", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(3));
        journal.append(completed).expect("append completion");
        let (_, next) = journal.rotate(&second, 2).expect("rotate");
        drop(next);

        // Re-encode a valid header with a forged predecessor digest.  The
        // segment remains internally valid, so only cross-segment verification
        // can detect the substitution.
        let mut bytes = fs::read(&second).expect("read second segment");
        let mut header =
            decode_segment_header(&bytes[..SEGMENT_HEADER_LEN]).expect("decode second header");
        header.previous_segment_sha256 = digest(0xee);
        let encoded = encode_segment_header(&header).expect("encode forged header");
        bytes[..SEGMENT_HEADER_LEN].copy_from_slice(&encoded);
        fs::write(&second, bytes).expect("write forged header");
        assert!(inspect_path(&second).is_ok());
        let error = inspect_chain([&first, &second]).expect_err("forged link must fail");
        assert!(
            matches!(error, JournalError::Corruption { reason, .. } if reason.contains("previous-segment digest link"))
        );
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn retention_prunes_only_old_exported_non_active_segments() {
        let safe = digest(7);
        let unsafe_digest = digest(8);
        let entries = vec![
            ArchivedSegment {
                path: PathBuf::from("one"),
                segment_number: 1,
                sealed_sha256: safe,
                exported_source_sha256: Some(safe),
                active: false,
            },
            ArchivedSegment {
                path: PathBuf::from("two"),
                segment_number: 2,
                sealed_sha256: unsafe_digest,
                exported_source_sha256: None,
                active: false,
            },
            ArchivedSegment {
                path: PathBuf::from("three"),
                segment_number: 3,
                sealed_sha256: digest(9),
                exported_source_sha256: Some(digest(9)),
                active: true,
            },
        ];
        assert_eq!(
            retention_candidates(&entries, 1).expect("retention"),
            vec![PathBuf::from("one")]
        );
    }

    struct FaultyWriter {
        bytes: Vec<u8>,
        remaining: usize,
        error: i32,
    }

    impl Write for FaultyWriter {
        fn write(&mut self, input: &[u8]) -> io::Result<usize> {
            if self.remaining == 0 {
                return Err(io::Error::from_raw_os_error(self.error));
            }
            let count = input.len().min(self.remaining);
            self.bytes.extend_from_slice(&input[..count]);
            self.remaining -= count;
            Ok(count)
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl DurableWrite for FaultyWriter {
        fn durable_sync(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn disk_full_is_typed_and_partial_bytes_never_become_committed_state() {
        let mut writer = FaultyWriter {
            bytes: Vec::new(),
            remaining: 11,
            error: 28,
        };
        let error = commit_bytes(&mut writer, &[3; 64]).expect_err("must fail");
        assert!(matches!(error, JournalError::StorageFull));
        assert_eq!(writer.bytes.len(), 11);
    }

    #[test]
    fn a_concurrent_reader_reports_partial_append_as_torn_not_corrupt() {
        let directory = temp_dir("reader");
        let path = directory.join("journal.bin");
        let mut journal =
            ReceiptJournal::create(&path, JournalId([14; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append");
        drop(journal);
        let path_for_writer = path.clone();
        let writer = thread::spawn(move || {
            let mut file = OpenOptions::new()
                .append(true)
                .open(path_for_writer)
                .expect("open append");
            file.write_all(&RECORD_MAGIC[..5]).expect("partial write");
            file.sync_data().expect("sync");
        });
        writer.join().expect("join");
        let report = inspect_path(&path).expect("inspect");
        assert!(matches!(report.tail, TailStatus::TornTail { .. }));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn secret_redacted_detail_is_rejected_before_persistence() {
        let mut value = event("receipt-1", LifecycleState::Requested);
        value.privacy_class = PrivacyClass::SecretRedacted;
        value.detail = Some("secret".to_owned());
        assert!(matches!(
            value.validate(),
            Err(JournalError::InvalidInput(_))
        ));
    }
}
