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
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process;

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
        validate_token("plan_revision", &self.plan_revision, 1, 64)?;
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
    path: PathBuf,
}

impl WriterLease {
    fn acquire(journal_path: &Path, recover_stale: bool) -> Result<Self, JournalError> {
        let path = writer_lock_path(journal_path)?;
        let identity = ProcessIdentity::current()?;
        let payload = identity.encode();
        match create_private_file(&path, true) {
            Ok(mut file) => {
                file.write_all(payload.as_bytes()).map_err(map_io_error)?;
                file.sync_all().map_err(map_io_error)?;
                sync_parent(&path)?;
                Ok(Self { path })
            }
            Err(JournalError::Io(error)) if error.kind() == io::ErrorKind::AlreadyExists => {
                let active = ProcessIdentity::from_lock_file(&path)
                    .and_then(|existing| existing.is_active())
                    .unwrap_or(false);
                if active {
                    return Err(JournalError::WriterBusy);
                }
                if !recover_stale {
                    return Err(JournalError::StaleWriterLease);
                }
                fs::remove_file(&path).map_err(map_io_error)?;
                sync_parent(&path)?;
                let mut file = create_private_file(&path, true)?;
                file.write_all(payload.as_bytes()).map_err(map_io_error)?;
                file.sync_all().map_err(map_io_error)?;
                sync_parent(&path)?;
                Ok(Self { path })
            }
            Err(error) => Err(error),
        }
    }
}

impl Drop for WriterLease {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
        let _ = sync_parent(&self.path);
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ProcessIdentity {
    pid: u32,
    start_time_ticks: u64,
    boot_id: String,
}

impl ProcessIdentity {
    fn current() -> Result<Self, JournalError> {
        let pid = process::id();
        let start_time_ticks = process_start_time(pid)?;
        let boot_id =
            read_bounded_text(Path::new("/proc/sys/kernel/random/boot_id"), 128, "boot_id")?;
        Ok(Self {
            pid,
            start_time_ticks,
            boot_id: boot_id.trim().to_owned(),
        })
    }

    fn encode(&self) -> String {
        format!(
            "pid={}\nstart_time_ticks={}\nboot_id={}\n",
            self.pid, self.start_time_ticks, self.boot_id
        )
    }

    fn from_lock_file(path: &Path) -> Result<Self, JournalError> {
        let text = read_bounded_text(path, 1024, "writer lease")?;
        let mut pid = None;
        let mut start_time_ticks = None;
        let mut boot_id = None;
        for line in text.lines() {
            if let Some(value) = line.strip_prefix("pid=") {
                pid = value.parse::<u32>().ok();
            } else if let Some(value) = line.strip_prefix("start_time_ticks=") {
                start_time_ticks = value.parse::<u64>().ok();
            } else if let Some(value) = line.strip_prefix("boot_id=") {
                boot_id = Some(value.to_owned());
            }
        }
        Ok(Self {
            pid: pid.ok_or(JournalError::InvalidRecord("writer lease lacks pid"))?,
            start_time_ticks: start_time_ticks
                .ok_or(JournalError::InvalidRecord("writer lease lacks start time"))?,
            boot_id: boot_id.ok_or(JournalError::InvalidRecord("writer lease lacks boot id"))?,
        })
    }

    fn is_active(&self) -> Result<bool, JournalError> {
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

pub struct ReceiptJournal {
    path: PathBuf,
    file: File,
    _lease: WriterLease,
    header: SegmentHeader,
    next_sequence: u64,
    previous_record_sha256: Digest,
    progress: HashMap<String, ReceiptProgress>,
    end_offset: u64,
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
        )
    }

    fn create_segment(
        path: &Path,
        header: SegmentHeader,
        recover_stale_writer_lease: bool,
    ) -> Result<Self, JournalError> {
        validate_new_path(path)?;
        validate_segment_header(&header)?;
        let lease = WriterLease::acquire(path, recover_stale_writer_lease)?;
        let mut file = create_private_file(path, true)?;
        let encoded = encode_segment_header(&header)?;
        commit_bytes(&mut file, &encoded)?;
        sync_parent(path)?;
        Ok(Self {
            path: path.to_owned(),
            file,
            _lease: lease,
            next_sequence: header.first_sequence,
            previous_record_sha256: header.previous_record_sha256,
            progress: HashMap::new(),
            end_offset: encoded.len() as u64,
            header,
            poisoned: false,
        })
    }

    pub fn open(path: impl AsRef<Path>, policy: OpenPolicy) -> Result<Self, JournalError> {
        let path = path.as_ref();
        validate_existing_path(path)?;
        let lease = WriterLease::acquire(path, policy.recover_stale_writer_lease)?;
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(path)
            .map_err(map_io_error)?;
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
            end_offset: report.last_complete_offset,
            poisoned: false,
        })
    }

    pub fn append(&mut self, event: ReceiptEvent) -> Result<CommittedRecord, JournalError> {
        if self.poisoned {
            return Err(JournalError::WriterPoisoned);
        }
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
        let committed = CommittedRecord {
            sequence: self.next_sequence,
            record_sha256: digest,
            end_offset: new_size,
        };
        self.next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or_else(|| JournalError::InvalidInput("sequence overflow".into()))?;
        self.previous_record_sha256 = digest;
        self.end_offset = new_size;
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
        recover_file(&mut self.file)
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
        let seal = self.seal()?;
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
            )?;
        Ok((seal, next))
    }

    pub fn path(&self) -> &Path {
        &self.path
    }
}

pub fn inspect_path(path: impl AsRef<Path>) -> Result<RecoveryReport, JournalError> {
    let path = path.as_ref();
    validate_existing_path(path)?;
    let mut file = File::open(path).map_err(map_io_error)?;
    recover_file(&mut file)
}

pub fn export_redacted_jsonl(
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
    OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(create_new)
        .mode(0o600)
        .open(path)
        .map_err(map_io_error)
}

fn validate_new_path(path: &Path) -> Result<(), JournalError> {
    if path.as_os_str().is_empty() || path.file_name().is_none() {
        return Err(JournalError::InsecurePath(
            "path must name a regular file".into(),
        ));
    }
    if fs::symlink_metadata(path).is_ok() {
        return Err(JournalError::InsecurePath(
            "destination already exists".into(),
        ));
    }
    let parent = path
        .parent()
        .ok_or_else(|| JournalError::InsecurePath("journal path has no parent directory".into()))?;
    let metadata = fs::symlink_metadata(parent).map_err(map_io_error)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(JournalError::InsecurePath(
            "parent must be a real directory".into(),
        ));
    }
    Ok(())
}

fn validate_existing_path(path: &Path) -> Result<(), JournalError> {
    let metadata = fs::symlink_metadata(path).map_err(map_io_error)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(JournalError::InsecurePath(
            "journal must be a regular non-symlink file".into(),
        ));
    }
    if metadata.permissions().mode() & 0o077 != 0 {
        return Err(JournalError::InsecurePath(
            "journal permissions must not grant group/other access".into(),
        ));
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
    let end = stat.rfind(')').ok_or(JournalError::InvalidRecord(
        "process stat lacks command terminator",
    ))?;
    let fields: Vec<&str> = stat[end + 1..].split_whitespace().collect();
    let value = fields
        .get(19)
        .ok_or(JournalError::InvalidRecord("process stat lacks start time"))?;
    value
        .parse::<u64>()
        .map_err(|_| JournalError::InvalidRecord("process start time is invalid"))
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
        let export_digest = export_redacted_jsonl(&report, &export).expect("export");
        let text = fs::read_to_string(&export).expect("read export");
        assert!(!text.contains("must-not-export"));
        assert!(text.contains("\"detail\":null"));
        assert_ne!(export_digest, ZERO_DIGEST);
        fs::remove_dir_all(directory).expect("cleanup");
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
