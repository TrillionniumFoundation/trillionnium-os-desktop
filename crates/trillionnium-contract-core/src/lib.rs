#![forbid(unsafe_code)]

//! Platform-neutral contract primitives shared by the desktop product crates.
//! This crate deliberately contains no Android, Servo, shell, ADB, policy, or
//! transport implementation semantics.

use std::error::Error;
use std::fmt;

pub const MAX_REQUEST_ID_BYTES: usize = 128;
pub const MAX_SESSION_ID_BYTES: usize = 128;
pub const MAX_LEASE_ID_BYTES: usize = 128;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContractViolation {
    Empty {
        field: &'static str,
    },
    TooLong {
        field: &'static str,
        max_bytes: usize,
        actual_bytes: usize,
    },
    InvalidCharacter {
        field: &'static str,
    },
    InvalidSha256,
    InvalidDnsLabel,
}

impl fmt::Display for ContractViolation {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Empty { field } => write!(formatter, "{field} must not be empty"),
            Self::TooLong {
                field,
                max_bytes,
                actual_bytes,
            } => write!(
                formatter,
                "{field} exceeds {max_bytes} bytes (actual {actual_bytes})"
            ),
            Self::InvalidCharacter { field } => {
                write!(formatter, "{field} contains a forbidden character")
            }
            Self::InvalidSha256 => formatter.write_str("value is not lowercase sha256 hex"),
            Self::InvalidDnsLabel => {
                formatter.write_str("value is not a valid lowercase DNS label")
            }
        }
    }
}

impl Error for ContractViolation {}

#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct BoundedId<const MAX: usize>(String);

impl<const MAX: usize> BoundedId<MAX> {
    pub fn parse(field: &'static str, value: impl Into<String>) -> Result<Self, ContractViolation> {
        let value = value.into();
        if value.is_empty() {
            return Err(ContractViolation::Empty { field });
        }
        if value.len() > MAX {
            return Err(ContractViolation::TooLong {
                field,
                max_bytes: MAX,
                actual_bytes: value.len(),
            });
        }
        if !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':'))
        {
            return Err(ContractViolation::InvalidCharacter { field });
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn into_string(self) -> String {
        self.0
    }
}

impl<const MAX: usize> fmt::Debug for BoundedId<MAX> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.debug_tuple("BoundedId").field(&self.0).finish()
    }
}

impl<const MAX: usize> fmt::Display for BoundedId<MAX> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

pub type RequestId = BoundedId<MAX_REQUEST_ID_BYTES>;
pub type SessionId = BoundedId<MAX_SESSION_ID_BYTES>;
pub type LeaseId = BoundedId<MAX_LEASE_ID_BYTES>;

#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Sha256Hex(String);

impl Sha256Hex {
    pub fn parse(value: impl Into<String>) -> Result<Self, ContractViolation> {
        let value = value.into();
        if value.len() != 64
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        {
            return Err(ContractViolation::InvalidSha256);
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for Sha256Hex {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.debug_tuple("Sha256Hex").field(&self.0).finish()
    }
}

impl fmt::Display for Sha256Hex {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct DnsLabel(String);

impl DnsLabel {
    pub fn parse(value: impl Into<String>) -> Result<Self, ContractViolation> {
        let value = value.into();
        let bytes = value.as_bytes();
        let valid = !bytes.is_empty()
            && bytes.len() <= 63
            && bytes[0].is_ascii_alphanumeric()
            && bytes[bytes.len() - 1].is_ascii_alphanumeric()
            && bytes
                .iter()
                .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'-');
        if !valid {
            return Err(ContractViolation::InvalidDnsLabel);
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for DnsLabel {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.debug_tuple("DnsLabel").field(&self.0).finish()
    }
}

impl fmt::Display for DnsLabel {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct UnixMillis(i64);

impl UnixMillis {
    pub const fn new(value: i64) -> Self {
        Self(value)
    }

    pub const fn get(self) -> i64 {
        self.0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RevisionClock {
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub mutation_epoch: u64,
}

impl Default for RevisionClock {
    fn default() -> Self {
        Self::new()
    }
}

impl RevisionClock {
    pub const fn new() -> Self {
        Self {
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 0,
            mutation_epoch: 0,
        }
    }

    /// Advance the mutation epoch, failing before any state is changed when
    /// the identity space is exhausted.
    pub fn try_on_dom_commit(&mut self) -> Result<(), RevisionError> {
        let next = self
            .mutation_epoch
            .checked_add(1)
            .ok_or(RevisionError::MutationEpochExhausted)?;
        self.mutation_epoch = next;
        Ok(())
    }

    /// Advance the semantic snapshot revision atomically, failing closed on
    /// exhaustion.
    pub fn try_on_semantic_snapshot(&mut self) -> Result<(), RevisionError> {
        let next = self
            .semantic_snapshot_revision
            .checked_add(1)
            .ok_or(RevisionError::SemanticSnapshotExhausted)?;
        self.semantic_snapshot_revision = next;
        Ok(())
    }

    /// Advance every layer invalidated by a committed navigation as one
    /// atomic operation.  No field changes if any successor cannot be
    /// represented.
    pub fn try_on_navigation_commit(&mut self) -> Result<(), RevisionError> {
        let document_generation = self
            .document_generation
            .checked_add(1)
            .ok_or(RevisionError::DocumentGenerationExhausted)?;
        let semantic_snapshot_revision = self
            .semantic_snapshot_revision
            .checked_add(1)
            .ok_or(RevisionError::SemanticSnapshotExhausted)?;
        let mutation_epoch = self
            .mutation_epoch
            .checked_add(1)
            .ok_or(RevisionError::MutationEpochExhausted)?;
        self.document_generation = document_generation;
        self.semantic_snapshot_revision = semantic_snapshot_revision;
        self.mutation_epoch = mutation_epoch;
        Ok(())
    }

    /// Advance all identity layers after process recovery atomically.  A
    /// failed preflight leaves the prior clock intact so callers cannot emit a
    /// recovery event that only partially invalidates references.
    pub fn try_on_process_recovery(&mut self) -> Result<(), RevisionError> {
        let session_generation = self
            .session_generation
            .checked_add(1)
            .ok_or(RevisionError::SessionGenerationExhausted)?;
        let document_generation = self
            .document_generation
            .checked_add(1)
            .ok_or(RevisionError::DocumentGenerationExhausted)?;
        let semantic_snapshot_revision = self
            .semantic_snapshot_revision
            .checked_add(1)
            .ok_or(RevisionError::SemanticSnapshotExhausted)?;
        let mutation_epoch = self
            .mutation_epoch
            .checked_add(1)
            .ok_or(RevisionError::MutationEpochExhausted)?;
        self.session_generation = session_generation;
        self.document_generation = document_generation;
        self.semantic_snapshot_revision = semantic_snapshot_revision;
        self.mutation_epoch = mutation_epoch;
        Ok(())
    }

    /// Backwards-compatible infallible wrapper.  Existing callers that do
    /// not inspect transition errors retain their API; once exhausted, the
    /// clock remains at its terminal value and `classify_reference` rejects
    /// references carrying that value instead of treating them as current.
    pub fn on_dom_commit(&mut self) {
        let _ = self.try_on_dom_commit();
    }

    /// Backwards-compatible infallible wrapper around
    /// [`Self::try_on_semantic_snapshot`].
    pub fn on_semantic_snapshot(&mut self) {
        let _ = self.try_on_semantic_snapshot();
    }

    /// Backwards-compatible infallible wrapper around
    /// [`Self::try_on_navigation_commit`].
    pub fn on_navigation_commit(&mut self) {
        let _ = self.try_on_navigation_commit();
    }

    /// Backwards-compatible infallible wrapper around
    /// [`Self::try_on_process_recovery`].
    pub fn on_process_recovery(&mut self) {
        let _ = self.try_on_process_recovery();
    }
}

/// A revision layer reached the terminal representable value.  Advancing it
/// would wrap and could make a stale reference numerically equal to a fresh
/// one, so transitions must fail closed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RevisionError {
    SessionGenerationExhausted,
    DocumentGenerationExhausted,
    SemanticSnapshotExhausted,
    MutationEpochExhausted,
}

impl fmt::Display for RevisionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let field = match self {
            Self::SessionGenerationExhausted => "session generation",
            Self::DocumentGenerationExhausted => "document generation",
            Self::SemanticSnapshotExhausted => "semantic snapshot revision",
            Self::MutationEpochExhausted => "mutation epoch",
        };
        write!(formatter, "{field} exhausted")
    }
}

impl std::error::Error for RevisionError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RefFreshness {
    Current,
    StaleSession,
    StaleDocument,
    StaleSnapshot,
}

pub fn classify_reference(
    current: RevisionClock,
    session_generation: u64,
    document_generation: u64,
    semantic_snapshot_revision: u64,
) -> RefFreshness {
    // MAX is a terminal sentinel, not a usable identity.  Treating a caller
    // carrying MAX as current would allow old references to survive after a
    // saturating counter hit its boundary.  Reject the current side too so a
    // freshly minted value at the boundary cannot be mistaken for a valid
    // reference.
    if current.session_generation != session_generation
        || current.session_generation == u64::MAX
        || session_generation == u64::MAX
    {
        RefFreshness::StaleSession
    } else if current.document_generation != document_generation
        || current.document_generation == u64::MAX
        || document_generation == u64::MAX
    {
        RefFreshness::StaleDocument
    } else if current.semantic_snapshot_revision != semantic_snapshot_revision
        || current.semantic_snapshot_revision == u64::MAX
        || semantic_snapshot_revision == u64::MAX
    {
        RefFreshness::StaleSnapshot
    } else {
        RefFreshness::Current
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounded_ids_reject_path_and_whitespace_characters() {
        assert!(RequestId::parse("request_id", "request:one-2_3.4").is_ok());
        assert!(RequestId::parse("request_id", "request/one").is_err());
        assert!(RequestId::parse("request_id", "request one").is_err());
    }

    #[test]
    fn sha256_is_lowercase_and_exact_length() {
        assert!(Sha256Hex::parse("a".repeat(64)).is_ok());
        assert!(Sha256Hex::parse("A".repeat(64)).is_err());
        assert!(Sha256Hex::parse("a".repeat(63)).is_err());
    }

    #[test]
    fn dns_labels_are_origin_safe_components() {
        assert!(DnsLabel::parse("first-party").is_ok());
        assert!(DnsLabel::parse("-first-party").is_err());
        assert!(DnsLabel::parse("FirstParty").is_err());
        assert!(DnsLabel::parse("first.party").is_err());
    }

    #[test]
    fn dom_mutation_does_not_change_document_or_snapshot_identity() {
        let mut clock = RevisionClock::new();
        clock.on_semantic_snapshot();
        let before = clock;
        clock.on_dom_commit();
        assert_eq!(clock.document_generation, before.document_generation);
        assert_eq!(
            clock.semantic_snapshot_revision,
            before.semantic_snapshot_revision
        );
        assert_eq!(clock.mutation_epoch, before.mutation_epoch + 1);
    }

    #[test]
    fn navigation_and_recovery_invalidate_references_at_distinct_layers() {
        let mut clock = RevisionClock::new();
        clock.on_semantic_snapshot();
        let original = clock;
        assert_eq!(
            classify_reference(
                clock,
                original.session_generation,
                original.document_generation,
                original.semantic_snapshot_revision
            ),
            RefFreshness::Current
        );

        clock.on_navigation_commit();
        assert_eq!(
            classify_reference(
                clock,
                original.session_generation,
                original.document_generation,
                original.semantic_snapshot_revision
            ),
            RefFreshness::StaleDocument
        );

        clock.on_process_recovery();
        assert_eq!(
            classify_reference(
                clock,
                original.session_generation,
                original.document_generation,
                original.semantic_snapshot_revision
            ),
            RefFreshness::StaleSession
        );
    }

    #[test]
    fn checked_revision_advancement_is_atomic_at_exhaustion() {
        let mut clock = RevisionClock::new();
        clock.mutation_epoch = u64::MAX;
        let before = clock;
        assert_eq!(
            clock.try_on_dom_commit(),
            Err(RevisionError::MutationEpochExhausted)
        );
        assert_eq!(clock, before);

        let mut clock = RevisionClock {
            document_generation: u64::MAX,
            ..RevisionClock::new()
        };
        let before = clock;
        assert_eq!(
            clock.try_on_navigation_commit(),
            Err(RevisionError::DocumentGenerationExhausted)
        );
        assert_eq!(
            clock, before,
            "compound transition must not partially advance"
        );

        let mut clock = RevisionClock {
            session_generation: u64::MAX,
            ..RevisionClock::new()
        };
        let before = clock;
        assert_eq!(
            clock.try_on_process_recovery(),
            Err(RevisionError::SessionGenerationExhausted)
        );
        assert_eq!(clock, before, "recovery preflight must be atomic");
    }

    #[test]
    fn exhausted_revision_values_are_never_classified_current() {
        let mut cases = Vec::new();
        let mut session = RevisionClock::new();
        session.session_generation = u64::MAX;
        cases.push((session, RefFreshness::StaleSession));
        let mut document = RevisionClock::new();
        document.document_generation = u64::MAX;
        cases.push((document, RefFreshness::StaleDocument));
        let mut snapshot = RevisionClock::new();
        snapshot.semantic_snapshot_revision = u64::MAX;
        cases.push((snapshot, RefFreshness::StaleSnapshot));

        for (clock, expected) in cases {
            assert_eq!(
                classify_reference(
                    clock,
                    clock.session_generation,
                    clock.document_generation,
                    clock.semantic_snapshot_revision,
                ),
                expected
            );
        }
    }
}
